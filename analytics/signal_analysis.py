"""Signal analysis — Phase 2 anti-overfitting framework.

Evaluates the predictive quality of each signal in market_timeline against
window_resolution (YES/NO) for all first-fire terminal-zone rows.

THREE ANALYSES:
1. Correlation matrix  — pairwise Pearson between continuous signals.
   Flags pairs >0.6 as redundant (gate doing same job as another).

2. Quantile YES rate   — for each signal, split into decile bins; YES rate
   per bin. Checks monotonicity (is higher signal → higher YES consistent?).

3. Marginal gate contribution — for each gate, what is the YES rate of windows
   where ONLY that gate fails (all others pass) vs the baseline all-pass rate?
   Low marginal YES rate = gate adds unique value. Similar to all-pass = gate
   is redundant.

4. Date-split discipline — discover cohort = rows before --split-date (default
   May 8). Validate cohort = rows on/after. Report both separately.

USAGE:
  python3 analytics/signal_analysis.py [--days 7] [--split-date 2026-05-08]

OUTPUT:
  1. Correlation matrix (signals with |r| > 0.4 to any signal)
  2. Quantile YES rate table per signal
  3. Marginal gate contribution table
  4. Date-split validation summary
"""
import argparse
import glob
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

SHADOW_ROOT = "logs/shadow/hot"
RESOLUTION_PATTERN = os.path.join(SHADOW_ROOT, "*", "window_resolution.jsonl")
GATE_TRACE_PATTERN  = os.path.join(SHADOW_ROOT, "*", "gate_trace.jsonl")
TIMELINE_PATTERN    = os.path.join(SHADOW_ROOT, "*", "market_timeline.jsonl")

# Continuous signals to analyse for predictive power.
# These must be fields present in market_timeline records.
CONTINUOUS_SIGNALS = [
    "best_ask",
    "ob_imb_top3",
    "ob_book_depth_size",
    "spread_bps",
    "tok_snap_30s",
    "tok_snap_60s",
    "binance_ret_30s_pct",
    "binance_ret_60s_pct",
    "binance_ret_5m_pct",
    "binance_ret_1m_pct",
    "binance_ret_60m_pct",
    "vpin_score",
    "tok_delta_5s",
    "tok_decel_ratio",
    "ask_stale_s",
    "seconds_to_resolution",
]

# Fields where v=0 is a placeholder ("not computed") rather than a real value.
# Exclude these from quantile/correlation analysis.
# Audit 2026-05-09 found binance_ret_30s/60s_pct have ~22% zeros clustering in middle bins.
PLACEHOLDER_ZERO_FIELDS = {
    "binance_ret_30s_pct",
    "binance_ret_60s_pct",
    "binance_ret_5m_pct",
    "binance_ret_1m_pct",
    "binance_ret_60m_pct",
    "vpin_score",
    "tok_decel_ratio",
}

# Gates replicated in gate_trace (same keys as gate_results in gate_trace rows)
GATES = ["terminal_zone", "ask_floor", "ask_max", "ob_imb_floor"]

