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
EDGE_MIN       = 0.04    # absolute floor on edge (p_win − ask), risk-of-ruin safety
KELLY_F_MIN    = 0.015   # minimum Kelly fraction to fire: f* = (p_c − ask)/(1 − ask)
                         # 0.015 = 1.5% of bankroll. Scales with both p and ask:
                         # high-ask bets (sells of unlikely YES) clear easily;
                         # low-ask longshot bets need larger edge to clear.
CONFIDENCE_MIN = 0.45    # minimum confidence score

# ── 2D Langevin velocity state ─────────────────────────────────────────────────
# Temperature residual X follows dX=V dt, dV=(−γV−κX)dt+σdW (damped harmonic OU).
# γ damps the velocity; scipy.linalg.expm handles over/under/critically-damped.
VELOCITY_GAMMA  = 1.5    # velocity damping coefficient (1/h)
VEL_OBS_N       = 6      # OLS buffer depth (observations)
VEL_PRIOR_VAR   = 4.0    # prior velocity variance ((°C/h)²) = (2 °C/h)²
VEL_MIN_VAR     = 0.25   # posterior floor to prevent degeneracy ((°C/h)²)
VEL_MIN_OBS_VAR = 0.50   # observation variance floor for numerical stability
METAR_MAX_AGE  = 3600    # seconds — METAR stations report hourly; allow up to 60 min
MIN_TIME_REM   = 1800    # don't fire within 30 min of market close
HOUR_BINS      = [(0, 6), (6, 12), (12, 18), (18, 24)]

# ── LP portfolio allocation ────────────────────────────────────────────────────
CITY_BUDGET_FRAC  = 0.05   # max fraction of bankroll per city
CITY_BUDGET_MAX   = 15.0   # hard cap per city (USD)
NEG_RISK_ARB_THR  = 0.85   # Σ YES ask < this → pure neg-risk arb available
                           # 0.85 leaves ~10pp for Polymarket fees (2% × 2 legs) + slippage
