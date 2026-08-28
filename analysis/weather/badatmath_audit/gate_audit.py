#!/usr/bin/env python3
"""AUDIT (b): replay OUR band gates on badatmath's resolved YES fills and measure
the ROI of what each gate would REJECT vs KEEP. If rejected slices are +EV in his
hands, the gate is destroying edge. Gates: price-ceil 0.45, convergence (fav>0.45),
Σ-gate (posted basket≥0.85), σ-skill (city σ∉[0.95,1.40])."""
import json, re, statistics as st
from collections import defaultdict

D = "analysis/weather/badatmath_audit/"
rows = [json.loads(l) for l in open(D + "act_31d.jsonl")]
WIN = json.load(open(D + "winners_31d.json"))
calib = json.load(open("config/stwa_peak_calib.json"))

# our σ-skill gate replica (June=month 6), mirrors _peak_sigma_for
SIGMA_CALIB_INFLATION = 1.0
def peak_sigma(city, month=6):
    cal = calib.get(city) or calib.get("_pooled", {})
    for src in (cal, calib.get("_pooled", {})):
        sm = src.get("sigma_monthly") if isinstance(src, dict) else None
        if isinstance(sm, dict):
            v = sm.get(str(month)) or sm.get(month)
            if v: return float(v) * SIGMA_CALIB_INFLATION
    if isinstance(cal, dict) and cal.get("sigma"): return float(cal["sigma"])
    return 1.1

def degc(slug):
    m = re.search(r'-(\d+)c$', slug or ''); return int(m.group(1)) if m else None
def city_of(slug):
    m = re.match(r'(?:arch-)?(?:highest|lowest)-temperature-in-(.+?)-on-', slug or '')
    return m.group(1) if m else None
def winner(cid):
    w = WIN.get(cid); return w if w in (0, 1) else None

# build per-event (eventSlug) bucket aggregates for YES buys on °C single-degree mkts
ev = defaultdict(lambda: defaultdict(lambda: {'cost':0.0,'sh':0.0,'pxsh':0.0,'cid':'','temp':None,'won':None}))
ev_city = {}
for r in rows:
    if r.get('type')!='TRADE' or r.get('side')!='BUY' or r.get('outcomeIndex')!=0: continue
    if 'temperature' not in (r.get('title') or '').lower(): continue
    t = degc(r.get('slug'))
    if t is None: continue          # °C single-degree only (clean offset math)
    es = r.get('eventSlug'); cid = r['conditionId']
    b = ev[es][t]
    b['cost']+=r['usdcSize']; b['sh']+=r['size']; b['pxsh']+=r['price']*r['size']
    b['cid']=cid; b['temp']=t
    ev_city[es]=city_of(r.get('slug'))

def roi(fills):  # fills = list of (cost, shares, won)
    c=sum(f[0] for f in fills); pay=sum(f[1] for f in fills if f[2])
    return (100*(pay-c)/c if c>0 else 0.0, c, len(fills))

# classify every near-mode YES bucket (|off|<=1, what WE'd post) by each gate
keep_price=[]; rej_price=[]      # price ceil 0.45 / floor
keep_conv=[]; rej_conv=[]        # convergence (event favorite>0.45)
keep_sum=[]; rej_sum=[]          # Σ-gate (posted basket>=0.85)
keep_sig=[]; rej_sig=[]          # σ-skill (city σ∉[0.95,1.40])
all_nm=[]
for es, buckets in ev.items():
    if not buckets: continue
    # $-mode = bucket with most YES cost; favorite ask proxy = max avg fill price
    mode_t = max(buckets, key=lambda t: buckets[t]['cost'])
    fav_px = max((b['pxsh']/b['sh'] if b['sh'] else 0) for b in buckets.values())
    city = ev_city.get(es); sig = peak_sigma(city) if city else 1.1
    # near-mode basket Σ (|off|<=1 avg prices)
    nm_sum = sum((buckets[t]['pxsh']/buckets[t]['sh'] if buckets[t]['sh'] else 0)
                 for t in buckets if abs(t-mode_t)<=1)
    for t, b in buckets.items():
        if abs(t-mode_t) > 1: continue        # we only post |off|<=1 YES
        w = winner(b['cid'])
        if w is None or b['sh']<=0: continue
        avgpx = b['pxsh']/b['sh']
        won = (w==0)
        f = (b['cost'], b['sh'], won)
        all_nm.append(f)
        # GATE 1: price window [0.03,0.45] (use 0.03 floor = d+1+; ceil 0.45)
        (keep_price if 0.03<=avgpx<=0.45 else rej_price).append(f)
        # GATE 2: convergence — skip whole event if favorite ask proxy > 0.45
        (rej_conv if fav_px>0.45 else keep_conv).append(f)
        # GATE 3: Σ-gate — skip if near-mode posted basket >= 0.85
        (rej_sum if nm_sum>=0.85 else keep_sum).append(f)
        # GATE 4: σ-skill — skip city if σ ∉ [0.95,1.40]
        (rej_sig if not (0.95<=sig<=1.40) else keep_sig).append(f)

