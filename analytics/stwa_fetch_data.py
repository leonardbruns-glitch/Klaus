"""
STWA Step 1 — Fetch historical data for parameter fitting.

Downloads for every station in analysis/weather/stations.py:
  - Hourly ASOS observations (Iowa State Mesonet): temp_c, dew_c, sky_cover
  - Hourly NWP hindcasts (Open-Meteo Historical Forecast API): temp_nwp_c

Outputs:
  data/stwa_asos.parquet    — one row per (station, hour)
  data/stwa_nwp.parquet     — one row per (station, hour)

Usage:
  python3 -m analytics.stwa_fetch_data [--start 2021] [--end 2024] [--force]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.parse
import urllib.request
from io import StringIO
from pathlib import Path

import aiohttp
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
NWP_URL  = "https://historical-forecast-api.open-meteo.com/v1/forecast"
USER_AGENT = "Klaus-WeatherBot/1.0 (research; contact: leonard.bruns@gmail.com)"

SKY_RANK = {"SKC": 0, "CLR": 0, "NSC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4, "VV": 4}

# US stations report °F; all others report °C
US_ICAO_PREFIX = ("K", "P")  # KORD, KLGA, etc.; PAJN Alaska
CHUNK_DAYS = 365  # fetch NWP in annual chunks


def _is_us(icao: str) -> bool:
    return icao[:1] in ("K",) or icao in ("PHNL",)


def _f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


# ── ASOS fetch ────────────────────────────────────────────────────────────────

def fetch_asos_hourly(icao: str, year_start: int, year_end: int) -> pd.DataFrame:
    """Fetch hourly ASOS obs.  Returns DataFrame with columns:
    time_utc (datetime64[ns, UTC]), temp_c, dew_c, sky_rank (0-4).
    """
    params = urllib.parse.urlencode({
        "station":      icao,
        "data":         "tmpf,dwpf,skyc1",
        "year1": year_start, "month1": 1, "day1": 1,
        "year2": year_end,   "month2": 12, "day2": 31,
        "tz":           "UTC",
        "format":       "onlycomma",
        "latlon":       "no",
        "direct":       "no",
        "report_type":  "2",   # routine METARs only
    })
    url = f"{ASOS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8", errors="replace")

    lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()

    df = pd.read_csv(StringIO("\n".join(lines)), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"valid": "time_utc", "tmpf": "temp_raw", "dwpf": "dew_raw", "skyc1": "sky"})

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"])

    # Iowa State Mesonet always returns tmpf/dwpf in Fahrenheit — convert all stations
    df["temp_c"] = pd.to_numeric(df["temp_raw"], errors="coerce").apply(
        lambda x: _f_to_c(x) if pd.notna(x) else np.nan
    )
    df["dew_c"] = pd.to_numeric(df["dew_raw"], errors="coerce").apply(
        lambda x: _f_to_c(x) if pd.notna(x) else np.nan
    )

    df["sky_rank"] = df["sky"].apply(lambda s: SKY_RANK.get(str(s).strip(), 2))

    # Keep sane bounds in °C
    df = df[(df["temp_c"].between(-50, 55)) | df["temp_c"].isna()]
    df = df[(df["dew_c"].between(-50, 35))  | df["dew_c"].isna()]

    # Floor to the hour (METAR is typically on the hour or :20/:50 specials — keep all)
    df["hour_utc"] = df["time_utc"].dt.floor("h")

    # One row per hour: take the observation closest to the top of the hour
    df["minute"] = df["time_utc"].dt.minute
    df = df.sort_values(["hour_utc", "minute"])
    df = df.groupby("hour_utc").first().reset_index()

    return df[["hour_utc", "temp_c", "dew_c", "sky_rank"]].rename(columns={"hour_utc": "time_utc"})


# ── NWP hindcast fetch ────────────────────────────────────────────────────────

async def fetch_nwp_hourly(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
    model: str,
    year_start: int,
    year_end: int,
) -> pd.DataFrame:
    """Fetch hourly NWP temperature from Open-Meteo historical-forecast API."""
    start = f"{year_start}-01-01"
    end   = f"{year_end}-12-31"
    params = {
        "latitude":    round(lat, 4),
        "longitude":   round(lon, 4),
        "start_date":  start,
        "end_date":    end,
        "hourly":      "temperature_2m,dewpoint_2m",
        "models":      model,
        "timezone":    "UTC",
    }
    url = NWP_URL + "?" + urllib.parse.urlencode(params)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"NWP fetch {resp.status}: {text[:200]}")
        data = await resp.json()

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    temps  = hourly.get("temperature_2m", [])
    dews   = hourly.get("dewpoint_2m", [])

    if not times:
        return pd.DataFrame()

    df = pd.DataFrame({
        "time_utc":   pd.to_datetime(times, utc=True),
        "temp_nwp_c": [float(t) if t is not None else np.nan for t in temps],
        "dew_nwp_c":  [float(d) if d is not None else np.nan for d in dews],
    })
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

async def _fetch_all(year_start: int, year_end: int, force: bool) -> None:
    from analysis.weather.stations import STATIONS

    asos_path = DATA_DIR / "stwa_asos.parquet"
    nwp_path  = DATA_DIR / "stwa_nwp.parquet"

    # Load existing data to allow incremental updates
    asos_existing = pd.read_parquet(asos_path) if (asos_path.exists() and not force) else pd.DataFrame()
    nwp_existing  = pd.read_parquet(nwp_path)  if (nwp_path.exists()  and not force) else pd.DataFrame()

    already_asos = set(asos_existing["city"].unique()) if "city" in asos_existing.columns else set()
    already_nwp  = set(nwp_existing["city"].unique())  if "city" in nwp_existing.columns  else set()

    asos_chunks, nwp_chunks = [], []
    if not asos_existing.empty:
        asos_chunks.append(asos_existing)
    if not nwp_existing.empty:
        nwp_chunks.append(nwp_existing)

    connector = aiohttp.TCPConnector(limit=4)
    async with aiohttp.ClientSession(connector=connector) as session:
        for city, st in STATIONS.items():
            # ── ASOS ──────────────────────────────────────────────────────
            if city not in already_asos:
                print(f"  ASOS  {st.icao} ({city})...", end=" ", flush=True)
                try:
                    df_a = fetch_asos_hourly(st.icao, year_start, year_end)
                    if df_a.empty:
                        print("EMPTY")
                    else:
                        df_a.insert(0, "city", city)
                        df_a.insert(1, "icao", st.icao)
                        asos_chunks.append(df_a)
                        print(f"{len(df_a):,} rows")
                    time.sleep(0.4)
                except Exception as e:
                    print(f"ERROR: {e}")
            else:
                print(f"  ASOS  {st.icao} ({city}) — cached")

            # ── NWP ───────────────────────────────────────────────────────
            if city not in already_nwp:
                # Pick best model: ECMWF for non-US, GFS for US
                model = "gfs_seamless" if _is_us(st.icao) else "ecmwf_ifs025"
                print(f"  NWP   {st.icao} ({city}, {model})...", end=" ", flush=True)
                try:
                    df_n = await fetch_nwp_hourly(session, st.lat, st.lon, model, year_start, year_end)
                    if df_n.empty:
                        print("EMPTY")
                    else:
                        df_n.insert(0, "city", city)
                        df_n.insert(1, "icao", st.icao)
                        df_n["model"] = model
                        nwp_chunks.append(df_n)
                        print(f"{len(df_n):,} rows")
                    await asyncio.sleep(0.2)
                except Exception as e:
                    print(f"ERROR: {e}")
            else:
                print(f"  NWP   {st.icao} ({city}) — cached")

    if asos_chunks:
        asos_all = pd.concat(asos_chunks, ignore_index=True)
        asos_all.to_parquet(asos_path, index=False)
        print(f"\nASOS saved: {len(asos_all):,} rows → {asos_path}")

    if nwp_chunks:
        nwp_all = pd.concat(nwp_chunks, ignore_index=True)
        nwp_all.to_parquet(nwp_path, index=False)
        print(f"NWP  saved: {len(nwp_all):,} rows → {nwp_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2021)
    ap.add_argument("--end",   type=int, default=2024)
    ap.add_argument("--force", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()

    print(f"Fetching {args.start}–{args.end} for all stations...")
    asyncio.run(_fetch_all(args.start, args.end, args.force))


if __name__ == "__main__":
    main()
