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

# All 78 stations mirrored from strategy/weather_arb.py CITY_COORDS + CITY_ICAO.
# Slug = city name lowercased + spaces→hyphens (matches WeightedEnsemble lookup key).
STATIONS = {
    # Original 7 — slugs must match CITY_NAME_TO_SLUG in weather_arb.py exactly
    "nyc":              {"lat": 40.7769,  "lon":  -73.8740,  "icao": "KLGA"},
    "chicago":          {"lat": 41.9742,  "lon":  -87.9073,  "icao": "KORD"},
    "los-angeles":      {"lat": 33.9425,  "lon": -118.4081,  "icao": "KLAX"},
    "miami":            {"lat": 25.7953,  "lon":  -80.2900,  "icao": "KMIA"},
    "san-francisco":    {"lat": 37.6213,  "lon": -122.3790,  "icao": "KSFO"},
    "tokyo":            {"lat": 35.5494,  "lon":  139.7798,  "icao": "RJTT"},
    "london":           {"lat": 51.5048,  "lon":    0.0495,  "icao": "EGLC"},
    "paris":            {"lat": 48.9694,  "lon":    2.4414,  "icao": "LFPB"},
    "seoul":            {"lat": 37.4602,  "lon":  126.4407,  "icao": "RKSI"},
    "seattle":          {"lat": 47.4502,  "lon": -122.3088,  "icao": "KSEA"},
    "sao-paulo":        {"lat":-23.4356,  "lon":  -46.4731,  "icao": "SBGR"},
    "buenos-aires":     {"lat":-34.8222,  "lon":  -58.5358,  "icao": "SAEZ"},
    "ankara":           {"lat": 40.1281,  "lon":   32.9951,  "icao": "LTAC"},
    "wellington":       {"lat":-41.3272,  "lon":  174.8051,  "icao": "NZWN"},
    "lucknow":          {"lat": 26.7606,  "lon":   80.8893,  "icao": "VILK"},
    "munich":           {"lat": 48.3538,  "lon":   11.7861,  "icao": "EDDM"},
    "dallas":           {"lat": 32.8481,  "lon":  -96.8517,  "icao": "KDAL"},
    "singapore":        {"lat":  1.3644,  "lon":  103.9915,  "icao": "WSSS"},
    "milan":            {"lat": 45.6307,  "lon":    8.7281,  "icao": "LIMC"},
    "madrid":           {"lat": 40.4936,  "lon":   -3.5668,  "icao": "LEMD"},
    "warsaw":           {"lat": 52.1657,  "lon":   20.9671,  "icao": "EPWA"},
    "taipei":           {"lat": 25.0694,  "lon":  121.5522,  "icao": "RCSS"},
    "beijing":          {"lat": 40.0799,  "lon":  116.5844,  "icao": "ZBAA"},
    "wuhan":            {"lat": 30.7838,  "lon":  114.2080,  "icao": "ZHHH"},
    "chengdu":          {"lat": 30.5782,  "lon":  103.9470,  "icao": "ZUUU"},
    "shenzhen":         {"lat": 22.6393,  "lon":  113.8107,  "icao": "ZGSZ"},
    "austin":           {"lat": 30.1945,  "lon":  -97.6699,  "icao": "KAUS"},
    "denver":           {"lat": 39.7017,  "lon": -104.7517,  "icao": "KBKF"},
    "houston":          {"lat": 29.6454,  "lon":  -95.2789,  "icao": "KHOU"},
    "mexico-city":      {"lat": 19.4363,  "lon":  -99.0721,  "icao": "MMMX"},
    "busan":            {"lat": 35.1795,  "lon":  128.9382,  "icao": "RKPK"},
    "amsterdam":        {"lat": 52.3086,  "lon":    4.7639,  "icao": "EHAM"},
    "helsinki":         {"lat": 60.3172,  "lon":   24.9633,  "icao": "EFHK"},
    "panama-city":      {"lat":  8.9788,  "lon":  -79.5556,  "icao": "MPHO"},
    "jakarta":          {"lat": -6.2662,  "lon":  106.8906,  "icao": "WIHH"},
    "jeddah":           {"lat": 21.6796,  "lon":   39.1565,  "icao": "OEJN"},
    "cape-town":        {"lat":-33.9648,  "lon":   18.6017,  "icao": "FACT"},
    "guangzhou":        {"lat": 23.3924,  "lon":  113.2990,  "icao": "ZGGG"},
    "jinan":            {"lat": 36.8572,  "lon":  117.0558,  "icao": "ZSJN"},
    "qingdao":          {"lat": 36.2661,  "lon":  120.3742,  "icao": "ZSQD"},
    "karachi":          {"lat": 24.8936,  "lon":   67.1355,  "icao": "OPKC"},
    "manila":           {"lat": 14.5086,  "lon":  121.0194,  "icao": "RPLL"},
    "toronto":          {"lat": 43.6777,  "lon":  -79.6248,  "icao": "CYYZ"},
    "shanghai":         {"lat": 31.1434,  "lon":  121.8052,  "icao": "ZSPD"},
    "hong-kong":        {"lat": 22.3080,  "lon":  113.9185,  "icao": "VHHH"},
    "dubai":            {"lat": 25.2532,  "lon":   55.3657,  "icao": "OMDB"},
    "sydney":           {"lat":-33.9399,  "lon":  151.1753,  "icao": "YSSY"},
    "phoenix":          {"lat": 33.4343,  "lon": -112.0117,  "icao": "KPHX"},
    "atlanta":          {"lat": 33.6407,  "lon":  -84.4277,  "icao": "KATL"},
    "berlin":           {"lat": 52.3667,  "lon":   13.5033,  "icao": "EDDB"},
    "stockholm":        {"lat": 59.6519,  "lon":   17.9186,  "icao": "ESSA"},
    "oslo":             {"lat": 60.1939,  "lon":   11.0998,  "icao": "ENGM"},
    "copenhagen":       {"lat": 55.6179,  "lon":   12.6560,  "icao": "EKCH"},
    "vienna":           {"lat": 48.1103,  "lon":   16.5697,  "icao": "LOWW"},
    "zurich":           {"lat": 47.4647,  "lon":    8.5492,  "icao": "LSZH"},
    "brussels":         {"lat": 50.9010,  "lon":    4.4844,  "icao": "EBBR"},
    "barcelona":        {"lat": 41.2971,  "lon":    2.0785,  "icao": "LEBL"},
    "rome":             {"lat": 41.8003,  "lon":   12.2389,  "icao": "LIRF"},
    "prague":           {"lat": 50.1008,  "lon":   14.2600,  "icao": "LKPR"},
    "budapest":         {"lat": 47.4298,  "lon":   19.2610,  "icao": "LHBP"},
    "bucharest":        {"lat": 44.5722,  "lon":   26.1022,  "icao": "LROP"},
    "athens":           {"lat": 37.9364,  "lon":   23.9445,  "icao": "LGAV"},
    "istanbul":         {"lat": 40.8986,  "lon":   29.3092,  "icao": "LTFJ"},
    "moscow":           {"lat": 55.9736,  "lon":   37.4125,  "icao": "UUEE"},
    "riyadh":           {"lat": 24.9576,  "lon":   46.6988,  "icao": "OERK"},
    "cairo":            {"lat": 30.1219,  "lon":   31.4056,  "icao": "HECA"},
    "lagos":            {"lat":  6.5774,  "lon":    3.3214,  "icao": "DNMM"},
    "nairobi":          {"lat": -1.3192,  "lon":   36.9275,  "icao": "HKJK"},
    "johannesburg":     {"lat":-26.1392,  "lon":   28.2460,  "icao": "FAOR"},
    "mumbai":           {"lat": 19.0896,  "lon":   72.8656,  "icao": "VABB"},
    "delhi":            {"lat": 28.5665,  "lon":   77.1031,  "icao": "VIDP"},
    "dhaka":            {"lat": 23.8433,  "lon":   90.3978,  "icao": "VGHS"},
    "bangkok":          {"lat": 13.6811,  "lon":  100.7472,  "icao": "VTBS"},
    "kuala-lumpur":     {"lat":  2.7456,  "lon":  101.7072,  "icao": "WMKK"},
    "bogota":           {"lat":  4.7016,  "lon":  -74.1469,  "icao": "SKBO"},
    "lima":             {"lat":-12.0219,  "lon":  -77.1143,  "icao": "SPJC"},
    "santiago":         {"lat":-33.3930,  "lon":  -70.7858,  "icao": "SCEL"},
    "chongqing":        {"lat": 29.7192,  "lon":  106.6418,  "icao": "ZUCK"},
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
