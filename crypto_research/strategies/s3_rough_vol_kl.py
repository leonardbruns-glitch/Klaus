"""Strategy S3 — Rough Volatility & Fractional Information Divergence.

Overview
========
This module trades Polymarket up/down binary windows on a *structural*,
calibration-light edge: the divergence between a **physical** outcome
probability ``P_phys`` derived from a **fractional Brownian motion (fBM)**
model of the log-price path and the Polymarket-**implied** probability
``P_poly`` read off the order book.  Position size is governed by an
**asymmetric fractional Kelly** rule that respects the favorite-longshot bias.

The whole edge is *probabilistic / mathematical* and is evaluated on **bar
cadence** (one ``market_timeline`` row per ``on_step`` call, seconds-to-minutes
apart).  Nothing here depends on sub-bar latency: the inputs are a rolling
Hurst estimate over hundreds of 5-minute bars, the accumulated log-move so far,
and the time remaining to the diurnal/window endpoint.  See the NON-HFT note at
the bottom for the explicit justification.

================================================================================
MATHEMATICAL CORE
================================================================================

1. ROUGH VOLATILITY / fBM MEMORY (the Hurst exponent ``H``)
-----------------------------------------------------------
Classical Brownian motion has independent increments and a variance that scales
**linearly** in time, ``Var[B_t] = t`` (i.e. ``t^{2H}`` with ``H = 1/2``).  A
*fractional* Brownian motion ``B^H_t`` (Mandelbrot–Van Ness) generalises this to
a single self-similarity / memory parameter ``H in (0, 1)``:

        Var[B^H_t] = sigma^2 * t^{2H},                                   (M1)

        Cov(B^H_s, B^H_t) = 0.5 * (|s|^{2H} + |t|^{2H} - |t - s|^{2H}).  (M2)

Interpretation of ``H``:
  * ``H = 0.5`` — independent increments, efficient random walk (Brownian).
  * ``H < 0.5`` — *anti-persistent* memory: increments negatively correlated,
    the path mean-reverts at the micro scale (the empirically dominant regime
    for high-frequency realised volatility and microstructure — "rough vol",
    Gatheral–Jaisson–Rosenbaum 2018, who find H ~ 0.1 for vol; for *returns*
    over minutes H sits a little below 0.5).
  * ``H > 0.5`` — *persistent / trending* memory: increments positively
    correlated, momentum.

We estimate ``H`` two ways and cross-check:

  (a) **DFA — Detrended Fluctuation Analysis** (primary).  For a series of
      length N, build the integrated profile ``Y_k = sum_{i<=k}(r_i - mean(r))``.
      Split into non-overlapping boxes of length ``s``; in each box fit and
      remove a linear (order-1) trend; the detrended fluctuation is

          F(s) = sqrt( mean_over_boxes mean_in_box (Y - trend)^2 ).        (M3)

      For self-similar data ``F(s) ~ s^{alpha}``.  Our DFA input is the
      **return** (fGN) series, which is the stationary-increment process, so
      the integrate-once-then-detrend DFA scaling exponent estimates the Hurst
      exponent of the increments directly:

          H = slope( log F(s) vs log s ).                                  (M4)

      (If one fed the already-integrated *price/profile* series instead, the
      exponent would be ``H + 1``; we feed returns, so no offset.)  Clipped to
      (0,1).

  (b) **R/S — Rescaled Range** (cross-check, Hurst 1951).  For window length n,
      mean-adjust ``z_i = r_i - mean``, cumulative deviation
      ``Z_k = sum_{i<=k} z_i``, range ``R = max Z - min Z``, std ``S``; then

          E[R/S]_n  ~  c * n^H   =>   H = slope( log(R/S) vs log n ).      (M5)

2. PHYSICAL OUTCOME PROBABILITY UNDER fBM (``P_phys``)
-----------------------------------------------------
The contract resolves on the **endpoint sign** of the log-move over the window:
it pays YES iff ``log(S_T / S_open) > 0``.  Let ``x = log(S_now / S_open)`` be the
log-move accumulated so far and ``tau`` the remaining time fraction to the
window end.  Under the fBM marginal (M1) the *remaining* increment is

        Delta ~ Normal( mu * tau,  sigma^2 * tau^{2H} ),                  (M6)

— note the variance scales as ``tau^{2H}`` (the **rough correction**), NOT the
Brownian ``tau^{1/2}`` standard-deviation scaling.  The endpoint is YES iff
``x + Delta > 0``, i.e. ``Delta > -x``, so

        P_phys = P[ x + Delta > 0 ]
               = Phi( (x + mu*tau) / (sigma * tau^{H}) ).                  (M7)

``Phi`` is the standard-normal CDF.  When ``H = 0.5`` this collapses to the
familiar Brownian endpoint probability ``Phi((x + mu*tau)/(sigma*sqrt(tau)))``.
``mu`` (drift) defaults to 0 (efficient-market prior) and is configurable;
``sigma`` is the **per-unit-time** volatility estimated from the same return
series used for ``H`` (so it is internally consistent with the memory model).

3. BARRIER / TARGET MARKETS — Monte-Carlo first passage (``p_phys_mc_barrier``)
-------------------------------------------------------------------------------
Some Polymarket crypto markets resolve on whether a *level* is touched (a
barrier), for which fBM has **no closed-form first-passage law**.  We therefore
provide an exact-covariance fBM **path simulator** (Davies–Harte circulant
embedding with a Cholesky fallback) and a Monte-Carlo breach estimator:

        P_breach ~= (1/M) * sum_{m=1..M} 1{ max_t S^{(m)}_t >= barrier }   (M8)

(or ``min ... <= barrier`` for a down-barrier).  This is the alternative
``P_phys`` engine for target markets; the endpoint formula (M7) is the primary
engine for the up/down sign markets that dominate the data.

4. INFORMATION DIVERGENCE — KL between Bernoullis (the trade trigger)
--------------------------------------------------------------------
``P_phys`` (our model) and ``P_poly`` (the book) are two Bernoulli beliefs about
the same event.  Their disagreement is measured by the Kullback–Leibler
divergence

        KL(P_phys || P_poly) = p*ln(p/q) + (1-p)*ln((1-p)/(1-q)),         (M9)

with ``p = P_phys``, ``q = P_poly``.  KL is the *expected log-likelihood-ratio*
— the information (in nats) our model claims the book is missing.  We act only
when ``KL > kl_threshold`` (enough divergence to overcome fees + adverse fills)
AND the *sign* of ``p - q`` points to a tradeable side:
  * ``p > q`` ⇒ YES is underpriced ⇒ buy YES (or the up token).
  * ``p < q`` ⇒ YES is overpriced  ⇒ buy NO  (the down/peer token).

5. ASYMMETRIC FRACTIONAL KELLY (sizing)
---------------------------------------
Buying a binary at ask ``a`` (pays 1 on win) has net decimal odds
``b = (1 - a) / a``.  With win probability ``p`` the **full-Kelly** fraction is

        f* = p - (1 - p) / b = p - (1 - p) * a / (1 - a).                 (M10)

We apply a *fractional* multiplier ``lambda`` (default 0.2 — quarter-to-fifth
Kelly for drawdown control) and, crucially, an **asymmetric** multiplier so that
longshots (cheap tails) are sized more conservatively than favorites — the
empirical favorite-longshot bias (longshots are systematically overpriced):

        f_used = clip( lambda_side * f*, 0, max_position_frac ),
        lambda_yes for YES-side bets, lambda_no for NO-side bets.         (M11)

We never bet when ``f* <= 0`` (no edge after the price is paid), and we floor at
``kelly_f_min`` so a vanishingly small Kelly does not waste capital on fees.

================================================================================
SAFEGUARDS HONORED (via the shared engine)
================================================================================
* **Bimodal fills** — we never assume mid fills; EV gating uses
  ``ctx.extras["expected_fill_price"]("buy", ask)`` (closed-form, no RNG draw),
  and the engine routes the actual fill through the seeded ``BimodalFillModel``.
* **Execution penalty** — the per-share slippage in [0.01, 0.02] is applied by
  the engine; we additionally discount the modelled win probability by the
  expected fill premium before computing Kelly so the edge must clear it.
* **Fees** — the live up/down fee curve (~1.8% of notional at p=0.5) is applied
  by the portfolio's ``fee_fn``; our ``edge_min`` floor is set above it.
* **Metrics** — Sharpe / Sortino / MaxDD / Profit-Factor / win-rate / n are
  produced by the engine's ``summary`` after fees + funding.

Run on synthetic data (no real logs needed):
    >>> from crypto_research.data.loader import make_synthetic_panels
    >>> from crypto_research.backtest.engine import BacktestEngine, EngineConfig
    >>> panels = make_synthetic_panels(300, seed=1)
    >>> from crypto_research.strategies.s3_rough_vol_kl import RoughVolKLStrategy
    >>> res = BacktestEngine(panels, [RoughVolKLStrategy()]).run()
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from .base import (
    Signal,
    Strategy,
    StrategyContext,
    StrategyParams,
    register_strategy,
)

# ---------------------------------------------------------------------------
# Numerical helpers
# ---------------------------------------------------------------------------

_SQRT2 = math.sqrt(2.0)


def _norm_cdf(z: float) -> float:
    """Standard-normal CDF ``Phi(z)`` via the error function (no SciPy dep)."""
    return 0.5 * (1.0 + math.erf(z / _SQRT2))


def _safe_log_returns(prices: np.ndarray) -> np.ndarray:
    """Log returns of a positive price series, dropping non-finite values.

    ``r_i = ln(P_{i+1} / P_i)``.  Robust to ``NaN`` / non-positive entries that
    appear in the sparse Tier-1 feature panels.
    """
    p = np.asarray(prices, dtype=float)
    p = p[np.isfinite(p) & (p > 0.0)]
    if p.size < 2:
        return np.empty(0, dtype=float)
    r = np.diff(np.log(p))
    return r[np.isfinite(r)]


# ===========================================================================
# 1. HURST ESTIMATION
# ===========================================================================


def hurst_dfa(
    returns: np.ndarray,
    *,
    min_box: int = 4,
    max_box: Optional[int] = None,
    n_scales: int = 12,
) -> float:
    """Hurst exponent via Detrended Fluctuation Analysis (Eq. M3–M4).

    Parameters
    ----------
    returns
        1-D array of (log) returns — the *increments* of the price process.
    min_box
        Smallest box length ``s`` (>= 4 so an order-1 detrend is well posed).
    max_box
        Largest box length (default ``N // 4`` so each scale has >= 4 boxes).
    n_scales
        Number of log-spaced scales between ``min_box`` and ``max_box``.

    Returns
    -------
    float
        Estimated ``H`` clipped to ``(0.01, 0.99)``; ``0.5`` if the series is
        too short to estimate (efficient-market fallback).

    Notes
    -----
    Builds the integrated profile ``Y_k = cumsum(r - mean(r))``, fits and
    removes a linear trend inside each non-overlapping box of length ``s``, and
    regresses ``log F(s)`` on ``log s``.  The slope ``alpha`` of the profile of
    stationary increments satisfies ``H = alpha - 1`` (clipped to (0,1)).
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < max(2 * min_box, 16):
        return 0.5

    profile = np.cumsum(r - r.mean())  # Y_k (integrate the increments once)
    if max_box is None:
        max_box = max(min_box + 1, n // 4)
    max_box = min(max_box, n // 2)
    if max_box <= min_box:
        return 0.5

    scales = np.unique(
        np.floor(
            np.logspace(np.log10(min_box), np.log10(max_box), n_scales)
        ).astype(int)
    )
    scales = scales[scales >= min_box]
    if scales.size < 3:
        return 0.5

    log_s: List[float] = []
    log_f: List[float] = []
    for s in scales:
        n_boxes = n // s
        if n_boxes < 2:
            continue
        trimmed = profile[: n_boxes * s].reshape(n_boxes, s)
        t = np.arange(s, dtype=float)
        # Vandermonde for an order-1 (linear) fit, shared across boxes.
        vander = np.vstack([t, np.ones_like(t)]).T  # (s, 2)
        # Least-squares trend per box: coeffs = (V^T V)^-1 V^T y, batched.
        coeffs, _, _, _ = np.linalg.lstsq(vander, trimmed.T, rcond=None)  # (2, n_boxes)
        trend = (vander @ coeffs).T  # (n_boxes, s)
        resid = trimmed - trend
        f_s = math.sqrt(float(np.mean(resid ** 2)))
        if f_s > 0.0:
            log_s.append(math.log(s))
            log_f.append(math.log(f_s))

    if len(log_s) < 3:
        return 0.5

    slope = float(np.polyfit(log_s, log_f, 1)[0])  # alpha == H for fGN input
    return float(min(0.99, max(0.01, slope)))


def hurst_rs(
    returns: np.ndarray,
    *,
    min_chunk: int = 8,
    n_scales: int = 8,
) -> float:
    """Hurst exponent via the Rescaled-Range (R/S) statistic (Eq. M5).

    Parameters
    ----------
    returns
        1-D array of (log) returns.
    min_chunk
        Smallest sub-series length used in the R/S average.
    n_scales
        Number of log-spaced chunk sizes.

    Returns
    -------
    float
        Estimated ``H`` clipped to ``(0.01, 0.99)``; ``0.5`` fallback if short.

    Notes
    -----
    For each chunk length ``n`` the series is split into non-overlapping
    sub-series; in each we mean-adjust, take the cumulative deviation range
    ``R`` and standard deviation ``S``, and average ``R/S`` over sub-series.
    ``log(E[R/S])`` regressed on ``log n`` has slope ``H``.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < max(2 * min_chunk, 16):
        return 0.5

    max_chunk = n // 2
    if max_chunk <= min_chunk:
        return 0.5
    sizes = np.unique(
        np.floor(
            np.logspace(np.log10(min_chunk), np.log10(max_chunk), n_scales)
        ).astype(int)
    )
    sizes = sizes[sizes >= min_chunk]

    log_n: List[float] = []
    log_rs: List[float] = []
    for size in sizes:
        n_chunks = n // size
        if n_chunks < 1:
            continue
        rs_vals: List[float] = []
        for c in range(n_chunks):
            chunk = r[c * size : (c + 1) * size]
            z = chunk - chunk.mean()
            cum = np.cumsum(z)
            rng = float(cum.max() - cum.min())
            sd = float(chunk.std(ddof=0))
            if sd > 0.0 and rng > 0.0:
                rs_vals.append(rng / sd)
        if rs_vals:
            log_n.append(math.log(size))
            log_rs.append(math.log(float(np.mean(rs_vals))))

    if len(log_n) < 3:
        return 0.5
    slope = float(np.polyfit(log_n, log_rs, 1)[0])
    return float(min(0.99, max(0.01, slope)))


# ===========================================================================
# 2. fBM PATH SIMULATOR (Davies–Harte, Cholesky fallback)
# ===========================================================================


def fbm_simulator(
    n_steps: int,
    hurst: float,
    *,
    n_paths: int = 1,
    length: float = 1.0,
    rng: Optional[np.random.Generator] = None,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Simulate fractional Brownian motion ``B^H`` on ``[0, length]``.

    Primary method: **Davies–Harte** circulant embedding — exact-covariance
    (Eq. M2) generation of the stationary fractional Gaussian noise (fGN)
    increments via FFT, then cumulative-summed to a path.  If the embedding
    is not non-negative-definite (can happen for some ``H``/``n``), falls back
    to an exact **Cholesky** factorisation of the fBM covariance matrix.

    Parameters
    ----------
    n_steps
        Number of increments (path has ``n_steps + 1`` points incl. 0).
    hurst
        Hurst exponent ``H in (0, 1)``.
    n_paths
        Number of independent paths to draw.
    length
        Total time horizon ``T``; increments are scaled by
        ``(T / n_steps)^H`` so ``Var[B^H_T] = T^{2H}`` (Eq. M1, sigma = 1).
    rng / seed
        Seeded ``numpy`` generator for reproducibility.

    Returns
    -------
    np.ndarray
        Shape ``(n_paths, n_steps + 1)`` fBM paths starting at 0.
    """
    if rng is None:
        rng = np.random.default_rng(seed)
    H = float(min(0.999, max(0.001, hurst)))
    n = int(n_steps)
    if n <= 0:
        return np.zeros((n_paths, 1), dtype=float)

    def _fgn_autocov(k: np.ndarray) -> np.ndarray:
        # Autocovariance of unit-variance fGN at lag k (increments of fBM).
        k = k.astype(float)
        return 0.5 * (
            np.abs(k - 1) ** (2 * H)
            - 2.0 * np.abs(k) ** (2 * H)
            + np.abs(k + 1) ** (2 * H)
        )

    fgn: Optional[np.ndarray] = None
    # --- Davies–Harte circulant embedding ---
    try:
        gamma = _fgn_autocov(np.arange(n))
        # Build the circulant first row of size 2(n-1).
        circ = np.concatenate([gamma, gamma[-2:0:-1]])
        eig = np.fft.fft(circ).real
        if np.all(eig > -1e-10):
            eig = np.clip(eig, 0.0, None)
            m = circ.size
            sqrt_eig = np.sqrt(eig)
            out = np.empty((n_paths, n), dtype=float)
            for p in range(n_paths):
                # Two independent Gaussians -> complex spectrum with the
                # required Hermitian symmetry; take the real causal half.
                z = rng.standard_normal(m) + 1j * rng.standard_normal(m)
                w = np.fft.fft(sqrt_eig * z) / math.sqrt(m)
                out[p] = w.real[:n]
            fgn = out
    except Exception:
        fgn = None

    # --- Cholesky fallback (exact, O(n^2) memory) ---
    if fgn is None:
        idx = np.arange(n)
        cov = _fgn_autocov(np.abs(idx[:, None] - idx[None, :]))
        cov[np.diag_indices_from(cov)] += 1e-12
        L = np.linalg.cholesky(cov)
        z = rng.standard_normal((n, n_paths))
        fgn = (L @ z).T  # (n_paths, n)

    scale = (float(length) / n) ** H
    increments = fgn * scale
    paths = np.zeros((n_paths, n + 1), dtype=float)
    paths[:, 1:] = np.cumsum(increments, axis=1)
    return paths


# ===========================================================================
# 3. PHYSICAL PROBABILITIES
# ===========================================================================


def p_phys_endpoint(
    x: float,
    tau: float,
    sigma: float,
    hurst: float,
    *,
    mu: float = 0.0,
) -> float:
    """Endpoint-sign YES probability under fBM (Eq. M6–M7).

    ``P_phys = Phi( (x + mu*tau) / (sigma * tau^H) )`` — the probability that
    the *total* log-move ends positive given accumulated move ``x`` and a
    remaining increment with mean ``mu*tau`` and std ``sigma*tau^H`` (the
    rough ``tau^{2H}`` variance scaling, NOT the Brownian ``tau``).

    Parameters
    ----------
    x
        Accumulated log-move so far, ``ln(S_now / S_open)``.
    tau
        Remaining time fraction to the window end (same units as ``sigma`` is
        calibrated in; here ``tau`` in *bars* and ``sigma`` per-bar).
    sigma
        Per-unit-time volatility of the return process (> 0).
    hurst
        Hurst exponent ``H``.
    mu
        Per-unit-time drift of the log-price (default 0, efficient prior).

    Returns
    -------
    float
        YES probability in ``(0, 1)``.  Degenerate inputs collapse to a
        hard 0/1 on the sign of ``x`` (no time / no vol left).
    """
    H = float(min(0.999, max(0.001, hurst)))
    if tau <= 0.0 or sigma <= 0.0:
        # No remaining randomness: outcome is the sign of the move so far.
        if x > 0.0:
            return 1.0 - 1e-9
        if x < 0.0:
            return 1e-9
        return 0.5
    denom = sigma * (tau ** H)
    if denom <= 0.0:
        return 0.5
    z = (x + mu * tau) / denom
    return float(min(1.0 - 1e-9, max(1e-9, _norm_cdf(z))))


def p_phys_mc_barrier(
    x: float,
    tau: float,
    sigma: float,
    hurst: float,
    barrier: float,
    *,
    direction: str = "up",
    n_paths: int = 2000,
    n_steps: int = 64,
    mu: float = 0.0,
    rng: Optional[np.random.Generator] = None,
    seed: Optional[int] = None,
) -> float:
    """Monte-Carlo first-passage breach probability under fBM (Eq. M8).

    For target/barrier markets (no closed-form fBM first-passage), simulate
    ``n_paths`` fBM continuations of the remaining horizon ``tau`` and estimate
    the fraction that breach ``barrier`` in log-move space relative to the
    window open (``x`` is the move already accumulated).

    Parameters
    ----------
    x
        Accumulated log-move so far (relative to window open).
    tau
        Remaining horizon in the same time units as ``sigma``.
    sigma
        Per-unit-time volatility.
    hurst
        Hurst exponent.
    barrier
        Log-move barrier level (relative to the window open) to breach.
    direction
        ``'up'`` ⇒ breach if running max log-move >= ``barrier``;
        ``'down'`` ⇒ breach if running min log-move <= ``barrier``.
    n_paths, n_steps
        Monte-Carlo resolution.
    mu
        Per-unit-time drift added linearly across the horizon.
    rng / seed
        Reproducible generator.

    Returns
    -------
    float
        Breach probability in ``[0, 1]``.
    """
    if tau <= 0.0 or sigma <= 0.0:
        hit = (x >= barrier) if direction == "up" else (x <= barrier)
        return 1.0 - 1e-9 if hit else 1e-9
    if rng is None:
        rng = np.random.default_rng(seed)
    # fBM paths over [0, tau]; scale handled inside the simulator via length.
    paths = fbm_simulator(
        n_steps, hurst, n_paths=n_paths, length=float(tau), rng=rng
    )  # (n_paths, n_steps+1), unit-sigma
    drift = mu * np.linspace(0.0, float(tau), n_steps + 1)[None, :]
    logmove = x + sigma * paths + drift  # absolute log-move vs window open
    if direction == "up":
        breached = (logmove.max(axis=1) >= barrier)
    else:
        breached = (logmove.min(axis=1) <= barrier)
    p = float(np.mean(breached))
    return float(min(1.0 - 1e-9, max(1e-9, p)))


# ===========================================================================
# 4. INFORMATION DIVERGENCE
# ===========================================================================


def kl_bernoulli(p: float, q: float, *, eps: float = 1e-9) -> float:
    """KL divergence ``KL(Bern(p) || Bern(q))`` in nats (Eq. M9).

    ``p*ln(p/q) + (1-p)*ln((1-p)/(1-q))``.  Both args are clipped to
    ``[eps, 1-eps]`` for numerical safety; returns ``>= 0`` always.
    """
    p = min(1.0 - eps, max(eps, float(p)))
    q = min(1.0 - eps, max(eps, float(q)))
    return float(
        p * math.log(p / q) + (1.0 - p) * math.log((1.0 - p) / (1.0 - q))
    )


# ===========================================================================
# 5. SIZING — ASYMMETRIC FRACTIONAL KELLY
# ===========================================================================


def asym_fractional_kelly(
    p: float,
    ask: float,
    *,
    lam: float,
    cap: float,
    floor: float = 0.0,
) -> float:
    """Asymmetric fractional Kelly fraction for a binary at ask ``ask`` (Eq. M10–M11).

    Full Kelly ``f* = p - (1-p)*ask/(1-ask)``; scaled by the side-specific
    fraction ``lam`` and clipped to ``[0, cap]``.  Returns ``0`` when there is
    no positive edge (``f* <= 0``) or when the scaled fraction is below
    ``floor`` (so fee drag does not eat a vanishing bet).

    Parameters
    ----------
    p
        Win probability for the leg being bought (``P_phys`` of that token).
    ask
        Per-share ask paid (pays 1 on win).  Must be in ``(0, 1)``.
    lam
        Side-specific fractional-Kelly multiplier (``lambda_yes`` / ``lambda_no``).
    cap
        Hard upper bound on the returned fraction (``max_position_frac``).
    floor
        Minimum fraction; below it the function returns 0.

    Returns
    -------
    float
        Fraction of the per-window budget to deploy, in ``[0, cap]``.
    """
    a = float(ask)
    if not (0.0 < a < 1.0):
        return 0.0
    b = (1.0 - a) / a  # net decimal odds
    f_star = p - (1.0 - p) / b  # = p - (1-p)*a/(1-a)
    if f_star <= 0.0:
        return 0.0
    f_used = lam * f_star
    if f_used < floor:
        return 0.0
    return float(min(cap, max(0.0, f_used)))


# ===========================================================================
# PARAMS
# ===========================================================================


@dataclass
class RoughVolKLParams(StrategyParams):
    """Tunable knobs for the Rough-Vol / KL-divergence strategy.

    Optimization-ready ranges are documented inline (and surfaced in the
    module README / SAFE_SCHEMA).  Defaults are deliberately conservative.
    """

    # --- Hurst estimation ---
    hurst_lookback: int = 200      # bars of 5m returns; range [100, 300]
    hurst_method: str = "dfa"      # 'dfa' (primary) | 'rs' | 'avg'
    min_returns: int = 32          # min returns before any estimate; [16, 64]

    # --- volatility / drift for P_phys ---
    sigma_lookback: int = 200      # bars for per-bar sigma; [60, 300]
    sigma_floor: float = 1e-5      # guard against zero vol; [1e-6, 1e-4]
    mu: float = 0.0                # per-bar drift prior; [-1e-4, 1e-4]

    # --- divergence trigger ---
    kl_threshold: float = 0.02     # min KL (nats) to act; range [0.005, 0.10]
    prob_clip: float = 0.02        # clamp P_phys/P_poly off 0/1; [0.005, 0.05]

    # --- asymmetric fractional Kelly ---
    lambda_yes: float = 0.20       # YES-side Kelly fraction; [0.05, 0.50]
    lambda_no: float = 0.12        # NO-side (longshot-shy) fraction; [0.03, 0.30]
    kelly_f_min: float = 0.015     # min Kelly to bother; [0.005, 0.05]

    # --- gating / lifecycle ---
    min_frac_elapsed: float = 0.15   # need some path before trusting x; [0.0, 0.5]
    one_shot_per_window: bool = True # at most one open leg per window-token
    use_binance_path: bool = True    # x from binance_spot (else from mid)
    price_limit_buffer: float = 0.02 # accept benign slippage; reject toxic-adverse; [0.0, 0.05]

    # base-class fields inherited & retuned for this strategy:
    #   max_position_frac (cap on single signal)   default 0.10  -> [0.02, 0.25]
    #   per_window_budget_frac                      default 0.20  -> [0.05, 0.40]
    #   edge_min (above the ~1.8% fee floor)        default 0.02  -> [0.01, 0.06]
    #   min_seconds_to_resolution                   default 0.0   -> [0, 60]


# ===========================================================================
# STRATEGY
# ===========================================================================


@register_strategy("s3_rough_vol_kl")
class RoughVolKLStrategy(Strategy):
    """Rough-volatility fBM ``P_phys`` vs Polymarket ``P_poly``, KL-gated, Kelly-sized.

    Per causal step (one ``market_timeline`` row):

    1. Estimate ``H`` (DFA primary, R/S cross-check) and per-bar ``sigma`` from
       the causal log-return series of ``binance_spot`` (the underlying), using
       a rolling lookback (``hurst_lookback`` / ``sigma_lookback``).
    2. Compute the accumulated log-move ``x = ln(S_now / S_open)`` and the
       remaining time fraction ``tau`` (in bars) to the window end.
    3. ``P_phys = Phi((x + mu*tau)/(sigma*tau^H))`` (Eq. M7) for the UP token;
       the DOWN token's physical prob is ``1 - P_phys``.
    4. Read ``P_poly`` from the book mid of the *token this panel tracks*.
    5. Trade only if ``KL(P_phys || P_poly) > kl_threshold`` AND the modelled
       edge (after the expected bimodal-fill premium) is positive after the
       ``edge_min`` floor.  Size by asymmetric fractional Kelly (Eq. M10–M11).

    The DOWN side is taken either by buying THIS token (if it is the down/NO
    panel) or by emitting ``BUY_NO`` from a YES panel (the engine redirects to
    the peer down token at its ask) — both are legitimate per the contract.
    """

    params_cls = RoughVolKLParams

    def __init__(self, params: Optional[RoughVolKLParams] = None) -> None:
        super().__init__(params)
        # Cached global sigma fallback (per asset) fit in warmup; never a label.
        self._sigma_prior: dict = {}

    # -- optional warmup: a robust per-asset sigma prior (no label leak) -----
    def warmup(self, panels: Sequence) -> None:
        """Fit a per-asset per-bar volatility prior from spot paths only.

        Uses ONLY ``binance_spot`` series (a feature, never the label) to seed
        ``sigma`` when a window is too short for a reliable in-window estimate.
        This is global calibration, not per-window memorisation.
        """
        acc: dict = {}
        for p in panels:
            spot = np.array(
                [r.binance_spot for r in p.timeline if r.binance_spot is not None],
                dtype=float,
            )
            r = _safe_log_returns(spot)
            if r.size:
                acc.setdefault(p.asset, []).append(r)
        for asset, chunks in acc.items():
            allr = np.concatenate(chunks)
            if allr.size >= 8:
                self._sigma_prior[asset] = float(
                    max(self.params.sigma_floor, np.std(allr, ddof=0))
                )

    # -- core per-bar decision ----------------------------------------------
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params  # type: ignore[assignment]
        if not p.enabled:
            return []
        # one open leg per token-window at most
        if p.one_shot_per_window and ctx.open_shares > 0:
            return []

        # need some path elapsed before x is informative
        if ctx.window_size_s and ctx.seconds_to_resolution is not None:
            frac_elapsed = 1.0 - (ctx.seconds_to_resolution / float(ctx.window_size_s))
            if frac_elapsed < p.min_frac_elapsed:
                return []

        # --- build the causal return series (underlying spot preferred) ---
        if p.use_binance_path:
            series = np.array(ctx.history_field("binance_spot"), dtype=float)
        else:
            series = np.array(ctx.history_field("mid"), dtype=float)
        rets = _safe_log_returns(series[-(p.sigma_lookback + 1):])
        if rets.size < p.min_returns:
            return []

        # --- Hurst exponent (rolling) ---
        h_window = _safe_log_returns(series[-(p.hurst_lookback + 1):])
        if p.hurst_method == "rs":
            hurst = hurst_rs(h_window)
        elif p.hurst_method == "avg":
            hurst = 0.5 * (hurst_dfa(h_window) + hurst_rs(h_window))
        else:
            hurst = hurst_dfa(h_window)

        # --- per-bar sigma (consistent with the same return series) ---
        sigma = float(np.std(rets, ddof=0))
        if not math.isfinite(sigma) or sigma < p.sigma_floor:
            sigma = self._sigma_prior.get(ctx.asset, p.sigma_floor)
        sigma = max(sigma, p.sigma_floor)

        # --- accumulated log-move x and remaining horizon tau (in bars) ---
        spot_series = series[np.isfinite(series) & (series > 0.0)]
        if spot_series.size < 2:
            return []
        s_now = float(spot_series[-1])
        s_open = float(spot_series[0])  # window open (history starts at window start)
        if s_open <= 0.0 or s_now <= 0.0:
            return []
        x = math.log(s_now / s_open)

        # remaining time in *bar* units (one feature row ~ one bar of sampling)
        # convert seconds-to-resolution into the same per-bar sigma clock:
        # estimate seconds-per-bar from the causal timestamps.
        sec_per_bar = self._seconds_per_bar(ctx)
        tau_bars = max(0.0, ctx.seconds_to_resolution / sec_per_bar)
        if tau_bars <= 0.0:
            return []

        # --- physical YES probability for the UP token (Eq. M7) ---
        p_up = p_phys_endpoint(x, tau_bars, sigma, hurst, mu=p.mu)

        # physical prob for the token THIS panel tracks
        is_up_panel = (ctx.outcome_side or "YES").upper() == "YES"
        p_phys_token = p_up if is_up_panel else (1.0 - p_up)

        # --- Polymarket implied prob for this token (book mid) ---
        q = ctx.mid
        if q is None:
            # fall back to mid of ask/bid if mid missing
            if ctx.best_ask is not None and ctx.best_bid is not None:
                q = 0.5 * (ctx.best_ask + ctx.best_bid)
            else:
                return []
        q = float(min(1.0 - p.prob_clip, max(p.prob_clip, q)))
        p_phys_token = float(
            min(1.0 - p.prob_clip, max(p.prob_clip, p_phys_token))
        )

        # --- information divergence gate (Eq. M9) ---
        kl = kl_bernoulli(p_phys_token, q)
        if kl < p.kl_threshold:
            return []

        # --- decide side from sign(P_phys - P_poly) ---
        # We want to BUY the token whose physical prob exceeds its price.
        # If p_phys_token > q for THIS token, buy this token; else consider the
        # complementary token (peer / opposite outcome).
        if p_phys_token > q:
            return self._maybe_buy_token(ctx, is_up_panel, p_phys_token, kl, hurst, x)
        # else: this token is overpriced -> the OTHER token is underpriced.
        return self._maybe_buy_peer(ctx, is_up_panel, 1.0 - p_phys_token, kl, hurst, x)

    # -- helpers ------------------------------------------------------------
    def _seconds_per_bar(self, ctx: StrategyContext) -> float:
        """Median inter-row spacing in seconds (the bar clock), >= 1s."""
        hist = ctx.history
        if len(hist) >= 3:
            ts = np.array([r.ts_s for r in hist[-30:]], dtype=float)
            d = np.diff(ts)
            d = d[d > 0.0]
            if d.size:
                return float(max(1.0, np.median(d)))
        return 1.0

    def _gate_edge(self, ctx: StrategyContext, p_win: float, ask: float) -> float:
        """Edge after the expected bimodal-fill premium: ``p_win - exp_fill``.

        Uses the engine-supplied closed-form expected fill (no RNG draw) so the
        modelled edge already prices the slippage + adverse-selection premium.
        """
        exp_fill = ctx.extras["expected_fill_price"]("buy", ask)
        return p_win - exp_fill

    def _maybe_buy_token(
        self,
        ctx: StrategyContext,
        is_up_panel: bool,
        p_win: float,
        kl: float,
        hurst: float,
        x: float,
    ) -> List[Signal]:
        """Buy THIS panel's token (YES if up panel, NO if down panel)."""
        p = self.params  # type: ignore[assignment]
        ask = ctx.best_ask
        if ask is None or not (0.0 < ask < 1.0):
            return []
        edge = self._gate_edge(ctx, p_win, ask)
        if edge < p.edge_min:
            return []
        side = "BUY_YES" if is_up_panel else "BUY_NO"
        lam = p.lambda_yes if is_up_panel else p.lambda_no
        frac = asym_fractional_kelly(
            p_win, ask, lam=lam, cap=p.max_position_frac, floor=p.kelly_f_min
        )
        if frac <= 0.0:
            return []
        slip = float(ctx.extras.get("per_share_slippage", 0.0))
        price_limit = float(min(1.0, ask + slip + p.price_limit_buffer))
        return [
            Signal(
                side=side,  # type: ignore[arg-type]
                size_fraction=frac,
                price_limit=price_limit,
                meta={
                    "strategy_logic": "rough_vol_kl",
                    "p_phys": round(p_win, 4),
                    "p_poly": round(float(ctx.mid or ask), 4),
                    "kl": round(kl, 5),
                    "hurst": round(hurst, 4),
                    "log_move": round(x, 6),
                    "side_taken": side,
                },
            )
        ]

    def _maybe_buy_peer(
        self,
        ctx: StrategyContext,
        is_up_panel: bool,
        p_win_peer: float,
        kl: float,
        hurst: float,
        x: float,
    ) -> List[Signal]:
        """Buy the complementary token via the engine's peer redirect.

        From a YES(up) panel a ``BUY_NO`` is redirected to the peer down token;
        from a NO(down) panel a ``BUY_YES`` is redirected to the peer up token.
        We price against the peer ask snapshot when available.
        """
        p = self.params  # type: ignore[assignment]
        peer = ctx.peer
        if peer is None:
            return []
        peer_ask = peer.get("best_ask")
        if peer_ask is None or not (0.0 < float(peer_ask) < 1.0):
            return []
        peer_ask = float(peer_ask)
        edge = self._gate_edge(ctx, p_win_peer, peer_ask)
        if edge < p.edge_min:
            return []
        # peer of an UP panel is the DOWN token (a NO buy is the down side);
        # peer of a DOWN panel is the UP token (a YES buy).
        if is_up_panel:
            side = "BUY_NO"
            lam = p.lambda_no
        else:
            side = "BUY_YES"
            lam = p.lambda_yes
        frac = asym_fractional_kelly(
            p_win_peer, peer_ask, lam=lam, cap=p.max_position_frac, floor=p.kelly_f_min
        )
        if frac <= 0.0:
            return []
        slip = float(ctx.extras.get("per_share_slippage", 0.0))
        price_limit = float(min(1.0, peer_ask + slip + p.price_limit_buffer))
        return [
            Signal(
                side=side,  # type: ignore[arg-type]
                size_fraction=frac,
                price_limit=price_limit,
                meta={
                    "strategy_logic": "rough_vol_kl_peer",
                    "p_phys_peer": round(p_win_peer, 4),
                    "peer_ask": round(peer_ask, 4),
                    "kl": round(kl, 5),
                    "hurst": round(hurst, 4),
                    "log_move": round(x, 6),
                    "side_taken": side,
                },
            )
        ]


__all__ = [
    "RoughVolKLParams",
    "RoughVolKLStrategy",
    "hurst_dfa",
    "hurst_rs",
    "fbm_simulator",
    "p_phys_endpoint",
    "p_phys_mc_barrier",
    "kl_bernoulli",
    "asym_fractional_kelly",
]
