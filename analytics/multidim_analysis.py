#!/usr/bin/env python3
"""
multidim_analysis.py — Multi-dimensional trade analysis.

Run from Klaus root:
    python3 analytics/multidim_analysis.py            # all live trades
    python3 analytics/multidim_analysis.py --last 84  # last N live trades
    python3 analytics/multidim_analysis.py --bond     # BOND trades only
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

TRADE_LOG = Path("logs/trades.jsonl")

last_n = None
bond_only = "--bond" in sys.argv
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--last" and i + 1 < len(sys.argv) - 1:
        try:
            last_n = int(sys.argv[i + 2])
        except ValueError:
            pass

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

live = [
    t for t in trades
    if t.get("is_live")
    and t.get("entry_price", 0) > 0
    and t.get("signal_source") not in ("ORPHAN",)
    and t.get("exit_reason") not in ("ORPHAN_SELL",)
]

if bond_only:
    live = [t for t in live if t.get("signal_source") == "BOND"]

if last_n is not None:
    live = live[-last_n:]
    label = "BOND " if bond_only else ""
    print(f"Loaded {len(trades)} total — analysing last {last_n} {label}live trades (n={len(live)})\n")
else:
    label = "BOND " if bond_only else ""
    print(f"Loaded {len(trades)} total, {len(live)} {label}live trades\n")

if not live:
    print("No usable live trades.")
    sys.exit(0)


# ── Formatters ────────────────────────────────────────────────────────────────

def wr_str(group):
    if not group:
        return "        —       "
    w = sum(1 for p in group if p > 0)
    wr = w / len(group)
    n = len(group)
    flag = "!!" if wr < 0.40 else ("**" if wr >= 0.60 else "  ")
    return f"{wr*100:4.0f}%(n={n:3d}){flag}"


def net_str(group):
    if not group:
        return "         —"
    return f"  ${sum(group):+7.2f}"


def avg_str(vals):
    if not vals:
        return "    —"
    return f"{sum(vals)/len(vals):+.4f}"


# ── Bin definitions ───────────────────────────────────────────────────────────

def lag_bin(lag):
    if lag < 0.60: return "lag<0.60"
    if lag < 0.65: return "lag0.60-0.65"
    if lag < 0.70: return "lag0.65-0.70"
    if lag < 0.75: return "lag0.70-0.75"
    if lag < 0.80: return "lag0.75-0.80"
    return "lag0.80+"

LAG_BINS = ["lag<0.60","lag0.60-0.65","lag0.65-0.70","lag0.70-0.75","lag0.75-0.80","lag0.80+"]


def delta_bin(d):
    ad = abs(d)
    if ad < 0.08:  return "d<0.08"
    if ad < 0.10:  return "d0.08-0.10"
    if ad < 0.13:  return "d0.10-0.13"
    if ad < 0.18:  return "d0.13-0.18"
    if ad < 0.25:  return "d0.18-0.25"
    return "d0.25+"

DELTA_BINS = ["d<0.08","d0.08-0.10","d0.10-0.13","d0.13-0.18","d0.18-0.25","d0.25+"]


def vpin_bin(v):
    if v is None or v == 0.0: return "vpin<0.30"
    if v < 0.30: return "vpin<0.30"
    if v < 0.40: return "vpin0.30-0.40"
    if v < 0.55: return "vpin0.40-0.55"
    if v < 0.65: return "vpin0.55-0.65"
    return "vpin0.65+"

VPIN_BINS = ["vpin<0.30","vpin0.30-0.40","vpin0.40-0.55","vpin0.55-0.65","vpin0.65+"]


def elap_bin(e):
    if e is None or e == 0.0: return "elap?"
    if e < 0.20: return "elap<20%"
    if e < 0.40: return "elap20-40%"
    if e < 0.60: return "elap40-60%"
    if e < 0.80: return "elap60-80%"
    return "elap80%+"

ELAP_BINS = ["elap<20%","elap20-40%","elap40-60%","elap60-80%","elap80%+"]


def edge_bin(e):
    if e <= 0.010: return "edge≤0.010"
    if e <  0.020: return "edge0.010-0.020"
    if e <  0.040: return "edge0.020-0.040"
    if e <  0.080: return "edge0.040-0.080"
    return "edge0.080+"

EDGE_BINS = ["edge≤0.010","edge0.010-0.020","edge0.020-0.040","edge0.040-0.080","edge0.080+"]


def vel_bin(vel_pct, move_age):
    if move_age is None or move_age >= 900:
        return "cold"
    av = abs(vel_pct or 0.0)
    if av < 0.010: return "|vel|<0.010%"
    if av < 0.030: return "|vel|0.010-0.030%"
    return "|vel|>0.030%"

VEL_BINS = ["cold", "|vel|<0.010%", "|vel|0.010-0.030%", "|vel|>0.030%"]


def ep_bin(ep):
    if ep < 0.72: return "ep<0.72"
    if ep < 0.77: return "ep0.72-0.77"
    if ep < 0.82: return "ep0.77-0.82"
    return "ep0.82+"

EP_BINS = ["ep<0.72","ep0.72-0.77","ep0.77-0.82","ep0.82+"]


ASSET_BINS = ["SOL","BTC","ETH","other"]

HRGRP_BINS = [f"hr{h:02d}" for h in range(24)]
def hour_grp(h):
    return f"hr{h:02d}"


# ── Pre-classify ──────────────────────────────────────────────────────────────

for t in live:
    t["_lb"]    = lag_bin(t.get("sniper_lag_remaining") or 0.0)
    t["_db"]    = delta_bin(t.get("sniper_delta_pct") or 0.0)
    t["_vb"]    = vpin_bin(t.get("sniper_vpin"))
    t["_eb"]    = elap_bin(t.get("sniper_elapsed_pct"))
    t["_edgeb"] = edge_bin(t.get("sniper_edge") or 0.0)
    t["_velb"]  = vel_bin(t.get("velocity_5s_pct") or 0.0, t.get("move_age_s"))
    t["_epb"]   = ep_bin(t.get("entry_price") or 0.0)
    asset = t.get("asset", "?")
    t["_asset"] = asset if asset in ("SOL","BTC","ETH") else "other"
    t["_hg"]    = hour_grp(t.get("hour_utc") or 0)
    t["_pnl"]   = t.get("net_pnl", 0)


W = 17

# ── Section 1: ELAPSED ────────────────────────────────────────────────────────
print("=" * 60)
print("SECTION 1: ELAPSED (% of window used at entry)")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_eb"]].append(t["_pnl"])
print(f"{'Elapsed':<16} {'WR':>16} {'Net PnL':>10}")
print("-" * 44)
for b in ELAP_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<16} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 2: DELTA breakdown ────────────────────────────────────────────────
print("=" * 60)
print("SECTION 2: DELTA breakdown")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_db"]].append(t["_pnl"])
print(f"{'Delta':<18} {'WR':>16} {'Net PnL':>10}")
print("-" * 46)
for b in DELTA_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<18} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 3: EDGE breakdown ─────────────────────────────────────────────────
print("=" * 60)
print("SECTION 3: EDGE breakdown")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_edgeb"]].append(t["_pnl"])
print(f"{'Edge':<18} {'WR':>16} {'Net PnL':>10}")
print("-" * 46)
for b in EDGE_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<18} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 4: VELOCITY breakdown ─────────────────────────────────────────────
print("=" * 60)
print("SECTION 4: VELOCITY breakdown")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_velb"]].append(t["_pnl"])
print(f"{'Velocity':<22} {'WR':>16} {'Net PnL':>10}")
print("-" * 50)
for b in VEL_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<22} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 5: ENTRY PRICE breakdown ──────────────────────────────────────────
print("=" * 60)
print("SECTION 5: ENTRY PRICE breakdown")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_epb"]].append(t["_pnl"])
print(f"{'Entry Price':<16} {'WR':>16} {'Net PnL':>10}")
print("-" * 44)
for b in EP_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<16} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 6: ASSET breakdown ────────────────────────────────────────────────
print("=" * 60)
print("SECTION 6: ASSET breakdown")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_asset"]].append(t["_pnl"])
print(f"{'Asset':<8} {'WR':>16} {'Net PnL':>10}")
print("-" * 36)
for b in ASSET_BINS:
    g = bkts.get(b, [])
    if g:
        print(f"{b:<8} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 7: HOUR breakdown (UTC, per hour) ─────────────────────────────────
print("=" * 60)
print("SECTION 7: HOUR breakdown (UTC, per hour)")
print("=" * 60)
bkts = defaultdict(list)
for t in live:
    bkts[t["_hg"]].append(t["_pnl"])
print(f"{'Hour (UTC)':<12} {'n':>4} {'WR':>16} {'Net PnL':>10}")
print("-" * 44)
for h in range(24):
    b = f"hr{h:02d}"
    g = bkts.get(b, [])
    if g:
        print(f"{b:<12} {len(g):>4} {wr_str(g):>16} {net_str(g):>10}")
print()


# ── Section 8: EDGE × DELTA ───────────────────────────────────────────────────
print("=" * 60)
print("SECTION 8: EDGE × DELTA  (WR%)")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_edgeb"], t["_db"])].append(t["_pnl"])

header = f"{'':17}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (17 + W * len(DELTA_BINS)))
for eb in EDGE_BINS:
    row = f"{eb:<17}"
    has = any(grid.get((eb, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{wr_str(grid.get((eb, db), [])):>{W}}"
    print(row)
print()
print("Net PnL EDGE × DELTA:")
for eb in EDGE_BINS:
    row = f"{eb:<17}"
    has = any(grid.get((eb, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{net_str(grid.get((eb, db), [])):>{W}}"
    print(row)
print()


# ── Section 9: VELOCITY × DELTA ──────────────────────────────────────────────
print("=" * 60)
print("SECTION 9: VELOCITY × DELTA  (WR%)")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_velb"], t["_db"])].append(t["_pnl"])

header = f"{'':20}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (20 + W * len(DELTA_BINS)))
for vb in VEL_BINS:
    row = f"{vb:<20}"
    has = any(grid.get((vb, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{wr_str(grid.get((vb, db), [])):>{W}}"
    print(row)
print()
print("Net PnL VELOCITY × DELTA:")
for vb in VEL_BINS:
    row = f"{vb:<20}"
    has = any(grid.get((vb, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{net_str(grid.get((vb, db), [])):>{W}}"
    print(row)
print()


# ── Section 10: ASSET × DELTA ─────────────────────────────────────────────────
print("=" * 60)
print("SECTION 10: ASSET × DELTA  (WR%)")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_asset"], t["_db"])].append(t["_pnl"])

header = f"{'':8}" + "".join(f"{d:>{W}}" for d in DELTA_BINS)
print(header)
print("-" * (8 + W * len(DELTA_BINS)))
for ab in ASSET_BINS:
    row = f"{ab:<8}"
    has = any(grid.get((ab, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{wr_str(grid.get((ab, db), [])):>{W}}"
    print(row)
print()
print("Net PnL ASSET × DELTA:")
for ab in ASSET_BINS:
    row = f"{ab:<8}"
    has = any(grid.get((ab, db)) for db in DELTA_BINS)
    if not has:
        continue
    for db in DELTA_BINS:
        row += f"{net_str(grid.get((ab, db), [])):>{W}}"
    print(row)
print()


# ── Section 11: ASSET × HOUR (per hour) ───────────────────────────────────────
print("=" * 60)
print("SECTION 11: ASSET × HOUR  (per hour, UTC)")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_asset"], t["_hg"])].append(t["_pnl"])

print(f"{'Hour':<8} {'Asset':<8} {'n':>4} {'WR':>16} {'Net PnL':>10}")
print("-" * 48)
for h in range(24):
    hg = f"hr{h:02d}"
    printed_any = False
    for ab in ASSET_BINS:
        g = grid.get((ab, hg), [])
        if g:
            print(f"{hg:<8} {ab:<8} {len(g):>4} {wr_str(g):>16} {net_str(g):>10}")
            printed_any = True
    if printed_any:
        print()
print()
print("Net PnL ASSET × HOUR GROUP:")
for ab in ASSET_BINS:
    row = f"{ab:<8}"
    has = any(grid.get((ab, hg)) for hg in HRGRP_BINS)
    if not has:
        continue
    for hg in HRGRP_BINS:
        row += f"{net_str(grid.get((ab, hg), [])):>{W}}"
    print(row)
print()


# ── Section 12: EDGE × VELOCITY ───────────────────────────────────────────────
print("=" * 60)
print("SECTION 12: EDGE × VELOCITY  (WR%)")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_edgeb"], t["_velb"])].append(t["_pnl"])

header = f"{'':17}" + "".join(f"{v:>{W}}" for v in VEL_BINS)
print(header)
print("-" * (17 + W * len(VEL_BINS)))
for eb in EDGE_BINS:
    row = f"{eb:<17}"
    has = any(grid.get((eb, vb)) for vb in VEL_BINS)
    if not has:
        continue
    for vb in VEL_BINS:
        row += f"{wr_str(grid.get((eb, vb), [])):>{W}}"
    print(row)
print()


# ── Section 13: LAG × ELAPSED (legacy — useful for SNIPER) ───────────────────
print("=" * 60)
print("SECTION 13: LAG × ELAPSED  (WR%) — SNIPER trades")
print("=" * 60)
grid = defaultdict(list)
for t in live:
    grid[(t["_lb"], t["_eb"])].append(t["_pnl"])

header = f"{'':14}" + "".join(f"{e:>{W}}" for e in ELAP_BINS)
print(header)
print("-" * (14 + W * len(ELAP_BINS)))
for lb in LAG_BINS:
    row = f"{lb:<14}"
    has = any(grid.get((lb, eb)) for eb in ELAP_BINS)
    if not has:
        continue
    for eb in ELAP_BINS:
        row += f"{wr_str(grid.get((lb, eb), [])):>{W}}"
    print(row)
print()


# ── Section 14: TOP COMBINATIONS ─────────────────────────────────────────────
print("=" * 60)
print("SECTION 14: TOP COMBINATIONS (n>=5, WR>=65%, net>0)")
print("=" * 60)

combos = defaultdict(list)
for t in live:
    key = (t["_asset"], t["_db"], t["_edgeb"], t["_velb"])
    combos[key].append(t["_pnl"])

results = []
for (ab, db, edgeb, velb), pnls in combos.items():
    n = len(pnls)
    if n < 5:
        continue
    w = sum(1 for p in pnls if p > 0)
    wr = w / n
    net = sum(pnls)
    if wr >= 0.65 and net > 0:
        results.append((wr, net, n, ab, db, edgeb, velb))

if results:
    results.sort(reverse=True)
    print(f"{'Asset':<6} {'Delta':<13} {'Edge':<17} {'Vel':<20} {'WR':>6} {'n':>4} {'Net':>9}")
    print("-" * 82)
    for wr, net, n, ab, db, edgeb, velb in results:
        print(f"{ab:<6} {db:<13} {edgeb:<17} {velb:<20} {wr*100:>5.0f}% {n:>4}  ${net:>+7.2f}")
else:
    print("No combinations with n>=5, WR>=65%, net>0 found.")

print()
print("KILL ZONES (n>=5, WR<40%):")
kills = []
for (ab, db, edgeb, velb), pnls in combos.items():
    n = len(pnls)
    if n < 5:
        continue
    w = sum(1 for p in pnls if p > 0)
    wr = w / n
    if wr < 0.40:
        kills.append((wr, sum(pnls), n, ab, db, edgeb, velb))

if kills:
    kills.sort()
    print(f"{'Asset':<6} {'Delta':<13} {'Edge':<17} {'Vel':<20} {'WR':>6} {'n':>4} {'Net':>9}")
    print("-" * 82)
    for wr, net, n, ab, db, edgeb, velb in kills:
        print(f"{ab:<6} {db:<13} {edgeb:<17} {velb:<20} {wr*100:>5.0f}% {n:>4}  ${net:>+7.2f}")
else:
    print("No kill zones with n>=5, WR<40% found.")

print()
print("!! = WR < 40%   ** = WR >= 60%")
print("Done.")
