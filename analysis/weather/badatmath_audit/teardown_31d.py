#!/usr/bin/env python3
"""DEFINITIVE 31-day teardown of badatmath. Answers every decomposition question:
legs, prices, maker/taker, YES-vs-NO logic, sizing, recycle, queue, d0/d1/d2, merge,
edge signature, equity/growth. Window May 17 -> Jun 17 2026."""
import json, time, re, statistics as st
from collections import defaultdict, Counter

D = "analysis/weather/badatmath_audit/"
rows = [json.loads(l) for l in open(D + "act_31d.jsonl")]
WIN = json.load(open(D + "winners_31d.json"))   # cid -> 0(YES won)/1(NO won)
try:
    taker = [json.loads(l) for l in open(D + "trd_31d.jsonl")]
except FileNotFoundError:
    taker = []

_MON = {m: i+1 for i, m in enumerate(
    ['january','february','march','april','may','june','july','august',
     'september','october','november','december'])}
CID_SLUG = {}
for _r in rows:
    if _r.get('conditionId') and _r.get('slug') and _r['conditionId'] not in CID_SLUG:
        CID_SLUG[_r['conditionId']] = _r['slug']

def day(ts): return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
def is_weather(r):
    t = (r.get('title') or '').lower(); s = (r.get('slug') or '').lower()
    return 'temperature' in t or 'temperature' in s
def is_min(r): return 'lowest-temperature' in (r.get('slug') or '')
def city_of(slug):
    m = re.match(r'(?:arch-)?(?:highest|lowest)-temperature-in-(.+?)-on-', slug or '')
    return m.group(1) if m else (slug or '')[:18]
def winner(cid):
    w = WIN.get(cid)
    return w if w in (0, 1) else None
def _slug_date(slug):
    m = re.search(r'-on-([a-z]+)-(\d{1,2})-(\d{4})', slug or '')
    if not m: return None
    mo = _MON.get(m.group(1));
    if not mo: return None
    return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}"
def end_day(cid, fb):
    d = _slug_date(CID_SLUG.get(cid, ''))
    return d if d else day(fb)
def doff_of(cid, ts):
    ed = end_day(cid, ts); d = day(ts)
    try:
        return int(round((time.mktime(time.strptime(ed, "%Y-%m-%d")) -
                          time.mktime(time.strptime(d, "%Y-%m-%d"))) / 86400))
    except: return -99

wx = [r for r in rows if is_weather(r)]
trades = [r for r in wx if r['type'] == 'TRADE']
buys = [r for r in trades if r['side'] == 'BUY']
yes_buys = [r for r in buys if r['outcomeIndex'] == 0]
no_buys = [r for r in buys if r['outcomeIndex'] == 1]
print("="*92)
print("0. SCOPE  (weather only; min-temp markets included, flagged where it matters)")
print("="*92)
tot_buy = sum(r['usdcSize'] for r in buys)
print(f"weather events: {len(wx):,}  TRADES: {len(trades):,}  BUYS: {len(buys):,}  "
      f"(YES {len(yes_buys):,} / NO {len(no_buys):,})")
print(f"buy$ total: ${tot_buy:,.0f}   YES$ ${sum(r['usdcSize'] for r in yes_buys):,.0f}  "
      f"NO$ ${sum(r['usdcSize'] for r in no_buys):,.0f}  (YES%={100*sum(r['usdcSize'] for r in yes_buys)/tot_buy:.0f})")
nmin = sum(1 for r in buys if is_min(r))
print(f"min-temp buys: {nmin:,} ({100*nmin/len(buys):.1f}% of buys)")

