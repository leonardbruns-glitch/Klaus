"""
Backfill entered_correctly + kline_pnl + weather metadata in trades.jsonl
for WEATHER_* entries using Polymarket resolution data.

Patches per trade:
  weather_question       — full Polymarket market question
  weather_city           — city slug (e.g. "london")
  weather_date           — resolution date YYYY-MM-DD
  weather_threshold_lo   — lower bound of temperature bucket (unit-native)
  weather_threshold_hi   — upper bound of temperature bucket (unit-native)
  weather_threshold_lo_c — lower bound in Celsius
  weather_threshold_hi_c — upper bound in Celsius
  weather_unit           — "C" or "F"
  weather_bucket_type    — "exact" | "above" | "below" | "range"
  entered_correctly      — True if resolution matched our BUY_YES/NO direction
  kline_pnl              — canonical hold-to-resolution PnL (analysis truth)

net_pnl stays as actual realized PnL (intraday exit or otherwise).

Usage:  python3 analytics/backfill_weather_resolution.py [--dry-run]
        python3 analytics/backfill_weather_resolution.py --date-range 2026-05-18 2026-05-25
"""

import json
import os
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, date, timedelta

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_REPO_ROOT, "logs", "trades.jsonl")
DRY_RUN = "--dry-run" in sys.argv

GAMMA_BASE = "https://gamma-api.polymarket.com"
WEATHER_CLASSES = {"WEATHER_ARB", "WEATHER_INTRADAY", "WEATHER_TAIL",
                   "WEATHER_NOSIDE", "WEATHER_CITYCTR", "WEATHER_BRACKET"}


# ── Question parser ───────────────────────────────────────────────────────────

_MONTHS = {m: i+1 for i, m in enumerate(
    ["January","February","March","April","May","June",
     "July","August","September","October","November","December"]
)}

def parse_weather_question(q: str) -> dict:
    """
    Parse questions like:
      "Will the highest temperature in London be 22°C on May 21?"
      "Will the highest temperature in Seattle be 74°F or higher on May 21?"
      "Will the highest temperature in Chicago be 59°F or below on May 21?"
      "Will the highest temperature in Seattle be between 70-71°F on May 21?"
      "Will the highest temperature in Dallas be 75°F or below on May 21?"
      "Will the highest temperature in London be 15°C or below on May 20?"
    """
    result: dict = {}

    # City
    m = re.search(r'temperature in ([A-Za-z\s\-]+?) be', q)
    if m:
        result["weather_city"] = m.group(1).strip().lower().replace(" ", "-")

    # Date
    m = re.search(
        r'on (January|February|March|April|May|June|July|August|'
        r'September|October|November|December) (\d+)', q)
    if m:
        mo = _MONTHS.get(m.group(1), 1)
        day = int(m.group(2))
        # Infer year from today (assume current or next calendar year)
        today = date.today()
        year = today.year
        try:
            candidate = date(year, mo, day)
            if candidate > today + timedelta(days=30):
                candidate = date(year - 1, mo, day)
        except ValueError:
            candidate = date(year, mo, 1)
        result["weather_date"] = candidate.isoformat()

    # Temperature bucket
    unit = None
    lo = hi = None
    btype = None

    # Range: "between 70-71°F" or "between 14°C-16°C" or "between 14°C and 16°C"
    m = re.search(r'between (\d+(?:\.\d+)?)°?([CF])?-(\d+(?:\.\d+)?)°([CF])', q)
    if m:
        lo, hi = float(m.group(1)), float(m.group(3))
        unit = m.group(4) or m.group(2) or "C"
        btype = "range"
    if not btype:
        m = re.search(r'between (\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)°([CF])', q)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            unit = m.group(3)
            btype = "range"
    # Above: "74°F or higher"
    if not btype:
        m = re.search(r'(\d+(?:\.\d+)?)°([CF]) or higher', q)
        if m:
            lo, hi = float(m.group(1)), float("inf")
            unit = m.group(2)
            btype = "above"
    # Below: "59°F or below"
    if not btype:
        m = re.search(r'(\d+(?:\.\d+)?)°([CF]) or below', q)
        if m:
            lo, hi = float("-inf"), float(m.group(1))
            unit = m.group(2)
            btype = "below"
    # Exact: "be 22°C on"
    if not btype:
        m = re.search(r'be (\d+(?:\.\d+)?)°([CF]) on', q)
        if m:
            lo = hi = float(m.group(1))
            unit = m.group(2)
            btype = "exact"

    if btype:
        result["weather_unit"] = unit
        result["weather_bucket_type"] = btype
        result["weather_threshold_lo"] = lo if lo != float("-inf") else None
        result["weather_threshold_hi"] = hi if hi != float("inf") else None

        def to_c(v):
            if v is None or v in (float("inf"), float("-inf")):
                return None
            return round((v - 32) * 5 / 9, 1) if unit == "F" else round(v, 1)

        result["weather_threshold_lo_c"] = to_c(lo)
        result["weather_threshold_hi_c"] = to_c(hi)

    return result


