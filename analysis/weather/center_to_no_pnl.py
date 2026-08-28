#!/usr/bin/env python3
"""
center -> NO-PnL test — does forecast-CENTER accuracy actually drive favorite-
longshot NO win-rate / EV?  This is the strategic gate: A1+A2 recovered center
MSE, but live data (state-log 613/610) said model skill barely moves NO WR. If
that holds here, the rest of the center-accuracy backlog (A4, more peak_bias,
section-C) is hygiene, and the edge is purely A3 (uncertainty) + lockout.

Live n is tiny (n=27, pre-fix). This runs structurally on 2021-2024 ASOS×NWP with
the NOW-FIXED center (ensemble NWP daily max + per-(city,month) peak_bias) and the
deployed per-(city,month) sigma, builds the favorite-longshot NO candidate set the
engine would price (model p_NO in the band that maps to the live ASK band ~[0.70,
0.88]), and asks ONE thing: binned by center error, does NO win-rate / pseudo-EV
fall off?  If yes -> center accuracy is the lever (A1/A2 pay off). If flat -> it
isn't, and center work stops.

Caveats (stated, not hidden): no historical book/asks (pseudo-EV uses model p_NO as
the ask, the calibration-neutral self-consistent choice, + a fixed-ask sensitivity);
no intraday x_hat; ensemble-of-2-models. It tests the MECHANISM at n=thousands, not
live execution.

READ-ONLY.  Run: python3 -m analysis.weather.center_to_no_pnl
"""
from __future__ import annotations
import ast, json, math, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEATHER_ARB = ROOT / "strategy/weather_arb.py"
PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"
import strategy.stwa_engine as eng

BAND_LO, BAND_HI = 0.70, 0.88     # model p_NO band mirroring the live NO ask band
FIXED_ASK = 0.78                  # representative ask for the sensitivity EV
BUCKET_W = 1.0                    # °C bucket width (approx; markets are ~1°F/1°C)
SIGMA_INFL = eng.SIGMA_CALIB_INFLATION


