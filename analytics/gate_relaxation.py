"""Gate relaxation surface — Phase 1 data analysis.

For every token the live gate REJECTED (gate_trace.all_pass=False), asks:
"If we had removed that gate, what would the YES resolution rate have been?"

Answers: which gates add value (they filter out tokens that would have resolved NO)
and which destroy value (they filter out tokens that would have resolved YES).

Runs on existing Phase 1 gate_trace + window_resolution data (~600k rows).

USAGE:
  python3 analytics/gate_relaxation.py [--days 3]

OUTPUT:
  Per-gate table: gate | n_rejected | yes_rate_of_rejected | edge_impact
  edge_impact = yes_rate_of_rejected - baseline_yes_rate
    positive → gate is correctly filtering losers (keep it)
    negative → gate is incorrectly filtering winners (worth relaxing)

Also prints: YES rate by first_failed_gate bucket (visualises which failure
is most associated with incorrect rejection).
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

SHADOW_ROOT = "logs/shadow/hot"
RESOLUTION_PATTERN = os.path.join(SHADOW_ROOT, "*", "window_resolution.jsonl")
GATE_TRACE_PATTERN  = os.path.join(SHADOW_ROOT, "*", "gate_trace.jsonl")


def load_resolutions(days: int) -> dict:
    """Returns {(condition_id, window_end_ts): full resolution record}.

    Join with direction_aware_resolved_yes() — the scheduler stores one record
    per (cid, wend) using the first token's direction (always 'up'), so YES-DOWN
    tokens need resolved_yes flipped at join time.
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
    ry = res["resolved_yes"]
    if res.get("outcome_dir", "up") != token_outcome_dir:
        ry = not ry
    return ry


def load_gate_trace(days: int) -> list:
    """Load gate_trace rows in terminal zone (25-120s) only. One row per second."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
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
                if 25.0 <= sec <= 120.0:
                    rows.append(r)
    return rows


def first_fire_per_window(gate_rows: list) -> list:
    """Deduplicate to one row per (token_id, window_end_ts) — the first tick in terminal zone.

    Analysis must be one-row-per-window to avoid double-counting tokens that
    spend many seconds failing the same gate (per shadow_unique_window rule).
    """
    seen = {}
    for r in sorted(gate_rows, key=lambda x: x["ts_s"]):
        key = (r["token_id"], r["window_end_ts"])
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--min-n", type=int, default=20,
                        help="Minimum n per gate bucket to report")
    args = parser.parse_args()

    print(f"Loading gate_trace + window_resolution (last {args.days} days)...")
    resolutions = load_resolutions(args.days)
    gate_rows = load_gate_trace(args.days)
    print(f"  gate_trace rows (terminal zone): {len(gate_rows)}")

    first_fires = first_fire_per_window(gate_rows)
    print(f"  unique token×windows (first-fire dedup): {len(first_fires)}")
    print(f"  resolution outcomes available: {len(resolutions)}")

    # Join to resolution
    joined = []
    unresolved = 0
    for r in first_fires:
        key = (r["condition_id"], r["window_end_ts"])
        if key not in resolutions:
            unresolved += 1
            continue
        r = dict(r)
        r["resolved_yes"] = direction_aware_resolved_yes(
            resolutions[key], r.get("outcome_dir", "up")
        )
        joined.append(r)
    print(f"  joined: {len(joined)} | unresolved (no kline yet): {unresolved}")

    if not joined:
        print("No joined data. Ensure window_resolution.jsonl has data.")
        return

    # Baseline: overall YES rate across all terminal-zone tokens
    baseline_yes = sum(1 for r in joined if r["resolved_yes"]) / len(joined)
    print(f"\nBaseline YES rate (all terminal-zone first-fires): {baseline_yes:.1%}  n={len(joined)}")

    # Separate gate-pass vs gate-fail
    passed = [r for r in joined if r["all_pass"]]
    rejected = [r for r in joined if not r["all_pass"]]
    if passed:
        pass_yes = sum(1 for r in passed if r["resolved_yes"]) / len(passed)
        print(f"Gate-PASS cohort YES rate: {pass_yes:.1%}  n={len(passed)}")
    if rejected:
        rej_yes = sum(1 for r in rejected if r["resolved_yes"]) / len(rejected)
        print(f"Gate-REJECT cohort YES rate: {rej_yes:.1%}  n={len(rejected)}")

    # Per first_failed_gate analysis
    print(f"\n=== Per-gate rejection analysis (one-row-per-window, n≥{args.min_n}) ===")
    print(f"  edge_impact = YES_rate_of_rejected − baseline ({baseline_yes:.1%})")
    print(f"  negative → gate rejects tokens with LOWER YES rate → correctly filtering losers → KEEP")
    print(f"  positive → gate rejects tokens with HIGHER YES rate → filtering winners → RELAX")
    print()
    print(f"{'Gate':<22} {'n_rej':>7} {'YES%':>7} {'edge_impact':>12} {'verdict':>10}")
    print("-" * 65)

    by_gate = defaultdict(list)
    for r in rejected:
        ffg = r.get("first_failed_gate") or "unknown"
        by_gate[ffg].append(r["resolved_yes"])

    for gate, outcomes in sorted(by_gate.items(), key=lambda x: -len(x[1])):
        n = len(outcomes)
        if n < args.min_n:
            print(f"{gate:<22} {n:>7}  (n<{args.min_n} — insufficient)")
            continue
        yes_rate = sum(outcomes) / n
        impact = yes_rate - baseline_yes
        # Positive impact = gate rejects tokens that resolve YES → gate filters winners → relax
        # Negative impact = gate rejects tokens that resolve NO  → gate filters losers → keep
        verdict = "RELAX?" if impact > 0.03 else ("KEEP" if impact < -0.03 else "neutral")
        print(f"{gate:<22} {n:>7} {yes_rate:>6.1%} {impact:>+11.1%}  {verdict:>10}")

    # Gate interaction: what fraction of rejections fail ONLY one gate?
    print("\n=== Gate rejection breakdown (rejected tokens, by gate combo) ===")
    combo_counts = defaultdict(int)
    for r in rejected:
        gates = r.get("gate_results", {})
        failing = tuple(sorted(k for k, v in gates.items() if v != "PASS"))
        combo_counts[failing] += 1
    top = sorted(combo_counts.items(), key=lambda x: -x[1])[:10]
    print(f"{'Failed gates':<45} {'n':>7}")
    print("-" * 55)
    for combo, cnt in top:
        label = ", ".join(combo) if combo else "(none)"
        print(f"{label:<45} {cnt:>7}")

    # Entry-timing: YES rate by seconds_to_resolution bucket at first-fire
    print("\n=== YES rate by seconds_to_resolution at first terminal-zone entry ===")
    print(f"{'sec bucket':<15} {'n':>7} {'YES%':>7} {'gate_pass%':>11}")
    print("-" * 45)
    buckets = [(120, 90), (90, 75), (75, 60), (60, 45), (45, 30), (30, 25)]
    for hi, lo in buckets:
        subset = [r for r in joined if lo <= r["seconds_to_resolution"] <= hi]
        if not subset:
            continue
        n = len(subset)
        yes = sum(1 for r in subset if r["resolved_yes"]) / n
        gp = sum(1 for r in subset if r["all_pass"]) / n
        print(f"{lo}-{hi}s{'':<10} {n:>7} {yes:>6.1%} {gp:>10.1%}")


if __name__ == "__main__":
    main()
