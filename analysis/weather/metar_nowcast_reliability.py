"""
METAR Nowcast Reliability Analysis
===================================
Fetches 90 days of ASOS hourly data from Iowa State Mesonet for every validated city.
For each day, applies the bot's mu_nowcast formula at T-6h, T-4h, T-2h before peak UTC,
and compares to the observed daily maximum temperature.

Metrics per city per phase:
  MAE      — mean absolute error of mu_nowcast vs actual_max  (lower = better)
  Bias     — signed mean error (positive = over-predicts)
  within_1σ — fraction of days where |error| < sigma_base (bot's floor)
  n_days   — usable days (skip days with <8 hourly obs or missing phase reading)

Run: python3 analysis/weather/metar_nowcast_reliability.py
"""

import csv
import io
import math
import sys
import time
import urllib.request
from datetime import date, timedelta, datetime, timezone
from typing import Optional

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import (
    CITY_ICAO,
    CITY_PEAK_HOUR_UTC,
    CITY_REMAINING_RISE,
    CITY_SIGMA_C,
    ICAO_UTC_OFFSET_H,
    VALIDATED_CITY_SLUGS,
    CITY_NAME_TO_SLUG,
)

# ── Config ────────────────────────────────────────────────────────────────────
DAYS_BACK    = 90
PHASES_H     = [6, 4, 2]   # hours before peak to evaluate
MIN_OBS_DAY  = 8           # skip days with fewer hourly readings
SLEEP_S      = 1.5         # polite delay between API calls

sky_factors = {"SKC": 1.0, "CLR": 1.0, "FEW": 0.85, "SCT": 0.60,
               "BKN": 0.30, "OVC": 0.08, "VV": 0.08, "M": 0.60}

# Build city list: name → (icao, slug)
CITIES: list[tuple[str, str, str]] = []
for city_name, slug in CITY_NAME_TO_SLUG.items():
    if slug not in VALIDATED_CITY_SLUGS:
        continue
    icao = CITY_ICAO.get(city_name)
    if not icao:
        continue
    CITIES.append((city_name, icao, slug))
CITIES.sort(key=lambda x: x[0])


def fetch_asos(icao: str, date_start: date, date_end: date) -> list[dict]:
    """
    Fetch hourly ASOS obs from Iowa State Mesonet.
    Returns list of {utc_dt, temp_c, sky_cover} sorted by utc_dt.
    Retries once on 429.
    """
    url = (
        "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        f"?station={icao}"
        f"&data=tmpf,skyc1"
        f"&year1={date_start.year}&month1={date_start.month:02d}&day1={date_start.day:02d}"
        f"&year2={date_end.year}&month2={date_end.month:02d}&day2={date_end.day:02d}"
        f"&tz=Etc%2FUTC&format=onlycomma&latlon=no&direct=no&report_type=3"
    )
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KlausAnalysis/1.0"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(8 + attempt * 8)
                continue
            print(f"\n  [WARN] fetch failed for {icao}: {e}")
            return []

    rows = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        try:
            tmpf_str = row.get("tmpf", "M")
            if not tmpf_str or tmpf_str.strip() in ("M", ""):
                continue
            temp_c = (float(tmpf_str) - 32) * 5 / 9
            valid_str = row.get("valid", "")
            utc_dt = datetime.strptime(valid_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            sky_raw = (row.get("skyc1") or "CLR").strip()
            sky = sky_raw if sky_raw in sky_factors else "CLR"
            rows.append({"utc_dt": utc_dt, "temp_c": temp_c, "sky": sky})
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda o: o["utc_dt"])
    return rows


