#!/usr/bin/env python3
"""
build_peak_monthly.py — write per-(city,month) pricing σ into stwa_peak_calib.json.

WRITES config. The engine prices buckets with peak_calib σ, currently per-city + SEASON-BLIND.
Daily-max forecast error varies ~2× by season (peak_calib_monthly.py). This computes per-
(city,month) σ = std(ensemble daily-max forecast error) from the clean 2021–2024 ASOS history
(local-day) and adds it as `sigma_monthly` to each city (+ a `_pooled` fallback), keeping the
existing flat `sigma` + `peak_bias` as fallbacks for thin months. σ is bias-invariant so this
does NOT touch peak_bias (no double-correction risk). The live loop then refreshes each cell.

Run: python3 -m analysis.weather.build_peak_monthly
"""
from __future__ import annotations
import ast, json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEATHER_ARB = ROOT / "strategy/weather_arb.py"
PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"
MIN_N = 30


def _pd(name):
    s = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", s, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1)))


def main():
    off = _pd("ICAO_UTC_OFFSET_H")
    calib = json.load(open(PEAK_CALIB))

    nwp = pd.read_parquet(ROOT / "data/stwa_nwp.parquet", columns=["city", "icao", "time_utc", "temp_nwp_c", "model"])
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
    df["err"] = df["nwp"] - df["act"]
    df["m"] = pd.to_datetime(df["ld"]).dt.month
    df = df[df["err"].abs() < 15]

    # pooled per-month σ (fallback for cities without their own history)
    pooled = {}
    for mo, g in df.groupby("m"):
        if len(g) >= MIN_N:
            pooled[str(int(mo))] = round(float(g["err"].std()), 3)

    n_city = 0
    n_new = 0
    for city, g in df.groupby("city"):
        sm = {}
        for mo, gm in g.groupby("m"):
            if len(gm) >= MIN_N and gm["err"].std() > 0:
                sm[str(int(mo))] = round(float(gm["err"].std()), 3)
        if not sm:
            continue
        if city not in calib:
            # New city (was pricing on the generic _pooled σ). Seed with annual σ + a 0
            # residual peak_bias — the skill-matrix per-(city,month) bias upstream handles
            # location; peak_bias is only the (small) residual on top of that.
            calib[city] = {"peak_bias": 0.0, "sigma": round(float(g["err"].std()), 3),
                           "n": int(len(g)), "_added": "2026-06-03 per-month build"}
            n_new += 1
        calib[city]["sigma_monthly"] = sm
        n_city += 1
    print(f"(added {n_new} new city entries that were pricing on _pooled)")

    calib.setdefault("_pooled", {})
    calib["_pooled"]["sigma_monthly"] = pooled
    calib["_note"] = (calib.get("_note", "") +
                      " | sigma_monthly added 2026-06-03: per-(city,month) σ = std(ensemble daily-max "
                      "forecast error) from 2021-24 ASOS (local-day, n≥30/cell); flat sigma kept as fallback.")

    PEAK_CALIB.write_text(json.dumps(calib, indent=2))
    print(f"wrote sigma_monthly for {n_city} cities + _pooled ({len(pooled)} months)")
    # show a few for sanity (flat → monthly range)
    for c in ["miami", "houston", "madrid", "moscow", "tokyo", "london", "lucknow"]:
        e = calib.get(c, {})
        sm = e.get("sigma_monthly", {})
        if sm:
            vals = sorted(sm.values())
            print(f"  {c:<12} flat={e.get('sigma'):.2f}  monthly σ {vals[0]:.2f}..{vals[-1]:.2f}  "
                  f"(now [{','.join(sm.get(str(m),'-') and f'{sm.get(str(m),0):.1f}' for m in (5,6))}] for May,Jun)")


if __name__ == "__main__":
    main()
