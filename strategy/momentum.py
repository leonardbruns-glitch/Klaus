"""
Klaus — Momentum Scalper Strategy
Replaces the naive price < 0.30 entry with a multi-factor momentum signal.

Signal pipeline:
  1. Breakout detection     (5-min bars)
  2. Trend alignment        (15-min EMA crossover)
  3. Volume surge           (volume vs rolling average)
  4. Order-book imbalance   (bid / ask depth ratio)
  5. Optional external boosts (funding rate, spot momentum)
  ──────────────────────────────────────────────────────
  → Composite MomentumScore  [0, 1]
  → Direction  (BUY_YES / BUY_NO / NO_TRADE)
  → Fee zone classification  (EXTREME / FAT_MIDDLE)
  → Entry price & confidence
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional
import logging

from config import CONFIG, MomentumConfig
from data.feeds import Bar, OrderBook, ExternalSignal

logger = logging.getLogger("strategy")


# ---------------------------------------------------------------------------
# Enumerations & output types
# ---------------------------------------------------------------------------

class Direction(Enum):
    BUY_YES = auto()    # buy YES token (price expected to rise toward 1.0)
    BUY_NO = auto()     # buy NO token  (price of YES expected to fall)
    NO_TRADE = auto()


class FeeZone(Enum):
    EXTREME = auto()    # price < 0.35 or > 0.65  → low fee
    FAT_MIDDLE = auto() # price 0.35 – 0.65       → high fee; needs 80 % conf


@dataclass
class SignalBreakdown:
    breakout_score: float = 0.0   # 0-1
    trend_score: float = 0.0
    volume_score: float = 0.0
    ob_score: float = 0.0
    external_boost: float = 0.0   # additive bonus from external data
    composite: float = 0.0
    direction: Direction = Direction.NO_TRADE
    entry_price: float = 0.0
    fee_zone: FeeZone = FeeZone.FAT_MIDDLE
    confidence: float = 0.0       # final adjusted confidence
    reason: str = ""              # human-readable explanation


# ---------------------------------------------------------------------------
# EMA helpers
# ---------------------------------------------------------------------------

def ema(values: List[float], period: int) -> List[float]:
    """Exponential moving average; returns list same length as input."""
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def rolling_avg(values: List[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def atr(bars: List[Bar], period: int = 14) -> float:
    """Average True Range on binary-price bars."""
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(len(trs), period)


# ---------------------------------------------------------------------------
# Individual signal scorers
# ---------------------------------------------------------------------------

def score_breakout(bars_5m: List[Bar], cfg: MomentumConfig) -> tuple[float, Direction]:
    """
    Detects price breakout from N-bar range.
    Returns (score 0-1, direction).
    """
    n = cfg.breakout_lookback
    if len(bars_5m) < n + 1:
        return 0.0, Direction.NO_TRADE

    lookback = bars_5m[-(n + 1):-1]   # exclude the latest bar
    range_high = max(b.high for b in lookback)
    range_low = min(b.low for b in lookback)
    range_size = range_high - range_low
    if range_size < 1e-6:
        return 0.0, Direction.NO_TRADE

    latest = bars_5m[-1]
    close = latest.close

    # Breakout above range high
    if close > range_high:
        # score = how far above range (normalised by range size, capped at 1)
        score = min(1.0, (close - range_high) / range_size)
        return score, Direction.BUY_YES

    # Breakout below range low
    if close < range_low:
        score = min(1.0, (range_low - close) / range_size)
        return score, Direction.BUY_NO

    # Inside range — score based on proximity to edges
    if (range_high - close) < (close - range_low):
        # closer to top; weak bullish lean
        proximity = (close - range_low) / range_size
        return proximity * 0.4, Direction.BUY_YES
    else:
        proximity = (range_high - close) / range_size
        return proximity * 0.4, Direction.BUY_NO


def score_trend(bars_15m: List[Bar], cfg: MomentumConfig) -> tuple[float, Direction]:
    """
    EMA fast/slow crossover on 15-min bars.
    Returns (score 0-1, aligned direction).
    """
    min_bars = cfg.ema_slow + 1
    if len(bars_15m) < min_bars:
        return 0.0, Direction.NO_TRADE

    closes = [b.close for b in bars_15m]
    fast = ema(closes, cfg.ema_fast)
    slow = ema(closes, cfg.ema_slow)

    if not fast or not slow:
        return 0.0, Direction.NO_TRADE

    f_now, f_prev = fast[-1], fast[-2] if len(fast) >= 2 else fast[-1]
    s_now = slow[-1]

    if f_now > s_now:
        # Bullish: score based on separation
        sep = (f_now - s_now) / s_now if s_now > 0 else 0
        momentum = f_now - f_prev  # EMA slope
        score = min(1.0, sep * 20 + max(0, momentum) * 50)
        return score, Direction.BUY_YES
    else:
        sep = (s_now - f_now) / s_now if s_now > 0 else 0
        momentum = f_prev - f_now
        score = min(1.0, sep * 20 + max(0, momentum) * 50)
        return score, Direction.BUY_NO


def score_volume(bars_5m: List[Bar], cfg: MomentumConfig) -> float:
    """
    Volume surge: latest bar volume vs rolling average.
    Score = ratio / (surge_mult * 2), capped at 1.
    """
    if len(bars_5m) < 5:
        return 0.0
    avg_vol = rolling_avg([b.volume for b in bars_5m[:-1]], 10)
    if not avg_vol or avg_vol < 1e-9:
        return 0.0
    ratio = bars_5m[-1].volume / avg_vol
    # normalise: at 1x avg → 0.25, at surge_mult → ~0.5, at 3x → ~1.0
    score = min(1.0, (ratio - 1.0) / (cfg.volume_surge_mult * 2))
    return max(0.0, score)


def score_order_book(ob: Optional[OrderBook], cfg: MomentumConfig) -> tuple[float, Direction]:
    """
    Bid/ask depth imbalance.
    Returns (score, direction implied by imbalance).
    """
    if ob is None:
        return 0.5, Direction.NO_TRADE  # neutral; don't penalise missing OB

    imb = ob.imbalance  # > 0.5 = bid heavy = bullish
    threshold = cfg.ob_imbalance_thresh

    if imb >= threshold:
        score = max(0.0, (imb - 0.5) / 0.5)   # 0 at 0.5, 1 at 1.0; clamped ≥ 0
        return score, Direction.BUY_YES
    elif imb <= (1 - threshold):
        score = max(0.0, (0.5 - imb) / 0.5)
        return score, Direction.BUY_NO
    else:
        return 0.0, Direction.NO_TRADE


def external_signal_boost(signal: Optional[ExternalSignal], direction: Direction) -> float:
    """
    Additive boost from optional external data.
    Never blocks a trade if missing. Max boost = 0.10 (keeps composite below 1).
    """
    if signal is None:
        return 0.0

    boost = 0.0

    # Spot momentum alignment
    if signal.spot_momentum_5m is not None:
        spot_dir = Direction.BUY_YES if signal.spot_momentum_5m > 0 else Direction.BUY_NO
        if spot_dir == direction:
            boost += min(0.05, abs(signal.spot_momentum_5m) / 5 * 0.05)

    if signal.spot_momentum_15m is not None:
        spot_dir_15 = Direction.BUY_YES if signal.spot_momentum_15m > 0 else Direction.BUY_NO
        if spot_dir_15 == direction:
            boost += min(0.03, abs(signal.spot_momentum_15m) / 5 * 0.03)

    # Funding rate: extreme positive funding → contrarian NO signal
    if signal.funding_rate is not None:
        if signal.funding_rate > 50 and direction == Direction.BUY_NO:
            boost += 0.02
        elif signal.funding_rate < -20 and direction == Direction.BUY_YES:
            boost += 0.02

    return min(0.10, boost)


# ---------------------------------------------------------------------------
# Fee zone classifier
# ---------------------------------------------------------------------------

def classify_fee_zone(price: float, cfg=CONFIG.fees) -> FeeZone:
    if price < cfg.extreme_low or price > cfg.extreme_high:
        return FeeZone.EXTREME
    return FeeZone.FAT_MIDDLE


# ---------------------------------------------------------------------------
# Composite scorer (main entry point)
# ---------------------------------------------------------------------------

class MomentumScorer:
    """
    Combines all sub-scores into a final MomentumScore decision.
    Called once per token per scan cycle.
    """

    def __init__(self) -> None:
        self.cfg = CONFIG.momentum
        self.fee_cfg = CONFIG.fees

    def score(
        self,
        bars_5m: List[Bar],
        bars_15m: List[Bar],
        ob: Optional[OrderBook],
        ext: Optional[ExternalSignal] = None,
    ) -> SignalBreakdown:

        sig = SignalBreakdown()

        # ── Sub-scores ────────────────────────────────────────────────────────
        breakout_s, breakout_dir = score_breakout(bars_5m, self.cfg)
        trend_s, trend_dir = score_trend(bars_15m, self.cfg)
        volume_s = score_volume(bars_5m, self.cfg)
        ob_s, ob_dir = score_order_book(ob, self.cfg)

        sig.breakout_score = breakout_s
        sig.trend_score = trend_s
        sig.volume_score = volume_s
        sig.ob_score = ob_s

        # ── Direction consensus ───────────────────────────────────────────────
        direction_votes = [
            (breakout_dir, self.cfg.w_breakout),
            (trend_dir, self.cfg.w_trend),
            (ob_dir, self.cfg.w_ob),
        ]
        yes_weight = sum(w for d, w in direction_votes if d == Direction.BUY_YES)
        no_weight = sum(w for d, w in direction_votes if d == Direction.BUY_NO)

        if yes_weight > no_weight:
            sig.direction = Direction.BUY_YES
        elif no_weight > yes_weight:
            sig.direction = Direction.BUY_NO
        else:
            sig.direction = Direction.NO_TRADE

        # ── Weighted composite ────────────────────────────────────────────────
        if sig.direction == Direction.BUY_YES:
            aligned_breakout = breakout_s if breakout_dir == Direction.BUY_YES else 0
            aligned_trend = trend_s if trend_dir == Direction.BUY_YES else 0
            # Only count OB score when it explicitly agrees; NO_TRADE = neutral (zero)
            aligned_ob = ob_s if ob_dir == Direction.BUY_YES else 0
        elif sig.direction == Direction.BUY_NO:
            aligned_breakout = breakout_s if breakout_dir == Direction.BUY_NO else 0
            aligned_trend = trend_s if trend_dir == Direction.BUY_NO else 0
            aligned_ob = ob_s if ob_dir == Direction.BUY_NO else 0
        else:
            sig.composite = 0.0
            sig.confidence = 0.0
            sig.reason = "No direction consensus"
            return sig

        composite = (
            aligned_breakout * self.cfg.w_breakout
            + aligned_trend * self.cfg.w_trend
            + volume_s * self.cfg.w_volume
            + aligned_ob * self.cfg.w_ob
        )
        sig.composite = min(1.0, composite)

        # ── External boost ────────────────────────────────────────────────────
        sig.external_boost = external_signal_boost(ext, sig.direction)

        # ── Entry price & fee zone ────────────────────────────────────────────
        # Always use the actual ask price of the token being evaluated.
        # For YES tokens → YES ask (e.g. 0.24).
        # For NO tokens  → NO ask  (e.g. 0.76).
        # Direction flip for NO tokens is handled in main._scan_for_signals().
        if ob:
            sig.entry_price = ob.asks[0][0] if ob.asks else ob.mid
        else:
            sig.entry_price = 0.0

        # Fee zone uses the actual token price being bought (already correct for both sides)
        sig.fee_zone = classify_fee_zone(sig.entry_price)

        # ── Confidence & gate checks ──────────────────────────────────────────
        sig.confidence = min(1.0, sig.composite + sig.external_boost)

        # NOTE: Fat-middle confidence gate is handled in risk/manager.py
        # (market-type-aware: 52% for updown, 80% for target).
        # Do NOT gate here — scorer doesn't know market_type.

        # Minimum score gate
        if sig.composite < self.cfg.min_score:
            sig.direction = Direction.NO_TRADE
            sig.reason = (
                f"Below min_score: {sig.composite:.2f} < {self.cfg.min_score}"
            )
            return sig

        # ── Reason string ─────────────────────────────────────────────────────
        parts = []
        if breakout_s > 0.4:
            parts.append(f"breakout={breakout_s:.2f}")
        if trend_s > 0.3:
            parts.append(f"trend={trend_s:.2f}")
        if volume_s > 0.3:
            parts.append(f"vol_surge={volume_s:.2f}")
        if ob_s > 0.3:
            parts.append(f"ob_imb={ob_s:.2f}")
        if sig.external_boost > 0.01:
            parts.append(f"ext_boost={sig.external_boost:.2f}")
        sig.reason = " | ".join(parts) if parts else "composite signal"

        return sig


# ---------------------------------------------------------------------------
# Dynamic TP / SL calculator
# ---------------------------------------------------------------------------

@dataclass
class TPSLLevels:
    take_profit: float   # target exit price
    stop_loss: float     # stop price
    tp_pct: float        # TP % from entry
    sl_pct: float        # SL % from entry
    risk_reward: float


def calculate_tp_sl(
    entry_price: float,
    direction: Direction,
    bars_5m: List[Bar],
    ob: Optional[OrderBook],
    volatility_multiplier: float = 1.0,
) -> TPSLLevels:
    """
    Dynamic TP/SL based on ATR and order-book spread.
    - TP = 2× ATR above entry (BUY_YES)
    - SL = 1× ATR below entry
    - Adjusted by volatility_multiplier for high-vol sessions.
    """
    atr_val = atr(bars_5m)
    spread = ob.spread if ob else 0.01

    # Minimum pip = spread or 0.005, whichever larger
    base_unit = max(spread, 0.005) * volatility_multiplier

    if atr_val > 0:
        tp_distance = max(atr_val * 2.0, base_unit * 3)
        sl_distance = max(atr_val * 1.0, base_unit * 1.5)
    else:
        tp_distance = base_unit * 3
        sl_distance = base_unit * 1.5

    # Cap to avoid unrealistic levels on binary [0,1] assets
    tp_distance = min(tp_distance, 0.15)
    sl_distance = min(sl_distance, 0.08)

    # Both BUY_YES and BUY_NO: we buy the token at entry and want price to rise.
    # (For NO tokens the direction flip in main.py ensures entry_price is the
    #  actual NO token ask, so rising NO price = profit — same math as BUY_YES.)
    tp = min(0.98, entry_price + tp_distance)
    sl = max(0.01, entry_price - sl_distance)

    rr = tp_distance / sl_distance if sl_distance > 0 else 0.0

    return TPSLLevels(
        take_profit=round(tp, 4),
        stop_loss=round(sl, 4),
        tp_pct=round(tp_distance / entry_price * 100, 2) if entry_price > 0 else 0.0,
        sl_pct=round(sl_distance / entry_price * 100, 2) if entry_price > 0 else 0.0,
        risk_reward=round(rr, 2),
    )
