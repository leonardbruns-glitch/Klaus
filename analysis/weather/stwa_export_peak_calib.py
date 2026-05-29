"""
Export per-city daily-max calibration for the PA-shrunk pricer (read-only).

Writes config/stwa_peak_calib.json:
  { city: {peak_bias, sigma, n}, "_pooled": {...}, "_beta": 0.3 }

peak_bias = mean(realized_daily_max − bias-corrected NWP peak)   [°C, per city]
sigma     = std(realized_daily_max − bias-corrected NWP peak)     [°C, per city]
beta      = 0.30  intraday-residual shrinkage (from stwa_intraday_value.py:
            morning residual mean-reverts ~70% by peak; optimal Kalman weight≈0.3)

The live PA-shrunk pricer prices:
    daily_max ~ N( NWP_peak_corrected + peak_bias + beta·resid_now , sigma² )
  with the hard running-max floor F_M(x)=1[x≥M0]·Φ((x−center)/sigma).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
PARAMS = json.load(open(ROOT / "config" / "stwa_params.json"))
from analysis.weather.stations import STATIONS

NWP_MODEL = "ecmwf_ifs025"
BETA = 0.30
SIGMA_FLOOR = 0.6
MIN_DAYS = 50


def _bias(city, month, hour):
    b = PARAMS["stations"].get(city, {}).get("bias", {})
    return float(b.get(f"{month}_{hour}", b.get(f"{month}_0", 0.0)))


def main():
    asos = pd.read_parquet(ROOT / "data" / "stwa_asos.parquet",
                           columns=["city", "time_utc", "temp_c"])
    nwp = pd.read_parquet(ROOT / "data" / "stwa_nwp.parquet",
                          columns=["city", "time_utc", "temp_nwp_c", "model"])
    nwp = nwp[nwp["model"] == NWP_MODEL].drop(columns="model")
    df = asos.merge(nwp, on=["city", "time_utc"], how="inner").dropna()
    df["month"] = df["time_utc"].dt.month
    df["hour_utc"] = df["time_utc"].dt.hour
    df["bias"] = [_bias(c, m, h) for c, m, h in zip(df["city"], df["month"], df["hour_utc"])]
    df["nwp_corr"] = df["temp_nwp_c"] + df["bias"]

    out = {"_beta": BETA, "_note": "PA-shrunk pricer calib from 2024 ASOS vs ECMWF; "
           "center=NWP_peak+peak_bias+beta*resid_now, sigma per city"}
    all_e = []
    for city, g in df.groupby("city"):
        tz = getattr(STATIONS.get(city), "tz", "UTC") or "UTC"
        loc = g["time_utc"].dt.tz_convert(tz)
        g = g.assign(lday=loc.dt.date)
        daily = g.groupby("lday").agg(rmax=("temp_c", "max"),
                                      npeak=("nwp_corr", "max"), n=("temp_c", "size"))
        daily = daily[daily["n"] >= 20]
        if len(daily) < MIN_DAYS:
            continue
        e = (daily["rmax"] - daily["npeak"]).values
        all_e.append(e)
        out[city] = {"peak_bias": round(float(np.mean(e)), 3),
                     "sigma": round(max(float(np.std(e)), SIGMA_FLOOR), 3),
                     "n": int(len(e))}
    pooled = np.concatenate(all_e)
    out["_pooled"] = {"peak_bias": round(float(np.mean(pooled)), 3),
                      "sigma": round(max(float(np.std(pooled)), SIGMA_FLOOR), 3),
                      "n": int(len(pooled))}

    path = ROOT / "config" / "stwa_peak_calib.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}  ({len([k for k in out if not k.startswith('_')])} cities, "
          f"pooled n={out['_pooled']['n']:,})")
    print("pooled:", out["_pooled"], " beta:", BETA)
    ex = {c: out[c] for c in list(out)[:0]}  # noop
    for c in ["nyc", "london", "tokyo", "helsinki", "tel-aviv", "shanghai"]:
        if c in out:
            print(f"  {c:12} {out[c]}")


if __name__ == "__main__":
    main()
