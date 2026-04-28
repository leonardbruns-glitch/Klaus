"""
Klaus — Automated Feedback Loop
Logs every trade, detects edge drift, flags fee bleed, and surfaces
execution inefficiencies. Claude reads these outputs to propose strategy updates.

Log format: newline-delimited JSON (JSONL)
"""
from __future__ import annotations

import json
import os
import statistics
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional
import logging

from config import CONFIG
from strategy.momentum import Direction, SignalBreakdown
from execution.order_manager import Fill, OrderResult

logger = logging.getLogger("analytics")


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    # Identity
    trade_id: str
    token_id: str
    asset: str
    direction: str           # "BUY_YES" / "BUY_NO"
    market_type: str         # "updown" / "target" — needed to split strategy analysis
    ts_open: float
    ts_close: float

    # Execution
    entry_price: float
    exit_price: float
    stake: float
    shares: float
    gross_pnl: float
    fee_paid: float          # derived: gross_pnl - net_pnl (always matches bankroll)
    net_pnl: float           # authoritative: from risk manager (same number that updates bankroll)
    slippage_entry: float
    slippage_exit: float
    exit_reason: str         # TAKE_PROFIT / STOP_LOSS / HARD_EXIT / MANUAL

    # Signal source — determines which analysis section applies
    signal_source: str = "MOMENTUM"   # "SNIPER" or "MOMENTUM"

    # Momentum scorer breakdown (populated for MOMENTUM trades, zero for SNIPER)
    breakout_score: float = 0.0
    trend_score: float = 0.0
    volume_score: float = 0.0
    ob_score: float = 0.0
    intrawindow_score: float = 0.0
    composite_score: float = 0.0
    confidence: float = 0.0
    fee_zone: str = ""
    external_boost: float = 0.0
    atr_percentile: float = 0.0
    atr_current: float = 0.0
    hurst: float = 0.0

    # Window Sniper fields (populated for SNIPER trades, zero for MOMENTUM)
    sniper_delta_pct: float = 0.0     # asset % move from window open (signed)
    sniper_fair_value: float = 0.0    # sigmoid fair value at entry
    sniper_edge: float = 0.0          # fair_value - token_ask at entry
    sniper_elapsed_pct: float = 0.0   # fraction of window elapsed at entry
    sniper_side: str = ""             # "YES" or "NO" — which side of the binary was bought
    sniper_vpin: float = 0.0          # VPIN at entry (0.5=neutral, >0.60=elevated toxicity)
    sniper_llm_boost: float = 0.0     # abs(macro_boost) at entry (0=no LLM signal active)
    sniper_prearm: bool = False       # True if pre-arm triggered early entry (<25% elapsed)
    # Polymarket lag analytics — core edge thesis validation
    sniper_pm_ask_at_trigger: float = 0.0  # PM ask when Binance delta first fired
    sniper_pm_drift_at_entry: float = 0.0  # PM ask drift from trigger→entry (analytics only)
    sniper_lag_remaining: float = 0.0      # fraction of expected PM move unpriced at entry (1.0=max lag)
    quality_score: int = 0                 # pre-entry quality gate score (lag+mom+regime+vpin)
    regime: str = ""                       # market regime at entry: ACTIVE_HOT/WARM/COLD/QUIET_FLOW/DEAD
    binance_price_at_entry: float = 0.0    # Binance spot price at fill — baseline for reversal detection
    binance_reversal_count_at_exit: int = 0  # consecutive cycles Binance was reversed at exit moment

    # Window context
    window_size_s: int = 0            # 300 (5m) or 900 (15m) — key for separate analysis

    # Time enrichment
    hour_utc: int = 0                 # UTC hour at entry — for hourly performance breakdown

    # Duration
    hold_seconds: float = 0.0

    # Execution quality / thesis validation
    spot_at_entry: float = 0.0          # Binance spot price at entry (thesis: did underlying move?)
    spot_at_exit: float = 0.0           # Binance spot price at exit
    signal_to_fill_ms: float = 0.0      # ms from signal eval to fill (infra latency per trade)
    ob_depth_at_entry: float = 0.0      # total OB depth (top-5 bids+asks in shares) at entry
    pre_entry_momentum_pct: float = 0.0 # spot 1m price change at entry (momentum context)

    # Price range during hold — volatility experienced from entry to exit
    max_price_seen: float = 0.0         # highest token price observed while position was open
    min_price_seen: float = 0.0         # lowest token price observed while position was open
    max_favourable_pct: float = 0.0     # best point reached as % from entry (how much we "had")
    max_adverse_pct: float = 0.0        # worst point reached as % from entry (how deep the dip)
    t_fav_s: float = 0.0               # seconds from open to when max_favourable_pct was reached
    t_adv_s: float = 0.0               # seconds from open to when max_adverse_pct was reached
    # Bounce-from-MAE: max price increase within 10s after the last new low, as % of entry.
    # Separates reversals (fast bounce) from collapses (no bounce). Meaningful when MAE > 40%.
    mae_bounce_10s_pct: float = 0.0

    # Window resolution outcome — populated async at window_end+60s for all trades
    # Answers: did the market resolve in our predicted direction regardless of how we exited?
    window_outcome_price: float = 0.0   # token price at window resolution (0 = not yet known)
    entered_correctly: Optional[bool] = None  # True if resolution_price ≥ 0.80 (our token won)

    # LLM recommendation tracking — veto disabled, recording for validation
    llm_rec: str = ""             # "ENTER" or "SKIP" — what LLM recommended at entry
    llm_rec_conf: float = 0.0    # LLM confidence in its recommendation (0.0 if no signal)

    # Meta
    heat_check_active: bool = False
    consecutive_wins_at_entry: int = 0
    capital_before: float = 0.0
    capital_after: float = 0.0   # always capital_before + net_pnl (not bankroll snapshot)
    is_live: bool = False         # False = dry-run/stub; True = real CLOB trade
    # ── New signal fields (data collection — gates in config.signal_gates) ────
    # Signal 1: Conditional WR for (regime, window_size_s) at entry time
    cond_wr: float = 0.5          # historical WR for this condition (0.5 = no data yet)
    cond_n: int = 0               # n trades used to compute cond_wr
    # Signal 2: Liquidation cascade in last 60s at entry time
    liq_long_60s: float = 0.0    # $ of long liquidations (price pushed DOWN)
    liq_short_60s: float = 0.0   # $ of short liquidations (price pushed UP)
    # Signal 3: Funding rate at entry (annualised APR %)
    funding_rate_pct: float = 0.0 # positive=longs crowded, negative=shorts crowded
    # Signal 4: Cross-exchange divergence at entry
    coinbase_price: float = 0.0   # Coinbase spot price (0 = not available)
    cross_exchange_div_pct: float = 0.0  # (binance-coinbase)/coinbase*100
    # Signal 5: 5-second Binance velocity at entry (data collection only)
    velocity_5s_pct: float = 0.0   # % Binance price change in last 5s (positive=up, negative=down)
    move_age_s: float = 999.0      # seconds since last >0.02% Binance tick (999=no recent move)
    # Post-entry path classification (SMOOTH_RUNNER / EARLY_CHOP / DEAD_DRIFT)
    # Diagnostic label only — not used by any entry/exit rule.
    path_class: str = ""
    path_confidence: int = 0       # 0–100
    path_reason: str = ""
    entry_snap_30s_pct: float = 0.0   # token return vs entry at T+30s (0 if not captured)
    entry_snap_60s_pct: float = 0.0   # token return vs entry at T+60s (0 if not captured)
    bond_outcome_direction: str = ""  # "up" or "down" — which asset direction makes YES resolve 1
    bond_entry_class: str = ""        # BOND zone/velocity at entry e.g. "CORE/hot", "IMPULSE/hot"
    # EARLY-zone adj_edge modifier instrumentation (evaluation phase — analytics only)
    bond_delta_penalty: float = 0.0        # 0.0–0.30, proportional |delta|>0.05 soft penalty applied
    bond_weak_vel_penalty: float = 0.0     # 0.0–0.15, weak-vel sole-confirmation penalty applied
    bond_macro_regime: str = ""            # Layer-1 regime at entry: TREND_UP / TREND_DOWN / CHOP
    # Raw entry primitives — direct inputs to entry decision (analytics only)
    bond_delta_at_entry: float = 0.0       # raw _bond_delta at entry (signed %)
    bond_adj_edge_at_entry: float = 0.0    # _adjusted_edge = edge × regime_weight
    bond_vel_at_entry: float = 0.0         # velocity magnitude at entry (%/s, unsigned)
    # BOND_STAB entry-quality classification (drives pre-entry stake scaling)
    bond_stab_class: str = ""              # CLEAN / NOISY / HIGH_RISK / FATAL
    bond_stability_score: int = 0          # 0–5, count of bad quality flags
    bond_stab_xp_bad: bool = False
    bond_stab_slip_bad: bool = False
    bond_stab_delta_bad: bool = False
    bond_stab_edge_weak: bool = False
    bond_stab_vel_flat: bool = False
    # Pre-entry trajectory — what the market was doing for the 30s before entry
    bond_delta_accel_30s: float = 0.0
    bond_accel_15s: float = 0.0
    bond_edge_drift_30s: float = 0.0
    bond_accel_sustained: bool = False
    bond_has_hist: bool = False
    bond_smooth_delta_60s: float = 0.0
    bond_entry_zone: str = ""
    # pre_score (Layer 1 — strictly pre-causal, observation mode, no gating)
    pre_score: float = 0.0
    pre_score_version: str = ""
    pre_score_schema_hash: str = ""
    pre_score_validity: str = ""
    pre_score_accel:  float = 0.0
    pre_score_daccel: float = 0.0
    pre_score_edge:   float = 0.0
    pre_score_stab:   float = 0.0
    pre_score_vel:    float = 0.0
    pre_score_class:  float = 0.0
    # Non-binding LLM bond advisor shadow decision (observation only — never blocks trade)
    bond_llm_decision: str = ""    # "TAKE" or "SKIP"
    bond_llm_conf: float = 0.0     # 0.50–0.95
    bond_llm_reason: str = ""      # max 12-word explanation
    bond_llm_tp_pct: float = 0.0   # LLM's shadow take-profit % target
    bond_llm_sl_pct: float = 0.0   # LLM's shadow stop-loss % limit
    bond_llm_shadow_pnl: float = 0.0  # shadow gross P&L: what LLM would have made
    # ── TERMINAL entry observations (data collection only, no gating) ──────────
    term_vpin: float = 0.0           # VPIN at entry from Binance aggTrade
    term_spot_delta_30s: float = 0.0 # Binance spot % change in last 30s
    term_spot_delta_60s: float = 0.0 # Binance spot % change in last 60s
    term_spot_delta_5m: float = 0.0  # Binance spot % change from 5m window open
    term_ask_spread_pct: float = 0.0 # (ask - bid) / ask * 100 at entry
    term_ask_qty: float = 0.0        # shares at best ask at entry
    term_ob_imbalance: float = 0.0   # (top3_bid - top3_ask) / total; +1=buy pressure
    term_ob_depth: float = 0.0       # total size of top-3 bids + asks at entry
    term_remaining_s: float = 0.0    # seconds to window end at signal time
    term_token_delta_3s: float = 0.0   # token ask % change vs 3s ago
    term_token_delta_5s: float = 0.0   # token ask % change vs 5s ago
    term_tok_tick_count_5s: int = 0    # number of OB ticks in last 5s
    term_tok_tick_count_30s: int = 0   # distinct ask price changes in last 30s
    term_ask_stale_s: float = 999.0    # seconds since ask last changed (scan-loop)
    term_tok_decel_ratio: float = 0.0  # d5s/d30s; near 0 = momentum stalled at entry
    term_token_delta_30s: float = 0.0  # token ask % change vs 30s ago (+ = rising)
    term_token_delta_60s: float = 0.0  # token ask % change vs 60s ago (+ = rising)
    term_binance_1m_pct: Optional[float] = None  # kline-based 1m Binance momentum at entry
    term_binance_5m_pct: Optional[float] = None  # kline-based 5m Binance momentum at entry
    term_pre_snap_60s: float = 0.0   # token ask % change from 60s-before-window-close anchor
    term_pre_snap_30s: float = 0.0   # token ask % change from 30s-before-window-close anchor
    term_pre_snap_open: float = 0.0  # token ask % change from window-open anchor
    # During-hold trajectory snapshots (MFE/MAE at T+10s and T+30s after entry)
    traj_mfe_10s: float = 0.0   # max favourable % at T+10s
    traj_mae_10s: float = 0.0   # max adverse % at T+10s
    traj_mfe_30s: float = 0.0   # max favourable % at T+30s
    traj_mae_30s: float = 0.0   # max adverse % at T+30s
    price_at_t10s: Optional[float] = None  # token bid at exactly T-10s before window close


