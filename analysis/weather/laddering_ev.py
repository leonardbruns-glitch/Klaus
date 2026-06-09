#!/usr/bin/env python3
"""Empirical test of temperature 'laddering' (buying cheap OTM tail buckets):
does the realized YES hit-rate exceed the price paid? Laddering is +EV only if,
in the cheap-price zone, realized_WR > price + fees. If realized_WR < price
(favorite-longshot bias), the rare 1.0 payoff does NOT cover the losers.

Uses our resolved WEATHER YES trades. exit_price (0/1) = resolution outcome.
Reports realized WR vs implied price per band + ladder EV/share net of fee.
"""
import json, statistics
from collections import defaultdict

FEE = 0.00  # Polymarket weather maker fee ~0; taker ~2% of notional. Report gross + net@2%.

rows = []
for ln in open("logs/trades.jsonl"):
    try: r = json.loads(ln)
    except: continue
    if r.get("asset") != "WEATHER": continue
    if "YES" not in str(r.get("direction", "")): continue
    e = r.get("entry_price"); o = r.get("exit_price")
    if e is None or o is None: continue
    rows.append((float(e), 1.0 if float(o) >= 0.5 else 0.0, r.get("bond_entry_class", "")))

print(f"resolved WEATHER YES trades: n={len(rows)}")

# fine price bands incl. the article's laddering zone 0.02-0.08
bands = [(0.00,0.02),(0.02,0.05),(0.05,0.08),(0.08,0.10),(0.10,0.15),
         (0.15,0.25),(0.25,0.40),(0.40,0.60),(0.60,1.01)]
print(f"\n{'price band':14} {'n':>4} {'avg_price':>9} {'realized_WR':>11} {'edge(WR-price)':>14} {'ladderEV/sh':>11}")
tot_n = tot_cost = tot_payoff = 0.0
for lo, hi in bands:
    sub = [(e,w) for e,w,_ in rows if lo <= e < hi]
    if not sub: continue
    n = len(sub)
    avgp = statistics.mean(e for e,_ in sub)
    wr = statistics.mean(w for _,w in sub)
    # ladder EV per share = P(win)*1 - price  (gross); buyer pays price, gets 1 if win
    ev = wr - avgp
    print(f"[{lo:.2f},{hi:.2f})  {n:>4} {avgp:>9.3f} {wr:>11.1%} {wr-avgp:>+14.3f} {ev:>+11.3f}")
    tot_n += n; tot_cost += sum(e for e,_ in sub); tot_payoff += sum(w for _,w in sub)

print(f"\nALL YES: paid total ${tot_cost:.2f} for {int(tot_payoff)} winners out of {int(tot_n)} "
      f"-> gross EV/share = {(tot_payoff-tot_cost)/tot_n:+.4f}")

# Laddering zone specifically (article: 0.02-0.08)
zone = [(e,w) for e,w,_ in rows if 0.02 <= e < 0.08]
if zone:
    n=len(zone); cost=sum(e for e,_ in zone); win=sum(w for _,w in zone)
    print(f"\n=== ARTICLE LADDERING ZONE (price 0.02-0.08), n={n} ===")
    print(f"  paid ${cost:.2f}, {int(win)} hits, avg_price={cost/n:.3f}, realized_WR={win/n:.1%}")
    print(f"  breakeven_WR = avg_price = {cost/n:.1%}  ->  {'+EV' if win/n>cost/n else 'NEGATIVE EV'}")
    print(f"  gross EV/share = {(win-cost)/n:+.4f};  net@2% taker = {(win-cost)/n - 0.02*cost/n:+.4f}")
    # implied payoff multiple of a winner
    print(f"  a winner pays {1/ (cost/n):.0f}x the avg stake; need 1 win per {1/(cost/n):.0f} bets to break even, "
          f"actual 1 per {n/max(win,1):.0f}")

# any band where market UNDERPRICES (WR > price)?  that's where laddering could live
under = [(lo,hi) for lo,hi in bands
         if (sub:=[(e,w) for e,w,_ in rows if lo<=e<hi]) and statistics.mean(w for _,w in sub) > statistics.mean(e for e,_ in sub) + 0.01]
print(f"\nbands where realized_WR > price+1% (underpriced, ladderable): {under or 'NONE'}")
