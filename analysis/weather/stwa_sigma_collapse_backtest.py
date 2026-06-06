#!/usr/bin/env python3
"""
stwa_sigma_collapse_backtest.py — READ-ONLY. Does the nowcast σ-collapse (06-03
f49f67bc) help or hurt pricer calibration? Re-prices the historical bucket
outcomes under several σ policies and compares reliability — same pricing loop as
stwa_isotonic_refit.build_historical_pairs, only the σ rule varies.

Reported per policy (RAW probs, no isotonic — we want the underlying calibration):
  Brier, ECE, rank-corr (discrimination), and the OVERCONFIDENCE measure
  (p>=0.9 buckets: mean predicted vs actual win-rate — live this is ~1.0 vs ~0.17).

Deployed today: sig = min(sig_month, max(0.25, 0.5*(center-m0))).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from math import floor
from scipy.stats import spearmanr

from analysis.weather.stwa_isotonic_refit import (
    ROOT, PARAMS, CALIB, NWP_MODEL, BETA, L, BUCKET_W,
    _bias, _phi, _sigma_month,
)
from analysis.weather.stations import STATIONS

# σ policies: name -> f(sig_month, center, m0) -> sig
POLICIES = {
    "deployed (floor .25, ratio .5)": lambda s, c, m: min(s, max(0.25, 0.5 * max(0.0, c - m))),
    "NO collapse (sig_month)":        lambda s, c, m: s,
    "floor .50":                      lambda s, c, m: min(s, max(0.50, 0.5 * max(0.0, c - m))),
    "gentler ratio .75 floor .40":    lambda s, c, m: min(s, max(0.40, 0.75 * max(0.0, c - m))),
}


def _brier(p, y): return float(np.mean((p - y) ** 2))
def _ece(p, y, nb=10):
    edges = np.linspace(0, 1, nb + 1); e = 0.0
    for i in range(nb):
        m = (p >= edges[i]) & (p < edges[i+1] if i < nb-1 else p <= edges[i+1])
        if m.sum(): e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e


def build_days():
    """Yield per-day pricing context (city, center, m0, realized, sig_month) once,
    so every σ policy re-prices the SAME days."""
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
    out = []
    for city, g in df.groupby("city"):
        cal = CALIB.get(city) or CALIB["_pooled"]
        pbias = float(cal["peak_bias"])
        st = PARAMS["stations"].get(city, {})
        peak_h = int(st.get("peak_hour_utc", 13))
        dec_h = (peak_h - L) % 24
        tz = getattr(STATIONS.get(city), "tz", "UTC") or "UTC"
        loc = g["time_utc"].dt.tz_convert(tz)
        g = g.assign(lday=loc.dt.date, lhour=loc.dt.hour)
        for _, day in g.groupby("lday"):
            if len(day) < 20:
                continue
            dec = day[day["hour_utc"] == dec_h]
            if dec.empty:
                continue
            resid_dec = float(dec["resid"].iloc[0])
            dec_lhour = int(dec["lhour"].iloc[0])
            m0 = day[day["lhour"] <= dec_lhour]["temp_c"].max()
            center = day["nwp_corr"].max() + pbias + BETA * resid_dec
            out.append((center, m0, day["temp_c"].max(), _sigma_month(city, int(day["month"].iloc[0]))))
    return out


def price(days, sig_fn):
    P, Y = [], []
    for center, m0, realized, sig_month in days:
        sig = sig_fn(sig_month, center, m0)
        lo0 = floor(center - 5)
        for k in range(11):
            blo, bhi = lo0 + k * BUCKET_W, lo0 + (k + 1) * BUCKET_W
            fhi = _phi((bhi - center) / sig) if bhi >= m0 else 0.0
            flo = _phi((blo - center) / sig) if blo >= m0 else 0.0
            p = max(0.0, fhi - flo)
            if p < 1e-4:
                continue
            P.append(p); Y.append(1.0 if blo <= realized < bhi else 0.0)
    return np.array(P), np.array(Y)


def main():
    days = build_days()
    print(f"days priced: {len(days):,}\n")
    print(f"{'policy':<34} {'n':>7} {'Brier':>7} {'ECE':>6} {'rankρ':>6}  "
          f"{'p>=.9: pred':>11} {'actual':>7} {'n>=.9':>6}")
    for name, fn in POLICIES.items():
        P, Y = price(days, fn)
        hi = P >= 0.9
        pred_hi = P[hi].mean() if hi.sum() else float('nan')
        act_hi = Y[hi].mean() if hi.sum() else float('nan')
        print(f"{name:<34} {len(P):>7,} {_brier(P,Y):>7.4f} {_ece(P,Y):>6.3f} "
              f"{spearmanr(P,Y).correlation:>6.3f}  {pred_hi:>11.3f} {act_hi:>7.3f} {int(hi.sum()):>6}")
    print("\nLower Brier/ECE = better calibrated. rankρ = discrimination (keep high).")
    print("p>=.9 actual should be ~0.9 if well-calibrated; far below = overconfident.")


if __name__ == "__main__":
    main()
