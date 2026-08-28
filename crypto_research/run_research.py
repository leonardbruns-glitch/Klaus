"""CLI entrypoint for the crypto_research backtest framework.

Builds :class:`~crypto_research.data.schema.WindowPanel` s (from the real Tier-1
logs OR from synthetic data), runs one of the four registered strategies through
the :class:`~crypto_research.backtest.engine.BacktestEngine`, and prints the
metrics summary.  Optionally runs a parameter search (grid / random /
walk-forward) via :mod:`crypto_research.optimize.search`.

Importing this module registers all four strategies (so ``--strategy`` accepts
them by name) without the caller having to know their module paths.

Examples
--------
Single backtest on synthetic data (no real logs needed)::

    python3 -m crypto_research.run_research --synthetic --n 400 \
        --strategy s3_rough_vol_kl

Single backtest on the real Tier-1 feature era (BTC 5-min, 2026-05-26..06-05)::

    python3 -m crypto_research.run_research --real \
        --assets BTC --window 300 --start 2026-05-26 --end 2026-06-05 \
        --strategy microstructure_statarb --param theta_entry=0.06

Walk-forward parameter search on synthetic data::

    python3 -m crypto_research.run_research --synthetic --n 600 \
        --strategy binary_delta_hedge --search walk_forward \
        --grid vrp_edge_min=0.01,0.02,0.04 --grid binary_edge_min=0.02,0.03

List the registered strategies::

    python3 -m crypto_research.run_research --list
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

# Importing these modules registers the four strategies in the registry.
from .strategies import (  # noqa: F401  (side-effect imports populate registry)
    s1_binary_delta_hedge,
    s2_hmm_regime,
    s3_rough_vol_kl,
    s4_microstructure_statarb,
    m5_markov_regime_gate,
    m6_markov_mid_revert,
    m7_markov_flow_follow,
    m8_markov_mdp_stop,
    m9_ripa,
    m0_naive_yes,
    m10_im_mispricing,
    m11_onchain_sweep,
    m12_mhd,
    m13_emr,
)
from .strategies.base import available_strategies, build_strategy
from .backtest.engine import BacktestEngine, EngineConfig
from .backtest.fills import BimodalFillModel
from .backtest.portfolio import Portfolio, default_fee_fn
from .data.loader import attach_binance_ticks, build_window_panels, make_synthetic_panels
from .data.schema import WindowPanel
from .optimize.search import (
    SearchConfig,
    grid_search,
    print_report,
    random_search,
    train_test_search,
    walk_forward,
)

_METRIC_KEYS = (
    "n_trades",
    "win_rate",
    "profit_factor",
    "sharpe",
    "sortino",
    "max_drawdown",
    "max_drawdown_usd",
    "total_net_pnl",
    "mean_trade_pnl",
    "final_equity",
    "total_return",
    "periods_per_year",
)


# ---------------------------------------------------------------------------
# Param / grid parsing
# ---------------------------------------------------------------------------
def _coerce(value: str) -> Any:
    """Coerce a CLI string to int/float/bool/str (best effort)."""
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("none", "null"):
        return None
    try:
        iv = int(value)
        return iv
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_params(items: Optional[Sequence[str]]) -> Dict[str, Any]:
    """Parse ``--param name=value`` items into a typed dict."""
    out: Dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--param must be name=value, got {item!r}")
        name, _, val = item.partition("=")
        out[name.strip()] = _coerce(val)
    return out


def _parse_grid(items: Optional[Sequence[str]]) -> Dict[str, List[Any]]:
    """Parse ``--grid name=v1,v2,v3`` items into a {name: [values]} grid."""
    out: Dict[str, List[Any]] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--grid must be name=v1,v2,..., got {item!r}")
        name, _, vals = item.partition("=")
        out[name.strip()] = [_coerce(v) for v in vals.split(",") if v != ""]
    return out


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------
def build_panels(args: argparse.Namespace) -> List[WindowPanel]:
    """Build panels from synthetic data or the real Tier-1 logs per ``args``."""
    if args.real:
        panels = build_window_panels(
            assets=args.assets,
            window_size_s=args.window,
            date_range=(args.start, args.end) if (args.start and args.end) else None,
            max_timeline_records=args.max_records,
            up_only=args.up_only,
            min_steps=args.min_steps,
        )
        if args.with_ticks:
            attach_binance_ticks(
                panels,
                date_range=(args.start, args.end)
                if (args.start and args.end)
                else None,
                max_records=args.max_records,
            )
        return panels
    # synthetic
    return make_synthetic_panels(
        args.n,
        seed=args.seed,
        window_size_s=args.window,
        assets=tuple(args.assets),
        up_and_down=args.up_and_down,
        edge_strength=args.edge_strength,
    )


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------
def run_single(args: argparse.Namespace, panels: Sequence[WindowPanel]) -> Dict[str, Any]:
    """Run a single backtest of one strategy and return the results dict."""
    params = _parse_params(args.param)
    strat = build_strategy(args.strategy, params)
    fill_model = BimodalFillModel(
        seed=args.seed,
        pi_toxic=args.pi_toxic,
        adverse_penalty=args.adverse_penalty,
    )
    portfolio = Portfolio(
        starting_cash=args.cash, fee_fn=default_fee_fn(base=args.fee_base)
    )
    engine = BacktestEngine(
        list(panels),
        [strat],
        fill_model=fill_model,
        portfolio=portfolio,
        config=EngineConfig(
            starting_cash=args.cash,
            seed=args.seed,
            allow_short_window_entries=not args.no_short_entries,
        ),
    )
    return engine.run()


def _search_config(args: argparse.Namespace) -> SearchConfig:
    return SearchConfig(
        objective=args.objective,
        min_trades=args.min_trades,
        min_profit_factor=args.min_pf,
        max_drawdown_limit=args.max_mdd,
        min_win_rate=args.min_wr,
        starting_cash=args.cash,
        seed=args.seed,
        pi_toxic=args.pi_toxic,
        adverse_penalty=args.adverse_penalty,
        fee_base=args.fee_base,
        allow_short_window_entries=not args.no_short_entries,
    )


def run_search(args: argparse.Namespace, panels: Sequence[WindowPanel]) -> None:
    """Run a parameter search and print the report."""
    grid = _parse_grid(args.grid)
    if not grid:
        print(
            "ERROR: --search requires at least one --grid name=v1,v2,... ",
            file=sys.stderr,
        )
        sys.exit(2)
    config = _search_config(args)
    n_samples = args.n_samples if args.search == "random" else None

    if args.search == "grid":
        report = grid_search(
            args.strategy, grid, panels, config=config, progress=args.progress
        )
    elif args.search == "random":
        report = random_search(
            args.strategy, grid, panels, n_samples=args.n_samples,
            config=config, progress=args.progress,
        )
    elif args.search == "train_test":
        report = train_test_search(
            args.strategy, grid, panels, train_frac=args.train_frac,
            config=config, n_samples=n_samples, top_k=args.top_k,
        )
    elif args.search == "walk_forward":
        report = walk_forward(
            args.strategy, grid, panels, k_folds=args.k_folds,
            config=config, n_samples=n_samples,
        )
    else:  # pragma: no cover - argparse choices guard this
        raise ValueError(f"unknown --search {args.search!r}")

    print_report(report, top=args.top)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_metrics(results: Dict[str, Any], as_json: bool) -> None:
    """Print the metrics summary of a single backtest."""
    overall = results["metrics_overall"]
    by_ws = results["metrics_by_window_size"]
    if as_json:
        print(json.dumps({"overall": overall, "by_window_size": by_ws}, indent=2))
        return
    print("== backtest metrics (after fees + funding) ==")
    for k in _METRIC_KEYS:
        v = overall.get(k)
        if isinstance(v, float):
            print(f"  {k:>18}: {v:,.4f}")
        else:
            print(f"  {k:>18}: {v}")
    print("-- by window size --")
    for ws, d in by_ws.items():
        print(
            f"  {ws}s: n={d['n_trades']} WR={d['win_rate']:.3f} "
            f"PF={d['profit_factor']:.3f} Sortino={d['sortino']:.3f} "
            f"PnL={d['total_net_pnl']:.2f}"
        )


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_research",
        description="Backtest / parameter-search the crypto_research strategies.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # data source (mutually exclusive)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--synthetic", action="store_true",
                     help="Use synthetic panels (default; no logs needed).")
    src.add_argument("--real", action="store_true",
                     help="Build panels from the real Tier-1 logs on disk.")

    # data params
    p.add_argument("--assets", nargs="+", default=["BTC", "ETH", "SOL"],
                   help="Assets to include.")
    p.add_argument("--window", type=int, default=300, choices=[300, 900],
                   help="Window size in seconds (5-min or 15-min).")
    p.add_argument("--start", default=None, help="Real-data start date YYYY-MM-DD.")
    p.add_argument("--end", default=None, help="Real-data end date YYYY-MM-DD.")
    p.add_argument("--max-records", dest="max_records", type=int, default=None,
                   help="Cap raw timeline rows read (fast smoke test).")
    p.add_argument("--up-only", dest="up_only", action="store_true",
                   help="(real) keep only UP/YES panels.")
    p.add_argument("--min-steps", dest="min_steps", type=int, default=1,
                   help="(real) drop panels with fewer steps.")
    p.add_argument("--with-ticks", dest="with_ticks", action="store_true",
                   help="(real) attach binance_trade ticks (slower).")
    # synthetic params
    p.add_argument("--n", type=int, default=400, help="(synthetic) number of windows.")
    p.add_argument("--up-and-down", dest="up_and_down", action="store_true",
                   help="(synthetic) emit both UP and DOWN token panels.")
    p.add_argument("--edge-strength", dest="edge_strength", type=float, default=0.6,
                   help="(synthetic) injected ground-truth edge in [0,1].")

    # strategy
    p.add_argument("--strategy", default=None,
                   help=f"Strategy name; one of {available_strategies()}.")
    p.add_argument("--param", action="append", default=None,
                   help="Strategy param name=value (repeatable).")
    p.add_argument("--list", action="store_true",
                   help="List registered strategies and exit.")

    # execution / portfolio
    p.add_argument("--cash", type=float, default=1000.0, help="Starting bankroll.")
    p.add_argument("--seed", type=int, default=7, help="Master RNG seed.")
    p.add_argument("--pi-toxic", dest="pi_toxic", type=float, default=0.25,
                   help="Bimodal-fill toxic probability.")
    p.add_argument("--adverse-penalty", dest="adverse_penalty", type=float,
                   default=0.03, help="Bimodal-fill adverse penalty per share.")
    p.add_argument("--fee-base", dest="fee_base", type=float, default=0.036,
                   help="Polymarket fee curve base (~1.8% at p=0.5).")
    p.add_argument("--no-short-entries", dest="no_short_entries", action="store_true",
                   help="Enforce per-strategy min_seconds_to_resolution gate.")

    # search
    p.add_argument("--search", default=None,
                   choices=["grid", "random", "train_test", "walk_forward"],
                   help="Run a parameter search instead of a single backtest.")
    p.add_argument("--grid", action="append", default=None,
                   help="Search axis name=v1,v2,v3 (repeatable).")
    p.add_argument("--objective", default="sortino",
                   help="Metric to maximise (sortino/sharpe/profit_factor/...).")
    p.add_argument("--min-trades", dest="min_trades", type=int, default=30,
                   help="Constraint: minimum closed trades.")
    p.add_argument("--min-pf", dest="min_pf", type=float, default=1.10,
                   help="Constraint: minimum profit factor.")
    p.add_argument("--max-mdd", dest="max_mdd", type=float, default=0.40,
                   help="Constraint: maximum drawdown fraction.")
    p.add_argument("--min-wr", dest="min_wr", type=float, default=0.0,
                   help="Constraint: minimum win rate (0 disables).")
    p.add_argument("--n-samples", dest="n_samples", type=int, default=50,
                   help="(random) number of grid points to sample.")
    p.add_argument("--train-frac", dest="train_frac", type=float, default=0.7,
                   help="(train_test) train fraction (time-ordered).")
    p.add_argument("--top-k", dest="top_k", type=int, default=5,
                   help="(train_test) #train winners re-tested OOS.")
    p.add_argument("--k-folds", dest="k_folds", type=int, default=4,
                   help="(walk_forward) number of time folds.")
    p.add_argument("--top", type=int, default=10, help="Report: rows to print.")
    p.add_argument("--progress", action="store_true", help="Print per-candidate progress.")

    # output
    p.add_argument("--json", action="store_true", help="Emit metrics as JSON.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI main; returns a process exit code."""
    args = build_parser().parse_args(argv)

    if args.list:
        print("registered strategies:")
        for name in available_strategies():
            print(f"  {name}")
        return 0

    if not args.strategy:
        print("ERROR: --strategy is required (or use --list).", file=sys.stderr)
        return 2
    if args.strategy not in available_strategies():
        print(
            f"ERROR: unknown strategy {args.strategy!r}; "
            f"available: {available_strategies()}",
            file=sys.stderr,
        )
        return 2

    # default data source = synthetic when neither flag is set
    if not args.real and not args.synthetic:
        args.synthetic = True

    panels = build_panels(args)
    # Status preamble goes to stderr so `--json` keeps stdout a clean,
    # machine-parseable JSON stream.
    print(
        f"built {len(panels)} panels "
        f"({'real' if args.real else 'synthetic'}, window={args.window}s, "
        f"assets={args.assets})",
        file=sys.stderr,
    )
    if not panels:
        print("ERROR: no panels built (check date range / logs).", file=sys.stderr)
        return 1

    if args.search:
        run_search(args, panels)
        return 0

    results = run_single(args, panels)
    print_metrics(results, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
