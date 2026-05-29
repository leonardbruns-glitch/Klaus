"""
STWA pricer backtest + μ-bias diagnostic (read-only, no live impact).

Uses the aligned hourly ASOS actuals (data/stwa_asos.parquet) and NWP forecasts
(data/stwa_nwp.parquet, 2021-2024) to answer the two questions that gate
confidence in the daily-max pricer:

(#3) μ-UNBIASEDNESS: is the bias-corrected residual y = T_obs − (T_nwp + bias)
     actually mean-zero per (city, UTC hour)? If not, every pricer inherits a
     location error.

(#1) DAILY-MAX SPREAD: what is the TRUE std of the daily-max forecast error
     e = realized_daily_max − bias_corrected_NWP_peak, vs the σ the peak-anchored
     pricer assumes (≈ √diag(C), the stationary residual std)? If the true spread
     is much larger, the pricer is over-confident (the 4.3× audit symptom);
     if it matches, the problem is location/bias not variance.
     Also: coverage (does ±1σ/±2σ contain 68%/95% of outcomes?) and bias of e.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
PARAMS = json.load(open(ROOT / "config" / "stwa_params.json"))
from analysis.weather.stations import STATIONS

NWP_MODEL = "ecmwf_ifs025"   # majority model, better global skill


def _bias(city: str, month: int, hour_utc: int) -> float:
    b = PARAMS["stations"].get(city, {}).get("bias", {})
    return float(b.get(f"{month}_{hour_utc}", b.get(f"{month}_0", 0.0)))


def _resid_std(city: str) -> float:
    """Engine's stationary residual std = sqrt(C_ii)."""
    order = PARAMS.get("city_order", list(PARAMS["stations"].keys()))
    if city not in order:
        return float("nan")
    i = order.index(city)
    return float(np.sqrt(max(PARAMS["spatial_covariance"][i][i], 1e-9)))


