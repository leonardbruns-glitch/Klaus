"""
Market Creation Monitor — investigates pre-open exploit hypothesis.

Polls Gamma and CLOB APIs for new markets and captures every book state
from the moment of creation through the first 90 seconds.

Goal: determine if there's a transient window where CLOB asks are < 0.20
(which would indicate a cheap-ask sniping opportunity or initialization bug).

Usage:
    python3 analytics/market_creation_monitor.py [--max-markets 50] [--duration 3600]

Output:
    logs/market_creation_events.jsonl
    - event=NEW_MARKET: when a new market is first detected
    - event=BOOK_SAMPLE: orderbook state at each second
    - event=CHEAP_ASK: when any ask < threshold is found (alert!)
    - event=TRANSITION: when book transitions (200→404 or similar)
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
import requests

ROOT = Path(__file__).parent.parent
LOG_FILE = ROOT / "logs" / "market_creation_events.jsonl"

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

CHEAP_ASK_THRESHOLD = 0.20  # alert if any ask < this
MONITOR_DURATION_S = 90      # watch each market for this many seconds
POLL_INTERVAL_S = 0.5        # poll every 500ms
GAMMA_POLL_S = 5             # check for new markets every 5s

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _write(record: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def gamma_latest(n: int = 30) -> list:
    try:
        r = requests.get(
            f"{GAMMA}/markets",
            params={"limit": n, "order": "createdAt", "ascending": False, "active": True},
            timeout=5,
        )
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def clob_book(token_id: str) -> tuple[list, list, int]:
    """Returns (asks, bids, http_status). asks/bids sorted by price descending (best first)."""
    try:
        r = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=3)
        if r.status_code == 200:
            b = r.json()
            asks = [(float(a["price"]), float(a["size"])) for a in b.get("asks", [])]
            bids = [(float(b2["price"]), float(b2["size"])) for b2 in b.get("bids", [])]
            return asks, bids, 200
        return [], [], r.status_code
    except Exception:
        return [], [], -1


def clob_market(condition_id: str) -> tuple[dict, int]:
    """Returns (market_data, http_status) from CLOB /markets/{condition_id}."""
    try:
        r = requests.get(f"{CLOB}/markets/{condition_id}", timeout=3)
        if r.status_code == 200:
            return r.json(), 200
        return {}, r.status_code
    except Exception:
        return {}, -1


def run(max_markets: int, duration_s: int) -> None:
    logger.info("Market creation monitor starting. Log: %s", LOG_FILE)
    logger.info("Watching for cheap asks < %.2f on new markets", CHEAP_ASK_THRESHOLD)

    seen_slugs: set = set()
    # Seed with existing slugs so we only track NEW markets
    for m in gamma_latest(50):
        seen_slugs.add(m.get("slug", ""))
    logger.info("Seeded %d existing markets. Watching for new ones...", len(seen_slugs))

    # active_monitors: slug -> {start_ts, token_ids, condition_id, last_status: {tid: int}}
    active_monitors: dict = {}
    markets_seen = 0
    start_run = time.time()

    while time.time() - start_run < duration_s and markets_seen < max_markets:
        now = time.time()
        now_dt = datetime.datetime.utcfromtimestamp(now).isoformat() + "Z"

        # Check for new markets
        latest = gamma_latest(20)
        for m in latest:
            slug = m.get("slug", "")
            if not slug or slug in seen_slugs:
                continue

            seen_slugs.add(slug)
            markets_seen += 1
            _raw_tids = m.get("clobTokenIds") or []
            # Gamma API returns clobTokenIds as a JSON-encoded string, not a list
            if isinstance(_raw_tids, str):
                try:
                    import json as _json
                    _raw_tids = _json.loads(_raw_tids)
                except Exception:
                    _raw_tids = []
            token_ids = [str(t).strip('"') for t in _raw_tids]
            condition_id = m.get("conditionId") or ""

            record = {
                "event": "NEW_MARKET",
                "ts": now,
                "dt": now_dt,
                "slug": slug,
                "createdAt": m.get("createdAt"),
                "acceptingOrders": m.get("acceptingOrders"),
                "acceptingOrdersTimestamp": m.get("acceptingOrdersTimestamp"),
                "ready": m.get("ready"),
                "funded": m.get("funded"),
                "condition_id": condition_id,
                "token_ids": token_ids,
                "bestBid": m.get("bestBid"),
                "bestAsk": m.get("bestAsk"),
            }
            _write(record)
            logger.info("*** NEW MARKET: %s | tokens=%d cid=%s", slug, len(token_ids), condition_id[:16])

            active_monitors[slug] = {
                "start_ts": now,
                "slug": slug,
                "token_ids": token_ids,
                "condition_id": condition_id,
                "last_status": {},
            }

        # Sample all active monitors
        expired = []
        for slug, mon in active_monitors.items():
            elapsed = now - mon["start_ts"]
            if elapsed > MONITOR_DURATION_S:
                expired.append(slug)
                logger.info("Monitor expired for %s after %.0fs", slug, elapsed)
                continue

            for i, tid in enumerate(mon["token_ids"][:2]):
                asks, bids, status = clob_book(tid)
                prev_status = mon["last_status"].get(tid, -99)

                if status != prev_status:
                    transition = {
                        "event": "TRANSITION",
                        "ts": now,
                        "dt": now_dt,
                        "slug": slug,
                        "elapsed_s": round(elapsed, 1),
                        "token_idx": i,
                        "token_id": tid[:20],
                        "prev_status": prev_status,
                        "new_status": status,
                    }
                    _write(transition)
                    logger.info(
                        "TRANSITION %s token%d: %s → %d at t+%.0fs",
                        slug[:40], i, prev_status, status, elapsed,
                    )
                    mon["last_status"][tid] = status

                if asks:
                    cheapest_ask = min(a[0] for a in asks)
                    best_bid = bids[0][0] if bids else 0.0

                    sample = {
                        "event": "BOOK_SAMPLE",
                        "ts": now,
                        "dt": now_dt,
                        "slug": slug,
                        "elapsed_s": round(elapsed, 1),
                        "token_idx": i,
                        "token_id": tid[:20],
                        "cheapest_ask": cheapest_ask,
                        "dearest_ask": max(a[0] for a in asks),
                        "best_bid": best_bid,
                        "n_ask_levels": len(asks),
                        "all_asks": asks[:5],
                    }
                    _write(sample)

                    if cheapest_ask < CHEAP_ASK_THRESHOLD:
                        alert = {
                            "event": "CHEAP_ASK",
                            "ts": now,
                            "dt": now_dt,
                            "slug": slug,
                            "elapsed_s": round(elapsed, 1),
                            "token_idx": i,
                            "cheapest_ask": cheapest_ask,
                            "all_asks": asks,
                        }
                        _write(alert)
                        logger.warning(
                            "!!! CHEAP ASK: %s token%d ask=%.4f at t+%.0fs !!!",
                            slug[:40], i, cheapest_ask, elapsed,
                        )

        for slug in expired:
            del active_monitors[slug]

        if int(now) % 60 == 0:
            logger.info(
                "Status: %d markets tracked, %d active monitors, run=%.0fmin",
                markets_seen, len(active_monitors), (now - start_run) / 60,
            )
            sys.stdout.flush()

        time.sleep(POLL_INTERVAL_S)

    logger.info("Monitor finished. Tracked %d markets. Log: %s", markets_seen, LOG_FILE)


def analyze_log() -> None:
    """Analyze existing log for patterns."""
    if not LOG_FILE.exists():
        print("No log file found.")
        return

    records = []
    with open(LOG_FILE) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    print(f"Total records: {len(records)}")

    # Count by event type
    by_event = {}
    for r in records:
        e = r.get("event", "?")
        by_event[e] = by_event.get(e, 0) + 1
    for e, count in sorted(by_event.items()):
        print(f"  {e}: {count}")

    # Find any cheap asks
    cheap = [r for r in records if r.get("event") == "CHEAP_ASK"]
    print(f"\nCheap ask alerts: {len(cheap)}")
    for r in cheap:
        print(f"  {r}")

    # Book evolution for each market
    new_markets = [r for r in records if r.get("event") == "NEW_MARKET"]
    print(f"\nNew markets captured: {len(new_markets)}")
    for m in new_markets:
        slug = m.get("slug", "")
        samples = [r for r in records
                   if r.get("event") == "BOOK_SAMPLE" and r.get("slug") == slug]
        transitions = [r for r in records
                       if r.get("event") == "TRANSITION" and r.get("slug") == slug]
        if samples:
            asks_by_time = [(s["elapsed_s"], s["cheapest_ask"]) for s in samples]
            min_ask = min(a[1] for a in asks_by_time)
            print(f"  {slug[:50]}")
            print(f"    samples={len(samples)} transitions={len(transitions)}")
            print(f"    min_ask_seen={min_ask:.3f}")
            if asks_by_time:
                print(f"    first_sample: t+{asks_by_time[0][0]}s ask={asks_by_time[0][1]}")
                print(f"    last_sample:  t+{asks_by_time[-1][0]}s ask={asks_by_time[-1][1]}")
        else:
            print(f"  {slug[:50]}: no book samples (CLOB 404 throughout)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market creation monitor")
    parser.add_argument("--max-markets", type=int, default=20,
                        help="Stop after monitoring this many new markets")
    parser.add_argument("--duration", type=int, default=3600,
                        help="Run for this many seconds (default: 1 hour)")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze existing log and exit")
    args = parser.parse_args()

    if args.analyze:
        analyze_log()
    else:
        run(max_markets=args.max_markets, duration_s=args.duration)
