"""Remaining-Rise Climatology Pricer — model-free pricing of the daily-max bin.

Thesis (Proposal 1, 2026-06-02): price daily-high-temperature bins from the
empirical conditional distribution of the running-max GAP

    remaining_rise(t) = daily_max - running_max(t)   conditioned on
                        (city, hours-to-peak, season)

instead of a Gaussian forecast distribution. remaining_rise is BOUNDED and
right-SKEWED (it can only be >=0 and decays fast); a Gaussian over-weights the
symmetric upper tail -> the market's structural mispricing (the fade is the
post-peak special case). This script:

  1. builds the empirical remaining_rise table on TRAIN years,
  2. OOS-prices each test city-day's resolved bin at several decision offsets
     relative to the climatological peak,
  3. scores it head-to-head vs a Gaussian(same mean, fitted sd) baseline via
     multiclass Brier + log-loss + tail/favorite calibration.

If the empirical table beats Gaussian OOS (esp. in the tail), the pricer is the
generating model behind the fade edge and the favorite-dual. Run locally:

    python3 analysis/weather/climatology_pricer.py
"""
from __future__ import annotations
import numpy as np, pandas as pd
from math import erf, sqrt

OFFSETS = [-3, -2, -1, 0, 1]   # decision hour relative to climatological peak
TRAIN_MAX_YEAR = 2023          # train 2021-2023, test 2024 (ASOS parquet ends 2024)
MIN_DAY_OBS = 18               # near-complete local days only
MIN_CELL = 40                  # min train samples for a per-(city,offset,season) cell

ICAO_OFF = {"KLGA":-5,"KORD":-6,"KLAX":-8,"KSFO":-8,"KSEA":-8,"KMIA":-5,"KDAL":-6,
"KHOU":-6,"KAUS":-6,"KDEN":-7,"KBKF":-7,"KATL":-5,"KPHX":-7,"MMMX":-6,"CYYZ":-5,
"SBGR":-3,"SAEZ":-3,"MPHO":-5,"SKBO":-5,"SPJC":-5,"SCEL":-3,"EGLC":0,"LFPB":1,
"LEMD":1,"EHAM":1,"LIMC":1,"EDDM":1,"EDDB":1,"EPWA":1,"EBBR":1,"LEBL":1,"EFHK":2,
"LIRF":1,"LKPR":1,"LHBP":1,"LROP":2,"LGAV":2,"LTFM":3,"LTAC":3,"UUEE":3,"UUWW":3,
"ESSA":1,"ENGM":1,"EKCH":1,"LOWW":1,"LSZH":1,"HECA":2,"DNMM":1,"HKJK":3,"FAOR":2,
"FACT":2,"OERK":3,"OEJN":3,"LLBG":3,"VHHH":8,"RJTT":9,"RKSI":9,"RKPK":9,"ZBAA":8,
"ZSPD":8,"ZGSZ":8,"ZGGG":8,"ZSJN":8,"ZSQD":8,"ZHHH":8,"ZUUU":8,"ZUCK":8,"RCSS":8,
"WSSS":8,"WIHH":7,"WMKK":8,"VTBS":7,"VABB":5,"VIDP":5,"VILK":5,"VGHS":6,"OMDB":4,
"OPKC":5,"RPLL":8,"YSSY":10,"NZWN":12}

def season(m):  # 3-way to keep cells dense
    return {12:0,1:0,2:0, 3:1,4:1,5:1, 6:2,7:2,8:2, 9:3,10:3,11:3}[m]

def _ncdf(x, mu, sd):
    if sd <= 1e-6: return 1.0 if x >= mu else 0.0
    return 0.5 * (1.0 + erf((x - mu) / (sd * sqrt(2))))


def build_frame(path):
    df = pd.read_parquet(path).dropna(subset=["temp_c"])
    df["off"] = df["icao"].map(ICAO_OFF).fillna(0)
    df["lt"] = df["time_utc"] + pd.to_timedelta(df["off"], unit="h")
    df["ldate"] = df["lt"].dt.date
    df["lhour"] = df["lt"].dt.hour
    df["year"] = df["lt"].dt.year
    df["month"] = df["lt"].dt.month
    df = df.sort_values(["city", "ldate", "lhour"])
    g = df.groupby(["city", "ldate"], sort=False)
    df["rmax"] = g["temp_c"].cummax()
    nobs = g["temp_c"].transform("size")
    df = df[nobs >= MIN_DAY_OBS]
    return df


def day_table(df):
    """One row per (city, ldate): M, season, year, and rmax at each decision hour."""
    base = df.groupby(["city", "ldate"]).agg(
        M=("temp_c", "max"), year=("year", "first"), month=("month", "first")).reset_index()
    base["season"] = base["month"].map(season)
    # climatological peak hour per (city, season) from argmax local hour
    pk = (df.loc[df.groupby(["city", "ldate"])["temp_c"].idxmax(), ["city", "ldate", "lhour"]]
          .rename(columns={"lhour": "pk_hour"}))
    base = base.merge(pk, on=["city", "ldate"], how="left")
    # modal peak hour per (city, season), TRAIN only, as the climatological peak
    tr = base[base["year"] <= TRAIN_MAX_YEAR]
    peak_clim = (tr.groupby(["city", "season"])["pk_hour"]
                 .agg(lambda s: int(s.round().mode().iloc[0])).rename("peak_clim").reset_index())
    base = base.merge(peak_clim, on=["city", "season"], how="left")
    base = base.dropna(subset=["peak_clim"])
    base["peak_clim"] = base["peak_clim"].astype(int)
    # rmax at each decision hour = last rmax with lhour <= decision_hour
    rm = df[["city", "ldate", "lhour", "rmax"]]
    for d in OFFSETS:
        bd = base[["city", "ldate", "peak_clim"]].copy()
        bd["dh"] = bd["peak_clim"] + d
        m = rm.merge(bd[["city", "ldate", "dh"]], on=["city", "ldate"])
        m = m[m["lhour"] <= m["dh"]]
        last = m.groupby(["city", "ldate"])["rmax"].last().rename(f"R{d}")
        base = base.merge(last, on=["city", "ldate"], how="left")
    return base


