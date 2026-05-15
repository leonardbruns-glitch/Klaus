"""
Post-fix clean analysis of LDA live trades.

Polluted trades excluded:
  - bond_outcome_direction empty/missing (direction unknown before field existed)
  - asset == SOL (structurally blocked)
  - is_live=False (dry run)
  - entry_price <= 0.01 (orphan sells / logging bugs)
  - signal_source != LDA

rem_bucket derived from ts_open + window_size_s (bypasses term_remaining_s=0 gap).
  B3: rem [180,300s)   B2: [120,180s)   B1: [60,120s)   B0: [8,60s)

BNC tiers (term_binance_5m_pct abs):
  low  < 0.07%
  mid  0.07-0.10%
  high >= 0.10%
"""

import json
import math
from collections import defaultdict
from pathlib import Path

TRADES_FILE = Path("/root/Klaus/logs/trades.jsonl")

# ── Current gate parameters (mirrors late_direction_arb.py) ──────────────────
ASK_FLOOR = 0.60
ASK_CEIL  = 0.98
BLOCKED_HOURS_UTC = {0, 1, 2, 3, 23}
_ALL_BLOCKED_LATE   = frozenset({3, 5, 6, 7, 12, 15})
_ALL_BLOCKED_LATE_B1 = frozenset({4, 5, 12, 15})
_ETH_BLOCKED_B1     = frozenset({1, 2})
_BTC_BLOCKED_B1     = frozenset({13})
_ETH_BLOCKED_LATE   = frozenset({0, 8, 9, 13, 16, 17, 21, 22})
_BTC_BLOCKED_LATE   = frozenset({17})
_BTC_BLOCKED_B3     = frozenset({1, 4, 18, 21, 23})
_BUCKET_KELLY_CUM   = {3: 0.90, 2: 0.95, 1: 1.00}

# ── Helpers ───────────────────────────────────────────────────────────────────

def rem_bucket(ts_open: float, window_s: int = 300) -> int:
    wend = math.ceil(ts_open / window_s) * window_s
    rem  = wend - ts_open
    if rem < 60:   return 0
    if rem < 120:  return 1
    if rem < 180:  return 2
    return 3

def bnc_tier(bnc_abs: float) -> str:
    if bnc_abs < 0.07:  return "low"
    if bnc_abs < 0.10:  return "mid"
    return "high"

def passes_current_gate(t: dict) -> bool:
    """Returns True if this trade would be accepted under current live gate."""
    ask  = float(t.get("entry_price", 0))
    hour = int(t.get("hour_utc", -1))
    asset = t.get("asset", "").upper()
    rb   = rem_bucket(float(t.get("ts_open", 0)), int(t.get("window_size_s", 300) or 300))
    rem  = float(t.get("term_remaining_s") or 0)
    # derive rem from ts_open if term_remaining_s is 0 (logging gap)
    if rem <= 0:
        wsz  = int(t.get("window_size_s", 300) or 300)
        wend = math.ceil(float(t.get("ts_open", 0)) / wsz) * wsz
        rem  = wend - float(t.get("ts_open", 0))

    if asset == "SOL":            return False
    if hour in BLOCKED_HOURS_UTC: return False
    if not (ASK_FLOOR <= ask <= ASK_CEIL): return False
    if rem > 60  and ask >= 0.90: return False
    if rem > 120 and ask >= 0.80: return False
    if rem > 120 and ask < 0.69:  return False
    if rem > 180 and ask < 0.70:  return False
    if rb == 1   and ask < 0.75:  return False
    if rem > 120 and hour in _ALL_BLOCKED_LATE:
        if not (asset == "BTC" and rem >= 180 and hour == 15):
            return False
    if rb == 1   and hour in _ALL_BLOCKED_LATE_B1: return False
    if rb == 1   and asset == "ETH" and hour in _ETH_BLOCKED_B1: return False
    if rb == 1   and asset == "BTC" and hour in _BTC_BLOCKED_B1: return False
    if rem > 120 and asset == "ETH" and hour in _ETH_BLOCKED_LATE: return False
    if rem > 120 and asset == "BTC" and hour in _BTC_BLOCKED_LATE: return False
    if rem > 180 and asset == "BTC" and hour in _BTC_BLOCKED_B3:   return False
    if rb == 2   and hour == 4:    return False
    return True

def fmt(label, n, wins, net, stakes=None):
    wr  = wins / n * 100 if n else 0
    avg = net / n if n else 0
    pf_str = ""
    if stakes is not None and stakes > 0:
        pf_str = f"  PF={net/stakes+1:.2f}" if net > -stakes else "  PF<0"
    return f"  {label:<35} n={n:>5}  WR={wr:>5.1f}%  net=${net:>8.2f}  avg={avg:>+.4f}{pf_str}"

