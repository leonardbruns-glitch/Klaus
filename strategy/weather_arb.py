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
from pathlib import Path
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
MIN_FAIR_PROB = 0.40   # minimum fair probability for the best bucket (raised 2026-05-26: 0/9 WR below ask<0.15)
ASK_BAND_LO  = 0.15    # min entry price — cheap-tail 0/9 WR, market correctly priced those
ASK_BAND_HI  = 0.29    # max entry price — OVERRIDE with BRACKET_ENABLED for high-price entries

# ── NegRisk Bracketing / Temperature Ladder ──────────────────────────────────
# SHADOW mode (2026-05-23): log ladder signals without entering.
# Ladder = buy 2-3 adjacent cheap tail buckets simultaneously on wide-sigma cities.
# Edge: each tail bucket individually mispriced (fair > ask+0.08) but none clears
# MIN_FAIR_PROB=0.45 alone. Combined fair 55-90%; combined cost 0.15-0.45.
# Live entry gated by BRACKET_ENABLED. Shadow validation target: n≥30 signals,
# combined hit rate within ±0.10 of combined_fair_prob before flipping live.
STWA_LIVE                = True  # 2026-06-05 re-deployed with band guardrails (ask-floor/EV-cap/interior/post-peak/depth)   # True → live entries from Kalman engine; False → shadow only
STWA_NO_SWEEP_EV_FLOOR   = 0.05  # favorite-longshot NO deep-sweep: walk the book up to (p_win − this); keeps ≥5pt edge after slippage
STWA_RESOLUTION_POLL_SEC = 300    # how often to poll Gamma to settle held-to-resolution STWA positions
# Held-to-resolution weather classes the poller settles. WEATHER_M1_PROBE (the live
# LOCKOUT-NO edge, ~98% WR OOS-confirmed) also holds to resolution and only TP-closes
# at bid>=0.999, so positions that never reach TP must be settled here or their (mostly
# winning) PnL never banks — the same write-only gap STWA had.
_STWA_RESOLVE_CLASSES = ("WEATHER_STWA", "WEATHER_M1_PROBE", "WEATHER_FADE", "WEATHER_OFI", "WEATHER_FAVYES", "WEATHER_THERMO", "WEATHER_STRUCT_BAND")
BRACKET_ENABLED          = False  # True → live entries; False → shadow only (when BRACKET_SHADOW)
BRACKET_SHADOW           = True   # log [LADDER SHADOW] signals for validation
BRACKET_COST_CAP         = 0.55   # reject bracket if Σ ask_i > this
BRACKET_MAX_BUCKETS      = 3      # up to 3 rungs
BRACKET_COMBINED_FAIR_MIN = 0.55  # combined fair_prob floor (replaces per-bucket MIN_FAIR_PROB)
BRACKET_SIGMA_MIN        = 0.60   # only ladder on wide-sigma cities (σ ≥ 0.60°C)
# Sigma inflation for entries above ASK_BAND_HI (compensates for suspected overconfidence).
# Set to 1.0 to disable. Increase to 1.3 to make high-price fair_prob estimates more conservative.
SIGMA_INFLATION_ABOVE_CAP = 1.30   # applied when ask > ASK_BAND_HI and BRACKET_ENABLED
STAKE_USD    = 5.0     # fallback flat stake (adaptive: capped at 25% bankroll)
PER_CITY_STAKE_USD: dict[str, float] = {
    "buenos-aires": 20.0,  # 2026-05-23: user-specified flat override
}

# ── Near-threshold CLOB WS watchlist ─────────────────────────────────────────
WATCHLIST_EDGE_FLOOR = -0.06  # subscribe if within 6pp of qualifying (ask too high by ≤0.06)
WATCHLIST_MIN_FAIR   = 0.35   # minimum fair_prob to be worth watching

# ── Fractional Kelly position sizing ─────────────────────────────────────────
KELLY_ENABLED    = False  # flat $5 stake — Kelly disabled 2026-05-26 (was creating $23 outlier bets)
KELLY_FRACTION   = 0.25   # quarter-Kelly: conservative for unverified sigma calibration
KELLY_MIN_USD    = 1.0    # floor: $1 minimum stake (adaptive to bankroll)
KELLY_MAX_USD    = 12.0   # ceiling: raised 2026-05-24 from $8
OVERNIGHT_ALLOC  = 0.00   # STRAT_1 paused: 100% allocation to M1_BETA_PROBE
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
DRY_RUN_LOG  = True   # 2026-05-26: STRAT_1 paused — 100% allocation to M1_BETA_PROBE
# NOTE: DRY_RUN_LOG=True disables WEATHER_ARB / BRACKET / INTRADAY / TAIL live trades.
# M1_BETA_PROBE runs INDEPENDENTLY of this flag (controlled by M1_BETA_PROBE_ENABLED below).

# ── M1 β-PROBE (live fill experiment for METAR lockout residual) ──────────────
# Purpose: measure fill rate, slippage, post-trade EV under real execution.
# ONE signal definition. Fixed thresholds. Small stakes. Hard budget cap.
# Do NOT modify these to "tune" — this is a measurement experiment.
M1_BETA_PROBE_ENABLED          = True   # 2026-06-05 user: RE-ENABLED. Validated slice (MIN_DEPTH_C=0.5 margin gate + dip-rebuy OFF + clean FATEDGE). Reliability analysis n=671: margin≥0.5 = 98.7% WR. Coexists w/ favorite-longshot NO (shared open_positions dedup).
M1_BETA_PROBE_STAKE_USD        = 10.0   # 2026-06-08: 40→10 — removing the NO-ask floor enables cheap-NO fills; at $70 capital a $40
                                        # loss on a false lock (~4.5%) would blow the $10 daily-halt (and 40 already exceeded the $20 max).
                                        # $10 keeps single-trade risk within the ruin discipline. Was 40 (06-03). Revert: 40
M1_BETA_PROBE_STAKE_DEEP_USD   = 20.0   # 2026-06-09 (user-approved): deep-clean slice only — depth_c>=0.5 AND
                                        # no_ask in [0.50,0.96]. Evidence: offline join 98.3% WR n=422 on the
                                        # >=0.5°C band; today's fills had 3-55x visible ask depth vs the $10
                                        # stake. Within the defined $20 max. Thin band [0.2,0.5) and cheap
                                        # fat-edge (ask<0.50) stay at $10. Revert: delete + branch below.
M1_BETA_PROBE_MIN_SHARES       = 5.0    # 2026-06-03 user directive: fire even on thin books — floor = 5 fillable shares
M1_BETA_PROBE_MAX_DAILY_FIRES  = 9999
M1_BETA_PROBE_MAX_TOTAL_FIRES  = 9999
M1_BETA_PROBE_MIN_SEC_SINCE    = 0      # fire on first detection (L0 enabled)
M1_BETA_PROBE_MAX_SEC_SINCE    = 86400  # 24 hr cap (full market lifetime)
M1_BETA_PROBE_MIN_DEPTH_C      = 0.2    # 2026-06-09 (user, LIVE): 0.5→0.2 — admit the [0.2,0.5)°C thin-margin
                                        # band. Re-measure (lockout_reliability n=567, oracle-clean Gamma join):
                                        # sub-0.5°C margin AND no_ask>=0.30 = 26/26 = 100% WR; every loser was
                                        # margin<0.2°C OR a dust ask<0.05 (already gated). The fat-edge slice of
                                        # this new band fires at any ask>=NO_ASK_MIN (0.05); the dust ask<0.05
                                        # losers (0/4) are the real false-lockout tell and stay gated. CAVEAT
                                        # n=24-28 (< the n>=100 rule) — explicit user override, $10 stake +
                                        # monitored; daily-loss halt is the backstop.
                                        # Revert: 0.5. [prior 2026-06-01: 0.4->0.5, margin<0.5=72% WR pre-fix.]
M1_BETA_PROBE_MAX_EDGE         = 0.95   # yes_bid staleness ceiling (no_ask floor below dominates)
# 2026-06-01: VALIDATED-SLICE no_ask gate. Only fire when the market AGREES the
# bucket is locked (NO expensive): no_ask ∈ [0.90, 0.97] = the deep-lockout slice
# (settlement_lock OOS WR 95.9%, n=195). The old `no_ask_clob < 1.0` fired far
# wider — including cheap-NO entries (e.g. 0.385) where the market disagrees; that
# wide firing booked the live −$23.60 (false-lockouts NO→0). Upper 0.97 keeps
# edge ≥ fee floor (1−0.97=0.03).
M1_BETA_PROBE_NO_ASK_MIN       = 0.05   # 2026-06-08: 0.70→0.05 (user) — on an oracle-clean margin≥0.5°C lock,
                                        # NO resolves NO 95-100% at ANY ask (/tmp/floor_tests.py: <0.50=95.5% n=22, 0.50-0.70=100% n=11).
                                        # The physical margin guarantees it, not the ask; the 0.70 floor only discarded the highest-edge
                                        # cheap-NO fills. Sub-0.90 asks STILL require the clean FATEDGE margin (evaluate line ~4371) with a
                                        # fail-safe skip — so cheap NO fires ONLY on a provenance-clean lock. Revert: 0.70.
                                        # [prior] 2026-06-01: widened 0.90→0.70 (user, live). The
                                        # [0.70,0.90) "fat-edge" band resolves NO 94.7% (n=38,
                                        # /tmp/fatedge.py) at +$0.13/sh vs +$0.06 in [0.90,0.97].
                                        # CAVEAT n<40 (trend, not proven). There the market only
                                        # PARTLY confirms the lockout, so the legacy market-agreement
                                        # safety is gone — the band is HARD-GATED below on a
                                        # provenance-clean PHYSICAL margin (official AWC/NWS
                                        # running_max ≥ FATEDGE_MIN_DEPTH_C past the ceiling ⇒ YES
                                        # physically impossible). REST path only. Revert: 0.70→0.90.
M1_BETA_PROBE_NO_ASK_MAX       = 0.97
M1_BETA_PROBE_NO_ASK_MARKET_AGREE = 0.90  # at/above this no_ask the market itself confirms the
                                        # lockout (legacy validated slice) → no clean-margin proof
                                        # required. WS path stays pinned to [MARKET_AGREE, MAX].
M1_BETA_PROBE_FATEDGE_MIN_DEPTH_C = 0.2   # 2026-06-09 (user, LIVE): 0.5→0.2 — the below-market-agree
                                        # fat-edge band requires a PROVENANCE-CLEAN official-METAR margin this
                                        # far past the ceiling. Re-measure (lockout_reliability n=567, oracle-
                                        # clean Gamma join, /tmp/askfloor.py): margin [0.2,0.5)°C AND no_ask≥0.05
                                        # = 24/24 = 100% WR (incl. the cheap [0.05,0.30) fills the market hasn't
                                        # confirmed — official margin makes them physically locked). The ONLY
                                        # thin-margin losers were dust ask<0.05 (0/4 — market ~95% against us =
                                        # the real false-lockout tell), already gated by NO_ASK_MIN=0.05. The
                                        # [0,0.2)°C band stays excluded (MIN_DEPTH_C). CAVEAT n=24-28 (< n≥100
                                        # rule) — explicit user override, $10 stake, -$10/day halt backstop.
                                        # Revert: 0.5. [prior 2026-06-08: 1.0→0.5; <0.5 looked lossy pre-fix.]
M1_BETA_PROBE_GAMMA_BLOCK_SEC  = 99999  # γ-block disabled — depth gate handles thin books
M1_BETA_PROBE_TP               = 0.999  # sell NO when bid >= this — recycle capital, don't wait for resolution
M1_BETA_PROBE_STATE_PATH       = "logs/m1_beta_probe_state.json"
# 2026-06-07 (Claude): ORACLE-CITY BLOCKLIST. The 06-05 M1β re-enable log flagged
# — and lockout_exec_backtest re-confirmed — that wrong-oracle settlement cities
# produce FALSE lockouts that resolve YES even at margin≥0.5°C, because our METAR
# feed diverges from the resolution source. Block by settlement ICAO — checked at
# the single _m1_beta_probe_evaluate chokepoint so both WS and REST paths gate.
#
# 2026-06-09 ORACLE-MATCH CENSUS (analysis/weather/oracle_census_blocked.py,
# 60 resolved Gamma days/city vs IEM METAR + HKO daily max):
#   RJTT Tokyo     60/60 = 100%  -> UNBLOCKED. Market description names the WU
#                                   RJTT/Haneda page; whole-deg C METAR == oracle.
#                                   The 06-07 false lockout was OUR mis-mapped
#                                   AMeDAS 44166 feed, fixed by the official-only
#                                   provenance rule (official_running_max_c is
#                                   AWC-METAR-only now).
#   WSSS Singapore 60/60 = 100%  -> UNBLOCKED (2 apparent misses were truncated
#                                   IEM fetches; per-day refetch matched exactly).
#   VHHH Hong Kong VHHH-METAR 37% -> STAYS BLOCKED on the METAR feed. Oracle is
#                                   the HKO OBSERVATORY (different station), one
#                                   decimal, floor/range-containing buckets:
#                                   HKO daily max matched 21/21 = 100%. Unblock
#                                   requires an HKO feed + floor-aware padding
#                                   (generic ±0.5 pad ⇒ false lockouts here).
#   ZGSZ Shenzhen  16/60 = 27%   -> STAYS BLOCKED. WU "Bao'an" page is NOT the
#                                   ZGSZ METAR (oracle reads 1-2°C warmer).
# Revert: add "RJTT", "WSSS" back.
M1_BETA_PROBE_ORACLE_BLOCK_ICAO = {"VHHH", "ZGSZ"}

# ── Locked-region MAKER first-exercise (2026-06-01, controlled / user-mandated) ──
# Exercises the maker_buy primitive on PROVENANCE-CLEAN locked buckets (NO physically
# certain ⇒ adverse selection = 0). SHADOW by default: logs the exact resting NO bid it
# WOULD post on each locked bucket (proves gating/sizing/non-crossing price on live data,
# ZERO real orders). Flip MAKER_EXERCISE_LIVE=True ONLY under live monitoring for the
# $4-cap real first-exercise. The MakerCircuitBreaker is the sole net (user declined the
# strategy-drawdown halt) — it trips on BUG signatures: runaway resting exposure, a
# failed/hung cancel, or bankroll < floor.
MAKER_EXERCISE_ENABLED           = True    # shadow-log maker candidates on locked buckets
MAKER_EXERCISE_LIVE              = True    # ⚠ LIVE real resting orders (2026-06-01 stage-3, MONITORED)
MAKER_EXERCISE_STAKE_USD         = 5.0     # per-order (user; raised from $4 — CLOB 5-share floor makes <~$4.5 unfillable at NO~0.9)
MAKER_EXERCISE_MAX_ORDERS        = 100000  # effectively UNCAPPED (user 2026-06-02; order code proven). The margin≥1°C locked-slice gate + breaker are the real bounds. Revert: 5.
MAKER_EXERCISE_LIVE_MIN_MARGIN_C = 0.5     # 2026-06-08 WS1: 1.0→0.5 — align to the VALIDATED lockout reliability gate (margin≥0.5°C + oracle-clean = 98.7% WR, n=671). The 1.0°C buffer was conservatism for false-locks; the oracle blocklist (deployed today) now handles those. Expands oracle-clean margin-path candidates ~6.4× (27→172 over 06-06/07), targeting the stale-book margin∈[0.5,1.0) buckets where the maker captures before reprice. Revert: 1.0
MAKER_BREAKER_MAX_EXPOSURE_USD   = 150.0   # 2026-06-09 user: "let it fire" — raised 40→150 (≈ full bankroll) so the d+1/d+2 band can quote the whole qualifying surface. Cash is the real limit; min-bankroll floor below unchanged. Was 40 (user 06-02).
# Persisted resting-maker tracker (oid → ctx). Contract with OrderManager.start():
# its keys are the open orders to KEEP at startup; everything else is a stray and
# gets cancelled. Replaces the blanket startup cancel_all() that wiped the band's
# quoted surface on every deploy (2026-06-10).
MAKER_RESTING_STATE_PATH = "logs/maker_resting_state.json"
# Cash cap on RESTING maker exposure (2026-06-10): the CLOB cancels the ENTIRE
# open-order set when bid commitments exceed free USDC (18/18 band legs swept
# at $50.10 resting vs $49.72 cash). Quote only what actual cash collateralizes.
MAKER_CASH_FRAC = 0.90
# Off-book reclaim grace (2026-06-17): when a tracked BUY is gone from BOTH the
# per-order endpoint (get_order 404s → status None) AND the live open-order set,
# release its phantom breaker exposure — but not within this window of placement,
# so a just-posted order momentarily missing from a snapshot isn't dropped.
MAKER_OFFBOOK_GRACE_SEC = 120.0
# ── PEAKSCALP Phase-0 SHADOW (2026-06-12, user GO) ────────────────────────────
# Winner-bucket convergence scalp candidate: once q(city, month, local_hour,
# headroom-to-ceiling) ≥ gate for the bucket CONTAINING the OFFICIAL running
# max, log gate-pass + real CLOB book. NO capital — Phase-0 measures
# fillability (ask px/depth at gate-pass) and convergence latency (timed
# follow-up snapshots) before any Phase-1 $5 fires. OOS gates: 0.985 → WR
# 98.84% (n=346) / 0.995 → 99.42% (n=344); breakeven at 0.95 entry ≈ 95.1%.
PEAKSCALP_SHADOW          = True
PEAKSCALP_Q_PATH          = "config/peakscalp_q.json"
PEAKSCALP_GATE            = 0.985   # log at the loose gate; analysis picks the live gate
PEAKSCALP_BLOCK_ICAO      = {"VHHH", "ZGSZ"}  # q-table=IEM METAR ≠ their oracle
PEAKSCALP_FOLLOWUP_SEC    = 900.0   # re-snapshot the book this long after gate-pass
PEAKSCALP_FOLLOWUP_GAP    = 120.0   # min spacing between follow-up snapshots
MAKER_BREAKER_MIN_BANKROLL_USD   = 30.0    # trip if bankroll craters below this
MAKER_EXERCISE_MAX_BID           = 0.96    # 2026-06-09: don't rest a maker NO bid above this on a PHYSICAL lock.
                                            # Fill-data (n=2 fills over 4d, both ≤0.94; median post 0.99 = ~0% fill) shows
                                            # deep ~0.99 bids never fill (no NO-selling flow on a settled bucket) yet rest
                                            # forever, consuming the $40 breaker (8×$5) and blocking productive posts. Skip
                                            # them → reserve maker capacity for the fat-edge zone (≤0.96) where fills happen.
                                            # Thermo exempt (its monitored experiment IS to rest deep early for the 4h reprice). Revert: 1.0.

# ── Daily-MIN lockout (2026-06-08, WS2) — SHADOW only, NO capital ───────────────
# Mirror of the validated daily-MAX lockout onto the daily-MINIMUM markets (which
# the bot already fetches via tag_slug=weather but discards at _parse_outcome). Min
# is set near dawn; once recorded, official_running_min_c is monotone, so buckets
# ABOVE it are physically NO-locked — in the MORNING (the dead window for max).
# Stage-1 = SHADOW logger only (metar_min_lockout.jsonl) to validate running_min
# provenance + lock→Gamma-resolution WR (n≥100) BEFORE any live order, exactly how
# max lockout was hardened. Live order-placement is a separate future flag.
MIN_LOCKOUT_SHADOW_ENABLED = True
MIN_LOCKOUT_MIN_MARGIN_C   = 0.5     # SHADOW log threshold: running_min this °C below bucket floor
# LIVE (2026-06-08, user): post real maker NO bids on locked min buckets, reusing
# the proven _maker_locked_exercise machinery (maker = adverse-selection-free on a
# physical lock; breaker + $5 stake + oracle-blocklist all inherited). Gated DEEPER
# than the 0.5 shadow/max threshold because running_min provenance is NOT YET
# validated against Gamma resolution — the one real risk (mirror of the running_max
# overshoot bugs). Loosen toward 0.5 after the first clean min resolutions confirm
# provenance. Revert live: MIN_LOCKOUT_LIVE=False.
MIN_LOCKOUT_LIVE           = True
MIN_LOCKOUT_LIVE_MIN_MARGIN_C = 1.0

# ── Thermo-ceiling MAKER on the upper tail (2026-06-08, user opt-in, BOUNDED) ──────
# Rest NO bids PRE-peak on buckets that are thermodynamically unreachable: a bucket whose
# floor lo_c exceeds the p99 ceiling = running_max + p99·remaining_rise can't contain the
# daily max ⇒ NO. Physics validated 97.2% Gamma WR (/tmp/thermo_econ.py), ~4h before peak,
# 32 cities. Reuses _maker_locked_exercise via the min→max arg map (official_running_max=lo_c,
# hi_c=ceiling ⇒ internal margin = lo_c−ceiling).
# ⚠⚠ ON-RECORD DISSENT (anti-sycophancy): UNLIKE the running_max physical lock (WS1, AS=0),
# this lock CAN reverse (~1% at p99) so the resting maker bid is exposed to WINNER'S CURSE —
# it fills preferentially when a late surge crosses it down (the exact mechanism that
# falsified maker-MVP). The taker econ join showed no_ask already ~0.998 at lock, so there is
# NO cheap taker edge either. This is a MONITORED experiment to MEASURE the live fill-bias,
# NOT a validated edge — likely marginal-to-negative EV. Bounded: p99 + 0.3°C margin, $5 stake,
# daily cap, shared maker breaker ($40 exposure), isolated tag WEATHER_THERMO.
# KILL CRITERION: if WEATHER_THERMO realized PnL is negative over the first ~20 resolved fills,
# set THERMO_MAKER_LIVE=False. Revert anytime: THERMO_MAKER_LIVE=False (keeps shadow log).
THERMO_MAKER_ENABLED       = True    # shadow-log thermo-ceiling upper-tail candidates
THERMO_MAKER_LIVE          = True    # ⚠ post real resting NO bids (user opt-in, monitored)
THERMO_MAKER_P99_K         = 2.33    # p99: ceiling = running_max + mean_rise·(1 + K·RR_CV)
THERMO_MAKER_MIN_MARGIN_C  = 0.3     # bucket floor must exceed the p99 ceiling by this (rounding buffer)
THERMO_MAKER_MAX_DAILY     = 3       # 2026-06-11: 8→3 (user challenge) — at 8×$5 = $40/day THERMO ate
                                     # >half the $65 cash gate AHEAD of the band's ROI-ordered queue
                                     # (execution order, not merit) with ZERO resolved fills (own kill
                                     # gate needs 20). $15/day keeps validation data flowing; re-expand
                                     # (possibly above band priority) only after the first 20 resolve
                                     # clean — near-certain fast turns then EARN the bigger slice. Was 8

# ── NO-arb real-book SHADOW probe (no capital) ──────────────────────────────
# Face 2 (buy-all-NO) is only ever eligible when Σyes_proxy>1 — the OPPOSITE of
# the real-book depth-fetch screen (Σyes_proxy<0.95) — so it has NEVER been
# evaluated on a real order book, only Gamma-proxy prices (no_ask=1−yes_gamma,
# depth 0). On proxy data "Σno_ask<N−1" reduces to "Σyes>1" = the overround, not
# a fillable arb. This probe fetches REAL CLOB books for the top eligible cities
# and logs real Σno_ask + per-leg depth → answers "real arb or just vig?" before
# any capital. Throttled + city-capped to bound HTTP. SHADOW only — no signals.
NO_ARB_PROBE_ENABLED          = True
NO_ARB_PROBE_INTERVAL_S       = 300.0   # at most once / 5 min
NO_ARB_PROBE_MAX_CITIES       = 5       # ≤5 cities × ~11 legs ≈ 55 fetches / interval
NO_ARB_PROBE_MIN_LEG_DEPTH_USD = 5.0    # a leg counts "fillable" only with ≥ this real ask depth

# Per-layer gates. One fire per (condition_id, layer) — bucket can fire up to 5 times
# across its lifetime, never twice in the same layer.
# This is multi-fire BY LAYER, not by time. Statistical clustering is by bucket.
M1_BETA_PROBE_LAYERS = [
    # name,   lo_s,   hi_s,   min_edge,  min_depth_usd
    # Uniform gates: min_edge=fee floor only, min_depth=stake size for full fill
    ("L0",    0,      60,     0.03,      5.0),
    ("L1",    60,     300,    0.03,      5.0),
    ("L2",    300,    1800,   0.03,      5.0),
    ("L3",    1800,   3600,   0.03,      5.0),
    ("L4",    3600,   86400,  0.03,      5.0),
]

# Dip-rebuy: market reprices YES up (hourly METAR misses peak) while 5-min ASOS
# still confirms lockout.  Separate from the time-layer ladder — triggered by
# price dip on an open position, not by time since first detection.
M1_DIP_REBUY_ENABLED     = False  # 2026-06-01: DISABLED. Fires when no_ask ≤ 0.25 (market thinks
                                  # YES ≥ 75%) on the strength of 5-min ASOS confirming lockout —
                                  # i.e. it trusts the SUB-HOURLY feed the oracle-provenance rule
                                  # forbids, and bets AGAINST the market on the validated slice's
                                  # opposite side. This is the false-lockout generator; part of the
                                  # live −$23.60. Re-enable only with official-hourly running_max gating.
M1_DIP_REBUY_NO_ASK_MAX  = 0.25   # fire when NO ask ≤ this (market thinks YES ≥ 75%)
M1_DIP_REBUY_MIN_DEPTH_C = 0.15   # live METAR cache must confirm this °C above hi_c

# DIP-BUY SHADOW (2026-06-02, no capital) — the SAFE re-spec of dip-rebuy. The killed
# dip-rebuy (above) trusted sub-hourly ASOS at no_ask≤0.25 = false-lockout generator.
# This shadow logs cheap-NO candidates ONLY on a STRONG OFFICIAL lockout (official
# running_max ≥ DIP_SHADOW_MIN_MARGIN_C past the ceiling, AWC/NWS-clean) — so the dip
# is genuine NOISE, not real uncertainty (the Seoul 0.7 dip was thin-margin 0.5°C =
# real uncertainty, NOT a clean buy). Logs broadly; sweep margin/dip thresholds + join
# resolution offline before any live re-enable. Disable: DIP_SHADOW_ENABLED=False.
DIP_SHADOW_ENABLED       = True
DIP_SHADOW_MIN_MARGIN_C  = 1.0    # log at/above this OFFICIAL margin (sweep 1.0/1.5/2.0 offline)
DIP_SHADOW_NO_ASK_MAX    = 0.95   # log when the real NO ask has dipped at/below this (a discount exists)
M1_DIP_REBUY_STAKE_USD   = 5.0    # smaller than initial stake (correlated resolution)

# ── FADE live edge — resolution hourly-sampling bias (user GO-LIVE 2026-06-02) ──
# Buy NO on the PRIME bin immediately ABOVE the OFFICIAL (AWC/NWS-clean) running_max,
# POST_PEAK, where the book overprices a between-ob peak poke the routine hourly METAR
# will miss → that bin resolves NO. Backtest n=244 (analysis/weather/resolution_bias_
# backtest.py): prime bin wins NO ~98%, priced ~22¢ YES. ⚠ LIVE n=0 resolved — this is
# semi-directional (YES is physically possible until the official high passes), NOT the
# calibration-free lockout. On-record dissent: enabled by user directive over the n≥100
# gate. Provenance gate (official running_max only) is NON-NEGOTIABLE (false-lockout lesson).
FADE_LIVE_ENABLED      = True   # 2026-06-08 RE-ENABLED (user). Gamma-join validated: prime-bin NO 93.7% (n=111),
                                # tradeable slice (ask∈[0.55,0.90]+depth≥$10) 100% (n=13). $5 stake, oracle-clean gate. Revert: False
FADE_NO_ASK_MIN        = 0.55   # below this the market strongly expects YES = false-fade zone, skip
FADE_NO_ASK_MAX        = 0.89   # 2026-06-08 user: entry NO-ask strictly < 0.9 (buy earlier/cheaper, more upside). Was 0.90
FADE_MAX_GAP_C         = 1.6    # bin lo at most this far above the official running_max (~1 bin)
FADE_MIN_DEPTH_USD     = 10.0   # require this much fillable NO depth at/under our price
FADE_MIN_SEC_TO_CLOSE  = 1800   # ≥30 min to resolution
FADE_WIN_PRIOR         = 0.90   # Kelly win-prob prior — HAIRCUT from backtest 0.98 (live-unconfirmed)
FADE_KELLY_FRACTION    = 0.20   # of full Kelly (matches STWA)
FADE_MIN_STAKE         = 3.0
FADE_MAX_STAKE         = 5.0    # 2026-06-08: 40→5 — $70 capital; collect live resolved n at small blast radius. Was 40
FADE_MIN_SHARES        = 5.0    # 2026-06-03 user directive: fire even on thin books — floor = 5 fillable shares

# ── FAVORITE-YES live edge — favorite-longshot underpricing of confident OPEN-ENDED
# tails (user GO-LIVE 2026-06-03, Tier-3 override of the n≥100 gate) ───────────────
# Buy YES on open-ended cumulative-tail buckets ("X or higher"/"X or below") whose REAL
# CLOB yes_ask is in [0.60,0.98]: the price→resolution calibration shows these resolve
# YES 84-100% vs implied 69-95% (+0.13/ct). ⚠⚠ ON-RECORD DISSENT: n=10-19/band =
# TREND-ONLY, FAR below the n≥100 act-gate (at n=16 a "100% WR" band has ~7% odds of
# being luck even if the market is efficient — which it is on the forecast distribution).
# NOT calibration-free; rides on the FLB persisting. Deployed BOUNDED (small stake +
# daily cap) to accrue LIVE n with a small blast radius. Scale ONLY after live n≥100
# confirms +EV. Revert: FAVYES_LIVE_ENABLED=False.
FAVYES_LIVE_ENABLED     = False  # 2026-06-05 user: BAND-only go-live
FAVYES_MIN_ASK          = 0.60   # below = not a confident favorite; the underpriced zone is [0.60,0.98]
FAVYES_MAX_ASK          = 0.98   # above this the edge < fee
FAVYES_STAKE_USD        = 5.0    # deliberately SMALL — n=10-19 unvalidated; scale only after live n≥100
FAVYES_MIN_SHARES       = 5.0    # require ≥5 fillable YES shares (rejects proxy / thin books)
FAVYES_MAX_DAILY_FIRES  = 10**9  # 2026-06-04 user: UNCAPPED. Real available USDC is now the only cap (per-token dedup happens only on a real fill, so cash freed by manual sells / 0.99 exits recycles into the next favorite). Stake stays $5.
FAVYES_MIN_SEC_TO_CLOSE = 3600   # ≥1h to resolution (standing days-out edge; skip the convergence tail)

# ── 0.99 EXIT (user 2026-06-04) ───────────────────────────────────────────────
# Exit every held-to-resolution weather position once it can be sold at ≥$0.99,
# to capture near-certain winners ~1¢ early and recycle the capital into new fires.
# Implemented as a poll-then-taker sell (NOT a resting limit order): a resting sell
# fills "externally" and the bot wouldn't book it, so the resolution loop would
# double-count it (it books from the Gamma outcome with no balance check). Selling
# at the bid and calling close_position() in the same step books PnL exactly once
# and removes the token so the settler can't re-book it — the same discipline as
# _ofi_manage_exits. Full-depth-gated (no partial-fill accounting); hold-to-
# resolution stays the fallback for anything that never reaches 0.99.
# Revert: EXIT099_ENABLED=False.
EXIT099_ENABLED    = True
EXIT099_PRICE      = 0.99   # sell once a ≥0.99 bid with enough depth is available
EXIT099_MIN_SHARES = 5.0    # skip dust — sub-5-share exits aren't worth the order; they resolve on their own
# ── WINNER-RECYCLE (2026-06-10): the MAKER leg of the last-cent exit — rest a
# 0.99 ask on every held weather position and let takers lift it (the $9-10k/mo
# last-cent wallets are ≥96% maker; EXIT099 above is the taker leg and needs a
# ≥0.99 BID to already exist). Selling at 0.99 is weakly dominant vs holding to
# resolution (give up ≤1¢ when it wins, pure gain when it loses) and recycles
# cash days earlier — cash is the band's binding constraint. Revert: False.
RECYCLE099_ENABLED    = True
RECYCLE099_PRICE      = 0.99
RECYCLE099_MIN_SHARES = 5.0   # CLOB resting minimum (5 shares / $1 maker amount)

# ── WEATHER OFI MOMENTUM (live-tiny, user GO-LIVE 2026-06-02) ──────────────────
# Per-bucket order-flow imbalance predicts resolution (research: edge2/conservation,
# +3.3pp/contract net on actual Gamma resolution, 90 events). v1 = OFI entry, HOLD TO
# RESOLUTION via the existing STWA settler (these are 5/15-min windows so the hold is
# ≤window; the settler is the validated, accounting-safe path). The 15-min ACTIVE sell
# (momentum scalp) is v2 — needs early-sell accounting; the resolution hold is its +EV
# fallback. OFI read from the maker_flow.jsonl tail (the probe already polls weather
# trades) → no new HTTP. ⚠ ON-RECORD DISSENT: validated on 2-3d backtest, n=0 LIVE;
# user chose go-live-tiny over shadow-first. HARD CAPS bound blast radius to ~$20/day.
OFI_LIVE_ENABLED       = False  # 2026-06-03 user directive: turned OFF (not optimized)
OFI_STAKE_USD          = 2.0    # tiny — this is a real-fill validation, not a size bet
OFI_MAX_CONCURRENT     = 3      # max open WEATHER_OFI positions at once (≤$6 at risk)
OFI_MAX_FIRES_DAY      = 10     # hard daily cap (≤$20 deployed/day); resets at UTC midnight
OFI_MIN                = 0.75   # |rolling-OFI| trigger (strongly one-sided flow)
OFI_WIN_S              = 300.0  # rolling OFI window (matches backtest)
OFI_MIN_VOL_USD        = 100.0  # min rolling $-volume to trust the imbalance
OFI_MID_LO             = 0.15   # entry mid band (avoid pinned tails)
OFI_MID_HI             = 0.85
OFI_MIN_DEPTH_USD      = 20.0   # fillable depth on the entry side (so $2 fills)
OFI_MIN_SEC_TO_CLOSE   = 120    # ≥2 min runway to resolution
OFI_MAX_SEC_TO_CLOSE   = 21600  # DEAD CONSTANT. Upper-cap gate not wired (lower bound only).
                                # 2026-06-03 horizon study (ofi_horizon.py): EDGE 2 signal lives
                                # ENTIRELY >6h to close; a 6h cap would gate away ~all of it. Moot —
                                # OFI is fully off (OFI_LIVE_ENABLED=False); kept for archaeology.
# v2 active exit (drift-decay curve, 992 signals): drift dies when OFI dies — when OFI
# is still strong@5m the 5→15m drift is +1.4c, when decayed it's +0.25c (≈nothing). So
# exit on signal-decay, not a clock. Sell at bid (taker) → close_position (books once,
# removes from open_positions; settler can't double-settle). Hold-to-resolution remains
# the fallback if a position can't be cleanly sold (insufficient bid depth).
OFI_EXIT_THRESH        = 0.50   # exit when (our-dir × current OFI) drops below this
OFI_SCALP_TP           = 0.03   # or take profit early if bid ≥ entry + 3c
OFI_TIME_CAP_S         = 1200   # backstop: force-consider exit at 20 min (momentum plateau)

# ── OFI WS-direct trade feed (augment the 180s file poll; validated 2026-06-02) ──
# CLOB market-WS last_trade_price push → sub-second OFI instead of ≤180s file lag.
# Side-semantics verified identical to the data-api tape (ofi_ws_validate.py: 8/8
# side+asset match). AUGMENT-only: an in-mem txhash-deduped buffer is MERGED into
# _ofi_from_tape; the maker_flow.jsonl file stays canonical (still serves the other
# tape consumers + is the silent fallback if the WS drops). False = pure file poll.
OFI_WS_ENABLED         = False  # 2026-06-03: OFI off → no need to run the WS trade-feed augment
OFI_WS_URL             = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
OFI_WS_SUB_REFRESH_S   = 60.0   # re-derive the weather token universe from cache

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

# 8-model global ensemble. All confirmed returning LIVE data via Open-Meteo (2026-06-03 probe).
# GFS (NOAA), ICON (DWD), ECMWF IFS, GEM (CMC/Canada), JMA, UKMO, Météo-France, + ECMWF AIFS.
# AIFS = the SOTA ML model; the LIVE id is `ecmwf_aifs025_single` — the bare `ecmwf_aifs025`
# is history-only and returns null on /v1/forecast (that's why AIFS was silently absent from
# the live ensemble). `gfs_graphcast025` REMOVED 2026-06-03: NOAA GraphCast returns null across
# ±8d on the live endpoint (dead). Models lacking regional coverage return null → silently
# excluded. AIFS has no skill-matrix entry yet → enters at W_FLOOR weight; the revived learning
# loop measures its skill and up-weights it over time.
FORECAST_MODELS = "gfs_seamless,icon_seamless,ecmwf_ifs025,gem_seamless,jma_seamless,ukmo_seamless,meteofrance_seamless,ecmwf_aifs025_single"

