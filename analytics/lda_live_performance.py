"""
LDA live performance: win/loss determined by kline direction vs bet direction.
Rule: WIN = kline moved in same direction as bond_outcome_direction.

Uses entered_correctly (kline-based) when available; falls back to
window_resolution.jsonl lookup for trades where resolution didn't fire.
"""
import json, glob, os, math
from collections import Counter

TRADES_FILE   = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.jsonl")
SHADOW_ROOT   = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")
STAKE_USD     = 5.0

# ── 1. Window resolutions (asset, window_end_ts, window_size_s) → moved_up ──
resolutions = {}
for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            r = json.loads(line)
            key = (r["asset"], r["window_end_ts"], r.get("window_size_s", 300))
            resolutions[key] = r["moved_up"]

# ── 2. Load live LDA trades ──────────────────────────────────────────────────
lda = []
with open(TRADES_FILE) as f:
    for line in f:
        t = json.loads(line)
        if t.get("bond_entry_class") == "LDA" and t.get("is_live"):
            lda.append(t)

# ── 3. Determine kline win for each trade ────────────────────────────────────
wins, losses, unknown = [], [], []
for t in lda:
    ec = t.get("entered_correctly")
    if ec is None:
        wsz   = t.get("window_size_s", 300)
        wend  = math.ceil(t["ts_open"] / wsz) * wsz
        asset = t["asset"].upper()
        moved_up = resolutions.get((asset, wend, wsz))
        if moved_up is not None:
            bet_up = t.get("bond_outcome_direction") == "up"
            ec = (bet_up == moved_up)
    if ec is True:
        wins.append(t)
    elif ec is False:
        losses.append(t)
    else:
        unknown.append(t)

n = len(wins) + len(losses)

# ── 4. Report ─────────────────────────────────────────────────────────────────
print(f"=== LDA LIVE PERFORMANCE (kline-based win/loss) ===")
print(f"Total live trades : {len(lda)}")
print(f"Resolved          : {n}  |  Unknown: {len(unknown)}")
print(f"Direction WR      : {len(wins)}/{n} = {len(wins)/n:.1%}")
print()

win_pnl  = sum(t["net_pnl"] for t in wins)
loss_pnl = sum(t["net_pnl"] for t in losses)

# Expected PnL: if every kline-win had been held and redeemed at $1/share
expected_wins = sum((t["shares"] - t["stake"]) for t in wins)  # payoff = shares - cost
actual_wins   = sum(t["net_pnl"] for t in wins if t["net_pnl"] > 0)

print(f"Kline WIN  n={len(wins):>3}  actual_net_pnl=${win_pnl:+.2f}  expected_net=${expected_wins:+.2f}")
print(f"Kline LOSE n={len(losses):>3}  actual_net_pnl=${loss_pnl:+.2f}")
print(f"Total actual PnL  : ${win_pnl + loss_pnl:+.2f}")
print()

# Win exits breakdown
print("Kline WIN exit reasons:", dict(Counter(t["exit_reason"] for t in wins)))
print("Kline LOSE exit reasons:", dict(Counter(t["exit_reason"] for t in losses)))
print()

# Cases where we won by kline but booked as BOND_RESOLVED_NO (lost prematurely)
rno_wins = [t for t in wins if t["exit_reason"] == "BOND_RESOLVED_NO"]
if rno_wins:
    rno_pnl = sum(t["net_pnl"] for t in rno_wins)
    rno_exp = sum((t["shares"] - t["stake"]) for t in rno_wins)
    print(f"Kline-WIN booked as BOND_RESOLVED_NO (premature loss): {len(rno_wins)}")
    print(f"  Actual logged PnL : ${rno_pnl:+.2f}  (booked as full losses)")
    print(f"  Expected PnL      : ${rno_exp:+.2f}  (if held to redemption)")
    print(f"  Gap (recoverable) : ${rno_exp - rno_pnl:+.2f}")
    print()

# By asset
print("=== BY ASSET ===")
print(f"{'asset':>6} {'n':>5} {'wins':>5} {'wr':>7}  exits(wins)")
for asset in ["BTC", "ETH", "SOL"]:
    w = [t for t in wins   if t["asset"] == asset]
    l = [t for t in losses if t["asset"] == asset]
    tot = len(w) + len(l)
    if tot == 0:
        continue
    exits = dict(Counter(t["exit_reason"] for t in w))
    print(f"{asset:>6} {tot:>5} {len(w):>5} {len(w)/tot:>7.1%}  {exits}")

print()
print("=== BY WINDOW SIZE ===")
print(f"{'wsz':>6} {'n':>5} {'wins':>5} {'wr':>7}")
for wsz, label in [(300, "5m"), (900, "15m")]:
    w = [t for t in wins   if t.get("window_size_s") == wsz]
    l = [t for t in losses if t.get("window_size_s") == wsz]
    tot = len(w) + len(l)
    if tot == 0:
        continue
    print(f"{label:>6} {tot:>5} {len(w):>5} {len(w)/tot:>7.1%}")

if unknown:
    print(f"\nUnresolved trades ({len(unknown)}):")
    for t in unknown:
        print(f"  {t['trade_id']} dir={t.get('bond_outcome_direction')} exit={t['exit_reason']} net_pnl={t['net_pnl']:+.2f}")
