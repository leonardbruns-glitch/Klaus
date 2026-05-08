"""Window resolution writer.

Mirrors main.py:_capture_resolution. Scans for windows that ended ≥35s ago and
haven't been resolved yet. Fetches Binance 5m kline (canonical resolution
source — see feedback_kline_resolution_canonical, >99% Chainlink agreement)
and emits one window_resolution record per (condition_id, window_end_ts).

Independent of trade execution: resolves every observed updown window,
including those the live bot did not trade.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set, Tuple

import aiohttp

from .pipeline import ShadowPipeline

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_SYMBOL_MAP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


class ResolutionWriter:
    def __init__(
        self,
        bot: Any,
        pipeline: ShadowPipeline,
        scan_interval_s: float = 30.0,
    ) -> None:
        self.bot = bot
        self.pipe = pipeline
        self.scan_interval_s = scan_interval_s
        # (condition_id, window_end_ts) — resolved or aged-out
        self._resolved: Set[Tuple[str, int]] = set()
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="shadow_resolution")
            logger.info("ResolutionWriter started — scan=%.0fs", self.scan_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._scan_once()
            except Exception:
                logger.exception("resolution scan failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.scan_interval_s)
            except asyncio.TimeoutError:
                pass
            # GC the resolved set occasionally — long-running bots accumulate.
            if len(self._resolved) > 5000:
                cutoff = int(time.time()) - 7 * 86400
                self._resolved = {(c, w) for (c, w) in self._resolved if w > cutoff}

    async def _scan_once(self) -> None:
        now = time.time()
        feed = self.bot.feed
        candidates: Dict[Tuple[str, int], dict] = {}
        for token_id, token in list(feed.tokens.items()):
            if getattr(token, "market_type", None) != "updown":
                continue
            wend = getattr(token, "window_end_ts", 0)
            if wend <= 0:
                continue
            cid = getattr(token, "condition_id", "") or ""
            if not cid:
                continue
            key = (cid, int(wend))
            if key in self._resolved:
                continue
            if now < wend + 35:
                continue
            if now > wend + 1800:
                self._resolved.add(key)
                continue
            # Dedup by (cid, wend) — both YES/NO sides share the same window.
            candidates[key] = {
                "asset": token.asset,
                "window_end_ts": int(wend),
                "window_size_s": int(getattr(token, "window_seconds", 300)),
                "outcome_dir": getattr(token, "outcome_direction", "up"),
            }
        for key, info in candidates.items():
            await self._resolve_one(key, info)

    async def _resolve_one(self, key: Tuple[str, int], info: dict) -> None:
        cid, wend = key
        asset_up = info["asset"].upper()
        symbol = _SYMBOL_MAP.get(asset_up)
        if symbol is None:
            self._resolved.add(key)
            return
        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            return  # retry next scan
        wstart_ms = int((wend - info["window_size_s"]) * 1000)
        try:
            async with session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": "5m",
                        "startTime": wstart_ms, "limit": 1},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return
                klines = await resp.json()
        except Exception as e:
            logger.debug("shadow kline fetch failed %s/%s: %s", asset_up, wend, e)
            return
        if not klines or len(klines[0]) < 5:
            return

        kopen  = float(klines[0][1])
        khigh  = float(klines[0][2])
        klow   = float(klines[0][3])
        kclose = float(klines[0][4])
        moved_up = kclose >= kopen
        realized_pct = (kclose - kopen) / kopen * 100.0 if kopen > 0 else 0.0
        ts_resolved = int(time.time())

        rec = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "window_resolution",
            "ts_resolved_s": ts_resolved,
            "condition_id": cid,
            "asset": info["asset"],
            "outcome_dir": info["outcome_dir"],
            "window_end_ts": wend,
            "window_size_s": info["window_size_s"],
            "binance_open_5m":  round(kopen,  2),
            "binance_close_5m": round(kclose, 2),
            "binance_high_5m":  round(khigh,  2),
            "binance_low_5m":   round(klow,   2),
            "realized_move_pct": round(realized_pct, 4),
            "moved_up": moved_up,
            "resolved_yes": (moved_up if info["outcome_dir"] == "up" else not moved_up),
            "resolution_method": f"kline:{kopen:.2f}->{kclose:.2f}",
            "resolution_delay_s": ts_resolved - wend,
            "resolution_source": "binance_kline",
        }
        self.pipe.emit(rec)
        self._resolved.add(key)
