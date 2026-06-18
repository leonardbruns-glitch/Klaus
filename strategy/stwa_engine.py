"""
STWA Engine — Spatiotemporal Weather Arbitrage.

Architecture:
  1. Spatiotemporal Kalman filter: 49-city joint state, empirical spatial covariance.
     Every METAR observation updates all city posteriors simultaneously via
     the spatial correlation structure (Kriging propagation).

  2. Running-maximum Monte Carlo: per city, simulate N=8000 OU paths forward
     with time-varying κ(t)/σ(t), compute P(daily_max ∈ bucket) analytically.

  3. Neg-risk LP: allocate capital across all open buckets per city to maximise
     expected edge; ensures probabilities sum to 1 (internal consistency gate).

  4. Regime gate: only fires in SUNNY / PARTLY_CLOUDY; RAIN/STORM/FOG suspended.

  5. Live calibration: ECE per city computed daily; city suspended if ECE > 0.10.

Usage (within weather_arb.py):
    engine = STWAEngine(params_path="config/stwa_params.json")
    # On each METAR callback:
    engine.on_metar(city, temp_c, dew_c, sky_rank, obs_ts, running_max_c)
    # Periodically (every 30s):
    signals = engine.get_signals(clob_books)
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
N_PATHS        = 8_000   # Monte Carlo paths per city
MC_STEP_S      = 300     # 5-minute simulation time step (seconds)
INNOV_DF       = 6       # Student-t df for path innovations (excess kurt = 3)
                         # Empirical residual kurt ~+1.7 → df=6 matches better
                         # than Gaussian. Set to >100 to recover Gaussian.
# Regular-YES kill switch. SUSPENDED 2026-05-29: calibration audit (n=349
# resolved) showed regular-YES is 4.3× overconfident (predicted 0.326 vs actual
# WR 0.075), rank-corr to outcomes −0.19 (anti-predictive), and loses to the
# market on log-loss. Two structural defects compound it: (1) no cross-cycle
# portfolio state → mutually-exclusive YES buckets accumulate across the day as
# the forecast drifts (Helsinki: bought 15-17°C AM, 20-21°C PM); (2) miscalibrated
# inputs. When False, _lp_allocate_city emits NO and NEG_RISK_ARB signals only.
# Re-enable once p_model is recalibrated AND per-city-day portfolio sizing exists.
STWA_REGULAR_YES_ENABLED = False  # 2026-06-05: OFF — the full-market calibration curve (n=1771) shows YES
                                  # is −EV in EVERY ask bin (realized far below ask; e.g. ask 0.44→won 18%).
                                  # YES-overpricing is the OTHER half of the favorite-longshot bias; only the
                                  # NO side is +EV. Was: RE-ENABLED 2026-06-01 (user directive): the directional YES ladder
                                  # is now guarded by the WIDTH GATE (drops the YES horse-race pool unless
                                  # book-implied σ > 1.10×our pricer σ) — the missing safety behind the
                                  # 05-29→05-31 bleed (YES fired in Regime-3 where it just paid vig). YES
                                  # is the ONLY directional bucket-ladder; engine model-NO is disabled
                                  # (STWA_REGULAR_NO_ENABLED) so all NO flows through the validated M1β
                                  # lockout harvest. Bounds: width gate + isotonic g(p) sizing + Tier-4
                                  # city-day budget + kelly_frac 0.20 + stake_max. STILL UNCONFIRMED on
                                  # LIVE 2026 resolution (calibration validated on 2024 history only) —
                                  # monitor. Revert: set False.
# Regular-NO kill switch. DISABLED 2026-06-01: the engine's model-edge NO is
# (1) redundant — on locked buckets the running-max floor drives g(p)→0 so
# edge_no=1−ask_no clears the gate on EXACTLY the buckets the validated M1β
# lockout-NO harvest (weather_arb.py, ~98% WR OOS) already buys → double-fire;
# and (2) the FLB-spread-walled speculative NO on UNLOCKED tail buckets (−EV;
# the regular-NO that bled). All NO now flows through M1β; the engine keeps only
# the directional YES ladder + NEG_RISK_ARB. Revert: set True.
STWA_REGULAR_NO_ENABLED  = False  # DISABLED 2026-06-11 (system audit): 0 fires in 48h while ARMED as a
                                  # TAKER duplicate of the band's maker NO overlay (same 0.52-0.85
                                  # favorite buckets) — when it does race the overlay it pays spread +
                                  # 1.25% taker fee for a bucket the maker quote captures cheaper, and
                                  # its open_positions fill then BLOCKS the maker pair leg. The validated
                                  # +EV slice it targeted is fully covered by BAND_NO_*. Revert: True.
                                  # Resolved-trade evidence (n=147, pre-fix model): BUY_NO is +EV in the
                                  # CONFIDENT region only — [0.5,0.7) 63%/+$2.63, [0.7,0.9) 89%/+$7.25
                                  # (n=37 ≥0.50, +$9.88, EV/sh +0.052, fee-positive, FILLED & resolved) —
                                  # and bleeds in the cheap region — [0,0.3) −$24.81, [0.3,0.5) −$10.69.
                                  # The PRICE_FLOOR (0.50) gate below surgically keeps the +EV slice and
                                  # kills the bleed. M1β is OFF (no double-fire). Revert: set False.
EDGE_MIN       = 0.04    # absolute floor on edge (p_win − ask), risk-of-ruin safety
KELLY_F_MIN    = 0.015   # minimum Kelly fraction to fire: f* = (p_c − ask)/(1 − ask)
                         # 0.015 = 1.5% of bankroll. Scales with both p and ask:
                         # high-ask bets (sells of unlikely YES) clear easily;
                         # low-ask longshot bets need larger edge to clear.
WIDTH_GATE_MARGIN = 1.10 # YES ladder fires only when the book-implied σ exceeds
                         # this × our per-city pricer σ. Edge on a directional
                         # ladder requires s_M > (1+φ)·s_our (our forecast tighter
                         # than the book); otherwise the ladder just pays vig
                         # across legs (Regime-3, no width advantage). 1.10 ≈ a
                         # fixed 10% overround proxy for (1+φ); conservative vs
                         # typical Polymarket overrounds. Gates YES only — arb
                         # spine (returns earlier) and NO pool are unaffected.

# ── Per-city Kelly confidence weighting (2026-06-04) ──────────────────────────
# The horse-race Kelly already sizes on edge, but the win-prob it uses is a POOLED
# isotonic calibration — it does NOT know that a tight-σ city's confident bucket
# genuinely wins more often. Scale the YES stake by per-(city,month) forecast σ
# (peak_calib `sigma_monthly`, = `s_our`, clean 4yr ASOS): theoretical mode-bucket
# WR ≈ 55% at σ=0.65 vs <30% at σ=1.4, and mode±1 band ≈ 93% at σ=0.80 vs <70%
# above σ=1.4. So size UP where the model is accurate, DOWN where it's loose, and
# fire NO directional YES at all where even the band can't clear vig.
# w_city = clip(YES_SIGMA_REF / s_our, MIN, MAX); s_our > CUTOFF ⇒ drop YES pool.
# Revert: YES_PERCITY_KELLY_ENABLED = False (restores flat kelly_frac sizing).
YES_PERCITY_KELLY_ENABLED = True
YES_SIGMA_REF    = 0.80   # pivot ≈ σ where mode±1 band hits ~93% (london-class)
YES_SIGMA_CUTOFF = 1.40   # above this P(mode±1) < 70% → directional YES is -EV (SF/guangzhou/taipei/chengdu/chongqing)
YES_WCITY_MIN    = 0.40   # floor: loosest still-eligible cities sized to 0.4×
YES_WCITY_MAX    = 1.60   # cap: tightest cities sized to 1.6× (risk-of-ruin guard)

# Global EMOS σ factor — RETIRED to 1.0 (2026-06-03). Calibration is now per-(city,month)
# via peak_calib `sigma_monthly` (built from clean 2021-24 ASOS history; see _peak_sigma_for).
# HISTORY: a ×1.52 was briefly deployed off 11 live days (emos_recal.py), but those used
# metar_lockout running_max_c as the "actual" — sub-hourly/NMS-contaminated → inflated error →
# a FALSE 1.52× "overconfidence". The clean 4yr ASOS history shows raw σ ≈ calibrated for this
# season (z-std 0.92) with a ~2× SEASONAL swing → per-(city,month) σ is the right fix, not a
# global multiplier. Kept as a reversible global knob; the live loop refines per-month cells.
SIGMA_CALIB_INFLATION = 1.0

# Nowcast σ-collapse (2026-06-03). Once the running max M0 nears the forecast peak, the
# remaining-rise uncertainty shrinks: σ_remaining ≈ 0.5×(daily_max − running_max), a ratio
# stable across all leads in 4yr hourly ASOS (analysis/weather/nowcast_sigma.py: σ 1.99°C at
# −4h → 0.52 at −1h → 0 at peak). So tighten the pricing σ toward 0.5×(center − M0) — only ever
# SMALLER than the per-month forecast σ (capped), floored to stay humble, folding smoothly into
# the running-max lockout as M0→center. Sharpens pricing exactly when the day is nearly decided.
# Revert: set NOWCAST_REMAIN_RATIO huge (e.g. 99.0) so the per-month cap always wins.
NOWCAST_REMAIN_RATIO = 0.5
NOWCAST_SIGMA_FLOOR  = 0.25
# DISABLED 2026-06-06 (data): the collapse HURTS calibration on every metric. Backtest
# (analysis/weather/stwa_sigma_collapse_backtest.py, n=53k–76k buckets, 12,821 days):
# deployed collapse Brier 0.181 / ECE 0.106 / rank-ρ 0.339 vs NO-collapse 0.129 / 0.058 /
# 0.393 — lower error, HALF the ECE, BETTER discrimination, and 5× fewer false-certain
# (p≥.9) buckets (4,130→861, which only won 39%). (center−M0) is not remaining-max
# uncertainty: it shrinks σ hardest just before the peak, where the residual rise has the
# most leverage on which bucket wins → confident single-bucket picks that miss. Lockout
# certainty is preserved separately by the running-max floor (bhi≥M0). Setting this False
# ALSO re-aligns with the isotonic map (fit on flat-σ 2024). Revert: set True.
NOWCAST_SIGMA_COLLAPSE = False

# ── MAKER SHADOW (log-only; 2026-06-01) ────────────────────────────────────────
# Live weather books are thin/one-sided with fat spreads ($2M vol across cities,
# but contested buckets show ~$350 standing liquidity at a 2.6–5¢ spread vs ~$29k
# volume) → the scalable edge is PROVIDING liquidity, not taking. This recorder
# logs, per bucket, our calibrated fair vs the live book + the two-sided quote we
# WOULD post, so maker EV = fill×(resolution − quote) can be measured offline
# BEFORE any real order. Zero capital. Prereq for the locked-bucket (adverse-
# selection-free) live maker. Disable: MAKER_SHADOW_ENABLED=False.
MAKER_SHADOW_ENABLED = True
# FADE SHADOW (forward, no-look-ahead test of the resolution hourly-sampling edge,
# 2026-06-02). Resolution = max of routine HOURLY METARs ≈ ~0.8°F below the true
# diurnal peak; the bin just ABOVE running_max is where the sub-hourly peak pokes in
# and the book overprices it (backtest n=244: that bin wins ~1% yet is priced ~22¢).
# Post-peak, log the live NO ask on the bins above running_max → join resolution
# offline → forward fade WR/EV with ZERO look-ahead. Log-only, no capital.
FADE_SHADOW_ENABLED = False  # moved to weather_arb (gate-independent + real-book enriched)
MAKER_HALF_SPREAD    = 0.02   # half-spread around calibrated fair for the shadow quote
CONFIDENCE_MIN = 0.45    # minimum confidence score

# ── 2D Langevin velocity state ─────────────────────────────────────────────────
# Temperature residual X follows dX=V dt, dV=(−γV−κX)dt+σdW (damped harmonic OU).
# γ damps the velocity; scipy.linalg.expm handles over/under/critically-damped.
VELOCITY_GAMMA  = 1.5    # velocity damping coefficient (1/h)
VEL_OBS_N       = 6      # OLS buffer depth (observations)
VEL_PRIOR_VAR   = 4.0    # prior velocity variance ((°C/h)²) = (2 °C/h)²
VEL_MIN_VAR     = 0.25   # posterior floor to prevent degeneracy ((°C/h)²)
VEL_MIN_OBS_VAR = 0.50   # observation variance floor for numerical stability
METAR_MAX_AGE  = 3600    # seconds — METAR stations report hourly; allow up to 60 min
MIN_TIME_REM   = 1800    # don't fire within 30 min of market close
HOUR_BINS      = [(0, 6), (6, 12), (12, 18), (18, 24)]

# ── Drift baseline (climate / NWP-version drift correction) ───────────────────
# Static bias was fit on 2021-2024 data. Climate trends + Open-Meteo NWP model
# version updates introduce drift in 2025+. We maintain an exponentially-
# decaying live residual baseline per (city, hour) to absorb persistent bias.
DRIFT_TAU_DAYS  = 30.0   # decay time-constant for drift baseline
DRIFT_BIAS_LIMIT = 3.0   # max |drift| (°C) — guards against transient spikes

# ── LP portfolio allocation ────────────────────────────────────────────────────
CITY_BUDGET_FRAC  = 1.0    # per-city fraction-of-bankroll throttle REMOVED 2026-06-03 (user directive: 5% cap starved a $53 account below the $3 min-stake). Per-city budget now bounded only by CITY_BUDGET_MAX + free cash.
CITY_BUDGET_MAX   = 15.0   # hard cap per city (USD)
NEG_RISK_ARB_THR  = 0.85   # Σ YES ask < this → pure neg-risk arb available
                           # 0.85 leaves ~10pp for Polymarket fees (2% × 2 legs) + slippage
NEG_RISK_ARB_THR_MULTILEG = 0.80   # ≥4 legs: wider Σask margin. Each extra leg
                           # adds partial-fill risk — if one leg's ask drifts past
                           # the ±0.15 fill gate after others fill, the book is left
                           # unhedged and the guaranteed-payoff structure breaks.
NEG_RISK_ARB_MULTILEG_N   = 4      # leg count at/above which the tighter THR applies
NEG_RISK_ARB_MIN  = 0.50   # minimum per-bucket stake for arb (below regular stake_min)
NEG_RISK_ARB_EXHAUSTIVITY = 0.95   # require Σ p_model > this to fire arb (proves bucket coverage)
NEG_RISK_ARB_BUDGET_MUL   = 1.5    # abort arb if min-feasible cost > this × city_budget
PROB_SUM_MAX      = 1.35   # Σ p_model > this → MC bug, skip city

# Primary daily-max pricer that drives the allocator. "MC" = legacy 8000-path
# Langevin (over-weights intraday → mis-located/overconfident, n=349 audit).
# "PA_SHRUNK" = peak-anchored Gaussian center=NWP_peak+peak_bias+β·x_hat, β=0.30,
# σ per-city — validated calibrated on 2024 ASOS vs ECMWF (n=12,835 city-days:
# daily-max-error std 1.04°C, coverage 80%/97% within ±1σ/±2σ; intraday optimal
# weight β≈0.3 vs the live pipeline's effective β≥1). MC/GEV/PA still logged in
# shadow for ongoing live-resolution comparison. Calib: config/stwa_peak_calib.json.
STWA_PRIMARY_PRICER = "PA_SHRUNK"   # "MC" | "PA_SHRUNK"
PA_SHRUNK_BETA      = 0.30          # intraday-residual shrinkage (data-fit ~0.3)

# ── BAND MODE (new directional-YES strategy, 2026-06-05) — DEFAULT OFF ─────────
# When True, the pricer uses the empirically-derived time-varying anomaly gain β_h
# (morning obs is noise → β=0 pre-11am; rises to 0.41 at peak) and the data-correct
# σ-floor (σ_h = σ_fc·√(1−R²_h), floored at BAND_SIGMA_FLOOR) INSTEAD of the fixed
# β=0.30 + nowcast σ-collapse (which forward_calibration showed = 2.32× overconfidence,
# [0.9,1.0] bin claims .98 wins .23). Flag-gated: STWA_BAND_MODE=False ⇒ byte-identical
# to the legacy pricer. Allocator-side (band selection + Matrix-Kelly + arb/NO-off) is a
# SEPARATE, not-yet-built step — this flag alone only fixes the PRICER. Validate in shadow
# before any live use. Derivation: analysis/weather/{dist_kalman_ev,multibucket_proof}.py.
STWA_BAND_MODE      = False         # 2026-06-05 user: OFF — superseded by the favorite-longshot
                                    #   directional ladder (regular YES/NO + PRICE_FLOOR) as the ONLY strat.
BAND_SHADOW         = True          # (inert while STWA_BAND_MODE=False)
# ── FAVORITE-LONGSHOT GO-LIVE (2026-06-05, user: "the only strat") ──
# The single edge the resolved data supports: take the favorite side at a fillable
# price, NEVER the cheap longshot. PRICE_FLOOR kills every fire below 0.50 — the
# fee-death/longshot zone where ALL −$85 of our directional loss lived.
PRICE_FLOOR         = 0.50          # only buy a token whose ask ≥ this (both YES and NO)
# 2026-06-07 (Claude): NO-side ASK BAND. Resolved weather NO split by ask band
# (n=111, all-time): <0.70 → n=65 WR~0.35 −$58.70 (the bleeder); [0.70,0.85] →
# n=18 WR 0.89 +$17.84 (the ONLY +EV slice — matches 06-06 scorecard + flb_calib);
# ≥0.85 engine path overpays (−$10.77) and deep-lockout ≥0.90 is M1β's validated
# job. Gate engine model-NO to [NO_FLOOR, NO_CEIL] instead of the shared 0.50 floor
# (which kept the whole bleeder zone). Revert: NO_FLOOR=PRICE_FLOOR, NO_CEIL=1.0.
NO_FLOOR            = 0.70
NO_CEIL             = 0.88
YES_STAGE_MIN_STAKE = True          # YES-favorite is UNPROVEN on resolved data (n=5) → fire at min-stake
                                    #   only, to collect clean post-fix n. NO-favorite (proven) sizes normally.
STWA_NEG_RISK_ENABLED = False       # 2026-06-05 user "only strat": neg-risk arb OFF — it never executed as
                                    #   intended (partial fills on phantom books → −$43.48 over n=15; 0
                                    #   fillable arbs in 1947 probe rows). Revert: set True.
BAND_SIGMA_FLOOR    = 0.90          # σ never collapses below this (kills σ-collapse)
BAND_EV_MIN         = 0.08          # 2026-06-05 user: LOWERED 0.15->0.08 (fires thin edges — AGAINST my advice, unvalidated; daily halt is the only backstop)
# Guardrails (added 2026-06-05 after the live misfire on stale near-zero asks):
BAND_ASK_MIN        = 0.05          # ignore buckets cheaper than this (stale/illiquid/losing)
BAND_EV_MAX         = 0.60          # EV above this = stale-ask artifact (efficient mkt ⇒ no 100%+ edge)
BAND_P_MIN          = 0.50          # band must actually be likely (mode±1 ⇒ ~0.85; <0.50 = misaligned)
BAND_HOUR_MAX       = 16            # peak window upper bound; after this the day's max is decided

# ── BADATMATH STRUCTURAL BAND (2026-06-09) ────────────────────────────────────
# Reverse-engineered from wallet 0x8fbd7cf5f806f563080864694415829f7229a959
# ("badatmath."), ~$70→$7.8k/mo. EDGE = the market OVER-disperses the daily-high
# (true σ≈1.3° < market-implied). Harvest: buy the contiguous near-MARKET-MODE YES
# buckets priced in [BAND_PX_MIN, BAND_PX_CEIL]; one in-band winner repays the
# sub-$1 band. STRUCTURAL — fires off the MARKET price ladder, NOT our (overconfident)
# model prob. Validated on n=3583 resolved buckets, May AND June independently:
# mkt-price 0.30-0.40 → win 50%, 0.22-0.30 → 33%, 0.15-0.22 → 27%, 0.10-0.15 → 16%
# (every bin wins MORE than its price). Coverage: realized high in-band 73%.
# ISOLATED from STWA_BAND_MODE (which also alters the pricer) — own flag, own path.
# EXECUTION = MAKER (on-chain fact 2026-06-09): badatmath is 97.6% MAKER — 27,929 of
# 28,429 fills are resting limit bids he POSTED and waited on (100% maker below ask
# 0.10). His "fill price" IS a posted-bid price, not an ask. A TAKER copy pays the ask
# and does NOT reproduce the edge (cf. Klaus's 0 fillable taker arbs / -$43). So the
# band quotes MAKER bids at BAND_QUOTE_FRAC of the spread above best-bid (never crosses),
# sized bell-shaped, held to resolution. PX_MIN/CEIL gate which buckets we quote on.
STWA_STRUCT_BAND    = True          # master ENABLE for the structural band path
BAND_LIVE           = True          # 2026-06-10 user: "exploit a recurring edge" — RE-FLIPPED LIVE after
                                    # post-fix shadow verified clean (2,514 rows / 2h, 0 mode-containment
                                    # violations, md_shadow firing d+1 candidates). Live = d+1/d+2 maker
                                    # band only (BAND_MD_LIVE_MIN_DOUT=1, BAND_SAMEDAY_LIVE=False).
                                    # [prior 2026-06-10 SHADOW note: BACK TO SHADOW "until u solve all this bugs" —
                                    # first live hours surfaced 4 defects (instant-FILLED untracked,
                                    # restart amnesia/duplicates, converged-ladder flank-only bands,
                                    # same-day path accidentally armed). All four are FIXED, but the
                                    # flip back to live is the user's call after clean shadow cycles.
                                    # [prior 2026-06-09 LIVE note: (user: "exploit those structural inefficiencies now"
                                    # after the full teardown re-audit). Live slice = d+1/d+2 ONLY (his
                                    # resolved ROI by days-out: +6.3/+14.4/+22.8%), maker-only, breaker-
                                    # gated, BAND_MD_DAILY_BUDGET-capped. Evidence: his n=8,043 resolved
                                    # tokens ground truth; worst-case bound = Σask<0.70 vs mode±band hit
                                    # ~0.84 ⇒ +EV even at ask-1¢ fills. Revert: False
BAND_PX_CEIL        = 0.45          # never quote a YES leg whose ask is above this (badatmath p99=0.44; >0.50 = -EV)
BAND_PX_MIN         = 0.10          # d+0 floor. 2026-06-09: 0.06→0.10 — FULL-HIST resolved curve: [0,0.05)
                                    # −11.9%, [0.05,0.10) −5.9%, [0.10,0.22) +29.2%, [0.22,0.45) +19.0%.
                                    # d+0 cheap stays dead post-inflection too: 0.05-0.10@d0 −7.4% (n=1364).
BAND_PX_MIN_MD      = 0.03          # 2026-06-11 (user challenged the 0.10 floor — user right): the 0.10
                                    # floor was calibrated on the WING-polluted full-history curve BEFORE
                                    # the off≤1 rule existed. Inside off≤1 at d+1/d+2 (the basket live
                                    # actually posts), his cheap legs are the deepest-return trades in the
                                    # book: px<0.10 @ d1/d2 = +120.1% (n=1592), still +44.9% (n=652) with
                                    # the W23 explosion week EXCLUDED; positive 4 of 6 weeks (neg weeks =
                                    # $137/$72 micro-samples). By price@d1: [0.05,0.10) +68.9% (n=776),
                                    # <0.05 +337.9% (n=524). Mechanism = buying tomorrow's shoulders before
                                    # the market prices them (revision mean-reversion + tail convexity).
                                    # 0.03 floor avoids 0.01-0.02 dust where one tick = 50% of price.
BAND_WING           = 2            # band = market-mode ± this (≤5 legs, his median width 5°)
BAND_SUM_MAX        = 0.85          # fire only if Σ ask of the POSTED legs (|off| ≤ BAND_YES_MAX_OFF) < this.
                                    # 2026-06-11 BASKET-MISMATCH FIX: the old 0.70 gate summed the full ±2
                                    # band (5 legs) while v2 only POSTS off≤1 (3 legs) — gating a basket we
                                    # don't buy killed 63/112 ladders/cycle (YES surface = 2.7% of his
                                    # universe). His off≤1 3-leg basket ROI by Σ(fill px), post-05-04:
                                    # <0.50 +57.4% (n=214) / 0.50-0.70 +39.0% (n=111) / 0.70-0.85 +13.0%
                                    # (n=46 TREND) / ≥0.85 −27.9%. Monotone, positive through 0.85; we gate
                                    # on ASKS (≥ fill px) so 0.85 is conservative-equivalent. The 0.70-0.85
                                    # slice accumulates in the validator (sum3 logged). Was 0.70 (full band).
BAND_MIN_LEGS       = 2             # a band needs ≥ this many in-price legs
BAND_BASE_STAKE     = 1.0           # 2026-06-15: 3→1 to the CLOB MINIMUM. His YES fills are $0.95-1.26
                                    # = AT the exchange floor (5 sh / $1); the $3 base posted 3× his
                                    # size = 1/3 the breadth from the same cash, and blocked posting
                                    # whenever yes_cap < $3 (the posted=0 freeze). Per-leg floor is
                                    # max($1, 5×quote) — applied in weather_arb band loop. Deployment
                                    # scales by BREADTH not stake size (his "bucket-$ flat, deploy 5×").
                                    # Was 8.0 → 3.0 (06-09).
BAND_BELL           = (1.0, 0.7, 0.4)  # stake weight by |offset from mode|: 0,1,2 (bell-shaped $, his shape)
BAND_QUOTE_FRAC     = 0.34          # GAMMA-PROXY FALLBACK ONLY (no real book): bid = proxy_bid + FRAC*spread.
BAND_REALBOOK_YES   = True          # 2026-06-11 (quote-watcher n=741 fill-joins, gate n≥100 PASSED): his
                                    # median fill is AT the touch (fill_vs_best_bid = 0.000; deep-bid theory
                                    # dead). YES legs now fetch the REAL CLOB book (the NO overlay always
                                    # did) and JOIN the best bid — never improve. The old gamma-proxy
                                    # bid (ask−0.02 + 0.34·spread) donated ~1¢/sh ≈ 40% of the 2.6¢ gross
                                    # edge and occasionally CROSSED stale proxies (accidental taker fills).
# ── 2026-06-11 re-audit (his own post-05-04 fills, all slices n≥100 unless noted;
# state_log 11:55): he is a TWO-SIDED PAIR-QUOTER — YES+NO bids on the SAME bucket
# (34-41% of buckets), pair Σ~0.79-0.87, both fill → MERGE → $1. Posting rules below
# encode his measured curve MINUS his measured bleeds:
#   YES by |off|: 0 +26.8% (n=1146) / 1 +43.8% (n=1125) / 2 −8.5% (n=646) /
#                 3 −72% (n=325) / 4 −56.5% (n=249)  ⇒ YES only |off|≤1
#   NO  by |off|: 0 +23.2% (pair leg) / 1 −6.7% (n=1214) / ≥2 +13..+35%  ⇒ skip off1
#   YES by dout:  d0 −3.4% (n=1531) / d1 +15.2% / d2 +56.5%  ⇒ d0 YES = pair leg only
#   NO  by dout:  d1 +12.4% (n=996) > d2 +5.9% > d0 +1.5%    ⇒ extend overlay to d≤2
BAND_YES_MAX_OFF    = 1             # YES legs only |off| ≤ this (wings flip to NO, they don't disappear)
BAND_YES_MAX_OFF_D0 = 0             # d+0: YES only on the mode (the pair leg; standalone d0 YES is his bleed)
BAND_PAIR_SUM_MAX   = 0.92          # same-bucket YES bid + NO bid hard cap ⇒ ≥$0.08/sh locked on a
                                    # completed pair (merge or settlement); his median pair 0.788-0.873
# Multi-day shadow (2026-06-09 rebuild): badatmath quotes the ROLLING horizon d/d+1/d+2
# as a maker — the single-day engine path only ever sees today's (collapsed) market.
BAND_MD_HORIZON     = 2             # quote d, d+1, d+2 (days past local today)
BAND_MD_TTL         = 300           # multi-day shadow rescan cadence (s); own Gamma fetch
BAND_SAMEDAY_LIVE     = False       # 2026-06-09: BAND_LIVE accidentally armed the same-day engine band
                                    # (11-16 local window) — d+0 is his weakest slice (+6.3%) and excluded
                                    # by design; keep the same-day path SHADOW until validator says otherwise.
BAND_MD_LIVE_MIN_DOUT = 0           # 2026-06-10 user ("mirror badatmath fully"): d+0 LIVE — his d+0 is
                                    # +6.3% ROI and carries most of the fill volume (our 3 fills/220
                                    # posts = d+1/d+2-only starvation). The converged-evening-d+0 risk
                                    # that motivated the old =1 is now caught by the mode-containment
                                    # gate (reason=converged). Was 1 (2026-06-10 00:05).
                                    # ROI +6.3% vs d+1 +14.4% / d+2 +22.8%, and our late-d+0 "bands"
                                    # are collapsed ladders — favorite above PX_CEIL ⇒ residual losers)
BAND_MD_DAILY_BUDGET  = 9999.0      # 2026-06-09 user: "we should not constraint it, let it fire" —
                                    # daily posted-budget effectively OFF; bankroll + breaker are the
                                    # only limits. Was 40.0 (first-hour training wheels).

# ── FAVORITE-NO overlay (2026-06-10; REWORKED 2026-06-11 per re-audit) ───────
# His NO leg is HALF the book (~$18/event, equal to YES) and the other half of
# the pair-quoting structure. Curve (post-05-04, n≥100): 0.50-0.65 +8.6%
# (n=1009), 0.65-0.85 +11.2% (n=1165), >0.85 +5.3%; trough 0.35-0.50 −7.8%.
# Offset rule: NEVER the ±1 shoulders (−6.7%, n=1214 — that's the underpriced-
# YES slice, so its NO is overpriced); mode NO = pair leg, |off|≥2 = wing NO.
# days_out: extended d+0-only → d+0..2 (his best NO slice is d+1 +12.4%).
BAND_NO_ENABLED   = True
BAND_NO_MIN       = 0.52    # real CLOB NO ask floor (skip his −EV 0.40-0.50 trough)
BAND_NO_MAX       = 0.85    # above this the NO is last-cent territory, not band
BAND_NO_STAKE     = 4.5     # 2026-06-11: 2.6→4.5 — his NO fill median $5.16 (4× his YES fill);
                            # also keeps ≥5 shares (CLOB resting min) up to px 0.90. Was 2.6
BAND_NO_DAILY_CAP = 40.0    # 2026-06-11: 12→40 — his NO = HALF the book at equal per-event
                            # budget; the cash gate is the real constraint. Was 12.0
BAND_NO_MAX_DOUT  = 2       # 2026-06-11: overlay quotes d+0..this (was d+0 only = his WORST slice)
BAND_NO_SKIP_OFF1 = True    # 2026-06-11: never NO on the ±1 shoulders (his −6.7%, n=1214)
BAND_NO_CASH_RESERVE = 0.0   # 2026-06-18: 0.25->0.0 — LIVE-MEASURED [STRUCT-BAND-Q] yes_resv_skip=78-82/cycle:
                             # the reserve cap was the BINDING throttle, rejecting ~80 +EV YES legs/cycle (the
                             # legs that FEED same-bucket pairs→merge→same-day recycle; merges=0 today, the freeze
                             # loop). Proportional cell weights already split the book (NO≈.46); the reserve was a
                             # redundant 2nd YES throttle fighting the proportional design. Decision-grade
                             # band_resolution_join (n=3,418) favors YES +7.6%. Was 0.25 (2026-06-16, see below):
                             # The 06-15 unreserve ("YES +8.6% vs NO -1.2%") read band_resolution_join's
                             # CONDITIONAL-ON-FILL selection ROI — NOT realized cash. Recent realized
                             # (recycle-attributed, 06-09->16): NO +$39 vs YES -$20 (regime inversion +
                             # adverse fill). NO also resolves d+1 (fast recycle) and is realized-positive,
                             # so a MODEST reserve keeps the fast/diversifying NO leg planted without
                             # over-rotating to a +3.3%-selection leg. Not 0.40 (that abandons YES, which
                             # the n=2740 selection data still favors). Revisit once realized-fill ROI by
                             # side is measurable at n>=100. Revert: 0.0 (YES-only) / 0.50 (his half-NO book).
# ── PROPORTIONAL POSTING (2026-06-17) — copy badatmath's "post BOTH books across all
# 3 horizons, let fills decide the mix" instead of strict-rank "drain rank-1 first"
# (which structurally starved NO ranks 3,4,6 and d+2 — measured 13% NO vs his ~50%).
# He has NO fixed YES/NO ranking: he blankets the surface (his deploy ≈ d0/d1/d2 40/40/20,
# YES/NO ≈ 50/50) and the realized split emerges from which side the market hits. We can't
# post his whole surface at our cash, so we allocate the cycle's headroom across 6 cells
# (YES/NO × d0/d1/d2) + PAIR by SOFT weights (sum>1 so empty cells spill; the global cash
# gate is the hard cap). Weights lean to ROI/cap-day (his d+1 YES +18.7%, d+0 YES +12.2%,
# d+2 YES +19.2%/2d; NO d+1 +6.1%, d+2 +6.7%, d+0 +0.3% breakeven) but every cell gets a
# guaranteed floor ⇒ NO/d+2 no longer starve. ⚠ ON-RECORD: proportional blanketing spreads
# our scarce cash thinner than the velocity-rank ⇒ may LOWER turns/day while cash-bound;
# user directive (copy his composition). Revert: BAND_PROPORTIONAL_QUEUE=False (→ strict rank).
BAND_PROPORTIONAL_QUEUE = True
BAND_CELL_WEIGHTS = {        # cell -> fraction of cycle headroom (soft cap; sum>1 = spill room)
    ("PAIR", 0): 0.20,
    ("YES", 0): 0.24, ("YES", 2): 0.22, ("YES", 1): 0.12,  # 2026-06-18: per-CAPITAL-DAY re-weight.
    # D6 days-out ROI (decision-grade, verifier-confirmed): d+0 YES +19.8% resolves SAME-DAY (fastest
    # recycle ⇒ velocity, the binding gap) > d+2 +30.4% (highest edge, his most under-funded leg) >>
    # d+1 +7.2% (weakest edge AND a 1-day cash lock). Old weights over-funded d+1 (the worst per-cap-day
    # leg). Spill (cell sum>1) covers d+0 mode-only scarcity / converged-favorite skips.
    ("NO", 1): 0.27,  ("NO", 2): 0.17,  ("NO", 0): 0.0,   # 2026-06-18: d+0 NO standalone overlay is
    # PROVEN −EV (badatmath d+0 NO −3.2%, n=1563) → weight 0; the 0.10 spilled to the +EV d+1/d+2 NO
    # horizons (+7.9%/+10.9%). d+0 PAIR legs are unaffected (separate ("PAIR",0) cell).
}
# 2026-06-11 audit: overlay now includes EDGE buckets (or-below / or-higher) — his
# NO 0.52-0.85 on edges = +5.7% (n=438) ≈ interiors +6.5% (n=3,877); they were
# silently excluded by the interior-only iteration and they are his NO meat.

# ── PAIR-INTENT FAVORITE QUOTING (2026-06-11 audit) ──────────────────────────
# His merge engine's core slice was structurally UNREACHABLE for us: on converged
# ladders (favorite ask > BAND_PX_CEIL) he bids BOTH sides of the favorite bucket
# (YES ~0.45-0.70 + NO ~0.20-0.40, Σ ≤ ~0.90) → both fill → on-chain MERGE → $1.
# Decision-grade on his post-05-04 fills: favorite YES leg 0.45-0.70 = +20.1%
# (n=170); cheap-NO PAIR legs = +52% May / +74% Jun (vs SOLO cheap NO −66/−100% —
# the pair context is what makes the cheap leg safe). Both legs are +EV standalone
# AND a completed pair locks ≥ (1 − Σ) per share risk-free + feeds merge velocity.
# Equal SHARES per leg (merge consumes share-for-share). Exempt from BAND_PX_CEIL
# by design — the economics here are a locked merge, not a directional band.
BAND_PAIR_FAV_ENABLED = True
BAND_PAIR_FAV_YES_MIN = 0.45   # real YES ask window for the favorite leg
BAND_PAIR_FAV_YES_MAX = 0.70   # above this the pair Σ can't clear PAIR_FAV_SUM_MAX
BAND_PAIR_FAV_SUM_MAX = 0.90   # qy + qn ≤ this ⇒ ≥ 10¢/sh locked on completion
# 2026-06-15 PAIR-SHADOW (measure-only, no cash): for each near-mode YES band leg
# we actually post, fetch the real NO book once and log the would-be NO pair leg +
# merge margin. The 5 real merges to date were ACCIDENTAL band-YES (~0.27) + overlay-
# NO (~0.61) overlaps (Σ 0.81-0.92, all +margin); PAIR_FAV proper posts ~0 (cash-
# starved + aimed at converged favorites = one-sided flow). This logs the deliberate-
# pair opportunity on the buckets where merges actually happen, so pair_shadow_join.py
# can estimate co-fill rate + real margin toward n>=100 before any live PAIR re-rank.
BAND_PAIR_SHADOW = True
BAND_PAIR_SHADOW_MARGIN = 0.0  # extra discount below NO touch when sizing the shadow leg
# 2026-06-17 SAME-BUCKET PAIRING (LIVE) — the badatmath co-fill engine. The 31-day
# re-derivation (n=42,470 buys/7,955 resolved, analysis/weather/badatmath_audit/
# TEARDOWN_31D.md) showed his merge velocity comes from quoting BOTH sides of the SAME
# near-mode/shoulder bucket: 40% of his buckets are two-sided (Σ bids ~0.79-0.87) → merge
# $1. Ours co-fill ~5% because the YES band (near-mode) and the favorite-NO overlay target
# DISJOINT buckets. This flag posts a NO pair-leg on each YES band leg we post, bid down
# only as far as needed to lock the merge margin (Σ bids ≤ BAND_PAIR_SUM_MAX = 0.92, ≥8¢/sh).
# Either leg alone is already a validated position (YES band +7.6% / favorite-NO +3.7%,
# n>=100 gate 06-17), and a completed pair merges to $1 calibration-free — so downside is
# bounded. Shares the NO daily cap; posts ahead of the standalone NO overlay (mergeable
# first). Revert: False (pair_shadow logging continues either way). Caveat: co-fill RATE is
# conditional-on-fill — pair_samebucket emits validate it live toward his 40%.
BAND_PAIR_SAMEBUCKET = True
BAND_PAIR_SB_MAX_BEHIND = 0.10  # skip the NO pair-leg if locking the margin needs a bid > this below the NO touch (fill-prob floor)

# ── DEAD-QUOTE RECLAIM (2026-06-11 audit) ────────────────────────────────────
# One-post-per-token + no reprice = stale quotes the book walked AWAY from sit
# for days consuming cash-gate headroom (resting commitments reduce free USDC).
# Reclaim ONLY the harmless half: unfilled, old, and ≥ BEHIND below the current
# touch (someone outbid us — we're not the market). NEVER reprice toward a
# converged mode: quotes the book walks THROUGH are the stale-band edge (his
# d+2 +56.5% > d+0 −3.4% ordering) and must keep resting.
BAND_RECLAIM_AGE_S     = 2 * 3600   # 2026-06-15: 6h→2h. queue_priority_join.py — our missed-fill
                                    # quotes were median ~13h stale, sitting median 4¢ (8 ticks) behind
                                    # the live touch (147 of his fills landed above our bid). 6h age
                                    # gate blocked the "≥2¢ behind touch" reclaim from chasing the
                                    # touch; 2h lets it re-quote fresh. min age before reclaimable
BAND_RECLAIM_BEHIND    = 0.02       # reclaim if our bid ≤ touch − this
BAND_RECLAIM_PER_CYCLE = 10         # book fetches per 300s cycle (rotating)

# ── BANKROLL-PROPORTIONAL STAKES (2026-06-11, user go) ───────────────────────
# Fixed $ stakes freeze compounding (growth goes linear between manual constant
# edits — BAND_BASE_STAKE's own history: "8→3 for the $155 bankroll") and are
# anti-Kelly in drawdowns (fixed $ = rising fraction of a shrinking bankroll).
# stake = clamp(capital·frac, floor, cap). Fracs calibrated so the FLOORS BIND
# until ~$300-450 capital: below that every new dollar buys BREADTH via the
# cash gate (badatmath's scaling axis — per-bucket $ flat across a 5× deploy
# ramp); stakes only deepen once the surface saturates. In drawdowns stakes
# shrink toward the floors (fractional-Kelly brake). Kill switches untouched.
BAND_STAKE_FRAC_YES = 0.005   # 2026-06-15: 0.010→0.005 — breadth model. At 0.010 the YES base was
                              # $2.68 at $268 capital (≈ the old $3 floor), 3× his ~$1 fills. At
                              # 0.005 the exchange-min floor max($1,5×q) binds through ~$250-450
                              # capital, so YES posts AT the CLOB minimum (max breadth) and only
                              # deepens above that. NO frac unchanged (its $4.5 floor is grounded).
BAND_STAKE_FRAC_NO  = 0.015
BAND_STAKE_MAX      = 20.0   # existing per-stake ceiling
BAND_NO_CAP_FRAC    = 0.30   # NO daily cap = max(BAND_NO_DAILY_CAP, frac·capital):
                             # NO is the scarce pair leg (YES side is uncapped, pairs
                             # need both); fixed $40 freezes pair formation as capital
                             # compounds. Floor binds to ~$133 capital (0.30·133≈40).


def band_stakes(capital: float) -> tuple:
    """(yes_base_stake, no_stake) for the current bankroll capital."""
    c = max(0.0, float(capital or 0.0))
    return (min(max(BAND_BASE_STAKE, c * BAND_STAKE_FRAC_YES), BAND_STAKE_MAX),
            min(max(BAND_NO_STAKE, c * BAND_STAKE_FRAC_NO), BAND_STAKE_MAX))


def band_no_daily_cap(capital: float) -> float:
    """NO-overlay daily posting cap for the current bankroll capital."""
    return max(BAND_NO_DAILY_CAP,
               max(0.0, float(capital or 0.0)) * BAND_NO_CAP_FRAC)


# ── PAIR MERGE (2026-06-11): held YES+NO on the same condition = $1/share at
# resolution; NegRiskAdapter.mergePositions converts it to USDC NOW via the
# proxy factory (execution/merger.py — on-chain path verified, adapter already
# CTF-approved). His cash-velocity engine: 638 merges / ~50% of buy$ recycled
# same-day (Jun 9-11 pull). Needs a few $ of POL gas in the EOA; ungated
# otherwise — a merge is strictly cash-positive (no fee, no market risk).
BAND_MERGE_ENABLED    = True
BAND_MERGE_MIN_SHARES = 3.0   # 2026-06-17: 5→3 (velocity). With same-bucket pairing live, pairs
                              # rarely co-fill both legs fully ⇒ mergeable overlap min(yes_sh,no_sh)
                              # is often 3-5; at 5 those partial pairs waited for resolution instead
                              # of recycling. A 3-share merge frees $3 cash + locks ≥8¢/sh (our pairs
                              # are Σ≤0.92) for ~$0.02 gas. BAND_MERGE_MIN_EDGE 0.03 still skips dust.
BAND_MERGE_MIN_EDGE   = 0.03  # require 1 − entry_y − entry_n ≥ this (pairs near Σ=1
                              # are better left to settle; merging them just spends gas)


def _beta_h(local_hour):
    """EV-optimal anomaly gain by local hour (measured, dist_kalman_ev.py)."""
    if local_hour is None or local_hour < 11: return 0.00
    if local_hour < 13: return 0.30
    if local_hour < 15: return 0.40
    return 0.41


def _r2_h(local_hour):
    """Variance the morning obs explains by local hour (measured)."""
    if local_hour is None or local_hour < 11: return 0.00
    if local_hour < 13: return 0.14
    if local_hour < 15: return 0.26
    return 0.30


def _local_hour(city):
    """City-local clock hour, or None if the tz can't be resolved (safe fallback)."""
    try:
        from analysis.weather.stations import STATIONS
        from zoneinfo import ZoneInfo
        from datetime import datetime, timezone as _tz
        tz = STATIONS[city].tz
        return datetime.now(_tz.utc).astimezone(ZoneInfo(tz)).hour if tz else None
    except Exception:
        return None

