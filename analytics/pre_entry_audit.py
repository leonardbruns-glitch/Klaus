"""
Pre-entry feature audit: do pre-causal features separate winners from losers?

This script restricts analysis to features that are strictly time-anchored
BEFORE entry (t ≤ entry_ts). Post-entry diagnostics (entry_snap_30s_pct,
mae_bounce, max_fav, max_adverse) are EXCLUDED — those are outcomes, not signals.

Pre-entry features audited:
  bond_smooth_delta_60s   — token price change [T-60s, T] (backward window)
  bond_delta_accel_30s    — acceleration over last 30s (backward)
  bond_edge_drift_30s     — edge slope over last 30s (backward)
  bond_stab_vel_flat      — velocity flat flag at T=0
  bond_stab_edge_weak     — edge weak flag at T=0
  bond_accel_sustained    — sustained acceleration flag (backward)
  pre_score               — composite pre-entry score (all components backward)
  pre_score_daccel / _edge / _vel / _stab / _accel / _class  — components

Run from VPS root:
  cd /root/Klaus && python3 analytics/pre_entry_audit.py
"""
from __future__ import annotations
import json
import os
import statistics
from typing import Any

TRADES_PATH = os.path.join("logs", "trades.jsonl")

# ── Helpers ───────────────────────────────────────────────────────────────────

def g(t: dict, k: str, default=0.0):
    v = t.get(k)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def gb(t: dict, k: str) -> bool:
    v = t.get(k)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return False

