"""
analytics/lag_detector.py — Binance/Polymarket WS lag detector

Subscribes simultaneously to:
  - Binance SPOT aggTrade stream (ETH/BTC/SOL)
  - Polymarket CLOB market channel (all active ETH/BTC/SOL updown tokens)

Records every event to logs/lag_ws_events.jsonl with ms-precision timestamps.

On Ctrl-C (or --duration expiry), prints a lag summary:
  For each Binance move >= threshold in 1s, how many ms until Polymarket ask
  changed for the correlated token?

This answers: is the cross-market lag exploitable with WS, or is it already
sub-100ms (arbed away too fast)?

Usage:
    python3 analytics/lag_detector.py                # run until Ctrl-C
    python3 analytics/lag_detector.py --duration 3600
    python3 analytics/lag_detector.py --summarize    # analyze existing log only

No credentials required. Polymarket market channel is public read-only.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

# ── Endpoints ──────────────────────────────────────────────────────────────────

_BINANCE_WS   = "wss://stream.binance.com:9443/stream?streams={streams}"
_CLOB_REST    = "https://clob.polymarket.com"
_CLOB_WS      = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

_BINANCE_SYMS = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}

# ── Parameters ──────────────────────────────────────────────────────────────────

_MOVE_WINDOW_S    = 1.0    # measure Binance pct-change over this window
_MOVE_THRESHOLD   = 0.001   # 0.1% — log a "move event" if Binance moves this much in window
_LAG_HORIZON_S    = 30.0   # look this far forward for Polymarket repricing
_LAG_REPRICE_MIN  = 0.005  # minimum ask change to count as "repriced" (0.5pp)

# ── Data types ──────────────────────────────────────────────────────────────────

@dataclass
class Token:
    token_id:     str
    asset:        str   # BTC / ETH / SOL
    outcome:      str   # YES / NO
    condition_id: str


# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("lag_detector")

# ── Output ─────────────────────────────────────────────────────────────────────

_OUT_PATH = Path("logs/lag_ws_events.jsonl")
_out_file = None

def _out() -> object:
    global _out_file
    if _out_file is None:
        _OUT_PATH.parent.mkdir(exist_ok=True)
        _out_file = open(_OUT_PATH, "a", buffering=1)
    return _out_file

def _write(record: dict) -> None:
    try:
        _out().write(json.dumps(record) + "\n")
    except Exception:
        pass


# ── Market discovery ───────────────────────────────────────────────────────────

_GAMMA_API = "https://gamma-api.polymarket.com"

# Slug prefixes the main bot uses per asset
_SLUG_PREFIXES = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}

# Keywords to confirm asset from question text (fallback)
_ASSET_KEYWORDS = {
    "BTC": ["BTC", "Bitcoin", "BITCOIN"],
    "ETH": ["ETH", "Ethereum", "ETHEREUM"],
    "SOL": ["SOL", "Solana", "SOLANA"],
}

def _detect_asset(question: str) -> Optional[str]:
    for asset, keywords in _ASSET_KEYWORDS.items():
        if any(kw in question for kw in keywords):
            return asset
    return None


def _extract_markets(raw: object) -> list[dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("data", "markets"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if raw.get("conditionId") or raw.get("condition_id"):
            return [raw]
    return []


async def discover_tokens(session: aiohttp.ClientSession) -> list[Token]:
    """
    Find active ETH/BTC/SOL updown tokens using the same slug-based approach
    as the main bot: current window + next window for 5m and 15m intervals.

    Falls back to broader Gamma bulk scan if slug lookup returns nothing.
    """
    tokens: list[Token] = []
    seen_token_ids: set[str] = set()

    now_ts = int(time.time())
    slugs: list[str] = []
    for asset, prefixes in _SLUG_PREFIXES.items():
        for prefix in prefixes:
            for interval in (300, 900):          # 5m and 15m
                w_ts = now_ts - (now_ts % interval)
                slugs.append(f"{prefix}-updown-{interval // 60}m-{w_ts}")
                slugs.append(f"{prefix}-updown-{interval // 60}m-{w_ts + interval}")

    _timeout = aiohttp.ClientTimeout(total=5.0)

    async def _fetch_slug(slug: str) -> list[dict]:
        for base in (_GAMMA_API, _CLOB_REST):
            try:
                async with session.get(
                    f"{base}/markets",
                    params={"slug": slug},
                    timeout=_timeout,
                ) as resp:
                    if resp.status == 200:
                        return _extract_markets(await resp.json())
            except Exception:
                pass
        return []

    results = await asyncio.gather(*[_fetch_slug(s) for s in slugs])
    markets: list[dict] = []
    for batch in results:
        markets.extend(batch)

    log.info("Slug lookup: %d raw market records across %d slugs", len(markets), len(slugs))

    # Deduplicate by condition_id and extract token IDs
    seen_conditions: set[str] = set()
    for mkt in markets:
        cid = str(mkt.get("conditionId") or mkt.get("condition_id") or "")
        if not cid or cid in seen_conditions:
            continue
        seen_conditions.add(cid)

        question = mkt.get("question", "")
        asset = _detect_asset(question)
        if not asset:
            slug = str(mkt.get("market_slug") or mkt.get("slug") or "").lower()
            for a, prefixes in _SLUG_PREFIXES.items():
                if any(p in slug for p in prefixes):
                    asset = a
                    break
        if not asset:
            continue

        # Gamma returns clobTokenIds as a JSON-encoded string (e.g. '["tid1","tid2"]')
        # and outcomes as a JSON-encoded string too
        raw_ids      = mkt.get("clobTokenIds", "[]")
        raw_outcomes = mkt.get("outcomes", "[]")
        try:
            clob_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
            outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
        except (json.JSONDecodeError, TypeError):
            clob_ids, outcomes = [], []
        # CLOB /markets/{cid} response returns tokens as dicts
        clob_dicts = mkt.get("tokens", [])

        if clob_ids and outcomes and len(clob_ids) == len(outcomes):
            for tid, outcome in zip(clob_ids, outcomes):
                tid = str(tid)
                if not tid or tid in seen_token_ids:
                    continue
                seen_token_ids.add(tid)
                tokens.append(Token(
                    token_id=tid,
                    asset=asset,
                    outcome=outcome.upper(),
                    condition_id=cid,
                ))
        elif clob_dicts:
            for tok in clob_dicts:
                tid = str(tok.get("token_id") or tok.get("tokenId") or "")
                outcome = str(tok.get("outcome", "")).upper()
                if not tid or tid in seen_token_ids:
                    continue
                seen_token_ids.add(tid)
                tokens.append(Token(
                    token_id=tid,
                    asset=asset,
                    outcome=outcome,
                    condition_id=cid,
                ))

    by_asset = {a: sum(1 for t in tokens if t.asset == a) for a in _SLUG_PREFIXES}
    log.info("Tokens discovered: BTC=%d ETH=%d SOL=%d",
             by_asset["BTC"], by_asset["ETH"], by_asset["SOL"])
    return tokens


# ── Shared state ───────────────────────────────────────────────────────────────

# Rolling price buffer: deque of (ts, price) per asset — last 10s
_binance_prices: dict[str, collections.deque] = {
    a: collections.deque(maxlen=1000) for a in _BINANCE_SYMS
}
# Last known ask per token_id
_poly_ask: dict[str, float] = {}

# token_id → asset (populated after discovery)
_token_asset: dict[str, str] = {}

# Pending move events: asset → (ts, price_at_move, direction)
# direction: +1 (up) or -1 (down)
_pending_moves: dict[str, tuple[float, float, int]] = {}

# Completed lag measurements
_lag_samples: list[dict] = []

_stop_event = asyncio.Event()


# ── Binance WS ─────────────────────────────────────────────────────────────────

async def run_binance() -> None:
    streams = "/".join(f"{sym}@aggTrade" for sym in _BINANCE_SYMS.values())
    url = _BINANCE_WS.format(streams=streams)

    while not _stop_event.is_set():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    url,
                    heartbeat=20.0,
                    timeout=aiohttp.ClientTimeout(connect=10.0),
                ) as ws:
                    log.info("Binance WS connected: %s", ", ".join(_BINANCE_SYMS))
                    async for msg in ws:
                        if _stop_event.is_set():
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            outer = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue
                        data = outer.get("data", outer)
                        if data.get("e") != "aggTrade":
                            continue

                        sym = data.get("s", "").upper()
                        asset = next((a for a, s in _BINANCE_SYMS.items()
                                      if s.upper() == sym), None)
                        if not asset:
                            continue

                        ts    = data["T"] / 1000.0   # trade time ms → seconds
                        price = float(data["p"])

                        buf = _binance_prices[asset]
                        buf.append((ts, price))

                        # Compute pct change over _MOVE_WINDOW_S
                        cutoff = ts - _MOVE_WINDOW_S
                        old_prices = [p for t, p in buf if t >= cutoff]
                        if len(old_prices) < 2:
                            continue
                        ref_price = old_prices[0]
                        pct = (price - ref_price) / ref_price

                        # Log raw Binance event (throttled: only if price changed ≥ 0.01%)
                        if abs(pct) >= 0.0001:
                            _write({
                                "ts": round(ts, 3),
                                "src": "binance",
                                "asset": asset,
                                "price": price,
                                "pct_1s": round(pct * 100, 4),
                            })

                        # Emit a move event if threshold crossed
                        if abs(pct) >= _MOVE_THRESHOLD:
                            direction = 1 if pct > 0 else -1
                            existing = _pending_moves.get(asset)
                            # Only register new move if no pending one within 5s
                            if not existing or (ts - existing[0]) > 5.0:
                                _pending_moves[asset] = (ts, price, direction)
                                log.debug("MOVE event | %s dir=%+d pct=%.3f%%", asset, direction, pct * 100)
                                _on_binance_move(asset, ts, direction)

                        # Expire stale pending moves
                        for a in list(_pending_moves):
                            if ts - _pending_moves[a][0] > _LAG_HORIZON_S:
                                _pending_moves.pop(a)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not _stop_event.is_set():
                log.warning("Binance WS error: %s — reconnecting in 3s", exc)
                await asyncio.sleep(3)


# ── Polymarket WS ─────────────────────────────────────────────────────────────

def _subscribe_payload(token_ids: list[str]) -> str:
    return json.dumps({
        "auth":       {"apiKey": ""},
        "type":       "market",
        "assets_ids": token_ids,
    })


async def run_polymarket(tokens: list[Token]) -> None:
    if not tokens:
        log.error("No tokens to subscribe — polymarket WS disabled")
        return

    token_map: dict[str, Token] = {t.token_id: t for t in tokens}
    token_ids = list(token_map.keys())
    log.info("Subscribing to %d Polymarket tokens", len(token_ids))

    import ssl as _ssl
    try:
        import certifi as _certifi
        ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
    except ImportError:
        ssl_ctx = _ssl.create_default_context()

    # Subscription in batches of 200 (WS limit)
    batch_size = 200

    while not _stop_event.is_set():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    _CLOB_WS,
                    ssl=ssl_ctx,
                    heartbeat=20.0,
                    timeout=aiohttp.ClientTimeout(connect=10.0),
                ) as ws:
                    # Send subscription in batches
                    for i in range(0, len(token_ids), batch_size):
                        batch = token_ids[i:i + batch_size]
                        await ws.send_str(_subscribe_payload(batch))
                    log.info("Polymarket WS connected")

                    async for msg in ws:
                        if _stop_event.is_set():
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            payload = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue

                        now = time.time()
                        events = payload if isinstance(payload, list) else [payload]

                        for event in events:
                            # Book snapshot: seed last known asks
                            if "bids" in event or "asks" in event:
                                tid = str(event.get("asset_id", ""))
                                tok = token_map.get(tid)
                                if not tok:
                                    continue
                                asks = event.get("asks", [])
                                if asks:
                                    try:
                                        best_ask = min(float(a["price"]) for a in asks)
                                        _poly_ask[tid] = best_ask
                                        _write({
                                            "ts":       round(now, 3),
                                            "src":      "poly_snap",
                                            "asset":    tok.asset,
                                            "outcome":  tok.outcome,
                                            "token_id": tid,
                                            "ask":      best_ask,
                                        })
                                    except (KeyError, ValueError):
                                        pass

                            # Incremental price_changes
                            elif "price_changes" in event:
                                for chg in event.get("price_changes", []):
                                    tid  = str(chg.get("asset_id", ""))
                                    side = chg.get("side", "")
                                    tok  = token_map.get(tid)
                                    if not tok or side not in ("BUY", "SELL"):
                                        continue
                                    try:
                                        price = float(chg["price"])
                                        size  = float(chg.get("size", 0))
                                    except (KeyError, ValueError):
                                        continue

                                    # Track best-ask changes; only log when ask moves
                                    if side == "SELL":
                                        prev_ask = _poly_ask.get(tid)
                                        new_best: Optional[float] = None
                                        if size == 0:
                                            # Level removed — ask may have risen; record unknown
                                            _poly_ask.pop(tid, None)
                                            new_best = None
                                        else:
                                            if prev_ask is None or price < prev_ask:
                                                _poly_ask[tid] = price
                                                new_best = price
                                            elif price == prev_ask:
                                                new_best = None  # size update, ask unchanged

                                        # Log only when best ask changes
                                        if new_best is not None and new_best != prev_ask:
                                            _write({
                                                "ts":       round(now, 3),
                                                "src":      "poly_ask",
                                                "asset":    tok.asset,
                                                "outcome":  tok.outcome,
                                                "token_id": tid,
                                                "ask":      new_best,
                                                "ask_prev": prev_ask,
                                            })
                                            _check_lag_for_token(now, tid, tok)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not _stop_event.is_set():
                log.warning("Polymarket WS error: %s — reconnecting in 3s", exc)
                await asyncio.sleep(3)


# ── Lag matching ───────────────────────────────────────────────────────────────

# Snapshot of ask per token at the moment a Binance move was recorded.
# token_id → (move_ts, ask_at_move, direction)
# Set when a Binance move fires; consumed once the corresponding ask moves.
_ask_at_move: dict[str, tuple[float, float, int]] = {}


def _on_binance_move(asset: str, move_ts: float, direction: int) -> None:
    """Snapshot current poly asks for tokens of this asset only."""
    for tid, ask in list(_poly_ask.items()):
        if _token_asset.get(tid) != asset:
            continue
        if tid not in _ask_at_move:
            _ask_at_move[tid] = (move_ts, ask, direction)


def _check_lag_for_token(now: float, tid: str, tok: Token) -> None:
    """
    Called on every best-ask change for a Polymarket token.
    If a Binance move was recorded for this asset, measure the lag.
    """
    snap = _ask_at_move.get(tid)
    if not snap:
        return

    move_ts, ask_at_move, direction = snap

    if now - move_ts > _LAG_HORIZON_S:
        _ask_at_move.pop(tid, None)
        return

    new_ask = _poly_ask.get(tid)
    if new_ask is None:
        return

    ask_change = new_ask - ask_at_move
    if abs(ask_change) < _LAG_REPRICE_MIN:
        return  # not a meaningful reprice yet

    lag_ms = (now - move_ts) * 1000.0

    # Direction match: Binance UP → YES ask should rise (less discount),
    # NO ask should fall. Reverse for Binance DOWN.
    if tok.outcome in ("UP", "YES"):
        dir_match = (direction == 1) == (ask_change > 0)
    else:
        dir_match = (direction == 1) == (ask_change < 0)

    lag_record = {
        "ts":          round(now, 3),
        "src":         "lag_event",
        "asset":       tok.asset,
        "outcome":     tok.outcome,
        "token_id":    tid,
        "lag_ms":      round(lag_ms, 1),
        "binance_dir": direction,
        "ask_before":  ask_at_move,
        "ask_after":   new_ask,
        "ask_change":  round(ask_change, 4),
        "dir_match":   dir_match,
    }
    _write(lag_record)
    _lag_samples.append(lag_record)
    _ask_at_move.pop(tid, None)

    log.info(
        "LAG EVENT | %s %s | lag=%.0fms | ask %.4f→%.4f | dir_match=%s",
        tok.asset, tok.outcome, lag_ms, ask_at_move, new_ask, dir_match,
    )


# ── Summary ────────────────────────────────────────────────────────────────────

def _print_summary(samples: list[dict]) -> None:
    if not samples:
        print("\nNo lag events recorded yet.")
        return

    print(f"\n{'='*60}")
    print(f"LAG SUMMARY  (n={len(samples)} events)")
    print(f"{'='*60}")

    lags = sorted(s["lag_ms"] for s in samples)
    n = len(lags)

    def pct(v: float) -> float:
        idx = int(v / 100 * n)
        return lags[min(idx, n - 1)]

    print(f"  p50:  {pct(50):.0f} ms")
    print(f"  p75:  {pct(75):.0f} ms")
    print(f"  p90:  {pct(90):.0f} ms")
    print(f"  p99:  {pct(99):.0f} ms")
    print(f"  max:  {lags[-1]:.0f} ms")
    print(f"  min:  {lags[0]:.0f} ms")

    matches = sum(1 for s in samples if s.get("direction_match"))
    print(f"\n  Direction match: {matches}/{n} = {matches/n*100:.1f}%")

    print("\n  Lag buckets:")
    buckets = [
        ("<100ms",   0,      100),
        ("100–500ms", 100,   500),
        ("500ms–2s",  500,  2000),
        ("2–10s",    2000, 10000),
        ("10–30s", 10000, 30000),
    ]
    for label, lo, hi in buckets:
        cnt = sum(1 for l in lags if lo <= l < hi)
        bar = "█" * min(int(cnt / max(n, 1) * 40), 40)
        print(f"  {label:12s}: {cnt:4d} ({cnt/n*100:5.1f}%)  {bar}")

    print("\n  Per-asset:")
    for asset in ("BTC", "ETH", "SOL"):
        subset = [s for s in samples if s["asset"] == asset]
        if not subset:
            continue
        sub_lags = sorted(s["lag_ms"] for s in subset)
        sn = len(sub_lags)
        m = sum(1 for s in subset if s.get("direction_match"))
        p50 = sub_lags[int(0.5 * sn)]
        p90 = sub_lags[min(int(0.9 * sn), sn - 1)]
        print(f"  {asset}: n={sn:3d}  p50={p50:.0f}ms  p90={p90:.0f}ms  "
              f"dir_match={m/sn*100:.0f}%")

    print(f"\n  Interpretation:")
    p50_val = pct(50)
    if p50_val < 100:
        print("  p50 < 100ms — lag is sub-100ms. Arbed away fast. WS edge requires")
        print("  co-location or aggressive latency work. Standard WS bot unlikely viable.")
    elif p50_val < 1000:
        print("  p50 100ms–1s — WS bot can compete. Polling (1s loop) misses most of this.")
        print("  → STRONG case for V2 WS strategy on cross-market lag.")
    elif p50_val < 10000:
        print("  p50 1–10s — lag large enough that even polling can partially exploit it.")
        print("  → WS gives speed advantage but current 1s loop may already capture some.")
    else:
        print("  p50 > 10s — large lag. Current polling approach already in the window.")
        print("  → WS is nice-to-have, not required for this edge.")
    print()


def _summarize_from_file(path: Path) -> None:
    if not path.exists():
        print(f"No file at {path}")
        return
    samples = []
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("src") == "lag_event":
                    samples.append(r)
            except json.JSONDecodeError:
                pass
    print(f"Loaded {samples.__len__()} lag events from {path}")
    _print_summary(samples)


# ── Main ───────────────────────────────────────────────────────────────────────

async def _main(duration: Optional[float]) -> None:
    async with aiohttp.ClientSession() as session:
        tokens = await discover_tokens(session)

    if not tokens:
        log.error("No tokens discovered — check network / CLOB endpoint")
        return

    # Build module-level token→asset map (used by _on_binance_move for filtering)
    for tok in tokens:
        _token_asset[tok.token_id] = tok.asset

    tasks = [
        asyncio.create_task(run_binance(), name="binance"),
        asyncio.create_task(run_polymarket(tokens), name="polymarket"),
    ]

    if duration:
        log.info("Running for %.0f seconds", duration)
        await asyncio.sleep(duration)
        _stop_event.set()
    else:
        log.info("Running until Ctrl-C (writing to %s)", _OUT_PATH)
        await _stop_event.wait()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    _print_summary(_lag_samples)


def main() -> None:
    global _OUT_PATH

    _default_log = str(_OUT_PATH)
    parser = argparse.ArgumentParser(description="WS lag detector — Binance vs Polymarket")
    parser.add_argument("--duration", type=float, default=None,
                        help="Stop after N seconds (default: run until Ctrl-C)")
    parser.add_argument("--summarize", action="store_true",
                        help="Print summary of existing log file and exit")
    parser.add_argument("--log", default=_default_log,
                        help=f"Output path (default: {_default_log})")
    args = parser.parse_args()

    out_path = Path(args.log)
    _OUT_PATH = out_path

    if args.summarize:
        _summarize_from_file(out_path)
        return

    loop = asyncio.new_event_loop()

    def _sig_handler(*_):
        log.info("Ctrl-C — stopping")
        loop.call_soon_threadsafe(_stop_event.set)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    try:
        loop.run_until_complete(_main(args.duration))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
