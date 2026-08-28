"""Exit-policy shadow logger — Deliverable 3 of the 2026-05-08 audit.

For each `gate_trace.all_pass=True` first-fire (deduped per
(token_id, window_end_ts)), runs the candidate exit policy forward over
subsequent `market_timeline` ticks until a trigger condition fires, then
emits ONE `exit_policy_shadow` record per (first_fire, policy_id).

Triggers per policy:
  - "PT"           — bid >= PT threshold
  - "FALLBACK_30s" — hold time >= 30s and PT not yet hit
  - "WINDOW_END"   — seconds_to_resolution <= 5 and no other trigger fired

Joins:
  - gate_trace        via (token_id, window_end_ts) [first-fire]
  - market_timeline   via (token_id, ts_s) [path verification]
  - window_resolution via (condition_id, window_end_ts) [outcome]
  - trades.jsonl      via (token_id, fire_ts_s ≈ ts_open) [vs-live]

Validation criteria for live policy swap (per audit Deliverable 3):
  n>=500 unique fires, >=5 days, every regime quartile n>=40,
  realistic_pnl_pct mean >= +1.0%, worst quartile >= -1.0%,
  bid-evap derate (clean-realistic) <= 0.5pp, cat-rate (<=-70%) <= 2%.
"""
import logging
import time
from typing import Dict, Optional, Set, Tuple

from .pipeline import ShadowPipeline

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


# ---- Policy registry ----
# Each policy returns Optional[(trigger_str, exit_bid)] given (state, tick).
def _policy_pt95_plus_30s(state: dict, tick: dict) -> Optional[tuple]:
    bid = float(tick["best_bid"])
    if bid >= 0.95:
        return ("PT", bid)
    if (tick["ts_s"] - state["fire_ts"]) >= 30.0:
        return ("FALLBACK_30s", bid)
    return None


def _policy_pt93_plus_30s(state: dict, tick: dict) -> Optional[tuple]:
    bid = float(tick["best_bid"])
    if bid >= 0.93:
        return ("PT", bid)
    if (tick["ts_s"] - state["fire_ts"]) >= 30.0:
        return ("FALLBACK_30s", bid)
    return None


def _policy_be_trail_5_3(state: dict, tick: dict) -> Optional[tuple]:
    bid = float(tick["best_bid"])
    fire_ask = state["fire_ask"]
    if fire_ask <= 0:
        return None
    mfe_pct = (state.get("mfe_bid", bid) - fire_ask) / fire_ask * 100.0
    state["mfe_bid"] = max(state.get("mfe_bid", bid), bid)
    if bid >= 0.95:
        return ("PT", bid)
    # If MFE has reached >=5% above entry-ask, arm BE-trail at MFE-3pp.
    armed_mfe = (state["mfe_bid"] - fire_ask) / fire_ask * 100.0
    if armed_mfe >= 5.0:
        trail_floor_pct = armed_mfe - 3.0
        cur_pct = (bid - fire_ask) / fire_ask * 100.0
        if cur_pct <= trail_floor_pct:
            return ("BE_TRAIL", bid)
    return None


def _policy_gate_died(state: dict, tick: dict) -> Optional[tuple]:
    """PT0.95 + gate-degradation exit + 30s fallback.

    Fires GATE_DIED when the entry gates that approved this fire stop passing
    on subsequent ticks. `gate_all_pass_now` is updated by evaluate_tick from
    the live gate_trace record. Default-None means we lack a fresh gate_trace
    for this tick — do not fire on missing data.
    """
    bid = float(tick["best_bid"])
    if bid >= 0.95:
        return ("PT", bid)
    if state.get("gate_all_pass_now") is False:
        return ("GATE_DIED", bid)
    if (tick["ts_s"] - state["fire_ts"]) >= 30.0:
        return ("FALLBACK_30s", bid)
    return None