# ── Load ──────────────────────────────────────────────────────────────────────

print("Loading trades.jsonl …", flush=True)
lines = TRADES_FILE.read_text().splitlines()
all_trades = []
for l in lines:
    l = l.strip()
    if l:
        try: all_trades.append(json.loads(l))
        except: pass

lda_all = [t for t in all_trades
           if t.get("is_live") and t.get("signal_source") == "LDA" and "trade_id" in t]
print(f"  LDA live total: {len(lda_all)}")

# ── Pollution filter ──────────────────────────────────────────────────────────
def is_reliable(t: dict) -> bool:
    if not t.get("bond_outcome_direction"): return False   # direction unknown
    if t.get("asset", "").upper() == "SOL":  return False  # structurally blocked
    ep = float(t.get("entry_price", 0))
    if ep <= 0.01: return False                             # orphan sell
    return True

reliable  = [t for t in lda_all if is_reliable(t)]
polluted  = [t for t in lda_all if not is_reliable(t)]
print(f"  Reliable: {len(reliable)}  |  Polluted (excluded): {len(polluted)}")

# ── Breakdown of polluted ─────────────────────────────────────────────────────
no_dir  = [t for t in lda_all if not t.get("bond_outcome_direction")]
sol     = [t for t in lda_all if t.get("asset", "").upper() == "SOL"
           and t.get("bond_outcome_direction")]
orphans = [t for t in lda_all if float(t.get("entry_price",0)) <= 0.01
           and t.get("bond_outcome_direction") and t.get("asset","").upper() != "SOL"]
print(f"  Pollution breakdown: no_direction={len(no_dir)}, SOL={len(sol)}, orphan={len(orphans)}")

# ── Enrich reliable trades ────────────────────────────────────────────────────
for t in reliable:
    wsz = int(t.get("window_size_s", 300) or 300)
    ts  = float(t.get("ts_open", 0))
    wend = math.ceil(ts / wsz) * wsz
    rem  = wend - ts
    t["_rb"]  = rem_bucket(ts, wsz)
    t["_rem"] = rem
    # BNC from term_binance_5m_pct (logged at entry tick)
    raw_bnc = t.get("term_binance_5m_pct")
    if raw_bnc is None or raw_bnc == 0.0:
        raw_bnc = t.get("sniper_pm_drift_at_entry", 0.0)
    t["_bnc_abs"] = abs(float(raw_bnc or 0))
    t["_bnc_tier"] = bnc_tier(t["_bnc_abs"])
    t["_win"] = float(t.get("net_pnl", 0)) > 0
    t["_gate"] = passes_current_gate(t)

# ── Global stats ──────────────────────────────────────────────────────────────
def stats(trades):
    n = len(trades)
    wins = sum(1 for t in trades if t["_win"])
    net  = sum(float(t.get("net_pnl", 0)) for t in trades)
    stk  = sum(float(t.get("stake", 0)) for t in trades)
    return n, wins, net, stk

print("\n═══════════════════════════════════════════════════════════")
print("  CLEAN LDA PERFORMANCE (reliable trades only)")
print("═══════════════════════════════════════════════════════════")
n, w, net, stk = stats(reliable)
print(fmt("ALL RELIABLE", n, w, net, stk))

# Current-gate filtered
gated = [t for t in reliable if t["_gate"]]
ng, wg, netg, stkg = stats(gated)
print(fmt("CURRENT GATE ONLY", ng, wg, netg, stkg))

# ── By bucket ────────────────────────────────────────────────────────────────
print("\n─── By rem_bucket ───────────────────────────────────────────")
for rb, label in [(3,"B3 [180,300s)"),(2,"B2 [120,180s)"),(1,"B1 [60,120s)"),(0,"B0 [8,60s)")]:
    sub = [t for t in reliable if t["_rb"] == rb]
    if sub:
        n,w,net,stk = stats(sub)
        print(fmt(label, n, w, net, stk))

print("\n─── Current gate by bucket ──────────────────────────────────")
for rb, label in [(3,"B3 gated"),(2,"B2 gated"),(1,"B1 gated"),(0,"B0 gated")]:
    sub = [t for t in reliable if t["_rb"] == rb and t["_gate"]]
    if sub:
        n,w,net,stk = stats(sub)
        print(fmt(label, n, w, net, stk))

# ── By asset ─────────────────────────────────────────────────────────────────
print("\n─── By asset (gated) ────────────────────────────────────────")
for asset in ["BTC","ETH"]:
    sub = [t for t in reliable if t["_gate"] and t.get("asset","").upper()==asset]
    if sub:
        n,w,net,stk = stats(sub)
        print(fmt(asset, n, w, net, stk))

