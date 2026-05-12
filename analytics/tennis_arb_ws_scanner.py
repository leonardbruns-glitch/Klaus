"""
Tennis arbitrage scanner — WebSocket version (ms resolution).

Subscribes to all active ATP/WTA market token_ids via Polymarket CLOB WS.
Maintains in-memory best_ask / best_bid per token. Recomputes sum_ask for
the affected market on EVERY book event. Logs when sum_ask drops below the
arb threshold within milliseconds of the book change.

Key differences from REST scanner:
  - Push-based: we get updates within ms of the book change, not 4s later
  - Per-market pair grouping: each market = 2 tokens; we know both books
  - Sub-second timestamps logged for latency analysis
  - One persistent connection; no per-cycle HTTP overhead

Architecture:
  1. Fetch active tennis markets via gamma (every METADATA_REFRESH_S)
  2. Diff against currently-subscribed token set; send new subs
  3. WS event loop: parse book/price_change/best_bid_ask, update state, check arb

Output: logs/shadow/hot/<date>/tennis_arb_ws.jsonl

Run on VPS:
    setsid python3 -m analytics.tennis_arb_ws_scanner &
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA = "https://gamma-api.polymarket.com"

VOL_TOTAL_MIN = 2_000            # user instruction: include thin-market niche
VOL_TOTAL_MAX = 500_000
VOL_24H_MIN = 500                # any activity today, however small

FEE_BPS = 200
FEE_DRAG_PCT = 0.04
SLIPPAGE_BUFFER = 0.01
ARB_THRESHOLD = 1.00 - FEE_DRAG_PCT - SLIPPAGE_BUFFER   # 0.95
NEAR_MISS_THRESHOLD = 1.02
METADATA_REFRESH_S = 120.0

LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
LOG_NAME = "tennis_arb_ws.jsonl"

logger = logging.getLogger("tennis_arb_ws")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def log_path() -> Path:
    p = LOG_DIR / utc_today() / LOG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(ev: dict) -> None:
    line = json.dumps(ev, separators=(",", ":"), default=str)
    with log_path().open("a") as f:
        f.write(line + "\n")


class TennisArbWS:
    def __init__(self):
        # token_id -> (cid, slug, outcome_index, outcomes_list)
        self.token_meta: dict[str, dict] = {}
        # token_id -> best_ask price + size (we maintain top-of-book per token)
        self.best_ask: dict[str, tuple[float, float]] = {}
        self.best_bid: dict[str, tuple[float, float]] = {}
        # condition_id -> [token_a, token_b]
        self.cid_to_tokens: dict[str, list[str]] = {}
        # last sum_ask we logged per cid (suppress noise)
        self.last_logged_sum: dict[str, float] = {}
        # Stats
        self.stats = {
            "events": 0,
            "arb_fires": 0,
            "near_miss": 0,
            "ws_reconnects": 0,
        }
        # Pending subs to send on next opportunity
        self._new_subs_queue: asyncio.Queue = asyncio.Queue()
        self._subscribed: set[str] = set()

    async def fetch_markets(self, sess: aiohttp.ClientSession) -> list[dict]:
        out = []
        seen = set()
        for offset in (0, 500):
            try:
                async with sess.get(f"{GAMMA}/markets",
                                    params={"closed": "false", "order": "volume24hr",
                                            "ascending": "false", "limit": 500, "offset": offset},
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        continue
                    d = await r.json()
            except Exception:
                continue
            if not isinstance(d, list) or not d:
                break
            for m in d:
                slug = (m.get("slug") or "").lower()
                if not ("atp-" in slug or "wta-" in slug):
                    continue
                cid = m.get("conditionId")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                vol = float(m.get("volume", 0) or 0)
                vol24 = float(m.get("volume24hr", 0) or 0)
                if not (VOL_TOTAL_MIN <= vol <= VOL_TOTAL_MAX):
                    continue
                if vol24 < VOL_24H_MIN:
                    continue
                ctokens = m.get("clobTokenIds")
                if isinstance(ctokens, str):
                    try:
                        ctokens = json.loads(ctokens)
                    except json.JSONDecodeError:
                        continue
                if not ctokens or len(ctokens) != 2:
                    continue
                outcomes = m.get("outcomes")
                if isinstance(outcomes, str):
                    try:
                        outcomes = json.loads(outcomes)
                    except json.JSONDecodeError:
                        outcomes = None
                out.append({
                    "conditionId": cid,
                    "slug": m.get("slug"),
                    "volume": vol,
                    "volume24hr": vol24,
                    "clobTokenIds": [str(c) for c in ctokens],
                    "outcomes": outcomes,
                })
        return out

    def _register_market(self, m: dict) -> list[str]:
        """Returns list of new token_ids to subscribe."""
        new_tokens = []
        cid = m["conditionId"]
        tokens = m["clobTokenIds"]
        self.cid_to_tokens[cid] = tokens
        for i, tok in enumerate(tokens):
            if tok not in self.token_meta:
                self.token_meta[tok] = {
                    "cid": cid,
                    "slug": m["slug"],
                    "outcome_index": i,
                    "outcomes": m.get("outcomes"),
                    "volume": m["volume"],
                }
                new_tokens.append(tok)
        return new_tokens

    async def _maybe_log_arb(self, cid: str, src_token: str) -> None:
        tokens = self.cid_to_tokens.get(cid)
        if not tokens or len(tokens) != 2:
            return
        ba = self.best_ask.get(tokens[0])
        bb = self.best_ask.get(tokens[1])
        if not ba or not bb:
            return
        ask_a, sz_a = ba
        ask_b, sz_b = bb
        if ask_a <= 0 or ask_b <= 0:
            return
        sum_ask = ask_a + ask_b
        last_logged = self.last_logged_sum.get(cid, 999.0)
        # Only log when state CROSSES a threshold (avoid spamming)
        if sum_ask >= NEAR_MISS_THRESHOLD:
            self.last_logged_sum[cid] = sum_ask
            return
        # crossed below threshold from above; log
        if last_logged < sum_ask + 0.001:
            # No improvement vs last log; suppress
            return
        capacity = min(ask_a * sz_a, ask_b * sz_b)
        bid_a = self.best_bid.get(tokens[0], (0, 0))[0]
        bid_b = self.best_bid.get(tokens[1], (0, 0))[0]
        meta = self.token_meta.get(src_token, {})
        rec_type = "ARB_OPPORTUNITY" if sum_ask < ARB_THRESHOLD else "NEAR_MISS"
        if rec_type == "ARB_OPPORTUNITY":
            self.stats["arb_fires"] += 1
        else:
            self.stats["near_miss"] += 1
        ev = {
            "rec": rec_type,
            "ts": time.time(),                   # sub-second precision
            "iso": datetime.utcnow().isoformat(),
            "condition_id": cid,
            "slug": meta.get("slug"),
            "outcomes": meta.get("outcomes"),
            "volume_total": meta.get("volume"),
            "src_token_short": src_token[:14],
            "best_ask_a": round(ask_a, 4),
            "best_ask_b": round(ask_b, 4),
            "sum_ask": round(sum_ask, 4),
            "edge_pct": round((1 - sum_ask) * 100, 3),
            "best_bid_a": round(bid_a, 4),
            "best_bid_b": round(bid_b, 4),
            "size_at_ask_a": round(sz_a, 2),
            "size_at_ask_b": round(sz_b, 2),
            "cap_usd_min": round(capacity, 2),
            "fireable_at_5usd_per_leg": capacity >= 5.0 and sum_ask < ARB_THRESHOLD,
        }
        record(ev)
        self.last_logged_sum[cid] = sum_ask
        if rec_type == "ARB_OPPORTUNITY":
            logger.info("FIRE  %s sum=%.3f edge=%.2f%% cap=$%.0f  %s",
                        rec_type, sum_ask, ev["edge_pct"], capacity, (meta.get("slug") or "")[:40])

    async def handle_event(self, ev: dict) -> None:
        self.stats["events"] += 1
        ev_type = ev.get("event_type", ev.get("type", ""))
        asset_id = ev.get("asset_id", ev.get("market", ""))
        if not asset_id or asset_id not in self.token_meta:
            return
        # Extract top-of-book from various event types
        new_ask: Optional[tuple[float, float]] = None
        new_bid: Optional[tuple[float, float]] = None
        if ev_type in ("book", "price_change"):
            asks = ev.get("asks") or []
            bids = ev.get("bids") or []
            # asks come as list; pick lowest price
            parsed_a = []
            for lv in asks:
                try:
                    p = float(lv[0] if isinstance(lv, (list, tuple)) else lv.get("price", 0))
                    s = float(lv[1] if isinstance(lv, (list, tuple)) else lv.get("size", 0))
                    if p > 0 and s > 0:
                        parsed_a.append((p, s))
                except Exception:
                    pass
            parsed_b = []
            for lv in bids:
                try:
                    p = float(lv[0] if isinstance(lv, (list, tuple)) else lv.get("price", 0))
                    s = float(lv[1] if isinstance(lv, (list, tuple)) else lv.get("size", 0))
                    if p > 0 and s > 0:
                        parsed_b.append((p, s))
                except Exception:
                    pass
            if parsed_a:
                parsed_a.sort(key=lambda x: x[0])
                new_ask = parsed_a[0]
            if parsed_b:
                parsed_b.sort(key=lambda x: -x[0])
                new_bid = parsed_b[0]
        elif ev_type == "best_bid_ask":
            try:
                ba = ev.get("best_ask")
                bb = ev.get("best_bid")
                if ba is not None:
                    new_ask = (float(ba), 100.0)  # size unknown from BBO event
                if bb is not None:
                    new_bid = (float(bb), 100.0)
            except Exception:
                pass

        if new_ask:
            self.best_ask[asset_id] = new_ask
        if new_bid:
            self.best_bid[asset_id] = new_bid

        if new_ask:
            cid = self.token_meta[asset_id]["cid"]
            await self._maybe_log_arb(cid, asset_id)

    async def metadata_refresh_loop(self, sess: aiohttp.ClientSession) -> None:
        while True:
            try:
                markets = await self.fetch_markets(sess)
                new_subs = []
                for m in markets:
                    new_subs.extend(self._register_market(m))
                new_subs = [t for t in new_subs if t not in self._subscribed]
                if new_subs:
                    await self._new_subs_queue.put(new_subs)
                    logger.info("metadata refresh — %d markets tracked, +%d new tokens to subscribe",
                                len(markets), len(new_subs))
            except Exception as exc:
                logger.exception("metadata refresh err: %s", exc)
            await asyncio.sleep(METADATA_REFRESH_S)

    async def stats_loop(self) -> None:
        last = dict(self.stats)
        while True:
            await asyncio.sleep(30)
            d_ev = self.stats["events"] - last.get("events", 0)
            d_arb = self.stats["arb_fires"] - last.get("arb_fires", 0)
            d_nm = self.stats["near_miss"] - last.get("near_miss", 0)
            logger.info("stats — markets=%d tokens=%d  events(+%d) arb_fires(+%d) near_miss(+%d)  totals: arb=%d near=%d ev=%d",
                        len(self.cid_to_tokens), len(self.token_meta),
                        d_ev, d_arb, d_nm,
                        self.stats["arb_fires"], self.stats["near_miss"], self.stats["events"])
            last = dict(self.stats)

    async def ws_loop(self) -> None:
        async with aiohttp.ClientSession() as http_sess:
            # Initial market discovery
            markets = await self.fetch_markets(http_sess)
            new_subs = []
            for m in markets:
                new_subs.extend(self._register_market(m))
            logger.info("startup — %d markets, %d tokens to subscribe", len(markets), len(new_subs))
            # Background metadata refresher + stats
            asyncio.create_task(self.metadata_refresh_loop(http_sess))
            asyncio.create_task(self.stats_loop())

            while True:
                try:
                    async with http_sess.ws_connect(
                        CLOB_WS,
                        heartbeat=15,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as ws:
                        if new_subs:
                            await ws.send_str(json.dumps({
                                "auth": {}, "type": "subscribe", "channel": "market",
                                "assets_ids": new_subs, "custom_feature_enabled": True,
                            }))
                            self._subscribed.update(new_subs)
                            logger.info("subscribed to %d tokens", len(new_subs))
                            new_subs = []
                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                            except asyncio.TimeoutError:
                                while not self._new_subs_queue.empty():
                                    batch = await self._new_subs_queue.get()
                                    truly_new = [t for t in batch if t not in self._subscribed]
                                    if truly_new:
                                        await ws.send_str(json.dumps({
                                            "auth": {}, "type": "subscribe", "channel": "market",
                                            "assets_ids": truly_new, "custom_feature_enabled": True,
                                        }))
                                        self._subscribed.update(truly_new)
                                        logger.info("re-subscribed to %d new tokens (%d total)",
                                                    len(truly_new), len(self._subscribed))
                                continue
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    events = json.loads(msg.data)
                                except json.JSONDecodeError:
                                    continue
                                if not isinstance(events, list):
                                    events = [events]
                                for ev in events:
                                    await self.handle_event(ev)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                except Exception as exc:
                    self.stats["ws_reconnects"] += 1
                    logger.warning("WS dropped (%s) — reconnect in 2s", exc)
                    # Re-subscribe everything on reconnect
                    new_subs = list(self._subscribed)
                    self._subscribed.clear()
                    await asyncio.sleep(2)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logger.info("tennis_arb_ws starting — WS ms-resolution scanner")
    logger.info("logs → %s", LOG_DIR / "<date>" / LOG_NAME)
    scanner = TennisArbWS()
    asyncio.run(scanner.ws_loop())


if __name__ == "__main__":
    main()
