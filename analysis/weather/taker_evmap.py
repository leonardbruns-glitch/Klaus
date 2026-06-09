"""
The mispricing MAP (read-only). Loads a taker_trades parquet.

Bins EVERY trade by side x outcome x price-band and computes the mark-to-resolution
edge PER SHARE, with n>=100 gates + 95% CIs. This is the mathematical map of the
goldmine: it shows exactly which price zones are mispriced (where buyers bleed) and the
mirror zones where the counter-side is +EV. Independent of any single wallet.

per-share edge:  BUY -> token_won - price ;  SELL -> price - token_won
EV/share is the expected $ per share if you HOLD that trade to resolution.
"bled$" = total realized mark-to-res loss of the takers in that cell = the pool on offer.

Run: python3 analysis/weather/taker_evmap.py [parquet_path]
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/taker_trades_2026-05-15_2026-05-15.parquet"
BANDS = [0, .01, .02, .05, .10, .20, .35, .50, .65, .80, .90, .95, .98, .995, 1.001]
MIN_N = 100


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z*z/n
    c = p + z*z/(2*n)
    h = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)


def main():
    df = pd.read_parquet(SRC)
    df["eshare"] = np.where(df.side == "BUY", df.token_won - df.price, df.price - df.token_won)
    df["band"] = pd.cut(df.price, BANDS, right=False)
    print(f"{SRC}: {len(df):,} trades, {df.wallet.nunique():,} takers, dates {df.date.min()}..{df.date.max()}\n")

    for side in ("BUY", "SELL"):
        for outcome in ("Yes", "No"):
            sub = df[(df.side == side) & (df.outcome == outcome)]
            if len(sub) < MIN_N:
                continue
            print("=" * 104)
            print(f"{side} {outcome}   (n={len(sub):,}, total eshare ${sub.eshare.mul(sub['size']).sum():,.0f})")
            print(f"{'price band':>14} {'n':>7} {'mean_px':>8} {'WR%':>6} {'WR 95%CI':>14} "
                  f"{'EV/sh':>8} {'EV CI':>16} {'edge/$':>8} {'bled$':>10}")
            g = sub.groupby("band", observed=True)
            for band, x in g:
                n = len(x)
                if n < 20:
                    continue
                wr = float((x.token_won == 1).mean()) if side == "BUY" else float((x.token_won == 0).mean())
                wlo, whi = wilson(int(round(wr*n)), n)
                ev = x.eshare.mean()
                se = x.eshare.std() / np.sqrt(n)
                evlo, evhi = ev - 1.96*se, ev + 1.96*se
                edollar = ev / x.price.mean() if x.price.mean() else float("nan")
                bled = x.pnl_m2r[x.pnl_m2r < 0].sum()
                flag = "" if n >= MIN_N else "  (n<100)"
                print(f"{str(band):>14} {n:>7} {x.price.mean():>8.3f} {100*wr:>5.0f}% "
                      f"[{100*wlo:>4.0f},{100*whi:>4.0f}] {ev:>+8.3f} [{evlo:>+6.3f},{evhi:>+6.3f}] "
                      f"{edollar:>+7.2f} {bled:>10.0f}{flag}")
            print()


if __name__ == "__main__":
    main()
