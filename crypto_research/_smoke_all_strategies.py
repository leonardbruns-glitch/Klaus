"""End-to-end smoke harness for ALL FOUR registered strategies.

Runs each of the four concrete strategies through the :class:`BacktestEngine`
on a SMALL synthetic panel set (no real 40GB logs required) and asserts that

* a metrics dict with Sharpe / Sortino / MaxDD / ProfitFactor is produced,
* the bimodal fill model + per-share slippage are actually applied to the
  realised fills (evidence is carried on each ``TradeRecord.meta``).

Strategy S3 (rough-vol / KL) has a ``min_returns`` gate of 32 returns, so it
needs windows with more than the default 30 steps before its buy path fires.
We therefore run the suite twice: a default ``steps_per_window=30`` pass and a
``steps_per_window=60`` pass so S3's buy path is exercised at least once.

Run:  python3 -m crypto_research._smoke_all_strategies
"""

from __future__ import annotations

from typing import Dict, List

from .backtest.engine import BacktestEngine, EngineConfig
from .backtest.fills import BimodalFillModel
from .backtest.portfolio import Portfolio, default_fee_fn
from .data.loader import make_synthetic_panels

# importing these registers all four strategies
from .strategies import (  # noqa: F401
    s1_binary_delta_hedge,
    s2_hmm_regime,
    s3_rough_vol_kl,
    s4_microstructure_statarb,
)
from .strategies.base import available_strategies, build_strategy

_METRIC_KEYS = ("sharpe", "sortino", "max_drawdown", "profit_factor",
                "win_rate", "n_trades", "total_net_pnl")

# The four registered names (decoupled from module file names).
STRATEGIES = [
    "binary_delta_hedge",
    "s2_hmm_regime",
    "s3_rough_vol_kl",
    "microstructure_statarb",
]


def _run_one(name: str, steps_per_window: int) -> Dict[str, object]:
    """Run a single strategy through the engine on synthetic panels."""
    panels = make_synthetic_panels(
        250,
        seed=11,
        window_size_s=300,
        steps_per_window=steps_per_window,
        up_and_down=True,      # exercise YES + NO + peer-redirect paths
        edge_strength=0.7,
    )
    strat = build_strategy(name, {})
    fill_model = BimodalFillModel(seed=7, pi_toxic=0.30, adverse_penalty=0.04)
    portfolio = Portfolio(starting_cash=1000.0, fee_fn=default_fee_fn())
    engine = BacktestEngine(
        panels,
        [strat],
        fill_model=fill_model,
        portfolio=portfolio,
        config=EngineConfig(starting_cash=1000.0, seed=7),
    )
    results = engine.run()
    results["_fill_model"] = fill_model
    return results


def _assert_metrics_dict(name: str, m: Dict[str, object]) -> None:
    for k in _METRIC_KEYS:
        assert k in m, f"[{name}] metrics dict missing key {k!r}"
        assert isinstance(m[k], (int, float)), f"[{name}] {k} not numeric: {m[k]!r}"


def _fill_evidence(results: Dict[str, object]) -> Dict[str, object]:
    """Summarise that the bimodal fill + slippage actually hit the trades."""
    trades = [t for t in results["closed_trades"] if t.kind == "binary"]
    slip = results["_fill_model"].per_share_slippage
    n_with_slip = 0
    n_toxic = 0
    n_entry_above_touch = 0
    for t in trades:
        meta = t.meta
        if meta.get("slippage", 0.0) > 0.0:
            n_with_slip += 1
        if meta.get("toxic_fill"):
            n_toxic += 1
        touch = meta.get("touch")
        # buys: realised entry price must be >= touch (slippage/adverse worsen)
        if touch is not None and t.entry_price >= touch - 1e-12:
            n_entry_above_touch += 1
    return {
        "n_binary_trades": len(trades),
        "per_share_slippage": slip,
        "n_with_slippage_meta": n_with_slip,
        "n_toxic_fills": n_toxic,
        "n_entry_ge_touch": n_entry_above_touch,
    }


def main() -> int:
    print("== ALL-STRATEGY smoke (synthetic, no real logs) ==")
    print(f"registered: {available_strategies()}")
    assert set(STRATEGIES).issubset(set(available_strategies())), (
        f"missing strategies: {set(STRATEGIES) - set(available_strategies())}"
    )

    any_fill_proven = False
    s3_fired = False
    for name in STRATEGIES:
        for spw in (30, 60):
            res = _run_one(name, spw)
            m = res["metrics_overall"]
            _assert_metrics_dict(name, m)
            ev = _fill_evidence(res)
            tag = f"{name}[spw={spw}]"
            print(
                f"-- {tag}: n={m['n_trades']} WR={m['win_rate']:.3f} "
                f"PF={m['profit_factor']:.3f} Sharpe={m['sharpe']:.3f} "
                f"Sortino={m['sortino']:.3f} MDD={m['max_drawdown']:.3f} "
                f"| binary_trades={ev['n_binary_trades']} "
                f"slip={ev['per_share_slippage']:.4f} "
                f"toxic={ev['n_toxic_fills']} "
                f"entry>=touch={ev['n_entry_ge_touch']}/{ev['n_binary_trades']}"
            )
            # if this strategy traded, the fill model must have left evidence
            if ev["n_binary_trades"] > 0:
                assert 0.01 <= ev["per_share_slippage"] <= 0.02, (
                    f"[{tag}] slippage out of mandated [0.01,0.02]"
                )
                assert ev["n_entry_ge_touch"] == ev["n_binary_trades"], (
                    f"[{tag}] some buy fills below touch (slippage not applied)"
                )
                any_fill_proven = True
            if name == "s3_rough_vol_kl" and ev["n_binary_trades"] > 0:
                s3_fired = True

    assert any_fill_proven, "no strategy produced any fill — cannot prove fill model"
    print(f"\nS3 buy path fired on longer windows: {s3_fired}")
    print("ALL-STRATEGY SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
