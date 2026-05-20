"""
60-day sigma calibration check for weather_arb.py.

Fetches resolved Polymarket weather markets from the last 60 days, replays our
Gaussian model fair_prob vs the CLOB price at open, and computes WR by ask band.

If the [0.27, 0.50) ask band shows WR > break_even with n >= 100, optionally
flips BRACKET_ENABLED = True in strategy/weather_arb.py.

Usage:
    python3 analysis/run_sigma_calibration_check.py           # report only
    python3 analysis/run_sigma_calibration_check.py --apply   # flip BRACKET_ENABLED if warranted

Break-even WR for a bucket = ask_midpoint (e.g. 0.385 for [0.27,0.50))
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

# ── CONFIG ───────────────────────────────────────────────────────────────────
GAMMA_BASE      = "https://gamma-api.polymarket.com"
CLOB_BASE       = "https://clob.polymarket.com"
ARCHIVE_URL     = "https://archive-api.open-meteo.com/v1/archive"
METEO_BASE      = "https://api.open-meteo.com/v1/forecast"
DAYS_BACK       = 60
MIN_N           = 100           # minimum observations to act on a band
BAND_EDGES      = [0.01, 0.10, 0.27, 0.50, 0.75, 1.01]
WEATHER_ARB_PY  = Path(__file__).parent.parent / "strategy" / "weather_arb.py"
FORECAST_MODELS = (
    "gfs_seamless,icon_seamless,ecmwf_ifs025,gem_seamless,"
    "jma_seamless,ukmo_seamless,meteofrance_seamless"
)

# Station coordinates for our 7 cities (slug → lat/lon)
STATIONS = {
    "nyc":           {"lat": 40.7769, "lon": -73.8740},
    "chicago":       {"lat": 41.9742, "lon": -87.9073},
    "los-angeles":   {"lat": 33.9425, "lon": -118.4081},
    "miami":         {"lat": 25.7953, "lon": -80.2900},
    "san-francisco": {"lat": 37.6213, "lon": -122.3790},
    "tokyo":         {"lat": 35.5494, "lon": 139.7798},
    "london":        {"lat": 51.5048, "lon":   0.0495},
}

CITY_SLUG_RE = re.compile(
    r"\b(new york|nyc|chicago|los angeles|miami|san francisco|tokyo|london)\b",
    re.IGNORECASE,
)
SLUG_MAP = {
    "new york": "nyc", "nyc": "nyc", "chicago": "chicago",
    "los angeles": "los-angeles", "miami": "miami",
    "san francisco": "san-francisco", "tokyo": "tokyo", "london": "london",
}

OUTCOME_RE = re.compile(r"(?:above|at least|at most|below|between)?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)


# ── HELPERS ──────────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _outcome_prob(mu: float, lo: Optional[float], hi: Optional[float], sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    lo_z = (lo - 0.5 - mu) / sigma if lo is not None else -10.0
    hi_z = (hi + 0.5 - mu) / sigma if hi is not None else  10.0
    return max(0.0, min(1.0, _norm_cdf(hi_z) - _norm_cdf(lo_z)))


def _parse_outcome(question: str) -> tuple[Optional[float], Optional[float]]:
    q = question.lower()
    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", q)]
    if not nums:
        return None, None
    if "between" in q and len(nums) >= 2:
        return min(nums[:2]), max(nums[:2])
    if "above" in q or "at least" in q:
        return nums[0], None
    if "below" in q or "at most" in q or "under" in q:
        return None, nums[0]
    return nums[0], nums[0]  # exact


def _city_slug(title: str) -> Optional[str]:
    m = CITY_SLUG_RE.search(title)
    if not m:
        return None
    return SLUG_MAP.get(m.group(0).lower())


def _band_label(ask: float) -> Optional[str]:
    for i in range(len(BAND_EDGES) - 1):
        if BAND_EDGES[i] <= ask < BAND_EDGES[i + 1]:
            return f"[{BAND_EDGES[i]:.2f},{BAND_EDGES[i+1]:.2f})"
    return None


# ── FETCH HELPERS ─────────────────────────────────────────────────────────────

async def fetch_resolved_weather_markets(sess: aiohttp.ClientSession, days: int) -> list[dict]:
    """Fetch resolved weather markets from Gamma — walk pagination."""
    markets = []
    offset = 0
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    while True:
        url = (f"{GAMMA_BASE}/markets?closed=true&tag_slug=weather"
               f"&limit=200&offset={offset}")
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                break
            page = await r.json()
        if not page:
            break
        fresh = [m for m in page if m.get("endDate", "")[:10] >= cutoff]
        markets.extend(fresh)
        if len(fresh) < len(page):
            break
        offset += len(page)
    return markets


async def fetch_clob_open_price(sess: aiohttp.ClientSession, token_id: str) -> Optional[float]:
    """Fetch earliest CLOB trade price as proxy for 'open ask'."""
    url = f"{CLOB_BASE}/trades?token_id={token_id}&limit=1&sort=ASC"
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        trades = data if isinstance(data, list) else data.get("data", [])
        if trades:
            return float(trades[0].get("price", 0))
    except Exception:
        pass
    return None


async def fetch_model_forecast(
    sess: aiohttp.ClientSession, lat: float, lon: float, target_date: str
) -> Optional[float]:
    """Fetch 1-day-ahead ensemble mean forecast for target_date."""
    prev = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    url = (
        f"{METEO_BASE}?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&daily=temperature_2m_max&temperature_unit=celsius"
        f"&start_date={prev}&end_date={target_date}"
        f"&models={FORECAST_MODELS}"
    )
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        if target_date not in dates:
            return None
        idx = dates.index(target_date)
        temp_keys = [k for k in daily if "temperature_2m_max" in k]
        vals = [daily[k][idx] for k in temp_keys if idx < len(daily[k]) and daily[k][idx] is not None]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


async def fetch_archive_actual(
    sess: aiohttp.ClientSession, lat: float, lon: float, target_date: str
) -> Optional[float]:
    url = (
        f"{ARCHIVE_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&daily=temperature_2m_max&temperature_unit=celsius"
        f"&start_date={target_date}&end_date={target_date}"
    )
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        daily = data.get("daily", {})
        temps = daily.get("temperature_2m_max", [])
        return float(temps[0]) if temps and temps[0] is not None else None
    except Exception:
        return None


# ── CORE ANALYSIS ─────────────────────────────────────────────────────────────

async def run(apply: bool) -> None:
    print(f"\nWeather Arb Sigma Calibration Check — last {DAYS_BACK} days")
    print("=" * 60)

    band_wins:   dict[str, int] = defaultdict(int)
    band_total:  dict[str, int] = defaultdict(int)
    band_edge_sum: dict[str, float] = defaultdict(float)

    async with aiohttp.ClientSession() as sess:
        markets = await fetch_resolved_weather_markets(sess, DAYS_BACK)
        print(f"Fetched {len(markets)} resolved weather markets\n")

        for mkt in markets:
            slug = _city_slug(mkt.get("title", ""))
            if not slug or slug not in STATIONS:
                continue
            target_date = mkt.get("endDate", "")[:10]
            if not target_date:
                continue

            # Skip markets with no resolution data
            res_prices = mkt.get("outcomePrices")
            if not res_prices:
                continue
            try:
                prices = json.loads(res_prices) if isinstance(res_prices, str) else res_prices
                resolved_yes = float(prices[0]) > 0.9  # final price ≈ 1.0 → YES won
            except Exception:
                continue

            question = mkt.get("question", "")
            lo_c, hi_c = _parse_outcome(question)
            if lo_c is None and hi_c is None:
                continue

            # Get CLOB open price (what we would have paid)
            token_ids = mkt.get("clobTokenIds", [])
            if isinstance(token_ids, str):
                try:
                    token_ids = json.loads(token_ids)
                except Exception:
                    continue
            if not token_ids:
                continue
            clob_price = await fetch_clob_open_price(sess, token_ids[0])
            if clob_price is None or clob_price < 0.01 or clob_price >= 1.0:
                continue

            band = _band_label(clob_price)
            if band is None:
                continue

            # Fetch model forecast for that date
            lat = STATIONS[slug]["lat"]
            lon = STATIONS[slug]["lon"]
            mu = await fetch_model_forecast(sess, lat, lon, target_date)
            if mu is None:
                continue

            # Compute model fair prob (sigma = 1.5 as conservative default)
            fair_p = _outcome_prob(mu, lo_c, hi_c, 1.5)
            edge   = fair_p - clob_price

            band_total[band] += 1
            if resolved_yes:
                band_wins[band] += 1
            band_edge_sum[band] += edge

    # ── REPORT ───────────────────────────────────────────────────────────────
    print(f"{'Band':<18} {'N':>5} {'WR':>7} {'Break-even':>11} {'Avg Edge':>9} {'Action'}")
    print("-" * 65)

    flip_bracket = False
    for i in range(len(BAND_EDGES) - 1):
        band = f"[{BAND_EDGES[i]:.2f},{BAND_EDGES[i+1]:.2f})"
        n    = band_total[band]
        if n == 0:
            print(f"{band:<18} {'—':>5}")
            continue
        wr   = band_wins[band] / n
        mid  = (BAND_EDGES[i] + BAND_EDGES[i + 1]) / 2.0
        bev  = mid  # at fair odds, WR = ask = break-even
        avg_edge = band_edge_sum[band] / n
        n_flag   = "" if n >= MIN_N else f" (n<{MIN_N})"
        action   = "—"

        if band == f"[{0.27:.2f},{0.50:.2f})" and n >= MIN_N and wr > bev:
            action = "FLIP BRACKET_ENABLED=True" if apply else "→ warrant BRACKET_ENABLED=True"
            flip_bracket = True

        print(f"{band:<18} {n:>5} {wr:>7.1%} {bev:>11.1%} {avg_edge:>+9.3f}  {action}{n_flag}")

    # ── APPLY ────────────────────────────────────────────────────────────────
    if apply and flip_bracket:
        src = WEATHER_ARB_PY.read_text()
        if "BRACKET_ENABLED = False" in src:
            updated = src.replace("BRACKET_ENABLED = False", "BRACKET_ENABLED = True", 1)
            WEATHER_ARB_PY.write_text(updated)
            print(f"\n✓ Flipped BRACKET_ENABLED = True in {WEATHER_ARB_PY}")
        elif "BRACKET_ENABLED = True" in src:
            print("\n✓ BRACKET_ENABLED already True — no change.")
        else:
            print("\n⚠ Could not locate BRACKET_ENABLED in weather_arb.py — edit manually.")
    elif apply and not flip_bracket:
        print(f"\n— n<{MIN_N} or WR below break-even for [0.27,0.50) band; BRACKET_ENABLED unchanged.")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weather arb sigma calibration check")
    parser.add_argument("--apply", action="store_true",
                        help="Flip BRACKET_ENABLED=True in weather_arb.py if warranted")
    args = parser.parse_args()
    asyncio.run(run(args.apply))
