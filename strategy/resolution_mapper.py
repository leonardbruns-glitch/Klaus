"""
Resolution Source Mapper for weather_arb.py.

Polymarket weather markets resolve against a specific Wunderground station URL embedded
in the market description. A 5-mile difference between city centre and the actual airport
tarmac invalidates our microclimate model — we must forecast at the exact sensor location.

Pipeline:
  1. _extract_wu_station(description) → station_code (e.g. "RKSI") or None
  2. STATION_COORDS[station_code] → (lat, lon) of the physical sensor
  3. Validation gate: haversine(city_centre, station) < MAX_STATION_OFFSET_KM
     If station coords missing or offset too large → skip market entirely.

Usage in weather_arb._scan() / _refresh_today_markets():
    from strategy.resolution_mapper import resolve_station
    result = resolve_station(market_description, city, city_lat, city_lon)
    if result is None:
        continue   # failsafe: can't confirm resolution source
    station_code, exact_lat, exact_lon = result
"""
from __future__ import annotations

import math
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum tolerated distance (km) between city-centre coords and extracted station.
# Beyond this we treat the market as "unconfirmed resolution source" and skip it.
MAX_STATION_OFFSET_KM = 50.0

# Regex: extracts the Wunderground station code from resolution source URLs.
# Matches all three URL formats Polymarket uses:
#   https://www.wunderground.com/history/daily/kr/incheon/RKSI/...
#   https://www.wunderground.com/history/daily/RKSI/date/2026-5-20
#   wunderground.com/history/daily/us/tx/dallas/KDAL
_WU_URL_RE = re.compile(
    # No IGNORECASE — station codes are uppercase (KLGA, RKSI);
    # path segments are lowercase (us, kr, tx, dallas, incheon).
    # Without this distinction the regex incorrectly captures city slugs as stations.
    r"wunderground\.com/history/daily/"
    r"(?:[a-z]{2}/(?:[a-z0-9-]+/){0,2})?"  # optional: country/[state/]city/ — all lowercase
    r"([A-Z]{3,4}[0-9A-Z]{0,6})"            # station code: uppercase ICAO or PWS id
)

# Some markets (Tel Aviv, Moscow, Istanbul) resolve via NOAA timeseries instead of WU:
#   https://www.weather.gov/wrh/timeseries?site=LLBG
_NOAA_URL_RE = re.compile(r"weather\.gov/wrh/timeseries\?site=([A-Z0-9]{3,6})")

