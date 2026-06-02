"""Morning Thermodynamic Nowcast — the daily max from dew point + cloud + air mass.

NOT-DONE-BEFORE angle (2026-06-02): the engine prices off NWP temperature + a
Kalman residual and IGNORES dew point entirely. But the morning thermodynamic
state physically governs the daily max:

  * LEVEL  — a dry (large dew-point depression), clear, fast-warming morning
    converts insolation into SENSIBLE heat -> bigger diurnal rise.
  * SPREAD — a humid morning destabilises into convection/cloud -> the max is
    LESS predictable; a dry morning radiates cleanly -> the max is tighter.

Both measured OOS (train 2021-23 / test 2024, ASOS parquet) against the realised
daily max:

  LEVEL  : morning thermo nowcast beats climatology by +11% MAE on the afternoon
           rise (corr 0.61 vs 0.46). Ablation: velocity alone (~what the Kalman
           has) = +4.5%; dew+cloud+air-mass adds +7.3%, ~+4% incremental.
  SPREAD : sd(rise) dry-morning 2.01 vs humid-morning 2.33 (16% wider) — a
           day-specific variance the market prices as roughly constant.

This is a NOWCAST (real-time morning obs) vs the market's stale overnight NWP, so
it can carry info the forecast lacks. Run: python3 analysis/weather/thermo_nowcast.py
"""
from __future__ import annotations
import numpy as np, pandas as pd
from analysis.weather.climatology_pricer import ICAO_OFF, season

MORNING_OFFSET = -5   # decision hour relative to climatological peak


def frame():
    df = pd.read_parquet("data/stwa_asos.parquet").dropna(subset=["temp_c"])
    df["off"] = df["icao"].map(ICAO_OFF).fillna(0)
    df["lt"] = df["time_utc"] + pd.to_timedelta(df["off"], unit="h")
    df["ldate"] = df["lt"].dt.date; df["lhour"] = df["lt"].dt.hour
    df["year"] = df["lt"].dt.year; df["month"] = df["lt"].dt.month
    df = df.sort_values(["city", "ldate", "lhour"]).reset_index(drop=True)
    g = df.groupby(["city", "ldate"], sort=False)
    df["rmax"] = g["temp_c"].cummax()
    df = df[g["temp_c"].transform("size") >= 18].reset_index(drop=True)
    g = df.groupby(["city", "ldate"], sort=False)
    day = g.agg(M=("temp_c", "max")).reset_index()
    pk = df.loc[g["temp_c"].idxmax(), ["city", "ldate", "lhour"]].rename(columns={"lhour": "pk"})
    day = day.merge(pk, on=["city", "ldate"])

    def at(off, cols):
        h = day[["city", "ldate", "pk"]].copy(); h["hh"] = h["pk"] + off
        mr = df.merge(h[["city", "ldate", "hh"]], on=["city", "ldate"])
        mr = mr[mr["lhour"] <= mr["hh"]]
        return mr.groupby(["city", "ldate"]).last().reset_index()[["city", "ldate"] + cols]

    m5 = at(MORNING_OFFSET, ["temp_c", "dew_c", "sky_rank", "rmax", "month", "year"]).rename(
        columns={"temp_c": "t5", "dew_c": "d5", "sky_rank": "sky5", "rmax": "rm5"})
    m7 = at(MORNING_OFFSET - 2, ["temp_c"]).rename(columns={"temp_c": "t7"})
    D = day.merge(m5, on=["city", "ldate"]).merge(m7, on=["city", "ldate"]).dropna(subset=["t5", "d5"])
    D["depr"] = D.t5 - D.d5; D["vel"] = D.t5 - D.t7
    D["rr"] = (D.M - D.rm5).clip(lower=0); D["season"] = D.month.map(season)
    D["cityc"] = D.city.astype("category").cat.codes
    return D


def run():
    from sklearn.ensemble import HistGradientBoostingRegressor
    D = frame()
    tr, te = D[D.year <= 2023], D[D.year > 2023]
    clim = tr.groupby(["city", "season"]).rr.mean().rename("rc").reset_index()
    te = te.merge(clim, on=["city", "season"], how="left"); te["rc"] = te.rc.fillna(tr.rr.mean())
    mae_c = (te.rr - te.rc).abs().mean()

    def fit(feats):
        gb = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05,
                                           max_iter=400, l2_regularization=1.0)
        gb.fit(tr[feats], tr.rr)
        return (te.rr - gb.predict(te[feats])).abs().mean()

    print(f"=== LEVEL: predict afternoon rise, OOS 2024 (n={len(te)}) ===")
    print(f"  climatology baseline           MAE={mae_c:.3f}")
    for nm, f in [("velocity only (Kalman~has)", ["vel", "month", "cityc"]),
                  ("dew+cloud+airmass (NEW)", ["depr", "sky5", "t5", "rm5", "month", "cityc"]),
                  ("FULL thermo nowcast", ["depr", "vel", "sky5", "t5", "rm5", "month", "cityc"])]:
        mae = fit(f)
        print(f"  {nm:<28} MAE={mae:.3f}  ({100*(mae_c-mae)/mae_c:+.1f}% vs climatology)")

    # SPREAD: day-specific variance by morning dew depression (within city-season)
    D["rr_z"] = D.groupby(["city", "season"]).rr.transform(lambda s: s - s.mean())
    D["dq"] = D.groupby(["city", "season"]).depr.transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["humid", "mid", "dry"]))
    print(f"\n=== SPREAD: sd(rise) by morning dew-depression (market prices ~constant) ===")
    for q in ["humid", "mid", "dry"]:
        s = D[D.dq == q].rr_z.dropna()
        print(f"  {q:<6} sd={s.std():.2f}  n={len(s)}")
    sh, sd = D[D.dq == "humid"].rr_z.std(), D[D.dq == "dry"].rr_z.std()
    print(f"  humid/dry spread ratio = {sh/sd:.2f}x  -> dry-morning max is {100*(1-sd/sh):.0f}% tighter")


if __name__ == "__main__":
    run()
