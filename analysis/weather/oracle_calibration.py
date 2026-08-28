"""Per-station oracle / pricer calibration over the 5-yr ASOS history.

SCOPE — read this before trusting any number it prints.
--------------------------------------------------------
This runs OFFLINE on data/stwa_asos.parquet (hourly ASOS, 2021-2024, 51 cities)
+ data/stwa_nwp.parquet (GFS/IFS hourly). It does NOT scrape Weather Underground
and does NOT see Gamma/UMA settlement. That has three consequences, stated up
front so the output is not over-read (DATA PRIMACY / anti-sycophancy):

  * The WU daily high IS max(official hourly METAR/SPECI). It is a deterministic
    function of the METAR feed, not an independent sensor. So a true "oracle minus
    physical sensor" bias is NOT measurable here. What IS measurable offline:
      (A) DISCRETIZATION residual — how whole-degree rounding in the market's unit
          (incl. F<->C conversion rounding) shifts the resolved value vs the
          continuous physical max. This is the one real, deterministic oracle
          effect we can isolate without a scrape.
      (B) FORECAST residual — observed daily high minus NWP-predicted daily high.
          This is the pricer's actual error and the thing sigma_calibrated must
          size. It is what skill_matrix.json already encodes; we recompute it here
          per (city, local-day) and fit Gaussian + Gumbel.
  * The "Ghost Station" metric here is an ANOMALY proxy: |observed_high - NWP_high|
    > 2 C. With a live WU scrape it would be |WU - ASOS|; offline it also catches
    genuine forecast busts, so treat it as an upper bound on true site-mismatch.
  * Rounding CONVENTION (floor/ceil/nearest) cannot be determined offline — it
    needs the live join. We report what each convention WOULD imply and defer the
    verdict to resolution_bias_backtest.py --mechanism at n>=100.

Tier boundaries follow the requested spec, but the tier is a SIGMA BAND that feeds
Kelly sizing — NOT a capital green-light. Enabling aggressive deployment on a Tier-1
city is a Tier-3 action (never autonomous).

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.oracle_calibration
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.oracle_calibration --city nyc --verbose
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.oracle_calibration --out config/oracle_calibration.json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy import stats

from analysis.weather.stations import STATIONS

ASOS_PARQUET = "data/stwa_asos.parquet"
NWP_PARQUET = "data/stwa_nwp.parquet"
SKILL_MATRIX = "strategy/skill_matrix.json"

# Tier boundaries (spec). Applied to the FORECAST-residual RMSE (channel B), the
# stat that actually governs pricer sigma. Ghost = anomaly-rate proxy.
TIER1_RMSE = 0.4
TIER2_RMSE = 0.8
GHOST_TIER3_PCT = 2.0          # anomaly rate above this -> Tier 3 regardless of RMSE
MBE_TIER1_MAX = 0.15           # |MBE| under this counts as "near zero"
ANOMALY_THRESH_C = 2.0         # |obs - nwp| above this = anomaly/"ghost" event
MISMATCH_LOG_C = 1.5           # log any day with |forecast residual| over this
SIGMA_FLOOR = 0.3              # matches skill_matrix.json sigma_floor
MIN_N = 100                    # n>=100 gate (CLAUDE.md) before a tier is trusted


def skillmatrix_sigma(city: str) -> float | None:
    """Fallback forecast sigma: median NWP-model sigma across months from the
    clean-ASOS-calibrated skill_matrix. Used where the local NWP parquet is
    null-poisoned (ecmwf_ifs025 is only ~23% populated for non-US cities)."""
    try:
        st = json.load(open(SKILL_MATRIX))["stations"].get(city, {})
    except Exception:
        return None
    sigmas = []
    for model, months in st.items():
        if model.startswith("_") or not isinstance(months, dict):
            continue
        for m, rec in months.items():
            if isinstance(rec, dict) and isinstance(rec.get("sigma"), (int, float)):
                sigmas.append(rec["sigma"])
    return float(np.median(sigmas)) if sigmas else None


def c_to_f(c: np.ndarray | float):
    return c * 9.0 / 5.0 + 32.0


def f_to_c(f: np.ndarray | float):
    return (f - 32.0) * 5.0 / 9.0


def oracle_read_c(physical_c: np.ndarray, unit: str, mode: str = "nearest") -> np.ndarray:
    """Value the oracle would PRINT, expressed back in C, under a rounding mode.

    F markets: round the F value to a whole degree, convert back to C.
    C markets: round the C value to a whole degree.
    mode in {nearest, floor, ceil}.
    """
    rounder = {"nearest": np.round, "floor": np.floor, "ceil": np.ceil}[mode]
    if unit == "F":
        return f_to_c(rounder(c_to_f(physical_c)))
    return rounder(physical_c)


@dataclass
class StationCalib:
    city: str
    icao: str
    unit: str
    n_days: int
    # channel A — discretization / unit-rounding (the only offline "oracle" effect)
    disc_mbe_c: float           # mean(oracle_read - physical), nearest rounding
    disc_rmse_c: float
    disc_floor_mbe_c: float     # what floor convention would imply
    disc_ceil_mbe_c: float      # what ceil convention would imply
    # channel B — forecast residual (feeds pricer sigma)
    fc_mbe_c: float             # mean(obs_high - nwp_high) -> warm/cool bias
    fc_rmse_c: float
    fc_sigma_gauss_c: float     # scipy norm.fit scale on residual
    gumbel_loc_c: float         # daily-high extreme-value fit (max-type)
    gumbel_scale_c: float
    sigma_calibrated_c: float   # max(sigma_floor, gauss sigma) -> integration loop
    sigma_source: str           # "nwp_residual" | "skill_matrix" | "floor"
    # ghost / anomaly proxy
    ghost_pct: float            # % days |obs - nwp| > 2 C
    ghost_n: int
    # classification
    tier: int
    tier_reason: str
    n_gate_met: bool


def _local_daily_high(df: pd.DataFrame, tz: str) -> pd.Series:
    """Daily max temp_c on the STATION-LOCAL calendar day (midnight-midnight)."""
    s = df.set_index("time_utc")["temp_c"].sort_index()
    local = s.tz_convert(ZoneInfo(tz)) if tz else s
    # group by local calendar date; require a usable diurnal sample
    grp = local.groupby(local.index.normalize())
    daily = grp.max()
    counts = grp.count()
    return daily[counts >= 12]            # >=12 hourly obs -> peak window covered


def calibrate_station(city: str, asos: pd.DataFrame, nwp: pd.DataFrame) -> StationCalib | None:
    st = STATIONS.get(city)
    if st is None:
        return None
    a = asos[asos.city == city]
    if a.empty:
        return None

    obs_high = _local_daily_high(a, st.tz)
    if obs_high.empty:
        return None

    # --- channel A: discretization residual on the observed physical high ---
    phys = obs_high.to_numpy()
    read_near = oracle_read_c(phys, st.unit, "nearest")
    read_floor = oracle_read_c(phys, st.unit, "floor")
    read_ceil = oracle_read_c(phys, st.unit, "ceil")
    disc = read_near - phys
    disc_mbe = float(np.mean(disc))
    disc_rmse = float(np.sqrt(np.mean(disc ** 2)))

    # --- channel B: forecast residual obs - nwp (per local day, ensemble-mean NWP) ---
    # CRITICAL: ecmwf_ifs025 (every non-US city in the parquet) is only ~23%
    # populated -> drop nulls, then require a real n>=MIN_N of joined days before
    # trusting any forecast stat. Otherwise channel B is left UNAVAILABLE and we
    # do NOT invent a skill/tier from null-poisoned data.
    n = nwp[nwp.city == city]
    fc_mbe = fc_rmse = sigma_g = gum_loc = gum_scale = float("nan")
    ghost_pct = float("nan")
    ghost_n = 0
    resid = np.array([])
    nwp_trusted = False
    if not n.empty:
        coverage = float(n["temp_nwp_c"].notna().mean())   # full-period populated frac
        n = n.dropna(subset=["temp_nwp_c"])
        nwp_mean = (n.groupby("time_utc")["temp_nwp_c"].mean().to_frame("temp_c")
                    .reset_index())
        nwp_high = _local_daily_high(nwp_mean.assign(city=city), st.tz)
        joined = pd.concat({"obs": obs_high, "nwp": nwp_high}, axis=1).dropna()
        # Trust channel B only on near-complete coverage. The partial-coverage
        # models (ecmwf_ifs025 ~23%) are seasonal hindcast subsets with a known
        # cold bias -> obs-nwp would read spuriously warm. Coverage, not row count.
        if coverage >= 0.80 and len(joined) >= MIN_N:
            nwp_trusted = True
            resid = (joined["obs"] - joined["nwp"]).to_numpy()
            fc_mbe = float(np.mean(resid))
            fc_rmse = float(np.sqrt(np.mean(resid ** 2)))
            sigma_g = float(stats.norm.fit(resid)[1])
            gum_loc, gum_scale = (float(x) for x in stats.gumbel_r.fit(resid))
            ghost_n = int(np.sum(np.abs(resid) > ANOMALY_THRESH_C))
            ghost_pct = 100.0 * ghost_n / len(resid)

    # sigma_calibrated: NWP residual if trusted, else clean-ASOS skill_matrix sigma,
    # else floor. Never derived from the null-poisoned join.
    if nwp_trusted:
        sigma_cal, sigma_source = max(SIGMA_FLOOR, sigma_g), "nwp_residual"
    else:
        sm = skillmatrix_sigma(city)
        sigma_cal = max(SIGMA_FLOOR, sm) if sm else SIGMA_FLOOR
        sigma_source = "skill_matrix" if sm else "floor"
    n_days = int(len(resid)) if nwp_trusted else int(len(obs_high))
    n_gate = nwp_trusted and n_days >= MIN_N

    # --- tiering on forecast-residual RMSE + anomaly rate (honest labels) ---
    if not nwp_trusted:                          # cannot score offline -> tier 0
        tier, reason = 0, ("NWP unavailable offline (ifs025 ~23% populated); "
                           "sigma from skill_matrix — tier deferred to live Gamma join")
    elif ghost_pct > GHOST_TIER3_PCT:
        tier, reason = 3, f"anomaly/ghost rate {ghost_pct:.1f}% > {GHOST_TIER3_PCT}%"
    elif fc_rmse > TIER2_RMSE:
        tier, reason = 3, f"forecast RMSE {fc_rmse:.2f}C > {TIER2_RMSE}C"
    elif fc_rmse > TIER1_RMSE or abs(fc_mbe) > MBE_TIER1_MAX:
        tier, reason = 2, (f"RMSE {fc_rmse:.2f}C in band / MBE {fc_mbe:+.2f}C "
                           f"-> static offset before book read")
    else:
        tier, reason = 1, f"RMSE {fc_rmse:.2f}C, MBE {fc_mbe:+.2f}C, ghost {ghost_pct:.1f}%"
    if not n_gate:
        reason += f" [n={n_days}<{MIN_N}: PROVISIONAL, do not act]"

    return StationCalib(
        city=city, icao=st.icao, unit=st.unit, n_days=n_days,
        disc_mbe_c=round(disc_mbe, 4), disc_rmse_c=round(disc_rmse, 4),
        disc_floor_mbe_c=round(float(np.mean(read_floor - phys)), 4),
        disc_ceil_mbe_c=round(float(np.mean(read_ceil - phys)), 4),
        fc_mbe_c=round(fc_mbe, 4) if fc_mbe == fc_mbe else None,
        fc_rmse_c=round(fc_rmse, 4) if fc_rmse == fc_rmse else None,
        fc_sigma_gauss_c=round(sigma_g, 4) if sigma_g == sigma_g else None,
        gumbel_loc_c=round(gum_loc, 4) if gum_loc == gum_loc else None,
        gumbel_scale_c=round(gum_scale, 4) if gum_scale == gum_scale else None,
        sigma_calibrated_c=round(sigma_cal, 4),
        sigma_source=sigma_source,
        ghost_pct=round(ghost_pct, 3) if ghost_pct == ghost_pct else None,
        ghost_n=ghost_n,
        tier=tier, tier_reason=reason, n_gate_met=n_gate,
    )


def log_mismatches(city: str, asos: pd.DataFrame, nwp: pd.DataFrame, thresh: float):
    """Print local-days where |obs_high - nwp_high| exceeds thresh, with variance."""
    st = STATIONS[city]
    obs = _local_daily_high(asos[asos.city == city], st.tz)
    n = nwp[nwp.city == city]
    if n.empty:
        return
    nwp_mean = n.groupby("time_utc")["temp_nwp_c"].mean().to_frame("temp_c").reset_index()
    nwp_high = _local_daily_high(nwp_mean.assign(city=city), st.tz)
    j = pd.concat({"obs": obs, "nwp": nwp_high}, axis=1).dropna()
    j["resid"] = j["obs"] - j["nwp"]
    bad = j[j["resid"].abs() > thresh].sort_values("resid", key=lambda s: s.abs(), ascending=False)
    for day, row in bad.head(20).iterrows():
        flag = "  <GHOST>" if abs(row.resid) > ANOMALY_THRESH_C else ""
        print(f"    {day.date()} obs={row.obs:6.2f}C nwp={row.nwp:6.2f}C "
              f"resid={row.resid:+.2f}C{flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="single city slug (default: all in ASOS)")
    ap.add_argument("--out", help="write structured JSON here")
    ap.add_argument("--verbose", action="store_true", help="print >1.5C mismatch days")
    args = ap.parse_args()

    asos = pd.read_parquet(ASOS_PARQUET)
    nwp = pd.read_parquet(NWP_PARQUET)
    cities = [args.city] if args.city else sorted(asos.city.unique())

    results: list[StationCalib] = []
    for city in cities:
        c = calibrate_station(city, asos, nwp)
        if c is None:
            continue
        results.append(c)

    # ---- report ----
    hdr = f"{'city':14} {'unit':4} {'n':>5} {'fc_MBE':>7} {'fc_RMSE':>7} {'sigma_cal':>9} {'ghost%':>7} {'tier':>4}"
    print(hdr)
    print("-" * len(hdr))
    for c in sorted(results, key=lambda x: (x.tier if x.tier else 99, -(x.fc_rmse_c or 9))):
        gate = "" if c.n_gate_met else "*"
        mbe = f"{c.fc_mbe_c:+.2f}" if c.fc_mbe_c is not None else "  n/a"
        rmse = f"{c.fc_rmse_c:.2f}" if c.fc_rmse_c is not None else " n/a"
        ghost = f"{c.ghost_pct:.2f}" if c.ghost_pct is not None else " n/a"
        tlab = str(c.tier) if c.tier else "-"
        print(f"{c.city:14} {c.unit:4} {c.n_days:5d}{gate:1} {mbe:>6} {rmse:>7} "
              f"{c.sigma_calibrated_c:9.3f} {ghost:>7} {tlab:>4}")
        if args.verbose and c.tier >= 2:
            print(f"      reason: {c.tier_reason}")
            log_mismatches(c.city, asos, nwp, MISMATCH_LOG_C)

    by_tier = {0: 0, 1: 0, 2: 0, 3: 0}
    for c in results:
        by_tier[c.tier] += 1
    print(f"\nTiers: T1={by_tier[1]} T2={by_tier[2]} T3={by_tier[3]} "
          f"unscored(no-NWP)={by_tier[0]}")

    # sigma_calibrated array for the integration loop
    sigma_array = {c.city: c.sigma_calibrated_c for c in results}
    disc_note = {c.city: {"nearest": c.disc_mbe_c, "floor": c.disc_floor_mbe_c,
                          "ceil": c.disc_ceil_mbe_c} for c in results}

    if args.out:
        payload = {
            "_meta": {
                "built_from": [ASOS_PARQUET, NWP_PARQUET],
                "span": "2021-2024 hourly ASOS, local-day windows",
                "scope": "OFFLINE: discretization (A) + forecast residual (B); "
                         "no WU scrape / no Gamma join. Ghost=anomaly proxy. "
                         "Rounding convention undetermined offline.",
                "sigma_floor": SIGMA_FLOOR, "min_n_gate": MIN_N,
                "tier_boundaries": {"T1_rmse": TIER1_RMSE, "T2_rmse": TIER2_RMSE,
                                    "ghost_tier3_pct": GHOST_TIER3_PCT},
            },
            "stations": {c.city: asdict(c) for c in results},
            "sigma_calibrated_c": sigma_array,
            "discretization_mbe_c": disc_note,
        }
        with open(args.out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