print("="*78)
print("GATE AUDIT — ROI of his near-mode YES fills (|off|<=1) by our gate decision")
print("(KEEP = we'd quote it; REJECT = our gate skips it. +ROI on REJECT = lost edge)")
print("="*78)
b_all = roi(all_nm)
print(f"\nALL near-mode YES (baseline): ROI {b_all[0]:+.1f}%  cost ${b_all[1]:,.0f}  n={b_all[2]}")
for name, keep, rej in [("PRICE [0.03,0.45]",keep_price,rej_price),
                        ("CONVERGENCE (fav>0.45 skip)",keep_conv,rej_conv),
                        ("Σ-GATE (basket>=0.85 skip)",keep_sum,rej_sum),
                        ("σ-SKILL (σ∉[0.95,1.40] skip)",keep_sig,rej_sig)]:
    k=roi(keep); r=roi(rej)
    verdict = "  <-- REJECT is +EV: gate COSTS edge" if (r[2]>200 and r[0]>3) else (
              "  (reject ~fair/−EV: gate OK)" if r[2]>50 else "  (reject n too small)")
    print(f"\n{name}")
    print(f"   KEEP:   ROI {k[0]:+6.1f}%  cost ${k[1]:>8,.0f}  n={k[2]:>5}")
    print(f"   REJECT: ROI {r[0]:+6.1f}%  cost ${r[1]:>8,.0f}  n={r[2]:>5}{verdict}")

# σ-skill: list which cities are gated and their ROI
print("\n"+"="*78)
print("σ-SKILL gate — per-city: which cities does it EXCLUDE, and his ROI there?")
print("="*78)
city_fills=defaultdict(list)
for es, buckets in ev.items():
    city=ev_city.get(es); mode_t=max(buckets,key=lambda t:buckets[t]['cost'])
    for t,b in buckets.items():
        if abs(t-mode_t)>1: continue
        w=winner(b['cid'])
        if w is None or b['sh']<=0: continue
        city_fills[city].append((b['cost'],b['sh'],w==0))
out=[]
for city,fills in city_fills.items():
    if not city or len(fills)<60: continue
    sig=peak_sigma(city); rr=roi(fills)
    gated = not (0.95<=sig<=1.40)
    out.append((rr[0],city,sig,gated,rr[1],rr[2]))
out.sort(reverse=True)
print(f"{'city':16} {'σ(Jun)':>7} {'gated?':>7} {'ROI%':>7} {'cost$':>9} {'n':>5}")
for r0,city,sig,gated,cost,n in out:
    print(f"{city:16} {sig:7.2f} {('SKIP' if gated else 'post'):>7} {r0:7.1f} {cost:9,.0f} {n:5}")
gated_fills=[f for c,fl in city_fills.items() if c and not(0.95<=peak_sigma(c)<=1.40) for f in fl]
if gated_fills:
    g=roi(gated_fills); print(f"\nALL σ-gated cities combined: ROI {g[0]:+.1f}%  cost ${g[1]:,.0f}  n={g[2]}")
