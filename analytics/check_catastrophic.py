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

# Filter: live TERMINAL trades only (last 7 days)
cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
terminal = [
    t for t in trades
    if t.get("bond_entry_class") == "TERMINAL"
    and not t.get("dry_run")
    and t.get("entry_ts", 0) >= cutoff
    and t.get("entry_price", 0) > 0
]

n_total = len(terminal)
print(f"\n=== BOND_CATASTROPHIC analysis | n={n_total} TERMINAL trades (7d) ===\n")

# Helper
def bucket_stats(trades, label=""):
    n = len(trades)
    if n == 0:
        return f"  {label}: n=0"
    wins = [t for t in trades if t.get("net_pnl", 0) > 0]
    pnl = sum(t.get("net_pnl", 0) for t in trades)
    wr = len(wins) / n * 100
    return f"  {label}: n={n:3d}  WR={wr:5.1f}%  sum=${pnl:+.2f}  avg=${pnl/n:+.2f}"

cat = [t for t in terminal if t.get("exit_reason") == "BOND_CATASTROPHIC"]
non_cat = [t for t in terminal if t.get("exit_reason") != "BOND_CATASTROPHIC"]

print(bucket_stats(terminal, "ALL TERMINAL"))
print(bucket_stats(cat,     "BOND_CATASTROPHIC"))
print(bucket_stats(non_cat, "NON-CATASTROPHIC"))

# By asset
print("\n--- BOND_CATASTROPHIC by asset ---")
for asset in ["BTC", "ETH", "SOL"]:
    sub = [t for t in cat if t.get("asset") == asset]
    print(bucket_stats(sub, asset))

# BOND_CATASTROPHIC by hour
print("\n--- BOND_CATASTROPHIC by UTC hour ---")
by_hour = collections.defaultdict(list)
for t in cat:
    ts = t.get("entry_ts", 0)
    if ts:
        h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        by_hour[h].append(t)
for h in sorted(by_hour):
    print(bucket_stats(by_hour[h], f"hr={h:02d}"))

# What fraction of losses would have been avoided (MAE/resolution proxy)
# Use exit_price vs entry_price: if exit_price < entry_price it was a loss stop
print("\n--- BOND_CATASTROPHIC: exit price distribution ---")
prices = [t.get("exit_price", 0) for t in cat if t.get("exit_price", 0) > 0]
if prices:
    print(f"  exit_price: min={min(prices):.4f}  avg={sum(prices)/len(prices):.4f}  max={max(prices):.4f}")
    buckets = {"<0.50": 0, "0.50-0.65": 0, "0.65-0.75": 0, "0.75+": 0}
    for p in prices:
        if p < 0.50: buckets["<0.50"] += 1
        elif p < 0.65: buckets["0.50-0.65"] += 1
        elif p < 0.75: buckets["0.65-0.75"] += 1
        else: buckets["0.75+"] += 1
    for k, v in buckets.items():
        print(f"  {k}: n={v}")

# Non-cat exit reasons
print("\n--- Non-catastrophic exit reasons ---")
reasons = collections.Counter(t.get("exit_reason", "?") for t in non_cat)
for reason, cnt in reasons.most_common():
    sub = [t for t in non_cat if t.get("exit_reason") == reason]
    pnl = sum(t.get("net_pnl", 0) for t in sub)
    wins = sum(1 for t in sub if t.get("net_pnl", 0) > 0)
    print(f"  {reason:<30s} n={cnt:3d}  WR={wins/cnt*100:5.1f}%  sum=${pnl:+.2f}")

# Asset × hour breakdown for ALL terminal (identify best/worst combos)
print("\n--- ALL TERMINAL: WR by asset × UTC hour (n>=5) ---")
by_ah = collections.defaultdict(list)
for t in terminal:
    ts = t.get("entry_ts", 0)
    if ts:
        h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        key = (t.get("asset", "?"), h)
        by_ah[key].append(t)
rows = []
for (asset, h), bucket in by_ah.items():
    if len(bucket) < 5:
        continue
    wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
    pnl = sum(t.get("net_pnl", 0) for t in bucket)
    rows.append((asset, h, len(bucket), wins/len(bucket)*100, pnl))
for asset, h, n, wr, pnl in sorted(rows, key=lambda x: (x[0], x[1])):
    flag = " <<<" if wr < 40 else (" ***" if wr > 70 else "")
    print(f"  {asset} hr={h:02d}  n={n:3d}  WR={wr:5.1f}%  sum=${pnl:+.2f}{flag}")

# entry_price bucket analysis
print("\n--- TERMINAL: WR by entry_price bucket ---")
ep_buckets = collections.defaultdict(list)
for t in terminal:
    ep = t.get("entry_price", 0)
    if ep <= 0: continue
    b = round(int(ep * 100 / 2) * 2) / 100  # 2-cent buckets
    ep_buckets[b].append(t)
for b in sorted(ep_buckets):
    bucket = ep_buckets[b]
    if len(bucket) < 3: continue
    wins = sum(1 for t in bucket if t.get("net_pnl", 0) > 0)
    pnl = sum(t.get("net_pnl", 0) for t in bucket)
    print(f"  ep={b:.2f}-{b+0.02:.2f}  n={len(bucket):3d}  WR={wins/len(bucket)*100:5.1f}%  sum=${pnl:+.2f}")

print()
