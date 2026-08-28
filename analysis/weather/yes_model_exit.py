#!/usr/bin/env python3
"""Model-signal exit for STWA YES: exit when the bucket becomes physically
unreachable (running_max_c > bucket ceiling => locked OUT of YES). Because
running_max is monotone and a YES wins only if the final max lands INSIDE
[lo,hi], this trigger can NEVER fire on a winner -> winners are structurally
protected. Exit fill = real CLOB yes_bid (yes_bid_clob) at the lockout moment,
sourced from metar_lockout.jsonl. Compare vs hold-to-resolution.
"""
import json, glob, pickle
from collections import defaultdict

# resolved STWA YES trades
ys = []
for ln in open("logs/trades.jsonl"):
    try: r = json.loads(ln)
    except: continue
    if r.get("bond_entry_class") == "WEATHER_STWA" and "YES" in str(r.get("direction", "")):
        ys.append(r)

# metar_lockout rows per token: (ts, running_max_c, hi, yes_bid_clob, yes_bid)
lk = defaultdict(list)
for fn in glob.glob("logs/shadow/hot/*/metar_lockout.jsonl"):
    for ln in open(fn):
        try: r = json.loads(ln)
        except: continue
        t = str(r.get("token_id"))
        lk[t].append((r.get("ts_s"), r.get("running_max_c"), r.get("bucket_hi_c_padded"),
                      r.get("yes_bid_clob"), r.get("yes_bid")))

def real_bid(row):
    b = row[3]  # yes_bid_clob (real CLOB)
    if b is None: b = row[4]  # implied yes_bid fallback
    return b if b is not None else 0.0

hold_tot = 0.0; model_tot = 0.0
n = 0; triggered = 0; saved_detail = []
winners = 0; overshoot = 0; undershoot = 0; false_exit = 0
for r in ys:
    tok = str(r.get("token_id")); entry = r.get("entry_price")
    outcome = (r.get("exit_price") if r.get("exit_price") is not None else 0.0)
    if entry is None: continue
    n += 1
    won = outcome >= 0.5
    if won: winners += 1
    hold_pnl = outcome - entry
    hold_tot += hold_pnl

    # find first lockout row during the hold (ts after open), running_max>hi
    t_open = r.get("ts_open", 0)
    rows = sorted([x for x in lk.get(tok, []) if x[0] and x[0] >= t_open
                   and x[1] is not None and x[2] is not None], key=lambda x: x[0])
    locks = [x for x in rows if x[1] > x[2]]
    # LIVE semantics: fire on running_max>hi regardless of eventual outcome (no
    # hindsight). NOTE: locks here use metar_lockout's raw station running_max,
    # which can be contaminated vs the official AWC/NWS oracle -> false exits on
    # eventual winners. A live build MUST gate on official_running_max_c.
    if locks:
        if won: false_exit += 1
        else: overshoot += 1
        exit_bid = real_bid(locks[0])                     # bid at FIRST lockout (act immediately)
        best10 = max((real_bid(x) for x in locks
                      if x[0] <= locks[0][0] + 600), default=exit_bid)  # best within 10 min
        triggered += 1
        model_pnl = exit_bid - entry
        model_tot += model_pnl
        saved_detail.append((tok[:8], entry, exit_bid, best10, model_pnl - hold_pnl, won))
    else:
        if not won: undershoot += 1
        model_tot += hold_pnl                              # no trigger -> hold

print(f"resolved STWA YES: n={n}  winners={winners}  overshoot-losers={overshoot}  undershoot/other-losers={undershoot}")
print(f"trigger-A fired (running_max>hi during hold): {triggered}  | of which FALSE exits on eventual winners: {false_exit}\n")
print(f"{'policy':38s} {'total/sh':>10s} {'mean/sh':>10s}")
print(f"{'HOLD_TO_RESOLUTION (baseline)':38s} {hold_tot:>10.3f} {hold_tot/n:>10.4f}")
print(f"{'MODEL-EXIT (running_max>hi, first bid)':38s} {model_tot:>10.3f} {model_tot/n:>10.4f}"
      f"   d={model_tot-hold_tot:+.3f}/sh")

# best-bid-within-10min variant
model_tot_best = 0.0
for r in ys:
    tok = str(r.get("token_id")); entry = r.get("entry_price")
    outcome = (r.get("exit_price") if r.get("exit_price") is not None else 0.0)
    if entry is None: continue
    won = outcome >= 0.5
    t_open = r.get("ts_open", 0)
    rows = sorted([x for x in lk.get(tok, []) if x[0] and x[0] >= t_open
                   and x[1] is not None and x[2] is not None], key=lambda x: x[0])
    locks = [x for x in rows if x[1] > x[2]]
    if locks and not won:
        best10 = max((real_bid(x) for x in locks if x[0] <= locks[0][0] + 600),
                     default=real_bid(locks[0]))
        model_tot_best += best10 - entry
    else:
        model_tot_best += outcome - entry
print(f"{'MODEL-EXIT (best bid <=10min post-lock)':38s} {model_tot_best:>10.3f} {model_tot_best/n:>10.4f}"
      f"   d={model_tot_best-hold_tot:+.3f}/sh")

print("\nper-trigger detail (token, entry, first_lock_bid, best10, save_vs_hold/sh):")
for d in sorted(saved_detail, key=lambda x: -x[4]):
    tag = "  <-- FALSE EXIT (eventual WINNER)" if d[5] else ""
    print(f"  {d[0]}  entry={d[1]:.3f}  lock_bid={d[2]:.3f}  best10={d[3]:.3f}  save={d[4]:+.3f}{tag}")
