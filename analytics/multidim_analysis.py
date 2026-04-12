#!/usr/bin/env python3
"""
multidim_analysis.py — Lag × VPIN × Delta × Elapsed cross-dimensional analysis.

Run from Klaus root:
    python3 analytics/multidim_analysis.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

TRADE_LOG = Path("logs/trades.jsonl")

trades = []
if not TRADE_LOG.exists():
    print(f"ERROR: {TRADE_LOG} not found. Run from Klaus root directory.")
    sys.exit(1)

with open(TRADE_LOG) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            trades.append(json.loads(line))
        except json.JSONDecodeError:
            continue

live = [t for t in trades if t.get("is_live")
        and t.get("entry_price", 0) > 0
        and t.get("sniper_lag_remaining") is not None
        and t.get("sniper_delta_pct") is not None]

print(f"Loaded {len(trades)} total, {len(live)} live with lag+delta\n")

if not live:
    print("No usable live trades.")
    sys.exit(0)


def wr_str(group):
    if not group:
        return "   —   "
    w = sum(1 for p in group if p > 0)
    wr = w / len(group)
    n = len(group)
    flag = "!!" if wr < 0.40 else ("**" if wr >= 0.60 else "  ")
    return f"{wr*100:4.0f}%(n={n:3d}){flag}"


def net_str(group):
    if not group:
        return "      —"
    return f"${sum(group):+7.2f}"


# ── Helper bins ───────────────────────────────────────────────────────────────

def lag_bin(lag):
    if lag < 0.60:  return "lag<0.60"
    if lag < 0.65:  return "lag0.60-0.65"
    if lag < 0.70:  return "lag0.65-0.70"
    if lag < 0.75:  return "lag0.70-0.75"
    if lag < 0.80:  return "lag0.75-0.80"
    return                  "lag0.80+"   # hard-rejected, shouldn't appear

LAG_BINS = ["lag<0.60", "lag0.60-0.65", "lag0.65-0.70", "lag0.70-0.75", "lag0.75-0.80", "lag0.80+"]

def delta_bin(d):
    ad = abs(d)
    if ad < 0.10:  return "d<0.10"
    if ad < 0.13:  return "d0.10-0.13"
    if ad < 0.18:  return "d0.13-0.18"
    if ad < 0.25:  return "d0.18-0.25"
    return                 "d0.25+"

DELTA_BINS = ["d<0.10", "d0.10-0.13", "d0.13-0.18", "d0.18-0.25", "d0.25+"]

def vpin_bin(v):
    if v is None:  return "vpin?"
    if v < 0.30:   return "vpin<0.30"
    if v < 0.40:   return "vpin0.30-0.40"
    if v < 0.55:   return "vpin0.40-0.55"
    if v < 0.65:   return "vpin0.55-0.65"
    return                 "vpin0.65+"

VPIN_BINS = ["vpin<0.30", "vpin0.30-0.40", "vpin0.40-0.55", "vpin0.55-0.65", "vpin0.65+"]

def elap_bin(e):
    if e is None:  return "elap?"
    if e < 0.20:   return "elap<20%"
    if e < 0.40:   return "elap20-40%"
    if e < 0.60:   return "elap40-60%"
    if e < 0.80:   return "elap60-80%"
    return                 "elap80%+"

ELAP_BINS = ["elap<20%", "elap20-40%", "elap40-60%", "elap60-80%", "elap80%+"]


# Pre-classify every trade
for t in live:
    t["_lb"] = lag_bin(t["sniper_lag_remaining"])
    t["_db"] = delta_bin(t["sniper_delta_pct"])
    t["_vb"] = vpin_bin(t.get("sniper_vpin"))
    t["_eb"] = elap_bin(t.get("sniper_elapsed_pct"))
    t["_pnl"] = t.get("net_pnl", 0)


# ── Section 1: ELAPSED breakdown ──────────────────────────────────────────────
print("=" * 60)
print("SECTION 1: ELAPSED (% of window used at entry)")
print("=" * 60)
ebuckets = defaultdict(list)
for t in live:
    ebuckets[t["_eb"]].append(t["_pnl"])

print(f"{'Elapsed':<14} {'WR':>14} {'Net PnL':>9}")
print("-" * 40)
for b in ELAP_BINS:
    g = ebuckets.get(b, [])
    print(f"{b:<14} {wr_str(g):>14} {net_str(g):>9}")
print()


# ── Section 2: LAG × DELTA cross-tab ─────────────────────────────────────────
print("=" * 60)
print("SECTION 2: LAG × DELTA  (WR%)")
print("=" * 60)

ld = defaultdict(list)
for t in live:
    ld[(t["_lb"], t["_db"])].append(t["_pnl"])

W = 16
header = f"{'':14}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (14 + W * len(DELTA_BINS)))
for lb in LAG_BINS:
    row = f"{lb:<14}"
    for db in DELTA_BINS:
        row += f"{wr_str(ld.get((lb, db), [])):>{W}}"
    print(row)
print()

print("Net PnL by LAG × DELTA:")
for lb in LAG_BINS:
    row = f"{lb:<14}"
    for db in DELTA_BINS:
        row += f"{net_str(ld.get((lb, db), [])):>{W}}"
    print(row)
print()


# ── Section 3: ELAPSED × DELTA cross-tab ─────────────────────────────────────
print("=" * 60)
print("SECTION 3: ELAPSED × DELTA  (WR%)")
print("=" * 60)

ed = defaultdict(list)
for t in live:
    ed[(t["_eb"], t["_db"])].append(t["_pnl"])

header = f"{'':14}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (14 + W * len(DELTA_BINS)))
for eb in ELAP_BINS:
    row = f"{eb:<14}"
    for db in DELTA_BINS:
        row += f"{wr_str(ed.get((eb, db), [])):>{W}}"
    print(row)
print()


# ── Section 4: LAG × ELAPSED cross-tab ───────────────────────────────────────
print("=" * 60)
print("SECTION 4: LAG × ELAPSED  (WR%)")
print("=" * 60)

le = defaultdict(list)
for t in live:
    le[(t["_lb"], t["_eb"])].append(t["_pnl"])

header = f"{'':14}" + "".join(f"{e:>{W}}" for e in ELAP_BINS)
print(header)
print("-" * (14 + W * len(ELAP_BINS)))
for lb in LAG_BINS:
    row = f"{lb:<14}"
    for eb in ELAP_BINS:
        row += f"{wr_str(le.get((lb, eb), [])):>{W}}"
    print(row)
print()


# ── Section 5: VPIN × DELTA cross-tab ────────────────────────────────────────
print("=" * 60)
print("SECTION 5: VPIN × DELTA  (WR%)")
print("=" * 60)

vd = defaultdict(list)
for t in live:
    vd[(t["_vb"], t["_db"])].append(t["_pnl"])

header = f"{'':16}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (16 + W * len(DELTA_BINS)))
for vb in VPIN_BINS:
    row = f"{vb:<16}"
    for db in DELTA_BINS:
        row += f"{wr_str(vd.get((vb, db), [])):>{W}}"
    print(row)
print()


# ── Section 6: TOP COMBINATIONS ──────────────────────────────────────────────
print("=" * 60)
print("SECTION 6: TOP COMBINATIONS (n>=5, WR>=55%, net>0)")
print("=" * 60)

combos = defaultdict(list)
for t in live:
    key = (t["_lb"], t["_db"], t["_vb"], t["_eb"])
    combos[key].append(t["_pnl"])

results = []
for (lb, db, vb, eb), pnls in combos.items():
    n = len(pnls)
    if n < 5:
        continue
    w = sum(1 for p in pnls if p > 0)
    wr = w / n
    net = sum(pnls)
    if wr >= 0.55 and net > 0:
        results.append((wr, net, n, lb, db, vb, eb))

if results:
    results.sort(reverse=True)
    print(f"{'Lag':<14} {'Delta':<13} {'VPIN':<16} {'Elapsed':<12} {'WR':>8} {'n':>4} {'Net':>8}")
    print("-" * 80)
    for wr, net, n, lb, db, vb, eb in results:
        print(f"{lb:<14} {db:<13} {vb:<16} {eb:<12} {wr*100:>6.0f}% {n:>4}  ${net:>+7.2f}")
else:
    print("No combinations with n>=5, WR>=55%, net>0 found.")

print()
print("KILL ZONES (n>=5, WR<40%):")
kills = []
for (lb, db, vb, eb), pnls in combos.items():
    n = len(pnls)
    if n < 5:
        continue
    w = sum(1 for p in pnls if p > 0)
    wr = w / n
    net = sum(pnls)
    if wr < 0.40:
        kills.append((wr, net, n, lb, db, vb, eb))

if kills:
    kills.sort()
    print(f"{'Lag':<14} {'Delta':<13} {'VPIN':<16} {'Elapsed':<12} {'WR':>8} {'n':>4} {'Net':>8}")
    print("-" * 80)
    for wr, net, n, lb, db, vb, eb in kills:
        print(f"{lb:<14} {db:<13} {vb:<16} {eb:<12} {wr*100:>6.0f}% {n:>4}  ${net:>+7.2f}")
else:
    print("No kill zones with n>=5, WR<40% found.")

print()
print("!! = WR < 40%   ** = WR >= 60%")
print("Done.")
