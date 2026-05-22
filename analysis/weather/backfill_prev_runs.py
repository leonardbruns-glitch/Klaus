"""
Backfill skill_matrix.json with recent (Jan 1 2026 → yesterday) D+1 operational
forecasts from the Open-Meteo Previous Runs API for ALL live models.

The existing matrix was built from the archive API (2021-2025 reanalysis-style NWP).
Previous Runs gives us the ACTUAL issued D+1 forecasts — same signal the live bot uses.
This adds ~20-40 data points per (city, model, month) for Jan-May 2026, which are
recency-upweighted when merged so recent model behavior dominates calibration.

Merge rule: combined stats = recency-weighted blend where 2026 data gets 3× weight
per day vs the 5yr historical baseline. Uses proper variance combination formula.

Usage:
    python3 -m analysis.weather.backfill_prev_runs [--days 142] [--recency 3.0] [--dry-run]
    python3 -m analysis.weather.backfill_prev_runs --city buenos-aires --days 60
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.backtest_6mo import fetch_d1_forecasts, fetch_asos_daily_max

SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
SIGMA_FLOOR   = 0.30
MIN_N_REPORT  = 5
RECENCY_WEIGHT = 3.0   # each 2026 data-point counts this many times vs historical

# All 9 models in live FORECAST_MODELS string
LIVE_MODELS = (
    "gfs_seamless",
    "icon_seamless",
    "ecmwf_ifs025",
    "gem_seamless",
    "jma_seamless",
    "ukmo_seamless",
    "meteofrance_seamless",
    "ecmwf_aifs025",
    "gfs_graphcast025",
)

# Models that are global (not region-specific in previous runs)
# jma / ukmo / meteofrance are globally available in previous-runs even if
# we only use them for specific regions at runtime.
PREV_RUNS_MODELS = LIVE_MODELS


def _merge_cells(old: dict, new: dict, recency_weight: float = RECENCY_WEIGHT) -> dict:
    """
    Combine historical (old) and recent (new) {bias, sigma, n} using recency-weighted
    variance combination. Each day in 'new' is weighted recency_weight× vs 'old'.

    Math: treat as mixture of two Gaussians weighted by effective sample size.
    """
    n1, n2 = old["n"], new["n"]
    b1, b2 = old["bias"], new["bias"]
    s1, s2 = old["sigma"], new["sigma"]

    eff1 = float(n1)
    eff2 = float(n2) * recency_weight
    total_eff = eff1 + eff2
    w1, w2 = eff1 / total_eff, eff2 / total_eff

    bias_c = w1 * b1 + w2 * b2
    # Total variance = weighted within-group variance + weighted between-group shift
    var = (w1 * (s1 ** 2 + (b1 - bias_c) ** 2) +
           w2 * (s2 ** 2 + (b2 - bias_c) ** 2))
    sigma = max(SIGMA_FLOOR, math.sqrt(var))

    return {
        "bias":  round(bias_c, 3),
        "sigma": round(sigma, 3),
        "n":     n1 + n2,
    }


def compute_recent_cells(city_slug: str, days: int) -> dict[str, dict[str, dict]]:
    """
    Fetch D+1 forecasts from Previous Runs API and ASOS actuals for the past `days` days.
    Returns {model: {month_str: {bias, sigma, n}}}.
    """
    station = STATIONS[city_slug]
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    print(f"  → {city_slug.upper()} ({station.icao})  {start} → {end}", file=sys.stderr)

    d1 = fetch_d1_forecasts(
        station.lat, station.lon, PREV_RUNS_MODELS,
        start.isoformat(), end.isoformat(),
        cache_key=f"prevrun_all_{city_slug}_{start}_{end}",
    )
    asos = fetch_asos_daily_max(
        station.icao, start.isoformat(), end.isoformat(),
        cache_key=f"asos_recent_{city_slug}_{start}_{end}",
    )

    if not d1 or not asos:
        print(f"     no data", file=sys.stderr)
        return {}

    errors: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for day, models_today in d1.items():
        actual = asos.get(day)
        if actual is None:
            continue
        month = int(day[5:7])
        for model, fc_val in models_today.items():
            if fc_val is not None:
                errors[model][month].append(float(fc_val) - float(actual))

    result: dict[str, dict[str, dict]] = {}
    for model, monthly in errors.items():
        result[model] = {}
        for month, errs in monthly.items():
            if len(errs) < MIN_N_REPORT:
                continue
            bias = statistics.fmean(errs)
            debiased = [e - bias for e in errs]
            sigma = statistics.stdev(debiased) if len(debiased) >= 2 else SIGMA_FLOOR
            sigma = max(SIGMA_FLOOR, sigma)
            result[model][str(month)] = {
                "bias":  round(bias, 3),
                "sigma": round(sigma, 3),
                "n":     len(errs),
            }

    n_cells = sum(len(m) for m in result.values())
    print(f"     {len(result)} models, {n_cells} cells", file=sys.stderr)
    for model, monthly in result.items():
        cells_str = "  ".join(
            f"m{m}:n={v['n']},b={v['bias']:+.2f}" for m, v in sorted(monthly.items(), key=lambda x: int(x[0]))
        )
        print(f"       {model:<30} {cells_str}", file=sys.stderr)
    return result


def merge_into_matrix(
    new_cells: dict[str, dict[str, dict[str, dict]]],
    recency_weight: float = RECENCY_WEIGHT,
    dry_run: bool = False,
) -> dict:
    """
    Merge {city_slug: {model: {month_str: {bias,sigma,n}}}} into skill_matrix.json.
    Existing cells are recency-blended; new cells (no historical) are added as-is.
    """
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    stations = matrix.setdefault("stations", {})

    added = merged = 0
    for city_slug, models in new_cells.items():
        city_data = stations.setdefault(city_slug, {})
        for model, monthly in models.items():
            model_data = city_data.setdefault(model, {})
            for mon_str, new_stats in monthly.items():
                old_stats = model_data.get(mon_str)
                if old_stats and old_stats.get("n", 0) >= MIN_N_REPORT:
                    combined = _merge_cells(old_stats, new_stats, recency_weight)
                    model_data[mon_str] = combined
                    merged += 1
                else:
                    model_data[mon_str] = new_stats
                    added += 1

    notes = matrix.get("_meta", {}).get("notes", "")
    tag = "prev-runs 2026 backfill all models"
    if tag not in notes:
        matrix["_meta"]["notes"] = (notes + f"; {tag}").lstrip("; ")
    matrix["_meta"]["prev_runs_backfill"] = date.today().isoformat()

    print(f"\n  Cells merged: {merged}  |  new cells added: {added}", file=sys.stderr)

    if dry_run:
        print("  (dry-run — not writing)", file=sys.stderr)
        return matrix

    SKILL_MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
    print(f"  → {SKILL_MATRIX_PATH} updated", file=sys.stderr)
    return matrix


def _cli():
    ap = argparse.ArgumentParser(description="Backfill skill matrix from Previous Runs API (all live models)")
    ap.add_argument("--days",     type=int,   default=142,          help="lookback window in days (default 142 = Jan 1 2026)")
    ap.add_argument("--recency",  type=float, default=RECENCY_WEIGHT, help="recency upweight factor (default 3.0)")
    ap.add_argument("--city",     action="append", dest="cities",   help="city slug(s); default=all in STATIONS")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    cities = args.cities or list(STATIONS.keys())
    print(f"Backfilling {len(cities)} cities, {args.days} days, recency×{args.recency}", file=sys.stderr)

    all_new: dict[str, dict] = {}
    for slug in cities:
        if slug not in STATIONS:
            print(f"  SKIP {slug}: not in STATIONS", file=sys.stderr)
            continue
        cells = compute_recent_cells(slug, args.days)
        if cells:
            all_new[slug] = cells
        time.sleep(0.8)

    merge_into_matrix(all_new, recency_weight=args.recency, dry_run=args.dry_run)
    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    _cli()
