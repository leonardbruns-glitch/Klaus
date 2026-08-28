"""
Station microclimate corrections for ASOS stations used as Polymarket resolution sources.

Two effects modeled:

  1. Tarmac Heat Island (THI): ASOS sensors near airport tarmac absorb solar radiation,
     recording 0.5–2°C above city forecast on clear, low-wind days. WunderGround resolves
     against this tarmac temperature. Our NWP models predict city / open-air temp.
     → Bias-correct forecast upward on clear/calm days.

  2. Sea Breeze Floor: Coastal airports experience afternoon onshore wind that caps the
     daily maximum below inland city forecast. Wind shifts off the water, cooling the sensor.
     → Bias-correct forecast downward + widen sigma when sea-breeze conditions detected.

Integration: call compute_forecast_correction() from _get_forecast() after deriving
ensemble mean/sigma. Pass live METAR conditions when available; falls back to a
climatological mean bias when no METAR data is cached yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StationMicroclimate:
    icao: str

    # --- Tarmac Heat Island ---
    thi_base_c: float          # Max THI offset at CLR sky, 0 kt wind (°C above city forecast)
    thi_wind_cutoff_kt: float  # Wind speed above which THI is fully suppressed

    # --- Sea Breeze ---
    is_coastal: bool
    sea_dir_from: float        # Onshore wind bearing range, start (°, clockwise from N)
    sea_dir_to: float          # Onshore wind bearing range, end (°)
    sea_breeze_onset_utc: int  # UTC hour when afternoon sea breeze typically establishes
    sea_breeze_cap_c: float    # Downward correction to daily max when sea breeze active (°C)
    sea_breeze_sigma_add: float  # Additional sigma uncertainty when sea breeze active (°C)

    # --- Climatological mean bias ---
    # Net expected offset (°C) to add to forecast_mu when no live METAR is available.
    # Derived from: P(clear & calm) × thi_base_c − P(sea-breeze) × sea_breeze_cap_c.
    # Positive = station tends to run hotter than NWP model output.
    calibrated_bias_c: float


STATION_MICROCLIMATE: dict[str, StationMicroclimate] = {
    # KLGA — LaGuardia (NYC): exposed tarmac + modest Atlantic sea-breeze via Jamaica Bay
    "KLGA": StationMicroclimate(
        icao="KLGA",
        thi_base_c=0.7, thi_wind_cutoff_kt=10.0,
        is_coastal=True,
        sea_dir_from=140.0, sea_dir_to=220.0,   # S–SW onshore from Jamaica Bay / Atlantic
        sea_breeze_onset_utc=18,                 # ~2 pm EDT
        sea_breeze_cap_c=0.5, sea_breeze_sigma_add=0.3,
        calibrated_bias_c=0.4,  # ~60% clear-calm days @ +0.7 offset net ≈ +0.4
    ),

    # KORD — O'Hare (Chicago): large exposed field + Lake Michigan lake-breeze (E–ENE)
    "KORD": StationMicroclimate(
        icao="KORD",
        thi_base_c=0.8, thi_wind_cutoff_kt=12.0,
        is_coastal=True,
        sea_dir_from=60.0, sea_dir_to=120.0,    # ENE–ESE from Lake Michigan
        sea_breeze_onset_utc=17,                 # ~noon CDT
        sea_breeze_cap_c=1.0, sea_breeze_sigma_add=0.5,
        calibrated_bias_c=0.5,  # THI partially offset by frequent lake-breeze incursions
    ),

    # KLAX — LAX (Los Angeles): Pacific marine layer regularly caps daily max; strong sea breeze W–NW
    "KLAX": StationMicroclimate(
        icao="KLAX",
        thi_base_c=1.0, thi_wind_cutoff_kt=8.0,
        is_coastal=True,
        sea_dir_from=240.0, sea_dir_to=300.0,   # W–NW from Pacific
        sea_breeze_onset_utc=20,                 # ~1 pm PDT
        sea_breeze_cap_c=2.0, sea_breeze_sigma_add=0.8,
        calibrated_bias_c=0.2,  # Marine layer + sea breeze nearly neutralise THI at KLAX
    ),

    # KMIA — Miami Intl: high humidity limits THI; moderate Atlantic sea breeze E–SE
    "KMIA": StationMicroclimate(
        icao="KMIA",
        thi_base_c=0.5, thi_wind_cutoff_kt=10.0,
        is_coastal=True,
        sea_dir_from=80.0, sea_dir_to=160.0,    # E–SE from Biscayne Bay / Atlantic
        sea_breeze_onset_utc=17,                 # ~1 pm EDT
        sea_breeze_cap_c=0.8, sea_breeze_sigma_add=0.4,
        calibrated_bias_c=0.3,
    ),

    # KSFO — SFO (San Francisco): famous marine layer + very strong NW sea breeze; THI weak
    "KSFO": StationMicroclimate(
        icao="KSFO",
        thi_base_c=0.6, thi_wind_cutoff_kt=8.0,
        is_coastal=True,
        sea_dir_from=270.0, sea_dir_to=330.0,   # W–NNW from Pacific
        sea_breeze_onset_utc=20,                 # ~1 pm PDT
        sea_breeze_cap_c=3.0, sea_breeze_sigma_add=1.0,
        calibrated_bias_c=0.0,  # Marine layer + sea breeze roughly cancel tarmac offset
    ),

    # RJTT — Haneda (Tokyo): Tokyo Bay SE–S sea breeze in summer; clear winter days add THI
    "RJTT": StationMicroclimate(
        icao="RJTT",
        thi_base_c=0.8, thi_wind_cutoff_kt=10.0,
        is_coastal=True,
        sea_dir_from=120.0, sea_dir_to=200.0,   # SE–S from Tokyo Bay
        sea_breeze_onset_utc=4,                  # ~1 pm JST
        sea_breeze_cap_c=0.8, sea_breeze_sigma_add=0.4,
        calibrated_bias_c=0.5,
    ),

    # EGLC — London City Airport: urban UHI + small tarmac; not coastal (40 mi inland)
    "EGLC": StationMicroclimate(
        icao="EGLC",
        thi_base_c=0.5, thi_wind_cutoff_kt=12.0,
        is_coastal=False,
        sea_dir_from=0.0, sea_dir_to=0.0,
        sea_breeze_onset_utc=0,
        sea_breeze_cap_c=0.0, sea_breeze_sigma_add=0.0,
        calibrated_bias_c=0.3,  # Urban heat island on clear/calm days
    ),
}


def _is_onshore(wind_dir_deg: float, sea_dir_from: float, sea_dir_to: float) -> bool:
    """True if wind_dir_deg falls within the [sea_dir_from, sea_dir_to] arc."""
    if sea_dir_from <= sea_dir_to:
        return sea_dir_from <= wind_dir_deg <= sea_dir_to
    # Range wraps through 0/360 (e.g. 350–20)
    return wind_dir_deg >= sea_dir_from or wind_dir_deg <= sea_dir_to


def compute_forecast_correction(
    icao: str,
    forecast_mu_c: float,
    sigma_c: float,
    wind_speed_kt: Optional[float] = None,
    wind_dir_deg: Optional[float] = None,
    sky_cover: Optional[str] = None,
    utc_hour: Optional[int] = None,
) -> tuple[float, float]:
    """
    Apply microclimate corrections to a temperature forecast for a specific ICAO station.

    With live METAR data supplied:
      - Sea breeze active (onshore wind past onset hour) → subtract sea_breeze_cap_c from mu,
        add sea_breeze_sigma_add to sigma.
      - Offshore/calm + clear sky → add THI correction to mu.

    Without METAR data (any arg is None):
      - Apply climatological mean bias only (calibrated_bias_c).

    Sky factor for THI: CLR=1.0, FEW=0.8, SCT=0.4, BKN=0.0, OVC=0.0
    Wind factor for THI: linear from 1.0 at 0 kt to 0.0 at thi_wind_cutoff_kt.

    Returns (corrected_mu_c, corrected_sigma_c).
    """
    mc = STATION_MICROCLIMATE.get(icao)
    if mc is None:
        return forecast_mu_c, sigma_c

    # No live METAR: climatological correction only
    if wind_speed_kt is None or wind_dir_deg is None or sky_cover is None:
        return round(forecast_mu_c + mc.calibrated_bias_c, 3), sigma_c

    # Sea breeze takes precedence over THI
    sea_breeze_active = (
        mc.is_coastal
        and _is_onshore(wind_dir_deg, mc.sea_dir_from, mc.sea_dir_to)
        and (utc_hour is None or utc_hour >= mc.sea_breeze_onset_utc)
    )
    if sea_breeze_active:
        return (
            round(forecast_mu_c - mc.sea_breeze_cap_c, 3),
            round(sigma_c + mc.sea_breeze_sigma_add, 3),
        )

    # Tarmac heat island: suppressed by wind and cloud cover
    sky_thi: dict[str, float] = {"CLR": 1.0, "FEW": 0.8, "SCT": 0.4, "BKN": 0.0, "OVC": 0.0}
    sky_f = sky_thi.get(sky_cover, 0.4)
    wind_f = max(0.0, 1.0 - wind_speed_kt / mc.thi_wind_cutoff_kt)
    thi = mc.thi_base_c * sky_f * wind_f
    return round(forecast_mu_c + thi, 3), sigma_c
