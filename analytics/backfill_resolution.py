"""
Backfill window_outcome_price in trades.jsonl using Gamma API authoritative outcomes.

The old capture method sampled the CLOB order book at window_end+5s, before the
Chainlink oracle (30-90s delay) had settled. This causes wrong outcomes especially
for NO-resolution trades (YES token still shows a non-zero stale price).

This script queries closed markets from the Gamma API and patches trades.jsonl
with the authoritative outcomePrices-derived outcome (1.0=YES won, 0.0=NO won).

Usage:  python3 analytics/backfill_resolution.py [--dry-run]
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

GAMMA = "https://gamma-api.polymarket.com"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_REPO_ROOT, "logs", "trades.jsonl")
DRY_RUN = "--dry-run" in sys.argv

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_SLUG_PREFIXES = {"BTC": "btc", "ETH": "eth", "SOL": "sol"}


def gamma_get(params: dict) -> list:
    """Query Gamma API (with User-Agent to avoid 403), return list of market dicts."""
    url = f"{GAMMA}/markets?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", [data] if data.get("conditionId") else [])
    except Exception as e:
        print(f"  WARN gamma request failed ({params}): {e}")
    return []


def parse_json_field(val, default):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default
    return val if val is not None else default


def outcome_from_market(m: dict, token_id: str) -> float | None:
    """
    Extract win/loss from a closed Gamma market dict.
    Uses outcomePrices: "1" = won ($1.00), "0" = lost.
    Returns 1.0, 0.0, or None if token_id not found in this market.
    """
    raw_ids = parse_json_field(m.get("clobTokenIds", []), [])
    prices = parse_json_field(m.get("outcomePrices", []), [])
    for i, tid in enumerate(raw_ids):
        if tid == token_id:
            p = float(prices[i]) if i < len(prices) else 0.0
            return 1.0 if p >= 0.5 else 0.0
    return None


def resolve_by_slug(token_id: str, asset: str, ts_open: float) -> float | None:
    """Try to resolve via slug lookup (fast, exact market)."""
    prefix = _SLUG_PREFIXES.get(asset.upper(), asset.lower())
    # Try window start = floor(ts_open, 300) and floor+300 (we might be in next window)
    for delta in (0, -300, 300):
        wstart = int(ts_open) - (int(ts_open) % 300) + delta
        slug = f"{prefix}-updown-5m-{wstart}"
        mkts = gamma_get({"slug": slug})
        for m in mkts:
            result = outcome_from_market(m, token_id)
            if result is not None:
                return result
    return None


def resolve_by_scan(token_id: str) -> float | None:
    """
    Scan recent closed markets for this token_id.
    Covers ~7 days of 5M windows across 3 assets (≈ 3×2016 = ~6000 markets).
    We scan up to 2500 to be safe, stopping early if we hit a match.
    """
    for offset in range(0, 2501, 500):
        mkts = gamma_get({"closed": "true", "limit": 500, "offset": offset})
        if not mkts:
            break
        for m in mkts:
            result = outcome_from_market(m, token_id)
            if result is not None:
                return result
    return None


def main():
    if not os.path.exists(TRADES_PATH):
        print(f"No trades file at {TRADES_PATH}")
        return

    with open(TRADES_PATH) as f:
        lines = f.readlines()

    trades = []
    for i, line in enumerate(lines):
        try:
            t = json.loads(line.strip())
            trades.append((i, t))
        except Exception:
            trades.append((i, None))

    live_trades = [(i, t) for i, t in trades if t and t.get("is_live") and t.get("token_id")]
    print(f"Loaded {len(live_trades)} live trades from {len(trades)} total records")

    # Skip ORPHAN sells (logging bugs, no real position entry)
    # Only fix trades with ambiguous wop: in (0.01, 0.79) — stale pre-settlement zone
    # or None where we couldn't capture at all.
    needs_check = [
        (i, t) for i, t in live_trades
        if "ORPHAN" not in (t.get("trade_id") or "")
        and (
            t.get("window_outcome_price") is None
            or (0.01 < (t.get("window_outcome_price") or 0.0) < 0.80)
        )
    ]
    print(f"{len(needs_check)} non-ORPHAN trades with ambiguous/missing window_outcome_price")

    if not needs_check:
        print("Nothing to fix.")
        return

    patched = 0
    changed = 0
    for idx, (line_i, trade) in enumerate(needs_check):
        tid = trade["trade_id"]
        token_id = trade["token_id"]
        asset = trade.get("asset", "")
        ts_open = trade.get("ts_open", 0)
        old_wop = trade.get("window_outcome_price")
        print(f"[{idx+1}/{len(needs_check)}] {tid} old_wop={old_wop}", end=" ", flush=True)

        # Fast path: slug lookup (deterministic market name)
        outcome = resolve_by_slug(token_id, asset, ts_open)

        # Slow path: scan recent closed markets
        if outcome is None:
            print("(slug miss, scanning...)", end=" ", flush=True)
            outcome = resolve_by_scan(token_id)

        if outcome is None:
            print("→ not found (market too old or slug format changed)")
            time.sleep(0.3)
            continue

        new_correct = outcome >= 0.80
        old_correct = trade.get("entered_correctly")
        print(f"→ outcome={outcome:.1f} correct={new_correct} (was {old_wop}/{old_correct})")

        if outcome != old_wop or new_correct != old_correct:
            changed += 1

        if not DRY_RUN:
            trade["window_outcome_price"] = outcome
            trade["entered_correctly"] = new_correct
            lines[line_i] = json.dumps(trade) + "\n"

        patched += 1
        time.sleep(0.2)

    print(f"\nPatched {patched}/{len(needs_check)} trades, {changed} values changed")
    if DRY_RUN:
        print("DRY RUN — no files written")
        return

    with open(TRADES_PATH, "w") as f:
        f.writelines(lines)
    print(f"Wrote {TRADES_PATH}")


if __name__ == "__main__":
    main()