_POLICIES = {
    "PT0.95+30s":     _policy_pt95_plus_30s,
    "PT0.93+30s":     _policy_pt93_plus_30s,
    "BE_trail_5_3":   _policy_be_trail_5_3,
    "gate_died":      _policy_gate_died,
}

# Reference share-count for fill-realism check. A first-fire under live's $7
# safety cap at ask~0.85 ⇒ ~8.2 shares; round to 10 for a conservative bar.
_REF_SHARES = 10.0


class ExitPolicyShadow:
    def __init__(self, pipeline: ShadowPipeline) -> None:
        self.pipe = pipeline
        # (token_id, window_end_ts) → state dict
        self._active: Dict[Tuple[str, int], dict] = {}
        # (token_id, window_end_ts) → set of policy_ids already emitted
        self._emitted: Dict[Tuple[str, int], Set[str]] = {}
        self.first_fires_seen = 0
        self.records_emitted = 0

    def register_first_fire(self, tl_rec: dict, gt_rec: dict) -> None:
        """Idempotent. Called from TimelineSampler at gate_trace emission.
        Records the first tick where all_pass=True for a (token, window)."""
        if not gt_rec.get("all_pass"):
            return
        try:
            wend = int(tl_rec["window_end_ts"])
        except (KeyError, TypeError, ValueError):
            return
        if wend <= 0:
            return
        key = (tl_rec["token_id"], wend)
        if key in self._active or key in self._emitted:
            return
        try:
            self._active[key] = {
                "fire_ts":              float(tl_rec["ts_s"]),
                "fire_ask":             float(tl_rec["best_ask"]),
                "condition_id":         tl_rec.get("condition_id", "") or "",
                "asset":                tl_rec.get("asset", ""),
                "outcome_dir":          tl_rec.get("outcome_dir", ""),
                "outcome_side":         tl_rec.get("outcome_side", ""),
                "window_end_ts":        wend,
                "sec_to_res_at_fire":   float(tl_rec.get("seconds_to_resolution", 0.0)),
                "bnc_5m_pct":           float(tl_rec.get("binance_ret_5m_pct", 0.0)),
                "snap30":               float(tl_rec.get("tok_snap_30s", 0.0)),
                "snap60":               float(tl_rec.get("tok_snap_60s", 0.0)),
                "hour_utc":             int(tl_rec.get("hour_utc", 0)),
                "session_bucket":       tl_rec.get("session_bucket", ""),
                "remaining_policies":   set(_POLICIES.keys()),
                "mfe_bid":              float(tl_rec.get("best_bid", 0.0)),
            }
            self._emitted[key] = set()
            self.first_fires_seen += 1
        except Exception:
            logger.debug("exit_policy register_first_fire failed", exc_info=True)

    def evaluate_tick(self, tl_rec: dict, gt_rec: Optional[dict] = None) -> None:
        """Called from TimelineSampler every market_timeline emission.
        Evaluates active position for this (token, window) against all
        remaining policies; emits records when policies fire.

        `gt_rec` is the same-tick gate_trace record (may be None if not
        built); gate-degradation policy reads `all_pass` from it.
        """
        try:
            wend = int(tl_rec["window_end_ts"])
        except (KeyError, TypeError, ValueError):
            return
        key = (tl_rec["token_id"], wend)
        state = self._active.get(key)
        if state is None:
            return
        # Update running MFE for trail-style policies.
        try:
            state["mfe_bid"] = max(state.get("mfe_bid", 0.0), float(tl_rec.get("best_bid", 0.0)))
        except Exception:
            pass
        # Update gate-degradation signal from current tick's gate_trace.
        if gt_rec is not None:
            state["gate_all_pass_now"] = bool(gt_rec.get("all_pass"))
        # Evaluate each remaining policy at this tick.
        for pid in list(state["remaining_policies"]):
            pol = _POLICIES.get(pid)
            if pol is None:
                state["remaining_policies"].discard(pid)
                continue
            try:
                fired = pol(state, tl_rec)
            except Exception:
                logger.debug("policy %s eval failed", pid, exc_info=True)
                state["remaining_policies"].discard(pid)
                continue
            if fired is not None:
                trigger, exit_bid = fired
                self._emit(state, pid, tl_rec, trigger, float(exit_bid))
                state["remaining_policies"].discard(pid)
                self._emitted[key].add(pid)
        # Window-end backstop: force-emit any remaining policies as WINDOW_END.
        try:
            sec_to_res = float(tl_rec.get("seconds_to_resolution", 999.0))
        except Exception:
            sec_to_res = 999.0
        if sec_to_res <= 5.0:
            for pid in list(state["remaining_policies"]):
                self._emit(state, pid, tl_rec, "WINDOW_END", float(tl_rec.get("best_bid", 0.0)))
                self._emitted[key].add(pid)
            state["remaining_policies"].clear()
        # Cleanup if nothing remains.
        if not state["remaining_policies"]:
            self._active.pop(key, None)

    def _emit(
        self,
        state: dict,
        pid: str,
        tl_rec: dict,
        trigger: str,
        exit_bid: float,
    ) -> None:
        fire_ask = state["fire_ask"]
        if fire_ask <= 0:
            return
        bid_size = float(tl_rec.get("ob_top1_bid_size", 0.0))
        clean_pnl_pct = (exit_bid - fire_ask) / fire_ask * 100.0
        # Realistic-sim bid-evaporation derate. Floor: a partial fill at exit_bid
        # for bid_size shares; remainder slips one tick (1% conservative).
        # When bid_size < REF_SHARES, we pay a haircut proportional to depth gap.
        if bid_size >= _REF_SHARES:
            realistic_bid = exit_bid
            fill_ok = True
        else:
            partial_frac = max(0.0, bid_size / _REF_SHARES) if _REF_SHARES > 0 else 0.0
            slip_frac = 1.0 - partial_frac
            realistic_bid = (partial_frac * exit_bid) + (slip_frac * exit_bid * 0.99)
            fill_ok = False
        realistic_pnl_pct = (realistic_bid - fire_ask) / fire_ask * 100.0
        rec = {
            "schema_version":      SCHEMA_VERSION,
            "record_type":         "exit_policy_shadow",
            "ts_s":                int(time.time()),
            "token_id":            tl_rec["token_id"],
            "condition_id":        state["condition_id"],
            "asset":               state["asset"],
            "outcome_dir":         state["outcome_dir"],
            "outcome_side":        state["outcome_side"],
            "window_end_ts":       state["window_end_ts"],
            "fire_ts_s":           int(state["fire_ts"]),
            "fire_ask":            round(state["fire_ask"], 4),
            "sec_to_res_at_fire":  round(state["sec_to_res_at_fire"], 1),
            "policy_id":           pid,
            "exit_ts_s":           int(tl_rec["ts_s"]),
            "exit_bid":            round(exit_bid, 4),
            "exit_bid_size":       round(bid_size, 2),
            "exit_trigger":        trigger,
            "clean_pnl_pct":       round(clean_pnl_pct, 4),
            "realistic_pnl_pct":   round(realistic_pnl_pct, 4),
            "fill_ok":             fill_ok,
            "hold_seconds":        round(int(tl_rec["ts_s"]) - state["fire_ts"], 1),
            # regime tags (snapshotted at first-fire so cohort assignment is stable):
            "bnc_5m_pct":          round(state["bnc_5m_pct"], 4),
            "snap30":              round(state["snap30"], 4),
            "snap60":              round(state["snap60"], 4),
            "hour_utc":            state["hour_utc"],
            "session_bucket":      state["session_bucket"],
            "direction":           state["outcome_dir"],
        }
        self.pipe.emit(rec)
        self.records_emitted += 1

    def stats(self) -> dict:
        return {
            "first_fires_seen": self.first_fires_seen,
            "records_emitted": self.records_emitted,
            "active_positions": len(self._active),
        }
