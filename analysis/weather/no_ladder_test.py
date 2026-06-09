#!/usr/bin/env python3
"""Direct test of NO-laddering on the FULL NO-signal population.
NO leg on bucket [lo,hi] LOSES iff the resolved daily max lands in [lo,hi].
EV_NO/share = realized_NO_WR - no_ask.  Split by phase (the user's claim is
PRE-PEAK: 'enough time before peak, temps priced ~0.3').  No fillable-band
filter -- the NO-tail zone is legitimately priced 0.9-0.99.
"""
import json, glob, statistics as st
from collections import defaultdict

PE = sorted(glob.glob("logs/shadow/hot/*/stwa_pricer_eval.jsonl"))
SG = sorted(glob.glob("logs/shadow/hot/*/stwa_signals.jsonl"))

# per city: list of (t_close, rmax) ; rmax = realized daily max proxy (max running_max)
rmax = defaultdict(lambda: -1e9)
for fn in PE:
    for ln in open(fn):
        try: r = json.loads(ln)
        except: continue
        tc = r.get("t_close"); rm = r.get("running_max")
        if tc is None: continue
        k = (r["city"], round(float(tc)))
        if rm is not None and rm > rmax[k]: rmax[k] = rm
by_city = defaultdict(list)
for (city, tc), rm in rmax.items():
    if rm > -1e8: by_city[city].append((tc, rm))
for v in by_city.values(): v.sort()

def winner_rmax(city, ts):
    """rmax of the market that is active at ts (smallest t_close > ts, within 30h)."""
    for tc, rm in by_city.get(city, []):
        if tc > ts and tc - ts < 30*3600:
            return rm
    return None

def contains(lo, hi, x):
    lo = -1e9 if lo <= -900 else lo;  hi = 1e9 if hi >= 900 else hi
    return lo <= x < hi

import sys
PRICE_FIELD = sys.argv[1] if len(sys.argv) > 1 else "clob_ask_live"  # real fillable quote
rows = []   # (phase, no_ask, no_win, p_model)
n_nofield = 0
for fn in SG:
    for ln in open(fn):
        try: r = json.loads(ln)
        except: continue
        if r.get("direction") != "NO": continue
        b = r.get("bucket"); a = r.get(PRICE_FIELD)
        if not b: continue
        if a is None: n_nofield += 1; continue
        rm = winner_rmax(r["city"], float(r["ts"]))
        if rm is None: continue
        no_win = 0 if contains(b[0], b[1], rm) else 1
        rows.append((r.get("phase",""), float(a), no_win, r.get("p_model",0.0)))

print(f"NO signals joined to resolution: n={len(rows)}  (price field = '{PRICE_FIELD}', {n_nofield} missing)")
nbands=[(0,.5),(.5,.7),(.7,.85),(.85,.93),(.93,.98),(.98,1.001)]
for phase in ("PRE_PEAK","AT_PEAK","POST_PEAK"):
    sub=[(a,w) for ph,a,w,_ in rows if ph==phase]
    if not sub: continue
    print(f"\n=== {phase} (n={len(sub)}) — realized NO-WR vs NO ask ===")
    print(f"{'no_ask band':>14} {'n':>6} {'mean_no_ask':>12} {'NO-WR':>8} {'EV/share':>10} {'gross $ if $1/leg':>17}")
    tot_ev=0.0; tot_n=0
    for lo,hi in nbands:
        s=[(a,w) for a,w in sub if lo<=a<hi]
        if not s: continue
        n=len(s); ma=st.mean(a for a,_ in s); wr=st.mean(w for _,w in s); ev=wr-ma
        print(f"[{lo:.2f},{hi:.2f}) {n:>6} {ma:>12.3f} {wr:>8.1%} {ev:>+10.3f} {ev*n:>+17.1f}")
        tot_ev+=ev*n; tot_n+=n
    ma=st.mean(a for a,_ in sub); wr=st.mean(w for _,w in sub)
    print(f"  ALL: n={tot_n} mean_no_ask={ma:.3f} NO-WR={wr:.1%} EV/share={wr-ma:+.3f} (sum EV ${tot_ev:+.1f})")
