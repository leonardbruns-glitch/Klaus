"""STWA directional-YES pricer + inventory-adjusted Matrix-Kelly allocator.

This implements the BACKTEST-VERIFIED parts of the proposed spec and REFUSES the
parts that contradict measured data. It is an A/B CANDIDATE for the directional-YES
slice — it is NOT wired live and does NOT replace:
  * NEG_RISK_ARB — calibration-independent, the one structurally sound edge (kept).
  * M1β lockout-NO — 95–98% WR OOS validated (kept).
The spec called those "broken / capital-draining"; the data says otherwise, so they
stay. This module only supplies a better directional pricer/allocator to shadow-test
against the live PA_SHRUNK.

IMPLEMENTED (added value, all measured on 11 clean gfs cities, dist_kalman_ev.py):
  * Stage 2  time-varying Kalman gain β_h: 0 before 11:00 local (morning obs R²≈0),
             0.30 / 0.40 / 0.41 across 11→peak. Replaces the engine's fixed β=0.30.
  * Stage 3  per-city distribution routing: Skew-Normal (default), Gaussian (symmetric
             LA/Miami), Gumbel-LEFT (SF marine cap). Gumbel-R banned (ξ<0 ⇒ tail bounded;
             Gumbel-R was worst OOS in 10/11 cities).
  * Stage 4  unit-aware CDF bucketization p_i = F(hi)−F(lo), running-max floor, Σ=1.
  * Stage 5  SLSQP inventory-adjusted Matrix Kelly, YES-only, Σf ≤ 0.20.

CORRECTED (spec was unsafe):
  * Variance shrinkage is σ_h = σ_base·√(1−R²_h) (R²_h measured: 0, .14, .26, .30) →
    σ shrinks only ~16% by peak. The spec's linear "1.1°C→0.2°C" is REJECTED: it is the
    σ-collapse bug (false ~100% confidence). Genuine late-window certainty comes from the
    RUNNING-MAX FLOOR (locked buckets → p=0), not from shrinking σ to 0.2.

REFUSED (falsified — see project memories):
  * Pre-11am cheap-tail ($0.01–0.05) passive sweep — −EV (favorite-longshot) AND
    self-contradictory: Stage 2 sets β_h=0 / R²≈0 pre-11am, i.e. NO edge to act on.
  * "Snipe mid-tier before MMs adjust" — latency front-run falsified (book reprices <30–60s).
    Kept only the defensible core: take EV-positive buckets post-gate.

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.stwa_matrix_kelly   # runs self-test
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy import optimize, stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stwa_mk")

EULER = 0.5772156649015329

# ── measured per-city law + residual σ (gfs cities; dist_kalman_ev.py fits) ───────
CITY_DIST: dict[str, dict] = {
    "nyc":           {"dist": "skewnorm", "alpha":  1.395, "sigma": 0.823},
    "chicago":       {"dist": "skewnorm", "alpha":  1.079, "sigma": 0.665},
    "los-angeles":   {"dist": "norm",                       "sigma": 0.634},
    "miami":         {"dist": "norm",                       "sigma": 0.760},
    "san-francisco": {"dist": "gumbel_l",                   "sigma": 1.550},
    "dallas":        {"dist": "skewnorm", "alpha":  1.324, "sigma": 0.826},
    "houston":       {"dist": "skewnorm", "alpha":  1.243, "sigma": 0.717},
    "seattle":       {"dist": "skewnorm", "alpha":  1.312, "sigma": 0.671},
    "denver":        {"dist": "skewnorm", "alpha": -1.757, "sigma": 0.884},
    "atlanta":       {"dist": "skewnorm", "alpha":  1.668, "sigma": 0.648},
    "austin":        {"dist": "skewnorm", "alpha": -1.203, "sigma": 0.700},
}
DEFAULT_DIST = {"dist": "norm", "sigma": 1.10}     # honest fallback for un-fit cities

# β_h and the variance-explained R²_h by local hour (measured, pooled gfs)
def beta_h(local_hour: int) -> float:
    if local_hour < 11:  return 0.00          # morning obs is noise (R²≈0) — gate shut
    if local_hour < 13:  return 0.30
    if local_hour < 15:  return 0.40
    return 0.41

def r2_h(local_hour: int) -> float:
    if local_hour < 11:  return 0.00
    if local_hour < 13:  return 0.14
    if local_hour < 15:  return 0.26
    return 0.30

SIGMA_HARD_FLOOR = 0.40        # never below this — REJECTS the spec's 0.2 σ-collapse
EDGE_MIN = 0.04                # engine EDGE_MIN (spec used 0.15; we keep the live value)
KELLY_CAP = 0.20               # Σf ≤ 0.20 (matches live fractional-Kelly risk param)


# ── Stage 3: per-city skewed distribution with controllable (mean=μ, std=σ) ───────
def make_dist(city: str, mu: float, sigma: float):
    """Return a frozen scipy dist with mean≈μ and std≈σ, per the city's routed law."""
    cfg = CITY_DIST.get(city, DEFAULT_DIST)
    kind = cfg["dist"]
    sigma = max(SIGMA_HARD_FLOOR, sigma)
    if kind == "norm":
        return stats.norm(loc=mu, scale=sigma)
    if kind == "gumbel_l":
        # gumbel_l: std = scale·π/√6 ; mean = loc − scale·γ  → solve loc,scale for (μ,σ)
        scale = sigma * np.sqrt(6) / np.pi
        loc = mu + scale * EULER
        return stats.gumbel_l(loc=loc, scale=scale)
    # skewnorm: match mean & std exactly given shape α
    a = cfg["alpha"]
    delta = a / np.sqrt(1 + a * a)
    std_factor = np.sqrt(1 - 2 * delta * delta / np.pi)
    scale = sigma / std_factor
    loc = mu - scale * delta * np.sqrt(2 / np.pi)
    return stats.skewnorm(a, loc=loc, scale=scale)


