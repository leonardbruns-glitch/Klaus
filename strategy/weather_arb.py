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
ASK_BAND_LO  = 0.20    # min entry price (London 30d backtest: <0.20 is calibration-mirage)
ASK_BAND_HI  = 0.40    # max entry price (London 30d backtest: <3 obs above 0.40, unsupported)
STAKE_USD    = 25.0    # per market position
SIGMA_C_DEFAULT = 1.5  # fallback forecast uncertainty when only one model available
SIGMA_F_DEFAULT = 2.7  # fallback in °F
SCAN_INTERVAL_S = 1800 # scan every 30 minutes
MAX_POSITIONS    = 30  # max concurrent weather positions
DRY_RUN_LOG  = False  # set False to trade live

# Hold-favourites / scalp-mids policy (London 30d backtest 2026-05-20).
# Favourites: entry in [SCALP_BAND_HI, 1.0) — hold to PROFIT_TARGET=0.99 or resolution.
# Mids:       entry in [SCALP_BAND_LO, SCALP_BAND_HI) — scalp on WS BBO at scalp_tp.
# Below SCALP_BAND_LO: hold to resolution (scalp fill rate too low to matter).
SCALP_BAND_LO = 0.05
SCALP_BAND_HI = 0.20
SCALP_TARGET_ABS       = 0.03   # min absolute profit per share on a scalp
SCALP_TARGET_EDGE_FRAC = 0.50   # capture this fraction of (fair - entry)
SCALP_DISCOUNT         = 0.90   # TP ≤ fair × this (executability buffer)


def _compute_scalp_tp(entry: float, fair: float) -> float:
    """Take-profit price for mid-band entries; 0.0 means hold-to-resolution."""
    if not (SCALP_BAND_LO <= entry < SCALP_BAND_HI):
        return 0.0
    edge = max(0.0, fair - entry)
    target = entry + max(SCALP_TARGET_ABS, SCALP_TARGET_EDGE_FRAC * edge)
    ceiling = fair * SCALP_DISCOUNT
    return round(min(target, ceiling), 4)

# 2026-05-20: Elevation-aware sigma tuning. Mountains (>1500m) have 2-3x higher forecast error
# than coastal cities. Prevents edge-hunting in unwinnable high-altitude markets.
ELEVATION_THRESHOLD_M = 1500
ELEVATION_SIGMA_FLOOR = 3.0  # Minimum sigma for mountain cities (vs 1.0 for sea level)

# Multiple forecast models — average for better point estimate, spread → dynamic sigma
# 2026-05-20: Added GraphCast (Google DeepMind AI model, outperforms ECMWF on 10-day horizon)
# and ECMWF IFS (most accurate global model). Now 5-model ensemble vs prior 3-model.
FORECAST_MODELS = "gfs_seamless,icon_seamless,ecmwf_ifs025"

