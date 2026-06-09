#!/usr/bin/env python3
"""Live M1β (LOCKOUT-NO) resolution join — WR + realized PnL on actual fills.

Reads m1_beta_probe.jsonl result rows (real filled NO buys), joins to Gamma
resolution, collapses correlated fires at the condition_id (bucket) level so n
is honest. NO wins when the bucket resolves NO.

Run: python3 analysis/weather/m1_live_resolution.py   (read-only)
"""
import json, glob, datetime as dt, sys
sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events

# Optional post-fix cutoff: pass an epoch or ISO; only fills at/after are kept.
# Contamination fix landed 2026-05-29 04:11 UTC (commit 64d7ecb1).
CUTOFF = None
if len(sys.argv) > 1:
    a = sys.argv[1]
    if a.lower() in ("postfix", "post-fix"):
        CUTOFF = dt.datetime(2026, 5, 29, 4, 11, tzinfo=dt.timezone.utc).timestamp()
    else:
        try: CUTOFF = float(a)
        except Exception:
            CUTOFF = dt.datetime.fromisoformat(a.replace("Z", "+00:00")).timestamp()

# ---- load filled M1β buys ----------------------------------------------------
fills = []  # one per filled fire
skipped_precutoff = 0
for fp in sorted(glob.glob("logs/shadow/hot/*/m1_beta_probe.jsonl")):
    for line in open(fp):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("record_type") != "m1_beta_probe" or r.get("phase") != "result":
            continue
        if not r.get("filled"):
            continue
        if CUTOFF is not None:
            t = r.get("ts_completed") or r.get("ts_submitted") or 0
            if t < CUTOFF:
                skipped_precutoff += 1
                continue
        fills.append(r)
if CUTOFF is not None:
    print("CUTOFF: fills >= %s UTC (skipped %d pre-cutoff)"
          % (dt.datetime.utcfromtimestamp(CUTOFF).isoformat(), skipped_precutoff))
print("filled M1β fires:", len(fills))
if not fills:
    raise SystemExit("no filled fires")

# ---- date span -> fetch Gamma ------------------------------------------------
ts = [f.get("ts_completed") or f.get("ts_submitted") for f in fills if (f.get("ts_completed") or f.get("ts_submitted"))]
dmin = dt.datetime.utcfromtimestamp(min(ts)).strftime("%Y-%m-%d")
dmax = (dt.datetime.utcfromtimestamp(max(ts)) + dt.timedelta(days=3)).strftime("%Y-%m-%d")
print("fetching Gamma %s .. %s" % (dmin, dmax))
token_map, cond_map = fetch_weather_events(dmin, dmax)
print("  gamma: %d tokens, %d conds" % (len(token_map), len(cond_map)))

def no_won(cid, tok):
    """True/False/None: did NO resolve for this market?"""
    e = cond_map.get(cid) or token_map.get(str(tok))
    if not e or not e.get("closed"):
        return None
    p = e.get("outcomePrices") or []
    try:
        yes, no = float(p[0]), float(p[1])
    except Exception:
        return None
    if no >= 0.99:
        return True
    if no <= 0.01:
        return False
    return None  # ambiguous

# ---- per-fire PnL, then collapse to bucket cluster ---------------------------
# Bucket cluster = condition_id. NO fill: cost = price*shares; payoff = shares if NO won else 0.
clusters = {}   # cid -> {wins,total, pnl, shares, cost, city, fires, unresolved}
unresolved = nomatch = 0
for f in fills:
    cid = f.get("condition_id") or ""
    tok = f.get("no_token_id")
    w = no_won(cid, tok)
    price = float(f.get("fill_avg_price") or 0)
    shares = float(f.get("fill_size_shares") or 0)
    cost = price * shares
    c = clusters.setdefault(cid, {"city": f.get("city"), "fires": 0,
                                   "shares": 0.0, "cost": 0.0, "pnl": 0.0,
                                   "win": None, "resolved": False})
    c["fires"] += 1
    c["shares"] += shares
    c["cost"] += cost
    if w is None:
        if cid not in cond_map and str(tok) not in token_map:
            nomatch += 1
        else:
            unresolved += 1
        continue
    c["resolved"] = True
    c["win"] = w
    payoff = shares if w else 0.0
    c["pnl"] += (payoff - cost)

# ---- aggregate (cluster-level WR; PnL summed over resolved clusters) ---------
res = [c for c in clusters.values() if c["resolved"]]
nwin = sum(1 for c in res if c["win"])
pnl = sum(c["pnl"] for c in res)
cost = sum(c["cost"] for c in res)
print("\n=== M1β LIVE (LOCKOUT-NO) — bucket-cluster level ===")
print("resolved clusters:        %d" % len(res))
print("NO wins:                  %d  (WR %.1f%%)" % (nwin, 100*nwin/max(len(res),1)))
print("realized PnL:             $%+.2f" % pnl)
print("cost deployed (resolved): $%.2f" % cost)
print("ROI:                      %+.1f%%" % (100*pnl/cost if cost else 0))
print("unresolved/open clusters: %d   no_gamma_match fires: %d"
      % (sum(1 for c in clusters.values() if not c["resolved"]), nomatch))

# ---- losers (provenance check) -----------------------------------------------
losers = sorted([c for c in res if not c["win"]], key=lambda c: c["pnl"])
if losers:
    print("\n--- losing clusters (provenance suspects) ---")
    print("%-14s %6s %8s %8s" % ("city", "fires", "cost$", "pnl$"))
    for c in losers[:15]:
        print("%-14s %6d %8.2f %+8.2f" % (c["city"], c["fires"], c["cost"], c["pnl"]))

# ---- by city -----------------------------------------------------------------
bycity = {}
for c in res:
    b = bycity.setdefault(c["city"], [0, 0, 0.0])
    b[0] += 1 if c["win"] else 0; b[1] += 1; b[2] += c["pnl"]
print("\n--- by city (resolved clusters) ---")
print("%-14s %8s %6s %9s" % ("city", "wins/n", "WR%", "pnl$"))
for city, (w, n, p) in sorted(bycity.items(), key=lambda x: x[1][2]):
    print("%-14s %4d/%-3d %5.0f%% %+9.2f" % (city, w, n, 100*w/max(n,1), p))
print("\nNOTE: cluster-level n collapses correlated fires. <100 = trend.")
