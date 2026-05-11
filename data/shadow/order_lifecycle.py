"""Shadow order-lifecycle recorder — Tier 1 execution-path addition.

Captures the full submit → ack → fill/cancel/reject sequence for every order
the bot places. This is the only data source that gives us:

  - Actual fill prices vs intended prices (corrects replay engine's slip assumption)
  - Queue latency: time from submit to ack, ack to fill
  - Cancel rate by token/session/regime
  - Maker-rebate strategy evaluation (Polymarket pays 20% maker rebate on resting buys)

Schema (one row per lifecycle event):
  record_type: "order_lifecycle"
  schema_version: 1
  ts_s, ts_ms_local          — wall clock at event time
  event                      — "submit" | "fill" | "cancel" | "reject"
  order_id                   — our polymarket order ID (from signed order)
  token_id, condition_id, asset, outcome_side
  seconds_to_resolution      — from feed cache at event time (0 if unavailable)
  side                       — "BUY" | "SELL"
  intended_price             — snapped limit price sent to CLOB
  intended_size              — snapped size sent to CLOB
  realized_price             — fill price (fill/cancel events only; null on submit/reject)
  realized_size              — fill size  (fill/cancel events only; null on submit/reject)
  latency_ms                 — ms since matching submit event (fill/cancel/reject only)
  cf_attempts                — number of CF retry attempts before this outcome

Compliance:
  - Principle #4 (timing provenance): ts_ms_local on every row
  - Principle #9 (additive only): new record_type, no schema mutation
  - Principle #11 (telemetry): rides ShadowPipeline
  - Principle #18 (drops are hard fails): emitter failures must never raise;
    all calls are wrapped in try/except at the call site

CRITICAL: this recorder hooks into the order execution path.
Any exception raised by emit_order_event MUST NOT propagate — it would
block or corrupt order submission / fill logic. The caller wraps every
call in try/except. This file itself also catches all exceptions internally.
"""
import time

SCHEMA_VERSION = 1


def emit_order_event(
    pipeline,
    *,
    event: str,                    # "submit" | "fill" | "cancel" | "reject"
    order_id: str,
    token_id: str,
    condition_id: str,
    asset: str,
    outcome_side: str,
    seconds_to_resolution: float,
    side: str,                     # "BUY" | "SELL"
    intended_price: float,
    intended_size: float,
    realized_price: float = None,
    realized_size: float = None,
    latency_ms: float = None,
    cf_attempts: int = 0,
) -> None:
    """Fire-and-forget — non-blocking, drop-on-full via ShadowPipeline.

    Called from execution/order_manager.py at submit, fill, cancel, reject.
    All exceptions are caught internally; caller should also wrap in try/except.
    """
    if pipeline is None:
        return
    try:
        now = time.time()
        rec = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "order_lifecycle",
            "ts_s": int(now),
            "ts_ms_local": int(now * 1000),
            "event": event,
            "order_id": order_id or "",
            "token_id": token_id or "",
            "condition_id": condition_id or "",
            "asset": asset or "",
            "outcome_side": outcome_side or "",
            "seconds_to_resolution": round(float(seconds_to_resolution or 0), 1),
            "side": side or "",
            "intended_price": float(intended_price) if intended_price is not None else None,
            "intended_size": float(intended_size) if intended_size is not None else None,
            "realized_price": float(realized_price) if realized_price is not None else None,
            "realized_size": float(realized_size) if realized_size is not None else None,
            "latency_ms": round(float(latency_ms), 1) if latency_ms is not None else None,
            "cf_attempts": int(cf_attempts),
        }
        pipeline.emit(rec)
    except Exception:
        pass  # never raise from a recorder
