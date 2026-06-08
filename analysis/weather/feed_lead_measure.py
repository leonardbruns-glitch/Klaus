"""Stage-0 feed-lead measurement.

Reads logs/shadow/hot/<date>/obs_receipt.jsonl (written by national_met.
_log_obs_receipt: one row per source's FIRST delivery of each obs, tagged with
our receipt wall-clock) and answers the make-or-break question:

    For the SAME physical observation (icao, obs_valid_ts), how much earlier did
    the fastest source hand it to us than AWC's batch did?

That AWC_recv − fastest_recv gap is the tradeable lead over a competitor running
off AWC. We restrict to obs where AWC ALSO eventually delivered the same
obs_valid_ts (i.e., resolution-grade hourly METARs both carry), so the lead is on
the value that actually resolves — not a sub-hourly reading AWC never publishes.
"""
from __future__ import annotations

import glob
import json
import statistics as st
from collections import defaultdict

files = sorted(glob.glob("logs/shadow/hot/2026-*/obs_receipt.jsonl"))
if not files:
    print("NO obs_receipt data yet. Deploy national_met (restart klaus) so "
          "_log_obs_receipt starts writing obs_receipt.jsonl, then re-run.")
    raise SystemExit

# group[(icao, valid)] = {source: earliest recv_ts}
group = defaultdict(dict)
n_rows = 0
for fp in files:
    for line in open(fp):
        try:
            r = json.loads(line)
        except Exception:
            continue
        n_rows += 1
        icao = r.get("icao"); src = r.get("source")
        valid = r.get("obs_valid_ts"); recv = r.get("recv_ts")
        if None in (icao, src, valid, recv):
            continue
        k = (icao, round(float(valid)))
        cur = group[k].get(src)
        if cur is None or recv < cur:
            group[k][src] = recv

print(f"obs_receipt rows={n_rows}  unique (icao,obs) groups={len(group)}  files={len(files)}")

# Lead = AWC_recv − fastest_non_AWC_recv, only where AWC also carried this obs
leads = []          # minutes
by_winner = defaultdict(list)   # which source provided the lead
multi = 0
for (icao, valid), srcs in group.items():
    if "AWC" not in srcs or len(srcs) < 2:
        continue
    multi += 1
    awc = srcs["AWC"]
    others = {s: t for s, t in srcs.items() if s != "AWC"}
    winner = min(others, key=others.get)
    lead_min = (awc - others[winner]) / 60.0
    leads.append(lead_min)
    by_winner[winner].append(lead_min)

print(f"obs carried by AWC + >=1 other source (resolution-grade, comparable): {multi}")
if not leads:
    print("no comparable AWC+other obs yet — need more collection time "
          "(AWC must redeliver an obs a faster source already had).")
    raise SystemExit

pos = [x for x in leads if x > 0]
ls = sorted(leads)
q = lambda p: ls[min(len(ls) - 1, int(p * len(ls)))]
print(f"\nFEED LEAD over AWC (min), n={len(leads)}:")
print(f"  median={st.median(ls):+.1f}  mean={sum(ls)/len(ls):+.1f}  p25={q(.25):+.1f}  p75={q(.75):+.1f}  max={max(ls):+.1f}")
print(f"  fraction with a POSITIVE lead (we beat AWC): {len(pos)/len(leads):.0%}")
print(f"\n  lead by fastest source (median min, n):")
for s, xs in sorted(by_winner.items(), key=lambda kv: -len(kv[1])):
    print(f"    {s:<10} n={len(xs):<4} median={st.median(xs):+.1f}")
print("\nVerdict gate: a real tradeable edge needs median lead >> 0 on a meaningful "
      "fraction of resolution-grade obs. ~0 ⇒ no speed edge on the value that resolves.")
