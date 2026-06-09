"""
Backtest: STRAT_5 bivariate-normal vs climatological baseline vs NWP proxy.

Question: when upstream city hits z > TRIGGER_Z, does the bivariate-normal
conditional model accurately predict downstream city outcomes the next day?
Does it add signal beyond what the unconditional climatology already implies?

Three models compared per (upstream, downstream, trigger event):
  1. Climatological baseline  — P(bucket) from unconditional Normal(mean, sigma_obs)
  2. STRAT_5 bivariate-normal — P(bucket) conditional on upstream z-score
  3. NWP proxy               — approximate NWP fair_prob using skill_matrix BLUE ensemble

Output:
  - Per-pair calibration: predicted P vs actual hit rate (binned)
  - Brier score comparison across the three models
  - Hit rate table: when z_up > 2σ, what % of downstream outcomes resolve hot/cold?
  - SYNOPTIC_R validation: does r=0.5 match the empirical conditional mean shift?

Usage:
    python3 -m analysis.weather.oracle_backtest [--months 6,7,8,9] [--trigger-z 2.0]
    python3 -m analysis.weather.oracle_backtest --pair dallas austin
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

CACHE_DIR         = Path(__file__).parent.parent.parent / "logs" / "asos_cache"
SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
YEAR_START = 2015
YEAR_END   = 2023   # hold 2024 as OOS

# Outcome definition: "anomalous hot/cold" means |z| > this in downstream city
OUTCOME_Z = 1.0   # ~top/bottom 16% of distribution — roughly where the market has edge

# Calibration bins
CAL_BINS = [0.0, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 1.01]


def _phi(x: float) -> float:
    from math import erf, sqrt
    return 0.5 * (1 + erf(x / sqrt(2)))


def _p_bucket(lo_z: float | None, hi_z: float | None) -> float:
    """P(z in [lo_z, hi_z]) under standard Normal."""
    p_hi = 1.0 if hi_z is None else _phi(hi_z)
    p_lo = 0.0 if lo_z is None else _phi(lo_z)
    return max(0.0, p_hi - p_lo)


def load_asos(city_slug: str) -> dict[str, float]:
    """Load cached ASOS temps. Falls back to fetching if not cached."""
    from analysis.weather.stations import STATIONS
    from analysis.weather.build_skill_matrix import fetch_asos_daily_max
    import time

    station = STATIONS.get(city_slug)
    if station is None:
        return {}
    cp = CACHE_DIR / f"{station.icao}_{YEAR_START}_{YEAR_END}.json"
    # cache uses 2015-2024 key — try both
    cp_alt = CACHE_DIR / f"{station.icao}_2015_2024.json"
    if cp_alt.exists():
        return json.loads(cp_alt.read_text())
    if cp.exists():
        return json.loads(cp.read_text())
    print(f"  fetching {city_slug}...", flush=True)
    data = fetch_asos_daily_max(station.icao, YEAR_START, YEAR_END)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data))
    time.sleep(0.3)
    return data


def load_climatology() -> dict:
    """Load _climatology from skill_matrix: {slug: {month_str: {mean_max_c, sigma_obs}}}"""
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    return {
        slug: data.get("_climatology", {})
        for slug, data in matrix.get("stations", {}).items()
    }


def load_nwp_sigma(city_slug: str, month: int) -> float | None:
    """
    Best-available NWP ensemble sigma from skill_matrix (BLUE estimate).
    Uses the minimum sigma across models as the tightest NWP estimate.
    """
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    city_data = matrix.get("stations", {}).get(city_slug, {})
    sigmas = []
    for model, monthly in city_data.items():
        if model.startswith("_"):
            continue
        cell = monthly.get(str(month))
        if cell and cell.get("n", 0) >= 10:
            sigmas.append(cell["sigma"])
    if not sigmas:
        return None
    # BLUE ensemble sigma ~ min individual sigma (ensemble reduces error)
    return min(sigmas)


def run_pair_backtest(
    upstream: str,
    downstream: str,
    months: set[int],
    trigger_z: float,
    synoptic_r: float,
    clim: dict,
) -> dict:
    """
    Run backtest for one upstream→downstream pair.
    Returns summary stats dict.
    """
    asos_up = load_asos(upstream)
    asos_dn = load_asos(downstream)
    clim_up = clim.get(upstream, {})
    clim_dn = clim.get(downstream, {})

    events: list[dict] = []

    for d_str, up_temp in asos_up.items():
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if d.year > YEAR_END:
            continue
        month = d.month
        if month not in months:
            continue

        cell_up = clim_up.get(str(month))
        cell_dn = clim_dn.get(str(month))
        if not cell_up or not cell_dn:
            continue

        z_up = (up_temp - cell_up["mean_max_c"]) / cell_up["sigma_obs"]
        if abs(z_up) < trigger_z:
            continue

        direction = "hot" if z_up > 0 else "cold"

        # Next day downstream actual
        next_d = (d + timedelta(days=1)).isoformat()
        dn_temp = asos_dn.get(next_d)
        if dn_temp is None:
            continue

        z_dn = (dn_temp - cell_dn["mean_max_c"]) / cell_dn["sigma_obs"]

        # Outcome: did downstream move in the predicted direction by > OUTCOME_Z?
        if direction == "hot":
            outcome = 1 if z_dn > OUTCOME_Z else 0
        else:
            outcome = 1 if z_dn < -OUTCOME_Z else 0

        # --- Model 1: Climatological baseline (no conditioning) ---
        sigma_dn = cell_dn["sigma_obs"]
        if direction == "hot":
            p_clim = 1 - _phi(OUTCOME_Z)        # P(z > OUTCOME_Z) unconditional
        else:
            p_clim = _phi(-OUTCOME_Z)

        # --- Model 2: STRAT_5 bivariate-normal ---
        signed_z = z_up if direction == "hot" else -abs(z_up)
        mu_cond    = cell_dn["mean_max_c"] + synoptic_r * signed_z * sigma_dn
        sigma_cond = sigma_dn * math.sqrt(1 - synoptic_r ** 2)
        threshold_temp = cell_dn["mean_max_c"] + OUTCOME_Z * sigma_dn

        if direction == "hot":
            p_strat5 = 1 - _phi((threshold_temp - mu_cond) / sigma_cond)
        else:
            p_strat5 = _phi((-threshold_temp + cell_dn["mean_max_c"] * 2 - mu_cond) / sigma_cond)
            p_strat5 = _phi((cell_dn["mean_max_c"] - OUTCOME_Z * sigma_dn - mu_cond) / sigma_cond)

        # --- Model 3: NWP proxy ---
        # NWP knows the climatological mean but not the upstream signal.
        # Approximate NWP fair_prob using sigma from skill_matrix (tighter than sigma_obs).
        nwp_sigma = load_nwp_sigma(downstream, month) or sigma_dn
        # NWP mean ≈ climatological mean (best we can do without historical NWP series)
        if direction == "hot":
            p_nwp = 1 - _phi(OUTCOME_Z * (sigma_dn / nwp_sigma))
        else:
            p_nwp = _phi(-OUTCOME_Z * (sigma_dn / nwp_sigma))

        events.append({
            "date":      d_str,
            "month":     month,
            "z_up":      round(z_up, 3),
            "z_dn":      round(z_dn, 3),
            "direction": direction,
            "outcome":   outcome,
            "p_clim":    round(p_clim, 4),
            "p_strat5":  round(p_strat5, 4),
            "p_nwp":     round(p_nwp, 4),
        })

    if not events:
        return {"pair": f"{upstream}→{downstream}", "n": 0}

    n = len(events)
    hit_rate = statistics.fmean(e["outcome"] for e in events)

    def brier(pkey: str) -> float:
        return statistics.fmean((e[pkey] - e["outcome"]) ** 2 for e in events)

    def mean_p(pkey: str) -> float:
        return statistics.fmean(e[pkey] for e in events)

    # Calibration: bin by p_strat5, compute actual hit rate per bin
    cal: dict[str, dict] = {}
    for i in range(len(CAL_BINS) - 1):
        lo, hi = CAL_BINS[i], CAL_BINS[i + 1]
        bucket_events = [e for e in events if lo <= e["p_strat5"] < hi]
        if bucket_events:
            cal[f"[{lo:.2f},{hi:.2f})"] = {
                "n":       len(bucket_events),
                "pred":    round(statistics.fmean(e["p_strat5"] for e in bucket_events), 3),
                "actual":  round(statistics.fmean(e["outcome"]  for e in bucket_events), 3),
            }

    # Conditional mean z_dn given z_up > trigger — measures empirical synoptic_r
    z_dn_vals  = [e["z_dn"] if e["direction"] == "hot" else -e["z_dn"] for e in events]
    z_up_vals  = [abs(e["z_up"]) for e in events]
    empirical_r = _pearson(z_up_vals, z_dn_vals)

    return {
        "pair":        f"{upstream}→{downstream}",
        "n":           n,
        "hit_rate":    round(hit_rate, 4),
        "mean_p_clim":   round(mean_p("p_clim"),  4),
        "mean_p_strat5": round(mean_p("p_strat5"), 4),
        "mean_p_nwp":    round(mean_p("p_nwp"),   4),
        "brier_clim":    round(brier("p_clim"),   4),
        "brier_strat5":  round(brier("p_strat5"), 4),
        "brier_nwp":     round(brier("p_nwp"),    4),
        "empirical_r":   round(empirical_r, 3),
        "calibration":   cal,
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num  = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return num / denom if denom > 0 else 0.0


def print_results(results: list[dict]) -> None:
    results = [r for r in results if r["n"] > 0]
    if not results:
        print("No events found.")
        return

    print(f"\n{'Pair':<25} {'n':>5}  {'HitRate':>8}  "
          f"{'P_clim':>7}  {'P_S5':>7}  {'P_NWP':>7}  "
          f"{'Brier_clim':>10}  {'Brier_S5':>8}  {'Brier_NWP':>9}  "
          f"{'EmpR':>6}")
    print("─" * 110)

    for r in sorted(results, key=lambda x: -x["n"]):
        skill_vs_clim = r["brier_clim"] - r["brier_strat5"]   # positive = S5 better
        skill_vs_nwp  = r["brier_nwp"]  - r["brier_strat5"]
        flag = "★" if skill_vs_clim > 0.005 and r["n"] >= 20 else " "
        print(f"  {r['pair']:<23} {r['n']:>5}  "
              f"{r['hit_rate']:>8.3f}  "
              f"{r['mean_p_clim']:>7.3f}  {r['mean_p_strat5']:>7.3f}  {r['mean_p_nwp']:>7.3f}  "
              f"{r['brier_clim']:>10.4f}  {r['brier_strat5']:>8.4f}  {r['brier_nwp']:>9.4f}  "
              f"{r['empirical_r']:>6.3f} {flag}")

    print()
    # Summary Brier skill score
    total_n     = sum(r["n"] for r in results)
    avg_brier_clim  = sum(r["brier_clim"]   * r["n"] for r in results) / total_n
    avg_brier_s5    = sum(r["brier_strat5"] * r["n"] for r in results) / total_n
    avg_brier_nwp   = sum(r["brier_nwp"]   * r["n"] for r in results) / total_n
    avg_emp_r       = statistics.fmean(r["empirical_r"] for r in results if r["n"] >= 10)

    print(f"  Weighted avg Brier:  clim={avg_brier_clim:.4f}  STRAT5={avg_brier_s5:.4f}  NWP={avg_brier_nwp:.4f}")
    print(f"  STRAT5 skill vs clim: {(avg_brier_clim - avg_brier_s5)/avg_brier_clim*100:+.1f}%   "
          f"vs NWP: {(avg_brier_nwp - avg_brier_s5)/avg_brier_nwp*100:+.1f}%")
    print(f"  Mean empirical r (conditional on |z|>{args_trigger_z:.1f}): {avg_emp_r:.3f}  "
          f"(model uses SYNOPTIC_R=0.50)")
    print()

    # Calibration for first high-n pair
    best = max(results, key=lambda x: x["n"])
    print(f"  Calibration for {best['pair']} (n={best['n']}):")
    print(f"  {'Bin':<15} {'n':>5}  {'Pred':>6}  {'Actual':>6}  {'Diff':>6}")
    for bin_label, cal in best["calibration"].items():
        diff = cal["actual"] - cal["pred"]
        flag = " ← over" if diff < -0.05 else (" ← under" if diff > 0.05 else "")
        print(f"    {bin_label:<13} {cal['n']:>5}  {cal['pred']:>6.3f}  {cal['actual']:>6.3f}  "
              f"{diff:>+6.3f}{flag}")


args_trigger_z = 2.0   # module-level so print_results can access it


def _cli():
    global args_trigger_z
    ap = argparse.ArgumentParser(description="Oracle backtest: STRAT_5 vs baseline vs NWP proxy")
    ap.add_argument("--months",    default="6,7,8,9",
                    help="comma-separated months (default summer 6-9)")
    ap.add_argument("--trigger-z", type=float, default=2.0,
                    help="minimum upstream z-score to trigger (default 2.0)")
    ap.add_argument("--synoptic-r", type=float, default=0.5,
                    help="synoptic correlation parameter (default 0.50)")
    ap.add_argument("--pair",      nargs=2, metavar=("UP", "DN"),
                    help="single pair only, e.g. --pair dallas chicago")
    ap.add_argument("--oos",       action="store_true",
                    help="use 2024 as test set instead of 2015-2023")
    args = ap.parse_args()

    args_trigger_z = args.trigger_z
    months = set(int(m) for m in args.months.split(",") if m.strip().isdigit())

    global YEAR_START, YEAR_END
    if args.oos:
        YEAR_START = YEAR_END = 2024
        print("=== OUT-OF-SAMPLE TEST: 2024 only ===")

    clim = load_climatology()

    from strategy.upstream_map import DOWNSTREAM_SUMMER
    if args.pair:
        pairs = [tuple(args.pair)]
    else:
        pairs = [
            (up, dn)
            for up, dns in DOWNSTREAM_SUMMER.items()
            for dn in dns
        ]

    print(f"\nOracle backtest: {len(pairs)} pairs, months={sorted(months)}, "
          f"trigger_z={args.trigger_z}, synoptic_r={args.synoptic_r}")
    print(f"Outcome definition: downstream |z| > {OUTCOME_Z:.1f}σ in predicted direction\n")

    results = []
    for up, dn in pairs:
        if up not in clim or dn not in clim:
            continue
        print(f"  {up}→{dn}...", end=" ", flush=True)
        r = run_pair_backtest(up, dn, months, args.trigger_z, args.synoptic_r, clim)
        print(f"n={r['n']}", flush=True)
        results.append(r)

    print_results(results)


if __name__ == "__main__":
    _cli()
