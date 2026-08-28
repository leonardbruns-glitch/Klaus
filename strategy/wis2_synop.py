"""
WIS2 MQTT subscriber for SYNOP surface-based observations.

Subscribes to the WMO WIS2 global broker, receives push notifications when
NMS members publish new SYNOP observations, downloads the BUFR bulletin,
decodes all station reports inside it, and stores any observations within
0.5° of our target airports in a thread-safe buffer.

national_met.poll_all() calls take_decoded() to drain the buffer each cycle.

Gains vs AWC:
  - Push (no polling lag) — observation arrives within seconds of NMS publishing
  - Coverage for countries without fast NMS REST API:
      SBGR (Brazil/INMET), SAEZ (Argentina), RJTT (Japan/JMA-GTS),
      UUWW (Moscow/Roshydromet), LLBG (Israel), WIHH (Jakarta/BMKG)
  - INMET Brazil does hourly SYNOP; most others 3-hourly at 00/06/12/18 UTC

Broker: globalbroker.meteo.fr:1883  creds: everyone/everyone  (WMO public)
Topic:  +/a/wis2/+/+/data/core/weather/surface-based-observations/synop
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# ── Target airports (ICAO → (lat, lon)) ───────────────────────────────────────
# Only airports NOT already covered by a direct NMS poll in national_met.py.
# Max match distance: 0.5° (~55 km). Tight enough to avoid wrong station.
_TARGETS: dict[str, tuple[float, float]] = {
    "RJTT": (35.55, 139.78),   # Tokyo Haneda         (JMA GTS→WIS2)
    "UUWW": (55.59,  37.26),   # Moscow Vnukovo       (Roshydromet)
    "SBGR": (-23.44,-46.47),   # São Paulo Guarulhos  (INMET, hourly SYNOP)
    "SAEZ": (-34.82,-58.54),   # Buenos Aires Ezeiza  (SMN Argentina)
    "MMMX": (19.44, -99.07),   # Mexico City          (SMN Mexico)
    "LLBG": (32.00,  34.87),   # Ben Gurion           (IMS Israel)
    "WIHH": (-6.266, 106.891),  # Jakarta Halim        (BMKG Indonesia)
    "RCSS": (25.07, 121.55),   # Taipei Songshan      (CWB Taiwan)
    "FACT": (-33.96,  18.60),  # Cape Town            (SAWS South Africa)
    "ZBAA": (40.08, 116.59),   # Beijing Capital      (CMA China via GTS)
    "ZSPD": (31.14, 121.81),   # Shanghai Pudong      (CMA China)
    "ZGSZ": (22.64, 113.81),   # Shenzhen             (CMA China)
    "ZGGG": (23.39, 113.30),   # Guangzhou            (CMA China)
    "ZSQD": (36.27, 120.37),   # Qingdao              (CMA China)
    "ZHHH": (30.78, 114.21),   # Wuhan Tianhe          (CMA China)
    "ZUUU": (30.57, 103.95),   # Chengdu Shuangliu    (CMA China)
    "ZUCK": (29.72, 106.65),   # Chongqing Jiangbei   (CMA China)
    "ZSJN": (36.86, 117.02),   # Jinan Yaoqiang       (CMA China)
    "LTFM": (41.26,  28.74),   # Istanbul             (MGM Turkey via GTS)
    "LTAC": (40.13,  32.99),   # Ankara Esenboğa      (MGM Turkey — same node as LTFM)
    # East Asia / Pacific — new NMS nodes (KMA, HKO, NCMS, BoM, MetService)
    "RKSI": (37.47, 126.45),   # Seoul Incheon         (KMA Korea)
    "RKPK": (35.18, 128.94),   # Busan Gimhae          (KMA Korea)
    "VHHH": (22.31, 113.92),   # Hong Kong Intl        (HKO)
    "OMDB": (25.25,  55.36),   # Dubai Intl            (NCMS UAE)
    "YSSY": (-33.95, 151.18),  # Sydney Kingsford Smith (BoM Australia)
    "NZWN": (-41.33, 174.81),  # Wellington Intl       (MetService NZ)
    # European cities — covered by national WIS2 nodes (MetOffice/MétéoFrance/AEMET/KNMI/ARPA)
    "EGLC": (51.51,   0.05),   # London City          (UK Met Office)
    "LFPB": (48.96,   2.44),   # Paris Le Bourget     (Météo-France)
    "LEMD": (40.47,  -3.56),   # Madrid Barajas       (AEMET)
    "LEBL": (41.30,   2.08),   # Barcelona El Prat    (AEMET — same node as LEMD)
    "EHAM": (52.31,   4.76),   # Amsterdam Schiphol   (KNMI)
    "LIMC": (45.63,   8.73),   # Milan Malpensa       (ARPA Lombardia)
    "LIRF": (41.80,  12.23),   # Rome Fiumicino       (ARPA — same node as LIMC)
    # Americas
    "CYYZ": (43.68, -79.63),   # Toronto Pearson      (ECCC Canada)
    "FAOR": (-26.14,  28.24),  # Johannesburg OR Tambo (SAWS — same node as FACT)
    # Southeast Asia — previously AWC-only, now WIS2-covered
    "WMKK": (2.74,  101.70),   # Kuala Lumpur Intl    (MetMalaysia)
    "RPLL": (14.51, 121.02),   # Manila Ninoy Aquino  (PAGASA Philippines)
    "OPKC": (24.91,  67.16),   # Karachi Jinnah       (PMD Pakistan)
    # European capitals — national NMS nodes active on WIS2
    "ESSA": (59.65,  17.92),   # Stockholm Arlanda    (SMHI Sweden)
    "ENGM": (60.19,  11.09),   # Oslo Gardermoen      (MET Norway)
    "EKCH": (55.62,  12.65),   # Copenhagen Kastrup   (DMI Denmark)
    "LOWW": (48.11,  16.57),   # Vienna Schwechat     (ZAMG Austria)
    "LSZH": (47.46,   8.55),   # Zurich Kloten        (MeteoSwiss)
    "EBBR": (50.90,   4.48),   # Brussels Zaventem    (RMI Belgium)
    "LKPR": (50.10,  14.26),   # Prague Ruzyne        (CHMI Czechia)
    "LHBP": (47.43,  19.26),   # Budapest Ferihegy    (OMSZ Hungary)
    "LROP": (44.57,  26.10),   # Bucharest Otopeni    (ANM Romania)
    "LGAV": (37.94,  23.95),   # Athens Eleftherios   (HNMS Greece)
    # South Asia — IMD and BMD are active WIS2 publishers
    "VIDP": (28.57,  77.10),   # Delhi IGI            (IMD India)
    "VABB": (19.09,  72.87),   # Mumbai Chhatrapati   (IMD India — same node as VIDP)
    "VILK": (26.77,  80.89),   # Lucknow Amausi       (IMD India — same node as VIDP)
    "VGHS": (23.84,  90.40),   # Dhaka Hazrat Shahjalal (BMD Bangladesh)
    # Southeast Asia — TMD active WIS2 publisher
    "VTBS": (13.69, 100.75),   # Bangkok Suvarnabhumi (TMD Thailand)
    # Middle East — GAMEP Saudi Arabia active WIS2 publisher
    "OEJN": (21.68,  39.15),   # Jeddah King Abdulaziz (GAMEP Saudi Arabia)
    "OERK": (24.96,  46.70),   # Riyadh King Khalid   (GAMEP Saudi Arabia — same node as OEJN)
    # Africa — WMO members; broker coverage varies
    "HECA": (30.12,  31.41),   # Cairo Intl            (EMA Egypt)
    "DNMM": ( 6.58,   3.32),   # Lagos Murtala         (NiMet Nigeria)
    "HKJK": (-1.32,  36.93),   # Nairobi Jomo Kenyatta (KMD Kenya)
    # Central/South America — WMO members; broker coverage varies
    "MPHO": ( 9.07, -79.38),   # Panama City Tocumen   (IMHPA Panama)
    "SKBO": ( 4.70, -74.15),   # Bogota El Dorado      (IDEAM Colombia)
    "SPJC": (-12.02,-77.11),   # Lima Jorge Chavez     (SENAMHI Peru)
    "SCEL": (-33.39,-70.79),   # Santiago Arturo Merino (DMC Chile)
}

_MAX_DIST_DEG = 0.15  # ~17km — tight enough to exclude off-airport ground stations

# ── Shared decoded buffer ─────────────────────────────────────────────────────
_lock = threading.Lock()
_buffer: list[tuple[str, dict]] = []   # [(icao, obs_dict), ...]
_running = False
_executor: Optional[ThreadPoolExecutor] = None
# Dedup: WIS2 message IDs seen recently (multiple cache servers relay same obs).
# Bounded at 2000 entries; old entries fall off when capacity is exceeded.
_seen_ids: list[str] = []
_SEEN_MAX = 2000


def take_decoded() -> list[tuple[str, dict]]:
    """Return and clear all decoded (icao, obs) pairs since last call."""
    with _lock:
        out = list(_buffer)
        _buffer.clear()
    return out


def is_running() -> bool:
    return _running


# ── Internal: station matching ────────────────────────────────────────────────

def _closest(lat: float, lon: float) -> Optional[str]:
    best_icao, best_d = None, _MAX_DIST_DEG
    for icao, (alat, alon) in _TARGETS.items():
        d = ((lat - alat) ** 2 + (lon - alon) ** 2) ** 0.5
        if d < best_d:
            best_d, best_icao = d, icao
    return best_icao


# ── Internal: BUFR decode ─────────────────────────────────────────────────────

def _decode_bufr(bufr_bytes: bytes) -> list[tuple[str, dict]]:
    """Decode a BUFR bulletin and return (icao, obs) for matching stations."""
    try:
        import eccodes
    except ImportError:
        return []

    results: list[tuple[str, dict]] = []

    with tempfile.NamedTemporaryFile(suffix=".bufr", delete=False) as f:
        f.write(bufr_bytes)
        tmppath = f.name

    try:
        with open(tmppath, "rb") as fh:
            while True:
                bfr = eccodes.codes_bufr_new_from_file(fh)
                if bfr is None:
                    break
                try:
                    eccodes.codes_set(bfr, "unpack", 1)

                    def _get(key):
                        try:
                            return eccodes.codes_get(bfr, key)
                        except Exception:
                            return None

                    def _get_arr(key):
                        try:
                            return eccodes.codes_get_array(bfr, key)
                        except Exception:
                            return None

                    # BUFR can be single-subset or multi-subset
                    n_subsets = _get("numberOfSubsets") or 1

                    def _to_list(v, n):
                        if v is None:
                            return [None] * n
                        try:
                            return list(v)
                        except TypeError:
                            return [v] * n

                    lats   = _to_list(_get_arr("latitude"),       n_subsets)
                    lons   = _to_list(_get_arr("longitude"),      n_subsets)
                    # Some NMS encode temperature under #1#airTemperature (replicated
                    # descriptor); codes_get_array falls back to scalar for those.
                    t_raw  = _get_arr("airTemperature")
                    if t_raw is None:
                        t_raw = _get_arr("#1#airTemperature")
                    temps  = _to_list(t_raw,                      n_subsets)
                    hours  = _to_list(_get_arr("hour"),           n_subsets)
                    days   = _to_list(_get_arr("day"),            n_subsets)
                    months = _to_list(_get_arr("month"),          n_subsets)
                    years  = _to_list(_get_arr("year"),           n_subsets)

                    # For multi-station bulletins keep only the closest match per
                    # ICAO so the cache always gets the actual airport station.
                    best: dict[str, tuple[float, float, dict]] = {}
                    # icao → (dist, obs_ts, obs_dict)

                    now_utc = time.time()
                    for lat, lon, t_k, hr, dy, mo, yr in zip(
                        lats, lons, temps, hours, days, months, years
                    ):
                        if lat is None or lon is None:
                            continue
                        try:
                            flat, flon = float(lat), float(lon)
                        except (TypeError, ValueError):
                            continue
                        if abs(flat) > 90 or abs(flon) > 180:
                            continue

                        icao = _closest(flat, flon)
                        if icao is None:
                            continue

                        # Temperature (Kelvin → Celsius)
                        if t_k is None:
                            continue
                        try:
                            tk_f = float(t_k)
                        except (TypeError, ValueError):
                            continue
                        if tk_f > 1e9 or tk_f < 0:
                            continue
                        temp_c = tk_f - 273.15
                        # Reject aircraft-altitude temperatures (≤-50°C) —
                        # multi-station BUFR bulletins sometimes contain aircraft
                        # reports whose lat/lon matches a ground station within 0.5°.
                        if not (-50.0 < temp_c < 55.0):
                            continue

                        # Observation timestamp
                        obs_ts = now_utc
                        try:
                            from datetime import datetime, timezone
                            yr_i = int(yr) if yr else 0
                            mo_i = int(mo) if mo else 0
                            dy_i = int(dy) if dy else 0
                            hr_i = int(hr) if hr else 0
                            if yr_i > 2000 and mo_i > 0 and dy_i > 0:
                                obs_dt = datetime(yr_i, mo_i, dy_i, hr_i, 0,
                                                  tzinfo=timezone.utc)
                                obs_ts = obs_dt.timestamp()
                        except Exception:
                            pass

                        dist = ((flat - _TARGETS[icao][0])**2 +
                                (flon - _TARGETS[icao][1])**2) ** 0.5
                        prev = best.get(icao)
                        if prev is None or dist < prev[0]:
                            from datetime import datetime, timezone as _tz
                            obs_hour = datetime.fromtimestamp(obs_ts, tz=_tz.utc).hour
                            best[icao] = (dist, obs_ts, {
                                "temp_c":        temp_c,
                                "obs_time":      obs_ts,
                                "last_obs_time": obs_ts,
                                "utc_hour":      obs_hour,
                                "source":        "WIS2",
                            })

                    for icao, (_, _, obs) in best.items():
                        results.append((icao, obs))

                except Exception as e:
                    logger.debug("[WIS2] BUFR subset decode error: %s", e)
                finally:
                    eccodes.codes_release(bfr)
    except Exception as e:
        logger.debug("[WIS2] BUFR file decode error: %s", e)
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass

    return results


def _download_and_decode(href: str) -> None:
    """Download BUFR from href, decode, add matches to _buffer."""
    try:
        req = urllib.request.Request(
            href, headers={"User-Agent": "Klaus-weather-bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            bufr_bytes = r.read()
    except Exception as e:
        logger.debug("[WIS2] download error %s: %s", href[:70], e)
        return

    matches = _decode_bufr(bufr_bytes)
    if matches:
        with _lock:
            _buffer.extend(matches)
        for icao, obs in matches:
            logger.info("[WIS2] ← %s: %.1f°C  obs_age=%ds",
                        icao, obs["temp_c"], int(time.time() - obs["obs_time"]))
        logger.debug("[WIS2] decoded %d matches from %s", len(matches), href[:70])


# ── MQTT client ───────────────────────────────────────────────────────────────

def _build_client() -> object:
    import paho.mqtt.client as mqtt

    def on_connect(client, userdata, flags, rc, props=None):
        if rc == 0 or str(rc) == "Success":
            # Broker requires starting with cache/ or origin/ — + wildcard at root is rejected.
            # Subscribe broadly and filter "synop" in topic client-side (cheap string check).
            client.subscribe("cache/a/wis2/#", 0)
            client.subscribe("origin/a/wis2/#", 0)
            logger.info("[WIS2] connected and subscribed to SYNOP topics")
        else:
            logger.warning("[WIS2] MQTT connect failed rc=%s", rc)

    def on_disconnect(client, userdata, rc, props=None, reasonCode=None):
        logger.info("[WIS2] disconnected rc=%s — will auto-reconnect", rc)

    def on_message(client, userdata, msg):
        # Only process SYNOP surface-based-observation notifications
        if "synop" not in msg.topic and "surface-based" not in msg.topic:
            return
        try:
            j = json.loads(msg.payload)

            # Dedup by message ID: multiple cache servers relay the same
            # notification — skip if we already processed this observation.
            msg_id = j.get("id", "")
            if msg_id:
                with _lock:
                    if msg_id in _seen_ids:
                        return
                    _seen_ids.append(msg_id)
                    if len(_seen_ids) > _SEEN_MAX:
                        del _seen_ids[:_SEEN_MAX // 4]

            # Pre-filter by GeoJSON geometry: each single-station WIS2 message
            # includes the station's coordinates. Skip if not near a target airport.
            # Multi-station bulletins often have null geometry — still download those.
            geo = j.get("geometry") or {}
            coords = geo.get("coordinates")
            if coords and len(coords) >= 2:
                try:
                    msg_lon, msg_lat = float(coords[0]), float(coords[1])
                    if abs(msg_lat) <= 90 and abs(msg_lon) <= 180:
                        if _closest(msg_lat, msg_lon) is None:
                            return  # Station too far from all target airports
                except (TypeError, ValueError):
                    pass  # Unparseable coords — proceed to download

            links = j.get("links", [])
            for lnk in links:
                ltype = lnk.get("type", "").lower()
                if "bufr" in ltype:
                    href = lnk.get("href", "")
                    if href.startswith("http"):
                        _executor.submit(_download_and_decode, href)
                    break
        except Exception as e:
            logger.debug("[WIS2] message parse error: %s", e)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.username_pw_set("everyone", "everyone")
    # WIS2 Global Broker requires TLS on 8883; plaintext 1883 silently stopped
    # completing the MQTT handshake (no CONNACK) — verified 2026-06-05. Default
    # tls_set() = CERT_REQUIRED against the system CA bundle.
    client.tls_set()
    return client


def _run_loop() -> None:
    """Background thread: maintain MQTT connection with auto-reconnect."""
    global _running
    import paho.mqtt.client as mqtt

    BROKER = "globalbroker.meteo.fr"
    PORT   = 8883   # TLS-only; plaintext 1883 no longer CONNACKs (verified 2026-06-05)
    RETRY  = 30   # seconds between reconnect attempts

    client = _build_client()
    while _running:
        try:
            client.connect(BROKER, PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            logger.warning("[WIS2] connection error: %s — retrying in %ds", e, RETRY)
        if _running:
            time.sleep(RETRY)
            client = _build_client()   # fresh client on reconnect

    logger.info("[WIS2] background thread stopped")


# ── Public API ────────────────────────────────────────────────────────────────

def start(max_workers: int = 4) -> None:
    """Start WIS2 subscriber in a daemon background thread."""
    global _running, _executor
    if _running:
        return
    _running = True
    _executor = ThreadPoolExecutor(max_workers=max_workers,
                                   thread_name_prefix="wis2-decode")
    t = threading.Thread(target=_run_loop, name="wis2-mqtt", daemon=True)
    t.start()
    logger.info("[WIS2] subscriber started (%d decode workers)", max_workers)


def stop() -> None:
    global _running
    _running = False
