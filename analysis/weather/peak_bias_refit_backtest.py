#!/usr/bin/env python3
"""
A2 backtest — is the frozen per-city `peak_bias` scalar leaving accuracy on the
table vs a per-(city,month) refit, out-of-sample?

peak_bias (config/stwa_peak_calib.json) is a single per-city scalar fit on 2024,
added to the daily-max center (stwa_engine.py:1013):
    center = NWP_peak + peak_bias        (+ beta*x_hat, dropped here — center-only test)
Audit A2 claim: it has drifted / it's not per-month → OOS CRPS +5.2% recoverable.

This script reconstructs the daily-max residual r = realized_max − NWP_peak per
(city, local-day) from 2021-2024 ASOS×NWP, splits TRAIN=2021-2023 / TEST=2024,
and compares three center corrections on the held-out TEST year:
    SCALAR  : per-city mean(r) from TRAIN            (the frozen-equivalent)
    MONTH   : per-(city,month) mean(r) from TRAIN    (the A2 proposal)
    NONE    : no peak_bias (r uncorrected)           (floor reference)
Metrics: daily-max center MSE and Gaussian CRPS (per-city-month sigma from TRAIN).
Local day approximated by shifting time_utc by round(lon/15)h (max resolves local).

READ-ONLY.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASOS = ROOT / "data" / "stwa_asos.parquet"
NWP  = ROOT / "data" / "stwa_nwp.parquet"
PARAMS = ROOT / "config" / "stwa_params.json"

TRAIN_MAX_YEAR = 2023      # train <= this year, test == TRAIN_MAX_YEAR+1
MIN_CELL = 20              # min days per (city) or (city,month) cell to trust a fit


def crps_gauss_scalar(err: float, sigma: float) -> float:
    s = max(sigma, 1e-6)
    z = err / s
    from math import erf, exp, sqrt, pi
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    pdf = exp(-0.5 * z * z) / sqrt(2 * pi)
    return s * (z * (2 * cdf - 1) + 2 * pdf - 1.0 / sqrt(pi))


def main() -> None:
    params = json.loads(PARAMS.read_text())
    stations = params.get("stations", {})
    lon_of = {c: s.get("lon", 0.0) for c, s in stations.items()}

    asos = pd.read_parquet(ASOS, columns=["city", "time_utc", "temp_c"])
    nwp  = pd.read_parquet(NWP, columns=["city", "time_utc", "temp_nwp_c"])
    asos["time_utc"] = pd.to_datetime(asos["time_utc"], utc=True)
    nwp["time_utc"]  = pd.to_datetime(nwp["time_utc"], utc=True)

    df = asos.merge(nwp, on=["city", "time_utc"], how="inner").dropna(
        subset=["temp_c", "temp_nwp_c"])

    # approximate local day via lon/15 offset
    off_h = df["city"].map(lambda c: round(lon_of.get(c, 0.0) / 15.0)).fillna(0)
    df["local"] = df["time_utc"] + pd.to_timedelta(off_h, unit="h")
    df["lday"]  = df["local"].dt.date
    df["year"]  = df["local"].dt.year
    df["month"] = df["local"].dt.month

    # per (city, local-day): realized daily max + NWP peak
    daily = (df.groupby(["city", "lday"])
               .agg(realized_max=("temp_c", "max"),
                    nwp_peak=("temp_nwp_c", "max"),
                    year=("year", "first"),
                    month=("month", "first"))
               .reset_index())
    daily["r"] = daily["realized_max"] - daily["nwp_peak"]   # residual the bias must absorb

    train = daily[daily["year"] <= TRAIN_MAX_YEAR]
    test  = daily[daily["year"] == TRAIN_MAX_YEAR + 1].copy()
    print(f"city-days: {len(daily):,}  train(<= {TRAIN_MAX_YEAR})={len(train):,}  "
          f"test({TRAIN_MAX_YEAR+1})={len(test):,}\n")

    # ---- fit corrections on TRAIN ----
    scalar = train.groupby("city")["r"].agg(["mean", "count"])
    scalar = scalar[scalar["count"] >= MIN_CELL]["mean"].to_dict()
    sig_city = train.groupby("city")["r"].std().to_dict()

    cm = train.groupby(["city", "month"])["r"].agg(["mean", "count", "std"])
    month_mean = {k: v for k, v in cm["mean"].items() if cm.loc[k, "count"] >= MIN_CELL}
    month_std  = {k: (v if v == v else 1.2) for k, v in cm["std"].items()}

    # ---- apply on TEST ----
    def scalar_bias(row):  return scalar.get(row["city"], 0.0)
    def month_bias(row):
        return month_mean.get((row["city"], row["month"]),
                              scalar.get(row["city"], 0.0))   # fall back to per-city
    def sigma_cm(row):
        return month_std.get((row["city"], row["month"]),
                             sig_city.get(row["city"], 1.2)) or 1.2

    test["b_scalar"] = test.apply(scalar_bias, axis=1)
    test["b_month"]  = test.apply(month_bias, axis=1)
    test["sigma"]    = test.apply(sigma_cm, axis=1)

    test["e_none"]   = test["r"]                       # realized - nwp_peak (no bias)
    test["e_scalar"] = test["r"] - test["b_scalar"]
    test["e_month"]  = test["r"] - test["b_month"]

    def mse(s): return float((s ** 2).mean())
    def crps(errs, sigs): return float(np.mean([crps_gauss_scalar(e, s) for e, s in zip(errs, sigs)]))

    print("=" * 92)
    print("DAILY-MAX center accuracy on held-out TEST year (lower = better)")
    print("=" * 92)
    for arm in ("none", "scalar", "month"):
        m = mse(test[f"e_{arm}"])
        c = crps(test[f"e_{arm}"].values, test["sigma"].values)
        print(f"  {arm:<8} MSE={m:7.4f}  RMSE={math.sqrt(m):6.4f}  CRPS={c:7.4f}  "
              f"mean_err={test[f'e_{arm}'].mean():+.3f}")
    m_s, m_m = mse(test["e_scalar"]), mse(test["e_month"])
    c_s = crps(test["e_scalar"].values, test["sigma"].values)
    c_m = crps(test["e_month"].values, test["sigma"].values)
    print(f"\n  MONTH vs SCALAR (all test cities):  MSE {100*(m_m-m_s)/m_s:+.1f}%   "
          f"CRPS {100*(c_m-c_s)/c_s:+.1f}%")

    # fitted-cities only — non-US cities have no TRAIN bias (0 in BOTH arms) and
    # dilute the comparison to nothing; the real per-month effect lives here.
    fit = test[test["city"].isin(scalar.keys())].copy()
    if len(fit):
        fm_s, fm_m = mse(fit["e_scalar"]), mse(fit["e_month"])
        fc_s = crps(fit["e_scalar"].values, fit["sigma"].values)
        fc_m = crps(fit["e_month"].values, fit["sigma"].values)
        fc_n = crps(fit["e_none"].values, fit["sigma"].values)
        print(f"  fitted cities only (n={len(fit)}, {fit['city'].nunique()} cities):")
        print(f"    NONE   MSE={mse(fit['e_none']):.4f} CRPS={fc_n:.4f}")
        print(f"    SCALAR MSE={fm_s:.4f} CRPS={fc_s:.4f}  (vs none CRPS {100*(fc_s-fc_n)/fc_n:+.1f}%)")
        print(f"    MONTH  MSE={fm_m:.4f} CRPS={fc_m:.4f}  (vs scalar CRPS {100*(fc_m-fc_s)/fc_s:+.1f}%, "
              f"MSE {100*(fm_m-fm_s)/fm_s:+.1f}%)")

    # ---- temporal drift of the per-city scalar: train-mean(r) vs test-mean(r) ----
    print("\n" + "=" * 92)
    print(f"DRIFT: per-city mean residual TRAIN(<= {TRAIN_MAX_YEAR}) vs TEST({TRAIN_MAX_YEAR+1}), "
          f"cities n>={MIN_CELL}, |drift| desc")
    print("=" * 92)
    tr_mean = train.groupby("city")["r"].mean()
    te_mean = test.groupby("city")["r"].mean()
    te_n    = test.groupby("city")["r"].count()
    rows = []
    for c in tr_mean.index:
        if c in te_mean and te_n.get(c, 0) >= MIN_CELL and c in scalar:
            rows.append((c, tr_mean[c], te_mean[c], te_mean[c] - tr_mean[c], int(te_n[c])))
    rows.sort(key=lambda r: -abs(r[3]))
    print(f"  {'city':<16}{'train_r':>9}{'test_r':>9}{'drift':>9}{'n_test':>8}")
    for c, tr, te, d, n in rows[:18]:
        print(f"  {c:<16}{tr:>+9.3f}{te:>+9.3f}{d:>+9.3f}{n:>8}")
    drifts = np.array([abs(r[3]) for r in rows])
    print(f"\n  median |drift| = {np.median(drifts):.3f}°C   "
          f"mean |drift| = {drifts.mean():.3f}°C   over {len(rows)} cities")


if __name__ == "__main__":
    main()
