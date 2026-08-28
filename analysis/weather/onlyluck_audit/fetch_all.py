#!/usr/bin/env python3
"""Full pull of onlylucknobrain (0x6a8d1709...) from late March 2026 -> now.
Mirrors the badatmath_audit recipe: /activity (all fills + merge/redeem/reward),
/trades (taker-only, for maker/taker anti-join), resolutions (gamma + CLOB winner)."""
import json, time, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor

W = "0x6a8d1709bfb718d8555d315a983c4816278350f9"
CUTOFF = 1774310400  # 2026-03-21 00:00 UTC (covers "late March"; walk stops at genesis if later)
D = "analysis/weather/onlyluck_audit/"
ACT_OUT = D + "act.jsonl"
TRD_OUT = D + "trd.jsonl"
RES_OUT = D + "res.json"

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
        if pages % 20 == 0:
            print(f"  {endpoint} p{pages}: {len(rows)} rows @ {time.strftime('%m-%d %H:%M', time.gmtime(last_ts))}", file=sys.stderr, flush=True)
        if last_ts <= CUTOFF: break
        nxt = last_ts - 1
        if nxt >= end: nxt = end - 1
        end = nxt
        if len(batch) < 500 and last_ts > CUTOFF: break
    rows = [r for r in rows if int(r["timestamp"]) >= CUTOFF]
    rows.sort(key=lambda x: int(x["timestamp"]))
    return rows

# ---- activity (all fills + MERGE/REDEEM/REWARD/SPLIT/CONVERSION) ----
act = walk("activity", lambda x: (x.get("transactionHash"), x.get("asset"), x.get("side"), int(x["timestamp"]), x.get("size"), x.get("type")))
with open(ACT_OUT, "w") as f:
    for r in act: f.write(json.dumps(r) + "\n")
tmin = time.strftime("%Y-%m-%d %H:%M", time.gmtime(min(int(r['timestamp']) for r in act)))
tmax = time.strftime("%Y-%m-%d %H:%M", time.gmtime(max(int(r['timestamp']) for r in act)))
print(f"ACTIVITY: {len(act)} rows {tmin} -> {tmax} -> {ACT_OUT}", flush=True)

# ---- trades (taker-only) ----
trd = walk("trades", lambda x: (x.get("transactionHash"), x.get("asset"), x.get("side"), int(x["timestamp"]), x.get("size")))
with open(TRD_OUT, "w") as f:
    for r in trd: f.write(json.dumps(r) + "\n")
print(f"TRADES(taker): {len(trd)} rows -> {TRD_OUT}", flush=True)

# ---- resolutions: gamma first, CLOB winner fallback ----
cids = sorted({r["conditionId"] for r in act if r.get("conditionId")})
print(f"unique conditionIds: {len(cids)}", flush=True)
res = {}; B = 20
for i in range(0, len(cids), B):
    chunk = cids[i:i+B]
    qs = "&".join(f"condition_ids={c}" for c in chunk)
    data = get(f"https://gamma-api.polymarket.com/markets?{qs}&limit=100")
    if data:
        for m in data:
            cid = m.get("conditionId")
            if cid:
                res[cid] = {"closed": m.get("closed"), "outcomePrices": m.get("outcomePrices"),
                            "outcomes": m.get("outcomes"), "slug": m.get("slug"),
                            "umaResolutionStatus": m.get("umaResolutionStatus")}
    if i % 200 == 0:
        print(f"  res {i}/{len(cids)}", file=sys.stderr, flush=True)

# CLOB winner fallback for any missing/unclosed
def clob_winner(cid):
    d = get(f"https://clob.polymarket.com/markets/{cid}")
    if not d: return None
    toks = d.get("tokens") or []
    win = [t for t in toks if t.get("winner")]
    if win:
        return {"winner_token": win[0].get("token_id"), "winner_outcome": win[0].get("outcome")}
    return None

missing = [c for c in cids if c not in res or not res[c].get("closed")]
print(f"CLOB fallback for {len(missing)} markets", flush=True)
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(clob_winner, c): c for c in missing}
    for fut in futs:
        c = futs[fut]
        w = fut.result()
        if w:
            res.setdefault(c, {}).update(w)
json.dump(res, open(RES_OUT, "w"))
print(f"RESOLUTIONS: {len(res)} -> {RES_OUT}", flush=True)
print("DONE", flush=True)
