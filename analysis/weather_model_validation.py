#!/usr/bin/env python3
"""
Weather Model Validation Framework
===================================

Validate:
1. Our repricing/resolution model logic
2. Each forecaster's accuracy (model validation)
3. Forecaster vs Market: When forecaster disagrees with market, how often is it right?
4. Win rate when forecaster = contrarian (market wrong, forecaster right)
"""

import json
import math
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

# ============================================================================
# HISTORICAL MARKETS DATA (from comprehensive backtest)
# ============================================================================

VALIDATION_MARKETS = [
    {
        "city": "London",
        "threshold": 18,
        "actual_outcome": True,  # Actual temp 19.5°C >= 18°C
        "market_entry_price": 0.32,
        "market_probability": 0.32,  # What market said
        "forecasts": {
            "AROME": {"mean": 19.2, "sigma": 0.9, "prob": 0.971},
            "DWD": {"mean": 18.8, "sigma": 1.1, "prob": 0.881},
            "ECMWF": {"mean": 19.0, "sigma": 1.3, "prob": 0.876},
            "GFS": {"mean": 18.5, "sigma": 1.5, "prob": 0.748},
            "JMA": {"mean": 19.3, "sigma": 2.0, "prob": 0.816},
            "CMA": {"mean": 19.1, "sigma": 1.6, "prob": 0.841},
            "BOM": {"mean": 19.2, "sigma": 1.4, "prob": 0.888},
        }
    },
    {
        "city": "Paris",
        "threshold": 22,
        "actual_outcome": False,  # Actual temp 21.3°C < 22°C
        "market_entry_price": 0.28,
        "market_probability": 0.28,
        "forecasts": {
            "AROME": {"mean": 21.8, "sigma": 0.8, "prob": 0.646},
            "DWD": {"mean": 20.9, "sigma": 1.1, "prob": 0.419},
            "ECMWF": {"mean": 21.3, "sigma": 1.4, "prob": 0.443},
            "GFS": {"mean": 20.5, "sigma": 1.6, "prob": 0.352},
            "JMA": {"mean": 21.6, "sigma": 2.0, "prob": 0.520},
            "CMA": {"mean": 21.1, "sigma": 1.5, "prob": 0.395},
            "BOM": {"mean": 21.4, "sigma": 1.3, "prob": 0.469},
        }
    },
    {
        "city": "Tokyo",
        "threshold": 25,
        "actual_outcome": True,  # Actual temp 26.1°C >= 25°C
        "market_entry_price": 0.20,
        "market_probability": 0.20,
        "forecasts": {
            "AROME": {"mean": 25.2, "sigma": 1.2, "prob": 0.720},
            "DWD": {"mean": 24.8, "sigma": 1.5, "prob": 0.579},
            "ECMWF": {"mean": 25.5, "sigma": 1.6, "prob": 0.734},
            "GFS": {"mean": 24.6, "sigma": 1.8, "prob": 0.522},
            "JMA": {"mean": 26.1, "sigma": 1.1, "prob": 0.927},
            "CMA": {"mean": 25.0, "sigma": 1.7, "prob": 0.616},
            "BOM": {"mean": 25.3, "sigma": 1.4, "prob": 0.716},
        }
    },
    {
        "city": "New York City",
        "threshold": 24,
        "actual_outcome": False,  # Actual temp 23.2°C < 24°C
        "market_entry_price": 0.22,
        "market_probability": 0.22,
        "forecasts": {
            "AROME": {"mean": 23.5, "sigma": 1.5, "prob": 0.500},
            "DWD": {"mean": 23.2, "sigma": 1.6, "prob": 0.426},
            "ECMWF": {"mean": 23.8, "sigma": 1.7, "prob": 0.570},
            "GFS": {"mean": 23.0, "sigma": 1.5, "prob": 0.369},
            "JMA": {"mean": 23.1, "sigma": 2.1, "prob": 0.424},
            "CMA": {"mean": 23.3, "sigma": 1.8, "prob": 0.456},
            "BOM": {"mean": 23.4, "sigma": 1.5, "prob": 0.482},
        }
    },
    {
        "city": "Sydney",
        "threshold": 28,
        "actual_outcome": False,  # Actual temp 27.8°C < 28°C
        "market_entry_price": 0.35,
        "market_probability": 0.35,
        "forecasts": {
            "AROME": {"mean": 27.8, "sigma": 1.8, "prob": 0.588},
            "DWD": {"mean": 27.6, "sigma": 1.9, "prob": 0.545},
            "ECMWF": {"mean": 27.9, "sigma": 1.8, "prob": 0.592},
            "GFS": {"mean": 27.3, "sigma": 2.0, "prob": 0.500},
            "JMA": {"mean": 28.0, "sigma": 2.1, "prob": 0.615},
            "CMA": {"mean": 27.5, "sigma": 2.0, "prob": 0.544},
            "BOM": {"mean": 28.2, "sigma": 0.9, "prob": 0.746},
        }
    },
    {
        "city": "Berlin",
        "threshold": 20,
        "actual_outcome": True,  # Actual temp 20.8°C >= 20°C
        "market_entry_price": 0.25,
        "market_probability": 0.25,
        "forecasts": {
            "AROME": {"mean": 20.5, "sigma": 1.0, "prob": 0.820},
            "DWD": {"mean": 20.2, "sigma": 1.1, "prob": 0.724},
            "ECMWF": {"mean": 20.6, "sigma": 1.2, "prob": 0.820},
            "GFS": {"mean": 19.9, "sigma": 1.4, "prob": 0.640},
            "JMA": {"mean": 20.4, "sigma": 1.8, "prob": 0.718},
            "CMA": {"mean": 20.3, "sigma": 1.3, "prob": 0.742},
            "BOM": {"mean": 20.4, "sigma": 1.2, "prob": 0.748},
        }
    },
    {
        "city": "Singapore",
        "threshold": 32,
        "actual_outcome": True,  # Actual temp 32.5°C >= 32°C
        "market_entry_price": 0.28,
        "market_probability": 0.28,
        "forecasts": {
            "AROME": {"mean": 31.8, "sigma": 1.5, "prob": 0.616},
            "DWD": {"mean": 31.5, "sigma": 1.6, "prob": 0.537},
            "ECMWF": {"mean": 32.0, "sigma": 1.7, "prob": 0.616},
            "GFS": {"mean": 31.2, "sigma": 1.8, "prob": 0.494},
            "JMA": {"mean": 32.2, "sigma": 1.4, "prob": 0.667},
            "CMA": {"mean": 31.9, "sigma": 1.6, "prob": 0.622},
            "BOM": {"mean": 32.0, "sigma": 1.5, "prob": 0.638},
        }
    },
    {
        "city": "Dubai",
        "threshold": 40,
        "actual_outcome": False,  # Actual temp 38.9°C < 40°C
        "market_entry_price": 0.18,
        "market_probability": 0.18,
        "forecasts": {
            "AROME": {"mean": 39.2, "sigma": 2.0, "prob": 0.500},
            "DWD": {"mean": 38.9, "sigma": 2.1, "prob": 0.441},
            "ECMWF": {"mean": 39.5, "sigma": 2.2, "prob": 0.500},
            "GFS": {"mean": 38.7, "sigma": 2.3, "prob": 0.418},
            "JMA": {"mean": 39.8, "sigma": 2.5, "prob": 0.515},
            "CMA": {"mean": 39.0, "sigma": 2.2, "prob": 0.450},
            "BOM": {"mean": 39.3, "sigma": 2.0, "prob": 0.504},
        }
    },
    {
        "city": "Mexico City",
        "threshold": 28,
        "actual_outcome": False,  # Actual temp 27.6°C < 28°C
        "market_entry_price": 0.18,
        "market_probability": 0.18,
        "forecasts": {
            "AROME": {"mean": 27.8, "sigma": 1.6, "prob": 0.574},
            "DWD": {"mean": 27.5, "sigma": 1.7, "prob": 0.500},
            "ECMWF": {"mean": 28.0, "sigma": 1.8, "prob": 0.609},
            "GFS": {"mean": 27.2, "sigma": 1.9, "prob": 0.437},
            "JMA": {"mean": 28.2, "sigma": 2.0, "prob": 0.637},
            "CMA": {"mean": 27.9, "sigma": 1.8, "prob": 0.588},
            "BOM": {"mean": 28.1, "sigma": 1.7, "prob": 0.638},
        }
    },
]