def _pcts(vals: list[float]) -> str:
    if not vals:
        return "—"
    vals_s = sorted(vals)
    n = len(vals_s)
    p25 = vals_s[n // 4]
    p50 = vals_s[n // 2]
    p75 = vals_s[3 * n // 4]
    return f"p25={p25:+.3f}  p50={p50:+.3f}  p75={p75:+.3f}"

def _row(label: str, wv: list[float], lv: list[float], nw: int, nl: int, fmt: str = "+.3f") -> None:
    def _s(vals: list[float]) -> str:
        if not vals:
            return " " * 38 + "—"
        vals_s = sorted(vals)
        n = len(vals_s)
        p25 = vals_s[max(0, n // 4)]
        p50 = vals_s[n // 2]
        p75 = vals_s[min(n - 1, 3 * n // 4)]
        mn   = statistics.mean(vals)
        return (f"mean={mn:{fmt}}  p25={p25:{fmt}}  p50={p50:{fmt}}  p75={p75:{fmt}}"
                f"  n={len(vals)}/{n if n else '?'}")
    print(f"  {label:<32}  W: {_s(wv)}")
    print(f"  {' ' * 32}  L: {_s(lv)}")

def _binary_row(label: str, wv: list[float], lv: list[float]) -> None:
    """For bool features: show proportion True in winners vs losers."""
    w_true = sum(1 for v in wv if v)
    l_true = sum(1 for v in lv if v)
    w_pct = w_true / len(wv) * 100 if wv else 0
    l_pct = l_true / len(lv) * 100 if lv else 0
    signal = ""
    if abs(w_pct - l_pct) >= 10:
        signal = f"  ← Δ={w_pct - l_pct:+.0f}pp"
    print(f"  {label:<32}  W: {w_true}/{len(wv)} ({w_pct:.0f}%)  "
          f"L: {l_true}/{len(lv)} ({l_pct:.0f}%){signal}")

# ── Load ──────────────────────────────────────────────────────────────────────

with open(TRADES_PATH) as f:
    all_trades = [json.loads(l) for l in f if l.strip()]

# BOND trades with pre_score populated (post-schema-v1 only)
trades = [
    t for t in all_trades
    if t.get("signal_source") == "BOND"
    and t.get("pre_score_schema_hash") == "6c249c44"
    and t.get("pre_score_validity", "").startswith("PASS")
    and t.get("dry_run") is not True
]

if not trades:
    # Fallback: BOND trades without pre_score (older data)
    trades = [
        t for t in all_trades
        if t.get("signal_source") == "BOND"
        and t.get("dry_run") is not True
    ]
    print(f"NOTE: No pre_score schema=6c249c44 trades found. Falling back to all BOND trades (n={len(trades)}).")
    print("      Pre_score component rows will show zeros — only raw feature rows are valid.\n")

wins = [t for t in trades if g(t, "net_pnl") > 0]
loss = [t for t in trades if g(t, "net_pnl") <= 0]
nw, nl = len(wins), len(loss)
wr = nw / len(trades) * 100 if trades else 0

print("=" * 78)
print(f"PRE-ENTRY FEATURE AUDIT — strictly t ≤ entry_ts features only")
print(f"n={len(trades)}  wins={nw}  loss={nl}  WR={wr:.0f}%")
print("EXCLUDED: entry_snap_30s/60s, mae_bounce, max_fav, max_adverse (all post-entry)")
print("=" * 78)

# ── 1. Continuous pre-entry features ─────────────────────────────────────────
print("\n── CONTINUOUS FEATURES ─────────────────────────────────────────────────────")

_row("bond_smooth_delta_60s",
     [g(t, "bond_smooth_delta_60s") for t in wins],
     [g(t, "bond_smooth_delta_60s") for t in loss],
     nw, nl)

_row("bond_delta_accel_30s",
     [g(t, "bond_delta_accel_30s") for t in wins],
     [g(t, "bond_delta_accel_30s") for t in loss],
     nw, nl)

_row("bond_edge_drift_30s",
     [g(t, "bond_edge_drift_30s") for t in wins],
     [g(t, "bond_edge_drift_30s") for t in loss],
     nw, nl)

_row("pre_score (composite)",
     [g(t, "pre_score") for t in wins],
     [g(t, "pre_score") for t in loss],
     nw, nl)

_row("pre_score_daccel",
     [g(t, "pre_score_daccel") for t in wins],
     [g(t, "pre_score_daccel") for t in loss],
     nw, nl)

_row("pre_score_edge",
     [g(t, "pre_score_edge") for t in wins],
     [g(t, "pre_score_edge") for t in loss],
     nw, nl)

_row("pre_score_vel",
     [g(t, "pre_score_vel") for t in wins],
     [g(t, "pre_score_vel") for t in loss],
     nw, nl)

_row("pre_score_stab",
     [g(t, "pre_score_stab") for t in wins],
     [g(t, "pre_score_stab") for t in loss],
     nw, nl)

_row("pre_score_accel",
     [g(t, "pre_score_accel") for t in wins],
     [g(t, "pre_score_accel") for t in loss],
     nw, nl)

_row("pre_score_class",
     [g(t, "pre_score_class") for t in wins],
     [g(t, "pre_score_class") for t in loss],
     nw, nl)

# ── 2. Binary pre-entry flags ─────────────────────────────────────────────────
print("\n── BINARY FLAGS (% trades where flag=True) ──────────────────────────────────")

_binary_row("bond_stab_vel_flat",
            [gb(t, "bond_stab_vel_flat") for t in wins],
            [gb(t, "bond_stab_vel_flat") for t in loss])

_binary_row("bond_stab_edge_weak",
            [gb(t, "bond_stab_edge_weak") for t in wins],
            [gb(t, "bond_stab_edge_weak") for t in loss])

_binary_row("bond_accel_sustained",
            [gb(t, "bond_accel_sustained") for t in wins],
            [gb(t, "bond_accel_sustained") for t in loss])

_binary_row("bond_stab_xp_bad",
            [gb(t, "bond_stab_xp_bad") for t in wins],
            [gb(t, "bond_stab_xp_bad") for t in loss])

_binary_row("bond_stab_slip_bad",
            [gb(t, "bond_stab_slip_bad") for t in wins],
            [gb(t, "bond_stab_slip_bad") for t in loss])

# ── 3. Pre_score bucket breakdown ────────────────────────────────────────────
print("\n── PRE_SCORE BUCKETS vs OUTCOME ─────────────────────────────────────────────")
buckets = [(-99, 0.0), (0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 99)]
bucket_labels = ["< 0.0", "0.0–1.0", "1.0–2.0", "2.0–3.0", "> 3.0"]
for (lo, hi), lbl in zip(buckets, bucket_labels):
    sub = [t for t in trades if lo <= g(t, "pre_score") < hi]
    if not sub:
        continue
    sub_w = sum(1 for t in sub if g(t, "net_pnl") > 0)
    sub_wr = sub_w / len(sub) * 100
    avg_pnl = statistics.mean(g(t, "net_pnl") for t in sub)
    sum_pnl = sum(g(t, "net_pnl") for t in sub)
    print(f"  {lbl:<10}  n={len(sub):>3}  WR={sub_wr:>5.0f}%  avg={avg_pnl:+.2f}  sum={sum_pnl:+.2f}")

# ── 4. Conditional on bond_smooth_delta_60s ──────────────────────────────────
print("\n── bond_smooth_delta_60s GATE SIMULATION ────────────────────────────────────")
print("  (does pre-entry price direction predict outcome?)\n")
thresholds = [-0.03, -0.02, -0.01, 0.0, 0.01]
for thr in thresholds:
    blocked = [t for t in trades if g(t, "bond_smooth_delta_60s") < thr]
    passed  = [t for t in trades if g(t, "bond_smooth_delta_60s") >= thr]
    if not blocked or not passed:
        continue
    b_wr = sum(1 for t in blocked if g(t, "net_pnl") > 0) / len(blocked) * 100
    p_wr = sum(1 for t in passed) and sum(1 for t in passed if g(t, "net_pnl") > 0) / len(passed) * 100
    b_sum = sum(g(t, "net_pnl") for t in blocked)
    p_sum = sum(g(t, "net_pnl") for t in passed)
    print(f"  smooth_delta_60s < {thr:+.2f}:  "
          f"blocked n={len(blocked):>3} WR={b_wr:>4.0f}% sum={b_sum:+.2f}  |  "
          f"passed  n={len(passed):>3} WR={p_wr:>4.0f}% sum={p_sum:+.2f}")

# ── 5. Conditional on vel_flat ───────────────────────────────────────────────
print("\n── vel_flat GATE SIMULATION ─────────────────────────────────────────────────")
vel_flat_yes = [t for t in trades if gb(t, "bond_stab_vel_flat")]
vel_flat_no  = [t for t in trades if not gb(t, "bond_stab_vel_flat")]
def _mini(sub):
    if not sub:
        return "n=0"
    wr_ = sum(1 for t in sub if g(t, "net_pnl") > 0) / len(sub) * 100
    sm_ = sum(g(t, "net_pnl") for t in sub)
    return f"n={len(sub):>3}  WR={wr_:>4.0f}%  sum={sm_:+.2f}"
print(f"  vel_flat=True   {_mini(vel_flat_yes)}")
print(f"  vel_flat=False  {_mini(vel_flat_no)}")

# ── 6. Interaction: vel_flat + smooth_delta ──────────────────────────────────
print("\n── INTERACTION: vel_flat=True AND smooth_delta_60s < threshold ──────────────")
for thr in [-0.02, -0.01, 0.0]:
    combo = [t for t in trades
             if gb(t, "bond_stab_vel_flat") and g(t, "bond_smooth_delta_60s") < thr]
    rest  = [t for t in trades
             if not (gb(t, "bond_stab_vel_flat") and g(t, "bond_smooth_delta_60s") < thr)]
    if not combo:
        continue
    c_wr = sum(1 for t in combo if g(t, "net_pnl") > 0) / len(combo) * 100
    r_wr = sum(1 for t in rest if g(t, "net_pnl") > 0) / len(rest) * 100 if rest else 0
    c_sum = sum(g(t, "net_pnl") for t in combo)
    r_sum = sum(g(t, "net_pnl") for t in rest)
    print(f"  vel_flat & delta<{thr:+.2f}:  "
          f"match n={len(combo):>3}  WR={c_wr:>4.0f}%  sum={c_sum:+.2f}  |  "
          f"rest  n={len(rest):>3}  WR={r_wr:>4.0f}%  sum={r_sum:+.2f}")

# ── 7. Verdict ───────────────────────────────────────────────────────────────
print("\n── VERDICT ──────────────────────────────────────────────────────────────────")
print("  If any feature shows W/L gap ≥ 10pp or gate simulation shows")
print("  clear WR improvement in 'passed' cohort: pre-entry signal EXISTS.")
print("  If all gaps < 10pp: no detectable pre-entry edge at this n.")
print("  Gate implementation is only justified if pre-entry signal exists here.")
print("=" * 78)
