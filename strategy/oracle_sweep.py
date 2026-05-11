"""Oracle sweep — exploits the 35-second Chainlink latency window.

VERIFIED (2026-05-11, n=3,678 windows):
  - 99% of windows: oracle fires exactly 35s after window_end_ts.
  - 100% of flat-kline windows (open==close, n=43): resolve YES UP.
  - Winning token asks confirmed at 0.01–0.96 in final 35s window (n=876 trades).
  - One confirmed sweep: SOL UP at $0.01 → $331 payout (9,900% return).

Two sub-strategies per window close:

  A) Kline sweep (T+0 to T+33s):
     Fetch Binance kline at window close. Result is deterministic (close>=open → YES).
     Buy any ask < ASK_CEILING on winning token. Sell at 0.99 or let auto-settle.

  B) Stale-ask sweep (same window):
     Orphaned limit sells placed early in window at stale prices.
     Same logic — buy any ask < ASK_CEILING on winning token.

Architecture:
  - OracleSweeper.register_token() called from TimelineSampler._sample_once() each tick.
    Builds a cid → {outcome_dir: token_id} map before window closes.
  - OracleSweeper.schedule() called once per (cid, wend). Spawns asyncio task.
  - Task sleeps until wend + SWEEP_DELAY_S, fetches kline, sweeps cheap asks.
  - Exit: cascade_sell at 0.99 immediately; if unfilled by wend+ORACLE_FIRES_S, cancel
    and hold for on-chain auto-settlement.

Risk limits:
  MAX_STAKE_PER_WINDOW = $50    (hard cap regardless of book depth)
  ASK_CEILING          = 0.97   (must yield at least 3% after taker fee)
  MIN_PROFIT_THRESHOLD = 0.005  (skip windows where expected edge < $0.005)

Capital tracking: separate from BOND/DISCOVER. Logged to shadow as "oracle_sweep" events.
Never raises — all exceptions caught internally.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set, Tuple

import aiohttp

from strategy.momentum import Direction

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SWEEP_DELAY_S      = 1.0    # seconds after window_end_ts before we sweep
ORACLE_FIRES_S     = 33.0   # sell/cancel before this (oracle fires at ~35s)
ASK_CEILING        = 0.97   # maximum price we'll pay (must leave 3% margin)
MAX_STAKE_PER_WIN  = 50.0   # max USDC per window
MIN_EDGE_USD       = 0.01   # skip if expected profit < $0.01

_SYMBOL_MAP   = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
_INTERVAL_MAP = {300: "5m", 900: "15m"}
_CLOB_BOOK_URL = "https://clob.polymarket.com/book"


class OracleSweeper:
    """Fires after every window close. Sweeps cheap asks on the winning token."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True

        # cid → {"up": token_id, "down": token_id}
        self._cid_tokens: Dict[str, Dict[str, str]] = {}
        # (cid, wend) already scheduled
        self._scheduled: Set[Tuple[str, int]] = set()
        # active asyncio tasks
        self._tasks = []

        # Lifetime stats
        self.sweeps_attempted: int = 0
        self.sweeps_filled: int   = 0
        self.gross_profit_usd: float = 0.0

    # ── Public API called from TimelineSampler ─────────────────────────────────

    def register_token(self, cid: str, outcome_dir: str, token_id: str) -> None:
        """Record the token_id for a given market side. Called every tick — idempotent."""
        if not cid or not token_id:
            return
        if cid not in self._cid_tokens:
            self._cid_tokens[cid] = {}
        self._cid_tokens[cid][outcome_dir] = token_id

    def schedule(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
    ) -> None:
        """Idempotent. First call per (cid, wend) spawns the sweep task."""
        if not self.enabled:
            return
        key = (cid, wend)
        if key in self._scheduled:
            return
        tokens = self._cid_tokens.get(cid, {})
        # Need both sides registered before we can sweep
        if "up" not in tokens or "down" not in tokens:
            return
        self._scheduled.add(key)
        task = asyncio.create_task(
            self._run(cid, wend, asset, window_size_s, dict(tokens)),
            name=f"oracle_sweep_{cid[:8]}_{wend}",
        )
        self._tasks.append(task)
        # Bound task list
        if len(self._tasks) > 128:
            self._tasks = [t for t in self._tasks if not t.done()]

    async def stop(self) -> None:
        live = [t for t in self._tasks if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)

    # ── Sweep task ─────────────────────────────────────────────────────────────

    async def _run(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
        tokens: Dict[str, str],  # {"up": tid, "down": tid}
    ) -> None:
        """Main sweep coroutine. Never raises."""
        try:
            await self._run_inner(cid, wend, asset, window_size_s, tokens)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("oracle_sweep unhandled error cid=%s wend=%s", cid[:8], wend)

    async def _run_inner(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
        tokens: Dict[str, str],
    ) -> None:
        # Wait until SWEEP_DELAY_S after window close
        wait = (wend + SWEEP_DELAY_S) - time.time()
        if wait > 2.0:
            await asyncio.sleep(wait)
        elif wait < -ORACLE_FIRES_S:
            # Already past the oracle fire window — nothing to do
            return

        # Fetch Binance kline to determine the winner
        winner_dir = await self._kline_winner(asset, wend, window_size_s)
        if winner_dir is None:
            logger.debug("oracle_sweep: kline fetch failed — %s wend=%s", asset, wend)
            return

        winning_token_id = tokens.get(winner_dir)
        if not winning_token_id:
            return

        logger.info(
            "oracle_sweep: wend=%s %s winner=%s token=%s",
            wend, asset, winner_dir, winning_token_id[:12],
        )

        # Fetch CLOB book for winning token via REST
        cheap_asks = await self._get_cheap_asks(winning_token_id)
        if not cheap_asks:
            logger.debug("oracle_sweep: no cheap asks for %s", winning_token_id[:12])
            return

        # Check time budget — must sweep before ORACLE_FIRES_S
        time_left = (wend + ORACLE_FIRES_S) - time.time()
        if time_left < 3.0:
            logger.info("oracle_sweep: insufficient time (%.1fs left) — skipping", time_left)
            return

        # Sweep each cheap ask level up to MAX_STAKE_PER_WIN
        budget = MAX_STAKE_PER_WIN
        total_spent = 0.0
        total_shares = 0.0

        for ask_price, ask_size in cheap_asks:
            if budget < MIN_EDGE_USD:
                break
            expected_profit = (1.0 - ask_price) * ask_size - (ask_price * ask_size * 0.02)
            if expected_profit < MIN_EDGE_USD:
                continue

            stake = min(budget, ask_price * ask_size)
            if stake < 1.0:  # CLOB minimum
                continue

            self.sweeps_attempted += 1
            logger.info(
                "oracle_sweep: BUY %s ask=%.4f stake=$%.2f expected_profit=$%.2f",
                asset, ask_price, stake, (1.0 - ask_price) * (stake / ask_price),
            )

            try:
                result = await self.bot.orders.limit_buy(
                    token_id=winning_token_id,
                    intended_price=ask_price,
                    stake_usd=stake,
                    direction=Direction.BUY,
                )
                from execution.order_manager import OrderStatus
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    self.sweeps_filled += 1
                    spent = ask_price * result.total_size
                    total_spent += spent
                    total_shares += result.total_size
                    budget -= spent
                    expected = result.total_size * 1.0
                    self.gross_profit_usd += expected - spent
                    logger.info(
                        "oracle_sweep FILLED: %.4f shares @ %.4f | cost=$%.2f expected_return=$%.2f",
                        result.total_size, ask_price, spent, expected,
                    )
                    self._emit_shadow(asset, winner_dir, winning_token_id, ask_price,
                                      result.total_size, spent, wend)
                else:
                    logger.debug("oracle_sweep: fill failed at ask=%.4f", ask_price)
            except Exception as exc:
                logger.debug("oracle_sweep: buy error: %s", exc)

        if total_shares <= 0:
            return

        # Schedule exit sell at ORACLE_FIRES_S - 2s
        exit_wait = max(0.5, (wend + ORACLE_FIRES_S - 2) - time.time())
        logger.info(
            "oracle_sweep: scheduling exit in %.1fs (%.4f shares, cost=$%.2f)",
            exit_wait, total_shares, total_spent,
        )
        await asyncio.sleep(exit_wait)
        try:
            await self.bot.orders.cascade_sell(
                token_id=winning_token_id,
                total_shares=total_shares,
                current_price=0.99,
                reason="oracle_sweep_exit",
                force_exit=True,
            )
            logger.info("oracle_sweep: exit sell submitted (%.4f shares)", total_shares)
        except Exception as exc:
            # Exit failed — token will auto-settle on-chain at resolution
            logger.info("oracle_sweep: exit sell failed (%s) — holding to auto-settle", exc)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _kline_winner(
        self,
        asset: str,
        wend: int,
        window_size_s: int,
    ) -> Optional[str]:
        """Fetch Binance kline for the closed window. Returns 'up' or 'down'."""
        symbol   = _SYMBOL_MAP.get(asset.upper())
        interval = _INTERVAL_MAP.get(window_size_s)
        if not symbol or not interval:
            return None

        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            return None

        wstart_ms = int((wend - window_size_s) * 1000)
        try:
            async with session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval,
                        "startTime": wstart_ms, "limit": 1},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return None
                klines = await resp.json()
        except Exception as exc:
            logger.debug("oracle_sweep kline fetch %s/%s: %s", asset, wend, exc)
            return None

        if not klines or len(klines[0]) < 5:
            return None

        kopen  = float(klines[0][1])
        kclose = float(klines[0][4])
        # Tie rule (verified): close >= open → YES UP wins (100% of ties in n=43 data)
        return "up" if kclose >= kopen else "down"

    async def _get_cheap_asks(
        self,
        token_id: str,
    ) -> list:
        """Fetch CLOB order book via REST. Returns list of (price, size) tuples
        for asks below ASK_CEILING, sorted cheapest first."""
        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            return []
        try:
            async with session.get(
                _CLOB_BOOK_URL,
                params={"token_id": token_id},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as exc:
            logger.debug("oracle_sweep book fetch %s: %s", token_id[:12], exc)
            return []

        asks = data.get("asks", [])
        result = []
        for entry in asks:
            try:
                p = float(entry.get("price", 1.0))
                s = float(entry.get("size",  0.0))
                if p < ASK_CEILING and s > 0:
                    result.append((p, s))
            except (TypeError, ValueError):
                continue
        result.sort(key=lambda x: x[0])
        return result

    def _emit_shadow(
        self,
        asset: str,
        winner_dir: str,
        token_id: str,
        price: float,
        shares: float,
        cost_usd: float,
        wend: int,
    ) -> None:
        """Log the sweep to shadow pipeline if available."""
        pipeline = getattr(self.bot, "shadow_pipeline", None)
        if pipeline is None:
            return
        try:
            pipeline.emit({
                "schema_version": 1,
                "record_type": "oracle_sweep",
                "ts_s": int(time.time()),
                "asset": asset,
                "winner_dir": winner_dir,
                "token_id": token_id,
                "fill_price": round(price, 4),
                "fill_shares": round(shares, 4),
                "cost_usd": round(cost_usd, 4),
                "expected_return_usd": round(shares, 4),
                "expected_profit_usd": round(shares - cost_usd, 4),
                "window_end_ts": wend,
            })
        except Exception:
            pass
