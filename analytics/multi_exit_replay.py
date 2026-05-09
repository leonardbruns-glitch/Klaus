"""Multi-exit replay on shadow hold_path data.

For each virtual position (one per token×window in the terminal zone), applies
~15 exit rules and reports which captures the most PnL.

EXIT RULES TESTED:
  Price targets (vs fire_ask):  PT88, PT90, PT92, PT95, PT97, PT99
  Time exits (seconds_to_res):  T45, T30, T20, T10
  Trailing from MFE:            trail3, trail5, trail8  (exit when pnl drops X pp from mfe)
  OB depth collapse:            depth_collapse (ob_depth_delta_1s < -50 for 2 consecutive ticks)
  Baseline:                     HOLD_TO_CLOSE (window_outcome_price proxy)

USAGE:
  python3 analytics/multi_exit_replay.py [--days 3] [--gate-filter gated|free|all]

  --gate-filter gated  : only vpos where gate_all_pass_at_open=True (live bot cohort)
  --gate-filter free   : only vpos where gate_all_pass_at_open=False (gate-rejected cohort)
  --gate-filter all    : both (default)

OUTPUT:
  Table: exit_rule | n | wr_pct | avg_pnl_pct | p10 | p50 | p90 | cat_rate
  cat_rate = fraction of exits with pnl_pct <= -10% (catastrophic)
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

SHADOW_ROOT = "logs/shadow/hot"
RESOLUTION_FILE_PATTERN = os.path.join(SHADOW_ROOT, "*", "window_resolution.jsonl")
HOLDPATH_FILE_PATTERN   = os.path.join(SHADOW_ROOT, "*", "hold_path.jsonl")

# Price-target thresholds (fraction of fire_ask, NOT absolute price)
PT_RULES = {
    "PT88": 1.0 * 0.88,   # exit when bid >= fire_ask * factor ... wait, these are absolute
}
# PT rules: exit when bid >= threshold (absolute, matching live bot convention)
PT_THRESHOLDS = {
    "PT88": 0.88,
    "PT90": 0.90,
    "PT92": 0.92,
    "PT95": 0.95,
    "PT97": 0.97,
    "PT99": 0.99,
}
# Time-exit rules: exit when seconds_to_resolution <= N
TIME_EXITS = {"T45": 45, "T30": 30, "T20": 20, "T10": 10}
# Trailing-stop rules: exit when (mfe - pnl_pct) >= N percentage points
TRAIL_RULES = {"trail3pp": 3.0, "trail5pp": 5.0, "trail8pp": 8.0}
# OB depth collapse: exit when ob_depth_delta_1s < threshold for 2 consecutive ticks
DEPTH_COLLAPSE_THRESH = -50.0


def load_resolutions(days: int) -> dict:
    """Returns {(condition_id, window_end_ts): resolved_yes}."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = {}
    for f in sorted(glob.glob(RESOLUTION_FILE_PATTERN)):
        date_str = f.split(os.sep)[-2]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        with open(f) as fh:
            for line in fh:
                r = json.loads(line)
                out[(r["condition_id"], r["window_end_ts"])] = r["resolved_yes"]
    return out


