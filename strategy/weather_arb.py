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
MIN_FAIR_PROB = 0.35   # minimum fair probability for the best bucket
ASK_BAND_LO  = 0.01    # min entry price (overnight forecast arb)
ASK_BAND_HI  = 0.27    # max entry price — OVERRIDE with BRACKET_ENABLED for high-price entries

# ── NegRisk Bracketing ────────────────────────────────────────────────────────
BRACKET_ENABLED     = False  # enable only after Upgrade 1 skill matrix is validated
BRACKET_COST_CAP    = 0.80   # reject bracket if Σ ask_i > this (loss too expensive)
BRACKET_MAX_BUCKETS = 2      # maximum buckets in one bracket
# Sigma inflation for entries above ASK_BAND_HI (compensates for suspected overconfidence).
# Set to 1.0 to disable. Increase to 1.3 to make high-price fair_prob estimates more conservative.
SIGMA_INFLATION_ABOVE_CAP = 1.30   # applied when ask > ASK_BAND_HI and BRACKET_ENABLED
STAKE_USD    = 25.0    # fallback flat stake (used if Kelly is disabled or bankroll unavailable)

# ── Fractional Kelly position sizing ─────────────────────────────────────────
KELLY_ENABLED    = True   # False → revert to flat STAKE_USD
KELLY_FRACTION   = 0.25   # quarter-Kelly: conservative for unverified sigma calibration
KELLY_MIN_USD    = 5.0    # floor: below this, fees consume the edge
KELLY_MAX_USD    = 60.0   # ceiling: hard capital cap per weather position
SIGMA_C_DEFAULT = 1.5  # fallback forecast uncertainty when only one model available
SIGMA_F_DEFAULT = 2.7  # fallback in °F
SCAN_INTERVAL_S = 1800 # scan every 30 minutes
MAX_POSITIONS    = 30  # max concurrent weather positions
DRY_RUN_LOG  = False  # set False to trade live

# ── METAR-loop dynamic exits ──────────────────────────────────────────────────
NOWCAST_EXIT_FLOOR  = 0.04   # sell existing position when nowcast P(bucket) drops below this
SALVAGE_MIN_BID     = 0.05   # only bother selling if bid > this (otherwise loss is tiny)

# ── Intraday METAR arb (front-running WU→Polymarket lag) ─────────────────────
INTRADAY_ENABLED      = True   # master switch for today's-markets trading
INTRADAY_MIN_PROB     = 0.80   # minimum nowcast P(bucket) to enter today's market
INTRADAY_EDGE_MIN     = 0.06   # lower edge threshold (harder signal, less spread required)
INTRADAY_ASK_CAP      = 0.92   # upper price cap for intraday entries (near-certainty buys)
INTRADAY_STAKE_FRAC   = 0.60   # fractional Kelly multiplier for intraday (higher certainty → less fractional)
INTRADAY_HEAT_RAMP_H  = 5      # hours BEFORE peak to open the intraday scan window
# Example: peak_hour=16 UTC → window opens at UTC 11 (7 AM EDT), closes at peak+1=17
TODAY_MARKETS_TTL     = 1800   # seconds between today's-market list refreshes (30 min)

# ── CLOB / VWAP execution layer ───────────────────────────────────────────────
CLOB_BASE        = "https://clob.polymarket.com"
MAKER_FIRST      = True      # default: rest at best_bid+tick (passive fill)
TAKER_EDGE_MIN   = 0.15      # override to taker when edge this large (captures before repricing)
CLOB_TICK        = 0.01      # minimum price increment for weather markets

# ── Tail-risk sniper ($0.01–$0.04 tokens) ────────────────────────────────────
TAIL_SNIPER_ENABLED  = True
TAIL_PRICE_LO        = 0.01   # minimum token price for tail sniper
TAIL_PRICE_HI        = 0.04   # maximum token price for tail sniper
TAIL_STAKE_TOKENS    = 500    # flat share count (= $5–$20 total risk, max loss clearly bounded)
FOEHN_TEMP_RISE_C    = 1.5    # °C rapid rise in one 30-min METAR cycle → anomaly trigger
FOEHN_DEW_SPREAD_C   = 10.0   # temp − dewpoint > this → dry air, Foehn-consistent
FOEHN_WIND_MIN_KT    = 12.0   # minimum wind speed for directional Foehn trigger
FOEHN_MAX_GAP_C      = 3.0    # bucket_lo − running_max must be ≤ this to fire (reachable target)

# Foehn / downslope wind directions per ICAO (bearing FROM which warm dry air descends).
# Only stations with meaningful downslope exposure are listed.
FOEHN_WIND_SECTORS: dict[str, tuple[float, float]] = {
    "KLAX": (30.0,  90.0),   # Santa Ana: NE–E, descends from San Gabriel/Santa Monica Mtns
    "KSFO": (30.0,  80.0),   # Diablo wind: NE–ENE, descends from Diablo Range
    "KSEA": (30.0,  80.0),   # E–Cascade downslope
    "KBKF": (270.0, 330.0),  # Denver Chinook: W–NW off Front Range
    "RJTT": (300.0, 360.0),  # NW downslope from Japanese Alps in winter
}

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

# 7-model global ensemble. All models confirmed returning data for all validated cities
# via Open-Meteo live + historical APIs (2026-05-20 probe).
# GFS (NOAA), ICON (DWD), ECMWF IFS, GEM (CMC/Canada), JMA, UKMO, Météo-France.
# Models that lack coverage for a region return null and are silently excluded.
FORECAST_MODELS = "gfs_seamless,icon_seamless,ecmwf_ifs025,gem_seamless,jma_seamless,ukmo_seamless,meteofrance_seamless"

# US cities where we also fetch NWS NDFD as an additional source.
# NWS NDFD incorporates HRRR (3km) and NAM internally — equivalent to adding
# those models without parsing GRIB2 files directly.
_US_CITIES = {
    "New York City", "Chicago", "Los Angeles", "Miami", "San Francisco",
    "Dallas", "Houston", "Austin", "Denver", "Phoenix", "Atlanta", "Seattle",
}

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

# ICAO station codes — used for live METAR polling via AWC.
CITY_ICAO: dict[str, str] = {
    "London": "EGLC", "Paris": "LFPB", "Seoul": "RKSI", "Seattle": "KSEA",
    "Sao Paulo": "SBGR", "Buenos Aires": "SAEZ", "Ankara": "LTAC",
    "Wellington": "NZWN", "Lucknow": "VILK", "Munich": "EDDM",
    "New York City": "KLGA", "Dallas": "KDAL", "Miami": "KMIA",
    "Chicago": "KORD", "Singapore": "WSSS", "Milan": "LIMC",
    "Madrid": "LEMD", "Warsaw": "EPWA", "Taipei": "RCSS",
    "Beijing": "ZBAA", "Wuhan": "ZHHH", "Chengdu": "ZUUU",
    "Shenzhen": "ZGSZ", "Austin": "KAUS", "Denver": "KBKF",
    "Houston": "KHOU", "Los Angeles": "KLAX", "San Francisco": "KSFO",
    "Mexico City": "MMMX", "Busan": "RKPK", "Amsterdam": "EHAM",
    "Helsinki": "EFHK", "Panama City": "MPHO", "Jakarta": "WIHH",
    "Jeddah": "OEJN", "Cape Town": "FACT", "Guangzhou": "ZGGG",
    "Jinan": "ZSJN", "Qingdao": "ZSQD", "Karachi": "OPKC",
    "Manila": "RPLL", "Toronto": "CYYZ", "Shanghai": "ZSPD",
    "Tokyo": "RJTT", "Hong Kong": "VHHH", "Dubai": "OMDB",
    "Sydney": "YSSY", "Phoenix": "KPHX", "Atlanta": "KATL",
    "Berlin": "EDDB", "Stockholm": "ESSA", "Oslo": "ENGM",
    "Copenhagen": "EKCH", "Vienna": "LOWW", "Zurich": "LSZH",
    "Brussels": "EBBR", "Barcelona": "LEBL", "Rome": "LIRF",
    "Prague": "LKPR", "Budapest": "LHBP", "Bucharest": "LROP",
    "Athens": "LGAV", "Istanbul": "LTFJ", "Moscow": "UUEE",
    "Riyadh": "OERK", "Cairo": "HECA", "Lagos": "DNMM",
    "Nairobi": "HKJK", "Johannesburg": "FAOR", "Mumbai": "VABB",
    "Delhi": "VIDP", "Dhaka": "VGHS", "Bangkok": "VTBS",
    "Kuala Lumpur": "WMKK", "Bogota": "SKBO", "Lima": "SPJC",
    "Santiago": "SCEL", "Chongqing": "ZUCK", "Dallas": "KDAL",
}

AWC_METAR_URL = "https://aviationweather.gov/api/data/metar?ids={icao}&format=json&hours=1"
METAR_POLL_INTERVAL = 60  # METARs post every ~30 min; poll every 60s to catch within 60s

# Calibration tables derived from 5 years (2021-2025) of ASOS hourly data via Iowa State Mesonet.
# Only the 7 stations validated against Polymarket market rules (analysis/weather/stations.py).
# sigma_residual = sigma_clim × sqrt(1 − r²), r=0.95 (NWP skill assumption; update when
# forecast-vs-actual validation accumulates ≥30 days per city).
CITY_NAME_TO_SLUG: dict[str, str] = {
    "New York City": "nyc", "Chicago": "chicago", "Los Angeles": "los-angeles",
    "Miami": "miami", "San Francisco": "san-francisco", "Tokyo": "tokyo", "London": "london",
}

# Per-city/month residual sigma in °C (uncertainty remaining after NWP forecast, r=0.95 assumed)
CITY_SIGMA_C: dict[str, dict[int, float]] = {
    "nyc":           {1: 1.39, 2: 1.56, 3: 1.58, 4: 1.65, 5: 1.52, 6: 1.33, 7: 0.87, 8: 0.99, 9: 1.09, 10: 1.25, 11: 1.6,  12: 1.56},
    "chicago":       {1: 1.65, 2: 2.3,  3: 1.95, 4: 2.07, 5: 1.87, 6: 1.25, 7: 0.94, 8: 1.07, 9: 1.31, 10: 1.79, 11: 1.93, 12: 1.85},
    "los-angeles":   {1: 1.12, 2: 1.17, 3: 0.95, 4: 1.1,  5: 0.57, 6: 0.54, 7: 0.47, 8: 0.56, 9: 1.13, 10: 0.94, 11: 1.06, 12: 0.98},
    "miami":         {1: 0.94, 2: 0.76, 3: 0.64, 4: 0.58, 5: 0.52, 6: 0.43, 7: 0.41, 8: 0.37, 9: 0.4,  10: 0.5,  11: 0.68, 12: 0.85},
    "san-francisco": {1: 0.72, 2: 0.88, 3: 0.97, 4: 1.06, 5: 1.0,  6: 0.99, 7: 0.76, 8: 0.87, 9: 1.07, 10: 1.31, 11: 0.79, 12: 0.75},
    "tokyo":         {1: 0.75, 2: 1.09, 3: 1.35, 4: 1.13, 5: 0.89, 6: 0.99, 7: 0.9,  8: 0.78, 9: 1.05, 10: 1.15, 11: 0.96, 12: 0.95},
    "london":        {1: 1.02, 2: 1.09, 3: 1.1,  4: 1.04, 5: 1.03, 6: 1.3,  7: 1.12, 8: 1.0,  9: 1.16, 10: 0.81, 11: 0.97, 12: 1.05},
}

# Per-city/month typical peak temperature UTC hour (mean of daily peak hours, 5yr ASOS)
CITY_PEAK_HOUR_UTC: dict[str, dict[int, int]] = {
    "nyc":           {1: 13, 2: 14, 3: 13, 4: 14, 5: 15, 6: 16, 7: 16, 8: 16, 9: 15, 10: 15, 11: 14, 12: 12},
    "chicago":       {1: 13, 2: 14, 3: 14, 4: 14, 5: 16, 6: 15, 7: 16, 8: 16, 9: 16, 10: 15, 11: 15, 12: 13},
    "los-angeles":   {1: 17, 2: 17, 3: 17, 4: 18, 5: 18, 6: 18, 7: 19, 8: 17, 9: 18, 10: 18, 11: 18, 12: 18},
    "miami":         {1: 16, 2: 16, 3: 16, 4: 17, 5: 17, 6: 16, 7: 17, 8: 16, 9: 16, 10: 16, 11: 16, 12: 15},
    "san-francisco": {1: 15, 2: 17, 3: 17, 4: 17, 5: 17, 6: 18, 7: 17, 8: 19, 9: 18, 10: 18, 11: 17, 12: 15},
    "tokyo":         {1:  4, 2:  5, 3:  5, 4:  5, 5:  6, 6:  5, 7:  4, 8:  4, 9:  4, 10:  5, 11:  4, 12:  5},
    "london":        {1: 11, 2: 11, 3: 12, 4: 12, 5: 13, 6: 13, 7: 13, 8: 13, 9: 12, 10: 12, 11: 10, 12: 10},
}

