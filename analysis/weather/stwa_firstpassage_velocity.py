#!/usr/bin/env python3
"""
stwa_firstpassage_velocity.py — READ-ONLY research (P2 Stage-1).

THESIS: the daily-max question is a FIRST-PASSAGE / record problem. The engine
prices buckets from ONE static CDF (center+sigma) over POSITION only, and DISCARDS
the velocity dT/dt it already computes. If the instantaneous tendency carries
information about the remaining rise BEYOND (current temp, time-of-day), then the
static-CDF pricer is structurally mispriced in the grey zone — and that is the
make-or-break for the whole proposal.

DESIGN (apples-to-apples ablation; the ONLY difference between the two models is
whether velocity is in the feature set):
  target  Y = remaining_rise_steps = daily_max_int - current_int_max  (>=0 integer)
             (the bucket the day's max lands in, in integer steps above now)
  also    R = 1[Y >= 1]  (a new record above the current running-max bucket)
  cells   POSITION+TIME = (hour_to_climpeak, climatological headroom) bins
  model B1 (velocity-BLIND): P(Y | cell)
  model M  (velocity-AWARE): P(Y | cell, v_now bin)
  anchor B0 (Gaussian static CDF): N(center, sigma) differenced into integer steps
Train on 2021-2023, score multiclass Brier + log-loss on held-out 2024, overall and
in the POST-PEAK grey zone. Mechanism check: P(new record) by velocity sign within
position/time cells. Conservative: hourly velocity is coarser than the live feed, so
any signal here is a lower bound on what's exploitable live.

Run: python3 analysis/weather/stwa_firstpassage_velocity.py
"""
import sys, math
import numpy as np
import pandas as pd

sys.path.insert(0, "analysis/weather")
from stations import STATIONS  # city -> Station(.unit, .tz)

ASOS = "data/stwa_asos.parquet"
TRAIN_YEARS = {2021, 2022, 2023}
TEST_YEAR = 2024
STEP_CAP = 3          # remaining-rise steps capped at {0,1,2,3+}
V_BINS = [-99, -0.75, -0.25, 0.25, 0.75, 99]   # velocity (deg/hr) bins
V_LBL = ["<<0", "-", "~0", "+", ">>0"]
DECISION_HOURS = range(10, 20)  # local decision hours to evaluate


def to_unit(temp_c, unit):
    return temp_c * 9.0 / 5.0 + 32.0 if unit == "F" else temp_c


def build_decision_table():
    df = pd.read_parquet(ASOS, columns=["city", "time_utc", "temp_c"])
    rows = []
    for city, g in df.groupby("city", sort=False):
        st = STATIONS.get(city)
        if st is None or not st.tz:
            continue
        unit = st.unit
        loc = g["time_utc"].dt.tz_convert(st.tz)
        t = to_unit(g["temp_c"].values, unit)
        d = pd.DataFrame({"ldate": loc.dt.date.values,
                          "lhour": loc.dt.hour.values,
                          "month": loc.dt.month.values,
                          "T": t})
        # one obs per (day,hour): the hourly max (closest to METAR hourly semantics)
        d = d.groupby(["ldate", "lhour"], as_index=False).agg(
            T=("T", "max"), month=("month", "first"))
        for ldate, day in d.groupby("ldate", sort=False):
            day = day.set_index("lhour").reindex(range(0, 24))
            T = day["T"]
            if T.notna().sum() < 18:
                continue
            dmax = np.nanmax(T.values)
            dmax_int = int(round(dmax))
            month = int(np.nanmedian(day["month"].values))
            peak_hour = int(np.nanargmax(np.where(np.isnan(T.values), -1e9, T.values)))
            runmax = T.cummax()
            for h in DECISION_HOURS:
                tnow, tprev, rm = T.get(h), T.get(h - 1), runmax.get(h)
                if pd.isna(tnow) or pd.isna(tprev) or pd.isna(rm):
                    continue
                cur_int = int(round(rm))
                steps = dmax_int - cur_int
                if steps < 0:
                    steps = 0
                rows.append((city, unit, ldate.year, month, h, peak_hour,
                             float(tnow), float(tnow - tprev), float(rm),
                             cur_int, min(steps, STEP_CAP), dmax_int))
    return pd.DataFrame(rows, columns=[
        "city", "unit", "year", "month", "lhour", "peak_hour",
        "Tnow", "v", "runmax", "cur_int", "steps", "dmax_int"])


def add_climatology(df):
    tr = df[df.year.isin(TRAIN_YEARS)]
    cpk = tr.groupby(["city", "month"]).agg(
        clim_peak=("peak_hour", "mean"),
        clim_dmax=("dmax_int", "mean")).reset_index()
    df = df.merge(cpk, on=["city", "month"], how="left")
    df = df.dropna(subset=["clim_peak", "clim_dmax"])
    df["htp"] = np.clip(np.round(df.lhour - df.clim_peak), -4, 4).astype(int)
    df["hroom"] = np.clip(np.round(df.clim_dmax - df.runmax), -1, 5).astype(int)
    df["vbin"] = pd.cut(df.v, V_BINS, labels=V_LBL).astype(str)
    return df


def fit_pmf(train, keys):
    """Conditional pmf of steps given the key columns (Laplace-smoothed)."""
    tab = (train.groupby(keys + ["steps"]).size()
           .unstack("steps", fill_value=0).reindex(columns=range(STEP_CAP + 1), fill_value=0))
    tab = tab + 0.5
    pmf = tab.div(tab.sum(axis=1), axis=0)
    return pmf, train.groupby(keys).size()


