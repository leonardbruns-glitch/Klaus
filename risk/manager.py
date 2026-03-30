"""
Klaus — Risk Manager
Handles: bankroll tracking, position sizing (heat-check), daily loss halts,
         max open positions, per-trade risk validation, and exit decisions.

Exit logic ported from baseline bot v4:
  - 2-stage profit taking: 95 % at +25 %, remainder at +45 % or cost+5 % floor
  - Time-aware dynamic SL: 35 % first 2.5 min, 10 % last 2 min
  - Condition dedup per window
  - Post-close cooldown
"""
from __future__ import annotations

import time
import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set
import logging

from config import CONFIG
from strategy.momentum import Direction, SignalBreakdown, TPSLLevels

logger = logging.getLogger("risk")


# ---------------------------------------------------------------------------
# Exit stage enum
# ---------------------------------------------------------------------------

class ExitStage(Enum):
    NONE = auto()        # no sell yet
    STAGE_1_DONE = auto()  # 95 % sold at +25 %


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PositionMeta:
    token_id: str
    asset: str
    direction: Direction
    stake: float
    entry_price: float
    tp: float                          # ATR-based TP (still used as fallback)
    sl: float                          # ATR-based SL (overridden by time-aware SL)
    open_ts: float = field(default_factory=time.time)
    window_end_ts: float = 0.0         # unix ts when the 5-min window closes
    shares: float = 0.0
    remaining_shares: float = 0.0     # updated after partial sells
    highest_price: float = 0.0        # peak since open (for trailing stop)
    exit_stage: ExitStage = ExitStage.NONE
    profit_trigger_ts: float = 0.0    # timestamp when +25 % first seen
    hard_exit_triggered: bool = False
    condition_id: str = ""            # Polymarket condition ID for dedup

    def __post_init__(self) -> None:
        if self.remaining_shares == 0.0:
            self.remaining_shares = self.shares
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price


@dataclass
class RiskDecision:
    approved: bool
    stake: float
    reason: str
    is_scaled: bool = False


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str
    partial: bool = False        # True = stage-1 sell (95 %)
    urgency: str = "cascade"     # "cascade" or "immediate"


# ---------------------------------------------------------------------------
# Bankroll & heat-check tracker
# ---------------------------------------------------------------------------

