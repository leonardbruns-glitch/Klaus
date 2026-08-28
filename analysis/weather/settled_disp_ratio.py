#!/usr/bin/env python3
"""Settled-lane dispersion ratio (implied vs realized) from FULL pricer_eval logs.

Unblocks the calib-monitor S3 gauge: the cloud lane needs outcome labels it cannot
fetch (gamma 403s cloud IPs; band dark = no fill joins). This computes, on the VPS,
per city-date d+0:
  impl  = p_cal-weighted std (deg C) of the bucket ladder at the LAST PRE_PEAK snapshot
  mode  = argmax-p_cal bucket center at that same snapshot
  real  = |resolved_center - mode_center|, resolved bucket = bucket containing the
          final running_max (official-floored, last snapshot before t_close)
Aggregations per day: pooled ratio = mean(impl)/mean(real), median per-city ratio.
Method differs in plumbing from the cloud lane (which uses s50 subsamples + fill
joins) — so it is run over Jun 28-Jul 2 as well, where the cloud lane published
0.807/0.663/0.976/0.866/0.858, to check comparability before reading Jul 3-9.

Run on VPS: PYTHONPATH=/root/Klaus python3 analysis/weather/settled_disp_ratio.py
Output: analysis/weather/settled_disp_ratio.json (+ stdout table)
"""
import json, glob, math, os, time
from collections import defaultdict

HOT = "/root/Klaus/logs/shadow/hot"
# rolling window: last 18 hot-log day dirs (was a hard-coded list ending 07-10,
# which read as a "dead feed" in the S3 gauge once the calendar moved past it)
DATES = sorted(d for d in os.listdir(HOT)
               if len(d) == 10 and d.startswith("202") and os.path.isdir(f"{HOT}/{d}"))[-18:]
NOW = time.time()

def center(lo, hi):
    if lo <= -900: return hi - 0.5
    if hi >= 900:  return lo + 0.5
    return (lo + hi) / 2.0

# pass 1: per (city, t_close) find last PRE_PEAK ts, last overall ts + running_max
last_prepeak = {}
last_snap = {}
files = [f"{HOT}/{d}/stwa_pricer_eval.jsonl" for d in DATES]
files = [f for f in files if os.path.exists(f)]
for fp in files:
    with open(fp) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            tc = r.get("t_close")
            if not tc or tc > NOW: continue          # only resolved markets
            key = (r["city"], round(tc))
            ts = r["ts"]
            if r.get("phase") == "PRE_PEAK":
                if ts > last_prepeak.get(key, 0): last_prepeak[key] = ts
            prev = last_snap.get(key)
            if prev is None or ts > prev[0]:
                last_snap[key] = (ts, r.get("running_max"))

# pass 2: collect the ladder at the chosen PRE_PEAK snapshot
ladders = defaultdict(list)
for fp in files:
    with open(fp) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            tc = r.get("t_close")
            if not tc or tc > NOW: continue
            key = (r["city"], round(tc))
            if last_prepeak.get(key) == r["ts"]:
                ladders[key].append((r["lo"], r["hi"], r.get("p_cal") or 0.0))

# per city-date rows
rows = []
for key, lad in ladders.items():
    city, tc = key
    ts_last, runmax = last_snap.get(key, (None, None))
    if runmax is None: continue
    # market local date via t_close - 10h heuristic (t_close = local midnight)
    date = time.strftime("%Y-%m-%d", time.gmtime(tc - 10*3600))
    w = sum(p for _,_,p in lad)
    if w <= 0 or len(lad) < 3: continue
    cs = [(center(lo,hi), p/w) for lo,hi,p in lad]
    mu = sum(c*p for c,p in cs)
    impl = math.sqrt(max(0.0, sum(p*(c-mu)**2 for c,p in cs)))
    mode_c = max(lad, key=lambda b: b[2])
    mode_center = center(mode_c[0], mode_c[1])
    res = [b for b in lad if b[0] <= runmax < b[1]]
    if not res:  # running_max outside ladder -> nearest edge bucket
        res = [min(lad, key=lambda b: min(abs(runmax-b[0]), abs(runmax-b[1])))]
    real = abs(center(res[0][0], res[0][1]) - mode_center)
    # only markets where the pre-peak snapshot is meaningfully before close
    if last_prepeak[key] > tc - 3600: continue
    rows.append({"city": city, "date": date, "t_close": tc, "impl": round(impl,4),
                 "real": round(real,4), "run_max": runmax, "n_buckets": len(lad)})

byday = defaultdict(list)
for r in rows: byday[r["date"]].append(r)
out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "method": "full pricer_eval, last PRE_PEAK ladder, p_cal-normalized std vs |resolved-mode|, resolved=final running_max",
       "days": {}}
print(f"{'date':<12}{'n':>4}{'impl_mean':>10}{'real_mean':>10}{'pooled':>8}{'med_ratio':>10}")
for d in sorted(byday):
    rs = byday[d]
    n = len(rs)
    im = sum(r["impl"] for r in rs)/n
    rm = sum(r["real"] for r in rs)/n
    pooled = im/rm if rm > 0 else None
    prs = sorted(r["impl"]/r["real"] for r in rs if r["real"] > 0)
    med = prs[len(prs)//2] if prs else None
    out["days"][d] = {"n": n, "impl_mean": round(im,3), "real_mean": round(rm,3),
                      "pooled_ratio": round(pooled,3) if pooled else None,
                      "median_city_ratio": round(med,3) if med else None,
                      "n_real_pos": len(prs)}
    print(f"{d:<12}{n:>4}{im:>10.3f}{rm:>10.3f}{(pooled or float('nan')):>8.3f}{(med or float('nan')):>10.3f}")
out["rows"] = rows
with open("/root/Klaus/analysis/weather/settled_disp_ratio.json","w") as fh:
    json.dump(out, fh, indent=1)
print("wrote analysis/weather/settled_disp_ratio.json  rows:", len(rows))
