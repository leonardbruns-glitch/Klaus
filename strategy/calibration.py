"""
UNIFIED CALIBRATION LAYER — single source of truth for every weather strategy.

Before this module: each strategy reached into different constants:
    STRAT_3 INTRADAY   → CITY_SIGMA_C[slug][month]
    STRAT_4 TAIL       → HOT_BUST_BASE_CITIES (hardcoded set)
    STRAT_4 FOEHN      → FOEHN_WIND_SECTORS (hardcoded dict)
    STRAT_6 CITY_CTR   → CITY_VS_AIRPORT_DELTA_C (hand-sketched)
    STRAT_7 NO_SIDE    → via WeatherArb._get_forecast → ensemble
    STRAT_5 NWP_LAG    → ad-hoc μ averaging, no skill weighting

After this module: every strategy goes through Calibration.get_*() and the
underlying source (matrix, empirical analysis, hardcoded fallback) becomes
swappable in one place.

This is a READ-ONLY accessor. Matrix updates happen via build_skill_matrix.py
and refresh_skill_matrix.py. The accessor reloads on demand or interval.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


SKILL_MATRIX_PATH = Path(__file__).parent / "skill_matrix.json"
RELOAD_INTERVAL_S = 3600     # hot-swap matrix every hour if file changed

# Models considered "AI/ML-class" — they have systematic biases worth tracking.
AI_MODELS = frozenset({"ecmwf_aifs025", "gfs_graphcast025"})

# Default values used when calibration cell is missing.
DEFAULT_SIGMA_C   = 1.0
DEFAULT_BIAS_C    = 0.0
DEFAULT_RR_CV     = 0.35     # remaining-rise coefficient-of-variation
DEFAULT_FOEHN_LIFT_C = 3.0   # mean °C above forecast on Foehn days (literature)
MIN_CELL_N        = 12       # minimum n to trust a calibration cell


class Calibration:
    """Singleton-style accessor. Strategies import the module-level instance."""

    def __init__(self, matrix_path: Path = SKILL_MATRIX_PATH) -> None:
        self._matrix_path = matrix_path
        self._matrix:   dict = {}
        self._meta:     dict = {}
        self._loaded_at: float = 0.0
        self._mtime:    float = 0.0
        self._lock = threading.Lock()
        self._reload_if_stale(force=True)

    # ── Matrix lifecycle ────────────────────────────────────────────────────

    def _reload_if_stale(self, force: bool = False) -> None:
        """Reload matrix from disk if file changed or RELOAD_INTERVAL_S elapsed."""
        if not self._matrix_path.exists():
            logger.warning("[CAL] skill_matrix.json not found at %s", self._matrix_path)
            return
        try:
            cur_mtime = self._matrix_path.stat().st_mtime
        except OSError:
            return
        if not force and cur_mtime == self._mtime and \
                (time.time() - self._loaded_at) < RELOAD_INTERVAL_S:
            return
        with self._lock:
            try:
                raw = json.loads(self._matrix_path.read_text())
                self._matrix   = raw.get("stations", {})
                self._meta     = raw.get("_meta", {})
                self._loaded_at = time.time()
                self._mtime     = cur_mtime
                logger.info("[CAL] matrix loaded: %d cities, built=%s",
                            len(self._matrix), self._meta.get("built", "?"))
            except Exception as e:
                logger.error("[CAL] reload failed: %s", e)

    # ── PRIMARY GET API — used by every strategy ────────────────────────────

    def get_sigma(self, city_slug: str, month: int,
                   prefer_models: tuple[str, ...] = ()) -> float:
        """
        Best calibrated σ in °C for (city, month).

        Strategy:
          1. If prefer_models supplied: median σ across those models' cells.
          2. Otherwise: median σ across ALL skilled models for this (city, month).
          3. Floor at DEFAULT_SIGMA_C if no cell has n >= MIN_CELL_N.
        """
        self._reload_if_stale()
        city_data = self._matrix.get(city_slug, {})
        if not city_data:
            return DEFAULT_SIGMA_C

        sigmas = []
        models_to_check = prefer_models or tuple(city_data.keys())
        for model in models_to_check:
            cell = city_data.get(model, {}).get(str(month)) or \
                   city_data.get(model, {}).get(month)
            if not cell:
                continue
            if cell.get("n", 0) < MIN_CELL_N:
                continue
            sig = cell.get("sigma")
            if sig and sig > 0:
                sigmas.append(sig)
        if not sigmas:
            return DEFAULT_SIGMA_C
        sigmas.sort()
        return sigmas[len(sigmas) // 2]   # median is robust to one outlier model

    def get_bias(self, city_slug: str, model: str, month: int) -> float:
        """Bias for one specific model (forecast − actual). Positive = runs hot."""
        self._reload_if_stale()
        cell = self._matrix.get(city_slug, {}).get(model, {}).get(str(month)) or \
               self._matrix.get(city_slug, {}).get(model, {}).get(month)
        if not cell or cell.get("n", 0) < MIN_CELL_N:
            return DEFAULT_BIAS_C
        return cell.get("bias", DEFAULT_BIAS_C)

    def get_n(self, city_slug: str, model: str, month: int) -> int:
        """Sample size for diagnostic / weighting purposes."""
        self._reload_if_stale()
        cell = self._matrix.get(city_slug, {}).get(model, {}).get(str(month)) or \
               self._matrix.get(city_slug, {}).get(model, {}).get(month)
        return cell.get("n", 0) if cell else 0

    def get_model_weight(self, city_slug: str, model: str, month: int) -> float:
        """
        Per-model inverse-variance weight: w_k = 1/σ²_k.
        Returns 0 if cell missing or unreliable; caller normalizes across models.
        """
        self._reload_if_stale()
        cell = self._matrix.get(city_slug, {}).get(model, {}).get(str(month)) or \
               self._matrix.get(city_slug, {}).get(model, {}).get(month)
        if not cell or cell.get("n", 0) < MIN_CELL_N:
            return 0.0
        sig = cell.get("sigma", 0.0)
        return (1.0 / (sig * sig)) if sig > 0 else 0.0

    def has_skill_for(self, city_slug: str, model: str, month: int) -> bool:
        """True if we have a reliable bias/sigma for this (city, model, month)."""
        return self.get_n(city_slug, model, month) >= MIN_CELL_N

    def best_model_for(self, city_slug: str, month: int) -> tuple[Optional[str], float]:
        """Returns (model_name, σ) for the lowest-σ skilled model for this (city, month)."""
        self._reload_if_stale()
        best, best_sig = None, float("inf")
        for model, months in self._matrix.get(city_slug, {}).items():
            cell = months.get(str(month)) or months.get(month)
            if not cell or cell.get("n", 0) < MIN_CELL_N:
                continue
            sig = cell.get("sigma", float("inf"))
            if sig < best_sig:
                best_sig, best = sig, model
        return best, best_sig

    # ── DERIVED STATS — wraps domain-specific calibration tables ────────────

    def get_remaining_rise(self, city_slug: str, month: int, hour_utc: int) -> float:
        """Mean °C remaining rise from hour_utc to peak (5yr ASOS).
        Used by STRAT_3 INTRADAY and STRAT_4 RAPID_RISE."""
        from strategy.weather_arb import CITY_REMAINING_RISE
        return CITY_REMAINING_RISE.get(city_slug, {}).get(month, {}).get(hour_utc, 0.0)

    def get_peak_hour(self, city_slug: str, month: int) -> Optional[int]:
        """Calibrated peak-temp UTC hour for the city/month."""
        from strategy.weather_arb import CITY_PEAK_HOUR_UTC
        return CITY_PEAK_HOUR_UTC.get(city_slug, {}).get(month)

    def get_airport_vs_centre_delta(self, city_slug: str, month: int) -> Optional[float]:
        """°C delta: T_city_centre − T_airport. Used by STRAT_6 CITY_CTR."""
        from strategy.city_centre_arb import CITY_VS_AIRPORT_DELTA_C
        return CITY_VS_AIRPORT_DELTA_C.get(city_slug, {}).get(month)

    def is_hot_bust_city(self, city_slug: str, month: int) -> bool:
        """Whether this (city, month) has a documented GFS hot-bust rate >15%."""
        from strategy.weather_arb import HOT_BUST_BASE_CITIES, HOT_BUST_JAKARTA_MONTHS
        if city_slug not in HOT_BUST_BASE_CITIES:
            return False
        if city_slug == "jakarta" and month not in HOT_BUST_JAKARTA_MONTHS:
            return False
        return True

    def get_foehn_sector(self, icao: str) -> Optional[tuple[float, float]]:
        """Foehn wind sector (bearing_lo, bearing_hi) for the ICAO, or None."""
        from strategy.weather_arb import FOEHN_WIND_SECTORS
        return FOEHN_WIND_SECTORS.get(icao)

    def get_marine_sector(self, icao: str) -> Optional[tuple[float, float]]:
        """Onshore-marine wind sector for the ICAO, or None."""
        from strategy.weather_arb import MARINE_WIND_SECTORS
        return MARINE_WIND_SECTORS.get(icao)

    # ── DIAGNOSTICS ─────────────────────────────────────────────────────────

    def coverage_report(self) -> dict:
        """Return a coverage summary suitable for logging / dashboard."""
        n_cities = len(self._matrix)
        cells_per_model: dict[str, int] = {}
        well_calibrated: dict[str, int] = {}
        for city, models in self._matrix.items():
            for model, months in models.items():
                cells_per_model[model] = cells_per_model.get(model, 0) + len(months)
                for stats in months.values():
                    if stats.get("n", 0) >= MIN_CELL_N:
                        well_calibrated[model] = well_calibrated.get(model, 0) + 1
        return {
            "cities": n_cities,
            "built":  self._meta.get("built", "?"),
            "years":  self._meta.get("years", "?"),
            "cells_per_model": cells_per_model,
            "well_calibrated_cells": well_calibrated,
            "missing_ai_models": [m for m in AI_MODELS if m not in cells_per_model],
        }


# Module-level singleton. Import as: from strategy.calibration import calibration
calibration = Calibration()
