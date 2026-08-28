#!/usr/bin/env python3
"""Reconstruct real-bid trajectories of held WEATHER BUY_YES positions from
bot.log POSITION snapshots (curr = top-of-book BID, main.py:1021) and test
whether an intraday exit at the real bid beats hold-to-resolution.

Position-instance key = (entry_price, open_ts) where open_ts = ts - hold is
constant per position. Exit fills use the BID (we cross to sell), entry cost
is entry_price (the ask we paid). PnL is per-share: exit_bid - entry_price.
"""
import re, glob, statistics
from collections import defaultdict

LINE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*POSITION [▲▼] WEATHER (BUY_YES|BUY_NO) \| "
    r"entry=([\d.]+) curr=([\d.]+) move=([+\-][\d.]+)% \| PnL=([+\-])\$([\d.]+) \| "
    r"TP=[\d.]+ SL=[\d.]+ \| hold=(\d+)s")

import datetime
def parse():
    inst = defaultdict(list)  # key -> list[(hold, bid)]
    for fn in sorted(glob.glob("logs/bot.log*")):
        for ln in open(fn, errors="ignore"):
            if "POSITION" not in ln or "WEATHER BUY_YES" not in ln:
                continue
            m = LINE.match(ln)
            if not m:
                continue
            tstr, side, entry, curr, mv, sgn, pnl, hold = m.groups()
            ts = datetime.datetime.strptime(tstr, "%Y-%m-%d %H:%M:%S").timestamp()
            entry = float(entry); bid = float(curr); hold = int(hold)
            open_ts = round(ts - hold, -1)  # constant per instance (round 10s)
            inst[(round(entry, 4), open_ts)].append((hold, bid))
    return inst

def main():
    inst = parse()
    rows = []
    for (entry, open_ts), pts in inst.items():
        pts.sort()
        bids = [b for _, b in pts]
        holds = [h for h, _ in pts]
        peak = max(bids)
        terminal = bids[-1]
        # time of peak
        t_peak = next(h for h, b in pts if b == peak)
        max_hold = holds[-1]
        # resolved? last bid pinned to 0 or 1, and we observed a long hold
        resolved = terminal <= 0.02 or terminal >= 0.97
        won = terminal >= 0.97
        rows.append(dict(entry=entry, peak=peak, terminal=terminal, t_peak=t_peak,
                         max_hold=max_hold, n=len(pts), resolved=resolved, won=won,
                         peak_mult=peak/entry if entry else 0, path=bids))
    print(f"reconstructed YES position-instances: {len(rows)}")
    res = [r for r in rows if r["resolved"]]
    print(f"  resolved (terminal pinned 0/1): {len(res)}  | open/censored: {len(rows)-len(res)}")
    if not res:
        return

    # ---- spike characterisation (all instances with a real path) ----
    have_bid = [r for r in rows if r["peak"] > 0]
    no_bid   = [r for r in rows if r["peak"] == 0]
    print(f"\nSELLABLE-BID CHECK: {len(no_bid)}/{len(rows)} instances NEVER had a positive bid "
          f"(can't exit at any price); {len(have_bid)} had some bid.")
    spiked = [r for r in have_bid if r["peak_mult"] >= 1.5]
    print(f"  instances whose bid spiked >=1.5x entry: {len(spiked)}/{len(have_bid)}")
    if spiked:
        print(f"  of those, median peak_mult={statistics.median(r['peak_mult'] for r in spiked):.2f}x, "
              f"median t_peak={statistics.median(r['t_peak'] for r in spiked)/3600:.1f}h into hold")

    # ---- exit-rule simulation on RESOLVED instances, per-share PnL ----
    # entry cost = entry (ask paid); exit fill = bid.
    def sim(rule):
        tot = 0.0; n = 0
        for r in res:
            exit_bid = rule(r)
            tot += (exit_bid - r["entry"]); n += 1
        return tot, tot / n

    rules = {
        "HOLD_TO_RESOLUTION (baseline)": lambda r: 1.0 if r["won"] else 0.0,
        "TP bid>=1.5x entry":  lambda r: min(r["peak"], r["entry"]*1.5) if r["peak"] >= r["entry"]*1.5 else (1.0 if r["won"] else 0.0),
        "TP bid>=2x entry":    lambda r: min(r["peak"], r["entry"]*2.0) if r["peak"] >= r["entry"]*2.0 else (1.0 if r["won"] else 0.0),
        "TP bid>=3x entry":    lambda r: min(r["peak"], r["entry"]*3.0) if r["peak"] >= r["entry"]*3.0 else (1.0 if r["won"] else 0.0),
        "TP bid>=0.50 abs":    lambda r: 0.50 if r["peak"] >= 0.50 else (1.0 if r["won"] else 0.0),
    }
    print(f"\nEXIT-RULE SIM (per-share PnL, real bids, n={len(res)} resolved YES):")
    print(f"  {'rule':32s} {'total/sh':>10s} {'mean/sh':>10s}")
    base_tot = None
    for name, rule in rules.items():
        tot, mean = sim(rule)
        if base_tot is None: base_tot = tot
        print(f"  {name:32s} {tot:>10.3f} {mean:>10.4f}   {'(base)' if name.startswith('HOLD') else f'd={tot-base_tot:+.3f}'}")

    # why TP fails: winners are also spikers. Show winner contribution.
    winners=[r for r in res if r["won"]]
    print(f"\n  winners={len(winners)}/{len(res)}; their hold-to-res payoff sum = "
          f"{sum(1.0-r['entry'] for r in winners):.3f}/sh; "
          f"all winners' peak_mult>=2x? {sum(r['peak_mult']>=2 for r in winners)}/{len(winners)}")

    # ---- TRAILING-STOP sim (causal): ride up, exit when bid falls D% from running peak ----
    def sim_trail(drop):
        tot=0.0
        for r in res:
            rp=0.0; exit_bid=None
            for b in r["path"]:
                rp=max(rp,b)
                # only arm once in profit above entry, then trail
                if rp> r["entry"] and b <= rp*(1-drop):
                    exit_bid=b; break
            if exit_bid is None:
                exit_bid = 1.0 if r["won"] else 0.0   # never triggered -> resolve
            tot += exit_bid - r["entry"]
        return tot, tot/len(res)
    print(f"\nTRAILING-STOP SIM (exit when bid drops D% below running peak, real bids):")
    for d in (0.10,0.20,0.30,0.40,0.50):
        tot,mean=sim_trail(d)
        print(f"  trail {int(d*100):2d}% from peak     total/sh={tot:>8.3f}  mean/sh={mean:>8.4f}  d_vs_hold={tot-base_tot:+.3f}")

    # entry-price stratification of the spike (low-priced YES is the user's case)
    print("\nBY ENTRY-PRICE BAND (resolved):")
    bands = [(0,0.10),(0.10,0.25),(0.25,0.50),(0.50,1.01)]
    for lo,hi in bands:
        sub=[r for r in res if lo<=r["entry"]<hi]
        if not sub: continue
        wr=sum(r["won"] for r in sub)/len(sub)
        spk=sum(r["peak"]>=r["entry"]*2 for r in sub)/len(sub)
        nobid=sum(r["peak"]==0 for r in sub)/len(sub)
        print(f"  ask[{lo:.2f},{hi:.2f}) n={len(sub):3d} WR={wr:5.1%} "
              f"bid_spiked>=2x={spk:5.1%} never_had_bid={nobid:5.1%}")

if __name__ == "__main__":
    main()
