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
    sniper_pm_drift_at_entry: float = 0.0  # PM ask drift from trigger→entry (0=lag open)

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

    # Meta
    heat_check_active: bool = False
    consecutive_wins_at_entry: int = 0
    capital_before: float = 0.0
    capital_after: float = 0.0   # always capital_before + net_pnl (not bankroll snapshot)
    is_live: bool = False         # False = dry-run/stub; True = real CLOB trade


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
            net_pnl = gross_pnl - stake * fee_rate

        if actual_fee_from_fills > 0:
            # Actual fees captured from CLOB — most accurate source
            fee_paid = actual_fee_from_fills
        else:
            # Fall back to derived: gross - net (risk manager's fee estimate)
            fee_paid = gross_pnl - net_pnl

        # capital_after is always capital_before + net_pnl. Using the live bankroll
        # snapshot was wrong: if two positions close in the same cycle, the snapshot
        # includes PnL from the *other* position too.
        capital_after = capital_before + net_pnl

        # Slippage
        slippage_entry = entry_fill.slippage if entry_fill else 0.0
        exit_slippages = [r.slippage for r in exit_fills if r.slippage is not None]
        slippage_exit = statistics.mean(exit_slippages) if exit_slippages else 0.0

        # Extract signal fields — handle both SniperSignal and SignalBreakdown
        is_sniper = signal_source == "SNIPER"
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

        # Hurst gate promotion: if mean-reverting trades (H<0.45) show materially
        # worse win rate than trending trades, flag that Hurst should become a hard gate.
        if regime_hurst["mean_reverting_<0.45"]["n"] >= 5:
            mr_wr = regime_hurst["mean_reverting_<0.45"]["wr"]
            tr_wr = regime_hurst["trending_>0.55"]["wr"] if regime_hurst["trending_>0.55"]["n"] >= 3 else None
            if mr_wr < 0.40:
                alerts.append(
                    f"HURST SIGNAL: mean-reverting regime (H<0.45) win_rate={mr_wr:.1%} "
                    f"{'vs trending=' + f'{tr_wr:.1%}' if tr_wr else ''} — "
                    f"consider promoting Hurst to hard gate (hurst_min=0.45)"
                )

        # ATR gate calibration: if low-ATR trades (<30th pct) show poor win rate,
        # the 30% floor may need raising.
        if regime_atr["low_pct_<0.30"]["n"] >= 5:
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
        ra = metrics.get("regime_atr", {})
        rh = metrics.get("regime_hurst", {})
        if ra:
            lines += ["", "REGIME ANALYSIS — ATR PERCENTILE (calibrate atr_regime_percentile)"]
            lines.append(f"  Low  (<30th pct):  n={ra.get('low_pct_<0.30', {}).get('n', 0):3d}  WR={ra.get('low_pct_<0.30', {}).get('wr', 0):.1%}")
            lines.append(f"  Mid  (30-70th pct): n={ra.get('mid_pct_0.30-0.70', {}).get('n', 0):3d}  WR={ra.get('mid_pct_0.30-0.70', {}).get('wr', 0):.1%}")
            lines.append(f"  High (>70th pct):  n={ra.get('high_pct_>0.70', {}).get('n', 0):3d}  WR={ra.get('high_pct_>0.70', {}).get('wr', 0):.1%}")
            lines.append(f"  Avg pct all={ra.get('avg_atr_pct_all', 0):.2f}  wins={ra.get('avg_atr_pct_wins', 0):.2f}  losses={ra.get('avg_atr_pct_losses', 0):.2f}")

        if rh:
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
        except Exception as exc:
            logger.error("Failed to write log %s: %s", path, exc)

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
