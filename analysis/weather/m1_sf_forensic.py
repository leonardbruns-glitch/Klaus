#!/usr/bin/env python3
"""SF lockout forensic: why did KSFO NO bets lose? Provenance check.

For each SF M1β fire (post-fix), show what the bot saw (running_max, bucket,
depth, NO price) vs what Gamma actually resolved, and which bucket WON.
Read-only.
"""
import json, glob, datetime as dt, sys
sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events, parse_weather_question

CUTOFF = dt.datetime(2026, 5, 29, 4, 11, tzinfo=dt.timezone.utc).timestamp()
CITY = "San Francisco"

# all SF fires (submit rows carry the rich state; result rows carry fill)
submits, results = {}, {}
for fp in sorted(glob.glob("logs/shadow/hot/*/m1_beta_probe.jsonl")):
    for line in open(fp):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("city") != CITY: continue
        t = r.get("ts_completed") or r.get("ts_submitted") or 0
        if t < CUTOFF: continue
        key = (r.get("no_token_id"), r.get("layer"), r.get("bucket_fire_seq"))
        if r.get("phase") == "submit": submits[key] = r
        elif r.get("phase") == "result": results[key] = r

print("SF post-fix fires:", len(results), "filled:",
      sum(1 for r in results.values() if r.get("filled")))

ts = [r.get("ts_completed") or r.get("ts_submitted") for r in results.values()]
dmin = dt.datetime.utcfromtimestamp(min(ts)).strftime("%Y-%m-%d")
dmax = (dt.datetime.utcfromtimestamp(max(ts)) + dt.timedelta(days=3)).strftime("%Y-%m-%d")
token_map, cond_map = fetch_weather_events(dmin, dmax)

# winning bucket per (city,date)
winners = {}
for cid, e in cond_map.items():
    p = e.get("outcomePrices") or []
    try: yes = float(p[0])
    except Exception: continue
    if yes < 0.99: continue
    m = parse_weather_question(e.get("question", ""))
    c = (m.get("weather_city") or "").lower()
    d = m.get("weather_date")
    if "san francisco" in c and d:
        winners[d] = (m.get("weather_threshold_lo_c_padded"),
                      m.get("weather_threshold_hi_c_padded"),
                      e.get("question", "")[:55])

print("\nSF winning buckets by date:")
for d, (lo, hi, q) in sorted(winners.items()):
    print("  %s  won=[%s,%s]  %s" % (d, lo, hi, q))

print("\n--- each SF fire: what bot saw vs resolution ---")
for key in sorted(results.keys(), key=lambda k: results[k].get("ts_submitted", 0)):
    res = results[key]
    sub = submits.get(key, {})
    cid = res.get("condition_id") or sub.get("condition_id")
    e = cond_map.get(cid) or token_map.get(str(res.get("no_token_id")))
    p = (e or {}).get("outcomePrices") or []
    try: no_res = float(p[1])
    except Exception: no_res = None
    ed = sub.get("end_date") or "?"
    rmax = sub.get("running_max_c")
    lo, hi = sub.get("bucket_lo_c"), sub.get("bucket_hi_c")
    depth = sub.get("depth_c")
    noask = res.get("fill_avg_price") or sub.get("no_ask_clob_at_signal")
    shares = res.get("fill_size_shares")
    won = "NO_WON" if (no_res is not None and no_res >= 0.99) else ("NO_LOST" if no_res is not None else "open")
    wb = winners.get(ed)
    print("%s L%-2s seq%s | bucket[%s,%s] rmax=%s depth=%s | NO@%s x%s -> %s | winbucket=%s"
          % (ed, sub.get("layer", "?"), sub.get("bucket_fire_seq", "?"),
             lo, hi, rmax, depth, noask, shares, won,
             ("[%s,%s]" % (wb[0], wb[1]) if wb else "?")))
