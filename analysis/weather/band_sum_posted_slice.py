#!/usr/bin/env python3
"""G7 slice: band shadow YES fires by sum_posted bucket + per-market-date regime table.

Same first-fire dedup + Gamma resolution join as band_resolution_join.py, but keeps
the fire-level sum_posted and market date so we can answer:
  (a) G7 — is the sum_posted [0.70,0.85] slice +EV with CI clearing zero?
  (b) regime — per market-date WR vs quote for the last week (dispersion check).

Usage:  PYTHONPATH=/root/Klaus python3 analysis/weather/band_sum_posted_slice.py
"""
import json, glob, math, urllib.request, time

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

def wilson(w, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = w / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (c-h, c+h)

raw = []
for f in sorted(glob.glob("logs/shadow/hot/*/band_struct.jsonl")):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("record") != "md_shadow" or r.get("reason") != "fire":
            continue
        ts = float(r.get("ts") or 0.0)
        for q in r.get("quotes", []):
            cid = q.get("cid")
            if not cid: continue
            raw.append({"cid": cid, "ts": ts, "bid": float(q["bid_quote"]),
                        "days_out": r.get("days_out"), "date": r.get("date"),
                        "sp": r.get("sum_posted"), "city": r.get("city")})
first = {}
for L in sorted(raw, key=lambda x: x["ts"]):
    first.setdefault((L["cid"], L["days_out"]), L)
legs = list(first.values())
print(f"YES legs: {len(raw)} raw -> {len(legs)} deduped")

cids = sorted(set(l["cid"] for l in legs))
res = {}
B = 20
for i in range(0, len(cids), B):
    q = "&".join(f"condition_ids={c}" for c in cids[i:i+B])
    d = get(f"https://gamma-api.polymarket.com/markets?{q}&closed=true&limit=200")
    if d:
        for m in d:
            res[m.get("conditionId")] = winner(m.get("outcomePrices"))

def report(rows, label):
    rows = [r for r in rows if res.get(r["cid"]) is not None]
    n = len(rows)
    if not n:
        print(f"  {label:28} 0 resolved"); return
    cost = sum(r["bid"] for r in rows)
    win = sum(1 for r in rows if res[r["cid"]] == 0)
    wr = win/n; impl = cost/n
    roi = 100*(win-cost)/cost if cost else 0.0
    lo, hi = wilson(win, n)
    roi_lo = 100*(lo-impl)/impl if impl else 0.0
    roi_hi = 100*(hi-impl)/impl if impl else 0.0
    print(f"  {label:28} n={n:5d} WR={100*wr:5.1f}% quote={impl:5.3f} "
          f"ROI={roi:7.1f}%  WilsonROI=[{roi_lo:+6.1f}%,{roi_hi:+6.1f}%]")

print("\n(a) G7 — YES legs by fire sum_posted bucket:")
buckets = [(0.0, 0.70, "sum_posted <0.70"),
           (0.70, 0.85, "sum_posted [0.70,0.85]"),
           (0.85, 9.9, "sum_posted >0.85")]
for lo, hi, lab in buckets:
    report([l for l in legs if l["sp"] is not None and lo <= l["sp"] < hi], lab)

print("\n(b) regime — YES legs by MARKET date (last 10 dates):")
dates = sorted(set(l["date"] for l in legs if l.get("date")))[-10:]
for d in dates:
    report([l for l in legs if l.get("date") == d], f"date {d}")
