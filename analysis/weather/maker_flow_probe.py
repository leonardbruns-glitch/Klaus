#!/usr/bin/env python3
"""
maker_flow_probe.py — Phase-0 flow/overround instrumentation for the coherent
partition-maker thesis (2026-06-01).

STANDALONE + READ-ONLY. Does NOT import or touch the live engine, so it cannot
affect trading and a mid-session interruption leaves the bot untouched. Polls
public Gamma (active weather markets) + data-api /trades (TAKER flow only) and
appends each NEW taker trade to logs/shadow/hot/<date>/maker_flow.jsonl.

WHY: the in-engine maker_shadow recorder logs BOOK snapshots (overround/spread)
but cannot see realized taker flow. A maker earns only if takers cross its
quotes. Joined offline to maker_shadow.jsonl (by token/asset id + time) this
answers the one question that adjudicates the whole maker thesis:
  (1) does taker flow exist on weather buckets, and how much $/day,
  (2) the effective spread/overround takers actually pay, by city + time-of-day,
  (3) does flow concentrate in the locked region (where adverse selection = 0).

No capital, no engine risk. Kill = stop the process.
Run:  python3 analysis/weather/maker_flow_probe.py            # loops every POLL_SEC
      python3 analysis/weather/maker_flow_probe.py --once      # single pass (test)
"""
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

GAMMA        = "https://gamma-api.polymarket.com"
DATA_API     = "https://data-api.polymarket.com"
POLL_SEC     = 180          # /trades returns recent fills; 3-min cadence is plenty
TRADES_LIMIT = 500
BATCH        = 10           # concurrent /trades requests (matches resolution loop)
SEEN_MAX     = 300_000      # bound the in-process dedup set


def _log_dir() -> Path:
    d = (Path(__file__).resolve().parents[2] / "logs" / "shadow" / "hot"
         / datetime.now(timezone.utc).date().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dedup_key(t: dict) -> str:
    """Stable per-trade key, defensive about field-name variants."""
    h = t.get("transactionHash") or t.get("transaction_hash") or ""
    a = t.get("asset") or t.get("asset_id") or t.get("token_id") or ""
    ts = t.get("timestamp") or t.get("ts") or ""
    base = f"{h}|{a}|{ts}"
    if base.strip("|"):
        return base
    return hashlib.md5(json.dumps(t, sort_keys=True).encode()).hexdigest()


async def _get_json(sess, url):
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def fetch_active_weather_markets(sess) -> dict:
    """{condition_id: {q, tokens, end}} for OPEN weather markets (paginated)."""
    out: dict = {}
    offset = 0
    while True:
        page = await _get_json(
            sess, f"{GAMMA}/events?closed=false&limit=100&offset={offset}&tag_slug=weather")
        if not page:
            break
        for ev in page:
            for m in ev.get("markets", []):
                if m.get("closed", False):
                    continue
                cid = m.get("conditionId")
                if not cid:
                    continue
                toks_raw = m.get("clobTokenIds", "[]")
                try:
                    toks = json.loads(toks_raw) if isinstance(toks_raw, str) else toks_raw
                except Exception:
                    toks = []
                out[cid] = {"q": m.get("question", ""), "tokens": toks,
                            "end": m.get("endDate", "")}
        if len(page) < 100:
            break
        offset += len(page)
    return out


async def _poll_trades(sess, cid):
    rows = await _get_json(sess, f"{DATA_API}/trades?market={cid}&limit={TRADES_LIMIT}")
    return cid, (rows or [])


async def one_pass(sess, seen: set, mf) -> tuple[int, int]:
    markets = await fetch_active_weather_markets(sess)
    cids = list(markets.keys())
    n_new = 0
    for i in range(0, len(cids), BATCH):
        batch = cids[i:i + BATCH]
        results = await asyncio.gather(*[_poll_trades(sess, c) for c in batch])
        for cid, trades in results:
            for t in trades:
                if not isinstance(t, dict):
                    continue
                key = _dedup_key(t)
                if key in seen:
                    continue
                seen.add(key)
                n_new += 1
                rec = {"poll_ts": time.time(), "cid": cid,
                       "q": markets[cid]["q"]}
                rec.update(t)   # raw trade fields verbatim (correct names, full coverage)
                mf.write(json.dumps(rec) + "\n")
        await asyncio.sleep(0.3)   # gentle pacing between batches
    mf.flush()
    if len(seen) > SEEN_MAX:
        seen.clear()   # offline analysis re-dedups by the same key; safe to drop
    return len(cids), n_new


async def main():
    once = "--once" in sys.argv
    seen: set = set()
    print(f"[maker_flow_probe] start once={once} poll={POLL_SEC}s", flush=True)
    async with aiohttp.ClientSession() as sess:
        while True:
            t0 = time.time()
            try:
                with (_log_dir() / "maker_flow.jsonl").open("a") as mf:
                    n_mkt, n_new = await one_pass(sess, seen, mf)
                print(f"[maker_flow_probe] {datetime.now(timezone.utc).isoformat()} "
                      f"markets={n_mkt} new_trades={n_new} ({time.time() - t0:.1f}s)",
                      flush=True)
            except Exception as e:
                print(f"[maker_flow_probe] pass error: {e}", flush=True)
            if once:
                break
            await asyncio.sleep(max(5.0, POLL_SEC - (time.time() - t0)))


if __name__ == "__main__":
    asyncio.run(main())
