"""
signal_quality_audit.py — Two-part diagnostic script.

Part 1: FAILED_TO_FILL audit
  - How many high-conviction entries are being killed by the 0.30 cap?
  - Distribution of entry prices near the cap
  - WR by entry price bucket

Part 2: Velocity heatmap (move_age_s × velocity_5s_pct)
  - Requires trades collected AFTER 2026-04-12 (new fields)
  - Shows "kill zone" where WR < 40%

Run from Klaus root:
    python3 analytics/signal_quality_audit.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

TRADE_LOG = Path("logs/trades.jsonl")
CAP = 0.30       # current hard cap in order_manager
BUFFER = 0.05    # 5% limit-buy buffer

# ── Load trades ──────────────────────────────────────────────────────────────

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

live = [t for t in trades if t.get("is_live") and t.get("entry_price", 0) > 0]
print(f"Loaded {len(trades)} total trades, {len(live)} live with entry price\n")

if not live:
    print("No live trades found.")
    sys.exit(0)


# ── Part 1: Entry price distribution + cap impact ────────────────────────────

print("=" * 60)
print("PART 1: ENTRY PRICE DISTRIBUTION & CAP IMPACT")
print("=" * 60)

prices = [t["entry_price"] for t in live]
wins   = [t for t in live if t.get("net_pnl", 0) > 0]
losses = [t for t in live if t.get("net_pnl", 0) <= 0]

print(f"Entry price range: {min(prices):.4f} – {max(prices):.4f}")
print(f"Mean: {sum(prices)/len(prices):.4f}   Median: {sorted(prices)[len(prices)//2]:.4f}")
print()

# Trades near or at the cap (ask was high enough that buffer would have hit 0.30)
# If entry_price >= 0.285, the ask before buffer was >= 0.285/1.05 = 0.271
# and the buffered price 0.285*1.05 = 0.299 → near the cap
near_cap = [t for t in live if t["entry_price"] >= 0.27]
at_cap   = [t for t in live if t["entry_price"] >= 0.295]  # effectively capped
print(f"Entries >= 0.27 (approaching cap zone): {len(near_cap)} ({len(near_cap)/len(live)*100:.1f}%)")
print(f"Entries >= 0.295 (effectively capped):  {len(at_cap)} ({len(at_cap)/len(live)*100:.1f}%)")

if near_cap:
    nc_wr = sum(1 for t in near_cap if t.get("net_pnl", 0) > 0) / len(near_cap)
    print(f"WR at >= 0.27: {nc_wr*100:.1f}%  (overall WR: {len(wins)/len(live)*100:.1f}%)")

print()

# Bucket analysis: 0.05 steps
buckets = defaultdict(list)
for t in live:
    p = t["entry_price"]
    bucket = round(int(p * 20) / 20, 2)   # round to nearest 0.05
    buckets[bucket].append(t)

print(f"{'Price bucket':<14} {'N':>4} {'WR':>7} {'Net PnL':>10} {'Avg PnL':>9}")
print("-" * 48)
for b in sorted(buckets):
    bt = buckets[b]
    wr = sum(1 for t in bt if t.get("net_pnl", 0) > 0) / len(bt)
    net = sum(t.get("net_pnl", 0) for t in bt)
    avg = net / len(bt)
    flag = " ← CAP ZONE" if b >= 0.25 else ""
    print(f"  {b:.2f}–{b+0.05:.2f}      {len(bt):>4}  {wr*100:>6.1f}%  ${net:>8.2f}  ${avg:>7.2f}{flag}")

print()

# WR by quality_score where entry is near cap
qs_near_cap = [(t.get("quality_score", 0), t.get("net_pnl", 0)) for t in near_cap]
if qs_near_cap:
    print("Quality score distribution for entries >= 0.27:")
    qs_buckets = defaultdict(list)
    for qs, pnl in qs_near_cap:
        qs_buckets[qs].append(pnl)
    for qs in sorted(qs_buckets):
        pnls = qs_buckets[qs]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        print(f"  QS={qs:+d}: n={len(pnls)}  WR={wr*100:.1f}%  net=${sum(pnls):.2f}")
    print()

# Estimated missed fills: how often would we have tried to enter at ask > 0.30/1.05?
# We can infer: if entry_price == 0.30 exactly AND win_rate > overall, cap is filtering
# (We can't directly count failed fills without the raw order log)
print("NOTE: FAILED_TO_FILL events are not in trades.jsonl (only successful fills are).")
print("To count failed fills, run:")
print("  grep -c 'Entry not filled\\|FAILED.*fill' logs/bot.log")
print()


# ── Part 2: Velocity heatmap ─────────────────────────────────────────────────

print("=" * 60)
print("PART 2: VELOCITY HEATMAP (move_age_s × velocity_5s_pct)")
print("=" * 60)

vel_trades = [t for t in live if t.get("move_age_s", 999) < 998 or t.get("velocity_5s_pct", 0) != 0]
print(f"Trades with velocity data (post 2026-04-12): {len(vel_trades)}")

if len(vel_trades) < 10:
    print(f"Insufficient data for heatmap (need ≥10, have {len(vel_trades)}).")
    print("Collect more live trades with the new fields, then re-run.")
else:
    # Bin move_age_s: 0-5, 5-10, 10-15, 15-20, 20-30, 30+
    age_bins  = [0, 5, 10, 15, 20, 30, 999]
    age_labels = ["0-5s", "5-10s", "10-15s", "15-20s", "20-30s", "30s+"]

    # Bin velocity_5s_pct: <-0.05, -0.05–0, 0–0.05, >0.05
    vel_bins  = [-999, -0.05, 0.0, 0.05, 999]
    vel_labels = ["<-0.05% (down)", "-0.05–0% (flat-)", "0–+0.05% (flat+)", ">+0.05% (up)"]

    grid = defaultdict(list)
    for t in vel_trades:
        age = t.get("move_age_s", 999)
        vel = t.get("velocity_5s_pct", 0)
        ai = next((i for i, b in enumerate(age_bins[1:]) if age < b), len(age_labels) - 1)
        vi = next((i for i, b in enumerate(vel_bins[1:]) if vel < b), len(vel_labels) - 1)
        grid[(ai, vi)].append(t.get("net_pnl", 0))

    print()
    print(f"{'':12}", end="")
    for vl in vel_labels:
        print(f"  {vl[:14]:>14}", end="")
    print()
    print("-" * (12 + 16 * len(vel_labels)))

    for ai, al in enumerate(age_labels):
        print(f"{al:<12}", end="")
        for vi in range(len(vel_labels)):
            pnls = grid.get((ai, vi), [])
            if not pnls:
                print(f"  {'—':>14}", end="")
            else:
                wr = sum(1 for p in pnls if p > 0) / len(pnls)
                flag = "!!" if wr < 0.40 else ("  " if wr < 0.55 else "**")
                print(f"  {wr*100:.0f}%(n={len(pnls)}){flag:>2}", end="")
        print()

    print()
    print("!! = WR < 40% KILL ZONE   ** = WR > 55% GOOD ZONE")
    print()

    # Summary: which velocity_5s/age combos should be blocked?
    kill_zones = [(age_labels[ai], vel_labels[vi], len(pnls), sum(1 for p in pnls if p > 0)/len(pnls))
                  for (ai, vi), pnls in grid.items()
                  if len(pnls) >= 5 and sum(1 for p in pnls if p > 0)/len(pnls) < 0.40]
    if kill_zones:
        print("KILL ZONES (n≥5, WR<40%):")
        for age, vel, n, wr in sorted(kill_zones, key=lambda x: x[3]):
            print(f"  move_age={age}  velocity={vel}  n={n}  WR={wr*100:.1f}%")
    else:
        print("No kill zones identified yet (need n≥5 per cell).")

print()
print("Done.")