# Minimum live models required for an STRAT_1/2 entry. Below this, σ_ens is unreliable:
# the ensemble spread shrinks artificially when models drop out, faking conviction.
# Open-Meteo nulls are typical for regional models in extra-coverage zones; require at least 4
# globally-coverage models to keep σ statistically meaningful.
MIN_MODELS_FOR_ENTRY = 4
# Sigma inflation factor applied when fewer than MIN_MODELS_FOR_ENTRY were available.
# Adds protection against the "fewer models → tighter spread → false confidence" failure.
LOW_MODEL_SIGMA_INFLATION = 1.40
# Local hour (city-local) after which the day's max is definitively final (past the
# diurnal peak everywhere) — the gate for emitting a learning-loop `actual`. Logging at
# 21:00 local guarantees the official daily high is settled and is robust to restarts.
ACTUALS_MIN_LOCAL_HOUR = 21

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
    "NYC":              (40.7769, -73.8740),   # KLGA LaGuardia (Polymarket title alias)
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
    "Istanbul":         (41.2608,  28.7425),   # LTFM Istanbul Airport (Polymarket NOAA resolution)
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
    "New York City": "KLGA", "NYC": "KLGA", "Dallas": "KDAL", "Miami": "KMIA",
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
    "Athens": "LGAV", "Istanbul": "LTFM", "Moscow": "UUWW",
    "Riyadh": "OERK", "Cairo": "HECA", "Lagos": "DNMM",
    "Nairobi": "HKJK", "Johannesburg": "FAOR", "Mumbai": "VABB",
    "Delhi": "VIDP", "Dhaka": "VGHS", "Bangkok": "VTBS",
    "Kuala Lumpur": "WMKK", "Bogota": "SKBO", "Lima": "SPJC",
    "Santiago": "SCEL", "Chongqing": "ZUCK", "Dallas": "KDAL",
}

AWC_METAR_URL = "https://aviationweather.gov/api/data/metar?ids={icao}&format=json&hours=1"
METAR_POLL_INTERVAL = 2   # poll AWC every 2s — minimum safe interval without throttling

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
    "LTFM":   3, "LTAC":   3, "UUEE":   3, "UUWW":   3, "ESSA":   1,
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
    # Added 2026-05-28 — calibrated from 2024 NWP archive daily argmax
    "cape-town":   {1: 12, 2: 12, 3: 11, 4: 12, 5: 11, 6: 12, 7: 12, 8: 11, 9: 12, 10: 11, 11: 10, 12: 11},
    "istanbul":    {1: 11, 2: 12, 3: 13, 4: 12, 5: 11, 6: 11, 7: 11, 8: 10, 9: 11, 10: 11, 11: 11, 12: 11},
    "qingdao":     {1: 6, 2: 6, 3: 5, 4: 4, 5: 5, 6: 4, 7: 5, 8: 5, 9: 5, 10: 6, 11: 6, 12: 6},
    "taipei":      {1: 5, 2: 5, 3: 5, 4: 5, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4},
    # Added 2026-05-28 — 15 new Polymarket cities, 2023-2024 NWP archive median argmax
    "ankara":      {1: 12, 2: 12, 3: 13, 4: 12, 5: 13, 6: 13, 7: 13, 8: 13, 9: 13, 10: 12, 11: 12, 12: 12},
    "busan":       {1: 5, 2: 5, 3: 5, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 5, 11: 5, 12: 5},
    "chengdu":     {1: 8, 2: 7, 3: 8, 4: 8, 5: 8, 6: 8, 7: 8, 8: 7, 9: 7, 10: 7, 11: 7, 12: 7},
    "chongqing":   {1: 8, 2: 8, 3: 8, 4: 8, 5: 8, 6: 8, 7: 8, 8: 7, 9: 7, 10: 7, 11: 7, 12: 7},
    "jeddah":      {1: 10, 2: 10, 3: 10, 4: 9, 5: 9, 6: 9, 7: 11, 8: 10, 9: 9, 10: 9, 11: 9, 12: 10},
    "jinan":       {1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6, 10: 6, 11: 6, 12: 6},
    "karachi":     {1: 10, 2: 9, 3: 9, 4: 8, 5: 8, 6: 8, 7: 8, 8: 8, 9: 8, 10: 8, 11: 8, 12: 10},
    "kuala-lumpur":{1: 6, 2: 7, 3: 6, 4: 6, 5: 7, 6: 7, 7: 7, 8: 7, 9: 7, 10: 6, 11: 6, 12: 6},
    "lucknow":     {1: 9, 2: 9, 3: 9, 4: 8, 5: 9, 6: 9, 7: 9, 8: 8, 9: 8, 10: 8, 11: 8, 12: 9},
    "manila":      {1: 5, 2: 5, 3: 6, 4: 6, 5: 5, 6: 5, 7: 5, 8: 5, 9: 4, 10: 4, 11: 5, 12: 5},
    "panama-city": {1: 18, 2: 18, 3: 18, 4: 18, 5: 17, 6: 17, 7: 17, 8: 18, 9: 17, 10: 16, 11: 17, 12: 18},
    "seoul":       {1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6, 10: 6, 11: 6, 12: 6},
    "wellington":  {1: 3, 2: 2, 3: 2, 4: 3, 5: 2, 6: 2, 7: 3, 8: 2, 9: 2, 10: 4, 11: 2, 12: 3},
    "wuhan":       {1: 7, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 6, 8: 7, 9: 7, 10: 7, 11: 7, 12: 7},
    "zhengzhou":   {1: 7, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 7, 8: 7, 9: 6, 10: 6, 11: 7, 12: 7},
}

# ICAO → STWA city slug (matches stations.py, used by the Kalman engine)
ICAO_TO_SLUG: dict[str, str] = {
    "KLGA": "nyc",          "KORD": "chicago",      "KLAX": "los-angeles",
    "KMIA": "miami",        "KSFO": "san-francisco", "RJTT": "tokyo",
    "EGLC": "london",       "KDAL": "dallas",        "KHOU": "houston",
    "KSEA": "seattle",      "KBKF": "denver",        "KATL": "atlanta",
    "LFPB": "paris",        "LEMD": "madrid",        "EHAM": "amsterdam",
    "ZBAA": "beijing",      "ZSPD": "shanghai",      "WSSS": "singapore",
    "WIHH": "jakarta",      "CYYZ": "toronto",       "MMMX": "mexico-city",
    "SAEZ": "buenos-aires", "SBGR": "sao-paulo",     "EDDM": "munich",
    "EPWA": "warsaw",       "LIMC": "milan",          "EFHK": "helsinki",
    "KAUS": "austin",       "RCSS": "taipei",         "FACT": "cape-town",
    "ZSQD": "qingdao",      "LLBG": "tel-aviv",       "LTFM": "istanbul",
    "UUWW": "moscow",       "ZGSZ": "shenzhen",       "ZGGG": "guangzhou",
    "LTAC": "ankara",      "RKPK": "busan",           "ZUUU": "chengdu",
    "ZUCK": "chongqing",   "OEJN": "jeddah",          "ZSJN": "jinan",
    "OPKC": "karachi",     "WMKK": "kuala-lumpur",    "VILK": "lucknow",
    "RPLL": "manila",      "MPTO": "panama-city",     "RKSS": "seoul",
    "NZWN": "wellington",  "ZHHH": "wuhan",           "ZHCC": "zhengzhou",
}

