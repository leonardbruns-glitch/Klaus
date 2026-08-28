"""Split the calibration by bucket TYPE: open-ended cumulative tail ('or higher'/
'or below') vs interior single/2-degree buckets. The favorite-longshot bias can
differ structurally between the two. Confirms which band+type carries the +EV.
"""
from __future__ import annotations
from collections import defaultdict
import numpy as np
from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.stations import STATIONS

DAYS_BACK = 10
BANDS = [(0.02,0.05),(0.05,0.10),(0.10,0.20),(0.20,0.40),(0.40,0.60),(0.60,0.80),(0.80,0.92),(0.92,0.98)]


def fee(a): return 0.05 * a * (1 - a)
def yes_ev(a, w): return (1-a)-fee(a) if w else -a-fee(a)
def no_ev(a, w):
    npx=1-a; return (1-npx)-fee(a) if (not w) else -npx-fee(a)


def is_open(label):
    l = label.lower()
    return ("or higher" in l) or ("or above" in l) or ("or below" in l)


def main():
    obs = []
    for c in sorted(STATIONS.keys()):
        try:
            ms = discover_resolved(c, DAYS_BACK); attach_entry_prices(ms)
        except Exception:
            continue
        for m in ms:
            if sum(b.is_winner for b in m.buckets) != 1:
                continue
            for b in m.buckets:
                a = b.entry_price
                if a is None or a <= 0 or a >= 1:
                    continue
                obs.append({"price": a, "won": b.is_winner, "open": is_open(b.label), "city": c})

    for typ, flag in [("INTERIOR (2-deg bins)", False), ("OPEN-ENDED (cumulative tail)", True)]:
        print(f"\n================= {typ} =================")
        print(f"{'band':<14}{'n':<7}{'WR':<9}{'implied':<10}{'misprice':<11}{'YES_EV':<11}{'NO_EV':<10}")
        for lo, hi in BANDS:
            rs = [o for o in obs if o["open"] == flag and lo <= o["price"] < hi]
            if not rs:
                print(f"[{lo:.2f},{hi:.2f})   0"); continue
            wr = np.mean([r["won"] for r in rs]); imp = np.mean([r["price"] for r in rs])
            ye = np.mean([yes_ev(r["price"], r["won"]) for r in rs])
            ne = np.mean([no_ev(r["price"], r["won"]) for r in rs])
            print(f"[{lo:.2f},{hi:.2f})   {len(rs):<7}{wr:<9.3f}{imp:<10.3f}{wr-imp:<+11.3f}{ye:<+11.4f}{ne:<+10.4f}")


if __name__ == "__main__":
    main()
