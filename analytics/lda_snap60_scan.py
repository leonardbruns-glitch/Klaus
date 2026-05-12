"""Threshold scan on tok_snap60 for LDA signal filtering."""
import json, glob, os

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")
STAKE = 5.0

resolutions = {}
for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("window_size_s", 0) != 300:
                continue
            resolutions[(r["condition_id"], r["window_end_ts"])] = r["moved_up"]

first_fire = {}
for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    with open(mt_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("record_type") != "market_timeline":
                continue
            if r.get("window_size_s", 0) != 300:
                continue
            rem = r.get("seconds_to_resolution", 0.0)
            ask = r.get("best_ask", 0.0)
            bid = r.get("best_bid", 0.0)
            bnc = r.get("binance_ret_5m_pct", None)
            if not (8 <= rem <= 90):
                continue
            if not (0.70 <= ask <= 0.994):
                continue
            if bid < 0.50:
                continue
            if bnc is None or abs(bnc) < 0.07:
                continue
            odir = r.get("outcome_dir", "")
            bnc_dir = "up" if bnc > 0 else "down"
            if bnc_dir != odir:
                continue
            key = (r["condition_id"], r["window_end_ts"])
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {
                    "rem":    rem,
                    "odir":   odir,
                    "ask":    ask,
                    "snap60": r.get("tok_snap_60s", 0.0) or 0.0,
                    "snap30": r.get("tok_snap_30s", 0.0) or 0.0,
                    "delta5s": r.get("tok_delta_5s", 0.0) or 0.0,
                    "spread": r.get("spread_bps", 0.0) or 0.0,
                    "ob_imb": r.get("ob_imb_top3", 0.0) or 0.0,
                    "bnc":    bnc,
                    "asset":  r.get("asset", ""),
                }

all_rows = []
for key, ff in first_fire.items():
    res = resolutions.get(key)
    if res is None:
        continue
    is_correct = (ff["odir"] == "up") == res
    sign = 1 if ff["odir"] == "up" else -1
    ff["signed_snap60"] = ff["snap60"] * sign
    ff["signed_snap30"] = ff["snap30"] * sign
    ff["correct"] = is_correct
    all_rows.append(ff)

print(f"Total rows: {len(all_rows)}")
print()

print("=== THRESHOLD SCAN: reject if tok_snap60_signed >= t (token already ran) ===")
print(f"{'cap_t':>8} {'n_kept':>8} {'n_rej':>7} {'wr_kept':>8} {'wr_rej':>8} {'ev/trade':>10} {'pct_kept':>10}")
for t in [-20, -10, -5, 0, 5, 10, 15, 20, 30, 50, 9999]:
    kept = [r for r in all_rows if r["signed_snap60"] < t]
    rej  = [r for r in all_rows if r["signed_snap60"] >= t]
    n_k, n_r = len(kept), len(rej)
    if n_k == 0:
        continue
    wr_k = sum(1 for r in kept if r["correct"]) / n_k
    wr_r = sum(1 for r in rej  if r["correct"]) / n_r if n_r else float("nan")
    avg_ask_k = sum(r["ask"] for r in kept) / n_k
    ev = wr_k * STAKE * (1 - avg_ask_k) / avg_ask_k - (1 - wr_k) * STAKE - STAKE * 0.01
    pct = n_k / len(all_rows) * 100
    print(f"{t:>8} {n_k:>8} {n_r:>7} {wr_k:>8.2%} {wr_r:>8.2%} {ev:>10.4f} {pct:>9.1f}%")

print()
print("=== 2D: ask_band x snap60 cap ===")
for ask_lo, ask_hi in [(0.70, 0.85), (0.85, 0.95), (0.95, 0.994)]:
    print(f"\n  ask [{ask_lo:.2f}, {ask_hi:.2f})")
    print(f"  {'snap60_cap':>12} {'n':>6} {'wr':>7} {'ev/trade':>10}")
    for t in [-99, 0, 5, 10, 20, 9999]:
        rows = [r for r in all_rows if ask_lo <= r["ask"] < ask_hi and r["signed_snap60"] < t]
        if len(rows) < 10:
            continue
        wr = sum(1 for r in rows if r["correct"]) / len(rows)
        avg_ask = sum(r["ask"] for r in rows) / len(rows)
        ev = wr * STAKE * (1 - avg_ask) / avg_ask - (1 - wr) * STAKE - STAKE * 0.01
        print(f"  {t:>12} {len(rows):>6} {wr:>7.2%} {ev:>10.4f}")

print()
print("=== DISTRIBUTION of signed_snap60 in wrong cases ===")
wrong = [r for r in all_rows if not r["correct"]]
buckets = [(-999,-20),(-20,-10),(-10,-5),(-5,0),(0,5),(5,10),(10,20),(20,50),(50,999)]
print(f"{'snap60 range':>20} {'n_wrong':>8} {'n_total':>8} {'wrong_rate':>11}")
for lo, hi in buckets:
    n_w = sum(1 for r in wrong if lo <= r["signed_snap60"] < hi)
    n_t = sum(1 for r in all_rows if lo <= r["signed_snap60"] < hi)
    if n_t == 0:
        continue
    print(f"[{lo:>6}, {hi:>5})  {n_w:>8} {n_t:>8} {n_w/n_t:>10.1%}")
