import json, glob, re, statistics
from collections import defaultdict
MONTH={'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,
       'august':8,'september':9,'october':10,'november':11,'december':12}
# 1) index Klaus PRE_PEAK p_cal by (city,date,lo,hi)
pidx=defaultdict(list)
for f in glob.glob('logs/shadow/hot/2026-0[56]-*/stwa_pricer_eval.jsonl'):
    date=f.split('/')[3]
    with open(f) as fh:
        for l in fh:
            try: r=json.loads(l)
            except: continue
            if r.get('phase')!='PRE_PEAK': continue
            key=(r['city'],date,round(r['lo'],1),round(r['hi'],1))
            pidx[key].append(r['p_cal'])
pmed={k:statistics.median(v) for k,v in pidx.items()}
print("pricer buckets indexed:", len(pmed))
# 2) resolutions
res=json.load(open("analysis/weather/badatmath_audit/resolutions.json"))
def winner(cid):
    v=res.get(cid);
    if not v or not v.get('closed'): return None
    try:
        p=json.loads(v['outcomePrices'])
        return 0 if float(p[0])>0.5 else (1 if float(p[1])>0.5 else None)
    except: return None
# 3) walk badatmath °C YES fills, join
SLUG=re.compile(r'highest-temperature-in-(.+?)-on-([a-z]+)-(\d+)-2026-(\d+)c$')
rows=[json.loads(l) for l in open("analysis/weather/badatmath_audit/activity_raw.jsonl")]
joined=[]
for x in rows:
    if x['type']!='TRADE' or x.get('side')!='BUY' or x.get('outcome')!='Yes': continue
    m=SLUG.match(x.get('slug','') or '')
    if not m: continue
    city,mon,day,deg=m.group(1),m.group(2),int(m.group(3)),int(m.group(4))
    if mon not in MONTH: continue
    date=f"2026-{MONTH[mon]:02d}-{day:02d}"
    lo,hi=round(deg-0.5,1),round(deg+0.5,1)
    pc=pmed.get((city,date,lo,hi))
    if pc is None: continue
    w=winner(x['conditionId'])
    if w is None: continue
    joined.append({"px":float(x['price']),"sz":float(x['size']),"u":float(x['usdcSize']),
                   "won":int(x.get('outcomeIndex')==w),"pcal":pc})
print("joined YES fills:", len(joined))
# 4) THE TEST: within the underpriced band, does p_cal>market discriminate?
def stats(fills):
    if not fills: return (0,0,0,0,0)
    n=len(fills); sh=sum(f['sz'] for f in fills); c=sum(f['u'] for f in fills)
    wsh=sum(f['sz'] for f in fills if f['won']); 
    wr=wsh/sh if sh else 0; impl=c/sh if sh else 0; roi=100*(wsh-c)/c if c else 0
    return n,sh,wr,impl,roi
for lo_band,hi_band,lbl in [(0.10,0.45,"YES BAND 0.10-0.45"),(0.10,0.50,"0.10-0.50"),(0.05,0.45,"0.05-0.45")]:
    band=[f for f in joined if lo_band<=f['px']<hi_band]
    over=[f for f in band if f['pcal']>f['px']]      # Klaus: underpriced (buy)
    under=[f for f in band if f['pcal']<=f['px']]     # Klaus: not
    print(f"\n=== {lbl}  (n={len(band)}) ===")
    for nm,grp in [("p_cal>mkt (KLAUS BUY)",over),("p_cal<=mkt (KLAUS SKIP)",under)]:
        n,sh,wr,impl,roi=stats(grp)
        print(f"  {nm:24} n={n:5d} WR={100*wr:5.1f}% implied={100*impl:5.1f}% ROI={roi:6.1f}%")

print("\n############ ROBUSTNESS ############")
band=[f for f in joined if 0.10<=f['px']<0.45]
# within price thirds, compare over vs under
for lo,hi in [(0.10,0.18),(0.18,0.28),(0.28,0.45)]:
    sub=[f for f in band if lo<=f['px']<hi]
    over=[f for f in sub if f['pcal']>f['px']]; under=[f for f in sub if f['pcal']<=f['px']]
    def roi(g):
        c=sum(f['u'] for f in g); w=sum(f['sz'] for f in g if f['won'])
        return (len(g),100*(w-c)/c if c else 0)
    no,ro=roi(over); nu,ru=roi(under)
    print(f"  px[{lo:.2f},{hi:.2f}): p_cal>mkt n={no:4d} ROI={ro:6.1f}% | p_cal<=mkt n={nu:4d} ROI={ru:6.1f}%")
# blind band ROI for reference
c=sum(f['u'] for f in band); w=sum(f['sz'] for f in band if f['won'])
print(f"\n  BLIND band 0.10-0.45: n={len(band)} ROI={100*(w-c)/c:.1f}%  (badatmath actual)")
und=[f for f in band if f['pcal']<=f['px']]
c2=sum(f['u'] for f in und); w2=sum(f['sz'] for f in und if f['won'])
print(f"  INVERSE-FILTER (skip p_cal>mkt): n={len(und)} ROI={100*(w2-c2)/c2:.1f}%  <-- Klaus-improvable?")
# how often is p_cal floored to 0 (lockout) in the band — artifact check
nz=sum(1 for f in band if f['pcal']<=0.001)
print(f"  p_cal~0 (floored) in band: {nz}/{len(band)} = {100*nz/len(band):.1f}%")
