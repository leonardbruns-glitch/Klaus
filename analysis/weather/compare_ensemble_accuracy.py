"""Compare D+1 ensemble accuracy: old skill matrix vs new (with UKMO+JMA globally).

For each city:
  - Fetches 180 days of D+1 forecasts via Previous Runs API (all 7 live models)
  - Fetches ASOS truth (daily max)
  - Computes skill-weighted ensemble mu using OLD and NEW skill matrices
  - Computes MAE and RMSE for: raw GFS (baseline), old ensemble, new ensemble

Usage:
    python3 -m analysis.weather.compare_ensemble_accuracy
    python3 -m analysis.weather.compare_ensemble_accuracy --days 90 --cities atlanta,buenos-aires
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
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from analysis.weather.stations import STATIONS
from strategy.ensemble_weights import WeightedEnsemble

PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ASOS_URL      = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
CACHE_DIR     = ROOT / "logs" / "backtest_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
UA            = "Klaus-WeatherBot/1.0 (compare-accuracy; contact: leonard.bruns@gmail.com)"

LIVE_MODELS = (
    "gfs_seamless", "icon_seamless", "ecmwf_ifs025",
    "gem_seamless", "jma_seamless", "ukmo_seamless", "meteofrance_seamless",
)


def _http_get(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_d1_forecasts(lat: float, lon: float, days: int) -> dict[str, dict[str, float]]:
    """Returns {model: {date_str: max_c}} for D+1 previous-run forecasts."""
    cache_key = f"d1_{lat:.4f}_{lon:.4f}_{days}d"
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < 3600:
            with open(cache_path) as f:
                return json.load(f)

    models_str = ",".join(LIVE_MODELS)
    url = (
        f"{PREV_RUNS_URL}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m_previous_day1"
        f"&models={models_str}"
        f"&past_days={days}&forecast_days=1&timezone=UTC"
    )
    try:
        data = _http_get(url, timeout=60)
    except Exception as e:
        print(f"  fetch_d1 error: {e}", file=sys.stderr)
        return {}

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    result: dict[str, dict[str, float]] = {m: {} for m in LIVE_MODELS}

    for key, vals in hourly.items():
        if "temperature_2m_previous_day1" not in key:
            continue
        suffix = key[len("temperature_2m_previous_day1"):].lstrip("_")
        model  = suffix if suffix else "gfs_seamless"
        if model not in result:
            continue
        for t, v in zip(times, vals):
            if v is None:
                continue
            d = t[:10]
            if d not in result[model] or v > result[model][d]:
                result[model][d] = float(v)

    cache_path.write_text(json.dumps(result))
    return result


def fetch_asos(icao: str, start: date, end: date) -> dict[str, float]:
    """Returns {date_str: max_c}."""
    cache_key = f"asos_{icao}_{start}_{end}"
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < 3600:
            with open(cache_path) as f:
                return json.load(f)

    params = urllib.parse.urlencode({
        "station": icao, "data": "tmpf",
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": end.year,   "month2": end.month,   "day2": end.day,
        "tz": "UTC", "format": "onlycomma", "latlon": "no",
        "direct": "no", "report_type": "2",
    })
    url = f"{ASOS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()

    lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
    if len(lines) < 2:
        return {}

    df = pd.read_csv(StringIO("\n".join(lines)))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"valid": "ts", "tmpf": "tf"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])
    df["tf"] = pd.to_numeric(df["tf"], errors="coerce")
    df = df.dropna(subset=["tf"])
    df["tc"] = (df["tf"] - 32) * 5 / 9
    df["d"]  = df["ts"].dt.strftime("%Y-%m-%d")
    result = df.groupby("d")["tc"].max().to_dict()

    cache_path.write_text(json.dumps(result))
    return result


def _rmse(errs: list[float]) -> float:
    return math.sqrt(sum(e**2 for e in errs) / len(errs)) if errs else float("nan")


def _mae(errs: list[float]) -> float:
    return sum(abs(e) for e in errs) / len(errs) if errs else float("nan")


def evaluate_city(slug: str, days: int,
                  ens_old: WeightedEnsemble, ens_new: WeightedEnsemble) -> dict | None:
    st = STATIONS.get(slug)
    if st is None or not st.icao:
        return None

    print(f"  {slug} (icao={st.icao})...", end=" ", flush=True)

    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    forecasts = fetch_d1_forecasts(st.lat, st.lon, days + 5)
    truth     = fetch_asos(st.icao, start_date, end_date)
    time.sleep(1.5)

    if not truth:
        print("no ASOS truth", flush=True)
        return None

    errs: dict[str, list[float]] = {"gfs_raw": [], "old": [], "new": []}

    for d_str, actual in truth.items():
        if d_str < start_date.isoformat() or d_str > end_date.isoformat():
            continue

        month = int(d_str[5:7])

        model_vals: dict[str, float] = {}
        for m in LIVE_MODELS:
            v = forecasts.get(m, {}).get(d_str)
            if v is not None:
                model_vals[m] = v

        if len(model_vals) < 3:
            continue

        # Baseline: raw GFS
        if "gfs_seamless" in model_vals:
            errs["gfs_raw"].append(model_vals["gfs_seamless"] - actual)

        # Old ensemble
        mu_old, _ = ens_old.combine(slug, month, model_vals)
        errs["old"].append(mu_old - actual)

        # New ensemble
        mu_new, _ = ens_new.combine(slug, month, model_vals)
        errs["new"].append(mu_new - actual)

    n = len(errs["old"])
    if n < 10:
        print(f"n={n} (skip)", flush=True)
        return None

    result = {
        "slug": slug,
        "n": n,
        "gfs_raw":  {"mae": round(_mae(errs["gfs_raw"]), 3),
                     "rmse": round(_rmse(errs["gfs_raw"]), 3),
                     "bias": round(statistics.mean(errs["gfs_raw"]), 3)},
        "old_ens":  {"mae": round(_mae(errs["old"]), 3),
                     "rmse": round(_rmse(errs["old"]), 3),
                     "bias": round(statistics.mean(errs["old"]), 3)},
        "new_ens":  {"mae": round(_mae(errs["new"]), 3),
                     "rmse": round(_rmse(errs["new"]), 3),
                     "bias": round(statistics.mean(errs["new"]), 3)},
    }

    mae_delta = result["new_ens"]["mae"] - result["old_ens"]["mae"]
    tag = f"new {'BETTER' if mae_delta < 0 else 'WORSE'} {mae_delta:+.3f}°C MAE"
    print(f"n={n} | GFS={result['gfs_raw']['mae']:.2f} old={result['old_ens']['mae']:.2f} new={result['new_ens']['mae']:.2f} | {tag}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days",   type=int, default=180)
    ap.add_argument("--cities", default="")
    ap.add_argument("--out",    default="")
    args = ap.parse_args()

    old_path = ROOT / "strategy" / "skill_matrix_pre_ukmo_jma.json"
    new_path = ROOT / "strategy" / "skill_matrix.json"

    if not old_path.exists():
        sys.exit("No backup matrix found at skill_matrix_pre_ukmo_jma.json")
    if not new_path.exists():
        sys.exit("No new matrix found — run build_skill_matrix first")

    with open(old_path) as f:
        old_sm = json.load(f)
    with open(new_path) as f:
        new_sm = json.load(f)

    # Check new matrix actually has UKMO/JMA for non-EU cities
    atl_new = new_sm.get("stations", {}).get("atlanta", {})
    has_ukmo = "ukmo_seamless" in atl_new
    has_jma  = "jma_seamless" in atl_new
    print(f"New matrix: atlanta has ukmo={has_ukmo} jma={has_jma}")
    if not (has_ukmo or has_jma):
        print("WARNING: new matrix does not have UKMO/JMA for Atlanta — rebuild may not be done yet")

    ens_old = WeightedEnsemble.__new__(WeightedEnsemble)
    ens_old._matrix = old_sm.get("stations", old_sm)

    ens_new = WeightedEnsemble.__new__(WeightedEnsemble)
    ens_new._matrix = new_sm.get("stations", new_sm)

    if args.cities:
        slugs = [s.strip() for s in args.cities.split(",")]
    else:
        slugs = list(STATIONS.keys())

    print(f"\nEvaluating {len(slugs)} cities over {args.days} days of D+1 forecasts\n")

    results = []
    for slug in slugs:
        r = evaluate_city(slug, args.days, ens_old, ens_new)
        if r:
            results.append(r)

    if not results:
        print("No results")
        return

    # Summary
    print("\n" + "="*80)
    print(f"{'CITY':<20} {'N':>5} {'GFS MAE':>8} {'OLD MAE':>8} {'NEW MAE':>8} {'DELTA':>8} {'WINNER':>8}")
    print("-"*80)

    total_old, total_new, n_better, n_worse = [], [], 0, 0
    for r in sorted(results, key=lambda x: x["new_ens"]["mae"] - x["old_ens"]["mae"]):
        delta = r["new_ens"]["mae"] - r["old_ens"]["mae"]
        winner = "NEW" if delta < -0.01 else ("OLD" if delta > 0.01 else "TIE")
        if winner == "NEW": n_better += 1
        elif winner == "OLD": n_worse += 1
        print(f"{r['slug']:<20} {r['n']:>5} {r['gfs_raw']['mae']:>8.3f} "
              f"{r['old_ens']['mae']:>8.3f} {r['new_ens']['mae']:>8.3f} "
              f"{delta:>+8.3f} {winner:>8}")
        total_old.append(r["old_ens"]["mae"])
        total_new.append(r["new_ens"]["mae"])

    print("="*80)
    avg_old = statistics.mean(total_old)
    avg_new = statistics.mean(total_new)
    print(f"{'AVERAGE':<20} {'':>5} {'':>8} {avg_old:>8.3f} {avg_new:>8.3f} "
          f"{avg_new-avg_old:>+8.3f} "
          f"{'NEW' if avg_new < avg_old else 'OLD':>8}")
    print(f"\nNew better in {n_better}/{len(results)} cities, worse in {n_worse}/{len(results)}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.out}")


if __name__ == "__main__":
    main()