# ── Stage 2: time-varying center ──────────────────────────────────────────────────
def center_mu(nwp_peak: float, peak_bias: float, observed_residual_now: float,
              local_hour: int) -> tuple[float, float]:
    """Return (μ, σ_h). Pre-11am: gate shut → μ = NWP_peak + peak_bias, σ unshrunk."""
    b = beta_h(local_hour)
    mu = nwp_peak + peak_bias + b * observed_residual_now
    return mu, b


def shrink_sigma(sigma_base: float, local_hour: int) -> float:
    """σ_h = σ_base·√(1−R²_h). NOT the spec's linear collapse to 0.2°C."""
    return max(SIGMA_HARD_FLOOR, sigma_base * np.sqrt(1.0 - r2_h(local_hour)))


# ── Stage 4: discrete bucket probabilities (unit-aware, running-max floored) ───────
@dataclass
class Bucket:
    lo_c: float            # padded lower edge in °C (-inf for open-bottom)
    hi_c: float            # padded upper edge in °C (+inf for open-top)
    ask: float             # live YES ask price
    q: float = 0.0         # open inventory tokens in this bucket ($1 payout if it wins)


def bucket_probs(dist, buckets: list[Bucket], running_max_c: float | None) -> np.ndarray:
    """p_i = F(hi_i) − F(lo_i); zero any bucket fully below running_max (locked); renorm."""
    p = np.array([dist.cdf(b.hi_c) - dist.cdf(b.lo_c) for b in buckets], dtype=float)
    if running_max_c is not None:
        for i, b in enumerate(buckets):
            if b.hi_c <= running_max_c:        # physically impossible → locked out
                p[i] = 0.0
    s = p.sum()
    return p / s if s > 0 else p


# ── Stage 5: inventory-adjusted Matrix Kelly (SLSQP, YES-only, Σf ≤ 0.20) ──────────
def matrix_kelly(p: np.ndarray, asks: np.ndarray, q: np.ndarray,
                 cash: float, cap: float = KELLY_CAP) -> np.ndarray:
    """maximize Σ p_i ln( C(1−Σf) + f_i·C/m_i + q_i ),  f_i≥0,  Σf ≤ cap.
    Returns f (cash fractions). Inventory q enters as fixed collateral per outcome."""
    n = len(p)
    valid = asks > 1e-6
    if cash <= 0 or not valid.any():
        return np.zeros(n)

    def neg_log_util(f):
        deploy = cash * (1.0 - f.sum())
        wealth = deploy + np.where(valid, f * cash / np.where(valid, asks, 1.0), 0.0) + q
        wealth = np.maximum(wealth, 1e-9)        # keep log in-domain
        return -float(np.sum(p * np.log(wealth)))

    cons = [{"type": "ineq", "fun": lambda f: cap - f.sum()}]   # Σf ≤ cap
    bounds = [(0.0, cap) if valid[i] else (0.0, 0.0) for i in range(n)]  # f_i ≥ 0, YES-only
    res = optimize.minimize(neg_log_util, np.zeros(n), method="SLSQP",
                            bounds=bounds, constraints=cons,
                            options={"maxiter": 200, "ftol": 1e-9})
    f = np.clip(res.x, 0.0, cap)
    if f.sum() > cap:                            # numerical guard
        f *= cap / f.sum()
    return f