# ── Polymarket event fetcher ──────────────────────────────────────────────────

def fetch_weather_events(date_min: str, date_max: str) -> dict:
    """Returns token_id -> market dict for weather events in the date range.

    The Gamma API returns fewer results with wide date windows (seems to cap
    at ~100 events regardless of pagination). Querying day-by-day guarantees
    complete coverage because each narrow window paginates properly.
    """
    token_map: dict = {}
    cond_map: dict = {}

    # Build list of daily windows from date_min to date_max
    d = date.fromisoformat(date_min)
    d_max = date.fromisoformat(date_max)
    day_windows: list = []
    while d <= d_max:
        day_windows.append(d.isoformat())
        d += timedelta(days=1)

    def _ingest_page(page: list) -> None:
        for ev in page:
            for m in ev.get("markets", []):
                cid = m.get("conditionId")
                question = m.get("question", "")
                outcome_prices = m.get("outcomePrices") or '["0","0"]'
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except Exception:
                        outcome_prices = ["0", "0"]
                closed_flag = m.get("closed", False)
                entry = {
                    "question": question,
                    "outcomePrices": outcome_prices,
                    "closed": closed_flag,
                    "conditionId": cid,
                }
                if cid:
                    cond_map[cid] = entry
                tokens_raw = m.get("clobTokenIds") or []
                if isinstance(tokens_raw, str):
                    try:
                        tokens_raw = json.loads(tokens_raw)
                    except Exception:
                        tokens_raw = []
                for tok in tokens_raw:
                    token_map[str(tok)] = entry

    for day in day_windows:
        next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        for closed in ("true", "false"):
            offset = 0
            while True:
                url = (f"{GAMMA_BASE}/events?tag_slug=weather&limit=200"
                       f"&offset={offset}&closed={closed}"
                       f"&end_date_min={day}&end_date_max={next_day}")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "klaus-backfill"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        page = json.loads(resp.read())
                except Exception as e:
                    print(f"  fetch error day={day} closed={closed} offset={offset}: {e}")
                    break
                if not page:
                    break
                _ingest_page(page)
                if len(page) < 200:
                    break
                offset += len(page)
                time.sleep(0.05)
        time.sleep(0.1)

    return token_map, cond_map


