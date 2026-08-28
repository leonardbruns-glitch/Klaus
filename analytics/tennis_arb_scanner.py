"""
Tennis arbitrage scanner — REST-poll first version.

Watches active ATP/WTA markets in the $25k-$130k volume band (tradecraft's
sweet spot, verified empirically) for sum_yes_ask + sum_no_ask < threshold.

Every SCAN_PERIOD_S seconds:
  1. Refresh active-market list from gamma (cached for METADATA_REFRESH_S seconds).
  2. Concurrently fetch BOTH outcomes' books for every market via CLOB.
  3. For each pair, compute sum_of_best_asks + capacity at top-of-book.
  4. If sum + slippage < 1.00 - FEE_DRAG_PCT, log an OPPORTUNITY event.
  5. If sum < 1.00 but doesn't clear our fee threshold, log a NEAR_MISS event.

NO ORDERS PLACED. Pure observation. Output:
  logs/shadow/hot/<date>/tennis_arb_scanner.jsonl

Run on VPS:
    setsid python3 -m analytics.tennis_arb_scanner &

Caveat carried over from prior falsification work:
  - REST timestamps and book snapshots are stale by 0-4s.
  - True ms-level arb detection requires WebSocket; this scanner is the
    REST-feasibility baseline to measure what we catch with our current infra.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

# Selection criteria from prior empirical analysis on tradecraft (commit e9175de+):
# their median market volume is $41k; range $7k-$235k. But TOTAL volume ≠ ACTIVE
# liquidity — most tennis markets in this band have wide-open books (sum_ask 1.5-1.9).
# We filter to markets with recent activity (volume24hr) AND non-pathological books.
VOL_TOTAL_MIN = 2_000      # user instruction: include thin-market niche
VOL_TOTAL_MAX = 500_000
VOL_24H_MIN = 500          # any activity today, however small
MAX_SUM_ASK_FOR_SCAN = 1.15  # skip wide-empty books; they aren't pair-arb candidates
SCAN_PERIOD_S = 4.0                    # ~match our wallet_shadow FAST tier
METADATA_REFRESH_S = 60.0              # refresh market list every minute
N_WORKERS = 24                         # concurrent book fetches

# Fire criteria:
#  sum_ask < 1.00 - FEE_DRAG_PCT - SLIPPAGE_BUFFER = arb survives both fees and slippage
FEE_BPS = 200            # 2% taker per leg = 4% combined
FEE_DRAG_PCT = 0.04
SLIPPAGE_BUFFER = 0.01   # +1¢ each side typical slippage
ARB_THRESHOLD = 1.00 - FEE_DRAG_PCT - SLIPPAGE_BUFFER  # = 0.95
# Capture parity-zone too so we see when MM spread widens / arb appears.
# Empirical: most tennis markets sit at sum=1.010 (1¢ MM spread above parity).
NEAR_MISS_THRESHOLD = 1.02

LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
LOG_NAME = "tennis_arb_scanner.jsonl"

logger = logging.getLogger("tennis_arb_scanner")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def log_path() -> Path:
    d = utc_today()
    p = LOG_DIR / d / LOG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(ev: dict) -> None:
    line = json.dumps(ev, separators=(",", ":"), default=str)
    with log_path().open("a") as f:
        f.write(line + "\n")


def fetch_book(session: requests.Session, token_id: str) -> Optional[dict]:
    try:
        r = session.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=5)
        if r.status_code != 200:
            return None
        d = r.json()
        asks = [(float(a["price"]), float(a["size"])) for a in (d.get("asks") or [])[:5]]
        bids = [(float(b["price"]), float(b["size"])) for b in (d.get("bids") or [])[:5]]
        return {"asks": asks, "bids": bids}
    except Exception:
        return None


def fetch_active_tennis_markets(session: requests.Session) -> list[dict]:
    """Return active ATP/WTA markets within the volume band of interest."""
    out = []
    seen_cids = set()
    for offset in (0, 500):
        try:
            r = session.get(f"{GAMMA}/markets",
                            params={"closed": "false", "order": "volume24hr",
                                    "ascending": "false", "limit": 500, "offset": offset},
                            timeout=15)
            if r.status_code != 200:
                continue
            d = r.json()
        except Exception:
            continue
        if not isinstance(d, list) or not d:
            break
        for m in d:
            slug = (m.get("slug") or "").lower()
            if not ("atp-" in slug or "wta-" in slug):
                continue
            cid = m.get("conditionId")
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            vol = float(m.get("volume", 0) or 0)
            vol24 = float(m.get("volume24hr", 0) or 0)
            if not (VOL_TOTAL_MIN <= vol <= VOL_TOTAL_MAX):
                continue
            if vol24 < VOL_24H_MIN:
                continue  # not actively traded today; books likely empty
            ctokens = m.get("clobTokenIds")
            if isinstance(ctokens, str):
                try:
                    ctokens = json.loads(ctokens)
                except json.JSONDecodeError:
                    continue
            if not ctokens or len(ctokens) != 2:
                continue
            outcomes = m.get("outcomes")
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except json.JSONDecodeError:
                    outcomes = None
            out.append({
                "conditionId": cid,
                "slug": m.get("slug"),
                "question": m.get("question"),
                "volume": vol,
                "volume24hr": float(m.get("volume24hr", 0) or 0),
                "endDate": m.get("endDate"),
                "clobTokenIds": ctokens,
                "outcomes": outcomes,
            })
    return out


def scan_one(session: requests.Session, market: dict) -> Optional[dict]:
    """Fetch both books, compute sum_ask + capacity. Return result dict for every market.
    Caller decides whether to log based on rec type."""
    cids = market["clobTokenIds"]
    if len(cids) != 2:
        return None
    book_a = fetch_book(session, cids[0])
    book_b = fetch_book(session, cids[1])
    if not book_a or not book_b:
        return None
    asks_a = book_a["asks"]
    asks_b = book_b["asks"]
    bids_a = book_a["bids"]
    bids_b = book_b["bids"]
    if not asks_a or not asks_b:
        return None
    best_ask_a = min(p for p, _ in asks_a)
    best_ask_b = min(p for p, _ in asks_b)
    size_at_best_a = sum(s for p, s in asks_a if abs(p - best_ask_a) < 1e-6)
    size_at_best_b = sum(s for p, s in asks_b if abs(p - best_ask_b) < 1e-6)
    sum_ask = best_ask_a + best_ask_b
    best_bid_a = max((p for p, _ in bids_a), default=0)
    best_bid_b = max((p for p, _ in bids_b), default=0)
    edge = 1.0 - sum_ask
    cap_usd_a = best_ask_a * size_at_best_a
    cap_usd_b = best_ask_b * size_at_best_b
    capacity = min(cap_usd_a, cap_usd_b)
    # Classify
    if sum_ask < ARB_THRESHOLD:
        rec = "ARB_OPPORTUNITY"
    elif sum_ask < NEAR_MISS_THRESHOLD:
        rec = "NEAR_MISS"
    else:
        rec = "STATE"   # log periodically for distribution analysis
    return {
        "rec": rec,
        "ts": int(time.time()),
        "iso": datetime.utcnow().isoformat(),
        "condition_id": market["conditionId"],
        "slug": market["slug"],
        "outcomes": market.get("outcomes"),
        "volume_total": market["volume"],
        "best_ask_a": round(best_ask_a, 4),
        "best_ask_b": round(best_ask_b, 4),
        "sum_ask": round(sum_ask, 4),
        "edge_pct": round(edge * 100, 3),
        "best_bid_a": round(best_bid_a, 4),
        "best_bid_b": round(best_bid_b, 4),
        "size_at_ask_a": round(size_at_best_a, 2),
        "size_at_ask_b": round(size_at_best_b, 2),
        "cap_usd_min": round(capacity, 2),
        "fireable_at_5usd_per_leg": capacity >= 5.0 and sum_ask < ARB_THRESHOLD,
    }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Suppress noisy connection-pool warnings; we size the pool below.
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    # Size the HTTP connection pool for N_WORKERS concurrent requests.
    adapter = requests.adapters.HTTPAdapter(pool_connections=N_WORKERS * 2,
                                            pool_maxsize=N_WORKERS * 2,
                                            max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    logger.info("tennis_arb_scanner start — vol band $%dk-$%dk, scan period %.1fs, arb threshold sum<%.2f",
                VOL_TOTAL_MIN / 1000, VOL_TOTAL_MAX / 1000, SCAN_PERIOD_S, ARB_THRESHOLD)
    logger.info("logs → %s", LOG_DIR / "<date>" / LOG_NAME)
    logger.warning("REST poll cadence; sub-second decay not measurable from this infra")

    markets: list[dict] = []
    last_meta = 0.0
    last_state_snapshot = 0.0
    STATE_SNAPSHOT_S = 60.0  # log full per-market STATE once a minute for distribution analysis
    stats = {"scans": 0, "opportunities": 0, "near_misses": 0, "fireable": 0}

    while True:
        now = time.time()
        try:
            if now - last_meta > METADATA_REFRESH_S:
                markets = fetch_active_tennis_markets(session)
                last_meta = now
                logger.info("refreshed markets — tracking %d in vol band", len(markets))
            if not markets:
                time.sleep(SCAN_PERIOD_S)
                continue
            t0 = time.time()
            log_states_this_cycle = (now - last_state_snapshot) > STATE_SNAPSHOT_S
            if log_states_this_cycle:
                last_state_snapshot = now
            cycle_sums = []
            with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
                futs = {ex.submit(scan_one, session, m): m for m in markets}
                for fut in as_completed(futs):
                    ev = fut.result()
                    if not ev:
                        continue
                    cycle_sums.append(ev["sum_ask"])
                    if ev["rec"] == "ARB_OPPORTUNITY":
                        record(ev)
                        stats["opportunities"] += 1
                        if ev["fireable_at_5usd_per_leg"]:
                            stats["fireable"] += 1
                            logger.info("FIRE %s sum=%.3f edge=%.2f%% cap=$%.0f %s",
                                        ev["slug"][:40], ev["sum_ask"], ev["edge_pct"],
                                        ev["cap_usd_min"], ev["condition_id"][:14])
                    elif ev["rec"] == "NEAR_MISS":
                        record(ev)
                        stats["near_misses"] += 1
                    elif ev["rec"] == "STATE" and log_states_this_cycle:
                        record(ev)
            stats["scans"] += 1
            dt = time.time() - t0
            if stats["scans"] % 5 == 0 and cycle_sums:  # log every ~20s with sum distribution
                s = sorted(cycle_sums)
                med = s[len(s) // 2]
                lo = s[0]
                p25 = s[len(s) // 4]
                logger.info("scans=%d opps=%d fireable=%d near=%d  sum_ask{min=%.3f p25=%.3f med=%.3f}  cycle=%.1fs",
                            stats["scans"], stats["opportunities"], stats["fireable"],
                            stats["near_misses"], lo, p25, med, dt)
        except Exception as exc:
            logger.exception("scan err: %s", exc)
        elapsed = time.time() - now
        time.sleep(max(0.5, SCAN_PERIOD_S - elapsed))


if __name__ == "__main__":
    main()
