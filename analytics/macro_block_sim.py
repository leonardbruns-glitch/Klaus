#!/usr/bin/env python3
"""
Simulate cross-asset macro reversal block:
  After any BOND_CATASTROPHIC exit, block new TERMINAL entries for N seconds.
  Report how many wins vs losses would be blocked at each N.

Run: python3 analytics/macro_block_sim.py
"""
import json, os
from datetime import datetime, timezone

LOGS   = os.path.join(os.path.dirname(__file__), "../logs")
CUTOFF = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc).timestamp()

trades = []
with open(os.path.join(LOGS, "trades.jsonl")) as f:
    for line in f:
        try:
            t = json.loads(line)
            if (t.get("ts_open", 0) or 0) >= CUTOFF and not t.get("dry_run"):
                trades.append(t)
        except Exception:
            pass

bond = [t for t in trades if t.get("is_bond") or t.get("signal_source") == "BOND"]
bond.sort(key=lambda t: t.get("ts_open", 0))

cats = [t for t in bond if t.get("exit_reason") == "BOND_CATASTROPHIC"]
entries = [t for t in bond if t.get("exit_reason") != "BOND_CATASTROPHIC"]

print(f"BOND trades (Apr25+): {len(bond)}")
print(f"  BOND_CATASTROPHIC exits: {len(cats)}")
print(f"  Non-catastrophic entries: {len(entries)}")
print()

# ts_close of the catastrophic exit = when the SL fired = when block starts
# Use ts_close; fall back to ts_open + hold_s
def cat_exit_ts(t):
    tc = t.get("ts_close", 0) or 0
    if tc > 0:
        return tc
    to = t.get("ts_open", 0) or 0
    hold = t.get("hold_s", 0) or 0
    return to + hold if to > 0 else 0

cat_events = [(cat_exit_ts(t), t.get("asset", "?")) for t in cats if cat_exit_ts(t) > 0]

print(f"  Catastrophic events with valid exit_ts: {len(cat_events)}")
print()

def simulate(block_s, cross_only=False):
    """
    block_s: seconds to block after a BOND_CATASTROPHIC fires
    cross_only: if True, only block OTHER assets (not same asset as the cat)
    """
    blocked_wins = []
    blocked_losses = []

    for entry in entries:
        to = entry.get("ts_open", 0) or 0
        if to == 0:
            continue
        asset = entry.get("asset", "?")
        pnl = entry.get("net_pnl", 0) or 0

        # Check if any catastrophic event blocks this entry
        blocked = False
        for cat_ts, cat_asset in cat_events:
            if cat_ts <= 0:
                continue
            if cross_only and cat_asset == asset:
                continue  # same asset — not blocked in cross_only mode
            if cat_ts <= to <= cat_ts + block_s:
                blocked = True
                break

        if blocked:
            if pnl > 0:
                blocked_wins.append(entry)
            else:
                blocked_losses.append(entry)

    return blocked_wins, blocked_losses

print("=== SIMULATION: block ALL assets after any BOND_CATASTROPHIC ===")
print(f"{'Block(s)':<10} {'Blk_W':<8} {'Blk_L':<8} {'W_pnl':<12} {'L_pnl':<12} {'NET_gain':<12} {'%wins_lost'}")
print("-" * 75)
all_wins = [t for t in entries if (t.get("net_pnl", 0) or 0) > 0]
all_losses = [t for t in entries if (t.get("net_pnl", 0) or 0) <= 0]
for s in [30, 60, 90, 120, 180]:
    bw, bl = simulate(s, cross_only=False)
    w_pnl = sum(t.get("net_pnl", 0) for t in bw)
    l_pnl = sum(t.get("net_pnl", 0) for t in bl)
    net = -l_pnl - w_pnl  # gains from blocking losses minus cost of blocking wins
    pct_w = len(bw) / len(all_wins) * 100 if all_wins else 0
    print(f"{s:<10} {len(bw):<8} {len(bl):<8} ${w_pnl:<10.2f} ${l_pnl:<10.2f} ${net:<10.2f} {pct_w:.1f}%")

print()
print("=== SIMULATION: block CROSS-ASSET only (same asset still allowed) ===")
print(f"{'Block(s)':<10} {'Blk_W':<8} {'Blk_L':<8} {'W_pnl':<12} {'L_pnl':<12} {'NET_gain':<12} {'%wins_lost'}")
print("-" * 75)
for s in [30, 60, 90, 120, 180]:
    bw, bl = simulate(s, cross_only=True)
    w_pnl = sum(t.get("net_pnl", 0) for t in bw)
    l_pnl = sum(t.get("net_pnl", 0) for t in bl)
    net = -l_pnl - w_pnl
    pct_w = len(bw) / len(all_wins) * 100 if all_wins else 0
    print(f"{s:<10} {len(bw):<8} {len(bl):<8} ${w_pnl:<10.2f} ${l_pnl:<10.2f} ${net:<10.2f} {pct_w:.1f}%")

print()
print("=== BREAKDOWN: which wins get blocked at 90s all-asset? ===")
bw90, bl90 = simulate(90, cross_only=False)
if bw90:
    by_asset = {}
    for t in bw90:
        a = t.get("asset", "?")
        by_asset.setdefault(a, []).append(t)
    for asset, ts in sorted(by_asset.items()):
        pnl = sum(t.get("net_pnl", 0) for t in ts)
        print(f"  {asset}: n={len(ts)}  sum=${pnl:.2f}")
else:
    print("  (no wins blocked)")

print()
print("=== BREAKDOWN: which losses get blocked at 90s all-asset? ===")
if bl90:
    by_reason = {}
    for t in bl90:
        r = t.get("exit_reason", "?")
        by_reason.setdefault(r, []).append(t)
    for reason, ts in sorted(by_reason.items()):
        pnl = sum(t.get("net_pnl", 0) for t in ts)
        print(f"  {reason}: n={len(ts)}  sum=${pnl:.2f}")
else:
    print("  (no losses blocked)")
