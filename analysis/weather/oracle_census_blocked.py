#!/usr/bin/env python3
"""Oracle-match census for the M1β blocked cities (VHHH / RJTT / ZGSZ / WSSS).

Question: for each blocked city, does an accessible obs source reproduce the
Gamma-resolved winner bucket at >=99%? If yes, that source IS (effectively)
the oracle and the city can be un-blocked for M1β lockout-NO with a clean
provenance feed.

Per-market oracle (from market descriptions, 2026-06-09):
  Tokyo     -> WU page for RJTT (Haneda airport), whole deg C
  Singapore -> WU page for WSSS (Changi airport), whole deg C
  Shenzhen  -> WU page for ZGSZ (Bao'an airport), whole deg C
  Hong Kong -> HKO Observatory "Absolute Daily Max", ONE DECIMAL deg C
               (different station from VHHH + finer precision)

Method:
  1. Gamma day-by-day closed weather events -> winner bucket per (city, local date)
  2. IEM METAR archive -> daily max (local day) per ICAO
  3. HKO CLMTEMP open-data -> HKO Observatory daily max for Hong Kong
  4. match rate per (city, source)
"""
import json, re, sys, time, datetime, urllib.request, urllib.parse
from collections import defaultdict

GAMMA = "https://gamma-api.polymarket.com"
DATE_MIN = "2026-04-10"
DATE_MAX = "2026-06-08"

CITIES = {
    "Tokyo":     {"icao": "RJTT", "tz_off": 9},
    "Hong Kong": {"icao": "VHHH", "tz_off": 8},
    "Shenzhen":  {"icao": "ZGSZ", "tz_off": 8},
    "Singapore": {"icao": "WSSS", "tz_off": 8},
}

def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-census"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def http_text(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-census"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

# ── 1. Gamma winner buckets ──────────────────────────────────────────────────
BUCKET_RE = re.compile(
    r"be (?P<a>-?\d+)(?:-(?P<b>-?\d+))?°C(?: (?P<rel>or below|or higher))? on", re.I)

def parse_bucket(q):
    m = BUCKET_RE.search(q)
    if not m: return None
    a = int(m.group("a")); b = m.group("b"); rel = (m.group("rel") or "").lower()
    if rel == "or below":  return (None, a)
    if rel == "or higher": return (a, None)
    if b is not None:      return (a, int(b))
    return (a, a)

DATE_RE = re.compile(r"on (\w+ \d+)\?")

def fetch_winners():
    winners = {}   # (city, iso_date) -> (lo, hi, question)
    d = datetime.date.fromisoformat(DATE_MIN)
    dmax = datetime.date.fromisoformat(DATE_MAX)
    while d <= dmax:
        nxt = d + datetime.timedelta(days=1)
        offset = 0
        while True:
            url = (f"{GAMMA}/events?tag_slug=weather&limit=200&offset={offset}"
                   f"&closed=true&end_date_min={d}&end_date_max={nxt}")
            try:
                page = http_json(url)
            except Exception as e:
                print(f"  gamma {d} offset={offset}: {e}", file=sys.stderr)
                break
            if not page: break
            for ev in page:
                for mkt in ev.get("markets", []):
                    q = mkt.get("question", "")
                    city = next((c for c in CITIES if c in q), None)
                    if not city or "highest temperature" not in q.lower():
                        continue
                    op = mkt.get("outcomePrices") or "[]"
                    if isinstance(op, str):
                        try: op = json.loads(op)
                        except Exception: continue
                    if len(op) != 2: continue
                    yes = float(op[0])
                    if yes < 0.99: continue          # not the winner bucket
                    bk = parse_bucket(q)
                    if not bk: continue
                    # end date = the market's local day; use endDate field
                    ed = (mkt.get("endDate") or "")[:10]
                    if not ed: continue
                    winners[(city, ed)] = (bk[0], bk[1], q)
            offset += 200
            if len(page) < 200: break
        d = nxt
        time.sleep(0.2)
    return winners