# Sky rank → regime label (sky_rank 0=clear, 4=overcast)
#  sky_rank comes from the METAR cache (0=SKC/CLR, 1=FEW, 2=SCT, 3=BKN, 4=OVC/VV)
REGIME_FROM_SKY = {0: "SUNNY", 1: "SUNNY", 2: "PARTLY_CLOUDY", 3: "CLOUDY", 4: "CLOUDY"}
REGIME_FIRE     = {"SUNNY", "PARTLY_CLOUDY"}    # only fire in these regimes
REGIME_SIGMA_MUL= {"SUNNY": 1.0, "PARTLY_CLOUDY": 1.2, "CLOUDY": 1.5}  # uncertainty multiplier


@dataclass
class Signal:
    city:        str
    bucket:      tuple[float, float]   # (lo_c, hi_c)  always in °C
    direction:   str                   # "YES" or "NO"
    token_id:    str
    p_model:     float                 # MC-based bucket probability (current primary)
    ask:         float
    edge:        float
    confidence:  float
    stake:       float
    regime:      str
    phase:       str
    metar_age_s: float
    kalman_var:  float
    kriging_pct: float   # fraction of posterior that came from spatial propagation
    p_gev:       float = 0.0   # shadow: GEV closed-form bucket probability
    drift_bias:  float = 0.0   # learned drift correction applied at peak hour
    maker:       bool  = False # STRUCT_BAND: post a resting maker bid (not a taker market buy)
    quote_price: float = 0.0   # STRUCT_BAND: the maker bid price to post (≤ ask, never crosses)


