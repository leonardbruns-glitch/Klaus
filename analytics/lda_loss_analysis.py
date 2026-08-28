"""
LDA loss analysis: feature differentiation, cross-asset correlation, post-entry bid evolution.

Pass 1: Load first-fire windows with full features; apply all live LDA gates.
Pass 2: Stream ticks again to collect bid at +10s/+30s/+60s post-entry.
        Stores only 3 floats per window — no full tick lists in memory.

Output: feature WIN/LOSS comparison, per-asset breakdown, cross-asset correlation,
        post-entry trajectory, categorical breakdowns.  Proposals only.
"""
import json, glob, os
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")
STAKE       = 5.0
BNC_LOAD    = 0.05
TOLS        = 6.0   # seconds tolerance for post-entry bid sampling


def bnc_floor(ask: float) -> float:
    if ask < 0.70: return 0.10
    if ask < 0.90: return 0.05
    return 0.07


# ── 1. Load resolutions ───────────────────────────────────────────────────────
resolutions = {}
for p in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            key = (r["condition_id"], r["window_end_ts"], r.get("window_size_s", 300))
            resolutions[key] = r["moved_up"]
print(f"Resolution windows: {len(resolutions):,}")


# ── 2. Pass 1: first-fire per qualifying window ───────────────────────────────
first_fires = {}  # wkey → feature dict

