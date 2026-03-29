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
    ts_open: float
    ts_close: float

    # Execution
    entry_price: float
    exit_price: float
    stake: float
    shares: float
    gross_pnl: float
    fee_paid: float
    net_pnl: float
    slippage_entry: float
    slippage_exit: float
    exit_reason: str         # TAKE_PROFIT / STOP_LOSS / HARD_EXIT / MANUAL

    # Signal breakdown (for Claude analysis)
    breakout_score: float
    trend_score: float
    volume_score: float
    ob_score: float
    composite_score: float
    confidence: float
    fee_zone: str            # EXTREME / FAT_MIDDLE
    external_boost: float

    # Duration
    hold_seconds: float

    # Meta
    heat_check_active: bool
    consecutive_wins_at_entry: int
    capital_before: float
    capital_after: float


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

    def _ensure_log_dir(self) -> None:
        os.makedirs(self.cfg.log_dir, exist_ok=True)

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
        signal: SignalBreakdown,
        ts_open: float,
        ts_close: float,
        capital_before: float,
        capital_after: float,
        heat_check_active: bool,
        consecutive_wins: int,
    ) -> TradeRecord:

        self._trade_counter += 1
        trade_id = f"T{self._trade_counter:05d}_{asset}_{int(ts_open)}"

        # Gross PnL (before fees)
        if direction == Direction.BUY_YES:
            gross_pnl = (exit_price - entry_price) * shares
        else:
            gross_pnl = (entry_price - exit_price) * shares

        # Total fees
        fee_paid = sum(r.total_fee for r in [entry_fill] + exit_fills)
        net_pnl = gross_pnl - fee_paid

        # Slippage
        slippage_entry = entry_fill.slippage if entry_fill else 0.0
        exit_slippages = [r.slippage for r in exit_fills if r.slippage is not None]
        slippage_exit = statistics.mean(exit_slippages) if exit_slippages else 0.0

        rec = TradeRecord(
            trade_id=trade_id,
            token_id=token_id,
            asset=asset,
            direction=direction.name,
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
            breakout_score=round(signal.breakout_score, 3),
            trend_score=round(signal.trend_score, 3),
            volume_score=round(signal.volume_score, 3),
            ob_score=round(signal.ob_score, 3),
            composite_score=round(signal.composite, 3),
            confidence=round(signal.confidence, 3),
            fee_zone=signal.fee_zone.name,
            external_boost=round(signal.external_boost, 3),
            hold_seconds=round(ts_close - ts_open, 1),
            heat_check_active=heat_check_active,
            consecutive_wins_at_entry=consecutive_wins,
            capital_before=round(capital_before, 2),
            capital_after=round(capital_after, 2),
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

        metrics = {
            "sample_size": n,
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
        alerts = diag.get("alerts", [])
        trades = list(self._recent)

        lines = [
            "=" * 60,
            "FEEDBACK LOOP REPORT — Klaus Momentum Scalper",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
            f"Sample: last {metrics.get('sample_size', 0)} trades",
            "=" * 60,
            "",
            "PERFORMANCE METRICS",
            f"  Win Rate:        {metrics.get('win_rate', 0):.1%}",
            f"  Profit Factor:   {metrics.get('profit_factor', 0):.2f}",
            f"  Avg Win:        ${metrics.get('avg_win_usd', 0):.3f}",
            f"  Avg Loss:       ${metrics.get('avg_loss_usd', 0):.3f}",
            f"  Net PnL:        ${metrics.get('net_profit_usd', 0):.3f}",
            f"  Fee Bleed:       {metrics.get('fee_bleed_pct', 0):.1f}% of gross",
            f"  Avg Slippage:    {metrics.get('avg_slippage', 0):.5f}",
            f"  Avg Hold:        {metrics.get('avg_hold_seconds', 0):.0f}s",
            f"  Hard Exit Rate:  {metrics.get('hard_exit_rate', 0):.1%}",
            "",
            "MARKET BREAKDOWN",
        ]

        for asset, pnl in metrics.get("pnl_by_asset", {}).items():
            lines.append(f"  {asset}: PnL=${pnl:.3f}")

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

        # Last 5 trades quick summary
        if trades:
            lines += ["", "LAST 5 TRADES"]
            for t in trades[-5:]:
                pnl_str = f"+${t.net_pnl:.3f}" if t.net_pnl > 0 else f"-${abs(t.net_pnl):.3f}"
                lines.append(
                    f"  {t.trade_id} | {t.asset} {t.direction} | "
                    f"entry={t.entry_price:.4f} exit={t.exit_price:.4f} | "
                    f"PnL={pnl_str} | {t.exit_reason} | {t.hold_seconds:.0f}s"
                )

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
