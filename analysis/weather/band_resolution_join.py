#!/usr/bin/env python3
"""STRUCT-BAND (badatmath copy) resolution validator — the n>=100 gate for BAND_LIVE.

Reads the multi-day band shadow fires (logs/shadow/hot/<date>/band_struct.jsonl,
record=md_shadow, reason=fire), joins each would-post YES leg to its Gamma
resolution by conditionId, and reports realized WR / ROI vs the QUOTED bid price
(what we would actually pay as a maker). This is the decisive gate: flip BAND_LIVE
only when the joined band ROI is positive at n>=100 (per CLAUDE.md discipline).

Honest about what it measures: WR at OUR (city,date,bucket) selection vs our quote.
It does NOT model fill probability — a resting maker bid below the ask may never
fill. Treat the ROI here as the edge CONDITIONAL on a fill; capacity/fill-rate is
a separate question (measure from maker_exercise.jsonl once BAND_LIVE is on).

Usage:  python3 analysis/weather/band_resolution_join.py
"""
import json, glob, urllib.request, time
from collections import defaultdict

def get(url):
    for _ in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.0)
    return None

def winner(op):
    try:
        p = json.loads(op)
        if float(p[0]) > 0.5: return 0
        if float(p[1]) > 0.5: return 1
    except Exception:
        pass
    return None

# 1) collect would-post YES legs from every band_struct fire
legs = []
for f in sorted(glob.glob("logs/shadow/hot/*/band_struct.jsonl")):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("record") != "md_shadow" or r.get("reason") != "fire":
            continue
        for q in r.get("quotes", []):
            cid = q.get("cid")
            if not cid: continue
            legs.append({"cid": cid, "bid": float(q["bid_quote"]),
                         "ask": float(q["ask"]), "off": q.get("off"),
                         "days_out": r.get("days_out"), "city": r.get("city")})
print(f"band fire legs (with cid): {len(legs)}  unique markets: {len(set(l['cid'] for l in legs))}")
if not legs:
    print("no joinable legs yet — data-collection mode (shadow just started).")
    raise SystemExit

# 2) fetch resolutions (YES is outcomeIndex 0 in these markets)
cids = sorted(set(l["cid"] for l in legs))
res = {}
B = 20
for i in range(0, len(cids), B):
    q = "&".join(f"condition_ids={c}" for c in cids[i:i+B])
    d = get(f"https://gamma-api.polymarket.com/markets?{q}&closed=true&limit=200")
    if d:
        for m in d:
            res[m.get("conditionId")] = winner(m.get("outcomePrices"))

# 3) realized WR / ROI vs the quoted bid (YES wins iff outcomeIndex 0 wins)
def report(rows, label):
    rows = [r for r in rows if res.get(r["cid"]) is not None]
    if not rows:
        print(f"  {label}: 0 resolved"); return
    n = len(rows)
    cost = sum(r["bid"] for r in rows)          # 1 share/leg notional
    win = sum(1 for r in rows if res[r["cid"]] == 0)
    payoff = win                                 # winners pay $1/share
    wr = win / n; impl = cost / n; roi = 100*(payoff-cost)/cost if cost else 0
    print(f"  {label:22} n={n:5d} WR={100*wr:5.1f}% quote={impl:5.3f} ROI={roi:6.1f}%")

print(f"\nresolved legs: {sum(1 for l in legs if res.get(l['cid']) is not None)} / {len(legs)}")
print("REALIZED (vs our maker quote, conditional on fill):")
report(legs, "ALL band legs")
for d in sorted(set(l["days_out"] for l in legs)):
    report([l for l in legs if l["days_out"] == d], f"days_out={d}")
for o in sorted(set(l["off"] for l in legs if l["off"] is not None)):
    report([l for l in legs if l["off"] == o], f"offset±{o} from mode")

nres = sum(1 for l in legs if res.get(l['cid']) is not None)
print(f"\nGATE: BAND_LIVE flip needs ROI>0 at n>=100. current resolved n={nres} "
      f"=> {'DATA-COLLECTION (n<40)' if nres<40 else 'TREND ONLY (40<=n<100)' if nres<100 else 'DECISION-READY'}")
