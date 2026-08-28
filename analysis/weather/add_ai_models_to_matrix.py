"""
Augment strategy/skill_matrix.json with AIFS + GraphCast skill cells.

These two AI models are in our live ensemble but the existing matrix doesn't
have bias/sigma for them — so WeightedEnsemble assigns them the W_FLOOR=0.03
fallback weight (effectively ignored).

This script:
  1. Pulls 6mo of D+1 hourly previous_day1 forecasts for both models, per city.
  2. Aggregates to daily max, pairs with ASOS truth.
  3. Computes per-(city, month) bias + sigma + n.
  4. Merges into skill_matrix.json (preserves existing cells).

Usage:
    python3 -m analysis.weather.add_ai_models_to_matrix [--days 180] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.backtest_6mo import (
    fetch_d1_forecasts, fetch_asos_daily_max,
)

SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
SIGMA_FLOOR = 0.30
MIN_N_REPORT = 5
AI_MODELS = ("ecmwf_aifs025", "gfs_graphcast025")


def compute_cells_for_city(city_slug: str, days: int = 180) -> dict:
    """Return {model: {month: {bias, sigma, n}}} for AI_MODELS at this city."""
    station = STATIONS[city_slug]
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)

    print(f"  → {city_slug.upper()} ({station.icao}) fetching AI models {start} → {end}",
          file=sys.stderr)
    d1 = fetch_d1_forecasts(station.lat, station.lon, AI_MODELS,
                             start.isoformat(), end.isoformat(),
                             cache_key=f"ai_{city_slug}_{start}_{end}")
    asos = fetch_asos_daily_max(station.icao, start.isoformat(), end.isoformat(),
                                  cache_key=f"{city_slug}_{start}_{end}")
    if not d1 or not asos:
        print(f"     no data — skipped", file=sys.stderr)
        return {}

    # Group errors by (model, month)
    errors: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for day, models_today in d1.items():
        actual = asos.get(day)
        if actual is None:
            continue
        month = int(day[5:7])
        for model, fc_val in models_today.items():
            if model in AI_MODELS and fc_val is not None:
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
    return result


def merge_into_matrix(new_cells: dict, dry_run: bool = False) -> dict:
    """Add new_cells {city_slug: {model: {month: stats}}} to skill_matrix.json."""
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    stations = matrix.get("stations", {})
    changed = 0
    for city_slug, models in new_cells.items():
        if city_slug not in stations:
            stations[city_slug] = {}
        for model, monthly in models.items():
            if model not in stations[city_slug]:
                stations[city_slug][model] = {}
            for mon_str, stats in monthly.items():
                old = stations[city_slug][model].get(mon_str)
                if old != stats:
                    stations[city_slug][model][mon_str] = stats
                    changed += 1

    # Update meta
    if changed:
        notes = matrix.get("_meta", {}).get("notes", "")
        if "AIFS+GraphCast" not in notes:
            notes = (notes + "; AIFS+GraphCast added from 6mo Previous Runs API").lstrip("; ")
        matrix["_meta"]["notes"] = notes
        matrix["_meta"]["ai_models_added"] = date.today().isoformat()

    print(f"\n  Total cells added/updated: {changed}", file=sys.stderr)

    if dry_run:
        print("  (dry-run — not writing)", file=sys.stderr)
        return matrix

    if changed:
        SKILL_MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
        print(f"  → {SKILL_MATRIX_PATH} updated", file=sys.stderr)
    return matrix


def _cli():
    ap = argparse.ArgumentParser(description="Add AIFS + GraphCast skill cells to matrix")
    ap.add_argument("--days", type=int, default=180, help="historical window")
    ap.add_argument("--cities", default="", help="comma-separated city slugs (default: all in STATIONS)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] or list(STATIONS.keys())
    print(f"Augmenting matrix with AI models for {len(cities)} cities ({args.days} days)",
          file=sys.stderr)

    all_new_cells = {}
    for city_slug in cities:
        if city_slug not in STATIONS:
            print(f"  SKIP {city_slug}: not in STATIONS", file=sys.stderr)
            continue
        cells = compute_cells_for_city(city_slug, days=args.days)
        if cells:
            all_new_cells[city_slug] = cells
            print(f"     models: {list(cells.keys())}, months: {[len(m) for m in cells.values()]}",
                  file=sys.stderr)

    merge_into_matrix(all_new_cells, dry_run=args.dry_run)


if __name__ == "__main__":
    _cli()