def _pd(name):
    s = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", s, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1))) if m else {}


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def main():
    off = _pd("ICAO_UTC_OFFSET_H")
    calib = json.load(open(PEAK_CALIB))

    nwp = pd.read_parquet(ROOT / "data/stwa_nwp.parquet",
                          columns=["city", "icao", "time_utc", "temp_nwp_c", "model"])
    aso = pd.read_parquet(ROOT / "data/stwa_asos.parquet", columns=["city", "time_utc", "temp_c"])
    nwp["o"] = nwp["icao"].map(off).fillna(0)
    nwp["ld"] = (nwp["time_utc"] + pd.to_timedelta(nwp["o"], unit="h")).dt.date
    mm = nwp.groupby(["city", "model", "ld"])["temp_nwp_c"].max().reset_index()
    ens = mm.groupby(["city", "ld"])["temp_nwp_c"].mean().reset_index().rename(columns={"temp_nwp_c": "nwp"})
    co = nwp.groupby("city")["o"].first().to_dict()
    aso["o"] = aso["city"].map(co).fillna(0)
    aso["ld"] = (aso["time_utc"] + pd.to_timedelta(aso["o"], unit="h")).dt.date
    am = aso.groupby(["city", "ld"])["temp_c"].max().reset_index().rename(columns={"temp_c": "act"})
    df = ens.merge(am, on=["city", "ld"])
    df["m"] = pd.to_datetime(df["ld"]).dt.month
    df = df[(df["act"] - df["nwp"]).abs() < 15]

    # fixed center (A1+A2 fixed) + deployed sigma
    df["center"] = df.apply(lambda r: r["nwp"] + eng._peak_bias_for(calib, r["city"], int(r["m"])), axis=1)
    df["sigma"]  = df.apply(lambda r: eng._peak_sigma_for(calib, r["city"], int(r["m"])), axis=1)
    df["cerr"]   = (df["center"] - df["act"]).abs()
    print(f"city-days: {len(df):,}   mean |center err| = {df['cerr'].mean():.2f}°C\n")

    # --- build favorite-longshot NO candidates per city-day ---
    cands = []
    for r in df.itertuples():
        c, s, act = r.center, max(r.sigma, 1e-6), r.act
        lo0 = math.floor((c - 5) )
        for k in range(0, 11):
            lo = lo0 + k * BUCKET_W
            hi = lo + BUCKET_W
            p_yes = _phi((hi - c) / s) - _phi((lo - c) / s)
            p_no = 1.0 - max(min(p_yes, 1.0), 0.0)
            if BAND_LO <= p_no <= BAND_HI:
                no_win = not (lo <= act < hi)         # NO wins if max NOT in bucket
                cands.append((r.cerr, r.sigma, p_no, no_win))
    cd = pd.DataFrame(cands, columns=["cerr", "sigma", "p_no", "no_win"])
    print(f"favorite-longshot NO candidates (model p_NO in [{BAND_LO},{BAND_HI}]): n={len(cd):,}")
    wr = cd["no_win"].mean()
    print(f"overall: NO WR={wr:.3f}   model mean p_NO={cd['p_no'].mean():.3f}  "
          f"(WR < p_NO => model overconfident, as audit says)")
    ev_self  = (cd["no_win"] - cd["p_no"]).mean()       # buy NO at model price
    ev_fixed = (cd["no_win"] - FIXED_ASK).mean()        # buy NO at fixed 0.78
    print(f"pseudo-EV/$1: at model-price={ev_self:+.4f}   at fixed ask {FIXED_ASK}={ev_fixed:+.4f}\n")

    # --- THE TEST: NO WR / EV binned by CENTER ERROR ---
    print("=" * 78)
    print("NO win-rate & pseudo-EV by CENTER-ERROR quintile  (the strategic gate)")
    print("=" * 78)
    cd["bin"] = pd.qcut(cd["cerr"], 5, duplicates="drop")
    print(f"  {'center_err range':<22}{'n':>7}{'NO_WR':>8}{'p_NO':>7}"
          f"{'EV@0.78':>9}{'EV@model':>10}")
    for b, g in cd.groupby("bin", observed=True):
        print(f"  {str(b):<22}{len(g):>7}{g['no_win'].mean():>8.3f}{g['p_no'].mean():>7.3f}"
              f"{(g['no_win']-FIXED_ASK).mean():>+9.3f}{(g['no_win']-g['p_no']).mean():>+10.3f}")
    c_corr = np.corrcoef(cd["cerr"], cd["no_win"].astype(float))[0, 1]
    print(f"\n  corr(center_err, NO_win) = {c_corr:+.3f}")
    lo_wr = cd[cd['bin']==cd['bin'].cat.categories[0]]['no_win'].mean()
    hi_wr = cd[cd['bin']==cd['bin'].cat.categories[-1]]['no_win'].mean()
    print(f"  best-center quintile WR={lo_wr:.3f}  vs  worst-center quintile WR={hi_wr:.3f}  "
          f"(spread {lo_wr-hi_wr:+.3f})")
    print("\n  READ: large WR spread + low-err quintile +EV while high-err -EV => center")
    print("  accuracy IS the NO lever (A1/A2 pay off, pursue conditional isotonic/section-C).")
    print("  Flat WR across quintiles => center is hygiene; edge is A3 + lockout only.")

    # --- DEPLOYABLE NOW: σ is OBSERVABLE at trade time. Does it predict NO EV? ---
    print("\n" + "=" * 78)
    print("NO win-rate & pseudo-EV by SIGMA quintile  (σ is known at trade time => a gate)")
    print("=" * 78)
    cd["sbin"] = pd.qcut(cd["sigma"], 5, duplicates="drop")
    print(f"  {'sigma range':<22}{'n':>7}{'NO_WR':>8}{'EV@0.78':>9}{'EV@model':>10}")
    for b, g in cd.groupby("sbin", observed=True):
        print(f"  {str(b):<22}{len(g):>7}{g['no_win'].mean():>8.3f}"
              f"{(g['no_win']-FIXED_ASK).mean():>+9.3f}{(g['no_win']-g['p_no']).mean():>+10.3f}")
    s_corr = np.corrcoef(cd["sigma"], cd["no_win"].astype(float))[0, 1]
    print(f"\n  corr(sigma, NO_win) = {s_corr:+.3f}")
    print("  If high-σ quintiles are −EV => gate NO off high-σ (city,month) cells NOW;")
    print("  A3 revision-velocity then adds the DAY-level refinement σ_monthly can't see.")


if __name__ == "__main__":
    main()
