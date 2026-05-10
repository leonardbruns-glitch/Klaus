"""
Strategy family grid.

Generates entry filters across:
    rem windows × ask ranges × bid ranges × ob_imb × spread × signal × asset/dir

For each filter, computes evaluate() under each policy with first-fire-per-window.
Outputs a long table; downstream filters apply CI/stability/overfit checks.
"""
from __future__ import annotations
import sys, json, time, itertools
sys.path.insert(0, '/root/Klaus/analytics/discover')

import numpy as np
import pandas as pd
from analyze import first_fire, boot_ci

PARQUET = '/root/Klaus/analytics/discover/replay.parquet'
OUT = '/root/Klaus/analytics/discover/grid.parquet'
RNG = np.random.default_rng(42)

# Step-1 ask-depth feasibility re-run.
# Set FEASIBILITY=True to require ob_top1_ask_size >= shares_needed at entry.
# Engine constants must mirror engine.py.
import os
FEASIBILITY = os.environ.get("FEASIBILITY", "0") == "1"
STAKE_USD = 5.00
ENTRY_SLIP = 0.005
if FEASIBILITY:
    OUT = '/root/Klaus/analytics/discover/grid_feasible.parquet'

POLICIES = ["HOLD","PT90_T1","PT93_T1","PT95_T1","PT97_T1","PT99_T1",
            "PT95_T30","PT97_T30","PT99_T30","T30","T15","T5","TRAIL5","PT95_TR3_T1"]


def evaluate_strategy(df, mask, label, polices=POLICIES):
    sub = df.loc[mask]
    if len(sub) == 0:
        return []
    ff = sub.sort_values("ts_s").drop_duplicates(["token_id","window_end_ts"], keep="first")
    rows = []
    for pol in polices:
        col = f"pnl_{pol}"
        if col not in ff.columns:
            continue
        pnl = ff[col].dropna().to_numpy()
        if len(pnl) < 20:
            continue
        ci = boot_ci(pnl) if len(pnl)>=20 else (np.nan,np.nan)
        gp = pnl[pnl>0].sum(); gl = -pnl[pnl<0].sum()
        pf = gp/gl if gl>0 else np.inf
        # per-day
        by_day = ff.groupby("date")[col].agg(["count","mean","sum"])
        per_day_means = by_day["mean"].dropna().to_dict()
        per_asset = ff.groupby("asset")[col].agg(["count","mean"])
        # Stability: fraction of days with positive EV
        pos_days = float((by_day["mean"]>0).mean()) if len(by_day) else 0.0
        # Concentration: max single-day EV share of total positive sum
        day_sums = by_day["sum"]
        total_abs = day_sums.abs().sum()
        max_day_concentration = (day_sums.abs().max()/total_abs) if total_abs>0 else np.nan
        # Per-asset positivity
        pos_assets = float((per_asset["mean"]>0).mean()) if len(per_asset) else 0.0
        rows.append(dict(
            strategy=label,
            policy=pol,
            n=int(len(pnl)),
            ev_trade=float(pnl.mean()),
            ev_total=float(pnl.sum()),
            wr=float((pnl>0).mean()),
            pf=float(pf),
            ci_lo=float(ci[0]) if not np.isnan(ci[0]) else np.nan,
            ci_hi=float(ci[1]) if not np.isnan(ci[1]) else np.nan,
            sharpe=float(pnl.mean()/pnl.std()*np.sqrt(len(pnl))) if pnl.std()>0 else np.nan,
            n_days=int(by_day.shape[0]),
            n_assets=int(per_asset.shape[0]),
            pos_days_frac=pos_days,
            pos_assets_frac=pos_assets,
            max_day_share=max_day_concentration,
            tail_loss=float(np.percentile(pnl,5)),
            max_dd=_max_dd(ff.sort_values("ts_s")[col].fillna(0).to_numpy()),
            trades_per_day=float(len(pnl)/max(by_day.shape[0],1)),
        ))
    return rows


def _max_dd(seq):
    if len(seq)==0: return 0.0
    cum = seq.cumsum()
    peak = np.maximum.accumulate(cum)
    return float((cum-peak).min())


