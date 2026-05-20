#!/usr/bin/env python3
"""
True signal validation: replay our model against real resolved Polymarket markets.

Resolution source: Polymarket uses WunderGround (WU) data, specifically the daily
highest temperature for the exact ICAO station in the market description (e.g., EGLC
for London), rounded to whole degrees Celsius. Our model must be validated against
this same source, not against generic reanalysis data.

For each resolved weather market (last N days):
  1. Fetch resolved markets + winner flags from Gamma API (no auth needed)
  2. Fetch realistic entry prices from CLOB price history
  3. Fetch what Open-Meteo actually predicted the day before (historical forecast API)
  4. Fetch actual WU temperature (Playwright scraper — same source as Polymarket resolution)
     Falls back to Open-Meteo reanalysis archive if Playwright is unavailable.
  5. Run the exact same model logic (sigma tables from weather_arb.py)
  6. Report:
       - Forecast accuracy vs WU actual: MAE, RMSE, % within ±1σ, ±2σ
       - Calibration: per fair_prob bucket, realized win rate
       - Strategy sim: n_entries, WR, net EV at stake=$25
       - Rounding impact: how often does WU rounding flip a bucket boundary?

Usage:
    python3 -m analysis.validate_weather_signals --days 30
    python3 -m analysis.validate_weather_signals --days 60 --cities nyc,london,tokyo
    python3 -m analysis.validate_weather_signals --days 30 --verbose
    python3 -m analysis.validate_weather_signals --days 30 --no-wu  # skip Playwright, use archive
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

# ── path setup (run from /root/Klaus or as module) ───────────────────────────
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.weather.backtest import (
    MarketView,
    discover_resolved,
    attach_entry_prices,
    attach_resolved_highs,
    _bucket_prob_normal,
    MIN_EDGE,
)
from analysis.weather.stations import STATIONS

# ── import our live model's sigma tables directly ────────────────────────────
from strategy.weather_arb import (
    CITY_SIGMA_C,
    SIGMA_C_DEFAULT,
    SIGMA_F_DEFAULT,
    EDGE_MIN,
    ASK_BAND_LO,
    ASK_BAND_HI,
    FORECAST_MODELS,
    CITY_COORDS,
)

STAKE = 25.0  # match live stake
USER_AGENT = "Klaus-WeatherValidator/1.0 (research)"

# Cities to validate by default (all 7 validated stations)
ALL_CITIES = list(STATIONS.keys())

# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ── Historical forecast fetcher ───────────────────────────────────────────────

HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

def fetch_historical_forecast(lat: float, lon: float, target_day: date,
                               models: str = FORECAST_MODELS) -> Optional[float]:
    """
    Fetch what Open-Meteo predicted for target_day's max temperature.
    Uses the historical forecast archive — approximates the day-before model run.
    Returns ensemble mean in Celsius, or None on failure.
    """
    day_str = target_day.isoformat()
    url = (
        f"{HIST_FORECAST_URL}"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&start_date={day_str}&end_date={day_str}"
        f"&daily=temperature_2m_max"
        f"&temperature_unit=celsius"
        f"&models={models}"
        f"&timezone=UTC"
    )
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"    [hist-forecast] error: {e}", file=sys.stderr)
        return None

    # Multi-model response: all data in one 'daily' block with suffixed keys
    # e.g. temperature_2m_max_gfs_seamless, temperature_2m_max_ecmwf_ifs025
    # Single-model response: temperature_2m_max (no suffix)
    temps: list[float] = []
    daily = data.get("daily", {})
    for key, values in daily.items():
        if not key.startswith("temperature_2m_max"):
            continue
        if isinstance(values, list):
            for v in values:
                if v is not None:
                    temps.append(float(v))

    if not temps:
        return None
    return sum(temps) / len(temps)


# ── Actual temperature: WU scraper (primary) + archive fallback ───────────────

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

def fetch_actual_temperature_archive(lat: float, lon: float, target_day: date) -> Optional[float]:
    """
    Fallback: Open-Meteo reanalysis archive. Close to station observations but NOT
    the exact WU station reading that Polymarket uses for resolution. Typical
    delta vs WU is <0.5°C, but rounding to whole °C can matter at bucket edges.
    """
    day_str = target_day.isoformat()
    url = (
        f"{ARCHIVE_URL}"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&start_date={day_str}&end_date={day_str}"
        f"&daily=temperature_2m_max"
        f"&temperature_unit=celsius"
        f"&timezone=UTC"
    )
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"    [archive] error: {e}", file=sys.stderr)
        return None

    daily = data.get("daily", {})
    values = daily.get("temperature_2m_max", [])
    for v in values:
        if v is not None:
            return float(v)
    return None


async def _attach_wu_temps_async(markets: list[MarketView]) -> None:
    """Run attach_resolved_highs (Playwright + WU scraper) in an async context."""
    await attach_resolved_highs(markets)


def attach_wu_temps(markets: list[MarketView]) -> bool:
    """
    Populate mkt.resolved_high_c on each market by scraping WunderGround via
    Playwright. Returns True on success, False if Playwright is unavailable.

    WU is the exact resolution source Polymarket uses: daily highest temperature
    at the specific ICAO station, rounded to whole degrees Celsius.
    """
    try:
        import asyncio
        asyncio.run(_attach_wu_temps_async(markets))
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"  [WU scraper] failed: {e}", file=sys.stderr)
        return False


# ── Sigma lookup ──────────────────────────────────────────────────────────────

def get_sigma_c(city_slug: str, month: int) -> float:
    """Return forecast residual sigma in Celsius for city+month from our live model."""
    city_table = CITY_SIGMA_C.get(city_slug)
    if city_table:
        return city_table.get(month, SIGMA_C_DEFAULT)
    return SIGMA_C_DEFAULT


def sigma_in_market_unit(sigma_c: float, unit: str) -> float:
    if unit == "F":
        return sigma_c * (SIGMA_F_DEFAULT / SIGMA_C_DEFAULT)
    return sigma_c


def forecast_in_market_unit(forecast_c: float, unit: str) -> float:
    if unit == "F":
        return forecast_c * 9.0 / 5.0 + 32.0
    return forecast_c


def actual_in_market_unit(actual_c: float, unit: str) -> float:
    return forecast_in_market_unit(actual_c, unit)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    city: str
    valid_day: date
    bucket: str
    entry_price: float       # CLOB ask price at realistic entry
    forecast_mu_c: float     # what Open-Meteo predicted (Celsius)
    actual_temp_c: float     # actual observed temperature (Celsius)
    sigma_c: float           # our model's sigma
    fair_prob: float         # model's P(bucket wins)
    edge: float              # fair_prob - entry_price
    would_enter: bool        # passes EDGE_MIN + ASK_BAND filter
    won: bool                # did this bucket resolve YES


# ── Main validation ───────────────────────────────────────────────────────────

def run_validation(cities: list[str], days_back: int, verbose: bool = False,
                   use_wu: bool = True, fetch_clob: bool = True) -> tuple[list[TradeRecord], str]:
    """
    Returns (records, temp_source) where temp_source is 'wu' or 'archive'.
    The WU source matches Polymarket's resolution (whole-°C rounding, exact station).
    Archive is a fallback if Playwright is unavailable.
    """
    all_records: list[TradeRecord] = []
    temp_source = "unknown"

    for city_slug in cities:
        station = STATIONS[city_slug]
        print(f"\n{'─'*60}")
        print(f"  {city_slug.upper()}  ({station.icao}, unit={station.unit})")
        print(f"{'─'*60}")

        markets = discover_resolved(city_slug, days_back)
        if not markets:
            print("  no resolved markets found")
            continue
        print(f"  found {len(markets)} resolved market-days")

        # Attach realistic CLOB entry prices (slow: ~1 HTTP req per bucket)
        if fetch_clob:
            print("  fetching CLOB price history...", flush=True)
            attach_entry_prices(markets)
        else:
            print("  skipping CLOB (--no-clob): strategy sim disabled, model accuracy only")

        # Attach actual temperatures from WU (resolution source) or archive (fallback)
        wu_ok = False
        if use_wu:
            print("  scraping WunderGround (resolution source)...", flush=True)
            wu_ok = attach_wu_temps(markets)
            if wu_ok:
                temp_source = "wu"
                print("  ✓ WU temperatures loaded")
            else:
                print("  ✗ WU scraper failed — falling back to Open-Meteo archive")

        for mkt in markets:
            # Fetch historical forecast (what model would have said day before)
            time.sleep(0.3)
            forecast_c = fetch_historical_forecast(station.lat, station.lon, mkt.valid_day)
            if forecast_c is None:
                if verbose:
                    print(f"  {mkt.valid_day}: no historical forecast, skipping")
                continue

            # Actual temperature: WU (from attach_resolved_highs) or archive fallback
            if wu_ok and mkt.resolved_high_c is not None:
                actual_c = float(mkt.resolved_high_c)
                # WU already rounds to whole °C for C-unit markets
            else:
                time.sleep(0.3)
                actual_c = fetch_actual_temperature_archive(station.lat, station.lon, mkt.valid_day)
                if temp_source == "unknown":
                    temp_source = "archive"
                if actual_c is None:
                    if verbose:
                        print(f"  {mkt.valid_day}: no temperature data, skipping")
                    continue

            month = mkt.valid_day.month
            sigma_c = get_sigma_c(city_slug, month)
            sigma_mu = sigma_in_market_unit(sigma_c, station.unit)
            forecast_mu = forecast_in_market_unit(forecast_c, station.unit)
            error_c = forecast_c - actual_c  # positive = model predicted too warm

            winning_bucket = next((b for b in mkt.buckets if b.is_winner), None)

            # WU rounding note: for C-unit markets, resolution is whole °C.
            # Check if the forecast is within 0.5°C of a bucket boundary (rounding-sensitive).
            if winning_bucket:
                boundary_proximity = min(
                    abs(forecast_c - b) for b in [winning_bucket.lo_inclusive,
                                                   winning_bucket.hi_exclusive]
                    if abs(b) < 1e6  # skip ±inf
                )
            else:
                boundary_proximity = None

            if verbose:
                print(
                    f"  {mkt.valid_day}  forecast={forecast_c:.1f}°C  "
                    f"actual={actual_c:.1f}°C (WU)  err={error_c:+.1f}°C  "
                    f"σ={sigma_c:.2f}°C  winner={winning_bucket.label if winning_bucket else 'NONE'}"
                )

            for bucket in mkt.buckets:
                if bucket.entry_price is None or bucket.entry_price <= 0.001:
                    continue

                fair_prob = _bucket_prob_normal(
                    bucket.lo_inclusive, bucket.hi_exclusive,
                    forecast_mu, sigma_mu,
                )
                edge = fair_prob - bucket.entry_price
                would_enter = (
                    edge >= EDGE_MIN and
                    ASK_BAND_LO <= bucket.entry_price < ASK_BAND_HI
                )

                all_records.append(TradeRecord(
                    city=city_slug,
                    valid_day=mkt.valid_day,
                    bucket=bucket.label,
                    entry_price=bucket.entry_price,
                    forecast_mu_c=forecast_c,
                    actual_temp_c=actual_c,
                    sigma_c=sigma_c,
                    fair_prob=round(fair_prob, 4),
                    edge=round(edge, 4),
                    would_enter=would_enter,
                    won=bucket.is_winner,
                ))

    return all_records, temp_source


# ── Report generation ─────────────────────────────────────────────────────────

def report(records: list[TradeRecord], temp_source: str = "unknown") -> None:
    if not records:
        print("\nNo records — check cities and days range.")
        return

    source_label = {
        "wu": "WunderGround (resolution source — exact match)",
        "archive": "Open-Meteo reanalysis archive (fallback — ~±0.5°C from WU)",
    }.get(temp_source, temp_source)

    print(f"\n{'═'*65}")
    print("  WEATHER SIGNAL VALIDATION REPORT")
    print(f"{'═'*65}")
    print(f"  Temperature source : {source_label}")
    print(f"  Total bucket-records: {len(records)}")

    # ── 1. Forecast accuracy ─────────────────────────────────────────────────
    errors = [r.forecast_mu_c - r.actual_temp_c for r in records]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e**2 for e in errors) / len(errors))
    bias = sum(errors) / len(errors)

    # Sigma-normalised errors (z-scores)
    z_scores = [(r.forecast_mu_c - r.actual_temp_c) / r.sigma_c for r in records]
    within_1sigma = sum(1 for z in z_scores if abs(z) <= 1.0) / len(z_scores)
    within_2sigma = sum(1 for z in z_scores if abs(z) <= 2.0) / len(z_scores)

    print(f"\n  FORECAST ACCURACY  (expected: MAE ~ σ/√π ≈ 0.8×σ)")
    print(f"  {'Metric':<30} {'Value':>10}")
    print(f"  {'─'*42}")
    print(f"  {'MAE (°C)':<30} {mae:>10.2f}")
    print(f"  {'RMSE (°C)':<30} {rmse:>10.2f}")
    print(f"  {'Bias (°C, + = warm)':<30} {bias:>+10.2f}")
    print(f"  {'% within ±1σ (expect 68%)':<30} {within_1sigma:>9.1%}")
    print(f"  {'% within ±2σ (expect 95%)':<30} {within_2sigma:>9.1%}")

    if within_1sigma < 0.55:
        print("  ⚠  σ is too tight — model overconfident; raises fair_prob above truth")
    elif within_1sigma > 0.80:
        print("  ⚠  σ is too wide — model underconfident; edge estimates are conservative")
    else:
        print("  ✓  σ calibration within acceptable range")

    # ── 2. Calibration by fair_prob bucket ───────────────────────────────────
    PROB_BANDS = [(0.0, 0.20), (0.20, 0.30), (0.30, 0.40), (0.40, 0.50),
                  (0.50, 0.60), (0.60, 0.70), (0.70, 1.0)]

    print(f"\n  CALIBRATION  (per fair_prob bucket → realized win rate)")
    print(f"  {'fair_prob range':<18} {'n':>5} {'realized WR':>12} {'expected WR':>12} {'diff':>8}")
    print(f"  {'─'*60}")
    any_data = False
    for lo, hi in PROB_BANDS:
        bucket_recs = [r for r in records if lo <= r.fair_prob < hi]
        if not bucket_recs:
            continue
        any_data = True
        n = len(bucket_recs)
        realized_wr = sum(1 for r in bucket_recs if r.won) / n
        expected_wr = sum(r.fair_prob for r in bucket_recs) / n
        diff = realized_wr - expected_wr
        flag = "  ⚠" if abs(diff) > 0.10 else ""
        print(f"  [{lo:.2f}, {hi:.2f})  {n:>14} {realized_wr:>11.1%} {expected_wr:>11.1%} {diff:>+7.1%}{flag}")
    if not any_data:
        print("  (no data)")

    # ── 3. Strategy simulation (would-enter filter) ──────────────────────────
    entries = [r for r in records if r.would_enter]
    print(f"\n  STRATEGY SIMULATION  (EDGE_MIN={EDGE_MIN}, ask=[{ASK_BAND_LO},{ASK_BAND_HI}))")
    print(f"  Bucket-records passing filter: {len(entries)} / {len(records)}")

    if entries:
        wins = sum(1 for r in entries if r.won)
        wr = wins / len(entries)
        net_pnl = sum(
            (1.0 - r.entry_price) * STAKE if r.won else -r.entry_price * STAKE
            for r in entries
        )
        avg_entry = sum(r.entry_price for r in entries) / len(entries)
        avg_fair = sum(r.fair_prob for r in entries) / len(entries)
        avg_edge = sum(r.edge for r in entries) / len(entries)
        ev_per_trade = net_pnl / len(entries)

        print(f"\n  {'Metric':<35} {'Value':>10}")
        print(f"  {'─'*47}")
        print(f"  {'n_entries':<35} {len(entries):>10}")
        print(f"  {'Win rate':<35} {wr:>9.1%}")
        print(f"  {'Avg entry price':<35} {avg_entry:>10.3f}")
        print(f"  {'Avg fair_prob':<35} {avg_fair:>10.3f}")
        print(f"  {'Avg edge':<35} {avg_edge:>10.3f}")
        print(f"  {'Net PnL (${:.0f} stake)':<35} ${net_pnl:>9.2f}".format(STAKE))
        print(f"  {'EV per trade':<35} ${ev_per_trade:>+9.2f}")

        break_even_wr = avg_entry
        print(f"\n  Break-even WR at avg entry:   {break_even_wr:.1%}")
        margin = wr - break_even_wr
        if margin >= 0:
            print(f"  ✓  Positive margin: {margin:+.1%} above break-even")
        else:
            print(f"  ✗  Negative margin: {margin:+.1%} — no edge at these prices")

    # ── 4. WU rounding impact ────────────────────────────────────────────────
    # WU rounds to whole °C. Check how often the forecast sits within 0.5°C of
    # a bucket boundary — these are the "coin-flip" cases where a 1°C error flips
    # the resolution. If this is frequent, our edge estimate is fragile.
    if temp_source == "wu":
        boundary_risk = []
        for r in records:
            # For C-unit markets, bucket boundaries are integers; for F, every 2°F
            # WU rounds C first, so the effective rounding is always whole °C.
            dist_from_actual = abs(r.forecast_mu_c - r.actual_temp_c)
            boundary_risk.append(dist_from_actual)
        if boundary_risk:
            risky = sum(1 for d in boundary_risk if d <= 0.5)
            print(f"\n  WU ROUNDING IMPACT  (resolution = whole °C)")
            print(f"  Forecast within ±0.5°C of actual: {risky}/{len(boundary_risk)} "
                  f"({risky/len(boundary_risk):.1%})  — these are boundary-sensitive entries")
            print(f"  (A 1°C WU rounding error can flip the bucket winner in these cases)")

    # ── 5. Per-city breakdown ────────────────────────────────────────────────
    cities_in_data = sorted(set(r.city for r in records))
    if len(cities_in_data) > 1:
        print(f"\n  PER-CITY SUMMARY")
        print(f"  {'city':<16} {'n_mkt':>6} {'n_entry':>8} {'WR':>8} {'EV/trade':>10}")
        print(f"  {'─'*55}")
        for city in cities_in_data:
            city_recs = [r for r in records if r.city == city]
            city_entries = [r for r in city_recs if r.would_enter]
            if not city_entries:
                print(f"  {city:<16} {len(city_recs):>6} {'—':>8} {'—':>8} {'—':>10}")
                continue
            c_wins = sum(1 for r in city_entries if r.won)
            c_wr = c_wins / len(city_entries)
            c_pnl = sum(
                (1.0 - r.entry_price) * STAKE if r.won else -r.entry_price * STAKE
                for r in city_entries
            )
            c_ev = c_pnl / len(city_entries)
            n_days = len(set(r.valid_day for r in city_recs))
            print(f"  {city:<16} {n_days:>6} {len(city_entries):>8} {c_wr:>7.1%} {c_ev:>+9.2f}$")

    print(f"\n{'═'*65}\n")

    # ── 6. Calibration verdict ───────────────────────────────────────────────
    if within_1sigma < 0.55:
        print("  VERDICT: σ is too tight. Our model overestimates fair_prob.")
        print("  Action: increase SIGMA_C_DEFAULT or recalibrate CITY_SIGMA_C.")
    elif within_1sigma > 0.80:
        print("  VERDICT: σ is too wide. Our model is conservative — we miss entries.")
        print("  Action: decrease SIGMA_C_DEFAULT or use ensemble spread directly.")
    else:
        calibration_ok = True
        if entries:
            realized = sum(1 for r in entries if r.won) / len(entries)
            expected = sum(r.fair_prob for r in entries) / len(entries)
            if realized >= expected * 0.85:
                print("  VERDICT: Calibration OK, edge appears real.")
            else:
                calibration_ok = False
                print("  VERDICT: Calibration gap — model overestimates edge.")
                print("  Realized WR significantly below model's fair_prob.")
        if calibration_ok:
            print("  Model appears well-calibrated on this sample.")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Validate weather signal against resolved markets")
    p.add_argument("--days", type=int, default=30, help="Days of history to fetch (default 30)")
    p.add_argument("--cities", type=str, default="",
                   help="Comma-separated city slugs (default: all 7 validated cities)")
    p.add_argument("--verbose", action="store_true", help="Print per-market details")
    p.add_argument("--no-wu", action="store_true",
                   help="Skip WU Playwright scraper, use Open-Meteo archive instead")
    p.add_argument("--no-clob", action="store_true",
                   help="Skip CLOB price history (fast, model accuracy only — no strategy sim)")
    args = p.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else ALL_CITIES
    invalid = [c for c in cities if c not in STATIONS]
    if invalid:
        print(f"Unknown cities: {invalid}. Valid: {list(STATIONS.keys())}")
        sys.exit(1)

    use_wu = not args.no_wu
    fetch_clob = not args.no_clob
    print(f"Weather signal validation — last {args.days} days, cities: {cities}")
    print(f"Temperature source: {'WU scraper (Playwright)' if use_wu else 'Open-Meteo archive'}")
    records, temp_source = run_validation(cities, args.days, verbose=args.verbose,
                                          use_wu=use_wu, fetch_clob=fetch_clob)
    report(records, temp_source)


if __name__ == "__main__":
    main()
