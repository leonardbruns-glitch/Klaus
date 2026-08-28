"""Build the real Tier-1 era ONCE, cache it, run all 4 strategies + OOS split.

Run:  nice -n 19 python3 -m crypto_research._run_era
Honest read on the real 2026-05-26..06-05 5-min era. Synthetic numbers are
plumbing; THESE are the numbers that matter (still thin: 11 days).
"""
from __future__ import annotations

import gc
import os
import pickle
import sys
import time
from typing import Dict, List, Sequence

from .data.loader import build_window_panels
from .data.schema import WindowPanel
from .backtest.engine import BacktestEngine, EngineConfig
from .backtest.fills import BimodalFillModel
from .backtest.portfolio import Portfolio, default_fee_fn
from .strategies.base import build_strategy
# Import the strategy modules so their @register_strategy decorators run
# (without this the registry is empty -> 'unknown strategy' KeyError).
from .strategies import (  # noqa: F401
    s1_binary_delta_hedge,
    s2_hmm_regime,
    s3_rough_vol_kl,
    s4_microstructure_statarb,
)

ASSETS = ["BTC", "ETH", "SOL"]
WINDOW = 300
# 6 days keeps all-asset 5m panels in RAM on this 8GB box (11 days OOM'd) while
# still giving ~1,700 windows/asset -- well past the n>=100 mandate. Override via
# ERA_START/ERA_END env vars.
START = os.environ.get("ERA_START", "2026-05-26")
END = os.environ.get("ERA_END", "2026-05-31")
STRATS = [
    # fast three first so they stream; S2 (slow HMM fit) runs last
    "binary_delta_hedge",
    "s3_rough_vol_kl",
    "microstructure_statarb",
    "s2_hmm_regime",
]
CASH = 1000.0
SEED = 7


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _free_gib() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except Exception:  # noqa: BLE001
        pass
    return -1.0


def build_or_load() -> List[WindowPanel]:
    log(f"building panels real {WINDOW}s {ASSETS} {START}..{END} (one parse); "
        f"mem_avail={_free_gib():.1f}GiB")
    t0 = time.time()
    panels = build_window_panels(
        assets=ASSETS,
        window_size_s=WINDOW,
        date_range=(START, END),
        min_steps=2,
    )
    log(f"built {len(panels)} panels in {time.time()-t0:.0f}s; "
        f"mem_avail={_free_gib():.1f}GiB (no pickle, in-memory only)")
    return panels


def run(strat_name: str, panels: Sequence[WindowPanel]) -> Dict[str, float]:
    strat = build_strategy(strat_name)
    fill = BimodalFillModel(seed=SEED, pi_toxic=0.25, adverse_penalty=0.03)
    port = Portfolio(starting_cash=CASH, fee_fn=default_fee_fn(base=0.036))
    eng = BacktestEngine(
        list(panels), [strat], fill_model=fill, portfolio=port,
        config=EngineConfig(starting_cash=CASH, seed=SEED),
    )
    res = eng.run()
    return res["metrics_overall"]


def fmt(m: Dict[str, float]) -> str:
    return (
        f"n={m.get('n_trades',0):<5} WR={m.get('win_rate',0):.3f} "
        f"PF={m.get('profit_factor',0):.3f} Sharpe={m.get('sharpe',0):.2f} "
        f"Sortino={m.get('sortino',0):.2f} MDD={m.get('max_drawdown',0):.3f} "
        f"PnL={m.get('total_net_pnl',0):+.2f}"
    )


def build_one(asset: str) -> List[WindowPanel]:
    """Build panels for a SINGLE asset (memory-frugal: ~2GB vs ~6GB all-asset).

    Per-asset pickle cache so a re-run (e.g. after a code fix) loads instantly
    instead of re-paying the ~4-min/asset parse.
    """
    cache = f"/root/Klaus/data/_era_{asset}_{WINDOW}_{START}_{END}.pkl"
    if os.path.exists(cache):
        log(f"loading cached {asset} panels from {cache}")
        with open(cache, "rb") as f:
            panels = pickle.load(f)
        log(f"  loaded {len(panels)} {asset} panels; mem_avail={_free_gib():.1f}GiB")
        return panels
    log(f"building {asset} {WINDOW}s {START}..{END}; mem_avail={_free_gib():.1f}GiB")
    t0 = time.time()
    panels = build_window_panels(
        assets=[asset], window_size_s=WINDOW, date_range=(START, END), min_steps=2,
    )
    log(f"  built {len(panels)} {asset} panels in {time.time()-t0:.0f}s; "
        f"mem_avail={_free_gib():.1f}GiB")
    try:
        with open(cache, "wb") as f:
            pickle.dump(panels, f, protocol=pickle.HIGHEST_PROTOCOL)
        log(f"  cached {asset} -> {cache}")
    except Exception as e:  # noqa: BLE001
        log(f"  cache write failed (continuing): {e}")
    return panels


def main() -> int:
    print(f"\n========== REAL ERA RESULTS (5-min, {START}..{END}) ==========")
    print("Per-asset; TEST(30%) is the time-ordered OOS holdout = the honest number.\n")
    for a in ASSETS:
        panels = build_one(a)
        if not panels:
            print(f"### {a}: NO PANELS ###")
            continue
        ordered = sorted(panels, key=lambda p: p.window_end_ts)
        cut = int(len(ordered) * 0.70)
        split_we = ordered[cut].window_end_ts
        train = [p for p in ordered if p.window_end_ts < split_we]
        test = [p for p in ordered if p.window_end_ts >= split_we]
        print(f"\n### {a}  (panels={len(panels)}, train={len(train)}, test={len(test)}) ###")
        for s in STRATS:
            try:
                mf = run(s, panels)
                mte = run(s, test)
                print(f"  {s:24} FULL: {fmt(mf)}")
                print(f"  {'':24} OOS : {fmt(mte)}")
            except Exception as e:  # noqa: BLE001
                print(f"  {s:24} ERROR {type(e).__name__}: {e}")
            gc.collect()
        del panels, ordered, train, test
        gc.collect()
        log(f"  freed {a}; mem_avail={_free_gib():.1f}GiB")
    print("\n=============================================================================")
    print("Reminder: ~50-50 base rate; n<100 = trend-only. Costs = fees+slip+toxic ~3c/sh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
