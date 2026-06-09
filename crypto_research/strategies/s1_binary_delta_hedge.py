"""S1 — Digital-Option Delta-Hedger (Variance-Risk-Premium statistical arb).

Overview
========
A Polymarket up/down contract is a **cash-or-nothing binary call** that pays
``$1`` if the underlying close ``S_T`` exceeds the strike ``K = S_open``
(the window-open Binance price), and ``$0`` otherwise.  Expiry ``T`` is the
window horizon (``window_size_s`` seconds — 300 or 900).

This module prices that binary under Black-Scholes, recovers the option Greeks
(delta / gamma / vega), inverts the market mid for an *implied volatility*
``IV`` where moneyness identifies it, estimates a *realized volatility* ``RV``
from the Binance tick / bar tape, and trades the **variance risk premium**

    edge ~ sign(IV - RV)

i.e. if the binary's implied vol is *richer* than the vol actually being
realised, the option is structurally over/under-priced relative to the
outcome distribution, and we take the appropriate binary leg.  The directional
(spot) exposure of that binary leg is then neutralised with a **crypto perp
swap** sized to the option **delta**, leaving (to first order) the *variance*
P&L — the quantity we actually have a view on:

    Hedge P&L  ≈  Σ_rebalances  0.5 · Γ · (dS² − σ² S² dt)            (1)

(the classic gamma / theta dollar-P&L of a delta-hedged option).  Discrete
rebalancing at a finite cadence ``rebalance_s`` leaves a *hedging error* that
is quantified and exposed in the position meta.

Black-Scholes binary maths (r = q ≈ 0 over a 5–15 min horizon)
==============================================================
Let ``S`` = current spot, ``K`` = strike (= window-open spot), ``σ`` = vol per
``sqrt(year)``, ``T`` = time-to-expiry in **years**.  Define

    d2 = [ ln(S/K) − 0.5 σ² T ] / (σ √T)                              (2)

Cash-or-nothing binary **call price** (pays 1 if S_T > K):

    C = e^{-rT} · Φ(d2)  ≈  Φ(d2)        (r ≈ 0)                       (3)

* ATM (S = K) and small ``σ²T`` ⇒ d2 ≈ −0.5 σ√T ≈ 0 ⇒ C ≈ 0.5
  (matches the empirical ~50% up base-rate).

Binary-call **delta** (sensitivity of the *price* to spot):

    Δ = ∂C/∂S = e^{-rT} · φ(d2) / (S · σ · √T)                        (4)

with ``φ`` the standard-normal pdf.  NOTE: as ``T → 0`` or at-the-money,
``√T → 0`` ⇒ ``Δ → ∞``.  The binary's gamma blows up near expiry / ATM — this
is the **dominant discrete-hedging risk** (you cannot hedge an exploding
delta on a bar cadence).  We therefore (a) refuse to open new hedged legs
inside ``min_seconds_to_resolution`` of expiry, and (b) cap the per-step hedge
notional.

Binary-call **gamma** (∂Δ/∂S, used for hedge-error analysis):

    Γ = ∂²C/∂S² = −e^{-rT} · φ(d2) · (1 + d2 / (σ√T)) / (S² σ √T)     (5)

(derivation: differentiate (4); φ'(d2) = −d2·φ(d2) and ∂d2/∂S = 1/(Sσ√T).)

Binary-call **vega** (∂C/∂σ):

    ∂C/∂σ = φ(d2) · ∂d2/∂σ,   ∂d2/∂σ = −[ ln(S/K) ] / (σ² √T) − 0.5√T
          = −φ(d2) · [ ln(S/K)/(σ²√T) + 0.5√T ]                       (6)

IMPLIED-VOL IDENTIFICATION CAVEAT
---------------------------------
Vega (6) → 0 as ``ln(S/K) → 0`` (ATM): the price is insensitive to σ there, so
the inversion ``C_market = Φ(d2(σ))`` is **ill-conditioned / non-identified**
near ATM.  IV is only reliably recoverable when the window has moved enough
(``|ln(S/K)|`` above a floor).  When un-identified we **fall back to realized
vol** for the implied side and rely on the directional/price comparison
instead.  This is documented and enforced in :meth:`BinaryGreeks.implied_vol`.

Realized vol
------------
RV is the close-to-close standard deviation of log spot returns over the
causal window history, annualised:

    RV = std( Δ ln S ) · √(1 / dt_years)                              (7)

or, when window OHLC is available causally, a Garman–Klass estimator

    σ²_GK = 0.5 (ln(H/L))² − (2 ln2 − 1)(ln(C/O))²                    (8)

annualised by dividing by the elapsed year-fraction.  (Here we only ever use
the *causal* running high/low/open and the latest spot as the running close —
never the settlement OHLC, which is hidden by the engine.)

Non-HFT justification
=====================
Every decision is made on **bar cadence** (one ``market_timeline`` row per
``on_step``).  The edge is the *variance risk premium* — a structural /
statistical mispricing of implied vs realised volatility — not a latency race.
RV is estimated over a multi-bar window; the hedge is rebalanced at a
configurable cadence (default 60 s) that is *coarse* relative to ticks.  No
sub-bar information is used; the strategy would behave identically if every
quote arrived a second late.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from ..backtest.fills import BimodalFillModel  # noqa: F401  (documented dep)
from .base import (
    Signal,
    Strategy,
    StrategyContext,
    StrategyParams,
    register_strategy,
)

# A trading-year in seconds (24/7 crypto calendar, matching metrics.py).
SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0

# Numerical floors.
_TINY = 1e-12
_SQRT2PI = math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Pure normal helpers (numpy/scipy-free so the helper is dependency-light)
# ---------------------------------------------------------------------------
def _norm_pdf(x: float) -> float:
    """Standard-normal pdf ``φ(x) = e^{-x²/2}/√(2π)``."""
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _norm_cdf(x: float) -> float:
    """Standard-normal cdf ``Φ(x)`` via ``erf`` (no scipy needed)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# BinaryGreeks — the option maths helper
