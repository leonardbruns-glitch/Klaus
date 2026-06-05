"""WHAT / WHEN / WHY we buy YES — hypothesis-tested on 51 clean cities.

EV needs a price; we don't have a 4yr Polymarket ask series, so this tests the SKILL
side (the upper bound on exploitable edge + the driver of Sharpe) cleanly and large-n,
and frames EV/Sharpe from it. Truth = clean ASOS daily max. Forecast = gfs (US from
stwa_nwp.parquet, non-US from stwa_nwp_gfs_global.parquet). Pricer = the validated
skew-routed dist + β_h center + σ_h shrink (stwa_matrix_kelly).

Hypotheses:
  H1 (WHEN):  single-bucket WR rises with proximity to peak (info accrues post-11am).
  H2 (WHAT):  mode±1 BAND WR >> single-bucket WR (horse-race beats the point bet).
  H3 (CALIB): model claimed-p ≈ realized WR (no residual overconfidence post-fix).
  H4 (LIFT):  WR beats persistence (yesterday's bucket) — there is real forecast signal.
  H5 (WHERE): per-city peak WR tiers cities into tradable vs skip.
Sharpe proxy: for a unit YES bet that pays (1−ask) on win / −ask on loss, with the
edge held fixed, per-bet Sharpe ∝ WR-driven; we report WR and the variance term so the
Sharpe ranking by hour/band is explicit.

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.yes_strategy_ht
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from analysis.weather.stations import STATIONS
from analysis.weather.stwa_matrix_kelly import make_dist, beta_h, shrink_sigma, CITY_DIST

HOURS = [9, 11, 13, 15]


def is_us(icao): return icao.startswith("K") and len(icao) == 4
def c2f(c): return c * 9 / 5 + 32


def _vec_bucket_p(city, mu, sigma, lo_c, hi_c):
    """Vectorised P(bucket) for the city's law with mean=μ (array), std=σ (scalar)."""
    from scipy import stats
    cfg = CITY_DIST.get(city, {"dist": "norm"})
    kind = cfg["dist"]
    if kind == "gumbel_l":
        scale = sigma * np.sqrt(6) / np.pi
        loc = mu + scale * 0.5772156649
        return stats.gumbel_l.cdf(hi_c, loc=loc, scale=scale) - stats.gumbel_l.cdf(lo_c, loc=loc, scale=scale)
    if kind == "skewnorm":
        a = cfg["alpha"]; delta = a / np.sqrt(1 + a*a)
        sf = np.sqrt(1 - 2*delta*delta/np.pi); scale = sigma / sf
        loc = mu - scale * delta * np.sqrt(2/np.pi)
        return stats.skewnorm.cdf(hi_c, a, loc=loc, scale=scale) - stats.skewnorm.cdf(lo_c, a, loc=loc, scale=scale)
    return stats.norm.cdf(hi_c, loc=mu, scale=sigma) - stats.norm.cdf(lo_c, loc=mu, scale=sigma)


def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z*z/n
    c = (p + z*z/(2*n))/d; h = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (c-h, c+h)


