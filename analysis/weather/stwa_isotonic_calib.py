"""
Isotonic recalibration of the PA-shrunk pricer + calibration measurement (read-only).

Replays PA-shrunk on 2024 ASOS vs ECMWF at a realistic decision time (L h before
the city's peak, running-max known only up to that point), over 1°C buckets, to
collect (predicted bucket prob p_ps, did_bucket_win) pairs. Then:
  - measures raw calibration (reliability deciles, Brier, log-loss, ECE),
  - fits a monotone isotonic map g: p_ps → calibrated prob,
  - measures calibration AFTER g,
  - writes config/stwa_isotonic.json (knot points) for the engine to apply.

This is the gate machinery for re-enabling YES: YES re-enables ONLY if the
recalibrated reliability is monotone with positive rank-corr (and ideally g≈identity,
meaning PA-shrunk was already calibrated).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from math import erf, sqrt
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).parent.parent.parent
PARAMS = json.load(open(ROOT / "config" / "stwa_params.json"))
CALIB = json.load(open(ROOT / "config" / "stwa_peak_calib.json"))
from analysis.weather.stations import STATIONS

NWP_MODEL = "ecmwf_ifs025"
BETA = float(CALIB.get("_beta", 0.30))
L = 4                      # decision lead: hours before peak
BUCKET_W = 1.0


def _bias(city, month, hour):
    b = PARAMS["stations"].get(city, {}).get("bias", {})
    return float(b.get(f"{month}_{hour}", b.get(f"{month}_0", 0.0)))


def _phi(z):
    return 0.5 * (1.0 + erf(z / sqrt(2)))


def _ece(p, y, nb=10):
    p = np.asarray(p); y = np.asarray(y)
    edges = np.linspace(0, 1, nb + 1)
    e = 0.0
    for i in range(nb):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < nb - 1 else p <= edges[i + 1])
        if m.sum():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e


def _brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def _logloss(p, y):
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6); y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


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

    P, Y = [], []
    for city, g in df.groupby("city"):
        cal = CALIB.get(city) or CALIB["_pooled"]
        pbias, sigma = float(cal["peak_bias"]), float(cal["sigma"])
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
            m0 = day[day["lhour"] <= dec_lhour]["temp_c"].max()      # running max so far
            nwp_peak = day["nwp_corr"].max()
            realized = day["temp_c"].max()
            center = nwp_peak + pbias + BETA * resid_dec
            lo0 = np.floor(center - 5)
            for k in range(11):
                blo, bhi = lo0 + k * BUCKET_W, lo0 + (k + 1) * BUCKET_W
                fhi = _phi((bhi - center) / sigma) if bhi >= m0 else 0.0
                flo = _phi((blo - center) / sigma) if blo >= m0 else 0.0
                p = max(0.0, fhi - flo)
                if p < 1e-4:
                    continue
                P.append(p); Y.append(1.0 if blo <= realized < bhi else 0.0)

    P = np.array(P); Y = np.array(Y)
    print(f"pairs: {len(P):,}  base rate (mean win): {Y.mean():.3f}  L={L}h\n")

    # raw reliability
    print("RAW p_ps reliability (decile pred vs actual):")
    edges = np.linspace(0, 1, 11)
    for i in range(10):
        m = (P >= edges[i]) & (P < edges[i + 1]) if i < 9 else (P >= edges[i]) & (P <= edges[i + 1])
        if m.sum() > 30:
            print(f"   [{edges[i]:.1f},{edges[i+1]:.1f})  n={m.sum():>6}  pred={P[m].mean():.3f}  actual={Y[m].mean():.3f}  diff={Y[m].mean()-P[m].mean():+.3f}")

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(P, Y)
    Pc = iso.predict(P)
    print(f"\n  metric          RAW      RECALIB")
    print(f"  Brier        {_brier(P,Y):.4f}   {_brier(Pc,Y):.4f}")
    print(f"  log-loss     {_logloss(P,Y):.4f}   {_logloss(Pc,Y):.4f}")
    print(f"  ECE          {_ece(P,Y):.4f}   {_ece(Pc,Y):.4f}")
    from scipy.stats import spearmanr
    print(f"  rank-corr(p,win) raw = {spearmanr(P,Y).correlation:+.3f}  (want >0)")

    # isotonic map knots on a grid
    grid = np.linspace(0, 1, 21)
    gmap = iso.predict(grid)
    out = {"grid": [round(float(x), 3) for x in grid],
           "calibrated": [round(float(x), 4) for x in gmap],
           "fit": {"n": int(len(P)), "L_hours": L, "beta": BETA,
                   "brier_raw": round(_brier(P, Y), 4), "brier_cal": round(_brier(Pc, Y), 4),
                   "near_identity_maxdev": round(float(np.max(np.abs(gmap - grid))), 3)}}
    (ROOT / "config" / "stwa_isotonic.json").write_text(json.dumps(out, indent=2))
    print(f"\n  isotonic map written to config/stwa_isotonic.json")
    print(f"  max |g(p)-p| over grid = {out['fit']['near_identity_maxdev']:.3f}  "
          f"(≈0 ⇒ PA-shrunk already calibrated, g≈identity)")
    print("  g(p) at p=0.1/0.2/0.3/0.5:",
          [round(float(iso.predict([x])[0]), 3) for x in (0.1, 0.2, 0.3, 0.5)])


if __name__ == "__main__":
    main()
