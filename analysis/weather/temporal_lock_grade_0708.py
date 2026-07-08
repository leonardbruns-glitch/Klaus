"""
Temporal-lock (P5) resolution grade — the first of the accrued-shadow sweeps
with real capacity: 545/2578 candidates had a resting YES bid >= 0.03
(NO buyable 0.39-0.97) at some point. Question: do temporally-locked buckets
actually resolve NO, and in which slices (gap, local hour, bid)?

Read-only. Run on VPS: python3 analysis/weather/temporal_lock_grade_0708.py
"""
from __future__ import annotations
import glob
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events

DATE_MIN = "2026-06-28"
CUTOFF = "2026-07-07"
GLOB = "/root/Klaus/logs/shadow/hot/*/temporal_lock.jsonl"
BLOCK = {"VHHH", "ZGSZ", "UUWW"}
FEE = 0.0125          # taker fee on proceeds


def wr_ci_low(w, n):
    if n == 0:
        return 0.0
    z = 1.96
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return c - h


def main():
    # first EXECUTABLE snapshot per (question, end_date)
    first = {}
    for fp in sorted(glob.glob(GLOB)):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            ed = r.get("end_date")
            if not ed or not (DATE_MIN <= ed <= CUTOFF):
                continue
            if (r.get("icao") or "") in BLOCK:
                continue
            b = r.get("gamma_best_bid")
            if b is None or b < 0.03:
                continue
            key = (r.get("question"), ed)
            if key not in first or r["ts_s"] < first[key]["ts_s"]:
                first[key] = r
    print(f"first-executable candidates (clean stations): {len(first)}")

    token_map, cond_map = fetch_weather_events(DATE_MIN, CUTOFF)
    q_res = {}
    for cid, e in cond_map.items():
        if not e.get("closed"):
            continue
        p = e.get("outcomePrices") or []
        try:
            yes = float(p[0])
        except Exception:
            continue
        if yes <= 0.01:
            q_res[e.get("question")] = True     # NO won
        elif yes >= 0.99:
            q_res[e.get("question")] = False

    rows = []
    nomatch = 0
    for (q, ed), r in first.items():
        w = q_res.get(q)
        if w is None:
            nomatch += 1
            continue
        rows.append((r, w))
    print(f"resolved: {len(rows)}  no_match/unresolved: {nomatch}\n")

    def slice_report(title, keyfn):
        agg = defaultdict(lambda: [0, 0, 0.0, 0.0])   # wins, n, ev_sum, stake-1
        for r, w in rows:
            b = r["gamma_best_bid"]
            p_no = round(1.0 - b, 3)
            if p_no <= 0.02:
                continue
            ret = ((1.0 - p_no) / p_no) * (1 - FEE) if w else -1.0
            k = keyfn(r)
            agg[k][0] += 1 if w else 0
            agg[k][1] += 1
            agg[k][2] += ret
        print(f"--- {title} ---")
        for k in sorted(agg):
            w, n, ev, _ = agg[k]
            print(f"  {str(k):12s} WR {w}/{n} = {100*w/max(n,1):5.1f}%  "
                  f"CI-low {100*wr_ci_low(w,n):5.1f}%  EV/$1 {ev/max(n,1):+.3f}")

    slice_report("gap_above_c band", lambda r: ("<1" if r["gap_above_c"] < 1 else
                                                "1-2" if r["gap_above_c"] < 2 else
                                                "2-3" if r["gap_above_c"] < 3 else ">=3"))
    slice_report("local_hour band", lambda r: ("00-11" if r["local_hour"] < 12 else
                                               "12-15" if r["local_hour"] < 16 else
                                               "16-19" if r["local_hour"] < 20 else "20-23"))
    slice_report("yes_bid band", lambda r: ("0.03-0.10" if r["gamma_best_bid"] < 0.10 else
                                            "0.10-0.25" if r["gamma_best_bid"] < 0.25 else
                                            "0.25-0.50" if r["gamma_best_bid"] < 0.50 else ">=0.50"))

    # the composite candidate live gate: post-peak-ish hour + real gap
    print("\n--- COMPOSITE: local_hour>=16 AND gap>=2 ---")
    losses = []
    w = n = 0
    ev = 0.0
    cap = 0.0
    for r, won in rows:
        if r["local_hour"] >= 16 and r["gap_above_c"] >= 2:
            b = r["gamma_best_bid"]
            p_no = 1.0 - b
            n += 1
            w += 1 if won else 0
            ev += ((1.0 - p_no) / p_no) * (1 - FEE) if won else -1.0
            cap += b * 10  # placeholder unit count; bid depth not logged
            if not won:
                losses.append((r["city"], r["end_date"], r["gap_above_c"],
                               r["local_hour"], b, r["question"][:60]))
    print(f"  WR {w}/{n} = {100*w/max(n,1):.1f}%  CI-low {100*wr_ci_low(w,n):.1f}%  "
          f"EV/$1 {ev/max(n,1):+.3f}")
    print(f"  LOSSES ({len(losses)}):")
    for x in losses[:12]:
        print("   ", x)


if __name__ == "__main__":
    main()