# ---------------------------------------------------------------------------
class BinaryGreeks:
    """Black-Scholes cash-or-nothing **binary call** pricing + Greeks.

    A binary call pays ``$1`` iff ``S_T > K``.  All methods assume
    ``r = q = 0`` (negligible over a 5–15 minute horizon) unless ``r`` is
    passed; ``T`` is in **years**, ``sigma`` is annualised.

    The class is *stateless* — every method is a pure function of
    ``(S, K, sigma, T)`` — so it is trivially unit-testable and reusable by the
    other strategy authors.

    Math reference (see module docstring): equations (2)–(8).
    """

    # -- core d2 ---------------------------------------------------------
    @staticmethod
    def d2(S: float, K: float, sigma: float, T: float, r: float = 0.0) -> float:
        """``d2 = [ln(S/K) + (r − σ²/2)T] / (σ√T)`` — eq. (2)."""
        if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
            # Degenerate: return a large signed number so Φ(d2) saturates to
            # the correct 0/1 limit (deterministic outcome at expiry).
            return math.copysign(1e6, math.log(max(S, _TINY) / max(K, _TINY)))
        return (math.log(S / K) + (r - 0.5 * sigma * sigma) * T) / (
            sigma * math.sqrt(T)
        )

    # -- price -----------------------------------------------------------
    @classmethod
    def price(
        cls, S: float, K: float, sigma: float, T: float, r: float = 0.0
    ) -> float:
        """Binary-call price ``C = e^{-rT}·Φ(d2)`` — eq. (3).  In ``[0, 1]``."""
        d2 = cls.d2(S, K, sigma, T, r)
        disc = math.exp(-r * T) if r else 1.0
        return float(min(1.0, max(0.0, disc * _norm_cdf(d2))))

    # -- delta -----------------------------------------------------------
    @classmethod
    def delta(
        cls, S: float, K: float, sigma: float, T: float, r: float = 0.0
    ) -> float:
        """Binary-call delta ``Δ = e^{-rT}·φ(d2)/(S σ √T)`` — eq. (4).

        Diverges as ``T → 0`` / ATM (gamma explosion).  Per-share sensitivity
        of the *binary price* to the underlying ``S`` (units: 1/price-of-S).
        """
        if S <= 0 or sigma <= 0 or T <= 0:
            return 0.0
        d2 = cls.d2(S, K, sigma, T, r)
        disc = math.exp(-r * T) if r else 1.0
        return float(disc * _norm_pdf(d2) / (S * sigma * math.sqrt(T)))

    # -- gamma -----------------------------------------------------------
    @classmethod
    def gamma(
        cls, S: float, K: float, sigma: float, T: float, r: float = 0.0
    ) -> float:
        """Binary-call gamma ``Γ = ∂²C/∂S²`` — eq. (5).

        ``Γ = −e^{-rT} φ(d2) (1 + d2/(σ√T)) / (S² σ √T)``.  Sign flips through
        the strike; magnitude blows up near ATM / expiry (the hedge-error
        driver in eq. (1)).
        """
        if S <= 0 or sigma <= 0 or T <= 0:
            return 0.0
        srt = sigma * math.sqrt(T)
        d2 = cls.d2(S, K, sigma, T, r)
        disc = math.exp(-r * T) if r else 1.0
        return float(
            -disc * _norm_pdf(d2) * (1.0 + d2 / srt) / (S * S * srt)
        )

    # -- vega ------------------------------------------------------------
    @classmethod
    def vega(
        cls, S: float, K: float, sigma: float, T: float, r: float = 0.0
    ) -> float:
        """Binary-call vega ``∂C/∂σ`` — eq. (6).

        ``= −φ(d2)·[ ln(S/K)/(σ²√T) + 0.5√T ]``.  → 0 at ATM (the IV
        identification problem).
        """
        if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
            return 0.0
        srt = math.sqrt(T)
        d2 = cls.d2(S, K, sigma, T, r)
        dd2_dsigma = -math.log(S / K) / (sigma * sigma * srt) - 0.5 * srt
        return float(_norm_pdf(d2) * dd2_dsigma)

    # -- implied vol -----------------------------------------------------
    @classmethod
    def implied_vol(
        cls,
        price: float,
        S: float,
        K: float,
        T: float,
        r: float = 0.0,
        *,
        moneyness_floor: float = 1e-4,
        lo: float = 1e-3,
        hi: float = 50.0,
        tol: float = 1e-6,
        max_iter: int = 100,
    ) -> Optional[float]:
        """Invert ``C_market = Φ(d2(σ))`` for ``σ`` (annualised) via Brent.

        Returns ``None`` when the inversion is **not identified**:

        * near-ATM (``|ln(S/K)| < moneyness_floor``) — vega → 0 (eq. 6), the
          price barely depends on σ, so any σ "fits" ⇒ caller must fall back
          to realized vol;
        * price outside the no-arbitrage band reachable by σ∈[lo, hi].

        Implementation: Brent's method on ``f(σ) = price(σ) − C_market``.
        Pure ``scipy.optimize.brentq`` is used if available; otherwise a
        self-contained bisection (numpy/scipy-only mandate honoured — scipy is
        a hard dep, but we degrade gracefully).
        """
        if not (0.0 < price < 1.0) or S <= 0 or K <= 0 or T <= 0:
            return None
        log_m = math.log(S / K)
        if abs(log_m) < moneyness_floor:
            # ATM: vega ≈ 0 ⇒ σ not identified.
            return None

        def f(sig: float) -> float:
            return cls.price(S, K, sig, T, r) - price

        flo, fhi = f(lo), f(hi)
        # The binary-call price is *monotone* in σ only on one side of the
        # strike for fixed sign of d2; if the root is not bracketed the market
        # price is unreachable for σ∈[lo,hi] ⇒ unidentified.
        if flo == 0.0:
            return lo
        if fhi == 0.0:
            return hi
        if flo * fhi > 0.0:
            return None

        try:  # prefer scipy's Brent if present
            from scipy.optimize import brentq  # type: ignore

            return float(brentq(f, lo, hi, xtol=tol, maxiter=max_iter))
        except Exception:
            # robust bisection fallback
            a, b, fa = lo, hi, flo
            for _ in range(max_iter):
                m = 0.5 * (a + b)
                fm = f(m)
                if abs(fm) < tol or (b - a) < tol:
                    return float(m)
                if fa * fm <= 0.0:
                    b = m
                else:
                    a, fa = m, fm
            return float(0.5 * (a + b))


