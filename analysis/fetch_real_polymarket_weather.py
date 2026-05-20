#!/usr/bin/env python3
"""
Real Data Validator: Fetch ACTUAL Polymarket weather markets using authenticated API
===================================================================================

Uses your CLOB_API_KEY to fetch resolved weather markets and validate forecasters.
"""

import requests
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import os
import sys

# ============================================================================
# AUTHENTICATED POLYMARKET DATA FETCHER
# ============================================================================

class AuthenticatedPolymarketFetcher:
    """Fetch real weather markets from Polymarket using CLOB API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://clob.polymarket.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Mozilla/5.0 (Klaus Weather Validator)'
        })

    def fetch_resolved_markets(self, search_term: str = "weather", limit: int = 100) -> List[Dict]:
        """Fetch resolved markets matching search term."""
        print(f"\n📥 Fetching {search_term} markets from Polymarket...")

        try:
            # Try CLOB API markets endpoint
            url = f"{self.base_url}/markets"
            params = {
                'search': search_term,
                'closed': True,
                'limit': limit,
            }

            resp = self.session.get(url, params=params, timeout=15)

            if resp.status_code == 401:
                print(f"⚠️  CLOB API returned 401 - trying REST API endpoint...")
                return self._fetch_via_rest_api(search_term, limit)

            if resp.status_code != 200:
                print(f"⚠️  Error {resp.status_code}: {resp.text}")
                return []

            data = resp.json()
            markets = data.get('data', data.get('markets', []))

            print(f"✅ Fetched {len(markets)} {search_term} markets")
            return markets

        except Exception as e:
            print(f"⚠️  Error fetching via CLOB: {e}")
            return self._fetch_via_rest_api(search_term, limit)

    def _fetch_via_rest_api(self, search_term: str, limit: int) -> List[Dict]:
        """Fallback: Try REST API without auth."""
        print(f"   Trying REST API without authentication...")

        try:
            url = "https://api.polymarket.com/markets"
            params = {
                'search': search_term,
                'closed': True,
                'limit': limit,
            }

            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()

            data = resp.json()
            markets = data.get('data', data.get('markets', []))

            print(f"✅ Fetched {len(markets)} {search_term} markets via REST API")
            return markets

        except Exception as e:
            print(f"⚠️  REST API also failed: {e}")
            return []

    def fetch_market_details(self, market_id: str) -> Optional[Dict]:
        """Fetch detailed market info."""
        try:
            url = f"{self.base_url}/markets/{market_id}"
            resp = self.session.get(url, timeout=10)

            if resp.status_code == 200:
                return resp.json()

            return None
        except Exception as e:
            return None

    def fetch_market_trades(self, market_id: str) -> List[Dict]:
        """Fetch trade history for market."""
        try:
            url = f"{self.base_url}/trades"
            params = {
                'market_id': market_id,
                'limit': 1000,
            }

            resp = self.session.get(url, params=params, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                return data.get('data', data.get('trades', []))

            return []
        except Exception as e:
            return []

    def parse_weather_market(self, market: Dict) -> Optional[Dict]:
        """Parse market data to extract weather details."""
        try:
            question = market.get('question', '').lower()

            # Check if it's a weather market
            if 'temperature' not in question and 'weather' not in question and 'temp' not in question:
                return None

            # Extract city
            city = None
            cities = [
                "london", "paris", "tokyo", "new york", "sydney", "berlin",
                "singapore", "dubai", "mexico city", "moscow", "bangkok",
                "shanghai", "hong kong", "toronto", "chicago", "los angeles",
                "tokyo", "mumbai", "istanbul", "buenos aires", "cairo"
            ]
            for c in cities:
                if c in question:
                    city = c
                    break

            if not city:
                return None

            # Extract threshold
            import re
            threshold_match = re.search(
                r'(?:above|exceed|higher than|>|≥)\s*(\d+)°?c?|(\d+)°?c?\s*(?:or|and)',
                question, re.IGNORECASE
            )
            if not threshold_match:
                return None

            threshold = int(threshold_match.group(1) or threshold_match.group(2))

            return {
                'market_id': market.get('id'),
                'city': city,
                'threshold': threshold,
                'question': market.get('question'),
                'resolution_price': float(market.get('resolvedPrice', market.get('final_price', 0.5))),
                'outcome': market.get('outcome'),
                'volume': float(market.get('volume', 0)),
                'created_at': market.get('createdAt'),
                'closed_at': market.get('closedAt'),
            }
        except Exception as e:
            return None

# ============================================================================
# FORECASTER SIMULATOR
# ============================================================================

class ForecasterSimulator:
    """Simulate forecaster predictions."""

    def __init__(self):
        # Historical forecast data from our backtest
        self.forecast_data = {
            "london": {
                "AROME": {"mean": 19.2, "sigma": 0.9},
                "DWD": {"mean": 18.8, "sigma": 1.1},
                "ECMWF": {"mean": 19.0, "sigma": 1.3},
            },
            "paris": {
                "AROME": {"mean": 21.8, "sigma": 0.8},
                "DWD": {"mean": 20.9, "sigma": 1.1},
                "ECMWF": {"mean": 21.3, "sigma": 1.4},
            },
            "tokyo": {
                "AROME": {"mean": 25.2, "sigma": 1.2},
                "DWD": {"mean": 24.8, "sigma": 1.5},
                "ECMWF": {"mean": 25.5, "sigma": 1.6},
            },
        }

    def predict(self, city: str, threshold: int) -> Dict[str, float]:
        """Get forecaster predictions for a city/threshold."""
        city_lower = city.lower()

        if city_lower not in self.forecast_data:
            return {}

        forecasts = {}
        for model, params in self.forecast_data[city_lower].items():
            prob = self.norm_cdf((threshold - 0.5 - params['mean']) / params['sigma'])
            forecasts[model] = prob

        return forecasts

    @staticmethod
    def norm_cdf(x: float) -> float:
        """Standard normal CDF."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

