"""LDA wrong-case breakdown by window size (5m vs 15m) and asset."""
import json, glob, os

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")
STAKE = 5.0

resolutions = {}
for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            r = json.loads(line)
            resolutions[(r["condition_id"], r["window_end_ts"], r.get("window_size_s", 300))] = r["moved_up"]

first_fire = {}
for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    with open(mt_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("record_type") != "market_timeline":
                continue
            wsz = r.get("window_size_s", 300)
            if wsz not in (300, 900):
                continue
            rem = r.get("seconds_to_resolution", 0.0)
            ask = r.get("best_ask", 0.0)
            bid = r.get("best_bid", 0.0)
            bnc = r.get("binance_ret_5m_pct", None)
            # Scale rem window for 15m: same relative entry (up to 90s before close)
            if not (8 <= rem <= 90):
                continue
            if not (0.70 <= ask <= 0.98):
                continue
            if bid < 0.50:
                continue
            if bnc is None or abs(bnc) < 0.07:
                continue
            odir = r.get("outcome_dir", "")
            bnc_dir = "up" if bnc > 0 else "down"
            if bnc_dir != odir:
                continue
            asset = r.get("asset", "UNK")
            key = (r["condition_id"], r["window_end_ts"], wsz)
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {
                    "rem":   rem,
                    "odir":  odir,
                    "ask":   ask,
                    "bnc":   bnc,
                    "asset": asset,
                    "wsz":   wsz,
                }

# Build result rows
rows = []
for key, ff in first_fire.items():
    res = resolutions.get(key)
    if res is None:
        continue
    is_correct = (ff["odir"] == "up") == res
    ff["correct"] = is_correct
    rows.append(ff)

def stats(subset):
    n = len(subset)
    if n == 0:
        return 0, 0, float("nan"), float("nan")
    nc = sum(1 for r in subset if r["correct"])
    wr = nc / n
    avg_ask = sum(r["ask"] for r in subset) / n
    ev = wr * STAKE * (1 - avg_ask) / avg_ask - (1 - wr) * STAKE - STAKE * 0.01
    return n, n - nc, wr, ev

print("=== BY WINDOW SIZE ===")
print(f"{'window':>10} {'n':>7} {'wrong':>7} {'wr':>8} {'ev/trade':>10}")
for wsz, label in [(300, "5m"), (900, "15m")]:
    subset = [r for r in rows if r["wsz"] == wsz]
    n, nw, wr, ev = stats(subset)
    print(f"{label:>10} {n:>7} {nw:>7} {wr:>8.2%} {ev:>10.4f}")

print()
print("=== BY ASSET ===")
print(f"{'asset':>8} {'n':>7} {'wrong':>7} {'wr':>8} {'ev/trade':>10}")
for asset in ["BTC", "ETH", "SOL"]:
    subset = [r for r in rows if r["asset"] == asset]
    n, nw, wr, ev = stats(subset)
    print(f"{asset:>8} {n:>7} {nw:>7} {wr:>8.2%} {ev:>10.4f}")

print()
print("=== ASSET x WINDOW SIZE ===")
print(f"{'asset':>6} {'window':>8} {'n':>7} {'wrong':>7} {'wr':>8} {'ev/trade':>10}")
for asset in ["BTC", "ETH", "SOL"]:
    for wsz, label in [(300, "5m"), (900, "15m")]:
        subset = [r for r in rows if r["asset"] == asset and r["wsz"] == wsz]
        n, nw, wr, ev = stats(subset)
        if n == 0:
            continue
        print(f"{asset:>6} {label:>8} {n:>7} {nw:>7} {wr:>8.2%} {ev:>10.4f}")

print()
print("=== BY ASSET x BNC ZONE ===")
print(f"{'asset':>6} {'bnc_zone':>14} {'n':>7} {'wrong':>7} {'wr':>8} {'ev/trade':>10}")
for asset in ["BTC", "ETH", "SOL"]:
    for blo, bhi in [(0.07, 0.10), (0.10, 0.15), (0.15, 99)]:
        subset = [r for r in rows if r["asset"] == asset and blo <= abs(r["bnc"]) < bhi]
        n, nw, wr, ev = stats(subset)
        if n == 0:
            continue
        label = f"[{blo:.2f},{bhi:.2f})"
        print(f"{asset:>6} {label:>14} {n:>7} {nw:>7} {wr:>8.2%} {ev:>10.4f}")

print()
print("=== BY ASSET x REMAINING TIME ===")
print(f"{'asset':>6} {'rem_bucket':>12} {'n':>7} {'wrong':>7} {'wr':>8}")
rem_buckets = [(8,30),(30,60),(60,90)]
for asset in ["BTC", "ETH", "SOL"]:
    for lo, hi in rem_buckets:
        subset = [r for r in rows if r["asset"] == asset and lo <= r["rem"] < hi]
        n, nw, wr, ev = stats(subset)
        if n < 5:
            continue
        print(f"{asset:>6} [{lo:>2}s,{hi:>3}s)  {n:>7} {nw:>7} {wr:>8.2%}")
