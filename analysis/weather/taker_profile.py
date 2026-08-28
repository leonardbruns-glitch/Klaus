"""
Taker profiling + segmentation (read-only). Loads data/taker_trades.parquet.

Finds the exploitable players: who LOSES systematically (the prey we fade), who trades
MECHANICALLY (most markets), and who is smart money. All wallet-level conclusions gated
at n>=MIN_N trades, with a 95% CI on mean PnL/trade (normal approx; n>=100 so fine) so
we never call an edge on noise (CLAUDE.md anti-sycophancy: n>=100, data>thesis).

mark-to-resolution PnL is the skill measure (see taker_harvest.py).

Run: python3 analysis/weather/taker_profile.py
Out: data/taker_wallet_profiles.parquet  + stdout report
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

SRC = "data/taker_trades.parquet"
OUT = "data/taker_wallet_profiles.parquet"
MIN_N = 100          # gate for any wallet-level conclusion


def agg(df):
    g = df.groupby("wallet")
    prof = g.agg(
        name=("name", lambda s: s.mode().iloc[0] if len(s.mode()) else ""),
        n=("pnl_m2r", "size"),
        mkts=("cid", "nunique"),
        cities=("city", "nunique"),
        dates=("date", "nunique"),
        notional=("notional", "sum"),
        pnl=("pnl_m2r", "sum"),
        pnl_std=("pnl_m2r", "std"),
        wr=("pnl_m2r", lambda s: float((s > 0).mean())),
        buy_frac=("side", lambda s: float((s == "BUY").mean())),
        yes_frac=("outcome", lambda s: float((s == "Yes").mean())),
        avg_price=("price", "mean"),
        tail_frac=("price", lambda s: float(((s < 0.10) | (s > 0.90)).mean())),
    )
    prof["pnl_per_trade"] = prof.pnl / prof.n
    prof["edge_per_$"] = prof.pnl / prof.notional.replace(0, np.nan)
    se = prof.pnl_std / np.sqrt(prof.n)
    prof["ci_lo"] = prof.pnl_per_trade - 1.96 * se     # 95% CI on mean PnL/trade
    prof["ci_hi"] = prof.pnl_per_trade + 1.96 * se
    return prof.reset_index()


def show(df, cols, n=25):
    with pd.option_context("display.width", 200, "display.max_columns", None,
                           "display.float_format", lambda x: f"{x:,.3f}"):
        print(df[cols].head(n).to_string(index=False))


def main():
    df = pd.read_parquet(SRC)
    print(f"loaded {len(df):,} trades | {df.wallet.nunique():,} takers | "
          f"{df.cid.nunique()} markets | {df.city.nunique()} cities | {df.date.min()}..{df.date.max()}")
    print(f"net taker PnL (mark-to-res): ${df.pnl_m2r.sum():,.0f}  "
          f"(negative = takers bleed to MMs/spread, as expected)\n")

    prof = agg(df)
    elig = prof[prof.n >= MIN_N].copy()
    print(f"wallets with n>={MIN_N}: {len(elig)}  (carry {elig.n.sum():,} trades, "
          f"{100*elig.n.sum()/len(df):.0f}% of all trades)\n")

    # ---- PREY: robustly losing (CI upper bound < 0), ranked by total $ bled ----
    prey = elig[elig.ci_hi < 0].sort_values("pnl")
    print("=" * 110)
    print(f"PREY — systematically LOSING takers (n>={MIN_N}, 95% CI upper < 0): {len(prey)} wallets, "
          f"total bled ${prey.pnl.sum():,.0f}")
    print("=" * 110)
    show(prey, ["wallet", "name", "n", "mkts", "cities", "notional", "pnl",
                "pnl_per_trade", "ci_hi", "edge_per_$", "wr", "buy_frac", "yes_frac",
                "avg_price", "tail_frac"], 30)

    # ---- WINNERS: robustly +EV (CI lower bound > 0) ----
    win = elig[elig.ci_lo > 0].sort_values("pnl", ascending=False)
    print("\n" + "=" * 110)
    print(f"SMART MONEY — robustly winning takers (n>={MIN_N}, 95% CI lower > 0): {len(win)} wallets, "
          f"total won ${win.pnl.sum():,.0f}")
    print("=" * 110)
    show(win, ["wallet", "name", "n", "mkts", "cities", "pnl", "pnl_per_trade",
               "ci_lo", "edge_per_$", "wr", "buy_frac", "yes_frac", "avg_price", "tail_frac"], 15)

    # ---- MECHANICAL BOTS: widest market coverage (predictable flow) ----
    bots = elig.sort_values("mkts", ascending=False)
    print("\n" + "=" * 110)
    print("MECHANICAL — widest market coverage (likely bots; predictable flow)")
    print("=" * 110)
    show(bots, ["wallet", "name", "n", "mkts", "cities", "dates", "pnl", "pnl_per_trade",
                "edge_per_$", "wr", "buy_frac", "yes_frac", "avg_price", "tail_frac"], 20)

    prof.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}")
    # the top targets for trigger analysis = high-volume prey
    tgt = prey.sort_values("pnl").head(12)["wallet"].tolist()
    print("\nTOP PREY WALLETS (for trigger reverse-engineering):")
    for w in tgt:
        print(" ", w)


if __name__ == "__main__":
    main()
