#!/usr/bin/env python3
"""
Weather Strategy Comparison: Temporary Repricing vs Resolution Betting
======================================================================

Two strategies for weather markets:
- Strategy A: Buy mispriced, exit at fair value (temporary repricing)
- Strategy B: Buy mispriced, hold to resolution (forecaster accuracy bet)

Analysis compares both approaches across 9 real market scenarios.
"""

import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
from collections import defaultdict

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class StrategyResult:
    """Result of one strategy execution."""
    strategy_name: str  # "Repricing" or "Resolution"
    city: str
    entry_price: float  # What we paid
    exit_price: float  # What we got (or resolution)
    shares: float  # How many YES tokens we bought
    pnl: float  # Profit/loss in dollars
    roi: float  # Return on investment %
    win: bool  # Did we make money?
    thesis: str  # Why we entered

# ============================================================================
# MARKET DATA (from Phase 4)
# ============================================================================

MARKETS = [
    {
        "city": "London",
        "date": "2026-05-18",
        "outcome_threshold": 18,
        "actual_temp": 19.5,
        "poly_entry_price": 0.40,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 19.2, "sigma": 0.9},
            "ECMWF": {"mean": 19.0, "sigma": 1.3},
            "JMA": {"mean": 19.3, "sigma": 2.0},
        }
    },
    {
        "city": "Paris",
        "date": "2026-05-19",
        "outcome_threshold": 22,
        "actual_temp": 21.3,
        "poly_entry_price": 0.40,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 21.8, "sigma": 0.8},
            "ECMWF": {"mean": 21.3, "sigma": 1.4},
            "JMA": {"mean": 21.6, "sigma": 2.0},
        }
    },
    {
        "city": "Tokyo",
        "date": "2026-05-18",
        "outcome_threshold": 25,
        "actual_temp": 26.1,
        "poly_entry_price": 0.35,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 25.2, "sigma": 1.2},
            "ECMWF": {"mean": 25.5, "sigma": 1.6},
            "JMA": {"mean": 26.1, "sigma": 1.1},
        }
    },
    {
        "city": "New York City",
        "date": "2026-05-20",
        "outcome_threshold": 24,
        "actual_temp": 23.2,
        "poly_entry_price": 0.38,
        "poly_resolution_price": 0.0,
        "forecasts": {
            "AROME": {"mean": 23.5, "sigma": 1.5},
            "ECMWF": {"mean": 23.8, "sigma": 1.7},
            "JMA": {"mean": 23.1, "sigma": 2.1},
        }
    },
    {
        "city": "Sydney",
        "date": "2026-05-16",
        "outcome_threshold": 28,
        "actual_temp": 27.8,
        "poly_entry_price": 0.45,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 27.8, "sigma": 1.8},
            "ECMWF": {"mean": 27.9, "sigma": 1.8},
            "JMA": {"mean": 28.0, "sigma": 2.1},
        }
    },
    {
        "city": "Berlin",
        "date": "2026-05-17",
        "outcome_threshold": 20,
        "actual_temp": 20.8,
        "poly_entry_price": 0.42,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 20.5, "sigma": 1.0},
            "ECMWF": {"mean": 20.6, "sigma": 1.2},
            "JMA": {"mean": 20.4, "sigma": 1.8},
        }
    },
    {
        "city": "Singapore",
        "date": "2026-05-21",
        "outcome_threshold": 32,
        "actual_temp": 32.5,
        "poly_entry_price": 0.41,
        "poly_resolution_price": 1.0,
        "forecasts": {
            "AROME": {"mean": 31.8, "sigma": 1.5},
            "ECMWF": {"mean": 32.0, "sigma": 1.7},
            "JMA": {"mean": 32.2, "sigma": 1.4},
        }
    },
    {
        "city": "Dubai",
        "date": "2026-05-22",
        "outcome_threshold": 40,
        "actual_temp": 38.9,
        "poly_entry_price": 0.35,
        "poly_resolution_price": 0.0,
        "forecasts": {
            "AROME": {"mean": 39.2, "sigma": 2.0},
            "ECMWF": {"mean": 39.5, "sigma": 2.2},
            "JMA": {"mean": 39.8, "sigma": 2.5},
        }
    },
    {
        "city": "Mexico City",
        "date": "2026-05-23",
        "outcome_threshold": 28,
        "actual_temp": 27.6,
        "poly_entry_price": 0.40,
        "poly_resolution_price": 0.0,
        "forecasts": {
            "AROME": {"mean": 27.8, "sigma": 1.6},
            "ECMWF": {"mean": 28.0, "sigma": 1.8},
            "JMA": {"mean": 28.2, "sigma": 2.0},
        }
    },
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def outcome_prob(forecast_mean: float, threshold: float, sigma: float) -> float:
    """P(temp >= threshold) under Normal(mean, sigma)."""
    return 1.0 - norm_cdf((threshold - 0.5 - forecast_mean) / sigma)

