"""
Klaus — Window Sniper

Fair-value based mid-window entry engine for Polymarket updown binary markets.

Strategy (inspired by 0x8dxd's documented $313→$438k run):
  - Wait until 25–80% of the 5M/15M window has elapsed
  - Compute how far the asset (BTC/ETH/SOL) has moved from the window's open price
  - Map that move to a fair-value probability via sigmoid function
  - If the Polymarket token is still significantly below fair value → enter

Fair value model (sigmoid, k=8, calibrated to Archetapp empirical pricing data):
  delta_pct  →  fair_value (YES)
    0.00%   →  0.50  (coin flip at window open)
    0.05%   →  0.60
    0.10%   →  0.69
    0.20%   →  0.83
    0.30%   →  0.92
    0.40%   →  0.96

Edge = fair_value - token_ask
  Normal entry:              edge ≥ 0.04
  VPIN confirmed (>0.60):    edge ≥ 0.03  (informed flow agrees)
  LLM boost confirmed:       edge ≥ 0.02  (Claude sees same signal)

Time gate:
  Enter only between 25% and 80% of window elapsed.
  Before 25%: move may reverse; wait for confirmation.
  After 80%:  too little time for edge to materialise; fee-adjusted EV shrinks.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import logging

from data.feeds import MarketToken, OrderBook, ExternalSignal
from strategy.momentum import Direction, FeeZone

logger = logging.getLogger("window_sniper")

# ── Tunable parameters ─────────────────────────────────────────────────────────
SIGMOID_K = 8.0             # steepness: 0.10% delta → 0.69 FV

# ── Fair value model: sigmoid + time confidence ──────────────────────────────
#
# Base model:  FV = sigmoid(K × |delta_pct|)
#   delta_pct  →  FV(YES token)
#     0.00%   →  0.50  (coin flip at window open)
#     0.05%   →  0.60
#     0.10%   →  0.69
#     0.20%   →  0.83
#
# LIMITATION (time-agnostic):
#   The base model gives identical FV at 18% elapsed vs 80% elapsed for the
#   same delta. This is wrong. Polymarket correctly prices a -0.083% move at
#   75% elapsed as ~0.85 (sustained for 11min, likely to hold) — our model
#   says 0.66. The gap looks like a lag but isn't: PM is right, we're wrong.
#   Observed: (fv=0.661 ask=0.850 delta=-0.083%) → "no lag" block was correct
#   but for the wrong reason (edge negative). Should be: FV_adj ≈ 0.79–0.85.
#
# FIX: time_confidence scales the effective delta by how much of the window
# has elapsed. A move that has persisted for 75% of the window is equivalent
# in certainty to a larger move at window open.
#
# Rationale: variance of remaining price path ∝ sqrt(time_remaining/window).
# Scaling delta by 1/sqrt(remaining_fraction) normalises for this uncertainty.
#
#   elapsed  → time_confidence  → FV for 0.083% delta
#   18%      → 1.10            → 0.68  (barely adjusted — early entry)
#   50%      → 1.41            → 0.74  (meaningfully more certain)
#   75%      → 2.00            → 0.80  (sustained move, high confidence)
#   80%      → 2.24            → 0.83  (close to PM ask — minimal false lag)
#
# Capped at 2.5× to prevent runaway near expiry (last 5% of window).
TIME_CONFIDENCE_CAP = 2.5   # max amplification of delta for time adjustment

# Session-aware minimum delta: quiet-hour moves <0.20% are noise (40% sustain rate).
# Matches macro_engine thresholds so both engines agree on what constitutes a signal.
# All 3 sniper losses (T00020/22/25) were quiet-hour trades at 0.066–0.079% delta.
_HIGH_VOLUME_HOURS = {8, 9, 13, 14, 15, 22, 23, 0}
_DELTA_PCT_ACTIVE = 0.04   # TEST MODE — floor only, edge gate does real filtering
_DELTA_PCT_QUIET  = 0.06   # TEST MODE

# 15m windows measure delta over 15 minutes — a 0.25% sustained drift over 15min
# is more reliable than a 0.35% spike in a 5min window. Lower bar justified.
# Adaptive: below 40% elapsed (early window), require 1.5× — move hasn't had time
# to confirm. T00088: 0.086% at 18% elapsed reversed immediately. Above 40% the
# move has been running 6+ minutes and is far more likely to persist to close.
_DELTA_PCT_15M_ACTIVE       = 0.08   # base bar ≥40% elapsed
_DELTA_PCT_15M_ACTIVE_EARLY = 0.12   # raised bar <40% elapsed (1.5×)
_DELTA_PCT_15M_QUIET        = 0.12   # quiet hours: same as early-window bar
_EARLY_ELAPSED_CUTOFF       = 0.40   # below this = "early window" for 15m

MIN_EDGE = 0.06             # require clear mispricing — 0.02 was too loose (T00070-76 had 0.057-0.082)
MIN_EDGE_VPIN = 0.04        # VPIN confirmation reduces bar
MIN_EDGE_BOOST = 0.03       # LLM boost confirmation
WINDOW_ELAPSED_MIN = 0.25   # raised 0.18→0.25: T00088 entered at 18% elapsed, delta=0.086%
                            # (barely above threshold) → reversed immediately, -$4.40
                            # 25% = 3.75min into 15m window: meaningful confirmation time
                            # data: <17% was 6L/0W; 18% is effectively the same zone
WINDOW_ELAPSED_MAX = 0.80   # no entry after 80% (too late)
VPIN_CONFIRM_THRESHOLD = 0.60   # VPIN above this = informed flow
LLM_BOOST_STRONG = 0.05     # macro_boost magnitude above this = LLM confirms
MIN_TOKEN_ASK = 0.35        # skip near-resolved tokens (both 5m and 15m)
MAX_TOKEN_ASK = 0.90        # hard ceiling — near-fully-resolved tokens only
# Fixed ask caps (0.55/0.58) replaced by lag_remaining gate:
# A large Binance move can push ask to 0.65+ while still having 70%+ lag remaining.
# Fixed cap would block this; lag_remaining gate allows it and blocks weak moves correctly.
MIN_LAG_REMAINING = 0.30    # loosened 0.55→0.30: collect data across wider lag range
MIN_LAG_REMAINING_5M = 0.40 # loosened 0.65→0.40: 5m still slightly tighter than 15m
VPIN_OFFPEAK_REQUIRED = 0.40  # loosened 0.55→0.40: allow more off-peak flow through

WINDOW_ELAPSED_MAX_5M  = 0.40  # 5m: stop entering after 40% (180s left = full hard-exit runway)
                                # T00040: entered at 54% elapsed → STOP_LOSS in 17s (too late)
                                # T00035: entered at 18% elapsed → +$0.992 (early = room to breathe)
                                # At 40%: 180s remaining ≥ hard-exit timer. At 54%: structurally broken.
WINDOW_ELAPSED_MAX_15M = 0.80  # 15m: full 80% (still 3 min left at 80%)

# ── Pre-arm: early entry when previous window already repriced ─────────────────
# If current window's token repriced past 0.80, next window will open at ~0.50.
# We already have direction confirmation — enter at 5% elapsed (15s into 5m window).
PREARM_ELAPSED_MIN = 0.05       # enter at 5% elapsed when pre-armed (vs 0.25 normal)
PREARM_ASK_THRESHOLD = 0.80     # set pre-arm when current window ask > 80%
PREARM_SUSTAIN_FACTOR = 0.5     # require only 50% of normal sustain (prev window = confirmation)
PREARM_EXPIRY_S = 600           # pre-arm expires after 10 min (2 windows) if unused
PREARM_MAX_ASK = 0.58           # PREARM entries capped tighter than normal (0.65/0.55)
                                # T00036/37: pre-arm fired at 0.65+, market already priced in,
                                # no edge → both stopped out at -$0.8. If price already
                                # repriced in the new window, there's nothing left to capture.


@dataclass
class SniperBlock:
    """
    Emitted when the sniper had a real candidate but blocked it for a signal-quality reason.
    Stored on WindowSniper._last_block[(asset, side)] so main.py can shadow-monitor the outcome.

    Only populated for meaningful blocks (lag too low, edge too low, VPIN off-peak).
    Trivial blocks (no data, time gate, wrong side, hard ceiling) are NOT tracked —
    they have no counterfactual value.
    """
    asset: str
    side: str
    token_id: str
    window_end_ts: float
    window_seconds: int
    block_reason: str           # "lag_too_low" | "edge_negative" | "edge_insufficient" | "vpin_offpeak"
    token_ask: float            # PM ask at block moment
    fair_value: float           # time-adjusted sigmoid FV
    edge: float                 # fair_value - token_ask (can be negative)
    lag_remaining_pct: float    # fraction of expected PM move not yet priced in
    delta_pct: float            # Binance move from window open (signed)
    elapsed_pct: float          # fraction of window elapsed
    vpin: float                 # VPIN at block time
    ts: float                   # unix timestamp of block


@dataclass
class SniperSignal:
    """
    Output of WindowSniper.score().
    Compatible fields with SignalBreakdown so main.py routing works unchanged.
    """
    asset: str              # "BTC", "ETH", "SOL"
    side: str               # "YES" or "NO" — which token we're evaluating
    asset_direction: int    # +1 = asset going UP (YES wins), -1 = DOWN (NO wins)
    delta_pct: float        # asset % move from window open (signed)
    fair_value: float       # sigmoid model probability for this specific token
    token_ask: float        # current best ask for this token
    edge: float             # fair_value - token_ask
    entry_price: float      # recommended limit entry (ask + 0.5 tick buffer)
    confidence: float       # 0.50–0.95
    composite: float        # edge-based score; used by risk manager min_score gate
    direction: Direction    # always BUY_YES (buy this specific token) when signal fires
    fee_zone: FeeZone       # EXTREME or FAT_MIDDLE (for risk manager gate)
    elapsed_pct: float      # fraction of window elapsed when signal fired
    reason: str             # human-readable explanation
    # Analytics enrichment — recorded in TradeRecord for post-session analysis
    is_prearm: bool = False         # True if pre-arm mechanism triggered early entry
    vpin_at_entry: float = 0.0      # VPIN score at time of signal (0.5=neutral, >0.6=toxic)
    llm_boost_at_entry: float = 0.0 # macro_boost magnitude at entry (0=no LLM signal)
    # Polymarket lag analytics — core edge thesis validation
    pm_ask_at_trigger: float = 0.0  # PM ask when Binance delta first crossed threshold
    pm_drift_at_entry: float = 0.0  # PM ask change since trigger (analytics only — not a gate)
    lag_remaining_pct: float = 0.0  # fraction of expected PM move not yet priced in (1.0=max lag, 0=closed)


def _session_min_delta(is_15m: bool = False, elapsed_pct: float = 1.0) -> float:
    """
    Minimum delta threshold. For 15m windows, early entries (< 40% elapsed)
    require 1.5× the normal threshold — move hasn't confirmed yet.
    """
    if is_15m:
        if elapsed_pct < _EARLY_ELAPSED_CUTOFF:
            return _DELTA_PCT_15M_ACTIVE_EARLY
        return _DELTA_PCT_15M_ACTIVE
    return _DELTA_PCT_ACTIVE


# Window-size-aware sustain period:
#   5-min windows (≤300s): 20s — wicks reverse in <15s; 30s too narrow (only 90s
#     first-breach window available between elapsed 40-70%). 10s still filters 5-15s wicks.
#   15-min+ windows  (>300s): 20s — longer window; 20s sustain proportionally less costly.
_SUSTAINED_5M = 0.0   # 0s sustain — PM ask snapshot check replaces sustain as confirmation
_SUSTAINED_15M = 0.0  # Burning 2s here wastes most of the 2.7s Polymarket lag window


class WindowSniper:
    """
    Mid-window fair-value arbitrage engine.
    Call score() for each updown token every scan cycle (~1s).

    Returns SniperSignal when entry conditions are met, else None.
    Only fires for the correct side: YES token when asset up, NO token when asset down.
    """

    def __init__(self) -> None:
        # Per-(token_id, direction) timestamp of first threshold breach.
        # Cleared when delta reverses or falls below min_delta.
        self._delta_sustained_since: dict = {}
        # Pre-arm state: (asset, side) → (set_at, armed_window_end_ts).
        # Set when current window is fully repriced (ask > 0.80).
        # Only fires for tokens whose window_end_ts > armed_window_end_ts (next window).
        self._prearm: dict = {}
        # Shadow monitoring: last meaningful block per (asset, side).
        # main.py reads this after each score() → None to spawn a shadow monitor.
        # Populated only for signal-quality blocks (lag, edge, VPIN) — not structural ones.
        self.last_block: dict = {}   # (asset, side) → SniperBlock

    def score(
        self,
        token: MarketToken,
        ob: Optional[OrderBook],
        ext: Optional[ExternalSignal],
        now: Optional[float] = None,
    ) -> Optional[SniperSignal]:
        """
        Evaluate whether this token represents a mispriceable opportunity.

        Parameters:
            token: MarketToken being evaluated (must be updown market_type)
            ob:    Current order book for this token
            ext:   External signal for this token's asset (Binance prices + VPIN + macro)
            now:   Current unix timestamp (defaults to time.time())
        """
        if now is None:
            now = time.time()

        # ── Data availability ──────────────────────────────────────────────────
        if ob is None or ext is None:
            return None
        if not ob.asks:
            return None

        # Select window-open price for this market's interval
        spot_window_open = (
            ext.spot_window_open_5m if token.window_seconds <= 300
            else ext.spot_window_open_15m
        )
        if not spot_window_open or spot_window_open <= 0:
            return None

        spot_current = ext.spot_price
        if not spot_current or spot_current <= 0:
            return None

        # ── Delta computation + sustain timer (runs before time gate) ────────────
        # Sustain timer must start as soon as delta crosses threshold — even if the
        # window hasn't reached 40% elapsed yet. Otherwise: a token at 35% elapsed
        # with a 0.3% move gets the time gate blocked, timer never starts, and when
        # it hits 40% the 10s sustain starts from zero — missing the entire move.
        delta_pct = (spot_current - spot_window_open) / spot_window_open * 100

        is_15m = token.window_seconds > 300
        # 5m re-enabled: lag_remaining gate replaces fixed ask cap as quality filter.
        # Old 50% WR on 5m was with fixed caps; lag_remaining > 0.65 should filter the noise.

        # Compute elapsed_pct early so adaptive delta threshold can use it
        _elapsed_pct_early = (
            (now - (token.window_end_ts - token.window_seconds)) / token.window_seconds
            if token.window_end_ts > 0 and token.window_seconds > 0 else 1.0
        )
        min_delta = _session_min_delta(is_15m=is_15m, elapsed_pct=_elapsed_pct_early)
        asset_direction = 1 if delta_pct > 0 else -1
        sustain_key = (token.token_id, asset_direction)
        opp_key = (token.token_id, -asset_direction)

        if abs(delta_pct) < min_delta:
            # Delta below threshold — clear any sustained timers for this token.
            self._delta_sustained_since.pop((token.token_id, 1), None)
            self._delta_sustained_since.pop((token.token_id, -1), None)
            return None

        # Start/maintain sustain timer regardless of time gate
        self._delta_sustained_since.pop(opp_key, None)  # clear reversed-direction timer
        if sustain_key not in self._delta_sustained_since:
            self._delta_sustained_since[sustain_key] = (now, ob.asks[0][0] if ob.asks else 0.0)
            logger.debug(
                "SNIPER SUSTAIN_START %s/%s | delta=%.3f%% ask=%.3f — waiting %.0fs confirmation",
                token.asset, token.side, delta_pct, ob.asks[0][0] if ob.asks else 0,
                _SUSTAINED_5M if not is_15m else _SUSTAINED_15M,
            )

        # ── Pre-arm check: allow early entry if previous window was fully repriced ─
        prearm_key = (token.asset, token.side)
        is_prearmed = False
        if prearm_key in self._prearm:
            prearm_set_at, prearm_window_end = self._prearm[prearm_key]
            age = now - prearm_set_at
            if age >= PREARM_EXPIRY_S:
                del self._prearm[prearm_key]  # expired
            elif token.window_end_ts > prearm_window_end:
                # This token is from a LATER window — pre-arm applies
                is_prearmed = True
                logger.debug("SNIPER PREARMED %s/%s | age=%.0fs — using early entry gate",
                             token.asset, token.side, age)
            # else: same window that triggered the pre-arm — don't apply

        # ── Time gate ──────────────────────────────────────────────────────────
        if token.window_end_ts <= 0 or token.window_seconds <= 0:
            return None

        window_start = token.window_end_ts - token.window_seconds
        elapsed = now - window_start
        elapsed_pct = elapsed / token.window_seconds

        elapsed_min = PREARM_ELAPSED_MIN if is_prearmed else WINDOW_ELAPSED_MIN
        if elapsed_pct < elapsed_min:
            logger.debug("SNIPER BLOCK %s/%s | time_early elapsed=%.1f%% < %.0f%%%s",
                         token.asset, token.side, elapsed_pct*100, elapsed_min*100,
                         " (prearmed)" if is_prearmed else "")
            return None
        elapsed_max = WINDOW_ELAPSED_MAX_5M if not is_15m else WINDOW_ELAPSED_MAX_15M
        if elapsed_pct > elapsed_max:
            logger.debug("SNIPER BLOCK %s/%s | time_late elapsed=%.1f%% > %.0f%% (%s)",
                         token.asset, token.side, elapsed_pct*100, elapsed_max*100,
                         "5m" if not is_15m else "15m")
            return None

        # ── Sustained delta gate ───────────────────────────────────────────────
        required_sustain = _SUSTAINED_5M if not is_15m else _SUSTAINED_15M
        if is_prearmed:
            required_sustain = max(0.2, required_sustain * PREARM_SUSTAIN_FACTOR)
        trigger_ts, ask_at_trigger = self._delta_sustained_since[sustain_key]
        sustained_for = now - trigger_ts
        if sustained_for < required_sustain:
            logger.debug("SNIPER BLOCK %s/%s | sustain %.1fs / %.0fs delta=%.3f%%",
                         token.asset, token.side, sustained_for, required_sustain, delta_pct)
            return None

        # ── Side alignment: only trade the winning token ───────────────────────
        if token.side == "YES" and asset_direction < 0:
            logger.debug("SNIPER BLOCK %s/YES | side_wrong (asset falling, YES loses)", token.asset)
            return None
        if token.side == "NO" and asset_direction > 0:
            logger.debug("SNIPER BLOCK %s/NO | side_wrong (asset rising, NO loses)", token.asset)
            return None

        # ── Fair value via sigmoid (time-adjusted) ────────────────────────────
        # Scale delta by time_confidence: a move that has persisted for X% of
        # the window is more likely to hold than the same move at window open.
        # This prevents late-window "false lag" where PM correctly prices high
        # and our model under-estimates because it ignores elapsed time.
        directional_delta = abs(delta_pct)
        time_remaining_frac = max(0.05, 1.0 - elapsed_pct)  # floor at 5%
        time_confidence = min(TIME_CONFIDENCE_CAP, 1.0 / math.sqrt(time_remaining_frac))
        fair_value = 1.0 / (1.0 + math.exp(-SIGMOID_K * directional_delta * time_confidence))

        # ── Token ask and edge ─────────────────────────────────────────────────
        token_ask = ob.asks[0][0]
        if is_prearmed:
            logger.debug("SNIPER PREARMED_EVAL %s/%s | elapsed=%.1f%% delta=%+.3f%% "
                         "fv=%.3f ask=%.3f edge=%+.4f",
                         token.asset, token.side, elapsed_pct*100, delta_pct,
                         fair_value, token_ask, fair_value - token_ask)
        if token_ask <= 0:
            logger.debug("SNIPER BLOCK %s/%s | ask=0 (empty OB)", token.asset, token.side)
            return None

        # Hard ceiling: near-resolved tokens only (>90% priced)
        if token_ask > MAX_TOKEN_ASK or token_ask < MIN_TOKEN_ASK:
            if token_ask > PREARM_ASK_THRESHOLD and prearm_key not in self._prearm:
                self._prearm[prearm_key] = (now, token.window_end_ts)
                logger.info(
                    "SNIPER PREARM %s/%s | ask=%.3f — next window early entry armed",
                    token.asset, token.side, token_ask,
                )
            _block_reason = "near_ceiling" if token_ask > MAX_TOKEN_ASK else "near_resolved"
            logger.info("SNIPER BLOCK %s/%s | ask=%.3f — %s (delta=%+.3f%%)",
                        token.asset, token.side, token_ask, _block_reason, delta_pct)
            return None

        edge = fair_value - token_ask
        if edge <= 0:
            logger.info("SNIPER BLOCK %s/%s | edge=%.4f (fv=%.3f ask=%.3f delta=%+.3f%%) — no lag",
                        token.asset, token.side, edge, fair_value, token_ask, delta_pct)
            self.last_block[(token.asset, token.side)] = SniperBlock(
                asset=token.asset, side=token.side, token_id=token.token_id,
                window_end_ts=token.window_end_ts, window_seconds=token.window_seconds,
                block_reason="edge_negative",
                token_ask=token_ask, fair_value=fair_value, edge=edge,
                lag_remaining_pct=0.0, delta_pct=delta_pct, elapsed_pct=elapsed_pct,
                vpin=ext.vpin_score or 0.0, ts=now,
            )
            return None

        # ── Polymarket lag measurement + lag_remaining gate ───────────────────
        # How much of the Binance move has PM already priced in?
        # lag_remaining = (FV - ask) / (FV - 0.50): fraction of expected move still unpriced.
        # 1.0 = PM hasn't moved at all (maximum lag, ideal entry).
        # 0.0 = PM fully repriced (no lag left).
        # pm_drift = mechanical repricing since trigger fired (pure data, not a block).
        pm_drift = (token_ask - ask_at_trigger) if ask_at_trigger > 0 else 0.0
        expected_move = fair_value - 0.50
        lag_remaining_pct = max(0.0, (fair_value - token_ask) / expected_move) if expected_move > 0.01 else 0.0
        # Gate: require sufficient lag remaining — adaptive to move magnitude.
        # Override: if absolute edge is very large (≥0.10), the lag% floor is relaxed
        # to 15% regardless. Rationale: FV=0.979, ask=0.840 → lag=29%, edge=+0.139.
        # The lag% penalises extreme FV (large denominator) even when uncaptured
        # repricing in dollar terms is huge. Edge ≥ 0.10 is strong evidence either way.
        MIN_EDGE_OVERRIDE = 0.10
        min_lag = MIN_LAG_REMAINING_5M if not is_15m else MIN_LAG_REMAINING
        if is_prearmed:
            min_lag = min_lag * 0.80  # pre-arm: slightly relaxed (prior window confirms direction)
        if edge >= MIN_EDGE_OVERRIDE:
            min_lag = min(min_lag, 0.15)   # absolute edge overrides lag% floor
        if lag_remaining_pct < min_lag:
            logger.info(
                "SNIPER BLOCK %s/%s | lag=%.0f%% < %.0f%% min (fv=%.3f ask=%.3f delta=%+.3f%%) — PM mostly repriced",
                token.asset, token.side, lag_remaining_pct * 100, min_lag * 100,
                fair_value, token_ask, delta_pct,
            )
            self.last_block[(token.asset, token.side)] = SniperBlock(
                asset=token.asset, side=token.side, token_id=token.token_id,
                window_end_ts=token.window_end_ts, window_seconds=token.window_seconds,
                block_reason="lag_too_low",
                token_ask=token_ask, fair_value=fair_value, edge=edge,
                lag_remaining_pct=lag_remaining_pct, delta_pct=delta_pct, elapsed_pct=elapsed_pct,
                vpin=ext.vpin_score or 0.0, ts=now,
            )
            return None

        logger.debug(
            "SNIPER LAG %s/%s | remaining=%.0f%% pm_drift=%+.3f (ask %.3f→%.3f) fv=%.3f",
            token.asset, token.side, lag_remaining_pct * 100,
            pm_drift, ask_at_trigger if ask_at_trigger > 0 else token_ask, token_ask, fair_value,
        )

        # ── VPIN off-peak gate ────────────────────────────────────────────────
        # During high-info sessions (13-15 UTC), information events drive real lag.
        # Off-peak: require minimum VPIN to confirm informed flow — filters the
        # 0/8 WR at 18-23 UTC without a hard hour block (preserves data collection).
        hour_utc = datetime.now(timezone.utc).hour
        is_active_session = hour_utc in _HIGH_VOLUME_HOURS
        if not is_active_session:
            vpin_for_gate = ext.vpin_score or 0.0
            if vpin_for_gate < VPIN_OFFPEAK_REQUIRED:
                logger.info(
                    "SNIPER BLOCK %s/%s | off-peak VPIN=%.3f < %.2f — no informed flow (hour=%d UTC)",
                    token.asset, token.side, vpin_for_gate, VPIN_OFFPEAK_REQUIRED, hour_utc,
                )
                self.last_block[(token.asset, token.side)] = SniperBlock(
                    asset=token.asset, side=token.side, token_id=token.token_id,
                    window_end_ts=token.window_end_ts, window_seconds=token.window_seconds,
                    block_reason="vpin_offpeak",
                    token_ask=token_ask, fair_value=fair_value, edge=edge,
                    lag_remaining_pct=lag_remaining_pct, delta_pct=delta_pct, elapsed_pct=elapsed_pct,
                    vpin=vpin_for_gate, ts=now,
                )
                return None

        # ── Edge gate with confirmation signals ───────────────────────────────
        macro_boost = ext.macro_boost or 0.0
        vpin = ext.vpin_score or 0.0
        vpin_dir = ext.vpin_direction or 0

        # VPIN direction must agree with our trade direction
        vpin_agrees = (
            vpin > VPIN_CONFIRM_THRESHOLD
            and (
                (token.side == "YES" and vpin_dir > 0)
                or (token.side == "NO" and vpin_dir < 0)
            )
        )

        # LLM boost must agree with our trade direction
        llm_confirms = (
            abs(macro_boost) > LLM_BOOST_STRONG
            and (
                (token.side == "YES" and macro_boost > 0)
                or (token.side == "NO" and macro_boost < 0)
            )
        )

        if llm_confirms:
            min_edge = MIN_EDGE_BOOST
        elif vpin_agrees:
            min_edge = MIN_EDGE_VPIN
        else:
            min_edge = MIN_EDGE

        if edge < min_edge:
            logger.info("SNIPER BLOCK %s/%s | edge=%.4f < min=%.4f (fv=%.3f ask=%.3f delta=%+.3f%%) — insufficient lag",
                        token.asset, token.side, edge, min_edge, fair_value, token_ask, delta_pct)
            self.last_block[(token.asset, token.side)] = SniperBlock(
                asset=token.asset, side=token.side, token_id=token.token_id,
                window_end_ts=token.window_end_ts, window_seconds=token.window_seconds,
                block_reason="edge_insufficient",
                token_ask=token_ask, fair_value=fair_value, edge=edge,
                lag_remaining_pct=lag_remaining_pct, delta_pct=delta_pct, elapsed_pct=elapsed_pct,
                vpin=vpin or 0.0, ts=now,
            )
            return None

        # ── Confidence ────────────────────────────────────────────────────────
        # Base: 0.50 + edge contribution (0.04 edge → 0.60, 0.10 edge → 0.75)
        confidence = min(0.95, max(0.50, 0.50 + edge * 2.5))

        # Boosts from confirmation signals
        if llm_confirms:
            confidence = min(0.95, confidence + 0.08)
        if vpin_agrees:
            confidence = min(0.95, confidence + 0.05)

        # Time decay: reduce confidence as we approach the 80% cutoff
        # (less time = higher variance, less room for the market to reprice)
        time_progress = (elapsed_pct - WINDOW_ELAPSED_MIN) / (WINDOW_ELAPSED_MAX - WINDOW_ELAPSED_MIN)
        time_factor = 1.0 - 0.20 * time_progress   # 1.0 at 25%, 0.80 at 80%
        confidence = max(0.50, confidence * time_factor)

        # ── Composite score ────────────────────────────────────────────────────
        # Normalised 0–1 score for risk manager's min_score gate.
        # 0.04 edge → 0.50, 0.08 edge → 0.60, 0.15 edge → 0.78
        composite = min(1.0, 0.40 + edge * 2.5)

        # ── Fee zone ──────────────────────────────────────────────────────────
        fee_zone = (
            FeeZone.EXTREME
            if token_ask < 0.35 or token_ask > 0.65
            else FeeZone.FAT_MIDDLE
        )

        # ── Entry price ───────────────────────────────────────────────────────
        # Small buffer above best ask: ~0.5 tick = fills immediately as aggressor
        entry_price = min(0.97, round(token_ask + 0.005, 4))

        # ── Reason string ─────────────────────────────────────────────────────
        # ── Clear pre-arm on signal — one-shot per window ─────────────────────
        if is_prearmed and prearm_key in self._prearm:
            del self._prearm[prearm_key]
            logger.info("SNIPER PREARM FIRED %s/%s | early entry used, pre-arm cleared",
                        token.asset, token.side)

        reason = (
            f"Sniper{'[PREARMED]' if is_prearmed else ''}: {token.asset} {delta_pct:+.3f}% from window open | "
            f"{elapsed_pct:.0%} elapsed | FV={fair_value:.3f} ask={token_ask:.3f} "
            f"edge={edge:+.3f}"
        )
        if llm_confirms:
            reason += f" [LLM {macro_boost:+.3f}]"
        if vpin_agrees:
            reason += f" [VPIN {vpin:.2f}]"

        logger.debug(
            "SNIPER %s/%s | %+.3f%% delta | FV=%.3f ask=%.3f edge=%.3f "
            "elapsed=%.0f%% conf=%.2f composite=%.2f",
            token.asset, token.side, delta_pct, fair_value, token_ask, edge,
            elapsed_pct * 100, confidence, composite,
        )

        return SniperSignal(
            asset=token.asset,
            side=token.side,
            asset_direction=asset_direction,
            delta_pct=delta_pct,
            fair_value=fair_value,
            token_ask=token_ask,
            edge=edge,
            entry_price=entry_price,
            confidence=confidence,
            composite=composite,
            direction=Direction.BUY_YES,   # always "buy this token" (side already aligned above)
            fee_zone=fee_zone,
            elapsed_pct=elapsed_pct,
            reason=reason,
            is_prearm=is_prearmed,
            vpin_at_entry=round(vpin, 4) if vpin > 0 else 0.0,
            llm_boost_at_entry=round(abs(macro_boost), 4) if macro_boost else 0.0,
            pm_ask_at_trigger=round(ask_at_trigger, 4) if ask_at_trigger > 0 else 0.0,
            pm_drift_at_entry=round(pm_drift, 4),
            lag_remaining_pct=round(lag_remaining_pct, 3),
        )