def predict(df, pmf, keys, global_pmf):
    idx = list(zip(*[df[k] for k in keys])) if len(keys) > 1 else list(df[keys[0]])
    out = np.tile(global_pmf, (len(df), 1))
    pmf_idx = set(pmf.index)
    P = pmf.values
    pos = {k: i for i, k in enumerate(pmf.index)}
    for r, k in enumerate(idx):
        if k in pmf_idx:
            out[r] = P[pos[k]]
    return out


def gaussian_pmf(df, sigma):
    """B0 anchor: static normal over remaining-rise, center = climatological headroom."""
    mu = np.clip(df.clim_dmax.values - df.runmax.values, 0, None)
    out = np.zeros((len(df), STEP_CAP + 1))
    for k in range(STEP_CAP + 1):
        lo = k - 0.5 if k > 0 else -np.inf
        hi = k + 0.5 if k < STEP_CAP else np.inf
        out[:, k] = _ncdf(hi, mu, sigma) - _ncdf(lo, mu, sigma)
    out = np.clip(out, 1e-6, None)
    return out / out.sum(axis=1, keepdims=True)


def _ncdf(x, mu, s):
    if np.isinf(x):
        return 1.0 if x > 0 else 0.0
    return 0.5 * (1 + np.vectorize(math.erf)((x - mu) / (s * math.sqrt(2))))


def brier(P, y):
    Y = np.zeros_like(P)
    Y[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def logloss(P, y):
    return float(np.mean(-np.log(np.clip(P[np.arange(len(y)), y], 1e-9, 1))))


def main():
    print("building decision table from", ASOS, "...", flush=True)
    df = build_decision_table()
    df = add_climatology(df)
    tr, te = df[df.year.isin(TRAIN_YEARS)], df[df.year == TEST_YEAR]
    print(f"rows: train={len(tr):,}  test={len(te):,}  cities={df.city.nunique()}")
    gpmf = (tr.groupby("steps").size().reindex(range(STEP_CAP + 1), fill_value=1)).values.astype(float)
    gpmf = gpmf / gpmf.sum()

    # ── mechanism check: post-peak grey zone, P(new record) by velocity sign ──
    gz = te[(te.htp >= 0) & (te.htp <= 3) & (te.hroom.between(0, 2))].copy()
    gz["newrec"] = (gz.steps >= 1).astype(int)
    print("\n=== MECHANISM (held-out 2024, post-peak grey zone htp∈[0,3], hroom∈[0,2]) ===")
    print(f"  n={len(gz):,}   overall P(new record)={gz.newrec.mean():.3f}")
    print("  P(new record) by velocity bin (same time/position regime):")
    for vb in V_LBL:
        s = gz[gz.vbin == vb]
        if len(s) >= 50:
            print(f"    v {vb:>3}: n={len(s):>5}  P(new record)={s.newrec.mean():.3f}")
    # within fixed (htp,hroom) cells, falling vs rising
    fall = gz[gz.v < -0.25].newrec.mean()
    rise = gz[gz.v > 0.25].newrec.mean()
    print(f"  falling(v<-0.25)={fall:.3f}  vs  rising(v>0.25)={rise:.3f}  "
          f"Δ={rise - fall:+.3f}")

    # ── predictive ablation: B0 Gaussian / B1 blind / M velocity-aware ──
    B1, _ = fit_pmf(tr, ["htp", "hroom"])
    M, cnt = fit_pmf(tr, ["htp", "hroom", "vbin"])
    yte = te.steps.values.astype(int)
    P_B0 = gaussian_pmf(te, sigma=1.1)
    P_B1 = predict(te, B1, ["htp", "hroom"], gpmf)
    P_M = predict(te, M, ["htp", "hroom", "vbin"], gpmf)

    print("\n=== PREDICTIVE ABLATION (multiclass remaining-steps, held-out 2024) ===")
    print(f"  {'model':<28}{'Brier':>10}{'logloss':>10}")
    for name, P in [("B0 Gaussian static-CDF", P_B0),
                    ("B1 empirical (vel-BLIND)", P_B1),
                    ("M  empirical (vel-AWARE)", P_M)]:
        print(f"  {name:<28}{brier(P, yte):>10.4f}{logloss(P, yte):>10.4f}")
    dB = brier(P_B1, yte) - brier(P_M, yte)
    dL = logloss(P_B1, yte) - logloss(P_M, yte)
    print(f"  velocity gain  ΔBrier={dB:+.4f}  Δlogloss={dL:+.4f}  "
          f"({'HELPS' if dB > 0 else 'no gain'})")

    # grey-zone-only ablation (where the thesis is sharpest)
    mask = ((te.htp >= 0) & (te.htp <= 3) & (te.hroom.between(0, 2))).values
    if mask.sum() > 200:
        print(f"\n  -- POST-PEAK GREY ZONE only (n={mask.sum():,}) --")
        for name, P in [("B1 vel-BLIND", P_B1[mask]), ("M vel-AWARE", P_M[mask])]:
            print(f"  {name:<28}{brier(P, yte[mask]):>10.4f}{logloss(P, yte[mask]):>10.4f}")
        dBg = brier(P_B1[mask], yte[mask]) - brier(P_M[mask], yte[mask])
        print(f"  velocity gain (grey zone) ΔBrier={dBg:+.4f}  "
              f"({'HELPS' if dBg > 0 else 'no gain'})")


if __name__ == "__main__":
    main()
