"""Lockout-NO execution backtest: WHEN to buy, BOOK availability, PROFIT CAPACITY.

Self-contained from metar_lockout.jsonl:
- running_max is monotone -> final official daily high per (city,end_date) = max
  asos_running_max_c over the group. A bucket's NO wins iff the official high is
  NOT inside the padded bucket.
- Each snapshot carries the live no_book (asks with USD depth) -> realistic fill
  price and capacity, plus seconds_since_first_lockout / seconds_to_event_close
  -> entry-timing curves.

Outputs: NO win-rate (clean lockouts), EV/share at the *available* ask, fillable
USD depth, and total capturable profit (capacity) — sliced by entry timing.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict

FEE = 0.0            # Polymarket weather taker fee ~0.05 base; modeled as haircut below
FEE_HAIRCUT = 0.02   # conservative per-share fee+slippage haircut
MARGIN_C = 0.5       # clean-lockout gate: official high must exceed bucket ceiling by this
MAX_BUY = 0.97       # only buy NO at/below this ask (need real discount)
MIN_EDGE = 0.03      # require (1 - ask - haircut) >= this to count as fillable depth
BLOCK = {"Hong Kong"}  # HKO oracle mismatch

files = sorted(glob.glob("logs/shadow/hot/2026-*/metar_lockout.jsonl"))

# pass 1: final official high per (city, end_date)
final_max = defaultdict(lambda: -999.0)
records = []
for fp in files:
    with open(fp) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            city = d.get("city")
            ed = d.get("end_date")
            if city is None or ed is None:
                continue
            am = d.get("asos_running_max_c")
            if am is not None:
                final_max[(city, ed)] = max(final_max[(city, ed)], float(am))
            records.append(d)

print(f"records={len(records)}  city-days={len(final_max)}  files={len(files)}")

def best_no_ask(d):
    nb = d.get("no_book") or {}
    asks = nb.get("asks") or []
    if asks:
        return float(asks[0]["price"])
    v = d.get("no_ask_clob")
    return float(v) if v is not None else None

def fillable_depth_usd(d, max_price):
    nb = d.get("no_book") or {}
    tot = 0.0
    for a in (nb.get("asks") or []):
        if float(a["price"]) <= max_price:
            tot += float(a.get("usd") or 0.0)
    return tot

# pass 2: per (city,end_date,bucket) take the FIRST snapshot meeting the entry rule
seen = {}
opps = []
for d in records:
    city = d.get("city")
    if city in BLOCK:
        continue
    ed = d.get("end_date")
    lo = d.get("bucket_lo_c_padded"); hi = d.get("bucket_hi_c_padded")
    am = d.get("asos_running_max_c")
    if None in (lo, hi, am):
        continue
    lo = float(lo); hi = float(hi); am = float(am)
    # clean lockout gate (official high safely above bucket ceiling)
    if am - hi < MARGIN_C:
        continue
    key = (city, ed, d.get("no_token_id") or (lo, hi))
    if key in seen:
        continue
    ask = best_no_ask(d)
    if ask is None or ask > MAX_BUY or ask <= 0:
        continue
    seen[key] = True
    fmax = final_max[(city, ed)]
    no_wins = not (lo <= fmax <= hi)         # NO wins if official high outside bucket
    depth = fillable_depth_usd(d, 1.0 - FEE_HAIRCUT - MIN_EDGE)
    pnl_share = (1.0 - ask) if no_wins else (-ask)
    pnl_share -= FEE_HAIRCUT
    opps.append({
        "city": city, "no_wins": no_wins, "ask": ask, "depth": depth,
        "edge": (1.0 - ask - FEE_HAIRCUT),
        "since_lockout": d.get("seconds_since_first_lockout"),
        "to_close": d.get("seconds_to_event_close"),
        "pnl_share": pnl_share,
    })

n = len(opps)
if n == 0:
    print("no opportunities under gates"); raise SystemExit
wr = sum(o["no_wins"] for o in opps) / n
ev = sum(o["pnl_share"] for o in opps) / n
mean_ask = sum(o["ask"] for o in opps) / n
mean_depth = sum(o["depth"] for o in opps) / n
# capacity: realistic $ = Σ over winning-rate of depth*edge (cap depth at $200/leg)
cap_each = [min(o["depth"], 200.0) * o["edge"] for o in opps if o["edge"] > 0]
total_cap = sum(cap_each)
print(f"\n=== LOCKOUT-NO (clean, margin>= {MARGIN_C}C, buy<= {MAX_BUY}, ex-HK) ===")
print(f"  opportunities n={n}")
print(f"  NO win-rate     = {wr:.3f}")
print(f"  mean NO ask     = {mean_ask:.3f}   (mean gross edge = {1-mean_ask:.3f})")
print(f"  EV/share (net)  = {ev:+.4f}")
print(f"  mean fillable depth/opp = ${mean_depth:.1f}")
print(f"  total capturable (capacity, depth<=200/leg x edge) = ${total_cap:,.0f}  over {len(files)} days")

# timing curves
def bucketize(opps, field, edges, label):
    print(f"\n  -- by {label} --")
    groups = defaultdict(list)
    for o in opps:
        v = o[field]
        if v is None:
            groups["NA"].append(o); continue
        v = float(v)
        placed = False
        for e in edges:
            if v < e:
                groups[f"<{int(e)}"].append(o); placed = True; break
        if not placed:
            groups[f">={int(edges[-1])}"].append(o)
    order = [f"<{int(e)}" for e in edges] + [f">={int(edges[-1])}", "NA"]
    for g in order:
        lst = groups.get(g)
        if not lst:
            continue
        m = len(lst)
        wrr = sum(x["no_wins"] for x in lst)/m
        evv = sum(x["pnl_share"] for x in lst)/m
        dep = sum(x["depth"] for x in lst)/m
        ask = sum(x["ask"] for x in lst)/m
        print(f"    {g:>8}: n={m:<5} WR={wrr:.3f} ask={ask:.3f} EV/sh={evv:+.4f} depth=${dep:.1f}")

bucketize(opps, "since_lockout", [900, 1800, 3600, 7200], "seconds since first lockout")
bucketize(opps, "to_close", [1800, 3600, 7200, 14400], "seconds to close")

# per-city
print("\n  -- by city (top by n) --")
bycity = defaultdict(list)
for o in opps:
    bycity[o["city"]].append(o)
for city, lst in sorted(bycity.items(), key=lambda kv: -len(kv[1]))[:12]:
    m = len(lst)
    wrr = sum(x["no_wins"] for x in lst)/m
    evv = sum(x["pnl_share"] for x in lst)/m
    dep = sum(x["depth"] for x in lst)/m
    print(f"    {city:>16}: n={m:<4} WR={wrr:.3f} EV/sh={evv:+.4f} depth=${dep:.1f}")
