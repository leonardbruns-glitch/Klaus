"""
Backfill skill_matrix.json with recent NWP data (past 90 days) for ALL live models.

Uses api.open-meteo.com with past_days=90 — the same endpoint as the live bot.
This returns current-model values for past dates (not the original issued D+1 forecast,
but the difference is typically <0.3°C). Pairs against ASOS actuals for same dates.

Adds ~20-90 data points per (city, model, month) for recent months, recency-upweighted
(3× per day) so current model behavior dominates bias/sigma calibration over 5yr history.

Usage:
    python3 -m analysis.weather.backfill_prev_runs [--days 90] [--recency 3.0] [--dry-run]
    python3 -m analysis.weather.backfill_prev_runs --city buenos-aires
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.backtest_6mo import fetch_asos_daily_max

SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"
USER_AGENT    = "Klaus-WeatherBot/1.0 (calibration; contact: leonard.bruns@gmail.com)"
CACHE_DIR     = Path(__file__).parent.parent.parent / "logs" / "backtest_cache"
SIGMA_FLOOR   = 0.30
MIN_N_REPORT  = 5
RECENCY_WEIGHT = 3.0

LIVE_MODELS = (
    "gfs_seamless", "icon_seamless", "ecmwf_ifs025", "gem_seamless",
    "jma_seamless", "ukmo_seamless", "meteofrance_seamless",
    "ecmwf_aifs025", "gfs_graphcast025",
)


def fetch_recent_forecasts(lat: float, lon: float, days: int,
                           cache_key: str = "") -> dict[str, dict[str, float]]:
    """
    Fetch past `days` days of daily max temperature for all live models.
    Uses api.open-meteo.com with past_days=N (returns current model output
    for past dates — close approximation to original D+1 forecast).

    Returns: {model_name: {date_str: max_temp_c}}
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}_recent.json" if cache_key else None
    if cache_file and cache_file.exists():
        return json.loads(cache_file.read_text())

    params = {
        "latitude":    f"{lat:.4f}",
        "longitude":   f"{lon:.4f}",
        "daily":       "temperature_2m_max",
        "models":      ",".join(LIVE_MODELS),
        "temperature_unit": "celsius",
        "timezone":    "UTC",
        "past_days":   str(days),
        "forecast_days": "1",
    }
    url = f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [fetch] error {cache_key}: {e}", file=sys.stderr)
        return {}

    daily = data.get("daily", {})
    times = daily.get("time", [])
    if not times:
        return {}

    result: dict[str, dict[str, float]] = {}
    for key, vals in daily.items():
        if not key.startswith("temperature_2m_max"):
            continue
        suffix = key[len("temperature_2m_max"):].lstrip("_")
        model = suffix if suffix else LIVE_MODELS[0]
        by_date: dict[str, float] = {}
        for i, d in enumerate(times):
            if i < len(vals) and vals[i] is not None:
                by_date[d] = float(vals[i])
        if by_date:
            result[model] = by_date

    if cache_file:
        cache_file.write_text(json.dumps(result))
    return result


def _merge_cells(old: dict, new: dict, recency_weight: float = RECENCY_WEIGHT) -> dict:
    """Recency-weighted combine of two {bias, sigma, n} cells."""
    n1, n2 = old["n"], new["n"]
    b1, b2 = old["bias"], new["bias"]
    s1, s2 = old["sigma"], new["sigma"]
    eff1, eff2 = float(n1), float(n2) * recency_weight
    w1, w2 = eff1 / (eff1 + eff2), eff2 / (eff1 + eff2)
    bias_c = w1 * b1 + w2 * b2
    var = w1 * (s1 ** 2 + (b1 - bias_c) ** 2) + w2 * (s2 ** 2 + (b2 - bias_c) ** 2)
    return {"bias": round(bias_c, 3), "sigma": round(max(SIGMA_FLOOR, math.sqrt(var)), 3), "n": n1 + n2}