@dataclass
class _CityState:
    """Live Kalman state + metadata for one city."""
    city:        str
    idx:         int              # index in the 49-city state vector
    # Kalman marginal posterior (marginal extracted from joint P matrix)
    x_hat:       float = 0.0     # posterior mean residual (°C)
    # Posterior variance stored in the joint P matrix; accessed via engine.P[idx, idx]
    last_obs_ts:    float = 0.0     # Unix timestamp of latest METAR
    running_max:    Optional[float] = None
    running_max_ts: float = 0.0     # Unix timestamp when running_max last increased
    regime:      str = "SUNNY"
    obs_count:   int = 0
    obs_date:    str = ""        # YYYY-MM-DD of the day running_max belongs to
    # For kriging contribution tracking
    last_update_from_self: bool = True
    # 2D velocity state (Langevin)
    v_hat:     float = 0.0          # posterior mean of dX/dt (°C/h)
    pv_var:    float = VEL_PRIOR_VAR # posterior variance of v_hat ((°C/h)²)
    obs_buf:   list  = field(default_factory=list)  # [(t_h, x_obs), …] last VEL_OBS_N
    last_temp: float = float("nan") # most recent raw observed temperature (°C)
    # Drift baseline: μ_drift[hour] ← α × y_obs_raw + (1−α) × μ_drift[hour]
    # α = 1 − exp(−Δt_days / τ). Captures persistent residual bias on top of
    # the static (month, hour) table — climate drift + NWP version updates.
    drift_bias:   dict = field(default_factory=dict)   # {hour_utc: float °C}
    drift_last_ts: dict = field(default_factory=dict)  # {hour_utc: unix_ts}
    # Last MC-vs-GEV shadow snapshot (for parallel logging)
    gev_probs_last:  dict = field(default_factory=dict)
    gev_anchor_last: float = 0.0
    mc_probs_last:   dict = field(default_factory=dict)   # raw Monte-Carlo (legacy; shadow A/B)
    pa_probs_last:   dict = field(default_factory=dict)   # peak-anchored (Rice) shadow pricer
    ps_probs_last:   dict = field(default_factory=dict)   # PA-shrunk pricer (primary)
    ps_center_last:  float = 0.0   # PA-shrunk daily-max center (°C) — for NO floored/forecast audit
    cal_probs_last:  dict = field(default_factory=dict)   # PA-shrunk after isotonic recal (staged; YES gate)
    # Joint 2N Kalman shadow estimates (Tier-3, shadow-only — not used live)
    x_hat_joint:  float = 0.0
    v_hat_joint:  float = 0.0
    pv_var_joint: float = 0.0