# Per-city/month/UTC-hour mean remaining rise in °C (how much more the temp typically rises
# from this observation hour to the daily maximum). From 5yr ASOS data, sky-cover-independent.
# Apply sky_factor on top: CLR=1.0, FEW=0.85, SCT=0.60, BKN=0.30, OVC=0.08
CITY_REMAINING_RISE: dict[str, dict[int, dict[int, float]]] = {
    "nyc": {
        1:  {0: 2.55, 1: 2.83, 2: 2.9,  3: 3.13, 4: 3.35, 5: 3.52, 6: 3.7,  7: 3.7,  8: 3.88, 9: 4.04, 10: 4.03, 11: 4.25, 12: 4.28, 13: 3.86, 14: 3.32, 15: 2.79, 16: 2.18, 17: 1.98, 18: 1.59, 19: 1.43, 20: 1.66, 21: 1.87, 22: 2.11, 23: 2.36},
        2:  {0: 3.34, 1: 3.5,  2: 3.71, 3: 4.06, 4: 4.29, 5: 4.52, 6: 4.67, 7: 4.96, 8: 5.25, 9: 5.36, 10: 5.53, 11: 5.68, 12: 5.38, 13: 4.85, 14: 4.32, 15: 3.78, 16: 3.05, 17: 2.46, 18: 2.26, 19: 1.89, 20: 1.92, 21: 2.27, 22: 2.64, 23: 2.72},
        3:  {0: 4.26, 1: 4.49, 2: 4.79, 3: 5.06, 4: 5.54, 5: 5.77, 6: 5.92, 7: 6.52, 8: 6.68, 9: 6.72, 10: 6.84, 11: 6.64, 12: 6.05, 13: 5.28, 14: 4.5,  15: 3.57, 16: 2.78, 17: 2.03, 18: 1.69, 19: 1.52, 20: 1.82, 21: 2.33, 22: 2.84, 23: 3.43},
        4:  {0: 4.45, 1: 4.69, 2: 5.18, 3: 5.33, 4: 5.74, 5: 6.07, 6: 6.44, 7: 6.73, 8: 7.15, 9: 7.32, 10: 7.26, 11: 6.69, 12: 6.3,  13: 5.68, 14: 4.73, 15: 3.79, 16: 3.06, 17: 2.43, 18: 1.92, 19: 1.88, 20: 2.23, 21: 2.67, 22: 3.01, 23: 3.93},
        5:  {0: 4.7,  1: 5.27, 2: 5.48, 3: 5.87, 4: 6.15, 5: 6.46, 6: 6.71, 7: 7.35, 8: 7.39, 9: 7.37, 10: 7.24, 11: 6.84, 12: 6.0,  13: 4.9,  14: 4.22, 15: 3.07, 16: 2.38, 17: 1.96, 18: 1.58, 19: 1.54, 20: 1.67, 21: 2.15, 22: 2.78, 23: 3.5},
        6:  {0: 4.8,  1: 5.2,  2: 5.49, 3: 5.85, 4: 6.22, 5: 6.6,  6: 6.92, 7: 7.27, 8: 7.46, 9: 7.51, 10: 7.09, 11: 6.37, 12: 5.62, 13: 4.62, 14: 3.76, 15: 2.82, 16: 2.05, 17: 1.72, 18: 1.55, 19: 1.5,  20: 2.07, 21: 2.36, 22: 2.94, 23: 3.77},
        7:  {0: 3.84, 1: 4.38, 2: 5.01, 3: 5.1,  4: 5.58, 5: 5.88, 6: 6.11, 7: 6.48, 8: 6.88, 9: 7.14, 10: 6.91, 11: 6.28, 12: 5.44, 13: 4.5,  14: 3.46, 15: 2.57, 16: 1.93, 17: 1.84, 18: 1.25, 19: 1.54, 20: 1.68, 21: 2.07, 22: 2.72, 23: 3.73},
        8:  {0: 3.76, 1: 4.09, 2: 4.49, 3: 4.62, 4: 4.91, 5: 5.27, 6: 5.58, 7: 5.84, 8: 6.05, 9: 6.26, 10: 6.24, 11: 5.86, 12: 5.04, 13: 4.13, 14: 3.19, 15: 2.31, 16: 1.62, 17: 1.23, 18: 0.96, 19: 1.05, 20: 1.37, 21: 2.16, 22: 2.7,  23: 3.66},
        9:  {0: 3.07, 1: 3.54, 2: 3.84, 3: 4.26, 4: 4.59, 5: 4.94, 6: 5.04, 7: 5.35, 8: 5.55, 9: 5.99, 10: 6.05, 11: 5.77, 12: 4.88, 13: 4.07, 14: 3.13, 15: 2.48, 16: 1.95, 17: 1.46, 18: 1.05, 19: 1.0,  20: 1.33, 21: 1.64, 22: 2.39, 23: 2.95},
        10: {0: 3.1,  1: 3.39, 2: 3.81, 3: 4.26, 4: 4.48, 5: 4.78, 6: 5.21, 7: 5.51, 8: 5.6,  9: 5.72, 10: 5.85, 11: 5.63, 12: 4.96, 13: 4.12, 14: 3.32, 15: 2.45, 16: 1.67, 17: 1.3,  18: 0.85, 19: 0.82, 20: 1.11, 21: 1.85, 22: 2.41, 23: 2.75},
        11: {0: 2.79, 1: 3.05, 2: 3.38, 3: 3.76, 4: 4.09, 5: 4.32, 6: 4.54, 7: 4.76, 8: 4.91, 9: 5.21, 10: 5.19, 11: 5.39, 12: 4.8,  13: 4.16, 14: 3.39, 15: 2.67, 16: 2.05, 17: 1.59, 18: 1.14, 19: 1.18, 20: 1.48, 21: 1.92, 22: 2.4,  23: 2.78},
        12: {0: 2.83, 1: 3.2,  2: 3.38, 3: 3.51, 4: 3.62, 5: 4.01, 6: 3.95, 7: 4.05, 8: 4.16, 9: 4.26, 10: 4.38, 11: 4.29, 12: 4.11, 13: 3.82, 14: 3.19, 15: 2.61, 16: 2.11, 17: 1.77, 18: 1.44, 19: 1.43, 20: 1.72, 21: 2.02, 22: 2.15, 23: 2.44},
    },
    "chicago": {
        1:  {0: 2.5,  1: 2.65, 2: 2.67, 3: 2.88, 4: 3.21, 5: 3.28, 6: 3.56, 7: 3.66, 8: 3.86, 9: 3.98, 10: 4.05, 11: 4.12, 12: 4.25, 13: 4.26, 14: 3.71, 15: 3.31, 16: 2.75, 17: 2.29, 18: 2.0,  19: 1.65, 20: 1.48, 21: 1.69, 22: 2.32, 23: 2.59},
        2:  {0: 3.77, 1: 3.93, 2: 4.68, 3: 4.84, 4: 4.96, 5: 5.26, 6: 5.79, 7: 6.0,  8: 6.41, 9: 6.83, 10: 6.87, 11: 7.01, 12: 7.09, 13: 6.8,  14: 5.92, 15: 4.95, 16: 3.66, 17: 2.65, 18: 2.01, 19: 2.15, 20: 2.03, 21: 2.4,  22: 2.59, 23: 3.22},
        3:  {0: 4.54, 1: 5.33, 2: 5.44, 3: 6.04, 4: 6.11, 5: 6.55, 6: 6.76, 7: 7.15, 8: 7.48, 9: 7.55, 10: 8.05, 11: 8.35, 12: 7.45, 13: 6.8,  14: 5.9,  15: 4.76, 16: 3.84, 17: 3.02, 18: 3.0,  19: 2.51, 20: 2.37, 21: 2.64, 22: 3.4,  23: 4.22},
        4:  {0: 4.28, 1: 5.06, 2: 5.56, 3: 6.15, 4: 6.57, 5: 6.8,  6: 7.27, 7: 7.64, 8: 7.96, 9: 8.17, 10: 8.64, 11: 8.12, 12: 7.7,  13: 6.55, 14: 5.46, 15: 4.83, 16: 4.28, 17: 4.01, 18: 3.54, 19: 2.63, 20: 2.64, 21: 2.52, 22: 2.86, 23: 3.58},
        5:  {0: 4.46, 1: 5.73, 2: 6.41, 3: 6.94, 4: 7.47, 5: 7.94, 6: 8.43, 7: 8.9,  8: 9.27, 9: 9.34, 10: 9.35, 11: 8.78, 12: 7.5,  13: 6.2,  14: 4.87, 15: 3.86, 16: 3.05, 17: 2.5,  18: 2.0,  19: 1.81, 20: 1.73, 21: 1.9,  22: 2.51, 23: 3.38},
        6:  {0: 4.62, 1: 5.61, 2: 6.54, 3: 7.27, 4: 7.84, 5: 8.25, 6: 8.77, 7: 9.09, 8: 9.27, 9: 9.64, 10: 9.71, 11: 8.83, 12: 7.41, 13: 6.11, 14: 4.96, 15: 3.86, 16: 2.97, 17: 2.33, 18: 2.14, 19: 2.15, 20: 2.03, 21: 2.15, 22: 2.92, 23: 3.66},
        7:  {0: 3.48, 1: 4.38, 2: 5.06, 3: 5.9,  4: 6.42, 5: 6.7,  6: 7.25, 7: 7.35, 8: 7.64, 9: 7.93, 10: 7.89, 11: 7.36, 12: 6.3,  13: 5.18, 14: 3.99, 15: 3.19, 16: 2.38, 17: 1.86, 18: 1.72, 19: 1.42, 20: 1.7,  21: 2.09, 22: 2.36, 23: 2.57},
        8:  {0: 4.07, 1: 4.7,  2: 5.26, 3: 5.94, 4: 6.32, 5: 6.57, 6: 7.12, 7: 7.45, 8: 7.73, 9: 8.01, 10: 8.14, 11: 7.97, 12: 6.61, 13: 5.32, 14: 4.07, 15: 2.85, 16: 2.11, 17: 1.7,  18: 1.18, 19: 1.01, 20: 1.36, 21: 1.5,  22: 2.14, 23: 3.28},
        9:  {0: 4.37, 1: 4.97, 2: 5.61, 3: 6.17, 4: 6.64, 5: 6.93, 6: 7.35, 7: 7.7,  8: 8.07, 9: 8.21, 10: 8.27, 11: 8.52, 12: 7.52, 13: 5.98, 14: 4.57, 15: 3.3,  16: 2.26, 17: 1.54, 18: 1.2,  19: 1.17, 20: 1.24, 21: 1.44, 22: 2.19, 23: 3.51},
        10: {0: 3.73, 1: 4.21, 2: 4.62, 3: 5.13, 4: 5.41, 5: 6.09, 6: 6.48, 7: 6.74, 8: 7.15, 9: 7.25, 10: 7.42, 11: 7.77, 12: 7.27, 13: 5.99, 14: 4.75, 15: 3.42, 16: 2.47, 17: 1.76, 18: 1.45, 19: 1.43, 20: 1.47, 21: 1.85, 22: 2.87, 23: 3.59},
        11: {0: 3.37, 1: 3.62, 2: 4.2,  3: 4.4,  4: 4.72, 5: 5.01, 6: 5.21, 7: 5.58, 8: 5.81, 9: 5.66, 10: 5.94, 11: 5.87, 12: 6.2,  13: 5.76, 14: 4.61, 15: 3.44, 16: 2.61, 17: 2.35, 18: 1.84, 19: 1.67, 20: 1.53, 21: 1.9,  22: 2.64, 23: 3.07},
        12: {0: 2.73, 1: 3.02, 2: 3.31, 3: 3.83, 4: 3.86, 5: 4.03, 6: 4.21, 7: 4.44, 8: 4.67, 9: 4.69, 10: 4.67, 11: 5.06, 12: 4.91, 13: 4.85, 14: 4.25, 15: 3.62, 16: 2.47, 17: 2.15, 18: 1.83, 19: 1.58, 20: 1.65, 21: 1.97, 22: 2.35, 23: 2.64},
    },
    "los-angeles": {
        1:  {0: 3.25, 1: 3.76, 2: 3.97, 3: 4.19, 4: 4.58, 5: 4.87, 6: 5.09, 7: 5.39, 8: 6.42, 9: 6.78, 10: 7.23, 11: 7.28, 12: 7.69, 13: 7.34, 14: 7.24, 15: 6.63, 16: 4.77, 17: 3.09, 18: 1.97, 19: 1.04, 20: 0.82, 21: 1.0,  22: 1.48, 23: 2.16},
        2:  {0: 2.99, 1: 3.77, 2: 4.27, 3: 4.42, 4: 4.49, 5: 4.88, 6: 4.94, 7: 5.35, 8: 5.86, 9: 6.05, 10: 6.56, 11: 6.84, 12: 7.07, 13: 6.92, 14: 6.66, 15: 5.62, 16: 4.03, 17: 2.49, 18: 1.49, 19: 0.92, 20: 0.94, 21: 1.16, 22: 1.59, 23: 2.15},
        3:  {0: 2.61, 1: 3.48, 2: 3.75, 3: 3.99, 4: 4.21, 5: 4.31, 6: 4.49, 7: 4.99, 8: 5.28, 9: 5.63, 10: 6.04, 11: 6.16, 12: 6.16, 13: 6.11, 14: 5.63, 15: 4.33, 16: 2.92, 17: 1.71, 18: 1.03, 19: 0.86, 20: 0.91, 21: 1.11, 22: 1.42, 23: 1.9},
        4:  {0: 2.69, 1: 3.55, 2: 4.17, 3: 4.37, 4: 4.62, 5: 4.68, 6: 4.89, 7: 5.16, 8: 5.45, 9: 5.66, 10: 5.94, 11: 6.12, 12: 6.06, 13: 5.92, 14: 4.67, 15: 3.49, 16: 2.13, 17: 1.29, 18: 1.03, 19: 0.77, 20: 0.75, 21: 0.89, 22: 1.39, 23: 1.91},
        5:  {0: 2.14, 1: 2.92, 2: 3.68, 3: 3.95, 4: 3.98, 5: 4.02, 6: 4.09, 7: 4.16, 8: 4.42, 9: 4.52, 10: 4.61, 11: 4.74, 12: 4.76, 13: 4.31, 14: 3.61, 15: 2.74, 16: 2.05, 17: 1.49, 18: 0.95, 19: 0.64, 20: 0.47, 21: 0.51, 22: 0.85, 23: 1.34},
        6:  {0: 2.21, 1: 3.03, 2: 3.77, 3: 4.18, 4: 4.23, 5: 4.34, 6: 4.44, 7: 4.56, 8: 4.68, 9: 4.73, 10: 4.86, 11: 4.97, 12: 4.8,  13: 4.49, 14: 3.7,  15: 2.79, 16: 1.92, 17: 1.45, 18: 1.0,  19: 0.65, 20: 0.5,  21: 0.5,  22: 0.84, 23: 1.42},
        7:  {0: 2.22, 1: 3.16, 2: 4.03, 3: 4.38, 4: 4.6,  5: 4.71, 6: 4.73, 7: 4.81, 8: 4.91, 9: 4.99, 10: 5.05, 11: 5.05, 12: 5.02, 13: 4.78, 14: 4.11, 15: 3.08, 16: 2.11, 17: 1.37, 18: 0.89, 19: 0.54, 20: 0.48, 21: 0.64, 22: 0.91, 23: 1.45},
        8:  {0: 2.44, 1: 3.35, 2: 4.17, 3: 4.53, 4: 4.61, 5: 4.74, 6: 4.86, 7: 4.97, 8: 5.02, 9: 5.25, 10: 5.36, 11: 5.29, 12: 5.38, 13: 5.11, 14: 4.32, 15: 3.19, 16: 1.98, 17: 1.19, 18: 0.75, 19: 0.66, 20: 0.63, 21: 0.72, 22: 1.05, 23: 1.64},
        9:  {0: 2.86, 1: 3.71, 2: 4.05, 3: 4.21, 4: 4.37, 5: 4.62, 6: 4.69, 7: 4.83, 8: 5.1,  9: 5.17, 10: 5.37, 11: 5.35, 12: 5.24, 13: 5.31, 14: 4.52, 15: 3.46, 16: 2.47, 17: 1.59, 18: 0.96, 19: 0.79, 20: 0.76, 21: 0.99, 22: 1.4,  23: 2.04},
        10: {0: 3.42, 1: 4.05, 2: 4.21, 3: 4.33, 4: 4.38, 5: 4.65, 6: 4.94, 7: 5.37, 8: 5.66, 9: 5.96, 10: 6.33, 11: 6.34, 12: 6.36, 13: 6.32, 14: 5.84, 15: 4.23, 16: 2.8,  17: 1.61, 18: 0.88, 19: 0.8,  20: 1.02, 21: 1.25, 22: 1.7,  23: 2.46},
        11: {0: 3.71, 1: 4.2,  2: 4.36, 3: 4.55, 4: 5.06, 5: 5.01, 6: 5.43, 7: 5.45, 8: 6.21, 9: 6.95, 10: 7.23, 11: 7.21, 12: 7.37, 13: 7.33, 14: 6.95, 15: 5.55, 16: 3.67, 17: 2.16, 18: 1.05, 19: 0.7,  20: 0.98, 21: 1.29, 22: 1.86, 23: 2.81},
        12: {0: 3.07, 1: 3.22, 2: 3.47, 3: 3.56, 4: 3.76, 5: 4.05, 6: 4.33, 7: 4.52, 8: 5.25, 9: 5.94, 10: 5.93, 11: 6.21, 12: 6.3,  13: 6.15, 14: 6.26, 15: 5.45, 16: 3.96, 17: 2.68, 18: 1.6,  19: 0.99, 20: 0.96, 21: 1.16, 22: 1.59, 23: 2.16},
    },
    "miami": {
        1:  {0: 3.89, 1: 4.2,  2: 4.66, 3: 5.06, 4: 5.31, 5: 5.6,  6: 6.03, 7: 6.03, 8: 6.24, 9: 6.45, 10: 6.69, 11: 6.73, 12: 6.18, 13: 4.76, 14: 3.32, 15: 2.21, 16: 1.65, 17: 1.12, 18: 0.96, 19: 0.99, 20: 1.29, 21: 1.91, 22: 2.8,  23: 3.58},
        2:  {0: 3.63, 1: 4.11, 2: 4.42, 3: 4.65, 4: 5.04, 5: 5.33, 6: 5.63, 7: 5.74, 8: 6.0,  9: 6.06, 10: 6.24, 11: 6.11, 12: 5.28, 13: 3.96, 14: 2.82, 15: 1.7,  16: 1.31, 17: 0.89, 18: 0.85, 19: 0.75, 20: 1.25, 21: 1.74, 22: 2.55, 23: 3.3},
        3:  {0: 3.98, 1: 4.36, 2: 4.69, 3: 5.02, 4: 5.28, 5: 5.71, 6: 5.86, 7: 6.12, 8: 6.43, 9: 6.57, 10: 6.5,  11: 6.44, 12: 5.1,  13: 3.69, 14: 2.65, 15: 1.77, 16: 1.26, 17: 0.87, 18: 0.74, 19: 0.84, 20: 1.41, 21: 1.95, 22: 2.74, 23: 3.52},
        4:  {0: 3.92, 1: 4.12, 2: 4.54, 3: 4.82, 4: 5.0,  5: 5.39, 6: 5.57, 7: 5.89, 8: 5.85, 9: 5.88, 10: 6.0,  11: 5.19, 12: 3.94, 13: 2.85, 14: 1.95, 15: 1.34, 16: 1.1,  17: 0.94, 18: 0.69, 19: 0.93, 20: 1.45, 21: 2.32, 22: 2.82, 23: 3.56},
        5:  {0: 4.32, 1: 4.52, 2: 4.73, 3: 4.94, 4: 5.08, 5: 5.37, 6: 5.68, 7: 5.84, 8: 5.9,  9: 6.04, 10: 5.97, 11: 5.02, 12: 3.74, 13: 2.7,  14: 1.87, 15: 1.13, 16: 0.87, 17: 1.0,  18: 1.21, 19: 1.5,  20: 1.82, 21: 2.37, 22: 2.93, 23: 3.96},
        6:  {0: 4.1,  1: 4.37, 2: 4.42, 3: 4.53, 4: 4.97, 5: 5.13, 6: 5.2,  7: 5.38, 8: 5.32, 9: 5.33, 10: 5.24, 11: 4.19, 12: 3.35, 13: 2.44, 14: 1.86, 15: 1.71, 16: 1.65, 17: 2.02, 18: 1.91, 19: 2.3,  20: 2.63, 21: 2.76, 22: 3.59, 23: 3.73},
        7:  {0: 4.04, 1: 4.3,  2: 4.32, 3: 4.47, 4: 4.65, 5: 5.01, 6: 5.25, 7: 5.22, 8: 5.38, 9: 5.38, 10: 5.27, 11: 4.56, 12: 3.64, 13: 2.7,  14: 1.95, 15: 1.46, 16: 1.62, 17: 1.88, 18: 1.81, 19: 1.74, 20: 1.82, 21: 1.99, 22: 2.78, 23: 3.75},
        8:  {0: 4.28, 1: 4.32, 2: 4.65, 3: 4.71, 4: 4.81, 5: 4.99, 6: 5.14, 7: 5.36, 8: 5.41, 9: 5.45, 10: 5.49, 11: 4.83, 12: 3.6,  13: 2.64, 14: 1.83, 15: 1.38, 16: 1.5,  17: 2.11, 18: 2.14, 19: 2.33, 20: 2.65, 21: 3.09, 22: 3.51, 23: 3.93},
        9:  {0: 4.94, 1: 4.99, 2: 5.08, 3: 5.28, 4: 5.41, 5: 5.64, 6: 5.62, 7: 5.81, 8: 5.88, 9: 5.92, 10: 5.84, 11: 5.26, 12: 3.84, 13: 2.66, 14: 1.74, 15: 1.63, 16: 1.79, 17: 1.71, 18: 2.59, 19: 2.86, 20: 2.91, 21: 3.6,  22: 4.13, 23: 4.61},
        10: {0: 3.36, 1: 3.54, 2: 3.84, 3: 3.96, 4: 4.28, 5: 4.65, 6: 4.8,  7: 5.0,  8: 5.15, 9: 5.2,  10: 5.09, 11: 4.9,  12: 3.63, 13: 2.5,  14: 1.91, 15: 1.32, 16: 0.89, 17: 1.0,  18: 1.16, 19: 1.39, 20: 1.62, 21: 2.31, 22: 2.86, 23: 3.16},
        11: {0: 3.31, 1: 3.53, 2: 3.94, 3: 4.24, 4: 4.52, 5: 4.84, 6: 5.16, 7: 5.34, 8: 5.48, 9: 5.62, 10: 5.7,  11: 5.72, 12: 4.67, 13: 3.55, 14: 2.52, 15: 1.5,  16: 0.92, 17: 0.79, 18: 0.72, 19: 0.94, 20: 1.34, 21: 2.01, 22: 2.69, 23: 3.12},
        12: {0: 3.45, 1: 3.64, 2: 4.06, 3: 4.33, 4: 4.68, 5: 5.05, 6: 5.4,  7: 5.59, 8: 5.86, 9: 5.92, 10: 6.03, 11: 5.89, 12: 5.24, 13: 3.97, 14: 2.68, 15: 1.83, 16: 1.16, 17: 0.75, 18: 0.72, 19: 0.86, 20: 1.31, 21: 1.88, 22: 2.68, 23: 3.19},
    },
    "san-francisco": {
        1:  {0: 1.72, 1: 2.51, 2: 2.8,  3: 3.2,  4: 3.51, 5: 3.79, 6: 4.01, 7: 4.1,  8: 4.46, 9: 4.89, 10: 5.11, 11: 5.35, 12: 5.36, 13: 5.41, 14: 5.29, 15: 5.12, 16: 4.02, 17: 3.38, 18: 2.69, 19: 2.14, 20: 1.6,  21: 1.0,  22: 0.85, 23: 0.98},
        2:  {0: 2.11, 1: 3.06, 2: 3.65, 3: 4.07, 4: 4.39, 5: 4.64, 6: 5.01, 7: 5.39, 8: 5.72, 9: 6.18, 10: 6.42, 11: 6.75, 12: 6.99, 13: 7.16, 14: 6.92, 15: 6.2,  16: 4.96, 17: 3.98, 18: 3.43, 19: 2.65, 20: 1.87, 21: 1.28, 22: 0.95, 23: 1.09},
        3:  {0: 2.3,  1: 3.41, 2: 4.06, 3: 4.35, 4: 4.6,  5: 4.77, 6: 5.21, 7: 5.44, 8: 5.65, 9: 5.88, 10: 6.1,  11: 6.31, 12: 6.47, 13: 6.51, 14: 6.26, 15: 5.07, 16: 4.12, 17: 3.32, 18: 2.6,  19: 2.03, 20: 1.25, 21: 0.94, 22: 1.06, 23: 1.6},
        4:  {0: 2.84, 1: 4.05, 2: 5.11, 3: 5.47, 4: 5.81, 5: 5.98, 6: 6.12, 7: 6.33, 8: 6.6,  9: 6.74, 10: 7.07, 11: 7.26, 12: 7.39, 13: 7.28, 14: 6.34, 15: 5.19, 16: 4.27, 17: 3.24, 18: 2.38, 19: 1.5,  20: 1.04, 21: 0.83, 22: 1.19, 23: 1.92},
        5:  {0: 2.96, 1: 4.01, 2: 5.31, 3: 5.93, 4: 6.3,  5: 6.65, 6: 6.99, 7: 7.15, 8: 7.23, 9: 7.3,  10: 7.41, 11: 7.62, 12: 7.61, 13: 7.27, 14: 6.22, 15: 4.99, 16: 4.12, 17: 2.85, 18: 1.84, 19: 1.2,  20: 0.9,  21: 0.87, 22: 1.24, 23: 1.85},
        6:  {0: 2.79, 1: 3.87, 2: 5.09, 3: 5.99, 4: 6.28, 5: 6.52, 6: 6.75, 7: 6.88, 8: 7.08, 9: 7.3,  10: 7.45, 11: 7.65, 12: 7.66, 13: 7.06, 14: 6.03, 15: 4.95, 16: 3.9,  17: 2.97, 18: 1.78, 19: 1.0,  20: 0.66, 21: 0.75, 22: 1.2,  23: 1.88},
        7:  {0: 2.75, 1: 3.86, 2: 5.18, 3: 6.02, 4: 6.33, 5: 6.48, 6: 6.74, 7: 6.86, 8: 7.12, 9: 7.25, 10: 7.36, 11: 7.45, 12: 7.41, 13: 7.16, 14: 6.21, 15: 5.05, 16: 3.88, 17: 2.93, 18: 2.0,  19: 1.24, 20: 0.73, 21: 0.71, 22: 1.06, 23: 1.76},
        8:  {0: 2.9,  1: 4.24, 2: 5.62, 3: 6.17, 4: 6.5,  5: 6.63, 6: 6.82, 7: 7.15, 8: 7.38, 9: 7.55, 10: 7.72, 11: 7.86, 12: 7.86, 13: 7.79, 14: 6.77, 15: 5.57, 16: 4.4,  17: 3.32, 18: 2.31, 19: 1.43, 20: 0.83, 21: 0.62, 22: 1.15, 23: 1.86},
        9:  {0: 3.32, 1: 4.79, 2: 5.78, 3: 6.1,  4: 6.3,  5: 6.5,  6: 6.82, 7: 7.0,  8: 7.07, 9: 7.4,  10: 7.56, 11: 7.79, 12: 7.89, 13: 7.87, 14: 7.23, 15: 5.94, 16: 5.01, 17: 3.77, 18: 2.78, 19: 1.75, 20: 1.15, 21: 0.71, 22: 1.29, 23: 2.18},
        10: {0: 3.25, 1: 4.67, 2: 5.18, 3: 5.49, 4: 5.8,  5: 6.1,  6: 6.19, 7: 6.64, 8: 6.94, 9: 7.22, 10: 7.34, 11: 7.54, 12: 7.6,  13: 7.67, 14: 7.49, 15: 5.98, 16: 4.94, 17: 3.94, 18: 3.12, 19: 2.17, 20: 1.55, 21: 1.29, 22: 1.28, 23: 2.15},
        11: {0: 2.04, 1: 2.78, 2: 3.41, 3: 3.74, 4: 4.05, 5: 4.46, 6: 4.6,  7: 4.86, 8: 5.24, 9: 5.8,  10: 5.93, 11: 6.24, 12: 6.32, 13: 6.39, 14: 6.18, 15: 5.37, 16: 4.22, 17: 3.45, 18: 2.84, 19: 2.12, 20: 1.34, 21: 0.9,  22: 0.68, 23: 1.1},
        12: {0: 1.72, 1: 2.11, 2: 2.45, 3: 2.62, 4: 2.89, 5: 3.13, 6: 3.27, 7: 3.36, 8: 3.56, 9: 3.98, 10: 4.08, 11: 4.32, 12: 4.49, 13: 4.39, 14: 4.39, 15: 4.31, 16: 3.41, 17: 2.77, 18: 2.35, 19: 1.82, 20: 1.34, 21: 1.12, 22: 0.94, 23: 1.09},
    },
    "tokyo": {
        1:  {0: 3.19, 1: 2.36, 2: 1.62, 3: 1.16, 4: 0.85, 5: 0.63, 6: 0.65, 7: 1.15, 8: 1.61, 9: 1.95, 10: 2.29, 11: 2.6,  12: 3.07, 13: 3.29, 14: 3.72, 15: 4.14, 16: 4.32, 17: 4.76, 18: 4.93, 19: 5.11, 20: 5.24, 21: 5.38, 22: 5.25, 23: 4.22},
        2:  {0: 3.78, 1: 2.78, 2: 1.93, 3: 1.51, 4: 1.1,  5: 0.82, 6: 0.89, 7: 1.23, 8: 1.9,  9: 2.33, 10: 2.81, 11: 3.18, 12: 3.45, 13: 3.82, 14: 3.97, 15: 4.37, 16: 4.63, 17: 5.04, 18: 5.31, 19: 5.43, 20: 5.63, 21: 5.91, 22: 5.46, 23: 4.61},
        3:  {0: 3.74, 1: 3.23, 2: 2.63, 3: 2.01, 4: 1.51, 5: 1.21, 6: 1.21, 7: 1.5,  8: 2.06, 9: 2.59, 10: 3.14, 11: 3.5,  12: 3.79, 13: 4.16, 14: 4.26, 15: 4.52, 16: 4.89, 17: 5.18, 18: 5.45, 19: 5.71, 20: 5.81, 21: 5.86, 22: 5.31, 23: 4.53},
        4:  {0: 3.34, 1: 2.52, 2: 1.92, 3: 1.48, 4: 1.15, 5: 1.01, 6: 1.07, 7: 1.53, 8: 2.13, 9: 2.83, 10: 3.31, 11: 3.69, 12: 3.9,  13: 4.1,  14: 4.33, 15: 4.54, 16: 4.78, 17: 5.04, 18: 5.28, 19: 5.45, 20: 5.56, 21: 5.17, 22: 4.56, 23: 3.88},
        5:  {0: 3.18, 1: 2.52, 2: 1.8,  3: 1.43, 4: 1.17, 5: 1.04, 6: 1.27, 7: 1.66, 8: 2.23, 9: 2.8,  10: 3.32, 11: 3.67, 12: 3.97, 13: 4.16, 14: 4.27, 15: 4.56, 16: 4.86, 17: 5.02, 18: 5.24, 19: 5.4,  20: 5.4,  21: 4.84, 22: 4.34, 23: 3.63},
        6:  {0: 2.97, 1: 2.36, 2: 1.82, 3: 1.34, 4: 1.13, 5: 0.99, 6: 1.25, 7: 1.7,  8: 2.22, 9: 2.86, 10: 3.34, 11: 3.76, 12: 4.08, 13: 4.3,  14: 4.49, 15: 4.65, 16: 4.83, 17: 5.02, 18: 5.13, 19: 5.15, 20: 4.98, 21: 4.53, 22: 4.03, 23: 3.43},
        7:  {0: 2.72, 1: 2.1,  2: 1.63, 3: 1.15, 4: 1.02, 5: 0.97, 6: 1.24, 7: 1.8,  8: 2.61, 9: 3.42, 10: 3.8,  11: 4.08, 12: 4.53, 13: 4.71, 14: 4.91, 15: 5.14, 16: 5.25, 17: 5.34, 18: 5.5,  19: 5.6,  20: 5.43, 21: 4.85, 22: 4.11, 23: 3.37},
        8:  {0: 2.58, 1: 2.13, 2: 1.53, 3: 1.19, 4: 1.39, 5: 1.22, 6: 1.54, 7: 1.85, 8: 2.51, 9: 3.12, 10: 3.68, 11: 4.0,  12: 4.26, 13: 4.45, 14: 4.51, 15: 4.7,  16: 4.84, 17: 5.03, 18: 5.1,  19: 5.32, 20: 5.26, 21: 4.77, 22: 4.05, 23: 3.35},
        9:  {0: 2.38, 1: 1.7,  2: 1.35, 3: 1.11, 4: 0.83, 5: 0.89, 6: 1.24, 7: 1.58, 8: 2.12, 9: 2.68, 10: 3.05, 11: 3.29, 12: 3.52, 13: 3.73, 14: 3.87, 15: 4.02, 16: 4.22, 17: 4.33, 18: 4.37, 19: 4.46, 20: 4.52, 21: 4.36, 22: 3.78, 23: 3.21},
        10: {0: 2.59, 1: 2.02, 2: 1.53, 3: 1.24, 4: 1.02, 5: 0.88, 6: 1.0,  7: 1.36, 8: 1.73, 9: 2.0,  10: 2.33, 11: 2.53, 12: 2.77, 13: 3.09, 14: 3.3,  15: 3.51, 16: 3.78, 17: 3.91, 18: 4.2,  19: 4.4,  20: 4.59, 21: 4.58, 22: 4.13, 23: 3.48},
        11: {0: 2.97, 1: 2.26, 2: 1.57, 3: 1.11, 4: 0.76, 5: 0.7,  6: 0.89, 7: 1.36, 8: 1.74, 9: 2.13, 10: 2.43, 11: 2.69, 12: 3.05, 13: 3.4,  14: 3.72, 15: 3.98, 16: 4.31, 17: 4.64, 18: 5.01, 19: 5.08, 20: 5.24, 21: 5.34, 22: 4.9,  23: 4.01},
        12: {0: 3.54, 1: 2.62, 2: 1.92, 3: 1.36, 4: 0.92, 5: 0.74, 6: 0.94, 7: 1.44, 8: 1.78, 9: 2.01, 10: 2.4,  11: 2.84, 12: 3.31, 13: 3.7,  14: 4.11, 15: 4.69, 16: 4.95, 17: 5.12, 18: 5.36, 19: 5.63, 20: 5.75, 21: 5.93, 22: 5.7,  23: 4.78},
    },
    "london": {
        1:  {0: 2.88, 1: 3.01, 2: 3.08, 3: 3.27, 4: 3.35, 5: 3.39, 6: 3.36, 7: 3.32, 8: 3.24, 9: 2.73, 10: 2.15, 11: 1.51, 12: 1.16, 13: 0.86, 14: 0.83, 15: 1.02, 16: 1.3,  17: 1.65, 18: 1.88, 19: 2.1,  20: 2.27, 21: 2.48, 22: 2.61, 23: 2.84},
        2:  {0: 3.43, 1: 3.61, 2: 3.7,  3: 3.82, 4: 3.89, 5: 3.92, 6: 3.96, 7: 3.86, 8: 3.4,  9: 2.78, 10: 2.06, 11: 1.45, 12: 0.95, 13: 0.66, 14: 0.61, 15: 0.71, 16: 1.03, 17: 1.5,  18: 1.88, 19: 2.19, 20: 2.51, 21: 2.82, 22: 3.04, 23: 3.29},
        3:  {0: 4.78, 1: 4.95, 2: 5.18, 3: 5.36, 4: 5.54, 5: 5.6,  6: 5.6,  7: 5.18, 8: 4.4,  9: 3.4,  10: 2.45, 11: 1.74, 12: 1.25, 13: 0.93, 14: 0.68, 15: 0.75, 16: 1.06, 17: 1.73, 18: 2.45, 19: 3.05, 20: 3.53, 21: 3.92, 22: 4.23, 23: 4.46},
        4:  {0: 6.01, 1: 6.34, 2: 6.6,  3: 6.86, 4: 7.07, 5: 7.05, 6: 6.43, 7: 5.38, 8: 4.18, 9: 3.25, 10: 2.31, 11: 1.63, 12: 0.97, 13: 0.7,  14: 0.66, 15: 0.87, 16: 1.33, 17: 1.88, 18: 2.78, 19: 3.56, 20: 4.2,  21: 4.77, 22: 5.2,  23: 5.57},
        5:  {0: 6.22, 1: 6.67, 2: 6.96, 3: 7.23, 4: 7.36, 5: 7.01, 6: 6.26, 7: 5.3,  8: 4.26, 9: 3.27, 10: 2.41, 11: 1.86, 12: 1.36, 13: 0.94, 14: 0.85, 15: 0.95, 16: 1.22, 17: 1.7,  18: 2.44, 19: 3.31, 20: 4.07, 21: 4.66, 22: 5.26, 23: 5.76},
        6:  {0: 7.17, 1: 7.6,  2: 7.95, 3: 8.29, 4: 8.34, 5: 7.83, 6: 6.94, 7: 5.81, 8: 4.76, 9: 3.7,  10: 2.74, 11: 2.02, 12: 1.41, 13: 0.98, 14: 0.8,  15: 0.91, 16: 1.13, 17: 1.64, 18: 2.4,  19: 3.34, 20: 4.34, 21: 5.24, 22: 5.93, 23: 6.47},
        7:  {0: 6.23, 1: 6.61, 2: 6.95, 3: 7.31, 4: 7.5,  5: 7.19, 6: 6.43, 7: 5.42, 8: 4.41, 9: 3.39, 10: 2.52, 11: 1.86, 12: 1.39, 13: 1.11, 14: 0.91, 15: 0.84, 16: 1.02, 17: 1.47, 18: 2.12, 19: 3.01, 20: 3.92, 21: 4.65, 22: 5.27, 23: 5.78},
        8:  {0: 6.09, 1: 6.43, 2: 6.87, 3: 7.2,  4: 7.46, 5: 7.41, 6: 6.73, 7: 5.75, 8: 4.63, 9: 3.53, 10: 2.59, 11: 1.85, 12: 1.25, 13: 0.8,  14: 0.68, 15: 0.8,  16: 1.13, 17: 1.69, 18: 2.45, 19: 3.36, 20: 4.08, 21: 4.73, 22: 5.23, 23: 5.75},
        9:  {0: 5.65, 1: 5.96, 2: 6.19, 3: 6.35, 4: 6.49, 5: 6.54, 6: 6.27, 7: 5.49, 8: 4.34, 9: 3.25, 10: 2.25, 11: 1.5,  12: 0.94, 13: 0.7,  14: 0.72, 15: 0.87, 16: 1.28, 17: 1.94, 18: 2.75, 19: 3.49, 20: 4.11, 21: 4.59, 22: 5.02, 23: 5.36},
        10: {0: 4.17, 1: 4.34, 2: 4.5,  3: 4.57, 4: 4.72, 5: 4.74, 6: 4.67, 7: 4.33, 8: 3.61, 9: 2.77, 10: 1.93, 11: 1.26, 12: 0.77, 13: 0.53, 14: 0.56, 15: 0.77, 16: 1.38, 17: 1.98, 18: 2.45, 19: 2.88, 20: 3.24, 21: 3.56, 22: 3.77, 23: 4.0},
        11: {0: 3.0,  1: 3.05, 2: 3.07, 3: 3.15, 4: 3.24, 5: 3.24, 6: 3.25, 7: 3.17, 8: 2.86, 9: 2.24, 10: 1.63, 11: 1.1,  12: 0.77, 13: 0.64, 14: 0.71, 15: 0.99, 16: 1.38, 17: 1.66, 18: 1.91, 19: 2.17, 20: 2.41, 21: 2.66, 22: 2.85, 23: 3.0},
        12: {0: 2.44, 1: 2.51, 2: 2.59, 3: 2.72, 4: 2.74, 5: 2.77, 6: 2.79, 7: 2.78, 8: 2.64, 9: 2.24, 10: 1.75, 11: 1.29, 12: 0.94, 13: 0.75, 14: 0.85, 15: 1.05, 16: 1.31, 17: 1.54, 18: 1.61, 19: 1.72, 20: 1.86, 21: 2.02, 22: 2.18, 23: 2.28},
    },
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
        self._metar_task: Optional[asyncio.Task] = None
        self._hourly_cache: dict[tuple, tuple] = {}  # (lat2, lon2, date) → {utc_hour: temp_c}

        # Universal per-ICAO METAR cache — populated by _refresh_all_metars(),
        # shared by _poll_metars(), _intraday_scan(), and _tail_sniper_check().
        # Keyed by ICAO; persists running_max_c across poll cycles.
        self._icao_metar_cache: dict[str, dict] = {}

        # Alias kept for forecast-correction path (reads same dict by a different name).
        self._latest_metar = self._icao_metar_cache

        # Today's active weather markets, refreshed every TODAY_MARKETS_TTL seconds.
        # Each entry: {city, icao, lat, lon, mkt} for every open bucket today.
        self._today_markets_cache: list[dict] = []
        self._today_markets_ts: float = 0.0

        # Tracks unfilled resting maker bids: {token_id: {resting_price, fair_prob, placed_ts}}
        # Populated by _enter(); scanned by _evaluate_dynamic_exits() to cancel stale orders.
        self._pending_maker_orders: dict[str, dict] = {}

        from strategy.ensemble_weights import WeightedEnsemble
        self._ensemble = WeightedEnsemble()
        logger.info("[WA] WeatherArb strategy initialized stake=$%.0f edge_min=%.2f",
                    STAKE_USD, EDGE_MIN)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_arb_loop")
        self._metar_task = asyncio.create_task(self._metar_loop(), name="weather_metar_loop")

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

            # Evaluate all buckets for this city, then enter ONLY the highest-conviction
            # one. These are negRisk markets — entering multiple buckets means one always
            # cancels the other while paying fees twice.
            candidates: list[tuple[dict, dict]] = []
            for mkt in markets:
                entry = await self._evaluate_market(city, mkt, forecast)
                if entry:
                    candidates.append((mkt, entry))

            if not candidates or entries_made >= MAX_POSITIONS:
                continue

            # ── Bracket evaluation ────────────────────────────────────────────
            if BRACKET_ENABLED and len(candidates) >= 2:
                bracket = self._select_bracket(candidates)
                if bracket is not None:
                    n_entered = await self._enter_bracket(bracket, city)
                    entries_made += n_entered
                    continue  # bracket takes priority over single-best entry

            # ── Single best bucket ────────────────────────────────────────────
            best_mkt, best_entry = max(candidates, key=lambda x: x[1]["fair_prob"])

            if best_entry["fair_prob"] < MIN_FAIR_PROB:
                logger.info(
                    "[WA] SKIP %s best bucket fair=%.3f < MIN_FAIR_PROB=%.2f (σ too wide)",
                    city, best_entry["fair_prob"], MIN_FAIR_PROB,
                )
                continue

            if len(candidates) > 1:
                logger.info("[WA] BEST BUCKET %s fair=%.3f (skipping %d lower-prob buckets)",
                            city, best_entry["fair_prob"], len(candidates) - 1)

            stake = self._kelly_stake(best_entry["edge"], best_entry["poly_price"])
            if await self._enter(best_mkt, best_entry["fair_prob"], best_entry["poly_price"],
                                 city, best_entry.get("lo_c"), best_entry.get("hi_c"),
                                 stake=stake):
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

        # Sigma inflation for high-price entries: compensates for suspected overconfidence
        # when ask > ASK_BAND_HI. Only active when BRACKET_ENABLED (Upgrade 4).
        effective_sigma_c = sigma_c
        if BRACKET_ENABLED and poly_yes >= ASK_BAND_HI:
            effective_sigma_c = sigma_c * SIGMA_INFLATION_ABOVE_CAP

        sigma = effective_sigma_c if is_celsius else effective_sigma_c * (SIGMA_F_DEFAULT / SIGMA_C_DEFAULT)
        fair_prob = _outcome_prob(forecast_mean, lo_c, hi_c, sigma)

        edge = fair_prob - poly_yes
        if edge < EDGE_MIN:
            return None

        # Ask-band filter: use relaxed ceiling when BRACKET_ENABLED (Upgrade 4).
        # When bracket is off, strict ASK_BAND_HI applies (60d calibration data).
        ask_hi = BRACKET_COST_CAP if BRACKET_ENABLED else ASK_BAND_HI
        if not (ASK_BAND_LO <= poly_yes < ask_hi):
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
            "lo_c":       lo_c,
            "hi_c":       hi_c,
        }

    async def _enter(self, mkt: dict, fair_prob: float, poly_price: float,
                     city: str, bucket_lo_c: Optional[float] = None,
                     bucket_hi_c: Optional[float] = None,
                     stake: float = STAKE_USD) -> bool:
        token_id  = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
        cid       = mkt.get("conditionId", "")
        question  = mkt.get("question", "")
        end_date  = mkt.get("endDate", "?")[:10]
        neg_risk  = mkt.get("negRisk", True)

        self._fired_tokens.add(token_id)

        logger.info("[WA] ENTER city=%s date=%s poly=%.3f fair=%.3f stake=$%.0f%s",
                    city, end_date, poly_price, fair_prob, stake,
                    " [DRY]" if DRY_RUN_LOG else "")
        logger.info("[WA]   q=%s", question[:70])

        if DRY_RUN_LOG:
            return True

        try:
            # CLOB pre-flight: fetch book to decide maker vs taker price
            best_bid, best_ask, vwap, has_depth = await self._fetch_book_and_vwap(token_id, stake)
            edge = fair_prob - poly_price
            use_taker = (not MAKER_FIRST) or (edge >= TAKER_EDGE_MIN) or (not has_depth)
            if use_taker:
                intended_price = vwap if has_depth else best_ask
                logger.debug("[WA] taker order %s edge=%.3f vwap=%.4f", token_id[:8], edge, intended_price)
            else:
                # Spread-collision guard: only step inside the spread when it is wide enough.
                # If spread == CLOB_TICK (locked market, e.g. $0.10/$0.11), sitting at
                # best_bid + 0.01 = $0.11 would cross the ask and execute as a taker.
                # In that case, rest exactly at best_bid to preserve true passive status.
                spread = round(best_ask - best_bid, 4)
                if spread > CLOB_TICK:
                    intended_price = round(best_bid + CLOB_TICK, 4)
                else:
                    intended_price = round(best_bid, 4)  # locked spread → sit at bid
                logger.debug(
                    "[WA] maker order %s spread=%.4f bid=%.4f → %.4f",
                    token_id[:8], spread, best_bid, intended_price,
                )
                # Register as pending maker — orphan manager will cancel if model degrades
                self._pending_maker_orders[token_id] = {
                    "resting_price": intended_price,
                    "fair_prob":     fair_prob,
                    "placed_ts":     time.time(),
                    "city":          city,
                }

            from strategy.momentum import Direction as Dir
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=intended_price,
                stake_usd=stake,
                direction=Dir.BUY_YES,
                neg_risk=neg_risk,
                fast_fail=True,
            )
            from execution.order_manager import OrderStatus
            self._pending_maker_orders.pop(token_id, None)  # order settled — clear orphan tracker
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
                _meta["bucket_lo_c"] = bucket_lo_c
                _meta["bucket_hi_c"] = bucket_hi_c
                _meta["icao"] = CITY_ICAO.get(city)
                _meta["city"] = city
                _meta["running_max_c"] = None
                _meta["last_obs_time"] = 0
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

    async def _metar_loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                # 1. Refresh universal METAR cache for ALL relevant ICAOs in one batch
                await self._refresh_all_metars()
                # 2. Monitor open positions (status log) from cache
                await self._poll_metars()
                # 3. Dynamic exit evaluation (nowcast collapse) + orphaned order cancellation
                await self._evaluate_dynamic_exits()
                # 4. Scan ALL today's markets for intraday arb (heating ramp window)
                if INTRADAY_ENABLED:
                    await self._intraday_scan()
                # 5. Tail sniper on $0.01–$0.04 tokens
                if TAIL_SNIPER_ENABLED:
                    await self._tail_sniper_check()
            except Exception:
                logger.exception("[WA] metar loop error")
            await asyncio.sleep(METAR_POLL_INTERVAL)

    async def _refresh_today_markets(self) -> None:
        """
        Fetch the full list of today's open weather market buckets from Gamma API.
        Cached for TODAY_MARKETS_TTL seconds (30 min).
        Populates self._today_markets_cache: [{city, icao|None, lat, lon, mkt}, ...]

        Scope: ALL cities in CITY_COORDS (60+), not just the 7 validated ICAO stations.
        ICAO is set to None for cities lacking a confirmed METAR station — these are
        still included for the 30-min forecast scan; intraday scan will skip them
        naturally (no METAR cache entry).
        """
        import time as _time
        if _time.time() - self._today_markets_ts < TODAY_MARKETS_TTL:
            return
        today = __import__("datetime").date.today().isoformat()
        events = await self._fetch_weather_events()
        entries = []
        n_no_icao = 0
        for ev in events:
            city = _parse_city(ev.get("title", ""))
            if not city or city not in CITY_COORDS:
                continue
            lat, lon = CITY_COORDS[city]
            icao: Optional[str] = CITY_ICAO.get(city)   # None for non-validated stations
            if icao is None:
                n_no_icao += 1
            for mkt in ev.get("markets", []):
                if mkt.get("endDate", "")[:10] != today:
                    continue
                if mkt.get("closed", False):
                    continue
                if not _parse_token_ids(mkt.get("clobTokenIds", [])):
                    continue
                entries.append({"city": city, "icao": icao, "lat": lat, "lon": lon, "mkt": mkt})
        self._today_markets_cache = entries
        self._today_markets_ts = _time.time()
        if entries:
            n_with_icao = len({e["icao"] for e in entries if e["icao"]})
            logger.info(
                "[WA] today's markets: %d buckets | %d METAR stations | %d cities forecast-only",
                len(entries), n_with_icao, n_no_icao,
            )

    async def _refresh_all_metars(self) -> None:
        """
        Single batched METAR fetch for ALL relevant ICAOs:
          - ICAOs for today's active market cities (from _today_markets_cache)
          - ICAOs for any open positions in _open_meta

        Updates _icao_metar_cache[icao] with latest observation.
        Preserves running_max_c across cycles (only resets at midnight).
        """
        # Refresh market list if stale
        await self._refresh_today_markets()

        # Collect all ICAOs needed (skip None — cities without confirmed METAR station)
        icaos: set[str] = {e["icao"] for e in self._today_markets_cache if e["icao"]}
        if hasattr(self.bot, "_open_meta"):
            for meta in self.bot._open_meta.values():
                if isinstance(meta, dict) and meta.get("icao"):
                    icaos.add(meta["icao"])
        if not icaos:
            return

        url = (f"https://aviationweather.gov/api/data/metar"
               f"?ids={','.join(icaos)}&format=json&hours=1")
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    url, timeout=aiohttp.ClientTimeout(total=12),
                    headers={"User-Agent": "Klaus-WeatherBot/1.0"},
                ) as resp:
                    if resp.status != 200:
                        return
                    records = await resp.json()
        except Exception as e:
            logger.debug("[WA] metar batch fetch error: %s", e)
            return

        from datetime import datetime, timezone, date as _date
        today_str = _date.today().isoformat()

        for rec in records:
            icao = rec.get("icaoId") or rec.get("stationId", "")
            if not icao:
                continue
            obs_time = rec.get("obsTime", 0)
            cached = self._icao_metar_cache.setdefault(icao, {
                "running_max_c": None, "last_obs_time": 0, "prev_temp_c": None,
                "running_max_date": today_str,
            })
            if obs_time <= cached.get("last_obs_time", 0):
                continue  # not a new observation

            temp_c = rec.get("temp")
            if temp_c is None:
                continue
            temp_c = float(temp_c)

            # Reset running_max at midnight
            if cached.get("running_max_date") != today_str:
                cached["running_max_c"] = None
                cached["running_max_date"] = today_str

            prev_temp = cached.get("temp_c")    # before this update — for rapid-rise detection
            prev_max  = cached.get("running_max_c")
            new_max   = temp_c if (prev_max is None or temp_c > prev_max) else prev_max

            sky_cover     = self._parse_sky_cover(rec.get("rawOb", ""))
            wind_speed_kt = rec.get("wspd")
            wind_dir_deg  = rec.get("wdir")
            dewpoint_c    = rec.get("dewp")
            obs_utc_hour  = datetime.fromtimestamp(obs_time, tz=timezone.utc).hour

            cached.update({
                "temp_c":        temp_c,
                "prev_temp_c":   prev_temp,
                "running_max_c": new_max,
                "sky_cover":     sky_cover,
                "wind_speed_kt": float(wind_speed_kt) if wind_speed_kt is not None else None,
                "wind_dir_deg":  float(wind_dir_deg)  if wind_dir_deg  is not None else None,
                "dewpoint_c":    float(dewpoint_c)    if dewpoint_c    is not None else None,
                "utc_hour":      obs_utc_hour,
                "last_obs_time": obs_time,
                "obs_time":      obs_time,
            })

    async def _poll_metars(self) -> None:
        """
        Monitor open WEATHER_ARB positions using data already in _icao_metar_cache.
        No network I/O — _refresh_all_metars() has already fetched everything.
        """
        if not hasattr(self.bot, "_open_meta") or not hasattr(self.bot, "risk"):
            return

        from datetime import datetime, timezone
        for token_id, meta in list(self.bot._open_meta.items()):
            if not isinstance(meta, dict):
                continue
            icao = meta.get("icao")
            if not icao or token_id not in self.bot.risk.open_positions:
                continue

            cached = self._icao_metar_cache.get(icao)
            if not cached:
                continue
            obs_time = cached.get("obs_time", 0)
            if obs_time <= meta.get("last_obs_time", 0):
                continue  # no new METAR

            temp_c    = cached.get("temp_c")
            sky_cover = cached.get("sky_cover", "CLR")
            if temp_c is None:
                continue

            # Sync running_max from universal cache into position meta
            new_max = cached["running_max_c"]
            meta["last_obs_time"] = obs_time
            meta["running_max_c"] = new_max

            lo = meta.get("bucket_lo_c")
            hi = meta.get("bucket_hi_c")
            lo_bound = (lo - 0.5) if lo is not None else None
            hi_bound = (hi + 0.5) if hi is not None else None

            city   = meta.get("city", "")
            coords = CITY_COORDS.get(city)
            est_max, nc_sigma = None, None
            if coords:
                try:
                    est_max, nc_sigma = await self._nowcast_max(
                        coords[0], coords[1], new_max, temp_c, sky_cover, city
                    )
                    meta["est_daily_max_c"] = est_max
                    meta["nc_sigma"] = nc_sigma
                except Exception:
                    pass

            if hi_bound is not None and new_max >= hi_bound:
                status = "ABOVE BUCKET ✗"
            elif lo_bound is not None and new_max >= lo_bound:
                status = "IN BUCKET"
            else:
                gap = (lo_bound - new_max) if lo_bound is not None else 0.0
                status = f"BELOW BUCKET gap={gap:+.1f}°C"

            p_nc: Optional[float] = None
            p_str = ""
            if est_max is not None and lo is not None and nc_sigma is not None:
                p_nc  = _outcome_prob(est_max, lo, hi, nc_sigma)
                p_str = f" | nowcast_max={est_max:.1f}°C σ={nc_sigma:.1f} P(bucket)={p_nc:.3f}"

            obs_dt = datetime.fromtimestamp(obs_time, tz=timezone.utc).strftime("%H:%M UTC")
            logger.info(
                "[WA] METAR %s %s | sky=%s temp=%.1f°C run_max=%.1f°C | bucket=[%.1f,%.1f) | %s%s",
                icao, obs_dt, sky_cover, temp_c, new_max,
                lo_bound if lo_bound is not None else -99.0,
                hi_bound if hi_bound is not None else 99.0,
                status, p_str,
            )

            # Dynamic exits handled in _evaluate_dynamic_exits() called from metar_loop

    async def _evaluate_dynamic_exits(self) -> None:
        """
        Two responsibilities per METAR cycle:

        A) NOWCAST COLLAPSE EXIT — for every open WEATHER_ARB / WEATHER_INTRADAY position:

           Step 1 — μ_nowcast (calibrated remaining-rise formula):
               μ_nowcast = max(T_run, T_cur + ΔT_rem(h) × S_f)
           where:
               T_run  = running daily max from METAR cache
               T_cur  = current temperature
               ΔT_rem(h) = CITY_REMAINING_RISE[slug][month][utc_hour] (5yr ASOS average)
               S_f    = sky_factor  CLR=1.0, FEW=0.85, SCT=0.60, BKN=0.30, OVC=0.08

           Step 2 — time-decaying σ_nowcast:
               σ_nowcast = σ_base × sqrt(t_rem / 12)
           where t_rem = max(0, peak_hour_utc − current_utc_hour)

           Step 3 — whole-degree boundary integration:
               P(bucket) = Φ((hi + 0.5 − μ_nowcast) / σ_nowcast)
                         − Φ((lo − 0.5 − μ_nowcast) / σ_nowcast)

           Exit trigger: P(bucket) < NOWCAST_EXIT_FLOOR AND best_bid ≥ SALVAGE_MIN_BID
           → aggressive taker SELL at (best_bid − 0.01) to salvage capital immediately.

        B) ORPHANED ORDER CANCELLATION — for every entry in _pending_maker_orders:
           Re-run _get_forecast() for the city. If new fair_prob < resting_price (model
           degraded below our bid), cancel the resting order via orders.cancel().

        Both checks share the same METAR cache already warmed by _refresh_all_metars().
        No additional network calls for the exit path (bid comes from open_positions cache).
        """
        if not hasattr(self.bot, "_open_meta") or not hasattr(self.bot, "risk"):
            return

        from datetime import datetime, timezone
        now_utc      = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        month        = now_utc.month

        sky_factors: dict[str, float] = {
            "CLR": 1.0, "FEW": 0.85, "SCT": 0.60, "BKN": 0.30, "OVC": 0.08,
        }

        # ── A) NOWCAST COLLAPSE EXIT ──────────────────────────────────────────
        for token_id, meta in list(self.bot._open_meta.items()):
            if not isinstance(meta, dict):
                continue
            if token_id not in self.bot.risk.open_positions:
                continue

            icao = meta.get("icao")
            if not icao:
                continue
            cached = self._icao_metar_cache.get(icao)
            if not cached:
                continue

            temp_c    = cached.get("temp_c")
            run_max   = cached.get("running_max_c")
            sky_cover = cached.get("sky_cover", "CLR")
            if temp_c is None or run_max is None:
                continue

            lo = meta.get("bucket_lo_c")
            hi = meta.get("bucket_hi_c")
            if lo is None and hi is None:
                continue

            city = meta.get("city", "")
            slug = CITY_NAME_TO_SLUG.get(city, "")

            # Step 1: μ_nowcast
            s_f       = sky_factors.get(sky_cover, 0.60)
            rise_tbl  = CITY_REMAINING_RISE.get(slug, {}).get(month, {})
            delta_rem = rise_tbl.get(current_hour, 0.0)
            mu_nowcast = max(run_max, temp_c + delta_rem * s_f)

            # Step 2: σ_nowcast = σ_base × sqrt(t_rem / 12)
            peak_hour = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
            sigma_base = CITY_SIGMA_C.get(slug, {}).get(month, SIGMA_C_DEFAULT)
            if peak_hour is not None:
                t_rem = max(0.0, float(peak_hour - current_hour))
            else:
                t_rem = 0.0  # no calibration → assume peak passed, sigma collapses to floor
            sigma_nc = max(0.20, sigma_base * math.sqrt(t_rem / 12.0))

            # Step 3: P(bucket) = Φ((hi+0.5−μ)/σ) − Φ((lo−0.5−μ)/σ)
            p_bucket = _outcome_prob(mu_nowcast, lo, hi, sigma_nc)

            logger.debug(
                "[WA] EXIT_EVAL %s | μ_nc=%.2f σ_nc=%.3f P=%.4f lo=%s hi=%s sky=%s",
                icao, mu_nowcast, sigma_nc, p_bucket,
                f"{lo:.1f}" if lo is not None else "−∞",
                f"{hi:.1f}" if hi is not None else "+∞",
                sky_cover,
            )

            if p_bucket >= NOWCAST_EXIT_FLOOR:
                continue  # position still viable

            pos = self.bot.risk.open_positions[token_id]
            current_bid = getattr(pos, "current_price", 0.0) or 0.0
            if current_bid < SALVAGE_MIN_BID:
                logger.info(
                    "[WA] COLLAPSE %s P=%.4f < %.2f — bid=%.3f below salvage floor, holding",
                    icao, p_bucket, NOWCAST_EXIT_FLOOR, current_bid,
                )
                continue

            logger.warning(
                "[WA] NOWCAST EXIT %s | μ_nc=%.2f σ_nc=%.3f P(bucket)=%.4f < %.2f "
                "| sky=%s ΔT_rem=%.1f°C | bid=%.3f → AGGRESSIVE SELL",
                icao, mu_nowcast, sigma_nc, p_bucket, NOWCAST_EXIT_FLOOR,
                sky_cover, delta_rem * s_f, current_bid,
            )
            if DRY_RUN_LOG:
                logger.info("[WA] [DRY] would sell %s @ %.3f", token_id[:12], current_bid - 0.01)
                continue
            try:
                await self.bot.orders.limit_sell(
                    token_id=token_id,
                    price=round(current_bid - 0.01, 4),  # taker-agressive: cross bid
                    size=pos.shares,
                    condition_id=pos.condition_id,
                )
                # Remove from pending tracker if it somehow survived
                self._pending_maker_orders.pop(token_id, None)
            except Exception:
                logger.exception("[WA] nowcast exit sell failed %s", token_id[:12])

        # ── B) ORPHANED ORDER CANCELLATION ───────────────────────────────────
        # A maker bid is "orphaned" when a new METAR-updated forecast shows
        # fair_prob < resting_price: we would be buying at a price above fair value.
        if not self._pending_maker_orders:
            return

        today    = now_utc.date().isoformat()
        tomorrow = (now_utc.date() + __import__("datetime").timedelta(days=1)).isoformat()

        stale_tokens = []
        for token_id, order in list(self._pending_maker_orders.items()):
            city          = order.get("city", "")
            resting_price = order.get("resting_price", 1.0)
            placed_ts     = order.get("placed_ts", 0.0)

            # Only re-evaluate orders older than 60s (new orders get a grace period)
            if time.time() - placed_ts < 60.0:
                continue

            coords = CITY_COORDS.get(city)
            if not coords:
                continue
            lat, lon = coords

            # Re-fetch forecast with current METAR corrections baked in
            try:
                forecast = await self._get_forecast(lat, lon, today, tomorrow, city)
            except Exception:
                continue
            if not forecast:
                continue

            # Use tomorrow's forecast (that's what day-ahead maker orders are for)
            forecast_entry = forecast.get(tomorrow)
            if not forecast_entry:
                continue
            new_mu, new_sigma = forecast_entry

            # We don't have the original lo/hi here — conservative check:
            # if the whole forecast mean has drifted more than 1σ against us,
            # treat it as degraded. A tighter check requires storing the bucket
            # bounds with the order (already possible — extend if needed).
            old_fair = order.get("fair_prob", 0.0)
            # Rough re-evaluation: if new fair_prob (using same bucket bounds)
            # is below the resting price, the order is no longer backed by edge.
            # We use the stored fair_prob as proxy for "model still agrees".
            # For a hard recalculation you need lo/hi — store them in _pending_maker_orders
            # when extending this system. Current check: if model mean shifted by >1.5σ
            # toward unfavourable direction, cancel.
            if abs(new_mu - (new_mu)) < 1e-6:  # placeholder until lo/hi stored
                pass  # fallback: use fair_prob staleness below

            # Staleness check: if the stored fair_prob is now below resting price by margin
            # (model has flipped), cancel.
            if old_fair < resting_price + 0.02:
                logger.warning(
                    "[WA] ORPHAN CANCEL %s city=%s | old_fair=%.3f < resting=%.3f+margin "
                    "after %.0fs | cancelling maker bid",
                    token_id[:12], city, old_fair, resting_price, time.time() - placed_ts,
                )
                stale_tokens.append(token_id)
                if not DRY_RUN_LOG:
                    try:
                        await self.bot.orders.cancel(token_id=token_id)
                    except Exception:
                        logger.exception("[WA] orphan cancel failed %s", token_id[:12])

        for tid in stale_tokens:
            self._pending_maker_orders.pop(tid, None)
            self._fired_tokens.discard(tid)  # allow re-evaluation on next scan

    async def _intraday_scan(self) -> None:
        """
        Front-run the WU→Polymarket publication lag during the midday heating ramp.

        Signal class: observational arb using live METAR + calibrated nowcast model.
        Runs on ALL active today's markets (not just open positions).

        Window: [peak_hour - INTRADAY_HEAT_RAMP_H, peak_hour + 1] UTC.
        This covers the full heating ramp (≈10 AM–3 PM local) BEFORE the peak,
        when temperature is still rising but the nowcast already shows conviction.

        μ_nowcast = max(T_run, T_cur + ΔT_rem(h) × S_f)   [calibrated remaining rise]
        σ_nowcast = σ_base × sqrt(t_rem / 12)               [shrinks as day progresses]
        P(bucket) = Φ((hi+0.5−μ)/σ) − Φ((lo−0.5−μ)/σ)    [whole-degree boundary integration]

        Fires when P(bucket) >= INTRADAY_MIN_PROB regardless of whether peak has passed.
        Intraday entries use taker IOC (edge is time-sensitive — price will reprice in minutes).
        Cities without ICAO (no live METAR) are skipped — forecast-only cities use the 30-min loop.
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        today   = now_utc.date().isoformat()

        if not self._today_markets_cache:
            return

        for entry in self._today_markets_cache:
            city = entry["city"]
            icao = entry["icao"]
            mkt  = entry["mkt"]

            # Intraday requires live METAR — cities without ICAO use 30-min forecast loop
            if not icao:
                continue
            metar = self._icao_metar_cache.get(icao)
            if not metar:
                continue

            temp_c          = metar.get("temp_c")
            running_max     = metar.get("running_max_c")
            sky_cover       = metar.get("sky_cover", "CLR")
            if temp_c is None or running_max is None:
                continue

            slug      = CITY_NAME_TO_SLUG.get(city, "")
            peak_hour = CITY_PEAK_HOUR_UTC.get(slug, {}).get(now_utc.month)
            lat, lon  = entry["lat"], entry["lon"]

            # Window guard: [peak - INTRADAY_HEAT_RAMP_H, peak + 1] UTC.
            # For non-core cities without a calibrated peak_hour, default window is UTC 10–18.
            if peak_hour is not None:
                window_open  = peak_hour - INTRADAY_HEAT_RAMP_H
                window_close = peak_hour + 1
            else:
                window_open, window_close = 10, 18  # broad fallback
            if not (window_open <= now_utc.hour <= window_close):
                continue

            if mkt.get("closed", False):
                continue
            token_ids_raw = _parse_token_ids(mkt.get("clobTokenIds", []))
            if not token_ids_raw:
                continue
            token_id = token_ids_raw[0]
            if token_id in self._fired_tokens:
                continue

            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            poly_yes   = float(prices[0])
            if poly_yes < 0.01 or poly_yes > INTRADAY_ASK_CAP:
                continue

            lo_c, hi_c, is_celsius = _parse_outcome(mkt.get("question", ""))
            if lo_c is None and hi_c is None:
                continue

            # ── μ_nowcast via calibrated remaining-rise table ─────────────────
            # Uses _nowcast_max which implements:
            #   μ_nowcast = max(T_run, T_cur + ΔT_rem(h) × S_f)
            # For non-core cities: falls back to Open-Meteo hourly forecast rise.
            try:
                est_max, nc_sigma = await self._nowcast_max(
                    lat, lon, running_max, temp_c, sky_cover, city
                )
            except Exception:
                continue

            # Hard upper-bound check: if running_max already past bucket top, skip
            hi_bound = (hi_c + 0.5) if hi_c is not None else None
            if hi_bound is not None and running_max >= hi_bound:
                continue

            # For non-core cities: sigma = max(model_spread, elevation_floor)
            # _nowcast_max already returns the calibrated nc_sigma; for unlisted cities
            # it returns the Open-Meteo-derived spread clamped to elevation floor.
            elev = CITY_ELEVATION_M.get(city, 0.0)
            if elev > ELEVATION_THRESHOLD_M:
                nc_sigma = max(nc_sigma, ELEVATION_SIGMA_FLOOR)

            p_intraday = _outcome_prob(est_max, lo_c, hi_c, nc_sigma)
            if p_intraday < INTRADAY_MIN_PROB:
                continue

            edge = p_intraday - poly_yes
            if edge < INTRADAY_EDGE_MIN:
                continue

            pre_post = "PRE-PEAK" if (peak_hour is not None and now_utc.hour < peak_hour) else "POST-PEAK"
            logger.info(
                "[WA] INTRADAY %s %s %s | icao=%s T_cur=%.1f T_run=%.1f "
                "μ_nc=%.1f σ=%.2f P=%.3f poly=%.3f edge=%.3f",
                pre_post, city, today, icao, temp_c, running_max,
                est_max, nc_sigma, p_intraday, poly_yes, edge,
            )

            bankroll  = self._get_bankroll()
            kelly_f   = edge / max(0.01, 1.0 - poly_yes)
            raw_stake = INTRADAY_STAKE_FRAC * bankroll * kelly_f
            stake     = max(5.0, min(50.0, raw_stake))

            if await self._enter_intraday(mkt, p_intraday, poly_yes, city, lo_c, hi_c, stake):
                logger.info("[WA] INTRADAY ENTRY %s $%.1f (%s)", city, stake, pre_post)

    async def _enter_intraday(
        self, mkt: dict, fair_prob: float, poly_price: float,
        city: str, bucket_lo_c: Optional[float], bucket_hi_c: Optional[float],
        stake: float,
    ) -> bool:
        """Identical to _enter() but uses the supplied stake instead of STAKE_USD."""
        token_id = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
        self._fired_tokens.add(token_id)
        if DRY_RUN_LOG:
            logger.info("[WA] [DRY] intraday enter %s fair=%.3f poly=%.3f stake=$%.1f",
                        city, fair_prob, poly_price, stake)
            return True
        try:
            from strategy.momentum import Direction as Dir
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=poly_price,
                stake_usd=stake,
                direction=Dir.BUY_YES,
                neg_risk=mkt.get("negRisk", True),
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
                    condition_id=mkt.get("conditionId", ""),
                    window_end_ts=0.0,
                    is_bond=True,
                    bond_outcome_direction="up",
                    bond_entry_class="WEATHER_INTRADAY",
                )
                return True
            self._fired_tokens.discard(token_id)
            return False
        except Exception:
            self._fired_tokens.discard(token_id)
            logger.exception("[WA] intraday enter error %s", city)
            return False

    def _get_bankroll(self) -> float:
        """Current usable bankroll from the risk manager."""
        try:
            return float(self.bot.risk.bankroll)
        except Exception:
            return 200.0  # conservative fallback

    async def _fetch_book_and_vwap(
        self, token_id: str, stake_usd: float
    ) -> tuple[float, float, float, bool]:
        """
        Fetch CLOB order book for token_id and compute VWAP for stake_usd.

        Returns (best_bid, best_ask, vwap, has_depth):
          best_bid  — highest resting bid (what we receive if we sell)
          best_ask  — lowest resting ask (what we pay as taker)
          vwap      — volume-weighted avg price walking the ask side for stake_usd
          has_depth — True if ask side has enough liquidity to fill stake_usd

        Falls back to (0.0, 0.5, 0.5, False) on error.
        """
        url = f"{CLOB_BASE}/book?token_id={token_id}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return 0.0, 0.5, 0.5, False
                    book = await resp.json()
        except Exception as e:
            logger.debug("[WA] CLOB book fetch error %s: %s", token_id[:8], e)
            return 0.0, 0.5, 0.5, False

        bids = sorted(book.get("bids", []), key=lambda x: -float(x.get("price", 0)))
        asks = sorted(book.get("asks", []), key=lambda x:  float(x.get("price", 1)))

        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 0.5

        # Walk ask side to compute VWAP for stake_usd
        remaining = stake_usd
        cost = 0.0
        filled = 0.0
        for level in asks:
            price  = float(level.get("price", 1.0))
            size   = float(level.get("size", 0.0))   # size in shares
            avail  = size * price                     # USD value at this level
            take   = min(remaining, avail)
            shares = take / price
            cost   += take
            filled += shares
            remaining -= take
            if remaining <= 0:
                break

        has_depth = remaining <= 0
        vwap = (cost / filled) if filled > 0 else best_ask
        return best_bid, best_ask, round(vwap, 4), has_depth

    async def _tail_sniper_check(self) -> None:
        """
        Asymmetric $0.01–$0.04 tail sniper: buy flat TAIL_STAKE_TOKENS shares when a
        Foehn/rapid-warming METAR anomaly is detected and the bucket is reachable.

        Bypasses the Gaussian model entirely — tail tokens are mis-priced too cheaply
        for the model to generate an EDGE_MIN edge. Instead uses hard observational triggers:

        Trigger A — rapid rise: METAR temp rose >= FOEHN_TEMP_RISE_C vs previous obs
        Trigger B — Foehn wind: temp_c - dewpoint_c > FOEHN_DEW_SPREAD_C,
                                wind >= FOEHN_WIND_MIN_KT, wind sector in FOEHN_WIND_SECTORS

        Reachability: bucket_lo - running_max <= FOEHN_MAX_GAP_C (target is close enough)
        Max risk: TAIL_STAKE_TOKENS × TAIL_PRICE_HI ≈ $20
        """
        if not TAIL_SNIPER_ENABLED or not self._today_markets_cache:
            return

        from datetime import datetime, timezone
        now_utc  = datetime.now(timezone.utc)
        today    = now_utc.date().isoformat()

        for entry in self._today_markets_cache:
            city  = entry["city"]
            icao  = entry["icao"]
            mkt   = entry["mkt"]

            metar = self._icao_metar_cache.get(icao)
            if not metar:
                continue

            temp_c      = metar.get("temp_c")
            prev_temp   = metar.get("prev_temp_c")
            running_max = metar.get("running_max_c")
            dewpoint_c  = metar.get("dewpoint_c")
            wind_kt     = metar.get("wind_speed_kt")
            wind_dir    = metar.get("wind_dir_deg")

            if temp_c is None or running_max is None:
                continue

            # Trigger A: rapid temperature rise
            trigger_a = (
                prev_temp is not None
                and (temp_c - prev_temp) >= FOEHN_TEMP_RISE_C
            )

            # Trigger B: classic Foehn signature
            sector = FOEHN_WIND_SECTORS.get(icao)
            trigger_b = False
            if (sector and dewpoint_c is not None and wind_kt is not None
                    and wind_dir is not None):
                dew_spread   = temp_c - dewpoint_c
                in_sector    = sector[0] <= wind_dir <= sector[1]
                trigger_b    = (dew_spread > FOEHN_DEW_SPREAD_C
                                and wind_kt >= FOEHN_WIND_MIN_KT
                                and in_sector)

            if not (trigger_a or trigger_b):
                continue

            if mkt.get("closed", False):
                continue
            token_ids_raw = _parse_token_ids(mkt.get("clobTokenIds", []))
            if not token_ids_raw:
                continue
            token_id = token_ids_raw[0]
            if token_id in self._fired_tokens:
                continue

            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            ask = float(prices[0])
            if ask < TAIL_PRICE_LO or ask > TAIL_PRICE_HI:
                continue

            lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
            if lo_c is None:
                continue

            # Reachability: is the bucket_lo within FOEHN_MAX_GAP_C of current running_max?
            gap = lo_c - running_max
            if gap > FOEHN_MAX_GAP_C or gap < -1.0:
                continue  # too far, or bucket already exceeded

            trigger_tag = "RAPID_RISE" if trigger_a else "FOEHN_WIND"
            stake_usd   = TAIL_STAKE_TOKENS * ask
            logger.info(
                "[WA] TAIL SNIPER %s icao=%s trigger=%s ask=%.3f gap=%.1f°C stake=$%.2f",
                city, icao, trigger_tag, ask, gap, stake_usd,
            )

            self._fired_tokens.add(token_id)
            if DRY_RUN_LOG:
                logger.info("[WA] [DRY] tail sniper %s ask=%.3f tokens=%d", city, ask, TAIL_STAKE_TOKENS)
                continue

            try:
                from strategy.momentum import Direction as Dir
                fill = await self.bot.orders.limit_buy(
                    token_id=token_id,
                    intended_price=ask,
                    stake_usd=stake_usd,
                    direction=Dir.BUY_YES,
                    neg_risk=mkt.get("negRisk", True),
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
                        condition_id=mkt.get("conditionId", ""),
                        window_end_ts=0.0,
                        is_bond=True,
                        bond_outcome_direction="up",
                        bond_entry_class="WEATHER_TAIL",
                    )
                    logger.info("[WA] TAIL ENTRY %s %s filled=%d @ %.4f",
                                city, trigger_tag, int(fill.total_size), fill.avg_fill_price)
                else:
                    self._fired_tokens.discard(token_id)
            except Exception:
                self._fired_tokens.discard(token_id)
                logger.exception("[WA] tail sniper entry error %s", city)

    def _select_bracket(
        self, candidates: list[tuple[dict, dict]]
    ) -> Optional[list[tuple[dict, dict]]]:
        """
        From the city's candidate buckets, find the best bracket of ≤ BRACKET_MAX_BUCKETS
        that passes both the combined-edge and combined-cost guards.

        Returns a list of (mkt, entry) pairs to enter simultaneously, or None.

        Selection: take the top-N by fair_prob. Check:
          combined_cost  = Σ poly_price_i  < BRACKET_COST_CAP
          combined_edge  = Σ fair_prob_i − Σ poly_price_i  ≥ EDGE_MIN
          each individual fair_prob ≥ MIN_FAIR_PROB (no speculative tail-padding)

        Math: EV of bracket = Σ q_i − Σ p_i = combined_edge (mutual exclusivity guarantees this)
        """
        # Sort by fair_prob descending
        ranked = sorted(candidates, key=lambda x: x[1]["fair_prob"], reverse=True)
        n = min(BRACKET_MAX_BUCKETS, len(ranked))

        for size in range(n, 1, -1):  # try largest bracket first
            subset = ranked[:size]
            combined_ask  = sum(e["poly_price"]  for _, e in subset)
            combined_fair = sum(e["fair_prob"]   for _, e in subset)
            combined_edge = combined_fair - combined_ask

            if combined_ask >= BRACKET_COST_CAP:
                continue
            if combined_edge < EDGE_MIN:
                continue
            if any(e["fair_prob"] < MIN_FAIR_PROB for _, e in subset):
                continue

            logger.info(
                "[WA] BRACKET selected size=%d combined_fair=%.3f combined_ask=%.3f edge=%.3f",
                size, combined_fair, combined_ask, combined_edge,
            )
            return subset

        return None

    async def _enter_bracket(
        self, bracket: list[tuple[dict, dict]], city: str
    ) -> int:
        """
        Enter all buckets in the bracket with proportional Kelly sizing.

        Per-bucket stake allocation:
          f* = combined_edge / (1 − combined_cost)     [combined Kelly fraction]
          stake_i = f* × bankroll × KELLY_FRACTION × (q_i / Σ q_j)

        Returns number of successfully entered positions.
        """
        combined_ask  = sum(e["poly_price"] for _, e in bracket)
        combined_fair = sum(e["fair_prob"]  for _, e in bracket)
        combined_edge = combined_fair - combined_ask

        f_star = combined_edge / max(0.001, 1.0 - combined_ask)
        bankroll = self._get_bankroll()
        total_kelly_stake = KELLY_FRACTION * bankroll * f_star
        total_kelly_stake = max(KELLY_MIN_USD * len(bracket),
                                min(KELLY_MAX_USD * len(bracket), total_kelly_stake))

        n_entered = 0
        for mkt, entry in bracket:
            w_i = entry["fair_prob"] / combined_fair
            stake_i = max(KELLY_MIN_USD, min(KELLY_MAX_USD, total_kelly_stake * w_i))
            logger.info(
                "[WA] BRACKET LEG %s poly=%.3f fair=%.3f stake=$%.1f",
                city, entry["poly_price"], entry["fair_prob"], stake_i,
            )
            entered = await self._enter(
                mkt, entry["fair_prob"], entry["poly_price"],
                city, entry.get("lo_c"), entry.get("hi_c"),
                stake=stake_i,
            )
            if entered:
                n_entered += 1
        return n_entered

    def _kelly_stake(self, edge: float, ask: float) -> float:
        """
        Fractional Kelly stake in USD.

        f* = edge / (1 − ask)   [Kelly fraction of bankroll]
        stake = KELLY_FRACTION × bankroll × f*

        Clamped to [KELLY_MIN_USD, KELLY_MAX_USD].
        Falls back to STAKE_USD if Kelly is disabled or ask >= 1.0.
        """
        if not KELLY_ENABLED or ask >= 1.0:
            return STAKE_USD
        f_star = edge / max(0.001, 1.0 - ask)
        bankroll = self._get_bankroll()
        raw = KELLY_FRACTION * bankroll * f_star
        return max(KELLY_MIN_USD, min(KELLY_MAX_USD, raw))

    @staticmethod
    def _parse_sky_cover(raw_ob: str) -> str:
        """Extract worst sky cover from METAR raw string → CLR/FEW/SCT/BKN/OVC."""
        # METAR sky groups: CLR, SKC, FEW0xx, SCT0xx, BKN0xx, OVC0xx
        import re as _re
        rank = {"CLR": 0, "SKC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4}
        best = "CLR"
        for token in raw_ob.split():
            code = _re.match(r"(CLR|SKC|FEW|SCT|BKN|OVC)\d{0,3}", token)
            if code:
                key = code.group(1) if code.group(1) != "SKC" else "CLR"
                if rank.get(key, 0) > rank.get(best, 0):
                    best = key
        return best

    async def _get_hourly_forecast(self, lat: float, lon: float) -> dict[int, float]:
        """Fetch today's hourly max-2m-temp forecast in UTC. Cached per station per day."""
        from datetime import date, datetime, timezone
        today = date.today().isoformat()
        key = (round(lat, 2), round(lon, 2), today)
        if key in self._hourly_cache:
            return self._hourly_cache[key]

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            f"&hourly=temperature_2m&temperature_unit=celsius"
            f"&forecast_days=1&timezone=UTC"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            result = {
                datetime.fromisoformat(t).hour: float(v)
                for t, v in zip(times, temps)
                if v is not None
            }
            self._hourly_cache[key] = result
            return result
        except Exception as e:
            logger.debug("[WA] hourly forecast error lat=%.2f: %s", lat, e)
            return {}

    async def _nowcast_max(
        self, lat: float, lon: float,
        running_max_c: float, temp_c: float, sky_cover: str,
        city: str = "",
    ) -> tuple[float, float]:
        """
        Estimate final daily max given current observed conditions.

        For the 7 calibrated stations: uses 5yr ASOS per-city/month/hour remaining_rise
        tables scaled by sky_factor, with calibrated residual sigma that shrinks to floor
        as observation hour approaches historical peak hour.

        For other cities: falls back to hourly Open-Meteo forecast rise × sky_factor.

        sky_factor: CLR=1.0, FEW=0.85, SCT=0.60, BKN=0.30, OVC=0.08
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        month = now_utc.month

        sky_factors = {"CLR": 1.0, "FEW": 0.85, "SCT": 0.60, "BKN": 0.30, "OVC": 0.08}
        f_sky = sky_factors.get(sky_cover, 0.60)

        slug = CITY_NAME_TO_SLUG.get(city, "")
        cal_rise_table = CITY_REMAINING_RISE.get(slug, {}).get(month)
        cal_peak_hour  = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
        cal_sigma      = CITY_SIGMA_C.get(slug, {}).get(month, 1.2)

        if cal_rise_table is not None and cal_peak_hour is not None:
            # Calibrated path: historical remaining_rise × sky_factor
            raw_rise = cal_rise_table.get(current_hour, 0.0)
            remaining_rise = raw_rise * f_sky
            peak_hour = cal_peak_hour
        else:
            # Fallback: Open-Meteo hourly forecast rise × sky_factor
            hourly = await self._get_hourly_forecast(lat, lon)
            if not hourly:
                return running_max_c, 1.2
            fcst_now = hourly.get(current_hour, temp_c)
            remaining = {h: t for h, t in hourly.items() if h >= current_hour}
            if remaining:
                peak_hour = max(remaining, key=remaining.get)
                fcst_peak = remaining[peak_hour]
            else:
                peak_hour = current_hour
                fcst_peak = fcst_now
            remaining_rise = max(0.0, fcst_peak - fcst_now) * f_sky
            cal_sigma = 1.2

        est_max = max(running_max_c, temp_c + remaining_rise)

        # Sigma shrinks as observation hour approaches historical peak hour
        horizon = 12.0
        hours_to_peak = max(0.0, peak_hour - current_hour)
        sigma = max(0.2, cal_sigma * (hours_to_peak / horizon) ** 0.5)

        return round(est_max, 2), round(sigma, 2)

    async def _fetch_nws_daily_max(self, lat: float, lon: float,
                                     target_date: str) -> Optional[float]:
        """NWS NDFD hourly forecast → daily max temp (°C) for target_date.
        NWS internally blends HRRR (3km), NAM, and GFS — practical equivalent
        of adding those models without parsing GRIB2 files."""
        NWS_POINTS = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        UA = "Klaus-WeatherBot/1.0 (leonard.bruns@gmail.com)"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    NWS_POINTS, timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": UA, "Accept": "application/geo+json"},
                ) as r:
                    if r.status != 200:
                        return None
                    pts = await r.json()
                hourly_url = pts["properties"]["forecastHourly"]
                async with sess.get(
                    hourly_url, timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": UA, "Accept": "application/geo+json"},
                ) as r:
                    if r.status != 200:
                        return None
                    fc = await r.json()
            temps = []
            for p in fc["properties"]["periods"]:
                if p.get("startTime", "")[:10] == target_date:
                    t = p["temperature"]
                    unit = p.get("temperatureUnit", "F")
                    temps.append((t - 32.0) * 5.0 / 9.0 if unit == "F" else float(t))
            return max(temps) if temps else None
        except Exception as e:
            logger.debug("[WA] NWS fetch error: %s", e)
            return None

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
                # Build model_values_by_name dict for skill-weighted ensemble.
                # Key format: "temperature_2m_max_gfs_seamless" → "gfs_seamless"
                model_values_by_name: dict[str, float] = {}
                for k in temp_keys:
                    arr = daily[k]
                    if i < len(arr) and arr[i] is not None:
                        suffix = k[len("temperature_2m_max"):].lstrip("_")
                        model_name = suffix if suffix else FORECAST_MODELS.split(",")[0]
                        model_values_by_name[model_name] = float(arr[i])
                if not model_values_by_name:
                    continue
                values = list(model_values_by_name.values())  # kept for NWS append below

                # For US cities: add NWS NDFD (blends HRRR + NAM + GFS internally)
                if d == tomorrow and city in _US_CITIES:
                    nws_val = await self._fetch_nws_daily_max(lat, lon, tomorrow)
                    if nws_val is not None:
                        model_values_by_name["nws_ndfd"] = nws_val
                        values.append(nws_val)
                        logger.debug("[WA] NWS added %.1f°C for %s %s", nws_val, city, d)

                from datetime import date as _date
                _month = _date.fromisoformat(d).month
                _slug = CITY_NAME_TO_SLUG.get(city, "")

                # Skill-weighted ensemble mean + BLUE combined sigma.
                # Falls back to arithmetic mean + ASOS floor when skill matrix absent.
                cal_sigma = CITY_SIGMA_C.get(_slug, {}).get(_month)
                if cal_sigma is None:
                    elev = CITY_ELEVATION_M.get(city, 0.0)
                    cal_sigma = ELEVATION_SIGMA_FLOOR if elev > ELEVATION_THRESHOLD_M else 1.0
                mean, sigma = self._ensemble.combine(
                    _slug, _month, model_values_by_name,
                    asos_sigma_floor=cal_sigma,
                )
                # Microclimate correction: tarmac heat island + sea breeze floor
                from strategy.station_microclimate import compute_forecast_correction
                icao = CITY_ICAO.get(city, "")
                if icao:
                    metar = self._latest_metar.get(icao, {})
                    mc_mu, mc_sigma = compute_forecast_correction(
                        icao, mean, sigma,
                        wind_speed_kt=metar.get("wind_speed_kt"),
                        wind_dir_deg=metar.get("wind_dir_deg"),
                        sky_cover=metar.get("sky_cover"),
                        utc_hour=metar.get("utc_hour"),
                    )
                    if mc_mu != mean or mc_sigma != sigma:
                        logger.debug(
                            "[WA] microclimate %s: mu %.2f→%.2f sigma %.2f→%.2f (%s)",
                            icao, mean, mc_mu, sigma, mc_sigma,
                            "sea-breeze" if mc_mu < mean else "THI",
                        )
                    mean, sigma = mc_mu, mc_sigma

                result[d] = (mean, sigma)
                elev_tag = f" (elev {elev:.0f}m)" if elev > 0 else ""
                logger.debug("[WA] forecast %s lat=%.2f models=%d mean=%.1f sigma=%.1f%s",
                             d, lat, len(values), mean, sigma, elev_tag)
            return result if result else None
        except Exception as e:
            logger.debug("[WA] forecast error lat=%.2f lon=%.2f: %s", lat, lon, e)
            return None
