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

# Session-aware minimum delta: quiet-hour moves <0.20% are noise (40% sustain rate).
# Matches macro_engine thresholds so both engines agree on what constitutes a signal.
# All 3 sniper losses (T00020/22/25) were quiet-hour trades at 0.066–0.079% delta.
_HIGH_VOLUME_HOURS = {8, 9, 13, 14, 15, 22, 23, 0}
_DELTA_PCT_ACTIVE = 0.15   # lowered 0.20→0.15: sustain gate now does wick-filtering
                           # 0.15% → FV=0.77, edge≥0.17 at ask≤0.60. ~2× more opportunities.
                           # Old 0.20% was approximating "not a wick"; sustain gate does that now.
_DELTA_PCT_QUIET  = 0.35   # 0.35% during quiet hours — raises bar to filter noise (unchanged)

MIN_EDGE = 0.04             # fair_value - token_ask ≥ this to enter
MIN_EDGE_VPIN = 0.03        # reduced gate when VPIN confirms direction
MIN_EDGE_BOOST = 0.02       # reduced gate when LLM macro_boost confirms
WINDOW_ELAPSED_MIN = 0.40   # raised 0.35→0.40: 20-trade data — all 3 losses at ≤35% elapsed; both wins at 40-45%
WINDOW_ELAPSED_MAX = 0.80   # no entry after 80% (too late)
VPIN_CONFIRM_THRESHOLD = 0.60   # VPIN above this = informed flow
LLM_BOOST_STRONG = 0.05     # macro_boost magnitude above this = LLM confirms
MIN_TOKEN_ASK = 0.40        # skip near-resolved tokens (mirrors risk manager gate)
MAX_TOKEN_ASK = 0.60        # skip if market has already priced in the move (>60¢)


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


def _session_min_delta() -> float:
    """Return minimum asset % move required to fire, based on current UTC hour."""
    hour = datetime.now(timezone.utc).hour
    return _DELTA_PCT_ACTIVE if hour in _HIGH_VOLUME_HOURS else _DELTA_PCT_QUIET


# Window-size-aware sustain period:
#   5-min windows (≤300s): 20s — wicks reverse in <15s; 30s too narrow (only 90s
#     first-breach window available between elapsed 40-70%). 20s still filters noise.
#   15-min+ windows  (>300s): 30s — 330s first-breach window; stricter confirmation OK.
_SUSTAINED_5M = 20.0
_SUSTAINED_15M = 30.0


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

        # ── Time gate ──────────────────────────────────────────────────────────
        if token.window_end_ts <= 0 or token.window_seconds <= 0:
            return None  # no timing data (stub mode without window expiry set)

        window_start = token.window_end_ts - token.window_seconds
        elapsed = now - window_start
        elapsed_pct = elapsed / token.window_seconds

        if elapsed_pct < WINDOW_ELAPSED_MIN:
            return None  # too early — wait for move to confirm
        if elapsed_pct > WINDOW_ELAPSED_MAX:
            return None  # too late — margin too thin; hard exit looming

        # ── Delta computation ──────────────────────────────────────────────────
        delta_pct = (spot_current - spot_window_open) / spot_window_open * 100

        min_delta = _session_min_delta()
        if abs(delta_pct) < min_delta:
            # Delta below threshold — clear any sustained timers for this token.
            # If the move reverses/fades, we reset so next breach starts fresh.
            self._delta_sustained_since.pop((token.token_id, 1), None)
            self._delta_sustained_since.pop((token.token_id, -1), None)
            logger.debug(
                "SNIPER SKIP %s/%s | delta=%.3f%% < session_min=%.2f%% (%s)",
                token.asset, token.side, delta_pct, min_delta,
                "active" if datetime.now(timezone.utc).hour in _HIGH_VOLUME_HOURS else "quiet",
            )
            return None  # asset hasn't moved enough to create a mispricing gap

        asset_direction = 1 if delta_pct > 0 else -1

        # ── Sustained delta gate ───────────────────────────────────────────────
        # Require delta to hold above threshold before firing.
        # Period is window-size-aware: 20s for 5-min (≤300s), 30s for 15-min+.
        # Filters out wicks (5-15s spike that reverses) vs genuine macro moves (20s+).
        # Data rationale: all 3 sniper losses were likely wick entries — delta at entry
        # was quickly fading, not a sustained directional move.
        required_sustain = _SUSTAINED_5M if token.window_seconds <= 300 else _SUSTAINED_15M

        sustain_key = (token.token_id, asset_direction)
        opp_key = (token.token_id, -asset_direction)
        self._delta_sustained_since.pop(opp_key, None)  # clear reversed-direction timer

        if sustain_key not in self._delta_sustained_since:
            self._delta_sustained_since[sustain_key] = now
            logger.debug(
                "SNIPER SUSTAIN_START %s/%s | delta=%.3f%% — waiting %.0fs confirmation",
                token.asset, token.side, delta_pct, required_sustain,
            )
            return None  # first breach — start sustain timer

        sustained_for = now - self._delta_sustained_since[sustain_key]
        if sustained_for < required_sustain:
            logger.debug(
                "SNIPER SUSTAIN_WAIT %s/%s | delta=%.3f%% held %.1fs / %.0fs",
                token.asset, token.side, delta_pct, sustained_for, required_sustain,
            )
            return None  # not yet sustained — wait

        # ── Side alignment: only trade the winning token ───────────────────────
        # YES wins when asset goes up; NO wins when asset goes down.
        # Skip the losing side — we never short; we only buy the correct token.
        if token.side == "YES" and asset_direction < 0:
            return None  # asset falling → YES token goes to 0 → not a buy
        if token.side == "NO" and asset_direction > 0:
            return None  # asset rising → NO token goes to 0 → not a buy

        # ── Fair value via sigmoid ─────────────────────────────────────────────
        # sigmoid(k * |delta|) gives probability the winning side wins.
        # For YES: delta > 0 → sigmoid(positive) → near 1.0
        # For NO:  delta < 0 → sigmoid(|delta|) → near 1.0 (since NO is the winner)
        directional_delta = abs(delta_pct)
        fair_value = 1.0 / (1.0 + math.exp(-SIGMOID_K * directional_delta))

        # ── Token ask and edge ─────────────────────────────────────────────────
        token_ask = ob.asks[0][0]
        if token_ask <= 0:
            return None

        # Skip near-resolved tokens: mirrors risk/manager.py updown gate [0.40, 0.60].
        # Above 0.60: market has priced in the move; insufficient edge remains.
        # Below 0.40: near-resolved the other way; we'd be fighting the resolved side.
        if token_ask > MAX_TOKEN_ASK or token_ask < MIN_TOKEN_ASK:
            return None

        edge = fair_value - token_ask
        if edge <= 0:
            return None  # token overpriced relative to fair value

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
        reason = (
            f"Sniper: {token.asset} {delta_pct:+.3f}% from window open | "
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
        )