# Strategy version targets — must match shadow timeline emitter
_SV_TARGETS = {
    "v1":  "shadow-passive-v1",
    "v2":  "shadow-passive-v2",
    "all": None,
}


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def load_resolutions(days: int) -> dict:
    """Returns {(condition_id, window_end_ts): full resolution record}.

    Callers must do a direction-aware join: if the token's outcome_dir differs
    from the stored resolution's outcome_dir, flip resolved_yes. The scheduler
    stores one record per (cid, wend) using whichever token direction called it
    first (always 'up' in practice), so YES-DOWN tokens need the flip.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = {}
    for f in sorted(glob.glob(RESOLUTION_PATTERN)):
        date_str = f.split(os.sep)[-2]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        with open(f) as fh:
            for line in fh:
                r = json.loads(line)
                out[(r["condition_id"], r["window_end_ts"])] = r
    return out


def direction_aware_resolved_yes(res: dict, token_outcome_dir: str) -> bool:
    """Return the correct resolved_yes for a token, accounting for direction mismatch."""
    ry = res["resolved_yes"]
    if res.get("outcome_dir", "up") != token_outcome_dir:
        ry = not ry
    return ry


def load_gate_trace(days: int, rem_min: float = 25.0, rem_max: float = 90.0,
                    strategy_version: str = "v2",
                    config_effective_from: int = None) -> dict:
    """Returns {(token_id, window_end_ts): first gate_trace row in terminal zone}.

    Filters:
    - rem_min/rem_max: terminal zone (default 25-90s = live entry window)
    - strategy_version: "v1" | "v2" | "all" (default v2 = current live gate set)
    - config_effective_from: Unix ts; rows with ts_s < this are excluded (handles
      intra-day gate config drift; pass latest threshold-change ts to get current-config-only data).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sv_target = _SV_TARGETS[strategy_version]
    rows = {}
    for f in sorted(glob.glob(GATE_TRACE_PATTERN)):
        date_str = f.split(os.sep)[-2]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        with open(f) as fh:
            for line in fh:
                r = json.loads(line)
                sec = r.get("seconds_to_resolution", 0)
                if not (rem_min <= sec <= rem_max):
                    continue
                if sv_target is not None and r.get("strategy_version") != sv_target:
                    continue
                if config_effective_from is not None and r.get("ts_s", 0) < config_effective_from:
                    continue
                key = (r["token_id"], r["window_end_ts"])
                if key not in rows:
                    rows[key] = r
    return rows


def load_timeline_first_fire(days: int, rem_min: float = 25.0, rem_max: float = 90.0,
                             allowed_keys: set = None,
                             config_effective_from: int = None) -> dict:
    """Returns {(token_id, window_end_ts): first market_timeline row in terminal zone}.

    market_timeline rows lack strategy_version, so we filter by:
    - allowed_keys: only keep rows whose (token_id, window_end_ts) is in this set
      (use the filtered gate_trace key set to enforce temporal/version alignment)
    - config_effective_from: Unix ts cutoff
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = {}
    for f in sorted(glob.glob(TIMELINE_PATTERN)):
        date_str = f.split(os.sep)[-2]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        with open(f) as fh:
            for line in fh:
                r = json.loads(line)
                sec = r.get("seconds_to_resolution", 0)
                if not (rem_min <= sec <= rem_max):
                    continue
                if config_effective_from is not None and r.get("ts_s", 0) < config_effective_from:
                    continue
                key = (r["token_id"], r["window_end_ts"])
                if allowed_keys is not None and key not in allowed_keys:
                    continue
                if key not in rows:
                    rows[key] = r
    return rows


def join_dataset(tl_rows: dict, gt_rows: dict, resolutions: dict) -> list:
    """Join first-fire timeline + gate_trace + resolution into analysis rows.

    Uses direction-aware resolution join: the resolution record stores outcome_dir
    from the first scheduling call (always 'up'). YES-DOWN tokens get resolved_yes
    flipped so their label reflects whether THEIR outcome resolved, not UP's.
    """
    joined = []
    for key, tl in tl_rows.items():
        res_key = (tl["condition_id"], tl["window_end_ts"])
        if res_key not in resolutions:
            continue
        gt = gt_rows.get(key)
        row = dict(tl)
        row["resolved_yes"] = direction_aware_resolved_yes(
            resolutions[res_key], tl.get("outcome_dir", "up")
        )
        row["all_pass"] = gt["all_pass"] if gt else False
        row["gate_results"] = gt.get("gate_results", {}) if gt else {}
        row["first_failed_gate"] = gt.get("first_failed_gate") if gt else None
        joined.append(row)
    return joined


def split_by_date(rows: list, split_dt: datetime) -> tuple:
    """Split rows into (discover, validate) by ts_s."""
    split_ts = int(split_dt.timestamp())
    discover = [r for r in rows if r["ts_s"] < split_ts]
    validate = [r for r in rows if r["ts_s"] >= split_ts]
    return discover, validate


# ── Analysis functions ─────────────────────────────────────────────────────────

def pearson_r(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 10:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dxs = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dys = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dxs == 0 or dys == 0:
        return float("nan")
    return num / (dxs * dys)


def _is_valid_signal_value(sig: str, v) -> bool:
    """Reject None, NaN, stale-marker (999.0), and field-specific placeholder zeros."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if math.isnan(f) or f == 999.0:
        return False
    if f == 0.0 and sig in PLACEHOLDER_ZERO_FIELDS:
        return False
    return True


