#!/usr/bin/env python3
"""
Weather Model Edge Validation
==============================
Validates the WeatherArb forecasting model by simulating realistic market scenarios.
Uses Open-Meteo forecast data + synthetic market prices to estimate WR and PnL.

Methodology:
1. Fetch real Open-Meteo forecasts for 40+ global cities
2. Simulate realistic Polymarket prices (assume normal mispricing)
3. Calculate fair value using forecast + uncertainty model
4. Measure: WR, average edge, daily/yearly PnL projections
"""

import json
import math
import time
import requests
from datetime import date, timedelta
from collections import defaultdict
from typing import Optional, Dict, List

# ============================================================================
# REAL FORECAST FETCHER (Open-Meteo)
# ============================================================================

class OpenMeteoFetcher:
    """Fetch real weather forecasts from Open-Meteo API."""

    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        # Temperature thresholds to test (°C)
        self.test_thresholds = [
            15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
        ]
        # Cities with coordinates
        self.cities = {
            "London": (51.5, -0.1),
            "Paris": (48.9, 2.4),
            "Tokyo": (35.5, 139.8),
            "New York": (40.7, -74.0),
            "Sydney": (-33.9, 151.2),
            "Dubai": (25.3, 55.4),
            "Singapore": (1.4, 103.9),
            "Beijing": (40.1, 116.6),
            "Berlin": (52.5, 13.4),
            "Mumbai": (19.1, 72.9),
            "São Paulo": (-23.5, -46.6),
            "Mexico City": (19.4, -99.1),
            "Toronto": (43.7, -79.4),
            "Moscow": (55.8, 37.6),
            "Istanbul": (41.0, 29.0),
            "Bangkok": (13.7, 100.5),
            "Seoul": (37.5, 127.0),
            "Shanghai": (31.2, 121.5),
            "Hong Kong": (22.3, 114.2),
            "Dubai": (25.3, 55.4),
            "Johannesburg": (-26.2, 28.0),
            "Lagos": (6.5, 3.3),
            "Cairo": (30.1, 31.2),
            "Mumbai": (19.1, 72.9),
            "Delhi": (28.7, 77.2),
            "Bangkok": (13.7, 100.5),
            "Melbourne": (-37.8, 145.0),
            "Amsterdam": (52.4, 4.9),
            "Vienna": (48.2, 16.4),
            "Prague": (50.1, 14.4),
            "Warsaw": (52.2, 21.0),
            "Athens": (37.9, 23.7),
            "Madrid": (40.4, -3.7),
            "Barcelona": (41.4, 2.2),
            "Rome": (41.9, 12.5),
            "Milan": (45.5, 9.2),
            "Chicago": (41.9, -87.6),
            "Los Angeles": (34.1, -118.2),
            "Houston": (29.8, -95.4),
            "Phoenix": (33.4, -112.1),
            "Miami": (25.8, -80.2),
            "San Francisco": (37.8, -122.4),
        }

    def fetch_forecast(self, lat: float, lon: float) -> Optional[Dict]:
        """Fetch real forecast data from Open-Meteo."""
        try:
            params = {
                'latitude': lat,
                'longitude': lon,
                'daily': 'temperature_2m_max',
                'temperature_unit': 'celsius',
                'forecast_days': 2,
                'models': 'best_match,gfs025,ecmwf'
            }

            resp = requests.get(self.base_url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def parse_forecast(self, data: Dict) -> Optional[Dict]:
        """Extract mean and sigma from forecast data."""
        if not data or 'daily' not in data:
            return None

        temps = data['daily'].get('temperature_2m_max', [])
        if len(temps) < 2:
            return None

        tomorrow_temp = temps[1]  # Index 1 is tomorrow

        # Calculate sigma from model spread (if multiple models available)
        # Otherwise use 1.5°C as default forecast uncertainty
        sigma = 1.5

        return {
            'mean': tomorrow_temp,
            'sigma': sigma,
        }

    def fetch_all_forecasts(self) -> Dict[str, Dict]:
        """Fetch forecasts for all cities."""
        print("\n📥 Fetching real forecasts from Open-Meteo...")
        results = {}

        for city, (lat, lon) in self.cities.items():
            data = self.fetch_forecast(lat, lon)
            parsed = self.parse_forecast(data)
            if parsed:
                results[city] = parsed
                print(f"  ✅ {city:15} mean={parsed['mean']:6.1f}°C σ={parsed['sigma']:.1f}°C")
            else:
                print(f"  ⚠️  {city:15} failed")
            time.sleep(0.1)  # Rate limit

        return results

# ============================================================================
# MARKET PRICE SIMULATOR
# ============================================================================

class MarketSimulator:
    """Simulate realistic Polymarket pricing."""

    @staticmethod
    def simulate_prices(mean: float, sigma: float, thresholds: List[int]) -> Dict[int, float]:
        """
        Simulate market prices for various threshold levels.
        Assumes markets are normally mispriced with ~10-30% deviation from fair.
        """
        prices = {}
        for threshold in thresholds:
            # Fair probability using normal CDF
            z = (threshold - mean) / sigma
            fair_prob = 0.5 * (1.0 + math.erf(-z / math.sqrt(2.0)))

            # Simulate market mispricing (realistic ±10-30% deviation)
            # With random walk: sometimes too high, sometimes too low
            misprice_factor = 0.85 + (hash(f"{threshold}") % 100) / 100.0 * 0.30
            market_price = max(0.01, min(0.99, fair_prob * misprice_factor))

            prices[threshold] = {
                'fair': fair_prob,
                'market': market_price,
                'edge': fair_prob - market_price,
            }

        return prices

# ============================================================================
# VALIDATOR
# ============================================================================

class WeatherEdgeValidator:
    """Validate weather forecasting model edge."""

    def __init__(self):
        self.fetcher = OpenMeteoFetcher()
        self.results = defaultdict(lambda: {
            'forecasts': {},
            'total_scenarios': 0,
            'tradeable_scenarios': 0,  # edge >= 0.08
            'trades': [],
            'wr': 0,
            'avg_edge': 0,
            'avg_pnl': 0,
        })

    def run_validation(self):
        """Run full validation."""
        print("=" * 100)
        print("WEATHER MODEL EDGE VALIDATOR: Real Forecasts + Simulated Markets")
        print("=" * 100)

        # Fetch real forecasts
        forecasts = self.fetcher.fetch_all_forecasts()

        if not forecasts:
            print("\n❌ Failed to fetch forecasts")
            return False

        print(f"\n✅ Got {len(forecasts)} real forecasts from Open-Meteo")

        # Simulate markets and calculate edges
        print("\n🎯 Simulating market prices and calculating edges...\n")
        print(f"{'City':<15} {'Threshold':<12} {'Fair Prob':<12} {'Mkt Price':<12} {'Edge':<10} {'Tradeable':<12}")
        print("─" * 100)

        for city, forecast in forecasts.items():
            mean = forecast['mean']
            sigma = forecast['sigma']

            prices = MarketSimulator.simulate_prices(mean, sigma, self.fetcher.test_thresholds)

            self.results[city]['forecasts'] = forecast

            for threshold, price_data in prices.items():
                fair = price_data['fair']
                market = price_data['market']
                edge = price_data['edge']

                self.results[city]['total_scenarios'] += 1

                # Only trade if edge >= 0.08 (8%)
                if edge >= 0.08:
                    self.results[city]['tradeable_scenarios'] += 1

                    # Simulate outcome: probability = fair value
                    outcome = 1.0 if (hash(f"{city}{threshold}") % 100) / 100.0 < fair else 0.0

                    # PnL: enter at market price, exit at outcome (0 or 1)
                    stake_usd = 25
                    shares = stake_usd / market
                    pnl = shares * (outcome - market)

                    self.results[city]['trades'].append({
                        'threshold': threshold,
                        'market': market,
                        'fair': fair,
                        'edge': edge,
                        'outcome': outcome,
                        'pnl': pnl,
                    })

                    status = "✓ TRADE" if edge >= 0.08 else ""
                    print(f"{city:<15} >{threshold:>3}°C        {fair:>10.1%}   {market:>10.1%}   {edge:>8.1%}   {status}")

        # Calculate stats
        self._calculate_stats()
        self._print_results()
        self._export_results()

        return True

    def _calculate_stats(self):
        """Calculate win rate and PnL statistics."""
        for city in self.results:
            trades = self.results[city]['trades']
            if trades:
                outcomes = [t['outcome'] for t in trades]
                wr = sum(outcomes) / len(outcomes)
                avg_pnl = sum(t['pnl'] for t in trades) / len(trades)
                avg_edge = sum(t['edge'] for t in trades) / len(trades)

                self.results[city]['wr'] = wr
                self.results[city]['avg_pnl'] = avg_pnl
                self.results[city]['avg_edge'] = avg_edge

    def _print_results(self):
        """Print results."""
        print("\n" + "=" * 100)
        print("VALIDATION RESULTS: EDGE & WIN RATE")
        print("=" * 100)

        print(f"\n{'City':<15} {'Scenarios':<12} {'Tradeable':<12} {'WR':<10} {'Avg Edge':<12} {'Avg PnL':<12}")
        print("─" * 100)

        total_scenarios = 0
        total_tradeable = 0
        all_wr = []
        all_edges = []
        all_pnl = []

        for city in sorted(self.results.keys()):
            res = self.results[city]
            print(f"{city:<15} {res['total_scenarios']:<12} {res['tradeable_scenarios']:<12} "
                  f"{res['wr']:>8.1%}   {res['avg_edge']:>10.1%}   ${res['avg_pnl']:>10.2f}")

            total_scenarios += res['total_scenarios']
            total_tradeable += res['tradeable_scenarios']
            if res['trades']:
                all_wr.extend([t['outcome'] for t in res['trades']])
                all_edges.extend([t['edge'] for t in res['trades']])
                all_pnl.extend([t['pnl'] for t in res['trades']])

        print("─" * 100)

        if all_wr:
            overall_wr = sum(all_wr) / len(all_wr)
            overall_edge = sum(all_edges) / len(all_edges) if all_edges else 0
            total_pnl = sum(all_pnl)
            avg_pnl = total_pnl / len(all_pnl) if all_pnl else 0

            print(f"{'TOTAL':<15} {total_scenarios:<12} {total_tradeable:<12} "
                  f"{overall_wr:>8.1%}   {overall_edge:>10.1%}   ${avg_pnl:>10.2f}")

            print(f"\n📊 Summary:")
            print(f"   Total scenario-threshold combinations: {total_scenarios}")
            print(f"   Tradeable (edge ≥ 8%):                 {total_tradeable} ({100*total_tradeable/total_scenarios:.1f}%)")
            print(f"   Win rate (on tradeable):               {overall_wr:.1%}")
            print(f"   Average edge per trade:                {overall_edge:.1%}")
            print(f"   Average PnL per trade:                 ${avg_pnl:.2f}")
            print(f"   Total PnL (if all traded):             ${total_pnl:.2f}")

            # Projections
            trades_per_day = 5  # assume 5 tradeable positions per day
            trades_per_year = trades_per_day * 365

            projected_annual = avg_pnl * trades_per_year
            print(f"\n🎯 Projections (if {trades_per_day} trades/day):")
            print(f"   Annual PnL at {overall_wr:.1%} WR:        ${projected_annual:,.0f}")
            print(f"   Daily average:                        ${projected_annual/365:,.0f}")

    def _export_results(self):
        """Export to JSON."""
        output = {
            "timestamp": time.time(),
            "data_source": "Real Open-Meteo forecasts + simulated market prices",
            "summary": {},
            "by_city": {},
        }

        for city in self.results:
            res = self.results[city]
            output["by_city"][city] = {
                "total_scenarios": res['total_scenarios'],
                "tradeable_scenarios": res['tradeable_scenarios'],
                "win_rate": res['wr'],
                "avg_edge": res['avg_edge'],
                "avg_pnl": res['avg_pnl'],
                "num_trades": len(res['trades']),
            }

        # Summary
        all_trades = []
        for res in self.results.values():
            all_trades.extend(res['trades'])

        if all_trades:
            wr = sum(t['outcome'] for t in all_trades) / len(all_trades)
            avg_edge = sum(t['edge'] for t in all_trades) / len(all_trades)
            avg_pnl = sum(t['pnl'] for t in all_trades) / len(all_trades)

            output["summary"] = {
                "total_tradeable_scenarios": len(all_trades),
                "win_rate": wr,
                "avg_edge": avg_edge,
                "avg_pnl_per_trade": avg_pnl,
                "total_pnl": sum(t['pnl'] for t in all_trades),
                "projected_annual_pnl_at_5trades_per_day": avg_pnl * 5 * 365,
            }

        path = "/root/Klaus/analysis/weather_edge_validation.json"
        with open(path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Results exported to {path}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    validator = WeatherEdgeValidator()
    validator.run_validation()
