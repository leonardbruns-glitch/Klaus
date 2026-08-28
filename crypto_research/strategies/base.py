"""Strategy interface contract: the ABC, Signal, StrategyContext, Params.

This is the **single contract** every one of the four strategies conforms to.
The :class:`~crypto_research.backtest.engine.BacktestEngine` constructs a
:class:`StrategyContext` for each causal step and calls
:meth:`Strategy.on_step`; the returned :class:`Signal` list is routed through
the bimodal fill model and the portfolio.

NON-HFT mandate
---------------
``on_step`` is called at **bar cadence** (once per ``market_timeline`` row,
typically seconds-to-minutes apart), never per tick.  A strategy expresses a
*structural / probabilistic* edge (mispricing of ``mid`` vs realised outcome
distribution, funding basis, order-flow imbalance over a bar), decided from
features available at time ``t``.  It must not depend on sub-bar latency.

No look-ahead
-------------
The engine guarantees a :class:`StrategyContext` only exposes data with
``ts_s <= t``.  ``ctx.history`` is the causal slice of the panel timeline up
to and including the current row; ``ctx.row`` is the current row; the
resolution label is hidden until settlement.  Strategies MUST NOT read
``panel.label_resolved_yes`` / ``panel.binance_close`` during ``on_step``
(those are the answer).  The engine does not pass the panel object into the
context for exactly this reason.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence

from ..data.schema import MarketTimelineRow, WindowPanel

# Allowed order sides a strategy may emit.
SignalSide = Literal["BUY_YES", "BUY_NO", "HEDGE", "FLAT"]


@dataclass
class Signal:
    """An order intent emitted by a strategy at one step.

    Attributes
    ----------
    side
        * ``'BUY_YES'`` — buy the UP token of the current window.
        * ``'BUY_NO'``  — buy the DOWN token of the current window.
        * ``'HEDGE'``   — open/adjust a perp-swap hedge leg (uses ``meta``:
          ``{'asset','qty','funding_rate','funding_interval_s'}``;
          ``qty>0`` long, ``qty<0`` short).
        * ``'FLAT'``    — request closing this strategy's open leg(s) for the
          current token (early exit before resolution).
    size_fraction
        Fraction of the *available bankroll budget* to deploy on this signal,
        in ``[0, 1]``.  The engine converts it to shares given the fill price
        and the per-window budget cap.  Ignored for ``FLAT``.
    price_limit
        Optional worst acceptable per-share price.  For a buy the engine
        rejects the fill if the modelled fill price exceeds this; for a HEDGE
        it is interpreted in underlying price units (optional).  ``None`` =
        take touch.
    token_id
        Target token; defaults (``None``) to the current context token for
        ``BUY_YES``/``BUY_NO``/``FLAT``.  Set explicitly to act on the peer
        (NO) token while iterating the YES panel.
    meta
        Free-form dict carried onto the resulting position / trade record
        (strategy name, signal score, hedge params, etc.).
    """

    side: SignalSide
    size_fraction: float = 0.0
    price_limit: Optional[float] = None
    token_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.side not in ("BUY_YES", "BUY_NO", "HEDGE", "FLAT"):
            raise ValueError(f"invalid Signal.side: {self.side!r}")
        self.size_fraction = float(max(0.0, min(1.0, self.size_fraction)))


@dataclass
class StrategyParams:
    """Base params dataclass; concrete strategies subclass and extend.

    Common knobs every strategy honours (the engine reads ``max_position_frac``
    and ``per_window_budget_frac`` for sizing guards).

    Attributes
    ----------
    max_position_frac
        Hard cap on bankroll fraction deployable in a single signal.
    per_window_budget_frac
        Cap on bankroll fraction deployable across one window (cross-leg).
    edge_min
        Minimum modelled edge (after expected fill penalty + fee) below which
        a strategy should emit no signal.  Risk-of-ruin floor.
    min_seconds_to_resolution
        Do not open new legs with less than this much time left (avoid
        un-exitable late entries).
    enabled
        Master enable flag for the strategy.
    """

    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20
    edge_min: float = 0.02
    min_seconds_to_resolution: float = 0.0
    enabled: bool = True


@dataclass
class StrategyContext:
    """Everything a strategy may see at one causal step (data ``<= t``).

    Constructed fresh by the engine for each step.  Exposes the current
    feature row, the causal history slice, window identity, and live bankroll
    / position views — but NEVER the resolution label or future rows.

    Attributes
    ----------
    now_ts
        Current epoch-seconds timestamp ``t``.
    row
        The current :class:`MarketTimelineRow` (data at ``t``).
    history
        Ascending-time slice of the panel timeline with ``ts_s <= t``
        (includes ``row`` as the last element).  Read-only by convention.
    token_id, asset, window_end_ts, window_size_s, outcome_dir, outcome_side
        Identity of the token-window being evaluated.
    seconds_to_resolution
        Time left until settlement (from ``row`` or derived).
    bankroll
        Current portfolio equity (cash + MTM) available for sizing.
    cash
        Free cash (excludes deployed binary capital).
    open_shares
        Shares this strategy currently holds in the current token (0 if none).
    open_positions
        Read-only list of the strategy's open binary positions in this token.
    peer
        Optional snapshot of the opposite (NO) token's latest book at ``t``:
        ``{'token_id','best_bid','best_ask','mid'}`` (may be ``None``).
    extras
        Engine-supplied extras (e.g. fill model's expected-penalty helper,
        funding snapshots) — see the engine docstring.
    """

    now_ts: float
    row: MarketTimelineRow
    history: Sequence[MarketTimelineRow]
    token_id: str
    asset: str
    window_end_ts: int
    window_size_s: int
    outcome_dir: Optional[str]
    outcome_side: Optional[str]
    seconds_to_resolution: float
    bankroll: float
    cash: float
    open_shares: float = 0.0
    open_positions: Sequence[Any] = field(default_factory=tuple)
    peer: Optional[Dict[str, Any]] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    # -- convenience causal feature accessors ---------------------------
    @property
    def mid(self) -> Optional[float]:
        return self.row.mid

    @property
    def best_ask(self) -> Optional[float]:
        return self.row.best_ask

    @property
    def best_bid(self) -> Optional[float]:
        return self.row.best_bid

    def history_field(self, name: str) -> List[float]:
        """Causal series of a numeric timeline field (NaN where missing)."""
        out: List[float] = []
        for r in self.history:
            v = getattr(r, name, None)
            out.append(float(v) if v is not None else float("nan"))
        return out


class Strategy(ABC):
    """Abstract base class every strategy must implement.

    Lifecycle
    ---------
    1. ``__init__(params)`` — store the (subclassed) params dataclass.
    2. :meth:`warmup` — optional one-shot fit/calibration over the panel set
       BEFORE the time-ordered backtest begins (e.g. estimate an isotonic
       map, a funding baseline, an HMM).  May see whole panels but MUST NOT
       leak per-window labels into the live decision path — fit global,
       cross-validated, or train/test-split objects only.
    3. :meth:`on_step(ctx)` — called once per causal step; returns a list of
       :class:`Signal`.  This is the only method allowed to act on live data.
    4. :meth:`on_window_close` — optional hook fired when a window resolves
       (after settlement), for per-strategy bookkeeping.

    Registration
    ------------
    Concrete strategies should be decorated with
    :func:`register_strategy('name')` so the engine / CLI can instantiate them
    by name from a params dict.
    """

    #: Human-readable strategy name (set by @register_strategy or subclass).
    name: str = "base"
    #: The params dataclass type this strategy expects.
    params_cls: type = StrategyParams

    def __init__(self, params: Optional[StrategyParams] = None) -> None:
        self.params: StrategyParams = params or self.params_cls()

    # -- lifecycle hooks ------------------------------------------------
    def warmup(self, panels: Sequence[WindowPanel]) -> None:
        """Optional pre-backtest calibration. Default: no-op.

        Override to fit global objects.  Honour the no-leakage rule: any use
        of ``panel.label_resolved_yes`` here must be for global/CV calibration
        only, never memorised per-window and replayed in :meth:`on_step`.
        """
        return None

    @abstractmethod
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        """Return order intents for the current causal step (data ``<= t``).

        MUST be pure w.r.t. ``ctx`` (no peeking at globals that encode the
        future).  Return an empty list to do nothing.
        """
        raise NotImplementedError

    def on_window_close(
        self, panel: WindowPanel, resolved_yes_for_token: int
    ) -> None:
        """Optional post-settlement hook. Default: no-op."""
        return None

    # -- factory --------------------------------------------------------
    @classmethod
    def from_params_dict(cls, d: Optional[dict] = None) -> "Strategy":
        """Instantiate from a plain dict of params (CLI / config friendly)."""
        params = cls.params_cls(**(d or {}))  # type: ignore[call-arg]
        return cls(params)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, type] = {}


def register_strategy(name: str):
    """Class decorator registering a strategy under ``name``.

    Example
    -------
    >>> @register_strategy("my_edge")
    ... class MyEdge(Strategy):
    ...     params_cls = MyParams
    ...     def on_step(self, ctx): ...
    """

    def _wrap(klass: type) -> type:
        if not issubclass(klass, Strategy):
            raise TypeError("register_strategy target must subclass Strategy")
        klass.name = name
        _REGISTRY[name] = klass
        return klass

    return _wrap


def get_strategy(name: str) -> type:
    """Look up a registered strategy class by name."""
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown strategy {name!r}; registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def available_strategies() -> List[str]:
    """List registered strategy names."""
    return sorted(_REGISTRY)


def build_strategy(name: str, params: Optional[dict] = None) -> Strategy:
    """Instantiate a registered strategy by name from a params dict."""
    return get_strategy(name).from_params_dict(params)  # type: ignore[attr-defined]


__all__ = [
    "SignalSide",
    "Signal",
    "StrategyParams",
    "StrategyContext",
    "Strategy",
    "register_strategy",
    "get_strategy",
    "available_strategies",
    "build_strategy",
]
