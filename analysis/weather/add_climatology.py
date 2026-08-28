"""
Add _climatology to skill_matrix.json: monthly mean/sigma of observed ASOS max temps.

Used by the Upstream Oracle strategy to compute anomaly z-scores:
    z = (observed_max - mean_max_c) / sigma_obs

This is NOT forecast error — it is the distribution of actual observed temperatures,
giving us the baseline to detect when an upstream city is running anomalously hot/cold.

Usage:
    python3 -m analysis.weather.add_climatology [--year-start 2015] [--dry-run]
    python3 -m analysis.weather.add_climatology --city dallas
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.build_skill_matrix import fetch_asos_daily_max

SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
SIGMA_FLOOR = 0.30
MIN_N_REPORT = 20
CLIM_KEY = "_climatology"


def compute_climatology(asos: dict[str, float]) -> dict[str, dict]:
    """
    From {date_str: actual_max_c}, return {month_str: {mean_max_c, sigma_obs, n}}.
    sigma_obs is the observed inter-annual spread (not forecast error).
    """
    monthly: dict[int, list[float]] = defaultdict(list)
    for date_str, temp in asos.items():
        month = int(date_str[5:7])
        monthly[month].append(temp)

    result: dict[str, dict] = {}
    for month, temps in monthly.items():
        if len(temps) < MIN_N_REPORT:
            continue
        mean = statistics.fmean(temps)
        sigma = max(SIGMA_FLOOR, statistics.stdev(temps) if len(temps) >= 2 else SIGMA_FLOOR)
        result[str(month)] = {
            "mean_max_c": round(mean, 2),
            "sigma_obs":  round(sigma, 3),
            "n":          len(temps),
        }
    return result


def run_city(city_slug: str, year_start: int, year_end: int) -> dict[str, dict]:
    station = STATIONS[city_slug]
    print(f"\n  {city_slug.upper()} ({station.icao})", file=sys.stderr)
    print(f"  ASOS {year_start}–{year_end}...", end=" ", flush=True, file=sys.stderr)
    try:
        asos = fetch_asos_daily_max(station.icao, year_start, year_end)
        print(f"{len(asos)} days", flush=True, file=sys.stderr)
    except Exception as e:
        print(f"ERROR: {e}", flush=True, file=sys.stderr)
        return {}

    if len(asos) < 100:
        print(f"  insufficient ASOS ({len(asos)} days)", file=sys.stderr)
        return {}

    clim = compute_climatology(asos)
    if clim:
        sample = "  ".join(
            f"m{m}:μ={v['mean_max_c']:.1f}°C,σ={v['sigma_obs']:.2f}"
            for m, v in sorted(clim.items(), key=lambda x: int(x[0]))[:4]
        )
        print(f"  clim: {sample} ...", file=sys.stderr)
    return clim


def merge_into_matrix(new_clim: dict[str, dict], dry_run: bool = False) -> dict:
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    stations = matrix.setdefault("stations", {})
    added = updated = 0

    for city_slug, monthly in new_clim.items():
        city_data = stations.setdefault(city_slug, {})
        existing = city_data.get(CLIM_KEY, {})
        for mon_str, stats in monthly.items():
            if mon_str in existing:
                updated += 1
            else:
                added += 1
            existing[mon_str] = stats
        city_data[CLIM_KEY] = existing

    matrix["_meta"]["climatology_added"] = date.today().isoformat()
    print(f"\n  climatology cells: {added} added, {updated} updated", file=sys.stderr)

    if dry_run:
        print("  (dry-run — not writing)", file=sys.stderr)
        return matrix

    SKILL_MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
    print(f"  → {SKILL_MATRIX_PATH} updated", file=sys.stderr)
    return matrix


def _cli():
    ap = argparse.ArgumentParser(description="Add observed-temp climatology to skill_matrix.json")
    ap.add_argument("--year-start", type=int, default=2015)
    ap.add_argument("--year-end",   type=int, default=2024)
    ap.add_argument("--city",       action="append", dest="cities")
    ap.add_argument("--dry-run",    action="store_true")
    args = ap.parse_args()

    cities = args.cities or list(STATIONS.keys())
    print(f"Climatology: {len(cities)} cities, {args.year_start}–{args.year_end}", file=sys.stderr)

    all_new: dict[str, dict] = {}
    for slug in cities:
        if slug not in STATIONS:
            print(f"  SKIP {slug}: not in STATIONS", file=sys.stderr)
            continue
        clim = run_city(slug, args.year_start, args.year_end)
        if clim:
            all_new[slug] = clim
        time.sleep(0.3)

    merge_into_matrix(all_new, dry_run=args.dry_run)
    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    _cli()
