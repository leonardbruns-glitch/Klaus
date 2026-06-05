"""When to use Gumbel vs Gaussian, and when/how much Kalman — scored by EV proxy.

Runs on the 11 CLEAN full-coverage gfs cities (US). Non-US NWP in the parquet is
ifs025 @23% (null-poisoned) — excluded; extending needs a full-coverage NWP backfill.

Truth = clean ASOS daily max (local-day). Forecast = gfs ensemble daily max.

PART A — distribution shape of the forecast residual r = actual_max − forecast_max:
  * skew + GEV shape ξ (genextreme): ξ<0 => BOUNDED tail (reverse-Weibull), ξ≈0 => Gumbel,
    ξ>0 => fat tail. Decides whether a skewed law is even warranted.
  * OUT-OF-SAMPLE scoring (time-split): fit each law on train residuals, price whole-°F
    buckets on test days, score by LOG-LOSS + BRIER vs the realized bucket. Lowest = best
    calibrated = best EV. Compares Normal / Gumbel-R / Gumbel-L / Skew-Normal.

PART B — Kalman gain schedule: at each local hour h, regress the FINAL residual
  (actual_max − forecast_max) on the obs-so-far residual e_h = obs(h) − forecast(h).
  slope β_h = optimal Kalman gain at hour h; R²_h = variance it explains. Tells us WHEN an
  intraday update adds EV (high R²) vs injects noise (low R²), and HOW MUCH to trust it (β_h).

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.dist_kalman_ev
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from zoneinfo import ZoneInfo

from analysis.weather.stations import STATIONS

ASOS = "data/stwa_asos.parquet"
NWP = "data/stwa_nwp.parquet"
GFS_CITIES = ["nyc", "chicago", "los-angeles", "miami", "san-francisco",
              "dallas", "houston", "seattle", "denver", "atlanta", "austin"]
LOCAL_HOURS = [7, 9, 11, 13, 15]      # morning -> peak (US diurnal peak ~14-16 local)


def c2f(c):
    return c * 9 / 5 + 32


def _series(df, tz, col):
    s = df.set_index("time_utc")[col].sort_index()
    return s.tz_convert(ZoneInfo(tz))


def load_city(asos, nwp, city):
    st = STATIONS[city]
    a = _series(asos[asos.city == city], st.tz, "temp_c")
    n = nwp[(nwp.city == city)].dropna(subset=["temp_nwp_c"])
    nser = _series(n, st.tz, "temp_nwp_c")
    # daily max (>=12 hourly obs)
    aday = a.groupby(a.index.normalize())
    nday = nser.groupby(nser.index.normalize())
    amax = aday.max()[aday.count() >= 12]
    nmax = nday.max()[nday.count() >= 12]
    joined = pd.concat({"amax": amax, "nmax": nmax}, axis=1).dropna()
    # debias per month
    joined["resid"] = joined["amax"] - joined["nmax"]
    joined["mo"] = joined.index.month
    joined["resid_db"] = joined["resid"] - joined.groupby("mo")["resid"].transform("mean")
    return st, a, nser, joined


def bucket_logloss(train_r, test_center, test_actual, dist):
    """Fit `dist` to train residuals; score whole-°F buckets on test days."""
    if dist == "norm":
        loc, sc = stats.norm.fit(train_r); cdf = lambda x: stats.norm.cdf(x, loc, sc)
    elif dist == "gumbel_r":
        loc, sc = stats.gumbel_r.fit(train_r); cdf = lambda x: stats.gumbel_r.cdf(x, loc, sc)
    elif dist == "gumbel_l":
        loc, sc = stats.gumbel_l.fit(train_r); cdf = lambda x: stats.gumbel_l.cdf(x, loc, sc)
    elif dist == "skewnorm":
        a_, loc, sc = stats.skewnorm.fit(train_r); cdf = lambda x: stats.skewnorm.cdf(x, a_, loc, sc)
    ll, brier, n = 0.0, 0.0, 0
    for C, A in zip(test_center, test_actual):
        k = int(round(A))
        # residual needed for actual to land in bucket k = [k-0.5, k+0.5] given center C
        p_k = max(1e-9, cdf((k + 0.5) - C) - cdf((k - 0.5) - C))
        ll += -np.log(p_k)
        # brier over a ±4°F window
        for j in range(k - 4, k + 5):
            p_j = max(0.0, cdf((j + 0.5) - C) - cdf((j - 0.5) - C))
            brier += (p_j - (1.0 if j == k else 0.0)) ** 2
        n += 1
    return ll / n, brier / n


def main():
    asos = pd.read_parquet(ASOS, columns=["city", "time_utc", "temp_c"])
    nwp = pd.read_parquet(NWP, columns=["city", "time_utc", "temp_nwp_c"])

    print("=== PART A: residual shape + OOS bucket scoring (°F, time-split 70/30) ===")
    print(f"{'city':13} {'n':>5} {'skew':>6} {'GEV_ξ':>7} {'σ°F':>5}  "
          f"{'LL_norm':>8} {'LL_gumR':>8} {'LL_gumL':>8} {'LL_skew':>8}  best")
    pooledA = []
    for city in GFS_CITIES:
        st, a, nser, j = load_city(asos, nwp, city)
        if len(j) < 200:
            continue
        rF = c2f(j["amax"].to_numpy()) - c2f(j["nmax"].to_numpy())   # residual in °F
        rF = rF - rF.mean()
        skew = float(stats.skew(rF))
        xi = float(stats.genextreme.fit(rF)[0])     # scipy shape c = -ξ; report -c as ξ
        xi = -xi
        # time split
        cF = c2f(j["nmax"].to_numpy()); aF = c2f(j["amax"].to_numpy())
        cut = int(len(j) * 0.7)
        trn = (aF[:cut] - cF[:cut]); trn = trn - trn.mean()
        teC, teA = cF[cut:], aF[cut:]
        res = {}
        for d in ("norm", "gumbel_r", "gumbel_l", "skewnorm"):
            try:
                res[d] = bucket_logloss(trn, teC, teA, d)[0]
            except Exception:
                res[d] = float("nan")
        best = min(res, key=lambda k: res[k])
        pooledA.append((city, res, best))
        print(f"{city:13} {len(j):5d} {skew:+6.2f} {xi:+7.2f} {rF.std():5.2f}  "
              f"{res['norm']:8.4f} {res['gumbel_r']:8.4f} {res['gumbel_l']:8.4f} "
              f"{res['skewnorm']:8.4f}  {best}")
    wins = {}
    for _, res, best in pooledA:
        wins[best] = wins.get(best, 0) + 1
    print(f"\n  best-law tally across {len(pooledA)} cities: {wins}")
    # how much does the best beat normal, on avg?
    gains = [res['norm'] - min(res.values()) for _, res, _ in pooledA]
    print(f"  mean log-loss improvement of best vs Normal: {np.mean(gains):.4f} "
          f"(>0.01 = materially better; ~0 = Normal is fine)")

    print("\n=== PART B: Kalman gain schedule β_h + R² (pooled gfs cities) ===")
    print(f"  e_h = obs(h) − forecast(h);  final residual = actual_max − forecast_max")
    print(f"  {'local_h':>7} {'n':>5} {'β_h(gain)':>10} {'R²':>6} {'corr':>6}  read")
    # build per (city,day): final residual + e_h at each hour
    by_hour = {h: ([], []) for h in LOCAL_HOURS}
    for city in GFS_CITIES:
        st, a, nser, j = load_city(asos, nwp, city)
        if len(j) < 200:
            continue
        # align obs & forecast hourly in local time
        af = pd.concat({"obs": a, "fc": nser}, axis=1).dropna()
        af["day"] = af.index.normalize()
        af["h"] = af.index.hour
        fin = (j["amax"] - j["nmax"])      # final residual per day (index = normalized day)
        for h in LOCAL_HOURS:
            sub = af[af["h"] == h]
            e = (sub["obs"] - sub["fc"])
            e.index = sub["day"]
            m = pd.concat({"e": e, "fin": fin}, axis=1).dropna()
            if len(m):
                by_hour[h][0].extend(m["e"].tolist())
                by_hour[h][1].extend(m["fin"].tolist())
    for h in LOCAL_HOURS:
        e = np.array(by_hour[h][0]); f = np.array(by_hour[h][1])
        if len(e) < 50:
            continue
        sl, ic, r, p, se = stats.linregress(e, f)
        read = ("strong — update here" if r**2 > 0.25 else
                "weak — mostly noise" if r**2 < 0.10 else "moderate")
        print(f"  {h:7d} {len(e):5d} {sl:10.2f} {r**2:6.2f} {r:+6.2f}  {read}")
    print("\n  β_h is the EV-optimal shrink on the morning anomaly at hour h; the engine's")
    print("  fixed β≈0.30 should match the high-R² (near-peak) rows, not the noisy early ones.")


if __name__ == "__main__":
    main()
