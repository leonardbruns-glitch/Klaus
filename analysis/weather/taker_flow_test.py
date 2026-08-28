"""
Is taker FLOW informed or noise? (read-only, per-market => no pseudo-replication).

The whole 'trade against takers' idea forks here:
  - if net taker buy-pressure PREDICTS resolution beyond price -> flow is INFORMED -> follow.
  - if it does NOT -> flow is noise; and if it also MOVES price, price overshoots -> FADE.

Per market we build an implied-YES view (No trades mapped to 1-price), a volume-weighted
implied-YES price (vwap), and net YES pressure (BUY Yes / SELL No = +, SELL Yes / BUY No = -)
normalized by volume. Then, STRATIFIED BY vwap (the confound), we ask whether high-flow
markets resolve YES more than low-flow markets. Ground truth = Gamma resolution (0/1).

Run: python3 analysis/weather/taker_flow_test.py [parquet_path]
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/taker_trades_2026-05-15_2026-05-15.parquet"
MIN_TR = 20   # min trades/market to include


def main():
    df = pd.read_parquet(SRC)
    # implied-YES price per trade; signed YES pressure per trade ($)
    df["impl_yes"] = np.where(df.outcome == "Yes", df.price, 1 - df.price)
    sgn = np.where(df.outcome == "Yes", 1.0, -1.0) * np.where(df.side == "BUY", 1.0, -1.0)
    df["yes_flow"] = sgn * df.notional          # + = pressure toward YES
    g = df.groupby("cid")
    m = g.agg(yes_res=("yes_res", "first"),
              vwap=("impl_yes", lambda s: np.average(s, weights=df.loc[s.index, "size"])),
              vol=("notional", "sum"),
              netflow=("yes_flow", "sum"),
              ntr=("price", "size"))
    m = m[m.ntr >= MIN_TR].copy()
    m["yes_res"] = (m.yes_res >= 0.99).astype(int)
    m["flow_norm"] = m.netflow / m.vol          # in [-1,1]
    m["surprise"] = m.yes_res - m.vwap          # resolved above/below priced
    print(f"{SRC}: {len(m)} markets (>= {MIN_TR} trades each), {df.date.nunique()} day(s)\n")

    # overall price efficiency
    r_pe = np.corrcoef(m.vwap, m.yes_res)[0, 1]
    print(f"price efficiency  corr(vwap, resolution) = {r_pe:+.3f}  "
          f"(brier={(np.mean((m.vwap-m.yes_res)**2)):.3f})")

    # does flow predict the surprise? (marginal info beyond price)
    r_fs = np.corrcoef(m.flow_norm, m.surprise)[0, 1]
    n = len(m); se = 1/np.sqrt(n-3)
    z = 0.5*np.log((1+r_fs)/(1-r_fs)); lo = np.tanh(z-1.96*se); hi = np.tanh(z+1.96*se)
    print(f"flow informedness corr(flow_norm, surprise) = {r_fs:+.3f}  95%CI[{lo:+.3f},{hi:+.3f}]")
    print("  >0 = flow INFORMED (follow);  ~0 = flow uninformative;  <0 = flow CONTRARIAN (fade)\n")

    # stratify by price band: within band, resolution rate by flow tercile
    print("within-vwap-band: resolution rate (YES%) by net-flow tercile  [n]")
    print(f"{'vwap band':>12} {'flow-LOW':>14} {'flow-MID':>14} {'flow-HIGH':>14}  {'spread(H-L)':>11}")
    bands = [(0.05,0.20),(0.20,0.40),(0.40,0.60),(0.60,0.80),(0.80,0.95)]
    for lo_b, hi_b in bands:
        seg = m[(m.vwap >= lo_b) & (m.vwap < hi_b)]
        if len(seg) < 15:
            continue
        try:
            seg = seg.assign(ft=pd.qcut(seg.flow_norm, 3, labels=["L","M","H"], duplicates="drop"))
        except Exception:
            continue
        cells = {}
        for t in ["L","M","H"]:
            s = seg[seg.ft == t]
            cells[t] = (s.yes_res.mean(), len(s)) if len(s) else (float("nan"),0)
        sp = (cells["H"][0]-cells["L"][0]) if (cells["H"][1] and cells["L"][1]) else float("nan")
        def c(t): return f"{100*cells[t][0]:4.0f}% [{cells[t][1]:>3}]"
        print(f"{lo_b:.2f}-{hi_b:.2f} {c('L'):>14} {c('M'):>14} {c('H'):>14}  {100*sp:>+9.0f}pp")


if __name__ == "__main__":
    main()
