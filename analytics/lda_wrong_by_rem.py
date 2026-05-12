"""Wrong-case distribution by entry remaining time (seconds to resolution)."""
import json, glob, os

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")

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
                    "rem":  rem,
                    "odir": odir,
                    "ask":  ask,
                    "bnc":  bnc,
                }

buckets = [(8, 20), (20, 30), (30, 45), (45, 60), (60, 75), (75, 90)]
print("Wrong-case distribution by entry remaining time:")
print(f"{'rem bucket':>15} {'n_correct':>10} {'n_wrong':>9} {'wr':>7} {'pct_wrong':>10}")
for lo, hi in buckets:
    correct = wrong = 0
    for key, ff in first_fire.items():
        res = resolutions.get(key)
        if res is None:
            continue
        if not (lo <= ff["rem"] < hi):
            continue
        if (ff["odir"] == "up") == res:
            correct += 1
        else:
            wrong += 1
    n = correct + wrong
    if n == 0:
        continue
    print(f"[{lo:>2}s,{hi:>3}s)  {correct:>10} {wrong:>9} {correct/n:>7.1%} {wrong/n:>9.1%}")

print()
print("BNC zone x remaining time (wrong rate):")
bnc_bands = [(0.07, 0.10), (0.10, 0.15), (0.15, 99)]
print(f"{'bnc_band':>15}", end="")
for lo, hi in buckets:
    print(f"  [{lo:>2}s,{hi:>3}s)", end="")
print()
for blo, bhi in bnc_bands:
    label = f"bnc [{blo:.2f},{bhi:.2f})"
    print(f"{label:>15}", end="")
    for lo, hi in buckets:
        correct = wrong = 0
        for key, ff in first_fire.items():
            res = resolutions.get(key)
            if res is None:
                continue
            if not (lo <= ff["rem"] < hi):
                continue
            if not (blo <= abs(ff["bnc"]) < bhi):
                continue
            if (ff["odir"] == "up") == res:
                correct += 1
            else:
                wrong += 1
        n = correct + wrong
        if n == 0:
            print(f"  {'—':>9}", end="")
        else:
            print(f"  {wrong/n:>8.0%}(n={n})", end="")
    print()
