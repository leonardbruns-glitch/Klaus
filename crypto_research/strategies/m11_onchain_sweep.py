"""M11 — Endgame sweep-catch / on-chain redemption (FALSIFICATION RE-TEST).

Thesis (user): in the final ≤120s, retail sweeps crash a tail bid below $0.05
while the diffusion fair P* ≥ 0.25 — buy the discounted tail, hold to settlement,
redeem 1.0/0.0 against the CTF contract minus gas.

WARNING — this is the oracle-sweep family already FALSIFIED on live capital
(−$487; postmortem: "cheap asks at T+0 exist ONLY on the losing side; the market
has already done price discovery — the cheap tail is the correctly-priced
loser").  We run it to confirm/deny on fresh BTC data, not because it is expected
to work.  "On-chain redemption / matching-engine bypass" is an execution detail
irrelevant to whether the edge exists — modeled here simply as hold-to-settlement
minus a flat gas cost.

Test form (taker): final ≤ entry_secs, best_ask ≤ cheap_thr, fair ≥ fair_min ⇒
BUY_YES (symmetric NO via peer when P_down ≥ fair_min).  Hold to settle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy

_EPS = 1e-12


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class OnchainSweepParams(StrategyParams):
    entry_secs: float = 120.0      # only act in the final 2 minutes
    cheap_thr: float = 0.05        # buy a tail at/below this ask
    fair_min: float = 0.25         # diffusion fair must say >= this for that side
    gas_cost: float = 0.01         # flat per-trade gas (modeled as edge haircut)
    edge_min: float = 0.0
    vol_floor_persec: float = 2e-5
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20


@register_strategy("onchain_sweep")
class OnchainSweepStrategy(Strategy):
    params_cls = OnchainSweepParams

    def __init__(self, params: Optional[OnchainSweepParams] = None) -> None:
        super().__init__(params)
        self.params: OnchainSweepParams
        self._acted: set = set()

    def _fair_up(self, rows: Sequence[MarketTimelineRow], sl: float) -> Optional[float]:
        spots = [r.binance_spot for r in rows if r.binance_spot is not None]
        if len(spots) < 3 or spots[0] <= 0 or spots[-1] <= 0:
            return None
        import numpy as np
        arr = np.asarray(spots, dtype=float)
        r = math.log(arr[-1] / arr[0])
        persec = max(self.params.vol_floor_persec, float(np.std(np.diff(np.log(arr)))))
        sigma = persec * math.sqrt(max(1.0, sl))
        return _phi(r / sigma) if sigma > 0 else None

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        if (ctx.outcome_dir or "").lower() != "up" or ctx.open_shares > 0:
            return []
        sl = ctx.seconds_to_resolution
        if sl is None or sl > p.entry_secs or sl <= 1.0:
            return []
        akey = (ctx.token_id, ctx.window_end_ts)
        if akey in self._acted:
            return []
        rows = list(ctx.history)
        fair = self._fair_up(rows, sl)
        if fair is None:
            return []
        exp_fill = ctx.extras["expected_fill_price"]

        # cheap UP tail that the model says is not dead
        ask = ctx.best_ask
        if ask is not None and 0 < ask <= p.cheap_thr and fair >= p.fair_min:
            f = exp_fill("buy", ask)
            self._acted.add(akey)
            return [Signal(side="BUY_YES", size_fraction=0.5,
                           price_limit=min(1.0, ask + 0.02),
                           meta={"note": "sweep_yes", "ask": round(ask, 3),
                                 "fair": round(fair, 3)})]
        # cheap NO tail (P_down >= fair_min)
        peer = ctx.peer
        no_ask = peer.get("best_ask") if peer else None
        if no_ask is not None and 0 < no_ask <= p.cheap_thr and (1.0 - fair) >= p.fair_min:
            f = exp_fill("buy", no_ask)
            self._acted.add(akey)
            return [Signal(side="BUY_NO", size_fraction=0.5,
                           price_limit=min(1.0, no_ask + 0.02),
                           meta={"note": "sweep_no", "ask": round(no_ask, 3),
                                 "fair": round(1.0 - fair, 3)})]
        return []

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["OnchainSweepParams", "OnchainSweepStrategy"]