def correlation_matrix(rows: list, min_n: int = 50) -> None:
    print(f"\n=== 1. Pairwise correlation matrix (|r|>0.40, n≥{min_n}) ===")
    print(f"   Flags which signals move together — redundant pairs (|r|>0.60) waste gate slots.")
    print(f"   Placeholder zeros excluded for: {sorted(PLACEHOLDER_ZERO_FIELDS)}")
    print()

    signals = [s for s in CONTINUOUS_SIGNALS]
    vecs = {}
    for sig in signals:
        vals = []
        for r in rows:
            v = r.get(sig)
            if _is_valid_signal_value(sig, v):
                vals.append(float(v))
            else:
                vals.append(None)
        vecs[sig] = vals

    high_pairs = []
    for i, s1 in enumerate(signals):
        for s2 in signals[i+1:]:
            xs, ys = [], []
            for v1, v2 in zip(vecs[s1], vecs[s2]):
                if v1 is not None and v2 is not None:
                    xs.append(v1)
                    ys.append(v2)
            if len(xs) < min_n:
                continue
            r = pearson_r(xs, ys)
            if math.isnan(r):
                continue
            if abs(r) >= 0.40:
                high_pairs.append((abs(r), r, s1, s2, len(xs)))

    if not high_pairs:
        print("  No pairs with |r| ≥ 0.40 found (may need more data).")
        return

    high_pairs.sort(reverse=True)
    print(f"{'Signal A':<22} {'Signal B':<22} {'r':>7} {'n':>7} {'flag'}")
    print("-" * 72)
    for abs_r, r, s1, s2, n in high_pairs:
        flag = "REDUNDANT" if abs_r > 0.60 else ""
        print(f"{s1:<22} {s2:<22} {r:>+6.3f} {n:>7} {flag}")