class STWAEngine:
    """
    Spatiotemporal Weather Arbitrage Engine.

    Thread-safe: on_metar() acquires a lock before updating Kalman state.
    get_signals() reads state under the same lock.
    """

    def __init__(
        self,
        params_path: str | Path = "config/stwa_params.json",
        bankroll: float = 100.0,
        stake_min: float = 3.0,
        stake_max: float = 20.0,
        kelly_fraction: float = 0.20,
    ) -> None:
        self._lock = threading.Lock()
        self.bankroll    = bankroll
        self.stake_min   = stake_min
        self.stake_max   = stake_max
        self.kelly_frac  = kelly_fraction

        self._params_path = Path(params_path)
        self._params: dict = {}
        self._cities: dict[str, _CityState] = {}
        self._city_list: list[str] = []   # ordered list matching spatial_cov rows

        # Kalman state vectors (N_cities dimensional)
        self._X: np.ndarray = np.array([])   # posterior mean
        self._P: np.ndarray = np.array([])   # posterior covariance (N×N)
        self._C: np.ndarray = np.array([])   # spatial process covariance (prior)

        # NWP forecast cache: city → {hour_utc: temp_c}
        self._nwp_cache: dict[str, dict[int, float]] = {}
        # NWP DEW-point forecast cache: city → {hour_utc: dew_c}. Separate from
        # _nwp_cache (air temp) — the humidity correction (A1) regresses obs dew
        # on (obs_dew − NWP_dew), so it must read THIS, never the air-temp cache.
        self._nwp_dew_cache: dict[str, dict[int, float]] = {}
        self._nwp_date:  str = ""

        # Calibration log: city → [(p_model, outcome), ...]
        self._cal_log: dict[str, list[tuple[float, int]]] = {}
        self._suspended: set[str] = set()

        # Persistence paths (same directory as params)
        _base = self._params_path.parent.parent / "data"
        self._state_kalman = _base / "stwa_kalman_state.npz"
        self._state_cities = _base / "stwa_city_state.json"
        self._save_counter: int = 0

        self._load_params()
        self._restore_state()

    # ── Param loading ──────────────────────────────────────────────────────────

    def _load_params(self) -> None:
        if not self._params_path.exists():
            logger.warning("[STWA] params not found at %s — engine in stub mode", self._params_path)
            return

        with open(self._params_path) as f:
            self._params = json.load(f)

        # City order for spatial covariance
        self._city_list = self._params.get("city_order", list(self._params["stations"].keys()))
        N = len(self._city_list)

        # Spatial covariance matrix
        C_raw = np.array(self._params["spatial_covariance"])
        self._C = C_raw if C_raw.shape == (N, N) else np.eye(N) * 0.5

        # Initial Kalman state: X=0 (no anomaly), P=C (prior = spatial covariance)
        self._X = np.zeros(N)
        self._P = self._C.copy()

        # Joint 2N shadow Kalman (Tier-3) — runs in PARALLEL, does NOT drive live
        # state. State [X;V]; block prior position=C, velocity=diag(κ_i·C_ii)
        # (stationary Var(V) of the inertial-OU). Not persisted; warms each start.
        self._Sj = np.zeros(2 * N)
        _kap0 = np.array([_get_kappa(self._params["stations"].get(c, {}), 0)
                          for c in self._city_list])
        self._Pj = np.zeros((2 * N, 2 * N))
        self._Pj[:N, :N] = self._C
        self._Pj[N:, N:] = np.diag(np.maximum(_kap0 * np.diag(self._C), 1e-6))
        self._shadow_lock = threading.Lock()
        self._joint_FQ_cache: dict = {}   # (κ-bin, round(Δt,2)) → (F, Q)

        # PA-shrunk pricer per-city calibration (peak_bias, sigma); pooled fallback.
        self._peak_calib: dict = {}
        _calib_path = self._params_path.parent / "stwa_peak_calib.json"
        if _calib_path.exists():
            try:
                self._peak_calib = json.load(open(_calib_path))
                logger.info("[STWA] peak calib loaded: %d cities",
                            len([k for k in self._peak_calib if not k.startswith("_")]))
            except Exception as e:
                logger.warning("[STWA] peak calib load failed: %s", e)

        # Isotonic recalibration map for PA-shrunk bucket probs (monotone g: p→p_cal).
        # Fit on 2024 history (analysis/weather/stwa_isotonic_calib.py): PA-shrunk
        # has positive rank-corr (+0.39) but is overconfident at high p; g squashes
        # it (g(0.95)≈0.40), ECE 0.056→0.000. STAGED: applied to cal_probs_last for
        # logging + the YES re-enable gate; live NO/arb still use raw coherent p_ps.
        self._isotonic = None
        _iso_path = self._params_path.parent / "stwa_isotonic.json"
        if _iso_path.exists():
            try:
                _iso = json.load(open(_iso_path))
                self._isotonic = (np.array(_iso["grid"], dtype=float),
                                  np.array(_iso["calibrated"], dtype=float))
                logger.info("[STWA] isotonic recal map loaded (max|g(p)-p|=%.2f)",
                            float(_iso.get("fit", {}).get("near_identity_maxdev", 0.0)))
            except Exception as e:
                logger.warning("[STWA] isotonic load failed: %s", e)

        # Build city state registry
        for idx, city in enumerate(self._city_list):
            if city in self._params["stations"]:
                self._cities[city] = _CityState(city=city, idx=idx)

        logger.info("[STWA] loaded params: %d cities, %dx%d covariance", N, N, N)

    def _save_state(self) -> None:
        """Persist Kalman X/P and per-city velocity state to disk."""
        try:
            np.savez_compressed(str(self._state_kalman), X=self._X, P=self._P)
            city_data = {}
            for city, cs in self._cities.items():
                city_data[city] = {
                    "x_hat": cs.x_hat, "last_obs_ts": cs.last_obs_ts, "last_temp": cs.last_temp,
                    "running_max": cs.running_max, "running_max_ts": cs.running_max_ts,
                    "obs_date": cs.obs_date, "regime": cs.regime,
                    "obs_count": cs.obs_count,
                    "v_hat": cs.v_hat, "pv_var": cs.pv_var,
                    "obs_buf": cs.obs_buf,
                    # JSON keys must be strings — convert int hour keys
                    "drift_bias":    {str(h): v for h, v in cs.drift_bias.items()},
                    "drift_last_ts": {str(h): v for h, v in cs.drift_last_ts.items()},
                }
            with open(self._state_cities, "w") as f:
                json.dump(city_data, f)
        except Exception as e:
            logger.debug("[STWA] state save failed: %s", e)

    def _restore_state(self) -> None:
        """Restore Kalman X/P and velocity state from disk if available."""
        try:
            if self._state_kalman.exists():
                snap = np.load(str(self._state_kalman))
                X_saved, P_saved = snap["X"], snap["P"]
                if X_saved.shape == self._X.shape and P_saved.shape == self._P.shape:
                    self._X = X_saved.astype(float)
                    self._P = P_saved.astype(float)
                    logger.info("[STWA] Kalman state restored from %s", self._state_kalman)
                else:
                    logger.info("[STWA] Kalman state shape mismatch — using prior")
            if self._state_cities.exists():
                with open(self._state_cities) as f:
                    city_data = json.load(f)
                for city, d in city_data.items():
                    cs = self._cities.get(city)
                    if cs is None:
                        continue
                    cs.x_hat         = float(d.get("x_hat", 0.0))
                    cs.last_obs_ts   = float(d.get("last_obs_ts", 0.0))
                    cs.last_temp     = float(d.get("last_temp", float("nan")))
                    cs.running_max   = d.get("running_max")
                    cs.running_max_ts= float(d.get("running_max_ts", 0.0))
                    cs.obs_date      = d.get("obs_date", "")
                    cs.regime        = d.get("regime", "SUNNY")
                    cs.obs_count     = int(d.get("obs_count", 0))
                    cs.v_hat         = float(d.get("v_hat", 0.0))
                    cs.pv_var        = float(d.get("pv_var", VEL_PRIOR_VAR))
                    cs.obs_buf       = [tuple(x) for x in d.get("obs_buf", [])]
                    cs.drift_bias    = {int(h): float(v) for h, v in d.get("drift_bias", {}).items()}
                    cs.drift_last_ts = {int(h): float(v) for h, v in d.get("drift_last_ts", {}).items()}
                logger.info("[STWA] city velocity state restored (%d cities)", len(city_data))
        except Exception as e:
            logger.info("[STWA] state restore failed (%s) — starting from prior", e)

    def reset_daily(self) -> None:
        """Reset all cities (legacy — prefer reset_city for per-city local midnight)."""
        with self._lock:
            N = len(self._city_list)
            self._X = np.zeros(N)
            self._P = self._C.copy()
            for cs in self._cities.values():
                cs.running_max = None
                cs.obs_date    = ""
                cs.x_hat       = 0.0
                cs.v_hat       = 0.0
                cs.pv_var      = VEL_PRIOR_VAR
                cs.obs_buf     = []
            self._nwp_cache.clear()
            self._nwp_dew_cache.clear()
            self._nwp_date = ""
        logger.info("[STWA] full daily reset — Kalman state re-initialised")

    def reset_city(self, city: str) -> None:
        """Reset one city at its local midnight without disturbing other cities."""
        with self._lock:
            cs = self._cities.get(city)
            if cs is None:
                return
            i = cs.idx
            # Zero this city's component in the joint state vector
            self._X[i] = 0.0
            # Reset row/col i of P back to the prior spatial covariance
            self._P[i, :] = self._C[i, :]
            self._P[:, i] = self._C[:, i]
            cs.running_max = None
            cs.obs_date    = ""
            cs.x_hat       = 0.0
            cs.v_hat       = 0.0
            cs.pv_var      = VEL_PRIOR_VAR
            cs.obs_buf     = []
            self._nwp_cache.pop(city, None)
            self._nwp_dew_cache.pop(city, None)
        logger.info("[STWA] city reset at local midnight: %s", city)

    # ── NWP forecast ───────────────────────────────────────────────────────────

    def update_nwp_forecast(self, city: str, hourly_temps: dict[int, float],
                            hourly_dew: Optional[dict[int, float]] = None) -> None:
        """Called by weather_arb when a fresh Open-Meteo forecast arrives.
        hourly_dew (NWP dewpoint, °C) feeds the A1 humidity correction; when
        absent the correction is skipped (≈ as good as the dew term off)."""
        with self._lock:
            self._nwp_cache[city] = hourly_temps
            if hourly_dew is not None:
                self._nwp_dew_cache[city] = hourly_dew

    def _get_mu(self, city: str, hour_utc: int) -> float:
        """Bias-corrected NWP forecast temperature for a city at a given UTC hour.
        Includes static (month, hour) bias + learned drift baseline."""
        nwp = self._nwp_cache.get(city, {})
        t_nwp = nwp.get(hour_utc)
        if t_nwp is None:
            return float("nan")

        st = self._params["stations"].get(city, {})
        month = _current_month()
        bias_key = f"{month}_{hour_utc}"
        bias = st.get("bias", {}).get(bias_key, 0.0)
        # Drift baseline (learned EMA of recent residuals)
        cs = self._cities.get(city)
        drift_h = 0.0
        if cs is not None:
            drift_h = float(np.clip(cs.drift_bias.get(hour_utc, 0.0),
                                    -DRIFT_BIAS_LIMIT, DRIFT_BIAS_LIMIT))
        return t_nwp + bias + drift_h

    def _get_mu_curve(self, city: str, t_start: float, t_end: float) -> tuple[np.ndarray, np.ndarray]:
        """Return (t_grid, mu_grid) for simulation from t_start to t_end (unix seconds)."""
        t_grid   = np.arange(t_start, t_end, MC_STEP_S, dtype=float)
        mu_grid  = np.full(len(t_grid), float("nan"))

        nwp = self._nwp_cache.get(city, {})
        if not nwp:
            return t_grid, mu_grid

        st     = self._params["stations"].get(city, {})
        biases = st.get("bias", {})
        month  = _current_month()
        cs = self._cities.get(city)
        # Snapshot drift baseline once per call (consistent across grid)
        drift_table = {}
        if cs is not None:
            for _h, _v in cs.drift_bias.items():
                drift_table[_h] = float(np.clip(_v, -DRIFT_BIAS_LIMIT, DRIFT_BIAS_LIMIT))

        for i, ts in enumerate(t_grid):
            h = int((ts % 86400) / 3600)
            t_nwp = nwp.get(h)
            if t_nwp is not None:
                b = biases.get(f"{month}_{h}", 0.0)
                d = drift_table.get(h, 0.0)
                mu_grid[i] = t_nwp + b + d

        # Fill small gaps by linear interpolation
        valid = np.isfinite(mu_grid)
        if valid.any() and not valid.all():
            mu_grid = np.interp(
                np.arange(len(t_grid)),
                np.where(valid)[0],
                mu_grid[valid]
            )

        return t_grid, mu_grid

    # ── Kalman filter ──────────────────────────────────────────────────────────

    def on_metar(
        self,
        city:        str,
        temp_c:      float,
        dew_c:       Optional[float],
        sky_rank:    int,
        obs_ts:      float,
        running_max: Optional[float],
        today_str:   str = "",
    ) -> None:
        """
        Process one METAR observation.  Updates:
          - Running maximum for city
          - Regime classification
          - Kalman posterior for ALL cities (spatial propagation)
        """
        if not self._params or city not in self._cities:
            return

        cs  = self._cities[city]
        idx = cs.idx
        st  = self._params["stations"].get(city, {})

        # ── Regime classification ──────────────────────────────────────────────
        regime = REGIME_FROM_SKY.get(min(sky_rank, 4), "PARTLY_CLOUDY")

        # ── Bias-corrected NWP for this hour ──────────────────────────────────
        hour_utc = int((obs_ts % 86400) / 3600)
        mu_now   = self._get_mu(city, hour_utc)

        if not math.isfinite(mu_now):
            # No NWP forecast — update running max + regime but skip Kalman
            with self._lock:
                cs.regime       = regime
                cs.last_obs_ts  = obs_ts
                cs.last_temp    = temp_c
                # Official-max only — never fold temp_c (see Kalman branch).
                new_max = _new_max(cs.running_max, running_max) if running_max is not None else cs.running_max
                if new_max != cs.running_max:
                    cs.running_max_ts = obs_ts
                cs.running_max  = new_max
                cs.obs_date     = today_str
            return

        # ── Humidity correction ───────────────────────────────────────────────
        mu_corrected = mu_now
        if dew_c is not None and math.isfinite(dew_c):
            # A1 fix: read the NWP DEW forecast (not the air-temp cache). alpha was
            # fit on (obs_dew − NWP_dew); reading air temp here tripled center MSE.
            nwp_dew = self._nwp_dew_cache.get(city, {}).get(hour_utc)
            if nwp_dew is not None:
                month = _current_month()
                alpha = st.get("alpha_humidity", {}).get(str(month), 0.0)
                mu_corrected += alpha * (dew_c - nwp_dew)

        # ── Drift baseline correction ─────────────────────────────────────────
        # Apply previously-learned drift bias for this (city, hour). Subtracted
        # because the static bias overstated/understated by this much in
        # recent observations. Bounded to ±DRIFT_BIAS_LIMIT.
        drift_h = float(cs.drift_bias.get(hour_utc, 0.0))
        drift_h = float(np.clip(drift_h, -DRIFT_BIAS_LIMIT, DRIFT_BIAS_LIMIT))
        mu_corrected += drift_h

        # ── Residual (what the OU process models) ─────────────────────────────
        y_obs = temp_c - mu_corrected

        # ── Gross error check ─────────────────────────────────────────────────
        if abs(y_obs) > 8.0:
            logger.debug("[STWA] %s outlier rejected: T=%.1f mu=%.1f y=%.1f", city, temp_c, mu_corrected, y_obs)
            return

        # ── Update drift baseline (EMA) ───────────────────────────────────────
        # y_obs is the residual AFTER static bias + previous drift was subtracted.
        # If y_obs is persistently positive, drift_h is wrong by that amount.
        # We add y_obs into drift_h with EMA weight α = 1 − exp(−Δt_days/τ).
        # First observation for this hour: initialize to y_obs (no prior).
        last_drift_ts = cs.drift_last_ts.get(hour_utc, 0.0)
        if last_drift_ts > 0:
            dt_days = max((obs_ts - last_drift_ts) / 86400.0, 1/24)  # min 1 hour
            alpha_d = 1.0 - math.exp(-dt_days / DRIFT_TAU_DAYS)
        else:
            alpha_d = 0.05   # first sample for this hour: 5% weight, smooth start
        cs.drift_bias[hour_utc] = drift_h + alpha_d * y_obs
        cs.drift_last_ts[hour_utc] = obs_ts

        # ── Kalman update (joint over all cities) ─────────────────────────────
        sigma_obs = st.get("sigma_obs", 0.5)
        regime_mul = REGIME_SIGMA_MUL.get(regime, 1.2)
        sigma_obs_eff = sigma_obs * regime_mul

        dt_hours = max((obs_ts - cs.last_obs_ts) / 3600.0, 1/60) if cs.last_obs_ts > 0 else 6.0
        dt_hours = min(dt_hours, 12.0)

        with self._lock:
            # Time propagation (predict step)
            N = len(self._city_list)
            kappas = np.array([
                _get_kappa(self._params["stations"].get(c, {}), hour_utc)
                for c in self._city_list
            ])
            F = np.diag(np.exp(-kappas * dt_hours))
            decay_ij = np.outer(kappas, kappas)
            k_eff = (kappas[:, None] + kappas[None, :]) / 2.0
            Q = self._C * (1.0 - np.exp(-k_eff * dt_hours))

            X_pred = F @ self._X
            P_pred = F @ self._P @ F.T + Q

            # Observation update (single station)
            h_vec = np.zeros(N)
            h_vec[idx] = 1.0
            S     = float(h_vec @ P_pred @ h_vec) + sigma_obs_eff ** 2
            K     = P_pred @ h_vec / S
            innov = y_obs - float(h_vec @ X_pred)

            # Mahalanobis check: |innov|/sqrt(S) > 4 → reject
            if abs(innov) / math.sqrt(S) > 4.0:
                logger.debug("[STWA] %s Mahalanobis outlier: innov=%.2f S=%.2f", city, innov, S)
                # Still update time propagation
                self._X = X_pred
                self._P = P_pred
            else:
                self._X = X_pred + K * innov
                self._P = P_pred - np.outer(K, K) * S

                # Ensure P stays symmetric positive definite (numerical hygiene)
                self._P = (self._P + self._P.T) / 2.0
                np.fill_diagonal(self._P, np.maximum(np.diag(self._P), 1e-6))

            cs.x_hat    = float(self._X[idx])
            cs.last_obs_ts  = obs_ts
            cs.last_temp    = temp_c
            # Running max must track ONLY the official METAR high the WU/PM
            # oracle resolves against — the caller passes official_running_max_c.
            # Never fold temp_c in: on the NMS path temp_c is a sub-hourly
            # Synoptic/AMeDAS reading the oracle never sees, so maxing it into
            # running_max would lift it above the official high (the M1β bug).
            new_max = _new_max(cs.running_max, running_max) if running_max is not None else cs.running_max
            if new_max != cs.running_max:
                cs.running_max_ts = obs_ts
            cs.running_max  = new_max
            cs.regime       = regime
            cs.obs_date     = today_str
            cs.obs_count   += 1
            cs.last_update_from_self = True

            # Periodic state persistence (every 20 Kalman updates)
            self._save_counter += 1
            if self._save_counter % 20 == 0:
                self._save_state()

            # ── Velocity Kalman update (OLS on RAW residuals, not x_hat) ────────
            # Raw residual y_obs is responsive; x_hat is Kalman-smoothed and lags.
            now_h = obs_ts / 3600.0
            cs.obs_buf.append((now_h, y_obs))
            if len(cs.obs_buf) > VEL_OBS_N:
                cs.obs_buf = cs.obs_buf[-VEL_OBS_N:]
            if len(cs.obs_buf) >= 3:
                v_obs, v_std = _ols_velocity(cs.obs_buf)
                R_v = max(v_std ** 2, VEL_MIN_OBS_VAR)
                K_v = cs.pv_var / (cs.pv_var + R_v)
                cs.v_hat   += K_v * (v_obs - cs.v_hat)
                cs.pv_var  *= (1.0 - K_v)
                cs.pv_var   = max(cs.pv_var, VEL_MIN_VAR)

        # ── Shadow joint 2N Kalman (Tier-3) ───────────────────────────────────
        # Runs in PARALLEL to the live position-only filter + OLS velocity above.
        # Drives NO live decision — logged via get_state_snapshot to compare the
        # joint posterior velocity vs the OLS hack before any promotion. Uses a
        # separate lock so it never adds latency to the live update path.
        if getattr(self, "_Sj", None) is not None:
            try:
                with self._shadow_lock:
                    Nn = len(self._city_list)
                    # (F,Q) depend only on (6h κ-bin, Δt) → cache the costly
                    # 204×204 Van Loan expm; steady state is cheap matmuls.
                    _ck = (hour_utc // 6, round(dt_hours, 2))
                    _fq = self._joint_FQ_cache.get(_ck)
                    if _fq is None:
                        kappas_j = np.array([
                            _get_kappa(self._params["stations"].get(c, {}), hour_utc)
                            for c in self._city_list
                        ])
                        _fq = _joint_FQ(kappas_j, VELOCITY_GAMMA, self._C, dt_hours)
                        if len(self._joint_FQ_cache) < 600:
                            self._joint_FQ_cache[_ck] = _fq
                    Fj, Qj = _fq
                    Sp = Fj @ self._Sj
                    Pp = Fj @ self._Pj @ Fj.T + Qj
                    hj = np.zeros(2 * Nn); hj[idx] = 1.0          # observe position of city idx
                    Sden = float(hj @ Pp @ hj) + sigma_obs_eff ** 2
                    Kj   = (Pp @ hj) / Sden
                    innj = y_obs - float(Sp[idx])
                    if abs(innj) / math.sqrt(Sden) <= 4.0:
                        self._Sj = Sp + Kj * innj
                        ImKH = np.eye(2 * Nn) - np.outer(Kj, hj)   # Joseph form (PSD-safe)
                        self._Pj = ImKH @ Pp @ ImKH.T + np.outer(Kj, Kj) * (sigma_obs_eff ** 2)
                    else:
                        self._Sj, self._Pj = Sp, Pp
                    self._Pj = (self._Pj + self._Pj.T) / 2.0
                    cs.x_hat_joint  = float(self._Sj[idx])
                    cs.v_hat_joint  = float(self._Sj[Nn + idx])
                    cs.pv_var_joint = float(self._Pj[Nn + idx, Nn + idx])
            except Exception as e:
                logger.debug("[STWA] shadow joint Kalman %s: %s", city, e)

    # ── Running maximum distribution ───────────────────────────────────────────

    def _forecast_bucket_probs(
        self,
        city: str,
        t_now: float,
        t_close: float,
        buckets: list[tuple[float, float]],
        phase: str = "PRE_PEAK",
    ) -> dict[tuple[float, float], float]:
        """
        Monte Carlo estimate of P(daily_max ∈ bucket) for each bucket.
        Uses time-varying OU parameters and the current Kalman posterior.
        """
        if not buckets:
            return {}

        cs = self._cities[city]
        st = self._params["stations"].get(city, {})

        tau_hours = (t_close - t_now) / 3600.0
        if tau_hours < 0.5:
            # Market nearly closed: just check if running max is in bucket
            m = cs.running_max if cs.running_max is not None else float("-inf")
            return {b: 1.0 if b[0] <= m < b[1] else 0.0 for b in buckets}

        # Get Kalman posterior (marginal for this city)
        with self._lock:
            idx   = cs.idx
            x_hat = float(self._X[idx])
            p_var = float(self._P[idx, idx])
            # Kriging contribution: how much of the posterior came from other cities?
            p_prior_diag = float(self._C[idx, idx])
            kriging_pct  = max(0.0, 1.0 - p_var / max(p_prior_diag, 1e-6))

        cs.kriging_pct_last = kriging_pct

        # NWP diurnal curve for simulation period
        t_grid, mu_grid = self._get_mu_curve(city, t_now, t_close)
        if not np.isfinite(mu_grid).any():
            return {}

        n_steps = len(t_grid)
        if n_steps < 2:
            return {}

        # Regime sigma multiplier; POST_PEAK dampens residual variance (day is done)
        _PHASE_SIG_MUL = {"PRE_PEAK": 1.0, "AT_PEAK": 0.5, "POST_PEAK": 0.15}
        regime_mul = REGIME_SIGMA_MUL.get(cs.regime, 1.2) * _PHASE_SIG_MUL.get(phase, 1.0)

        # Running maximum floor (needed for both initial condition and path_max)
        M0 = cs.running_max if cs.running_max is not None else float("-inf")

        # Simulate N_PATHS 2D Langevin paths: dX=V dt, dV=(−γV−κX)dt+σdW
        rng   = np.random.default_rng(seed=int(t_now) % (2**31))
        paths = np.zeros((N_PATHS, n_steps), dtype=np.float32)

        # Initial position: Kalman posterior, but hard-constrained by running_max.
        # If running_max was set within the last hour the temperature WAS at M0
        # recently — the Kalman sticky posterior may lie far below that due to
        # transient dips, which would produce inconsistent path initialisation.
        x_hat_eff = x_hat
        if (M0 > float("-inf") and np.isfinite(mu_grid[0])
                and (t_now - cs.running_max_ts) < 3600):
            x_hat_eff = max(x_hat, M0 - float(mu_grid[0]))

        paths[:, 0] = rng.normal(x_hat_eff, math.sqrt(max(p_var, 1e-6)),
                                 N_PATHS).astype(np.float32)
        v_now = rng.normal(cs.v_hat, math.sqrt(max(cs.pv_var, VEL_MIN_VAR)),
                           N_PATHS).astype(np.float32)

        _step_cache: dict = {}  # (kap, sig, dt_hr) → (F11,F12,F21,F22,L11,L21,L22)

        # Student-t innovation degrees of freedom. Empirical residuals have
        # excess kurtosis ~+1.7 (Jarque-Bera p≈0 for all cities). df=6 gives
        # excess kurtosis 3 — matches well. Rescale by sqrt((df-2)/df) so unit
        # variance matches Gaussian (else the OU σ has the wrong scale).
        # df=∞ would recover Gaussian; we expose INNOV_DF as a constant.
        _df = INNOV_DF
        _t_scale = math.sqrt((_df - 2.0) / _df) if _df > 2 else 1.0

        for i in range(n_steps - 1):
            h_utc = int((t_grid[i] % 86400) / 3600)
            kap   = _get_kappa(st, h_utc)
            sig   = _get_sigma(st, h_utc) * regime_mul
            dt_hr = (t_grid[i + 1] - t_grid[i]) / 3600.0

            ck = (round(kap, 4), round(sig, 4), round(dt_hr, 5))
            if ck not in _step_cache:
                _step_cache[ck] = _vel_step(kap, VELOCITY_GAMMA, sig, dt_hr)
            F11, F12, F21, F22, L11, L21, L22 = _step_cache[ck]

            # Standardized Student-t innovations (unit variance after rescale)
            n1 = (rng.standard_t(_df, N_PATHS) * _t_scale).astype(np.float32)
            n2 = (rng.standard_t(_df, N_PATHS) * _t_scale).astype(np.float32)

            new_x = (F11 * paths[:, i] + F12 * v_now + L11 * n1).astype(np.float32)
            v_now = (F21 * paths[:, i] + F22 * v_now
                     + L21 * n1 + L22 * n2).astype(np.float32)
            paths[:, i + 1] = new_x

        # Temperature paths = residual + NWP diurnal
        T_paths = (paths + mu_grid.astype(np.float32)).astype(np.float32)  # (N, steps)

        # Running maximum: compete against already-observed max
        path_max = np.maximum(M0, T_paths.max(axis=1))  # (N,)

        # Bucket probabilities (MC)
        probs: dict[tuple[float, float], float] = {}
        for (lo, hi) in buckets:
            probs[(lo, hi)] = float(np.mean((path_max >= lo) & (path_max < hi)))
        cs.mc_probs_last = dict(probs)   # stash raw MC for shadow A/B (primary may differ)

        # GEV closed-form shadow: P2-I. Use the NWP daily-max from mu_grid as
        # anchor, apply the fitted GEV(loc, scale, shape) per (city, month) for
        # daily-max residuals. Stored as a parallel dict for shadow logging.
        # Future round: when shadow comparison validates GEV better than MC,
        # switch primary path.
        try:
            month = _current_month()
            gev_params = st.get("daily_max_gev", {}).get(str(month), None)
            if gev_params is not None:
                gev_loc   = float(gev_params.get("loc", 0.0))
                gev_scale = float(gev_params.get("scale", 1.0))
                gev_shape = float(gev_params.get("shape", 0.0))
                # Anchor: peak of bias-corrected NWP curve (incl. drift)
                nwp_peak = float(np.nanmax(mu_grid))
                gev_probs = {
                    (lo, hi): _gev_bucket_prob(lo, hi, M0, nwp_peak,
                                               gev_loc, gev_scale, gev_shape)
                    for (lo, hi) in buckets
                }
                # Stash on cs for shadow logger pickup
                cs.gev_probs_last = gev_probs
                cs.gev_anchor_last = nwp_peak
        except Exception:
            cs.gev_probs_last = {}

        # ── Peak-anchored shadow pricer (Rice up-crossing; P3 Tier-2) ─────────
        # Deterministic moment propagation of the residual (mean, variance) along
        # the grid using the SAME 2D transition the MC uses, then F_S via the
        # up-crossing integral. Shadow-only — logged for calibration A/B vs MC/GEV.
        try:
            tg = np.asarray(t_grid, dtype=np.float64)
            m_arr   = np.empty(n_steps, dtype=np.float64)
            s2_arr  = np.empty(n_steps, dtype=np.float64)
            mx, vx = float(x_hat_eff), float(cs.v_hat)
            Pxx, Pxv, Pvv = max(p_var, 1e-6), 0.0, max(cs.pv_var, VEL_MIN_VAR)
            m_arr[0], s2_arr[0] = mx, Pxx
            for i in range(n_steps - 1):
                h_utc = int((tg[i] % 86400) / 3600)
                kap   = _get_kappa(st, h_utc)
                sig   = _get_sigma(st, h_utc) * regime_mul
                dt_hr = (tg[i + 1] - tg[i]) / 3600.0
                ck    = (round(kap, 4), round(sig, 4), round(dt_hr, 5))
                step  = _step_cache.get(ck)
                if step is None:
                    step = _vel_step(kap, VELOCITY_GAMMA, sig, dt_hr)
                    _step_cache[ck] = step
                F11, F12, F21, F22, L11, L21, L22 = step
                mx, vx = F11 * mx + F12 * vx, F21 * mx + F22 * vx
                nPxx = F11*F11*Pxx + 2*F11*F12*Pxv + F12*F12*Pvv + L11*L11
                nPxv = F11*F21*Pxx + (F11*F22 + F12*F21)*Pxv + F12*F22*Pvv + L11*L21
                nPvv = F21*F21*Pxx + 2*F21*F22*Pxv + F22*F22*Pvv + (L21*L21 + L22*L22)
                Pxx, Pxv, Pvv = nPxx, nPxv, nPvv
                m_arr[i + 1], s2_arr[i + 1] = mx, Pxx
            cs.pa_probs_last = _peak_anchored_bucket_probs(
                buckets, M0, mu_grid.astype(np.float64), m_arr, s2_arr)
        except Exception:
            cs.pa_probs_last = {}

        # ── PA-shrunk pricer (PRIMARY candidate) ──────────────────────────────
        # center = NWP_peak + per-city peak_bias + β·x_hat (β=0.30 shrinkage on
        # the intraday residual). σ per-city empirical. Coherent + running-max
        # floor. Data-validated calibrated (2024, n=12,835). Drives the allocator
        # when STWA_PRIMARY_PRICER=="PA_SHRUNK"; MC still computed for shadow A/B.
        try:
            _cal = self._peak_calib.get(city) or self._peak_calib.get("_pooled", {})
            # A2: per-(city,month) peak_bias (seasonal), falls back to scalar.
            _base = float(np.nanmax(mu_grid)) + _peak_bias_for(self._peak_calib, city, _current_month())
            _sig_fc = _peak_sigma_for(self._peak_calib, city, _current_month())
            if STWA_BAND_MODE:
                # time-varying gain + data-correct σ-floor (no σ-collapse).
                _h = _local_hour(city)
                _center = _base + _beta_h(_h) * x_hat
                _sig = max(BAND_SIGMA_FLOOR, _sig_fc * math.sqrt(1.0 - _r2_h(_h)))
            else:
                # legacy PA_SHRUNK: fixed β=0.30. Nowcast σ-collapse DISABLED 2026-06-06
                # (NOWCAST_SIGMA_COLLAPSE=False) — it hurt calibration on every metric; σ now
                # stays at the validated per-month value (lockout certainty via running-max floor).
                _center = _base + PA_SHRUNK_BETA * x_hat
                _sig = _sig_fc
                if NOWCAST_SIGMA_COLLAPSE and M0 is not None:
                    _sig = min(_sig_fc, max(NOWCAST_SIGMA_FLOOR,
                                            NOWCAST_REMAIN_RATIO * max(0.0, _center - float(M0))))
            cs.ps_probs_last = _peak_shrunk_bucket_probs(buckets, M0, _center, _sig)
            cs.ps_center_last = float(_center)
        except Exception:
            cs.ps_probs_last = {}

        # Isotonic recalibration (STAGED): correct PA-shrunk's high-p overconfidence.
        # Logged for live validation; becomes the YES sizing prob at re-enable.
        if self._isotonic is not None and cs.ps_probs_last:
            try:
                _g, _y = self._isotonic
                cs.cal_probs_last = {b: float(np.interp(p, _g, _y))
                                     for b, p in cs.ps_probs_last.items()}
            except Exception:
                cs.cal_probs_last = {}

        if STWA_PRIMARY_PRICER == "PA_SHRUNK" and cs.ps_probs_last:
            return cs.ps_probs_last
        return probs

    # ── Signal generation ──────────────────────────────────────────────────────

    def _band_allocate(self, city, entries, clob_books, bankroll, held_k, phase,
                       regime, metar_age, p_var, kriging_pct):
        """BAND MODE allocator — the new directional-YES strategy, ONLY.

        Buys the mode±1 YES band (the horse-race where the skill lives: band WR≈0.88 vs
        single≈0.44), STAGED at min-stake. GUARDED (rebuilt 2026-06-05 after a live misfire
        that bought near-worthless tail buckets the model overconfidently rated p=1.0):
          • WINDOW: 11 ≤ local hour ≤ BAND_HOUR_MAX AND phase ≠ POST_PEAK — the band is a
            PRE-peak→peak edge; after the peak the day's max is already decided.
          • SKILL: per-city σ ≤ YES_SIGMA_CUTOFF (high-σ cities are coin-flips).
          • LIQUIDITY: band legs must be INTERIOR (no open-ended [X,∞) tails) AND have a real
            ask in [BAND_ASK_MIN, 0.95] AND book depth ≥ min-stake. This kills the $0.001-ask
            stale-token fires outright.
          • SANITY: P_band ≥ BAND_P_MIN and BAND_EV_MIN ≤ EV ≤ BAND_EV_MAX. An efficient
            market (Brier≈0.01) never offers a true 100%+ edge — EV above the cap is a
            stale-ask artifact (model says p=1.0, market says 0.001 ⇒ the market is right).
        Arb + NO are OFF by construction. Every evaluation (fired or rejected, with reason)
        logs to band_alloc.jsonl. Min-stake until that log confirms +EV at n≥100.
        """
        import json as _json, time as _time
        from datetime import datetime as _dt, timezone as _tz
        from pathlib import Path as _Path

        def _log(reason, **kw):
            try:
                _d = _Path("logs/shadow/hot") / _dt.now(_tz.utc).date().isoformat()
                _d.mkdir(parents=True, exist_ok=True)
                with (_d / "band_alloc.jsonl").open("a") as _f:
                    _f.write(_json.dumps({"ts": _time.time(), "city": city,
                                          "reason": reason, **kw}) + "\n")
            except Exception:
                pass

        # ── window: pre-peak → peak only ──
        h = _local_hour(city)
        if h is None or not (11 <= h <= BAND_HOUR_MAX) or phase == "POST_PEAK":
            return []
        # ── skill: skip high-σ coin-flip cities ──
        sig_city = _peak_sigma_for(self._peak_calib, city, _current_month())
        if sig_city > YES_SIGMA_CUTOFF:
            return []

        # ── liquidity: interior buckets, real asks, fillable depth ──
        def _depth_ok(yes_tok):
            d = (clob_books.get(yes_tok) or {}).get("usd_depth")
            return d is None or d >= self.stake_min      # unknown depth → defer to exec loop
        valid = [e for e in entries
                 if e[0] > -900.0 and e[1] < 900.0       # interior (no open-ended tails)
                 and e[5] is not None and BAND_ASK_MIN <= e[5] <= 0.95
                 and _depth_ok(e[2])]
        if len(valid) < 2:                               # a band needs ≥2 liquid legs
            _log("no_liquid_band", local_h=h, n_valid=len(valid))
            return []

        valid.sort(key=lambda e: e[0])
        mi = max(range(len(valid)), key=lambda i: valid[i][4])     # modal = max p
        band = [valid[i] for i in (mi - 1, mi, mi + 1) if 0 <= i < len(valid)]
        sum_ask = sum(e[5] for e in band)
        p_band = sum(e[4] for e in band)
        band_ev = (p_band / sum_ask - 1.0) if sum_ask > 0 else -1.0

        fired = (p_band >= BAND_P_MIN and BAND_EV_MIN <= band_ev <= BAND_EV_MAX)
        # per-rank [p, ask, lo, hi] for the top liquid interior buckets — lets the
        # resolution join measure realized EV by RANK (tests "buy 2nd/3rd vs favorite").
        ranked = [[round(e[4], 3), round(e[5], 3), e[0], e[1]]
                  for e in sorted(valid, key=lambda x: -x[4])[:6]]
        _log("eval", local_h=h, sig_city=round(sig_city, 3), p_band=round(p_band, 4),
             sum_ask=round(sum_ask, 4), band_ev=round(band_ev, 4), fired=fired,
             shadow=BAND_SHADOW,
             buckets=[(e[0], e[1]) for e in band], ranked=ranked)
        if not fired:
            return []
        # SHADOW: log the would-fire band (fired=True above) but deploy NO real
        # capital — the band edge is unvalidated (efficient-mkt prior, n<100). The
        # band_alloc→Gamma join scores these would-fires; flip BAND_SHADOW=False
        # only after n≥100 confirms +EV at the real ask. NEG_RISK_ARB still fires.
        if BAND_SHADOW:
            return []

        sigs = []
        for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in band:
            sigs.append(Signal(
                city=city, bucket=(lo, hi), direction="YES", token_id=yes_tok,
                p_model=round(p_m, 4), ask=ask_yes, edge=round(band_ev, 4),
                confidence=round(p_band, 4), stake=self.stake_min,   # STAGED: min stake
                regime=regime, phase=phase, metar_age_s=round(metar_age, 1),
                kalman_var=round(p_var, 4), kriging_pct=round(kriging_pct, 3),
                p_gev=0.0, drift_bias=0.0))
        return sigs

    def _struct_band_allocate(self, city, entries, clob_books, bankroll, held_k, phase,
                              regime, metar_age, p_var, kriging_pct):
        """STRUCTURAL BAND (badatmath copy, 2026-06-09) — the over-dispersion harvest.

        Buys a contiguous YES band centered on the MARKET mode (highest-ask interior
        bucket), one bell-weighted MAKER bid per leg, held to resolution. STRUCTURAL:
        it does NOT use our model prob to fire — only the market price ladder. The edge
        is that the market over-disperses the daily high (true σ≈1.3°), so the near-mode
        band collectively costs < its hit-probability. Validated n=3583, May+June.

        Differs from _band_allocate (model-driven, mode±1, taker): wider (±BAND_WING),
        bell-$ weighted, MAKER-quoted (he is 97.6% maker), price-gated [PX_MIN,PX_CEIL].
        Fires only when Σ band ask < BAND_SUM_MAX (a genuine sub-$1 band). σ skill-gate
        kept (Klaus improvement: skip coin-flip cities — he doesn't, it's free safety).
        BAND_LIVE=False ⇒ logs the exact quotes it WOULD post (no capital); True ⇒ emits
        maker-intent Signals for the weather_arb maker executor.
        """
        import json as _json, time as _time
        from datetime import datetime as _dt, timezone as _tz
        from pathlib import Path as _Path

        def _log(reason, **kw):
            try:
                _d = _Path("logs/shadow/hot") / _dt.now(_tz.utc).date().isoformat()
                _d.mkdir(parents=True, exist_ok=True)
                with (_d / "band_struct.jsonl").open("a") as _f:
                    _f.write(_json.dumps({"ts": _time.time(), "city": city,
                                          "reason": reason, **kw}) + "\n")
            except Exception:
                pass

        # ── window: pre-peak → peak only (the band is decided around the diurnal peak) ──
        h = _local_hour(city)
        if h is None or not (11 <= h <= BAND_HOUR_MAX) or phase == "POST_PEAK":
            return []
        # ── skill gate: skip high-σ coin-flip cities (free improvement over badatmath) ──
        sig_city = _peak_sigma_for(self._peak_calib, city, _current_month())
        if sig_city > YES_SIGMA_CUTOFF:
            return []

        # ── liquid interior buckets whose ASK is in the harvest band [PX_MIN, PX_CEIL] ──
        valid = []
        for lo, hi, yt, nt, p_m, ay, an in entries:
            if lo <= -900.0 or hi >= 900.0:          # interior only (no open-ended tails)
                continue
            if ay is None or not (BAND_PX_MIN <= ay <= BAND_PX_CEIL):
                continue
            bk = clob_books.get(yt) or {}
            bid = bk.get("best_bid"); depth = bk.get("usd_depth")
            if depth is not None and depth < self.stake_min:
                continue
            valid.append((lo, hi, yt, nt, p_m, ay, an, bid))
        if len(valid) < BAND_MIN_LEGS:
            _log("no_band", local_h=h, n_valid=len(valid))
            return []

        # ── MODE-CONTAINMENT (2026-06-10): same gate as the multiday path — if the
        # GLOBAL interior mode asks above PX_CEIL the ladder has CONVERGED; the
        # in-window "band" is flanks around a hole (dist-1 −96% without dist-0
        # +432%). The valid-list ≤PX_CEIL filter is blind to it. This path lacked
        # the gate (state log 06-10 00:05 said "both paths" — it wasn't here).
        _gmode = max((e[5] for e in entries
                      if e[0] > -900.0 and e[1] < 900.0 and e[5] is not None),
                     default=0.0)
        if _gmode > BAND_PX_CEIL:
            _log("converged", local_h=h, mode_ask=round(_gmode, 3))
            return []

        # ── market mode = the dearest interior bucket we may quote; band = mode ± WING ──
        valid.sort(key=lambda e: e[0])               # by temperature
        mi = max(range(len(valid)), key=lambda i: valid[i][5])   # max ASK = market mode
        band = [valid[i] for i in range(mi - BAND_WING, mi + BAND_WING + 1)
                if 0 <= i < len(valid)]
        sum_ask = sum(e[5] for e in band)
        if len(band) < BAND_MIN_LEGS or sum_ask >= BAND_SUM_MAX:
            _log("sum_gate", local_h=h, n=len(band), sum_ask=round(sum_ask, 3))
            return []

        # ── per-leg MAKER quote + bell-weighted stake (mode temperature = valid[mi][0]) ──
        quotes = []
        for lo, hi, yt, nt, p_m, ay, an, bid in band:
            off = abs(int(round((lo - valid[mi][0]))))          # |offset from mode| in legs
            w = BAND_BELL[off] if off < len(BAND_BELL) else 0.0
            if w <= 0.0:
                continue
            stake = round(BAND_BASE_STAKE * w, 2)
            # maker bid: join the book just inside the spread, never cross the ask
            b = bid if (bid is not None and bid > 0) else max(0.01, ay - 0.02)
            q = round(min(ay - 0.01, b + BAND_QUOTE_FRAC * max(0.0, ay - b)), 3)
            q = max(0.01, q)
            quotes.append((lo, hi, yt, ay, q, stake, off))

        # budget cap: scale the band's quotes to the per-city-day budget (net of held)
        city_budget = max(0.0, min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX) - held_k)
        want = sum(q[5] for q in quotes)
        scale = 1.0 if (want <= city_budget or want <= 0) else city_budget / want
        quotes = [(lo, hi, yt, ay, q, round(max(self.stake_min, st * scale), 2), off)
                  for (lo, hi, yt, ay, q, st, off) in quotes]

        _log("fire", local_h=h, sig_city=round(sig_city, 3), mode_lo=valid[mi][0],
             sum_ask=round(sum_ask, 3), live=BAND_LIVE, budget=round(city_budget, 2),
             quotes=[{"lo": lo, "hi": hi, "ask": round(ay, 3), "bid_quote": q,
                      "stake": st, "off": off} for (lo, hi, yt, ay, q, st, off) in quotes])

        if not BAND_LIVE:
            return []                                # shadow: logged the would-post quotes only

        sigs = []
        for lo, hi, yt, ay, q, st, off in quotes:
            sigs.append(Signal(
                city=city, bucket=(lo, hi), direction="YES", token_id=yt,
                p_model=0.0, ask=ay,
                edge=round(1.0 / sum_ask - 1.0, 4), confidence=round(sum_ask, 4),
                stake=st, regime=regime, phase=phase, metar_age_s=round(metar_age, 1),
                kalman_var=round(p_var, 4), kriging_pct=round(kriging_pct, 3),
                p_gev=0.0, drift_bias=0.0, maker=True, quote_price=q))
        return sigs

    def _lp_allocate_city(
        self,
        city:        str,
        buckets_raw: list,    # [(lo, hi, yes_tok, no_tok), ...]
        probs:       dict,    # {(lo,hi): p_model}
        clob_books:  dict,
        confidence:  float,
        phase:       str,
        bankroll:    float,
        metar_age:   float,
        p_var:       float,
        kriging_pct: float,
        regime:      str,
        held_k:      float = 0.0,    # Tier-4: capital ($) already deployed in this city today
        cal_probs:   Optional[dict] = None,   # isotonic-recalibrated per-bucket win-prob (YES/NO sizing)
    ) -> list[Signal]:
        """
        Kelly allocation for a city's active bucket candidates.

        YES bets on different buckets are mutually exclusive (only one can win),
        so they use horse-race Kelly:
            x_i = s × (Q × p_c_i − ask_i)
            Q = (1 − Σask) / p_neither,  s = W − T,
            T = W × (Σp_c − Σask/Q),  p_c_i = p_i × confidence
        Collapses to standard Kelly for a single YES candidate.

        NO bets can win simultaneously (all NOs win except the one whose bucket
        contains the actual max), so they use independent Kelly with the win
        probability p_win = (1 − p_model) × confidence.

        Both pools share the city budget; stakes are scaled proportionally if
        their sum exceeds it.

        Also detects pure neg-risk arb: Σ YES ask < NEG_RISK_ARB_THR means
        buying all YES tokens guarantees profit regardless of which bucket wins.
        """
        # ── Build candidates ──────────────────────────────────────────────────
        entries = []
        for lo, hi, yes_tok, no_tok in buckets_raw:
            p_m      = probs.get((lo, hi), 0.0)
            ask_yes  = _book_ask(clob_books, yes_tok)
            ask_no   = _book_ask(clob_books, no_tok)
            entries.append((lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no))

        if not entries:
            return []

        # Forward-ladder book snapshot (write-only, throttled) — capacity backtest data.
        # Pass running_max + center so the next-day-edge detector can exclude
        # floor-driven p_cal flips (lockout advances) and fire only on genuine
        # forecast/center updates (the actual thesis).
        _cs_lad = self._cities.get(city)
        _log_ladder_book(city, entries, clob_books, phase, regime, cal_probs,
                         running_max=(_cs_lad.running_max if _cs_lad is not None else None),
                         center=(_cs_lad.ps_center_last if _cs_lad is not None else None))

        # ── Consistency gate ─────────────────────────────────────────────────
        total_p = sum(p for *_, p, _, _ in entries)
        if total_p > PROB_SUM_MAX:
            logger.debug("[STWA] LP %s: prob sum %.2f > %.2f — MC bug, skip", city, total_p, PROB_SUM_MAX)
            return []

        # ── BAND MODE: directional-YES band governs the DIRECTIONAL slot only.
        # NEG_RISK_ARB (the calibration-free YES + NO neg-risk faces below) runs
        # FIRST and is NOT bypassed — band only replaces the regular Kelly ladder.
        # The band hand-off happens after the arb blocks (search BAND_MODE hand-off).
        # ─────────────────────────────────────────────────────────────────────

        # ── Neg-risk arb ─────────────────────────────────────────────────────
        # If Σ YES ask < NEG_RISK_ARB_THR, buying k shares of every YES token
        # gives guaranteed profit IF the buckets are exhaustive of the outcome
        # space: payoff = k × (1 − Σask) regardless of which bucket resolves.
        #
        # Exhaustivity gate (P0-A): require Σ p_model ≥ EXHAUSTIVITY before
        # firing — proves the buckets we see cover the outcome space. If a
        # tail bucket is missing, the model still assigns it positive p, so
        # Σ p_model on visible-only buckets falls below 0.95.
        #
        # Equal-shares preservation (P0-C): the arb math requires the SAME k
        # for every bucket. Min-order constraints ($1 maker, 5 shares, 2¢
        # ticks) impose a per-bucket lower bound. We raise the global k so
        # every bucket clears its constraint; if the resulting total cost
        # exceeds BUDGET_MUL × city_budget we abort instead of cliping.
        MIN_ORDER_USD = 1.05   # CLOB $1 maker min + small buffer
        MIN_ORDER_SHARES = 5.05

        valid_yes_asks = [a for *_, a, _ in entries if a is not None and 0 < a < 1]
        # Leg-count-dependent margin: multi-leg arbs carry partial-fill risk, so
        # require a wider Σask margin as the number of legs grows.
        _arb_thr = (NEG_RISK_ARB_THR_MULTILEG
                    if len(valid_yes_asks) >= NEG_RISK_ARB_MULTILEG_N
                    else NEG_RISK_ARB_THR)
        if STWA_NEG_RISK_ENABLED and len(valid_yes_asks) == len(entries) and sum(valid_yes_asks) < _arb_thr:
            sum_ask  = sum(valid_yes_asks)
            sum_p    = sum(p for *_, p, _, _ in entries)
            arb_edge = 1.0 - sum_ask
            city_budget = max(0.0, min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX) - held_k)  # Tier-4: remaining day budget net of deployed capital

            # Exhaustivity gate
            if sum_p < NEG_RISK_ARB_EXHAUSTIVITY:
                logger.debug("[STWA] NEG_RISK_ARB %s: NOT exhaustive (Σp_model=%.3f < %.3f) — skip arb",
                             city, sum_p, NEG_RISK_ARB_EXHAUSTIVITY)
            else:
                # Equal-shares k: must satisfy min-order on EVERY bucket simultaneously
                k_budget = city_budget / sum_ask
                k_min_share = MIN_ORDER_SHARES
                k_min_dollar = max(MIN_ORDER_USD / max(a, 1e-4)
                                   for *_, a, _ in entries if a and 0 < a < 1)
                k_feasible = max(k_min_share, k_min_dollar)

                # Use the larger of budget-implied and feasibility-implied k
                k = max(k_budget, k_feasible)

                # Depth check: clamp k so no bucket order exceeds available book depth
                for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                    if not (ask_yes and 0 < ask_yes < 1):
                        continue
                    depth = (clob_books.get(yes_tok) or {}).get("usd_depth") or 0.0
                    if depth > 0 and k * ask_yes > depth:
                        k = depth / ask_yes

                # After all clamps: verify min-order still satisfied on cheapest bucket
                # If depth clamped k below feasibility, the arb is infeasible.
                if k < k_feasible:
                    logger.debug("[STWA] NEG_RISK_ARB %s: depth clamped k=%.1f below feasibility=%.1f — skip",
                                 city, k, k_feasible)
                elif k * sum_ask > city_budget * NEG_RISK_ARB_BUDGET_MUL:
                    logger.info("[STWA] NEG_RISK_ARB %s: feasible cost $%.2f exceeds %.1fx budget $%.2f — skip",
                                city, k * sum_ask, NEG_RISK_ARB_BUDGET_MUL, city_budget)
                else:
                    actual_cost = k * sum_ask
                    actual_payoff = k * 1.0
                    actual_edge = (actual_payoff - actual_cost) / actual_cost if actual_cost > 0 else 0.0
                    logger.info("[STWA] NEG_RISK_ARB %s: sum_ask=%.3f Σp=%.3f k=%.1f cost=$%.2f payoff=$%.2f edge=%.1f%%",
                                city, sum_ask, sum_p, k, actual_cost, actual_payoff, actual_edge * 100)
                    arb_signals = []
                    for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                        if ask_yes is None or not (0 < ask_yes < 1):
                            continue
                        # Equal-shares: same k for every bucket — DON'T clip.
                        stake = round(k * ask_yes, 2)
                        # Cap individual stake at stake_max ($20) as last-resort safety
                        # but if any bucket needs > stake_max we'd already have aborted above.
                        stake = min(stake, self.stake_max)
                        _cs_local = self._cities.get(city)
                        _p_gev = float(_cs_local.gev_probs_last.get((lo, hi), 0.0)) if _cs_local else 0.0
                        _drift_h_local = 0.0
                        if _cs_local and _cs_local.drift_bias:
                            _peak_h = int((time.time() % 86400) / 3600)  # not exact peak; approximation
                            _drift_h_local = float(_cs_local.drift_bias.get(_peak_h, 0.0))
                        arb_signals.append(Signal(
                            city=city, bucket=(lo, hi), direction="YES",
                            token_id=yes_tok, p_model=round(p_m, 4),
                            ask=ask_yes, edge=round(arb_edge, 4),
                            confidence=1.0, stake=stake,
                            regime=regime, phase=phase,
                            metar_age_s=round(metar_age, 1),
                            kalman_var=round(p_var, 4),
                            kriging_pct=round(kriging_pct, 3),
                            p_gev=round(_p_gev, 4),
                            drift_bias=round(_drift_h_local, 3),
                        ))
                    if arb_signals:
                        return arb_signals

        # ── Per-bucket: pick the positive-edge side ──────────────────────────
        # Use composite gate: edge > EDGE_MIN (risk-of-ruin safety) AND
        # Kelly fraction f* > KELLY_F_MIN (sizing-aware threshold). The
        # Kelly gate scales naturally: high-ask sells need much less edge to
        # be efficient than low-ask longshots.
        def _kelly_f(p_win: float, ask: float, conf: float) -> float:
            """Confidence-adjusted Kelly fraction. Returns 0 if non-positive."""
            if ask is None or ask <= 0 or ask >= 1:
                return 0.0
            p_c = p_win * conf
            b = (1.0 / ask) - 1.0
            f = (p_c * b - (1.0 - p_c)) / b
            return max(0.0, f)

        # ── Face 2: buy-all-NO neg-risk arb (model-free, calibration-free → no n-gate) ──
        # Dual of the YES arb on the SAME coherence polytope: exactly one bucket
        # wins ⇒ the other N−1 NO tokens pay 1. Buy equal k shares of every NO ⇒
        # guaranteed profit when Σ NO ask < N−1. Guaranteed on ANY subset (a winner
        # outside the visible buckets only ADDS a payoff), so no exhaustivity gate is
        # needed. Buys NO on DISTINCT buckets — no same-bucket opposite-side conflict.
        # Same min-order / depth / budget clamps as the YES arb. Fires only when the
        # book underprices the NO side — a polytope face the Σ-YES<1 scan never sees.
        valid_no_asks = [ask_no for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries
                         if ask_no is not None and 0 < ask_no < 1]
        n_legs = len(entries)
        if STWA_NEG_RISK_ENABLED and len(valid_no_asks) == n_legs and n_legs >= 2 and sum(valid_no_asks) < float(n_legs - 1):
            sum_ask_no  = sum(valid_no_asks)
            payoff_no   = float(n_legs - 1)
            city_budget = max(0.0, min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX) - held_k)
            k_feasible  = max(MIN_ORDER_SHARES,
                              max(MIN_ORDER_USD / max(a, 1e-4) for a in valid_no_asks))
            k = max(city_budget / sum_ask_no if sum_ask_no > 0 else 0.0, k_feasible)
            # Depth clamp: no NO leg may exceed its book depth.
            for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                depth = (clob_books.get(no_tok) or {}).get("usd_depth") or 0.0
                if depth > 0 and k * ask_no > depth:
                    k = depth / ask_no
            if k < k_feasible:
                logger.debug("[STWA] NO_RISK_ARB %s: depth clamped k=%.1f < feasibility=%.1f — skip",
                             city, k, k_feasible)
            elif k * sum_ask_no > city_budget * NEG_RISK_ARB_BUDGET_MUL:
                logger.info("[STWA] NO_RISK_ARB %s: cost $%.2f > %.1fx budget $%.2f — skip",
                            city, k * sum_ask_no, NEG_RISK_ARB_BUDGET_MUL, city_budget)
            else:
                arb_edge_no = round((payoff_no - sum_ask_no) / sum_ask_no, 4)
                logger.info("[STWA] NO_RISK_ARB %s: Σno_ask=%.3f N=%d k=%.1f cost=$%.2f payoff=$%.2f edge=%.1f%%",
                            city, sum_ask_no, n_legs, k, k * sum_ask_no, k * payoff_no, arb_edge_no * 100)
                no_arb_signals = []
                for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                    no_arb_signals.append(Signal(
                        city=city, bucket=(lo, hi), direction="NO",
                        token_id=no_tok, p_model=round(p_m, 4),
                        ask=ask_no, edge=arb_edge_no, confidence=1.0,
                        stake=min(round(k * ask_no, 2), self.stake_max),
                        regime=regime, phase=phase,
                        metar_age_s=round(metar_age, 1), kalman_var=round(p_var, 4),
                        kriging_pct=round(kriging_pct, 3), p_gev=0.0, drift_bias=0.0,
                    ))
                if no_arb_signals:
                    return no_arb_signals

        # ── BAND_MODE hand-off: arb did not fire → band governs the directional
        # slot (in place of the regular Kelly ladder). Under BAND_SHADOW it logs
        # the eval and returns []; no directional capital is deployed. ──
        if STWA_STRUCT_BAND:
            try:
                _band_sigs = self._struct_band_allocate(city, entries, clob_books, bankroll,
                                                        held_k, phase, regime, metar_age,
                                                        p_var, kriging_pct)
            except Exception:
                logger.debug("[STRUCT-BAND] alloc failed %s", city, exc_info=True)
                _band_sigs = []
            if BAND_LIVE and BAND_SAMEDAY_LIVE:
                return _band_sigs          # band governs the directional slot (YES); M1β-NO + arb still run
            # shadow: _struct_band_allocate logged its would-post quotes; fall through so
            # the current live regular-NO ladder keeps running until we flip BAND_LIVE.
        if STWA_BAND_MODE:
            return self._band_allocate(city, entries, clob_books, bankroll, held_k,
                                       phase, regime, metar_age, p_var, kriging_pct)

        candidates = []
        for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
            # Use isotonic-RECALIBRATED win-prob for edge + Kelly (raw p_m stays
            # for the arb Σ-exhaustivity gate above). This is what prevents YES
            # from over-paying on the raw overconfident high-p region (g squashes
            # 0.95→0.40, so YES only fires where the recalibrated edge is real).
            p_use = float((cal_probs or {}).get((lo, hi), p_m))
            edge_yes = (p_use - ask_yes) if ask_yes is not None else -1.0
            edge_no  = ((1.0 - p_use) - ask_no) if ask_no is not None else -1.0
            f_yes = _kelly_f(p_use, ask_yes, confidence) if ask_yes else 0.0
            f_no  = _kelly_f(1.0 - p_use, ask_no, confidence) if ask_no else 0.0

            # Phase gate. The directional YES ladder is PRE_PEAK ONLY (user
            # directive 2026-06-01): AT_PEAK and POST_PEAK both underperformed
            # on live resolution — the forecast edge is most decayed there and
            # lockout dynamics dominate, so the only edge in the at/post-peak
            # window is the M1β lockout-NO harvest (weather_arb), NOT this ladder.
            # Measured (110 resolved, Gamma join 2026-05-31): post-peak YES =
            # 13% WR / -$36 (76% of all STWA loss). Requiring strict PRE_PEAK
            # also sidesteps the plateau guard that relabels POST_PEAK→AT_PEAK.
            # NEG_RISK_ARB is exempt — it returns before this loop and is a
            # timing-independent guaranteed-profit edge.
            _yes_phase_ok = phase == "PRE_PEAK"          # YES: pre-peak only
            _no_phase_ok  = phase != "POST_PEAK"         # (NO path disabled below)
            # PRICE_FLOOR: only ever buy the FAVORITE side at a fillable price.
            # Every dollar of our directional loss lived below 0.50 (fee-death /
            # longshot zone); the +EV harvest is entirely at ask ≥ 0.50.
            _yes_price_ok = ask_yes is not None and ask_yes >= PRICE_FLOOR
            # NO: band-gated to the only +EV slice (see NO_FLOOR/NO_CEIL note).
            _no_price_ok  = ask_no  is not None and NO_FLOOR <= ask_no <= NO_CEIL
            yes_ok = (STWA_REGULAR_YES_ENABLED and _yes_phase_ok and _yes_price_ok
                      and edge_yes > EDGE_MIN and f_yes > KELLY_F_MIN)
            no_ok  = (STWA_REGULAR_NO_ENABLED and _no_phase_ok and _no_price_ok
                      and edge_no > EDGE_MIN and f_no > KELLY_F_MIN)

            if yes_ok and no_ok:
                # Both sides positive ↔ neg-risk within this bucket; pick higher Kelly
                if f_yes >= f_no:
                    candidates.append(("YES", yes_tok, p_use, ask_yes, edge_yes, (lo, hi)))
                else:
                    candidates.append(("NO", no_tok, p_use, ask_no, edge_no, (lo, hi)))
            elif yes_ok:
                candidates.append(("YES", yes_tok, p_use, ask_yes, edge_yes, (lo, hi)))
            elif no_ok:
                candidates.append(("NO", no_tok, p_use, ask_no, edge_no, (lo, hi)))

        # ── Per-city YES diagnostic (logged for EVERY PRE_PEAK city reaching
        # allocation, even with 0 candidates, so we can see exactly why YES does
        # or doesn't fire: width gate, best available edge, budget). s_our/s_book
        # are reused by the width gate below. ─────────────────────────────────
        _cal_w = self._peak_calib.get(city) or self._peak_calib.get("_pooled", {})
        s_our  = _peak_sigma_for(self._peak_calib, city, _current_month())
        s_book = _book_implied_sigma(entries)
        _width_ok = (s_book is not None and s_book > WIDTH_GATE_MARGIN * s_our)
        _best_yes_edge = max(
            ((float((cal_probs or {}).get((lo, hi), p_m)) - a)
             for lo, hi, _yt, _nt, p_m, a, _an in entries if a is not None),
            default=-1.0)
        _n_yes_cand = sum(1 for c in candidates if c[0] == "YES")
        if phase == "PRE_PEAK":
            _bud = max(0.0, min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX) - held_k)
            logger.info(
                "[STWA] yes-eval %s phase=PRE_PEAK s_our=%.2f s_book=%s width_ok=%s "
                "best_yes_edge=%+.3f n_yes_cand=%d yes_enabled=%s budget=$%.2f",
                city, s_our, (f"{s_book:.2f}" if s_book is not None else "NA"),
                _width_ok, _best_yes_edge, _n_yes_cand,
                STWA_REGULAR_YES_ENABLED, _bud)

        # ── MAKER SHADOW recorder (log-only, no capital) ──────────────────────
        # Per bucket: our calibrated fair vs the live two-sided book + the quote
        # we WOULD post. Runs for every bucket every scan (independent of the
        # candidate early-return below). locked=(p_m==0 ⇒ below running-max floor):
        # there the safe maker action is SELL YES (offer) — adverse-selection-free.
        if MAKER_SHADOW_ENABLED and entries:
            try:
                _mk_dir = (Path(__file__).parent.parent / "logs" / "shadow"
                           / "hot" / time.strftime("%Y-%m-%d", time.gmtime()))
                _mk_dir.mkdir(parents=True, exist_ok=True)
                _now = time.time()
                _cal = cal_probs or {}
                with (_mk_dir / "maker_shadow.jsonl").open("a") as _mf:
                    for _lo, _hi, _yt, _nt, _pm, _ay, _an in entries:
                        _fair = float(_cal.get((_lo, _hi), _pm))
                        _yb = clob_books.get(_yt) or {}
                        _nb = clob_books.get(_nt) or {}
                        _bid = _yb.get("best_bid"); _ask = _yb.get("best_ask")
                        _mf.write(json.dumps({
                            "ts": _now, "city": city, "phase": phase,
                            "lo": _lo, "hi": _hi, "yes_tok": _yt, "no_tok": _nt,
                            "fair": round(_fair, 4),
                            "yes_bid": _bid, "yes_ask": _ask,
                            "yes_depth_usd": _yb.get("usd_depth"),
                            "no_bid": _nb.get("best_bid"), "no_ask": _nb.get("best_ask"),
                            "no_depth_usd": _nb.get("usd_depth"),
                            "q_bid": round(max(0.01, _fair - MAKER_HALF_SPREAD), 4),
                            "q_ask": round(min(0.99, _fair + MAKER_HALF_SPREAD), 4),
                            "spread": (round(_ask - _bid, 4)
                                       if (_bid is not None and _ask is not None) else None),
                            "locked": (_pm == 0.0),
                        }) + "\n")
            except Exception:
                logger.debug("[STWA] maker_shadow log fail", exc_info=True)

        # ── FADE SHADOW (forward, no-look-ahead) ──────────────────────────────
        # Post-peak the resolved high ≈ hourly running_max. The bin(s) just ABOVE
        # it are the fade targets (sub-hourly peak pokes in, book overprices ~22¢,
        # but they resolve NO ~99%). Log the LIVE NO ask now; join resolution by
        # no_tok offline → forward fade WR/EV (no look-ahead — all fields real-time).
        _cs_fade = self._cities.get(city)
        if (FADE_SHADOW_ENABLED and entries and phase in ("AT_PEAK", "POST_PEAK")
                and _cs_fade is not None and _cs_fade.running_max is not None):
            try:
                _rm = float(_cs_fade.running_max)
                _above = sorted(
                    [(lo, hi, yt, nt, pm, ay, an) for (lo, hi, yt, nt, pm, ay, an) in entries
                     if lo >= _rm], key=lambda e: e[0])[:3]
                if _above:
                    _fd_dir = (Path(__file__).parent.parent / "logs" / "shadow"
                               / "hot" / time.strftime("%Y-%m-%d", time.gmtime()))
                    _fd_dir.mkdir(parents=True, exist_ok=True)
                    _cal = cal_probs or {}
                    _rec = {
                        "ts": time.time(), "city": city, "phase": phase,
                        "regime": regime, "running_max_c": round(_rm, 2),
                        "rm_age_s": round(time.time() - _cs_fade.running_max_ts, 0),
                        "fade_bins": [{
                            "lo": lo, "hi": hi, "no_tok": nt,
                            "no_ask": (clob_books.get(nt) or {}).get("best_ask"),
                            "no_bid": (clob_books.get(nt) or {}).get("best_bid"),
                            "no_depth_usd": (clob_books.get(nt) or {}).get("usd_depth"),
                            "yes_ask": (clob_books.get(yt) or {}).get("best_ask"),
                            "fair": round(float(_cal.get((lo, hi), pm)), 4),
                            "rank_above": i,  # 0 = bin immediately above running_max (prime)
                        } for i, (lo, hi, yt, nt, pm, ay, an) in enumerate(_above)],
                    }
                    with (_fd_dir / "fade_shadow.jsonl").open("a") as _ff:
                        _ff.write(json.dumps(_rec) + "\n")
            except Exception:
                logger.debug("[STWA] fade_shadow log fail", exc_info=True)

        if not candidates:
            return []

        # ── Split by direction ────────────────────────────────────────────────
        city_budget = max(0.0, min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX) - held_k)  # Tier-4: remaining day budget net of deployed capital
        yes_cands = [c for c in candidates if c[0] == "YES"]
        no_cands  = [c for c in candidates if c[0] == "NO"]

        # ── Width gate (directional YES ladder only) ─────────────────────────
        # A YES ladder carries edge only when the book-implied σ (s_M) is wider
        # than our per-city pricer σ (s_our) by more than the overround — i.e.
        # our forecast is tighter/better-located than the book. If s_M ≤
        # WIDTH_GATE_MARGIN·s_our we have no width advantage (Regime-3), so the
        # ladder would just pay vig across legs: drop the YES pool. NEG_RISK_ARB
        # (returned earlier) and the NO pool (lockout harvest) are unaffected.
        if yes_cands and not _width_ok:   # _width_ok / s_our / s_book computed above
            logger.debug("[STWA] width-gate %s: s_book=%s s_our=%.2f (need > %.2f×) — drop YES ladder",
                         city, f"{s_book:.2f}" if s_book is not None else "NA",
                         s_our, WIDTH_GATE_MARGIN)
            yes_cands = []

        # ── Per-city confidence: σ-cutoff + stake weight ──────────────────────
        # Cities whose forecast σ is too wide can't clear even the mode±1 band
        # (P_band < 70% above σ≈1.40) → no directional YES there. Otherwise weight
        # the YES stake by accuracy: w_city = clip(σ_ref/s_our). See constants.
        w_city = 1.0
        if YES_PERCITY_KELLY_ENABLED:
            if yes_cands and s_our > YES_SIGMA_CUTOFF:
                logger.debug("[STWA] σ-cutoff %s: s_our=%.2f > %.2f — drop YES (band <70%% WR)",
                             city, s_our, YES_SIGMA_CUTOFF)
                yes_cands = []
            else:
                w_city = min(YES_WCITY_MAX, max(YES_WCITY_MIN, YES_SIGMA_REF / max(s_our, 1e-6)))

        # ── YES pool: horse-race Kelly ────────────────────────────────────────
        yes_pairs: list[tuple] = []   # (candidate-tuple, raw_stake)
        if yes_cands:
            working = [(d, t, p, a, e, b, p * confidence)
                       for d, t, p, a, e, b in yes_cands]
            active = working
            raw_stakes: list[float] = []
            for _ in range(len(working)):
                p_sum = sum(w[6] for w in active)
                a_sum = sum(w[3] for w in active)
                p3    = max(1.0 - p_sum, 1e-9)
                Q     = (1.0 - a_sum) / p3
                T     = bankroll * max(0.0, p_sum - a_sum / Q)
                s     = bankroll - T
                raw_stakes = [s * (Q * w[6] - w[3]) for w in active]
                if all(x > 0 for x in raw_stakes):
                    break
                active = [w for w, x in zip(active, raw_stakes) if x > 0]
                if not active:
                    break
            for w, x in zip(active, raw_stakes):
                # Per-city confidence weight: concentrate YES capital in low-σ
                # (accurate) cities, shrink it in loose ones. w_city=1.0 when the
                # weighting is disabled.
                yes_pairs.append((w[:6], x * self.kelly_frac * w_city))

        # ── NO pool: independent Kelly (NOs can win simultaneously) ──────────
        no_pairs: list[tuple] = []
        for cand in no_cands:
            d, t, p_m, ask, edge, bucket = cand
            raw = _kelly_stake(1.0 - p_m, ask, confidence, bankroll,
                               self.kelly_frac, self.stake_min, self.stake_max)
            no_pairs.append((cand, raw))

        # ── Combine and scale to city_budget ─────────────────────────────────
        all_pairs = yes_pairs + no_pairs
        total = sum(r for _, r in all_pairs)
        budget_ratio = min(1.0, city_budget / total) if total > 0 else 0.0

        signals = []
        _cs_local = self._cities.get(city)
        _drift_h_local = 0.0
        if _cs_local and _cs_local.drift_bias:
            _peak_h = int((time.time() % 86400) / 3600)
            _drift_h_local = float(_cs_local.drift_bias.get(_peak_h, 0.0))
        for (direction, tok, p_m, ask, edge, bucket), raw_stake in all_pairs:
            alloc = float(np.clip(raw_stake * budget_ratio,
                                  self.stake_min, self.stake_max))
            if alloc < self.stake_min:
                continue
            # YES-favorite is unproven on resolved data (n=5) → stage at min-stake
            # to accrue clean post-fix n without betting it. NO-favorite is proven.
            if direction == "YES" and YES_STAGE_MIN_STAKE:
                alloc = self.stake_min
            _p_gev = float(_cs_local.gev_probs_last.get(bucket, 0.0)) if _cs_local else 0.0
            signals.append(Signal(
                city=city, bucket=bucket, direction=direction,
                token_id=tok, p_model=round(p_m, 4),
                ask=ask, edge=round(edge, 4),
                confidence=round(confidence, 3), stake=round(alloc, 2),
                regime=regime, phase=phase,
                metar_age_s=round(metar_age, 1),
                kalman_var=round(p_var, 4),
                kriging_pct=round(kriging_pct, 3),
                p_gev=round(_p_gev, 4),
                drift_bias=round(_drift_h_local, 3),
            ))

        return signals

    def get_signals(
        self,
        clob_books:  dict[str, dict],   # token_id → {"best_ask": float, "best_bid": float, "usd_depth": float}
        bucket_map:  dict[str, list],   # city → [(lo_c, hi_c, yes_token_id, no_token_id), ...]
        t_close_map: dict[str, float],  # city → unix ts of market close
        bankroll:    Optional[float]    = None,
        t_now:       Optional[float]    = None,
        held_k_by_city: Optional[dict]  = None,   # Tier-4: $ deployed per city today
    ) -> list[Signal]:
        """
        For each active city, compute bucket probabilities and return signals
        where |p_model - ask| > EDGE_MIN with sufficient confidence.
        """
        if not self._params:
            return []

        signals: list[Signal] = []
        self._last_pricer_rows = []   # per-bucket MC/GEV/PA comparison for calibration log
        now = t_now or time.time()
        br  = bankroll or self.bankroll

        _g = {"no_bucket": 0, "t_close": 0, "regime": 0, "fresh": 0, "mc": 0, "conf": 0, "edge": 0, "ok": 0}

        for city, cs in self._cities.items():
            if city in self._suspended:
                continue
            if city not in bucket_map or city not in t_close_map:
                _g["no_bucket"] += 1
                continue

            t_close = t_close_map[city]
            if t_close <= now + MIN_TIME_REM:
                _g["t_close"] += 1
                continue

            # Regime gate
            if cs.regime not in REGIME_FIRE:
                _g["regime"] += 1
                continue

            # Freshness gate
            metar_age = now - cs.last_obs_ts
            if cs.last_obs_ts <= 0 or metar_age > METAR_MAX_AGE:
                _g["fresh"] += 1
                continue

            buckets_raw = bucket_map[city]   # [(lo, hi, yes_tok, no_tok), ...]
            buckets     = [(lo, hi) for lo, hi, _, _ in buckets_raw]

            # Phase must be computed before MC so sigma damping is applied correctly
            phase = _phase(cs, t_close_map[city], now)
            # Override: if running_max was updated within the last hour AND the
            # current temperature is still near the peak (decline < 0.5°C), the
            # day is still active — POST_PEAK suppression (×0.15) would be wrong.
            # Without the decline guard, a falling temperature that peaked recently
            # would still get AT_PEAK sigma, inflating high-bucket probabilities.
            if phase == "POST_PEAK" and (now - cs.running_max_ts) < 3600:
                # Only override if current temperature is still near the peak.
                # A decline ≥ 0.5°C below running_max means the day has peaked;
                # keep POST_PEAK so sigma suppression correctly limits path spread.
                temp_decline = ((cs.running_max or 0.0) - cs.last_temp
                                if math.isfinite(cs.last_temp)
                                else 0.0)
                if temp_decline < 0.5:
                    phase = "AT_PEAK"

            try:
                probs = self._forecast_bucket_probs(city, now, t_close, buckets, phase=phase)
            except Exception as e:
                logger.debug("[STWA] MC error %s: %s", city, e)
                _g["mc"] += 1
                continue

            if not probs:
                _g["mc"] += 1
                continue

            # Per-bucket pricer comparison for calibration validation (shadow).
            # Logged for EVERY priced bucket regardless of which signals fire,
            # so the suspended-YES side still accumulates calibration data.
            _mc_last  = getattr(cs, "mc_probs_last", {}) or {}
            _gev_last = getattr(cs, "gev_probs_last", {}) or {}
            _pa_last  = getattr(cs, "pa_probs_last", {}) or {}
            _ps_last  = getattr(cs, "ps_probs_last", {}) or {}
            _cal_last = getattr(cs, "cal_probs_last", {}) or {}
            for (lo, hi) in buckets:
                self._last_pricer_rows.append({
                    "city": city, "lo": lo, "hi": hi,
                    "p_mc":  round(float(_mc_last.get((lo, hi), 0.0)), 5),
                    "p_gev": round(float(_gev_last.get((lo, hi), 0.0)), 5),
                    "p_pa":  round(float(_pa_last.get((lo, hi), 0.0)), 5),
                    "p_ps":  round(float(_ps_last.get((lo, hi), 0.0)), 5),
                    "p_cal": round(float(_cal_last.get((lo, hi), 0.0)), 5),
                    "running_max": cs.running_max,
                    "t_close": t_close, "phase": phase,
                })

            with self._lock:
                idx         = cs.idx
                p_var       = float(self._P[idx, idx])
                kriging_pct = getattr(cs, "kriging_pct_last", 0.0)

            # Confidence factors
            # c_age: phase-dependent freshness decay. At-peak we need tight
            # METARs (15-min decay) because a 1°C swing in 60 min changes
            # the bucket. Pre-peak the trajectory matters more than absolute
            # value so 90-min decay is fine. Post-peak the day is settled
            # so we tolerate more stale data.
            _c_age_tau_min = {"PRE_PEAK": 90.0, "AT_PEAK": 15.0, "POST_PEAK": 120.0}.get(phase, 90.0)
            c_age      = math.exp(-metar_age / 60.0 / _c_age_tau_min)
            c_variance = math.exp(-p_var / max(float(self._C[cs.idx, cs.idx]), 0.1))
            c_regime   = 1.0 if cs.regime == "SUNNY" else 0.75
            c_phase    = {"PRE_PEAK": 0.80, "AT_PEAK": 0.60, "POST_PEAK": 0.95}.get(phase, 0.80)

            confidence = c_age * c_variance * c_regime * c_phase

            if confidence < CONFIDENCE_MIN:
                logger.debug("[STWA] %s conf=%.3f (age=%.2f var=%.2f reg=%.2f ph=%.2f) p_var=%.3f C=%.3f",
                             city, confidence, c_age, c_variance, c_regime, c_phase,
                             p_var, float(self._C[cs.idx, cs.idx]))
                _g["conf"] += 1
                continue

            # LP portfolio allocation — replaces independent per-bucket Kelly.
            city_signals = self._lp_allocate_city(
                city=city, buckets_raw=buckets_raw, probs=probs,
                clob_books=clob_books, confidence=confidence,
                phase=phase, bankroll=br, metar_age=metar_age,
                p_var=p_var, kriging_pct=kriging_pct, regime=cs.regime,
                held_k=float((held_k_by_city or {}).get(city, 0.0)),
                cal_probs=getattr(cs, "cal_probs_last", None),
            )
            if not city_signals:
                _g["edge"] += 1
            signals.extend(city_signals)

        _g["ok"] = len(signals)
        logger.info("[STWA] gates: no_bkt=%d t_close=%d regime=%d fresh=%d mc=%d conf=%d edge=%d signals=%d",
                    _g["no_bucket"], _g["t_close"], _g["regime"], _g["fresh"],
                    _g["mc"], _g["conf"], _g["edge"], _g["ok"])
        return signals

    # ── Calibration ────────────────────────────────────────────────────────────

    def record_outcome(self, city: str, p_model_at_fire: float, outcome: int) -> None:
        """Call after market resolves. outcome=1 if token won, 0 if lost."""
        if city not in self._cal_log:
            self._cal_log[city] = []
        self._cal_log[city].append((p_model_at_fire, outcome))

        # Rolling ECE on last 100 resolved buckets
        log = self._cal_log[city]
        if len(log) >= 50:
            ece = _compute_ece([p for p, _ in log[-100:]], [o for _, o in log[-100:]])
            if ece > 0.10:
                self._suspended.add(city)
                logger.warning("[STWA] %s SUSPENDED — ECE=%.3f > 0.10 (last 100 trades)", city, ece)
            elif city in self._suspended and ece < 0.07:
                self._suspended.discard(city)
                logger.info("[STWA] %s re-activated — ECE=%.3f < 0.07", city, ece)

    def get_state_snapshot(self, t_now: Optional[float] = None) -> list[dict]:
        """Dump current Kalman state per city — no CLOB data needed. For shadow logging."""
        now = t_now or time.time()
        rows = []
        for city, cs in self._cities.items():
            with self._lock:
                idx   = cs.idx
                p_mu  = float(self._X[idx])
                p_var = float(self._P[idx, idx])
            st = self._params["stations"].get(city, {})
            hour_utc = int((now % 86400) / 3600)
            nwp_mu = self._get_mu(city, hour_utc)
            rows.append({
                "ts":           round(now),
                "city":         city,
                "regime":       cs.regime,
                "running_max":  cs.running_max,
                "last_obs_ts":  cs.last_obs_ts,
                "metar_age_s":  round(now - cs.last_obs_ts) if cs.last_obs_ts > 0 else None,
                "kalman_mu":    round(p_mu, 3),
                "kalman_var":   round(p_var, 4),
                # Tier-3 joint-2N-Kalman shadow vs live OLS velocity (for A/B)
                "v_hat_ols":    round(cs.v_hat, 4),
                "pv_var_ols":   round(cs.pv_var, 4),
                "x_hat_joint":  round(cs.x_hat_joint, 3),
                "v_hat_joint":  round(cs.v_hat_joint, 4),
                "pv_var_joint": round(cs.pv_var_joint, 4),
                "nwp_mu":       round(nwp_mu, 2) if math.isfinite(nwp_mu) else None,
                "suspended":    city in self._suspended,
            })
        return rows

    def get_last_obs_ts(self, city: str) -> float:
        """Return the last METAR observation timestamp for a city (0.0 if unseen)."""
        cs = self._cities.get(city)
        return cs.last_obs_ts if cs is not None else 0.0

    def calibration_summary(self) -> dict:
        out = {}
        for city, log in self._cal_log.items():
            if not log:
                continue
            probs   = [p for p, _ in log]
            outcomes= [o for _, o in log]
            out[city] = {
                "n":          len(log),
                "ece":        round(_compute_ece(probs, outcomes), 4),
                "mean_p":     round(float(np.mean(probs)), 4),
                "win_rate":   round(float(np.mean(outcomes)), 4),
                "suspended":  city in self._suspended,
            }
        return out


