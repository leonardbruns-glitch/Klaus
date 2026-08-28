"""Naive baseline: buy YES near each window's open, hold to resolution.

Reference floor only — measures the coinflip base rate minus fees/fills.  Not a
strategy; it exists so RIPA et al. are judged against the cost of doing nothing
clever.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .base import Signal, Strategy, StrategyContext, StrategyParams, register_strategy


@dataclass
class NaiveYesParams(StrategyParams):
    min_secs_left: float = 30.0
    max_secs_left: float = 285.0
    max_position_frac: float = 0.05
    per_window_budget_frac: float = 0.10


@register_strategy("naive_yes")
class NaiveYesStrategy(Strategy):
    params_cls = NaiveYesParams

    def __init__(self, params: Optional[NaiveYesParams] = None) -> None:
        super().__init__(params)
        self.params: NaiveYesParams
        self._acted: set = set()

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        if (ctx.outcome_dir or "").lower() != "up" or ctx.open_shares > 0:
            return []
        sl = ctx.seconds_to_resolution
        if sl is None or sl < p.min_secs_left or sl > p.max_secs_left:
            return []
        key = (ctx.token_id, ctx.window_end_ts)
        if key in self._acted:
            return []
        ask = ctx.best_ask
        if ask is None or not (0 < ask < 1):
            return []
        self._acted.add(key)
        return [Signal(side="BUY_YES", size_fraction=0.5,
                       price_limit=min(1.0, ask + 0.02), meta={"note": "naive_yes"})]

    def on_window_close(self, panel, resolved_yes_for_token: int) -> None:
        self._acted.discard((panel.token_id, int(panel.window_end_ts)))


__all__ = ["NaiveYesParams", "NaiveYesStrategy"]
