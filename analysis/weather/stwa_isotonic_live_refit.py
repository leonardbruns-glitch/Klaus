#!/usr/bin/env python3
"""
stwa_isotonic_live_refit.py — DAILY self-learning refit of the isotonic recal map g,
folding in LIVE 2026 resolutions (YES *and* NO buckets) on top of the historical prior.

Why this exists: config/stwa_isotonic.json was fit on 2024 only and is stale — live
data shows the deployed pricer is badly overconfident at the extremes (p≈0.999 buckets
win ~16%; p≈0 NO buckets the model treats as certain lose ~8%). The skill matrix already
self-learns the *temperature* forecast (side-agnostic). This closes the other half:
the probability calibration learns from live bucket outcomes — including the low-p
region the model-NO edge rides on.

Design (CLAUDE.md n>=100 discipline — never fit live calibration on noise):
  • PAIRS = historical prior (stwa_isotonic_refit.build_historical_pairs, deployed-σ path)
            + live pairs (stwa_pricer_eval LAST PRE_PEAK eval per city-day-bucket,
              joined to official realized high in forecast_actuals). Live pairs are
              weighted x LIVE_WEIGHT so 4 days of live actually move the extremes
              without the sparse mid-range going degenerate (prior fills it).
  • Always writes config/stwa_isotonic_candidate.json + a live reliability report.
  • PROMOTES candidate -> live config ONLY if the guard passes:
      - live joined city-days >= MIN_LIVE_DAYS
      - live pairs with p_ps in the model-NO region (<0.10) >= MIN_LIVE_NO
      - Brier(cal) <= Brier(raw) on the LIVE pairs (the map must help live, not just history)
    Otherwise the live config is left UNTOUCHED (candidate refreshed for inspection).
  • --force promotes regardless of guard (manual Tier-2 override); --dry-run never writes live.

Cron (09:30 UTC, after refresh_skill_matrix at 09:00 so actuals are merged first).
"""
from __future__ import annotations
import json, glob, os, sys, shutil
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from sklearn.isotonic import IsotonicRegression

from analysis.weather.stwa_isotonic_refit import build_historical_pairs

ROOT = Path(__file__).parent.parent.parent
LIVE_CFG  = ROOT / "config" / "stwa_isotonic.json"
CAND_CFG  = ROOT / "config" / "stwa_isotonic_candidate.json"

LIVE_WEIGHT    = 8        # each live pair counts this many times in the pooled fit
MIN_CAL_DAYS   = 14       # distinct CALENDAR days of live data before auto-promote
                          #   (city-days are weather-correlated within a day → not independent)
MIN_LIVE_NO    = 100      # live pairs in the model-NO region (p_ps<0.10) before auto-promote
HOLDOUT_DAYS   = 3        # most-recent calendar days held OUT of the fit for the Brier guard
LIVE_START     = "2026-06-07"   # first CLEAN no-collapse day (σ-collapse disabled 2026-06-06);
                                # pre-06-07 pricer evals were priced under the old collapsed σ and
                                # would teach the refit the wrong target.


def _brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def build_live_pairs():
    """(P_ps, Y, n_city_days) from live pricer evals joined to realized highs.
    One row per (city, valid_day, bucket) = the LAST PRE_PEAK eval (decision-time)."""
    actual = {}
    fa = ROOT / "logs/weather/forecast_actuals.jsonl"
    if fa.exists():
        for l in open(fa):
            try: t = json.loads(l)
            except: continue
            if t.get("event") == "actual" and t.get("wu_high_c") is not None:
                actual[(t.get("city_slug"), t.get("valid_day"))] = float(t["wu_high_c"])
    last = {}
    for path in sorted(glob.glob(str(ROOT / "logs/shadow/hot/*/stwa_pricer_eval.jsonl"))):
        day = os.path.basename(os.path.dirname(path))
        if day < LIVE_START:
            continue
        for l in open(path):
            try: t = json.loads(l)
            except: continue
            if t.get("phase") != "PRE_PEAK":
                continue
            key = (t.get("city"), day, t.get("lo"), t.get("hi"))
            ts = t.get("ts", 0)
            if key not in last or ts > last[key][0]:
                last[key] = (ts, t)
    P, Y, D = [], [], []
    for (city, day, lo, hi), (_, row) in last.items():
        mx = actual.get((city, day))
        if mx is None or lo is None or hi is None:
            continue
        P.append(float(row.get("p_ps", 0.0)))
        Y.append(1.0 if (lo <= mx < hi) else 0.0)
        D.append(day)
    return np.array(P), np.array(Y), np.array(D)


