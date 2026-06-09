"""IM + onchain_sweep (+ naive ref) on BTC, single panel load.
Usage: python3 -m crypto_research._run_im START END
"""
from __future__ import annotations

import sys

import crypto_research.run_research  # noqa: F401
from crypto_research.backtest.engine import BacktestEngine, EngineConfig
from crypto_research.backtest.fills import BimodalFillModel
from crypto_research.backtest.portfolio import Portfolio, default_fee_fn
from crypto_research.data.loader import build_window_panels
from crypto_research.strategies.base import build_strategy

START, END = sys.argv[1], sys.argv[2]
STRATS = ["im_mispricing", "onchain_sweep", "naive_yes"]

panels = build_window_panels(
    assets=["BTC"], window_size_s=300, date_range=(START, END), min_steps=3,
)
print(f"panels={len(panels)} range={START}..{END}", flush=True)

for name in STRATS:
    strat = build_strategy(name, None)
    fill_model = BimodalFillModel(seed=7, pi_toxic=0.25, adverse_penalty=0.03)
    portfolio = Portfolio(starting_cash=1000.0, fee_fn=default_fee_fn(base=0.036))
    engine = BacktestEngine(
        list(panels), [strat], fill_model=fill_model, portfolio=portfolio,
        config=EngineConfig(starting_cash=1000.0, seed=7,
                            allow_short_window_entries=True),
    )
    o = engine.run()["metrics_overall"]
    print(f"\n=== {name} ===", flush=True)
    print(f"  n={o['n_trades']}  WR={o['win_rate']:.3f}  PF={o['profit_factor']:.3f}  "
          f"Sharpe={o['sharpe']:.3f}  Sortino={o['sortino']:.3f}  "
          f"avg={o['mean_trade_pnl']:.4f}  PnL={o['total_net_pnl']:.2f}  "
          f"ret={o['total_return']*100:.2f}%  maxDD={o['max_drawdown']*100:.1f}%", flush=True)
