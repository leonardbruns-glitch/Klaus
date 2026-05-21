"""Build strategy/skill_matrix.json from 5 years of historical data.

Sources:
  - ASOS (Iowa State Mesonet): 5-year hourly station data → daily max (ground truth)
  - Open-Meteo archive API: ERA5, ERA5_land, gfs_seamless, icon_seamless,
    + regional NWP (jma_seamless for Tokyo, ukmo/metno/meteofrance for Europe)
  - ecmwf_ifs025 excluded: returns nulls for all historical dates in archive API

Output: strategy/skill_matrix.json
  {
    "_meta": {"built": "...", "years": "2021-2025", "cities": n},
    "stations": {
      slug: {
        model: {
          "1": {"bias": float, "sigma": float, "n": int},  # month 1=Jan
          ...
        }
      }
    }
  }

bias = mean(forecast - actual)  [positive = model runs hot]
sigma = std(forecast - actual - bias)  [debiased RMSE, floored at 0.30]
n = number of day/year pairs contributing

Usage:
    python3 -m analysis.weather.build_skill_matrix [--out strategy/skill_matrix.json]
    python3 -m analysis.weather.build_skill_matrix --city tokyo  # single city test
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd

from analysis.weather.stations import STATIONS, Station

ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "Klaus-WeatherBot/1.0 (research; contact: leonard.bruns@gmail.com)"

YEAR_START = 2021
YEAR_END   = 2025
SIGMA_FLOOR = 0.30   # minimum debiased sigma (°C) — prevents over-confident weights
MIN_N_REPORT = 5     # include cell in matrix only if n >= this (MIN_N_PER_MONTH in ensemble_weights checks further)

# Models to pull from archive API per station class.
# ecmwf_ifs025 excluded — returns all-null in archive.
# gem_seamless = Canadian GEM; in live FORECAST_MODELS, available in archive.
# metno_seamless included for EU even though not in FORECAST_MODELS (provides extra sigma info).
ARCHIVE_MODELS_GLOBAL = ("era5", "era5_land", "gfs_seamless", "icon_seamless", "gem_seamless")
ARCHIVE_MODELS_JP     = ARCHIVE_MODELS_GLOBAL + ("jma_seamless",)
ARCHIVE_MODELS_EU     = ARCHIVE_MODELS_GLOBAL + ("ukmo_seamless", "metno_seamless", "meteofrance_seamless")


def _http_get_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _archive_models_for(station: Station) -> tuple[str, ...]:
    slug = station.city_slug
    if slug == "tokyo":
        return ARCHIVE_MODELS_JP
    if slug in ("paris", "madrid", "amsterdam", "london"):
        return ARCHIVE_MODELS_EU
    return ARCHIVE_MODELS_GLOBAL


# ── ASOS ──────────────────────────────────────────────────────────────────────

def fetch_asos_daily_max(icao: str, year_start: int, year_end: int) -> dict[str, float]:
    """Returns {date_str: max_temp_c} for all days with data."""
    params = urllib.parse.urlencode({
        "station": icao,
        "data": "tmpf",
        "year1": year_start, "month1": 1, "day1": 1,
        "year2": year_end,   "month2": 12, "day2": 31,
        "tz": "UTC",
        "format": "onlycomma",
        "latlon": "no",
        "direct": "no",
        "report_type": "2",
    })
    url = f"{ASOS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8")

    lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
    if len(lines) < 2:
        return {}

    df = pd.read_csv(StringIO("\n".join(lines)))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"valid": "time_utc", "tmpf": "temp_f"})
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"])
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")
    df["temp_c"] = (df["temp_f"] - 32) * 5 / 9
    df = df.dropna(subset=["temp_c"])
    df["date_str"] = df["time_utc"].dt.strftime("%Y-%m-%d")
    daily_max = df.groupby("date_str")["temp_c"].max()
    return daily_max.to_dict()


# ── Open-Meteo archive ─────────────────────────────────────────────────────────

def fetch_archive_chunk(lat: float, lon: float, models: tuple[str, ...],
                         start: str, end: str) -> dict[str, dict[str, float | None]]:
    """Returns {model_name: {date_str: value_c}} for all requested models."""
    daily_vars = ",".join(f"temperature_2m_max" for _ in models)
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": start,
        "end_date": end,
        "daily": "temperature_2m_max",
        "models": ",".join(models),
        "temperature_unit": "celsius",
        "timezone": "UTC",
    }
    url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url)
    daily = data.get("daily", {})
    times = daily.get("time", [])

    result: dict[str, dict[str, float | None]] = {}
    for model in models:
        key = f"temperature_2m_max_{model}"
        vals = daily.get(key, [])
        result[model] = {t: vals[i] for i, t in enumerate(times) if i < len(vals)}
    return result


def fetch_archive_all_years(station: Station,
                             year_start: int = YEAR_START,
                             year_end: int = YEAR_END) -> dict[str, dict[str, float | None]]:
    """Pull full 5-year archive in annual chunks to avoid timeout."""
    models = _archive_models_for(station)
    combined: dict[str, dict[str, float | None]] = {m: {} for m in models}
    for yr in range(year_start, year_end + 1):
        start = f"{yr}-01-01"
        end   = f"{yr}-12-31"
        print(f"    archive {yr}...", end=" ", flush=True)
        try:
            chunk = fetch_archive_chunk(station.lat, station.lon, models, start, end)
            for model, dates in chunk.items():
                combined[model].update(dates)
            print(f"ok ({len(next(iter(chunk.values())))} days)", flush=True)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
        time.sleep(0.4)   # polite
    return combined


# ── Skill matrix computation ──────────────────────────────────────────────────

def compute_skill(asos: dict[str, float],
                  forecasts: dict[str, dict[str, float | None]]) -> dict:
    """
    Returns nested dict: {model: {month_str: {bias, sigma, n}}}

    bias  = mean(f - a)     [positive = model runs hot]
    sigma = std(f - a - bias)  [debiased; floored at SIGMA_FLOOR]
    n     = paired days with both values present
    """
    # Accumulate per model per month
    errors: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for model, fc_dates in forecasts.items():
        for date_str, fc_val in fc_dates.items():
            if fc_val is None:
                continue
            actual = asos.get(date_str)
            if actual is None:
                continue
            month = int(date_str[5:7])
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
                "bias":  round(bias,  3),
                "sigma": round(sigma, 3),
                "n":     len(errs),
            }
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def build_matrix(target_slugs: list[str] | None = None,
                 out_path: str | None = None,
                 year_start: int = YEAR_START,
                 year_end: int = YEAR_END) -> dict:
    slugs = target_slugs or list(STATIONS.keys())
    matrix: dict[str, dict] = {}

    for slug in slugs:
        station = STATIONS[slug]
        print(f"\n{'─'*60}", flush=True)
        print(f"  {slug.upper()} ({station.icao})", flush=True)

        # 1. ASOS actuals
        print(f"  ASOS {year_start}–{year_end}...", end=" ", flush=True)
        try:
            asos = fetch_asos_daily_max(station.icao, year_start, year_end)
            print(f"{len(asos)} days", flush=True)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            asos = {}

        if len(asos) < 100:
            print(f"  WARNING: insufficient ASOS data ({len(asos)} days), skipping", flush=True)
            continue

        # 2. Archive NWP forecasts
        print(f"  Archive NWP ({', '.join(_archive_models_for(station))}):", flush=True)
        try:
            forecasts = fetch_archive_all_years(station, year_start, year_end)
        except Exception as e:
            print(f"  ERROR fetching archive: {e}", flush=True)
            forecasts = {}

        if not forecasts:
            continue

        # 3. Compute skill
        skill = compute_skill(asos, forecasts)
        matrix[slug] = skill

        # Print summary
        models = list(skill.keys())
        print(f"  Skill summary (n/bias/sigma by month):", flush=True)
        for model in models:
            months_with_data = sorted(skill[model].keys(), key=int)
            cells = [f"m{m}:n={skill[model][m]['n']},b={skill[model][m]['bias']:+.2f}" for m in months_with_data[:4]]
            print(f"    {model:<25} {' | '.join(cells)} ...", flush=True)

        time.sleep(1.0)   # polite between stations

    # Write output
    if out_path is None:
        out_path = str(Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json")

    built_ts = date.today().isoformat()
    output = {
        "_meta": {
            "built": built_ts,
            "years": f"{year_start}-{year_end}",
            "cities": len(matrix),
            "sigma_floor": SIGMA_FLOOR,
            "min_n_report": MIN_N_REPORT,
            "notes": "ecmwf_ifs025 excluded (archive returns nulls); ecmwf_aifs025 excluded (forecast-only)",
        },
        "stations": matrix,
    }
    Path(out_path).write_text(json.dumps(output, indent=2))
    print(f"\nSkill matrix -> {out_path}  ({len(matrix)} cities)", flush=True)
    return output


def _cli():
    ap = argparse.ArgumentParser(description="Build strategy/skill_matrix.json from 5-year ERA5+NWP vs ASOS")
    ap.add_argument("--city", action="append", dest="cities", help="city slug(s); default=all")
    ap.add_argument("--out", default=None, help="output path (default: strategy/skill_matrix.json)")
    ap.add_argument("--year-start", type=int, default=YEAR_START)
    ap.add_argument("--year-end",   type=int, default=YEAR_END)
    args = ap.parse_args()

    build_matrix(target_slugs=args.cities, out_path=args.out,
                 year_start=args.year_start, year_end=args.year_end)


if __name__ == "__main__":
    _cli()
