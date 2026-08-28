"""Self-contained smoke test: exercises the whole core on synthetic data.

Run with:  python3 -m crypto_research._smoke_test
No real logs required.  Validates: schema, synthetic panels, fill model,
portfolio (binary + perp/funding + fees), metrics, engine no-look-ahead, and
the Strategy/Signal/registry contract.
"""

from __future__ import annotations

from typing import List

from .backtest.engine import BacktestEngine, EngineConfig
from .backtest.fills import BimodalFillModel
from .backtest.metrics import periods_per_year_for_window, summary
from .backtest.portfolio import Portfolio, default_fee_fn
from .data.loader import make_synthetic_panels
from .strategies.base import (
    Signal,
    Strategy,
    StrategyContext,
    StrategyParams,
    available_strategies,
    build_strategy,
    register_strategy,
)


@register_strategy("smoke_momentum")
class _SmokeMomentum(Strategy):
    """Toy reference strategy: buy YES when late-window mid > 0.55 (momentum)."""

    params_cls = StrategyParams

    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        if ctx.open_shares > 0:
            return []
        if ctx.seconds_to_resolution > 90:
            return []  # only act in the late window
        mid = ctx.mid
        ask = ctx.best_ask
        if mid is None or ask is None:
            return []
        # structural bet: take the YES leg whenever the book leans YES and the
        # expected fill premium clears the edge floor (demonstrates the buy
        # path; this is a toy, not a validated edge).
        exp_fill = ctx.extras["expected_fill_price"]("buy", ask)
        edge = mid - exp_fill
        if mid > 0.50 and edge >= -self.params.edge_min:
            return [Signal(side="BUY_YES", size_fraction=0.5, meta={"mid": mid})]
        return []


def main() -> None:
    print("== crypto_research smoke test ==")

    # 1. synthetic panels
    panels = make_synthetic_panels(300, seed=1, window_size_s=300)
    assert all(p.label_resolved_yes in (0, 1) for p in panels)
    assert all(p.n_steps > 0 for p in panels)
    print(f"panels: {len(panels)} | up rate: "
          f"{sum(p.label_resolved_yes for p in panels) / len(panels):.3f}")

    # 2. fill model reproducibility
    fm1 = BimodalFillModel(seed=42, pi_toxic=0.3, adverse_penalty=0.04)
    fm2 = BimodalFillModel(seed=42, pi_toxic=0.3, adverse_penalty=0.04)
    f1 = fm1.fill("buy", 0.6, 10)
    f2 = fm2.fill("buy", 0.6, 10)
    assert f1.fill_price == f2.fill_price, "fill model not reproducible"
    assert f1.fill_price >= 0.6, "buy fill must be >= touch"
    print(f"fill: touch=0.60 -> {f1.fill_price:.4f} (toxic={f1.toxic}, "
          f"slip={fm1.per_share_slippage:.4f})")

    # 3. portfolio + fee model
    pf = Portfolio(starting_cash=1000.0, fee_fn=default_fee_fn())
    fee_at_half = pf.fee_fn(0.5, 100)  # notional 50 -> 1.8% = 0.9
    assert abs(fee_at_half - 0.9) < 1e-9, f"fee curve wrong: {fee_at_half}"
    print(f"fee(p=0.5, 100sh): ${fee_at_half:.4f} (=1.8% of $50 notional)")

    # 4. perp + funding
    perp = pf.open_perp(asset="BTC", qty=0.01, entry_price=60000.0,
                        entry_ts=0.0, funding_rate=0.0001,
                        funding_interval_s=28800.0)
    charged = pf.accrue_all_funding(28800.0, {"BTC": 60000.0})
    # long pays positive funding: -qty*rate*price = -0.01*0.0001*60000 = -0.06
    assert charged < 0, "long should pay positive funding"
    print(f"funding (1 interval, long $600 notional): ${charged:.4f}")
    pf.close_perp(perp, exit_price=60600.0, exit_ts=28800.0)
    print(f"perp closed; realized_pnl=${pf.realized_pnl:.4f}")

    # 5. metrics annualizer
    ppy5 = periods_per_year_for_window(300)
    ppy15 = periods_per_year_for_window(900)
    print(f"periods/yr: 5m={ppy5:,.0f}  15m={ppy15:,.0f}")
    assert abs(ppy5 - 105120.0) < 1.0
    assert abs(ppy15 - 35040.0) < 1.0

    # 6. registry
    print(f"registered strategies: {available_strategies()}")
    assert "smoke_momentum" in available_strategies()

    # 7. full engine run (no look-ahead enforced internally)
    strat = build_strategy("smoke_momentum", {"edge_min": 0.05, "per_window_budget_frac": 0.2})
    engine = BacktestEngine(
        panels,
        [strat],
        fill_model=BimodalFillModel(seed=7, pi_toxic=0.25, adverse_penalty=0.03),
        portfolio=Portfolio(starting_cash=1000.0),
        config=EngineConfig(starting_cash=1000.0, seed=7),
    )
    results = engine.run()
    m = results["metrics_overall"]
    print("-- engine results --")
    for k in ("n_trades", "win_rate", "profit_factor", "sharpe", "sortino",
              "max_drawdown", "total_net_pnl", "final_equity"):
        print(f"  {k:>16}: {m[k]}")
    assert m["n_trades"] >= 0
    assert len(results["equity_curve"]) > 0
    print("by window size:", {ws: round(d["total_net_pnl"], 2)
                              for ws, d in results["metrics_by_window_size"].items()})

    # 8. no-look-ahead sanity: history is strictly causal
    seen_future = {"bad": False}

    @register_strategy("_audit")
    class _Audit(Strategy):
        def on_step(self, ctx):
            if ctx.history and ctx.history[-1].ts_s > ctx.now_ts + 1e-9:
                seen_future["bad"] = True
            for r in ctx.history:
                if r.ts_s > ctx.now_ts + 1e-9:
                    seen_future["bad"] = True
            return []

    BacktestEngine(panels[:50], [_Audit()]).run()
    assert not seen_future["bad"], "LOOK-AHEAD LEAK detected"
    print("no-look-ahead: OK")

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
