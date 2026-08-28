"""Refetch last ~36h of 15m+5m BTC updown tape, throttled, with 429 retry."""
import asyncio, json, time, aiohttp

OUT = "/root/Klaus/analysis/crypto/updown_audit"
HDR = {"User-Agent": "Mozilla/5.0"}
now = int(time.time())

def epochs(step, hours):
    end = now - now % step - 2 * step
    return [(f"btc-updown-{'5m' if step==300 else '15m'}-{w}", w, step)
            for w in range(end - hours*3600, end + 1, step)]
SLUGS = epochs(900, 36) + epochs(300, 36)

async def get(sess, url, tries=5):
    for i in range(tries):
        try:
            async with sess.get(url) as r:
                if r.status == 429:
                    await asyncio.sleep(2 + 2*i); continue
                if r.status != 200:
                    return None
                return await r.json()
        except Exception:
            await asyncio.sleep(1 + i)
    return None

async def main():
    conn = aiohttp.TCPConnector(limit=4)
    async with aiohttp.ClientSession(connector=conn, headers=HDR,
                                     timeout=aiohttp.ClientTimeout(total=30)) as sess:
        mkts = []
        for i in range(0, len(SLUGS), 10):
            q = "&".join(f"slug={s}" for s,_,_ in SLUGS[i:i+10])
            evs = await get(sess, f"https://gamma-api.polymarket.com/events?{q}") or []
            for ev in evs:
                for m in ev.get("markets") or []:
                    if not m.get("closed"): continue
                    try:
                        op = json.loads(m.get("outcomePrices") or "[]")
                        oc = json.loads(m.get("outcomes") or "[]")
                    except Exception: continue
                    if len(op)!=2 or float(op[0])+float(op[1])!=1.0: continue
                    mkts.append({"slug": ev.get("slug"), "conditionId": m["conditionId"],
                                 "winner": oc[0] if float(op[0])==1.0 else oc[1],
                                 "volume": m.get("volumeNum")})
            await asyncio.sleep(0.2)
        print(f"resolved markets: {len(mkts)}", flush=True)
        n = 0
        with open(f"{OUT}/trades_fresh.jsonl","w") as f:
            for j, m in enumerate(mkts):
                offset = 0
                for _ in range(12):
                    page = await get(sess, f"https://data-api.polymarket.com/trades?market={m['conditionId']}&limit=500&offset={offset}")
                    if page is None: print(f"FAIL {m['slug']}", flush=True); break
                    for t in page:
                        keep = {k: t.get(k) for k in ("proxyWallet","side","price","size","timestamp","outcome")}
                        keep["_slug"] = m["slug"]; keep["_winner"] = m["winner"]
                        f.write(json.dumps(keep)+"\n")
                    n += len(page)
                    if len(page) < 500: break
                    offset += 500
                await asyncio.sleep(0.25)
                if j % 60 == 0: print(f"{j}/{len(mkts)} rows={n}", flush=True)
        print(f"DONE rows={n}", flush=True)

asyncio.run(main())
