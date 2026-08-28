"""
LDA loser early-cut analysis.

Loads all live LDA trades, labels them using kline-based outcome (same logic
as lda_live_performance.py), then compares post-entry trajectory for winners
vs losers. Proposes early-exit thresholds as shadow-only candidates.

Deploy threshold only when n_losers ≥ 50.
"""
import json
import glob
import math
import statistics
from collections import Counter
from pathlib import Path

TRADES_FILE = Path("logs/trades.jsonl")
SHADOW_ROOT = Path("logs/shadow/hot")
STAKE = 5.0


def load_resolutions():
    res = {}
    for p in sorted(glob.glob(str(SHADOW_ROOT / "*/window_resolution.jsonl"))):
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                key = (r["asset"], r["window_end_ts"], r.get("window_size_s", 300))
                res[key] = r["moved_up"]
    return res


def label_trades(trades, resolutions):
    wins, losses, unknown = [], [], []
    for t in trades:
        ec = t.get("entered_correctly")
        if ec is None:
            wsz  = t.get("window_size_s", 300)
            wend = math.ceil(t["ts_open"] / wsz) * wsz
            asset = t["asset"].upper()
            moved_up = resolutions.get((asset, wend, wsz))
            if moved_up is not None:
                bet_up = t.get("bond_outcome_direction") == "up"
                ec = (bet_up == moved_up)
        if ec is True:
            wins.append(t)
        elif ec is False:
            losses.append(t)
        else:
            unknown.append(t)
    return wins, losses, unknown


def fmt(v, pct=False):
    if v is None:
        return "  n/a"
    return f"{v:+.3f}{'%' if pct else ''}"