# ── By BNC tier ───────────────────────────────────────────────────────────────
print("\n─── By BNC tier (gated) ─────────────────────────────────────")
for tier in ["high","mid","low"]:
    sub = [t for t in reliable if t["_gate"] and t["_bnc_tier"]==tier]
    if sub:
        n,w,net,stk = stats(sub)
        print(fmt(f"BNC {tier} ({'>0.10%' if tier=='high' else '0.07-0.10%' if tier=='mid' else '<0.07%'})", n, w, net, stk))

# ── Bucket × BNC tier (gated) ─────────────────────────────────────────────────
print("\n─── Bucket × BNC tier (gated) ───────────────────────────────")
for rb, rl in [(3,"B3"),(2,"B2"),(1,"B1")]:
    for tier in ["high","mid","low"]:
        sub = [t for t in reliable if t["_gate"] and t["_rb"]==rb and t["_bnc_tier"]==tier]
        if len(sub) >= 5:
            n,w,net,stk = stats(sub)
            print(fmt(f"  {rl} × BNC-{tier}", n, w, net, stk))

# ── Bucket × asset (gated) ────────────────────────────────────────────────────
print("\n─── Bucket × asset (gated) ──────────────────────────────────")
for rb, rl in [(3,"B3"),(2,"B2"),(1,"B1")]:
    for asset in ["BTC","ETH"]:
        sub = [t for t in reliable if t["_gate"] and t["_rb"]==rb and t.get("asset","").upper()==asset]
        if len(sub) >= 5:
            n,w,net,stk = stats(sub)
            print(fmt(f"  {rl} × {asset}", n, w, net, stk))

# ── By UTC hour (gated, n>=5) ─────────────────────────────────────────────────
print("\n─── By UTC hour (gated, n≥5) ────────────────────────────────")
hour_data = defaultdict(list)
for t in reliable:
    if t["_gate"]:
        hour_data[int(t.get("hour_utc",-1))].append(t)
for h in sorted(hour_data.keys()):
    sub = hour_data[h]
    if len(sub) >= 5:
        n,w,net,stk = stats(sub)
        print(fmt(f"  H{h:02d}", n, w, net, stk))

# ── Ask band (gated) ─────────────────────────────────────────────────────────
print("\n─── Ask band (gated) ────────────────────────────────────────")
bands = [(0.60,0.70),(0.70,0.75),(0.75,0.80),(0.80,0.85),(0.85,0.90),(0.90,0.99)]
for lo, hi in bands:
    sub = [t for t in reliable if t["_gate"] and lo <= float(t.get("entry_price",0)) < hi]
    if len(sub) >= 3:
        n,w,net,stk = stats(sub)
        print(fmt(f"  ask [{lo:.2f},{hi:.2f})", n, w, net, stk))

# ── Bucket weight re-validation on live data ──────────────────────────────────
# Group reliable+gated trades by (asset, window_end_ts) to form windows
# then simulate EV under different (b3_cum, b2_cum) allocations.
print("\n═══════════════════════════════════════════════════════════")
print("  BUCKET WEIGHT RE-VALIDATION (live gated trades)")
print("═══════════════════════════════════════════════════════════")

BANKROLL   = 300.0
FEE_RATE   = 0.02
MIN_BUDGET = 5.0
BNC_FRACS  = {"low": 0.015, "mid": 0.15, "high": 0.22}

# Build per-asset-window groups
windows = defaultdict(list)
for t in reliable:
    if not t["_gate"]: continue
    wsz  = int(t.get("window_size_s",300) or 300)
    ts   = float(t.get("ts_open",0))
    wend = math.ceil(ts / wsz) * wsz
    asset = t.get("asset","").upper()
    key = (asset, wend)
    windows[key].append(t)

# For each window-key, we have trades from B1/B2/B3 (often only 1 bucket fires).
# We compute: for a given (b3_cum, b2_cum), what would the net EV be across all windows?
# Per window-asset: simulate cumulative staking, use actual win/loss from fixed trades.

