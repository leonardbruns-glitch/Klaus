"""Backtest layer: fills, portfolio, metrics, and the event-driven engine."""

from __future__ import annotations

from .fills import BimodalFillModel, FillResult
from .portfolio import (
    BinaryPosition,
    FeeFn,
    PerpPosition,
    Portfolio,
    TradeRecord,
    default_fee_fn,
    zero_fee_fn,
)
from .metrics import (
    equity_to_returns,
    max_drawdown,
    max_drawdown_usd,
    periods_per_year_for_window,
    profit_factor,
    sharpe,
    sortino,
    summary,
    win_rate,
)
from .engine import BacktestEngine, EngineConfig

__all__ = [
    "BimodalFillModel",
    "FillResult",
    "Portfolio",
    "BinaryPosition",
    "PerpPosition",
    "TradeRecord",
    "FeeFn",
    "default_fee_fn",
    "zero_fee_fn",
    "sharpe",
    "sortino",
    "max_drawdown",
    "max_drawdown_usd",
    "profit_factor",
    "win_rate",
    "summary",
    "equity_to_returns",
    "periods_per_year_for_window",
    "BacktestEngine",
    "EngineConfig",
]