# ---------------------------------------------------------------------------
# Analytics engine
# ---------------------------------------------------------------------------

class FeedbackEngine:
    """
    Records trades and computes rolling metrics for Claude's review cycle.
    """

    def __init__(self) -> None:
        self.cfg = CONFIG.analytics
        self._ensure_log_dir()
        self._recent: deque[TradeRecord] = deque(
            maxlen=self.cfg.edge_drift_window
        )
        self._session_trades: List[TradeRecord] = []
        self._trade_counter = 0
        self.last_trade_id = ""
        self._load_history_from_file()
        self._telemetry: dict = {}  # injected from main.py before each report

    def inject_telemetry(self, connectivity: dict, order_latency: dict) -> None:
        """Called by main.py before generating report — passes live infra metrics."""
        self._telemetry = {"connectivity": connectivity, "order_latency": order_latency}

    def _ensure_log_dir(self) -> None:
        os.makedirs(self.cfg.log_dir, exist_ok=True)

    def _load_history_from_file(self) -> None:
        """
        Pre-populate _recent from trades.jsonl so generate_claude_report() has
        data immediately after a restart (not just from the current session).
        Only loads the last edge_drift_window records to keep the deque bounded.
        """
        records = self.load_trade_history()
        if not records:
            return
        # Take the most recent window's worth
        tail = records[-self.cfg.edge_drift_window:]
        loaded = 0
        for d in tail:
            try:
                # Reconstruct minimal TradeRecord from the stored dict.
                # Fields added later (e.g. external_boost) may be absent — default to 0.
                # Skip stub/dry-run records — they have wrong capital/stakes
                # and pollute strategy analysis. Filter by token_id prefix.
                if d.get("token_id", "").startswith("stub_"):
                    continue
                # ORPHAN_SELL records have no real entry data (entry_price=0.0)
                # and zero PnL — they corrupt WR/profit-factor calculations.
                if d.get("signal_source") == "ORPHAN" or d.get("exit_reason") == "ORPHAN_SELL":
                    continue

                rec = TradeRecord(
                    trade_id=d.get("trade_id", ""),
                    token_id=d.get("token_id", ""),
                    asset=d.get("asset", ""),
                    direction=d.get("direction", ""),
                    market_type=d.get("market_type", "unknown"),
                    ts_open=d.get("ts_open", 0.0),
                    ts_close=d.get("ts_close", 0.0),
                    entry_price=d.get("entry_price", 0.0),
                    exit_price=d.get("exit_price", 0.0),
                    stake=d.get("stake", 0.0),
                    shares=d.get("shares", 0.0),
                    gross_pnl=d.get("gross_pnl", 0.0),
                    fee_paid=d.get("fee_paid", 0.0),
                    net_pnl=d.get("net_pnl", 0.0),
                    slippage_entry=d.get("slippage_entry", 0.0),
                    slippage_exit=d.get("slippage_exit", 0.0),
                    exit_reason=d.get("exit_reason", ""),
                    signal_source=d.get("signal_source", "MOMENTUM"),
                    breakout_score=d.get("breakout_score", 0.0),
                    trend_score=d.get("trend_score", 0.0),
                    volume_score=d.get("volume_score", 0.0),
                    ob_score=d.get("ob_score", 0.0),
                    intrawindow_score=d.get("intrawindow_score", 0.0),
                    composite_score=d.get("composite_score", 0.0),
                    confidence=d.get("confidence", 0.0),
                    fee_zone=d.get("fee_zone", ""),
                    external_boost=d.get("external_boost", 0.0),
                    atr_percentile=d.get("atr_percentile", 0.0),
                    atr_current=d.get("atr_current", 0.0),
                    hurst=d.get("hurst", 0.0),
                    sniper_delta_pct=d.get("sniper_delta_pct", 0.0),
                    sniper_fair_value=d.get("sniper_fair_value", 0.0),
                    sniper_edge=d.get("sniper_edge", 0.0),
                    sniper_elapsed_pct=d.get("sniper_elapsed_pct", 0.0),
                    sniper_side=d.get("sniper_side", ""),
                    sniper_vpin=d.get("sniper_vpin", 0.0),
                    sniper_llm_boost=d.get("sniper_llm_boost", 0.0),
                    sniper_prearm=d.get("sniper_prearm", False),
                    sniper_pm_ask_at_trigger=d.get("sniper_pm_ask_at_trigger", 0.0),
                    sniper_pm_drift_at_entry=d.get("sniper_pm_drift_at_entry", 0.0),
                    sniper_lag_remaining=d.get("sniper_lag_remaining", 0.0),
                    quality_score=int(d.get("quality_score", 0)),
                    regime=d.get("regime", ""),
                    window_size_s=d.get("window_size_s", 0),
                    hour_utc=d.get("hour_utc", 0),
                    hold_seconds=d.get("hold_seconds", 0.0),
                    heat_check_active=d.get("heat_check_active", False),
                    consecutive_wins_at_entry=d.get("consecutive_wins_at_entry", 0),
                    capital_before=d.get("capital_before", 0.0),
                    capital_after=d.get("capital_after", 0.0),
                    is_live=d.get("is_live", False),
                    spot_at_entry=d.get("spot_at_entry", 0.0),
                    spot_at_exit=d.get("spot_at_exit", 0.0),
                    signal_to_fill_ms=d.get("signal_to_fill_ms", 0.0),
                    ob_depth_at_entry=d.get("ob_depth_at_entry", 0.0),
                    pre_entry_momentum_pct=d.get("pre_entry_momentum_pct", 0.0),
                    max_price_seen=d.get("max_price_seen", 0.0),
                    min_price_seen=d.get("min_price_seen", 0.0),
                    max_favourable_pct=d.get("max_favourable_pct", 0.0),
                    max_adverse_pct=d.get("max_adverse_pct", 0.0),
                    window_outcome_price=d.get("window_outcome_price", 0.0),
                    entered_correctly=d.get("entered_correctly", None),
                )
                self._recent.append(rec)
                if d.get("trade_id", "").startswith("T"):
                    try:
                        num = int(d["trade_id"][1:6])
                        if num > self._trade_counter:
                            self._trade_counter = num
                    except (ValueError, IndexError):
                        pass
                loaded += 1
            except Exception:
                pass
        if loaded:
            logger.info("FeedbackEngine: loaded %d historical trades from file", loaded)

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_trade(
        self,
        token_id: str,
        asset: str,
        direction: Direction,
        entry_price: float,
        exit_price: float,
        stake: float,
        shares: float,
        entry_fill: OrderResult,
        exit_fills: List[OrderResult],
        exit_reason: str,
        signal,                            # SignalBreakdown or SniperSignal
        ts_open: float,
        ts_close: float,
        capital_before: float,
        heat_check_active: bool,
        consecutive_wins: int,
        net_pnl_actual: Optional[float] = None,
        market_type: str = "unknown",
        is_live: bool = False,
        signal_source: str = "MOMENTUM",
        window_size_s: int = 0,
        spot_at_entry: float = 0.0,
        spot_at_exit: float = 0.0,
        signal_to_fill_ms: float = 0.0,
        ob_depth_at_entry: float = 0.0,
        pre_entry_momentum_pct: float = 0.0,
        llm_rec: str = "",
        llm_rec_conf: float = 0.0,
        max_price_seen: float = 0.0,
        min_price_seen: float = 0.0,
        highest_price_ts: float = 0.0,
        lowest_price_ts: float = 0.0,
        binance_price_at_entry: float = 0.0,
        binance_reversal_count_at_exit: int = 0,
        velocity_5s_pct: float = 0.0,
        move_age_s: float = 999.0,
        path_class: str = "",
        path_confidence: int = 0,
        path_reason: str = "",
        entry_snap_30s_pct: float = 0.0,
        entry_snap_60s_pct: float = 0.0,
        bond_entry_class: str = "",
        bond_outcome_direction: str = "",
        bond_macro_regime: str = "",
        mae_bounce_10s_pct: float = 0.0,
        bond_stab_class: str = "",
        bond_stability_score: int = 0,
        bond_stab_xp_bad: bool = False,
        bond_stab_slip_bad: bool = False,
        bond_stab_delta_bad: bool = False,
        bond_stab_edge_weak: bool = False,
        bond_stab_vel_flat: bool = False,
        bond_delta_accel_30s: float = 0.0,
        bond_accel_15s: float = 0.0,
        bond_edge_drift_30s: float = 0.0,
        bond_accel_sustained: bool = False,
        bond_has_hist: bool = False,
        bond_smooth_delta_60s: float = 0.0,
        bond_entry_zone: str = "",
        pre_score: float = 0.0,
        pre_score_version: str = "",
        pre_score_schema_hash: str = "",
        pre_score_validity: str = "",
        pre_score_accel: float = 0.0,
        pre_score_daccel: float = 0.0,
        pre_score_edge: float = 0.0,
        pre_score_stab: float = 0.0,
        pre_score_vel: float = 0.0,
        pre_score_class: float = 0.0,
        bond_llm_decision: str = "",
        bond_llm_conf: float = 0.0,
        bond_llm_reason: str = "",
        bond_llm_tp_pct: float = 0.0,
        bond_llm_sl_pct: float = 0.0,
        term_vpin: float = 0.0,
        term_spot_delta_30s: float = 0.0,
        term_spot_delta_60s: float = 0.0,
        term_spot_delta_5m: float = 0.0,
        term_ask_spread_pct: float = 0.0,
        term_ask_qty: float = 0.0,
        term_ob_imbalance: float = 0.0,
        term_ob_depth: float = 0.0,
        term_remaining_s: float = 0.0,
        term_token_delta_3s: float = 0.0,
        term_token_delta_5s: float = 0.0,
        term_tok_tick_count_5s: int = 0,
        term_tok_tick_count_30s: int = 0,
        term_ask_stale_s: float = 999.0,
        term_tok_decel_ratio: float = 0.0,
        term_token_delta_30s: float = 0.0,
        term_token_delta_60s: float = 0.0,
        term_binance_1m_pct: Optional[float] = None,
        term_binance_5m_pct: Optional[float] = None,
        term_pre_snap_60s: float = 0.0,
        term_pre_snap_30s: float = 0.0,
        term_pre_snap_open: float = 0.0,
        traj_mfe_10s: float = 0.0,
        traj_mae_10s: float = 0.0,
        traj_mfe_30s: float = 0.0,
        traj_mae_30s: float = 0.0,
        price_at_t10s: Optional[float] = None,
    ) -> TradeRecord:

        self._trade_counter += 1
        trade_id = f"T{self._trade_counter:05d}_{asset}_{int(ts_open)}"
        self.last_trade_id = trade_id

        # Gross PnL: token price movement × shares (always calculable)
        gross_pnl = (exit_price - entry_price) * shares

        # fee_paid: actual fees from CLOB fill reconciliation if available,
        # otherwise derive from gross - net (risk manager's estimate).
        # Priority: (1) actual Fill.fee sum from CLOB → (2) gross - net_pnl_actual
        actual_fee_from_fills = sum(
            f.fee for r in (exit_fills or []) for f in r.fills if f.fee > 0
        )
        if entry_fill and entry_fill.fills:
            actual_fee_from_fills += sum(f.fee for f in entry_fill.fills if f.fee > 0)

        # net_pnl: use risk manager's authoritative value (which includes fees and
        # matches the bankroll change exactly). Fall back to gross only if not provided.
        if net_pnl_actual is not None:
            net_pnl = net_pnl_actual
        else:
            # Legacy / dry-run fallback: estimate fees from config
            fee_rate = (
                CONFIG.fees.extreme_fee_rate
                if (exit_price < CONFIG.fees.extreme_low or exit_price > CONFIG.fees.extreme_high)
                else CONFIG.fees.middle_fee_rate
            )
            # Round-trip fee: entry notional (stake) + exit notional.
            # stake = entry_price × shares; exit_notional = exit_price × shares.
            shares_est = stake / max(entry_price, 0.01) if entry_price else 0
            exit_notional_est = exit_price * shares_est
            net_pnl = gross_pnl - (stake + exit_notional_est) * fee_rate

        if actual_fee_from_fills > 0:
            # Actual fees captured from CLOB — most accurate source
            fee_paid = actual_fee_from_fills
        else:
            # Fall back to derived: gross - net (risk manager's fee estimate)
            fee_paid = gross_pnl - net_pnl

        # Sanity check: fees are always a cost (≥ 0). Negative fee_paid means
        # net_pnl_actual was wrong (e.g. EXTERNALLY_SOLD bookkeeping bug where
        # bankroll wasn't decremented correctly). Don't corrupt analytics with it.
        if fee_paid < 0:
            import logging as _log
            _log.getLogger("feedback").warning(
                "fee_paid=%.4f < 0 for trade %s — net_pnl_actual likely wrong. "
                "Clamping to 0 to prevent analytics corruption.",
                fee_paid, trade_id,
            )
            fee_paid = 0.0

        # capital_after is always capital_before + net_pnl. Using the live bankroll
        # snapshot was wrong: if two positions close in the same cycle, the snapshot
        # includes PnL from the *other* position too.
        capital_after = capital_before + net_pnl

        # Slippage
        slippage_entry = entry_fill.slippage if entry_fill else 0.0
        exit_slippages = [r.slippage for r in exit_fills if r.slippage is not None]
        slippage_exit = statistics.mean(exit_slippages) if exit_slippages else 0.0

        # LLM shadow P&L: apply LLM's TP/SL rules to the actual price path we observed.
        # Uses max_price_seen / min_price_seen and their timestamps to determine which
        # exit condition would have triggered first. Gross only (no fee model).
        bond_llm_shadow_pnl = 0.0
        if bond_llm_decision == "TAKE" and bond_llm_tp_pct > 0 and entry_price > 0 and shares > 0:
            _shadow_tp_price = entry_price * (1.0 + bond_llm_tp_pct / 100.0)
            _shadow_sl_price = entry_price * (1.0 - bond_llm_sl_pct / 100.0) if bond_llm_sl_pct > 0 else 0.0
            _hit_tp = max_price_seen > 0 and max_price_seen >= _shadow_tp_price
            _hit_sl = _shadow_sl_price > 0 and min_price_seen > 0 and min_price_seen <= _shadow_sl_price
            if _hit_tp and _hit_sl:
                _t_tp = (highest_price_ts - ts_open) if highest_price_ts > ts_open else 9999.0
                _t_sl = (lowest_price_ts  - ts_open) if lowest_price_ts  > ts_open else 9999.0
                _shadow_exit = _shadow_tp_price if _t_tp <= _t_sl else _shadow_sl_price
            elif _hit_tp:
                _shadow_exit = _shadow_tp_price
            elif _hit_sl:
                _shadow_exit = _shadow_sl_price
            else:
                _shadow_exit = exit_price  # neither triggered — LLM held to actual exit
            bond_llm_shadow_pnl = (_shadow_exit - entry_price) * shares
        # SKIP decision → LLM didn't trade → shadow P&L stays 0.0

        # Extract signal fields — handle both SniperSignal and SignalBreakdown
        is_sniper = signal_source in ("SNIPER", "BOND", "CONTRARIAN")
        rec = TradeRecord(
            trade_id=trade_id,
            token_id=token_id,
            asset=asset,
            direction=direction.name,
            market_type=market_type,
            ts_open=ts_open,
            ts_close=ts_close,
            entry_price=entry_price,
            exit_price=exit_price,
            stake=stake,
            shares=shares,
            gross_pnl=round(gross_pnl, 4),
            fee_paid=round(fee_paid, 4),
            net_pnl=round(net_pnl, 4),
            slippage_entry=round(slippage_entry, 5),
            slippage_exit=round(slippage_exit, 5),
            exit_reason=exit_reason,
            signal_source=signal_source,
            # Momentum fields (zero for sniper trades)
            breakout_score=0.0 if is_sniper else round(getattr(signal, "breakout_score", 0.0), 3),
            trend_score=0.0 if is_sniper else round(getattr(signal, "trend_score", 0.0), 3),
            volume_score=0.0 if is_sniper else round(getattr(signal, "volume_score", 0.0), 3),
            ob_score=0.0 if is_sniper else round(getattr(signal, "ob_score", 0.0), 3),
            intrawindow_score=0.0 if is_sniper else round(getattr(signal, "intrawindow_score", 0.0), 3),
            composite_score=round(getattr(signal, "composite", 0.0), 3),
            confidence=round(getattr(signal, "confidence", 0.0), 3),
            fee_zone=signal.fee_zone.name if hasattr(signal, "fee_zone") and signal.fee_zone else "",
            external_boost=0.0 if is_sniper else round(getattr(signal, "external_boost", 0.0), 3),
            atr_percentile=0.0 if is_sniper else round(getattr(signal, "atr_percentile", 0.0), 3),
            atr_current=0.0 if is_sniper else round(getattr(signal, "atr_current", 0.0), 5),
            hurst=0.0 if is_sniper else round(getattr(signal, "hurst", 0.0), 3),
            # Sniper fields (zero for momentum trades)
            sniper_delta_pct=round(getattr(signal, "delta_pct", 0.0), 4) if is_sniper else 0.0,
            sniper_fair_value=round(getattr(signal, "fair_value", 0.0), 4) if is_sniper else 0.0,
            sniper_edge=round(getattr(signal, "edge", 0.0), 4) if is_sniper else 0.0,
            sniper_elapsed_pct=round(getattr(signal, "elapsed_pct", 0.0), 3) if is_sniper else 0.0,
            sniper_side=getattr(signal, "side", "") if is_sniper else "",
            sniper_vpin=round(getattr(signal, "vpin_at_entry", 0.0), 4) if is_sniper else 0.0,
            sniper_llm_boost=round(getattr(signal, "llm_boost_at_entry", 0.0), 4) if is_sniper else 0.0,
            sniper_prearm=bool(getattr(signal, "is_prearm", False)) if is_sniper else False,
            sniper_pm_ask_at_trigger=round(getattr(signal, "pm_ask_at_trigger", 0.0), 4) if is_sniper else 0.0,
            sniper_pm_drift_at_entry=round(getattr(signal, "pm_drift_at_entry", 0.0), 4) if is_sniper else 0.0,
            sniper_lag_remaining=round(getattr(signal, "lag_remaining_pct", 0.0), 3) if is_sniper else 0.0,
            quality_score=int(getattr(signal, "quality_score", 0)) if is_sniper else 0,
            regime=getattr(signal, "regime", ""),
            # New signal fields — extracted from SniperSignal if present, else 0
            cond_wr=round(float(getattr(signal, "cond_wr", 0.5)), 3),
            cond_n=int(getattr(signal, "cond_n", 0)),
            liq_long_60s=round(float(getattr(signal, "liq_long_60s", 0.0)), 0),
            liq_short_60s=round(float(getattr(signal, "liq_short_60s", 0.0)), 0),
            funding_rate_pct=round(float(getattr(signal, "funding_rate_pct", 0.0)), 3),
            coinbase_price=round(float(getattr(signal, "coinbase_price", 0.0)), 2),
            cross_exchange_div_pct=round(float(getattr(signal, "cross_exchange_div_pct", 0.0)), 4),
            window_size_s=window_size_s,
            hour_utc=int(time.gmtime(ts_open).tm_hour),
            hold_seconds=round(ts_close - ts_open, 1),
            spot_at_entry=round(spot_at_entry, 2),
            spot_at_exit=round(spot_at_exit, 2),
            signal_to_fill_ms=round(signal_to_fill_ms, 1),
            ob_depth_at_entry=round(ob_depth_at_entry, 2),
            pre_entry_momentum_pct=round(pre_entry_momentum_pct, 4),
            heat_check_active=heat_check_active,
            consecutive_wins_at_entry=consecutive_wins,
            capital_before=round(capital_before, 2),
            capital_after=round(capital_after, 2),
            is_live=is_live,
            llm_rec=llm_rec,
            llm_rec_conf=round(llm_rec_conf, 3),
            max_price_seen=round(max_price_seen, 4),
            min_price_seen=round(min_price_seen, 4),
            max_favourable_pct=round((max_price_seen - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0,
            max_adverse_pct=round((entry_price - min_price_seen) / entry_price * 100, 2) if entry_price > 0 else 0.0,
            t_fav_s=round(highest_price_ts, 1),
            t_adv_s=round(lowest_price_ts, 1),
            binance_price_at_entry=round(binance_price_at_entry, 2),
            binance_reversal_count_at_exit=binance_reversal_count_at_exit,
            velocity_5s_pct=round(velocity_5s_pct, 4),
            move_age_s=round(move_age_s, 1),
            path_class=path_class,
            path_confidence=path_confidence,
            path_reason=path_reason,
            entry_snap_30s_pct=round(entry_snap_30s_pct, 2),
            entry_snap_60s_pct=round(entry_snap_60s_pct, 2),
            bond_entry_class=bond_entry_class,
            bond_outcome_direction=bond_outcome_direction,
            bond_delta_penalty=round(float(getattr(signal, "bond_delta_penalty", 0.0)), 4),
            bond_weak_vel_penalty=round(float(getattr(signal, "bond_weak_vel_penalty", 0.0)), 4),
            bond_macro_regime=bond_macro_regime,
            mae_bounce_10s_pct=round(mae_bounce_10s_pct, 2),
            bond_stab_class=bond_stab_class,
            bond_stability_score=bond_stability_score,
            bond_stab_xp_bad=bond_stab_xp_bad,
            bond_stab_slip_bad=bond_stab_slip_bad,
            bond_stab_delta_bad=bond_stab_delta_bad,
            bond_stab_edge_weak=bond_stab_edge_weak,
            bond_stab_vel_flat=bond_stab_vel_flat,
            bond_delta_accel_30s=round(bond_delta_accel_30s, 4),
            bond_accel_15s=round(bond_accel_15s, 4),
            bond_edge_drift_30s=round(bond_edge_drift_30s, 4),
            bond_accel_sustained=bond_accel_sustained,
            bond_has_hist=bond_has_hist,
            bond_smooth_delta_60s=round(bond_smooth_delta_60s, 4),
            bond_entry_zone=bond_entry_zone,
            pre_score=round(pre_score, 4),
            pre_score_version=pre_score_version,
            pre_score_schema_hash=pre_score_schema_hash,
            pre_score_validity=pre_score_validity,
            pre_score_accel=round(pre_score_accel, 4),
            pre_score_daccel=round(pre_score_daccel, 4),
            pre_score_edge=round(pre_score_edge, 4),
            pre_score_stab=round(pre_score_stab, 4),
            pre_score_vel=round(pre_score_vel, 4),
            pre_score_class=round(pre_score_class, 4),
            bond_llm_decision=bond_llm_decision,
            bond_llm_conf=round(bond_llm_conf, 2),
            bond_llm_reason=bond_llm_reason,
            bond_llm_tp_pct=round(bond_llm_tp_pct, 1),
            term_vpin=round(term_vpin, 4),
            term_spot_delta_30s=round(term_spot_delta_30s, 4),
            term_spot_delta_60s=round(term_spot_delta_60s, 4),
            term_spot_delta_5m=round(term_spot_delta_5m, 4),
            term_ask_spread_pct=round(term_ask_spread_pct, 4),
            term_ask_qty=round(term_ask_qty, 2),
            term_ob_imbalance=round(term_ob_imbalance, 4),
            term_ob_depth=round(term_ob_depth, 2),
            term_remaining_s=round(term_remaining_s, 1),
            term_token_delta_3s=round(term_token_delta_3s, 4),
            term_token_delta_5s=round(term_token_delta_5s, 4),
            term_tok_tick_count_5s=int(term_tok_tick_count_5s),
            term_tok_tick_count_30s=int(term_tok_tick_count_30s),
            term_ask_stale_s=round(term_ask_stale_s, 1),
            term_tok_decel_ratio=round(term_tok_decel_ratio, 4),
            term_token_delta_30s=round(term_token_delta_30s, 4),
            term_token_delta_60s=round(term_token_delta_60s, 4),
            term_binance_1m_pct=round(term_binance_1m_pct, 4) if term_binance_1m_pct is not None else None,
            term_binance_5m_pct=round(term_binance_5m_pct, 4) if term_binance_5m_pct is not None else None,
            term_pre_snap_60s=round(term_pre_snap_60s, 4),
            term_pre_snap_30s=round(term_pre_snap_30s, 4),
            term_pre_snap_open=round(term_pre_snap_open, 4),
            traj_mfe_10s=round(traj_mfe_10s, 2),
            traj_mae_10s=round(traj_mae_10s, 2),
            traj_mfe_30s=round(traj_mfe_30s, 2),
            traj_mae_30s=round(traj_mae_30s, 2),
            price_at_t10s=round(price_at_t10s, 4) if price_at_t10s is not None else None,
            bond_llm_sl_pct=round(bond_llm_sl_pct, 1),
            bond_llm_shadow_pnl=round(bond_llm_shadow_pnl, 4),
        )

        self._recent.append(rec)
        self._session_trades.append(rec)
        self._write_jsonl(self.cfg.trade_log, asdict(rec))

        # Run diagnostics after each trade
        diag = self.run_diagnostics()
        if diag["alerts"]:
            for alert in diag["alerts"]:
                logger.warning("[FEEDBACK ALERT] %s", alert)
            self._write_jsonl(self.cfg.session_log, {"ts": time.time(), "diagnostics": diag})

        return rec

    # ── Diagnostics (Claude reads these) ─────────────────────────────────────

    def run_diagnostics(self) -> Dict:
        """
        Compute rolling metrics over the last N trades.
        Returns structured dict Claude uses to propose strategy changes.
        """
        trades = list(self._recent)
        if not trades:
            return {"alerts": [], "metrics": {}, "status": "no_data"}

        n = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]

        win_rate = len(wins) / n
        avg_win = statistics.mean([t.net_pnl for t in wins]) if wins else 0
        avg_loss = statistics.mean([abs(t.net_pnl) for t in losses]) if losses else 0
        gross_profit = sum(t.gross_pnl for t in trades)
        total_fees = sum(t.fee_paid for t in trades)
        net_profit = sum(t.net_pnl for t in trades)
        avg_slippage = statistics.mean([t.slippage_entry + t.slippage_exit for t in trades])
        avg_hold = statistics.mean([t.hold_seconds for t in trades])

        fat_middle_trades = [t for t in trades if t.fee_zone == "FAT_MIDDLE"]
        extreme_trades = [t for t in trades if t.fee_zone == "EXTREME"]

        hard_exits = [t for t in trades if t.exit_reason == "HARD_EXIT"]
        hard_exit_rate = len(hard_exits) / n

        by_asset: Dict[str, List] = {}
        for t in trades:
            by_asset.setdefault(t.asset, []).append(t.net_pnl)

        # market_type breakdown: updown vs target
        by_market_type: Dict[str, List] = {}
        for t in trades:
            by_market_type.setdefault(t.market_type, []).append(t.net_pnl)

        live_trades = [t for t in trades if t.is_live]

        # ── Signal breakdown: avg score for wins vs losses ─────────────────────
        def _avg(lst: list) -> float:
            return round(statistics.mean(lst), 3) if lst else 0.0

        sig_wins = {
            "breakout": _avg([t.breakout_score for t in wins]),
            "trend": _avg([t.trend_score for t in wins]),
            "volume": _avg([t.volume_score for t in wins]),
            "ob": _avg([t.ob_score for t in wins]),
            "intrawindow": _avg([t.intrawindow_score for t in wins]),
            "composite": _avg([t.composite_score for t in wins]),
        }
        sig_losses = {
            "breakout": _avg([t.breakout_score for t in losses]),
            "trend": _avg([t.trend_score for t in losses]),
            "volume": _avg([t.volume_score for t in losses]),
            "ob": _avg([t.ob_score for t in losses]),
            "intrawindow": _avg([t.intrawindow_score for t in losses]),
            "composite": _avg([t.composite_score for t in losses]),
        }

        # ── Regime analysis: ATR buckets + Hurst buckets ─────────────────────
        # ATR percentile buckets: low (<30%), mid (30-70%), high (>70%)
        atr_low = [t for t in trades if t.atr_percentile < 0.30]
        atr_mid = [t for t in trades if 0.30 <= t.atr_percentile <= 0.70]
        atr_high = [t for t in trades if t.atr_percentile > 0.70]

        def _wr(bucket: list) -> float:
            if not bucket:
                return 0.0
            return round(sum(1 for t in bucket if t.net_pnl > 0) / len(bucket), 3)

        regime_atr = {
            "low_pct_<0.30": {"n": len(atr_low), "wr": _wr(atr_low)},
            "mid_pct_0.30-0.70": {"n": len(atr_mid), "wr": _wr(atr_mid)},
            "high_pct_>0.70": {"n": len(atr_high), "wr": _wr(atr_high)},
            "avg_atr_pct_all": _avg([t.atr_percentile for t in trades]),
            "avg_atr_pct_wins": _avg([t.atr_percentile for t in wins]),
            "avg_atr_pct_losses": _avg([t.atr_percentile for t in losses]),
        }

        # Hurst buckets: mean-reverting (<0.45), random walk (0.45-0.55), trending (>0.55)
        hurst_mr = [t for t in trades if t.hurst < 0.45]
        hurst_rw = [t for t in trades if 0.45 <= t.hurst <= 0.55]
        hurst_tr = [t for t in trades if t.hurst > 0.55]

        regime_hurst = {
            "mean_reverting_<0.45": {"n": len(hurst_mr), "wr": _wr(hurst_mr)},
            "random_walk_0.45-0.55": {"n": len(hurst_rw), "wr": _wr(hurst_rw)},
            "trending_>0.55": {"n": len(hurst_tr), "wr": _wr(hurst_tr)},
            "avg_hurst_all": _avg([t.hurst for t in trades]),
            "avg_hurst_wins": _avg([t.hurst for t in wins]),
            "avg_hurst_losses": _avg([t.hurst for t in losses]),
        }

        # ── Intrawindow score vs outcome ──────────────────────────────────────
        iwd_low = [t for t in trades if t.intrawindow_score < 0.30]
        iwd_mid = [t for t in trades if 0.30 <= t.intrawindow_score < 0.60]
        iwd_high = [t for t in trades if t.intrawindow_score >= 0.60]

        intrawindow_buckets = {
            "iwd_weak_<0.30": {"n": len(iwd_low), "wr": _wr(iwd_low)},
            "iwd_mid_0.30-0.60": {"n": len(iwd_mid), "wr": _wr(iwd_mid)},
            "iwd_strong_>=0.60": {"n": len(iwd_high), "wr": _wr(iwd_high)},
        }

        # ── Sniper vs Momentum split ──────────────────────────────────────────
        sniper_trades = [t for t in trades if t.signal_source == "SNIPER"]
        momentum_trades = [t for t in trades if t.signal_source == "MOMENTUM"]

        def _source_stats(src_trades: list) -> dict:
            if not src_trades:
                return {"n": 0, "wr": 0.0, "net_pnl": 0.0, "avg_edge": 0.0,
                        "avg_elapsed_pct": 0.0, "avg_delta_pct": 0.0}
            sw = [t for t in src_trades if t.net_pnl > 0]
            return {
                "n": len(src_trades),
                "wr": round(len(sw) / len(src_trades), 3),
                "net_pnl": round(sum(t.net_pnl for t in src_trades), 3),
                "avg_edge": _avg([t.sniper_edge for t in src_trades if t.sniper_edge > 0]),
                "avg_elapsed_pct": _avg([t.sniper_elapsed_pct for t in src_trades if t.sniper_elapsed_pct > 0]),
                "avg_delta_pct": _avg([t.sniper_delta_pct for t in src_trades if t.sniper_delta_pct != 0]),
            }

        sniper_wins = [t for t in sniper_trades if t.net_pnl > 0]
        sniper_losses = [t for t in sniper_trades if t.net_pnl <= 0]
        sniper_edge_analysis = {
            "edge_wins":   _avg([t.sniper_edge for t in sniper_wins]),
            "edge_losses": _avg([t.sniper_edge for t in sniper_losses]),
            "elapsed_wins":   _avg([t.sniper_elapsed_pct for t in sniper_wins]),
            "elapsed_losses": _avg([t.sniper_elapsed_pct for t in sniper_losses]),
            "delta_wins":   _avg([t.sniper_delta_pct for t in sniper_wins]),
            "delta_losses": _avg([t.sniper_delta_pct for t in sniper_losses]),
            "fv_wins":   _avg([t.sniper_fair_value for t in sniper_wins]),
            "fv_losses": _avg([t.sniper_fair_value for t in sniper_losses]),
        }

        # ── 5m vs 15m window performance split ────────────────────────────────
        w5m = [t for t in trades if t.window_size_s == 300]
        w15m = [t for t in trades if t.window_size_s == 900]
        by_window = {
            "5m":  {"n": len(w5m),  "wr": _wr(w5m),  "net_pnl": round(sum(t.net_pnl for t in w5m), 3)},
            "15m": {"n": len(w15m), "wr": _wr(w15m), "net_pnl": round(sum(t.net_pnl for t in w15m), 3)},
        }

        # ── Hourly breakdown (UTC hour at entry) ──────────────────────────────
        by_hour: Dict[int, list] = {}
        for t in trades:
            by_hour.setdefault(t.hour_utc, []).append(t)
        hourly_stats = {
            h: {
                "n": len(bucket),
                "wr": _wr(bucket),
                "net_pnl": round(sum(t.net_pnl for t in bucket), 3),
            }
            for h, bucket in sorted(by_hour.items())
        }

        # ── VPIN impact (sniper trades only) ──────────────────────────────────
        vpin_none  = [t for t in sniper_trades if t.sniper_vpin < 0.55]
        vpin_elev  = [t for t in sniper_trades if 0.55 <= t.sniper_vpin < 0.70]
        vpin_high  = [t for t in sniper_trades if t.sniper_vpin >= 0.70]
        vpin_impact = {
            "no_signal_<0.55":   {"n": len(vpin_none), "wr": _wr(vpin_none)},
            "elevated_0.55-0.70": {"n": len(vpin_elev), "wr": _wr(vpin_elev)},
            "high_>=0.70":       {"n": len(vpin_high), "wr": _wr(vpin_high)},
        }

        # ── LLM boost impact (sniper trades only) ─────────────────────────────
        llm_none   = [t for t in sniper_trades if t.sniper_llm_boost < 0.05]
        llm_active = [t for t in sniper_trades if t.sniper_llm_boost >= 0.05]
        llm_impact = {
            "no_boost_<0.05":  {"n": len(llm_none),   "wr": _wr(llm_none)},
            "boosted_>=0.05":  {"n": len(llm_active), "wr": _wr(llm_active)},
        }

        # ── Pre-arm vs normal entry stats (sniper only) ───────────────────────
        prearm_trades  = [t for t in sniper_trades if t.sniper_prearm]
        normal_entries = [t for t in sniper_trades if not t.sniper_prearm]
        prearm_stats = {
            "prearm":  {"n": len(prearm_trades),  "wr": _wr(prearm_trades),
                        "net_pnl": round(sum(t.net_pnl for t in prearm_trades), 3)},
            "normal":  {"n": len(normal_entries), "wr": _wr(normal_entries),
                        "net_pnl": round(sum(t.net_pnl for t in normal_entries), 3)},
        }

        # ── YES vs NO side performance (sniper only) ──────────────────────────
        yes_trades = [t for t in sniper_trades if t.sniper_side == "YES"]
        no_trades  = [t for t in sniper_trades if t.sniper_side == "NO"]
        side_stats = {
            "YES": {"n": len(yes_trades), "wr": _wr(yes_trades),
                    "net_pnl": round(sum(t.net_pnl for t in yes_trades), 3)},
            "NO":  {"n": len(no_trades),  "wr": _wr(no_trades),
                    "net_pnl": round(sum(t.net_pnl for t in no_trades), 3)},
        }

        # ── Direction breakdown (YES_UP vs YES_DOWN, all trades) ─────────────
        # All TERMINAL trades buy YES tokens. The distinction is the market:
        # YES_UP  ("up"):   YES resolves 1 if asset price goes UP (above threshold)
        # YES_DOWN ("down"): YES resolves 1 if asset price goes DOWN (below threshold)
        # Both buy YES tokens at 0.70-0.88 and win by reaching 1.0 — same token mechanics,
        # different underlying bet. ob_imbalance and tok_d30 are identical for both
        # (positive = bid pressure on our YES token = favorable regardless of market direction).
        # spot_delta_30s differs: for YES_UP wins want positive, for YES_DOWN wins want negative.
        def _dir_stats_detail(bucket: list) -> dict:
            if not bucket:
                return {"n": 0, "wr": 0.0, "net_pnl": 0.0,
                        "avg_ob_imb_all": 0.0, "avg_ob_imb_wins": 0.0, "avg_ob_imb_losses": 0.0,
                        "avg_tok_d30": 0.0, "avg_tok_d30_wins": 0.0, "avg_tok_d30_losses": 0.0,
                        "avg_spot_d30": 0.0, "avg_spot_d30_wins": 0.0, "avg_spot_d30_losses": 0.0,
                        "avg_ask_qty": 0.0, "avg_ask_spread_pct": 0.0}
            wins_b   = [t for t in bucket if t.net_pnl > 0]
            losses_b = [t for t in bucket if t.net_pnl <= 0]
            has_term = [t for t in bucket  if t.term_ask_qty > 0 or t.term_ob_imbalance != 0]
            wins_t   = [t for t in wins_b  if t.term_ask_qty > 0 or t.term_ob_imbalance != 0]
            losses_t = [t for t in losses_b if t.term_ask_qty > 0 or t.term_ob_imbalance != 0]
            has_spot = [t for t in bucket  if t.term_spot_delta_30s != 0]
            wins_s   = [t for t in wins_b  if t.term_spot_delta_30s != 0]
            losses_s = [t for t in losses_b if t.term_spot_delta_30s != 0]
            return {
                "n": len(bucket),
                "wr": round(len(wins_b) / len(bucket), 3),
                "net_pnl": round(sum(t.net_pnl for t in bucket), 3),
                "avg_ob_imb_all":     round(_avg([t.term_ob_imbalance for t in has_term]), 4),
                "avg_ob_imb_wins":    round(_avg([t.term_ob_imbalance for t in wins_t]),   4),
                "avg_ob_imb_losses":  round(_avg([t.term_ob_imbalance for t in losses_t]), 4),
                "avg_tok_d30":        round(_avg([t.term_token_delta_30s for t in has_term]), 4),
                "avg_tok_d30_wins":   round(_avg([t.term_token_delta_30s for t in wins_t]),   4),
                "avg_tok_d30_losses": round(_avg([t.term_token_delta_30s for t in losses_t]), 4),
                "avg_spot_d30":       round(_avg([t.term_spot_delta_30s for t in has_spot]), 4),
                "avg_spot_d30_wins":  round(_avg([t.term_spot_delta_30s for t in wins_s]),   4),
                "avg_spot_d30_losses":round(_avg([t.term_spot_delta_30s for t in losses_s]), 4),
                "avg_ask_qty":        round(_avg([t.term_ask_qty for t in has_term]), 2),
                "avg_ask_spread_pct": round(_avg([t.term_ask_spread_pct for t in has_term]), 3),
            }

        yes_up_trades   = [t for t in trades if getattr(t, "bond_outcome_direction", "") == "up"]
        yes_down_trades = [t for t in trades if getattr(t, "bond_outcome_direction", "") == "down"]
        by_direction = {
            "YES_UP":   _dir_stats_detail(yes_up_trades),
            "YES_DOWN": _dir_stats_detail(yes_down_trades),
        }

        # Per-asset × outcome-direction breakdown
        by_asset_dir: Dict[str, dict] = {}
        for t in trades:
            odir = getattr(t, "bond_outcome_direction", "") or t.direction
            key = f"{t.asset}_{odir}"
            bucket = by_asset_dir.setdefault(key, {"trades": [], "asset": t.asset, "odir": odir})
            bucket["trades"].append(t)
        asset_dir_stats: Dict[str, dict] = {}
        for key, info in by_asset_dir.items():
            bkt = info["trades"]
            wins_a = [t for t in bkt if t.net_pnl > 0]
            asset_dir_stats[key] = {
                "asset": info["asset"],
                "direction": info["odir"],
                "n": len(bkt),
                "wr": round(len(wins_a) / len(bkt), 3),
                "net_pnl": round(sum(t.net_pnl for t in bkt), 3),
            }

        # ── Exit reason breakdown ─────────────────────────────────────────────
        exit_reasons: Dict[str, list] = {}
        for t in trades:
            exit_reasons.setdefault(t.exit_reason, []).append(t)
        by_exit_reason = {
            reason: {
                "n": len(bucket),
                "wr": _wr(bucket),
                "net_pnl": round(sum(t.net_pnl for t in bucket), 3),
                "avg_hold_s": round(_avg([t.hold_seconds for t in bucket]), 1),
            }
            for reason, bucket in sorted(exit_reasons.items())
        }

        # ── Lag-tier breakdown (sniper only — Kelly Criterion validation data) ──
        # lag_remaining=1.0 = PM hasn't repriced at all = MAX opportunity (best entry).
        # lag_remaining=0.0 = PM fully repriced = no edge remaining (worst entry).
        # Tiers use corrected lag direction vs friend's original proposal.
        # NOTE: analytics only — no stake changes until n>=20 per tier confirmed.
        def _tier_stats(bucket: list) -> dict:
            if not bucket:
                return {"n": 0, "wr": 0.0, "net_pnl": 0.0,
                        "avg_delta_pct": 0.0, "avg_entry_price": 0.0}
            wins_b = [t for t in bucket if t.net_pnl > 0]
            return {
                "n": len(bucket),
                "wr": round(len(wins_b) / len(bucket), 3),
                "net_pnl": round(sum(t.net_pnl for t in bucket), 3),
                "avg_delta_pct": _avg([t.sniper_delta_pct for t in bucket
                                       if t.sniper_delta_pct != 0]),
                "avg_entry_price": _avg([t.entry_price for t in bucket]),
            }

        lag_dead   = [t for t in sniper_trades if t.sniper_lag_remaining < 0.35]
        lag_std    = [t for t in sniper_trades if 0.35 <= t.sniper_lag_remaining < 0.55]
        lag_good   = [t for t in sniper_trades if 0.55 <= t.sniper_lag_remaining < 0.75]
        lag_sniper = [t for t in sniper_trades if t.sniper_lag_remaining >= 0.75]
        lag_tier_stats = {
            "nearly_repriced_<0.35":  _tier_stats(lag_dead),
            "moderate_0.35-0.55":     _tier_stats(lag_std),
            "good_0.55-0.75":         _tier_stats(lag_good),
            "max_lag_>=0.75":         _tier_stats(lag_sniper),
        }

        # ── Delta-tier breakdown (sniper only — move strength vs outcome) ────────
        # abs(delta_pct) captures move size regardless of YES/NO direction.
        delta_weak   = [t for t in sniper_trades if abs(t.sniper_delta_pct) < 0.08]
        delta_std    = [t for t in sniper_trades if 0.08 <= abs(t.sniper_delta_pct) < 0.13]
        delta_strong = [t for t in sniper_trades if abs(t.sniper_delta_pct) >= 0.13]
        delta_tier_stats = {
            "weak_<0.08pct":         _tier_stats(delta_weak),
            "standard_0.08-0.13pct": _tier_stats(delta_std),
            "strong_>=0.13pct":      _tier_stats(delta_strong),
        }

        metrics = {
            "sample_size": n,
            "live_trades": len(live_trades),
            "win_rate": round(win_rate, 3),
            "avg_win_usd": round(avg_win, 3),
            "avg_loss_usd": round(avg_loss, 3),
            "profit_factor": round(avg_win / avg_loss, 2) if avg_loss > 0 else 999,
            "gross_profit_usd": round(gross_profit, 3),
            "total_fees_usd": round(total_fees, 3),
            "net_profit_usd": round(net_profit, 3),
            "fee_bleed_pct": round(total_fees / gross_profit * 100, 1) if gross_profit > 0 else 0,
            "avg_slippage": round(avg_slippage, 5),
            "avg_hold_seconds": round(avg_hold, 1),
            "hard_exit_rate": round(hard_exit_rate, 3),
            "fat_middle_count": len(fat_middle_trades),
            "extreme_count": len(extreme_trades),
            "pnl_by_asset": {a: round(sum(v), 3) for a, v in by_asset.items()},
            "pnl_by_market_type": {m: round(sum(v), 3) for m, v in by_market_type.items()},
            # New: signal quality + regime analysis
            "signal_scores_wins": sig_wins,
            "signal_scores_losses": sig_losses,
            "regime_atr": regime_atr,
            "regime_hurst": regime_hurst,
            "intrawindow_buckets": intrawindow_buckets,
            "by_signal_source": {
                "SNIPER": _source_stats(sniper_trades),
                "MOMENTUM": _source_stats(momentum_trades),
            },
            "sniper_edge_analysis": sniper_edge_analysis,
            "by_window_size": by_window,
            "by_hour_utc": hourly_stats,
            "vpin_impact": vpin_impact,
            "llm_impact": llm_impact,
            "prearm_stats": prearm_stats,
            "side_stats": side_stats,
            "by_exit_reason": by_exit_reason,
            "by_direction": by_direction,
            "asset_dir_stats": asset_dir_stats,
            # Kelly Criterion validation data — analytics only, no stake changes yet
            "lag_tier_stats": lag_tier_stats,
            "delta_tier_stats": delta_tier_stats,
        }

        # ── Alert generation ──────────────────────────────────────────────────
        alerts = []

        if win_rate < self.cfg.min_win_rate and n >= 10:
            alerts.append(
                f"EDGE DRIFT: win_rate={win_rate:.1%} below threshold {self.cfg.min_win_rate:.1%}"
            )

        fee_bleed = metrics["fee_bleed_pct"]
        if fee_bleed > self.cfg.fee_bleed_threshold * 100 and gross_profit > 0:
            alerts.append(
                f"FEE BLEED: fees consuming {fee_bleed:.1f}% of gross profit "
                f"(threshold {self.cfg.fee_bleed_threshold*100:.0f}%)"
            )

        if avg_slippage > 0.015:
            alerts.append(
                f"SLIPPAGE WARNING: avg slippage {avg_slippage:.4f} indicates liquidity issues"
            )

        if hard_exit_rate > 0.30:
            alerts.append(
                f"HARD EXIT RATE HIGH: {hard_exit_rate:.1%} of trades hitting 180s timer — "
                "consider tightening entry conditions or reducing hold time"
            )

        if len(fat_middle_trades) > len(extreme_trades) and n >= 5:
            alerts.append(
                "FAT MIDDLE OVERWEIGHT: more fat-middle than extreme-odds trades — "
                "fee drag increasing; tighten fat-middle confidence filter"
            )

        # Per-asset underperformance
        for asset, pnl_list in by_asset.items():
            if len(pnl_list) >= 5:
                asset_win_rate = sum(1 for p in pnl_list if p > 0) / len(pnl_list)
                if asset_win_rate < 0.40:
                    alerts.append(
                        f"ASSET DRAG: {asset} win_rate={asset_win_rate:.1%} "
                        f"over last {len(pnl_list)} trades — consider pausing this market"
                    )

        # Hurst gate promotion: only valid for MOMENTUM trades — SniperSignal has no
        # hurst field, so all sniper trades have hurst=0.0, making this analysis meaningless.
        sniper_trades = [t for t in trades if t.signal_source == "SNIPER"]
        has_real_hurst = any(t.hurst > 0.0 for t in trades)
        if has_real_hurst and regime_hurst["mean_reverting_<0.45"]["n"] >= 5:
            mr_wr = regime_hurst["mean_reverting_<0.45"]["wr"]
            tr_wr = regime_hurst["trending_>0.55"]["wr"] if regime_hurst["trending_>0.55"]["n"] >= 3 else None
            if mr_wr < 0.40:
                alerts.append(
                    f"HURST SIGNAL: mean-reverting regime (H<0.45) win_rate={mr_wr:.1%} "
                    f"{'vs trending=' + f'{tr_wr:.1%}' if tr_wr else ''} — "
                    f"consider promoting Hurst to hard gate (hurst_min=0.45)"
                )

        # ATR gate calibration: only valid for MOMENTUM trades — SniperSignal has no
        # atr_percentile field, so all sniper trades have atr=0.0, making this analysis meaningless.
        has_real_atr = any(t.atr_percentile > 0.0 for t in trades)
        if has_real_atr and regime_atr["low_pct_<0.30"]["n"] >= 5:
            low_atr_wr = regime_atr["low_pct_<0.30"]["wr"]
            if low_atr_wr < 0.40:
                alerts.append(
                    f"ATR REGIME: low-ATR trades win_rate={low_atr_wr:.1%} — "
                    f"consider raising atr_regime_percentile from 0.30 to 0.40"
                )

        # Intrawindow signal validation: flag if strong IWD (>0.60) is NOT
        # outperforming weak IWD (<0.30) — if it doesn't help, something is wrong.
        if (intrawindow_buckets["iwd_strong_>=0.60"]["n"] >= 5
                and intrawindow_buckets["iwd_weak_<0.30"]["n"] >= 5):
            strong_wr = intrawindow_buckets["iwd_strong_>=0.60"]["wr"]
            weak_wr = intrawindow_buckets["iwd_weak_<0.30"]["wr"]
            if strong_wr < weak_wr:
                alerts.append(
                    f"SIGNAL QUALITY: intrawindow_strong win_rate={strong_wr:.1%} < "
                    f"intrawindow_weak={weak_wr:.1%} — IWD signal may not be predictive "
                    f"for this market; review weight allocation"
                )

        return {
            "alerts": alerts,
            "metrics": metrics,
            "status": "ok" if not alerts else "warning",
            "ts": time.time(),
        }

    # ── Claude-facing report ──────────────────────────────────────────────────

    def generate_claude_report(self) -> str:
        """
        Produces a structured text report for Claude's analysis cycle.
        Python logs this; Claude reads it to propose parameter changes.
        """
        diag = self.run_diagnostics()
        metrics = diag.get("metrics", {})
        metrics.update(self._telemetry)  # inject connectivity + latency
        alerts = diag.get("alerts", [])
        trades = list(self._recent)

        n_total = metrics.get('sample_size', 0)
        n_live = metrics.get('live_trades', 0)
        lines = [
            "=" * 60,
            "FEEDBACK LOOP REPORT — Klaus Momentum Scalper",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
            f"Sample: {n_total} trades ({n_live} live, {n_total - n_live} dry-run)",
            "=" * 60,
            "",
            "PERFORMANCE METRICS",
            f"  Win Rate:        {metrics.get('win_rate', 0):.1%}",
            f"  Profit Factor:   {metrics.get('profit_factor', 0):.2f}",
            f"  Avg Win:        ${metrics.get('avg_win_usd', 0):.3f}",
            f"  Avg Loss:       ${metrics.get('avg_loss_usd', 0):.3f}",
            f"  Net PnL:        ${metrics.get('net_profit_usd', 0):.3f}",
            f"  Fees (est):     ${metrics.get('total_fees_usd', 0):.3f}  "
            f"({metrics.get('fee_bleed_pct', 0):.1f}% of gross)",
            f"  Avg Slippage:    {metrics.get('avg_slippage', 0):.5f}",
            f"  Avg Hold:        {metrics.get('avg_hold_seconds', 0):.0f}s",
            f"  Hard Exit Rate:  {metrics.get('hard_exit_rate', 0):.1%}",
            "",
            "BY ASSET",
        ]

        for asset, pnl in metrics.get("pnl_by_asset", {}).items():
            lines.append(f"  {asset}: PnL=${pnl:.3f}")

        lines += ["", "BY MARKET TYPE"]
        for mtype, pnl in metrics.get("pnl_by_market_type", {}).items():
            lines.append(f"  {mtype}: PnL=${pnl:.3f}")

        lines += [
            "",
            f"  Fat-Middle trades: {metrics.get('fat_middle_count', 0)}",
            f"  Extreme-odds trades: {metrics.get('extreme_count', 0)}",
            "",
        ]

        if alerts:
            lines.append("ALERTS — Claude should review")
            for alert in alerts:
                lines.append(f"  ⚠  {alert}")
        else:
            lines.append("ALERTS — None; strategy operating within parameters")

        # Signal scores: wins vs losses
        sw = metrics.get("signal_scores_wins", {})
        sl_ = metrics.get("signal_scores_losses", {})
        if sw and sl_:
            lines += ["", "SIGNAL SCORES (wins vs losses)"]
            for sig_name in ["breakout", "trend", "volume", "ob", "intrawindow", "composite"]:
                lines.append(
                    f"  {sig_name:12s}: win={sw.get(sig_name, 0):.3f}  "
                    f"loss={sl_.get(sig_name, 0):.3f}  "
                    f"diff={sw.get(sig_name, 0) - sl_.get(sig_name, 0):+.3f}"
                )

        # Regime analysis: ATR + Hurst
        # NOTE: SniperSignal has no atr_percentile/hurst fields — these are MOMENTUM-only.
        # Only show if at least one trade has a non-zero value (i.e. MOMENTUM trades exist).
        ra = metrics.get("regime_atr", {})
        rh = metrics.get("regime_hurst", {})
        _has_real_atr = ra.get("avg_atr_pct_all", 0) > 0
        _has_real_hurst = rh.get("avg_hurst_all", 0) > 0
        if ra and _has_real_atr:
            lines += ["", "REGIME ANALYSIS — ATR PERCENTILE (calibrate atr_regime_percentile)"]
            lines.append(f"  Low  (<30th pct):  n={ra.get('low_pct_<0.30', {}).get('n', 0):3d}  WR={ra.get('low_pct_<0.30', {}).get('wr', 0):.1%}")
            lines.append(f"  Mid  (30-70th pct): n={ra.get('mid_pct_0.30-0.70', {}).get('n', 0):3d}  WR={ra.get('mid_pct_0.30-0.70', {}).get('wr', 0):.1%}")
            lines.append(f"  High (>70th pct):  n={ra.get('high_pct_>0.70', {}).get('n', 0):3d}  WR={ra.get('high_pct_>0.70', {}).get('wr', 0):.1%}")
            lines.append(f"  Avg pct all={ra.get('avg_atr_pct_all', 0):.2f}  wins={ra.get('avg_atr_pct_wins', 0):.2f}  losses={ra.get('avg_atr_pct_losses', 0):.2f}")
        elif ra:
            lines += ["", "REGIME ANALYSIS — ATR/HURST: N/A (SNIPER-only session — these fields are MOMENTUM-only)"]

        if rh and _has_real_hurst:
            lines += ["", "REGIME ANALYSIS — HURST EXPONENT (promote to hard gate when n>=20)"]
            lines.append(f"  Mean-reverting (<0.45): n={rh.get('mean_reverting_<0.45', {}).get('n', 0):3d}  WR={rh.get('mean_reverting_<0.45', {}).get('wr', 0):.1%}")
            lines.append(f"  Random walk  (0.45-0.55): n={rh.get('random_walk_0.45-0.55', {}).get('n', 0):3d}  WR={rh.get('random_walk_0.45-0.55', {}).get('wr', 0):.1%}")
            lines.append(f"  Trending     (>0.55): n={rh.get('trending_>0.55', {}).get('n', 0):3d}  WR={rh.get('trending_>0.55', {}).get('wr', 0):.1%}")
            lines.append(f"  Avg H all={rh.get('avg_hurst_all', 0):.3f}  wins={rh.get('avg_hurst_wins', 0):.3f}  losses={rh.get('avg_hurst_losses', 0):.3f}")

        # Intrawindow signal strength vs outcome
        ib = metrics.get("intrawindow_buckets", {})
        if ib:
            lines += ["", "INTRAWINDOW SIGNAL STRENGTH (validate 'king signal' hypothesis)"]
            lines.append(f"  Weak  (<0.30): n={ib.get('iwd_weak_<0.30', {}).get('n', 0):3d}  WR={ib.get('iwd_weak_<0.30', {}).get('wr', 0):.1%}")
            lines.append(f"  Mid  (0.30-0.60): n={ib.get('iwd_mid_0.30-0.60', {}).get('n', 0):3d}  WR={ib.get('iwd_mid_0.30-0.60', {}).get('wr', 0):.1%}")
            lines.append(f"  Strong (>=0.60): n={ib.get('iwd_strong_>=0.60', {}).get('n', 0):3d}  WR={ib.get('iwd_strong_>=0.60', {}).get('wr', 0):.1%}")
            lines.append(f"  (Expected: strong > mid > weak WR if IWD is predictive)")

        # Signal source split: SNIPER vs MOMENTUM
        src = metrics.get("by_signal_source", {})
        ea = metrics.get("sniper_edge_analysis", {})
        sniper_src = src.get("SNIPER", {})
        momentum_src = src.get("MOMENTUM", {})
        lines += ["", "BY SIGNAL SOURCE"]
        lines.append(
            f"  SNIPER:   n={sniper_src.get('n', 0):3d}  "
            f"WR={sniper_src.get('wr', 0):.1%}  "
            f"PnL=${sniper_src.get('net_pnl', 0):.3f}  "
            f"avg_edge={sniper_src.get('avg_edge', 0):.3f}  "
            f"avg_elapsed={sniper_src.get('avg_elapsed_pct', 0):.0%}"
        )
        lines.append(
            f"  MOMENTUM: n={momentum_src.get('n', 0):3d}  "
            f"WR={momentum_src.get('wr', 0):.1%}  "
            f"PnL=${momentum_src.get('net_pnl', 0):.3f}  "
            f"(updown disabled — price-target only)"
        )

        if sniper_src.get("n", 0) >= 3:
            lines += ["", "SNIPER EDGE ANALYSIS (wins vs losses)"]
            lines.append(f"  edge       : win={ea.get('edge_wins', 0):.3f}  loss={ea.get('edge_losses', 0):.3f}  diff={ea.get('edge_wins', 0)-ea.get('edge_losses', 0):+.3f}")
            lines.append(f"  fair_value : win={ea.get('fv_wins', 0):.3f}  loss={ea.get('fv_losses', 0):.3f}  diff={ea.get('fv_wins', 0)-ea.get('fv_losses', 0):+.3f}")
            lines.append(f"  elapsed%   : win={ea.get('elapsed_wins', 0):.1%}  loss={ea.get('elapsed_losses', 0):.1%}")
            lines.append(f"  delta_pct  : win={ea.get('delta_wins', 0):.3f}%  loss={ea.get('delta_losses', 0):.3f}%")
            lines.append(f"  (Higher edge + lower elapsed% in wins = model is working)")

        # ── Window size split ─────────────────────────────────────────────────
        bw = metrics.get("by_window_size", {})
        if bw:
            lines += ["", "BY WINDOW SIZE"]
            for wlabel, ws in bw.items():
                lines.append(f"  {wlabel:4s}: n={ws['n']:3d}  WR={ws['wr']:.1%}  PnL=${ws['net_pnl']:.3f}")

        # ── Hourly breakdown ──────────────────────────────────────────────────
        bh = metrics.get("by_hour_utc", {})
        if bh:
            lines += ["", "BY HOUR UTC (edge window: 08,13-15,22-23)"]
            for h, hs in bh.items():
                marker = " ←" if h in {8, 9, 13, 14, 15, 22, 23, 0} else ""
                lines.append(f"  {h:02d}:00  n={hs['n']:3d}  WR={hs['wr']:.1%}  PnL=${hs['net_pnl']:.3f}{marker}")

        # ── YES vs NO side performance ────────────────────────────────────────
        ss = metrics.get("side_stats", {})
        yes_s = ss.get("YES", {})
        no_s  = ss.get("NO", {})
        if yes_s.get("n", 0) + no_s.get("n", 0) > 0:
            lines += ["", "BY SIDE (sniper trades)"]
            lines.append(f"  YES: n={yes_s.get('n',0):3d}  WR={yes_s.get('wr',0):.1%}  PnL=${yes_s.get('net_pnl',0):.3f}  (asset moved UP)")
            lines.append(f"  NO:  n={no_s.get('n',0):3d}  WR={no_s.get('wr',0):.1%}  PnL=${no_s.get('net_pnl',0):.3f}  (asset moved DOWN)")

        # ── YES_UP vs YES_DOWN direction breakdown ────────────────────────────
        bd = metrics.get("by_direction", {})
        up_d   = bd.get("YES_UP",   {})
        down_d = bd.get("YES_DOWN", {})
        if up_d.get("n", 0) + down_d.get("n", 0) > 0:
            lines += ["", "BY DIRECTION (YES_UP = above-threshold market / YES_DOWN = below-threshold)"]
            lines.append("  Both buy YES tokens; both win by reaching 1.0 — market direction differs.")
            for dname, ds in [("YES_UP", up_d), ("YES_DOWN", down_d)]:
                if ds.get("n", 0) == 0:
                    continue
                lines.append(
                    f"  {dname}: n={ds['n']:3d}  WR={ds['wr']:.1%}  PnL=${ds['net_pnl']:.3f}"
                )
                if ds.get("avg_ask_qty", 0) > 0 or ds.get("avg_ob_imb_all", 0) != 0:
                    lines.append(
                        f"    ob_imb: all={ds.get('avg_ob_imb_all',0):+.3f}  "
                        f"wins={ds.get('avg_ob_imb_wins',0):+.3f}  "
                        f"losses={ds.get('avg_ob_imb_losses',0):+.3f}"
                    )
                    lines.append(
                        f"    tok_d30: all={ds.get('avg_tok_d30',0):+.4f}%  "
                        f"wins={ds.get('avg_tok_d30_wins',0):+.4f}%  "
                        f"losses={ds.get('avg_tok_d30_losses',0):+.4f}%"
                    )
                    lines.append(
                        f"    spot_d30: all={ds.get('avg_spot_d30',0):+.4f}%  "
                        f"wins={ds.get('avg_spot_d30_wins',0):+.4f}%  "
                        f"losses={ds.get('avg_spot_d30_losses',0):+.4f}%"
                        f"  (YES_UP: positive=favorable; YES_DOWN: negative=favorable)"
                    )
                    lines.append(
                        f"    ask_qty={ds.get('avg_ask_qty',0):.1f}sh  "
                        f"spread={ds.get('avg_ask_spread_pct',0):.2f}%"
                    )

        # ── Per-asset × outcome-direction breakdown ────────────────────────────
        ads = metrics.get("asset_dir_stats", {})
        if ads:
            lines += ["", "BY ASSET × DIRECTION"]
            for key in sorted(ads.keys()):
                ds = ads[key]
                lines.append(
                    f"  {ds['asset']:3s} {ds['direction']:8s}: n={ds['n']:3d}  "
                    f"WR={ds['wr']:.1%}  PnL=${ds['net_pnl']:.3f}"
                )

        # ── VPIN signal impact ────────────────────────────────────────────────
        vi = metrics.get("vpin_impact", {})
        if vi and any(v.get("n", 0) > 0 for v in vi.values()):
            lines += ["", "VPIN IMPACT (sniper trades — does order flow confirm edge?)"]
            for label, vs in vi.items():
                lines.append(f"  {label:22s}: n={vs['n']:3d}  WR={vs['wr']:.1%}")
            lines.append(f"  (Expected: higher VPIN = higher WR if toxicity signal works)")

        # ── LLM boost impact ──────────────────────────────────────────────────
        li = metrics.get("llm_impact", {})
        if li and any(v.get("n", 0) > 0 for v in li.values()):
            lines += ["", "LLM BOOST IMPACT (sniper trades — does macro engine help?)"]
            for label, ls in li.items():
                lines.append(f"  {label:20s}: n={ls['n']:3d}  WR={ls['wr']:.1%}")
            lines.append(f"  (Expected: boosted WR > no-boost WR if LLM signal is valuable)")

        # ── Pre-arm stats ─────────────────────────────────────────────────────
        pa = metrics.get("prearm_stats", {})
        prearm_n = pa.get("prearm", {}).get("n", 0)
        normal_n = pa.get("normal", {}).get("n", 0)
        if prearm_n + normal_n > 0:
            lines += ["", "PRE-ARM vs NORMAL ENTRY (sniper trades)"]
            pre = pa.get("prearm", {})
            norm = pa.get("normal", {})
            lines.append(f"  Pre-armed: n={prearm_n:3d}  WR={pre.get('wr',0):.1%}  PnL=${pre.get('net_pnl',0):.3f}")
            lines.append(f"  Normal:    n={normal_n:3d}  WR={norm.get('wr',0):.1%}  PnL=${norm.get('net_pnl',0):.3f}")

        # ── Exit reason breakdown ─────────────────────────────────────────────
        ber = metrics.get("by_exit_reason", {})
        if ber:
            lines += ["", "BY EXIT REASON"]
            for reason, rs in ber.items():
                lines.append(
                    f"  {reason:15s}: n={rs['n']:3d}  WR={rs['wr']:.1%}  "
                    f"PnL=${rs['net_pnl']:.3f}  avg_hold={rs['avg_hold_s']:.0f}s"
                )

        # Last 5 trades quick summary
        if trades:
            lines += ["", "LAST 5 TRADES"]
            for t in trades[-5:]:
                pnl_str = f"+${t.net_pnl:.3f}" if t.net_pnl > 0 else f"-${abs(t.net_pnl):.3f}"
                if t.signal_source == "SNIPER":
                    wsize = "5m" if t.window_size_s == 300 else ("15m" if t.window_size_s == 900 else f"{t.window_size_s}s")
                    trigger = "PREARM" if t.sniper_prearm else "NORMAL"
                    lines.append(
                        f"  {t.trade_id} | {t.asset}/{t.sniper_side} [{wsize}/{trigger}] "
                        f"{t.hour_utc:02d}:xx UTC | "
                        f"entry={t.entry_price:.4f} exit={t.exit_price:.4f} | "
                        f"PnL={pnl_str} | {t.exit_reason} | {t.hold_seconds:.0f}s | "
                        f"delta={t.sniper_delta_pct:+.3f}% edge={t.sniper_edge:.3f} "
                        f"elapsed={t.sniper_elapsed_pct:.0%}"
                    )
                else:
                    lines.append(
                        f"  {t.trade_id} | {t.asset} {t.direction} [MOMENTUM] | "
                        f"entry={t.entry_price:.4f} exit={t.exit_price:.4f} | "
                        f"PnL={pnl_str} | {t.exit_reason} | {t.hold_seconds:.0f}s | "
                        f"iwd={t.intrawindow_score:.2f} atr={t.atr_percentile:.2f} H={t.hurst:.3f}"
                    )

        # ── Connectivity telemetry ────────────────────────────────────────────
        conn = metrics.get("connectivity", {})
        lat = metrics.get("order_latency", {})
        if conn or lat:
            lines += ["", "CONNECTIVITY (VPS JUSTIFICATION DATA)"]
            if conn:
                total_rc = conn.get("total_reconnects", 0)
                rph = conn.get("reconnects_per_hour", 0)
                uptime = conn.get("uptime_hours", 0)
                verdict = "OK" if total_rc == 0 else ("WARN" if rph < 2 else "BAD — VPS recommended")
                lines.append(f"  WS reconnects: {total_rc} total | {rph:.1f}/hr | {uptime:.1f}h uptime → {verdict}")
                by_feed = conn.get("by_feed", {})
                if any(v > 0 for v in by_feed.values()):
                    lines.append(f"  by feed: clob={by_feed.get('clob_ws',0)} rtds={by_feed.get('rtds_ws',0)} "
                                 f"binance={by_feed.get('binance_ws',0)} kline={by_feed.get('binance_kline',0)}")
            if lat and lat.get("n", 0) > 0:
                slow_pct = lat.get("slow_pct", 0)
                verdict = "OK" if slow_pct < 5 else ("WARN" if slow_pct < 20 else "BAD — VPS recommended")
                lines.append(f"  Order latency: avg={lat['avg_ms']:.0f}ms max={lat['max_ms']:.0f}ms "
                             f"slow(>500ms)={slow_pct:.0f}% → {verdict}")

        lines.append("=" * 60)
        return "\n".join(lines)

    # ── Session summary ───────────────────────────────────────────────────────

    def session_summary(self) -> dict:
        trades = self._session_trades
        if not trades:
            return {"trades": 0}
        return {
            "trades": len(trades),
            "net_pnl": round(sum(t.net_pnl for t in trades), 3),
            "win_rate": round(sum(1 for t in trades if t.net_pnl > 0) / len(trades), 3),
            "fees_paid": round(sum(t.fee_paid for t in trades), 3),
            "assets": list({t.asset for t in trades}),
        }

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _write_jsonl(self, path: str, data: dict) -> None:
        try:
            with open(path, "a") as f:
                f.write(json.dumps(data) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as exc:
            logger.error("Failed to write log %s: %s", path, exc)

    def record_orphan_sell(
        self,
        token_id: str,
        asset: str,
        side: str,
        shares_sold: float,
        avg_exit_price: float,
        is_live: bool = True,
        avg_entry_price: float = 0.0,
    ) -> None:
        """
        Log an ORPHAN_SELL event to trades.jsonl.

        Orphan shares arise from CF retry double-fills — the second order fills
        but the position tracker only knows about the first. At window-end these
        are detected and sold; without logging the financial result is invisible.

        If avg_entry_price is provided (recovered from CLOB BUY history), real
        gross/net PnL is computed. Otherwise gross_pnl/net_pnl are left 0.
        Bankroll reconciliation from CLOB USDC balance should follow any orphan sell.
        """
        self._trade_counter += 1
        trade_id = f"T{self._trade_counter:05d}_{asset}_{int(time.time())}_ORPHAN"
        self.last_trade_id = trade_id
        now = time.time()

        gross_pnl = 0.0
        fee_paid  = 0.0
        net_pnl   = 0.0
        stake     = 0.0
        if avg_entry_price > 0 and shares_sold > 0:
            stake     = round(avg_entry_price * shares_sold, 4)
            gross_pnl = round((avg_exit_price - avg_entry_price) * shares_sold, 4)
            fee_rate  = 0.0142 if (avg_entry_price < 0.30 or avg_entry_price > 0.70) else 0.0312
            fee_paid  = round((avg_entry_price + avg_exit_price) * shares_sold * fee_rate, 4)
            net_pnl   = round(gross_pnl - fee_paid, 4)

        note = (
            f"entry recovered from CLOB history @ {avg_entry_price:.4f}"
            if avg_entry_price > 0
            else "entry cost unknown — bankroll reconciliation required"
        )

        record = {
            "trade_id": trade_id,
            "token_id": token_id,
            "asset": asset,
            "direction": f"BUY_{side}",
            "market_type": "updown",
            "signal_source": "ORPHAN",
            "exit_reason": "ORPHAN_SELL",
            "ts_open": 0.0,
            "ts_close": now,
            "entry_price": round(avg_entry_price, 4),
            "exit_price": round(avg_exit_price, 4),
            "stake": stake,
            "shares": round(shares_sold, 4),
            "gross_pnl": gross_pnl,
            "fee_paid": fee_paid,
            "net_pnl": net_pnl,
            "is_live": is_live,
            "hour_utc": int(time.gmtime(now).tm_hour),
            "note": note,
        }
        self._write_jsonl(self.cfg.trade_log, record)
        logger.warning(
            "ORPHAN_SELL logged: %s/%s %.4f shares ep=%.4f xp=%.4f net=%+.3f (trade_id=%s)",
            asset, side, shares_sold, avg_entry_price, avg_exit_price, net_pnl, trade_id,
        )

    def load_trade_history(self, path: Optional[str] = None) -> List[dict]:
        path = path or self.cfg.trade_log
        if not os.path.exists(path):
            return []
        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records
