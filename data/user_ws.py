"""
User-channel WebSocket consumer — wss://ws-subscriptions-clob.polymarket.com/ws/user

Streams OUR OWN order/trade events in real time, authed with the CLOB API creds
the OrderManager already derives. Three jobs:

1. Durable event log — every event is appended to
   logs/shadow/hot/<utc-date>/user_ws.jsonl (forensics for the maker paths).
2. Low-latency fill TRIGGER — on a trade event the registered callback fires
   (weather_arb points it at _maker_reconcile_fills), replacing the worst-case
   300s REST-poll latency with ~1s. The WS is a trigger ONLY: fill accounting
   still flows through the idempotent REST reconcile (get_order_match), so a
   dropped WS message can never lose a fill and a duplicate can never
   double-book one.
3. UNTRACKED-FILL alarm — a fill on a token with no tracker entry and no open
   position is the invisible-position bug class (restart amnesia / Munich
   double-fill 2026-06-09); the callback can now log it the second it happens
   instead of discovering it at resolution.

Protocol (docs.polymarket.com/api-reference/wss/user): auth message on connect
{auth:{apiKey,secret,passphrase}, type:"user"}; omitting `markets` receives all
events for the account; server requires a plain-text PING under every 10s.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import aiohttp

logger = logging.getLogger(__name__)


class UserWsFeed:
    """Maintains the authed user-channel connection; reconnects forever."""

    URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

    def __init__(
        self,
        creds_getter: Callable[[], Any],
        on_trade: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> None:
        # creds_getter: () -> py_clob_client ApiCreds | None (None ⇒ idle, e.g. dry-run)
        self._creds_getter = creds_getter
        self._on_trade = on_trade
        self._task: Optional[asyncio.Task] = None
        self._seen: dict = {}  # (trade_id, status) → recv_ts; dedup across re-emits
        self.events_total = 0
        self.last_event_ts = 0.0

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run(), name="user_ws_feed")
        return self._task

    async def run(self) -> None:
        backoff = 5.0
        while True:
            creds = None
            try:
                creds = self._creds_getter()
            except Exception:
                pass
            if creds is None:
                await asyncio.sleep(60.0)
                continue
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    ssl_ctx = _ssl.create_default_context()
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(
                        self.URL, ssl=ssl_ctx, heartbeat=20.0
                    ) as ws:
                        await ws.send_str(json.dumps({
                            "auth": {
                                "apiKey": creds.api_key,
                                "secret": creds.api_secret,
                                "passphrase": creds.api_passphrase,
                            },
                            "type": "user",
                        }))
                        logger.info("[USER-WS] connected + auth sent")
                        backoff = 5.0
                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=9.0)
                            except asyncio.TimeoutError:
                                await ws.send_str("PING")  # text PING <10s required
                                continue
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.data
                                if not data or data == "PONG":
                                    continue
                                try:
                                    payload = json.loads(data)
                                except ValueError:
                                    continue
                                events = payload if isinstance(payload, list) else [payload]
                                for ev in events:
                                    if isinstance(ev, dict):
                                        await self._handle(ev)
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[USER-WS] connection error: %s", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 120.0)

    async def _handle(self, ev: dict) -> None:
        self.events_total += 1
        self.last_event_ts = time.time()
        self._log(ev)
        if str(ev.get("event_type") or "") != "trade":
            return
        # Trades re-emit on status transitions (MATCHED→MINED→CONFIRMED…);
        # fire the callback once per (id, status).
        key = (str(ev.get("id") or ""), str(ev.get("status") or ""))
        if key in self._seen:
            return
        self._seen[key] = time.time()
        if len(self._seen) > 2000:
            for k in sorted(self._seen, key=self._seen.get)[:1000]:
                self._seen.pop(k, None)
        if self._on_trade is not None:
            try:
                await self._on_trade(ev)
            except Exception:
                logger.exception("[USER-WS] on_trade callback failed")

    def _log(self, ev: dict) -> None:
        try:
            d = Path("logs/shadow/hot") / datetime.now(timezone.utc).date().isoformat()
            d.mkdir(parents=True, exist_ok=True)
            with (d / "user_ws.jsonl").open("a") as f:
                f.write(json.dumps({"recv_ts": round(time.time(), 3), "ev": ev}) + "\n")
        except Exception:
            pass
