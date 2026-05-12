"""
Late-window directional arb (LDA).

Signal: Binance 5m-return direction (spot vs open_5m).
Gate  : predicted-winner token ask in [0.70, 0.994] + bid > 0.50.
Timing: one entry per window, fired the first eligible tick in T-8 to T-90s.
Exit  : PROFIT_TARGET fires at bid≥0.99; BOND_DEADLINE T-3s catches the rest.
        Losing tokens resolve NO and are booked by BOND_RESOLVED_NO.

Accuracy baseline (n=85 windows, 2 days): 96.6% direction accuracy, PF≈6.3.
Stake: $5 per window during validation (raise after n≥100, WR>55%).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Set, Tuple

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)

ASK_FLOOR    = 0.70
ASK_CEIL     = 0.93   # shadow n=1812: [0.93,0.96) WR=91.8% EV=-$0.17 (37.7% of wrongs); above 0.96 near-zero EV
BID_MIN      = 0.50    # safeguard: both tokens on wrong side if bid < 0.50
REM_MIN_S    = 8.0     # don't enter if <8s left (can't fill reliably)
REM_MAX_S    = 90.0    # don't enter >90s before close (signal less reliable)
BNC_MOVE_MIN = 0.07    # |5m return %| floor; all reversals were at <0.056%; 0.07→99.8% acc +66% trades
STAKE_USD    = 5.00
BLOCKED_HOURS_UTC = {1}  # H01 WR=88.6% n=79 wrong=9 (shadow); only flagged hour


class LateDirectionArb:
    """Per-tick late-window directional arb."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True

        self._fired: Set[Tuple[str, int]] = set()  # (cid, wend) already entered
        self._tasks = []

        self.entries_attempted: int = 0
        self.entries_filled: int = 0

    # ── Public: called synchronously from timeline sampler ────────────────────

    def schedule_if_ready(self, rec: dict) -> None:
        """Check current tick; spawn async entry task if conditions met."""
        if not self.enabled:
            return

        remaining = rec.get("seconds_to_resolution", 0.0)
        if not (REM_MIN_S <= remaining <= REM_MAX_S):
            return

        cid  = rec.get("condition_id", "")
        wend = rec.get("window_end_ts", 0)
        if not cid or not wend:
            return

        key = (cid, wend)
        if key in self._fired:
            return

        hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
        if hour_utc in BLOCKED_HOURS_UTC:
            return

        ask = rec.get("best_ask", 0.0)
        bid = rec.get("best_bid", 0.0)
        if not (ASK_FLOOR <= ask <= ASK_CEIL) or bid < BID_MIN:
            return

        feed = self.bot.feed
        asset_up = rec.get("asset", "").upper()
        spot    = feed._spot_price.get(asset_up, 0.0)
        open_5m = feed._spot_open_5m.get(asset_up, 0.0)
        if spot <= 0 or open_5m <= 0:
            return

        bnc_move_pct = (spot - open_5m) / open_5m * 100.0
        if abs(bnc_move_pct) < BNC_MOVE_MIN:
            return  # move too small; all known reversals were at <0.056%

        # Per-asset / per-window-size bnc gates (shadow data, n=1631, May 8-12):
        #   ETH 15m: all bnc zones NEG EV or LOW WR → block entirely
        #   SOL 15m: 0.07-0.10% NEG EV (dominant bucket), rest too small → block entirely
        #   BTC 15m: 0.07-0.10% LOW WR (87.5%) → require bnc >= 0.10%
        #   SOL 5m:  0.10-0.15% and 0.15%+ NEG EV (ask too high by then) → cap at 0.10%
        wsz   = rec.get("window_size_s", 300)
        asset = rec.get("asset", "").upper()
        bnc_abs = abs(bnc_move_pct)
        if wsz == 900:  # 15m window
            if asset in ("ETH", "SOL"):
                return
            if asset == "BTC" and bnc_abs < 0.10:
                return
        elif wsz == 300 and asset == "SOL" and bnc_abs >= 0.10:
            return

        bnc_dir = "up" if bnc_move_pct > 0 else "down"
        if bnc_dir != rec.get("outcome_dir"):
            return  # this token is NOT on the predicted winning side

        # Mark fired BEFORE creating task to prevent a second tick from double-firing.
        self._fired.add(key)
        self.entries_attempted += 1

        task = asyncio.create_task(
            self._fire(dict(rec), bnc_dir, spot, open_5m, bnc_move_pct),
            name=f"lda_{cid[:8]}_{wend}",
        )
        self._tasks.append(task)
        if len(self._tasks) > 128:
            self._tasks = [t for t in self._tasks if not t.done()]

    async def stop(self) -> None:
        live = [t for t in self._tasks if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)

    # ── Async entry execution ─────────────────────────────────────────────────

    async def _fire(
        self,
        rec: dict,
        bnc_dir: str,
        spot: float,
        open_5m: float,
        bnc_move_pct: float,
    ) -> None:
        """Execute the buy and register the position. Never raises."""
        try:
            await self._fire_inner(rec, bnc_dir, spot, bnc_move_pct)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[LDA] unhandled error %s/%s", rec.get("asset"), rec.get("window_end_ts"))

    async def _fire_inner(
        self,
        rec: dict,
        bnc_dir: str,
        spot: float,
        bnc_move_pct: float,
    ) -> None:
        from execution.order_manager import OrderStatus

        token_id = rec["token_id"]
        asset    = rec["asset"]
        ask      = rec["best_ask"]
        rem      = rec["seconds_to_resolution"]
        cid      = rec["condition_id"]
        wend     = rec["window_end_ts"]

        logger.info(
            "[LDA] ENTER %s/%s ask=%.4f rem=%.1fs bnc_move=%+.4f%%",
            asset, bnc_dir, ask, rem, bnc_move_pct,
        )

        fill = await self.bot.orders.limit_buy(
            token_id=token_id,
            intended_price=ask,
            stake_usd=STAKE_USD,
            direction=Direction.BUY_YES,
        )

        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            logger.info("[LDA] fill failed %s: %s", asset, getattr(fill, "error", "?"))
            key = (cid, wend)
            self._fired.discard(key)  # allow retry on next tick
            self.entries_attempted -= 1
            return

        self.entries_filled += 1
        actual_stake = fill.avg_fill_price * fill.total_size

        logger.info(
            "[LDA] FILLED %s/%s %.4f shares @ %.4f | cost=$%.2f expect=$%.2f (+$%.2f)",
            asset, bnc_dir, fill.total_size, fill.avg_fill_price,
            actual_stake, fill.total_size, fill.total_size - actual_stake,
        )

        tpsl = TPSLLevels(
            take_profit=0.0, stop_loss=0.0,
            tp_pct=0.0, sl_pct=0.0, risk_reward=0.0,
        )

        class _Sig:
            signal_source = "LDA"
            entry_price = fill.avg_fill_price
            direction = Direction.BUY_YES

        try:
            self.bot.risk.open_position(
                token_id=token_id,
                asset=asset,
                direction=Direction.BUY_YES,
                stake=actual_stake,
                entry_price=fill.avg_fill_price,
                tpsl=tpsl,
                condition_id=cid,
                window_end_ts=wend,
                window_seconds=rec.get("window_size_s", 300),
                quality_score=0,
                binance_price_at_entry=spot,
                is_bond=True,
                bond_outcome_direction=bnc_dir,
                bond_entry_class="LDA",
            )
            import time as _time
            self.bot._open_meta[token_id] = {
                "signal_source": "LDA",
                "ts_open": _time.time(),
                "spot_at_entry": spot,
                "pre_entry_momentum_pct": bnc_move_pct,
                "window_size_s": rec.get("window_size_s", 300),
                "capital_before": self.bot.risk.bankroll.capital,
            }
        except Exception:
            logger.exception("[LDA] risk.open_position failed %s", asset)