n_files = 0
for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    n_files += 1
    with open(mt_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("record_type") != "market_timeline":
                continue
            wsz = r.get("window_size_s", 0)
            if wsz not in (300, 900):
                continue

            bnc = r.get("binance_ret_5m_pct")
            if bnc is None or abs(bnc) < BNC_LOAD:
                continue

            odir = r.get("outcome_dir", "")
            bnc_dir = "up" if bnc > 0 else "down"
            if bnc_dir != odir:
                continue

            cid  = r.get("condition_id", "")
            wend = r.get("window_end_ts", 0)
            if not cid or not wend:
                continue
            wkey = (cid, wend, wsz)
            if wkey not in resolutions:
                continue

            ask = r.get("best_ask", 0.0)
            bid = r.get("best_bid", 0.0)
            rem = r.get("seconds_to_resolution", 0.0)
            if ask <= 0 or rem <= 0:
                continue

            # Apply all live LDA gates
            if not (8 <= rem <= 300):
                continue
            if not (0.60 <= ask <= 0.98):
                continue
            if bid < 0.50:
                continue
            if rem > 60 and ask >= 0.90:
                continue
            if rem > 120 and ask >= 0.80:
                continue
            if rem > 180 and ask < 0.70:
                continue
            vol_regime = r.get("vol_regime", "unknown")
            if vol_regime != "normal":
                continue
            bnc_abs = abs(bnc)
            if bnc_abs < bnc_floor(ask):
                continue

            # Hour gates
            hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
            if hour_utc == 1:
                continue
            if rem > 120 and 0.70 <= ask < 0.80 and hour_utc in (12, 16):
                continue

            # Per-asset/wsz gates
            asset = r.get("asset", "").upper()
            if wsz == 900:
                if asset in ("ETH", "SOL"):
                    continue
                if asset == "BTC" and bnc_abs < 0.10:
                    continue
            elif wsz == 300 and asset == "SOL" and bnc_abs >= 0.10:
                continue

            # Keep highest rem = earliest qualifying entry
            existing = first_fires.get(wkey)
            if existing is not None and rem <= existing["rem"]:
                continue

            moved_up = resolutions[wkey]
            correct  = (odir == "up") == moved_up

            first_fires[wkey] = {
                "rem":        rem,
                "ask":        ask,
                "bid_entry":  bid,
                "vol_regime": vol_regime,
                "bnc_abs":    bnc_abs,
                "bnc_1m":     r.get("binance_ret_1m_pct"),
                "bnc_30s":    r.get("binance_ret_30s_pct"),
                "bnc_60s":    r.get("binance_ret_60s_pct"),
                "bnc_vel_5s": r.get("binance_vel_5s_pct"),
                "bnc_60m":    r.get("binance_ret_60m_pct"),
                "bnc_15m":    r.get("binance_ret_15m_pct"),
                "ob_imb":     r.get("ob_imb_top3"),
                "ob_depth":   r.get("ob_book_depth_size"),
                "spread_bps": r.get("spread_bps"),
                "arb_sum":    r.get("arb_sum_yes_no"),
                "vpin":       r.get("vpin_score"),
                "tok_snap30": r.get("tok_snap_30s"),
                "tok_snap60": r.get("tok_snap_60s"),
                "tok_delta5": r.get("tok_delta_5s"),
                "tok_decel":  r.get("tok_decel_ratio"),
                "ask_stale":  r.get("ask_stale_s"),
                "trend_reg":  r.get("trend_regime"),
                "liq_reg":    r.get("liquidity_regime"),
                "session":    r.get("session_bucket"),
                "correct":    correct,
                "wend":       wend,
                "wsz":        wsz,
                "cid":        cid,
                "asset":      asset,
                "hour":       hour_utc,
                # post-entry slots (filled Pass 2)
                "bid_t10":    None,
                "bid_t30":    None,
                "bid_t60":    None,
            }

print(f"Shadow files: {n_files}  |  Qualifying first-fire windows: {len(first_fires):,}")


# ── 3. Pass 2: collect post-entry bid at +10s/+30s/+60s (streaming) ───────────
# For each tick that belongs to a qualifying window and occurs after first-fire,
# compute elapsed = ff_rem - current_rem and sample into slots.
# Only the first hit per slot is stored (no lists).

for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    with open(mt_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("record_type") != "market_timeline":
                continue
            wsz  = r.get("window_size_s", 0)
            cid  = r.get("condition_id", "")
            wend = r.get("window_end_ts", 0)
            if not cid or not wend:
                continue
            wkey = (cid, wend, wsz)
            ff = first_fires.get(wkey)
            if ff is None:
                continue

            rem = r.get("seconds_to_resolution", 0.0)
            bid = r.get("best_bid", 0.0)
            if bid <= 0 or rem <= 0:
                continue

            elapsed = ff["rem"] - rem  # seconds since first-fire entry
            if elapsed <= 0:
                continue  # before or at entry

            for slot, target in [("bid_t10", 10.0), ("bid_t30", 30.0), ("bid_t60", 60.0)]:
                if ff[slot] is None and abs(elapsed - target) <= TOLS:
                    ff[slot] = bid

print("Post-entry bid evolution pass complete.")


# ── 4. Analysis ───────────────────────────────────────────────────────────────
all_rows = list(first_fires.values())
wins     = [v for v in all_rows if v["correct"]]
losses   = [v for v in all_rows if not v["correct"]]

W = 105
print()
print(f"Total qualifying windows: {len(all_rows):,} | WIN: {len(wins)} ({len(wins)/len(all_rows):.1%}) | LOSS: {len(losses)}")


def safe_stats(lst, key):
    vals = [x[key] for x in lst if x.get(key) is not None]
    if not vals:
        return None, None, 0
    return float(np.mean(vals)), float(np.median(vals)), len(vals)


# ── 4a. Feature comparison WIN vs LOSS ────────────────────────────────────────
print()
print("=" * W)
print("FEATURE COMPARISON: WIN vs LOSS (first-fire qualifying windows, all assets)")
print("=" * W)
print(f"  {'Feature':<28} | {'WIN mean / med':>16} (n) | {'LOSS mean / med':>16} (n) | {'Δ mean':>8} |")
print("  " + "-"*100)

FEAT_LABELS = [
    ("ask",        "Ask at entry"),
    ("rem",        "Rem (s) at entry"),
    ("bid_entry",  "Bid at entry"),
    ("bnc_abs",    "BNC 5m abs %"),
    ("bnc_1m",     "BNC 1m %"),
    ("bnc_30s",    "BNC 30s %"),
    ("bnc_60s",    "BNC 60s %"),
    ("bnc_vel_5s", "BNC velocity 5s"),
    ("bnc_60m",    "BNC 60m %"),
    ("bnc_15m",    "BNC 15m %"),
    ("ob_imb",     "OB imb top3"),
    ("ob_depth",   "OB depth"),
    ("spread_bps", "Spread (bps)"),
    ("arb_sum",    "Arb sum yes+no"),
    ("vpin",       "VPIN"),
    ("tok_snap30", "Tok snap 30s"),
    ("tok_snap60", "Tok snap 60s"),
    ("tok_delta5", "Tok delta 5s"),
    ("tok_decel",  "Tok decel ratio"),
    ("ask_stale",  "Ask stale (s)"),
    ("bid_t10",    "Bid at +10s"),
    ("bid_t30",    "Bid at +30s"),
    ("bid_t60",    "Bid at +60s"),
]

for key, label in FEAT_LABELS:
    w_mean, w_med, w_n = safe_stats(wins, key)
    l_mean, l_med, l_n = safe_stats(losses, key)
    if w_n == 0 and l_n == 0:
        continue
    if w_mean is not None and l_mean is not None and w_mean != 0:
        delta_pct = (l_mean - w_mean) / abs(w_mean) * 100
        flag = " ⚠" if abs(delta_pct) > 20 else ""
    else:
        delta_pct = float("nan")
        flag = ""
    w_str = f"{w_mean:+.4f}/{w_med:+.4f}" if w_mean is not None else "        n/a"
    l_str = f"{l_mean:+.4f}/{l_med:+.4f}" if l_mean is not None else "        n/a"
    d_str = f"{delta_pct:+.1f}%" if not np.isnan(delta_pct) else "    n/a"
    print(f"  {label:<28} | {w_str:>16} ({w_n:4d}) | {l_str:>16} ({l_n:4d}) | {d_str:>8}{flag}")


# ── 4b. WR by ask zone and rem bucket ─────────────────────────────────────────
print()
print("=" * W)
print("WIN RATE BY ASK ZONE × REM BUCKET")
print("=" * W)
ask_zones = [(0.60,0.70),(0.70,0.80),(0.80,0.90),(0.90,0.98)]
rem_zones = [(8,60,"[8,60s)"), (60,120,"[60,120s)"), (120,300,"[120,300s)")]

hdr = f"  {'ask zone':<14}"
for _,_,rl in rem_zones:
    hdr += f"  {rl:^20}"
print(hdr)
print("  " + "-"*80)
for a_lo, a_hi in ask_zones:
    row = f"  [{a_lo:.2f},{a_hi:.2f}):    "
    for r_lo, r_hi, _ in rem_zones:
        sub = [v for v in all_rows if a_lo <= v["ask"] < a_hi and r_lo <= v["rem"] < r_hi]
        if len(sub) < 5:
            row += f"  {'n<5':^20}"
        else:
            wr = sum(v["correct"] for v in sub) / len(sub)
            row += f"  {wr:.0%} n={len(sub)} L={sum(1 for v in sub if not v['correct']):<4}"
    print(row)


# ── 4c. Per-asset breakdown ───────────────────────────────────────────────────
print()
print("=" * W)
print("PER-ASSET BREAKDOWN")
print("=" * W)

assets = sorted(set(v["asset"] for v in all_rows))
for asset in assets:
    sub = [v for v in all_rows if v["asset"] == asset]
    if len(sub) < 5:
        continue
    w_sub = [v for v in sub if v["correct"]]
    l_sub = [v for v in sub if not v["correct"]]
    wr = len(w_sub) / len(sub)
    print(f"\n  {asset}: n={len(sub):4d}  WR={wr:.1%}  wins={len(w_sub)}  losses={len(l_sub)}")

    probe_feats = [
        ("ask",       "ask"),
        ("rem",       "rem_s"),
        ("bnc_abs",   "bnc_abs"),
        ("bnc_1m",    "bnc_1m"),
        ("ob_imb",    "ob_imb"),
        ("spread_bps","spread_bps"),
        ("arb_sum",   "arb_sum"),
        ("bid_t10",   "bid@+10s"),
        ("bid_t30",   "bid@+30s"),
    ]
    print(f"    {'feat':<12} | {'WIN mean':>10} (n) | {'LOSS mean':>10} (n) | {'Δ':>8}")
    print(f"    " + "-"*55)
    for key, lbl in probe_feats:
        w_m, _, w_n = safe_stats(w_sub, key)
        l_m, _, l_n = safe_stats(l_sub, key)
        if w_n == 0 and l_n == 0:
            continue
        if w_m is not None and l_m is not None and w_m != 0:
            delta = (l_m - w_m) / abs(w_m) * 100
            flag = " ⚠" if abs(delta) > 20 else ""
        else:
            delta = float("nan")
            flag = ""
        w_s = f"{w_m:+.4f}" if w_m is not None else "    n/a"
        l_s = f"{l_m:+.4f}" if l_m is not None else "    n/a"
        d_s = f"{delta:+.1f}%{flag}" if not np.isnan(delta) else "    n/a"
        print(f"    {lbl:<12} | {w_s:>10} ({w_n:3d}) | {l_s:>10} ({l_n:3d}) | {d_s}")

    # WR by rem bucket for this asset
    print(f"    rem buckets:")
    for r_lo, r_hi, rl in rem_zones:
        bsub = [v for v in sub if r_lo <= v["rem"] < r_hi]
        if len(bsub) < 3:
            continue
        bwr = sum(v["correct"] for v in bsub) / len(bsub)
        print(f"      {rl}: n={len(bsub):3d}  WR={bwr:.0%}  losses={sum(1 for v in bsub if not v['correct'])}")

    # WR by ask zone for this asset
    print(f"    ask zones:")
    for a_lo, a_hi in ask_zones:
        bsub = [v for v in sub if a_lo <= v["ask"] < a_hi]
        if len(bsub) < 3:
            continue
        bwr = sum(v["correct"] for v in bsub) / len(bsub)
        print(f"      [{a_lo:.2f},{a_hi:.2f}): n={len(bsub):3d}  WR={bwr:.0%}  losses={sum(1 for v in bsub if not v['correct'])}")


# ── 4d. Cross-asset correlation: do losses cluster at same wend? ───────────────
print()
print("=" * W)
print("CROSS-ASSET LOSS CORRELATION")
print("=" * W)

by_wend = defaultdict(lambda: {"wins": [], "losses": []})
for v in all_rows:
    bucket = v["wend"]
    if v["correct"]:
        by_wend[bucket]["wins"].append(v["asset"])
    else:
        by_wend[bucket]["losses"].append(v["asset"])

n0 = sum(1 for d in by_wend.values() if len(d["losses"]) == 0)
n1 = sum(1 for d in by_wend.values() if len(d["losses"]) == 1)
n2 = sum(1 for d in by_wend.values() if len(d["losses"]) >= 2)
total_wends = len(by_wend)

print(f"  Unique wend timestamps with ≥1 qualifying window: {total_wends}")
print(f"  0 losses at wend:  {n0:4d} ({n0/total_wends:.1%})")
print(f"  1 loss at wend:    {n1:4d} ({n1/total_wends:.1%})")
print(f"  ≥2 losses at wend: {n2:4d} ({n2/total_wends:.1%})")

# Expected multi-loss rate if independent (binomial)
avg_n_per_wend = len(all_rows) / total_wends if total_wends else 1
uncond_loss_rate = len(losses) / len(all_rows) if all_rows else 0
expected_multi = 0
for d in by_wend.values():
    n_this = len(d["wins"]) + len(d["losses"])
    if n_this >= 2:
        p_all_win = (1 - uncond_loss_rate) ** n_this
        expected_multi += 1 - p_all_win - n_this * uncond_loss_rate * (1 - uncond_loss_rate) ** (n_this - 1)
print(f"  Expected multi-loss wends (if independent): {expected_multi:.1f}")
print(f"  Observed:                                   {n2}")

# Conditional WR when companion asset also lost
companion_outcomes = []
for wend_key, d in by_wend.items():
    if len(d["losses"]) >= 1:
        all_at_wend = [v for v in all_rows if v["wend"] == wend_key]
        for v in all_at_wend:
            other_losses = [a for a in d["losses"] if a != v["asset"]]
            if other_losses:
                companion_outcomes.append(v["correct"])

if companion_outcomes:
    cond_wr = sum(companion_outcomes) / len(companion_outcomes)
    print(f"\n  Conditional WR when companion asset loses same wend: {cond_wr:.1%} (n={len(companion_outcomes)})")
    print(f"  Unconditional WR:                                     {uncond_loss_rate:.1%} (inverted loss rate, same)")

# Show multi-loss examples
print(f"\n  Multi-asset loss examples (first 8):")
shown = 0
for wend_key, d in sorted(by_wend.items()):
    if len(d["losses"]) >= 2:
        dt_str = datetime.fromtimestamp(wend_key, tz=timezone.utc).strftime("%m-%d %H:%M")
        print(f"    {dt_str} UTC  losses={d['losses']}  wins={d['wins']}")
        shown += 1
        if shown >= 8:
            break


# ── 4e. Post-entry trajectory WIN vs LOSS ─────────────────────────────────────
print()
print("=" * W)
print("POST-ENTRY BID TRAJECTORY (change relative to entry ask)")
print("=" * W)
print(f"  {'Offset':<8} | {'WIN bid':>9} | {'WIN Δ%':>8} (n) | {'LOSS bid':>9} | {'LOSS Δ%':>8} (n)")
print("  " + "-"*60)

for slot, label in [("bid_t10", "+10s"), ("bid_t30", "+30s"), ("bid_t60", "+60s")]:
    w_bids = [v[slot] for v in wins if v.get(slot) is not None]
    l_bids = [v[slot] for v in losses if v.get(slot) is not None]
    w_chgs = [(v[slot] - v["ask"]) / v["ask"] * 100 for v in wins if v.get(slot) is not None and v["ask"] > 0]
    l_chgs = [(v[slot] - v["ask"]) / v["ask"] * 100 for v in losses if v.get(slot) is not None and v["ask"] > 0]

    w_bid_m = np.mean(w_bids) if w_bids else None
    l_bid_m = np.mean(l_bids) if l_bids else None
    w_chg_m = np.mean(w_chgs) if w_chgs else None
    l_chg_m = np.mean(l_chgs) if l_chgs else None

    w_bid_s = f"{w_bid_m:.4f}" if w_bid_m else "    n/a"
    l_bid_s = f"{l_bid_m:.4f}" if l_bid_m else "    n/a"
    w_chg_s = f"{w_chg_m:+.2f}%" if w_chg_m is not None else "    n/a"
    l_chg_s = f"{l_chg_m:+.2f}%" if l_chg_m is not None else "    n/a"

    print(f"  {label:<8} | {w_bid_s:>9} | {w_chg_s:>8} ({len(w_chgs):3d}) | {l_bid_s:>9} | {l_chg_s:>8} ({len(l_chgs):3d})")

# Per-asset post-entry trajectory
print()
print("  Post-entry by asset:")
for asset in assets:
    w_sub = [v for v in wins if v["asset"] == asset]
    l_sub = [v for v in losses if v["asset"] == asset]
    if not l_sub:
        continue
    row = f"    {asset}  losses={len(l_sub)}"
    for slot, label in [("bid_t10","+10s"),("bid_t30","+30s")]:
        w_chgs = [(v[slot] - v["ask"]) / v["ask"] * 100 for v in w_sub if v.get(slot) and v["ask"] > 0]
        l_chgs = [(v[slot] - v["ask"]) / v["ask"] * 100 for v in l_sub if v.get(slot) and v["ask"] > 0]
        w_s = f"{np.mean(w_chgs):+.2f}%" if w_chgs else "n/a"
        l_s = f"{np.mean(l_chgs):+.2f}%" if l_chgs else "n/a"
        row += f"  {label} W={w_s} L={l_s}"
    print(row)


# ── 4f. Categorical breakdowns ────────────────────────────────────────────────
print()
print("=" * W)
print("CATEGORICAL BREAKDOWNS")
print("=" * W)
for cat_key, cat_label in [("trend_reg","trend_regime"), ("liq_reg","liquidity_regime"), ("session","session_bucket")]:
    cats = sorted(set(v[cat_key] for v in all_rows if v.get(cat_key) is not None))
    if not cats:
        continue
    print(f"\n  {cat_label}:")
    for cat in cats:
        sub = [v for v in all_rows if v.get(cat_key) == cat]
        if len(sub) < 5:
            continue
        wr = sum(v["correct"] for v in sub) / len(sub)
        print(f"    {str(cat):<22}: n={len(sub):4d}  WR={wr:.1%}  losses={sum(1 for v in sub if not v['correct'])}")

# Hour breakdown
print(f"\n  hour_utc (WR <70% flagged):")
for h in range(24):
    sub = [v for v in all_rows if v["hour"] == h]
    if len(sub) < 10:
        continue
    wr = sum(v["correct"] for v in sub) / len(sub)
    flag = " ⚠" if wr < 0.70 else ""
    print(f"    H{h:02d}: n={len(sub):4d}  WR={wr:.1%}  losses={sum(1 for v in sub if not v['correct'])}{flag}")


# ── 4g. BNC velocity: is loss driven by fading signal? ────────────────────────
print()
print("=" * W)
print("BNC SIGNAL DECAY ANALYSIS (longer-horizon vs 5m)")
print("= (positive = longer horizon agrees with 5m direction)")
print("=" * W)
print("  Rationale: if 5m is up but 1m/30s is fading → momentum exhausted → loss?")
print(f"  {'Feature':<20} | {'WIN mean':>10} | {'LOSS mean':>10} | {'Δ':>8}")
print("  " + "-"*55)
for key, lbl in [("bnc_1m","bnc_1m %"),("bnc_30s","bnc_30s %"),("bnc_vel_5s","bnc_vel_5s"),("bnc_15m","bnc_15m %")]:
    w_m, _, w_n = safe_stats(wins, key)
    l_m, _, l_n = safe_stats(losses, key)
    if w_n == 0: continue
    delta = (l_m - w_m) / abs(w_m) * 100 if (w_m and l_m and w_m != 0) else float("nan")
    flag = " ⚠" if not np.isnan(delta) and abs(delta) > 20 else ""
    w_s = f"{w_m:+.5f}" if w_m is not None else "    n/a"
    l_s = f"{l_m:+.5f}" if l_m is not None else "    n/a"
    d_s = f"{delta:+.1f}%{flag}" if not np.isnan(delta) else "    n/a"
    print(f"  {lbl:<20} | {w_s:>10} ({w_n}) | {l_s:>10} ({l_n}) | {d_s}")


# ── 4h. BNC LOW tier hour breakdown ──────────────────────────────────────────
# LOW tier = BNC [0.05, 0.07%). Now at 1.5% bankroll stake (near break-even avg).
# Check if specific hours within LOW tier are systematically negative.
print()
print("=" * W)
print("BNC LOW TIER [0.05,0.07%) — WR BY HOUR (gate candidates if WR<70% n≥10)")
print("=" * W)
low_tier = [v for v in all_rows if 0.05 <= v["bnc_abs"] < 0.07]
print(f"  LOW tier total: n={len(low_tier)}  WR={sum(1 for v in low_tier if v['correct'])/len(low_tier):.1%}" if low_tier else "  LOW tier: n=0")
low_by_hour: dict = {}
for v in low_tier:
    h = v["hour"]
    low_by_hour.setdefault(h, {"n": 0, "w": 0})
    low_by_hour[h]["n"] += 1
    if v["correct"]:
        low_by_hour[h]["w"] += 1
for h in sorted(low_by_hour):
    d = low_by_hour[h]
    wr = d["w"] / d["n"] if d["n"] else 0.0
    flag = " ⚠" if wr < 0.70 and d["n"] >= 10 else ""
    print(f"  H{h:02d}: n={d['n']:3d} WR={wr:.1%}{flag}")

# ── 4i. 15m/5m alignment analysis ────────────────────────────────────────────
# binance_ret_15m_pct added 2026-05-15; will be None for older shadow data.
print()
print("=" * W)
print("BNC 15m/5m ALIGNMENT (hypothesis: divergent = counter-trend noise = lower WR)")
print("= Field added 2026-05-15; expect n=0 on older shadow. Run again after 7+ days.")
print("=" * W)
has_15m = [v for v in all_rows if v.get("bnc_15m") is not None and v["bnc_15m"] != 0.0]
print(f"  Windows with bnc_15m populated: {len(has_15m)} / {len(all_rows)}")
if has_15m:
    aligned   = [v for v in has_15m if (v["bnc_15m"] > 0) == (v.get("bnc_abs", 0) > 0 and True)]
    # bnc_abs is absolute; reconstruct direction from odir field
    def _bnc_dir_up(v):
        return v.get("odir", "up") == "up"  # first_fire only has bnc_dir==odir entries
    aligned   = [v for v in has_15m if (v["bnc_15m"] > 0) == _bnc_dir_up(v)]
    divergent = [v for v in has_15m if v not in aligned]
    for label, sub in [("15m ALIGNED", aligned), ("15m DIVERGENT", divergent)]:
        if not sub:
            print(f"  {label}: n=0")
            continue
        wr = sum(1 for v in sub if v["correct"]) / len(sub)
        flag = " ⚠" if wr < 0.80 and len(sub) >= 20 else (" (n<20)" if len(sub) < 20 else "")
        print(f"  {label}: n={len(sub):4d} WR={wr:.1%}{flag}")

print()
print("=" * W)
print("SUMMARY — PROPOSALS (shadow evidence, no implementation)")
print("=" * W)
print("""
  Review the ⚠ flags above for gate candidates.  Guidelines:
  - Any feature with |Δ| > 20% and n_loss ≥ 20 → candidate entry filter
  - Post-entry: if LOSS mean bid Δ at +10s << WIN mean → T+10s early-exit candidate
  - Cross-asset: if conditional WR (companion-loss) << unconditional → companion gate candidate
  - Categorical: categories with WR < 70% and n ≥ 20 → block candidate
  - BNC decay: if 1m/30s fade significantly predicts loss → add bnc_1m/bnc_30s floor

  Deploy NONE of the above until:
  1. n_loss ≥ 50 in shadow (confirmed, not just flagged)
  2. Per-asset n ≥ 20 for per-asset rules
  3. No cherry-picking: rule must survive in train/test split
""")
