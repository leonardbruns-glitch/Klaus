#!/usr/bin/env python3
"""
Calibrate 15 new cities for Polymarket weather bot.
Fetches ERA5 + GFS data from Open-Meteo to compute:
1. Peak hour UTC by month (median UTC hour of daily max temp)
2. NWP bias by month (mean(actual_max - GFS_max) per calendar month)
"""
import json
import time
import urllib.request
import urllib.error
from collections import defaultdict
import statistics

# City definitions: slug -> (icao, lat, lon)
CITIES = {
    "ankara":       ("LTAC", 40.1281, 32.9951),   # Esenboga Airport
    "busan":        ("RKPK", 35.1795, 128.9382),  # Gimhae International
    "chengdu":      ("ZUUU", 30.5785, 103.9473),  # Chengdu Shuangliu
    "chongqing":    ("ZUCK", 29.7192, 106.6418),  # Chongqing Jiangbei
    "jeddah":       ("OEJN", 21.6796, 39.1565),   # King Abdulaziz Intl
    "jinan":        ("ZSJN", 36.8572, 117.0160),  # Jinan Yaoqiang
    "karachi":      ("OPKC", 24.9065, 67.1608),   # Jinnah Intl
    "kuala-lumpur": ("WMKK", 2.7456, 101.7072),   # KLIA
    "lucknow":      ("VILK", 26.7606, 80.8893),   # Chaudhary Charan Singh
    "manila":       ("RPLL", 14.5086, 121.0197),  # Ninoy Aquino Intl
    "panama-city":  ("MPTO", 9.0714, -79.3835),   # Tocumen Intl
    "seoul":        ("RKSI", 37.4692, 126.4505),  # Incheon Intl
    "wellington":   ("NZWN", -41.3272, 174.8054), # Wellington Airport
    "wuhan":        ("ZHHH", 30.7838, 114.2081),  # Wuhan Tianhe
    "zhengzhou":    ("ZHCC", 34.5197, 113.8408),  # Xinzheng Intl
}


