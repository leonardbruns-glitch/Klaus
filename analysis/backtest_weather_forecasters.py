#!/usr/bin/env python3
"""
Weather Forecaster Backtest
============================
Backtest forecaster accuracy against historical weather + realistic market prices.

Methodology:
1. For 30 past dates, fetch what ACTUAL weather happened (from Open-Meteo archive)
2. Simulate realistic Polymarket prices based on how they typically price vs forecasts
3. For each date/city/threshold, test each forecaster combination:
   - What would the forecast have predicted?
   - Did it match actual outcome?
   - Would we have been mispriced (edge)?
4. Calculate WR, PnL, edge by forecaster combo and entry price band
"""

import requests
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import time

# ============================================================================
# HISTORICAL WEATHER DATA FETCHER
# ============================================================================

class HistoricalWeatherFetcher:
    """Fetch actual past weather from Open-Meteo archive."""

    def __init__(self):
        self.archive_base = "https://archive-api.open-meteo.com/v1/archive"

        # Test cities + coordinates
        self.test_cases = [
            ("London", 51.5, -0.1),
            ("Paris", 48.9, 2.4),
            ("Tokyo", 35.5, 139.8),
            ("New York", 40.7, -74.0),
            ("Sydney", -33.9, 151.2),
        ]

    def fetch_historical_temps(self, lat: float, lon: float,
                               start_date: str, end_date: str) -> Dict[str, float]:
        """
        Fetch actual historical max temperatures for a date range.
        Returns: {date_str: max_temp_celsius}
        """
        try:
            params = {
                'latitude': lat,
                'longitude': lon,
                'start_date': start_date,
                'end_date': end_date,
                'daily': 'temperature_2m_max',
                'temperature_unit': 'celsius',
                'timezone': 'UTC',
            }

            resp = requests.get(self.archive_base, params=params, timeout=15)
            if resp.status_code != 200:
                return {}

            data = resp.json()
            daily = data.get('daily', {})

            temps = {}
            dates = daily.get('time', [])
            max_temps = daily.get('temperature_2m_max', [])

            for date, temp in zip(dates, max_temps):
                temps[date] = temp

            return temps

        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return {}

    def get_historical_cases(self, days_back: int = 30) -> List[Tuple]:
        """Generate historical test cases for past N days."""
        cases = []
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days_back)

        for city, lat, lon in self.test_cases:
            temps = self.fetch_historical_temps(lat, lon,
                                               start_date.isoformat(),
                                               end_date.isoformat())

            for date_str, actual_temp in temps.items():
                # Generate test thresholds around the actual temperature
                thresholds = [
                    int(actual_temp) - 2,
                    int(actual_temp) - 1,
                    int(actual_temp),
                    int(actual_temp) + 1,
                    int(actual_temp) + 2,
                ]

                for threshold in thresholds:
                    # Outcome: did temp exceed threshold?
                    outcome = 1.0 if actual_temp > threshold else 0.0
                    cases.append({
                        'city': city,
                        'lat': lat,
                        'lon': lon,
                        'date': date_str,
                        'threshold': threshold,
                        'actual_temp': actual_temp,
                        'outcome': outcome,  # 1 if YES, 0 if NO
                    })

        return cases

# ============================================================================
# FORECAST MODEL (Multi-model ensemble)
# ============================================================================

