#!/usr/bin/env python3
"""
calib_verify.py — verify the DEPLOYED pricing distribution's calibration. READ-ONLY.

The skill scorecard reports z-std≈1.79 OVERCONFIDENT — but that is computed with the
RAW ACROSS-MODEL spread (ensemble_sigma), which the live pricer does NOT use. The live
PA-shrunk pricer prices each bucket from N(center, sigma) where:
  center = bias-corrected NWP peak  (peak_bias + per-(month,hour) station bias + beta*x_hat)
  sigma  = per-(city,month) sigma_monthly  from config/stwa_peak_calib.json   (deployed 2026-06-03)

This script re-scores the SAME paired (forecast, actual) data under the deployed sigma to
answer the only question that matters: "is the distribution we PRICE WITH honest?"

Bias is handled by the engine's learned per-(month,hour) bias + peak_bias. Offline we cannot
reproduce that table exactly, so we remove the systematic component two honest ways:
  (A) per-city demeaning   (matches what peak_bias+station-bias do; uses ~1 dof/city)
  (B) single global demean  (conservative lower bound on calibration quality)
and report z-std / coverage / PIT / CRPS under each sigma choice. The dispersion verdict
(z-std, coverage) is bias-invariant up to the small demeaning dof, so it is the robust readout.
"""
from __future__ import annotations
import json, math, statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

import analysis.weather.skill_scorecard as sc  # reuse pairing

ROOT = Path(__file__).resolve().parents[2]
PEAK_CALIB = ROOT / "config/stwa_peak_calib.json"


def _Phi(z): return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def sigma_monthly_for(calib: dict, city: str, month: int) -> float:
    """Mirror stwa_engine._peak_sigma_for (SIGMA_CALIB_INFLATION=1.0)."""
    cal = calib.get(city) or calib.get("_pooled", {})
    for src in (cal, calib.get("_pooled", {})):
        sm = src.get("sigma_monthly") if isinstance(src, dict) else None
        if isinstance(sm, dict):
            v = sm.get(str(month)) or sm.get(month)
            if v:
                return float(v)
    return float(cal.get("sigma", 1.1))


def calib_block(zs, label):
    if len(zs) < 2:
        print(f"  {label}: n<2"); return
    z_std = st.pstdev(zs)
    cov68 = sum(1 for z in zs if abs(z) <= 1.0) / len(zs)
    cov95 = sum(1 for z in zs if abs(z) <= 1.96) / len(zs)
    pit = [_Phi(z) for z in zs]
    verdict = ("OVERCONFIDENT" if z_std > 1.15 else
               "UNDERCONFIDENT" if z_std < 0.85 else "≈CALIBRATED")
    print(f"  {label:<34} z-std {z_std:4.2f}  cov±1σ {cov68:5.1%}  "
          f"cov±1.96σ {cov95:5.1%}  PIT μ {st.fmean(pit):.3f}  →  {verdict}")


def main():
    name_to_slug = sc.load_name_to_slug()
    actuals = sc.load_actuals(name_to_slug)
    fc = sc.load_forecasts()
    calib = json.load(open(PEAK_CALIB))

    rows = []  # (slug, day, mu, sig_ens, actual, month)
    for key, snaps in fc.items():
        act = actuals.get(key)
        if act is None:
            continue
        lead, mv, mu, sig = sc.final_snapshot(snaps)
        try:
            month = date.fromisoformat(key[1]).month
        except Exception:
            continue
        rows.append((key[0], key[1], mu, sig, act, month))

    print("=== DEPLOYED-PATH CALIBRATION VERIFICATION (read-only) ===")
    print(f"paired city-days (lead~0): {len(rows)}  "
          f"across {len({r[0] for r in rows})} cities, {len({r[1] for r in rows})} days\n")

    # residual r = actual - mu  (mu = raw across-model ensemble peak)
    res = [r[4] - r[2] for r in rows]
    city_res = defaultdict(list)
    for (slug, _d, mu, _s, act, _m) in rows:
        city_res[slug].append(act - mu)
    city_bias = {c: st.fmean(v) for c, v in city_res.items()}
    glob_bias = st.fmean(res)

    print(f"raw systematic bias (actual-mu): global {glob_bias:+.2f}°C   "
          f"(this is what peak_bias + station bias remove live)\n")

    for demean_name, biasfn in (("per-city demean (A)", lambda r: city_bias[r[0]]),
                                ("global demean (B)",   lambda r: glob_bias)):
        print(f"── {demean_name} ──")
        # (1) raw ensemble sigma  — what the scorecard's 1.79 uses
        zs_ens = [((r[4] - r[2]) - biasfn(r)) / r[3] for r in rows if r[3] > 0]
        calib_block(zs_ens, "raw across-model σ (scorecard)")
        # (2) flat per-city peak_calib sigma
        zs_flat = []
        for r in rows:
            cal = calib.get(r[0]) or calib.get("_pooled", {})
            s = float(cal.get("sigma", 1.1))
            if s > 0:
                zs_flat.append(((r[4] - r[2]) - biasfn(r)) / s)
        calib_block(zs_flat, "flat per-city σ (pre-06-03)")
        # (3) DEPLOYED per-(city,month) sigma
        zs_dep = []
        for r in rows:
            s = sigma_monthly_for(calib, r[0], r[5])
            if s > 0:
                zs_dep.append(((r[4] - r[2]) - biasfn(r)) / s)
        calib_block(zs_dep, ">>> DEPLOYED per-(city,month) σ")
        print()

    # ── Per-bucket Brier (internal °C-grid, 1°C buckets) under each σ ──
    # multiclass Brier on integer-°C buckets centered on round temps; relative comparison
    def bucket_briers(sig_choice):
        tot, n = 0.0, 0
        for (slug, _d, mu, sig_ens, act, month) in rows:
            if sig_choice == "ens":
                s = sig_ens
            elif sig_choice == "flat":
                cal = calib.get(slug) or calib.get("_pooled", {})
                s = float(cal.get("sigma", 1.1))
            else:
                s = sigma_monthly_for(calib, slug, month)
            if s <= 0:
                continue
            center = mu + city_bias[slug]           # bias-corrected center
            lo, hi = int(math.floor(min(center, act))) - 4, int(math.ceil(max(center, act))) + 4
            act_b = int(round(act))
            bsum = 0.0
            for b in range(lo, hi + 1):
                p = _Phi((b + 0.5 - center) / s) - _Phi((b - 0.5 - center) / s)
                y = 1.0 if b == act_b else 0.0
                bsum += (p - y) ** 2
            tot += bsum; n += 1
        return tot / n if n else float("nan")

    print("── multiclass bucket Brier (1°C grid, bias-corrected center; lower=better) ──")
    print(f"  raw across-model σ : {bucket_briers('ens'):.4f}")
    print(f"  flat per-city σ    : {bucket_briers('flat'):.4f}")
    print(f"  DEPLOYED monthly σ : {bucket_briers('dep'):.4f}")


if __name__ == "__main__":
    main()
