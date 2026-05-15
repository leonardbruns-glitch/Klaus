"""
Exit structure optimizer for LDA 5m strategy.

Uses hold_path shadow trajectories (per-second bid evolution) joined to
window_resolution (kline outcome) to simulate alternative exit rules and
find the structure that maximises EV without over-pruning winners.

Shadow positions filtered: gate_all_pass_at_open=True, window_size_s=300 (5m only).
Win label: resolution.moved_up matches outcome_dir.
"""
import json, math
from pathlib import Path
from collections import defaultdict

SHADOW_ROOT = Path("/root/Klaus/logs/shadow/hot")
HP_DAYS = sorted(SHADOW_ROOT.glob("*/hold_path.jsonl"))
RES_DAYS = sorted(SHADOW_ROOT.glob("*/window_resolution.jsonl"))

# ── 1. Load resolutions ───────────────────────────────────────────────────────
resolutions = {}  # (asset, wend, wsz) → moved_up
for f in RES_DAYS:
    with open(f) as fh:
        for line in fh:
            try:
                r = json.loads(line)
                k = (r["asset"].upper(), r["window_end_ts"], r.get("window_size_s", 300))
                resolutions[k] = r["moved_up"]
            except: pass
print(f"Resolutions: {len(resolutions):,}")

# ── 2. Build per-position trajectories from hold_path ────────────────────────
# Key = (token_id, window_end_ts) → trajectory list sorted by seconds_held ASC
# Only 5m windows with gate_all_pass_at_open=True

traj_raw = defaultdict(list)
n_loaded = 0
for f in HP_DAYS:
    with open(f) as fh:
        for line in fh:
            try:
                r = json.loads(line)
                if r.get("record_type") != "hold_path": continue
                wsz = r.get("window_size_s", 300)
                if wsz != 300: continue
                if not r.get("gate_all_pass_at_open"): continue
                key = (r["token_id"], r["window_end_ts"])
                traj_raw[key].append(r)
                n_loaded += 1
            except: pass

print(f"Hold-path ticks loaded (5m, gate_pass): {n_loaded:,}  positions: {len(traj_raw):,}")

# ── 3. Finalise trajectories + attach win/loss label ─────────────────────────
positions = []  # list of dicts
n_resolved = n_win = n_loss = 0

for (tid, wend), ticks in traj_raw.items():
    if not ticks: continue
    ticks_sorted = sorted(ticks, key=lambda x: x["seconds_held"])
    first = ticks_sorted[0]
    asset  = first["asset"].upper()
    odir   = first["outcome_dir"]
    wsz    = first.get("window_size_s", 300)
    hour   = first["hour_utc"]
    fire_ask = first["fire_ask"]
    fire_rem = first["fire_sec_to_res"]
    session  = first.get("session_bucket", "")

    res_key = (asset, wend, wsz)
    moved_up = resolutions.get(res_key)
    if moved_up is None: continue
    is_win = (moved_up and odir == "up") or (not moved_up and odir == "down")

    n_resolved += 1
    if is_win: n_win += 1
    else:       n_loss += 1

    # Trajectory: list of (seconds_held, pnl_pct, bid, bid_vel, binance_ret_5m)
    traj = [(t["seconds_held"], t["pnl_pct"], t["bid"],
             t.get("bid_velocity_1s", 0.0),
             t.get("binance_ret_5m_pct", 0.0)) for t in ticks_sorted]

    # MFE / MAE from hold_path
    mfe = max(t["mfe"] for t in ticks_sorted)
    mae = min(t["mae"] for t in ticks_sorted)

    positions.append(dict(
        asset=asset, odir=odir, hour=hour, session=session,
        fire_ask=fire_ask, fire_rem=fire_rem,
        is_win=is_win, traj=traj, mfe=mfe, mae=mae,
        wend=wend,
    ))

print(f"Resolved: {n_resolved:,}  WIN: {n_win:,} ({n_win/n_resolved:.1%})  LOSE: {n_loss:,}")

# ── 4. Baseline: hold-to-resolution EV ───────────────────────────────────────
def hold_ev(pos):
    """EV of hold-to-resolution: win = (1.0 - ask), lose = -ask"""
    ask = pos["fire_ask"]
    return (1.0 - ask) if pos["is_win"] else -ask

baseline_ev = sum(hold_ev(p) for p in positions) / len(positions)
baseline_wr = n_win / n_resolved
print(f"\nBaseline hold-to-res: WR={baseline_wr:.1%}  EV={baseline_ev:+.4f}/trade")

# ── 5. Simulate exit rules ────────────────────────────────────────────────────