# ---------------- 1. MAKER vs TAKER ----------------
print("\n" + "="*92); print("1. EXECUTION — MAKER vs TAKER (how he puts orders)"); print("="*92)
tk_keys = set((r.get('transactionHash'), r.get('asset'), int(r['timestamp']), r.get('size')) for r in taker)
if taker:
    n_taker_wx = 0
    for r in trades:
        if (r.get('transactionHash'), r.get('asset'), int(r['timestamp']), r.get('size')) in tk_keys:
            n_taker_wx += 1
    print(f"taker pull: {len(taker):,} fills. weather TRADES matched as TAKER: {n_taker_wx:,} "
          f"=> MAKER = {len(trades)-n_taker_wx:,} ({100*(len(trades)-n_taker_wx)/len(trades):.1f}% maker)")
else:
    print("taker pull empty — maker% via prior audits (97-99%).")
# stale-fill evidence: same (cid,asset,price) fills spanning hours = one resting bid eaten over time
lvl = defaultdict(list)
for r in buys:
    lvl[(r['conditionId'], r['outcomeIndex'], round(r['price'], 3))].append(int(r['timestamp']))
spans = [(max(v)-min(v))/3600 for v in lvl.values() if len(v) >= 2]
multi = [v for v in lvl.values() if len(v) >= 2]
print(f"price-levels with >=2 fills: {len(multi):,}/{len(lvl):,}  "
      f"median span {st.median(spans):.2f}h  p90 {sorted(spans)[int(.9*len(spans))]:.1f}h  "
      f"(long spans @ one price = a resting maker bid filled over time, not repriced)")
fillsper = [len(v) for v in lvl.values()]
print(f"fills per (bucket,side,price): median {st.median(fillsper):.0f}  max {max(fillsper)} "
      f"(many fills @ identical px = he leaves the bid, does NOT chase)")

# ---------------- 2. LEGS PER EVENT (width) ----------------
print("\n" + "="*92); print("2. LEGS PER EVENT — how many buckets per city-day (we do mode +/-1)"); print("="*92)
ev_yes = defaultdict(set); ev_no = defaultdict(set); ev_any = defaultdict(set)
for r in buys:
    es = r.get('eventSlug') or r['conditionId']
    ev_any[es].add(r['conditionId'])
    (ev_yes if r['outcomeIndex'] == 0 else ev_no)[es].add(r['conditionId'])
def dist(x):
    x=sorted(x); return f"med {st.median(x):.0f} p25 {x[int(.25*len(x))]:.0f} p75 {x[int(.75*len(x))]:.0f} p90 {x[int(.9*len(x))]:.0f} max {max(x)}"
print(f"distinct buckets/event (any side): {dist([len(v) for v in ev_any.values()])}  (n_events={len(ev_any)})")
print(f"YES buckets/event:               {dist([len(v) for v in ev_yes.values() if v])}")
print(f"NO  buckets/event:               {dist([len(v) for v in ev_no.values() if v])}")
both = sum(1 for es in ev_any if ev_yes.get(es) and ev_no.get(es))
print(f"events with BOTH YES and NO legs: {both}/{len(ev_any)} ({100*both/len(ev_any):.0f}%)")

# ---------------- 3. ENTRY PRICE DISTRIBUTION ----------------
print("\n" + "="*92); print("3. ENTRY PRICES — where he buys (YES vs NO)"); print("="*92)
def pxtable(bset, edges):
    tot=sum(r['usdcSize'] for r in bset)
    for lo,hi in zip(edges,edges[1:]):
        sel=[r for r in bset if lo<=r['price']<hi]
        if not sel: continue
        u=sum(r['usdcSize'] for r in sel); sh=sum(r['size'] for r in sel)
        print(f"   px [{lo:.2f},{hi:.2f}): n={len(sel):6,} ${u:8,.0f} ({100*u/tot:4.1f}%) shares={sh:9,.0f}")
print("YES entry price histogram:")
pxtable(yes_buys,[0,.03,.05,.10,.15,.22,.30,.40,.45,.55,1.01])
print(f"   YES px: median {st.median([r['price'] for r in yes_buys]):.3f}  fill$ median {st.median([r['usdcSize'] for r in yes_buys]):.2f}")
print("NO entry price histogram:")
pxtable(no_buys,[0,.20,.35,.45,.52,.65,.75,.85,.95,1.01])
print(f"   NO px: median {st.median([r['price'] for r in no_buys]):.3f}  fill$ median {st.median([r['usdcSize'] for r in no_buys]):.2f}")

