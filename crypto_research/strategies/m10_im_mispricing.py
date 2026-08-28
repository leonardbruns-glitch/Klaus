"""M10 — Informational Mispricing (IM): post-stabilization reaction-lag arb.

Distinct from M7
----------------
M7 followed flow *during* the impulse and was destroyed.  IM's central rule is
the opposite: detect a shock, then **only enter AFTER the impulse has
stabilized** (velocity decaying, ≥ min_stab steps of calm), betting the binary
under-reacted to a confirmed BTC move and will catch up.  This is reaction-lag
arb, not prediction.

Mechanism
---------
* Shock: |binance 30s return| > shock_ret  (flow/intensity proxies folded in via
  velocity).  Record pre-shock mid and peak |velocity|.
* Stabilization: current |5s velocity| < decay_frac · peak for ≥ min_stab steps.
* P_expected = diffusion fair (the principled "where the binary should be given
  BTC now"); mispricing = mid − P_expected.
* Enter LONG if mispricing < −thr (binary lagging an up-move); NO if > +thr.
* Exit on reversion to fair/pre-shock mid, time cap, or an opposite shock.

Honest prior: RIPA showed the fair-vs-book gap is anti-predictive on this market
(WR 16%).  IM's only new lever is entry *timing*; the test says whether waiting
for stabilization rescues it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy

_EPS = 1e-12


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class ImParams(StrategyParams):
    shock_ret: float = 0.0015      # |30s return| shock threshold (0.15%)
    decay_frac: float = 0.5        # |vel| below this fraction of peak = stabilizing
    min_stab: int = 3              # consecutive stabilizing steps required
    mispricing_thr: float = 0.05   # |mid - fair| to call it a mispricing
    edge_min: float = 0.04
    eps_revert: float = 0.02       # exit when |mid - fair| below this
    time_cap_secs: float = 150.0   # exit if held longer than this
    min_secs_left: float = 30.0
    vol_floor_persec: float = 2e-5
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20


@register_strategy("im_mispricing")
class ImStrategy(Strategy):
    params_cls = ImParams

    def __init__(self, params: Optional[ImParams] = None) -> None:
        super().__init__(params)
        self.params: ImParams
        # per-token shock state
        self._st: Dict[str, dict] = {}
        self._entry_ts: Dict[str, float] = {}
        self._acted: set = set()

    @staticmethod
    def _ret30(rows: Sequence[MarketTimelineRow]) -> float:
        for r in reversed(rows):
            if r.binance_ret_30s_pct is not None:
                return float(r.binance_ret_30s_pct) / 100.0
        return 0.0

    @staticmethod
    def _vel(rows: Sequence[MarketTimelineRow]) -> float:
        for r in reversed(rows):
            if r.binance_vel_5s_pct is not None:
                return abs(float(r.binance_vel_5s_pct)) / 100.0
        return 0.0

    def _fair_up(self, rows: Sequence[MarketTimelineRow], sl: float) -> Optional[float]:
        spots = [r.binance_spot for r in rows if r.binance_spot is not None]
        if len(spots) < 3 or spots[0] <= 0 or spots[-1] <= 0:
            return None
        import numpy as np
        arr = np.asarray(spots, dtype=float)
        r = math.log(arr[-1] / arr[0])
        persec = max(self.params.vol_floor_persec,
                     float(np.std(np.diff(np.log(arr)))))
        sigma = persec * math.sqrt(max(1.0, sl))
        return _phi(r / sigma) if sigma > 0 else None

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        tok = ctx.token_id
        rows = list(ctx.history)
        sl = ctx.seconds_to_resolution or 0.0
        mid = ctx.mid

        # ---- manage open leg ----
        if ctx.open_shares > 0:
            fair = self._fair_up(rows, sl) if sl > 0 else None
            ent = self._entry_ts.get(tok)
            reasons = []
            if fair is not None and mid is not None and abs(mid - fair) < p.eps_revert:
                reasons.append("reverted")
            if ent is not None and (ent - sl) > p.time_cap_secs:
                reasons.append("time_cap")
            if self._ret30(rows) and abs(self._ret30(rows)) > p.shock_ret:
                reasons.append("opposite_shock")
            if reasons:
                return [Signal(side="FLAT", meta={"reason": ",".join(reasons)})]
            return []

        if (ctx.outcome_dir or "").lower() != "up":
            return []
        if sl < p.min_secs_left:
            return []
        akey = (tok, ctx.window_end_ts)
        if akey in self._acted or mid is None:
            return []

        # ---- shock state machine ----
        st = self._st.setdefault(tok, {"active": False, "pre_mid": mid,
                                       "peak_vel": 0.0, "stab": 0})
        ret30 = self._ret30(rows)
        vel = self._vel(rows)
        if not st["active"]:
            st["pre_mid"] = mid  # rolling pre-shock anchor
            if abs(ret30) > p.shock_ret:
                st["active"] = True
                st["peak_vel"] = vel
                st["stab"] = 0
            return []
        # shock active: track peak and stabilization
        st["peak_vel"] = max(st["peak_vel"], vel)
        if vel < p.decay_frac * st["peak_vel"]:
            st["stab"] += 1
        else:
            st["stab"] = 0
        if st["stab"] < p.min_stab:
            return []  # not stabilized yet — the M7-avoidance rule

        fair = self._fair_up(rows, sl)
        if fair is None:
            return []
        mispricing = mid - fair
        if abs(mispricing) < p.mispricing_thr:
            return []
        exp_fill = ctx.extras["expected_fill_price"]
        fee_fn = ctx.extras.get("fee_fn")

        if mispricing < 0:  # binary lagging an up-move -> LONG YES
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                f = exp_fill("buy", ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                if (fair - f - fee) >= p.edge_min:
                    self._acted.add(akey)
                    self._entry_ts[tok] = sl
                    return [Signal(side="BUY_YES", size_fraction=0.5,
                                   price_limit=min(1.0, ask + 2 * abs(f - ask) + 0.02),
                                   meta={"note": "im_long", "mis": round(mispricing, 4)})]
        else:               # binary over-priced -> NO
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                f = exp_fill("buy", no_ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                if ((1 - fair) - f - fee) >= p.edge_min:
                    self._acted.add(akey)
                    self._entry_ts[tok] = sl
                    return [Signal(side="BUY_NO", size_fraction=0.5,
                                   price_limit=min(1.0, no_ask + 2 * abs(f - no_ask) + 0.02),
                                   meta={"note": "im_short", "mis": round(mispricing, 4)})]
        return []

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._st.pop(panel.token_id, None)
        self._entry_ts.pop(panel.token_id, None)
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["ImParams", "ImStrategy"]