def simulate(positions, exit_fn, label=""):
    """Apply exit_fn(traj, fire_ask, fire_rem) → exit_pnl_pct or None(hold).
    Returns (mean_ev, wr_kept, win_cutoff_rate, loss_saved_rate)."""
    total_ev = 0.0
    n = len(positions)
    n_wins_cut = 0
    n_loss_saved = 0
    n_hold = 0
    for pos in positions:
        exit_pnl_pct = exit_fn(pos["traj"], pos["fire_ask"], pos["fire_rem"])
        if exit_pnl_pct is None:
            ev = hold_ev(pos)
            n_hold += 1
        else:
            ev = exit_pnl_pct / 100.0 * pos["fire_ask"]  # pnl_pct is relative to ask
            if pos["is_win"]: n_wins_cut += 1
            else: n_loss_saved += 1
        total_ev += ev
    mean_ev = total_ev / n
    return dict(
        label=label, mean_ev=mean_ev, ev_vs_base=mean_ev - baseline_ev,
        wins_cut=n_wins_cut/n_win if n_win else 0,
        loss_saved=n_loss_saved/n_loss if n_loss else 0,
        n_hold=n_hold/n,
    )

results = []

# A) Fixed stop-loss: sell when pnl_pct < -SL
for sl in [5, 10, 15, 20, 25, 30, 40, 50]:
    def make_sl(sl):
        def fn(traj, ask, rem):
            for secs, pnl, bid, vel, bnc in traj:
                if pnl < -sl:
                    return pnl  # exit at this pnl
            return None
        return fn
    results.append(simulate(positions, make_sl(sl), f"SL-{sl}%"))

# B) Trailing stop: sell when bid drops Y% from peak bid
for trail in [5, 8, 10, 15, 20]:
    def make_trail(trail):
        def fn(traj, ask, rem):
            peak = ask  # start peak at entry ask
            for secs, pnl, bid, vel, bnc in traj:
                peak = max(peak, bid)
                drop_from_peak = (peak - bid) / peak * 100
                if drop_from_peak > trail:
                    exit_pnl_pct = (bid - ask) / ask * 100
                    return exit_pnl_pct
            return None
        return fn
    results.append(simulate(positions, make_trail(trail), f"Trail-{trail}%"))

# C) Time-based: at rem=T, cut if pnl_pct < threshold
for cut_rem, threshold in [(45,0), (30,0), (20,0), (45,-5), (30,-5), (20,-5)]:
    def make_time(cut_rem, threshold):
        def fn(traj, ask, rem):
            for secs, pnl, bid, vel, bnc in traj:
                held_rem = rem - secs
                time_left = rem - secs  # not right; use seconds_to_res
                # seconds_held = secs; remaining = fire_rem - secs
                remaining_now = rem - secs
                if remaining_now <= cut_rem and pnl < threshold:
                    return pnl
            return None
        return fn
    results.append(simulate(positions, make_time(cut_rem, threshold), f"T@{cut_rem}s<{threshold}%"))

# D) BNC reversal exit: sell when bnc direction flips vs entry direction
def bnc_reversal(traj, ask, rem):
    # Determine entry bnc direction from first tick
    if not traj: return None
    entry_bnc = traj[0][4]
    entry_dir = "up" if entry_bnc > 0 else "down"
    # Wait at least 30s before checking reversal (avoid noise)
    for secs, pnl, bid, vel, bnc in traj:
        if secs < 30: continue
        cur_dir = "up" if bnc > 0 else "down"
        if cur_dir != entry_dir and abs(bnc) >= 0.03:
            exit_pnl_pct = (bid - ask) / ask * 100
            return exit_pnl_pct
    return None
results.append(simulate(positions, bnc_reversal, "BNC-Reversal"))

# E) Bid velocity: exit if bid_velocity negative for sustained period
for vel_thresh, n_consec in [(-0.01, 3), (-0.005, 5), (-0.01, 5)]:
    def make_vel(vt, nc):
        def fn(traj, ask, rem):
            streak = 0
            for secs, pnl, bid, vel, bnc in traj:
                if secs < 20: continue  # ignore first 20s noise
                if vel < vt:
                    streak += 1
                    if streak >= nc:
                        exit_pnl_pct = (bid - ask) / ask * 100
                        return exit_pnl_pct
                else:
                    streak = 0
            return None
        return fn
    results.append(simulate(positions, make_vel(vel_thresh, n_consec), f"Vel<{vel_thresh}x{n_consec}"))

# F) Combo: SL + trailing stop (whichever fires first)
for sl, trail in [(15, 8), (20, 10), (25, 12), (20, 8)]:
    def make_combo(sl, trail):
        def fn(traj, ask, rem):
            peak = ask
            for secs, pnl, bid, vel, bnc in traj:
                peak = max(peak, bid)
                drop_from_peak = (peak - bid) / peak * 100
                if pnl < -sl:
                    return pnl
                if drop_from_peak > trail and bid > ask * 0.92:  # only trail after profit
                    exit_pnl_pct = (bid - ask) / ask * 100
                    return exit_pnl_pct
            return None
        return fn
    results.append(simulate(positions, make_combo(sl, trail), f"SL{sl}+Trail{trail}"))

