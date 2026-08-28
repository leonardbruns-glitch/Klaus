"""Daily-high scraper for NOAA timeseries cities (Tel Aviv, Moscow).

Polymarket markets for these cities resolve against:
  https://www.weather.gov/wrh/timeseries?site=<ICAO>

The page fetches data from the Synoptic Labs (MesoWest) API using a public
token embedded in the NWS page. No browser required — pure urllib.

Returns the same dict structure as wu_high_scraper.scrape_one for drop-in
use in wu_monitor.py.
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from datetime import date, datetime, timezone

from analysis.weather.stations import Station

SYNOPTIC_URL = "https://api.synopticdata.com/v2/stations/timeseries"
_TOKEN = "7c76618b66c74aee913bdbae4b448bdd"
_REFERER = "https://www.weather.gov/wrh/timeseries"

# Cities that resolve via NOAA timeseries (not WU). Maps city_slug → ICAO.
NOAA_CITY_SITES: dict[str, str] = {
    "tel-aviv": "LLBG",
    "moscow":   "UUWW",
}


def fetch_noaa_daily_max(station: Station, day: date) -> dict:
    """Fetch daily max air temp for a NOAA-resolution city via Synoptic API.

    Queries the UTC window [day 00:00, day 23:59]. The daily high is
    virtually never in the edge-hours near local midnight, so this window
    matches NOAA's local-day summary well enough for calibration.

    Returns same dict structure as wu_high_scraper.scrape_one.
    """
    icao = NOAA_CITY_SITES.get(station.city_slug, station.icao)
    day_str = day.strftime("%Y%m%d")
    api_url = (
        f"{SYNOPTIC_URL}?STID={icao}"
        f"&showemptystations=1"
        f"&start={day_str}0000&end={day_str}2359"
        f"&complete=1&token={_TOKEN}&obtimezone=local"
    )
    out: dict = {
        "city":            station.city_slug,
        "icao":            icao,
        "date":            day.isoformat(),
        "unit_market":     station.unit,
        "bucket_width":    station.bucket_width,
        "tz":              station.tz,
        "url":             f"https://www.weather.gov/wrh/timeseries?site={icao}",
        "fetched_at_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "high_f":          None,
        "high_c":          None,
        "high_time_local": None,
        "low_f":           None,
        "avg_f":           None,
        "no_data":         False,
        "error":           None,
        "source":          "synoptic",
    }
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer":    _REFERER,
            "Origin":     "https://www.weather.gov",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())

        summary = data.get("SUMMARY", {})
        if summary.get("RESPONSE_MESSAGE") != "OK":
            out["error"] = f"Synoptic: {summary.get('RESPONSE_MESSAGE')}"
            out["no_data"] = True
            return out

        stations_data = data.get("STATION", [])
        if not stations_data:
            out["no_data"] = True
            return out

        obs = stations_data[0].get("OBSERVATIONS", {})
        temps = obs.get("air_temp_set_1", [])
        times = obs.get("date_time", [])

        valid = [(t, float(v)) for t, v in zip(times, temps) if v is not None]
        if not valid:
            out["no_data"] = True
            return out

        max_c = max(v for _, v in valid)
        max_time = next(t for t, v in valid if v == max_c)
        min_c = min(v for _, v in valid)
        mean_c = sum(v for _, v in valid) / len(valid)

        out["high_c"] = round(max_c, 2)
        out["high_f"] = round(max_c * 9.0 / 5.0 + 32.0, 2)
        out["high_time_local"] = max_time
        out["low_f"]  = round(min_c * 9.0 / 5.0 + 32.0, 2)
        out["avg_f"]  = round(mean_c * 9.0 / 5.0 + 32.0, 2)

    except urllib.error.HTTPError as e:
        out["error"] = f"HTTPError {e.code}: {e.reason}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


async def async_fetch_noaa_daily_max(station: Station, day: date) -> dict:
    """Async wrapper — runs fetch_noaa_daily_max in a thread pool."""
    return await asyncio.to_thread(fetch_noaa_daily_max, station, day)
