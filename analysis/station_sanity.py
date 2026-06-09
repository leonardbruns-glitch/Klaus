import sys, json, urllib.request
sys.path.insert(0, '/root/Klaus')
from strategy.resolution_mapper import _extract_wu_station, STATION_COORDS
from strategy.weather_arb import CITY_ICAO

url = 'https://gamma-api.polymarket.com/events?tag=weather&active=true&limit=200'
req = urllib.request.Request(url, headers={'User-Agent': 'Klaus/1.0'})
data = json.loads(urllib.request.urlopen(req, timeout=15).read())

seen = set()
rows = []
for ev in data:
    for mkt in ev.get('markets', []):
        desc = mkt.get('description', '') or ''
        end_date = (mkt.get('endDate', '') or '')[:10]
        if end_date != '2026-05-27':
            continue
        wu = _extract_wu_station(desc)
        city = (mkt.get('groupItemTitle', '') or ev.get('title', '') or '')[:28]
        key = (city, wu)
        if key in seen:
            continue
        seen.add(key)
        in_sc = wu in STATION_COORDS if wu else False
        city_icao = CITY_ICAO.get(city.strip())
        same = (wu == city_icao) if (wu and city_icao) else None
        rows.append((city, wu, city_icao, in_sc, same))

# Sort: problems first
rows.sort(key=lambda r: (r[3], r[4] is not False), reverse=False)

print(f"{'City':28}  {'WU station':12}  {'CITY_ICAO':10}  {'SC':7}  note")
print("-" * 80)
for city, wu, city_icao, in_sc, same in rows:
    sc_flag = "OK" if in_sc else "MISSING"
    note = ""
    if not wu:
        note = "NO WU URL"
    elif not in_sc:
        note = "<< ADD TO STATION_COORDS"
    elif same is False:
        note = "<< MISMATCH vs CITY_ICAO"
    print(f"{city:28}  {str(wu):12}  {str(city_icao):10}  {sc_flag:7}  {note}")
