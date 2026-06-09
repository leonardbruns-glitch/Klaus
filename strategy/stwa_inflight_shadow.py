"""
stwa_inflight_shadow.py — SHADOW-ONLY in-flight position re-evaluation for STWA.

WHAT THIS IS
------------
The live engine holds every STWA position to daily-max settlement and never re-evaluates
it intraday. But the forecast distribution DOES move while we hold (NWP run-to-run + new
METARs). The dormant live switcher (`weather_arb._update_and_maybe_switch`) keys on a
PHYSICAL proxy — mu_delta in °C — with NO notion of whether the *calibrated probability*
change is worth the round-trip cost, so it would chase a 0.1 °C NWP wobble straight into vig.

This module is the cost-aware, provenance-aware GATE the brief (Task 3) asks for, shipped
LOG-ONLY first. Every scan it classifies each open STWA bucket and records the would-be
OPEN / HOLD / SWITCH / CLOSE decision plus the inputs needed to score counterfactual PnL
against hold-to-resolution. It NEVER trades. A live exit is a separate, explicit Tier-3 step
that stays gated on: n>=100 confirmed CLOSE triggers whose counterfactual EV beats hold AND
the official-oracle gate showing zero false-closes on eventual winners.

THE MATH  (verified; fee curve = fee_model.taker_fee_rate, redemption is fee-free)
----------------------------------------------------------------------------------
Let, for a held YES bucket B = [lo, hi):
    g_held  = g(p) now for B           (cal_probs_last[B]; isotonic-recalibrated win prob)
    bid_held= current best YES bid on B (the *liquidation* value if we sell — NOT the sunk
                                         entry ask; using entry ask understates abandon cost)
    g_new   = g(p) now for the model's currently-preferred bucket B'
    a_new   = current best YES ask on B'
    M0      = official_running_max_c   (clean AWC/NWS oracle ONLY — never running_max_c)

PROVENANCE splits the hysteresis asymmetrically:

(1) CONFIRMED_LOCKOUT  (M0 >= hi):  monotone & irreversible — B can NEVER resolve YES.
    g_held -> 0 by the running-max floor. This trigger CANNOT fire on a winner (structural),
    so it needs NO dwell — provenance itself is the confirmation.
        salvage = bid_held * (1 - fee(bid_held))        # taker proceeds on a token worth 0
        if bid_held > SALVAGE_MIN_BID and salvage > 0:  -> CLOSE_LOCKED_LOSER (dump for salvage)
        else:                                            -> HOLD_DEAD (0-bid, no paid exit)
    (This is the SELL-side mirror of what M1β harvests on the buy side.)

(2) FORECAST_WOBBLE  (B not locked, model now prefers B' != B): reversible — wide dead-band.
    Forward-EV of switching (sunk entry cost ignored; held leg liquidated at its CURRENT bid):
        switch_gain = (g_new - a_new) - (g_held - bid_held)
        C_rt        = fee(bid_held) + fee(a_new) + spread + slip      # paid round-trip
    HOLD unless  switch_gain > C_rt + HYST_PAD.   Pure sub-cost NWP noise => HOLD (kills churn).
    A SWITCH must additionally survive the existing dwell ladder (required_runs consecutive
    scans agreeing on the same B'), so a one-scan wobble never fires.

velocity / first-passage (dV) belongs HERE and ONLY here — as an internal down-weight that
shrinks an *unconfirmed* implied rise (multiplies the wobble's effective Δg). It is never a
standalone trigger (that dead-end is falsified). Passed in as `vel_downweight` in [0,1].

Sizing on any post-close redeploy is unchanged: it flows through the live entry gate +
Tier-4 held_k_by_city budget. This module proposes nothing about size.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from strategy.fee_model import taker_fee_rate, estimate_spread

# Mirrors weather_arb.SALVAGE_MIN_BID (only bother selling above this; below it the loss is
# already ~0 and the spread eats the proceeds).
SALVAGE_MIN_BID = 0.05
# Hysteresis pad on top of round-trip cost — the dead-band half-width in EV/share. Switching
# must beat cost by this margin, so a forecast that merely ties cost does not churn.
HYST_PAD = 0.02
# Default per-share slippage estimate when a depth-aware figure is unavailable.
DEFAULT_SLIP = 0.005

_SHADOW_FILE = "stwa_inflight_shadow.jsonl"


def _dwell_required_runs(mu_delta_c: float) -> int:
    """Reuse the live ladder (weather_arb.py:2970-2977): bigger revision -> fewer confirms."""
    if mu_delta_c >= 1.5:
        return 1
    if mu_delta_c >= 0.8:
        return 2
    if mu_delta_c >= 0.35:
        return 3
    return 5


@dataclass
class InflightDecision:
    decision: str            # HOLD | HOLD_DEAD | CLOSE_LOCKED_LOSER | SWITCH | SWITCH_PENDING | OPEN_OK
    provenance: str          # CONFIRMED_LOCKOUT | FORECAST_WOBBLE | NONE
    reason: str
    # economics (per share, °C where noted)
    g_held: float
    bid_held: float
    g_new: Optional[float] = None
    a_new: Optional[float] = None
    switch_gain: Optional[float] = None      # forward-EV advantage of switching
    c_rt: Optional[float] = None             # round-trip cost
    salvage: Optional[float] = None          # taker proceeds on a locked-loser dump
    mu_delta_c: Optional[float] = None
    required_runs: Optional[int] = None
    n_agree: Optional[int] = None
    # counterfactual hooks (scored offline against resolution)
    held_lo: Optional[float] = None
    held_hi: Optional[float] = None
    official_running_max_c: Optional[float] = None
    vel_downweight: float = 1.0


def evaluate_inflight(
    *,
    held_lo: float,
    held_hi: float,
    g_held: float,
    bid_held: float,
    official_running_max_c: Optional[float],
    is_celsius_market: bool = True,
    # forecast-wobble inputs (None when the model still prefers the held bucket)
    g_new: Optional[float] = None,
    a_new: Optional[float] = None,
    mu_delta_c: float = 0.0,
    n_agree: int = 0,
    vel_downweight: float = 1.0,
    # cost inputs
    spread: Optional[float] = None,
    slip: float = DEFAULT_SLIP,
) -> InflightDecision:
    """Pure decision core. No I/O, no trading. Returns the would-be action + economics.

    Provenance-asymmetric hysteresis:
      * CONFIRMED_LOCKOUT (official running_max past the bucket ceiling) -> immediate
        CLOSE_LOCKED_LOSER if a salvageable stale bid exists, else HOLD_DEAD. No dwell.
      * else FORECAST_WOBBLE -> wide forward-EV dead-band + dwell ladder.
    """
    # Unit-aware bucket pad is already applied upstream in hi/lo; the lock test is a plain
    # comparison against the clean official oracle.
    pad = 0.5  # °F or °C half-degree padding sense already baked into hi by the engine;
    # we compare directly: a bucket is locked once the official max has cleared its ceiling.

    # ── (1) CONFIRMED_LOCKOUT — monotone, irreversible, cannot hit a winner ──────────────
    if official_running_max_c is not None and official_running_max_c >= held_hi:
        salvage = bid_held * (1.0 - taker_fee_rate(bid_held))
        if bid_held > SALVAGE_MIN_BID and salvage > 0.0:
            return InflightDecision(
                decision="CLOSE_LOCKED_LOSER", provenance="CONFIRMED_LOCKOUT",
                reason=f"official max {official_running_max_c:.2f} >= ceiling {held_hi:.2f}; "
                       f"bucket resolves NO; salvage stale bid {bid_held:.3f}",
                g_held=g_held, bid_held=bid_held, salvage=round(salvage, 4),
                held_lo=held_lo, held_hi=held_hi,
                official_running_max_c=official_running_max_c,
            )
        return InflightDecision(
            decision="HOLD_DEAD", provenance="CONFIRMED_LOCKOUT",
            reason=f"locked NO but bid {bid_held:.3f} <= SALVAGE_MIN_BID {SALVAGE_MIN_BID}; "
                   f"no paid exit on a ~0 token",
            g_held=g_held, bid_held=bid_held, salvage=round(bid_held, 4),
            held_lo=held_lo, held_hi=held_hi,
            official_running_max_c=official_running_max_c,
        )

    # ── (2) FORECAST_WOBBLE — reversible; act only if forward-EV beats round-trip cost ───
    if g_new is None or a_new is None:
        return InflightDecision(
            decision="HOLD", provenance="NONE",
            reason="model still prefers held bucket (no alternative)",
            g_held=g_held, bid_held=bid_held,
            held_lo=held_lo, held_hi=held_hi,
            official_running_max_c=official_running_max_c, vel_downweight=vel_downweight,
        )

    if spread is None:
        spread = estimate_spread()
    c_rt = taker_fee_rate(bid_held) + taker_fee_rate(a_new) + spread + slip

    # Forward-EV: liquidate held at its CURRENT bid (not sunk entry ask). Down-weight an
    # unconfirmed implied rise via the velocity gate (shrinks the new bucket's apparent edge).
    edge_new = (g_new - a_new) * max(0.0, min(1.0, vel_downweight))
    edge_held = g_held - bid_held
    switch_gain = edge_new - edge_held

    required_runs = _dwell_required_runs(mu_delta_c)
    beats_cost = switch_gain > (c_rt + HYST_PAD)

    if not beats_cost:
        decision, reason = "HOLD", (
            f"switch_gain {switch_gain:+.3f} <= C_rt+pad {c_rt + HYST_PAD:.3f} — dead-band")
    elif n_agree < required_runs:
        decision, reason = "SWITCH_PENDING", (
            f"switch_gain {switch_gain:+.3f} > cost but dwell {n_agree}/{required_runs} "
            f"(mu_delta {mu_delta_c:.2f}°C)")
    else:
        decision, reason = "SWITCH", (
            f"switch_gain {switch_gain:+.3f} > C_rt+pad {c_rt + HYST_PAD:.3f} and "
            f"dwell {n_agree}/{required_runs} satisfied")

    return InflightDecision(
        decision=decision, provenance="FORECAST_WOBBLE", reason=reason,
        g_held=g_held, bid_held=bid_held, g_new=g_new, a_new=a_new,
        switch_gain=round(switch_gain, 4), c_rt=round(c_rt, 4),
        mu_delta_c=round(mu_delta_c, 3), required_runs=required_runs, n_agree=n_agree,
        held_lo=held_lo, held_hi=held_hi,
        official_running_max_c=official_running_max_c, vel_downweight=vel_downweight,
    )


def log_inflight_decision(city: str, end_date: str, token_id: str,
                          dec: InflightDecision,
                          log_root: str = "logs/shadow/hot") -> None:
    """Append the decision to today's shadow JSONL. Best-effort; never raises into the caller."""
    try:
        import datetime as _dt
        day = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        d = Path(log_root) / day
        d.mkdir(parents=True, exist_ok=True)
        row = {"ts_utc": time.time(), "city": city, "end_date": end_date,
               "token_id": token_id, **asdict(dec)}
        with (d / _SHADOW_FILE).open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


