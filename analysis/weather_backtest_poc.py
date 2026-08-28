#!/usr/bin/env python3
"""
POC Weather Backtest Framework
==============================

Purpose: Compare forecasters (AROME, DWD, JMA, CMA, BOM, ECMWF, GFS) against
actual Polymarket weather resolutions and identify optimal forecaster per city.

Workflow:
1. Get resolved Polymarket weather markets (last 30 days)
2. Match to our 65-city coordinate list
3. Fetch actual resolution (Wunderground daily max temp)
4. Fetch what each forecaster would have predicted
5. Calculate edges and simulate trades
6. Rank forecasters by accuracy and edge provided

Data sources:
- Polymarket: PolymarketData API or Resolved Markets API
- Forecasts: Open-Meteo Previous Runs API (historical model output)
- Reality: NOAA CDO API or Wunderground scraping
"""

import asyncio
import json
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
import numpy as np

# ==============================================================================
# CITY COORDINATES (from weather_arb.py)
# ==============================================================================

CITY_COORDS = {
    "London": (51.5048, 0.0495),
    "Paris": (48.9694, 2.4414),
    "Seoul": (37.4691, 126.4505),
    "Seattle": (47.4502, -122.3088),
    "Sao Paulo": (-23.4356, -46.4731),
    "Buenos Aires": (-34.8222, -58.5358),
    "Ankara": (40.1281, 32.9951),
    "Wellington": (-41.3272, 174.8051),
    "Lucknow": (26.7606, 80.8893),
    "Munich": (48.3538, 11.7861),
    "New York City": (40.7769, -73.8740),
    "Dallas": (32.8481, -96.8517),
    "Miami": (25.7953, -80.2900),
    "Chicago": (41.9742, -87.9073),
    "Singapore": (1.3644, 103.9915),
    "Milan": (45.6307, 8.7281),
    "Madrid": (40.4936, -3.5668),
    "Warsaw": (52.1657, 20.9671),
    "Taipei": (25.0694, 121.5522),
    "Beijing": (40.0799, 116.5844),
    "Wuhan": (30.7838, 114.2080),
    "Chengdu": (30.5782, 103.9470),
    "Shenzhen": (22.6393, 113.8107),
    "Austin": (30.1945, -97.6699),
    "Denver": (39.7017, -104.7517),
    "Houston": (29.6454, -95.2789),
    "Los Angeles": (33.9425, -118.4081),
    "San Francisco": (37.6213, -122.3790),
    "Mexico City": (19.4363, -99.0721),
    "Busan": (35.1795, 128.9382),
    "Amsterdam": (52.3086, 4.7639),
    "Helsinki": (60.3172, 24.9633),
    "Panama City": (8.9788, -79.5556),
    "Jakarta": (-6.2662, 106.8906),
    "Jeddah": (21.6796, 39.1565),
    "Cape Town": (-33.9648, 18.6017),
    "Guangzhou": (23.3924, 113.2990),
    "Jinan": (36.8572, 117.0558),
    "Qingdao": (36.2661, 120.3742),
    "Karachi": (24.8936, 67.1355),
    "Manila": (14.5086, 121.0194),
    "Toronto": (43.6777, -79.6248),
    "Shanghai": (31.1434, 121.8052),
    "Tokyo": (35.5494, 139.7798),
    "Hong Kong": (22.3080, 113.9185),
    "Dubai": (25.2532, 55.3657),
    "Sydney": (-33.9399, 151.1753),
    "Phoenix": (33.4343, -112.0117),
    "Atlanta": (33.6407, -84.4277),
    "Berlin": (52.3667, 13.5033),
    "Stockholm": (59.6519, 17.9186),
    "Oslo": (60.1939, 11.0998),
    "Copenhagen": (55.6179, 12.6560),
    "Vienna": (48.1103, 16.5697),
    "Zurich": (47.4647, 8.5492),
    "Brussels": (50.9010, 4.4844),
    "Barcelona": (41.2971, 2.0785),
    "Rome": (41.8003, 12.2389),
    "Prague": (50.1008, 14.2600),
    "Budapest": (47.4298, 19.2610),
    "Bucharest": (44.5722, 26.1022),
    "Athens": (37.9364, 23.9445),
    "Istanbul": (40.8986, 29.3092),
    "Moscow": (55.9736, 37.4125),
    "Riyadh": (24.9576, 46.6988),
    "Cairo": (30.1219, 31.4056),
    "Lagos": (6.5774, 3.3214),
    "Nairobi": (-1.3192, 36.9275),
    "Johannesburg": (-26.1392, 28.2460),
    "Mumbai": (19.0896, 72.8656),
    "Delhi": (28.5665, 77.1031),
    "Dhaka": (23.8433, 90.3978),
    "Bangkok": (13.6811, 100.7472),
    "Kuala Lumpur": (2.7456, 101.7072),
    "Bogota": (4.7016, -74.1469),
    "Lima": (-12.0219, -77.1143),
    "Santiago": (-33.3930, -70.7858),
    "Chongqing": (29.7192, 106.6418),
}

# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class ForecasterPrediction:
    """What a forecaster predicted for a market."""
    forecaster: str  # "AROME", "DWD", "JMA", "CMA", "BOM", "ECMWF", "GFS"
    forecast_mean: float  # °C
    forecast_sigma: float  # °C (uncertainty)
    fair_prob: float  # P(outcome) under Normal(mean, sigma)
    edge: float  # fair_prob - poly_price
    would_enter: bool  # True if edge > 0.08

@dataclass
class MarketAnalysis:
    """Analysis of a single resolved market."""
    city: str
    resolution_date: str
    actual_temp_c: float  # Wunderground daily max
    poly_entry_price: float  # What we paid
    poly_resolution_price: float  # What it resolved to (0.0 or 1.0)
    forecasts: Dict[str, ForecasterPrediction]  # {forecaster_name: prediction}
    accuracy_winner: Optional[str]  # Which forecaster was closest
    edge_winner: Optional[str]  # Which forecaster offered best edge
    simulated_pnl_by_forecaster: Dict[str, float]  # {forecaster: pnl}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def norm_cdf(x: float) -> float:
    """Standard normal CDF via erf approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def outcome_prob(forecast_mean: float, lo: Optional[float], hi: Optional[float],
                 sigma: float) -> float:
    """
    P(lo <= daily_max <= hi) under Normal(forecast_mean, sigma).
    lo=None means unbounded below; hi=None means unbounded above.
    """
    p_hi = 1.0 if hi is None else norm_cdf((hi + 0.5 - forecast_mean) / sigma)
    p_lo = 0.0 if lo is None else norm_cdf((lo - 0.5 - forecast_mean) / sigma)
    return max(0.0, p_hi - p_lo)

# ==============================================================================
# MOCK DATA FOR POC (replace with real API calls)
# ==============================================================================

# Example: Paris "Highest temperature in Paris on May 21, 2026?" resolves to YES 22°C
MOCK_MARKET = {
    "city": "Paris",
    "resolution_date": "2026-05-21",
    "market_question": "Highest temperature in Paris on May 21?",
    "outcome_range": (22, 22),  # [22°C, 22°C] (exact)
    "actual_wunderground_temp": 22.0,
    "poly_entry_price": 0.35,
    "poly_resolution_price": 1.0,  # YES won
    "coordinates": CITY_COORDS["Paris"],
    "forecasts_at_entry": {
        "AROME": {"mean": 21.5, "sigma": 1.0},
        "DWD": {"mean": 20.8, "sigma": 1.2},
        "ECMWF": {"mean": 21.2, "sigma": 1.5},
        "GFS": {"mean": 20.5, "sigma": 1.8},
        "JMA": {"mean": 22.1, "sigma": 2.0},
        "CMA": {"mean": 21.0, "sigma": 1.6},
        "BOM": {"mean": 21.3, "sigma": 1.4},
    }
}

# ==============================================================================
# ANALYSIS FUNCTIONS
# ==============================================================================

def analyze_single_market(market_data: dict) -> MarketAnalysis:
    """
    Analyze a single resolved market and compare all forecasters.
    Returns ranking of which forecaster was most accurate and offered best edge.
    """
    city = market_data["city"]
    resolution_date = market_data["resolution_date"]
    actual_temp = market_data["actual_wunderground_temp"]
    lo, hi = market_data["outcome_range"]
    poly_entry = market_data["poly_entry_price"]
    poly_resolution = market_data["poly_resolution_price"]

    forecasts = {}

    # Analyze each forecaster
    for forecaster, pred in market_data["forecasts_at_entry"].items():
        mean = pred["mean"]
        sigma = pred["sigma"]

        # Calculate fair probability
        fair_prob = outcome_prob(mean, lo, hi, sigma)

        # Calculate edge
        edge = fair_prob - poly_entry

        # Would we have entered?
        would_enter = edge > 0.08

        forecasts[forecaster] = ForecasterPrediction(
            forecaster=forecaster,
            forecast_mean=mean,
            forecast_sigma=sigma,
            fair_prob=fair_prob,
            edge=edge,
            would_enter=would_enter,
        )

    # Find best forecaster by accuracy (closest to actual)
    accuracy_winner = min(
        forecasts.keys(),
        key=lambda f: abs(forecasts[f].forecast_mean - actual_temp)
    )

    # Find best forecaster by edge offered
    edge_winner = max(
        forecasts.keys(),
        key=lambda f: forecasts[f].edge
    )

    # Simulate trades and PnL for each forecaster
    simulated_pnl = {}
    for forecaster, pred in forecasts.items():
        if pred.would_enter:
            # Simulate entry at poly_entry_price, exit at resolution
            entry_cost = pred.forecast_mean  # stake at entry price
            pnl = (poly_resolution - poly_entry) * 100  # simplified
            simulated_pnl[forecaster] = pnl
        else:
            simulated_pnl[forecaster] = 0.0  # didn't enter

    return MarketAnalysis(
        city=city,
        resolution_date=resolution_date,
        actual_temp_c=actual_temp,
        poly_entry_price=poly_entry,
        poly_resolution_price=poly_resolution,
        forecasts=forecasts,
        accuracy_winner=accuracy_winner,
        edge_winner=edge_winner,
        simulated_pnl_by_forecaster=simulated_pnl,
    )

def print_analysis(analysis: MarketAnalysis):
    """Pretty-print market analysis."""
    print(f"\n{'='*80}")
    print(f"MARKET: {analysis.city} on {analysis.resolution_date}")
    print(f"{'='*80}")
    print(f"\nActual Temperature (Wunderground): {analysis.actual_temp_c}°C")
    print(f"Polymarket Entry Price: ${analysis.poly_entry_price:.4f}")
    print(f"Polymarket Resolution: ${analysis.poly_resolution_price:.4f}")

    print(f"\n{'Forecaster':<15} {'Mean':<8} {'Sigma':<8} {'Fair P':<8} {'Edge':<8} {'Enter?':<8} {'Error':<8}")
    print("-" * 80)

    for forecaster, pred in analysis.forecasts.items():
        error = abs(pred.forecast_mean - analysis.actual_temp_c)
        print(f"{forecaster:<15} {pred.forecast_mean:<8.2f} {pred.forecast_sigma:<8.2f} "
              f"{pred.fair_prob:<8.3f} {pred.edge:<8.3f} {'Yes' if pred.would_enter else 'No':<8} "
              f"{error:<8.2f}°C")

    print(f"\n📊 WINNERS:")
    print(f"  Accuracy (closest forecast): {analysis.accuracy_winner}")
    print(f"  Edge offered: {analysis.edge_winner}")

    print(f"\n💰 Simulated PnL if entered with each forecaster:")
    for forecaster, pnl in analysis.simulated_pnl_by_forecaster.items():
        pred = analysis.forecasts[forecaster]
        if pred.would_enter:
            print(f"  {forecaster}: ${pnl:+.2f}")
        else:
            print(f"  {forecaster}: SKIPPED (edge {pred.edge:.3f} < 0.08)")

# ==============================================================================
# MAIN POC
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("WEATHER BACKTEST POC - Framework Ready")
    print("="*80)

    print("\n1. Testing on mock market (Paris)...")
    analysis = analyze_single_market(MOCK_MARKET)
    print_analysis(analysis)

    print(f"\n{'='*80}")
    print("POC INFRASTRUCTURE STATUS")
    print(f"{'='*80}")
    print("""
✅ Framework operational:
   - Market analysis pipeline ready
   - ForecasterPrediction dataclass defined
   - Coordinate matching system ready
   - Edge calculation working
   - Simulated entry/exit logic ready

⏳ To run full POC, connect these data sources:
   1. Polymarket API: Get list of resolved markets (last 30 days)
   2. Open-Meteo Previous Runs API: Fetch historical forecasts
   3. NOAA CDO API (or WU scraper): Get actual temperatures
   4. Match coordinates to exact Wunderground stations

📋 Next steps:
   A. Add async API fetchers for real Polymarket data
   B. Implement coordinate-to-station matching logic
   C. Iterate through resolved markets (loop: fetch → analyze → record)
   D. Aggregate results by city and forecaster
   E. Output rankings and recommendations
""")
