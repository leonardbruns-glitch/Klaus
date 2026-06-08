"""
National meteorological service feeds — layered from fastest to slowest.

All sources merge into _icao_metar_cache. merge_into_cache keeps only the
freshest observation per station, so faster sources always win.

  Synoptic HF-ASOS  — US cities (KLAX etc.),       1-5 min  (requires key)
  Singapore NEA     — WSSS (Changi, station S24),   ~2 min   (no auth)
  JMA AMeDAS        — RJTT (Tokyo Haneda),           ~9 min   (no auth)
  DWD via BrightSky — EDDM/EDDB (Munich/Berlin),    ~7 min   (no auth)
  FMI WFS           — EFHK (Helsinki),               ~7 min   (no auth)
  IMGW Poland       — EPWA (Warsaw),                ~10 min   (no auth)
  NOAA NWS API      — US cities fallback,           ~10 min   (no auth)
  WIS2 MQTT push    — 60+ airports globally,         push-based, varies
  AWC METAR batch   — ALL ICAO airports globally,   15-30 min (no auth)
                      universal fallback, 4-min poll interval

AWC batch is the baseline that ensures every city has data. Faster sources
above it overwrite AWC observations automatically via merge_into_cache.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── JMA AMeDAS (Japan) ───────────────────────────────────────────────────────
# https://www.jma.go.jp/bosai/amedas/ — no auth, 10-min obs cycle
# latest_time.txt → timestamp → map/{ts}.json → station data
# Fills in between AWC's hourly METAR cycle for Tokyo.
# Register free KMA key at https://apihub.kma.go.kr to activate Korea.
# Register free AEMET key at https://opendata.aemet.es to activate Spain.
_JMA_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
_JMA_MAP_URL    = "https://www.jma.go.jp/bosai/amedas/data/map/{ts}.json"
_JMA_STATIONS: dict[str, str] = {
    "RJTT": "44166",   # Tokyo Haneda (0.5km from airport)
}

# ── KMA ──────────────────────────────────────────────────────────────────────
_KMA_KEY = os.getenv("KMA_API_KEY", "")
_KMA_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php"

# KMA ASOS station IDs (WMO 47xxx → last 3 digits)
_KMA_STN_TO_ICAO: dict[int, str] = {
    102: "RKSI",   # Incheon Intl (WMO 47102)
    159: "RKPK",   # Busan Gimhae (WMO 47159)
}
_KMA_ICAO_TO_STN: dict[str, int] = {v: k for k, v in _KMA_STN_TO_ICAO.items()}

# ── DWD via BrightSky ────────────────────────────────────────────────────────
# https://api.brightsky.dev — no auth, wraps DWD OpenData
# Default units = DWD native (temperature in °C)
_BRIGHTSKY_URL = "https://api.brightsky.dev/current_weather"
_DWD_STATIONS: dict[str, str] = {
    "EDDM": "01262",   # Munich Airport (DWD station 01262)
    "EDDB": "00403",   # Berlin Brandenburg (DWD station 00403)
}

# ── FMI (Finnish Met) ─────────────────────────────────────────────────────────
# https://opendata.fmi.fi/wfs — no auth
# fmisid 100968 = Helsinki-Vantaa Airport (EFHK)
_FMI_URL = "https://opendata.fmi.fi/wfs"
_FMI_STATIONS: dict[str, str] = {
    "EFHK": "100968",
}

# ── Singapore NEA ──────────────────────────────────────────────────────────────
# https://api-open.data.gov.sg/v2/real-time/api/air-temperature — no auth
# S24 = Upper Changi Road North, 1.1 km from WSSS — NOT the airport instrument.
# WU resolves against the official WSSS METAR station (AWC-sourced). Using S24
# causes false lockouts when S24 diverges from the WSSS sensor. Removed.
_NEA_URL = "https://api-open.data.gov.sg/v2/real-time/api/air-temperature"
_NEA_STATIONS: dict[str, str] = {
    # WSSS removed — use AWC only (same source as WU resolution)
}

# ── IMGW Poland ───────────────────────────────────────────────────────────────
# https://danepubliczne.imgw.pl/api/data/synop — no auth, hourly synoptic obs
# Station 12375 = Warsaw Okecie (EPWA). Timestamps in UTC.
_IMGW_URL = "https://danepubliczne.imgw.pl/api/data/synop"
_IMGW_STATIONS: dict[str, str] = {
    "EPWA": "12375",  # Warsaw Okecie
}

# ── NOAA NWS API (US cities) ──────────────────────────────────────────────────
# https://api.weather.gov/stations/{id}/observations/latest — no auth
# ~10 min faster than AWC for routine hourly METARs (different ingest path).
_NWS_URL = "https://api.weather.gov/stations/{}/observations/latest"
_NWS_STATIONS: set[str] = {
    "KLGA",   # New York (LaGuardia)
    "KORD",   # Chicago O'Hare
    "KLAX",   # Los Angeles
    "KMIA",   # Miami
    "KSFO",   # San Francisco
    "KDAL",   # Dallas Love Field
    "KHOU",   # Houston Hobby
    "KSEA",   # Seattle-Tacoma
    "KBKF",   # Denver (Buckley AFB, closest to KBKF)
    "KATL",   # Atlanta
    "KAUS",   # Austin
    "KPHX",   # Phoenix Sky Harbor
}

# ── Synoptic HF-ASOS (US cities — 1-min obs, 2-5 min latency) ─────────────────
# https://docs.synopticdata.com/services/high-frequency-asos
# Station IDs: ICAO + "1M" suffix. Single batch request for all US stations.
# Supersedes NWS (~10 min) with 1-min data when SYNOPTIC_API_KEY is set.
# Register free 14-day trial: https://customer.synopticdata.com
_SYNOPTIC_TOKEN = os.getenv("SYNOPTIC_API_KEY", "")
_SYNOPTIC_URL   = "https://api.synopticdata.com/v2/stations/latest"
_SYNOPTIC_STATIONS: dict[str, str] = {
    "KLGA": "KLGA",
    "KORD": "KORD",
    "KLAX": "KLAX",
    "KMIA": "KMIA",
    "KSFO": "KSFO",
    "KDAL": "KDAL",
    "KHOU": "KHOU",
    "KSEA": "KSEA",
    "KBKF": "KBKF",
    "KATL": "KATL",
    "KAUS": "KAUS",
    "KPHX": "KPHX",
}
# Max obs age to trust Synoptic over NWS fallback (57-min KBKF outlier observed)
_SYNOPTIC_MAX_AGE_S = 1800  # 30 min — staleness beyond this → NWS takes over


async def _fetch_nea(session, icao: str) -> Optional[dict]:
    """Fetch latest air temperature from Singapore NEA (no auth). ~2 min obs age."""
    station_id = _NEA_STATIONS.get(icao)
    if not station_id:
        return None
    try:
        import aiohttp
        async with session.get(_NEA_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                logger.debug("[NMS] NEA %s HTTP %d", icao, resp.status)
                return None
            data = await resp.json()
    except Exception as exc:
        logger.debug("[NMS] NEA %s error: %s", icao, exc)
        return None

    try:
        readings = data["data"]["readings"]
        if not readings:
            return None
        r = readings[0]
        ts_str = r["timestamp"]   # e.g. "2026-05-27T00:14:00+08:00"
        obs_dt = datetime.fromisoformat(ts_str)
        obs_ts = obs_dt.astimezone(timezone.utc).timestamp()
        for item in r.get("data", []):
            if item.get("stationId") == station_id:
                temp_c = float(item["value"])
                if not (-10.0 < temp_c < 50.0):
                    return None
                return {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                        "utc_hour": obs_dt.astimezone(timezone.utc).hour, "source": "NEA"}
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        logger.debug("[NMS] NEA %s parse error: %s", icao, exc)
    return None


async def _fetch_imgw(session, icao: str) -> Optional[dict]:
    """Fetch latest synoptic obs from IMGW Poland (no auth). Hourly resolution."""
    station_id = _IMGW_STATIONS.get(icao)
    if not station_id:
        return None
    try:
        import aiohttp
        async with session.get(_IMGW_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                logger.debug("[NMS] IMGW %s HTTP %d", icao, resp.status)
                return None
            stations = await resp.json()
    except Exception as exc:
        logger.debug("[NMS] IMGW %s error: %s", icao, exc)
        return None

    try:
        for s in stations:
            if str(s.get("id_stacji")) == station_id:
                temp_c = float(s["temperatura"])
                date_str = s["data_pomiaru"]   # "2026-05-26"
                hour_str = s["godzina_pomiaru"] # "16" (UTC hour)
                obs_dt = datetime.strptime(
                    f"{date_str} {int(hour_str):02d}:00", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=timezone.utc)
                obs_ts = obs_dt.timestamp()
                if not (-40.0 < temp_c < 55.0):
                    return None
                return {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                        "utc_hour": obs_dt.hour, "source": "IMGW"}
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] IMGW %s parse error: %s", icao, exc)
    return None


async def _fetch_nws(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from NOAA NWS API (no auth). ~10 min faster than AWC for US."""
    if icao not in _NWS_STATIONS:
        return None
    url = _NWS_URL.format(icao)
    headers = {
        "User-Agent": "Klaus-weather-bot/1.0 (leonard.bruns@gmail.com)",
        "Accept": "application/json",
    }
    try:
        import aiohttp
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                logger.debug("[NMS] NWS %s HTTP %d", icao, resp.status)
                return None
            data = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("[NMS] NWS %s error: %s", icao, exc)
        return None

    try:
        props = data["properties"]
        ts_str = props["timestamp"]       # ISO 8601 UTC
        temp_val = props.get("temperature", {}).get("value")
        if temp_val is None:
            return None
        temp_c = float(temp_val)
        obs_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-50.0 < temp_c < 55.0):
            return None
        return {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                "utc_hour": obs_dt.hour, "source": "NWS"}
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] NWS %s parse error: %s", icao, exc)
    return None


