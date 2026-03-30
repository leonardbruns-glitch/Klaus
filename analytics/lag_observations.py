"""
Klaus — Lag Observation Logger

Records Binance spot price alongside every Polymarket SCAN for updown markets.
Used to validate whether Binance-to-Polymarket price lag exists and is tradeable.

Does NOT affect any trading logic. Pure data collection.

Log file: logs/lag_observations.jsonl
Each line: one observation per updown token per scan cycle.

Run analytics/lag_analysis.py after 2-3 days to analyse the data.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

_LOG_PATH = os.path.join("logs", "lag_observations.jsonl")
_log_file = None


def _get_file():
    global _log_file
    if _log_file is None:
        os.makedirs("logs", exist_ok=True)
        _log_file = open(_LOG_PATH, "a", buffering=1)  # line-buffered
    return _log_file


def log_lag_observation(
    ts: float,
    asset: str,
    token_id: str,
    side: str,
    market_type: str,
    window_end_ts: float,
    polymarket_price: float,
    binance_spot_price: Optional[float],
    binance_1m_pct: Optional[float],
    binance_5m_pct: Optional[float],
    binance_15m_pct: Optional[float],
) -> None:
    """Append one observation record. Never raises — logging must not crash the bot."""
    try:
        record = {
            "ts": round(ts, 3),
            "asset": asset,
            "token_id": token_id,
            "side": side,
            "market_type": market_type,
            "window_end_ts": round(window_end_ts, 1),
            "remaining_s": round(window_end_ts - ts, 1) if window_end_ts > 0 else None,
            "polymarket_price": polymarket_price,
            "binance_spot": binance_spot_price,
            "binance_1m_pct": round(binance_1m_pct, 6) if binance_1m_pct is not None else None,
            "binance_5m_pct": round(binance_5m_pct, 6) if binance_5m_pct is not None else None,
            "binance_15m_pct": round(binance_15m_pct, 6) if binance_15m_pct is not None else None,
        }
        _get_file().write(json.dumps(record) + "\n")
    except Exception:
        pass  # never crash the bot over logging