class BankrollTracker:
    def __init__(self) -> None:
        self.cfg = CONFIG.bankroll
        self.capital = self.cfg.total
        self.daily_start_capital = self.cfg.total
        self.consecutive_wins = 0
        self.total_trades = 0
        self.total_pnl = 0.0
        self.session_start_ts = time.time()

    def record_trade_result(self, pnl: float) -> None:
        self.capital += pnl
        self.total_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self.consecutive_wins += 1
        else:
            self.consecutive_wins = 0

    @property
    def is_heat_check_active(self) -> bool:
        return self.consecutive_wins >= self.cfg.heat_trigger_wins

    @property
    def current_stake(self) -> float:
        return self.cfg.scaled_stake if self.is_heat_check_active else self.cfg.base_stake

    @property
    def daily_loss(self) -> float:
        return self.daily_start_capital - self.capital

    @property
    def is_halted(self) -> bool:
        return self.daily_loss >= self.cfg.max_daily_loss

    def reset_daily(self) -> None:
        self.daily_start_capital = self.capital

    def summary(self) -> dict:
        return {
            "capital": round(self.capital, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_trades": self.total_trades,
            "consecutive_wins": self.consecutive_wins,
            "heat_check_active": self.is_heat_check_active,
            "current_stake": self.current_stake,
            "daily_loss": round(self.daily_loss, 2),
            "halted": self.is_halted,
        }


# ---------------------------------------------------------------------------
# Main risk manager
# ---------------------------------------------------------------------------

class RiskManager:
    """
    Gates entries and drives exit decisions for all open positions.
    """

    def __init__(self) -> None:
        self.cfg = CONFIG.bankroll
        self.fee_cfg = CONFIG.fees
        self.exec_cfg = CONFIG.execution
        self.edge_cfg = CONFIG.edge
        self.bankroll = BankrollTracker()
        self.open_positions: Dict[str, PositionMeta] = {}
        self._traded_conditions: Set[str] = set()   # dedup within window
        self._last_close_ts: float = 0.0

    # ── Window reset ─────────────────────────────────────────────────────────

    def reset_window(self) -> None:
        """Call at the start of each new 5-min window to clear dedup set."""
        self._traded_conditions.clear()
        logger.debug("Window reset: condition dedup cleared")

    # ── Trade approval ────────────────────────────────────────────────────────

    def evaluate(
        self,
        token_id: str,
        signal: SignalBreakdown,
        tpsl: TPSLLevels,
        condition_id: str = "",
        window_end_ts: float = 0.0,
        asset: str = "",
    ) -> RiskDecision:
        # Daily loss halt
        if self.bankroll.is_halted:
            return RiskDecision(False, 0, "Daily loss limit reached")

        # ── Trading hours gate (data-driven: 14:00 UTC is the only edge window) ──
        # Skip in dry_run mode so the simulation can be tested at any hour.
        allowed = self.edge_cfg.allowed_hours_utc
        if allowed and not CONFIG.dry_run:
            current_hour = datetime.datetime.utcnow().hour
            if current_hour not in allowed:
                return RiskDecision(
                    False, 0,
                    f"Outside trading hours (UTC {current_hour:02d}:xx — allowed: {allowed})",
                )

        # Post-close cooldown
        if time.time() - self._last_close_ts < self.cfg.post_close_cooldown:
            return RiskDecision(False, 0, "Post-close cooldown active")

        # Window expiry gate: don't enter if < no_trade_last_sec remaining
        if window_end_ts > 0:
            remaining = window_end_ts - time.time()
            if remaining < self.exec_cfg.no_trade_last_sec:
                return RiskDecision(False, 0, f"Window closing in {remaining:.0f}s")

        # Condition dedup
        if condition_id and condition_id in self._traded_conditions:
            return RiskDecision(False, 0, f"Already traded condition {condition_id[:8]}")

        # Min entry price floor (from old bot: reject < 3¢ tokens)
        if signal.entry_price < self.cfg.min_entry_price:
            return RiskDecision(False, 0, f"Entry price {signal.entry_price:.4f} below floor")

        # Max entry price cap (data: sweet spot at YES~0.245-0.260)
        # BUY_YES: YES token must be cheap (< 0.27)
        # BUY_NO:  NO token must be expensive (> 0.73 ≡ YES < 0.27)
        if signal.direction == Direction.BUY_YES:
            if signal.entry_price > self.edge_cfg.max_entry_price:
                return RiskDecision(
                    False, 0,
                    f"YES entry {signal.entry_price:.4f} above max {self.edge_cfg.max_entry_price}",
                )
        else:  # BUY_NO
            min_no = 1.0 - self.edge_cfg.max_entry_price  # e.g. 0.73
            if signal.entry_price < min_no:
                return RiskDecision(
                    False, 0,
                    f"NO entry {signal.entry_price:.4f} below min {min_no:.4f}",
                )

        # ── Per-asset confidence multiplier (data-driven) ──────────────────────
        # BTC: 6% WR → needs 40% higher score. ETH: 30% WR → 10% discount.
        if asset:
            multiplier = self.edge_cfg.asset_score_multiplier.get(asset.upper(), 1.0)
            from config import CONFIG as _C
            effective_min = _C.momentum.min_score * multiplier

            # Macro window discount: 13:30 UTC (CPI/NFP/claims) creates 30s-2min
            # mispricing lag — be more aggressive during this high-edge window.
            current_hour = datetime.datetime.utcnow().hour
            if current_hour in self.edge_cfg.macro_window_hours:
                effective_min = max(0.20, effective_min - self.edge_cfg.macro_score_discount)

            if signal.composite < effective_min:
                return RiskDecision(
                    False, 0,
                    f"{asset} score {signal.composite:.2f} < effective_min {effective_min:.2f} "
                    f"(multiplier={multiplier}x macro={'yes' if current_hour in self.edge_cfg.macro_window_hours else 'no'})",
                )

        # Already in this token
        if token_id in self.open_positions:
            return RiskDecision(False, 0, f"Already in {token_id[:8]}")

        # Max concurrent positions
        if len(self.open_positions) >= self.cfg.max_open_positions:
            return RiskDecision(False, 0, f"Max positions reached")

        stake = self.bankroll.current_stake
        max_pct = 0.10 if self.bankroll.is_heat_check_active else 0.05
        stake = min(stake, round(self.bankroll.capital * max_pct, 2))

        # RR gate
        if tpsl.risk_reward < 1.5:
            return RiskDecision(False, 0, f"RR {tpsl.risk_reward:.2f} < 1.5")

        # Fat-middle EV gate
        from strategy.momentum import FeeZone
        if signal.fee_zone == FeeZone.FAT_MIDDLE:
            odds = signal.entry_price
            fee_factor = min(odds, 1.0 - odds) / 0.5
            fee = self.fee_cfg.middle_fee_rate * fee_factor
            ev = (signal.confidence * tpsl.tp_pct / 100
                  - (1 - signal.confidence) * tpsl.sl_pct / 100
                  - fee)
            if ev <= 0:
                return RiskDecision(False, 0, f"Fat-middle EV={ev:.4f} ≤ 0")

        is_scaled = self.bankroll.is_heat_check_active
        return RiskDecision(
            approved=True,
            stake=stake,
            reason=f"Approved | ${stake} | heat={is_scaled}",
            is_scaled=is_scaled,
        )

    # ── Position lifecycle ────────────────────────────────────────────────────

    def open_position(
        self,
        token_id: str,
        asset: str,
        direction: Direction,
        stake: float,
        entry_price: float,
        tpsl: TPSLLevels,
        condition_id: str = "",
        window_end_ts: float = 0.0,
    ) -> PositionMeta:
        shares = stake / entry_price if entry_price > 0 else 0
        pos = PositionMeta(
            token_id=token_id,
            asset=asset,
            direction=direction,
            stake=stake,
            entry_price=entry_price,
            tp=tpsl.take_profit,
            sl=tpsl.stop_loss,
            shares=shares,
            remaining_shares=shares,
            highest_price=entry_price,
            condition_id=condition_id,
            window_end_ts=window_end_ts,
        )
        self.open_positions[token_id] = pos
        if condition_id:
            self._traded_conditions.add(condition_id)
        logger.info(
            "OPEN %s %s @ %.4f | stake=$%.2f | TP=%.4f SL=%.4f",
            direction.name, asset, entry_price, stake,
            tpsl.take_profit, tpsl.stop_loss,
        )
        return pos

    def record_stage1_sell(self, token_id: str, shares_sold: float) -> None:
        """Called after 95 % profit sell. Updates remaining shares."""
        pos = self.open_positions.get(token_id)
        if pos:
            pos.remaining_shares = max(0.0, pos.remaining_shares - shares_sold)
            pos.exit_stage = ExitStage.STAGE_1_DONE
            logger.info(
                "STAGE-1 SELL %s | sold=%.4f remaining=%.4f",
                token_id[:8], shares_sold, pos.remaining_shares,
            )

    def close_position(
        self,
        token_id: str,
        exit_price: float,
        reason: str,
        shares_override: Optional[float] = None,
    ) -> Optional[float]:
        """Close fully; returns net PnL. Uses remaining_shares for accuracy."""
        pos = self.open_positions.pop(token_id, None)
        if pos is None:
            return None

        shares = shares_override if shares_override is not None else pos.remaining_shares

        # Always: bought token at entry_price, selling at exit_price
        raw_pnl = (exit_price - pos.entry_price) * shares

        fee_rate = (
            CONFIG.fees.extreme_fee_rate
            if exit_price < CONFIG.fees.extreme_low or exit_price > CONFIG.fees.extreme_high
            else CONFIG.fees.middle_fee_rate
        )
        fee_cost = pos.stake * fee_rate
        net_pnl = raw_pnl - fee_cost

        self.bankroll.record_trade_result(net_pnl)
        self._last_close_ts = time.time()
        logger.info(
            "CLOSE %s %s @ %.4f | PnL=$%.2f (fee=$%.3f) | reason=%s",
            pos.direction.name, pos.asset, exit_price,
            net_pnl, fee_cost, reason,
        )
        return net_pnl

    # ── Exit decision engine ─────────────────────────────────────────────────
    # Ported from baseline bot v4 with fee awareness added.

    def check_exit_conditions(
        self,
        token_id: str,
        current_price: float,
    ) -> Optional[ExitDecision]:
        """
        Evaluates all exit rules in priority order.
        Returns ExitDecision or None if no exit warranted.

        Priority:
          1. Hard-exit timer (unconditional)
          2. Window expiry guard
          3. Stage-1 profit: +25 % with 2.5s confirmation → sell 95 %
          4. Stage-2 profit: +45 % (on remaining 5 %)
          5. Stage-2 floor: remaining at cost+5 %
          6. Trailing stop (after stage-1): 20 % below peak
          7. Time-aware dynamic SL (no stop in first 10s)
             - First 2.5 min: 35 % stop
             - Last 2 min:    10 % stop
        """
        pos = self.open_positions.get(token_id)
        if not pos:
            return None

        now = time.time()
        time_held = now - pos.open_ts
        remaining = pos.window_end_ts - now if pos.window_end_ts > 0 else 999

        # Update peak price — both BUY_YES and BUY_NO profit from rising price
        if current_price > pos.highest_price:
            pos.highest_price = current_price

        # move_pct > 0 means profit for both directions
        move_pct = (current_price - pos.entry_price) / pos.entry_price

        # ── 1. Hard-exit timer ────────────────────────────────────────────────
        if time_held >= self.exec_cfg.hard_exit_seconds and not pos.hard_exit_triggered:
            pos.hard_exit_triggered = True
            return ExitDecision(True, "HARD_EXIT", urgency="immediate")

        # ── 2. Window expiry guard ─────────────────────────────────────────────
        if 0 < remaining < self.exec_cfg.no_trade_last_sec:
            return ExitDecision(True, "EXIT_WINDOW_END", urgency="immediate")

        # ── 3. Stage-1 profit: +25 % with 2.5s confirmation ──────────────────
        if pos.exit_stage == ExitStage.NONE:
            if move_pct >= 0.25:
                if pos.profit_trigger_ts == 0.0:
                    pos.profit_trigger_ts = now
                    return None  # Start confirmation timer
                if now - pos.profit_trigger_ts >= 2.5:
                    return ExitDecision(True, "PROFIT_1", partial=True, urgency="cascade")
                return None  # Still confirming
            else:
                pos.profit_trigger_ts = 0.0  # Reset if price dropped

        # ── 4. Stage-2: +45 % on remaining shares ────────────────────────────
        if pos.exit_stage == ExitStage.STAGE_1_DONE:
            if move_pct >= 0.45:
                return ExitDecision(True, "PROFIT_2", urgency="cascade")

            # Floor: don't let stage-2 give back to cost+5 %
            if move_pct <= 0.05:
                return ExitDecision(True, "FLOOR_SELL", urgency="cascade")

            # Trailing stop after stage-1: 20 % below peak (same for both sides)
            trail_stop = pos.highest_price * 0.80
            if current_price <= trail_stop:
                return ExitDecision(True, "TRAIL_STOP", urgency="cascade")

            return None

        # ── 7. Dynamic SL (only before stage-1, after 10s grace) ─────────────
        if time_held >= 10:
            if remaining > 120:
                sl_pct = 0.35  # First 2.5 min: wide stop
            else:
                sl_pct = 0.10  # Last 2 min: tight stop

            # Stop loss fires when price falls below entry (same for BUY_YES and BUY_NO)
            if current_price <= pos.entry_price * (1 - sl_pct):
                return ExitDecision(True, "STOP_LOSS", urgency="immediate")

        return None

    # ── Convenience ──────────────────────────────────────────────────────────

    def positions_needing_hard_exit(self) -> List[PositionMeta]:
        """Returns positions that hit the 180s timer."""
        now = time.time()
        result = []
        for pos in self.open_positions.values():
            age = now - pos.open_ts
            if age >= self.exec_cfg.hard_exit_seconds and not pos.hard_exit_triggered:
                pos.hard_exit_triggered = True
                result.append(pos)
        return result
