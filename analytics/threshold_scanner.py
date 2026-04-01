"""
Klaus — Threshold Scanner

Sweeps every tunable parameter across its full range and shows how
WR and trade frequency change at each cutoff. Uses all available data:

  logs/shadow_blocks.jsonl  — blocked trades with counterfactual outcomes
  logs/trades.jsonl         — live entries with real outcomes
  logs/backtest_results.jsonl — historical replay (optional, large dataset)

Combined, these cover the full parameter space. For any threshold T of
metric M, "virtual entries if we had used T" = all records where M ≥ T.

Output example (lag_remaining sweep):
  threshold   WR     n     EV      freq/day
  ≥ 0.00      8%   289   -0.03    41.3
  ≥ 0.10     10%   245   -0.01    35.0
  ≥ 0.20     12%   195   +0.02    27.9    ← shadow WR crossover
  ≥ 0.30     15%   150   +0.04    21.4    ← current threshold
  ≥ 0.40     19%    98   +0.06    14.0    ← optimal EV
  ≥ 0.50     24%    61   +0.09     8.7
  ≥ 0.60     31%    35   +0.11     5.0
  ↑ WR rises as we require more lag, ↓ frequency falls.
  Optimal = highest EV (not just highest WR).

Usage:
  python3 analytics/threshold_scanner.py            # all parameters
  python3 analytics/threshold_scanner.py --param lag # single param
  python3 analytics/threshold_scanner.py --hour      # WR by hour heatmap
  python3 analytics/threshold_scanner.py --grid      # lag×edge grid search
  python3 analytics/threshold_scanner.py --combine   # include backtest data
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHADOW_LOG   = os.path.join("logs", "shadow_blocks.jsonl")
TRADES_LOG   = os.path.join("logs", "trades.jsonl")
BACKTEST_LOG = os.path.join("logs", "backtest_results.jsonl")

# Current live thresholds (for reference markers in output)
CURRENT = {
    "lag":     0.30,
    "edge":    0.06,
    "delta":   0.08,   # 15m active
    "elapsed": 0.25,
    "vpin":    0.40,   # off-peak gate
}


# ─────────────────────────────────────────────────────────────────────────────
# Data loading + normalisation
# ─────────────────────────────────────────────────────────────────────────────

_WIN_PNL  =  0.20   # stage-1 exit at +20%
_LOSS_PNL = -0.28   # approximate dynamic SL; update from live trade avg once available


def _realistic_pnl(won: bool, max_ask: Optional[float], entry_ask: float) -> float:
    """
    Return a realistic P&L estimate instead of the raw window-end P&L.

    For wins: use actual peak gain (capped at +25% for stage-1) if max_ask available,
              otherwise assume +20%.
    For losses: use -0.28 (dynamic SL approximation).
              Do NOT use window-end P&L — losing tokens expire at 0.01 → -98%.
    """
    if won:
        if max_ask and entry_ask > 0:
            return min((max_ask - entry_ask) / entry_ask, 0.25)
        return _WIN_PNL
    return _LOSS_PNL


def load_records(include_backtest: bool = False) -> List[dict]:
    """
    Load and normalise all available data sources into a unified schema:
      lag, edge, delta_pct, elapsed_pct, vpin, hour_utc, asset, side,
      window_seconds, won (bool or None), pnl (float or None)

    P&L model (realistic, not window-expiry):
      Shadow blocks store pnl_if_entered = (ask_at_window_end - entry) / entry.
      Losing tokens expire at ~0.01 → pnl = -98%. That's "held to death" P&L,
      not what the bot actually does. Real exit is stop-loss at -25 to -35%.

      Realistic model used here:
        win  → +0.20 (stage-1 exit at +20%, conservative)
        loss → -0.28 (approximate dynamic SL, calibrate from live trades later)

      Once enough live trades accumulate, replace these with empirical averages.
    """
    records = []

    # ── Shadow blocks ─────────────────────────────────────────────────────────
    if os.path.exists(SHADOW_LOG):
        for line in open(SHADOW_LOG):
            if not line.strip():
                continue
            r = json.loads(line)
            won = r.get("would_win_20pct")
            if won is None:
                continue  # pending — skip
            ts = r.get("ts", 0)
            records.append({
                "source":   "shadow",
                "asset":    r.get("asset", ""),
                "side":     r.get("side", ""),
                "hour_utc": r.get("hour_utc") or (
                    datetime.fromtimestamp(ts, tz=timezone.utc).hour if ts else 0),
                "window_seconds": r.get("window_seconds", 900),
                "lag":      r.get("lag_remaining_pct", 0.0),
                "edge":     r.get("edge", 0.0),
                "delta_pct": abs(r.get("delta_pct", 0.0)),
                "elapsed_pct": r.get("elapsed_pct", 0.0),
                "vpin":     r.get("vpin", 0.0),
                "entry_ask": r.get("token_ask", 0.0),
                "won":      bool(won),
                "pnl":      _realistic_pnl(bool(won), r.get("max_ask_seen"),
                                           r.get("token_ask", 0.0)),
                "block_reason": r.get("block_reason", ""),
            })

    # ── Live trades ────────────────────────────────────────────────────────────
    if os.path.exists(TRADES_LOG):
        for line in open(TRADES_LOG):
            if not line.strip():
                continue
            r = json.loads(line)
            # Determine win: positive PnL
            pnl = r.get("pnl_usd") or r.get("pnl") or 0.0
            exit_type = r.get("exit_type", "")
            if exit_type == "":
                continue  # incomplete record
            won = pnl > 0
            ts = r.get("ts_open") or r.get("entry_ts") or 0
            records.append({
                "source":   "live",
                "asset":    r.get("asset", ""),
                "side":     r.get("side", ""),
                "hour_utc": r.get("hour_utc") or (
                    datetime.fromtimestamp(ts, tz=timezone.utc).hour if ts else 0),
                "window_seconds": r.get("window_size_s", 900),
                "lag":      r.get("sniper_lag_remaining", 0.0),
                "edge":     r.get("sniper_edge") or r.get("edge", 0.0),
                "delta_pct": abs(r.get("delta_pct") or r.get("sniper_delta_pct", 0.0)),
                "elapsed_pct": r.get("elapsed_pct") or r.get("sniper_elapsed_pct", 0.0),
                "vpin":     r.get("vpin_at_entry") or r.get("sniper_vpin", 0.0),
                "entry_ask": r.get("entry_price", 0.0),
                "won":      won,
                "pnl":      pnl / max(r.get("stake", 1.0), 0.01) if pnl else None,
                # live trades use actual P&L (real exits, not window-expiry)
                "block_reason": "",
            })

    # ── Backtest results ──────────────────────────────────────────────────────
    if include_backtest and os.path.exists(BACKTEST_LOG):
        for line in open(BACKTEST_LOG):
            if not line.strip():
                continue
            r = json.loads(line)
            won = r.get("would_win_20")
            if won is None:
                continue
            records.append({
                "source":   "backtest",
                "asset":    r.get("asset", ""),
                "side":     r.get("side", ""),
                "hour_utc": r.get("hour_utc", 0),
                "window_seconds": r.get("window_seconds", 900),
                "lag":      r.get("lag_pct", 0.0),
                "edge":     r.get("edge", 0.0),
                "delta_pct": abs(r.get("delta_pct", 0.0)),
                "elapsed_pct": r.get("elapsed_pct", 0.0),
                "vpin":     0.0,  # not available in backtest
                "entry_ask": r.get("entry_ask", 0.0),
                "won":      bool(won),
                "pnl":      _realistic_pnl(bool(won), r.get("peak_ask"),
                                           r.get("entry_ask", 0.0)),
                "block_reason": "",
            })

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Threshold sweep
# ─────────────────────────────────────────────────────────────────────────────

def _sweep_one(rated: List[dict], metric: str, thresholds: list,
               days: float, label: str = "") -> Optional[float]:
    """Sweep one slice (all / 5m / 15m). Returns best threshold."""
    current_t = CURRENT.get(metric)
    pfx = f"  [{label}] " if label else "  "
    best_ev, best_t = None, None

    for t in thresholds:
        group = [r for r in rated if r[metric] >= t]
        if not group:
            break
        wr = sum(r["won"] for r in group) / len(group)
        pnls = [r["pnl"] for r in group if r["pnl"] is not None]
        avg_pnl = sum(pnls) / len(pnls) if pnls else None
        ev = avg_pnl
        freq = len(group) / days

        ev_str   = f"{ev:+.3f}" if ev is not None else "  n/a "
        pnl_str  = f"{avg_pnl:+.1%}" if avg_pnl is not None else "  n/a"
        freq_str = f"{freq:.1f}/d"

        notes = []
        if current_t is not None and abs(t - current_t) < 1e-6:
            notes.append("← current")
        if ev is not None and (best_ev is None or ev > best_ev):
            best_ev, best_t = ev, t
            notes.append("← best EV")

        print(f"{pfx}≥ {t:<8.2f}  WR={wr:>4.0%}  n={len(group):>4}  "
              f"pnl={pnl_str:>7}  ev={ev_str:>7}  {freq_str:>7}  {'  '.join(notes)}")

    return best_t


def sweep(records: List[dict], metric: str, thresholds: list,
          filter_fn=None, days: float = 7.0) -> None:
    """
    For each threshold value, compute WR and frequency. Automatically splits
    into 5m and 15m sub-tables when both window types are present.
    """
    rated = [r for r in records if r["won"] is not None]
    if filter_fn:
        rated = [r for r in rated if filter_fn(r)]
    if not rated:
        print(f"  No rated records for {metric}")
        return

    has_5m  = any(r["window_seconds"] == 300 for r in rated)
    has_15m = any(r["window_seconds"] == 900 for r in rated)
    split   = has_5m and has_15m

    current_t = CURRENT.get(metric)
    print(f"\n  Threshold sweep: {metric}  "
          f"(n={len(rated)}  current={current_t})")
    print(f"  {'threshold':<10}  {'WR':>5}  {'n':>5}  {'pnl':>7}  {'ev':>7}  {'freq':>7}")
    print(f"  {'-'*70}")

    if split:
        print(f"  — All windows —")
    best_t = _sweep_one(rated, metric, thresholds, days)

    if split:
        print(f"  — 15m windows —")
        best_15 = _sweep_one(
            [r for r in rated if r["window_seconds"] == 900],
            metric, thresholds, days, "15m")
        print(f"  — 5m windows —")
        best_5 = _sweep_one(
            [r for r in rated if r["window_seconds"] == 300],
            metric, thresholds, days, "5m")
        print(f"\n  → Best thresholds by window:  "
              f"15m={best_15}  5m={best_5}  combined={best_t}")


# ─────────────────────────────────────────────────────────────────────────────
# Hour heatmap
# ─────────────────────────────────────────────────────────────────────────────

def hour_heatmap(records: List[dict]) -> None:
    rated = [r for r in records if r["won"] is not None]
    if not rated:
        print("  No rated records")
        return

    by_hour: dict = defaultdict(list)
    for r in rated:
        by_hour[r["hour_utc"]].append(r)

    # Group by source for side-by-side
    shadow = [r for r in rated if r["source"] == "shadow"]
    live   = [r for r in rated if r["source"] == "live"]
    bktest = [r for r in rated if r["source"] == "backtest"]

    sources = []
    if shadow: sources.append(("shadow", shadow))
    if live:   sources.append(("live",   live))
    if bktest: sources.append(("bktest", bktest))

    print(f"\n  WR by hour UTC  {'  '.join(f'{s[0]:>12}' for s in sources)}")
    print(f"  {'-'*65}")

    active = {8, 9, 13, 14, 15, 22, 23, 0}
    for hour in range(24):
        cols = []
        for _, src in sources:
            grp = [r for r in src if r["hour_utc"] == hour]
            if grp:
                wr = sum(r["won"] for r in grp) / len(grp)
                cols.append(f"{wr:>5.0%} (n={len(grp):>3})")
            else:
                cols.append(f"{'—':>12}")
        flag = " ◆" if hour in active else ""
        print(f"  {hour:02d}:xx{flag}  {'  '.join(cols)}")

    print(f"\n  ◆ = active session hour")


# ─────────────────────────────────────────────────────────────────────────────
# Grid search: lag × edge
# ─────────────────────────────────────────────────────────────────────────────

def grid_search(records: List[dict]) -> None:
    rated = [r for r in records if r["won"] is not None]
    if not rated:
        print("  No rated records")
        return

    lag_vals  = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    edge_vals = [0.02, 0.04, 0.06, 0.08, 0.10, 0.12]

    print(f"\n  Grid search: lag_remaining × edge  (WR% / n)")
    print(f"  {'':12}", end="")
    for e in edge_vals:
        print(f"  edge≥{e:.2f}", end="")
    print()
    print(f"  {'-'*80}")

    best_ev, best_combo = None, None

    for lag_t in lag_vals:
        marker = " ←" if abs(lag_t - CURRENT["lag"]) < 0.01 else ""
        print(f"  lag≥{lag_t:.2f}{marker:3}", end="")
        for edge_t in edge_vals:
            grp = [r for r in rated if r["lag"] >= lag_t and r["edge"] >= edge_t]
            if not grp:
                print(f"  {'—':>9}", end="")
                continue
            wr = sum(r["won"] for r in grp) / len(grp)
            pnls = [r["pnl"] for r in grp if r["pnl"] is not None]
            ev = sum(pnls) / len(pnls) if pnls else None
            if ev is not None and (best_ev is None or ev > best_ev):
                best_ev, best_combo = ev, (lag_t, edge_t)
            marker2 = "*" if (abs(lag_t - CURRENT["lag"]) < 0.01
                              and abs(edge_t - CURRENT["edge"]) < 0.01) else " "
            print(f"  {marker2}{wr:>4.0%}/{len(grp):>3}", end="")
        print()

    if best_combo:
        print(f"\n  → Best EV combo: lag≥{best_combo[0]:.2f} + edge≥{best_combo[1]:.2f}  "
              f"(EV={best_ev:+.3f})")
        print(f"     Current:       lag≥{CURRENT['lag']:.2f} + edge≥{CURRENT['edge']:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# Asset breakdown per metric
# ─────────────────────────────────────────────────────────────────────────────

def asset_sweep(records: List[dict], metric: str, thresholds: list) -> None:
    assets = sorted(set(r["asset"] for r in records if r["asset"]))
    rated = [r for r in records if r["won"] is not None]

    print(f"\n  {metric} threshold vs WR by asset")
    header = f"  {'threshold':<12}" + "".join(f"  {a:>14}" for a in assets)
    print(header)
    print(f"  {'-'*len(header)}")

    for t in thresholds:
        row = f"  ≥ {t:<10.2f}"
        for asset in assets:
            grp = [r for r in rated if r["asset"] == asset and r[metric] >= t]
            if grp:
                wr = sum(r["won"] for r in grp) / len(grp)
                row += f"  {wr:>5.0%} (n={len(grp):>3})"
            else:
                row += f"  {'—':>14}"
        print(row)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Klaus threshold scanner")
    parser.add_argument("--param",   type=str, default=None,
                        help="Single param: lag|edge|delta|elapsed|vpin")
    parser.add_argument("--hour",    action="store_true", help="WR by hour heatmap")
    parser.add_argument("--grid",    action="store_true", help="lag×edge grid search")
    parser.add_argument("--asset",   action="store_true", help="Per-asset threshold breakdown")
    parser.add_argument("--combine", action="store_true", help="Include backtest data")
    parser.add_argument("--window",  type=int, default=None, choices=[5, 15],
                        help="Filter to 5m or 15m windows only")
    parser.add_argument("--days",    type=float, default=7.0,
                        help="Days of data for freq/day calculation")
    args = parser.parse_args()

    records = load_records(include_backtest=args.combine)

    # Window filter
    if args.window:
        wsec = args.window * 60
        records = [r for r in records if r["window_seconds"] == wsec]

    rated   = [r for r in records if r["won"] is not None]

    src_counts = defaultdict(int)
    for r in records:
        src_counts[r["source"]] += 1

    wlabel = f" [{args.window}m only]" if args.window else " [5m + 15m]"
    print(f"\n{'='*65}")
    print(f"  THRESHOLD SCANNER{wlabel}")
    print(f"{'='*65}")
    print(f"  Records: {len(rated)} rated  "
          + "  ".join(f"{k}={v}" for k, v in sorted(src_counts.items())))

    if not rated:
        print("\n  No rated records yet. Run the bot to collect data.")
        sys.exit(0)

    params = {
        "lag":     ([round(x * 0.05, 2) for x in range(0, 21)],),   # 0.00 to 1.00
        "edge":    ([round(x * 0.01, 2) for x in range(0, 21)],),   # 0.00 to 0.20
        "delta":   ([round(x * 0.01, 2) for x in range(4, 25)],),   # 0.04 to 0.24%
        "elapsed": ([round(x * 0.05, 2) for x in range(0, 17)],),   # 0.00 to 0.80
        "vpin":    ([round(x * 0.05, 2) for x in range(0, 21)],),   # 0.00 to 1.00
    }

    if args.hour:
        print(f"\n{'─'*65}")
        hour_heatmap(records)

    if args.grid:
        print(f"\n{'─'*65}")
        grid_search(records)

    selected = [args.param] if args.param else list(params.keys())
    for param in selected:
        if param not in params:
            print(f"  Unknown param: {param}. Choose from: {list(params.keys())}")
            continue
        print(f"\n{'─'*65}")
        sweep(records, param, params[param][0], days=args.days)
        if args.asset:
            asset_sweep(records, param, params[param][0][::2])  # every other threshold

    print()