# ---------------- 4. SIZING (bell in $, U in shares) ----------------
print("\n" + "="*92); print("4. SIZING — $ and shares per offset-from-mode"); print("="*92)
# mode per event = bucket with most YES $ (his $-center). offset = bucket index distance.
def degc(slug):
    m=re.search(r'-(\d+)c$', slug or ''); return int(m.group(1)) if m else None
ev_mode={}
ev_buck_usd=defaultdict(lambda: defaultdict(float))
for r in yes_buys:
    es=r.get('eventSlug'); t=degc(r.get('slug'))
    if t is None: continue
    ev_buck_usd[es][t]+=r['usdcSize']
for es,bk in ev_buck_usd.items():
    ev_mode[es]=max(bk,key=bk.get)
off_yes=defaultdict(lambda:[0.0,0.0,0]); off_no=defaultdict(lambda:[0.0,0.0,0])
for r in yes_buys:
    es=r.get('eventSlug'); t=degc(r.get('slug'))
    if es in ev_mode and t is not None:
        o=abs(t-ev_mode[es]); off_yes[o][0]+=r['usdcSize']; off_yes[o][1]+=r['size']; off_yes[o][2]+=1
for r in no_buys:
    es=r.get('eventSlug'); t=degc(r.get('slug'))
    if es in ev_mode and t is not None:
        o=t-ev_mode[es]; off_no[o][0]+=r['usdcSize']; off_no[o][1]+=r['size']; off_no[o][2]+=1
print("YES |offset from $-mode|:  $-bell vs share-U  (per-fill $)")
for o in sorted(off_yes)[:6]:
    u,sh,n=off_yes[o]; print(f"   |off|={o}: n={n:6,} ${u:8,.0f}  shares={sh:9,.0f}  $/fill={u/n:.2f}  sh/fill={sh/n:.0f}")
print("NO signed offset from YES-$-mode (favorite side):")
for o in sorted(off_no):
    if abs(o)>4: continue
    u,sh,n=off_no[o]
    if n<20: continue
    print(f"   off={o:+d}: n={n:6,} ${u:8,.0f}  shares={sh:9,.0f}  $/fill={u/n:.2f}")

# ---------------- 5. OFFSET d+0/d+1/d+2 (spend + ROI) ----------------
print("\n" + "="*92); print("5. DAYS-OUT d+0/d+1/d+2 — spend split + hold-to-resolution ROI"); print("="*92)
doff_buy=defaultdict(lambda: defaultdict(lambda:[0.0,0.0,0.0,0]))  # [cost,payoff,won_sh,n] keyed side
for r in buys:
    do=doff_of(r['conditionId'],r['timestamp'])
    if not (0<=do<=3): continue
    side='YES' if r['outcomeIndex']==0 else 'NO'
    w=winner(r['conditionId'])
    rec=doff_buy[(do,side)][r['conditionId']]
    rec[0]+=r['usdcSize']
    if w is not None:
        rec[1]+= r['size'] if w==r['outcomeIndex'] else 0.0
        rec[3]=1
agg=defaultdict(lambda:[0.0,0.0])
for (do,side),cids in doff_buy.items():
    for cid,rec in cids.items():
        if rec[3]:
            agg[(do,side)][0]+=rec[0]; agg[(do,side)][1]+=rec[1]
print(f"{'days_out':9} {'side':4} {'cost$':>9} {'payoff$':>9} {'ROI%':>7}")
for do in range(0,4):
    for side in ('YES','NO'):
        c,p=agg.get((do,side),[0,0])
        if c<=0: continue
        print(f"   d+{do:<6} {side:4} {c:9,.0f} {p:9,.0f} {100*(p-c)/c:7.1f}")

