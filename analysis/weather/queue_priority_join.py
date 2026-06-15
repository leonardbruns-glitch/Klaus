#!/usr/bin/env python3
"""Queue-priority join (2026-06-12 hidden-assumption audit #3).

Tests the assumption "our quotes fill like badatmath's" by joining HIS
observed fills (badatmath_watch.jsonl fill_join, logged with the live book at
~69s detection lag) against OUR resting band quotes (band_struct.jsonl post
records) on the same token at the same time.

For each of his fills where we had an ACTIVE quote on the same token:
  - same-level contention: his fill price == our quote price (±half tick)
    → did OUR order fill within GRACE_S of his? If he repeatedly eats flow at
    a level where our bid sits unfilled, we are queue-behind (FIFO).
  - he-fills-better: his fill price ABOVE our bid → flow never reached us
    (placement gap, not queue gap).

Our fill timeline comes from journalctl MAKER-FILL lines (token prefix match).
Cancels/reclaims are NOT modelled (bias: overstates our 'active' window late
in the day — stated in output, makes queue-behind counts conservative upper
bounds on parity, i.e. real queue position can only be worse than measured).
"""
import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DAYS = ["2026-06-11", "2026-06-12"]
HOT = Path("logs/shadow/hot")
GRACE_S = 1800.0          # our order "also filled" if within 30 min of his
TICK = 0.005

# ── our posts ────────────────────────────────────────────────────────────────
posts = []                 # (ts, token, side, price, city, days_out)
for day in DAYS:
    p = HOT / day / "band_struct.jsonl"
    if not p.exists():
        continue
    for line in p.open():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("record") == "post" and r.get("token"):
            posts.append((r["ts"], r["token"], r.get("side", "YES"),
                          float(r.get("q") or 0), r.get("city"),
                          r.get("days_out")))
posts.sort()
by_token = defaultdict(list)
for ts, tok, side, px, city, do in posts:
    by_token[tok].append((ts, side, px, city, do))

# ── our fills (journal MAKER-FILL, token prefix 12) ──────────────────────────
try:
    out = subprocess.run(
        ["journalctl", "-u", "klaus", "--since", DAYS[0], "-o", "short-unix"],
        capture_output=True, text=True, timeout=120).stdout
except Exception as e:
    print("journalctl failed:", e)
    sys.exit(1)
fill_re = re.compile(
    r"^(\d+\.\d+).*\[MAKER-FILL\] (?:registered \S+.* (\d{12})|"
    r"\+[\d.]+ maker sh @ [\d.]+ → \S+.* (\d{12}))")
our_fills = []             # (ts, token12)
for line in out.splitlines():
    if "[MAKER-FILL]" not in line:
        continue
    m = re.match(r"^(\d+)(?:\.\d+)?\s", line)
    t12 = re.search(r"\b(\d{12})\b", line)
    if m and t12:
        our_fills.append((float(m.group(1)), t12.group(1)))
fills_by_tok12 = defaultdict(list)
for ts, t12 in our_fills:
    fills_by_tok12[t12].append(ts)

def our_fill_near(token: str, t: float) -> bool:
    for ts in fills_by_tok12.get(token[:12], []):
        if abs(ts - t) <= GRACE_S:
            return True
    return False

