#!/usr/bin/env python3
"""Resolutions for act_31d conditionIds + taker /trades (offset-paginated)."""
import json, time, urllib.request, sys
W = "0x8fbd7cf5f806f563080864694415829f7229a959"
CUTOFF = 1778976000
D = "analysis/weather/badatmath_audit/"

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

act = [json.loads(l) for l in open(D + "act_31d.jsonl")]

# ---- taker trades via offset ----
seen = set(); trd = []; offset = 0
while offset < 60000:
    batch = get(f"https://data-api.polymarket.com/trades?user={W}&limit=500&offset={offset}")
    if not batch: break
    stop = False
    for x in batch:
        if int(x["timestamp"]) < CUTOFF:
            stop = True; continue
        k = (x.get("transactionHash"), x.get("asset"), x.get("side"), int(x["timestamp"]), x.get("size"))
        if k in seen: continue
        seen.add(k); trd.append(x)
    if len(batch) < 500 or stop: break
    offset += 500
with open(D + "trd_31d.jsonl", "w") as f:
    for r in trd: f.write(json.dumps(r) + "\n")
if trd:
    tmin = time.strftime("%m-%d", time.gmtime(min(int(r['timestamp']) for r in trd)))
    tmax = time.strftime("%m-%d", time.gmtime(max(int(r['timestamp']) for r in trd)))
    print(f"TAKER trades: {len(trd)} rows {tmin}->{tmax}")
else:
    print("TAKER trades: 0")

# ---- resolutions ----
cids = sorted({r["conditionId"] for r in act if r.get("conditionId")})
print(f"unique conditionIds: {len(cids)}")
res = {}; B = 20
for i in range(0, len(cids), B):
    chunk = cids[i:i+B]
    qs = "&".join(f"condition_ids={c}" for c in chunk)
    data = get(f"https://gamma-api.polymarket.com/markets?{qs}&limit=100")
    if not data: continue
    for m in data:
        cid = m.get("conditionId")
        if cid:
            res[cid] = {"closed": m.get("closed"), "outcomePrices": m.get("outcomePrices"),
                        "outcomes": m.get("outcomes"), "slug": m.get("slug"),
                        "endDate": m.get("endDate"), "umaResolutionStatus": m.get("umaResolutionStatus")}
    if (i // B) % 25 == 0:
        print(f"  res {i+len(chunk)}/{len(cids)}", file=sys.stderr)
    time.sleep(0.04)
with open(D + "res_31d.json", "w") as f: json.dump(res, f)
closed = sum(1 for v in res.values() if v.get("closed"))
print(f"RESOLUTIONS: {len(res)} markets ({closed} closed)")