# ── 2. IEM METAR daily max ───────────────────────────────────────────────────
def fetch_iem_daily_max(icao, tz_off):
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
           f"station={icao}&data=tmpc&year1=2026&month1=4&day1=8"
           "&year2=2026&month2=6&day2=9&tz=Etc/UTC&format=onlycomma"
           "&latlon=no&missing=M&trace=T&report_type=3&report_type=4")
    txt = http_text(url, timeout=120)
    daymax = {}
    for ln in txt.splitlines()[1:]:
        parts = ln.split(",")
        if len(parts) < 3: continue
        ts, val = parts[1], parts[2]
        if val in ("M", ""): continue
        try:
            t = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M")
            v = float(val)
        except ValueError:
            continue
        local = t + datetime.timedelta(hours=tz_off)
        k = local.date().isoformat()
        if k not in daymax or v > daymax[k]:
            daymax[k] = v
    return daymax

# ── 3. HKO Observatory daily max (CLMTEMP = daily max temp, station HKO) ─────
def fetch_hko_daily_max():
    out = {}
    url = ("https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?"
           "dataType=CLMMAXT&year=2026&rformat=json&station=HKO")
    try:
        d = http_json(url, timeout=30)
    except Exception as e:
        print(f"  HKO fetch failed: {e}", file=sys.stderr)
        return out
    for row in d.get("data", []):
        try:
            y, m, day, v = int(row[0]), int(row[1]), int(row[2]), float(row[3])
            out[datetime.date(y, m, day).isoformat()] = v
        except (ValueError, IndexError, TypeError):
            continue
    return out

# ── 4. join ──────────────────────────────────────────────────────────────────
def in_bucket(maxc, lo, hi, whole=True):
    v = round(maxc) if whole else round(maxc, 1)
    if lo is not None and v < lo: return False
    if hi is not None and v > hi: return False
    return True

def main():
    print("fetching Gamma winners …")
    winners = fetch_winners()
    bycity = defaultdict(dict)
    for (city, ed), w in winners.items():
        bycity[city][ed] = w
    for c in CITIES:
        print(f"  {c}: {len(bycity[c])} resolved days")

    print("fetching IEM METAR daily max …")
    iem = {}
    for c, cfg in CITIES.items():
        try:
            iem[c] = fetch_iem_daily_max(cfg["icao"], cfg["tz_off"])
            print(f"  {cfg['icao']}: {len(iem[c])} days")
        except Exception as e:
            iem[c] = {}
            print(f"  {cfg['icao']}: FAILED {e}", file=sys.stderr)

    print("fetching HKO Observatory daily max …")
    hko = fetch_hko_daily_max()
    print(f"  HKO: {len(hko)} days")

    results = {}
    for city in CITIES:
        days = bycity[city]
        rows = []
        for ed, (lo, hi, q) in sorted(days.items()):
            mx_metar = iem[city].get(ed)
            mx_hko = hko.get(ed) if city == "Hong Kong" else None
            rows.append((ed, lo, hi, mx_metar, mx_hko, q))
        n = len(rows)
        m_ok = sum(1 for r in rows if r[3] is not None and in_bucket(r[3], r[1], r[2]))
        m_n  = sum(1 for r in rows if r[3] is not None)
        h_ok = sum(1 for r in rows if r[4] is not None and in_bucket(r[4], r[1], r[2], whole=False))
        h_n  = sum(1 for r in rows if r[4] is not None)
        results[city] = dict(days=n, metar_n=m_n, metar_match=m_ok,
                             hko_n=h_n, hko_match=h_ok)
        print(f"\n=== {city} (n={n} resolved days) ===")
        if m_n: print(f"  METAR ({CITIES[city]['icao']}): {m_ok}/{m_n} = {m_ok/m_n*100:.1f}%")
        if h_n: print(f"  HKO Observatory:               {h_ok}/{h_n} = {h_ok/h_n*100:.1f}%")
        for r in rows:
            if r[3] is None: continue
            ok = in_bucket(r[3], r[1], r[2])
            okh = in_bucket(r[4], r[1], r[2], whole=False) if r[4] is not None else None
            if not ok or okh is False:
                print(f"  MISS {r[0]} bucket=({r[1]},{r[2]}) metar_max={r[3]:.1f}"
                      + (f" hko_max={r[4]:.1f}" if r[4] is not None else "")
                      + f"  [{r[5][:60]}]")
    with open("/tmp/oracle_census_blocked.json", "w") as f:
        json.dump({"winners": {f"{c}|{d}": w[:2] for (c, d), w in winners.items()},
                   "results": results}, f)
    print("\nsaved /tmp/oracle_census_blocked.json")

if __name__ == "__main__":
    main()
