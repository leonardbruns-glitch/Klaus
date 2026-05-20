"""
WeatherArb — Daily city temperature prediction market arbitrage.

Signal: compare Open-Meteo forecast (same source as wunderground resolution ±1-2°C)
vs Polymarket implied probability. Buy YES tokens where Poly price is significantly
below the forecast-implied probability.

Markets: "Will the highest temperature in [City] be [X°C/°F] on [Date]?"
Resolution: wunderground.com daily max temperature for each city station.

Edge validated: wallet 0xb40e89677d has $7,018 realized profit from 428 weather
positions, entering at 0.04-0.92 vs fair value. WR=42% vs ~20% random baseline.

Strategy:
  1. Scan weather events (tag=weather) every 30 minutes
  2. Extract city name from market title, look up coordinates
  3. Fetch Open-Meteo daily max temperature forecast (free, no API key)
  4. Model temp as Normal(forecast_mean, sigma=1.5°C)
  5. Buy YES token if Poly price < P(outcome) - EDGE_MIN
  6. Hold to resolution (daily markets resolve at local noon)
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from datetime import date, timedelta
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

GAMMA_BASE   = "https://gamma-api.polymarket.com"
METEO_BASE   = "https://api.open-meteo.com/v1/forecast"

EDGE_MIN     = 0.08    # minimum edge (fair_prob - poly_price) required to enter
STAKE_USD    = 25.0    # per market position
SIGMA_C      = 1.5     # forecast uncertainty std-dev in °C
SIGMA_F      = 2.7     # forecast uncertainty std-dev in °F
SCAN_INTERVAL_S = 1800 # scan every 30 minutes
MAX_POSITIONS    = 30  # max concurrent weather positions
DRY_RUN_LOG  = False  # set False to trade live

# City → (lat, lon) for Open-Meteo API
# Derived from observed Polymarket weather market cities
CITY_COORDS: dict[str, tuple[float, float]] = {
    "London":           (51.5085, -0.1257),
    "Paris":            (48.8567,  2.3508),
    "Seoul":            (37.5665, 126.9780),
    "Seattle":          (47.6062, -122.3321),
    "Sao Paulo":        (-23.5475, -46.6361),
    "Buenos Aires":     (-34.6118, -58.4173),
    "Ankara":           (39.9199,  32.8543),
    "Wellington":       (-41.2866, 174.7756),
    "Lucknow":          (26.8467,  80.9462),
    "Munich":           (48.1374,  11.5755),
    "Tokyo":            (35.6895, 139.6917),
    "Beijing":          (39.9042, 116.4074),
    "Shanghai":         (31.2304, 121.4737),
    "Hong Kong":        (22.3193, 114.1694),
    "Singapore":        (1.3521,  103.8198),
    "Dubai":            (25.2048,  55.2708),
    "Sydney":           (-33.8688, 151.2093),
    "Miami":            (25.7617,  -80.1918),
    "Los Angeles":      (34.0522, -118.2437),
    "New York City":    (40.7128,  -74.0060),
    "Chicago":          (41.8781,  -87.6298),
    "Houston":          (29.7604,  -95.3698),
    "Denver":           (39.7392, -104.9903),
    "Phoenix":          (33.4484, -112.0740),
    "Atlanta":          (33.7490,  -84.3880),
    "Berlin":           (52.5200,  13.4050),
    "Amsterdam":        (52.3676,   4.9041),
    "Helsinki":         (60.1695,  24.9354),
    "Stockholm":        (59.3293,  18.0686),
    "Oslo":             (59.9139,  10.7522),
    "Copenhagen":       (55.6761,  12.5683),
    "Vienna":           (48.2082,  16.3738),
    "Zurich":           (47.3769,   8.5417),
    "Brussels":         (50.8503,   4.3517),
    "Madrid":           (40.4168,  -3.7038),
    "Barcelona":        (41.3851,   2.1734),
    "Rome":             (41.9028,  12.4964),
    "Milan":            (45.4654,   9.1859),
    "Warsaw":           (52.2297,  21.0122),
    "Prague":           (50.0755,  14.4378),
    "Budapest":         (47.4979,  19.0402),
    "Bucharest":        (44.4268,  26.1025),
    "Athens":           (37.9838,  23.7275),
    "Istanbul":         (41.0082,  28.9784),
    "Moscow":           (55.7558,  37.6173),
    "Riyadh":           (24.6877,  46.7219),
    "Jeddah":           (21.3891,  39.8579),
    "Cairo":            (30.0444,  31.2357),
    "Lagos":            (6.5244,    3.3792),
    "Nairobi":          (-1.2921,  36.8219),
    "Johannesburg":     (-26.2041,  28.0473),
    "Mumbai":           (19.0760,  72.8777),
    "Delhi":            (28.7041,  77.1025),
    "Karachi":          (24.8607,  67.0011),
    "Dhaka":            (23.8103,  90.4125),
    "Bangkok":          (13.7563, 100.5018),
    "Jakarta":          (-6.2088, 106.8456),
    "Manila":           (14.5995, 120.9842),
    "Kuala Lumpur":     (3.1390,  101.6869),
    "Mexico City":      (19.4326,  -99.1332),
    "Bogota":           (4.7110,   -74.0721),
    "Lima":             (-12.0464, -77.0428),
    "Santiago":         (-33.4489, -70.6693),
    "Wuhan":            (30.5928,  114.3055),
    "Chengdu":          (30.5728,  104.0668),
    "Guangzhou":        (23.1291,  113.2644),
    "Shenzhen":         (22.5431,  114.0579),
    "Chongqing":        (29.4316,  106.9123),
    "Qingdao":          (36.0671,  120.3826),
}


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _outcome_prob(forecast_mean: float, lo: Optional[float], hi: Optional[float],
                  sigma: float) -> float:
    """
    P(lo <= daily_max <= hi) under Normal(forecast_mean, sigma).
    lo=None means unbounded below; hi=None means unbounded above.
    """
    p_hi = 1.0 if hi is None else _norm_cdf((hi + 0.5 - forecast_mean) / sigma)
    p_lo = 0.0 if lo is None else _norm_cdf((lo - 0.5 - forecast_mean) / sigma)
    return max(0.0, p_hi - p_lo)


def _parse_outcome(question: str) -> tuple[Optional[float], Optional[float], bool]:
    """
    Parse temperature outcome from market question.
    Returns (lo_celsius, hi_celsius, is_celsius).
    Returns (None, None, False) if unparseable.

    Handles patterns:
      "...be 19°C on..."          → exact 19°C range [18.5, 19.5]
      "...be 20°C or higher..."   → [20, None]
      "...be 15°C or below..."    → [None, 15]
      "...be between 88-89°F..."  → convert to Celsius
      "...be 84°F or higher..."   → convert
    """
    # Fahrenheit exact range "88-89°F"
    m = re.search(r'be (?:between )?(\d+)-(\d+)[°\s]*F', question, re.IGNORECASE)
    if m:
        lo_f, hi_f = float(m.group(1)), float(m.group(2))
        lo_c = (lo_f - 32) * 5 / 9
        hi_c = (hi_f - 32) * 5 / 9
        return lo_c, hi_c, False  # fahrenheit range, already in Celsius

    # Fahrenheit "84°F or higher"
    m = re.search(r'be (\d+)[°\s]*F or higher', question, re.IGNORECASE)
    if m:
        lo_f = float(m.group(1))
        return (lo_f - 32) * 5 / 9, None, False

    # Fahrenheit "72°F or below" / "below 72°F"
    m = re.search(r'(?:be )?(\d+)[°\s]*F or below', question, re.IGNORECASE)
    if m:
        hi_f = float(m.group(1))
        return None, (hi_f - 32) * 5 / 9, False

    # Celsius exact: "be 19°C on"
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C (?:on|in)', question, re.IGNORECASE)
    if m:
        t = float(m.group(1))
        return t, t, True  # exact bucket [t-0.5, t+0.5]

    # Celsius "or higher / above"
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C or (?:higher|above)', question, re.IGNORECASE)
    if m:
        return float(m.group(1)), None, True

    # Celsius "or below"
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C or (?:below|lower)', question, re.IGNORECASE)
    if m:
        return None, float(m.group(1)), True

    return None, None, False


def _parse_city(title: str) -> Optional[str]:
    """Extract city name from event title like 'Highest temperature in London on May 20?'"""
    m = re.search(r'temperature in ([^?]+?) on', title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


class WeatherArb:
    def __init__(self, bot) -> None:
        self.bot = bot
        self._fired_tokens: set[str] = set()
        self._task: Optional[asyncio.Task] = None
        logger.info("[WA] WeatherArb strategy initialized stake=$%.0f edge_min=%.2f",
                    STAKE_USD, EDGE_MIN)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_arb_loop")

    async def _loop(self) -> None:
        # First run after 60s (allow bot to initialize), then every 30 min
        await asyncio.sleep(60.0)
        while True:
            try:
                await self._scan()
            except Exception:
                logger.exception("[WA] scan error")
            await asyncio.sleep(SCAN_INTERVAL_S)

    async def _scan(self) -> None:
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        # Only trade tomorrow's markets — today's markets are partially resolved by the time
        # we scan (they end at noon local time; markets already show resolution direction).
        target_dates = {tomorrow}

        logger.info("[WA] scanning weather markets for tomorrow=%s", tomorrow)

        # Fetch all open weather events
        events = await self._fetch_weather_events()
        if not events:
            logger.warning("[WA] no weather events returned")
            return

        entries_made = 0
        for ev in events:
            city = _parse_city(ev.get("title", ""))
            if not city or city not in CITY_COORDS:
                continue

            lat, lon = CITY_COORDS[city]

            # Only process markets resolving today or tomorrow
            markets = []
            for m in ev.get("markets", []):
                if m.get("endDate", "")[:10] not in target_dates: continue
                if m.get("closed", False): continue
                if not m.get("conditionId") or not m.get("clobTokenIds"): continue
                prices_raw = m.get("outcomePrices", '["0"]')
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if float(prices[0]) <= 0.001: continue
                markets.append(m)
            if not markets:
                continue

            # Get forecast for this city (only once per city)
            forecast = await self._get_forecast(lat, lon, today, tomorrow)
            if not forecast:
                logger.debug("[WA] no forecast for %s", city)
                continue

            for mkt in markets:
                if entries_made >= MAX_POSITIONS:
                    break
                entry = await self._evaluate_market(city, mkt, forecast)
                if entry:
                    if await self._enter(mkt, entry["fair_prob"], entry["poly_price"], city):
                        entries_made += 1

        logger.info("[WA] scan done: %d entries made", entries_made)

    async def _evaluate_market(
        self, city: str, mkt: dict, forecast: dict
    ) -> Optional[dict]:
        """Return entry dict if this market has edge, else None."""
        question  = mkt.get("question", "")
        prices_raw = mkt.get("outcomePrices", '["0.5", "0.5"]')
        prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        poly_yes   = float(prices[0])  # YES token price = P(outcome)
        token_ids = mkt.get("clobTokenIds", [])
        end_date  = mkt.get("endDate", "")[:10]

        if not token_ids or poly_yes <= 0.005:
            return None

        token_id = token_ids[0]  # YES token
        if token_id in self._fired_tokens:
            return None

        lo_c, hi_c, is_celsius = _parse_outcome(question)
        if lo_c is None and hi_c is None:
            return None

        forecast_mean = forecast.get(end_date)
        if not forecast_mean:
            return None

        sigma = SIGMA_C if is_celsius else SIGMA_F
        fair_prob = _outcome_prob(forecast_mean, lo_c, hi_c, sigma)

        edge = fair_prob - poly_yes
        if edge < EDGE_MIN:
            return None

        logger.info("[WA] CANDIDATE %s %s poly=%.3f fair=%.3f edge=%.3f %s",
                    city, end_date, poly_yes, fair_prob, edge, question[:55])

        return {
            "token_id":   token_id,
            "condition_id": mkt.get("conditionId", ""),
            "poly_price": poly_yes,
            "fair_prob":  fair_prob,
            "edge":       edge,
            "question":   question,
            "end_date":   end_date,
        }

    async def _enter(self, mkt: dict, fair_prob: float, poly_price: float,
                     city: str) -> bool:
        token_id  = mkt["clobTokenIds"][0]
        cid       = mkt.get("conditionId", "")
        question  = mkt.get("question", "")
        end_date  = mkt.get("endDate", "?")[:10]
        neg_risk  = mkt.get("negRisk", True)

        self._fired_tokens.add(token_id)

        logger.info("[WA] ENTER city=%s date=%s poly=%.3f fair=%.3f stake=$%.0f%s",
                    city, end_date, poly_price, fair_prob, STAKE_USD,
                    " [DRY]" if DRY_RUN_LOG else "")
        logger.info("[WA]   q=%s", question[:70])

        if DRY_RUN_LOG:
            return True

        try:
            from strategy.momentum import Direction as Dir
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=poly_price,
                stake_usd=STAKE_USD,
                direction=Dir.BUY_YES,
                neg_risk=neg_risk,
                fast_fail=True,
            )
            from execution.order_manager import OrderStatus
            if fill.status == OrderStatus.FILLED and fill.total_size > 0:
                self.bot.risk.open_position(
                    token_id=token_id,
                    condition_id=cid,
                    asset="WEATHER",
                    direction="UP",
                    side="YES",
                    shares=fill.total_size,
                    entry_price=fill.avg_price,
                    stake_usd=STAKE_USD,
                    bond_entry_class="WEATHER_ARB",
                    bond_outcome_direction="up",
                    window_end_ts=0,
                )
                logger.info("[WA] FILLED %s shares=%.1f @ %.4f",
                            question[:45], fill.total_size, fill.avg_price)
                return True
            else:
                self._fired_tokens.discard(token_id)
                logger.warning("[WA] fill failed %s: %s",
                               city, getattr(fill, "error", "?"))
                return False
        except Exception:
            self._fired_tokens.discard(token_id)
            logger.exception("[WA] enter error %s", city)
            return False

    async def _fetch_weather_events(self) -> list[dict]:
        url = f"{GAMMA_BASE}/events?closed=false&limit=200&tag_slug=weather"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    return await resp.json()
        except Exception as e:
            logger.debug("[WA] events fetch error: %s", e)
            return []

    async def _get_forecast(
        self, lat: float, lon: float, today: str, tomorrow: str
    ) -> Optional[dict[str, float]]:
        """Return dict {date_str: forecast_max_celsius} for today+tomorrow."""
        url = (
            f"{METEO_BASE}?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max&temperature_unit=celsius&forecast_days=2"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            daily  = data.get("daily", {})
            dates  = daily.get("time", [])
            maxes  = daily.get("temperature_2m_max", [])
            result = {}
            for d, mx in zip(dates, maxes):
                if mx is not None and d in (today, tomorrow):
                    result[d] = float(mx)
            return result if result else None
        except Exception as e:
            logger.debug("[WA] forecast error lat=%.2f lon=%.2f: %s", lat, lon, e)
            return None
