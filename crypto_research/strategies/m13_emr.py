"""M13 — Execution Microstructure Reversal (EMR).

Goal
----
Pure mechanical post-shock reversion: a large aggressive move dislocates the
binary price, and that impact PARTIALLY reverts within seconds-to-minutes.  No
valuation, no fair value, no prediction — enter AGAINST the shock only after it
has exhausted (no continuation), exit on micro-reversion.

Mechanism
---------
* Shock: |5s velocity| (flow/impact proxy) > shock_vel  (timeline has no
  per-tick buy/sell volume in on_step, so velocity is the impact proxy).
* Record shock direction and the pre-shock mid.
* Exhaustion: |velocity| decays below decay_frac·peak for >= min_exh steps with
  no fresh continuation.
* Enter AGAINST the move: up-shock exhausted -> BUY_NO; down-shock -> BUY_YES.
* Exit (FLAT): mid reverts toward pre-shock mid (target capture), OR renewed
  flow (|velocity| spikes again), OR time cap.

Honest prior: the repo's taker-fade was FALSIFIED (flow is informed) and M6's
mid-reversion lost −77.8% to fees.  EMR's distinct claim is *short-horizon impact
reversion gated on exhaustion*.  The test decides; the bar is clearing 2×fees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy


@dataclass
class EmrParams(StrategyParams):
    shock_vel: float = 0.0006      # |5s velocity| (frac) shock threshold
    decay_frac: float = 0.4        # |vel| below this fraction of peak = exhausted
    min_exh: int = 2               # consecutive exhausted steps required
    target_revert: float = 0.02    # FLAT when mid reverts this far toward pre-shock
    renew_vel: float = 0.0008      # renewed flow -> abort/exit
    time_cap_secs: float = 90.0    # max hold
    min_secs_left: float = 45.0
    edge_min: float = 0.0
    max_position_frac: float = 0.08
    per_window_budget_frac: float = 0.15


@register_strategy("emr_reversal")
class EmrStrategy(Strategy):
    params_cls = EmrParams

    def __init__(self, params: Optional[EmrParams] = None) -> None:
        super().__init__(params)
        self.params: EmrParams
        self._st: Dict[str, dict] = {}
        self._pos: Dict[str, dict] = {}   # entry mid, dir, entry_sl
        self._acted: set = set()

    @staticmethod
    def _vel(rows: Sequence[MarketTimelineRow]) -> float:
        for r in reversed(rows):
            if r.binance_vel_5s_pct is not None:
                return float(r.binance_vel_5s_pct) / 100.0
        return 0.0

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        tok = ctx.token_id
        rows = list(ctx.history)
        mid = ctx.mid
        sl = ctx.seconds_to_resolution or 0.0
        vel = self._vel(rows)

        # ---- manage open leg ----
        if ctx.open_shares > 0 and tok in self._pos:
            pos = self._pos[tok]
            is_up = pos["dir_long"]
            reverted = mid is not None and (
                (is_up and mid >= pos["entry_mid"] + p.target_revert) or
                ((not is_up) and mid <= pos["entry_mid"] - p.target_revert)
            )
            reasons = []
            if reverted:
                reasons.append("reverted")
            if abs(vel) > p.renew_vel:
                reasons.append("renewed_flow")
            if (pos["entry_sl"] - sl) > p.time_cap_secs:
                reasons.append("time_cap")
            if reasons:
                return [Signal(side="FLAT", meta={"reason": ",".join(reasons)})]
            return []

        if (ctx.outcome_dir or "").lower() != "up":
            return []
        if sl < p.min_secs_left or mid is None:
            return []
        akey = (tok, ctx.window_end_ts)
        if akey in self._acted:
            return []

        st = self._st.setdefault(tok, {"active": False, "pre_mid": mid,
                                       "peak": 0.0, "exh": 0, "dir_up": True})
        if not st["active"]:
            st["pre_mid"] = mid
            if abs(vel) > p.shock_vel:
                st["active"] = True
                st["peak"] = abs(vel)
                st["exh"] = 0
                st["dir_up"] = vel > 0   # up-shock vs down-shock
            return []
        # shock active: wait for exhaustion (no continuation)
        st["peak"] = max(st["peak"], abs(vel))
        if abs(vel) < p.decay_frac * st["peak"]:
            st["exh"] += 1
        else:
            st["exh"] = 0
        if st["exh"] < p.min_exh:
            return []

        exp_fill = ctx.extras["expected_fill_price"]
        # enter AGAINST the shock
        if st["dir_up"]:   # up-shock exhausted -> fade with NO
            peer = ctx.peer
            no_ask = peer.get("best_ask") if peer else None
            if no_ask is not None and 0 < no_ask < 1:
                exp_fill("buy", no_ask)
                self._acted.add(akey)
                self._pos[tok] = {"entry_mid": mid, "dir_long": False, "entry_sl": sl}
                return [Signal(side="BUY_NO", size_fraction=0.5,
                               price_limit=min(1.0, no_ask + 0.02),
                               meta={"note": "emr_fade_up"})]
        else:              # down-shock exhausted -> fade with YES
            ask = ctx.best_ask
            if ask is not None and 0 < ask < 1:
                exp_fill("buy", ask)
                self._acted.add(akey)
                self._pos[tok] = {"entry_mid": mid, "dir_long": True, "entry_sl": sl}
                return [Signal(side="BUY_YES", size_fraction=0.5,
                               price_limit=min(1.0, ask + 0.02),
                               meta={"note": "emr_fade_down"})]
        return []

    def on_window_close(self, panel: WindowPanel, resolved_yes_for_token: int) -> None:
        self._st.pop(panel.token_id, None)
        self._pos.pop(panel.token_id, None)
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["EmrParams", "EmrStrategy"]
