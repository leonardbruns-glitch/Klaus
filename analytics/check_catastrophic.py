"""
BOND_CATASTROPHIC analysis — run on VPS:
  python3 analytics/check_catastrophic.py
"""
import json, os, collections
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(__file__), "../logs/trades.jsonl")
CUTOFF = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc).timestamp()

trades = []
with open(LOG) as f:
    for line in f:
        try:
            t = json.loads(line)
            if t.get("ts_open", t.get("entry_ts", 0)) >= CUTOFF:
                trades.append(t)
        except Exception:
            pass

print(f"Total trades in file: {len(trades)}")

if not trades:
    print("No trades found.")
    exit()

# Dry run breakdown
dry = [t for t in trades if t.get("dry_run")]
live = [t for t in trades if not t.get("dry_run")]
print(f"  dry_run=True: {len(dry)}")
print(f"  dry_run=False/missing: {len(live)}")

# Timestamp range
def fmt_ts(ts):
    if not ts: return "?"
    try: return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except: return str(ts)

all_ts = [t.get("entry_ts", 0) for t in trades if t.get("entry_ts")]
if all_ts:
    print(f"  entry_ts range: {fmt_ts(min(all_ts))} → {fmt_ts(max(all_ts))}")

# Sample most recent trade (regardless of dry_run)
most_recent = sorted(trades, key=lambda t: t.get("entry_ts", 0))[-1]
print(f"\nMost recent trade:")
for k in sorted(most_recent.keys()):
    print(f"  {k}: {most_recent.get(k)}")

# Work with all trades (no dry_run filter, no date filter) to see structure
all_bond = [t for t in trades if t.get("is_bond") or t.get("signal_source") == "BOND"
            or t.get("bond_entry_class")]
print(f"\nBOND trades (any indicator): {len(all_bond)}")
print(f"  bond_entry_class values: {collections.Counter(t.get('bond_entry_class','(missing)') for t in all_bond).most_common()}")
print(f"  signal_source values: {collections.Counter(t.get('signal_source','(missing)') for t in trades).most_common(5)}")
print(f"  dry_run in bond: {collections.Counter(t.get('dry_run') for t in all_bond).most_common()}")

# Now use all live bond trades (no date cutoff)
target = [t for t in all_bond if not t.get("dry_run")]
if not target:
    print("\nNo live BOND trades found — checking if dry_run field is set differently...")
    # Maybe dry_run is stored as string
    sample_dr = [t.get("dry_run") for t in trades[:5]]
    print(f"  dry_run sample values: {sample_dr}")
    # Try without any filter
    target = all_bond
    print(f"  Using all bond trades (including dry_run): n={len(target)}")

print(f"\n=== Analysis on n={len(target)} BOND trades ===\n")

if not target:
    print("No data to analyze.")
    exit()

def stats(bucket, label):
    n = len(bucket)
    if n == 0:
        return f"  {label}: n=0"
    wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
    pnl = sum(t.get("net_pnl", 0) for t in bucket)
    return f"  {label}: n={n:3d}  WR={wins/n*100:5.1f}%  sum=${pnl:+.2f}  avg=${pnl/n:+.2f}"

cat = [t for t in target if t.get("exit_reason") == "BOND_CATASTROPHIC"]
non_cat = [t for t in target if t.get("exit_reason") != "BOND_CATASTROPHIC"]

print(stats(target,  "ALL BOND"))
print(stats(cat,     "BOND_CATASTROPHIC"))
print(stats(non_cat, "NON-CATASTROPHIC"))

print("\n  BOND_CATASTROPHIC by asset:")
for asset in ["BTC", "ETH", "SOL"]:
    print(stats([t for t in cat if t.get("asset") == asset], f"  {asset}"))

print("\n  BOND_CATASTROPHIC by UTC hour:")
by_hour = collections.defaultdict(list)
for t in cat:
    ts = t.get("entry_ts", 0)
    if ts:
        by_hour[datetime.fromtimestamp(float(ts), tz=timezone.utc).hour].append(t)
for h in sorted(by_hour):
    print(stats(by_hour[h], f"  hr={h:02d}"))

print("\n  Exit price distribution (BOND_CATASTROPHIC):")
prices = [t.get("exit_price", 0) for t in cat if t.get("exit_price", 0) > 0]
if prices:
    print(f"    min={min(prices):.4f}  avg={sum(prices)/len(prices):.4f}  max={max(prices):.4f}")
else:
    print("    (no exit_price data)")

print("\n  ALL BOND exit reasons:")
for reason, cnt in collections.Counter(t.get("exit_reason") for t in target).most_common():
    sub = [t for t in target if t.get("exit_reason") == reason]
    pnl = sum(t.get("net_pnl", 0) for t in sub)
    wins = sum(1 for t in sub if t.get("net_pnl", 0) > 0)
    print(f"    {str(reason):<35s} n={cnt:3d}  WR={wins/cnt*100:5.1f}%  sum=${pnl:+.2f}")

print("\n  BOND: WR by asset × UTC hour (n>=3):")
by_ah = collections.defaultdict(list)
for t in target:
    ts = t.get("entry_ts", 0)
    if ts:
        h = datetime.fromtimestamp(float(ts), tz=timezone.utc).hour
        by_ah[(t.get("asset", "?"), h)].append(t)