def main():
    asos = pd.read_parquet("data/stwa_asos.parquet", columns=["city", "time_utc", "temp_c"])
    nwp_us = pd.read_parquet("data/stwa_nwp.parquet", columns=["city", "time_utc", "temp_nwp_c"])
    nwp_gl = pd.read_parquet("data/stwa_nwp_gfs_global.parquet", columns=["city", "time_utc", "temp_nwp_c"])

    # accumulators: hour -> lists
    modal_win = {h: [] for h in HOURS}
    band_win = {h: [] for h in HOURS}
    claimed = {h: [] for h in HOURS}
    persist_win = []
    city_peak = {}                                   # city -> (modal_wins, n) at h=15

    for city, st in STATIONS.items():
        if city not in CITY_DIST:
            continue
        nwp = nwp_us if is_us(st.icao) else nwp_gl
        unit_f = (st.unit == "F"); width = 2 if unit_f else 1     # market bucket width
        a = asos[asos.city == city].set_index("time_utc")["temp_c"].sort_index().tz_convert(ZoneInfo(st.tz))
        n = nwp[nwp.city == city].dropna(subset=["temp_nwp_c"]).set_index("time_utc")["temp_nwp_c"].sort_index().tz_convert(ZoneInfo(st.tz))
        amax = a.groupby(a.index.normalize()).max()
        nmax = n.groupby(n.index.normalize()).max()
        # per-month forecast bias (so center is debiased like the live engine)
        j = pd.concat({"a": amax, "n": nmax}, axis=1).dropna()
        if len(j) < 150:
            continue
        j["mo"] = j.index.month
        bias = (j["a"] - j["n"]).groupby(j["mo"]).transform("mean")
        # hourly aligned obs/forecast for the intraday residual
        af = pd.concat({"obs": a, "fc": n}, axis=1).dropna()
        af["day"] = af.index.normalize(); af["h"] = af.index.hour

        # persistence baseline: yesterday's actual bucket == today's?
        av = j["a"].to_numpy()
        for i in range(1, len(av)):
            persist_win.append(1 if abs(round(av[i]) - round(av[i-1])) < width else 0)

        for h in HOURS:
            sub = af[af["h"] == h]
            e = (sub["obs"] - sub["fc"]); e.index = sub["day"]
            day_e = pd.concat({"e": e, "nmax": j["n"], "amax": j["a"], "bias": bias}, axis=1).dropna()
            if day_e.empty:
                continue
            b = beta_h(h)
            sigma = shrink_sigma(CITY_DIST[city]["sigma"], h)
            mu = (day_e["nmax"] + day_e["bias"] + b * day_e["e"]).to_numpy()   # °C, per day
            act = day_e["amax"].to_numpy()
            mu_nat = c2f(mu) if unit_f else mu
            act_nat = c2f(act) if unit_f else act
            # market bucket id = floor(x/width); modal bucket = the one containing μ
            pred_id = np.floor(mu_nat / width)
            act_id = np.floor(act_nat / width)
            diff = np.abs(pred_id - act_id)
            modal_win[h].extend((diff == 0).astype(int).tolist())
            band_win[h].extend((diff <= 1).astype(int).tolist())
            # claimed p of the modal bucket (vectorised, per-city law via loc-array)
            lo_nat = pred_id * width; hi_nat = lo_nat + width
            lo_c = (lo_nat - 32) * 5 / 9 if unit_f else lo_nat
            hi_c = (hi_nat - 32) * 5 / 9 if unit_f else hi_nat
            claimed[h].extend(_vec_bucket_p(city, mu, sigma, lo_c, hi_c).tolist())
            if h == 15:
                w, c = city_peak.get(city, (0, 0))
                city_peak[city] = (w + int((diff == 0).sum()), c + len(diff))

    print("=== H1/H2/H3: WR by local hour (pooled 51 cities) ===")
    print(f"  {'hour':>4} {'n':>6} {'WR_single':>10} {'95% CI':>16} {'WR_band±1':>10} "
          f"{'band CI':>16} {'claimed_p':>9} {'calib_gap':>9}")
    for h in HOURS:
        n_ = len(modal_win[h])
        ws, wb = np.mean(modal_win[h]), np.mean(band_win[h])
        cl = np.mean(claimed[h])
        cis = wilson(sum(modal_win[h]), n_); cib = wilson(sum(band_win[h]), n_)
        print(f"  {h:>4} {n_:>6} {ws:>10.3f} [{cis[0]:.3f},{cis[1]:.3f}] {wb:>10.3f} "
              f"[{cib[0]:.3f},{cib[1]:.3f}] {cl:>9.3f} {cl-ws:>+9.3f}")
    pw = np.mean(persist_win)
    print(f"\n  H4 persistence baseline (single-bucket): WR={pw:.3f}  n={len(persist_win)}")
    print(f"     -> peak-hour single-bucket lift over persistence: "
          f"{np.mean(modal_win[15])-pw:+.3f}")

    print("\n=== H5: per-city peak (h=15) single-bucket WR — tiering ===")
    rows = [(w/c, c, city) for city, (w, c) in city_peak.items() if c >= 100]
    rows.sort(reverse=True)
    print("  TOP (tradable, sharp):")
    for wr, c, city in rows[:8]:
        print(f"    {city:14} WR={wr:.3f}  σ={CITY_DIST[city]['sigma']:.2f}  n={c}")
    print("  BOTTOM (skip / too noisy):")
    for wr, c, city in rows[-8:]:
        print(f"    {city:14} WR={wr:.3f}  σ={CITY_DIST[city]['sigma']:.2f}  n={c}")


if __name__ == "__main__":
    main()
