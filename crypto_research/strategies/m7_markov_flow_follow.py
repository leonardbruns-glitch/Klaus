"""M7 — Markov-modulated informed-flow follower (adaptive).

Family (distinct from S2)
-------------------------
The repo's falsification record established that **taker flow is informed —
follow it, do not fade it** (taker-fade FALSIFIED).  S2 instead used order-book
imbalance to *warp regime transitions and forecast direction* and was refused.
M7 uses a Markov chain only as a **state detector for informed flow**: a
per-asset GaussianHMM over flow-intensity features [vpin, |30s return|,
|ob-imbalance|] separates a *quiet/noise* state from an *informed/active* state.
When the filtered posterior says we are in the informed state, M7 **follows the
realised flow's sign** (recent binance momentum + book imbalance) for the rest of
the window.  It acts on *confirmed* flow, never on a blind regime→direction map.

Edge mechanism
--------------
Informed-state gate (Markov, adaptive online filter) × follow the sign of
realised flow × post-fee/fill edge floor.  Hold to resolution.

Honest prior: if the book already impounds informed flow within the bar (efficient
pricing, Brier≈0.01), following it at the ask leaves no edge after fees.  The test
decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy
from .s2_hmm_regime import GaussianHMM

_EPS = 1e-12


@dataclass
class MarkovFlowFollowParams(StrategyParams):
    n_states: int = 2              # quiet vs informed
    min_train_windows: int = 60
    edge_min: float = 0.04
    gate_posterior: float = 0.55   # min P(informed state) to act
    flow_min: float = 0.02         # min |signed flow| (in prob units) to call a side
    min_secs_left: float = 30.0
    max_secs_left: float = 285.0
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20


@register_strategy("markov_flow_follow")
class MarkovFlowFollowStrategy(Strategy):
    params_cls = MarkovFlowFollowParams

    def __init__(self, params: Optional[MarkovFlowFollowParams] = None) -> None:
        super().__init__(params)
        self.params: MarkovFlowFollowParams
        self._models: Dict[str, GaussianHMM] = {}
        self._informed_state: Dict[str, int] = {}
        self._acted: set = set()

    @staticmethod
    def _ret30(rows: Sequence[MarketTimelineRow]) -> float:
        for r in reversed(rows):
            if r.binance_ret_30s_pct is not None:
                return float(r.binance_ret_30s_pct) / 100.0
        return 0.0

    @staticmethod
    def _obi(rows: Sequence[MarketTimelineRow]) -> float:
        for r in reversed(rows):
            if r.ob_imb_top3 is not None:
                return float(r.ob_imb_top3)
        return 0.0

    @staticmethod
    def _vpin(rows: Sequence[MarketTimelineRow]) -> float:
        vp = [r.vpin_score for r in rows if r.vpin_score is not None]
        return float(np.mean(vp)) if vp else 0.0

    def _flow_feat(self, rows: Sequence[MarketTimelineRow]) -> List[float]:
        return [self._vpin(rows), abs(self._ret30(rows)), abs(self._obi(rows))]

    def _signed_flow(self, rows: Sequence[MarketTimelineRow]) -> float:
        """Direction of informed flow in [-1,1]: momentum + book imbalance."""
        r30 = self._ret30(rows)
        obi = self._obi(rows)
        # scale return to a probability-ish unit; combine with imbalance sign
        return float(np.tanh(200.0 * r30) * 0.6 + np.tanh(obi) * 0.4)

    def warmup(self, panels: Sequence[WindowPanel]) -> None:
        per_asset: Dict[str, List[Tuple[int, List[float]]]] = {}
        for panel in panels:
            if not panel.is_up_token or not panel.timeline:
                continue
            per_asset.setdefault(panel.asset, []).append(
                (int(panel.window_end_ts), self._flow_feat(panel.timeline))
            )
        for asset, bars in per_asset.items():
            if len(bars) < self.params.n_states + 3:
                continue
            bars.sort(key=lambda b: b[0])
            X = np.array([b[1] for b in bars], dtype=float)
            m = GaussianHMM(n_states=self.params.n_states, seed=abs(hash(asset)) % 99999)
            m.fit(X)
            # informed = highest combined flow intensity (sum of feature means)
            self._models[asset] = m
            self._informed_state[asset] = int(np.argmax(m.means_.sum(axis=1)))

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        if (ctx.outcome_dir or "").lower() != "up":
            return []
        if ctx.open_shares > 0:
            return []
        sl = ctx.seconds_to_resolution
        if sl is None or sl < p.min_secs_left or sl > p.max_secs_left:
            return []
        akey = (ctx.token_id, ctx.window_end_ts)
        if akey in self._acted:
            return []
        model = self._models.get(ctx.asset)
        if model is None:
            return []
        rows = list(ctx.history)
        if not rows:
            return []
        alpha, _ = model.filter(np.array([self._flow_feat(rows)], dtype=float))
        inf_s = self._informed_state[ctx.asset]
        if float(alpha[-1][inf_s]) < p.gate_posterior:
            return []  # not an informed-flow state — stand down

        flow = self._signed_flow(rows)
        if abs(flow) < p.flow_min:
            return []
        exp_fill = ctx.extras["expected_fill_price"]
        fee_fn = ctx.extras.get("fee_fn")
        # convert flow magnitude into an implied win-prob lean over 0.5
        p_dir = 0.5 + 0.5 * min(0.9, abs(flow))

        if flow > 0:  # follow up-flow -> YES
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                f = exp_fill("buy", ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                edge = p_dir - f - fee
                if edge >= p.edge_min:
                    self._acted.add(akey)
                    return [Signal(side="BUY_YES", size_fraction=self._size(edge),
                                   price_limit=min(1.0, ask + 2 * abs(f - ask) + 0.02),
                                   meta={"note": "follow_up_flow", "flow": round(flow, 3),
                                         "p_inf": round(float(alpha[-1][inf_s]), 3)})]
        else:        # follow down-flow -> NO
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                f = exp_fill("buy", no_ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                edge = p_dir - f - fee
                if edge >= p.edge_min:
                    self._acted.add(akey)
                    return [Signal(side="BUY_NO", size_fraction=self._size(edge),
                                   price_limit=min(1.0, no_ask + 2 * abs(f - no_ask) + 0.02),
                                   meta={"note": "follow_down_flow", "flow": round(flow, 3),
                                         "p_inf": round(float(alpha[-1][inf_s]), 3)})]
        return []

    def _size(self, edge: float) -> float:
        return float(min(1.0, max(0.0, 0.2 + 3.2 * max(0.0, edge - self.params.edge_min))))

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["MarkovFlowFollowParams", "MarkovFlowFollowStrategy"]
