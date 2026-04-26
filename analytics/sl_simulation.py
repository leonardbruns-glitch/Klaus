"""
Stop-loss simulation across BOND trades.
Run on VPS: python3 analytics/sl_simulation.py

Uses max_adverse_pct (MAE) to determine if each SL threshold would have fired.
"""
import json, os
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(__file__), "../logs/trades.jsonl")

# ── Filter: April 25 08:00 UTC onwards ───────────────────────────────────────
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
    and t.get("exit_reason") not in ("BOND_EXPIRED_UNSOLD",)  # exclude no-exit trades
    and t.get("max_adverse_pct", 100) < 99.0  # exclude sentinel / no MAE data
]

print(f"\nFiltered from: 2026-04-25 08:00 UTC")
print(f"Total trades in file: {len(trades)}")
print(f"BOND trades with MAE data in window: {len(bond)}")

if not bond:
    # Diagnose why
    all_bond = [t for t in trades if t.get("is_bond") or t.get("signal_source") == "BOND"]
    recent = [t for t in all_bond if t.get("ts_open", 0) >= CUTOFF]
    print(f"\nDiagnosis:")
    print(f"  All BOND in file: {len(all_bond)}")
    print(f"  BOND after cutoff: {len(recent)}")
    if recent:
        s = recent[0]
        print(f"  Sample: ts_open={s.get('ts_open')} max_adverse_pct={s.get('max_adverse_pct')} exit_reason={s.get('exit_reason')}")
    # Try with looser filter
    loose = [t for t in all_bond if t.get("ts_open", 0) >= CUTOFF]
    print(f"\n  Dropping MAE filter: n={len(loose)}")
    if loose:
        mae_vals = [t.get("max_adverse_pct") for t in loose[:10]]
        print(f"  max_adverse_pct sample: {mae_vals}")
    exit()

winners = [t for t in bond if t.get("net_pnl", 0) > 0]
losers  = [t for t in bond if t.get("net_pnl", 0) <= 0]

print(f"\nn={len(bond)}  W={len(winners)}(mae={sum(1 for t in winners if t.get('max_adverse_pct',0) > 0)})  "
      f"L={len(losers)}(mae={sum(1 for t in losers if t.get('max_adverse_pct',0) > 0)})")

total_w_pnl = sum(t.get("net_pnl", 0) for t in winners)
total_l_pnl = sum(t.get("net_pnl", 0) for t in losers)
print(f"No-SL baseline: wins=${total_w_pnl:+.2f}  losses=${total_l_pnl:+.2f}  net=${total_w_pnl+total_l_pnl:+.2f}")

SL_LEVELS = [5, 8, 10, 12, 15, 20, 25, 30, 35, 40]

print(f"\n{'SL%':<6} {'cut_W':<6} {'cut_W%':<8} {'pnl_lost':<14} | {'cut_L':<6} {'cut_L%':<8} {'pnl_saved':<14} {'NET_BENEFIT'}")
print("-" * 95)

for sl in SL_LEVELS:
    cut_w = [t for t in winners if t.get("max_adverse_pct", 0) >= sl]
    cut_l = [t for t in losers  if t.get("max_adverse_pct", 0) >= sl]

    # pnl_lost: actual profit earned on cut winners (now lost due to SL)
    pnl_lost = sum(t.get("net_pnl", 0) for t in cut_w)

    # pnl_saved: for each cut loser, we exit at -SL% instead of actual loss
    # savings = actual_loss - SL_exit_loss = |net_pnl| - (sl/100 * stake)
    pnl_saved = 0.0
    for t in cut_l:
        stake = t.get("stake", t.get("entry_price", 0) * t.get("shares", 0))
        sl_exit_loss = (sl / 100.0) * stake
        actual_loss  = abs(t.get("net_pnl", 0))
        pnl_saved += max(0.0, actual_loss - sl_exit_loss)

    net = pnl_saved - pnl_lost
    cut_w_pct = len(cut_w) / len(winners) * 100 if winners else 0
    cut_l_pct = len(cut_l) / len(losers)  * 100 if losers  else 0

    print(f"{sl:<6}% {len(cut_w):<6} {cut_w_pct:<8.1f}% ${pnl_lost:<12.2f}  | "
          f"{len(cut_l):<6} {cut_l_pct:<8.1f}% ${pnl_saved:<12.2f}  {net:+.2f}")

print()

# Also break down by asset
for asset in ["BTC", "ETH", "SOL"]:
    sub = [t for t in bond if t.get("asset") == asset]
    if len(sub) < 5:
        continue
    w = [t for t in sub if t.get("net_pnl", 0) > 0]
    l = [t for t in sub if t.get("net_pnl", 0) <= 0]
    print(f"\n{asset}: n={len(sub)} W={len(w)} L={len(l)}  net=${sum(t.get('net_pnl',0) for t in sub):+.2f}")
    print(f"  {'SL%':<6} {'cut_W%':<8} {'pnl_lost':<12} | {'cut_L%':<8} {'pnl_saved':<12} {'NET'}")
    for sl in [10, 15, 20, 25, 30, 40]:
        cw = [t for t in w if t.get("max_adverse_pct", 0) >= sl]
        cl = [t for t in l if t.get("max_adverse_pct", 0) >= sl]
        pl = sum(t.get("net_pnl", 0) for t in cw)
        ps = sum(max(0, abs(t.get("net_pnl",0)) - (sl/100)*t.get("stake",0)) for t in cl)
        net = ps - pl
        print(f"  {sl:<6}% {len(cw)/len(w)*100 if w else 0:<8.1f}% ${pl:<10.2f}  | "
              f"{len(cl)/len(l)*100 if l else 0:<8.1f}% ${ps:<10.2f}  {net:+.2f}")
