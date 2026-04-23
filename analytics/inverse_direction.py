"""
Counterfactual: what if every trade was flipped to the OPPOSITE side?

For each YES trade at (ep → xp), compute the NO-side PnL that would have
resulted from buying NO at (1-ep) and selling at (1-xp). Assumes symmetric
YES+NO=1.0 pricing and ignores fee differences between the two sides
(fee formula is symmetric around 0.50 so this is a reasonable first-order
approximation).

Key formula:
    NO_gross = stake * (ep - xp) / (1 - ep)

Run:
    cd /root/Klaus && python3 analytics/inverse_direction.py [--since "YYYY-MM-DD HH:MM"]
"""
from __future__ import annotations
import json, os, sys, datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_ROOT, "logs", "trades.jsonl")

# ── --since filter (same interface as trade_report.py) ───────────────────────
_since_ts = 0.0
for i, a in enumerate(sys.argv[1:]):
    if a == "--since" and i + 1 < len(sys.argv) - 1:
        try:
            _since_ts = datetime.datetime.strptime(
                sys.argv[i + 2], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            pass

with open(TRADES_PATH) as f:
    all_trades = [json.loads(l) for l in f if l.strip()]

trades = [
    t for t in all_trades
    if (t.get("ts_open", 0) or 0) >= _since_ts
    and t.get("signal_source") == "BOND"
    and t.get("dry_run") is not True
    and (t.get("stake", 0) or 0) > 0
    and (t.get("entry_price", 0) or 0) > 0
    and (t.get("exit_price", 0) or 0) > 0
]

if not trades:
    print("no trades match filter")
    sys.exit(0)

def _no_gross(t: dict) -> float:
    ep = float(t["entry_price"])
    xp = float(t["exit_price"])
    stake = float(t["stake"])
    if ep >= 0.99 or ep <= 0.01:
        return 0.0
    return stake * (ep - xp) / (1 - ep)

def _yes_gross(t: dict) -> float:
    return float(t.get("gross_pnl", 0) or 0)

# Aggregate
total_yes_gross = sum(_yes_gross(t) for t in trades)
total_yes_net   = sum(float(t.get("net_pnl", 0) or 0) for t in trades)
total_yes_fees  = total_yes_gross - total_yes_net
total_no_gross  = sum(_no_gross(t) for t in trades)
# NO fees: approximate symmetry — fee rate function peaks at 0.50 and is
# symmetric around it, so fees on the opposite side are computed at price (1-p).
# As a first-order proxy, apply the same fee bleed ratio (fee/stake) observed
# on the YES side. This is approximate but consistent enough for direction check.
total_stake = sum(float(t.get("stake", 0) or 0) for t in trades)
fee_bleed_rate = total_yes_fees / total_stake if total_stake else 0
approx_no_fees = total_stake * fee_bleed_rate
total_no_net_est = total_no_gross - approx_no_fees

# Win counts
yes_wins = sum(1 for t in trades if float(t.get("net_pnl", 0) or 0) > 0)
no_wins  = sum(1 for t in trades if _no_gross(t) > 0)

# Avg entry price
avg_ep = sum(float(t["entry_price"]) for t in trades) / len(trades)

print("=" * 78)
print(f"COUNTERFACTUAL: INVERSE DIRECTION (BUY NO INSTEAD OF YES)")
print(f"n={len(trades)}  avg_entry_price={avg_ep:.4f}")
print("=" * 78)
print()
print("── ACTUAL (YES side — what the bot traded) ─────────────────────────")
print(f"  wins={yes_wins}/{len(trades)}  WR={yes_wins/len(trades)*100:.1f}%")
print(f"  gross_pnl  = {total_yes_gross:+.2f}")
print(f"  fees       = {total_yes_fees:+.2f}")
print(f"  net_pnl    = {total_yes_net:+.2f}")
print()
print("── COUNTERFACTUAL (NO side — opposite direction) ───────────────────")
print(f"  wins={no_wins}/{len(trades)}  WR={no_wins/len(trades)*100:.1f}%")
print(f"  gross_pnl  = {total_no_gross:+.2f}")
print(f"  fees (est) = {approx_no_fees:+.2f}  (symmetric fee bleed proxy)")
print(f"  net_pnl    = {total_no_net_est:+.2f}")
print()
print("── WHY NOT A SIMPLE FLIP ────────────────────────────────────────────")
print(f"  avg entry price = {avg_ep:.3f} → NO avg entry = {1-avg_ep:.3f}")
print(f"  Asymmetry: when YES wins (token→1.0), NO loses ALL stake (-100%).")
print(f"  When YES loses (token→0.0), NO gains only (1/(1-ep) - 1) × stake.")
print(f"  At ep=0.61, NO max upside per loss = +56% vs NO max loss = -100%.")
print(f"  Low YES WR does NOT mean high NO profit — NO has asymmetric loss tail.")
print()

# Per-trade breakdown (top gainers/losers on NO side)
print("── TOP 10 TRADES BY NO-SIDE PNL ─────────────────────────────────────")
trades_with_no = [(t, _no_gross(t)) for t in trades]
trades_with_no.sort(key=lambda x: -x[1])
print(f"  {'time':<17} {'asset':<4} {'ep':>6} {'xp':>6} {'stake':>7} {'YES_net':>9} {'NO_gross':>9}")
print(f"  {'-'*17} {'-'*4} {'-'*6} {'-'*6} {'-'*7} {'-'*9} {'-'*9}")
top5 = trades_with_no[:5]
bot5 = trades_with_no[-5:]
for t, no_g in top5 + bot5:
    ts = datetime.datetime.fromtimestamp(t.get("ts_open", 0), tz=datetime.timezone.utc)
    print(f"  {ts.strftime('%m-%d %H:%M:%S'):<17} "
          f"{t.get('asset', '?'):<4} "
          f"{float(t['entry_price']):>6.4f} "
          f"{float(t['exit_price']):>6.4f} "
          f"{float(t['stake']):>7.2f} "
          f"{float(t.get('net_pnl', 0) or 0):>+9.2f} "
          f"{no_g:>+9.2f}")
print()
print("  Note: NO-side winners come from big YES losers (xp << ep).")
print("  NO-side losers come from big YES winners (xp >> ep).")
print("=" * 78)
