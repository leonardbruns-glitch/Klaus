"""
Does intraday observation HELP or HURT the daily-max forecast? (read-only)

The live MC centers the daily-max distribution using the intraday Kalman x_hat +
velocity (the residual observed so far, projected to the peak). The static
alternative ignores intraday obs and centers on the bias-corrected NWP peak.

Head-to-head test on 2021-2024 ASOS vs ECMWF NWP: for each (city, day) pick a
decision time L hours before the city's peak, measure the residual then
(resid_dec = T_obs−μ at decision), and ask how well it predicts the realized
daily-max error (err_static = realized_max − bias-corrected NWP peak).

Key outputs per lead time L:
  corr(resid_dec, err_static)  — if ≈0, intraday obs carry no signal for the peak
  optimal β = cov/var          — Kalman-optimal weight on the intraday residual
  std reduction with optimal β — variance the intraday term actually removes
  std with β=1 (naive persistence, ~ what an undamped tracker/velocity does)
A positive corr ⇒ intraday helps (use shrinkage β). corr≈0 or std(β=1)>std(static)
⇒ intraday is noise and the live machinery should be simplified/heavily damped.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
PARAMS = json.load(open(ROOT / "config" / "stwa_params.json"))
from analysis.weather.stations import STATIONS

NWP_MODEL = "ecmwf_ifs025"
LEADS = [2, 4, 6]   # hours before peak to take the decision-time observation


def _bias(city, month, hour):
    b = PARAMS["stations"].get(city, {}).get("bias", {})
    return float(b.get(f"{month}_{hour}", b.get(f"{month}_0", 0.0)))


def main():
    asos = pd.read_parquet(ROOT / "data" / "stwa_asos.parquet",
                           columns=["city", "time_utc", "temp_c"])
    nwp = pd.read_parquet(ROOT / "data" / "stwa_nwp.parquet",
                          columns=["city", "time_utc", "temp_nwp_c", "model"])
    nwp = nwp[nwp["model"] == NWP_MODEL].drop(columns="model")
    df = asos.merge(nwp, on=["city", "time_utc"], how="inner").dropna()
    df["month"] = df["time_utc"].dt.month
    df["hour_utc"] = df["time_utc"].dt.hour
    df["bias"] = [_bias(c, m, h) for c, m, h in zip(df["city"], df["month"], df["hour_utc"])]
    df["nwp_corr"] = df["temp_nwp_c"] + df["bias"]
    df["resid"] = df["temp_c"] - df["nwp_corr"]

    for L in LEADS:
        pr, rd = [], []           # peak-error (static), residual at decision
        for city, g in df.groupby("city"):
            st = PARAMS["stations"].get(city, {})
            peak_h = int(st.get("peak_hour_utc", 13))
            dec_h = (peak_h - L) % 24
            tz = getattr(STATIONS.get(city), "tz", "UTC") or "UTC"
            loc = g["time_utc"].dt.tz_convert(tz)
            g = g.assign(lday=loc.dt.date)
            for _, day in g.groupby("lday"):
                if len(day) < 20:
                    continue
                dec = day[day["hour_utc"] == dec_h]
                if dec.empty:
                    continue
                realized_max = day["temp_c"].max()
                nwp_peak = day["nwp_corr"].max()
                pr.append(realized_max - nwp_peak)        # err_static
                rd.append(float(dec["resid"].iloc[0]))    # residual at decision
        pr = np.array(pr); rd = np.array(rd)
        # de-mean (we already know the +0.3 peak bias; test the predictable part)
        prc = pr - pr.mean(); rdc = rd - rd.mean()
        corr = float(np.corrcoef(rdc, prc)[0, 1])
        beta = float(np.cov(rdc, prc)[0, 1] / np.var(rdc)) if np.var(rdc) > 0 else 0.0
        std_static = float(np.std(pr))
        std_opt = float(np.std(pr - (pr.mean()) - beta * rdc))      # with optimal β
        std_b1 = float(np.std(pr - rd))                              # naive β=1 persistence
        print(f"L={L}h before peak   n={len(pr):,}")
        print(f"   corr(resid_dec, peak_err)      = {corr:+.3f}   "
              f"(variance explained = {corr**2:.1%})")
        print(f"   optimal β (Kalman weight)      = {beta:+.3f}   "
              f"(1.0=full persist, 0=ignore intraday)")
        print(f"   std err  static (ignore obs)   = {std_static:.3f} °C")
        print(f"   std err  optimal-β intraday    = {std_opt:.3f} °C  "
              f"({(1-std_opt/std_static)*100:+.1f}% vs static)")
        print(f"   std err  naive β=1 (undamped)  = {std_b1:.3f} °C  "
              f"({(std_b1/std_static-1)*100:+.1f}% vs static — >0 means HURTS)\n")


if __name__ == "__main__":
    main()
