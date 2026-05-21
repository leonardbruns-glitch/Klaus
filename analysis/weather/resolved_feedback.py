"""
Resolved-trade feedback patcher.

Runs at 12:00 UTC daily. Finds WEATHER_* trades in logs/trades.jsonl where
entered_correctly=null (market resolved while bot was offline or before
resolution logic ran), fetches the Polymarket market outcome via public API,
determines win/loss based on bond_outcome_direction, and patches the file.

Also logs actual resolution to logs/weather/forecast_actuals.jsonl so
refresh_skill_matrix can accumulate live calibration data.

Safety:
  - Reads trades.jsonl sequentially; writes a new file then replaces atomically.
  - Never modifies trades where entered_correctly is already set.
  - Skips trades with exit_reason STARTUP_EXTERNALLY_SOLD (outcome unknowable
    without market data; let the bot resolve on next restart).

Usage:
    python3 -m analysis.weather.resolved_feedback [--days 3]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT         = Path(__file__).parent.parent.parent
TRADES_FILE  = ROOT / "logs" / "trades.jsonl"
ACTUALS_FILE = ROOT / "logs" / "weather" / "forecast_actuals.jsonl"

WEATHER_CLASSES = {
    "WEATHER_ARB", "WEATHER_INTRADAY", "WEATHER_TAIL",
    "WEATHER_NWPLAG", "WEATHER_CITYCTR", "WEATHER_NOSIDE", "WEATHER_BRACKET",
}

GAMMA_BASE = "https://gamma-api.polymarket.com"


def _fetch_market_outcome(token_id: str) -> str | None:
    """
    Returns "YES_WIN" | "NO_WIN" | "OPEN" | None (error).

    Queries Polymarket gamma API for market info. After resolution,
    outcomePrices is [1.0, 0.0] (YES win) or [0.0, 1.0] (NO win).
    """
    url = f"{GAMMA_BASE}/markets?clob_token_ids={token_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        logger.warning("gamma API error for %s: %s", token_id[:20], e)
        return None

    markets = data if isinstance(data, list) else data.get("markets", [])
    if not markets:
        return None
    mkt = markets[0]
    if not mkt.get("resolved", False):
        return "OPEN"
    prices_raw = mkt.get("outcomePrices", "")
    try:
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        yes_price = float(prices[0])
    except Exception:
        return None
    return "YES_WIN" if yes_price >= 0.99 else "NO_WIN"


def _determine_entered_correctly(outcome: str, bond_outcome_direction: str) -> bool | None:
    """
    Map market outcome + direction to entered_correctly.

    bond_outcome_direction:
        "up"   = we bought YES (win if YES_WIN)
        "down" = we bought NO  (win if NO_WIN)
    """
    if outcome == "OPEN":
        return None
    if bond_outcome_direction == "up":
        return outcome == "YES_WIN"
    if bond_outcome_direction == "down":
        return outcome == "NO_WIN"
    return None


def _patch_trades(days: float) -> int:
    if not TRADES_FILE.exists():
        logger.warning("trades.jsonl not found")
        return 0

    cutoff   = time.time() - days * 86400
    patched  = 0
    skipped  = 0
    lines_out: list[str] = []

    with TRADES_FILE.open() as f:
        raw_lines = f.readlines()

    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            lines_out.append(raw)
            continue
        try:
            t = json.loads(stripped)
        except Exception:
            lines_out.append(raw)
            continue

        bec = t.get("bond_entry_class", "")
        ec  = t.get("entered_correctly")
        ts  = t.get("ts_open", 0.0)
        direction = t.get("bond_outcome_direction", "")
        exit_reason = t.get("exit_reason", "")

        # Only patch: WEATHER class, unresolved, within window, not externally-sold unknowns
        if (
            bec not in WEATHER_CLASSES
            or ec is not None
            or ts < cutoff
            or exit_reason == "STARTUP_EXTERNALLY_SOLD"
            or not t.get("token_id")
            or not direction
        ):
            lines_out.append(raw)
            continue

        outcome = _fetch_market_outcome(t["token_id"])
        time.sleep(0.5)   # rate-limit

        if outcome is None or outcome == "OPEN":
            skipped += 1
            lines_out.append(raw)
            continue

        ec_val = _determine_entered_correctly(outcome, direction)
        if ec_val is None:
            lines_out.append(raw)
            continue

        t["entered_correctly"] = ec_val
        lines_out.append(json.dumps(t) + "\n")
        patched += 1

        result_str = "WIN" if ec_val else "LOSS"
        logger.info("[FEEDBACK] %s %s → %s (outcome=%s dir=%s)",
                    bec, t.get("trade_id", "?"), result_str, outcome, direction)

        # Append to forecast_actuals for skill matrix accumulation
        _log_actual_resolution(t, ec_val)

    # Atomic replace
    tmp = TRADES_FILE.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(lines_out))
    tmp.replace(TRADES_FILE)
    logger.info("[FEEDBACK] patched=%d skipped/open=%d", patched, skipped)
    return patched


def _log_actual_resolution(trade: dict, entered_correctly: bool) -> None:
    """Log resolution event to forecast_actuals.jsonl for skill matrix use."""
    ACTUALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    signal = trade.get("signal_source", "")
    city_slug = ""
    parts = signal.split("/")
    if len(parts) >= 2:
        city_slug = parts[1].lower().replace(" ", "-")
    record = {
        "event":       "resolved",
        "trade_id":    trade.get("trade_id", ""),
        "city_slug":   city_slug,
        "strategy":    trade.get("bond_entry_class", ""),
        "direction":   trade.get("bond_outcome_direction", ""),
        "entered_correctly": entered_correctly,
        "entry_price": trade.get("entry_price"),
        "ts_open":     trade.get("ts_open"),
        "ts_utc":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with ACTUALS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def run(days: float = 3.0) -> None:
    patched = _patch_trades(days)
    logger.info("[FEEDBACK] done — %d trades patched over last %.0fd", patched, days)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=3.0,
                    help="look-back window in days (default 3)")
    args = ap.parse_args()
    run(days=args.days)
    sys.exit(0)
