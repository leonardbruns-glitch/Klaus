"""Event-driven backtest engine: time-ordered, no look-ahead, fee/fill/funding.

The engine merges all :class:`WindowPanel` timelines into one global
time-ordered event stream of ``(ts_s, panel, step_index)`` tuples.  At each
event it builds a strictly-causal :class:`StrategyContext` (history ``<= t``),
asks every strategy for :class:`Signal` s, and routes each signal through the
:class:`BimodalFillModel` into the :class:`Portfolio`.  When a window's last
observed step is reached, the window is **settled** to its resolution label.

No look-ahead guarantees
------------------------
* A context's ``history`` is the panel timeline sliced to ``ts_s <= t`` via a
  binary search; ``row`` is the step at ``t``.
* The resolution label / settlement OHLC are never placed in the context.
* New legs may only open while ``seconds_to_resolution >=
  params.min_seconds_to_resolution``; settlement happens strictly after the
  last observed step of a window.

Cadence (NON-HFT)
-----------------
Events are the ``market_timeline`` rows — bar cadence, not ticks.  Equity is
marked once per event so :mod:`metrics` annualizes on bar returns.

Funding
-------
At each event the engine accrues perp funding on open hedge legs using the
asset's latest ``binance_spot`` as the mark, then marks equity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.schema import MarketTimelineRow, WindowKey, WindowPanel
from ..strategies.base import Signal, Strategy, StrategyContext
from .fills import BimodalFillModel
from .metrics import summary
from .portfolio import BinaryPosition, Portfolio


@dataclass
class EngineConfig:
    """Backtest engine configuration.

    Attributes
    ----------
    starting_cash
        Initial bankroll.
    seed
        Master RNG seed (drives the fill model unless one is injected).
    mark_each_step
        Mark equity at every event (recommended; needed for Sharpe).
    settle_at_last_step
        Settle a window at its last observed timeline step (vs. exactly at
        ``window_end_ts``).  Default ``True`` — labels are known at the last
        observed row's window.
    allow_short_window_entries
        If ``False``, reject new opens once ``seconds_to_resolution`` falls
        below each strategy's ``min_seconds_to_resolution``.
    """

    starting_cash: float = 1000.0
    seed: int = 2024
    mark_each_step: bool = True
    settle_at_last_step: bool = True
    allow_short_window_entries: bool = True


@dataclass
class _Event:
    """One scheduled step in the global timeline."""

    ts: float
    panel_idx: int
    step_idx: int
    is_last_step: bool


class BacktestEngine:
    """Drives strategies over :class:`WindowPanel` s with full execution model.

    Parameters
    ----------
    panels
        The token-windows to replay (will be processed in global time order).
    strategies
        One or more :class:`Strategy` instances.  Each gets its own context
        per step; their signals are routed independently, and positions are
        tagged with the strategy name in ``meta['strategy']``.
    fill_model
        :class:`BimodalFillModel`.  If ``None``, one is built from
        ``config.seed``.
    portfolio
        :class:`Portfolio`.  If ``None``, one is built from
        ``config.starting_cash``.
    config
        :class:`EngineConfig`.
    """

    def __init__(
        self,
        panels: Sequence[WindowPanel],
        strategies: Sequence[Strategy],
        *,
        fill_model: Optional[BimodalFillModel] = None,
        portfolio: Optional[Portfolio] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.panels: List[WindowPanel] = [p for p in panels if p.n_steps > 0]
        self.strategies: List[Strategy] = list(strategies)
        self.fill_model = fill_model or BimodalFillModel(seed=self.config.seed)
        self.portfolio = portfolio or Portfolio(starting_cash=self.config.starting_cash)

        # peer lookup: (asset, window_end_ts) -> {outcome_side: panel_idx}
        self._peer_index: Dict[Tuple[str, int], Dict[str, int]] = {}
        # token_id -> panel (O(1) settlement of peer-redirected legs)
        self._token_panel: Dict[str, WindowPanel] = {}
        # window key -> list of panel indices sharing that (asset, window_end_ts, ws)
        self._key_panels: Dict[WindowKey, List[int]] = {}
        for i, p in enumerate(self.panels):
            key = (p.asset, int(p.window_end_ts))
            self._peer_index.setdefault(key, {})[
                (p.outcome_side or ("YES" if p.is_up_token else "NO")).upper()
            ] = i
            self._token_panel[p.token_id] = p
            self._key_panels.setdefault(p.key, []).append(i)
        # count of remaining (unfinished) panels per window key, to settle once
        self._key_pending: Dict[WindowKey, int] = {
            k: len(v) for k, v in self._key_panels.items()
        }

        # latest spot per asset (for funding marks)
        self._last_spot: Dict[str, float] = {}
        # which panels are already settled
        self._settled: set = set()
        # per-strategy open positions per token: name -> token_id -> [pos]
        self._open: Dict[str, Dict[str, List[BinaryPosition]]] = {
            s.name: {} for s in self.strategies
        }

    # ------------------------------------------------------------------
    def _build_events(self) -> List[_Event]:
        """Flatten all panel steps into one global, time-sorted event list."""
        events: List[_Event] = []
        for pi, panel in enumerate(self.panels):
            n = panel.n_steps
            for si, row in enumerate(panel.timeline):
                events.append(
                    _Event(
                        ts=row.ts_s,
                        panel_idx=pi,
                        step_idx=si,
                        is_last_step=(si == n - 1),
                    )
                )
        # Stable sort by time; ties keep panel/step order (deterministic).
        events.sort(key=lambda e: (e.ts, e.panel_idx, e.step_idx))
        return events

    def _peer_snapshot(
        self, panel: WindowPanel, ts: float
    ) -> Optional[dict]:
        """Latest book of the opposite token at time ``ts`` (causal)."""
        key = (panel.asset, int(panel.window_end_ts))
        sides = self._peer_index.get(key)
        if not sides:
            return None
        my_side = (panel.outcome_side or ("YES" if panel.is_up_token else "NO")).upper()
        peer_side = "NO" if my_side == "YES" else "YES"
        pidx = sides.get(peer_side)
        if pidx is None:
            return None
        peer_panel = self.panels[pidx]
        idx = peer_panel.asof_index(ts)
        if idx < 0:
            return None
        prow = peer_panel.timeline[idx]
        return {
            "token_id": peer_panel.token_id,
            "best_bid": prow.best_bid,
            "best_ask": prow.best_ask,
            "mid": prow.mid,
        }

    def _make_context(
        self,
        strat: Strategy,
        panel: WindowPanel,
        step_idx: int,
        ts: float,
    ) -> StrategyContext:
        """Construct a causal context for ``strat`` at this step."""
        row = panel.timeline[step_idx]
        history = panel.timeline[: step_idx + 1]  # data <= t
        my_open = self._open[strat.name].get(panel.token_id, [])
        open_shares = sum(p.shares for p in my_open)
        s2r = (
            row.seconds_to_resolution
            if row.seconds_to_resolution is not None
            else float(panel.window_end_ts) - ts
        )
        return StrategyContext(
            now_ts=ts,
            row=row,
            history=history,
            token_id=panel.token_id,
            asset=panel.asset,
            window_end_ts=int(panel.window_end_ts),
            window_size_s=int(panel.window_size_s),
            outcome_dir=panel.outcome_dir,
            outcome_side=panel.outcome_side,
            seconds_to_resolution=float(s2r),
            bankroll=self.portfolio.equity(),
            cash=self.portfolio.cash,
            open_shares=open_shares,
            open_positions=tuple(my_open),
            peer=self._peer_snapshot(panel, ts),
            extras={
                "expected_fill_price": self.fill_model.expected_fill_price,
                "per_share_slippage": self.fill_model.per_share_slippage,
                "fee_fn": self.portfolio.fee_fn,
                "last_spot": dict(self._last_spot),
            },
        )

    # ------------------------------------------------------------------
    def _route_signal(
        self,
        strat: Strategy,
        sig: Signal,
        ctx: StrategyContext,
        panel: WindowPanel,
    ) -> None:
        """Convert a signal into a fill + portfolio mutation (no look-ahead)."""
        if sig.side == "FLAT":
            self._flatten(strat, ctx, panel)
            return
        if sig.side == "HEDGE":
            self._open_hedge(strat, sig, ctx)
            return

        # binary buy (YES or NO token)
        if not self.config.allow_short_window_entries:
            if ctx.seconds_to_resolution < strat.params.min_seconds_to_resolution:
                return

        target_token = sig.token_id
        target_panel = panel
        if sig.side == "BUY_NO" and (panel.outcome_side or "YES").upper() == "YES":
            # acting on the peer NO token while iterating the YES panel
            peer = self._peer_snapshot(panel, ctx.now_ts)
            if peer is None:
                return
            target_token = peer["token_id"]
            target_panel = self._panel_for_token(target_token) or panel
            touch = peer["best_ask"]
        elif sig.side == "BUY_YES" and (panel.outcome_side or "YES").upper() == "NO":
            peer = self._peer_snapshot(panel, ctx.now_ts)
            if peer is None:
                return
            target_token = peer["token_id"]
            target_panel = self._panel_for_token(target_token) or panel
            touch = peer["best_ask"]
        else:
            target_token = target_token or panel.token_id
            touch = ctx.best_ask

        if touch is None or touch <= 0 or touch >= 1:
            return

        # size: fraction of per-window budget (bankroll * per_window_budget_frac)
        frac = min(sig.size_fraction, strat.params.max_position_frac)
        budget = ctx.bankroll * strat.params.per_window_budget_frac
        deploy_usd = min(budget * frac, ctx.cash)
        if deploy_usd <= 0:
            return

        # Limit semantics: the price_limit guards against the QUOTE itself being
        # beyond our tolerance — it is checked against the BENIGN price
        # (touch + benign per-share slippage), NOT the toxic draw. Adverse
        # selection is then ALWAYS realized once we trade: that is the entire
        # point of a bimodal fill model, so a toxic draw is booked into PnL
        # rather than silently rejected (which would erase the toxic cost the
        # user mandate requires us to factor in).
        benign_price = float(touch) + self.fill_model.per_share_slippage
        if sig.price_limit is not None and benign_price > sig.price_limit:
            return
        fill = self.fill_model.fill("buy", float(touch), deploy_usd / max(touch, 1e-6))
        if fill.fill_price <= 0 or fill.fill_price >= 1:
            return
        shares = deploy_usd / fill.fill_price
        meta = dict(sig.meta)
        meta.update(
            {
                "strategy": strat.name,
                "toxic_fill": fill.toxic,
                "touch": float(touch),
                "slippage": fill.slippage_applied,
                "adverse": fill.adverse_applied,
            }
        )
        pos = self.portfolio.open_binary(
            token_id=target_token,
            asset=target_panel.asset,
            window_end_ts=int(target_panel.window_end_ts),
            window_size_s=int(target_panel.window_size_s),
            shares=shares,
            fill_price=fill.fill_price,
            entry_ts=ctx.now_ts,
            outcome_dir=target_panel.outcome_dir,
            meta=meta,
        )
        if pos is not None:
            self._open[strat.name].setdefault(target_token, []).append(pos)

    def _open_hedge(self, strat: Strategy, sig: Signal, ctx: StrategyContext) -> None:
        """Open a perp-swap hedge leg from a HEDGE signal's meta."""
        m = sig.meta
        asset = m.get("asset", ctx.asset)
        qty = float(m.get("qty", 0.0))
        if qty == 0.0:
            return
        entry_price = float(
            m.get("entry_price", ctx.row.binance_spot or self._last_spot.get(asset, 0.0))
        )
        if entry_price <= 0:
            return
        self.portfolio.open_perp(
            asset=asset,
            qty=qty,
            entry_price=entry_price,
            entry_ts=ctx.now_ts,
            funding_rate=float(m.get("funding_rate", 0.0)),
            funding_interval_s=float(m.get("funding_interval_s", 28800.0)),
            meta={"strategy": strat.name, **m},
        )

    def _flatten(self, strat: Strategy, ctx: StrategyContext, panel: WindowPanel) -> None:
        """Early-exit this strategy's open legs in the current token at the bid."""
        my_open = list(self._open[strat.name].get(ctx.token_id, []))
        bid = ctx.best_bid
        if bid is None or bid <= 0:
            return
        for pos in my_open:
            fill = self.fill_model.fill("sell", float(bid), pos.shares)
            self.portfolio.close_binary_at_price(
                pos, fill_price=fill.fill_price, exit_ts=ctx.now_ts
            )
        self._open[strat.name][ctx.token_id] = []

    def _panel_for_token(self, token_id: str) -> Optional[WindowPanel]:
        return self._token_panel.get(token_id)

    # ------------------------------------------------------------------
    def _on_panel_finished(self, panel: WindowPanel, ts: float) -> None:
        """Decrement the window-key pending count; settle when all done.

        A window may carry two panels (UP + DOWN token).  We settle the whole
        window key only once *every* panel sharing the key has reached its last
        observed step, so a peer-redirected leg opened on the sibling panel is
        never orphaned.
        """
        key = panel.key
        if key in self._settled:
            return
        self._key_pending[key] = self._key_pending.get(key, 1) - 1
        if self._key_pending[key] <= 0:
            self._settle_key(key, ts)

    def _settle_key(self, key: WindowKey, ts: float) -> None:
        """Settle ALL open legs whose own token belongs to this window key.

        Each position is settled against the label of *its own* token's panel
        (looked up by token_id), so YES and NO legs resolve to the right
        outcome regardless of which panel they were routed from.
        """
        if key in self._settled:
            return
        self._settled.add(key)
        panels = [self.panels[i] for i in self._key_panels.get(key, [])]
        key_tokens = {p.token_id for p in panels}
        for strat in self.strategies:
            book = self._open[strat.name]
            for token_id in list(book.keys()):
                if token_id not in key_tokens:
                    continue
                tok_panel = self._token_panel.get(token_id)
                label = tok_panel.label_resolved_yes if tok_panel else None
                for pos in list(book[token_id]):
                    if label is not None:
                        self.portfolio.settle_binary(
                            pos, resolved_yes_for_token=int(label), exit_ts=ts
                        )
                    else:
                        last_bid = (
                            tok_panel.timeline[-1].best_bid
                            if tok_panel and tok_panel.timeline
                            else 0.0
                        ) or 0.0
                        f = self.fill_model.fill("sell", float(last_bid), pos.shares)
                        self.portfolio.close_binary_at_price(
                            pos, fill_price=f.fill_price, exit_ts=ts
                        )
                book[token_id] = []
        # Close any perp HEDGE legs belonging to this window. A delta hedge is
        # held only THROUGH its window and unwound at resolution; leaving perps
        # open would let their mark-to-market accumulate across the whole run
        # (the S1 equity-feedback blowup). Match on the window_end_ts carried in
        # the hedge meta.
        settle_we = {int(p.window_end_ts) for p in panels}
        for pos in list(self.portfolio.perp_positions):
            if int(pos.meta.get("window_end_ts", -1)) in settle_we:
                mark = float(self._last_spot.get(pos.asset, pos.entry_price))
                self.portfolio.close_perp(pos, exit_price=mark, exit_ts=ts)
        # per-strategy post-settlement hook (once per panel with a known label)
        for p in panels:
            if p.label_resolved_yes is not None:
                for strat in self.strategies:
                    strat.on_window_close(p, int(p.label_resolved_yes))

    # ------------------------------------------------------------------
    def run(self) -> Dict[str, object]:
        """Execute the backtest and return a results dict.

        Returns
        -------
        dict
            ``{'portfolio', 'metrics_overall', 'metrics_by_window_size',
            'closed_trades', 'equity_curve', 'equity_ts'}``.
        """
        # warmup (may see whole panels; must not leak per-window labels live)
        for strat in self.strategies:
            strat.warmup(self.panels)

        events = self._build_events()
        for ev in events:
            panel = self.panels[ev.panel_idx]
            row = panel.timeline[ev.step_idx]
            ts = ev.ts

            # update spot mark for funding
            if row.binance_spot is not None:
                self._last_spot[panel.asset] = float(row.binance_spot)

            # accrue funding on open perp legs
            self.portfolio.accrue_all_funding(ts, self._last_spot)

            # ask each strategy and route
            for strat in self.strategies:
                if not strat.params.enabled:
                    continue
                ctx = self._make_context(strat, panel, ev.step_idx, ts)
                signals = strat.on_step(ctx)
                if not signals:
                    continue
                for sig in signals:
                    self._route_signal(strat, sig, ctx, panel)

            # mark equity BEFORE settlement collapses the open leg to cash, so
            # the bar return reflects the mark-to-bid path (no settlement jump
            # double-counted). Settlement then realises the leg.
            if self.config.mark_each_step:
                binary_marks = self._binary_marks_at(ts)
                self.portfolio.mark(
                    ts, binary_marks=binary_marks, perp_marks=self._last_spot
                )

            # mark the panel finished after its last observed step; the window
            # key settles once all its panels (UP + DOWN) are done.
            if ev.is_last_step and self.config.settle_at_last_step:
                self._on_panel_finished(panel, ts)

        # settle any straggler windows (e.g. settle_at_last_step disabled)
        for key in list(self._key_panels.keys()):
            if key not in self._settled:
                panels = [self.panels[i] for i in self._key_panels[key]]
                last_ts = max(p.timeline[-1].ts_s for p in panels)
                self._settle_key(key, last_ts)

        return self._results()

    def _binary_marks_at(self, ts: float) -> Dict[str, float]:
        """Best-effort current bid mark per open binary token (causal)."""
        marks: Dict[str, float] = {}
        for strat in self.strategies:
            for token_id, plist in self._open[strat.name].items():
                if not plist:
                    continue
                panel = self._panel_for_token(token_id)
                if panel is None:
                    continue
                idx = panel.asof_index(ts)
                if idx >= 0 and panel.timeline[idx].best_bid is not None:
                    marks[token_id] = float(panel.timeline[idx].best_bid)
        return marks

    def _results(self) -> Dict[str, object]:
        """Assemble the final metrics / artifacts dict."""
        trades = self.portfolio.closed_trades
        eq = self.portfolio.equity_curve
        # split metrics by window size for the 5m/15m annualizer
        by_ws: Dict[int, dict] = {}
        for ws in sorted({p.window_size_s for p in self.panels}):
            ws_trades = [
                t
                for t in trades
                if t.meta.get("window_size_s", ws) == ws
                or self._trade_ws(t) == ws
            ]
            by_ws[ws] = summary(
                eq,
                ws_trades,
                window_size_s=ws,
                starting_cash=self.config.starting_cash,
            )
        overall_ws = self.panels[0].window_size_s if self.panels else 300
        return {
            "portfolio": self.portfolio,
            "metrics_overall": summary(
                eq,
                trades,
                window_size_s=overall_ws,
                starting_cash=self.config.starting_cash,
            ),
            "metrics_by_window_size": by_ws,
            "closed_trades": trades,
            "equity_curve": eq,
            "equity_ts": self.portfolio.equity_ts,
        }

    @staticmethod
    def _trade_ws(trade) -> Optional[int]:
        return trade.meta.get("window_size_s")


__all__ = ["BacktestEngine", "EngineConfig"]
