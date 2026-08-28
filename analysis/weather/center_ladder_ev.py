#!/usr/bin/env python3
"""Center-laddering research: does buying the model's TOP-k buckets (a ladder
around the predicted winner) capture enough real win-probability to beat the
summed ask?  Ladder EV = sum_{i in S}(realized_win_i - ask_i).  Mutually
exclusive => exactly one bucket wins; no coverage bonus, EV is additive.

Data:
  - stwa_pricer_eval.jsonl : per (city,lo,hi,ts) p_ps/p_cal + running_max + t_close.
    Realized winner per city-day = bucket containing max(running_max) over the day.
  - stwa_signals.jsonl     : per (city,bucket,ts) the live YES `ask` (edge>=0.04 only).

Evaluation snapshot = pricer row-group whose ts is closest to t_close - L hours.
Reports: model rank skill (P(winner in top-k)), p_cal calibration in the favorite
band, and realized ladder EV/share for top-k ladders (over buckets with a logged ask).
"""
import json, glob, statistics as st
from collections import defaultdict

L_HOURS = 4.0
WIN_TOL = 5400           # +/-90 min window to find a genuine pre-peak snapshot
ASK_TOL = 600            # match a signal ask within 10 min of eval ts
GAP_MIN = 1.5            # require realized_max - running_max(eval) >= this (deg): winner NOT yet locked
ASK_LO, ASK_HI = 0.03, 0.97   # fillable-quote band (exclude phantom ~0 / ~1 asks)
PE = sorted(glob.glob("logs/shadow/hot/*/stwa_pricer_eval.jsonl"))
SG = sorted(glob.glob("logs/shadow/hot/*/stwa_signals.jsonl"))

def daykey(city, t_close):
    return (city, round(float(t_close)))

# ---- pass 1: per city-day, global max running_max + buckets near target snapshot
rmax = defaultdict(lambda: -1e9)          # daykey -> max running_max (realized daily max proxy)
snaps = defaultdict(dict)                 # daykey -> {ts: {(lo,hi):(p_ps,p_cal)}}
snaprm = defaultdict(dict)                # daykey -> {ts: (running_max, phase)} at that snapshot
tclose = {}                               # daykey -> t_close
for fn in PE:
    for ln in open(fn):
        try: r = json.loads(ln)
        except: continue
        tc = r.get("t_close")
        if tc is None: continue
        k = daykey(r["city"], tc); tclose[k] = float(tc)
        rm = r.get("running_max")
        if rm is not None and rm > rmax[k]: rmax[k] = rm
        if r.get("phase") != "PRE_PEAK": continue          # only genuine-forecast moments
        ts = round(float(r["ts"])/600)*600                 # 10-min grid (bounded memory)
        snaps[k].setdefault(ts, {})[(r["lo"], r["hi"])] = (r.get("p_ps",0.0), r.get("p_cal",0.0))
        snaprm[k][ts] = (rm if rm is not None else -1e9, "PRE_PEAK")

# ---- load signal asks: (city, round(lo,1), round(hi,1)) -> [(ts, ask)]   (YES + NO)
asks = defaultdict(list)
no_asks = defaultdict(list)
for fn in SG:
    for ln in open(fn):
        try: r = json.loads(ln)
        except: continue
        b = r.get("bucket");  a = r.get("ask")
        if not b or a is None: continue
        key = (r["city"], round(b[0],1), round(b[1],1))
        if r.get("direction") == "YES":  asks[key].append((float(r["ts"]), float(a)))
        elif r.get("direction") == "NO": no_asks[key].append((float(r["ts"]), float(a)))
for v in asks.values(): v.sort()
for v in no_asks.values(): v.sort()

def no_ask(city, lo, hi, ts):
    cand = no_asks.get((city, round(lo,1), round(hi,1)))
    if not cand: return None
    best = min(cand, key=lambda x: abs(x[0]-ts))
    return best[1] if abs(best[0]-ts) <= 1800 else None

def raw_ask(city, lo, hi, ts):
    cand = asks.get((city, round(lo,1), round(hi,1)))
    if not cand: return None
    best = min(cand, key=lambda x: abs(x[0]-ts))
    return best[1] if abs(best[0]-ts) <= 1800 else None   # any logged quote within 30min

def get_ask(city, lo, hi, ts):
    a = raw_ask(city, lo, hi, ts)
    if a is None: return None
    return a if ASK_LO <= a <= ASK_HI else None   # fillable band only

