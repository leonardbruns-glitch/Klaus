"""
Skill-weighted NWP ensemble for weather_arb.py.

Replaces the arithmetic average with an optimal inverse-variance combination
(Best Linear Unbiased Estimator) calibrated on historical monthly performance.

Usage in _get_forecast():
    from strategy.ensemble_weights import WeightedEnsemble
    _ensemble = WeightedEnsemble()               # once at class init
    mu, sigma = _ensemble.combine(slug, month, model_values)
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILL_MATRIX_PATH = Path(__file__).parent / "skill_matrix.json"

# If a model has fewer than this many historical days for a (station, month),
# its individual weight is zeroed and equal-weight fallback applies.
MIN_N_PER_MONTH = 12

# Inter-model correlation inflation: NWP models share physics and assimilation
# systems, so their errors are correlated. σ_ens is inflated by γ before use.
GAMMA = 1.30

# Minimum weight per model in the final mixture (prevents any single model from
# dominating to zero; softens the inverse-variance when n is small).
W_FLOOR = 0.03


class WeightedEnsemble:
    """
    Loads skill_matrix.json on construction. Call .combine() each forecast.

    .combine(slug, month, model_values) → (bias_corrected_mu, inflated_sigma)

    model_values: dict[model_name, forecast_max_celsius]
                  Models not in skill matrix → treated as equal-weight with no bias correction.
    """

    def __init__(self) -> None:
        self._matrix: dict = {}
        self._meta: dict = {}
        self._load()

    def _load(self) -> None:
        if not SKILL_MATRIX_PATH.exists():
            logger.warning("[ENS] skill_matrix.json not found — using equal weights. "
                           "Run analysis/build_skill_matrix.py to generate it.")
            return
        try:
            raw = json.loads(SKILL_MATRIX_PATH.read_text())
            self._meta   = raw.get("_meta", {})
            self._matrix = raw.get("stations", {})
            logger.info("[ENS] skill matrix loaded: %d stations, built %s",
                        len(self._matrix), self._meta.get("built", "?"))
        except Exception as e:
            logger.error("[ENS] failed to load skill matrix: %s", e)

    def reload(self) -> None:
        """Call this after re-running build_skill_matrix.py without restarting."""
        self._load()

    def _skill_entry(self, slug: str, model: str, month: int) -> Optional[dict]:
        """Returns {bias, sigma, n} or None if unavailable / insufficient data."""
        entry = self._matrix.get(slug, {}).get(model, {}).get(str(month))
        if entry is None:
            entry = self._matrix.get(slug, {}).get(model, {}).get(month)
        if entry is None:
            return None
        if entry.get("n", 0) < MIN_N_PER_MONTH:
            return None
        if entry.get("sigma", 0.0) <= 0.0:
            return None
        return entry

    def compute_weights(
        self, slug: str, month: int, available_models: list[str]
    ) -> dict[str, tuple[float, float]]:
        """
        Returns {model: (weight, bias_c)} for each available model.

        Weight derivation:
          raw_w_k = 1 / σ²_k   [inverse variance, penalises high residual variance]
          w_k     = raw_w_k / Σ raw_w_j  [normalise]

        Models without sufficient historical data fall back to equal weight
        and zero bias correction.
        """
        inv_var: dict[str, float] = {}
        biases:  dict[str, float] = {}

        for m in available_models:
            entry = self._skill_entry(slug, m, month)
            if entry:
                inv_var[m] = 1.0 / (entry["sigma"] ** 2)
                biases[m]  = entry["bias"]
            # else: model absent from skill matrix, handled in fallback below

        if not inv_var:
            # No skill data at all — equal weights, no bias correction
            n = len(available_models)
            return {m: (1.0 / n, 0.0) for m in available_models}

        total = sum(inv_var.values())
        weights_raw = {m: v / total for m, v in inv_var.items()}

        # Apply W_FLOOR and re-normalise (prevents extreme single-model dominance)
        weights_floored = {m: max(W_FLOOR, w) for m, w in weights_raw.items()}
        total_floored = sum(weights_floored.values())
        weights_final = {m: w / total_floored for m, w in weights_floored.items()}

        # Models without skill data but present in the forecast get a W_FLOOR share
        # with no bias correction
        result = {}
        for m in available_models:
            if m in weights_final:
                result[m] = (weights_final[m], biases.get(m, 0.0))
            else:
                result[m] = (W_FLOOR / (total_floored + W_FLOOR), 0.0)

        return result

    def median_model_sigma(self, slug: str, month: int) -> Optional[float]:
        """
        Median per-model residual sigma for (slug, month) from the skill matrix.
        Returns None if fewer than 2 qualified models exist.
        Used as the asos_sigma_floor for cities not in CITY_SIGMA_C.
        """
        sigmas = []
        for model_data in self._matrix.get(slug, {}).values():
            entry = model_data.get(str(month)) or model_data.get(month)
            if entry and entry.get("n", 0) >= MIN_N_PER_MONTH and entry.get("sigma", 0) > 0:
                sigmas.append(entry["sigma"])
        if len(sigmas) < 2:
            return None
        sigmas.sort()
        return sigmas[len(sigmas) // 2]

    def combine(
        self,
        slug: str,
        month: int,
        model_values: dict[str, float],
        asos_sigma_floor: Optional[float] = None,
    ) -> tuple[float, float]:
        """
        Returns (bias_corrected_mu, inflated_sigma).

        mu formula:
            μ = Σ_k w_k × (F_k - B_k)

        Sigma formula (BLUE with correlation inflation):
            σ_blue = 1 / sqrt(Σ_k w_k / σ²_k × total_inv_var)
            Wait, cleaner:
            σ_ens  = 1 / sqrt(Σ_k 1/σ²_k)  [BLUE theoretical minimum]
            σ_final = max(asos_floor, GAMMA × σ_ens)

        If skill matrix unavailable: arithmetic mean + asos_sigma_floor (original behaviour).
        """
        if not model_values:
            return 0.0, asos_sigma_floor or 1.5

        available = list(model_values.keys())
        month_weights = self.compute_weights(slug, month, available)

        # Bias-corrected weighted mean
        mu = sum(w * (model_values[m] - b)
                 for m, (w, b) in month_weights.items()
                 if m in model_values)

        # BLUE combined sigma
        # σ_ens = 1/sqrt(Σ 1/σ²_k) — combine only models with real skill data
        sum_inv_var = 0.0
        n_skilled = 0
        for m in available:
            entry = self._skill_entry(slug, m, month)
            if entry:
                sum_inv_var += 1.0 / entry["sigma"] ** 2
                n_skilled += 1

        if n_skilled >= 2 and sum_inv_var > 0:
            sigma_ens = 1.0 / math.sqrt(sum_inv_var)
            sigma = GAMMA * sigma_ens
        else:
            # Fallback: inter-model spread
            vals = list(model_values.values())
            sigma = max(vals) - min(vals) if len(vals) > 1 else 1.5

        if asos_sigma_floor is not None:
            sigma = max(asos_sigma_floor, sigma)

        return round(mu, 3), round(sigma, 3)
