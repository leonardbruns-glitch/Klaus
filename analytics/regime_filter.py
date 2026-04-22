"""
Pre-entry regime filter and post-entry cascade detector for bond trades.

Derived from 1170-trade dataset analysis (2026-04-22):
  - EV priors: avg_pnl by bond_entry_class (n=1170)
  - Cascade probability: P(cascade | snap30 < -5%) = 0.87  (n=329)
  - Recovery probability: P(recovery | snap30 < -5%, winner) = 0.79
  - TREND_UP hard veto: WR=0%, EV=-0.99, n=11

Architecture (3-phase stochastic path model):
  Phase 1: bond_stake_multiplier() — EV-based stake scaling (pre-entry)
  Phase 2: cascade_detected()      — Rule B trajectory classifier (T+60s)
  Phase 3: existing SL/time-exit   — unchanged, do not duplicate here

Do not change thresholds without re-running analytics/abort_threshold_sweep.py
and updating n/WR figures in comments below.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# EV priors by bond_entry_class
# ---------------------------------------------------------------------------
# Source: avg_pnl across all 1170 live trades (2026-04-22).
# Unclassified "?" baseline = -0.24 (n=815).
#
# Important: CORE/COLD has EV=+0.09 — slightly positive, do NOT block.
# Its poor WR (4.9%) is rescued to 32.1% in SMOOTH_RUNNER paths.
# The cascade detector (Phase 2) handles CORE/COLD entries that go adverse.
EV_PRIOR: dict[str, float] = {
    "CORE-B-EXP/INIT":      +3.13,   # n=6,   WR=66.7%
    "EARLY-A-PRE/COLD":     +0.94,   # n=165, WR=27.2%
    "EARLY-A-EDGE/INIT":    +0.81,   # n=6,   WR=33.3%
    "CORE-B-COMP/COLD":     +0.43,   # n=25,  WR=16.0%
    "CORE/COLD":            +0.09,   # n=82,  WR=4.9%  — enter, rely on cascade abort
    "LATE/COLD":            +0.03,   # n=15,  WR=13.3%
    "EARLY/COLD":           -0.12,   # n=4,   WR=0.0%
    "IMPULSE/INIT":         -0.58,   # n=9,   WR=11.1%
    "EARLY-A-EDGE/COLD":    -0.84,   # n=16,  WR=12.5%
    "EARLY-A-PRE/INIT":     -1.84,   # n=17,  WR=18.8% avg_pnl=-1.84
    "CORE/INIT":            -1.91,   # n=4,   WR=0.0%
}

_UNCLASSIFIED_EV: float = -0.24   # "?" bucket: n=815, avg_pnl=-0.24


def bond_stake_multiplier(
    bond_entry_class: str | None,
    bond_macro_regime: str | None,
    base_stake: float,
) -> float:
    """
    Return the stake to deploy for a bond entry.

    Single hard veto: TREND_UP (n=11, WR=0%, EV=-0.99).
    All other classes scaled by EV prior — never zeroed, because path
    trajectory may rescue marginal entries (CORE/COLD → SMOOTH_RUNNER = 32.1% WR).

    Stake tiers derived from EV sign and magnitude:
      EV ≥ +0.50 → 1.0x  (strong positive)
      EV ≥  0.00 → 0.75x (marginal positive)
      EV ≥ -0.50 → 0.50x (mild negative)
      EV <  -0.50 → 0.25x (strongly negative, minimum exposure)
    """
    if bond_macro_regime == "TREND_UP":
        return 0.0   # hard veto: underlying moving against bond thesis

    ev = EV_PRIOR.get(bond_entry_class or "?", _UNCLASSIFIED_EV)

    if ev >= 0.50:
        return base_stake * 1.0
    if ev >= 0.00:
        return base_stake * 0.75
    if ev >= -0.50:
        return base_stake * 0.50
    return base_stake * 0.25


def cascade_detected(
    snap30: float | None,
    snap60: float | None,
    bond_entry_class: str | None = None,
) -> tuple[bool, str]:
    """
    Rule B cascade detector. Returns (should_abort, exit_reason).

    Design rationale:
      - P(cascade | snap30 < -5%) = 0.87 — high, but 0.79 of adverse winners
        recover between T+30s and T+60s. Aborting on snap30 alone destroys
        mean-reversion edge (Rule A is net negative across all thresholds).
      - Rule B requires snap60 ≤ snap30 to distinguish cascade from wick:
        cascade = price still falling at T+60s (abort)
        recovery = snap60 > snap30 (hold, likely winner)
      - CORE/COLD exception: single snap30 < -5% is sufficient because
        CORE/COLD in EARLY_CHOP or DEAD_DRIFT path has 0% WR (n=53 trades).

    Caller must populate pos.entry_snap_30s_pct at T+30s and
    pos.entry_snap_60s_pct at T+60s during position monitoring.
    Values of 0.0 mean "not yet measured" — do not abort on 0.0.
    """
    if not snap30 or snap30 == 0.0:
        return False, ""

    # CORE/COLD: no need to wait for continuation — recovery less likely here
    if bond_entry_class == "CORE/COLD" and snap30 < -5.0:
        return True, f"BOND_ABORT_CASCADE: CORE/COLD snap30={snap30:.1f}%"

    # Rule B: cascade confirmed (price still falling, not a wick)
    if snap30 < -5.0 and snap60 is not None and snap60 != 0.0 and snap60 <= snap30:
        return True, (
            f"BOND_ABORT_CASCADE: snap30={snap30:.1f}% snap60={snap60:.1f}% (continuing)"
        )

    return False, ""
