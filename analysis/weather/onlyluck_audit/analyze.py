#!/usr/bin/env python3
"""Full strategy teardown of onlylucknobrain. Reads act.jsonl + trd.jsonl + res.json.
Derives winner map from res.json (gamma outcomePrices OR CLOB winner_outcome).
Outputs: maker/taker %, YES/NO split, price bands, days-out, leg structure, sizing,
recycle/merge velocity, resolution ROI, equity curve (cum_cf + MTM)."""
import json, time, re, statistics as st
from collections import defaultdict

D = "analysis/weather/onlyluck_audit/"
rows = [json.loads(l) for l in open(D + "act.jsonl")]
try:
    trd = [json.loads(l) for l in open(D + "trd.jsonl")]
except FileNotFoundError:
    trd = []
res = json.load(open(D + "res.json"))

def day(ts): return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
def is_weather(r):
    t=(r.get('title') or '').lower(); s=(r.get('slug') or '').lower()
    return 'temperature' in t or 'temperature' in s
def is_min(slug): return (slug or '').startswith('lowest')
def city_of(slug):
    m=re.match(r'(?:arch-)?(?:highest|lowest)-temperature-in-(.+?)-on-', slug or '')
    return m.group(1) if m else (slug or '')[:18]

# ---- winner map from res.json ----
def winner_of(cid):
    v = res.get(cid)
    if not v: return None
    op = v.get('outcomePrices')
    if op:
        try:
            arr = json.loads(op) if isinstance(op, str) else op
            arr = [float(x) for x in arr]
            if len(arr) >= 2 and (arr[0] > 0.5 or arr[1] > 0.5):
                return 0 if arr[0] > arr[1] else 1
        except Exception: pass
    wo = v.get('winner_outcome')
    if wo:
        return 0 if str(wo).lower().startswith('y') else 1
    return None

W = [r for r in rows if is_weather(r)]
W.sort(key=lambda x:int(x['timestamp']))
days_all = sorted({day(r['timestamp']) for r in W})
DMIN, DMAX = days_all[0], days_all[-1]
nonw = len(rows) - len(W)
print(f"TOTAL activity rows {len(rows)} | weather {len(W)} | non-weather {nonw} | span {DMIN} -> {DMAX}")
print(f"event types: " + ", ".join(f"{k}={v}" for k,v in sorted(((t,sum(1 for r in rows if r['type']==t)) for t in {r['type'] for r in rows}), key=lambda x:-x[1])))

# ---- maker/taker anti-join (trades = taker-only; /trades caps at offset 3500 => recent window only) ----
def tk(r): return (r.get('transactionHash'), r.get('asset'), r.get('side'), round(float(r.get('size',0) or 0),4))
wtrd=[r for r in trd if is_weather(r)]
taker_keys = {tk(r) for r in wtrd}
tk_min = min((int(r['timestamp']) for r in wtrd), default=0)  # only window with complete taker data
buys = [r for r in W if r['type']=='TRADE' and r.get('side')=='BUY']
sells = [r for r in W if r['type']=='TRADE' and r.get('side')=='SELL']
win_buys=[r for r in buys if int(r['timestamp'])>=tk_min]
n_taker_buy = sum(1 for r in win_buys if tk(r) in taker_keys)
print(f"\n--- MAKER/TAKER (weather BUY fills, window {time.strftime('%m-%d',time.gmtime(tk_min))}->now where taker data complete) ---")
print(f"window buys={len(win_buys)} | taker={n_taker_buy} ({100*n_taker_buy/max(1,len(win_buys)):.1f}%) | maker={len(win_buys)-n_taker_buy} ({100*(len(win_buys)-n_taker_buy)/max(1,len(win_buys)):.1f}%)")

