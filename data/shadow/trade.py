"""Shadow trade-tape emitters — Phase 1 ingestion expansion (Commit B).

Two record types, both event-driven from feeds.py callbacks:

  - token_trade   → Polymarket CLOB last_trade_price events for tracked
                    updown tokens (with aggressor side when reported).
  - binance_trade → Binance futures aggTrade tape for BTC/ETH/SOL
                    (taker side derived from is_buyer_maker).

Both are real-time-only data the live bot already receives but currently
discards (token trades feed only the bar builders; aggTrades feed only
the VPIN tracker). Without persistence here, this is irrecoverable.

Fired non-blocking through ShadowPipeline.emit (drop-on-full).
"""
import time

SCHEMA_VERSION = 1


def _exchange_ts_ms(ev: dict) -> int:
    """Best-effort exchange timestamp from a Polymarket WS event payload.

    Polymarket docs say a millisecond timestamp is present in every event
    but the field name isn't formally documented; try the common candidates.
    """
    for k in ("timestamp", "t", "ts", "ts_ms", "T"):
        v = ev.get(k)
        if v is None:
            continue
        try:
            iv = int(v)
            # Heuristic: ms epoch is ~13 digits in this era; reject seconds
            if iv > 1_000_000_000_000:
                return iv
            if iv > 1_000_000_000:
                return iv * 1000
        except (TypeError, ValueError):
            continue
    return 0


def emit_token_trade(pipeline, bot, token_id: str, ev: dict) -> None:
    """Called from feeds._handle_clob_ws_event for every last_trade_price event."""
    if pipeline is None:
        return
    feed = bot.feed
    token = feed.tokens.get(token_id)
    if token is None:
        return
    if getattr(token, "market_type", None) != "updown":
        return  # only persist updown trades; target/other markets out of scope
    try:
        price = float(ev.get("price", 0))
    except (TypeError, ValueError):
        return
    if price <= 0:
        return
    try:
        size = float(ev.get("size", 0))
    except (TypeError, ValueError):
        size = 0.0

    side = ev.get("side", "") or ""
    if isinstance(side, str):
        side = side.upper()

    now = time.time()
    wend = int(getattr(token, "window_end_ts", 0))
    remaining = (wend - now) if wend else 0.0

    pipeline.emit({
        "schema_version": SCHEMA_VERSION,
        "record_type": "token_trade",
        "ts_s": int(now),
        "ts_ms_local": int(now * 1000),
        "exchange_ts_ms": _exchange_ts_ms(ev),
        "token_id": token_id,
        "condition_id": getattr(token, "condition_id", "") or "",
        "asset": token.asset,
        "outcome_dir": getattr(token, "outcome_direction", "up"),
        "outcome_side": getattr(token, "side", "YES"),
        "window_end_ts": wend,
        "seconds_to_resolution": round(remaining, 1),
        "price": round(price, 4),
        "size": round(size, 4),
        "side": side,  # taker direction if reported; '' if absent
    })


def emit_binance_trade(pipeline, asset: str, price: float, qty: float,
                       is_buyer_maker: bool, exchange_ts_ms: int = 0) -> None:
    """Called from feeds._run_binance_ws for every aggTrade event."""
    if pipeline is None:
        return
    now = time.time()
    pipeline.emit({
        "schema_version": SCHEMA_VERSION,
        "record_type": "binance_trade",
        "ts_s": int(now),
        "ts_ms_local": int(now * 1000),
        "exchange_ts_ms": int(exchange_ts_ms) if exchange_ts_ms else 0,
        "asset": asset,
        "price": float(price),
        "qty": float(qty),
        "is_buyer_maker": bool(is_buyer_maker),
        # Binance convention: m=true → buyer was maker → taker is the seller (SELL)
        # m=false → seller was maker → taker is the buyer (BUY)
        "taker_side": "SELL" if is_buyer_maker else "BUY",
    })
