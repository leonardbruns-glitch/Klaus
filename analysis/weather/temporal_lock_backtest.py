#!/usr/bin/env python3
"""Temporal-lock (P5) violation-rate backtest.

Hypothesis: late in the local day, buckets ABOVE the current running max become
physically unreachable — the diurnal peak has passed and temperature decays.
If P(final_max - running_max(t) > delta) is ~0 for some (t, delta) frontier,
then "bucket_lo_padded > running_max(t) + delta" is a tradeable NO lock of the
same family as the running-max-exceeded lockout, but on the OTHER side of the
ladder, multiplying candidate count.

Data: data/stwa_asos.parquet — 4yr (2021-2024) hourly obs, 51 cities. Hourly is
exactly the oracle resolution for METAR cities (WU daily max = max of hourly
METARs; SPECIs missing here = slight understatement of violations, noted).

Output:
  - pooled violation surface: rows = local hour, cols = delta margin
  - per-city violation at the candidate rule
  - per-month pooling at the candidate rule (seasonality check)
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import ICAO_UTC_OFFSET_H  # single source of truth

HOURS = list(range(12, 24))           # local hours to evaluate
DELTAS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
CAND_HOUR = 18                        # candidate rule defaults (refined below)
CAND_DELTA = 1.0

def main():
    df = pd.read_parquet("/root/Klaus/data/stwa_asos.parquet")
    df = df.dropna(subset=["temp_c"])
    off = df["icao"].map(lambda i: ICAO_UTC_OFFSET_H.get(i, 0))
    local = df["time_utc"] + pd.to_timedelta(off, unit="h")
    df["local_date"] = local.dt.date
    df["local_hour"] = local.dt.hour
    df["month"] = local.dt.month

    # per (city, local_date): cumulative running max by hour + final max
    df = df.sort_values(["city", "local_date", "local_hour"])
    g = df.groupby(["city", "local_date"], sort=False)
    df["run_max"] = g["temp_c"].cummax()
    day_final = g["temp_c"].max().rename("final_max")
    day_n = g.size().rename("n_obs")
    df = df.merge(day_final, on=["city", "local_date"])
    df = df.merge(day_n, on=["city", "local_date"])
    df = df[df["n_obs"] >= 20]                     # complete-ish days only
    df["gap_to_come"] = df["final_max"] - df["run_max"]

    sub = df[df["local_hour"].isin(HOURS)]

    print(f"days evaluated: {df.groupby(['city','local_date']).ngroups}, "
          f"(city,day,hour) points: {len(sub)}")

    print("\n=== POOLED violation rate %  P(gap_to_come > delta) ===")
    print("hour | " + " | ".join(f"d={d}" for d in DELTAS))
    for h in HOURS:
        s = sub[sub["local_hour"] == h]
        row = [f"{(s['gap_to_come'] > d).mean()*100:6.3f}" for d in DELTAS]
        print(f"  {h:02d} | " + " | ".join(row) + f"   n={len(s)}")

    # candidate rules: for each hour, smallest delta with pooled violation <=0.2%
    print("\n=== frontier: min delta with pooled violation <= 0.2% / 0.5% ===")
    for h in HOURS:
        s = sub[sub["local_hour"] == h]
        f02 = next((d for d in DELTAS if (s["gap_to_come"] > d).mean() <= 0.002), None)
        f05 = next((d for d in DELTAS if (s["gap_to_come"] > d).mean() <= 0.005), None)
        print(f"  hour {h:02d}: <=0.2% at delta={f02}  <=0.5% at delta={f05}")

    # per-city at the candidate rule
    print(f"\n=== per-city violation % at hour>={CAND_HOUR}, delta={CAND_DELTA} ===")
    s = sub[sub["local_hour"] >= CAND_HOUR]
    per = (s.assign(viol=s["gap_to_come"] > CAND_DELTA)
             .groupby("city")["viol"].agg(["mean", "size"]))
    per["mean"] *= 100
    per = per.sort_values("mean", ascending=False)
    print(per.head(15).to_string(float_format="%.3f"))
    print("  ... cities with 0 violations:",
          int((per["mean"] == 0).sum()), "/", len(per))

    # per-month at the candidate rule
    print(f"\n=== per-month violation % at hour>={CAND_HOUR}, delta={CAND_DELTA} ===")
    pm = (s.assign(viol=s["gap_to_come"] > CAND_DELTA)
            .groupby("month")["viol"].agg(["mean", "size"]))
    pm["mean"] *= 100
    print(pm.to_string(float_format="%.3f"))

if __name__ == "__main__":
    main()
