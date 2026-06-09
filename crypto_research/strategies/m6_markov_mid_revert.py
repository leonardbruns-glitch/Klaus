"""M6 — Direct Markov-chain mid reversion (online, adaptive).

Family (distinct from S2 and M5)
--------------------------------
No latent regime, no binance fair.  The binary **mid is itself a Markov process
on [0,1]**.  Discretise it into K buckets and maintain an *online,
exponentially-decayed* empirical K×K transition matrix of the mid's own
one-step moves.  The decay makes it adaptive — the matrix tracks the current
regime's reversion/persistence structure instead of a frozen average.

Edge mechanism
--------------
From the current mid-bucket i the chain implies an expected next mid
``E[mid' | i] = Σ_j P(j|i)·center_j``.  When that expected move clears the
post-fee/fill floor we enter the implied direction and **scalp the reversion**
with an early FLAT exit when the move is captured or the chain's expected drift
flips.  This is microstructure mean-reversion of the quote expressed as a pure
Markov chain — the antithesis of forecasting the settlement coinflip.

Honest prior: a few-cent mid reversion must clear ~2×(fee≈1.8% at p=0.5) +
spread; most predicted moves will not.  The test decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from ..data.schema import WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy

_EPS = 1e-12


@dataclass
class MarkovMidRevertParams(StrategyParams):
    n_buckets: int = 10            # mid discretisation over [0,1]
    decay: float = 0.995           # per-update forgetting on transition counts
    edge_min: float = 0.03         # expected move beyond fees to enter
    take_profit: float = 0.02      # FLAT when mid has moved this far our way
    min_secs_left: float = 45.0    # need room to scalp + exit
    min_count: float = 20.0        # min effective count in a row before trusting it
    max_position_frac: float = 0.08
    per_window_budget_frac: float = 0.15


@register_strategy("markov_mid_revert")
class MarkovMidRevertStrategy(Strategy):
    params_cls = MarkovMidRevertParams

    def __init__(self, params: Optional[MarkovMidRevertParams] = None) -> None:
        super().__init__(params)
        self.params: MarkovMidRevertParams
        K = self.params.n_buckets
        self._C: Dict[str, np.ndarray] = {}           # per-asset decayed counts
        self._centers = (np.arange(K) + 0.5) / K
        self._last_bucket: Dict[str, int] = {}        # per token_id last seen bucket
        self._entry_mid: Dict[str, float] = {}        # per token_id entry mid

    def _bucket(self, mid: float) -> int:
        K = self.params.n_buckets
        return int(min(K - 1, max(0, int(mid * K))))

    def warmup(self, panels) -> None:
        # Seed the transition matrix from the panel mids (unsupervised; no labels).
        K = self.params.n_buckets
        for panel in panels:
            if not panel.timeline:
                continue
            C = self._C.setdefault(panel.asset, np.ones((K, K)) * 0.1)
            prev = None
            for r in panel.timeline:
                if r.mid is None or not (0 < r.mid < 1):
                    continue
                b = self._bucket(r.mid)
                if prev is not None:
                    C[prev, b] += 1.0
                prev = b

    def _expected_next(self, asset: str, bucket: int) -> Optional[float]:
        C = self._C.get(asset)
        if C is None:
            return None
        row = C[bucket]
        s = row.sum()
        if s < self.params.min_count:
            return None
        P = row / (s + _EPS)
        return float(P @ self._centers)

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        mid = ctx.mid
        asset = ctx.asset
        tok = ctx.token_id
        if mid is None or not (0 < mid < 1):
            return []
        K = p.n_buckets
        C = self._C.setdefault(asset, np.ones((K, K)) * 0.1)
        b = self._bucket(mid)
        # online decayed transition update from this token's own trajectory
        prev = self._last_bucket.get(tok)
        if prev is not None:
            C *= p.decay
            C[prev, b] += 1.0
        self._last_bucket[tok] = b

        exp_fill = ctx.extras["expected_fill_price"]
        fee_fn = ctx.extras.get("fee_fn")

        # ---- manage an open scalp: take profit / flip exit ----
        if ctx.open_shares > 0:
            entry = self._entry_mid.get(tok, mid)
            is_up = (ctx.outcome_dir or "").lower() == "up"
            moved = (mid - entry) if is_up else (entry - mid)
            exp_next = self._expected_next(asset, b)
            flip = exp_next is not None and (
                (is_up and exp_next < mid) or ((not is_up) and exp_next > mid)
            )
            if moved >= p.take_profit or flip:
                return [Signal(side="FLAT", meta={"reason": "tp" if moved >= p.take_profit else "flip",
                                                  "moved": round(moved, 4)})]
            return []

        if ctx.seconds_to_resolution is None or ctx.seconds_to_resolution < p.min_secs_left:
            return []
        exp_next = self._expected_next(asset, b)
        if exp_next is None:
            return []
        drift = exp_next - mid  # chain's expected next-mid move

        if drift > 0:  # mid expected to rise -> buy YES
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                f = exp_fill("buy", ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                if drift - (f - mid) - fee >= p.edge_min:
                    self._entry_mid[tok] = mid
                    return [Signal(side="BUY_YES", size_fraction=0.5,
                                   price_limit=min(1.0, ask + 0.02),
                                   meta={"note": "mid_revert_up", "drift": round(drift, 4)})]
        elif drift < 0:  # mid expected to fall -> buy NO (peer)
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                f = exp_fill("buy", no_ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                # NO gains when mid falls; expected NO move ≈ -drift
                if (-drift) - (f - (1 - mid)) - fee >= p.edge_min:
                    self._entry_mid[tok] = mid
                    return [Signal(side="BUY_NO", size_fraction=0.5,
                                   price_limit=min(1.0, no_ask + 0.02),
                                   meta={"note": "mid_revert_down", "drift": round(drift, 4)})]
        return []

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._last_bucket.pop(panel.token_id, None)
        self._entry_mid.pop(panel.token_id, None)


__all__ = ["MarkovMidRevertParams", "MarkovMidRevertStrategy"]
