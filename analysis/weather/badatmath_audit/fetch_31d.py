#!/usr/bin/env python3
"""Fresh 31-day pull of badatmath: /activity (all fills), /trades (taker-only),
+ gamma resolutions. Window = May 17 00:00 UTC -> now. For the definitive teardown."""
import json, time, urllib.request, sys

W = "0x8fbd7cf5f806f563080864694415829f7229a959"
CUTOFF = 1778976000  # 2026-05-17 00:00 UTC
D = "analysis/weather/badatmath_audit/"
ACT_OUT = D + "act_31d.jsonl"
TRD_OUT = D + "trd_31d.jsonl"
RES_OUT = D + "res_31d.json"

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

def walk(endpoint, keyfn):
    seen = set(); rows = []; end = int(time.time()) + 60; pages = 0
    while True:
        url = f"https://data-api.polymarket.com/{endpoint}?user={W}&limit=500&end={end}"
        batch = get(url)
        if not batch: break
        pages += 1
        for x in batch:
            k = keyfn(x)
            if k in seen: continue
            seen.add(k); rows.append(x)
        last_ts = min(int(x["timestamp"]) for x in batch)
        if pages % 15 == 0:
            print(f"  {endpoint} p{pages}: {len(rows)} rows @ {time.strftime('%m-%d %H:%M', time.gmtime(last_ts))}", file=sys.stderr)
        if last_ts <= CUTOFF: break
        nxt = last_ts - 1
        if nxt >= end: nxt = end - 1
        end = nxt
        if len(batch) < 500 and last_ts > CUTOFF: break
    rows = [r for r in rows if int(r["timestamp"]) >= CUTOFF]
    rows.sort(key=lambda x: int(x["timestamp"]))
    return rows

# ---- activity (all fills + merge/redeem/reward) ----
act = walk("activity", lambda x: (x.get("transactionHash"), x.get("asset"), x.get("side"), int(x["timestamp"]), x.get("size"), x.get("type")))
with open(ACT_OUT, "w") as f:
    for r in act: f.write(json.dumps(r) + "\n")
tmin = time.strftime("%Y-%m-%d %H:%M", time.gmtime(min(int(r['timestamp']) for r in act)))
tmax = time.strftime("%Y-%m-%d %H:%M", time.gmtime(max(int(r['timestamp']) for r in act)))
print(f"ACTIVITY: {len(act)} rows {tmin} -> {tmax} -> {ACT_OUT}")

# ---- trades (taker-only) ----
trd = walk("trades", lambda x: (x.get("transactionHash"), x.get("asset"), x.get("side"), int(x["timestamp"]), x.get("size")))
with open(TRD_OUT, "w") as f:
    for r in trd: f.write(json.dumps(r) + "\n")
print(f"TRADES(taker): {len(trd)} rows -> {TRD_OUT}")

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
    time.sleep(0.04)
with open(RES_OUT, "w") as f: json.dump(res, f)
closed = sum(1 for v in res.values() if v.get("closed"))
print(f"RESOLUTIONS: {len(res)} markets ({closed} closed) -> {RES_OUT}")