# ── Velocity helpers ──────────────────────────────────────────────────────────

def _ols_velocity(buf: list) -> tuple[float, float]:
    """
    OLS slope of (time_h, x_hat) buffer.  Returns (slope °C/h, slope_std °C/h).
    """
    ts = np.array([b[0] for b in buf], dtype=float)
    xs = np.array([b[1] for b in buf], dtype=float)
    t_bar = ts.mean()
    Stt   = float(((ts - t_bar) ** 2).sum())
    if Stt < 1e-9:
        return 0.0, float("inf")
    slope = float(((ts - t_bar) * xs).sum() / Stt)
    xs_fit = xs.mean() + slope * (ts - t_bar)
    rss    = float(((xs - xs_fit) ** 2).sum())
    slope_std = math.sqrt(max(rss / max(len(buf) - 2, 1) / Stt, 1e-8))
    return slope, slope_std


def _vel_step(kap: float, gamma: float, sig: float, dt_hr: float
              ) -> tuple[float, float, float, float, float, float, float]:
    """
    Exact 2D state transition for dX=V dt, dV=(−γV−κX)dt+σdW.

    Uses scipy.linalg.expm for F = exp(A·Δt) and the Van Loan (1978) method
    for the process-noise covariance Q = ∫₀^Δt exp(A·s)·B·Bᵀ·exp(Aᵀ·s) ds,
    where A=[[0,1],[−κ,−γ]] and B=[0,σ]ᵀ.

    Returns (F11,F12,F21,F22, L11,L21,L22) where L = chol(Q) lower-triangular,
    so noise_x = L11·n1, noise_v = L21·n1 + L22·n2 with n1,n2 ~ N(0,1).
    Works for all damping regimes (over-, under-, critically-damped).
    """
    from scipy.linalg import expm as _expm
    A   = np.array([[0.0, 1.0], [-kap, -gamma]])
    Q_c = np.array([[0.0, 0.0], [0.0, sig ** 2]])
    # Van Loan: build block matrix M = [[-A, Q_c], [0, Aᵀ]]
    M        = np.zeros((4, 4))
    M[:2, :2] = -A
    M[:2, 2:] = Q_c
    M[2:, 2:] = A.T
    eM  = _expm(M * dt_hr)
    F   = _expm(A * dt_hr)
    Q   = F @ eM[:2, 2:]     # Q_Δt = F · upper-right block of exp(M·Δt)
    Q   = (Q + Q.T) / 2.0    # symmetrise (numerical hygiene)
    # Cholesky of Q
    try:
        L = np.linalg.cholesky(Q + 1e-12 * np.eye(2))
    except np.linalg.LinAlgError:
        L = np.diag([math.sqrt(max(Q[0, 0], 1e-10)),
                     math.sqrt(max(Q[1, 1], 1e-10))])
    return (float(F[0, 0]), float(F[0, 1]), float(F[1, 0]), float(F[1, 1]),
            float(L[0, 0]), float(L[1, 0]), float(L[1, 1]))


