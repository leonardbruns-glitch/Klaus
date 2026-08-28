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
_EU_NATIONAL = ("ukmo_seamless", "metno_seamless", "meteofrance_seamless")


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
    tz: str = ""             # IANA timezone, e.g. "America/Chicago" — for local-time display


STATIONS: dict[str, Station] = {
    # US — global ensemble + native NWS gridpoint
    "nyc":           Station("nyc",           "KLGA", "us/ny/new-york-city/KLGA",  40.7773, -73.8726, "F", 2, _GLOBAL, True,  "America/New_York"),
    "chicago":       Station("chicago",       "KORD", "us/il/chicago/KORD",        41.9786, -87.9048, "F", 2, _GLOBAL, True,  "America/Chicago"),
    "los-angeles":   Station("los-angeles",   "KLAX", "us/ca/los-angeles/KLAX",    33.9425, -118.4081,"F", 2, _GLOBAL, True,  "America/Los_Angeles"),
    "miami":         Station("miami",         "KMIA", "us/fl/miami/KMIA",          25.7959, -80.2870, "F", 2, _GLOBAL, True,  "America/New_York"),
    "san-francisco": Station("san-francisco", "KSFO", "us/ca/san-francisco/KSFO",  37.6213, -122.3790,"F", 2, _GLOBAL, True,  "America/Los_Angeles"),
    # Tokyo — global + 3 JMA models (national)
    "tokyo":         Station("tokyo",         "RJTT", "jp/tokyo/RJTT",             35.5494, 139.7798, "C", 1, _GLOBAL + _JP_NATIONAL, False, "Asia/Tokyo"),
    # London — global + UKMO + MetNo + Meteofrance (national/European)
    "london":        Station("london",        "EGLC", "gb/london/EGLC",            51.5053,   0.0553, "C", 1, _GLOBAL + _UK_NATIONAL, False, "Europe/London"),

    # --- Additional US cities (validated 2026-05-21, WU Summary OK, 1-day PM match) ---
    "dallas":        Station("dallas",        "KDAL", "us/tx/dallas/KDAL",         32.8481,  -96.8517,"F", 2, _GLOBAL, True,  "America/Chicago"),
    "houston":       Station("houston",       "KHOU", "us/tx/houston/KHOU",        29.6450,  -95.2789,"F", 2, _GLOBAL, True,  "America/Chicago"),
    "seattle":       Station("seattle",       "KSEA", "us/wa/seatac/KSEA",         47.4435, -122.3014,"F", 2, _GLOBAL, True,  "America/Los_Angeles"),
    "denver":        Station("denver",        "KBKF", "us/co/aurora/KBKF",         39.7017, -104.7519,"F", 2, _GLOBAL, True,  "America/Denver"),
    "atlanta":       Station("atlanta",       "KATL", "us/ga/atlanta/KATL",        33.6367,  -84.4281,"F", 2, _GLOBAL, True,  "America/New_York"),

    # --- European cities (validated 2026-05-21) ---
    "paris":         Station("paris",         "LFPB", "fr/bonneuil-en-france/LFPB",48.9589,   2.4408,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Paris"),
    "madrid":        Station("madrid",        "LEMD", "es/madrid/LEMD",            40.4719,  -3.5626, "C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Madrid"),
    "amsterdam":     Station("amsterdam",     "EHAM", "nl/schiphol/EHAM",          52.3086,   4.7639, "C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Amsterdam"),

    # --- Asian cities (validated 2026-05-21) ---
    "beijing":       Station("beijing",       "ZBAA", "cn/beijing/ZBAA",           40.0799, 116.5858, "C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "shanghai":      Station("shanghai",      "ZSPD", "cn/shanghai/ZSPD",          31.1443, 121.8083, "C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "singapore":     Station("singapore",     "WSSS", "sg/singapore/WSSS",          1.3644, 103.9915, "C", 1, _GLOBAL, False, "Asia/Singapore"),
    "jakarta":       Station("jakarta",       "WIHH", "id/jakarta/WIHH",           -6.1275, 106.6537, "C", 1, _GLOBAL, False, "Asia/Jakarta"),

    # --- Americas non-US (validated 2026-05-21) ---
    "toronto":       Station("toronto",       "CYYZ", "ca/mississauga/CYYZ",       43.6772,  -79.6306,"C", 1, _GLOBAL, False, "America/Toronto"),
    "mexico-city":   Station("mexico-city",   "MMMX", "mx/mexico-city/MMMX",      19.4363,  -99.0721,"C", 1, _GLOBAL, False, "America/Mexico_City"),
    "buenos-aires":  Station("buenos-aires",  "SAEZ", "ar/ezeiza/SAEZ",           -34.8222,  -58.5358,"C", 1, _GLOBAL, False, "America/Argentina/Buenos_Aires"),
    "sao-paulo":     Station("sao-paulo",     "SBGR", "br/guarulhos/SBGR",        -23.4356,  -46.4731,"C", 1, _GLOBAL, False, "America/Sao_Paulo"),

    # --- Candidates — confirmed on Polymarket, calibration run 2026-05-22 ---
    # WU paths are best-guess patterns; verify via wu_high_scraper before enabling live accumulator.
    "munich":        Station("munich",        "EDDM", "de/munich/EDDM",            48.3538,   11.7861,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Berlin"),
    "warsaw":        Station("warsaw",        "EPWA", "pl/warsaw/EPWA",            52.1657,   20.9671,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Warsaw"),
    "milan":         Station("milan",         "LIMC", "it/milan/LIMC",             45.6307,    8.7281,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Rome"),
    "helsinki":      Station("helsinki",      "EFHK", "fi/vantaa/EFHK",            60.3172,   24.9633,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Helsinki"),
    "austin":        Station("austin",        "KAUS", "us/tx/austin/KAUS",         30.1945,  -97.6699,"F", 2, _GLOBAL, True,  "America/Chicago"),
    "taipei":        Station("taipei",        "RCSS", "tw/taipei/RCSS",            25.0694,  121.5522,"C", 1, _GLOBAL, False, "Asia/Taipei"),
    "cape-town":     Station("cape-town",     "FACT", "za/cape-town/FACT",        -33.9648,   18.6017,"C", 1, _GLOBAL, False, "Africa/Johannesburg"),
    "qingdao":       Station("qingdao",       "ZSQD", "cn/qingdao/ZSQD",           36.2661,  120.3742,"C", 1, _GLOBAL, False, "Asia/Shanghai"),

    # --- Wave-3 candidates (calibration run 2026-05-22) ---
    "tel-aviv":      Station("tel-aviv",      "LLBG", "il/tel-aviv/LLBG",          32.0005,   34.8706,"C", 1, _GLOBAL, False, "Asia/Jerusalem"),
    "istanbul":      Station("istanbul",      "LTFM", "tr/istanbul/LTFM",          41.2608,   28.7425,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Istanbul"),
    "moscow":        Station("moscow",        "UUWW", "ru/moscow/UUWW",            55.5915,   37.2613,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Moscow"),
    "shenzhen":      Station("shenzhen",      "ZGSZ", "cn/shenzhen/ZGSZ",          22.6393,  113.8107,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "guangzhou":     Station("guangzhou",     "ZGGG", "cn/guangzhou/ZGGG",         23.3924,  113.2990,"C", 1, _GLOBAL, False, "Asia/Shanghai"),

    # --- Wave-4 candidates (calibration run 2026-05-28, ERA5+GFS bias computed) ---
    "ankara":        Station("ankara",        "LTAC", "tr/ankara/LTAC",            40.1281,   32.9951,"C", 1, _GLOBAL + _EU_NATIONAL, False, "Europe/Istanbul"),
    "busan":         Station("busan",         "RKPK", "kr/busan/RKPK",             35.1795,  128.9382,"C", 1, _GLOBAL, False, "Asia/Seoul"),
    "chengdu":       Station("chengdu",       "ZUUU", "cn/chengdu/ZUUU",           30.5785,  103.9473,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "chongqing":     Station("chongqing",     "ZUCK", "cn/chongqing/ZUCK",         29.7192,  106.6418,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "jeddah":        Station("jeddah",        "OEJN", "sa/jeddah/OEJN",            21.6796,   39.1565,"C", 1, _GLOBAL, False, "Asia/Riyadh"),
    "jinan":         Station("jinan",         "ZSJN", "cn/jinan/ZSJN",             36.8572,  117.0160,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "karachi":       Station("karachi",       "OPKC", "pk/karachi/OPKC",           24.9065,   67.1608,"C", 1, _GLOBAL, False, "Asia/Karachi"),
    "kuala-lumpur":  Station("kuala-lumpur",  "WMKK", "my/kuala-lumpur/WMKK",       2.7456,  101.7072,"C", 1, _GLOBAL, False, "Asia/Kuala_Lumpur"),
    "lucknow":       Station("lucknow",       "VILK", "in/lucknow/VILK",           26.7606,   80.8893,"C", 1, _GLOBAL, False, "Asia/Kolkata"),
    "manila":        Station("manila",        "RPLL", "ph/manila/RPLL",            14.5086,  121.0197,"C", 1, _GLOBAL, False, "Asia/Manila"),
    "panama-city":   Station("panama-city",   "MPMG", "pa/panama-city/MPMG",        8.967,   -79.555, "C", 1, _GLOBAL, False, "America/Panama"),  # 2026-06-02: resolves on MPMG (Albrook) per WU URL, not MPTO. NB MPMG is an AUTO station w/ frequently-missing temp — running_max may be sparse.
    "seoul":         Station("seoul",         "RKSI", "kr/incheon/RKSI",           37.4692,  126.4505,"C", 1, _GLOBAL, False, "Asia/Seoul"),
    "wellington":    Station("wellington",    "NZWN", "nz/wellington/NZWN",       -41.3272,  174.8054,"C", 1, _GLOBAL, False, "Pacific/Auckland"),
    "wuhan":         Station("wuhan",         "ZHHH", "cn/wuhan/ZHHH",             30.7838,  114.2081,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
    "zhengzhou":     Station("zhengzhou",     "ZHCC", "cn/zhengzhou/ZHCC",         34.5197,  113.8408,"C", 1, _GLOBAL, False, "Asia/Shanghai"),
}
