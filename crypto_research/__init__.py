"""crypto_research — a non-HFT, structurally-advantaged research framework.

A sandbox package for designing and backtesting Polymarket crypto up/down
strategies on the accumulated Tier-1 feature era (see ``CRYPTO_DATA_BLUEPRINT.md``).
It is fully decoupled from the live bot: it only reads logs and never imports
``strategy/`` / ``main.py`` / ``config.py``.

Layout
------
* ``data``       — typed record schemas + lazy JSONL loaders + panel assembly.
* ``backtest``   — bimodal fill model, portfolio (binary + perp/funding + fees),
                   metrics, and the event-driven engine.
* ``strategies`` — the :class:`Strategy` ABC + Signal/Context/Params contract
                   and a registry; the four concrete strategies plug in here.

Quick start (no real logs needed)
---------------------------------
>>> from crypto_research.data.loader import make_synthetic_panels
>>> from crypto_research.backtest.engine import BacktestEngine, EngineConfig
>>> panels = make_synthetic_panels(200)
>>> # engine = BacktestEngine(panels, [MyStrategy()])
>>> # results = engine.run()
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
