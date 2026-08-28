"""Deep-dive top updown winners via data-api /activity (end= pagination)."""
import json, sys, time, urllib.request, collections

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=20))

def activity(addr, max_pages=30):
    rows, end = [], int(time.time())
    for _ in range(max_pages):
        try:
            page = get(f"https://data-api.polymarket.com/activity?user={addr}&limit=500&end={end}")
        except Exception as e:
            print("  fetch err:", e); break
        if not page: break
        rows += page
        ts = min(r["timestamp"] for r in page)
        if len(page) < 500 or ts >= end: break
        end = ts
        time.sleep(0.25)
    return rows

for addr in sys.argv[1:]:
    rows = activity(addr)
    types = collections.Counter(r["type"] for r in rows)
    trades = [r for r in rows if r.get("type") == "TRADE"]
    updown = [r for r in trades if "updown" in (r.get("slug") or "")]
    rebates = [r for r in rows if "REBATE" in r.get("type","")]
    print(f"\n########## {addr}")
    print(f"rows {len(rows)} types {dict(types)}")
    print(f"rebate total: ${sum(float(r.get('usdcSize') or 0) for r in rebates):,.0f} across {len(rebates)} rows")
    if not updown: continue
    ts = [r["timestamp"] for r in updown]
    print(f"updown trades {len(updown)} span {time.strftime('%m-%d %H:%M', time.gmtime(min(ts)))} -> {time.strftime('%m-%d %H:%M', time.gmtime(max(ts)))} UTC")
    ab = collections.Counter(); tb = collections.Counter(); pb = collections.Counter()
    sizes = []; sells = 0
    buy_vol = buy_ev = 0.0
    for r in updown:
        slug = r["slug"]
        try: w = int(slug.rsplit("-",1)[1])
        except: continue
        step = 300 if "-5m-" in slug else 900
        trel = (w + step) - r["timestamp"]
        p = float(r["price"]); s = float(r["size"])
        ab[(slug.split("-updown")[0], "5m" if step==300 else "15m")] += 1
        sizes.append(p*s)
        if r["side"] == "SELL": sells += 1; continue
        for lo,hi in [(-1e9,0),(0,5),(5,15),(15,30),(30,60),(60,120),(120,300),(300,1800)]:
            if lo <= trel < hi: tb[(lo,hi)] += 1; break
        for plo,phi in [(0,0.5),(0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,0.95),(0.95,0.995),(0.995,1.01)]:
            if plo <= p < phi: pb[(plo,phi)] += 1; break
    print("assets:", dict(ab.most_common(8)))
    print("BUY t_rel(s):", {f"{int(lo)}-{int(hi)}": n for (lo,hi),n in sorted(tb.items())})
    print("BUY px:", {f"{plo}-{phi}": n for (plo,phi),n in sorted(pb.items())})
    sizes.sort()
    print(f"clip $ med/p90/max: {sizes[len(sizes)//2]:.0f}/{sizes[int(len(sizes)*0.9)]:.0f}/{sizes[-1]:.0f}  SELLs: {sells}/{len(updown)}")
