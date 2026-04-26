"""
Stop-loss simulation across BOND trades.
Run on VPS: python3 analytics/sl_simulation.py

Joins trades.jsonl with post_exit.jsonl (resolution records) to answer:
do the "losers" the SL catches actually resolve NO, or do they recover?
"""
import json, os, collections
from datetime import datetime, timezone

LOGS = os.path.join(os.path.dirname(__file__), "../logs")
CUTOFF = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc).timestamp()

# ── Load trades ───────────────────────────────────────────────────────────────
trades = []
with open(os.path.join(LOGS, "trades.jsonl")) as f:
    for line in f:
        try: trades.append(json.loads(line))
        except Exception: pass

# ── Load resolution outcomes from post_exit.jsonl ────────────────────────────
resolution = {}  # trade_id → {window_outcome_price, entered_correctly, window_max_fav_from_entry_pct}
post_exit_path = os.path.join(LOGS, "post_exit.jsonl")
n_res = 0
if os.path.exists(post_exit_path):
    with open(post_exit_path) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("record_type") == "resolution" and r.get("trade_id"):
                    resolution[r["trade_id"]] = r
                    n_res += 1
            except Exception: pass

print(f"Trades in file: {len(trades)}")
print(f"Resolution records in post_exit.jsonl: {n_res}")

# ── Filter BOND trades from cutoff ────────────────────────────────────────────
bond = [
    t for t in trades
    if (t.get("is_bond") or t.get("signal_source") == "BOND")
    and t.get("ts_open", 0) >= CUTOFF
    and t.get("entry_price", 0) > 0
    and t.get("exit_reason") not in ("BOND_EXPIRED_UNSOLD",)
    and t.get("max_adverse_pct", 100) < 99.0
]

# Attach resolution data
for t in bond:
    res = resolution.get(t.get("trade_id", ""))
    if res:
        t["_wop"] = res.get("window_outcome_price", 0)
        t["_entered_correctly"] = res.get("entered_correctly")
        t["_max_fav"] = res.get("window_max_fav_from_entry_pct", 0)
    else:
        t["_wop"] = 0
        t["_entered_correctly"] = None
        t["_max_fav"] = 0

matched = sum(1 for t in bond if t["_wop"] > 0)
print(f"BOND trades (Apr25+, with MAE): {len(bond)}  matched to resolution: {matched}\n")

winners = [t for t in bond if t.get("net_pnl", 0) > 0]
losers  = [t for t in bond if t.get("net_pnl", 0) <= 0]

print(f"n={len(bond)}  W={len(winners)}  L={len(losers)}")
print(f"No-SL net: ${sum(t.get('net_pnl',0) for t in bond):+.2f}\n")

# ── Core question: do losers with MAE >= SL% recover at window end? ──────────
print("=== KEY QUESTION: do caught losers recover? ===")
print(f"{'SL%':<5}  {'cut_L':<7} {'wop_YES':<10} {'wop_NO':<10} {'wop_??':<8}  {'if_held_EV':>12}")
print("-" * 65)

for sl in [10, 15, 20, 25, 30, 40]:
    cut_l = [t for t in losers if t.get("max_adverse_pct", 0) >= sl]
    if not cut_l:
        continue

    yes = [t for t in cut_l if t["_wop"] >= 0.80]   # resolved YES
    no  = [t for t in cut_l if 0 < t["_wop"] < 0.20]  # resolved NO
    unk = [t for t in cut_l if t["_wop"] == 0]

    # EV if held: YES → avg win from entry, NO → full stake loss
    avg_entry = sum(t.get("entry_price", 0.84) for t in cut_l) / len(cut_l)
    avg_stake = sum(t.get("stake", 4.5) for t in cut_l) / len(cut_l)
    if yes or no:
        p_yes = len(yes) / (len(yes) + len(no))
        avg_win  = avg_stake * (1.0 - avg_entry) / avg_entry  # pnl if held to 1.0
        avg_loss = -avg_stake                                   # pnl if held to 0.0
        ev = p_yes * avg_win + (1 - p_yes) * avg_loss
        ev_str = f"${ev:+.2f}/trade"
    else:
        ev_str = "?? (no res data)"

    print(f"{sl:<5}%  {len(cut_l):<7} {len(yes):<10} {len(no):<10} {len(unk):<8}  {ev_str:>12}")

print()

# ── For matched trades only: full resolution breakdown ────────────────────────
matched_losers = [t for t in losers if t["_wop"] > 0]
if matched_losers:
    print(f"=== RESOLUTION BREAKDOWN (matched losers only, n={len(matched_losers)}) ===")
    yes_l = [t for t in matched_losers if t["_wop"] >= 0.80]
    no_l  = [t for t in matched_losers if t["_wop"] < 0.20]
    mid_l = [t for t in matched_losers if 0.20 <= t["_wop"] < 0.80]
    print(f"  Resolved YES (wop>=0.80): n={len(yes_l)}  pnl={sum(t.get('net_pnl',0) for t in yes_l):+.2f}")
    print(f"  Uncertain   (0.20-0.80): n={len(mid_l)}  pnl={sum(t.get('net_pnl',0) for t in mid_l):+.2f}")
    print(f"  Resolved NO (wop<0.20):  n={len(no_l)}   pnl={sum(t.get('net_pnl',0) for t in no_l):+.2f}")

    matched_winners = [t for t in winners if t["_wop"] > 0]
    if matched_winners:
        print(f"\n=== RESOLUTION BREAKDOWN (matched winners only, n={len(matched_winners)}) ===")
        yes_w = [t for t in matched_winners if t["_wop"] >= 0.80]
        no_w  = [t for t in matched_winners if t["_wop"] < 0.20]
        print(f"  Resolved YES (wop>=0.80): n={len(yes_w)}")
        print(f"  Resolved NO  (wop<0.20):  n={len(no_w)}")

    print()

# ── Full SL table ─────────────────────────────────────────────────────────────
print("=== FULL SL TABLE ===")
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
