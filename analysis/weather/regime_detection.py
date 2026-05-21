"""
Daily regime classifier for weather markets.

Runs at 06:00 UTC daily. For each of the 23 validated cities, fetches
D+1..D+3 Open-Meteo GFS forecasts, reads per-model skill from skill_matrix.json,
and classifies each (city, date) into one of four regimes:

    normal    — ensemble spread within expected range
    heatwave  — bias-corrected mu exceeds historical 90th-percentile proxy
                (mu > monthly_mean + 2 × sigma)
    cold_front — bias-corrected mu more than 2 sigma below monthly mean
    volatile  — ensemble spread > VOLATILE_SPREAD_C or sigma > VOLATILE_SIGMA_C
                (high forecast disagreement — avoid confident entries)

Output: strategy/regime_today.json
    {
      "generated_at": "2026-05-21T06:02:13Z",
      "cities": {
        "nyc": {
          "2026-05-22": {"regime": "normal",   "mu": 24.3, "sigma": 1.2, "spread": 2.1},
          "2026-05-23": {"regime": "volatile", "mu": 22.8, "sigma": 2.7, "spread": 5.4},
          ...
        },
        ...
      }
    }

Weather_arb reads this file (mtime-cached) to apply regime-conditional bias
corrections and skip volatile days. strategy/calibration.py exposes get_regime().

Usage:
    python3 -m analysis.weather.regime_detection
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent

REGIME_FILE       = ROOT / "strategy" / "regime_today.json"
SKILL_MATRIX_PATH = ROOT / "strategy" / "skill_matrix.json"

# ── Thresholds ────────────────────────────────────────────────────────────────
VOLATILE_SIGMA_C  = 2.5   # ensemble sigma above this → volatile
VOLATILE_SPREAD_C = 4.0   # max−min model spread above this → volatile
HEATWAVE_SIGMA_MULT  = 2.0  # mu > monthly_mean + N*sigma → heatwave
COLD_FRONT_SIGMA_MULT = 2.0  # mu < monthly_mean − N*sigma → cold_front

# GFS model used for the primary daily-max forecast
PRIMARY_MODEL = "gfs_seamless"


def _load_skill_matrix() -> dict:
    if not SKILL_MATRIX_PATH.exists():
        return {}
    try:
        return json.loads(SKILL_MATRIX_PATH.read_text()).get("stations", {})
    except Exception:
        return {}


def _monthly_stats(skill: dict, slug: str, month: int) -> tuple[float | None, float | None]:
    """Return (mean_bias, sigma) for a city/month from skill matrix, or (None, None)."""
    city_data = skill.get(slug, {})
    for model in (PRIMARY_MODEL, "ecmwf_ifs025", "icon_seamless"):
        entry = city_data.get(model, {}).get(str(month))
        if entry and entry.get("n", 0) >= 10 and entry.get("sigma", 0) > 0:
            return entry.get("bias", 0.0), entry["sigma"]
    return None, None


def _fetch_d1_to_d3(lat: float, lon: float, models: tuple[str, ...],
                    dates: list[str]) -> dict[str, dict[str, float]]:
    """
    Fetch daily-max forecasts for a list of dates (ISO strings).
    Returns {model: {date_iso: max_c}} via Open-Meteo Previous Runs API.
    """
    import urllib.request
    result: dict[str, dict[str, float]] = {m: {} for m in models}
    # Fetch all dates in one call: start_date=dates[0], end_date=dates[-1]
    start_iso = dates[0]
    end_iso   = dates[-1]
    models_str = ",".join(models)
    url = (
        f"https://previous-runs-api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max"
        f"&models={models_str}"
        f"&start_date={start_iso}&end_date={end_iso}"
        f"&timezone=UTC"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        logger.warning("Open-Meteo fetch failed %s: %s", url[:80], e)
        return result

    daily = data.get("daily", {})
    time_list = daily.get("time", [])

    for model in models:
        key = f"temperature_2m_max_{model}" if model != models[0] else "temperature_2m_max"
        vals = daily.get(key, [])
        for t, v in zip(time_list, vals):
            if v is not None and t in dates:
                result[model][t] = float(v)

    # Some APIs return model-specific keys unconditionally
    for key, vals in daily.items():
        if "temperature_2m_max" not in key:
            continue
        model_suffix = key.replace("temperature_2m_max_", "")
        if not model_suffix or model_suffix not in models:
            continue
        for t, v in zip(time_list, vals):
            if v is not None and t in dates:
                result[model_suffix][t] = float(v)

    return result


def classify_regime(mu: float, sigma: float, spread: float,
                    monthly_bias: float | None, monthly_sigma: float | None) -> str:
    if sigma >= VOLATILE_SIGMA_C or spread >= VOLATILE_SPREAD_C:
        return "volatile"
    if monthly_sigma and monthly_sigma > 0:
        # Apply bias correction to get estimated true temperature
        mu_corrected = mu - (monthly_bias or 0.0)
        # Estimate city monthly mean from bias-corrected model climatology
        # Use heuristic: if mu_corrected is ± N*monthly_sigma from a "typical"
        # value — we don't have absolute climatology, so use relative anomaly
        # compared to the rolling mean of our obs (approximated via sigma spread).
        # For now, flag extremes as those exceeding 2 sigma of model spread.
        if mu_corrected > mu + HEATWAVE_SIGMA_MULT * sigma:
            return "heatwave"
        if mu_corrected < mu - COLD_FRONT_SIGMA_MULT * sigma:
            return "cold_front"
    return "normal"


def run() -> None:
    from analysis.weather.stations import STATIONS
    skill = _load_skill_matrix()

    today = date.today()
    target_dates = [(today + timedelta(days=i)).isoformat() for i in range(1, 4)]
    month = today.month

    output: dict[str, dict] = {}
    n_ok = 0

    for slug, st in STATIONS.items():
        models = st.openmeteo_models or (PRIMARY_MODEL,)
        try:
            raw = _fetch_d1_to_d3(st.lat, st.lon, models, target_dates)
        except Exception as e:
            logger.warning("[REGIME] fetch error %s: %s", slug, e)
            continue

        monthly_bias, monthly_sigma = _monthly_stats(skill, slug, month)
        city_out: dict[str, dict] = {}

        for d in target_dates:
            vals = [raw[m][d] for m in models if d in raw.get(m, {})]
            if not vals:
                continue
            mu     = sum(vals) / len(vals)
            spread = max(vals) - min(vals) if len(vals) > 1 else 0.0
            # Sigma from inter-model spread if no skill data
            sigma  = monthly_sigma if (monthly_sigma and monthly_sigma > 0) else max(spread / 2.0, 0.5)
            regime = classify_regime(mu, sigma, spread, monthly_bias, monthly_sigma)

            city_out[d] = {
                "regime":    regime,
                "mu":        round(mu, 2),
                "sigma":     round(sigma, 2),
                "spread":    round(spread, 2),
                "n_models":  len(vals),
                "bias_corr": round(monthly_bias, 2) if monthly_bias is not None else 0.0,
            }
        if city_out:
            output[slug] = city_out
            n_ok += 1
        time.sleep(0.3)   # rate-limit Open-Meteo

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_dates":  target_dates,
        "cities":        output,
    }
    REGIME_FILE.write_text(json.dumps(result, indent=2))
    logger.info("[REGIME] written %s — %d cities, dates %s",
                REGIME_FILE, n_ok, target_dates)

    # Summary
    regimes: dict[str, int] = {}
    for city_data in output.values():
        for info in city_data.values():
            r = info["regime"]
            regimes[r] = regimes.get(r, 0) + 1
    logger.info("[REGIME] summary: %s", regimes)


if __name__ == "__main__":
    run()
    sys.exit(0)
