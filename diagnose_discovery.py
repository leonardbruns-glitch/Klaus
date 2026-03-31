"""
Standalone diagnostic: test market discovery from Gamma and CLOB APIs.
Run: python3 diagnose_discovery.py
"""
import asyncio
import time
import sys

try:
    import aiohttp
except ImportError:
    print("ERROR: aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)


GAMMA = "https://gamma-api.polymarket.com"
CLOB  = "https://clob.polymarket.com"

ASSETS = ["BTC", "ETH", "SOL"]
SLUG_ALIASES = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}


def _extract_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw["data"], list):
            return raw["data"]
        if "markets" in raw and isinstance(raw["markets"], list):
            return raw["markets"]
        if raw.get("conditionId") or raw.get("condition_id"):
            return [raw]
    return []


def is_updown(m: dict) -> bool:
    slug = (m.get("slug") or m.get("market_slug") or "").lower()
    q    = m.get("question", "").lower()
    if not ("updown" in slug or "up-or-down" in slug or "up or down" in q or "go up or down" in q):
        return False
    return "5m" in slug or "15m" in slug or "5 min" in q or "15 min" in q


async def run():
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:

        # ── Test 1: Gamma bulk scan ────────────────────────────────────────────
        print("\n=== Test 1: Gamma bulk scan (active, limit=500) ===")
        try:
            async with sess.get(
                f"{GAMMA}/markets",
                params={"active": "true", "closed": "false", "limit": "500"},
            ) as r:
                print(f"  Status: {r.status}")
                if r.status == 200:
                    raw = await r.json()
                    print(f"  Response type: {type(raw).__name__}")
                    if isinstance(raw, dict):
                        print(f"  Top-level keys: {list(raw.keys())[:10]}")
                    markets = _extract_list(raw)
                    print(f"  Extracted markets: {len(markets)}")
                    updown_ms = [m for m in markets if is_updown(m)]
                    print(f"  Updown markets: {len(updown_ms)}")
                    for m in updown_ms[:5]:
                        slug = m.get("slug") or m.get("market_slug") or "?"
                        print(f"    slug={slug[:60]}  q={m.get('question','')[:60]}")
                    if not updown_ms:
                        # Show first 5 slugs to understand format
                        print("  First 5 slugs from bulk:")
                        for m in markets[:5]:
                            print(f"    slug={m.get('slug','?')[:60]}  q={m.get('question','?')[:60]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ── Test 2: Gamma slug lookup ──────────────────────────────────────────
        print("\n=== Test 2: Gamma slug lookup (current windows) ===")
        now_ts = int(time.time())
        for interval in [300, 900]:
            w_ts = now_ts - (now_ts % interval)
            for slug_prefix in SLUG_ALIASES["BTC"]:
                for ts in [w_ts, w_ts + interval]:
                    slug = f"{slug_prefix}-updown-{interval//60}m-{ts}"
                    try:
                        async with sess.get(
                            f"{GAMMA}/markets", params={"slug": slug}
                        ) as r:
                            if r.status == 200:
                                raw = await r.json()
                                ms = _extract_list(raw)
                                if ms:
                                    print(f"  FOUND slug={slug}  ({len(ms)} result(s))")
                                    for m in ms[:2]:
                                        print(f"    tokens: {m.get('clobTokenIds', m.get('tokens', '?'))[:80]}")
                                else:
                                    print(f"  miss  slug={slug}  (empty)")
                            else:
                                print(f"  {r.status}   slug={slug}")
                    except Exception as e:
                        print(f"  ERR   slug={slug}: {e}")

        # ── Test 3: CLOB /markets ──────────────────────────────────────────────
        print("\n=== Test 3: CLOB /markets ===")
        try:
            async with sess.get(
                f"{CLOB}/markets",
                params={"active": "true", "accepting_orders": "true", "limit": "100"},
            ) as r:
                print(f"  Status: {r.status}")
                if r.status == 200:
                    raw = await r.json()
                    print(f"  Response type: {type(raw).__name__}")
                    if isinstance(raw, dict):
                        print(f"  Top-level keys: {list(raw.keys())[:10]}")
                    markets = _extract_list(raw)
                    print(f"  Extracted markets: {len(markets)}")
                    updown_ms = [m for m in markets if is_updown(m)]
                    print(f"  Updown markets: {len(updown_ms)}")
                    for m in updown_ms[:5]:
                        slug = m.get("slug") or m.get("market_slug") or "?"
                        toks = m.get("tokens", [])
                        print(f"    slug={slug[:60]}")
                        for t in toks[:2]:
                            print(f"      token_id={t.get('token_id','?')[:20]}  outcome={t.get('outcome','?')}")
                else:
                    body = await r.text()
                    print(f"  Body (first 200): {body[:200]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ── Test 4: Gamma with endDate filter ─────────────────────────────────
        print("\n=== Test 4: Gamma sorted by endDate ascending (soonest first) ===")
        try:
            async with sess.get(
                f"{GAMMA}/markets",
                params={"active": "true", "closed": "false",
                        "limit": "50", "order": "endDate", "ascending": "true"},
            ) as r:
                print(f"  Status: {r.status}")
                if r.status == 200:
                    raw = await r.json()
                    markets = _extract_list(raw)
                    print(f"  Extracted: {len(markets)}")
                    updown_ms = [m for m in markets if is_updown(m)]
                    print(f"  Updown: {len(updown_ms)}")
                    for m in updown_ms[:5]:
                        slug = m.get("slug") or m.get("market_slug") or "?"
                        print(f"    slug={slug[:60]}  endDate={m.get('endDate','?')}")
        except Exception as e:
            print(f"  ERROR: {e}")


asyncio.run(run())