# ── self-test: runs the canonical scenarios; no I/O, no network ──────────────────────────
if __name__ == "__main__":
    def show(name, dec):
        print(f"{name:<34} -> {dec.decision:<18} | {dec.reason}")

    # A) locked loser WITH a salvageable stale bid -> CLOSE
    show("locked-loser, stale bid 0.44",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.01, bid_held=0.44,
                           official_running_max_c=29.3))
    # B) locked loser, dead 0-bid -> HOLD_DEAD (no paid exit on a zero)
    show("locked-loser, bid 0.02",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.01, bid_held=0.02,
                           official_running_max_c=29.3))
    # C) forecast wobble inside the dead-band (tiny edge gain) -> HOLD
    show("wobble: +0.01 edge, sub-cost",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.40, bid_held=0.38,
                           official_running_max_c=22.0,
                           g_new=0.45, a_new=0.44, mu_delta_c=0.1, n_agree=1))
    # D) big confirmed revision beyond cost, dwell satisfied -> SWITCH
    show("wobble: big edge, dwell met",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.20, bid_held=0.18,
                           official_running_max_c=22.0,
                           g_new=0.70, a_new=0.40, mu_delta_c=1.6, n_agree=1))
    # E) same big edge but dwell not yet met -> SWITCH_PENDING
    show("wobble: big edge, dwell pending",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.20, bid_held=0.18,
                           official_running_max_c=22.0,
                           g_new=0.70, a_new=0.40, mu_delta_c=0.4, n_agree=1))
    # F) velocity down-weight kills an unconfirmed-rise wobble -> HOLD
    show("wobble: edge real but vel=0.2",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.20, bid_held=0.18,
                           official_running_max_c=22.0,
                           g_new=0.70, a_new=0.40, mu_delta_c=1.6, n_agree=2,
                           vel_downweight=0.2))
    # G) model still prefers held bucket -> HOLD
    show("no alternative bucket",
         evaluate_inflight(held_lo=24.5, held_hi=25.5, g_held=0.55, bid_held=0.52,
                           official_running_max_c=22.0))
