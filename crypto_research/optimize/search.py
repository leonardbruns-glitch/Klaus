"""Parameter-search harness: grid + random search with walk-forward splits.

This module drives a registered :class:`~crypto_research.strategies.base.Strategy`
through the :class:`~crypto_research.backtest.engine.BacktestEngine` over a set of
:class:`~crypto_research.data.schema.WindowPanel` s, sweeping a parameter grid (or a
random sample of it), and ranks the parameter sets by an **objective** under
**constraints**.

Objective & constraints (the ranking math)
-------------------------------------------
The default objective maximises the **annualized Sortino ratio** — downside-risk
adjusted return, ``E[r] / sqrt(E[min(r,0)^2]) * sqrt(periods_per_year)``.  Sortino
is preferred to Sharpe here because a binary-options equity curve is strongly
left-skewed (occasional total-loss legs), so penalising only *downside* deviation
is the honest risk measure.

A candidate is **feasible** only if it clears all hard constraints
(:class:`SearchConfig`):

* ``min_trades``            — reject thin samples (anti-noise; the project mandate
                              is n>=100 per bucket before any edge claim).
* ``min_profit_factor``     — gross-profit / gross-loss floor (>1 required to be
                              worth running at all; default 1.10).
* ``max_drawdown_limit``    — peak-to-trough equity drawdown ceiling (fraction).
* ``min_win_rate``          — optional win-rate floor.

Infeasible candidates are **not discarded** (they are recorded with their metrics
and ``feasible=False``) but are ranked *below* every feasible candidate so the
search never "wins" by reporting an over-fit point that violates a risk floor.
The objective for an infeasible candidate is set to ``-inf`` for ranking only.

Walk-forward / train-test split (the overfitting guard)
-------------------------------------------------------
Optimising parameters on the SAME data you then report is in-sample overfitting:
with enough knobs you can always fit the noise of one 11-day feature window.  Two
guards are provided and SHOULD be used together:

1. **Time-ordered train/test split** (:func:`split_panels_time`): panels are
   sorted by ``window_end_ts`` and cut at ``train_frac``; parameters are *selected*
   on the TRAIN slice and *re-evaluated, unchanged* on the held-out TEST slice.
   The reported edge is the TEST metric, never the TRAIN metric.

2. **Walk-forward** (:func:`walk_forward`): the panel timeline is cut into ``k``
   contiguous folds; for each fold ``i`` parameters are optimised on folds
   ``0..i-1`` (the past) and scored on fold ``i`` (the immediate future), then the
   per-fold out-of-sample scores are aggregated.  This simulates re-fitting the
   strategy periodically and trading it forward — the only honest estimate of a
   live edge.

Additional anti-overfitting discipline (documented, partly enforced):
   * The objective is computed on a **risk-adjusted** metric (Sortino), not raw
     PnL, so a single lucky window cannot dominate.
   * Hard ``min_trades`` gate rejects parameter sets that only ever fire a handful
     of times (the classic "0 trades, infinite Sharpe" overfit).
   * The SAME seed drives the fill model across all candidates so differences are
     attributable to parameters, not RNG luck; for a robustness check, sweep
     ``seed`` as just another parameter and require the candidate to clear the
     constraints across *all* seeds (multi-seed stability — see README).
   * Walk-forward **degradation** (train-minus-test objective) is reported so a
     large positive gap flags an over-fit candidate even if its test score is
     positive.

Reproducibility
---------------
All randomness (random-search sampling and the engine fill model) is seeded.  A
given ``SearchConfig`` + panel set reproduces bit-for-bit.

NON-HFT note
------------
This harness does not change the cadence of any strategy: every candidate is run
through the same bar-cadence engine.  It is a *meta*-search over structural
parameters, not a latency optimiser.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)

from ..backtest.engine import BacktestEngine, EngineConfig
from ..backtest.fills import BimodalFillModel
from ..backtest.portfolio import Portfolio, default_fee_fn
from ..data.schema import WindowPanel
from ..strategies.base import Strategy, build_strategy

# A metrics dict (the engine's ``metrics_overall``) -> a scalar to maximise.
ObjectiveFn = Callable[[Dict[str, Any]], float]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class SearchConfig:
    """Configuration for a parameter search.

    Attributes
    ----------
    objective
        Name of the metric to MAXIMISE, one of the keys in the engine's
        ``metrics_overall`` dict (``'sortino'`` default; also ``'sharpe'``,
        ``'profit_factor'``, ``'total_net_pnl'``, ``'total_return'``).  A
        custom :class:`ObjectiveFn` may be passed to the search functions to
        override this entirely.
    min_trades
        Reject candidates with fewer than this many closed trades (anti-noise).
    min_profit_factor
        Profit-factor floor for feasibility.
    max_drawdown_limit
        Max acceptable peak-to-trough drawdown fraction (in ``[0, 1]``).
    min_win_rate
        Optional win-rate floor (0 disables).
    starting_cash
        Backtest starting bankroll.
    seed
        Master seed for the engine fill model (and the default for random
        search sampling unless overridden).
    pi_toxic, adverse_penalty
        Bimodal-fill model parameters (see :class:`BimodalFillModel`); these
        are the *execution-stress* knobs — keep them FIXED across a search so
        candidates are compared under identical adverse-selection assumptions.
    fee_base
        Polymarket fee curve base (``default_fee_fn`` peaks ~1.8% notional at
        p=0.5 with the default 0.036).
    allow_short_window_entries
        Engine flag; if ``False`` the per-strategy ``min_seconds_to_resolution``
        gate is enforced.
    """

    objective: str = "sortino"
    # Project anti-sycophancy mandate: no edge claim below n>=100 per bucket.
    # Default binds to 100 so an un-tuned search cannot certify a thin sample;
    # lower it only deliberately for exploration on the thin 15-min folds.
    min_trades: int = 100
    min_profit_factor: float = 1.10
    max_drawdown_limit: float = 0.40
    min_win_rate: float = 0.0
    starting_cash: float = 1000.0
    seed: int = 7
    pi_toxic: float = 0.25
    adverse_penalty: float = 0.03
    fee_base: float = 0.036
    allow_short_window_entries: bool = True


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class EvalResult:
    """One evaluated parameter set on one panel slice.

    Attributes
    ----------
    params
        The strategy params dict that was evaluated.
    metrics
        The engine's ``metrics_overall`` dict (after fees + funding).
    objective_value
        The raw objective value (the metric being maximised), independent of
        feasibility.
    feasible
        Whether every hard constraint in :class:`SearchConfig` was satisfied.
    rank_score
        The value used for ranking: ``objective_value`` if feasible else
        ``-inf``.  Sorting candidates by ``rank_score`` (desc) puts every
        feasible candidate above every infeasible one.
    reason
        Human-readable note on why a candidate is infeasible ("" if feasible).
    """

    params: Dict[str, Any]
    metrics: Dict[str, Any]
    objective_value: float
    feasible: bool
    rank_score: float
    reason: str = ""


@dataclass
class SplitResult:
    """Train/test (or per-fold) evaluation of a single parameter set.

    Attributes
    ----------
    params
        The parameter set.
    train
        :class:`EvalResult` on the training slice (used for SELECTION).
    test
        :class:`EvalResult` on the held-out slice (used for REPORTING).
    degradation
        ``train.objective_value - test.objective_value``; a large positive
        value flags overfitting.
    """

    params: Dict[str, Any]
    train: EvalResult
    test: EvalResult
    degradation: float


@dataclass
class SearchReport:
    """Aggregate output of a search.

    Attributes
    ----------
    strategy
        Registered strategy name searched.
    config
        The :class:`SearchConfig` used.
    results
        All :class:`EvalResult` s (in-sample search) sorted best-first by
        ``rank_score``.  Empty for a pure walk-forward report.
    splits
        Per-candidate train/test :class:`SplitResult` s (when a split/
        walk-forward search was run), sorted by TEST ``rank_score`` best-first.
    best
        The best feasible :class:`EvalResult` (in-sample) or ``None``.
    best_split
        The best :class:`SplitResult` by TEST score (walk-forward / split) or
        ``None``.
    n_evaluated
        Number of distinct parameter sets evaluated.
    """

    strategy: str
    config: SearchConfig
    results: List[EvalResult] = field(default_factory=list)
    splits: List[SplitResult] = field(default_factory=list)
    best: Optional[EvalResult] = None
    best_split: Optional[SplitResult] = None
    n_evaluated: int = 0


# ---------------------------------------------------------------------------
# Objective / scoring
# ---------------------------------------------------------------------------
def default_objective(metrics: Dict[str, Any]) -> float:
    """Default objective: the annualized Sortino ratio (to be MAXIMISED).

    ``inf`` Sortino (positive mean, zero downside) is clamped to a large finite
    value so ranking is well-defined.
    """
    val = float(metrics.get("sortino", 0.0))
    if math.isinf(val):
        return 1e9 if val > 0 else -1e9
    if math.isnan(val):
        return -1e9
    return val


def _metric_objective(name: str) -> ObjectiveFn:
    """Build an objective that maximises ``metrics[name]`` (NaN/inf-safe)."""

    def _obj(metrics: Dict[str, Any]) -> float:
        val = float(metrics.get(name, 0.0))
        if math.isinf(val):
            return 1e9 if val > 0 else -1e9
        if math.isnan(val):
            return -1e9
        return val

    return _obj


def score_metrics(
    metrics: Dict[str, Any],
    config: SearchConfig,
    objective: Optional[ObjectiveFn] = None,
) -> Tuple[float, bool, float, str]:
    """Score a metrics dict against the objective + feasibility constraints.

    Returns
    -------
    (objective_value, feasible, rank_score, reason)
        ``objective_value`` is the raw objective.  ``feasible`` is the
        all-constraints-pass flag.  ``rank_score`` is ``objective_value`` if
        feasible else ``-inf``.  ``reason`` explains an infeasibility.
    """
    obj = objective or _metric_objective(config.objective)
    objective_value = obj(metrics)

    reasons: List[str] = []
    n = int(metrics.get("n_trades", 0))
    if n < config.min_trades:
        reasons.append(f"n_trades={n}<{config.min_trades}")
    pf = float(metrics.get("profit_factor", 0.0))
    if pf < config.min_profit_factor:
        reasons.append(f"PF={pf:.3f}<{config.min_profit_factor}")
    mdd = float(metrics.get("max_drawdown", 1.0))
    if mdd > config.max_drawdown_limit:
        reasons.append(f"MDD={mdd:.3f}>{config.max_drawdown_limit}")
    wr = float(metrics.get("win_rate", 0.0))
    if config.min_win_rate > 0.0 and wr < config.min_win_rate:
        reasons.append(f"WR={wr:.3f}<{config.min_win_rate}")

    feasible = not reasons
    rank_score = objective_value if feasible else float("-inf")
    return objective_value, feasible, rank_score, "; ".join(reasons)


# ---------------------------------------------------------------------------
# Single-evaluation backtest
# ---------------------------------------------------------------------------
def backtest_params(
    strategy: str,
    params: Dict[str, Any],
    panels: Sequence[WindowPanel],
    config: SearchConfig,
    objective: Optional[ObjectiveFn] = None,
) -> EvalResult:
    """Run one parameter set through the engine and score it.

    Builds a fresh strategy instance, a fresh seeded fill model and portfolio
    (so evaluations are independent), runs the backtest, and scores the
    ``metrics_overall`` dict.

    Parameters
    ----------
    strategy
        Registered strategy name (importing the module that registers it is the
        caller's responsibility — see :func:`crypto_research.optimize` /
        ``run_research`` which import the four strategy modules).
    params
        Strategy params dict (keys must match the strategy's params dataclass).
    panels
        The :class:`WindowPanel` slice to evaluate on.
    config
        Search config (constraints + execution-stress knobs).
    objective
        Optional custom objective; defaults to ``config.objective``.

    Returns
    -------
    EvalResult
    """
    strat: Strategy = build_strategy(strategy, params)
    fill_model = BimodalFillModel(
        seed=config.seed,
        pi_toxic=config.pi_toxic,
        adverse_penalty=config.adverse_penalty,
    )
    portfolio = Portfolio(
        starting_cash=config.starting_cash,
        fee_fn=default_fee_fn(base=config.fee_base),
    )
    engine = BacktestEngine(
        list(panels),
        [strat],
        fill_model=fill_model,
        portfolio=portfolio,
        config=EngineConfig(
            starting_cash=config.starting_cash,
            seed=config.seed,
            allow_short_window_entries=config.allow_short_window_entries,
        ),
    )
    results = engine.run()
    metrics = dict(results["metrics_overall"])  # type: ignore[index]
    objective_value, feasible, rank_score, reason = score_metrics(
        metrics, config, objective
    )
    return EvalResult(
        params=dict(params),
        metrics=metrics,
        objective_value=objective_value,
        feasible=feasible,
        rank_score=rank_score,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Grid expansion / sampling
# ---------------------------------------------------------------------------
def expand_grid(param_grid: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    """Cartesian product of ``{name: [values...]}`` into a list of dicts.

    An empty grid yields a single empty dict (the strategy defaults).
    """
    if not param_grid:
        return [{}]
    names = list(param_grid.keys())
    value_lists = [list(param_grid[k]) for k in names]
    combos: List[Dict[str, Any]] = []
    for values in itertools.product(*value_lists):
        combos.append(dict(zip(names, values)))
    return combos


def _sample_grid(
    param_grid: Dict[str, Sequence[Any]],
    n_samples: int,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """Draw ``n_samples`` *distinct* random points from the grid (no dup eval).

    If the grid has fewer points than ``n_samples``, every point is returned.
    """
    full = expand_grid(param_grid)
    if n_samples >= len(full):
        return full
    # sample distinct indices for reproducibility & no duplicate work
    idxs = rng.sample(range(len(full)), n_samples)
    return [full[i] for i in idxs]


# ---------------------------------------------------------------------------
# Grid / random search (in-sample, single panel slice)
# ---------------------------------------------------------------------------
def grid_search(
    strategy: str,
    param_grid: Dict[str, Sequence[Any]],
    panels: Sequence[WindowPanel],
    config: Optional[SearchConfig] = None,
    objective: Optional[ObjectiveFn] = None,
    progress: bool = False,
) -> SearchReport:
    """Exhaustive grid search over ``param_grid`` on ``panels``.

    .. warning::
       This is **in-sample**: the returned ranking reflects performance on the
       SAME panels.  For an honest edge estimate use :func:`walk_forward` or
       wrap with :func:`split_panels_time` and select on train / report on
       test.  In-sample search is only for *exploring* the parameter surface.

    Returns a :class:`SearchReport` with all results sorted best-first.
    """
    config = config or SearchConfig()
    combos = expand_grid(param_grid)
    results: List[EvalResult] = []
    for i, params in enumerate(combos):
        if progress:
            print(f"[grid {i + 1}/{len(combos)}] {params}")
        results.append(backtest_params(strategy, params, panels, config, objective))
    results.sort(key=lambda r: r.rank_score, reverse=True)
    best = next((r for r in results if r.feasible), None)
    return SearchReport(
        strategy=strategy,
        config=config,
        results=results,
        best=best,
        n_evaluated=len(results),
    )


def random_search(
    strategy: str,
    param_grid: Dict[str, Sequence[Any]],
    panels: Sequence[WindowPanel],
    n_samples: int = 50,
    config: Optional[SearchConfig] = None,
    objective: Optional[ObjectiveFn] = None,
    rng_seed: Optional[int] = None,
    progress: bool = False,
) -> SearchReport:
    """Random search: evaluate ``n_samples`` distinct random points of the grid.

    Random search is the recommended *in-sample explorer* for high-dimensional
    grids (it covers each axis more efficiently than a coarse full grid for the
    same evaluation budget; Bergstra & Bengio 2012).  Still in-sample — pair
    with a held-out split for the reported number.

    Parameters
    ----------
    n_samples
        Number of distinct grid points to evaluate.
    rng_seed
        Seed for the *sampling* RNG (defaults to ``config.seed``).  Independent
        of the engine fill-model seed.
    """
    config = config or SearchConfig()
    rng = random.Random(config.seed if rng_seed is None else rng_seed)
    combos = _sample_grid(param_grid, n_samples, rng)
    results: List[EvalResult] = []
    for i, params in enumerate(combos):
        if progress:
            print(f"[random {i + 1}/{len(combos)}] {params}")
        results.append(backtest_params(strategy, params, panels, config, objective))
    results.sort(key=lambda r: r.rank_score, reverse=True)
    best = next((r for r in results if r.feasible), None)
    return SearchReport(
        strategy=strategy,
        config=config,
        results=results,
        best=best,
        n_evaluated=len(results),
    )


# ---------------------------------------------------------------------------
# Time-ordered split + walk-forward (the overfitting guards)
# ---------------------------------------------------------------------------
def split_panels_time(
    panels: Sequence[WindowPanel],
    train_frac: float = 0.7,
) -> Tuple[List[WindowPanel], List[WindowPanel]]:
    """Time-ordered train/test split by ``window_end_ts``.

    Panels are sorted by ``window_end_ts`` (then ``token_id`` for determinism)
    and cut at ``train_frac``.  This is a *forward* split — TRAIN is strictly
    the past, TEST strictly the future — so selecting on TRAIN and reporting on
    TEST never leaks future information into the parameter choice.

    Parameters
    ----------
    train_frac
        Fraction of panels (by count, in time order) allocated to TRAIN.

    Returns
    -------
    (train_panels, test_panels)
    """
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0, 1)")
    ordered = sorted(panels, key=lambda p: (p.window_end_ts, p.token_id))
    cut = int(round(len(ordered) * train_frac))
    cut = max(1, min(len(ordered) - 1, cut)) if len(ordered) >= 2 else len(ordered)
    return ordered[:cut], ordered[cut:]


def _time_folds(
    panels: Sequence[WindowPanel], k: int
) -> List[List[WindowPanel]]:
    """Cut panels (time-ordered) into ``k`` contiguous, roughly-equal folds."""
    ordered = sorted(panels, key=lambda p: (p.window_end_ts, p.token_id))
    n = len(ordered)
    if k < 2:
        raise ValueError("walk-forward needs k>=2 folds")
    fold_size = max(1, n // k)
    folds: List[List[WindowPanel]] = []
    for i in range(k):
        start = i * fold_size
        end = n if i == k - 1 else (i + 1) * fold_size
        folds.append(ordered[start:end])
    return folds


def _search_in_sample(
    strategy: str,
    param_grid: Dict[str, Sequence[Any]],
    panels: Sequence[WindowPanel],
    config: SearchConfig,
    objective: Optional[ObjectiveFn],
    n_samples: Optional[int],
    rng_seed: Optional[int],
) -> SearchReport:
    """Dispatch to grid or random search (random iff ``n_samples`` given)."""
    if n_samples is not None:
        return random_search(
            strategy, param_grid, panels, n_samples=n_samples,
            config=config, objective=objective, rng_seed=rng_seed,
        )
    return grid_search(strategy, param_grid, panels, config=config, objective=objective)


def train_test_search(
    strategy: str,
    param_grid: Dict[str, Sequence[Any]],
    panels: Sequence[WindowPanel],
    train_frac: float = 0.7,
    config: Optional[SearchConfig] = None,
    objective: Optional[ObjectiveFn] = None,
    n_samples: Optional[int] = None,
    rng_seed: Optional[int] = None,
    top_k: int = 5,
) -> SearchReport:
    """Select parameters on a TRAIN slice, report on a held-out TEST slice.

    Procedure
    ---------
    1. Forward-split panels into TRAIN (past) / TEST (future).
    2. Search the grid IN-SAMPLE on TRAIN (grid or random).
    3. Take the ``top_k`` feasible TRAIN candidates and *re-run them unchanged*
       on TEST.
    4. Report each as a :class:`SplitResult` (train, test, degradation), sorted
       by TEST ``rank_score`` best-first.

    The reported edge is the TEST metric.  ``degradation = train_obj - test_obj``
    quantifies overfitting (large positive ⇒ the TRAIN score did not generalise).

    ``top_k`` limits how many TRAIN winners are re-evaluated out-of-sample;
    re-testing only the top few (rather than all) keeps the TEST slice from
    being mined as a second training set.
    """
    config = config or SearchConfig()
    train, test = split_panels_time(panels, train_frac=train_frac)
    train_report = _search_in_sample(
        strategy, param_grid, train, config, objective, n_samples, rng_seed
    )
    # candidate pool: feasible-on-train first, then fall back to best-by-rank
    feasible_train = [r for r in train_report.results if r.feasible]
    pool = (feasible_train or train_report.results)[:top_k]

    splits: List[SplitResult] = []
    for tr in pool:
        te = backtest_params(strategy, tr.params, test, config, objective)
        splits.append(
            SplitResult(
                params=tr.params,
                train=tr,
                test=te,
                degradation=tr.objective_value - te.objective_value,
            )
        )
    splits.sort(key=lambda s: s.test.rank_score, reverse=True)
    best_split = next((s for s in splits if s.test.feasible), None)
    return SearchReport(
        strategy=strategy,
        config=config,
        results=train_report.results,
        splits=splits,
        best=train_report.best,
        best_split=best_split,
        n_evaluated=train_report.n_evaluated,
    )


def walk_forward(
    strategy: str,
    param_grid: Dict[str, Sequence[Any]],
    panels: Sequence[WindowPanel],
    k_folds: int = 4,
    config: Optional[SearchConfig] = None,
    objective: Optional[ObjectiveFn] = None,
    n_samples: Optional[int] = None,
    rng_seed: Optional[int] = None,
) -> SearchReport:
    """Walk-forward (anchored) parameter search — the honest OOS estimator.

    For each fold ``i`` in ``1..k-1``:
      * optimise the grid in-sample on the ANCHORED past (folds ``0..i-1``),
        picking that window's best feasible parameter set;
      * score that parameter set OUT-OF-SAMPLE on fold ``i`` (the immediate
        future);
    then aggregate the per-fold out-of-sample :class:`SplitResult` s.

    This mimics a live workflow: periodically refit on all data so far, then
    trade forward until the next refit.  The aggregate of the per-fold TEST
    scores is the closest thing to a credible live-edge estimate the framework
    can produce — and because each fold re-selects parameters, it does not
    reward a single globally-overfit point.

    Returns a :class:`SearchReport` whose ``splits`` are the per-fold OOS
    results (the per-fold chosen params + their test metrics) and whose
    ``best_split`` is the fold with the best OOS ``rank_score``.

    Notes
    -----
    Needs enough panels per fold to clear ``config.min_trades`` — with the 11-day
    Tier-1 feature era this is realistic for 5-min windows (thousands of panels)
    but marginal for 15-min; reduce ``k_folds`` if folds are starved.
    """
    config = config or SearchConfig()
    folds = _time_folds(panels, k_folds)
    splits: List[SplitResult] = []
    for i in range(1, k_folds):
        train = [p for f in folds[:i] for p in f]
        test = folds[i]
        if not train or not test:
            continue
        train_report = _search_in_sample(
            strategy, param_grid, train, config, objective, n_samples, rng_seed
        )
        chosen = train_report.best or (
            train_report.results[0] if train_report.results else None
        )
        if chosen is None:
            continue
        te = backtest_params(strategy, chosen.params, test, config, objective)
        splits.append(
            SplitResult(
                params=chosen.params,
                train=chosen,
                test=te,
                degradation=chosen.objective_value - te.objective_value,
            )
        )
    splits.sort(key=lambda s: s.test.rank_score, reverse=True)
    best_split = next((s for s in splits if s.test.feasible), None)
    return SearchReport(
        strategy=strategy,
        config=config,
        splits=splits,
        best_split=best_split,
        n_evaluated=sum(1 for _ in splits),
    )


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------
_REPORT_KEYS = (
    "n_trades",
    "win_rate",
    "profit_factor",
    "sharpe",
    "sortino",
    "max_drawdown",
    "total_net_pnl",
    "total_return",
)


def format_eval(res: EvalResult) -> str:
    """One-line human summary of an :class:`EvalResult`."""
    m = res.metrics
    flag = "OK " if res.feasible else "REJ"
    parts = [
        f"obj={res.objective_value:.3f}",
        f"n={int(m.get('n_trades', 0))}",
        f"WR={float(m.get('win_rate', 0.0)):.3f}",
        f"PF={float(m.get('profit_factor', 0.0)):.3f}",
        f"Srt={float(m.get('sortino', 0.0)):.3f}",
        f"Shp={float(m.get('sharpe', 0.0)):.3f}",
        f"MDD={float(m.get('max_drawdown', 0.0)):.3f}",
        f"PnL={float(m.get('total_net_pnl', 0.0)):.2f}",
    ]
    line = f"[{flag}] " + "  ".join(parts) + f"  params={res.params}"
    if not res.feasible and res.reason:
        line += f"  ({res.reason})"
    return line


def print_report(report: SearchReport, top: int = 10) -> None:
    """Print a human-readable summary of a :class:`SearchReport`."""
    print(f"== search report: {report.strategy} ==")
    print(
        f"objective={report.config.objective}  evaluated={report.n_evaluated}  "
        f"constraints: n>={report.config.min_trades} "
        f"PF>={report.config.min_profit_factor} "
        f"MDD<={report.config.max_drawdown_limit} "
        f"WR>={report.config.min_win_rate}"
    )
    if report.results:
        print("\n-- in-sample ranking (top) --")
        for res in report.results[:top]:
            print("  " + format_eval(res))
        if report.best is not None:
            print("\nbest feasible (in-sample):")
            print("  " + format_eval(report.best))
        else:
            print("\nNO feasible candidate in-sample.")
    if report.splits:
        print("\n-- out-of-sample (train -> test) --")
        for s in report.splits[:top]:
            print(
                f"  TEST {format_eval(s.test)}\n"
                f"       (train_obj={s.train.objective_value:.3f}, "
                f"degradation={s.degradation:+.3f})"
            )
        if report.best_split is not None:
            print("\nbest by TEST score:")
            print("  TEST  " + format_eval(report.best_split.test))
            print(
                f"  degradation (train-test) = "
                f"{report.best_split.degradation:+.3f}"
            )
        else:
            print("\nNO feasible OUT-OF-SAMPLE candidate.")


__all__ = [
    "ObjectiveFn",
    "SearchConfig",
    "EvalResult",
    "SplitResult",
    "SearchReport",
    "default_objective",
    "score_metrics",
    "backtest_params",
    "expand_grid",
    "grid_search",
    "random_search",
    "split_panels_time",
    "train_test_search",
    "walk_forward",
    "format_eval",
    "print_report",
]
