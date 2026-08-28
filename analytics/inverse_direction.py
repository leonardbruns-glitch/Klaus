"""
Counterfactual: what if every BOND trade had ONLY two exits?
  (1) TP at price ≥ 0.99
  (2) Time exit at window_end (no SL, no stage-1, no trailing)

Applied to both YES (as bot traded) and NO (opposite direction).

Data approximation:
- We don't have full price time-series per trade, so we infer whether
  price hit 0.99 from two data points: the bot's exit price (xp) and
  the window_outcome_price (from post_exit.jsonl resolution record).
- If max(xp, window_outcome_price) >= 0.99 → YES hit TP
- If min(xp, window_outcome_price) <= 0.01 → NO hit TP (equivalent to YES ≤ 0.01)
- Otherwise → time exit at window_outcome_price (or xp as fallback)

This is a best-case simulation — assumes TP fires the moment 0.99 is reached
and that we don't miss it during the window. In practice there may be
slippage / liquidity issues at extreme prices.

Run:
    cd /root/Klaus && python3 analytics/inverse_direction.py [--since "YYYY-MM-DD HH:MM"]
"""
from __future__ import annotations
import json, os, sys, datetime

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_ROOT, "logs", "trades.jsonl")
POST_PATH   = os.path.join(_ROOT, "logs", "post_exit.jsonl")

