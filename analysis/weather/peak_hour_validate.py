"""Validate CITY_PEAK_HOUR_UTC against empirical hour-of-daily-max from ASOS history.

The fade (and STWA phase logic) gates on a *static* per-city/month peak hour.
This script measures two things per city for a given month:

  1. table vs empirical peak hour (mode + median of the UTC hour at which the
     daily max occurs, grouped by LOCAL calendar day — the market resolves on
     the local day's max, so UTC-day grouping would corrupt the argmax).
  2. P(peak_late): the fraction of days whose TRUE peak occurs >1h AFTER the
     POST_PEAK gate opens (table_peak + 1h). This is the fade's structural
     pre-peak false-fire rate — the Jeddah-2026-06-02 failure mode.

Usage: python3 analysis/weather/peak_hour_validate.py [MONTH]
"""
import sys
import numpy as np
import pandas as pd
from analysis.weather.stations import STATIONS
from strategy.weather_arb import CITY_PEAK_HOUR_UTC

MONTH = int(sys.argv[1]) if len(sys.argv) > 1 else 6
PARQUET = "data/stwa_asos.parquet"

tz = {k: s.tz for k, s in STATIONS.items()}
df = pd.read_parquet(PARQUET)

rows = []
for city in sorted(df["city"].unique()):
    z = tz.get(city)
    tbl = CITY_PEAK_HOUR_UTC.get(city, {}).get(MONTH)
    if z is None or tbl is None:
        continue
    sub = df[df["city"] == city].copy()
    lt = sub["time_utc"].dt.tz_convert(z)
    sub = sub.assign(local_date=lt.dt.date, local_month=lt.dt.month,
                     utc_hour=sub["time_utc"].dt.hour)
    sub = sub[sub["local_month"] == MONTH]
    if len(sub) < 200:
        continue
    idx = sub.groupby("local_date")["temp_c"].idxmax()
    ph = sub.loc[idx, "utc_hour"].values
    mode = int(pd.Series(ph).mode().iloc[0])
    med = int(round(np.median(ph)))
    d = ((ph - tbl + 12) % 24) - 12          # circular signed offset of true peak vs table
    late = float((d > 1).mean())             # true peak >1h after gate-open = fired pre-peak
    on = float((np.abs(d) <= 1).mean())
    diff = abs(mode - tbl)
    diff = min(diff, 24 - diff)
    rows.append((city, tbl, mode, med, diff, round(late, 2), round(on, 2), len(ph)))

rows.sort(key=lambda r: r[5], reverse=True)
print(f"MONTH={MONTH}  data {df['time_utc'].min().date()}..{df['time_utc'].max().date()}\n")
print(f'{"city":16}{"tbl":>4}{"mode":>5}{"med":>4}{"|Δ|":>4}{"P(late)":>9}{"P(±1h)":>8}{"n":>5}')
for city, tbl, mode, med, diff, late, on, n in rows:
    flag = "  <== OFF" if diff >= 2 else ("  <== late-risk" if late >= 0.30 else "")
    print(f"{city:16}{tbl:>4}{mode:>5}{med:>4}{diff:>4}{late:>9}{on:>8}{n:>5}{flag}")