NEG_RISK_ARB_MIN  = 0.50   # minimum per-bucket stake for arb (below regular stake_min)
NEG_RISK_ARB_EXHAUSTIVITY = 0.95   # require Σ p_model > this to fire arb (proves bucket coverage)
NEG_RISK_ARB_BUDGET_MUL   = 1.5    # abort arb if min-feasible cost > this × city_budget
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
    last_obs_ts:    float = 0.0     # Unix timestamp of latest METAR
    running_max:    Optional[float] = None
    running_max_ts: float = 0.0     # Unix timestamp when running_max last increased
    regime:      str = "SUNNY"
    obs_count:   int = 0
    obs_date:    str = ""        # YYYY-MM-DD of the day running_max belongs to
    # For kriging contribution tracking
    last_update_from_self: bool = True
    # 2D velocity state (Langevin)
    v_hat:     float = 0.0          # posterior mean of dX/dt (°C/h)
    pv_var:    float = VEL_PRIOR_VAR # posterior variance of v_hat ((°C/h)²)
    obs_buf:   list  = field(default_factory=list)  # [(t_h, x_obs), …] last VEL_OBS_N
    last_temp: float = float("nan") # most recent raw observed temperature (°C)


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

        # Persistence paths (same directory as params)
        _base = self._params_path.parent.parent / "data"
        self._state_kalman = _base / "stwa_kalman_state.npz"
        self._state_cities = _base / "stwa_city_state.json"
        self._save_counter: int = 0

        self._load_params()
        self._restore_state()

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

    def _save_state(self) -> None:
        """Persist Kalman X/P and per-city velocity state to disk."""
        try:
            np.savez_compressed(str(self._state_kalman), X=self._X, P=self._P)
            city_data = {}
            for city, cs in self._cities.items():
                city_data[city] = {
                    "x_hat": cs.x_hat, "last_obs_ts": cs.last_obs_ts, "last_temp": cs.last_temp,
                    "running_max": cs.running_max, "running_max_ts": cs.running_max_ts,
                    "obs_date": cs.obs_date, "regime": cs.regime,
                    "obs_count": cs.obs_count,
                    "v_hat": cs.v_hat, "pv_var": cs.pv_var,
                    "obs_buf": cs.obs_buf,
                }
            with open(self._state_cities, "w") as f:
                json.dump(city_data, f)
        except Exception as e:
            logger.debug("[STWA] state save failed: %s", e)

    def _restore_state(self) -> None:
        """Restore Kalman X/P and velocity state from disk if available."""
        try:
            if self._state_kalman.exists():
                snap = np.load(str(self._state_kalman))
                X_saved, P_saved = snap["X"], snap["P"]
                if X_saved.shape == self._X.shape and P_saved.shape == self._P.shape:
                    self._X = X_saved.astype(float)
                    self._P = P_saved.astype(float)
                    logger.info("[STWA] Kalman state restored from %s", self._state_kalman)
                else:
                    logger.info("[STWA] Kalman state shape mismatch — using prior")
            if self._state_cities.exists():
                with open(self._state_cities) as f:
                    city_data = json.load(f)
                for city, d in city_data.items():
                    cs = self._cities.get(city)
                    if cs is None:
                        continue
                    cs.x_hat         = float(d.get("x_hat", 0.0))
                    cs.last_obs_ts   = float(d.get("last_obs_ts", 0.0))
                    cs.last_temp     = float(d.get("last_temp", float("nan")))
                    cs.running_max   = d.get("running_max")
                    cs.running_max_ts= float(d.get("running_max_ts", 0.0))
                    cs.obs_date      = d.get("obs_date", "")
                    cs.regime        = d.get("regime", "SUNNY")
                    cs.obs_count     = int(d.get("obs_count", 0))
                    cs.v_hat         = float(d.get("v_hat", 0.0))
                    cs.pv_var        = float(d.get("pv_var", VEL_PRIOR_VAR))
                    cs.obs_buf       = [tuple(x) for x in d.get("obs_buf", [])]
                logger.info("[STWA] city velocity state restored (%d cities)", len(city_data))
        except Exception as e:
            logger.info("[STWA] state restore failed (%s) — starting from prior", e)

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
                cs.v_hat       = 0.0
                cs.pv_var      = VEL_PRIOR_VAR
                cs.obs_buf     = []
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
            cs.v_hat       = 0.0
            cs.pv_var      = VEL_PRIOR_VAR
            cs.obs_buf     = []
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
                cs.last_temp    = temp_c
                new_max = _new_max(_new_max(cs.running_max, temp_c), running_max)
                if new_max != cs.running_max:
                    cs.running_max_ts = obs_ts
                cs.running_max  = new_max
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
            cs.last_temp    = temp_c
            new_max = _new_max(running_max, temp_c)
            if new_max != cs.running_max:
                cs.running_max_ts = obs_ts
            cs.running_max  = new_max
            cs.regime       = regime
            cs.obs_date     = today_str
            cs.obs_count   += 1
            cs.last_update_from_self = True

            # Periodic state persistence (every 20 Kalman updates)
            self._save_counter += 1
            if self._save_counter % 20 == 0:
                self._save_state()

            # ── Velocity Kalman update (OLS on RAW residuals, not x_hat) ────────
            # Raw residual y_obs is responsive; x_hat is Kalman-smoothed and lags.
            now_h = obs_ts / 3600.0
            cs.obs_buf.append((now_h, y_obs))
            if len(cs.obs_buf) > VEL_OBS_N:
                cs.obs_buf = cs.obs_buf[-VEL_OBS_N:]
            if len(cs.obs_buf) >= 3:
                v_obs, v_std = _ols_velocity(cs.obs_buf)
                R_v = max(v_std ** 2, VEL_MIN_OBS_VAR)
                K_v = cs.pv_var / (cs.pv_var + R_v)
                cs.v_hat   += K_v * (v_obs - cs.v_hat)
                cs.pv_var  *= (1.0 - K_v)
                cs.pv_var   = max(cs.pv_var, VEL_MIN_VAR)

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

        # Running maximum floor (needed for both initial condition and path_max)
        M0 = cs.running_max if cs.running_max is not None else float("-inf")

        # Simulate N_PATHS 2D Langevin paths: dX=V dt, dV=(−γV−κX)dt+σdW
        rng   = np.random.default_rng(seed=int(t_now) % (2**31))
        paths = np.zeros((N_PATHS, n_steps), dtype=np.float32)

        # Initial position: Kalman posterior, but hard-constrained by running_max.
        # If running_max was set within the last hour the temperature WAS at M0
        # recently — the Kalman sticky posterior may lie far below that due to
        # transient dips, which would produce inconsistent path initialisation.
        x_hat_eff = x_hat
        if (M0 > float("-inf") and np.isfinite(mu_grid[0])
                and (t_now - cs.running_max_ts) < 3600):
            x_hat_eff = max(x_hat, M0 - float(mu_grid[0]))

        paths[:, 0] = rng.normal(x_hat_eff, math.sqrt(max(p_var, 1e-6)),
                                 N_PATHS).astype(np.float32)
        v_now = rng.normal(cs.v_hat, math.sqrt(max(cs.pv_var, VEL_MIN_VAR)),
                           N_PATHS).astype(np.float32)

        _step_cache: dict = {}  # (kap, sig, dt_hr) → (F11,F12,F21,F22,L11,L21,L22)

        for i in range(n_steps - 1):
            h_utc = int((t_grid[i] % 86400) / 3600)
            kap   = _get_kappa(st, h_utc)
            sig   = _get_sigma(st, h_utc) * regime_mul
            dt_hr = (t_grid[i + 1] - t_grid[i]) / 3600.0

            ck = (round(kap, 4), round(sig, 4), round(dt_hr, 5))
            if ck not in _step_cache:
                _step_cache[ck] = _vel_step(kap, VELOCITY_GAMMA, sig, dt_hr)
            F11, F12, F21, F22, L11, L21, L22 = _step_cache[ck]

            n1 = rng.normal(0, 1, N_PATHS).astype(np.float32)
            n2 = rng.normal(0, 1, N_PATHS).astype(np.float32)

            new_x = (F11 * paths[:, i] + F12 * v_now + L11 * n1).astype(np.float32)
            v_now = (F21 * paths[:, i] + F22 * v_now
                     + L21 * n1 + L22 * n2).astype(np.float32)
            paths[:, i + 1] = new_x

        # Temperature paths = residual + NWP diurnal
        T_paths = (paths + mu_grid.astype(np.float32)).astype(np.float32)  # (N, steps)

        # Running maximum: compete against already-observed max
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
        Kelly allocation for a city's active bucket candidates.

        YES bets on different buckets are mutually exclusive (only one can win),
        so they use horse-race Kelly:
            x_i = s × (Q × p_c_i − ask_i)
            Q = (1 − Σask) / p_neither,  s = W − T,
            T = W × (Σp_c − Σask/Q),  p_c_i = p_i × confidence
        Collapses to standard Kelly for a single YES candidate.

        NO bets can win simultaneously (all NOs win except the one whose bucket
        contains the actual max), so they use independent Kelly with the win
        probability p_win = (1 − p_model) × confidence.

        Both pools share the city budget; stakes are scaled proportionally if
        their sum exceeds it.

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

        # ── Neg-risk arb ─────────────────────────────────────────────────────
        # If Σ YES ask < NEG_RISK_ARB_THR, buying k shares of every YES token
        # gives guaranteed profit IF the buckets are exhaustive of the outcome
        # space: payoff = k × (1 − Σask) regardless of which bucket resolves.
        #
        # Exhaustivity gate (P0-A): require Σ p_model ≥ EXHAUSTIVITY before
        # firing — proves the buckets we see cover the outcome space. If a
        # tail bucket is missing, the model still assigns it positive p, so
        # Σ p_model on visible-only buckets falls below 0.95.
        #
        # Equal-shares preservation (P0-C): the arb math requires the SAME k
        # for every bucket. Min-order constraints ($1 maker, 5 shares, 2¢
        # ticks) impose a per-bucket lower bound. We raise the global k so
        # every bucket clears its constraint; if the resulting total cost
        # exceeds BUDGET_MUL × city_budget we abort instead of cliping.
        MIN_ORDER_USD = 1.05   # CLOB $1 maker min + small buffer
        MIN_ORDER_SHARES = 5.05

        valid_yes_asks = [a for *_, a, _ in entries if a is not None and 0 < a < 1]
        if len(valid_yes_asks) == len(entries) and sum(valid_yes_asks) < NEG_RISK_ARB_THR:
            sum_ask  = sum(valid_yes_asks)
            sum_p    = sum(p for *_, p, _, _ in entries)
            arb_edge = 1.0 - sum_ask
            city_budget = min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX)

            # Exhaustivity gate
            if sum_p < NEG_RISK_ARB_EXHAUSTIVITY:
                logger.debug("[STWA] NEG_RISK_ARB %s: NOT exhaustive (Σp_model=%.3f < %.3f) — skip arb",
                             city, sum_p, NEG_RISK_ARB_EXHAUSTIVITY)
            else:
                # Equal-shares k: must satisfy min-order on EVERY bucket simultaneously
                k_budget = city_budget / sum_ask
                k_min_share = MIN_ORDER_SHARES
                k_min_dollar = max(MIN_ORDER_USD / max(a, 1e-4)
                                   for *_, a, _ in entries if a and 0 < a < 1)
                k_feasible = max(k_min_share, k_min_dollar)

                # Use the larger of budget-implied and feasibility-implied k
                k = max(k_budget, k_feasible)

                # Depth check: clamp k so no bucket order exceeds available book depth
                for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                    if not (ask_yes and 0 < ask_yes < 1):
                        continue
                    depth = (clob_books.get(yes_tok) or {}).get("usd_depth") or 0.0
                    if depth > 0 and k * ask_yes > depth:
                        k = depth / ask_yes

                # After all clamps: verify min-order still satisfied on cheapest bucket
                # If depth clamped k below feasibility, the arb is infeasible.
                if k < k_feasible:
                    logger.debug("[STWA] NEG_RISK_ARB %s: depth clamped k=%.1f below feasibility=%.1f — skip",
                                 city, k, k_feasible)
                elif k * sum_ask > city_budget * NEG_RISK_ARB_BUDGET_MUL:
                    logger.info("[STWA] NEG_RISK_ARB %s: feasible cost $%.2f exceeds %.1fx budget $%.2f — skip",
                                city, k * sum_ask, NEG_RISK_ARB_BUDGET_MUL, city_budget)
                else:
                    actual_cost = k * sum_ask
                    actual_payoff = k * 1.0
                    actual_edge = (actual_payoff - actual_cost) / actual_cost if actual_cost > 0 else 0.0
                    logger.info("[STWA] NEG_RISK_ARB %s: sum_ask=%.3f Σp=%.3f k=%.1f cost=$%.2f payoff=$%.2f edge=%.1f%%",
                                city, sum_ask, sum_p, k, actual_cost, actual_payoff, actual_edge * 100)
                    arb_signals = []
                    for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
                        if ask_yes is None or not (0 < ask_yes < 1):
                            continue
                        # Equal-shares: same k for every bucket — DON'T clip.
                        stake = round(k * ask_yes, 2)
                        # Cap individual stake at stake_max ($20) as last-resort safety
                        # but if any bucket needs > stake_max we'd already have aborted above.
                        stake = min(stake, self.stake_max)
                        arb_signals.append(Signal(
                            city=city, bucket=(lo, hi), direction="YES",
                            token_id=yes_tok, p_model=round(p_m, 4),
                            ask=ask_yes, edge=round(arb_edge, 4),
                            confidence=1.0, stake=stake,
                            regime=regime, phase=phase,
                            metar_age_s=round(metar_age, 1),
                            kalman_var=round(p_var, 4),
                            kriging_pct=round(kriging_pct, 3),
                        ))
                    if arb_signals:
                        return arb_signals

        # ── Per-bucket: pick the positive-edge side ──────────────────────────
        # Use composite gate: edge > EDGE_MIN (risk-of-ruin safety) AND
        # Kelly fraction f* > KELLY_F_MIN (sizing-aware threshold). The
        # Kelly gate scales naturally: high-ask sells need much less edge to
        # be efficient than low-ask longshots.
        def _kelly_f(p_win: float, ask: float, conf: float) -> float:
            """Confidence-adjusted Kelly fraction. Returns 0 if non-positive."""
            if ask is None or ask <= 0 or ask >= 1:
                return 0.0
            p_c = p_win * conf
            b = (1.0 / ask) - 1.0
            f = (p_c * b - (1.0 - p_c)) / b
            return max(0.0, f)

        candidates = []
        for lo, hi, yes_tok, no_tok, p_m, ask_yes, ask_no in entries:
            edge_yes = (p_m - ask_yes) if ask_yes is not None else -1.0
            edge_no  = ((1.0 - p_m) - ask_no) if ask_no is not None else -1.0
            f_yes = _kelly_f(p_m, ask_yes, confidence) if ask_yes else 0.0
            f_no  = _kelly_f(1.0 - p_m, ask_no, confidence) if ask_no else 0.0

            yes_ok = edge_yes > EDGE_MIN and f_yes > KELLY_F_MIN
            no_ok  = edge_no  > EDGE_MIN and f_no  > KELLY_F_MIN

            if yes_ok and no_ok:
                # Both sides positive ↔ neg-risk within this bucket; pick higher Kelly
                if f_yes >= f_no:
                    candidates.append(("YES", yes_tok, p_m, ask_yes, edge_yes, (lo, hi)))
                else:
                    candidates.append(("NO", no_tok, p_m, ask_no, edge_no, (lo, hi)))
            elif yes_ok:
                candidates.append(("YES", yes_tok, p_m, ask_yes, edge_yes, (lo, hi)))
            elif no_ok:
                candidates.append(("NO", no_tok, p_m, ask_no, edge_no, (lo, hi)))

        if not candidates:
            return []

        # ── Split by direction ────────────────────────────────────────────────
        city_budget = min(bankroll * CITY_BUDGET_FRAC, CITY_BUDGET_MAX)
        yes_cands = [c for c in candidates if c[0] == "YES"]
        no_cands  = [c for c in candidates if c[0] == "NO"]

        # ── YES pool: horse-race Kelly ────────────────────────────────────────
        yes_pairs: list[tuple] = []   # (candidate-tuple, raw_stake)
        if yes_cands:
            working = [(d, t, p, a, e, b, p * confidence)
                       for d, t, p, a, e, b in yes_cands]
            active = working
            raw_stakes: list[float] = []
            for _ in range(len(working)):
                p_sum = sum(w[6] for w in active)
                a_sum = sum(w[3] for w in active)
                p3    = max(1.0 - p_sum, 1e-9)
                Q     = (1.0 - a_sum) / p3
                T     = bankroll * max(0.0, p_sum - a_sum / Q)
                s     = bankroll - T
                raw_stakes = [s * (Q * w[6] - w[3]) for w in active]
                if all(x > 0 for x in raw_stakes):
                    break
                active = [w for w, x in zip(active, raw_stakes) if x > 0]
                if not active:
                    break
            for w, x in zip(active, raw_stakes):
                yes_pairs.append((w[:6], x * self.kelly_frac))

        # ── NO pool: independent Kelly (NOs can win simultaneously) ──────────
        no_pairs: list[tuple] = []
        for cand in no_cands:
            d, t, p_m, ask, edge, bucket = cand
            raw = _kelly_stake(1.0 - p_m, ask, confidence, bankroll,
                               self.kelly_frac, self.stake_min, self.stake_max)
            no_pairs.append((cand, raw))

        # ── Combine and scale to city_budget ─────────────────────────────────
        all_pairs = yes_pairs + no_pairs
        total = sum(r for _, r in all_pairs)
        budget_ratio = min(1.0, city_budget / total) if total > 0 else 0.0

        signals = []
        for (direction, tok, p_m, ask, edge, bucket), raw_stake in all_pairs:
            alloc = float(np.clip(raw_stake * budget_ratio,
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
            # Override: if running_max was updated within the last hour AND the
            # current temperature is still near the peak (decline < 0.5°C), the
            # day is still active — POST_PEAK suppression (×0.15) would be wrong.
            # Without the decline guard, a falling temperature that peaked recently
            # would still get AT_PEAK sigma, inflating high-bucket probabilities.
            if phase == "POST_PEAK" and (now - cs.running_max_ts) < 3600:
                # Only override if current temperature is still near the peak.
                # A decline ≥ 0.5°C below running_max means the day has peaked;
                # keep POST_PEAK so sigma suppression correctly limits path spread.
                temp_decline = ((cs.running_max or 0.0) - cs.last_temp
                                if math.isfinite(cs.last_temp)
                                else 0.0)
                if temp_decline < 0.5:
                    phase = "AT_PEAK"

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
            # c_age: phase-dependent freshness decay. At-peak we need tight
            # METARs (15-min decay) because a 1°C swing in 60 min changes
            # the bucket. Pre-peak the trajectory matters more than absolute
            # value so 90-min decay is fine. Post-peak the day is settled
            # so we tolerate more stale data.
            _c_age_tau_min = {"PRE_PEAK": 90.0, "AT_PEAK": 15.0, "POST_PEAK": 120.0}.get(phase, 90.0)
            c_age      = math.exp(-metar_age / 60.0 / _c_age_tau_min)
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


# ── Velocity helpers ──────────────────────────────────────────────────────────

def _ols_velocity(buf: list) -> tuple[float, float]:
    """
    OLS slope of (time_h, x_hat) buffer.  Returns (slope °C/h, slope_std °C/h).
    """
    ts = np.array([b[0] for b in buf], dtype=float)
    xs = np.array([b[1] for b in buf], dtype=float)
    t_bar = ts.mean()
    Stt   = float(((ts - t_bar) ** 2).sum())
    if Stt < 1e-9:
        return 0.0, float("inf")
    slope = float(((ts - t_bar) * xs).sum() / Stt)
    xs_fit = xs.mean() + slope * (ts - t_bar)
    rss    = float(((xs - xs_fit) ** 2).sum())
    slope_std = math.sqrt(max(rss / max(len(buf) - 2, 1) / Stt, 1e-8))
    return slope, slope_std


def _vel_step(kap: float, gamma: float, sig: float, dt_hr: float
              ) -> tuple[float, float, float, float, float, float, float]:
    """
    Exact 2D state transition for dX=V dt, dV=(−γV−κX)dt+σdW.

    Uses scipy.linalg.expm for F = exp(A·Δt) and the Van Loan (1978) method
    for the process-noise covariance Q = ∫₀^Δt exp(A·s)·B·Bᵀ·exp(Aᵀ·s) ds,
    where A=[[0,1],[−κ,−γ]] and B=[0,σ]ᵀ.

    Returns (F11,F12,F21,F22, L11,L21,L22) where L = chol(Q) lower-triangular,
    so noise_x = L11·n1, noise_v = L21·n1 + L22·n2 with n1,n2 ~ N(0,1).
    Works for all damping regimes (over-, under-, critically-damped).
    """
    from scipy.linalg import expm as _expm
    A   = np.array([[0.0, 1.0], [-kap, -gamma]])
    Q_c = np.array([[0.0, 0.0], [0.0, sig ** 2]])
    # Van Loan: build block matrix M = [[-A, Q_c], [0, Aᵀ]]
    M        = np.zeros((4, 4))
    M[:2, :2] = -A
    M[:2, 2:] = Q_c
    M[2:, 2:] = A.T
    eM  = _expm(M * dt_hr)
    F   = _expm(A * dt_hr)
    Q   = F @ eM[:2, 2:]     # Q_Δt = F · upper-right block of exp(M·Δt)
    Q   = (Q + Q.T) / 2.0    # symmetrise (numerical hygiene)
    # Cholesky of Q
    try:
        L = np.linalg.cholesky(Q + 1e-12 * np.eye(2))
    except np.linalg.LinAlgError:
        L = np.diag([math.sqrt(max(Q[0, 0], 1e-10)),
                     math.sqrt(max(Q[1, 1], 1e-10))])
    return (float(F[0, 0]), float(F[0, 1]), float(F[1, 0]), float(F[1, 1]),
            float(L[0, 0]), float(L[1, 0]), float(L[1, 1]))


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