# ── Stage 6: execution decision (corrected — gated, no pre-11am tail sweep) ────────
@dataclass
class Decision:
    city: str
    local_hour: int
    mu: float
    sigma: float
    p: np.ndarray
    ev: np.ndarray
    f: np.ndarray
    dollars: np.ndarray
    note: str = ""


def decide(city: str, local_hour: int, nwp_peak: float, peak_bias: float,
           observed_residual_now: float, running_max_c: float | None,
           buckets: list[Bucket], cash: float, city_day_budget: float) -> Decision:
    cfg = CITY_DIST.get(city, DEFAULT_DIST)
    sigma_base = cfg["sigma"]
    mu, b = center_mu(nwp_peak, peak_bias, observed_residual_now, local_hour)
    sigma = shrink_sigma(sigma_base, local_hour)
    dist = make_dist(city, mu, sigma)
    p = bucket_probs(dist, buckets, running_max_c)
    asks = np.array([b.ask for b in buckets])
    q = np.array([b.q for b in buckets])
    ev = np.where(asks > 1e-6, p / np.where(asks > 1e-6, asks, 1.0) - 1.0, -1.0)

    # GATE: before 11:00 local there is no informational edge (β=0, R²≈0). No buys.
    if local_hour < 11:
        return Decision(city, local_hour, mu, sigma, p, ev,
                        np.zeros(len(p)), np.zeros(len(p)),
                        note="pre-11am gate shut — morning obs is noise; no buys "
                             "(REFUSED: cheap-tail sweep is −EV)")

    # only let Kelly consider buckets that clear the edge floor (calibrated EV)
    elig = ev >= EDGE_MIN
    p_use = np.where(elig, p, 0.0)
    f = matrix_kelly(p_use, asks, q, cash)
    dollars = f * cash
    # respect the per-city-day budget net of held capital
    spent = dollars.sum()
    if spent > city_day_budget and spent > 0:
        dollars *= city_day_budget / spent
        f = dollars / cash
    return Decision(city, local_hour, mu, sigma, p, ev, f, dollars,
                    note=f"β_h={b:.2f} σ={sigma:.2f} eligible={int(elig.sum())}/{len(p)}")


# ── self-test with mock data (no live wiring) ─────────────────────────────────────
def _selftest():
    print("=== STWA Matrix-Kelly self-test (mock data, NOT live) ===\n")
    city = "nyc"
    # NYC °F market: 2°F buckets around a forecast peak of ~28°C (82°F). Edges in °C.
    nwp_peak, peak_bias = 28.0, 0.3
    buckets = [
        Bucket(-np.inf, 25.5, ask=0.02),
        Bucket(25.5, 26.6, ask=0.06),
        Bucket(26.6, 27.8, ask=0.15),
        Bucket(27.8, 28.9, ask=0.34, q=5.0),    # we already hold 5 tokens here
        Bucket(28.9, 30.0, ask=0.22),
        Bucket(30.0, np.inf, ask=0.05),
    ]
    cash, budget = 50.0, 9.0

    for hour, obs_resid, rmax in [(9, 1.2, None), (13, 0.9, 26.0), (15, 1.4, 28.2)]:
        d = decide(city, hour, nwp_peak, peak_bias, obs_resid, rmax, buckets, cash, budget)
        print(f"--- local {hour}:00  obs_resid={obs_resid:+.1f}  running_max={rmax} ---")
        print(f"  μ={d.mu:.2f}°C σ={d.sigma:.2f}  Σp={d.p.sum():.3f}  {d.note}")
        print(f"  {'bucket':>16} {'p':>6} {'ask':>5} {'EV':>7} {'$buy':>6} {'held':>5}")
        for b, pi, evi, dol in zip(buckets, d.p, d.ev, d.dollars):
            lab = f"[{b.lo_c:.1f},{b.hi_c:.1f})".replace("inf", "∞")
            print(f"  {lab:>16} {pi:6.3f} {b.ask:5.2f} {evi:+7.2f} {dol:6.2f} {b.q:5.1f}")
        print()

    # synthetic-hedge demo: afternoon shift moves μ up; we hold the now-OOM bucket and
    # the optimizer buys the newly favored adjacent YES with cash — never sells.
    print("--- afternoon shift: obs_resid jumps +2.5 (heat spike); hold Q, re-allocate ---")
    d = decide(city, 15, nwp_peak, peak_bias, 2.5, 29.0, buckets, cash, budget)
    print(f"  μ={d.mu:.2f}°C  new favored buys: "
          f"{[(f'{b.lo_c:.1f}-{b.hi_c:.1f}', round(dol,2)) for b,dol in zip(buckets,d.dollars) if dol>0.01]}")
    print("  (held 5 tokens in [27.8,28.9) untouched — no sell; cash buys the new mode)")


if __name__ == "__main__":
    _selftest()