async def _fetch_kma(session, icao: str) -> Optional[dict]:
    """Fetch latest 1-min ASOS obs from KMA. Requires KMA_API_KEY in env."""
    if not _KMA_KEY:
        return None
    stn = _KMA_ICAO_TO_STN.get(icao)
    if stn is None:
        return None

    now_utc = datetime.now(timezone.utc)
    tm = now_utc.strftime("%Y%m%d%H%M")
    params = {"authKey": _KMA_KEY, "tm": tm, "stn": str(stn), "help": "0"}
    try:
        import aiohttp
        async with session.get(
            _KMA_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] KMA %s HTTP %d", icao, resp.status)
                return None
            text = await resp.text()
    except Exception as exc:
        logger.debug("[NMS] KMA %s error: %s", icao, exc)
        return None

    # KMA typ01 text: space-separated, #START7777 / #END7777 delimiters
    # Columns: TM STN WD WS GST GSH PA PS PT PR TA TD HM ...
    # TA (index 10) = air temp °C
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 11:
            continue
        try:
            obs_dt = datetime.strptime(parts[0], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
            temp_c = float(parts[10])
            if not (-60.0 < temp_c < 60.0):
                continue
            obs_ts = obs_dt.timestamp()
            return {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                    "utc_hour": obs_dt.hour, "source": "KMA"}
        except (ValueError, IndexError):
            continue
    return None


async def _fetch_jma_batch(session) -> dict[str, dict]:
    """
    Fetch JMA AMeDAS 10-min surface obs for all _JMA_STATIONS in one request.
    No auth required. Updates every 10 min; obs_age typically ~9 min.
    Fills in between AWC's hourly METAR cycle for mid-hour new highs.
    Returns {icao: obs_dict}.
    """
    try:
        import aiohttp
        async with session.get(_JMA_LATEST_URL,
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                logger.debug("[NMS] JMA latest_time HTTP %d", resp.status)
                return {}
            ts_raw = (await resp.text()).strip()
        # ts_raw e.g. "2026-05-27T14:10:00+09:00" — convert to UTC yyyymmddHHMMSS
        obs_dt = datetime.fromisoformat(ts_raw).astimezone(timezone.utc)
        ts_fmt = obs_dt.strftime("%Y%m%d%H%M%S")
        map_url = _JMA_MAP_URL.format(ts=ts_fmt)
        async with session.get(map_url,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.debug("[NMS] JMA map HTTP %d", resp.status)
                return {}
            data = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("[NMS] JMA error: %s", exc)
        return {}

    result: dict[str, dict] = {}
    obs_ts = obs_dt.timestamp()
    for icao, stn_code in _JMA_STATIONS.items():
        entry = data.get(stn_code)
        if not entry:
            continue
        try:
            temp_entry = entry.get("temp")
            if temp_entry is None:
                continue
            temp_c = float(temp_entry[0])
            quality = temp_entry[1] if len(temp_entry) > 1 else 0
            if quality != 0:          # non-zero = suspect/missing
                continue
            if not (-50.0 < temp_c < 60.0):
                continue
            result[icao] = {
                "temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                "utc_hour": obs_dt.hour, "source": "JMA",
            }
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            logger.debug("[NMS] JMA %s parse error: %s", icao, exc)
    return result


async def _fetch_dwd(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from DWD via BrightSky API (no auth). Returns °C."""
    stn = _DWD_STATIONS.get(icao)
    if not stn:
        return None
    try:
        import aiohttp
        async with session.get(
            _BRIGHTSKY_URL,
            params={"dwd_station_id": stn},   # no units= → native DWD = °C
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] DWD %s HTTP %d", icao, resp.status)
                return None
            data = await resp.json()
    except Exception as exc:
        logger.debug("[NMS] DWD %s error: %s", icao, exc)
        return None

    try:
        wx = data["weather"]
        temp_c = wx.get("temperature")
        ts_str = wx.get("timestamp")
        if temp_c is None or ts_str is None:
            return None
        temp_c = float(temp_c)
        obs_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-60.0 < temp_c < 60.0):
            return None
        result = {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                  "utc_hour": obs_dt.hour, "source": "DWD"}
        if wx.get("dew_point") is not None:
            result["dewpoint_c"] = float(wx["dew_point"])
        if wx.get("wind_speed") is not None:
            result["wind_speed_kt"] = float(wx["wind_speed"]) * 1.944
        return result
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] DWD %s parse error: %s", icao, exc)
        return None


async def _fetch_fmi(session, icao: str) -> Optional[dict]:
    """Fetch latest obs from FMI WFS (no auth). Station by fmisid."""
    fmisid = _FMI_STATIONS.get(icao)
    if not fmisid:
        return None
    params = {
        "service": "WFS", "version": "2.0.0", "request": "getFeature",
        "storedquery_id": "fmi::observations::weather::simple",
        "fmisid": fmisid, "parameters": "temperature",
    }
    try:
        import aiohttp
        async with session.get(
            _FMI_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] FMI %s HTTP %d", icao, resp.status)
                return None
            xml = await resp.text()
    except Exception as exc:
        logger.debug("[NMS] FMI %s error: %s", icao, exc)
        return None

    # FMI WFS simple: <BsWfs:Time>...</BsWfs:Time> <BsWfs:ParameterValue>...</BsWfs:ParameterValue>
    vals = re.findall(r"<BsWfs:ParameterValue>([\d.\-]+)</BsWfs:ParameterValue>", xml)
    times = re.findall(r"<BsWfs:Time>([\dT:Z\-]+)</BsWfs:Time>", xml)
    if not vals or not times:
        return None
    try:
        temp_c = float(vals[-1])
        obs_dt = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))
        obs_ts = obs_dt.timestamp()
        if not (-60.0 < temp_c < 60.0):
            return None
        return {"temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                "utc_hour": obs_dt.hour, "source": "FMI"}
    except (ValueError, IndexError) as exc:
        logger.debug("[NMS] FMI %s parse error: %s", icao, exc)
        return None


async def fetch_synoptic_batch(session, icaos: set[str]) -> dict[str, dict]:
    """
    Fetch 1-min ASOS obs for all US stations in one Synoptic API call.
    Returns {icao: obs_dict}. Skips silently if no token.
    2-5 min latency vs ~13-22 min for NWS.
    """
    if not _SYNOPTIC_TOKEN:
        return {}
    targets = {icao: stid for icao, stid in _SYNOPTIC_STATIONS.items() if icao in icaos}
    if not targets:
        return {}
    stids = ",".join(targets.values())
    params = {
        "stid":   stids,
        "vars":   "air_temp",
        "units":  "metric",
        "token":  _SYNOPTIC_TOKEN,
    }
    try:
        import aiohttp
        async with session.get(
            _SYNOPTIC_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.warning("[NMS] Synoptic HTTP %d", resp.status)
                return {}
            data = await resp.json()
    except Exception as exc:
        logger.debug("[NMS] Synoptic error: %s", exc)
        return {}

    result: dict[str, dict] = {}
    stid_to_icao = {v: k for k, v in _SYNOPTIC_STATIONS.items()}
    try:
        for stn in data.get("STATION", []):
            stid = stn.get("STID", "")
            icao = stid_to_icao.get(stid)
            if not icao:
                continue
            obs = stn.get("OBSERVATIONS", {})
            at = obs.get("air_temp_value_1", {})
            temp_c = at.get("value")
            dt_str = at.get("date_time", "")
            if temp_c is None or not dt_str:
                continue
            temp_c = float(temp_c)
            if not (-60.0 < temp_c < 60.0):
                continue
            obs_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            obs_ts = obs_dt.timestamp()
            obs_age_s = time.time() - obs_ts
            if obs_age_s > _SYNOPTIC_MAX_AGE_S:
                logger.debug("[NMS] Synoptic %s stale (%.0fs) — skipping", icao, obs_age_s)
                continue
            result[icao] = {
                "temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                "utc_hour": obs_dt.hour, "source": "Synoptic",
            }
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] Synoptic parse error: %s", exc)
    return result


# ── AWC METAR batch (universal fallback, all ICAOs, ~15-30 min obs latency) ──
# https://aviationweather.gov/api/data/metar — no auth, all ICAO airports globally.
# Runs at most every 4 min; merge_into_cache rejects stale obs so faster sources win.
_AWC_BATCH_URL       = "https://aviationweather.gov/api/data/metar"
_AWC_MIN_INTERVAL_S  = 240   # max one call per 4 min
_awc_last_call_ts: float = 0.0


async def fetch_awc_batch(session, icaos: set[str]) -> dict[str, dict]:
    """
    Fetch the freshest METAR for each ICAO from AWC in one HTTP call.
    Returns {icao: obs_dict}. ~15-30 min obs_age for international airports.
    Acts as universal fallback — merge_into_cache rejects obs stale vs WIS2/Synoptic.
    """
    global _awc_last_call_ts
    now = time.time()
    if now - _awc_last_call_ts < _AWC_MIN_INTERVAL_S:
        return {}
    if not icaos:
        return {}

    params = {
        "ids":    ",".join(sorted(icaos)),
        "format": "json",
        "hours":  "1",
    }
    try:
        import aiohttp
        async with session.get(
            _AWC_BATCH_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                logger.debug("[NMS] AWC batch HTTP %d", resp.status)
                return {}
            data = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("[NMS] AWC batch error: %s", exc)
        return {}

    _awc_last_call_ts = now
    # AWC returns multiple historical obs per station; keep only the freshest per ICAO
    best: dict[str, tuple[float, dict]] = {}
    try:
        for m in data:
            icao = m.get("icaoId", "")
            if not icao or icao not in icaos:
                continue
            obs_str = m.get("reportTime") or m.get("obsTime") or ""
            temp    = m.get("temp")
            if temp is None or not obs_str:
                continue
            try:
                obs_dt = datetime.fromisoformat(obs_str.replace("Z", "+00:00"))
                obs_ts = obs_dt.timestamp()
                temp_c = float(temp)
            except (ValueError, TypeError):
                continue
            if not (-60.0 < temp_c < 60.0):
                continue
            prev = best.get(icao)
            if prev is None or obs_ts > prev[0]:
                best[icao] = (obs_ts, {
                    "temp_c": temp_c, "obs_time": obs_ts, "last_obs_time": obs_ts,
                    "utc_hour": obs_dt.hour, "source": "AWC",
                })
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("[NMS] AWC batch parse error: %s", exc)

    return {icao: obs for icao, (_, obs) in best.items()}


# Registry: ICAO → fetch function
_FETCHERS: dict[str, object] = {}

def _register() -> None:
    for icao in _DWD_STATIONS:
        _FETCHERS[icao] = _fetch_dwd
    for icao in _FMI_STATIONS:
        _FETCHERS[icao] = _fetch_fmi
    for icao in _NEA_STATIONS:
        _FETCHERS[icao] = _fetch_nea
    for icao in _IMGW_STATIONS:
        _FETCHERS[icao] = _fetch_imgw
    # NWS always registered as fallback; Synoptic batch runs first in poll_all()
    # and merge_into_cache ensures only fresher obs wins.
    if _SYNOPTIC_TOKEN:
        logger.info("[NMS] Synoptic active for %d US stations (NWS fallback retained)", len(_SYNOPTIC_STATIONS))
    for icao in _NWS_STATIONS:
        _FETCHERS[icao] = _fetch_nws
    if _KMA_KEY:
        for icao in _KMA_ICAO_TO_STN.values():
            _FETCHERS[icao] = _fetch_kma
    # JMA batch is called directly in poll_all(); mark ICAOs covered here
    for icao in _JMA_STATIONS:
        _FETCHERS[icao] = None   # sentinel: handled by _fetch_jma_batch

_register()


def covered_icaos() -> set[str]:
    try:
        from strategy.wis2_synop import _TARGETS as _wis2_targets
        wis2_icaos = set(_wis2_targets.keys())
    except Exception:
        wis2_icaos = set()
    return set(_FETCHERS.keys()) | wis2_icaos


# ── Per-source obs receipt logger (Stage-0 feed-lead measurement) ────────────
# Records the FIRST time each source delivers each physical observation
# (keyed by icao+source+obs_valid_ts), tagged with our receipt wall-clock. The
# analysis groups by (icao, obs_valid_ts): when two sources carry the SAME
# hourly METAR, AWC_recv_ts − fastest_recv_ts is the tradeable lead over a
# competitor on AWC's batch. Captures losers of the merge too — that's the point.
_OBS_RECEIPT_SEEN: set = set()

def _log_obs_receipt(icao: str, obs: dict) -> None:
    try:
        src = obs.get("source"); ovt = obs.get("last_obs_time")
        if src is None or ovt is None:
            return
        key = (icao, src, round(float(ovt)))
        if key in _OBS_RECEIPT_SEEN:
            return
        if len(_OBS_RECEIPT_SEEN) > 200_000:
            _OBS_RECEIPT_SEEN.clear()
        _OBS_RECEIPT_SEEN.add(key)
        import json as _j
        from pathlib import Path as _P
        d = _P("logs/shadow/hot") / datetime.now(timezone.utc).date().isoformat()
        d.mkdir(parents=True, exist_ok=True)
        with (d / "obs_receipt.jsonl").open("a") as f:
            f.write(_j.dumps({"recv_ts": time.time(), "icao": icao, "source": src,
                              "obs_valid_ts": float(ovt),
                              "temp_c": obs.get("temp_c")}) + "\n")
    except Exception:
        pass


def merge_into_cache(
    icao: str,
    obs: dict,
    cache: dict,
    tz_offset_h: int = 0,
) -> bool:
    """
    Merge a fresh NMS observation into _icao_metar_cache.
    Only updates if obs is strictly newer than what AWC provided.
    Returns True if the cache was updated.
    """
    obs_ts = obs.get("last_obs_time", 0.0)
    temp_c = obs.get("temp_c")
    if temp_c is None:
        return False

    # Stage-0 feed-lead measurement: log every source's first delivery of this
    # obs (before the staleness reject below, so AWC-delivers-late is captured).
    _log_obs_receipt(icao, obs)

    now_utc = datetime.now(timezone.utc)
    today_str = (now_utc + timedelta(hours=tz_offset_h)).date().isoformat()

    entry = cache.setdefault(icao, {
        "running_max_c": None, "official_running_max_c": None,
        "last_obs_time": 0, "prev_temp_c": None, "running_max_date": today_str,
    })

    if obs_ts <= entry.get("last_obs_time", 0):
        return False  # AWC already has a newer obs

    if entry.get("running_max_date") != today_str:
        entry["running_max_c"] = None
        entry["official_running_max_c"] = None
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

    # official_running_max_c only updates from METAR sources (AWC, NWS).
    # This matches what WU/Polymarket oracle uses: hourly METARs + SPECIs.
    # Synoptic 1-min ASOS, JMA AMeDAS, and similar non-METAR feeds are excluded.
    _OFFICIAL_METAR_SOURCES = {"AWC", "NWS"}
    if obs.get("source", "") in _OFFICIAL_METAR_SOURCES:
        official_prev = entry.get("official_running_max_c")
        official_new = temp_c if (official_prev is None or temp_c > official_prev) else official_prev
        entry["official_running_max_c"] = official_new
    if obs.get("dewpoint_c") is not None:
        entry["dewpoint_c"] = obs["dewpoint_c"]
    if obs.get("wind_speed_kt") is not None:
        entry["wind_speed_kt"] = obs["wind_speed_kt"]

    logger.info(
        "[NMS] %s ← %s: %.1f°C  running_max=%.1f°C  obs_age=%.0fs",
        icao, obs.get("source", "?"), temp_c, new_max,
        time.time() - obs_ts,
    )
    return True


# ── Persistent HTTP session ──────────────────────────────────────────────────
# One keepalive ClientSession reused across all poll cycles, instead of opening
# (and tearing down) a fresh session per source group every 2s. Eliminates the
# repeated DNS+TCP+TLS handshakes that dominated per-cycle ingestion latency.
_session = None  # type: ignore[assignment]


async def _get_session():
    """Lazily create / reuse a single keepalive aiohttp session."""
    global _session
    import aiohttp
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=32, ttl_dns_cache=300,
                keepalive_timeout=30, enable_cleanup_closed=True,
            )
        )
    return _session


async def close_session() -> None:
    """Close the shared session on shutdown (optional; OS reclaims at exit)."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def poll_all(
    icaos_needed: set[str],
    cache: dict,
    tz_offsets: dict[str, int],
) -> int:
    """Poll all configured NMS sources + drain WIS2 decoded buffer.

    All HTTP source groups run concurrently on one shared keepalive session;
    per-station REST fetches are gathered too. merge_into_cache is monotone by
    obs_time, so merge order does not affect the result — AWC (stalest) still
    loses to any fresher source exactly as before.
    """
    updates = 0

    # ── Drain WIS2 push buffer first (zero HTTP cost, already decoded) ──
    try:
        from strategy.wis2_synop import take_decoded
        for icao, obs in take_decoded():
            if icao in icaos_needed:
                if merge_into_cache(icao, obs, cache, tz_offsets.get(icao, 0)):
                    updates += 1
                    logger.info("[NMS] %s ← WIS2: %.1f°C  obs_age=%ds",
                                icao, obs["temp_c"],
                                int(time.time() - obs["obs_time"]))
    except Exception as e:
        logger.debug("[NMS] WIS2 drain error: %s", e)

    session = await _get_session()

    # ── Synoptic HF-ASOS batch (US stations) ──
    async def _synoptic() -> dict:
        if not _SYNOPTIC_TOKEN:
            return {}
        us_needed = icaos_needed & set(_SYNOPTIC_STATIONS)
        if not us_needed:
            return {}
        return await fetch_synoptic_batch(session, us_needed)

    # ── JMA AMeDAS batch (Japan) ──
    async def _jma() -> dict:
        if not (icaos_needed & set(_JMA_STATIONS)):
            return {}
        jma_batch = await _fetch_jma_batch(session)
        return {i: o for i, o in jma_batch.items() if i in icaos_needed}

    # ── Per-station REST fetchers (concurrent) ──
    # Skip JMA sentinels (None fetcher) — handled by _fetch_jma_batch above.
    async def _rest() -> dict:
        targets = list((icaos_needed & set(_FETCHERS)) - set(_JMA_STATIONS))
        if not targets:
            return {}
        results = await asyncio.gather(
            *[_FETCHERS[i](session, i) for i in targets],
            return_exceptions=True,
        )
        out: dict = {}
        for icao, obs in zip(targets, results):
            if isinstance(obs, dict):
                out[icao] = obs
            elif isinstance(obs, Exception):
                logger.debug("[NMS] REST %s error: %s", icao, obs)
        return out

    # ── AWC METAR batch — universal fallback for all needed ICAOs ──
    async def _awc() -> dict:
        return await fetch_awc_batch(session, icaos_needed)

    syn, jma, rest, awc = await asyncio.gather(
        _synoptic(), _jma(), _rest(), _awc(),
        return_exceptions=True,
    )

    # Merge in source-priority order (order-independent: merge is monotone).
    awc_updates = 0
    for label, batch in (("Synoptic", syn), ("JMA", jma), ("REST", rest), ("AWC", awc)):
        if isinstance(batch, Exception):
            logger.debug("[NMS] %s group error: %s", label, batch)
            continue
        for icao, obs in batch.items():
            if obs is None:
                continue
            if merge_into_cache(icao, obs, cache, tz_offsets.get(icao, 0)):
                updates += 1
                if label == "AWC":
                    awc_updates += 1
    if isinstance(awc, dict) and awc:
        logger.debug("[NMS] AWC batch: %d fetched, %d new updates", len(awc), awc_updates)

    return updates