def resolve_outcome(entry: dict, direction: str) -> tuple:
    """
    Returns (entered_correctly: bool | None, yes_price: float).
    direction is "BUY_YES" or "BUY_NO".
    """
    prices = entry.get("outcomePrices", ["0", "0"])
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1]) if len(prices) > 1 else 1 - yes_price
    except Exception:
        return None, 0.0

    if not entry.get("closed"):
        return None, yes_price   # not yet resolved

    if direction == "BUY_YES":
        if yes_price >= 0.99:
            return True, yes_price
        if yes_price <= 0.01:
            return False, yes_price
    else:  # BUY_NO
        if no_price >= 0.99:
            return True, no_price
        if no_price <= 0.01:
            return False, no_price

    return None, yes_price  # closed but ambiguous


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Parse optional date-range override
    date_min = "2026-05-18"
    date_max = (date.today() + timedelta(days=2)).isoformat()
    args = sys.argv[1:]
    if "--date-range" in args:
        idx = args.index("--date-range")
        if idx + 2 < len(args):
            date_min = args[idx + 1]
            date_max = args[idx + 2]

    print(f"Loading {TRADES_PATH}...")
    with open(TRADES_PATH) as f:
        raw_lines = f.readlines()

    parsed = []
    for ln in raw_lines:
        try:
            parsed.append(json.loads(ln))
        except Exception:
            parsed.append(None)

    # Find WEATHER_* candidates — includes STARTUP_EXTERNALLY_SOLD with blank class
    # (those are positions recovered at startup where CLOB API returned 401, so
    # exit_price was set to entry_price and net_pnl ≈ -fee even for actual wins).
    candidates = [
        (i, t) for i, t in enumerate(parsed)
        if t and t.get("is_live") and
        t.get("entered_correctly") is None and
        (
            t.get("bond_entry_class", "") in WEATHER_CLASSES or
            (
                t.get("exit_reason", "").startswith("STARTUP_EXTERNALLY_SOLD") and
                t.get("bond_entry_class", "") == ""
            )
        )
    ]
    print(f"WEATHER_* trades needing resolution: {len(candidates)}")
    if not candidates:
        print("Nothing to patch.")
        return

    # Determine date range to query from trade timestamps
    ts_list = [t.get("ts_open", 0) for _, t in candidates]
    q_date_min = (datetime.utcfromtimestamp(min(ts_list)) - timedelta(days=1)).strftime("%Y-%m-%d")
    q_date_max = (datetime.utcfromtimestamp(max(ts_list)) + timedelta(days=3)).strftime("%Y-%m-%d")
    # Use provided range or computed range, whichever is wider
    q_date_min = min(q_date_min, date_min)
    q_date_max = max(q_date_max, date_max)

    print(f"Fetching Polymarket events {q_date_min} → {q_date_max}...")
    token_map, cond_map = fetch_weather_events(q_date_min, q_date_max)
    print(f"  mapped {len(token_map)} tokens, {len(cond_map)} conditions")

    patched = unresolved = no_match = 0
    for i, t in candidates:
        tid = str(t.get("token_id", ""))
        cid = str(t.get("condition_id", ""))
        direction = t.get("direction", "BUY_YES")

        entry = token_map.get(tid) or cond_map.get(cid)
        if not entry:
            no_match += 1
            continue

        entered_correctly, _ = resolve_outcome(entry, direction)
        question = entry.get("question", "")
        weather_meta = parse_weather_question(question)
        weather_meta["weather_question"] = question

        # Always write the question/metadata even if resolution is still pending
        for k, v in weather_meta.items():
            parsed[i][k] = v

        # Tag unclassified orphan recoveries so they appear in weather reports
        if not parsed[i].get("bond_entry_class"):
            parsed[i]["bond_entry_class"] = "WEATHER_STARTUP_ORPHAN"

        if entered_correctly is None:
            unresolved += 1
            continue

        parsed[i]["entered_correctly"] = entered_correctly

        shares = t.get("shares") or 0.0
        ep = t.get("entry_price") or 0.0
        stake = t.get("stake") or (ep * shares)
        fee = t.get("fee_paid") or 0.0

        if entered_correctly:
            parsed[i]["kline_pnl"] = round(shares * (1.0 - ep) - fee, 4)
        else:
            parsed[i]["kline_pnl"] = round(-stake - fee, 4)

        patched += 1
        print(f"  PATCHED [{('WIN' if entered_correctly else 'LOSS')}] "
              f"{t.get('bond_entry_class')} ep={ep:.3f} | {question[:55]}")

    print(f"\npatched={patched}  unresolved={unresolved}  no_match={no_match}  "
          f"total_candidates={len(candidates)}")

    if DRY_RUN:
        print("DRY RUN — not writing")
        return

    bak = TRADES_PATH + ".bak_weather"
    shutil.copy2(TRADES_PATH, bak)
    print(f"backup: {bak}")

    initial_size = os.path.getsize(bak)
    tmp = TRADES_PATH + ".tmp"
    with open(tmp, "w") as f:
        for i, t in enumerate(parsed):
            if t is None:
                f.write(raw_lines[i])
            else:
                f.write(json.dumps(t) + "\n")
        current_size = os.path.getsize(TRADES_PATH)
        if current_size > initial_size:
            with open(TRADES_PATH, "rb") as src:
                src.seek(initial_size)
                tail = src.read()
                f.write(tail.decode("utf-8", errors="replace"))

    os.replace(tmp, TRADES_PATH)
    print(f"rewrote {TRADES_PATH}")


def run_backfill() -> None:
    """Callable entry point for the bot's background backfill loop.

    Equivalent to running main() with no arguments (uses default date range,
    no dry-run).  Suppresses stdout so it doesn't pollute bot logs — outcomes
    are visible in the next feedback.py run.
    """
    import logging as _log
    _logger = _log.getLogger("backfill_weather")
    try:
        # Redirect print() to the module logger so output isn't swallowed silently
        import builtins as _bt
        _orig_print = _bt.print

        def _log_print(*args, **kwargs):
            _logger.info("[weather_backfill] %s", " ".join(str(a) for a in args))

        _bt.print = _log_print
        main()
    finally:
        _bt.print = _orig_print


if __name__ == "__main__":
    main()