def load_holdpath(days: int, gate_filter: str,
                  config_effective_from: int = None,
                  fire_rem_max: float = None) -> dict:
    """Returns {(token_id, window_end_ts): sorted list of tick dicts}.

    Filters:
    - gate_filter: "gated"|"free"|"all" — uses gate_all_pass_at_open from hold_path
    - config_effective_from: Unix ts cutoff on fire_ts_s (intra-day gate drift)
    - fire_rem_max: max fire_sec_to_res — exclude entries fired outside live entry zone
      (pre-2026-05-08 hold_path rows may have fire_sec_to_res in 90-120s range)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    positions = defaultdict(list)
    for f in sorted(glob.glob(HOLDPATH_FILE_PATTERN)):
        date_str = f.split(os.sep)[-2]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        with open(f) as fh:
            for line in fh:
                r = json.loads(line)
                if gate_filter == "gated" and not r.get("gate_all_pass_at_open"):
                    continue
                if gate_filter == "free" and r.get("gate_all_pass_at_open"):
                    continue
                if config_effective_from is not None and r.get("fire_ts_s", 0) < config_effective_from:
                    continue
                if fire_rem_max is not None and r.get("fire_sec_to_res", 0) > fire_rem_max:
                    continue
                key = (r["token_id"], r["window_end_ts"])
                positions[key].append(r)
    # Sort each position by ts_s
    for key in positions:
        positions[key].sort(key=lambda x: x["ts_s"])
    return positions


def apply_exit_rules(ticks: list) -> dict:
    """Given sorted tick list for one virtual position, return exit pnl_pct per rule."""
    results = {}
    depth_collapse_streak = 0

    # Walk ticks in order; each rule fires at most once (first trigger wins)
    pt_remaining = set(PT_THRESHOLDS)
    time_remaining = set(TIME_EXITS)
    trail_remaining = set(TRAIL_RULES)
    depth_fired = False

    for tick in ticks:
        bid = tick["bid"]
        sec = tick["seconds_to_resolution"]
        pnl = tick["pnl_pct"]
        mfe = tick["mfe"]
        depth_delta = tick.get("ob_depth_delta_1s", 0.0)

        # PT rules
        for rule in list(pt_remaining):
            if bid >= PT_THRESHOLDS[rule]:
                results[rule] = pnl
                pt_remaining.discard(rule)

        # Time exits
        for rule in list(time_remaining):
            if sec <= TIME_EXITS[rule]:
                results[rule] = pnl
                time_remaining.discard(rule)

        # Trailing stop (fires when pnl drops trail_pp below MFE)
        for rule in list(trail_remaining):
            if mfe >= 2.0 and (mfe - pnl) >= TRAIL_RULES[rule]:
                results[rule] = pnl
                trail_remaining.discard(rule)

        # OB depth collapse (2 consecutive ticks with depth_delta < threshold)
        if not depth_fired:
            if depth_delta < DEPTH_COLLAPSE_THRESH:
                depth_collapse_streak += 1
            else:
                depth_collapse_streak = 0
            if depth_collapse_streak >= 2:
                results["depth_collapse"] = pnl
                depth_fired = True

    # Baseline: last tick bid (closest to window close)
    last = ticks[-1]
    results["HOLD_TO_CLOSE"] = last["pnl_pct"]

    return results


def summarise(rule_results: dict) -> None:
    """Print summary table."""
    import statistics

    all_rules = (
        list(PT_THRESHOLDS) + list(TIME_EXITS) + list(TRAIL_RULES) +
        ["depth_collapse", "HOLD_TO_CLOSE"]
    )

    print(f"\n{'Rule':<18} {'n':>6} {'fire%':>7} {'WR%':>7} {'avg_pnl':>8} "
          f"{'p10':>7} {'p50':>7} {'p90':>7} {'cat%':>7}")
    print("-" * 80)

    total_vpos = rule_results.pop("_total_vpos", 0)

    for rule in all_rules:
        pnls = rule_results.get(rule, [])
        n = len(pnls)
        if n == 0:
            print(f"{rule:<18} {'0':>6}")
            continue
        fire_pct = n / total_vpos * 100 if total_vpos else 0
        wr = sum(1 for p in pnls if p > 0) / n * 100
        avg = sum(pnls) / n
        sorted_p = sorted(pnls)
        p10 = sorted_p[max(0, int(n * 0.10))]
        p50 = sorted_p[n // 2]
        p90 = sorted_p[min(n - 1, int(n * 0.90))]
        cat = sum(1 for p in pnls if p <= -10.0) / n * 100
        print(f"{rule:<18} {n:>6} {fire_pct:>6.1f}% {wr:>6.1f}% {avg:>+7.2f}% "
              f"{p10:>+6.2f}% {p50:>+6.2f}% {p90:>+6.2f}% {cat:>6.1f}%")


def summarise_full_cohort(full_data: dict) -> None:
    """Print full-cohort table — each rule + HOLD_TO_CLOSE fallback for non-fires.

    Apples-to-apples comparison: every rule scored on every position. If the
    rule didn't fire, the position falls through to HOLD_TO_CLOSE (last tick),
    the shadow analog of the live +30s timeout.
    """
    all_rules = (
        list(PT_THRESHOLDS) + list(TIME_EXITS) + list(TRAIL_RULES) +
        ["depth_collapse", "HOLD_TO_CLOSE"]
    )
    print(f"\n{'Rule':<18} {'n':>6} {'fire%':>7} {'WR%':>7} {'avg_pnl':>8} "
          f"{'p10':>7} {'p50':>7} {'p90':>7} {'cat%':>7}")
    print("-" * 80)
    for rule in all_rules:
        rows = full_data.get(rule, [])
        n = len(rows)
        if n == 0:
            print(f"{rule:<18} {'0':>6}")
            continue
        pnls = [p for p, _ in rows]
        n_fired = sum(1 for _, f in rows if f)
        fire_pct = n_fired / n * 100
        wr = sum(1 for p in pnls if p > 0) / n * 100
        avg = sum(pnls) / n
        sorted_p = sorted(pnls)
        p10 = sorted_p[max(0, int(n * 0.10))]
        p50 = sorted_p[n // 2]
        p90 = sorted_p[min(n - 1, int(n * 0.90))]
        cat = sum(1 for p in pnls if p <= -10.0) / n * 100
        print(f"{rule:<18} {n:>6} {fire_pct:>6.1f}% {wr:>6.1f}% {avg:>+7.2f}% "
              f"{p10:>+6.2f}% {p50:>+6.2f}% {p90:>+6.2f}% {cat:>6.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--gate-filter", choices=["gated", "free", "all"], default="all")
    parser.add_argument("--config-effective-from", type=int, default=None,
                        help="Unix ts cutoff on fire_ts_s (handles intra-day gate config drift)")
    parser.add_argument("--fire-rem-max", type=float, default=90.0,
                        help="Max fire_sec_to_res (default 90 = live entry zone max). Set None/0 to disable.")
    args = parser.parse_args()
    fire_rem_max = args.fire_rem_max if args.fire_rem_max and args.fire_rem_max > 0 else None

    print(f"Loading hold_path data (last {args.days} days, gate_filter={args.gate_filter}, "
          f"config_from={args.config_effective_from}, fire_rem_max={fire_rem_max})...")
    resolutions = load_resolutions(args.days)
    positions = load_holdpath(args.days, args.gate_filter,
                               args.config_effective_from, fire_rem_max)

    if not positions:
        print("No hold_path data found. Run after shadow Phase 2 has been collecting for a few hours.")
        sys.exit(0)

    print(f"Virtual positions loaded: {len(positions)}")
    print(f"Resolution outcomes loaded: {len(resolutions)}")

    rule_pnls = defaultdict(list)
    rule_pnls["_total_vpos"] = len(positions)
    full_data = defaultdict(list)  # rule -> [(pnl, fired_bool), ...] for full-cohort scoring
    optional_rules = list(PT_THRESHOLDS) + list(TIME_EXITS) + list(TRAIL_RULES) + ["depth_collapse"]
    skipped = 0

    for (token_id, wend), ticks in positions.items():
        if len(ticks) < 3:
            skipped += 1
            continue
        exit_pnls = apply_exit_rules(ticks)
        for rule, pnl in exit_pnls.items():
            rule_pnls[rule].append(pnl)
        htc = exit_pnls["HOLD_TO_CLOSE"]
        for rule in optional_rules:
            if rule in exit_pnls:
                full_data[rule].append((exit_pnls[rule], True))
            else:
                full_data[rule].append((htc, False))
        full_data["HOLD_TO_CLOSE"].append((htc, True))

    print(f"Skipped (< 3 ticks): {skipped}")

    # Fired-only stats (rule pnl conditional on rule firing)
    print(f"\n=== Multi-Exit Replay — FIRED-ONLY  gate_filter={args.gate_filter}, n_vpos={len(positions)} ===")
    summarise(dict(rule_pnls))

    # Full-cohort stats (rule pnl if fired, else HOLD_TO_CLOSE fallback) — apples-to-apples
    print(f"\n=== Multi-Exit Replay — FULL-COHORT (rule + HOLD_TO_CLOSE fallback)  n_vpos={len(positions)} ===")
    summarise_full_cohort(dict(full_data))

    # Entry-timing analysis: pnl_pct at HOLD_TO_CLOSE grouped by fire_sec_to_res bucket
    all_ticks_last = []
    for ticks in positions.values():
        if ticks:
            first = ticks[0]
            last = ticks[-1]
            all_ticks_last.append((first.get("fire_sec_to_res", 0), last["pnl_pct"],
                                   first.get("gate_all_pass_at_open", False)))

    print("\n=== Entry timing: HOLD_TO_CLOSE pnl by fire_sec_to_res bucket ===")
    buckets = [(120, 90), (90, 75), (75, 60), (60, 45), (45, 30), (30, 25)]
    print(f"{'Entry rem bucket':<20} {'n':>6} {'WR%':>7} {'avg_pnl':>9} {'gate_pass%':>11}")
    print("-" * 60)
    for hi, lo in buckets:
        subset = [(pnl, gp) for (sec, pnl, gp) in all_ticks_last if lo <= sec <= hi]
        if not subset:
            continue
        n = len(subset)
        wr = sum(1 for p, _ in subset if p > 0) / n * 100
        avg = sum(p for p, _ in subset) / n
        gp = sum(1 for _, gp in subset if gp) / n * 100
        print(f"{lo}-{hi}s{'':<16} {n:>6} {wr:>6.1f}% {avg:>+8.2f}% {gp:>10.1f}%")


if __name__ == "__main__":
    main()
