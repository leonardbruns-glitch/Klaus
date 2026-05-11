"""MM silence gap sweeper — B2 exploit.

Market-makers on Polymarket handle YES and NO tokens for a single market as a pair.
When the MM process goes offline, BOTH tokens stop receiving quote updates simultaneously.
The last resting GTC ask remains live on the CLOB.

If Binance moves significantly during the gap, that stale ask is mispriced.

Verified data (2026-05-11):
  - 114 gaps > 30s today across all tracked tokens
  - Max gap: 245s (4+ minutes of no quotes)
  - Gaps always come in pairs (YES+NO go silent together)
  - 32% of all replay ticks have ask_stale > 5s; 16% > 30s

Strategy:
  1. Track last ob_delta timestamp per token. Gap = no update for > GAP_THRESHOLD_S.
  2. Record Binance spot price at gap start.
  3. Every 5s: check active tokens for gaps.
  4. If gap > threshold AND Binance moved > MIN_MOVE_PCT in the token's favorable direction:
     - REST-fetch CLOB book for the token
     - If any ask < SWEEP_CEILING: buy it (stale ask, price has moved away)
     - Schedule exit at T-15s
  5. One position per token per window (dedup).

The directional logic:
  - YES_UP token (outcome_dir="up"): favorable if Binance moved UP during gap
  - YES_DOWN token (outcome_dir="down"): favorable if Binance moved DOWN during gap

Risk:
  - Binance can reverse before window close — gap buy loses
  - Stale ask may already reflect fair value (MM left at correct price)
  - SWEEP_CEILING kept at 0.85 to limit max loss per entry

Capital: max $10/entry, max 2 concurrent gap positions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set

import aiohttp

from strategy.momentum import Direction

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
GAP_THRESHOLD_S   = 30.0   # seconds without ob_delta = MM offline
MIN_MOVE_PCT      = 0.30   # Binance must have moved ≥ 0.30% during gap
SWEEP_CEILING     = 0.85   # max ask we'll pay (Binance confirmation required)
MAX_STAKE         = 10.0   # max USDC per gap entry
MIN_REM_S         = 60.0   # skip if < 60s remaining in window
MAX_CONCURRENT    = 2      # max gap positions at once
SCAN_INTERVAL_S   = 5.0    # how often to scan for gaps
_CLOB_BOOK_URL    = "https://clob.polymarket.com/book"


class GapSweeper:
    """Detects MM silence gaps and sweeps stale asks when Binance has moved."""

    def __init__(self, bot: Any) -> None:
        self.bot     = bot
        self.enabled = True

        # token_id → timestamp of last ob_delta event
        self._last_ob_ts: Dict[str, float] = {}
        # token_id → Binance spot price at the moment of last ob_delta
        self._last_ob_binance: Dict[str, float] = {}
        # token_ids where we already entered a gap position this window
        self._gap_traded: Set[str] = set()

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        # Lifetime stats
        self.sweeps_attempted: int = 0
        self.sweeps_filled:    int = 0
        self.gross_profit_usd: float = 0.0

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="gap_sweeper")
            logger.info("GapSweeper started — GAP=%.0fs MOVE=%.2f%%", GAP_THRESHOLD_S, MIN_MOVE_PCT)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    # ── Hook called from feeds.py per ob_delta event ──────────────────────────

    def on_ob_event(self, token_id: str, asset: str) -> None:
        """Record that we just received an OB event for this token."""
        now = time.time()
        self._last_ob_ts[token_id] = now
        spot = self.bot.feed._spot_price.get(asset.upper(), 0.0)
        if spot > 0:
            self._last_ob_binance[token_id] = spot

    # ── Main scan loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                await self._scan_once()
            except Exception:
                logger.exception("gap_sweeper scan error")
            elapsed = time.monotonic() - t0
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=max(0.1, SCAN_INTERVAL_S - elapsed),
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _scan_once(self) -> None:
        if not self.enabled:
            return

        now = time.time()
        feed = self.bot.feed

        # Count current gap positions
        gap_open = sum(
            1 for pid, pos in self.bot.risk.open_positions.items()
            if getattr(pos, "bond_entry_class", "") == "GAP_SWEEP"
        )
        if gap_open >= MAX_CONCURRENT:
            return

        for token_id, token in list(feed.tokens.items()):
            if getattr(token, "market_type", None) != "updown":
                continue
            wend = getattr(token, "window_end_ts", 0)
            if wend <= 0:
                continue
            rem = wend - now
            if rem < MIN_REM_S:
                continue
            # Already entered a gap position for this token this window
            if token_id in self._gap_traded:
                continue
            # Already in a position
            if token_id in self.bot.risk.open_positions:
                continue

            last_ob = self._last_ob_ts.get(token_id, 0)
            if last_ob <= 0:
                continue  # never seen an ob_delta — can't establish gap baseline
            gap_s = now - last_ob
            if gap_s < GAP_THRESHOLD_S:
                continue  # no gap yet

            # Binance at gap start vs now
            gap_binance = self._last_ob_binance.get(token_id, 0)
            if gap_binance <= 0:
                continue
            asset = token.asset.upper()
            current_binance = feed._spot_price.get(asset, 0.0)
            if current_binance <= 0:
                continue

            move_pct = (current_binance - gap_binance) / gap_binance * 100.0
            outcome_dir = getattr(token, "outcome_direction", "")

            # Is the move favorable for this token?
            if outcome_dir == "up":
                favorable = move_pct >= MIN_MOVE_PCT
            elif outcome_dir == "down":
                favorable = move_pct <= -MIN_MOVE_PCT
            else:
                continue

            if not favorable:
                continue

            logger.info(
                "gap_sweeper: GAP DETECTED %s/%s gap=%.0fs binance_move=%+.3f%% rem=%.0fs",
                asset, outcome_dir, gap_s, move_pct, rem,
            )

            await self._try_sweep(token_id, token, gap_s, move_pct, rem, wend)

            # Only one gap sweep attempt per scan cycle (avoid flooding)
            break

    async def _try_sweep(
        self,
        token_id: str,
        token,
        gap_s: float,
        move_pct: float,
        rem: float,
        wend: int,
    ) -> None:
        """REST-fetch CLOB book and buy cheap asks if the gap is real."""
        cheap_asks = await self._get_cheap_asks(token_id)
        if not cheap_asks:
            logger.debug("gap_sweeper: no cheap asks for %s", token_id[:12])
            return

        asset       = token.asset
        outcome_dir = getattr(token, "outcome_direction", "")
        budget      = MAX_STAKE

        for ask_price, ask_size in cheap_asks:
            if budget < 1.0:
                break
            stake = min(budget, ask_price * ask_size)
            if stake < 1.0:
                continue

            self.sweeps_attempted += 1
            logger.info(
                "gap_sweeper: BUY %s/%s ask=%.4f stake=$%.2f gap=%.0fs move=%+.3f%%",
                asset, outcome_dir, ask_price, stake, gap_s, move_pct,
            )

            try:
                result = await self.bot.orders.limit_buy(
                    token_id=token_id,
                    intended_price=ask_price,
                    stake_usd=stake,
                    direction=Direction.BUY,
                )
                from execution.order_manager import OrderStatus
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    self.sweeps_filled += 1
                    spent = ask_price * result.total_size
                    budget -= spent
                    self._gap_traded.add(token_id)
                    logger.info(
                        "gap_sweeper FILLED: %.4f shares @ %.4f | $%.2f spent | rem=%.0fs",
                        result.total_size, ask_price, spent, rem,
                    )
                    self._emit_shadow(asset, outcome_dir, token_id, ask_price,
                                      result.total_size, spent, gap_s, move_pct, wend)
                    # Schedule exit at T-15s
                    exit_delay = max(1.0, rem - 15.0)
                    asyncio.create_task(
                        self._exit_at(token_id, result.total_size, exit_delay, asset),
                        name=f"gap_exit_{token_id[:8]}",
                    )
            except Exception as exc:
                logger.debug("gap_sweeper buy error: %s", exc)

        # GC stale dedup entries (window ended)
        now = time.time()
        expired = {tid for tid in self._gap_traded
                   if self.bot.feed.tokens.get(tid) is None}
        self._gap_traded -= expired

    async def _exit_at(
        self,
        token_id: str,
        shares: float,
        delay_s: float,
        asset: str,
    ) -> None:
        """Sell gap position at T-15s."""
        try:
            await asyncio.sleep(delay_s)
            ob = self.bot.feed.get_order_book(token_id)
            bid = ob.bids[0][0] if (ob and ob.bids) else 0.0
            if bid <= 0.01:
                logger.info("gap_sweeper exit: no bid for %s — leaving to settle", token_id[:12])
                return
            logger.info("gap_sweeper exit: cascade_sell %.4f shares @ %.4f (%s)", shares, bid, asset)
            await self.bot.orders.cascade_sell(
                token_id=token_id,
                total_shares=shares,
                current_price=bid,
                reason="gap_sweep_exit",
                force_exit=True,
            )
        except Exception as exc:
            logger.debug("gap_sweeper exit error: %s", exc)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_cheap_asks(self, token_id: str) -> list:
        """REST-fetch CLOB book. Returns [(price, size)] for asks ≤ SWEEP_CEILING."""
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
            logger.debug("gap_sweeper book fetch %s: %s", token_id[:12], exc)
            return []

        result = []
        for entry in data.get("asks", []):
            try:
                p = float(entry.get("price", 1.0))
                s = float(entry.get("size",  0.0))
                if p <= SWEEP_CEILING and s > 0:
                    result.append((p, s))
            except (TypeError, ValueError):
                continue
        result.sort(key=lambda x: x[0])
        return result

    def _emit_shadow(
        self,
        asset: str,
        outcome_dir: str,
        token_id: str,
        price: float,
        shares: float,
        cost_usd: float,
        gap_s: float,
        move_pct: float,
        wend: int,
    ) -> None:
        pipeline = getattr(self.bot, "shadow_pipeline", None)
        if pipeline is None:
            return
        try:
            pipeline.emit({
                "schema_version": 1,
                "record_type": "gap_sweep",
                "ts_s": int(time.time()),
                "asset": asset,
                "outcome_dir": outcome_dir,
                "token_id": token_id,
                "fill_price": round(price, 4),
                "fill_shares": round(shares, 4),
                "cost_usd": round(cost_usd, 4),
                "gap_s": round(gap_s, 1),
                "binance_move_pct": round(move_pct, 4),
                "window_end_ts": wend,
            })
        except Exception:
            pass
