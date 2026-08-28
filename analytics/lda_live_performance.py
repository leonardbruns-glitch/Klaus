"""
LDA live performance: win/loss determined by kline direction vs bet direction.

kline_pnl (patched into trades.jsonl at resolution) is ground truth:
  WIN  = (1 - entry_price) * shares - fee  (guaranteed redemption at $1)
  LOSE = -stake - fee

net_pnl = actual realized exit price (may differ from kline_pnl due to exit timing).

Primary win/loss source: window_resolution.jsonl (binance_kline).
Fallback: entered_correctly field (also kline-patched at resolution time).
"""
import json, glob, os, math
from collections import Counter

TRADES_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.jsonl")
SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")

# ── 1. Window resolutions → moved_up ────────────────────────────────────────
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

# ── 3. Resolve win/loss — kline primary, field fallback ─────────────────────
wins, losses, unknown = [], [], []
src_kline = src_field = src_unknown = 0
for t in lda:
    wsz   = t.get("window_size_s", 300)
    wend  = math.ceil(t["ts_open"] / wsz) * wsz
    moved_up = resolutions.get((t["asset"].upper(), wend, wsz))
    if moved_up is not None:
        ec = ((t.get("bond_outcome_direction") == "up") == moved_up)
        src_kline += 1
    else:
        ec = t.get("entered_correctly")
        if ec is not None:
            src_field += 1
        else:
            src_unknown += 1
    if ec is True:
        wins.append(t)
    elif ec is False:
        losses.append(t)
    else:
        unknown.append(t)

n = len(wins) + len(losses)

# ── 4. PnL summary using kline_pnl (ground truth) ───────────────────────────
kpnl_wins   = sum(t["kline_pnl"] for t in wins   if t.get("kline_pnl") is not None)
kpnl_losses = sum(t["kline_pnl"] for t in losses if t.get("kline_pnl") is not None)
kpnl_total  = kpnl_wins + kpnl_losses
apnl_total  = sum(t["net_pnl"] for t in wins + losses)

print("=== LDA LIVE PERFORMANCE ===")
print(f"Total live trades : {len(lda)}")
print(f"Resolved          : {n}  |  Unknown: {len(unknown)}")
print(f"  Source: kline={src_kline}  field_fallback={src_field}  unresolved={src_unknown}")
print(f"Direction WR      : {len(wins)}/{n} = {len(wins)/n:.1%}")
print()
print(f"kline_pnl total   : ${kpnl_total:+.2f}  (ground truth: WIN=sell@1, LOSE=lose stake)")
print(f"net_pnl total     : ${apnl_total:+.2f}  (actual realized exits)")
print(f"Exit drag         : ${apnl_total - kpnl_total:+.2f}  (negative = exits cost us vs ideal)")
print()

print("Kline WIN  exit reasons:", dict(Counter(t["exit_reason"] for t in wins)))
print("Kline LOSE exit reasons:", dict(Counter(t["exit_reason"] for t in losses)))
print()

# Premature losses: kline-WIN but exited as loss
rno_wins = [t for t in wins if t["net_pnl"] < 0]
if rno_wins:
    rno_kpnl = sum(t["kline_pnl"] for t in rno_wins if t.get("kline_pnl") is not None)
    rno_apnl = sum(t["net_pnl"] for t in rno_wins)
    exits = dict(Counter(t["exit_reason"] for t in rno_wins))
    print(f"Kline-WIN booked as loss ({len(rno_wins)} trades, exits={exits}):")
    print(f"  actual net_pnl  : ${rno_apnl:+.2f}")
    print(f"  kline_pnl       : ${rno_kpnl:+.2f}")
    print(f"  recoverable gap : ${rno_kpnl - rno_apnl:+.2f}")
    print()

# ── 5. By asset ──────────────────────────────────────────────────────────────
print("=== BY ASSET ===")
print(f"{'asset':>6} {'n':>4} {'WR':>6} {'kline_pnl':>10} {'net_pnl':>9}  exits(wins)")
for asset in ["BTC", "ETH", "SOL"]:
    w = [t for t in wins   if t["asset"] == asset]
    l = [t for t in losses if t["asset"] == asset]
    tot = len(w) + len(l)
    if tot == 0:
        continue
    kp = sum(t.get("kline_pnl", 0) for t in w + l)
    ap = sum(t["net_pnl"] for t in w + l)
    exits = dict(Counter(t["exit_reason"] for t in w))
    print(f"{asset:>6} {tot:>4} {len(w)/tot:>5.1%} ${kp:>+9.2f} ${ap:>+8.2f}  {exits}")

print()
print("=== BY WINDOW SIZE ===")
print(f"{'wsz':>6} {'n':>4} {'WR':>6} {'kline_pnl':>10} {'net_pnl':>9}")
for wsz, label in [(300, "5m"), (900, "15m")]:
    w = [t for t in wins   if t.get("window_size_s") == wsz]
    l = [t for t in losses if t.get("window_size_s") == wsz]
    tot = len(w) + len(l)
    if tot == 0:
        continue
    kp = sum(t.get("kline_pnl", 0) for t in w + l)
    ap = sum(t["net_pnl"] for t in w + l)
    print(f"{label:>6} {tot:>4} {len(w)/tot:>5.1%} ${kp:>+9.2f} ${ap:>+8.2f}")

if unknown:
    print(f"\nUnresolved trades ({len(unknown)}):")
    for t in unknown:
        print(f"  {t['trade_id']} dir={t.get('bond_outcome_direction')} exit={t['exit_reason']} net_pnl={t['net_pnl']:+.2f}")