def compute_recent_cells(city_slug: str, days: int) -> dict[str, dict[str, dict]]:
    """Fetch recent forecasts + ASOS actuals → {model: {month_str: {bias,sigma,n}}}."""
    station = STATIONS[city_slug]
    end   = (date.today() - timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()
    print(f"  → {city_slug.upper()} ({station.icao})  {start} → {end}", file=sys.stderr)

    forecasts = fetch_recent_forecasts(
        station.lat, station.lon, days,
        cache_key=f"recent_{city_slug}_{days}d",
    )
    asos = fetch_asos_daily_max(
        station.icao, start, end,
        cache_key=f"asos_recent_{city_slug}_{start}_{end}",
    )
    if not forecasts or not asos:
        print(f"     no data (forecasts={len(forecasts)} asos={len(asos)})", file=sys.stderr)
        return {}

    errors: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for model, fc_dates in forecasts.items():
        for day, fc_val in fc_dates.items():
            actual = asos.get(day)
            if actual is None:
                continue
            month = int(day[5:7])
            errors[model][month].append(fc_val - actual)

    result: dict[str, dict[str, dict]] = {}
    for model, monthly in errors.items():
        result[model] = {}
        for month, errs in monthly.items():
            if len(errs) < MIN_N_REPORT:
                continue
            bias = statistics.fmean(errs)
            debiased = [e - bias for e in errs]
            sigma = max(SIGMA_FLOOR, statistics.stdev(debiased) if len(debiased) >= 2 else SIGMA_FLOOR)
            result[model][str(month)] = {"bias": round(bias, 3), "sigma": round(sigma, 3), "n": len(errs)}

    n_cells = sum(len(m) for m in result.values())
    print(f"     {len(result)} models, {n_cells} cells", file=sys.stderr)
    for model, monthly in sorted(result.items()):
        cells_str = "  ".join(
            f"m{m}:n={v['n']},b={v['bias']:+.2f}" for m, v in sorted(monthly.items(), key=lambda x: int(x[0]))
        )
        print(f"       {model:<30} {cells_str}", file=sys.stderr)
    return result


def merge_into_matrix(new_cells: dict, recency_weight: float = RECENCY_WEIGHT, dry_run: bool = False) -> dict:
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    stations = matrix.setdefault("stations", {})
    added = merged = 0
    for city_slug, models in new_cells.items():
        city_data = stations.setdefault(city_slug, {})
        for model, monthly in models.items():
            model_data = city_data.setdefault(model, {})
            for mon_str, new_stats in monthly.items():
                old = model_data.get(mon_str)
                if old and old.get("n", 0) >= MIN_N_REPORT:
                    model_data[mon_str] = _merge_cells(old, new_stats, recency_weight)
                    merged += 1
                else:
                    model_data[mon_str] = new_stats
                    added += 1

    tag = "recent-backfill via forecast past_days"
    notes = matrix.get("_meta", {}).get("notes", "")
    if tag not in notes:
        matrix["_meta"]["notes"] = (notes + f"; {tag}").lstrip("; ")
    matrix["_meta"]["recent_backfill"] = date.today().isoformat()
    print(f"\n  Cells merged: {merged}  |  new cells added: {added}", file=sys.stderr)
    if dry_run:
        print("  (dry-run — not writing)", file=sys.stderr)
        return matrix
    SKILL_MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
    print(f"  → {SKILL_MATRIX_PATH} updated", file=sys.stderr)
    return matrix


def _cli():
    ap = argparse.ArgumentParser(description="Backfill skill matrix from recent forecast data (all live models)")
    ap.add_argument("--days",    type=int,   default=90,           help="lookback window in days (default 90)")
    ap.add_argument("--recency", type=float, default=RECENCY_WEIGHT, help="recency upweight factor (default 3.0)")
    ap.add_argument("--city",    action="append", dest="cities",   help="city slug(s); default=all in STATIONS")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cities = args.cities or list(STATIONS.keys())
    print(f"Backfilling {len(cities)} cities, past {args.days} days, recency×{args.recency}", file=sys.stderr)

    all_new: dict[str, dict] = {}
    for slug in cities:
        if slug not in STATIONS:
            print(f"  SKIP {slug}: not in STATIONS", file=sys.stderr)
            continue
        cells = compute_recent_cells(slug, args.days)
        if cells:
            all_new[slug] = cells
        time.sleep(0.5)

    merge_into_matrix(all_new, recency_weight=args.recency, dry_run=args.dry_run)
    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    _cli()
