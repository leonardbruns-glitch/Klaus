"""Performance metrics: Sharpe, Sortino, max-drawdown, profit factor, summary.

All metrics are computed **after fees and funding** (the portfolio's equity
curve and closed trades already net those out).

Annualization for bar-cadence strategies
-----------------------------------------
The equity curve is sampled once per *window* (5-min or 15-min bar), so the
per-period return is a per-bar return.  To annualize a Sharpe computed on
per-bar returns we scale by ``sqrt(periods_per_year)`` where

* 5-min bars:  ``periods_per_year = 365 * 24 * 60 / 5  = 105_120``
* 15-min bars: ``periods_per_year = 365 * 24 * 60 / 15 =  35_040``

(24/7 crypto markets ⇒ no trading-day discount.)  Use
:func:`periods_per_year_for_window` to get the right constant.  Because these
markets trade continuously, the *calendar* convention (365d) is used rather
than the equity-market 252-day convention.

NON-HFT note: returns are measured on *bars*, never on ticks — the annualizer
reflects a position-cadence strategy, not a latency engine.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0


def periods_per_year_for_window(window_size_s: int) -> float:
    """Bars-per-year for a given window size (24/7 calendar convention)."""
    if window_size_s <= 0:
        raise ValueError("window_size_s must be positive")
    return SECONDS_PER_YEAR / float(window_size_s)


def equity_to_returns(equity_curve: Sequence[float]) -> np.ndarray:
    """Simple per-period returns from an equity curve.

    ``r_t = E_t / E_{t-1} - 1``.  Periods where the prior equity is
    non-positive are dropped (undefined return).
    """
    eq = np.asarray(equity_curve, dtype=float)
    if eq.size < 2:
        return np.array([], dtype=float)
    prev = eq[:-1]
    cur = eq[1:]
    mask = prev > 0
    rets = np.full(prev.shape, np.nan)
    rets[mask] = cur[mask] / prev[mask] - 1.0
    return rets[~np.isnan(rets)]


def sharpe(
    returns: Sequence[float],
    periods_per_year: float,
    *,
    risk_free_per_period: float = 0.0,
) -> float:
    """Annualized Sharpe ratio of per-period returns.

    ``Sharpe = (mean(r - rf) / std(r)) * sqrt(periods_per_year)``.
    Uses the population std (ddof=0); returns 0.0 if std is ~0 or n<2.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - risk_free_per_period
    sd = excess.std(ddof=0)
    if sd < 1e-12:
        return 0.0
    return float(excess.mean() / sd * math.sqrt(periods_per_year))


def sortino(
    returns: Sequence[float],
    periods_per_year: float,
    *,
    risk_free_per_period: float = 0.0,
    target: float = 0.0,
) -> float:
    """Annualized Sortino ratio (downside-deviation denominator).

    Downside deviation uses only returns below ``target`` and divides by the
    full sample size ``n`` (standard MAR convention).  Returns ``inf`` if
    there is positive mean excess and no downside, ``0.0`` if n<2.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - risk_free_per_period
    downside = np.minimum(r - target, 0.0)
    dd = math.sqrt(np.mean(downside ** 2))
    mean_excess = excess.mean()
    if dd < 1e-12:
        return float("inf") if mean_excess > 0 else 0.0
    return float(mean_excess / dd * math.sqrt(periods_per_year))


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction in ``[0, 1]``.

    ``MDD = max_t (1 - E_t / running_max(E)_t)``.  Returns 0.0 for a curve
    with fewer than 2 points or a non-positive running peak.
    """
    eq = np.asarray(equity_curve, dtype=float)
    if eq.size < 2:
        return 0.0
    running_max = np.maximum.accumulate(eq)
    safe = running_max > 0
    dd = np.zeros_like(eq)
    dd[safe] = 1.0 - eq[safe] / running_max[safe]
    return float(np.clip(dd.max(), 0.0, 1.0))


