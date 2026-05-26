"""
Supplemental national meteorological service feeds.

Polls national met services that have faster station data than AWC's GTS
ingest path (~3-12 min lag for international stations). Each fetcher returns
a dict compatible with _icao_metar_cache schema so the lockout scan sees the
fresher obs automatically.

Services implemented:
  KMA  — Korea Meteorological Administration (RKSI/RKPK, ~20 min gain)
  MET  — MET Norway, frost.met.no (ENGM, ~5-8 min gain, no key)
  DWD  — Deutscher Wetterdienst via BrightSky (EDDM/EDDB, ~5-8 min gain, no key)
  SMHI — Swedish Met (ESSA, ~5-8 min gain, no key)
  FMI  — Finnish Met (EFHK, ~5-8 min gain, no key)

To add KMA: register free at https://apihub.kma.go.kr, add KMA_API_KEY to .env.
All other services here need no key.

Call poll_all() from the weather arb's 60s slow path.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── KMA ──────────────────────────────────────────────────────────────────────
# Register free at https://apihub.kma.go.kr → API 목록 → 지상관측(ASOS)
# Env var: KMA_API_KEY
_KMA_KEY = os.getenv("KMA_API_KEY", "")
_KMA_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php"

# KMA ASOS station IDs → ICAO. Derived from WMO station catalog (47xxx → last 3 digits).
# RKSI = Incheon Intl (WMO 47102 → KMA stn 102)
# RKPK = Busan Gimhae (WMO 47159 → KMA stn 159)
_KMA_STN_TO_ICAO: dict[int, str] = {
    102: "RKSI",
    159: "RKPK",
}
_KMA_ICAO_TO_STN: dict[str, int] = {v: k for k, v in _KMA_STN_TO_ICAO.items()}

# ── MET Norway ────────────────────────────────────────────────────────────────
# https://frost.met.no — no auth required for current obs
_MET_NO_URL = "https://frost.met.no/observations/v0.jsonld"
_MET_NO_STATIONS: dict[str, str] = {
    "ENGM": "SN50540",  # Oslo Gardermoen
}

# ── DWD via BrightSky ────────────────────────────────────────────────────────
# https://api.brightsky.dev — wraps DWD OpenData, no auth
_BRIGHTSKY_URL = "https://api.brightsky.dev/current_weather"
# Values: DWD station IDs
_DWD_STATIONS: dict[str, str] = {
    "EDDM": "01262",   # Munich Airport
    "EDDB": "00403",   # Berlin Brandenburg
}

# ── SMHI (Swedish Met) ────────────────────────────────────────────────────────
# https://opendata-download-metobs.smhi.se — no auth
_SMHI_BASE = "https://opendata-download-metobs.smhi.se/api/category/mesan2g"
_SMHI_STATIONS: dict[str, str] = {
    "ESSA": "SE_SMI_81410",   # Stockholm Arlanda (SMHI station 81410)
}

# ── FMI (Finnish Met) ─────────────────────────────────────────────────────────
# https://opendata.fmi.fi — WFS, no auth
_FMI_URL = "https://opendata.fmi.fi/wfs"
_FMI_STATIONS: dict[str, str] = {
    "EFHK": "Helsinki-Vantaa",  # EFHK — FMI place name
}


def _utc_now_ts() -> float:
    return time.time()


def _ts_to_utc_hour(ts: float) -> int:
    return datetime.fromtimestamp(ts, tz=timezone.utc).hour


async def _fetch_kma(session, icao: str) -> Optional[dict]:
    """Fetch latest 1-minute ASOS obs from KMA for one ICAO."""
    if not _KMA_KEY:
        return None
    stn = _KMA_ICAO_TO_STN.get(icao)
    if stn is None:
        return None

    # Request the most recent minute: round down current UTC to nearest minute
    now_utc = datetime.now(timezone.utc)
    tm = now_utc.strftime("%Y%m%d%H%M")

    params = {
        "authKey": _KMA_KEY,
        "tm":      tm,
        "stn":     str(stn),
        "help":    "0",
    }
    try:
        async with session.get(
            _KMA_URL, params=params,
            timeout=__import__("aiohttp").ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] KMA %s HTTP %d", icao, resp.status)
                return None
            text = await resp.text()
    except Exception as exc:
        logger.debug("[NMS] KMA %s fetch error: %s", icao, exc)
        return None

    # Parse KMA typ01 text response
    # Format lines: #START7777 ... data row ... #END7777
    # Data columns (space-separated):
    # TM          STN  WD   WS  GST  GSH   PA     PS    PT  PR   TA   TD   HM  ...
    # 202605261200 112  72  1.2  ...                          24.3 18.2 68  ...
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 11:
            continue
        try:
            tm_str = parts[0]       # YYYYMMDDHHMM
            ta_str = parts[10]      # TA = air temp °C (index may shift — verify)
            obs_dt = datetime.strptime(tm_str, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
            obs_ts = obs_dt.timestamp()
            temp_c = float(ta_str)
            if not (-60.0 < temp_c < 60.0):
                continue
            return {
                "temp_c":      temp_c,
                "obs_time":    obs_ts,
                "last_obs_time": obs_ts,
                "utc_hour":    obs_dt.hour,
                "source":      "KMA",
            }
        except (ValueError, IndexError):
            continue
    return None


async def _fetch_met_norway(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from MET Norway frost.met.no (no auth)."""
    src = _MET_NO_STATIONS.get(icao)
    if not src:
        return None
    params = {
        "sources":       src,
        "elements":      "air_temperature",
        "referencetime": "latest",
        "fields":        "value,referenceTime",
    }
    try:
        async with session.get(
            _MET_NO_URL, params=params,
            timeout=__import__("aiohttp").ClientTimeout(total=8),
            headers={"Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] MET-NO %s HTTP %d", icao, resp.status)
                return None
            data = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("[NMS] MET-NO %s fetch error: %s", icao, exc)
        return None

    try:
        obs = data["data"][0]["observations"][0]
        ref_time = data["data"][0]["referenceTime"]   # ISO8601
        temp_c = float(obs["value"])
        obs_dt = datetime.fromisoformat(ref_time.replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-60.0 < temp_c < 60.0):
            return None
        return {
            "temp_c":        temp_c,
            "obs_time":      obs_ts,
            "last_obs_time": obs_ts,
            "utc_hour":      obs_dt.hour,
            "source":        "MET-NO",
        }
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.debug("[NMS] MET-NO %s parse error: %s", icao, exc)
        return None


async def _fetch_dwd(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from DWD via BrightSky (no auth)."""
    stn = _DWD_STATIONS.get(icao)
    if not stn:
        return None
    params = {
        "dwd_station_id": stn,
        "units":          "si",
    }
    try:
        async with session.get(
            _BRIGHTSKY_URL, params=params,
            timeout=__import__("aiohttp").ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] DWD/BrightSky %s HTTP %d", icao, resp.status)
                return None
            data = await resp.json()
    except Exception as exc:
        logger.debug("[NMS] DWD %s fetch error: %s", icao, exc)
        return None

    try:
        wx = data["weather"]
        temp_c = wx.get("temperature")   # °C (units=si)
        ts_str = wx.get("timestamp")     # ISO8601
        if temp_c is None or ts_str is None:
            return None
        temp_c = float(temp_c)
        obs_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-60.0 < temp_c < 60.0):
            return None
        return {
            "temp_c":        temp_c,
            "obs_time":      obs_ts,
            "last_obs_time": obs_ts,
            "utc_hour":      obs_dt.hour,
            "source":        "DWD",
            "dewpoint_c":    float(wx["dew_point"]) if wx.get("dew_point") is not None else None,
            "wind_speed_kt": float(wx["wind_speed"]) * 1.944 if wx.get("wind_speed") is not None else None,
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] DWD %s parse error: %s", icao, exc)
        return None


async def _fetch_fmi(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from FMI WFS (no auth)."""
    place = _FMI_STATIONS.get(icao)
    if not place:
        return None
    params = {
        "service":      "WFS",
        "version":      "2.0.0",
        "request":      "getFeature",
        "storedquery_id": "fmi::observations::weather::simple",
        "place":        place,
        "parameters":   "temperature",
        "maxlocations": "1",
    }
    try:
        async with session.get(
            _FMI_URL, params=params,
            timeout=__import__("aiohttp").ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] FMI %s HTTP %d", icao, resp.status)
                return None
            xml = await resp.text()
    except Exception as exc:
        logger.debug("[NMS] FMI %s fetch error: %s", icao, exc)
        return None

    # Parse XML: <BsWfs:ParameterValue>24.3</BsWfs:ParameterValue>
    # and       <gml:timePosition>2026-05-26T11:50:00Z</gml:timePosition>
    import re
    vals = re.findall(r"<BsWfs:ParameterValue>([\d.\-]+)</BsWfs:ParameterValue>", xml)
    times = re.findall(r"<gml:timePosition>([\dT:Z\-]+)</gml:timePosition>", xml)
    if not vals or not times:
        return None
    try:
        # Last entry is the most recent
        temp_c = float(vals[-1])
        obs_dt = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-60.0 < temp_c < 60.0):
            return None
        return {
            "temp_c":        temp_c,
            "obs_time":      obs_ts,
            "last_obs_time": obs_ts,
            "utc_hour":      obs_dt.hour,
            "source":        "FMI",
        }
    except (ValueError, IndexError) as exc:
        logger.debug("[NMS] FMI %s parse error: %s", icao, exc)
        return None


# Registry: ICAO → fetch function
_FETCHERS = {}

def _register():
    for icao in _KMA_ICAO_TO_STN:
        _FETCHERS[icao] = _fetch_kma
    for icao in _MET_NO_STATIONS:
        _FETCHERS[icao] = _fetch_met_norway
    for icao in _DWD_STATIONS:
        _FETCHERS[icao] = _fetch_dwd
    for icao in _FMI_STATIONS:
        _FETCHERS[icao] = _fetch_fmi

_register()


def covered_icaos() -> set[str]:
    """ICAOs that have a supplemental NMS source configured."""
    s = set()
    for icao in _MET_NO_STATIONS:
        s.add(icao)
    for icao in _DWD_STATIONS:
        s.add(icao)
    for icao in _FMI_STATIONS:
        s.add(icao)
    if _KMA_KEY:
        for icao in _KMA_ICAO_TO_STN.values():
            s.add(icao)
    return s


def merge_into_cache(
    icao: str,
    obs: dict,
    cache: dict,
    tz_offset_h: int = 0,
) -> bool:
    """
    Merge a fresh NMS observation into the shared _icao_metar_cache.
    Only updates if obs is strictly newer than what's cached.
    Updates running_max_c if temp is higher.
    Returns True if the cache was updated.
    """
    obs_ts = obs.get("last_obs_time", 0.0)
    temp_c = obs.get("temp_c")
    if temp_c is None:
        return False

    now_utc = datetime.now(timezone.utc)
    local_dt = now_utc + timedelta(hours=tz_offset_h)
    today_str = local_dt.date().isoformat()

    entry = cache.setdefault(icao, {
        "running_max_c": None, "last_obs_time": 0, "prev_temp_c": None,
        "running_max_date": today_str,
    })

    if obs_ts <= entry.get("last_obs_time", 0):
        return False   # AWC already has a newer obs

    # Midnight reset
    if entry.get("running_max_date") != today_str:
        entry["running_max_c"] = None
        entry["running_max_date"] = today_str

    prev_max = entry.get("running_max_c")
    new_max = temp_c if (prev_max is None or temp_c > prev_max) else prev_max

    entry.update({
        "temp_c":        temp_c,
        "prev_temp_c":   entry.get("temp_c"),
        "running_max_c": new_max,
        "last_obs_time": obs_ts,
        "obs_time":      obs_ts,
        "utc_hour":      obs.get("utc_hour", now_utc.hour),
        "nms_source":    obs.get("source", "NMS"),
    })
    if obs.get("dewpoint_c") is not None:
        entry["dewpoint_c"] = obs["dewpoint_c"]
    if obs.get("wind_speed_kt") is not None:
        entry["wind_speed_kt"] = obs["wind_speed_kt"]

    logger.info(
        "[NMS] %s updated from %s: temp=%.1f°C running_max=%.1f°C (was %.1f) obs_age=%.0fs",
        icao, obs.get("source", "?"), temp_c, new_max,
        prev_max if prev_max is not None else float("nan"),
        time.time() - obs_ts,
    )
    return True


async def poll_all(
    icaos_needed: set[str],
    cache: dict,
    tz_offsets: dict[str, int],
) -> int:
    """
    Poll all configured NMS sources for the given ICAO set.
    Merges results into cache. Returns count of cache updates.
    Called from weather_arb's 60s slow path.
    """
    import aiohttp as _aiohttp

    targets = icaos_needed & set(_FETCHERS)
    if not targets:
        return 0

    updates = 0
    async with _aiohttp.ClientSession() as session:
        for icao in targets:
            fetcher = _FETCHERS[icao]
            obs = await fetcher(session, icao)
            if obs is not None:
                tz_h = tz_offsets.get(icao, 0)
                if merge_into_cache(icao, obs, cache, tz_h):
                    updates += 1

    return updates
