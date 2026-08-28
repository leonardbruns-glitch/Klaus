"""Build authoritative {city: resolution_station} from Gamma resolutionSource URLs.
The WU URL tail (…/KXXX) IS the station Polymarket resolves on — which differs from
our primary ICAO for some cities (Dallas→KDAL not KDFW, Houston→KHOU not KIAH)."""
import json, urllib.request, re, sys
from datetime import date, timedelta
UA={"User-Agent":"Mozilla/5.0"}
M=["january","february","march","april","may","june","july","august","september","october","november","december"]
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20))
CITIES=["miami","chicago","dallas","houston","austin","los-angeles","atlanta","seattle",
        "phoenix","new-york","denver","boston","philadelphia","washington-dc","las-vegas",
        "san-francisco","san-antonio","san-diego","sacramento","portland","minneapolis","detroit"]
out={}
today=date.today()
for city in CITIES:
    found=None
    for back in range(1,9):
        d=today-timedelta(days=back)
        slug=f"highest-temperature-in-{city}-on-{M[d.month-1]}-{d.day}-{d.year}"
        try: ev=get(f"https://gamma-api.polymarket.com/events/slug/{slug}")
        except Exception: continue
        rs=ev.get("resolutionSource","") or ""
        m=re.search(r"/([A-Z]{4})\b", rs)
        if m:
            found={"station":m.group(1),"wu":rs}; break
    if found:
        out[city]=found["station"]
        print(f"{city:<16} -> {found['station']}   {found['wu']}")
    else:
        print(f"{city:<16} -> (no resolved event found)")
json.dump(out, open("/root/Klaus/config/wu_resolution_stations.json","w"), indent=2)
print(f"\nsaved {len(out)} stations -> config/wu_resolution_stations.json")
