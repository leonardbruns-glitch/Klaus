"""
Reconstruct binance_ret_15m_pct for 15m windows using raw JSONL spot data.
Then run ask/rem/BNC-15m grid analysis with proper first-fire dedup.

Signal: (spot_now - spot_900s_ago) / spot_900s_ago * 100
Win: moved_up == True for outcome_dir=='up' token, moved_up == False for 'down' token
"""
import json, bisect, math
from pathlib import Path
from collections import defaultdict
import duckdb

SHADOW_ROOT = Path("/root/Klaus/logs/shadow/hot")
PARQUET     = "/root/Klaus/analytics/discover/replay_enriched.parquet"
BNC_FLOOR   = 0.05   # same as 5m LDA

# ── 1. Build spot lookup per asset ───────────────────────────────────────────
print("Loading spot prices from JSONL...")
spot_ts   = defaultdict(list)  # asset → [ts_s, ...]
spot_val  = defaultdict(list)  # asset → [price, ...]

for f in sorted(SHADOW_ROOT.glob("*/market_timeline.jsonl")):
    with open(f) as fh:
        for line in fh:
            try:
                r = json.loads(line)
                if r.get("record_type") != "market_timeline":
                    continue
                asset = r.get("asset", "").upper()
                ts    = r.get("ts_s", 0)
                spot  = r.get("binance_spot", 0.0)
                if asset in ("BTC", "ETH", "SOL") and ts and spot > 0:
                    spot_ts[asset].append(ts)
                    spot_val[asset].append(spot)
            except:
                pass

# Sort by ts
for asset in spot_ts:
    pairs = sorted(zip(spot_ts[asset], spot_val[asset]))
    spot_ts[asset]  = [p[0] for p in pairs]
    spot_val[asset] = [p[1] for p in pairs]
    print(f"  {asset}: {len(spot_ts[asset]):,} points, {spot_ts[asset][0]}–{spot_ts[asset][-1]}")

def lookup_spot(asset, ts, tol=15):
    """Binary search: nearest spot price within ±tol seconds."""
    ts_list = spot_ts[asset]
    if not ts_list:
        return None
    idx = bisect.bisect_left(ts_list, ts)
    best, best_dist = None, tol + 1
    for i in [idx - 1, idx]:
        if 0 <= i < len(ts_list):
            d = abs(ts_list[i] - ts)
            if d < best_dist:
                best_dist = d
                best = spot_val[asset][i]
    return best if best_dist <= tol else None

# ── 2. Load 15m window data from parquet ─────────────────────────────────────
print("\nLoading 15m parquet data...")
con = duckdb.connect()
rows_15m = con.execute(f"""
    SELECT condition_id, window_end_ts, token_id, asset, outcome_dir,
           ts_s, seconds_to_resolution, best_ask, best_bid,
           binance_spot, binance_ret_5m_pct, vol_regime,
           moved_up, pnl_PT95_T1, pnl_HOLD, hour_utc, ob_imb_top3
    FROM read_parquet('{PARQUET}')
    WHERE window_size_s = 900
      AND vol_regime = 'normal'
      AND best_ask BETWEEN 0.50 AND 0.99
      AND seconds_to_resolution BETWEEN 8 AND 300
""").fetchall()
cols = ["cid","wend","token_id","asset","outcome_dir","ts_s","rem","ask","bid",
        "spot_now","bnc5","vol_regime","moved_up","pnl_pt95","pnl_hold","hour","imb"]
print(f"  {len(rows_15m):,} rows loaded")

# ── 3. Reconstruct bnc_15m, apply signal alignment, first-fire dedup ─────────
print("\nReconstructing bnc_15m...")
results = []
matched = 0
total   = 0
fired_windows = set()  # (cid, wend, outcome_dir) for dedup

# Process ALL ticks, collect, then dedup
all_ticks = []
for row in rows_15m:
    r = dict(zip(cols, row))
    total += 1
    asset = r["asset"].upper()
    ts    = r["ts_s"]
    spot_now = r["spot_now"]
    
    spot_ago = lookup_spot(asset, ts - 900, tol=20)
    if spot_ago is None or spot_ago <= 0:
        continue
    
    bnc15 = (spot_now - spot_ago) / spot_ago * 100.0
    matched += 1
    
    bnc15_dir = "up" if bnc15 > 0 else "down"
    r["bnc15"] = bnc15
    r["bnc15_dir"] = bnc15_dir
    all_ticks.append(r)

print(f"  Matched: {matched:,}/{total:,} ({matched/total*100:.1f}%)")

# First-fire dedup: earliest (highest rem) tick per (cid, wend, outcome_dir, rem_bucket)
# where signal is aligned
def rem_bucket(rem):
    if rem < 60:   return "B0"
    if rem < 120:  return "B1"
    if rem < 180:  return "B2"
    return "B3"

# Group by (cid, wend, outcome_dir, rem_bkt) → pick highest rem (first fire)
from collections import defaultdict
bucket_map = defaultdict(list)
for r in all_ticks:
    if r["bnc15_dir"] != r["outcome_dir"]:
        continue  # only signal-aligned
    if abs(r["bnc15"]) < BNC_FLOOR:
        continue
    bkt = rem_bucket(r["rem"])
    key = (r["cid"], r["wend"], r["outcome_dir"], bkt)
    bucket_map[key].append(r)

first_fires = []
for key, ticks in bucket_map.items():
    # Take the one with highest rem (earliest entry opportunity)
    best = max(ticks, key=lambda x: x["rem"])
    first_fires.append(best)

