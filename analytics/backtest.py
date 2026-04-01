"""
Klaus — Historical Backtest

Replays the Window Sniper logic against real historical data:
  - Binance public REST API  → 1m klines for BTC/ETH/SOL
  - Polymarket Gamma API     → market metadata (slug-based lookup)
  - Polymarket CLOB API      → historical trades (ask approximation)

Fetched data is cached in logs/backtest_cache/ so re-runs are fast.

Usage:
  python3 analytics/backtest.py                  # last 7 days, all assets
  python3 analytics/backtest.py --days 30        # last 30 days
  python3 analytics/backtest.py --asset BTC      # single asset
  python3 analytics/backtest.py --interval 15    # 15m only (5 or 15)
  python3 analytics/backtest.py --no-cache       # force re-fetch

What it tests:
  For every historical 5m/15m window, at every minute between 18%-80%
  elapsed, the script computes what the sniper would have seen:
    delta      = (binance_spot - window_open) / window_open * 100
    fair_value = sigmoid(8 × |delta| × time_confidence)
    edge       = fair_value - pm_ask
    lag_pct    = (fair_value - pm_ask) / (fair_value - 0.50)

  If all gates pass → "virtual entry". Then looks at subsequent PM trade
  prices to determine if +20% or +25% would have been reached.

  PM ask is approximated from the last trade price before each minute.
  This slightly underestimates the true ask but is the best available
  without OB snapshots.

Output:
  - Win rate by hour, asset, lag bucket
  - Trade frequency (entries per day)
  - Avg P&L, avg win, avg loss
  - Which block reason fires most (lag_too_low, edge_negative, etc.)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── API endpoints ─────────────────────────────────────────────────────────────
GAMMA_API   = "https://gamma-api.polymarket.com"
CLOB_API    = "https://clob.polymarket.com"
BINANCE_API = "https://api.binance.com"

CACHE_DIR = os.path.join("logs", "backtest_cache")

# ── Sniper parameters (must match window_sniper.py) ──────────────────────────
SIGMOID_K             = 8.0
TIME_CONFIDENCE_CAP   = 2.5
WINDOW_ELAPSED_MIN    = 0.18
WINDOW_ELAPSED_MAX_5M = 0.40
WINDOW_ELAPSED_MAX_15M= 0.80
MIN_DELTA_5M          = 0.04   # % move required
MIN_DELTA_15M         = 0.08
MIN_EDGE              = 0.06
MIN_EDGE_VPIN         = 0.04   # not tested in backtest (no historical VPIN)
MIN_LAG_REMAINING_5M  = 0.40
MIN_LAG_REMAINING_15M = 0.30
MIN_EDGE_OVERRIDE     = 0.10   # if edge ≥ this, relax lag floor to 0.15
MAX_TOKEN_ASK         = 0.90
MIN_TOKEN_ASK         = 0.35

# ── Slug prefixes (matches feeds.py _SLUG_ALIASES) ───────────────────────────
SLUG_PREFIXES = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = key.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, safe + ".json")


def _cache_get(key: str):
    p = _cache_path(key)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def _cache_set(key: str, data) -> None:
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


# ─────────────────────────────────────────────────────────────────────────────
# Binance klines
# ─────────────────────────────────────────────────────────────────────────────

def fetch_binance_klines(asset: str, start_ms: int, end_ms: int, use_cache: bool = True) -> List[dict]:
    """
    Fetch 1m klines from Binance for the given time range.
    Returns list of {ts_ms, open, high, low, close, volume}.
    Handles pagination (max 1000 per request).
    """
    symbol = BINANCE_SYMBOLS[asset]
    cache_key = f"binance_{symbol}_{start_ms}_{end_ms}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    result = []
    cursor = start_ms
    while cursor < end_ms:
        url = (f"{BINANCE_API}/api/v3/klines"
               f"?symbol={symbol}&interval=1m"
               f"&startTime={cursor}&endTime={end_ms}&limit=1000")
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            print(f"  [WARN] Binance fetch error for {symbol}: {e}")
            break
        if not rows:
            break
        for row in rows:
            result.append({
                "ts_ms": int(row[0]),
                "open":  float(row[1]),
                "high":  float(row[2]),
                "low":   float(row[3]),
                "close": float(row[4]),
            })
        cursor = int(rows[-1][0]) + 60_000  # next minute
        if len(rows) < 1000:
            break
        time.sleep(0.1)  # gentle rate limit

    if use_cache and result:
        _cache_set(cache_key, result)
    return result


def klines_to_minute_map(klines: List[dict]) -> Dict[int, float]:
    """Map minute_ts (unix, floored to minute) → close price."""
    return {k["ts_ms"] // 1000 // 60 * 60: k["close"] for k in klines}


# ─────────────────────────────────────────────────────────────────────────────
# Polymarket market discovery
# ─────────────────────────────────────────────────────────────────────────────

def fetch_market_by_slug(slug: str, use_cache: bool = True) -> Optional[dict]:
    """Fetch one market from Gamma API by slug. Returns None if not found."""
    cache_key = f"gamma_slug_{slug}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached if cached else None

    url = f"{GAMMA_API}/markets?slug={slug}"
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        markets = data if isinstance(data, list) else data.get("markets", [])
        market = markets[0] if markets else None
    except Exception:
        market = None

    if use_cache:
        _cache_set(cache_key, market or {})
    return market


def generate_window_slugs(asset: str, interval: int, start_ts: int, end_ts: int) -> List[Tuple[str, int]]:
    """
    Generate all (slug, window_start_ts) pairs for an asset+interval between start and end.
    Slug format: {prefix}-updown-{interval//60}m-{window_end_ts}
    """
    result = []
    prefixes = SLUG_PREFIXES[asset]
    minutes = interval // 60
    # Align to interval boundary
    cursor = start_ts - (start_ts % interval)
    while cursor < end_ts:
        window_end = cursor + interval
        for prefix in prefixes:
            slug = f"{prefix}-updown-{minutes}m-{window_end}"
            result.append((slug, cursor, window_end))
        cursor += interval
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Polymarket historical trades
# ─────────────────────────────────────────────────────────────────────────────

def fetch_pm_trades(token_id: str, start_ts: float, end_ts: float,
                    use_cache: bool = True) -> List[dict]:
    """
    Fetch historical trades for a token from CLOB API.
    Returns list of {ts, price} sorted by ts ascending.
    """
    cache_key = f"trades_{token_id}_{int(start_ts)}_{int(end_ts)}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    trades = []
    url = f"{CLOB_API}/trades?token_id={token_id}&limit=500"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw = data if isinstance(data, list) else data.get("data", [])
        for t in raw:
            ts = float(t.get("timestamp") or t.get("ts") or 0)
            price = float(t.get("price") or 0)
            if ts and price and start_ts <= ts <= end_ts:
                trades.append({"ts": ts, "price": price})
    except Exception as e:
        pass  # empty trades = no data available

    trades.sort(key=lambda x: x["ts"])
    if use_cache:
        _cache_set(cache_key, trades)
    return trades


def price_at(trades: List[dict], ts: float) -> Optional[float]:
    """Most recent trade price at or before ts. None if no trades yet."""
    price = None
    for t in trades:
        if t["ts"] <= ts:
            price = t["price"]
        else:
            break
    return price


def max_price_after(trades: List[dict], entry_ts: float, window_end_ts: float) -> Optional[float]:
    """Peak trade price between entry_ts and window_end_ts."""
    prices = [t["price"] for t in trades if entry_ts < t["ts"] <= window_end_ts]
    return max(prices) if prices else None


def final_price(trades: List[dict], window_end_ts: float) -> Optional[float]:
    """Last trade price before window end."""
    return price_at(trades, window_end_ts)


# ─────────────────────────────────────────────────────────────────────────────
# Sniper logic (inline — mirrors window_sniper.py)
# ─────────────────────────────────────────────────────────────────────────────

def sigmoid_fv(delta_pct: float, elapsed_pct: float) -> float:
    """Time-adjusted sigmoid fair value."""
    time_remaining = max(0.05, 1.0 - elapsed_pct)
    time_confidence = min(TIME_CONFIDENCE_CAP, 1.0 / math.sqrt(time_remaining))
    return 1.0 / (1.0 + math.exp(-SIGMOID_K * abs(delta_pct) * time_confidence))


def sniper_decision(
    delta_pct: float,
    elapsed_pct: float,
    pm_ask: float,
    is_15m: bool,
) -> Tuple[str, float, float, float, float]:
    """
    Returns (decision, fair_value, edge, lag_remaining_pct, min_edge_used).
    decision: "ENTER" | "lag_too_low" | "edge_negative" | "edge_insufficient"
              | "time_gate" | "delta_too_low" | "ask_bounds"
    """
    # ── Time gate ──────────────────────────────────────────────────────────
    elapsed_max = WINDOW_ELAPSED_MAX_15M if is_15m else WINDOW_ELAPSED_MAX_5M
    if elapsed_pct < WINDOW_ELAPSED_MIN or elapsed_pct > elapsed_max:
        return "time_gate", 0, 0, 0, 0

    # ── Delta gate ─────────────────────────────────────────────────────────
    min_delta = MIN_DELTA_15M if is_15m else MIN_DELTA_5M
    if abs(delta_pct) < min_delta:
        return "delta_too_low", 0, 0, 0, 0

    # ── Ask bounds ─────────────────────────────────────────────────────────
    if pm_ask > MAX_TOKEN_ASK or pm_ask < MIN_TOKEN_ASK:
        return "ask_bounds", 0, 0, 0, 0

    # ── Fair value + edge ──────────────────────────────────────────────────
    fv = sigmoid_fv(delta_pct, elapsed_pct)
    edge = fv - pm_ask

    if edge <= 0:
        return "edge_negative", fv, edge, 0.0, 0

    # ── Lag remaining ──────────────────────────────────────────────────────
    expected_move = fv - 0.50
    lag_pct = max(0.0, (fv - pm_ask) / expected_move) if expected_move > 0.01 else 0.0

    min_lag = MIN_LAG_REMAINING_5M if not is_15m else MIN_LAG_REMAINING_15M
    if edge >= MIN_EDGE_OVERRIDE:
        min_lag = min(min_lag, 0.15)

    if lag_pct < min_lag:
        return "lag_too_low", fv, edge, lag_pct, 0

    # ── Edge gate ──────────────────────────────────────────────────────────
    min_edge = MIN_EDGE
    if edge < min_edge:
        return "edge_insufficient", fv, edge, lag_pct, min_edge

    return "ENTER", fv, edge, lag_pct, min_edge


# ─────────────────────────────────────────────────────────────────────────────
# Backtest one window
# ─────────────────────────────────────────────────────────────────────────────

def backtest_window(
    asset: str,
    side: str,          # "YES" or "NO"
    window_start: float,
    window_end: float,
    window_seconds: int,
    spot_map: Dict[int, float],  # minute_ts → close price
    trades: List[dict],
) -> List[dict]:
    """
    Walk through every minute in the window. At each minute, check if the
    sniper would have entered. If so, record the outcome.
    Returns list of virtual trade records.
    """
    results = []
    is_15m = window_seconds > 300

    # Window open spot price (nearest available minute)
    open_minute = int(window_start) // 60 * 60
    spot_open = spot_map.get(open_minute)
    if not spot_open:
        return []  # no Binance data for this window

    entered_this_window = False  # only one entry per window per side

    # Walk minutes from window start to end
    t = open_minute + 60  # start checking at 1 minute in
    while t < window_end:
        spot_now = spot_map.get(t)
        if spot_now is None:
            t += 60
            continue

        elapsed = t - window_start
        elapsed_pct = elapsed / window_seconds

        # Delta: if side=YES, we buy YES → asset must be UP (positive delta)
        # If side=NO, we buy NO → asset must be DOWN (negative delta)
        raw_delta = (spot_now - spot_open) / spot_open * 100
        if side == "YES" and raw_delta < 0:
            t += 60
            continue
        if side == "NO" and raw_delta > 0:
            t += 60
            continue

        delta_pct = raw_delta  # signed, direction already checked above

        # PM ask at this minute
        pm_ask = price_at(trades, float(t))
        if pm_ask is None or pm_ask <= 0:
            t += 60
            continue

        decision, fv, edge, lag_pct, _ = sniper_decision(delta_pct, elapsed_pct, pm_ask, is_15m)

        if decision == "ENTER" and not entered_this_window:
            entered_this_window = True
            entry_ts = float(t)
            entry_ask = pm_ask

            peak = max_price_after(trades, entry_ts, window_end)
            final = final_price(trades, window_end)

            pnl = (final - entry_ask) / entry_ask if final else None
            would_win_20 = (peak >= entry_ask * 1.20) if peak else None
            would_win_25 = (peak >= entry_ask * 1.25) if peak else None

            hour_utc = datetime.fromtimestamp(entry_ts, tz=timezone.utc).hour
            results.append({
                "asset": asset,
                "side": side,
                "window_start": window_start,
                "window_end": window_end,
                "window_seconds": window_seconds,
                "entry_ts": entry_ts,
                "entry_ask": round(entry_ask, 4),
                "fair_value": round(fv, 4),
                "edge": round(edge, 4),
                "lag_pct": round(lag_pct, 3),
                "delta_pct": round(delta_pct, 4),
                "elapsed_pct": round(elapsed_pct, 3),
                "hour_utc": hour_utc,
                "peak_ask": round(peak, 4) if peak else None,
                "final_ask": round(final, 4) if final else None,
                "pnl": round(pnl, 4) if pnl else None,
                "would_win_20": would_win_20,
                "would_win_25": would_win_25,
            })

        t += 60

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    assets: List[str],
    days: int,
    intervals: List[int],
    use_cache: bool,
) -> List[dict]:
    now = int(time.time())
    start_ts = now - days * 86400
    all_trades_data: List[dict] = []

    for asset in assets:
        print(f"\n[{asset}] Fetching Binance klines ({days}d)...")
        klines = fetch_binance_klines(asset, start_ts * 1000, now * 1000, use_cache)
        if not klines:
            print(f"  No Binance data for {asset}, skipping.")
            continue
        spot_map = klines_to_minute_map(klines)
        print(f"  {len(spot_map)} minutes of spot data")

        for interval in intervals:
            slugs = generate_window_slugs(asset, interval, start_ts, now)
            print(f"  [{interval//60}m] {len(slugs)//len(SLUG_PREFIXES[asset])} windows to check...")

            hit = 0
            for slug, w_start, w_end in slugs:
                market = fetch_market_by_slug(slug, use_cache)
                if not market:
                    continue
                hit += 1

                tokens = market.get("tokens") or market.get("clobTokenIds") or []
                # Handle both formats
                if tokens and isinstance(tokens[0], dict):
                    token_pairs = [(t.get("token_id") or t.get("outcome_id"), t.get("outcome", "")) for t in tokens]
                else:
                    token_pairs = [(tid, "") for tid in tokens]

                for token_id, outcome in token_pairs:
                    if not token_id:
                        continue
                    # Determine side from outcome label
                    outcome_lo = outcome.lower()
                    if "yes" in outcome_lo or "up" in outcome_lo or outcome_lo == "":
                        side = "YES"
                    elif "no" in outcome_lo or "down" in outcome_lo:
                        side = "NO"
                    else:
                        side = "YES"  # default

                    trades = fetch_pm_trades(token_id, float(w_start), float(w_end), use_cache)
                    if len(trades) < 3:
                        continue  # too sparse to backtest

                    window_results = backtest_window(
                        asset=asset, side=side,
                        window_start=float(w_start), window_end=float(w_end),
                        window_seconds=interval,
                        spot_map=spot_map,
                        trades=trades,
                    )
                    all_trades_data.extend(window_results)

            print(f"  [{interval//60}m] {hit} markets found, {sum(1 for t in all_trades_data if t['window_seconds'] == interval and t['asset'] == asset)} virtual entries so far")

    return all_trades_data


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def report(trades: List[dict], days: int) -> None:
    if not trades:
        print("\nNo virtual trades generated. Possible causes:")
        print("  - Polymarket API returned no historical markets (slugs not found)")
        print("  - PM trades too sparse (< 3 trades per window)")
        print("  - All windows blocked by sniper gates")
        return

    rated = [t for t in trades if t.get("would_win_20") is not None]
    print(f"\n{'='*65}")
    print(f"  BACKTEST RESULTS  ({days}d, {len(trades)} virtual entries, {len(rated)} with outcomes)")
    print(f"{'='*65}")

    if not rated:
        print("  No completed trades (final prices unavailable)")
        return

    wr = sum(t["would_win_20"] for t in rated) / len(rated)
    pnls = [t["pnl"] for t in rated if t.get("pnl") is not None]
    avg_pnl = sum(pnls) / len(pnls) if pnls else 0
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    per_day = len(trades) / days

    print(f"\n  Overall WR (+20% target): {wr:.0%}  ({sum(t['would_win_20'] for t in rated)}/{len(rated)})")
    print(f"  Avg P&L at window close:  {avg_pnl:+.1%}")
    print(f"  Avg win:  {sum(wins)/len(wins):+.1%}  ({len(wins)} wins)" if wins else "  No wins")
    print(f"  Avg loss: {sum(losses)/len(losses):+.1%}  ({len(losses)} losses)" if losses else "  No losses")
    print(f"  Frequency: {per_day:.1f} entries/day")

    # By asset
    print(f"\n  By asset:")
    by_asset: dict = defaultdict(list)
    for t in rated:
        by_asset[t["asset"]].append(t)
    for asset, group in sorted(by_asset.items()):
        g_wr = sum(t["would_win_20"] for t in group) / len(group)
        g_pnls = [t["pnl"] for t in group if t.get("pnl") is not None]
        g_avg = sum(g_pnls) / len(g_pnls) if g_pnls else 0
        print(f"    {asset:<6}  WR={g_wr:.0%}  avg_pnl={g_avg:+.1%}  n={len(group)}")

    # By hour
    print(f"\n  By hour (UTC):")
    by_hour: dict = defaultdict(list)
    for t in rated:
        by_hour[t["hour_utc"]].append(t)
    for hour in sorted(by_hour.keys()):
        group = by_hour[hour]
        h_wr = sum(t["would_win_20"] for t in group) / len(group)
        h_pnls = [t["pnl"] for t in group if t.get("pnl") is not None]
        h_avg = sum(h_pnls) / len(h_pnls) if h_pnls else 0
        bar = "█" * int(h_wr * 20)
        print(f"    {hour:02d}:xx  WR={h_wr:.0%}  avg={h_avg:+.1%}  n={len(group):>3}  {bar}")

    # By lag bucket
    print(f"\n  By lag remaining at entry:")
    buckets = [("0-20%", 0, 0.20), ("20-40%", 0.20, 0.40),
               ("40-60%", 0.40, 0.60), ("60-80%", 0.60, 0.80), ("80-100%", 0.80, 1.01)]
    for label, lo, hi in buckets:
        group = [t for t in rated if lo <= t.get("lag_pct", 0) < hi]
        if group:
            g_wr = sum(t["would_win_20"] for t in group) / len(group)
            g_pnls = [t["pnl"] for t in group if t.get("pnl") is not None]
            g_avg = sum(g_pnls) / len(g_pnls) if g_pnls else 0
            print(f"    lag {label:<10}  WR={g_wr:.0%}  avg={g_avg:+.1%}  n={len(group)}")

    # By interval
    print(f"\n  By window type:")
    for wtype, wsec in [("5m", 300), ("15m", 900)]:
        group = [t for t in rated if t["window_seconds"] == wsec]
        if group:
            g_wr = sum(t["would_win_20"] for t in group) / len(group)
            g_pnls = [t["pnl"] for t in group if t.get("pnl") is not None]
            g_avg = sum(g_pnls) / len(g_pnls) if g_pnls else 0
            print(f"    {wtype:<5}  WR={g_wr:.0%}  avg={g_avg:+.1%}  n={len(group)}")

    # Save results
    out_path = os.path.join("logs", "backtest_results.jsonl")
    os.makedirs("logs", exist_ok=True)
    with open(out_path, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")
    print(f"\n  Full results saved to {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Klaus Window Sniper backtester")
    parser.add_argument("--days",     type=int,   default=7,                    help="Days of history (default 7)")
    parser.add_argument("--asset",    type=str,   default=None,                 help="Single asset: BTC, ETH, SOL")
    parser.add_argument("--interval", type=int,   default=None,  choices=[5,15], help="Window minutes: 5 or 15")
    parser.add_argument("--no-cache", action="store_true",                       help="Force re-fetch all data")
    args = parser.parse_args()

    assets    = [args.asset.upper()] if args.asset else ["BTC", "ETH", "SOL"]
    intervals = [args.interval * 60] if args.interval else [300, 900]
    use_cache = not args.no_cache

    print(f"Klaus Backtest | {args.days}d | assets={assets} | intervals={[i//60 for i in intervals]}m | cache={use_cache}")

    trades = run_backtest(assets=assets, days=args.days, intervals=intervals, use_cache=use_cache)
    report(trades, args.days)
