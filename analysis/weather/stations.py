"""Validated station map for Polymarket Daily Highest Temperature markets.

Source: 2026-05-20 cross-city verification (Playwright scrape of WU + Polymarket
gamma `events/slug` description text). Each entry was confirmed by reading the
market's rules text. Korean cities (Seoul/Incheon) are intentionally excluded —
WU's Summary widget renders "No data recorded" for RKSI, making resolution
non-deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Per-tier model lists. Empty tuple means "no source available at this tier".
# These names are Open-Meteo `models=` values. Verified via curl probe 2026-05-20.
_GLOBAL = ("ecmwf_aifs025", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")
_JP_NATIONAL = ("jma_seamless", "jma_msm", "jma_gsm")
_UK_NATIONAL = ("ukmo_seamless", "metno_seamless", "meteofrance_seamless")


@dataclass(frozen=True)
class Station:
    city_slug: str           # matches Polymarket slug fragment, e.g. "nyc"
    icao: str                # ICAO code, e.g. "KLGA"
    wu_path: str             # path under wunderground.com/history/daily/, no leading slash
    lat: float
    lon: float
    unit: str                # "F" or "C" — bucket-labelling unit per market rules
    bucket_width: int        # 2 for °F US markets, 1 for °C non-US markets
    openmeteo_models: tuple[str, ...]   # global + national models for Open-Meteo
    use_nws: bool = False    # add NOAA NWS gridpoint forecast (US only)


STATIONS: dict[str, Station] = {
    # US — global ensemble + native NWS gridpoint
    "nyc":           Station("nyc",           "KLGA", "us/ny/new-york-city/KLGA",  40.7773, -73.8726, "F", 2, _GLOBAL, True),
    "chicago":       Station("chicago",       "KORD", "us/il/chicago/KORD",        41.9786, -87.9048, "F", 2, _GLOBAL, True),
    "los-angeles":   Station("los-angeles",   "KLAX", "us/ca/los-angeles/KLAX",    33.9425, -118.4081,"F", 2, _GLOBAL, True),
    "miami":         Station("miami",         "KMIA", "us/fl/miami/KMIA",          25.7959, -80.2870, "F", 2, _GLOBAL, True),
    "san-francisco": Station("san-francisco", "KSFO", "us/ca/san-francisco/KSFO",  37.6213, -122.3790,"F", 2, _GLOBAL, True),
    # Tokyo — global + 3 JMA models (national)
    "tokyo":         Station("tokyo",         "RJTT", "jp/tokyo/RJTT",             35.5494, 139.7798, "C", 1, _GLOBAL + _JP_NATIONAL),
    # London — global + UKMO + MetNo + Meteofrance (national/European)
    "london":        Station("london",        "EGLC", "gb/london/EGLC",            51.5053,   0.0553, "C", 1, _GLOBAL + _UK_NATIONAL),
}
