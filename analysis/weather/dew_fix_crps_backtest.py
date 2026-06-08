#!/usr/bin/env python3
"""
A1 dew-fix backtest — quantify the center-MSE recovery from correcting the
humidity-correction wiring.

CONFIRMED BUG (stwa_engine.py:665):
    nwp_dew = self._nwp_cache.get(city, {}).get(hour_utc)   # <- holds AIR TEMP
    mu_corrected += alpha * (dew_c - nwp_dew)               # applied vs air temp
The alpha coefficient (stwa_fit_params.py:192-201) was fit on the regressor
    x = (dew_c - dew_nwp_c)                                 # obs dew - NWP DEW
but the engine evaluates it on (dew_c - temp_nwp_c). The two regressors differ
by the forecast dewpoint depression (several deg C), injecting a systematic
wrong offset into the center the whole NO path sizes off.

This script reconstructs the engine center three ways and scores each vs the
realized observation, both on the peak window (what the daily-max center is
built from) and on the realized daily max itself:
    A0  no dew term            center = nwp + bias
    BUG alpha*(dew - airtemp)  center = nwp + bias + alpha*(dew_c - temp_nwp_c)
    FIX alpha*(dew - dew_nwp)  center = nwp + bias + alpha*(dew_c - dew_nwp_c)
alpha + bias are the LIVE fitted values from config/stwa_params.json.

READ-ONLY. No live state touched.
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

PEAK_WIN = 2          # +/- hours around peak_hour_utc for the "peak window" metric
MIN_N    = 100        # n>=100 gate per city before we trust a per-city verdict


def _hour_bin(h: int) -> str:
    # must match analytics/stwa_fit_params.py::_hour_bin
    if 5 <= h < 11:  return "morning"
    if 11 <= h < 17: return "midday"
    if 17 <= h < 23: return "evening"
    return "night"


def crps_gauss(mu_err: np.ndarray, sigma: float) -> np.ndarray:
    """Closed-form Gaussian CRPS for a forecast N(center, sigma) and obs;
    mu_err = obs - center.  CRPS(z) with z = mu_err/sigma."""
    s = max(sigma, 1e-6)
    z = mu_err / s
    from scipy.stats import norm
    return s * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1.0 / math.sqrt(math.pi))


def main() -> None:
    params = json.loads(PARAMS.read_text())
    stations = params.get("stations", {})

    asos = pd.read_parquet(ASOS)
    nwp  = pd.read_parquet(NWP)
    asos["time_utc"] = pd.to_datetime(asos["time_utc"], utc=True)
    nwp["time_utc"]  = pd.to_datetime(nwp["time_utc"],  utc=True)

    df = asos.merge(nwp[["city", "time_utc", "temp_nwp_c", "dew_nwp_c"]],
                    on=["city", "time_utc"], how="inner")
    df["hour"]  = df["time_utc"].dt.hour
    df["month"] = df["time_utc"].dt.month
    df["date"]  = df["time_utc"].dt.date

    # coverage: the fix is meaningless where dew_nwp_c is null (ifs025 non-US leg)
    n_total = len(df)
    df = df.dropna(subset=["temp_c", "dew_c", "temp_nwp_c", "dew_nwp_c"])
    print(f"rows: {n_total:,} merged -> {len(df):,} with full dew coverage "
          f"({100*len(df)/max(n_total,1):.0f}%)\n")

    # ---- per-row alpha + static bias from live params ----
    def alpha_of(row):
        s = stations.get(row["city"], {})
        return s.get("alpha_humidity", {}).get(str(int(row["month"])), 0.0)

    def bias_of(row):
        s = stations.get(row["city"], {})
        b = s.get("bias", {})
        # bias keyed "{month}_{hour}" in fit script (m=1..12, h=0..23)
        return b.get(f"{int(row['month'])}_{int(row['hour'])}", 0.0)

    df["alpha"] = df.apply(alpha_of, axis=1)
    df["bias"]  = df.apply(bias_of, axis=1)

    base = df["temp_nwp_c"] + df["bias"]
    df["c_a0"]  = base
    df["c_bug"] = base + df["alpha"] * (df["dew_c"] - df["temp_nwp_c"])
    df["c_fix"] = base + df["alpha"] * (df["dew_c"] - df["dew_nwp_c"])

    for arm in ("a0", "bug", "fix"):
        df[f"e_{arm}"] = df["temp_c"] - df[f"c_{arm}"]

    # only rows where the dew term is actually active (alpha != 0) move the needle;
    # report both the full set and the active subset.
    active = df[df["alpha"].abs() > 1e-6].copy()

    def mse(s):  return float((s ** 2).mean())

    def report(d, label):
        if len(d) == 0:
            print(f"  {label}: n=0"); return
        m0, mb, mf = mse(d["e_a0"]), mse(d["e_bug"]), mse(d["e_fix"])
        print(f"  {label:<28} n={len(d):>6}  "
              f"MSE  no-dew={m0:6.3f}  BUG={mb:6.3f}  FIX={mf:6.3f}   "
              f"| RMSE {math.sqrt(m0):.3f}/{math.sqrt(mb):.3f}/{math.sqrt(mf):.3f}")
        print(f"  {'':28}        bug vs no-dew: {100*(mb-m0)/m0:+5.1f}%   "
              f"fix vs no-dew: {100*(mf-m0)/m0:+5.1f}%   "
              f"fix vs BUG: {100*(mf-mb)/mb:+5.1f}%")

    print("=" * 100)
    print("1) HOURLY CENTER MSE vs observed temp  (all hours)")
    print("=" * 100)
    report(df,     "all rows")
    report(active, "dew-active rows (alpha!=0)")

    # ---- peak window: rows within +/-PEAK_WIN of city peak hour ----
    def near_peak(row):
        s = stations.get(row["city"], {})
        ph = s.get("peak_hour_utc", 14)
        d = abs(((int(row["hour"]) - ph + 12) % 24) - 12)
        return d <= PEAK_WIN
    peak = active[active.apply(near_peak, axis=1)].copy()

    print("\n" + "=" * 100)
    print(f"2) PEAK-WINDOW CENTER MSE (+/-{PEAK_WIN}h of peak, dew-active)  "
          "<- this feeds the daily-max center")
    print("=" * 100)
    report(peak, "peak-window")

    # ---- daily-max center: per (city,date) take peak-hour row, vs realized daily max ----
    print("\n" + "=" * 100)
    print("3) DAILY-MAX center error (peak-hour center vs realized daily max temp)")
    print("=" * 100)
    rows = []
    for (city, date), g in active.groupby(["city", "date"]):
        s = stations.get(city, {})
        ph = s.get("peak_hour_utc", 14)
        g = g.assign(_pd=(g["hour"] - ph).abs())
        pk = g.sort_values("_pd").iloc[0]
        dmax = g["temp_c"].max()
        rows.append({"city": city,
                     "e_a0":  dmax - pk["c_a0"],
                     "e_bug": dmax - pk["c_bug"],
                     "e_fix": dmax - pk["c_fix"]})
    dm = pd.DataFrame(rows)
    report(dm, "daily-max (all cities)")

    # ---- per-city breakdown (n>=MIN_N), sorted by how much the bug hurts ----
    print("\n" + "=" * 100)
    print(f"4) PER-CITY peak-window (n>={MIN_N}), sorted by bug damage (BUG-FIX MSE)")
    print("=" * 100)
    out = []
    for city, g in peak.groupby("city"):
        if len(g) < MIN_N:
            continue
        mb, mf, m0 = mse(g["e_bug"]), mse(g["e_fix"]), mse(g["e_a0"])
        out.append((city, len(g), m0, mb, mf, mb - mf))
    out.sort(key=lambda r: -r[5])
    print(f"  {'city':<16}{'n':>6}  {'no-dew':>8}{'BUG':>8}{'FIX':>8}  {'BUG-FIX':>9}")
    for city, n, m0, mb, mf, d in out:
        print(f"  {city:<16}{n:>6}  {m0:>8.3f}{mb:>8.3f}{mf:>8.3f}  {d:>+9.3f}")

    # ---- CRPS (Gaussian, per-city-month sigma) on peak window ----
    try:
        def sigma_of(row):
            s = stations.get(row["city"], {})
            sig = s.get("sigma", {})
            # sigma keyed by hour-bin index str(h//6), 0..3
            return float(sig.get(str(int(row["hour"]) // 6), 1.05)) if isinstance(sig, dict) else float(sig or 1.05)
        peak["sigma"] = peak.apply(sigma_of, axis=1)
        for arm in ("a0", "bug", "fix"):
            peak[f"crps_{arm}"] = crps_gauss(peak[f"e_{arm}"].values, 1.0) * 0  # placeholder
        # vectorized per-row sigma
        for arm in ("a0", "bug", "fix"):
            peak[f"crps_{arm}"] = [crps_gauss(np.array([e]), s)[0]
                                   for e, s in zip(peak[f"e_{arm}"].values, peak["sigma"].values)]
        print("\n" + "=" * 100)
        print("5) PEAK-WINDOW Gaussian CRPS (per-city-month sigma)")
        print("=" * 100)
        c0, cb, cf = peak["crps_a0"].mean(), peak["crps_bug"].mean(), peak["crps_fix"].mean()
        print(f"  CRPS  no-dew={c0:.4f}  BUG={cb:.4f}  FIX={cf:.4f}   "
              f"| fix vs bug: {100*(cf-cb)/cb:+.1f}%   fix vs no-dew: {100*(cf-c0)/c0:+.1f}%")
    except Exception as e:
        print(f"\n(CRPS skipped: {e})")


if __name__ == "__main__":
    main()