def main():
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    Ph, Yh = build_historical_pairs()
    Pl, Yl, Dl = build_live_pairs()
    cal_days = sorted(set(Dl.tolist())) if len(Dl) else []
    n_cal_days = len(cal_days)
    live_no = int((Pl < 0.10).sum()) if len(Pl) else 0

    # pooled fit (DEPLOYED candidate): historical prior + ALL live (upweighted)
    if len(Pl):
        P = np.concatenate([Ph, np.repeat(Pl, LIVE_WEIGHT)])
        Y = np.concatenate([Yh, np.repeat(Yl, LIVE_WEIGHT)])
    else:
        P, Y = Ph, Yh
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(P, Y)
    grid = np.linspace(0, 1, 21)
    gmap = iso.predict(grid)

    # ── OUT-OF-SAMPLE guard: hold out the most-recent HOLDOUT_DAYS calendar days,
    # fit on (historical + older live), score Brier on the held-out live. An
    # in-sample Brier would always "improve" and is not a real test. ──
    brier_live_raw = brier_live_cal = float("nan")
    if n_cal_days > HOLDOUT_DAYS:
        test_days = set(cal_days[-HOLDOUT_DAYS:])
        te = np.array([d in test_days for d in Dl])
        tr = ~te
        Pfit = np.concatenate([Ph, np.repeat(Pl[tr], LIVE_WEIGHT)])
        Yfit = np.concatenate([Yh, np.repeat(Yl[tr], LIVE_WEIGHT)])
        iso_oos = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(Pfit, Yfit)
        if te.sum():
            brier_live_raw = _brier(Pl[te], Yl[te])
            brier_live_cal = _brier(iso_oos.predict(Pl[te]), Yl[te])

    out = {
        "grid": [round(float(x), 3) for x in grid],
        "calibrated": [round(float(x), 4) for x in gmap],
        "fit": {
            "n_hist": int(len(Ph)), "n_live": int(len(Pl)),
            "live_calendar_days": n_cal_days, "live_no_region": live_no,
            "live_weight": LIVE_WEIGHT,
            "brier_live_oos_raw": round(brier_live_raw, 4) if brier_live_raw == brier_live_raw else None,
            "brier_live_oos_cal": round(brier_live_cal, 4) if brier_live_cal == brier_live_cal else None,
            "refit_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "near_identity_maxdev": round(float(np.max(np.abs(gmap - grid))), 3),
        },
    }
    CAND_CFG.write_text(json.dumps(out, indent=2))

    # ── live reliability report (overall + NO region) ──
    print(f"=== STWA isotonic LIVE refit  {out['fit']['refit_utc']} ===")
    print(f"hist pairs={len(Ph):,}  live pairs={len(Pl)}  live calendar-days={n_cal_days}  "
          f"live NO-region(p<0.10)={live_no}")
    if brier_live_cal == brier_live_cal:
        print(f"LIVE OOS Brier (hold out last {HOLDOUT_DAYS}d) raw={brier_live_raw:.4f} -> cal={brier_live_cal:.4f}")
    if len(Pl):
        edges = np.linspace(0, 1, 11)
        print("LIVE reliability (raw p_ps decile vs realized win):")
        for i in range(10):
            m = (Pl >= edges[i]) & (Pl < edges[i+1]) if i < 9 else (Pl >= edges[i]) & (Pl <= edges[i+1])
            if m.sum():
                tag = "  <- NO region" if edges[i] < 0.2 else ""
                print(f"   [{edges[i]:.1f},{edges[i+1]:.1f})  n={m.sum():>5}  "
                      f"pred={Pl[m].mean():.3f}  actual={Yl[m].mean():.3f}{tag}")
    print("g(p):  " + "  ".join(f"{x:.2f}->{g:.3f}" for x, g in zip(grid, gmap) if x in (0,.1,.3,.5,.7,.9,1.0)))

    # ── promotion guard: independent calendar-day coverage + NO-region n +
    # OUT-OF-SAMPLE Brier improvement on held-out live days ──
    guard_ok = (n_cal_days >= MIN_CAL_DAYS and live_no >= MIN_LIVE_NO
                and brier_live_cal == brier_live_cal and brier_live_cal <= brier_live_raw)
    if dry:
        print(f"\n[dry-run] candidate written -> {CAND_CFG}  (live config untouched)")
        print(f"   guard would {'PASS' if guard_ok else 'HOLD'} "
              f"(cal_days {n_cal_days}/{MIN_CAL_DAYS}, NO {live_no}/{MIN_LIVE_NO})")
        return
    if force or guard_ok:
        if LIVE_CFG.exists():
            shutil.copy(LIVE_CFG, LIVE_CFG.with_suffix(".json.bak"))
        shutil.copy(CAND_CFG, LIVE_CFG)
        why = "FORCED" if (force and not guard_ok) else "guard PASSED"
        print(f"\n*** PROMOTED candidate -> live ({why}). backup: {LIVE_CFG.name}.bak ***")
        print("    (engine picks it up on next restart — it loads the map at init)")
    else:
        reasons = []
        if n_cal_days < MIN_CAL_DAYS: reasons.append(f"cal_days {n_cal_days}<{MIN_CAL_DAYS}")
        if live_no < MIN_LIVE_NO: reasons.append(f"live_NO {live_no}<{MIN_LIVE_NO}")
        if not (brier_live_cal == brier_live_cal): reasons.append("no OOS holdout yet")
        elif brier_live_cal > brier_live_raw: reasons.append("OOS cal Brier worse")
        print(f"\n[guard HELD — live config UNTOUCHED] {'; '.join(reasons)}")
        print(f"   candidate refreshed for inspection -> {CAND_CFG}")


if __name__ == "__main__":
    main()
