#!/usr/bin/env python3
"""PEAKSCALP backtest — winner-bucket convergence capture after the official
feed knew.

For each resolved (city, day) max-temp ladder, June 1-9:
  t*  = first UTC time the official hourly running max entered the FINAL
        winner bucket (IEM routine METARs = oracle-grade source).
  Then every data-api taker-BUY-YES print on the winner bucket AFTER t* is
  capture that was actually traded: profit-if-held = (0.999 - price) * size.

Split by price band and by latency-after-t* band: the 0-15 min slice is the
part our NMS/METAR feeds (9-28 min ahead of AWC) can reach before slow players.

Excludes Hong Kong (HKO oracle != IEM METAR) and Shenzhen (wrong oracle).
"""
import json, sys, glob, time, urllib.request, urllib.parse
from io import StringIO
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import ICAO_UTC_OFFSET_H, _parse_outcome

HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
DAY_MIN, DAY_MAX = "2026-06-01", "2026-06-09"
BLOCK_CITY = {"hong kong", "shenzhen"}
PRICE_BANDS = [(0.0, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 0.97), (0.97, 0.99)]
LAT_BANDS = [(0, 300), (300, 900), (900, 3600), (3600, 10**9)]  # sec after t*
SELL = 0.999

def get(u, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers=HDR)
            return json.loads(urllib.request.urlopen(req, timeout=25).read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.0)

def city_icao_map():
    m = {}
    for fp in glob.glob("/root/Klaus/logs/shadow/hot/*/metar_lockout.jsonl"):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            c, i = r.get("city"), r.get("icao")
            if c and i:
                m[c.strip().lower()] = i
        if len(m) > 45:
            break
    return m

def iem_hourly(icao, d1, d2):
    """routine METARs (report_type=2), temp in °C, list of (ts_utc, temp_c)."""
    p = urllib.parse.urlencode({
        "station": icao, "data": "tmpf",
        "year1": d1.year, "month1": d1.month, "day1": d1.day,
        "year2": d2.year, "month2": d2.month, "day2": d2.day,
        "tz": "UTC", "format": "onlycomma", "latlon": "no", "direct": "no",
        "report_type": "2",
    })
    url = f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?{p}"
    req = urllib.request.Request(url, headers=HDR)
    raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
    out = []
    for ln in raw.strip().split("\n"):
        if ln.startswith("#") or ln.startswith("station"):
            continue
        parts = ln.split(",")
        if len(parts) < 3:
            continue
        try:
            ts = datetime.fromisoformat(parts[1]).replace(tzinfo=timezone.utc)
            tf = float(parts[2])
        except Exception:
            continue
        out.append((ts, (tf - 32.0) * 5.0 / 9.0))
    return sorted(out)