# ── his fills ────────────────────────────────────────────────────────────────
n_his = 0
overlap = 0                # his fill on a token we were quoting at that time
same_level = 0             # ...at OUR price level
same_level_we_filled = 0   # ...and we also filled within grace
he_better = 0              # his fill px > our bid (flow never reached us)
he_worse = 0               # his fill px < our bid (we should've filled first!)
examples = []
# timing/placement diagnostics
contend_lead = []          # same-level: his_fill_ts − our_post_ts (s). >0 we were resting first
contend_lead_filled = []   # ...subset where we ALSO filled
contend_lead_missed = []   # ...subset where we did NOT fill
placement_ticks = []       # he_better: (his_px − our_px) in ticks (how deep we sat)
for day in DAYS:
    p = HOT / day / "badatmath_watch.jsonl"
    if not p.exists():
        continue
    for line in p.open():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("record") != "fill_join":
            continue
        n_his += 1
        tok = r.get("token")
        if not tok or tok not in by_token:
            continue
        ft = float(r.get("fill_ts") or 0)
        px = float(r.get("price") or 0)
        # most recent of our posts on this token before his fill
        active = [q for q in by_token[tok] if q[0] <= ft]
        if not active:
            continue
        overlap += 1
        our_ts, side, our_px, city, do = active[-1]
        if abs(px - our_px) <= TICK:
            same_level += 1
            filled = our_fill_near(tok, ft)
            same_level_we_filled += int(filled)
            lead = ft - our_ts          # >0: our quote was resting before his fill
            contend_lead.append(lead)
            (contend_lead_filled if filled else contend_lead_missed).append(lead)
            if len(examples) < 12:
                examples.append(
                    f"  {city} d+{do} {side} our={our_px:.2f} his={px:.2f} "
                    f"lead={lead/60:+.0f}min we_filled_±30m={filled}")
        elif px > our_px + TICK:
            he_better += 1
            placement_ticks.append(round((px - our_px) / TICK))
        else:
            he_worse += 1

print(f"his fills (2d):                {n_his}")
print(f"on tokens we were quoting:     {overlap}")
print(f"  at OUR price level:          {same_level}")
print(f"    we also filled (±30min):   {same_level_we_filled}"
      f"   ← queue parity")
print(f"    we did NOT fill:           {same_level - same_level_we_filled}"
      f"   ← queue-BEHIND evidence")
print(f"  his fill ABOVE our bid:      {he_better}   ← placement gap "
      f"(flow died before our level)")
print(f"  his fill BELOW our bid:      {he_worse}   ← anomaly "
      f"(stale/cancelled quote or async books)")
print()

def _summ(xs, unit="min", div=60.0):
    if not xs:
        return "n=0"
    xs = sorted(xs)
    return (f"n={len(xs)} median={statistics.median(xs)/div:+.0f}{unit} "
            f"p25={xs[len(xs)//4]/div:+.0f} p75={xs[3*len(xs)//4]/div:+.0f}")

# ── TIME-PRIORITY: were we resting BEFORE his fill, or did we arrive late? ─────
print("TIME-PRIORITY (same-level contention) — lead = his_fill_ts − our_post_ts")
print(f"  our quote was resting BEFORE his fill: "
      f"{sum(1 for x in contend_lead if x > 0)}/{len(contend_lead)}"
      f"  (>0 = we had time priority yet still lost ⇒ depth/size, not lateness)")
print(f"  we arrived AFTER his fill (clear time-loss): "
      f"{sum(1 for x in contend_lead if x <= 0)}/{len(contend_lead)}")
print(f"  lead | we FILLED:  {_summ(contend_lead_filled)}")
print(f"  lead | we MISSED:  {_summ(contend_lead_missed)}")
print()

# ── PLACEMENT GAP: when flow died above us, how many ticks too deep were we? ───
if placement_ticks:
    pt = sorted(placement_ticks)
    within1 = sum(1 for x in pt if x <= 1)
    print(f"PLACEMENT GAP ({len(pt)} fills above our bid) — ticks above our quote")
    print(f"  median={statistics.median(pt):.0f} ticks "
          f"p25={pt[len(pt)//4]} p75={pt[3*len(pt)//4]}  "
          f"(1 tick = {TICK*100:.1f}¢)")
    print(f"  within 1 tick of our bid: {within1}/{len(pt)} "
          f"({100*within1/len(pt):.0f}%) ⇐ a join-touch improve would capture these")
    print()

print("examples (same-level contention):")
print("\n".join(examples) if examples else "  none")
print()
print(f"[our side] posts={len(posts)}  journal MAKER-FILL events="
      f"{len(our_fills)}  (cancels not modelled — parity counts are "
      f"upper bounds)")
