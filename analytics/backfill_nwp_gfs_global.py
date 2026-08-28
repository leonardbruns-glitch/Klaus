"""Backfill full-coverage gfs_seamless NWP for the non-US cities.

The original pull (stwa_fetch_data.py:201) hardcoded ecmwf_ifs025 for non-US cities,
and that archive returns ~23% nulls -> the residual/skew/β fits in dist_kalman_ev and
stwa_matrix_kelly could only be done for the 11 US/gfs cities. gfs_seamless is GLOBAL and
fully populated, so re-pull it for the non-US cities. Writes a sidecar parquet (same
schema as stwa_nwp.parquet) so the existing file is untouched.

2 years (default 2023-2024) is sufficient to fit per-city skewnorm α + σ + β_h.

Usage:
    PYTHONPATH=/root/Klaus python3 -m analytics.backfill_nwp_gfs_global
    PYTHONPATH=/root/Klaus python3 -m analytics.backfill_nwp_gfs_global --years 2021 2024
"""
from __future__ import annotations

import argparse
import asyncio

import aiohttp
import pandas as pd

from analytics.stwa_fetch_data import fetch_nwp_hourly
from analysis.weather.stations import STATIONS

OUT = "data/stwa_nwp_gfs_global.parquet"


def _is_us(icao: str) -> bool:
    return icao.startswith("K") and len(icao) == 4


async def _run(year_start: int, year_end: int, concurrency: int):
    targets = [(c, st) for c, st in STATIONS.items() if not _is_us(st.icao)]
    print(f"backfilling gfs_seamless for {len(targets)} non-US cities {year_start}-{year_end}")
    sem = asyncio.Semaphore(concurrency)
    frames: list[pd.DataFrame] = []

    async def one(city, st, session):
        async with sem:
            for attempt in range(3):
                try:
                    df = await fetch_nwp_hourly(session, st.lat, st.lon,
                                                "gfs_seamless", year_start, year_end)
                    if df.empty:
                        print(f"  {city:14} EMPTY"); return
                    df["city"] = city
                    df["icao"] = st.icao
                    df["model"] = "gfs_seamless"
                    cov = df["temp_nwp_c"].notna().mean()
                    print(f"  {city:14} rows={len(df):6d} cov={cov:.2f}")
                    frames.append(df[["city", "icao", "time_utc", "temp_nwp_c", "dew_nwp_c", "model"]])
                    return
                except Exception as e:
                    if attempt == 2:
                        print(f"  {city:14} FAIL {str(e)[:70]}")
                    await asyncio.sleep(2 + attempt * 3)

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(one(c, st, session) for c, st in targets))

    if not frames:
        print("no data fetched"); return
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(OUT, index=False)
    print(f"\nwrote {len(out)} rows / {out.city.nunique()} cities -> {OUT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2023, 2024])
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    asyncio.run(_run(args.years[0], args.years[1], args.concurrency))


if __name__ == "__main__":
    main()
