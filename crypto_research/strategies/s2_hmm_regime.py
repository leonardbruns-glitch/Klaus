"""S2 — HMM Regime Lead-Lag with OBI-driven (non-homogeneous) transitions.

Strategy family
---------------
A regime-switching model of 5-/15-minute crypto returns in which the
*latent regime* (bull / bear / chop) is the driver of next-bar direction and
the **order-book imbalance (OBI)** acts as an *exogenous covariate that warps
the regime-transition probabilities*.  This is a structural, bar-cadence edge:
regimes persist over many bars, and OBI carries information about the *timing*
of regime changes before they are fully expressed in price.

Why this is NON-HFT
-------------------
The unit of decision is one **window** (one 5-min or 15-min bar).  At the close
of a bar we compute the filtered probability that the *next* bar lands in the
bull (or bear) regime, and we take the corresponding binary leg for the next
window.  Nothing here depends on sub-bar latency, queue position, or tick
racing — the edge is the persistence/transition structure of regimes plus the
exogenous OBI tilt, both estimated on bar-cadence statistics.  See module
``base`` for the binding NON-HFT mandate.

================================================================================
MATHEMATICAL CORE
================================================================================

Observation
-----------
Per asset, the bar observation at bar t is

    o_t = r_t                       (1-D emission, log return of the window), or
    o_t = [ r_t , v_t ]             (2-D emission, r_t and realised vol v_t),

where  r_t = ln(close_t / open_t)  is the within-window log return and
v_t = |r_t| (or a rolling RV) is a coarse realised-volatility proxy.

Hidden Markov Model (homogeneous baseline)
------------------------------------------
K latent states S_t in {0..K-1}.  Parameters:
    pi_i        = P(S_1 = i)                                 (initial dist)
    A[i,j]      = P(S_{t+1}=j | S_t=i)                        (transition matrix)
    emission    = N(o_t ; mu_i, Sigma_i)  (diagonal Sigma)   (Gaussian emission)

Forward (alpha) / Backward (beta) recursions, with c_t the scaling constants:
    alpha_1(i)  = pi_i b_i(o_1)               ; c_1 = sum_i alpha_1(i)
    alpha_t(j)  = [ sum_i alpha_{t-1}(i) A[i,j] ] b_j(o_t)
                  scaled by c_t = sum_j (.)
    beta_T(i)   = 1
    beta_t(i)   = sum_j A[i,j] b_j(o_{t+1}) beta_{t+1}(j) / c_{t+1}
    gamma_t(i)  = alpha_t(i) beta_t(i)                       (posterior over S_t)
    xi_t(i,j)   ∝ alpha_t(i) A[i,j] b_j(o_{t+1}) beta_{t+1}(j)   (joint posterior)

Baum-Welch (EM) updates:
    pi_i   = gamma_1(i)
    A[i,j] = sum_t xi_t(i,j) / sum_t gamma_t(i)
    mu_i   = sum_t gamma_t(i) o_t / sum_t gamma_t(i)
    Sigma_i= sum_t gamma_t(i) (o_t-mu_i)(o_t-mu_i)^T / sum_t gamma_t(i)
Log-likelihood = sum_t ln c_t (monotone increasing ⇒ convergence check).

Non-homogeneous (OBI-driven) transitions — the spec's core
----------------------------------------------------------
The transition matrix is made *time-varying* and driven by the exogenous
order-book-imbalance OBI_t (a number in roughly [-1,1]) via a row-wise
multinomial-logit (softmax):

    A_t[i,j] = softmax_j( beta_ij + w_ij * OBI_t )
             = exp(beta_ij + w_ij*OBI_t) / sum_k exp(beta_ik + w_ik*OBI_t).

A_t replaces the constant A in BOTH the forward/backward passes and the xi
recursion; gamma/xi are otherwise identical.  Because OBI_t is *observed* (not
latent) it is a covariate, not part of the emission — this is a classic
input-output / non-homogeneous HMM.

EM with a logistic M-step (the transition update):
For each "from" state i we have a multinomial-logistic regression whose targets
are the expected transition counts xi_t(i,·) and whose single feature is OBI_t.
The expected complete-data Q-function term for row i is

    Q_i = sum_t sum_j xi_t(i,j) * ln A_t[i,j].

Maximising Q_i over (beta_i·, w_i·) is a weighted multinomial-logit fit, solved
by Newton / IRLS on the logits.  We implement a numerically-robust gradient
ascent (optionally Newton) on Q_i; gradients:

    dQ_i/dbeta_ij = sum_t ( xi_t(i,j) - (sum_k xi_t(i,k)) * A_t[i,j] )
    dQ_i/dw_ij    = sum_t OBI_t * ( xi_t(i,j) - (sum_k xi_t(i,k)) * A_t[i,j] )

(One column is fixed as the softmax reference to identify the parameters.)

Documented 2-step approximation (fallback, ``transition_fit='two_step'``)
-------------------------------------------------------------------------
1. Fit a homogeneous Gaussian HMM (Baum-Welch) ⇒ A, gammas, xi.
2. Regress the expected transitions on OBI: for each from-state i fit a
   weighted multinomial logit of the to-state (weighted by xi_t(i,j)) on OBI_t.
This is *not* the joint MLE — the emission/regime posteriors are held fixed
from the homogeneous fit — but it is fast, stable, and a good initialiser.  It
is labelled an approximation wherever it is used.

================================================================================
ENTRY / EXIT RULES  (explicit, >0.75 gate)
================================================================================
Define the *up regime* u as the fitted state with the largest mean return mu_i
(2-D: largest mu over the return dimension); the *down regime* d as the
smallest.  At the close of each window (filtered on causal data <= t) compute
the one-step-ahead transition-into probability using the OBI-warped A_t:

    P_up   = P(S_{next} = u | o_{1..t}, OBI_t) = sum_i alpha_hat_t(i) A_t[i, u]
    P_down = P(S_{next} = d | o_{1..t}, OBI_t) = sum_i alpha_hat_t(i) A_t[i, d]

where alpha_hat_t is the *normalised* filtered state distribution at t.

    P_up   > p_enter (default 0.75)  ⇒ BUY_YES   (long the UP binary)
    P_down > p_enter (default 0.75)  ⇒ BUY_NO    (the spanning peer DOWN binary)

A trade is only taken if the **post-fee, post-fill modelled edge** clears
``edge_min`` (ruin floor): the binary pays 1 on success, costs the modelled
fill price f; expected edge = P_regime - f - fee_per_share.

Exit: hold to window resolution by default.  If a leg is open and the regime
signal *flips* — the filtered P of the entered regime falls below
``p_exit`` (default 0.5) at a later step of the SAME window — emit FLAT (early
exit at the bid).  Resolution settlement is otherwise automatic.

================================================================================
LEAD-LAG (optional, documented)
================================================================================
BTC is the market beta; ETH/SOL lag it.  When ``use_cross_asset`` is on, the
exogenous transition covariate for ETH/SOL is augmented with BTC's most-recent
OBI / return:  OBI_eff = OBI_self + lead_weight * OBI_BTC(t).  This is a single
extra additive covariate in the same softmax (kept optional; default off so the
core single-covariate model is the default contract).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.schema import MarketTimelineRow, WindowPanel
from .base import (
    Signal,
    Strategy,
    StrategyContext,
    StrategyParams,
    register_strategy,
)

# Optional accelerated baselines (must degrade gracefully — see README).
try:  # pragma: no cover - exercised only when the optional dep is installed
    from hmmlearn.hmm import GaussianHMM as _HMMLearnGaussianHMM  # type: ignore

    _HAVE_HMMLEARN = True
except Exception:  # pragma: no cover
    _HMMLearnGaussianHMM = None  # type: ignore
    _HAVE_HMMLEARN = False

try:  # pragma: no cover
    import statsmodels.api as _sm  # type: ignore  # noqa: F401

    _HAVE_STATSMODELS = True
except Exception:  # pragma: no cover
    _sm = None  # type: ignore
    _HAVE_STATSMODELS = False


_LOG2PI = math.log(2.0 * math.pi)
_EPS = 1e-12


# ===========================================================================
# Gaussian (homogeneous) HMM — self-contained numpy forward-backward + EM
# ===========================================================================
class GaussianHMM:
    """K-state Gaussian HMM with diagonal covariances (numpy Baum-Welch).

    Self-contained implementation of the forward-backward algorithm and the
    EM (Baum-Welch) parameter updates documented in the module header.  Works
    for 1-D or D-D diagonal-Gaussian emissions.  No external dependencies
    beyond numpy; if ``hmmlearn`` is installed it can be used as an optional
    cross-check baseline via :meth:`fit_with_hmmlearn`.

    Parameters
    ----------
    n_states
        Number of latent regimes K (2..4 in practice).
    n_iter
        Maximum Baum-Welch iterations.
    tol
        Convergence tolerance on the per-iteration log-likelihood gain.
    covariance_floor
        Lower bound on each diagonal variance (numerical safety / prevents a
        state collapsing onto a single point).
    seed
        RNG seed for k-means-lite initialisation.
    """

    def __init__(
        self,
        n_states: int = 3,
        *,
        n_iter: int = 50,
        tol: float = 1e-4,
        covariance_floor: float = 1e-9,
        seed: int = 0,
    ) -> None:
        self.K = int(n_states)
        self.n_iter = int(n_iter)
        self.tol = float(tol)
        self.cov_floor = float(covariance_floor)
        self.seed = int(seed)
        # parameters (populated by fit)
        self.startprob_: Optional[np.ndarray] = None  # (K,)
        self.transmat_: Optional[np.ndarray] = None  # (K, K)
        self.means_: Optional[np.ndarray] = None  # (K, D)
        self.vars_: Optional[np.ndarray] = None  # (K, D) diagonal
        self.loglik_: float = -np.inf
        self.n_features_: int = 1

    # -- initialisation ----------------------------------------------------
    def _init_params(self, X: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        T, D = X.shape
        self.n_features_ = D
        # spread initial means along sorted quantiles of the 1st feature so the
        # states start ordered by return (gives a stable up/down labelling).
        order_feat = X[:, 0]
        qs = np.linspace(0.1, 0.9, self.K)
        means = np.empty((self.K, D))
        for k, q in enumerate(qs):
            thr = np.quantile(order_feat, q)
            idx = np.argmin(np.abs(order_feat - thr))
            means[k] = X[idx]
        # jitter to break ties
        means += rng.normal(0.0, 1e-6, size=means.shape)
        self.means_ = means
        var = X.var(axis=0) + self.cov_floor
        self.vars_ = np.tile(np.maximum(var, self.cov_floor), (self.K, 1))
        self.startprob_ = np.full(self.K, 1.0 / self.K)
        # mildly sticky transitions (regimes persist) as a prior init
        A = np.full((self.K, self.K), 0.1 / max(self.K - 1, 1))
        np.fill_diagonal(A, 0.9)
        self.transmat_ = A

    # -- emission log-density ---------------------------------------------
    def _log_emission(self, X: np.ndarray) -> np.ndarray:
        """Return (T, K) log N(x_t; mu_k, diag(var_k))."""
        assert self.means_ is not None and self.vars_ is not None
        T = X.shape[0]
        D = self.n_features_
        logB = np.empty((T, self.K))
        for k in range(self.K):
            var = self.vars_[k]
            diff = X - self.means_[k]
            quad = np.sum(diff * diff / var, axis=1)
            logdet = np.sum(np.log(var))
            logB[:, k] = -0.5 * (D * _LOG2PI + logdet + quad)
        return logB

    # -- forward-backward (scaled) ----------------------------------------
    @staticmethod
    def _forward_backward(
        logB: np.ndarray, A: np.ndarray, pi: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """Scaled forward-backward for a HOMOGENEOUS transition matrix A.

        Returns (alpha_hat, beta_hat, c, loglik) with alpha_hat the normalised
        filtered distribution at each t and c the scaling constants.
        """
        T, K = logB.shape
        B = np.exp(logB - logB.max(axis=1, keepdims=True))  # stabilised
        scale_log = logB.max(axis=1)  # add back into loglik
        alpha = np.zeros((T, K))
        c = np.zeros(T)
        alpha[0] = pi * B[0]
        c[0] = alpha[0].sum() + _EPS
        alpha[0] /= c[0]
        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            c[t] = alpha[t].sum() + _EPS
            alpha[t] /= c[t]
        beta = np.zeros((T, K))
        beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            b = A @ (B[t + 1] * beta[t + 1])
            # self-normalise per step: the constant cancels in the gamma/xi
            # renormalisation in fit(), and avoids the /c[t+1] underflow that
            # overflowed beta on heavy-tailed real returns.
            bmax = b.max()
            beta[t] = b / bmax if bmax > 0 else b
        loglik = float(np.sum(np.log(c)) + np.sum(scale_log))
        return alpha, beta, c, loglik

    # -- fit (Baum-Welch) --------------------------------------------------
    def fit(self, X: np.ndarray) -> "GaussianHMM":
        """Baum-Welch EM fit on a (T, D) observation matrix (or (T,) 1-D)."""
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X[:, None]
        if X.shape[0] < self.K + 2:
            # too few points: fall back to a trivial 1-blob model
            self._init_params(np.vstack([X, X]) if X.shape[0] else np.zeros((2, 1)))
            return self
        self._init_params(X)
        assert self.transmat_ is not None and self.startprob_ is not None
        prev_ll = -np.inf
        for _ in range(self.n_iter):
            logB = self._log_emission(X)
            alpha, beta, c, ll = self._forward_backward(
                logB, self.transmat_, self.startprob_
            )
            self.loglik_ = ll
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True) + _EPS
            # xi_t(i,j) via stabilised emissions
            B = np.exp(logB - logB.max(axis=1, keepdims=True))
            xi_sum = np.zeros((self.K, self.K))
            for t in range(X.shape[0] - 1):
                m = (
                    alpha[t][:, None]
                    * self.transmat_
                    * (B[t + 1] * beta[t + 1])[None, :]
                )
                m /= m.sum() + _EPS
                xi_sum += m
            # updates
            self.startprob_ = gamma[0] / (gamma[0].sum() + _EPS)
            denom = gamma[:-1].sum(axis=0) + _EPS
            self.transmat_ = xi_sum / denom[:, None]
            self.transmat_ /= self.transmat_.sum(axis=1, keepdims=True) + _EPS
            gsum = gamma.sum(axis=0) + _EPS
            self.means_ = (gamma.T @ X) / gsum[:, None]
            for k in range(self.K):
                diff = X - self.means_[k]
                self.vars_[k] = np.maximum(
                    (gamma[:, k][:, None] * diff * diff).sum(axis=0) / gsum[k],
                    self.cov_floor,
                )
            if ll - prev_ll < self.tol and _ > 0:
                break
            prev_ll = ll
        return self

    # -- optional hmmlearn baseline ---------------------------------------
    def fit_with_hmmlearn(self, X: np.ndarray) -> "GaussianHMM":  # pragma: no cover
        """Fit via hmmlearn if available; copy params back into this object.

        Used only as an optional cross-check baseline.  Falls back to the
        numpy :meth:`fit` if hmmlearn is not installed.
        """
        if not _HAVE_HMMLEARN:
            return self.fit(X)
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X[:, None]
        model = _HMMLearnGaussianHMM(
            n_components=self.K, covariance_type="diag", n_iter=self.n_iter
        )
        model.fit(X)
        self.startprob_ = np.asarray(model.startprob_)
        self.transmat_ = np.asarray(model.transmat_)
        self.means_ = np.asarray(model.means_)
        self.vars_ = np.maximum(np.asarray(model.covars_), self.cov_floor)
        self.n_features_ = X.shape[1]
        self.loglik_ = float(model.score(X))
        return self

    # -- inference helpers -------------------------------------------------
    def filter(self, X: np.ndarray) -> Tuple[np.ndarray, float]:
        """Causal filtered state distribution alpha_hat over (T, D) data.

        Returns (alpha_hat (T,K) normalised, loglik).
        """
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X[:, None]
        assert self.transmat_ is not None and self.startprob_ is not None
        logB = self._log_emission(X)
        alpha, _, _, ll = self._forward_backward(
            logB, self.transmat_, self.startprob_
        )
        return alpha, ll

    def up_down_states(self) -> Tuple[int, int]:
        """Return (up_state, down_state) by the sign/order of the mean return.

        The up state has the largest mean of feature 0 (the return); the down
        state the smallest.
        """
        assert self.means_ is not None
        mu0 = self.means_[:, 0]
        return int(np.argmax(mu0)), int(np.argmin(mu0))


# ===========================================================================
# Non-homogeneous (OBI-driven) HMM
# ===========================================================================
class NonHomogeneousHMM:
    """HMM with OBI-driven, time-varying transition matrices.

    Transition logits are an affine function of the exogenous covariate(s)
    ``x_t`` (OBI, optionally + cross-asset lead), passed through a row-wise
    softmax::

        A_t[i, j] = softmax_j( beta[i, j] + w[i, j] . x_t ).

    The emission model is the same diagonal-Gaussian as :class:`GaussianHMM`.
    Fitting offers two modes:

    * ``transition_fit='joint'`` — full EM: E-step computes gamma/xi under the
      time-varying A_t; M-step does a gradient ascent on the per-row
      multinomial-logit Q-function (the exact MLE direction documented in the
      module header).
    * ``transition_fit='two_step'`` — the documented APPROXIMATION: fit a
      homogeneous HMM first, then regress its expected transitions on OBI
      (multinomial logit weighted by xi).  Faster / more stable; not the joint
      optimum.

    Parameters
    ----------
    n_states, n_iter, tol, covariance_floor, seed
        As :class:`GaussianHMM`.
    transition_fit
        ``'joint'`` or ``'two_step'``.
    logit_lr, logit_iter
        Step size / inner iterations for the gradient M-step on the transition
        logits.
    n_covariates
        Dimension of the exogenous covariate x_t (1 = OBI only; 2 = OBI +
        cross-asset lead).
    """

    def __init__(
        self,
        n_states: int = 3,
        *,
        n_iter: int = 40,
        tol: float = 1e-4,
        covariance_floor: float = 1e-9,
        seed: int = 0,
        transition_fit: str = "joint",
        logit_lr: float = 0.25,
        logit_iter: int = 30,
        n_covariates: int = 1,
    ) -> None:
        self.K = int(n_states)
        self.n_iter = int(n_iter)
        self.tol = float(tol)
        self.cov_floor = float(covariance_floor)
        self.seed = int(seed)
        self.transition_fit = str(transition_fit)
        self.logit_lr = float(logit_lr)
        self.logit_iter = int(logit_iter)
        self.M = int(n_covariates)
        # emission params (shared with the Gaussian model)
        self.startprob_: Optional[np.ndarray] = None
        self.means_: Optional[np.ndarray] = None
        self.vars_: Optional[np.ndarray] = None
        # transition logits: beta (K,K), w (K,K,M)
        self.beta_: Optional[np.ndarray] = None
        self.w_: Optional[np.ndarray] = None
        self.loglik_: float = -np.inf
        self.n_features_: int = 1
        self._gauss = GaussianHMM(
            n_states=n_states,
            n_iter=n_iter,
            tol=tol,
            covariance_floor=covariance_floor,
            seed=seed,
        )

    # -- transition matrix at a covariate value ---------------------------
    def transition_at(self, x: np.ndarray) -> np.ndarray:
        """A_t (K,K) = row-softmax(beta + w . x) for covariate vector x (M,)."""
        assert self.beta_ is not None and self.w_ is not None
        x = np.atleast_1d(np.asarray(x, dtype=float))
        logits = self.beta_ + self.w_ @ x  # (K,K)
        logits = logits - logits.max(axis=1, keepdims=True)
        A = np.exp(logits)
        A /= A.sum(axis=1, keepdims=True) + _EPS
        return A

    def _all_transitions(self, Xcov: np.ndarray) -> np.ndarray:
        """Stack of A_t over time: returns (T, K, K)."""
        T = Xcov.shape[0]
        At = np.empty((T, self.K, self.K))
        for t in range(T):
            At[t] = self.transition_at(Xcov[t])
        return At

    # -- forward-backward with time-varying transitions -------------------
    def _forward_backward_nh(
        self, logB: np.ndarray, At: np.ndarray, pi: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """Scaled forward-backward with per-step transition A_t (uses A_{t}).

        Convention: the transition from t to t+1 uses ``At[t]`` (the covariate
        observed at t drives the move into t+1).
        """
        T, K = logB.shape
        B = np.exp(logB - logB.max(axis=1, keepdims=True))
        scale_log = logB.max(axis=1)
        alpha = np.zeros((T, K))
        c = np.zeros(T)
        alpha[0] = pi * B[0]
        c[0] = alpha[0].sum() + _EPS
        alpha[0] /= c[0]
        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ At[t - 1]) * B[t]
            c[t] = alpha[t].sum() + _EPS
            alpha[t] /= c[t]
        beta = np.zeros((T, K))
        beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            b = At[t] @ (B[t + 1] * beta[t + 1])
            # self-normalise per step (cancels in the gamma/xi renormalisation);
            # avoids the /c[t+1] underflow that overflowed beta on heavy-tailed
            # real returns.
            bmax = b.max()
            beta[t] = b / bmax if bmax > 0 else b
        loglik = float(np.sum(np.log(c)) + np.sum(scale_log))
        return alpha, beta, c, loglik

    # -- gradient M-step on transition logits -----------------------------
    def _update_transition_logits(
        self, xi: np.ndarray, Xcov: np.ndarray
    ) -> None:
        """Gradient ascent on Q_i for each from-state i.

        xi : (T-1, K, K) expected joint transition posteriors.
        Xcov : (T, M) covariates (transition t->t+1 uses Xcov[t]).

        Gradients (per row i, column j>0; column 0 = softmax reference):
            dQ/dbeta_ij = sum_t ( xi_t[i,j] - g_t[i] * A_t[i,j] )
            dQ/dw_ij    = sum_t x_t * ( xi_t[i,j] - g_t[i] * A_t[i,j] )
        with g_t[i] = sum_k xi_t[i,k].
        """
        assert self.beta_ is not None and self.w_ is not None
        Tm1 = xi.shape[0]
        Xc = Xcov[:Tm1]  # covariate driving each transition
        g = xi.sum(axis=2)  # (T-1, K)
        for _ in range(self.logit_iter):
            # current A_t for all t
            grad_beta = np.zeros_like(self.beta_)
            grad_w = np.zeros_like(self.w_)
            for t in range(Tm1):
                A = self.transition_at(Xc[t])  # (K,K)
                resid = xi[t] - g[t][:, None] * A  # (K,K)
                grad_beta += resid
                grad_w += resid[:, :, None] * Xc[t][None, None, :]
            # hold column 0 as reference (identifiability): zero its gradient
            grad_beta[:, 0] = 0.0
            grad_w[:, 0, :] = 0.0
            step = self.logit_lr / max(Tm1, 1)
            self.beta_ += step * grad_beta
            self.w_ += step * grad_w
            # keep reference column pinned at 0
            self.beta_[:, 0] = 0.0
            self.w_[:, 0, :] = 0.0

    def _init_logits_from_A(self, A: np.ndarray) -> None:
        """Seed beta from a homogeneous A (log-ratio to reference col 0); w=0."""
        A = np.clip(A, _EPS, 1.0)
        beta = np.log(A) - np.log(A[:, [0]])  # reference col 0
        beta[:, 0] = 0.0
        self.beta_ = beta
        self.w_ = np.zeros((self.K, self.K, self.M))

    # -- fit ---------------------------------------------------------------
    def fit(self, X: np.ndarray, Xcov: np.ndarray) -> "NonHomogeneousHMM":
        """Fit emissions + OBI-driven transitions.

        Parameters
        ----------
        X : (T, D) or (T,)
            Emission observations (returns, optionally with realised vol).
        Xcov : (T, M) or (T,)
            Exogenous transition covariates aligned to X (OBI[, lead]).
        """
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X[:, None]
        Xcov = np.asarray(Xcov, dtype=float)
        if Xcov.ndim == 1:
            Xcov = Xcov[:, None]
        self.M = Xcov.shape[1]
        self.n_features_ = X.shape[1]

        # 1) homogeneous Gaussian HMM bootstraps the emissions + an A seed.
        self._gauss.fit(X)
        self.means_ = np.array(self._gauss.means_, dtype=float)
        self.vars_ = np.array(self._gauss.vars_, dtype=float)
        self.startprob_ = np.array(self._gauss.startprob_, dtype=float)
        self._init_logits_from_A(np.array(self._gauss.transmat_, dtype=float))

        if X.shape[0] < self.K + 3:
            return self

        if self.transition_fit == "two_step":
            # APPROXIMATION: emissions/posteriors fixed from the homogeneous
            # fit; regress the expected transitions on OBI once.
            xi = self._expected_xi(X, Xcov, homogeneous=True)
            self._update_transition_logits(xi, Xcov)
            self.loglik_ = self._score(X, Xcov)
            return self

        # joint EM
        prev_ll = -np.inf
        for _ in range(self.n_iter):
            At = self._all_transitions(Xcov)
            logB = self._log_emission(X)
            alpha, beta, c, ll = self._forward_backward_nh(
                logB, At, self.startprob_
            )
            self.loglik_ = ll
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True) + _EPS
            B = np.exp(logB - logB.max(axis=1, keepdims=True))
            xi = np.zeros((X.shape[0] - 1, self.K, self.K))
            for t in range(X.shape[0] - 1):
                m = (
                    alpha[t][:, None]
                    * At[t]
                    * (B[t + 1] * beta[t + 1])[None, :]
                )
                m /= m.sum() + _EPS
                xi[t] = m
            # emission M-step (standard weighted Gaussian)
            self.startprob_ = gamma[0] / (gamma[0].sum() + _EPS)
            gsum = gamma.sum(axis=0) + _EPS
            self.means_ = (gamma.T @ X) / gsum[:, None]
            for k in range(self.K):
                diff = X - self.means_[k]
                self.vars_[k] = np.maximum(
                    (gamma[:, k][:, None] * diff * diff).sum(axis=0) / gsum[k],
                    self.cov_floor,
                )
            # transition M-step (gradient ascent on logits)
            self._update_transition_logits(xi, Xcov)
            if ll - prev_ll < self.tol and _ > 0:
                break
            prev_ll = ll
        return self

    def _log_emission(self, X: np.ndarray) -> np.ndarray:
        assert self.means_ is not None and self.vars_ is not None
        T = X.shape[0]
        D = self.n_features_
        logB = np.empty((T, self.K))
        for k in range(self.K):
            var = self.vars_[k]
            diff = X - self.means_[k]
            quad = np.sum(diff * diff / var, axis=1)
            logdet = np.sum(np.log(var))
            logB[:, k] = -0.5 * (D * _LOG2PI + logdet + quad)
        return logB

    def _expected_xi(
        self, X: np.ndarray, Xcov: np.ndarray, *, homogeneous: bool
    ) -> np.ndarray:
        """E-step xi (T-1,K,K) under current transitions."""
        logB = self._log_emission(X)
        if homogeneous:
            A = self.transition_at(np.zeros(self.M))
            At = np.repeat(A[None], X.shape[0], axis=0)
        else:
            At = self._all_transitions(Xcov)
        alpha, beta, c, _ = self._forward_backward_nh(logB, At, self.startprob_)
        B = np.exp(logB - logB.max(axis=1, keepdims=True))
        xi = np.zeros((X.shape[0] - 1, self.K, self.K))
        for t in range(X.shape[0] - 1):
            m = alpha[t][:, None] * At[t] * (B[t + 1] * beta[t + 1])[None, :]
            m /= m.sum() + _EPS
            xi[t] = m
        return xi

    def _score(self, X: np.ndarray, Xcov: np.ndarray) -> float:
        logB = self._log_emission(X)
        At = self._all_transitions(Xcov)
        _, _, _, ll = self._forward_backward_nh(logB, At, self.startprob_)
        return float(ll)

    # -- inference ---------------------------------------------------------
    def filter(
        self, X: np.ndarray, Xcov: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """Causal filtered state distribution under OBI-driven transitions.

        Returns (alpha_hat (T,K) normalised, loglik).
        """
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X[:, None]
        Xcov = np.asarray(Xcov, dtype=float)
        if Xcov.ndim == 1:
            Xcov = Xcov[:, None]
        assert self.startprob_ is not None
        logB = self._log_emission(X)
        At = self._all_transitions(Xcov)
        alpha, _, _, ll = self._forward_backward_nh(logB, At, self.startprob_)
        return alpha, ll

    def up_down_states(self) -> Tuple[int, int]:
        """(up_state, down_state) by the mean of feature 0 (the return)."""
        assert self.means_ is not None
        mu0 = self.means_[:, 0]
        return int(np.argmax(mu0)), int(np.argmin(mu0))

    def predict_next_regime(
        self, alpha_last: np.ndarray, obi_now: np.ndarray
    ) -> np.ndarray:
        """P(S_{next}=j | data, OBI_now) = sum_i alpha_last_i * A_now[i,j].

        ``alpha_last`` is the normalised filtered state distribution at t;
        ``obi_now`` is the covariate observed at t.  Returns a (K,) vector.
        """
        A = self.transition_at(np.atleast_1d(obi_now))
        v = alpha_last @ A
        v = v / (v.sum() + _EPS)
        return v


# ===========================================================================
# Strategy params
# ===========================================================================
@dataclass
class HmmRegimeParams(StrategyParams):
    """Parameters for the HMM regime lead-lag strategy.

    Optimization-ready: each knob lists a sensible search range in its comment.

    Attributes
    ----------
    n_states
        Number of latent regimes K.  Range: 2..4.
    emission_2d
        If True use 2-D emission [r_t, realised_vol_t]; else 1-D [r_t].
    transition_fit
        ``'joint'`` (full gradient-EM) or ``'two_step'`` (documented approx).
    p_enter
        Transition-into probability gate to OPEN a leg.  Range: 0.65..0.90.
    p_exit
        If the entered regime's filtered prob falls below this mid-window,
        emit FLAT.  Range: 0.35..0.55.
    use_cross_asset
        Augment ETH/SOL transition covariate with BTC OBI (lead-lag).
    lead_weight
        Weight on the BTC lead covariate.  Range: 0.0..1.0.
    min_train_windows
        Minimum bars per asset before the model is considered fit.  Range:
        80..400.
    obi_clip
        Clip OBI into [-obi_clip, obi_clip] before use.  Range: 1.0..3.0.
    logit_lr
        Gradient step for the transition M-step.  Range: 0.05..0.5.
    n_iter
        Max EM iterations.  Range: 20..80.
    act_seconds_to_resolution
        (legacy; retained for the exit path) window-end proximity that the exit
        check may use.  Range: 20..120.
    act_within_open_s
        Emit the OPEN decision only within this many seconds of the window's
        OPEN.  The forecast is made from regimes filtered over COMPLETED bars
        (through w-1) and traded on window w's own token, so the forecast
        horizon matches the settled instrument (no w→w+1 mismatch).  Acting near
        the open also means we bet on the full open→close move.  Range: 30..150.
    bar_history_len
        Number of recent *completed* bars (windows) kept per asset and prepended
        to the current causal partial bar before forward-filtering, so the
        filter respects cross-window regime persistence (a 1-bar filter would
        discard the Markov structure).  Range: 10..60.
    """

    n_states: int = 3
    emission_2d: bool = True
    transition_fit: str = "joint"
    p_enter: float = 0.75
    p_exit: float = 0.50
    use_cross_asset: bool = False
    lead_weight: float = 0.5
    min_train_windows: int = 120
    obi_clip: float = 2.0
    logit_lr: float = 0.25
    n_iter: int = 40
    act_seconds_to_resolution: float = 60.0
    act_within_open_s: float = 120.0
    bar_history_len: int = 30
    # sizing defaults tuned for a structural, lower-frequency edge
    max_position_frac: float = 0.10
    per_window_budget_frac: float = 0.20
    edge_min: float = 0.03


# ===========================================================================
# The Strategy
# ===========================================================================
@register_strategy("s2_hmm_regime")
class S2HmmRegimeStrategy(Strategy):
    """HMM regime lead-lag with OBI-driven non-homogeneous transitions.

    Pipeline
    --------
    * :meth:`warmup` — build a per-asset *bar stream* from the panel set (one
      bar = one window: return r and OBI from the window's own causal
      features), then fit a :class:`NonHomogeneousHMM` per asset.  This is
      UNSUPERVISED on the bar returns — it never reads ``label_resolved_yes``
      and never memorises a per-window outcome (no-leakage compliant).
    * :meth:`on_step` — near the close of the *current* window, reconstruct the
      causal observation/covariate history of the window seen so far,
      forward-filter to the latest state distribution, and use the OBI-warped
      A_now to compute P(next regime = up/down).  Fire BUY_YES / BUY_NO past
      ``p_enter`` if the post-fee/fill modelled edge clears ``edge_min``.
      Mid-window regime collapse below ``p_exit`` ⇒ FLAT.

    The per-window observation is built from the timeline rows themselves
    (intra-window return path + OBI), so the decision at the close of window w
    is a true one-step-ahead forecast for window w+1's direction — bar
    cadence, no look-ahead.
    """

    params_cls = HmmRegimeParams

    def __init__(self, params: Optional[HmmRegimeParams] = None) -> None:
        super().__init__(params)
        self.params: HmmRegimeParams
        # per-asset fitted models
        self._models: Dict[str, NonHomogeneousHMM] = {}
        self._up_down: Dict[str, Tuple[int, int]] = {}
        # latest BTC OBI for the cross-asset lead covariate (causal, updated
        # as events stream through on_step)
        self._btc_obi: float = 0.0
        # remember which (strategy) tokens we've already acted on per window
        self._acted: set = set()
        # per-asset rolling history of COMPLETED bars (emission vec, covariate
        # vec).  Prepended to the current causal partial bar at decision time
        # so the forward-filter keeps the cross-window Markov structure rather
        # than collapsing a 1-bar filter onto the start distribution.
        self._bar_hist: Dict[str, List[Tuple[List[float], List[float]]]] = {}
        # window_end_ts already folded into the rolling history (avoid double
        # counting when both UP and DOWN panels of a window close).
        self._folded_we: Dict[str, set] = {}

    # ------------------------------------------------------------------
    # Feature extraction (shared by warmup and live)
    # ------------------------------------------------------------------
    def _bar_return(self, rows: Sequence[MarketTimelineRow]) -> float:
        """Window log-return from the causal binance_spot path.

        Uses the first and last available ``binance_spot`` in the slice; falls
        back to ``binance_ret_5m_pct`` when spot is missing.
        """
        spots = [r.binance_spot for r in rows if r.binance_spot is not None]
        if len(spots) >= 2 and spots[0] > 0 and spots[-1] > 0:
            return float(math.log(spots[-1] / spots[0]))
        for r in reversed(rows):
            if r.binance_ret_5m_pct is not None:
                return float(r.binance_ret_5m_pct) / 100.0
        return 0.0

    def _bar_vol(self, rows: Sequence[MarketTimelineRow]) -> float:
        """Coarse realised-vol proxy: std of step log-returns of the spot."""
        spots = [r.binance_spot for r in rows if r.binance_spot is not None]
        if len(spots) >= 3:
            arr = np.asarray(spots, dtype=float)
            rets = np.diff(np.log(np.clip(arr, _EPS, None)))
            if rets.size:
                return float(np.std(rets))
        # fallback: absolute return
        return abs(self._bar_return(rows))

    def _obi(self, rows: Sequence[MarketTimelineRow]) -> float:
        """Latest causal order-book imbalance (top-3), clipped."""
        val = 0.0
        for r in reversed(rows):
            if r.ob_imb_top3 is not None:
                val = float(r.ob_imb_top3)
                break
        c = self.params.obi_clip
        return float(np.clip(val, -c, c))

    def _emission_vec(self, rows: Sequence[MarketTimelineRow]) -> List[float]:
        r = self._bar_return(rows)
        if self.params.emission_2d:
            return [r, self._bar_vol(rows)]
        return [r]

    def _covariate_vec(self, asset: str, obi_self: float) -> List[float]:
        """Build the transition covariate (OBI, optionally + BTC lead)."""
        if self.params.use_cross_asset and asset != "BTC":
            return [obi_self, self.params.lead_weight * self._btc_obi]
        if self.params.use_cross_asset:
            return [obi_self, 0.0]
        return [obi_self]

    def _filter_sequence(
        self, asset: str, cur_emis: List[float], cur_cov: List[float]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Assemble the causal (obs, cov) sequence for the forward filter.

        Prepends the per-asset rolling history of COMPLETED bars (built only
        from windows that have already settled — strictly causal) to the
        current window's partial-bar observation.  This preserves the
        cross-window Markov/persistence structure the HMM was fit on; a 1-bar
        filter would otherwise collapse onto the start distribution and discard
        all regime memory.
        """
        hist = self._bar_hist.get(asset, [])
        if hist:
            keep = hist[-self.params.bar_history_len :]
            emis_seq = [e for (e, _) in keep] + [cur_emis]
            cov_seq = [c for (_, c) in keep] + [cur_cov]
        else:
            emis_seq = [cur_emis]
            cov_seq = [cur_cov]
        return (
            np.array(emis_seq, dtype=float),
            np.array(cov_seq, dtype=float),
        )

    # ------------------------------------------------------------------
    # Warmup: per-asset bar stream + HMM fit (unsupervised, no leakage)
    # ------------------------------------------------------------------
    def warmup(self, panels: Sequence[WindowPanel]) -> None:
        """Fit one :class:`NonHomogeneousHMM` per asset on the bar stream.

        A *bar* is one window's (return, vol, OBI) computed from that window's
        own feature timeline.  Bars are ordered by ``window_end_ts`` so the
        HMM learns the cross-window regime persistence and the OBI→transition
        coupling.  No outcome labels are consumed: the fit is unsupervised on
        returns, satisfying the no-look-ahead mandate.
        """
        p = self.params
        # collect bars per asset, ordered by window end
        per_asset: Dict[str, List[Tuple[int, List[float], float]]] = {}
        # also keep BTC OBI per window_end_ts for the cross-asset lead
        btc_obi_by_we: Dict[int, float] = {}
        for panel in panels:
            if not panel.is_up_token:
                continue  # one bar per window: use the UP panel's timeline
            rows = panel.timeline
            if not rows:
                continue
            emis = self._emission_vec(rows)
            obi = self._obi(rows)
            per_asset.setdefault(panel.asset, []).append(
                (int(panel.window_end_ts), emis, obi)
            )
            if panel.asset == "BTC":
                btc_obi_by_we[int(panel.window_end_ts)] = obi

        for asset, bars in per_asset.items():
            bars.sort(key=lambda b: b[0])
            if len(bars) < p.min_train_windows:
                # still fit on what we have so the model is usable, but it will
                # be a weaker estimate; callers can raise min_train_windows.
                if len(bars) < self.params.n_states + 3:
                    continue
            X = np.array([b[1] for b in bars], dtype=float)
            obis = np.array([b[2] for b in bars], dtype=float)
            if p.use_cross_asset and asset != "BTC":
                lead = np.array(
                    [p.lead_weight * btc_obi_by_we.get(b[0], 0.0) for b in bars]
                )
                Xcov = np.column_stack([obis, lead])
            elif p.use_cross_asset:
                Xcov = np.column_stack([obis, np.zeros(len(obis))])
            else:
                Xcov = obis[:, None]
            model = NonHomogeneousHMM(
                n_states=p.n_states,
                n_iter=p.n_iter,
                transition_fit=p.transition_fit,
                logit_lr=p.logit_lr,
                seed=self.seed_for(asset),
                n_covariates=Xcov.shape[1],
            )
            model.fit(X, Xcov)
            self._models[asset] = model
            self._up_down[asset] = model.up_down_states()

    @staticmethod
    def seed_for(asset: str) -> int:
        return abs(hash(asset)) % 100_000

    # ------------------------------------------------------------------
    # Live decision
    # ------------------------------------------------------------------
    def on_step(self, ctx: StrategyContext) -> List[Signal]:
        p = self.params
        # update the causal BTC OBI used as the cross-asset lead covariate
        if ctx.asset == "BTC" and ctx.row.ob_imb_top3 is not None:
            c = p.obi_clip
            self._btc_obi = float(np.clip(ctx.row.ob_imb_top3, -c, c))

        model = self._models.get(ctx.asset)
        if model is None or model.startprob_ is None:
            return []

        # ---- mid-window exit on regime collapse ----
        if ctx.open_shares > 0 and ctx.open_positions:
            sig = self._maybe_exit(ctx, model)
            if sig is not None:
                return [sig]
            return []

        # Act at most once per token-window, near the window's OPEN.  The
        # forecast for window w is the one-step-ahead transition from the
        # regimes filtered over COMPLETED bars (through w-1) ONLY -- we do NOT
        # fold window w's own partial bar into the filter, because that would
        # make predict_next_regime forecast w+1 while we trade w (the horizon
        # mismatch the audit flagged).  Trading w's own token then matches the
        # forecast horizon to the settled instrument.
        if ctx.seconds_to_resolution < ctx.window_size_s - p.act_within_open_s:
            return []
        akey = (ctx.token_id, ctx.window_end_ts)
        if akey in self._acted:
            return []

        # Completed prior bars only (strictly causal; appended at on_window_close
        # for already-settled windows).  Need at least a couple to filter.
        hist = self._bar_hist.get(ctx.asset, [])
        if len(hist) < 2:
            return []
        keep = hist[-self.params.bar_history_len :]
        obs = np.array([e for (e, _) in keep], dtype=float)
        cov = np.array([c for (_, c) in keep], dtype=float)
        obi_now = float(cov[-1][0]) if cov.size else 0.0

        # filtered state after the last COMPLETED bar (w-1), then the OBI-warped
        # one-step-ahead transition == the forecast for the current window w.
        alpha, _ = model.filter(obs, cov)
        nxt = model.predict_next_regime(alpha[-1], cov[-1])
        up_s, down_s = self._up_down[ctx.asset]
        p_up = float(nxt[up_s])
        p_down = float(nxt[down_s])

        # ---- entry gate (>0.75) + post-fee/fill edge floor ----
        ask = ctx.best_ask
        if ask is None or ask <= 0 or ask >= 1:
            # for a NO entry we will read the peer ask below
            ask = None

        sigs: List[Signal] = []
        fee_fn = ctx.extras.get("fee_fn")
        exp_fill = ctx.extras["expected_fill_price"]

        if p_up > p_enter_threshold(p):
            touch = ctx.best_ask
            if touch is not None and 0 < touch < 1:
                f = exp_fill("buy", touch)
                fee_ps = (fee_fn(f, 1.0) if fee_fn else 0.0)
                edge = p_up - f - fee_ps
                if edge >= p.edge_min:
                    self._acted.add(akey)
                    sigs.append(
                        Signal(
                            side="BUY_YES",
                            size_fraction=self._size(edge),
                            price_limit=min(1.0, touch + 2.0 * abs(f - touch) + 0.02),
                            meta={
                                "strategy_note": "hmm_up_regime",
                                "p_up": round(p_up, 4),
                                "obi": round(obi_now, 4),
                                "regime_up_state": up_s,
                            },
                        )
                    )
        elif p_down > p_enter_threshold(p):
            # BUY_NO routes to the peer DOWN token at its own ask
            peer = ctx.peer
            touch = peer.get("best_ask") if peer else None
            if touch is not None and 0 < touch < 1:
                f = exp_fill("buy", touch)
                fee_ps = (fee_fn(f, 1.0) if fee_fn else 0.0)
                edge = p_down - f - fee_ps
                if edge >= p.edge_min:
                    self._acted.add(akey)
                    sigs.append(
                        Signal(
                            side="BUY_NO",
                            size_fraction=self._size(edge),
                            price_limit=min(1.0, touch + 2.0 * abs(f - touch) + 0.02),
                            meta={
                                "strategy_note": "hmm_down_regime",
                                "p_down": round(p_down, 4),
                                "obi": round(obi_now, 4),
                                "regime_down_state": down_s,
                            },
                        )
                    )
        return sigs

    # ------------------------------------------------------------------
    def _maybe_exit(
        self, ctx: StrategyContext, model: NonHomogeneousHMM
    ) -> Optional[Signal]:
        """Emit FLAT if the entered regime's filtered prob has collapsed.

        We re-filter on the causal slice and check the probability of the
        regime we entered.  If it has fallen below ``p_exit`` we early-exit at
        the bid (the engine routes FLAT to a bid-side fill).
        """
        rows = list(ctx.history)
        if len(rows) < 2:
            return None
        cur_emis = self._emission_vec(rows)
        obi_now = self._obi(rows)
        cur_cov = self._covariate_vec(ctx.asset, obi_now)
        obs, cov = self._filter_sequence(ctx.asset, cur_emis, cur_cov)
        alpha, _ = model.filter(obs, cov)
        # We hold a position ON window w; check whether w's CURRENT filtered
        # regime (including w's partial bar so far) still favours our side --
        # not the next-window transition.
        cur_state = alpha[-1]
        up_s, down_s = self._up_down[ctx.asset]
        # infer which side we hold from the token's direction
        is_up_token = (ctx.outcome_dir or "").lower() == "up" or (
            ctx.outcome_side or ""
        ).upper() == "YES"
        held_p = float(cur_state[up_s]) if is_up_token else float(cur_state[down_s])
        if held_p < self.params.p_exit:
            return Signal(side="FLAT", meta={"reason": "regime_collapse",
                                             "held_p": round(held_p, 4)})
        return None

    def _size(self, edge: float) -> float:
        """Edge-proportional sizing in [0,1], capped by params downstream.

        A simple proportional rule: larger modelled edge ⇒ larger fraction,
        saturating at 1.0.  The engine further caps by ``max_position_frac``
        and ``per_window_budget_frac``.
        """
        # map an edge of edge_min..(edge_min+0.25) onto 0.2..1.0
        lo = self.params.edge_min
        frac = 0.2 + 3.2 * max(0.0, edge - lo)
        return float(min(1.0, max(0.0, frac)))

    def on_window_close(
        self, panel: WindowPanel, resolved_yes_for_token: int
    ) -> None:
        """Causal bookkeeping after a window settles.

        1. Append the just-settled window's completed bar (its full-timeline
           emission + OBI covariate) to the per-asset rolling history.  Because
           this fires only AFTER settlement, the bar is fully observed and the
           rolling buffer used by the next window's :meth:`on_step` is strictly
           causal (no future leakage).  De-dup by ``window_end_ts`` so the UP
           and DOWN panels of the same window do not double-count.
        2. Drop the per-window 'acted' memo entries to bound the set size.

        The label ``resolved_yes_for_token`` is intentionally NOT used to build
        any feature: the rolling history is unsupervised (returns/OBI only).
        """
        asset = panel.asset
        we = int(panel.window_end_ts)
        folded = self._folded_we.setdefault(asset, set())
        if panel.is_up_token and we not in folded and panel.timeline:
            rows = panel.timeline
            emis = self._emission_vec(rows)
            obi = self._obi(rows)
            cov = self._covariate_vec(asset, obi)
            self._bar_hist.setdefault(asset, []).append((emis, cov))
            # bound memory: keep a generous tail (>= bar_history_len)
            cap = max(self.params.bar_history_len * 4, 200)
            if len(self._bar_hist[asset]) > cap:
                self._bar_hist[asset] = self._bar_hist[asset][-cap:]
            folded.add(we)
            if len(folded) > 4000:
                # keep the most recent window-ids only
                self._folded_we[asset] = set(sorted(folded)[-2000:])

        akey = (panel.token_id, we)
        self._acted.discard(akey)


def p_enter_threshold(params: HmmRegimeParams) -> float:
    """The OPEN gate probability (kept as a function for clarity/override)."""
    return float(params.p_enter)


__all__ = [
    "GaussianHMM",
    "NonHomogeneousHMM",
    "HmmRegimeParams",
    "S2HmmRegimeStrategy",
    "p_enter_threshold",
]
