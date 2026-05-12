"""
LDA signal accuracy by remaining-time bucket.
Uses shadow market_timeline + window_resolution records (May 8-12).
One row per window: first tick where LDA would have fired.
"""
import json, os, glob
from collections import defaultdict

ASK_FLOOR    = 0.70
ASK_CEIL     = 0.994
BID_MIN      = 0.50
REM_MIN_S    = 8.0
REM_MAX_S    = 90.0
BNC_MOVE_MIN = 0.07
WINDOW_S     = 300  # 5m only

SHADOW_ROOT = "logs/shadow/hot"

# ── 1. Collect window resolutions ────────────────────────────────────────────
# window_resolution records: {condition_id, window_end_ts, outcome_dir_actual}
# outcome_dir_actual = "up" if kline close > open else "down"
resolutions = {}  # (cid, wend) -> "up" / "down"

for date_dir in sorted(glob.glob(f"{SHADOW_ROOT}/*/market_timeline.jsonl")):
    date_str = date_dir.split("/")[-2]
    res_path = date_dir.replace("market_timeline.jsonl", "market_timeline.jsonl")
    # window_resolution might be inline in market_timeline or separate
    pass

# Also try dedicated window_resolution file
for date_dir in sorted(glob.glob(f"{SHADOW_ROOT}/*")):
    wr_path = os.path.join(date_dir, "window_resolution.jsonl")
    if os.path.exists(wr_path):
        with open(wr_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("record_type") == "window_resolution":
                        cid  = r.get("condition_id", "")
                        wend = r.get("window_end_ts", 0)
                        # kline_open vs kline_close
                        ko = r.get("kline_open", 0.0)
                        kc = r.get("kline_close", 0.0)
                        if ko and kc:
                            resolutions[(cid, wend)] = "up" if kc >= ko else "down"
                except Exception:
                    pass

# Also check market_timeline for inline resolution records
for mt_path in sorted(glob.glob(f"{SHADOW_ROOT}/*/market_timeline.jsonl")):
    with open(mt_path) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("record_type") == "window_resolution":
                    cid  = r.get("condition_id", "")
                    wend = r.get("window_end_ts", 0)
                    ko = r.get("kline_open", 0.0)
                    kc = r.get("kline_close", 0.0)
                    if ko and kc:
                        resolutions[(cid, wend)] = "up" if kc >= ko else "down"
            except Exception:
                pass

print(f"Resolutions loaded: {len(resolutions)}")

# ── 2. Find first LDA-eligible tick per window ───────────────────────────────
# Scan market_timeline in reverse (latest first per window) to find first tick
# where LDA would have fired (highest remaining = earliest in window scan order)

# first_fire[(cid, wend)] = {rem, bnc_dir, outcome_dir_token, asset}
first_fire = {}

for mt_path in sorted(glob.glob(f"{SHADOW_ROOT}/*/market_timeline.jsonl")):
    with open(mt_path) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("record_type") != "market_timeline":
                    continue
                if r.get("window_size_s", 0) != WINDOW_S:
                    continue

                rem  = r.get("seconds_to_resolution", 0.0)
                ask  = r.get("best_ask", 0.0)
                bid  = r.get("best_bid", 0.0)
                bnc  = r.get("binance_ret_5m_pct", None)
                cid  = r.get("condition_id", "")
                wend = r.get("window_end_ts", 0)
                odir = r.get("outcome_dir", "")  # token direction label

                if not (REM_MIN_S <= rem <= REM_MAX_S):
                    continue
                if not (ASK_FLOOR <= ask <= ASK_CEIL):
                    continue
                if bid < BID_MIN:
                    continue
                if bnc is None or abs(bnc) < BNC_MOVE_MIN:
                    continue

                bnc_dir = "up" if bnc > 0 else "down"
                if bnc_dir != odir:
                    continue  # not the predicted-winner token

                key = (cid, wend)
                # Keep the tick with highest rem (= earliest fire = first eligible tick)
                if key not in first_fire or rem > first_fire[key]["rem"]:
                    first_fire[key] = {
                        "rem":      rem,
                        "bnc_dir":  bnc_dir,
                        "odir":     odir,
                        "asset":    r.get("asset", ""),
                        "ask":      ask,
                        "bnc_move": bnc,
                    }
            except Exception:
                pass

print(f"Windows with LDA-eligible first-fire tick: {len(first_fire)}")
print(f"Windows with resolution data:              {len(resolutions)}")

# ── 3. Join and bucket ───────────────────────────────────────────────────────
buckets = defaultdict(lambda: {"n": 0, "correct": 0})

matched = 0
for key, ff in first_fire.items():
    res = resolutions.get(key)
    if res is None:
        continue
    matched += 1
    rem = ff["rem"]
    correct = (ff["bnc_dir"] == res)

    # bucket by remaining time
    if rem <= 20:
        b = "T-08 to T-20s"
    elif rem <= 30:
        b = "T-20 to T-30s"
    elif rem <= 45:
        b = "T-30 to T-45s"
    elif rem <= 60:
        b = "T-45 to T-60s"
    elif rem <= 75:
        b = "T-60 to T-75s"
    else:
        b = "T-75 to T-90s"

    buckets[b]["n"] += 1
    if correct:
        buckets[b]["correct"] += 1

print(f"\nMatched windows (fire + resolution): {matched}")
print(f"\n{'Bucket':<18} {'n':>5} {'correct':>8} {'accuracy':>10}")
print("-" * 46)
for b in ["T-08 to T-20s", "T-20 to T-30s", "T-30 to T-45s", "T-45 to T-60s", "T-60 to T-75s", "T-75 to T-90s"]:
    d = buckets[b]
    n = d["n"]
    c = d["correct"]
    acc = f"{c/n*100:.1f}%" if n > 0 else "—"
    print(f"{b:<18} {n:>5} {c:>8} {acc:>10}")

total_n = sum(d["n"] for d in buckets.values())
total_c = sum(d["correct"] for d in buckets.values())
print("-" * 46)
print(f"{'TOTAL':<18} {total_n:>5} {total_c:>8} {total_c/total_n*100:.1f}%" if total_n else "no data")
