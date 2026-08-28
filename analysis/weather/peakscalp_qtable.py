#!/usr/bin/env python3
"""Generate the PEAKSCALP q-table: P(final daily max climbs <= d above the
current running max | city, month, local hour), from 4yr oracle-grade hourly
obs (data/stwa_asos.parquet). This is the model-free win probability for
buying YES on the bucket containing the official running max ("winner-bucket
convergence"), the YES-side twin of the P5 temporal lock.

Output: config/peakscalp_q.json
  { city: { "m<month>": { "h<hour>": { "d04": q, "d06": q, "d10": q, "n": n } } } }
d = headroom from running max to bucket ceiling, °C. Live lookup uses the
largest d <= actual headroom (conservative). Cells with n < 60 are omitted —
the live gate must treat missing cells as q=0 (no trade).
"""
import json, sys
import pandas as pd

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import ICAO_UTC_OFFSET_H

DS = {"d02": 0.2, "d04": 0.4, "d06": 0.6, "d10": 1.0}
MIN_N = 60

def main():
    df = pd.read_parquet("/root/Klaus/data/stwa_asos.parquet")
    df = df.dropna(subset=["temp_c"])
    off = df["icao"].map(lambda i: ICAO_UTC_OFFSET_H.get(i, 0))
    local = df["time_utc"] + pd.to_timedelta(off, unit="h")
    df["local_date"] = local.dt.date
    df["local_hour"] = local.dt.hour
    df["month"] = local.dt.month
    df = df.sort_values(["city", "local_date", "local_hour"])
    g = df.groupby(["city", "local_date"], sort=False)
    df["run_max"] = g["temp_c"].cummax()
    df = df.merge(g["temp_c"].max().rename("final_max"), on=["city", "local_date"])
    df = df.merge(g.size().rename("n_obs"), on=["city", "local_date"])
    df = df[df["n_obs"] >= 20]
    df["gap"] = df["final_max"] - df["run_max"]
    sub = df[df["local_hour"].between(10, 23)]

    out = {}
    grp = sub.groupby(["city", "month", "local_hour"])
    for (city, month, hour), s in grp:
        n = len(s)
        if n < MIN_N:
            continue
        cell = {k: round(float((s["gap"] <= d).mean()), 4) for k, d in DS.items()}
        cell["n"] = int(n)
        out.setdefault(city, {}).setdefault(f"m{int(month)}", {})[f"h{int(hour)}"] = cell

    with open("/root/Klaus/config/peakscalp_q.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    ncells = sum(len(h) for c in out.values() for h in c.values())
    print(f"wrote config/peakscalp_q.json: {len(out)} cities, {ncells} (month,hour) cells")

if __name__ == "__main__":
    main()