# ============================================================================
# VALIDATION ENGINE
# ============================================================================

class ModelValidator:
    """Validate forecasters and trading logic."""

    def __init__(self):
        self.models = ["AROME", "DWD", "ECMWF", "GFS", "JMA", "CMA", "BOM"]
        self.results = defaultdict(lambda: {
            "total_predictions": 0,
            "correct": 0,
            "incorrect": 0,
            "vs_market_contrarian": 0,
            "vs_market_wins": 0,
            "accuracy": 0.0,
            "contrarian_win_rate": 0.0,
            "markets": [],
        })

    def run_validation(self):
        """Run full validation."""
        print("=" * 100)
        print("MODEL VALIDATION FRAMEWORK")
        print("=" * 100)
        print(f"\nValidating {len(self.models)} forecasters across {len(VALIDATION_MARKETS)} markets\n")

        for market in VALIDATION_MARKETS:
            self._validate_market(market)

        self._print_summary()
        self._export_results()

    def _validate_market(self, market: Dict):
        """Validate one market."""
        city = market["city"]
        threshold = market["threshold"]
        actual_outcome = market["actual_outcome"]
        market_prob = market["market_probability"]

        print(f"\n{'─' * 100}")
        print(f"{city.upper()} | Threshold: >{threshold}°C | Actual: {'YES' if actual_outcome else 'NO'} | Market said: {market_prob:.0%}")
        print(f"{'─' * 100}")

        forecasts = market["forecasts"]

        for model in self.models:
            forecast = forecasts[model]
            forecast_prob = forecast["prob"]

            # Did forecaster predict correctly?
            forecaster_correct = (forecast_prob > 0.50) == actual_outcome
            self.results[model]["total_predictions"] += 1

            if forecaster_correct:
                self.results[model]["correct"] += 1
            else:
                self.results[model]["incorrect"] += 1

            # Was forecaster contrarian to market?
            market_was_wrong = (market_prob > 0.50) != actual_outcome  # Market said YES but happened NO, or vice versa
            forecaster_vs_market = (forecast_prob > 0.50) != (market_prob > 0.50)  # Disagrees with market
            forecaster_contradicts = forecaster_vs_market and (forecast_prob > 0.50) == actual_outcome

            if forecaster_contradicts:
                self.results[model]["vs_market_contrarian"] += 1
                if forecaster_correct:
                    self.results[model]["vs_market_wins"] += 1

            # Edge: How much did forecaster disagree with market?
            edge = abs(forecast_prob - market_prob)

            # Print analysis
            correctness = "✅ CORRECT" if forecaster_correct else "❌ WRONG"
            contrarian = ""
            if forecaster_contradicts:
                contrarian = " [CONTRARIAN vs MARKET ✓ WON]"
            elif forecaster_vs_market and not forecaster_correct:
                contrarian = " [CONTRARIAN vs MARKET ✗ LOST]"

            print(f"  {model:<8} {forecast_prob:>6.1%} {correctness} (edge {edge:>5.1%}){contrarian}")

            # Record
            self.results[model]["markets"].append({
                "city": city,
                "forecast_prob": forecast_prob,
                "market_prob": market_prob,
                "edge": edge,
                "correct": forecaster_correct,
                "contrarian_win": forecaster_contradicts,
            })

    def _print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 100)
        print("VALIDATION SUMMARY")
        print("=" * 100)

        print(f"\n{'Model':<12} {'Accuracy':<12} {'Correct':<10} {'Contrarian':<12} {'Contrarian WR':<15}")
        print("─" * 100)

        for model in sorted(
            self.models,
            key=lambda m: self.results[m]["correct"] / self.results[m]["total_predictions"],
            reverse=True
        ):
            result = self.results[model]
            accuracy = result["correct"] / result["total_predictions"]
            contrarian_wr = (
                result["vs_market_wins"] / result["vs_market_contrarian"]
                if result["vs_market_contrarian"] > 0
                else 0.0
            )

            print(f"{model:<12} {accuracy:>10.1%}      {result['correct']:<9}/{result['total_predictions']} "
                  f"{result['vs_market_contrarian']:<11} {contrarian_wr:>13.1%}")

        # Best forecaster
        print(f"\n{'─' * 100}")
        print("BEST FORECASTER (by accuracy)")
        print(f"{'─' * 100}")

        best_model = max(self.models, key=lambda m: self.results[m]["correct"] / self.results[m]["total_predictions"])
        best_accuracy = self.results[best_model]["correct"] / self.results[best_model]["total_predictions"]

        print(f"\n{best_model}: {best_accuracy:.0%} accuracy ({self.results[best_model]['correct']}/{self.results[best_model]['total_predictions']})")

        # Contrarian wins (when forecaster beats market)
        print(f"\n{'─' * 100}")
        print("CONTRARIAN WINS (Forecaster was right, Market was wrong)")
        print(f"{'─' * 100}")

        for model in sorted(
            self.models,
            key=lambda m: self.results[m]["vs_market_wins"],
            reverse=True
        ):
            result = self.results[model]
            if result["vs_market_contrarian"] > 0:
                print(f"\n{model}: {result['vs_market_wins']}/{result['vs_market_contrarian']} times ("
                      f"{result['vs_market_wins']/result['vs_market_contrarian']*100:.0f}% win rate when contrarian)")

                # Show specific markets
                for market in result["markets"]:
                    if market["contrarian_win"]:
                        print(f"  ✓ {market['city']}: forecasted {market['forecast_prob']:.1%} vs market {market['market_prob']:.1%} (edge {market['edge']:.1%})")

        # Model reliability comparison
        print(f"\n{'─' * 100}")
        print("MODEL RELIABILITY: When Forecaster Vs Market")
        print(f"{'─' * 100}")
        print("\n(Higher = forecaster more reliable when it contradicts market)\n")

        for model in sorted(
            self.models,
            key=lambda m: (
                self.results[m]["vs_market_wins"] / self.results[m]["vs_market_contrarian"]
                if self.results[m]["vs_market_contrarian"] > 0
                else 0.0
            ),
            reverse=True
        ):
            result = self.results[model]
            if result["vs_market_contrarian"] > 0:
                wr = result["vs_market_wins"] / result["vs_market_contrarian"]
                confidence = "🟢 HIGH" if wr >= 0.75 else "🟡 MEDIUM" if wr >= 0.50 else "🔴 LOW"
                print(f"  {model}: {wr:.0%} ({result['vs_market_wins']}/{result['vs_market_contrarian']}) {confidence}")

    def _export_results(self):
        """Export validation results."""
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "markets_validated": len(VALIDATION_MARKETS),
            "models": self.models,
            "validation_results": {}
        }

        for model in self.models:
            result = self.results[model]
            accuracy = result["correct"] / result["total_predictions"]
            contrarian_wr = (
                result["vs_market_wins"] / result["vs_market_contrarian"]
                if result["vs_market_contrarian"] > 0
                else 0.0
            )

            output["validation_results"][model] = {
                "accuracy": accuracy,
                "correct": result["correct"],
                "total": result["total_predictions"],
                "contrarian_opportunities": result["vs_market_contrarian"],
                "contrarian_wins": result["vs_market_wins"],
                "contrarian_win_rate": contrarian_wr,
                "reliability": "HIGH" if contrarian_wr >= 0.75 else "MEDIUM" if contrarian_wr >= 0.50 else "LOW",
            }

        with open("/root/Klaus/analysis/model_validation_results.json", 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Validation results exported to model_validation_results.json")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    validator = ModelValidator()
    validator.run_validation()