def main():
    df = pd.read_parquet(PARQUET)
    print(f"loaded {len(df):,} rows", flush=True)

    # Coerce regimes if present
    for c in ["vol_regime","trend_regime","liquidity_regime"]:
        if c not in df.columns:
            df[c] = "unknown"

    # Step-1 ask-depth feasibility — applied at the row level so that
    # `first_fire` per (token, window) lands on the first FILLABLE tick.
    if FEASIBILITY:
        fill_ask = df["best_ask"] * (1 + ENTRY_SLIP)
        shares_needed = STAKE_USD / fill_ask
        feas = df["ob_top1_ask_size"].fillna(0) >= shares_needed
        before = len(df)
        df = df.loc[feas].reset_index(drop=True)
        print(f"[FEASIBILITY ON] rows {before:,} -> {len(df):,} "
              f"({100*len(df)/before:.1f}% retained)", flush=True)
    else:
        print("[FEASIBILITY OFF] running stock grid", flush=True)

    # ----- Strategy axes -----
    REM_WINDOWS = [
        ("rem5_30",   5,  30),
        ("rem25_90",  25, 90),
        ("rem10_60",  10, 60),
        ("rem30_120", 30, 120),
        ("rem60_180", 60, 180),
        ("rem120_240",120,240),
        ("rem180_300",180,300),
        ("rem5_120",  5, 120),
    ]
    ASK_BANDS = [
        ("ask_low",   0.10, 0.30),
        ("ask_mid",   0.30, 0.55),
        ("ask_med",   0.55, 0.75),
        ("ask_hi",    0.75, 0.90),
        ("ask_xhi",   0.85, 0.95),
        ("ask_top",   0.92, 0.99),
        ("ask_any",   0.05, 0.99),
    ]
    SIGNAL_FILTERS = [
        ("none",       lambda d: pd.Series(True, index=d.index)),
        ("imb_pos20",  lambda d: d["ob_imb_top3"] >= 0.20),
        ("imb_pos50",  lambda d: d["ob_imb_top3"] >= 0.50),
        ("imb_neg20",  lambda d: d["ob_imb_top3"] <= -0.20),
        ("snap30_pos5",lambda d: d["tok_snap_30s"] >= 5.0),
        ("snap30_pos15",lambda d: d["tok_snap_30s"] >= 15.0),
        ("snap30_neg5",lambda d: d["tok_snap_30s"] <= -5.0),
        ("snap60_pos15",lambda d: d["tok_snap_60s"] >= 15.0),
        ("snap60_neg15",lambda d: d["tok_snap_60s"] <= -15.0),
        ("bnc5m_align",lambda d: ((d["outcome_dir"]=="up") & (d["binance_ret_5m_pct"]>0)) |
                                  ((d["outcome_dir"]=="down")& (d["binance_ret_5m_pct"]<0))),
        ("bnc5m_against",lambda d: ((d["outcome_dir"]=="up") & (d["binance_ret_5m_pct"]<0)) |
                                    ((d["outcome_dir"]=="down")& (d["binance_ret_5m_pct"]>0))),
        ("bnc5m_strong_align",lambda d: ((d["outcome_dir"]=="up") & (d["binance_ret_5m_pct"]>=0.10)) |
                                         ((d["outcome_dir"]=="down")& (d["binance_ret_5m_pct"]<=-0.10))),
        ("arb_sub1",   lambda d: d["arb_sum_yes_no"] < 1.00),
        ("arb_sub099", lambda d: d["arb_sum_yes_no"] < 0.99),
        ("spread_tight", lambda d: d["spread_abs"] <= 0.02),
        ("spread_wide",  lambda d: d["spread_abs"] >= 0.05),
        ("depth_deep",   lambda d: d["ob_book_depth_size"] >= 1000),
        ("depth_thin",   lambda d: d["ob_book_depth_size"] <= 200),
        ("vpin_hi",      lambda d: d.get("vpin_score", pd.Series(0,index=d.index)) >= 0.4),
        ("vpin_mid",     lambda d: (d.get("vpin_score", pd.Series(0,index=d.index)) >= 0.30) &
                                    (d.get("vpin_score", pd.Series(0,index=d.index)) < 0.45)),
    ]

    DIR_VARIANTS = [
        ("any", None),
        ("up_only", "up"),
        ("dn_only", "down"),
    ]

    rows = []
    t0 = time.time()
    n_combos = len(REM_WINDOWS)*len(ASK_BANDS)*len(SIGNAL_FILTERS)*len(DIR_VARIANTS)
    print(f"total combos: {n_combos}", flush=True)

    done = 0
    for (rem_lbl, rem_lo, rem_hi), (ask_lbl, ask_lo, ask_hi), \
        (sig_lbl, sig_fn), (dir_lbl, dir_v) in itertools.product(
            REM_WINDOWS, ASK_BANDS, SIGNAL_FILTERS, DIR_VARIANTS):
        m = (df["seconds_to_resolution"]>=rem_lo) & (df["seconds_to_resolution"]<=rem_hi)
        m &= (df["best_ask"]>=ask_lo) & (df["best_ask"]<=ask_hi)
        m &= sig_fn(df)
        if dir_v is not None:
            m &= df["outcome_dir"]==dir_v
        label = f"{rem_lbl}|{ask_lbl}|{sig_lbl}|{dir_lbl}"
        rows.extend(evaluate_strategy(df, m, label))
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{n_combos} ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    out.to_parquet(OUT, index=False)
    print(f"\nwritten {OUT} ({len(out)} rows)", flush=True)
    print(f"elapsed {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
