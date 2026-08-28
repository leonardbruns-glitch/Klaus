"""Next-day model-update edge — shadow detector + thesis validator (v2).

Reads the forward-ladder book log (logs/shadow/hot/<date>/stwa_ladder_book.jsonl,
written by stwa_engine._log_ladder_book) and tests the core thesis WITHOUT needing
resolution:

    When the model's forecast updates on a fresh NWP run (the daily-max CENTER
    shifts), does the book ask LAG and then CONVERGE toward the new forecast over
    the next snapshots?

v1 keyed on |Δp_cal| and was dominated by running-max-floor LOCKOUT FLIPS (the day
warming through buckets), not genuine forecast updates — 60/70 of its jumps were
floor artifacts. v2 fixes that using the running_max + model_center now logged per
snapshot:

A candidate fires at snapshot t for a (city,bucket) when ALL hold:
  • |Δmodel_center| >= CENTER_THR        (a real forecast/NWP update, city-level)
  • the bucket is NOT floored: bucket_hi > running_max  (exclude lockout flips)
  • the book hasn't followed: ask lags the new p_cal by >= EDGE
Then we measure ask convergence over the next CONV_HORIZON snapshots, and report
FILLABLE candidates (depth >= MIN_DEPTH_USD) SEPARATELY — so "edge exists but isn't
fillable" can't masquerade as "no edge."

Graduation to live capital is gated: n>=100 fillable candidates + positive mean
convergence on the fillable set + a later resolution-join EV>0.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict

CENTER_THR    = 0.30   # |Δ daily-max center °C| to call it a forecast update
EDGE          = 0.05   # ask must lag p_cal_new by at least this
MIN_DEPTH_USD = 5.0    # fillable book depth (reported separately, not a hard gate)
CONV_HORIZON  = 5      # snapshots ahead to measure ask convergence

files = sorted(glob.glob("logs/shadow/hot/2026-*/stwa_ladder_book.jsonl"))
if not files:
    print("NO ladder-book data yet. Deploy stwa_engine (restart klaus) so "
          "_log_ladder_book starts writing stwa_ladder_book.jsonl, then re-run.")
    raise SystemExit

# Per-city ordered list of snapshots: (ts, running_max, center, {(lo,hi): bucketdict})
snaps = defaultdict(list)
n_rows = 0
have_center = 0
for fp in files:
    with open(fp) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            n_rows += 1
            if r.get("model_center") is not None:
                have_center += 1
            bmap = {(b.get("lo"), b.get("hi")): b for b in r.get("buckets", [])}
            snaps[r.get("city")].append(
                (r.get("ts"), r.get("running_max"), r.get("model_center"), bmap))

print(f"ladder snapshots: rows={n_rows}  cities={len(snaps)}  files={len(files)}")
print(f"snapshots WITH center/running_max (v2-usable, post-deploy): {have_center}/{n_rows}")
if have_center == 0:
    print("\nNo center-stamped snapshots yet — deploy the ladder-logger change "
          "(restart klaus) and let it run across at least one NWP-update window.")
    raise SystemExit

cands = []          # (side, city, dcenter, gap, conv, depth, fillable)
n_updates = 0
for city, rows in snaps.items():
    rows = [x for x in rows if x[0] is not None]
    rows.sort(key=lambda x: x[0])
    for i in range(1, len(rows)):
        ts1, rm1, c1, bm1 = rows[i]
        c0 = rows[i - 1][2]
        if c0 is None or c1 is None:
            continue
        if abs(c1 - c0) < CENTER_THR:          # not a real forecast update
            continue
        n_updates += 1
        for (lo, hi), b in bm1.items():
            if hi is None or (rm1 is not None and rm1 >= hi):
                continue                        # floored bucket = lockout, not forecast
            pc1 = b.get("p_cal")
            if pc1 is None:
                continue
            up = (c1 - c0) > 0                   # center rose → higher buckets gain
            # side the update favors for THIS bucket: above old center → YES gains
            # on a rising center; below → NO gains. Use p_cal directly vs ask.
            ask_y, ask_n = b.get("ask_yes"), b.get("ask_no")
            yd = b.get("yes_depth_usd") or 0.0
            nd = b.get("no_depth_usd") or 0.0
            # YES lag
            if ask_y is not None and ask_y < pc1 - EDGE:
                fut = [rows[j][3].get((lo, hi), {}).get("ask_yes")
                       for j in range(i + 1, min(i + 1 + CONV_HORIZON, len(rows)))]
                fut = [a for a in fut if a is not None]
                conv = (fut[-1] - ask_y) if fut else None
                if conv is not None:
                    cands.append(("YES", city, c1 - c0, pc1 - ask_y, conv, yd, yd >= MIN_DEPTH_USD))
            # NO lag
            pc_no = 1.0 - pc1
            if ask_n is not None and ask_n < pc_no - EDGE:
                fut = [rows[j][3].get((lo, hi), {}).get("ask_no")
                       for j in range(i + 1, min(i + 1 + CONV_HORIZON, len(rows)))]
                fut = [a for a in fut if a is not None]
                conv = (fut[-1] - ask_n) if fut else None
                if conv is not None:
                    cands.append(("NO", city, c1 - c0, pc_no - ask_n, conv, nd, nd >= MIN_DEPTH_USD))

print(f"forecast-update events (|Δcenter|>={CENTER_THR}): {n_updates}")
if not cands:
    print("no lagging-book candidates on non-floored buckets yet "
          "(need more snapshots spanning NWP runs).")
    raise SystemExit


def _report(label, cs):
    if not cs:
        print(f"\n[{label}] n=0")
        return
    n = len(cs)
    mg = sum(c[3] for c in cs) / n
    mc = sum(c[4] for c in cs) / n
    cap = sum(1 for c in cs if c[4] > 0) / n
    print(f"\n[{label}] n={n}")
    print(f"  mean entry gap (p_cal - ask) = {mg:+.3f}")
    print(f"  mean ask convergence /{CONV_HORIZON} snaps = {mc:+.3f}  (fraction converged = {cap:.2f})")
    print(f"  THESIS {'SUPPORTED' if mc > 0 else 'NOT supported'}: "
          f"book {'converges to' if mc > 0 else 'does NOT follow'} the fresh forecast")
    for side in ("YES", "NO"):
        s = [c for c in cs if c[0] == side]
        if s:
            print(f"    {side}: n={len(s)} mean_conv={sum(x[4] for x in s)/len(s):+.3f}")


_report("ALL candidates", cands)
_report("FILLABLE (depth>=$%.0f)" % MIN_DEPTH_USD, [c for c in cands if c[6]])
print(f"\nGraduation gate: n>=100 FILLABLE AND mean_conv>0 (fillable) AND resolution EV>0.")
