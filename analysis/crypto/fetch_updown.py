"""Fetch resolved BTC updown markets (15m: 7d, 5m: 3d) + full taker tape.
Writes updown_audit/markets.json + updown_audit/trades.jsonl"""
import asyncio, json, time, aiohttp

OUT = "/root/Klaus/analysis/crypto/updown_audit"
HDR = {"User-Agent": "Mozilla/5.0"}
now = int(time.time())

def epochs(step, days):
    end = now - now % step - 2 * step          # skip unresolved tail
    start = end - days * 86400
    return [(f"btc-updown-{'5m' if step==300 else '15m'}-{w}", w, step)
            for w in range(start, end + 1, step)]

SLUGS = epochs(900, 7) + epochs(300, 3)

async def gamma_batch(sess, batch):
    q = "&".join(f"slug={s}" for s, _, _ in batch)
    async with sess.get(f"https://gamma-api.polymarket.com/events?{q}") as r:
        if r.status != 200:
            return []
        evs = await r.json()
    out = []
    for ev in evs or []:
        for m in ev.get("markets") or []:
            if not m.get("closed"):
                continue
            try:
                op = json.loads(m.get("outcomePrices") or "[]")
                oc = json.loads(m.get("outcomes") or "[]")
            except Exception:
                continue
            if len(op) != 2 or float(op[0]) + float(op[1]) != 1.0:
                continue
            winner = oc[0] if float(op[0]) == 1.0 else oc[1]
            slug = (ev.get("slug") or "")
            out.append({"slug": slug, "conditionId": m["conditionId"],
                        "winner": winner, "volume": m.get("volumeNum"),
                        "endDate": m.get("endDate")})
    return out

async def trades(sess, cid):
    rows, offset = [], 0
    for _ in range(12):
        url = f"https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={offset}"
        try:
            async with sess.get(url) as r:
                if r.status != 200:
                    break
                page = await r.json()
        except Exception:
            break
        rows += page
        if len(page) < 500:
            break
        offset += 500
    return rows

async def main():
    conn = aiohttp.TCPConnector(limit=12)
    async with aiohttp.ClientSession(connector=conn, headers=HDR,
                                     timeout=aiohttp.ClientTimeout(total=30)) as sess:
        mkts = []
        for i in range(0, len(SLUGS), 10):
            mkts += await gamma_batch(sess, SLUGS[i:i+10])
            if i % 200 == 0:
                print(f"gamma {i}/{len(SLUGS)} -> {len(mkts)} resolved", flush=True)
        json.dump(mkts, open(f"{OUT}/markets.json", "w"))
        print(f"markets: {len(mkts)}", flush=True)

        sem = asyncio.Semaphore(12)
        n_tr = 0
        async def one(m):
            nonlocal n_tr
            async with sem:
                rows = await trades(sess, m["conditionId"])
            for t in rows:
                t["_slug"] = m["slug"]; t["_winner"] = m["winner"]
            n_tr += len(rows)
            return rows
        with open(f"{OUT}/trades.jsonl", "w") as f:
            for i in range(0, len(mkts), 50):
                chunk = await asyncio.gather(*(one(m) for m in mkts[i:i+50]))
                for rows in chunk:
                    for t in rows:
                        keep = {k: t.get(k) for k in
                                ("proxyWallet","side","price","size","timestamp",
                                 "outcome","outcomeIndex","_slug","_winner")}
                        f.write(json.dumps(keep) + "\n")
                print(f"trades {min(i+50,len(mkts))}/{len(mkts)} rows={n_tr}", flush=True)

asyncio.run(main())
