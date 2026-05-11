"""Shadow OB-delta recorder — Tier 1 event-stream addition.

Captures every Polymarket WS price_change / book / best_bid_ask event as one row
per affected level. The full OB SNAPSHOTS we already log in market_timeline.jsonl
discard the per-event sequence; cancels and refills net out within a snapshot
interval. Event deltas are structurally non-reconstructable from snapshots.

Unlocks the following research-grade features (none of which are reachable
from current data):
  - cancel intensity per side per window (Cont-Kukanov filtered OFI)
  - refill-latency after sweeps (order book resiliency lit)
  - flickering-order detection / spoofing filter (arxiv 2507.22712)
  - Hawkes intensity / self+cross-excitation rates
  - liquidity-shock flag (sudden top-N depth drop)

Compliance:
  - Principle #4 (timing provenance): exchange_ts_ms from WS event + local ts_ms
  - Principle #7 (no raw deep OB): top-5 levels only filter at emit time;
    deeper-level events are observed by feeds.py but dropped here.
  - Principle #9 (additive only): new record_type, no shared schema mutation
  - Principle #11 (telemetry): rides ShadowPipeline so file size + dropped
    count surface in shadow_telemetry.jsonl automatically

Fired non-blocking via pipeline.emit (drop-on-full per shadow_engine principles).
"""
import time

SCHEMA_VERSION = 1

# Per-event row cap — protects pipeline queue from pathological events that
# claim thousands of price changes at once. Top-5 each side = 10 max.
TOP_N_LEVELS = 5


def _exchange_ts_ms(ev: dict) -> int:
    """Best-effort exchange timestamp. Same heuristic as trade.py."""
    for k in ("timestamp", "t", "ts", "ts_ms", "T"):
        v = ev.get(k)
        if v is None:
            continue
        try:
            iv = int(v)
            if iv > 1_000_000_000_000:
                return iv
            if iv > 1_000_000_000:
                return iv * 1000
        except (TypeError, ValueError):
            continue
    return 0


def _level_rank_for_side(price: float, side: str, ob) -> int:
    """Return 0-indexed depth rank of `price` on `side`. -1 if not in top-5.

    Cheap top-N filter — we don't need exact rank precision deeper than 5.
    """
    if ob is None:
        return -1
    try:
        if side == "BUY":
            levels = ob.bids[:TOP_N_LEVELS]
        elif side == "SELL":
            levels = ob.asks[:TOP_N_LEVELS]
        else:
            return -1
    except (AttributeError, IndexError):
        return -1
    for i, (lp, _ls) in enumerate(levels):
        try:
            if abs(float(lp) - price) < 1e-9:
                return i
        except (TypeError, ValueError):
            continue
    return -1


def emit_ob_delta(pipeline, bot, asset_id: str, ev: dict) -> None:
    """Called from feeds._handle_clob_ws_event for book/price_change/best_bid_ask.

    Emits one row per affected level. Filters to top-5 only (principle #7).
    Non-blocking; emitter failures must not raise (caller wraps in try/except).
    """
    if pipeline is None:
        return
    feed = bot.feed
    token = feed.tokens.get(asset_id)
    if token is None:
        return
    if getattr(token, "market_type", None) != "updown":
        return

    ev_type = ev.get("event_type", ev.get("type", ""))
    # We care about per-level events. `book` is a full snapshot — recorded
    # already by market_timeline; skip here unless we want true initial-state
    # provenance, which we don't (would double the volume).
    if ev_type not in ("price_change", "best_bid_ask"):
        return

    now = time.time()
    wend = int(getattr(token, "window_end_ts", 0))
    remaining = (wend - now) if wend else 0.0
    ex_ts = _exchange_ts_ms(ev)
    ob = feed.order_books.get(asset_id)  # pre-update snapshot when we're called BEFORE rebuild

    common = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "ob_delta",
        "ts_s": int(now),
        "ts_ms_local": int(now * 1000),
        "exchange_ts_ms": ex_ts,
        "token_id": asset_id,
        "condition_id": getattr(token, "condition_id", "") or "",
        "asset": token.asset,
        "outcome_dir": getattr(token, "outcome_direction", "up"),
        "outcome_side": getattr(token, "side", "YES"),
        "window_end_ts": wend,
        "seconds_to_resolution": round(remaining, 1),
        "event_type": ev_type,
    }

    if ev_type == "best_bid_ask":
        # Single BBO update — emit one row with both best prices.
        try:
            bb = float(ev.get("best_bid")) if ev.get("best_bid") is not None else None
            ba = float(ev.get("best_ask")) if ev.get("best_ask") is not None else None
        except (TypeError, ValueError):
            return
        if bb is None and ba is None:
            return
        rec = dict(common)
        rec.update({
            "level_price": None,
            "level_size": None,
            "level_side": "BBO",
            "level_hash": "",
            "level_rank": 0,
            "best_bid_at_event": bb,
            "best_ask_at_event": ba,
        })
        pipeline.emit(rec)
        return

    # price_change: list of per-level updates
    changes = ev.get("price_changes", [])
    if not changes:
        return
    # Pre-compute BBO context for each row (cheap — single ref look-up per event)
    pre_bb = ob.bids[0][0] if (ob and ob.bids) else None
    pre_ba = ob.asks[0][0] if (ob and ob.asks) else None

    emitted = 0
    for ch in changes:
        try:
            lp = float(ch.get("price"))
            ls = float(ch.get("size"))
        except (TypeError, ValueError):
            continue
        lside = str(ch.get("side", "")).upper()
        if lside not in ("BUY", "SELL"):
            continue
        rank = _level_rank_for_side(lp, lside, ob)
        if rank < 0 or rank >= TOP_N_LEVELS:
            # Filter principle #7: deep levels dropped at write
            continue
        rec = dict(common)
        rec.update({
            "level_price": lp,
            "level_size": ls,                          # zero = removal/cancel
            "level_side": lside,                       # BUY=bid side, SELL=ask side
            "level_hash": str(ch.get("hash", "") or ""),
            "level_rank": rank,
            "best_bid_at_event": pre_bb,
            "best_ask_at_event": pre_ba,
        })
        pipeline.emit(rec)
        emitted += 1
        if emitted >= 2 * TOP_N_LEVELS:
            # hard cap so a pathological event can't flood the queue
            break
