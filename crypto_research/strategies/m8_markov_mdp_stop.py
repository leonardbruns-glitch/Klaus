"""M8 — Markov Decision Process adaptive optimal stopping (Q-learning).

Family (distinct from all of S2/M5/M6/M7)
-----------------------------------------
The other three Markov strategies decide *what/whether* to enter.  M8 is about
**control, not forecasting**: given a cheap structural entry (intrawindow
momentum), it learns an *optimal stopping policy* — when to bail vs hold to
settlement — by tabular **Q-learning over a Markov state**.  This is the
"AI-smart / adaptive" member: the policy is learned online from realised returns
(Monte-Carlo control with ε-greedy exploration), so it adapts the exit rule to
the data instead of using a fixed profit-target / stop-loss.

Markov state / MDP
------------------
* state  s = (time-left bucket, unrealised-PnL bucket)  — Markov in the held leg.
* action a ∈ {HOLD, EXIT}.
* reward = realised per-share PnL of the episode (EXIT → mid-at-exit − entry;
  else settlement 1/0 − entry).  Episode-return updates every visited (s,a) toward
  G (first-visit MC).  Labels are used ONLY for this offline-style learning
  update at window close — never read in the live on_step decision (no leakage).

Honest prior: optimal stopping cannot manufacture edge from a coinflip entry; it
can only cut the left tail.  If the entry has no edge, the learned policy converges
to "hold" and PnL stays ≈ −fees.  The test decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..data.schema import WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy

_EPS = 1e-12


@dataclass
class MarkovMdpStopParams(StrategyParams):
    entry_mom_min: float = 0.0005   # |intrawindow binance return| to enter
    edge_min: float = 0.0           # entry is structural, not edge-gated
    lr: float = 0.10                # Q-learning rate
    epsilon: float = 0.10           # exploration during the learning run
    min_secs_left: float = 60.0     # only enter with room to manage
    n_time_buckets: int = 5
    max_position_frac: float = 0.06
    per_window_budget_frac: float = 0.12


@register_strategy("markov_mdp_stop")
class MarkovMdpStopStrategy(Strategy):
    params_cls = MarkovMdpStopParams

    def __init__(self, params: Optional[MarkovMdpStopParams] = None) -> None:
        super().__init__(params)
        self.params: MarkovMdpStopParams
        # Q[(t_bucket, pnl_bucket, action)] -> value ; action 0=HOLD 1=EXIT
        self._Q: Dict[Tuple[int, int, int], float] = {}
        self._N: Dict[Tuple[int, int, int], int] = {}
        self._rng = np.random.default_rng(7)
        # per-token episode: entry mid, dir, list of visited (state)
        self._entry: Dict[str, Tuple[float, bool]] = {}
        self._path: Dict[str, List[Tuple[int, int, int]]] = {}

    # -- state discretisation -------------------------------------------
    def _t_bucket(self, ctx: StrategyContext) -> int:
        ws = ctx.window_size_s or 300
        frac = max(0.0, min(1.0, (ctx.seconds_to_resolution or 0) / ws))
        return int(min(self.params.n_time_buckets - 1, frac * self.params.n_time_buckets))

    @staticmethod
    def _pnl_bucket(pnl: float) -> int:
        edges = [-0.05, -0.02, 0.0, 0.02, 0.05]
        b = 0
        for e in edges:
            if pnl >= e:
                b += 1
        return b  # 0..5

    def _q(self, s: Tuple[int, int], a: int) -> float:
        return self._Q.get((s[0], s[1], a), 0.0)

    def _greedy(self, s: Tuple[int, int]) -> int:
        return 1 if self._q(s, 1) > self._q(s, 0) else 0

    # -- entry signal ----------------------------------------------------
    def _intrawindow_ret(self, ctx: StrategyContext) -> Optional[float]:
        spots = [r.binance_spot for r in ctx.history if r.binance_spot is not None]
        if len(spots) < 2 or spots[0] <= 0 or spots[-1] <= 0:
            return None
        return math.log(spots[-1] / spots[0])

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        tok = ctx.token_id

        # ---- manage an open leg via the learned policy ----
        if ctx.open_shares > 0 and tok in self._entry:
            entry_mid, is_up = self._entry[tok]
            mid = ctx.mid if ctx.mid is not None else entry_mid
            pnl = (mid - entry_mid) if is_up else (entry_mid - mid)
            s = (self._t_bucket(ctx), self._pnl_bucket(pnl))
            # ε-greedy action over the Markov state
            if self._rng.random() < p.epsilon:
                a = int(self._rng.integers(0, 2))
            else:
                a = self._greedy(s)
            self._path.setdefault(tok, []).append((s[0], s[1], a))
            if a == 1:  # EXIT
                return [Signal(side="FLAT", meta={"note": "mdp_exit", "pnl": round(pnl, 4)})]
            return []

        # ---- entry: cheap structural momentum trigger ----
        if (ctx.outcome_dir or "").lower() != "up":
            return []
        if ctx.seconds_to_resolution is None or ctx.seconds_to_resolution < p.min_secs_left:
            return []
        r = self._intrawindow_ret(ctx)
        if r is None or abs(r) < p.entry_mom_min:
            return []
        exp_fill = ctx.extras["expected_fill_price"]
        if r > 0:
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 0.9:
                self._entry[tok] = (ctx.mid if ctx.mid else ask, True)
                return [Signal(side="BUY_YES", size_fraction=0.5,
                               price_limit=min(1.0, ask + 0.02),
                               meta={"note": "mdp_entry_up", "r": round(r, 5)})]
        else:
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 0.9:
                # entry mid for the NO leg is (1 - up_mid) ~ no ask side
                self._entry[tok] = (1.0 - (ctx.mid if ctx.mid else (1 - no_ask)), False)
                return [Signal(side="BUY_NO", size_fraction=0.5,
                               price_limit=min(1.0, no_ask + 0.02),
                               meta={"note": "mdp_entry_down", "r": round(r, 5)})]
        return []

    # -- learning update at episode end ---------------------------------
    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        tok = panel.token_id
        path = self._path.pop(tok, None)
        entry = self._entry.pop(tok, None)
        if not path or entry is None:
            return
        entry_mid, is_up = entry
        # terminal settlement value of the side we held (label-based, learning only)
        settle = float(resolved_yes_for_token) if is_up else float(1 - resolved_yes_for_token)
        G = settle - entry_mid  # realised per-share return of holding to settle
        # first-visit MC update toward the episode return
        seen = set()
        for (tb, pb, a) in path:
            key = (tb, pb, a)
            if key in seen:
                continue
            seen.add(key)
            self._N[key] = self._N.get(key, 0) + 1
            old = self._Q.get(key, 0.0)
            self._Q[key] = old + self.params.lr * (G - old)


__all__ = ["MarkovMdpStopParams", "MarkovMdpStopStrategy"]