def calculate_fair_value(forecast_mean: float, threshold: float, sigma: float) -> float:
    """Calculate fair probability based on forecast."""
    return outcome_prob(forecast_mean, threshold, sigma)

# ============================================================================
# STRATEGY A: TEMPORARY REPRICING
# ============================================================================

class RepricingStrategy:
    """
    Strategy A: Buy when mispriced, exit when market reprices to fair value.

    Assumes:
    - We identify mispricing (market_price << fair_value)
    - We buy at entry_price
    - Market gradually reprices as other traders notice
    - We exit at fair_value (or close to it)
    """

    @staticmethod
    def analyze_market(market: Dict, best_model: str = "ECMWF") -> Tuple[float, bool, str]:
        """
        Analyze if market is mispriced.

        Returns: (fair_value, is_mispriced, thesis)
        """
        forecast = market["forecasts"][best_model]
        threshold = market["outcome_threshold"]
        entry_price = market["poly_entry_price"]

        fair_value = calculate_fair_value(
            forecast["mean"],
            threshold,
            forecast["sigma"]
        )

        is_mispriced = (fair_value > entry_price + 0.08)  # >8% mispricing threshold
        thesis = f"{best_model}: P(T>={threshold}°C)={fair_value:.3f} vs market {entry_price:.3f}"

        return fair_value, is_mispriced, thesis

    @staticmethod
    def simulate_exit(entry_price: float, fair_value: float, stake: float = 100) -> StrategyResult:
        """
        Simulate exit at fair value (or close to it due to liquidity).

        Assumes: We can exit at 90-95% of fair value due to slippage.
        """
        # Assume we get 90% of fair value due to market impact
        exit_price = fair_value * 0.90

        # Calculate PnL
        shares = stake / entry_price  # How many YES we bought
        cost = stake
        revenue = shares * exit_price
        pnl = revenue - cost
        roi = (pnl / cost) * 100

        return {
            "entry": entry_price,
            "exit": exit_price,
            "fair": fair_value,
            "shares": shares,
            "pnl": pnl,
            "roi": roi,
            "win": pnl > 0,
        }

# ============================================================================
# STRATEGY B: RESOLUTION BETTING
# ============================================================================

class ResolutionBettingStrategy:
    """
    Strategy B: Buy when mispriced, hold to resolution.

    Assumes:
    - We identify mispricing (forecast says high prob, market underprices)
    - We buy at entry_price and hold
    - Token resolves to 1.0 if outcome happens, 0.0 if not
    - We win if forecast is accurate
    """

    @staticmethod
    def analyze_market(market: Dict, best_model: str = "ECMWF") -> Tuple[float, bool, str]:
        """Same as repricing — check if mispriced."""
        return RepricingStrategy.analyze_market(market, best_model)

    @staticmethod
    def simulate_resolution(
        entry_price: float,
        fair_value: float,
        actual_temp: float,
        threshold: float,
        stake: float = 100
    ) -> Dict:
        """
        Simulate holding to resolution.

        Win if actual_temp >= threshold, lose otherwise.
        """
        # Determine resolution price
        outcome_happened = (actual_temp >= threshold)
        resolution_price = 1.0 if outcome_happened else 0.0

        # Calculate PnL
        shares = stake / entry_price
        cost = stake
        revenue = shares * resolution_price
        pnl = revenue - cost
        roi = (pnl / cost) * 100

        return {
            "entry": entry_price,
            "resolution": resolution_price,
            "fair": fair_value,
            "actual_temp": actual_temp,
            "threshold": threshold,
            "outcome_happened": outcome_happened,
            "shares": shares,
            "pnl": pnl,
            "roi": roi,
            "win": pnl > 0,
        }

