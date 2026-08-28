#!/usr/bin/env python3
"""
skill_scorecard.py — the honest daily-max forecast skill scorecard. READ-ONLY.

Answers the only question that gates the whole predictive program:
  "Which cities can we actually nail, how well, and is our distribution honest?"

Method
------
1. Forecasts  : logs/weather/forecast_actuals.jsonl  (event="forecast")
                per (city_slug, valid_day) snapshot: per-model daily-max values,
                ensemble_mu (raw across-model mean), ensemble_sigma (across-model spread).
                Multiple snapshots/day → binned by lead = valid_day − ts_date.
2. Actuals    : realized daily high = max(running_max_c) per (city, end_date) over
                ALL logs/shadow/hot/*/metar_lockout.jsonl  (METAR-based running max).
                NOTE: read-only proxy. The LIVE learning loop must instead use the
                provenance-clean `official_running_max_c` (AWC/NWS only).
3. Pair on (city_slug, valid_day); report bias / MAE / RMSE / CRPS, PIT calibration
   (the overconfidence test), per-model ranking, per-city reliability vs persistence.

Discipline: n per city is small (days, not 100s). Per-city numbers are DIRECTIONAL
only (anti-sycophancy n-gates). The AGGREGATE (n≈hundreds of city-days) is where the
calibration / model-ranking verdicts are trustworthy. This is exactly why reviving
the learning loop (so actuals accumulate) is Stage 1.

Run:  python3 -m analysis.weather.skill_scorecard
"""
from __future__ import annotations
import ast
import glob
import json
import math
import re
import statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORECASTS = ROOT / "logs/weather/forecast_actuals.jsonl"
LOCKOUTS = sorted(glob.glob(str(ROOT / "logs/shadow/hot/*/metar_lockout.jsonl")))
WEATHER_ARB = ROOT / "strategy/weather_arb.py"

SQRT_PI = math.sqrt(math.pi)


