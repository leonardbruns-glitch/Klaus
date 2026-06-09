"""Quick OOS peek: S4 + fixed-S2 on cached BTC held-out test set. Run from /root/Klaus."""
import pickle, time
from crypto_research.backtest.engine import BacktestEngine, EngineConfig
from crypto_research.backtest.fills import BimodalFillModel
from crypto_research.backtest.portfolio import Portfolio, default_fee_fn
from crypto_research.strategies.base import build_strategy
import crypto_research.strategies.s2_hmm_regime  # noqa: F401  register
import crypto_research.strategies.s4_microstructure_statarb  # noqa: F401  register

panels = pickle.load(open('/root/Klaus/data/_era_BTC_300_2026-05-26_2026-05-31.pkl', 'rb'))
panels.sort(key=lambda p: p.window_end_ts)
cut = int(len(panels) * 0.70)
swe = panels[cut].window_end_ts
test = [p for p in panels if p.window_end_ts >= swe]
print(f"BTC OOS test panels={len(test)} (held-out 30%)", flush=True)


def run(name, ps):
    s = build_strategy(name)
    f = BimodalFillModel(seed=7, pi_toxic=0.25, adverse_penalty=0.03)
    pt = Portfolio(starting_cash=1000.0, fee_fn=default_fee_fn(base=0.036))
    return BacktestEngine(list(ps), [s], fill_model=f, portfolio=pt,
                          config=EngineConfig(starting_cash=1000.0, seed=7)).run()["metrics_overall"]


def fmt(m):
    return (f"n={m.get('n_trades',0):<5} WR={m.get('win_rate',0):.3f} "
            f"PF={m.get('profit_factor',0):.3f} Sharpe={m.get('sharpe',0):.2f} "
            f"MDD={m.get('max_drawdown',0):.3f} PnL={m.get('total_net_pnl',0):+.1f}")


for name in ["microstructure_statarb", "s2_hmm_regime"]:
    t0 = time.time()
    m = run(name, test)
    print(f"{name:24} OOS: {fmt(m)}   ({time.time()-t0:.0f}s)", flush=True)
print("DONE", flush=True)