def quantile_yes_rate(rows: list, n_bins: int = 10, min_bin_n: int = 10) -> None:
    print(f"\n=== 2. Quantile YES rate per signal (decile bins, min n={min_bin_n}) ===")
    print(f"   Monotonic ↑ = higher signal → higher YES. Monotonic ↓ = inverse predictor.")
    print(f"   Non-monotonic = signal adds noise, not signal.")
    print()

    baseline = sum(1 for r in rows if r["resolved_yes"]) / len(rows) if rows else 0.0
    n_total = len(rows)

    for sig in CONTINUOUS_SIGNALS:
        vals = [(float(r[sig]), r["resolved_yes"]) for r in rows
                if _is_valid_signal_value(sig, r.get(sig))]
        n_used = len(vals)
        n_dropped = n_total - n_used
        if n_used < n_bins * min_bin_n:
            print(f"  {sig}: insufficient data (n={n_used}, need ≥{n_bins * min_bin_n}; dropped {n_dropped} placeholder/null)")
            continue

        vals_sorted = sorted(vals, key=lambda x: x[0])
        bin_size = len(vals_sorted) // n_bins
        bin_yes_rates = []
        for i in range(n_bins):
            start = i * bin_size
            end = start + bin_size if i < n_bins - 1 else len(vals_sorted)
            chunk = vals_sorted[start:end]
            n = len(chunk)
            if n < min_bin_n:
                bin_yes_rates.append(None)
                continue
            yr = sum(1 for _, y in chunk if y) / n
            bin_yes_rates.append((yr, n, chunk[0][0], chunk[-1][0]))

        valid = [x for x in bin_yes_rates if x is not None]
        if len(valid) < 3:
            print(f"  {sig}: too few valid bins")
            continue

        yes_rates = [x[0] for x in valid]
        diffs = [yes_rates[i+1] - yes_rates[i] for i in range(len(yes_rates)-1)]
        n_up = sum(1 for d in diffs if d > 0)
        n_dn = sum(1 for d in diffs if d < 0)
        if n_up >= len(diffs) * 0.75:
            mono = "↑ monotonic"
        elif n_dn >= len(diffs) * 0.75:
            mono = "↓ monotonic"
        else:
            mono = "non-monotonic"

        min_yr = min(yes_rates)
        max_yr = max(yes_rates)
        spread = max_yr - min_yr

        drop_note = f"  (dropped {n_dropped} placeholder/null of {n_total})" if n_dropped else ""
        print(f"\n  {sig}  [baseline={baseline:.1%}  spread={spread:+.1%}  {mono}]{drop_note}")
        print(f"  {'bin':>4} {'range':<22} {'n':>5} {'YES%':>7}")
        print(f"  " + "-" * 43)
        for i, entry in enumerate(bin_yes_rates):
            if entry is None:
                print(f"  {i+1:>4}  (n<{min_bin_n})")
                continue
            yr, n, lo, hi = entry
            diff = yr - baseline
            marker = " *" if abs(diff) > 0.10 else ""
            print(f"  {i+1:>4}  [{lo:.4f} – {hi:.4f}]  {n:>5} {yr:>6.1%}{marker}")


def marginal_gate_contribution(rows: list, min_n: int = 20) -> None:
    print(f"\n=== 3. Marginal gate contribution (only-that-gate-fails, n≥{min_n}) ===")
    print(f"   YES rate when ONLY this gate fails (all others pass) vs all-pass baseline.")
    print(f"   HIGH yes_rate (close to all-pass) = gate filters tokens that would have resolved YES → RELAX?")
    print(f"   LOW yes_rate (much lower than baseline) = gate correctly filters losers → KEEP")
    print()

    # Baseline: all-pass cohort
    all_pass = [r for r in rows if r.get("all_pass")]
    if all_pass:
        baseline_pass = sum(1 for r in all_pass if r["resolved_yes"]) / len(all_pass)
    else:
        baseline_pass = 0.0

    # Overall baseline
    baseline_all = sum(1 for r in rows if r["resolved_yes"]) / len(rows) if rows else 0.0

    print(f"  Overall YES rate (all terminal-zone first-fires): {baseline_all:.1%}  n={len(rows)}")
    print(f"  Gate-PASS cohort YES rate:                        {baseline_pass:.1%}  n={len(all_pass)}")
    print()
    print(f"{'Gate':<20} {'n_solo_fail':>12} {'YES%':>7} {'vs_baseline':>12} {'verdict':>10}")
    print("-" * 68)

    for gate in GATES:
        # Windows where ONLY this gate fails (all other gates pass)
        solo_fails = []
        for r in rows:
            gr = r.get("gate_results", {})
            if not gr:
                continue
            this_fails = gr.get(gate, "PASS") != "PASS"
            others_pass = all(
                gr.get(g, "PASS") == "PASS"
                for g in GATES if g != gate
            )
            if this_fails and others_pass:
                solo_fails.append(r)

        n = len(solo_fails)
        if n < min_n:
            print(f"{gate:<20} {n:>12}  (n<{min_n} — insufficient)")
            continue

        yr = sum(1 for r in solo_fails if r["resolved_yes"]) / n
        diff = yr - baseline_all
        verdict = "RELAX?" if yr > baseline_all + 0.05 else ("KEEP" if yr < baseline_all - 0.05 else "neutral")
        print(f"{gate:<20} {n:>12} {yr:>6.1%} {diff:>+11.1%}  {verdict:>10}")


