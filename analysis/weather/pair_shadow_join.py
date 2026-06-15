#!/usr/bin/env python3
"""Deliberate-pair shadow join (2026-06-15).

Question: if we two-side the NEAR-MODE YES band buckets (post a NO leg at the NO
touch on the same cond where we post YES), what fraction would COMPLETE into a
mergeable pair, and is the merge margin (1 - pair_sum) real?

Background: the 5 real merges to date were ACCIDENTAL band-YES (~0.27) + overlay-NO
(~0.61) overlaps on the same cond (Σ 0.81-0.92, all +margin). PAIR_FAV proper posts
~0 (cash-starved + aimed at CONVERGED favorites where flow is one-sided). The live
PAIR-SHADOW emit (band_struct.jsonl record=md_shadow reason=pair_shadow) logs, for
each YES band leg we actually posted, the real NO book + would-be NO pair leg.

This joins those shadow records against REAL NO MAKER-FILLs on the same cond to
estimate the deliberate-pair CO-FILL rate. A merge needs BOTH legs filled; we posted
(and largely filled) the YES leg, so co-fill ~= did the NO leg fill on that cond.

Honest limits: (a) we never actually POSTED the shadow NO, so "no_fillable" (our bid
>= NO touch) is a placement proxy and real NO fills are opportunistic (the overlay's,
not a deliberate band-NO); both UNDER-count true co-fill if a deliberate resting NO
bid would have caught more flow. (b) cond match is by 10-char prefix (journal truncates).

Usage:  python3 analysis/weather/pair_shadow_join.py
"""
import json, glob, re, subprocess, statistics
from collections import defaultdict

# ── 1) pair_shadow records (deduped first per cond) ──────────────────────────
shadow = {}
for f in sorted(glob.glob("logs/shadow/hot/*/band_struct.jsonl")):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("record") == "md_shadow" and r.get("reason") == "pair_shadow":
            cid = r.get("cid")
            if cid and cid not in shadow:
                shadow[cid] = r
if not shadow:
    print("no pair_shadow records yet — data-collection mode (just deployed).")
    raise SystemExit
print(f"pair_shadow records (deduped per cond): {len(shadow)}")

# ── 2) real MAKER-FILLs by cond-prefix + side ────────────────────────────────
out = subprocess.run(["journalctl","-u","klaus","--since","2026-06-15","-o","cat"],
                     capture_output=True, text=True, timeout=180).stdout
reg = re.compile(r"\[MAKER-FILL\] registered .+? (YES|NO) \d+ \+[\d.]+ @ [\d.]+ \(cond=(0x[0-9a-f]+)\)")
fills = defaultdict(set)   # cond_prefix(10) -> {sides}
for line in out.splitlines():
    m = reg.search(line)
    if m:
        fills[m.group(2)].add(m.group(1))

def filled(cid, side):
    return side in fills.get(cid[:10], set())

# ── 3) report ────────────────────────────────────────────────────────────────
margins = [r["merge_margin"] for r in shadow.values()]
pos_margin = [m for m in margins if m > 0]
no_fillable = sum(1 for r in shadow.values() if r.get("no_fillable"))
yes_filled = [c for c in shadow if filled(c, "YES")]
co_filled = [c for c in yes_filled if filled(c, "NO")]

def summ(xs):
    xs = sorted(xs)
    return (f"median={statistics.median(xs):+.3f} p25={xs[len(xs)//4]:+.3f} "
            f"p75={xs[3*len(xs)//4]:+.3f}") if xs else "n=0"

print(f"\nMERGE MARGIN (1 - pair_sum) on band buckets:")
print(f"  all: n={len(margins)} {summ(margins)}")
print(f"  positive-margin share: {len(pos_margin)}/{len(margins)} "
      f"({100*len(pos_margin)/max(len(margins),1):.0f}%)")
print(f"\nNO-LEG FILLABILITY (placement proxy — our would-be NO bid >= NO touch):")
print(f"  {no_fillable}/{len(shadow)} ({100*no_fillable/len(shadow):.0f}%)")
print(f"\nEMPIRICAL CO-FILL (real fills on the shadow cond):")
print(f"  YES filled: {len(yes_filled)}/{len(shadow)}")
print(f"  ...and NO also filled (co-fill): {len(co_filled)}/{max(len(yes_filled),1)} "
      f"= {100*len(co_filled)/max(len(yes_filled),1):.1f}%  (his ~47%)")
print(f"\nby days_out (positive-margin & fillable count):")
for d in sorted(set(r.get("days_out") for r in shadow.values())):
    rs = [r for r in shadow.values() if r.get("days_out") == d]
    fb = sum(1 for r in rs if r.get("no_fillable"))
    print(f"  d+{d}: n={len(rs)} fillable={fb} median_margin={statistics.median([r['merge_margin'] for r in rs]):+.3f}")

n = len(co_filled)
print(f"\nGATE: live PAIR re-rank needs co-fill rate that makes Σ<1 pairs net +EV. "
      f"co-fill n={n} => {'DATA-COLLECTION (n<40)' if n<40 else 'TREND (40<=n<100)' if n<100 else 'DECISION-READY'}")