def _peak_shrunk_bucket_probs(buckets: list, M0: float, center: float, sigma: float) -> dict:
    """
    PA-shrunk daily-max bucket probabilities (PRIMARY candidate pricer).

    daily_max ~ N(center, sigma²) with center = NWP_peak + peak_bias + β·x_hat
    (β≈0.3 shrinkage on the intraday residual — the 2024 backtest shows the
    morning anomaly mean-reverts ~70% by the peak, so the live pipeline's
    effective β≥1 over-weights it and mis-locates). σ is the per-city empirical
    daily-max-error std (~1.0-1.3°C). Single Gaussian CDF ⇒ coherent (Σ≤1);
    hard running-max floor F_M(x)=1[x≥M0]·Φ((x−center)/σ).
    """
    inv = 1.0 / (max(sigma, 1e-3) * math.sqrt(2.0))

    def _F_S(b: float) -> float:
        return 0.5 * (1.0 + math.erf((b - center) * inv))

    probs: dict = {}
    for (lo, hi) in buckets:
        f_hi = _F_S(hi) if hi >= M0 else 0.0
        f_lo = _F_S(lo) if lo >= M0 else 0.0
        probs[(lo, hi)] = max(0.0, f_hi - f_lo)
    return probs


def _joint_FQ(kappas: np.ndarray, gamma: float, C: np.ndarray, dt_hr: float):
    """
    Joint 2N transition F=exp(A·Δt) and process-noise Q=∫₀^Δt e^{Aτ}Σe^{Aᵀτ}dτ
    (Van Loan 1978) for the joint position-velocity OU field. State s=[X;V],
    drift A=[[0,I],[−diag(κ),−γI]]; noise drives velocity only, with cross-city
    covariance C_σ_ij = 2γ√(κ_iκ_j)·C_ij — chosen so the stationary position
    covariance equals the empirical spatial covariance C exactly. Shadow-only.
    """
    from scipy.linalg import expm as _expm
    N = len(kappas)
    A = np.zeros((2 * N, 2 * N))
    A[:N, N:] = np.eye(N)
    A[N:, :N] = -np.diag(kappas)
    A[N:, N:] = -gamma * np.eye(N)
    sk = np.sqrt(np.maximum(kappas, 1e-9))
    C_sigma = 2.0 * gamma * np.outer(sk, sk) * C        # 2γ√(κᵢκⱼ)·Cᵢⱼ
    Sigma = np.zeros((2 * N, 2 * N))
    Sigma[N:, N:] = C_sigma
    F = _expm(A * dt_hr)
    M = np.zeros((4 * N, 4 * N))
    M[:2 * N, :2 * N] = -A
    M[:2 * N, 2 * N:] = Sigma
    M[2 * N:, 2 * N:] = A.T
    Q = F @ _expm(M * dt_hr)[:2 * N, 2 * N:]
    return F, (Q + Q.T) / 2.0


