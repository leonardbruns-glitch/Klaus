"""
LDA signal accuracy by remaining-time bucket.
Uses shadow market_timeline + window_resolution records (May 8-12).
One row per window: first tick where LDA would have fired.
"""
import json, os, glob
from collections import defaultdict

BASEDIR      = os.path.join(os.path.dirname(__file__), "..")
SHADOW_ROOT  = os.path.join(BASEDIR, "logs", "shadow", "hot")

ASK_FLOOR    = 0.70
ASK_CEIL     = 0.994
BID_MIN      = 0.50
REM_MIN_S    = 8.0
REM_MAX_S    = 90.0
BNC_MOVE_MIN = 0.07
WINDOW_S     = 300  # 5m only

# ── 1. Load window resolutions ───────────────────────────────────────────────
# moved_up=True means price went up -> UP token paid $1
resolutions = {}  # (cid, wend) -> True/False (moved_up)

for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("window_size_s", 0) != WINDOW_S:
                    continue
                cid  = r.get("condition_id", "")
                wend = r.get("window_end_ts", 0)
                if cid and wend:
                    resolutions[(cid, wend)] = bool(r.get("moved_up", False))
            except Exception:
                pass

print(f"Resolutions loaded: {len(resolutions)}")

# ── 2. Find first eligible LDA tick per window ───────────────────────────────
# first_fire[(cid, wend)] = highest rem tick that passes all LDA gates
first_fire = {}

for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
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
                odir = r.get("outcome_dir", "")

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
                # Keep highest rem = earliest eligible tick in the window
                if key not in first_fire or rem > first_fire[key]["rem"]:
                    first_fire[key] = {
                        "rem":   rem,
                        "odir":  odir,
                        "asset": r.get("asset", ""),
                        "ask":   ask,
                        "bnc":   bnc,
                    }
            except Exception:
                pass

print(f"Windows with eligible first-fire tick: {len(first_fire)}")

# ── 3. Join and bucket ───────────────────────────────────────────────────────
buckets = defaultdict(lambda: {"n": 0, "correct": 0})
unmatched = 0

for key, ff in first_fire.items():
    res = resolutions.get(key)
    if res is None:
        unmatched += 1
        continue

    moved_up = res
    # Correct if we bought the winner: UP token + price went up, or DOWN token + price went down
    correct = (ff["odir"] == "up") == moved_up

    rem = ff["rem"]
    if rem <= 20:
        b = "T-08..20s"
    elif rem <= 30:
        b = "T-20..30s"
    elif rem <= 45:
        b = "T-30..45s"
    elif rem <= 60:
        b = "T-45..60s"
    elif rem <= 75:
        b = "T-60..75s"
    else:
        b = "T-75..90s"

    buckets[b]["n"] += 1
    if correct:
        buckets[b]["correct"] += 1

matched = sum(d["n"] for d in buckets.values())
print(f"Matched (fire + resolution): {matched}  |  no resolution: {unmatched}")

print(f"\n{'Bucket':<14} {'n':>5} {'acc':>8}")
print("-" * 30)
order = ["T-08..20s","T-20..30s","T-30..45s","T-45..60s","T-60..75s","T-75..90s"]
for b in order:
    d = buckets[b]
    n, c = d["n"], d["correct"]
    acc = f"{c/n*100:.1f}%" if n else "—"
    print(f"{b:<14} {n:>5} {acc:>8}")

total_n = matched
total_c = sum(d["correct"] for d in buckets.values())
print("-" * 30)
if total_n:
    print(f"{'TOTAL':<14} {total_n:>5} {total_c/total_n*100:.1f}%")
