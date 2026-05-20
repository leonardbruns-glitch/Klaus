"""
Build the Historical Skill Matrix for the 7 NWP models used in weather_arb.py.

For each (station, model, calendar_month):
  - Fetches what each model forecast 1-day ahead for every day in the last 5 years
    using Open-Meteo Historical Forecast API
  - Compares against Open-Meteo archive reanalysis (proxy for actual WU reading)
  - Computes: bias (systematic error), sigma² (residual variance post-debiasing)
  - Stores skill_matrix.json used by _get_forecast() to weight the ensemble

Run:  python3 analysis/build_skill_matrix.py
Output: strategy/skill_matrix.json

Note on model availability on Historical Forecast API:
  gfs_seamless      : 2015+   (best coverage)
  icon_seamless     : 2019+
  gem_seamless      : 2019+
  jma_seamless      : 2021+
  ecmwf_ifs025      : 2024+   (limited — will have <12 months in some stations)
  ukmo_seamless     : 2024+   (limited)
  meteofrance_seamless: 2023+ (limited)

MIN_N_PER_MONTH = 30 days minimum to use a model's weight for a given month.
Models below this threshold fall back to equal-weight in that month.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

# ── CONFIG ──────────────────────────────────────────────────────────────────
YEARS_BACK    = 5        # how many years of history to use
MIN_N_MONTH   = 30       # minimum data-points to trust a model's monthly weight
GAMMA         = 1.30     # inter-model correlation inflation on combined sigma
REQUEST_DELAY = 0.40     # seconds between API requests (rate limiting)

HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ARCHIVE_URL             = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_PATH             = Path(__file__).parent.parent / "strategy" / "skill_matrix.json"

# Stations to build the matrix for
STATIONS = {
    "nyc":           {"lat": 40.7769, "lon": -73.8740, "icao": "KLGA"},
    "chicago":       {"lat": 41.9742, "lon": -87.9073, "icao": "KORD"},
    "los-angeles":   {"lat": 33.9425, "lon": -118.4081, "icao": "KLAX"},
    "miami":         {"lat": 25.7953, "lon": -80.2900, "icao": "KMIA"},
    "san-francisco": {"lat": 37.6213, "lon": -122.3790, "icao": "KSFO"},
    "tokyo":         {"lat": 35.5494, "lon": 139.7798,  "icao": "RJTT"},
    "london":        {"lat": 51.5048, "lon":   0.0495,  "icao": "EGLC"},
}

MODELS = [
    "gfs_seamless",
    "icon_seamless",
    "ecmwf_ifs025",
    "gem_seamless",
    "jma_seamless",
    "ukmo_seamless",
    "meteofrance_seamless",
]

# ── FETCH HELPERS ────────────────────────────────────────────────────────────

async def fetch_historical_forecasts(
    sess: aiohttp.ClientSession,
    lat: float, lon: float,
    start: str, end: str,
    models: list[str],
) -> dict[str, dict[str, float]]:
    """
    Returns: {model_name: {date_str: forecast_max_c}}
    One call per batch of models (Open-Meteo accepts comma-separated models).
    """
    params = (
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&daily=temperature_2m_max"
        f"&temperature_unit=celsius"
        f"&start_date={start}&end_date={end}"
        f"&models={','.join(models)}"
    )
    url = HISTORICAL_FORECAST_URL + params
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                return {}
            data = await r.json()
    except Exception as e:
        print(f"  [ERR] historical forecast fetch failed: {e}")
        return {}

    daily = data.get("daily", {})
    dates = daily.get("time", [])

    result: dict[str, dict[str, float]] = {m: {} for m in models}
    for key, vals in daily.items():
        if not key.startswith("temperature_2m_max"):
            continue
        # key formats: "temperature_2m_max" (single model) or
        # "temperature_2m_max_gfs_seamless" (multi-model)
        suffix = key[len("temperature_2m_max"):]
        model_name = suffix.lstrip("_") if suffix else models[0]
        for d, v in zip(dates, vals):
            if v is not None:
                result.setdefault(model_name, {})[d] = float(v)
    return result


async def fetch_archive_actuals(
    sess: aiohttp.ClientSession,
    lat: float, lon: float,
    start: str, end: str,
) -> dict[str, float]:
    """Returns: {date_str: actual_max_c} from reanalysis archive."""
    params = (
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&daily=temperature_2m_max"
        f"&temperature_unit=celsius"
        f"&start_date={start}&end_date={end}"
    )
    try:
        async with sess.get(ARCHIVE_URL + params, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                return {}
            data = await r.json()
    except Exception as e:
        print(f"  [ERR] archive fetch failed: {e}")
        return {}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temps = daily.get("temperature_2m_max", [])
    return {d: float(t) for d, t in zip(dates, temps) if t is not None}


# ── CORE COMPUTATION ─────────────────────────────────────────────────────────

def compute_station_skill(
    forecasts: dict[str, dict[str, float]],  # model → {date: forecast_c}
    actuals: dict[str, float],               # date → actual_c
) -> dict[str, dict[int, dict]]:
    """
    Returns: {model_name: {month_int: {bias, sigma, n}}}

    For each model × month:
      bias  = mean(forecast - actual)          [systematic offset]
      sigma = RMSE(forecast - bias - actual)   [residual std after debiasing]
      n     = number of days with data
    """
    # Group errors by model and month
    errors_by_model_month: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for model, fc_days in forecasts.items():
        for d, fc_val in fc_days.items():
            if d not in actuals:
                continue
            month = int(d[5:7])
            errors_by_model_month[model][month].append(fc_val - actuals[d])

    result: dict[str, dict[int, dict]] = {}
    for model, months in errors_by_model_month.items():
        result[model] = {}
        for month, errors in months.items():
            n = len(errors)
            if n < 1:
                continue
            bias = sum(errors) / n
            debiased = [e - bias for e in errors]
            variance = sum(x * x for x in debiased) / n
            sigma = math.sqrt(variance) if variance > 0 else 0.0
            result[model][month] = {"bias": round(bias, 4), "sigma": round(sigma, 4), "n": n}
    return result


# ── MAIN ─────────────────────────────────────────────────────────────────────

async def build():
    today = date.today()
    start_date = (today - timedelta(days=365 * YEARS_BACK)).isoformat()
    end_date   = (today - timedelta(days=2)).isoformat()  # yesterday is latest safe point

    skill_matrix: dict[str, dict] = {}

    async with aiohttp.ClientSession() as sess:
        for slug, cfg in STATIONS.items():
            lat, lon = cfg["lat"], cfg["lon"]
            print(f"\n{'─'*60}")
            print(f"  {slug.upper()}  ({cfg['icao']})  {start_date} → {end_date}")
            print(f"{'─'*60}")

            # Fetch historical forecasts for all models in one call
            await asyncio.sleep(REQUEST_DELAY)
            fc_all = await fetch_historical_forecasts(
                sess, lat, lon, start_date, end_date, MODELS
            )

            # Fetch actuals
            await asyncio.sleep(REQUEST_DELAY)
            actuals = await fetch_archive_actuals(sess, lat, lon, start_date, end_date)

            print(f"  Actuals: {len(actuals)} days")
            for model, fc in fc_all.items():
                print(f"  {model:28s}: {len(fc)} forecast-days")

            # Compute skill
            station_skill = compute_station_skill(fc_all, actuals)

            # Report and store
            skill_matrix[slug] = station_skill
            for model, months in sorted(station_skill.items()):
                for month in sorted(months):
                    e = months[month]
                    flag = "" if e["n"] >= MIN_N_MONTH else " ⚠ LOW-N"
                    print(f"    {model:28s} M{month:02d}: "
                          f"bias={e['bias']:+.2f}°C  σ={e['sigma']:.2f}°C  n={e['n']}{flag}")

    # Write output
    meta = {
        "built":      today.isoformat(),
        "years_back": YEARS_BACK,
        "min_n":      MIN_N_MONTH,
        "gamma":      GAMMA,
        "models":     MODELS,
    }
    output = {"_meta": meta, "stations": skill_matrix}
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nSkill matrix saved → {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(build())
