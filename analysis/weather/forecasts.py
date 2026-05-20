"""Multi-source next-day max-temperature forecasts for the 7 validated stations.

MVP sources:
  - Open-Meteo daily forecast with multi-model fan-out (ECMWF IFS, GFS, ICON).
    Free, no key, works for all 7 stations.
  - NWS gridpoint forecast. Free, no key, US stations only (KLGA/KORD/KLAX/KMIA/KSFO).

Ensemble: equal-weight mean + sample stdev across surviving sources. Regime-
conditional weighting per the blueprint §3 is deferred until we have ≥30 days
of accumulated (forecast, actual) pairs to fit per-source skill.

From these we derive bucket probabilities via the chosen distribution
(Gaussian for MVP; Gumbel/skew-normal toggleable per station after backtest).

Usage:
    from analysis.weather.forecasts import build_distribution
    from analysis.weather.stations import STATIONS
    from datetime import date

    dist = build_distribution(STATIONS["nyc"], date(2026, 5, 21))
    # -> {'mean_c': 28.4, 'sigma_c': 1.1, 'sources': [...], 'distribution': 'gaussian'}
"""
from __future__ import annotations

import json
import math
import statistics
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Optional

from analysis.weather.stations import Station

USER_AGENT = "Klaus-WeatherBot/1.0 (research; contact: leonard.bruns@gmail.com)"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
NWS_POINTS_URL = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"

# Per-station Open-Meteo model lists live on `Station.openmeteo_models`
# (defined in stations.py). National-agency models added for non-US stations
# (JMA for Tokyo, UKMO/MetNo/Meteofrance for London). GraphCast/Pangu are
# NOT exposed via Open-Meteo's free tier (400 on probe).

DEFAULT_SIGMA_FLOOR_C = 0.5   # when single source or zero-variance, assume at least this
DEFAULT_SIGMA_CEIL_C  = 5.0   # extreme variance is clipped (likely a parsing bug)


@dataclass
class Forecast:
    station: str          # ICAO
    valid_day: str        # YYYY-MM-DD (UTC date — caller maps to station-local day)
    source: str           # 'openmeteo:ecmwf_ifs04', 'nws', etc.
    t_max_c: float
    issued_at_utc: str
    raw_url: str

    def to_jsonable(self) -> dict:
        return asdict(self)


def _http_get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_openmeteo(station: Station, valid_day: date) -> list[Forecast]:
    """Pull daily t_max forecasts from station-specific Open-Meteo models.
    Returns one Forecast per model that returned data (nulls are skipped)."""
    params = {
        "latitude": f"{station.lat:.4f}",
        "longitude": f"{station.lon:.4f}",
        "daily": "temperature_2m_max",
        "temperature_unit": "celsius",
        "timezone": "auto",
        "start_date": valid_day.isoformat(),
        "end_date": valid_day.isoformat(),
        "models": ",".join(station.openmeteo_models),
    }
    url = f"{OPENMETEO_URL}?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url)

    daily = data.get("daily", {})
    times = daily.get("time", [])
    out: list[Forecast] = []
    issued = _now_utc_iso()
    for model in station.openmeteo_models:
        # Open-Meteo returns per-model fields like "temperature_2m_max_ecmwf_ifs04"
        key = f"temperature_2m_max_{model}"
        vals = daily.get(key)
        if not vals:
            continue
        # Match valid_day; usually a single element since start==end
        for i, t in enumerate(times):
            if t == valid_day.isoformat() and vals[i] is not None:
                out.append(Forecast(
                    station=station.icao,
                    valid_day=valid_day.isoformat(),
                    source=f"openmeteo:{model}",
                    t_max_c=float(vals[i]),
                    issued_at_utc=issued,
                    raw_url=url,
                ))
                break
    return out


