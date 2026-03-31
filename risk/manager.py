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

import json
import os
import time
import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set
import logging

from config import CONFIG
from strategy.momentum import Direction, SignalBreakdown, TPSLLevels

POSITIONS_FILE = os.path.join("logs", "positions.json")
BANKROLL_FILE  = os.path.join("logs", "bankroll.json")

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
    sl_breach_ts: float = 0.0        # timestamp when wide SL first breached (0 = not breached)
    dynamic_sl_override: float = 0.0 # when > 0: LLM-set stop % (e.g. 0.05 = exit if -5% from entry)

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
        self._load()

    def _load(self) -> None:
        """Restore capital and streak from disk so restarts don't reset state."""
        if not os.path.exists(BANKROLL_FILE):
            return
        try:
            with open(BANKROLL_FILE) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                logger.warning("Bankroll file has wrong format — starting fresh")
                return
            self.capital = float(d.get("capital", self.cfg.total))
            self.daily_start_capital = float(d.get("daily_start_capital", self.capital))
            self.consecutive_wins = int(d.get("consecutive_wins", 0))
            self.total_trades = int(d.get("total_trades", 0))
            self.total_pnl = float(d.get("total_pnl", 0.0))
            logger.info(
                "Bankroll restored: capital=$%.2f streak=%d trades=%d",
                self.capital, self.consecutive_wins, self.total_trades,
            )
        except Exception as exc:
            logger.warning("Failed to load bankroll state: %s", exc)

    def _save(self) -> None:
        """Persist capital and streak to disk after every trade."""
        os.makedirs("logs", exist_ok=True)
        try:
            with open(BANKROLL_FILE, "w") as f:
                json.dump({
                    "capital": round(self.capital, 6),
                    "daily_start_capital": round(self.daily_start_capital, 6),
                    "consecutive_wins": self.consecutive_wins,
                    "total_trades": self.total_trades,
                    "total_pnl": round(self.total_pnl, 6),
                    "saved_ts": time.time(),
                }, f)
        except Exception as exc:
            logger.warning("Failed to save bankroll state: %s", exc)

    def record_trade_result(self, pnl: float) -> None:
        self.capital += pnl
        self.total_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self.consecutive_wins += 1
        else:
            self.consecutive_wins = 0
        self._save()

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
        self._load_positions()

    # ── Position persistence ─────────────────────────────────────────────────

    def _save_positions(self) -> None:
        """Persist open_positions to disk so bot restarts can resume monitoring."""
        os.makedirs("logs", exist_ok=True)
        try:
            data = {}
            for tid, pos in self.open_positions.items():
                data[tid] = {
                    "token_id": pos.token_id,
                    "asset": pos.asset,
                    "direction": pos.direction.name,
                    "stake": pos.stake,
                    "entry_price": pos.entry_price,
                    "tp": pos.tp,
                    "sl": pos.sl,
                    "open_ts": pos.open_ts,
                    "window_end_ts": pos.window_end_ts,
                    "shares": pos.shares,
                    "remaining_shares": pos.remaining_shares,
                    "highest_price": pos.highest_price,
                    "exit_stage": pos.exit_stage.name,
                    "profit_trigger_ts": pos.profit_trigger_ts,
                    "hard_exit_triggered": pos.hard_exit_triggered,
                    "condition_id": pos.condition_id,
                    "dynamic_sl_override": pos.dynamic_sl_override,
                }
            with open(POSITIONS_FILE, "w") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("Failed to save positions: %s", exc)

    def _load_positions(self) -> None:
        """Restore open_positions from disk on startup."""
        if not os.path.exists(POSITIONS_FILE):
            return
        try:
            with open(POSITIONS_FILE) as f:
                data = json.load(f)
            if not data:
                return
            now = time.time()
            for tid, d in data.items():
                # Reject stub/dry-run token IDs (real Polymarket IDs are 64-char hex strings).
                # Prevents dry-run ghost positions from persisting into live sessions.
                if len(tid) < 20 or not all(c in "0123456789abcdefABCDEF" for c in tid):
                    logger.warning(
                        "Discarding non-production token ID '%s' from positions file — "
                        "likely a dry-run stub; skipping",
                        tid,
                    )
                    continue
                pos = PositionMeta(
                    token_id=d["token_id"],
                    asset=d["asset"],
                    direction=Direction[d["direction"]],
                    stake=d["stake"],
                    entry_price=d["entry_price"],
                    tp=d["tp"],
                    sl=d["sl"],
                    open_ts=d["open_ts"],
                    window_end_ts=d["window_end_ts"],
                    shares=d["shares"],
                    remaining_shares=d["remaining_shares"],
                    highest_price=d["highest_price"],
                    exit_stage=ExitStage[d["exit_stage"]],
                    profit_trigger_ts=d["profit_trigger_ts"],
                    hard_exit_triggered=d["hard_exit_triggered"],
                    condition_id=d["condition_id"],
                )
                pos.dynamic_sl_override = float(d.get("dynamic_sl_override", 0.0))
                # Discard positions whose 5-min window has already expired.
                # Keeping stale positions fills max_open_positions and blocks
                # all new trades. The market resolved on-chain; we can't sell.
                if pos.window_end_ts > 0 and pos.window_end_ts < now - 30:
                    logger.warning(
                        "Discarding expired position %s/%s — window ended %ds ago",
                        pos.asset, pos.direction.name,
                        int(now - pos.window_end_ts),
                    )
                    continue
                self.open_positions[tid] = pos
                if pos.condition_id:
                    self._traded_conditions.add(pos.condition_id)
            logger.info(
                "Restored %d open position(s) from disk: %s",
                len(self.open_positions),
                [f"{p.asset}/{p.direction.name}" for p in self.open_positions.values()],
            )
        except Exception as exc:
            logger.warning("Failed to load positions from disk: %s", exc)

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
        market_type: str = "target",
        cascade_discount: float = 0.0,
    ) -> RiskDecision:
        # Ruin floor: capital < $50 → hard stop (CLAUDE.md rule)
        if self.bankroll.capital < 50.0:
            return RiskDecision(False, 0, f"RUIN FLOOR: capital=${self.bankroll.capital:.2f} < $50 — halt until manual review")

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

        # Max entry price cap — applies only to price-target markets (0.20-0.27 sweet spot).
        # Up/Down markets trade near $0.50 by design; price cap doesn't apply.
        if market_type != "updown":
            if signal.direction == Direction.BUY_YES:
                if signal.entry_price > self.edge_cfg.max_entry_price:
                    return RiskDecision(
                        False, 0,
                        f"YES entry {signal.entry_price:.4f} above max {self.edge_cfg.max_entry_price}",
                    )
            else:
                min_no = 1.0 - self.edge_cfg.max_entry_price
                if signal.entry_price < min_no:
                    return RiskDecision(
                        False, 0,
                        f"NO entry {signal.entry_price:.4f} below min {min_no:.4f}",
                    )
        else:
            # Updown: reject near-resolved markets.
            # Track record: all profitable trades were at 0.48-0.56 entry;
            # all losses were 0.59+ entries (ETH 0.59, SOL 0.88, SOL 0.89, SOL 0.67 live).
            # Tightened 0.75→0.60: above 0.60, upside to 0.98 cap < 38¢ while
            # 35% dynamic SL = up to 21¢ downside at 0.60 → apparent RR OK but
            # the ATR-based RR check uses capped sl_distance (0.08) which doesn't
            # reflect the 35% stop → fake RR of 1.12 lets bad trades through.
            # 0.60 hard cap eliminates the entire 0.59+ losing pattern.
            # Mirror: below 0.40 → symmetric rejection (NO near-resolved).
            if signal.entry_price > 0.60 or signal.entry_price < 0.40:
                return RiskDecision(
                    False, 0,
                    f"Updown near-resolved: price {signal.entry_price:.4f} outside [0.40, 0.60]",
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

            # Cross-asset cascade discount: lead asset fired → follower gets easier entry
            if cascade_discount > 0:
                effective_min = max(0.20, effective_min - cascade_discount)

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

        # RR gate — relaxed for Up/Down markets (symmetric coin-flip, RR ~1.0 is normal)
        min_rr = 0.9 if market_type == "updown" else 1.5
        if tpsl.risk_reward < min_rr:
            return RiskDecision(False, 0, f"RR {tpsl.risk_reward:.2f} < {min_rr}")

        # Fat-middle confidence gate
        from strategy.momentum import FeeZone
        if signal.fee_zone == FeeZone.FAT_MIDDLE:
            # Up/Down markets: just need to beat coin flip + fees (~52% confidence)
            # Price-target markets: require high conviction (80%)
            min_conf = (
                self.fee_cfg.updown_min_confidence
                if market_type == "updown"
                else self.fee_cfg.middle_min_confidence
            )
            if signal.confidence < min_conf:
                return RiskDecision(
                    False, 0,
                    f"Fat-middle conf {signal.confidence:.2f} < {min_conf:.2f} ({market_type})",
                )

            # EV gate for price-target markets only
            if market_type != "updown":
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
        self._save_positions()
        return pos

    def record_stage1_sell(self, token_id: str, shares_sold: float) -> None:
        """Called after stage-1 sell. Updates remaining shares.
        Only marks STAGE_1_DONE when shares were actually sold — prevents
        the position from entering stage-2 logic if the cascade failed (0 fills).
        """
        pos = self.open_positions.get(token_id)
        if pos:
            pos.remaining_shares = max(0.0, pos.remaining_shares - shares_sold)
            if shares_sold > 0:
                pos.exit_stage = ExitStage.STAGE_1_DONE
            logger.info(
                "STAGE-1 SELL %s | sold=%.4f remaining=%.4f",
                token_id[:8], shares_sold, pos.remaining_shares,
            )
            # Persist immediately — if bot crashes before stage-2, we must not
            # re-attempt to sell the already-sold 95% on restart.
            self._save_positions()

    def close_position(
        self,
        token_id: str,
        exit_price: float,
        reason: str,
        shares_override: Optional[float] = None,
        actual_fee: Optional[float] = None,
    ) -> Optional[float]:
        """
        Close fully; returns net PnL. Uses remaining_shares for accuracy.
        actual_fee: real fee from CLOB fill reconciliation. If provided, used
        directly instead of estimating from config fee rates — eliminates the
        primary source of reporting drift vs actual Polymarket balance.
        """
        pos = self.open_positions.pop(token_id, None)
        if pos is None:
            return None

        shares = shares_override if shares_override is not None else pos.remaining_shares

        # Always: bought token at entry_price, selling at exit_price
        raw_pnl = (exit_price - pos.entry_price) * shares

        if actual_fee is not None and actual_fee >= 0:
            fee_cost = actual_fee
            fee_source = "actual"
        else:
            fee_rate = (
                CONFIG.fees.extreme_fee_rate
                if exit_price < CONFIG.fees.extreme_low or exit_price > CONFIG.fees.extreme_high
                else CONFIG.fees.middle_fee_rate
            )
            # Fee applies to BOTH sides: entry notional (pos.stake) + exit notional.
            # Previous estimate only used pos.stake (buy-side), missing the sell fee.
            # For entry=0.55→exit=0.75 on 4.85 shares:
            #   old: $2.67 × 1.6% = $0.043  (missing sell-side fee)
            #   new: ($2.67 + $3.64) × 1.6% = $0.101  (correct round-trip fee)
            exit_notional = exit_price * shares
            fee_cost = (pos.stake + exit_notional) * fee_rate
            fee_source = "estimated"

        net_pnl = raw_pnl - fee_cost

        self.bankroll.record_trade_result(net_pnl)
        self._last_close_ts = time.time()
        logger.info(
            "CLOSE %s %s @ %.4f | PnL=$%.2f (fee=$%.3f %s) | reason=%s",
            pos.direction.name, pos.asset, exit_price,
            net_pnl, fee_cost, fee_source, reason,
        )
        self._save_positions()
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
        # Scale to window size: 180s flat is correct for 5-min windows but exits
        # 15-min positions far too early (3 min into a 10-min remaining window).
        # Adaptive: 60% of time remaining at entry, capped at 480s, floor at 180s.
        #   5-min window, 225s remaining at entry  → max(180, min(135, 480)) = 180s
        #   15-min window, 600s remaining at entry → max(180, min(360, 480)) = 360s (6 min)
        #   15-min window, 840s remaining at entry → max(180, min(504, 480)) = 480s (8 min)
        if pos.window_end_ts > 0:
            remaining_at_entry = pos.window_end_ts - pos.open_ts
            adaptive_hard_exit = max(
                self.exec_cfg.hard_exit_seconds,
                min(int(remaining_at_entry * 0.60), 480),
            )
        else:
            adaptive_hard_exit = self.exec_cfg.hard_exit_seconds
        if time_held >= adaptive_hard_exit and not pos.hard_exit_triggered:
            pos.hard_exit_triggered = True
            return ExitDecision(True, "HARD_EXIT", urgency="immediate")

        # ── 2. Window expiry guard ─────────────────────────────────────────────
        # Fire when entering the final no_trade_last_sec window OR when window has
        # already passed (remaining <= 0). The original `0 < remaining` check meant
        # positions stayed open forever once the window expired mid-session.
        if pos.window_end_ts > 0 and remaining <= self.exec_cfg.no_trade_last_sec:
            return ExitDecision(True, "EXIT_WINDOW_END", urgency="immediate")

        # ── 3. Stage-1 profit: time-aware target ────────────────────────────────
        # Windowed markets: target scales with time remaining.
        #   >120s remaining: hold for +30% (enough time; better R/R — breakeven WR ~40%)
        #   60-120s remaining: standard +25%
        #   <60s remaining: take +18% (window closing; don't die waiting for a higher target)
        # Fee math: round-trip fees ~3.6% → breakeven WR at 25%/20% = ~50%;
        #           at 30%/20% = ~40%. Raising TP to 30% when time allows crosses break-even.
        if pos.exit_stage == ExitStage.NONE:
            if pos.window_end_ts > 0:
                if remaining > 120:
                    profit1_pct = 0.30
                elif remaining > 60:
                    profit1_pct = 0.25
                else:
                    profit1_pct = 0.18   # take what's available near window expiry
            else:
                profit1_pct = 0.25       # price-target markets: unchanged

            if move_pct >= profit1_pct:
                if pos.window_end_ts > 0:
                    # Windowed markets: no confirmation timer — price decays near expiry.
                    return ExitDecision(True, "PROFIT_1", partial=True, urgency="cascade")
                # Price-target markets: 2.5s confirmation to filter wicks
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

        # ── 6b. LLM-tightened stop (set via advise_exit TIGHTEN_STOP) ──────────
        # When the exit advisor tightens the stop, this overrides the wide 35% SL.
        # e.g. dynamic_sl_override=0.05 → exit if price drops below entry * 0.95
        # (protecting a +8% profit from reversing below breakeven)
        if pos.dynamic_sl_override > 0 and time_held >= 10:
            tight_price = pos.entry_price * (1 - pos.dynamic_sl_override)
            if current_price <= tight_price:
                return ExitDecision(True, f"LLM_TIGHT_SL({pos.dynamic_sl_override:.0%})", urgency="immediate")

        # ── 7. Dynamic SL (only before stage-1, after 10s grace) ─────────────
        if time_held >= 10:
            if remaining > 120:
                # Windowed markets: 20% SL (breakeven WR ~46% vs 69% at 35%).
                # Data: T00021 exit=0.28 entry=0.56 (-50%), T00022 exit=0.35 entry=0.58 (-40%),
                # T00023 exit=0.31 entry=0.54 (-43%) — all would have exited at 20% SL.
                # Avg win=$0.539 vs avg loss=$1.196 (2.22×): 35% SL makes breakeven 69% WR.
                # At 20% SL: avg loss ~$0.57 → breakeven ~46% WR, achievable with new filters.
                sl_pct = 0.20 if pos.window_end_ts > 0 else 0.35
                # Catastrophic drop (>50%): exit immediately — not a wick, genuine move.
                # T00016 ETH: entered 0.56, exited 0.10 (-$2.32) because 10s confirmation
                # window delayed SL until hard exit fired. At -50%+ the confirmation
                # window costs more than it saves.
                if current_price <= pos.entry_price * 0.50:
                    return ExitDecision(True, "STOP_LOSS", urgency="immediate")
                # Normal wide SL: require 10s confirmation to filter wick noise.
                # Updown mid-window prices spike and recover frequently.
                if current_price <= pos.entry_price * (1 - sl_pct):
                    # Windowed markets (updown sniper): immediate exit — no confirmation.
                    # 10s window causes 15-20% extra loss as price falls through the stop.
                    # Sniper entry already confirms direction; a 35% adverse move = thesis wrong.
                    if pos.window_end_ts > 0:
                        return ExitDecision(True, "STOP_LOSS", urgency="immediate")
                    if pos.sl_breach_ts == 0.0:
                        pos.sl_breach_ts = now  # first breach — start confirmation timer
                        logger.debug(
                            "Wide SL breached @ %.4f (entry=%.4f sl_pct=%.0f%%) — "
                            "waiting 10s confirmation",
                            current_price, pos.entry_price, sl_pct * 100,
                        )
                    elif now - pos.sl_breach_ts >= 10.0:
                        return ExitDecision(True, "STOP_LOSS", urgency="immediate")
                else:
                    if pos.sl_breach_ts > 0.0:
                        logger.debug(
                            "Wide SL breach reset — price %.4f recovered above threshold %.4f",
                            current_price, pos.entry_price * (1 - sl_pct),
                        )
                    pos.sl_breach_ts = 0.0  # price recovered — reset confirmation timer
            else:
                sl_pct = 0.10  # Last 2 min: tight stop, fire immediately
                if current_price <= pos.entry_price * (1 - sl_pct):
                    return ExitDecision(True, "STOP_LOSS", urgency="immediate")

        return None

    # ── Convenience ──────────────────────────────────────────────────────────

    def positions_needing_hard_exit(self) -> List[PositionMeta]:
        """Returns positions that hit the adaptive hard-exit timer or window expiry."""
        now = time.time()
        result = []
        for pos in self.open_positions.values():
            if pos.hard_exit_triggered:
                continue
            age = now - pos.open_ts

            # Absolute window expiry guard: force exit when within no_trade_last_sec
            # of window close, regardless of the adaptive timer. This prevents positions
            # from ever reaching market resolution (tokens go to 0 / 1 at T=0).
            if pos.window_end_ts > 0:
                time_to_expiry = pos.window_end_ts - now
                if time_to_expiry <= self.exec_cfg.no_trade_last_sec:
                    pos.hard_exit_triggered = True
                    result.append(pos)
                    continue

            # Adaptive timer: 60% of remaining time at entry, capped at 480s, floor at 180s
            if pos.window_end_ts > 0:
                remaining_at_entry = pos.window_end_ts - pos.open_ts
                adaptive = max(
                    self.exec_cfg.hard_exit_seconds,
                    min(int(remaining_at_entry * 0.60), 480),
                )
            else:
                adaptive = self.exec_cfg.hard_exit_seconds
            if age >= adaptive:
                pos.hard_exit_triggered = True
                result.append(pos)
        return result
