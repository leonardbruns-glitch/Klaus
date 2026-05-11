"""
S2 live-strategy audit — 3-criterion validation suite.

S2 definition (live bot as of 2026-05-11):
  arb_sum_yes_no < 0.99  |  DOWN  |  ask 0.10-0.55  |  rem 60-180s
  5m windows  |  BTC + ETH only (live whitelist)
  Exit surface: PT0.95 / T-15 / T-5 safety

Questions answered:
  (0) Baseline: does S2 hold EV on 4-day data?
  (i) Per-asset: +EV in each asset at n>=100?
  (ii) OOS: LOO leave-one-day-out — positive on every held-out day?
  (iii) Realistic-fill: still +EV at 1.5x and 2x ask-depth margin?
  (iv) ask ceiling tightening: does ask<0.40 improve S2?
  (v) Early-UTC: is the May-11 early session an ongoing pattern?
"""
from pathlib import Path
import numpy as np
import pandas as pd

REPLAY = Path("/root/Klaus/analytics/discover/replay.parquet")
STAKE  = 5.0
ORIG_ENTRY_SLIP = 0.005
ORIG_EXIT_SLIP  = 0.005

# S2 parameters
S2_OUTCOME_DIR    = "down"
S2_ARB_CEIL       = 0.99
S2_ASK_LO         = 0.10
S2_ASK_HI         = 0.55
S2_REM_LO         = 60
S2_REM_HI         = 180
S2_WINDOW_S       = 300          # 5m only
S2_ASSETS         = {"BTC", "ETH"}   # live whitelist
S2_POLICY         = "pnl_T15"    # primary backtest proxy for T-15 exit
S2_POLICY_PT      = "pnl_PT95_T30"  # closer to live PT0.95 + T-30 surface


def boot_ci(arr, B=2000, lo=2.5, hi=97.5, seed=42):
    rng = np.random.default_rng(seed)
    n = len(arr)
    if n == 0:
        return (np.nan, np.nan)
    idx = rng.integers(0, n, (B, n))
    means = arr[idx].mean(axis=1)
    return (float(np.percentile(means, lo)), float(np.percentile(means, hi)))


def summarize(label, arr, indent="  "):
    n = len(arr)
    if n == 0:
        print(f"{indent}{label}: n=0  no data")
        return
    ev = arr.mean()
    ci = boot_ci(arr)
    wr = (arr > 0).mean()
    pf_w = arr[arr > 0].sum() if (arr > 0).any() else 0
    pf_l = -arr[arr < 0].sum() if (arr < 0).any() else 1e-9
    pf = pf_w / pf_l if pf_l > 0 else float("inf")
    flag = "+" if ci[0] > 0 else ("~" if ev > 0 else "-")
    print(f"{indent}[{flag}] {label}: n={n:>4d}  EV=${ev:+.2f}  "
          f"CI95=[{ci[0]:+.2f},{ci[1]:+.2f}]  WR={wr:.0%}  PF={pf:.2f}")
    return ev, ci, n


def realistic_pnl_arr(entry_asks, raw_pnls, new_es, new_xs,
                      oe=ORIG_ENTRY_SLIP, ox=ORIG_EXIT_SLIP, stake=STAKE):
    R = (raw_pnls / stake + 1) * (1 + oe) / (1 - ox)
    return stake * (R * (1 - new_xs) / (1 + new_es) - 1)


# ── load ───────────────────────────────────────────────────────────────────────
print("Loading replay.parquet ...", flush=True)
df = pd.read_parquet(REPLAY)
print(f"  total rows: {len(df):,}")

# ── Apply S2 entry conditions FIRST, then first-fire dedup ───────────────────
# "First fire" for S2 = the earliest tick in each window that passes the S2 filter.
# Deduping before filtering would give the absolute earliest tick per window,
# which is almost never in rem 60-180 (most windows start at rem ~300).

s2_mask_base = (
    (df["window_size_s"] == S2_WINDOW_S) &
    (df["outcome_dir"]   == S2_OUTCOME_DIR) &
    (df["arb_sum_yes_no"] < S2_ARB_CEIL) &
    (df["best_ask"]      >= S2_ASK_LO) &
    (df["best_ask"]      < S2_ASK_HI) &
    (df["seconds_to_resolution"] >= S2_REM_LO) &
    (df["seconds_to_resolution"] <= S2_REM_HI)
)

# feasibility filter
shares_needed = STAKE / (df["best_ask"] * (1 + ORIG_ENTRY_SLIP))
feasible_mask = df["ob_top1_ask_size"] >= shares_needed

# first-fire dedup after filter (all assets)
sub_all_assets = (df[s2_mask_base]
                  .sort_values("ts_s")
                  .drop_duplicates(["token_id", "window_end_ts"], keep="first")
                  .copy())

sub_feas = (df[s2_mask_base & feasible_mask]
            .sort_values("ts_s")
            .drop_duplicates(["token_id", "window_end_ts"], keep="first")
            .copy())

# asset whitelist (live config: BTC+ETH)
sub = sub_feas[sub_feas["asset"].isin(S2_ASSETS)].copy()

print(f"\n{'='*72}")
print("S2 FILTER COUNTS")
print(f"  All assets, no feasibility: n={len(sub_all_assets)}")
print(f"  All assets, feasibility-filtered: n={len(sub_feas)}")
print(f"  BTC+ETH only (live whitelist), feasibility-filtered: n={len(sub)}")
print(f"  Date range: {sub['date'].min()} – {sub['date'].max()}")