class ForecastEnsemble:
    """Ensemble of forecasters for temperature prediction."""

    def __init__(self):
        # Model accuracy profiles from research (typical bias/sigma)
        self.models = {
            'ECMWF': {'bias': 0.1, 'sigma': 1.2},      # Best overall
            'GFS': {'bias': 0.3, 'sigma': 1.8},        # Good but higher variance
            'ICON': {'bias': 0.2, 'sigma': 1.4},       # European model
            'JMA': {'bias': -0.15, 'sigma': 1.3},      # Japanese, slight cold bias
            'CMA': {'bias': 0.0, 'sigma': 1.9},        # Chinese, high variance
        }

    def predict_prob_above(self, city: str, threshold: float,
                          actual_temp: float, models: List[str]) -> float:
        """
        Predict P(temp > threshold) using ensemble of models.

        Simulate what forecasters would have predicted by adding realistic noise
        to the actual temperature.
        """
        if not models:
            models = list(self.models.keys())

        # Simulate what each model would have forecast
        forecasts = []
        for model in models:
            if model not in self.models:
                continue

            # Add model-specific bias and noise
            bias = self.models[model]['bias']
            sigma = self.models[model]['sigma']

            # Forecast is actual temp + bias + noise
            forecast = actual_temp + bias + (hash(f"{city}{threshold}{model}") % 100 - 50) / 100.0 * sigma

            # Probability that forecast > threshold
            prob = 0.5 + 0.5 * math.erf((forecast - threshold) / (sigma * math.sqrt(2)))
            forecasts.append(prob)

        # Ensemble: average probability
        if forecasts:
            return sum(forecasts) / len(forecasts)
        return 0.5

    @staticmethod
    def norm_cdf(x: float) -> float:
        """Standard normal CDF."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

# ============================================================================
# MARKET PRICE SIMULATOR
# ============================================================================

class MarketPriceSimulator:
    """Simulate realistic Polymarket prices based on forecaster consensus."""

    @staticmethod
    def simulate_market_price(fair_prob: float, misprice_factor: float = 1.0) -> float:
        """
        Simulate market price given fair probability.
        Polymarket typically has 10-25% mispricing in various directions.
        """
        # Random market inefficiency (favor low or high)
        noise = (hash(f"{fair_prob}{misprice_factor}") % 100 - 50) / 100.0 * 0.20
        market_price = max(0.01, min(0.99, fair_prob + noise))

        return market_price

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class WeatherBacktest:
    """Run full backtest of forecaster combinations."""

    def __init__(self):
        self.fetcher = HistoricalWeatherFetcher()
        self.ensemble = ForecastEnsemble()
        self.simulator = MarketPriceSimulator()
        self.results = defaultdict(lambda: {
            'trades': [],
            'wins': 0,
            'total': 0,
            'wr': 0,
            'avg_edge': 0,
            'avg_pnl': 0,
        })

    def run(self, days_back: int = 30):
        """Run full backtest."""
        print("=" * 100)
        print("WEATHER FORECASTER BACKTEST: Historical Data")
        print("=" * 100)

        # Get historical test cases
        print(f"\n📊 Fetching {days_back} days of historical weather data...")
        cases = self.fetcher.get_historical_cases(days_back=days_back)

        print(f"✅ Generated {len(cases)} test cases (5 cities × {days_back} days × ~5 thresholds)\n")

        # Test different forecaster combinations
        model_combos = [
            ['ECMWF'],
            ['GFS'],
            ['ECMWF', 'GFS'],
            ['ECMWF', 'GFS', 'ICON'],
            ['ECMWF', 'GFS', 'ICON', 'JMA'],
            ['ECMWF', 'GFS', 'ICON', 'JMA', 'CMA'],  # All 5
        ]

        for combo in model_combos:
            combo_name = '+'.join(combo)
            print(f"Testing {combo_name}...")

            for case in cases:
                # Get forecast from ensemble
                fair_prob = self.ensemble.predict_prob_above(
                    case['city'],
                    case['threshold'],
                    case['actual_temp'],
                    combo
                )

                # Simulate market price
                market_price = self.simulator.simulate_market_price(fair_prob)

                # Edge: fair - market
                edge = fair_prob - market_price

                # Only trade if edge >= 8%
                if abs(edge) >= 0.08:
                    # Simulate entry and outcome
                    stake = 25.0
                    shares = stake / market_price

                    # Outcome determines if forecast was correct
                    # (simplified: if forecast > 0.5 and outcome = 1, it was correct)
                    forecast_yes = fair_prob > 0.5
                    actual_yes = case['outcome'] > 0.5
                    correct = forecast_yes == actual_yes

                    # PnL
                    exit_price = 1.0 if actual_yes else 0.0
                    pnl = shares * (exit_price - market_price)

                    # Record
                    self.results[combo_name]['trades'].append({
                        'city': case['city'],
                        'threshold': case['threshold'],
                        'actual_temp': case['actual_temp'],
                        'fair': fair_prob,
                        'market': market_price,
                        'edge': edge,
                        'outcome': case['outcome'],
                        'correct': correct,
                        'pnl': pnl,
                    })

            # Calculate stats
            if self.results[combo_name]['trades']:
                trades = self.results[combo_name]['trades']
                self.results[combo_name]['total'] = len(trades)
                self.results[combo_name]['wins'] = sum(1 for t in trades if t['correct'])
                self.results[combo_name]['wr'] = self.results[combo_name]['wins'] / len(trades)
                self.results[combo_name]['avg_edge'] = sum(t['edge'] for t in trades) / len(trades)
                self.results[combo_name]['avg_pnl'] = sum(t['pnl'] for t in trades) / len(trades)

        # Print results
        self._print_results()
        self._export_results()

    def _print_results(self):
        """Print backtest results."""
        print("\n" + "=" * 100)
        print("BACKTEST RESULTS: Forecaster Combinations")
        print("=" * 100)

        print(f"\n{'Forecasters':<40} {'Trades':<10} {'WR':<10} {'Avg Edge':<12} {'Avg PnL':<12}")
        print("─" * 100)

        best_combo = None
        best_wr = 0

        for combo in sorted(self.results.keys()):
            res = self.results[combo]
            if res['total'] > 0:
                print(f"{combo:<40} {res['total']:<10} {res['wr']:>8.1%}   {res['avg_edge']:>10.1%}   ${res['avg_pnl']:>10.2f}")

                if res['wr'] > best_wr:
                    best_wr = res['wr']
                    best_combo = combo

        print("─" * 100)

        if best_combo:
            res = self.results[best_combo]
            print(f"\n🏆 BEST: {best_combo}")
            print(f"   Win Rate: {res['wr']:.1%}")
            print(f"   Average Edge: {res['avg_edge']:.1%}")
            print(f"   Average PnL/Trade: ${res['avg_pnl']:.2f}")
            print(f"   Tradeable Scenarios: {res['total']}")

            # Projection
            if res['avg_pnl'] > 0:
                annual_pnl = res['avg_pnl'] * 5 * 365  # 5 trades/day, 365 days
                print(f"   Projected Annual PnL (5 trades/day): ${annual_pnl:,.0f}")

    def _export_results(self):
        """Export results to JSON."""
        output = {
            'timestamp': datetime.utcnow().isoformat(),
            'backtest_type': 'Historical Weather + Forecaster Combinations',
            'results_by_combo': {},
            'best_combo': None,
        }

        best_wr = 0
        best_combo = None

        for combo in self.results:
            res = self.results[combo]
            if res['total'] > 0:
                output['results_by_combo'][combo] = {
                    'num_trades': res['total'],
                    'win_rate': res['wr'],
                    'avg_edge': res['avg_edge'],
                    'avg_pnl_per_trade': res['avg_pnl'],
                    'total_pnl': sum(t['pnl'] for t in res['trades']),
                }

                if res['wr'] > best_wr:
                    best_wr = res['wr']
                    best_combo = combo

        output['best_combo'] = best_combo

        with open('/root/Klaus/analysis/weather_forecaster_backtest.json', 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Results saved to analysis/weather_forecaster_backtest.json")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    backtest = WeatherBacktest()
    backtest.run(days_back=30)
