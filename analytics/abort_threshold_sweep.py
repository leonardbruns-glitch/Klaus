#!/usr/bin/env python3
"""BOND early-abort threshold sweep.

Measures, on the historical BOND trade log, how different T+30s / T+60s
abort rules would have affected the outcome of every trade. Produces:

  1. Winner vs loser histograms of entry_snap_30s_pct and entry_snap_60s_pct
  2. Confusion matrix across threshold candidates for three rule families:
       A) snap_30s ≤ X                         (static T+30s)
       B) snap_30s ≤ X AND snap_60s ≤ snap_30s (T+30s with continuation)
       C) snap_60s ≤ X                         (static T+60s)
  3. Estimated net $ impact per rule (abort truncates pnl to stake * snap/100)

Run:  python3 /root/Klaus/analytics/abort_threshold_sweep.py
Optional: --since "YYYY-MM-DD HH:MM"  (UTC)
"""
import json, os, sys, datetime
from collections import defaultdict

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_ROOT, "logs", "trades.jsonl")

# ── --since filter ────────────────────────────────────────────────────────────
_since_ts = 0.0
_since_arg = None
for i, a in enumerate(sys.argv[1:]):
    if a == "--since" and i + 1 < len(sys.argv) - 1:
        _since_arg = sys.argv[i + 2]
        try:
            _since_ts = datetime.datetime.strptime(
                _since_arg, "%Y-%m-%d %H:%M"
            ).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            print(f"[warn] bad --since '{_since_arg}', ignoring", file=sys.stderr)
            _since_ts = 0.0

with open(TRADES_PATH) as f:
    trades = [json.loads(l) for l in f if l.strip()]
if _since_ts > 0:
    trades = [t for t in trades
              if (t.get("ts_open", 0) or 0) >= _since_ts
              or (t.get("ts_close", 0) or 0) >= _since_ts]

# Only BOND trades with populated snap fields
def _has_snap(t):
    s30 = t.get("entry_snap_30s_pct")
    return s30 is not None and s30 != 0  # filter out structurally-zero legacy rows

bond = [t for t in trades
        if (t.get("signal_source") == "BOND" or t.get("is_bond"))
        and _has_snap(t)]
if not bond:
    print("no BOND trades with entry_snap_30s_pct populated — nothing to analyze")
    sys.exit(0)

def _fmt_pnl(v):
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"

def _pct(vals, q):
    s = sorted(vals); n = len(s)
    return s[max(0, min(n - 1, int(q * n / 100)))] if n else 0.0

wins = [t for t in bond if (t.get("net_pnl", 0) or 0) > 0]
loss = [t for t in bond if (t.get("net_pnl", 0) or 0) <= 0]

print("=" * 78)
print(f"BOND ABORT SWEEP  n={len(bond)}  wins={len(wins)}  loss={len(loss)}"
      f"  since={_since_arg or 'all'}")
print("=" * 78)

# ── 1. Distribution of snap_30s / snap_60s ───────────────────────────────────
def _hist(label, vals, edges):
    buckets = [0] * (len(edges) + 1)
    for v in vals:
        placed = False
        for i, e in enumerate(edges):
            if v <= e:
                buckets[i] += 1
                placed = True
                break
        if not placed:
            buckets[-1] += 1
    lbl = []
    prev = "-inf"
    for e in edges:
        lbl.append(f"({prev},{e}]")
        prev = str(e)
    lbl.append(f"({prev},+inf)")
    print(f"  {label}")
    for l, c in zip(lbl, buckets):
        bar = "#" * c
        print(f"    {l:>14}  n={c:>3}  {bar}")

EDGES_30 = [-20, -15, -10, -7.5, -5, -2.5, 0, 2.5, 5, 10]
print(f"\n── HISTOGRAM: entry_snap_30s_pct ───────────────────────────────────────")
_hist("WINNERS", [t["entry_snap_30s_pct"] for t in wins], EDGES_30)
_hist("LOSERS ", [t["entry_snap_30s_pct"] for t in loss], EDGES_30)

print(f"\n── HISTOGRAM: entry_snap_60s_pct ───────────────────────────────────────")
w60 = [t["entry_snap_60s_pct"] for t in wins if t.get("entry_snap_60s_pct") not in (None, 0)]
l60 = [t["entry_snap_60s_pct"] for t in loss if t.get("entry_snap_60s_pct") not in (None, 0)]
if w60 and l60:
    _hist("WINNERS", w60, EDGES_30)
    _hist("LOSERS ", l60, EDGES_30)

# Summary quartiles
print(f"\n── QUARTILES ───────────────────────────────────────────────────────────")
for lab, key in (("snap_30s", "entry_snap_30s_pct"),
                 ("snap_60s", "entry_snap_60s_pct")):
    wv = [t.get(key, 0) or 0 for t in wins if t.get(key) not in (None, 0)]
    lv = [t.get(key, 0) or 0 for t in loss if t.get(key) not in (None, 0)]
    if not wv or not lv:
        continue
    print(f"  {lab}  W[p25/p50/p75]={_pct(wv,25):+.1f}/{_pct(wv,50):+.1f}/{_pct(wv,75):+.1f}  "
          f"L[p25/p50/p75]={_pct(lv,25):+.1f}/{_pct(lv,50):+.1f}/{_pct(lv,75):+.1f}")