def fetch_nws(station: Station, valid_day: date) -> Optional[Forecast]:
    """NWS gridpoint daily forecast. Returns None for stations that opt out
    of NWS (`use_nws=False`) or on failure. NWS returns 7-day forecast with
    period names like 'Tuesday', 'Tuesday Night' — the day period's
    `temperature` is the daily high in °F."""
    if not station.use_nws:
        return None
    points_url = NWS_POINTS_URL.format(lat=station.lat, lon=station.lon)
    try:
        pts = _http_get_json(points_url)
        fcst_url = pts["properties"]["forecast"]
        fc = _http_get_json(fcst_url)
    except Exception:
        return None

    periods = fc.get("properties", {}).get("periods", [])
    target_iso = valid_day.isoformat()
    for p in periods:
        # day periods (not Night) have isDaytime=True; startTime contains the date
        if not p.get("isDaytime"):
            continue
        start = p.get("startTime", "")
        if not start.startswith(target_iso):
            continue
        t = p.get("temperature")
        unit = p.get("temperatureUnit", "F")
        if t is None:
            return None
        t_c = (t - 32.0) * 5.0 / 9.0 if unit == "F" else float(t)
        return Forecast(
            station=station.icao,
            valid_day=target_iso,
            source="nws",
            t_max_c=round(t_c, 2),
            issued_at_utc=_now_utc_iso(),
            raw_url=fcst_url,
        )
    return None


def ensemble(forecasts: list[Forecast]) -> tuple[float, float]:
    """Equal-weight mean + sample stdev. Variance is floored/ceiled to avoid
    pathological bucket-probability collapse on n=1 or model agreement."""
    if not forecasts:
        raise ValueError("ensemble() called with no forecasts")
    vals = [f.t_max_c for f in forecasts]
    mean = statistics.fmean(vals)
    if len(vals) >= 2:
        sigma = statistics.stdev(vals)
    else:
        sigma = DEFAULT_SIGMA_FLOOR_C
    sigma = max(DEFAULT_SIGMA_FLOOR_C, min(DEFAULT_SIGMA_CEIL_C, sigma))
    return mean, sigma


def bucket_probs(mean_c: float, sigma_c: float, buckets: list[tuple[float, float]],
                 distribution: str = "gaussian") -> dict[tuple[float, float], float]:
    """Probability mass per bucket. Each bucket is (lo, hi); use ±inf for tails.
    Returns a dict mapping the same (lo,hi) tuple to its probability under
    Normal(mean_c, sigma_c) or Gumbel.

    For Gumbel (extreme-value), parameters are derived from the same (mean, sigma):
        β = sigma · √6 / π, μ = mean − γβ  (γ ≈ 0.5772 Euler-Mascheroni)
    """
    def cdf(x: float) -> float:
        if distribution == "gumbel":
            beta = sigma_c * math.sqrt(6.0) / math.pi
            mu = mean_c - 0.5772156649 * beta
            return math.exp(-math.exp(-(x - mu) / beta))
        # Gaussian
        return 0.5 * (1.0 + math.erf((x - mean_c) / (sigma_c * math.sqrt(2.0))))

    out: dict[tuple[float, float], float] = {}
    for lo, hi in buckets:
        p_lo = 0.0 if lo == float("-inf") else cdf(lo)
        p_hi = 1.0 if hi == float("inf") else cdf(hi)
        out[(lo, hi)] = max(0.0, p_hi - p_lo)
    return out


def build_distribution(station: Station, valid_day: date,
                       distribution: str = "gaussian") -> dict:
    """One-call helper: pull all sources, ensemble, return the parameters.

    Returns: {
        'mean_c': float, 'sigma_c': float, 'n_sources': int,
        'sources': [Forecast.to_jsonable(), ...],
        'distribution': 'gaussian'|'gumbel',
        'station': ICAO, 'valid_day': YYYY-MM-DD,
    }
    Raises ValueError if no source returns data.
    """
    forecasts: list[Forecast] = []
    forecasts.extend(fetch_openmeteo(station, valid_day))
    nws = fetch_nws(station, valid_day)
    if nws is not None:
        forecasts.append(nws)
    if not forecasts:
        raise ValueError(f"no forecast sources returned data for {station.icao} {valid_day}")
    mean, sigma = ensemble(forecasts)
    return {
        "station": station.icao,
        "valid_day": valid_day.isoformat(),
        "mean_c": round(mean, 2),
        "sigma_c": round(sigma, 2),
        "n_sources": len(forecasts),
        "sources": [f.to_jsonable() for f in forecasts],
        "distribution": distribution,
    }


def _main_cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Build forecast distribution for one station+day")
    ap.add_argument("--city", required=True, help="city slug (nyc, tokyo, etc.)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--distribution", default="gaussian", choices=["gaussian", "gumbel"])
    args = ap.parse_args()
    from analysis.weather.stations import STATIONS
    station = STATIONS[args.city]
    valid_day = date.fromisoformat(args.date)
    dist = build_distribution(station, valid_day, distribution=args.distribution)
    print(json.dumps(dist, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main_cli())
