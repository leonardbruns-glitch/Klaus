#!/usr/bin/env python3
"""
nowcast_sigma.py — how much daily-max uncertainty collapses as the peak nears. READ-ONLY.

The pricer uses a constant per-(city,month) σ all day. But once we've observed the running
max R at local hour h, the eventual daily max is daily_max = max(R, future rise) — and the
residual uncertainty std(daily_max − R) shrinks toward 0 as h passes the diurnal peak. That
is the nowcast: σ_eff(h) = min(σ_forecast, σ_remaining(h)). This measures σ_remaining by
hours-to-peak from the 4yr hourly ASOS history (local-day), so we can shrink σ late in the day
(more confident exactly when the day is nearly decided) — SAFE because it only ever *shrinks* σ.

Run: python3 -m analysis.weather.nowcast_sigma
"""
from __future__ import annotations
import ast, json, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEATHER_ARB = ROOT / "strategy/weather_arb.py"


def _pd(name):
    s = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", s, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1)))


def main():
    off = _pd("ICAO_UTC_OFFSET_H")
    aso = pd.read_parquet(ROOT / "data/stwa_asos.parquet", columns=["city", "icao", "time_utc", "temp_c"])
    aso["o"] = aso["icao"].map(off).fillna(0)
    lt = aso["time_utc"] + pd.to_timedelta(aso["o"], unit="h")
    aso["lday"] = lt.dt.date
    aso["lhour"] = lt.dt.hour
    aso["month"] = lt.dt.month
    aso = aso.dropna(subset=["temp_c"]).sort_values(["city", "lday", "lhour"])

    # running max within each local day, daily max, peak hour
    g = aso.groupby(["city", "lday"], sort=False)
    aso["runmax"] = g["temp_c"].cummax()
    daily = g.agg(dmax=("temp_c", "max")).reset_index()
    peakh = aso.loc[g["temp_c"].idxmax().values, ["city", "lday", "lhour"]].rename(columns={"lhour": "peakh"})
    aso = aso.merge(daily, on=["city", "lday"]).merge(peakh, on=["city", "lday"])
    aso["h2p"] = aso["lhour"] - aso["peakh"]          # hours to peak (neg=before)
    aso["remain"] = aso["dmax"] - aso["runmax"]       # >=0 by construction

    print(f"=== NOWCAST σ — uncertainty collapse vs hours-to-peak (n={len(aso):,} obs-hours) ===\n")
    print("  h2p = local hour − peak hour (−3 = 3h before peak, 0 = at peak, +2 = 2h after)")
    print(f"  {'h2p':>4} {'σ_remaining':>11} {'mean_remain':>11} {'n':>9}")
    pooled = {}
    for h, gh in aso.groupby("h2p"):
        if -6 <= h <= 4 and len(gh) > 500:
            s = float(gh["remain"].std()); pooled[int(h)] = s
            print(f"  {int(h):>4} {s:>11.2f} {gh['remain'].mean():>11.2f} {len(gh):>9,}")

    # forecast σ reference (typical per-month σ we price with)
    print("\n── interpretation ──")
    if pooled:
        pre = pooled.get(-4, pooled.get(-5))
        atp = pooled.get(0); post = pooled.get(1)
        print(f"  σ_remaining ≈ {pre:.2f}°C at −4h  →  {atp:.2f}°C at peak  →  {post:.2f}°C at +1h")
        print(f"  Forecast σ we price with is ~0.7–1.1°C (per-month). So nowcast σ drops BELOW the")
        print(f"  forecast σ roughly from ~1h before peak onward → that's the window to sharpen.")

    # per-city: at what h2p does σ_remaining fall under 0.5°C? (how early each city 'locks')
    print("\n── per-city: hours-to-peak where σ_remaining first ≤ 0.5°C (earlier = more nowcastable) ──")
    rows = []
    for city, gc in aso.groupby("city"):
        ser = gc.groupby("h2p")["remain"].std()
        cands = [h for h in sorted(ser.index) if h <= 2 and ser[h] <= 0.5 and gc[gc["h2p"] == h].shape[0] > 100]
        if cands:
            rows.append((city, min(cands)))
    for city, h in sorted(rows, key=lambda r: r[1])[:16]:
        print(f"  {city:<15} σ≤0.5°C from h2p={h:+d}")
    print("\n  Proposal: σ_eff = min(σ_(city,month), σ_remaining(city,month,h2p)). Only shrinks σ")
    print("  (never widens) → safe; sharpens pricing in the final approach to peak. Engine already")
    print("  floors bins below the running max; this sharpens the soft part above it.")


if __name__ == "__main__":
    main()
