"""
Upstream Oracle — cross-city synoptic anomaly detector for weather prediction markets.

Triggers when:
  A. An upstream city confirms an observed max-temp anomaly > ANOMALY_Z_MIN standard
     deviations from its 10-year climatological mean (wu_high_c vs _climatology mean_max_c).
  B. Synoptic coherence: ≥2 cities in the same region show anomaly in the same direction
     simultaneously (or single city with z > ANOMALY_Z_SOLO).
  C. A downstream city (per upstream_map.DOWNSTREAM_*) has an open tomorrow market
     priced below DOWNSTREAM_FAIR_FLOOR.

Called from weather_arb._check_wu_transitions() after each new actual is processed.
Entry is routed through the normal _enter() path with entry_class="STRAT_5_UPSTREAM".
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular import; arb instance passed as opaque object

logger = logging.getLogger(__name__)

SKILL_MATRIX_PATH = Path(__file__).parent / "skill_matrix.json"

# ── Thresholds ────────────────────────────────────────────────────────────────
ANOMALY_Z_MIN   = 2.0   # minimum z-score (paired coherence)
ANOMALY_Z_SOLO  = 2.5   # z-score for single-city trigger (isolated region)
DOWNSTREAM_FAIR_FLOOR = 0.50   # only enter if downstream fair_prob > this
DOWNSTREAM_ASK_CAP    = 0.55   # skip if market has already repriced
DOWNSTREAM_EDGE_MIN   = 0.10   # minimum edge vs ask

# Rolling buffer: last N city actuals for coherence check
COHERENCE_WINDOW_DAYS = 1   # same calendar day (UTC)

# Module-level: city_slug → {date_iso: wu_high_c}
# Updated by notify_actual(); cleared on new day.
_actual_buffer: dict[str, dict[str, float]] = {}
_clim_cache: dict | None = None


def _load_clim() -> dict:
    global _clim_cache
    if _clim_cache is None:
        try:
            matrix = json.loads(SKILL_MATRIX_PATH.read_text())
            _clim_cache = {
                slug: data.get("_climatology", {})
                for slug, data in matrix.get("stations", {}).items()
            }
        except Exception as e:
            logger.warning("[Oracle] failed to load skill_matrix climatology: %s", e)
            _clim_cache = {}
    return _clim_cache


def reload_climatology() -> None:
    """Force reload on next access (call after skill_matrix.json is updated)."""
    global _clim_cache
    _clim_cache = None


def _z_score(city_slug: str, wu_high_c: float, month: int) -> float | None:
    """Return anomaly z-score for this observation vs climatological baseline."""
    clim = _load_clim()
    city_clim = clim.get(city_slug, {})
    cell = city_clim.get(str(month))
    if not cell:
        return None
    mean = cell["mean_max_c"]
    sigma = cell["sigma_obs"]
    if sigma <= 0:
        return None
    return (wu_high_c - mean) / sigma


def notify_actual(city_slug: str, valid_day: str, wu_high_c: float) -> None:
    """
    Call from weather_arb._check_wu_transitions() for every new actual logged.
    Updates the rolling buffer used by check_upstream_signal().
    """
    if city_slug not in _actual_buffer:
        _actual_buffer[city_slug] = {}
    _actual_buffer[city_slug][valid_day] = wu_high_c


def check_upstream_signal(
    city_slug: str,
    valid_day: str,
    wu_high_c: float,
    month: int,
) -> list[dict]:
    """
    Main entry point. Called after notify_actual() for the triggering city.

    Returns list of entry specs:
        [{"city_slug": str, "direction": "hot"|"cold", "z": float}, ...]
    Each entry spec represents a downstream city that should be scanned for a buy.
    The caller (weather_arb) handles the actual market fetch + entry.
    """
    from strategy.upstream_map import get_downstream, get_region_cities

    z = _z_score(city_slug, wu_high_c, month)
    if z is None:
        return []

    direction = "hot" if z > 0 else "cold"
    abs_z = abs(z)

    if abs_z < ANOMALY_Z_MIN:
        return []

    # --- Synoptic coherence check ---
    region_cities = get_region_cities(city_slug)
    region_anomalies: list[tuple[str, float]] = []

    for peer in region_cities:
        peer_temps = _actual_buffer.get(peer, {})
        peer_temp = peer_temps.get(valid_day)
        if peer_temp is None:
            continue
        peer_clim = _load_clim().get(peer, {})
        peer_cell = peer_clim.get(str(month))
        if not peer_cell:
            continue
        peer_z = (peer_temp - peer_cell["mean_max_c"]) / peer_cell["sigma_obs"]
        if (direction == "hot" and peer_z >= ANOMALY_Z_MIN) or \
           (direction == "cold" and peer_z <= -ANOMALY_Z_MIN):
            region_anomalies.append((peer, peer_z))

    n_coherent = len(region_anomalies)
    is_isolated_region = len(region_cities) <= 1

    # Accept if: ≥2 coherent peers, OR isolated region + z >= solo threshold
    if n_coherent < 2 and not (is_isolated_region and abs_z >= ANOMALY_Z_SOLO):
        logger.debug(
            "[Oracle] %s z=%.2f %s — coherence failed (%d/%d peers)",
            city_slug, z, direction, n_coherent, len(region_cities)
        )
        return []

    logger.info(
        "[Oracle] SIGNAL %s z=%.2f %s — %d coherent peers in region",
        city_slug, z, direction, n_coherent
    )

    downstream = get_downstream(city_slug, month)
    if not downstream:
        logger.debug("[Oracle] %s — no downstream cities for month %d", city_slug, month)
        return []

    targets = []
    for ds_city in downstream:
        targets.append({"city_slug": ds_city, "direction": direction, "z": abs_z, "trigger": city_slug})

    return targets


SYNOPTIC_R = 0.50   # typical 500mb synoptic correlation for 300-600mi same-regime city pairs
                    # (NCEP/NCAR reanalysis literature; 0.5 is conservative for 24h lag)


def estimate_downstream_bucket_prob(
    trigger_z: float,
    direction: str,
    ds_city: str,
    month: int,
    lo_c: float | None,
    hi_c: float | None,
) -> float | None:
    """
    Bivariate-normal estimate: P(downstream bucket) conditional on upstream anomaly.

    Model:
        mu_cond   = mu_ds + r * z_trigger * sigma_ds    (conditional mean shift)
        sigma_cond = sigma_ds * sqrt(1 - r^2)            (conditional sigma, always < sigma_ds)
        P(bucket) = Φ((hi - mu_cond)/sigma_cond) - Φ((lo - mu_cond)/sigma_cond)

    Returns probability in [0,1], or None if climatology missing.
    """
    from math import erf, sqrt

    clim = _load_clim()
    cell = clim.get(ds_city, {}).get(str(month))
    if not cell:
        return None

    mu_ds    = cell["mean_max_c"]
    sigma_ds = cell["sigma_obs"]

    signed_z = trigger_z if direction == "hot" else -trigger_z
    mu_cond    = mu_ds + SYNOPTIC_R * signed_z * sigma_ds
    sigma_cond = sigma_ds * math.sqrt(1 - SYNOPTIC_R ** 2)

    def phi(x: float) -> float:
        return 0.5 * (1 + erf(x / math.sqrt(2)))

    lo = lo_c if lo_c is not None else float("-inf")
    hi = hi_c if hi_c is not None else float("inf")
    p_hi = 1.0 if hi == float("inf")  else phi((hi - mu_cond) / sigma_cond)
    p_lo = 0.0 if lo == float("-inf") else phi((lo - mu_cond) / sigma_cond)
    return round(max(0.0, min(1.0, p_hi - p_lo)), 4)
