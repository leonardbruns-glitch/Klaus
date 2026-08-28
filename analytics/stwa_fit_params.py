"""
STWA Step 2 — Fit all model parameters from historical ASOS + NWP data.

Reads:
  data/stwa_asos.parquet
  data/stwa_nwp.parquet

Fits per city:
  1. Bias correction:   mean(T_ASOS - T_NWP) per month × hour
  2. Humidity coeff:    slope of residual on dew-point departure, per month
  3. OU parameters:     κ, σ per 6-hour bin (00-06, 06-12, 12-18, 18-24 UTC)
  4. Spatial covariance: Ledoit-Wolf on aligned residual matrix (n_cities × n_cities)

Outputs:
  config/stwa_params.json

Usage:
  python3 -m analytics.stwa_fit_params [--train-end 2024] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm
from sklearn.covariance import LedoitWolf

ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
CONFIG    = ROOT / "config"
CONFIG.mkdir(exist_ok=True)

OUT_PATH  = CONFIG / "stwa_params.json"
HOUR_BINS = [(0, 6), (6, 12), (12, 18), (18, 24)]   # UTC hour bins for OU fitting
MIN_OBS   = 20      # minimum obs per (city, month, hour) for bias estimate
                    # Non-US cities use ECMWF which only has 2024 data on
                    # Open-Meteo (8k hourly readings ≈ 28 obs/cell), so we
                    # need a low floor. With James-Stein style shrinkage
                    # below, low-count cells blend with month-mean.
SHRINK_TARGET = 30  # James-Stein shrinkage: weight per-hour mean by n/(n+SHRINK_TARGET)
                    # n=30 → 50/50 blend; n=120 → 80/20 per-hour; n=5 → 14% per-hour
MIN_OU    = 500     # minimum obs per (city, hour-bin) for OU MLE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hour_bin(h: int) -> int:
    """Map UTC hour 0-23 → bin index 0-3."""
    return h // 6


def _ou_nll(params: list[float], residuals: np.ndarray, dt: float = 1.0) -> float:
    """Negative log-likelihood for discretely-observed OU process (unit dt=1h)."""
    kappa, sigma = params
    if kappa <= 1e-4 or sigma <= 1e-4:
        return 1e12
    decay    = np.exp(-kappa * dt)
    cond_var = (sigma ** 2 / (2 * kappa)) * (1 - np.exp(-2 * kappa * dt))
    if cond_var <= 0:
        return 1e12
    cond_std = np.sqrt(cond_var)
    cond_mean = residuals[:-1] * decay
    nll = -norm.logpdf(residuals[1:], cond_mean, cond_std).sum()
    return float(nll)


def fit_ou(residuals: np.ndarray) -> tuple[float, float]:
    """
    Method-of-moments fit of OU (κ, σ) from hourly residual series.

    For dX = -κX dt + σ dW with stationary variance V = σ²/(2κ) and
    lag-1 autocorrelation ρ = exp(-κ·1h), the two sufficient statistics
    are sample variance and sample lag-1 correlation:
        κ̂ = -ln(ρ̂)
        σ̂² = 2 κ̂ · V̂

    This is robust to non-Gaussian innovations (which MLE was not — empirical
    residuals have excess kurtosis +1.7 across cities, which biased the
    Nelder-Mead MLE κ estimate ~30-60% too high vs empirical autocorrelation).
    """
    if len(residuals) < MIN_OU:
        return 0.5, 0.5   # fallback

    eps = residuals[np.isfinite(residuals)]
    if len(eps) < MIN_OU:
        return 0.5, 0.5

    # Sample variance and lag-1 autocorrelation
    var_emp = float(eps.var(ddof=1))
    if var_emp < 1e-6:
        return 0.05, 0.05

    rho = float(np.corrcoef(eps[:-1], eps[1:])[0, 1])
    # Clamp ρ into (0.01, 0.99) — outside this range OU is degenerate
    rho = max(0.01, min(0.99, rho))

    kappa = -np.log(rho)              # 1h spacing assumed
    sigma_sq = 2.0 * kappa * var_emp
    sigma = float(np.sqrt(max(sigma_sq, 1e-6)))

    # Sanity bounds: κ in [0.05, 5.0], σ in [0.05, 3.0]
    kappa = float(np.clip(kappa, 0.05, 5.0))
    sigma = float(np.clip(sigma, 0.05, 3.0))
    return kappa, sigma


# ── Main fitting ──────────────────────────────────────────────────────────────

def main(train_end: int = 2024, verbose: bool = False) -> None:
    asos_path = DATA_DIR / "stwa_asos.parquet"
    nwp_path  = DATA_DIR / "stwa_nwp.parquet"

    if not asos_path.exists() or not nwp_path.exists():
        raise FileNotFoundError(
            "Run analytics/stwa_fetch_data.py first to download ASOS + NWP data."
        )

    print("Loading data...")
    asos = pd.read_parquet(asos_path)
    nwp  = pd.read_parquet(nwp_path)

    # Filter to training period
    asos["time_utc"] = pd.to_datetime(asos["time_utc"], utc=True)
    nwp["time_utc"]  = pd.to_datetime(nwp["time_utc"],  utc=True)
    cutoff = pd.Timestamp(f"{train_end}-12-31 23:59", tz="UTC")
    asos = asos[asos["time_utc"] <= cutoff]
    nwp  = nwp[nwp["time_utc"]  <= cutoff]

    print(f"ASOS: {len(asos):,} rows across {asos['city'].nunique()} cities")
    print(f"NWP:  {len(nwp):,} rows across {nwp['city'].nunique()} cities")

    # Merge ASOS and NWP on (city, time_utc)
    merged = asos.merge(nwp[["city", "time_utc", "temp_nwp_c", "dew_nwp_c"]],
                        on=["city", "time_utc"], how="inner")
    merged["hour"]    = merged["time_utc"].dt.hour
    merged["month"]   = merged["time_utc"].dt.month
    merged["hour_bin"]= merged["hour"].apply(_hour_bin)

    # Raw residual: ASOS observed - NWP forecast
    merged["resid_raw"] = merged["temp_c"] - merged["temp_nwp_c"]

    cities = sorted(merged["city"].unique())
    print(f"\nFitting parameters for {len(cities)} cities...")

    params: dict = {"stations": {}, "spatial_covariance": [], "city_order": []}

    # ── Per-city fitting ───────────────────────────────────────────────────────
    for city in cities:
        df = merged[merged["city"] == city].copy().sort_values("time_utc")
        if len(df) < 1000:
            print(f"  {city}: SKIP (only {len(df)} obs)")
            continue

        if verbose:
            print(f"  {city}: {len(df):,} obs", end="")

        # 1. Bias correction: per-(month,hour) mean residual, shrunk toward
        # month mean by James-Stein-style weighting. Pure per-hour mean is
        # noisy for low-count cells (non-US cities have ~28 obs/cell); pure
        # month-mean collapses 2-4°C of diurnal variation. Empirical Bayes
        # blend: w_per_hour = n/(n + SHRINK_TARGET).
        bias: dict[str, float] = {}
        for m in range(1, 13):
            month_residuals = df[df["month"] == m]["resid_raw"].dropna()
            month_mean = float(month_residuals.mean()) if len(month_residuals) >= 30 else 0.0
            for h in range(24):
                sub = df[(df["month"] == m) & (df["hour"] == h)]["resid_raw"].dropna()
                if len(sub) >= MIN_OBS:
                    per_hour_mean = float(sub.mean())
                    n = len(sub)
                    w = n / (n + SHRINK_TARGET)
                    bias[f"{m}_{h}"] = w * per_hour_mean + (1 - w) * month_mean
                elif len(sub) > 0:
                    # Below MIN_OBS: heavy shrinkage but use what we have
                    per_hour_mean = float(sub.mean())
                    n = len(sub)
                    w = n / (n + SHRINK_TARGET * 2)  # 2× shrinkage for tiny cells
                    bias[f"{m}_{h}"] = w * per_hour_mean + (1 - w) * month_mean
                else:
                    bias[f"{m}_{h}"] = month_mean

        # 2. Bias-corrected residual
        df["bias_key"] = df["month"].astype(str) + "_" + df["hour"].astype(str)
        df["bias_val"] = df["bias_key"].map(bias).fillna(0.0)
        df["resid"]    = df["resid_raw"] - df["bias_val"]

        # 3. Humidity coefficient: regress resid_raw on (dew_c - dew_nwp_c) per month
        alpha: dict[str, float] = {}
        for m in range(1, 13):
            sub = df[df["month"] == m][["resid_raw", "dew_c", "dew_nwp_c"]].dropna()
            if len(sub) >= 100:
                x = sub["dew_c"] - sub["dew_nwp_c"]
                y = sub["resid_raw"]
                # OLS: alpha = Cov(x,y) / Var(x)
                vx = float(x.var())
                alpha[str(m)] = float((x * y).mean() - x.mean() * y.mean()) / vx if vx > 0.01 else 0.0
            else:
                alpha[str(m)] = 0.0

        # 4. OU parameters per 6-hour bin
        # Compute lag-1 correlation only on TRULY adjacent hours within the bin:
        # naively filtering by hour_bin and taking corrcoef(eps[:-1], eps[1:])
        # mixes within-day 1h-gap pairs with cross-day 19h-gap pairs (~17% of
        # samples). The cross-day pairs have near-zero correlation, which
        # biases the lag-1 estimate downward → κ̂ biased high → mean reversion
        # too fast → MC paths too tight → cheap-tail bucket probs too low.
        df["date_d"] = df["time_utc"].dt.date
        kappa: dict[str, float] = {}
        sigma: dict[str, float] = {}
        for bin_i, (h_lo, h_hi) in enumerate(HOUR_BINS):
            bin_df = df[df["hour_bin"] == bin_i].sort_values("time_utc")
            if len(bin_df) < MIN_OU:
                kappa[str(bin_i)] = 0.5
                sigma[str(bin_i)] = 0.5
                continue
            # Per-day truly-adjacent (h_t, h_{t+1}) pairs within this bin
            pairs_t = []
            pairs_t1 = []
            for _d, _sub in bin_df.groupby("date_d"):
                vals = _sub["resid"].dropna().values
                hours_ = _sub["hour"].values[:len(vals)]
                # Find consecutive-hour pairs within the bin
                for i in range(len(vals) - 1):
                    if hours_[i+1] == hours_[i] + 1:
                        pairs_t.append(vals[i])
                        pairs_t1.append(vals[i+1])
            if len(pairs_t) < 200:
                # Insufficient adjacent pairs — fall back to naive
                bin_resids = bin_df["resid"].dropna().values
                k, s = fit_ou(bin_resids)
            else:
                pairs_t = np.array(pairs_t)
                pairs_t1 = np.array(pairs_t1)
                var_emp = float(pairs_t.var(ddof=1))
                rho = float(np.corrcoef(pairs_t, pairs_t1)[0, 1])
                rho = max(0.01, min(0.99, rho))
                k = float(np.clip(-np.log(rho), 0.05, 5.0))
                s = float(np.clip(np.sqrt(max(2.0 * k * var_emp, 1e-6)), 0.05, 3.0))
            kappa[str(bin_i)] = k
            sigma[str(bin_i)] = s

        # 5. Observation noise: std of single-point error
        sigma_obs = float(df["resid"].std()) if len(df) > 100 else 0.5
        sigma_obs = float(np.clip(sigma_obs, 0.1, 2.0))

        # 6. GEV fit on daily-max residuals per month
        # Block-maxima theory (Fisher-Tippett-Gnedenko): the max of a sequence
        # converges to GEV regardless of the underlying distribution. Direct
        # parametrization of the daily-max distribution gives closed-form
        # bucket probabilities — no MC needed, captures heavy/light tail
        # via shape parameter ξ.
        #
        # scipy.genextreme uses c = -ξ; standard convention is ξ > 0 = Fréchet
        # (heavy right tail), ξ < 0 = Weibull (bounded above), ξ = 0 = Gumbel.
        # We store {loc, scale, shape} where shape = -c (standard form).
        from scipy import stats as _sps
        gev_per_month: dict[str, dict] = {}
        # Compute daily max actual vs NWP per (city, month)
        df_daily = df.groupby(df["time_utc"].dt.date).agg(
            actual_max=("temp_c", "max"),
            nwp_max=("temp_nwp_c", "max"),
        ).reset_index()
        df_daily["eps_max"] = df_daily["actual_max"] - df_daily["nwp_max"]
        df_daily["month"]   = pd.to_datetime(df_daily["time_utc"]).dt.month
        df_daily = df_daily.dropna(subset=["eps_max"])
        for m in range(1, 13):
            sub = df_daily[df_daily["month"] == m]["eps_max"].values
            if len(sub) < 20:
                # Insufficient — use month-mean ± 1 fallback
                if len(sub) > 0:
                    gev_per_month[str(m)] = {
                        "loc": float(sub.mean()),
                        "scale": max(float(sub.std()), 0.3),
                        "shape": 0.0,  # Gumbel fallback
                        "n": len(sub),
                    }
                else:
                    gev_per_month[str(m)] = {"loc": 0.0, "scale": 1.0, "shape": 0.0, "n": 0}
                continue
            try:
                c, loc, scale = _sps.genextreme.fit(sub)
                # Sanity clip on shape and scale
                shape = float(np.clip(-c, -0.8, 0.8))
                scale = float(np.clip(scale, 0.1, 5.0))
                loc   = float(np.clip(loc, -10.0, 10.0))
                gev_per_month[str(m)] = {
                    "loc": loc, "scale": scale, "shape": shape, "n": int(len(sub)),
                }
            except Exception:
                gev_per_month[str(m)] = {
                    "loc": float(sub.mean()),
                    "scale": max(float(sub.std()), 0.3),
                    "shape": 0.0,
                    "n": int(len(sub)),
                }

        # Peak hour from stations registry
        from analysis.weather.stations import STATIONS as _ST
        st = _ST.get(city)
        peak_hour_utc = int(st.peak_hour_utc) if (st and hasattr(st, "peak_hour_utc")) else 14

        params["stations"][city] = {
            "icao":          st.icao if st else "",
            "lat":           st.lat  if st else 0.0,
            "lon":           st.lon  if st else 0.0,
            "unit":          st.unit if st else "C",
            "peak_hour_utc": peak_hour_utc,
            "kappa":         kappa,
            "sigma":         sigma,
            "sigma_obs":     round(sigma_obs, 4),
            "bias":          {k: round(v, 4) for k, v in bias.items()},
            "alpha_humidity":{k: round(v, 4) for k, v in alpha.items()},
            "daily_max_gev": gev_per_month,
        }
        if verbose:
            kv = [f"{v:.2f}" for v in kappa.values()]
            sv = [f"{v:.2f}" for v in sigma.values()]
            print(f"  κ={kv} σ={sv}")
        else:
            print(f"  {city}: OK  κ={list(kappa.values())}  σ={list(sigma.values())}")

    # ── Spatial covariance (Ledoit-Wolf) ──────────────────────────────────────
    print("\nFitting spatial covariance...")

    # Build aligned residual matrix: rows=timestamps, cols=cities
    # Use hourly bias-corrected residuals, pivot to wide format
    # Only keep cities that have fitted params
    fitted_cities = sorted(params["stations"].keys())

    # Recompute residuals with bias correction for all cities together
    resid_frames = []
    for city in fitted_cities:
        df_c = merged[merged["city"] == city][["time_utc", "month", "hour", "resid_raw"]].copy()
        city_bias = params["stations"][city]["bias"]
        df_c["bias_val"] = df_c.apply(
            lambda r: city_bias.get(f"{int(r['month'])}_{int(r['hour'])}", 0.0), axis=1
        )
        df_c["resid"] = df_c["resid_raw"] - df_c["bias_val"]
        df_c = df_c[["time_utc", "resid"]].rename(columns={"resid": city})
        resid_frames.append(df_c.set_index("time_utc"))

    wide = pd.concat(resid_frames, axis=1)
    wide = wide.dropna(how="any")   # keep only rows where ALL cities have obs

    print(f"  Aligned matrix: {wide.shape[0]:,} common timestamps × {wide.shape[1]} cities")

    if wide.shape[0] >= wide.shape[1] * 10:
        lw = LedoitWolf(assume_centered=True)
        lw.fit(wide.values)
        C_lw = lw.covariance_
        print(f"  Ledoit-Wolf shrinkage: {lw.shrinkage_:.4f}")
    else:
        # Fallback: diagonal (no spatial correlation)
        print(f"  WARNING: insufficient common obs, using diagonal covariance")
        C_lw = np.diag(wide.var().values)

    # Physical spatial kernel: blend empirical LW with great-circle-distance
    # exponential decay. The empirical LW captures real correlations
    # (Austin-Denver-Houston Sun-Belt block at ρ=0.4) but is noisy for
    # weakly-correlated pairs (mean ρ=0.018, median 0.004). The physical
    # kernel regularizes weakly-observed pairs toward their distance prior.
    #
    # Kernel: C_phys_ij = σ_i σ_j × exp(-d_ij / L_geo) × peak_hour_factor
    # L_geo calibrated to give ρ ≈ 0.4 at d ≈ 500 km (synoptic scale).
    fitted_cities_list = list(wide.columns)
    coords = {}
    peak_hours = {}
    for c in fitted_cities_list:
        st_p = params["stations"].get(c, {})
        coords[c] = (st_p.get("lat", 0.0), st_p.get("lon", 0.0))
        peak_hours[c] = st_p.get("peak_hour_utc", 14)
    sigmas = np.sqrt(np.diag(C_lw))

    def _gc_km(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, asin, sqrt
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dl = lon2 - lon1; dla = lat2 - lat1
        a = sin(dla/2)**2 + cos(lat1)*cos(lat2)*sin(dl/2)**2
        return 2 * 6371.0 * asin(sqrt(a))

    L_GEO_KM = 800.0   # synoptic scale, e-folding distance for correlation
    PHYS_BLEND = 0.35  # weight on physical kernel; LW gets (1-PHYS_BLEND)
    N = len(fitted_cities_list)
    C_phys = np.zeros((N, N))
    for i, ci in enumerate(fitted_cities_list):
        for j, cj in enumerate(fitted_cities_list):
            if i == j:
                C_phys[i, j] = sigmas[i] ** 2
                continue
            d = _gc_km(coords[ci][0], coords[ci][1], coords[cj][0], coords[cj][1])
            rho_phys = float(np.exp(-d / L_GEO_KM))
            # Peak-hour penalty: cities with very different diurnal phase
            # (>6h apart in peak_hour_utc) get reduced correlation
            dh = abs(peak_hours[ci] - peak_hours[cj])
            dh = min(dh, 24 - dh)  # circular
            phase_factor = float(np.exp(-(dh / 6.0) ** 2))
            C_phys[i, j] = sigmas[i] * sigmas[j] * rho_phys * phase_factor

    C = PHYS_BLEND * C_phys + (1.0 - PHYS_BLEND) * C_lw
    # Ensure symmetry + PSD
    C = (C + C.T) / 2.0
    eigs = np.linalg.eigvalsh(C)
    if eigs.min() < 1e-6:
        # Bump diagonal to guarantee PSD
        C = C + np.eye(N) * max(1e-6 - eigs.min(), 1e-6)
        print(f"  PSD repair: bumped diagonal by {max(1e-6 - eigs.min(), 1e-6):.4f}")
    print(f"  Spatial covariance: LW + {PHYS_BLEND:.0%} physical kernel "
          f"(L_geo={L_GEO_KM}km, min eig={np.linalg.eigvalsh(C).min():.4f})")

    params["spatial_covariance"] = C.tolist()
    params["city_order"]         = list(wide.columns)
    params["fit_date"]           = str(pd.Timestamp.now().date())
    params["train_end"]          = train_end
    params["n_cities"]           = len(fitted_cities)
    params["n_common_timestamps"]= int(wide.shape[0])
    params["spatial_kernel"]     = {
        "L_geo_km": L_GEO_KM,
        "phys_blend": PHYS_BLEND,
        "type": "lw_plus_physical_distance_phase",
    }

    OUT_PATH.write_text(json.dumps(params, indent=2))
    print(f"\nParams saved → {OUT_PATH}")
    print(f"  Cities fitted: {len(fitted_cities)}")
    print(f"  Covariance matrix: {len(params['city_order'])}×{len(params['city_order'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-end", type=int, default=2024)
    ap.add_argument("--verbose",   action="store_true")
    args = ap.parse_args()
    main(train_end=args.train_end, verbose=args.verbose)