def brier_logloss(p_by_c, actual_c):
    # p_by_c: dict int->prob (need not sum to 1; renormalize). actual_c: int
    tot = sum(p_by_c.values()) or 1.0
    p = {c: v / tot for c, v in p_by_c.items()}
    pa = p.get(actual_c, 0.0)
    # brier over the union support
    b = sum((p.get(c, 0.0) - (1.0 if c == actual_c else 0.0)) ** 2 for c in p) \
        + (0.0 if actual_c in p else 1.0)
    ll = -np.log(max(pa, 1e-6))
    return b, ll, pa


def run():
    df = build_frame("data/stwa_asos.parquet")
    base = day_table(df)
    print(f"city-days: {len(base)}  train(<= {TRAIN_MAX_YEAR}): {int((base.year<=TRAIN_MAX_YEAR).sum())}"
          f"  test(>= {TRAIN_MAX_YEAR+1}): {int((base.year>TRAIN_MAX_YEAR).sum())}")

    for d in OFFSETS:
        Rc = f"R{d}"
        sub = base.dropna(subset=[Rc]).copy()
        sub["rr"] = (sub["M"] - sub[Rc]).clip(lower=0)   # remaining rise >= 0
        tr = sub[sub.year <= TRAIN_MAX_YEAR]
        te = sub[sub.year > TRAIN_MAX_YEAR]
        if len(te) < 50:
            continue
        # TRAIN cells: empirical remaining_rise samples per (city, season); global fallback
        cells = {k: v["rr"].values for k, v in tr.groupby(["city", "season"]) if len(v) >= MIN_CELL}
        gpool = tr["rr"].values
        gmu, gsd = float(gpool.mean()), float(gpool.std() + 1e-6)

        be_emp = be_g = ll_emp = ll_g = 0.0
        tail_emp = tail_g = tail_real = 0.0   # P assigned to bin >=2 above R (the fade zone)
        fav_emp = fav_g = fav_real = 0.0      # favorite bin (round of R+median rr region)
        n = 0
        for _, r in te.iterrows():
            R = r[Rc]; actual = int(round(r["M"]))
            samp = cells.get((r["city"], r["season"]))
            if samp is None or len(samp) < MIN_CELL:
                samp = gpool
            mu = float(samp.mean()); sd = float(samp.std() + 1e-6)
            cmin, cmax = int(np.floor(R - 1)), int(np.ceil(R + max(samp.max(), gmu + 4*gsd)) + 1)
            pe, pg = {}, {}
            ssort = np.sort(samp); N = len(ssort)
            for c in range(cmin, cmax + 1):
                lo, hi = c - 0.5 - R, c + 0.5 - R           # remaining-rise interval for bin c
                # empirical ECDF on remaining_rise
                pe_c = (np.searchsorted(ssort, hi, "right") - np.searchsorted(ssort, lo, "right")) / N
                pg_c = _ncdf(hi, mu, sd) - _ncdf(lo, mu, sd)
                if pe_c > 0: pe[c] = pe_c
                if pg_c > 1e-6: pg[c] = pg_c
            b1, l1, _ = brier_logloss(pe, actual); be_emp += b1; ll_emp += l1
            b2, l2, _ = brier_logloss(pg, actual); be_g += b2; ll_g += l2
            # tail zone = bins >= round(R)+2 ; favorite = round(R) .. (the settled bin)
            rr0 = int(round(R))
            te_p = sum(v for c, v in pe.items() if c >= rr0 + 2)
            tg_p = sum(v for c, v in pg.items() if c >= rr0 + 2)
            tail_emp += te_p / (sum(pe.values()) or 1); tail_g += tg_p / (sum(pg.values()) or 1)
            tail_real += 1.0 if actual >= rr0 + 2 else 0.0
            n += 1
        print(f"\n=== decision = peak{d:+d}h  (n_test={n}, train cells={len(cells)}) ===")
        print(f"  Brier   empirical={be_emp/n:.4f}   gaussian={be_g/n:.4f}   "
              f"{'EMP wins' if be_emp<be_g else 'gauss wins'} ({100*(be_g-be_emp)/be_g:+.1f}%)")
        print(f"  LogLoss empirical={ll_emp/n:.4f}   gaussian={ll_g/n:.4f}")
        print(f"  TAIL P(bin>=R+2): empirical={tail_emp/n:.3f}  gaussian={tail_g/n:.3f}  REALIZED={tail_real/n:.3f}"
              f"   (gaussian over-weights tail by {100*((tail_g/n)-(tail_real/n))/max(tail_real/n,1e-3):+.0f}% vs realized)")


if __name__ == "__main__":
    run()