# ── Station coordinate table ────────────────────────────────────────────────
# Physical lat/lon of the exact WU/ASOS sensor (airport tarmac, not city centre).
# Source: FAA/ICAO published aerodrome reference points + WMO station tables.
# Add new stations as Polymarket opens new cities.
STATION_COORDS: dict[str, tuple[float, float]] = {
    # North America
    "KLGA":  (40.7769,  -73.8740),   # LaGuardia — NYC Polymarket station (confirmed)
    "KORD":  (41.9742,  -87.9073),   # O'Hare — Chicago
    "KLAX":  (33.9425, -118.4081),   # LAX — Los Angeles
    "KMIA":  (25.7953,  -80.2900),   # Miami International
    "KSFO":  (37.6213, -122.3790),   # SFO — San Francisco
    "KDAL":  (32.8481,  -96.8517),   # Dallas Love Field
    "KAUS":  (30.1945,  -97.6699),   # Austin Bergstrom
    "KHOU":  (29.6454,  -95.2789),   # Houston Hobby
    "KBKF":  (39.7017, -104.7517),   # Denver Buckley SFB
    "KPHX":  (33.4343, -112.0117),   # Phoenix Sky Harbor
    "KATL":  (33.6407,  -84.4277),   # Atlanta Hartsfield
    "KSEA":  (47.4502, -122.3088),   # Seattle-Tacoma
    "CYYZ":  (43.6777,  -79.6248),   # Toronto Pearson
    "MMMX":  (19.4363,  -99.0721),   # Mexico City Juárez
    # Europe
    "EGLC":  (51.5048,    0.0495),   # London City Airport
    "LFPB":  (48.9694,    2.4414),   # Paris Le Bourget
    "EDDM":  (48.3538,   11.7861),   # Munich Airport
    "LIMC":  (45.6307,    8.7281),   # Milan Malpensa
    "LEMD":  (40.4936,   -3.5668),   # Madrid Barajas
    "EPWA":  (52.1657,   20.9671),   # Warsaw Chopin
    "EHAM":  (52.3086,    4.7639),   # Amsterdam Schiphol
    "EFHK":  (60.3172,   24.9633),   # Helsinki Vantaa
    "EDDB":  (52.3667,   13.5033),   # Berlin Brandenburg
    "ESSA":  (59.6519,   17.9186),   # Stockholm Arlanda
    "ENGM":  (60.1939,   11.0998),   # Oslo Gardermoen
    "EKCH":  (55.6179,   12.6560),   # Copenhagen Kastrup
    "LOWW":  (48.1103,   16.5697),   # Vienna Schwechat
    "LSZH":  (47.4647,    8.5492),   # Zurich Kloten
    "EBBR":  (50.9010,    4.4844),   # Brussels Zaventem
    "LEBL":  (41.2971,    2.0785),   # Barcelona El Prat
    "LIRF":  (41.8003,   12.2389),   # Rome Fiumicino
    "LKPR":  (50.1008,   14.2600),   # Prague Václav Havel
    "LHBP":  (47.4298,   19.2610),   # Budapest Ferenc Liszt
    "LROP":  (44.5722,   26.1022),   # Bucharest Henri Coandă
    "LGAV":  (37.9364,   23.9445),   # Athens Venizelos
    "LTFJ":  (40.8986,   29.3092),   # Istanbul Sabiha Gökçen
    "LTFM":  (41.2608,   28.7425),   # Istanbul Airport (new main, NOAA resolution)
    "UUEE":  (55.9736,   37.4125),   # Moscow Sheremetyevo
    "UUWW":  (55.5915,   37.2613),   # Moscow Vnukovo (Polymarket NOAA resolution station)
    # Asia-Pacific
    "RKSI":  (37.4602,  126.4407),   # Seoul Incheon (confirmed Polymarket station)
    "RJTT":  (35.5494,  139.7798),   # Tokyo Haneda
    "VHHH":  (22.3080,  113.9185),   # Hong Kong International
    "RCSS":  (25.0694,  121.5522),   # Taipei Songshan
    "ZBAA":  (40.0799,  116.5844),   # Beijing Capital
    "ZSPD":  (31.1434,  121.8052),   # Shanghai Pudong
    "ZHHH":  (30.7838,  114.2080),   # Wuhan Tianhe
    "ZUUU":  (30.5782,  103.9470),   # Chengdu Shuangliu
    "ZGSZ":  (22.6393,  113.8107),   # Shenzhen Bao'an
    "ZGGG":  (23.3924,  113.2990),   # Guangzhou Baiyun
    "ZSJN":  (36.8572,  117.0558),   # Jinan Yaoqiang
    "ZSQD":  (36.2661,  120.3742),   # Qingdao Jiaodong
    "ZUCK":  (29.7192,  106.6418),   # Chongqing Jiangbei
    "WSSS":  (1.3644,   103.9915),   # Singapore Changi
    "VTBS":  (13.6811,  100.7472),   # Bangkok Suvarnabhumi
    "WMKK":  (2.7456,   101.7072),   # Kuala Lumpur KLIA
    "RPLL":  (14.5086,  121.0194),   # Manila Ninoy Aquino
    "WIHH":  (-6.2662,  106.8906),   # Jakarta Halim
    "VABB":  (19.0896,   72.8656),   # Mumbai Chhatrapati
    "VIDP":  (28.5665,   77.1031),   # Delhi Indira Gandhi
    "VILK":  (26.7606,   80.8893),   # Lucknow Chaudhary Charan
    "VGHS":  (23.8433,   90.3978),   # Dhaka Hazrat Shahjalal
    "OMDB":  (25.2532,   55.3657),   # Dubai International
    "OEJN":  (21.6796,   39.1565),   # Jeddah King Abdulaziz
    "OERK":  (24.9576,   46.6988),   # Riyadh King Khalid
    "HECA":  (30.1219,   31.4056),   # Cairo International
    "DNMM":  (6.5774,     3.3214),   # Lagos Murtala Muhammed
    "HKJK":  (-1.3192,   36.9275),   # Nairobi Jomo Kenyatta
    "FAOR":  (-26.1392,  28.2460),   # Johannesburg O.R. Tambo
    "FACT":  (-33.9648,  18.6017),   # Cape Town International
    "YSSY":  (-33.9399, 151.1753),   # Sydney Kingsford Smith
    "NZWN":  (-41.3272, 174.8051),   # Wellington International
    "SAEZ":  (-34.8222,  -58.5358),  # Buenos Aires Ezeiza
    "SBGR":  (-23.4356,  -46.4731),  # São Paulo Guarulhos
    "SKBO":  (4.7016,   -74.1469),   # Bogotá El Dorado
    "SPJC":  (-12.0219,  -77.1143),  # Lima Jorge Chávez
    "SCEL":  (-33.3930,  -70.7858),  # Santiago Arturo Merino
    "RKPK":  (35.1795,  128.9382),   # Busan Gimhae
    "LTAC":  (40.1281,   32.9951),   # Ankara Esenboğa
    "MPHO":  (8.9788,   -79.5556),   # Panama City Marcos Gelabert
    "OPKC":  (24.8936,   67.1355),   # Karachi Masroor
    "LLBG":  (32.0005,   34.8706),   # Tel Aviv Ben Gurion
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _extract_wu_station(text: str) -> Optional[str]:
    """
    Extract the resolution station code from a Polymarket market description.

    Handles WU URLs:
      wunderground.com/history/daily/kr/incheon/RKSI/...   → "RKSI"
      wunderground.com/history/daily/KLGA/date/2026-5-20   → "KLGA"
      wunderground.com/history/daily/us/tx/dallas/KDAL     → "KDAL"
    And NOAA timeseries URLs (Tel Aviv, Moscow, Istanbul):
      https://www.weather.gov/wrh/timeseries?site=LLBG     → "LLBG"
    Returns the uppercase station code, or None if not found.
    """
    if not text:
        return None
    m = _WU_URL_RE.search(text) or _NOAA_URL_RE.search(text)
    if not m:
        return None
    code = m.group(1).upper()
    # Sanity: ICAO codes are 4 chars; PWS codes are 6–10 alphanumeric. Reject junk.
    if len(code) < 3 or len(code) > 10:
        return None
    return code


def resolve_station(
    description: str,
    city: str,
    city_lat: float,
    city_lon: float,
) -> Optional[tuple[str, float, float]]:
    """
    Full resolution pipeline. Returns (station_code, exact_lat, exact_lon) or None.

    None means: skip this market — cannot confirm the physical sensor location.

    Failure modes that return None:
      1. No WU URL found in description          → station unknown
      2. Station code not in STATION_COORDS      → coordinates unknown
      3. Station offset > MAX_STATION_OFFSET_KM  → suspicious station (bad market setup)
    """
    station = _extract_wu_station(description)
    if station is None:
        logger.debug("[RM] no WU station in description for %s", city)
        return None

    coords = STATION_COORDS.get(station)
    if coords is None:
        logger.warning(
            "[RM] station %s not in STATION_COORDS for city=%s — add to table to trade",
            station, city,
        )
        return None

    s_lat, s_lon = coords
    dist_km = _haversine_km(city_lat, city_lon, s_lat, s_lon)
    if dist_km > MAX_STATION_OFFSET_KM:
        logger.warning(
            "[RM] STATION MISMATCH city=%s station=%s dist=%.1f km > %.0f km — SKIP",
            city, station, dist_km, MAX_STATION_OFFSET_KM,
        )
        return None

    logger.debug(
        "[RM] %s → station=%s @ (%.4f, %.4f) dist=%.1f km from city centre",
        city, station, s_lat, s_lon, dist_km,
    )
    return station, s_lat, s_lon