def _phi(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _Phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def crps_gaussian(mu: float, sigma: float, y: float) -> float:
    """Closed-form CRPS of N(mu,sigma) against observation y (Gneiting&Raftery 2007). °C."""
    if sigma <= 0:
        return abs(y - mu)
    z = (y - mu) / sigma
    return sigma * (z * (2 * _Phi(z) - 1) + 2 * _phi(z) - 1.0 / SQRT_PI)


def load_name_to_slug() -> dict:
    """Parse CITY_NAME_TO_SLUG dict literal from weather_arb.py (no heavy import)."""
    src = WEATHER_ARB.read_text()
    m = re.search(r"CITY_NAME_TO_SLUG[^=]*=\s*(\{.*?\})", src, re.DOTALL)
    if not m:
        return {}
    # strip inline comments before literal_eval
    body = re.sub(r"#.*", "", m.group(1))
    return ast.literal_eval(body)


def load_actuals(name_to_slug: dict) -> dict:
    """realized daily high per (slug, valid_day) = max running_max_c over the day."""
    out: dict[tuple, float] = {}
    for fp in LOCKOUTS:
        with open(fp) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                slug = name_to_slug.get(r.get("city"))
                day = r.get("end_date")
                v = r.get("running_max_c")
                if not slug or not day or not isinstance(v, (int, float)):
                    continue
                k = (slug, day)
                out[k] = v if k not in out else max(out[k], v)
    return out


def load_forecasts() -> dict:
    """{(slug,day): [snapshot,...]} where snapshot = (lead_days, model_values, mu, sigma)."""
    snaps: dict[tuple, list] = defaultdict(list)
    with open(FORECASTS) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") != "forecast":
                continue
            slug = r.get("city_slug")
            day = r.get("valid_day")
            mu = r.get("ensemble_mu")
            sig = r.get("ensemble_sigma")
            mv = r.get("model_values") or {}
            ts = r.get("ts_utc", "")
            if not slug or not day or mu is None:
                continue
            try:
                lead = (date.fromisoformat(day) - date.fromisoformat(ts[:10])).days
            except Exception:
                lead = -99
            snaps[(slug, day)].append((lead, mv, float(mu), float(sig or 0.0)))
    return snaps


def final_snapshot(snaps: list):
    """The lead-0 (day-of) snapshot if present, else the smallest-lead one (closest)."""
    day_of = [s for s in snaps if s[0] == 0]
    pool = day_of or snaps
    return min(pool, key=lambda s: abs(s[0]))


def main() -> None:
    name_to_slug = load_name_to_slug()
    actuals = load_actuals(name_to_slug)
    fc = load_forecasts()

    # ---- Pair: use day-of (lead 0) forecast as the headline (the trading-relevant lead)
    rows = []          # (slug, day, lead, mv, mu, sigma, actual)
    rows_all_leads = []
    for key, snaps in fc.items():
        act = actuals.get(key)
        if act is None:
            continue
        lead, mv, mu, sig = final_snapshot(snaps)
        rows.append((key[0], key[1], lead, mv, mu, sig, act))
        for (ld, mv2, mu2, sig2) in snaps:
            rows_all_leads.append((key[0], ld, mu2, sig2, act))

    print(f"=== DAILY-MAX SKILL SCORECARD  (read-only) ===")
    print(f"forecast city-days logged : {len(fc)}")
    print(f"actual city-days (metar)  : {len(actuals)}")
    print(f"PAIRED (headline, lead~0) : {len(rows)}  across {len({r[0] for r in rows})} cities, "
          f"{len({r[1] for r in rows})} days")
    if not rows:
        print("no pairs — cannot score"); return

    # ---- AGGREGATE calibration verdict (trustworthy at n≈hundreds) ----
    ens_err = [r[4] - r[6] for r in rows]                       # mu - actual
    ens_abs = [abs(e) for e in ens_err]
    zs = [(r[6] - r[4]) / r[5] for r in rows if r[5] > 0]       # (actual-mu)/sigma
    pit = [_Phi(z) for z in zs]
    crps = [crps_gaussian(r[4], r[5], r[6]) for r in rows if r[5] > 0]
    cov68 = sum(1 for z in zs if abs(z) <= 1.0) / len(zs) if zs else 0
    cov95 = sum(1 for z in zs if abs(z) <= 1.96) / len(zs) if zs else 0
    z_std = st.pstdev(zs) if len(zs) > 1 else 0.0

    print("\n── AGGREGATE (raw across-model ensemble; lead~0) ──")
    print(f"  ensemble bias (mu-act) : {st.fmean(ens_err):+.2f} °C   (raw, before engine bias-corr)")
    print(f"  ensemble MAE           : {st.fmean(ens_abs):.2f} °C")
    print(f"  ensemble RMSE          : {math.sqrt(st.fmean([e*e for e in ens_err])):.2f} °C")
    print(f"  mean CRPS              : {st.fmean(crps):.2f} °C   (lower=better; proper score)")
    print(f"  PIT mean / std         : {st.fmean(pit):.3f} / {st.pstdev(pit):.3f}   (ideal 0.500 / 0.289)")
    print(f"  z-score std            : {z_std:.2f}   (ideal 1.00; >1 = UNDERDISPERSED/overconfident)")
    print(f"  coverage ±1σ / ±1.96σ  : {cov68:.1%} / {cov95:.1%}   (ideal 68.3% / 95.0%)")
    verdict = ("OVERCONFIDENT" if z_std > 1.15 else "UNDERCONFIDENT" if z_std < 0.85 else "≈CALIBRATED")
    print(f"  >>> DISPERSION VERDICT : {verdict}  (across-model spread is "
          f"{'too tight' if z_std>1.15 else 'too wide' if z_std<0.85 else 'about right'})")

    # ---- Per-model ranking (raw bias / MAE, aggregate) ----
    perm = defaultdict(list)   # model -> [(fc-act)]
    for (_slug, _day, _lead, mv, _mu, _sig, act) in rows:
        for m, v in mv.items():
            if isinstance(v, (int, float)):
                perm[m].append(v - act)
    print("\n── PER-MODEL skill (raw, aggregate) ──   bias / MAE / n")
    model_rank = sorted(((m, st.fmean([abs(e) for e in es]), st.fmean(es), len(es))
                         for m, es in perm.items() if len(es) >= 10), key=lambda t: t[1])
    for m, mae, bias, n in model_rank:
        print(f"  {m:<22} bias {bias:+.2f}   MAE {mae:.2f}   n={n}")

    # ---- Persistence baseline + per-city reliability (DIRECTIONAL, small n) ----
    by_city = defaultdict(list)
    for r in rows:
        by_city[r[0]].append(r)
    print("\n── PER-CITY reliability (DIRECTIONAL — n=days, NOT a decision gate) ──")
    print(f"  {'city':<15} {'n':>3} {'MAE':>5} {'bias':>6} {'CRPS':>5} {'z_std':>5} {'persMAE':>7} {'skill%':>6}")
    city_tbl = []
    for slug, rs in by_city.items():
        if len(rs) < 3:
            continue
        errs = [x[4] - x[6] for x in rs]
        mae = st.fmean([abs(e) for e in errs])
        bias = st.fmean(errs)
        czs = [(x[6]-x[4])/x[5] for x in rs if x[5] > 0]
        czstd = st.pstdev(czs) if len(czs) > 1 else float("nan")
        ccrps = st.fmean([crps_gaussian(x[4], x[5], x[6]) for x in rs if x[5] > 0]) if czs else float("nan")
        # persistence: actual(day-1) as forecast for day
        pe = []
        for (s, day, *_rest, act) in [(x[0], x[1], x[6]) for x in rs]:
            try:
                prev = date.fromisoformat(day).toordinal() - 1
                prevd = date.fromordinal(prev).isoformat()
            except Exception:
                continue
            pa = actuals.get((s, prevd))
            if pa is not None:
                pe.append(abs(pa - act))
        pers = st.fmean(pe) if pe else float("nan")
        skill = (1 - mae / pers) * 100 if pe and pers > 0 else float("nan")
        city_tbl.append((slug, len(rs), mae, bias, ccrps, czstd, pers, skill))
    for t in sorted(city_tbl, key=lambda x: x[2]):
        sk = f"{t[7]:+5.0f}" if t[7] == t[7] else "  n/a"
        pr = f"{t[6]:7.2f}" if t[6] == t[6] else "    n/a"
        cz = f"{t[5]:5.2f}" if t[5] == t[5] else "  n/a"
        cc = f"{t[4]:5.2f}" if t[4] == t[4] else "  n/a"
        print(f"  {t[0]:<15} {t[1]:>3} {t[2]:5.2f} {t[3]:+6.2f} {cc} {cz} {pr} {sk}")

    # ---- Lead-time degradation ----
    by_lead = defaultdict(list)
    for (slug, ld, mu, sig, act) in rows_all_leads:
        if ld in (0, 1, 2, 3):
            by_lead[ld].append((mu, sig, act))
    print("\n── LEAD-TIME degradation (all snapshots) ──   lead_days: MAE / CRPS / n")
    for ld in sorted(by_lead):
        pts = by_lead[ld]
        mae = st.fmean([abs(mu-a) for (mu, s, a) in pts])
        cr = st.fmean([crps_gaussian(mu, s, a) for (mu, s, a) in pts if s > 0])
        print(f"  lead {ld}d : MAE {mae:.2f}   CRPS {cr:.2f}   n={len(pts)}")

    print("\n── READING THIS ──")
    print("  • z-score std > 1.15  → our σ (across-model spread) is too tight → bucket probs")
    print("    overconfident → directional YES bleeds. This is the calibration target (Stage 2).")
    print("  • skill% > 0 → ensemble beats persistence for that city (worth trading on forecast).")
    print("    skill% < 0 → persistence wins → do NOT trade directional there yet.")
    print("  • Per-city n is days (small) → DIRECTIONAL. Reviving log_actual grows n → decisions.")


if __name__ == "__main__":
    main()
