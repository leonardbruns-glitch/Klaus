#!/usr/bin/env python3
"""
A3 analyzer (flagship) — does intraday forecast REVISION VELOCITY predict daily-max
forecast error?  If yes, map it to a live σ-inflation multiplier (high-revision day
=> wider, less-confident book).  READ-ONLY; touches no live σ.

Audit A3: |μ_last − μ_first| across the intraday model_center revision series predicts
forecast error magnitude + model overconfidence, but never widens priced σ. Section B
already KILLED naive same-cycle cross-model spread — only the TIME-DERIVATIVE works,
so this must run on the live revision series, not the single-cycle reanalysis parquet.

Per (city, local-day) from logs/shadow/hot/<date>/stwa_ladder_book.jsonl:
  - revision series  = model_center stamped per snapshot (added 2026-06-07, entry 614)
  - rev_velocity     = |center_last − center_first|
  - rev_range        = max(center) − min(center)
  - realized daily max = max running_max_c over the day from metar_lockout.jsonl (official)
  - error             = |center_last − realized_max|
Reports corr(rev_velocity, error) and an error-by-revision-bin curve (the σ-inflation
shape). GRADUATION GATE before any live σ change: n>=100 city-days AND monotone
error-vs-revision AND the implied σ-inflation improves held-out CRPS. Prints current n.

Run: python3 -m analysis.weather.revision_velocity_sigma
"""
from __future__ import annotations
import ast, json, re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SHADOW = ROOT / "logs/shadow/hot"
WEATHER_ARB = ROOT / "strategy/weather_arb.py"
GATE_N = 100


def _pd(name):
    s = WEATHER_ARB.read_text()
    m = re.search(name + r"[^=]*=\s*(\{.*?\})", s, re.DOTALL)
    return ast.literal_eval(re.sub(r"#.*", "", m.group(1))) if m else {}


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def main():
    off = _pd("ICAO_UTC_OFFSET_H")
    days = sorted(p.name for p in SHADOW.glob("2026-*") if p.is_dir())
    # --- collect model_center revision series per (city, local-day) ---
    series = defaultdict(list)   # (slug, lday) -> [(ts, center)]
    for d in days:
        f = SHADOW / d / "stwa_ladder_book.jsonl"
        if not f.exists():
            continue
        for line in f.open():
            try:
                r = json.loads(line)
            except Exception:
                continue
            mc = r.get("model_center")
            if mc is None:
                continue
            slug = _slugify(r.get("city", ""))
            ts = r.get("ts", 0)
            o = off.get((r.get("icao") or "").upper(), 0)
            lday = pd.to_datetime(ts, unit="s", utc=True) + pd.Timedelta(hours=o)
            series[(slug, lday.date())].append((ts, float(mc)))

    # --- realized daily max from metar_lockout (official running_max_c) ---
    realized = {}  # (slug, lday) -> max running_max_c
    for d in days:
        f = SHADOW / d / "metar_lockout.jsonl"
        if not f.exists():
            continue
        for line in f.open():
            try:
                r = json.loads(line)
            except Exception:
                continue
            rm = r.get("running_max_c")
            if rm is None:
                continue
            slug = _slugify(r.get("city", ""))
            o = off.get((r.get("icao") or "").upper(), 0)
            ts = r.get("ts_s") or 0
            lday = (pd.to_datetime(ts, unit="s", utc=True) + pd.Timedelta(hours=o)).date()
            k = (slug, lday)
            realized[k] = max(realized.get(k, -999), float(rm))

    # --- build per-(city,day) features ---
    rows = []
    for key, pts in series.items():
        if len(pts) < 3:
            continue
        pts.sort()
        centers = [c for _, c in pts]
        rev_vel = abs(centers[-1] - centers[0])
        rev_rng = max(centers) - min(centers)
        rm = realized.get(key)
        err = abs(centers[-1] - rm) if rm is not None and rm > -900 else None
        rows.append({"city": key[0], "day": str(key[1]), "n_snap": len(pts),
                     "rev_vel": rev_vel, "rev_rng": rev_rng,
                     "center_last": centers[-1], "realized": rm, "err": err})
    df = pd.DataFrame(rows)
    print(f"city-days with a usable revision series (>=3 snaps): {len(df)}")
    if len(df) == 0:
        print("no revision data yet — ladder_book model_center logging (entry 614) "
              "needs the bot RUNNING to accumulate. Nothing to validate.")
        return
    joined = df.dropna(subset=["err"]).copy()
    print(f"  ... of which joined to a realized max: {len(joined)}")
    print(f"  median snaps/city-day: {df['n_snap'].median():.0f}  "
          f"max: {df['n_snap'].max()}   (audit claimed ~48, up to 300)\n")

    if len(joined) >= 5:
        c_vel = joined["rev_vel"].corr(joined["err"])
        c_rng = joined["rev_rng"].corr(joined["err"])
        print(f"corr(rev_velocity, |error|) = {c_vel:+.3f}   "
              f"corr(rev_range, |error|) = {c_rng:+.3f}   (n={len(joined)})")
        # error-by-revision-bin = the σ-inflation shape
        try:
            joined["bin"] = pd.qcut(joined["rev_vel"], q=min(4, joined["rev_vel"].nunique()),
                                    duplicates="drop")
            print("\n  error (RMSE) by revision-velocity quartile (the σ-inflation curve):")
            for b, g in joined.groupby("bin", observed=True):
                print(f"    rev_vel {str(b):<22} n={len(g):>3}  "
                      f"RMSE_err={np.sqrt((g['err']**2).mean()):.2f}°C  mean_rev={g['rev_vel'].mean():.2f}")
        except Exception as e:
            print(f"  (binning skipped: {e})")
    else:
        print("too few joined city-days for even a directional read.")

    print("\n" + "=" * 78)
    verdict = "PASS" if len(joined) >= GATE_N else "HOLD"
    print(f"GRADUATION GATE n>={GATE_N}: {verdict}  (have {len(joined)} joined city-days)")
    if verdict == "HOLD":
        print("A3 stays SHADOW — no live σ change. Keep the bot running to accumulate the\n"
              "model_center revision series; re-run this analyzer at n>=100 for a verdict.")
    print("=" * 78)


if __name__ == "__main__":
    main()
