"""Hold-path evolution recorder — Phase 2.

For every virtual position (first gate_trace.all_pass=True per (token_id,
window_end_ts)), records one hold_path row per second while the virtual
position is "held", until the window closes.

Substrate for per-second MAE/MFE, drawdown velocity, imbalance evolution,
liquidity collapse, momentum decay, divergence vs Binance — per
shadow_engine_principles directive #5 (hold-path is highest-value Phase-2
component).

Not coupled to live position state. Receives (market_timeline, gate_trace)
records from TimelineSampler via on_tick().
"""
from typing import Dict, Optional, Tuple

from .pipeline import ShadowPipeline

SCHEMA_VERSION = 2

_MAX_HOLD_S = 400  # force-evict virtual positions older than this


class HoldPathSampler:
    def __init__(self, pipeline: ShadowPipeline) -> None:
        self.pipe = pipeline
        # (token_id, window_end_ts) -> running state dict
        self._vpos: Dict[Tuple[str, int], dict] = {}

    def on_tick(self, tl: dict, gt: Optional[dict]) -> None:
        """Call after each (market_timeline, gate_trace) pair from TimelineSampler."""
        key = (tl["token_id"], tl["window_end_ts"])
        now_s = tl["ts_s"]
        sec = tl["seconds_to_resolution"]

        # Open on FIRST terminal-zone entry (25-120s), regardless of gate state.
        # Full counterfactual coverage per directive #2: gate-qualified and
        # gate-rejected entries are comparable in the same dataset. Gate state
        # at open + at every tick is stored so analysts can slice either way.
        if 25.0 <= sec <= 120.0 and key not in self._vpos:
            gate_pass = gt["all_pass"] if gt is not None else False
            first_fail = (gt.get("first_failed_gate") or "") if gt is not None else ""
            self._vpos[key] = {
                "fire_ask": tl["best_ask"],
                "fire_ts_s": now_s,
                "fire_sec_to_res": sec,
                "gate_all_pass_at_open": gate_pass,
                "first_failed_gate_at_open": first_fail,
                "mae": 0.0,
                "mfe": 0.0,
                "last_bid": tl["best_bid"],
                "last_depth": tl["ob_book_depth_size"],
            }

        if key not in self._vpos:
            return

        vp = self._vpos[key]
        fire_ask = vp["fire_ask"]
        if fire_ask <= 0:
            return

        bid = tl["best_bid"]
        depth = tl["ob_book_depth_size"]
        pnl_pct = (bid - fire_ask) / fire_ask * 100.0
        vp["mae"] = min(vp["mae"], pnl_pct)
        vp["mfe"] = max(vp["mfe"], pnl_pct)

        bid_vel = bid - vp["last_bid"]
        depth_delta = depth - vp["last_depth"]
        vp["last_bid"] = bid
        vp["last_depth"] = depth

        seconds_held = now_s - vp["fire_ts_s"]

        gate_pass_now = gt["all_pass"] if gt is not None else False

        self.pipe.emit({
            "schema_version": SCHEMA_VERSION,
            "record_type": "hold_path",
            "ts_s": now_s,
            "ts_ms_local": tl["ts_ms_local"],
            "token_id": tl["token_id"],
            "condition_id": tl["condition_id"],
            "asset": tl["asset"],
            "outcome_dir": tl["outcome_dir"],
            "outcome_side": tl["outcome_side"],
            "window_end_ts": tl["window_end_ts"],
            "seconds_to_resolution": tl["seconds_to_resolution"],
            # virtual position provenance
            "fire_ask": round(fire_ask, 4),
            "fire_ts_s": vp["fire_ts_s"],
            "fire_sec_to_res": round(vp["fire_sec_to_res"], 1),
            "seconds_held": seconds_held,
            # gate state — enables entry-timing analysis:
            #   gate_all_pass_at_open: was the gate green when this vpos opened?
            #   gate_all_pass_now: is the gate green at THIS tick?
            #   filtering on gate_all_pass_at_open=True replicates current bot behaviour;
            #   filtering on gate_all_pass_now=True gives "optimal entry timing" surface.
            "gate_all_pass_at_open": vp["gate_all_pass_at_open"],
            "first_failed_gate_at_open": vp["first_failed_gate_at_open"],
            "gate_all_pass_now": gate_pass_now,
            # price state
            "bid": round(bid, 4),
            "ask": round(tl["best_ask"], 4),
            "mid": round(tl["mid"], 4),
            "spread_abs": round(tl["spread_abs"], 4),
            # synthetic PnL trajectory (vs fire_ask)
            "pnl_pct": round(pnl_pct, 4),
            "mae": round(vp["mae"], 4),
            "mfe": round(vp["mfe"], 4),
            "bid_velocity_1s": round(bid_vel, 4),
            # OB evolution
            "ob_imb_top3": tl["ob_imb_top3"],
            "ob_book_depth_size": depth,
            "ob_depth_delta_1s": round(depth_delta, 2),
            "ob_quote_age_ms": tl["ob_quote_age_ms"],
            # external reference
            "binance_spot": tl["binance_spot"],
            "binance_ret_5m_pct": tl["binance_ret_5m_pct"],
            "binance_ret_60s_pct": tl["binance_ret_60s_pct"],
            # regime (self-contained — no join needed for conditional analysis)
            "session_bucket": tl["session_bucket"],
            "hour_utc": tl["hour_utc"],
            "weekday": tl["weekday"],
            "vol_regime": tl.get("vol_regime", ""),
            "trend_regime": tl.get("trend_regime", ""),
            "liquidity_regime": tl.get("liquidity_regime", ""),
        })

        if tl["seconds_to_resolution"] <= 1.0 or seconds_held > _MAX_HOLD_S:
            del self._vpos[key]

    def gc_stale(self, now_s: float) -> None:
        """Evict virtual positions whose window has long since closed."""
        cutoff = int(now_s) - _MAX_HOLD_S
        stale = [k for k, v in self._vpos.items() if v["fire_ts_s"] < cutoff]
        for k in stale:
            del self._vpos[k]
