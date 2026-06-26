#!/usr/bin/env python3
"""Pull trades (taker-only, offset-paginated) + resolutions for onlylucknobrain.
act.jsonl already pulled. Trades endpoint ignores end= cursor -> use offset."""
import json, time, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor

W = "0x6a8d1709bfb718d8555d315a983c4816278350f9"
CUTOFF = 1774310400  # 2026-03-21
D = "analysis/weather/onlyluck_audit/"

def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "klaus-audit/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url[:90], e, file=sys.stderr); return None
            time.sleep(1.5 * (i + 1))
    return None

# ---- trades via offset ----
trd=[]; seen=set(); off=0
while True:
    b=get(f"https://data-api.polymarket.com/trades?user={W}&limit=500&offset={off}")
    if not b: break
    new=0
    for x in b:
        k=(x.get('transactionHash'),x.get('asset'),x.get('side'),int(x['timestamp']),round(float(x.get('size',0) or 0),4))
        if k in seen: continue
        seen.add(k); trd.append(x); new+=1
    last=min(int(x['timestamp']) for x in b)
    off+=500
    if off % 5000 == 0:
        print(f"  trades off{off}: {len(trd)} rows @ {time.strftime('%m-%d %H:%M',time.gmtime(last))}", file=sys.stderr, flush=True)
    if last <= CUTOFF or len(b) < 500: break
trd=[r for r in trd if int(r['timestamp'])>=CUTOFF]
trd.sort(key=lambda x:int(x['timestamp']))
with open(D+"trd.jsonl","w") as f:
    for r in trd: f.write(json.dumps(r)+"\n")
print(f"TRADES(taker): {len(trd)} rows -> trd.jsonl", flush=True)

# ---- resolutions ----
act=[json.loads(l) for l in open(D+"act.jsonl")]
cids=sorted({r["conditionId"] for r in act if r.get("conditionId")})
print(f"unique conditionIds: {len(cids)}", flush=True)
res={}; B=20
for i in range(0,len(cids),B):
    chunk=cids[i:i+B]
    qs="&".join(f"condition_ids={c}" for c in chunk)
    data=get(f"https://gamma-api.polymarket.com/markets?{qs}&limit=100")
    if data:
        for m in data:
            cid=m.get("conditionId")
            if cid:
                res[cid]={"closed":m.get("closed"),"outcomePrices":m.get("outcomePrices"),
                          "outcomes":m.get("outcomes"),"slug":m.get("slug")}
    if i % 400 == 0:
        print(f"  res {i}/{len(cids)}", file=sys.stderr, flush=True)
def clob_winner(cid):
    d=get(f"https://clob.polymarket.com/markets/{cid}")
    if not d: return None
    win=[t for t in (d.get("tokens") or []) if t.get("winner")]
    return {"winner_outcome":win[0].get("outcome")} if win else None
missing=[c for c in cids if c not in res or not res[c].get("closed")]
print(f"CLOB fallback for {len(missing)} markets", flush=True)
with ThreadPoolExecutor(max_workers=10) as ex:
    futs={ex.submit(clob_winner,c):c for c in missing}
    for fut in futs:
        c=futs[fut]; w=fut.result()
        if w: res.setdefault(c,{}).update(w)
json.dump(res,open(D+"res.json","w"))
print(f"RESOLUTIONS: {len(res)} -> res.json", flush=True)
print("DONE", flush=True)
