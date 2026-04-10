#!/usr/bin/env python3
"""
Parameter Analysis — reads logs/trades.jsonl and produces a full breakdown
of every tunable parameter vs win/loss outcome.

Usage:
    python3 analytics/param_analysis.py
"""

import json
import os
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
TRADES_PATH = os.path.join(REPO_ROOT, "logs", "trades.jsonl")

# ---------------------------------------------------------------------------
# Data loading & filtering
# ---------------------------------------------------------------------------

def load_trades(path: str) -> list[dict]:
    trades = []
    skipped_orphan = 0
    skipped_blank = 0
    with open(path) as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                skipped_blank += 1
                continue
            try:
                t = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"  [WARN] line {lineno}: JSON parse error — {exc}", file=sys.stderr)
                continue
            # Orphan filter: must have is_live set AND entry_price > 0
            if not t.get("is_live"):
                skipped_orphan += 1
                continue
            if (t.get("entry_price") or 0.0) == 0.0:
                skipped_orphan += 1
                continue
            trades.append(t)
    print(f"Loaded {len(trades)} valid live trades  "
          f"(skipped orphans/non-live: {skipped_orphan}, blank lines: {skipped_blank})\n")
    return trades

# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def compute_stats(bucket_trades: list[dict]) -> dict:
    """Compute n, wins, WR%, avg_win, avg_loss, profit_factor, net_pnl."""
    n = len(bucket_trades)
    if n == 0:
        return dict(n=0, wins=0, wr=None, avg_win=None,
                    avg_loss=None, pf=None, net_pnl=0.0)

    wins = [t["pnl"] for t in bucket_trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in bucket_trades if t["pnl"] <= 0]

    n_wins = len(wins)
    wr = (n_wins / n) * 100.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    pf = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")
    net_pnl = sum(t["pnl"] for t in bucket_trades)

    return dict(n=n, wins=n_wins, wr=wr, avg_win=avg_win,
                avg_loss=avg_loss, pf=pf, net_pnl=net_pnl)

def fmt_pct(v) -> str:
    if v is None:
        return "  —  "
    return f"{v:5.1f}%"

def fmt_money(v, zero_dash: bool = False) -> str:
    if v is None:
        return "   —   "
    if zero_dash and v == 0.0:
        return "   —   "
    return f"${v:+.3f}"

def fmt_pf(v) -> str:
    if v is None:
        return "  —  "
    if v == float("inf"):
        return "  ∞  "
    return f"{v:5.2f}"

# ---------------------------------------------------------------------------
# Table printing
# ---------------------------------------------------------------------------

SEP = "=" * 78