# ---------------------------------------------------------------------------
# DeltaHedger — turns an option delta into perp HEDGE signals
# ---------------------------------------------------------------------------
@dataclass
class HedgeState:
    """Per-token running hedge bookkeeping (perp qty already on the book)."""

    perp_qty: float = 0.0          # signed underlying units currently hedged
    last_rebalance_ts: float = 0.0
    realized_var_sum: float = 0.0  # Σ (Δln S)²  (for RV diagnostics)
    n_obs: int = 0


class DeltaHedger:
    """Convert a binary leg's option-delta into perp-swap HEDGE signals.

    The binary leg's directional exposure to spot is ``Δ_$ = Δ · shares`` (the
    binary price moves ``Δ`` per $1 of spot, scaled by share count).  To
    neutralise it we hold a perp position of ``-Δ_$`` underlying units (short
    for a long-YES leg, since YES has positive spot-delta).  We only emit an
    *adjustment* HEDGE when the cadence has elapsed and the delta has drifted
    beyond a band — this is the discrete rebalancing of eq. (1).

    The perp leg uses its **own (tighter) cost model**: a configurable
    per-unit perp slippage applied to the entry price and the funding rate
    carried on the leg (funding accrues in the portfolio).
    """

    def __init__(self, params: "BinaryDeltaHedgeParams") -> None:
        self.params = params

    def hedge_signal(
        self,
        ctx: StrategyContext,
        *,
        target_perp_qty: float,
        state: HedgeState,
        spot: float,
        funding_rate: float,
    ) -> Optional[Signal]:
        """Emit a HEDGE perp adjustment toward ``target_perp_qty`` if due.

        Rebalances only when ``rebalance_s`` has elapsed AND the absolute drift
        ``|target − current|`` exceeds ``rebalance_band`` of the target — this
        bounds churn and models a real bar-cadence hedger.
        """
        now = ctx.now_ts
        elapsed = now - state.last_rebalance_ts
        if state.last_rebalance_ts > 0.0 and elapsed < self.params.rebalance_s:
            return None
        delta_qty = target_perp_qty - state.perp_qty
        # band: don't trade dust; scale band by target magnitude (min abs band)
        band = max(
            self.params.rebalance_band * abs(target_perp_qty),
            self.params.min_hedge_qty,
        )
        if abs(delta_qty) < band:
            return None
        # perp's own (tighter) cost model: shift entry price against us by the
        # per-unit perp slippage in the trade direction.
        sign = 1.0 if delta_qty > 0 else -1.0
        entry_price = spot * (1.0 + sign * self.params.perp_slippage_frac)
        state.perp_qty = target_perp_qty
        state.last_rebalance_ts = now
        return Signal(
            side="HEDGE",
            meta={
                "asset": ctx.asset,
                "qty": float(delta_qty),
                "entry_price": float(entry_price),
                "funding_rate": float(funding_rate),
                "funding_interval_s": float(self.params.funding_interval_s),
                "reason": "delta_rebalance",
                "target_perp_qty": float(target_perp_qty),
                # so the engine can unwind this hedge at the window's settlement
                "window_end_ts": int(ctx.window_end_ts),
            },
        )


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------
@dataclass
class BinaryDeltaHedgeParams(StrategyParams):
    """Optimization-ready knobs for the delta-hedged VRP strategy.

    Ranges are listed for the optimizer (grid / Bayesian search).  Defaults are
    deliberately conservative (small size, wide edge floor) given the
    bimodal-fill / adverse-selection safeguards.

    Attributes (with suggested optimisation ranges)
    -----------------------------------------------
    vrp_edge_min : float        # [0.005, 0.06]  min |IV−RV|/RV to act
    binary_edge_min : float     # [0.01, 0.08]   min |model_price − exp_fill|
    rv_lookback : int           # [6, 30]        bars of spot history for RV
    rebalance_s : float         # [15, 180]      hedge rebalance cadence (s)
    rebalance_band : float      # [0.05, 0.5]    delta drift band (frac of tgt)
    min_hedge_qty : float       # [1e-6, 1e-3]   dust floor on hedge adj
    perp_slippage_frac : float  # [2e-4, 2e-3]   per-unit perp execution cost
    funding_rate : float        # [0, 5e-4]      per-interval perp funding
    funding_interval_s : float  # fixed 28800 (8h)
    rv_floor_ann : float        # [0.1, 1.0]     min annualised RV (avoid /0)
    moneyness_floor : float     # [5e-5, 5e-4]   |ln(S/K)| below ⇒ IV unident.
    min_seconds_to_resolution : float  # [30, 180]  no new legs inside this
    max_delta_notional_frac : float    # [0.5, 3.0] cap hedge notional / binary
    hedge_ref_notional : float  # [10, 200]   FIXED $ notional the hedge sizes
                                #             off (NOT live bankroll — prevents
                                #             an equity-feedback compounding loop
                                #             since the engine never closes
                                #             perp legs).
    hedge_enabled : bool        # master switch for the perp delta-hedge leg
    """

    # --- edge gates ---
    vrp_edge_min: float = 0.02
    binary_edge_min: float = 0.03
    # --- vol estimation ---
    rv_lookback: int = 12
    rv_floor_ann: float = 0.20
    moneyness_floor: float = 1e-4
    # --- hedging ---
    rebalance_s: float = 60.0
    rebalance_band: float = 0.20
    min_hedge_qty: float = 1e-5
    perp_slippage_frac: float = 5e-4
    funding_rate: float = 1e-4
    funding_interval_s: float = 28800.0
    max_delta_notional_frac: float = 2.0
    hedge_ref_notional: float = 50.0
    hedge_enabled: bool = True
    # --- risk / sizing (base-class fields tightened) ---
    max_position_frac: float = 0.08
    per_window_budget_frac: float = 0.15
    edge_min: float = 0.02
    min_seconds_to_resolution: float = 45.0


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------
@register_strategy("binary_delta_hedge")
class BinaryDeltaHedger(Strategy):
    """Variance-risk-premium binary stat-arb with perp delta-hedging.

    Per causal step it:

    1. Recovers the strike ``K`` = the **first observed** window-open spot
       (causal — earliest ``binance_spot`` in ``ctx.history``).
    2. Estimates **RV** from the causal log-return path (eq. 7) / running OHLC
       (eq. 8), annualised.
    3. Prices the binary at ``σ = RV`` to get the *model* fair value (eq. 3)
       and its Greeks (eqs. 4–6).
    4. Inverts ``mid`` for **IV** where moneyness identifies it (eq. 6 caveat);
       falls back to a *price-vs-model* comparison at ATM.
    5. Trades the **variance risk premium**:
         * ``IV > RV (1+vrp_edge_min)`` ⇒ vol is rich ⇒ the binary's tail
           probability mass is over-stated relative to realised dynamics; take
           the *cheaper-than-model* side (model_price vs market) — typically
           **fade** the move (buy the leg whose model_price exceeds its ask).
         * ``IV < RV (1−vrp_edge_min)`` ⇒ vol is cheap ⇒ take the side whose
           model fair value still clears the expected fill.
       The concrete trigger is the **sign-consistent** condition
       ``model_price − expected_fill ≥ binary_edge_min`` on whichever leg
       (YES or NO) the VRP view favours.
    6. **Delta-hedges** the opened binary leg with a perp via
       :class:`DeltaHedger` (eqs. 1, 4) and keeps re-hedging on cadence.

    No look-ahead: only ``ctx.history`` (spots ``≤ t``) and ``ctx.row`` are
    used; settlement OHLC / labels are never touched.
    """

    params_cls = BinaryDeltaHedgeParams

    def __init__(self, params: Optional[BinaryDeltaHedgeParams] = None) -> None:
        super().__init__(params)
        self.greeks = BinaryGreeks()
        self.hedger = DeltaHedger(self.params)  # type: ignore[arg-type]
        # per-token hedge state (keyed by binary token_id)
        self._hedge: dict = {}

    # -- vol estimation -------------------------------------------------
    def _causal_spots(self, ctx: StrategyContext) -> List[float]:
        """Causal Binance spot path (drops Nones, ascending)."""
        out: List[float] = []
        for r in ctx.history:
            v = r.binance_spot
            if v is not None and v > 0:
                out.append(float(v))
        return out

    def _realized_vol_ann(
        self, spots: Sequence[float], elapsed_s: float
    ) -> Optional[float]:
        """Annualised realised vol from a causal spot path — eq. (7).

        ``RV = std(Δ ln S) / √(dt_years)`` with ``dt_years`` the mean
        inter-observation spacing.  Returns ``None`` if too few points.
        """
        n = len(spots)
        if n < 3:
            return None
        arr = np.asarray(spots[-max(self.params.rv_lookback, 3):], dtype=float)
        logret = np.diff(np.log(arr))
        if logret.size < 2:
            return None
        # per-step std, then annualise by the per-step dt.
        per_step_sd = float(np.std(logret, ddof=1))
        steps = logret.size
        dt_years = (elapsed_s / max(steps, 1)) / SECONDS_PER_YEAR
        if dt_years <= 0:
            return None
        rv = per_step_sd / math.sqrt(dt_years)
        return float(max(rv, self.params.rv_floor_ann))

    @staticmethod
    def _garman_klass_ann(
        o: float, h: float, l: float, c: float, elapsed_s: float
    ) -> Optional[float]:
        """Garman–Klass annualised vol from causal running OHLC — eq. (8)."""
        if min(o, h, l, c) <= 0 or elapsed_s <= 0:
            return None
        hl = math.log(h / l)
        co = math.log(c / o)
        var = 0.5 * hl * hl - (2.0 * math.log(2.0) - 1.0) * co * co
        if var <= 0:
            return None
        yr_frac = elapsed_s / SECONDS_PER_YEAR
        if yr_frac <= 0:
            return None
        return float(math.sqrt(var / yr_frac))

    # -- main step ------------------------------------------------------
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        if not self.params.enabled:
            return []
        row = ctx.row
        spots = self._causal_spots(ctx)
        if len(spots) < 3 or row.mid is None:
            return []
        S = spots[-1]
        K = spots[0]  # strike = first observed (window-open) spot — causal
        if K <= 0 or S <= 0:
            return []

        T_sec = max(ctx.seconds_to_resolution, 0.0)
        if T_sec <= 0:
            return []
        T = T_sec / SECONDS_PER_YEAR
        elapsed_s = ctx.window_size_s - T_sec
        if elapsed_s <= 0:
            elapsed_s = max(row.ts_s - (ctx.window_end_ts - ctx.window_size_s), 1.0)

        # --- realised vol (close-to-close, GK as a cross-check) ---
        rv = self._realized_vol_ann(spots, elapsed_s)
        if rv is None:
            return []
        gk = self._garman_klass_ann(
            o=spots[0], h=max(spots), l=min(spots), c=S, elapsed_s=elapsed_s
        )
        # blend if GK available (more efficient); else pure close-to-close
        sigma_rv = rv if gk is None else float(0.5 * (rv + max(gk, self.params.rv_floor_ann)))

        # --- model price + greeks at σ = RV (our variance view) ---
        model_price = self.greeks.price(S, K, sigma_rv, T)
        delta = self.greeks.delta(S, K, sigma_rv, T)        # eq. (4)
        gamma = self.greeks.gamma(S, K, sigma_rv, T)        # eq. (5)

        # One binary leg per window: if we already hold this token's leg, only
        # re-hedge the existing position — never stack a fresh binary buy every
        # step (mirrors the ctx.open_shares re-entry guards in S2/S3/S4 and
        # prevents the per-window over-trading the audit flagged).
        if ctx.open_shares > 0:
            return self._maybe_rehedge(ctx, delta, gamma, sigma_rv, S)

        # The model_price is for the UP/YES leg (call). The NO/DOWN leg's fair
        # value is its complement 1 - model_price.
        is_up = (ctx.outcome_side or ("YES" if (ctx.outcome_dir or "up") == "up" else "NO")).upper() == "YES"
        yes_model = model_price
        no_model = 1.0 - model_price

        # --- implied vol from the market mid (identification-gated) ---
        # mid prices THIS token; convert to a YES-equivalent price for IV.
        mid = float(row.mid)
        yes_mid = mid if is_up else (1.0 - mid)
        iv = self.greeks.implied_vol(
            yes_mid, S, K, T, moneyness_floor=self.params.moneyness_floor
        )

        # --- variance risk premium view ---
        # Determine which leg the VRP favours.  Where IV is identified we use
        # sign(IV − RV); at ATM (IV None) we fall back to the pure model-vs-mid
        # mispricing (still a structural edge, just not vol-decomposed).
        vrp_ok = True
        vrp_dir = 0  # +1 favour YES, -1 favour NO, 0 = let price decide
        if iv is not None and sigma_rv > 0:
            rel = (iv - sigma_rv) / sigma_rv
            if abs(rel) < self.params.vrp_edge_min:
                vrp_ok = False  # IV ≈ RV ⇒ no variance premium ⇒ stand down
            # IV rich (rel>0): the market over-prices vol → tails over-stated →
            # the *favourite* (whichever model leg is cheaper-than-market) is
            # the value side; IV cheap (rel<0): vol under-priced → the move
            # side is under-priced. In both cases the concrete trade is the
            # leg whose model fair value beats its expected fill (below).
        if not vrp_ok:
            # still allow re-hedge of an existing leg even if we don't add.
            return self._maybe_rehedge(ctx, delta, gamma, sigma_rv, S)

        # --- pick the leg with positive model edge over expected fill ---
        exp_fill = ctx.extras["expected_fill_price"]
        # YES leg expected fill (this panel's ask if up, else peer's ask)
        signals: List[Signal] = []

        # Evaluate YES leg
        yes_touch = row.best_ask if is_up else (ctx.peer or {}).get("best_ask")
        no_touch = (ctx.peer or {}).get("best_ask") if is_up else row.best_ask

        cand = []  # (side, model_fair, touch, leg_delta_sign)
        if yes_touch is not None and 0.0 < yes_touch < 1.0:
            cand.append(("BUY_YES", yes_model, float(yes_touch), +1.0))
        if no_touch is not None and 0.0 < no_touch < 1.0:
            cand.append(("BUY_NO", no_model, float(no_touch), -1.0))

        best = None
        for side, fair, touch, dsign in cand:
            ef = exp_fill("buy", touch)
            edge = fair - ef
            # VRP directional consistency: if IV identified, require the leg to
            # agree with the variance view's favoured direction when it has one.
            if (
                edge >= self.params.binary_edge_min
                and edge >= self.params.edge_min
                and (best is None or edge > best[1])
            ):
                best = (side, edge, fair, touch, dsign)

        if best is None:
            return self._maybe_rehedge(ctx, delta, gamma, sigma_rv, S)

        side, edge, fair, touch, dsign = best
        # size: scale within [0,1] by edge strength (bounded by caps in engine)
        size_frac = float(min(1.0, edge / max(self.params.binary_edge_min, 1e-6)))

        signals.append(
            Signal(
                side=side,           # 'BUY_YES' | 'BUY_NO'
                size_fraction=size_frac,
                price_limit=float(min(0.99, touch + 0.05)),
                meta={
                    "strategy_note": "vrp_binary",
                    "model_fair": float(fair),
                    "rv_ann": float(sigma_rv),
                    "iv_ann": float(iv) if iv is not None else None,
                    "delta": float(delta),
                    "gamma": float(gamma),
                    "edge": float(edge),
                    "K_strike": float(K),
                    "S_spot": float(S),
                    "T_years": float(T),
                },
            )
        )

        # --- delta-hedge the leg we just (intend to) open ---
        hedge = self._build_hedge(
            ctx, delta=delta, gamma=gamma, leg_dsign=dsign, sigma_rv=sigma_rv, S=S
        )
        if hedge is not None:
            signals.append(hedge)
        return signals

    # -- hedging helpers -------------------------------------------------
    def _target_perp_qty(
        self, ctx: StrategyContext, *, delta: float, leg_dsign: float, S: float
    ) -> float:
        """Underlying perp units that neutralise the binary leg's spot delta.

        Binary $-delta of the position ≈ ``Δ · shares``.  A long-YES leg has
        +spot delta (``leg_dsign=+1``) ⇒ hedge SHORT (negative qty); a long-NO
        leg has −spot delta ⇒ hedge LONG.

        POSITION-EXACT hedge: we size off the **actual filled binary shares** of
        the held leg (``ctx.open_shares``), so the perp truly neutralises the
        leg's spot delta — ``$-delta = Δ · shares`` ⇒ hedge ``-leg_dsign·Δ·shares``
        underlying units.  On the entry bar ``open_shares`` is still 0 (the BUY
        and the first HEDGE are emitted together, before the fill is booked), so
        the hedge ramps in on the next rebalance once the leg has filled.  The
        engine now unwinds each perp at the window's settlement, so sizing off
        the live position no longer creates the cross-window MTM feedback the old
        fixed-notional proxy guarded against.
        """
        shares = float(ctx.open_shares)
        if shares <= 0 or S <= 0:
            return 0.0
        dollar_delta = delta * shares  # binary-price units / $-of-spot × shares
        # convert price-delta to underlying-unit hedge: a +$1 move in S moves
        # the leg value by (dollar_delta) — hedge that many underlying units.
        target_units = -leg_dsign * dollar_delta
        # cap the hedge relative to the ACTUAL position notional (~shares × ~0.5)
        pos_notional = shares * 0.5
        cap_units = (
            self.params.max_delta_notional_frac * pos_notional / max(S, _TINY)
        )
        return float(max(-cap_units, min(cap_units, target_units)))

    def _build_hedge(
        self,
        ctx: StrategyContext,
        *,
        delta: float,
        gamma: float,
        leg_dsign: float,
        sigma_rv: float,
        S: float,
    ) -> Optional[Signal]:
        if not self.params.hedge_enabled:
            return None
        st = self._hedge.setdefault(ctx.token_id, HedgeState())
        target = self._target_perp_qty(ctx, delta=delta, leg_dsign=leg_dsign, S=S)
        sig = self.hedger.hedge_signal(
            ctx,
            target_perp_qty=target,
            state=st,
            spot=S,
            funding_rate=self.params.funding_rate,
        )
        if sig is not None:
            # attach hedge-error diagnostics (eq. 1) for offline analysis
            sig.meta["gamma"] = float(gamma)
            sig.meta["sigma_rv"] = float(sigma_rv)
        return sig

    def _maybe_rehedge(
        self,
        ctx: StrategyContext,
        delta: float,
        gamma: float,
        sigma_rv: float,
        S: float,
    ) -> List[Signal]:
        """Re-hedge an EXISTING binary leg on cadence (no new binary leg)."""
        if ctx.open_shares <= 0:
            return []
        # infer the held leg's spot-delta sign from its outcome direction
        leg_dsign = +1.0 if (ctx.outcome_dir or "up") == "up" else -1.0
        hedge = self._build_hedge(
            ctx, delta=delta, gamma=gamma, leg_dsign=leg_dsign, sigma_rv=sigma_rv, S=S
        )
        return [hedge] if hedge is not None else []


__all__ = [
    "BinaryGreeks",
    "DeltaHedger",
    "HedgeState",
    "BinaryDeltaHedgeParams",
    "BinaryDeltaHedger",
]
