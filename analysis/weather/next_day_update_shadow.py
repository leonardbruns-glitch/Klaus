"""Next-day model-update edge — shadow detector + thesis validator.

Reads the forward-ladder book log (logs/shadow/hot/<date>/stwa_ladder_book.jsonl,
written by stwa_engine._log_ladder_book) and tests the core thesis WITHOUT needing
resolution:

    When the model (p_cal) jumps on a fresh NWP run, does the book ask LAG and then
    CONVERGE toward the new p_cal over the next snapshots?

A candidate fires at snapshot t for a (city,bucket) when:
  • |Δp_cal| >= MOVE_THR              (a real model update, not drift)
  • the book hasn't followed: ask is on the wrong side of the new p_cal by >= EDGE
  • fillable depth >= MIN_DEPTH_USD

Then we measure ask convergence over the next CONV_HORIZON snapshots:
  did the ask move toward p_cal_new?  by how much?  This is the capturable reprice
  (exit-at-convergence EV) — the resolution-free proof the lag is real.

Run daily as the ladder log accumulates. Graduation to live capital is gated
separately (n>=100 candidates + positive mean convergence + later resolution EV).
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict

MOVE_THR      = 0.10    # |Δp_cal| to call it a model update
EDGE          = 0.05    # ask must lag p_cal_new by at least this
MIN_DEPTH_USD = 5.0     # fillable book depth required
CONV_HORIZON  = 5       # snapshots ahead to measure ask convergence

files = sorted(glob.glob("logs/shadow/hot/2026-*/stwa_ladder_book.jsonl"))
if not files:
    print("NO ladder-book data yet. Deploy stwa_engine (restart klaus) so "
          "_log_ladder_book starts writing stwa_ladder_book.jsonl, then re-run.")
    raise SystemExit

# series[(city,(lo,hi))] = list of (ts, p_cal, ask_yes, ask_no, yes_depth, no_depth)
series = defaultdict(list)
n_rows = 0
for fp in files:
    with open(fp) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = r.get("ts"); city = r.get("city")
            for b in r.get("buckets", []):
                key = (city, (b.get("lo"), b.get("hi")))
                series[key].append((ts, b.get("p_cal"), b.get("ask_yes"),
                                    b.get("ask_no"), b.get("yes_depth_usd"),
                                    b.get("no_depth_usd")))
                n_rows += 1

print(f"ladder snapshots: rows={n_rows}  series={len(series)}  files={len(files)}")

cands = []
for key, pts in series.items():
    pts = [p for p in pts if p[0] is not None]
    pts.sort(key=lambda x: x[0])
    for i in range(1, len(pts)):
        ts0, pc0, ay0, an0, yd0, nd0 = pts[i - 1]
        ts1, pc1, ay1, an1, yd1, nd1 = pts[i]
        if pc0 is None or pc1 is None:
            continue
        dpc = pc1 - pc0
        if abs(dpc) < MOVE_THR:
            continue
        if dpc > 0:                       # model now favors YES; is ask lagging?
            ask = ay1
            depth = yd1 or 0.0
            if ask is None or depth < MIN_DEPTH_USD or ask >= pc1 - EDGE:
                continue
            gap = pc1 - ask
            # convergence: ask movement toward p_cal_new over the horizon
            fut = pts[i + 1: i + 1 + CONV_HORIZON]
            fut_ask = [a for (_, _, a, _, _, _) in fut if a is not None]
            conv = (fut_ask[-1] - ask) if fut_ask else 0.0   # +ve = ask rose toward p_cal
            cands.append(("YES", key[0], dpc, gap, conv, depth))
        else:                             # model now favors NO
            ask = an1
            depth = nd1 or 0.0
            pc_no = 1.0 - pc1
            if ask is None or depth < MIN_DEPTH_USD or ask >= pc_no - EDGE:
                continue
            gap = pc_no - ask
            fut = pts[i + 1: i + 1 + CONV_HORIZON]
            fut_ask = [a for (_, _, _, a, _, _) in fut if a is not None]
            conv = (fut_ask[-1] - ask) if fut_ask else 0.0
            cands.append(("NO", key[0], dpc, gap, conv, depth))

if not cands:
    print("no model-update-lag candidates yet (need more snapshots spanning NWP runs).")
    raise SystemExit

n = len(cands)
mean_gap = sum(c[3] for c in cands) / n
mean_conv = sum(c[4] for c in cands) / n
captured = sum(1 for c in cands if c[4] > 0) / n
print(f"\n=== model-update-lag candidates n={n} ===")
print(f"  mean entry gap (p_cal - ask) = {mean_gap:+.3f}")
print(f"  mean ask convergence over {CONV_HORIZON} snaps = {mean_conv:+.3f} "
      f"(fraction that converged = {captured:.2f})")
print(f"  THESIS {'SUPPORTED' if mean_conv > 0 else 'NOT supported'}: "
      f"book {'converges to' if mean_conv > 0 else 'does NOT follow'} the fresh forecast")
# by side + by gap magnitude
for side in ("YES", "NO"):
    s = [c for c in cands if c[0] == side]
    if s:
        print(f"  {side}: n={len(s)} mean_gap={sum(x[3] for x in s)/len(s):+.3f} "
              f"mean_conv={sum(x[4] for x in s)/len(s):+.3f}")
print("\nGraduation gate: n>=100 AND mean_conv>0 AND (resolution-join EV>0) before live.")