# ---- YES/NO split, price bands, sizing ----
def oi(r): return r.get('outcomeIndex')
yes_buys=[r for r in buys if oi(r)==0]; no_buys=[r for r in buys if oi(r)==1]
def usd(r): return float(r.get('usdcSize',0) or 0)
def px(r): return float(r.get('price') or 0)
ybuy_u=sum(usd(r) for r in yes_buys); nbuy_u=sum(usd(r) for r in no_buys); allbuy_u=ybuy_u+nbuy_u
print(f"\n--- YES/NO SPLIT (BUY $) ---")
print(f"YES: ${ybuy_u:,.0f} ({100*ybuy_u/max(1,allbuy_u):.0f}%) n={len(yes_buys)} | NO: ${nbuy_u:,.0f} ({100*nbuy_u/max(1,allbuy_u):.0f}%) n={len(no_buys)}")
print(f"median fill $: YES {st.median([usd(r) for r in yes_buys]) if yes_buys else 0:.2f} | NO {st.median([usd(r) for r in no_buys]) if no_buys else 0:.2f} | ALL {st.median([usd(r) for r in buys]) if buys else 0:.2f}")
print(f"median size(sh): YES {st.median([float(r.get('size',0)) for r in yes_buys]) if yes_buys else 0:.1f} | NO {st.median([float(r.get('size',0)) for r in no_buys]) if no_buys else 0:.1f}")

def hist(vals, edges):
    out=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        c=[v for v in vals if lo<=v<hi]
        out.append((lo,hi,len(c)))
    return out
print(f"\n--- YES BUY price distribution (n={len(yes_buys)}) ---")
ye=[0,0.05,0.10,0.15,0.25,0.35,0.45,0.55,0.70,1.01]
yv=[px(r) for r in yes_buys]
for lo,hi,c in hist(yv,ye):
    udollars=sum(usd(r) for r in yes_buys if lo<=px(r)<hi)
    print(f"  [{lo:.2f},{hi:.2f}): n={c:6d} ({100*c/max(1,len(yes_buys)):4.1f}%)  ${udollars:8,.0f} ({100*udollars/max(1,ybuy_u):4.1f}% of YES$)")
print(f"  YES px: median {st.median(yv) if yv else 0:.3f}  mean {st.mean(yv) if yv else 0:.3f}")
print(f"\n--- NO BUY price distribution (n={len(no_buys)}) ---")
ne=[0,0.05,0.45,0.52,0.62,0.72,0.85,0.95,1.01]
nv=[px(r) for r in no_buys]
for lo,hi,c in hist(nv,ne):
    udollars=sum(usd(r) for r in no_buys if lo<=px(r)<hi)
    print(f"  [{lo:.2f},{hi:.2f}): n={c:6d} ({100*c/max(1,len(no_buys)):4.1f}%)  ${udollars:8,.0f} ({100*udollars/max(1,nbuy_u):4.1f}% of NO$)")
print(f"  NO px: median {st.median(nv) if nv else 0:.3f}  mean {st.mean(nv) if nv else 0:.3f}")

# ---- per-event leg structure (YES legs, NO legs, buckets spanned) ----
ev_legs=defaultdict(lambda:{'yes':set(),'no':set(),'yes_n':0,'no_n':0})
for r in buys:
    e=r.get('eventSlug') or r['conditionId']
    L=ev_legs[e]
    if oi(r)==0: L['yes'].add(r['conditionId']); L['yes_n']+=1
    else: L['no'].add(r['conditionId']); L['no_n']+=1
yes_legs=[len(L['yes']) for L in ev_legs.values()]; no_legs=[len(L['no']) for L in ev_legs.values()]
print(f"\n--- PER-EVENT LEG STRUCTURE (n_events={len(ev_legs)}) ---")
print(f"median YES buckets/event {st.median(yes_legs) if yes_legs else 0:.0f} | median NO buckets/event {st.median(no_legs) if no_legs else 0:.0f}")
print(f"mean YES buckets/event {st.mean(yes_legs) if yes_legs else 0:.1f} | mean NO buckets/event {st.mean(no_legs) if no_legs else 0:.1f}")

# ---- days-out: entry day vs resolution endDate ----
def end_day(cid, fallback):
    # use slug date (on-<month>-<day>) since gamma endDate not stored; parse from slug
    return None
def slug_date(slug):
    m=re.search(r'on-([a-z]+)-(\d{1,2})-(\d{4})', slug or '')
    if not m:
        m2=re.search(r'(\d{4})-(\d{2})-(\d{2})', slug or '')
        if m2: return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        return None
    months={'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}
    mo=months.get(m.group(1).lower())
    if not mo: return None
    return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}"