for (asset, h), bucket in sorted(by_ah.items()):
    if len(bucket) < 3: continue
    wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
    pnl = sum(t.get("net_pnl", 0) for t in bucket)
    n = len(bucket)
    flag = " <<<" if wins/n < 0.40 else (" ***" if wins/n > 0.70 else "")
    print(f"    {asset} hr={h:02d}  n={n:3d}  WR={wins/n*100:5.1f}%  sum=${pnl:+.2f}{flag}")

print("\n  BOND: WR by entry_price bucket:")
ep_b = collections.defaultdict(list)
for t in target:
    ep = t.get("entry_price", 0)
    if ep > 0:
        b = round(int(ep * 100 / 2) * 2) / 100
        ep_b[b].append(t)
for b in sorted(ep_b):
    bucket = ep_b[b]
    if len(bucket) < 3: continue
    wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
    pnl = sum(t.get("net_pnl", 0) for t in bucket)
    print(f"    ep={b:.2f}-{b+0.02:.2f}  n={len(bucket):3d}  WR={wins/len(bucket)*100:5.1f}%  sum=${pnl:+.2f}")

print()

# ── Hold-bucket analysis (requires wick_events.jsonl) ────────────────────────
WICK_LOG = os.path.join(os.path.dirname(__file__), "../logs/wick_events.jsonl")
if os.path.exists(WICK_LOG):
    wick_events = []
    with open(WICK_LOG) as wf:
        for line in wf:
            try:
                wick_events.append(json.loads(line))
            except Exception:
                pass

    arms      = [e for e in wick_events if e.get("event_type") == "WICK_ARM"      and e.get("bc_hold_bucket")]
    cancels   = [e for e in wick_events if e.get("event_type") == "WICK_CANCEL"   and e.get("bc_hold_bucket")]
    confirms  = [e for e in wick_events if e.get("event_type") == "WICK_CONFIRM"  and e.get("bc_hold_bucket")]
    reversals = [e for e in wick_events if e.get("event_type") == "WICK_REVERSAL" and e.get("bc_hold_bucket")]
    closeds   = [e for e in wick_events if e.get("event_type") == "WICK_ARM_CLOSED"]

    print(f"\n=== POST_BC_REVERSAL_RATE (n_arm={len(arms)}, n_closed={len(closeds)}, n_reversal={len(reversals)}) ===")
    print("  reversal_rate = % of BC-ARM trades where price recovered above entry")
    print("  cancel_rate   = % where wick filter fired (price recovered to -12%)")
    print("  NOTE: only events after 2026-04-28 deploy carry bc_hold_bucket\n")

    for bucket in ["fast", "mid", "late"]:
        a  = [e for e in arms      if e.get("bc_hold_bucket") == bucket]
        k  = [e for e in cancels   if e.get("bc_hold_bucket") == bucket]
        c  = [e for e in confirms  if e.get("bc_hold_bucket") == bucket]
        rv = [e for e in reversals if e.get("bc_hold_bucket") == bucket]
        cl = [e for e in closeds   if e.get("bc_hold_bucket") == bucket]

        n_a  = len(a)
        n_cl = len(cl)    # closed positions that had an ARM (complete outcomes)

        if n_a == 0:
            print(f"  [{bucket:4s}]: no events yet")
            continue

        wick_windows = [e.get("wick_window_s") for e in a if e.get("wick_window_s")]
        ww = wick_windows[0] if wick_windows else "?"

        # Reversal rate from WICK_ARM_CLOSED records (most reliable — full position lifecycle)
        if n_cl > 0:
            cl_reversed = [e for e in cl if e.get("reversed")]
            rev_rate = len(cl_reversed) / n_cl * 100
            rev_str = f"  reversal_rate={rev_rate:.0f}% ({len(cl_reversed)}/{n_cl} closed)"
        else:
            rev_rate = len(rv) / n_a * 100
            rev_str = f"  reversal_rate={rev_rate:.0f}% ({len(rv)}/{n_a} arms, incomplete)"

        cancel_rate  = len(k) / n_a * 100 if n_a else 0
        confirm_rate = len(c) / n_a * 100 if n_a else 0

        print(f"  [{bucket:4s}] window={ww}s  arms={n_a:3d}  cancel={cancel_rate:.0f}%  confirm={confirm_rate:.0f}%{rev_str}")

        # Time-to-reversal distribution
        if rv:
            t_rev = sorted(e.get("elapsed_to_reversal_s", 0) for e in rv)
            p50 = t_rev[len(t_rev) // 2]
            p90 = t_rev[int(len(t_rev) * 0.9)]
            print(f"         time_to_reversal: p50={p50:.0f}s  p90={p90:.0f}s  max={max(t_rev):.0f}s")

        # Reversal rate by time window (X seconds after breach)
        if cl and len(cl) >= 5:
            print(f"         reversal_by_window (of {n_cl} closed):", end="")
            for window_s in [10, 20, 30, 60]:
                # count reversals where elapsed_to_reversal_s <= window_s
                rev_in_window = sum(
                    1 for e in cl
                    if e.get("reversed") and
                    any(r.get("elapsed_to_reversal_s", 999) <= window_s
                        for r in reversals
                        if r.get("bc_hold_bucket") == bucket)
                )
                # simpler: use reversal events directly
                rv_w = [r for r in rv if r.get("elapsed_to_reversal_s", 999) <= window_s]
                print(f"  <{window_s}s:{len(rv_w)}/{len(cl)}", end="")
            print()

    print("\n  Hypothesis: late reversal_rate >> fast reversal_rate.")
    print("  Validate at n>=100 closed per bucket before changing thresholds.")
else:
    print("\n  (wick_events.jsonl not found — run from /root/Klaus)")
