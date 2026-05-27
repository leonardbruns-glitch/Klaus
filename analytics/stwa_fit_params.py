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
MIN_OBS   = 200     # minimum obs per (city, month, hour) for bias estimate
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
    """MLE fit of OU (κ, σ) from hourly residual series."""
    # Initial guess from ACF: ρ(1h) ≈ exp(-κ), stationary var ≈ σ²/(2κ)
    if len(residuals) < MIN_OU:
        return 0.5, 0.5   # fallback

    eps = residuals[np.isfinite(residuals)]
    if len(eps) < MIN_OU:
        return 0.5, 0.5

    corr1 = float(np.corrcoef(eps[:-1], eps[1:])[0, 1])
    corr1 = max(0.01, min(0.99, corr1))
    k0 = -np.log(corr1)
    s0 = float(eps.std()) * np.sqrt(2 * k0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = minimize(
            _ou_nll,
            x0=[k0, max(s0, 0.1)],
            args=(eps,),
            method="Nelder-Mead",
            options={"xatol": 1e-4, "fatol": 1e-4, "maxiter": 2000},
        )

    kappa, sigma = float(res.x[0]), float(res.x[1])
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

        # 1. Bias correction: mean residual per (month, hour)
        bias: dict[str, float] = {}
        for m in range(1, 13):
            for h in range(24):
                sub = df[(df["month"] == m) & (df["hour"] == h)]["resid_raw"].dropna()
                if len(sub) >= MIN_OBS:
                    bias[f"{m}_{h}"] = float(sub.mean())
                else:
                    # Fall back to month-level mean
                    sub_m = df[df["month"] == m]["resid_raw"].dropna()
                    bias[f"{m}_{h}"] = float(sub_m.mean()) if len(sub_m) >= 50 else 0.0

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
        kappa: dict[str, float] = {}
        sigma: dict[str, float] = {}
        for bin_i, (h_lo, h_hi) in enumerate(HOUR_BINS):
            bin_resids = df[df["hour_bin"] == bin_i]["resid"].dropna().values
            k, s = fit_ou(bin_resids)
            kappa[str(bin_i)] = k
            sigma[str(bin_i)] = s

        # 5. Observation noise: std of single-point error
        sigma_obs = float(df["resid"].std()) if len(df) > 100 else 0.5
        sigma_obs = float(np.clip(sigma_obs, 0.1, 2.0))

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
        C = lw.covariance_
        print(f"  Ledoit-Wolf shrinkage: {lw.shrinkage_:.4f}")
    else:
        # Fallback: diagonal (no spatial correlation)
        print(f"  WARNING: insufficient common obs, using diagonal covariance")
        C = np.diag(wide.var().values)

    params["spatial_covariance"] = C.tolist()
    params["city_order"]         = list(wide.columns)
    params["fit_date"]           = str(pd.Timestamp.now().date())
    params["train_end"]          = train_end
    params["n_cities"]           = len(fitted_cities)
    params["n_common_timestamps"]= int(wide.shape[0])

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
