#!/usr/bin/env python3
"""
stwa_isotonic_refit.py — refit the isotonic recal map g AGAINST THE DEPLOYED PRICER. READ-ONLY
except it writes a CANDIDATE file (never the live config).

WHY: config/stwa_isotonic.json (live) was fit by stwa_isotonic_calib.py using the OLD flat
cal["sigma"]. On 2026-06-03 the engine switched to per-(city,month) sigma_monthly + nowcast
σ-collapse (stwa_engine._peak_sigma_for + sig_eff). The raw PA-shrunk bucket probs the engine
now produces have a DIFFERENT distribution, so the old aggressive g (g(0.95)≈0.39) would
double-correct on top of the already-calibrated σ. This re-fits g on raw probs generated with
the EXACT deployed σ path, so g and the pricer are consistent again.

Mirrors stwa_isotonic_calib.py exactly EXCEPT the σ used to price each bucket:
  sigma_month = sigma_monthly[city][month]   (falls back _pooled, then flat sigma)
  sig_eff     = min(sigma_month, max(0.25, 0.5*(center - m0)))   # nowcast collapse, as live
Output: config/stwa_isotonic_candidate.json + a side-by-side vs the live map. Deploy is a
deliberate, separate Tier-2 copy step — this script does NOT touch the live config.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from math import erf, sqrt
from sklearn.isotonic import IsotonicRegression
from scipy.stats import spearmanr

ROOT = Path(__file__).parent.parent.parent
PARAMS = json.load(open(ROOT / "config" / "stwa_params.json"))
CALIB = json.load(open(ROOT / "config" / "stwa_peak_calib.json"))
from analysis.weather.stations import STATIONS

NWP_MODEL = "ecmwf_ifs025"
BETA = float(CALIB.get("_beta", 0.30))
L = 4
BUCKET_W = 1.0
NOWCAST_REMAIN_RATIO = 0.5     # matches stwa_engine
NOWCAST_SIGMA_FLOOR = 0.25


def _bias(city, month, hour):
    b = PARAMS["stations"].get(city, {}).get("bias", {})
    return float(b.get(f"{month}_{hour}", b.get(f"{month}_0", 0.0)))


def _phi(z):
    return 0.5 * (1.0 + erf(z / sqrt(2)))


def _brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def _logloss(p, y):
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6); y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _ece(p, y, nb=10):
    p = np.asarray(p); y = np.asarray(y); edges = np.linspace(0, 1, nb + 1); e = 0.0
    for i in range(nb):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < nb - 1 else p <= edges[i + 1])
        if m.sum():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e


def _sigma_month(city, month):
    cal = CALIB.get(city) or CALIB["_pooled"]
    for src in (cal, CALIB.get("_pooled", {})):
        sm = src.get("sigma_monthly") if isinstance(src, dict) else None
        if isinstance(sm, dict):
            v = sm.get(str(month)) or sm.get(month)
            if v:
                return float(v)
    return float(cal.get("sigma", 1.1))


def build_historical_pairs():
    """Return (P, Y) raw-prob/outcome pairs from the historical parquet under the
    DEPLOYED σ path. Extracted so the live-refit job can pool these as a prior
    over the sparse regions where live 2026 data is still thin."""
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
            nwp_peak = day["nwp_corr"].max()
            realized = day["temp_c"].max()
            month = int(day["month"].iloc[0])
            center = nwp_peak + pbias + BETA * resid_dec
            # ── DEPLOYED σ path: per-(city,month) + nowcast collapse ──
            sig_month = _sigma_month(city, month)
            sig = min(sig_month, max(NOWCAST_SIGMA_FLOOR,
                                     NOWCAST_REMAIN_RATIO * max(0.0, center - m0)))
            lo0 = np.floor(center - 5)
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
    P, Y = build_historical_pairs()
    print(f"=== ISOTONIC REFIT vs DEPLOYED σ (per-(city,month)+nowcast) ===")
    print(f"pairs: {len(P):,}  base rate (mean win): {Y.mean():.3f}  L={L}h\n")

    print("RAW p_ps reliability under DEPLOYED σ (decile pred vs actual):")
    edges = np.linspace(0, 1, 11)
    for i in range(10):
        m = (P >= edges[i]) & (P < edges[i + 1]) if i < 9 else (P >= edges[i]) & (P <= edges[i + 1])
        if m.sum() > 30:
            print(f"   [{edges[i]:.1f},{edges[i+1]:.1f})  n={m.sum():>6}  pred={P[m].mean():.3f}  "
                  f"actual={Y[m].mean():.3f}  diff={Y[m].mean()-P[m].mean():+.3f}")

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(P, Y)
    Pc = iso.predict(P)
    print(f"\n  metric          RAW      RECALIB")
    print(f"  Brier        {_brier(P,Y):.4f}   {_brier(Pc,Y):.4f}")
    print(f"  log-loss     {_logloss(P,Y):.4f}   {_logloss(Pc,Y):.4f}")
    print(f"  ECE          {_ece(P,Y):.4f}   {_ece(Pc,Y):.4f}")
    print(f"  rank-corr(p,win) raw = {spearmanr(P,Y).correlation:+.3f}  (want >0)")

    grid = np.linspace(0, 1, 21)
    gmap = iso.predict(grid)
    out = {"grid": [round(float(x), 3) for x in grid],
           "calibrated": [round(float(x), 4) for x in gmap],
           "fit": {"n": int(len(P)), "L_hours": L, "beta": BETA, "sigma": "per-(city,month)+nowcast",
                   "brier_raw": round(_brier(P, Y), 4), "brier_cal": round(_brier(Pc, Y), 4),
                   "near_identity_maxdev": round(float(np.max(np.abs(gmap - grid))), 3)}}
    cand = ROOT / "config" / "stwa_isotonic_candidate.json"
    cand.write_text(json.dumps(out, indent=2))

    # side-by-side vs the LIVE map (old flat-σ fit)
    live = json.load(open(ROOT / "config" / "stwa_isotonic.json"))
    lg, ly = np.array(live["grid"]), np.array(live["calibrated"])
    print(f"\n  near-identity maxdev: NEW {out['fit']['near_identity_maxdev']:.3f}  "
          f"vs LIVE {live['fit'].get('near_identity_maxdev','?')}")
    print(f"  Brier raw→cal: NEW {out['fit']['brier_raw']}→{out['fit']['brier_cal']}  "
          f"vs LIVE {live['fit'].get('brier_raw','?')}→{live['fit'].get('brier_cal','?')}")
    print(f"\n  g(p) side-by-side  p:    NEW_g    LIVE_g   (double-correction check)")
    for x in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 0.95):
        ng = float(iso.predict([x])[0]); og = float(np.interp(x, lg, ly))
        print(f"       p={x:<4}            {ng:.3f}    {og:.3f}   {'⚠ live over-corrects' if og < ng - 0.03 else ''}")
    print(f"\n  candidate written → {cand}  (LIVE config UNTOUCHED; deploy = deliberate copy)")


if __name__ == "__main__":
    main()