doff=defaultdict(float); doff_n=defaultdict(int)
for r in buys:
    d=day(r['timestamp']); sd=slug_date(r.get('slug'))
    if not sd: continue
    try:
        o=int(round((time.mktime(time.strptime(sd,"%Y-%m-%d"))-time.mktime(time.strptime(d,"%Y-%m-%d")))/86400))
    except Exception: continue
    key=f"d+{o}" if 0<=o<=3 else ('d+3plus' if o>3 else 'past')
    doff[key]+=usd(r); doff_n[key]+=1
print(f"\n--- DAYS-OUT (entry vs settle date from slug) ---")
tot=sum(doff.values()) or 1
for k in ['d+0','d+1','d+2','d+3','d+3plus','past']:
    if k in doff: print(f"  {k:8}: ${doff[k]:9,.0f} ({100*doff[k]/tot:4.1f}%)  n={doff_n[k]}")

# ---- equity curve + recycle velocity (replay) ----
tok_shares=defaultdict(float); tok_meta={}; tok_lastpx=defaultdict(float); bucket_tokens=defaultdict(dict)
def token_resval(a):
    cid,o=tok_meta.get(a,(None,None))
    if cid is None: return tok_lastpx.get(a,0.0)
    w=winner_of(cid)
    if w is not None: return 1.0 if w==o else 0.0
    return tok_lastpx.get(a,0.0)
snap=[]; cur=None; cum_cf=0.0
ENT=defaultdict(lambda:defaultdict(float))
for r in W:
    d=day(r['timestamp'])
    if cur is None: cur=d
    while cur<d:
        mtm=sum(sh*token_resval(a) for a,sh in tok_shares.items() if sh>1e-6)
        snap.append((cur,cum_cf,mtm))
        t=time.strptime(cur,"%Y-%m-%d"); cur=time.strftime("%Y-%m-%d", time.gmtime(time.mktime(t)+86400))
    typ=r['type']; u=usd(r); sz=float(r.get('size',0) or 0); cid=r['conditionId']
    if typ=='TRADE':
        o=oi(r); a=r['asset']; tok_meta[a]=(cid,o); bucket_tokens[cid][o]=a
        p=px(r)
        if p>0: tok_lastpx[a]=p
        if r.get('side')=='BUY': tok_shares[a]+=sz; cum_cf-=u; ENT[d]['buy_u']+=u; ENT[d]['n_buys']+=1; ENT[d][('yes_buy_u' if o==0 else 'no_buy_u')]+=u
        else: tok_shares[a]-=sz; cum_cf+=u; ENT[d]['sell_u']+=u
    elif typ=='REDEEM':
        cum_cf+=u; ENT[d]['redeem_u']+=u; ENT[d]['n_redeem']+=1
        for o,a in bucket_tokens.get(cid,{}).items():
            if winner_of(cid)==o: tok_shares[a]=max(0.0,tok_shares[a]-sz)
    elif typ=='MERGE':
        cum_cf+=u; ENT[d]['merge_u']+=u; ENT[d]['n_merge']+=1
        for o,a in bucket_tokens.get(cid,{}).items(): tok_shares[a]=max(0.0,tok_shares[a]-sz)
    elif typ in ('REWARD','MAKER_REBATE'):
        cum_cf+=u; ENT[d]['reward_u']+=u
mtm=sum(sh*token_resval(a) for a,sh in tok_shares.items() if sh>1e-6)
snap.append((cur,cum_cf,mtm))

min_cf = min(cf for _,cf,_ in snap)
final_cf = snap[-1][1]; final_mtm = snap[-1][2]
print(f"\n--- CAPITAL / EQUITY ---")
print(f"max own cash sunk (min cum_cf) = ${min_cf:,.0f}")
print(f"final cum_cf = ${final_cf:,.0f} | final MTM(open) = ${final_mtm:,.0f} | net growth (cf+mtm) = ${final_cf+final_mtm:,.0f}")