def main():
    c2i = city_icao_map()
    print(f"city->icao: {len(c2i)} known")

    # 1) resolved max-temp ladders with winner + bucket bounds
    ladders = []
    d = datetime.fromisoformat(DAY_MIN).date()
    dmax = datetime.fromisoformat(DAY_MAX).date()
    while d <= dmax:
        nxt = d + timedelta(days=1)
        evs = get(f"https://gamma-api.polymarket.com/events?tag_slug=weather&limit=100"
                  f"&closed=true&end_date_min={d}&end_date_max={nxt}")
        for ev in evs:
            t = (ev.get("title") or "").lower()
            if not t.startswith("highest temperature in"):
                continue
            city = t.split("highest temperature in ")[1].split(" on ")[0].strip()
            if city in BLOCK_CITY or city not in c2i:
                continue
            for m in ev.get("markets", []):
                pr = m.get("outcomePrices")
                pr = json.loads(pr) if isinstance(pr, str) else pr
                try:
                    if float(pr[0]) <= 0.5:
                        continue
                except Exception:
                    continue
                lo, hi, is_c = _parse_outcome(m.get("question", ""))
                ladders.append({"city": city, "icao": c2i[city], "day": str(d),
                                "cid": m["conditionId"], "q": m.get("question", ""),
                                "lo": lo, "hi": hi, "is_c": is_c})
        d = nxt
        time.sleep(0.15)
    print(f"resolved city-days with winner: {len(ladders)}")

    # 2) IEM obs per station (one fetch each)
    obs = {}
    for icao in sorted({L["icao"] for L in ladders}):
        try:
            obs[icao] = iem_hourly(icao, datetime(2026, 5, 31), datetime(2026, 6, 11))
        except Exception as e:
            print(f"  IEM fail {icao}: {e}")
        time.sleep(0.3)
    print(f"IEM stations: {len(obs)}")

    # 3) per ladder: t* then prints
    band_cap = defaultdict(float); band_n = defaultdict(int)
    lat_cap = defaultdict(float)
    daily = defaultdict(float)
    rows = []
    for L in ladders:
        o = obs.get(L["icao"])
        if not o or L["lo"] is None:
            continue
        tz_h = ICAO_UTC_OFFSET_H.get(L["icao"], 0)
        # local-day obs for this end_date
        day0 = datetime.fromisoformat(L["day"]).replace(tzinfo=timezone.utc) - timedelta(hours=tz_h)
        day1 = day0 + timedelta(hours=24)
        run, tstar = -999.0, None
        viol = False
        for ts, tc in o:
            if not (day0 <= ts < day1):
                continue
            run = max(run, tc)
            if tstar is None and run >= L["lo"]:
                tstar = ts
            if L["hi"] is not None and run >= L["hi"]:
                viol = True   # ran past the winner bucket?! parse/oracle mismatch
        if tstar is None or viol:
            rows.append({**L, "tstar": None, "skip": "no_tstar" if tstar is None else "ran_past"})
            continue
        # prints (paginate)
        prints = []
        off = 0
        while True:
            tr = get(f"https://data-api.polymarket.com/trades?market={L['cid']}&limit=500&offset={off}")
            if not tr:
                break
            prints.extend(tr)
            if len(tr) < 500 or off > 4000:
                break
            off += 500
            time.sleep(0.1)
        cap_day = 0.0
        for x in prints:
            try:
                px, sz = float(x["price"]), float(x["size"])
                ts = int(x["timestamp"])
            except Exception:
                continue
            if x.get("outcome") != "Yes" or x.get("side") != "BUY":
                continue
            dt_s = ts - int(tstar.timestamp())
            if dt_s < 0 or px > 0.99:
                continue
            profit = (SELL - px) * sz
            cap_day += profit
            for blo, bhi in PRICE_BANDS:
                if blo <= px < bhi:
                    band_cap[(blo, bhi)] += profit
                    band_n[(blo, bhi)] += 1
            for llo, lhi in LAT_BANDS:
                if llo <= dt_s < lhi:
                    lat_cap[(llo, lhi)] += profit
        daily[L["day"]] += cap_day
        rows.append({**L, "tstar": tstar.isoformat(), "cap": round(cap_day, 2),
                     "n_prints": len(prints)})
        time.sleep(0.1)

    ok = [r for r in rows if r.get("tstar")]
    print(f"\nscored city-days: {len(ok)} (skipped {len(rows)-len(ok)})")
    print("\ncapture by PRICE band (taker-BUY-YES prints after t*, profit to 0.999):")
    for b in PRICE_BANDS:
        print(f"  [{b[0]:.2f},{b[1]:.2f}): ${band_cap[b]:9.2f}  prints={band_n[b]}")
    print("\ncapture by LATENCY after t*:")
    for b in LAT_BANDS:
        lbl = f"{b[0]//60}-{b[1]//60 if b[1]<10**9 else 'inf'}min"
        print(f"  {lbl:>12}: ${lat_cap[b]:9.2f}")
    print("\nper-day total capture:")
    for dday in sorted(daily):
        print(f"  {dday}: ${daily[dday]:8.2f}")
    tot = sum(daily.values())
    print(f"  TOTAL ${tot:.2f} over {len(daily)} days = ${tot/max(1,len(daily)):.2f}/day")
    top = sorted(ok, key=lambda r: -r.get("cap", 0))[:10]
    print("\ntop city-days:")
    for r in top:
        print(f"  {r['city']:<14} {r['day']} ${r['cap']:8.2f}  t*={r['tstar'][11:16]}Z  {r['q'][:50]}")
    json.dump(rows, open("/tmp/peakscalp_backtest.json", "w"), default=str)
    print("\nwrote /tmp/peakscalp_backtest.json")

if __name__ == "__main__":
    main()