# Sky cover string → rank 0-4 (matches STWAEngine SKY_RANK convention)
SKY_RANK_MAP: dict[str, int] = {
    "CLR": 0, "SKC": 0, "NSC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4, "VV": 4,
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


def _parse_min_outcome(question: str) -> tuple[Optional[float], Optional[float], bool]:
    """Bucket edges (°C) for a daily-MINIMUM market. The bucket phrasing is
    IDENTICAL to the daily-max markets ('be 70-71°F', 'be 22°C or below', …) —
    only the leading statistic word differs — so we reuse _parse_outcome's
    battle-tested regexes by neutralizing its highest-only guard word. Returns
    (None, None, False) for non-min questions."""
    ql = question.lower()
    if not ("lowest" in ql or "coldest" in ql):
        return None, None, False
    return _parse_outcome(re.sub(r'lowest|coldest', 'be', question, flags=re.IGNORECASE))


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
        # OFI WS-direct trade buffer (augments the file tape; see OFI_WS_ENABLED).
        self._ofi_ws_task: Optional[asyncio.Task] = None
        self._ofi_ws_buf: dict[str, tuple] = {}   # txhash → (recv_ts, cid, ask_bool, notion)
        self._ofi_ws_tok: dict[str, tuple] = {}   # token_id → (cid, "yes"|"no")  resolver
        self._ofi_ws_subbed: set[str] = set()     # tokens already subscribed on the WS
        self._hourly_cache: dict[tuple, tuple] = {}  # key → ({utc_hour: temp_c}, {utc_hour: dew_c})
        self._nwp_today_cache: dict[tuple, Optional[float]] = {}  # (lat2, lon2, date) → nwp_daily_max_c

        # Universal per-ICAO METAR cache — populated by _refresh_all_metars(),
        # shared by _poll_metars(), _intraday_scan(), and _tail_sniper_check().
        # Keyed by ICAO; persists running_max_c across poll cycles.
        self._icao_metar_cache: dict[str, dict] = {}
        self._metar_backfill_done: bool = False  # first fetch uses hours=24 to rebuild running_max

        # Alias kept for forecast-correction path (reads same dict by a different name).
        self._latest_metar = self._icao_metar_cache

        # Today's active weather markets, refreshed every TODAY_MARKETS_TTL seconds.
        # Each entry: {city, icao, lat, lon, mkt} for every open bucket today.
        self._today_markets_cache: list[dict] = []
        self._today_markets_ts: float = 0.0

        # METAR_LOCKOUT shadow tracker — token_id → first-seen-locked ts.
        # Persists across cycles to record the moment a bucket first locked out.
        self._lockout_first_seen: dict[str, float] = {}

        # M1_PROBE real-time watchlist — yes_token_id → lockout context.
        # Populated the moment a lockout is detected in _metar_lockout_scan.
        # _on_weather_bbo fires M1_PROBE entry/TP in milliseconds from this dict.
        # Schema: {no_token_id, city, icao, lo_c, hi_c, depth_c, running_max,
        #          end_date, question, first_ts, mkt, neg_risk}
        self._m1_lockout_watchlist: dict[str, dict] = {}

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

        # ── STWA engine (shadow mode until validated) ─────────────────────────
        try:
            from strategy.stwa_engine import STWAEngine
            _stwa_params = Path(__file__).parent.parent / "config" / "stwa_params.json"
            self._stwa: Optional[STWAEngine] = (
                STWAEngine(params_path=_stwa_params) if _stwa_params.exists() else None
            )
            if self._stwa:
                logger.info("[STWA] engine loaded — shadow mode active")
        except Exception as _e:
            logger.warning("[STWA] engine load failed: %s", _e)
            self._stwa = None
        self._stwa_shadow_task: Optional[asyncio.Task] = None
        self._stwa_city_last_local_day: dict[str, int] = {}  # city → last local day int (for per-city midnight reset)
        self._stwa_city_fires_today: dict[str, int] = {}    # city → entries today (persistent across scans)
        self._stwa_fires_date: str = ""                     # UTC date string for daily reset
        # Tracks the file position (byte offset) in forecast_actuals.jsonl so we only
        # process newly appended actual events each METAR cycle.
        self._wu_actuals_offset: int = 0
        # Learning-loop producer dedup: {(city_slug, valid_day)} already emitted an
        # `actual` for. Revives the dead skill-matrix feed (log_actual had no producer).
        self._actuals_logged: set[tuple[str, str]] = set()
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
        if OFI_WS_ENABLED:
            self._ofi_ws_task = asyncio.create_task(self._ofi_ws_loop(), name="weather_ofi_ws_loop")
        if self._stwa is not None:
            self._stwa_shadow_task = asyncio.create_task(
                self._stwa_shadow_loop(), name="stwa_shadow_loop"
            )
        # Restore the persisted resting-maker tracker BEFORE the resolution loop
        # starts reconciling — surviving orders keep tracking, downtime fills book.
        try:
            self._maker_state_init()
        except Exception:
            logger.exception("[WA] maker state init failed")
        # Settle held-to-resolution STWA positions (PnL → bankroll + trades.jsonl).
        # Spawned unconditionally so persisted WEATHER_STWA still settles even if
        # the engine is disabled. Without this STWA is a write-only position book.
        self._stwa_resolution_task = asyncio.create_task(
            self._stwa_resolution_loop(), name="stwa_resolution_loop"
        )
        # User-channel WS: real-time own-fill events → instant maker reconcile
        # (vs the 300s poll) + durable user_ws.jsonl log + untracked-fill alarm.
        # Idles harmlessly when creds are absent (dry-run / stub client).
        try:
            from data.user_ws import UserWsFeed
            _om = getattr(self.bot, "orders", None)
            self._user_ws = UserWsFeed(
                lambda: getattr(getattr(_om, "_client", None), "creds", None),
                on_trade=self._on_user_ws_trade,
            )
            self._user_ws.start()
        except Exception as _e:
            logger.warning("[WA] user WS feed failed to start: %s", _e)
        try:
            from strategy.wis2_synop import start as _wis2_start
            _wis2_start()
        except Exception as _e:
            logger.warning("[WA] WIS2 subscriber failed to start: %s", _e)

    def _maker_state_init(self) -> None:
        """Init the shared maker objects ONCE and restore the persisted resting
        tracker. Maker orders now SURVIVE restarts (OrderManager startup cancel is
        selective, keyed on this file), so restored entries keep reconciling fills,
        count in the breaker's exposure, and keep the dedup seen-set truthful.
        Orders that died while we were down are polled once by
        _maker_reconcile_fills (get_order_match) — downtime fills get registered,
        terminal entries dropped. Idempotent; called from start() and both lazy
        post paths."""
        if hasattr(self, "_maker_breaker"):
            return
        from strategy.maker_breaker import MakerCircuitBreaker
        self._maker_breaker = MakerCircuitBreaker(
            MAKER_BREAKER_MAX_EXPOSURE_USD, MAKER_BREAKER_MIN_BANKROLL_USD)
        self._maker_ex_seen: set = set()
        self._maker_ex_orders: int = 0
        self._maker_resting: dict = {}
        try:
            st = json.load(open(MAKER_RESTING_STATE_PATH))
            if isinstance(st, dict) and st:
                self._maker_resting = st
                for oid, ctx in st.items():
                    if str(ctx.get("side") or "") == "SELL_EXIT":
                        continue   # share-backed asks consume no cash — keep them out of the cash cap
                    # NET of matched (2026-06-12): the filled portion already left
                    # free USDC as a position — counting it as resting too would
                    # double-tighten the cash gate.
                    stake = float(ctx.get("q_price") or 0.0) * max(
                        float(ctx.get("size") or 0.0) - float(ctx.get("matched") or 0.0), 0.0)
                    try:
                        self._maker_breaker.register_resting(oid, round(stake, 2))
                    except Exception:
                        pass
                logger.info("[MAKER] restored %d resting maker orders from disk "
                            "(exposure $%.2f)", len(st), self._maker_breaker.exposure_usd())
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("[MAKER] resting-state load failed — starting empty")

    def _maker_cash_gate(self, stake_usd: float) -> tuple:
        """NON-LATCHING cash cap on resting maker exposure. Unlike the breaker
        (which trips and latches on breach — bug protection), running out of
        cash is normal: skip the leg, retry next cycle when cash frees up.
        Returns (ok, reason)."""
        free = getattr(getattr(self.bot, "orders", None), "last_usdc_balance", None)
        if free is None or float(free) <= 0:
            return True, ""   # no balance info — fall through to the breaker
        cur = self._maker_breaker.exposure_usd() if hasattr(self, "_maker_breaker") else 0.0
        cap = MAKER_CASH_FRAC * float(free)
        if cur + float(stake_usd) > cap:
            return False, (f"resting ${cur:.2f} + ${float(stake_usd):.2f} > "
                           f"{MAKER_CASH_FRAC:.0%} of ${float(free):.2f} cash")
        return True, ""

    def _maker_resting_save(self) -> None:
        """Persist the resting tracker. OrderManager.start() reads its KEYS to
        decide which open orders survive startup (the rest are strays)."""
        try:
            Path(MAKER_RESTING_STATE_PATH).write_text(json.dumps(self._maker_resting))
        except Exception:
            logger.exception("[MAKER] resting-state save failed")

    async def _maker_reconcile_fills(self) -> None:
        """Fill→position tracker for the locked-region maker.

        maker_buy() posts a resting NO bid and returns RESTING — the fill lands
        asynchronously (minutes/hours later) with no live waiter, so without this
        a fill is invisible: it never becomes a risk.open_position, never reaches
        the resolution poller, never books PnL (the old write-only-book failure).

        This polls each tracked resting maker order via REST (get_order_match —
        source of truth across WS reconnects) and, on any matched volume, registers
        the position (tagged WEATHER_M1_PROBE so the existing settler closes it at
        resolution). Terminal orders (filled/cancelled/expired) are dropped from the
        tracker and released from the breaker's resting-exposure cap.
        """
        resting = getattr(self, "_maker_resting", None)
        if not resting:
            return
        orders = getattr(self.bot, "orders", None)
        risk = getattr(self.bot, "risk", None)
        if orders is None or risk is None:
            return
        # Re-entrancy guard: this runs from BOTH the 300s resolution loop and the
        # user-WS fill callback. Two interleaved passes can each read a stale
        # ctx["matched"], compute the same fill increment, and register it twice
        # (double-booked BUY shares / double close attempts). Serialize.
        if not hasattr(self, "_maker_reconcile_lock"):
            self._maker_reconcile_lock = asyncio.Lock()
        async with self._maker_reconcile_lock:
            await self._maker_reconcile_fills_locked()

    async def _maker_reconcile_fills_locked(self) -> None:
        resting = self._maker_resting
        orders = self.bot.orders
        breaker = getattr(self, "_maker_breaker", None)
        dirty = False
        # Live open-order set (source of truth). Phantom breaker exposure builds
        # up when the CLOB balance engine cancels resting BUYs server-side: that
        # is neither a fill nor a bot cancel, get_order then 404s (status None),
        # and the only release path was a >24h-past-end_date reap — so exposure
        # stayed pinned for days, strangling the cash gate (2026-06-17: ~$22 of
        # ~33 dead ids phantom while ~$27 of free USDC sat idle, posted=0). A
        # SUCCESSFUL fetch lets us release ids that are confirmably off-book now.
        _live_ids = await orders.get_open_order_ids()
        for oid in list(resting.keys()):
            ctx = resting[oid]
            if str(ctx.get("side") or "") == "SELL_EXIT":
                drop, changed = await self._recycle_reconcile_one(oid, ctx)
                if drop:
                    resting.pop(oid, None)
                if drop or changed:
                    dirty = True
                continue
            status, matched, fill_price = await orders.get_order_match(oid)
            if status is None:
                # Off-book reclaim (2026-06-17): status None means get_order
                # RAISED (order not individually fetchable → truly gone, not just
                # paginated out). If a SUCCESSFUL live-book fetch also lacks the
                # id, the order is off-book now (server-side sweep / cancel) — two
                # independent signals — so release the phantom resting exposure
                # immediately instead of waiting 24h past end_date. Grace window
                # guards against a just-posted order momentarily absent from a
                # snapshot. Both signals required: if the open-book fetch failed
                # (_live_ids is None) we fall through to the end_date reap.
                _age = time.time() - float(ctx.get("ts") or 0.0)
                if (_live_ids is not None and oid not in _live_ids
                        and _age > MAKER_OFFBOOK_GRACE_SEC):
                    if breaker is not None:
                        try:
                            breaker.release(oid)
                        except Exception:
                            pass
                    resting.pop(oid, None)
                    self._maker_ex_seen.discard(ctx.get("token_id"))
                    dirty = True
                    logger.warning(
                        "[MAKER] off-book reclaim %s %s — released $%.2f phantom "
                        "resting exposure (gone from live book + get_order 404)",
                        ctx.get("city"), str(oid)[:12],
                        float(ctx.get("q_price") or 0.0) * max(
                            float(ctx.get("size") or 0.0)
                            - float(ctx.get("matched") or 0.0), 0.0))
                    continue
                # REAP (2026-06-12): a long-resolved market's order can't be
                # fetched anymore — "retry next pass" loops forever and the entry
                # pins breaker exposure (= cash-gate headroom) for days (3 stale
                # entries were holding $10.20 of a $76 cap). Once >24h past the
                # market's end_date (resolution is local-midnight +~1.6h, so noon-UTC
                # end + 24h is past resolution in every timezone), cancel best-effort
                # and drop the entry only if the cancel call confirms it's off-book.
                _raw_end = str(ctx.get("end_date") or "")
                try:
                    if "T" in _raw_end:
                        _end_dt = datetime.fromisoformat(_raw_end.replace("Z", "+00:00"))
                    elif _raw_end:
                        _end_dt = datetime.fromisoformat(_raw_end + "T12:00:00+00:00")
                    else:
                        _end_dt = None
                except Exception:
                    _end_dt = None
                if (_end_dt is not None
                        and (datetime.now(timezone.utc) - _end_dt).total_seconds() > 86400
                        and await orders.cancel_order(oid)):
                    if breaker is not None:
                        try:
                            breaker.release(oid)
                        except Exception:
                            pass
                    resting.pop(oid, None)
                    self._maker_ex_seen.discard(ctx.get("token_id"))
                    dirty = True
                    logger.warning(
                        "[MAKER] reaped dead entry %s %s end=%s — released $%.2f resting exposure",
                        ctx.get("city"), str(oid)[:12], _raw_end[:10],
                        float(ctx.get("q_price") or 0.0) * max(
                            float(ctx.get("size") or 0.0) - float(ctx.get("matched") or 0.0), 0.0))
                continue  # transient fetch failure — retry next pass
            price = fill_price if (fill_price and fill_price > 0) else float(ctx.get("q_price") or 0.0)
            prev = float(ctx.get("matched") or 0.0)
            if matched > prev + 1e-6 and matched > 0:
                self._maker_register_fill(oid, ctx, matched - prev, price)  # add the NEW shares only
                ctx["matched"] = matched
                if breaker is not None:
                    # NET exposure (2026-06-12): the filled slice is now spent cash
                    # (free USDC already dropped) — keep only the still-on-book
                    # remainder in the resting cap or the gate counts it twice.
                    try:
                        breaker.register_resting(oid, round(
                            float(ctx.get("q_price") or 0.0) * max(
                                float(ctx.get("size") or 0.0) - matched, 0.0), 2))
                    except Exception:
                        pass
                dirty = True
            # Stop tracking once the order is no longer live on the book.
            fully_filled = matched > 0 and matched >= float(ctx.get("size") or 0.0) - 1e-6
            terminal = status.upper() in (
                "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "INVALID")
            if fully_filled or terminal:
                if breaker is not None:
                    try:
                        breaker.release(oid)
                    except Exception:
                        pass
                resting.pop(oid, None)
                dirty = True
        if dirty:
            self._maker_resting_save()

    async def _on_user_ws_trade(self, ev: dict) -> None:
        """User-channel WS fill event → run the idempotent maker reconcile NOW
        (worst case was the 300s poll) and alarm on fills no tracker knows about
        (the invisible-position class: restart amnesia, double-fills)."""
        try:
            tid = str(ev.get("asset_id") or "")
            oids = {str(o.get("order_id") or o.get("id") or "")
                    for o in (ev.get("maker_orders") or []) if isinstance(o, dict)}
            oids.add(str(ev.get("taker_order_id") or ""))
            resting = getattr(self, "_maker_resting", None) or {}
            tracked_tokens = {m.get("token_id") for m in resting.values()}
            if (oids & set(resting.keys())) or (tid and tid in tracked_tokens):
                await self._maker_reconcile_fills()
                return
            risk = getattr(self.bot, "risk", None)
            if (tid and risk is not None
                    and tid not in getattr(risk, "open_positions", {})):
                logger.warning(
                    "[USER-WS] UNTRACKED FILL: token=%s side=%s price=%s size=%s "
                    "status=%s trader_side=%s — no tracker entry, no open position",
                    tid[:16], ev.get("side"), ev.get("price"), ev.get("size"),
                    ev.get("status"), ev.get("trader_side"))
        except Exception:
            logger.exception("[USER-WS] trade handler failed")

    async def _recycle_reconcile_one(self, oid: str, ctx: dict) -> tuple:
        """SELL_EXIT leg of the maker reconcile. Books the exit EXACTLY ONCE on
        full fill via risk.close_position (position popped → the resolution
        settler skips it); cancels the stale ask when the settler resolved the
        position first. Partial fills only update ctx — the position stays
        intact until the ask FULLY fills, so no partial-close accounting exists
        to drift. Returns (drop_entry, state_changed)."""
        orders = self.bot.orders
        risk = self.bot.risk
        tid = ctx.get("token_id")
        pos = getattr(risk, "open_positions", {}).get(tid)
        if pos is None:
            # Settler got there first — pull the ask. A partial maker-sell before
            # resolution leaves bounded ledger drift (sold@0.99 vs booked outcome).
            await orders.cancel_order(oid)
            m = float(ctx.get("matched") or 0.0)
            if m > 0:
                logger.warning("[RECYCLE099] %s resolved with partial maker-sell %.1f sh — "
                               "ledger drift ≤ $%.2f", str(tid)[:10], m, 0.99 * m)
            return True, True
        status, matched, fill_price = await orders.get_order_match(oid)
        if status is None:
            return False, False
        changed = False
        if matched > float(ctx.get("matched") or 0.0) + 1e-6:
            ctx["matched"] = matched
            changed = True
        size = float(ctx.get("size") or 0.0)
        fully = matched > 0 and matched >= size - 0.01
        terminal = str(status).upper() in (
            "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "INVALID")
        if fully:
            px = fill_price if (fill_price and fill_price > 0) else float(
                ctx.get("q_price") or RECYCLE099_PRICE)
            entry = float(getattr(pos, "entry_price", 0.0) or 0.0)
            pnl = risk.close_position(tid, exit_price=px,
                                      reason="WEATHER_RECYCLE099", actual_fee=0.0)
            self.bot._open_meta.pop(tid, None)
            logger.warning("[RECYCLE099] SOLD %s %.1f sh @ %.4f entry=%.3f pnl=%.3f "
                           "(maker ask lifted)", str(tid)[:10], matched, px, entry, pnl or 0.0)
            try:
                _ld = Path("logs/shadow/hot") / datetime.now(timezone.utc).date().isoformat()
                _ld.mkdir(parents=True, exist_ok=True)
                (_ld / "exit099_live.jsonl").open("a").write(json.dumps({
                    "ts": time.time(), "record": "recycle099", "token": tid,
                    "shares": matched, "entry": entry, "exit": round(px, 4),
                    "pnl": round(pnl, 4) if pnl is not None else None}) + "\n")
            except Exception:
                pass
            return True, True
        return (True, True) if terminal else (False, changed)

    async def _winner_recycle_scan(self) -> None:
        """Maker leg of the last-cent exit: rest a 0.99 GTC ask on every held
        weather position (≥5 sh, one ask per token, restart-proof via the
        persisted maker tracker). The taker leg (_exit_at_099) still catches
        books that gap straight past 0.99 — it skips tokens we have asks on."""
        if not RECYCLE099_ENABLED:
            return
        risk = getattr(self.bot, "risk", None)
        orders = getattr(self.bot, "orders", None)
        if risk is None or orders is None:
            return
        self._maker_state_init()
        try:
            opens = [(t, p) for t, p in list(risk.open_positions.items())
                     if getattr(p, "bond_entry_class", "") in _STWA_RESOLVE_CLASSES]
        except Exception:
            return
        if not opens:
            return
        import math as _math
        asked = {c.get("token_id") for c in self._maker_resting.values()
                 if str(c.get("side") or "") == "SELL_EXIT"}
        tok2neg: dict = {}
        tok2tick: dict = {}
        for _e in (self._today_markets_cache or []):
            _m = _e.get("mkt") or {}
            for _t in _parse_token_ids(_m.get("clobTokenIds", [])):
                tok2neg[_t] = bool(_m.get("negRisk", True))
                try:
                    tok2tick[_t] = float(_m.get("orderPriceMinTickSize") or 0.01)
                except (TypeError, ValueError):
                    pass
        from execution.order_manager import OrderStatus as _OS
        for tok, p in opens:
            try:
                if tok in asked:
                    continue
                sell_sh = float(_math.floor(float(getattr(p, "remaining_shares", 0.0) or 0.0)))
                if sell_sh < RECYCLE099_MIN_SHARES:
                    continue
                # Tick-aware last-cent ask: 813/1051 open weather buckets tick at
                # 0.001 (gamma census 2026-06-10), and post-midnight taker flow
                # pays ≥0.99 into already-decided buckets (HK Jun-7/8 winner:
                # $0.9-1.3k/day) — the $9-10k/mo last-cent wallets rest 0.999,
                # not 0.99. On 0.01-tick books keep 0.99.
                _tick = tok2tick.get(tok, 0.01)
                ask_px = 0.999 if _tick <= 0.001 else RECYCLE099_PRICE
                res = await orders.maker_sell(tok, ask_px, sell_sh,
                                              neg_risk=tok2neg.get(tok, True),
                                              tick_size=("0.001" if _tick <= 0.001
                                                         else "0.01"))
                oid = getattr(res, "order_id", "") or ""
                status = getattr(res, "status", None)
                if status == _OS.FILLED:
                    # Crossed instantly (a ≥0.99 bid was already there) — book now.
                    px = float(getattr(res, "avg_fill_price", ask_px) or ask_px)
                    pnl = risk.close_position(tok, exit_price=px,
                                              reason="WEATHER_RECYCLE099", actual_fee=0.0)
                    self.bot._open_meta.pop(tok, None)
                    logger.warning("[RECYCLE099] instant exit %s %.1f sh @ %.4f pnl=%.3f",
                                   str(tok)[:10], sell_sh, px, pnl or 0.0)
                    continue
                if oid and status == _OS.RESTING:
                    self._maker_resting[oid] = {
                        "token_id": tok, "side": "SELL_EXIT",
                        "q_price": ask_px, "size": sell_sh, "matched": 0.0,
                        "entry_class": str(getattr(p, "bond_entry_class", "") or ""),
                    }
                    self._maker_resting_save()
                    logger.info("[RECYCLE099] resting ask %s %.1f sh @ %.3f order=%s",
                                str(tok)[:10], sell_sh, ask_px, str(oid)[:12])
            except Exception:
                logger.debug("[RECYCLE099] post failed %s", str(tok)[:10], exc_info=True)

    def _maker_register_fill(self, oid: str, ctx: dict, add_shares: float, price: float) -> None:
        """Book `add_shares` (the fill increment since the last poll) of a maker NO
        bid into a held-to-resolution position. New token → open it. ALREADY tracked
        (an M1β taker on the same bucket, or a prior maker partial) → ADD the shares
        with a cost-blended entry_price so settlement counts the full fill
        (close_position uses remaining_shares × (exit − entry_price))."""
        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        if add_shares <= 0:
            return
        tid = ctx["token_id"]
        risk = self.bot.risk
        pos = getattr(risk, "open_positions", {}).get(tid)
        if pos is not None:
            # Blend the maker lot into the existing position (weighted-average cost).
            old_sh = float(getattr(pos, "remaining_shares", 0.0) or 0.0)
            old_entry = float(getattr(pos, "entry_price", price) or price)
            new_sh = old_sh + add_shares
            new_entry = ((old_sh * old_entry + add_shares * price) / new_sh) if new_sh > 0 else price
            pos.remaining_shares = new_sh
            try:
                pos.shares = float(getattr(pos, "shares", old_sh) or old_sh) + add_shares
            except Exception:
                pass
            pos.entry_price = round(new_entry, 6)
            try:
                pos.stake = round(float(getattr(pos, "stake", 0.0) or 0.0) + add_shares * price, 4)
            except Exception:
                pass
            meta = self.bot._open_meta.setdefault(tid, {})
            meta.setdefault("maker_fills", []).append(
                {"oid": oid, "shares": round(add_shares, 2), "price": round(price, 4)})
            try:
                risk._save_positions()
            except Exception:
                pass
            logger.warning("[MAKER-FILL] +%.1f maker sh @ %.4f → %s %s %s now shares=%.1f entry=%.4f",
                           add_shares, price, ctx.get("city"),
                           str(ctx.get("side") or "NO").upper(), str(tid)[:12], new_sh, new_entry)
            return
        # New position — the maker is the first fill on this token. Direction-aware:
        # STRUCT_BAND posts YES bids (ctx side="YES"); lockout/thermo are NO (default).
        _side = str(ctx.get("side") or "NO").upper()
        _dir  = _Dir.BUY_YES if _side == "YES" else _Dir.BUY_NO
        _bod  = "up" if _side == "YES" else "down"
        risk.open_position(
            token_id=tid,
            asset="WEATHER",
            direction=_dir,
            stake=add_shares * price,
            entry_price=price,
            tpsl=_TPSL(take_profit=0.0, stop_loss=0.0,
                       tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
            condition_id=ctx.get("condition_id", ""),
            window_end_ts=0.0,
            is_bond=True,
            bond_outcome_direction=_bod,
            bond_entry_class=ctx.get("entry_class", "WEATHER_M1_PROBE"),
        )
        meta = self.bot._open_meta.setdefault(tid, {})
        meta["signal_source"] = f"WEATHER/{ctx.get('city')}/WEATHER_MAKER"
        meta["city"] = ctx.get("city")
        meta["icao"] = ctx.get("icao")
        meta["weather_question"] = ctx.get("question")
        meta["weather_date"] = ctx.get("end_date")
        meta["bucket_lo_c"] = ctx.get("lo_c")
        meta["bucket_hi_c"] = ctx.get("hi_c")
        meta["maker_order_id"] = oid
        logger.warning("[MAKER-FILL] registered %s %s %s +%.1f @ %.4f (cond=%s)",
                       ctx.get("city"), _side, str(tid)[:12], add_shares, price,
                       str(ctx.get("condition_id"))[:10])

    async def _struct_band_post_maker(self, sig, mkt: dict, live_ask: float,
                                      side: str = "YES") -> None:
        """STRUCT_BAND (badatmath copy) — post ONE resting maker bid for a band leg
        and hand it to the fill→position tracker (_maker_reconcile_fills). side="YES"
        for the mode-band legs, "NO" for the favorite-NO overlay (sig.token_id is
        then the NO token and live_ask the real NO ask). Breaker-gated; non-crossing
        (bid strictly < live ask); held to resolution."""
        from execution.order_manager import OrderStatus
        from strategy.stwa_engine import BAND_MD_DAILY_BUDGET
        # lazy-init the shared maker breaker + resting tracker (same objects the NO path uses)
        self._maker_state_init()
        tid = sig.token_id
        # ── RESTART-PROOF dedup state (2026-06-09: Munich triple-fill): the
        # seen-set was in-memory only, so each deploy restart wiped it while the
        # resting orders survived on the exchange — every restart re-posted the
        # whole surface (3 restarts ⇒ 3 stacked fills/orders per leg). Persist
        # posted tokens + daily spent to disk; reload last 4 days at init
        # (d+1/d+2 quotes span days).
        if not hasattr(self, "_band_state_loaded"):
            self._band_state_loaded = True
            try:
                _st = json.load(open("logs/band_posted_state.json"))
                _cut = (datetime.now(timezone.utc).date()
                        - __import__("datetime").timedelta(days=4)).isoformat()
                for _d, _v in _st.items():
                    if _d >= _cut:
                        self._maker_ex_seen.update(_v.get("tokens", []))
                _today0 = datetime.now(timezone.utc).date().isoformat()
                self._band_budget_date = _today0
                self._band_budget_spent = float(
                    _st.get(_today0, {}).get("spent", 0.0))
            except FileNotFoundError:
                pass
            except Exception:
                logger.exception("[STRUCT-BAND] state load failed")
        # ── DEDUP (2026-06-09, pre-live audit): the multiday scan re-runs every
        # BAND_MD_TTL=300s; without this, every cycle would STACK a fresh resting
        # bid on the same leg until the breaker jammed. One post per token per
        # process lifetime; also skip if we already hold the leg.
        if tid in self._maker_ex_seen:
            return
        if any(m.get("token_id") == tid for m in self._maker_resting.values()):
            return
        _risk0 = getattr(self.bot, "risk", None)
        if _risk0 is not None and tid in getattr(_risk0, "open_positions", {}):
            return
        # ── daily band budget: bound worst-case fills, independent of the
        # resting-only breaker. Resets at UTC midnight.
        _today = datetime.now(timezone.utc).date().isoformat()
        if getattr(self, "_band_budget_date", "") != _today:
            self._band_budget_date = _today
            self._band_budget_spent = 0.0
        if self._band_budget_spent + float(sig.stake) > BAND_MD_DAILY_BUDGET:
            return
        # non-crossing bid: engine quote, re-clamped strictly below the live ask
        q = round(min(float(sig.quote_price), round(live_ask - 0.01, 2)), 2)
        if q < 0.01 or q >= live_ask:
            return
        stake = float(sig.stake)
        ok_cash, why = self._maker_cash_gate(stake)
        if not ok_cash:
            logger.info("[STRUCT-BAND] cash gate: skip %s @ %.2f (%s)", sig.city, q, why)
            return
        risk = getattr(self.bot, "risk", None)
        bankroll = float(getattr(getattr(risk, "bankroll", None), "capital", 0.0) or 0.0)
        ok, reason = self._maker_breaker.precheck(bankroll, stake)
        if not ok:
            logger.warning("[STRUCT-BAND] breaker blocked %s @ %.2f: %s", sig.city, q, reason)
            return
        size = round(stake / q, 2)
        neg_risk = bool(mkt.get("negRisk", True))
        try:
            result = await self.bot.orders.maker_buy(
                token_id=tid, price=q, stake_usd=stake, neg_risk=neg_risk)
        except Exception as e:
            logger.error("[STRUCT-BAND] maker_buy raised %s: %s", sig.city, e)
            return
        oid = getattr(result, "order_id", "") or ""
        status = getattr(result, "status", None)
        # 2026-06-09: FILLED must be tracked like RESTING — a maker bid that
        # instantly matches (real CLOB ask below the stale Gamma ask) returns
        # FILLED; marking only RESTING let the next 300s cycle re-post and
        # DOUBLE-FILL the same leg (Munich 12.5-13.5 ×2), and the fill was
        # invisible to _maker_reconcile_fills (untracked position).
        if oid and status in (OrderStatus.RESTING, OrderStatus.FILLED):
            self._maker_ex_seen.add(tid)
            self._band_budget_spent += stake
            # persist dedup state (restart-proof; see triple-fill note above)
            try:
                _today1 = datetime.now(timezone.utc).date().isoformat()
                try:
                    _st = json.load(open("logs/band_posted_state.json"))
                except FileNotFoundError:
                    _st = {}
                _e = _st.setdefault(_today1, {"tokens": [], "spent": 0.0})
                if tid not in _e["tokens"]:
                    _e["tokens"].append(tid)
                _e["spent"] = round(float(self._band_budget_spent), 2)
                json.dump(_st, open("logs/band_posted_state.json", "w"))
            except Exception:
                logger.exception("[STRUCT-BAND] state persist failed")
            self._maker_breaker.register_resting(oid, stake)
            self._maker_resting[oid] = {
                "token_id": tid, "city": sig.city, "icao": CITY_ICAO.get(sig.city),
                "question": mkt.get("question", ""), "end_date": mkt.get("endDate", ""),
                "lo_c": sig.bucket[0], "hi_c": sig.bucket[1],
                "condition_id": mkt.get("conditionId", ""),
                "q_price": q, "size": size, "matched": 0.0,
                "side": side, "entry_class": "WEATHER_STRUCT_BAND",
                "ts": time.time(),
            }
            self._maker_resting_save()
            # Live BBO on the quoted leg (market-channel WS) — band tokens were
            # the only maker surface NOT subscribed; lockout/bond paths already do this.
            try:
                self.bot.feed._clob_ws_sub_queue.put_nowait([tid])
            except Exception:
                pass
        try:
            _ld = Path("logs/shadow/hot") / datetime.now(timezone.utc).date().isoformat()
            _ld.mkdir(parents=True, exist_ok=True)
            (_ld / "band_struct.jsonl").open("a").write(json.dumps({
                "ts": time.time(), "record": "post", "city": sig.city, "token": tid,
                "side": side, "cid": mkt.get("conditionId", ""),
                "days_out": getattr(sig, "days_out", None),
                "lo": sig.bucket[0], "hi": sig.bucket[1], "ask": round(live_ask, 3),
                "q": q, "stake": round(stake, 2), "size": size,
                "order_id": oid, "status": str(status),
                "exposure": round(self._maker_breaker.exposure_usd(), 2),
            }) + "\n")
        except Exception:
            pass
        logger.warning("[STRUCT-BAND] posted %s %s @ %.2f (ask %.2f) size %.1f order=%s status=%s exposure=$%.2f",
                       sig.city, side, q, live_ask, size, str(oid)[:12], str(status),
                       self._maker_breaker.exposure_usd())

    async def _band_merge_once(self) -> None:
        """Find held YES+NO pairs on the same condition and merge them on-chain
        to USDC (2026-06-11; see execution/merger.py for the verified path).

        A completed pair pays $1/share at settlement no matter what — merging
        realizes that dollar NOW and re-arms the cash-capped band. Per pair:
        cancel any RECYCLE099 SELL_EXIT asks on both legs (they commit the
        tokens), merge min(y, n) clamped to on-chain balances, then book the
        fully-merged leg via close_position and decrement the partial leg
        (exit split: each leg gets half the locked spread, Σ exits = 1)."""
        from strategy.stwa_engine import (BAND_MERGE_ENABLED,
                                          BAND_MERGE_MIN_SHARES,
                                          BAND_MERGE_MIN_EDGE)
        if not BAND_MERGE_ENABLED:
            return
        risk = getattr(self.bot, "risk", None)
        if risk is None:
            return
        if not hasattr(self, "_merger"):
            from execution.merger import ProxyMerger
            from config import CONFIG as _CFG
            self._merger = ProxyMerger(
                private_key=_CFG.wallet_private_key or "",
                proxy_wallet=_CFG.funder_address or "")
        # group open weather positions by condition: cond -> side -> (tid, pos)
        pairs: dict = {}
        for tid, pos in list(getattr(risk, "open_positions", {}).items()):
            if getattr(pos, "bond_entry_class", "") not in _STWA_RESOLVE_CLASSES:
                continue
            cond = getattr(pos, "condition_id", "") or ""
            if not cond:
                continue
            side = "YES" if "YES" in str(getattr(pos, "direction", "")) else "NO"
            pairs.setdefault(cond, {})[side] = (tid, pos)
        for cond, sides in pairs.items():
            if "YES" not in sides or "NO" not in sides:
                continue
            (yt, ypos), (nt, npos) = sides["YES"], sides["NO"]
            ey = float(getattr(ypos, "entry_price", 0.0) or 0.0)
            en = float(getattr(npos, "entry_price", 0.0) or 0.0)
            edge = 1.0 - ey - en
            if edge < BAND_MERGE_MIN_EDGE:
                continue
            m = min(float(getattr(ypos, "remaining_shares", 0.0) or 0.0),
                    float(getattr(npos, "remaining_shares", 0.0) or 0.0))
            if m < BAND_MERGE_MIN_SHARES:
                continue
            # cancel SELL_EXIT asks committing either leg's tokens
            for oid, ctx in list((self._maker_resting or {}).items()):
                if (str(ctx.get("side") or "") == "SELL_EXIT"
                        and ctx.get("token_id") in (yt, nt)):
                    try:
                        await self.bot.orders.cancel_order(oid)
                    except Exception:
                        pass
                    self._maker_resting.pop(oid, None)
            self._maker_resting_save()
            merged = await asyncio.to_thread(
                self._merger.merge, cond, yt, nt, m, True)
            if merged <= 0:
                return  # gas/RPC gate — no point trying further pairs this pass
            # book: each leg exits at entry + half the locked spread (Σ = 1)
            exit_y = round(ey + edge / 2.0, 6)
            exit_n = round(1.0 - exit_y, 6)
            for tid, pos, ex in ((yt, ypos, exit_y), (nt, npos, exit_n)):
                rem = float(getattr(pos, "remaining_shares", 0.0) or 0.0)
                if merged >= rem - 0.01:           # full close
                    self._stwa_close_resolved(tid, pos, ex, reason="BAND_MERGE")
                else:                               # partial: decrement at cost
                    entry = float(getattr(pos, "entry_price", 0.0) or 0.0)
                    pos.remaining_shares = rem - merged
                    try:
                        pos.shares = float(getattr(pos, "shares", rem) or rem) - merged
                        pos.stake = round(max(0.0, float(getattr(pos, "stake", 0.0) or 0.0)
                                              - merged * entry), 4)
                    except Exception:
                        pass
                    risk.bankroll.record_trade_result(merged * (ex - entry))
                    risk._save_positions()
                    logger.warning("[MERGE] partial %s: −%.2f sh @ exit %.3f "
                                   "(%.2f sh remain)", str(tid)[:12], merged, ex,
                                   pos.remaining_shares)
            try:
                _ld = Path("logs/shadow/hot") / datetime.now(timezone.utc).date().isoformat()
                _ld.mkdir(parents=True, exist_ok=True)
                (_ld / "band_struct.jsonl").open("a").write(json.dumps({
                    "ts": time.time(), "record": "merge", "cid": cond,
                    "shares": round(merged, 2), "entry_yes": ey, "entry_no": en,
                    "edge": round(edge, 4),
                    "locked_pnl": round(merged * edge, 4)}) + "\n")
            except Exception:
                pass

    async def _band_quote_reclaim(self) -> None:
        """DEAD-QUOTE RECLAIM (2026-06-11 audit): cancel band quotes that are
        unfilled, old, and ≥ BAND_RECLAIM_BEHIND below the current touch —
        someone outbid us and the book walked AWAY; the quote is just locking
        cash-gate headroom. Quotes AT/near the touch get their age refreshed
        (a quote only becomes reclaimable RECLAIM_AGE_S after it stops being
        competitive). NEVER reprices toward a converged mode — quotes the book
        walks THROUGH are the stale-band edge and keep resting. Partials kept."""
        from strategy.stwa_engine import (BAND_RECLAIM_AGE_S, BAND_RECLAIM_BEHIND,
                                          BAND_RECLAIM_PER_CYCLE, BAND_PAIR_RECLAIM_AGE_S)
        import time as _time
        self._maker_state_init()
        now = _time.time()
        cands = []
        # live merge pairs = a bucket (condition_id) with BOTH a YES and NO band leg
        # resting unmatched. They bid deep below touch ON PURPOSE (merge margin), so the
        # fast 2h behind-touch reclaim would churn them before they co-fill. Paired legs
        # get a longer rest window; lone directional legs keep the fast reclaim.
        _pair_sides: dict = {}
        for _o2, _m2 in (self._maker_resting or {}).items():
            if _m2.get("entry_class") != "WEATHER_STRUCT_BAND":
                continue
            if float(_m2.get("matched", 0.0) or 0.0) > 0.0:
                continue
            _pair_sides.setdefault(_m2.get("condition_id"),
                                   set()).add(str(_m2.get("side", "")).upper())
        _paired_cids = {c for c, s in _pair_sides.items() if {"YES", "NO"} <= s}
        for oid, m in list((self._maker_resting or {}).items()):
            if m.get("entry_class") != "WEATHER_STRUCT_BAND":
                continue
            if str(m.get("side", "")).upper() not in ("YES", "NO"):
                continue
            if float(m.get("matched", 0.0) or 0.0) > 0.0:
                continue
            ts = m.get("ts")
            if ts is None:
                m["ts"] = now          # grandfather pre-existing quotes
                continue
            _age_gate = (BAND_PAIR_RECLAIM_AGE_S if m.get("condition_id") in _paired_cids
                         else BAND_RECLAIM_AGE_S)
            if now - float(ts) < _age_gate:
                continue
            cands.append((float(ts), oid, m))
        if not cands:
            self._maker_resting_save()
            return
        cands.sort()                    # oldest first; budget rotates the rest
        checked = 0
        for ts, oid, m in cands:
            if checked >= BAND_RECLAIM_PER_CYCLE:
                break
            checked += 1
            try:
                bk = await self._fetch_book_levels(m["token_id"], n=1)
            except Exception:
                continue
            bids = (bk or {}).get("bids") or []
            if not bids:
                continue
            touch = float(bids[0]["price"])
            q = float(m.get("q_price", 0.0) or 0.0)
            if q > touch - BAND_RECLAIM_BEHIND:
                m["ts"] = _time.time()  # still competitive — reset the clock
                continue
            try:
                await self.bot.orders.cancel_order(oid)
            except Exception:
                logger.debug("[STRUCT-BAND] reclaim cancel failed %s",
                             str(oid)[:12], exc_info=True)
                continue
            self._maker_breaker.release(oid)
            self._maker_resting.pop(oid, None)
            self._maker_ex_seen.discard(m["token_id"])
            # drop from the restart-proof posted-state so the next cycle may
            # re-quote this leg fresh at the new touch
            try:
                _st = json.load(open("logs/band_posted_state.json"))
                for _v in _st.values():
                    if m["token_id"] in (_v.get("tokens") or []):
                        _v["tokens"].remove(m["token_id"])
                json.dump(_st, open("logs/band_posted_state.json", "w"))
            except Exception:
                pass
            logger.warning("[STRUCT-BAND] reclaimed dead quote %s %s @ %.2f "
                           "(touch %.2f, age %.1fh)", m.get("city"),
                           m.get("side"), q, touch, (now - ts) / 3600.0)
        self._maker_resting_save()

    async def _struct_band_multiday_shadow(self) -> None:
        """BADATMATH multi-day band shadow (2026-06-09 rebuild).

        WHY: the single-day engine path (_struct_band_allocate) only ever sees
        TODAY's market — _refresh_today_markets drops d+1/d+2 at the fetch
        (weather_arb.py:~5023) — and only quotes in the same-day peak window,
        exactly where the over-dispersion band has already collapsed (asks pinned
        0.001/0.996). badatmath quotes the ROLLING horizon d/d+1/d+2 as a maker,
        days before resolution, where the daily high is genuinely uncertain and
        the band is wide. That's the edge our copy was structurally blind to.

        This scanner replicates it faithfully and in ISOLATION: its OWN multi-day
        Gamma fetch, per-(city,date) ladders, NO peak-window gate, NO depth gate
        (a maker POSTS depth, it does not require pre-existing ask-depth). SHADOW
        only — logs would-post maker quotes per (city,date) to band_struct.jsonl
        with days_out; emits no orders, touches no live path. Flip BAND_LIVE to act.
        """
        import time as _time
        from strategy.stwa_engine import BAND_MD_TTL
        if _time.time() - getattr(self, "_band_md_ts", 0.0) < BAND_MD_TTL:
            return
        self._band_md_ts = _time.time()

        # free dead-quote cash BEFORE this cycle's posting spends it
        try:
            await self._band_quote_reclaim()
        except Exception:
            logger.exception("[STRUCT-BAND] reclaim pass failed")

        from strategy.stwa_engine import (
            BAND_PX_MIN, BAND_PX_CEIL, BAND_WING, BAND_SUM_MAX, BAND_MIN_LEGS,
            BAND_BELL, BAND_QUOTE_FRAC, BAND_MD_HORIZON, BAND_LIVE,
            BAND_MD_LIVE_MIN_DOUT, YES_SIGMA_CUTOFF, _peak_sigma_for,
            BAND_YES_MAX_OFF, BAND_YES_MAX_OFF_D0, band_stakes,
            BAND_REALBOOK_YES, BAND_PAIR_FAV_ENABLED, BAND_PAIR_FAV_YES_MIN,
            BAND_PAIR_FAV_YES_MAX, BAND_PAIR_FAV_SUM_MAX, BAND_PX_MIN_MD,
            BAND_PX_MIN_OFF2_D2,
            BAND_PAIR_SHADOW, BAND_PAIR_SHADOW_MARGIN,
            BAND_PAIR_SAMEBUCKET, BAND_PAIR_SB_MAX_BEHIND)

        events = await self._fetch_weather_events()
        if not events:
            return
        _now_utc = datetime.now(timezone.utc)
        # bankroll-proportional stakes (2026-06-11): floors bind until ~$300-450
        # capital (breadth eats first via the cash gate); recomputed per cycle
        _capital = float(getattr(getattr(getattr(self.bot, "risk", None),
                                         "bankroll", None), "capital", 0.0) or 0.0)
        _stk_yes, _stk_no = band_stakes(_capital)
        # 2026-06-18 CAPITAL-PHASE LADDER (user "ready for all phases"): the
        # capital-dependent knobs (YES/NO balance, tail-NO wing expansion + pair cap)
        # are now functions of the live bankroll — they advance on their own as cash
        # compounds, no code edit. Breadth (d+2→d+1→d+0 fill) is already automatic via
        # strict rank + the cash gate.
        from strategy.stwa_engine import band_phase as _band_phase
        _ph = _band_phase(_capital)
        _no_reserve = _ph["no_reserve"]
        _no_max_live = _ph["no_max_live"]      # NO buckets we POST (favorite band, +wings at P3-validated)
        _no_scan_max = _ph["no_scan_max"]      # NO buckets we EVALUATE (incl. tail-NO shadow at P2+)
        _pair_sum = _ph["pair_sum"]            # same-bucket pair Σ cap (widens for wing merges at P3-live)
        _tailno_shadow = _ph["tailno_shadow"]

        # Group buckets by (city, end_date) for end_date in {today..today+HORIZON} local.
        ladders: dict = {}
        meta: dict = {}
        for ev in events:
            city = _parse_city(ev.get("title", ""))
            if not city:
                continue
            icao = CITY_ICAO.get(city)
            _tz_h = ICAO_UTC_OFFSET_H.get(icao or "", 0)
            _local_today = (_now_utc + timedelta(hours=_tz_h)).date()
            horizon = {(_local_today + timedelta(days=d)).isoformat()
                       for d in range(BAND_MD_HORIZON + 1)}
            for mkt in ev.get("markets", []):
                ed = mkt.get("endDate", "")[:10]
                if ed not in horizon or mkt.get("closed", False):
                    continue
                toks = _parse_token_ids(mkt.get("clobTokenIds", []))
                if not toks:
                    continue
                lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
                if lo_c is None and hi_c is None:
                    continue
                prices_raw = mkt.get("outcomePrices", '["0.5"]')
                try:
                    prices = (json.loads(prices_raw)
                              if isinstance(prices_raw, str) else prices_raw)
                    yes_ask = float(prices[0])
                except (IndexError, ValueError, TypeError):
                    continue
                key = (city, ed)
                ladders.setdefault(key, []).append((
                    -999.0 if lo_c is None else lo_c,
                    +999.0 if hi_c is None else hi_c, toks[0], yes_ask, mkt,
                    toks[1] if len(toks) > 1 else ""))   # NO token (favorite-NO overlay)
                meta.setdefault(key, _local_today.isoformat())

        out = Path("logs/shadow/hot") / _now_utc.date().isoformat()
        out.mkdir(parents=True, exist_ok=True)

        def _emit(rec: dict) -> None:
            try:
                with (out / "band_struct.jsonl").open("a") as f:
                    f.write(json.dumps({"ts": _time.time(),
                                        "record": "md_shadow", **rec}) + "\n")
            except Exception:
                pass

        _live_legs: list = []     # (days_out, sum_posted, off, sig, mkt, ask) — posted via unified queue
        _conv_ladders: list = []  # converged ladders stashed for the PAIR_FAV pass
        for (city, ed), ladder in ladders.items():
            days_out = (date.fromisoformat(ed) - date.fromisoformat(meta[(city, ed)])).days
            # interior buckets in the harvest price band — NO depth gate (a maker
            # posts depth; requiring existing ask-depth killed every leg in the
            # old path) and NO peak-window gate (the band lives days out, not at peak).
            # days-out-aware price floor (2026-06-11, user challenge): d+1/d+2
            # admit cheap shoulders down to BAND_PX_MIN_MD (+44.9% ex-explosion,
            # n=652); d+0 keeps the 0.10 floor (cheap@d0 −7.4%, n=1364).
            # 2026-06-18 (user): at d+2 drop the scan floor to the CLOB tick so deep
            # cheap off2 wings ENTER the band (they were pre-filtered out below 0.03).
            # off0/off1 at d+2 are re-floored at the live gate (BAND_PX_MIN_MD); only
            # |off|≥2 actually posts below 0.03. Mode = max-ask, unaffected by admitting
            # cheaper buckets; this just makes index-distance == degree-distance.
            _px_min = (BAND_PX_MIN if days_out == 0
                       else BAND_PX_MIN_OFF2_D2 if days_out == 2
                       else BAND_PX_MIN_MD)
            valid = [(e[0], e[1], e[2], e[3], e[4]) for e in ladder
                     if e[0] > -900.0 and e[1] < 900.0
                     and _px_min <= e[3] <= BAND_PX_CEIL]
            if len(valid) < BAND_MIN_LEGS:
                _emit({"city": city, "date": ed, "days_out": days_out, "reason": "no_band",
                       "n_interior": sum(1 for e in ladder if e[0] > -900 and e[1] < 900),
                       "n_valid": len(valid)})
                continue
            # ── MODE-CONTAINMENT gate (2026-06-09, user caught "only 1 temp per
            # city"): if the GLOBAL ladder mode asks > PX_CEIL the ladder has
            # CONVERGED — the favorite is no longer cheap and the in-window
            # "band" is just the two flanks AROUND it (a hole in the middle).
            # Flanks-only = buying the over-dispersed (overpriced) side WITHOUT
            # the underpriced center: his dist-1 legs (−96%) without the dist-0
            # leg (+432%). The Σ gate cannot see this. Skip converged ladders —
            # the harvest only exists while the whole band incl. the mode is in
            # the price window.
            _global_mode_ask = max((e[3] for e in ladder
                                    if e[0] > -900.0 and e[1] < 900.0
                                    and e[3] is not None), default=0.0)
            if _global_mode_ask > BAND_PX_CEIL:
                _emit({"city": city, "date": ed, "days_out": days_out,
                       "reason": "converged", "mode_ask": round(_global_mode_ask, 3)})
                # converged ladder = pair-fav territory (favorite bid both sides);
                # stash for the PAIR_FAV pass below instead of dropping outright
                _conv_ladders.append((days_out, city, ed, ladder))
                continue
            valid.sort(key=lambda e: e[0])
            mi = max(range(len(valid)), key=lambda i: valid[i][3])   # market mode = max ask
            mode_lo = valid[mi][0]
            band = [valid[i] for i in range(mi - BAND_WING, mi + BAND_WING + 1)
                    if 0 <= i < len(valid)]
            sum_ask = sum(e[3] for e in band)
            # ── 2026-06-11 BASKET-MISMATCH FIX: gate on the POSTED basket. The old
            # gate summed the full ±WING band (5 legs) while live only posts
            # |off| ≤ BAND_YES_MAX_OFF(_D0) — wings we deliberately don't buy were
            # vetoing legs we do (63/112 ladders/cycle died here; YES surface was
            # 2.7% of his universe). His off≤1 basket ROI is positive through
            # Σ3 = 0.85 (see BAND_SUM_MAX note). Full-band Σ still logged.
            _max_off_live = BAND_YES_MAX_OFF_D0 if days_out == 0 else BAND_YES_MAX_OFF
            sum_posted = sum(e[3] for e in band
                             if abs(int(round(e[0] - mode_lo))) <= _max_off_live)
            if len(band) < BAND_MIN_LEGS or sum_posted >= BAND_SUM_MAX:
                _emit({"city": city, "date": ed, "days_out": days_out, "reason": "sum_gate",
                       "n": len(band), "sum_ask": round(sum_ask, 3),
                       "sum_posted": round(sum_posted, 3)})
                continue
            # ── LIVE gates (2026-06-09 teardown re-audit) ──────────────────────
            # days_out: his resolved ROI = d+0 +6.3% / d+1 +14.4% / d+2 +22.8%;
            # late-d+0 "bands" on our books are collapsed ladders (the favorite
            # sits above PX_CEIL so the residual losers masquerade as a band).
            # Live only quotes d+1/d+2; d+0 keeps logging for the validator.
            # σ window: his per-city table loses exactly where true dispersion
            # dies (Singapore −16.7%) or explodes (coin-flip cities) — gate
            # 0.95 ≤ σ(city,month) ≤ YES_SIGMA_CUTOFF.
            # 2026-06-17 σ-SKILL GATE REMOVED (analysis/weather/badatmath_audit/
            # gate_audit.py): replayed on his n=1,126 resolved near-mode YES fills,
            # the σ∉[0.95,1.40] slice this gate rejected was +11.8% ROI ($21.3k =
            # 55% of his near-mode volume). It EXCLUDED his best cities (London
            # σ0.82 +74%, Amsterdam 0.66 +64%, Paris 0.87 +49%, Taipei 1.54 +33%)
            # while ADMITTING losers (Wuhan σ1.38 −27%) ⇒ σ is anti-predictive of
            # band ROI. The gate was inherited from the directional single-bucket
            # YES path, but the dispersion BAND harvest is RICHEST at low σ (a tight
            # true distribution is exactly where the market over-disperses most).
            # Convergence + Σ + price gates already protect the −EV slices
            # (convergence-rejected near-mode YES verified at −34.5%). Revert: git.
            _live_ok = BAND_LIVE and days_out >= BAND_MD_LIVE_MIN_DOUT
            quotes = []
            for lo, hi, tok, ay, mkt in band:
                off = abs(int(round(lo - mode_lo)))
                w = BAND_BELL[off] if off < len(BAND_BELL) else 0.0
                if w <= 0.0:
                    continue
                stake = round(_stk_yes * w, 2)
                bid = max(0.01, ay - 0.02)        # best-bid proxy (Gamma gives no book)
                q = round(max(0.01, min(ay - 0.01,
                                        bid + BAND_QUOTE_FRAC * max(0.0, ay - bid))), 3)
                # 2026-06-15 EXCHANGE-MIN floor (breadth): every order must clear the
                # CLOB minimum max($1, 5 shares); below that it's rejected. His YES
                # fills are $0.95-1.26 = AT this floor. The bell still tilts the mode
                # heavier only where capital lifts _stk_yes·w above the floor.
                stake = round(max(stake, 1.0, 5.0 * q + 0.01), 2)
                quotes.append({"lo": lo, "hi": hi, "ask": round(ay, 3),
                               "bid_quote": q, "stake": stake, "off": off,
                               "cid": mkt.get("conditionId", ""), "tok": tok})
                # LIVE path (gated): collect — posted SORTED after the scan so
                # limited cash goes to the best legs first. Inert while
                # BAND_LIVE=False.
                # 2026-06-11 offset rules (his own fills, n≥100): YES only
                # |off|≤1 (off2/3/4 = −8.5/−72/−56.5%; wings get NO bids via the
                # overlay instead); d+0 YES only on the mode (his d0 YES −3.4%
                # n=1531 — the off0 leg survives as the merge-pair half).
                # Shadow `quotes` above stays ALL offsets so the validator keeps
                # accumulating the wing slices toward its own n≥100.
                _max_off = BAND_YES_MAX_OFF_D0 if days_out == 0 else BAND_YES_MAX_OFF
                if _live_ok and off <= _max_off:
                    import types as _types
                    _sig = _types.SimpleNamespace(token_id=tok, quote_price=q,
                                                  stake=stake, city=city, bucket=(lo, hi),
                                                  days_out=days_out)
                    _live_legs.append((days_out, sum_posted, off, _sig, mkt, float(ay)))
            _emit({"city": city, "date": ed, "days_out": days_out, "reason": "fire",
                   "mode_lo": mode_lo, "sum_ask": round(sum_ask, 3),
                   "sum_posted": round(sum_posted, 3), "live": BAND_LIVE,
                   "n_legs": len(quotes), "quotes": quotes})
        # YES legs are NOT posted here (2026-06-11 audit): YES-first posting ate
        # the whole cash gate every cycle and starved the NO half (17 YES vs 2 NO
        # resting; his book is ~50% NO). All sides now enter ONE ROI-ordered
        # posting queue below — one list, one cash pool, best slice first.

        # ── PAIR MERGE (2026-06-11): held YES+NO on the same condition → $1/sh
        # via NegRiskAdapter through the proxy factory. Cash-velocity engine
        # (his ~50% same-day recycle); strictly cash-positive, no market risk.
        try:
            await self._band_merge_once()
        except Exception:
            logger.exception("[MERGE] pass failed")

        # ── FAVORITE-NO overlay (2026-06-10; REWORKED 2026-06-11 re-audit) ────
        # He is a two-sided pair-quoter: NO is HALF the book and the other half
        # of the same-bucket pair (YES bid + NO bid Σ<1 → both fill → merge $1).
        # Rules from his own post-05-04 fills (n≥100 per slice, state_log 06-11):
        #   price 0.52-0.85 (0.65-0.85 +11.2% is the meat; 0.35-0.50 trough −7.8%)
        #   offset: mode NO = pair leg (+23.2%); SKIP ±1 shoulders (−6.7%,
        #   n=1214); |off|≥2 = wing NO (+13..+35%) — the wings that lost as YES.
        #   days_out d+0..2, posted d+1 first (his best NO slice +12.4%).
        # Same-bucket pair cap: our YES bid + NO bid ≤ BAND_PAIR_SUM_MAX so a
        # completed pair locks ≥8¢/share (merge or settlement pays $1).
        # Gamma proxy pre-filters; the REAL CLOB NO book confirms before posting
        # (proxy-only quoting was the stwa_ladder_book trap).
        from strategy.stwa_engine import (BAND_NO_ENABLED, BAND_NO_MIN,
                                          BAND_NO_MAX,
                                          band_no_daily_cap, BAND_NO_MAX_DOUT,
                                          BAND_NO_SKIP_OFF1, BAND_PAIR_SUM_MAX,
                                          BAND_NO_CASH_RESERVE,
                                          BAND_PROPORTIONAL_QUEUE,
                                          BAND_CELL_WEIGHTS)
        if not BAND_LIVE:
            return
        _today_no = _now_utc.date().isoformat()
        if getattr(self, "_band_no_date", "") != _today_no:
            self._band_no_date = _today_no
            self._band_no_spent = 0.0
        _no_cands = []
        if BAND_NO_ENABLED:
            for (city, ed), ladder in ladders.items():
                days_out = (date.fromisoformat(ed)
                            - date.fromisoformat(meta[(city, ed)])).days
                if not (0 <= days_out <= BAND_NO_MAX_DOUT):
                    continue
                # 2026-06-11 audit: FULL ladder incl. EDGE buckets (or-below /
                # or-higher) — his NO 0.52-0.85 on edges +5.7% (n=438) ≈ interiors
                # +6.5% (n=3,877); the interior-only iteration silently excluded
                # them. Sentinel lo values sort edges to the ends naturally.
                _full = sorted(ladder, key=lambda e: (e[0], e[1]))
                if not _full:
                    continue
                _mi = max(range(len(_full)), key=lambda i: _full[i][3])
                for _i, (lo, hi, yt, ay, mkt, nt) in enumerate(_full):
                    if not nt:
                        continue
                    _off = abs(_i - _mi)
                    if BAND_NO_SKIP_OFF1 and _off == 1:
                        continue
                    # proxy pre-filter (±slack): real book decides below
                    if not (BAND_NO_MIN - 0.10 <= 1.0 - ay <= _no_scan_max + 0.05):
                        continue
                    _no_cands.append((days_out, _off, city, lo, hi, yt, nt, mkt))
        # 2026-06-12 NO-starvation fix: the sort below is deterministic, so the
        # same first few NO candidates got whatever fetch budget remained every
        # cycle and the tail was NEVER evaluated. Rotate per cycle so coverage
        # sweeps the full set (stable sort keeps rotation within equal keys).
        if _no_cands:
            self._band_no_rot = (getattr(self, "_band_no_rot", 0) + 7) \
                % len(_no_cands)
            _no_cands = (_no_cands[self._band_no_rot:]
                         + _no_cands[:self._band_no_rot])

        # ── PAIR_FAV candidates (2026-06-11 audit): converged ladders carry his
        # merge engine's core slice — bid BOTH sides of the favorite bucket at
        # Σ ≤ BAND_PAIR_FAV_SUM_MAX. Favorite YES leg 0.45-0.70 = +20.1% (n=170);
        # cheap-NO PAIR legs +52%/+74% May/Jun. Both +EV standalone; completion
        # locks ≥10¢/sh + feeds merge velocity. Edge-bucket favorites included
        # (each bucket is its own condition — merge works the same).
        _pair_cands = []
        if BAND_PAIR_FAV_ENABLED:
            for days_out, city, ed, ladder in _conv_ladders:
                _full = sorted(ladder, key=lambda e: (e[0], e[1]))
                if not _full:
                    continue
                _mi = max(range(len(_full)), key=lambda i: _full[i][3])
                lo, hi, yt, ay, mkt, nt = _full[_mi]
                if not nt:
                    continue
                # gamma pre-filter (±slack): real books decide below
                if not (BAND_PAIR_FAV_YES_MIN - 0.05 <= ay
                        <= BAND_PAIR_FAV_YES_MAX + 0.05):
                    continue
                _pair_cands.append((days_out, city, lo, hi, yt, nt, mkt))

        # ── UNIFIED VELOCITY-ORDERED POSTING QUEUE (2026-06-16 rerank) ─────────
        # Ordered by ROI per CAPITAL-DAY (compounding rate), not ROI/trade — the
        # binding constraint is turnover, not per-bet edge (badatmath compounded
        # ~$200->$10k in 20d via ~daily turnover, not bigger bets). From the
        # n=2740 band_resolution_join (conditional-on-fill selection ROI):
        # 2026-06-18 (user) DAYS-OUT CAPITAL PRIORITY — fund d+2 first, then d+1,
        # then d+0; within each days-out, YES (mode + off±2) then favorite-NO. The
        # NO leg is funded out of BAND_NO_CASH_RESERVE so d+2 YES (rank 0) can't
        # starve "and the nofav (d+2)". PAIR_FAV de-prioritized to LAST (rank 6):
        # "merge comes with more capital deployed which needs more legs first" —
        # let merge emerge from co-filled directional legs, don't spend scarce
        # cash chasing converged-favorite pairs now.
        # 2026-06-18 (user): favNO buys ONLY at d+1/d+0 — d+2 NO dropped. Dispersion
        # test term structure: mode YES gap +0.022 @ d+2 (mode UNDER-priced) vs −0.043
        # @ d+1 (over-priced), so shorting the mode at d+2 is wrong-way; d+1 favNO is
        # the only +EV NO horizon (realized +3.7%, n=133, all d+1). YES keeps d+2
        # priority (d+2 = the YES horizon — mode cheap there). New order:
        # 2026-06-18 (user): d+1 NO promoted to 2nd (the +EV NO horizon goes right
        # after the best YES horizon).
        #   d+2 YES rank 0  >  d+1 NO rank 1  >  d+1 YES rank 2
        #   >  d+0 YES rank 4  >  d+0 NO rank 5  >  PAIR_FAV rank 6   (d+2 NO dropped)
        # Tiebreak: lower Σ(posted) first (deeper band discount), then |off|.
        _rank_yes = {2: 0, 1: 2, 0: 4}
        _rank_no = {1: 1, 0: 5}     # d+1 NO=rank1 (2nd, after d+2 YES); d+2 NO dropped
        _queue = []
        for _do, _sp, _off, _sig, _mkt, _ay in _live_legs:
            _queue.append((_rank_yes.get(_do, 2), _sp, _off,
                           ("YES", _do, _sig, _mkt, _ay)))
        for _do, _off, city, lo, hi, yt, nt, mkt in _no_cands:
            if _do == 2:
                continue   # 2026-06-18 (user): favNO only d+1/d+0; d+2 NO is wrong-way
            _queue.append((_rank_no.get(_do, 3), 0.0, _off,
                           ("NO", _do, (city, lo, hi, yt, nt, mkt), None, None)))
        for _do, city, lo, hi, yt, nt, mkt in _pair_cands:
            _queue.append((6, 0.0, 0,
                           ("PAIR", _do, (city, lo, hi, yt, nt, mkt), None, None)))
        _queue.sort(key=lambda t: (t[0], t[1], t[2]))
        _no_cap = band_no_daily_cap(_capital)
        _books_left = 80          # real-book fetch budget per cycle
        # 2026-06-12 NO-starvation fix: YES ranks 0-1 consumed the whole fetch
        # budget every cycle (cash-gate-skipped legs never enter the dedup set,
        # so ~50 books re-burned per cycle on legs that could not post) — NO
        # fired 0 times 04:00-12:00 UTC while YES posted all morning. YES gets
        # a fetch sub-budget; cash is pre-checked BEFORE any fetch.
        _books_yes = 50
        _cash_preskip = 0
        # 2026-06-12 NO cash reservation (user directive — match his ~half-NO
        # book): the strict rank order gave NO $0 of freed cash all day
        # (75 YES / 0 NO posts) because ranks 0-1 absorb every freed dollar
        # before rank 2 is reached. YES may consume at most
        # (1 − BAND_NO_CASH_RESERVE) of this cycle's headroom; the remainder
        # is only postable by the NO/PAIR ranks below.
        _free_b = getattr(getattr(self.bot, "orders", None),
                          "last_usdc_balance", None)
        if _free_b is None or float(_free_b) <= 0:
            _yes_cash_cap = float("inf")   # no balance info → old behavior
        else:
            _rest_b = (self._maker_breaker.exposure_usd()
                       if hasattr(self, "_maker_breaker") else 0.0)
            _yes_cash_cap = max(0.0, (MAKER_CASH_FRAC * float(_free_b)
                                      - _rest_b)
                                * (1.0 - _no_reserve))
        _yes_cash_used = 0.0
        _yes_resv_skip = 0
        # ── PROPORTIONAL per-cell budgets (copy badatmath: blanket BOTH books × all
        # horizons, let fills decide the mix). Supersedes the single YES/NO reserve
        # above when on. Soft caps (BAND_CELL_WEIGHTS sum>1) so an empty cell spills
        # to others; the _maker_cash_gate stays the hard global cap. Each cell gets a
        # guaranteed floor ⇒ NO ranks + d+2 no longer starve.
        _cell_spent: dict = {}
        _cell_budget = None
        if BAND_PROPORTIONAL_QUEUE and _free_b and float(_free_b) > 0:
            _rb_c = (self._maker_breaker.exposure_usd()
                     if hasattr(self, "_maker_breaker") else 0.0)
            _headroom = max(0.0, MAKER_CASH_FRAC * float(_free_b) - _rb_c)
            _cell_budget = {k: _headroom * v for k, v in BAND_CELL_WEIGHTS.items()}

        def _cell_of(kind, do):
            return (kind, 0) if kind == "PAIR" else (kind, int(do))

        def _cell_ok(kind, do, stake):
            if _cell_budget is None:
                return True
            cell = _cell_of(kind, do)
            cap = _cell_budget.get(cell)
            if cap is None:                       # unexpected horizon → d+2 cap
                cap = _cell_budget.get((kind, 2), 0.0)
            return _cell_spent.get(cell, 0.0) + float(stake) <= cap

        def _cell_charge(kind, do, stake):
            cell = _cell_of(kind, do)
            _cell_spent[cell] = _cell_spent.get(cell, 0.0) + float(stake)
        _seen_n0 = len(getattr(self, "_maker_ex_seen", set()) or set())
        _risk_band = getattr(self.bot, "risk", None)
        _seen_band = getattr(self, "_maker_ex_seen", set())
        import types as _types
        for _rank, _spq, _offq, _item in _queue:
            _kind = _item[0]
            if _books_left <= 0:
                break
            if _kind == "YES":
                _, _do, _sig, _mkt, _ay = _item
                tid = _sig.token_id
                if (tid in _seen_band
                        or tid in getattr(_risk_band, "open_positions", {})):
                    continue
                _stk_this = float(getattr(_sig, "stake", _stk_yes))
                _okc, _ = self._maker_cash_gate(_stk_this)
                if not _okc:
                    _cash_preskip += 1
                    continue
                if _cell_budget is not None:
                    if not _cell_ok("YES", _do, _stk_this):
                        _yes_resv_skip += 1
                        continue   # this YES cell's proportional budget is spent
                elif _yes_cash_used + _stk_this > _yes_cash_cap:
                    _yes_resv_skip += 1
                    continue   # reserved for NO/PAIR ranks this cycle
                if _books_yes <= 0:
                    continue   # YES sub-budget spent; leave fetches for NO/PAIR
                _ra = float(_ay)
                if BAND_REALBOOK_YES:
                    _books_left -= 1
                    _books_yes -= 1
                    try:
                        _bk = await self._fetch_book_levels(tid, n=1)
                    except Exception:
                        _bk = None
                    if _bk and (_bk.get("asks") or []):
                        _ra = float(_bk["asks"][0]["price"])
                        # re-validate the price window on the REAL ask (gamma
                        # proxies drift; crossing a stale proxy = taker fill);
                        # days-out-aware floor matches the scan filter
                        # 2026-06-18 (user): off2 (|off|≥2) at d+2 has NO min-ask floor
                        # (post down to the CLOB tick); off0/off1 keep the 0.03 d+1/d+2
                        # floor; d+0 keeps 0.10.
                        if _do == 0:
                            _pxm = BAND_PX_MIN
                        elif _do == 2 and _offq >= 2:
                            _pxm = BAND_PX_MIN_OFF2_D2
                        else:
                            _pxm = BAND_PX_MIN_MD
                        if not (_pxm <= _ra <= BAND_PX_CEIL):
                            continue
                        _rb = (float(_bk["bids"][0]["price"])
                               if _bk.get("bids") else max(0.01, _ra - 0.02))
                        # JOIN the touch (watcher n=741: he rests AT the touch;
                        # improving donated ~1¢/sh ≈ 40% of the gross edge)
                        _sig.quote_price = round(min(_rb, _ra - 0.01), 3)
                        if _sig.quote_price < 0.01:
                            continue
                _pre_y = len(getattr(self, "_maker_resting", {}) or {})
                try:
                    await self._struct_band_post_maker(_sig, _mkt, _ra)
                except Exception as e:
                    logger.error("[STRUCT-BAND-MD] live post failed %s: %s",
                                 _sig.city, e)
                if len(getattr(self, "_maker_resting", {}) or {}) > _pre_y:
                    _yes_cash_used += _stk_this
                    _cell_charge("YES", _do, _stk_this)
                    # ── PAIR-SHADOW (2026-06-15, measure-only): for each YES band
                    # leg we actually posted, fetch the real NO book once and log
                    # the would-be NO pair leg + merge margin on the SAME cond.
                    # No cash, no effect on posting (fully wrapped). Offline
                    # pair_shadow_join.py → deliberate-pair co-fill rate + margin.
                    if (BAND_PAIR_SHADOW or BAND_PAIR_SAMEBUCKET) and _books_left > 5:
                        try:
                            _nt = next((t for t in _parse_token_ids(
                                _mkt.get("clobTokenIds", [])) if t != tid), None)
                            if _nt:
                                _books_left -= 1
                                _nbk = await self._fetch_book_levels(_nt, n=1)
                                _nbids = (_nbk or {}).get("bids") or []
                                _nasks = (_nbk or {}).get("asks") or []
                                if _nbids and _nasks:
                                    _nbid = float(_nbids[0]["price"])
                                    _nask = float(_nasks[0]["price"])
                                    # join the NO touch, then bid down ONLY as far as
                                    # needed to lock the merge margin (Σ bids ≤ cap)
                                    _ntouch = round(min(_nask - 0.01, _nbid), 3)
                                    _nq = round(min(_ntouch,
                                                    _pair_sum - _sig.quote_price), 3)
                                    _psum = round(_sig.quote_price + _nq, 3)
                                    _emit({"reason": "pair_shadow",
                                           "cid": _mkt.get("conditionId", ""),
                                           "city": _sig.city, "days_out": _do,
                                           "off": _offq, "yes_quote": _sig.quote_price,
                                           "no_bid": _nbid, "no_ask": _nask,
                                           "no_quote": _nq, "pair_sum": _psum,
                                           "merge_margin": round(1.0 - _psum, 3),
                                           "no_fillable": _nq >= _nbid})
                                    # ── LIVE same-bucket pairing (badatmath co-fill
                                    # engine): post the NO leg on the SAME bucket so the
                                    # pair can merge to $1. Gates: ≥8¢ merge margin
                                    # (Σ bids ≤ cap), NO bid within MAX_BEHIND of touch
                                    # (fill-prob floor), cash + NO daily cap + dedup.
                                    # Either leg alone is a validated YES-band / favorite-
                                    # NO position, so downside is bounded.
                                    if (BAND_PAIR_SAMEBUCKET and BAND_LIVE
                                            and _nq >= 0.01
                                            and _psum <= _pair_sum
                                            and (_ntouch - _nq) <= BAND_PAIR_SB_MAX_BEHIND
                                            and _nt not in _seen_band
                                            and _nt not in getattr(
                                                _risk_band, "open_positions", {})
                                            and self._band_no_spent + _stk_no <= _no_cap
                                            and _cell_ok("NO", _do, _stk_no)):
                                        _okp, _ = self._maker_cash_gate(_stk_no)
                                        if _okp:
                                            _np_sig = _types.SimpleNamespace(
                                                token_id=_nt, quote_price=_nq,
                                                stake=_stk_no, city=_sig.city,
                                                bucket=getattr(_sig, "bucket", None),
                                                days_out=_do)
                                            _pre_n = len(getattr(
                                                self, "_maker_resting", {}) or {})
                                            try:
                                                await self._struct_band_post_maker(
                                                    _np_sig, _mkt, _nask, side="NO")
                                            except Exception as e:
                                                logger.error(
                                                    "[STRUCT-BAND-PAIRSB] %s: %s",
                                                    _sig.city, e)
                                            if len(getattr(self, "_maker_resting", {})
                                                   or {}) > _pre_n:
                                                self._band_no_spent += _stk_no
                                                _cell_charge("NO", _do, _stk_no)
                                                _emit({"reason": "pair_samebucket",
                                                       "cid": _mkt.get(
                                                           "conditionId", ""),
                                                       "city": _sig.city,
                                                       "days_out": _do, "off": _offq,
                                                       "yes_quote": _sig.quote_price,
                                                       "no_quote": _nq,
                                                       "pair_sum": _psum,
                                                       "merge_margin": round(
                                                           1.0 - _psum, 3)})
                        except Exception:
                            pass
            elif _kind == "NO":
                _, days_out, (city, lo, hi, yt, nt, mkt), _x, _y = _item
                if self._band_no_spent + _stk_no > _no_cap:
                    continue
                if nt in _seen_band or nt in getattr(_risk_band, "open_positions", {}):
                    continue
                _okc, _ = self._maker_cash_gate(_stk_no)
                if not _okc:
                    _cash_preskip += 1
                    continue
                if not _cell_ok("NO", days_out, _stk_no):
                    continue   # this NO cell's proportional budget is spent
                _books_left -= 1
                try:
                    _bk = await self._fetch_book_levels(nt, n=3)
                except Exception:
                    continue
                _asks = _bk.get("asks") or []
                _bids = _bk.get("bids") or []
                if not _asks:
                    continue
                _na = float(_asks[0]["price"])
                # tail-NO (above the live favorite-NO ceiling): SHADOW-log at P2+ to
                # accrue the n≥100 validation, but do NOT post until P3 + validated
                # (_no_max_live rises to 0.95 only then). CLAUDE.md rule #2.
                if _na > _no_max_live:
                    if _tailno_shadow and BAND_NO_MIN <= _na <= 0.95:
                        _emit({"city": city, "date": mkt.get("endDate", "")[:10],
                               "days_out": days_out, "reason": "tailno_shadow",
                               "side": "NO", "off": _offq, "ask": round(_na, 3)})
                    continue
                if not (BAND_NO_MIN <= _na):
                    continue
                _nb = float(_bids[0]["price"]) if _bids else max(0.01, _na - 0.04)
                _q = round(max(0.01, min(_na - 0.01, _nb)), 3)   # join, never improve
                # pair cap: if we quote/hold the YES side of this bucket, the two
                # bids must sum ≤ BAND_PAIR_SUM_MAX (locked pair margin ≥ 8¢/sh)
                _qy = None
                _cid = mkt.get("conditionId", "")
                for _m in (getattr(self, "_maker_resting", {}) or {}).values():
                    if (_m.get("condition_id") == _cid
                            and str(_m.get("side", "YES")).upper() == "YES"):
                        _qy = float(_m.get("q_price") or 0.0)
                        break
                if _qy is None:
                    _ypos = getattr(_risk_band, "open_positions", {}).get(yt)
                    if _ypos is not None:
                        _qy = float(getattr(_ypos, "entry_price", 0.0) or 0.0)
                if _qy:
                    _q = min(_q, round(_pair_sum - _qy, 3))
                    if _q < 0.01:
                        continue
                _emit({"city": city, "date": mkt.get("endDate", "")[:10],
                       "days_out": days_out, "reason": "fire_no", "side": "NO",
                       "off": _offq, "ask": round(_na, 3), "bid_quote": _q,
                       "pair_yes_q": _qy, "cid": _cid})
                _sig = _types.SimpleNamespace(token_id=nt, quote_price=_q,
                                              stake=_stk_no, city=city,
                                              bucket=(lo, hi), days_out=days_out)
                _pre = len(getattr(self, "_maker_resting", {}) or {})
                try:
                    await self._struct_band_post_maker(_sig, mkt, _na, side="NO")
                except Exception as e:
                    logger.error("[STRUCT-BAND-NO] post failed %s: %s", city, e)
                    continue
                if len(getattr(self, "_maker_resting", {}) or {}) > _pre:
                    self._band_no_spent += _stk_no
                    _cell_charge("NO", days_out, _stk_no)
            elif _kind == "PAIR":
                _, days_out, (city, lo, hi, yt, nt, mkt), _x, _y = _item
                if self._band_no_spent + _stk_no > _no_cap:
                    continue
                if yt in _seen_band or nt in _seen_band:
                    continue
                if (yt in getattr(_risk_band, "open_positions", {})
                        or nt in getattr(_risk_band, "open_positions", {})):
                    continue
                _okc, _ = self._maker_cash_gate(_stk_yes + _stk_no)
                if not _okc:
                    _cash_preskip += 1
                    continue
                if not _cell_ok("PAIR", days_out, _stk_yes + _stk_no):
                    continue   # PAIR cell's proportional budget is spent
                if _books_left < 2:
                    continue
                _books_left -= 2
                try:
                    _bky = await self._fetch_book_levels(yt, n=1)
                    _bkn = await self._fetch_book_levels(nt, n=1)
                except Exception:
                    continue
                if not (_bky and (_bky.get("asks") or [])
                        and _bkn and (_bkn.get("asks") or [])):
                    continue
                _ya = float(_bky["asks"][0]["price"])
                _na = float(_bkn["asks"][0]["price"])
                if not (BAND_PAIR_FAV_YES_MIN <= _ya <= BAND_PAIR_FAV_YES_MAX):
                    continue
                _yb = (float(_bky["bids"][0]["price"])
                       if _bky.get("bids") else max(0.01, _ya - 0.02))
                _nb = (float(_bkn["bids"][0]["price"])
                       if _bkn.get("bids") else max(0.01, _na - 0.02))
                _qy = round(min(_yb, _ya - 0.01), 3)
                _qn = round(min(_nb, _na - 0.01,
                                BAND_PAIR_FAV_SUM_MAX - _qy), 3)
                if _qy < 0.01 or _qn < 0.01:
                    continue
                # equal SHARES per leg — merge consumes share-for-share
                _shares = round((_stk_yes + _stk_no) / (_qy + _qn), 2)
                if _shares < 5.0:
                    continue          # CLOB resting minimum
                _emit({"city": city, "date": mkt.get("endDate", "")[:10],
                       "days_out": days_out, "reason": "pair_fav",
                       "qy": _qy, "qn": _qn, "shares": _shares,
                       "cid": mkt.get("conditionId", "")})
                _sy = _types.SimpleNamespace(token_id=yt, quote_price=_qy,
                                             stake=round(_shares * _qy, 2),
                                             city=city, bucket=(lo, hi),
                                             days_out=days_out)
                _sn = _types.SimpleNamespace(token_id=nt, quote_price=_qn,
                                             stake=round(_shares * _qn, 2),
                                             city=city, bucket=(lo, hi),
                                             days_out=days_out)
                _pre = len(getattr(self, "_maker_resting", {}) or {})
                try:
                    await self._struct_band_post_maker(_sy, mkt, _ya)
                    await self._struct_band_post_maker(_sn, mkt, _na, side="NO")
                except Exception as e:
                    logger.error("[STRUCT-BAND-PAIR] post failed %s: %s", city, e)
                    continue
                if len(getattr(self, "_maker_resting", {}) or {}) > _pre:
                    self._band_no_spent += round(_shares * _qn, 2)
                    _cell_charge("PAIR", days_out, _stk_yes + _stk_no)
        # per-cycle visibility: the 06-12 starvation hunt was blind because
        # every pre-fire death path was silent
        if _queue:
            _cells_str = (" ".join(f"{k[0][0]}{k[1]}=${v:.0f}"
                                   for k, v in sorted(_cell_spent.items()))
                          if _cell_budget is not None else "rank")
            logger.info(
                "[STRUCT-BAND-Q] cap=$%.0f phase=%d no_resv=%.2f tailno=%s "
                "queue=%d posted=%d cash_preskip=%d "
                "books=%d/80 yes_books=%d/50 no_cands=%d pair_cands=%d "
                "yes_resv_skip=%d mode=%s cells[%s]",
                _capital, _ph["phase"], _no_reserve,
                ("live" if _ph["tailno_live"] else "shadow" if _tailno_shadow else "off"),
                len(_queue),
                max(0, len(getattr(self, "_maker_ex_seen", set()) or set())
                    - _seen_n0),
                _cash_preskip, 80 - _books_left, 50 - _books_yes,
                len(_no_cands), len(_pair_cands),
                _yes_resv_skip,
                "prop" if _cell_budget is not None else "rank", _cells_str)

    async def _stwa_resolution_loop(self) -> None:
        """Settle held-to-resolution WEATHER_STWA positions.

        STWA's only exit is holding to the daily-max settlement, but nothing
        else in the bot detects that settlement — so positions never close, PnL
        never books, and the bankroll + kill switches stay blind (a write-only
        position book). This loop polls Gamma for each open STWA market and,
        once resolved (closed + a definitive 0/1 outcome), books the position
        via risk.close_position so PnL reaches the bankroll AND trades.jsonl.
        The first pass backfills any already-resolved positions.
        """
        await asyncio.sleep(90.0)  # let positions/feed settle after restart
        while True:
            try:
                await self._maker_reconcile_fills()
            except Exception:
                logger.exception("[MAKER-FILL] reconcile failed")
            try:
                await self._stwa_resolve_once()
            except Exception:
                logger.exception("[STWA-RES] resolution poll failed")
            await asyncio.sleep(STWA_RESOLUTION_POLL_SEC)

    async def _stwa_fetch_market(self, sess, condition_id: str):
        """Fetch one *resolved* market by condition_id from Gamma. None on any
        failure. NOTE: Gamma's default /markets query HIDES closed markets
        (returns []); closed=true is required to see resolved ones — which is
        exactly what settlement needs (open markets correctly return nothing)."""
        url = f"{GAMMA_BASE}/markets?condition_ids={condition_id}&closed=true"
        try:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                rows = await resp.json()
                return rows[0] if rows else None
        except Exception:
            return None

    async def _stwa_resolve_once(self) -> None:
        """One pass: close every open WEATHER_STWA whose market has resolved."""
        risk = getattr(self.bot, "risk", None)
        if risk is None:
            return
        open_stwa = {
            tid: pos
            for tid, pos in list(getattr(risk, "open_positions", {}).items())
            if getattr(pos, "bond_entry_class", "") in _STWA_RESOLVE_CLASSES
            and getattr(pos, "condition_id", "")
        }
        if not open_stwa:
            return

        cond_ids = sorted({pos.condition_id for pos in open_stwa.values()})
        markets: dict = {}
        async with aiohttp.ClientSession() as sess:
            BATCH = 10
            for i in range(0, len(cond_ids), BATCH):
                batch = cond_ids[i:i + BATCH]
                results = await asyncio.gather(
                    *[self._stwa_fetch_market(sess, c) for c in batch]
                )
                for c, m in zip(batch, results):
                    if m:
                        markets[c] = m

        n_closed = 0
        for tid, pos in open_stwa.items():
            m = markets.get(pos.condition_id)
            if not m or not m.get("closed", False):
                continue
            toks = _parse_token_ids(m.get("clobTokenIds", []))
            praw = m.get("outcomePrices", "[]")
            try:
                prices = json.loads(praw) if isinstance(praw, str) else praw
                prices = [float(p) for p in (prices or [])]
            except Exception:
                continue
            if not toks or not prices or len(toks) != len(prices):
                continue
            # Require a definitive binary resolution: exactly one outcome ~1.0 and
            # the rest ~0.0. Anything ambiguous (still 0.5/0.5, UMA dispute) is
            # skipped and retried next cycle — never guess a settlement price.
            if (sum(1 for p in prices if p >= 0.99) != 1
                    or sum(1 for p in prices if p <= 0.01) != len(prices) - 1):
                continue
            try:
                idx = toks.index(tid)
            except ValueError:
                continue
            exit_price = 1.0 if prices[idx] >= 0.99 else 0.0
            try:
                self._stwa_close_resolved(tid, pos, exit_price)
                n_closed += 1
            except Exception:
                logger.exception("[STWA-RES] close failed %s", str(tid)[:12])

        if n_closed:
            still = sum(
                1 for p in risk.open_positions.values()
                if getattr(p, "bond_entry_class", "") in _STWA_RESOLVE_CLASSES
            )
            logger.info("[STWA-RES] settled %d position(s); %d STWA still open",
                        n_closed, still)

    def _stwa_close_resolved(self, token_id: str, pos, exit_price: float,
                             reason: str = "STWA_RESOLVED") -> None:
        """Book a resolved STWA position: PnL → bankroll (close_position) and a
        row → trades.jsonl (record_trade). Polymarket redemption is fee-free, so
        actual_fee=0.0 (else close_position would subtract a phantom fee).
        reason="BAND_MERGE" books an on-chain pair merge (also fee-free)."""
        meta = (self.bot._open_meta.get(token_id, {}) or {})
        cap_before = self.bot.risk.bankroll.capital
        pnl = self.bot.risk.close_position(
            token_id, exit_price=exit_price, reason=reason, actual_fee=0.0,
        )
        if pnl is None:
            return
        logger.info("[STWA-RES] CLOSE %s %s @ %.1f | PnL=$%.2f (entry=%.3f shares=%.1f)",
                    meta.get("city", pos.asset), pos.direction.name, exit_price,
                    pnl, pos.entry_price, pos.shares)
        try:
            from strategy.momentum import SignalBreakdown, FeeZone
            from config import CONFIG as _CFG
            sig = SignalBreakdown(
                direction=pos.direction, entry_price=pos.entry_price,
                composite=0.0, confidence=0.0, breakout_score=0.0,
                trend_score=0.0, volume_score=0.0, ob_score=0.0,
                fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                reason="stwa_resolved",
            )
            extra = {k: v for k, v in meta.items() if str(k).startswith("weather_")}
            extra["entered_correctly"] = exit_price >= 0.99
            extra["kline_pnl"] = round(pnl, 4)
            self.bot.analytics.record_trade(
                token_id=token_id, asset=pos.asset, direction=pos.direction,
                entry_price=pos.entry_price, exit_price=exit_price,
                stake=pos.stake, shares=pos.shares,
                entry_fill=None, exit_fills=[],
                exit_reason=reason, signal=sig,
                ts_open=meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                capital_before=cap_before,
                heat_check_active=False,
                consecutive_wins=self.bot.risk.bankroll.consecutive_wins,
                net_pnl_actual=pnl, is_live=not _CFG.dry_run,
                signal_source=meta.get("signal_source", "WEATHER/STWA"),
                bond_entry_class=getattr(pos, "bond_entry_class", "WEATHER_STWA"),
                bond_outcome_direction=getattr(pos, "bond_outcome_direction", ""),
                extra_fields=extra,
            )
        except Exception:
            logger.exception("[STWA-RES] record_trade failed %s", str(token_id)[:12])
        self.bot._open_meta.pop(token_id, None)
        self._fired_tokens.discard(token_id)

    async def _stwa_shadow_loop(self) -> None:
        """Every 30s: log STWA shadow signals. Every 6h: refresh NWP cache for all STWA cities."""
        import json as _json
        from analysis.weather.stations import STATIONS as _STWA_STATIONS
        shadow_dir = Path(__file__).parent.parent / "logs" / "shadow" / "hot"
        _last_nwp_refresh = 0.0
        _NWP_REFRESH_INTERVAL = 6 * 3600  # 6 hours
        while True:
            try:
                await asyncio.sleep(30)
                if self._stwa is None:
                    break

                now_ts = datetime.now(timezone.utc).timestamp()

                # NWP refresh: on first run and every 6h
                # Anchors single-model hourly shape to WEATHER_ARB 9-model BLUE ensemble peak.
                if now_ts - _last_nwp_refresh >= _NWP_REFRESH_INTERVAL:
                    from datetime import date as _dt_date, timedelta as _td
                    _today_s  = _dt_date.today().isoformat()
                    _tmrw_s   = (_dt_date.today() + _td(days=1)).isoformat()
                    _month    = _dt_date.today().month
                    for slug, st in _STWA_STATIONS.items():
                        try:
                            # 1. Hourly shape from single-model (Open-Meteo default)
                            hourly, hourly_dew = await self._get_hourly_forecast(st.lat, st.lon)
                            if not hourly:
                                await asyncio.sleep(0.1)
                                continue

                            # 2. 9-model BLUE ensemble daily max for today
                            fc = await self._get_forecast(st.lat, st.lon, _today_s, _tmrw_s, slug)
                            ens_mu = fc[_today_s][0] if (fc and _today_s in fc) else None

                            if ens_mu is not None and self._stwa is not None:
                                # 3. Read STWA's per-(month, hour) bias.
                                # Old code used bias[month_0] uniformly, but the
                                # bias table is per-hour with 1-2°C peak-to-trough
                                # diurnal variation. Anchor against the bias AT THE
                                # PEAK HOUR so the ensemble peak alignment is exact.
                                _st_params = (self._stwa._params.get("stations", {})
                                              .get(slug, {}))
                                _bias_dict = _st_params.get("bias", {}) or {}

                                # 4. Find the peak hour of the raw hourly forecast
                                _h_peak = max(hourly, key=lambda h: hourly[h])
                                _bias_at_peak = float(_bias_dict.get(
                                    f"{_month}_{_h_peak}",
                                    _bias_dict.get(f"{_month}_0", 0.0),
                                ))

                                # 5. Anchor: shift hourly so that at peak hour,
                                #    T_raw + delta + bias[month, peak_h] = ens_mu
                                #    → delta = ens_mu − bias_at_peak − raw_peak
                                raw_peak = hourly[_h_peak]
                                target_raw_at_peak = ens_mu - _bias_at_peak
                                delta = target_raw_at_peak - raw_peak
                                hourly = {h: t + delta for h, t in hourly.items()}
                                logger.debug("[STWA] NWP anchor %s: peak_h=%d raw_peak=%.1f ens_mu=%.1f "
                                             "bias@peak=%.2f delta=%.2f",
                                             slug, _h_peak, raw_peak, ens_mu, _bias_at_peak, delta)

                            # dew is NOT anchored by the temp delta — it's a separate
                            # variable feeding the humidity correction (A1 fix).
                            self._stwa.update_nwp_forecast(slug, hourly, hourly_dew)
                        except Exception:
                            pass
                        await asyncio.sleep(0.1)  # gentle rate limit
                    _last_nwp_refresh = now_ts
                    logger.info("[STWA] NWP cache refreshed for %d cities (ensemble-anchored)",
                                len(_STWA_STATIONS))

                # State snapshot logging (no CLOB needed)
                rows = self._stwa.get_state_snapshot()
                if not rows:
                    continue
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                out_dir = shadow_dir / today
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "stwa_state.jsonl"
                with open(out_path, "a") as _fh:
                    for row in rows:
                        _fh.write(_json.dumps(row) + "\n")
                logger.debug("[STWA] %d state rows written to %s", len(rows), out_path)
            except asyncio.CancelledError:
                break
            except Exception as _e:
                logger.debug("[STWA] shadow loop error: %s", _e)

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
        now_utc = datetime.now(timezone.utc)
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
                _end_dt_str = m.get("endDate", "")
                _end = _end_dt_str[:10]
                if _end not in target_dates: continue
                if m.get("closed", False): continue
                _end_dt = datetime.fromisoformat(_end_dt_str.replace("Z", "+00:00")) if _end_dt_str else None
                if _end_dt and _end_dt <= now_utc: continue
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
                if getattr(_p, "bond_entry_class", "") in ("WEATHER_ARB", "WEATHER_BRACKET", "WEATHER_STWA")
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
            bankroll = self._get_bankroll()
            stake = min(stake, 5.0, bankroll * OVERNIGHT_ALLOC)
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

        # Pre-entry METAR gate: only valid for same LOCAL day.
        # If today's run_max already exceeds this bucket's ceiling, the outcome
        # is impossible. For tomorrow's markets today's METAR is irrelevant.
        # Compare against LOCAL date: run_max resets at local midnight, so using
        # UTC date causes false blocks for Western-hemisphere cities in the
        # 00:00–local-midnight window where UTC is already "tomorrow" but the
        # run_max accumulated for the previous local day.
        _icao = CITY_ICAO.get(city)
        if _icao and hi_c is not None:
            from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
            _tz_h = ICAO_UTC_OFFSET_H.get(_icao, 0)
            _local_today = (_dt2.now(_tz2.utc) + _td2(hours=_tz_h)).date().isoformat()
            if end_date == _local_today:
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
        """BBO callback: M1_PROBE entry/TP, INTRADAY scalp TP, and watchlist entry firing."""

        # ── M1_PROBE TP: NO token bid >= 0.999 → sell immediately ────────────
        if M1_BETA_PROBE_ENABLED and hasattr(self.bot, "risk"):
            _m1_pos = self.bot.risk.open_positions.get(token_id)
            if _m1_pos is not None and getattr(_m1_pos, "bond_entry_class", "") == "WEATHER_M1_PROBE":
                if bid >= M1_BETA_PROBE_TP:
                    logger.info("[M1β] WS TP %.4f >= %.4f → sell %s", bid, M1_BETA_PROBE_TP, token_id[:12])
                    try:
                        await self.bot.orders.limit_sell(
                            token_id=token_id,
                            price=round(bid - 0.001, 4),
                            size=_m1_pos.shares,
                            condition_id=_m1_pos.condition_id,
                        )
                        self.bot.risk.close_position(token_id, exit_price=bid, reason="M1B_TP_WS")
                    except Exception:
                        logger.exception("[M1β] WS TP sell failed %s", token_id[:12])
                return

        # ── M1_PROBE entry: YES token BBO fires on locked-out bucket ─────────
        if M1_BETA_PROBE_ENABLED:
            w = self._m1_lockout_watchlist.get(token_id)
            if w is not None:
                import time as _t
                now_ts = _t.time()
                yes_bid = bid
                no_token_id = w["no_token_id"]

                # Gates — all evaluated in-memory, zero network I/O
                depth_c = w["depth_c"]
                if (depth_c >= M1_BETA_PROBE_MIN_DEPTH_C
                        and M1_BETA_PROBE_MIN_SEC_SINCE <= int(now_ts - w["first_ts"]) < M1_BETA_PROBE_MAX_SEC_SINCE
                        and 0.03 <= yes_bid < M1_BETA_PROBE_MAX_EDGE
                        and yes_bid != 1.0):
                    # Check NO book depth from live WebSocket order book
                    no_ob = self.bot.feed.order_books.get(no_token_id)
                    no_ask_clob = None
                    no_depth_usd = 0.0
                    no_depth_shares = 0.0
                    if no_ob and no_ob.asks:
                        no_ask_clob = no_ob.asks[0][0]
                        cap = 1.0 - yes_bid + 0.005
                        no_depth_usd = sum(
                            lvl[0] * lvl[1] for lvl in no_ob.asks if lvl[0] <= cap
                        )
                        no_depth_shares = sum(
                            lvl[1] for lvl in no_ob.asks if lvl[0] <= cap
                        )
                    # 2026-06-09 (user): WS fast path widened MARKET_AGREE→NO_ASK_MIN so the
                    # cheap-NO fat-edge band gets WS-speed fills instead of being ceded to the
                    # slower REST scan (fill-rate gain on the highest-EV-per-$ fills). NOT a
                    # safety loosening: _m1_beta_probe_evaluate re-applies the authoritative
                    # official-METAR margin proof (oracle-blocklist + official_running_max +
                    # MIN_DEPTH_C + FATEDGE) on every path. Revert: NO_ASK_MIN→NO_ASK_MARKET_AGREE.
                    if (no_ask_clob is not None
                            and M1_BETA_PROBE_NO_ASK_MIN <= no_ask_clob <= M1_BETA_PROBE_NO_ASK_MAX
                            and no_depth_shares >= 5):
                        # Remove from watchlist to prevent race double-fire
                        # (REST path in _metar_lockout_scan may also check this token)
                        # Keep in watchlist for L1-L4 re-entries — only remove after
                        # state tracks this layer as fired.
                        logger.info(
                            "[M1β] WS ENTRY %s yes_bid=%.3f depth_c=%.2f no_ask=%.3f depth_usd=%.1f",
                            w["city"], yes_bid, depth_c, no_ask_clob, no_depth_usd,
                        )
                        try:
                            await self._m1_beta_probe_evaluate(
                                now_ts=now_ts,
                                now_utc=__import__("datetime").datetime.now(
                                    __import__("datetime").timezone.utc),
                                first_seen=w["first_ts"],
                                mkt=w["mkt"], city=w["city"], icao=w["icao"],
                                end_date=w["end_date"], question=w["question"],
                                lo_c=w["lo_c"], hi_c=w["hi_c"],
                                running_max=w["running_max"],
                                yes_bid=yes_bid,
                                no_token_id=no_token_id,
                                no_ask_clob=no_ask_clob,
                                no_book={"asks": [{"price": lvl[0], "usd": lvl[0] * lvl[1]}
                                                  for lvl in (no_ob.asks if no_ob else [])]},
                                no_ask_usd_at_implied=no_depth_usd,
                                seconds_to_close=None,
                                # PROVENANCE (2026-06-03): pass the AWC/NWS-clean official
                                # running max so the WS deep-band fire also requires a
                                # clean lockout margin; _m1_beta_probe_evaluate fail-safe
                                # skips when none is in hand (was: official=None ⇒ fired
                                # the deep band on contaminated running_max, zero check).
                                official_running_max=(self._icao_metar_cache.get(w["icao"]) or {}).get("official_running_max_c"),
                            )
                        except Exception:
                            logger.exception("[M1β] WS entry evaluate failed %s", w["city"])
                return

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

        # If mu is still inside the held bucket, the held bucket is still the peak by definition.
        # _fired_tokens blinds _evaluate_market to the held token, so without this check the
        # consensus tracker would build toward the 2nd-best bucket even when we're correctly placed.
        _held_lo: Optional[float] = held_pos_meta.get("lo_c")
        _held_hi: Optional[float] = held_pos_meta.get("hi_c")
        if _held_lo is not None and _held_hi is not None:
            if _held_lo <= new_mu < _held_hi:
                if self._bucket_consensus.pop(city_date_key, None) is not None:
                    self._save_consensus_state()
                    logger.info("[WA] SWITCH_RESET %s/%s: mu=%.2f°C still inside held bucket [%.1f,%.1f)",
                                city, end_date, new_mu, _held_lo, _held_hi)
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
        _last_slow = 0.0
        while True:
            try:
                import time as _t
                # Fast path (every METAR_POLL_INTERVAL seconds):
                # 1. Refresh METAR cache — returns True if any station has a new observation
                new_obs = await self._refresh_all_metars()
                # 2. All NMS sources (Synoptic/JMA/NWS/NEA/etc.) — polled every 2s so we
                #    catch new obs within 2s of the source publishing. 60s was misaligned
                #    with update cycles by up to 59s.
                nms_obs = await self._poll_national_met()
                # 3. M1β TP + NOWCAST exits — no network, just checks current_price in memory
                await self._evaluate_dynamic_exits()
                # 4. Lockout scan + M1_PROBE evaluate — only when new data arrived
                if new_obs or nms_obs:
                    try:
                        await self._metar_lockout_scan()
                    except Exception:
                        logger.exception("[WA] metar lockout scan error")

                # Slow path (every ~60s): position monitor + WU + oracle + intraday + tail
                if _t.time() - _last_slow >= 60.0:
                    _last_slow = _t.time()
                    await self._poll_metars()
                    await self._check_wu_transitions()
                    await self._log_weather_actuals()
                    await self._oracle_metar_check()
                    try:
                        await self._metar_lockout_scan()
                    except Exception:
                        logger.exception("[WA] metar lockout scan (nms) error")
                    try:
                        await self._metar_min_lockout_scan()   # WS2 shadow — no capital
                    except Exception:
                        logger.exception("[WA] metar MIN lockout scan error")
                    try:
                        await self._thermo_ceiling_maker_scan()   # bounded thermo-ceiling maker (monitored)
                    except Exception:
                        logger.exception("[WA] thermo-ceiling maker scan error")
                    try:
                        await self._m1_dip_rebuy_scan()
                    except Exception:
                        logger.exception("[M1β-DIP] scan error")
                    if INTRADAY_ENABLED:
                        await self._intraday_scan()
                    if self._stwa is not None:
                        await self._stwa_signal_scan()
                    if TAIL_SNIPER_ENABLED:
                        await self._tail_sniper_check()
                    try:
                        await self._exit_at_099()
                    except Exception:
                        logger.exception("[EXIT099] scan error")
                    try:
                        await self._winner_recycle_scan()
                    except Exception:
                        logger.exception("[RECYCLE099] scan error")
            except Exception:
                logger.exception("[WA] metar loop error")
            await asyncio.sleep(METAR_POLL_INTERVAL)

    async def _metar_min_lockout_scan(self) -> None:
        """SHADOW logger for daily-MINIMUM lockout (mirror of _metar_lockout_scan).
        A min-market bucket is physically NO-locked once the official running MIN
        (monotone, AWC/NWS-hourly) sits ≥MARGIN below the bucket's lower edge — the
        daily min already undercut it, so it cannot contain the min. Logs to
        metar_min_lockout.jsonl. NO capital. Min markets are already in
        _today_markets_cache (tag_slug=weather); only _parse_outcome discards them."""
        if not (MIN_LOCKOUT_SHADOW_ENABLED and self._today_markets_cache):
            return
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        import time as _time
        now_utc  = datetime.now(timezone.utc)
        today_str = now_utc.date().isoformat()
        log_dir  = Path("logs/shadow/hot") / today_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "metar_min_lockout.jsonl"
        now_ts   = _time.time()

        cands = []
        for entry in self._today_markets_cache:
            mkt  = entry.get("mkt") or {}
            city = entry.get("city"); icao = entry.get("icao")
            if not city or not icao:
                continue
            if icao in M1_BETA_PROBE_ORACLE_BLOCK_ICAO:   # wrong-oracle cities (mirror M1β)
                continue
            question = mkt.get("question", "")
            lo_c, hi_c, is_celsius = _parse_min_outcome(question)
            if lo_c is None:        # only buckets with a lower edge can NO-lock from below
                continue
            end_date = (mkt.get("endDate") or "")[:10]
            _tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
            _local_today = (now_utc + timedelta(hours=_tz_h)).date().isoformat()
            if end_date != _local_today:
                continue
            metar = self._icao_metar_cache.get(icao) or {}
            run_min = metar.get("official_running_min_c")
            if run_min is None:
                continue
            if metar.get("running_max_date", "") != _local_today:   # shared midnight key
                continue
            margin = lo_c - run_min        # min sits this far below the bucket floor
            if margin < MIN_LOCKOUT_MIN_MARGIN_C:
                continue
            ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            no_tok = ids[1] if len(ids) > 1 else None
            cond_id = mkt.get("conditionId") or mkt.get("condition_id") or ""
            cands.append((entry, question, lo_c, hi_c, is_celsius, run_min, margin, no_tok, end_date, cond_id))
        if not cands:
            return

        written = 0
        live_fired = 0
        try:
            async with aiohttp.ClientSession() as sess:
                for (entry, question, lo_c, hi_c, is_celsius, run_min, margin, no_tok, end_date, cond_id) in cands:
                    no_ask = None; best_bid = None; depth_usd = 0.0
                    if no_tok:
                        try:
                            async with sess.get(
                                f"https://clob.polymarket.com/book?token_id={no_tok}",
                                timeout=aiohttp.ClientTimeout(total=6)) as r:
                                if r.status == 200:
                                    b = await r.json()
                                    asks = b.get("asks") or []
                                    bids = b.get("bids") or []
                                    if asks:
                                        no_ask = min(float(a["price"]) for a in asks)
                                        depth_usd = sum(float(a["price"]) * float(a["size"]) for a in asks
                                                        if abs(float(a["price"]) - no_ask) <= 0.05)
                                    if bids:
                                        best_bid = max(float(a["price"]) for a in bids)
                        except Exception:
                            pass
                    # ── LIVE: post a maker NO bid on the locked min bucket ──────────
                    # Reuse the proven _maker_locked_exercise (maker = AS-free on a
                    # physical lock). Map min→max args so its internal margin compute
                    # (official_running_max − hi_c) yields the MIN margin (lo_c − min).
                    # Deeper gate than shadow: provenance still unvalidated.
                    if (MIN_LOCKOUT_LIVE and no_ask is not None
                            and margin >= MIN_LOCKOUT_LIVE_MIN_MARGIN_C):
                        try:
                            await self._maker_locked_exercise(
                                city=entry.get("city"), no_token_id=no_tok,
                                no_book={"best_bid": best_bid, "best_ask": no_ask},
                                no_ask_clob=no_ask, hi_c=run_min,
                                official_running_max=lo_c, now_ts=now_ts, now_utc=now_utc,
                                icao=entry.get("icao") or "", question=question,
                                end_date=end_date, lo_c=lo_c, condition_id=cond_id)
                            live_fired += 1
                        except Exception:
                            logger.exception("[WA] min-lockout live maker error")
                    rec = {
                        "schema_version": 1, "record_type": "metar_min_lockout_candidate",
                        "ts_s": round(now_ts, 1), "ts_utc": now_utc.isoformat(),
                        "city": entry.get("city"), "icao": entry.get("icao"),
                        "token_id": no_tok, "question": question,
                        "bucket_lo_c": round(lo_c, 3),
                        "bucket_hi_c": (round(hi_c, 3) if hi_c is not None else None),
                        "is_celsius_market": is_celsius,
                        "official_running_min_c": round(float(run_min), 3),
                        "margin_c": round(float(margin), 3),
                        "no_ask": no_ask, "no_depth_usd": round(depth_usd, 2),
                        "end_date": end_date,
                    }
                    with open(log_path, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    written += 1
        except Exception:
            logger.exception("[WA] metar_min_lockout write error")
        if written:
            logger.info("[WA] MIN_LOCKOUT: %d locked min-bucket candidates, %d live maker posts this cycle",
                        written, live_fired)

    async def _thermo_ceiling_maker_scan(self) -> None:
        """Thermo-ceiling MAKER on the upper tail (BOUNDED, MONITORED — see THERMO_MAKER_*
        dissent). Rests NO bids PRE-peak on buckets that are thermodynamically unreachable
        (lo_c > running_max + p99·remaining_rise + buffer). Reuses _maker_locked_exercise via
        the min→max arg map (official_running_max=lo_c, hi_c=ceiling ⇒ margin = lo_c−ceiling).
        NO capital unless THERMO_MAKER_LIVE; logs every candidate to thermo_maker.jsonl. Tag
        WEATHER_THERMO keeps PnL isolated so the kill criterion can be evaluated."""
        if not (THERMO_MAKER_ENABLED and self._today_markets_cache):
            return
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        import time as _time
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.date().isoformat()
        log_dir = Path("logs/shadow/hot") / today_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "thermo_maker.jsonl"
        now_ts = _time.time()
        if getattr(self, "_thermo_fire_date", "") != today_str:
            self._thermo_fire_date = today_str
            self._thermo_fires_today = 0

        written = 0
        live_fired = 0
        for entry in self._today_markets_cache:
            mkt = entry.get("mkt") or {}
            city = entry.get("city"); icao = entry.get("icao")
            if not city or not icao:
                continue
            if icao in M1_BETA_PROBE_ORACLE_BLOCK_ICAO:        # wrong-oracle cities
                continue
            question = mkt.get("question", "")
            if "highest" not in question.lower():               # MAX markets only (running_max semantics)
                continue
            lo_c, hi_c, is_celsius = _parse_outcome(question)
            if lo_c is None:                                    # need a lower edge to lock from above
                continue
            end_date = (mkt.get("endDate") or "")[:10]
            _tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
            _local_today = (now_utc + timedelta(hours=_tz_h)).date().isoformat()
            if end_date != _local_today:
                continue
            metar = self._icao_metar_cache.get(icao) or {}
            rm = metar.get("official_running_max_c")            # PROVENANCE-CLEAN only
            if rm is None:
                continue
            if metar.get("running_max_date", "") != _local_today:
                continue
            slug = (city or "").lower().replace(" ", "-")
            month = now_utc.month; hour = now_utc.hour
            peak_hour = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month)
            if peak_hour is None or hour >= peak_hour:          # PRE-peak only (the earliness window)
                continue
            mean_rise = CITY_REMAINING_RISE.get(slug, {}).get(month, {}).get(hour, 0.0)
            if mean_rise <= 0:                                  # no rise data for this city/time
                continue
            # Pre-peak running_max ≈ current temp, so ceiling ≈ running_max + p99 remaining rise.
            ceiling = rm + mean_rise * (1.0 + THERMO_MAKER_P99_K * RR_CV)
            margin = lo_c - ceiling                             # how far the bucket floor is above the p99 max
            if margin < THERMO_MAKER_MIN_MARGIN_C:
                continue
            ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            no_tok = ids[1] if len(ids) > 1 else None
            if not no_tok:
                continue
            no_book = await self._fetch_book_levels(no_tok, n=3)
            no_ask = (no_book["asks"][0]["price"] if no_book.get("asks") else None)
            best_bid = (no_book["bids"][0]["price"] if no_book.get("bids") else None)
            cond_id = mkt.get("conditionId") or mkt.get("condition_id") or ""
            if (THERMO_MAKER_LIVE and no_ask is not None
                    and self._thermo_fires_today < THERMO_MAKER_MAX_DAILY):
                try:
                    await self._maker_locked_exercise(
                        city=city, no_token_id=no_tok,
                        no_book={"best_bid": best_bid, "best_ask": no_ask},
                        no_ask_clob=no_ask, hi_c=ceiling,
                        official_running_max=lo_c, now_ts=now_ts, now_utc=now_utc,
                        icao=icao, question=question, end_date=end_date,
                        lo_c=lo_c, condition_id=cond_id, entry_class="WEATHER_THERMO")
                    self._thermo_fires_today += 1
                    live_fired += 1
                except Exception:
                    logger.exception("[THERMO] maker error %s", city)
            rec = {
                "schema_version": 1, "record_type": "thermo_maker_candidate",
                "ts_s": round(now_ts, 1), "city": city, "icao": icao,
                "token_id": no_tok, "question": question[:80],
                "bucket_lo_c": round(lo_c, 3), "official_running_max_c": round(float(rm), 3),
                "mean_rise_c": round(mean_rise, 3), "ceiling_c": round(ceiling, 3),
                "margin_c": round(margin, 3), "hour_utc": hour, "peak_hour_utc": peak_hour,
                "no_ask": no_ask, "end_date": end_date,
            }
            with open(log_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            written += 1
        if written:
            logger.info("[THERMO] %d upper-tail thermo-ceiling candidates, %d live maker posts this cycle",
                        written, live_fired)

    def _peakscalp_q(self, slug: str, month: int, hour: int,
                     headroom_c: float):
        """q(city, month, local_hour, headroom) from config/peakscalp_q.json.
        Same convention as analysis/weather/peakscalp_score_v2.py: take the max
        q over headroom bins {0.2,0.4,0.6,1.0}°C that the actual headroom
        covers (deeper-bin q is a lower bound for shallower headroom).
        Returns None when the cell is missing (no 4yr obs for that slot)."""
        if not hasattr(self, "_ps_qtab"):
            try:
                with open(PEAKSCALP_Q_PATH) as f:
                    self._ps_qtab = json.load(f)
            except Exception:
                self._ps_qtab = {}
        cell = (self._ps_qtab.get(slug, {}).get(f"m{month}", {})
                or {}).get(f"h{hour}")
        if not cell:
            return None
        best = None
        for k, d in (("d02", 0.2), ("d04", 0.4), ("d06", 0.6), ("d10", 1.0)):
            if d <= headroom_c + 1e-9 and k in cell:
                v = cell[k]
                best = v if best is None else max(best, v)
        return best

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
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        import time as _time

        today_str = datetime.now(timezone.utc).date().isoformat()
        log_dir = Path("logs/shadow/hot") / today_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "metar_lockout.jsonl"

        now_ts = _time.time()
        now_utc = datetime.now(timezone.utc)

        # Purge stale watchlist entries (token resolved/expired > 24h ago).
        # Prevents unbounded memory growth; max_sec_since already blocks firing,
        # but old entries still get checked on every BBO callback.
        _stale = [tid for tid, w in self._m1_lockout_watchlist.items()
                  if now_ts - w.get("first_ts", now_ts) > M1_BETA_PROBE_MAX_SEC_SINCE]
        for tid in _stale:
            self._m1_lockout_watchlist.pop(tid, None)
            self._lockout_first_seen.pop(tid, None)

        # Group markets by (event_id, city) to extract event-level resolution time
        candidates_written = 0
        for entry in self._today_markets_cache:
            mkt = entry.get("mkt") or {}
            city = entry.get("city")
            icao = entry.get("icao")
            if not city or not icao:
                continue

            # Same-day only — lockout logic is meaningless for tomorrow's markets.
            # Compare against LOCAL date for this city: running_max resets at local
            # midnight, so using UTC date causes false lockouts for Western-hemisphere
            # cities in the 00:00–local-midnight UTC window (e.g. Toronto 00:00–05:00
            # UTC, São Paulo 00:00–03:00 UTC) where UTC day is already "tomorrow" but
            # the running_max was accumulated for the previous local day.
            end_date = (mkt.get("endDate") or "")[:10]
            _tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
            _local_today = (now_utc + timedelta(hours=_tz_h)).date().isoformat()
            if end_date != _local_today:
                continue

            metar = self._icao_metar_cache.get(icao) or {}
            running_max = metar.get("running_max_c")
            if running_max is None:
                continue
            # Reject stale cache from previous local day — reset fires in
            # merge_into_cache only when a new obs arrives, so at local midnight
            # the cache still holds yesterday's running_max until the first poll.
            if metar.get("running_max_date", "") != _local_today:
                continue

            question = mkt.get("question", "")
            lo_c, hi_c, is_celsius = _parse_outcome(question)

            # ── TEMPORAL-LOCK SHADOW (P5, 2026-06-09) — no capital ──
            # Buckets ABOVE the running max late in the local day: once the
            # diurnal peak has passed, they become physically unreachable.
            # Backtest (analysis/weather/temporal_lock_backtest.py, 72k
            # city-days 2021-24 hourly = oracle resolution): P(final_max −
            # run_max > 1.0°C | local hour ≥ 18) = 0.04–0.18% Apr–Oct but ~1%
            # Dec–Jan (high-lat nocturnal warm advection: Helsinki/Moscow/NYC/
            # Toronto worst) ⇒ any live gate must be month-aware. Shadow logs
            # candidates wide (hour ≥ 15, gap ≥ 0.5°C) with gamma quotes so a
            # resolution join + fillability analysis picks the live
            # (hour, delta, month) gate. One record per (bucket, hour, day).
            _lh = (now_utc + timedelta(hours=_tz_h)).hour
            if (lo_c is not None and (hi_c is None or running_max < hi_c + 0.05)
                    and _lh >= 15
                    and (float(lo_c) - float(running_max)) >= 0.5):
                if not hasattr(self, "_tlock_seen"):
                    self._tlock_seen = set()
                if len(self._tlock_seen) > 50000:
                    self._tlock_seen.clear()
                _tlk = (mkt.get("conditionId") or question, _local_today, _lh)
                if _tlk not in self._tlock_seen:
                    self._tlock_seen.add(_tlk)
                    try:
                        (log_dir / "temporal_lock.jsonl").open("a").write(json.dumps({
                            "schema_version": 1,
                            "record_type": "temporal_lock_candidate",
                            "ts_utc": now_utc.isoformat(), "ts_s": int(now_ts),
                            "city": city, "icao": icao, "end_date": end_date,
                            "question": question,
                            "local_hour": _lh, "month": now_utc.month,
                            "bucket_lo_c_padded": round(float(lo_c), 4),
                            "bucket_hi_c_padded": (round(float(hi_c), 4)
                                                   if hi_c is not None else None),
                            "running_max_c": round(float(running_max), 3),
                            "official_running_max_c": (
                                round(float(metar["official_running_max_c"]), 3)
                                if metar.get("official_running_max_c") is not None
                                else None),
                            "gap_above_c": round(float(lo_c) - float(running_max), 3),
                            "gamma_best_bid": mkt.get("bestBid"),
                            "gamma_best_ask": mkt.get("bestAsk"),
                            "is_celsius_market": is_celsius,
                        }) + "\n")
                    except Exception:
                        pass

            # ── PEAKSCALP Phase-0 SHADOW (2026-06-12, user GO) — no capital ──
            # Convergence-scalp candidate: the bucket CONTAINING the OFFICIAL
            # running max passes q(city, month, local_hour, headroom) ≥ gate →
            # log the real YES book at gate-pass plus timed follow-ups, so the
            # join measures fillability (ask px/depth) and convergence latency.
            # Provenance: official_running_max_c ONLY — the q-table is built on
            # oracle-grade hourly obs; gating on the broad running_max here
            # would recreate the false-lockout bug class.
            if PEAKSCALP_SHADOW and icao not in PEAKSCALP_BLOCK_ICAO:
                _ps_orm = metar.get("official_running_max_c")
                _ps_tids = _parse_token_ids(mkt.get("clobTokenIds", []))
                _ps_tid = _ps_tids[0] if _ps_tids else None
                if not hasattr(self, "_ps_watch"):
                    self._ps_watch, self._ps_seen = {}, set()
                if len(self._ps_watch) > 500:
                    self._ps_watch = {
                        t: w for t, w in self._ps_watch.items()
                        if now_ts - w["pass_ts"] <= PEAKSCALP_FOLLOWUP_SEC}
                if len(self._ps_seen) > 50000:
                    self._ps_seen.clear()
                _ps_lt = now_utc + timedelta(hours=_tz_h)
                _ps_in = (_ps_orm is not None and lo_c is not None
                          and hi_c is not None
                          and float(lo_c) <= float(_ps_orm) < float(hi_c))
                _ps_head = (float(hi_c) - float(_ps_orm)) if _ps_in else None
                _ps_q = (self._peakscalp_q(
                             (city or "").lower().replace(" ", "-"),
                             _ps_lt.month, _ps_lt.hour, _ps_head)
                         if _ps_in else None)
                _ps_w = self._ps_watch.get(_ps_tid) if _ps_tid else None
                _ps_rec = None
                if (_ps_w is not None
                        and now_ts - _ps_w["pass_ts"] <= PEAKSCALP_FOLLOWUP_SEC
                        and now_ts - _ps_w["last_snap"] >= PEAKSCALP_FOLLOWUP_GAP):
                    _ps_rec = "followup"
                elif (_ps_w is None and _ps_tid is not None and _ps_q is not None
                      and _ps_q >= PEAKSCALP_GATE
                      and (_ps_tid, _local_today) not in self._ps_seen):
                    self._ps_seen.add((_ps_tid, _local_today))
                    _ps_rec = "gate_pass"
                if _ps_rec is not None:
                    try:
                        _ps_bk = await self._fetch_book_levels(_ps_tid, n=3)
                    except Exception:
                        _ps_bk = None
                    if _ps_rec == "gate_pass":
                        self._ps_watch[_ps_tid] = {"pass_ts": now_ts,
                                                   "last_snap": now_ts}
                    else:
                        self._ps_watch[_ps_tid]["last_snap"] = now_ts
                    try:
                        (log_dir / "peakscalp_shadow.jsonl").open("a").write(
                            json.dumps({
                                "schema_version": 1,
                                "record_type": f"peakscalp_{_ps_rec}",
                                "ts_utc": now_utc.isoformat(),
                                "ts_s": round(now_ts, 1),
                                "city": city, "icao": icao,
                                "end_date": end_date,
                                "question": mkt.get("question", ""),
                                "condition_id": mkt.get("conditionId"),
                                "token_id": _ps_tid,
                                "bucket_lo_c": (round(float(lo_c), 3)
                                                if lo_c is not None else None),
                                "bucket_hi_c": (round(float(hi_c), 3)
                                                if hi_c is not None else None),
                                "official_running_max_c": (
                                    round(float(_ps_orm), 3)
                                    if _ps_orm is not None else None),
                                "running_max_c": round(float(running_max), 3),
                                "headroom_c": (round(_ps_head, 3)
                                               if _ps_head is not None else None),
                                "local_hour": _ps_lt.hour,
                                "local_month": _ps_lt.month,
                                "q": _ps_q,
                                "sec_since_pass": (
                                    0.0 if _ps_rec == "gate_pass"
                                    else round(now_ts
                                               - self._ps_watch[_ps_tid]["pass_ts"], 1)),
                                "gamma_best_bid": mkt.get("bestBid"),
                                "gamma_best_ask": mkt.get("bestAsk"),
                                "book_bids": (_ps_bk or {}).get("bids"),
                                "book_asks": (_ps_bk or {}).get("asks"),
                                "is_celsius_market": is_celsius,
                            }) + "\n")
                    except Exception:
                        pass

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
            is_new_lockout = first_seen is None
            if is_new_lockout:
                first_seen = now_ts
                self._lockout_first_seen[token_id] = first_seen

            # Subscribe YES + NO tokens to CLOB WebSocket the moment lockout is detected.
            # After this, _on_weather_bbo fires in milliseconds on every price change —
            # no waiting for the next METAR poll cycle.
            no_token_id_early = token_ids[1] if len(token_ids) >= 2 else None
            depth_c_early = round(float(running_max) - float(hi_c), 2)
            if M1_BETA_PROBE_ENABLED and no_token_id_early is not None:
                if token_id not in self._m1_lockout_watchlist:
                    self._m1_lockout_watchlist[token_id] = {
                        "no_token_id": no_token_id_early,
                        "city": city, "icao": icao, "end_date": end_date,
                        "lo_c": lo_c, "hi_c": hi_c,
                        "depth_c": depth_c_early,
                        "running_max": float(running_max),
                        "question": mkt.get("question", ""),
                        "first_ts": first_seen,
                        "mkt": mkt,
                        "neg_risk": mkt.get("negRisk", True),
                    }
                    try:
                        self.bot.feed._clob_ws_sub_queue.put_nowait(
                            [token_id, no_token_id_early]
                        )
                    except Exception:
                        pass
                else:
                    # Refresh depth_c and running_max each scan — frozen values
                    # cause probe log to show stale depth at fire time.
                    self._m1_lockout_watchlist[token_id]["depth_c"] = depth_c_early
                    self._m1_lockout_watchlist[token_id]["running_max"] = float(running_max)
                    if is_new_lockout:
                        logger.info(
                            "[M1β] WS subscribed %s/%s YES=%s NO=%s depth=%.2f°C",
                            city, end_date, token_id[:8], no_token_id_early[:8], depth_c_early,
                        )

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

            # CLOB-based depth: Gamma bestBid lags CLOB heavily on weather markets.
            # When Gamma shows 0.62 but CLOB is at 0.15, the Gamma-based cap (0.38)
            # misses NO asks sitting at 0.85. Use CLOB bid for the authoritative check.
            if yes_bid_clob is not None:
                _no_ask_clob_implied = max(0.0, 1.0 - yes_bid_clob)
                no_ask_usd_at_clob_implied = round(sum(
                    lvl["usd"] for lvl in no_book.get("asks", [])
                    if lvl["price"] <= _no_ask_clob_implied + tol
                ), 2)
            else:
                no_ask_usd_at_clob_implied = no_ask_usd_at_implied

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
                # official (AWC/NWS-only) running max — the oracle-provenance field.
                # Without it the offline real-vs-trap split is impossible: 06-10
                # join showed $29.7k of the naive broad-feed "harvest" was 5 false
                # lockouts (HK/Tokyo sub-hourly feeds) vs $3.2k real.
                "official_running_max_c": (
                    round(float(metar["official_running_max_c"]), 3)
                    if metar.get("official_running_max_c") is not None else None),
                "asos_running_max_c": round(float(metar.get("running_max_c") or running_max), 3),
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
                "no_ask_usd_at_clob_implied": no_ask_usd_at_clob_implied,
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

            # === M1 β-PROBE: single fixed signal, live $2 limit at displayed +1¢ ===
            if M1_BETA_PROBE_ENABLED and no_token_id is not None:
                try:
                    await self._m1_beta_probe_evaluate(
                        now_ts=now_ts, now_utc=now_utc, first_seen=first_seen,
                        mkt=mkt, city=city, icao=icao, end_date=end_date,
                        question=question, lo_c=lo_c, hi_c=hi_c,
                        running_max=float(running_max), yes_bid=yes_bid_f,
                        yes_bid_clob=yes_bid_clob,
                        no_token_id=no_token_id, no_ask_clob=no_ask_clob,
                        no_book=no_book,
                        no_ask_usd_at_implied=no_ask_usd_at_implied,
                        no_ask_usd_at_clob_implied=no_ask_usd_at_clob_implied,
                        seconds_to_close=seconds_to_close,
                        official_running_max=metar.get("official_running_max_c"),
                    )
                except Exception:
                    logger.exception("[M1β] probe error %s", city)

        if candidates_written:
            logger.info(
                "[WA] LOCKOUT_SHADOW logged %d candidates this cycle",
                candidates_written,
            )

    # === M1 β-PROBE implementation ============================================
    def _m1_beta_probe_load_state(self) -> dict:
        """State: {date, fires_today, total_fires, fires_by_token, bucket_fire_seq}.
        fires_by_token maps no_token_id -> [list of layer names already fired].
        bucket_fire_seq maps no_token_id -> count of fires (for tagging).
        Per-day resets: fires_today only.
        Persists: total_fires, fires_by_token, bucket_fire_seq.
        fires_by_token is token-scoped (no_token_id unique per market) so resetting
        at UTC midnight caused double-fires on Western-hemisphere markets that straddle
        midnight — a Dallas May-27 bucket could re-fire all layers after 00:00 UTC."""
        from datetime import datetime, timezone
        from pathlib import Path as _P
        today = datetime.now(timezone.utc).date().isoformat()
        path = _P(M1_BETA_PROBE_STATE_PATH)
        if path.exists():
            try:
                st = json.loads(path.read_text())
            except Exception:
                st = {}
        else:
            st = {}
        if st.get("date") != today:
            st = {
                "date": today,
                "fires_today": 0,
                "total_fires": st.get("total_fires", 0),
                "fires_by_token": st.get("fires_by_token", {}),  # persist — token_ids are unique per market
                "bucket_fire_seq": st.get("bucket_fire_seq", {}),  # token_id -> int
            }
        st.setdefault("fires_by_token", {})
        st.setdefault("bucket_fire_seq", {})
        st.setdefault("total_fires", 0)
        return st

    def _m1_beta_probe_save_state(self, st: dict) -> None:
        from pathlib import Path as _P
        try:
            _P(M1_BETA_PROBE_STATE_PATH).write_text(json.dumps(st))
        except Exception:
            logger.exception("[M1β] state save failed")

    async def _maker_locked_exercise(
        self, *, city: str, no_token_id: str, no_book: dict,
        no_ask_clob, hi_c, official_running_max, now_ts: float, now_utc,
        icao: str = "", question: str = "", end_date: str = "",
        lo_c=None, condition_id: str = "", entry_class: str = "WEATHER_M1_PROBE",
    ) -> None:
        """Controlled first-exercise of the maker_buy primitive on a provenance-clean
        locked bucket (caller already cleared M1β's gates ⇒ NO physically certain,
        AS=0). SHADOW (default): log the resting NO bid we WOULD post. LIVE: post it
        ($4 cap, ≤MAKER_EXERCISE_MAX_ORDERS, breaker-gated, official-margin ≥1°C only).
        In-memory caps reset on restart — intended; stage 3 is monitored."""
        self._maker_state_init()
        if no_token_id in self._maker_ex_seen:
            return
        if no_ask_clob is None or no_ask_clob <= 0.02:
            return
        # Non-crossing resting NO bid: inside [no_bid, no_ask], strictly below the ask.
        no_bid = (no_book or {}).get("best_bid")
        if no_bid is not None and float(no_bid) > 0:
            q_price = round((float(no_bid) + no_ask_clob) / 2.0, 2)
        else:
            q_price = round(no_ask_clob - 0.02, 2)
        q_price = min(q_price, round(no_ask_clob - 0.01, 2))   # strictly non-crossing
        q_price = max(0.01, q_price)
        if q_price >= no_ask_clob:
            return
        # 2026-06-09: skip dead-weight deep bids on PHYSICAL locks (≈0% fill at ~0.99, but they
        # rest forever and burn the $40 breaker). Reserve maker for the fat-edge zone where
        # NO-selling flow exists. Not seen-marked → re-posts if the book drops into range.
        # Thermo exempt — it intentionally rests deep early to capture the 4h reprice.
        if entry_class != "WEATHER_THERMO" and q_price > MAKER_EXERCISE_MAX_BID:
            return
        size = round(MAKER_EXERCISE_STAKE_USD / q_price, 2)
        margin = ((official_running_max - hi_c)
                  if (official_running_max is not None and hi_c is not None) else None)
        rec = {
            "ts": round(now_ts), "city": city, "no_token": no_token_id,
            "no_bid": no_bid, "no_ask": no_ask_clob, "q_price": q_price,
            "size": size, "stake": MAKER_EXERCISE_STAKE_USD,
            "clean_margin_c": (round(margin, 2) if margin is not None else None),
            "live": MAKER_EXERCISE_LIVE, "orders_so_far": self._maker_ex_orders,
        }
        log_dir = Path("logs/shadow/hot") / now_utc.date().isoformat()
        log_dir.mkdir(parents=True, exist_ok=True)

        if not MAKER_EXERCISE_LIVE:
            self._maker_ex_seen.add(no_token_id)
            rec["mode"] = "SHADOW"
            with (log_dir / "maker_exercise.jsonl").open("a") as f:
                f.write(json.dumps(rec) + "\n")
            logger.info("[MAKER-EX] SHADOW %s NO bid @ %.2f (ask %.2f bid %s) size %.1f margin=%s",
                        city, q_price, no_ask_clob, str(no_bid), size,
                        f"{margin:.2f}" if margin is not None else "?")
            return

        # ── LIVE (monitored) — M1β's validated locked population only ──
        # Caller already cleared M1β's provenance gate; fire on the market-agreed
        # slice (no_ask ≥ 0.90, 95.6% OOS) OR the physical-proof fat band (margin ≥1°C).
        _market_agreed = no_ask_clob is not None and no_ask_clob >= M1_BETA_PROBE_NO_ASK_MARKET_AGREE
        _margin_clean  = margin is not None and margin >= MAKER_EXERCISE_LIVE_MIN_MARGIN_C
        if not (_market_agreed or _margin_clean):
            return
        if self._maker_ex_orders >= MAKER_EXERCISE_MAX_ORDERS:
            return
        ok_cash, why = self._maker_cash_gate(MAKER_EXERCISE_STAKE_USD)
        if not ok_cash:
            logger.info("[MAKER-EX] cash gate: skip %s (%s)", city, why)
            return
        risk = getattr(self.bot, "risk", None)
        bankroll = float(getattr(getattr(risk, "bankroll", None), "capital", 0.0) or 0.0)
        ok, reason = self._maker_breaker.precheck(bankroll, MAKER_EXERCISE_STAKE_USD)
        if not ok:
            logger.warning("[MAKER-EX] LIVE breaker blocked %s: %s", city, reason)
            return
        self._maker_ex_seen.add(no_token_id)
        try:
            from execution.order_manager import OrderStatus
            result = await self.bot.orders.maker_buy(
                token_id=no_token_id, price=q_price,
                stake_usd=MAKER_EXERCISE_STAKE_USD, neg_risk=True)
        except Exception as e:
            logger.error("[MAKER-EX] LIVE maker_buy raised %s: %s", city, e)
            return
        self._maker_ex_orders += 1
        oid = getattr(result, "order_id", "") or ""
        status = getattr(result, "status", None)
        if status == OrderStatus.RESTING and oid:
            self._maker_breaker.register_resting(oid, MAKER_EXERCISE_STAKE_USD)
            # Hand the order to the fill→position tracker (resolution loop polls it).
            self._maker_resting[oid] = {
                "token_id": no_token_id, "city": city, "icao": icao,
                "question": question, "end_date": end_date,
                "lo_c": lo_c, "hi_c": hi_c, "condition_id": condition_id,
                "q_price": q_price, "size": size, "matched": 0.0,
                "entry_class": entry_class,
            }
            self._maker_resting_save()
        rec["mode"] = "LIVE"
        rec["order_id"] = oid
        rec["status"] = str(status)
        with (log_dir / "maker_exercise.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")
        logger.warning("[MAKER-EX] LIVE posted %s NO @ %.2f size %.1f order=%s status=%s (#%d/%d) exposure=$%.2f",
                       city, q_price, size, str(oid)[:12], str(status),
                       self._maker_ex_orders, MAKER_EXERCISE_MAX_ORDERS,
                       self._maker_breaker.exposure_usd())

    async def _fade_evaluate(
        self, *, slug: str, city: str, icao: str, mkt: dict,
        lo_c: float, hi_c: float, no_token_id: str,
        no_ask: float, no_depth_usd: float, no_book: dict,
        official_rm: float, phase: str, end_date: str, question: str,
        now_ts: float, now_utc, seconds_to_close,
    ) -> None:
        """LIVE fade fire: buy NO on the prime bin immediately above the official
        running_max (resolution hourly-sampling-bias edge). Gates already checked by
        the caller; this does the authoritative dedup/sizing/order/registration.
        Mirrors the M1β fill→register path (tag WEATHER_FADE so the existing settler
        books it). Isolated — wrapped by the caller's try/except."""
        risk = self.bot.risk
        if not hasattr(self, "_fade_fired"):
            self._fade_fired = set()
        # Dedup: one fade per NO token; never double a token already held.
        if no_token_id in self._fade_fired:
            return
        if no_token_id in getattr(risk, "open_positions", {}):
            return

        # 2026-06-03 user directive: fade sizes FLAT at FADE_MAX_STAKE (no Kelly haircut) —
        # the ~98-99% backtest WR makes the prime-bin fade high-conviction. Bounded only by
        # the visible fillable NO depth so we never over-size the book.
        stake = min(FADE_MAX_STAKE, float(no_depth_usd))
        if stake < FADE_MIN_SHARES * no_ask:      # fewer than 5 fillable shares → skip
            return

        intended_price = round(min(0.99, no_ask + 0.01), 4)
        margin_c = round(float(lo_c) - float(official_rm), 3)
        condition_id = mkt.get("conditionId", "") or mkt.get("condition_id", "")
        neg_risk = mkt.get("negRisk", True)

        log_dir = Path("logs/shadow/hot") / now_utc.date().isoformat()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "fade_live.jsonl"
        pre = {
            "record_type": "fade_live", "phase_rec": "submit", "ts": now_ts,
            "city": city, "icao": icao, "end_date": end_date, "question": question,
            "condition_id": condition_id, "no_token_id": no_token_id,
            "bucket_lo_c": round(lo_c, 4), "bucket_hi_c": round(hi_c, 4),
            "official_running_max_c": round(float(official_rm), 3),
            "gap_above_official_c": margin_c, "diurnal_phase": phase,
            "no_ask": round(no_ask, 4), "no_depth_usd": round(float(no_depth_usd), 2),
            "intended_price": intended_price, "stake_usd": round(stake, 2),
            "kelly_f_star": round(f_star, 4), "win_prior": FADE_WIN_PRIOR,
            "sec_to_close": int(seconds_to_close) if seconds_to_close is not None else None,
        }
        try:
            log_path.open("a").write(json.dumps(pre) + "\n")
        except Exception:
            logger.debug("[FADE] pre-log fail", exc_info=True)

        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus
        logger.info("[FADE] FIRE %s bin[%.1f,%.1f] NO@%.3f stake=$%.1f off_rm=%.2f gap=%.2f°C %s",
                    city, lo_c, hi_c, intended_price, stake, official_rm, margin_c, phase)
        try:
            fill = await self.bot.orders.limit_buy(
                token_id=no_token_id, intended_price=intended_price,
                stake_usd=stake, direction=_Dir.BUY_NO, neg_risk=neg_risk,
                fast_fail=False,
            )
        except Exception as e:
            logger.exception("[FADE] order error %s", city)
            try:
                log_path.open("a").write(json.dumps(
                    {**pre, "phase_rec": "submit_error", "error": str(e)}) + "\n")
            except Exception:
                pass
            return

        # Count the attempt regardless of fill (one chance per token).
        self._fade_fired.add(no_token_id)
        filled = (fill.status == OrderStatus.FILLED and fill.total_size > 0)
        fill_price = float(fill.avg_fill_price) if filled else None
        fill_size = float(fill.total_size) if filled else 0.0
        try:
            log_path.open("a").write(json.dumps({
                **pre, "phase_rec": "result", "filled": filled,
                "fill_avg_price": fill_price, "fill_size_shares": fill_size,
                "fill_status": str(fill.status),
            }) + "\n")
        except Exception:
            pass

        if not filled:
            logger.info("[FADE] no-fill %s (status=%s)", city, fill.status)
            return
        if no_token_id in getattr(risk, "open_positions", {}):
            return  # raced an M1β/other fill on same token — don't overwrite
        risk.open_position(
            token_id=no_token_id, asset="WEATHER", direction=_Dir.BUY_NO,
            stake=fill_size * fill_price, entry_price=fill_price,
            tpsl=_TPSL(take_profit=0.0, stop_loss=0.0, tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
            condition_id=condition_id, window_end_ts=0.0, is_bond=True,
            bond_outcome_direction="down", bond_entry_class="WEATHER_FADE",
        )
        meta = self.bot._open_meta.setdefault(no_token_id, {})
        meta["signal_source"] = f"WEATHER/{city}/WEATHER_FADE"
        meta["city"] = city
        meta["icao"] = icao
        meta["weather_question"] = question
        meta["weather_date"] = end_date
        meta["bucket_lo_c"] = lo_c
        meta["bucket_hi_c"] = hi_c
        meta["fade_first_signal_state"] = pre
        logger.info("[FADE] FILLED %s NO@%.4f size=%.1f stake=$%.2f",
                    city, fill_price, fill_size, fill_size * fill_price)

    async def _favorite_evaluate(
        self, *, slug: str, city: str, icao: str, mkt: dict,
        lo_c: float, hi_c: float, yes_token_id: str,
        yes_ask: float, yes_depth_usd: float, phase: str,
        end_date: str, question: str, now_ts: float, now_utc, seconds_to_close,
    ) -> None:
        """LIVE favorite-YES fire (user GO-LIVE 2026-06-03, Tier-3 override of n≥100):
        buy YES on a confident OPEN-ENDED cumulative-tail bucket priced [0.60,0.98]
        (favorite-longshot underpricing; n=10-19 TREND-ONLY ⇒ bounded deploy). Gates
        already checked by the caller; this does dedup/sizing/order/registration. Tag
        WEATHER_FAVYES so the existing settler books it. Isolated by caller try/except."""
        risk = self.bot.risk
        if not hasattr(self, "_favyes_fired"):
            self._favyes_fired = set()
        if yes_token_id in self._favyes_fired:
            return
        if yes_token_id in getattr(risk, "open_positions", {}):
            return
        # Hong Kong resolves against HK Observatory, not VHHH — blocked system-wide
        # (M1β/fade do the same). The favorite calibration doesn't trust the HK oracle.
        if icao == "VHHH":
            return
        # Per-city confidence cutoff (2026-06-04): skip cities whose per-(city,month)
        # forecast σ is too wide (> YES_SIGMA_CUTOFF, the SAME gate the engine YES
        # ladder uses) — the favorite-longshot edge is thinnest exactly where our
        # model is least accurate (SF/guangzhou/taipei/chengdu/chongqing; SF also has
        # the microclimate/oracle problem). Keeps the two YES paths in sync.
        try:
            from strategy.stwa_engine import (_peak_sigma_for as _psf,
                                              _current_month as _cm,
                                              YES_SIGMA_CUTOFF as _SCUT)
            _pc = getattr(self._stwa, "_peak_calib", {}) if self._stwa else {}
            _sig = _psf(_pc, slug, _cm())
            if _sig > _SCUT:
                logger.debug("[FAVYES] σ-cutoff %s: σ=%.2f > %.2f — skip (model too loose)",
                             city, _sig, _SCUT)
                return
        except Exception:
            pass
        # Bounded flat stake (small — unvalidated edge), capped by visible fillable depth.
        stake = min(FAVYES_STAKE_USD, float(yes_depth_usd))
        if stake < FAVYES_MIN_SHARES * yes_ask:   # fewer than 5 fillable shares → skip
            return
        intended_price = round(min(0.99, yes_ask + 0.01), 4)
        condition_id = mkt.get("conditionId", "") or mkt.get("condition_id", "")
        neg_risk = mkt.get("negRisk", True)

        log_dir = Path("logs/shadow/hot") / now_utc.date().isoformat()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "favyes_live.jsonl"
        pre = {
            "record_type": "favyes_live", "phase_rec": "submit", "ts": now_ts,
            "city": city, "icao": icao, "end_date": end_date, "question": question,
            "condition_id": condition_id, "yes_token_id": yes_token_id,
            "bucket_lo_c": round(lo_c, 4), "bucket_hi_c": round(hi_c, 4),
            "yes_ask": round(yes_ask, 4), "yes_depth_usd": round(float(yes_depth_usd), 2),
            "intended_price": intended_price, "stake_usd": round(stake, 2),
            "diurnal_phase": phase,
            "sec_to_close": int(seconds_to_close) if seconds_to_close is not None else None,
        }
        try:
            log_path.open("a").write(json.dumps(pre) + "\n")
        except Exception:
            logger.debug("[FAVYES] pre-log fail", exc_info=True)

        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus
        logger.info("[FAVYES] FIRE %s bin[%.1f,%.1f] YES@%.3f stake=$%.1f %s",
                    city, lo_c, hi_c, intended_price, stake, phase)
        try:
            fill = await self.bot.orders.limit_buy(
                token_id=yes_token_id, intended_price=intended_price,
                stake_usd=stake, direction=_Dir.BUY_YES, neg_risk=neg_risk,
                fast_fail=False,
            )
        except Exception as e:
            logger.exception("[FAVYES] order error %s", city)
            try:
                log_path.open("a").write(json.dumps(
                    {**pre, "phase_rec": "submit_error", "error": str(e)}) + "\n")
            except Exception:
                pass
            return

        filled = (fill.status == OrderStatus.FILLED and fill.total_size > 0)
        fill_price = float(fill.avg_fill_price) if filled else None
        fill_size = float(fill.total_size) if filled else 0.0
        try:
            log_path.open("a").write(json.dumps({
                **pre, "phase_rec": "result", "filled": filled,
                "fill_avg_price": fill_price, "fill_size_shares": fill_size,
                "fill_status": str(fill.status),
            }) + "\n")
        except Exception:
            pass

        if not filled:
            # Do NOT dedup on a no-fill: the usual cause is no free USDC right now.
            # Leaving the token un-fired lets it fill on a later cycle once cash is
            # freed (manual sells / 0.99 exits) — "fire whenever USDC is available."
            logger.info("[FAVYES] no-fill %s (status=%s)", city, fill.status)
            return
        # Real fill → dedup this token for the day (one held position per favorite tail).
        self._favyes_fired.add(yes_token_id)
        self._favyes_fires_today = getattr(self, "_favyes_fires_today", 0) + 1
        if yes_token_id in getattr(risk, "open_positions", {}):
            return  # raced another fill on same token — don't overwrite
        risk.open_position(
            token_id=yes_token_id, asset="WEATHER", direction=_Dir.BUY_YES,
            stake=fill_size * fill_price, entry_price=fill_price,
            tpsl=_TPSL(take_profit=0.0, stop_loss=0.0, tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
            condition_id=condition_id, window_end_ts=0.0, is_bond=True,
            bond_outcome_direction="up", bond_entry_class="WEATHER_FAVYES",
        )
        meta = self.bot._open_meta.setdefault(yes_token_id, {})
        meta["signal_source"] = f"WEATHER/{city}/WEATHER_FAVYES"
        meta["city"] = city
        meta["icao"] = icao
        meta["weather_question"] = question
        meta["weather_date"] = end_date
        meta["bucket_lo_c"] = lo_c
        meta["bucket_hi_c"] = hi_c
        meta["favyes_first_signal_state"] = pre
        logger.info("[FAVYES] FILLED %s YES@%.4f size=%.1f stake=$%.2f",
                    city, fill_price, fill_size, fill_size * fill_price)

    def _ofi_from_tape(self, now_ts: float) -> dict:
        """Rolling OFI per condition_id. Primary source = the maker_flow.jsonl tail
        (the probe's weather trade feed); when OFI_WS_ENABLED the sub-second WS
        last_trade_price buffer is MERGED in (txhash-deduped, file wins on a shared
        hash) so the freshest ≤180s window isn't poll-stale. ask-side(+) = YES-buy
        pressure. Returns {cid: (ofi, vol_usd)} for buckets with >= OFI_MIN_VOL_USD."""
        from datetime import datetime as _dt, timezone as _tz
        out: dict = {}
        cutoff = now_ts - OFI_WIN_S
        trades: dict = {}   # txhash → (cid, ask_bool, notion); dedups file ↔ WS
        _fsynth = 0
        try:
            path = Path("logs/shadow/hot") / _dt.now(_tz.utc).date().isoformat() / "maker_flow.jsonl"
            if path.exists():
                sz = path.stat().st_size
                with open(path, "rb") as fh:
                    if sz > 2_000_000:
                        fh.seek(sz - 2_000_000)
                        fh.readline()  # drop partial line
                    chunk = fh.read().decode("utf-8", "ignore")
                for line in chunk.splitlines():
                    if "highest-temperature" not in line:
                        continue
                    try:
                        r = json.loads(line)
                        ts = float(r.get("timestamp"))
                    except (ValueError, TypeError):
                        continue
                    if ts < cutoff:
                        continue
                    cid = r.get("conditionId")
                    if not cid:
                        continue
                    try:
                        notion = float(r.get("price")) * float(r.get("size"))
                    except (TypeError, ValueError):
                        continue
                    oc = str(r.get("outcome", "")).lower()
                    sd = str(r.get("side", "")).upper()
                    ask = (oc == "yes" and sd == "BUY") or (oc == "no" and sd == "SELL")
                    th = (r.get("transactionHash") or "").lower()
                    if not th:
                        th = f"_f{_fsynth}"; _fsynth += 1
                    trades[th] = (cid, ask, notion)
        except Exception:
            logger.debug("[OFI] tape read failed", exc_info=True)
        # WS augment: merge the sub-second buffer (file wins on a shared txhash).
        if OFI_WS_ENABLED and self._ofi_ws_buf:
            for th, (rts, cid, ask, notion) in list(self._ofi_ws_buf.items()):
                if rts < cutoff or not cid:
                    continue
                trades.setdefault(th, (cid, ask, notion))
        agg: dict = {}
        for cid, ask, notion in trades.values():
            a = agg.setdefault(cid, [0.0, 0.0])
            a[0] += notion if ask else -notion
            a[1] += notion
        for cid, (signed, vol) in agg.items():
            if vol >= OFI_MIN_VOL_USD:
                out[cid] = (signed / vol, vol)
        return out

    def _ofi_ws_refresh_tokens(self) -> None:
        """Rebuild token_id → (conditionId, yes/no) from the live markets cache so
        the WS knows which weather tokens to subscribe + how to classify each fill."""
        m: dict = {}
        for e in (getattr(self, "_today_markets_cache", None) or []):
            mk = e.get("mkt") or {}
            cid = mk.get("conditionId")
            tids = _parse_token_ids(mk.get("clobTokenIds", []))
            if cid and len(tids) >= 2:
                m[tids[0]] = (cid, "yes")
                m[tids[1]] = (cid, "no")
        self._ofi_ws_tok = m

    def _ofi_ws_prune(self) -> None:
        """Bound the in-mem buffer to ~2× the OFI window."""
        cut = time.time() - OFI_WIN_S * 2
        for th in [k for k, v in self._ofi_ws_buf.items() if v[0] < cut]:
            self._ofi_ws_buf.pop(th, None)

    async def _ofi_ws_loop(self) -> None:
        """Background CLOB market-WS listener: subscribes the weather token universe
        and maintains _ofi_ws_buf (txhash → (recv_ts, cid, ask_bool, notion)) from
        last_trade_price pushes. Side-semantics validated (ofi_ws_validate.py). Pure
        augment — never trades; _ofi_from_tape merges this buffer. Reconnects on drop;
        any failure falls back silently to the file tape."""
        if not OFI_WS_ENABLED:
            return
        while True:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(OFI_WS_URL, timeout=20, heartbeat=10) as ws:
                        self._ofi_ws_subbed = set()
                        last_sub = 0.0
                        logger.info("[OFI-WS] connected")
                        while True:
                            if time.time() - last_sub > OFI_WS_SUB_REFRESH_S:
                                last_sub = time.time()
                                self._ofi_ws_refresh_tokens()
                                new = [t for t in self._ofi_ws_tok if t not in self._ofi_ws_subbed]
                                for i in range(0, len(new), 200):
                                    await ws.send_str(json.dumps({
                                        "auth": {}, "type": "subscribe", "channel": "market",
                                        "assets_ids": new[i:i + 200], "custom_feature_enabled": True}))
                                    self._ofi_ws_subbed.update(new[i:i + 200])
                                self._ofi_ws_prune()
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                            except asyncio.TimeoutError:
                                continue
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    evs = json.loads(msg.data)
                                except Exception:
                                    continue
                                if not isinstance(evs, list):
                                    evs = [evs]
                                for ev in evs:
                                    if ev.get("event_type", ev.get("type")) != "last_trade_price":
                                        continue
                                    th = (ev.get("transaction_hash") or ev.get("transactionHash") or "").lower()
                                    if not th:
                                        continue
                                    res = self._ofi_ws_tok.get(str(ev.get("asset_id") or ev.get("asset") or ""))
                                    if not res:
                                        continue  # unknown token — file tape still catches it
                                    cid, oc = res
                                    sd = str(ev.get("side", "")).upper()
                                    ask = (oc == "yes" and sd == "BUY") or (oc == "no" and sd == "SELL")
                                    try:
                                        notion = float(ev.get("price")) * float(ev.get("size"))
                                    except (TypeError, ValueError):
                                        continue
                                    self._ofi_ws_buf[th] = (time.time(), cid, ask, notion)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logger.info("[OFI-WS] socket closed/error %s", msg.type)
                                break
            except Exception:
                logger.debug("[OFI-WS] loop error", exc_info=True)
            await asyncio.sleep(5.0)  # reconnect backoff

    async def _ofi_manage_exits(self) -> None:
        """v2 exit for WEATHER_OFI positions: leave when the OFI edge dies (our-dir OFI
        < OFI_EXIT_THRESH), or scalp-TP (+OFI_SCALP_TP) hits, or the 20-min backstop.
        Sell at bid (taker) then close_position (books PnL once + removes from
        open_positions, so the settler can't double-settle). Only books on a confirmed
        FULL fill; if bid depth < shares it waits (hold-to-resolution is the fallback) —
        so no partial-fill accounting. Read-mostly + try/except: can't disturb STWA."""
        if not OFI_LIVE_ENABLED:
            return
        import time as _t
        now = _t.time()
        try:
            opens = [(t, p) for t, p in self.bot.risk.open_positions.items()
                     if getattr(p, "bond_entry_class", "") == "WEATHER_OFI"]
        except Exception:
            return
        if not opens:
            return
        from execution.order_manager import OrderStatus as _OS
        from datetime import datetime as _dtx, timezone as _tzx
        ofi_map = self._ofi_from_tape(now)
        for tok, p in opens:
            try:
                cid = getattr(p, "condition_id", None)
                held = now - getattr(p, "open_ts", now)
                mydir = 1.0 if getattr(p, "bond_outcome_direction", "up") == "up" else -1.0
                ofi = ofi_map.get(cid, (0.0, 0.0))[0]
                signal_alive = (mydir * ofi) >= OFI_EXIT_THRESH
                bk = await self._fetch_book_levels(tok, n=3)
                bids = bk.get("bids") or []
                if not bids:
                    continue
                bid = float(bids[0]["price"]); bidsz = float(bids[0]["size"])
                entry = float(getattr(p, "entry_price", 0.0))
                tp_hit = bid >= entry + OFI_SCALP_TP
                time_up = held >= OFI_TIME_CAP_S
                if signal_alive and not tp_hit and not time_up:
                    continue  # edge still alive → hold
                shares = float(getattr(p, "remaining_shares", 0.0) or 0.0)
                if shares <= 0 or bidsz < shares:
                    continue  # wait for full-exit depth; settler is the fallback
                reason = "OFI_TP" if tp_hit else ("OFI_DECAY" if not signal_alive else "OFI_TIMECAP")
                fill = await self.bot.orders.limit_sell(
                    token_id=tok, price=round(bid, 4), size=shares, condition_id=cid)
                filled = (getattr(fill, "status", None) == _OS.FILLED
                          and float(getattr(fill, "total_size", 0) or 0) >= shares - 0.01)
                if not filled:
                    logger.info("[OFI] exit no-fill %s status=%s — retry next cycle",
                                str(tok)[:10], getattr(fill, "status", None))
                    continue
                exitpx = float(getattr(fill, "avg_fill_price", bid) or bid)
                pnl = self.bot.risk.close_position(
                    tok, exit_price=exitpx, reason="WEATHER_OFI_EXIT", actual_fee=0.0)
                logger.info("[OFI] EXIT %s %s held=%.0fs ofi=%.2f entry=%.3f exit=%.3f pnl=%.3f",
                            reason, str(tok)[:10], held, ofi, entry, exitpx, pnl or 0.0)
                try:
                    _ld = Path("logs/shadow/hot") / _dtx.now(_tzx.utc).date().isoformat()
                    _ld.mkdir(parents=True, exist_ok=True)
                    (_ld / "ofi_live.jsonl").open("a").write(json.dumps({
                        "ts": now, "record": "exit", "reason": reason, "cid": cid,
                        "held_s": round(held), "ofi_now": round(ofi, 3),
                        "entry": entry, "exit": round(exitpx, 4), "shares": shares,
                        "pnl": round(pnl, 4) if pnl is not None else None,
                    }) + "\n")
                except Exception:
                    pass
            except Exception:
                logger.debug("[OFI] exit failed %s", str(tok)[:10], exc_info=True)

    async def _exit_at_099(self) -> None:
        """Sell every held-to-resolution weather position once a ≥$0.99 bid with
        enough depth exists, then close_position() inline — books PnL exactly once
        and removes the token so the settler can't double-count it (it books from
        the Gamma outcome with no balance check). Poll-then-taker, full-depth-gated
        (no partial-fill accounting); hold-to-resolution is the fallback. Uses the
        working _submit_limit_order primitive (orders.limit_sell does not exist).
        Read-mostly + try/except: cannot disturb the rest of the engine."""
        if not EXIT099_ENABLED:
            return
        risk = getattr(self.bot, "risk", None)
        if risk is None:
            return
        try:
            opens = [(t, p) for t, p in list(risk.open_positions.items())
                     if getattr(p, "bond_entry_class", "") in _STWA_RESOLVE_CLASSES]
        except Exception:
            return
        if not opens:
            return
        # token → negRisk (weather markets default to neg-risk) — avoid a wrong-exchange sell.
        tok2neg: dict = {}
        for _e in (self._today_markets_cache or []):
            _m = _e.get("mkt") or {}
            for _t in _parse_token_ids(_m.get("clobTokenIds", [])):
                tok2neg[_t] = bool(_m.get("negRisk", True))
        from execution.order_manager import OrderStatus as _OS, OrderSide as _OSide, OrderType as _OT
        from datetime import datetime as _dtx, timezone as _tzx
        import time as _t, math as _math
        # Tokens with a resting RECYCLE099 maker ask: their shares are committed
        # on the book — a taker sell here would be rejected for balance. Skip.
        _asked = {c.get("token_id") for c in getattr(self, "_maker_resting", {}).values()
                  if str(c.get("side") or "") == "SELL_EXIT"}
        for tok, p in opens:
            try:
                if tok in _asked:
                    continue
                shares = float(getattr(p, "remaining_shares", 0.0) or 0.0)
                # A 0.99 price forces whole-share CLOB steps, so sell the floored whole
                # amount; any sub-1-share remainder is dust that redeems at resolution.
                # Flooring keeps the full-fill check exact (no partial-sell orphan).
                sell_sh = float(_math.floor(shares))
                if sell_sh < EXIT099_MIN_SHARES:
                    continue
                # Cheap pre-filter: skip the book fetch unless the cached bid is near 0.99.
                cached_bid = float(getattr(p, "current_price", 0.0) or 0.0)
                if cached_bid and cached_bid < EXIT099_PRICE - 0.01:
                    continue
                bk = await self._fetch_book_levels(tok, n=3)
                bids = (bk or {}).get("bids") or []
                if not bids:
                    continue
                bid = float(bids[0]["price"]); bidsz = float(bids[0]["size"])
                if bid < EXIT099_PRICE or bidsz < sell_sh:
                    continue   # need a ≥0.99 bid deep enough to clear the whole position
                neg = tok2neg.get(tok, True)
                await self.bot.orders.approve_token_for_sell(tok)
                fill = await self.bot.orders._submit_limit_order(
                    tok, _OSide.SELL, round(bid, 2), sell_sh,
                    neg_risk=neg, order_type=_OT.GTC)
                filled = (getattr(fill, "status", None) == _OS.FILLED
                          and float(getattr(fill, "total_size", 0) or 0) >= sell_sh - 0.01)
                if not filled:
                    logger.info("[EXIT099] no-fill %s status=%s — retry next cycle",
                                str(tok)[:10], getattr(fill, "status", None))
                    continue
                exitpx = float(getattr(fill, "avg_fill_price", bid) or bid)
                cls = getattr(p, "bond_entry_class", "")
                entry = float(getattr(p, "entry_price", 0.0) or 0.0)
                pnl = self.bot.risk.close_position(
                    tok, exit_price=exitpx, reason="WEATHER_EXIT099", actual_fee=0.0)
                self.bot._open_meta.pop(tok, None)
                logger.info("[EXIT099] EXIT %s %s shares=%.1f entry=%.3f exit=%.4f pnl=%.3f",
                            cls, str(tok)[:10], shares, entry, exitpx, pnl or 0.0)
                try:
                    _ld = Path("logs/shadow/hot") / _dtx.now(_tzx.utc).date().isoformat()
                    _ld.mkdir(parents=True, exist_ok=True)
                    (_ld / "exit099_live.jsonl").open("a").write(json.dumps({
                        "ts": _t.time(), "record": "exit099", "cls": cls, "token": tok,
                        "shares": shares, "entry": entry, "exit": round(exitpx, 4),
                        "pnl": round(pnl, 4) if pnl is not None else None,
                    }) + "\n")
                except Exception:
                    pass
            except Exception:
                logger.debug("[EXIT099] exit failed %s", str(tok)[:10], exc_info=True)

    async def _m1_beta_probe_evaluate(
        self, *, now_ts: float, now_utc, first_seen: float,
        mkt: dict, city: str, icao: str, end_date: str,
        question: str, lo_c, hi_c, running_max: float, yes_bid: float,
        yes_bid_clob=None,
        no_token_id: str, no_ask_clob, no_book: dict,
        no_ask_usd_at_implied: float, no_ask_usd_at_clob_implied=None,
        seconds_to_close,
        official_running_max: float | None = None,
        override_layer: str | None = None,
        override_stake_usd: float | None = None,
    ) -> None:
        """Multi-layer surface: one fire per (bucket × layer). Up to 5 fires per bucket.

        Per-fire gates: must clear layer-specific min_edge + min_depth.
        Universal blocks: depth_c < 1.0°C, edge > 0.50 (γ ceiling), γ-block
        (edge>=0.50 AND sec>=1800 — but already excluded by MAX_EDGE).

        Statistical safety: every fire is tagged with condition_id (bucket cluster),
        event_key (city+date cluster), layer, and bucket_fire_seq. Analyzer must
        collapse correlated outcomes at the bucket-cluster level for WR/EV stats.
        """
        sec_since = int(now_ts - first_seen)
        # 2026-06-07: oracle-city blocklist — skip wrong-oracle settlement cities
        # whose METAR-derived lockout diverges from the resolution source (false
        # lockouts that resolve YES even at margin≥0.5°C). Single chokepoint ⇒
        # gates both WS and REST fire paths. See M1_BETA_PROBE_ORACLE_BLOCK_ICAO.
        #
        # 2026-06-09 HK EXCEPTION: VHHH stays in the blocklist constant (so every
        # OTHER lockout path — maker mirrors, min-lockout — remains closed), but
        # THIS path may trade HK using the HKO-Observatory feed, which IS the HK
        # oracle (census: HKO daily max == winner bucket 21/21; VHHH METAR 37%).
        # Two substitutions, both mandatory:
        #   1. proof max = official_running_max_hko_c (debounced 1-min HKO feed),
        #      never the METAR-derived official_running_max passed in;
        #   2. HK buckets are FLOOR/range-containing at one decimal — bucket "32"
        #      covers [32.0, 33.0). hi_c arrives with the generic +0.5 pad, so the
        #      true dead-line is another +0.5 above it.
        if icao == "VHHH":
            _hko_max = (self._icao_metar_cache.get("VHHH") or {}).get(
                "official_running_max_hko_c")
            if _hko_max is None or hi_c is None:
                return
            official_running_max = float(_hko_max)
            hi_c = hi_c + 0.5
        elif icao in M1_BETA_PROBE_ORACLE_BLOCK_ICAO:
            return
        # PROVENANCE-CLEAN lockout proof (2026-06-03): depth_c is M1β's binding
        # physical-lockout margin (the MIN_DEPTH_C gate). It MUST be derived from the
        # AWC/NWS hourly-METAR oracle (official_running_max), NEVER the NMS-merged
        # running_max which Synoptic 1-min ASOS inflates (the NYC +4.73°C false
        # lockout; the LA/SF/Shenzhen losses were all inflated-running_max false
        # lockouts). Fail-safe: no clean obs in hand ⇒ skip — never trade a lockout
        # on contaminated sub-hourly data. Applies to every band + the WS path.
        if official_running_max is None or hi_c is None:
            return
        depth_c = official_running_max - hi_c

        # Prefer CLOB prices over Gamma for all gates. Gamma bestBid lags the CLOB
        # on weather markets by minutes; using it causes depth caps that miss where
        # NO asks actually sit (e.g. Gamma 0.62 → cap 0.38, but CLOB 0.15 → cap 0.85).
        eff_yes_bid = yes_bid_clob if yes_bid_clob is not None else yes_bid
        eff_depth = (
            no_ask_usd_at_clob_implied
            if no_ask_usd_at_clob_implied is not None
            else no_ask_usd_at_implied
        )

        # === Universal blocks (apply to every layer) ===
        # (VHHH hard-block removed 2026-06-09 — HK now trades on the HKO-oracle
        #  substitution above; the station mismatch was vs VHHH METAR, not HKO.)
        if not (M1_BETA_PROBE_MIN_SEC_SINCE <= sec_since < M1_BETA_PROBE_MAX_SEC_SINCE):
            return

        # ── DIP-BUY SHADOW (no capital) — safe re-spec of the killed dip-rebuy ──
        # Log cheap-NO candidates ONLY on a STRONG OFFICIAL lockout (official
        # running_max well past the ceiling, AWC/NWS-clean ⇒ physically impossible),
        # where a dip is NOISE not real uncertainty. Placed before the depth/edge/
        # no_ask gates so it captures deep dips. Join resolution offline → confirm NO
        # wins → only then re-enable dip-buy live on the validated (margin, dip) box.
        if (DIP_SHADOW_ENABLED and override_layer is None
                and official_running_max is not None and hi_c is not None
                and no_ask_clob is not None and 0.02 < no_ask_clob <= DIP_SHADOW_NO_ASK_MAX
                and (official_running_max - hi_c) >= DIP_SHADOW_MIN_MARGIN_C):
            try:
                _dd = Path("logs/shadow/hot") / now_utc.date().isoformat()
                _dd.mkdir(parents=True, exist_ok=True)
                _nbk = no_book or {}
                with (_dd / "dip_shadow.jsonl").open("a") as _df:
                    _df.write(json.dumps({
                        "ts": round(now_ts), "city": city, "no_tok": no_token_id,
                        "hi_c": hi_c,
                        "official_running_max_c": round(float(official_running_max), 2),
                        "official_margin_c": round(float(official_running_max) - hi_c, 2),
                        "no_ask": no_ask_clob, "no_bid": _nbk.get("best_bid"),
                        "no_depth_usd": _nbk.get("usd_depth"),
                        "discount": round(1.0 - no_ask_clob, 4),
                        "sec_to_close": seconds_to_close,
                    }) + "\n")
            except Exception:
                logger.debug("[DIP-SHADOW] log fail", exc_info=True)

        if depth_c < M1_BETA_PROBE_MIN_DEPTH_C:
            return  # integer-bucket misclass guard
        # DIP layers bypass the MAX_EDGE gate: the whole point is buying when YES bid
        # is artificially high (market mispriced). Allow up to 0.999.
        is_dip = override_layer is not None and override_layer.startswith("DIP")
        if not is_dip and eff_yes_bid >= M1_BETA_PROBE_MAX_EDGE:
            return
        if eff_yes_bid >= 0.50 and sec_since >= M1_BETA_PROBE_GAMMA_BLOCK_SEC:
            return
        # VALIDATED-SLICE gate (2026-06-01): only fire when the market AGREES the
        # bucket is locked — NO ask in the deep-lockout range [0.90, 0.97]. Below
        # 0.90 the market still prices YES meaningfully (false-lockout zone, source
        # of the live −$23.60); above 0.97 the edge < fee floor. Authoritative gate
        # for BOTH the WS and REST (_metar_lockout_scan) firing paths.
        if no_ask_clob is None or not (
                M1_BETA_PROBE_NO_ASK_MIN <= no_ask_clob <= M1_BETA_PROBE_NO_ASK_MAX):
            return
        # WIDENED fat-edge band [NO_ASK_MIN, NO_ASK_MARKET_AGREE) (2026-06-01): the
        # market does NOT fully confirm the lockout here, so the legacy market-agreement
        # safety is absent. Substitute a PROVENANCE-CLEAN physical proof: official
        # (AWC/NWS-only) running_max ≥ FATEDGE_MIN_DEPTH_C past the ceiling ⇒ YES is
        # physically impossible regardless of the stale quote. Fail-safe: no clean value
        # in hand (e.g. WS path, no official obs yet) ⇒ skip — never trade the fat band
        # on the contaminated feed (that booked the −$23.60 false-lockouts).
        if no_ask_clob < M1_BETA_PROBE_NO_ASK_MARKET_AGREE:
            _clean_margin = (
                (official_running_max - hi_c)
                if (official_running_max is not None and hi_c is not None) else None
            )
            if _clean_margin is None or _clean_margin < M1_BETA_PROBE_FATEDGE_MIN_DEPTH_C:
                return

        # ── Locked-region MAKER first-exercise (controlled; shadow by default) ──
        # The bucket has now cleared M1β's provenance gates ⇒ NO is physically
        # certain (AS=0). Exercise the maker_buy primitive: shadow-logs the resting
        # NO bid we'd post; in LIVE it posts $4 (breaker-gated, ≤5, margin ≥1°C).
        if MAKER_EXERCISE_ENABLED:
            try:
                await self._maker_locked_exercise(
                    city=city, no_token_id=no_token_id, no_book=no_book,
                    no_ask_clob=no_ask_clob, hi_c=hi_c,
                    official_running_max=official_running_max,
                    now_ts=now_ts, now_utc=now_utc,
                    icao=icao, question=question, end_date=end_date,
                    lo_c=lo_c, condition_id=mkt.get("conditionId", ""))
            except Exception:
                # A maker bug must NEVER disrupt the live M1β/scan path.
                logger.debug("[MAKER-EX] exercise failed (isolated)", exc_info=True)

        # === Layer selection (bypassed for DIP rebuys) ===
        if override_layer is not None:
            layer_name      = override_layer
            layer_min_edge  = 0.03
            layer_min_depth = 1.0   # low bar — dip scan already verified depth
        else:
            layer_name = None
            layer_min_edge = None
            layer_min_depth = None
            for name, lo_s, hi_s, min_edge, min_depth in M1_BETA_PROBE_LAYERS:
                if lo_s <= sec_since < hi_s:
                    layer_name, layer_min_edge, layer_min_depth = name, min_edge, min_depth
                    break
            if layer_name is None:
                return

        # === Layer-specific gates ===
        if eff_yes_bid < layer_min_edge:
            return
        if (eff_depth or 0.0) < M1_BETA_PROBE_MIN_SHARES * no_ask_clob:   # ≥5 fillable shares (partial fills ok)
            return

        st = self._m1_beta_probe_load_state()
        # Already fired this bucket in this layer?
        layers_fired = st["fires_by_token"].get(no_token_id, [])
        if layer_name in layers_fired:
            return  # one fire per (bucket, layer)

        if st["fires_today"] >= M1_BETA_PROBE_MAX_DAILY_FIRES:
            logger.info("[M1β] daily fire cap reached (%d)", st["fires_today"])
            return
        if st["total_fires"] >= M1_BETA_PROBE_MAX_TOTAL_FIRES:
            logger.warning("[M1β] total fire cap reached (%d) — halted for review",
                            st["total_fires"])
            return

        # Pre-fire log + order submission
        intended_price = round(min(0.99, no_ask_clob + 0.01), 4)
        if override_stake_usd is not None:
            stake_usd = override_stake_usd
        elif depth_c >= 0.5 and 0.50 <= no_ask_clob <= 0.96:
            stake_usd = M1_BETA_PROBE_STAKE_DEEP_USD   # deep-clean slice (98.3% WR n=422)
        else:
            stake_usd = M1_BETA_PROBE_STAKE_USD
        submitted_ts = now_ts
        log_dir = Path("logs/shadow/hot") / now_utc.date().isoformat()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "m1_beta_probe.jsonl"

        # Cluster IDs for contamination-aware analysis:
        # - condition_id identifies the bucket cluster (one resolution outcome per cluster)
        # - event_key groups buckets by city+date (deeper correlation: shared daily-high obs)
        # - bucket_fire_seq is the Nth fire on this specific bucket (1,2,3,...)
        # - layer is which time band this fire was in
        condition_id = mkt.get("conditionId", "")
        event_key = f"{city}|{end_date}"
        bucket_fire_seq = st["bucket_fire_seq"].get(no_token_id, 0) + 1

        pre = {
            "schema_version": 2,
            "record_type": "m1_beta_probe",
            "phase": "submit",
            "ts_submitted": submitted_ts,
            # --- cluster identifiers (DO NOT remove — analyzer relies on these) ---
            "condition_id": condition_id,
            "event_key": event_key,
            "layer": layer_name,
            "bucket_fire_seq": bucket_fire_seq,
            # --- market identity ---
            "city": city, "icao": icao, "end_date": end_date,
            "question": question,
            "no_token_id": no_token_id,
            # --- state at signal ---
            "running_max_c": round(running_max, 3),
            "bucket_lo_c": round(lo_c, 4) if lo_c is not None else None,
            "bucket_hi_c": round(hi_c, 4) if hi_c is not None else None,
            "depth_c": round(depth_c, 3),
            "yes_bid_gamma_at_signal": round(yes_bid, 4),
            "yes_bid_clob_at_signal": round(yes_bid_clob, 4) if yes_bid_clob is not None else None,
            "yes_bid_at_signal": round(eff_yes_bid, 4),
            "no_ask_clob_at_signal": round(no_ask_clob, 4),
            "no_visible_depth_usd_at_signal": round(eff_depth, 2),
            "no_visible_depth_usd_gamma": round(no_ask_usd_at_implied, 2),
            "no_book_at_signal": no_book,
            "sec_since_first_lockout": sec_since,
            "sec_to_close": int(seconds_to_close) if seconds_to_close is not None else None,
            # --- order ---
            "intended_price": intended_price,
            "stake_usd": stake_usd,
            # --- bookkeeping ---
            "daily_fires_before": st["fires_today"],
            "total_fires_before": st["total_fires"],
            "layer_min_edge": layer_min_edge,
            "layer_min_depth": layer_min_depth,
        }
        try:
            log_path.open("a").write(json.dumps(pre) + "\n")
        except Exception:
            logger.exception("[M1β] pre-log write fail")

        # Submit the live order
        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus
        neg_risk = mkt.get("negRisk", True)
        logger.info("[M1β] FIRE %s/%s seq=%d NO@%.3f stake=$%.1f sec=%ds edge=%.3f depth=%.1f°C",
                    city, layer_name, bucket_fire_seq,
                    intended_price, stake_usd,
                    sec_since, yes_bid, depth_c)
        try:
            fill = await self.bot.orders.limit_buy(
                token_id=no_token_id,
                intended_price=intended_price,
                stake_usd=stake_usd,
                direction=_Dir.BUY_NO,
                neg_risk=neg_risk,
                fast_fail=False,
            )
        except Exception as e:
            logger.exception("[M1β] order error %s", city)
            post = {**pre, "phase": "submit_error", "error": str(e),
                    "completed_ts": time.time()}
            try: log_path.open("a").write(json.dumps(post) + "\n")
            except Exception: pass
            return

        completed_ts = time.time()
        filled = (fill.status == OrderStatus.FILLED and fill.total_size > 0)
        fill_price = float(fill.avg_fill_price) if filled else None
        fill_size = float(fill.total_size) if filled else 0.0
        slippage = (fill_price - no_ask_clob) if (filled and fill_price is not None) else None

        post = {
            "schema_version": 2,
            "record_type": "m1_beta_probe",
            "phase": "result",
            "ts_submitted": submitted_ts,
            "ts_completed": completed_ts,
            # --- cluster identifiers (mirror of submit) ---
            "condition_id": condition_id,
            "event_key": event_key,
            "layer": layer_name,
            "bucket_fire_seq": bucket_fire_seq,
            # ---
            "no_token_id": no_token_id,
            "city": city,
            "fill_status": str(fill.status),
            "filled": filled,
            "fill_avg_price": fill_price,
            "fill_size_shares": fill_size,
            "fill_notional_usd": round(fill_price * fill_size, 4) if filled else 0.0,
            "slippage_vs_displayed_no_ask": round(slippage, 4) if slippage is not None else None,
            "time_to_fill_ms": int((completed_ts - submitted_ts) * 1000),
        }
        try:
            log_path.open("a").write(json.dumps(post) + "\n")
        except Exception:
            logger.exception("[M1β] post-log write fail")

        # Bookkeeping — count the fire whether or not it filled (one chance per layer/bucket)
        st["fires_by_token"].setdefault(no_token_id, []).append(layer_name)
        st["bucket_fire_seq"][no_token_id] = bucket_fire_seq
        st["fires_today"] += 1
        st["total_fires"] += 1

        if filled:
            # Multi-fire safety: only register the first fire's PositionMeta.
            # Subsequent fires on the same token: CLOB accumulates shares in the
            # wallet naturally, and the orders layer writes a separate trades.jsonl
            # record per fill (resolution patcher works per-record). Re-calling
            # open_position would overwrite the original meta with the new size only.
            already_registered = no_token_id in self.bot.risk.open_positions
            if not already_registered:
                self.bot.risk.open_position(
                    token_id=no_token_id,
                    asset="WEATHER",
                    direction=_Dir.BUY_NO,
                    stake=fill_size * fill_price,
                    entry_price=fill_price,
                    tpsl=_TPSL(take_profit=0.0, stop_loss=0.0,
                                tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
                    condition_id=condition_id,
                    window_end_ts=0.0,
                    is_bond=True,
                    bond_outcome_direction="down",
                    bond_entry_class="WEATHER_M1_PROBE",
                )
                meta = self.bot._open_meta.setdefault(no_token_id, {})
                meta["signal_source"] = f"WEATHER/{city}/WEATHER_M1_PROBE"
                meta["city"] = city
                meta["icao"] = icao
                meta["weather_question"] = question
                meta["weather_date"] = end_date
                meta["bucket_lo_c"] = lo_c
                meta["bucket_hi_c"] = hi_c
                meta["m1_beta_first_signal_state"] = pre
            else:
                # Re-fire on same token: log additional signal context but don't
                # overwrite the original PositionMeta.
                meta = self.bot._open_meta.setdefault(no_token_id, {})
                meta.setdefault("m1_beta_refire_history", []).append({
                    "layer": layer_name,
                    "fire_seq": bucket_fire_seq,
                    "ts": completed_ts,
                    "fill_price": fill_price,
                    "fill_size": fill_size,
                })
            logger.info("[M1β] FILLED %s NO@%.4f size=%.1f (total=%d/%d)",
                        city, fill_price, fill_size,
                        st["total_fires"], M1_BETA_PROBE_MAX_TOTAL_FIRES)
        else:
            logger.info("[M1β] no-fill %s (status=%s) (total=%d/%d)",
                        city, fill.status,
                        st["total_fires"], M1_BETA_PROBE_MAX_TOTAL_FIRES)

        self._m1_beta_probe_save_state(st)

    async def _m1_dip_rebuy_scan(self) -> None:
        """Dip-rebuy: buy NO cheaply when market reprices YES up on hourly-METAR dip
        while the 5-min ASOS (live METAR cache) still confirms running_max > hi_c.

        Runs in the 60s slow path. Up to 2 DIP fires per bucket (DIP1, DIP2),
        deduped by the same fires_by_token mechanism as L0-L4.
        """
        if not (M1_BETA_PROBE_ENABLED and M1_DIP_REBUY_ENABLED):
            return
        if not self._today_markets_cache:
            return

        import time as _t
        from datetime import datetime, timezone, timedelta
        now_ts  = _t.time()
        now_utc = datetime.now(timezone.utc)

        for entry in self._today_markets_cache:
            mkt  = entry.get("mkt") or {}
            city = entry.get("city")
            icao = entry.get("icao")
            if not city or not icao:
                continue

            question = mkt.get("question", "")
            lo_c, hi_c, _ = _parse_outcome(question)
            if hi_c is None:
                continue

            token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            if len(token_ids) < 2:
                continue
            yes_token_id = token_ids[0]
            no_token_id  = token_ids[1]

            # Only act on buckets where we already hold a position
            risk = getattr(self.bot, "risk", None)
            pos  = risk.open_positions.get(no_token_id) if risk else None
            if not pos:
                continue
            if getattr(pos, "bond_entry_class", "") != "WEATHER_M1_PROBE":
                continue

            metar    = self._icao_metar_cache.get(icao) or {}
            live_max = metar.get("running_max_c")
            _tz_h    = ICAO_UTC_OFFSET_H.get(icao, 0)
            _local_today = (now_utc + timedelta(hours=_tz_h)).date().isoformat()
            if live_max is None or live_max < hi_c + M1_DIP_REBUY_MIN_DEPTH_C:
                continue
            if metar.get("running_max_date", "") != _local_today:
                continue

            # Restore watchlist entry if wiped by restart so BBO path resumes
            if yes_token_id not in self._m1_lockout_watchlist:
                first_seen = self._lockout_first_seen.get(yes_token_id, now_ts)
                self._m1_lockout_watchlist[yes_token_id] = {
                    "no_token_id": no_token_id,
                    "city": city, "icao": icao,
                    "end_date": (mkt.get("endDate") or "")[:10],
                    "lo_c": lo_c, "hi_c": hi_c,
                    "depth_c": round(live_max - hi_c, 2),
                    "running_max": live_max,
                    "question": question,
                    "first_ts": first_seen,
                    "mkt": mkt,
                    "neg_risk": mkt.get("negRisk", True),
                }
                try:
                    self.bot.feed._clob_ws_sub_queue.put_nowait([yes_token_id, no_token_id])
                except Exception:
                    pass
                logger.info("[M1β-DIP] watchlist restored: %s depth=%.2f°C",
                            city, live_max - hi_c)

            # Get current NO ask — WS book first, then CLOB REST fallback
            no_ob  = self.bot.feed.order_books.get(no_token_id)
            no_ask = None
            no_book: dict = {}
            if no_ob and no_ob.asks:
                no_ask  = no_ob.asks[0][0]
                no_book = {"asks": [{"price": a[0], "usd": a[0] * a[1]}
                                    for a in no_ob.asks[:5]]}
            else:
                try:
                    import aiohttp as _aio
                    async with _aio.ClientSession() as _sess:
                        async with _sess.get(
                            f"https://clob.polymarket.com/book?token_id={no_token_id}",
                            timeout=_aio.ClientTimeout(total=5),
                        ) as _resp:
                            _bk   = await _resp.json()
                            _asks = _bk.get("asks", [])
                            if _asks:
                                no_ask  = float(_asks[0]["price"])
                                no_book = {"asks": [{"price": float(a["price"]), "usd": 0.0}
                                                    for a in _asks[:5]]}
                except Exception:
                    continue

            if no_ask is None or no_ask > M1_DIP_REBUY_NO_ASK_MAX or no_ask >= 1.0:
                continue

            # Pick DIP1 or DIP2 (max 2 per bucket)
            st           = self._m1_beta_probe_load_state()
            layers_fired = st["fires_by_token"].get(no_token_id, [])
            if "DIP1" not in layers_fired:
                dip_layer = "DIP1"
            elif "DIP2" not in layers_fired:
                dip_layer = "DIP2"
            else:
                continue

            yes_bid    = round(1.0 - no_ask, 4)
            first_seen = self._lockout_first_seen.get(yes_token_id, now_ts)

            logger.info("[M1β-DIP] %s %s no_ask=%.3f depth=%.2f°C",
                        city, dip_layer, no_ask, live_max - hi_c)

            await self._m1_beta_probe_evaluate(
                now_ts=now_ts, now_utc=now_utc, first_seen=first_seen,
                mkt=mkt, city=city, icao=icao,
                end_date=(mkt.get("endDate") or "")[:10],
                question=question, lo_c=lo_c, hi_c=hi_c,
                running_max=live_max,
                yes_bid=yes_bid,
                no_token_id=no_token_id,
                no_ask_clob=no_ask,
                no_book=no_book,
                no_ask_usd_at_implied=M1_DIP_REBUY_STAKE_USD,
                no_ask_usd_at_clob_implied=M1_DIP_REBUY_STAKE_USD,
                seconds_to_close=None,
                override_layer=dip_layer,
                override_stake_usd=M1_DIP_REBUY_STAKE_USD,
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
        _now_utc = datetime.now(timezone.utc)
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

            # Local date for this city — each market closes at its own midnight
            _tz_h = ICAO_UTC_OFFSET_H.get(icao or "", 0)
            _local_today = (_now_utc + timedelta(hours=_tz_h)).date().isoformat()

            for mkt in ev.get("markets", []):
                if mkt.get("endDate", "")[:10] != _local_today:
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

    async def _refresh_all_metars(self) -> bool:
        """
        Single batched METAR fetch for ALL relevant ICAOs:
          - ICAOs for today's active market cities (from _today_markets_cache)
          - ICAOs for any open positions in _open_meta

        Updates _icao_metar_cache[icao] with latest observation.
        Preserves running_max_c across cycles (only resets at midnight).
        Returns True if at least one ICAO had a new observation this cycle.
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
            return False

        # Midnight reset pass — runs unconditionally every cycle, before any new obs.
        # The per-observation reset below only fires when a new METAR arrives; this
        # ensures running_max is cleared at local midnight even if no METAR lands
        # in the first ~30 min of the new local day (common for overnight US stations).
        from datetime import timedelta as _td2
        _now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        for _icao in list(self._icao_metar_cache.keys()):
            _tz_h2 = ICAO_UTC_OFFSET_H.get(_icao, 0)
            _local_today = (_now_utc + _td2(hours=_tz_h2)).date().isoformat()
            _c = self._icao_metar_cache[_icao]
            if _c.get("running_max_date") != _local_today:
                _c["running_max_c"] = None
                # 2026-06-09 BUG FIX: the official fields MUST be cleared here too.
                # This pass flips running_max_date unconditionally, which made the
                # per-observation reset below (the only place official_* was cleared)
                # permanently dead — official_running_max_c carried YESTERDAY'S max
                # into the new local day (a false-lockout generator for any process
                # that survives a local midnight; frequent restarts masked it).
                _c["official_running_max_c"] = None
                _c["official_running_min_c"] = None
                _c["official_running_max_hko_c"] = None   # HK oracle feed (mirror)
                _c["_hko_prev"] = None
                _c["running_max_date"] = _local_today

        hours = 1 if self._metar_backfill_done else 24
        self._metar_backfill_done = True
        url = (f"https://aviationweather.gov/api/data/metar"
               f"?ids={','.join(icaos)}&format=json&hours={hours}")
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    url, timeout=aiohttp.ClientTimeout(total=12),
                    headers={"User-Agent": "Klaus-WeatherBot/1.0"},
                ) as resp:
                    if resp.status != 200:
                        return False
                    records = await resp.json()
        except Exception as e:
            logger.debug("[WA] metar batch fetch error: %s", e)
            return False

        from datetime import datetime, timezone, timedelta as _td, date as _date

        new_obs_count = 0
        # 2026-06-09 BUG FIX: AWC returns records NEWEST-FIRST. The monotone
        # obs_time skip below ("not a new observation") then discarded every
        # older record after the first — so the 24h restart backfill only ever
        # ingested the single latest obs, wiping the day's running max on EVERY
        # restart (Paris 06-09: cache 13.0 vs true daily max 19.0; lockout
        # detection silently lost the whole pre-restart surface). Process
        # oldest-first so the backfill replays the day chronologically.
        records = sorted(records, key=lambda r: r.get("obsTime", 0) or 0)
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
                "official_running_max_c": None,
                "official_running_min_c": None,
            })
            if obs_time <= cached.get("last_obs_time", 0):
                continue  # not a new observation

            # Guard: skip observations from a different local day (protects 24h backfill
            # from including yesterday's peak for western-hemisphere cities like SBGR/CYYZ).
            _obs_local_date = (datetime.fromtimestamp(obs_time, tz=timezone.utc) + _td(hours=_tz_h)).date().isoformat()
            if _obs_local_date != today_str:
                continue

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
                cached["official_running_max_c"] = None
                cached["official_running_min_c"] = None   # MIN-lockout (mirror)
                cached["running_max_date"] = today_str

            prev_temp = cached.get("temp_c")    # before this update — for rapid-rise detection
            prev_max  = cached.get("running_max_c")
            new_max   = temp_c if (prev_max is None or temp_c > prev_max) else prev_max

            # OFFICIAL running max: built ONLY from this AWC/NWS hourly METAR's
            # T-group-decoded temp_c (the exact source the WU/Polymarket oracle
            # resolves against). Kept separate from running_max_c, which the NMS
            # path (Synoptic/JMA, sub-hourly + whole-degree) also writes and which
            # therefore over-counts the high. This is the field both on_metar
            # callers already prefer via `official_running_max_c or running_max_c`,
            # so populating it here is what actually wires the oracle guard that
            # was previously a no-op (caused the LA/SF false-lockout losses).
            prev_off = cached.get("official_running_max_c")
            official_max = temp_c if (prev_off is None or temp_c > prev_off) else prev_off
            cached["official_running_max_c"] = official_max
            # OFFICIAL running MIN — same AWC/NWS-hourly provenance as official_max
            # (the daily-min oracle). Tracked ONLY here (never from the NMS sub-hourly
            # path), so a sub-hourly cold spike can't deflate it into a false NO-lock —
            # the exact mirror of the running_max false-lockout bug class.
            prev_off_min = cached.get("official_running_min_c")
            official_min = temp_c if (prev_off_min is None or temp_c < prev_off_min) else prev_off_min
            cached["official_running_min_c"] = official_min

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
            new_obs_count += 1

            # ── STWA Kalman update ────────────────────────────────────────────
            if self._stwa is not None:
                try:
                    _slug = ICAO_TO_SLUG.get(icao, "")
                    if _slug:
                        _dew  = cached.get("dewpoint_c")
                        _sky  = SKY_RANK_MAP.get(sky_cover, 2)
                        self._stwa.on_metar(
                            _slug,
                            temp_c,
                            float(_dew) if _dew is not None else None,
                            _sky,
                            obs_time,
                            # Official AWC/NWS METAR max ONLY — never fall back to the
                            # shared all-source running_max_c. Gamma settle (2026-06-04)
                            # proved running_max_c overshoots the true daily high by
                            # +4..+13°C (Synoptic sub-hourly / wrong-station), and an
                            # inflated M0 collapses the nowcast σ to the 0.25 floor
                            # ⇒ false-confident favorites (the directional-YES bleed).
                            # None when no clean obs yet → engine prices on forecast σ
                            # (humble) instead of a contaminated lock. Note: `or` also
                            # wrongly discarded a legitimate 0.0°C official high.
                            cached.get("official_running_max_c"),
                            today_str,
                        )
                except Exception:
                    pass   # never crash the main METAR loop

        return new_obs_count > 0

    async def _poll_national_met(self) -> None:
        """Poll all NMS sources every fast-path tick (2s). Returns update count."""
        try:
            from strategy.national_met import poll_all, covered_icaos
        except ImportError:
            return 0
        icaos_needed: set[str] = {e["icao"] for e in self._today_markets_cache if e["icao"]}
        icaos_needed &= covered_icaos()
        if not icaos_needed:
            return 0
        result = await poll_all(icaos_needed, self._icao_metar_cache, ICAO_UTC_OFFSET_H)

        # Feed any new NMS observations to the STWA Kalman engine.
        # AWC's on_metar hook only fires for AWC-sourced obs; NMS (Synoptic/WIS2)
        # updates _icao_metar_cache directly, so we mirror them here.
        if result > 0 and self._stwa is not None:
            import time as _t
            _now_str = __import__("datetime").date.today().isoformat()
            for _icao, _slug in ICAO_TO_SLUG.items():
                _cached = self._icao_metar_cache.get(_icao)
                if not _cached:
                    continue
                _cache_ts = _cached.get("last_obs_time", 0.0)
                if _cache_ts > self._stwa.get_last_obs_ts(_slug):
                    _temp = _cached.get("temp_c")
                    if _temp is not None:
                        self._stwa.on_metar(
                            _slug, _temp,
                            _cached.get("dewpoint_c"),
                            SKY_RANK_MAP.get(_cached.get("sky_cover", "CLR"), 2),
                            _cache_ts,
                            # Official AWC/NWS max ONLY — drop the contaminated
                            # all-source running_max_c fallback (Gamma settle: it
                            # overshoots +4..+13°C → false σ-collapse). None ⇒ humble.
                            _cached.get("official_running_max_c"),
                            _cached.get("running_max_date", _now_str),
                        )

        return result

    async def _poll_metars(self) -> None:
        """
        Monitor open WEATHER_ARB positions using data already in _icao_metar_cache.
        No network I/O — _refresh_all_metars() has already fetched everything.
        """
        if not hasattr(self.bot, "_open_meta") or not hasattr(self.bot, "risk"):
            return

        # v2: active OFI exits (signal-decay / scalp-TP / time-cap). Isolated.
        try:
            await self._ofi_manage_exits()
        except Exception:
            logger.debug("[OFI] manage_exits call failed", exc_info=True)

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

        # ── M1β TP EXIT ───────────────────────────────────────────────────────
        # Sell NO when bid >= 0.999 — market has fully repriced, recycle capital.
        if M1_BETA_PROBE_ENABLED and hasattr(self.bot, "risk"):
            for _tp_tid, _tp_pos in list(self.bot.risk.open_positions.items()):
                if getattr(_tp_pos, "bond_entry_class", "") != "WEATHER_M1_PROBE":
                    continue
                _tp_bid = getattr(_tp_pos, "current_price", 0.0) or 0.0
                if _tp_bid < M1_BETA_PROBE_TP:
                    continue
                logger.info("[M1β] TP %.4f >= %.4f → sell %s shares=%.2f",
                            _tp_bid, M1_BETA_PROBE_TP, _tp_tid[:12], _tp_pos.shares)
                try:
                    await self.bot.orders.limit_sell(
                        token_id=_tp_tid,
                        price=round(_tp_bid - 0.001, 4),
                        size=_tp_pos.shares,
                        condition_id=_tp_pos.condition_id,
                    )
                    self.bot.risk.close_position(_tp_tid, exit_price=_tp_bid,
                                                 reason="M1B_TP")
                except Exception:
                    logger.exception("[M1β] TP sell failed %s", _tp_tid[:12])

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

    async def _stwa_signal_scan(self) -> None:
        """
        Shadow signal logger for the STWA Kalman engine.
        Runs every 60s (piggybacking the metar slow-path).
        Uses Gamma outcomePrices as best_ask proxy — no live CLOB calls needed.
        Logs signals to logs/shadow/hot/{date}/stwa_signals.jsonl for validation.
        """
        # Multi-day badatmath band shadow — runs independently of today's cache
        # (it does its own d/d+1/d+2 fetch). Isolated, shadow-only, no live path.
        try:
            await self._struct_band_multiday_shadow()
        except Exception:
            logger.debug("[STRUCT-BAND-MD] multiday shadow failed", exc_info=True)

        if self._stwa is None or not self._today_markets_cache:
            return

        import time as _t
        now = _t.time()

        # Per-city local-midnight reset: fire reset_city() when each city's local day rolls over.
        for entry in self._today_markets_cache:
            _city = entry["city"]
            # entry["city"] is the DISPLAY name from the market title ("Tel Aviv");
            # the engine keys cities by SLUG ("tel-aviv"). reset_city/_cities.get
            # must use the slug or they silently no-op (the reason reset_city never
            # fired and running_max went stale across the local-day boundary).
            _slug = CITY_NAME_TO_SLUG.get(_city, _city)
            _icao = entry.get("icao") or ""
            _tz_h = ICAO_UTC_OFFSET_H.get(_icao, 0)
            _local_day = int((now + _tz_h * 3600) // 86400)
            _prev = self._stwa_city_last_local_day.get(_city, 0)
            if _prev == 0:
                # Post-restart the in-memory tracker is empty, but cs.running_max
                # may have been restored STALE from disk (a prior local day). Seed
                # _prev from the local day the restored max actually belongs to
                # (running_max_ts) so a carried-over max gets RESET, not suppressed
                # by the first-sight guard. This was the 06-06→06-07 false-lockout
                # bleed: a restart near local midnight froze yesterday's high all
                # day, so every bucket below it became a false lockout that engine
                # model-NO shorted at ~0.50 hours before peak (n=11, −$27.21).
                _cs0 = self._stwa._cities.get(_slug)
                if _cs0 is not None and _cs0.running_max is not None and _cs0.running_max_ts:
                    _prev = int((_cs0.running_max_ts + _tz_h * 3600) // 86400)
            if _prev and _local_day != _prev:
                # Day rolled over → cs.running_max is the FINALISED official daily
                # high for the day that just ended. Feed the self-learning skill
                # matrix (closes the forecast↔actual loop) BEFORE reset_city wipes
                # it. log_actual had no live producer since wu_monitor was retired
                # (2026-05-31 resolution overhaul), so the matrix had been frozen
                # since 2026-05-22. Provenance: running_max is official-hourly
                # METAR/SPECI (AWC/NWS) only. valid_day is derived from _prev (the
                # ended local day), NOT cs.obs_date, so a new-day METAR that already
                # advanced obs_date can't mis-date the actual. (Midnight temps are
                # near the daily min, so monotone running_max isn't contaminated.)
                try:
                    _cs = self._stwa._cities.get(_slug)
                    if _cs is not None and _cs.running_max is not None:
                        _ended = _t.strftime("%Y-%m-%d", _t.gmtime(_prev * 86400))
                        _aslug = _slug
                        from analysis.weather.live_accumulator import log_actual as _la
                        _la(
                            slug=f"stwa-actual-{_aslug}-{_ended}",
                            city_slug=_aslug,
                            valid_day=_ended,
                            wu_high_c=float(_cs.running_max),
                        )
                except Exception:
                    logger.debug("[STWA] skill-matrix log_actual hook failed for %s", _city, exc_info=True)
                self._stwa.reset_city(_slug)
            self._stwa_city_last_local_day[_city] = _local_day

        bucket_map:  dict[str, list]  = {}
        t_close_map: dict[str, float] = {}
        clob_books:  dict[str, dict]  = {}

        for entry in self._today_markets_cache:
            city = entry["city"]
            icao = entry["icao"]
            mkt  = entry["mkt"]

            if mkt.get("closed", False):
                continue

            token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            if not token_ids:
                continue
            yes_tok = token_ids[0]
            no_tok  = token_ids[1] if len(token_ids) > 1 else ""

            slug = CITY_NAME_TO_SLUG.get(city, "")
            if not slug:
                continue

            lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
            if lo_c is None and hi_c is None:
                continue

            # Gamma outcomePrices[0] = YES price; treat as best_ask proxy
            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            try:
                yes_ask = float(prices[0])
            except (IndexError, ValueError):
                continue

            # P0-A: include tail buckets with sentinel bounds so the MC's
            # path_max integration covers (-∞, ∞). Without this the NEG_RISK_ARB
            # detection assumes only-middle buckets are exhaustive — they aren't.
            # The exhaustivity gate (Σp_model > 0.95 in engine) then refuses arb
            # if any tail bucket is missing from this scan.
            lo_c_eff = -999.0 if lo_c is None else lo_c
            hi_c_eff = +999.0 if hi_c is None else hi_c
            bucket_map.setdefault(slug, []).append((lo_c_eff, hi_c_eff, yes_tok, no_tok))
            # usd_depth=0.0 marks "not yet fetched"; the engine will treat 0
            # as "skip depth clamp". Real depth is fetched below for cities
            # where an arb is plausible.
            clob_books[yes_tok] = {"best_ask": yes_ask, "best_bid": max(0.0, yes_ask - 0.02), "usd_depth": 0.0}
            if no_tok:
                no_ask = round(1.0 - yes_ask, 4)
                clob_books[no_tok] = {"best_ask": no_ask, "best_bid": max(0.0, no_ask - 0.02), "usd_depth": 0.0}

            # t_close = unix ts of local midnight resolution (keyed by slug)
            end_date = mkt.get("endDate", "")[:10]
            if end_date and slug not in t_close_map:
                hrs_rem = self._hours_to_local_resolution(end_date, icao)
                t_close_map[slug] = now + hrs_rem * 3600.0

        if not bucket_map:
            return

        # P0-B: pre-fetch real CLOB top-of-book + depth for cities where an arb
        # is plausible (Σ proxy YES ask < NEG_RISK_ARB_THR + 0.10 slack). Without
        # this, the engine's NEG_RISK_ARB ran on stale Gamma prices and fake
        # usd_depth=999, so the depth-clamp did nothing. Skipping low-arb-
        # likelihood cities keeps the HTTP cost bounded (~5-10 cities × 9-11
        # buckets ≈ 100 fetches per scan rather than 500+).
        from strategy.stwa_engine import NEG_RISK_ARB_THR as _ARB_THR, PRICE_FLOOR as _PRICE_FLOOR
        arb_screen_thr = _ARB_THR + 0.10
        cities_for_depth_fetch = []
        for _slug, _bks in bucket_map.items():
            _sum_yes = sum(
                (clob_books.get(_yes) or {}).get("best_ask", 1.0)
                for _lo, _hi, _yes, _no in _bks
            )
            if _sum_yes < arb_screen_thr:
                cities_for_depth_fetch.append(_slug)

        # Favorite-longshot NO: fetch real top-5 book for NO tokens whose proxy ask is
        # in the actionable zone [PRICE_FLOOR, 0.96]. These cities (Σyes>1) are NEVER
        # arb candidates, so their NO depth was previously never measured (logged 0.0).
        # Bounded to FAV_NO_DEPTH_CAP tokens/scan, prioritized toward the peak-edge zone.
        FAV_NO_DEPTH_CAP = 150
        _fav_no = []
        for _slug, _bks in bucket_map.items():
            for _lo, _hi, _yes, _no in _bks:
                if not _no:
                    continue
                _na = (clob_books.get(_no) or {}).get("best_ask")
                if _na is not None and _PRICE_FLOOR <= _na <= 0.96:
                    _fav_no.append((abs(_na - 0.65), _no))   # closest to peak-edge first
        _fav_no.sort(key=lambda x: x[0])
        _fav_no_toks = [t for _, t in _fav_no[:FAV_NO_DEPTH_CAP]]

        if cities_for_depth_fetch or _fav_no_toks:
            _toks_to_fetch = []
            for _slug in cities_for_depth_fetch:
                for _lo, _hi, _yes, _no in bucket_map[_slug]:
                    _toks_to_fetch.append(_yes)
                    if _no:
                        _toks_to_fetch.append(_no)
            _toks_to_fetch.extend(_fav_no_toks)
            _toks_to_fetch = list(dict.fromkeys(_toks_to_fetch))   # dedup, preserve order
            # Parallel-fetch top-5 levels; aiohttp inside _fetch_book_levels
            # creates its own session per call (ok for ~100 calls).
            import asyncio as _aio
            _books = await _aio.gather(
                *[self._fetch_book_levels(_t, n=5) for _t in _toks_to_fetch],
                return_exceptions=True,
            )
            _enriched = 0
            for _tok, _b in zip(_toks_to_fetch, _books):
                if isinstance(_b, Exception) or not isinstance(_b, dict):
                    continue
                _asks = _b.get("asks") or []
                if not _asks:
                    continue
                _best_ask = _asks[0]["price"]
                _depth = sum(a["price"] * a["size"] for a in _asks)
                # Update if depth is meaningful (> $1) and price is fillable
                if 0 < _best_ask < 1.0 and _depth > 0:
                    clob_books[_tok]["best_ask"] = _best_ask
                    clob_books[_tok]["usd_depth"] = round(_depth, 2)
                    _enriched += 1
            logger.info("[STWA] depth pre-fetch: %d/%d tokens enriched (%d arb-cities + %d favorite-longshot NO)",
                        _enriched, len(_toks_to_fetch), len(cities_for_depth_fetch), len(_fav_no_toks))

        # NO-arb real-book SHADOW probe (no capital): the Σyes<0.95 fetch above
        # NEVER covers NO-arb-eligible cities (Σyes>1), so Face 2 has only ever
        # seen Gamma-proxy prices. Measure the real book to see if an arb exists.
        try:
            await self._no_arb_shadow_probe(bucket_map, clob_books, now)
        except Exception:
            logger.debug("[NO-ARB-PROBE] probe failed (isolated)", exc_info=True)

        # Fade-shadow real-book recorder (gate-INDEPENDENT, no capital). Two prior
        # blind spots, both fixed here:
        #   (1) the engine's fade logger only sees Gamma-proxy NO (usd_depth=0,
        #       no_ask=complement) — real CLOB books are fetched only for the
        #       Σyes<0.95 arb screen, which never covers post-peak fade cities.
        #   (2) that logger lives INSIDE the gated allocator, so it never runs for
        #       the 13-14 cities/scan dropped on the regime gate (REGIME_FIRE) — but
        #       the resolution-sampling-bias edge is NOT regime-dependent, so those
        #       cities belong in the sample.
        # Here we fetch the REAL NO book for the ≤3 bins immediately above
        # running_max (prime fade target = rank_above 0) and write the fade row for
        # EVERY post-peak city with a running_max, independent of trade-eligibility.
        # Read-only/shadow: isolated in try/except, cannot disturb the live path.
        try:
            from strategy.stwa_engine import _phase as _stwa_phase
            _fade_cands = []   # (slug, cs, [(lo,hi,yes_tok,no_tok), ...] top-3 above rm)
            _fade_toks: list[str] = []
            for _slug, _bks in bucket_map.items():
                _csf = (self._stwa._cities.get(_slug) if self._stwa else None)
                if _csf is None or _csf.running_max is None or _slug not in t_close_map:
                    continue
                if _stwa_phase(_csf, t_close_map[_slug], now) not in ("AT_PEAK", "POST_PEAK"):
                    continue
                _rmf = float(_csf.running_max)
                _abf = sorted([b for b in _bks if b[0] >= _rmf], key=lambda e: e[0])[:3]
                if not _abf:
                    continue
                _fade_cands.append((_slug, _csf, _abf))
                for _lo, _hi, _y, _n in _abf[:2]:   # fetch real book for rank 0-1
                    if _n:
                        _fade_toks.append(_n)
            if _fade_toks:
                import asyncio as _aiof
                _fbooks = await _aiof.gather(
                    *[self._fetch_book_levels(_t, n=5) for _t in _fade_toks],
                    return_exceptions=True,
                )
                _fenr = 0
                for _tok, _fb in zip(_fade_toks, _fbooks):
                    if isinstance(_fb, Exception) or not isinstance(_fb, dict):
                        continue
                    _fasks = _fb.get("asks") or []
                    _fbids = _fb.get("bids") or []
                    if not _fasks:
                        continue
                    _fba = _fasks[0]["price"]
                    _fdepth = sum(a["price"] * a["size"] for a in _fasks)
                    if 0 < _fba < 1.0 and _fdepth > 0:
                        _ent = clob_books.setdefault(_tok, {})
                        _ent["best_ask"] = _fba
                        _ent["usd_depth"] = round(_fdepth, 2)
                        if _fbids:
                            _ent["best_bid"] = _fbids[0]["price"]
                        _fenr += 1
                logger.info("[STWA] fade depth pre-fetch: %d/%d NO tokens enriched (%d cities)",
                            _fenr, len(_fade_toks), len(_fade_cands))
            if _fade_cands:
                _fd_dir = (Path(__file__).parent.parent / "logs" / "shadow"
                           / "hot" / time.strftime("%Y-%m-%d", time.gmtime()))
                _fd_dir.mkdir(parents=True, exist_ok=True)
                with (_fd_dir / "fade_shadow.jsonl").open("a") as _ff:
                    for _slug, _csf, _abf in _fade_cands:
                        _rec = {
                            "ts": now, "city": _slug,
                            "phase": _stwa_phase(_csf, t_close_map[_slug], now),
                            "regime": getattr(_csf, "regime", None),
                            "running_max_c": round(float(_csf.running_max), 2),
                            "rm_age_s": round(now - getattr(_csf, "running_max_ts", now), 0),
                            "fade_bins": [{
                                "lo": _lo, "hi": _hi, "no_tok": _n,
                                "no_ask": (clob_books.get(_n) or {}).get("best_ask"),
                                "no_bid": (clob_books.get(_n) or {}).get("best_bid"),
                                "no_depth_usd": (clob_books.get(_n) or {}).get("usd_depth"),
                                "yes_ask": (clob_books.get(_y) or {}).get("best_ask"),
                                "fair": None,
                                "rank_above": _i,
                            } for _i, (_lo, _hi, _y, _n) in enumerate(_abf)],
                        }
                        _ff.write(json.dumps(_rec) + "\n")

            # ── LIVE FADE FIRE (user GO-LIVE 2026-06-02) ─────────────────────
            # Buy NO on the prime bin immediately above the OFFICIAL (AWC/NWS-clean)
            # running_max, POST_PEAK only. Prime bin is selected RELATIVE TO OFFICIAL
            # (provenance — never the possibly-contaminated engine running_max); the
            # real-book depth gate is the fillability safety net. n=0 resolved live —
            # dissent on record (see FADE_* constants). Per-city try so one fire
            # error can't stop the others.
            if FADE_LIVE_ENABLED and _fade_cands:
                from datetime import datetime as _dtf, timezone as _tzf, timedelta as _tdf
                from analysis.weather.stations import STATIONS as _FADE_ST
                _now_utc = _dtf.now(_tzf.utc)
                _tok2mkt = {}
                for _e in (self._today_markets_cache or []):
                    _m = _e.get("mkt") or {}
                    _tids = _parse_token_ids(_m.get("clobTokenIds", []))
                    if len(_tids) >= 2:
                        _tok2mkt[_tids[1]] = (_m, _e.get("city"), _e.get("icao"))
                for _slug, _csf, _abf in _fade_cands:
                    try:
                        if _stwa_phase(_csf, t_close_map[_slug], now) != "POST_PEAK":
                            continue
                        _st = _FADE_ST.get(_slug)
                        _icao = getattr(_st, "icao", None) if _st else None
                        if not _icao:
                            continue
                        if _icao in M1_BETA_PROBE_ORACLE_BLOCK_ICAO:
                            continue  # 2026-06-08: oracle-clean gate — provenance-divergent cities (reuse M1β blocklist)
                        _mc = self._icao_metar_cache.get(_icao) or {}
                        _tzh = ICAO_UTC_OFFSET_H.get(_icao, 0)
                        _ltoday = (_now_utc + _tdf(hours=_tzh)).date().isoformat()
                        if _mc.get("running_max_date", "") != _ltoday:
                            continue  # stale provenance — never fire on yesterday's high
                        _off = _mc.get("official_running_max_c")
                        if _off is None:
                            continue  # no AWC/NWS-clean value in hand → skip (fail-safe)
                        _pbins = sorted([b for b in bucket_map.get(_slug, []) if b[0] >= _off],
                                        key=lambda e: e[0])
                        if not _pbins:
                            continue
                        _lo, _hi, _y, _n = _pbins[0]   # prime = lowest bin above official high
                        if not _n:
                            continue
                        if not (0.0 <= float(_lo) - float(_off) <= FADE_MAX_GAP_C):
                            continue
                        _bk = clob_books.get(_n) or {}
                        _na = _bk.get("best_ask")
                        _dep = _bk.get("usd_depth") or 0.0
                        if _na is None or not (FADE_NO_ASK_MIN <= _na <= FADE_NO_ASK_MAX):
                            continue
                        if _dep < FADE_MIN_SHARES * _na:
                            continue  # need ≥5 fillable shares (still rejects proxy books w/ ~0 depth)
                        _sec_close = (t_close_map.get(_slug, now) - now)
                        if _sec_close < FADE_MIN_SEC_TO_CLOSE:
                            continue
                        _mm = _tok2mkt.get(_n)
                        if not _mm:
                            continue
                        _mkt2, _cname, _icao2 = _mm
                        await self._fade_evaluate(
                            slug=_slug, city=_cname or _slug, icao=_icao, mkt=_mkt2,
                            lo_c=float(_lo), hi_c=float(_hi), no_token_id=_n,
                            no_ask=float(_na), no_depth_usd=float(_dep), no_book=_bk,
                            official_rm=float(_off), phase="POST_PEAK",
                            end_date=(_mkt2.get("endDate") or "")[:10],
                            question=_mkt2.get("question", ""),
                            now_ts=now, now_utc=_now_utc, seconds_to_close=_sec_close)
                    except Exception:
                        logger.debug("[FADE] live fire failed (isolated) %s", _slug, exc_info=True)
        except Exception:
            logger.debug("[STWA] fade shadow recorder failed (isolated)", exc_info=True)

        # ── FAVORITE-YES live fire (user GO-LIVE 2026-06-03, Tier-3 override of n≥100) ──
        # Buy YES on confident OPEN-ENDED cumulative-tail buckets priced [0.60,0.98]
        # (favorite-longshot underpricing; n=10-19 TREND-ONLY, dissent on record). Bounded:
        # small flat stake + daily cap. Real-CLOB-book gated (Gamma proxy screens which
        # tails to fetch; the real book confirms the ask + fillable depth). Isolated
        # try/except — cannot disturb the live path.
        if FAVYES_LIVE_ENABLED:
            try:
                _fy_today = time.strftime("%Y-%m-%d", time.gmtime())
                if getattr(self, "_favyes_fires_date", "") != _fy_today:
                    self._favyes_fires_date = _fy_today
                    self._favyes_fires_today = 0
                if getattr(self, "_favyes_fires_today", 0) < FAVYES_MAX_DAILY_FIRES:
                    _fy_fired = getattr(self, "_favyes_fired", set())
                    _fy_cands = []          # (slug, lo, hi, yes_tok)
                    _fy_toks: list[str] = []
                    for _slug, _bks in bucket_map.items():
                        for _lo, _hi, _y, _n in _bks:
                            if not _y or _y in _fy_fired:
                                continue
                            if not ((_lo <= -990.0) or (_hi >= 990.0)):
                                continue   # OPEN-ENDED cumulative tails only
                            _pa = (clob_books.get(_y) or {}).get("best_ask")
                            if _pa is None or not (0.55 <= _pa <= 0.99):
                                continue   # screen by Gamma proxy before paying for a real fetch
                            _fy_cands.append((_slug, _lo, _hi, _y))
                            _fy_toks.append(_y)
                    if _fy_toks:
                        import asyncio as _aiofy
                        _fybooks = await _aiofy.gather(
                            *[self._fetch_book_levels(_t, n=5) for _t in _fy_toks],
                            return_exceptions=True)
                        for _t, _fb in zip(_fy_toks, _fybooks):
                            if isinstance(_fb, Exception) or not isinstance(_fb, dict):
                                continue
                            _asks = _fb.get("asks") or []
                            if not _asks:
                                continue
                            _ba = _asks[0]["price"]
                            _depth = sum(a["price"] * a["size"] for a in _asks)
                            if 0 < _ba < 1.0 and _depth > 0:
                                _e = clob_books.setdefault(_t, {})
                                _e["best_ask"] = _ba
                                _e["usd_depth"] = round(_depth, 2)
                        from strategy.stwa_engine import _phase as _fy_phase
                        from datetime import datetime as _dtfy, timezone as _tzfy
                        _now_utc_fy = _dtfy.now(_tzfy.utc)
                        _ytok2mkt = {}
                        for _e2 in (self._today_markets_cache or []):
                            _m = _e2.get("mkt") or {}
                            _tids = _parse_token_ids(_m.get("clobTokenIds", []))
                            if _tids:
                                _ytok2mkt[_tids[0]] = (_m, _e2.get("city"), _e2.get("icao"))
                        for _slug, _lo, _hi, _y in _fy_cands:
                            if getattr(self, "_favyes_fires_today", 0) >= FAVYES_MAX_DAILY_FIRES:
                                break
                            try:
                                _bk = clob_books.get(_y) or {}
                                _ya = _bk.get("best_ask")
                                _dep = _bk.get("usd_depth") or 0.0
                                if _ya is None or not (FAVYES_MIN_ASK <= _ya <= FAVYES_MAX_ASK):
                                    continue
                                if _dep < FAVYES_MIN_SHARES * _ya:
                                    continue   # need ≥5 fillable YES shares (rejects proxy/thin books)
                                _sec_close = (t_close_map.get(_slug, now) - now)
                                if _sec_close < FAVYES_MIN_SEC_TO_CLOSE:
                                    continue
                                _mm = _ytok2mkt.get(_y)
                                if not _mm:
                                    continue
                                _mkt2, _cname, _icao2 = _mm
                                if _icao2 == "VHHH":
                                    continue   # Hong Kong blocked (HKO oracle ≠ VHHH)
                                _csf2 = (self._stwa._cities.get(_slug) if self._stwa else None)
                                _ph = (_fy_phase(_csf2, t_close_map[_slug], now)
                                       if (_csf2 is not None and _slug in t_close_map) else "NA")
                                await self._favorite_evaluate(
                                    slug=_slug, city=_cname or _slug, icao=_icao2 or "",
                                    mkt=_mkt2, lo_c=float(_lo), hi_c=float(_hi),
                                    yes_token_id=_y, yes_ask=float(_ya),
                                    yes_depth_usd=float(_dep), phase=_ph,
                                    end_date=(_mkt2.get("endDate") or "")[:10],
                                    question=_mkt2.get("question", ""),
                                    now_ts=now, now_utc=_now_utc_fy, seconds_to_close=_sec_close)
                            except Exception:
                                logger.debug("[FAVYES] live fire failed (isolated) %s", _slug, exc_info=True)
            except Exception:
                logger.debug("[FAVYES] recorder failed (isolated)", exc_info=True)

        # ── WEATHER OFI MOMENTUM live fire (user GO-LIVE 2026-06-02; hold-to-res v1) ──
        # OFI from the maker_flow tail → taker-buy the flow-aligned token, register
        # WEATHER_OFI (settler holds to resolution = validated +EV on these ≤15-min
        # windows). HARD CAPS: $2/fill, ≤3 concurrent, ≤10 fires/day, 1/bucket/day.
        # On-record dissent: n=0 LIVE; user chose go-live-tiny over shadow-first.
        try:
            if OFI_LIVE_ENABLED:
                from datetime import datetime as _dto, timezone as _tzo
                from strategy.momentum import Direction as _DirO, TPSLLevels as _TPSLO
                from execution.order_manager import OrderStatus as _OSO
                _today = _dto.now(_tzo.utc).date().isoformat()
                if getattr(self, "_ofi_day", None) != _today:
                    self._ofi_day = _today
                    self._ofi_fired = set()
                    self._ofi_fires_today = 0
                _open_ofi = sum(1 for _p in self.bot.risk.open_positions.values()
                                if getattr(_p, "bond_entry_class", "") == "WEATHER_OFI")
                if self._ofi_fires_today < OFI_MAX_FIRES_DAY and _open_ofi < OFI_MAX_CONCURRENT:
                    _ofi_map = self._ofi_from_tape(now)
                    _cid2mkt = {}
                    for _e in (self._today_markets_cache or []):
                        _m = _e.get("mkt") or {}
                        _tids = _parse_token_ids(_m.get("clobTokenIds", []))
                        _cid = _m.get("conditionId")
                        if _cid and len(_tids) >= 2:
                            _cid2mkt[_cid] = (_m, _e.get("city"), _e.get("icao"), _tids[0], _tids[1])
                    _now_utc_o = _dto.now(_tzo.utc)
                    for _cid, (_ofi, _vol) in _ofi_map.items():
                        if abs(_ofi) < OFI_MIN or _cid in self._ofi_fired:
                            continue
                        if self._ofi_fires_today >= OFI_MAX_FIRES_DAY or _open_ofi >= OFI_MAX_CONCURRENT:
                            break
                        _mm = _cid2mkt.get(_cid)
                        if not _mm:
                            continue
                        _mkt, _city, _icao, _yes, _no = _mm
                        _up = _ofi > 0
                        _tok = _yes if _up else _no
                        _dir = _DirO.BUY_YES if _up else _DirO.BUY_NO
                        if _tok in self.bot.risk.open_positions:
                            continue
                        try:
                            _bk = await self._fetch_book_levels(_tok, n=5)
                            _asks = _bk.get("asks") or []
                            _bids = _bk.get("bids") or []
                            if not _asks or not _bids:
                                continue
                            _ba = float(_asks[0]["price"]); _bb = float(_bids[0]["price"])
                            _mid = 0.5 * (_ba + _bb)
                            _depth = sum(float(_a["usd"]) for _a in _asks if float(_a["price"]) <= _ba + 0.03)
                            if not (OFI_MID_LO <= _mid <= OFI_MID_HI) or _depth < OFI_MIN_DEPTH_USD:
                                continue
                            try:
                                _ec = _dto.fromisoformat((_mkt.get("endDate") or "").replace("Z", "+00:00"))
                                _stc = (_ec - _now_utc_o).total_seconds()
                            except Exception:
                                _stc = 9e9
                            if _stc < OFI_MIN_SEC_TO_CLOSE:
                                continue
                            logger.info("[OFI] FIRE %s %s ofi=%+.2f vol=$%.0f mid=%.3f depth=$%.0f stc=%.0f",
                                        _city, ("YES" if _up else "NO"), _ofi, _vol, _mid, _depth, _stc)
                            _fill = await self.bot.orders.limit_buy(
                                token_id=_tok, intended_price=_ba, stake_usd=OFI_STAKE_USD,
                                direction=_dir, neg_risk=_mkt.get("negRisk", True), fast_fail=False,
                            )
                            self._ofi_fired.add(_cid)   # one attempt per bucket/day
                            _filled = (_fill.status == _OSO.FILLED and _fill.total_size > 0)
                            _fp = float(_fill.avg_fill_price) if _filled else None
                            _fs = float(_fill.total_size) if _filled else 0.0
                            try:
                                _ld = Path("logs/shadow/hot") / _now_utc_o.date().isoformat()
                                _ld.mkdir(parents=True, exist_ok=True)
                                (_ld / "ofi_live.jsonl").open("a").write(json.dumps({
                                    "ts": now, "city": _city, "cid": _cid, "dir": ("YES" if _up else "NO"),
                                    "ofi": round(_ofi, 4), "vol_usd": round(_vol, 1), "mid": round(_mid, 4),
                                    "best_ask": _ba, "depth_usd": round(_depth, 1), "sec_to_close": round(_stc),
                                    "filled": _filled, "fill_price": _fp, "fill_size": _fs,
                                    "question": _mkt.get("question", ""),
                                }) + "\n")
                            except Exception:
                                pass
                            if not _filled or _tok in self.bot.risk.open_positions:
                                continue
                            self.bot.risk.open_position(
                                token_id=_tok, asset="WEATHER", direction=_dir,
                                stake=_fs * _fp, entry_price=_fp,
                                tpsl=_TPSLO(take_profit=0.0, stop_loss=0.0, tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
                                condition_id=_cid, window_end_ts=0.0, is_bond=True,
                                bond_outcome_direction=("up" if _up else "down"),
                                bond_entry_class="WEATHER_OFI",
                            )
                            _meta = self.bot._open_meta.setdefault(_tok, {})
                            _meta["signal_source"] = f"WEATHER/{_city}/WEATHER_OFI"
                            _meta["city"] = _city
                            _meta["icao"] = _icao
                            _meta["weather_question"] = _mkt.get("question", "")
                            _meta["weather_date"] = (_mkt.get("endDate") or "")[:10]
                            self._ofi_fires_today += 1
                            _open_ofi += 1
                            logger.info("[OFI] FILLED %s %s @%.4f size=%.1f stake=$%.2f",
                                        _city, ("YES" if _up else "NO"), _fp, _fs, _fs * _fp)
                        except Exception:
                            logger.debug("[OFI] live fire failed (isolated) %s", _cid, exc_info=True)
        except Exception:
            logger.debug("[OFI] block failed (isolated)", exc_info=True)

        # Tier-4: capital already deployed per city today (open WEATHER_STWA
        # positions). Feeds the per-city-day budget R = budget − held_k so the
        # allocator caps total city-day exposure instead of re-deploying the full
        # budget every cycle (the cross-time multi-YES accumulation fix).
        held_k_by_city: dict[str, float] = {}
        _op = getattr(self.bot.risk, "open_positions", {})
        for _tid, _pos in _op.items():
            if getattr(_pos, "bond_entry_class", "") != "WEATHER_STWA":
                continue
            # Date-scope: only count today's deployment. Stale positions (>28h,
            # awaiting the resolution loop) must not keep starving the per-city-day
            # arb budget. The resolution loop closes them; this bridges the gap.
            if (time.time() - getattr(_pos, "open_ts", 0.0)) > 100_800:
                continue
            _c = (self.bot._open_meta.get(_tid, {}) or {}).get("city")
            if not _c:
                continue
            _rem = getattr(_pos, "remaining_shares", 0.0) or 0.0
            held_k_by_city[_c] = held_k_by_city.get(_c, 0.0) + _rem * _pos.entry_price

        try:
            signals = self._stwa.get_signals(
                clob_books=clob_books,
                bucket_map=bucket_map,
                t_close_map=t_close_map,
                bankroll=self._get_bankroll(),
                t_now=now,
                held_k_by_city=held_k_by_city,
            )
        except Exception:
            logger.exception("[STWA] get_signals error")
            return

        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        out_dir  = Path(__file__).parent.parent / "logs" / "shadow" / "hot" / today
        out_dir.mkdir(parents=True, exist_ok=True)

        # Per-bucket pricer comparison (MC vs GEV vs peak-anchored), logged for
        # every priced city regardless of whether a signal fired — this is how
        # the suspended-YES calibration gets validated before any re-enable.
        _pricer_rows = getattr(self._stwa, "_last_pricer_rows", []) or []
        if _pricer_rows:
            with open(out_dir / "stwa_pricer_eval.jsonl", "a") as _pf:
                for _r in _pricer_rows:
                    _r2 = dict(_r); _r2["ts"] = now
                    _pf.write(json.dumps(_r2) + "\n")

        # 2026-06-12 (Claude): BASKET EXIT SHADOW (write-only, no live behavior).
        # Per held city basket, log the mirror-bid cash-out value (Σ sh·bid,
        # bid = 1 − opposite-side ask) vs cost vs best-possible hold payoff.
        # Purpose: accumulate n≥100 on the "cash green baskets at d+0 beats
        # holding" hypothesis. Exit-dominance analysis 06-12: a guaranteed-
        # dominant exit is impossible (Σ ladder bids pegged ≤0.999), but the
        # EV question is open — ex-post 5/6 resolved basket-days favored
        # exiting (n=8, trend-only). Revert: delete block + helper.
        try:
            self._log_basket_exit_shadow(out_dir, bucket_map, clob_books,
                                         t_close_map, now)
        except Exception:
            logger.debug("[STWA] basket_exit_shadow log failed", exc_info=True)

        if not signals:
            return

        out_path = out_dir / "stwa_signals.jsonl"

        # Fetch live CLOB ask for each signal token (top-of-book, 4s timeout).
        # This replaces the stale Gamma proxy price with the real fillable price.
        clob_ask_live: dict[str, float] = {}
        for sig in signals:
            try:
                book = await self._fetch_book_levels(sig.token_id, n=1)
                asks = book.get("asks", [])
                if asks:
                    clob_ask_live[sig.token_id] = asks[0]["price"]
            except Exception:
                pass

        import dataclasses
        with open(out_path, "a") as fh:
            for sig in signals:
                row = dataclasses.asdict(sig)
                row["ts"] = now
                row["bucket"] = list(sig.bucket)
                row["clob_ask_live"] = clob_ask_live.get(sig.token_id)
                # NO floored/forecast audit: stamp the running-max (M0) and the
                # PA-shrunk center at decision time so post-hoc classification is
                # reliable (floored ⟺ running_max ≥ bucket_hi) without a fragile
                # nearest-ts pricer_eval join. Lets us measure whether forecast-NO
                # WR tracks per-city model error once clean (post-floor-fix) data
                # accumulates. cs.city key is the slug, same as sig.city.
                _cs = self._stwa._cities.get(sig.city)
                _rm = _cs.running_max if _cs is not None else None
                row["running_max"] = _rm
                row["model_center"] = round(_cs.ps_center_last, 3) if _cs is not None else None
                row["floored"] = (_rm is not None and _rm >= sig.bucket[1])
                fh.write(json.dumps(row) + "\n")

        logger.info("[STWA] %d signal(s) logged to %s", len(signals), out_path)

        if not STWA_LIVE:
            return

        # Kill-switch gate (mirrors cas_lowask/volarb/LDA): never deploy capital
        # while the shared bankroll is halted/ruined. NOTE: the thresholds are
        # config-disabled today (max_daily_loss_pct=0, ruin_floor=0) so this is
        # inert until the user re-arms them (a Tier-3 cross-strategy decision).
        # The resolution loop is separate, so settlement still proceeds when halted.
        _bk = self.bot.risk.bankroll
        if _bk.is_ruined or _bk.is_halted:
            logger.warning("[STWA] kill-switch active (halted=%s ruined=%s) — no entries this cycle",
                           _bk.is_halted, _bk.is_ruined)
            return

        # ── Live execution ────────────────────────────────────────────────────
        # Build token → market dict lookup once for this scan cycle.
        tok_to_entry: dict[str, dict] = {}
        for _entry in self._today_markets_cache:
            _tids = _parse_token_ids(_entry["mkt"].get("clobTokenIds", []))
            for _tid in _tids:
                tok_to_entry[_tid] = _entry

        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus

        # Reset daily city cap at UTC midnight.
        _today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if _today_str != self._stwa_fires_date:
            self._stwa_city_fires_today.clear()
            self._stwa_fires_date = _today_str

        # LP already sized stakes and ordered signals by edge/ask.
        # No count cap — budget exhaustion in the engine is the natural limit.
        for sig in signals:
            is_arb = (sig.confidence >= 1.0)  # NEG_RISK_ARB signals have confidence=1.0

            # Arb bypasses _fired_tokens: we may already hold one side of a bucket
            # (e.g. YES [30.8,31.9] from earlier today) and still need to fill it
            # again as part of the arb structure.
            if not is_arb and sig.token_id in self._fired_tokens:
                continue

            # Arb dedup: if we already hold this exact token, skip — the arb
            # for this bucket is already in the wallet. Without this, the arb
            # re-fires every scan minute because it bypasses _fired_tokens above.
            if is_arb and sig.token_id in getattr(self.bot.risk, "open_positions", {}):
                continue

            entry = tok_to_entry.get(sig.token_id)
            if entry is None:
                continue

            # Opposite-direction dedup (regular signals only): if we already hold
            # the other side of this bucket, skip to avoid cancelling positions.
            if not is_arb:
                mkt_tids = _parse_token_ids(entry["mkt"].get("clobTokenIds", []))
                open_pos = getattr(self.bot.risk, "open_positions", {})
                if any(t != sig.token_id and t in open_pos for t in mkt_tids):
                    logger.debug("[STWA] skip %s %s — opposite direction already held",
                                 sig.city, sig.direction)
                    continue

            # Use live CLOB ask; skip dead markets and ask drift.
            live_ask = clob_ask_live.get(sig.token_id)
            if live_ask is None:
                continue

            # ── STRUCT_BAND maker leg: post a RESTING bid (not a taker buy). The band
            # is structural (engine-gated), so it bypasses the taker p_win edge-gate
            # below (its p_model is 0). One resting quote per token/day (_fired_tokens).
            if getattr(sig, "maker", False):
                try:
                    await self._struct_band_post_maker(sig, entry["mkt"], live_ask)
                except Exception:
                    logger.debug("[STRUCT-BAND] post failed %s", sig.city, exc_info=True)
                for _t in _parse_token_ids(entry["mkt"].get("clobTokenIds", [])):
                    self._fired_tokens.add(_t)
                continue

            if is_arb:
                # Arb bucket: only kill if truly zero (ask=0 = resolved token).
                # Near-zero asks (0.0005) are still fillable and part of the structure.
                if live_ask <= 0:
                    continue
                if abs(live_ask - sig.ask) > 0.15:
                    logger.debug("[STWA] arb skip %s — ask drifted %.4f→%.4f",
                                 sig.city, sig.ask, live_ask)
                    continue
            else:
                if live_ask < 0.05:  # resolved/illiquid market — no fills possible
                    continue
                if abs(live_ask - sig.ask) > 0.05:
                    logger.debug("[STWA] skip %s %s — ask drifted %.3f→%.3f",
                                 sig.city, sig.direction, sig.ask, live_ask)
                    continue
                p_win = (1.0 - sig.p_model) if sig.direction == "NO" else sig.p_model
                if p_win - live_ask < EDGE_MIN:
                    continue

            # Block both YES and NO sides of this bucket — prevents opposite-direction
            # re-entry after model swings or restart clears _fired_tokens.
            mkt = entry["mkt"]
            for _all_tid in _parse_token_ids(mkt.get("clobTokenIds", [])):
                self._fired_tokens.add(_all_tid)
            neg_risk  = mkt.get("negRisk", True)
            cond_id   = mkt.get("conditionId", "")
            direction = _Dir.BUY_NO if sig.direction == "NO" else _Dir.BUY_YES
            bond_out  = "down" if sig.direction == "NO" else "up"

            _lo_s = "−∞" if sig.bucket[0] <= -500 else f"{sig.bucket[0]:.1f}"
            _hi_s = "+∞" if sig.bucket[1] >= 500  else f"{sig.bucket[1]:.1f}"
            # For regular signals, p_win was computed at the edge gate above.
            # For arb, the meaningful edge is sig.edge (the arb_edge from engine).
            _log_edge = sig.edge if is_arb else (p_win - live_ask)
            # EV-bounded deep sweep (favorite-longshot NO): walk the book up to the
            # highest avg price that still keeps a STWA_NO_SWEEP_EV_FLOOR edge, so we
            # fill real size across levels instead of just the (often thin) top ask.
            # Depth auto-scales with edge: fat-edge NO sweeps deep, thin-edge buys at
            # touch (ceiling ≤ live_ask ⇒ limit_buy uses max(intended, ceiling)).
            _pc = None
            if (not is_arb) and sig.direction == "NO":
                _pc = round(p_win - STWA_NO_SWEEP_EV_FLOOR, 4)
            logger.info("[STWA] ENTER %s %s [%s,%s] p=%.3f ask=%.3f edge=%.3f stake=$%.2f sweep_cap=%s",
                        sig.city, sig.direction, _lo_s, _hi_s,
                        sig.p_model, live_ask, _log_edge, sig.stake,
                        (f"{_pc:.3f}" if _pc is not None else "—"))
            try:
                fill = await self.bot.orders.limit_buy(
                    token_id=sig.token_id,
                    intended_price=live_ask,
                    stake_usd=sig.stake,
                    direction=direction,
                    neg_risk=neg_risk,
                    price_ceiling=_pc,
                    fast_fail=False,
                )
            except Exception:
                logger.exception("[STWA] order error %s", sig.city)
                self._fired_tokens.discard(sig.token_id)
                city_fires[sig.city] -= 1
                continue

            if fill.status == OrderStatus.FILLED and fill.total_size > 0:
                fp = float(fill.avg_fill_price)
                fs = float(fill.total_size)
                self.bot.risk.open_position(
                    token_id=sig.token_id,
                    asset="WEATHER",
                    direction=direction,
                    stake=fs * fp,
                    entry_price=fp,
                    tpsl=_TPSL(take_profit=0.0, stop_loss=0.0,
                                tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
                    condition_id=cond_id,
                    window_end_ts=0.0,
                    is_bond=True,
                    bond_outcome_direction=bond_out,
                    bond_entry_class="WEATHER_STWA",
                )
                meta = self.bot._open_meta.setdefault(sig.token_id, {})
                meta["signal_source"] = "WEATHER/%s/STWA" % sig.city
                meta["city"] = sig.city
                logger.info("[STWA] FILLED %s %s @%.3f shares=%.1f cost=$%.2f",
                            sig.city, sig.direction, fp, fs, fp * fs)
            else:
                logger.info("[STWA] UNFILLED %s %s status=%s",
                            sig.city, sig.direction, fill.status)

    _BASKET_EXIT_LOG_LAST: dict = {}   # city -> last log ts (throttle)

    def _log_basket_exit_shadow(self, out_dir, bucket_map, clob_books,
                                t_close_map, now) -> None:
        """Write-only shadow: per held city basket, mirror-bid cash-out value
        vs cost vs best-possible hold payoff (see 06-12 exit-dominance study).
        bid(YES leg) = 1 − no_ask, bid(NO leg) = 1 − yes_ask; ask in (0,1)
        required, else bid logged as None and excluded from cash_value."""
        op = getattr(self.bot.risk, "open_positions", {})
        if not op:
            return
        for city, bks in bucket_map.items():
            if now - self._BASKET_EXIT_LOG_LAST.get(city, 0.0) < 120.0:
                continue
            legs = []
            for lo, hi, yes_tok, no_tok in bks:
                for tok, side, opp in ((yes_tok, "YES", no_tok),
                                       (no_tok, "NO", yes_tok)):
                    pos = op.get(tok)
                    if pos is None or tok is None:
                        continue
                    sh = getattr(pos, "remaining_shares", 0.0) or 0.0
                    if sh <= 0:
                        continue
                    ask_opp = (clob_books.get(opp) or {}).get("best_ask")
                    bid = round(1.0 - ask_opp, 4) if ask_opp and 0 < ask_opp < 1 else None
                    legs.append({
                        "token": tok, "side": side, "lo": lo, "hi": hi,
                        "sh": round(sh, 4), "entry": pos.entry_price,
                        "bid": bid,
                        "depth_usd": (clob_books.get(opp) or {}).get("usd_depth"),
                        "cls": getattr(pos, "bond_entry_class", ""),
                    })
            if not legs:
                continue
            self._BASKET_EXIT_LOG_LAST[city] = now
            cost = sum(l["sh"] * l["entry"] for l in legs)
            cash = sum(l["sh"] * l["bid"] for l in legs if l["bid"] is not None)
            # best possible hold payoff over all ladder outcomes
            max_hold = 0.0
            for lo, hi, _, _ in bks:
                pay = sum(l["sh"] * (1.0 if (l["side"] == "YES") ==
                                     (l["lo"] == lo and l["hi"] == hi) else 0.0)
                          for l in legs)
                max_hold = max(max_hold, pay)
            all_green = all(l["bid"] is not None and l["bid"] > l["entry"]
                            for l in legs)
            with open(out_dir / "basket_exit_shadow.jsonl", "a") as f:
                f.write(json.dumps({
                    "ts": now, "city": city,
                    "t_close": t_close_map.get(city),
                    "n_legs": len(legs), "cost": round(cost, 4),
                    "cash_value": round(cash, 4),
                    "max_hold": round(max_hold, 4),
                    "all_green": all_green, "legs": legs,
                }) + "\n")

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
        """FREE DEPLOYABLE CASH = total equity − cost basis of open positions.

        Sizing must reflect real liquid cash, not total account value. `capital`
        counts held-to-resolution positions at cost basis (cash + positions), so
        sizing off it over-deploys the shrinking free cash as positions accumulate
        (2026-06-03: capital $117.69 = $53 cash + $64.53 in 9 open positions →
        every Kelly sizer ran ~2.1× hot). Subtract the still-open cost basis
        (remaining_shares × entry_price; fallback to recorded stake) so the base is
        what can actually be deployed; it self-corrects toward `capital` as
        positions resolve and cash returns. The risk-of-ruin floor still checks
        total equity (bankroll.capital) directly — unchanged.

        2026-06-04 (user): prefer the LIVE CLOB USDC balance (cached ~45s) so the
        bot sizes/fires off real available cash even when the user sells positions
        manually between reconciles — those proceeds are invisible to capital−held
        until the next 5-min reconcile. fetch_usdc_balance() returns free cash only,
        which is exactly this quantity. Falls back to capital−held on fetch failure."""
        _live = self._free_usdc_cached()
        if _live is not None:
            return _live
        try:
            cap = float(self.bot.risk.bankroll.capital)
            held = 0.0
            for pos in self.bot.risk.open_positions.values():
                sh = float(getattr(pos, "remaining_shares", 0.0) or 0.0)
                ep = float(getattr(pos, "entry_price", 0.0) or 0.0)
                held += (sh * ep) if (sh > 0 and ep > 0) else float(getattr(pos, "stake", 0.0) or 0.0)
            return max(0.0, cap - held)
        except Exception:
            return 30.0  # conservative fallback

    def _free_usdc_cached(self, ttl: float = 45.0) -> Optional[float]:
        """Live free USDC from the CLOB (GET /balance-allowance), cached `ttl`s so
        the weather loop blocks on the HTTP call at most once per window. Returns
        None in dry-run or on a fetch failure with no prior cache — caller then
        falls back to the capital−held estimate. A stale cached value beats None."""
        try:
            from config import CONFIG as _CFG
            if _CFG.dry_run:
                return None
        except Exception:
            pass
        now = time.time()
        ts = getattr(self, "_usdc_cache_ts", 0.0)
        cached = getattr(self, "_usdc_cache_val", None)
        if cached is not None and (now - ts) < ttl:
            return cached
        try:
            bal = self.bot.orders.fetch_usdc_balance()
        except Exception:
            bal = None
        if bal is None:
            return cached  # keep the last good value if the fetch hiccups
        self._usdc_cache_val = float(bal)
        self._usdc_cache_ts = now
        return self._usdc_cache_val

    async def _no_arb_shadow_probe(self, bucket_map: dict, clob_books: dict, now: float) -> None:
        """SHADOW (no capital, no signals): fetch REAL CLOB books for the top
        NO-arb-eligible cities and log real Σno_ask + per-leg fillable depth.

        Rationale: Face 2's eligibility (Σno_proxy<N−1 ⟺ Σyes_proxy>1) is the
        mathematical opposite of the real-book depth-fetch screen (Σyes_proxy<0.95),
        so the NO-arb has only ever seen Gamma-proxy prices (no_ask=1−yes_gamma,
        depth 0) where "arb" is just the overround. This measures the REAL book so
        we can decide whether a fillable arb exists before risking capital.
        Throttled (≤1/interval) + city-capped to bound HTTP cost.
        """
        if not NO_ARB_PROBE_ENABLED:
            return
        if now - getattr(self, "_no_arb_probe_last_ts", 0.0) < NO_ARB_PROBE_INTERVAL_S:
            return
        # Rank eligible cities by proxy NO-arb edge (most negative Σno−(N−1) first).
        cand = []
        for slug, bks in bucket_map.items():
            legs = [(lo, hi, yt, nt) for (lo, hi, yt, nt) in bks if nt]
            N = len(legs)
            if N < 2:
                continue
            sum_no_proxy = sum((clob_books.get(nt) or {}).get("best_ask", 1.0) for *_, nt in legs)
            if sum_no_proxy < N - 1:                       # NO-arb eligible on proxy
                cand.append((sum_no_proxy - (N - 1), slug, legs, N, sum_no_proxy))
        if not cand:
            return
        cand.sort(key=lambda x: x[0])
        cand = cand[:NO_ARB_PROBE_MAX_CITIES]
        self._no_arb_probe_last_ts = now

        from datetime import datetime, timezone
        import asyncio as _aio
        today = datetime.now(timezone.utc).date().isoformat()
        out_dir = Path(__file__).parent.parent / "logs" / "shadow" / "hot" / today
        out_dir.mkdir(parents=True, exist_ok=True)

        for _edge, slug, legs, N, sum_no_proxy in cand:
            no_toks = [nt for *_, nt in legs]
            books = await _aio.gather(
                *[self._fetch_book_levels(t, n=5) for t in no_toks],
                return_exceptions=True,
            )
            per_leg = []
            real_sum_no = 0.0
            n_fillable = 0
            min_depth = None
            ok_all = True
            for (lo, hi, yt, nt), b in zip(legs, books):
                if isinstance(b, Exception) or not isinstance(b, dict):
                    ok_all = False
                    real_sum_no += (clob_books.get(nt) or {}).get("best_ask", 1.0)  # fall back to proxy
                    per_leg.append({"hi": hi, "no_ask": None, "depth": 0.0, "src": "err"})
                    continue
                asks = b.get("asks") or []
                if not asks:
                    ok_all = False
                    real_sum_no += (clob_books.get(nt) or {}).get("best_ask", 1.0)
                    per_leg.append({"hi": hi, "no_ask": None, "depth": 0.0, "src": "no_asks"})
                    continue
                ba = float(asks[0]["price"])
                depth = round(sum(float(a["usd"]) for a in asks), 2)
                real_sum_no += ba
                min_depth = depth if min_depth is None else min(min_depth, depth)
                if (0 < ba < 1) and depth >= NO_ARB_PROBE_MIN_LEG_DEPTH_USD:
                    n_fillable += 1
                else:
                    ok_all = False
                per_leg.append({"hi": hi, "no_ask": ba, "depth": depth, "src": "real"})
            payoff = float(N - 1)
            real_edge = round((payoff - real_sum_no) / real_sum_no, 4) if real_sum_no > 0 else None
            real_arb = ok_all and (real_sum_no < payoff)
            rec = {
                "ts": round(now), "city": slug, "N": N,
                "proxy_sum_no": round(sum_no_proxy, 4),
                "real_sum_no": round(real_sum_no, 4),
                "payoff_N_1": payoff, "real_edge": real_edge,
                "n_legs_fillable": n_fillable, "all_legs_fillable": ok_all,
                "min_leg_depth_usd": min_depth, "real_arb": real_arb,
                "legs": per_leg,
            }
            try:
                with (out_dir / "no_arb_probe.jsonl").open("a") as f:
                    f.write(json.dumps(rec) + "\n")
            except Exception:
                logger.debug("[NO-ARB-PROBE] log write fail", exc_info=True)
            logger.info("[NO-ARB-PROBE] %s N=%d proxyΣno=%.2f realΣno=%.2f payoff=%.0f edge=%s fillable=%d/%d all=%s ARB=%s",
                        slug, N, sum_no_proxy, real_sum_no, payoff,
                        f"{real_edge:.3f}" if real_edge is not None else "?",
                        n_fillable, N, ok_all, real_arb)

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

    async def _log_weather_actuals(self) -> None:
        """Revive the self-learning loop: emit ONE provenance-clean `actual` per
        (city, valid_day) once the day's diurnal peak is definitively past
        (local hour ≥ ACTUALS_MIN_LOCAL_HOUR). The producer that fed
        forecast_actuals.jsonl died in the 2026-05-31 resolution overhaul, freezing
        the skill matrix. This re-wires it.

        Source of truth = official_running_max_c (AWC/NWS hourly METAR only) — the
        SAME oracle Polymarket resolves against. Never the sub-hourly running_max_c
        (the M1β/P3 false-lockout lesson). Idempotent via self._actuals_logged.
        """
        from datetime import datetime, timezone, timedelta as _td
        try:
            from analysis.weather.live_accumulator import log_actual
        except Exception:
            return
        now_utc = datetime.now(timezone.utc)
        for icao, cached in list(self._icao_metar_cache.items()):
            slug = ICAO_TO_SLUG.get(icao)
            if not slug:
                continue
            official = cached.get("official_running_max_c")
            valid_day = cached.get("running_max_date")
            if official is None or not valid_day:
                continue
            key = (slug, valid_day)
            if key in self._actuals_logged:
                continue
            tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
            local_hour = (now_utc + _td(hours=tz_h)).hour
            if local_hour < ACTUALS_MIN_LOCAL_HOUR:
                continue  # not yet definitively post-peak — the max may still rise
            self._actuals_logged.add(key)
            try:
                log_actual(slug, slug, valid_day, float(official))
            except Exception:
                logger.exception("[WA] log_actual emit failed %s %s", slug, valid_day)

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

        Clamped to [KELLY_MIN_USD, KELLY_MAX_USD] and bankroll safety cap (25%).
        Falls back to STAKE_USD if Kelly is disabled or ask >= 1.0.
        """
        bankroll = self._get_bankroll()
        if not KELLY_ENABLED or ask >= 1.0:
            return min(STAKE_USD, bankroll * 0.25)
        fee_adj_edge = edge - ask * TAKER_FEE_RATE
        p_eff = ask * (1.0 + TAKER_FEE_RATE)
        f_star = fee_adj_edge / max(0.001, 1.0 - p_eff)
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

    async def _get_hourly_forecast(self, lat: float, lon: float) -> tuple[dict[int, float], dict[int, float]]:
        """Fetch today's hourly 2m-temp + 2m-dewpoint forecast in UTC (°C).
        Returns (temps, dews). Cached per station per 6h slot.
        The dew forecast feeds the engine humidity correction (A1 fix): alpha was
        fit on (obs_dew − NWP_dew), so the engine must read NWP dew, not air temp."""
        import time
        from datetime import date, datetime, timezone
        today = date.today().isoformat()
        refresh_slot = int(time.time()) // (6 * 3600)
        key = (round(lat, 2), round(lon, 2), today, refresh_slot)
        if key in self._hourly_cache:
            return self._hourly_cache[key]

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            f"&hourly=temperature_2m,dew_point_2m&temperature_unit=celsius"
            f"&forecast_days=1&timezone=UTC"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return {}, {}
                    data = await resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            dews  = hourly.get("dew_point_2m", [])
            result = {
                datetime.fromisoformat(t).hour: float(v)
                for t, v in zip(times, temps)
                if v is not None
            }
            dew_result = {
                datetime.fromisoformat(t).hour: float(v)
                for t, v in zip(times, dews)
                if v is not None
            }
            self._hourly_cache[key] = (result, dew_result)
            return result, dew_result
        except Exception as e:
            logger.debug("[WA] hourly forecast error lat=%.2f: %s", lat, e)
            return {}, {}

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
            hourly, _ = await self._get_hourly_forecast(lat, lon)
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
                _slug = CITY_NAME_TO_SLUG.get(city, city)  # accept display-name or slug directly

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

                # ── METAR trajectory blend (same-day only) ──────────────
                # Anchor the NWP ensemble with a rise-table trajectory from
                # the current observed temperature. Weight grows closer to
                # peak so live obs dominate in the final hours.
                if d == today and icao:
                    _m = self._latest_metar.get(icao, {})
                    _t_cur   = _m.get("temp_c")
                    _sf      = _m.get("sky_factor")
                    _run_max = _m.get("running_max_c")
                    _utc_h   = _m.get("utc_hour")
                    _rt = CITY_REMAINING_RISE.get(_slug, {}).get(_month, {})
                    if _t_cur is not None and _sf is not None and _utc_h is not None and _rt:
                        _remaining = _rt.get(_utc_h) or _rt.get(
                            min(_rt, key=lambda k: abs(k - _utc_h)), 0.0)
                        _t_traj = _t_cur + _remaining * _sf
                        if _run_max is not None:
                            _t_traj = max(_t_traj, _run_max)
                        _peak_h = CITY_PEAK_HOUR_UTC.get(_slug, {}).get(_month, _utc_h + 8)
                        _htp = max(0, _peak_h - _utc_h)
                        _w_m = 0.70 if _htp < 2 else 0.55 if _htp < 4 else 0.35 if _htp < 8 else 0.20
                        _mean_nwp = mean
                        mean = round(_w_m * _t_traj + (1.0 - _w_m) * _mean_nwp, 2)
                        logger.debug(
                            "[WA] METAR_BLEND %s %s: t_cur=%.1f sf=%.2f rise=%.2f "
                            "traj=%.2f nwp=%.2f htp=%d w_m=%.2f → blend=%.2f",
                            city, d, _t_cur, _sf, _remaining, _t_traj,
                            _mean_nwp, _htp, _w_m, mean,
                        )

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
