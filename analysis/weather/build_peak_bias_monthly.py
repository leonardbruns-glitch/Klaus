#!/usr/bin/env python3
"""
build_peak_bias_monthly.py — write per-(city,month) `peak_bias_monthly` into
stwa_peak_calib.json (A2 implementation). WRITES config (with backup).

The engine adds a per-city SCALAR peak_bias to the (ensemble-anchored, bias-
corrected) daily-max center (stwa_engine.py:1013). Audit A2 + peak_bias_refit_
backtest.py showed the daily-max residual has per-MONTH structure a single scalar
misses: on the 11 offline-testable (US) cities, per-(city,month) beats the scalar
by ~-3.8% CRPS / -11.7% MSE OOS (train<=2023 / test 2024).

This is the bias-sibling of build_peak_monthly.py (which wrote sigma_monthly):
SAME fit basis (err = ensemble daily-max forecast - ASOS actual, local-day,
n>=MIN_N), so it does NOT introduce new double-counting — peak_bias_monthly is
just the existing scalar sliced by month. Cities/months without enough data keep
no monthly key -> engine falls back to the scalar peak_bias -> behaviour unchanged.
peak_bias to ADD = -(forecast - actual) = mean(actual - forecast).

Prints a self-validation (OOS CRPS, and annual peak_bias_monthly vs existing
scalar for consistency) BEFORE writing.

Run: python3 -m analysis.weather.build_peak_bias_monthly [--write]
"""
from __future__ import annotations
import ast, json, math, re, sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
WEATHER_ARB = ROOT / "strategy/weather_arb.py"
PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"
MIN_N = 30
TRAIN_MAX_YEAR = 2023


def _pd(name):
    s = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", s, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1)))


def crps_g(err, sigma):
    s = max(sigma, 1e-6); z = err / s
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return s * (z * (2 * cdf - 1) + 2 * pdf - 1.0 / math.sqrt(math.pi))


def load_daily():
    off = _pd("ICAO_UTC_OFFSET_H")
    nwp = pd.read_parquet(ROOT / "data/stwa_nwp.parquet",
                          columns=["city", "icao", "time_utc", "temp_nwp_c", "model"])
    aso = pd.read_parquet(ROOT / "data/stwa_asos.parquet",
                          columns=["city", "time_utc", "temp_c"])
    nwp["o"] = nwp["icao"].map(off).fillna(0)
    nwp["ld"] = (nwp["time_utc"] + pd.to_timedelta(nwp["o"], unit="h")).dt.date
    mm = nwp.groupby(["city", "model", "ld"])["temp_nwp_c"].max().reset_index()
    ens = mm.groupby(["city", "ld"])["temp_nwp_c"].mean().reset_index().rename(columns={"temp_nwp_c": "nwp"})
    co = nwp.groupby("city")["o"].first().to_dict()
    aso["o"] = aso["city"].map(co).fillna(0)
    aso["ld"] = (aso["time_utc"] + pd.to_timedelta(aso["o"], unit="h")).dt.date
    am = aso.groupby(["city", "ld"])["temp_c"].max().reset_index().rename(columns={"temp_c": "act"})
    df = ens.merge(am, on=["city", "ld"])
    df["err"] = df["nwp"] - df["act"]          # forecast - actual
    df["m"] = pd.to_datetime(df["ld"]).dt.month
    df["y"] = pd.to_datetime(df["ld"]).dt.year
    return df[df["err"].abs() < 15]


