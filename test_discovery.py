"""
Quick market discovery test — run before the 13:00 UTC window to verify
Gamma API connectivity and that updown tokens are discoverable.

Usage:
    python3 test_discovery.py

No API keys needed; dry-run safe.
"""
import asyncio
import time
import sys

async def main():
    try:
        import aiohttp
    except ImportError:
        print("FAIL: aiohttp not installed — install with: pip install aiohttp")
        return 1

    from data.feeds import PolymarketFeed
    from config import CONFIG

    print(f"Testing market discovery for: {CONFIG.markets.tracked_assets}")
    print(f"Gamma API: {CONFIG.markets.gamma_api_url}")
    print()

    feed = PolymarketFeed()
    t0 = time.time()
    await feed.start()
    elapsed = time.time() - t0

    if feed._stub_mode:
        print(f"WARN: Fell back to stub mode — no live tokens discovered ({elapsed:.1f}s)")
        print("  Check network connectivity and Gamma API availability")
        return 1

    n = len(feed.tokens)
    updown = sum(1 for t in feed.tokens.values() if t.market_type == "updown")
    target = sum(1 for t in feed.tokens.values() if t.market_type == "target")

    print(f"OK: Discovered {n} tokens in {elapsed:.1f}s")
    print(f"   Updown (5M/15M): {updown}")
    print(f"   Target (price):  {target}")
    print()

    # Print discovered tokens grouped by asset
    from collections import defaultdict
    by_asset = defaultdict(list)
    for tok in feed.tokens.values():
        by_asset[tok.asset].append(tok)

    for asset, tokens in sorted(by_asset.items()):
        print(f"  {asset}:")
        for t in tokens:
            ob = feed.order_books.get(t.token_id)
            mid_str = f"mid={ob.mid:.4f}" if ob else "no OB"
            remaining = t.window_end_ts - time.time() if t.window_end_ts > 0 else 0
            exp_str = f"expires in {remaining:.0f}s" if remaining > 0 else "no expiry"
            print(f"    {t.side:3s} [{t.market_type:6s}] {mid_str} | {exp_str} | "
                  f"neg_risk={t.neg_risk} tick={t.tick_size} | {t.token_id[:12]}...")

    await feed.stop()
    return 0 if n > 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