# ============================================================================
# ANALYSIS ENGINE
# ============================================================================

class StrategyComparison:
    """Compare both strategies across all markets."""

    def __init__(self):
        self.repricing_results = []
        self.resolution_results = []
        self.mispricings_found = 0
        self.mispriced_markets = []

    def run_analysis(self):
        """Analyze all markets with both strategies."""
        print("="*80)
        print("DUAL-STRATEGY ANALYSIS: Repricing vs Resolution Betting")
        print("="*80)

        for market in MARKETS:
            self._analyze_single_market(market)

        self._print_summary()
        self._export_results()

    def _analyze_single_market(self, market: Dict):
        """Analyze one market with both strategies."""
        city = market["city"]
        threshold = market["outcome_threshold"]
        actual_temp = market["actual_temp"]
        entry_price = market["poly_entry_price"]
        resolution_price = market["poly_resolution_price"]

        # Use ECMWF as primary (from Phase 4 analysis)
        fair_value, is_mispriced, thesis = RepricingStrategy.analyze_market(market, "ECMWF")

        print(f"\n{'─'*80}")
        print(f"{city.upper()} (Actual: {actual_temp}°C, Threshold: >{threshold}°C)")
        print(f"{'─'*80}")
        print(f"Entry price: ${entry_price:.4f} | Fair value: ${fair_value:.4f}")
        print(f"Mispricing: {'✅ YES' if is_mispriced else '❌ NO'} (edge: {fair_value - entry_price:.4f})")
        print(f"Thesis: {thesis}")

        if not is_mispriced:
            print("→ Not mispriced enough to trade (need >8% edge). Skipping both strategies.")
            return

        self.mispricings_found += 1
        self.mispriced_markets.append((city, fair_value - entry_price, fair_value))

        # STRATEGY A: Repricing
        print(f"\n📊 STRATEGY A: Temporary Repricing")
        repricing = RepricingStrategy.simulate_exit(entry_price, fair_value, stake=100)
        print(f"   Exit at 90% of fair value: ${repricing['exit']:.4f}")
        print(f"   PnL: ${repricing['pnl']:+.2f} ({repricing['roi']:+.1f}%)")
        print(f"   Result: {'✅ WIN' if repricing['win'] else '❌ LOSS'}")
        self.repricing_results.append((city, repricing))

        # STRATEGY B: Resolution Betting
        print(f"\n💰 STRATEGY B: Hold to Resolution")
        resolution = ResolutionBettingStrategy.simulate_resolution(
            entry_price, fair_value, actual_temp, threshold, stake=100
        )
        print(f"   Holds to resolution at ${resolution['resolution']:.4f}")
        print(f"   Outcome: {'✅ WIN (temp exceeded)' if resolution['outcome_happened'] else '❌ LOSS (temp missed)'}")
        print(f"   PnL: ${resolution['pnl']:+.2f} ({resolution['roi']:+.1f}%)")
        print(f"   Result: {'✅ WIN' if resolution['win'] else '❌ LOSS'}")
        self.resolution_results.append((city, resolution))

        # Compare
        if repricing['pnl'] > resolution['pnl']:
            print(f"\n🏆 WINNER: Strategy A (Repricing) +${repricing['pnl'] - resolution['pnl']:.2f}")
        elif resolution['pnl'] > repricing['pnl']:
            print(f"\n🏆 WINNER: Strategy B (Resolution) +${resolution['pnl'] - repricing['pnl']:.2f}")
        else:
            print(f"\n🏆 TIE: Both strategies equal")

    def _print_summary(self):
        """Print summary statistics."""
        print("\n" + "="*80)
        print("SUMMARY STATISTICS")
        print("="*80)

        print(f"\n🎯 Mispricings Found: {self.mispricings_found}/{len(MARKETS)} markets")

        if self.mispricings_found == 0:
            print("\n⚠️  NO MISPRICINGS DETECTED in any market!")
            print("   All Polymarket prices are fair or underpriced (from long perspective)")
            print("   → Cannot execute either strategy profitably")
            return

        # Strategy A results
        print(f"\n{'─'*80}")
        print(f"STRATEGY A: TEMPORARY REPRICING (Buy mispriced, exit at fair value)")
        print(f"{'─'*80}")

        if self.repricing_results:
            wins_a = sum(1 for _, r in self.repricing_results if r['win'])
            total_pnl_a = sum(r['pnl'] for _, r in self.repricing_results)
            avg_roi_a = sum(r['roi'] for _, r in self.repricing_results) / len(self.repricing_results)

            print(f"Win rate: {wins_a}/{len(self.repricing_results)} ({wins_a/len(self.repricing_results)*100:.1f}%)")
            print(f"Total PnL: ${total_pnl_a:+.2f}")
            print(f"Avg ROI: {avg_roi_a:+.1f}%")
            print(f"Profit factor: {self._profit_factor([r['pnl'] for _, r in self.repricing_results]):.2f}")

        # Strategy B results
        print(f"\n{'─'*80}")
        print(f"STRATEGY B: RESOLUTION BETTING (Buy mispriced, hold to resolution)")
        print(f"{'─'*80}")

        if self.resolution_results:
            wins_b = sum(1 for _, r in self.resolution_results if r['win'])
            total_pnl_b = sum(r['pnl'] for _, r in self.resolution_results)
            avg_roi_b = sum(r['roi'] for _, r in self.resolution_results) / len(self.resolution_results)

            print(f"Win rate: {wins_b}/{len(self.resolution_results)} ({wins_b/len(self.resolution_results)*100:.1f}%)")
            print(f"Total PnL: ${total_pnl_b:+.2f}")
            print(f"Avg ROI: {avg_roi_b:+.1f}%")
            print(f"Profit factor: {self._profit_factor([r['pnl'] for _, r in self.resolution_results]):.2f}")

        # Head-to-head
        print(f"\n{'─'*80}")
        print(f"HEAD-TO-HEAD COMPARISON")
        print(f"{'─'*80}")

        total_a = sum(r['pnl'] for _, r in self.repricing_results)
        total_b = sum(r['pnl'] for _, r in self.resolution_results)

        if total_a > total_b:
            print(f"🏆 WINNER: Strategy A (Repricing)")
            print(f"   Edge: +${total_a - total_b:.2f} ({(total_a/total_b - 1)*100:+.1f}%)")
        else:
            print(f"🏆 WINNER: Strategy B (Resolution Betting)")
            print(f"   Edge: +${total_b - total_a:.2f} ({(total_b/total_a - 1)*100:+.1f}%)")

        print(f"\nStrategy A: ${total_a:+.2f} total")
        print(f"Strategy B: ${total_b:+.2f} total")

    def _profit_factor(self, pnls: List[float]) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        gross_win = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))

        if gross_loss == 0:
            return float('inf') if gross_win > 0 else 1.0

        return gross_win / gross_loss

    def _export_results(self):
        """Export results to JSON."""
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "mispricings_found": self.mispricings_found,
            "strategy_a_repricing": {
                "trades": len(self.repricing_results),
                "total_pnl": sum(r['pnl'] for _, r in self.repricing_results),
                "win_rate": sum(1 for _, r in self.repricing_results if r['win']) / len(self.repricing_results) if self.repricing_results else 0,
                "results": {city: r for city, r in self.repricing_results}
            },
            "strategy_b_resolution": {
                "trades": len(self.resolution_results),
                "total_pnl": sum(r['pnl'] for _, r in self.resolution_results),
                "win_rate": sum(1 for _, r in self.resolution_results if r['win']) / len(self.resolution_results) if self.resolution_results else 0,
                "results": {city: r for city, r in self.resolution_results}
            }
        }

        with open("/root/Klaus/analysis/strategy_comparison_results.json", 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Results exported to strategy_comparison_results.json")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    analyzer = StrategyComparison()
    analyzer.run_analysis()
