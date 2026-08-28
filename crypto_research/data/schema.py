"""Typed record schemas for the crypto_research data layer.

This module defines lightweight ``@dataclass`` records that mirror the
on-disk JSONL streams documented in ``CRYPTO_DATA_BLUEPRINT.md`` plus the
ground-truth loader facts from phase 1.

Design principles
------------------
* **One dataclass per physical stream** — field names match the JSONL keys
  exactly so a row can be constructed with ``Record.from_dict(json_obj)``.
* **Unknown / future fields are tolerated** — ``from_dict`` ignores keys it
  does not recognise (the Tier-1 schema is ``schema_version=2`` and may grow).
* **Time-unit discipline** is encoded in the field names and docstrings:
  ``ts_s`` / ``window_end_ts`` are epoch **seconds**; ``ts_ms_local`` /
  ``exchange_ts_ms`` are epoch **milliseconds**.  The blueprint's two
  collection eras disagree on which fields exist, so most numeric fields are
  ``Optional`` and default to ``None``.

The composite join key for the Tier-1 feature era is
``(asset, window_end_ts, window_size_s)``.  ``window_resolution`` is the
clean supervised label set; the label ``resolved_yes`` is for the UP token,
and the DOWN/NO token's label is the complement ``1 - resolved_yes``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar

import numpy as np

_T = TypeVar("_T", bound="_Record")


class _Record:
    """Mixin providing a tolerant ``from_dict`` constructor.

    ``from_dict`` only consumes keys that correspond to declared dataclass
    fields; everything else is dropped.  This keeps the loader robust across
    the legacy / Tier-1 schema split where extra fields appear and disappear.
    """

    @classmethod
    def _field_names(cls: Type[_T]) -> frozenset:
        cache_attr = "_field_name_cache"
        cached = cls.__dict__.get(cache_attr)
        if cached is None:
            cached = frozenset(f.name for f in fields(cls))  # type: ignore[arg-type]
            setattr(cls, cache_attr, cached)
        return cached

    @classmethod
    def from_dict(cls: Type[_T], obj: Dict[str, Any]) -> _T:
        """Build a record from a parsed JSON object, ignoring unknown keys."""
        names = cls._field_names()
        kwargs = {k: v for k, v in obj.items() if k in names}
        return cls(**kwargs)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Raw stream records
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BinanceTrade(_Record):
    """One Binance-futures aggregated-trade tick (``binance_trade.jsonl``).

    NOTE (loader fact): this stream carries **no** ``token_id`` /
    ``condition_id`` / ``window_end_ts``.  To attach a tick to a Polymarket
    window you must bucket ``ts_s`` into ``[window_end_ts - window_size_s,
    window_end_ts)`` for the chosen asset and window grid (300 or 900).
    """

    ts_s: float
    asset: str
    price: float
    qty: float
    is_buyer_maker: Optional[bool] = None
    taker_side: Optional[str] = None  # 'BUY' | 'SELL'
    ts_ms_local: Optional[int] = None  # epoch ms (our clock)
    exchange_ts_ms: Optional[int] = None  # epoch ms (exchange clock; prefer for ordering)
    schema_version: Optional[int] = None
    record_type: Optional[str] = None

    @property
    def signed_qty(self) -> float:
        """Qty signed by aggressor side: +qty taker BUY, -qty taker SELL.

        ``is_buyer_maker == True`` means the buyer was the resting maker, so
        the aggressor was a SELL.  We prefer the explicit ``taker_side`` when
        present and fall back to ``is_buyer_maker``.
        """
        if self.taker_side is not None:
            return self.qty if self.taker_side.upper() == "BUY" else -self.qty
        if self.is_buyer_maker is not None:
            return -self.qty if self.is_buyer_maker else self.qty
        return 0.0


@dataclass(slots=True)
class MarketTimelineRow(_Record):
    """One row of the primary Polymarket feature panel (``market_timeline``).

    Carries BOTH the YES(up) and NO(down) tokens per window as separate
    ``token_id`` rows.  ``window_size_s`` IS present on this stream, so the
    composite label key ``(asset, window_end_ts, window_size_s)`` is direct.
    """

    ts_s: float
    token_id: str
    asset: str
    window_end_ts: int  # epoch seconds
    # --- identity / window ---
    condition_id: Optional[str] = None
    outcome_dir: Optional[str] = None  # 'up' | 'down'
    outcome_side: Optional[str] = None  # 'YES' | 'NO'
    window_size_s: Optional[int] = None  # 300 | 900
    seconds_to_resolution: Optional[float] = None
    ts_ms_local: Optional[int] = None
    schema_version: Optional[int] = None
    record_type: Optional[str] = None
    # --- calendar ---
    weekday: Optional[int] = None
    hour_utc: Optional[int] = None
    minute_utc: Optional[int] = None
    session_bucket: Optional[str] = None
    # --- Polymarket book ---
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid: Optional[float] = None
    spread_abs: Optional[float] = None
    spread_bps: Optional[float] = None
    ob_top1_bid_size: Optional[float] = None
    ob_top1_ask_size: Optional[float] = None
    ob_imb_top3: Optional[float] = None
    ob_book_depth_size: Optional[float] = None
    ob_levels_bid: Optional[int] = None
    ob_levels_ask: Optional[int] = None
    ob_quote_age_ms: Optional[float] = None
    # --- token momentum snaps ---
    tok_snap_30s: Optional[float] = None
    tok_snap_60s: Optional[float] = None
    tok_history_seconds: Optional[float] = None
    # --- Binance spot context ---
    binance_spot: Optional[float] = None
    binance_vel_5s_pct: Optional[float] = None
    binance_ret_30s_pct: Optional[float] = None
    binance_ret_60s_pct: Optional[float] = None
    binance_ret_1m_pct: Optional[float] = None
    binance_ret_5m_pct: Optional[float] = None
    binance_ret_15m_pct: Optional[float] = None
    binance_ret_60m_pct: Optional[float] = None
    # --- peer (the opposite token) ---
    peer_token_id: Optional[str] = None
    peer_bid: Optional[float] = None
    peer_ask: Optional[float] = None
    peer_age_ms: Optional[float] = None
    arb_sum_yes_no: Optional[float] = None
    # --- regimes / flow ---
    vol_regime: Optional[str] = None
    trend_regime: Optional[str] = None
    liquidity_regime: Optional[str] = None
    macro_event_window: Optional[bool] = None
    vpin_score: Optional[float] = None
    tok_delta_5s: Optional[float] = None
    tok_decel_ratio: Optional[float] = None
    ask_stale_s: Optional[float] = None


@dataclass(slots=True)
class ObDelta(_Record):
    """One L2 order-book event from ``ob_delta.jsonl``.

    NOTE (loader fact): **no** ``window_size_s`` on this stream.  Recover it
    from ``window_end_ts`` congruence (``% 300`` / ``% 900``) disambiguated
    via the matching ``token_id`` from ``market_timeline``.
    """

    ts_s: float
    token_id: str
    asset: str
    window_end_ts: int
    condition_id: Optional[str] = None
    outcome_dir: Optional[str] = None
    outcome_side: Optional[str] = None
    seconds_to_resolution: Optional[float] = None
    ts_ms_local: Optional[int] = None
    exchange_ts_ms: Optional[int] = None
    schema_version: Optional[int] = None
    record_type: Optional[str] = None
    event_type: Optional[str] = None  # e.g. 'best_bid_ask'
    level_price: Optional[float] = None
    level_size: Optional[float] = None
    level_side: Optional[str] = None  # 'BBO' | 'bid' | 'ask'
    level_hash: Optional[str] = None
    level_rank: Optional[int] = None
    best_bid_at_event: Optional[float] = None
    best_ask_at_event: Optional[float] = None
    ask_top3: Optional[List[List[float]]] = None  # [[price, size], ...]
    bid_top3: Optional[List[List[float]]] = None


@dataclass(slots=True)
class TokenTrade(_Record):
    """One Polymarket executed print (``token_trade.jsonl``).

    WARNING (loader fact): ``fee_rate_bps`` is logged ``0.0`` for 100% of
    rows and MUST NOT be trusted.  Fees are modelled via an injectable
    ``fee_fn(price, shares)`` in the backtester.
    """

    ts_s: float
    token_id: str
    asset: str
    window_end_ts: int
    price: float
    size: float
    side: Optional[str] = None  # 'BUY' | 'SELL'
    condition_id: Optional[str] = None
    outcome_dir: Optional[str] = None
    outcome_side: Optional[str] = None
    seconds_to_resolution: Optional[float] = None
    ts_ms_local: Optional[int] = None
    exchange_ts_ms: Optional[int] = None
    transaction_hash: Optional[str] = None
    fee_rate_bps: Optional[float] = None  # ALWAYS 0.0 — DO NOT TRUST
    schema_version: Optional[int] = None
    record_type: Optional[str] = None


@dataclass(slots=True)
class WindowResolution(_Record):
    """One resolved-window label (``window_resolution.jsonl``) — CLEAN LABELS.

    ONE row per ``(asset, window_end_ts, window_size_s)``.  The label is for
    the UP token: ``resolved_yes == 1`` iff the UP token resolved YES.

    IMPORTANT (confirmed quirk): the ``_5m`` suffix on ``binance_open_5m`` /
    ``binance_close_5m`` / ``binance_high_5m`` / ``binance_low_5m`` is a
    **misnomer** — these are the FULL-window open/close/high/low spanning the
    whole ``window_size_s`` (300 *or* 900), not a 5-minute sub-slice.
    ``realized_move_pct == (close - open) / open * 100``.
    """

    asset: str
    window_end_ts: int
    window_size_s: int
    condition_id: Optional[str] = None
    outcome_dir: Optional[str] = None  # 'up'
    ts_resolved_s: Optional[int] = None  # epoch seconds
    binance_open_5m: Optional[float] = None  # window OPEN (misnomer suffix)
    binance_close_5m: Optional[float] = None  # window CLOSE
    binance_high_5m: Optional[float] = None  # window HIGH
    binance_low_5m: Optional[float] = None  # window LOW
    realized_move_pct: Optional[float] = None
    moved_up: Optional[bool] = None
    resolved_yes: Optional[int] = None  # label for the UP token (0/1)
    resolution_method: Optional[str] = None
    resolution_delay_s: Optional[float] = None
    resolution_source: Optional[str] = None  # 'binance_kline'
    schema_version: Optional[int] = None

    @property
    def key(self) -> "WindowKey":
        """Composite join key ``(asset, window_end_ts, window_size_s)``."""
        return (self.asset, int(self.window_end_ts), int(self.window_size_s))


# Composite key type used throughout the loader / engine.
WindowKey = tuple  # (asset: str, window_end_ts: int, window_size_s: int)


# ---------------------------------------------------------------------------
# Aligned panel: feature time-series + label for ONE token-window
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WindowPanel:
    """A time-aligned panel for ONE token-window: features + the label.

    A panel bundles everything a strategy needs to evaluate a single
    Polymarket up/down token over its life:

    * the per-step Polymarket feature time-series (one ``MarketTimelineRow``
      per observed timestamp, sorted ascending by ``ts_s``);
    * optional raw Binance ticks / order-book deltas / token prints bucketed
      into the window (kept lazy/optional to bound memory);
    * the resolved label (``resolved_yes`` for THIS token's direction).

    The panel is the unit the :class:`BacktestEngine` iterates.  A strategy's
    ``on_step`` is called once per timeline row with a context that can only
    see rows ``<= t`` (no look-ahead — enforced by the engine).

    Attributes
    ----------
    asset, window_end_ts, window_size_s
        Composite window identity.
    token_id
        The specific Polymarket token this panel tracks.
    outcome_dir, outcome_side
        ``'up'``/``'down'`` and ``'YES'``/``'NO'`` for this token.
    timeline
        Ascending-``ts_s`` list of feature rows (the primary panel).
    label_resolved_yes
        Binary outcome for THIS token (already complemented for NO tokens):
        1 if this token resolves YES, else 0.  ``None`` if unlabeled.
    realized_move_pct, binance_open, binance_close, binance_high, binance_low
        Window settlement OHLC + move (from ``window_resolution``).
    binance_ticks, ob_deltas, token_trades
        Optional bucketed raw streams (may be empty to save memory).
    """

    asset: str
    window_end_ts: int
    window_size_s: int
    token_id: str
    outcome_dir: Optional[str] = None
    outcome_side: Optional[str] = None
    timeline: List[MarketTimelineRow] = field(default_factory=list)
    label_resolved_yes: Optional[int] = None
    realized_move_pct: Optional[float] = None
    binance_open: Optional[float] = None
    binance_close: Optional[float] = None
    binance_high: Optional[float] = None
    binance_low: Optional[float] = None
    binance_ticks: List[BinanceTrade] = field(default_factory=list)
    ob_deltas: List[ObDelta] = field(default_factory=list)
    token_trades: List[TokenTrade] = field(default_factory=list)

    # -- identity -----------------------------------------------------------
    @property
    def key(self) -> WindowKey:
        """``(asset, window_end_ts, window_size_s)`` join key."""
        return (self.asset, int(self.window_end_ts), int(self.window_size_s))

    @property
    def is_up_token(self) -> bool:
        """True if this panel tracks the UP/YES token."""
        if self.outcome_dir is not None:
            return self.outcome_dir.lower() == "up"
        if self.outcome_side is not None:
            return self.outcome_side.upper() == "YES"
        return True

    @property
    def n_steps(self) -> int:
        return len(self.timeline)

    @property
    def window_start_ts(self) -> int:
        return int(self.window_end_ts) - int(self.window_size_s)

    def sort(self) -> "WindowPanel":
        """Sort the timeline (and raw streams) ascending by time, in place."""
        self.timeline.sort(key=lambda r: r.ts_s)
        self.binance_ticks.sort(key=lambda t: (t.exchange_ts_ms or t.ts_ms_local or t.ts_s * 1000.0))
        self.ob_deltas.sort(key=lambda d: (d.exchange_ts_ms or d.ts_ms_local or d.ts_s * 1000.0))
        self.token_trades.sort(key=lambda t: (t.exchange_ts_ms or t.ts_ms_local or t.ts_s * 1000.0))
        return self

    def first_ts(self) -> float:
        """Earliest timeline timestamp (epoch seconds); window start if empty."""
        return self.timeline[0].ts_s if self.timeline else float(self.window_start_ts)

    def asof_index(self, ts_s: float) -> int:
        """Largest index ``i`` with ``timeline[i].ts_s <= ts_s`` (else -1).

        Used by the engine to build a strictly causal history view.  Assumes
        ``timeline`` is sorted ascending.
        """
        lo, hi, ans = 0, len(self.timeline) - 1, -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.timeline[mid].ts_s <= ts_s:
                ans = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return ans

    def mid_series(self) -> np.ndarray:
        """Array of ``mid`` over the timeline (NaN where missing)."""
        return np.array(
            [r.mid if r.mid is not None else np.nan for r in self.timeline],
            dtype=float,
        )


def panels_to_frame(panels: Sequence[WindowPanel]):
    """Flatten panels to a one-row-per-window pandas DataFrame (labels + meta).

    Convenience for offline EDA / calibration; does NOT include the full
    per-step feature time-series (use the panels directly for that).
    """
    import pandas as pd

    rows = []
    for p in panels:
        rows.append(
            {
                "asset": p.asset,
                "window_end_ts": p.window_end_ts,
                "window_size_s": p.window_size_s,
                "token_id": p.token_id,
                "outcome_dir": p.outcome_dir,
                "outcome_side": p.outcome_side,
                "n_steps": p.n_steps,
                "label_resolved_yes": p.label_resolved_yes,
                "realized_move_pct": p.realized_move_pct,
                "binance_open": p.binance_open,
                "binance_close": p.binance_close,
                "binance_high": p.binance_high,
                "binance_low": p.binance_low,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "BinanceTrade",
    "MarketTimelineRow",
    "ObDelta",
    "TokenTrade",
    "WindowResolution",
    "WindowPanel",
    "WindowKey",
    "panels_to_frame",
]
