"""
Klaus — Risk Manager
Handles: bankroll tracking, position sizing (heat-check), daily loss halts,
         max open positions, and per-trade risk validation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from config import CONFIG
from strategy.momentum import Direction, SignalBreakdown, TPSLLevels

logger = logging.getLogger("risk")


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
    tp: float
    sl: float
    open_ts: float = field(default_factory=time.time)
    shares: float = 0.0      # units purchased (stake / entry_price)
    hard_exit_triggered: bool = False


@dataclass
class RiskDecision:
    approved: bool
    stake: float
    reason: str
    is_scaled: bool = False   # True when heat-check scaling active


# ---------------------------------------------------------------------------
# Bankroll & heat-check tracker
# ---------------------------------------------------------------------------

class BankrollTracker:
    """Tracks running capital and consecutive-win streak for heat-check scaling."""

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
    Gates every proposed trade through capital and exposure checks.
    Tracks open positions and enforces the hard-exit timer.
    """

    def __init__(self) -> None:
        self.cfg = CONFIG.bankroll
        self.fee_cfg = CONFIG.fees
        self.exec_cfg = CONFIG.execution
        self.bankroll = BankrollTracker()
        self.open_positions: Dict[str, PositionMeta] = {}   # token_id → meta

    # ── Trade approval ────────────────────────────────────────────────────────

    def evaluate(
        self,
        token_id: str,
        signal: SignalBreakdown,
        tpsl: TPSLLevels,
    ) -> RiskDecision:
        """
        Returns RiskDecision indicating whether to proceed and at what stake.
        Never raises; always returns a decision.
        """
        # Daily loss halt
        if self.bankroll.is_halted:
            return RiskDecision(False, 0, "Daily loss limit reached — trading halted")

        # Already in this market
        if token_id in self.open_positions:
            return RiskDecision(False, 0, f"Already have open position in {token_id[:8]}")

        # Max concurrent positions
        if len(self.open_positions) >= self.cfg.max_open_positions:
            return RiskDecision(
                False, 0,
                f"Max open positions ({self.cfg.max_open_positions}) reached",
            )

        stake = self.bankroll.current_stake

        # Cap stake to the configured percentage of current capital
        # (protects against drawdown eroding safety margins)
        max_pct = 0.10 if self.bankroll.is_heat_check_active else 0.05
        stake = min(stake, round(self.bankroll.capital * max_pct, 2))

        # Risk/reward gate: only enter if RR ≥ 1.5
        if tpsl.risk_reward < 1.5:
            return RiskDecision(
                False, 0,
                f"RR {tpsl.risk_reward:.2f} < 1.5 minimum",
            )

        # Fee awareness: fat-middle positions need edge to cover variable fee
        from strategy.momentum import FeeZone
        if signal.fee_zone == FeeZone.FAT_MIDDLE:
            # Polymarket fee: taker_rate * stake * min(odds, 1-odds) / 0.5
            # Peaks at 0.50 odds (factor=1.0), falls toward extremes
            odds = signal.entry_price
            fee_factor = min(odds, 1.0 - odds) / 0.5
            fee = self.fee_cfg.middle_fee_rate * fee_factor
            ev = (signal.confidence * tpsl.tp_pct / 100
                  - (1 - signal.confidence) * tpsl.sl_pct / 100
                  - fee)
            if ev <= 0:
                return RiskDecision(
                    False, 0,
                    f"Fat-middle EV={ev:.4f} ≤ 0 after {fee*100:.1f}% fee",
                )

        is_scaled = self.bankroll.is_heat_check_active
        return RiskDecision(
            approved=True,
            stake=stake,
            reason=f"Approved | stake=${stake} | heat={is_scaled}",
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
        )
        self.open_positions[token_id] = pos
        logger.info(
            "OPEN %s %s @ %.4f | stake=$%.2f | TP=%.4f SL=%.4f",
            direction.name, asset, entry_price, stake, tpsl.take_profit, tpsl.stop_loss,
        )
        return pos

    def close_position(self, token_id: str, exit_price: float, reason: str) -> Optional[float]:
        """
        Close a position; returns realised PnL or None if not found.
        PnL is in dollars.
        """
        pos = self.open_positions.pop(token_id, None)
        if pos is None:
            return None

        if pos.direction == Direction.BUY_YES:
            raw_pnl = (exit_price - pos.entry_price) * pos.shares
        else:
            raw_pnl = (pos.entry_price - exit_price) * pos.shares

        # Deduct fees
        fee_rate = (
            CONFIG.fees.extreme_fee_rate
            if exit_price < CONFIG.fees.extreme_low or exit_price > CONFIG.fees.extreme_high
            else CONFIG.fees.middle_fee_rate
        )
        fee_cost = pos.stake * fee_rate
        net_pnl = raw_pnl - fee_cost

        self.bankroll.record_trade_result(net_pnl)
        logger.info(
            "CLOSE %s %s @ %.4f | PnL=$%.2f (fee=$%.3f) | reason=%s",
            pos.direction.name, pos.asset, exit_price,
            net_pnl, fee_cost, reason,
        )
        return net_pnl

    # ── Hard-exit monitor ─────────────────────────────────────────────────────

    def positions_needing_hard_exit(self) -> List[PositionMeta]:
        """Returns positions that have exceeded the 180-second hard-exit timer."""
        now = time.time()
        result = []
        for pos in self.open_positions.values():
            age = now - pos.open_ts
            if age >= self.exec_cfg.hard_exit_seconds and not pos.hard_exit_triggered:
                pos.hard_exit_triggered = True
                result.append(pos)
        return result

    # ── TP/SL check ───────────────────────────────────────────────────────────

    def check_exit_conditions(
        self,
        token_id: str,
        current_price: float,
    ) -> Optional[str]:
        """
        Returns exit reason string if TP or SL is hit, else None.
        """
        pos = self.open_positions.get(token_id)
        if not pos:
            return None

        if pos.direction == Direction.BUY_YES:
            if current_price >= pos.tp:
                return "TAKE_PROFIT"
            if current_price <= pos.sl:
                return "STOP_LOSS"
        else:  # BUY_NO
            if current_price <= pos.tp:
                return "TAKE_PROFIT"
            if current_price >= pos.sl:
                return "STOP_LOSS"

        return None