def daily_nowcast_errors(
    obs: list[dict],
    slug: str,
    utc_offset_h: int,
) -> dict[int, list[float]]:
    """
    For each local calendar date in obs, evaluate mu_nowcast at T-6, T-4, T-2
    before peak UTC. Returns {h_before: [error, ...]} where error = mu_nc - actual_max.

    Key: running_max resets at LOCAL midnight (= 00:00 local = -utc_offset_h UTC).
    The eval UTC datetime is computed as peak_utc_dt - h_before, and only obs BEFORE
    that datetime (from local midnight of the same local day) contribute to run_max.
    """
    results: dict[int, list[float]] = {h: [] for h in PHASES_H}

    # Group obs into local calendar dates
    by_local_date: dict[date, list[dict]] = {}
    for o in obs:
        local_dt = o["utc_dt"] + timedelta(hours=utc_offset_h)
        d = local_dt.date()
        by_local_date.setdefault(d, []).append(o)

    for local_d, day_obs in sorted(by_local_date.items()):
        if len(day_obs) < MIN_OBS_DAY:
            continue
        month    = local_d.month
        peak_h   = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
        if peak_h is None:
            continue

        # Local midnight in UTC: local date 00:00 local = date 00:00 - utc_offset_h
        local_midnight_utc = datetime(
            local_d.year, local_d.month, local_d.day, 0, 0,
            tzinfo=timezone.utc
        ) - timedelta(hours=utc_offset_h)

        # Peak UTC datetime: find the first UTC datetime >= local_midnight_utc
        # where the UTC clock reads peak_h (handles Asian cities where peak_h < utc_offset_h).
        candidate = local_midnight_utc.replace(hour=peak_h, minute=0, second=0, microsecond=0)
        if candidate < local_midnight_utc:
            candidate += timedelta(days=1)
        peak_utc_dt = candidate

        # Actual daily max: max temp across ALL obs on this local date
        actual_max = max(o["temp_c"] for o in day_obs)

        for h_before in PHASES_H:
            eval_utc_dt = peak_utc_dt - timedelta(hours=h_before)
            if eval_utc_dt < local_midnight_utc:
                continue  # phase is before local midnight — skip (not meaningful)

            # Observations from local midnight up to eval_utc_dt
            prior = [o for o in day_obs
                     if local_midnight_utc <= o["utc_dt"] <= eval_utc_dt]
            if not prior:
                continue

            run_max = max(o["temp_c"] for o in prior)
            # Closest obs to eval_utc_dt for current temp + sky
            closest = min(prior, key=lambda o: abs((o["utc_dt"] - eval_utc_dt).total_seconds()))
            temp_c  = closest["temp_c"]
            sky     = closest["sky"]
            s_f     = sky_factors.get(sky, 0.60)

            eval_utc_hour = eval_utc_dt.hour
            rise_tbl  = CITY_REMAINING_RISE.get(slug, {}).get(month, {})
            delta_rem = rise_tbl.get(eval_utc_hour, 0.0)
            mu_nc     = max(run_max, temp_c + delta_rem * s_f)

            results[h_before].append(mu_nc - actual_max)

    return results


def analyse_city(
    city_name: str, icao: str, slug: str,
    date_start: date, date_end: date,
) -> dict:
    obs = fetch_asos(icao, date_start, date_end)
    if not obs:
        return {"city": city_name, "icao": icao, "slug": slug, "n_days": 0}

    utc_offset_h = ICAO_UTC_OFFSET_H.get(icao, 0)
    results = daily_nowcast_errors(obs, slug, utc_offset_h)

    out = {"city": city_name, "icao": icao, "slug": slug}
    n_days = min(len(v) for v in results.values()) if results else 0
    out["n_days"] = n_days

    month_now = date_end.month
    sigma_base = CITY_SIGMA_C.get(slug, {}).get(month_now, 1.0)

    for h in PHASES_H:
        errs = results[h]
        if not errs:
            out[f"mae_{h}h"]  = None
            out[f"bias_{h}h"] = None
            out[f"w1s_{h}h"]  = None
            continue
        mae  = sum(abs(e) for e in errs) / len(errs)
        bias = sum(errs) / len(errs)
        w1s  = sum(1 for e in errs if abs(e) <= sigma_base) / len(errs)
        out[f"mae_{h}h"]  = mae
        out[f"bias_{h}h"] = bias
        out[f"w1s_{h}h"]  = w1s

    return out


def fmt(val, fmt_str, fallback="    —  "):
    if val is None:
        return fallback
    return fmt_str.format(val)