# ---------------- 6. EDGE SIGNATURE (over-dispersion proof) ----------------
print("\n" + "="*92); print("6. EDGE SIGNATURE — WR vs implied price (the dispersion harvest)"); print("="*92)
def edge_table(bset, edges, lbl):
    print(f"{lbl}:")
    for lo,hi in zip(edges,edges[1:]):
        sh=shw=pxsh=0.0; n=0; unres=0.0
        for r in bset:
            if not (lo<=r['price']<hi): continue
            w=winner(r['conditionId']); n+=1
            if w is None: unres+=r['size']; continue
            sh+=r['size']; pxsh+=r['price']*r['size']
            if w==r['outcomeIndex']: shw+=r['size']
        if sh<=0: continue
        wr=shw/sh; avg=pxsh/sh
        print(f"   px[{lo:.2f},{hi:.2f}) n={n:6,} WR={wr:.3f} impl={avg:.3f} edge={100*(wr-avg):+5.1f}% "
              f"ROI~{100*(shw-pxsh)/pxsh:+6.1f}%")
edge_table(yes_buys,[0,.05,.10,.15,.22,.30,.40,.45,.55,1.01],"YES")
edge_table(no_buys,[.35,.45,.52,.65,.75,.85,.95,1.01],"NO")

# ---------------- 7. RECYCLE / MERGE / TURNOVER ----------------
print("\n" + "="*92); print("7. RECYCLE — merge + redeem velocity"); print("="*92)
merges=[r for r in wx if r['type']=='MERGE']; redeems=[r for r in wx if r['type']=='REDEEM']
print(f"MERGE: n={len(merges):,} ${sum(r['usdcSize'] for r in merges):,.0f}   "
      f"REDEEM: n={len(redeems):,} ${sum(r['usdcSize'] for r in redeems):,.0f}")
# pair co-fill: cids with both YES and NO buys
cid_y=set(r['conditionId'] for r in yes_buys); cid_n=set(r['conditionId'] for r in no_buys)
both_cid=cid_y & cid_n
print(f"buckets with BOTH YES+NO buys (pair-quote): {len(both_cid):,}/{len(cid_y|cid_n):,} "
      f"({100*len(both_cid)/len(cid_y|cid_n):.0f}%) -> mergeable to $1")
# same-day recycle: merge$+redeem$ vs buy$ by day
print("daily recycle ratio (merge$+redeem$ as % of that day's buy$):")
dd=defaultdict(lambda:[0.0,0.0,0.0])
for r in buys: dd[day(r['timestamp'])][0]+=r['usdcSize']
for r in merges: dd[day(r['timestamp'])][1]+=r['usdcSize']
for r in redeems: dd[day(r['timestamp'])][2]+=r['usdcSize']
for d in sorted(dd)[-7:]:
    b,m,rd=dd[d]
    print(f"   {d}: buy${b:8,.0f} merge${m:7,.0f} redeem${rd:7,.0f}  recycle={100*(m+rd)/b if b else 0:4.0f}%")

# ---------------- 8. YES->NO TIMING (when NO is added) ----------------
print("\n" + "="*92); print("8. YES->NO SWITCH — when in market life he adds NO"); print("="*92)
lags=[]
fy=defaultdict(lambda:1e11); fn=defaultdict(lambda:1e11)
for r in yes_buys: fy[r['conditionId']]=min(fy[r['conditionId']],int(r['timestamp']))
for r in no_buys: fn[r['conditionId']]=min(fn[r['conditionId']],int(r['timestamp']))
for c in both_cid:
    lags.append((fn[c]-fy[c])/3600)
if lags:
    lags.sort()
    print(f"first-NO minus first-YES (h), same bucket: median {st.median(lags):+.2f}h "
          f"p25 {lags[int(.25*len(lags))]:+.1f} p75 {lags[int(.75*len(lags))]:+.1f}  "
          f"(+ = NO added later/lockout-style)")