# ── Pure helper functions ──────────────────────────────────────────────────────

def _get_kappa(st: dict, hour_utc: int) -> float:
    bin_i = hour_utc // 6
    return float(st.get("kappa", {}).get(str(bin_i), 0.5))


def _get_sigma(st: dict, hour_utc: int) -> float:
    bin_i = hour_utc // 6
    return float(st.get("sigma", {}).get(str(bin_i), 0.5))


def _current_month() -> int:
    import datetime
    return datetime.datetime.utcnow().month


def _peak_sigma_for(peak_calib: dict, city: str, month: int) -> float:
    """Per-(city,month) PA-shrunk pricing σ. Tries the city's sigma_monthly, then the
    _pooled monthly fallback, then the city's flat sigma (then 1.1). × the global EMOS
    factor (now 1.0). Season-aware: daily-max forecast error swings ~2× across the year."""
    cal = peak_calib.get(city) or peak_calib.get("_pooled", {})
    for src in (cal, peak_calib.get("_pooled", {})):
        sm = src.get("sigma_monthly") if isinstance(src, dict) else None
        if isinstance(sm, dict):
            v = sm.get(str(month)) or sm.get(month)
            if v:
                return float(v) * SIGMA_CALIB_INFLATION
    return float(cal.get("sigma", 1.1)) * SIGMA_CALIB_INFLATION