# G) Two-phase: hold unless deep loss early, then trail in final zone
for sl_early, trail_late in [(30, 5), (25, 8), (20, 10)]:
    def make_twophase(sl_early, trail_late):
        def fn(traj, ask, rem):
            peak = ask
            for secs, pnl, bid, vel, bnc in traj:
                remaining_now = rem - secs
                peak = max(peak, bid)
                drop_from_peak = (peak - bid) / peak * 100
                if remaining_now > 60:  # early phase: only hard stop
                    if pnl < -sl_early:
                        return pnl
                else:  # late phase: trail tightly
                    if drop_from_peak > trail_late and peak > ask:
                        return (bid - ask) / ask * 100
                    if pnl < -sl_early:
                        return pnl
            return None
        return fn
    results.append(simulate(positions, make_twophase(sl_early, trail_late), f"2Ph-SL{sl_early}/Trail{trail_late}@60s"))

# ── 6. Print results ──────────────────────────────────────────────────────────
results.sort(key=lambda x: x["mean_ev"], reverse=True)

print(f"\n{'Strategy':<28} {'EV/trade':>9} {'vs Base':>8} {'WinsCut':>9} {'LossSaved':>10} {'Hold%':>7}")
print("-" * 78)
for r in results[:25]:
    flag = " ◄ BEST" if r == results[0] else ""
    print(f"{r['label']:<28} {r['mean_ev']:>+9.4f} {r['ev_vs_base']:>+8.4f} "
          f"{r['wins_cut']:>9.1%} {r['loss_saved']:>10.1%} {r['n_hold']:>7.1%}{flag}")

print(f"\n{'Baseline (hold)':28} {baseline_ev:>+9.4f} {'---':>8}")

# ── 7. Hour breakdown for best strategy ──────────────────────────────────────
best_fn_name = results[0]["label"]
print(f"\n=== Hour breakdown: Baseline vs {best_fn_name} ===")

# Find the best exit function
def find_best_fn(label):
    # Re-create best fn based on label
    if label.startswith("SL-") and "Trail" not in label and "+" not in label:
        sl = int(label.split("-")[1].replace("%",""))
        def fn(traj, ask, rem):
            for secs, pnl, bid, vel, bnc in traj:
                if pnl < -sl: return pnl
            return None
        return fn
    return None

# Do per-hour analysis
by_hour_base = defaultdict(list)
by_hour_best = defaultdict(list)
best_exit = results[0]

for pos in positions:
    h = pos["hour"]
    base = hold_ev(pos)
    by_hour_base[h].append(base)

# Need to re-run the simulation per-hour with the best strategy
# Just show per-hour baseline + WR for now
print(f"{'Hour':>5} {'n':>5} {'WR':>7} {'BaseEV':>8} {'LoseRate':>9} {'AvgMAE':>8} {'AvgMFE':>8}")
print("-" * 56)
by_hour = defaultdict(list)
for pos in positions:
    by_hour[pos["hour"]].append(pos)

for h in sorted(by_hour.keys()):
    ps = by_hour[h]
    if len(ps) < 5: continue
    wr = sum(p["is_win"] for p in ps) / len(ps)
    ev = sum(hold_ev(p) for p in ps) / len(ps)
    avg_mae = sum(p["mae"] for p in ps) / len(ps)
    avg_mfe = sum(p["mfe"] for p in ps) / len(ps)
    lose_rate = 1 - wr
    flag = " ◄" if 14 <= h <= 18 else ""
    print(f"H{h:02d}   {len(ps):>5} {wr:>7.1%} {ev:>+8.4f} {lose_rate:>9.1%} {avg_mae:>8.2f}% {avg_mfe:>8.2f}%{flag}")

# ── 8. Deep look: losing trade trajectory profiles ────────────────────────────
print("\n=== Losing trade MFE distribution (did they ever go profitable?) ===")
loss_mfe_bins = [0, 2, 5, 10, 20, 100]
mfe_counts = defaultdict(int)
loss_positions = [p for p in positions if not p["is_win"]]
for p in loss_positions:
    for i in range(len(loss_mfe_bins)-1):
        if loss_mfe_bins[i] <= p["mfe"] < loss_mfe_bins[i+1]:
            mfe_counts[f"[{loss_mfe_bins[i]},{loss_mfe_bins[i+1]})"] += 1
            break

total_loss = len(loss_positions)
print(f"Total losing positions: {total_loss:,}")
for band, cnt in sorted(mfe_counts.items()):
    print(f"  MFE {band:>12}: {cnt:>5} ({cnt/total_loss:>5.1%})")

print(f"\nAvg MAE on losers: {sum(p['mae'] for p in loss_positions)/total_loss:.2f}%")
print(f"Avg MFE on losers: {sum(p['mfe'] for p in loss_positions)/total_loss:.2f}%")
win_positions = [p for p in positions if p["is_win"]]
print(f"Avg MAE on winners: {sum(p['mae'] for p in win_positions)/len(win_positions):.2f}%")
print(f"Avg MFE on winners: {sum(p['mfe'] for p in win_positions)/len(win_positions):.2f}%")