# market-life fraction at fill: need market start; use event first-fill as proxy
print("intraday: median fill happens at what fraction of his own holding window per bucket")

# ---------------- 9. EQUITY / GROWTH CURVE ----------------
print("\n" + "="*92); print("9. EQUITY CURVE — the 200 -> 15k+ growth"); print("="*92)
# cash flow: -buy +sell +redeem +merge +reward ; mtm of open positions at cost
flow=defaultdict(float);
for r in wx:
    d=day(r['timestamp']); t=r['type']
    if t=='TRADE':
        flow[d]+= (-r['usdcSize'] if r['side']=='BUY' else r['usdcSize'])
    elif t in('REDEEM','MERGE','REWARD','MAKER_REBATE'):
        flow[d]+=r['usdcSize']
# realized PnL by resolution day (hold-to-resolution on net held)
B=defaultdict(lambda:{'yc':0.0,'nc':0.0,'ys':0.0,'ns':0.0,'ysell':0.0,'nsell':0.0,'red':0.0,'mrg':0.0,'ms':0.0})
for r in wx:
    b=B[r['conditionId']]; t=r['type']; u=r.get('usdcSize',0) or 0; s=r.get('size',0) or 0
    if t=='TRADE':
        sd='y' if r['outcomeIndex']==0 else 'n'
        if r['side']=='BUY': b[sd+'c']+=u; b[sd+'s']+=s
        else: b[sd+'sell']+=u
    elif t=='REDEEM': b['red']+=u
    elif t=='MERGE': b['mrg']+=u; b['ms']+=s
resday=defaultdict(lambda:[0.0,0.0,0])
cum_cf=0.0; days=sorted(flow)
for cid,b in B.items():
    w=winner(cid)
    if w is None: continue
    cost=b['yc']+b['nc'];
    if cost<=0: continue
    cashback=b['ysell']+b['nsell']+b['red']+b['mrg']
    if w==0: held=max(0.0,b['ys']-b['ms']-b['red'])
    else: held=max(0.0,b['ns']-b['ms']-b['red'])
    # note: red counted as cash already; held excludes redeemed
    pnl=cashback+held-cost
    ed=_slug_date(CID_SLUG.get(cid,''))
    if ed: resday[ed][0]+=pnl; resday[ed][1]+=cost; resday[ed][2]+=1
cum=0.0
print(f"{'res_day':11} {'n':>4} {'cost$':>9} {'pnl$':>8} {'ROI%':>6} {'cumPnL$':>9}")
for d in sorted(resday):
    if d<'2026-05-17' or d>'2026-06-17': continue
    p,c,n=resday[d]; cum+=p
    print(f"   {d:11} {n:>4} {c:9,.0f} {p:8,.0f} {100*p/c if c else 0:6.1f} {cum:9,.0f}")
tc=sum(v[1] for d,v in resday.items() if '2026-05-17'<=d<='2026-06-17')
tp=sum(v[0] for d,v in resday.items() if '2026-05-17'<=d<='2026-06-17')
print(f"   RESOLVED TOTAL: cost ${tc:,.0f}  pnl ${tp:,.0f}  ROI {100*tp/tc:.1f}%")
# deploy + turnover
print("\ndaily deploy$ + #buys + cities + events (breadth):")
de=defaultdict(lambda:[0.0,0,set(),set()])
for r in buys:
    d=day(r['timestamp']); de[d][0]+=r['usdcSize']; de[d][1]+=1
    de[d][2].add(city_of(r.get('slug'))); de[d][3].add(r.get('eventSlug'))
for d in sorted(de):
    if d<'2026-05-17': continue
    x=de[d]; print(f"   {d}: deploy${x[0]:9,.0f}  buys={x[1]:5,}  cities={len(x[2]):2}  events={len(x[3]):3}")