# ---- resolution ledger (edge/ROI) ----
B=defaultdict(lambda:{'yc':0.0,'nc':0.0,'ys':0.0,'ns':0.0,'ysell_u':0.0,'nsell_u':0.0,'ysell_s':0.0,'nsell_s':0.0,'merge_u':0.0,'merge_s':0.0,'red_u':0.0,'slug':'','min':False})
for r in W:
    cid=r['conditionId']; b=B[cid]; typ=r['type']
    b['slug']=b['slug'] or r.get('slug') or ''; b['min']=b['min'] or is_min(r.get('slug'))
    u=usd(r); sz=float(r.get('size',0) or 0); o=oi(r)
    if typ=='TRADE':
        if r.get('side')=='BUY':
            if o==0: b['yc']+=u; b['ys']+=sz
            else: b['nc']+=u; b['ns']+=sz
        else:
            if o==0: b['ysell_u']+=u; b['ysell_s']+=sz
            else: b['nsell_u']+=u; b['nsell_s']+=sz
    elif typ=='REDEEM': b['red_u']+=u
    elif typ=='MERGE': b['merge_u']+=u; b['merge_s']+=sz
rc=rp=0.0; n_res=0; ywin=nwin=0; ypnl=npnl=0.0; ycost=ncost=0.0
for cid,b in B.items():
    w=winner_of(cid); cost=b['yc']+b['nc']
    if cost<=0 or w is None: continue
    cash_back=b['ysell_u']+b['nsell_u']+b['red_u']+b['merge_u']
    # red_u (winning-redeem cash) also proxies redeemed shares (paid $1) -> subtract so we don't double-count
    if w==0: held=b['ys']-b['ysell_s']-b['merge_s']-b['red_u']
    else:    held=b['ns']-b['nsell_s']-b['merge_s']-b['red_u']
    payoff=max(0.0,held)*1.0
    pnl=cash_back+payoff-cost
    rc+=cost; rp+=pnl; n_res+=1
    # classify event side by which side had more $
    if b['yc']>=b['nc']: ypnl+=pnl; ycost+=cost
    else: npnl+=pnl; ncost+=cost
print(f"\n--- RESOLVED LEDGER (edge) ---")
print(f"resolved buckets n={n_res} | cost ${rc:,.0f} | pnl ${rp:,.0f} | ROI {100*rp/max(1,rc):.1f}%")
print(f"  YES-side buckets: cost ${ycost:,.0f} pnl ${ypnl:,.0f} ROI {100*ypnl/max(1,ycost):.1f}%")
print(f"  NO-side buckets:  cost ${ncost:,.0f} pnl ${npnl:,.0f} ROI {100*npnl/max(1,ncost):.1f}%")

# ---- daily velocity table ----
print(f"\n--- DAILY FLOW (buy/recycle/merge/turns) ---")
print(f"{'day':11}{'buy$':>8}{'YES%':>5}{'fills':>6}{'merge$':>8}{'#mg':>4}{'redeem$':>9}{'sell$':>7}{'recyc':>6}")
valmap={}; base=0.0
for d,cf,m in snap: valmap[d]=cf+m
days=[d for d in sorted(ENT) if d>=DMIN]
for d in days[-30:]:
    e=ENT[d]; buy=e.get('buy_u',0); yes=e.get('yes_buy_u',0)
    mg=e.get('merge_u',0); rd=e.get('redeem_u',0); sl=e.get('sell_u',0)
    recyc=(mg+rd+sl)/buy if buy else 0
    print(f"{d:11}{buy:8,.0f}{100*yes/max(1,buy):5.0f}{int(e.get('n_buys',0)):6d}{mg:8,.0f}{int(e.get('n_merge',0)):4d}{rd:9,.0f}{sl:7,.0f}{recyc:6.2f}")

# ---- equity ramp milestones (cum_cf + mtm = profit-from-zero; + min cum_cf trajectory) ----
print(f"\n--- EQUITY RAMP (working equity proxy = cum_cf + MTM; capital floor = -min cum_cf to date) ---")
print(f"{'day':11}{'cum_cf':>10}{'MTM':>9}{'equity':>9}{'min_cf_todate':>14}")
runmin=0.0
for d,cf,m in snap:
    runmin=min(runmin,cf)
    # print weekly + key
    pass
# print every ~7th day
for i,(d,cf,m) in enumerate(snap):
    if i%7==0 or i==len(snap)-1:
        rmin=min(c for _,c,_ in snap[:i+1])
        print(f"{d:11}{cf:10,.0f}{m:9,.0f}{cf+m:9,.0f}{-rmin:14,.0f}")
json.dump([{'day':d,'cum_cf':cf,'mtm':m} for d,cf,m in snap], open(D+"equity_curve.json","w"))
print(f"\n-> equity_curve.json  ({len(snap)} days)")
