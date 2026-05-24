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
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Lazy-loaded: only imported after STATIONS have registered (avoids circular boot order).
_hot_bust_rates = None

def _hbr():
    global _hot_bust_rates
    if _hot_bust_rates is None:
        try:
            from analysis.weather.build_hot_bust_table import HotBustRates
            _hot_bust_rates = HotBustRates()
        except Exception as e:
            logger.warning("[WA] HotBustRates unavailable: %s", e)
            _hot_bust_rates = _NullHotBustRates()
    return _hot_bust_rates

class _NullHotBustRates:
    def query(self, *a, **kw):   return 0.0
    def reload(self):             pass


# ── Regime cache ──────────────────────────────────────────────────────────────
# Reads strategy/regime_today.json written by analysis/weather/regime_detection.py
# at 06:00 UTC. Returns regime string for (slug, date_iso): "normal" | "volatile"
# | "heatwave" | "cold_front". Falls back to "normal" on any error.

import os as _os
_REGIME_PATH = _os.path.join(_os.path.dirname(__file__), "regime_today.json")
_CONSENSUS_STATE_PATH = _os.path.join(_os.path.dirname(__file__), "bucket_consensus_state.json")
_regime_cache: dict = {}
_regime_mtime: float = 0.0

def _get_regime(slug: str, date_iso: str) -> str:
    global _regime_cache, _regime_mtime
    try:
        mtime = _os.path.getmtime(_REGIME_PATH)
        if mtime != _regime_mtime:
            with open(_REGIME_PATH) as _f:
                _regime_cache = json.load(_f)
            _regime_mtime = mtime
    except Exception:
        return "normal"
    return _regime_cache.get("cities", {}).get(slug, {}).get(date_iso, {}).get("regime", "normal")


GAMMA_BASE   = "https://gamma-api.polymarket.com"
METEO_BASE   = "https://api.open-meteo.com/v1/forecast"

EDGE_MIN     = 0.08    # minimum edge (fair_prob - poly_price) required to enter
MIN_FAIR_PROB = 0.45   # minimum fair probability for the best bucket
ASK_BAND_LO  = 0.00    # min entry price (overnight forecast arb) — no floor
ASK_BAND_HI  = 0.29    # max entry price — OVERRIDE with BRACKET_ENABLED for high-price entries

# ── NegRisk Bracketing / Temperature Ladder ──────────────────────────────────
# SHADOW mode (2026-05-23): log ladder signals without entering.
# Ladder = buy 2-3 adjacent cheap tail buckets simultaneously on wide-sigma cities.
# Edge: each tail bucket individually mispriced (fair > ask+0.08) but none clears
# MIN_FAIR_PROB=0.45 alone. Combined fair 55-90%; combined cost 0.15-0.45.
# Live entry gated by BRACKET_ENABLED. Shadow validation target: n≥30 signals,
# combined hit rate within ±0.10 of combined_fair_prob before flipping live.
BRACKET_ENABLED          = False  # True → live entries; False → shadow only (when BRACKET_SHADOW)
BRACKET_SHADOW           = True   # log [LADDER SHADOW] signals for validation
BRACKET_COST_CAP         = 0.55   # reject bracket if Σ ask_i > this
BRACKET_MAX_BUCKETS      = 3      # up to 3 rungs
BRACKET_COMBINED_FAIR_MIN = 0.55  # combined fair_prob floor (replaces per-bucket MIN_FAIR_PROB)
BRACKET_SIGMA_MIN        = 0.60   # only ladder on wide-sigma cities (σ ≥ 0.60°C)
# Sigma inflation for entries above ASK_BAND_HI (compensates for suspected overconfidence).
# Set to 1.0 to disable. Increase to 1.3 to make high-price fair_prob estimates more conservative.
SIGMA_INFLATION_ABOVE_CAP = 1.30   # applied when ask > ASK_BAND_HI and BRACKET_ENABLED
STAKE_USD    = 10.0    # fallback flat stake (2026-05-23: raised from $5)
PER_CITY_STAKE_USD: dict[str, float] = {
    "buenos-aires": 20.0,  # 2026-05-23: user-specified flat override
}

# ── Near-threshold CLOB WS watchlist ─────────────────────────────────────────
WATCHLIST_EDGE_FLOOR = -0.06  # subscribe if within 6pp of qualifying (ask too high by ≤0.06)
WATCHLIST_MIN_FAIR   = 0.35   # minimum fair_prob to be worth watching

# ── Fractional Kelly position sizing ─────────────────────────────────────────
KELLY_ENABLED    = True   # False → revert to flat STAKE_USD
KELLY_FRACTION   = 0.25   # quarter-Kelly: conservative for unverified sigma calibration
KELLY_MIN_USD    = 10.0   # floor: $10 flat minimum stake
KELLY_MAX_USD    = 12.0   # ceiling: raised 2026-05-24 from $8
OVERNIGHT_ALLOC  = 1.00   # STRAT_1 overnight: 100% — all capital to NWP overnight positions
INTRADAY_ALLOC   = 0.00   # STRAT_3 intraday: disabled — all capital to STRAT_1
BRACKET_ALLOC    = 0.10   # STRAT_2 bracket: 10% of bankroll total
TAIL_STRAT_ALLOC = 0.10   # STRAT_4 tail sniper: 10% of bankroll total
MAX_POS_PER_STRAT = 4     # up to 4 positions per strategy
# Per-position cap = strat_alloc / MAX_POS_PER_STRAT
OVERNIGHT_POS_ALLOC  = OVERNIGHT_ALLOC  / MAX_POS_PER_STRAT   # 10% per overnight position
INTRADAY_POS_ALLOC   = INTRADAY_ALLOC   / MAX_POS_PER_STRAT   # 10% per intraday position
BRACKET_POS_ALLOC    = BRACKET_ALLOC    / MAX_POS_PER_STRAT   # 2.5% per bracket position
TAIL_POS_ALLOC       = TAIL_STRAT_ALLOC / MAX_POS_PER_STRAT   # 2.5% per tail position
PER_STRAT_ALLOC  = OVERNIGHT_POS_ALLOC  # default for _kelly_stake (STRAT_1)
SIGMA_C_DEFAULT = 1.5  # fallback forecast uncertainty when only one model available
SIGMA_F_DEFAULT = 2.7  # fallback in °F
SCAN_INTERVAL_S = 21600  # baseline 6h scan cadence between NWP slots

# ── Entry timing window (local-time-aware) ────────────────────────────────────
# Resolution = midnight LOCAL on endDate. Window is [MAX_H_BEFORE, MIN_H_BEFORE] before that.
# Computed per-city using ICAO_UTC_OFFSET_H so Asian/Western cities are treated correctly.
MIN_HOURS_BEFORE_RESOLUTION = 6    # don't enter if <6h left in local day (market already priced)
MAX_HOURS_BEFORE_RESOLUTION = 36   # don't enter if >36h out (forecast not yet converged)

# STRAT_1 same-day NWP staleness gate.
# Once we're within this many hours of city peak, NWP daily-max forecast is stale
# (actual peak may have already passed). INTRADAY (STRAT_3) owns same-day territory
# via live METAR. Skip today's markets in STRAT_1 once the peak window approaches.
STRAT1_PRE_PEAK_BLOCK_H = 2

# NWP publish slots (UTC hours). Scan fires T+5min after each slot when fresh model data lands.
# Mirrors nwp_lag.py schedule; that strategy is paused but the schedule is ground truth.
NWP_SCAN_SLOTS_UTC: list[int] = sorted({3,4,5,6,7,9,10,11,15,16,17,18,19,21,22,23})

# ── NWP data-freshness probe ──────────────────────────────────────────────────
# After each NWP slot, poll reference cities until Open-Meteo shows a forecast
# shift (new model run ingested) rather than waiting a fixed T+N offset.
PROBE_FIRST_WAIT_MIN = 10   # first probe at T+10min after slot
PROBE_INTERVAL_MIN   = 10   # retry every 10min
PROBE_MAX_RETRIES    = 3    # give up and scan anyway at T+30min
PROBE_SHIFT_C        = 0.3  # °C shift in ensemble mean → new run confirmed

# Geographically diverse reference cities for the freshness probe only (not traded).
# London = ECMWF territory; Chicago = GFS territory; Tokyo = JMA territory.
_PROBE_CITIES: tuple[tuple[str, float, float], ...] = (
    ("London",  51.5048,   0.0495),
    ("Chicago", 41.9742, -87.9073),
    ("Tokyo",   35.5494, 139.7798),
)
MAX_POSITIONS    = 30  # max concurrent weather positions
DRY_RUN_LOG  = False  # set False to trade live

# ── METAR-loop dynamic exits ──────────────────────────────────────────────────
NOWCAST_EXIT_FLOOR  = 0.04   # sell existing position when nowcast P(bucket) drops below this
SALVAGE_MIN_BID     = 0.05   # only bother selling if bid > this (otherwise loss is tiny)

# ── Intraday METAR arb (front-running WU→Polymarket lag) ─────────────────────
INTRADAY_ENABLED      = False  # disabled 2026-05-24: all capital to STRAT_1 overnight NWP
INTRADAY_MIN_PROB     = 0.90   # minimum nowcast P(bucket) to enter today's market
INTRADAY_MIN_PROB_HI_PREC = 0.72  # lower threshold for high-precision cities (σ_blue < 0.45°C)
INTRADAY_EDGE_MIN     = 0.06   # lower edge threshold (harder signal, less spread required)
INTRADAY_EDGE_MAX     = 0.40   # crowd-divergence gate: edge above this = broken model or anomaly
INTRADAY_ASK_CAP      = 0.96   # upper price cap for intraday entries (raised: T-2h certainty buys)
INTRADAY_STAKE_FRAC   = 0.60   # fractional Kelly multiplier for intraday (higher certainty → less fractional)
INTRADAY_HI_PROB      = 0.90   # p threshold for $20 stake (requires σ < 0.65 gate already passed)
INTRADAY_HI_POS_ALLOC = 0.20   # 20% of bankroll when p >= INTRADAY_HI_PROB ($20 at $100)
# below INTRADAY_HI_PROB: INTRADAY_POS_ALLOC applies (10% = $10)
INTRADAY_HEAT_RAMP_H  = 2      # 2026-05-21: tightened 5h→2h. First 3h were NWP-anchored
                                # and structurally not where the METAR-lag edge lives.
                                # Genuine edge appears in the final 2h before peak when
                                # observed running_max dominates μ_nowcast.
INTRADAY_W1_MIN       = 0.30   # minimum METAR weight at window open; NWP anchors the remainder
RR_CV                 = 0.35   # coefficient of variation proxy: std(remaining_rise) ≈ mean × RR_CV
                                # True std requires per-city/month/hour ASOS reanalysis; 0.35 is
                                # calibrated from literature (Oke 2002, NWS verification studies).

# Cities with σ_blue < 0.45°C (8 regional models) — lower intraday prob threshold applies
INTRADAY_HI_PREC_CITIES = {"amsterdam", "paris", "madrid", "london"}
# Only run INTRADAY arb in city-months where σ < this threshold.
# Acts as a coarse pre-filter ceiling; the real gate is p_intraday < min_p downstream.
# Raised 0.65→0.85 (2026-05-23): old cap blocked Paris/Madrid/Amsterdam/Munich/Warsaw
# in May despite p_intraday being mathematically reachable at off-centered μ. The
# HI_PREC list (which lowers min_p to 0.72) was dead code for those cities under 0.65.
INTRADAY_SIGMA_CAP = 0.85
# Example: peak_hour=16 UTC → window opens at UTC 11 (7 AM EDT), closes at peak+1=17
TODAY_MARKETS_TTL     = 1800   # seconds between today's-market list refreshes (30 min)

# ── CLOB / VWAP execution layer ───────────────────────────────────────────────
CLOB_BASE        = "https://clob.polymarket.com"
MAKER_FIRST      = True      # default: rest at best_bid+tick (passive fill)
TAKER_EDGE_MIN   = 0.15      # override to taker when edge this large (captures before repricing)
CLOB_TICK        = 0.01      # minimum price increment for weather markets
TAKER_FEE_RATE   = 0.02      # Polymarket taker fee (~2% on order value)

# ── Upstream Oracle (STRAT_5) ─────────────────────────────────────────────────
UPSTREAM_ORACLE_ENABLED = False  # shadow mode: log signals but don't enter
DOWNSTREAM_FAIR_FLOOR = 0.50   # minimum bivariate-normal P(bucket) to consider entry
DOWNSTREAM_ASK_CAP    = 0.55   # skip if market has already repriced above this
DOWNSTREAM_EDGE_MIN   = 0.10   # minimum edge (fair_prob - ask)

# ── Tail-risk sniper ($0.01–$0.04 tokens) ────────────────────────────────────
TAIL_SNIPER_ENABLED  = False  # disabled 2026-05-22: STRAT_1-only mode
TAIL_PRICE_LO        = 0.01   # minimum token price for tail sniper
TAIL_PRICE_HI        = 0.08   # maximum token price for tail sniper (raised 0.04→0.08: live data shows
                               # meaningful HOT-bias edge at $0.04-$0.08, gap filter already gates reachability)
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

# Marine / cold-onshore wind sectors per ICAO (bearing FROM which cool maritime air arrives).
# When live METAR wind falls in this sector, remaining_rise is multiplied by MARINE_RISE_MULTIPLIER.
# Distinct from FOEHN_WIND_SECTORS (opposing directional effect: cooling, not warming).
MARINE_RISE_MULTIPLIER: float = 0.10   # scale remaining_rise when cold marine flow detected
MARINE_WIND_SECTORS: dict[str, tuple[float, float]] = {
    "KSFO": (180.0, 300.0),   # Pacific onshore SW–NW: marine layer suppresses inland heating
    "KLAX": (200.0, 270.0),   # Pacific onshore SW–W: coastal marine inversion
    "KSEA": (210.0, 270.0),   # Pacific/Puget onshore SW–W: cool marine push
    "KMIA": ( 70.0, 150.0),   # Atlantic onshore E–SE: sea breeze caps afternoon max
    "EGLC": (210.0, 270.0),   # Channel/Atlantic onshore SW: damps London heating ramp
    "EHAM": (270.0, 330.0),   # North Sea onshore NW: cool maritime suppresses Amsterdam max
}

# Cloud height threshold for cirrus reclassification.
# METAR BKN/OVC layers at altitude ≥ CIRRUS_ALT_CODE (in hundreds of feet = 20,000 ft)
# are high cirrus decks that transmit most solar radiation; reclassify sky_factor to SCT=0.60
# instead of BKN=0.30 / OVC=0.08 (which are valid only for low/mid clouds).
CIRRUS_ALT_CODE: int = 200   # hundreds of feet; 200 = 20,000 ft

# Latent heat evaporation penalty: recent precipitation keeps surface and air moist,
# suppressing afternoon max through evaporative cooling. Applied in _compute_nowcast_mu_sigma.
PRECIP_LATENT_THRESH_MM: float = 5.0    # 24h precip (mm) above which penalty fires
PRECIP_LATENT_PENALTY_C: float = 0.75   # °C subtracted from both mu_metar and mu_NWP

# Hold-favourites / scalp-mids policy (London 30d backtest 2026-05-20).
# Favourites: entry in [SCALP_BAND_HI, 1.0) — hold to PROFIT_TARGET=0.99 or resolution.
# Mids:       entry in [SCALP_BAND_LO, SCALP_BAND_HI) — scalp on WS BBO at scalp_tp.
# Below SCALP_BAND_LO: hold to resolution (scalp fill rate too low to matter).
SCALP_BAND_LO = 0.05
SCALP_BAND_HI = 0.20
SCALP_TARGET_ABS       = 0.03   # min absolute profit per share on a scalp
SCALP_TARGET_EDGE_FRAC = 0.50   # capture this fraction of (fair - entry)
SCALP_DISCOUNT         = 0.90   # TP ≤ fair × this (executability buffer)

# ── Tail sniper base-rate triggers — empirical HOT_BUST_RATE table ───────────
# Trigger C fires when P(actual_daily_max - gfs_d1 >= 1.5°C) >= HOT_BUST_MIN_PROB
# for the current (city, month), as computed by build_hot_bust_table.py.
# The binary HOT_BUST_BASE_CITIES set is retained as the offline fallback only.
HOT_BUST_MIN_PROB = 0.10          # P(bust >= 1.5°C) threshold to fire Trigger C
HOT_BUST_TABLE_GAP_C = 1.5       # gap used for table lookup (°C)
HOT_BUST_STAKE_REF_PROB = 0.20   # stake scale = bust_prob / this (1.0× at 20%, 2× at 40%)

# Offline fallback (used only if hot_bust_rates.json is missing):
HOT_BUST_BASE_CITIES = frozenset({
    "shanghai",     # ~35% HOT bust year-round
    "madrid",       # ~32% HOT bust year-round
    "jakarta",      # HOT Sep-Nov only
    "buenos-aires", # ~63% HOT bust year-round
})
TAIL_HOT_GAP_BASE = 4.0  # °C: relaxed reachability for base-rate cities
HOT_BUST_JAKARTA_MONTHS = frozenset({9, 10, 11})

# Cities where morning METAR signals predict daily max will fall BELOW GFS.
# Signal: low dew spread (humid, clouds suppress heating) + calm wind.
# Highest z-scores in calibration: Singapore z=-1.27, Jakarta z=-1.10.
# Entry: buy the bucket currently containing running_max (temp has entered it
# but market prices it cheap because it expects temperature to keep rising).
SIGNAL_COLD_CITIES  = frozenset({"singapore", "jakarta"})
TAIL_COLD_DEW_MAX   = 4.5   # °C dew spread: below this = humid → suppressed heating
TAIL_COLD_WIND_MAX  = 7.0   # kt: calm wind amplifies cold-bust signal

# ── Forecast consensus / bucket-switching ────────────────────────────────────
# Dynamic required_runs by mu_delta: ≥1.5°C→1, ≥0.8°C→2, ≥0.35°C→3, else→5
BUCKET_SWITCH_MAX_RUNS = 5      # queue depth (must hold up to max required_runs)

# Cities excluded from STRAT_1 overnight entries: ERA5 validation shows σ_real > 1.5°C all-year
# or structural bucket-hit WR < 55% (fee-negative after spread+rebate).
STRAT1_SKIP_CITIES = {
    "denver",        # σ_blue=0.97 → real D+1 WR ≈ 34% — original exclusion
    "nyc",           # ERA5 σ=0.8–1.6°C; Mar–Jul all >1.3°C → marginal / coin-flip
    "shanghai",      # ERA5 σ=1.0–2.1°C; Mar–Jun all ≥1.5°C → unreliable forecast city
    # los-angeles / san-francisco removed 2026-05-22: ERA5 unreliable for coastal cities
    # (coarse grid can't resolve marine layer); ASOS-calibrated σ=0.45/0.51 is the better signal
}

# Skip any city/month where calibrated σ > this floor (forecast too uncertain for positive EV)
SIGMA_SKIP_FLOOR = 1.5  # °C — erf(1/(1.5×√2)) ≈ 52% true WR ceiling, below fee break-even

# Validated set from analysis/weather/stations.py (23 cities with confirmed WU source + 5yr calibration).
# _scan() filters to this set so STRAT_1/2 never trade unvalidated cities.
VALIDATED_CITY_SLUGS: frozenset = frozenset({
    # Original 23 (5yr ASOS + ERA5 calibrated, 2026-05-21)
    "nyc", "chicago", "los-angeles", "miami", "san-francisco", "tokyo", "london",
    "dallas", "houston", "seattle", "denver", "atlanta", "paris", "madrid",
    "amsterdam", "beijing", "shanghai", "singapore", "jakarta", "toronto",
    "mexico-city", "buenos-aires", "sao-paulo",
    # Wave-2 additions (calibrated 2026-05-22, ERA5 σ < 1.3°C all-year)
    "munich", "warsaw", "helsinki",
    # Wave-2 marginal (SIGMA_SKIP_FLOOR blocks worst months automatically)
    "milan", "austin",
    # Wave-3 (2026-05-22): tel-aviv/moscow clean; guangzhou/shenzhen marginal winter months
    "tel-aviv", "moscow", "guangzhou", "shenzhen",
})


def _compute_scalp_tp(entry: float, fair: float) -> float:
    """Scalp exits disabled: all positions hold to resolution or METAR/nowcast exit.
    METAR dynamic exit (NOWCAST_EXIT_FLOOR) handles early risk-off; WU transition
    confirms the winner. Scalp TPs cut winners short without improving loss discipline.
    Return 0.0 always so main.py skips the WEATHER_SCALP_TP path."""
    return 0.0

# 2026-05-20: Elevation-aware sigma tuning. Mountains (>1500m) have 2-3x higher forecast error
# than coastal cities. Prevents edge-hunting in unwinnable high-altitude markets.
ELEVATION_THRESHOLD_M = 1500
ELEVATION_SIGMA_FLOOR = 3.0  # Minimum sigma for mountain cities (vs 1.0 for sea level)

# 7-model global ensemble. All models confirmed returning data for all validated cities
# via Open-Meteo live + historical APIs (2026-05-20 probe).
# GFS (NOAA), ICON (DWD), ECMWF IFS, GEM (CMC/Canada), JMA, UKMO, Météo-France.
# Models that lack coverage for a region return null and are silently excluded.
FORECAST_MODELS = "gfs_seamless,icon_seamless,ecmwf_ifs025,gem_seamless,jma_seamless,ukmo_seamless,meteofrance_seamless,ecmwf_aifs025,gfs_graphcast025"

# Minimum live models required for an STRAT_1/2 entry. Below this, σ_ens is unreliable:
# the ensemble spread shrinks artificially when models drop out, faking conviction.
# Open-Meteo nulls are typical for regional models in extra-coverage zones; require at least 4
# globally-coverage models to keep σ statistically meaningful.
MIN_MODELS_FOR_ENTRY = 4
# Sigma inflation factor applied when fewer than MIN_MODELS_FOR_ENTRY were available.
# Adds protection against the "fewer models → tighter spread → false confidence" failure.
LOW_MODEL_SIGMA_INFLATION = 1.40

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
    "Tel Aviv":         (32.0005,  34.8706),   # LLBG Ben Gurion Intl
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
    "Moscow":           (55.5915,  37.2613),   # UUWW Vnukovo (Polymarket NOAA resolution)
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
    "Karachi": 4, "Manila": 22, "Toronto": 76, "Shanghai": 4, "Tokyo": 44, "Tel Aviv": 48,
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
    "Manila": "RPLL", "Toronto": "CYYZ", "Shanghai": "ZSPD", "Tel Aviv": "LLBG",
    "Tokyo": "RJTT", "Hong Kong": "VHHH", "Dubai": "OMDB",
    "Sydney": "YSSY", "Phoenix": "KPHX", "Atlanta": "KATL",
    "Berlin": "EDDB", "Stockholm": "ESSA", "Oslo": "ENGM",
    "Copenhagen": "EKCH", "Vienna": "LOWW", "Zurich": "LSZH",
    "Brussels": "EBBR", "Barcelona": "LEBL", "Rome": "LIRF",
    "Prague": "LKPR", "Budapest": "LHBP", "Bucharest": "LROP",
    "Athens": "LGAV", "Istanbul": "LTFJ", "Moscow": "UUWW",
    "Riyadh": "OERK", "Cairo": "HECA", "Lagos": "DNMM",
    "Nairobi": "HKJK", "Johannesburg": "FAOR", "Mumbai": "VABB",
    "Delhi": "VIDP", "Dhaka": "VGHS", "Bangkok": "VTBS",
    "Kuala Lumpur": "WMKK", "Bogota": "SKBO", "Lima": "SPJC",
    "Santiago": "SCEL", "Chongqing": "ZUCK", "Dallas": "KDAL",
}

AWC_METAR_URL = "https://aviationweather.gov/api/data/metar?ids={icao}&format=json&hours=1"
METAR_POLL_INTERVAL = 60  # METARs post every ~30 min; poll every 60s to catch within 60s

# UTC offset in hours per ICAO. Used to reset running_max at LOCAL midnight, not UTC.
# Critical for Asia/Pacific cities where local midnight is at 14:00-18:00 UTC: resetting at
# UTC 00:00 would erase the morning observations from the day Polymarket actually resolves.
# Note: ignores DST — error is ≤1h, and the running_max reset only matters around midnight.
ICAO_UTC_OFFSET_H: dict[str, int] = {
    # Americas
    "KLGA":  -5, "KORD":  -6, "KLAX":  -8, "KSFO":  -8, "KSEA":  -8,
    "KMIA":  -5, "KDAL":  -6, "KHOU":  -6, "KAUS":  -6, "KDEN":  -7,
    "KBKF":  -7, "KATL":  -5, "KPHX":  -7, "MMMX":  -6, "CYYZ":  -5,
    "SBGR":  -3, "SAEZ":  -3, "MPHO":  -5, "SKBO":  -5, "SPJC":  -5,
    "SCEL":  -3,
    # Europe / Africa
    "EGLC":   0, "LFPB":   1, "LEMD":   1, "EHAM":   1, "LIMC":   1,
    "EDDM":   1, "EDDB":   1, "EPWA":   1, "EBBR":   1, "LEBL":   1, "EFHK":   2, "KAUS":  -6,
    "LIRF":   1, "LKPR":   1, "LHBP":   1, "LROP":   2, "LGAV":   2,
    "LTFJ":   3, "LTAC":   3, "UUEE":   3, "UUWW":   3, "ESSA":   1,
    "ENGM":   1, "EKCH":   1, "LOWW":   1, "LSZH":   1, "HECA":   2,
    "DNMM":   1, "HKJK":   3, "FAOR":   2, "FACT":   2, "OERK":   3,
    "OEJN":   3,
    # Asia / Oceania
    "LLBG":   3,
    "VHHH":   8, "RJTT":   9, "RKSI":   9, "RKPK":   9, "ZBAA":   8,
    "ZSPD":   8, "ZGSZ":   8, "ZGGG":   8, "ZSJN":   8, "ZSQD":   8,
    "ZHHH":   8, "ZUUU":   8, "ZUCK":   8, "RCSS":   8, "WSSS":   8,
    "WIHH":   7, "WMKK":   8, "VTBS":   7, "VABB":   5, "VIDP":   5,
    "VILK":   5, "VGHS":   6, "OMDB":   4, "OPKC":   5, "RPLL":   8,
    "YSSY":  10, "NZWN":  12,
}

# Calibration tables derived from 5 years (2021-2025) of ASOS hourly data via Iowa State Mesonet.
# All 23 validated stations (analysis/weather/stations.py). sigma = ASOS-measured intraday
# residual std at peak hour: std(daily_max − max(running_max, T_h + remaining_rise[h])).
CITY_NAME_TO_SLUG: dict[str, str] = {
    # Original 7 — calibrated ASOS sigma + remaining-rise tables
    "New York City": "nyc", "Chicago": "chicago", "Los Angeles": "los-angeles",
    "Miami": "miami", "San Francisco": "san-francisco", "Tokyo": "tokyo", "London": "london",
    # All other cities — skill matrix provides bias + sigma; no ASOS rise table (falls back)
    "Paris": "paris", "Seoul": "seoul", "Seattle": "seattle", "Sao Paulo": "sao-paulo",
    "Buenos Aires": "buenos-aires", "Ankara": "ankara", "Wellington": "wellington",
    "Lucknow": "lucknow", "Munich": "munich", "Dallas": "dallas", "Singapore": "singapore",
    "Milan": "milan", "Madrid": "madrid", "Warsaw": "warsaw", "Taipei": "taipei",
    "Beijing": "beijing", "Wuhan": "wuhan", "Chengdu": "chengdu", "Shenzhen": "shenzhen",
    "Austin": "austin", "Denver": "denver", "Houston": "houston", "Mexico City": "mexico-city",
    "Busan": "busan", "Amsterdam": "amsterdam", "Helsinki": "helsinki",
    "Panama City": "panama-city", "Jakarta": "jakarta", "Jeddah": "jeddah",
    "Cape Town": "cape-town", "Guangzhou": "guangzhou", "Jinan": "jinan",
    "Qingdao": "qingdao", "Karachi": "karachi", "Manila": "manila", "Toronto": "toronto",
    "Shanghai": "shanghai", "Hong Kong": "hong-kong", "Dubai": "dubai", "Sydney": "sydney",
    "Phoenix": "phoenix", "Atlanta": "atlanta", "Berlin": "berlin", "Stockholm": "stockholm",
    "Oslo": "oslo", "Copenhagen": "copenhagen", "Vienna": "vienna", "Zurich": "zurich",
    "Brussels": "brussels", "Barcelona": "barcelona", "Rome": "rome", "Prague": "prague",
    "Budapest": "budapest", "Bucharest": "bucharest", "Athens": "athens",
    "Istanbul": "istanbul", "Moscow": "moscow", "Riyadh": "riyadh", "Cairo": "cairo",
    "Lagos": "lagos", "Nairobi": "nairobi", "Johannesburg": "johannesburg",
    "Mumbai": "mumbai", "Delhi": "delhi", "Dhaka": "dhaka", "Bangkok": "bangkok",
    "Kuala Lumpur": "kuala-lumpur", "Bogota": "bogota", "Lima": "lima",
    "Santiago": "santiago", "Chongqing": "chongqing", "Tel Aviv": "tel-aviv",
}

# Per-city/month calibrated sigma floor in °C — ERA5 reanalysis validation (5yr, max of prior
# hand-coded vs ERA5 grid-vs-station error). Used as asos_sigma_floor in ensemble_weights.combine().
CITY_SIGMA_C: dict[str, dict[int, float]] = {
    "nyc":         {1: 0.844, 2: 0.963, 3: 0.745, 4: 0.995, 5: 0.754, 6: 0.973, 7: 0.713, 8: 0.528, 9: 0.461, 10: 0.368, 11: 0.571, 12: 0.739},
    "chicago":     {1: 0.629, 2: 0.810, 3: 0.979, 4: 1.173, 5: 0.731, 6: 0.802, 7: 0.691, 8: 0.536, 9: 0.576, 10: 0.608, 11: 0.660, 12: 0.758},
    "los-angeles": {1: 0.668, 2: 0.477, 3: 0.510, 4: 0.386, 5: 0.353, 6: 0.364, 7: 0.315, 8: 0.317, 9: 0.422, 10: 0.602, 11: 0.509, 12: 0.473},
    "miami":       {1: 0.418, 2: 0.337, 3: 0.494, 4: 0.377, 5: 0.675, 6: 0.882, 7: 0.923, 8: 0.827, 9: 0.794, 10: 0.606, 11: 0.353, 12: 0.380},
    "san-francisco":{1: 0.562, 2: 0.584, 3: 0.601, 4: 0.547, 5: 0.407, 6: 0.528, 7: 0.367, 8: 0.429, 9: 0.590, 10: 0.634, 11: 0.418, 12: 0.468},
    "tokyo":       {1: 0.642, 2: 1.009, 3: 1.006, 4: 0.739, 5: 1.054, 6: 0.787, 7: 0.604, 8: 0.992, 9: 0.626, 10: 0.847, 11: 0.985, 12: 1.131},
    "london":      {1: 0.711, 2: 0.551, 3: 0.580, 4: 0.486, 5: 0.548, 6: 0.588, 7: 0.443, 8: 0.492, 9: 0.532, 10: 0.630, 11: 0.648, 12: 0.807},
    "dallas":      {1: 0.718, 2: 0.881, 3: 0.630, 4: 0.583, 5: 0.661, 6: 0.504, 7: 0.344, 8: 0.405, 9: 0.409, 10: 0.393, 11: 0.547, 12: 0.595},
    "houston":     {1: 0.635, 2: 0.658, 3: 0.554, 4: 0.547, 5: 0.472, 6: 0.490, 7: 0.740, 8: 0.562, 9: 0.588, 10: 0.357, 11: 0.446, 12: 0.437},
    "seattle":     {1: 0.374, 2: 0.388, 3: 0.592, 4: 0.753, 5: 0.740, 6: 0.866, 7: 0.645, 8: 0.721, 9: 0.717, 10: 0.527, 11: 0.465, 12: 0.529},
    "denver":      {1: 0.751, 2: 0.903, 3: 0.795, 4: 1.032, 5: 0.971, 6: 1.000, 7: 0.728, 8: 0.609, 9: 0.604, 10: 0.548, 11: 0.675, 12: 0.504},
    "atlanta":     {1: 0.583, 2: 0.645, 3: 0.494, 4: 0.545, 5: 0.498, 6: 0.723, 7: 0.723, 8: 0.696, 9: 0.445, 10: 0.322, 11: 0.340, 12: 0.528},
    "paris":       {1: 1.027, 2: 0.496, 3: 0.515, 4: 0.621, 5: 0.654, 6: 0.565, 7: 0.458, 8: 0.490, 9: 0.524, 10: 0.581, 11: 0.608, 12: 0.815},
    "madrid":      {1: 0.481, 2: 0.481, 3: 0.571, 4: 0.550, 5: 0.710, 6: 0.527, 7: 0.421, 8: 0.416, 9: 0.526, 10: 0.459, 11: 0.491, 12: 0.622},
    "amsterdam":   {1: 1.127, 2: 0.673, 3: 0.524, 4: 0.553, 5: 0.742, 6: 0.632, 7: 0.507, 8: 0.587, 9: 0.492, 10: 0.457, 11: 0.872, 12: 0.967},
    "beijing":     {1: 0.362, 2: 0.462, 3: 0.503, 4: 0.516, 5: 0.961, 6: 0.542, 7: 0.536, 8: 0.528, 9: 0.384, 10: 0.496, 11: 0.510, 12: 0.518},
    "shanghai":    {1: 0.470, 2: 0.563, 3: 0.716, 4: 0.545, 5: 0.677, 6: 0.664, 7: 0.572, 8: 0.458, 9: 0.568, 10: 0.593, 11: 0.415, 12: 0.458},
    "singapore":   {1: 0.585, 2: 0.482, 3: 0.599, 4: 0.712, 5: 0.653, 6: 0.530, 7: 0.560, 8: 0.653, 9: 0.614, 10: 0.585, 11: 0.669, 12: 0.576},
    "jakarta":     {1: 0.858, 2: 0.617, 3: 0.705, 4: 0.660, 5: 0.494, 6: 0.556, 7: 0.553, 8: 0.596, 9: 0.718, 10: 0.677, 11: 0.792, 12: 0.837},
    "toronto":     {1: 0.641, 2: 0.723, 3: 0.810, 4: 0.866, 5: 0.741, 6: 0.828, 7: 0.887, 8: 0.690, 9: 0.763, 10: 0.543, 11: 0.787, 12: 0.766},
    "mexico-city": {1: 0.526, 2: 0.383, 3: 0.507, 4: 0.557, 5: 0.781, 6: 0.752, 7: 0.854, 8: 0.782, 9: 0.789, 10: 1.662, 11: 0.425, 12: 0.413},
    "buenos-aires":{1: 0.503, 2: 0.547, 3: 0.525, 4: 0.356, 5: 0.364, 6: 0.367, 7: 0.273, 8: 0.483, 9: 0.444, 10: 0.475, 11: 0.565, 12: 0.426},
    "sao-paulo":   {1: 0.873, 2: 0.814, 3: 0.827, 4: 0.514, 5: 0.350, 6: 0.440, 7: 0.258, 8: 0.458, 9: 0.637, 10: 0.605, 11: 0.567, 12: 0.936},
    # Wave-2 (2026-05-22)
    "munich":      {1: 1.158, 2: 1.136, 3: 0.703, 4: 0.779, 5: 0.799, 6: 0.923, 7: 0.847, 8: 0.950, 9: 0.783, 10: 1.218, 11: 1.143, 12: 1.034},
    "warsaw":      {1: 0.730, 2: 0.701, 3: 0.804, 4: 0.706, 5: 0.750, 6: 0.845, 7: 0.834, 8: 0.782, 9: 0.864, 10: 0.767, 11: 0.742, 12: 0.585},
    "helsinki":    {1: 0.711, 2: 0.568, 3: 1.105, 4: 1.171, 5: 0.931, 6: 0.861, 7: 0.827, 8: 0.850, 9: 0.829, 10: 0.571, 11: 0.725, 12: 0.752},
    "milan":       {1: 1.517, 2: 1.055, 3: 0.881, 4: 1.008, 5: 0.960, 6: 1.268, 7: 1.167, 8: 1.108, 9: 0.870, 10: 0.765, 11: 1.287, 12: 1.481},
    "austin":      {1: 1.549, 2: 1.455, 3: 1.441, 4: 1.374, 5: 1.130, 6: 0.873, 7: 0.983, 8: 1.110, 9: 1.088, 10: 0.974, 11: 0.876, 12: 1.010},
    # Wave-3 (2026-05-22)
    "tel-aviv":    {1: 0.834, 2: 0.697, 3: 1.271, 4: 1.480, 5: 1.186, 6: 0.922, 7: 0.753, 8: 0.666, 9: 0.656, 10: 0.732, 11: 0.893, 12: 1.061},
    "moscow":      {1: 0.807, 2: 0.721, 3: 0.730, 4: 0.839, 5: 0.778, 6: 0.756, 7: 0.723, 8: 0.807, 9: 0.602, 10: 0.613, 11: 0.665, 12: 0.622},
    "guangzhou":   {1: 1.014, 2: 1.086, 3: 1.248, 4: 1.184, 5: 1.196, 6: 1.201, 7: 1.031, 8: 1.063, 9: 1.056, 10: 0.975, 11: 1.002, 12: 1.027},
    "shenzhen":    {1: 1.321, 2: 1.400, 3: 1.365, 4: 1.118, 5: 1.099, 6: 1.089, 7: 0.982, 8: 1.001, 9: 1.068, 10: 1.025, 11: 1.115, 12: 1.048},
}

# ERA5-reanalysis sigma values (2026-05-22 calibration) — shadow only, not used for trading.
# Logged alongside CITY_SIGMA_C to track divergence and inform future recalibration decisions.
CITY_SIGMA_C_ERA5: dict[str, dict[int, float]] = {
    "amsterdam":   {1: 1.127, 2: 0.753, 3: 0.903, 4: 0.710, 5: 0.845, 6: 0.855, 7: 0.858, 8: 0.751, 9: 0.742, 10: 0.643, 11: 0.872, 12: 0.967},
    "atlanta":     {1: 0.909, 2: 0.878, 3: 0.863, 4: 0.852, 5: 0.871, 6: 0.825, 7: 0.953, 8: 0.849, 9: 0.812, 10: 0.674, 11: 0.732, 12: 0.891},
    "beijing":     {1: 0.935, 2: 0.933, 3: 1.223, 4: 1.091, 5: 1.247, 6: 1.342, 7: 1.273, 8: 1.085, 9: 1.053, 10: 0.932, 11: 1.054, 12: 1.003},
    "buenos-aires":{1: 1.116, 2: 0.906, 3: 0.909, 4: 0.767, 5: 0.787, 6: 0.732, 7: 1.020, 8: 3.413, 9: 0.923, 10: 0.923, 11: 1.117, 12: 0.962},
    "chicago":     {1: 0.806, 2: 0.929, 3: 1.026, 4: 1.173, 5: 1.014, 6: 1.083, 7: 0.882, 8: 0.862, 9: 0.914, 10: 0.727, 11: 0.660, 12: 0.774},
    "dallas":      {1: 0.820, 2: 1.031, 3: 1.088, 4: 1.068, 5: 0.843, 6: 0.711, 7: 0.750, 8: 0.769, 9: 0.768, 10: 0.765, 11: 0.735, 12: 0.923},
    "houston":     {1: 1.133, 2: 1.032, 3: 0.735, 4: 0.943, 5: 0.694, 6: 0.755, 7: 0.838, 8: 1.032, 9: 0.897, 10: 0.767, 11: 0.813, 12: 0.850},
    "jakarta":     {1: 0.858, 2: 0.846, 3: 0.909, 4: 0.663, 5: 0.741, 6: 0.809, 7: 0.683, 8: 0.703, 9: 0.938, 10: 0.930, 11: 0.903, 12: 0.888},
    "london":      {1: 0.711, 2: 0.648, 3: 0.776, 4: 0.742, 5: 0.850, 6: 0.738, 7: 0.693, 8: 0.778, 9: 0.649, 10: 0.630, 11: 0.648, 12: 0.807},
    "los-angeles": {1: 1.577, 2: 1.610, 3: 1.479, 4: 1.935, 5: 1.669, 6: 1.966, 7: 1.662, 8: 1.986, 9: 2.170, 10: 2.182, 11: 2.162, 12: 1.782},
    "madrid":      {1: 1.327, 2: 0.708, 3: 0.780, 4: 1.024, 5: 0.819, 6: 0.824, 7: 0.664, 8: 0.678, 9: 0.769, 10: 0.756, 11: 0.936, 12: 0.860},
    "mexico-city": {1: 0.906, 2: 0.914, 3: 0.864, 4: 0.915, 5: 1.236, 6: 1.133, 7: 1.037, 8: 0.997, 9: 0.884, 10: 1.662, 11: 0.965, 12: 0.796},
    "miami":       {1: 1.013, 2: 0.929, 3: 0.786, 4: 0.707, 5: 0.696, 6: 0.882, 7: 0.923, 8: 0.827, 9: 0.799, 10: 0.800, 11: 0.857, 12: 0.975},
    "nyc":         {1: 0.944, 2: 1.174, 3: 1.462, 4: 1.385, 5: 1.407, 6: 1.635, 7: 1.082, 8: 0.982, 9: 0.806, 10: 1.051, 11: 0.783, 12: 0.983},
    "paris":       {1: 1.027, 2: 0.571, 3: 0.583, 4: 0.621, 5: 0.654, 6: 0.985, 7: 0.703, 8: 0.637, 9: 0.667, 10: 0.581, 11: 0.655, 12: 0.815},
    "san-francisco":{1: 1.181, 2: 1.268, 3: 1.069, 4: 1.501, 5: 1.777, 6: 2.029, 7: 2.109, 8: 1.891, 9: 2.038, 10: 1.786, 11: 1.051, 12: 1.080},
    "sao-paulo":   {1: 1.042, 2: 0.870, 3: 0.839, 4: 0.811, 5: 0.798, 6: 0.873, 7: 0.724, 8: 1.041, 9: 1.022, 10: 1.236, 11: 1.025, 12: 1.140},
    "seattle":     {1: 0.983, 2: 0.834, 3: 1.057, 4: 1.097, 5: 1.304, 6: 1.226, 7: 1.189, 8: 1.298, 9: 1.234, 10: 1.169, 11: 0.913, 12: 1.014},
    "shanghai":    {1: 1.469, 2: 1.595, 3: 2.093, 4: 1.816, 5: 1.593, 6: 1.513, 7: 1.312, 8: 1.106, 9: 1.046, 10: 1.026, 11: 1.035, 12: 1.146},
    "singapore":   {1: 0.861, 2: 0.821, 3: 0.912, 4: 1.092, 5: 0.894, 6: 0.950, 7: 0.824, 8: 0.891, 9: 0.846, 10: 0.851, 11: 0.964, 12: 0.880},
    "tokyo":       {1: 0.936, 2: 1.157, 3: 1.206, 4: 1.196, 5: 1.278, 6: 1.188, 7: 1.320, 8: 1.107, 9: 1.194, 10: 0.923, 11: 1.072, 12: 1.131},
    "toronto":     {1: 0.678, 2: 0.832, 3: 1.271, 4: 1.609, 5: 1.100, 6: 1.022, 7: 0.988, 8: 0.752, 9: 0.870, 10: 1.055, 11: 0.960, 12: 0.865},
}

# Per-city/month typical peak temperature UTC hour (mean of daily peak hours, 5yr ASOS)
CITY_PEAK_HOUR_UTC: dict[str, dict[int, int]] = {
    "nyc": {1: 19, 2: 19, 3: 19, 4: 18, 5: 19, 6: 18, 7: 18, 8: 18, 9: 19, 10: 19, 11: 19, 12: 18},
    "chicago": {1: 20, 2: 20, 3: 20, 4: 20, 5: 20, 6: 20, 7: 19, 8: 19, 9: 19, 10: 20, 11: 20, 12: 18},
    "los-angeles": {1: 20, 2: 20, 3: 19, 4: 20, 5: 20, 6: 20, 7: 20, 8: 21, 9: 20, 10: 19, 11: 19, 12: 20},
    "miami": {1: 19, 2: 19, 3: 18, 4: 18, 5: 16, 6: 16, 7: 15, 8: 15, 9: 17, 10: 16, 11: 18, 12: 18},
    "san-francisco": {1: 22, 2: 22, 3: 21, 4: 21, 5: 21, 6: 20, 7: 21, 8: 21, 9: 21, 10: 22, 11: 22, 12: 22},
    "tokyo": {1: 6, 2: 6, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 3, 9: 4, 10: 5, 11: 5, 12: 5},
    "london": {1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 14, 7: 15, 8: 14, 9: 13, 10: 13, 11: 13, 12: 13},
    "dallas": {1: 21, 2: 21, 3: 21, 4: 21, 5: 20, 6: 21, 7: 21, 8: 21, 9: 21, 10: 20, 11: 20, 12: 20},
    "houston": {1: 19, 2: 20, 3: 20, 4: 19, 5: 20, 6: 21, 7: 21, 8: 20, 9: 19, 10: 20, 11: 19, 12: 20},
    "seattle": {1: 22, 2: 22, 3: 21, 4: 22, 5: 22, 6: 23, 7: 23, 8: 23, 9: 23, 10: 21, 11: 21, 12: 22},
    "denver": {1: 20, 2: 20, 3: 21, 4: 21, 5: 19, 6: 19, 7: 20, 8: 20, 9: 21, 10: 20, 11: 21, 12: 20},
    "atlanta": {1: 19, 2: 20, 3: 20, 4: 19, 5: 20, 6: 18, 7: 18, 8: 18, 9: 19, 10: 19, 11: 19, 12: 19},
    "paris": {1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 15, 7: 16, 8: 15, 9: 14, 10: 13, 11: 14, 12: 14},
    "madrid": {1: 15, 2: 15, 3: 15, 4: 15, 5: 14, 6: 15, 7: 16, 8: 16, 9: 15, 10: 15, 11: 15, 12: 14},
    "amsterdam": {1: 12, 2: 13, 3: 13, 4: 13, 5: 13, 6: 13, 7: 13, 8: 12, 9: 13, 10: 13, 11: 12, 12: 13},
    "beijing": {1: 7, 2: 7, 3: 7, 4: 7, 5: 6, 6: 7, 7: 7, 8: 7, 9: 7, 10: 6, 11: 6, 12: 6},
    "shanghai": {1: 5, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 6, 8: 5, 9: 4, 10: 4, 11: 5, 12: 5},
    "singapore": {1: 5, 2: 6, 3: 6, 4: 5, 5: 5, 6: 6, 7: 6, 8: 5, 9: 5, 10: 6, 11: 5, 12: 5},
    "jakarta": {1: 5, 2: 6, 3: 5, 4: 5, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6, 10: 5, 11: 5, 12: 5},
    "toronto": {1: 19, 2: 20, 3: 20, 4: 21, 5: 22, 6: 21, 7: 19, 8: 19, 9: 19, 10: 19, 11: 19, 12: 19},
    "mexico-city": {1: 20, 2: 21, 3: 20, 4: 20, 5: 19, 6: 19, 7: 19, 8: 19, 9: 19, 10: 20, 11: 20, 12: 20},
    "buenos-aires": {1: 19, 2: 19, 3: 19, 4: 18, 5: 18, 6: 18, 7: 19, 8: 18, 9: 19, 10: 18, 11: 19, 12: 19},
    "sao-paulo": {1: 16, 2: 16, 3: 16, 4: 17, 5: 18, 6: 18, 7: 18, 8: 18, 9: 17, 10: 17, 11: 17, 12: 16},
    "austin":      {1: 20, 2: 21, 3: 21, 4: 20, 5: 20, 6: 21, 7: 21, 8: 21, 9: 21, 10: 20, 11: 20, 12: 20},
    # Wave-2/3 additions (2026-05-23, 5yr ASOS 2021–2025, n≈1800 station-days each)
    "munich":      {1: 10, 2: 11, 3: 12, 4: 12, 5: 12, 6: 13, 7: 13, 8: 12, 9: 12, 10: 12, 11: 10, 12: 10},
    "warsaw":      {1: 10, 2: 11, 3: 12, 4: 12, 5: 12, 6: 12, 7: 12, 8: 12, 9: 12, 10: 11, 11: 9, 12: 9},
    "helsinki":    {1: 8, 2: 8, 3: 11, 4: 11, 5: 11, 6: 11, 7: 11, 8: 11, 9: 10, 10: 10, 11: 8, 12: 8},
    "milan":       {1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 13, 8: 13, 9: 12, 10: 12, 11: 11, 12: 12},
    "tel-aviv":    {1: 10, 2: 10, 3: 10, 4: 9, 5: 9, 6: 9, 7: 9, 8: 9, 9: 9, 10: 9, 11: 9, 12: 10},
    "moscow":      {1: 9, 2: 10, 3: 11, 4: 10, 5: 11, 6: 11, 7: 11, 8: 11, 9: 10, 10: 10, 11: 8, 12: 9},
    "guangzhou":   {1: 6, 2: 5, 3: 6, 4: 5, 5: 5, 6: 5, 7: 6, 8: 6, 9: 5, 10: 5, 11: 5, 12: 6},
    "shenzhen":    {1: 5, 2: 6, 3: 5, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 5, 10: 5, 11: 5, 12: 6},
}

# Per-city/month/UTC-hour mean remaining rise in °C (how much more the temp typically rises
# from this observation hour to the daily maximum). From 5yr ASOS data, sky-cover-independent.
# Apply sky_factor on top: CLR=1.0, FEW=0.85, SCT=0.60, BKN=0.30, OVC=0.08
CITY_REMAINING_RISE: dict[str, dict[int, dict[int, float]]] = {
    "nyc": {
        1:  {0: 2.55, 1: 2.83, 2: 2.9, 3: 3.13, 4: 3.35, 5: 3.52, 6: 3.7, 7: 3.7, 8: 3.88, 9: 4.04, 10: 4.03, 11: 4.25, 12: 4.28, 13: 3.86, 14: 3.32, 15: 2.79, 16: 2.18, 17: 1.98, 18: 1.59, 19: 1.43, 20: 1.66, 21: 1.87, 22: 2.11, 23: 2.36},
        2:  {0: 3.34, 1: 3.5, 2: 3.71, 3: 4.06, 4: 4.29, 5: 4.52, 6: 4.67, 7: 4.96, 8: 5.25, 9: 5.36, 10: 5.53, 11: 5.68, 12: 5.38, 13: 4.85, 14: 4.32, 15: 3.78, 16: 3.05, 17: 2.46, 18: 2.26, 19: 1.89, 20: 1.92, 21: 2.27, 22: 2.64, 23: 2.72},
        3:  {0: 4.26, 1: 4.49, 2: 4.79, 3: 5.06, 4: 5.54, 5: 5.77, 6: 5.92, 7: 6.52, 8: 6.68, 9: 6.72, 10: 6.84, 11: 6.64, 12: 6.05, 13: 5.28, 14: 4.5, 15: 3.57, 16: 2.78, 17: 2.03, 18: 1.69, 19: 1.52, 20: 1.82, 21: 2.33, 22: 2.84, 23: 3.43},
        4:  {0: 4.45, 1: 4.69, 2: 5.18, 3: 5.33, 4: 5.74, 5: 6.07, 6: 6.44, 7: 6.73, 8: 7.15, 9: 7.32, 10: 7.26, 11: 6.69, 12: 6.3, 13: 5.68, 14: 4.73, 15: 3.79, 16: 3.06, 17: 2.43, 18: 1.92, 19: 1.88, 20: 2.23, 21: 2.67, 22: 3.01, 23: 3.93},
        5:  {0: 4.7, 1: 5.27, 2: 5.48, 3: 5.87, 4: 6.15, 5: 6.46, 6: 6.71, 7: 7.35, 8: 7.39, 9: 7.37, 10: 7.24, 11: 6.84, 12: 6.0, 13: 4.9, 14: 4.22, 15: 3.07, 16: 2.38, 17: 1.96, 18: 1.58, 19: 1.54, 20: 1.67, 21: 2.15, 22: 2.78, 23: 3.5},
        6:  {0: 4.8, 1: 5.2, 2: 5.49, 3: 5.85, 4: 6.22, 5: 6.6, 6: 6.92, 7: 7.27, 8: 7.46, 9: 7.51, 10: 7.09, 11: 6.37, 12: 5.62, 13: 4.62, 14: 3.76, 15: 2.82, 16: 2.05, 17: 1.72, 18: 1.55, 19: 1.5, 20: 2.07, 21: 2.36, 22: 2.94, 23: 3.77},
        7:  {0: 3.84, 1: 4.38, 2: 5.01, 3: 5.1, 4: 5.58, 5: 5.88, 6: 6.11, 7: 6.48, 8: 6.88, 9: 7.14, 10: 6.91, 11: 6.28, 12: 5.44, 13: 4.5, 14: 3.46, 15: 2.57, 16: 1.93, 17: 1.84, 18: 1.25, 19: 1.54, 20: 1.68, 21: 2.07, 22: 2.72, 23: 3.73},
        8:  {0: 3.76, 1: 4.09, 2: 4.49, 3: 4.62, 4: 4.91, 5: 5.27, 6: 5.58, 7: 5.84, 8: 6.05, 9: 6.26, 10: 6.24, 11: 5.86, 12: 5.04, 13: 4.13, 14: 3.19, 15: 2.31, 16: 1.62, 17: 1.23, 18: 0.96, 19: 1.05, 20: 1.37, 21: 2.16, 22: 2.7, 23: 3.66},
        9:  {0: 3.07, 1: 3.54, 2: 3.84, 3: 4.26, 4: 4.59, 5: 4.94, 6: 5.04, 7: 5.35, 8: 5.55, 9: 5.99, 10: 6.05, 11: 5.77, 12: 4.88, 13: 4.07, 14: 3.13, 15: 2.48, 16: 1.95, 17: 1.46, 18: 1.05, 19: 1.0, 20: 1.33, 21: 1.64, 22: 2.39, 23: 2.95},
        10:  {0: 3.1, 1: 3.39, 2: 3.81, 3: 4.26, 4: 4.48, 5: 4.78, 6: 5.21, 7: 5.51, 8: 5.6, 9: 5.72, 10: 5.85, 11: 5.63, 12: 4.96, 13: 4.12, 14: 3.32, 15: 2.45, 16: 1.67, 17: 1.3, 18: 0.85, 19: 0.82, 20: 1.11, 21: 1.85, 22: 2.41, 23: 2.75},
        11:  {0: 2.79, 1: 3.05, 2: 3.38, 3: 3.76, 4: 4.09, 5: 4.32, 6: 4.54, 7: 4.76, 8: 4.91, 9: 5.21, 10: 5.19, 11: 5.39, 12: 4.8, 13: 4.16, 14: 3.39, 15: 2.67, 16: 2.05, 17: 1.59, 18: 1.14, 19: 1.18, 20: 1.48, 21: 1.92, 22: 2.4, 23: 2.78},
        12:  {0: 2.83, 1: 3.2, 2: 3.38, 3: 3.51, 4: 3.62, 5: 4.01, 6: 3.95, 7: 4.05, 8: 4.16, 9: 4.26, 10: 4.38, 11: 4.29, 12: 4.11, 13: 3.82, 14: 3.19, 15: 2.61, 16: 2.11, 17: 1.77, 18: 1.44, 19: 1.43, 20: 1.72, 21: 2.02, 22: 2.15, 23: 2.44},
    },
    "chicago": {
        1:  {0: 2.5, 1: 2.65, 2: 2.67, 3: 2.88, 4: 3.21, 5: 3.28, 6: 3.56, 7: 3.66, 8: 3.86, 9: 3.98, 10: 4.05, 11: 4.12, 12: 4.25, 13: 4.26, 14: 3.71, 15: 3.31, 16: 2.75, 17: 2.29, 18: 2.0, 19: 1.65, 20: 1.48, 21: 1.69, 22: 2.32, 23: 2.59},
        2:  {0: 3.77, 1: 3.93, 2: 4.68, 3: 4.84, 4: 4.96, 5: 5.26, 6: 5.79, 7: 6.0, 8: 6.41, 9: 6.83, 10: 6.87, 11: 7.01, 12: 7.09, 13: 6.8, 14: 5.92, 15: 4.95, 16: 3.66, 17: 2.65, 18: 2.01, 19: 2.15, 20: 2.03, 21: 2.4, 22: 2.59, 23: 3.22},
        3:  {0: 4.54, 1: 5.33, 2: 5.44, 3: 6.04, 4: 6.11, 5: 6.55, 6: 6.76, 7: 7.15, 8: 7.48, 9: 7.55, 10: 8.05, 11: 8.35, 12: 7.45, 13: 6.8, 14: 5.9, 15: 4.76, 16: 3.84, 17: 3.02, 18: 3.0, 19: 2.51, 20: 2.37, 21: 2.64, 22: 3.4, 23: 4.22},
        4:  {0: 4.28, 1: 5.06, 2: 5.56, 3: 6.15, 4: 6.57, 5: 6.8, 6: 7.27, 7: 7.64, 8: 7.96, 9: 8.17, 10: 8.64, 11: 8.12, 12: 7.7, 13: 6.55, 14: 5.46, 15: 4.83, 16: 4.28, 17: 4.01, 18: 3.54, 19: 2.63, 20: 2.64, 21: 2.52, 22: 2.86, 23: 3.58},
        5:  {0: 4.46, 1: 5.73, 2: 6.41, 3: 6.94, 4: 7.47, 5: 7.94, 6: 8.43, 7: 8.9, 8: 9.27, 9: 9.34, 10: 9.35, 11: 8.78, 12: 7.5, 13: 6.2, 14: 4.87, 15: 3.86, 16: 3.05, 17: 2.5, 18: 2.0, 19: 1.81, 20: 1.73, 21: 1.9, 22: 2.51, 23: 3.38},
        6:  {0: 4.62, 1: 5.61, 2: 6.54, 3: 7.27, 4: 7.84, 5: 8.25, 6: 8.77, 7: 9.09, 8: 9.27, 9: 9.64, 10: 9.71, 11: 8.83, 12: 7.41, 13: 6.11, 14: 4.96, 15: 3.86, 16: 2.97, 17: 2.33, 18: 2.14, 19: 2.15, 20: 2.03, 21: 2.15, 22: 2.92, 23: 3.66},
        7:  {0: 3.48, 1: 4.38, 2: 5.06, 3: 5.9, 4: 6.42, 5: 6.7, 6: 7.25, 7: 7.35, 8: 7.64, 9: 7.93, 10: 7.89, 11: 7.36, 12: 6.3, 13: 5.18, 14: 3.99, 15: 3.19, 16: 2.38, 17: 1.86, 18: 1.72, 19: 1.42, 20: 1.7, 21: 2.09, 22: 2.36, 23: 2.57},
        8:  {0: 4.07, 1: 4.7, 2: 5.26, 3: 5.94, 4: 6.32, 5: 6.57, 6: 7.12, 7: 7.45, 8: 7.73, 9: 8.01, 10: 8.14, 11: 7.97, 12: 6.61, 13: 5.32, 14: 4.07, 15: 2.85, 16: 2.11, 17: 1.7, 18: 1.18, 19: 1.01, 20: 1.36, 21: 1.5, 22: 2.14, 23: 3.28},
        9:  {0: 4.37, 1: 4.97, 2: 5.61, 3: 6.17, 4: 6.64, 5: 6.93, 6: 7.35, 7: 7.7, 8: 8.07, 9: 8.21, 10: 8.27, 11: 8.52, 12: 7.52, 13: 5.98, 14: 4.57, 15: 3.3, 16: 2.26, 17: 1.54, 18: 1.2, 19: 1.17, 20: 1.24, 21: 1.44, 22: 2.19, 23: 3.51},
        10:  {0: 3.73, 1: 4.21, 2: 4.62, 3: 5.13, 4: 5.41, 5: 6.09, 6: 6.48, 7: 6.74, 8: 7.15, 9: 7.25, 10: 7.42, 11: 7.77, 12: 7.27, 13: 5.99, 14: 4.75, 15: 3.42, 16: 2.47, 17: 1.76, 18: 1.45, 19: 1.43, 20: 1.47, 21: 1.85, 22: 2.87, 23: 3.59},
        11:  {0: 3.37, 1: 3.62, 2: 4.2, 3: 4.4, 4: 4.72, 5: 5.01, 6: 5.21, 7: 5.58, 8: 5.81, 9: 5.66, 10: 5.94, 11: 5.87, 12: 6.2, 13: 5.76, 14: 4.61, 15: 3.44, 16: 2.61, 17: 2.35, 18: 1.84, 19: 1.67, 20: 1.53, 21: 1.9, 22: 2.64, 23: 3.07},
        12:  {0: 2.73, 1: 3.02, 2: 3.31, 3: 3.83, 4: 3.86, 5: 4.03, 6: 4.21, 7: 4.44, 8: 4.67, 9: 4.69, 10: 4.67, 11: 5.06, 12: 4.91, 13: 4.85, 14: 4.25, 15: 3.62, 16: 2.47, 17: 2.15, 18: 1.83, 19: 1.58, 20: 1.65, 21: 1.97, 22: 2.35, 23: 2.64},
    },
    "los-angeles": {
        1:  {0: 3.25, 1: 3.76, 2: 3.97, 3: 4.19, 4: 4.58, 5: 4.87, 6: 5.09, 7: 5.39, 8: 6.42, 9: 6.78, 10: 7.23, 11: 7.28, 12: 7.69, 13: 7.34, 14: 7.24, 15: 6.63, 16: 4.77, 17: 3.09, 18: 1.97, 19: 1.04, 20: 0.82, 21: 1.0, 22: 1.48, 23: 2.16},
        2:  {0: 2.99, 1: 3.77, 2: 4.27, 3: 4.42, 4: 4.49, 5: 4.88, 6: 4.94, 7: 5.35, 8: 5.86, 9: 6.05, 10: 6.56, 11: 6.84, 12: 7.07, 13: 6.92, 14: 6.66, 15: 5.62, 16: 4.03, 17: 2.49, 18: 1.49, 19: 0.92, 20: 0.94, 21: 1.16, 22: 1.59, 23: 2.15},
        3:  {0: 2.61, 1: 3.48, 2: 3.75, 3: 3.99, 4: 4.21, 5: 4.31, 6: 4.49, 7: 4.99, 8: 5.28, 9: 5.63, 10: 6.04, 11: 6.16, 12: 6.16, 13: 6.11, 14: 5.63, 15: 4.33, 16: 2.92, 17: 1.71, 18: 1.03, 19: 0.86, 20: 0.91, 21: 1.11, 22: 1.42, 23: 1.9},
        4:  {0: 2.69, 1: 3.55, 2: 4.17, 3: 4.37, 4: 4.62, 5: 4.68, 6: 4.89, 7: 5.16, 8: 5.45, 9: 5.66, 10: 5.94, 11: 6.12, 12: 6.06, 13: 5.92, 14: 4.67, 15: 3.49, 16: 2.13, 17: 1.29, 18: 1.03, 19: 0.77, 20: 0.75, 21: 0.89, 22: 1.39, 23: 1.91},
        5:  {0: 2.14, 1: 2.92, 2: 3.68, 3: 3.95, 4: 3.98, 5: 4.02, 6: 4.09, 7: 4.16, 8: 4.42, 9: 4.52, 10: 4.61, 11: 4.74, 12: 4.76, 13: 4.31, 14: 3.61, 15: 2.74, 16: 2.05, 17: 1.49, 18: 0.95, 19: 0.64, 20: 0.47, 21: 0.51, 22: 0.85, 23: 1.34},
        6:  {0: 2.21, 1: 3.03, 2: 3.77, 3: 4.18, 4: 4.23, 5: 4.34, 6: 4.44, 7: 4.56, 8: 4.68, 9: 4.73, 10: 4.86, 11: 4.97, 12: 4.8, 13: 4.49, 14: 3.7, 15: 2.79, 16: 1.92, 17: 1.45, 18: 1.0, 19: 0.65, 20: 0.5, 21: 0.5, 22: 0.84, 23: 1.42},
        7:  {0: 2.22, 1: 3.16, 2: 4.03, 3: 4.38, 4: 4.6, 5: 4.71, 6: 4.73, 7: 4.81, 8: 4.91, 9: 4.99, 10: 5.05, 11: 5.05, 12: 5.02, 13: 4.78, 14: 4.11, 15: 3.08, 16: 2.11, 17: 1.37, 18: 0.89, 19: 0.54, 20: 0.48, 21: 0.64, 22: 0.91, 23: 1.45},
        8:  {0: 2.44, 1: 3.35, 2: 4.17, 3: 4.53, 4: 4.61, 5: 4.74, 6: 4.86, 7: 4.97, 8: 5.02, 9: 5.25, 10: 5.36, 11: 5.29, 12: 5.38, 13: 5.11, 14: 4.32, 15: 3.19, 16: 1.98, 17: 1.19, 18: 0.75, 19: 0.66, 20: 0.63, 21: 0.72, 22: 1.05, 23: 1.64},
        9:  {0: 2.86, 1: 3.71, 2: 4.05, 3: 4.21, 4: 4.37, 5: 4.62, 6: 4.69, 7: 4.83, 8: 5.1, 9: 5.17, 10: 5.37, 11: 5.35, 12: 5.24, 13: 5.31, 14: 4.52, 15: 3.46, 16: 2.47, 17: 1.59, 18: 0.96, 19: 0.79, 20: 0.76, 21: 0.99, 22: 1.4, 23: 2.04},
        10:  {0: 3.42, 1: 4.05, 2: 4.21, 3: 4.33, 4: 4.38, 5: 4.65, 6: 4.94, 7: 5.37, 8: 5.66, 9: 5.96, 10: 6.33, 11: 6.34, 12: 6.36, 13: 6.32, 14: 5.84, 15: 4.23, 16: 2.8, 17: 1.61, 18: 0.88, 19: 0.8, 20: 1.02, 21: 1.25, 22: 1.7, 23: 2.46},
        11:  {0: 3.71, 1: 4.2, 2: 4.36, 3: 4.55, 4: 5.06, 5: 5.01, 6: 5.43, 7: 5.45, 8: 6.21, 9: 6.95, 10: 7.23, 11: 7.21, 12: 7.37, 13: 7.33, 14: 6.95, 15: 5.55, 16: 3.67, 17: 2.16, 18: 1.05, 19: 0.7, 20: 0.98, 21: 1.29, 22: 1.86, 23: 2.81},
        12:  {0: 3.07, 1: 3.22, 2: 3.47, 3: 3.56, 4: 3.76, 5: 4.05, 6: 4.33, 7: 4.52, 8: 5.25, 9: 5.94, 10: 5.93, 11: 6.21, 12: 6.3, 13: 6.15, 14: 6.26, 15: 5.45, 16: 3.96, 17: 2.68, 18: 1.6, 19: 0.99, 20: 0.96, 21: 1.16, 22: 1.59, 23: 2.16},
    },
    "miami": {
        1:  {0: 3.89, 1: 4.2, 2: 4.66, 3: 5.06, 4: 5.31, 5: 5.6, 6: 6.03, 7: 6.03, 8: 6.24, 9: 6.45, 10: 6.69, 11: 6.73, 12: 6.18, 13: 4.76, 14: 3.32, 15: 2.21, 16: 1.65, 17: 1.12, 18: 0.96, 19: 0.99, 20: 1.29, 21: 1.91, 22: 2.8, 23: 3.58},
        2:  {0: 3.63, 1: 4.11, 2: 4.42, 3: 4.65, 4: 5.04, 5: 5.33, 6: 5.63, 7: 5.74, 8: 6.0, 9: 6.06, 10: 6.24, 11: 6.11, 12: 5.28, 13: 3.96, 14: 2.82, 15: 1.7, 16: 1.31, 17: 0.89, 18: 0.85, 19: 0.75, 20: 1.25, 21: 1.74, 22: 2.55, 23: 3.3},
        3:  {0: 3.98, 1: 4.36, 2: 4.69, 3: 5.02, 4: 5.28, 5: 5.71, 6: 5.86, 7: 6.12, 8: 6.43, 9: 6.57, 10: 6.5, 11: 6.44, 12: 5.1, 13: 3.69, 14: 2.65, 15: 1.77, 16: 1.26, 17: 0.87, 18: 0.74, 19: 0.84, 20: 1.41, 21: 1.95, 22: 2.74, 23: 3.52},
        4:  {0: 3.92, 1: 4.12, 2: 4.54, 3: 4.82, 4: 5.0, 5: 5.39, 6: 5.57, 7: 5.89, 8: 5.85, 9: 5.88, 10: 6.0, 11: 5.19, 12: 3.94, 13: 2.85, 14: 1.95, 15: 1.34, 16: 1.1, 17: 0.94, 18: 0.69, 19: 0.93, 20: 1.45, 21: 2.32, 22: 2.82, 23: 3.56},
        5:  {0: 4.32, 1: 4.52, 2: 4.73, 3: 4.94, 4: 5.08, 5: 5.37, 6: 5.68, 7: 5.84, 8: 5.9, 9: 6.04, 10: 5.97, 11: 5.02, 12: 3.74, 13: 2.7, 14: 1.87, 15: 1.13, 16: 0.87, 17: 1.0, 18: 1.21, 19: 1.5, 20: 1.82, 21: 2.37, 22: 2.93, 23: 3.96},
        6:  {0: 4.1, 1: 4.37, 2: 4.42, 3: 4.53, 4: 4.97, 5: 5.13, 6: 5.2, 7: 5.38, 8: 5.32, 9: 5.33, 10: 5.24, 11: 4.19, 12: 3.35, 13: 2.44, 14: 1.86, 15: 1.71, 16: 1.65, 17: 2.02, 18: 1.91, 19: 2.3, 20: 2.63, 21: 2.76, 22: 3.59, 23: 3.73},
        7:  {0: 4.04, 1: 4.3, 2: 4.32, 3: 4.47, 4: 4.65, 5: 5.01, 6: 5.25, 7: 5.22, 8: 5.38, 9: 5.38, 10: 5.27, 11: 4.56, 12: 3.64, 13: 2.7, 14: 1.95, 15: 1.46, 16: 1.62, 17: 1.88, 18: 1.81, 19: 1.74, 20: 1.82, 21: 1.99, 22: 2.78, 23: 3.75},
        8:  {0: 4.28, 1: 4.32, 2: 4.65, 3: 4.71, 4: 4.81, 5: 4.99, 6: 5.14, 7: 5.36, 8: 5.41, 9: 5.45, 10: 5.49, 11: 4.83, 12: 3.6, 13: 2.64, 14: 1.83, 15: 1.38, 16: 1.5, 17: 2.11, 18: 2.14, 19: 2.33, 20: 2.65, 21: 3.09, 22: 3.51, 23: 3.93},
        9:  {0: 4.94, 1: 4.99, 2: 5.08, 3: 5.28, 4: 5.41, 5: 5.64, 6: 5.62, 7: 5.81, 8: 5.88, 9: 5.92, 10: 5.84, 11: 5.26, 12: 3.84, 13: 2.66, 14: 1.74, 15: 1.63, 16: 1.79, 17: 1.71, 18: 2.59, 19: 2.86, 20: 2.91, 21: 3.6, 22: 4.13, 23: 4.61},
        10:  {0: 3.36, 1: 3.54, 2: 3.84, 3: 3.96, 4: 4.28, 5: 4.65, 6: 4.8, 7: 5.0, 8: 5.15, 9: 5.2, 10: 5.09, 11: 4.9, 12: 3.63, 13: 2.5, 14: 1.91, 15: 1.32, 16: 0.89, 17: 1.0, 18: 1.16, 19: 1.39, 20: 1.62, 21: 2.31, 22: 2.86, 23: 3.16},
        11:  {0: 3.31, 1: 3.53, 2: 3.94, 3: 4.24, 4: 4.52, 5: 4.84, 6: 5.16, 7: 5.34, 8: 5.48, 9: 5.62, 10: 5.7, 11: 5.72, 12: 4.67, 13: 3.55, 14: 2.52, 15: 1.5, 16: 0.92, 17: 0.79, 18: 0.72, 19: 0.94, 20: 1.34, 21: 2.01, 22: 2.69, 23: 3.12},
        12:  {0: 3.45, 1: 3.64, 2: 4.06, 3: 4.33, 4: 4.68, 5: 5.05, 6: 5.4, 7: 5.59, 8: 5.86, 9: 5.92, 10: 6.03, 11: 5.89, 12: 5.24, 13: 3.97, 14: 2.68, 15: 1.83, 16: 1.16, 17: 0.75, 18: 0.72, 19: 0.86, 20: 1.31, 21: 1.88, 22: 2.68, 23: 3.19},
    },
    "san-francisco": {
        1:  {0: 1.72, 1: 2.51, 2: 2.8, 3: 3.2, 4: 3.51, 5: 3.79, 6: 4.01, 7: 4.1, 8: 4.46, 9: 4.89, 10: 5.11, 11: 5.35, 12: 5.36, 13: 5.41, 14: 5.29, 15: 5.12, 16: 4.02, 17: 3.38, 18: 2.69, 19: 2.14, 20: 1.6, 21: 1.0, 22: 0.85, 23: 0.98},
        2:  {0: 2.11, 1: 3.06, 2: 3.65, 3: 4.07, 4: 4.39, 5: 4.64, 6: 5.01, 7: 5.39, 8: 5.72, 9: 6.18, 10: 6.42, 11: 6.75, 12: 6.99, 13: 7.16, 14: 6.92, 15: 6.2, 16: 4.96, 17: 3.98, 18: 3.43, 19: 2.65, 20: 1.87, 21: 1.28, 22: 0.95, 23: 1.09},
        3:  {0: 2.3, 1: 3.41, 2: 4.06, 3: 4.35, 4: 4.6, 5: 4.77, 6: 5.21, 7: 5.44, 8: 5.65, 9: 5.88, 10: 6.1, 11: 6.31, 12: 6.47, 13: 6.51, 14: 6.26, 15: 5.07, 16: 4.12, 17: 3.32, 18: 2.6, 19: 2.03, 20: 1.25, 21: 0.94, 22: 1.06, 23: 1.6},
        4:  {0: 2.84, 1: 4.05, 2: 5.11, 3: 5.47, 4: 5.81, 5: 5.98, 6: 6.12, 7: 6.33, 8: 6.6, 9: 6.74, 10: 7.07, 11: 7.26, 12: 7.39, 13: 7.28, 14: 6.34, 15: 5.19, 16: 4.27, 17: 3.24, 18: 2.38, 19: 1.5, 20: 1.04, 21: 0.83, 22: 1.19, 23: 1.92},
        5:  {0: 2.96, 1: 4.01, 2: 5.31, 3: 5.93, 4: 6.3, 5: 6.65, 6: 6.99, 7: 7.15, 8: 7.23, 9: 7.3, 10: 7.41, 11: 7.62, 12: 7.61, 13: 7.27, 14: 6.22, 15: 4.99, 16: 4.12, 17: 2.85, 18: 1.84, 19: 1.2, 20: 0.9, 21: 0.87, 22: 1.24, 23: 1.85},
        6:  {0: 2.79, 1: 3.87, 2: 5.09, 3: 5.99, 4: 6.28, 5: 6.52, 6: 6.75, 7: 6.88, 8: 7.08, 9: 7.3, 10: 7.45, 11: 7.65, 12: 7.66, 13: 7.06, 14: 6.03, 15: 4.95, 16: 3.9, 17: 2.97, 18: 1.78, 19: 1.0, 20: 0.66, 21: 0.75, 22: 1.2, 23: 1.88},
        7:  {0: 2.75, 1: 3.86, 2: 5.18, 3: 6.02, 4: 6.33, 5: 6.48, 6: 6.74, 7: 6.86, 8: 7.12, 9: 7.25, 10: 7.36, 11: 7.45, 12: 7.41, 13: 7.16, 14: 6.21, 15: 5.05, 16: 3.88, 17: 2.93, 18: 2.0, 19: 1.24, 20: 0.73, 21: 0.71, 22: 1.06, 23: 1.76},
        8:  {0: 2.9, 1: 4.24, 2: 5.62, 3: 6.17, 4: 6.5, 5: 6.63, 6: 6.82, 7: 7.15, 8: 7.38, 9: 7.55, 10: 7.72, 11: 7.86, 12: 7.86, 13: 7.79, 14: 6.77, 15: 5.57, 16: 4.4, 17: 3.32, 18: 2.31, 19: 1.43, 20: 0.83, 21: 0.62, 22: 1.15, 23: 1.86},
        9:  {0: 3.32, 1: 4.79, 2: 5.78, 3: 6.1, 4: 6.3, 5: 6.5, 6: 6.82, 7: 7.0, 8: 7.07, 9: 7.4, 10: 7.56, 11: 7.79, 12: 7.89, 13: 7.87, 14: 7.23, 15: 5.94, 16: 5.01, 17: 3.77, 18: 2.78, 19: 1.75, 20: 1.15, 21: 0.71, 22: 1.29, 23: 2.18},
        10:  {0: 3.25, 1: 4.67, 2: 5.18, 3: 5.49, 4: 5.8, 5: 6.1, 6: 6.19, 7: 6.64, 8: 6.94, 9: 7.22, 10: 7.34, 11: 7.54, 12: 7.6, 13: 7.67, 14: 7.49, 15: 5.98, 16: 4.94, 17: 3.94, 18: 3.12, 19: 2.17, 20: 1.55, 21: 1.29, 22: 1.28, 23: 2.15},
        11:  {0: 2.04, 1: 2.78, 2: 3.41, 3: 3.74, 4: 4.05, 5: 4.46, 6: 4.6, 7: 4.86, 8: 5.24, 9: 5.8, 10: 5.93, 11: 6.24, 12: 6.32, 13: 6.39, 14: 6.18, 15: 5.37, 16: 4.22, 17: 3.45, 18: 2.84, 19: 2.12, 20: 1.34, 21: 0.9, 22: 0.68, 23: 1.1},
        12:  {0: 1.72, 1: 2.11, 2: 2.45, 3: 2.62, 4: 2.89, 5: 3.13, 6: 3.27, 7: 3.36, 8: 3.56, 9: 3.98, 10: 4.08, 11: 4.32, 12: 4.49, 13: 4.39, 14: 4.39, 15: 4.31, 16: 3.41, 17: 2.77, 18: 2.35, 19: 1.82, 20: 1.34, 21: 1.12, 22: 0.94, 23: 1.09},
    },
    "tokyo": {
        1:  {0: 3.19, 1: 2.36, 2: 1.62, 3: 1.16, 4: 0.85, 5: 0.63, 6: 0.65, 7: 1.15, 8: 1.61, 9: 1.95, 10: 2.29, 11: 2.6, 12: 3.07, 13: 3.29, 14: 3.72, 15: 4.14, 16: 4.32, 17: 4.76, 18: 4.93, 19: 5.11, 20: 5.24, 21: 5.38, 22: 5.25, 23: 4.22},
        2:  {0: 3.78, 1: 2.78, 2: 1.93, 3: 1.51, 4: 1.1, 5: 0.82, 6: 0.89, 7: 1.23, 8: 1.9, 9: 2.33, 10: 2.81, 11: 3.18, 12: 3.45, 13: 3.82, 14: 3.97, 15: 4.37, 16: 4.63, 17: 5.04, 18: 5.31, 19: 5.43, 20: 5.63, 21: 5.91, 22: 5.46, 23: 4.61},
        3:  {0: 3.74, 1: 3.23, 2: 2.63, 3: 2.01, 4: 1.51, 5: 1.21, 6: 1.21, 7: 1.5, 8: 2.06, 9: 2.59, 10: 3.14, 11: 3.5, 12: 3.79, 13: 4.16, 14: 4.26, 15: 4.52, 16: 4.89, 17: 5.18, 18: 5.45, 19: 5.71, 20: 5.81, 21: 5.86, 22: 5.31, 23: 4.53},
        4:  {0: 3.34, 1: 2.52, 2: 1.92, 3: 1.48, 4: 1.15, 5: 1.01, 6: 1.07, 7: 1.53, 8: 2.13, 9: 2.83, 10: 3.31, 11: 3.69, 12: 3.9, 13: 4.1, 14: 4.33, 15: 4.54, 16: 4.78, 17: 5.04, 18: 5.28, 19: 5.45, 20: 5.56, 21: 5.17, 22: 4.56, 23: 3.88},
        5:  {0: 3.18, 1: 2.52, 2: 1.8, 3: 1.43, 4: 1.17, 5: 1.04, 6: 1.27, 7: 1.66, 8: 2.23, 9: 2.8, 10: 3.32, 11: 3.67, 12: 3.97, 13: 4.16, 14: 4.27, 15: 4.56, 16: 4.86, 17: 5.02, 18: 5.24, 19: 5.4, 20: 5.4, 21: 4.84, 22: 4.34, 23: 3.63},
        6:  {0: 2.97, 1: 2.36, 2: 1.82, 3: 1.34, 4: 1.13, 5: 0.99, 6: 1.25, 7: 1.7, 8: 2.22, 9: 2.86, 10: 3.34, 11: 3.76, 12: 4.08, 13: 4.3, 14: 4.49, 15: 4.65, 16: 4.83, 17: 5.02, 18: 5.13, 19: 5.15, 20: 4.98, 21: 4.53, 22: 4.03, 23: 3.43},
        7:  {0: 2.72, 1: 2.1, 2: 1.63, 3: 1.15, 4: 1.02, 5: 0.97, 6: 1.24, 7: 1.8, 8: 2.61, 9: 3.42, 10: 3.8, 11: 4.08, 12: 4.53, 13: 4.71, 14: 4.91, 15: 5.14, 16: 5.25, 17: 5.34, 18: 5.5, 19: 5.6, 20: 5.43, 21: 4.85, 22: 4.11, 23: 3.37},
        8:  {0: 2.58, 1: 2.13, 2: 1.53, 3: 1.19, 4: 1.39, 5: 1.22, 6: 1.54, 7: 1.85, 8: 2.51, 9: 3.12, 10: 3.68, 11: 4.0, 12: 4.26, 13: 4.45, 14: 4.51, 15: 4.7, 16: 4.84, 17: 5.03, 18: 5.1, 19: 5.32, 20: 5.26, 21: 4.77, 22: 4.05, 23: 3.35},
        9:  {0: 2.38, 1: 1.7, 2: 1.35, 3: 1.11, 4: 0.83, 5: 0.89, 6: 1.24, 7: 1.58, 8: 2.12, 9: 2.68, 10: 3.05, 11: 3.29, 12: 3.52, 13: 3.73, 14: 3.87, 15: 4.02, 16: 4.22, 17: 4.33, 18: 4.37, 19: 4.46, 20: 4.52, 21: 4.36, 22: 3.78, 23: 3.21},
        10:  {0: 2.59, 1: 2.02, 2: 1.53, 3: 1.24, 4: 1.02, 5: 0.88, 6: 1.0, 7: 1.36, 8: 1.73, 9: 2.0, 10: 2.33, 11: 2.53, 12: 2.77, 13: 3.09, 14: 3.3, 15: 3.51, 16: 3.78, 17: 3.91, 18: 4.2, 19: 4.4, 20: 4.59, 21: 4.58, 22: 4.13, 23: 3.48},
        11:  {0: 2.97, 1: 2.26, 2: 1.57, 3: 1.11, 4: 0.76, 5: 0.7, 6: 0.89, 7: 1.36, 8: 1.74, 9: 2.13, 10: 2.43, 11: 2.69, 12: 3.05, 13: 3.4, 14: 3.72, 15: 3.98, 16: 4.31, 17: 4.64, 18: 5.01, 19: 5.08, 20: 5.24, 21: 5.34, 22: 4.9, 23: 4.01},
        12:  {0: 3.54, 1: 2.62, 2: 1.92, 3: 1.36, 4: 0.92, 5: 0.74, 6: 0.94, 7: 1.44, 8: 1.78, 9: 2.01, 10: 2.4, 11: 2.84, 12: 3.31, 13: 3.7, 14: 4.11, 15: 4.69, 16: 4.95, 17: 5.12, 18: 5.36, 19: 5.63, 20: 5.75, 21: 5.93, 22: 5.7, 23: 4.78},
    },
    "london": {
        1:  {0: 2.88, 1: 3.01, 2: 3.08, 3: 3.27, 4: 3.35, 5: 3.39, 6: 3.36, 7: 3.32, 8: 3.24, 9: 2.73, 10: 2.15, 11: 1.51, 12: 1.16, 13: 0.86, 14: 0.83, 15: 1.02, 16: 1.3, 17: 1.65, 18: 1.88, 19: 2.1, 20: 2.27, 21: 2.48, 22: 2.61, 23: 2.84},
        2:  {0: 3.43, 1: 3.61, 2: 3.7, 3: 3.82, 4: 3.89, 5: 3.92, 6: 3.96, 7: 3.86, 8: 3.4, 9: 2.78, 10: 2.06, 11: 1.45, 12: 0.95, 13: 0.66, 14: 0.61, 15: 0.71, 16: 1.03, 17: 1.5, 18: 1.88, 19: 2.19, 20: 2.51, 21: 2.82, 22: 3.04, 23: 3.29},
        3:  {0: 4.78, 1: 4.95, 2: 5.18, 3: 5.36, 4: 5.54, 5: 5.6, 6: 5.6, 7: 5.18, 8: 4.4, 9: 3.4, 10: 2.45, 11: 1.74, 12: 1.25, 13: 0.93, 14: 0.68, 15: 0.75, 16: 1.06, 17: 1.73, 18: 2.45, 19: 3.05, 20: 3.53, 21: 3.92, 22: 4.23, 23: 4.46},
        4:  {0: 6.01, 1: 6.34, 2: 6.6, 3: 6.86, 4: 7.07, 5: 7.05, 6: 6.43, 7: 5.38, 8: 4.18, 9: 3.25, 10: 2.31, 11: 1.63, 12: 0.97, 13: 0.7, 14: 0.66, 15: 0.87, 16: 1.33, 17: 1.88, 18: 2.78, 19: 3.56, 20: 4.2, 21: 4.77, 22: 5.2, 23: 5.57},
        5:  {0: 6.22, 1: 6.67, 2: 6.96, 3: 7.23, 4: 7.36, 5: 7.01, 6: 6.26, 7: 5.3, 8: 4.26, 9: 3.27, 10: 2.41, 11: 1.86, 12: 1.36, 13: 0.94, 14: 0.85, 15: 0.95, 16: 1.22, 17: 1.7, 18: 2.44, 19: 3.31, 20: 4.07, 21: 4.66, 22: 5.26, 23: 5.76},
        6:  {0: 7.17, 1: 7.6, 2: 7.95, 3: 8.29, 4: 8.34, 5: 7.83, 6: 6.94, 7: 5.81, 8: 4.76, 9: 3.7, 10: 2.74, 11: 2.02, 12: 1.41, 13: 0.98, 14: 0.8, 15: 0.91, 16: 1.13, 17: 1.64, 18: 2.4, 19: 3.34, 20: 4.34, 21: 5.24, 22: 5.93, 23: 6.47},
        7:  {0: 6.23, 1: 6.61, 2: 6.95, 3: 7.31, 4: 7.5, 5: 7.19, 6: 6.43, 7: 5.42, 8: 4.41, 9: 3.39, 10: 2.52, 11: 1.86, 12: 1.39, 13: 1.11, 14: 0.91, 15: 0.84, 16: 1.02, 17: 1.47, 18: 2.12, 19: 3.01, 20: 3.92, 21: 4.65, 22: 5.27, 23: 5.78},
        8:  {0: 6.09, 1: 6.43, 2: 6.87, 3: 7.2, 4: 7.46, 5: 7.41, 6: 6.73, 7: 5.75, 8: 4.63, 9: 3.53, 10: 2.59, 11: 1.85, 12: 1.25, 13: 0.8, 14: 0.68, 15: 0.8, 16: 1.13, 17: 1.69, 18: 2.45, 19: 3.36, 20: 4.08, 21: 4.73, 22: 5.23, 23: 5.75},
        9:  {0: 5.65, 1: 5.96, 2: 6.19, 3: 6.35, 4: 6.49, 5: 6.54, 6: 6.27, 7: 5.49, 8: 4.34, 9: 3.25, 10: 2.25, 11: 1.5, 12: 0.94, 13: 0.7, 14: 0.72, 15: 0.87, 16: 1.28, 17: 1.94, 18: 2.75, 19: 3.49, 20: 4.11, 21: 4.59, 22: 5.02, 23: 5.36},
        10:  {0: 4.17, 1: 4.34, 2: 4.5, 3: 4.57, 4: 4.72, 5: 4.74, 6: 4.67, 7: 4.33, 8: 3.61, 9: 2.77, 10: 1.93, 11: 1.26, 12: 0.77, 13: 0.53, 14: 0.56, 15: 0.77, 16: 1.38, 17: 1.98, 18: 2.45, 19: 2.88, 20: 3.24, 21: 3.56, 22: 3.77, 23: 4.0},
        11:  {0: 3.0, 1: 3.05, 2: 3.07, 3: 3.15, 4: 3.24, 5: 3.24, 6: 3.25, 7: 3.17, 8: 2.86, 9: 2.24, 10: 1.63, 11: 1.1, 12: 0.77, 13: 0.64, 14: 0.71, 15: 0.99, 16: 1.38, 17: 1.66, 18: 1.91, 19: 2.17, 20: 2.41, 21: 2.66, 22: 2.85, 23: 3.0},
        12:  {0: 2.44, 1: 2.51, 2: 2.59, 3: 2.72, 4: 2.74, 5: 2.77, 6: 2.79, 7: 2.78, 8: 2.64, 9: 2.24, 10: 1.75, 11: 1.29, 12: 0.94, 13: 0.75, 14: 0.85, 15: 1.05, 16: 1.31, 17: 1.54, 18: 1.61, 19: 1.72, 20: 1.86, 21: 2.02, 22: 2.18, 23: 2.28},
    },
    "dallas": {
        1:  {0: 3.95, 1: 4.58, 2: 5.28, 3: 5.8, 4: 6.35, 5: 6.62, 6: 6.98, 7: 7.74, 8: 7.89, 9: 8.25, 10: 8.63, 11: 8.82, 12: 9.0, 13: 9.1, 14: 7.71, 15: 6.57, 16: 5.33, 17: 4.03, 18: 3.05, 19: 2.28, 20: 1.91, 21: 1.74, 22: 2.12, 23: 3.09},
        2:  {0: 4.44, 1: 5.25, 2: 5.83, 3: 6.22, 4: 6.63, 5: 7.26, 6: 7.68, 7: 8.16, 8: 8.76, 9: 8.79, 10: 9.23, 11: 8.96, 12: 9.45, 13: 9.23, 14: 8.74, 15: 7.18, 16: 6.0, 17: 5.13, 18: 4.04, 19: 2.92, 20: 2.57, 21: 2.16, 22: 2.49, 23: 3.34},
        3:  {0: 4.07, 1: 4.99, 2: 5.78, 3: 6.52, 4: 7.06, 5: 7.74, 6: 8.37, 7: 8.78, 8: 9.43, 9: 9.66, 10: 9.85, 11: 9.89, 12: 10.26, 13: 9.54, 14: 8.41, 15: 6.83, 16: 5.31, 17: 4.01, 18: 3.38, 19: 2.45, 20: 1.67, 21: 1.47, 22: 2.04, 23: 2.8},
        4:  {0: 3.25, 1: 4.09, 2: 4.9, 3: 5.71, 4: 6.29, 5: 6.67, 6: 7.31, 7: 7.4, 8: 8.1, 9: 8.29, 10: 8.85, 11: 9.03, 12: 8.44, 13: 7.52, 14: 6.65, 15: 5.44, 16: 4.29, 17: 3.26, 18: 2.65, 19: 2.17, 20: 1.68, 21: 1.43, 22: 1.55, 23: 2.18},
        5:  {0: 3.31, 1: 4.3, 2: 4.78, 3: 5.64, 4: 6.41, 5: 6.74, 6: 6.99, 7: 7.7, 8: 8.15, 9: 8.47, 10: 8.53, 11: 8.85, 12: 8.06, 13: 7.17, 14: 5.95, 15: 4.93, 16: 4.02, 17: 3.41, 18: 2.57, 19: 1.82, 20: 1.62, 21: 1.59, 22: 1.95, 23: 2.41},
        6:  {0: 3.0, 1: 4.01, 2: 4.49, 3: 5.15, 4: 6.06, 5: 6.6, 6: 7.18, 7: 7.62, 8: 8.07, 9: 8.44, 10: 8.77, 11: 8.7, 12: 8.03, 13: 7.2, 14: 5.9, 15: 4.87, 16: 3.68, 17: 2.65, 18: 1.92, 19: 1.59, 20: 1.17, 21: 1.25, 22: 1.32, 23: 1.84},
        7:  {0: 2.62, 1: 3.71, 2: 4.74, 3: 5.54, 4: 6.23, 5: 6.83, 6: 7.38, 7: 7.88, 8: 8.33, 9: 8.84, 10: 9.02, 11: 9.29, 12: 8.8, 13: 7.7, 14: 6.34, 15: 5.09, 16: 3.95, 17: 2.95, 18: 1.99, 19: 1.32, 20: 0.99, 21: 0.78, 22: 1.27, 23: 1.68},
        8:  {0: 2.7, 1: 3.64, 2: 4.56, 3: 5.43, 4: 6.01, 5: 6.47, 6: 7.1, 7: 7.73, 8: 8.19, 9: 8.84, 10: 9.17, 11: 9.44, 12: 8.98, 13: 7.91, 14: 6.5, 15: 5.02, 16: 3.74, 17: 2.97, 18: 2.0, 19: 1.16, 20: 1.04, 21: 0.97, 22: 1.32, 23: 2.05},
        9:  {0: 3.38, 1: 4.29, 2: 5.36, 3: 6.14, 4: 7.05, 5: 7.6, 6: 8.09, 7: 8.62, 8: 9.14, 9: 9.6, 10: 9.91, 11: 10.2, 12: 10.01, 13: 8.75, 14: 7.05, 15: 5.32, 16: 3.98, 17: 2.73, 18: 1.79, 19: 1.06, 20: 1.28, 21: 0.97, 22: 1.36, 23: 2.19},
        10:  {0: 3.83, 1: 4.83, 2: 5.69, 3: 6.49, 4: 7.01, 5: 7.71, 6: 8.1, 7: 8.61, 8: 9.3, 9: 9.64, 10: 9.81, 11: 10.17, 12: 10.03, 13: 8.87, 14: 7.33, 15: 5.67, 16: 4.29, 17: 2.95, 18: 2.01, 19: 1.57, 20: 0.94, 21: 1.05, 22: 1.73, 23: 2.93},
        11:  {0: 4.11, 1: 4.8, 2: 5.51, 3: 6.01, 4: 6.55, 5: 6.84, 6: 7.06, 7: 7.41, 8: 7.86, 9: 8.0, 10: 8.69, 11: 8.73, 12: 8.98, 13: 8.3, 14: 7.26, 15: 5.7, 16: 4.26, 17: 3.19, 18: 2.62, 19: 1.91, 20: 1.33, 21: 1.45, 22: 2.15, 23: 3.4},
        12:  {0: 4.28, 1: 5.03, 2: 5.33, 3: 5.87, 4: 6.3, 5: 6.75, 6: 6.88, 7: 7.34, 8: 7.65, 9: 8.03, 10: 8.27, 11: 8.39, 12: 8.75, 13: 8.45, 14: 7.3, 15: 6.09, 16: 4.75, 17: 3.42, 18: 2.62, 19: 1.89, 20: 1.45, 21: 1.45, 22: 2.07, 23: 3.25},
    },
    "houston": {
        1:  {0: 4.21, 1: 4.79, 2: 5.31, 3: 5.79, 4: 6.06, 5: 6.42, 6: 6.94, 7: 6.79, 8: 7.15, 9: 7.33, 10: 7.83, 11: 7.55, 12: 7.77, 13: 7.8, 14: 6.44, 15: 5.0, 16: 3.72, 17: 2.74, 18: 1.99, 19: 1.46, 20: 1.55, 21: 1.73, 22: 2.35, 23: 3.7},
        2:  {0: 4.78, 1: 5.48, 2: 5.8, 3: 6.61, 4: 6.73, 5: 7.02, 6: 7.29, 7: 7.26, 8: 7.64, 9: 8.02, 10: 8.23, 11: 7.96, 12: 7.94, 13: 7.74, 14: 6.37, 15: 4.84, 16: 3.92, 17: 2.9, 18: 2.17, 19: 1.84, 20: 1.65, 21: 1.99, 22: 2.27, 23: 3.59},
        3:  {0: 4.58, 1: 5.39, 2: 5.98, 3: 6.39, 4: 6.74, 5: 7.19, 6: 7.43, 7: 7.7, 8: 8.05, 9: 8.28, 10: 8.35, 11: 8.37, 12: 8.45, 13: 7.44, 14: 6.07, 15: 4.79, 16: 3.8, 17: 2.46, 18: 1.82, 19: 1.33, 20: 1.23, 21: 1.52, 22: 2.11, 23: 3.06},
        4:  {0: 3.79, 1: 4.7, 2: 5.15, 3: 5.62, 4: 6.04, 5: 6.26, 6: 6.59, 7: 6.8, 8: 7.01, 9: 7.06, 10: 7.15, 11: 7.44, 12: 6.77, 13: 5.53, 14: 4.5, 15: 3.24, 16: 2.21, 17: 1.42, 18: 1.06, 19: 0.81, 20: 0.88, 21: 1.35, 22: 1.85, 23: 2.76},
        5:  {0: 3.84, 1: 4.71, 2: 5.19, 3: 5.64, 4: 5.99, 5: 6.28, 6: 6.6, 7: 6.75, 8: 6.94, 9: 7.01, 10: 7.14, 11: 7.03, 12: 6.33, 13: 5.15, 14: 4.06, 15: 3.27, 16: 2.45, 17: 1.74, 18: 1.31, 19: 1.61, 20: 1.07, 21: 1.46, 22: 1.81, 23: 2.75},
        6:  {0: 4.13, 1: 5.07, 2: 5.96, 3: 6.36, 4: 6.64, 5: 6.98, 6: 7.17, 7: 7.42, 8: 7.55, 9: 7.69, 10: 7.83, 11: 7.54, 12: 6.57, 13: 5.42, 14: 4.14, 15: 3.14, 16: 2.24, 17: 1.77, 18: 1.37, 19: 1.32, 20: 1.21, 21: 1.22, 22: 1.85, 23: 2.95},
        7:  {0: 3.96, 1: 5.04, 2: 5.67, 3: 6.25, 4: 6.62, 5: 6.99, 6: 7.16, 7: 7.5, 8: 7.69, 9: 7.7, 10: 7.77, 11: 7.97, 12: 6.92, 13: 5.56, 14: 4.45, 15: 3.28, 16: 2.28, 17: 2.01, 18: 2.3, 19: 2.01, 20: 1.86, 21: 1.84, 22: 2.25, 23: 3.13},
        8:  {0: 4.15, 1: 5.22, 2: 5.91, 3: 6.51, 4: 6.85, 5: 7.2, 6: 7.5, 7: 7.73, 8: 8.04, 9: 8.33, 10: 8.31, 11: 8.22, 12: 7.41, 13: 5.96, 14: 4.69, 15: 3.57, 16: 2.54, 17: 1.99, 18: 1.51, 19: 1.29, 20: 1.22, 21: 1.5, 22: 2.19, 23: 3.1},
        9:  {0: 4.44, 1: 5.14, 2: 5.84, 3: 6.4, 4: 6.87, 5: 7.14, 6: 7.47, 7: 7.77, 8: 7.99, 9: 8.25, 10: 8.36, 11: 8.63, 12: 7.94, 13: 6.27, 14: 4.69, 15: 3.43, 16: 2.33, 17: 1.71, 18: 1.52, 19: 1.08, 20: 1.16, 21: 1.37, 22: 2.17, 23: 3.14},
        10:  {0: 4.49, 1: 5.43, 2: 5.93, 3: 6.65, 4: 7.23, 5: 7.47, 6: 7.89, 7: 8.18, 8: 8.54, 9: 8.88, 10: 8.84, 11: 8.91, 12: 8.67, 13: 6.83, 14: 5.22, 15: 3.77, 16: 2.56, 17: 1.91, 18: 1.27, 19: 0.98, 20: 0.75, 21: 1.4, 22: 2.07, 23: 3.66},
        11:  {0: 4.53, 1: 5.03, 2: 5.49, 3: 5.98, 4: 6.21, 5: 6.89, 6: 7.12, 7: 7.49, 8: 7.84, 9: 7.99, 10: 7.93, 11: 8.19, 12: 7.92, 13: 6.85, 14: 5.27, 15: 3.88, 16: 2.55, 17: 1.77, 18: 1.19, 19: 0.98, 20: 1.12, 21: 1.64, 22: 2.55, 23: 3.89},
        12:  {0: 4.7, 1: 4.98, 2: 5.63, 3: 5.84, 4: 6.26, 5: 6.47, 6: 6.6, 7: 6.93, 8: 7.16, 9: 7.34, 10: 7.44, 11: 7.35, 12: 7.63, 13: 7.28, 14: 6.02, 15: 4.79, 16: 3.34, 17: 2.22, 18: 1.61, 19: 1.31, 20: 1.04, 21: 1.41, 22: 2.35, 23: 3.63},
    },
    "seattle": {
        1:  {0: 1.7, 1: 2.15, 2: 2.52, 3: 2.68, 4: 2.78, 5: 3.0, 6: 3.16, 7: 3.34, 8: 3.51, 9: 3.79, 10: 3.8, 11: 4.13, 12: 4.2, 13: 4.12, 14: 3.98, 15: 3.88, 16: 3.5, 17: 3.06, 18: 2.41, 19: 1.8, 20: 1.3, 21: 1.0, 22: 0.85, 23: 1.23},
        2:  {0: 1.68, 1: 2.19, 2: 2.54, 3: 2.79, 4: 3.15, 5: 3.33, 6: 3.47, 7: 3.89, 8: 4.16, 9: 4.35, 10: 4.4, 11: 4.53, 12: 4.6, 13: 4.58, 14: 4.9, 15: 4.8, 16: 3.88, 17: 3.37, 18: 2.53, 19: 1.7, 20: 1.25, 21: 1.17, 22: 0.89, 23: 1.2},
        3:  {0: 2.08, 1: 2.79, 2: 3.68, 3: 4.19, 4: 4.3, 5: 4.72, 6: 5.11, 7: 5.47, 8: 5.77, 9: 5.93, 10: 6.25, 11: 6.51, 12: 6.64, 13: 6.52, 14: 6.61, 15: 6.04, 16: 5.01, 17: 4.08, 18: 3.18, 19: 2.4, 20: 1.96, 21: 1.5, 22: 1.51, 23: 1.35},
        4:  {0: 2.01, 1: 2.86, 2: 4.01, 3: 4.67, 4: 5.25, 5: 5.7, 6: 6.29, 7: 6.75, 8: 7.12, 9: 7.53, 10: 7.78, 11: 7.99, 12: 8.27, 13: 8.21, 14: 7.49, 15: 6.72, 16: 5.64, 17: 4.96, 18: 3.88, 19: 3.04, 20: 2.37, 21: 1.95, 22: 1.75, 23: 1.78},
        5:  {0: 2.08, 1: 2.83, 2: 3.83, 3: 5.14, 4: 5.75, 5: 6.55, 6: 7.09, 7: 7.61, 8: 8.18, 9: 8.55, 10: 8.59, 11: 8.77, 12: 9.13, 13: 8.85, 14: 8.09, 15: 7.39, 16: 6.47, 17: 5.49, 18: 4.58, 19: 3.6, 20: 2.7, 21: 2.19, 22: 1.76, 23: 1.8},
        6:  {0: 2.19, 1: 2.78, 2: 3.65, 3: 5.17, 4: 6.22, 5: 6.94, 6: 7.59, 7: 8.36, 8: 8.68, 9: 9.21, 10: 9.47, 11: 9.91, 12: 10.26, 13: 9.71, 14: 8.88, 15: 8.03, 16: 7.13, 17: 6.06, 18: 4.95, 19: 3.77, 20: 3.14, 21: 2.46, 22: 2.0, 23: 1.9},
        7:  {0: 1.52, 1: 2.17, 2: 3.47, 3: 5.53, 4: 6.99, 5: 7.99, 6: 8.94, 7: 9.82, 8: 10.37, 9: 11.14, 10: 11.54, 11: 12.11, 12: 12.38, 13: 11.87, 14: 11.02, 15: 10.01, 16: 8.98, 17: 7.55, 18: 6.22, 19: 4.89, 20: 3.59, 21: 2.45, 22: 1.7, 23: 1.42},
        8:  {0: 1.73, 1: 2.55, 2: 4.08, 3: 5.68, 4: 6.53, 5: 7.34, 6: 7.99, 7: 8.85, 8: 9.26, 9: 9.55, 10: 10.15, 11: 10.23, 12: 10.58, 13: 10.92, 14: 10.18, 15: 8.99, 16: 8.12, 17: 6.85, 18: 5.47, 19: 4.4, 20: 3.15, 21: 2.2, 22: 1.75, 23: 1.6},
        9:  {0: 1.91, 1: 3.07, 2: 4.47, 3: 5.25, 4: 5.91, 5: 6.48, 6: 7.06, 7: 7.53, 8: 7.82, 9: 8.2, 10: 8.62, 11: 8.81, 12: 8.96, 13: 9.12, 14: 8.64, 15: 7.67, 16: 6.62, 17: 5.63, 18: 4.59, 19: 3.54, 20: 2.64, 21: 2.06, 22: 1.78, 23: 1.66},
        10:  {0: 2.05, 1: 3.11, 2: 3.68, 3: 4.04, 4: 4.18, 5: 4.64, 6: 5.02, 7: 5.56, 8: 5.72, 9: 5.93, 10: 6.25, 11: 6.32, 12: 6.38, 13: 6.61, 14: 6.63, 15: 5.96, 16: 5.2, 17: 4.3, 18: 3.17, 19: 2.19, 20: 1.72, 21: 1.22, 22: 1.25, 23: 1.59},
        11:  {0: 2.05, 1: 2.25, 2: 2.5, 3: 2.64, 4: 2.76, 5: 2.87, 6: 3.1, 7: 3.21, 8: 3.38, 9: 3.76, 10: 3.88, 11: 4.01, 12: 4.18, 13: 4.21, 14: 4.16, 15: 4.13, 16: 3.41, 17: 2.61, 18: 1.85, 19: 1.36, 20: 1.11, 21: 0.99, 22: 1.13, 23: 1.52},
        12:  {0: 2.14, 1: 2.34, 2: 2.32, 3: 2.59, 4: 2.55, 5: 2.61, 6: 2.84, 7: 2.8, 8: 2.92, 9: 3.14, 10: 3.27, 11: 3.36, 12: 3.39, 13: 3.31, 14: 3.28, 15: 3.14, 16: 2.93, 17: 2.66, 18: 2.21, 19: 1.69, 20: 1.4, 21: 1.45, 22: 1.22, 23: 1.58},
    },
    "denver": {
        1:  {0: 6.3, 1: 7.23, 2: 8.11, 3: 8.68, 4: 8.9, 5: 9.25, 6: 9.32, 7: 9.44, 8: 9.68, 9: 9.99, 10: 9.92, 11: 9.87, 12: 10.02, 13: 10.12, 14: 9.52, 15: 7.26, 16: 5.51, 17: 3.7, 18: 2.64, 19: 2.0, 20: 1.85, 21: 2.34, 22: 3.24, 23: 5.21},
        2:  {0: 6.6, 1: 7.83, 2: 8.46, 3: 9.07, 4: 9.59, 5: 9.95, 6: 10.39, 7: 10.42, 8: 10.86, 9: 11.32, 10: 11.23, 11: 11.26, 12: 11.68, 13: 11.7, 14: 10.01, 15: 7.71, 16: 6.07, 17: 4.48, 18: 2.98, 19: 2.31, 20: 2.22, 21: 2.19, 22: 2.94, 23: 4.91},
        3:  {0: 5.46, 1: 7.13, 2: 7.99, 3: 9.04, 4: 9.61, 5: 10.27, 6: 11.06, 7: 11.53, 8: 12.08, 9: 12.64, 10: 12.95, 11: 13.01, 12: 12.98, 13: 12.5, 14: 9.66, 15: 7.6, 16: 5.96, 17: 4.35, 18: 3.14, 19: 2.5, 20: 2.14, 21: 1.91, 22: 2.68, 23: 3.96},
        4:  {0: 5.56, 1: 7.48, 2: 8.91, 3: 9.73, 4: 10.45, 5: 11.39, 6: 11.81, 7: 12.37, 8: 12.92, 9: 13.38, 10: 13.71, 11: 14.0, 12: 14.09, 13: 11.69, 14: 9.45, 15: 7.65, 16: 6.2, 17: 4.89, 18: 3.61, 19: 2.93, 20: 2.46, 21: 2.66, 22: 3.37, 23: 3.81},
        5:  {0: 4.5, 1: 6.28, 2: 7.83, 3: 8.86, 4: 9.81, 5: 10.36, 6: 10.94, 7: 11.56, 8: 12.05, 9: 12.5, 10: 12.75, 11: 12.78, 12: 11.59, 13: 9.86, 14: 7.86, 15: 5.99, 16: 4.76, 17: 3.5, 18: 3.41, 19: 2.4, 20: 2.68, 21: 2.87, 22: 3.55, 23: 3.65},
        6:  {0: 5.01, 1: 6.78, 2: 8.54, 3: 9.88, 4: 10.67, 5: 11.22, 6: 11.93, 7: 12.62, 8: 13.21, 9: 13.75, 10: 14.27, 11: 14.28, 12: 12.87, 13: 10.62, 14: 8.53, 15: 6.78, 16: 5.04, 17: 3.54, 18: 2.65, 19: 1.97, 20: 2.17, 21: 2.23, 22: 2.9, 23: 4.18},
        7:  {0: 5.77, 1: 7.85, 2: 9.56, 3: 10.59, 4: 11.34, 5: 11.99, 6: 12.65, 7: 13.1, 8: 13.73, 9: 14.2, 10: 14.74, 11: 14.8, 12: 13.71, 13: 11.22, 14: 9.21, 15: 6.97, 16: 5.02, 17: 3.32, 18: 2.0, 19: 1.6, 20: 1.8, 21: 2.52, 22: 3.27, 23: 4.68},
        8:  {0: 5.78, 1: 7.94, 2: 9.23, 3: 10.29, 4: 10.98, 5: 11.59, 6: 12.19, 7: 12.66, 8: 13.13, 9: 13.71, 10: 14.18, 11: 14.53, 12: 14.17, 13: 11.61, 14: 9.16, 15: 7.03, 16: 5.13, 17: 3.51, 18: 2.17, 19: 1.31, 20: 1.24, 21: 2.27, 22: 3.06, 23: 4.43},
        9:  {0: 5.74, 1: 8.31, 2: 9.01, 3: 9.89, 4: 10.66, 5: 11.8, 6: 12.37, 7: 13.12, 8: 13.65, 9: 14.24, 10: 14.7, 11: 15.19, 12: 15.11, 13: 12.79, 14: 9.92, 15: 7.37, 16: 5.19, 17: 3.63, 18: 2.36, 19: 1.58, 20: 1.63, 21: 1.48, 22: 2.66, 23: 3.85},
        10:  {0: 6.74, 1: 8.17, 2: 9.32, 3: 10.35, 4: 11.25, 5: 11.57, 6: 12.07, 7: 12.42, 8: 12.92, 9: 13.36, 10: 13.58, 11: 13.59, 12: 14.21, 13: 12.68, 14: 9.61, 15: 7.02, 16: 5.0, 17: 3.28, 18: 2.27, 19: 1.5, 20: 1.03, 21: 1.26, 22: 2.23, 23: 4.73},
        11:  {0: 7.19, 1: 8.17, 2: 9.01, 3: 9.55, 4: 9.71, 5: 10.29, 6: 10.59, 7: 10.73, 8: 11.13, 9: 11.53, 10: 11.94, 11: 12.02, 12: 12.03, 13: 12.19, 14: 10.19, 15: 6.98, 16: 4.87, 17: 3.32, 18: 2.17, 19: 1.63, 20: 1.28, 21: 1.62, 22: 2.97, 23: 5.69},
        12:  {0: 7.6, 1: 8.45, 2: 9.03, 3: 9.52, 4: 9.81, 5: 10.38, 6: 10.57, 7: 10.69, 8: 11.06, 9: 10.97, 10: 11.22, 11: 11.37, 12: 11.34, 13: 11.61, 14: 10.75, 15: 7.81, 16: 5.34, 17: 3.24, 18: 1.88, 19: 1.37, 20: 1.14, 21: 1.71, 22: 3.36, 23: 6.12},
    },
    "atlanta": {
        1:  {0: 4.23, 1: 4.82, 2: 5.34, 3: 5.74, 4: 6.12, 5: 6.59, 6: 6.75, 7: 7.06, 8: 7.45, 9: 7.24, 10: 7.63, 11: 7.73, 12: 7.72, 13: 6.96, 14: 5.97, 15: 4.54, 16: 3.36, 17: 2.58, 18: 1.78, 19: 1.29, 20: 1.37, 21: 1.77, 22: 2.65, 23: 3.58},
        2:  {0: 4.66, 1: 5.44, 2: 5.95, 3: 6.37, 4: 6.81, 5: 7.26, 6: 7.63, 7: 7.94, 8: 8.12, 9: 8.01, 10: 8.42, 11: 8.99, 12: 8.74, 13: 7.47, 14: 6.62, 15: 5.39, 16: 4.18, 17: 3.0, 18: 2.25, 19: 1.46, 20: 1.56, 21: 1.68, 22: 2.56, 23: 3.76},
        3:  {0: 4.64, 1: 5.48, 2: 6.1, 3: 6.73, 4: 7.44, 5: 7.85, 6: 8.03, 7: 8.42, 8: 8.9, 9: 9.19, 10: 9.59, 11: 9.68, 12: 8.95, 13: 7.68, 14: 6.27, 15: 4.9, 16: 3.68, 17: 2.73, 18: 2.07, 19: 1.48, 20: 1.15, 21: 1.43, 22: 2.23, 23: 3.46},
        4:  {0: 4.38, 1: 5.43, 2: 6.19, 3: 6.9, 4: 7.37, 5: 7.91, 6: 8.37, 7: 8.7, 8: 9.3, 9: 9.62, 10: 9.67, 11: 9.38, 12: 8.38, 13: 7.05, 14: 5.66, 15: 4.28, 16: 3.08, 17: 2.39, 18: 1.76, 19: 1.16, 20: 1.19, 21: 1.32, 22: 2.04, 23: 3.02},
        5:  {0: 3.94, 1: 4.85, 2: 5.53, 3: 6.04, 4: 6.62, 5: 7.2, 6: 7.69, 7: 8.12, 8: 8.36, 9: 8.58, 10: 8.74, 11: 8.09, 12: 7.23, 13: 5.95, 14: 4.79, 15: 3.93, 16: 2.76, 17: 1.92, 18: 1.49, 19: 1.23, 20: 1.23, 21: 1.31, 22: 1.76, 23: 2.56},
        6:  {0: 4.51, 1: 5.12, 2: 5.79, 3: 6.5, 4: 7.16, 5: 7.48, 6: 8.15, 7: 8.22, 8: 8.53, 9: 8.66, 10: 8.77, 11: 8.03, 12: 6.9, 13: 5.57, 14: 4.37, 15: 3.07, 16: 2.23, 17: 1.47, 18: 1.14, 19: 1.41, 20: 1.68, 21: 1.74, 22: 2.37, 23: 3.51},
        7:  {0: 4.73, 1: 5.4, 2: 6.08, 3: 6.72, 4: 7.17, 5: 7.55, 6: 7.9, 7: 8.07, 8: 8.42, 9: 8.61, 10: 8.8, 11: 8.11, 12: 6.83, 13: 5.65, 14: 4.22, 15: 3.0, 16: 2.06, 17: 1.5, 18: 1.14, 19: 1.34, 20: 1.77, 21: 2.14, 22: 2.74, 23: 3.63},
        8:  {0: 4.66, 1: 5.44, 2: 6.08, 3: 6.46, 4: 6.85, 5: 7.19, 6: 7.48, 7: 7.8, 8: 7.9, 9: 8.06, 10: 8.27, 11: 8.01, 12: 7.01, 13: 5.72, 14: 4.4, 15: 3.25, 16: 2.25, 17: 1.4, 18: 1.25, 19: 1.58, 20: 1.73, 21: 2.13, 22: 2.97, 23: 3.7},
        9:  {0: 4.18, 1: 4.77, 2: 5.53, 3: 6.12, 4: 6.53, 5: 6.81, 6: 7.12, 7: 7.59, 8: 7.79, 9: 8.0, 10: 8.13, 11: 8.24, 12: 6.86, 13: 5.53, 14: 3.94, 15: 2.71, 16: 2.01, 17: 1.33, 18: 1.04, 19: 0.89, 20: 0.98, 21: 1.24, 22: 2.07, 23: 3.28},
        10:  {0: 4.81, 1: 5.53, 2: 6.28, 3: 6.8, 4: 7.53, 5: 7.7, 6: 8.19, 7: 8.52, 8: 8.69, 9: 9.16, 10: 9.29, 11: 9.41, 12: 8.1, 13: 6.42, 14: 4.83, 15: 3.4, 16: 2.24, 17: 1.41, 18: 0.77, 19: 0.44, 20: 0.67, 21: 1.33, 22: 2.75, 23: 4.14},
        11:  {0: 4.85, 1: 5.49, 2: 6.21, 3: 6.64, 4: 6.92, 5: 7.33, 6: 7.57, 7: 7.8, 8: 8.35, 9: 8.24, 10: 8.1, 11: 8.7, 12: 8.21, 13: 6.76, 14: 5.08, 15: 3.72, 16: 2.43, 17: 1.47, 18: 0.93, 19: 0.7, 20: 0.96, 21: 1.74, 22: 3.27, 23: 4.28},
        12:  {0: 4.11, 1: 4.74, 2: 5.34, 3: 5.56, 4: 5.93, 5: 6.22, 6: 6.17, 7: 6.68, 8: 7.07, 9: 6.95, 10: 7.28, 11: 7.52, 12: 7.51, 13: 6.75, 14: 5.45, 15: 4.09, 16: 2.9, 17: 2.04, 18: 1.29, 19: 1.16, 20: 1.04, 21: 1.82, 22: 2.86, 23: 3.72},
    },
    "paris": {
        1:  {0: 3.23, 1: 3.36, 2: 3.51, 3: 3.6, 4: 3.71, 5: 3.78, 6: 3.82, 7: 3.9, 8: 3.75, 9: 3.15, 10: 2.49, 11: 1.86, 12: 1.31, 13: 0.98, 14: 0.86, 15: 0.99, 16: 1.35, 17: 1.79, 18: 2.14, 19: 2.37, 20: 2.55, 21: 2.71, 22: 2.92, 23: 3.1},
        2:  {0: 4.59, 1: 4.84, 2: 5.05, 3: 5.14, 4: 5.31, 5: 5.45, 6: 5.57, 7: 5.54, 8: 4.74, 9: 3.73, 10: 2.72, 11: 1.85, 12: 1.21, 13: 0.76, 14: 0.56, 15: 0.62, 16: 1.04, 17: 1.81, 18: 2.42, 19: 2.92, 20: 3.4, 21: 3.75, 22: 4.16, 23: 4.38},
        3:  {0: 6.82, 1: 7.15, 2: 7.49, 3: 7.73, 4: 7.94, 5: 8.06, 6: 8.11, 7: 7.25, 8: 5.73, 9: 4.4, 10: 3.15, 11: 2.13, 12: 1.33, 13: 0.83, 14: 0.57, 15: 0.72, 16: 1.04, 17: 1.79, 18: 2.91, 19: 3.87, 20: 4.6, 21: 5.23, 22: 5.75, 23: 6.21},
        4:  {0: 7.4, 1: 7.85, 2: 8.35, 3: 8.68, 4: 9.02, 5: 9.19, 6: 8.41, 7: 6.98, 8: 5.45, 9: 4.07, 10: 2.87, 11: 2.01, 12: 1.41, 13: 0.94, 14: 0.74, 15: 0.77, 16: 0.92, 17: 1.55, 18: 2.56, 19: 3.72, 20: 4.59, 21: 5.37, 22: 6.03, 23: 6.7},
        5:  {0: 7.67, 1: 8.19, 2: 8.64, 3: 9.03, 4: 9.23, 5: 8.87, 6: 7.78, 7: 6.45, 8: 5.07, 9: 3.94, 10: 2.93, 11: 2.19, 12: 1.58, 13: 1.19, 14: 0.79, 15: 0.84, 16: 1.13, 17: 1.58, 18: 2.19, 19: 3.33, 20: 4.5, 21: 5.46, 22: 6.25, 23: 6.96},
        6:  {0: 8.33, 1: 8.93, 2: 9.5, 3: 9.96, 4: 10.13, 5: 9.41, 6: 8.19, 7: 6.8, 8: 5.52, 9: 4.17, 10: 3.11, 11: 2.25, 12: 1.65, 13: 1.22, 14: 0.91, 15: 0.71, 16: 0.87, 17: 1.31, 18: 2.04, 19: 3.25, 20: 4.7, 21: 5.95, 22: 6.85, 23: 7.66},
        7:  {0: 7.81, 1: 8.46, 2: 8.98, 3: 9.39, 4: 9.68, 5: 9.23, 6: 7.93, 7: 6.58, 8: 5.37, 9: 4.26, 10: 3.27, 11: 2.49, 12: 1.74, 13: 1.26, 14: 0.92, 15: 0.85, 16: 0.85, 17: 1.2, 18: 1.9, 19: 3.09, 20: 4.45, 21: 5.49, 22: 6.39, 23: 7.15},
        8:  {0: 8.16, 1: 8.67, 2: 9.14, 3: 9.51, 4: 9.84, 5: 9.92, 6: 8.9, 7: 7.43, 8: 5.86, 9: 4.49, 10: 3.25, 11: 2.36, 12: 1.62, 13: 1.07, 14: 0.83, 15: 0.69, 16: 0.93, 17: 1.54, 18: 2.49, 19: 3.91, 20: 5.08, 21: 6.1, 22: 6.88, 23: 7.58},
        9:  {0: 7.31, 1: 7.73, 2: 8.05, 3: 8.42, 4: 8.72, 5: 8.87, 6: 8.52, 7: 7.2, 8: 5.61, 9: 4.18, 10: 2.98, 11: 2.08, 12: 1.43, 13: 0.89, 14: 0.67, 15: 0.71, 16: 1.15, 17: 2.02, 18: 3.34, 19: 4.44, 20: 5.34, 21: 6.06, 22: 6.52, 23: 6.96},
        10:  {0: 6.12, 1: 6.42, 2: 6.74, 3: 6.85, 4: 7.01, 5: 7.11, 6: 7.14, 7: 6.53, 8: 5.21, 9: 3.9, 10: 2.7, 11: 1.77, 12: 1.11, 13: 0.7, 14: 0.72, 15: 0.86, 16: 1.5, 17: 2.54, 18: 3.45, 19: 4.19, 20: 4.67, 21: 5.05, 22: 5.42, 23: 5.78},
        11:  {0: 3.83, 1: 4.06, 2: 4.2, 3: 4.31, 4: 4.39, 5: 4.42, 6: 4.43, 7: 4.33, 8: 3.82, 9: 3.05, 10: 2.22, 11: 1.53, 12: 0.95, 13: 0.61, 14: 0.58, 15: 0.88, 16: 1.52, 17: 2.1, 18: 2.48, 19: 2.84, 20: 3.14, 21: 3.38, 22: 3.62, 23: 3.9},
        12:  {0: 2.94, 1: 3.0, 2: 3.08, 3: 3.18, 4: 3.15, 5: 3.17, 6: 3.2, 7: 3.23, 8: 3.16, 9: 2.7, 10: 2.17, 11: 1.56, 12: 1.16, 13: 0.91, 14: 0.76, 15: 1.06, 16: 1.55, 17: 1.85, 18: 2.06, 19: 2.17, 20: 2.29, 21: 2.43, 22: 2.47, 23: 2.64},
    },
    "madrid": {
        1:  {0: 7.7, 1: 8.07, 2: 8.5, 3: 8.84, 4: 9.09, 5: 9.17, 6: 9.38, 7: 9.45, 8: 9.14, 9: 7.47, 10: 5.7, 11: 3.81, 12: 2.36, 13: 1.26, 14: 0.67, 15: 0.56, 16: 1.0, 17: 2.54, 18: 3.8, 19: 4.75, 20: 5.45, 21: 6.13, 22: 6.59, 23: 7.16},
        2:  {0: 9.13, 1: 9.77, 2: 10.23, 3: 10.7, 4: 11.16, 5: 11.52, 6: 11.82, 7: 11.87, 8: 10.67, 9: 8.48, 10: 6.31, 11: 4.18, 12: 2.56, 13: 1.5, 14: 0.92, 15: 0.55, 16: 0.61, 17: 1.63, 18: 3.42, 19: 4.66, 20: 5.85, 21: 6.69, 22: 7.5, 23: 8.4},
        3:  {0: 7.85, 1: 8.38, 2: 8.92, 3: 9.26, 4: 9.72, 5: 10.05, 6: 10.42, 7: 9.8, 8: 8.07, 9: 6.23, 10: 4.67, 11: 3.32, 12: 2.17, 13: 1.4, 14: 0.92, 15: 0.74, 16: 0.95, 17: 1.55, 18: 2.74, 19: 3.96, 20: 4.77, 21: 5.5, 22: 6.36, 23: 7.08},
        4:  {0: 9.58, 1: 10.42, 2: 11.16, 3: 11.72, 4: 12.33, 5: 12.79, 6: 12.62, 7: 10.93, 8: 8.71, 9: 6.7, 10: 4.99, 11: 3.63, 12: 2.43, 13: 1.54, 14: 1.14, 15: 0.9, 16: 1.0, 17: 1.53, 18: 2.66, 19: 4.25, 20: 5.48, 21: 6.68, 22: 7.72, 23: 8.62},
        5:  {0: 10.58, 1: 11.49, 2: 12.32, 3: 13.02, 4: 13.64, 5: 14.06, 6: 12.82, 7: 10.76, 8: 8.51, 9: 6.58, 10: 4.89, 11: 3.47, 12: 2.45, 13: 1.7, 14: 1.05, 15: 1.1, 16: 1.22, 17: 1.58, 18: 2.47, 19: 4.03, 20: 5.54, 21: 6.97, 22: 8.31, 23: 9.35},
        6:  {0: 10.69, 1: 11.67, 2: 12.56, 3: 13.32, 4: 13.96, 5: 14.28, 6: 12.81, 7: 10.84, 8: 8.84, 9: 6.94, 10: 5.15, 11: 3.68, 12: 2.6, 13: 1.66, 14: 1.2, 15: 1.03, 16: 1.08, 17: 1.52, 18: 2.57, 19: 3.92, 20: 5.57, 21: 6.91, 22: 8.22, 23: 9.49},
        7:  {0: 11.62, 1: 12.79, 2: 13.93, 3: 14.79, 4: 15.71, 5: 16.32, 6: 14.86, 7: 12.58, 8: 10.24, 9: 8.04, 10: 6.06, 11: 4.36, 12: 2.93, 13: 1.86, 14: 1.16, 15: 0.74, 16: 0.51, 17: 0.87, 18: 1.57, 19: 3.02, 20: 4.92, 21: 6.57, 22: 8.35, 23: 10.01},
        8:  {0: 10.9, 1: 12.01, 2: 13.03, 3: 13.9, 4: 14.74, 5: 15.55, 6: 15.06, 7: 12.95, 8: 10.53, 9: 8.18, 10: 6.22, 11: 4.41, 12: 2.87, 13: 1.71, 14: 0.99, 15: 0.7, 16: 0.51, 17: 0.97, 18: 1.86, 19: 3.52, 20: 5.31, 21: 7.0, 22: 8.53, 23: 9.87},
        9:  {0: 9.0, 1: 9.82, 2: 10.62, 3: 11.26, 4: 11.83, 5: 12.35, 6: 12.55, 7: 11.08, 8: 8.86, 9: 6.88, 10: 5.17, 11: 3.62, 12: 2.41, 13: 1.52, 14: 1.07, 15: 0.66, 16: 0.72, 17: 1.23, 18: 2.68, 19: 4.13, 20: 5.36, 21: 6.59, 22: 7.58, 23: 8.43},
        10:  {0: 8.77, 1: 9.29, 2: 9.78, 3: 10.23, 4: 10.66, 5: 11.0, 6: 11.15, 7: 10.6, 8: 8.85, 9: 6.88, 10: 4.88, 11: 3.31, 12: 2.13, 13: 1.36, 14: 0.84, 15: 0.6, 16: 0.96, 17: 2.0, 18: 3.53, 19: 4.77, 20: 5.75, 21: 6.67, 22: 7.42, 23: 8.17},
        11:  {0: 7.15, 1: 7.54, 2: 7.8, 3: 8.21, 4: 8.37, 5: 8.66, 6: 8.75, 7: 8.7, 8: 7.62, 9: 6.07, 10: 4.38, 11: 2.95, 12: 1.77, 13: 0.98, 14: 0.66, 15: 0.57, 16: 1.18, 17: 2.66, 18: 3.69, 19: 4.61, 20: 5.29, 21: 5.89, 22: 6.36, 23: 6.84},
        12:  {0: 6.69, 1: 7.12, 2: 7.44, 3: 7.84, 4: 8.09, 5: 8.29, 6: 8.27, 7: 8.34, 8: 7.91, 9: 6.48, 10: 4.93, 11: 3.37, 12: 2.02, 13: 1.0, 14: 0.52, 15: 0.53, 16: 1.24, 17: 2.74, 18: 3.65, 19: 4.4, 20: 4.88, 21: 5.49, 22: 5.98, 23: 6.48},
    },
    "amsterdam": {
        1:  {0: 2.72, 1: 2.82, 2: 2.9, 3: 2.95, 4: 2.98, 5: 2.95, 6: 2.89, 7: 2.84, 8: 2.57, 9: 1.97, 10: 1.39, 11: 0.99, 12: 0.86, 13: 0.89, 14: 1.08, 15: 1.56, 16: 1.95, 17: 2.17, 18: 2.27, 19: 2.32, 20: 2.43, 21: 2.56, 22: 2.68, 23: 2.79},
        2:  {0: 3.69, 1: 3.75, 2: 3.89, 3: 4.02, 4: 4.06, 5: 4.12, 6: 4.09, 7: 3.78, 8: 3.18, 9: 2.41, 10: 1.75, 11: 1.2, 12: 0.83, 13: 0.71, 14: 0.83, 15: 1.18, 16: 1.74, 17: 2.33, 18: 2.61, 19: 2.75, 20: 3.06, 21: 3.3, 22: 3.52, 23: 3.61},
        3:  {0: 5.84, 1: 6.06, 2: 6.29, 3: 6.42, 4: 6.48, 5: 6.59, 6: 6.2, 7: 5.06, 8: 3.84, 9: 2.78, 10: 1.93, 11: 1.22, 12: 0.83, 13: 0.6, 14: 0.64, 15: 0.93, 16: 1.68, 17: 2.73, 18: 3.49, 19: 4.07, 20: 4.45, 21: 4.85, 22: 5.09, 23: 5.42},
        4:  {0: 6.19, 1: 6.46, 2: 6.66, 3: 6.76, 4: 6.86, 5: 6.34, 6: 5.14, 7: 4.02, 8: 3.13, 9: 2.38, 10: 1.82, 11: 1.25, 12: 0.94, 13: 0.77, 14: 0.79, 15: 1.05, 16: 1.53, 17: 2.34, 18: 3.33, 19: 4.09, 20: 4.61, 21: 5.04, 22: 5.49, 23: 5.74},
        5:  {0: 6.95, 1: 7.23, 2: 7.4, 3: 7.55, 4: 7.26, 5: 6.02, 6: 4.93, 7: 3.88, 8: 3.0, 9: 2.31, 10: 1.74, 11: 1.39, 12: 1.07, 13: 0.96, 14: 1.14, 15: 1.38, 16: 1.93, 17: 2.68, 18: 3.64, 19: 4.61, 20: 5.3, 21: 5.75, 22: 6.25, 23: 6.54},
        6:  {0: 6.98, 1: 7.29, 2: 7.58, 3: 7.75, 4: 7.11, 5: 5.89, 6: 4.74, 7: 3.81, 8: 2.93, 9: 2.16, 10: 1.66, 11: 1.26, 12: 0.93, 13: 0.86, 14: 0.97, 15: 1.19, 16: 1.65, 17: 2.2, 18: 3.04, 19: 4.08, 20: 5.07, 21: 5.68, 22: 6.11, 23: 6.55},
        7:  {0: 6.27, 1: 6.51, 2: 6.69, 3: 6.76, 4: 6.4, 5: 5.3, 6: 4.35, 7: 3.38, 8: 2.67, 9: 2.15, 10: 1.57, 11: 1.14, 12: 0.95, 13: 0.88, 14: 1.02, 15: 1.32, 16: 1.72, 17: 2.29, 18: 3.06, 19: 3.98, 20: 4.78, 21: 5.3, 22: 5.65, 23: 5.95},
        8:  {0: 6.32, 1: 6.52, 2: 6.75, 3: 6.94, 4: 6.98, 5: 6.29, 6: 4.95, 7: 3.81, 8: 2.94, 9: 2.09, 10: 1.48, 11: 1.05, 12: 0.83, 13: 0.85, 14: 0.95, 15: 1.28, 16: 1.78, 17: 2.55, 18: 3.59, 19: 4.55, 20: 5.04, 21: 5.53, 22: 5.92, 23: 6.25},
        9:  {0: 6.18, 1: 6.36, 2: 6.56, 3: 6.69, 4: 6.79, 5: 6.68, 6: 5.79, 7: 4.57, 8: 3.52, 9: 2.53, 10: 1.86, 11: 1.31, 12: 0.94, 13: 0.79, 14: 0.9, 15: 1.25, 16: 1.99, 17: 3.06, 18: 4.04, 19: 4.68, 20: 5.11, 21: 5.46, 22: 5.66, 23: 5.98},
        10:  {0: 4.27, 1: 4.33, 2: 4.44, 3: 4.55, 4: 4.65, 5: 4.54, 6: 4.37, 7: 3.66, 8: 2.73, 9: 1.96, 10: 1.4, 11: 0.93, 12: 0.77, 13: 0.68, 14: 0.9, 15: 1.28, 16: 2.05, 17: 2.68, 18: 3.08, 19: 3.36, 20: 3.6, 21: 3.85, 22: 4.06, 23: 4.16},
        11:  {0: 3.13, 1: 3.27, 2: 3.35, 3: 3.24, 4: 3.33, 5: 3.36, 6: 3.34, 7: 3.16, 8: 2.67, 9: 1.89, 10: 1.34, 11: 0.99, 12: 0.79, 13: 0.83, 14: 1.18, 15: 1.78, 16: 2.27, 17: 2.51, 18: 2.64, 19: 2.84, 20: 2.88, 21: 3.09, 22: 3.26, 23: 3.34},
        12:  {0: 2.52, 1: 2.59, 2: 2.6, 3: 2.6, 4: 2.65, 5: 2.61, 6: 2.62, 7: 2.65, 8: 2.52, 9: 2.0, 10: 1.55, 11: 1.28, 12: 1.08, 13: 1.07, 14: 1.28, 15: 1.6, 16: 1.82, 17: 1.93, 18: 1.98, 19: 2.03, 20: 2.07, 21: 2.19, 22: 2.3, 23: 2.35},
    },
    "beijing": {
        1:  {0: 9.4, 1: 6.22, 2: 4.35, 3: 3.01, 4: 1.96, 5: 1.06, 6: 0.5, 7: 0.31, 8: 0.92, 9: 2.83, 10: 4.58, 11: 5.55, 12: 6.37, 13: 7.15, 14: 7.77, 15: 8.26, 16: 8.69, 17: 8.98, 18: 9.44, 19: 9.67, 20: 9.94, 21: 10.23, 22: 10.36, 23: 10.44},
        2:  {0: 9.65, 1: 6.66, 2: 4.94, 3: 3.44, 4: 2.27, 5: 1.3, 6: 0.7, 7: 0.39, 8: 0.58, 9: 1.74, 10: 3.84, 11: 5.61, 12: 6.77, 13: 7.7, 14: 8.46, 15: 9.06, 16: 9.77, 17: 10.41, 18: 10.92, 19: 11.3, 20: 11.61, 21: 12.05, 22: 12.21, 23: 12.24},
        3:  {0: 8.27, 1: 6.32, 2: 4.79, 3: 3.46, 4: 2.39, 5: 1.47, 6: 0.9, 7: 0.64, 8: 0.8, 9: 1.51, 10: 3.01, 11: 4.58, 12: 5.73, 13: 6.73, 14: 7.64, 15: 8.43, 16: 9.15, 17: 9.66, 18: 10.45, 19: 10.84, 20: 11.53, 21: 12.08, 22: 12.34, 23: 11.02},
        4:  {0: 7.51, 1: 6.01, 2: 4.6, 3: 3.43, 4: 2.24, 5: 1.52, 6: 0.99, 7: 0.77, 8: 0.96, 9: 1.57, 10: 2.7, 11: 4.47, 12: 5.78, 13: 6.63, 14: 7.36, 15: 8.36, 16: 9.45, 17: 10.29, 18: 11.19, 19: 11.91, 20: 12.57, 21: 13.1, 22: 12.48, 23: 9.49},
        5:  {0: 7.17, 1: 5.75, 2: 4.48, 3: 3.29, 4: 2.22, 5: 1.42, 6: 0.98, 7: 1.09, 8: 1.17, 9: 1.64, 10: 2.7, 11: 4.38, 12: 5.97, 13: 7.08, 14: 8.06, 15: 8.91, 16: 9.93, 17: 10.76, 18: 11.49, 19: 12.27, 20: 12.83, 21: 13.13, 22: 11.38, 23: 8.78},
        6:  {0: 7.17, 1: 5.89, 2: 4.68, 3: 3.47, 4: 2.44, 5: 1.58, 6: 1.15, 7: 0.85, 8: 0.94, 9: 1.42, 10: 2.35, 11: 3.91, 12: 5.52, 13: 6.6, 14: 7.65, 15: 8.75, 16: 9.51, 17: 10.36, 18: 11.06, 19: 11.71, 20: 12.16, 21: 12.16, 22: 10.36, 23: 8.58},
        7:  {0: 5.7, 1: 4.6, 2: 3.54, 3: 2.66, 4: 1.89, 5: 1.27, 6: 1.07, 7: 0.84, 8: 0.9, 9: 1.45, 10: 2.4, 11: 3.62, 12: 4.79, 13: 5.49, 14: 5.94, 15: 6.46, 16: 6.87, 17: 7.36, 18: 7.82, 19: 8.18, 20: 8.55, 21: 8.69, 22: 7.88, 23: 6.77},
        8:  {0: 5.48, 1: 4.22, 2: 3.16, 3: 2.32, 4: 1.69, 5: 1.15, 6: 0.84, 7: 0.65, 8: 1.04, 9: 1.64, 10: 2.97, 11: 4.39, 12: 5.17, 13: 5.91, 14: 6.5, 15: 6.99, 16: 7.33, 17: 7.66, 18: 7.98, 19: 8.31, 20: 8.51, 21: 8.68, 22: 8.36, 23: 6.88},
        9:  {0: 6.49, 1: 4.91, 2: 3.65, 3: 2.54, 4: 1.7, 5: 1.0, 6: 0.6, 7: 0.53, 8: 0.89, 9: 1.97, 10: 4.17, 11: 5.91, 12: 6.93, 13: 7.66, 14: 8.27, 15: 8.62, 16: 8.93, 17: 9.26, 18: 9.59, 19: 9.95, 20: 10.17, 21: 10.45, 22: 10.42, 23: 8.64},
        10:  {0: 7.11, 1: 5.13, 2: 3.76, 3: 2.63, 4: 1.59, 5: 0.97, 6: 0.52, 7: 0.57, 8: 1.15, 9: 3.34, 10: 5.92, 11: 7.17, 12: 7.94, 13: 8.5, 14: 9.09, 15: 9.49, 16: 9.96, 17: 10.36, 18: 10.65, 19: 10.83, 20: 11.05, 21: 11.27, 22: 11.32, 23: 10.19},
        11:  {0: 7.64, 1: 5.25, 2: 3.71, 3: 2.47, 4: 1.45, 5: 0.79, 6: 0.41, 7: 0.51, 8: 1.43, 9: 3.6, 10: 5.13, 11: 6.25, 12: 7.18, 13: 7.79, 14: 8.31, 15: 8.74, 16: 9.18, 17: 9.47, 18: 9.73, 19: 10.06, 20: 10.4, 21: 10.57, 22: 10.65, 23: 10.25},
        12:  {0: 8.89, 1: 5.75, 2: 3.96, 3: 2.53, 4: 1.5, 5: 0.81, 6: 0.39, 7: 0.47, 8: 1.32, 9: 3.31, 10: 4.95, 11: 5.96, 12: 7.14, 13: 7.73, 14: 8.2, 15: 8.67, 16: 9.32, 17: 9.69, 18: 9.99, 19: 10.22, 20: 10.4, 21: 10.58, 22: 10.52, 23: 10.44},
    },
    "shanghai": {
        1:  {0: 4.88, 1: 3.29, 2: 2.08, 3: 1.27, 4: 0.77, 5: 0.55, 6: 0.61, 7: 0.86, 8: 1.7, 9: 2.85, 10: 3.68, 11: 4.15, 12: 4.47, 13: 4.71, 14: 4.95, 15: 5.26, 16: 5.57, 17: 5.79, 18: 6.05, 19: 6.22, 20: 6.29, 21: 6.36, 22: 6.55, 23: 6.3},
        2:  {0: 3.76, 1: 2.69, 2: 1.94, 3: 1.3, 4: 0.87, 5: 0.71, 6: 0.71, 7: 1.03, 8: 1.59, 9: 2.36, 10: 3.19, 11: 3.58, 12: 3.85, 13: 4.11, 14: 4.27, 15: 4.42, 16: 4.61, 17: 4.74, 18: 4.92, 19: 5.11, 20: 5.18, 21: 5.26, 22: 5.3, 23: 4.84},
        3:  {0: 4.42, 1: 3.15, 2: 2.23, 3: 1.53, 4: 1.03, 5: 0.79, 6: 0.8, 7: 1.16, 8: 1.87, 9: 2.89, 10: 4.09, 11: 4.85, 12: 5.28, 13: 5.53, 14: 5.69, 15: 5.9, 16: 6.25, 17: 6.41, 18: 6.55, 19: 6.76, 20: 6.8, 21: 6.83, 22: 6.78, 23: 5.87},
        4:  {0: 4.2, 1: 3.0, 2: 2.1, 3: 1.38, 4: 0.95, 5: 0.73, 6: 0.85, 7: 1.33, 8: 2.02, 9: 3.02, 10: 4.18, 11: 4.94, 12: 5.41, 13: 5.7, 14: 5.92, 15: 6.18, 16: 6.33, 17: 6.5, 18: 6.75, 19: 6.99, 20: 7.08, 21: 7.16, 22: 6.73, 23: 5.35},
        5:  {0: 3.68, 1: 2.59, 2: 1.78, 3: 1.26, 4: 1.02, 5: 0.87, 6: 0.97, 7: 1.38, 8: 1.88, 9: 2.87, 10: 3.83, 11: 4.77, 12: 5.27, 13: 5.6, 14: 5.78, 15: 6.12, 16: 6.31, 17: 6.48, 18: 6.74, 19: 6.93, 20: 7.02, 21: 6.87, 22: 6.14, 23: 4.83},
        6:  {0: 3.24, 1: 2.46, 2: 1.87, 3: 1.34, 4: 0.98, 5: 0.91, 6: 0.91, 7: 1.16, 8: 1.58, 9: 2.17, 10: 3.02, 11: 3.82, 12: 4.21, 13: 4.5, 14: 4.66, 15: 4.86, 16: 5.0, 17: 5.15, 18: 5.35, 19: 5.4, 20: 5.44, 21: 5.39, 22: 4.8, 23: 3.89},
        7:  {0: 3.38, 1: 2.64, 2: 1.84, 3: 1.41, 4: 1.18, 5: 1.05, 6: 1.01, 7: 1.19, 8: 1.77, 9: 2.54, 10: 3.32, 11: 4.13, 12: 4.56, 13: 4.84, 14: 4.99, 15: 5.27, 16: 5.41, 17: 5.57, 18: 5.73, 19: 5.84, 20: 5.85, 21: 5.89, 22: 5.27, 23: 4.29},
        8:  {0: 3.27, 1: 2.27, 2: 1.53, 3: 1.13, 4: 0.69, 5: 0.63, 6: 0.94, 7: 1.27, 8: 1.97, 9: 2.84, 10: 3.83, 11: 4.6, 12: 4.92, 13: 5.14, 14: 5.41, 15: 5.53, 16: 5.73, 17: 5.81, 18: 6.03, 19: 6.2, 20: 6.28, 21: 6.34, 22: 5.72, 23: 4.45},
        9:  {0: 2.74, 1: 1.95, 2: 1.27, 3: 1.02, 4: 0.91, 5: 1.07, 6: 1.48, 7: 1.72, 8: 2.17, 9: 2.77, 10: 3.44, 11: 3.79, 12: 3.96, 13: 4.13, 14: 4.27, 15: 4.48, 16: 4.63, 17: 4.79, 18: 4.93, 19: 4.99, 20: 5.08, 21: 5.04, 22: 4.83, 23: 3.9},
        10:  {0: 2.82, 1: 1.89, 2: 1.22, 3: 0.82, 4: 0.64, 5: 0.68, 6: 0.97, 7: 1.37, 8: 2.07, 9: 2.82, 10: 3.34, 11: 3.64, 12: 3.91, 13: 4.08, 14: 4.16, 15: 4.38, 16: 4.59, 17: 4.75, 18: 4.94, 19: 5.2, 20: 5.24, 21: 5.19, 22: 5.15, 23: 4.15},
        11:  {0: 3.73, 1: 2.48, 2: 1.53, 3: 0.95, 4: 0.62, 5: 0.56, 6: 0.8, 7: 1.26, 8: 2.08, 9: 3.12, 10: 3.8, 11: 4.17, 12: 4.47, 13: 4.76, 14: 5.01, 15: 5.22, 16: 5.49, 17: 5.76, 18: 6.02, 19: 6.21, 20: 6.31, 21: 6.4, 22: 6.53, 23: 5.77},
        12:  {0: 4.38, 1: 2.84, 2: 1.79, 3: 1.08, 4: 0.68, 5: 0.5, 6: 0.65, 7: 1.14, 8: 1.97, 9: 2.97, 10: 3.56, 11: 3.94, 12: 4.31, 13: 4.55, 14: 4.83, 15: 5.11, 16: 5.37, 17: 5.64, 18: 5.94, 19: 6.23, 20: 6.35, 21: 6.34, 22: 6.39, 23: 5.97},
    },
    "singapore": {
        1:  {0: 4.09, 1: 3.09, 2: 2.24, 3: 1.69, 4: 1.2, 5: 0.8, 6: 0.9, 7: 0.99, 8: 1.34, 9: 1.78, 10: 2.37, 11: 3.07, 12: 3.54, 13: 3.7, 14: 3.84, 15: 3.98, 16: 4.14, 17: 4.26, 18: 4.38, 19: 4.49, 20: 4.6, 21: 4.62, 22: 4.67, 23: 4.63},
        2:  {0: 5.11, 1: 3.95, 2: 2.84, 3: 1.85, 4: 1.12, 5: 0.85, 6: 0.82, 7: 0.94, 8: 1.26, 9: 1.94, 10: 2.77, 11: 3.72, 12: 4.33, 13: 4.69, 14: 4.87, 15: 4.98, 16: 5.1, 17: 5.25, 18: 5.36, 19: 5.49, 20: 5.63, 21: 5.73, 22: 5.74, 23: 5.74},
        3:  {0: 4.97, 1: 3.81, 2: 2.84, 3: 1.89, 4: 1.28, 5: 1.14, 6: 1.19, 7: 1.45, 8: 1.68, 9: 2.25, 10: 3.1, 11: 4.03, 12: 4.52, 13: 4.68, 14: 4.92, 15: 5.07, 16: 5.17, 17: 5.28, 18: 5.49, 19: 5.6, 20: 5.75, 21: 5.82, 22: 5.87, 23: 5.8},
        4:  {0: 4.29, 1: 3.17, 2: 2.34, 3: 1.83, 4: 1.35, 5: 1.2, 6: 1.28, 7: 1.48, 8: 1.89, 9: 2.33, 10: 2.96, 11: 3.74, 12: 4.11, 13: 4.32, 14: 4.45, 15: 4.53, 16: 4.57, 17: 4.76, 18: 4.94, 19: 5.18, 20: 5.36, 21: 5.43, 22: 5.49, 23: 5.55},
        5:  {0: 3.66, 1: 2.8, 2: 2.12, 3: 1.64, 4: 1.28, 5: 1.08, 6: 1.21, 7: 1.34, 8: 1.51, 9: 1.93, 10: 2.5, 11: 3.18, 12: 3.49, 13: 3.65, 14: 3.79, 15: 3.95, 16: 3.95, 17: 4.12, 18: 4.27, 19: 4.49, 20: 4.67, 21: 4.78, 22: 4.81, 23: 4.78},
        6:  {0: 3.6, 1: 2.77, 2: 2.3, 3: 1.77, 4: 1.36, 5: 1.23, 6: 1.13, 7: 1.26, 8: 1.31, 9: 1.67, 10: 2.18, 11: 2.89, 12: 3.18, 13: 3.35, 14: 3.47, 15: 3.64, 16: 3.71, 17: 3.85, 18: 4.04, 19: 4.23, 20: 4.52, 21: 4.59, 22: 4.65, 23: 4.55},
        7:  {0: 3.49, 1: 2.68, 2: 2.12, 3: 1.6, 4: 1.2, 5: 1.05, 6: 0.88, 7: 0.94, 8: 1.09, 9: 1.32, 10: 1.96, 11: 2.71, 12: 3.11, 13: 3.27, 14: 3.42, 15: 3.45, 16: 3.49, 17: 3.63, 18: 3.8, 19: 3.96, 20: 4.08, 21: 4.18, 22: 4.23, 23: 4.2},
        8:  {0: 3.51, 1: 2.65, 2: 2.18, 3: 1.63, 4: 1.24, 5: 1.15, 6: 1.32, 7: 1.41, 8: 1.56, 9: 1.7, 10: 2.21, 11: 2.86, 12: 3.17, 13: 3.28, 14: 3.3, 15: 3.37, 16: 3.44, 17: 3.7, 18: 3.89, 19: 4.03, 20: 4.14, 21: 4.21, 22: 4.3, 23: 4.37},
        9:  {0: 3.48, 1: 2.78, 2: 2.18, 3: 1.68, 4: 1.29, 5: 1.12, 6: 1.12, 7: 1.27, 8: 1.52, 9: 1.71, 10: 2.25, 11: 2.92, 12: 3.33, 13: 3.35, 14: 3.45, 15: 3.57, 16: 3.68, 17: 3.79, 18: 3.93, 19: 4.17, 20: 4.31, 21: 4.38, 22: 4.45, 23: 4.39},
        10:  {0: 3.82, 1: 2.95, 2: 2.27, 3: 1.79, 4: 1.41, 5: 1.27, 6: 1.18, 7: 1.34, 8: 1.52, 9: 2.0, 10: 2.64, 11: 3.41, 12: 3.65, 13: 3.94, 14: 4.06, 15: 4.24, 16: 4.29, 17: 4.5, 18: 4.7, 19: 4.86, 20: 5.07, 21: 5.26, 22: 5.33, 23: 5.01},
        11:  {0: 4.07, 1: 3.06, 2: 2.19, 3: 1.56, 4: 1.31, 5: 1.33, 6: 1.51, 7: 1.96, 8: 2.28, 9: 2.81, 10: 3.27, 11: 3.99, 12: 4.3, 13: 4.44, 14: 4.61, 15: 4.71, 16: 4.85, 17: 4.93, 18: 5.06, 19: 5.16, 20: 5.27, 21: 5.43, 22: 5.37, 23: 5.23},
        12:  {0: 4.06, 1: 3.1, 2: 2.28, 3: 1.57, 4: 1.1, 5: 0.96, 6: 1.23, 7: 1.52, 8: 1.89, 9: 2.39, 10: 2.93, 11: 3.51, 12: 3.85, 13: 4.05, 14: 4.18, 15: 4.23, 16: 4.34, 17: 4.47, 18: 4.58, 19: 4.73, 20: 4.83, 21: 4.9, 22: 4.93, 23: 4.96},
    },
    "jakarta": {
        1:  {0: 5.46, 1: 4.29, 2: 3.03, 3: 2.07, 4: 1.39, 5: 1.06, 6: 1.09, 7: 1.45, 8: 1.9, 9: 2.38, 10: 2.9, 11: 3.67, 12: 4.24, 13: 4.64, 14: 4.9, 15: 5.16, 16: 5.48, 17: 5.6, 18: 5.08, 19: 4.83, 20: 5.57, 21: 6.28, 22: 6.54, 23: 6.49},
        2:  {0: 5.41, 1: 4.18, 2: 2.96, 3: 2.16, 4: 1.65, 5: 1.3, 6: 1.09, 7: 1.27, 8: 1.43, 9: 1.94, 10: 2.62, 11: 3.33, 12: 3.96, 13: 4.29, 14: 4.55, 15: 4.8, 16: 4.98, 17: 5.26, 18: 5.63, 19: 5.98, 20: 6.14, 21: 5.97, 22: 6.26, 23: 6.13},
        3:  {0: 6.25, 1: 4.51, 2: 3.09, 3: 1.99, 4: 1.34, 5: 1.1, 6: 1.26, 7: 1.43, 8: 1.89, 9: 2.49, 10: 3.34, 11: 4.11, 12: 4.56, 13: 4.93, 14: 5.13, 15: 5.61, 16: 5.88, 17: 6.17, 18: 6.88, 19: 6.82, 20: 6.75, 21: 6.74, 22: 6.98, 23: 7.07},
        4:  {0: 6.63, 1: 4.8, 2: 3.29, 3: 2.04, 4: 1.27, 5: 0.78, 6: 1.03, 7: 1.37, 8: 1.91, 9: 2.63, 10: 3.61, 11: 4.62, 12: 5.13, 13: 5.6, 14: 5.95, 15: 6.29, 16: 6.62, 17: 6.67, 21: 7.31, 22: 7.54, 23: 7.64},
        5:  {0: 6.56, 1: 4.82, 2: 3.22, 3: 2.07, 4: 1.14, 5: 0.75, 6: 0.69, 7: 1.11, 8: 1.44, 9: 2.24, 10: 3.2, 11: 4.18, 12: 4.74, 13: 5.16, 14: 5.48, 15: 5.82, 16: 6.14, 17: 6.45, 21: 7.37, 22: 7.46, 23: 7.44},
        6:  {0: 6.67, 1: 4.8, 2: 3.18, 3: 2.12, 4: 1.18, 5: 0.74, 6: 0.73, 7: 0.97, 8: 1.66, 9: 2.06, 10: 3.13, 11: 4.31, 12: 4.84, 13: 5.18, 14: 5.47, 15: 5.75, 16: 5.99, 17: 6.34, 21: 7.29, 22: 7.4, 23: 7.59},
        7:  {0: 7.46, 1: 5.41, 2: 3.68, 3: 2.36, 4: 1.38, 5: 0.86, 6: 0.61, 7: 0.77, 8: 1.24, 9: 1.86, 10: 3.01, 11: 3.94, 12: 4.63, 13: 5.1, 14: 5.63, 15: 6.13, 16: 6.42, 17: 6.71, 20: 7.38, 21: 8.15, 22: 8.33, 23: 8.43},
        8:  {0: 7.41, 1: 5.42, 2: 3.6, 3: 2.37, 4: 1.41, 5: 0.88, 6: 0.68, 7: 0.76, 8: 1.01, 9: 1.89, 10: 3.12, 11: 4.32, 12: 5.14, 13: 5.62, 14: 5.95, 15: 6.35, 16: 6.82, 17: 7.32, 20: 8.17, 21: 8.59, 22: 8.76, 23: 8.74},
        9:  {0: 7.3, 1: 5.02, 2: 3.4, 3: 2.1, 4: 1.33, 5: 0.94, 6: 0.88, 7: 1.06, 8: 1.54, 9: 2.43, 10: 3.75, 11: 4.94, 12: 5.58, 13: 5.96, 14: 6.37, 15: 6.79, 16: 7.42, 17: 7.88, 21: 8.9, 22: 9.19, 23: 8.96},
        10:  {0: 6.94, 1: 4.97, 2: 3.32, 3: 2.06, 4: 1.13, 5: 0.78, 6: 0.82, 7: 1.22, 8: 1.91, 9: 2.96, 10: 4.19, 11: 5.27, 12: 6.14, 13: 6.54, 14: 7.0, 15: 7.24, 16: 7.71, 17: 8.07, 20: 7.79, 21: 9.0, 22: 9.18, 23: 8.8},
        11:  {0: 6.12, 1: 4.38, 2: 2.9, 3: 1.86, 4: 1.19, 5: 0.9, 6: 1.1, 7: 1.56, 8: 2.51, 9: 3.55, 10: 4.6, 11: 5.59, 12: 6.08, 13: 6.45, 14: 6.69, 15: 6.92, 16: 7.13, 17: 7.31, 18: 7.18, 19: 7.33, 20: 7.39, 21: 7.95, 22: 8.09, 23: 7.68},
        12:  {0: 5.84, 1: 4.34, 2: 3.03, 3: 2.24, 4: 1.48, 5: 1.08, 6: 1.29, 7: 1.65, 8: 2.3, 9: 3.05, 10: 3.85, 11: 4.62, 12: 5.29, 13: 5.52, 14: 5.82, 15: 6.02, 16: 6.18, 17: 6.34, 18: 7.03, 19: 7.12, 20: 6.98, 21: 7.16, 22: 7.31, 23: 7.13},
    },
    "toronto": {
        1:  {0: 2.37, 1: 2.44, 2: 2.8, 3: 2.78, 4: 2.93, 5: 2.86, 6: 3.08, 7: 3.48, 8: 3.53, 9: 3.69, 10: 3.63, 11: 3.72, 12: 3.75, 13: 3.7, 14: 3.27, 15: 2.85, 16: 2.39, 17: 1.9, 18: 1.54, 19: 1.28, 20: 1.43, 21: 1.59, 22: 1.98, 23: 2.24},
        2:  {0: 3.24, 1: 3.64, 2: 3.73, 3: 4.09, 4: 4.22, 5: 4.5, 6: 4.85, 7: 5.16, 8: 5.3, 9: 5.51, 10: 5.26, 11: 5.46, 12: 5.59, 13: 5.42, 14: 4.76, 15: 3.75, 16: 3.02, 17: 2.63, 18: 1.97, 19: 1.68, 20: 1.6, 21: 1.88, 22: 2.85, 23: 2.87},
        3:  {0: 4.5, 1: 4.59, 2: 5.17, 3: 5.26, 4: 5.6, 5: 5.74, 6: 6.07, 7: 6.18, 8: 6.28, 9: 6.34, 10: 6.63, 11: 6.67, 12: 6.6, 13: 5.58, 14: 4.73, 15: 3.8, 16: 3.17, 17: 2.35, 18: 2.01, 19: 1.94, 20: 1.82, 21: 2.18, 22: 2.6, 23: 3.33},
        4:  {0: 4.36, 1: 5.01, 2: 5.48, 3: 6.04, 4: 6.33, 5: 6.67, 6: 6.84, 7: 7.05, 8: 7.66, 9: 7.61, 10: 7.72, 11: 7.47, 12: 6.64, 13: 5.74, 14: 4.61, 15: 3.91, 16: 3.33, 17: 2.78, 18: 2.18, 19: 1.78, 20: 1.99, 21: 1.97, 22: 2.55, 23: 3.16},
        5:  {0: 4.01, 1: 5.05, 2: 5.85, 3: 6.39, 4: 7.07, 5: 7.64, 6: 8.09, 7: 8.24, 8: 8.87, 9: 9.05, 10: 9.14, 11: 8.32, 12: 7.19, 13: 5.81, 14: 4.57, 15: 3.74, 16: 2.99, 17: 2.69, 18: 2.05, 19: 1.57, 20: 1.51, 21: 1.5, 22: 1.87, 23: 2.64},
        6:  {0: 3.69, 1: 4.5, 2: 5.39, 3: 5.89, 4: 6.72, 5: 7.19, 6: 7.73, 7: 8.09, 8: 8.4, 9: 8.76, 10: 8.7, 11: 7.94, 12: 6.82, 13: 5.64, 14: 4.72, 15: 3.54, 16: 2.84, 17: 2.13, 18: 1.88, 19: 1.95, 20: 1.94, 21: 1.91, 22: 2.44, 23: 3.06},
        7:  {0: 3.28, 1: 4.4, 2: 5.07, 3: 5.79, 4: 6.31, 5: 6.86, 6: 7.34, 7: 7.68, 8: 8.33, 9: 8.21, 10: 8.49, 11: 7.8, 12: 6.64, 13: 5.55, 14: 4.47, 15: 3.56, 16: 2.74, 17: 2.18, 18: 1.97, 19: 1.5, 20: 1.65, 21: 1.67, 22: 2.21, 23: 2.48},
        8:  {0: 3.23, 1: 3.99, 2: 4.65, 3: 5.42, 4: 5.93, 5: 6.45, 6: 6.96, 7: 7.35, 8: 7.75, 9: 7.89, 10: 8.07, 11: 7.79, 12: 6.64, 13: 5.25, 14: 4.03, 15: 3.02, 16: 2.22, 17: 1.77, 18: 1.54, 19: 1.44, 20: 1.52, 21: 1.62, 22: 1.68, 23: 2.45},
        9:  {0: 3.86, 1: 4.36, 2: 5.01, 3: 5.54, 4: 6.05, 5: 6.54, 6: 6.84, 7: 7.27, 8: 7.68, 9: 7.73, 10: 7.99, 11: 7.73, 12: 7.25, 13: 5.86, 14: 4.48, 15: 3.14, 16: 2.2, 17: 1.64, 18: 1.31, 19: 1.24, 20: 1.16, 21: 1.46, 22: 2.14, 23: 3.24},
        10:  {0: 3.39, 1: 3.94, 2: 4.53, 3: 4.83, 4: 5.28, 5: 5.75, 6: 6.27, 7: 6.4, 8: 6.57, 9: 6.7, 10: 6.91, 11: 6.73, 12: 6.56, 13: 5.44, 14: 4.15, 15: 3.18, 16: 2.05, 17: 1.59, 18: 1.35, 19: 1.14, 20: 1.2, 21: 1.47, 22: 2.27, 23: 3.09},
        11:  {0: 3.11, 1: 3.48, 2: 3.78, 3: 4.02, 4: 4.12, 5: 4.36, 6: 4.79, 7: 4.84, 8: 5.12, 9: 5.18, 10: 5.52, 11: 5.34, 12: 5.31, 13: 4.87, 14: 4.08, 15: 3.05, 16: 2.2, 17: 1.83, 18: 1.72, 19: 1.49, 20: 1.74, 21: 2.11, 22: 2.96, 23: 3.28},
        12:  {0: 2.64, 1: 2.82, 2: 2.93, 3: 3.07, 4: 3.18, 5: 3.18, 6: 3.47, 7: 3.68, 8: 3.73, 9: 3.82, 10: 3.63, 11: 3.67, 12: 3.6, 13: 3.49, 14: 3.22, 15: 2.69, 16: 2.12, 17: 1.84, 18: 1.77, 19: 1.68, 20: 2.0, 21: 2.1, 22: 2.68, 23: 2.98},
    },
    "mexico-city": {
        1:  {0: 4.23, 1: 5.4, 2: 6.36, 3: 7.21, 4: 7.81, 5: 8.55, 6: 9.56, 7: 10.28, 8: 11.26, 9: 12.1, 10: 12.81, 11: 13.31, 12: 13.88, 13: 13.41, 14: 11.3, 15: 8.73, 16: 6.04, 17: 3.92, 18: 2.27, 19: 1.06, 20: 0.48, 21: 0.83, 22: 1.47, 23: 2.77},
        2:  {0: 4.04, 1: 5.56, 2: 6.78, 3: 7.57, 4: 8.5, 5: 9.32, 6: 10.28, 7: 11.4, 8: 12.7, 9: 13.48, 10: 14.14, 11: 14.86, 12: 15.5, 13: 14.53, 14: 12.14, 15: 9.25, 16: 6.65, 17: 4.17, 18: 2.44, 19: 1.16, 20: 0.85, 21: 0.65, 22: 1.21, 23: 2.44},
        3:  {0: 4.3, 1: 6.14, 2: 7.18, 3: 8.05, 4: 8.92, 5: 9.52, 6: 10.46, 7: 11.56, 8: 12.82, 9: 13.56, 10: 14.19, 11: 14.88, 12: 15.58, 13: 13.6, 14: 10.95, 15: 8.2, 16: 5.84, 17: 3.58, 18: 1.95, 19: 1.1, 20: 0.54, 21: 1.03, 22: 1.81, 23: 2.98},
        4:  {0: 4.79, 1: 6.55, 2: 7.7, 3: 8.47, 4: 8.95, 5: 9.55, 6: 10.23, 7: 11.1, 8: 12.1, 9: 12.91, 10: 13.57, 11: 14.13, 12: 14.37, 13: 12.16, 14: 9.6, 15: 7.25, 16: 4.95, 17: 3.17, 18: 1.84, 19: 0.94, 20: 0.73, 21: 1.18, 22: 2.27, 23: 3.44},
        5:  {0: 5.64, 1: 6.88, 2: 7.83, 3: 8.17, 4: 8.57, 5: 9.35, 6: 9.77, 7: 10.38, 8: 11.2, 9: 11.83, 10: 12.18, 11: 12.84, 12: 12.51, 13: 10.37, 14: 8.33, 15: 6.01, 16: 4.32, 17: 2.84, 18: 1.65, 19: 0.94, 20: 1.13, 21: 1.82, 22: 3.05, 23: 4.27},
        6:  {0: 4.86, 1: 5.79, 2: 6.58, 3: 7.12, 4: 7.35, 5: 7.75, 6: 8.04, 7: 8.49, 8: 9.19, 9: 9.48, 10: 9.8, 11: 10.34, 12: 9.64, 13: 8.48, 14: 6.99, 15: 5.23, 16: 4.03, 17: 2.75, 18: 1.75, 19: 1.31, 20: 1.53, 21: 1.81, 22: 3.12, 23: 4.07},
        7:  {0: 5.27, 1: 6.27, 2: 6.81, 3: 7.21, 4: 7.36, 5: 7.71, 6: 8.1, 7: 8.38, 8: 8.82, 9: 9.11, 10: 9.49, 11: 9.69, 12: 9.5, 13: 8.38, 14: 6.76, 15: 5.16, 16: 3.95, 17: 2.72, 18: 1.64, 19: 1.11, 20: 1.29, 21: 2.34, 22: 3.67, 23: 4.72},
        8:  {0: 5.65, 1: 6.31, 2: 6.71, 3: 7.02, 4: 7.48, 5: 7.82, 6: 8.07, 7: 8.59, 8: 8.77, 9: 9.12, 10: 9.38, 11: 9.58, 12: 9.65, 13: 8.46, 14: 7.06, 15: 5.48, 16: 4.07, 17: 2.8, 18: 1.73, 19: 1.4, 20: 1.32, 21: 2.46, 22: 3.46, 23: 4.74},
        9:  {0: 5.36, 1: 6.06, 2: 6.63, 3: 6.94, 4: 7.14, 5: 7.62, 6: 7.83, 7: 8.18, 8: 8.44, 9: 8.71, 10: 9.01, 11: 9.24, 12: 9.16, 13: 8.35, 14: 6.87, 15: 5.2, 16: 3.97, 17: 2.63, 18: 1.6, 19: 0.95, 20: 1.09, 21: 1.58, 22: 2.97, 23: 4.51},
        10:  {0: 4.49, 1: 5.61, 2: 6.36, 3: 6.76, 4: 7.89, 5: 8.07, 6: 8.28, 7: 9.0, 8: 9.68, 9: 9.82, 10: 10.33, 11: 10.77, 12: 10.87, 13: 9.69, 14: 8.13, 15: 6.2, 16: 4.6, 17: 3.07, 18: 1.98, 19: 1.22, 20: 0.95, 21: 1.06, 22: 1.81, 23: 3.23},
        11:  {0: 4.23, 1: 5.68, 2: 6.64, 3: 7.4, 4: 7.93, 5: 9.01, 6: 10.05, 7: 10.88, 8: 11.91, 9: 12.71, 10: 13.14, 11: 13.77, 12: 13.92, 13: 12.83, 14: 10.93, 15: 8.15, 16: 5.69, 17: 3.53, 18: 2.11, 19: 0.86, 20: 0.44, 21: 0.45, 22: 1.33, 23: 2.88},
        12:  {0: 3.82, 1: 5.02, 2: 6.06, 3: 6.71, 4: 7.55, 5: 8.28, 6: 9.48, 7: 10.47, 8: 11.6, 9: 12.26, 10: 12.63, 11: 13.24, 12: 13.7, 13: 12.6, 14: 11.0, 15: 8.7, 16: 6.04, 17: 3.8, 18: 2.03, 19: 0.92, 20: 0.49, 21: 0.78, 22: 1.48, 23: 2.74},
    },
    "buenos-aires": {
        1:  {0: 6.08, 1: 7.23, 2: 7.87, 3: 8.58, 4: 8.97, 5: 9.44, 6: 9.91, 7: 10.34, 8: 10.71, 9: 11.07, 10: 10.21, 11: 8.37, 12: 6.81, 13: 5.25, 14: 3.82, 15: 2.73, 16: 2.08, 17: 1.41, 18: 1.09, 19: 1.06, 20: 1.37, 21: 2.07, 22: 2.85, 23: 4.61},
        2:  {0: 5.81, 1: 6.58, 2: 7.28, 3: 7.85, 4: 8.76, 5: 9.35, 6: 9.6, 7: 10.05, 8: 10.3, 9: 10.55, 10: 10.41, 11: 8.78, 12: 7.04, 13: 5.4, 14: 4.14, 15: 3.08, 16: 2.44, 17: 1.63, 18: 1.23, 19: 1.24, 20: 1.58, 21: 1.81, 22: 2.78, 23: 4.49},
        3:  {0: 5.41, 1: 6.05, 2: 6.41, 3: 7.01, 4: 7.85, 5: 8.11, 6: 8.31, 7: 8.83, 8: 9.02, 9: 9.2, 10: 9.46, 11: 8.29, 12: 6.32, 13: 4.76, 14: 3.58, 15: 2.54, 16: 1.83, 17: 1.27, 18: 1.01, 19: 1.01, 20: 1.27, 21: 2.07, 22: 3.28, 23: 4.86},
        4:  {0: 5.76, 1: 6.38, 2: 6.79, 3: 7.19, 4: 7.81, 5: 8.13, 6: 8.64, 7: 8.9, 8: 8.94, 9: 9.07, 10: 9.5, 11: 9.01, 12: 6.66, 13: 4.66, 14: 3.09, 15: 1.86, 16: 1.16, 17: 0.76, 18: 0.57, 19: 0.84, 20: 1.26, 21: 2.29, 22: 3.83, 23: 4.9},
        5:  {0: 5.49, 1: 5.9, 2: 6.4, 3: 6.72, 4: 7.17, 5: 7.59, 6: 8.13, 7: 8.19, 8: 8.49, 9: 8.59, 10: 8.98, 11: 8.51, 12: 7.06, 13: 5.02, 14: 3.12, 15: 1.87, 16: 1.12, 17: 0.75, 18: 0.6, 19: 0.65, 20: 1.22, 21: 2.56, 22: 4.19, 23: 5.1},
        6:  {0: 5.47, 1: 5.89, 2: 6.17, 3: 6.42, 4: 6.84, 5: 7.45, 6: 7.65, 7: 7.99, 8: 8.11, 9: 8.38, 10: 8.59, 11: 8.36, 12: 7.7, 13: 5.6, 14: 3.76, 15: 2.45, 16: 1.33, 17: 0.7, 18: 0.41, 19: 0.62, 20: 1.37, 21: 2.87, 22: 4.21, 23: 4.94},
        7:  {0: 5.34, 1: 5.78, 2: 6.26, 3: 6.54, 4: 6.89, 5: 7.58, 6: 7.85, 7: 8.2, 8: 8.5, 9: 8.56, 10: 9.04, 11: 9.16, 12: 8.05, 13: 5.85, 14: 3.9, 15: 2.4, 16: 1.48, 17: 0.8, 18: 0.62, 19: 0.53, 20: 1.16, 21: 2.53, 22: 3.75, 23: 4.82},
        8:  {0: 6.28, 1: 6.53, 2: 7.31, 3: 7.67, 4: 8.09, 5: 8.25, 6: 8.84, 7: 9.09, 8: 9.28, 9: 9.75, 10: 10.32, 11: 10.12, 12: 7.72, 13: 5.44, 14: 3.86, 15: 2.65, 16: 1.71, 17: 1.29, 18: 0.98, 19: 1.12, 20: 1.4, 21: 2.55, 22: 4.26, 23: 5.4},
        9:  {0: 5.88, 1: 6.45, 2: 6.97, 3: 7.43, 4: 8.02, 5: 8.39, 6: 9.06, 7: 9.22, 8: 9.51, 9: 9.7, 10: 9.74, 11: 8.18, 12: 5.89, 13: 4.33, 14: 2.88, 15: 1.87, 16: 1.29, 17: 1.04, 18: 0.89, 19: 0.91, 20: 1.2, 21: 2.29, 22: 3.64, 23: 5.14},
        10:  {0: 6.57, 1: 7.17, 2: 7.9, 3: 8.55, 4: 9.05, 5: 9.53, 6: 10.01, 7: 10.37, 8: 10.9, 9: 10.94, 10: 10.5, 11: 8.01, 12: 6.24, 13: 4.66, 14: 3.47, 15: 2.38, 16: 1.57, 17: 1.06, 18: 0.89, 19: 0.96, 20: 1.49, 21: 2.29, 22: 3.88, 23: 5.58},
        11:  {0: 6.87, 1: 7.86, 2: 8.35, 3: 8.97, 4: 9.46, 5: 9.87, 6: 10.39, 7: 10.68, 8: 11.27, 9: 11.29, 10: 9.47, 11: 7.31, 12: 5.72, 13: 4.48, 14: 3.51, 15: 2.47, 16: 1.7, 17: 1.55, 18: 1.51, 19: 1.18, 20: 1.55, 21: 2.32, 22: 3.6, 23: 5.53},
        12:  {0: 6.46, 1: 7.17, 2: 8.32, 3: 8.79, 4: 9.42, 5: 10.09, 6: 10.87, 7: 11.36, 8: 11.82, 9: 11.79, 10: 10.28, 11: 8.19, 12: 6.44, 13: 5.01, 14: 3.65, 15: 2.79, 16: 2.02, 17: 1.37, 18: 0.84, 19: 0.66, 20: 0.96, 21: 1.59, 22: 2.94, 23: 4.84},
    },
    "sao-paulo": {
        1:  {0: 7.0, 1: 7.19, 2: 7.33, 3: 7.57, 4: 7.95, 5: 8.13, 6: 8.4, 7: 8.47, 8: 8.47, 9: 8.51, 10: 7.48, 11: 6.26, 12: 4.89, 13: 3.36, 14: 2.34, 15: 1.55, 16: 1.28, 17: 1.37, 18: 2.72, 19: 3.49, 20: 4.25, 21: 4.95, 22: 5.84, 23: 6.61},
        2:  {0: 7.21, 1: 7.54, 2: 7.92, 3: 8.21, 4: 8.4, 5: 8.72, 6: 8.95, 7: 9.21, 8: 9.33, 9: 9.39, 10: 8.68, 11: 7.34, 12: 5.68, 13: 3.97, 14: 2.62, 15: 1.73, 16: 1.11, 17: 1.32, 18: 2.37, 19: 3.4, 20: 4.18, 21: 5.37, 22: 6.12, 23: 6.74},
        3:  {0: 7.16, 1: 7.55, 2: 7.85, 3: 8.21, 4: 8.58, 5: 8.76, 6: 9.08, 7: 9.23, 8: 9.38, 9: 9.53, 10: 8.97, 11: 7.84, 12: 6.02, 13: 4.4, 14: 2.82, 15: 1.88, 16: 1.17, 17: 1.25, 18: 1.64, 19: 2.72, 20: 4.17, 21: 5.38, 22: 6.44, 23: 6.9},
        4:  {0: 6.16, 1: 6.42, 2: 6.84, 3: 7.19, 4: 7.44, 5: 7.82, 6: 8.03, 7: 8.22, 8: 8.26, 9: 8.36, 10: 8.06, 11: 7.0, 12: 5.69, 13: 4.23, 14: 2.84, 15: 1.77, 16: 1.12, 17: 0.53, 18: 0.62, 19: 1.41, 20: 2.77, 21: 4.18, 22: 5.21, 23: 5.88},
        5:  {0: 6.76, 1: 7.39, 2: 7.66, 3: 7.94, 4: 8.2, 5: 8.54, 6: 8.74, 7: 8.93, 8: 9.14, 9: 9.06, 10: 9.0, 11: 7.99, 12: 6.6, 13: 4.77, 14: 3.1, 15: 1.87, 16: 1.06, 17: 0.61, 18: 0.54, 19: 1.19, 20: 2.34, 21: 4.47, 22: 5.52, 23: 6.3},
        6:  {0: 7.06, 1: 7.6, 2: 7.74, 3: 8.19, 4: 8.23, 5: 8.65, 6: 8.75, 7: 9.07, 8: 9.38, 9: 9.36, 10: 9.53, 11: 8.26, 12: 7.05, 13: 5.11, 14: 3.25, 15: 2.2, 16: 1.34, 17: 0.72, 18: 0.59, 19: 1.12, 20: 2.17, 21: 4.46, 22: 5.72, 23: 6.44},
        7:  {0: 7.97, 1: 8.55, 2: 8.97, 3: 9.18, 4: 9.58, 5: 9.89, 6: 10.21, 7: 10.25, 8: 10.53, 9: 10.81, 10: 10.56, 11: 9.52, 12: 7.87, 13: 6.08, 14: 4.13, 15: 2.52, 16: 1.35, 17: 0.66, 18: 0.41, 19: 0.81, 20: 2.24, 21: 4.73, 22: 6.16, 23: 7.22},
        8:  {0: 8.26, 1: 8.83, 2: 9.05, 3: 9.55, 4: 10.07, 5: 10.19, 6: 10.51, 7: 10.9, 8: 10.99, 9: 10.99, 10: 10.8, 11: 9.7, 12: 8.05, 13: 5.94, 14: 3.97, 15: 2.57, 16: 1.5, 17: 0.92, 18: 0.94, 19: 1.59, 20: 2.8, 21: 5.0, 22: 6.38, 23: 7.52},
        9:  {0: 8.83, 1: 9.14, 2: 9.55, 3: 9.87, 4: 10.38, 5: 10.71, 6: 10.99, 7: 11.19, 8: 11.2, 9: 11.25, 10: 10.67, 11: 9.37, 12: 7.65, 13: 5.61, 14: 3.94, 15: 2.42, 16: 1.41, 17: 0.88, 18: 1.22, 19: 2.28, 20: 3.65, 21: 5.62, 22: 7.25, 23: 8.01},
        10:  {0: 7.02, 1: 7.35, 2: 7.66, 3: 7.92, 4: 8.05, 5: 8.4, 6: 8.61, 7: 8.66, 8: 8.73, 9: 8.66, 10: 7.96, 11: 6.98, 12: 5.57, 13: 4.08, 14: 2.87, 15: 1.89, 16: 1.21, 17: 1.09, 18: 1.6, 19: 2.83, 20: 4.26, 21: 5.23, 22: 6.2, 23: 6.88},
        11:  {0: 7.49, 1: 7.88, 2: 8.25, 3: 8.31, 4: 8.75, 5: 8.94, 6: 9.09, 7: 9.38, 8: 9.47, 9: 9.08, 10: 8.14, 11: 6.96, 12: 5.22, 13: 3.92, 14: 2.61, 15: 1.52, 16: 1.01, 17: 1.02, 18: 1.51, 19: 2.5, 20: 3.57, 21: 4.71, 22: 6.17, 23: 6.93},
        12:  {0: 7.26, 1: 7.62, 2: 7.82, 3: 8.2, 4: 8.6, 5: 8.81, 6: 9.2, 7: 9.43, 8: 9.42, 9: 9.25, 10: 7.99, 11: 6.68, 12: 5.09, 13: 3.69, 14: 2.52, 15: 1.6, 16: 1.32, 17: 1.45, 18: 2.14, 19: 2.91, 20: 4.3, 21: 5.13, 22: 6.19, 23: 6.63},
    },
    "austin": {
        1:  {0: 5.51, 1: 6.82, 2: 7.59, 3: 8.03, 4: 8.64, 5: 9.09, 6: 9.33, 7: 9.63, 8: 9.86, 9: 10.17, 10: 10.55, 11: 10.89, 12: 11.07, 13: 10.75, 14: 8.36, 15: 6.48, 16: 4.78, 17: 3.3, 18: 2.13, 19: 1.32, 20: 0.67, 21: 0.71, 22: 1.32, 23: 3.42},
        2:  {0: 5.29, 1: 6.94, 2: 7.84, 3: 8.32, 4: 8.93, 5: 9.49, 6: 10.33, 7: 10.85, 8: 11.03, 9: 11.43, 10: 11.41, 11: 11.49, 12: 11.63, 13: 10.91, 14: 8.58, 15: 6.55, 16: 4.72, 17: 3.31, 18: 2.22, 19: 1.51, 20: 0.94, 21: 0.75, 22: 1.13, 23: 2.49},
        3:  {0: 4.33, 1: 6.1, 2: 7.16, 3: 8.25, 4: 9.11, 5: 9.64, 6: 10.28, 7: 10.86, 8: 11.09, 9: 11.41, 10: 11.84, 11: 11.99, 12: 12.1, 13: 10.33, 14: 8.22, 15: 6.23, 16: 4.61, 17: 3.1, 18: 2.01, 19: 1.15, 20: 0.68, 21: 0.51, 22: 0.89, 23: 1.99},
        4:  {0: 3.93, 1: 5.53, 2: 6.53, 3: 7.3, 4: 8.04, 5: 8.61, 6: 9.21, 7: 9.54, 8: 9.73, 9: 9.9, 10: 9.97, 11: 10.01, 12: 9.47, 13: 8.1, 14: 6.53, 15: 4.94, 16: 3.71, 17: 2.65, 18: 1.79, 19: 1.08, 20: 0.69, 21: 0.7, 22: 1.32, 23: 2.16},
        5:  {0: 3.53, 1: 5.25, 2: 6.53, 3: 7.43, 4: 8.28, 5: 8.84, 6: 9.35, 7: 9.63, 8: 9.93, 9: 10.09, 10: 10.24, 11: 10.28, 12: 9.15, 13: 7.72, 14: 6.27, 15: 4.75, 16: 3.58, 17: 2.44, 18: 1.61, 19: 0.84, 20: 0.57, 21: 0.64, 22: 1.09, 23: 1.96},
        6:  {0: 3.35, 1: 5.2, 2: 6.64, 3: 7.53, 4: 8.44, 5: 9.13, 6: 9.69, 7: 10.16, 8: 10.55, 9: 10.78, 10: 11.06, 11: 11.01, 12: 9.59, 13: 7.91, 14: 6.4, 15: 4.97, 16: 3.62, 17: 2.48, 18: 1.6, 19: 1.03, 20: 0.72, 21: 0.85, 22: 1.28, 23: 2.02},
        7:  {0: 3.27, 1: 5.42, 2: 6.67, 3: 7.57, 4: 8.4, 5: 9.15, 6: 9.74, 7: 10.15, 8: 10.5, 9: 10.92, 10: 11.1, 11: 11.21, 12: 9.93, 13: 8.21, 14: 6.46, 15: 4.95, 16: 3.52, 17: 2.44, 18: 1.52, 19: 0.93, 20: 0.9, 21: 1.07, 22: 1.26, 23: 1.94},
        8:  {0: 4.18, 1: 6.08, 2: 7.22, 3: 8.25, 4: 9.22, 5: 9.99, 6: 10.61, 7: 11.24, 8: 11.73, 9: 12.19, 10: 12.35, 11: 12.49, 12: 11.27, 13: 9.12, 14: 7.05, 15: 5.22, 16: 3.81, 17: 2.68, 18: 1.8, 19: 1.19, 20: 0.98, 21: 0.99, 22: 1.4, 23: 2.38},
        9:  {0: 4.92, 1: 6.6, 2: 7.94, 3: 9.06, 4: 10.25, 5: 11.15, 6: 11.73, 7: 12.51, 8: 12.84, 9: 13.21, 10: 13.54, 11: 13.76, 12: 12.87, 13: 9.88, 14: 7.45, 15: 5.4, 16: 3.8, 17: 2.51, 18: 1.61, 19: 0.79, 20: 0.6, 21: 0.69, 22: 0.99, 23: 2.31},
        10:  {0: 6.22, 1: 7.71, 2: 8.72, 3: 9.51, 4: 10.24, 5: 11.31, 6: 11.74, 7: 12.25, 8: 12.7, 9: 12.95, 10: 13.27, 11: 13.44, 12: 13.22, 13: 10.25, 14: 7.63, 15: 5.45, 16: 3.77, 17: 2.39, 18: 1.44, 19: 0.85, 20: 0.44, 21: 0.55, 22: 1.35, 23: 3.49},
        11:  {0: 6.17, 1: 7.14, 2: 7.9, 3: 8.33, 4: 8.62, 5: 9.17, 6: 9.53, 7: 9.89, 8: 10.2, 9: 10.4, 10: 10.58, 11: 10.66, 12: 10.67, 13: 9.28, 14: 7.35, 15: 5.56, 16: 3.83, 17: 2.5, 18: 1.7, 19: 0.97, 20: 0.55, 21: 0.7, 22: 1.68, 23: 4.3},
        12:  {0: 6.02, 1: 7.0, 2: 7.66, 3: 8.21, 4: 8.56, 5: 8.96, 6: 9.22, 7: 9.46, 8: 9.63, 9: 9.86, 10: 9.97, 11: 10.2, 12: 10.32, 13: 10.0, 14: 7.88, 15: 6.14, 16: 4.62, 17: 3.13, 18: 2.0, 19: 1.19, 20: 0.81, 21: 0.87, 22: 1.7, 23: 4.32},
    },
    "guangzhou": {
        1:  {0: 7.7, 1: 6.32, 2: 4.93, 3: 3.5, 4: 2.33, 5: 1.41, 6: 0.84, 7: 0.58, 8: 0.67, 9: 1.36, 10: 2.44, 11: 3.31, 12: 4.08, 13: 4.72, 14: 5.2, 15: 5.66, 16: 6.05, 17: 6.44, 18: 6.82, 19: 7.14, 20: 7.4, 21: 7.65, 22: 7.95, 23: 8.15},
        2:  {0: 6.55, 1: 5.47, 2: 4.24, 3: 3.11, 4: 2.11, 5: 1.35, 6: 0.83, 7: 0.6, 8: 0.79, 9: 1.23, 10: 2.16, 11: 2.91, 12: 3.43, 13: 3.93, 14: 4.48, 15: 4.88, 16: 5.31, 17: 5.62, 18: 5.93, 19: 6.22, 20: 6.5, 21: 6.65, 22: 6.79, 23: 6.96},
        3:  {0: 6.19, 1: 5.1, 2: 3.85, 3: 2.76, 4: 1.88, 5: 1.29, 6: 0.87, 7: 0.8, 8: 0.84, 9: 1.2, 10: 1.94, 11: 2.88, 12: 3.43, 13: 3.95, 14: 4.45, 15: 4.93, 16: 5.3, 17: 5.63, 18: 5.95, 19: 6.23, 20: 6.48, 21: 6.77, 22: 6.93, 23: 6.89},
        4:  {0: 5.28, 1: 4.23, 2: 3.2, 3: 2.35, 4: 1.71, 5: 1.35, 6: 1.0, 7: 1.07, 8: 1.1, 9: 1.55, 10: 2.13, 11: 2.93, 12: 3.45, 13: 3.9, 14: 4.33, 15: 4.65, 16: 5.16, 17: 5.41, 18: 5.63, 19: 5.93, 20: 6.09, 21: 6.26, 22: 6.45, 23: 6.18},
        5:  {0: 4.88, 1: 3.94, 2: 3.0, 3: 2.15, 4: 1.56, 5: 1.18, 6: 1.2, 7: 1.12, 8: 1.34, 9: 1.76, 10: 2.31, 11: 2.96, 12: 3.48, 13: 3.95, 14: 4.23, 15: 4.48, 16: 4.85, 17: 5.11, 18: 5.27, 19: 5.48, 20: 5.62, 21: 5.79, 22: 5.94, 23: 5.5},
        6:  {0: 4.7, 1: 3.78, 2: 2.91, 3: 2.12, 4: 1.65, 5: 1.53, 6: 1.35, 7: 1.31, 8: 1.71, 9: 2.13, 10: 2.89, 11: 3.61, 12: 4.23, 13: 4.53, 14: 4.89, 15: 5.08, 16: 5.35, 17: 5.51, 18: 5.7, 19: 5.87, 20: 6.06, 21: 6.19, 22: 6.27, 23: 5.62},
        7:  {0: 5.63, 1: 4.46, 2: 3.49, 3: 2.69, 4: 1.88, 5: 1.52, 6: 1.27, 7: 1.21, 8: 1.65, 9: 1.99, 10: 2.71, 11: 3.73, 12: 4.34, 13: 4.86, 14: 5.28, 15: 5.66, 16: 5.98, 17: 6.34, 18: 6.69, 19: 6.92, 20: 7.12, 21: 7.29, 22: 7.44, 23: 6.74},
        8:  {0: 5.65, 1: 4.35, 2: 3.42, 3: 2.5, 4: 1.77, 5: 1.51, 6: 1.4, 7: 1.58, 8: 1.94, 9: 2.59, 10: 3.57, 11: 4.37, 12: 4.86, 13: 5.26, 14: 5.61, 15: 5.83, 16: 6.05, 17: 6.25, 18: 6.48, 19: 6.69, 20: 6.9, 21: 7.05, 22: 7.17, 23: 6.76},
        9:  {0: 6.17, 1: 4.69, 2: 3.43, 3: 2.44, 4: 1.61, 5: 1.11, 6: 0.78, 7: 0.95, 8: 1.31, 9: 2.19, 10: 3.03, 11: 3.92, 12: 4.43, 13: 5.01, 14: 5.37, 15: 5.77, 16: 6.15, 17: 6.45, 18: 6.76, 19: 6.94, 20: 7.18, 21: 7.39, 22: 7.65, 23: 7.29},
        10:  {0: 5.96, 1: 4.56, 2: 3.36, 3: 2.3, 4: 1.41, 5: 0.91, 6: 0.67, 7: 0.7, 8: 1.01, 9: 1.78, 10: 2.74, 11: 3.5, 12: 3.98, 13: 4.57, 14: 4.93, 15: 5.3, 16: 5.46, 17: 5.77, 18: 6.1, 19: 6.4, 20: 6.61, 21: 6.9, 22: 7.21, 23: 7.03},
        11:  {0: 6.18, 1: 4.84, 2: 3.52, 3: 2.45, 4: 1.55, 5: 0.97, 6: 0.63, 7: 0.5, 8: 0.83, 9: 1.67, 10: 2.74, 11: 3.35, 12: 3.92, 13: 4.38, 14: 4.87, 15: 5.25, 16: 5.4, 17: 5.65, 18: 6.02, 19: 6.32, 20: 6.54, 21: 6.75, 22: 6.96, 23: 6.97},
        12:  {0: 7.28, 1: 5.91, 2: 4.37, 3: 2.97, 4: 1.97, 5: 1.14, 6: 0.53, 7: 0.46, 8: 0.71, 9: 1.48, 10: 2.63, 11: 3.46, 12: 4.1, 13: 4.73, 14: 5.26, 15: 5.71, 16: 6.15, 17: 6.52, 18: 6.83, 19: 7.15, 20: 7.3, 21: 7.55, 22: 7.72, 23: 7.97},
    },
    "helsinki": {
        1:  {0: 2.83, 1: 2.87, 2: 2.88, 3: 2.88, 4: 2.99, 5: 2.99, 6: 2.92, 7: 2.7, 8: 2.43, 9: 2.1, 10: 1.79, 11: 1.51, 12: 1.59, 13: 1.81, 14: 2.02, 15: 2.17, 16: 2.17, 17: 2.29, 18: 2.33, 19: 2.37, 20: 2.5, 21: 2.52, 22: 2.65, 23: 2.77},
        2:  {0: 3.46, 1: 3.52, 2: 3.52, 3: 3.67, 4: 3.61, 5: 3.61, 6: 3.4, 7: 2.98, 8: 2.3, 9: 1.69, 10: 1.17, 11: 0.82, 12: 0.72, 13: 0.84, 14: 1.17, 15: 1.67, 16: 2.03, 17: 2.28, 18: 2.42, 19: 2.56, 20: 2.62, 21: 2.76, 22: 3.04, 23: 3.3},
        3:  {0: 5.66, 1: 5.91, 2: 5.95, 3: 6.01, 4: 6.03, 5: 5.45, 6: 4.52, 7: 3.44, 8: 2.49, 9: 1.68, 10: 1.1, 11: 0.72, 12: 0.63, 13: 0.68, 14: 0.97, 15: 1.54, 16: 2.53, 17: 3.35, 18: 3.92, 19: 4.36, 20: 4.57, 21: 4.92, 22: 5.15, 23: 5.49},
        4:  {0: 7.9, 1: 8.13, 2: 8.26, 3: 8.07, 4: 6.95, 5: 5.69, 6: 4.45, 7: 3.38, 8: 2.34, 9: 1.75, 10: 1.21, 11: 0.91, 12: 0.63, 13: 0.69, 14: 0.95, 15: 1.49, 16: 2.29, 17: 3.66, 18: 4.98, 19: 5.83, 20: 6.51, 21: 6.89, 22: 7.31, 23: 7.46},
        5:  {0: 10.1, 1: 10.27, 2: 9.82, 3: 8.32, 4: 6.59, 5: 5.12, 6: 3.88, 7: 2.93, 8: 2.13, 9: 1.48, 10: 1.23, 11: 0.99, 12: 0.84, 13: 0.78, 14: 1.09, 15: 1.47, 16: 2.25, 17: 3.27, 18: 4.75, 19: 6.18, 20: 7.42, 21: 8.11, 22: 9.05, 23: 9.56},
        6:  {0: 10.51, 1: 10.45, 2: 9.25, 3: 7.47, 4: 6.01, 5: 4.71, 6: 3.59, 7: 2.72, 8: 2.03, 9: 1.66, 10: 1.38, 11: 1.09, 12: 0.91, 13: 1.08, 14: 1.13, 15: 1.57, 16: 2.14, 17: 2.87, 18: 4.29, 19: 6.06, 20: 7.55, 21: 8.47, 22: 9.42, 23: 10.07},
        7:  {0: 8.94, 1: 9.15, 2: 8.5, 3: 6.99, 4: 5.6, 5: 4.38, 6: 3.32, 7: 2.5, 8: 2.02, 9: 1.59, 10: 1.23, 11: 0.81, 12: 0.93, 13: 1.01, 14: 1.22, 15: 1.59, 16: 2.27, 17: 3.09, 18: 4.45, 19: 5.88, 20: 6.79, 21: 7.6, 22: 8.14, 23: 8.56},
        8:  {0: 7.63, 1: 7.86, 2: 7.94, 3: 7.27, 4: 5.94, 5: 4.65, 6: 3.72, 7: 2.81, 8: 2.04, 9: 1.5, 10: 1.23, 11: 0.92, 12: 0.84, 13: 0.92, 14: 1.2, 15: 1.66, 16: 2.39, 17: 3.49, 18: 4.66, 19: 5.55, 20: 6.13, 21: 6.58, 22: 6.93, 23: 7.25},
        9:  {0: 6.21, 1: 6.37, 2: 6.35, 3: 6.46, 4: 5.91, 5: 4.79, 6: 3.63, 7: 2.7, 8: 1.87, 9: 1.31, 10: 0.8, 11: 0.57, 12: 0.47, 13: 0.71, 14: 1.11, 15: 1.91, 16: 3.11, 17: 4.27, 18: 5.01, 19: 5.31, 20: 5.63, 21: 5.92, 22: 5.94, 23: 6.1},
        10:  {0: 3.97, 1: 4.06, 2: 4.09, 3: 4.16, 4: 4.25, 5: 4.1, 6: 3.27, 7: 2.4, 8: 1.82, 9: 1.27, 10: 0.88, 11: 0.67, 12: 0.7, 13: 0.96, 14: 1.46, 15: 2.11, 16: 2.64, 17: 2.96, 18: 3.15, 19: 3.41, 20: 3.48, 21: 3.56, 22: 3.66, 23: 3.86},
        11:  {0: 2.25, 1: 2.35, 2: 2.44, 3: 2.36, 4: 2.43, 5: 2.37, 6: 2.34, 7: 1.99, 8: 1.55, 9: 1.12, 10: 0.99, 11: 0.87, 12: 0.95, 13: 1.25, 14: 1.5, 15: 1.67, 16: 1.82, 17: 1.97, 18: 2.04, 19: 2.15, 20: 2.25, 21: 2.31, 22: 2.13, 23: 2.24},
        12:  {0: 2.45, 1: 2.38, 2: 2.36, 3: 2.35, 4: 2.34, 5: 2.38, 6: 2.41, 7: 2.43, 8: 2.16, 9: 1.9, 10: 1.67, 11: 1.54, 12: 1.66, 13: 1.83, 14: 2.01, 15: 2.12, 16: 2.27, 17: 2.24, 18: 2.35, 19: 2.35, 20: 2.46, 21: 2.46, 22: 2.3, 23: 2.41},
    },
    "milan": {
        1:  {0: 7.25, 1: 7.48, 2: 7.66, 3: 7.68, 4: 7.82, 5: 7.7, 6: 7.64, 7: 7.24, 8: 5.1, 9: 3.17, 10: 1.97, 11: 1.05, 12: 0.54, 13: 0.25, 14: 0.5, 15: 1.52, 16: 2.9, 17: 4.43, 18: 5.41, 19: 5.89, 20: 6.32, 21: 6.55, 22: 6.76, 23: 7.12},
        2:  {0: 8.84, 1: 9.0, 2: 9.28, 3: 9.38, 4: 9.45, 5: 9.47, 6: 9.21, 7: 7.68, 8: 4.91, 9: 3.33, 10: 2.01, 11: 1.31, 12: 0.67, 13: 0.3, 14: 0.34, 15: 0.89, 16: 2.04, 17: 3.6, 18: 5.11, 19: 6.35, 20: 7.06, 21: 7.57, 22: 8.01, 23: 8.45},
        3:  {0: 8.48, 1: 8.81, 2: 9.08, 3: 9.34, 4: 9.48, 5: 9.45, 6: 7.9, 7: 5.45, 8: 3.88, 9: 2.73, 10: 1.85, 11: 1.2, 12: 0.68, 13: 0.44, 14: 0.3, 15: 0.55, 16: 1.29, 17: 2.49, 18: 4.18, 19: 5.6, 20: 6.62, 21: 7.18, 22: 7.71, 23: 8.23},
        4:  {0: 9.77, 1: 10.22, 2: 10.66, 3: 10.95, 4: 11.12, 5: 9.91, 6: 7.09, 7: 5.28, 8: 3.95, 9: 2.88, 10: 2.11, 11: 1.46, 12: 0.94, 13: 0.61, 14: 0.58, 15: 0.8, 16: 1.43, 17: 2.77, 18: 4.45, 19: 5.96, 20: 6.99, 21: 7.63, 22: 8.47, 23: 9.19},
        5:  {0: 8.65, 1: 8.82, 2: 9.13, 3: 9.39, 4: 9.12, 5: 7.44, 6: 5.89, 7: 4.6, 8: 3.58, 9: 2.77, 10: 2.09, 11: 1.45, 12: 0.97, 13: 0.75, 14: 0.57, 15: 0.79, 16: 1.38, 17: 2.23, 18: 3.62, 19: 5.23, 20: 6.3, 21: 7.01, 22: 7.64, 23: 8.18},
        6:  {0: 9.36, 1: 9.76, 2: 10.19, 3: 10.39, 4: 9.55, 5: 7.55, 6: 5.93, 7: 4.57, 8: 3.54, 9: 2.59, 10: 1.91, 11: 1.27, 12: 0.91, 13: 0.81, 14: 0.91, 15: 1.0, 16: 1.52, 17: 2.3, 18: 3.52, 19: 5.27, 20: 6.73, 21: 7.43, 22: 8.08, 23: 8.82},
        7:  {0: 9.42, 1: 9.79, 2: 9.99, 3: 10.52, 4: 10.05, 5: 8.27, 6: 6.63, 7: 5.22, 8: 4.15, 9: 2.95, 10: 2.09, 11: 1.42, 12: 0.94, 13: 0.75, 14: 0.59, 15: 0.82, 16: 1.4, 17: 2.2, 18: 3.49, 19: 5.32, 20: 6.92, 21: 7.8, 22: 8.36, 23: 8.91},
        8:  {0: 9.47, 1: 9.79, 2: 10.18, 3: 10.55, 4: 10.57, 5: 9.08, 6: 7.05, 7: 5.26, 8: 3.95, 9: 2.78, 10: 1.96, 11: 1.28, 12: 0.72, 13: 0.48, 14: 0.54, 15: 0.85, 16: 1.41, 17: 2.62, 18: 4.3, 19: 6.15, 20: 7.33, 21: 7.99, 22: 8.57, 23: 9.03},
        9:  {0: 8.13, 1: 8.39, 2: 8.62, 3: 8.81, 4: 8.91, 5: 8.63, 6: 6.82, 7: 5.22, 8: 3.82, 9: 2.66, 10: 1.9, 11: 1.28, 12: 0.8, 13: 0.46, 14: 0.42, 15: 0.79, 16: 1.72, 17: 3.34, 18: 5.03, 19: 6.24, 20: 6.78, 21: 7.19, 22: 7.67, 23: 7.88},
        10:  {0: 7.12, 1: 7.48, 2: 7.66, 3: 7.83, 4: 7.8, 5: 7.93, 6: 7.05, 7: 5.12, 8: 3.57, 9: 2.41, 10: 1.54, 11: 0.85, 12: 0.46, 13: 0.29, 14: 0.34, 15: 1.03, 16: 2.6, 17: 4.6, 18: 5.57, 19: 6.11, 20: 6.3, 21: 6.64, 22: 6.87, 23: 7.05},
        11:  {0: 7.36, 1: 7.65, 2: 7.81, 3: 7.95, 4: 8.09, 5: 8.09, 6: 7.87, 7: 6.56, 8: 4.06, 9: 2.45, 10: 1.49, 11: 0.75, 12: 0.35, 13: 0.31, 14: 0.74, 15: 1.91, 16: 3.81, 17: 5.35, 18: 5.93, 19: 6.37, 20: 6.73, 21: 7.08, 22: 7.23, 23: 7.28},
        12:  {0: 7.38, 1: 7.35, 2: 7.48, 3: 7.66, 4: 7.68, 5: 7.56, 6: 7.56, 7: 7.23, 8: 5.13, 9: 3.03, 10: 1.85, 11: 1.01, 12: 0.48, 13: 0.33, 14: 0.88, 15: 2.09, 16: 3.75, 17: 5.04, 18: 5.83, 19: 6.39, 20: 6.74, 21: 6.88, 22: 6.93, 23: 7.1},
    },
    "moscow": {
        1:  {0: 2.47, 1: 2.56, 2: 2.63, 3: 2.66, 4: 2.72, 5: 2.79, 6: 2.85, 7: 2.75, 8: 2.43, 9: 1.98, 10: 1.58, 11: 1.35, 12: 1.35, 13: 1.44, 14: 1.74, 15: 1.86, 16: 1.93, 17: 1.99, 18: 2.08, 19: 2.12, 20: 2.15, 21: 2.17, 22: 2.31, 23: 2.44},
        2:  {0: 3.55, 1: 3.7, 2: 3.77, 3: 3.89, 4: 3.91, 5: 3.96, 6: 3.7, 7: 3.19, 8: 2.45, 9: 1.74, 10: 1.21, 11: 0.72, 12: 0.54, 13: 0.6, 14: 0.87, 15: 1.31, 16: 1.8, 17: 1.96, 18: 2.24, 19: 2.41, 20: 2.62, 21: 2.85, 22: 3.11, 23: 3.28},
        3:  {0: 6.06, 1: 6.39, 2: 6.63, 3: 6.82, 4: 6.91, 5: 6.28, 6: 5.0, 7: 3.78, 8: 2.73, 9: 1.97, 10: 1.29, 11: 0.78, 12: 0.56, 13: 0.53, 14: 0.68, 15: 1.33, 16: 2.17, 17: 2.79, 18: 3.45, 19: 3.86, 20: 4.32, 21: 4.98, 22: 5.39, 23: 5.75},
        4:  {0: 6.86, 1: 7.19, 2: 7.52, 3: 7.48, 4: 6.78, 5: 5.78, 6: 4.65, 7: 3.59, 8: 2.69, 9: 2.03, 10: 1.41, 11: 1.03, 12: 0.83, 13: 0.77, 14: 0.95, 15: 1.37, 16: 2.2, 17: 3.19, 18: 4.02, 19: 4.67, 20: 5.23, 21: 5.59, 22: 6.05, 23: 6.51},
        5:  {0: 8.78, 1: 9.25, 2: 9.34, 3: 8.45, 4: 7.0, 5: 5.45, 6: 4.1, 7: 3.1, 8: 2.34, 9: 1.79, 10: 1.32, 11: 1.11, 12: 0.83, 13: 0.91, 14: 0.99, 15: 1.27, 16: 1.88, 17: 2.96, 18: 4.32, 19: 5.32, 20: 6.14, 21: 7.03, 22: 7.65, 23: 8.19},
        6:  {0: 8.89, 1: 9.25, 2: 9.05, 3: 7.87, 4: 6.41, 5: 5.05, 6: 3.95, 7: 3.09, 8: 2.27, 9: 1.69, 10: 1.33, 11: 1.18, 12: 1.17, 13: 1.19, 14: 1.23, 15: 1.77, 16: 2.32, 17: 3.17, 18: 4.31, 19: 5.31, 20: 6.12, 21: 6.97, 22: 7.57, 23: 8.21},
        7:  {0: 8.59, 1: 8.94, 2: 8.98, 3: 8.13, 4: 6.89, 5: 5.37, 6: 4.17, 7: 3.18, 8: 2.46, 9: 1.82, 10: 1.43, 11: 0.99, 12: 0.95, 13: 1.1, 14: 1.1, 15: 1.57, 16: 2.39, 17: 3.43, 18: 4.64, 19: 5.71, 20: 6.51, 21: 7.1, 22: 7.67, 23: 8.12},
        8:  {0: 8.0, 1: 8.42, 2: 8.86, 3: 8.59, 4: 7.41, 5: 6.03, 6: 4.72, 7: 3.55, 8: 2.59, 9: 1.9, 10: 1.39, 11: 1.05, 12: 0.88, 13: 0.79, 14: 1.0, 15: 1.44, 16: 2.38, 17: 3.83, 18: 4.99, 19: 5.65, 20: 6.3, 21: 6.85, 22: 7.19, 23: 7.67},
        9:  {0: 7.08, 1: 7.34, 2: 7.61, 3: 7.8, 4: 7.43, 5: 6.21, 6: 4.74, 7: 3.41, 8: 2.43, 9: 1.64, 10: 1.11, 11: 0.66, 12: 0.47, 13: 0.63, 14: 1.09, 15: 1.99, 16: 3.21, 17: 4.09, 18: 4.91, 19: 5.29, 20: 5.81, 21: 5.91, 22: 6.22, 23: 6.67},
        10:  {0: 4.17, 1: 4.38, 2: 4.54, 3: 4.73, 4: 4.79, 5: 4.51, 6: 3.84, 7: 2.97, 8: 2.21, 9: 1.54, 10: 1.03, 11: 0.81, 12: 0.78, 13: 0.97, 14: 1.47, 15: 2.07, 16: 2.53, 17: 2.78, 18: 3.07, 19: 3.37, 20: 3.63, 21: 3.66, 22: 3.8, 23: 4.01},
        11:  {0: 2.14, 1: 2.22, 2: 2.27, 3: 2.28, 4: 2.31, 5: 2.27, 6: 2.14, 7: 1.99, 8: 1.64, 9: 1.35, 10: 1.12, 11: 0.92, 12: 0.99, 13: 1.19, 14: 1.44, 15: 1.63, 16: 1.72, 17: 1.82, 18: 1.88, 19: 1.93, 20: 2.09, 21: 1.87, 22: 1.99, 23: 2.11},
        12:  {0: 2.1, 1: 2.11, 2: 2.11, 3: 2.13, 4: 2.11, 5: 2.15, 6: 2.08, 7: 1.96, 8: 1.68, 9: 1.39, 10: 1.17, 11: 1.03, 12: 1.12, 13: 1.31, 14: 1.44, 15: 1.58, 16: 1.6, 17: 1.7, 18: 1.75, 19: 1.85, 20: 1.9, 21: 1.94, 22: 1.99, 23: 2.02},
    },
    "munich": {
        1:  {0: 4.72, 1: 4.74, 2: 4.85, 3: 4.87, 4: 4.9, 5: 4.7, 6: 4.66, 7: 4.29, 8: 3.34, 9: 2.35, 10: 1.57, 11: 0.98, 12: 0.57, 13: 0.52, 14: 0.95, 15: 1.83, 16: 2.57, 17: 3.06, 18: 3.26, 19: 3.68, 20: 4.05, 21: 4.14, 22: 4.37, 23: 4.58},
        2:  {0: 5.72, 1: 5.85, 2: 5.88, 3: 6.06, 4: 6.08, 5: 6.09, 6: 5.96, 7: 5.02, 8: 3.88, 9: 2.77, 10: 1.89, 11: 1.22, 12: 0.66, 13: 0.5, 14: 0.61, 15: 1.16, 16: 2.28, 17: 3.14, 18: 3.7, 19: 4.18, 20: 4.54, 21: 4.85, 22: 5.25, 23: 5.61},
        3:  {0: 9.65, 1: 10.06, 2: 10.35, 3: 10.59, 4: 10.61, 5: 10.29, 6: 8.61, 7: 6.66, 8: 4.89, 9: 3.52, 10: 2.33, 11: 1.55, 12: 0.97, 13: 0.65, 14: 0.71, 15: 1.23, 16: 2.34, 17: 4.12, 18: 5.52, 19: 6.63, 20: 7.36, 21: 8.03, 22: 8.59, 23: 9.27},
        4:  {0: 9.84, 1: 10.13, 2: 10.52, 3: 10.71, 4: 10.41, 5: 8.67, 6: 6.89, 7: 5.27, 8: 3.81, 9: 2.79, 10: 2.05, 11: 1.47, 12: 0.89, 13: 0.78, 14: 0.7, 15: 0.95, 16: 1.57, 17: 2.87, 18: 4.71, 19: 6.26, 20: 7.05, 21: 8.13, 22: 8.94, 23: 9.41},
        5:  {0: 10.14, 1: 10.42, 2: 10.82, 3: 10.9, 4: 9.54, 5: 7.64, 6: 6.1, 7: 4.62, 8: 3.48, 9: 2.58, 10: 1.94, 11: 1.39, 12: 0.99, 13: 0.75, 14: 0.67, 15: 1.06, 16: 1.55, 17: 2.53, 18: 4.28, 19: 6.14, 20: 7.18, 21: 8.14, 22: 8.81, 23: 9.58},
        6:  {0: 11.21, 1: 11.71, 2: 12.22, 3: 12.11, 4: 9.95, 5: 8.21, 6: 6.57, 7: 5.19, 8: 3.95, 9: 2.95, 10: 2.1, 11: 1.53, 12: 0.95, 13: 0.73, 14: 0.79, 15: 1.23, 16: 1.73, 17: 2.73, 18: 4.39, 19: 6.9, 20: 8.15, 21: 9.09, 22: 9.99, 23: 10.74},
        7:  {0: 10.44, 1: 10.79, 2: 11.18, 3: 11.21, 4: 9.79, 5: 8.09, 6: 6.51, 7: 5.08, 8: 3.96, 9: 3.05, 10: 2.23, 11: 1.7, 12: 1.35, 13: 1.12, 14: 0.95, 15: 1.19, 16: 1.64, 17: 2.71, 18: 4.37, 19: 6.57, 20: 7.7, 21: 8.57, 22: 9.36, 23: 9.94},
        8:  {0: 10.08, 1: 10.39, 2: 10.7, 3: 10.79, 4: 10.4, 5: 8.5, 6: 6.73, 7: 5.3, 8: 4.0, 9: 2.9, 10: 2.12, 11: 1.47, 12: 1.06, 13: 0.73, 14: 0.82, 15: 1.21, 16: 1.89, 17: 3.2, 18: 5.51, 19: 7.04, 20: 7.79, 21: 8.68, 22: 9.35, 23: 9.75},
        9:  {0: 9.43, 1: 9.79, 2: 10.03, 3: 10.17, 4: 10.01, 5: 9.07, 6: 7.07, 7: 5.4, 8: 3.89, 9: 2.67, 10: 1.73, 11: 1.15, 12: 0.71, 13: 0.61, 14: 0.71, 15: 1.27, 16: 2.33, 17: 4.47, 18: 5.93, 19: 6.93, 20: 7.65, 21: 8.31, 22: 8.97, 23: 9.05},
        10:  {0: 7.92, 1: 8.17, 2: 8.32, 3: 8.46, 4: 8.23, 5: 8.11, 6: 7.07, 7: 5.3, 8: 3.84, 9: 2.52, 10: 1.56, 11: 0.97, 12: 0.56, 13: 0.43, 14: 0.86, 15: 1.74, 16: 3.31, 17: 4.47, 18: 5.18, 19: 5.83, 20: 6.36, 21: 6.95, 22: 7.37, 23: 7.68},
        11:  {0: 4.91, 1: 5.08, 2: 5.15, 3: 5.2, 4: 5.17, 5: 5.12, 6: 4.98, 7: 4.08, 8: 3.14, 9: 2.24, 10: 1.45, 11: 0.91, 12: 0.57, 13: 0.55, 14: 1.03, 15: 2.18, 16: 2.92, 17: 3.39, 18: 3.71, 19: 4.11, 20: 4.43, 21: 4.63, 22: 4.85, 23: 4.77},
        12:  {0: 3.55, 1: 3.65, 2: 3.7, 3: 3.74, 4: 3.68, 5: 3.67, 6: 3.72, 7: 3.48, 8: 2.73, 9: 2.01, 10: 1.32, 11: 0.88, 12: 0.65, 13: 0.61, 14: 1.1, 15: 1.78, 16: 2.21, 17: 2.47, 18: 2.69, 19: 2.88, 20: 2.96, 21: 3.14, 22: 3.4, 23: 3.53},
    },
    "shenzhen": {
        1:  {0: 5.1, 1: 4.06, 2: 2.99, 3: 2.1, 4: 1.37, 5: 1.01, 6: 0.68, 7: 0.61, 8: 0.85, 9: 1.32, 10: 2.12, 11: 2.66, 12: 2.97, 13: 3.28, 14: 3.61, 15: 3.86, 16: 3.99, 17: 4.29, 18: 4.54, 19: 4.81, 20: 5.12, 21: 5.24, 22: 5.41, 23: 5.58},
        2:  {0: 4.47, 1: 3.72, 2: 2.77, 3: 2.02, 4: 1.5, 5: 0.98, 6: 0.74, 7: 0.7, 8: 0.91, 9: 1.29, 10: 1.97, 11: 2.61, 12: 2.85, 13: 3.04, 14: 3.35, 15: 3.57, 16: 3.82, 17: 3.99, 18: 4.18, 19: 4.43, 20: 4.62, 21: 4.74, 22: 4.89, 23: 4.94},
        3:  {0: 3.91, 1: 3.14, 2: 2.43, 3: 1.8, 4: 1.34, 5: 1.06, 6: 0.8, 7: 0.88, 8: 1.1, 9: 1.6, 10: 2.12, 11: 2.6, 12: 2.91, 13: 3.02, 14: 3.21, 15: 3.46, 16: 3.8, 17: 3.95, 18: 4.19, 19: 4.46, 20: 4.55, 21: 4.65, 22: 4.74, 23: 4.68},
        4:  {0: 3.09, 1: 2.41, 2: 1.79, 3: 1.31, 4: 1.05, 5: 0.79, 6: 0.71, 7: 0.65, 8: 0.95, 9: 1.41, 10: 1.88, 11: 2.32, 12: 2.63, 13: 2.71, 14: 2.91, 15: 3.07, 16: 3.33, 17: 3.49, 18: 3.62, 19: 3.83, 20: 3.9, 21: 4.01, 22: 4.05, 23: 3.75},
        5:  {0: 2.71, 1: 2.15, 2: 1.58, 3: 1.17, 4: 1.0, 5: 0.75, 6: 0.77, 7: 0.86, 8: 1.04, 9: 1.37, 10: 1.79, 11: 2.21, 12: 2.38, 13: 2.57, 14: 2.76, 15: 2.88, 16: 3.06, 17: 3.23, 18: 3.43, 19: 3.54, 20: 3.63, 21: 3.74, 22: 3.71, 23: 3.27},
        6:  {0: 2.27, 1: 1.79, 2: 1.42, 3: 1.12, 4: 0.93, 5: 0.89, 6: 0.91, 7: 0.98, 8: 1.21, 9: 1.35, 10: 1.71, 11: 2.01, 12: 2.23, 13: 2.31, 14: 2.43, 15: 2.57, 16: 2.71, 17: 2.85, 18: 2.96, 19: 3.03, 20: 3.19, 21: 3.23, 22: 3.31, 23: 2.81},
        7:  {0: 2.59, 1: 2.01, 2: 1.56, 3: 1.26, 4: 0.97, 5: 0.69, 6: 0.67, 7: 0.78, 8: 0.97, 9: 1.2, 10: 1.72, 11: 2.16, 12: 2.43, 13: 2.66, 14: 2.82, 15: 2.9, 16: 2.97, 17: 3.16, 18: 3.36, 19: 3.47, 20: 3.64, 21: 3.73, 22: 3.72, 23: 3.15},
        8:  {0: 2.73, 1: 2.04, 2: 1.61, 3: 1.23, 4: 1.12, 5: 0.98, 6: 1.06, 7: 1.21, 8: 1.32, 9: 1.57, 10: 2.01, 11: 2.51, 12: 2.75, 13: 2.75, 14: 2.88, 15: 3.04, 16: 3.06, 17: 3.21, 18: 3.25, 19: 3.39, 20: 3.54, 21: 3.61, 22: 3.75, 23: 3.39},
        9:  {0: 3.25, 1: 2.51, 2: 1.89, 3: 1.38, 4: 1.01, 5: 0.83, 6: 0.81, 7: 0.81, 8: 1.05, 9: 1.53, 10: 2.17, 11: 2.66, 12: 2.85, 13: 3.11, 14: 3.37, 15: 3.55, 16: 3.71, 17: 3.83, 18: 4.01, 19: 4.26, 20: 4.37, 21: 4.43, 22: 4.55, 23: 4.19},
        10:  {0: 4.05, 1: 3.13, 2: 2.28, 3: 1.68, 4: 1.17, 5: 0.77, 6: 0.62, 7: 0.59, 8: 0.86, 9: 1.46, 10: 2.14, 11: 2.55, 12: 2.8, 13: 3.07, 14: 3.43, 15: 3.7, 16: 3.8, 17: 4.03, 18: 4.23, 19: 4.46, 20: 4.65, 21: 4.84, 22: 4.96, 23: 4.9},
        11:  {0: 4.42, 1: 3.41, 2: 2.49, 3: 1.69, 4: 1.07, 5: 0.74, 6: 0.51, 7: 0.63, 8: 0.85, 9: 1.47, 10: 2.3, 11: 2.75, 12: 3.03, 13: 3.31, 14: 3.62, 15: 3.85, 16: 3.89, 17: 4.08, 18: 4.3, 19: 4.57, 20: 4.75, 21: 4.89, 22: 5.05, 23: 5.11},
        12:  {0: 5.26, 1: 4.22, 2: 3.12, 3: 2.21, 4: 1.4, 5: 0.91, 6: 0.59, 7: 0.43, 8: 0.74, 9: 1.35, 10: 2.32, 11: 2.83, 12: 3.18, 13: 3.43, 14: 3.7, 15: 4.06, 16: 4.3, 17: 4.46, 18: 4.77, 19: 5.03, 20: 5.29, 21: 5.45, 22: 5.66, 23: 5.81},
    },
    "tel-aviv": {
        1:  {0: 7.74, 1: 7.99, 2: 8.3, 3: 8.3, 4: 8.21, 5: 7.31, 6: 5.19, 7: 3.02, 8: 1.64, 9: 0.81, 10: 0.47, 11: 0.47, 12: 0.72, 13: 1.23, 14: 2.17, 15: 3.17, 16: 4.1, 17: 4.77, 18: 5.41, 19: 5.93, 20: 6.25, 21: 6.6, 22: 7.05, 23: 7.36},
        2:  {0: 7.51, 1: 7.78, 2: 7.96, 3: 8.06, 4: 7.99, 5: 6.72, 6: 4.52, 7: 2.74, 8: 1.55, 9: 0.87, 10: 0.57, 11: 0.58, 12: 0.77, 13: 1.17, 14: 1.95, 15: 3.01, 16: 3.7, 17: 4.38, 18: 5.1, 19: 5.77, 20: 6.14, 21: 6.62, 22: 6.92, 23: 7.18},
        3:  {0: 8.57, 1: 8.85, 2: 9.05, 3: 9.32, 4: 8.72, 5: 6.67, 6: 4.41, 7: 2.67, 8: 1.54, 9: 0.9, 10: 0.68, 11: 0.69, 12: 1.03, 13: 1.34, 14: 2.19, 15: 3.3, 16: 4.23, 17: 4.92, 18: 5.7, 19: 6.3, 20: 6.85, 21: 7.47, 22: 7.83, 23: 8.21},
        4:  {0: 9.23, 1: 9.51, 2: 9.62, 3: 9.55, 4: 8.07, 5: 5.74, 6: 3.81, 7: 2.3, 8: 1.23, 9: 1.01, 10: 0.91, 11: 1.06, 12: 1.37, 13: 1.91, 14: 2.77, 15: 3.93, 16: 4.96, 17: 5.78, 18: 6.32, 19: 6.94, 20: 7.39, 21: 8.01, 22: 8.38, 23: 8.87},
        5:  {0: 8.94, 1: 9.19, 2: 9.4, 3: 8.8, 4: 7.02, 5: 5.02, 6: 3.07, 7: 1.73, 8: 1.16, 9: 0.91, 10: 0.96, 11: 0.94, 12: 1.34, 13: 1.76, 14: 2.59, 15: 3.6, 16: 4.76, 17: 5.47, 18: 5.98, 19: 6.55, 20: 7.05, 21: 7.54, 22: 8.1, 23: 8.5},
        6:  {0: 7.76, 1: 8.09, 2: 8.17, 3: 7.53, 4: 5.98, 5: 4.33, 6: 2.57, 7: 1.23, 8: 0.76, 9: 0.43, 10: 0.43, 11: 0.64, 12: 0.91, 13: 1.23, 14: 1.85, 15: 2.79, 16: 3.91, 17: 4.63, 18: 5.11, 19: 5.54, 20: 5.95, 21: 6.43, 22: 6.93, 23: 7.44},
        7:  {0: 7.41, 1: 7.74, 2: 7.91, 3: 7.45, 4: 6.0, 5: 4.39, 6: 2.67, 7: 1.3, 8: 0.7, 9: 0.43, 10: 0.3, 11: 0.46, 12: 0.82, 13: 1.16, 14: 1.86, 15: 2.64, 16: 3.77, 17: 4.32, 18: 4.81, 19: 5.17, 20: 5.61, 21: 6.08, 22: 6.58, 23: 7.03},
        8:  {0: 6.64, 1: 6.94, 2: 7.1, 3: 6.94, 4: 5.66, 5: 4.05, 6: 2.56, 7: 1.22, 8: 0.63, 9: 0.29, 10: 0.3, 11: 0.47, 12: 0.75, 13: 1.28, 14: 1.94, 15: 2.86, 16: 3.71, 17: 4.1, 18: 4.46, 19: 4.79, 20: 5.11, 21: 5.43, 22: 5.84, 23: 6.26},
        9:  {0: 7.04, 1: 7.39, 2: 7.57, 3: 7.59, 4: 6.33, 5: 4.18, 6: 2.81, 7: 1.44, 8: 0.57, 9: 0.3, 10: 0.34, 11: 0.38, 12: 0.74, 13: 1.31, 14: 2.06, 15: 3.08, 16: 3.66, 17: 4.1, 18: 4.46, 19: 4.89, 20: 5.29, 21: 5.66, 22: 6.16, 23: 6.65},
        10:  {0: 7.88, 1: 8.15, 2: 8.47, 3: 8.53, 4: 7.61, 5: 5.4, 6: 3.23, 7: 1.83, 8: 0.89, 9: 0.47, 10: 0.38, 11: 0.57, 12: 0.99, 13: 1.66, 14: 2.55, 15: 3.43, 16: 3.91, 17: 4.45, 18: 5.06, 19: 5.65, 20: 6.16, 21: 6.6, 22: 7.07, 23: 7.44},
        11:  {0: 8.47, 1: 8.71, 2: 9.01, 3: 9.01, 4: 8.63, 5: 6.82, 6: 4.4, 7: 2.39, 8: 1.17, 9: 0.44, 10: 0.45, 11: 0.77, 12: 1.14, 13: 1.83, 14: 2.93, 15: 3.79, 16: 4.51, 17: 5.27, 18: 5.89, 19: 6.49, 20: 6.97, 21: 7.25, 22: 7.59, 23: 7.93},
        12:  {0: 8.04, 1: 8.23, 2: 8.51, 3: 8.62, 4: 8.59, 5: 7.29, 6: 5.1, 7: 2.82, 8: 1.55, 9: 0.76, 10: 0.5, 11: 0.5, 12: 0.88, 13: 1.48, 14: 2.67, 15: 3.53, 16: 4.28, 17: 5.06, 18: 5.58, 19: 6.05, 20: 6.54, 21: 6.9, 22: 7.18, 23: 7.6},
    },
    "warsaw": {
        1:  {0: 2.68, 1: 2.8, 2: 2.97, 3: 3.16, 4: 3.25, 5: 3.3, 6: 3.31, 7: 3.32, 8: 3.01, 9: 2.4, 10: 1.87, 11: 1.37, 12: 1.01, 13: 0.85, 14: 0.93, 15: 1.28, 16: 1.7, 17: 1.92, 18: 2.07, 19: 2.26, 20: 2.41, 21: 2.52, 22: 2.66, 23: 2.58},
        2:  {0: 4.07, 1: 4.2, 2: 4.35, 3: 4.45, 4: 4.57, 5: 4.6, 6: 4.67, 7: 4.26, 8: 3.5, 9: 2.63, 10: 1.96, 11: 1.38, 12: 0.93, 13: 0.74, 14: 0.7, 15: 1.04, 16: 1.63, 17: 2.18, 18: 2.57, 19: 2.87, 20: 3.04, 21: 3.34, 22: 3.62, 23: 3.9},
        3:  {0: 7.84, 1: 8.2, 2: 8.61, 3: 8.88, 4: 9.26, 5: 9.26, 6: 8.49, 7: 6.66, 8: 5.03, 9: 3.55, 10: 2.3, 11: 1.52, 12: 0.85, 13: 0.46, 14: 0.5, 15: 0.74, 16: 1.57, 17: 2.94, 18: 3.96, 19: 4.71, 20: 5.49, 21: 6.08, 22: 6.7, 23: 7.37},
        4:  {0: 7.58, 1: 8.13, 2: 8.61, 3: 9.01, 4: 9.26, 5: 8.38, 6: 6.86, 7: 5.37, 8: 4.05, 9: 3.0, 10: 2.24, 11: 1.57, 12: 1.19, 13: 0.73, 14: 0.61, 15: 0.67, 16: 1.13, 17: 1.93, 18: 3.05, 19: 3.93, 20: 4.88, 21: 5.59, 22: 6.28, 23: 7.09},
        5:  {0: 8.67, 1: 9.23, 2: 9.62, 3: 10.07, 4: 9.48, 5: 7.88, 6: 6.27, 7: 4.7, 8: 3.47, 9: 2.58, 10: 1.92, 11: 1.42, 12: 0.99, 13: 0.76, 14: 0.75, 15: 0.88, 16: 1.29, 17: 1.85, 18: 3.21, 19: 4.53, 20: 5.62, 21: 6.63, 22: 7.19, 23: 8.17},
        6:  {0: 9.28, 1: 9.79, 2: 10.33, 3: 10.56, 4: 9.43, 5: 7.79, 6: 6.31, 7: 4.95, 8: 3.79, 9: 2.82, 10: 2.17, 11: 1.47, 12: 1.0, 13: 0.98, 14: 0.89, 15: 1.18, 16: 1.51, 17: 2.13, 18: 3.17, 19: 4.56, 20: 6.05, 21: 7.03, 22: 7.85, 23: 8.65},
        7:  {0: 8.57, 1: 8.94, 2: 9.37, 3: 9.66, 4: 8.98, 5: 7.55, 6: 6.25, 7: 5.02, 8: 4.01, 9: 2.99, 10: 2.22, 11: 1.63, 12: 1.15, 13: 1.03, 14: 0.95, 15: 1.2, 16: 1.56, 17: 2.32, 18: 3.41, 19: 4.72, 20: 5.9, 21: 6.79, 22: 7.55, 23: 7.93},
        8:  {0: 8.42, 1: 8.86, 2: 9.32, 3: 9.6, 4: 9.58, 5: 8.26, 6: 6.83, 7: 5.32, 8: 3.96, 9: 2.9, 10: 2.03, 11: 1.36, 12: 0.98, 13: 0.72, 14: 0.73, 15: 0.86, 16: 1.35, 17: 2.35, 18: 3.77, 19: 5.05, 20: 5.88, 21: 6.63, 22: 7.28, 23: 7.95},
        9:  {0: 7.74, 1: 8.19, 2: 8.5, 3: 8.95, 4: 9.13, 5: 8.83, 6: 7.48, 7: 5.93, 8: 4.36, 9: 2.97, 10: 1.95, 11: 1.23, 12: 0.65, 13: 0.41, 14: 0.45, 15: 0.81, 16: 1.52, 17: 2.95, 18: 4.17, 19: 4.97, 20: 5.65, 21: 6.38, 22: 6.96, 23: 7.25},
        10:  {0: 6.28, 1: 6.37, 2: 6.55, 3: 6.65, 4: 6.75, 5: 6.77, 6: 6.53, 7: 5.34, 8: 3.99, 9: 2.86, 10: 1.8, 11: 1.07, 12: 0.54, 13: 0.4, 14: 0.61, 15: 1.4, 16: 2.36, 17: 3.25, 18: 3.9, 19: 4.38, 20: 4.76, 21: 5.28, 22: 5.61, 23: 6.06},
        11:  {0: 3.05, 1: 3.19, 2: 3.24, 3: 3.42, 4: 3.44, 5: 3.54, 6: 3.51, 7: 3.23, 8: 2.65, 9: 2.08, 10: 1.47, 11: 0.95, 12: 0.6, 13: 0.57, 14: 0.85, 15: 1.46, 16: 1.87, 17: 2.23, 18: 2.43, 19: 2.65, 20: 2.77, 21: 2.93, 22: 3.04, 23: 2.93},
        12:  {0: 2.15, 1: 2.25, 2: 2.32, 3: 2.41, 4: 2.41, 5: 2.47, 6: 2.43, 7: 2.38, 8: 2.18, 9: 1.83, 10: 1.39, 11: 1.12, 12: 0.79, 13: 0.75, 14: 0.96, 15: 1.2, 16: 1.45, 17: 1.53, 18: 1.61, 19: 1.7, 20: 1.72, 21: 1.8, 22: 1.92, 23: 2.06},
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
    `lo` and `hi` must already encode the bucket extent — _parse_outcome is the
    canonical source (Celsius-exact "be 19°C" returns [18.5, 19.5]).
    """
    p_hi = 1.0 if hi is None else _norm_cdf((hi - forecast_mean) / sigma)
    p_lo = 0.0 if lo is None else _norm_cdf((lo - forecast_mean) / sigma)
    return max(0.0, p_hi - p_lo)


def _parse_outcome(question: str) -> tuple[Optional[float], Optional[float], bool]:
    """
    Parse temperature outcome from market question.
    Returns (lo_celsius, hi_celsius, is_celsius) — the resolution bucket's
    continuous edges in °C. Resolution rounds raw temp to whole degrees in
    the market's native unit (°F or °C, round-half-up); the ±0.5 pad in the
    native unit defines the bucket's continuous extent. `_outcome_prob` is
    pure CDF(hi)−CDF(lo) and does no further padding.

    Returns (None, None, False) if unparseable.

    Handles patterns:
      "...be 19°C on..."          → [18.5, 19.5]°C
      "...be 20°C or higher..."   → [19.5, None]°C
      "...be 15°C or below..."    → [None, 15.5]°C
      "...be between 70-71°F..."  → [69.5°F, 71.5°F] → converted to °C
      "...be 84°F or higher..."   → [83.5°F, None] → converted
      "...be 72°F or below..."    → [None, 72.5°F] → converted
    """
    # Forecast μ/σ from Open-Meteo are daily-MAX only. Reject any market
    # asking about a different statistic (lowest/coldest/warmest/coolest)
    # — we have no model for it and would mis-price.
    ql = question.lower()
    if "lowest" in ql or "coldest" in ql or "warmest" in ql or "coolest" in ql:
        return None, None, False

    # Fahrenheit exact range "70-71°F"  →  [lo-0.5°F, hi+0.5°F]
    m = re.search(r'be (?:between )?(\d+)-(\d+)[°\s]*F', question, re.IGNORECASE)
    if m:
        lo_f, hi_f = float(m.group(1)), float(m.group(2))
        lo_c = (lo_f - 0.5 - 32) * 5 / 9
        hi_c = (hi_f + 0.5 - 32) * 5 / 9
        return lo_c, hi_c, False

    # Fahrenheit "84°F or higher"  →  [lo-0.5°F, +∞)
    m = re.search(r'be (\d+)[°\s]*F or higher', question, re.IGNORECASE)
    if m:
        lo_f = float(m.group(1))
        return (lo_f - 0.5 - 32) * 5 / 9, None, False

    # Fahrenheit "72°F or below" / "below 72°F"  →  (−∞, hi+0.5°F]
    m = re.search(r'(?:be )?(\d+)[°\s]*F or below', question, re.IGNORECASE)
    if m:
        hi_f = float(m.group(1))
        return None, (hi_f + 0.5 - 32) * 5 / 9, False

    # Celsius exact "be 19°C on"  →  [t-0.5, t+0.5]°C
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C (?:on|in)', question, re.IGNORECASE)
    if m:
        t = float(m.group(1))
        return t - 0.5, t + 0.5, True

    # Celsius "or higher / above"  →  [lo-0.5, +∞)°C
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C or (?:higher|above)', question, re.IGNORECASE)
    if m:
        return float(m.group(1)) - 0.5, None, True

    # Celsius "or below / lower"  →  (−∞, hi+0.5]°C
    m = re.search(r'be (\d+(?:\.\d+)?)[°\s]*C or (?:below|lower)', question, re.IGNORECASE)
    if m:
        return None, float(m.group(1)) + 0.5, True

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


def _resolve_coords_from_description(description: str) -> Optional[tuple]:
    """
    Extract WU station code + exact coords from a market description without needing
    city-centre coords (no haversine gate). Used for dynamically discovered cities
    that are not in CITY_COORDS.

    Returns (station_code, lat, lon) or None.
    """
    from strategy.resolution_mapper import _extract_wu_station, STATION_COORDS
    station = _extract_wu_station(description)
    if not station:
        return None
    coords = STATION_COORDS.get(station)
    if not coords:
        return None
    return station, coords[0], coords[1]


class WeatherArb:
    def __init__(self, bot) -> None:
        self.bot = bot
        self._fired_tokens: set[str] = set()
        self._fired_city_dates: dict[str, str] = {}  # city|date → held token_id
        self._bucket_consensus: dict[str, list] = {}  # city|date → [(token_id, mu, ts), ...]
        # Restore consensus counter from disk so restarts don't reset the run streak.
        # Keep both today and tomorrow — D+1 markets accumulate consensus overnight.
        _today_iso    = date.today().isoformat()
        _tomorrow_iso = (date.today() + timedelta(days=1)).isoformat()
        try:
            with open(_CONSENSUS_STATE_PATH) as _cf:
                _saved = json.load(_cf)
            _now_ts = time.time()
            for _k, _entries in _saved.items():
                if not (_k.endswith(_today_iso) or _k.endswith(_tomorrow_iso)):
                    continue  # stale date — skip
                _valid = [e for e in _entries if _now_ts - e[2] < 8 * 3600]
                if _valid:
                    self._bucket_consensus[_k] = [tuple(e) for e in _valid]
            if self._bucket_consensus:
                logger.info("[WA] Restored %d bucket consensus state(s) from disk",
                            len(self._bucket_consensus))
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            pass
        self._task: Optional[asyncio.Task] = None
        self._metar_task: Optional[asyncio.Task] = None
        self._hourly_cache: dict[tuple, tuple] = {}  # (lat2, lon2, date) → {utc_hour: temp_c}
        self._nwp_today_cache: dict[tuple, Optional[float]] = {}  # (lat2, lon2, date) → nwp_daily_max_c

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

        # METAR_LOCKOUT shadow tracker — token_id → first-seen-locked ts.
        # Persists across cycles to record the moment a bucket first locked out.
        self._lockout_first_seen: dict[str, float] = {}

        # ── Centralized position state tracker ───────────────────────────────────
        # Single source of truth for ALL weather positions from order placement to settlement.
        # Lifecycle: RESTING_MAKER → FILLED → (auto-popped when bot.risk drops it)
        #            TAKER_PENDING → FILLED
        # Schema per token_id:
        #   strategy_tag   : str   — STRAT_1_OVERNIGHT|STRAT_2_BRACKET|STRAT_3_INTRADAY|STRAT_4_TAIL_SNIPER
        #   icao_station   : str|None  — ICAO code of the resolution station (or None)
        #   station_coords : (lat,lon) — exact sensor coords
        #   entry_price    : float — avg fill price (set at fill; resting_price before fill)
        #   target_bucket  : (lo_c, hi_c) — bucket bounds in Celsius
        #   initial_fair_prob: float  — model probability at order time
        #   expected_max_c : float|None — forecast daily max at entry
        #   status         : str   — RESTING_MAKER|TAKER_PENDING|FILLED|CLOSED
        #   placed_ts      : float — unix timestamp of order placement
        #   city           : str
        #   lo_c, hi_c     : float|None  — mirrors target_bucket (convenience aliases)
        self._positions: dict[str, dict] = {}

        # Open-Meteo live current-conditions cache for non-ICAO cities.
        # Keyed by (round(lat,2), round(lon,2)). Persists running_max_c across cycles.
        self._om_live_cache: dict[tuple, dict] = {}

        # HOT_BASE_RATE / COLD_SIGNAL fire dedup: {city|date: trigger_tag}.
        # Without this, the no-physical-event triggers fire every METAR cycle for the same
        # city, exposing us to METAR-noise-driven over-firing. One fire per city per day max.
        self._tail_base_rate_fired: dict[str, str] = {}

        # Ask anchor at session open for each city/date — used to detect that the market has
        # already repriced significantly upward before HOT_BASE_RATE fires (signal stale).
        self._tail_open_ask: dict[str, float] = {}

        # Near-threshold CLOB WS watchlist: markets that almost qualify.
        # token_id → {mkt, fair_prob, city, end_date, lo_c, hi_c, expected_max_c, min_ask}
        # Populated by _evaluate_market() when edge is thin; cleared at each _scan() start.
        # _on_weather_bbo() fires _enter() the moment ask drops to min_ask.
        self._near_threshold_watchlist: dict[str, dict] = {}

        # INTRADAY scalp TP tracking: token_id → resting sell price (fair_prob - 0.05).
        # Set when a GTC limit_sell is placed post-fill. Cleaned up when bid reaches the TP
        # (via _on_weather_bbo), when NOWCAST exit fires, or on market resolution.
        self._intraday_scalp_tp: dict[str, float] = {}

        # NWP freshness probe: last observed ensemble μ per reference city.
        # Seeded on startup; compared each scan cycle to detect when Open-Meteo
        # has ingested a new model run.
        self._nwp_probe_cache: dict[str, float] = {}

        from strategy.ensemble_weights import WeightedEnsemble
        self._ensemble = WeightedEnsemble()
        # Tracks the file position (byte offset) in forecast_actuals.jsonl so we only
        # process newly appended actual events each METAR cycle.
        self._wu_actuals_offset: int = 0
        # Upstream Oracle dedup: {city_slug|date_iso} already checked this run-day
        self._oracle_fired_dates: set[str] = set()
        # Seed _fired_tokens from any WEATHER positions already open in the risk manager
        # so restarts don't re-enter the same city/token.
        for tid, pos in getattr(self.bot.risk, "open_positions", {}).items():
            if getattr(pos, "bond_entry_class", "").startswith("WEATHER_"):
                self._fired_tokens.add(tid)
        if self._fired_tokens:
            logger.info("[WA] Seeded %d fired tokens from open positions", len(self._fired_tokens))

        logger.info("[WA] WeatherArb strategy initialized stake=$%.0f edge_min=%.2f",
                    STAKE_USD, EDGE_MIN)

    def _register_position(
        self,
        token_id: str,
        strategy_tag: str,
        icao_station: Optional[str],
        target_bucket: tuple,
        initial_fair_prob: float,
        expected_max_c: Optional[float],
        entry_price: float,
        city: str,
        status: str,
        station_coords: Optional[tuple] = None,
        end_date: str = "",
    ) -> None:
        lo_c, hi_c = target_bucket if len(target_bucket) == 2 else (None, None)
        self._positions[token_id] = {
            "strategy_tag":    strategy_tag,
            "icao_station":    icao_station,
            "station_coords":  station_coords or (CITY_COORDS.get(city, (0.0, 0.0))),
            "entry_price":     entry_price,
            "target_bucket":   target_bucket,
            "initial_fair_prob": initial_fair_prob,
            "expected_max_c":  expected_max_c,
            "status":          status,
            "placed_ts":       time.time(),
            "city":            city,
            "lo_c":            lo_c,
            "hi_c":            hi_c,
            "end_date":        end_date,
        }

    def _close_position(self, token_id: str) -> None:
        """Mark a position as CLOSED and remove it from the tracker."""
        self._positions.pop(token_id, None)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_arb_loop")
        self._metar_task = asyncio.create_task(self._metar_loop(), name="weather_metar_loop")

    @staticmethod
    def _seconds_to_next_nwp_slot() -> tuple[float, bool]:
        """Return (sleep_seconds, is_nwp_slot).
        sleep_seconds is capped at 21600s (6h) so we baseline-scan every 6 hours.
        is_nwp_slot=True means we woke because a publish slot is imminent — run the
        freshness probe. is_nwp_slot=False means 6h cap fired — scan immediately."""
        now = datetime.now(timezone.utc)
        for h in NWP_SCAN_SLOTS_UTC:
            candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if candidate > now:
                secs = (candidate - now).total_seconds()
                if secs <= 21600.0:
                    return secs, True   # NWP slot within 6h
                return 21600.0, False   # 6h cap fires first
        tomorrow_first = now.replace(hour=NWP_SCAN_SLOTS_UTC[0],
                                     minute=0, second=0, microsecond=0) \
                         + timedelta(days=1)
        secs = (tomorrow_first - now).total_seconds()
        if secs <= 21600.0:
            return secs, True
        return 21600.0, False

    async def _probe_data_fresh(self) -> bool:
        """Fetch ensemble μ for 3 reference cities; return True if any shifted > PROBE_SHIFT_C.
        Updates _nwp_probe_cache regardless — seeds it on first call."""
        today     = date.today().isoformat()
        tomorrow  = (date.today() + timedelta(days=1)).isoformat()
        shifted   = False
        for city, lat, lon in _PROBE_CITIES:
            try:
                fc = await self._get_forecast(lat, lon, today, tomorrow, city)
            except Exception:
                continue
            if not fc or tomorrow not in fc:
                continue
            mu_new, _ = fc[tomorrow]
            mu_old = self._nwp_probe_cache.get(city)
            self._nwp_probe_cache[city] = mu_new
            if mu_old is not None and abs(mu_new - mu_old) > PROBE_SHIFT_C:
                logger.info("[WA] NWP shift: %s μ %.2f→%.2f°C (Δ%.2f)",
                            city, mu_old, mu_new, mu_new - mu_old)
                shifted = True
        return shifted

    async def _wait_for_nwp_refresh(self) -> bool:
        """After a publish slot, poll until Open-Meteo confirms a new run or we time out.
        First probe at T+10min, then every 10min, give up at T+30 and scan anyway."""
        await asyncio.sleep(PROBE_FIRST_WAIT_MIN * 60)
        for attempt in range(PROBE_MAX_RETRIES):
            if attempt > 0:
                await asyncio.sleep(PROBE_INTERVAL_MIN * 60)
            try:
                if await self._probe_data_fresh():
                    logger.info("[WA] fresh NWP data confirmed (probe %d) — scanning now",
                                attempt + 1)
                    return True
            except Exception:
                logger.debug("[WA] probe attempt %d error", attempt + 1, exc_info=True)
        logger.info("[WA] no NWP shift after %dmin — scanning anyway",
                    PROBE_FIRST_WAIT_MIN + (PROBE_MAX_RETRIES - 1) * PROBE_INTERVAL_MIN)
        return False

    async def _loop(self) -> None:
        await asyncio.sleep(60.0)  # allow bot to initialise
        # Seed probe cache and do an initial scan before entering the main loop
        await self._probe_data_fresh()
        try:
            await self._scan()
        except Exception:
            logger.exception("[WA] initial scan error")
        while True:
            sleep_s, is_nwp_slot = self._seconds_to_next_nwp_slot()
            logger.debug("[WA] sleeping %.0fs (%s)", sleep_s,
                         "NWP slot" if is_nwp_slot else "60min baseline")
            await asyncio.sleep(sleep_s)
            if is_nwp_slot:
                # NWP publish: probe until Open-Meteo confirms fresh data, then scan
                await self._wait_for_nwp_refresh()
            # else: 60-min baseline scan — no probe, scan immediately
            try:
                await self._scan()
            except Exception:
                logger.exception("[WA] scan error")

    @staticmethod
    def _hours_to_local_resolution(end_date_str: str, icao: Optional[str]) -> float:
        """Hours from now until midnight LOCAL on end_date for this city's ICAO.
        Midnight local = start of the day AFTER end_date in the city's timezone.
        Falls back to UTC if ICAO unknown."""
        utc_offset_h = ICAO_UTC_OFFSET_H.get(icao or "", 0)
        end_d = date.fromisoformat(end_date_str)
        # Midnight local at end of end_date = 00:00 local on end_date+1
        # In UTC: end_date+1 00:00 local = end_date+1 00:00 UTC - utc_offset_h hours
        resolution_utc = datetime(end_d.year, end_d.month, end_d.day,
                                  tzinfo=timezone.utc) + timedelta(days=1) \
                         - timedelta(hours=utc_offset_h)
        return (resolution_utc - datetime.now(timezone.utc)).total_seconds() / 3600.0

    async def _scan(self) -> None:
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        # Include both today and tomorrow: UTC+9 cities (Tokyo etc.) can have their
        # "today" market still within the entry window when scanning in the morning UTC.
        target_dates = {today, tomorrow}

        logger.info("[WA] scanning weather markets today=%s tomorrow=%s", today, tomorrow)

        # Refresh watchlist each scan so fair_probs stay current.
        # CLOB WS subscriptions persist independently; only the in-memory trigger
        # context is cleared here — it gets re-populated below for still-qualifying markets.
        self._near_threshold_watchlist.clear()

        # Fetch all open weather events
        events = await self._fetch_weather_events()
        if not events:
            logger.warning("[WA] no weather events returned")
            return

        from strategy.resolution_mapper import resolve_station

        entries_made = 0
        for ev in events:
            city = _parse_city(ev.get("title", ""))

            # Only trade the 23 validated cities (stations.py + 5yr skill matrix + WU source confirmed).
            city_slug = CITY_NAME_TO_SLUG.get(city, "")
            if city_slug not in VALIDATED_CITY_SLUGS:
                logger.debug("[WA] SKIP %s (not in validated 23 cities)", city)
                continue

            # Skip cities where overnight D+1 forecast edge is structurally too thin
            if city_slug in STRAT1_SKIP_CITIES:
                logger.debug("[WA] SKIP %s (STRAT1_SKIP_CITIES — low overnight WR)", city)
                continue

            # Only process markets within the local-time entry window
            _city_icao = CITY_ICAO.get(city)
            markets = []
            for m in ev.get("markets", []):
                _end = m.get("endDate", "")[:10]
                if _end not in target_dates: continue
                if m.get("closed", False): continue
                if not m.get("conditionId"): continue
                token_ids_raw = _parse_token_ids(m.get("clobTokenIds", []))
                if not token_ids_raw: continue
                prices_raw = m.get("outcomePrices", '["0"]')
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if float(prices[0]) <= 0.001: continue
                # Local-time resolution window gate
                h_left = self._hours_to_local_resolution(_end, _city_icao)
                if h_left < MIN_HOURS_BEFORE_RESOLUTION:
                    logger.debug("[WA] SKIP %s %s — only %.1fh to local resolution (min %dh)",
                                 city, _end, h_left, MIN_HOURS_BEFORE_RESOLUTION)
                    continue
                if h_left > MAX_HOURS_BEFORE_RESOLUTION:
                    logger.debug("[WA] SKIP %s %s — %.1fh to local resolution > max %dh",
                                 city, _end, h_left, MAX_HOURS_BEFORE_RESOLUTION)
                    continue
                # STRAT_1 same-day NWP staleness gate.
                # NWP daily-max forecast is valid for D+1 but stale for today once
                # we approach the city's afternoon peak. After that point INTRADAY
                # (STRAT_3) owns same-day territory via live METAR observations.
                if _end == today:
                    _slug_peak = CITY_NAME_TO_SLUG.get(city, "")
                    _peak_month = date.fromisoformat(_end).month
                    _peak_h = CITY_PEAK_HOUR_UTC.get(_slug_peak, {}).get(_peak_month)
                    _now_h = datetime.now(timezone.utc).hour
                    if _peak_h is None or _now_h >= _peak_h - STRAT1_PRE_PEAK_BLOCK_H:
                        logger.info(
                            "[WA] SKIP %s %s (same-day NWP stale: now UTC %02d, peak UTC %s, "
                            "block starts at UTC %s)",
                            city, _end, _now_h,
                            str(_peak_h) if _peak_h else "unknown",
                            str(_peak_h - STRAT1_PRE_PEAK_BLOCK_H) if _peak_h else "?",
                        )
                        continue
                markets.append(m)
            if not markets:
                continue

            # ── Dynamic location resolution ───────────────────────────────────
            # Priority 1: extract exact WU station from market description (oracle-aligned).
            # Priority 2: use CITY_COORDS lookup if city is known.
            # Priority 3: skip — cannot determine resolution location.
            description = ev.get("description", "") or ""
            if not description:
                description = markets[0].get("description", "") or ""

            city_lat = CITY_COORDS.get(city, (0.0, 0.0))[0] if city else 0.0
            city_lon = CITY_COORDS.get(city, (0.0, 0.0))[1] if city else 0.0
            known_city = city and city in CITY_COORDS

            # SAFETY: STRAT_1/2 require oracle-aligned station coords.
            # City-centre coords introduce 3-8°F bias on 1-2°F bucket markets → guaranteed loss.
            # If WU station cannot be confirmed from description, REFUSE to trade.
            if known_city:
                station_result = resolve_station(description, city, city_lat, city_lon)
                if station_result is None:
                    logger.warning(
                        "[WA] SKIP %s — WU station unconfirmed in description "
                        "(city-centre coords would introduce systematic bucket bias)",
                        city,
                    )
                    continue
                _station_code, lat, lon = station_result
            else:
                # Unknown city: extract station directly from description
                direct = _resolve_coords_from_description(description)
                if direct is None:
                    logger.debug("[WA] SKIP unknown-city market — no resolvable WU station")
                    continue
                _station_code, lat, lon = direct
                if city is None:
                    city = _station_code
                logger.debug("[WA] DYNAMIC CITY %s → station %s @ (%.4f, %.4f)",
                             city, _station_code, lat, lon)

            # Triple-check: extracted station must match the ICAO we'd use for METAR/microclimate.
            # If mismatch, the bot is about to trade with NWP from one location and exit logic
            # (METAR cache) from another — silent wrong-station risk. Refuse.
            _expected_icao = CITY_ICAO.get(city)
            if _expected_icao and _station_code and _expected_icao != _station_code:
                logger.warning(
                    "[WA] SKIP %s — station mismatch: WU=%s CITY_ICAO=%s (would split data sources)",
                    city, _station_code, _expected_icao,
                )
                continue

            # Get forecast for this city (only once per city, at exact station coords)
            forecast = await self._get_forecast(lat, lon, today, tomorrow, city)
            if not forecast:
                logger.debug("[WA] no forecast for %s", city)
                continue

            # Regime gate: skip volatile cities (high inter-model spread → σ unreliable)
            _slug_for_regime = CITY_NAME_TO_SLUG.get(city, "")
            if _get_regime(_slug_for_regime, tomorrow) == "volatile":
                logger.info("[WA] SKIP %s %s — regime=volatile (inter-model spread too wide)",
                            city, tomorrow)
                continue

            # Evaluate all buckets for this city, then enter ONLY the highest-conviction
            # one. These are negRisk markets — entering multiple buckets means one always
            # cancels the other while paying fees twice.
            candidates: list[tuple[dict, dict]] = []
            for mkt in markets:
                entry = await self._evaluate_market(city, mkt, forecast)
                if entry:
                    candidates.append((mkt, entry))

            # ── Neg-risk dedup / consensus tracking ──────────────────────────
            # Lazy-reseed from open positions: PositionMeta doesn't carry city/end_date,
            # so _fired_city_dates is empty after a process restart even though the
            # wallet still holds. Without this, a restart between scans for the same
            # city/date enters a different bucket (e.g. Atlanta 78-79°F then 80-81°F).
            _open_arb_tids = {
                _tid for _tid, _p in getattr(self.bot.risk, "open_positions", {}).items()
                if getattr(_p, "bond_entry_class", "") in ("WEATHER_ARB", "WEATHER_BRACKET")
            }
            if _open_arb_tids:
                for _mkt in markets:
                    _tids = _parse_token_ids(_mkt.get("clobTokenIds", []))
                    if _tids and _tids[0] in _open_arb_tids:
                        _ed = _mkt.get("endDate", "")[:10]
                        _tid = _tids[0]
                        self._fired_city_dates.setdefault(f"{city}|{_ed}", _tid)
                        # Re-seed in-memory position meta so bucket-switch mu_delta works after restart
                        if _tid not in self._positions:
                            _lo, _hi, _ = _parse_outcome(_mkt.get("question", ""))
                            _mid = ((_lo or 0) + (_hi or 0)) / 2 if _lo is not None and _hi is not None else None
                            self._positions[_tid] = {"expected_max_c": _mid, "status": "FILLED"}
            # Use the event's actual end_date (target_dates = {today, tomorrow},
            # so an event may be for today — hardcoding `tomorrow` here misses today's dedup).
            event_end_date = (candidates[0][0].get("endDate", "")[:10]) if candidates else tomorrow
            city_date_key = f"{city}|{event_end_date}"

            if city_date_key in self._fired_city_dates:
                # Already holding a bucket for this city/date.
                # Still evaluate to detect sustained model shifts.
                if candidates:
                    best_c_mkt, best_c_entry = max(candidates, key=lambda x: x[1]["fair_prob"])
                    await self._update_and_maybe_switch(
                        city, city_date_key, best_c_mkt, best_c_entry,
                    )
                continue

            if not candidates or entries_made >= MAX_POSITIONS:
                continue

            # ── Bracket / ladder evaluation ───────────────────────────────────
            # Only attempt ladder on wide-sigma cities (σ ≥ BRACKET_SIGMA_MIN).
            _sigma_c = (forecast.get(tomorrow) or (None, None))[1] or 0.0
            if (BRACKET_ENABLED or BRACKET_SHADOW) and len(candidates) >= 2 and _sigma_c >= BRACKET_SIGMA_MIN:
                bracket = self._select_bracket(candidates)
                if bracket is not None:
                    n_entered = await self._enter_bracket(bracket, city)
                    entries_made += n_entered
                    if BRACKET_ENABLED:
                        continue  # live bracket entered — skip single-leg

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
            _cslug = CITY_NAME_TO_SLUG.get(city, "")
            if _cslug in PER_CITY_STAKE_USD:
                stake = PER_CITY_STAKE_USD[_cslug]
            if await self._enter(best_mkt, best_entry["fair_prob"], best_entry["poly_price"],
                                 city, best_entry.get("lo_c"), best_entry.get("hi_c"),
                                 stake=stake,
                                 strategy_tag="STRAT_1_OVERNIGHT",
                                 expected_max_c=best_entry.get("expected_max_c")):
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

        # Pre-entry METAR gate: only valid for same-day markets.
        # If today's run_max already exceeds this bucket's ceiling, the outcome
        # is impossible. For tomorrow's markets today's METAR is irrelevant.
        _today = __import__("datetime").date.today().isoformat()
        _icao = CITY_ICAO.get(city)
        if end_date == _today and _icao and hi_c is not None:
            _metar = self._icao_metar_cache.get(_icao)
            if _metar:
                _run_max = _metar.get("running_max_c")
                if _run_max is not None and _run_max > hi_c:
                    logger.info(
                        "[WA] SKIP %s bucket=[%.1f,%.1f) — METAR run_max=%.1f°C already above ceiling",
                        city, lo_c if lo_c is not None else float("-inf"), hi_c, _run_max,
                    )
                    return None

        forecast_entry = forecast.get(end_date)
        if not forecast_entry:
            return None
        forecast_mean, sigma_c = forecast_entry

        if sigma_c > SIGMA_SKIP_FLOOR:
            logger.debug("[WA] SKIP %s %s — sigma=%.2f > SIGMA_SKIP_FLOOR=%.1f (too uncertain)",
                         city, end_date, sigma_c, SIGMA_SKIP_FLOOR)
            return None

        city_slug = CITY_NAME_TO_SLUG.get(city, "")
        month = date.fromisoformat(end_date).month
        era5_sigma = CITY_SIGMA_C_ERA5.get(city_slug, {}).get(month)
        if era5_sigma and abs(era5_sigma - sigma_c) > 0.05:
            logger.debug("[WA] SIGMA_SHADOW %s M%02d live=%.3f era5=%.3f delta=%.3f",
                         city_slug, month, sigma_c, era5_sigma, era5_sigma - sigma_c)

        # Sigma inflation for high-price entries: compensates for suspected overconfidence
        # when ask > ASK_BAND_HI. Only active when BRACKET_ENABLED (Upgrade 4).
        effective_sigma_c = sigma_c
        if BRACKET_ENABLED and poly_yes >= ASK_BAND_HI:
            effective_sigma_c = sigma_c * SIGMA_INFLATION_ABOVE_CAP

        sigma = effective_sigma_c if is_celsius else effective_sigma_c * (SIGMA_F_DEFAULT / SIGMA_C_DEFAULT)
        fair_prob = _outcome_prob(forecast_mean, lo_c, hi_c, sigma)

        edge = fair_prob - poly_yes
        if edge < EDGE_MIN:
            self._maybe_add_to_watchlist(
                token_id, mkt, fair_prob, poly_yes, edge,
                city, end_date, lo_c, hi_c, forecast_mean,
            )
            return None

        # Ask-band filter: use relaxed ceiling when BRACKET_ENABLED (Upgrade 4).
        # When bracket is off, strict ASK_BAND_HI applies (60d calibration data).
        ask_hi = BRACKET_COST_CAP if BRACKET_ENABLED else ASK_BAND_HI
        if not (ASK_BAND_LO <= poly_yes < ask_hi):
            return None

        logger.info("[WA] CANDIDATE %s %s poly=%.3f fair=%.3f edge=%.3f mu=%.2f°C sigma=%.2f°C bucket=[%.1f,%.1f] %s",
                    city, end_date, poly_yes, fair_prob, edge,
                    forecast_mean, effective_sigma_c,
                    lo_c if lo_c is not None else float("-inf"),
                    hi_c if hi_c is not None else float("inf"),
                    question[:55])

        return {
            "token_id":      token_id,
            "condition_id":  mkt.get("conditionId", ""),
            "poly_price":    poly_yes,
            "fair_prob":     fair_prob,
            "edge":          edge,
            "question":      question,
            "end_date":      end_date,
            "lo_c":          lo_c,
            "hi_c":          hi_c,
            "expected_max_c": forecast_mean,
        }

    def _maybe_add_to_watchlist(
        self, token_id: str, mkt: dict, fair_prob: float, poly_yes: float,
        edge: float, city: str, end_date: str,
        lo_c: Optional[float], hi_c: Optional[float], expected_max_c: float,
    ) -> None:
        """Subscribe a near-qualifying market to CLOB WS; fire entry when ask falls."""
        ask_hi = BRACKET_COST_CAP if BRACKET_ENABLED else ASK_BAND_HI
        min_ask = fair_prob - EDGE_MIN  # ask must reach this level before we can enter

        if (edge < WATCHLIST_EDGE_FLOOR          # too far from qualifying
                or fair_prob < WATCHLIST_MIN_FAIR
                or min_ask >= ask_hi              # would never pass ask-band check
                or poly_yes < ASK_BAND_LO
                or token_id in self._fired_tokens
                or token_id in self._near_threshold_watchlist):
            return

        self._near_threshold_watchlist[token_id] = {
            "mkt": mkt,
            "fair_prob": fair_prob,
            "city": city,
            "end_date": end_date,
            "lo_c": lo_c,
            "hi_c": hi_c,
            "expected_max_c": expected_max_c,
            "min_ask": min_ask,
        }
        try:
            self.bot.feed._clob_ws_sub_queue.put_nowait([token_id])
        except Exception:
            pass
        logger.info(
            "[WA] WATCHLIST+SUB %s %s fair=%.3f ask=%.3f → watching for ask≤%.3f (gap=%.3f)",
            city, end_date, fair_prob, poly_yes, min_ask, EDGE_MIN - edge,
        )

    async def _on_weather_bbo(self, token_id: str, bid: float) -> None:
        """BBO callback: scalp TP monitoring for INTRADAY, and watchlist entry firing."""
        # INTRADAY scalp TP: bid reached our resting sell → position filled, clean up tracker
        if token_id in self._intraday_scalp_tp:
            scalp_tp = self._intraday_scalp_tp[token_id]
            if bid >= scalp_tp:
                logger.info(
                    "[WA] INTRADAY SCALP TP HIT %s bid=%.3f tp=%.3f → tracker closed",
                    token_id[:12], bid, scalp_tp,
                )
                del self._intraday_scalp_tp[token_id]
                self._close_position(token_id)
                self._fired_tokens.discard(token_id)
            return  # active position — don't process watchlist

        entry = self._near_threshold_watchlist.get(token_id)
        if entry is None:
            return

        city = entry["city"]
        end_date = entry["end_date"]

        # Stale: city already entered or token already fired
        if token_id in self._fired_tokens or f"{city}|{end_date}" in self._fired_city_dates:
            self._near_threshold_watchlist.pop(token_id, None)
            return

        # Get live ask from order book (bid alone is insufficient — spread can be wide)
        ob = self.bot.feed.order_books.get(token_id)
        if ob is None or not ob.asks:
            return
        live_ask = ob.asks[0][0]

        fair_prob = entry["fair_prob"]
        live_edge = fair_prob - live_ask

        if live_edge < EDGE_MIN:
            return  # not yet

        ask_hi = BRACKET_COST_CAP if BRACKET_ENABLED else ASK_BAND_HI
        if not (ASK_BAND_LO <= live_ask < ask_hi):
            return

        # Remove immediately to prevent double-entry before _enter() returns
        self._near_threshold_watchlist.pop(token_id, None)

        logger.info(
            "[WA] WATCHLIST HIT %s %s fair=%.3f live_ask=%.3f edge=%.3f (bid=%.3f)",
            city, end_date, fair_prob, live_ask, live_edge, bid,
        )
        stake = self._kelly_stake(live_edge, live_ask)
        await self._enter(
            entry["mkt"], fair_prob, live_ask,
            city, entry["lo_c"], entry["hi_c"],
            stake=stake,
            strategy_tag="STRAT_1_OVERNIGHT",
            expected_max_c=entry["expected_max_c"],
        )

    async def _enter(self, mkt: dict, fair_prob: float, poly_price: float,
                     city: str, bucket_lo_c: Optional[float] = None,
                     bucket_hi_c: Optional[float] = None,
                     stake: float = STAKE_USD,
                     strategy_tag: str = "STRAT_1_OVERNIGHT",
                     expected_max_c: Optional[float] = None) -> bool:
        token_id  = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
        cid       = mkt.get("conditionId", "")
        question  = mkt.get("question", "")
        end_date  = mkt.get("endDate", "?")[:10]
        neg_risk  = mkt.get("negRisk", True)

        self._fired_tokens.add(token_id)
        self._fired_city_dates.setdefault(f"{city}|{end_date}", token_id)

        logger.info("[WA] ENTER city=%s date=%s poly=%.3f fair=%.3f stake=$%.0f%s",
                    city, end_date, poly_price, fair_prob, stake,
                    " [DRY]" if DRY_RUN_LOG else "")
        logger.info("[WA]   q=%s", question[:70])

        if DRY_RUN_LOG:
            return True

        try:
            # CLOB pre-flight: fetch book to decide maker vs taker price
            best_bid, best_ask, vwap, has_depth = await self._fetch_book_and_vwap(token_id, stake)
            live_edge = fair_prob - best_ask
            if live_edge < EDGE_MIN:
                logger.info(
                    "[WA] ABORT %s %s — ask moved %.3f→%.3f, live edge %.3f < %.2f (retry next scan)",
                    city, end_date, poly_price, best_ask, live_edge, EDGE_MIN,
                )
                self._fired_tokens.discard(token_id)
                self._fired_city_dates.pop(f"{city}|{end_date}", None)
                return False
            edge = fair_prob - poly_price
            use_taker = (not MAKER_FIRST) or (edge >= TAKER_EDGE_MIN) or (not has_depth)
            if use_taker:
                intended_price = vwap if has_depth else best_ask
                # Thin-book guard: if walking the book pushes VWAP above edge floor, abort.
                # Paying more than fair_prob - EDGE_MIN destroys the EV basis for the trade.
                if intended_price > fair_prob - EDGE_MIN:
                    logger.info(
                        "[WA] ABORT %s %s — thin book vwap=%.3f > edge floor %.3f",
                        city, end_date, intended_price, fair_prob - EDGE_MIN,
                    )
                    self._fired_tokens.discard(token_id)
                    self._fired_city_dates.pop(f"{city}|{end_date}", None)
                    return False
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
                # Register as RESTING_MAKER — orphan manager will cancel if model degrades.
                self._register_position(
                    token_id, strategy_tag, CITY_ICAO.get(city),
                    (bucket_lo_c, bucket_hi_c), fair_prob, expected_max_c,
                    intended_price, city, "RESTING_MAKER",
                    end_date=end_date,
                )
            if use_taker:
                # Taker: register as TAKER_PENDING; will update to FILLED on success.
                self._register_position(
                    token_id, strategy_tag, CITY_ICAO.get(city),
                    (bucket_lo_c, bucket_hi_c), fair_prob, expected_max_c,
                    intended_price, city, "TAKER_PENDING",
                    end_date=end_date,
                )

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
            if fill.status == OrderStatus.FILLED and fill.total_size > 0:
                # Transition position state to FILLED; update actual fill price
                if token_id in self._positions:
                    self._positions[token_id]["status"] = "FILLED"
                    self._positions[token_id]["entry_price"] = fill.avg_fill_price
                else:
                    self._register_position(
                        token_id, strategy_tag, CITY_ICAO.get(city),
                        (bucket_lo_c, bucket_hi_c), fair_prob, expected_max_c,
                        fill.avg_fill_price, city, "FILLED",
                        end_date=end_date,
                    )
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
                    bond_entry_class="WEATHER_BRACKET" if strategy_tag == "STRAT_2_BRACKET" else "WEATHER_ARB",
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
                _meta["signal_source"] = f"WEATHER/{city}/{strategy_tag}"
                _meta["weather_question"] = question
                _meta["weather_date"] = end_date
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
                _mu_log = expected_max_c if expected_max_c is not None else float("nan")
                logger.info(
                    "[WA] FILLED %s shares=%.1f @ %.4f fair=%.3f mu=%.2f°C scalp_tp=%.4f%s",
                    question[:45], fill.total_size, fill.avg_fill_price,
                    fair_prob, _mu_log, _scalp_tp,
                    "" if _scalp_tp > 0 else " (hold-to-resolution)",
                )
                return True
            else:
                self._close_position(token_id)
                self._fired_tokens.discard(token_id)
                logger.warning("[WA] fill failed %s: %s",
                               city, getattr(fill, "error", "?"))
                return False
        except Exception:
            self._close_position(token_id)
            self._fired_tokens.discard(token_id)
            logger.exception("[WA] enter error %s", city)
            return False

    async def _exit_for_switch(self, token_id: str, city: str) -> bool:
        """
        Exit a held position to free the city/date slot for a better bucket.
        Returns True if exit succeeded (or position was already gone), False if illiquid.
        """
        if not hasattr(self.bot, "risk") or token_id not in self.bot.risk.open_positions:
            self._close_position(token_id)
            return True
        pos = self.bot.risk.open_positions[token_id]
        current_bid, current_ask, _, _ = await self._fetch_book_and_vwap(token_id, pos.stake)
        # CLOB REST snapshots go stale (bid≈0, ask≈1 while Gamma shows fair price).
        # If spread is disconnected, fall back to Gamma outcomePrices mid.
        if current_bid < 0.05 and current_ask > 0.90 and pos.condition_id:
            try:
                async with aiohttp.ClientSession() as sess:
                    url = f"{GAMMA_BASE}/markets?condition_ids={pos.condition_id}"
                    async with sess.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            mkts = await resp.json()
                            if mkts:
                                prices_raw = mkts[0].get("outcomePrices", "[]")
                                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                                if prices:
                                    current_bid = float(prices[0])
                                    logger.info("[WA] SWITCH_BID_FALLBACK %s: CLOB stale, using Gamma mid=%.3f", city, current_bid)
            except Exception:
                pass
        if current_bid < SALVAGE_MIN_BID:
            logger.warning(
                "[WA] SWITCH_BLOCKED %s bid=%.3f < SALVAGE_MIN_BID=%.2f — illiquid, not switching",
                city, current_bid, SALVAGE_MIN_BID,
            )
            return False
        if DRY_RUN_LOG:
            logger.info("[WA] [DRY] switch: would sell %s @ %.3f", token_id[:12], current_bid - 0.01)
            return True
        try:
            await self.bot.orders.cascade_sell(
                token_id=token_id,
                total_shares=pos.shares,
                current_price=current_bid,
                reason="BUCKET_SWITCH",
                force_exit=True,
            )
            # Verify on-chain — neg-risk locks can take 5-15s to clear; USDC exhaustion
            # breaks immediately inside cascade_sell. Retry up to 3 times with 5s gaps.
            sold = False
            for attempt in range(1, 4):
                await asyncio.sleep(5.0)
                remaining = await self._fetch_onchain_size(token_id)
                if not remaining or remaining <= 0.01:
                    sold = True
                    break
                logger.warning(
                    "[WA] SWITCH_PARTIAL %s: %.4f shares remain after attempt %d — retrying",
                    city, remaining, attempt,
                )
                pos.remaining_shares = remaining
                # Re-fetch bid so we don't pass a 15s-stale price to cascade_sell
                fresh_bid, _, _, _ = await self._fetch_book_and_vwap(token_id, pos.stake)
                retry_bid = fresh_bid if fresh_bid >= SALVAGE_MIN_BID else current_bid
                await self.bot.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=remaining,
                    current_price=retry_bid,
                    reason=f"BUCKET_SWITCH_RETRY_{attempt}",
                    force_exit=True,
                )
            if not sold:
                # All 3 retries exhausted — wait for final settlement then check
                await asyncio.sleep(5.0)
                remaining = await self._fetch_onchain_size(token_id)
                if remaining and remaining > 0.01:
                    logger.error(
                        "[WA] SWITCH_SELL_FAILED %s: %.4f shares still held after 3 attempts "
                        "(NEG_RISK_LOCK or CLOB lock) — keeping position, not switching",
                        city, remaining,
                    )
                    return False
            self._close_position(token_id)
            return True
        except Exception:
            logger.exception("[WA] switch exit sell failed %s", token_id[:12])
            return False

    def _save_consensus_state(self) -> None:
        try:
            serializable = {k: [list(e) for e in v] for k, v in self._bucket_consensus.items()}
            with open(_CONSENSUS_STATE_PATH, "w") as _cf:
                json.dump(serializable, _cf)
        except Exception:
            logger.debug("[WA] Could not save bucket consensus state", exc_info=True)

    async def _update_and_maybe_switch(
        self,
        city: str,
        city_date_key: str,
        best_mkt: dict,
        best_entry: dict,
    ) -> None:
        """
        Track which bucket the model most prefers across consecutive scans.
        Fires a bucket switch when required_runs consecutive scans prefer the same new token.
        required_runs is dynamic based on mu_delta (entry mu → current NWP mu):
          >=1.5°C → 1 scan  (decisive revision)
          >=0.8°C → 2 scans (clear signal, one confirmation)
          >=0.35°C → 3 scans (moderate, full confirmation)
          < 0.35°C → 5 scans (slow drift — allowed but needs persistence)
        Switch = exit old position (if bid >= SALVAGE_MIN_BID) + enter new bucket.
        """
        new_token  = best_entry["token_id"]
        new_mu     = best_entry.get("expected_max_c") or 0.0
        held_token = self._fired_city_dates.get(city_date_key, "")
        end_date   = best_entry.get("end_date", "")

        if not held_token or new_token == held_token:
            # Model still prefers the held bucket — reset streak
            if self._bucket_consensus.pop(city_date_key, None) is not None:
                self._save_consensus_state()
            return

        # Fetch entry mu early — needed for dynamic required_runs
        held_pos_meta = self._positions.get(held_token, {})
        if held_pos_meta.get("status") == "RESTING_MAKER":
            return  # orphan cancellation handles model drift for resting orders

        entry_mu: Optional[float] = held_pos_meta.get("expected_max_c")
        if entry_mu is None:
            logger.debug("[WA] SWITCH %s/%s: no entry_mu for held token, skipping", city, end_date)
            return

        mu_delta = abs(new_mu - entry_mu)

        # Dynamic required_runs: larger shift → fewer confirmations needed
        if mu_delta >= 1.5:
            required_runs = 1
        elif mu_delta >= 0.8:
            required_runs = 2
        elif mu_delta >= 0.35:
            required_runs = 3
        else:
            required_runs = 5  # slow drift — must persist across many scans

        # Record this scan's best token
        q = self._bucket_consensus.setdefault(city_date_key, [])
        q.append((new_token, new_mu, time.time()))
        if len(q) > BUCKET_SWITCH_MAX_RUNS:
            del q[:-BUCKET_SWITCH_MAX_RUNS]
        self._save_consensus_state()

        n_agree = sum(1 for t, _, _ in q if t == new_token)
        if n_agree < required_runs:
            logger.info(
                "[WA] CONSENSUS %s/%s: %d/%d scans prefer %s... over held %s... (mu_delta=%.2f°C)",
                city, end_date, n_agree, required_runs,
                new_token[:12], held_token[:12], mu_delta,
            )
            return

        logger.warning(
            "[WA] BUCKET_SWITCH %s/%s | held=%s... → new=%s... | "
            "mu_delta=%.2f°C (%.1f→%.1f°C) | %d/%d runs agree",
            city, end_date, held_token[:12], new_token[:12],
            mu_delta, entry_mu, new_mu, n_agree, required_runs,
        )

        exit_ok = await self._exit_for_switch(held_token, city)
        if not exit_ok:
            # Sell failed (USDC exhaustion, illiquidity, etc.) but NWP has 3/3 consensus.
            # Buy the new bucket anyway with available capital — do NOT block on the sell.
            # Old position stays in _positions and will exit via METAR/WU/resolution.
            # Worst case: hold both simultaneously; 3/3 NWP edge on new bucket justifies it.
            logger.warning(
                "[WA] BUCKET_SWITCH_FORCED %s/%s: sell of %s... failed "
                "— buying new bucket %s... regardless (3/3 NWP, old position kept)",
                city, end_date, held_token[:12], new_token[:12],
            )

        # Clear dedup so _enter() can register the new bucket.
        # held_token stays in _fired_tokens (prevents spurious re-entry of old bucket)
        # but is removed from city_date dedup so the new token can claim the slot.
        self._fired_city_dates.pop(city_date_key, None)
        if exit_ok:
            self._fired_tokens.discard(held_token)
        self._bucket_consensus.pop(city_date_key, None)

        stake = self._kelly_stake(best_entry["edge"], best_entry["poly_price"])
        await self._enter(
            best_mkt, best_entry["fair_prob"], best_entry["poly_price"],
            city, best_entry.get("lo_c"), best_entry.get("hi_c"),
            stake=stake,
            strategy_tag="STRAT_1_OVERNIGHT",
            expected_max_c=new_mu,
        )

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
                # 4. WU transition check — sell confirmed losers immediately when WU posts the daily high
                await self._check_wu_transitions()
                # 5. Upstream Oracle — check METAR running_max post-peak for anomaly signal
                await self._oracle_metar_check()
                # 6. METAR_LOCKOUT shadow logger (passive, no entries)
                try:
                    await self._metar_lockout_scan()
                except Exception:
                    logger.exception("[WA] metar lockout scan error")
                # 7. Scan ALL today's markets for intraday arb (heating ramp window)
                if INTRADAY_ENABLED:
                    await self._intraday_scan()
                # 8. Tail sniper on $0.01–$0.04 tokens
                if TAIL_SNIPER_ENABLED:
                    await self._tail_sniper_check()
            except Exception:
                logger.exception("[WA] metar loop error")
            await asyncio.sleep(METAR_POLL_INTERVAL)

    async def _metar_lockout_scan(self) -> None:
        """
        Shadow logger for the METAR_LOCKOUT strategy candidate.

        For every open bucket in today's events, check whether the resolution
        bucket is physically locked out (running_max already past the bucket's
        upper edge). If locked out AND the YES side still has a non-trivial
        bid, record a candidate to logs/shadow/metar_lockout.jsonl with full
        state. No capital deployed — pure passive log for backtest.

        Rationale:
          A locked-out bucket cannot resolve YES (running_max only grows over
          the day; even a brief rise would already be reflected in running_max
          since METARs are sampled every 60s and the bot reads the running max
          across all observations in the day). YES bids > $0.02 on such
          buckets reflect MM repricing lag or dispute-risk premium.

          Edge per candidate (gross of fees):
              E[R per $ NO] = (1 − p_overshoot) × (1 / NO_ask − 1) − p_overshoot
          where NO_ask ≈ 1 − YES_bid and p_overshoot is the climatological
          probability that future METAR pushes running_max above hi_c.

          p_overshoot is post-hoc computed from ASOS data; the shadow log
          captures the raw state so the inequality can be evaluated against
          observed resolution outcomes.

        Output schema (one record per candidate per scan cycle):
          {
            schema_version, record_type, ts_utc, ts_s,
            city, icao, token_id, condition_id, question,
            bucket_lo_c_padded, bucket_hi_c_padded, is_celsius_market,
            running_max_c, temp_c, last_obs_ts,
            yes_bid, yes_ask, no_ask_implied,
            seconds_since_first_lockout, seconds_to_event_close,
            hour_utc, peak_hour_utc, month, end_date,
          }
        """
        if not self._today_markets_cache:
            return
        from datetime import datetime, timezone
        from pathlib import Path
        import time as _time

        today_str = datetime.now(timezone.utc).date().isoformat()
        log_dir = Path("logs/shadow/hot") / today_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "metar_lockout.jsonl"

        now_ts = _time.time()
        now_utc = datetime.now(timezone.utc)

        # Group markets by (event_id, city) to extract event-level resolution time
        candidates_written = 0
        for entry in self._today_markets_cache:
            mkt = entry.get("mkt") or {}
            city = entry.get("city")
            icao = entry.get("icao")
            if not city or not icao:
                continue

            # Same-day only — lockout logic is meaningless for tomorrow's markets
            end_date = (mkt.get("endDate") or "")[:10]
            if end_date != today_str:
                continue

            metar = self._icao_metar_cache.get(icao) or {}
            running_max = metar.get("running_max_c")
            if running_max is None:
                continue

            question = mkt.get("question", "")
            lo_c, hi_c, is_celsius = _parse_outcome(question)
            # Need an upper bound to be "locked out from above"
            if hi_c is None:
                continue

            # Lockout condition: running_max already past the bucket's upper edge.
            # Use a small safety margin (0.05°C) to avoid edge-case false fires at
            # the exact boundary where a tenth-degree METAR could go either way.
            LOCKOUT_SAFETY_C = 0.05
            if running_max < (hi_c + LOCKOUT_SAFETY_C):
                continue

            token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            if not token_ids:
                continue
            token_id = token_ids[0]  # YES token

            # Track first-seen lockout time per token
            first_seen = self._lockout_first_seen.get(token_id)
            if first_seen is None:
                first_seen = now_ts
                self._lockout_first_seen[token_id] = first_seen

            # Read live quote — prefer bestBid/bestAsk if gamma supplies them,
            # otherwise fall back to outcomePrices[0] as a price proxy.
            yes_bid = mkt.get("bestBid")
            yes_ask = mkt.get("bestAsk")
            try:
                yes_bid_f = float(yes_bid) if yes_bid is not None else None
                yes_ask_f = float(yes_ask) if yes_ask is not None else None
            except (TypeError, ValueError):
                yes_bid_f = yes_ask_f = None

            if yes_bid_f is None:
                # Fall back to outcomePrices[0] (mid/last)
                try:
                    prices_raw = mkt.get("outcomePrices", '["0"]')
                    prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                    yes_bid_f = float(prices[0])
                except Exception:
                    continue

            # Skip if YES bid is already near zero — no edge to capture.
            LOCKOUT_BID_FLOOR = 0.005  # only log if there's a non-trivial bid
            if yes_bid_f < LOCKOUT_BID_FLOOR:
                continue

            no_ask_implied = max(0.0, 1.0 - yes_bid_f)

            # Time to event close (resolution time = end_date local midnight + WU lag,
            # but we approximate as end_date 23:59:59 UTC for simplicity)
            try:
                end_dt = datetime.fromisoformat(end_date + "T23:59:59+00:00")
                seconds_to_close = (end_dt - now_utc).total_seconds()
            except Exception:
                seconds_to_close = None

            slug = (city or "").lower().replace(" ", "-")
            peak_hour = CITY_PEAK_HOUR_UTC.get(slug, {}).get(now_utc.month)

            # Fetch live CLOB book for both YES and NO tokens. Gamma's bestBid lags
            # the CLOB heavily on weather markets; without this we cannot tell
            # whether the lockout "edge" is actually fillable.
            no_token_id = token_ids[1] if len(token_ids) >= 2 else None
            yes_book = await self._fetch_book_levels(token_id, n=3)
            no_book = (
                await self._fetch_book_levels(no_token_id, n=3)
                if no_token_id else {"bids": [], "asks": [], "error": "no_no_token"}
            )

            tol = 0.005  # tolerate 0.5c slippage off the implied/quoted price
            no_ask_usd_at_implied = round(sum(
                lvl["usd"] for lvl in no_book.get("asks", [])
                if lvl["price"] <= no_ask_implied + tol
            ), 2)
            yes_bid_usd_at_quoted = round(sum(
                lvl["usd"] for lvl in yes_book.get("bids", [])
                if lvl["price"] >= yes_bid_f - tol
            ), 2)
            no_taker_fillable = no_ask_usd_at_implied > 0
            mint_dump_fillable = yes_bid_usd_at_quoted > 0
            if no_taker_fillable and mint_dump_fillable:
                fill_path = "both"
            elif no_taker_fillable:
                fill_path = "no_taker_only"
            elif mint_dump_fillable:
                fill_path = "mint_dump_only"
            else:
                fill_path = "neither"

            no_ask_clob = (no_book["asks"][0]["price"] if no_book.get("asks") else None)
            yes_bid_clob = (yes_book["bids"][0]["price"] if yes_book.get("bids") else None)

            record = {
                "schema_version": 2,
                "record_type": "metar_lockout_candidate",
                "ts_utc": now_utc.isoformat(),
                "ts_s": int(now_ts),
                "city": city,
                "icao": icao,
                "token_id": token_id,
                "no_token_id": no_token_id,
                "condition_id": mkt.get("conditionId") or mkt.get("condition_id"),
                "question": question,
                "bucket_lo_c_padded": round(lo_c, 4) if lo_c is not None else None,
                "bucket_hi_c_padded": round(hi_c, 4) if hi_c is not None else None,
                "is_celsius_market": is_celsius,
                "running_max_c": round(float(running_max), 3),
                "temp_c": round(float(metar.get("temp_c") or 0.0), 3) or None,
                "last_obs_ts": metar.get("last_obs_time"),
                "yes_bid": round(yes_bid_f, 4),
                "yes_ask": round(yes_ask_f, 4) if yes_ask_f is not None else None,
                "no_ask_implied": round(no_ask_implied, 4),
                "yes_book": yes_book,
                "no_book": no_book,
                "no_ask_clob": no_ask_clob,
                "yes_bid_clob": yes_bid_clob,
                "no_ask_usd_at_implied": no_ask_usd_at_implied,
                "yes_bid_usd_at_quoted": yes_bid_usd_at_quoted,
                "fill_path": fill_path,
                "seconds_since_first_lockout": int(now_ts - first_seen),
                "seconds_to_event_close": int(seconds_to_close) if seconds_to_close is not None else None,
                "hour_utc": now_utc.hour,
                "peak_hour_utc": peak_hour,
                "month": now_utc.month,
                "end_date": end_date,
            }
            try:
                with log_path.open("a") as f:
                    f.write(json.dumps(record) + "\n")
                candidates_written += 1
            except Exception:
                logger.exception("[WA] metar_lockout write error")

        if candidates_written:
            logger.info(
                "[WA] LOCKOUT_SHADOW logged %d candidates this cycle",
                candidates_written,
            )

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
        from strategy.resolution_mapper import resolve_station, STATION_COORDS as _SC
        n_no_icao = 0
        for ev in events:
            city = _parse_city(ev.get("title", ""))
            description = ev.get("description", "") or ""

            city_lat = CITY_COORDS.get(city, (0.0, 0.0))[0] if city else 0.0
            city_lon = CITY_COORDS.get(city, (0.0, 0.0))[1] if city else 0.0
            known_city = city and city in CITY_COORDS

            if known_city:
                icao: Optional[str] = CITY_ICAO.get(city)
                station_result = resolve_station(description, city, city_lat, city_lon)
                if station_result is not None:
                    station_icao, lat, lon = station_result
                    if station_icao in _SC:
                        icao = station_icao
                else:
                    lat, lon = city_lat, city_lon
            else:
                # Dynamically discovered city: extract station directly from description
                direct = _resolve_coords_from_description(description)
                if direct is None:
                    continue
                station_icao, lat, lon = direct
                icao = station_icao if station_icao in _SC else None
                if city is None:
                    city = station_icao

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

        from datetime import datetime, timezone, timedelta as _td, date as _date

        for rec in records:
            icao = rec.get("icaoId") or rec.get("stationId", "")
            if not icao:
                continue
            obs_time = rec.get("obsTime", 0)
            # Local trading day = (utc_now + offset_h) date. This is the day the market resolves.
            _tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
            _local_dt = datetime.now(timezone.utc) + _td(hours=_tz_h)
            today_str = _local_dt.date().isoformat()
            cached = self._icao_metar_cache.setdefault(icao, {
                "running_max_c": None, "last_obs_time": 0, "prev_temp_c": None,
                "running_max_date": today_str,
            })
            if obs_time <= cached.get("last_obs_time", 0):
                continue  # not a new observation

            # Prefer the RMK T-group (0.1°C precision) over the rounded METAR temp field.
            # Format: T[s][TTT][s][TTT] — sign=0/1, exactly 3 digits = tenths of °C.
            # e.g. T02750211 → dry=+27.5°C, dew=+21.1°C.
            # SAFETY: lock to exactly 3 digits per field; sanity-range −60..+60°C.
            raw_ob = rec.get("rawOb", "")
            temp_c = None
            _t_match = __import__("re").search(
                r"\bT([01])(\d{3})(?:([01])(\d{3}))?\b", raw_ob,
            )
            if _t_match:
                _sign = -1 if _t_match.group(1) == "1" else 1
                _cand = _sign * int(_t_match.group(2)) / 10.0
                if -60.0 < _cand < 60.0:
                    temp_c = _cand
                else:
                    logger.warning(
                        "[WA] METAR T-group out-of-range icao=%s val=%.1f raw=%s",
                        rec.get("icaoId", "?"), _cand, raw_ob[:80],
                    )
            if temp_c is None:
                _fallback = rec.get("temp")
                if _fallback is not None:
                    _fallback = float(_fallback)
                    if -60.0 < _fallback < 60.0:
                        temp_c = _fallback
                    else:
                        logger.warning(
                            "[WA] METAR temp out-of-range icao=%s val=%.1f",
                            rec.get("icaoId", "?"), _fallback,
                        )
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
            sky_factor    = self._sky_factor_from_layers(rec.get("rawOb", ""))
            wind_speed_kt = rec.get("wspd")
            wind_dir_deg  = rec.get("wdir")
            dewpoint_c    = rec.get("dewp")
            obs_utc_hour  = datetime.fromtimestamp(obs_time, tz=timezone.utc).hour
            # 24h precipitation (inches → mm); AWC field "p24i"; None when not reported.
            _p24i = rec.get("p24i")
            precip_24h_mm = float(_p24i) * 25.4 if _p24i is not None else 0.0

            cached.update({
                "temp_c":        temp_c,
                "prev_temp_c":   prev_temp,
                "running_max_c": new_max,
                "sky_cover":     sky_cover,
                "sky_factor":    sky_factor,
                "wind_speed_kt": float(wind_speed_kt) if wind_speed_kt is not None else None,
                "wind_dir_deg":  (float(wind_dir_deg) if str(wind_dir_deg).replace('.','',1).isdigit() else None) if wind_dir_deg is not None else None,
                "dewpoint_c":    float(dewpoint_c)    if dewpoint_c    is not None else None,
                "utc_hour":      obs_utc_hour,
                "last_obs_time": obs_time,
                "obs_time":      obs_time,
                "precip_24h_mm": precip_24h_mm,
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

            # bucket_lo_c / bucket_hi_c are already the padded resolution-bucket
            # edges (set from _parse_outcome at entry time).
            lo = meta.get("bucket_lo_c")
            hi = meta.get("bucket_hi_c")
            lo_bound = lo
            hi_bound = hi

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

           Step 3 — bucket integration (lo, hi already include the resolution
           rounding pad from _parse_outcome — ±0.5°F for F-markets, ±0.5°C for C):
               P(bucket) = Φ((hi − μ_nowcast) / σ_nowcast)
                         − Φ((lo − μ_nowcast) / σ_nowcast)

           Exit trigger: P(bucket) < NOWCAST_EXIT_FLOOR AND best_bid ≥ SALVAGE_MIN_BID
           → aggressive taker SELL at (best_bid − 0.01) to salvage capital immediately.

        B) ORPHANED ORDER CANCELLATION — for every RESTING_MAKER entry in _positions:
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

        # ── Cleanup resolved positions ────────────────────────────────────────
        if hasattr(self.bot, "risk"):
            for _tid in list(self._positions.keys()):
                _pos = self._positions[_tid]
                if (_pos.get("status") == "FILLED"
                        and _tid not in self.bot.risk.open_positions):
                    self._close_position(_tid)

        # ── A) NOWCAST COLLAPSE EXIT ──────────────────────────────────────────
        # Applies to STRAT_1/2/3 (FILLED). STRAT_4_TAIL_SNIPER is held to maturity.
        for token_id, pos in list(self._positions.items()):
            if pos.get("status") != "FILLED":
                continue
            if pos.get("strategy_tag") == "STRAT_4_TAIL_SNIPER":
                continue
            if not hasattr(self.bot, "risk") or token_id not in self.bot.risk.open_positions:
                continue

            icao = pos.get("icao_station")
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

            lo = pos.get("lo_c")
            hi = pos.get("hi_c")
            if lo is None and hi is None:
                continue

            city = pos.get("city", "")
            slug = CITY_NAME_TO_SLUG.get(city, "")
            if slug not in VALIDATED_CITY_SLUGS:
                continue

            # Step 1: μ_nowcast
            s_f       = sky_factors.get(sky_cover, 0.60)
            rise_tbl  = CITY_REMAINING_RISE.get(slug, {}).get(month, {})
            delta_rem = rise_tbl.get(current_hour, 0.0)
            mu_nowcast = max(run_max, temp_c + delta_rem * s_f)

            # Step 2: σ_nowcast = σ_base × sqrt(t_rem / 12), floored at max(0.5×σ_base, 0.5)
            peak_hour = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
            sigma_base = CITY_SIGMA_C.get(slug, {}).get(month, SIGMA_C_DEFAULT)
            if peak_hour is not None:
                t_rem = max(0.0, float(peak_hour - current_hour))
            else:
                t_rem = 0.0  # no calibration → assume peak passed, sigma collapses to floor
            sigma_floor_exit = sigma_base
            sigma_nc = max(sigma_floor_exit, sigma_base * math.sqrt(t_rem / 12.0))

            # Step 3: P(bucket) = Φ((hi−μ)/σ) − Φ((lo−μ)/σ)
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
            # Cancel any pending intraday scalp TP sell before placing emergency exit
            if token_id in self._intraday_scalp_tp:
                try:
                    await self.bot.orders.cancel(token_id=token_id)
                except Exception:
                    pass
                del self._intraday_scalp_tp[token_id]
            try:
                await self.bot.orders.limit_sell(
                    token_id=token_id,
                    price=round(current_bid - 0.01, 4),  # taker-aggressive: cross bid
                    size=pos.shares,
                    condition_id=pos.condition_id,
                )
                self._close_position(token_id)  # pop from tracker; risk manager handles PnL
            except Exception:
                logger.exception("[WA] nowcast exit sell failed %s", token_id[:12])

        # ── B) ORPHANED ORDER CANCELLATION ───────────────────────────────────
        # Cancel condition (exact): (new_fair_prob − resting_price) < EDGE_MIN
        #
        # "new_fair_prob" is a full recomputation using the current NWP ensemble
        # + METAR microclimate correction, over the exact same bucket bounds (lo_c, hi_c)
        # that triggered the original entry. This catches:
        #   - Model mean drift (e.g., a new GFS run cools the forecast by 2°C)
        #   - METAR microclimate flips (sea breeze establishes, THI disappears)
        #   - Sigma widening (convective uncertainty grows) that erodes the probability mass
        # Any of these can drop new_fair_prob below resting_price + EDGE_MIN without
        # old_fair_prob moving at all — the old proxy check was blind to all three.
        resting = {tid: p for tid, p in self._positions.items()
                   if p.get("status") == "RESTING_MAKER"}
        if not resting:
            return

        from datetime import timedelta as _td
        today    = now_utc.date().isoformat()
        tomorrow = (now_utc.date() + _td(days=1)).isoformat()

        stale_tokens = []
        for token_id, order in list(resting.items()):
            city          = order.get("city", "")
            resting_price = order.get("entry_price", 1.0)
            placed_ts     = order.get("placed_ts", 0.0)
            lo_c          = order.get("lo_c")
            hi_c          = order.get("hi_c")

            # Grace period: don't re-evaluate orders placed in the last 60s
            if time.time() - placed_ts < 60.0:
                continue

            # Cannot compute fair_prob without bucket bounds — leave the order alive
            if lo_c is None and hi_c is None:
                continue

            coords = CITY_COORDS.get(city)
            if not coords:
                continue
            lat, lon = coords

            # Re-fetch full forecast with live METAR microclimate correction baked in.
            # _get_forecast() reads self._latest_metar which was warmed by _refresh_all_metars().
            try:
                forecast = await self._get_forecast(lat, lon, today, tomorrow, city)
            except Exception:
                continue
            if not forecast:
                continue

            # Day-ahead maker orders target tomorrow's market
            forecast_entry = forecast.get(tomorrow)
            if not forecast_entry:
                continue
            new_mu, new_sigma = forecast_entry

            # Recompute fair probability over the same resolution-bucket edges
            # (lo_c, hi_c are already padded by _parse_outcome at entry):
            # new_fair_prob = Φ((hi−μ)/σ) − Φ((lo−μ)/σ)
            new_fair_prob = _outcome_prob(new_mu, lo_c, hi_c, new_sigma)

            # Edge-decay cancel condition: (new_fair_prob − resting_price) < EDGE_MIN
            # Example: resting=$0.12, new_fair=0.15 → edge=0.03 < EDGE_MIN=0.08 → CANCEL
            residual_edge = new_fair_prob - resting_price
            if residual_edge >= EDGE_MIN:
                logger.debug(
                    "[WA] ORPHAN OK %s city=%s | new_fair=%.3f resting=%.3f "
                    "edge=%.3f >= EDGE_MIN=%.2f",
                    token_id[:12], city, new_fair_prob, resting_price, residual_edge, EDGE_MIN,
                )
                continue

            logger.warning(
                "[WA] ORPHAN CANCEL %s city=%s | new_fair=%.3f resting=%.3f "
                "edge=%.3f < EDGE_MIN=%.2f (was %.3f) | after %.0fs → CANCEL",
                token_id[:12], city, new_fair_prob, resting_price,
                residual_edge, EDGE_MIN, order.get("fair_prob", 0.0),
                time.time() - placed_ts,
            )
            stale_tokens.append(token_id)
            if not DRY_RUN_LOG:
                try:
                    await self.bot.orders.cancel(token_id=token_id)
                except Exception:
                    logger.exception("[WA] orphan cancel failed %s", token_id[:12])
            else:
                logger.info("[WA] [DRY] would cancel orphan %s edge=%.3f", token_id[:12], residual_edge)

        for tid in stale_tokens:
            self._close_position(tid)
            self._fired_tokens.discard(tid)  # allow re-evaluation on next scan cycle

    def _log_intraday_skip(self, city: str, reason: str, detail: str = "") -> None:
        """Throttled INFO log for silent INTRADAY skip paths.

        Logs each (city, reason) pair at most once per 5 minutes to avoid spam.
        Detail string is included only when changed since last log.
        """
        if not hasattr(self, "_intraday_skip_throttle"):
            self._intraday_skip_throttle: dict[tuple, float] = {}
        key = (city, reason)
        now = time.time()
        last = self._intraday_skip_throttle.get(key, 0.0)
        if now - last < 300:
            return
        self._intraday_skip_throttle[key] = now
        logger.info("[WA] INTRADAY SKIP %s — %s %s", city, reason, detail)

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
        P(bucket) = Φ((hi−μ)/σ) − Φ((lo−μ)/σ)    [lo/hi already padded by _parse_outcome]

        Fires when P(bucket) >= INTRADAY_MIN_PROB regardless of whether peak has passed.
        Intraday entries use taker IOC (edge is time-sensitive — price will reprice in minutes).
        Cities without ICAO (no live METAR) are skipped — forecast-only cities use the 30-min loop.
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        today   = now_utc.date().isoformat()

        if not self._today_markets_cache:
            return

        # Clean up scalp TP entries for positions that have already closed externally
        for tid in list(self._intraday_scalp_tp):
            if tid not in self._positions:
                del self._intraday_scalp_tp[tid]

        for entry in self._today_markets_cache:
            city = entry["city"]
            icao = entry["icao"]
            mkt  = entry["mkt"]

            # Resolve live current conditions.
            # ICAO cities: use the METAR batch already in _icao_metar_cache.
            # Non-ICAO cities: call Open-Meteo /current (cloud_cover, temp_2m, wind_10m)
            #   via _refresh_open_meteo_live() which persists running_max_c between cycles.
            if icao:
                obs = self._icao_metar_cache.get(icao)
                if not obs:
                    continue
            else:
                obs = await self._refresh_open_meteo_live(entry["lat"], entry["lon"])
                if not obs:
                    continue

            temp_c      = obs.get("temp_c")
            running_max = obs.get("running_max_c")
            sky_cover   = obs.get("sky_cover", "CLR")
            if temp_c is None or running_max is None:
                continue

            slug      = CITY_NAME_TO_SLUG.get(city, "")
            if slug not in VALIDATED_CITY_SLUGS:
                continue

            # Precision gate (coarse). Real gate is p_intraday < min_p further down.
            _sigma_intra = CITY_SIGMA_C.get(slug, {}).get(now_utc.month, 1.0)
            if _sigma_intra >= INTRADAY_SIGMA_CAP:
                logger.info("[WA] INTRADAY SKIP %s — σ=%.2f ≥ INTRADAY_SIGMA_CAP=%.2f M%02d",
                            city, _sigma_intra, INTRADAY_SIGMA_CAP, now_utc.month)
                continue

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
                self._log_intraday_skip(city, "fired_token", token_id[:12])
                continue

            # City-level dedup: one INTRADAY position per city per day
            today_str = now_utc.date().isoformat()
            if any(
                p.get("city") == city and p.get("end_date", "") == today_str
                for p in self._positions.values()
            ):
                self._log_intraday_skip(city, "city_dedup", today_str)
                continue

            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            poly_yes   = float(prices[0])
            if poly_yes < 0.01 or poly_yes > INTRADAY_ASK_CAP:
                self._log_intraday_skip(city, "price_band", f"{poly_yes:.3f}")
                continue

            lo_c, hi_c, is_celsius = _parse_outcome(mkt.get("question", ""))
            if lo_c is None and hi_c is None:
                self._log_intraday_skip(city, "parse_outcome_failed", mkt.get("question", "")[:40])
                continue

            # Regime gate: volatile today → inter-model spread too wide for INTRADAY
            if _get_regime(slug, today_str) == "volatile":
                logger.info("[WA] INTRADAY SKIP %s — regime=volatile", city)
                continue

            # ── μ_nowcast via calibrated remaining-rise table ─────────────────
            # Uses _nowcast_max which implements:
            #   μ_nowcast = max(T_run, T_cur + ΔT_rem(h) × S_f)
            # For non-core cities: falls back to Open-Meteo hourly forecast rise.
            # NWP anchoring: fetch today's ensemble daily max once per city per day.
            _nwp_key = (round(lat, 2), round(lon, 2), today_str)
            if _nwp_key not in self._nwp_today_cache:
                try:
                    _fc = await self._get_forecast(lat, lon, today_str, today_str, city)
                    self._nwp_today_cache[_nwp_key] = (
                        _fc[today_str][0] if (_fc and today_str in _fc) else None
                    )
                except Exception:
                    self._nwp_today_cache[_nwp_key] = None
            nwp_max_c = self._nwp_today_cache[_nwp_key]

            try:
                est_max, nc_sigma = await self._nowcast_max(
                    lat, lon, running_max, temp_c, sky_cover, city,
                    nwp_max_c=nwp_max_c,
                )
            except Exception:
                continue

            # Hard upper-bound check: if running_max already past bucket top, skip.
            # hi_c is the padded resolution-bucket edge from _parse_outcome.
            if hi_c is not None and running_max >= hi_c:
                self._log_intraday_skip(city, "above_bucket", f"run={running_max:.1f} hi={hi_c:.1f}")
                continue

            # For non-core cities: sigma = max(model_spread, elevation_floor)
            # _nowcast_max already returns the calibrated nc_sigma; for unlisted cities
            # it returns the Open-Meteo-derived spread clamped to elevation floor.
            elev = CITY_ELEVATION_M.get(city, 0.0)
            if elev > ELEVATION_THRESHOLD_M:
                nc_sigma = max(nc_sigma, ELEVATION_SIGMA_FLOOR)

            p_intraday = _outcome_prob(est_max, lo_c, hi_c, nc_sigma)
            _min_prob = (INTRADAY_MIN_PROB_HI_PREC
                         if slug in INTRADAY_HI_PREC_CITIES
                         else INTRADAY_MIN_PROB)
            if p_intraday < _min_prob:
                self._log_intraday_skip(city, "p_below_min",
                    f"p={p_intraday:.3f}<{_min_prob} μ={est_max:.1f} σ={nc_sigma:.2f} bkt=[{lo_c},{hi_c}]")
                continue

            edge = p_intraday - poly_yes
            if edge < INTRADAY_EDGE_MIN:
                self._log_intraday_skip(city, "edge_below_min",
                    f"edge={edge:.3f}<{INTRADAY_EDGE_MIN} p={p_intraday:.3f} poly={poly_yes:.3f}")
                continue

            # Crowd divergence gate: edge > 0.40 means our model disagrees with the market
            # by more than 40pp. At that magnitude the signal is almost certainly a broken
            # model assumption (wrong μ_nowcast) rather than a genuine pricing lag.
            # Valid intraday arb is 0.06–0.40; anything above is an anomaly, not an edge.
            if edge > INTRADAY_EDGE_MAX:
                logger.info(
                    "[WA] INTRADAY SKIP %s %s — crowd divergence edge=%.3f > %.2f "
                    "(μ_nc=%.1f poly=%.3f nwp=%.1f)",
                    city, today_str, edge, INTRADAY_EDGE_MAX,
                    est_max, poly_yes, nwp_max_c if nwp_max_c is not None else float("nan"),
                )
                continue

            pre_post   = "PRE-PEAK" if (peak_hour is not None and now_utc.hour < peak_hour) else "POST-PEAK"
            source_tag = icao if icao else "OM_LIVE"
            logger.info(
                "[WA] INTRADAY %s %s %s | src=%s T_cur=%.1f T_run=%.1f "
                "μ_nc=%.1f σ=%.2f P=%.3f poly=%.3f edge=%.3f",
                pre_post, city, today, source_tag, temp_c, running_max,
                est_max, nc_sigma, p_intraday, poly_yes, edge,
            )

            bankroll  = self._get_bankroll()
            kelly_f   = edge / max(0.01, 1.0 - poly_yes)
            raw_stake = INTRADAY_STAKE_FRAC * bankroll * kelly_f
            _pos_alloc = INTRADAY_HI_POS_ALLOC if p_intraday >= INTRADAY_HI_PROB else INTRADAY_POS_ALLOC
            stake     = max(5.0, min(50.0, bankroll * _pos_alloc, raw_stake))

            if await self._enter_intraday(mkt, p_intraday, poly_yes, city, lo_c, hi_c, stake,
                                         expected_max_c=est_max):
                logger.info("[WA] INTRADAY ENTRY %s $%.1f (%s)", city, stake, pre_post)

    async def _enter_intraday(
        self, mkt: dict, fair_prob: float, poly_price: float,
        city: str, bucket_lo_c: Optional[float], bucket_hi_c: Optional[float],
        stake: float, expected_max_c: Optional[float] = None,
    ) -> bool:
        """Identical to _enter() but uses the supplied stake instead of STAKE_USD."""
        token_id = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
        icao = CITY_ICAO.get(city)
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
                _intra_meta = self.bot._open_meta.setdefault(token_id, {})
                _intra_meta["signal_source"] = f"WEATHER/{city}/STRAT_3_INTRADAY"
                _intra_meta["city"] = city
                _intra_meta["weather_question"] = mkt.get("question", "")
                _intra_meta["weather_date"] = mkt.get("endDate", "")[:10]
                self._register_position(
                    token_id, "STRAT_3_INTRADAY", icao,
                    (bucket_lo_c, bucket_hi_c), fair_prob, expected_max_c,
                    fill.avg_fill_price, city, "FILLED",
                    end_date=mkt.get("endDate", "")[:10],
                )
                # Scalp exit: resting GTC sell at fair_prob - 0.05.
                # Fires when WU publishes confirmed daily max and market reprices up.
                scalp_tp = round(fair_prob - 0.05, 4)
                if scalp_tp > fill.avg_fill_price:
                    try:
                        await self.bot.orders.limit_sell(
                            token_id=token_id,
                            price=scalp_tp,
                            size=fill.total_size,
                            condition_id=mkt.get("conditionId", ""),
                        )
                        self._intraday_scalp_tp[token_id] = scalp_tp
                        logger.info(
                            "[WA] INTRADAY SCALP TP placed %s @ %.3f (fair=%.3f fill=%.3f)",
                            city, scalp_tp, fair_prob, fill.avg_fill_price,
                        )
                    except Exception:
                        logger.exception("[WA] scalp TP placement failed %s", city)
                return True
            self._close_position(token_id)
            self._fired_tokens.discard(token_id)
            return False
        except Exception:
            self._close_position(token_id)
            self._fired_tokens.discard(token_id)
            logger.exception("[WA] intraday enter error %s", city)
            return False

    def _get_bankroll(self) -> float:
        """Current usable bankroll from the risk manager."""
        try:
            return float(self.bot.risk.bankroll.capital)
        except Exception:
            return 30.0  # conservative fallback

    async def _fetch_book_levels(
        self, token_id: str, n: int = 3
    ) -> dict:
        """
        Return top-n bid/ask levels for token. Each level is
        {price, size (shares), usd (price*size)}. On error returns empty levels
        with an 'error' field set.
        """
        url = f"{CLOB_BASE}/book?token_id={token_id}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status != 200:
                        return {"bids": [], "asks": [], "error": f"http_{resp.status}"}
                    book = await resp.json()
        except Exception as e:
            return {"bids": [], "asks": [], "error": str(e)[:80]}

        def _fmt(lvl):
            p = float(lvl.get("price", 0.0))
            s = float(lvl.get("size", 0.0))
            return {"price": round(p, 4), "size": round(s, 2), "usd": round(p * s, 2)}

        bids = sorted(book.get("bids", []), key=lambda x: -float(x.get("price", 0)))[:n]
        asks = sorted(book.get("asks", []), key=lambda x:  float(x.get("price", 1)))[:n]
        return {"bids": [_fmt(b) for b in bids], "asks": [_fmt(a) for a in asks]}

    async def _fetch_onchain_size(self, token_id: str) -> Optional[float]:
        """Query data-API for actual on-chain position size. Returns None on error."""
        wallet = getattr(self.bot, "proxy_wallet", None) or getattr(self.bot, "wallet_address", None)
        if not wallet:
            return None
        url = f"https://data-api.polymarket.com/positions?user={wallet}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    positions = await resp.json()
            for p in positions:
                if p.get("asset", "").startswith(token_id[:20]):
                    return float(p.get("size", 0))
            return 0.0  # not found = fully sold
        except Exception:
            return None

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
        Asymmetric $0.01–$0.04 tail sniper. Four triggers:

        A — RAPID_RISE:    METAR temp rose >= FOEHN_TEMP_RISE_C vs previous obs (hot)
        B — FOEHN_WIND:    dew_spread > FOEHN_DEW_SPREAD_C + wind sector match (hot)
        C — HOT_BASE_RATE: city in HOT_BUST_BASE_CITIES (>20% GFS hot-bust rate),
                           no physical trigger needed; relaxed gap to TAIL_HOT_GAP_BASE
        D — COLD_SIGNAL:   city in SIGNAL_COLD_CITIES + dew_spread < TAIL_COLD_DEW_MAX
                           + wind < TAIL_COLD_WIND_MAX → temperature likely to peak in
                           current bucket (running_max inside lo_c..hi_c)

        A/B/C → hot entry: buy bucket ABOVE running_max (existing gap logic)
        D     → cold entry: buy bucket currently containing running_max
                            (market prices it cheap expecting more rise; cold signal
                            says it will peak here instead)
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

            slug        = CITY_NAME_TO_SLUG.get(city, "")
            if slug not in VALIDATED_CITY_SLUGS:
                continue
            dew_spread  = (temp_c - dewpoint_c) if dewpoint_c is not None else None
            _c_bust_prob = 0.0   # populated by Trigger C block below; used for stake scaling

            # Trigger A (RAPID_RISE): RE-ENABLED 2026-05-21 — 6mo backtest verdict.
            # 23 cities × 180 days: n=2458, WR=23.2%, EV/bet=$27.70, PF=4.0, +$68k.
            # The original sensor-glitch concern is mitigated by two new guards:
            #   1. Hard upper bound (4°C/cycle): sensor glitches spike 3-10°C; real
            #      heating maxes at 1.5-2.5°C/cycle.
            #   2. Block firing past the city's calibrated peak hour — ramp is over.
            _peak_h_a = CITY_PEAK_HOUR_UTC.get(slug, {}).get(now_utc.month)
            _post_peak = (_peak_h_a is not None and now_utc.hour > _peak_h_a)
            _rise = (temp_c - prev_temp) if prev_temp is not None else 0.0
            trigger_a = (
                prev_temp is not None
                and _rise >= FOEHN_TEMP_RISE_C   # >= 1.5°C
                and _rise <= 4.0                  # cap sensor-glitch
                and not _post_peak
            )

            # Trigger B: classic Foehn/downslope wind signature
            sector    = FOEHN_WIND_SECTORS.get(icao)
            trigger_b = False
            if (sector and dew_spread is not None and wind_kt is not None
                    and wind_dir is not None):
                in_sector = sector[0] <= wind_dir <= sector[1]
                trigger_b = (dew_spread > FOEHN_DEW_SPREAD_C
                             and wind_kt >= FOEHN_WIND_MIN_KT
                             and in_sector)

            # Trigger C: base-rate hot bust — probability table (empirical GFS cold bias)
            # Primary: query hot_bust_rates.json for P(actual - gfs >= 1.5°C) this month.
            # Fallback (table missing): binary HOT_BUST_BASE_CITIES set.
            _bust_prob = _hbr().query(slug, now_utc.month, gap_c=HOT_BUST_TABLE_GAP_C)
            if _bust_prob >= HOT_BUST_MIN_PROB:
                trigger_c    = True
                _c_bust_prob = _bust_prob
            elif _bust_prob == 0.0:
                # Table has no data for this city/month — fall back to binary set
                _fallback_c = (
                    slug in HOT_BUST_BASE_CITIES
                    and (slug != "jakarta" or now_utc.month in HOT_BUST_JAKARTA_MONTHS)
                )
                trigger_c    = _fallback_c
                _c_bust_prob = 0.20 if _fallback_c else 0.0   # assume ~20% for fallback cities
            else:
                trigger_c    = False
                _c_bust_prob = _bust_prob

            # Trigger D (COLD_SIGNAL): DISABLED 2026-05-21 — strategic audit verdict.
            # Only 2 cities (Singapore, Jakarta), training sample size unknown.
            # Reactivate after ≥30 forward live observations confirm the direction.
            trigger_d = False

            if not (trigger_a or trigger_b or trigger_c):
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
            if lo_c is None or hi_c is None:
                continue

            # ── HOT_BASE_RATE / COLD_SIGNAL fire-once-per-day-per-city dedup ────────
            # These triggers fire on every cycle without a physical event, so without
            # dedup the bot would attempt entry every 60s. RAPID_RISE / FOEHN_WIND have
            # natural physical debouncing (the event itself is transient).
            _city_date_key = f"{city}|{today}|{lo_c:.1f}|{hi_c:.1f}"
            _is_no_event_trigger = (trigger_c or trigger_d) and not (trigger_a or trigger_b)
            if _is_no_event_trigger and _city_date_key in self._tail_base_rate_fired:
                continue

            # ── Ask anchor / market-priced check ─────────────────────────────────────
            # Capture session-open ask; if the market has already moved >50% up since
            # then, the edge is gone — market has repriced and we're chasing.
            _ask_key = f"{city}|{today}|{lo_c:.1f}|{hi_c:.1f}"
            _open_ask = self._tail_open_ask.get(_ask_key)
            if _open_ask is None:
                self._tail_open_ask[_ask_key] = ask
            elif ask > _open_ask * 1.5 and _is_no_event_trigger:
                logger.debug(
                    "[WA] TAIL SKIP %s — ask anchored %.3f → now %.3f (>50%% move), edge gone",
                    city, _open_ask, ask,
                )
                continue

            # Route by direction and validate bucket reachability
            if trigger_d and not (trigger_a or trigger_b):
                # COLD entry: running_max must be inside this bucket right now.
                # Market expects temperature to keep rising past hi_c; cold signal
                # says it will stall here. Valid only before the peak hour.
                if not (lo_c <= running_max < hi_c):
                    continue
                trigger_tag = "COLD_SIGNAL"
                gap = running_max - lo_c   # for logging: how far into the bucket we are
            else:
                # HOT entry: bucket must still be reachable from below.
                gap     = lo_c - running_max
                gap_cap = TAIL_HOT_GAP_BASE if (trigger_c and not (trigger_a or trigger_b)) else FOEHN_MAX_GAP_C
                if gap > gap_cap or gap < -1.0:
                    continue
                # Remaining-rise gate: gap must not exceed mean remaining rise at
                # this hour from the ASOS calibration table. Prevents entries near
                # or past peak hour where the target bucket is physically unreachable.
                # Post-peak: CITY_REMAINING_RISE stores mean(daily_max − T_h), which
                # is a past drop-from-peak, not future rise. Use 0 after peak_hour
                # so any positive gap is correctly rejected.
                peak_hour_m = CITY_PEAK_HOUR_UTC.get(slug, {}).get(now_utc.month)
                if peak_hour_m is not None and now_utc.hour > peak_hour_m:
                    mean_rise = 0.0
                else:
                    mean_rise = CITY_REMAINING_RISE.get(slug, {}).get(now_utc.month, {}).get(now_utc.hour, 0.0)
                if gap > mean_rise:
                    continue
                if trigger_a:
                    trigger_tag = "RAPID_RISE"
                elif trigger_b:
                    trigger_tag = "FOEHN_WIND"
                else:
                    trigger_tag = "HOT_BASE_RATE"

            # Trigger C stake scaled by bust probability (more confident = larger position).
            # Scale factor: 1.0× at HOT_BUST_STAKE_REF_PROB (20%), up to 2.0× at 40%+.
            # Physical triggers (A/B) use flat stake; C uses bust_prob-weighted stake.
            _base_stake = min(TAIL_STAKE_TOKENS * ask, self._get_bankroll() * TAIL_POS_ALLOC)
            if trigger_c and not (trigger_a or trigger_b):
                _scale = min(2.0, _c_bust_prob / max(HOT_BUST_STAKE_REF_PROB, 0.01))
                stake_usd = min(_base_stake * _scale, self._get_bankroll() * TAIL_POS_ALLOC * 2)
            else:
                stake_usd = _base_stake
            logger.info(
                "[WA] TAIL SNIPER %s icao=%s trigger=%s ask=%.3f gap=%.1f°C stake=$%.2f"
                " bust_p=%.2f dew=%.1f wind=%.1fkt",
                city, icao, trigger_tag, ask, gap, stake_usd,
                _c_bust_prob if trigger_c else 0.0,
                dew_spread if dew_spread is not None else float("nan"),
                wind_kt    if wind_kt    is not None else float("nan"),
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
                    # STRAT_4 positions are held to maturity — dynamic exit module skips them.
                    _tail_meta = self.bot._open_meta.setdefault(token_id, {})
                    _tail_meta["signal_source"] = f"WEATHER/{city}/STRAT_4/{trigger_tag}"
                    _tail_meta["city"] = city
                    _tail_meta["weather_question"] = mkt.get("question", "")
                    _tail_meta["weather_date"] = mkt.get("endDate", "")[:10]
                    self._register_position(
                        token_id, "STRAT_4_TAIL_SNIPER", icao,
                        (lo_c, hi_c), 0.0, None,
                        fill.avg_fill_price, city, "FILLED",
                        end_date=mkt.get("endDate", "")[:10],
                    )
                    logger.info("[WA] TAIL ENTRY %s %s filled=%d @ %.4f",
                                city, trigger_tag, int(fill.total_size), fill.avg_fill_price)
                    # Mark no-physical-event triggers fired-for-the-day so we don't re-enter
                    # adjacent buckets in the same city on subsequent METAR cycles.
                    if _is_no_event_trigger:
                        self._tail_base_rate_fired[_city_date_key] = trigger_tag
                else:
                    self._close_position(token_id)
                    self._fired_tokens.discard(token_id)
            except Exception:
                self._fired_tokens.discard(token_id)
                logger.exception("[WA] tail sniper entry error %s", city)

    async def _check_wu_transitions(self) -> None:
        """
        Read newly appended actual events from forecast_actuals.jsonl and match them
        against open FILLED positions.

        For each new actual (event="actual"):
          - Match on: city_slug == CITY_NAME_TO_SLUG[pos["city"]]
                  AND valid_day == pos["end_date"]   ← critical: same weather day, same market
          - If wu_high_c NOT in [lo_c, hi_c): position is a confirmed loser → sell immediately.
          - If wu_high_c IS in [lo_c, hi_c): confirmed winner → log, hold to resolution.

        Uses a byte-offset cursor (_wu_actuals_offset) so each cycle only processes new lines.
        """
        from pathlib import Path as _Path
        import json as _json
        from analysis.weather.live_accumulator import ACTUALS_FILE

        actuals_path = _Path(ACTUALS_FILE)
        if not actuals_path.exists():
            return

        new_actuals: list[dict] = []
        try:
            with actuals_path.open("rb") as fh:
                fh.seek(self._wu_actuals_offset)
                chunk = fh.read()
                self._wu_actuals_offset = actuals_path.stat().st_size
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if rec.get("event") == "actual":
                    new_actuals.append(rec)
        except Exception:
            logger.exception("[WA] WU transition check failed reading actuals file")
            return

        if not new_actuals:
            return

        for actual in new_actuals:
            city_slug  = actual.get("city_slug", "")
            valid_day  = actual.get("valid_day", "")
            wu_high_c  = actual.get("wu_high_c")
            if not city_slug or not valid_day or wu_high_c is None:
                continue

            for token_id, pos in list(self._positions.items()):
                if pos.get("status") != "FILLED":
                    continue
                pos_city = pos.get("city", "")
                pos_slug = CITY_NAME_TO_SLUG.get(pos_city, "")
                pos_date = pos.get("end_date", "")

                # Guard: only act when slug AND date match exactly.
                if pos_slug != city_slug or pos_date != valid_day:
                    continue

                lo_c = pos.get("lo_c")
                hi_c = pos.get("hi_c")
                if lo_c is None or hi_c is None:
                    continue

                in_bucket = lo_c <= wu_high_c < hi_c

                if in_bucket:
                    logger.info(
                        "[WA] WU_CONFIRMED_WINNER %s %s wu=%.1f°C bucket=[%.1f,%.1f) → hold to resolution",
                        city_slug, valid_day, wu_high_c, lo_c, hi_c,
                    )
                    continue

                # Confirmed loser — sell immediately to salvage capital.
                logger.warning(
                    "[WA] WU_CONFIRMED_LOSER %s %s wu=%.1f°C NOT in bucket=[%.1f,%.1f) → SELL NOW",
                    city_slug, valid_day, wu_high_c, lo_c, hi_c,
                )
                if DRY_RUN_LOG:
                    logger.info("[WA] [DRY] would sell loser %s", token_id[:12])
                    continue
                try:
                    risk_pos = self.bot.risk.open_positions.get(token_id)
                    if risk_pos is None:
                        self._close_position(token_id)
                        continue
                    current_bid = getattr(risk_pos, "current_price", 0.0) or 0.0
                    sell_price  = round(max(0.01, current_bid - 0.01), 4)
                    await self.bot.orders.limit_sell(
                        token_id=token_id,
                        price=sell_price,
                        size=risk_pos.shares,
                        condition_id=risk_pos.condition_id,
                    )
                    self._close_position(token_id)
                    logger.info(
                        "[WA] WU_EXIT sold %s @ %.4f (bid was %.4f)",
                        token_id[:12], sell_price, current_bid,
                    )
                except Exception:
                    logger.exception("[WA] WU_EXIT sell failed %s", token_id[:12])

        # After processing all new actuals, run upstream oracle check.
        if new_actuals:
            for actual in new_actuals:
                cs = actual.get("city_slug", "")
                vd = actual.get("valid_day", "")
                wh = actual.get("wu_high_c")
                if cs and vd and wh is not None:
                    month = int(vd[5:7]) if vd else 0
                    if month:
                        try:
                            await self._upstream_oracle_check(cs, vd, wh, month)
                        except Exception:
                            logger.exception("[Oracle] check failed for %s %s", cs, vd)

    async def _oracle_metar_check(self) -> None:
        """
        METAR-driven upstream oracle trigger (replaces WU-actuals path).

        After a city's peak hour has passed, running_max_c from the METAR cache
        IS the confirmed daily maximum — same signal, 2-4h earlier than WU publication.

        Fires once per city per calendar day (deduped by _oracle_fired_dates).
        Only considers cities with a calibrated CITY_PEAK_HOUR_UTC entry + ICAO.
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        today   = now_utc.date().isoformat()
        month   = now_utc.month

        for city_name, icao in CITY_ICAO.items():
            slug = CITY_NAME_TO_SLUG.get(city_name, "")
            if not slug:
                continue
            dedup_key = f"{slug}|{today}"
            if dedup_key in self._oracle_fired_dates:
                continue

            peak_h = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
            if peak_h is None:
                continue
            # Only fire after peak hour has passed (plus 1h buffer for temp to plateau)
            if now_utc.hour < peak_h + 1:
                continue

            obs = self._icao_metar_cache.get(icao)
            if not obs:
                continue
            running_max = obs.get("running_max_c")
            if running_max is None:
                continue

            # Mark as checked regardless of whether oracle fires, to avoid per-cycle spam
            self._oracle_fired_dates.add(dedup_key)

            try:
                await self._upstream_oracle_check(slug, today, running_max, month)
            except Exception:
                logger.exception("[Oracle] metar check failed for %s", slug)

    async def _upstream_oracle_check(
        self, city_slug: str, valid_day: str, wu_high_c: float, month: int
    ) -> None:
        """
        Called after each confirmed WU actual.  If upstream anomaly detected and synoptic
        coherence passes, enters tomorrow's markets for downstream cities.
        """
        import strategy.upstream_oracle as _oracle
        from strategy.resolution_mapper import STATION_COORDS as _SC

        _oracle.notify_actual(city_slug, valid_day, wu_high_c)
        targets = _oracle.check_upstream_signal(city_slug, valid_day, wu_high_c, month)
        if not targets:
            return

        tomorrow = (date.fromisoformat(valid_day) + timedelta(days=1)).isoformat()
        logger.info("[Oracle] upstream %s z→%.2f — scanning %d downstream cities for %s",
                    city_slug, targets[0]["z"], len(targets), tomorrow)

        events = await self._fetch_weather_events()
        # Build city→markets index for tomorrow
        tomorrow_mkts: dict[str, list[dict]] = {}
        for ev in events:
            city_name = _parse_city(ev.get("title", ""))
            if not city_name:
                continue
            ds_slug = CITY_NAME_TO_SLUG.get(city_name, "")
            if not ds_slug:
                continue
            for mkt in ev.get("markets", []):
                if mkt.get("endDate", "")[:10] != tomorrow:
                    continue
                if mkt.get("closed", False):
                    continue
                if not _parse_token_ids(mkt.get("clobTokenIds", [])):
                    continue
                tomorrow_mkts.setdefault(ds_slug, []).append(mkt)

        for target in targets:
            ds_slug     = target["city_slug"]
            direction   = target["direction"]
            trigger_z   = target["z"]
            ds_mkts     = tomorrow_mkts.get(ds_slug, [])
            if not ds_mkts:
                logger.debug("[Oracle] no tomorrow markets found for %s", ds_slug)
                continue

            # Resolve city name for _enter()
            ds_city = next(
                (c for c, s in CITY_NAME_TO_SLUG.items() if s == ds_slug), ds_slug
            )

            best_mkt    = None
            best_prob   = 0.0
            best_ask    = 1.0
            best_edge   = 0.0
            best_lo_c   = None
            best_hi_c   = None

            for mkt in ds_mkts:
                question = mkt.get("question", "")
                lo_c, hi_c, _ = _parse_outcome(question)

                # Direction gate: hot → only buy high buckets; cold → only buy low buckets
                clim_cell = _oracle._load_clim().get(ds_slug, {}).get(str(month))
                if not clim_cell:
                    continue
                ds_mean = clim_cell["mean_max_c"]
                if direction == "hot" and lo_c is not None and lo_c < ds_mean:
                    continue   # this bucket is below average — not the anomaly bucket
                if direction == "cold" and hi_c is not None and hi_c > ds_mean:
                    continue   # this bucket is above average — not the anomaly bucket

                fair_prob = _oracle.estimate_downstream_bucket_prob(
                    trigger_z, direction, ds_slug, month, lo_c, hi_c
                )
                if fair_prob is None or fair_prob < DOWNSTREAM_FAIR_FLOOR:
                    continue

                # Get current ask from CLOB
                token_id = _parse_token_ids(mkt.get("clobTokenIds", []))[0]
                if token_id in self._fired_tokens:
                    continue

                try:
                    _, poly_ask, _, _ = await self._fetch_book_and_vwap(token_id, KELLY_MIN_USD)
                except Exception:
                    continue

                if poly_ask > DOWNSTREAM_ASK_CAP:
                    logger.debug("[Oracle] %s bucket=[%.1f,%.1f) ask=%.3f > cap %.2f — skip",
                                 ds_slug, lo_c or -99, hi_c or 99, poly_ask, DOWNSTREAM_ASK_CAP)
                    continue

                edge = fair_prob - poly_ask
                if edge < DOWNSTREAM_EDGE_MIN:
                    continue

                if edge > best_edge:
                    best_mkt  = mkt
                    best_prob = fair_prob
                    best_ask  = poly_ask
                    best_edge = edge
                    best_lo_c = lo_c
                    best_hi_c = hi_c

            if best_mkt is None:
                logger.debug("[Oracle] %s — no qualifying bucket (direction=%s)", ds_slug, direction)
                continue

            stake = self._kelly_stake(best_prob, best_ask, OVERNIGHT_POS_ALLOC)
            logger.info(
                "[Oracle] SIGNAL trigger=%s→%s dir=%s fair=%.3f ask=%.3f edge=%.3f stake=$%.1f%s",
                city_slug, ds_slug, direction, best_prob, best_ask, best_edge, stake,
                " [SHADOW]" if not UPSTREAM_ORACLE_ENABLED else "",
            )
            if not UPSTREAM_ORACLE_ENABLED:
                continue
            await self._enter(
                best_mkt, best_prob, best_ask,
                ds_city,
                bucket_lo_c=best_lo_c, bucket_hi_c=best_hi_c,
                stake=stake,
                strategy_tag="STRAT_5_UPSTREAM",
            )

    def _select_bracket(
        self, candidates: list[tuple[dict, dict]]
    ) -> Optional[list[tuple[dict, dict]]]:
        """
        Temperature ladder: find best bracket of ≤ BRACKET_MAX_BUCKETS adjacent tail buckets.

        Guards:
          combined_fair ≥ BRACKET_COMBINED_FAIR_MIN  (overall conviction)
          combined_ask  < BRACKET_COST_CAP            (total cost cap)
          combined_edge ≥ EDGE_MIN                    (net positive EV)

        Deliberately does NOT require each bucket to individually clear MIN_FAIR_PROB —
        that is the exact wrong gate for ladder mode. Each leg is a cheap mispriced tail;
        combined probability is what matters.

        Math: EV = Σ(P_i × payout_i) − total_cost; mutual exclusivity makes this additive.
        """
        ranked = sorted(candidates, key=lambda x: x[1]["fair_prob"], reverse=True)
        n = min(BRACKET_MAX_BUCKETS, len(ranked))

        for size in range(n, 1, -1):  # try largest bracket first
            subset = ranked[:size]
            combined_ask  = sum(e["poly_price"] for _, e in subset)
            combined_fair = sum(e["fair_prob"]  for _, e in subset)
            combined_edge = combined_fair - combined_ask

            if combined_fair < BRACKET_COMBINED_FAIR_MIN:
                continue
            if combined_ask >= BRACKET_COST_CAP:
                continue
            if combined_edge < EDGE_MIN:
                continue

            logger.info(
                "[WA] LADDER selected size=%d combined_fair=%.3f combined_ask=%.3f edge=%.3f%s",
                size, combined_fair, combined_ask, combined_edge,
                " [SHADOW]" if not BRACKET_ENABLED else "",
            )
            return subset

        return None

    async def _enter_bracket(
        self, bracket: list[tuple[dict, dict]], city: str
    ) -> int:
        """
        Enter all buckets in the bracket with proportional Kelly sizing.
        In shadow mode (BRACKET_SHADOW and not BRACKET_ENABLED): log only, no fills.

        Per-bucket stake allocation:
          f* = combined_edge / (1 − combined_cost)     [combined Kelly fraction]
          stake_i = f* × bankroll × KELLY_FRACTION × (q_i / Σ q_j)

        Returns number of successfully entered positions (0 in shadow mode).
        """
        combined_ask  = sum(e["poly_price"] for _, e in bracket)
        combined_fair = sum(e["fair_prob"]  for _, e in bracket)
        combined_edge = combined_fair - combined_ask

        f_star = combined_edge / max(0.001, 1.0 - combined_ask)
        bankroll = self._get_bankroll()
        total_kelly_stake = KELLY_FRACTION * bankroll * f_star
        # Cap total bracket spend at BRACKET_ALLOC of bankroll (not per-position).
        # Use $2/leg floor (not KELLY_MIN_USD=$5) so the bankroll cap isn't overridden.
        bracket_min = 2.0 * len(bracket)
        total_kelly_stake = max(bracket_min,
                                min(KELLY_MAX_USD * len(bracket),
                                    bankroll * BRACKET_ALLOC,
                                    total_kelly_stake))

        shadow = not BRACKET_ENABLED
        shadow_legs: list[dict] = []  # populated only in shadow mode

        n_entered = 0
        for mkt, entry in bracket:
            w_i = entry["fair_prob"] / combined_fair
            stake_i = max(2.0, min(KELLY_MAX_USD, total_kelly_stake * w_i))
            if shadow:
                logger.info(
                    "[WA] LADDER SHADOW city=%s poly=%.3f fair=%.3f edge=%.3f "
                    "stake=$%.1f combined_fair=%.3f combined_ask=%.3f q=%s",
                    city, entry["poly_price"], entry["fair_prob"], entry["edge"],
                    stake_i, combined_fair, combined_ask,
                    (entry.get("question") or "")[:60],
                )
                # Fetch live YES-side CLOB book for fillability analysis. The
                # bot.log message above carries the gamma-derived plan; we also
                # need to know whether the leg's stake can actually be taken at
                # the quoted poly_price.
                token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
                yes_tok = token_ids[0] if token_ids else None
                yes_book = (
                    await self._fetch_book_levels(yes_tok, n=3)
                    if yes_tok else {"bids": [], "asks": [], "error": "no_token"}
                )
                tol = 0.005
                ask_usd_at_quoted = round(sum(
                    lvl["usd"] for lvl in yes_book.get("asks", [])
                    if lvl["price"] <= entry["poly_price"] + tol
                ), 2)
                yes_ask_clob = (
                    yes_book["asks"][0]["price"] if yes_book.get("asks") else None
                )
                shadow_legs.append({
                    "token_id": yes_tok,
                    "condition_id": mkt.get("conditionId") or mkt.get("condition_id"),
                    "question": (entry.get("question") or "")[:120],
                    "lo_c": entry.get("lo_c"),
                    "hi_c": entry.get("hi_c"),
                    "expected_max_c": entry.get("expected_max_c"),
                    "poly_price": round(entry["poly_price"], 4),
                    "fair_prob": round(entry["fair_prob"], 4),
                    "edge": round(entry["edge"], 4),
                    "stake_planned_usd": round(stake_i, 2),
                    "yes_ask_clob": yes_ask_clob,
                    "yes_book": yes_book,
                    "ask_usd_at_quoted": ask_usd_at_quoted,
                    "fillable_at_stake": ask_usd_at_quoted >= stake_i,
                    "fillable_any": ask_usd_at_quoted > 0,
                })
            else:
                logger.info(
                    "[WA] LADDER LEG %s poly=%.3f fair=%.3f stake=$%.1f",
                    city, entry["poly_price"], entry["fair_prob"], stake_i,
                )
                entered = await self._enter(
                    mkt, entry["fair_prob"], entry["poly_price"],
                    city, entry.get("lo_c"), entry.get("hi_c"),
                    stake=stake_i,
                    strategy_tag="STRAT_2_BRACKET",
                    expected_max_c=entry.get("expected_max_c"),
                )
                if entered:
                    n_entered += 1

        if shadow and shadow_legs:
            from datetime import datetime, timezone
            from pathlib import Path
            import time as _time
            now_utc = datetime.now(timezone.utc)
            log_dir = Path("logs/shadow/hot") / now_utc.date().isoformat()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "ladder.jsonl"
            record = {
                "schema_version": 1,
                "record_type": "ladder_shadow",
                "ts_utc": now_utc.isoformat(),
                "ts_s": int(_time.time()),
                "city": city,
                "n_legs": len(shadow_legs),
                "combined_fair": round(combined_fair, 4),
                "combined_ask": round(combined_ask, 4),
                "combined_edge": round(combined_edge, 4),
                "f_star_kelly": round(f_star, 4),
                "total_planned_stake_usd": round(total_kelly_stake, 2),
                "bankroll": round(bankroll, 2),
                "all_legs_fillable_at_stake": all(L["fillable_at_stake"] for L in shadow_legs),
                "any_leg_fillable": any(L["fillable_any"] for L in shadow_legs),
                "min_ask_usd_at_quoted": min(L["ask_usd_at_quoted"] for L in shadow_legs),
                "legs": shadow_legs,
            }
            try:
                with log_path.open("a") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception:
                logger.exception("[WA] ladder shadow JSONL write error")

        return n_entered

    def _kelly_stake(self, edge: float, ask: float, strat_alloc: float = PER_STRAT_ALLOC) -> float:
        """
        Fee-adjusted fractional Kelly stake in USD.

        Taker fee r means effective entry cost = ask × (1 + r).
        f* = (fair - ask×(1+r)) / (1 - ask×(1+r))
           = fee_adj_edge / (1 - p_eff)

        where edge already equals (fair - ask), so:
        fee_adj_edge = edge - ask × r

        Clamped to [KELLY_MIN_USD, KELLY_MAX_USD].
        Falls back to STAKE_USD if Kelly is disabled or ask >= 1.0.
        """
        if not KELLY_ENABLED or ask >= 1.0:
            return STAKE_USD
        fee_adj_edge = edge - ask * TAKER_FEE_RATE
        p_eff = ask * (1.0 + TAKER_FEE_RATE)
        f_star = fee_adj_edge / max(0.001, 1.0 - p_eff)
        bankroll = self._get_bankroll()
        raw = KELLY_FRACTION * bankroll * f_star
        return max(KELLY_MIN_USD, min(KELLY_MAX_USD, bankroll * strat_alloc, raw))

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

    @staticmethod
    def _sky_factor_from_layers(raw_ob: str) -> float:
        """
        Compute sky_factor from METAR raw string with cirrus altitude correction.

        BKN/OVC layers at altitude >= CIRRUS_ALT_CODE (200 = 20,000 ft) are high
        cirrus that transmit most solar radiation; they are reclassified as SCT (0.60)
        instead of BKN (0.30) or OVC (0.08).

        Returns the minimum sky_factor across all parsed layers:
          CLR/SKC (no groups) → 1.00
          FEW → 0.85, SCT → 0.60, BKN → 0.30, OVC → 0.08
        """
        import re as _re
        FACTORS = {"FEW": 0.85, "SCT": 0.60, "BKN": 0.30, "OVC": 0.08}
        worst = 1.0
        for m in _re.finditer(r'\b(FEW|SCT|BKN|OVC)(\d{3})(?:TCU|CB)?\b', raw_ob):
            code = m.group(1)
            alt  = int(m.group(2))
            if code in ("BKN", "OVC") and alt >= CIRRUS_ALT_CODE:
                code = "SCT"   # high cirrus: transmits radiation like SCT
            f = FACTORS[code]
            if f < worst:
                worst = f
        return worst

    async def _refresh_open_meteo_live(self, lat: float, lon: float) -> Optional[dict]:
        """
        Fetch current conditions from Open-Meteo for cities without an ICAO METAR station.

        Endpoint: /v1/forecast?current=temperature_2m,cloud_cover,wind_speed_10m
        Returns a dict compatible with _icao_metar_cache entries so the rest of the
        intraday scan pipeline (nowcast, probability calc) works identically.

        running_max_c persists across calls via _om_live_cache (keyed by rounded coords).
        Cloud cover → sky_cover mapping:
          0–10%  → CLR (S_f = 1.00)
          11–25% → FEW (S_f = 0.85)
          26–50% → SCT (S_f = 0.60)
          51–84% → BKN (S_f = 0.30)
          85–100%→ OVC (S_f = 0.08)
        """
        from datetime import datetime, timezone, date as _date
        key = (round(lat, 2), round(lon, 2))
        today_str = _date.today().isoformat()

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            f"&current=temperature_2m,cloud_cover,wind_speed_10m"
            f"&temperature_unit=celsius&wind_speed_unit=kn"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception as e:
            logger.debug("[WA] OM_LIVE fetch error lat=%.2f lon=%.2f: %s", lat, lon, e)
            return None

        current = data.get("current", {})
        temp_c      = current.get("temperature_2m")
        cloud_pct   = current.get("cloud_cover", 0)
        wind_kt     = current.get("wind_speed_10m")
        obs_ts      = current.get("time", "")  # ISO string e.g. "2026-05-20T14:00"

        if temp_c is None:
            return None
        temp_c = float(temp_c)

        # Cloud cover → sky_cover
        cloud_pct = int(cloud_pct or 0)
        if cloud_pct <= 10:
            sky_cover = "CLR"
        elif cloud_pct <= 25:
            sky_cover = "FEW"
        elif cloud_pct <= 50:
            sky_cover = "SCT"
        elif cloud_pct <= 84:
            sky_cover = "BKN"
        else:
            sky_cover = "OVC"

        # Persist running_max_c; reset at midnight
        cached = self._om_live_cache.setdefault(key, {
            "running_max_c": None, "running_max_date": today_str, "prev_temp_c": None,
        })
        if cached.get("running_max_date") != today_str:
            cached["running_max_c"] = None
            cached["running_max_date"] = today_str

        prev_max = cached.get("running_max_c")
        new_max  = temp_c if (prev_max is None or temp_c > prev_max) else prev_max

        # Parse approximate UTC hour from the obs_ts string
        try:
            obs_utc_hour = int(obs_ts[11:13])
        except Exception:
            obs_utc_hour = datetime.now(timezone.utc).hour

        cached.update({
            "temp_c":        temp_c,
            "prev_temp_c":   cached.get("temp_c"),
            "running_max_c": new_max,
            "sky_cover":     sky_cover,
            "wind_speed_kt": float(wind_kt) if wind_kt is not None else None,
            "utc_hour":      obs_utc_hour,
            "cloud_pct":     cloud_pct,
        })
        return cached

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

    @staticmethod
    def _compute_nowcast_mu_sigma(
        mean_rise: float,
        temp_c: float,
        running_max_c: float,
        sky_factor: float,
        cal_sigma: float,
        hours_to_peak: float,
        nwp_max_c: Optional[float] = None,
        heat_ramp_h: float = float(INTRADAY_HEAT_RAMP_H),
        precip_penalty_c: float = 0.0,
    ) -> tuple[float, float]:
        """
        Pure math core for the intraday nowcast. Separated for testability.

        mu:
          METAR extrapolation: mu_metar = max(T_run, T_cur + mean_rise × sky_factor − penalty)
          NWP anchoring (when nwp_max_c supplied):
            w1 = clamp(1 − (h/ramp_h) × (1 − W1_MIN), W1_MIN, 1.0)
            mu = w1 × mu_metar + (1−w1) × (nwp_max_c − penalty)
          Near or past peak (h=0): w1=1.0 → METAR observed max is the truth.
          At window open (h=ramp_h): w1=W1_MIN → NWP carries (1−W1_MIN) weight.

        sigma:
          std_RR = mean_rise × RR_CV  (proxy for historical spread of remaining rise)
          sigma  = max(cal_sigma, std_RR × sqrt(h / 12))
          When mean_rise → 0 or h → 0: sigma collapses to cal_sigma (ASOS floor).
          When mean_rise is large (early morning, large projection): sigma expands,
          flattening the Gaussian and suppressing P(exact bucket).

        precip_penalty_c:
          Latent heat evaporation penalty. Subtracted from both mu_metar projection
          and nwp_max_c before the blend. Running max provides the hard floor so the
          penalty cannot push mu below already-observed temperature.
        """
        h = max(0.0, hours_to_peak)

        # mu (with latent heat evaporation penalty applied to the rising component)
        mu_metar = max(running_max_c, temp_c + mean_rise * sky_factor - precip_penalty_c)
        if nwp_max_c is not None and h > 0 and heat_ramp_h > 0:
            w1 = 1.0 - (h / heat_ramp_h) * (1.0 - INTRADAY_W1_MIN)
            w1 = max(INTRADAY_W1_MIN, min(1.0, w1))
            nwp_adj = nwp_max_c - precip_penalty_c
            mu_nowcast = w1 * mu_metar + (1.0 - w1) * nwp_adj
        else:
            mu_nowcast = mu_metar

        # sigma
        std_rr = mean_rise * RR_CV
        sigma_dynamic = std_rr * math.sqrt(h / 12.0) if h > 0 else 0.0
        sigma_nowcast = max(cal_sigma, sigma_dynamic)

        return round(mu_nowcast, 2), round(sigma_nowcast, 2)

    async def _log_met_adjustment(self, record: dict) -> None:
        """Append one met-adjustment shadow record to logs/shadow/met_adjustments.jsonl.

        Called via asyncio.create_task() — runs concurrently with no latency on the
        critical decision path. File I/O delegated to thread-pool via run_in_executor.
        """
        from pathlib import Path as _Path

        def _write(path: str, line: str) -> None:
            with open(path, "a") as fh:
                fh.write(line)

        log_path = _Path("logs/shadow/met_adjustments.jsonl")
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record) + "\n"
            await asyncio.get_event_loop().run_in_executor(None, _write, str(log_path), line)
        except Exception as e:
            logger.debug("[WA] met shadow log error: %s", e)

    async def _nowcast_max(
        self, lat: float, lon: float,
        running_max_c: float, temp_c: float, sky_cover: str,
        city: str = "", nwp_max_c: Optional[float] = None,
    ) -> tuple[float, float]:
        """
        Estimate final daily max given current observed conditions.

        For the 7 calibrated stations: uses 5yr ASOS per-city/month/hour remaining_rise
        tables scaled by sky_factor, with calibrated residual sigma that shrinks to floor
        as observation hour approaches historical peak hour.

        For other cities: falls back to hourly Open-Meteo forecast rise × sky_factor.

        Three live meteorological corrections (shadow-logged when active):
          1. Cirrus dampening: BKN/OVC at ≥20k ft → sky_factor reclassified to SCT=0.60
          2. Marine sea-breeze: onshore flow → mean_rise × max(0.1, 1−spd/25) [wind-scaled]
          3. Latent heat penalty: precip_24h_mm → max(0, mm*0.15−0.5)°C [linear scaler]

        Delegates mu/sigma math to _compute_nowcast_mu_sigma().
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        month = now_utc.month

        # Pull pre-computed fields from METAR cache (populated by _refresh_all_metars).
        icao = CITY_ICAO.get(city, "")
        obs_cache = self._icao_metar_cache.get(icao, {}) if icao else {}

        # ── Rule 1: Cirrus cloud height dampening ─────────────────────────────────
        # f_sky_raw = string-lookup baseline (what old code would use)
        _sky_factors_str = {"CLR": 1.0, "FEW": 0.85, "SCT": 0.60, "BKN": 0.30, "OVC": 0.08}
        f_sky_raw = _sky_factors_str.get(sky_cover, 0.60)
        cached_sky_factor = obs_cache.get("sky_factor")
        f_sky = cached_sky_factor if cached_sky_factor is not None else f_sky_raw
        cirrus_active = cached_sky_factor is not None and round(cached_sky_factor, 3) != round(f_sky_raw, 3)

        # ── Rule 2: Latent heat evaporation penalty (linear scaler) ──────────────
        # Penalty = max(0, mm*0.15 − 0.5): zero below ~3.3 mm, ramps to 0.25°C at 5 mm,
        # 1.0°C at 10 mm. Replaces the binary 0.75°C threshold.
        precip_24h_mm = obs_cache.get("precip_24h_mm", 0.0) or 0.0
        precip_penalty_c = max(0.0, precip_24h_mm * 0.15 - 0.5)

        slug = CITY_NAME_TO_SLUG.get(city, "")
        cal_rise_table = CITY_REMAINING_RISE.get(slug, {}).get(month)
        cal_peak_hour  = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
        cal_sigma      = CITY_SIGMA_C.get(slug, {}).get(month, 1.2)

        if cal_rise_table is not None and cal_peak_hour is not None:
            mean_rise = cal_rise_table.get(current_hour, 0.0)
            peak_hour = cal_peak_hour
        else:
            # Fallback: Open-Meteo hourly forecast rise
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
            mean_rise = max(0.0, fcst_peak - fcst_now)
            cal_sigma = 1.2

        mean_rise_raw = mean_rise

        # ── Rule 3: Marine sea-breeze floor (wind-speed-scaled multiplier) ────────
        # multiplier = max(0.1, 1 − wind_speed/25):
        #   5 kt → 0.80, 12.5 kt → 0.50, 20 kt → 0.20, ≥25 kt → 0.10 (floor)
        marine_active   = False
        marine_mult     = 1.0
        wind_speed_kt_v = obs_cache.get("wind_speed_kt") or 0.0
        wind_dir_v      = obs_cache.get("wind_dir_deg")
        if icao in MARINE_WIND_SECTORS and wind_dir_v is not None:
            lo_sec, hi_sec = MARINE_WIND_SECTORS[icao]
            in_marine = (lo_sec <= wind_dir_v <= hi_sec) if lo_sec <= hi_sec else (
                wind_dir_v >= lo_sec or wind_dir_v <= hi_sec
            )
            if in_marine:
                marine_mult = max(0.1, 1.0 - (wind_speed_kt_v / 25.0))
                mean_rise  *= marine_mult
                marine_active = True
                logger.debug(
                    "[WA] marine flow %s wind_dir=%.0f° spd=%.0fkt mult=%.2f "
                    "mean_rise %.2f→%.2f°C",
                    icao, wind_dir_v, wind_speed_kt_v, marine_mult,
                    mean_rise_raw, mean_rise,
                )

        hours_to_peak = max(0.0, peak_hour - current_hour)
        mu_final, sigma = self._compute_nowcast_mu_sigma(
            mean_rise=mean_rise,
            temp_c=temp_c,
            running_max_c=running_max_c,
            sky_factor=f_sky,
            cal_sigma=cal_sigma,
            hours_to_peak=hours_to_peak,
            nwp_max_c=nwp_max_c,
            precip_penalty_c=precip_penalty_c,
        )

        # ── Shadow log: fire-and-forget when any rule was active ─────────────────
        if marine_active or cirrus_active or precip_penalty_c > 0.0:
            mu_baseline, _ = self._compute_nowcast_mu_sigma(
                mean_rise=mean_rise_raw,
                temp_c=temp_c,
                running_max_c=running_max_c,
                sky_factor=f_sky_raw,
                cal_sigma=cal_sigma,
                hours_to_peak=hours_to_peak,
                nwp_max_c=nwp_max_c,
                precip_penalty_c=0.0,
            )
            shadow = {
                "ts":   now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "city": city,
                "icao": icao or None,
                "marine": {
                    "active":        marine_active,
                    "wind_dir_deg":  round(wind_dir_v, 1) if wind_dir_v is not None else None,
                    "wind_speed_kt": round(wind_speed_kt_v, 1),
                    "multiplier":    round(marine_mult, 3),
                    "mean_rise_raw": round(mean_rise_raw, 3),
                    "mean_rise_adj": round(mean_rise, 3),
                } if marine_active else {"active": False},
                "cirrus": {
                    "active":    cirrus_active,
                    "f_sky_raw": round(f_sky_raw, 2),
                    "f_sky_adj": round(f_sky, 2),
                } if cirrus_active else {"active": False},
                "latent_heat": {
                    "active":        precip_penalty_c > 0.0,
                    "precip_24h_mm": round(precip_24h_mm, 1),
                    "penalty_c":     round(precip_penalty_c, 3),
                } if precip_penalty_c > 0.0 else {"active": False},
                "mu_baseline":  mu_baseline,
                "mu_final":     mu_final,
                "total_delta":  round(mu_final - mu_baseline, 3),
            }
            try:
                asyncio.create_task(self._log_met_adjustment(shadow))
            except RuntimeError:
                pass  # no running event loop (test / offline context)

        return mu_final, sigma

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
        """
        Fetch ALL open weather events from Gamma API with pagination.
        Walks pages until an empty page is returned (offset increments by 100).
        API hard-caps at 100 per page; requesting 200 still returns 100, which
        previously triggered the "partial page = last page" break after offset 0.
        This ensures newly opened cities are discovered automatically without code changes.
        """
        events: list[dict] = []
        offset = 0
        limit  = 100
        try:
            async with aiohttp.ClientSession() as sess:
                while True:
                    url = (f"{GAMMA_BASE}/events?closed=false&limit={limit}"
                           f"&offset={offset}&tag_slug=weather")
                    async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            break
                        page: list[dict] = await resp.json()
                    if not page:
                        break
                    events.extend(page)
                    if len(page) < limit:
                        break   # last partial page — no more data
                    offset += len(page)
        except Exception as e:
            logger.debug("[WA] events fetch error: %s", e)
        logger.debug("[WA] fetched %d weather events (paginated)", len(events))
        return events

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
                elev = CITY_ELEVATION_M.get(city, 0.0)   # defined always — used by elev_tag below
                cal_sigma = CITY_SIGMA_C.get(_slug, {}).get(_month)
                if cal_sigma is None:
                    cal_sigma = ELEVATION_SIGMA_FLOOR if elev > ELEVATION_THRESHOLD_M else 1.0
                # Defense against σ collapse: when fewer than MIN_MODELS_FOR_ENTRY models
                # respond, the ensemble spread is structurally underestimated. Either skip
                # the day or inflate σ — choose inflation to preserve trading but reduce risk.
                _n_models = len(model_values_by_name)
                mean, sigma = self._ensemble.combine(
                    _slug, _month, model_values_by_name,
                    asos_sigma_floor=cal_sigma,
                )
                if _n_models < MIN_MODELS_FOR_ENTRY:
                    sigma *= LOW_MODEL_SIGMA_INFLATION
                    logger.warning(
                        "[WA] LOW_MODEL_COUNT %s %s: n=%d < %d → σ inflated %.2f→%.2f",
                        city, d, _n_models, MIN_MODELS_FOR_ENTRY,
                        sigma / LOW_MODEL_SIGMA_INFLATION, sigma,
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
                # Live calibration accumulator: log raw model values + ensemble output
                if _slug:
                    try:
                        from analysis.weather.live_accumulator import log_forecast as _lf
                        _lf(
                            slug=f"weather-forecast-{_slug}-{d}",
                            city_slug=_slug,
                            valid_day=d,
                            model_values=model_values_by_name,
                            ensemble_mu=mean,
                            ensemble_sigma=sigma,
                        )
                    except Exception:
                        pass
            return result if result else None
        except Exception as e:
            logger.debug("[WA] forecast error lat=%.2f lon=%.2f: %s", lat, lon, e)
            return None