def max_drawdown_usd(equity_curve: Sequence[float]) -> float:
    """Maximum peak-to-trough drawdown in absolute USD."""
    eq = np.asarray(equity_curve, dtype=float)
    if eq.size < 2:
        return 0.0
    running_max = np.maximum.accumulate(eq)
    return float((running_max - eq).max())


def profit_factor(trade_pnls: Sequence[float]) -> float:
    """Gross profit / gross loss over realised trades.

    ``inf`` if there are wins and no losses; ``0.0`` if no wins.
    """
    p = np.asarray(trade_pnls, dtype=float)
    if p.size == 0:
        return 0.0
    gross_profit = p[p > 0].sum()
    gross_loss = -p[p < 0].sum()
    if gross_loss < 1e-12:
        return float("inf") if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def win_rate(trade_pnls: Sequence[float]) -> float:
    """Fraction of trades with strictly positive net PnL."""
    p = np.asarray(trade_pnls, dtype=float)
    if p.size == 0:
        return 0.0
    return float((p > 0).mean())


def summary(
    equity_curve: Sequence[float],
    trades: Sequence,
    *,
    window_size_s: int = 300,
    periods_per_year: Optional[float] = None,
    starting_cash: Optional[float] = None,
) -> Dict[str, float]:
    """Full metric summary dict (after fees + funding).

    Parameters
    ----------
    equity_curve
        Per-bar equity samples (from :meth:`Portfolio.mark`).
    trades
        Sequence of objects exposing a ``net_pnl`` attribute (e.g.
        :class:`~crypto_research.backtest.portfolio.TradeRecord`) OR plain
        floats.
    window_size_s
        Bar size, used to derive the annualizer if ``periods_per_year`` is
        not given.
    periods_per_year
        Override the annualizer (e.g. when bars are irregular).
    starting_cash
        If given, total/return metrics are reported relative to it.

    Returns
    -------
    dict
        Keys: ``n_trades, win_rate, profit_factor, sharpe, sortino,
        max_drawdown, max_drawdown_usd, total_net_pnl, mean_trade_pnl,
        final_equity, total_return, periods_per_year``.
    """
    if periods_per_year is None:
        periods_per_year = periods_per_year_for_window(window_size_s)

    pnls = _extract_pnls(trades)
    rets = equity_to_returns(equity_curve)
    eq = np.asarray(equity_curve, dtype=float)
    final_eq = float(eq[-1]) if eq.size else (starting_cash or 0.0)
    base = starting_cash if starting_cash is not None else (
        float(eq[0]) if eq.size else 0.0
    )
    total_return = (final_eq / base - 1.0) if base and base > 0 else 0.0

    return {
        "n_trades": int(len(pnls)),
        "win_rate": win_rate(pnls),
        "profit_factor": profit_factor(pnls),
        "sharpe": sharpe(rets, periods_per_year),
        "sortino": sortino(rets, periods_per_year),
        "max_drawdown": max_drawdown(equity_curve),
        "max_drawdown_usd": max_drawdown_usd(equity_curve),
        "total_net_pnl": float(np.sum(pnls)) if len(pnls) else 0.0,
        "mean_trade_pnl": float(np.mean(pnls)) if len(pnls) else 0.0,
        "final_equity": final_eq,
        "total_return": float(total_return),
        "periods_per_year": float(periods_per_year),
    }


def _extract_pnls(trades: Sequence) -> List[float]:
    """Pull net PnL floats from trade records or accept raw floats."""
    out: List[float] = []
    for t in trades:
        if hasattr(t, "net_pnl"):
            out.append(float(t.net_pnl))
        elif isinstance(t, (int, float)):
            out.append(float(t))
    return out


__all__ = [
    "SECONDS_PER_YEAR",
    "periods_per_year_for_window",
    "equity_to_returns",
    "sharpe",
    "sortino",
    "max_drawdown",
    "max_drawdown_usd",
    "profit_factor",
    "win_rate",
    "summary",
]