def fetch_url(url, retries=3, delay=2):
    """Fetch URL with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt+1} after error: {e}")
                time.sleep(delay * (attempt + 1))
            else:
                raise
    return None


def get_peak_hours(lat, lon):
    """
    Fetch ERA5 hourly temp 2023-2024, find UTC hour of daily max per day,
    return dict {month: median_hour}.
    """
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m"
        f"&start_date=2023-01-01&end_date=2024-12-31"
        f"&timezone=UTC"
    )
    data = fetch_url(url)
    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]

    # Group by date -> list of (hour, temp)
    day_data = defaultdict(list)
    for t_str, temp in zip(times, temps):
        if temp is None:
            continue
        date_part = t_str[:10]
        hour = int(t_str[11:13])
        day_data[date_part].append((hour, temp))

    # For each day, find hour of max temp; then aggregate by month
    month_hours = defaultdict(list)
    for date_str, hourly_list in day_data.items():
        if not hourly_list:
            continue
        month = int(date_str[5:7])
        max_hour = max(hourly_list, key=lambda x: x[1])[0]
        month_hours[month].append(max_hour)

    result = {}
    for m in range(1, 13):
        hours = month_hours.get(m, [])
        if hours:
            result[m] = int(statistics.median(hours))
        else:
            result[m] = 14  # fallback
    return result


def get_nwp_bias(lat, lon):
    """
    Fetch actual ERA5 daily max and GFS daily max 2023-01-01 to 2025-05-01.
    Return dict {month: mean_bias} where bias = actual - GFS.
    """
    # Actual daily max from ERA5
    url_actual = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max"
        f"&start_date=2023-01-01&end_date=2025-04-30"
        f"&timezone=UTC"
    )
    # GFS hourly temps (models=gfs_seamless) then take daily max
    url_gfs = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m"
        f"&models=gfs_seamless"
        f"&start_date=2023-01-01&end_date=2025-04-30"
        f"&timezone=UTC"
    )

    print(f"    Fetching actual daily max...")
    data_actual = fetch_url(url_actual)
    dates_actual = data_actual["daily"]["time"]
    maxes_actual = data_actual["daily"]["temperature_2m_max"]
    actual_by_date = {d: v for d, v in zip(dates_actual, maxes_actual) if v is not None}

    time.sleep(0.5)  # be gentle to API

    print(f"    Fetching GFS hourly...")
    data_gfs = fetch_url(url_gfs)
    gfs_times = data_gfs["hourly"]["time"]
    gfs_temps = data_gfs["hourly"]["temperature_2m"]

    # Compute daily max from GFS hourly
    gfs_daily = defaultdict(list)
    for t_str, temp in zip(gfs_times, gfs_temps):
        if temp is None:
            continue
        date_part = t_str[:10]
        gfs_daily[date_part].append(temp)
    gfs_max_by_date = {d: max(v) for d, v in gfs_daily.items() if v}

    # Compute bias by month
    month_biases = defaultdict(list)
    for date_str, actual_max in actual_by_date.items():
        if date_str not in gfs_max_by_date:
            continue
        gfs_max = gfs_max_by_date[date_str]
        bias = actual_max - gfs_max
        month = int(date_str[5:7])
        month_biases[month].append(bias)

    result = {}
    for m in range(1, 13):
        biases = month_biases.get(m, [])
        if biases:
            result[m] = round(sum(biases) / len(biases), 3)
        else:
            result[m] = 0.0
    return result


def build_bias_dict(monthly_bias):
    """Build {month_hour: value} dict for all 12 months x 24 hours."""
    d = {}
    for m in range(1, 13):
        val = monthly_bias.get(m, 0.0)
        for h in range(24):
            d[f"{m}_{h}"] = val
    return d


def main():
    # Default Helsinki kappa/sigma values
    DEFAULT_KAPPA = {"0": 0.374, "1": 0.327, "2": 0.284, "3": 0.440}
    DEFAULT_SIGMA = {"0": 1.368, "1": 1.036, "2": 1.051, "3": 1.330}
    DEFAULT_SIGMA_OBS = 1.423
    DEFAULT_ALPHA_HUM = {str(k): 0.0 for k in range(24)}

    all_peak_hours = {}
    all_stwa_params = {}

    cities_list = list(CITIES.items())

    for idx, (slug, (icao, lat, lon)) in enumerate(cities_list):
        print(f"\n[{idx+1}/{len(cities_list)}] Processing {slug} ({icao}) lat={lat} lon={lon}")

        try:
            print(f"  Computing peak hours...")
            peak_hours = get_peak_hours(lat, lon)
            time.sleep(0.5)

            print(f"  Computing NWP bias...")
            monthly_bias = get_nwp_bias(lat, lon)

            all_peak_hours[slug] = peak_hours

            # May = month 5 for peak_hour_utc
            may_peak = peak_hours.get(5, 14)

            all_stwa_params[slug] = {
                "icao": icao,
                "lat": lat,
                "lon": lon,
                "unit": "C",
                "peak_hour_utc": may_peak,
                "kappa": DEFAULT_KAPPA,
                "sigma": DEFAULT_SIGMA,
                "sigma_obs": DEFAULT_SIGMA_OBS,
                "bias": build_bias_dict(monthly_bias),
                "alpha_humidity": DEFAULT_ALPHA_HUM,
            }

            print(f"  Peak hours: {peak_hours}")
            print(f"  Monthly bias: {monthly_bias}")

        except Exception as e:
            print(f"  ERROR for {slug}: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(1.0)  # rate limit between cities

    print("\n" + "="*70)
    print("CITY_PEAK_HOUR_UTC = {")
    for slug, peaks in all_peak_hours.items():
        hours_str = ", ".join(f"{m}: {h}" for m, h in sorted(peaks.items()))
        print(f'    "{slug}": {{{hours_str}}},')
    print("}")

    print("\n" + "="*70)
    print("STWA_PARAMS (JSON):")
    print(json.dumps(all_stwa_params, indent=2))


if __name__ == "__main__":
    main()
