"""
STWA Engine — Spatiotemporal Weather Arbitrage.

Architecture:
  1. Spatiotemporal Kalman filter: 49-city joint state, empirical spatial covariance.
     Every METAR observation updates all city posteriors simultaneously via
     the spatial correlation structure (Kriging propagation).

  2. Running-maximum Monte Carlo: per city, simulate N=8000 OU paths forward
     with time-varying κ(t)/σ(t), compute P(daily_max ∈ bucket) analytically.

  3. Neg-risk LP: allocate capital across all open buckets per city to maximise
     expected edge; ensures probabilities sum to 1 (internal consistency gate).

  4. Regime gate: only fires in SUNNY / PARTLY_CLOUDY; RAIN/STORM/FOG suspended.

  5. Live calibration: ECE per city computed daily; city suspended if ECE > 0.10.

Usage (within weather_arb.py):
    engine = STWAEngine(params_path="config/stwa_params.json")
    # On each METAR callback:
    engine.on_metar(city, temp_c, dew_c, sky_rank, obs_ts, running_max_c)
    # Periodically (every 30s):
    signals = engine.get_signals(clob_books)
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
N_PATHS        = 8_000   # Monte Carlo paths per city
MC_STEP_S      = 300     # 5-minute simulation time step (seconds)
EDGE_MIN       = 0.08    # minimum edge to generate a signal
CONFIDENCE_MIN = 0.45    # minimum confidence score
METAR_MAX_AGE  = 3600    # seconds — METAR stations report hourly; allow up to 60 min
MIN_TIME_REM   = 1800    # don't fire within 30 min of market close
HOUR_BINS      = [(0, 6), (6, 12), (12, 18), (18, 24)]

# ── LP portfolio allocation ────────────────────────────────────────────────────
CITY_BUDGET_FRAC  = 0.05   # max fraction of bankroll per city
CITY_BUDGET_MAX   = 15.0   # hard cap per city (USD)
NEG_RISK_ARB_THR  = 0.92   # Σ YES ask < this → pure neg-risk arb available
PROB_SUM_MAX      = 1.35   # Σ p_model > this → MC bug, skip city

# Sky rank → regime label (sky_rank 0=clear, 4=overcast)
#  sky_rank comes from the METAR cache (0=SKC/CLR, 1=FEW, 2=SCT, 3=BKN, 4=OVC/VV)
REGIME_FROM_SKY = {0: "SUNNY", 1: "SUNNY", 2: "PARTLY_CLOUDY", 3: "CLOUDY", 4: "CLOUDY"}
REGIME_FIRE     = {"SUNNY", "PARTLY_CLOUDY"}    # only fire in these regimes
REGIME_SIGMA_MUL= {"SUNNY": 1.0, "PARTLY_CLOUDY": 1.2, "CLOUDY": 1.5}  # uncertainty multiplier


@dataclass
class Signal:
    city:        str
    bucket:      tuple[float, float]   # (lo_c, hi_c)  always in °C
    direction:   str                   # "YES" or "NO"
    token_id:    str
    p_model:     float
    ask:         float
    edge:        float
    confidence:  float
    stake:       float
    regime:      str
    phase:       str
    metar_age_s: float
    kalman_var:  float
    kriging_pct: float   # fraction of posterior that came from spatial propagation


@dataclass
class _CityState:
    """Live Kalman state + metadata for one city."""
    city:        str
    idx:         int              # index in the 49-city state vector
    # Kalman marginal posterior (marginal extracted from joint P matrix)
    x_hat:       float = 0.0     # posterior mean residual (°C)
    # Posterior variance stored in the joint P matrix; accessed via engine.P[idx, idx]
    last_obs_ts: float = 0.0     # Unix timestamp of latest METAR
    running_max: Optional[float] = None
    regime:      str = "SUNNY"
    obs_count:   int = 0
    obs_date:    str = ""        # YYYY-MM-DD of the day running_max belongs to
    # For kriging contribution tracking
    last_update_from_self: bool = True


class STWAEngine:
    """
    Spatiotemporal Weather Arbitrage Engine.

    Thread-safe: on_metar() acquires a lock before updating Kalman state.
    get_signals() reads state under the same lock.
    """

    def __init__(
        self,
        params_path: str | Path = "config/stwa_params.json",
        bankroll: float = 100.0,
        stake_min: float = 3.0,
        stake_max: float = 20.0,
        kelly_fraction: float = 0.20,
    ) -> None:
        self._lock = threading.Lock()
        self.bankroll    = bankroll
        self.stake_min   = stake_min
        self.stake_max   = stake_max
        self.kelly_frac  = kelly_fraction

        self._params_path = Path(params_path)
        self._params: dict = {}
        self._cities: dict[str, _CityState] = {}
        self._city_list: list[str] = []   # ordered list matching spatial_cov rows

        # Kalman state vectors (N_cities dimensional)
        self._X: np.ndarray = np.array([])   # posterior mean
        self._P: np.ndarray = np.array([])   # posterior covariance (N×N)
        self._C: np.ndarray = np.array([])   # spatial process covariance (prior)

        # NWP forecast cache: city → {hour_utc: temp_c}
        self._nwp_cache: dict[str, dict[int, float]] = {}
        self._nwp_date:  str = ""

        # Calibration log: city → [(p_model, outcome), ...]
        self._cal_log: dict[str, list[tuple[float, int]]] = {}
        self._suspended: set[str] = set()

        self._load_params()

    # ── Param loading ──────────────────────────────────────────────────────────

    def _load_params(self) -> None:
        if not self._params_path.exists():
            logger.warning("[STWA] params not found at %s — engine in stub mode", self._params_path)
            return

        with open(self._params_path) as f:
            self._params = json.load(f)

        # City order for spatial covariance
        self._city_list = self._params.get("city_order", list(self._params["stations"].keys()))
        N = len(self._city_list)

        # Spatial covariance matrix
        C_raw = np.array(self._params["spatial_covariance"])
        self._C = C_raw if C_raw.shape == (N, N) else np.eye(N) * 0.5

        # Initial Kalman state: X=0 (no anomaly), P=C (prior = spatial covariance)
        self._X = np.zeros(N)
        self._P = self._C.copy()

        # Build city state registry
        for idx, city in enumerate(self._city_list):
            if city in self._params["stations"]:
                self._cities[city] = _CityState(city=city, idx=idx)

        logger.info("[STWA] loaded params: %d cities, %dx%d covariance", N, N, N)

    def reset_daily(self) -> None:
        """Reset all cities (legacy — prefer reset_city for per-city local midnight)."""
        with self._lock:
            N = len(self._city_list)
            self._X = np.zeros(N)
            self._P = self._C.copy()
            for cs in self._cities.values():
                cs.running_max = None
                cs.obs_date    = ""
                cs.x_hat       = 0.0
            self._nwp_cache.clear()
            self._nwp_date = ""
        logger.info("[STWA] full daily reset — Kalman state re-initialised")

    def reset_city(self, city: str) -> None:
        """Reset one city at its local midnight without disturbing other cities."""
        with self._lock:
            cs = self._cities.get(city)
            if cs is None:
                return
            i = cs.idx
            # Zero this city's component in the joint state vector
            self._X[i] = 0.0
            # Reset row/col i of P back to the prior spatial covariance
            self._P[i, :] = self._C[i, :]
            self._P[:, i] = self._C[:, i]
            cs.running_max = None
            cs.obs_date    = ""
            cs.x_hat       = 0.0
            self._nwp_cache.pop(city, None)
        logger.info("[STWA] city reset at local midnight: %s", city)

    # ── NWP forecast ───────────────────────────────────────────────────────────

    def update_nwp_forecast(self, city: str, hourly_temps: dict[int, float]) -> None:
        """Called by weather_arb when a fresh Open-Meteo forecast arrives."""
        with self._lock:
            self._nwp_cache[city] = hourly_temps

    def _get_mu(self, city: str, hour_utc: int) -> float:
        """Bias-corrected NWP forecast temperature for a city at a given UTC hour."""
        nwp = self._nwp_cache.get(city, {})
        t_nwp = nwp.get(hour_utc)
        if t_nwp is None:
            return float("nan")

        st = self._params["stations"].get(city, {})
        month = _current_month()
        bias_key = f"{month}_{hour_utc}"
        bias = st.get("bias", {}).get(bias_key, 0.0)
        return t_nwp + bias

    def _get_mu_curve(self, city: str, t_start: float, t_end: float) -> tuple[np.ndarray, np.ndarray]:
        """Return (t_grid, mu_grid) for simulation from t_start to t_end (unix seconds)."""
        t_grid   = np.arange(t_start, t_end, MC_STEP_S, dtype=float)
        mu_grid  = np.full(len(t_grid), float("nan"))

        nwp = self._nwp_cache.get(city, {})
        if not nwp:
            return t_grid, mu_grid

        st     = self._params["stations"].get(city, {})
        biases = st.get("bias", {})
        month  = _current_month()

        for i, ts in enumerate(t_grid):
            h = int((ts % 86400) / 3600)
            t_nwp = nwp.get(h)
            if t_nwp is not None:
                b = biases.get(f"{month}_{h}", 0.0)
                mu_grid[i] = t_nwp + b

        # Fill small gaps by linear interpolation
        valid = np.isfinite(mu_grid)
        if valid.any() and not valid.all():
            mu_grid = np.interp(
                np.arange(len(t_grid)),
                np.where(valid)[0],
                mu_grid[valid]
            )

        return t_grid, mu_grid

    # ── Kalman filter ──────────────────────────────────────────────────────────

    def on_metar(
        self,
        city:        str,
        temp_c:      float,
        dew_c:       Optional[float],
        sky_rank:    int,
        obs_ts:      float,
        running_max: Optional[float],
        today_str:   str = "",
    ) -> None:
        """
        Process one METAR observation.  Updates:
          - Running maximum for city
          - Regime classification
          - Kalman posterior for ALL cities (spatial propagation)
        """
        if not self._params or city not in self._cities:
            return

        cs  = self._cities[city]
        idx = cs.idx
        st  = self._params["stations"].get(city, {})

        # ── Regime classification ──────────────────────────────────────────────
        regime = REGIME_FROM_SKY.get(min(sky_rank, 4), "PARTLY_CLOUDY")

        # ── Bias-corrected NWP for this hour ──────────────────────────────────
        hour_utc = int((obs_ts % 86400) / 3600)
        mu_now   = self._get_mu(city, hour_utc)

        if not math.isfinite(mu_now):
            # No NWP forecast — update running max + regime but skip Kalman
            with self._lock:
                cs.regime       = regime
                cs.last_obs_ts  = obs_ts
                cs.running_max  = _new_max(running_max, temp_c)
                cs.obs_date     = today_str
            return

        # ── Humidity correction ───────────────────────────────────────────────
        mu_corrected = mu_now
        if dew_c is not None and math.isfinite(dew_c):
            nwp_dew = self._nwp_cache.get(city, {}).get(hour_utc)
            if nwp_dew is not None:
                month = _current_month()
                alpha = st.get("alpha_humidity", {}).get(str(month), 0.0)
                mu_corrected += alpha * (dew_c - nwp_dew)

        # ── Residual (what the OU process models) ─────────────────────────────
        y_obs = temp_c - mu_corrected

        # ── Gross error check ─────────────────────────────────────────────────
        if abs(y_obs) > 8.0:
            logger.debug("[STWA] %s outlier rejected: T=%.1f mu=%.1f y=%.1f", city, temp_c, mu_corrected, y_obs)
            return

        # ── Kalman update (joint over all cities) ─────────────────────────────
        sigma_obs = st.get("sigma_obs", 0.5)
        regime_mul = REGIME_SIGMA_MUL.get(regime, 1.2)
        sigma_obs_eff = sigma_obs * regime_mul

        dt_hours = max((obs_ts - cs.last_obs_ts) / 3600.0, 1/60) if cs.last_obs_ts > 0 else 6.0
        dt_hours = min(dt_hours, 12.0)

        with self._lock:
            # Time propagation (predict step)
            N = len(self._city_list)
            kappas = np.array([
                _get_kappa(self._params["stations"].get(c, {}), hour_utc)
                for c in self._city_list
            ])
            F = np.diag(np.exp(-kappas * dt_hours))
            decay_ij = np.outer(kappas, kappas)
            k_eff = (kappas[:, None] + kappas[None, :]) / 2.0
            Q = self._C * (1.0 - np.exp(-k_eff * dt_hours))

            X_pred = F @ self._X
            P_pred = F @ self._P @ F.T + Q

            # Observation update (single station)
            h_vec = np.zeros(N)
            h_vec[idx] = 1.0
            S     = float(h_vec @ P_pred @ h_vec) + sigma_obs_eff ** 2
            K     = P_pred @ h_vec / S
            innov = y_obs - float(h_vec @ X_pred)

            # Mahalanobis check: |innov|/sqrt(S) > 4 → reject
            if abs(innov) / math.sqrt(S) > 4.0:
                logger.debug("[STWA] %s Mahalanobis outlier: innov=%.2f S=%.2f", city, innov, S)
                # Still update time propagation
                self._X = X_pred
                self._P = P_pred
            else:
                self._X = X_pred + K * innov
                self._P = P_pred - np.outer(K, K) * S

                # Ensure P stays symmetric positive definite (numerical hygiene)
                self._P = (self._P + self._P.T) / 2.0
                np.fill_diagonal(self._P, np.maximum(np.diag(self._P), 1e-6))

            cs.x_hat    = float(self._X[idx])
            cs.last_obs_ts  = obs_ts
            cs.running_max  = _new_max(running_max, temp_c)
            cs.regime       = regime
            cs.obs_date     = today_str
            cs.obs_count   += 1
            cs.last_update_from_self = True

    # ── Running maximum distribution ───────────────────────────────────────────

    def _forecast_bucket_probs(
        self,
        city: str,
        t_now: float,
        t_close: float,
        buckets: list[tuple[float, float]],
        phase: str = "PRE_PEAK",
    ) -> dict[tuple[float, float], float]:
        """
        Monte Carlo estimate of P(daily_max ∈ bucket) for each bucket.
        Uses time-varying OU parameters and the current Kalman posterior.
        """
        if not buckets:
            return {}

        cs = self._cities[city]
        st = self._params["stations"].get(city, {})

        tau_hours = (t_close - t_now) / 3600.0
        if tau_hours < 0.5:
            # Market nearly closed: just check if running max is in bucket
            m = cs.running_max if cs.running_max is not None else float("-inf")
            return {b: 1.0 if b[0] <= m < b[1] else 0.0 for b in buckets}

        # Get Kalman posterior (marginal for this city)
        with self._lock:
            idx   = cs.idx
            x_hat = float(self._X[idx])
            p_var = float(self._P[idx, idx])
            # Kriging contribution: how much of the posterior came from other cities?
            p_prior_diag = float(self._C[idx, idx])
            kriging_pct  = max(0.0, 1.0 - p_var / max(p_prior_diag, 1e-6))

        cs.kriging_pct_last = kriging_pct

        # NWP diurnal curve for simulation period
        t_grid, mu_grid = self._get_mu_curve(city, t_now, t_close)
        if not np.isfinite(mu_grid).any():
            return {}

        n_steps = len(t_grid)
        if n_steps < 2:
            return {}

        # Regime sigma multiplier; POST_PEAK dampens residual variance (day is done)
        _PHASE_SIG_MUL = {"PRE_PEAK": 1.0, "AT_PEAK": 0.5, "POST_PEAK": 0.15}
        regime_mul = REGIME_SIGMA_MUL.get(cs.regime, 1.2) * _PHASE_SIG_MUL.get(phase, 1.0)

        # Simulate N_PATHS OU residual paths with time-varying κ(t), σ(t)
        rng    = np.random.default_rng(seed=int(t_now) % (2**31))
        paths  = np.zeros((N_PATHS, n_steps), dtype=np.float32)

        # Sample initial state from Kalman posterior (propagates uncertainty correctly)
        paths[:, 0] = rng.normal(x_hat, math.sqrt(max(p_var, 1e-6)), N_PATHS).astype(np.float32)

        for i in range(n_steps - 1):
            h_utc   = int((t_grid[i] % 86400) / 3600)
            bin_i   = h_utc // 6
            kap     = _get_kappa(st, h_utc)
            sig     = _get_sigma(st, h_utc) * regime_mul
            dt_hr   = (t_grid[i + 1] - t_grid[i]) / 3600.0
            decay   = math.exp(-kap * dt_hr)
            cond_v  = (sig ** 2 / (2 * kap)) * (1 - math.exp(-2 * kap * dt_hr))
            cond_sd = math.sqrt(max(cond_v, 1e-8))
            noise   = rng.normal(0, cond_sd, N_PATHS).astype(np.float32)
            paths[:, i + 1] = paths[:, i] * decay + noise

        # Temperature paths = residual + NWP diurnal
        T_paths = (paths + mu_grid.astype(np.float32)).astype(np.float32)  # (N, steps)

        # Running maximum: compete against already-observed max
        M0 = cs.running_max if cs.running_max is not None else float("-inf")
        path_max = np.maximum(M0, T_paths.max(axis=1))  # (N,)

        # Bucket probabilities
        probs: dict[tuple[float, float], float] = {}
        for (lo, hi) in buckets:
            probs[(lo, hi)] = float(np.mean((path_max >= lo) & (path_max < hi)))

        return probs

    # ── Signal generation ──────────────────────────────────────────────────────

    def _lp_allocate_city(
        self,
        city:        str,
        buckets_raw: list,    # [(lo, hi, yes_tok, no_tok), ...]
        probs:       dict,    # {(lo,hi): p_model}
        clob_books:  dict,
        confidence:  float,
        phase:       str,
        bankroll:    float,
        metar_age:   float,
        p_var:       float,
        kriging_pct: float,
        regime:      str,
    ) -> list[Signal]:
        """
        Horse-race Kelly allocation for a city's mutually exclusive buckets.

        Buckets are mutually exclusive: exactly one temperature range wins.
        Independent Kelly over-stakes because it ignores cross-losses (when
        bucket A wins you lose the bucket B stake).  The correct framework is
        the Kelly horse race, whose optimal stakes satisfy:

            x_i = s × (Q × p_c_i − ask_i)

        where Q = (1 − Σask) / p_neither, s = bankroll − T (sideline cash),
        T = bankroll × (Σp_c − Σask/Q), and p_c_i = p_win_i × confidence.

        This collapses to standard Kelly for a single candidate.  Candidates
        with non-positive horse-race stakes are dropped iteratively (converges
        in ≤ N passes).

        Also detects pure neg-risk arb: Σ YES ask < NEG_RISK_ARB_THR means
        buying all YES tokens guarantees profit regardless of which bucket wins.
        """
        # ── Build candidates ──────────────────────────────────────────────────
        entries = []
        for lo, hi, yes_tok, no_tok in buckets_raw:
            p_m      = probs.get((lo, hi), 0.0)
            ask_yes  = _book_ask(clob_books, yes_tok)
            ask_no   = _book_ask(clob_books, no_tok)
            entries.append((lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no))

        if not entries:
            return []

        # ── Consistency gate ─────────────────────────────────────────────────
        total_p = sum(p for *_, p, _, _ in entries)
        if total_p > PROB_SUM_MAX:
            logger.debug("[STWA] LP %s: prob sum %.2f > %.2f — MC bug, skip", city, total_p, PROB_SUM_MAX)
            return []

        # ── Neg-risk arb check ───────────────────────────────────────────────
        valid_yes_asks = [a for *_, a, _ in entries if a is not None and a > 0]
        if len(valid_yes_asks) == len(entries) and sum(valid_yes_asks) < NEG_RISK_ARB_THR:
            arb_edge = 1.0 - sum(valid_yes_asks)
            logger.info("[STWA] NEG_RISK_ARB %s: sum_ask=%.3f edge=%.3f",
                        city, sum(valid_yes_asks), arb_edge)
            # TODO: construct arb signals; for now fall through to greedy

        # ── Per-bucket: pick the positive-edge side ──────────────────────────
        candidates = []
        for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
            edge_yes = (p_m - ask_yes) if ask_yes is not None else -1.0
            edge_no  = ((1.0 - p_m) - ask_no) if ask_no is not None else -1.0

            if edge_yes > EDGE_MIN and edge_no > EDGE_MIN:
                # Both sides positive ↔ neg-risk within this bucket; pick better
                if edge_yes / ask_yes >= edge_no / ask_no:
                    candidates.append(("YES", yes_tok, p_m, ask_yes, edge_yes, (lo, hi)))
                else:
                    candidates.append(("NO", no_tok, p_m, ask_no, edge_no, (lo, hi)))
            elif edge_yes > EDGE_MIN:
                candidates.append(("YES", yes_tok, p_m, ask_yes, edge_yes, (lo, hi)))
            elif edge_no > EDGE_MIN:
                candidates.append(("NO", no_tok, p_m, ask_no, edge_no, (lo, hi)))

        if not candidates:
            return []

        # ── Horse-race Kelly ──────────────────────────────────────────────────
        city_budget = min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX)

        # Attach confidence-adjusted win probability (p_c) to each candidate
        working = []
        for direction, tok, p_m, ask, edge, bucket in candidates:
            p_win = p_m if direction == "YES" else (1.0 - p_m)
            working.append((direction, tok, p_m, ask, edge, bucket, p_win * confidence))

        # Iteratively drop non-positive stakes (converges in ≤ N passes)
        active = working
        raw_stakes: list[float] = []
        for _ in range(len(working)):
            p_sum = sum(w[6] for w in active)        # Σ p_c_i
            a_sum = sum(w[3] for w in active)        # Σ ask_i
            p3    = max(1.0 - p_sum, 1e-9)          # p(neither wins)
            Q     = (1.0 - a_sum) / p3
            T     = bankroll * max(0.0, p_sum - a_sum / Q)
            s     = bankroll - T                     # sideline cash
            raw_stakes = [s * (Q * w[6] - w[3]) for w in active]
            if all(x > 0 for x in raw_stakes):
                break
            active = [w for w, x in zip(active, raw_stakes) if x > 0]
            if not active:
                return []

        # Scale by kelly_frac, then fit to city_budget proportionally
        total_scaled = sum(raw_stakes) * self.kelly_frac
        budget_ratio = min(1.0, city_budget / total_scaled) if total_scaled > 0 else 0.0

        signals = []
        for w, x_raw in zip(active, raw_stakes):
            direction, tok, p_m, ask, edge, bucket, _ = w
            alloc = float(np.clip(x_raw * self.kelly_frac * budget_ratio,
                                  self.stake_min, self.stake_max))
            if alloc < self.stake_min:
                continue
            signals.append(Signal(
                city=city, bucket=bucket, direction=direction,
                token_id=tok, p_model=round(p_m, 4),
                ask=ask, edge=round(edge, 4),
                confidence=round(confidence, 3), stake=round(alloc, 2),
                regime=regime, phase=phase,
                metar_age_s=round(metar_age, 1),
                kalman_var=round(p_var, 4),
                kriging_pct=round(kriging_pct, 3),
            ))

        return signals

    def get_signals(
        self,
        clob_books:  dict[str, dict],   # token_id → {"best_ask": float, "best_bid": float, "usd_depth": float}
        bucket_map:  dict[str, list],   # city → [(lo_c, hi_c, yes_token_id, no_token_id), ...]
        t_close_map: dict[str, float],  # city → unix ts of market close
        bankroll:    Optional[float]    = None,
        t_now:       Optional[float]    = None,
    ) -> list[Signal]:
        """
        For each active city, compute bucket probabilities and return signals
        where |p_model - ask| > EDGE_MIN with sufficient confidence.
        """
        if not self._params:
            return []

        signals: list[Signal] = []
        now = t_now or time.time()
        br  = bankroll or self.bankroll

        _g = {"no_bucket": 0, "t_close": 0, "regime": 0, "fresh": 0, "mc": 0, "conf": 0, "edge": 0, "ok": 0}

        for city, cs in self._cities.items():
            if city in self._suspended:
                continue
            if city not in bucket_map or city not in t_close_map:
                _g["no_bucket"] += 1
                continue

            t_close = t_close_map[city]
            if t_close <= now + MIN_TIME_REM:
                _g["t_close"] += 1
                continue

            # Regime gate
            if cs.regime not in REGIME_FIRE:
                _g["regime"] += 1
                continue

            # Freshness gate
            metar_age = now - cs.last_obs_ts
            if cs.last_obs_ts <= 0 or metar_age > METAR_MAX_AGE:
                _g["fresh"] += 1
                continue

            buckets_raw = bucket_map[city]   # [(lo, hi, yes_tok, no_tok), ...]
            buckets     = [(lo, hi) for lo, hi, _, _ in buckets_raw]

            # Phase must be computed before MC so sigma damping is applied correctly
            phase = _phase(cs, t_close_map[city], now)

            try:
                probs = self._forecast_bucket_probs(city, now, t_close, buckets, phase=phase)
            except Exception as e:
                logger.debug("[STWA] MC error %s: %s", city, e)
                _g["mc"] += 1
                continue

            if not probs:
                _g["mc"] += 1
                continue

            with self._lock:
                idx         = cs.idx
                p_var       = float(self._P[idx, idx])
                kriging_pct = getattr(cs, "kriging_pct_last", 0.0)

            # Confidence factors
            c_age      = math.exp(-0.15 * metar_age / 3600)
            c_variance = math.exp(-p_var / max(float(self._C[cs.idx, cs.idx]), 0.1))
            c_regime   = 1.0 if cs.regime == "SUNNY" else 0.75
            c_phase    = {"PRE_PEAK": 0.80, "AT_PEAK": 0.60, "POST_PEAK": 0.95}.get(phase, 0.80)

            confidence = c_age * c_variance * c_regime * c_phase

            if confidence < CONFIDENCE_MIN:
                logger.debug("[STWA] %s conf=%.3f (age=%.2f var=%.2f reg=%.2f ph=%.2f) p_var=%.3f C=%.3f",
                             city, confidence, c_age, c_variance, c_regime, c_phase,
                             p_var, float(self._C[cs.idx, cs.idx]))
                _g["conf"] += 1
                continue

            # LP portfolio allocation — replaces independent per-bucket Kelly.
            city_signals = self._lp_allocate_city(
                city=city, buckets_raw=buckets_raw, probs=probs,
                clob_books=clob_books, confidence=confidence,
                phase=phase, bankroll=br, metar_age=metar_age,
                p_var=p_var, kriging_pct=kriging_pct, regime=cs.regime,
            )
            if not city_signals:
                _g["edge"] += 1
            signals.extend(city_signals)

        _g["ok"] = len(signals)
        logger.info("[STWA] gates: no_bkt=%d t_close=%d regime=%d fresh=%d mc=%d conf=%d edge=%d signals=%d",
                    _g["no_bucket"], _g["t_close"], _g["regime"], _g["fresh"],
                    _g["mc"], _g["conf"], _g["edge"], _g["ok"])
        return signals

    # ── Calibration ────────────────────────────────────────────────────────────

    def record_outcome(self, city: str, p_model_at_fire: float, outcome: int) -> None:
        """Call after market resolves. outcome=1 if token won, 0 if lost."""
        if city not in self._cal_log:
            self._cal_log[city] = []
        self._cal_log[city].append((p_model_at_fire, outcome))

        # Rolling ECE on last 100 resolved buckets
        log = self._cal_log[city]
        if len(log) >= 50:
            ece = _compute_ece([p for p, _ in log[-100:]], [o for _, o in log[-100:]])
            if ece > 0.10:
                self._suspended.add(city)
                logger.warning("[STWA] %s SUSPENDED — ECE=%.3f > 0.10 (last 100 trades)", city, ece)
            elif city in self._suspended and ece < 0.07:
                self._suspended.discard(city)
                logger.info("[STWA] %s re-activated — ECE=%.3f < 0.07", city, ece)

    def get_state_snapshot(self, t_now: Optional[float] = None) -> list[dict]:
        """Dump current Kalman state per city — no CLOB data needed. For shadow logging."""
        now = t_now or time.time()
        rows = []
        for city, cs in self._cities.items():
            with self._lock:
                idx   = cs.idx
                p_mu  = float(self._X[idx])
                p_var = float(self._P[idx, idx])
            st = self._params["stations"].get(city, {})
            hour_utc = int((now % 86400) / 3600)
            nwp_mu = self._get_mu(city, hour_utc)
            rows.append({
                "ts":           round(now),
                "city":         city,
                "regime":       cs.regime,
                "running_max":  cs.running_max,
                "last_obs_ts":  cs.last_obs_ts,
                "metar_age_s":  round(now - cs.last_obs_ts) if cs.last_obs_ts > 0 else None,
                "kalman_mu":    round(p_mu, 3),
                "kalman_var":   round(p_var, 4),
                "nwp_mu":       round(nwp_mu, 2) if math.isfinite(nwp_mu) else None,
                "suspended":    city in self._suspended,
            })
        return rows

    def get_last_obs_ts(self, city: str) -> float:
        """Return the last METAR observation timestamp for a city (0.0 if unseen)."""
        cs = self._cities.get(city)
        return cs.last_obs_ts if cs is not None else 0.0

    def calibration_summary(self) -> dict:
        out = {}
        for city, log in self._cal_log.items():
            if not log:
                continue
            probs   = [p for p, _ in log]
            outcomes= [o for _, o in log]
            out[city] = {
                "n":          len(log),
                "ece":        round(_compute_ece(probs, outcomes), 4),
                "mean_p":     round(float(np.mean(probs)), 4),
                "win_rate":   round(float(np.mean(outcomes)), 4),
                "suspended":  city in self._suspended,
            }
        return out


# ── Pure helper functions ──────────────────────────────────────────────────────

def _get_kappa(st: dict, hour_utc: int) -> float:
    bin_i = hour_utc // 6
    return float(st.get("kappa", {}).get(str(bin_i), 0.5))


def _get_sigma(st: dict, hour_utc: int) -> float:
    bin_i = hour_utc // 6
    return float(st.get("sigma", {}).get(str(bin_i), 0.5))


def _current_month() -> int:
    import datetime
    return datetime.datetime.utcnow().month


def _new_max(existing: Optional[float], temp_c: float) -> float:
    if existing is None:
        return temp_c
    return max(existing, temp_c)


def _book_ask(books: dict, token_id: str) -> Optional[float]:
    b = books.get(token_id)
    if b is None:
        return None
    ask = b.get("best_ask") or b.get("ask")
    if ask is None or ask <= 0 or ask >= 1:
        return None
    return float(ask)


def _kelly_stake(
    p: float, ask: float, confidence: float,
    bankroll: float, frac: float, lo: float, hi: float
) -> float:
    b   = (1.0 / ask) - 1.0   # net odds per dollar staked
    p_c = p * confidence
    f   = (p_c * b - (1.0 - p_c)) / b
    f   = max(0.0, f) * frac
    raw = bankroll * f
    return float(np.clip(raw, lo, hi))


def _phase(cs: _CityState, t_close: float, t_now: float) -> str:
    """Classify whether we're before, at, or after the expected daily peak."""
    import datetime
    try:
        from strategy.weather_arb import CITY_PEAK_HOUR_UTC, CITY_NAME_TO_SLUG
        slug   = CITY_NAME_TO_SLUG.get(cs.city, cs.city)
        month  = datetime.datetime.utcnow().month
        peak_h = CITY_PEAK_HOUR_UTC.get(slug, {}).get(month, 14)
    except Exception:
        peak_h = 14
    # Anchor peak time to t_close (market close = local midnight), then walk back
    # to find the most recent occurrence of peak_h UTC before t_close.
    # This is timezone-agnostic and handles Americas cities where peak_h < UTC midnight.
    t_close_h = int((t_close % 86400) / 3600)
    hours_since_peak = (t_close_h - peak_h) % 24  # hours from peak to close (same day)
    peak_time = t_close - hours_since_peak * 3600
    diff_s = t_now - peak_time
    if diff_s < -3600:
        return "PRE_PEAK"
    elif diff_s > 3600:
        return "POST_PEAK"
    else:
        return "AT_PEAK"


def _compute_ece(probs: list[float], outcomes: list[int], n_bins: int = 10) -> float:
    if not probs:
        return 0.0
    p = np.array(probs)
    o = np.array(outcomes, dtype=float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece  = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi)
        if mask.sum() == 0:
            continue
        acc  = o[mask].mean()
        conf = p[mask].mean()
        ece += mask.mean() * abs(acc - conf)
    return float(ece)