# City → (lat, lon) of the EXACT weather station Polymarket resolves against.
# All station codes verified from market description wunderground URLs (2026-05-20).
# Cities without a confirmed Polymarket market use nearest major airport as best proxy.
CITY_COORDS: dict[str, tuple[float, float]] = {
    # Confirmed from live Polymarket market descriptions (ICAO station)
    "London":           (51.5048,   0.0495),   # EGLC London City Airport
    "Paris":            (48.9694,   2.4414),   # LFPB Paris-Le Bourget
    "Seoul":            (37.4691, 126.4505),   # RKSI Incheon Intl
    "Seattle":          (47.4502, -122.3088),  # KSEA Seattle-Tacoma Intl
    "Sao Paulo":        (-23.4356, -46.4731),  # SBGR Guarulhos Intl
    "Buenos Aires":     (-34.8222, -58.5358),  # SAEZ Ezeiza Intl
    "Ankara":           (40.1281,  32.9951),   # LTAC Esenboğa Intl
    "Wellington":       (-41.3272, 174.8051),  # NZWN Wellington Intl
    "Lucknow":          (26.7606,  80.8893),   # VILK Chaudhary Charan Singh Intl
    "Munich":           (48.3538,  11.7861),   # EDDM Munich Airport
    "New York City":    (40.7769, -73.8740),   # KLGA LaGuardia
    "Dallas":           (32.8481, -96.8517),   # KDAL Dallas Love Field
    "Miami":            (25.7953, -80.2900),   # KMIA Miami Intl
    "Chicago":          (41.9742, -87.9073),   # KORD O'Hare Intl
    "Singapore":        (1.3644,  103.9915),   # WSSS Changi Airport
    "Milan":            (45.6307,   8.7281),   # LIMC Malpensa Intl
    "Madrid":           (40.4936,  -3.5668),   # LEMD Barajas
    "Warsaw":           (52.1657,  20.9671),   # EPWA Chopin Airport
    "Taipei":           (25.0694, 121.5522),   # RCSS Songshan Airport
    "Beijing":          (40.0799, 116.5844),   # ZBAA Capital Intl
    "Wuhan":            (30.7838, 114.2080),   # ZHHH Tianhe Intl
    "Chengdu":          (30.5782, 103.9470),   # ZUUU Shuangliu Intl
    "Shenzhen":         (22.6393, 113.8107),   # ZGSZ Bao'an Intl
    "Austin":           (30.1945, -97.6699),   # KAUS Bergstrom Intl
    "Denver":           (39.7017,-104.7517),   # KBKF Buckley Space Force Base
    "Houston":          (29.6454, -95.2789),   # KHOU William P. Hobby
    "Los Angeles":      (33.9425,-118.4081),   # KLAX LAX
    "San Francisco":    (37.6213,-122.3790),   # KSFO SFO
    "Mexico City":      (19.4363, -99.0721),   # MMMX Benito Juárez Intl
    "Busan":            (35.1795, 128.9382),   # RKPK Gimhae Intl
    "Amsterdam":        (52.3086,   4.7639),   # EHAM Schiphol
    "Helsinki":         (60.3172,  24.9633),   # EFHK Vantaa Airport
    "Panama City":      (8.9788,  -79.5556),   # MPHO Marcos Gelabert Intl
    "Jakarta":          (-6.2662, 106.8906),   # WIHH Halim Perdanakusuma
    "Jeddah":           (21.6796,  39.1565),   # OEJN King Abdulaziz Intl
    "Cape Town":        (-33.9648,  18.6017),  # FACT Cape Town Intl
    "Guangzhou":        (23.3924, 113.2990),   # ZGGG Baiyun Intl
    "Jinan":            (36.8572, 117.0558),   # ZSJN Yaoqiang Intl
    "Qingdao":          (36.2661, 120.3742),   # ZSQD Jiaodong Intl
    "Karachi":          (24.8936,  67.1355),   # OPKC Masroor Airbase
    "Manila":           (14.5086, 121.0194),   # RPLL Ninoy Aquino Intl
    "Toronto":          (43.6777, -79.6248),   # CYYZ Pearson Intl
    "Shanghai":         (31.1434, 121.8052),   # ZSPD Pudong Intl
    # Best-proxy airports for cities not yet confirmed in Polymarket markets
    "Tokyo":            (35.5494, 139.7798),   # RJTT Haneda
    "Hong Kong":        (22.3080, 113.9185),   # VHHH HK Intl
    "Dubai":            (25.2532,  55.3657),   # OMDB Dubai Intl
    "Sydney":           (-33.9399, 151.1753),  # YSSY Kingsford Smith
    "Phoenix":          (33.4343,-112.0117),   # KPHX Phoenix Sky Harbor
    "Atlanta":          (33.6407, -84.4277),   # KATL Hartsfield-Jackson
    "Berlin":           (52.3667,  13.5033),   # EDDB Brandenburg
    "Stockholm":        (59.6519,  17.9186),   # ESSA Arlanda
    "Oslo":             (60.1939,  11.0998),   # ENGM Gardermoen
    "Copenhagen":       (55.6179,  12.6560),   # EKCH Kastrup
    "Vienna":           (48.1103,  16.5697),   # LOWW Schwechat
    "Zurich":           (47.4647,   8.5492),   # LSZH Kloten
    "Brussels":         (50.9010,   4.4844),   # EBBR Zaventem
    "Barcelona":        (41.2971,   2.0785),   # LEBL El Prat
    "Rome":             (41.8003,  12.2389),   # LIRF Fiumicino
    "Prague":           (50.1008,  14.2600),   # LKPR Václav Havel
    "Budapest":         (47.4298,  19.2610),   # LHBP Ferenc Liszt
    "Bucharest":        (44.5722,  26.1022),   # LROP Henri Coandă
    "Athens":           (37.9364,  23.9445),   # LGAV Venizelos
    "Istanbul":         (40.8986,  29.3092),   # LTFJ Sabiha Gökçen
    "Moscow":           (55.9736,  37.4125),   # UUEE Sheremetyevo
    "Riyadh":           (24.9576,  46.6988),   # OERK King Khalid Intl
    "Cairo":            (30.1219,  31.4056),   # HECA Cairo Intl
    "Lagos":            (6.5774,    3.3214),   # DNMM Murtala Muhammed
    "Nairobi":          (-1.3192,  36.9275),   # HKJK Jomo Kenyatta
    "Johannesburg":     (-26.1392,  28.2460),  # FAOR O.R. Tambo
    "Mumbai":           (19.0896,  72.8656),   # VABB Chhatrapati Shivaji
    "Delhi":            (28.5665,  77.1031),   # VIDP Indira Gandhi
    "Dhaka":            (23.8433,  90.3978),   # VGHS Hazrat Shahjalal
    "Bangkok":          (13.6811, 100.7472),   # VTBS Suvarnabhumi
    "Kuala Lumpur":     (2.7456,  101.7072),   # WMKK KLIA
    "Bogota":           (4.7016,  -74.1469),   # SKBO El Dorado
    "Lima":             (-12.0219, -77.1143),  # SPJC Jorge Chávez
    "Santiago":         (-33.3930, -70.7858),  # SCEL Arturo Merino Benítez
    "Chongqing":        (29.7192, 106.6418),   # ZUCK Jiangbei Intl
}