# ── --since filter ───────────────────────────────────────────────────────────
_since_ts = 0.0
for i, a in enumerate(sys.argv[1:]):
    if a == "--since" and i + 1 < len(sys.argv) - 1:
        try:
            _since_ts = datetime.datetime.strptime(
                sys.argv[i + 2], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            pass

# ── Load trades and post_exit resolution records ─────────────────────────────
with open(TRADES_PATH) as f:
    all_trades = [json.loads(l) for l in f if l.strip()]

resolution: dict[str, float] = {}
if os.path.exists(POST_PATH):
    with open(POST_PATH) as f:
        for l in f:
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get("record_type") == "resolution" and r.get("trade_id"):
                wop = r.get("window_outcome_price")
                if wop is not None:
                    resolution[r["trade_id"]] = float(wop)

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

# ── Fee approximation (symmetric around 0.50) ────────────────────────────────
# Polymarket: extreme_fee_rate=0.005 when p<0.35 or p>0.65; middle_fee_rate=0.018.
# fee = stake * feeRate * p*(1-p) * 4  (approx round-trip)
# Simpler: use observed YES fee/stake bleed and mirror it to NO based on price zone.
EXTREME_LOW, EXTREME_HIGH = 0.35, 0.65
def _rt_fee_rate(p: float) -> float:
    """Approximate round-trip fee rate for entering/exiting at price p."""
    if p <= 0.01 or p >= 0.99:
        return 0.005
    # Peak ~3.1% at 0.50 for middle-zone; ~1% at 0.35; ~0.5% at extremes.
    if p < EXTREME_LOW or p > EXTREME_HIGH:
        return 0.010
    # middle zone scales with p*(1-p)
    return 0.018 + 0.012 * (1 - abs(p - 0.5) * 2)   # simple bell-ish shape

# ── Simulate TP@0.99-or-time-exit strategy ────────────────────────────────────
def _sim_yes(t: dict) -> tuple[float, float, bool]:
    """Return (gross, fees, hit_tp)."""
    ep    = float(t["entry_price"])
    xp    = float(t["exit_price"])
    stake = float(t["stake"])
    wop   = resolution.get(t.get("trade_id", ""), None)
    # Did YES price ever reach 0.99?
    hi = max(xp, wop) if wop is not None else xp
    if hi >= 0.99:
        exit_price = 0.99
    elif wop is not None:
        exit_price = wop   # time exit: price at window_end
    else:
        exit_price = xp    # fallback
    gross = stake * (exit_price - ep) / ep
    # Fees: entry at ep, exit at exit_price
    fees = stake * (_rt_fee_rate(ep) / 2 + _rt_fee_rate(exit_price) / 2)
    return gross, fees, (hi >= 0.99)

def _sim_no(t: dict) -> tuple[float, float, bool]:
    ep    = float(t["entry_price"])
    xp    = float(t["exit_price"])
    stake = float(t["stake"])
    wop   = resolution.get(t.get("trade_id", ""), None)
    no_entry = 1 - ep
    no_xp    = 1 - xp
    no_wop   = (1 - wop) if wop is not None else None
    # NO hits 0.99 when YES hits ≤ 0.01
    hi_no = max(no_xp, no_wop) if no_wop is not None else no_xp
    if hi_no >= 0.99:
        exit_price = 0.99
    elif no_wop is not None:
        exit_price = no_wop
    else:
        exit_price = no_xp
    gross = stake * (exit_price - no_entry) / no_entry
    fees  = stake * (_rt_fee_rate(no_entry) / 2 + _rt_fee_rate(exit_price) / 2)
    return gross, fees, (hi_no >= 0.99)

# ── Aggregate ────────────────────────────────────────────────────────────────
yes_grosses, yes_fees_all, yes_tps = [], [], 0
no_grosses,  no_fees_all,  no_tps  = [], [], 0
has_resolution = 0
per_trade = []
for t in trades:
    if t.get("trade_id") in resolution:
        has_resolution += 1
    yg, yf, ytp = _sim_yes(t)
    ng, nf, ntp = _sim_no(t)
    yes_grosses.append(yg); yes_fees_all.append(yf); yes_tps += int(ytp)
    no_grosses.append(ng);  no_fees_all.append(nf);  no_tps  += int(ntp)
    per_trade.append((t, yg - yf, ng - nf))

yes_gross = sum(yes_grosses); yes_fees = sum(yes_fees_all); yes_net = yes_gross - yes_fees
no_gross  = sum(no_grosses);  no_fees  = sum(no_fees_all);  no_net  = no_gross - no_fees
yes_wins = sum(1 for g, f in zip(yes_grosses, yes_fees_all) if (g - f) > 0)
no_wins  = sum(1 for g, f in zip(no_grosses, no_fees_all)  if (g - f) > 0)

# Actual YES results for comparison
actual_yes_net = sum(float(t.get("net_pnl", 0) or 0) for t in trades)
actual_yes_wins = sum(1 for t in trades if float(t.get("net_pnl", 0) or 0) > 0)

avg_ep = sum(float(t["entry_price"]) for t in trades) / len(trades)

# ── Print ────────────────────────────────────────────────────────────────────
print("=" * 78)
print("COUNTERFACTUAL: TP@0.99 or TIME_EXIT only (no SL, no stage-1, no trailing)")
print(f"n={len(trades)}  avg_entry_price={avg_ep:.4f}  "
      f"trades_with_resolution_data={has_resolution}/{len(trades)}")
print("=" * 78)
print()
print("── ACTUAL (bot as-is, with SL/TP/trailing) ──────────────────────────")
print(f"  wins={actual_yes_wins}/{len(trades)}  WR={actual_yes_wins/len(trades)*100:.1f}%")
print(f"  net_pnl = {actual_yes_net:+.2f}")
print()
print("── SIMULATED YES side, TP@0.99-or-time_exit ─────────────────────────")
print(f"  wins={yes_wins}/{len(trades)}  WR={yes_wins/len(trades)*100:.1f}%")
print(f"  TP_hits = {yes_tps}/{len(trades)}  "
      f"time_exits = {len(trades) - yes_tps}/{len(trades)}")
print(f"  gross   = {yes_gross:+.2f}")
print(f"  fees    = -{yes_fees:.2f}")
print(f"  net     = {yes_net:+.2f}")
print()
print("── SIMULATED NO side, TP@0.99-or-time_exit ──────────────────────────")
print(f"  wins={no_wins}/{len(trades)}  WR={no_wins/len(trades)*100:.1f}%")
print(f"  TP_hits = {no_tps}/{len(trades)}  "
      f"time_exits = {len(trades) - no_tps}/{len(trades)}")
print(f"  gross   = {no_gross:+.2f}")
print(f"  fees    = -{no_fees:.2f}")
print(f"  net     = {no_net:+.2f}")
print()
print("── COMPARISON ───────────────────────────────────────────────────────")
print(f"  YES actual            → {actual_yes_net:+.2f}")
print(f"  YES simulated (no SL) → {yes_net:+.2f}   Δ={yes_net - actual_yes_net:+.2f}")
print(f"  NO simulated (no SL)  → {no_net:+.2f}   Δ={no_net - actual_yes_net:+.2f}")
print()
print("── TOP SIMULATED NO WINS ────────────────────────────────────────────")
per_trade.sort(key=lambda x: -x[2])
print(f"  {'time':<17} {'asset':<4} {'ep':>6} {'xp':>6} {'wop':>7} "
      f"{'stake':>7} {'YES_net':>8} {'NO_net':>8}")
for t, ynet, nnet in per_trade[:7]:
    ts = datetime.datetime.fromtimestamp(t.get("ts_open", 0), tz=datetime.timezone.utc)
    wop = resolution.get(t.get("trade_id", ""), None)
    wop_s = f"{wop:.4f}" if wop is not None else "—"
    print(f"  {ts.strftime('%m-%d %H:%M:%S'):<17} "
          f"{t.get('asset', '?'):<4} "
          f"{float(t['entry_price']):>6.4f} "
          f"{float(t['exit_price']):>6.4f} "
          f"{wop_s:>7} "
          f"{float(t['stake']):>7.2f} "
          f"{ynet:>+8.2f} "
          f"{nnet:>+8.2f}")
print()
print("── BOTTOM SIMULATED NO LOSSES ───────────────────────────────────────")
print(f"  {'time':<17} {'asset':<4} {'ep':>6} {'xp':>6} {'wop':>7} "
      f"{'stake':>7} {'YES_net':>8} {'NO_net':>8}")
for t, ynet, nnet in per_trade[-7:]:
    ts = datetime.datetime.fromtimestamp(t.get("ts_open", 0), tz=datetime.timezone.utc)
    wop = resolution.get(t.get("trade_id", ""), None)
    wop_s = f"{wop:.4f}" if wop is not None else "—"
    print(f"  {ts.strftime('%m-%d %H:%M:%S'):<17} "
          f"{t.get('asset', '?'):<4} "
          f"{float(t['entry_price']):>6.4f} "
          f"{float(t['exit_price']):>6.4f} "
          f"{wop_s:>7} "
          f"{float(t['stake']):>7.2f} "
          f"{ynet:>+8.2f} "
          f"{nnet:>+8.2f}")
print()
print("── CAVEATS ──────────────────────────────────────────────────────────")
print("  (1) Trades missing post_exit resolution record fall back to using xp")
print("      as the time_exit price. This is usually WORSE than reality for")
print("      SL-exited trades that bounced by window_end.")
print("  (2) TP detection is a 2-point heuristic (xp OR window_outcome_price).")
print("      If price touched 0.99 MID-window then decayed, we miss the TP.")
print("  (3) Fees are approximated from the middle/extreme rate formula —")
print("      actual fees may vary by 10-20% from this estimate.")
print("  (4) No slippage modeled. Real 0.99 fills have thin liquidity.")
print("=" * 78)
