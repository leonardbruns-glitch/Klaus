"""Find ColdMath's wallet from on-chain /trades, then pull + analyze full history."""
from __future__ import annotations
import json, glob, time, urllib.request, collections

DATA="https://data-api.polymarket.com"
def get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.0)
    return []

# 1) candidate cids from the LAST 2 days only (recent active markets), target cities
TARGET={"Atlanta","Dallas","Cape Town","Buenos Aires","Sao Paulo","Austin","Houston","Miami"}
cids=collections.OrderedDict()
for fp in sorted(glob.glob("logs/shadow/hot/2026-06-0[67]/metar_lockout.jsonl")):
    for l in open(fp):
        try: d=json.loads(l)
        except: continue
        c=d.get("city"); cid=d.get("condition_id")
        if c in TARGET and cid: cids.setdefault(cid,c)
cids=collections.OrderedDict(list(cids.items())[:30])
print(f"candidate markets (recent, target cities): {len(cids)}",flush=True)

# 2) scan FIRST PAGE only (ColdMath is high-volume -> appears early) -> wallet
wallet=None; who=None
for i,(cid,city) in enumerate(cids.items()):
    rows=get(f"{DATA}/trades?market={cid}&limit=500")
    print(f"  [{i+1}/{len(cids)}] {city} {cid[:10]} trades={len(rows)}",flush=True)
    for t in rows:
        nm=(t.get("name") or "")+"|"+(t.get("pseudonym") or "")
        if "cold" in nm.lower():
            wallet=t.get("proxyWallet"); who=nm
            print(f"FOUND name='{nm}' wallet={wallet} in {city}",flush=True)
            break
    if wallet: break

if not wallet:
    print("no 'cold' name found in target-city markets we track. "
          "ColdMath may trade cities/markets not in our logs — need a wider market list.")
    raise SystemExit

# 3) full history via ?user=
print(f"\n=== pulling full history for {who} {wallet} ===")
all_t=[]; off=0
while off<20000:
    rows=get(f"{DATA}/trades?user={wallet}&limit=500&offset={off}")
    if not rows: break
    all_t+=rows
    if len(rows)<500: break
    off+=500
print(f"total trades pulled: {len(all_t)}")
if not all_t: raise SystemExit

# 4) analyze: side, outcome, entry price band, by title keyword
buys=[t for t in all_t if (t.get("side")=="BUY")]
print(f"BUY trades: {len(buys)}  SELL: {len(all_t)-len(buys)}")
# outcome split on BUYs
oc=collections.Counter(t.get("outcome") for t in buys)
print("BUY outcome split:",dict(oc))
# entry price band on BUYs
band=collections.Counter()
for t in buys:
    p=float(t.get("price") or 0)
    for b in [0.1,0.2,0.3,0.5,0.7,0.85,1.01]:
        if p<b: band[f"<{b}"]+=1; break
print("BUY price bands:",dict(sorted(band.items())))
# weather vs other (title contains temperature/highest)
wx=[t for t in buys if any(k in (t.get("title") or "").lower() for k in ("temperature","highest","weather","°","degrees"))]
print(f"weather BUYs: {len(wx)} / {len(buys)}")
# size-weighted price band (where's the capital)
import collections as C
val=C.defaultdict(float)
for t in buys:
    p=float(t.get("price") or 0); s=float(t.get("size") or 0)
    for b in [0.1,0.2,0.3,0.5,0.7,0.85,1.01]:
        if p<b: val[f"<{b}"]+=p*s; break
print("BUY $ by price band:",{k:round(v) for k,v in sorted(val.items())})
# sample recent weather buys
print("\nsample recent weather BUYs:")
for t in sorted(wx,key=lambda x:-(x.get('timestamp') or 0))[:12]:
    print(f"  {t.get('outcome'):>3} p={t.get('price')} sz={t.get('size')} {str(t.get('title'))[:60]}")