def date_split_summary(discover: list, validate: list, split_date: str) -> None:
    print(f"\n=== 4. Date-split discipline (discover: before {split_date}, validate: on/after) ===")

    for label, rows in [("DISCOVER", discover), ("VALIDATE", validate)]:
        if not rows:
            print(f"\n  {label}: no data")
            continue
        n = len(rows)
        yr = sum(1 for r in rows if r["resolved_yes"]) / n
        passed = sum(1 for r in rows if r.get("all_pass"))
        print(f"\n  {label}  n={n}  YES%={yr:.1%}  gate-pass-rate={passed/n:.1%}")

        # YES rate by gate
        for gate in GATES:
            solo_fails = [r for r in rows
                          if r.get("gate_results", {}).get(gate, "PASS") != "PASS"
                          and all(r.get("gate_results", {}).get(g, "PASS") == "PASS"
                                  for g in GATES if g != gate)]
            if len(solo_fails) < 10:
                continue
            yr_g = sum(1 for r in solo_fails if r["resolved_yes"]) / len(solo_fails)
            print(f"    {gate:<20} solo-fail n={len(solo_fails):>5}  YES%={yr_g:.1%}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--split-date", default="2026-05-08",
                        help="ISO date — discover before, validate on/after")
    parser.add_argument("--min-n", type=int, default=20)
    parser.add_argument("--rem-min", type=float, default=25.0,
                        help="Min seconds_to_resolution (default 25 = live entry zone min)")
    parser.add_argument("--rem-max", type=float, default=90.0,
                        help="Max seconds_to_resolution (default 90 = live entry zone max; "
                             "feedback_terminal_window_filter mandates 25-90s)")
    parser.add_argument("--strategy-version", choices=["v1", "v2", "all"], default="v2",
                        help="Filter gate_trace by shadow strategy version (default v2 = current live gate set)")
    parser.add_argument("--config-effective-from", type=int, default=None,
                        help="Unix ts cutoff — exclude rows with ts_s < this. Use to filter to "
                             "post-gate-config-change data (today's last threshold change: 19:49 UTC)")
    args = parser.parse_args()

    split_dt = _parse_date(args.split_date)

    print(f"Loading data (last {args.days} days, rem {args.rem_min:.0f}-{args.rem_max:.0f}s, "
          f"strategy_version={args.strategy_version}, config_from={args.config_effective_from})...")
    resolutions = load_resolutions(args.days)
    gt_rows = load_gate_trace(args.days, args.rem_min, args.rem_max,
                               args.strategy_version, args.config_effective_from)
    # Constrain timeline to keys present in filtered gate_trace → enforces version/time alignment
    tl_rows = load_timeline_first_fire(args.days, args.rem_min, args.rem_max,
                                        allowed_keys=set(gt_rows.keys()),
                                        config_effective_from=args.config_effective_from)

    print(f"  timeline first-fires (terminal zone): {len(tl_rows)}")
    print(f"  gate_trace first-fires:               {len(gt_rows)}")
    print(f"  resolution outcomes:                  {len(resolutions)}")

    rows = join_dataset(tl_rows, gt_rows, resolutions)
    print(f"  joined rows:                          {len(rows)}")

    if not rows:
        print("No data. Ensure shadow Phase 2 has been running and resolutions are available.")
        return

    discover, validate = split_by_date(rows, split_dt)
    print(f"  discover (before {args.split_date}):      {len(discover)}")
    print(f"  validate (on/after {args.split_date}):    {len(validate)}")

    print(f"\nRunning on DISCOVER cohort (n={len(discover)}) unless noted.")

    analysis_rows = discover if discover else rows

    correlation_matrix(analysis_rows)
    quantile_yes_rate(analysis_rows)
    marginal_gate_contribution(analysis_rows, min_n=args.min_n)
    date_split_summary(discover, validate, args.split_date)


if __name__ == "__main__":
    main()