def main():
    date_end   = date.today()
    date_start = date_end - timedelta(days=DAYS_BACK)

    print(f"\nMETAR NOWCAST RELIABILITY — T-6h / T-4h / T-2h before peak UTC")
    print(f"Data: Iowa State Mesonet ASOS  |  {date_start} → {date_end}  |  {len(CITIES)} cities")
    print(f"Formula: mu_nc = max(run_max, temp + ΔT_rem × sky_factor)  (CLR=1.0 OVC=0.08)")
    print(f"Error = mu_nc − actual_max  (positive = over-predicted)\n")

    all_results = []
    for i, (city_name, icao, slug) in enumerate(CITIES):
        print(f"  [{i+1:2d}/{len(CITIES)}] {city_name:<22} ({icao})...", end="", flush=True)
        r = analyse_city(city_name, icao, slug, date_start, date_end)
        print(f" {r['n_days']} days")
        all_results.append(r)
        time.sleep(SLEEP_S)

    # ── Print table ───────────────────────────────────────────────────────────
    has_rise = lambda s: bool(CITY_REMAINING_RISE.get(s))

    print()
    hdr = (f"{'City':<22} {'ICAO':<5} {'σ':>5}  "
           f"{'T-6h MAE':>9} {'bias':>6}  "
           f"{'T-4h MAE':>9} {'bias':>6}  "
           f"{'T-2h MAE':>9} {'bias':>6}  "
           f"{'w1σ@T-2':>7}  {'n':>4}  {'Rise':>4}")
    print(hdr)
    print("─" * len(hdr))

    # Sort: cities with data first (by T-2h MAE), then no-data at end
    all_results.sort(key=lambda r: (r.get("mae_2h") is None, r.get("mae_2h") or 99))

    for r in all_results:
        slug      = r["slug"]
        month_now = date_end.month
        sigma_b   = CITY_SIGMA_C.get(slug, {}).get(month_now)
        rise_mark = "✓" if has_rise(slug) else "—"
        print(
            f"{r['city']:<22} {r['icao']:<5} "
            f"{fmt(sigma_b, '{:5.3f}'):>5}  "
            f"{fmt(r.get('mae_6h'), '{:7.2f}°C'):>9} {fmt(r.get('bias_6h'), '{:+5.2f}'):>6}  "
            f"{fmt(r.get('mae_4h'), '{:7.2f}°C'):>9} {fmt(r.get('bias_4h'), '{:+5.2f}'):>6}  "
            f"{fmt(r.get('mae_2h'), '{:7.2f}°C'):>9} {fmt(r.get('bias_2h'), '{:+5.2f}'):>6}  "
            f"{fmt(r.get('w1s_2h'), '{:6.0%}'):>7}  "
            f"{r['n_days']:>4}  {rise_mark:>4}"
        )

    print()
    print("Columns:")
    print("  MAE      = mean|mu_nc − actual_max|  (lower = nowcast closer to truth)")
    print("  bias     = mean(mu_nc − actual_max)  (+ve = over-predicts; −ve = under-predicts)")
    print("  w1σ@T-2  = % of days where |T-2h error| < sigma_base (within NWP uncertainty floor)")
    print("  Rise     = ✓ if calibrated CITY_REMAINING_RISE table exists (else nowcast = run_max)")
    print()
    print("Interpretation guide:")
    print("  T-2h MAE < 0.5×σ_base  →  METAR strongly outperforms NWP at T-2h (use for exit decisions)")
    print("  T-6h MAE > σ_base      →  NWP still dominates at T-6h; METAR not yet reliable")
    print("  bias strongly negative  →  formula under-predicts (sky_factor too aggressive / no rise table)")
    print("  T-6h ≈ T-4h ≈ T-2h MAE →  formula not adding value (likely no rise table / flat profile)")

    # ── Per-city verdict ──────────────────────────────────────────────────────
    print()
    print("VERDICT PER CITY (T-2h MAE vs σ_base):")
    print(f"  {'City':<22}  {'T-2h MAE':>9}  {'σ_base':>7}  {'ratio':>6}  Verdict")
    print("  " + "─" * 65)
    for r in all_results:
        if r.get("mae_2h") is None:
            continue
        slug = r["slug"]
        month_now = date_end.month
        sigma_b = CITY_SIGMA_C.get(slug, {}).get(month_now, 1.0)
        mae2 = r["mae_2h"]
        ratio = mae2 / sigma_b
        if ratio < 0.5:
            verdict = "STRONG — METAR clearly beats NWP at T-2h"
        elif ratio < 0.9:
            verdict = "USEFUL — METAR provides information"
        elif ratio < 1.2:
            verdict = "MARGINAL — close to NWP baseline"
        else:
            verdict = "WEAK — METAR not reliable even at T-2h"
        print(f"  {r['city']:<22}  {mae2:>8.2f}°C  {sigma_b:>6.3f}°C  {ratio:>5.2f}×  {verdict}")


if __name__ == "__main__":
    main()
