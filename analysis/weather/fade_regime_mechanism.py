#!/usr/bin/env python3
"""P1 Prong A — does the diurnal PEAK CURVATURE (the driver of the hourly-sampling
fade gap) partition by synoptic regime? READ-ONLY, large-n from the ASOS parquet.

Sampling theory: the fade edge is the gap between the true continuous daily max and
the hourly-sampled max. For a parabolic peak T(t)=T*-a(t-t*)^2 sampled at interval
Δt, E[gap] ∝ a (the peak curvature). So a regime that SHARPENS the peak (bigger a)
=> bigger sampling gap => fatter fade; a regime that FLATTENS it => thin/false fade.

Curvature proxy from hourly data:  curv = 2*T_peak - T_{peak-1h} - T_{peak+1h}  (°C,
>=0 since peak is the daily argmax). Partition by sky cover (sky_rank 0=clear..4=ovc)
and dew depression (T-Td; large=dry) AT the peak. Hypothesis: clear+dry => large curv
(sharp peak => big fade); cloudy+humid => small curv (flat peak => suppress fade).

Run: python3 analysis/weather/fade_regime_mechanism.py
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "analysis/weather")
from stations import STATIONS

ASOS = "data/stwa_asos.parquet"


def build():
    df = pd.read_parquet(ASOS, columns=["city", "time_utc", "temp_c", "dew_c", "sky_rank"])
    rows = []
    for city, g in df.groupby("city", sort=False):
        st = STATIONS.get(city)
        if st is None or not st.tz:
            continue
        loc = g["time_utc"].dt.tz_convert(st.tz)
        d = pd.DataFrame({"ldate": loc.dt.date.values, "lhour": loc.dt.hour.values,
                          "T": g["temp_c"].values, "Td": g["dew_c"].values,
                          "sky": g["sky_rank"].values})
        d = d.groupby(["ldate", "lhour"], as_index=False).agg(
            T=("T", "max"), Td=("Td", "median"), sky=("sky", "median"))
        for ldate, day in d.groupby("ldate", sort=False):
            day = day.set_index("lhour").reindex(range(24))
            T = day["T"]
            if T.notna().sum() < 18:
                continue
            ph = int(np.nanargmax(np.where(np.isnan(T.values), -1e9, T.values)))
            if ph < 10 or ph > 19:                 # daytime peak only
                continue
            tp, tprev, tnext = T.get(ph), T.get(ph - 1), T.get(ph + 1)
            if pd.isna(tp) or pd.isna(tprev) or pd.isna(tnext):
                continue
            curv = float(2 * tp - tprev - tnext)   # °C, >=0; bigger = sharper peak
            sky = day["sky"].get(ph)
            td = day["Td"].get(ph)
            depr = float(tp - td) if pd.notna(td) else np.nan
            amp = float(tp - np.nanmin(T.values))  # diurnal amplitude (control)
            rows.append((city, ldate.month, curv, float(sky) if pd.notna(sky) else np.nan,
                         depr, amp))
    return pd.DataFrame(rows, columns=["city", "month", "curv", "sky", "depr", "amp"])


def tier(df):
    df = df.dropna(subset=["sky", "depr"]).copy()
    df["sky_t"] = pd.cut(df.sky, [-1, 1.0, 2.0, 4.1], labels=["clear(0-1)", "partly(2)", "cloudy(3-4)"])
    df["dew_t"] = pd.cut(df.depr, [-99, 4, 8, 99], labels=["humid(<4)", "mod(4-8)", "dry(>8)"])
    return df


def main():
    print("building per-city-day peaks from", ASOS, "...", flush=True)
    df = tier(build())
    print(f"city-days: {len(df):,}   cities: {df.city.nunique()}\n")

    print("=== mean PEAK CURVATURE (°C) by regime  [bigger = sharper peak = bigger fade gap] ===")
    piv = df.pivot_table("curv", "dew_t", "sky_t", aggfunc="mean", observed=True)
    cnt = df.pivot_table("curv", "dew_t", "sky_t", aggfunc="count", observed=True)
    print(piv.round(3).to_string())
    print("\n cell counts:"); print(cnt.astype(int).to_string())

    clear_dry = df[(df.sky_t == "clear(0-1)") & (df.dew_t == "dry(>8)")].curv
    cloudy_hum = df[(df.sky_t == "cloudy(3-4)") & (df.dew_t == "humid(<4)")].curv
    print(f"\n clear+dry  curv mean={clear_dry.mean():.3f}  n={len(clear_dry):,}")
    print(f" cloudy+humid curv mean={cloudy_hum.mean():.3f}  n={len(cloudy_hum):,}")
    if len(cloudy_hum) > 30 and cloudy_hum.mean() > 0:
        print(f" => SHARPNESS RATIO clear-dry / cloudy-humid = {clear_dry.mean()/cloudy_hum.mean():.2f}x")
        print(f"    (sampling gap ∝ curvature => fade EV ~{clear_dry.mean()/cloudy_hum.mean():.2f}x larger on clear-dry days)")

    # marginal effects + a simple control for amplitude (sharp != just big swing)
    print("\n=== marginals ===")
    print(" by sky:   ", df.groupby("sky_t", observed=True).curv.mean().round(3).to_dict())
    print(" by dew:   ", df.groupby("dew_t", observed=True).curv.mean().round(3).to_dict())
    print(" corr(curv, sky_rank) =", round(df.curv.corr(df.sky), 3),
          " (expect negative: cloudier=flatter)")
    print(" corr(curv, dew_depr) =", round(df.curv.corr(df.depr), 3),
          " (expect positive: drier=sharper)")
    # partial: within amplitude deciles, does sky still matter? (isolate shape from size)
    df["amp_d"] = pd.qcut(df.amp, 5, labels=False, duplicates="drop")
    within = df.groupby("amp_d", observed=True).apply(
        lambda s: s.curv.corr(s.sky), include_groups=False)
    print(" corr(curv,sky) within amplitude quintiles (shape, not size):",
          [round(x, 3) for x in within.values])


if __name__ == "__main__":
    main()
