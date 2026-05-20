"""
Historical diurnal temperature analysis for all 7 validated Polymarket weather stations.

Pulls 5 years of ASOS hourly data from Iowa State Mesonet, computes per-station/month:
  - Mean T(hour) diurnal curve
  - Typical peak UTC hour
  - std(T_daily_max) — base sigma for bucket probability
  - mean(T_max - T(hour)) — remaining rise from each observation hour
  - Sky factor calibration: CLR vs OVC days vs daily max

Usage: python3 -m analysis.weather.diurnal_analysis [--out /tmp/diurnal.json]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from io import StringIO

import pandas as pd
import numpy as np

# 7 validated stations
STATIONS = {
    "nyc":           ("KLGA",  "New York City"),
    "chicago":       ("KORD",  "Chicago"),
    "los-angeles":   ("KLAX",  "Los Angeles"),
    "miami":         ("KMIA",  "Miami"),
    "san-francisco": ("KSFO",  "San Francisco"),
    "tokyo":         ("RJTT",  "Tokyo"),
    "london":        ("EGLC",  "London"),
}

ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
YEARS_BACK = 5   # 2021-2025
USER_AGENT = "Klaus-WeatherBot/1.0 (research; contact: leonard.bruns@gmail.com)"


def fetch_asos(icao: str, year_start: int, year_end: int) -> pd.DataFrame:
    """Fetch hourly ASOS data for a station over the given year range."""
    params = urllib.parse.urlencode({
        "station": icao,
        "data": "tmpf,skyc1",
        "year1": year_start, "month1": 1, "day1": 1,
        "year2": year_end,   "month2": 12, "day2": 31,
        "tz": "UTC",
        "format": "onlycomma",
        "latlon": "no",
        "direct": "no",
        "report_type": "2",   # routine METAR only (not specials)
    })
    url = f"{ASOS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")

    lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()

    df = pd.read_csv(StringIO("\n".join(lines)))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"valid": "time_utc", "tmpf": "temp_f", "skyc1": "sky"})
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"])
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")
    df["temp_c"] = (df["temp_f"] - 32) * 5 / 9
    df = df.dropna(subset=["temp_c"])
    df["date_utc"] = df["time_utc"].dt.date
    df["hour_utc"] = df["time_utc"].dt.hour
    df["month"] = df["time_utc"].dt.month
    return df[["time_utc", "date_utc", "hour_utc", "month", "temp_c", "sky"]]


def analyse_station(df: pd.DataFrame, name: str) -> dict:
    """Compute diurnal statistics per month for one station."""
    results = {}

    for month in range(1, 13):
        mdf = df[df["month"] == month].copy()
        if len(mdf) < 100:
            continue

        # ── Diurnal curve: mean temp by UTC hour ─────────────────────────────
        diurnal = mdf.groupby("hour_utc")["temp_c"].agg(["mean", "std", "count"])
        diurnal_mean = diurnal["mean"].to_dict()

        # ── Daily max stats ───────────────────────────────────────────────────
        daily_max = mdf.groupby("date_utc")["temp_c"].max()
        daily_max = daily_max[daily_max > -50]   # exclude bad data
        sigma_daily_max = float(daily_max.std())
        mean_daily_max  = float(daily_max.mean())

        # Typical peak UTC hour (hour of daily max, averaged over all days)
        def peak_hour(grp):
            if grp.empty: return np.nan
            return int(grp["temp_c"].idxmax() if hasattr(grp["temp_c"].idxmax(), '__int__') else np.nan)

        daily_peak_hour = (
            mdf.groupby("date_utc")
               .apply(lambda g: g.loc[g["temp_c"].idxmax(), "hour_utc"] if not g.empty else np.nan,
                      include_groups=False)
               .dropna()
        )
        mean_peak_hour = float(daily_peak_hour.mean())
        std_peak_hour  = float(daily_peak_hour.std())

        # ── Remaining rise from each hour ─────────────────────────────────────
        # For each day, compute (daily_max - T_at_hour_h) per hour h
        # This tells us how much more the temp rises after observing at hour h
        remaining_rise = {}
        for h in range(24):
            hour_obs = mdf[mdf["hour_utc"] == h][["date_utc", "temp_c"]].rename(
                columns={"temp_c": "t_obs"}
            )
            day_max = daily_max.reset_index().rename(
                columns={"temp_c": "t_max", "date_utc": "date_utc"}
            )
            merged = hour_obs.merge(day_max, on="date_utc", how="inner")
            if len(merged) < 20:
                continue
            rise = (merged["t_max"] - merged["t_obs"]).clip(lower=0)
            remaining_rise[h] = {
                "mean": round(float(rise.mean()), 2),
                "p25":  round(float(rise.quantile(0.25)), 2),
                "p75":  round(float(rise.quantile(0.75)), 2),
                "n":    len(rise),
            }

        # ── Sky factor calibration ────────────────────────────────────────────
        # Compare daily max on CLR/FEW days vs BKN/OVC days at same forecast baseline
        # Proxy: compare daily max distribution by worst-sky-cover-of-day
        SKY_RANK = {"CLR": 0, "SKC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4}
        mdf["sky_rank"] = mdf["sky"].map(SKY_RANK).fillna(2)
        worst_sky = mdf.groupby("date_utc")["sky_rank"].max()
        sky_by_day = pd.DataFrame({"sky_rank": worst_sky, "daily_max": daily_max})
        sky_by_day = sky_by_day.dropna()

        sky_max_mean = {}
        for rank, label in [(0, "CLR/FEW"), (1, "FEW"), (2, "SCT"), (3, "BKN"), (4, "OVC")]:
            sub = sky_by_day[sky_by_day["sky_rank"] == rank]["daily_max"]
            if len(sub) >= 10:
                sky_max_mean[label] = round(float(sub.mean()), 2)

        results[month] = {
            "n_days":         int(len(daily_max)),
            "mean_daily_max": round(mean_daily_max, 2),
            "sigma_daily_max": round(sigma_daily_max, 2),
            "mean_peak_hour_utc": round(mean_peak_hour, 1),
            "std_peak_hour":     round(std_peak_hour, 1),
            "diurnal_mean_c":    {int(k): round(v, 2) for k, v in diurnal_mean.items()},
            "remaining_rise":    remaining_rise,
            "sky_daily_max":     sky_max_mean,
        }

    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/diurnal.json")
    ap.add_argument("--station", default=None, help="single city slug to test")
    args = ap.parse_args()

    import datetime
    year_end   = datetime.date.today().year - 1   # full years only
    year_start = year_end - YEARS_BACK + 1

    targets = {k: v for k, v in STATIONS.items()
               if args.station is None or k == args.station}

    output = {}
    for slug, (icao, city_name) in targets.items():
        print(f"Fetching {city_name} ({icao}) {year_start}–{year_end} ...", flush=True)
        t0 = time.time()
        try:
            df = fetch_asos(icao, year_start, year_end)
            print(f"  {len(df):,} rows in {time.time()-t0:.1f}s", flush=True)
            if df.empty:
                print(f"  WARNING: no data for {icao}")
                continue
            stats = analyse_station(df, city_name)
            output[slug] = {"icao": icao, "city": city_name, "months": stats}
            print(f"  analysed {sum(v['n_days'] for v in stats.values())} station-days", flush=True)
        except Exception as e:
            print(f"  ERROR {icao}: {e}")
        time.sleep(1)   # be polite to ASOS API

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {args.out}")

    # Print summary table
    print("\n=== PEAK HOUR UTC BY CITY × MONTH ===")
    months = list(range(1, 13))
    print(f"{'City':<16}", end="")
    for m in months:
        print(f" {m:>4}", end="")
    print()
    for slug, data in output.items():
        print(f"{data['city']:<16}", end="")
        for m in months:
            mdata = data["months"].get(m, {})
            ph = mdata.get("mean_peak_hour_utc")
            print(f" {ph:>4.0f}" if ph else "    ?", end="")
        print()

    print("\n=== SIGMA (DAILY MAX STD) BY CITY × MONTH ===")
    print(f"{'City':<16}", end="")
    for m in months:
        print(f" {m:>4}", end="")
    print()
    for slug, data in output.items():
        print(f"{data['city']:<16}", end="")
        for m in months:
            mdata = data["months"].get(m, {})
            s = mdata.get("sigma_daily_max")
            print(f" {s:>4.1f}" if s else "    ?", end="")
        print()

    print("\n=== SKY FACTOR CALIBRATION (May — mean daily max by sky cover) ===")
    for slug, data in output.items():
        may = data["months"].get(5, {})
        sky = may.get("sky_daily_max", {})
        base = sky.get("CLR/FEW", sky.get("CLR", None))
        print(f"{data['city']:<16} CLR={sky.get('CLR/FEW','?'):>5}  SCT={sky.get('SCT','?'):>5}  BKN={sky.get('BKN','?'):>5}  OVC={sky.get('OVC','?'):>5}°C", end="")
        if base and sky.get("OVC"):
            factor = round((sky["OVC"] - may.get("mean_daily_max", sky["OVC"])) /
                           (base - may.get("mean_daily_max", base) + 0.001) + 1, 2)
            print(f"  OVC_factor≈{sky['OVC']/base:.2f}", end="")
        print()


if __name__ == "__main__":
    main()
