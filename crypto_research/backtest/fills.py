"""Bimodal (adverse-selection-aware) fill model for Polymarket up/down legs.

Why bimodal?
------------
On Polymarket binary markets a resting taker does **not** get the mid.  Worse,
fills are *informationally adverse*: you tend to get filled precisely when the
short-horizon move is about to go against you (winner's curse / toxic flow).
The validated weather work and the crypto VOLARB post-mortems both show that
assuming mid-fills manufactures phantom edge.

So the model is a **two-component mixture** for every fill:

* with probability ``1 - pi_toxic`` — a *benign* fill **at touch**
  (the ask for a buy, the bid for a sell), plus a fixed per-share execution
  slippage penalty ``slippage`` drawn (once, per backtest) in ``[0.01, 0.02]``;
* with probability ``pi_toxic`` — a *toxic* fill, worse by an additional
  ``adverse_penalty`` per share (adverse selection), on top of touch+slippage.

All randomness flows through a single seeded ``numpy.random.Generator`` so a
backtest is bit-for-bit reproducible.

The model returns a per-share **price actually paid (buy) / received (sell)**,
clipped to the valid probability range ``[0, 1]``.  Notional fees are applied
separately by the portfolio's injectable ``fee_fn`` — this class models only
*price* impact, never fees.

Non-HFT note
------------
This is a *statistical* execution model evaluated on bar cadence, not a
latency simulator.  ``pi_toxic`` / ``adverse_penalty`` encode the
*distribution* of realised slippage observed in ``order_lifecycle.jsonl`` /
``trades.jsonl`` — they are not a microsecond queue model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class FillResult:
    """Outcome of one simulated fill.

    Attributes
    ----------
    fill_price
        Per-share price paid (buy) or received (sell), in ``[0, 1]``.
    toxic
        Whether the toxic mixture component fired.
    slippage_applied
        Per-share benign execution slippage added.
    adverse_applied
        Per-share adverse-selection penalty added (0 if benign).
    requested_price
        The touch price the order was evaluated against.
    side
        ``'buy'`` or ``'sell'``.
    shares
        Share count requested (echoed for convenience).
    """

    fill_price: float
    toxic: bool
    slippage_applied: float
    adverse_applied: float
    requested_price: float
    side: str
    shares: float


@dataclass
class BimodalFillModel:
    """Mixture fill model: benign-at-touch vs toxic adverse-selected.

    Parameters
    ----------
    pi_toxic
        Probability the toxic component fires for a given fill (``[0, 1]``).
    adverse_penalty
        Extra per-share price penalty under the toxic component.  This is the
        cost of being filled exactly when wrong.
    slippage
        Per-share benign execution slippage; if ``None`` it is drawn once
        (per model instance) from ``U[slippage_low, slippage_high]`` so the
        whole backtest shares one realised slippage level.
    slippage_low, slippage_high
        Bounds for the per-share slippage draw (mandate: ``[0.01, 0.02]``).
    rng
        Seeded ``numpy.random.Generator``.  If ``None`` one is created from
        ``seed`` for reproducibility.
    seed
        Seed used when ``rng is None``.

    Notes
    -----
    Sign convention: a **buy** pays ``touch + slippage (+ adverse)`` (higher
    is worse); a **sell** receives ``touch - slippage (- adverse)`` (lower is
    worse).  Both are clipped to ``[0, 1]``.
    """

    pi_toxic: float = 0.25
    adverse_penalty: float = 0.03
    slippage: Optional[float] = None
    slippage_low: float = 0.01
    slippage_high: float = 0.02
    rng: Optional[np.random.Generator] = None
    seed: int = 12345
    # resolved slippage (set in __post_init__)
    _slippage: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if not (0.0 <= self.pi_toxic <= 1.0):
            raise ValueError("pi_toxic must be in [0, 1]")
        if self.adverse_penalty < 0.0:
            raise ValueError("adverse_penalty must be >= 0")
        if self.rng is None:
            self.rng = np.random.default_rng(self.seed)
        if self.slippage is None:
            self._slippage = float(
                self.rng.uniform(self.slippage_low, self.slippage_high)
            )
        else:
            self._slippage = float(self.slippage)

    # ------------------------------------------------------------------
    @property
    def per_share_slippage(self) -> float:
        """The realised per-share benign slippage used for this backtest."""
        return self._slippage

    def fill(
        self,
        side: str,
        touch_price: float,
        shares: float,
        *,
        toxic_override: Optional[bool] = None,
    ) -> FillResult:
        """Simulate one fill and return the realised per-share price.

        Parameters
        ----------
        side
            ``'buy'`` (pay the ask) or ``'sell'`` (hit the bid).
        touch_price
            The touch price (ask for buys, bid for sells).  In ``[0, 1]``.
        shares
            Share count (echoed; does not affect the per-share price here —
            depth-aware impact can be layered by a subclass).
        toxic_override
            Force the toxic / benign branch (testing & deterministic replay).

        Returns
        -------
        FillResult
        """
        s = side.lower()
        if s not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        assert self.rng is not None

        if toxic_override is None:
            toxic = bool(self.rng.random() < self.pi_toxic)
        else:
            toxic = bool(toxic_override)

        slip = self._slippage
        adverse = self.adverse_penalty if toxic else 0.0
        penalty = slip + adverse  # always against us

        if s == "buy":
            price = touch_price + penalty
        else:  # sell
            price = touch_price - penalty

        price = float(np.clip(price, 0.0, 1.0))
        return FillResult(
            fill_price=price,
            toxic=toxic,
            slippage_applied=slip,
            adverse_applied=adverse,
            requested_price=float(touch_price),
            side=s,
            shares=float(shares),
        )

    def expected_fill_price(self, side: str, touch_price: float) -> float:
        """Closed-form expected per-share fill price (no RNG draw).

        Useful for analytic EV gating inside a strategy without consuming the
        RNG stream.  Expected penalty = ``slippage + pi_toxic * adverse``.
        """
        penalty = self._slippage + self.pi_toxic * self.adverse_penalty
        if side.lower() == "buy":
            return float(np.clip(touch_price + penalty, 0.0, 1.0))
        return float(np.clip(touch_price - penalty, 0.0, 1.0))


__all__ = ["BimodalFillModel", "FillResult"]
