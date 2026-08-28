"""M12 — Multi-Horizon Dislocation (MHD).

Goal
----
Trade when the 5-min binary price is misaligned with the broader drift implied
by LONGER horizons (15m / 60m BTC returns).  Low-frequency, directional, low-vol
only.  No flow / order-book signals (per spec) — price, returns, volatility only.

Mechanism
---------
* P_5m = current binary mid.
* P_real = diffusion fair that ADDS a longer-horizon drift term: the remaining
  expected move μ_rem = drift_rate · secs_left, drift_rate blended from the 15m
  and 60m per-second BTC return.  P_real = Φ((r + μ_rem)/σ_rem) where r is the
  intrawindow lead.  (The prior fairs were drift-free; MHD's novelty is folding
  multi-horizon drift in.)
* edge = P_real − P_5m.  Trade |edge|>thr in a LOW-vol, no-rapid-move regime.
* LONG if edge>0, NO if edge<0.  Hold to resolution.

Honest prior: every fair-vs-book variant tested has been anti-predictive on this
market; MHD's new lever is the multi-horizon drift + low-vol gate.  The test
decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class MhdParams(StrategyParams):
    edge_thr: float = 0.06         # |P_real - P_5m| beyond this to trade
    edge_min: float = 0.04         # post-fee floor
    w15: float = 0.5               # weight on 15m drift
    w60: float = 0.5               # weight on 60m drift
    lowvol_persec: float = 8e-5    # realized per-sec vol must be below this
    rapid_vel: float = 0.0008      # |5s velocity| above this = rapid move, skip
    min_secs_left: float = 45.0
    max_secs_left: float = 270.0
    vol_floor_persec: float = 2e-5
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20


@register_strategy("mhd_multihorizon")
class MhdStrategy(Strategy):
    params_cls = MhdParams

    def __init__(self, params: Optional[MhdParams] = None) -> None:
        super().__init__(params)
        self.params: MhdParams
        self._acted: set = set()

    @staticmethod
    def _last(rows, attr) -> Optional[float]:
        for r in reversed(rows):
            v = getattr(r, attr, None)
            if v is not None:
                return float(v)
        return None

    def _components(self, rows: Sequence[MarketTimelineRow], sl: float):
        spots = [r.binance_spot for r in rows if r.binance_spot is not None and r.binance_spot > 0]
        if len(spots) < 3:
            return None
        import numpy as np
        arr = np.asarray(spots, dtype=float)
        r = math.log(arr[-1] / arr[0])
        persec = max(self.params.vol_floor_persec, float(np.std(np.diff(np.log(arr)))))
        return r, persec

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        if (ctx.outcome_dir or "").lower() != "up" or ctx.open_shares > 0:
            return []
        sl = ctx.seconds_to_resolution
        if sl is None or sl < p.min_secs_left or sl > p.max_secs_left:
            return []
        akey = (ctx.token_id, ctx.window_end_ts)
        if akey in self._acted:
            return []
        mid = ctx.mid
        if mid is None or not (0 < mid < 1):
            return []
        rows = list(ctx.history)
        comp = self._components(rows, sl)
        if comp is None:
            return []
        r, persec = comp
        # low-vol / no-rapid-move regime gate (no flow signals used)
        if persec > p.lowvol_persec:
            return []
        vel = self._last(rows, "binance_vel_5s_pct")
        if vel is not None and abs(vel) / 100.0 > p.rapid_vel:
            return []

        # multi-horizon drift -> remaining expected move
        ret15 = self._last(rows, "binance_ret_15m_pct")
        ret60 = self._last(rows, "binance_ret_60m_pct")
        d15 = (ret15 / 100.0) / (15 * 60) if ret15 is not None else 0.0   # per-sec
        d60 = (ret60 / 100.0) / (60 * 60) if ret60 is not None else 0.0
        drift_rate = p.w15 * d15 + p.w60 * d60
        mu_rem = drift_rate * sl
        sigma_rem = persec * math.sqrt(max(1.0, sl))
        if sigma_rem <= 0:
            return []
        p_real = _phi((r + mu_rem) / sigma_rem)
        edge = p_real - mid
        if abs(edge) < p.edge_thr:
            return []

        exp_fill = ctx.extras["expected_fill_price"]
        fee_fn = ctx.extras.get("fee_fn")
        if edge > 0:
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                f = exp_fill("buy", ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                if (p_real - f - fee) >= p.edge_min:
                    self._acted.add(akey)
                    return [Signal(side="BUY_YES", size_fraction=0.5,
                                   price_limit=min(1.0, ask + 2 * abs(f - ask) + 0.02),
                                   meta={"note": "mhd_long", "edge": round(edge, 4),
                                         "p_real": round(p_real, 3)})]
        else:
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                f = exp_fill("buy", no_ask)
                fee = fee_fn(f, 1.0) if fee_fn else 0.0
                if ((1 - p_real) - f - fee) >= p.edge_min:
                    self._acted.add(akey)
                    return [Signal(side="BUY_NO", size_fraction=0.5,
                                   price_limit=min(1.0, no_ask + 2 * abs(f - no_ask) + 0.02),
                                   meta={"note": "mhd_short", "edge": round(edge, 4),
                                         "p_real": round(p_real, 3)})]
        return []

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["MhdParams", "MhdStrategy"]
