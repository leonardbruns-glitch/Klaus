"""
Stop-loss simulation across BOND trades.
Run on VPS: python3 analytics/sl_simulation.py

Key question: do the "losers" the SL catches actually resolve NO at window end,
or do they recover? If they recover, the SL is killing good trades.
"""
import json, os, collections
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(__file__), "../logs/trades.jsonl")
CUTOFF = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc).timestamp()

trades = []
with open(LOG) as f:
    for line in f:
        try:
            trades.append(json.loads(line))
        except Exception:
            pass

bond = [
    t for t in trades
    if (t.get("is_bond") or t.get("signal_source") == "BOND")
    and t.get("ts_open", 0) >= CUTOFF
    and t.get("entry_price", 0) > 0
    and t.get("exit_reason") not in ("BOND_EXPIRED_UNSOLD",)
    and t.get("max_adverse_pct", 100) < 99.0
]

winners = [t for t in bond if t.get("net_pnl", 0) > 0]
losers  = [t for t in bond if t.get("net_pnl", 0) <= 0]

print(f"Filtered from: 2026-04-25 08:00 UTC")
print(f"n={len(bond)}  W={len(winners)}  L={len(losers)}")
print(f"No-SL net: ${sum(t.get('net_pnl',0) for t in bond):+.2f}\n")

# ── window_outcome_price availability ────────────────────────────────────────
has_outcome = [t for t in bond if t.get("window_outcome_price", 0) > 0]
print(f"Trades with window_outcome_price populated: {len(has_outcome)} / {len(bond)}")
if has_outcome:
    sample = has_outcome[0]
    print(f"  Sample: exit_reason={sample.get('exit_reason')} "
          f"net_pnl={sample.get('net_pnl'):.2f} "
          f"window_outcome_price={sample.get('window_outcome_price')}")
print()

# ── For each SL threshold: break down the loser bucket by window outcome ─────
SL_LEVELS = [10, 15, 20, 25, 30, 40]

print("=== LOSER BUCKET RECOVERY ANALYSIS ===")
print("For each SL%, of the losers that would be cut:")
print("  YES = market resolved FOR us (SL killed a good trade)")
print("  NO  = market resolved against us (SL correctly protected)")
print("  ??  = window_outcome_price not populated\n")

for sl in SL_LEVELS:
    cut_l = [t for t in losers if t.get("max_adverse_pct", 0) >= sl]
    if not cut_l:
        continue

    resolved_yes = [t for t in cut_l if t.get("window_outcome_price", 0) >= 0.90]
    resolved_no  = [t for t in cut_l if 0 < t.get("window_outcome_price", 0) < 0.20]
    unknown      = [t for t in cut_l if t.get("window_outcome_price", 0) == 0]

    pnl_yes = sum(t.get("net_pnl", 0) for t in resolved_yes)
    pnl_no  = sum(t.get("net_pnl", 0) for t in resolved_no)
    pnl_unk = sum(t.get("net_pnl", 0) for t in unknown)

    print(f"SL={sl:2d}%  cut_L={len(cut_l):3d} | "
          f"YES(recovered)={len(resolved_yes):3d} ${pnl_yes:+.2f}  "
          f"NO(genuine)={len(resolved_no):3d} ${pnl_no:+.2f}  "
          f"??={len(unknown):3d} ${pnl_unk:+.2f}")

print()

# ── EXIT REASON of the loser bucket at SL=15% ────────────────────────────────
print("=== EXIT REASONS of losers with MAE >= 15% ===")
cut_l_15 = [t for t in losers if t.get("max_adverse_pct", 0) >= 15]
for reason, cnt in collections.Counter(t.get("exit_reason") for t in cut_l_15).most_common():
    sub = [t for t in cut_l_15 if t.get("exit_reason") == reason]
    pnl = sum(t.get("net_pnl", 0) for t in sub)
    outcome_prices = [t.get("window_outcome_price", 0) for t in sub]
    yes_count = sum(1 for p in outcome_prices if p >= 0.90)
    print(f"  {str(reason):<35s} n={cnt:3d}  pnl=${pnl:+.2f}  resolved_YES={yes_count}")

print()

# ── Use exit_price as proxy if window_outcome_price missing ──────────────────
# For TIME_EXIT and DEADLINE: exit is at T-1s to T-3s before resolution.
# If exit_price >= 0.90 → market was already pricing YES → trade was "good"
# If exit_price <= 0.20 → market was pricing NO → SL would have been correct
print("=== EXIT PRICE DISTRIBUTION for losers with MAE >= 15% (proxy for resolution) ===")
cut_l_15 = [t for t in losers if t.get("max_adverse_pct", 0) >= 15]
ep = [t.get("exit_price", 0) for t in cut_l_15 if t.get("exit_price", 0) > 0]
if ep:
    buckets = [
        (">=0.90 (resolving YES)", [p for p in ep if p >= 0.90]),
        ("0.75-0.90 (uncertain-high)", [p for p in ep if 0.75 <= p < 0.90]),
        ("0.50-0.75 (uncertain)", [p for p in ep if 0.50 <= p < 0.75]),
        ("0.20-0.50 (leaning NO)", [p for p in ep if 0.20 <= p < 0.50]),
        ("<0.20 (resolving NO)", [p for p in ep if p < 0.20]),
    ]
    for label, vals in buckets:
        n = len(vals)
        pct = n / len(ep) * 100
        print(f"  {label:<30s}: n={n:3d} ({pct:4.1f}%)")
    print(f"  (n with exit_price data: {len(ep)} / {len(cut_l_15)})")
else:
    print("  No exit_price data available")

print()

# ── Full SL table for reference ───────────────────────────────────────────────
print("=== FULL SL SIMULATION (for reference) ===")
print(f"{'SL%':<5} {'cut_W':<6} {'cut_W%':<8} {'pnl_lost':<12} | {'cut_L':<6} {'cut_L%':<8} {'pnl_saved':<12} {'NET'}")
print("-" * 80)
for sl in [5, 8, 10, 12, 15, 20, 25, 30, 35, 40]:
    cut_w = [t for t in winners if t.get("max_adverse_pct", 0) >= sl]
    cut_l = [t for t in losers  if t.get("max_adverse_pct", 0) >= sl]
    pl = sum(t.get("net_pnl", 0) for t in cut_w)
    ps = sum(max(0, abs(t.get("net_pnl",0)) - (sl/100)*t.get("stake",0)) for t in cut_l)
    net = ps - pl
    print(f"{sl:<5}% {len(cut_w):<6} {len(cut_w)/len(winners)*100:<8.1f}% ${pl:<10.2f}  | "
          f"{len(cut_l):<6} {len(cut_l)/len(losers)*100:<8.1f}% ${ps:<10.2f}  {net:+.2f}")
print()
