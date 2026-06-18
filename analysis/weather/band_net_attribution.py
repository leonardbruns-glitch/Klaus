#!/usr/bin/env python3
"""NET realized band PnL — joins the TWO streams that live in different files
(the split that made profitability unreadable for 2 weeks):

  LOSERS / held-to-resolution : logs/trades.jsonl  (asset=WEATHER, exit_reason STWA_RESOLVED etc.)
  WINNERS / sold early @0.99  : logs/shadow/hot/<day>/exit099_live.jsonl (record=recycle099)

A position is in exactly ONE stream (sold via RECYCLE099 OR held to resolution) — no double-count.
Reports NET (winner+loser) by entry-price bucket, by side, and by resolution day, with cost basis
=> true realized ROI. This is the clean measurement to read after the 2026-06-18 config FREEZE.

Usage: python3 analysis/weather/band_net_attribution.py [days_back]   (default 14)
Run on the VPS (where the logs live). No network, no deps.
"""
import json, time, glob, sys
from collections import defaultdict

DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 else 14
CUT = time.time() - DAYS_BACK * 86400
PX_EDGES = [0, 0.03, 0.05, 0.10, 0.15, 0.22, 0.30, 0.45, 0.55, 0.75, 1.01]

def pxbucket(p):
    for lo, hi in zip(PX_EDGES, PX_EDGES[1:]):
        if lo <= p < hi:
            return f"[{lo:.2f},{hi:.2f})"
    return "?"

def day_of(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(float(ts)))

# bucket -> [cost, net_pnl, n]   ; also by side and by day
by_px   = defaultdict(lambda: [0.0, 0.0, 0])
by_side = defaultdict(lambda: [0.0, 0.0, 0])
by_day  = defaultdict(lambda: [0.0, 0.0, 0])   # [cost, net, n]
streams = defaultdict(lambda: [0.0, 0])         # stream label -> [net, n]

# ---- 1) LOSER / held-to-resolution stream (trades.jsonl) ----
for l in open("/root/Klaus/logs/trades.jsonl"):
    try:
        r = json.loads(l)
    except Exception:
        continue
    if r.get("asset") != "WEATHER":
        continue
    ts = r.get("ts_close") or r.get("ts_open")
    if not ts or float(ts) < CUT:
        continue
    side = "YES" if "YES" in str(r.get("direction", "")).upper() else "NO"
    cost = float(r.get("stake") or 0.0)
    pnl  = float(r.get("net_pnl") or 0.0)
    px   = float(r.get("entry_price") or 0.0)
    b = pxbucket(px); d = day_of(ts)
    by_px[b][0]+=cost; by_px[b][1]+=pnl; by_px[b][2]+=1
    by_side[side][0]+=cost; by_side[side][1]+=pnl; by_side[side][2]+=1
    by_day[d][0]+=cost; by_day[d][1]+=pnl; by_day[d][2]+=1
    streams["held_to_resolution"][0]+=pnl; streams["held_to_resolution"][1]+=1

# ---- 2) WINNER / RECYCLE099 stream (exit099_live.jsonl) ----
for f in glob.glob("/root/Klaus/logs/shadow/hot/*/exit099_live.jsonl"):
    for l in open(f):
        try:
            r = json.loads(l)
        except Exception:
            continue
        if r.get("record") != "recycle099":
            continue
        ts = r.get("ts")
        if not ts or float(ts) < CUT:
            continue
        entry = float(r.get("entry") or 0.0)
        shares = float(r.get("shares") or 0.0)
        pnl = float(r.get("pnl") or 0.0)
        cost = entry * shares
        side = "YES" if entry < 0.45 else "NO"   # band YES enters <0.45; favorite-NO enters >=0.45
        b = pxbucket(entry); d = day_of(ts)
        by_px[b][0]+=cost; by_px[b][1]+=pnl; by_px[b][2]+=1
        by_side[side][0]+=cost; by_side[side][1]+=pnl; by_side[side][2]+=1
        by_day[d][0]+=cost; by_day[d][1]+=pnl; by_day[d][2]+=1
        streams["recycle099_winner"][0]+=pnl; streams["recycle099_winner"][1]+=1

def roi(c, p):
    return f"{100*p/c:+6.1f}%" if c else "   n/a"

print(f"=== NET realized band attribution (last {DAYS_BACK}d, both streams joined) ===\n")
print("STREAMS:")
tot_net = 0.0
for k, v in sorted(streams.items()):
    print(f"  {k:22} net={v[0]:+9.2f}  n={v[1]}")
    tot_net += v[0]
print(f"  {'TOTAL NET':22} net={tot_net:+9.2f}\n")

print(f"NET by ENTRY-PRICE bucket  (cost = held stake + 099 entry*shares):")
print(f"  {'px':14} {'cost$':>9} {'net$':>9} {'ROI':>8} {'n':>5}")
for b in sorted(by_px):
    c, p, n = by_px[b]
    print(f"  {b:14} {c:>9.2f} {p:>+9.2f} {roi(c,p):>8} {n:>5}")

print(f"\nNET by SIDE:")
for s in ("YES", "NO"):
    c, p, n = by_side[s]
    print(f"  {s}: cost={c:9.2f} net={p:+9.2f} ROI={roi(c,p)} n={n}")

print(f"\nNET by RESOLUTION DAY (combined):")
print(f"  {'day':12} {'cost$':>9} {'net$':>9} {'ROI':>8} {'n':>5}")
cum = 0.0
for d in sorted(by_day):
    c, p, n = by_day[d]; cum += p
    print(f"  {d:12} {c:>9.2f} {p:>+9.2f} {roi(c,p):>8} {n:>5}   cum={cum:+8.2f}")
