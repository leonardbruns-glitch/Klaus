#!/usr/bin/env python3
"""
stwa_isotonic_live_join.py — READ-ONLY diagnostic. Join the LIVE per-bucket pricer
evals (logs/shadow/hot/<date>/stwa_pricer_eval.jsonl) to realized daily highs
(logs/weather/forecast_actuals.jsonl 'actual' events) and report reliability of the
deployed raw prob p_ps and calibrated p_cal — split out the low-p (NO-traded) region,
which is what the model-NO edge rides on.

One row per (city, valid_day, bucket): take the LAST PRE_PEAK eval (the decision-time
print). valid_day = the dated log folder. y = 1 if realized_max in [lo, hi).
Writes nothing. Decides whether a live isotonic refit is justified (n) and in which
direction (does live low-p behave as the map assumes).
"""
from __future__ import annotations
import json, glob, os
from pathlib import Path
from collections import defaultdict
import numpy as np

ROOT = Path(__file__).parent.parent.parent

# realized daily high per (city_slug, valid_day), live era
actual = {}
with open(ROOT / "logs/weather/forecast_actuals.jsonl") as f:
    for l in f:
        try: t = json.loads(l)
        except: continue
        if t.get("event") == "actual" and t.get("wu_high_c") is not None:
            actual[(t.get("city_slug"), t.get("valid_day"))] = float(t["wu_high_c"])

# last PRE_PEAK eval per (city, day, bucket)
last = {}  # key -> (ts, row)
for path in sorted(glob.glob(str(ROOT / "logs/shadow/hot/*/stwa_pricer_eval.jsonl"))):
    day = os.path.basename(os.path.dirname(path))
    if day < "2026-06-03":
        continue
    with open(path) as f:
        for l in f:
            try: t = json.loads(l)
            except: continue
            if t.get("phase") != "PRE_PEAK":
                continue
            key = (t.get("city"), day, t.get("lo"), t.get("hi"))
            ts = t.get("ts", 0)
            if key not in last or ts > last[key][0]:
                last[key] = (ts, t)

P_ps, P_cal, Y = [], [], []
joined_days = set()
for (city, day, lo, hi), (_, row) in last.items():
    mx = actual.get((city, day))
    if mx is None:
        continue
    joined_days.add((city, day))
    y = 1.0 if (lo <= mx < hi) else 0.0
    P_ps.append(float(row.get("p_ps", 0.0)))
    P_cal.append(float(row.get("p_cal", 0.0)))
    Y.append(y)

P_ps = np.array(P_ps); P_cal = np.array(P_cal); Y = np.array(Y)
print(f"joined city-days: {len(joined_days)}   bucket rows: {len(Y)}   base win-rate: {Y.mean():.3f}")

def reliability(P, Y, label):
    print(f"\n=== {label} reliability (decile pred vs actual win) ===")
    edges = np.linspace(0, 1, 11)
    for i in range(10):
        m = (P >= edges[i]) & (P < edges[i+1]) if i < 9 else (P >= edges[i]) & (P <= edges[i+1])
        if m.sum() > 0:
            tag = "  <- NO region" if edges[i] < 0.2 else ""
            print(f"   [{edges[i]:.1f},{edges[i+1]:.1f})  n={m.sum():>5}  pred={P[m].mean():.3f}  "
                  f"actual={Y[m].mean():.3f}  diff={Y[m].mean()-P[m].mean():+.3f}{tag}")

def brier(P, Y): return float(np.mean((P - Y) ** 2))

reliability(P_ps, Y, "RAW p_ps (deployed)")
reliability(P_cal, Y, "CALIBRATED p_cal (live map applied)")
print(f"\nBrier  raw p_ps={brier(P_ps,Y):.4f}   cal p_cal={brier(P_cal,Y):.4f}")

# NO-region focus: buckets the model-NO would target (low YES prob -> high NO prob)
no_mask = P_ps < 0.10
print(f"\n--- low-p NO region (p_ps<0.10): n={no_mask.sum()}  "
      f"realized YES-rate={Y[no_mask].mean():.4f}  (NO wins = 1 - this = {1-Y[no_mask].mean():.4f}) ---")
print("If NO-win-rate >> implied by ask, the model-NO edge is real on live data.")
