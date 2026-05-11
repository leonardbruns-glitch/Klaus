"""Shadow liquidation recorder — persists Binance liquidation events.

Binance tracks liquidation cascades in memory (_liquidations dict in feeds.py)
but never persisted them. This recorder writes each liquidation event to shadow
so replay analysis can use them as directional pre-signals.

Schema (one row per liquidation event):
  record_type: "liquidation"
  schema_version: 1
  ts_s, ts_ms_local   — wall clock at event time
  asset               — BTC / ETH / SOL
  symbol              — BTCUSDT etc.
  side                — "BUY" (forced long liquidation) | "SELL" (forced short liq)
  price               — liquidation price
  qty                 — liquidated quantity (base asset)
  notional_usd        — price * qty

Directional signal:
  BUY liquidation  = forced buying (long squeezed) → price likely fell → DOWN signal
  SELL liquidation = forced selling (short squeezed) → price likely rose → UP signal

Compliance:
  - Principle #4 (timing provenance): ts_ms_local on every row
  - Principle #9 (additive only): new record_type
  - Principle #11 (telemetry): rides ShadowPipeline
  - Never raises; called from feeds.py event handler.
"""
import time

SCHEMA_VERSION = 1


def emit_liquidation(
    pipeline,
    *,
    asset: str,
    symbol: str,
    side: str,       # "BUY" or "SELL"
    price: float,
    qty: float,
) -> None:
    """Fire-and-forget. Called from feeds.py _handle_liq_event.
    All exceptions caught internally; never raises.
    """
    if pipeline is None:
        return
    try:
        now = time.time()
        pipeline.emit({
            "schema_version": SCHEMA_VERSION,
            "record_type": "liquidation",
            "ts_s": int(now),
            "ts_ms_local": int(now * 1000),
            "asset": asset or "",
            "symbol": symbol or "",
            "side": side or "",
            "price": float(price) if price is not None else None,
            "qty": float(qty) if qty is not None else None,
            "notional_usd": round(float(price or 0) * float(qty or 0), 2),
        })
    except Exception:
        pass  # never raise from a recorder
