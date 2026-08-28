#!/usr/bin/env python3
"""
NWP calibration for 8 new Polymarket weather cities.
Computes: peak UTC hour by month, and NWP bias by month.
"""

import urllib.request
import json
import sys
from collections import defaultdict
from statistics import median

CITIES = [
    {"name": "ankara",        "icao": "LTAC", "lat": 39.9334, "lon": 32.8597},
    {"name": "busan",         "icao": "RKPK", "lat": 35.1796, "lon": 129.0756},
    {"name": "chengdu",       "icao": "ZUUU", "lat": 30.5728, "lon": 104.0668},
    {"name": "chongqing",     "icao": "ZUCK", "lat": 29.5630, "lon": 106.5516},
    {"name": "jeddah",        "icao": "OEJN", "lat": 21.4858, "lon": 39.1925},
    {"name": "jinan",         "icao": "ZSJN", "lat": 36.6512, "lon": 117.1201},
    {"name": "karachi",       "icao": "OPKC", "lat": 24.8607, "lon": 67.0011},
    {"name": "kuala_lumpur",  "icao": "WMKK", "lat":  3.1390, "lon": 101.6869},
]


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def compute_peak_hours(lat, lon):
    """For each day 2023-2024, find UTC hour of max temp. Return median per month."""
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m"
        f"&start_date=2023-01-01&end_date=2024-12-31"
        f"&timezone=UTC"
    )
    data = fetch_url(url)
    times = data["hourly"]["time"]       # list of "YYYY-MM-DDTHH:00"
    temps = data["hourly"]["temperature_2m"]

    # Group by date
    by_date = defaultdict(list)  # date_str -> list of (hour, temp)
    for t, temp in zip(times, temps):
        if temp is None:
            continue
        date_str = t[:10]  # "YYYY-MM-DD"
        hour = int(t[11:13])
        by_date[date_str].append((hour, temp))

    # For each date, find hour of max temp; group by month
    month_peak_hours = defaultdict(list)
    for date_str, hourtemps in by_date.items():
        if not hourtemps:
            continue
        peak_hour = max(hourtemps, key=lambda x: x[1])[0]
        month = int(date_str[5:7])
        month_peak_hours[month].append(peak_hour)

    result = {}
    for m in range(1, 13):
        hours = month_peak_hours.get(m, [])
        result[m] = int(median(hours)) if hours else None
    return result


def compute_nwp_bias(lat, lon):
    """
    Bias = mean(actual_daily_max - NWP_daily_max) per calendar month.
    actual: daily temperature_2m_max from archive 2023-01-01 to 2025-05-01
    NWP:    hourly temperature_2m with models=gfs_seamless, take daily max
    """
    # Actual daily max
    url_actual = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max"
        f"&start_date=2023-01-01&end_date=2025-05-01"
        f"&timezone=UTC"
    )
    data_actual = fetch_url(url_actual)
    actual_dates = data_actual["daily"]["time"]
    actual_maxes = data_actual["daily"]["temperature_2m_max"]
    actual_by_date = {}
    for d, v in zip(actual_dates, actual_maxes):
        if v is not None:
            actual_by_date[d] = v

    # NWP hourly -> derive daily max
    url_nwp = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m"
        f"&models=gfs_seamless"
        f"&start_date=2023-01-01&end_date=2025-05-01"
        f"&timezone=UTC"
    )
    data_nwp = fetch_url(url_nwp)
    nwp_times = data_nwp["hourly"]["time"]
    nwp_temps = data_nwp["hourly"]["temperature_2m"]

    nwp_by_date = defaultdict(list)
    for t, temp in zip(nwp_times, nwp_temps):
        if temp is not None:
            date_str = t[:10]
            nwp_by_date[date_str].append(temp)

    nwp_daily_max = {}
    for date_str, temps in nwp_by_date.items():
        if temps:
            nwp_daily_max[date_str] = max(temps)

    # Compute bias per month
    month_diffs = defaultdict(list)
    for date_str, act_max in actual_by_date.items():
        nwp_max = nwp_daily_max.get(date_str)
        if nwp_max is None:
            continue
        month = int(date_str[5:7])
        month_diffs[month].append(act_max - nwp_max)

    result = {}
    for m in range(1, 13):
        diffs = month_diffs.get(m, [])
        result[m] = round(sum(diffs) / len(diffs), 3) if diffs else None
    return result


def main():
    for city in CITIES:
        name = city["name"]
        icao = city["icao"]
        lat = city["lat"]
        lon = city["lon"]

        peak = compute_peak_hours(lat, lon)
        bias = compute_nwp_bias(lat, lon)

        print(f"CITY: {name}")
        print(f"ICAO: {icao}")
        print(f"LAT: {lat}")
        print(f"LON: {lon}")
        print(f"PEAK_HOURS: {{{', '.join(f'{m}: {peak[m]}' for m in range(1,13))}}}")
        print(f"BIAS: {{{', '.join(f'{m}: {bias[m]:.3f}' for m in range(1,13))}}}")
        print()
        sys.stdout.flush()


if __name__ == "__main__":
    main()
