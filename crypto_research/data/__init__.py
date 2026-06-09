"""Data layer: typed schemas + lazy loaders + window-panel assembly."""

from __future__ import annotations

from .schema import (
    BinanceTrade,
    MarketTimelineRow,
    ObDelta,
    TokenTrade,
    WindowKey,
    WindowPanel,
    WindowResolution,
    panels_to_frame,
)
from .loader import (
    DEFAULT_HOT_ROOT,
    attach_binance_ticks,
    build_window_panels,
    discover_dates,
    iter_binance_trade,
    iter_jsonl,
    iter_market_timeline,
    iter_ob_delta,
    iter_token_trade,
    iter_window_resolution,
    load_resolution_index,
    make_synthetic_panels,
)

__all__ = [
    "BinanceTrade",
    "MarketTimelineRow",
    "ObDelta",
    "TokenTrade",
    "WindowResolution",
    "WindowPanel",
    "WindowKey",
    "panels_to_frame",
    "DEFAULT_HOT_ROOT",
    "iter_jsonl",
    "discover_dates",
    "iter_window_resolution",
    "iter_market_timeline",
    "iter_ob_delta",
    "iter_token_trade",
    "iter_binance_trade",
    "load_resolution_index",
    "build_window_panels",
    "attach_binance_ticks",
    "make_synthetic_panels",
]
