"""Window resolution writer — per-window scheduled task model.

Mirrors the live bot's main.py:5610 _capture_resolution pattern:
  - One asyncio task per observed window (idempotent via _scheduled set)
  - Task sleeps until window_end_ts + 35s, fetches Binance 5m kline,
    emits a window_resolution record.

Driven by TimelineSampler.schedule() — does NOT poll feed.tokens, because
markets evict from the live feed shortly after they resolve, before the
35s wait completes. The previous polling design missed all resolutions.

Resolution source = Binance kline (canonical per
feedback_kline_resolution_canonical: >99% Chainlink agreement).
"""
import asyncio
import logging
import time
from typing import Any, List, Optional, Set, Tuple

import aiohttp

from .pipeline import ShadowPipeline

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_SYMBOL_MAP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
# Binance kline interval matched to Polymarket window size (300s = 5m, 900s = 15m).
_INTERVAL_FOR_SIZE = {300: "5m", 900: "15m"}


class ResolutionWriter:
    def __init__(self, bot: Any, pipeline: ShadowPipeline) -> None:
        self.bot = bot
        self.pipe = pipeline
        self._scheduled: Set[Tuple[str, int]] = set()
        self._tasks: List[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def start(self) -> None:
        logger.info("ResolutionWriter started — scheduling-mode (per-window task)")

    async def stop(self) -> None:
        self._stop.set()
        live = [t for t in self._tasks if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)

    def schedule(
        self,
        cid: str,
        wend: int,
        asset: str,
        outcome_dir: str,
        window_size_s: int,
    ) -> None:
        """Idempotent. First call per (cid, wend) spawns the resolution task.
        Safe to call from any sync context."""
        if not cid or wend <= 0:
            return
        if window_size_s not in _INTERVAL_FOR_SIZE:
            return  # unsupported window size — skip silently
        key = (cid, wend)
        if key in self._scheduled:
            return
        self._scheduled.add(key)
        task = asyncio.create_task(
            self._resolve_at(cid, wend, asset, outcome_dir, window_size_s),
            name=f"shadow_resolve_{cid[:8]}_{wend}",
        )
        self._tasks.append(task)
        # GC completed tasks every ~256 schedules to bound the list.
        if len(self._tasks) > 256:
            self._tasks = [t for t in self._tasks if not t.done()]

    async def _resolve_at(
        self,
        cid: str,
        wend: int,
        asset: str,
        outcome_dir: str,
        window_size_s: int,
    ) -> None:
        wait = (wend + 35) - time.time()
        if wait > 0:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
                return  # stop signalled before resolution time
            except asyncio.TimeoutError:
                pass
        if self._stop.is_set():
            return
        try:
            await self._fetch_and_emit(cid, wend, asset, outcome_dir, window_size_s)
        except Exception:
            logger.exception("shadow resolution failed cid=%s wend=%s", cid[:12], wend)

    async def _fetch_and_emit(
        self,
        cid: str,
        wend: int,
        asset: str,
        outcome_dir: str,
        window_size_s: int,
    ) -> None:
        asset_up = asset.upper()
        symbol = _SYMBOL_MAP.get(asset_up)
        if symbol is None:
            return
        interval = _INTERVAL_FOR_SIZE[window_size_s]
        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            logger.debug("shadow resolve: no feed session; skipping cid=%s", cid[:12])
            return
        wstart_ms = int((wend - window_size_s) * 1000)
        try:
            async with session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval,
                        "startTime": wstart_ms, "limit": 1},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return
                klines = await resp.json()
        except Exception as e:
            logger.debug("shadow kline fetch %s/%s: %s", asset_up, wend, e)
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
            "asset": asset,
            "outcome_dir": outcome_dir,
            "window_end_ts": wend,
            "window_size_s": window_size_s,
            "binance_open_5m":  round(kopen,  2),
            "binance_close_5m": round(kclose, 2),
            "binance_high_5m":  round(khigh,  2),
            "binance_low_5m":   round(klow,   2),
            "realized_move_pct": round(realized_pct, 4),
            "moved_up": moved_up,
            "resolved_yes": (moved_up if outcome_dir == "up" else not moved_up),
            "resolution_method": f"kline:{kopen:.2f}->{kclose:.2f}",
            "resolution_delay_s": ts_resolved - wend,
            "resolution_source": "binance_kline",
        }
        self.pipe.emit(rec)
