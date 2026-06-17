#!/usr/bin/env python3
"""Unified winner map for the 31-day window: merge old gamma resolutions +
fetch missing recent cids from CLOB /markets/{cid} (authoritative tokens[].winner).
Output: winners_31d.json = {cid: 0|1}  (0=YES won, 1=NO won; absent=unresolved)."""
import json, time, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor
D = "analysis/weather/badatmath_audit/"
act = [json.loads(l) for l in open(D + "act_31d.jsonl")]
cids = sorted({r["conditionId"] for r in act
               if r.get("conditionId") and 'temperature' in (r.get('title') or '').lower()})

win = {}
# 1. from old gamma files (outcomePrices[0]>0.5 => YES won)
for f in ['resolutions_window.json', 'resolutions.json']:
    try: old = json.load(open(D + f))
    except FileNotFoundError: continue
    for cid, v in old.items():
        if cid in win or not v.get('closed'): continue
        try:
            p = json.loads(v['outcomePrices'])
            win[cid] = 0 if float(p[0]) > 0.5 else 1
        except: pass
print(f"from gamma files: {len(win)} winners", file=sys.stderr)

missing = [c for c in cids if c not in win]
print(f"missing -> CLOB: {len(missing)}", file=sys.stderr)

def fetch(cid):
    url = f"https://clob.polymarket.com/markets/{cid}"
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "klaus/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.load(r)
            if not d.get('closed'): return (cid, None)
            for t in d.get('tokens', []):
                if t.get('winner'):
                    return (cid, 0 if t.get('outcome') == 'Yes' else 1)
            return (cid, None)
        except Exception:
            time.sleep(0.5 * (i + 1))
    return (cid, None)

done = 0
with ThreadPoolExecutor(max_workers=12) as ex:
    for cid, w in ex.map(fetch, missing):
        done += 1
        if w is not None: win[cid] = w
        if done % 200 == 0: print(f"  clob {done}/{len(missing)}  total winners {len(win)}", file=sys.stderr)

json.dump(win, open(D + "winners_31d.json", "w"))
print(f"WINNERS: {len(win)} resolved of {len(cids)} weather cids -> winners_31d.json")