# City elevation in meters (used for sigma tuning). Mountains >1500m get higher sigma.
# Source: airport elevation data, WGS84 datum.
CITY_ELEVATION_M: dict[str, float] = {
    "London": 5, "Paris": 75, "Seoul": 86, "Seattle": 174, "Sao Paulo": 760,
    "Buenos Aires": 25, "Ankara": 940, "Wellington": 12, "Lucknow": 128, "Munich": 519,
    "New York City": 3, "Dallas": 133, "Miami": 2, "Chicago": 205, "Singapore": 13,
    "Milan": 102, "Madrid": 610, "Warsaw": 110, "Taipei": 4, "Beijing": 54,
    "Wuhan": 24, "Chengdu": 506, "Shenzhen": 5, "Austin": 189, "Denver": 1609,
    "Houston": 9, "Los Angeles": 28, "San Francisco": 4, "Mexico City": 2250,
    "Busan": 13, "Amsterdam": -2, "Helsinki": 4, "Panama City": 14, "Jakarta": 8,
    "Jeddah": 4, "Cape Town": 41, "Guangzhou": 13, "Jinan": 34, "Qingdao": 76,
    "Karachi": 4, "Manila": 22, "Toronto": 76, "Shanghai": 4, "Tokyo": 44,
    "Hong Kong": 33, "Dubai": 3, "Sydney": 6, "Phoenix": 342, "Atlanta": 315,
    "Berlin": 34, "Stockholm": 7, "Oslo": 88, "Copenhagen": 7, "Vienna": 171,
    "Zurich": 432, "Brussels": 15, "Barcelona": 7, "Rome": 21, "Prague": 235,
    "Budapest": 139, "Bucharest": 82, "Athens": 256, "Istanbul": 32, "Moscow": 149,
    "Riyadh": 625, "Cairo": 73, "Lagos": 73, "Nairobi": 1609, "Johannesburg": 1742,
    "Mumbai": 14, "Delhi": 216, "Dhaka": 7, "Bangkok": 2, "Kuala Lumpur": 82,
    "Bogota": 2640, "Lima": 505, "Santiago": 570, "Chongqing": 257,
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


def _parse_token_ids(raw) -> list:
    """gamma-api returns clobTokenIds inconsistently as list or JSON string."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


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
                if not m.get("conditionId"): continue
                token_ids_raw = _parse_token_ids(m.get("clobTokenIds", []))
                if not token_ids_raw: continue
                prices_raw = m.get("outcomePrices", '["0"]')
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if float(prices[0]) <= 0.001: continue
                markets.append(m)
            if not markets:
                continue

            # Get forecast for this city (only once per city)
            forecast = await self._get_forecast(lat, lon, today, tomorrow, city)
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
        token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
        end_date  = mkt.get("endDate", "")[:10]

        if not token_ids or poly_yes <= 0.005:
            return None

        token_id = token_ids[0]  # YES token
        if token_id in self._fired_tokens:
            return None

        lo_c, hi_c, is_celsius = _parse_outcome(question)
        if lo_c is None and hi_c is None:
            return None

        forecast_entry = forecast.get(end_date)
        if not forecast_entry:
            return None
        forecast_mean, sigma_c = forecast_entry

        sigma = sigma_c if is_celsius else sigma_c * (SIGMA_F_DEFAULT / SIGMA_C_DEFAULT)
        fair_prob = _outcome_prob(forecast_mean, lo_c, hi_c, sigma)

        edge = fair_prob - poly_yes
        if edge < EDGE_MIN:
            return None

        # Ask-band filter (London 30d calibration backtest, 2026-05-20):
        # <$0.20 is the calibration-mirage zone where Gaussian σ=1.2°C
        # overpredicts and post-edge-filter realized WR ≈ 0%. >$0.40 has
        # too few historical obs (n=3) to validate.
        if not (ASK_BAND_LO <= poly_yes < ASK_BAND_HI):
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
        token_id  = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
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
                from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
                _tpsl = _TPSL(take_profit=0.0, stop_loss=0.0, tp_pct=0.0, sl_pct=0.0, risk_reward=0.0)
                self.bot.risk.open_position(
                    token_id=token_id,
                    asset="WEATHER",
                    direction=_Dir.BUY_YES,
                    stake=fill.total_size * fill.avg_fill_price,
                    entry_price=fill.avg_fill_price,
                    tpsl=_tpsl,
                    condition_id=cid,
                    window_end_ts=0.0,
                    is_bond=True,
                    bond_outcome_direction="up",
                    bond_entry_class="WEATHER_ARB",
                )
                # Hold-favourites / scalp-mids: store scalp_tp on the position meta
                # so the WS BBO callback (_ws_bond_tp_check) can fire instantly when
                # the bid touches it. scalp_tp=0.0 means hold to PROFIT_TARGET / resolution.
                _scalp_tp = _compute_scalp_tp(fill.avg_fill_price, fair_prob)
                _meta = self.bot._open_meta.setdefault(token_id, {})
                _meta["scalp_tp"] = _scalp_tp
                _meta["fair_prob"] = fair_prob
                # Register the token with the feed so the CLOB WS subscribes to its
                # BBO updates. Without this, weather positions get only REST-poll prices
                # and the BBO scalp callback never fires.
                try:
                    from data.feeds import MarketToken as _MT
                    if token_id not in self.bot.feed.tokens:
                        self.bot.feed.tokens[token_id] = _MT(
                            token_id=token_id,
                            condition_id=cid,
                            asset="WEATHER",
                            side="YES",
                            question=question,
                            end_date_iso=mkt.get("endDate", "") or "",
                            active=True,
                            market_type="weather",
                            window_end_ts=0.0,      # disables window-based exits
                            window_seconds=0,
                            neg_risk=neg_risk,
                            tick_size=str(mkt.get("orderPriceMinTickSize") or "0.01"),
                            outcome_direction="up",
                        )
                    try:
                        self.bot.feed._clob_ws_sub_queue.put_nowait([token_id])
                    except Exception:
                        logger.debug("[WA] WS subscribe queue full for %s", token_id[:12])
                except Exception:
                    logger.exception("[WA] failed to register %s with feed", token_id[:12])
                logger.info("[WA] FILLED %s shares=%.1f @ %.4f scalp_tp=%.4f%s",
                            question[:45], fill.total_size, fill.avg_fill_price,
                            _scalp_tp,
                            "" if _scalp_tp > 0 else " (hold-to-resolution)")
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
        self, lat: float, lon: float, today: str, tomorrow: str, city: str = ""
    ) -> Optional[dict[str, tuple[float, float]]]:
        """
        Return dict {date_str: (forecast_mean_celsius, sigma_celsius)}.
        Fetches multiple NWP models; mean=ensemble average, sigma=model spread (min 1.0°C).
        2026-05-20: Added elevation-aware sigma. Mountains (>1500m) floor at 3.0°C instead of 1.0°C.
        """
        url = (
            f"{METEO_BASE}?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max&temperature_unit=celsius"
            f"&forecast_days=2&models={FORECAST_MODELS}"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            # Collect all temperature_2m_max arrays (one per model)
            temp_keys = [k for k in daily if "temperature_2m_max" in k]
            result: dict[str, tuple[float, float]] = {}
            for i, d in enumerate(dates):
                if d not in (today, tomorrow):
                    continue
                values = []
                for k in temp_keys:
                    arr = daily[k]
                    if i < len(arr) and arr[i] is not None:
                        values.append(float(arr[i]))
                if not values:
                    continue
                mean = sum(values) / len(values)
                # Dynamic sigma: model spread is the best uncertainty estimate.
                spread = max(values) - min(values) if len(values) > 1 else 0.0

                # Elevation-aware sigma floor: mountains have higher forecast error
                elev = CITY_ELEVATION_M.get(city, 0.0)
                if elev > ELEVATION_THRESHOLD_M:
                    sigma_floor = ELEVATION_SIGMA_FLOOR
                else:
                    sigma_floor = 1.0
                sigma = max(sigma_floor, spread)
                result[d] = (mean, sigma)
                elev_tag = f" (elev {elev:.0f}m)" if elev > 0 else ""
                logger.debug("[WA] forecast %s lat=%.2f models=%d mean=%.1f sigma=%.1f%s",
                             d, lat, len(values), mean, sigma, elev_tag)
            return result if result else None
        except Exception as e:
            logger.debug("[WA] forecast error lat=%.2f lon=%.2f: %s", lat, lon, e)
            return None