def contains(lo, hi, x):
    lo = -1e9 if lo <= -900 else lo
    hi =  1e9 if hi >=  900 else hi
    return lo <= x < hi

# ---- evaluate each city-day at the eval snapshot
rank_hits = defaultdict(int); n_days = 0
covclaim = defaultdict(list); covreal = defaultdict(list)   # k -> claimed sum p_cal / realized hit
ladder_ev = defaultdict(list)                               # k -> per-day ladder EV/share (ask-priced)
ladder_cov = defaultdict(list)                              # k -> frac of legs with a known ask
calib = []                                                  # (p_cal, is_winner) per bucket (top region)
single_fav = []                                             # (p_cal, ask, win) for the #1 bucket only
no_calib = []                                               # (no_ask, no_win) per bucket w/ logged NO ask
no_ladder = defaultdict(list)                               # k -> per-day NO-ladder EV/share (bottom-k by p_cal)

skipped_locked = 0
for k, snapdict in snaps.items():
    if rmax[k] < -1e8: continue
    # genuine forecast uncertainty: pre-peak AND winner not yet locked into running_max
    # (else the running-max floor leaks the answer = hindsight). Take the LATEST such
    # snapshot = max info while outcome still uncertain.
    elig = [t for t in snapdict if rmax[k] - snaprm[k].get(t,(-1e9,""))[0] >= GAP_MIN]
    if not elig:
        skipped_locked += 1; continue
    ts = max(elig)
    buckets = snapdict[ts]
    if len(buckets) < 3: continue
    win = next((b for b in buckets if contains(b[0], b[1], rmax[k])), None)
    if win is None: continue
    n_days += 1
    ranked = sorted(buckets.items(), key=lambda kv: kv[1][1], reverse=True)  # by p_cal desc
    for (b, (pps, pcal)) in ranked:
        calib.append((pcal, 1 if b == win else 0))
    b1, (pps1, pcal1) = ranked[0]
    a1 = get_ask(k[0], b1[0], b1[1], ts)
    a1raw = raw_ask(k[0], b1[0], b1[1], ts)
    single_fav.append((pcal1, a1, 1 if b1 == win else 0, a1raw))
    # --- NO side: every bucket with a logged NO ask -> (no_ask, no_win)
    for (b, (pps, pcal)) in ranked:
        na = no_ask(k[0], b[0], b[1], ts)
        if na is not None:
            no_calib.append((na, 0 if b == win else 1))
    # NO ladder = buy NO on the BOTTOM-k buckets by p_cal (model most sure NOT the max)
    bottom = sorted(buckets.items(), key=lambda kv: kv[1][1])  # ascending p_cal
    for kk in (3,5,8):
        legs = [(b, no_ask(k[0], b[0], b[1], ts)) for b,_ in bottom[:kk]]
        known = [(b,a) for b,a in legs if a is not None and ASK_LO <= a <= ASK_HI]
        if known:
            ev = sum((0.0 if b==win else 1.0) - a for b,a in known)/len(known)
            no_ladder[kk].append(ev)
    for kk in (1,2,3,5):
        top = ranked[:kk]
        hit = any(b == win for b,_ in top)
        rank_hits[kk] += 1 if hit else 0
        covclaim[kk].append(sum(v[1] for _,v in top))      # summed p_cal
        covreal[kk].append(1 if hit else 0)
        legs = [(b, get_ask(k[0], b[0], b[1], ts)) for b,_ in top]
        known = [(b,a) for b,a in legs if a is not None]
        if known:
            ev = sum((1.0 if b==win else 0.0) - a for b,a in known)/len(known)  # per-share avg
            ladder_ev[kk].append(ev)
            ladder_cov[kk].append(len(known)/len(top))

print(f"eval = LATEST PRE_PEAK snapshot with winner>={GAP_MIN}deg above running_max (genuine uncertainty)")
print(f"city-days evaluated: n={n_days}  (skipped {skipped_locked}: no unlocked pre-peak snapshot)")
print(f"fillable ask band [{ASK_LO},{ASK_HI}] | PE files: {len(PE)}  SG files: {len(SG)}\n")

print("MODEL RANK SKILL (does a top-k ladder contain the realized winner?)")
print(f"{'k':>3} {'P(winner in topk)':>18} {'claimed sum p_cal':>18} {'overconf gap':>13}")
for kk in (1,2,3,5):
    pr = rank_hits[kk]/n_days
    cc = st.mean(covclaim[kk])
    print(f"{kk:>3} {pr:>17.1%} {cc:>18.3f} {cc-pr:>+13.3f}")

