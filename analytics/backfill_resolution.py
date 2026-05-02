"""
Backfill window_outcome_price in trades.jsonl using Gamma API authoritative outcomes.

The old capture method sampled the CLOB order book at window_end+5s, before the
Chainlink oracle (30-90s delay) had settled. This causes wrong outcomes especially
for NO-resolution trades (YES token still shows a non-zero stale price).

This script queries closed markets from the Gamma API and patches trades.jsonl
with the authoritative winningOutcomeIndex-derived outcome (1.0=YES won, 0.0=NO won).

Usage:  python3 analytics/backfill_resolution.py [--dry-run]
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

GAMMA = "https://gamma-api.polymarket.com"
TRADES_PATH = os.path.join("logs", "trades.jsonl")
DRY_RUN = "--dry-run" in sys.argv


def gamma_get(params: dict) -> list:
    """Query Gamma API, return list of market dicts."""
    url = f"{GAMMA}/markets?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", [data] if data.get("conditionId") else [])
    except Exception as e:
        print(f"  WARN gamma request failed ({params}): {e}")
    return []


def resolve_token(token_id: str) -> float | None:
    """
    Return 1.0 if token_id is the winning token, 0.0 if losing, None if not found.
    Queries Gamma for closed markets containing this token.
    """
    # Try direct condition lookup isn't possible without cid — scan recent closed markets
    # by fetching batches of inactive markets and matching clobTokenIds.
    # Limit to last 2000 closed markets (covers ~7 days of 5M windows across 3 assets).
    for offset in range(0, 2001, 500):
        mkts = gamma_get({"active": "false", "closed": "true", "limit": 500, "offset": offset})
        if not mkts:
            break
        for m in mkts:
            raw_ids = m.get("clobTokenIds", [])
            if isinstance(raw_ids, str):
                try:
                    raw_ids = json.loads(raw_ids)
                except Exception:
                    raw_ids = []
            if token_id not in raw_ids:
                continue
            widx = m.get("winningOutcomeIndex")
            if widx is None:
                continue
            if widx < len(raw_ids):
                return 1.0 if raw_ids[widx] == token_id else 0.0
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

    # Only process trades where window_outcome_price might be wrong:
    # - value in (0.01, 0.79) — ambiguous zone, stale pre-settlement price
    # - None/missing
    needs_check = [
        (i, t) for i, t in live_trades
        if t.get("window_outcome_price") is None
        or (0.01 < (t.get("window_outcome_price") or 0.0) < 0.80)
    ]
    print(f"{len(needs_check)} trades with ambiguous/missing window_outcome_price")

    if not needs_check:
        print("Nothing to fix.")
        return

    patched = 0
    changed = 0
    for idx, (line_i, trade) in enumerate(needs_check):
        tid = trade["trade_id"]
        token_id = trade["token_id"]
        old_wop = trade.get("window_outcome_price")
        print(f"[{idx+1}/{len(needs_check)}] {tid} token={token_id[:16]}... old_wop={old_wop}", end=" ", flush=True)

        outcome = resolve_token(token_id)
        if outcome is None:
            print("→ not found in Gamma (market too old or archived differently)")
            time.sleep(0.3)
            continue

        new_correct = outcome >= 0.80
        old_correct = trade.get("entered_correctly")
        print(f"→ outcome={outcome:.1f} entered_correctly={new_correct} (was {old_wop}/{old_correct})")

        if outcome != old_wop or new_correct != old_correct:
            changed += 1

        if not DRY_RUN:
            trade["window_outcome_price"] = outcome
            trade["entered_correctly"] = new_correct
            lines[line_i] = json.dumps(trade) + "\n"

        patched += 1
        time.sleep(0.2)  # rate limit

    print(f"\nPatched {patched}/{len(needs_check)} trades, {changed} values changed")
    if DRY_RUN:
        print("DRY RUN — no files written")
        return

    with open(TRADES_PATH, "w") as f:
        f.writelines(lines)
    print(f"Wrote {TRADES_PATH}")


if __name__ == "__main__":
    main()