# ── 2. Confusion matrix across rules ─────────────────────────────────────────
#
# Modelling the abort:
#   original_pnl = t.net_pnl
#   if the rule fires at snap time T, we exit at approximately snap%:
#     aborted_share_pnl ≈ stake * (snap_pct/100)
#     aborted_net_pnl   ≈ aborted_share_pnl - (entry_fee + exit_fee_estimate)
#   We approximate exit_fee_estimate as the trade's logged fee_paid minus
#   entry_fee if available; otherwise use fee_paid/2 as symmetric approximation.
#
# Delta per trade = aborted_net_pnl - original_pnl
#   winners with positive delta → abort helped (rare — aborted winner loses profit)
#   winners with negative delta → abort hurt (cut a winner short)
#   losers  with positive delta → abort helped (truncated a loss)
#   losers  with negative delta → abort hurt (aborted at snap lower than final exit)

def _abort_pnl(t, snap_pct):
    stake = float(t.get("stake", 0) or 0)
    fee   = float(t.get("fee_paid", 0) or 0)
    # Symmetric fee approximation: assume round-trip fee already paid ≈ fee_paid
    return stake * (snap_pct / 100.0) - fee

def _rule_A(t, thr):  # snap_30s ≤ thr
    s30 = t.get("entry_snap_30s_pct")
    return s30 is not None and s30 <= thr

def _rule_B(t, thr):  # snap_30s ≤ thr AND snap_60s ≤ snap_30s (still falling/flat)
    s30 = t.get("entry_snap_30s_pct")
    s60 = t.get("entry_snap_60s_pct")
    if s30 is None or s60 is None:
        return False
    return s30 <= thr and s60 <= s30

def _rule_C(t, thr):  # snap_60s ≤ thr
    s60 = t.get("entry_snap_60s_pct")
    return s60 is not None and s60 <= thr

def _eval(rule_fn, thr, snap_key):
    fired_w = fired_l = 0
    delta_w = delta_l = 0.0
    saved_l = 0
    for t in bond:
        if not rule_fn(t, thr):
            continue
        snap = t.get(snap_key) or 0
        orig = t.get("net_pnl", 0) or 0
        new  = _abort_pnl(t, snap)
        delta = new - orig
        if orig > 0:
            fired_w += 1
            delta_w += delta
        else:
            fired_l += 1
            delta_l += delta
            if new > orig:
                saved_l += 1
    tot_delta = delta_w + delta_l
    return {
        "fired_w": fired_w, "fired_l": fired_l,
        "delta_w": delta_w, "delta_l": delta_l,
        "total_delta": tot_delta,
        "saved_l": saved_l,
        "winners_cut_pct": 100 * fired_w / max(1, len(wins)),
        "losers_caught_pct": 100 * fired_l / max(1, len(loss)),
    }

THRESHOLDS = [-20, -15, -10, -7.5, -5, -2.5, 0]

def _table(title, rule_fn, snap_key):
    print(f"\n── {title} " + "─" * max(0, 66 - len(title)))
    print(f"  {'thr':>6}  {'fired_W':>7} ({'%W':>5})  {'fired_L':>7} ({'%L':>5})  "
          f"{'ΔW':>8}  {'ΔL':>8}  {'net Δ':>8}  {'saved_L':>7}")
    best = None
    for thr in THRESHOLDS:
        r = _eval(rule_fn, thr, snap_key)
        tag = ""
        if best is None or r["total_delta"] > best["total_delta"]:
            best = dict(r, thr=thr)
        print(f"  {thr:>+6.1f}  {r['fired_w']:>7} ({r['winners_cut_pct']:>4.0f}%)  "
              f"{r['fired_l']:>7} ({r['losers_caught_pct']:>4.0f}%)  "
              f"{_fmt_pnl(r['delta_w']):>8}  {_fmt_pnl(r['delta_l']):>8}  "
              f"{_fmt_pnl(r['total_delta']):>8}  {r['saved_l']:>7}")
    return best

bA = _table("RULE A: snap_30s ≤ thr  (static T+30s abort)", _rule_A, "entry_snap_30s_pct")
bB = _table("RULE B: snap_30s ≤ thr AND snap_60s ≤ snap_30s  (T+30s with continuation at T+60s)",
            _rule_B, "entry_snap_30s_pct")
bC = _table("RULE C: snap_60s ≤ thr  (static T+60s abort)", _rule_C, "entry_snap_60s_pct")

# ── 3. Best-of summary ───────────────────────────────────────────────────────
print(f"\n── BEST BY NET Δ ───────────────────────────────────────────────────────")
for name, b in (("A (T+30s static)", bA),
                ("B (T+30s + 60s continuation)", bB),
                ("C (T+60s static)", bC)):
    if b is None:
        continue
    print(f"  {name:<32}  thr={b['thr']:+.1f}%  netΔ={_fmt_pnl(b['total_delta'])}  "
          f"winners_cut={b['fired_w']} ({b['winners_cut_pct']:.0f}%)  "
          f"losers_caught={b['fired_l']} ({b['losers_caught_pct']:.0f}%)")

print("\nNotes:")
print("  • fee approximation: abort_pnl = stake * snap% - fee_paid (uses full round-trip fee)")
print("    → real abort would pay only exit fee; actual Δ is slightly better than reported")
print("  • Rule B requires snap_60s to be populated; rule fires at T+60s in practice")
print("  • If no rule shows net positive Δ, threshold is wrong or signal is too noisy")