def main():
    trades = []
    with open(TRADES_FILE) as f:
        for line in f:
            t = json.loads(line)
            if t.get("bond_entry_class") == "LDA" and t.get("is_live"):
                trades.append(t)

    resolutions = load_resolutions()
    wins, losses, unknown = label_trades(trades, resolutions)

    print(f"LDA live trades: {len(trades)} | Kline WIN: {len(wins)} LOSS: {len(losses)} Unknown: {len(unknown)}")
    print()

    # ── Loser trajectory detail ───────────────────────────────────────────────
    print("=" * 80)
    print("LOSER TRAJECTORIES")
    print("=" * 80)
    if not losses:
        print("  No kline losers resolved yet.")
    for t in losses:
        ep = t.get("entry_price", 0)
        p10 = t.get("price_at_t10s")
        mae10 = t.get("traj_mae_10s")
        mfe10 = t.get("traj_mfe_10s")
        mae30 = t.get("traj_mae_30s")
        mfe30 = t.get("traj_mfe_30s")
        drop10_pct = (p10 - ep) / ep * 100 if p10 and ep else None
        print(
            f"  {t['trade_id'][:14]} {t['asset']} "
            f"ep={ep:.4f} rem={t.get('term_remaining_s', 0):.0f}s "
            f"exit={t.get('exit_reason', '?'):<22} pnl={t['net_pnl']:+.2f}"
        )
        print(f"    T+10s bid_chg={fmt(drop10_pct, pct=True):>8}  mae_10s={fmt(mae10, pct=True):>8}  mfe_10s={fmt(mfe10, pct=True):>8}")
        print(f"    T+30s          mae_30s={fmt(mae30, pct=True):>8}  mfe_30s={fmt(mfe30, pct=True):>8}  max_adv={fmt(t.get('max_adverse_pct'), pct=True):>8}")

    print()

    # ── Winner vs loser comparison ────────────────────────────────────────────
    def safe_vals(lst, key):
        return [x[key] for x in lst if x.get(key) is not None]

    print("=" * 80)
    print("WINNER vs LOSER — trajectory features")
    print("=" * 80)
    metrics = [
        ("traj_mae_10s",    "MAE at T+10s (%)"),
        ("traj_mfe_10s",    "MFE at T+10s (%)"),
        ("traj_mae_30s",    "MAE at T+30s (%)"),
        ("traj_mfe_30s",    "MFE at T+30s (%)"),
        ("max_adverse_pct", "Max adverse total (%)"),
        ("max_favourable_pct", "Max favourable total (%)"),
        ("hold_seconds",    "Hold time (s)"),
    ]
    for key, label in metrics:
        w = safe_vals(wins, key)
        l = safe_vals(losses, key)
        w_mean = statistics.mean(w) if w else None
        l_mean = statistics.mean(l) if l else None
        w_p90  = sorted(w)[int(0.9 * len(w))] if len(w) > 2 else None
        print(
            f"  {label:<30} | WIN n={len(w):2d} mean={fmt(w_mean):>8} p90={fmt(w_p90):>8}"
            f" | LOSE n={len(l):2d} mean={fmt(l_mean):>8}"
        )

    print()

    # ── Early-cut threshold scan ──────────────────────────────────────────────
    print("=" * 80)
    print("EARLY-CUT CANDIDATES (shadow candidates only — deploy at n_losers≥50)")
    print("=" * 80)

    # MAE is positive (magnitude of drop below entry). Cut if MAE exceeds threshold.
    # MFE is positive (magnitude of rise above entry). Cut if MFE stays below threshold.
    for thr_key, thr_label, direction in [
        ("traj_mae_10s", "MAE_10s > X%", "gt"),
        ("traj_mae_30s", "MAE_30s > X%", "gt"),
        ("traj_mfe_10s", "MFE_10s < X%", "lt"),
    ]:
        print(f"\n  {thr_label} (cut if {thr_label}):")
        thresholds_gt = [2.0, 4.0, 6.0, 8.0, 12.0] if direction == "gt" else [0.0, 0.5, 1.0, 2.0]
        for thr in thresholds_gt:
            if direction == "gt":
                cut_w = [t for t in wins   if t.get(thr_key, 0) > thr]
                cut_l = [t for t in losses if t.get(thr_key, 0) > thr]
            else:
                cut_w = [t for t in wins   if t.get(thr_key, 0) < thr]
                cut_l = [t for t in losses if t.get(thr_key, 0) < thr]
            fp = len(cut_w) / len(wins)   if wins   else 0
            tp = len(cut_l) / len(losses) if losses else 0
            w_cost = abs(statistics.mean([t["net_pnl"] for t in cut_w])) if cut_w else 0
            l_save = abs(statistics.mean([t["net_pnl"] for t in cut_l])) if cut_l else 0
            note = f"  | saves ${l_save:.2f}/loser, costs ${w_cost:.2f}/winner" if cut_l or cut_w else ""
            print(
                f"    {thr_label.split()[0]} {'>' if direction == 'gt' else '<'} {thr:.0f}%  →  "
                f"{len(cut_l)}/{len(losses)} losers TP={tp:.0%}"
                f"  / {len(cut_w)}/{len(wins)} winners FP={fp:.0%}{note}"
            )

    print()
    print(f"  Current n_losers={len(losses)} / 50 needed before deployment.")
    print(f"  Re-run when n_losers hits 10, 25, 50 to track pattern emergence.")

    # ── By rem bucket: where are losers entering? ─────────────────────────────
    # For LDA, term_remaining_s=0 (not from terminal signal). Use window_end_ts - ts_open.
    if losses:
        print()
        print("=" * 80)
        print("LOSER ENTRY BUCKETS (rem = window_end_ts - ts_open)")
        print("=" * 80)
        buckets = {"[0,60s)": 0, "[60,120s)": 0, "[120,300s)": 0}
        for t in losses:
            wend = t.get("window_end_ts", 0) or math.ceil(t["ts_open"] / t.get("window_size_s", 300)) * t.get("window_size_s", 300)
            rem = max(0, wend - t.get("ts_open", 0))
            if rem < 60:
                buckets["[0,60s)"] += 1
            elif rem < 120:
                buckets["[60,120s)"] += 1
            else:
                buckets["[120,300s)"] += 1
        for b, n_b in buckets.items():
            print(f"  {b}: {n_b} losers")


if __name__ == "__main__":
    main()
