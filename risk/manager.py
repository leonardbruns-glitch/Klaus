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
import tempfile
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


def _atomic_json_write(path: str, data: dict) -> None:
    """
    Write JSON atomically via temp-file + os.replace().
    A crash mid-write leaves the old file intact — never a partial/corrupt file.
    os.replace() is atomic on POSIX (rename syscall).
    """
    dir_ = os.path.dirname(os.path.abspath(path))
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_, suffix=".tmp", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
            tmp_path = f.name
        os.replace(tmp_path, path)
    except Exception as exc:
        logger.warning("Atomic write failed for %s: %s", path, exc)
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Exit stage enum
# ---------------------------------------------------------------------------

class ExitStage(Enum):
    NONE = auto()        # no sell yet
    STAGE_1_DONE = auto()  # 60% sold at stage-1; 40% remaining for stage-2


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
    best_ask: float = 0.0              # market ask at entry — captures execution quality
    tp: float = 0.0                    # ATR-based TP (still used as fallback)
    sl: float = 0.0                    # ATR-based SL (overridden by time-aware SL)
    open_ts: float = field(default_factory=time.time)
    window_end_ts: float = 0.0         # unix ts when the window closes
    window_seconds: int = 0            # actual window duration (300=5m, 900=15m) — DO NOT use window_end_ts - open_ts (late entries skew this)
    shares: float = 0.0
    remaining_shares: float = 0.0     # updated after partial sells
    highest_price: float = 0.0        # peak since open (for trailing stop)
    lowest_price: float = 0.0         # trough since open (for volatility analysis)
    highest_price_ts: float = 0.0     # seconds from open_ts when highest_price was set
    lowest_price_ts: float = 0.0      # seconds from open_ts when lowest_price was set
    # Bounce-from-MAE: max price within 10s after a new lowest_price was set.
    # Separates reversals (fast bounce) from collapses (no bounce) when MAE > 40%.
    mae_bounce_peak: float = 0.0      # highest price seen within 10s of last new low
    mae_bounce_start_ts: float = 0.0  # absolute ts when current MAE window opened
    exit_stage: ExitStage = ExitStage.NONE
    profit_trigger_ts: float = 0.0    # timestamp when +25 % first seen
    hard_exit_triggered: bool = False
    condition_id: str = ""            # Polymarket condition ID for dedup
    sl_breach_ts: float = 0.0        # timestamp when wide SL first breached (0 = not breached)
    sl_breach_price: float = 0.0     # token price at the moment SL was first breached
    sl_breach_llm_queried: bool = False  # True once LLM has been asked about this breach
    dynamic_sl_override: float = 0.0 # when > 0: LLM-set stop % (e.g. 0.05 = exit if -5% from entry)
    ratchet_sl: float = 0.0          # locked profit floor — only moves up, never down
                                      # 0.0 = inactive | entry*1.07 = +7% floor | entry*1.15 = +15% floor
    ratchet_lock_ts: float = 0.0      # timestamp when price first crossed the next ratchet tier (3s confirmation)
    ratchet_exit_breach_ts: float = 0.0  # when price first touched ratchet floor (3s confirmation before exit)
    quality_score: int = 0            # QS at entry — drives ratchet floor buffer (see ratchet logic)
    velocity_breach_ts: float = 0.0   # when price first dropped below -25% (5s emergency brake)
    moon_bag_trail_breach_ts: float = 0.0  # when moon bag trail floor first touched (3s confirmation before exit)
    binance_price_at_entry: float = 0.0  # Binance spot at entry — used to detect post-entry reversal
    binance_reversal_count: int = 0      # consecutive check cycles Binance has been reversed (each ~1s)
    entry_delta_pct: float = 0.0      # |Binance delta| at entry (fraction, e.g. 0.0013 = 0.13%)
    entry_lag_pct: float = 0.0        # lag_remaining at entry (fraction, e.g. 0.50 = 50% unpriced)
    entry_fair_value: float = 0.0     # sigmoid fair value at entry — used for lag inversion check
    stage1_attempts: int = 0         # failed stage-1 attempts (0 fills); force STAGE_1_DONE after 3
    stage1_sell_price: float = 0.0   # actual fill price at stage-1 exit — saved for crash recovery
    signal_flip_ts: float = 0.0      # when SIGNAL_FLIPPED condition first became true (Phase 2 confirmation)
    moon_bag_high: float = 0.0       # highest price seen since Stage-1 completed (for trailing stop)
    is_bond: bool = False            # True for BOND trades — time-exit only, no TP/SL
    bond_exit_sec: int = 0           # seconds before window close to exit (30=15m, 20=5m)
    bond_outcome_direction: str = "down"  # "up" or "down" — token resolves when asset goes this direction
    bond_entry_class: str = ""       # e.g. "CORE/INIT" — drives SL regime in _check_open_positions
    bond_macro_regime: str = ""      # Layer-1 regime at entry: TREND_UP / TREND_DOWN / CHOP
    bond_tp1_done: bool = False      # True after +40% partial sell (50% of remaining)
    bond_tp2_done: bool = False      # True after +80% partial sell (25% of remaining)
    # Cascade-abort inputs (populated by main.py position monitor at T+30s / T+60s)
    entry_snap_30s_pct: float = 0.0  # (current - entry) / entry at T+30s, 0.0 = not yet captured
    entry_snap_60s_pct: float = 0.0  # same metric at T+60s
    cascade_state: str = "UNKNOWN"   # UNKNOWN → RECOVERING | CASCADING (frozen once written)
    scale_in_done: bool = False      # True after smooth-runner scale-in fires (once per trade)

    def __post_init__(self) -> None:
        if self.remaining_shares == 0.0:
            self.remaining_shares = self.shares
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == 0.0:
            self.lowest_price = self.entry_price


