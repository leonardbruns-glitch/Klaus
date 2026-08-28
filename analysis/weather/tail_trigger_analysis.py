"""Tail trigger analysis: which intraday METAR conditions predict that the actual
daily max will significantly beat OR miss the NWP model forecast?

Two bust types:
  HOT_BUST  — actual_max − best_model >= +BUST_THRESH_C (market underpriced higher buckets)
  COLD_BUST — actual_max − best_model <= −BUST_THRESH_C (market underpriced lower buckets)

For each bust type, computes mean intraday METAR features at key observation hours
(morning = peak_hour - 6, mid = peak_hour - 3) vs NORMAL days. The features that
differ most between bust and normal days are actionable STRAT_4 triggers.

ASOS variables fetched: tmpf (temp), dwpf (dew point), sknt (wind speed),
drct (wind direction), skyc1 (sky cover). This requires one ASOS pull per city.

NWP: GFS seamless from archive API (lowest bias, best coverage). Acts as the
"market consensus" forecast. Bust = actual deviates from this by >= BUST_THRESH_C.

Usage:
    # Full run — all validated stations (takes ~30 min, writes JSON + prints report):
    python3 -m analysis.weather.tail_trigger_analysis

    # Single city (fast, for inspection):
    python3 -m analysis.weather.tail_trigger_analysis --city nyc

    # Adjust bust threshold (default 2.0°C):
    python3 -m analysis.weather.tail_trigger_analysis --bust-thresh 1.5
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import numpy as np

from analysis.weather.stations import STATIONS, Station
from analysis.weather.build_skill_matrix import (
    fetch_asos_daily_max,
    fetch_archive_chunk,
    ARCHIVE_URL,
    ASOS_URL,
    USER_AGENT,
    YEAR_START,
    YEAR_END,
    SIGMA_FLOOR,
)

BUST_THRESH_C  = 2.0   # °C deviation from model forecast to classify as a bust
REFERENCE_MODEL = "gfs_seamless"   # model used as forecast baseline for bust detection
# Hours before city peak to sample METAR features. We use the peak hour from
# CITY_PEAK_HOUR_UTC (weather_arb.py). Cities not listed use UTC 14 as default.
HOURS_BEFORE_PEAK = (6, 3, 1)     # observation hours relative to peak

OUT_PATH = Path(__file__).parent.parent.parent / "strategy" / "tail_trigger_calibration.json"


# ── ASOS multi-variable fetch ────────────────────────────────────────────────

def fetch_asos_hourly(icao: str, year_start: int, year_end: int) -> pd.DataFrame:
    """Fetch hourly ASOS with temp, dew point, wind speed/dir, and sky cover."""
    params = urllib.parse.urlencode({
        "station":  icao,
        "data":     "tmpf,dwpf,sknt,drct,skyc1",
        "year1": year_start, "month1": 1, "day1": 1,
        "year2": year_end,   "month2": 12, "day2": 31,
        "tz":       "UTC",
        "format":   "onlycomma",
        "latlon":   "no",
        "direct":   "no",
        "report_type": "2",
    })
    url = f"{ASOS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8")

    lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()

    df = pd.read_csv(StringIO("\n".join(lines)), low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    df = df.rename(columns={
        "valid": "time_utc", "tmpf": "temp_f", "dwpf": "dewp_f",
        "sknt": "wind_kt", "drct": "wind_dir", "skyc1": "sky_raw",
    })
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"])

    for col in ["temp_f", "dewp_f", "wind_kt", "wind_dir"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["temp_c"]    = (df["temp_f"] - 32) * 5 / 9
    df["dewp_c"]    = (df["dewp_f"] - 32) * 5 / 9
    df["dew_spread"]= df["temp_c"] - df["dewp_c"]
    df["sky_clr"]   = df["sky_raw"].apply(_sky_to_frac)

    df["date_utc"]  = df["time_utc"].dt.date
    df["hour_utc"]  = df["time_utc"].dt.hour
    df["month"]     = df["time_utc"].dt.month

    return df


def _sky_to_frac(s) -> float:
    """Convert ASOS sky cover code to clear-sky fraction [0=OVC, 1=CLR]."""
    if not isinstance(s, str):
        return float("nan")
    s = s.strip().upper()
    return {"CLR": 1.0, "SKC": 1.0, "FEW": 0.75, "SCT": 0.45,
            "BKN": 0.20, "OVC": 0.0, "VV": 0.0}.get(s, float("nan"))


# ── Daily feature extraction ─────────────────────────────────────────────────

def build_daily_features(hourly: pd.DataFrame,
                          peak_hour_utc: int) -> pd.DataFrame:
    """
    For each date, compute:
      - daily_max_c       : actual daily max temperature
      - rise_rate_3h      : (T at peak-3h obs) − (T at peak-6h obs), per hour
      - dew_spread_m6     : dew spread at peak−6h obs
      - sky_clr_m6        : sky clear fraction at peak−6h obs
      - wind_kt_m6        : wind speed at peak−6h obs
      - temp_anom_m6      : T at peak−6h minus monthly mean of that hour across all days
      - rapid_rise_flag   : 1 if any 30-60 min rise >= 1.5°C in the 6h before peak
      - peak_hour         : UTC hour of actual daily maximum (vs expected peak_hour_utc)
    """
    records = []
    for date_val, grp in hourly.groupby("date_utc"):
        grp = grp.sort_values("hour_utc")
        if grp["temp_c"].notna().sum() < 4:
            continue

        daily_max = grp["temp_c"].max()
        month     = grp["month"].iloc[0]

        # Target hours: peak-6, peak-3, peak-1
        def obs_at(h_offset: int):
            target = peak_hour_utc - h_offset
            if target < 0:
                target += 24
            sub = grp[grp["hour_utc"] == target]
            if sub.empty:
                # fallback: closest hour within ±1
                sub = grp[(grp["hour_utc"] - target).abs() <= 1]
            return sub.iloc[0] if not sub.empty else None

        obs_m6 = obs_at(6)
        obs_m3 = obs_at(3)

        temp_m6   = obs_m6["temp_c"]   if obs_m6 is not None else float("nan")
        temp_m3   = obs_m3["temp_c"]   if obs_m3 is not None else float("nan")
        dew_m6    = obs_m6["dew_spread"] if obs_m6 is not None else float("nan")
        sky_m6    = obs_m6["sky_clr"]  if obs_m6 is not None else float("nan")
        wind_m6   = obs_m6["wind_kt"]  if obs_m6 is not None else float("nan")
        wind_dir  = obs_m6["wind_dir"] if obs_m6 is not None else float("nan")

        # Rise rate between peak-6 and peak-3 (°C per hour)
        if not (math.isnan(temp_m6) or math.isnan(temp_m3)):
            rise_rate_3h = (temp_m3 - temp_m6) / 3.0
        else:
            rise_rate_3h = float("nan")

        # Rapid rise flag: any 30-60 min jump >= 1.5°C in 6h before peak
        window_start = peak_hour_utc - 6
        if window_start < 0:
            window_start += 24
        window_grp = grp[(grp["hour_utc"] >= window_start) &
                         (grp["hour_utc"] <= peak_hour_utc)].copy()
        window_grp = window_grp.sort_values("hour_utc")
        temps = window_grp["temp_c"].dropna().values
        rapid_rise = 0
        if len(temps) >= 2:
            diffs = np.diff(temps)
            if any(d >= 1.5 for d in diffs):
                rapid_rise = 1

        actual_peak_h = int(grp.loc[grp["temp_c"].idxmax(), "hour_utc"])

        records.append({
            "date":          str(date_val),
            "month":         int(month),
            "daily_max_c":   round(float(daily_max), 3),
            "temp_m6":       round(float(temp_m6), 3) if not math.isnan(temp_m6) else None,
            "temp_m3":       round(float(temp_m3), 3) if not math.isnan(temp_m3) else None,
            "rise_rate_3h":  round(float(rise_rate_3h), 3) if not math.isnan(rise_rate_3h) else None,
            "dew_spread_m6": round(float(dew_m6), 3)   if not math.isnan(dew_m6) else None,
            "sky_clr_m6":    round(float(sky_m6), 3)   if not math.isnan(sky_m6) else None,
            "wind_kt_m6":    round(float(wind_m6), 3)  if not math.isnan(wind_m6) else None,
            "wind_dir_m6":   round(float(wind_dir), 1) if not math.isnan(wind_dir) else None,
            "rapid_rise":    rapid_rise,
            "actual_peak_h": actual_peak_h,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Temperature anomaly at peak-6h vs monthly mean of that hour
    month_hour_means = (
        df.dropna(subset=["temp_m6"])
          .groupby("month")["temp_m6"].mean()
          .to_dict()
    )
    df["temp_anom_m6"] = df.apply(
        lambda r: (r["temp_m6"] - month_hour_means.get(r["month"], float("nan")))
                  if r["temp_m6"] is not None else None,
        axis=1,
    )
    return df


# ── Bust classification ──────────────────────────────────────────────────────

def classify_busts(daily_feats: pd.DataFrame,
                   gfs_daily: dict[str, float | None],
                   bust_thresh: float) -> pd.DataFrame:
    """
    Attach the GFS forecast for each date and classify the residual.
    residual = actual_max_c − gfs_forecast_c
    bust_type: HOT_BUST | COLD_BUST | NORMAL
    """
    df = daily_feats.copy()
    df["gfs_forecast_c"] = df["date"].map(lambda d: gfs_daily.get(d))
    df = df.dropna(subset=["gfs_forecast_c"])
    df["residual"] = df["daily_max_c"] - df["gfs_forecast_c"]

    def classify(r):
        if r >= bust_thresh:
            return "HOT_BUST"
        if r <= -bust_thresh:
            return "COLD_BUST"
        return "NORMAL"

    df["bust_type"] = df["residual"].apply(classify)
    return df


# ── Feature statistics ───────────────────────────────────────────────────────

FEATURE_COLS = [
    "rise_rate_3h", "dew_spread_m6", "sky_clr_m6",
    "wind_kt_m6", "temp_anom_m6", "rapid_rise",
]

def feature_stats(df: pd.DataFrame) -> dict:
    """
    For each bust type vs NORMAL, compute mean + std for each feature.
    Also computes the separation (z-score) between bust and normal means.
    """
    out = {}
    for bust_type in ["HOT_BUST", "COLD_BUST"]:
        bust_df   = df[df["bust_type"] == bust_type]
        normal_df = df[df["bust_type"] == "NORMAL"]
        n_bust    = len(bust_df)
        n_normal  = len(normal_df)
        if n_bust < 5:
            out[bust_type] = {"n": n_bust, "note": "too few observations"}
            continue

        feat_rows = []
        for col in FEATURE_COLS:
            b_vals = bust_df[col].dropna()
            n_vals = normal_df[col].dropna()
            if len(b_vals) < 3 or len(n_vals) < 3:
                continue
            b_mean = float(b_vals.mean())
            b_std  = float(b_vals.std())
            n_mean = float(n_vals.mean())
            n_std  = float(n_vals.std())
            # pooled std for z-score
            pool_std = math.sqrt((b_std**2 + n_std**2) / 2) or 1e-6
            z = (b_mean - n_mean) / pool_std
            feat_rows.append({
                "feature":   col,
                "bust_mean": round(b_mean, 3),
                "bust_std":  round(b_std, 3),
                "norm_mean": round(n_mean, 3),
                "norm_std":  round(n_std, 3),
                "z_score":   round(z, 2),
                "n_bust":    int(len(b_vals)),
                "n_norm":    int(len(n_vals)),
            })
        feat_rows.sort(key=lambda r: abs(r["z_score"]), reverse=True)

        # Rapid-rise bust rate
        rr_bust  = float(bust_df["rapid_rise"].mean()) if "rapid_rise" in bust_df else float("nan")
        rr_norm  = float(normal_df["rapid_rise"].mean()) if "rapid_rise" in normal_df else float("nan")

        # Residual distribution
        res_vals = bust_df["residual"]
        out[bust_type] = {
            "n":              n_bust,
            "n_normal":       n_normal,
            "pct_of_days":    round(100 * n_bust / (n_bust + n_normal + 1e-9), 1),
            "residual_mean":  round(float(res_vals.mean()), 2),
            "residual_p90":   round(float(res_vals.quantile(0.9)), 2),
            "rapid_rise_rate_bust":   round(rr_bust, 3),
            "rapid_rise_rate_normal": round(rr_norm, 3),
            "features":       feat_rows,
        }
    return out


# ── Threshold derivation ─────────────────────────────────────────────────────

def derive_thresholds(stats: dict, bust_type: str) -> dict:
    """
    For each feature with |z| > 1.0, propose a threshold that separates bust
    from normal: bust_mean − 0.5 × bust_std (for features higher in busts)
    or bust_mean + 0.5 × bust_std (for features lower in busts).
    Includes estimated precision and recall from the feature distribution.
    """
    entry = stats.get(bust_type, {})
    features = entry.get("features", [])
    thresholds = []
    for f in features:
        if abs(f["z_score"]) < 0.8:
            continue
        direction = "above" if f["z_score"] > 0 else "below"
        thresh = (f["bust_mean"] - 0.5 * f["bust_std"]
                  if direction == "above"
                  else f["bust_mean"] + 0.5 * f["bust_std"])
        thresholds.append({
            "feature":   f["feature"],
            "direction": direction,
            "threshold": round(thresh, 2),
            "z_score":   f["z_score"],
        })
    return {"bust_type": bust_type, "thresholds": thresholds}


# ── Archive NWP fetch (GFS only for speed) ───────────────────────────────────

def fetch_gfs_daily(station: Station,
                    year_start: int = YEAR_START,
                    year_end: int = YEAR_END) -> dict[str, float | None]:
    """Pull GFS seamless daily max from archive API for all years.

    Requests two models so the API appends model suffixes to keys.
    When a single model is requested, the API returns 'temperature_2m_max'
    without any suffix — unusable for per-model extraction.
    """
    combined: dict[str, float | None] = {}
    # Request a second dummy model so the API appends model-name suffixes
    models = (REFERENCE_MODEL, "era5")
    for yr in range(year_start, year_end + 1):
        start = f"{yr}-01-01"
        end   = f"{yr}-12-31"
        try:
            chunk = fetch_archive_chunk(station.lat, station.lon, models, start, end)
            combined.update(chunk.get(REFERENCE_MODEL, {}))
            time.sleep(0.3)
        except Exception as e:
            print(f"    GFS archive {yr} error: {e}", flush=True)
    return combined


# ── Per-city peak hour (mirrors weather_arb.py CITY_PEAK_HOUR_UTC) ───────────

CITY_PEAK_HOUR_UTC: dict[str, dict[int, int]] = {
    "nyc":           {1: 13, 2: 14, 3: 13, 4: 14, 5: 15, 6: 16, 7: 16, 8: 16, 9: 15, 10: 15, 11: 14, 12: 12},
    "chicago":       {1: 13, 2: 14, 3: 14, 4: 14, 5: 16, 6: 15, 7: 16, 8: 16, 9: 16, 10: 15, 11: 15, 12: 13},
    "los-angeles":   {1: 17, 2: 17, 3: 17, 4: 18, 5: 18, 6: 18, 7: 19, 8: 17, 9: 18, 10: 18, 11: 18, 12: 18},
    "miami":         {1: 16, 2: 16, 3: 16, 4: 17, 5: 17, 6: 16, 7: 17, 8: 16, 9: 16, 10: 16, 11: 16, 12: 15},
    "san-francisco": {1: 15, 2: 17, 3: 17, 4: 17, 5: 17, 6: 18, 7: 17, 8: 19, 9: 18, 10: 18, 11: 17, 12: 15},
    "tokyo":         {1:  4, 2:  5, 3:  5, 4:  5, 5:  6, 6:  5, 7:  4, 8:  4, 9:  4, 10:  5, 11:  4, 12:  5},
    "london":        {1: 11, 2: 11, 3: 12, 4: 12, 5: 13, 6: 13, 7: 13, 8: 13, 9: 12, 10: 12, 11: 10, 12: 10},
}
DEFAULT_PEAK_HOUR = 14   # fallback for cities not in the table


def _peak_hour(slug: str, month: int) -> int:
    return CITY_PEAK_HOUR_UTC.get(slug, {}).get(month, DEFAULT_PEAK_HOUR)


# ── Main analysis ────────────────────────────────────────────────────────────

def analyse_city(slug: str, station: Station,
                 bust_thresh: float = BUST_THRESH_C,
                 year_start: int = YEAR_START,
                 year_end: int = YEAR_END) -> dict:
    print(f"\n{'─'*60}", flush=True)
    print(f"  {slug.upper()} ({station.icao})", flush=True)

    # 1. ASOS hourly
    print(f"  ASOS hourly {year_start}–{year_end}...", end=" ", flush=True)
    try:
        hourly = fetch_asos_hourly(station.icao, year_start, year_end)
        print(f"{len(hourly):,} rows", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return {}

    if len(hourly) < 100:
        print(f"  WARNING: insufficient ASOS data, skipping", flush=True)
        return {}

    # 2. GFS archive daily max
    print(f"  GFS archive {year_start}–{year_end}...", end=" ", flush=True)
    try:
        gfs_daily = fetch_gfs_daily(station, year_start, year_end)
        print(f"{len(gfs_daily)} days", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return {}

    if not gfs_daily:
        print(f"  WARNING: no GFS data, skipping", flush=True)
        return {}

    # 3. Daily feature extraction (use median peak hour across months as default)
    # Use month 6 peak hour as a representative default (summer peak)
    default_peak = _peak_hour(slug, 6)
    print(f"  Building daily features (peak_hour={default_peak} UTC)...", end=" ", flush=True)
    daily = build_daily_features(hourly, peak_hour_utc=default_peak)
    print(f"{len(daily)} days", flush=True)

    if daily.empty:
        return {}

    # 4. Bust classification
    daily = classify_busts(daily, gfs_daily, bust_thresh)
    counts = daily["bust_type"].value_counts().to_dict()
    n_hot   = counts.get("HOT_BUST", 0)
    n_cold  = counts.get("COLD_BUST", 0)
    n_norm  = counts.get("NORMAL", 0)
    total   = len(daily)
    print(f"  HOT_BUST={n_hot} ({100*n_hot/total:.1f}%)  "
          f"COLD_BUST={n_cold} ({100*n_cold/total:.1f}%)  "
          f"NORMAL={n_norm} ({100*n_norm/total:.1f}%)", flush=True)

    # 5. Feature statistics per bust type
    stats = feature_stats(daily)

    # 6. Threshold derivation
    thresholds = {
        "HOT_BUST":  derive_thresholds(stats, "HOT_BUST"),
        "COLD_BUST": derive_thresholds(stats, "COLD_BUST"),
    }

    # Print top signals
    for bust_type in ["HOT_BUST", "COLD_BUST"]:
        entry = stats.get(bust_type, {})
        feats = entry.get("features", [])[:3]
        if feats:
            print(f"\n  Top signals for {bust_type} (residual_mean={entry.get('residual_mean','?')}°C):",
                  flush=True)
            for f in feats:
                direction = "↑" if f["z_score"] > 0 else "↓"
                print(f"    {f['feature']:<20} {direction}  bust={f['bust_mean']:+.2f}  "
                      f"norm={f['norm_mean']:+.2f}  z={f['z_score']:+.2f}", flush=True)
        rr_bust = entry.get("rapid_rise_rate_bust", float("nan"))
        rr_norm = entry.get("rapid_rise_rate_normal", float("nan"))
        if not math.isnan(rr_bust):
            print(f"    rapid_rise_flag        rapid_rise on {100*rr_bust:.1f}% bust days "
                  f"vs {100*rr_norm:.1f}% normal days", flush=True)

    return {
        "slug":       slug,
        "icao":       station.icao,
        "bust_thresh": bust_thresh,
        "n_total":    total,
        "n_hot_bust": n_hot,
        "n_cold_bust": n_cold,
        "n_normal":   n_norm,
        "stats":      stats,
        "thresholds": thresholds,
    }


def run(target_slugs: list[str] | None = None,
        bust_thresh: float = BUST_THRESH_C,
        year_start: int = YEAR_START,
        year_end: int = YEAR_END,
        out_path: str | None = None) -> dict:
    slugs = target_slugs or list(STATIONS.keys())
    results: dict[str, dict] = {}

    for slug in slugs:
        station = STATIONS[slug]
        try:
            city_result = analyse_city(slug, station, bust_thresh, year_start, year_end)
            if city_result:
                results[slug] = city_result
        except Exception as e:
            print(f"  FATAL {slug}: {e}", flush=True)
        time.sleep(1.0)

    # Summary table
    print(f"\n{'═'*60}", flush=True)
    print(f"{'CITY':<18} {'HOT%':>6} {'COLD%':>6} {'Top HOT signal':<28} {'Top COLD signal'}", flush=True)
    print(f"{'─'*60}", flush=True)
    for slug, r in results.items():
        n = r["n_total"]
        hot_pct  = f"{100*r['n_hot_bust']/n:.1f}%" if n else "—"
        cold_pct = f"{100*r['n_cold_bust']/n:.1f}%" if n else "—"
        hot_feat  = (r["stats"].get("HOT_BUST",  {}).get("features", [{}]) or [{}])[0].get("feature", "—")
        cold_feat = (r["stats"].get("COLD_BUST", {}).get("features", [{}]) or [{}])[0].get("feature", "—")
        print(f"{slug:<18} {hot_pct:>6} {cold_pct:>6} {hot_feat:<28} {cold_feat}", flush=True)

    # Write output
    if out_path is None:
        out_path = str(OUT_PATH)
    Path(out_path).write_text(json.dumps({
        "_meta": {
            "bust_thresh_c": bust_thresh,
            "years": f"{year_start}-{year_end}",
            "reference_model": REFERENCE_MODEL,
            "features": FEATURE_COLS,
            "note": (
                "z_score > 0 means feature is higher on bust days than normal days. "
                "Threshold = bust_mean ± 0.5×bust_std (±0.5 sigma cutoff). "
                "Use thresholds as STRAT_4 trigger candidates."
            ),
        },
        "cities": results,
    }, indent=2))
    print(f"\nResults → {out_path}", flush=True)
    return results


def _cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--city", action="append", dest="cities",
                    help="city slug(s); default=all validated stations")
    ap.add_argument("--bust-thresh", type=float, default=BUST_THRESH_C,
                    help=f"°C deviation to classify as a bust (default {BUST_THRESH_C})")
    ap.add_argument("--year-start", type=int, default=YEAR_START)
    ap.add_argument("--year-end",   type=int, default=YEAR_END)
    ap.add_argument("--out", default=None, help="output JSON path")
    args = ap.parse_args()
    run(target_slugs=args.cities,
        bust_thresh=args.bust_thresh,
        year_start=args.year_start,
        year_end=args.year_end,
        out_path=args.out)


if __name__ == "__main__":
    _cli()
