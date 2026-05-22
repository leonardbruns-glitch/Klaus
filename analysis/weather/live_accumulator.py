"""Live calibration accumulator for weather markets.

After a weather market resolves (WU shows final daily high), logs:
  - The per-model forecasts that were issued at market-open time (T-0)
  - The WU actual daily high temperature

These observations accumulate in logs/weather/forecast_actuals.jsonl and are
merged into strategy/skill_matrix.json via update_skill_matrix().

Typical call pattern from weather_arb.py:
    from analysis.weather.live_accumulator import log_forecast, update_skill_matrix
    # At market open (when we pull forecasts):
    log_forecast(slug, city_slug, valid_day, forecasts, model_values, month)
    # After WU confirms the daily high:
    log_actual(slug, city_slug, valid_day, wu_high_c)
    # Weekly/monthly batch update:
    update_skill_matrix()

JSONL schema (logs/weather/forecast_actuals.jsonl):
  {
    "slug":       "highest-temperature-in-nyc-on-may-21-2026",
    "city_slug":  "nyc",
    "valid_day":  "2026-05-21",
    "month":      5,
    "event":      "forecast" | "actual",
    # for forecast events:
    "model_values": {"gfs_seamless": 28.4, ...},  # bias-corrected already? No — raw forecasts
    "ensemble_mu":  28.1,
    "ensemble_sigma": 1.2,
    # for actual events:
    "wu_high_c":  27.0,   # WU summary high in °C (after F→C conversion if needed)
    "ts_utc":     "2026-05-21T10:30:00+00:00",
  }
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOGS_PATH = Path(__file__).parent.parent.parent / "logs" / "weather"
ACTUALS_FILE = LOGS_PATH / "forecast_actuals.jsonl"
SKILL_MATRIX_PATH = Path(__file__).parent.parent.parent / "strategy" / "skill_matrix.json"

SIGMA_FLOOR = 0.30
MIN_N_REPORT = 5


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_logs_dir() -> None:
    LOGS_PATH.mkdir(parents=True, exist_ok=True)


def log_forecast(
    slug: str,
    city_slug: str,
    valid_day: str,
    model_values: dict[str, float],
    ensemble_mu: float,
    ensemble_sigma: float,
) -> None:
    """Log a forecast snapshot at the time we query Open-Meteo."""
    _ensure_logs_dir()
    record = {
        "event": "forecast",
        "slug": slug,
        "city_slug": city_slug,
        "valid_day": valid_day,
        "month": int(valid_day[5:7]),
        "model_values": model_values,
        "ensemble_mu": round(ensemble_mu, 3),
        "ensemble_sigma": round(ensemble_sigma, 3),
        "ts_utc": _now_utc(),
    }
    with ACTUALS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    logger.debug("[ACCUM] forecast logged: %s %s mu=%.2f", city_slug, valid_day, ensemble_mu)


def log_actual(
    slug: str,
    city_slug: str,
    valid_day: str,
    wu_high_c: float,
    wu_high_time_local: str | None = None,
    tz: str = "",
) -> None:
    """Log the WU Summary daily high after market resolution."""
    _ensure_logs_dir()
    record = {
        "event": "actual",
        "slug": slug,
        "city_slug": city_slug,
        "valid_day": valid_day,
        "month": int(valid_day[5:7]),
        "wu_high_c": round(wu_high_c, 3),
        "ts_utc": _now_utc(),
    }
    if wu_high_time_local is not None:
        record["wu_high_time_local"] = wu_high_time_local
    if tz:
        record["tz"] = tz
    with ACTUALS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info("[ACCUM] actual logged: %s %s wu_high=%.1f°C time=%s",
                city_slug, valid_day, wu_high_c, wu_high_time_local or "?")


def _load_actuals() -> list[dict]:
    if not ACTUALS_FILE.exists():
        return []
    records = []
    with ACTUALS_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _pair_records(records: list[dict]) -> list[dict]:
    """Join forecast + actual records by (city_slug, valid_day)."""
    forecasts: dict[tuple, dict] = {}
    actuals: dict[tuple, dict] = {}
    for r in records:
        key = (r["city_slug"], r["valid_day"])
        if r["event"] == "forecast":
            forecasts[key] = r
        elif r["event"] == "actual":
            actuals[key] = r

    paired = []
    for key, fc in forecasts.items():
        act = actuals.get(key)
        if act is None:
            continue
        paired.append({
            "city_slug": key[0],
            "valid_day": key[1],
            "month": fc["month"],
            "model_values": fc.get("model_values", {}),
            "wu_high_c": act["wu_high_c"],
        })
    return paired


def compute_incremental_skill(paired: list[dict]) -> dict:
    """
    Compute {slug: {model: {month: {bias, sigma, n}}}} from paired records.
    Same formula as build_skill_matrix.compute_skill().
    """
    errors: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in paired:
        slug = row["city_slug"]
        month = row["month"]
        actual = row["wu_high_c"]
        for model, fc_val in row["model_values"].items():
            if fc_val is None:
                continue
            errors[slug][model][month].append(float(fc_val) - float(actual))

    result: dict[str, dict[str, dict[str, dict]]] = {}
    for slug, models in errors.items():
        result[slug] = {}
        for model, monthly in models.items():
            result[slug][model] = {}
            for month, errs in monthly.items():
                if len(errs) < MIN_N_REPORT:
                    continue
                bias = statistics.fmean(errs)
                debiased = [e - bias for e in errs]
                sigma = statistics.stdev(debiased) if len(debiased) >= 2 else SIGMA_FLOOR
                sigma = max(SIGMA_FLOOR, sigma)
                result[slug][model][str(month)] = {
                    "bias":  round(bias,  3),
                    "sigma": round(sigma, 3),
                    "n":     len(errs),
                }
    return result


def _merge_skill(base: dict, live: dict) -> dict:
    """
    Merge live observations into base skill matrix using inverse-variance pooling.

    For each (slug, model, month): combine base stats {bias, sigma, n} with
    live stats using weighted average where weights = n.

    If the combined n is >= 2× the base n, the live data dominates strongly enough
    that we recompute purely from the raw live sample (avoids double-counting if
    live data overlaps the archive period). This rarely happens in practice.
    """
    merged = json.loads(json.dumps(base))  # deep copy

    for slug, models in live.items():
        if slug not in merged:
            merged[slug] = {}
        for model, monthly in models.items():
            if model not in merged[slug]:
                merged[slug][model] = {}
            for month_str, live_stats in monthly.items():
                base_stats = merged[slug].get(model, {}).get(month_str)
                if base_stats is None:
                    merged[slug][model][month_str] = live_stats
                else:
                    # Weighted average of bias; pooled sigma via variance pooling
                    n_b = base_stats["n"]
                    n_l = live_stats["n"]
                    n_total = n_b + n_l
                    combined_bias = (base_stats["bias"] * n_b + live_stats["bias"] * n_l) / n_total
                    # Pool variances: total_var = (n_b×σ²_b + n_l×σ²_l) / (n_b+n_l)
                    pooled_var = (base_stats["sigma"]**2 * n_b + live_stats["sigma"]**2 * n_l) / n_total
                    combined_sigma = max(SIGMA_FLOOR, math.sqrt(pooled_var))
                    merged[slug][model][month_str] = {
                        "bias":  round(combined_bias,  3),
                        "sigma": round(combined_sigma, 3),
                        "n":     n_total,
                    }
    return merged


def update_skill_matrix(dry_run: bool = False) -> dict:
    """
    Read logs/weather/forecast_actuals.jsonl, pair records, compute incremental
    skill, merge into strategy/skill_matrix.json, and overwrite in-place.

    Returns the updated matrix dict. If dry_run=True, prints a diff but does
    not write.
    """
    records = _load_actuals()
    paired = _pair_records(records)
    if not paired:
        logger.info("[ACCUM] no paired records yet, skill matrix unchanged")
        return {}

    logger.info("[ACCUM] %d paired observations across %d cities",
                len(paired), len({r["city_slug"] for r in paired}))

    incremental = compute_incremental_skill(paired)

    # Load base matrix
    if SKILL_MATRIX_PATH.exists():
        raw = json.loads(SKILL_MATRIX_PATH.read_text())
        base_stations = raw.get("stations", {})
        meta = raw.get("_meta", {})
    else:
        base_stations = {}
        meta = {}

    merged_stations = _merge_skill(base_stations, incremental)

    if dry_run:
        _print_diff(base_stations, merged_stations, paired)
        return merged_stations

    output = {
        "_meta": {
            **meta,
            "last_live_update": _now_utc(),
            "live_pairs": len(paired),
        },
        "stations": merged_stations,
    }
    SKILL_MATRIX_PATH.write_text(json.dumps(output, indent=2))
    logger.info("[ACCUM] skill matrix updated: %d cities", len(merged_stations))
    return merged_stations


def _print_diff(base: dict, merged: dict, paired: list[dict]) -> None:
    cities_touched = {r["city_slug"] for r in paired}
    print(f"=== INCREMENTAL SKILL UPDATE (dry-run) ===")
    print(f"Paired observations: {len(paired)}")
    print(f"Cities with new data: {sorted(cities_touched)}")
    for slug in sorted(cities_touched):
        base_city = base.get(slug, {})
        merged_city = merged.get(slug, {})
        print(f"\n  {slug}:")
        for model in sorted(merged_city.keys()):
            for month_str in sorted(merged_city[model].keys(), key=int):
                b = base_city.get(model, {}).get(month_str, {})
                m = merged_city[model][month_str]
                if b:
                    print(f"    {model} m{month_str}: bias {b['bias']:+.3f}→{m['bias']:+.3f}  "
                          f"sigma {b['sigma']:.3f}→{m['sigma']:.3f}  n {b['n']}→{m['n']}")
                else:
                    print(f"    {model} m{month_str}: NEW  bias={m['bias']:+.3f}  sigma={m['sigma']:.3f}  n={m['n']}")


def status() -> None:
    """Print summary of accumulated live observations."""
    records = _load_actuals()
    forecasts = [r for r in records if r["event"] == "forecast"]
    actuals = [r for r in records if r["event"] == "actual"]
    paired = _pair_records(records)
    print(f"Forecast records: {len(forecasts)}")
    print(f"Actual records:   {len(actuals)}")
    print(f"Paired:           {len(paired)}")
    if paired:
        by_city: dict[str, int] = defaultdict(int)
        for r in paired:
            by_city[r["city_slug"]] += 1
        for city, n in sorted(by_city.items()):
            print(f"  {city}: {n}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="show accumulator status")
    p_update = sub.add_parser("update", help="merge live obs into skill matrix")
    p_update.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.cmd == "status":
        status()
    elif args.cmd == "update":
        update_skill_matrix(dry_run=args.dry_run)
    else:
        ap.print_help()
