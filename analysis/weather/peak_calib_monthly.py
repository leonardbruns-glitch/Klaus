#!/usr/bin/env python3
"""
peak_calib_monthly.py — per-city × per-MONTH pricing calibration from 4yr history. READ-ONLY.

The engine prices buckets with peak_calib[city].sigma — which is per-city, SEASON-BLIND,
fit on 2024 only (~1yr), then ×1.52 global EMOS. But daily-max forecast error varies a lot
by season (winter fronts vs summer stability). This computes the proper per-(city,month)
forecast-error bias + σ from the full 2021–2024 hourly history (data/stwa_nwp.parquet ensemble
vs data/stwa_asos.parquet actuals), grouped by LOCAL day (the resolution day), and shows:
  • how much σ varies month-to-month within a city (= the cost of season-blindness),
  • current flat peak_calib σ × 1.52 vs the per-month truth,
  • the calibration each implies (z-std).

Proposes a per-(city,month) peak_calib; does NOT write. The live loop then keeps it fresh.

Run: python3 -m analysis.weather.peak_calib_monthly
"""
from __future__ import annotations
import ast
import json
import re
import statistics as st
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEATHER_ARB = ROOT / "strategy/weather_arb.py"
PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"
SIGMA_INFL = 1.52   # the global EMOS factor currently deployed


def _parse_dict(name: str) -> dict:
    src = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", src, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1))) if m else {}


def main():
    icao_off = _parse_dict("ICAO_UTC_OFFSET_H")
    calib = json.load(open(PEAK_CALIB))

    nwp = pd.read_parquet(ROOT / "data/stwa_nwp.parquet", columns=["city", "icao", "time_utc", "temp_nwp_c", "model"])
    aso = pd.read_parquet(ROOT / "data/stwa_asos.parquet", columns=["city", "time_utc", "temp_c"])

    # local-day grouping (resolution day) using per-icao UTC offset
    nwp["off"] = nwp["icao"].map(icao_off).fillna(0)
    nwp["lday"] = (nwp["time_utc"] + pd.to_timedelta(nwp["off"], unit="h")).dt.date
    # ensemble = mean across the 2 archived models of each model's daily max
    nwp_mm = nwp.groupby(["city", "model", "lday"])["temp_nwp_c"].max().reset_index()
    nwp_ens = nwp_mm.groupby(["city", "lday"])["temp_nwp_c"].mean().reset_index().rename(columns={"temp_nwp_c": "nwp_max"})

    # ASOS local-day max (offset via the city's icao from nwp table)
    city_off = nwp.groupby("city")["off"].first().to_dict()
    aso["off"] = aso["city"].map(city_off).fillna(0)
    aso["lday"] = (aso["time_utc"] + pd.to_timedelta(aso["off"], unit="h")).dt.date
    aso_max = aso.groupby(["city", "lday"])["temp_c"].max().reset_index().rename(columns={"temp_c": "act_max"})

    df = nwp_ens.merge(aso_max, on=["city", "lday"])
    df["err"] = df["nwp_max"] - df["act_max"]          # forecast - actual
    df["month"] = pd.to_datetime(df["lday"]).dt.month
    df = df[df["err"].abs() < 15]                       # drop gross station/data errors

    print(f"=== PER-CITY × PER-MONTH PEAK CALIBRATION (2021–2024, n={len(df)} city-days) ===\n")

    # ---- Aggregate: does σ vary by month? (the cost of season-blindness) ----
    spreads = []
    rows = []
    for city, g in df.groupby("city"):
        monthly_sigma = {}
        for mo, gm in g.groupby("month"):
            if len(gm) < 20:
                continue
            b = gm["err"].mean()
            s = gm["err"].std()
            monthly_sigma[int(mo)] = s
        if len(monthly_sigma) >= 6:
            smin, smax = min(monthly_sigma.values()), max(monthly_sigma.values())
            flat = float(calib.get(city, {}).get("sigma", 1.1)) * SIGMA_INFL
            rows.append((city, smin, smax, smax / max(smin, 0.1), st.fmean(monthly_sigma.values()), flat))
            spreads.append(smax / max(smin, 0.1))

    print("── monthly σ range per city vs the flat (peak_calib σ × 1.52) we price with now ──")
    print(f"  {'city':<15} {'σ_min':>6} {'σ_max':>6} {'max/min':>7} {'mean_σ':>7} {'flat_now':>8}  flag")
    for city, smn, smx, ratio, smean, flat in sorted(rows, key=lambda r: -r[3])[:18]:
        # flag where the flat σ is badly wrong for some months
        flag = "  ⚠flat too tight" if smx > 1.25 * flat else ("  ⚠flat too wide" if smn < 0.75 * flat else "")
        print(f"  {city:<15} {smn:6.2f} {smx:6.2f} {ratio:7.2f} {smean:7.2f} {flat:8.2f}{flag}")
    if spreads:
        print(f"\n  median within-city σ_max/σ_min ratio: {st.median(spreads):.2f}  "
              f"(1.0 = season doesn't matter; >1.4 = season-blind flat σ is materially wrong)")

    # ---- Calibration check: flat-σ×1.52 vs per-month σ (in-sample z-std by month, pooled) ----
    z_flat, z_mon = [], []
    for city, g in df.groupby("city"):
        flat = float(calib.get(city, {}).get("sigma", 1.1)) * SIGMA_INFL
        cb = g["err"].mean()
        for mo, gm in g.groupby("month"):
            if len(gm) < 20:
                continue
            b = gm["err"].mean(); s = gm["err"].std()
            if s <= 0:
                continue
            for e in gm["err"]:
                z_flat.append((e - cb) / flat)     # flat σ, city-bias
                z_mon.append((e - b) / s)          # per-month σ+bias
    print("\n── calibration (pooled z-std; ideal 1.00) ──")
    print(f"  flat σ×1.52 (current)     : z-std {st.pstdev(z_flat):.2f}   cov±1σ {sum(1 for z in z_flat if abs(z)<=1)/len(z_flat):.1%}")
    print(f"  per-(city,month) (proposed): z-std {st.pstdev(z_mon):.2f}   cov±1σ {sum(1 for z in z_mon if abs(z)<=1)/len(z_mon):.1%}")
    print("\n  NOTE: per-month z-std is in-sample (=1.0 by construction); the real signal is the")
    print("  monthly σ RANGE above — where it's wide, the flat σ misprices whole seasons.")
    print("  Proposal: write per-(city,month) {peak_bias,sigma} to stwa_peak_calib.json; the live")
    print("  loop then refreshes each cell. Drops the need for the global ×1.52 crutch.")


if __name__ == "__main__":
    main()