# ── (0) BASELINE ──────────────────────────────────────────────────────────────
print(f"\n{'='*72}")
print("(0) BASELINE — both exit policies")
arr_t15  = sub[S2_POLICY].dropna().to_numpy()
arr_pt   = sub[S2_POLICY_PT].dropna().to_numpy()
summarize(f"T15 (backtest primary)", arr_t15)
summarize(f"PT95+T30 (closest to live)", arr_pt)


# ── (i) PER-ASSET ─────────────────────────────────────────────────────────────
print(f"\n{'='*72}")
print("(i) PER-ASSET breakdown")
pos_assets = 0
for asset in ["BTC", "ETH", "SOL"]:
    a = sub[sub["asset"] == asset][S2_POLICY].dropna().to_numpy()
    r = summarize(asset, a)
    if r and r[1][0] > 0 and r[2] >= 100:
        pos_assets += 1
print(f"\n  → {pos_assets}/2 live assets have CI>0 at n≥100")
crit_i = pos_assets >= 2


# ── (ii) LEAVE-ONE-DAY-OUT OOS ────────────────────────────────────────────────
print(f"\n{'='*72}")
print("(ii) LEAVE-ONE-DAY-OUT cross-validation")
days = sorted(sub["date"].unique())
oos_pos = 0
for held in days:
    test_arr = sub[sub["date"] == held][S2_POLICY].dropna().to_numpy()
    r = summarize(f"held={held}", test_arr)
    if r and r[0] > 0:
        oos_pos += 1
print(f"\n  → {oos_pos}/{len(days)} held-out days +EV")
crit_ii = oos_pos == len(days)


# ── (iii) REALISTIC-FILL ──────────────────────────────────────────────────────
print(f"\n{'='*72}")
print("(iii) REALISTIC-FILL sensitivity (entry-side ask_size margin)")
raw_asks = sub["best_ask"].to_numpy()
raw_pnl  = sub[S2_POLICY].dropna().to_numpy()
# trim to same length (should be identical after dropna on same df)
n_ = min(len(raw_asks), len(raw_pnl))
raw_asks, raw_pnl = raw_asks[:n_], raw_pnl[:n_]

adj_15 = realistic_pnl_arr(raw_asks, raw_pnl, 0.01, 0.01)   # 1% slip
adj_20 = realistic_pnl_arr(raw_asks, raw_pnl, 0.02, 0.02)   # 2% slip
adj_40 = realistic_pnl_arr(raw_asks, raw_pnl, 0.04, 0.04)   # 4% slip
print(f"  EV@0.5% slip (baseline): ${raw_pnl.mean():+.2f}")
print(f"  EV@1.0% slip:            ${adj_15.mean():+.2f}")
print(f"  EV@2.0% slip:            ${adj_20.mean():+.2f}")
print(f"  EV@4.0% slip:            ${adj_40.mean():+.2f}")
crit_iii = adj_20.mean() > 0
print(f"\n  → 2%-slip EV {'>0' if crit_iii else '≤0'}  ({'PASS' if crit_iii else 'FAIL'})")


# ── (iv) ASK CEILING TIGHTENING ───────────────────────────────────────────────
print(f"\n{'='*72}")
print("(iv) ASK CEILING TIGHTENING — does ask<0.40 improve S2?")
for ceil in [0.30, 0.35, 0.40, 0.45, 0.55]:
    a = sub[sub["best_ask"] < ceil][S2_POLICY].dropna().to_numpy()
    summarize(f"ask<{ceil:.2f}", a)
# also show the 0.40-0.55 sub-bucket
bucket = sub[(sub["best_ask"] >= 0.40) & (sub["best_ask"] < 0.55)][S2_POLICY].dropna().to_numpy()
summarize(f"ask [0.40,0.55) bucket only", bucket)

# per-asset at ask<0.40
print("\n  Per-asset at ask<0.40:")
sub40 = sub[sub["best_ask"] < 0.40]
for asset in ["BTC", "ETH"]:
    a = sub40[sub40["asset"] == asset][S2_POLICY].dropna().to_numpy()
    summarize(asset, a, indent="    ")


# ── (v) EARLY-UTC HOUR PATTERN ────────────────────────────────────────────────
print(f"\n{'='*72}")
print("(v) EARLY-UTC HOUR PATTERN (00-08 UTC) — is May-11 early-UTC loss structural?")
sub_early = sub[sub["hour_utc"] < 8]
sub_late  = sub[sub["hour_utc"] >= 8]
print("  All days combined:")
summarize("UTC 00-07", sub_early[S2_POLICY].dropna().to_numpy())
summarize("UTC 08-23", sub_late[S2_POLICY].dropna().to_numpy())
print("\n  Per-day early-UTC (00-07):")
for d in days:
    a = sub[(sub["date"] == d) & (sub["hour_utc"] < 8)][S2_POLICY].dropna().to_numpy()
    summarize(f"{d} UTC 00-07", a)


# ── VERDICT ───────────────────────────────────────────────────────────────────
print(f"\n{'='*72}")
print("VERDICT")
print(f"  (i)  Per-asset   : {'PASS' if crit_i else 'FAIL'}")
print(f"  (ii) OOS         : {'PASS' if crit_ii else 'FAIL'}")
print(f"  (iii) Slip-fill  : {'PASS' if crit_iii else 'FAIL'}")
overall = crit_i and crit_ii and crit_iii
print(f"\n  S2 OVERALL: {'PASS — capital defensible' if overall else 'FAIL — reassess capital allocation'}")