@dataclass
class RiskDecision:
    approved: bool
    stake: float
    reason: str
    is_scaled: bool = False
    bond_ev_multiplier: float = 1.0   # EV-prior multiplier applied (bonds only; 1.0 for sniper)


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
        self._last_utc_day: int = -1
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
            self._last_utc_day = int(d.get("last_utc_day", -1))
            logger.info(
                "Bankroll restored: capital=$%.2f streak=%d trades=%d",
                self.capital, self.consecutive_wins, self.total_trades,
            )
        except Exception as exc:
            logger.warning("Failed to load bankroll state: %s", exc)

    def _save(self) -> None:
        """Persist capital and streak to disk after every trade (atomic write)."""
        os.makedirs("logs", exist_ok=True)
        _atomic_json_write(BANKROLL_FILE, {
            "capital": round(self.capital, 6),
            "daily_start_capital": round(self.daily_start_capital, 6),
            "consecutive_wins": self.consecutive_wins,
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 6),
            "last_utc_day": self._last_utc_day,
            "saved_ts": time.time(),
        })

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
        if self.cfg.max_daily_loss_pct <= 0:
            return False
        if self.daily_start_capital <= 0:
            return False
        return self.daily_loss >= self.daily_start_capital * self.cfg.max_daily_loss_pct

    @property
    def is_ruined(self) -> bool:
        return self.cfg.ruin_floor > 0 and self.capital < self.cfg.ruin_floor

    def reset_daily(self) -> None:
        self.daily_start_capital = self.capital

    def maybe_reset_daily(self) -> bool:
        """Reset daily_start_capital at UTC midnight. Returns True if reset occurred."""
        today = int(time.time() // 86400)
        if self._last_utc_day < 0:
            self._last_utc_day = today
            return False
        if today != self._last_utc_day:
            self._last_utc_day = today
            self.daily_start_capital = self.capital
            self._save()
            logger.info(
                "DAILY_RESET: new UTC day — daily_start_capital=%.2f", self.capital
            )
            return True
        return False

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
        self._pending_assets: Set[str] = set()       # race-condition guard: asset locked from approve→fill
        self._traded_conditions: Set[str] = set()   # dedup within window
        self._last_close_ts: float = 0.0
        # Expired positions with STAGE_1_DONE found on startup — bot crashed before stage-2.
        # Populated by _load_positions, consumed by main.py _startup_orphan_sweep to write recovery records.
        self._expired_stage1_positions: list = []
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
                    "lowest_price": pos.lowest_price,
                    "exit_stage": pos.exit_stage.name,
                    "profit_trigger_ts": pos.profit_trigger_ts,
                    "hard_exit_triggered": pos.hard_exit_triggered,
                    "condition_id": pos.condition_id,
                    "dynamic_sl_override": pos.dynamic_sl_override,
                    "stage1_sell_price": pos.stage1_sell_price,
                    "window_seconds": pos.window_seconds,
                    "sl_breach_ts": pos.sl_breach_ts,
                    "sl_breach_price": pos.sl_breach_price,
                    "stage1_attempts": pos.stage1_attempts,
                    "ratchet_sl": pos.ratchet_sl,
                    "ratchet_lock_ts": pos.ratchet_lock_ts,
                    "quality_score": pos.quality_score,
                    "velocity_breach_ts": pos.velocity_breach_ts,
                    "binance_price_at_entry": pos.binance_price_at_entry,
                    "binance_reversal_count": pos.binance_reversal_count,
                    "entry_delta_pct": pos.entry_delta_pct,
                    "entry_lag_pct": pos.entry_lag_pct,
                    "entry_fair_value": pos.entry_fair_value,
                    "moon_bag_high": pos.moon_bag_high,
                    "bond_tp1_done": pos.bond_tp1_done,
                    "bond_tp2_done": pos.bond_tp2_done,
                    "scale_in_done": pos.scale_in_done,
                    "is_bond": pos.is_bond,
                    "bond_entry_class": pos.bond_entry_class,
                    "bond_exit_sec": pos.bond_exit_sec,
                    "bond_outcome_direction": pos.bond_outcome_direction,
                    "bond_macro_regime": pos.bond_macro_regime,
                }
            _atomic_json_write(POSITIONS_FILE, data)
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
                # Default 900 (15m) if missing from legacy positions.json — wrong default (0)
                # caused 15m positions to be classified as 5m → wrong SL grace/threshold.
                # Infer from window_end_ts - open_ts as tiebreaker when field is absent.
                _ws = int(d.get("window_seconds", 0))
                if _ws == 0:
                    _inferred = d["window_end_ts"] - d["open_ts"]
                    _ws = 900 if _inferred >= 600 else 300
                pos.window_seconds = _ws
                pos.stage1_attempts = int(d.get("stage1_attempts", 0))
                pos.stage1_sell_price = float(d.get("stage1_sell_price", 0.0))
                pos.sl_breach_ts = float(d.get("sl_breach_ts", 0.0))
                pos.sl_breach_price = float(d.get("sl_breach_price", 0.0))
                pos.ratchet_sl = float(d.get("ratchet_sl", 0.0))
                pos.ratchet_lock_ts = float(d.get("ratchet_lock_ts", 0.0))
                pos.quality_score = int(d.get("quality_score", 0))
                pos.velocity_breach_ts = float(d.get("velocity_breach_ts", 0.0))
                pos.binance_price_at_entry = float(d.get("binance_price_at_entry", 0.0))
                pos.binance_reversal_count = int(d.get("binance_reversal_count", 0))
                pos.entry_delta_pct = float(d.get("entry_delta_pct", 0.0))
                pos.entry_lag_pct = float(d.get("entry_lag_pct", 0.0))
                pos.entry_fair_value = float(d.get("entry_fair_value", 0.0))
                pos.moon_bag_high = float(d.get("moon_bag_high", 0.0))
                pos.lowest_price = float(d.get("lowest_price", pos.entry_price))
                pos.bond_tp1_done = bool(d.get("bond_tp1_done", False))
                pos.bond_tp2_done = bool(d.get("bond_tp2_done", False))
                pos.scale_in_done = bool(d.get("scale_in_done", False))
                pos.is_bond = bool(d.get("is_bond", False))
                pos.bond_entry_class = str(d.get("bond_entry_class", ""))
                pos.bond_exit_sec = int(d.get("bond_exit_sec", 0))
                pos.bond_outcome_direction = str(d.get("bond_outcome_direction", "down"))
                pos.bond_macro_regime = str(d.get("bond_macro_regime", ""))
                # Discard positions whose 5-min window has already expired.
                # Keeping stale positions fills max_open_positions and blocks
                # all new trades. The market resolved on-chain; we can't sell.
                if (pos.window_end_ts > 0 and pos.window_end_ts < now - 30
                        and pos.bond_entry_class != "LDA"):
                    if pos.exit_stage == ExitStage.STAGE_1_DONE:
                        # Stage-1 was profitable (60% sold) but bot crashed before stage-2 completed.
                        # Queue for recovery record in _startup_orphan_sweep — don't silently discard.
                        self._expired_stage1_positions.append({
                            "token_id": pos.token_id,
                            "asset": pos.asset,
                            "direction": pos.direction.name,
                            "entry_price": pos.entry_price,
                            "stage1_sell_price": pos.stage1_sell_price,
                            "shares": pos.shares,
                            "remaining_shares": pos.remaining_shares,
                            "open_ts": pos.open_ts,
                            "window_end_ts": pos.window_end_ts,
                            "window_size_s": pos.window_seconds,
                            "stake": pos.stake,
                        })
                        logger.warning(
                            "EXPIRED STAGE-1 %s/%s: entry=%.4f s1_price=%.4f — queued for recovery",
                            pos.asset, pos.direction.name, pos.entry_price, pos.stage1_sell_price,
                        )
                    else:
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
        """Clear condition dedup set between windows.

        Not strictly required: condition_ids are per-window (include window_end_ts
        in their hash), so a new window always generates a new condition_id and is
        never blocked by a previous window's entry. However, calling this prevents
        unbounded set growth during long sessions. main.py does not call this —
        acceptable because the set only holds ~3-10 ids per session at current
        trade frequency.
        """
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
        is_sniper: bool = False,
        window_seconds: int = 0,
        bond_entry_class: str = "",
        bond_macro_regime: str = "",
    ) -> RiskDecision:
        _is_bond = getattr(signal, "signal_source", "") == "BOND"

        # ── Trading hours gate (data-driven: 14:00 UTC is the only edge window) ──
        # Skip in dry_run mode so the simulation can be tested at any hour.
        # BOND is exempt — it has its own 15-min volatile gate in the scanner.
        if not CONFIG.dry_run and not _is_bond:
            current_hour = datetime.datetime.utcnow().hour
            blocked = getattr(self.edge_cfg, "blocked_hours_utc", [])
            if blocked and current_hour in blocked:
                return RiskDecision(
                    False, 0,
                    f"Blocked trading hour (UTC {current_hour:02d}:xx — blocked: {blocked})",
                )
            allowed = self.edge_cfg.allowed_hours_utc
            if allowed and current_hour not in allowed:
                return RiskDecision(
                    False, 0,
                    f"Outside trading hours (UTC {current_hour:02d}:xx — allowed: {allowed})",
                )

        # Post-close cooldown
        if time.time() - self._last_close_ts < self.cfg.post_close_cooldown:
            return RiskDecision(False, 0, "Post-close cooldown active")

        # Window expiry gate: don't enter if < no_trade_last_sec remaining.
        # BOND exempt: scanner already enforces 45s minimum remaining.
        if not _is_bond and window_end_ts > 0:
            remaining = window_end_ts - time.time()
            if remaining < self.exec_cfg.no_trade_last_sec:
                return RiskDecision(False, 0, f"Window closing in {remaining:.0f}s")

        # Condition dedup — blocks same market window (condition_id) from re-entry.
        # BOND exempt: LLM may want to re-enter the same window if conditions changed.
        if not _is_bond and condition_id and condition_id in self._traded_conditions:
            return RiskDecision(False, 0, f"Already traded condition {condition_id[:8]}")

        # Token-level re-entry guard: also block by token_id for 120s.
        # BOND exempt: LLM decides its own re-entry timing.
        _recently_closed = getattr(self, "_recently_closed_tokens", {})
        if not _is_bond and token_id in _recently_closed:
            if time.time() - _recently_closed[token_id] < 120:
                return RiskDecision(False, 0, f"Token {token_id[:8]} closed <120s ago — no re-entry")
            else:
                _recently_closed.pop(token_id, None)

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
            # Updown: cap at 0.77 (sniper path) / 0.90 (contrarian) / 0.99 (bond).
            # Sniper cap: tokens above 0.77 are fully-priced — fee-adjusted edge shrinks.
            # Confirmed: ETH@0.63 and SOL@0.60 wicked out within 25s (2026-04-09).
            # Contrarian buys cheap tokens (~0.10) — floor doesn't apply, max is 0.90.
            # Bond: buys low-probability tokens (≤0.20) near window close — contrarian bet.
            _signal_source = getattr(signal, "signal_source", "MOMENTUM")
            _is_contrarian = _signal_source == "CONTRARIAN"
            _is_bond = _signal_source == "BOND"
            if _is_contrarian:
                _updown_max = 0.90
                _updown_min = 0.03
            elif _is_bond:
                _updown_max = 0.99   # LLM decides — no price cap
                _updown_min = 0.01   # LLM decides — no price floor
            else:
                _updown_max = 0.65   # BOND owns 0.66–0.82; sniper stays below to avoid overlap
                _updown_min = 0.05
            if signal.entry_price > _updown_max or signal.entry_price < _updown_min:
                return RiskDecision(
                    False, 0,
                    f"Updown entry {signal.entry_price:.4f} outside [{_updown_min:.2f}, {_updown_max:.2f}] "
                    f"({'contrarian' if _is_contrarian else 'bond' if _is_bond else 'sniper'} path)",
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

            _sig_src = getattr(signal, "signal_source", "MOMENTUM")
            if _sig_src not in ("BOND", "CONTRARIAN") and signal.composite < effective_min:
                return RiskDecision(
                    False, 0,
                    f"{asset} score {signal.composite:.2f} < effective_min {effective_min:.2f} "
                    f"(multiplier={multiplier}x macro={'yes' if current_hour in self.edge_cfg.macro_window_hours else 'no'})",
                )

        # Already in this token
        if token_id in self.open_positions:
            return RiskDecision(False, 0, f"Already in {token_id[:8]}")

        # Already have an open position on this asset (any direction, any window).
        # Entering opposite direction = guaranteed fee loss (SOL Up + SOL Down = hedge).
        # Entering same direction = redundant double exposure, not additive edge.
        # Also check _pending_assets: race-condition guard for concurrent entry paths
        # firing before the first fill is confirmed in open_positions.
        if asset:
            if asset in self._pending_assets:
                return RiskDecision(False, 0, f"Already in {asset} (pending fill)")
            for pos in self.open_positions.values():
                if pos.asset == asset:
                    return RiskDecision(False, 0, f"Already in {asset} ({pos.direction.name})")

        # Max concurrent positions
        if len(self.open_positions) >= self.cfg.max_open_positions:
            return RiskDecision(False, 0, f"Max positions reached")

        # Sniper bypasses heat check — strategy unvalidated at <20 live trades.
        # Heat check caused T00022 to scale to 8 shares at bad entry → -$1.97 loss.
        # Re-enable after 20+ sniper trades with WR >55%.
        _bond_ev_mult: float = 1.0   # set in bond branch below; sniper branch leaves at 1.0
        if is_sniper:
            # Quality Score stake mapping (Kelly-lite tier sizing).
            # Score computed in window_sniper._compute_quality_score() from lag/mom/regime.
            # Score ≤ -1 is hard-rejected by the sniper before reaching here.
            #
            # New tiers (2026-04-14) — delta scoring restructured:
            #   score >= 5 → 1.5x  (Instant Max Stake: delta>0.25% + high lag + ACTIVE)
            #   score >= 2 → 1.0x  (Base Stake: covers qs=2,3,4)
            #   score 0-1  → 0.5x  (WEAK: low confidence, minimise risk)
            #   score < 0  → reject (safety net — sniper should have caught this)
            #
            # Note: qs=3 was previously 0.5x (WR=20% at old scoring). With new delta
            # tiers, qs=3 = delta 0.18%+ + moderate lag — higher quality signal.
            _qs = getattr(signal, 'quality_score', 0)
            if _qs < 0:
                logger.warning(
                    "STAKE REJECT %s | quality_score=%d — should have been rejected by sniper",
                    asset, _qs,
                )
                return RiskDecision(False, 0, f"Quality score {_qs} < 0")
            elif _qs >= 5:
                _multiplier = 1.5   # qs=5: Instant Max Stake (delta>0.25% + lag≥0.70 + ACTIVE)
            elif _qs >= 2:
                _multiplier = 1.0   # qs=2,3,4: Base Stake (sufficient combined signal)
            else:
                _multiplier = 0.5   # qs=0 or qs=1: low confidence
            # QUIET_DEAD + QUIET_FLOW hard cap: no informed flow = max 0.5x
            # QUIET_FLOW: 0%/1 trade, ETH hr=19 qs=3 QUIET_FLOW → -$8.02 at $23.69 stake
            _regime_sig = getattr(signal, 'regime', '')
            if _regime_sig in ('QUIET_DEAD', 'QUIET_FLOW') and _multiplier > 0.5:
                logger.info(
                    "STAKE CAP %s: %s regime → %.1fx capped to 0.5x",
                    asset, _regime_sig, _multiplier,
                )
                _multiplier = 0.5
            stake = round(self.cfg.base_stake * _multiplier, 2)
            logger.info(
                "STAKE QUALITY %s: score=%d regime=%s → %.1fx → $%.2f",
                asset, _qs, _regime_sig or 'unknown', _multiplier, stake,
            )
        else:
            # Bond trades: LLM decides freely — use base stake, no EV veto.
            # (EV_PRIOR was calibrated on rule-gated trades; LLM operates differently.)
            if _is_bond:
                stake = self.bankroll.current_stake
            else:
                stake = self.bankroll.current_stake
        # LATE zone: half stake — structurally worse WR, less time to recover,
        # stronger adverse-selection risk entering near window close.
        if getattr(signal, "signal_source", "") == "BOND" and "LATE" in (bond_entry_class or ""):
            stake = round(stake * 0.50, 2)
            logger.info(
                "BOND LATE stake halved → $%.2f (class=%s)", stake, bond_entry_class
            )

        # Cap at 50% of capital per position — user instruction 2026-04-15
        max_pct = 0.50
        stake = min(stake, round(self.bankroll.capital * max_pct, 2))

        # BOND stake cap: floored at base_stake (2026-05-06: raised 20→30 per user instruction)
        if getattr(signal, "signal_source", "") == "BOND":
            stake = min(stake, self.cfg.base_stake)
            min_shares_stake = round(5 * signal.entry_price, 2)
            if min_shares_stake > stake:
                stake = min_shares_stake
                logger.info("BOND stake floored to 5 shares → $%.2f (ep=%.2f)", stake, signal.entry_price)

        # RR gate — BOND exempt: LLM sets its own TP/SL and is responsible for RR.
        if not _is_bond:
            min_rr = 0.9 if market_type == "updown" else 1.5
            if tpsl.risk_reward < min_rr:
                logger.info(
                    "RISK BLOCK %s/%s | RR=%.2f < %.1f (tp=%.4f sl=%.4f ask=%.4f)",
                    signal.asset, signal.side, tpsl.risk_reward, min_rr,
                    tpsl.take_profit, tpsl.stop_loss, signal.entry_price,
                )
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
        # Lock asset immediately — prevents race condition where second concurrent
        # entry path approves before first fill is confirmed in open_positions.
        if asset:
            self._pending_assets.add(asset)
        # Lock condition immediately — prevents double-entry when fill orphans.
        # Without this: fill not detected → open_position never called → condition_id
        # never added → bot re-enters same market window on next signal (e.g. buys
        # both ETH Down AND ETH Up in same window when Down entry orphans).
        # condition_id is window-specific (includes window_end_ts hash) so locking
        # here only blocks this window, not future windows.
        if condition_id:
            self._traded_conditions.add(condition_id)
        return RiskDecision(
            approved=True,
            stake=stake,
            reason=f"Approved | ${stake} | heat={is_scaled}",
            is_scaled=is_scaled,
            bond_ev_multiplier=_bond_ev_mult if not is_sniper else 1.0,
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
        best_ask: float = 0.0,
        condition_id: str = "",
        window_end_ts: float = 0.0,
        window_seconds: int = 0,
        quality_score: int = 0,
        binance_price_at_entry: float = 0.0,
        entry_delta_pct: float = 0.0,
        entry_lag_pct: float = 0.0,
        entry_fair_value: float = 0.0,
        is_bond: bool = False,
        bond_exit_sec: int = 0,
        bond_outcome_direction: str = "down",
        bond_entry_class: str = "",
        bond_macro_regime: str = "",
    ) -> PositionMeta:
        shares = stake / entry_price if entry_price > 0 else 0
        pos = PositionMeta(
            token_id=token_id,
            asset=asset,
            direction=direction,
            stake=stake,
            entry_price=entry_price,
            best_ask=best_ask,
            tp=tpsl.take_profit,
            sl=tpsl.stop_loss,
            shares=shares,
            remaining_shares=shares,
            highest_price=entry_price,
            lowest_price=entry_price,
            condition_id=condition_id,
            window_end_ts=window_end_ts,
            window_seconds=window_seconds,
            quality_score=quality_score,
            binance_price_at_entry=binance_price_at_entry,
            entry_delta_pct=entry_delta_pct,
            entry_lag_pct=entry_lag_pct,
            entry_fair_value=entry_fair_value,
            is_bond=is_bond,
            bond_exit_sec=bond_exit_sec,
            bond_outcome_direction=bond_outcome_direction,
            bond_entry_class=bond_entry_class,
            bond_macro_regime=bond_macro_regime,
        )
        self.open_positions[token_id] = pos
        self._pending_assets.discard(asset)  # fill confirmed — release lock
        if condition_id:
            self._traded_conditions.add(condition_id)
        logger.info(
            "OPEN %s %s @ %.4f | stake=$%.2f | TP=%.4f SL=%.4f",
            direction.name, asset, entry_price, stake,
            tpsl.take_profit, tpsl.stop_loss,
        )
        self._save_positions()
        return pos

    def add_to_position(
        self,
        token_id: str,
        add_shares: float,
        add_fill_price: float,
        add_stake: float,
    ) -> bool:
        """
        Mid-trade scale-up: merge an additional fill into an existing position.

        Updates entry_price to a share-weighted blended average so PnL math
        remains correct at close (close uses entry_price * remaining_shares
        and a single fee_rate based on exit price). TP/SL are kept unchanged —
        they are absolute prices set at the original entry, and the add-on
        rides them through. highest_price/lowest_price are NOT reset because
        MFE/MAE diagnostics measure the trade lifecycle, not the add-on.

        Args:
          token_id        — must already be in self.open_positions
          add_shares      — shares actually filled by market_buy
          add_fill_price  — average fill price of the add-on
          add_stake       — actual capital spent on the add-on (USD)

        Returns True if the merge applied, False if the position is missing
        or the inputs are non-positive.
        """
        pos = self.open_positions.get(token_id)
        if pos is None or add_shares <= 0 or add_fill_price <= 0:
            return False

        prev_shares = pos.shares
        prev_entry = pos.entry_price
        prev_stake = pos.stake

        # Share-weighted blended entry: (orig_cost + add_cost) / total_shares.
        # Use price * shares for cost basis (not stake, which includes any
        # entry slippage we already booked).
        new_total_shares = prev_shares + add_shares
        blended_entry = (
            (prev_entry * prev_shares + add_fill_price * add_shares) / new_total_shares
            if new_total_shares > 0 else prev_entry
        )

        pos.entry_price = blended_entry
        pos.shares = new_total_shares
        pos.remaining_shares = pos.remaining_shares + add_shares
        pos.stake = prev_stake + add_stake

        logger.info(
            "POSITION_SCALED %s/%s | +%.4f @ %.4f (+$%.2f) | "
            "shares: %.4f → %.4f | entry: %.4f → %.4f | stake: $%.2f → $%.2f | "
            "TP/SL kept: %.4f / %.4f",
            pos.asset, pos.direction.name,
            add_shares, add_fill_price, add_stake,
            prev_shares, pos.shares,
            prev_entry, pos.entry_price,
            prev_stake, pos.stake,
            pos.tp, pos.sl,
        )
        self._save_positions()
        return True

    def record_stage1_sell(self, token_id: str, shares_sold: float, sell_price: float = 0.0) -> None:
        """Called after stage-1 sell. Updates remaining shares and saves actual fill price.
        sell_price: weighted average fill price from cascade_sell — saved for crash recovery.
        Only marks STAGE_1_DONE when shares were actually sold — prevents
        the position from entering stage-2 logic if the cascade failed (0 fills).
        """
        pos = self.open_positions.get(token_id)
        if pos:
            pos.remaining_shares = max(0.0, pos.remaining_shares - shares_sold)
            if shares_sold > 0:
                pos.exit_stage = ExitStage.STAGE_1_DONE
                if sell_price > 0:
                    pos.stage1_sell_price = sell_price
            logger.info(
                "STAGE-1 SELL %s | sold=%.4f @ %.4f remaining=%.4f",
                token_id[:8], shares_sold, sell_price, pos.remaining_shares,
            )
            # Persist immediately — if bot crashes before stage-2, we must not
            # re-attempt to sell the already-sold 60% on restart.
            # stage1_sell_price is also persisted — enables recovery record on next startup.
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

        # Track closed token for re-entry guard (120s cooldown)
        if not hasattr(self, "_recently_closed_tokens"):
            self._recently_closed_tokens = {}
        self._recently_closed_tokens[token_id] = time.time()

        # Condition stays in _traded_conditions after close — prevents re-entry
        # into the same window within a session. Each window has a unique condition_id
        # so this never blocks a future window on the same asset.

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
        ext=None,   # Optional ExternalSignal — used for VPIN-aware Stage 2 hold + SL extension
        binance_spot: float = 0.0,  # current Binance spot price for reversal detection
    ) -> Optional[ExitDecision]:
        """
        Evaluates all exit rules in priority order.
        Returns ExitDecision or None if no exit warranted.

        Priority:
          1. Hard-exit timer (unconditional)
          2. Window expiry guard
          3. Stage-1 profit: +25 % with 2.5s confirmation → sell 60 %
          4. Stage-2 profit: +45 % (on remaining 40 %)
          5. Stage-2 floor: remaining at cost+15 %
          6. Trailing stop (after stage-1): 20 % below peak
          7. Dynamic SL — Risk Matrix
             - Unified wick guard: 60s at -35% (CB zone), 20s at -20% (SL zone)
             - Instant at both levels when remaining ≤ 120s
             - Last 2 min: -10% → instant
        """
        pos = self.open_positions.get(token_id)
        if not pos:
            return None

        now = time.time()
        time_held = now - pos.open_ts
        remaining = pos.window_end_ts - now if pos.window_end_ts > 0 else 999

        # ── Phase detection (3-phase exit architecture) ──────────────────────
        # Phase 1 (0–30s):    Immunity Zone  — soft exits disabled, catastrophic stop only
        # Phase 2 (31–120s):  Confirmation   — SIGNAL_FLIPPED requires 5s continuous confirmation
        # Phase 3 (121–210s): Alpha Decay    — normal ops, hard close at max_trade_duration
        _phase = 1 if time_held < self.exec_cfg.min_hold_seconds else (
            2 if time_held < 120.0 else 3
        )

        # Track price range + time to peak/trough from open
        if current_price > pos.highest_price:
            pos.highest_price = current_price
            pos.highest_price_ts = now - pos.open_ts
        if current_price < pos.lowest_price:
            pos.lowest_price = current_price
            pos.lowest_price_ts = now - pos.open_ts
            # Reset 10s bounce window on every new low
            pos.mae_bounce_peak = current_price
            pos.mae_bounce_start_ts = now
        elif (pos.mae_bounce_start_ts > 0
              and (now - pos.mae_bounce_start_ts) <= 10.0
              and current_price > pos.mae_bounce_peak):
            pos.mae_bounce_peak = current_price

        # move_pct > 0 means profit for both directions
        move_pct = (current_price - pos.entry_price) / pos.entry_price

        # ── 1. Hard-exit timer (Phase 3: flat max_trade_duration) ────────────
        # 3-phase architecture: hard close at max_trade_duration (120s).
        # PM repricing is statistically complete within 120s — holding longer
        # is alpha decay, not alpha capture.
        # 15m SNI exception: 720s hard exit — 240s exited mid-window when
        # 10+ min of resolution time remained (2026-04-16: saved 2 losses).
        _hard_exit_limit = (
            720 if pos.window_seconds >= 900 and not pos.is_bond
            else self.exec_cfg.max_trade_duration
        )
        _ec = getattr(pos, "bond_entry_class", "")
        if (
            time_held >= _hard_exit_limit
            and not pos.hard_exit_triggered
            and not _ec.startswith("WEATHER_")
            and _ec != "SPORTS_COPY"
        ):
            pos.hard_exit_triggered = True
            return ExitDecision(True, "HARD_EXIT", urgency="immediate")

        # ── 2. Window expiry guard ─────────────────────────────────────────────
        # Fire when entering the final no_trade_last_sec window OR when window has
        # already passed (remaining <= 0). The original `0 < remaining` check meant
        # positions stayed open forever once the window expired mid-session.
        #
        # Min-hold gate: entry gate uses `< no_trade_last_sec` (strict) while this
        # exit uses `<=` (inclusive). A position entered at remaining=46s opens at
        # ~44s after order latency — EXIT_WINDOW_END then fires on the very next
        # OB scan, producing a 1-2s hold before Phase 1 immunity even starts.
        # Fix: suppress EXIT_WINDOW_END for the first min_hold_seconds after open.
        # Exception: let it fire immediately when remaining ≤ 5s (window truly ending).
        # BOND positions never use EXIT_WINDOW_END — they have _bond_precise_timer.
        if pos.window_end_ts > 0 and remaining <= self.exec_cfg.no_trade_last_sec:
            if pos.is_bond:
                pass  # BOND exits via _bond_precise_timer at T-bond_exit_sec
            elif now - pos.open_ts < self.exec_cfg.min_hold_seconds and remaining > 5:
                logger.debug(
                    "EXIT_WINDOW_END suppressed for %s/%s — only %.1fs held "
                    "(min %.0fs before window exit fires)",
                    pos.asset, pos.direction.name, now - pos.open_ts,
                    self.exec_cfg.min_hold_seconds,
                )
            else:
                return ExitDecision(True, "EXIT_WINDOW_END", urgency="immediate")

        # ── 2b. Bond cascade abort — Rule B (T+60s trajectory classifier) ──────
        # cascade_state is written once when BOTH snaps are populated and frozen.
        # Re-evaluation on subsequent ticks is skipped — prevents non-deterministic
        # exits from snap update lag (field-gated would retrigger on every tick).
        # P(cascade | Rule B fires) ≈ 0.85; P(recovery | snap30<-5, winner) = 0.79.
        # WEATHER_ARB excluded: multi-hour holds; snap30/60 noise is irrelevant.
        if pos.is_bond and not getattr(pos, "bond_entry_class", "").startswith("WEATHER_"):
            time_held = now - pos.open_ts

            # CAS_LOWASK: fire cascade check at T+30s (T+60s = resolution, too late).
            # cascade_detected() handles the CAS_LOWASK snap30 < -5% rule internally.
            if (pos.bond_entry_class == "CAS_LOWASK"
                    and pos.cascade_state == "UNKNOWN"
                    and time_held >= 30
                    and pos.entry_snap_30s_pct != 0.0):
                from analytics.regime_filter import cascade_detected
                _abort, _abort_reason = cascade_detected(
                    pos.entry_snap_30s_pct,
                    None,
                    "CAS_LOWASK",
                )
                pos.cascade_state = "CASCADING" if _abort else "RECOVERING"
                if _abort:
                    logger.info(
                        "CAS ABORT snap30 %s/%s @ %.4f | held=%.0fs | snap30=%.1f%%",
                        pos.asset, pos.direction.name, current_price, time_held,
                        pos.entry_snap_30s_pct,
                    )
                    return ExitDecision(True, _abort_reason, urgency="immediate")

            if pos.cascade_state == "CASCADING":
                return ExitDecision(
                    True,
                    f"BOND_ABORT_CASCADE: {pos.bond_entry_class or '?'} (state=CASCADING)",
                    urgency="immediate",
                )
            if (pos.cascade_state == "UNKNOWN"
                    and time_held >= 60
                    and pos.entry_snap_30s_pct != 0.0
                    and pos.entry_snap_60s_pct != 0.0):
                from analytics.regime_filter import cascade_detected
                _abort, _abort_reason = cascade_detected(
                    pos.entry_snap_30s_pct,
                    pos.entry_snap_60s_pct,
                    pos.bond_entry_class or None,
                )
                pos.cascade_state = "CASCADING" if _abort else "RECOVERING"
                if _abort:
                    logger.info(
                        "CASCADE ABORT %s/%s @ %.4f | held=%.0fs | snap30=%.1f%% snap60=%.1f%%",
                        pos.asset, pos.direction.name, current_price, time_held,
                        pos.entry_snap_30s_pct, pos.entry_snap_60s_pct,
                    )
                    return ExitDecision(True, _abort_reason, urgency="immediate")
                logger.info(
                    "CASCADE RECOVERING %s/%s | snap30=%.1f%% snap60=%.1f%% — hold",
                    pos.asset, pos.direction.name,
                    pos.entry_snap_30s_pct, pos.entry_snap_60s_pct,
                )

        # All WEATHER_* and UPDOWN: hold to resolution (1.0 or 0.0).
        # All intraday profit and stop exits (Stage-1, Moon Bag, Ratchet, signal-flip, etc.)
        # are wrong for multi-hour daily-resolution markets. Managed by weather_arb._monitor_positions.
        if getattr(pos, "bond_entry_class", "").startswith("WEATHER_") or getattr(pos, "bond_entry_class", "") == "UPDOWN":
            return None

        # ── 3. Stage-1 profit: 60% of fair-value gap ────────────────────────────
        # Thesis: we entered because PM hasn't priced in the Binance move.
        # TP1 = entry + 60% of (FV - entry) — take partial profits at 60% of gap closed.
        # Fallback to time-based if entry_fair_value not stored (old positions).
        if pos.exit_stage == ExitStage.NONE:
            # Flat pt_objective (22%) — edge is used as an entry filter, not a TP cap.
            # Once in the trade, Patient Sniper carries to the statistical peak.
            profit1_pct = self.exec_cfg.pt_objective

            if move_pct >= profit1_pct:
                if pos.window_end_ts > 0:
                    return ExitDecision(True, "PROFIT_1", partial=True, urgency="cascade")
                if pos.profit_trigger_ts == 0.0:
                    pos.profit_trigger_ts = now
                    return None
                if now - pos.profit_trigger_ts >= 2.5:
                    return ExitDecision(True, "PROFIT_1", partial=True, urgency="cascade")
                return None
            else:
                pos.profit_trigger_ts = 0.0

        # ── 4. Stage-2: Moon Bag ─────────────────────────────────────────────
        # After Stage-1 (60% sold at +22%), the remaining 40% rides with a
        # 15% trailing stop from the highest price seen since Stage-1.
        # This protects against manufactured wicks while still riding real runs.
        _MOON_BAG_TRAIL = 0.15

        if pos.exit_stage == ExitStage.STAGE_1_DONE:
            # Track post-Stage-1 high
            if current_price > pos.moon_bag_high:
                pos.moon_bag_high = current_price

            # Use entry_price as baseline if moon_bag_high not yet set
            _trail_ref = pos.moon_bag_high if pos.moon_bag_high > 0 else current_price
            _trail_floor = _trail_ref * (1 - _MOON_BAG_TRAIL)

            # Exit 1: token approaching resolution value (0.82+)
            if current_price >= 0.82:
                logger.info(
                    "MOON_BAG_TP %s/%s @ %.4f ≥ 0.82 near-resolution — closing moon bag",
                    pos.asset, pos.direction.name, current_price,
                )
                return ExitDecision(True, "MOON_BAG_TP", urgency="cascade")

            # Exit 2: 15% trailing stop from post-Stage-1 high
            # 3s confirmation required — prevents single manufactured wick from triggering
            # (trade 16: +26.2% peak → wick to -52.5% in 9s → MOON_BAG_TRAIL fired immediately)
            _MOON_BAG_TRAIL_CONFIRM_S = 3.0
            if current_price <= _trail_floor:
                if pos.moon_bag_trail_breach_ts == 0.0:
                    pos.moon_bag_trail_breach_ts = now
                    logger.info(
                        "MOON_BAG_TRAIL breach pending %s/%s @ %.4f — %.1f%% below high %.4f "
                        "(floor %.4f) — waiting %.1fs confirmation",
                        pos.asset, pos.direction.name, current_price,
                        (1 - current_price / _trail_ref) * 100, _trail_ref, _trail_floor,
                        _MOON_BAG_TRAIL_CONFIRM_S,
                    )
                elif now - pos.moon_bag_trail_breach_ts >= _MOON_BAG_TRAIL_CONFIRM_S:
                    logger.info(
                        "MOON_BAG_TRAIL %s/%s @ %.4f — %.1f%% below high %.4f (floor %.4f) "
                        "confirmed %.1fs",
                        pos.asset, pos.direction.name, current_price,
                        (1 - current_price / _trail_ref) * 100, _trail_ref, _trail_floor,
                        now - pos.moon_bag_trail_breach_ts,
                    )
                    return ExitDecision(True, "MOON_BAG_TRAIL", urgency="cascade")
            else:
                if pos.moon_bag_trail_breach_ts > 0.0:
                    logger.debug(
                        "MOON_BAG_TRAIL breach cancelled %s/%s — price %.4f recovered above floor %.4f",
                        pos.asset, pos.direction.name, current_price, _trail_floor,
                    )
                pos.moon_bag_trail_breach_ts = 0.0

            # Exit 3: 60s before window close — don't hold into resolution uncertainty
            if pos.window_end_ts > 0 and remaining <= 60:
                logger.info(
                    "MOON_BAG_WINDOW %s/%s @ %.4f — 60s before window close (%.0fs remaining)",
                    pos.asset, pos.direction.name, current_price, remaining,
                )
                return ExitDecision(True, "MOON_BAG_WINDOW", urgency="cascade")

            return None

        # ── 6b. LLM-tightened stop (set via advise_exit TIGHTEN_STOP) ──────────
        # When the exit advisor tightens the stop, this overrides the wide 35% SL.
        # e.g. dynamic_sl_override=0.05 → exit if price drops below entry * 0.95
        # (protecting a +8% profit from reversing below breakeven)
        if pos.dynamic_sl_override > 0 and time_held >= 10:
            tight_price = pos.entry_price * (1 - pos.dynamic_sl_override)
            if current_price <= tight_price:
                return ExitDecision(True, f"LLM_TIGHT_SL({pos.dynamic_sl_override:.0%})", urgency="immediate")

        # ── 6c. Ratchet Stop-Loss Escalator ──────────────────────────────────────
        # One-way upward ratchet — floor only moves up, never down.
        # 3-tier system — every tier locks in PROFIT (not breakeven/loss):
        #   +18% sustained 3s  → floor at +8%   (was: +15% → floor at -4% to -1% = LOSS)
        #   +28% sustained 3s  → floor at +15%  (was: +25% → floor at +10%)
        #   +40% sustained 3s  → floor at +25%  (new tier — protect large gains)
        #
        # 3s confirmation: price must STAY above a tier for 3s before floor locks.
        # Prevents wick-triggered locks (a 1s spike to +18% then instant reversal
        # used to lock the floor below entry, guaranteeing a loss on exit).
        #
        # Data basis: n=540 RATCHET_SL WR=15.8%, net=-$15.4k. Root cause:
        # old +15%→floor@entry*0.96 = floor BELOW entry. 84% of exits were at loss
        # despite price falling further after (confirmed correct direction).
        # Fix: all floors now yield a profit if triggered.
        _move_pct_raw = (current_price - pos.entry_price) / pos.entry_price

        # Tier definitions: (trigger_pct, floor_pct) — both as fractions
        _RATCHET_TIERS = [
            (0.40, 0.25),  # +40% seen → lock at +25%
            (0.28, 0.15),  # +28% seen → lock at +15%
            (0.18, 0.08),  # +18% seen → lock at +8%
        ]
        _RATCHET_CONFIRM_S = 3.0  # seconds price must sustain above trigger before floor locks

        _next_trigger = None
        for trigger, floor in _RATCHET_TIERS:
            _floor_price = pos.entry_price * (1 + floor)
            if _move_pct_raw >= trigger and pos.ratchet_sl < _floor_price:
                _next_trigger = (trigger, floor, _floor_price)
                break  # highest applicable tier — stop here

        if _next_trigger:
            trigger, floor, _floor_price = _next_trigger
            if pos.ratchet_lock_ts == 0.0:
                pos.ratchet_lock_ts = now
                logger.debug(
                    "RATCHET PENDING %s/%s | +%.0f%% @ %.4f — waiting %.1fs to lock floor at +%.0f%% (%.4f)",
                    pos.asset, pos.direction.name, trigger * 100, current_price,
                    _RATCHET_CONFIRM_S, floor * 100, _floor_price,
                )
            elif now - pos.ratchet_lock_ts >= _RATCHET_CONFIRM_S:
                _confirmed_for = now - pos.ratchet_lock_ts
                pos.ratchet_sl = _floor_price
                pos.ratchet_lock_ts = 0.0  # reset confirmation timer for next tier
                logger.info(
                    "RATCHET LOCK %s/%s | +%.0f%% confirmed %.1fs → floor locked at +%.0f%% (%.4f)",
                    pos.asset, pos.direction.name, trigger * 100,
                    _confirmed_for, floor * 100, pos.ratchet_sl,
                )
        else:
            # Price no longer above the pending trigger — cancel pending lock (wick)
            if pos.ratchet_lock_ts > 0.0:
                logger.debug(
                    "RATCHET WICK %s/%s — price %.4f fell below pending trigger before %.1fs confirm; lock cancelled",
                    pos.asset, pos.direction.name, current_price, _RATCHET_CONFIRM_S,
                )
            pos.ratchet_lock_ts = 0.0

        _RATCHET_EXIT_CONFIRM_S = 3.0  # require 3s sustained breach before exiting — prevents single-tick wicks
        if pos.ratchet_sl > 0 and current_price <= pos.ratchet_sl:
            _locked_profit_pct = (pos.ratchet_sl - pos.entry_price) / pos.entry_price * 100
            if pos.ratchet_exit_breach_ts == 0.0:
                pos.ratchet_exit_breach_ts = now
                logger.info(
                    "RATCHET_SL breach pending %s/%s @ %.4f ≤ floor %.4f (+%.1f%% locked) "
                    "— waiting %.1fs confirmation",
                    pos.asset, pos.direction.name, current_price, pos.ratchet_sl,
                    _locked_profit_pct, _RATCHET_EXIT_CONFIRM_S,
                )
            elif now - pos.ratchet_exit_breach_ts >= _RATCHET_EXIT_CONFIRM_S:
                logger.info(
                    "RATCHET EXIT %s/%s @ %.4f ≤ floor %.4f (+%.1f%% locked) confirmed %.1fs",
                    pos.asset, pos.direction.name, current_price, pos.ratchet_sl,
                    _locked_profit_pct, now - pos.ratchet_exit_breach_ts,
                )
                return ExitDecision(True, "RATCHET_SL", urgency="immediate")
        else:
            if pos.ratchet_exit_breach_ts > 0.0:
                logger.debug(
                    "RATCHET_SL breach cancelled %s/%s — price %.4f recovered above floor %.4f",
                    pos.asset, pos.direction.name, current_price, pos.ratchet_sl,
                )
            pos.ratchet_exit_breach_ts = 0.0

        # ── 7. Velocity SL — CTF V2 Speed Rules (2026-04-09, Binance-aware 2026-04-10) ─
        # Hope-based guards eliminated. Live data: 50–80% stake loss waiting for
        # recoveries that never come on the new exchange speed.
        #
        # Binance reversal detection: if Binance spot has moved > 0.10% against our
        # entry direction, the original signal premise is dead. Timers tighten.
        # binance_reversal_count increments each check cycle (~1s) Binance is reversed;
        # resets to 0 on recovery. Counters below are in check cycles (≈ seconds).
        #
        # Rule 0 : Price floor 0.20          → instant, always
        # Rule -1: Binance early exit         → 15 counts (no SL threshold needed)
        # Rule 1 : -25% VELOCITY              → reversed=6, flat=32, confirmed=10 counts (sole owner below -25%)
        # Rule 2 : -15% SL_15S               → reversed=7, flat=25, confirmed=15 counts (only active -15% to -25%)
        #
        # Three Binance states during a drawdown:
        #   REVERSED  (|move| > 0.10% against us) — signal dead, tighten timers
        #   FLAT      (|move| < 0.03% either way) — PM-specific move (stop-hunt?), extend timers
        #   CONFIRMED (|move| > 0.10% with us)    — real Binance-driven move, normal timers
        # Only valid when binance_price_at_entry > 0; otherwise treat as CONFIRMED (unknown).

        # ── Binance state flags (computed once, used by all rules) ───────────────
        # Threshold: 0.001 fraction = 0.10% = 10 basis points.
        # Stricter than 15m entry delta (0.07%) to avoid false reversal exits.
        # Matches 5m entry delta (_DELTA_PCT_ACTIVE = 0.10 in plain-% units).
        _BINANCE_REVERSAL_THRESHOLD = 0.001   # 0.10% as fraction — do not lower below entry delta
        _BINANCE_FLAT_THRESHOLD = 0.0003      # 0.03% as fraction — below this = Binance flat (PM-specific move)
        _binance_reversed = False
        _binance_flat = False
        if binance_spot > 0 and pos.binance_price_at_entry > 0:
            _b_move = (binance_spot - pos.binance_price_at_entry) / pos.binance_price_at_entry
            # BUY_NO: entered on asset going DOWN — reversal = Binance now going UP
            # BUY_YES: entered on asset going UP  — reversal = Binance now going DOWN
            if pos.direction.name == "BUY_NO":
                _binance_reversed = _b_move > _BINANCE_REVERSAL_THRESHOLD
            else:
                _binance_reversed = _b_move < -_BINANCE_REVERSAL_THRESHOLD
            # Flat: Binance barely moved while PM dropped — no Binance backing for the move.
            # Likely a PM-specific liquidity event (stop-hunting wick). Extend timer.
            # Only meaningful when we have a valid entry spot price.
            _binance_flat = not _binance_reversed and abs(_b_move) < _BINANCE_FLAT_THRESHOLD
            logger.debug(
                "BINANCE CHK %s/%s spot=%.2f entry_spot=%.2f move=%+.3f%% reversed=%s flat=%s cnt=%d",
                pos.asset, pos.direction.name, binance_spot, pos.binance_price_at_entry,
                _b_move * 100, _binance_reversed, _binance_flat, pos.binance_reversal_count,
            )

        # Update reversal counter
        if _binance_reversed:
            pos.binance_reversal_count += 1
        else:
            pos.binance_reversal_count = 0

        # -1. Weather positions hold to resolution — no dynamic exits at any phase
        _entry_class = getattr(pos, "bond_entry_class", "")
        if _entry_class.startswith("WEATHER_"):
            return None

        # -2. Phase 1 immunity zone — soft exits disabled, catastrophic stop only
        # All SIGNAL_FLIPPED / VELOCITY_EXIT / SL_15S are below this return None,
        # so they are structurally unreachable during Phase 1.
        if _phase == 1:
            if move_pct <= -self.exec_cfg.catastrophic_sl_pct:
                logger.warning(
                    "CATASTROPHIC_SL %s/%s @ %.4f — %.1f%% loss exceeds %.0f%% threshold "
                    "in immunity zone (%.1fs held)",
                    pos.asset, pos.direction.name, current_price,
                    abs(move_pct) * 100, self.exec_cfg.catastrophic_sl_pct * 100, time_held,
                )
                return ExitDecision(True, "CATASTROPHIC_SL", urgency="immediate")
            # Reset soft-exit timers so they start cleanly when Phase 2 begins
            pos.sl_breach_ts = 0.0
            pos.sl_breach_price = 0.0
            pos.sl_breach_llm_queried = False
            pos.velocity_breach_ts = 0.0
            pos.signal_flip_ts = 0.0
            return None

        if current_price <= 0.20:
            logger.warning(
                "PRICE_FLOOR %s/%s @ %.4f ≤ 0.20 — instant exit",
                pos.asset, pos.direction.name, current_price,
            )
            return ExitDecision(True, "PRICE_FLOOR", urgency="immediate")

        # -1. Signal-flipped exit — original entry premise reversed on both axes
        #
        # Fires when BOTH conditions are true simultaneously:
        #   A) Delta flipped: Binance has moved against our direction by >= entry_delta_pct
        #      = the Binance move that justified entry has been fully retraced and inverted
        #   B) Lag inverted: PM token price < (2 * entry_price - entry_fair_value)
        #      = PM has moved against us by as much as the entry lag implied it would move for us
        #      = the lag opportunity has fully closed and inverted
        #
        # Both required — delta alone is noisy (Binance wicks), lag alone is noisy (PM wicks).
        # Together they confirm the signal is structurally dead, not just temporarily drawdown.
        #
        # Falls back to delta-only check if entry_fair_value not stored (legacy positions).
        _signal_flipped = False
        if binance_spot > 0 and pos.binance_price_at_entry > 0 and pos.entry_delta_pct > 0:
            # A) Delta check — Binance has reversed past the entry threshold
            # entry_delta_pct is stored as a fraction (e.g. 0.0013 = 0.13%)
            if pos.direction.name == "BUY_NO":
                _delta_flipped = _b_move > pos.entry_delta_pct   # Binance recovered above entry threshold
            else:
                _delta_flipped = _b_move < -pos.entry_delta_pct  # Binance dropped below entry threshold

            # B) Lag inversion check — PM moved against us by as much as the lag said it would move for us
            # lag_inversion_price = 2 * entry_price - entry_fair_value
            # e.g. entry=0.50, fv=0.70 → inversion at 0.30 (PM has moved -20% against us = equal & opposite)
            if pos.entry_fair_value > 0:
                _lag_inversion_price = 2 * pos.entry_price - pos.entry_fair_value
                _lag_inverted = current_price <= _lag_inversion_price
            else:
                # Legacy position: no fair value stored — use entry_lag_pct as proxy
                # PM dropped by more than (entry_lag_pct * entry_price) against us
                _lag_inversion_price = pos.entry_price * (1 - pos.entry_lag_pct) if pos.entry_lag_pct > 0 else 0
                _lag_inverted = _lag_inversion_price > 0 and current_price <= _lag_inversion_price

            _signal_flipped = _delta_flipped and _lag_inverted

        if _signal_flipped:
            # Both Phase 2 and Phase 3: require signal_flip_delay continuous confirmation.
            # Data shows Phase 3 false positives too (trades at 130-180s recovering +30%+ after exit).
            # The 5s delay filters manufactured wicks in both phases.
            if pos.signal_flip_ts == 0.0:
                pos.signal_flip_ts = now
                logger.info(
                    "SIGNAL_FLIPPED pending %s/%s @ %.4f — waiting %.1fs confirmation "
                    "(phase=%d, %.1fs held)",
                    pos.asset, pos.direction.name, current_price,
                    self.exec_cfg.signal_flip_delay, _phase, time_held,
                )
            elif now - pos.signal_flip_ts >= self.exec_cfg.signal_flip_delay:
                logger.warning(
                    "SIGNAL_FLIPPED %s/%s @ %.4f — delta reversed (binance %+.3f%% vs entry_delta %.3f%%) "
                    "AND lag inverted (price %.4f ≤ inversion %.4f) confirmed %.1fs (phase=%d)",
                    pos.asset, pos.direction.name, current_price,
                    _b_move * 100, pos.entry_delta_pct * 100,
                    current_price, _lag_inversion_price, now - pos.signal_flip_ts, _phase,
                )
                return ExitDecision(True, "SIGNAL_FLIPPED", urgency="immediate")
        else:
            if pos.signal_flip_ts > 0.0:
                logger.debug("SIGNAL_FLIPPED reset %s/%s — condition no longer true after %.1fs",
                             pos.asset, pos.direction.name, now - pos.signal_flip_ts)
            pos.signal_flip_ts = 0.0

        # SPORTS_COPY exits via mirror-sell + 50% stop only — skip all price-action SLs.
        if getattr(pos, "bond_entry_class", "") == "SPORTS_COPY":
            return None

        # 1. -25% emergency brake: reversed=6, flat=32, confirmed=10 cycles
        # Sole owner of exit logic when price is below -25%. SL_15S is suspended here.
        _below_25pct = current_price <= pos.entry_price * 0.75
        if _below_25pct:
            # Suspend SL_15S while VELOCITY owns this depth — reset its timer so it
            # starts fresh if price recovers back into the -15% to -25% band.
            if pos.sl_breach_ts > 0.0:
                pos.sl_breach_ts = 0.0
                pos.sl_breach_price = 0.0
                pos.sl_breach_llm_queried = False
            _velocity_threshold = 6 if _binance_reversed else (32 if _binance_flat else 18)
            if pos.velocity_breach_ts == 0.0:
                pos.velocity_breach_ts = now
                logger.info(
                    "VELOCITY BREACH %s/%s @ %.4f (entry=%.4f -25%%) — threshold=%d cycles reversed=%s flat=%s",
                    pos.asset, pos.direction.name, current_price, pos.entry_price,
                    _velocity_threshold, _binance_reversed, _binance_flat,
                )
            _t_below = now - pos.velocity_breach_ts
            if _t_below >= _velocity_threshold:
                logger.warning(
                    "VELOCITY_EXIT %s/%s @ %.4f — %.1fs elapsed threshold=%d reversed=%s flat=%s",
                    pos.asset, pos.direction.name, current_price,
                    _t_below, _velocity_threshold, _binance_reversed, _binance_flat,
                )
                return ExitDecision(True, "VELOCITY_EXIT", urgency="immediate")
        else:
            if pos.velocity_breach_ts > 0.0:
                logger.debug("VELOCITY RESET %s/%s — recovered above -25%%",
                             pos.asset, pos.direction.name)
            pos.velocity_breach_ts = 0.0

        # 2. -15% hard ceiling: reversed=7, flat=25, confirmed=15 cycles
        # Only active when price is between -15% and -25%. VELOCITY_EXIT owns below -25%.
        _below_15pct = current_price <= pos.entry_price * 0.85
        if _below_15pct and not _below_25pct:
            _sl_threshold = 7 if _binance_reversed else (25 if _binance_flat else 22)
            if pos.sl_breach_ts == 0.0:
                pos.sl_breach_ts = now
                pos.sl_breach_price = current_price
                logger.info(
                    "SL_15S BREACH %s/%s @ %.4f (entry=%.4f -%.0f%%) — threshold=%d cycles reversed=%s flat=%s",
                    pos.asset, pos.direction.name, current_price, pos.entry_price,
                    (1 - current_price / pos.entry_price) * 100,
                    _sl_threshold, _binance_reversed, _binance_flat,
                )
            _t_below = now - pos.sl_breach_ts
            if _t_below >= _sl_threshold:
                logger.warning(
                    "SL_15S %s/%s @ %.4f (entry=%.4f -%.0f%%) t=%.1fs threshold=%d reversed=%s flat=%s",
                    pos.asset, pos.direction.name, current_price, pos.entry_price,
                    (1 - current_price / pos.entry_price) * 100,
                    _t_below, _sl_threshold, _binance_reversed, _binance_flat,
                )
                return ExitDecision(True, "SL_15S", urgency="immediate")
            else:
                logger.debug("SL_15S guard %s/%s @ %.4f t=%.1fs/%d reversed=%s flat=%s",
                             pos.asset, pos.direction.name, current_price,
                             _t_below, _sl_threshold, _binance_reversed, _binance_flat)
        else:
            if pos.sl_breach_ts > 0.0:
                logger.debug("SL_15S reset %s/%s — recovered above -15%%",
                             pos.asset, pos.direction.name)
            pos.sl_breach_ts = 0.0
            pos.sl_breach_price = 0.0
            pos.sl_breach_llm_queried = False

        return None

    # ── Convenience ──────────────────────────────────────────────────────────

    def positions_needing_hard_exit(self) -> List[PositionMeta]:
        """Returns positions that hit the adaptive hard-exit timer or window expiry."""
        now = time.time()
        result = []
        for pos in self.open_positions.values():
            if pos.hard_exit_triggered:
                continue
            # All WEATHER_* and SPORTS_COPY are long-hold strategies (hours-days);
            # the adaptive timer is calibrated for crypto-window strategies (~210s).
            if getattr(pos, "bond_entry_class", "").startswith("WEATHER_") or getattr(pos, "bond_entry_class", "") == "SPORTS_COPY":
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