print("\nFAVORITE-ZONE CALIBRATION (p_cal vs realized win, all buckets at snapshot)")
bands=[(0,.05),(.05,.10),(.10,.20),(.20,.35),(.35,.50),(.50,.70),(.70,1.01)]
print(f"{'p_cal band':>14} {'n':>6} {'mean p_cal':>11} {'realized WR':>12} {'gap(WR-p)':>10}")
for lo,hi in bands:
    sub=[(p,w) for p,w in calib if lo<=p<hi]
    if not sub: continue
    n=len(sub); mp=st.mean(p for p,_ in sub); wr=st.mean(w for _,w in sub)
    print(f"[{lo:.2f},{hi:.2f}) {n:>6} {mp:>11.3f} {wr:>12.1%} {wr-mp:>+10.3f}")

print("\nREALIZED LADDER EV (top-k by p_cal, priced at logged YES ask, /share net)")
print(f"{'k':>3} {'n_days':>7} {'avg ask coverage':>17} {'EV/share':>10} {'  => sign':>10}")
for kk in (1,2,3,5):
    if not ladder_ev[kk]: continue
    ev=st.mean(ladder_ev[kk]); cov=st.mean(ladder_cov[kk]); n=len(ladder_ev[kk])
    print(f"{kk:>3} {n:>7} {cov:>16.0%} {ev:>+10.3f} {'+EV' if ev>0 else 'NEG':>10}")

print("\nSINGLE FAVORITE (#1 bucket only): realized WR vs its ask")
fa=[(p,a,w) for p,a,w,_ in single_fav if a is not None]
if fa:
    n=len(fa); wr=st.mean(w for _,_,w in fa); aa=st.mean(a for _,a,_ in fa); mp=st.mean(p for p,_,_ in fa)
    print(f"  n={n}  mean p_cal={mp:.3f}  realized WR={wr:.1%}  mean ask={aa:.3f}  EV/share={wr-aa:+.3f}")
n_tot=len(single_fav)
n_anyq=sum(1 for *_,ar in single_fav if ar is not None)
n_phantom=sum(1 for *_,ar in single_fav if ar is not None and not (ASK_LO<=ar<=ASK_HI))
print(f"\nFAVORITE ASK COVERAGE (the executability wall):")
print(f"  {n_tot} favorites | {n_anyq} had ANY logged YES quote | {n_anyq-n_phantom} fillable [{ASK_LO},{ASK_HI}] | {n_phantom} phantom(~0/~1)")
print(f"  {n_tot-n_anyq} had NO signal quote at all (edge<0.04 => fairly priced / not flagged)")

print("\n" + "="*64)
print("NO-LADDER (buy NO on buckets the model says won't be the max)")
print("NO wins unless that bucket is the resolved max. EV_NO = (1-p) - no_ask.")
print(f"\nNO calibration: realized NO-win vs NO ask paid (pre-peak, logged NO quotes)")
print(f"{'no_ask band':>14} {'n':>6} {'mean no_ask':>12} {'realized NO-WR':>15} {'EV/share':>10}")
nbands=[(0,.5),(.5,.7),(.7,.85),(.85,.93),(.93,.98),(.98,1.001)]
for lo,hi in nbands:
    sub=[(a,w) for a,w in no_calib if lo<=a<hi]
    if not sub: continue
    n=len(sub); ma=st.mean(a for a,_ in sub); wr=st.mean(w for _,w in sub)
    print(f"[{lo:.2f},{hi:.2f}) {n:>6} {ma:>12.3f} {wr:>15.1%} {wr-ma:>+10.3f}")
allno=no_calib
if allno:
    n=len(allno); ma=st.mean(a for a,_ in allno); wr=st.mean(w for _,w in allno)
    print(f"  ALL logged NO buckets: n={n} mean_no_ask={ma:.3f} realized_NO_WR={wr:.1%} EV/share={wr-ma:+.3f}")
print(f"\nNO-ladder EV (bottom-k by p_cal, fillable NO asks only, /share):")
print(f"{'k':>3} {'n_days':>7} {'EV/share':>10} {'=> sign':>9}")
for kk in (3,5,8):
    if not no_ladder[kk]: continue
    ev=st.mean(no_ladder[kk]); n=len(no_ladder[kk])
    print(f"{kk:>3} {n:>7} {ev:>+10.3f} {'+EV' if ev>0 else 'NEG':>9}")
