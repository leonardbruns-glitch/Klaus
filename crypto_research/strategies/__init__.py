"""Strategy layer: the Strategy ABC + Signal/Context/Params contract + registry.

The four concrete strategies import from :mod:`crypto_research.strategies.base`
and register themselves via :func:`register_strategy`.  Importing this package
exposes the contract; concrete strategy modules are imported on demand so the
registry is populated when their module is loaded.
"""

from __future__ import annotations

from .base import (
    Signal,
    SignalSide,
    Strategy,
    StrategyContext,
    StrategyParams,
    available_strategies,
    build_strategy,
    get_strategy,
    register_strategy,
)

__all__ = [
    "Signal",
    "SignalSide",
    "Strategy",
    "StrategyContext",
    "StrategyParams",
    "register_strategy",
    "get_strategy",
    "available_strategies",
    "build_strategy",
]