def main():
    asos = pd.read_parquet(ROOT / "data" / "stwa_asos.parquet",
                           columns=["city", "time_utc", "temp_c"])
    nwp = pd.read_parquet(ROOT / "data" / "stwa_nwp.parquet",
                          columns=["city", "time_utc", "temp_nwp_c", "model"])
    nwp = nwp[nwp["model"] == NWP_MODEL].drop(columns="model")

    df = asos.merge(nwp, on=["city", "time_utc"], how="inner")
    df = df.dropna(subset=["temp_c", "temp_nwp_c"])
    df["month"] = df["time_utc"].dt.month
    df["hour_utc"] = df["time_utc"].dt.hour
    df["bias"] = [
        _bias(c, m, h) for c, m, h in zip(df["city"], df["month"], df["hour_utc"])
    ]
    df["raw_err"] = df["temp_c"] - df["temp_nwp_c"]          # obs − nwp (before bias)
    df["resid"] = df["raw_err"] - df["bias"]                 # corrected residual y
    print(f"merged hourly rows: {len(df):,}  cities: {df['city'].nunique()}  "
          f"({df['time_utc'].min().date()} → {df['time_utc'].max().date()})\n")

    # ── #3 μ-bias diagnostic ──────────────────────────────────────────────────
    print("=" * 70)
    print("#3  μ-UNBIASEDNESS  (corrected residual should be ~0 mean)")
    print("=" * 70)
    print(f"{'':16}{'raw obs−nwp':>14}{'corrected y':>14}{'|corr| > 0.3?':>16}")
    print(f"{'POOLED':16}{df['raw_err'].mean():>14.3f}{df['resid'].mean():>14.3f}"
          f"{'YES' if abs(df['resid'].mean())>0.3 else 'ok':>16}")
    # worst-biased cities by |corrected residual mean|
    cm = df.groupby("city")[["raw_err", "resid"]].mean()
    cm["abs_resid"] = cm["resid"].abs()
    print("\n  worst-biased cities (corrected residual mean, °C):")
    for city, r in cm.sort_values("abs_resid", ascending=False).head(8).iterrows():
        flag = "  ← biased" if abs(r["resid"]) > 0.3 else ""
        print(f"    {city:14}{r['raw_err']:>12.3f}{r['resid']:>12.3f}{flag}")
    # per-hour residual structure pooled (does bias leave an intraday pattern?)
    hr = df.groupby("hour_utc")["resid"].mean()
    print(f"\n  corrected residual by UTC hour (range {hr.min():.2f}..{hr.max():.2f}, "
          f"max|·|={hr.abs().max():.2f}) — flat≈good")

    # ── #1 daily-max spread backtest ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("#1  DAILY-MAX FORECAST ERROR  e = realized_max − corrected_NWP_peak")
    print("=" * 70)
    df["nwp_corr"] = df["temp_nwp_c"] + df["bias"]
    rows = []
    for city, g in df.groupby("city"):
        tz = getattr(STATIONS.get(city), "tz", "UTC") or "UTC"
        loc = g["time_utc"].dt.tz_convert(tz)
        g = g.assign(lday=loc.dt.date)
        daily = g.groupby("lday").agg(realized_max=("temp_c", "max"),
                                      nwp_peak=("nwp_corr", "max"),
                                      n=("temp_c", "size"))
        daily = daily[daily["n"] >= 20]          # need a near-complete day
        if len(daily) < 50:
            continue
        e = (daily["realized_max"] - daily["nwp_peak"]).values
        s_eng = _resid_std(city)
        rows.append({
            "city": city, "ndays": len(daily),
            "bias_e": float(np.mean(e)), "std_e": float(np.std(e)),
            "s_engine": s_eng, "ratio": float(np.std(e) / s_eng) if s_eng > 0 else float("nan"),
            "cov1": float(np.mean(np.abs(e - np.mean(e)) <= s_eng)),
            "cov2": float(np.mean(np.abs(e - np.mean(e)) <= 2 * s_eng)),
        })
    R = pd.DataFrame(rows)
    alle_std = float(np.sqrt((R["std_e"] ** 2 * R["ndays"]).sum() / R["ndays"].sum()))
    alls_eng = float((R["s_engine"] * R["ndays"]).sum() / R["ndays"].sum())
    print(f"  cities: {len(R)}  total city-days: {int(R['ndays'].sum()):,}")
    print(f"  POOLED daily-max-error std        = {alle_std:.2f} °C")
    print(f"  engine assumed residual std (√Cii)= {alls_eng:.2f} °C")
    print(f"  RATIO true/assumed                = {alle_std/alls_eng:.2f}×  "
          f"(>1 ⇒ pricer TOO TIGHT ⇒ overconfident)")
    print(f"  mean daily-max bias (e)           = {R['bias_e'].mean():+.2f} °C  "
          f"(NWP peak {'under' if R['bias_e'].mean()>0 else 'over'}-forecasts the max)")
    print(f"  coverage within ±1σ_engine        = {(R['cov1']*R['ndays']).sum()/R['ndays'].sum():.1%}  (want 68%)")
    print(f"  coverage within ±2σ_engine        = {(R['cov2']*R['ndays']).sum()/R['ndays'].sum():.1%}  (want 95%)")
    print("\n  per-city (worst overconfidence ratio first):")
    print(f"    {'city':14}{'ndays':>6}{'bias_e':>8}{'std_e':>7}{'s_eng':>7}{'ratio':>7}{'cov1':>7}")
    for _, r in R.sort_values("ratio", ascending=False).head(12).iterrows():
        print(f"    {r['city']:14}{int(r['ndays']):>6}{r['bias_e']:>8.2f}"
              f"{r['std_e']:>7.2f}{r['s_engine']:>7.2f}{r['ratio']:>7.2f}{r['cov1']:>7.1%}")


if __name__ == "__main__":
    main()