print(f"\nFirst-fire signal-aligned entries: {len(first_fires):,}")

# ── 4. Grid analysis ──────────────────────────────────────────────────────────
def ask_band(ask):
    if ask < 0.60: return "X:<0.60"
    if ask < 0.70: return "A:[0.60,0.70)"
    if ask < 0.80: return "B:[0.70,0.80)"
    if ask < 0.90: return "C:[0.80,0.90)"
    return "D:[0.90,0.98]"

# Aggregate by ask_band × rem_bucket
from collections import defaultdict
grid = defaultdict(lambda: {"n":0,"wins":0,"ev_pt95":0,"ev_hold":0,"bnc_sum":0})
for r in first_fires:
    ab = ask_band(r["ask"])
    bkt = rem_bucket(r["rem"])
    key = (ab, bkt)
    g = grid[key]
    g["n"]      += 1
    g["wins"]   += 1 if r["moved_up"] else 0
    g["ev_pt95"]+= r["pnl_pt95"]
    g["ev_hold"]+= r["pnl_hold"]
    g["bnc_sum"]+= abs(r["bnc15"])

print("\n=== 15m LDA with RECONSTRUCTED bnc_15m signal ===")
print("First-fire per bucket, vol=normal, bnc15>=0.05%, ask 0.50-0.99")
print(f"\n{'AskBand':<15} {'Bkt':<5} {'n':<6} {'WR':<8} {'EV_PT95':<10} {'EV_HOLD':<10} {'AvgBNC'}")
print("-" * 65)

for (ab, bkt), g in sorted(grid.items()):
    if g["n"] < 10:
        continue
    wr = g["wins"] / g["n"]
    ev95 = g["ev_pt95"] / g["n"]
    evh  = g["ev_hold"] / g["n"]
    bnc  = g["bnc_sum"] / g["n"]
    flag = " ***" if wr > 0.55 and ev95 > 0 else ""
    print(f"{ab:<15} {bkt:<5} {g['n']:<6} {wr:<8.1%} {ev95:<10.4f} {evh:<10.4f} {bnc:.3f}%{flag}")

# ── 5. BNC tier analysis for the best cells ───────────────────────────────────
print("\n=== BNC tier breakdown (ask 0.80-0.99, all rem buckets) ===")
tier_grid = defaultdict(lambda: {"n":0,"wins":0,"ev_pt95":0})
for r in first_fires:
    ab = ask_band(r["ask"])
    if ab not in ("C:[0.80,0.90)", "D:[0.90,0.98]"):
        continue
    bnc = abs(r["bnc15"])
    if bnc < 0.05: tier = "<0.05"
    elif bnc < 0.07: tier = "[0.05,0.07)"
    elif bnc < 0.10: tier = "[0.07,0.10)"
    elif bnc < 0.15: tier = "[0.10,0.15)"
    else: tier = ">=0.15"
    g = tier_grid[tier]
    g["n"]      += 1
    g["wins"]   += 1 if r["moved_up"] else 0
    g["ev_pt95"]+= r["pnl_pt95"]

print(f"{'BNC15 tier':<15} {'n':<6} {'WR':<8} {'EV_PT95'}")
print("-" * 40)
for tier in ["[0.05,0.07)", "[0.07,0.10)", "[0.10,0.15)", ">=0.15"]:
    g = tier_grid.get(tier, {"n":0,"wins":0,"ev_pt95":0})
    if g["n"] < 5: continue
    wr = g["wins"]/g["n"]
    ev = g["ev_pt95"]/g["n"]
    print(f"{tier:<15} {g['n']:<6} {wr:<8.1%} {ev:.4f}")

# ── 6. Compare: bnc_15m vs bnc_5m signal alignment on same windows ───────────
print("\n=== Signal comparison: bnc_5m vs bnc_15m on 15m windows ===")
agree = disagree = 0
for r in all_ticks:
    bnc5_dir = "up" if r["bnc5"] > 0 else "down"
    if bnc5_dir == r["bnc15_dir"]:
        agree += 1
    else:
        disagree += 1
total_comp = agree + disagree
print(f"  5m and 15m BNC directions agree: {agree:,}/{total_comp:,} = {agree/total_comp:.1%}")

# When they disagree: who wins?
n_agree_win = n_agree_loss = 0
n_dis_win = n_dis_loss = 0
for r in all_ticks:
    bnc5_dir = "up" if r["bnc5"] > 0 else "down"
    is_win = r["moved_up"]  # for 'up' direction token
    if r["outcome_dir"] == "down":
        is_win = not r["moved_up"]
    aligned5  = bnc5_dir == r["outcome_dir"]
    aligned15 = r["bnc15_dir"] == r["outcome_dir"]
    if aligned5 and aligned15:
        if is_win: n_agree_win += 1
        else: n_agree_loss += 1
    elif aligned15 and not aligned5:
        if is_win: n_dis_win += 1
        else: n_dis_loss += 1

n_agree_all = n_agree_win + n_agree_loss
n_dis_all = n_dis_win + n_dis_loss
if n_agree_all > 0:
    print(f"  Both signals aligned → WR {n_agree_win/n_agree_all:.1%} (n={n_agree_all:,})")
if n_dis_all > 0:
    print(f"  Only bnc_15m aligned (bnc_5m opposite) → WR {n_dis_win/n_dis_all:.1%} (n={n_dis_all:,})")