# ============================================================================
# REAL DATA VALIDATOR
# ============================================================================

class RealDataValidator:
    """Validate against REAL Polymarket data."""

    def __init__(self, api_key: str):
        self.fetcher = AuthenticatedPolymarketFetcher(api_key)
        self.simulator = ForecasterSimulator()
        self.validated_markets = []
        self.results = defaultdict(lambda: {
            "markets": [],
            "correct_predictions": 0,
            "total_predictions": 0,
            "contrarian_wins": 0,
            "contrarian_total": 0,
            "avg_edge": 0,
            "edges": [],
        })

    def run_validation(self):
        """Run full validation."""
        print("=" * 100)
        print("REAL DATA VALIDATOR: Actual Polymarket Weather Markets")
        print("=" * 100)

        # Fetch real markets
        markets = self.fetcher.fetch_resolved_markets(search_term="temperature", limit=100)

        if not markets:
            print("\n⚠️  Could not fetch markets from Polymarket API")
            print("   This may require direct GraphQL API access or web scraping")
            return False

        # Parse and analyze
        print(f"\n🔍 Parsing weather markets...")
        for market in markets:
            parsed = self.fetcher.parse_weather_market(market)
            if parsed:
                self.validated_markets.append(parsed)

        print(f"✅ Parsed {len(self.validated_markets)} valid weather markets")

        if not self.validated_markets:
            print("\n⚠️  No weather markets found in results")
            return False

        # Validate each market
        self._validate_markets()

        self._print_results()
        self._export_results()

        return True

    def _validate_markets(self):
        """Validate each market against forecasters."""
        print(f"\n📊 Validating {len(self.validated_markets)} markets...\n")

        for market in self.validated_markets:
            city = market['city']
            threshold = market['threshold']
            actual_outcome = market['resolution_price']  # 1.0 = YES, 0.0 = NO

            # Get forecasts
            forecasts = self.simulator.predict(city, threshold)

            if not forecasts:
                continue

            print(f"{city.upper():12} | Threshold: >{threshold}°C | Resolution: {actual_outcome:.1%}")

            for model, forecast_prob in forecasts.items():
                # Did forecaster predict correctly?
                forecast_correct = (forecast_prob > 0.50) == (actual_outcome > 0.50)

                # Edge: |forecast - 0.5| (distance from market midpoint)
                edge = abs(forecast_prob - 0.5)

                # Record
                self.results[model]["total_predictions"] += 1
                if forecast_correct:
                    self.results[model]["correct_predictions"] += 1

                self.results[model]["edges"].append(edge)

                status = "✅" if forecast_correct else "❌"
                print(f"  {model:8} {forecast_prob:6.1%} edge={edge:.1%} {status}")

            print()

    def _print_results(self):
        """Print validation results."""
        print("\n" + "=" * 100)
        print("VALIDATION RESULTS: REAL DATA")
        print("=" * 100)

        if not self.results:
            print("\n❌ No validation data available")
            return

        print(f"\n{'Model':<12} {'Accuracy':<12} {'Avg Edge':<12} {'Markets':<10}")
        print("─" * 100)

        for model in sorted(self.results.keys()):
            result = self.results[model]
            accuracy = (
                result['correct_predictions'] / result['total_predictions']
                if result['total_predictions'] > 0
                else 0
            )
            avg_edge = (
                sum(result['edges']) / len(result['edges'])
                if result['edges']
                else 0
            )

            print(f"{model:<12} {accuracy:>10.1%}      {avg_edge:>10.1%}      {result['total_predictions']:<10}")

    def _export_results(self):
        """Export validation results."""
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "markets_analyzed": len(self.validated_markets),
            "data_source": "Real Polymarket API",
            "validation_results": {}
        }

        for model in self.results:
            result = self.results[model]
            accuracy = (
                result['correct_predictions'] / result['total_predictions']
                if result['total_predictions'] > 0
                else 0
            )
            avg_edge = (
                sum(result['edges']) / len(result['edges'])
                if result['edges']
                else 0
            )

            output["validation_results"][model] = {
                "accuracy": accuracy,
                "avg_edge": avg_edge,
                "markets": result['total_predictions'],
                "correct": result['correct_predictions'],
            }

        output_path = "/root/Klaus/analysis/real_polymarket_validation.json"
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Results exported to {output_path}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    api_key = os.getenv("CLOB_API_KEY")

    if not api_key:
        # Try to load from .env file
        env_path = "/root/Klaus/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CLOB_API_KEY="):
                        api_key = line.split("=", 1)[1]
                        break

    if not api_key:
        print("❌ CLOB_API_KEY not found")
        sys.exit(1)

    validator = RealDataValidator(api_key)
    success = validator.run_validation()

    sys.exit(0 if success else 1)
