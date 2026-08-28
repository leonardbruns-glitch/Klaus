"""Portfolio accounting: Polymarket binary legs + perp-swap legs with funding.

Two leg types
-------------
1. **Binary leg** (Polymarket up/down token).  A share is bought at a price
   ``p in [0, 1]`` and settles to ``1.0`` (token resolves YES) or ``0.0``
   (resolves NO).  Buying the NO token is modelled as a separate binary leg on
   the NO token (price = its own ask), NOT as a short of YES — this matches
   how the live book actually trades up/down pairs.

2. **Perp-swap leg** (Binance futures hedge).  A directional notional with
   linear PnL ``qty * (exit - entry)`` and **funding accrual**:
   every funding interval the holder of the position pays/receives
   ``funding_rate * notional`` (positive funding ⇒ longs pay shorts).  This
   lets a strategy hedge a binary leg's directional exposure and carry the
   funding basis as part of the edge.

Fees
----
Polymarket up/down fees are modelled by an **injectable** ``fee_fn(price,
shares) -> usd`` (the logged ``fee_rate_bps`` is always 0.0 and is ignored).
The documented live curve peaks at ~1.8% of notional at ``p=0.5`` and scales
as ``base * min(p, 1-p) * (shares * price)``.  :func:`default_fee_fn` builds
exactly that; the backtester can inject a stressed alternative.

All PnL is **after fees and after funding**.  The portfolio exposes a
mark-to-market equity curve so :mod:`metrics` can compute Sharpe/Sortino/MDD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# fee_fn(price, shares) -> usd fee
FeeFn = Callable[[float, float], float]


def default_fee_fn(base: float = 0.036) -> FeeFn:
    """Build the documented Polymarket up/down fee function.

    ``fee = base * min(p, 1-p) * (shares * price)``.

    With ``base = 0.036`` the peak fee at ``p = 0.5`` is
    ``0.036 * 0.5 = 0.018`` = **1.8% of notional**, matching the documented
    live curve; it tapers toward the price extremes.

    Parameters
    ----------
    base
        Scale so that ``base * 0.5`` equals the peak notional fee rate.

    Returns
    -------
    FeeFn
        ``fee_fn(price, shares) -> usd``.
    """

    def _fee(price: float, shares: float) -> float:
        p = min(max(price, 0.0), 1.0)
        notional = shares * p
        return base * min(p, 1.0 - p) * notional

    return _fee


def zero_fee_fn() -> FeeFn:
    """A no-fee function (for isolating gross edge in diagnostics)."""

    def _fee(price: float, shares: float) -> float:
        return 0.0

    return _fee


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@dataclass
class BinaryPosition:
    """An open Polymarket binary-token position.

    Attributes
    ----------
    token_id
        Identifier of the bought token (YES or NO leg — each its own token).
    asset, window_end_ts, window_size_s
        Window identity for joining the settlement label.
    shares
        Share count held (always >= 0; a "short" is a separate NO-token leg).
    entry_price
        Average per-share entry price actually paid (post-fill-model).
    entry_fee
        USD fee paid at entry (from ``fee_fn``).
    entry_ts
        Epoch-seconds entry time.
    outcome_dir
        ``'up'`` / ``'down'`` of this token (for reporting).
    meta
        Free-form tags (strategy name, signal meta, etc.).
    """

    token_id: str
    asset: str
    window_end_ts: int
    window_size_s: int
    shares: float
    entry_price: float
    entry_fee: float
    entry_ts: float
    outcome_dir: Optional[str] = None
    meta: dict = field(default_factory=dict)

    @property
    def cost_basis(self) -> float:
        """USD deployed at entry incl. fee = shares*entry_price + entry_fee."""
        return self.shares * self.entry_price + self.entry_fee

    def settle_value(self, resolved_yes_for_token: int) -> float:
        """Settlement cash = shares if token resolves YES else 0."""
        return self.shares * (1.0 if resolved_yes_for_token else 0.0)


@dataclass
class PerpPosition:
    """A Binance perp-swap hedge leg with funding accrual.

    Attributes
    ----------
    asset
        Underlying (BTC/ETH/SOL).
    qty
        Signed quantity in underlying units (+ long, - short).
    entry_price
        Underlying entry price.
    entry_ts
        Epoch-seconds entry time.
    funding_rate
        Per-interval funding rate (fraction of notional).  Positive ⇒ longs
        pay shorts.  Sign of accrual = ``-sign(qty) * funding_rate``.
    funding_interval_s
        Seconds per funding charge (Binance perps ≈ 8h = 28800s).
    accrued_funding
        Running USD funding paid (+) / received (-) so far.
    last_funding_ts
        Last time funding was charged.
    """

    asset: str
    qty: float
    entry_price: float
    entry_ts: float
    funding_rate: float = 0.0
    funding_interval_s: float = 28800.0
    accrued_funding: float = 0.0
    last_funding_ts: float = 0.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.last_funding_ts == 0.0:
            self.last_funding_ts = self.entry_ts

    def notional(self, price: float) -> float:
        return abs(self.qty) * price

    def accrue_funding(self, now_ts: float, mark_price: float) -> float:
        """Charge funding for whole intervals elapsed; return USD accrued now.

        Longs pay when ``funding_rate > 0``: cash flow =
        ``-qty * funding_rate * mark_price`` per interval (long qty>0 pays).
        """
        if self.funding_interval_s <= 0:
            return 0.0
        elapsed = now_ts - self.last_funding_ts
        n_intervals = int(elapsed // self.funding_interval_s)
        if n_intervals <= 0:
            return 0.0
        per_interval = -self.qty * self.funding_rate * mark_price
        charge = per_interval * n_intervals
        self.accrued_funding += charge
        self.last_funding_ts += n_intervals * self.funding_interval_s
        return charge

    def unrealized_pnl(self, mark_price: float) -> float:
        """Linear perp PnL before funding: qty * (mark - entry)."""
        return self.qty * (mark_price - self.entry_price)


# ---------------------------------------------------------------------------
# Closed-trade record (for metrics / attribution)
# ---------------------------------------------------------------------------


@dataclass
class TradeRecord:
    """A fully-realised round-trip for metrics + attribution."""

    kind: str  # 'binary' | 'perp'
    token_id: Optional[str]
    asset: str
    entry_ts: float
    exit_ts: float
    entry_price: float
    exit_price: float
    shares: float
    gross_pnl: float
    fee_paid: float
    funding_paid: float
    net_pnl: float
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


@dataclass
class Portfolio:
    """Cash + open binary/perp legs, fee/funding accounting, equity curve.

    Parameters
    ----------
    starting_cash
        Initial bankroll (USD).
    fee_fn
        Injectable Polymarket fee model; defaults to :func:`default_fee_fn`.

    Conventions
    -----------
    * ``cash`` is reduced by ``shares*price + fee`` at every binary buy and
      increased by settlement at resolution.
    * Perp legs do not consume cash here (margin is abstracted); their PnL and
      funding flow into realised PnL on close.
    * :meth:`mark` snapshots equity (cash + MTM of open legs) onto the equity
      curve — call it once per engine step for the metrics module.
    """

    starting_cash: float = 1000.0
    fee_fn: FeeFn = field(default_factory=default_fee_fn)

    cash: float = field(init=False)
    binary_positions: List[BinaryPosition] = field(init=False, default_factory=list)
    perp_positions: List[PerpPosition] = field(init=False, default_factory=list)
    closed_trades: List[TradeRecord] = field(init=False, default_factory=list)
    realized_pnl: float = field(init=False, default=0.0)
    total_fees: float = field(init=False, default=0.0)
    total_funding: float = field(init=False, default=0.0)
    equity_curve: List[float] = field(init=False, default_factory=list)
    equity_ts: List[float] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.cash = float(self.starting_cash)

    # -- binary legs ----------------------------------------------------
    def open_binary(
        self,
        *,
        token_id: str,
        asset: str,
        window_end_ts: int,
        window_size_s: int,
        shares: float,
        fill_price: float,
        entry_ts: float,
        outcome_dir: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> Optional[BinaryPosition]:
        """Buy ``shares`` of a binary token at ``fill_price``.

        Returns the created position, or ``None`` if there is not enough cash
        to cover cost + fee (the order is rejected, not partially filled).
        """
        if shares <= 0:
            return None
        fee = self.fee_fn(fill_price, shares)
        cost = shares * fill_price + fee
        if cost > self.cash + 1e-9:
            return None
        self.cash -= cost
        self.total_fees += fee
        pos = BinaryPosition(
            token_id=token_id,
            asset=asset,
            window_end_ts=int(window_end_ts),
            window_size_s=int(window_size_s),
            shares=float(shares),
            entry_price=float(fill_price),
            entry_fee=float(fee),
            entry_ts=float(entry_ts),
            outcome_dir=outcome_dir,
            meta=dict(meta or {}),
        )
        self.binary_positions.append(pos)
        return pos

    def settle_binary(
        self,
        pos: BinaryPosition,
        *,
        resolved_yes_for_token: int,
        exit_ts: float,
    ) -> float:
        """Settle a binary position at resolution (1.0/0.0) and book PnL.

        Returns the net PnL of the trade (after the entry fee already paid).
        Settlement itself incurs no Polymarket trading fee (resolution payout).
        """
        payout = pos.settle_value(resolved_yes_for_token)
        self.cash += payout
        exit_price = 1.0 if resolved_yes_for_token else 0.0
        gross = pos.shares * (exit_price - pos.entry_price)
        net = gross - pos.entry_fee
        self.realized_pnl += net
        self.closed_trades.append(
            TradeRecord(
                kind="binary",
                token_id=pos.token_id,
                asset=pos.asset,
                entry_ts=pos.entry_ts,
                exit_ts=float(exit_ts),
                entry_price=pos.entry_price,
                exit_price=exit_price,
                shares=pos.shares,
                gross_pnl=gross,
                fee_paid=pos.entry_fee,
                funding_paid=0.0,
                net_pnl=net,
                meta=dict(pos.meta),
            )
        )
        if pos in self.binary_positions:
            self.binary_positions.remove(pos)
        return net

    def close_binary_at_price(
        self,
        pos: BinaryPosition,
        *,
        fill_price: float,
        exit_ts: float,
    ) -> float:
        """Early-exit a binary leg by selling at ``fill_price`` (hits the bid).

        Sell incurs a fee via ``fee_fn``.  Returns net PnL of the round-trip.
        """
        fee = self.fee_fn(fill_price, pos.shares)
        proceeds = pos.shares * fill_price - fee
        self.cash += proceeds
        self.total_fees += fee
        gross = pos.shares * (fill_price - pos.entry_price)
        net = gross - pos.entry_fee - fee
        self.realized_pnl += net
        self.closed_trades.append(
            TradeRecord(
                kind="binary",
                token_id=pos.token_id,
                asset=pos.asset,
                entry_ts=pos.entry_ts,
                exit_ts=float(exit_ts),
                entry_price=pos.entry_price,
                exit_price=float(fill_price),
                shares=pos.shares,
                gross_pnl=gross,
                fee_paid=pos.entry_fee + fee,
                funding_paid=0.0,
                net_pnl=net,
                meta=dict(pos.meta),
            )
        )
        if pos in self.binary_positions:
            self.binary_positions.remove(pos)
        return net

    # -- perp legs ------------------------------------------------------
    def open_perp(
        self,
        *,
        asset: str,
        qty: float,
        entry_price: float,
        entry_ts: float,
        funding_rate: float = 0.0,
        funding_interval_s: float = 28800.0,
        meta: Optional[dict] = None,
    ) -> PerpPosition:
        """Open a signed perp hedge leg (no cash consumed; margin abstracted)."""
        pos = PerpPosition(
            asset=asset,
            qty=float(qty),
            entry_price=float(entry_price),
            entry_ts=float(entry_ts),
            funding_rate=float(funding_rate),
            funding_interval_s=float(funding_interval_s),
            meta=dict(meta or {}),
        )
        self.perp_positions.append(pos)
        return pos

    def accrue_all_funding(self, now_ts: float, mark_prices: Dict[str, float]) -> float:
        """Charge funding on all open perp legs; return total USD this step."""
        total = 0.0
        for pos in self.perp_positions:
            mark = mark_prices.get(pos.asset, pos.entry_price)
            charge = pos.accrue_funding(now_ts, mark)
            if charge:
                self.cash += charge  # +=, sign already correct (receive>0)
                self.total_funding += charge
                total += charge
        return total

    def close_perp(
        self,
        pos: PerpPosition,
        *,
        exit_price: float,
        exit_ts: float,
    ) -> float:
        """Close a perp leg; book linear PnL net of accrued funding."""
        gross = pos.unrealized_pnl(exit_price)
        net = gross + pos.accrued_funding  # accrued already signed cash flow
        self.cash += gross  # funding already added to cash as it accrued
        self.realized_pnl += net
        self.closed_trades.append(
            TradeRecord(
                kind="perp",
                token_id=None,
                asset=pos.asset,
                entry_ts=pos.entry_ts,
                exit_ts=float(exit_ts),
                entry_price=pos.entry_price,
                exit_price=float(exit_price),
                shares=abs(pos.qty),
                gross_pnl=gross,
                fee_paid=0.0,
                funding_paid=-pos.accrued_funding,
                net_pnl=net,
                meta=dict(pos.meta),
            )
        )
        if pos in self.perp_positions:
            self.perp_positions.remove(pos)
        return net

    # -- marking / equity ----------------------------------------------
    def unrealized_pnl(
        self,
        *,
        binary_marks: Optional[Dict[str, float]] = None,
        perp_marks: Optional[Dict[str, float]] = None,
    ) -> float:
        """MTM unrealized PnL across open legs.

        ``binary_marks`` maps ``token_id -> current bid`` (conservative mark);
        unmarked binary legs are held at cost.  ``perp_marks`` maps
        ``asset -> price``; unmarked perp legs held at entry.
        """
        upl = 0.0
        bm = binary_marks or {}
        for pos in self.binary_positions:
            mark = bm.get(pos.token_id, pos.entry_price)
            upl += pos.shares * (mark - pos.entry_price) - pos.entry_fee
        pm = perp_marks or {}
        for pos in self.perp_positions:
            mark = pm.get(pos.asset, pos.entry_price)
            upl += pos.unrealized_pnl(mark) + pos.accrued_funding
        return upl

    def equity(
        self,
        *,
        binary_marks: Optional[Dict[str, float]] = None,
        perp_marks: Optional[Dict[str, float]] = None,
    ) -> float:
        """Total equity = cash + cost of open binary legs + MTM adjustments.

        Cash already excludes deployed binary capital, so we add it back at
        mark: ``equity = cash + Σ shares*mark(binary) + Σ perp_mtm``.
        """
        eq = self.cash
        bm = binary_marks or {}
        for pos in self.binary_positions:
            mark = bm.get(pos.token_id, pos.entry_price)
            eq += pos.shares * mark
        pm = perp_marks or {}
        for pos in self.perp_positions:
            mark = pm.get(pos.asset, pos.entry_price)
            eq += pos.unrealized_pnl(mark) + pos.accrued_funding
        return eq

    def mark(
        self,
        now_ts: float,
        *,
        binary_marks: Optional[Dict[str, float]] = None,
        perp_marks: Optional[Dict[str, float]] = None,
    ) -> float:
        """Append the current equity to the equity curve and return it."""
        eq = self.equity(binary_marks=binary_marks, perp_marks=perp_marks)
        self.equity_curve.append(eq)
        self.equity_ts.append(float(now_ts))
        return eq

    # -- convenience ----------------------------------------------------
    @property
    def n_open(self) -> int:
        return len(self.binary_positions) + len(self.perp_positions)

    def summary_dict(self) -> dict:
        """Quick scalar snapshot of portfolio state."""
        return {
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
            "total_fees": self.total_fees,
            "total_funding": self.total_funding,
            "n_open_binary": len(self.binary_positions),
            "n_open_perp": len(self.perp_positions),
            "n_closed": len(self.closed_trades),
            "equity_last": self.equity_curve[-1] if self.equity_curve else self.cash,
        }


__all__ = [
    "FeeFn",
    "default_fee_fn",
    "zero_fee_fn",
    "BinaryPosition",
    "PerpPosition",
    "TradeRecord",
    "Portfolio",
]