def simulate_window_ev(window_trades, b3_cum, b2_cum, b1_cum=1.00):
    """Given trades in one asset-window (sorted by bucket desc), compute simulated net pnl."""
    # Sort B3 first, then B2, then B1
    sorted_t = sorted(window_trades, key=lambda t: -t["_rb"])
    cum_map = {3: b3_cum, 2: b2_cum, 1: b1_cum, 0: 0.0}

    # Use the first trade's BNC tier to set full_target (all trades in same window same BNC env)
    bnc_abs   = sorted_t[0]["_bnc_abs"]
    frac      = BNC_FRACS.get(sorted_t[0]["_bnc_tier"], 0.15)
    full_target = max(5.0, min(100.0, BANKROLL * frac))

    cum_staked = 0.0
    net_pnl    = 0.0

    for t in sorted_t:
        rb = t["_rb"]
        if rb == 0:
            continue   # B0 flat; not included in cumulative Kelly
        bucket_target = full_target * cum_map.get(rb, 1.0)
        budget = bucket_target - cum_staked
        if budget < MIN_BUDGET:
            continue
        stake = budget
        ep    = float(t.get("entry_price", 0.8))
        shares = stake / ep
        fee   = stake * FEE_RATE
        if t["_win"]:
            gross = (1.0 - ep) * shares
            net   = gross - fee
        else:
            gross = -stake
            net   = gross - fee
        net_pnl    += net
        cum_staked  = bucket_target   # top up to this level

    return net_pnl

# Collect window EVs per config
configs = []
for b3 in [round(x*0.05,2) for x in range(10,21)]:   # 0.50..1.00
    for b2 in [round(x*0.05,2) for x in range(10,21)]:
        if b2 < b3: continue
        configs.append((b3, b2))

results = {}
for b3, b2 in configs:
    total_ev = 0.0
    n_windows = 0
    for key, wt in windows.items():
        ev = simulate_window_ev(wt, b3, b2)
        total_ev += ev
        n_windows += 1
    results[(b3, b2)] = (total_ev, n_windows)

# Current config
cur_b3, cur_b2 = 0.90, 0.95
cur_ev, cur_n = results[(cur_b3, cur_b2)]
print(f"\n  Current config (B3=0.90, B2=0.95): EV=${cur_ev:.2f}  over {cur_n} windows")

# Best config
best = max(results, key=lambda k: results[k][0])
best_ev, best_n = results[best]
print(f"  Best config    (B3={best[0]:.2f}, B2={best[1]:.2f}): EV=${best_ev:.2f}  over {best_n} windows")

# Top 10
print("\n  Top 10 configs by EV:")
for cfg, (ev, n) in sorted(results.items(), key=lambda x: -x[1][0])[:10]:
    marker = " ◄ CURRENT" if cfg == (cur_b3, cur_b2) else (" ◄ BEST" if cfg == best else "")
    print(f"    B3={cfg[0]:.2f} B2={cfg[1]:.2f}  EV=${ev:.2f}{marker}")

# ── Exit reason distribution ──────────────────────────────────────────────────
from collections import Counter
print("\n─── Exit reason distribution (reliable) ─────────────────────")
reasons = Counter(t.get("exit_reason") for t in reliable)
for r, cnt in reasons.most_common():
    pct = cnt/len(reliable)*100
    print(f"  {r or 'None':<30} n={cnt:>5}  ({pct:.1f}%)")

# ── Net PnL over time (daily) ─────────────────────────────────────────────────
from datetime import datetime, timezone
print("\n─── Daily net PnL (reliable, gated) ─────────────────────────")
daily = defaultdict(float)
daily_n = defaultdict(int)
for t in reliable:
    if not t["_gate"]: continue
    try:
        d = datetime.fromtimestamp(float(t.get("ts_open",0)), tz=timezone.utc).strftime("%Y-%m-%d")
        daily[d] += float(t.get("net_pnl",0))
        daily_n[d] += 1
    except: pass
for d in sorted(daily.keys()):
    print(f"  {d}  n={daily_n[d]:>4}  net=${daily[d]:>8.2f}")

print("\n═══════════════════════════════════════════════════════════")
print("  UNKNOWNS SUMMARY")
print("═══════════════════════════════════════════════════════════")

# BNC zero (can't tier these)
no_bnc = [t for t in reliable if t["_gate"] and t["_bnc_abs"] == 0.0]
print(f"\n  Trades with BNC=0 (untiereable): {len(no_bnc)} ({len(no_bnc)/max(ng,1)*100:.1f}% of gated)")

# B0 volume
b0 = [t for t in reliable if t["_rb"]==0]
print(f"  B0 trades (<60s): {len(b0)} — excluded from Kelly analysis")

# B3 volume
b3_all = [t for t in reliable if t["_rb"]==3]
b3_gated = [t for t in b3_all if t["_gate"]]
print(f"  B3 live trades: {len(b3_all)} total, {len(b3_gated)} gated — key for 90/95 weight decision")

# Hours with 5≤n<20 (trend only, no action)
print(f"\n  Hours in flag zone (5≤n<20, gated):")
for h in sorted(hour_data.keys()):
    sub = hour_data[h]
    if 5 <= len(sub) < 20:
        n,w,net,stk = stats(sub)
        wr = w/n*100
        print(f"    H{h:02d}  n={n}  WR={wr:.0f}%  net=${net:.2f}")

if __name__ == "__main__":
    pass
