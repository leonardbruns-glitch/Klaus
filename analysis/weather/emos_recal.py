#!/usr/bin/env python3
"""
emos_recal.py — EMOS variance-inflation for the daily-max pricer. READ-ONLY (proposes).

The engine prices buckets with peak_calib[city].sigma (PA_SHRUNK center = NWP_peak +
peak_bias + β·resid). The scorecard showed the predictive distribution is ~1.8×
underdispersed (realized RMSE 1.60°C vs pricing σ ~0.9–1.1°C). This computes the
global variance-inflation that calibrates it (z-std → 1.0, coverage → 68/95), keeping
the 2024 per-city σ SHAPE (relative predictability) but scaling to realized live
forecast-error dispersion. n/city is small (days) → a GLOBAL factor, NOT per-city σ
from 7 points. Also flags cities whose peak_bias has drifted (frozen since 2024).

Proposes; does NOT write. Apply via stwa_peak_calib.json once the revived loop feeds n.

Run: python3 -m analysis.weather.emos_recal
"""
from __future__ import annotations
import json
import math
import statistics as st
from collections import defaultdict

from analysis.weather.skill_scorecard import (
    load_name_to_slug, load_actuals, load_forecasts, final_snapshot, ROOT,
    crps_gaussian,
)

PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"
DEFAULT_SIGMA = 1.1


def main():
    calib = json.load(open(PEAK_CALIB))
    name_to_slug = load_name_to_slug()
    actuals = load_actuals(name_to_slug)
    fc = load_forecasts()

    rows = []  # (slug, mu, actual, sigma_pc, peak_bias_pc)
    for key, snaps in fc.items():
        act = actuals.get(key)
        if act is None:
            continue
        _lead, _mv, mu, _sig = final_snapshot(snaps)
        c = calib.get(key[0]) or calib.get("_pooled", {})
        rows.append((key[0], mu, act, float(c.get("sigma", DEFAULT_SIGMA)),
                     float(c.get("peak_bias", 0.0))))
    n = len(rows)
    print(f"=== EMOS σ-RECALIBRATION (read-only proposal) ===")
    print(f"paired city-days: {n}  ({len({r[0] for r in rows})} cities)")
    if n < 20:
        print("too few pairs"); return

    # engine center ≈ ensemble_mu + peak_bias ; signed error e = center - actual
    e = [(mu + pb) - act for (_s, mu, act, spc, pb) in rows]
    s = [spc for (_s, mu, act, spc, pb) in rows]
    r = [ei / si for ei, si in zip(e, s)]                 # standardized residual
    bias = st.fmean(e)
    infl_rms = math.sqrt(st.fmean([ri * ri for ri in r])) # σ matches total MSE (absorbs bias)
    infl_std = st.pstdev(r)                                # σ matches pure spread (bias fixed elsewhere)

    print("\n── current engine calibration (center = ensemble_μ + peak_bias) ──")
    print(f"  residual bias (center-act): {bias:+.2f} °C   "
          f"({'peak_bias still ≈ holds' if abs(bias) < 0.35 else 'peak_bias DRIFTED — refit'})")
    print(f"  std standardized resid    : {infl_std:.2f}   (=1.0 if σ calibrated; this is the inflation)")
    print(f"  rms standardized resid    : {infl_rms:.2f}   (conservative inflation, absorbs bias)")
    cov68_0 = sum(1 for ri in r if abs(ri) <= 1) / n
    print(f"  current coverage ±1σ      : {cov68_0:.1%}  (ideal 68.3%)")

    # ---- Apply global inflation k=infl_std (+ global bias removal) and validate ----
    k = round(infl_std, 3)
    z_cal = [(ei - bias) / (si * k) for ei, si in zip(e, s)]
    cov68 = sum(1 for z in z_cal if abs(z) <= 1) / n
    cov95 = sum(1 for z in z_cal if abs(z) <= 1.96) / n
    crps0 = st.fmean([crps_gaussian(0.0, si, ei) for ei, si in zip(e, s)])           # current σ
    crps1 = st.fmean([crps_gaussian(bias, si * k, ei) for ei, si in zip(e, s)])      # calibrated
    print(f"\n── after global inflation σ → σ × {k}  (+ remove {bias:+.2f}°C residual bias) ──")
    print(f"  z-std            : {st.pstdev(z_cal):.2f}  (target 1.00)")
    print(f"  coverage ±1σ/95  : {cov68:.1%} / {cov95:.1%}  (ideal 68.3% / 95.0%)")
    print(f"  mean CRPS        : {crps0:.2f} → {crps1:.2f} °C  ({100*(crps0-crps1)/crps0:+.0f}%)")

    # ---- Per-city: proposed σ, residual bias, dispersion (flag broken shapes) ----
    by_city = defaultdict(list)
    for (slug, mu, act, spc, pb) in rows:
        by_city[slug].append(((mu + pb) - act, spc))
    print("\n── per-city (DIRECTIONAL, n=days) ──  σ_now→σ_cal | resid_bias | city z-std | n")
    print("   (city z-std ≫ global → σ shape wrong; |bias|≫0 → peak_bias stale)")
    out = []
    for slug, es in sorted(by_city.items()):
        if len(es) < 4:
            continue
        errs = [x[0] for x in es]
        spc = es[0][1]
        cbias = st.fmean(errs)
        cz = st.pstdev([x[0] / x[1] for x in es])
        out.append((slug, spc, round(spc * k, 2), cbias, cz, len(es)))
    for slug, s0, s1, cb, cz, nn in sorted(out, key=lambda t: -t[4]):
        flag = "  ⚠shape" if cz > 1.6 * k else ("  ⚠bias" if abs(cb) > 1.0 else "")
        print(f"  {slug:<15} {s0:.2f}→{s1:.2f}  {cb:+.2f}  z={cz:.2f}  n={nn}{flag}")

    print("\n── PROPOSAL ──")
    print(f"  • Global σ inflation ×{k} on stwa_peak_calib.json (keep per-city shape).")
    print(f"  • This is the bleed fix: bucket probs stop being {infl_std:.1f}× overconfident.")
    print(f"  • ⚠shape cities (seattle etc.) need per-city σ once n grows — don't trade yet.")
    print(f"  • ⚠bias cities (seoul etc.) = station/oracle mismatch — exclude, don't just widen σ.")
    print(f"  • Re-run after the revived loop adds pairs; promote to per-city EMOS at n≥30/city.")


if __name__ == "__main__":
    main()