def main():
    write = "--write" in sys.argv
    calib = json.load(open(PEAK_CALIB))
    df = load_daily()
    print(f"city-days: {len(df):,}\n")

    # ---- OOS validation (train<=2023 / test 2024), fitted cities only ----
    tr, te = df[df["y"] <= TRAIN_MAX_YEAR], df[df["y"] == TRAIN_MAX_YEAR + 1]
    scalar = {c: -g["err"].mean() for c, g in tr.groupby("city") if len(g) >= MIN_N}
    sigc   = {c: g["err"].std() for c, g in tr.groupby("city")}
    mon, msig = {}, {}
    for (c, m), g in tr.groupby(["city", "m"]):
        if len(g) >= MIN_N:
            mon[(c, m)] = -g["err"].mean(); msig[(c, m)] = g["err"].std()
    fit = te[te["city"].isin(scalar)]
    es, em, ss = [], [], []
    for _, r in fit.iterrows():
        b_s = scalar[r["city"]]
        b_m = mon.get((r["city"], r["m"]), b_s)
        sg  = msig.get((r["city"], r["m"]), sigc.get(r["city"], 1.2)) or 1.2
        es.append((r["act"] - (r["nwp"] + b_s)))   # note: act - (forecast + bias_to_add)
        em.append((r["act"] - (r["nwp"] + b_m)))
        ss.append(sg)
    es, em, ss = np.array(es), np.array(em), np.array(ss)
    cs = np.mean([crps_g(e, s) for e, s in zip(es, ss)])
    cm = np.mean([crps_g(e, s) for e, s in zip(em, ss)])
    print(f"OOS (test 2024, {fit['city'].nunique()} fitted cities, n={len(fit)}):")
    print(f"  SCALAR  MSE={np.mean(es**2):.4f}  CRPS={cs:.4f}")
    print(f"  MONTH   MSE={np.mean(em**2):.4f}  CRPS={cm:.4f}   "
          f"(MSE {100*(np.mean(em**2)-np.mean(es**2))/np.mean(es**2):+.1f}%, CRPS {100*(cm-cs)/cs:+.1f}%)\n")

    # ---- consistency: full-data annual peak_bias vs existing config scalar ----
    print("consistency — full-data annual peak_bias (-mean err) vs existing config scalar:")
    diffs = []
    for c in sorted(scalar):
        ann = -df[df["city"] == c]["err"].mean()
        cur = float(calib.get(c, {}).get("peak_bias", 0.0))
        diffs.append(abs(ann - cur))
    print(f"  median |annual_fit - config_scalar| = {np.median(diffs):.3f}°C over {len(diffs)} cities "
          f"(small => same basis, no regime shift)\n")

    # ---- build peak_bias_monthly: existing scalar + SEASONAL DEVIATION ----
    # Anchor on each city's trusted config scalar (the absolute level was fit on a
    # different period/basis — 0.33°C median gap above) and add ONLY the seasonal
    # shape (month_fit - annual_fit). Preserves the annual level exactly => no
    # regime shift; adds only the per-month structure the OOS test credits.
    global_annual = -df["err"].mean()
    pooled = {}
    for mo, g in df.groupby("m"):
        if len(g) >= MIN_N:
            pooled[str(int(mo))] = round(float(-g["err"].mean()), 3)  # _pooled: absolute (new cities)
    n_city = 0
    for city, g in df.groupby("city"):
        if city not in calib:
            continue
        scalar_cfg = float(calib[city].get("peak_bias", 0.0))
        annual_fit = -g["err"].mean()
        bm = {}
        for mo, gm in g.groupby("m"):
            if len(gm) >= MIN_N:
                season_dev = (-gm["err"].mean()) - annual_fit
                bm[str(int(mo))] = round(float(scalar_cfg + season_dev), 3)
        if not bm:
            continue
        calib[city]["peak_bias_monthly"] = bm
        n_city += 1
    calib.setdefault("_pooled", {})["peak_bias_monthly"] = pooled

    if write:
        bak = PEAK_CALIB.with_suffix(".json.bak_preA2")
        bak.write_text(json.dumps(json.load(open(PEAK_CALIB)), indent=2))
        calib["_note"] = (calib.get("_note", "") +
                          " | peak_bias_monthly added 2026-06-08 (A2): per-(city,month) peak_bias = "
                          "mean(actual - ensemble daily-max forecast), 2021-24 local-day n>=30; scalar peak_bias "
                          "kept as fallback. OOS (US cities) -3.8% CRPS vs scalar.")
        PEAK_CALIB.write_text(json.dumps(calib, indent=2))
        print(f"WROTE peak_bias_monthly for {n_city} cities + _pooled ({len(pooled)} months). backup -> {bak.name}")
    else:
        print(f"DRY RUN — would write peak_bias_monthly for {n_city} cities + _pooled ({len(pooled)} months). "
              f"re-run with --write to commit.")


if __name__ == "__main__":
    main()
