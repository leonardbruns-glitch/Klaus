"""M5 — Markov Regime-GATED binance-fair convergence (adaptive).

Family (deliberately NOT S2)
----------------------------
S2 forecast the *next window's direction* from a latent regime — refused: the
window outcome is a near-coinflip and the book prices it efficiently.  M5 does
the opposite: it never forecasts the coinflip.  It computes a **model-light
binance-implied fair** for the CURRENT window (endpoint-vs-open probability from
the intrawindow lead and the remaining diffusion) and trades the book's
disagreement with it — but ONLY when an adaptive Markov regime says the book is
currently in an *exploitable* (lag/dislocation) state rather than an efficient
one.  The Markov chain is a **gate on a structural signal**, not a direction
predictor.

Mechanism
---------
* Fair (causal): r = ln(spot_now / spot_open); σ_rem = per-sec vol · √(secs left);
  P_up = Φ(r / σ_rem).  This is the coherent endpoint probability — no strike
  first-passage over-counting.
* Regime (adaptive): a per-asset GaussianHMM over window-level micro-features
  [spread_bps, vpin, |intrawindow r|, quote_age].  The *exploitable* state is the
  one with the widest spread / stalest quotes (where the book lags binance).  The
  filtered regime posterior is updated online from the causal history each step.
* Act only in the exploitable regime, and only if |P_up − ask| clears the
  post-fee/fill edge floor.  Hold to resolution.

This is the "lag-convergence" candidate operationalised with a Markov gate.  The
honest prior (oracle-sweep postmortem) is that the book prices the outcome
correctly pre-close, so the edge may be small/negative — the test decides.
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


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class MarkovRegimeGateParams(StrategyParams):
    n_states: int = 3          # latent micro-regimes (2..4)
    min_train_windows: int = 60
    edge_min: float = 0.04
    gate_posterior: float = 0.55   # min P(exploitable regime) to act
    min_secs_left: float = 30.0    # don't enter in the un-exitable tail
    max_secs_left: float = 285.0   # need some lead to have formed
    vol_floor_persec: float = 2e-5
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20


@register_strategy("markov_regime_gate")
class MarkovRegimeGateStrategy(Strategy):
    params_cls = MarkovRegimeGateParams

    def __init__(self, params: Optional[MarkovRegimeGateParams] = None) -> None:
        super().__init__(params)
        self.params: MarkovRegimeGateParams
        self._models: Dict[str, GaussianHMM] = {}
        self._exploit_state: Dict[str, int] = {}
        self._acted: set = set()

    # -- features --------------------------------------------------------
    @staticmethod
    def _spot_series(rows: Sequence[MarketTimelineRow]) -> List[float]:
        return [r.binance_spot for r in rows if r.binance_spot is not None]

    def _window_features(self, rows: Sequence[MarketTimelineRow]) -> Optional[List[float]]:
        if not rows:
            return None
        spr = [r.spread_bps for r in rows if r.spread_bps is not None]
        vp = [r.vpin_score for r in rows if r.vpin_score is not None]
        qa = [r.ob_quote_age_ms for r in rows if r.ob_quote_age_ms is not None]
        spots = self._spot_series(rows)
        absr = (abs(math.log(spots[-1] / spots[0]))
                if len(spots) >= 2 and spots[0] > 0 and spots[-1] > 0 else 0.0)
        return [
            float(np.mean(spr)) if spr else 0.0,
            float(np.mean(vp)) if vp else 0.0,
            absr,
            float(np.mean(qa)) / 1000.0 if qa else 0.0,
        ]

    def _fair_up(self, rows: Sequence[MarketTimelineRow], secs_left: float) -> Optional[float]:
        spots = self._spot_series(rows)
        if len(spots) < 3 or spots[0] <= 0:
            return None
        arr = np.asarray(spots, dtype=float)
        if arr[-1] <= 0:
            return None
        r = math.log(arr[-1] / arr[0])
        steps = np.diff(np.log(np.clip(arr, _EPS, None)))
        persec = max(self.params.vol_floor_persec,
                     float(np.std(steps)) / max(1.0, (len(arr) and 1.0)))
        # std of per-step returns ~ per-step; scale by remaining steps≈secs_left/dt.
        # use a coarse dt≈1s proxy: σ_rem = persec·√secs_left.
        sigma_rem = persec * math.sqrt(max(1.0, secs_left))
        if sigma_rem <= 0:
            return None
        return _phi(r / sigma_rem)

    # -- warmup: per-asset regime HMM -----------------------------------
    def warmup(self, panels: Sequence[WindowPanel]) -> None:
        per_asset: Dict[str, List[Tuple[int, List[float]]]] = {}
        for panel in panels:
            if not panel.is_up_token or not panel.timeline:
                continue
            f = self._window_features(panel.timeline)
            if f is not None:
                per_asset.setdefault(panel.asset, []).append((int(panel.window_end_ts), f))
        for asset, bars in per_asset.items():
            if len(bars) < self.params.n_states + 3:
                continue
            bars.sort(key=lambda b: b[0])
            X = np.array([b[1] for b in bars], dtype=float)
            m = GaussianHMM(n_states=self.params.n_states, seed=abs(hash(asset)) % 99999)
            m.fit(X)
            # exploitable = widest spread (feat 0) + stalest quote (feat 3)
            score = m.means_[:, 0] + m.means_[:, 3]
            self._models[asset] = m
            self._exploit_state[asset] = int(np.argmax(score))

    # -- live ------------------------------------------------------------
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        if (ctx.outcome_dir or "").lower() != "up":
            return []  # one decision per window, on the UP panel
        if ctx.open_shares > 0:
            return []  # hold to resolution
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
        feat = self._window_features(rows)
        if feat is None:
            return []
        alpha, _ = model.filter(np.array([feat], dtype=float))
        exp_s = self._exploit_state[ctx.asset]
        if float(alpha[-1][exp_s]) < p.gate_posterior:
            return []  # market efficient right now — stand down

        fair_up = self._fair_up(rows, sl)
        if fair_up is None:
            return []
        exp_fill = ctx.extras["expected_fill_price"]
        fee_fn = ctx.extras.get("fee_fn")

        # YES leg if book underprices UP; NO leg if book overprices UP.
        yes_ask = ctx.best_ask
        if yes_ask is not None and 0 < yes_ask < 1:
            f = exp_fill("buy", yes_ask)
            fee = fee_fn(f, 1.0) if fee_fn else 0.0
            edge = fair_up - f - fee
            if edge >= p.edge_min:
                self._acted.add(akey)
                return [Signal(side="BUY_YES", size_fraction=self._size(edge),
                               price_limit=min(1.0, yes_ask + 2 * abs(f - yes_ask) + 0.02),
                               meta={"note": "regime_gate_up", "fair_up": round(fair_up, 4),
                                     "p_exploit": round(float(alpha[-1][exp_s]), 3)})]
        peer = ctx.peer
        no_ask = peer.get("best_ask") if peer else None
        if no_ask is not None and 0 < no_ask < 1:
            f = exp_fill("buy", no_ask)
            fee = fee_fn(f, 1.0) if fee_fn else 0.0
            edge = (1.0 - fair_up) - f - fee
            if edge >= p.edge_min:
                self._acted.add(akey)
                return [Signal(side="BUY_NO", size_fraction=self._size(edge),
                               price_limit=min(1.0, no_ask + 2 * abs(f - no_ask) + 0.02),
                               meta={"note": "regime_gate_down", "fair_up": round(fair_up, 4),
                                     "p_exploit": round(float(alpha[-1][exp_s]), 3)})]
        return []

    def _size(self, edge: float) -> float:
        return float(min(1.0, max(0.0, 0.2 + 3.2 * max(0.0, edge - self.params.edge_min))))

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["MarkovRegimeGateParams", "MarkovRegimeGateStrategy"]