def print_section_header(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def print_table(rows: list[tuple[str, dict]], col_width: int = 22):
    """rows = list of (label, stats_dict)"""
    header = (
        f"{'Bucket':<{col_width}} {'n':>5}  {'WR%':>7}  "
        f"{'avg_win':>8}  {'avg_loss':>9}  {'PF':>6}  {'net_pnl':>9}"
    )
    print(header)
    print("-" * len(header))
    for label, s in rows:
        if s["n"] == 0:
            continue
        print(
            f"{label:<{col_width}} {s['n']:>5}  {fmt_pct(s['wr']):>7}  "
            f"{fmt_money(s['avg_win'], zero_dash=True):>8}  "
            f"{fmt_money(s['avg_loss'], zero_dash=True):>9}  "
            f"{fmt_pf(s['pf']):>6}  {fmt_money(s['net_pnl']):>9}"
        )

# ---------------------------------------------------------------------------
# Bucketing helpers
# ---------------------------------------------------------------------------

def bucket_continuous(value: float, breakpoints: list[float], labels: list[str]) -> str:
    """Map a float to a bucket label using a sorted list of upper bounds."""
    for bp, label in zip(breakpoints, labels[:-1]):
        if value < bp:
            return label
    return labels[-1]

# ---------------------------------------------------------------------------
# Individual parameter analyses
# ---------------------------------------------------------------------------

def analyse_quality_score(trades: list[dict]) -> tuple[list[tuple], float]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        qs = t.get("quality_score")
        if qs is None:
            continue
        groups[str(int(qs))].append(t)
    rows = []
    for val in ["0", "1", "2", "3", "4"]:
        rows.append((f"qs={val}", compute_stats(groups[val])))
    return rows, _wr_spread(rows)


def analyse_lag(trades: list[dict]) -> tuple[list[tuple], float]:
    breakpoints = [0.40, 0.50, 0.60, 0.70, 0.80]
    labels = ["<0.40", "0.40–0.50", "0.50–0.60", "0.60–0.70", "0.70–0.80", "0.80+"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        # field is sniper_lag_remaining in trades.jsonl
        v = t.get("sniper_lag_remaining") or t.get("lag_remaining") or t.get("lag")
        if v is None:
            continue
        groups[bucket_continuous(float(v), breakpoints, labels)].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_delta_pct(trades: list[dict]) -> tuple[list[tuple], float]:
    breakpoints = [0.10, 0.12, 0.15, 0.18]
    labels = ["<0.10", "0.10–0.12", "0.12–0.15", "0.15–0.18", "0.18+"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        # field is sniper_delta_pct in trades.jsonl
        v = t.get("sniper_delta_pct") or t.get("delta_pct") or t.get("intrawindow_delta")
        if v is None:
            continue
        groups[bucket_continuous(abs(float(v)), breakpoints, labels)].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_elapsed_pct(trades: list[dict]) -> tuple[list[tuple], float]:
    breakpoints = [0.10, 0.25, 0.40, 0.55, 0.70]
    labels = ["<0.10", "0.10–0.25", "0.25–0.40", "0.40–0.55", "0.55–0.70", "0.70+"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        # field is sniper_elapsed_pct in trades.jsonl
        v = t.get("sniper_elapsed_pct") or t.get("elapsed_pct")
        if v is None:
            continue
        groups[bucket_continuous(float(v), breakpoints, labels)].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_entry_price(trades: list[dict]) -> tuple[list[tuple], float]:
    breakpoints = [0.50, 0.55, 0.60, 0.65, 0.70]
    labels = ["<0.50", "0.50–0.55", "0.55–0.60", "0.60–0.65", "0.65–0.70", "0.70+"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("entry_price")
        if v is None:
            continue
        groups[bucket_continuous(float(v), breakpoints, labels)].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_vpin(trades: list[dict]) -> tuple[list[tuple], float]:
    breakpoints = [0.25, 0.35, 0.45, 0.55]
    labels = ["<0.25", "0.25–0.35", "0.35–0.45", "0.45–0.55", "0.55+"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        # field is sniper_vpin in trades.jsonl
        v = t.get("sniper_vpin") or t.get("vpin_score") or t.get("vpin")
        if v is None:
            continue
        groups[bucket_continuous(float(v), breakpoints, labels)].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_hour_utc(trades: list[dict], min_n: int = 3) -> tuple[list[tuple], float]:
    groups: dict[int, list] = defaultdict(list)
    for t in trades:
        h = t.get("hour_utc")
        if h is None:
            continue
        groups[int(h)].append(t)
    rows = []
    for h in sorted(groups.keys()):
        s = compute_stats(groups[h])
        if s["n"] >= min_n:
            rows.append((f"hour={h:02d}UTC", s))
    return rows, _wr_spread(rows)


def analyse_asset(trades: list[dict]) -> tuple[list[tuple], float]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("asset")
        if v is None:
            continue
        groups[str(v)].append(t)
    ordered = sorted(groups.keys())
    rows = [(a, compute_stats(groups[a])) for a in ordered]
    return rows, _wr_spread(rows)


def analyse_regime(trades: list[dict]) -> tuple[list[tuple], float]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("regime")
        if v is None:
            continue
        groups[str(v)].append(t)
    ordered = sorted(groups.keys())
    rows = [(r, compute_stats(groups[r])) for r in ordered]
    return rows, _wr_spread(rows)


def analyse_direction(trades: list[dict]) -> tuple[list[tuple], float]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("direction")
        if v is None:
            continue
        groups[str(v)].append(t)
    ordered = sorted(groups.keys())
    rows = [(d, compute_stats(groups[d])) for d in ordered]
    return rows, _wr_spread(rows)


def analyse_binance_reversal(trades: list[dict]) -> tuple[list[tuple], float]:
    """WR by binance_reversal_count_at_exit: was Binance reversed when we exited?"""
    breakpoints = [1, 4, 8, 15]
    labels = ["0 (aligned)", "1–3", "4–7", "8–14", "15+ (confirmed)"]
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("binance_reversal_count_at_exit")
        if v is None:
            continue
        cnt = int(v)
        if cnt == 0:
            bucket = "0 (aligned)"
        elif cnt < 4:
            bucket = "1–3"
        elif cnt < 8:
            bucket = "4–7"
        elif cnt < 15:
            bucket = "8–14"
        else:
            bucket = "15+ (confirmed)"
        groups[bucket].append(t)
    rows = [(lbl, compute_stats(groups[lbl])) for lbl in labels]
    return rows, _wr_spread(rows)


def analyse_exit_reason(trades: list[dict], top_n: int = 10) -> tuple[list[tuple], float]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        v = t.get("exit_reason")
        if v is None:
            continue
        groups[str(v)].append(t)
    # Sort by frequency, take top_n
    ordered = sorted(groups.keys(), key=lambda k: len(groups[k]), reverse=True)[:top_n]
    rows = [(r, compute_stats(groups[r])) for r in ordered]
    return rows, _wr_spread(rows)


# ---------------------------------------------------------------------------
# Correlation summary helpers
# ---------------------------------------------------------------------------

def _wr_spread(rows: list[tuple]) -> float:
    """WR spread = max(WR%) - min(WR%) across buckets with n>=3."""
    wrs = [s["wr"] for _, s in rows if s["n"] >= 3 and s["wr"] is not None]
    if len(wrs) < 2:
        return 0.0
    return max(wrs) - min(wrs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(TRADES_PATH):
        print(f"ERROR: trades file not found at {TRADES_PATH}", file=sys.stderr)
        sys.exit(1)

    trades = load_trades(TRADES_PATH)

    if not trades:
        print("No valid live trades found. Nothing to analyse.")
        return

    # Normalise pnl field: prefer net_pnl, fall back to pnl, then gross_pnl
    for t in trades:
        if "pnl" not in t:
            if "net_pnl" in t:
                t["pnl"] = t["net_pnl"]
            elif "gross_pnl" in t:
                t["pnl"] = t["gross_pnl"]
            else:
                t["pnl"] = 0.0

    n_total = len(trades)
    n_wins = sum(1 for t in trades if t["pnl"] > 0)
    net_total = sum(t["pnl"] for t in trades)
    print(f"{'='*78}")
    print(f"  PARAMETER ANALYSIS  —  {n_total} live trades | "
          f"WR={n_wins/n_total*100:.1f}% | net_pnl=${net_total:+.3f}")
    print(f"  NOTE: n<20 — data collection mode. All patterns below are tentative.")
    print(f"{'='*78}")

    correlation_summary: list[tuple[str, float]] = []

    def run(title: str, fn, *args):
        rows, spread = fn(*args)
        visible = [(lbl, s) for lbl, s in rows if s["n"] > 0]
        print_section_header(title)
        if not visible:
            print("  (no data — field absent from all trades)")
        else:
            print_table(visible)
        correlation_summary.append((title, spread))

    run("QUALITY SCORE (qs)", analyse_quality_score, trades)
    run("LAG (lag_remaining fraction)", analyse_lag, trades)
    run("DELTA PCT (|delta_pct| or |intrawindow_delta|)", analyse_delta_pct, trades)
    run("ELAPSED PCT (window elapsed at entry)", analyse_elapsed_pct, trades)
    run("ENTRY PRICE", analyse_entry_price, trades)
    run("VPIN SCORE", analyse_vpin, trades)
    run("HOUR UTC (only hours with n≥3)", analyse_hour_utc, trades)
    run("ASSET", analyse_asset, trades)
    run("REGIME", analyse_regime, trades)
    run("DIRECTION", analyse_direction, trades)
    run("EXIT REASON (top 10 by frequency)", analyse_exit_reason, trades)
    run("BINANCE REVERSAL COUNT AT EXIT", analyse_binance_reversal, trades)

    # ------------------------------------------------------------------
    # Correlation summary
    # ------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  CORRELATION SUMMARY  —  ranked by WR spread (best bucket – worst bucket)")
    print(f"  (only buckets with n≥3 count toward spread; 0.0 = insufficient data)")
    print(SEP)
    correlation_summary.sort(key=lambda x: x[1], reverse=True)
    print(f"{'Parameter':<45} {'WR spread':>10}")
    print("-" * 57)
    for name, spread in correlation_summary:
        flag = "  *** strong signal" if spread >= 30 else ("  ** moderate" if spread >= 15 else "")
        print(f"{name:<45} {spread:>9.1f}%{flag}")

    print(f"\n{SEP}")
    print("  INTERPRETATION GUIDE")
    print(SEP)
    print("  WR spread ≥30pp  — parameter shows strong predictive signal (validate with n≥20)")
    print("  WR spread 15–30pp — moderate signal worth monitoring")
    print("  WR spread <15pp  — no meaningful edge found in this dimension")
    print(f"  Current n={n_total} — minimum n=20 required before acting on any finding.")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
