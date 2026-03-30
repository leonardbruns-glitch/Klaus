"""
Klaus — Fill Tracker
Subscribes to Polymarket user channel WebSocket for real-time order fill events.

Endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/user
Auth: API key + secret + passphrase (from CLOB client credentials).

Provides sub-100ms fill detection via asyncio.Event instead of REST polling.
Used by OrderManager.wait_fill(order_id) in place of the 2s polling loop.

Trade event schema (from Polymarket docs):
{
  "event_type": "trade",
  "id":               "trade_id",
  "taker_order_id":   "order_id_of_taker",
  "maker_order_id":   "order_id_of_maker",
  "asset_id":         "token_id",
  "price":            "0.5300",
  "size":             "4.9000",
  "side":             "BUY",
  "match_time":       "...",
  "status":           "MATCHED"
}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("fill_tracker")

USER_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"


class FillTracker:
    """
    Listens to the Polymarket user channel WebSocket.
    Any component can call wait_fill(order_id) to await a real-time fill
    notification instead of polling REST.

    Lifecycle:
        tracker = FillTracker()
        tracker.set_creds(key, secret, passphrase)
        await tracker.start()           # launches WS loop as background task
        result = await tracker.wait_fill(order_id, timeout=10.0)
        await tracker.stop()
    """

    def __init__(self) -> None:
        self._creds: Optional[dict] = None
        self._pending: Dict[str, asyncio.Event] = {}   # order_id → Event
        self._results: Dict[str, dict] = {}            # order_id → fill dict
        # Buffer for fills that arrived before wait_fill() registered the order_id.
        # Race: order fills within ~10ms of posting → WS event fires before wait_fill()
        # sets up the asyncio.Event → event silently dropped → 10s timeout → cancel.
        # Fix: _handle_event stores into _early_fills when order not yet in _pending;
        # wait_fill() checks this buffer first before waiting.
        self._early_fills: Dict[str, dict] = {}        # order_id → fill dict (pre-claim)
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_creds(self, api_key: str, api_secret: str, api_passphrase: str) -> None:
        """Must be called before start() with credentials from ClobClient."""
        # Polymarket user-channel WS subscription auth uses "apiKey" (not "key").
        # Using "key" causes the server to close the connection immediately,
        # triggering a reconnect loop every 2s.
        self._creds = {
            "apiKey": api_key,
            "secret": api_secret,
            "passphrase": api_passphrase,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._creds:
            logger.warning("FillTracker: no creds set — user WS disabled (dry run?)")
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._run_ws())
        logger.info("FillTracker: user channel WS starting")

    async def stop(self) -> None:
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()

    # ── Public API ────────────────────────────────────────────────────────────

    async def wait_fill(
        self,
        order_id: str,
        timeout: float = 10.0,
    ) -> Optional[dict]:
        """
        Wait for a fill event for order_id with a timeout.

        Returns a normalised fill dict on success:
            {"order_id", "size", "price", "cost"}
        Returns None on timeout or if WS is not connected (caller should
        fall back to REST polling).

        Race-condition safe: checks _early_fills buffer before registering,
        so fills that arrive between order posting and wait_fill() call are
        not dropped.
        """
        if not self._running or not self._connected:
            # WS not ready — signal caller to fall back to polling
            return None

        # ── Check early-arrival buffer first ─────────────────────────────────
        # Fill may have arrived before this call registered the order_id.
        if order_id in self._early_fills:
            fill = self._early_fills.pop(order_id)
            logger.debug("FillTracker: early-buffer hit for order %s", order_id[:12])
            return fill

        event = asyncio.Event()
        self._pending[order_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._results.pop(order_id, None)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending.pop(order_id, None)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── WebSocket loop ────────────────────────────────────────────────────────

    async def _run_ws(self) -> None:
        import json as _json

        try:
            import aiohttp
        except ImportError:
            logger.warning("FillTracker: aiohttp not available — user WS disabled")
            return

        while self._running:
            self._connected = False
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    _ssl_ctx = _ssl.create_default_context()
                    _ssl_ctx.check_hostname = False
                    _ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        USER_WS_URL,
                        ssl=_ssl_ctx,
                        heartbeat=15.0,
                    ) as ws:
                        sub = _json.dumps({
                            "type": "user",
                            "auth": self._creds,
                            "markets": [],   # empty = all markets for this user
                        })
                        await ws.send_str(sub)
                        self._connected = True
                        logger.info("FillTracker: user channel WS connected")

                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = _json.loads(msg.data)
                                    events = payload if isinstance(payload, list) else [payload]
                                    for ev in events:
                                        self._handle_event(ev)
                                except Exception:
                                    pass
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("FillTracker WS disconnected (%s) — reconnecting in 2s", exc)

            self._connected = False
            if self._running:
                await asyncio.sleep(2)

    # ── Event handler ─────────────────────────────────────────────────────────

    def _handle_event(self, ev: dict) -> None:
        """
        Match trade events to pending orders and fire their asyncio.Event.

        Polymarket sends "trade" events with status "MATCHED" when our GTC
        order fills. Both taker_order_id and maker_order_id are checked since
        our order can be on either side of the match.
        """
        ev_type = ev.get("event_type", ev.get("type", ""))
        if ev_type != "trade":
            return

        status = ev.get("status", "")
        if status.upper() not in ("MATCHED",):
            return

        # Extract the normalised fill result once, check both maker/taker IDs
        try:
            size = float(ev.get("size", 0))
            price = float(ev.get("price", 0))
            fill = {
                "order_id": "",
                "size": size,
                "price": price,
                "cost": round(size * price, 6),
                "raw": ev,
            }
        except Exception:
            return

        for id_field in ("taker_order_id", "maker_order_id", "id", "order_id"):
            order_id = ev.get(id_field, "")
            if not order_id:
                continue
            fill["order_id"] = order_id
            if order_id in self._pending:
                # Normal path: wait_fill() is already waiting
                self._results[order_id] = fill
                self._pending[order_id].set()
                logger.info(
                    "FillTracker: fill event → order %s | size=%.4f @ %.4f",
                    order_id[:12], size, price,
                )
                return
            else:
                # Early-arrival path: wait_fill() hasn't registered yet.
                # Buffer the fill so wait_fill() can claim it immediately.
                self._early_fills[order_id] = fill
                logger.info(
                    "FillTracker: early fill buffered for order %s | size=%.4f @ %.4f",
                    order_id[:12], size, price,
                )
                return
