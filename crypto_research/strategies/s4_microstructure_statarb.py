"""S4 — Efficient-Price Stat-Arb with Adverse-Selection Immunization.

Designer's-choice synthesis.  Trades the gap between the Polymarket ``mid`` and
a microstructure-noise-corrected **fair probability** of the up/down window
resolving YES, and STANDS DOWN whenever order-flow toxicity is high so we are
never the adversely-selected counterparty.

================================================================================
BACKTEST HYPOTHESIS
================================================================================
During **low order-flow-toxicity** windows the Polymarket ``mid`` is a *noisy*
estimate of the true outcome probability.  A microstructure-noise-corrected
"efficient price" of the underlying (Binance spot), combined with a noise-robust
volatility, implies a **better-calibrated** ``P_fair(up)`` than the raw
binary's ``mid``.  The signed gap ``g = mid - P_fair`` is a *mispricing* that
**reverts toward 0 by window close** (the binary must settle at the realised
outcome distribution).  We buy the cheap side of that gap.  When toxicity (VPIN)
is high, informed flow is present: the gap is more likely *information* than
*noise*, so we stand down — converting an adverse-selection liability into a
filter.  Edge = calibration + minutes-scale mean-reversion + a toxicity
stand-down.  NOT latency.

================================================================================
MATH CORE — FOUR PILLARS (+ optional EVT tail overlay)
================================================================================

PILLAR 1 — MICROSTRUCTURE NOISE -> EFFICIENT PRICE
--------------------------------------------------
(Hasbrouck 1993; Aït-Sahalia, Mykland & Zhang 2005.)  An observed tick price
decomposes as

    p_obs(t) = p_star(t) + eta(t),     eta ~ N(0, sigma_eta^2)            (1)

where ``p_star`` is the latent **efficient price** and ``eta`` is i.i.d.
microstructure noise (bid-ask bounce, discreteness, order-flow).  Model
``p_star`` as a random walk and ``p_obs`` as a noisy measurement — a *local-level
state-space model* — and recover ``p_star`` with a scalar **Kalman filter**:

    state:        p_star(t) = p_star(t-1) + w(t),   w ~ N(0, q)          (2a)
    measurement:  p_obs(t)  = p_star(t)  + eta(t),  eta ~ N(0, r)        (2b)

Kalman recursion (predict / update), with prior variance ``P``:

    P_pred   = P + q                                                      (3a)
    K_gain   = P_pred / (P_pred + r)            (Kalman gain in [0,1])     (3b)
    p_star  += K_gain * (p_obs - p_star)        (innovation update)       (3c)
    P        = (1 - K_gain) * P_pred                                       (3d)

The steady-state gain depends only on the **signal-to-noise ratio** ``q/r``:

    K_ss = ( -(q/r) + sqrt((q/r)^2 + 4 q/r) ) / 2                          (4)

Small ``q/r`` (lots of noise) ⇒ small gain ⇒ heavy smoothing.  We estimate
``q`` and ``r`` once per window from the tick tape (see ``estimate_qr``):
``r`` ≈ half the lag-0 vs lag-1 variance structure of noise, ``q`` ≈ the
noise-robust signal variance (TSRV, pillar-1b).

PILLAR 1b — TWO-SCALES REALIZED VOLATILITY (TSRV)
-------------------------------------------------
(Zhang, Mykland & Aït-Sahalia 2005.)  Naive realized variance over ``n`` ticks
is biased UP by microstructure noise:

    RV_all  = Σ (Δp_obs)^2  ->  RV_star + 2 n sigma_eta^2   (noise term)   (5)

TSRV removes the bias by combining an *all-ticks* estimator with a *sparse,
subsampled-and-averaged* estimator:

    TSRV = RV_avg(K) - (n_bar / n) * RV_all                                (6)

where ``RV_avg(K)`` averages ``K`` subsampled RVs (every K-th tick), ``n`` is
the number of all-tick returns and ``n_bar = (n - K + 1)/K``.  TSRV is a
consistent, noise-robust estimator of integrated variance; ``sigma`` per
sqrt(time) follows by annualising.  As a by-product we recover the noise level

    sigma_eta^2 = RV_all / (2 n)                                           (7)

which feeds the Kalman ``r`` (eq. 2b).

PILLAR 2 — FAIR PROBABILITY (Gaussian / endpoint formula)
---------------------------------------------------------
The window resolves YES iff close ``S_T > K`` with strike ``K`` = window-open
spot.  Under a driftless Gaussian terminal law for log-spot with efficient
current level ``S_star`` and noise-robust vol ``sigma`` over remaining time
``tau`` (year-fraction):

    x      = ln(S_star / K)                  (efficient log-moneyness)     (8)
    P_fair = Phi( (x + mu*tau) / (sigma * sqrt(tau)) )                     (9)

(``mu`` is an optional drift, default 0 over a 5–15 min horizon; this is the
binary-call price with r=q=0, identical to S1 eq. (3) but evaluated at the
*efficient* spot rather than the raw last tick — the whole point of pillar 1).

PILLAR 3 — GAME THEORY / ADVERSE-SELECTION STAND-DOWN (VPIN)
-----------------------------------------------------------
(Easley, López de Prado & O'Hara 2012 — VPIN; Kyle 1985 — lambda; PIN.)
**Volume-synchronised Probability of INformed trading**.  Classify each volume
bucket's buy/sell split via *bulk-volume classification* (BVC): the buy fraction
of bucket volume is ``Phi(Δp / (sigma_p * z))`` from the standardised price
change over the bucket.  Then

    VPIN = (1/N) * Σ_b |V_buy(b) - V_sell(b)| / V(b)                      (10)

VPIN ∈ [0,1] rises with order-flow imbalance = informed trading.  GAME-THEORETIC
RATIONALE: a market maker (us, taking the structural side) loses to *informed*
counterparties (Glosten-Milgrom adverse selection).  When VPIN is high the
flow is informed → the ``mid`` gap is *information, not noise* → DO NOT TRADE
AGAINST THE INFORMED.  We only act when ``VPIN < q-quantile`` of its rolling
distribution (low toxicity), and we KILL/early-exit when VPIN spikes above a
higher kill quantile.  This is the adverse-selection *immunization*.

PILLAR 4 — INFORMATION-ENTROPY SIZING (KL divergence + fractional Kelly)
-----------------------------------------------------------------------
Signal strength = the information gain of ``P_fair`` over the market prior
``mid``, the binary Kullback-Leibler divergence

    D_KL(P_fair || mid) = P_fair*ln(P_fair/mid)
                          + (1-P_fair)*ln((1-P_fair)/(1-mid))             (11)

(nats; how many nats our posterior adds over the book's prior).  Position size
∝ D_KL, scaled by the toxicity-confidence ``(1 - vpin_percentile)`` (size up
only when flow is benign), and capped by **fractional Kelly** on the modelled
binary edge:

    f_kelly = clip( (P_win - price) / (1 - price), 0, 1 )                 (12)
    size_fraction = clip( kelly_frac * f_kelly
                          * tanh(kl_gain * D_KL)
                          * (1 - vpin_pct), 0, 1 )                        (13)

EVT TAIL OVERLAY (optional, documented)
---------------------------------------
The Gaussian (eq. 9) under-prices tails; near 0/1 strikes that biases
calibration.  We fit a **Generalized Pareto Distribution** (GPD) to the tail of
spot log-returns by *peaks-over-threshold* (Pickands-Balkema-de Haan): for
exceedances ``y = (r - u)`` above a high threshold ``u``,

    P(R - u > y | R > u) = (1 + xi * y / beta)^(-1/xi)   (xi != 0)       (14)

with shape ``xi`` and scale ``beta`` fit by probability-weighted moments (no
statsmodels needed).  The tail probability of crossing the strike is then a
blend of the Gaussian body and the GPD tail, nudging ``P_fair`` toward better
extreme-strike calibration.  OFF by default (``use_evt_tail=False``) — it only
binds for far-from-ATM windows and needs enough ticks to fit.

================================================================================
ENTRY / EXIT
================================================================================
ENTRY (open a leg):
    * compute efficient spot ``S_star`` (Kalman, eq. 3), ``sigma`` (TSRV, eq. 6),
      ``P_fair`` (eq. 9, optionally EVT-corrected), ``VPIN`` (eq. 10),
    * require ``VPIN < vpin_entry_q`` quantile (low toxicity, pillar 3),
    * require ``|P_fair - mid| > theta_entry`` (the gap, pillar 1+2),
    * BUY the CHEAP side:  P_fair > mid + theta ⇒ BUY_YES ; P_fair < mid - theta
      ⇒ BUY_NO,
    * but only if the modelled edge clears the **expected fill** (bimodal-fill
      penalty + slippage) and ``edge_min`` (ruin floor),
    * size by entropy/Kelly (eq. 13).

EXIT (close this strategy's leg early, else hold to resolution):
    * ``|P_fair - mid| < theta_exit``  (gap reverted — take the convergence), OR
    * ``VPIN > vpin_kill_q``           (toxicity spike — informed flow arrived), OR
    * window resolution                (engine settles automatically).

================================================================================
NON-HFT JUSTIFICATION
================================================================================
Every decision is on **bar cadence** (one ``market_timeline`` row per
``on_step``).  The Kalman efficient price, TSRV, and VPIN are all estimated over
a *multi-bar / multi-bucket* causal history; the edge is a *statistical
mispricing* of ``mid`` vs a noise-corrected fair value that **reverts over
minutes**, gated by a *structural* adverse-selection filter.  Nothing here is a
latency race: the strategy would behave identically if every quote and tick
arrived a second late — it consumes *aggregates over a bar*, never the leading
edge of the tape.  This is the antithesis of HFT: we deliberately *avoid* being
fast against informed flow (pillar 3) rather than trying to out-run it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..backtest.fills import BimodalFillModel  # noqa: F401  (documented dep)
from .base import (
    Signal,
    Strategy,
    StrategyContext,
    StrategyParams,
    register_strategy,
)

# 24/7 crypto trading-year in seconds (matches metrics.py annualiser).
SECONDS_PER_YEAR: float = 365.0 * 24.0 * 60.0 * 60.0
_SQRT_2: float = math.sqrt(2.0)
_EPS: float = 1e-12


# ===========================================================================
# Small numerics — standard-normal CDF (no scipy dependency in the hot path)
# ===========================================================================
def norm_cdf(x: float) -> float:
    """Standard-normal CDF ``Phi(x)`` via the error function (scipy-free).

    ``Phi(x) = 0.5 * (1 + erf(x / sqrt(2)))``.  Uses :func:`math.erf` so the
    per-step pricing path has no scipy dependency (scipy is still a hard dep of
    the package, but the hot loop stays pure-stdlib/numpy).
    """
    if not math.isfinite(x):
        return 1.0 if x > 0 else 0.0
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


# ===========================================================================
# PILLAR 1 — Kalman efficient price (local-level state-space filter)
# ===========================================================================
@dataclass
class KalmanState:
    """Posterior state of the scalar local-level Kalman filter.

    Attributes
    ----------
    p_star
        Current efficient-price estimate (eq. 3c).
    P
        Posterior state variance (eq. 3d).
    initialised
        Whether the first measurement has been ingested.
    """

    p_star: float = 0.0
    P: float = 1.0
    initialised: bool = False


class KalmanEfficientPrice:
    """Local-level Kalman filter extracting the efficient price ``p_star``.

    State-space model (eqs. 2a/2b):

        p_star(t) = p_star(t-1) + w(t),   w ~ N(0, q)     (random-walk state)
        p_obs(t)  = p_star(t)  + eta(t),  eta ~ N(0, r)   (noisy measurement)

    The recursion (eqs. 3a-3d) is a scalar Kalman filter whose steady-state gain
    depends only on the signal-to-noise ratio ``q/r`` (eq. 4).  Larger noise
    ``r`` ⇒ smaller gain ⇒ heavier smoothing ⇒ a cleaner efficient price.

    Parameters
    ----------
    q
        State (signal) variance — how fast the efficient price drifts.
    r
        Measurement (noise) variance — the microstructure-noise level.
    """

    def __init__(self, q: float, r: float) -> None:
        self.q: float = float(max(q, _EPS))
        self.r: float = float(max(r, _EPS))
        self.state = KalmanState()

    @property
    def steady_state_gain(self) -> float:
        """Closed-form steady-state Kalman gain ``K_ss`` (eq. 4)."""
        ratio = self.q / self.r
        return 0.5 * (-ratio + math.sqrt(ratio * ratio + 4.0 * ratio))

    def update(self, p_obs: float) -> float:
        """Ingest one observed price, return the updated efficient price.

        Implements the predict/update recursion (eqs. 3a-3d).  The first
        observation initialises the state at the measurement.
        """
        st = self.state
        if not st.initialised:
            st.p_star = float(p_obs)
            st.P = self.r  # start at measurement-noise scale
            st.initialised = True
            return st.p_star
        P_pred = st.P + self.q                       # (3a)
        gain = P_pred / (P_pred + self.r)            # (3b) Kalman gain in [0,1]
        st.p_star = st.p_star + gain * (p_obs - st.p_star)   # (3c)
        st.P = (1.0 - gain) * P_pred                 # (3d)
        return st.p_star

    def filter_series(self, prices: Sequence[float]) -> float:
        """Run the filter over a price series, return the final ``p_star``.

        Stateless convenience: builds a fresh filter, ingests ``prices`` in
        order, and returns the terminal efficient price.  Used per-step over the
        causal spot history so there is no carried-state leakage between windows.
        """
        self.state = KalmanState()
        last = float("nan")
        for p in prices:
            if p is None or not math.isfinite(float(p)):
                continue
            last = self.update(float(p))
        return last


def estimate_qr(
    prices: Sequence[float],
    *,
    r_floor: float = 1e-10,
    q_floor: float = 1e-12,
) -> Tuple[float, float]:
    """Estimate Kalman ``(q, r)`` from a price series, noise-robustly.

    ``r`` (microstructure-noise variance) is estimated from the **negative lag-1
    autocovariance** of first differences: pure i.i.d. noise on a random-walk
    signal induces ``Cov(Δp_t, Δp_{t-1}) = -sigma_eta^2`` (the bid-ask-bounce
    signature, Roll 1984).  ``q`` (signal variance) is the *noise-corrected*
    variance of differences: ``Var(Δp) - 2 sigma_eta^2``, floored positive.

    Returns
    -------
    (q, r)
        State and measurement variances for :class:`KalmanEfficientPrice`.
    """
    p = np.asarray([x for x in prices if x is not None and math.isfinite(float(x))], dtype=float)
    if p.size < 4:
        return q_floor, r_floor
    d = np.diff(p)
    if d.size < 3:
        return q_floor, max(float(np.var(d)) if d.size else r_floor, r_floor)
    # lag-1 autocovariance of differences; -gamma1 ~ sigma_eta^2 for noisy RW
    gamma1 = float(np.mean((d[1:] - d.mean()) * (d[:-1] - d.mean())))
    sigma_eta2 = max(-gamma1, r_floor)
    var_d = float(np.var(d))
    q = max(var_d - 2.0 * sigma_eta2, q_floor)
    r = max(sigma_eta2, r_floor)
    return q, r


# ===========================================================================
# PILLAR 1b — Two-Scales Realized Volatility (TSRV)
# ===========================================================================
def tsrv_sigma(
    prices: Sequence[float],
    *,
    dt_seconds: float,
    K: int = 5,
    annualise: bool = True,
    floor: float = 1e-8,
) -> float:
    """Two-Scales Realized Volatility estimator of ``sigma`` (per sqrt(time)).

    Naive realized variance is biased UP by microstructure noise (eq. 5).  TSRV
    (Zhang-Mykland-Aït-Sahalia 2005, eq. 6) debiases it by subtracting a scaled
    all-ticks RV from a subsampled-averaged RV:

        TSRV = RV_avg(K) - (n_bar / n) * RV_all,    n_bar = (n - K + 1)/K

    Parameters
    ----------
    prices
        Tick/bar price series (log-returns taken internally).
    dt_seconds
        Average seconds between successive observations (for annualisation).
    K
        Subsampling stride (number of sparse grids averaged).
    annualise
        If True, scale variance to per-year then take sqrt → annual sigma.
    floor
        Lower clip on the returned sigma (avoids divide-by-zero downstream).

    Returns
    -------
    sigma
        Noise-robust volatility (annualised if ``annualise``), >= ``floor``.
    """
    p = np.asarray([x for x in prices if x is not None and float(x) > 0 and math.isfinite(float(x))], dtype=float)
    if p.size < max(2 * K, 4):
        # too few ticks for TSRV → fall back to naive RV (still better than 0).
        if p.size < 2:
            return floor
        lr = np.diff(np.log(p))
        rv = float(np.sum(lr * lr))
        per_sec_var = rv / max((p.size - 1) * dt_seconds, _EPS)
        var = per_sec_var * (SECONDS_PER_YEAR if annualise else 1.0)
        return max(math.sqrt(max(var, 0.0)), floor)

    logp = np.log(p)
    lr = np.diff(logp)
    n = lr.size
    rv_all = float(np.sum(lr * lr))                       # all-ticks RV

    # subsampled-and-averaged RV over K sparse grids
    rv_sub = []
    for start in range(K):
        sub = logp[start::K]
        if sub.size >= 2:
            dl = np.diff(sub)
            rv_sub.append(float(np.sum(dl * dl)))
    if not rv_sub:
        rv_avg = rv_all
    else:
        rv_avg = float(np.mean(rv_sub))
    n_bar = (n - K + 1) / float(K)
    tsrv = rv_avg - (n_bar / max(n, 1)) * rv_all          # (6)
    tsrv = max(tsrv, 0.0)

    total_seconds = max(n * dt_seconds, _EPS)
    per_sec_var = tsrv / total_seconds
    var = per_sec_var * (SECONDS_PER_YEAR if annualise else 1.0)
    return max(math.sqrt(max(var, 0.0)), floor)


# ===========================================================================
# PILLAR 3 — VPIN (volume-synchronised probability of informed trading)
# ===========================================================================
def vpin(
    prices: Sequence[float],
    volumes: Optional[Sequence[float]] = None,
    *,
    n_buckets: int = 20,
    bvc_scale: float = 1.0,
) -> float:
    """VPIN order-flow toxicity via bulk-volume classification (eq. 10).

    (Easley-López de Prado-O'Hara 2012.)  Volume is split into ``n_buckets``
    equal-volume buckets.  Within each bucket the **buy fraction** is the
    bulk-volume-classification estimate

        f_buy = Phi( Δp / (sigma_dp * bvc_scale) )

    from the standardised intra-bucket price change (informed buying pushes
    price up).  The bucket's order-flow imbalance is ``|2*f_buy - 1|`` and

        VPIN = mean_b |V_buy(b) - V_sell(b)| / V(b) = mean_b |2 f_buy(b) - 1|.

    Returns a toxicity score in ``[0, 1]`` (0 = perfectly balanced flow, 1 =
    fully one-sided/informed).  When volumes are absent, equal weights are used
    (tick-time VPIN).

    Parameters
    ----------
    prices
        Price series across the bucketing horizon.
    volumes
        Per-tick volumes; if ``None`` each tick counts as 1 unit.
    n_buckets
        Number of equal-volume buckets to synchronise on.
    bvc_scale
        Scale on the standard deviation of price changes in the BVC ``Phi`` map.
    """
    p = np.asarray([x for x in prices if x is not None and math.isfinite(float(x))], dtype=float)
    if p.size < 3:
        return float("nan")
    dp = np.diff(p)
    if volumes is None:
        vol = np.ones(dp.size, dtype=float)
    else:
        v = np.asarray([x for x in volumes if x is not None and math.isfinite(float(x))], dtype=float)
        # align: one volume per price-change interval (use trailing tick volume)
        if v.size >= p.size:
            vol = v[1:p.size].astype(float)
        elif v.size == dp.size:
            vol = v.astype(float)
        else:
            vol = np.ones(dp.size, dtype=float)
    vol = np.abs(vol)
    total_v = float(vol.sum())
    if total_v <= 0 or dp.size == 0:
        return float("nan")

    sigma_dp = float(np.std(dp))
    if sigma_dp <= _EPS:
        # no price variation → flow is uninformative → low toxicity
        return 0.0
    z = dp / (sigma_dp * max(bvc_scale, _EPS))
    f_buy = np.array([norm_cdf(float(zz)) for zz in z])   # BVC buy fraction

    # synchronise into equal-volume buckets
    target = total_v / float(max(n_buckets, 1))
    cum = np.cumsum(vol)
    imbalances: List[float] = []
    b_start = 0
    bucket_idx = 1
    for i in range(dp.size):
        if cum[i] >= bucket_idx * target - _EPS or i == dp.size - 1:
            seg = slice(b_start, i + 1)
            vseg = vol[seg]
            vtot = float(vseg.sum())
            if vtot > 0:
                vbuy = float(np.sum(vseg * f_buy[seg]))
                vsell = vtot - vbuy
                imbalances.append(abs(vbuy - vsell) / vtot)
            b_start = i + 1
            bucket_idx += 1
    if not imbalances:
        # fall back to a single global imbalance
        vbuy = float(np.sum(vol * f_buy))
        return abs(2.0 * vbuy / total_v - 1.0)
    return float(np.mean(imbalances))


# ===========================================================================
# PILLAR 2 — Fair probability (Gaussian / endpoint formula)
# ===========================================================================
def fair_prob_up(
    s_star: float,
    strike: float,
    sigma_ann: float,
    tau_years: float,
    *,
    mu_ann: float = 0.0,
) -> float:
    """Gaussian endpoint fair probability that the window resolves UP (eq. 9).

        x      = ln(S_star / K)
        P_fair = Phi( (x + mu*tau) / (sigma * sqrt(tau)) )

    Evaluated at the **efficient** spot ``S_star`` (pillar 1) and the noise-robust
    ``sigma`` (pillar 1b).  Degenerate inputs (tau<=0, sigma<=0) collapse to a
    hard ``{0, 0.5, 1}`` indicator on the sign of the log-moneyness.
    """
    if strike <= 0 or s_star <= 0:
        return 0.5
    x = math.log(s_star / strike)
    denom = sigma_ann * math.sqrt(max(tau_years, 0.0))
    if denom <= _EPS:
        if abs(x) < _EPS:
            return 0.5
        return 1.0 if x > 0 else 0.0
    return norm_cdf((x + mu_ann * tau_years) / denom)


# ===========================================================================
# EVT TAIL OVERLAY — Generalized Pareto via peaks-over-threshold (optional)
# ===========================================================================
@dataclass
class GPDFit:
    """Fitted Generalized Pareto tail parameters (peaks-over-threshold).

    Attributes
    ----------
    xi
        Shape parameter (``xi<0`` ⇒ bounded tail; ``xi>0`` ⇒ heavy/fat tail).
    beta
        Scale parameter (>0).
    threshold
        The POT threshold ``u`` above which the GPD models exceedances.
    n_exceed
        Number of exceedances used in the fit.
    tail_frac
        Empirical fraction of returns above the threshold (= P(R>u)).
    """

    xi: float
    beta: float
    threshold: float
    n_exceed: int
    tail_frac: float

    def exceedance_sf(self, y: float) -> float:
        """GPD survival ``P(R - u > y | R > u)`` for exceedance ``y>=0`` (eq. 14)."""
        if y <= 0:
            return 1.0
        if abs(self.xi) < 1e-8:
            return math.exp(-y / max(self.beta, _EPS))          # xi→0 limit
        z = 1.0 + self.xi * y / max(self.beta, _EPS)
        if z <= 0:
            return 0.0  # past the finite upper bound (xi<0)
        return z ** (-1.0 / self.xi)

    def tail_prob_above(self, level: float) -> float:
        """Unconditional ``P(R > level)`` using the POT decomposition.

        ``P(R>level) = tail_frac * P(R-u > level-u | R>u)`` for ``level>=u``.
        """
        if level <= self.threshold:
            return float("nan")  # body region — caller should use the Gaussian
        return self.tail_frac * self.exceedance_sf(level - self.threshold)


def gpd_tail_fit(
    returns: Sequence[float],
    *,
    threshold_q: float = 0.90,
    min_exceed: int = 15,
) -> Optional[GPDFit]:
    """Fit a GPD to the upper tail of ``returns`` by peaks-over-threshold.

    Uses the **method-of-moments** GPD estimator (Hosking-Wallis 1987) —
    closed-form, no statsmodels.  For threshold exceedances ``y = r - u`` with
    sample mean ``m1`` and variance ``s2``:

        xi   = 0.5 * (1 - m1^2 / s2)            (shape)
        beta = 0.5 * m1 * (m1^2 / s2 + 1)       (scale)

    (Derived from the GPD moments ``E[Y]=beta/(1-xi)`` and
    ``Var[Y]=beta^2/((1-xi)^2 (1-2xi))``.)  Returns ``None`` if there are too
    few exceedances or the moments are degenerate.  (Pickands-Balkema-de Haan
    justifies the GPD as the limiting exceedance law; eq. 14.)

    Parameters
    ----------
    returns
        Sample of (log) returns whose UPPER tail we model.
    threshold_q
        Quantile defining the POT threshold ``u`` (e.g. 0.90 = top decile).
    min_exceed
        Minimum number of exceedances required to attempt a fit.
    """
    r = np.asarray([x for x in returns if x is not None and math.isfinite(float(x))], dtype=float)
    if r.size < min_exceed * 3:
        return None
    u = float(np.quantile(r, threshold_q))
    exc = r[r > u] - u
    m = exc.size
    if m < min_exceed:
        return None
    m1 = float(np.mean(exc))
    s2 = float(np.var(exc))
    if m1 <= 0 or s2 <= _EPS:
        return None
    ratio = (m1 * m1) / s2
    xi = 0.5 * (1.0 - ratio)            # method-of-moments shape
    beta = 0.5 * m1 * (ratio + 1.0)     # method-of-moments scale
    if beta <= 0 or not math.isfinite(xi) or not math.isfinite(beta):
        return None
    tail_frac = float(m) / float(r.size)
    return GPDFit(xi=float(xi), beta=float(beta), threshold=u, n_exceed=int(m), tail_frac=float(tail_frac))


def evt_corrected_fair_prob(
    s_star: float,
    strike: float,
    sigma_ann: float,
    tau_years: float,
    *,
    log_returns: Sequence[float],
    gaussian_p: float,
    threshold_q: float = 0.90,
    blend: float = 0.5,
) -> float:
    """Blend the Gaussian fair prob with a GPD tail estimate near the strike.

    For an UP bet the relevant tail event is "remaining log-return exceeds the
    log-distance to the strike", ``need = ln(K / S_star)``.  When ``need`` lands
    in the *fitted upper tail* (``need > u``), the Gaussian (eq. 9) understates
    the crossing probability; we replace it with a convex blend of the Gaussian
    and the GPD ``tail_prob_above`` (eq. 14).  Outside the tail (body region) we
    return the Gaussian unchanged.  Symmetric handling is used for the lower
    tail (``need < -u`` on the down side) by modelling ``-log_returns``.

    Returns the (possibly tail-corrected) ``P_fair(up)`` in ``[0,1]``.
    """
    if strike <= 0 or s_star <= 0 or tau_years <= 0:
        return gaussian_p
    need = math.log(strike / s_star)  # positive ⇒ need an UP move to cross
    lr = list(log_returns)
    if need >= 0:
        fit = gpd_tail_fit(lr, threshold_q=threshold_q)
        if fit is None:
            return gaussian_p
        p_cross_up = fit.tail_prob_above(need)
        if not math.isfinite(p_cross_up):
            return gaussian_p
        p_evt = float(np.clip(p_cross_up, 0.0, 1.0))   # P(close>K) ≈ P(up move ≥ need)
    else:
        # already above strike; tail event is a DOWN move beyond |need| to fall
        fit = gpd_tail_fit([-x for x in lr], threshold_q=threshold_q)
        if fit is None:
            return gaussian_p
        p_cross_down = fit.tail_prob_above(-need)
        if not math.isfinite(p_cross_down):
            return gaussian_p
        p_evt = float(np.clip(1.0 - p_cross_down, 0.0, 1.0))
    return float(np.clip((1.0 - blend) * gaussian_p + blend * p_evt, 0.0, 1.0))


# ===========================================================================
# PILLAR 4 — Information-entropy sizing
# ===========================================================================
def kl_divergence_binary(p_fair: float, mid: float) -> float:
    """Binary KL divergence ``D_KL(P_fair || mid)`` in nats (eq. 11).

    The information gain of our posterior ``P_fair`` over the book's prior
    ``mid`` — large when we disagree confidently with the market.  Clipped away
    from {0,1} for numerical safety.
    """
    p = min(max(p_fair, 1e-6), 1.0 - 1e-6)
    q = min(max(mid, 1e-6), 1.0 - 1e-6)
    return p * math.log(p / q) + (1.0 - p) * math.log((1.0 - p) / (1.0 - q))


def entropy_size(
    p_fair: float,
    mid: float,
    fill_price: float,
    *,
    vpin_pct: float,
    kelly_frac: float,
    kl_gain: float,
    win_prob: Optional[float] = None,
) -> float:
    """Toxicity-scaled, KL-weighted fractional-Kelly size in ``[0,1]`` (eq. 13).

    Combines:
      * fractional Kelly on the modelled binary edge (eq. 12) at the *fill*
        price (so the size already respects the bimodal-fill penalty),
      * the information gain ``tanh(kl_gain * D_KL)`` (pillar 4, bounded in
        [0,1)),
      * the toxicity confidence ``(1 - vpin_pct)`` — size up only in benign flow.

    Parameters
    ----------
    p_fair
        Model fair probability of the leg paying $1 (win prob of the leg).
    mid
        Market mid of the leg's token (the prior in the KL term).
    fill_price
        Expected per-share fill price of the leg (Kelly uses this, not the mid).
    vpin_pct
        VPIN percentile in [0,1] at the decision time (1 = max toxicity).
    kelly_frac
        Fraction of full Kelly to deploy (risk control), e.g. 0.20.
    kl_gain
        Gain on the KL term inside the ``tanh`` saturation.
    win_prob
        Optional explicit leg win-probability; defaults to ``p_fair``.
    """
    pw = p_fair if win_prob is None else win_prob
    price = min(max(fill_price, 1e-6), 1.0 - 1e-6)
    f_kelly = (pw - price) / (1.0 - price)
    f_kelly = float(np.clip(f_kelly, 0.0, 1.0))
    kl = kl_divergence_binary(p_fair, mid)
    info = math.tanh(max(kl_gain, 0.0) * max(kl, 0.0))
    tox = float(np.clip(1.0 - vpin_pct, 0.0, 1.0))
    return float(np.clip(kelly_frac * f_kelly * info * tox, 0.0, 1.0))


# ===========================================================================
# Params
# ===========================================================================
@dataclass
class MicrostructureStatArbParams(StrategyParams):
    """Optimization-ready knobs for S4.

    Attributes (with suggested optimisation ranges)
    -----------------------------------------------
    theta_entry : float          # [0.02, 0.12]  min |P_fair-mid| gap to open
    theta_exit : float           # [0.005, 0.05] gap below ⇒ early-exit (reverted)
    vpin_entry_q : float         # [0.30, 0.70]  act only if VPIN < this quantile
    vpin_kill_q : float          # [0.80, 0.98]  early-exit if VPIN > this quantile
    vpin_buckets : int           # [10, 50]      equal-volume buckets for VPIN
    vpin_window : int            # [40, 300]     bars of VPIN history for quantile
    bvc_scale : float            # [0.5, 2.0]    BVC sigma scale in Phi map
    kalman_min_obs : int         # [8, 60]       min spot obs to trust efficient px
    tsrv_K : int                 # [3, 10]       TSRV subsampling stride
    sigma_floor_ann : float      # [0.2, 1.5]    floor on annualised sigma
    sigma_scale : float          # [0.6, 1.6]    multiplicative tune on TSRV sigma
    mu_ann : float               # [-0.5, 0.5]   optional annual drift in P_fair
    kelly_frac : float           # [0.05, 0.5]   fraction of full Kelly
    kl_gain : float              # [1.0, 20.0]   gain inside tanh(KL) sizing
    use_evt_tail : bool          # toggle GPD tail overlay (default off)
    evt_threshold_q : float      # [0.85, 0.97]  POT threshold quantile
    evt_blend : float            # [0.0, 1.0]    Gaussian/GPD blend weight
    enable_early_exit : bool     # allow FLAT on reversion / toxicity spike
    binary_edge_min : float      # [0.01, 0.08]  min (P_fair - exp_fill) to act
    """

    # --- gap / reversion gates ---
    theta_entry: float = 0.05
    theta_exit: float = 0.015
    # --- toxicity (adverse-selection immunization) ---
    vpin_entry_q: float = 0.50
    vpin_kill_q: float = 0.90
    vpin_buckets: int = 20
    vpin_window: int = 120
    bvc_scale: float = 1.0
    # --- efficient price / vol ---
    kalman_min_obs: int = 10
    tsrv_K: int = 5
    sigma_floor_ann: float = 0.40
    sigma_scale: float = 1.0
    mu_ann: float = 0.0
    # --- entropy / Kelly sizing ---
    kelly_frac: float = 0.20
    kl_gain: float = 6.0
    # --- EVT tail overlay ---
    use_evt_tail: bool = False
    evt_threshold_q: float = 0.90
    evt_blend: float = 0.5
    # --- exits / edge floor ---
    enable_early_exit: bool = True
    binary_edge_min: float = 0.02
    # --- base-class fields tightened for this strategy ---
    max_position_frac: float = 0.08
    per_window_budget_frac: float = 0.15
    edge_min: float = 0.02
    min_seconds_to_resolution: float = 30.0


# ===========================================================================
# Strategy
# ===========================================================================
@register_strategy("microstructure_statarb")
class MicrostructureStatArb(Strategy):
    """Efficient-price stat-arb with VPIN adverse-selection immunization.

    Per causal step (data ``<= t``):

    1. Build causal spot/return history from ``ctx.history`` (``binance_spot``).
    2. Strike ``K`` = the **first observed** window-open spot (causal).
    3. Efficient spot ``S_star`` via :class:`KalmanEfficientPrice` with
       ``(q, r)`` estimated from the spot tape (:func:`estimate_qr`).
    4. Noise-robust ``sigma`` via :func:`tsrv_sigma` (TSRV).
    5. ``P_fair`` via :func:`fair_prob_up` (optionally EVT-tail-corrected).
    6. ``VPIN`` toxicity via :func:`vpin`; convert to a rolling percentile.
    7. ENTRY: if ``VPIN`` percentile < ``vpin_entry_q`` AND ``|P_fair-mid| >
       theta_entry`` AND the modelled edge over expected fill clears the floors,
       BUY the cheap side, sized by :func:`entropy_size`.
    8. EXIT: if holding and (gap reverted < ``theta_exit`` OR VPIN percentile >
       ``vpin_kill_q``) → emit ``FLAT`` (else hold to resolution).

    No look-ahead: only ``ctx.history`` (spots ``<= t``), ``ctx.row``, and
    ``ctx.peer`` are read; settlement OHLC / labels are never touched.
    """

    params_cls = MicrostructureStatArbParams

    def __init__(self, params: Optional[MicrostructureStatArbParams] = None) -> None:
        super().__init__(params)
        # Rolling VPIN sample for the percentile gate (per strategy instance).
        # This is a causal, online quantile reference — it only ever ingests
        # VPIN values computed from data <= t, so it cannot leak the future.
        self._vpin_hist: List[float] = []
        # One round-trip per window-token: once we have opened (and possibly
        # early-exited) this window we do NOT re-enter it. Without this guard the
        # gap oscillates around theta_entry/theta_exit and the strategy churns
        # many entries per window, bleeding fees+slippage+toxic cost (observed on
        # real BTC 5m: ~13 trades/window, full-bankroll wipeout).
        self._acted: set = set()

    # -- helpers -----------------------------------------------------------
    def _causal_spots(self, ctx: StrategyContext) -> np.ndarray:
        """Causal Binance-spot series from history (ascending, finite)."""
        out: List[float] = []
        for r in ctx.history:
            v = r.binance_spot
            if v is not None and math.isfinite(float(v)) and float(v) > 0:
                out.append(float(v))
        return np.asarray(out, dtype=float)

    def _vpin_percentile(self, current: float) -> float:
        """Rolling percentile of the current VPIN within recent history.

        Updates the causal rolling buffer (bounded by ``vpin_window``) and
        returns ``current``'s percentile rank in ``[0,1]``.  Until the buffer
        warms up we return a neutral 0.5 (no strong toxicity prior).
        """
        if not math.isfinite(current):
            return 1.0  # unknown toxicity ⇒ treat as toxic ⇒ stand down
        hist = self._vpin_hist
        n = len(hist)
        if n < max(10, self.params.vpin_window // 8):
            hist.append(current)
            if len(hist) > self.params.vpin_window:
                del hist[0]
            return 0.5
        arr = np.asarray(hist, dtype=float)
        pct = float(np.mean(arr <= current))
        hist.append(current)
        if len(hist) > self.params.vpin_window:
            del hist[0]
        return pct

    def _compute_signal(
        self, ctx: StrategyContext
    ) -> Optional[Tuple[float, float, float, float, float]]:
        """Return ``(p_fair, mid, sigma_ann, vpin_pct, tau_years)`` or None.

        Pure function of the causal context; encapsulates pillars 1-3 so both
        the entry and the exit paths share one consistent computation.
        """
        p = self.params
        mid = ctx.mid
        if mid is None or not (0.0 < float(mid) < 1.0):
            return None
        spots = self._causal_spots(ctx)
        if spots.size < p.kalman_min_obs:
            return None
        strike = float(spots[0])  # window-open spot = strike K (causal)

        # PILLAR 1 — Kalman efficient price
        q, r = estimate_qr(spots)
        kf = KalmanEfficientPrice(q=q, r=r)
        s_star = kf.filter_series(spots)
        if not math.isfinite(s_star) or s_star <= 0:
            s_star = float(spots[-1])

        # PILLAR 1b — TSRV noise-robust sigma
        # average inter-observation spacing from the causal timeline
        ts = [row.ts_s for row in ctx.history]
        if len(ts) >= 2:
            dt_seconds = max((ts[-1] - ts[0]) / max(len(ts) - 1, 1), 1e-3)
        else:
            dt_seconds = 10.0
        sigma = tsrv_sigma(spots, dt_seconds=dt_seconds, K=p.tsrv_K, annualise=True)
        sigma = max(sigma * p.sigma_scale, p.sigma_floor_ann)

        tau_years = max(float(ctx.seconds_to_resolution), 0.0) / SECONDS_PER_YEAR
        if tau_years <= 0:
            return None

        # PILLAR 2 — Gaussian fair prob (efficient spot + robust sigma)
        p_fair = fair_prob_up(s_star, strike, sigma, tau_years, mu_ann=p.mu_ann)
        # EVT tail overlay (optional)
        if p.use_evt_tail and spots.size >= 30:
            log_rets = list(np.diff(np.log(spots)))
            p_fair = evt_corrected_fair_prob(
                s_star, strike, sigma, tau_years,
                log_returns=log_rets, gaussian_p=p_fair,
                threshold_q=p.evt_threshold_q, blend=p.evt_blend,
            )
        # If this panel is the DOWN/NO token, its mid prices P(down) = 1-P(up).
        # We always reason in this token's own probability space so the gap
        # (P_fair_token - mid_token) is apples-to-apples.
        if not ctx.outcome_dir or ctx.outcome_dir.lower() == "up":
            p_fair_token = p_fair
        else:
            p_fair_token = 1.0 - p_fair

        # PILLAR 3 — VPIN toxicity (tick-time over the causal spot tape)
        vp = vpin(spots, volumes=None, n_buckets=p.vpin_buckets, bvc_scale=p.bvc_scale)
        vpin_pct = self._vpin_percentile(vp)

        return (float(p_fair_token), float(mid), float(sigma), float(vpin_pct), float(tau_years))

    # -- main step ---------------------------------------------------------
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        if not self.params.enabled:
            return []
        sig = self._compute_signal(ctx)
        if sig is None:
            return []
        p_fair_token, mid, sigma, vpin_pct, tau_years = sig
        gap = p_fair_token - mid  # >0 ⇒ this token underpriced (P_fair richer)

        # -------- EXIT path: reversion or toxicity spike --------
        if ctx.open_shares > 0 and self.params.enable_early_exit:
            reverted = abs(gap) < self.params.theta_exit
            toxic_spike = vpin_pct > self.params.vpin_kill_q
            if reverted or toxic_spike:
                return [Signal(
                    side="FLAT",
                    meta={
                        "strategy_note": "s4_exit",
                        "reason": "reverted" if reverted else "vpin_kill",
                        "gap": float(gap),
                        "vpin_pct": float(vpin_pct),
                    },
                )]
            return []  # hold to resolution otherwise

        # -------- ENTRY gating --------
        # already holding (and not exiting) ⇒ do not stack
        if ctx.open_shares > 0:
            return []
        # one round-trip per window-token: do not re-enter a window we've
        # already traded (prevents the theta-band churn seen on real data).
        akey = (ctx.token_id, ctx.window_end_ts)
        if akey in self._acted:
            return []
        # min-horizon guard: P_fair = Phi((..)/(sigma*sqrt(tau))) collapses to a
        # hard 0/1 step as tau->0, so never enter inside the final
        # min_seconds_to_resolution. Enforced internally (do NOT rely on the
        # engine's allow_short_window_entries, which defaults to open).
        if ctx.seconds_to_resolution < self.params.min_seconds_to_resolution:
            return []
        # adverse-selection immunization: only act in benign (low-VPIN) flow
        if vpin_pct >= self.params.vpin_entry_q:
            return []
        # require a real gap
        if abs(gap) <= self.params.theta_entry:
            return []

        # Choose the cheap side IN THIS TOKEN's space:
        #   gap>0 ⇒ this token underpriced ⇒ buy THIS token (UP→BUY_YES, DOWN→BUY_NO)
        #   gap<0 ⇒ this token overpriced  ⇒ buy the PEER token (the other leg)
        is_up = (not ctx.outcome_dir) or ctx.outcome_dir.lower() == "up"
        row = ctx.row
        peer = ctx.peer or {}

        if gap > 0:
            # buy this token at its own ask
            side = "BUY_YES" if is_up else "BUY_NO"
            touch = row.best_ask
            leg_winprob = p_fair_token
            leg_mid = mid
        else:
            # buy the opposite leg; its win-prob is (1 - p_fair_token),
            # its mid is (1 - mid) (peer mid if available)
            side = "BUY_NO" if is_up else "BUY_YES"
            touch = peer.get("best_ask")
            leg_winprob = 1.0 - p_fair_token
            leg_mid = peer.get("mid")
            if leg_mid is None:
                leg_mid = 1.0 - mid

        if touch is None or not (0.0 < float(touch) < 1.0):
            return []
        touch = float(touch)
        if leg_mid is None or not (0.0 < float(leg_mid) < 1.0):
            return []
        leg_mid = float(leg_mid)

        # modelled edge net of the bimodal-fill penalty + slippage
        exp_fill = ctx.extras["expected_fill_price"]("buy", touch)
        edge = leg_winprob - exp_fill
        if edge < self.params.binary_edge_min or edge < self.params.edge_min:
            return []

        # PILLAR 4 — entropy/Kelly sizing (toxicity-scaled)
        size_frac = entropy_size(
            p_fair=leg_winprob,
            mid=leg_mid,
            fill_price=exp_fill,
            vpin_pct=vpin_pct,
            kelly_frac=self.params.kelly_frac,
            kl_gain=self.params.kl_gain,
        )
        if size_frac <= 0.0:
            return []

        self._acted.add(akey)
        return [Signal(
            side=side,
            size_fraction=size_frac,
            price_limit=float(min(0.99, touch + 0.05)),
            meta={
                "strategy_note": "s4_microstructure_statarb",
                "p_fair_token": float(p_fair_token),
                "leg_winprob": float(leg_winprob),
                "mid": float(mid),
                "gap": float(gap),
                "sigma_ann": float(sigma),
                "vpin_pct": float(vpin_pct),
                "edge": float(edge),
                "tau_years": float(tau_years),
                "exp_fill": float(exp_fill),
            },
        )]


__all__ = [
    "norm_cdf",
    "KalmanState",
    "KalmanEfficientPrice",
    "estimate_qr",
    "tsrv_sigma",
    "vpin",
    "fair_prob_up",
    "GPDFit",
    "gpd_tail_fit",
    "evt_corrected_fair_prob",
    "kl_divergence_binary",
    "entropy_size",
    "MicrostructureStatArbParams",
    "MicrostructureStatArb",
]
