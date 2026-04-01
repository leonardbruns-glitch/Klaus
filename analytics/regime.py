"""
Klaus — Market Regime Classifier

Classifies current market conditions into a regime label used to:
  1. Tag every trade and shadow block for post-session analysis
  2. Adapt sniper gate parameters once enough regime-specific data exists
  3. Surface regime performance in the feedback report

Regime labels
─────────────
  ACTIVE_HOT   Active session hour + VPIN ≥ 0.55 (informed flow confirmed)
               Best edge window. Data target: 40%+ WR, >3 trades/day.

  ACTIVE_WARM  Active session hour + VPIN 0.35–0.55
               Moderate edge. Some moves are informed, some noise.

  ACTIVE_COLD  Active session hour + VPIN < 0.35
               Session time but no informed flow. Treat like quiet hours.

  QUIET_FLOW   Off-peak hour + VPIN ≥ 0.45
               Unusual flow outside normal session — worth watching.

  QUIET_DEAD   Off-peak hour + VPIN < 0.45
               Thin books, no informed flow. Historical WR = 0%.
               Bot still operates but with maximum gate tightness.

Active session hours (matches macro_engine + sniper definitions):
  08–09 UTC  — London open
  13–15 UTC  — NYSE open + US macro (CPI, NFP, claims)
  22–24 UTC  — Asia open
  00 UTC     — Asia continuation

Adaptive parameters
───────────────────
Parameters below are ASPIRATIONAL — do not use until each regime has
≥ 30 completed trades with known outcomes. Until then, sniper uses
its standard parameters and regime is data-collection only.

Once data exists, replace the None values with empirical targets:

  REGIME_PARAMS = {
      "ACTIVE_HOT":  {"min_lag": 0.15, "min_delta_15m": 0.08, "min_edge": 0.04},
      "ACTIVE_WARM": {"min_lag": 0.25, "min_delta_15m": 0.10, "min_edge": 0.05},
      "ACTIVE_COLD": {"min_lag": 0.35, "min_delta_15m": 0.12, "min_edge": 0.06},
      "QUIET_FLOW":  {"min_lag": 0.35, "min_delta_15m": 0.12, "min_edge": 0.06},
      "QUIET_DEAD":  {"min_lag": 0.45, "min_delta_15m": 0.15, "min_edge": 0.08},
  }

Usage
─────
  from analytics.regime import classify_regime, REGIME_DESCRIPTIONS

  regime = classify_regime(hour_utc=14, vpin=0.62)
  # → "ACTIVE_HOT"

  python3 analytics/regime.py   # show regime performance from trade history
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

# ── Regime definitions ────────────────────────────────────────────────────────

_ACTIVE_HOURS = {8, 9, 13, 14, 15, 22, 23, 0}

REGIME_DESCRIPTIONS = {
    "ACTIVE_HOT":  "Active session + VPIN ≥ 0.55 — peak edge window",
    "ACTIVE_WARM": "Active session + VPIN 0.35–0.55 — moderate edge",
    "ACTIVE_COLD": "Active session + VPIN < 0.35 — time is right, flow isn't",
    "QUIET_FLOW":  "Off-peak + VPIN ≥ 0.45 — unusual flow, watch carefully",
    "QUIET_DEAD":  "Off-peak + VPIN < 0.45 — thin books, no informed flow",
}

# Thresholds
_VPIN_HOT  = 0.55
_VPIN_FLOW = 0.45
_VPIN_WARM = 0.35


def classify_regime(hour_utc: int, vpin: float) -> str:
    """
    Classify the current market regime from hour and VPIN.

    Args:
        hour_utc: Current UTC hour (0–23)
        vpin: Current VPIN score (0.0 = no flow, 1.0 = fully informed)

    Returns:
        One of: ACTIVE_HOT, ACTIVE_WARM, ACTIVE_COLD, QUIET_FLOW, QUIET_DEAD
    """
    is_active = hour_utc in _ACTIVE_HOURS

    if is_active:
        if vpin >= _VPIN_HOT:
            return "ACTIVE_HOT"
        elif vpin >= _VPIN_WARM:
            return "ACTIVE_WARM"
        else:
            return "ACTIVE_COLD"
    else:
        if vpin >= _VPIN_FLOW:
            return "QUIET_FLOW"
        else:
            return "QUIET_DEAD"


def regime_from_record(record: dict) -> str:
    """
    Derive regime from a trade or shadow block JSONL record.
    Falls back gracefully if fields are missing.
    """
    # Prefer stored regime label (new records)
    if record.get("regime"):
        return record["regime"]

    # Re-derive from stored fields (old records)
    ts = record.get("entry_ts") or record.get("ts") or 0
    hour = (
        record.get("hour_utc")
        or (datetime.fromtimestamp(ts, tz=timezone.utc).hour if ts else 0)
    )
    vpin = record.get("vpin_at_entry") or record.get("vpin") or 0.0
    return classify_regime(int(hour), float(vpin))


# ── Analysis ─────────────────────────────────────────────────────────────────

def _analyse_file(path: str, label: str) -> dict:
    """Load a JSONL file and return per-regime stats."""
    if not os.path.exists(path):
        return {}

    rows = [json.loads(l) for l in open(path) if l.strip()]
    if not rows:
        return {}

    stats: dict = defaultdict(lambda: {
        "n": 0, "wins": 0, "losses": 0, "pnls": [], "pending": 0
    })

    for r in rows:
        regime = regime_from_record(r)
        s = stats[regime]
        s["n"] += 1

        win = r.get("would_win_20") if "would_win_20" in r else r.get("would_win_20pct")
        pnl = r.get("pnl") if "pnl" in r else r.get("pnl_if_entered")

        if win is True:
            s["wins"] += 1
            if pnl is not None:
                s["pnls"].append(pnl)
        elif win is False:
            s["losses"] += 1
            if pnl is not None:
                s["pnls"].append(pnl)
        else:
            s["pending"] += 1

    return dict(stats)


def _print_regime_table(stats: dict, title: str) -> None:
    if not stats:
        print(f"  {title}: no data")
        return

    print(f"\n  {title}")
    order = ["ACTIVE_HOT", "ACTIVE_WARM", "ACTIVE_COLD", "QUIET_FLOW", "QUIET_DEAD"]
    all_regimes = order + [r for r in stats if r not in order]

    for regime in all_regimes:
        if regime not in stats:
            continue
        s = stats[regime]
        rated = s["wins"] + s["losses"]
        if rated == 0:
            wr_str = "  n/a  "
        else:
            wr = s["wins"] / rated
            wr_str = f"{wr:>5.0%} "
        avg_pnl = (sum(s["pnls"]) / len(s["pnls"])) if s["pnls"] else None
        pnl_str = f"{avg_pnl:+.1%}" if avg_pnl is not None else "  n/a"
        bar = "█" * int((s["wins"] / rated * 20) if rated else 0)
        desc = REGIME_DESCRIPTIONS.get(regime, "")
        print(
            f"    {regime:<14} WR={wr_str} avg={pnl_str}  "
            f"n={rated:>3} (+{s['pending']} pending)  {bar}"
        )
        print(f"                  └─ {desc}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    trades_path  = os.path.join("logs", "trades.jsonl")
    shadow_path  = os.path.join("logs", "shadow_blocks.jsonl")

    print(f"\n{'='*65}")
    print(f"  REGIME PERFORMANCE ANALYSIS")
    print(f"{'='*65}")

    trade_stats  = _analyse_file(trades_path, "trades.jsonl")
    shadow_stats = _analyse_file(shadow_path, "shadow_blocks.jsonl")

    _print_regime_table(trade_stats,  "Live trades (actual outcomes)")
    _print_regime_table(shadow_stats, "Shadow blocks (counterfactual outcomes)")

    print(f"\n  Regime legend:")
    for label, desc in REGIME_DESCRIPTIONS.items():
        active = "active hours" if label.startswith("ACTIVE") else "off-peak"
        print(f"    {label:<14} — {desc}")

    print(f"\n  Note: adaptive parameter tuning requires ≥30 rated trades per regime.")
    print(f"  Until then, regime is data-collection only.\n")
