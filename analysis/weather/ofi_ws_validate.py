#!/usr/bin/env python3
"""
ofi_ws_validate.py — READ-ONLY. Validate the CLOB market WS `last_trade_price`
feed against the data-api /trades tape the live OFI currently reads, BEFORE
rewiring OFI to the WS (latency: 180s poll -> sub-second push).

Two questions:
  (1) Does the market-WS deliver last_trade_price events for weather tokens at all?
  (2) Does WS.side mean the same as data-api side (taker side per token)?

Method (fast): seed recent weather token ids + their (txhash -> side/outcome)
from the live maker_flow.jsonl tail, subscribe those tokens to the WS, capture
last_trade_price for RUN_S, keep extending the file map, then match by txhash.

Run: python3 analysis/weather/ofi_ws_validate.py [seconds]   (default 150)
"""
import asyncio, json, sys, time, glob, os
from collections import Counter
import aiohttp

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RUN_S  = int(sys.argv[1]) if len(sys.argv) > 1 else 150


def latest_maker_flow():
    files = sorted(glob.glob("logs/shadow/hot/*/maker_flow.jsonl"))
    return files[-1] if files else None


def read_recent(path, since_ts, tail_bytes=8_000_000):
    """Return (txmap, tokens) from the tail of maker_flow.jsonl.
    txmap[txhash] = {'side','outcome','asset'}; tokens = set of recent asset ids."""
    txmap, tokens = {}, set()
    sz = os.path.getsize(path)
    with open(path, "rb") as fh:
        if sz > tail_bytes:
            fh.seek(sz - tail_bytes)
            fh.readline()
        chunk = fh.read().decode("utf-8", "ignore")
    for line in chunk.splitlines():
        if "highest-temperature" not in line:
            continue
        try:
            r = json.loads(line)
            ts = float(r.get("timestamp", 0))
        except Exception:
            continue
        if ts < since_ts:
            continue
        a = str(r.get("asset", "") or "")
        th = (r.get("transactionHash") or "").lower()
        if a:
            tokens.add(a)
        if th:
            txmap[th] = {"side": str(r.get("side", "")).upper(),
                         "outcome": str(r.get("outcome", "")), "asset": a}
    return txmap, tokens


async def main():
    path = latest_maker_flow()
    if not path:
        print("no maker_flow.jsonl found"); return
    stop_at = time.time() + RUN_S
    txmap, tokens = read_recent(path, time.time() - 1800)
    tokens = [t for t in tokens if t]
    print(f"[seed] {len(tokens)} recent tokens, {len(txmap)} txhashes from {path}", flush=True)
    if not tokens:
        print("no recent weather tokens in file tail"); return

    ws_events, type_counts = {}, Counter()
    async with aiohttp.ClientSession() as sess:
        async with sess.ws_connect(WS_URL, timeout=20, heartbeat=10) as ws:
            for i in range(0, len(tokens), 200):
                await ws.send_str(json.dumps({
                    "auth": {}, "type": "subscribe", "channel": "market",
                    "assets_ids": tokens[i:i + 200], "custom_feature_enabled": True}))
                await asyncio.sleep(0.2)
            print(f"[ws] subscribed {len(tokens)} tokens", flush=True)
            last_log = time.time()
            while time.time() < stop_at:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                except asyncio.TimeoutError:
                    msg = None
                if msg is not None:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            evs = json.loads(msg.data)
                        except Exception:
                            evs = []
                        if not isinstance(evs, list):
                            evs = [evs]
                        for ev in evs:
                            et = ev.get("event_type", ev.get("type", "?"))
                            type_counts[et] += 1
                            if et == "last_trade_price":
                                th = (ev.get("transaction_hash") or ev.get("transactionHash") or "").lower()
                                if th:
                                    ws_events[th] = {
                                        "asset": str(ev.get("asset_id") or ev.get("asset") or ""),
                                        "side": str(ev.get("side", "")).upper(),
                                        "market": str(ev.get("market", "")),
                                        "keys": sorted(ev.keys()), "txh": th}
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        print(f"[ws] closed/error {msg.type}", flush=True)
                        break
                if time.time() - last_log > 20:
                    last_log = time.time()
                    print(f"[poll] types={dict(type_counts)} ltp={type_counts['last_trade_price']}", flush=True)

        # ── validate side semantics against data-api /trades (by market+txhash) ──
        print("\n=== event type counts ===", dict(type_counts))
        if ws_events:
            print("WS last_trade_price keys:", next(iter(ws_events.values()))["keys"])
        print(f"[settle] sleeping 75s so data-api ingests the {len(ws_events)} WS trades...", flush=True)
        await asyncio.sleep(75)
        markets = {w["market"] for w in ws_events.values() if w["market"]}
        api: dict = {}
        for c in markets:
            try:
                async with sess.get(f"https://data-api.polymarket.com/trades?market={c}&limit=500",
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    rows = await r.json() if r.status == 200 else []
            except Exception:
                rows = []
            for t in (rows or []):
                th = (t.get("transactionHash") or "").lower()
                if th:
                    api[th] = {"side": str(t.get("side", "")).upper(),
                               "outcome": str(t.get("outcome", "")), "asset": str(t.get("asset", ""))}

    matched = [(ws_events[k], api[k]) for k in ws_events if k in api]
    print(f"\nmatched WS↔data-api by txhash: {len(matched)} / ws_ltp={len(ws_events)}")
    agree = sum(1 for w, a in matched if w["side"] == a["side"])
    amatch = sum(1 for w, a in matched if w["asset"] == a["asset"])
    print(f"side agreement (WS.side == api.side): {agree}/{len(matched)}")
    print(f"asset_id agreement (WS.asset_id == api.asset): {amatch}/{len(matched)}")
    for w, a in matched[:15]:
        print(f"  WS side={w['side']:4} | api side={a['side']:4} outcome={a['outcome']:3} "
              f"asset_match={w['asset']==a['asset']}")


if __name__ == "__main__":
    asyncio.run(main())