def _peak_bias_for(peak_calib: dict, city: str, month: int) -> float:
    """Per-(city,month) PA-shrunk peak_bias (A2). Tries the city's peak_bias_monthly,
    then the _pooled monthly fallback, then the city's flat scalar peak_bias (then 0.0).
    The monthly values preserve each city's annual scalar level and add only the
    seasonal deviation (daily-max residual swings by season)."""
    cal = peak_calib.get(city) or peak_calib.get("_pooled", {})
    bm = cal.get("peak_bias_monthly") if isinstance(cal, dict) else None
    if isinstance(bm, dict):
        v = bm.get(str(month), bm.get(month))
        if v is not None:
            return float(v)
    pooled_bm = peak_calib.get("_pooled", {}).get("peak_bias_monthly")
    if isinstance(pooled_bm, dict):
        v = pooled_bm.get(str(month), pooled_bm.get(month))
        if v is not None:
            return float(v)
    return float(cal.get("peak_bias", 0.0))


def _new_max(existing: Optional[float], temp_c: float) -> float:
    if existing is None:
        return temp_c
    return max(existing, temp_c)


def _book_ask(books: dict, token_id: str) -> Optional[float]:
    b = books.get(token_id)
    if b is None:
        return None
    ask = b.get("best_ask") or b.get("ask")
    if ask is None or ask <= 0 or ask >= 1:
        return None
    return float(ask)


# 2026-06-07 (Claude): FORWARD-LADDER BOOK LOGGER. Snapshots the FULL bucket
# ladder (every bucket's yes/no ask + usd depth + p_model + p_cal) per city per
# scan to logs/shadow/hot/<date>/stwa_ladder_book.jsonl. This is the data gap that
# blocks backtesting the higher-capacity weather edges: pricer_eval logs probs but
# NO book; metar_lockout logs the book only for already-locked buckets. With this,
# the next-day model-update lag, favorite-longshot, and neg-risk-arb edges become
# backtestable with REAL ask + depth + capacity. Write-only to logs/; throttled per
# city. Revert: STWA_LADDER_LOG_ENABLED=False.
STWA_LADDER_LOG_ENABLED  = True
STWA_LADDER_LOG_INTERVAL = 120.0   # min seconds between snapshots per city
_LADDER_LOG_LAST: dict = {}        # city -> last snapshot ts (module-level throttle)


def _log_ladder_book(city, entries, clob_books, phase, regime, cal_probs,
                     running_max=None, center=None):
    """Append one full-ladder book snapshot for capacity backtests (best-effort)."""
    if not STWA_LADDER_LOG_ENABLED:
        return
    import json as _json, time as _time
    now = _time.time()
    if now - _LADDER_LOG_LAST.get(city, 0.0) < STWA_LADDER_LOG_INTERVAL:
        return
    _LADDER_LOG_LAST[city] = now
    try:
        from datetime import datetime as _dt, timezone as _tz
        from pathlib import Path as _Path
        d = _Path("logs/shadow/hot") / _dt.now(_tz.utc).date().isoformat()
        d.mkdir(parents=True, exist_ok=True)
        cp = cal_probs or {}
        rows = []
        for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
            yb = clob_books.get(yes_tok) or {}
            nb = clob_books.get(no_tok) or {}
            rows.append({
                "lo": lo, "hi": hi,
                "p_model": round(p_m, 4),
                "p_cal": round(cp.get((lo, hi), p_m), 4),
                "ask_yes": ask_yes, "ask_no": ask_no,
                "yes_depth_usd": yb.get("usd_depth"),
                "no_depth_usd": nb.get("usd_depth"),
            })
        with (d / "stwa_ladder_book.jsonl").open("a") as f:
            f.write(_json.dumps({"ts": now, "city": city, "phase": phase,
                                 "regime": regime,
                                 "running_max": running_max,
                                 "model_center": (round(center, 3)
                                                  if isinstance(center, (int, float)) else None),
                                 "buckets": rows}) + "\n")
    except Exception:
        pass


def _book_implied_sigma(entries: list) -> Optional[float]:
    """Std (°C) of the YES-ask-implied daily-max distribution.

    The YES asks across a city's buckets are an overround-inflated, discretized
    forecast distribution. Normalizing the asks removes the overround φ (it
    cancels), so the mass-weighted std of the bucket centers recovers the book's
    implied σ (= s_M), Sheppard-corrected for bucket-width quantization.

    Returns None if fewer than 3 priced buckets (can't estimate). Truncated tails
    bias s_M DOWN, which only makes the width gate MORE conservative — safe.

    entries: [(lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no), ...]
    """
    centers, weights = [], []
    width = None
    for lo, hi, _yt, _nt, _pm, ask_yes, _an in entries:
        if ask_yes is None or not (0 < ask_yes < 1):
            continue
        centers.append(0.5 * (lo + hi))
        weights.append(ask_yes)
        if width is None:
            width = abs(hi - lo)
    if len(weights) < 3:
        return None
    w = np.array(weights, dtype=float)
    c = np.array(centers, dtype=float)
    wsum = w.sum()
    if wsum <= 0:
        return None
    w = w / wsum
    mu  = float((w * c).sum())
    var = float((w * (c - mu) ** 2).sum())
    if width:                       # Sheppard's correction for bucket discretization
        var -= (width ** 2) / 12.0
    return math.sqrt(var) if var > 1e-6 else None


def _kelly_stake(
    p: float, ask: float, confidence: float,
    bankroll: float, frac: float, lo: float, hi: float
) -> float:
    b   = (1.0 / ask) - 1.0   # net odds per dollar staked
    p_c = p * confidence
    f   = (p_c * b - (1.0 - p_c)) / b
    f   = max(0.0, f) * frac
    raw = bankroll * f
    return float(np.clip(raw, lo, hi))


def _gev_cdf(x: float, loc: float, scale: float, shape: float) -> float:
    """
    CDF of the Generalized Extreme Value distribution.
        F(x) = exp(-(1 + ξ·z)^(-1/ξ))    for ξ ≠ 0, where z = (x − μ) / σ
        F(x) = exp(-exp(-z))             for ξ = 0  (Gumbel)
    The support is restricted: 1 + ξ·z > 0 (else F = 0 or 1 depending on sign).
    """
    if scale <= 0:
        return 1.0 if x >= loc else 0.0
    z = (x - loc) / scale
    if abs(shape) < 1e-6:
        return float(np.exp(-np.exp(-z)))
    arg = 1.0 + shape * z
    if arg <= 0:
        # Below lower bound (ξ > 0) or above upper bound (ξ < 0)
        return 0.0 if shape > 0 else 1.0
    return float(np.exp(-arg ** (-1.0 / shape)))


def _gev_bucket_prob(
    lo: float, hi: float,
    running_max: Optional[float],
    nwp_max_today: float,
    gev_loc: float, gev_scale: float, gev_shape: float,
) -> float:
    """
    Closed-form bucket probability under the daily-max GEV model.

        Daily max M = max(running_max, M_future)
        M_future = NWP_max_today + ε   where ε ~ GEV(loc, scale, shape)

        P(M ∈ [lo, hi]) = P(max(M0, M_future) < hi) − P(max(M0, M_future) < lo)
                       = I(M0 < hi) · F_GEV(hi − NWP_max) − I(M0 < lo) · F_GEV(lo − NWP_max)
    """
    M0 = running_max if running_max is not None else float("-inf")
    if M0 >= hi:
        return 0.0
    p_hi = _gev_cdf(hi - nwp_max_today, gev_loc, gev_scale, gev_shape)
    if M0 < lo:
        p_lo = _gev_cdf(lo - nwp_max_today, gev_loc, gev_scale, gev_shape)
    else:
        p_lo = 0.0  # already past the lower bound; P(M < lo) = 0
    return max(0.0, p_hi - p_lo)


def _peak_anchored_bucket_probs(
    buckets: list,
    M0: float,
    mu_grid: np.ndarray,
    m_arr: np.ndarray,
    s2_arr: np.ndarray,
) -> dict:
    """
    Peak-anchored daily-max bucket probabilities.

    The daily max is dominated by the diurnal peak: the deterministic NWP curve
    μ(t) sweeps up to μ_peak, and the residual Y is a small mean-reverting
    fluctuation, so to first order

        daily_max ≈ μ_peak + Y(t*),   Y(t*) ~ N(m*, s*²),

    where (m*, s*²) are the residual posterior mean/variance propagated to the
    peak hour t*. Crucially s* stays bounded near the *stationary* residual std
    (σ²/2γκ) — it does NOT inflate with horizon like the raw MC whole-day
    path-max, which is the over-spread that made the MC 4.3× overconfident.

    Single Gaussian CDF F_S(b)=Φ((b−μ_peak−m*)/s*) ⇒ bucket probabilities are
    coherent by construction (a telescoping difference of one monotone CDF, so
    they sum to ≤1). The observed running max M0 is a hard floor:
    F_M(x)=1[x≥M0]·F_S(x),  p(lo,hi)=F_M(hi)−F_M(lo).

    (This is the units-clean form of agent C's peak-window idea. The second-order
    sup-correction — the max over the peak window slightly exceeds the point
    value at t* — is intentionally omitted: it is a small upper-tail effect with
    a fragile constant, and is left for a later refinement once the base
    estimator is validated against resolution in shadow.)
    """
    n = len(mu_grid)
    if n < 1:
        return {}
    i_peak  = int(np.argmax(mu_grid))
    mu_peak = float(mu_grid[i_peak])
    m_star  = float(m_arr[i_peak])
    s_star  = math.sqrt(max(float(s2_arr[i_peak]), 1e-6))
    center  = mu_peak + m_star
    inv     = 1.0 / (s_star * math.sqrt(2.0))

    def _F_S(b: float) -> float:
        return 0.5 * (1.0 + math.erf((b - center) * inv))

    probs: dict = {}
    for (lo, hi) in buckets:
        f_hi = _F_S(hi) if hi >= M0 else 0.0
        f_lo = _F_S(lo) if lo >= M0 else 0.0
        probs[(lo, hi)] = max(0.0, f_hi - f_lo)
    return probs


def _phase(cs: _CityState, t_close: float, t_now: float) -> str:
    """Classify whether we're before, at, or after the expected daily peak."""
    import datetime
    try:
        from strategy.weather_arb import CITY_PEAK_HOUR_UTC, CITY_NAME_TO_SLUG
        slug   = CITY_NAME_TO_SLUG.get(cs.city, cs.city)
        month  = datetime.datetime.utcnow().month
        peak_h = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month, 14)
    except Exception:
        peak_h = 14
    # Anchor peak time to t_close (market close = local midnight), then walk back
    # to find the most recent occurrence of peak_h UTC before t_close.
    # This is timezone-agnostic and handles Americas cities where peak_h < UTC midnight.
    t_close_h = int((t_close % 86400) / 3600)
    hours_since_peak = (t_close_h - peak_h) % 24  # hours from peak to close (same day)
    peak_time = t_close - hours_since_peak * 3600
    diff_s = t_now - peak_time
    if diff_s < -3600:
        return "PRE_PEAK"
    elif diff_s > 3600:
        return "POST_PEAK"
    else:
        return "AT_PEAK"


def _compute_ece(probs: list[float], outcomes: list[int], n_bins: int = 10) -> float:
    if not probs:
        return 0.0
    p = np.array(probs)
    o = np.array(outcomes, dtype=float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece  = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi)
        if mask.sum() == 0:
            continue
        acc  = o[mask].mean()
        conf = p[mask].mean()
        ece += mask.mean() * abs(acc - conf)
    return float(ece)
