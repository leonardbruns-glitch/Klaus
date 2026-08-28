"""
Extend skill_matrix.json with 10-year MERRA-2 history from NASA POWER API.

archive-api.open-meteo.com is unreachable from the VPS. NASA POWER
(power.larc.nasa.gov) provides MERRA-2 T2M_MAX globally, free, no auth,
reachable from the VPS — confirmed 2026-05-22.

Adds model key "merra2" per city with 10yr (2015-2024) bias/sigma vs ASOS.
Two uses:
  1. Robust σ estimates (n≈365/month vs n≈155 from 5yr archive) improve
     ensemble BLUE floor for cities where GFS/ICON cells have low n.
  2. Allows re-deriving CITY_SIGMA_C candidates (run --print-sigma-c after).

Usage:
    python3 -m analysis.weather.add_nasa_power_to_matrix [--year-start 2015] [--dry-run]
    python3 -m analysis.weather.add_nasa_power_to_matrix --city buenos-aires
    python3 -m analysis.weather.add_nasa_power_to_matrix --print-sigma-c  # show updated σ floor candidates
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
from datetime import date
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.build_skill_matrix import fetch_asos_daily_max

SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"
NASA_POWER_URL    = "https://power.larc.nasa.gov/api/temporal/daily/point"
USER_AGENT        = "Klaus-WeatherBot/1.0 (calibration; contact: leonard.bruns@gmail.com)"
SIGMA_FLOOR       = 0.30
MIN_N_REPORT      = 20   # higher bar since merra2 is reanalysis, not operational forecast
MODEL_KEY         = "merra2"


def fetch_nasa_power_year(lat: float, lon: float, year: int) -> dict[str, float]:
    """Returns {date_str: T2M_MAX_celsius} for a single calendar year."""
    params = {
        "parameters": "T2M_MAX",
        "community":  "AG",
        "longitude":  f"{lon:.4f}",
        "latitude":   f"{lat:.4f}",
        "start":      f"{year}0101",
        "end":        f"{year}1231",
        "format":     "JSON",
    }
    url = f"{NASA_POWER_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"    [NASA] {year} error: {e}", file=sys.stderr)
        return {}

    raw = data.get("properties", {}).get("parameter", {}).get("T2M_MAX", {})
    result: dict[str, float] = {}
    for k, v in raw.items():
        if v is None or v == -999:
            continue
        date_str = f"{k[:4]}-{k[4:6]}-{k[6:8]}"
        result[date_str] = float(v)
    return result


def fetch_nasa_power_range(lat: float, lon: float,
                            year_start: int, year_end: int) -> dict[str, float]:
    """Fetch multiple years, return combined {date_str: T2M_MAX}."""
    combined: dict[str, float] = {}
    for yr in range(year_start, year_end + 1):
        print(f"    NASA POWER {yr}...", end=" ", flush=True, file=sys.stderr)
        chunk = fetch_nasa_power_year(lat, lon, yr)
        combined.update(chunk)
        print(f"{len(chunk)} days", flush=True, file=sys.stderr)
        time.sleep(0.3)
    return combined


def compute_merra2_skill(asos: dict[str, float],
                          merra2: dict[str, float]) -> dict[str, dict]:
    """
    Compute bias/sigma/n per month from MERRA-2 vs ASOS paired errors.
    Returns {month_str: {bias, sigma, n}}.
    """
    monthly: dict[int, list[float]] = defaultdict(list)
    for date_str, fc_val in merra2.items():
        actual = asos.get(date_str)
        if actual is None:
            continue
        month = int(date_str[5:7])
        monthly[month].append(fc_val - actual)

    result: dict[str, dict] = {}
    for month, errs in monthly.items():
        if len(errs) < MIN_N_REPORT:
            continue
        bias = statistics.fmean(errs)
        debiased = [e - bias for e in errs]
        sigma = max(SIGMA_FLOOR, statistics.stdev(debiased) if len(debiased) >= 2 else SIGMA_FLOOR)
        result[str(month)] = {"bias": round(bias, 3), "sigma": round(sigma, 3), "n": len(errs)}
    return result


def print_sigma_c_candidates(matrix: dict) -> None:
    """Print CITY_SIGMA_C candidate values derived from merra2 sigma per month."""
    stations = matrix.get("stations", {})
    print("\n=== CITY_SIGMA_C candidates from MERRA-2 10yr ===")
    print("(Use as σ floor in weather_arb.py — lower = sharper city)")
    print()
    for slug in sorted(stations.keys()):
        merra2 = stations[slug].get(MODEL_KEY, {})
        if not merra2:
            continue
        by_month = {int(m): v["sigma"] for m, v in merra2.items() if v.get("n", 0) >= MIN_N_REPORT}
        if not by_month:
            continue
        monthly_str = ", ".join(f"{m}:{v:.3f}" for m, v in sorted(by_month.items()))
        mean_sigma = statistics.mean(by_month.values())
        print(f"  {slug:<20} mean={mean_sigma:.3f}  [{monthly_str}]")


def run_city(city_slug: str, year_start: int, year_end: int) -> dict[str, dict]:
    """Returns {month_str: {bias,sigma,n}} for MODEL_KEY at this city."""
    station = STATIONS[city_slug]
    print(f"\n  {city_slug.upper()} ({station.icao})", file=sys.stderr)

    print(f"  ASOS {year_start}–{year_end}...", end=" ", flush=True, file=sys.stderr)
    try:
        from analysis.weather.build_skill_matrix import fetch_asos_daily_max as _fetch
        asos = _fetch(station.icao, year_start, year_end)
        print(f"{len(asos)} days", flush=True, file=sys.stderr)
    except Exception as e:
        print(f"ERROR: {e}", flush=True, file=sys.stderr)
        return {}

    if len(asos) < 100:
        print(f"  insufficient ASOS ({len(asos)} days)", file=sys.stderr)
        return {}

    print(f"  NASA POWER (MERRA-2) {year_start}–{year_end}:", file=sys.stderr)
    merra2 = fetch_nasa_power_range(station.lat, station.lon, year_start, year_end)
    if not merra2:
        return {}

    skill = compute_merra2_skill(asos, merra2)
    if skill:
        cells_str = "  ".join(
            f"m{m}:n={v['n']},b={v['bias']:+.2f},σ={v['sigma']:.3f}"
            for m, v in sorted(skill.items(), key=lambda x: int(x[0]))[:4]
        )
        print(f"  skill: {cells_str} ...", file=sys.stderr)
    return skill


def merge_into_matrix(
    new_cells: dict[str, dict[str, dict]],
    dry_run: bool = False,
) -> dict:
    matrix = json.loads(SKILL_MATRIX_PATH.read_text())
    stations = matrix.setdefault("stations", {})
    added = updated = 0

    for city_slug, monthly in new_cells.items():
        city_data = stations.setdefault(city_slug, {})
        model_data = city_data.setdefault(MODEL_KEY, {})
        for mon_str, stats in monthly.items():
            if mon_str in model_data:
                model_data[mon_str] = stats   # replace — merra2 always 10yr
                updated += 1
            else:
                model_data[mon_str] = stats
                added += 1

    tag = "merra2 10yr from NASA POWER"
    notes = matrix.get("_meta", {}).get("notes", "")
    if tag not in notes:
        matrix["_meta"]["notes"] = (notes + f"; {tag}").lstrip("; ")
    matrix["_meta"]["merra2_added"] = date.today().isoformat()

    print(f"\n  merra2 cells: {added} added, {updated} updated", file=sys.stderr)
    if dry_run:
        print("  (dry-run — not writing)", file=sys.stderr)
        return matrix

    SKILL_MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
    print(f"  → {SKILL_MATRIX_PATH} updated", file=sys.stderr)
    return matrix


def _cli():
    ap = argparse.ArgumentParser(description="Add 10yr MERRA-2 (NASA POWER) to skill_matrix.json")
    ap.add_argument("--year-start",    type=int, default=2015)
    ap.add_argument("--year-end",      type=int, default=2024)
    ap.add_argument("--city",          action="append", dest="cities")
    ap.add_argument("--dry-run",       action="store_true")
    ap.add_argument("--print-sigma-c", action="store_true",
                    help="After merge, print CITY_SIGMA_C candidates derived from merra2 sigma")
    args = ap.parse_args()

    cities = args.cities or list(STATIONS.keys())
    print(f"NASA POWER MERRA-2: {len(cities)} cities, {args.year_start}–{args.year_end}", file=sys.stderr)

    all_new: dict[str, dict] = {}
    for slug in cities:
        if slug not in STATIONS:
            print(f"  SKIP {slug}: not in STATIONS", file=sys.stderr)
            continue
        skill = run_city(slug, args.year_start, args.year_end)
        if skill:
            all_new[slug] = skill
        time.sleep(0.5)

    matrix = merge_into_matrix(all_new, dry_run=args.dry_run)

    if args.print_sigma_c:
        print_sigma_c_candidates(matrix)

    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    _cli()
