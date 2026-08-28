"""Parameter-search harness for the crypto_research backtest framework.

This package provides :mod:`crypto_research.optimize.search` — a grid + random
search driver that runs any registered :class:`~crypto_research.strategies.base.Strategy`
through the :class:`~crypto_research.backtest.engine.BacktestEngine` over a set of
:class:`~crypto_research.data.schema.WindowPanel` s, ranks parameter sets by a
configurable objective (default: annualized Sortino) under Profit-Factor and
Max-Drawdown constraints, and supports **walk-forward / train-test split**
evaluation to guard against overfitting.

See :class:`SearchConfig`, :func:`grid_search`, :func:`random_search`,
:func:`walk_forward` and the module docstring of :mod:`search` for the
overfitting guards.
"""

from __future__ import annotations

from .search import (
    EvalResult,
    SearchConfig,
    SearchReport,
    SplitResult,
    backtest_params,
    default_objective,
    grid_search,
    random_search,
    score_metrics,
    split_panels_time,
    walk_forward,
)

__all__ = [
    "EvalResult",
    "SearchConfig",
    "SearchReport",
    "SplitResult",
    "backtest_params",
    "default_objective",
    "grid_search",
    "random_search",
    "score_metrics",
    "split_panels_time",
    "walk_forward",
]
