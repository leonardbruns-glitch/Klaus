"""
BOND_CATASTROPHIC analysis — run on VPS:
  python3 analytics/check_catastrophic.py
"""
import json, os, collections
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(__file__), "../logs/trades.jsonl")

trades = []
with open(LOG) as f:
    for line in f:
        try:
            trades.append(json.loads(line))
        except Exception:
            pass

cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
recent = [t for t in trades if t.get("entry_ts", 0) >= cutoff and not t.get("dry_run")]

print(f"\nTotal trades in file: {len(trades)}")
print(f"Recent (7d) non-dryrun: {len(recent)}")

if recent:
    sample = recent[-1]
    print(f"\nMost recent trade keys: {sorted(sample.keys())}")
    print(f"\nSample values:")
    for k in ["asset", "exit_reason", "bond_entry_class", "signal_source", "is_bond", "entry_price", "net_pnl"]:
        print(f"  {k}: {sample.get(k, '(missing)')}")

# Show all exit_reason values
print("\n--- exit_reason distribution (7d) ---")
for reason, cnt in collections.Counter(t.get("exit_reason", "?") for t in recent).most_common():
    sub = [t for t in recent if t.get("exit_reason") == reason]
    pnl = sum(t.get("net_pnl", 0) for t in sub)
    wins = sum(1 for t in sub if t.get("net_pnl", 0) > 0)
    print(f"  {reason:<30s} n={cnt:3d}  WR={wins/cnt*100:5.1f}%  sum=${pnl:+.2f}")

# Show all bond_entry_class values
print("\n--- bond_entry_class distribution (7d) ---")
for cls, cnt in collections.Counter(t.get("bond_entry_class", "(missing)") for t in recent).most_common():
    print(f"  {cls}: n={cnt}")

# Show all signal_source values
print("\n--- signal_source distribution (7d) ---")
for src, cnt in collections.Counter(t.get("signal_source", "(missing)") for t in recent).most_common():
    print(f"  {src}: n={cnt}")

# Use is_bond=True as TERMINAL proxy if bond_entry_class missing
bond_trades = [t for t in recent if t.get("is_bond") or t.get("signal_source") == "BOND"]
print(f"\n--- BOND trades (is_bond=True or signal_source=BOND): n={len(bond_trades)} ---")

if bond_trades:
    cat = [t for t in bond_trades if t.get("exit_reason") == "BOND_CATASTROPHIC"]
    non_cat = [t for t in bond_trades if t.get("exit_reason") != "BOND_CATASTROPHIC"]

    def stats(bucket, label):
        n = len(bucket)
        if n == 0:
            return f"  {label}: n=0"
        wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
        pnl = sum(t.get("net_pnl", 0) for t in bucket)
        return f"  {label}: n={n:3d}  WR={wins/n*100:5.1f}%  sum=${pnl:+.2f}  avg=${pnl/n:+.2f}"

    print(stats(bond_trades, "ALL BOND"))
    print(stats(cat,         "BOND_CATASTROPHIC"))
    print(stats(non_cat,     "NON-CATASTROPHIC"))

    print("\n  BOND_CATASTROPHIC by asset:")
    for asset in ["BTC", "ETH", "SOL"]:
        print(stats([t for t in cat if t.get("asset") == asset], f"  {asset}"))

    print("\n  BOND_CATASTROPHIC by UTC hour:")
    by_hour = collections.defaultdict(list)
    for t in cat:
        ts = t.get("entry_ts", 0)
        if ts:
            by_hour[datetime.fromtimestamp(ts, tz=timezone.utc).hour].append(t)
    for h in sorted(by_hour):
        print(stats(by_hour[h], f"  hr={h:02d}"))

    print("\n  Exit price distribution (BOND_CATASTROPHIC):")
    prices = [t.get("exit_price", 0) for t in cat if t.get("exit_price", 0) > 0]
    if prices:
        print(f"    min={min(prices):.4f}  avg={sum(prices)/len(prices):.4f}  max={max(prices):.4f}")
    else:
        print("    (no exit_price data)")

    print("\n  ALL BOND exit reasons:")
    for reason, cnt in collections.Counter(t.get("exit_reason") for t in bond_trades).most_common():
        sub = [t for t in bond_trades if t.get("exit_reason") == reason]
        pnl = sum(t.get("net_pnl", 0) for t in sub)
        wins = sum(1 for t in sub if t.get("net_pnl", 0) > 0)
        print(f"    {reason:<30s} n={cnt:3d}  WR={wins/cnt*100:5.1f}%  sum=${pnl:+.2f}")

    print("\n  BOND: WR by asset × UTC hour (n>=3):")
    by_ah = collections.defaultdict(list)
    for t in bond_trades:
        ts = t.get("entry_ts", 0)
        if ts:
            h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
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
    for t in bond_trades:
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
