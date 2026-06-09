"""
Rigorous validation of the mispriced cells found by taker_evmap.py (read-only).

The per-TRADE CIs in the EV map are too tight: trades within one market are perfectly
correlated (one bucket -> one YES outcome). The honest unit is PER-MARKET. For a
(side,outcome,price-band) cell we compute, across the qualifying markets:
  per-market vote = token_won (0/1) vs the avg price paid in-band
  edge = mean(token_won) - mean(price)   with a BINOMIAL CI on the win rate (n=markets)
We also check: concentration (top-5 market share of signed PnL, #cities), TIMING
(hour-of-day — is the edge just late-day convergence?), and btype split.

A cell is a real edge only if: n_markets large, per-market CI excludes break-even,
NOT concentrated in a few markets, and present across hours (not only the final hour).

Run: python3 analysis/weather/taker_edge_validate.py [parquet_path]
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/taker_trades_2026-05-15_2026-05-15.parquet"


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k/n; d = 1+z*z/n; c = p+z*z/(2*n); h = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)


def edge_report(df, side, outcome, plo, phi):
    sub = df[(df.side == side) & (df.outcome == outcome) &
             (df.price >= plo) & (df.price < phi)].copy()
    print("=" * 96)
    print(f"{side} {outcome}  price [{plo},{phi})   trades={len(sub):,}")
    if len(sub) < 50:
        print("  (too few trades)\n"); return
    # per-market vote: outcome (same for all rows in a market) vs avg in-band price
    gm = sub.groupby("cid").agg(won=("token_won", "first"),
                                px=("price", "mean"),
                                eshare=("eshare", "mean"),
                                city=("city", "first"),
                                btype=("btype", "first"),
                                pnl=("pnl_m2r", "sum"),
                                ntr=("price", "size"))
    nM = len(gm)
    winM = int((gm.won == 1).sum()) if side == "BUY" else int((gm.won == 0).sum())
    wr = winM/nM
    wlo, whi = wilson(winM, nM)
    avg_px = gm.px.mean()
    ev_market = gm.eshare.mean()
    se = gm.eshare.std()/np.sqrt(nM)
    print(f"  PER-MARKET: n_markets={nM}  win-side WR={100*wr:.0f}% [{100*wlo:.0f},{100*whi:.0f}]  "
          f"avg_px={avg_px:.3f}  EV/sh(market-mean)={ev_market:+.3f} [{ev_market-1.96*se:+.3f},{ev_market+1.96*se:+.3f}]")
    verdict = "REAL (CI clears 0)" if (ev_market-1.96*se > 0 or ev_market+1.96*se < 0) else "NOT SIGNIFICANT per-market"
    print(f"  VERDICT: {verdict}")
    # concentration
    tot = gm.pnl.sum()
    top5 = gm.pnl.reindex(gm.pnl.abs().sort_values(ascending=False).index).head(5).sum()
    print(f"  concentration: total taker PnL ${tot:,.0f}; top-5 markets = ${top5:,.0f} "
          f"({100*top5/tot if tot else 0:.0f}% of total); cities={gm.city.nunique()}")
    # timing by hour
    by_h = sub.groupby("hour_utc").agg(n=("eshare", "size"), ev=("eshare", "mean"))
    hrs = " ".join(f"{h:02d}:{r.ev:+.2f}(n{int(r.n)})" for h, r in by_h.iterrows() if r.n >= 30)
    print(f"  by hour_utc (ev/sh, n>=30): {hrs}")
    # btype
    bt = sub.groupby("btype").agg(n=("eshare", "size"), ev=("eshare", "mean"),
                                  mk=("cid", "nunique"))
    bts = "  ".join(f"{b}:{r.ev:+.3f}(mk{int(r.mk)})" for b, r in bt.iterrows())
    print(f"  by btype: {bts}\n")


def main():
    df = pd.read_parquet(SRC)
    df["eshare"] = np.where(df.side == "BUY", df.token_won - df.price, df.price - df.token_won)
    print(f"{SRC}: {len(df):,} trades, {df.cid.nunique()} markets, {df.date.nunique()} day(s)\n")
    # the standout cells from the EV map
    edge_report(df, "BUY", "Yes", 0.50, 0.80)   # favorites underpriced (+0.13..0.16)
    edge_report(df, "BUY", "Yes", 0.20, 0.35)   # mid-longshot YES overpriced ($22k bled)
    edge_report(df, "BUY", "No", 0.35, 0.50)    # NO overpriced (-0.188)
    edge_report(df, "BUY", "No", 0.65, 0.90)    # tail-NO/lockout zone (+0.03..0.04)
    edge_report(df, "BUY", "Yes", 0.00, 0.05)   # deep longshot YES overpriced


if __name__ == "__main__":
    main()
