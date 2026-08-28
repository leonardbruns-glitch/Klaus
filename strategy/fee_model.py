"""
Polymarket weather-market fee/rebate/slippage model.

Single source of truth for execution costs across the bot and backtester.

Fee formula (probability-weighted; verified May 2026 per Polymarket docs):
    fee_rate(p) = PEAK_RATE × 4 × p × (1 − p)

Peaks at p = 0.50, collapses to 0 at p = 0.00 / 1.00.

Weather peak rate: 1.25%. Maker rebate: 25% of counterparty fee.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ── Polymarket fee schedule (weather category, May 2026) ─────────────────────
WEATHER_PEAK_FEE_RATE = 0.0125    # 1.25% peak taker fee
MAKER_REBATE_FRAC     = 0.25      # makers earn 25% of counterparty taker fee
MIN_FEE_USD           = 0.001     # absolute floor per trade

# Tick / size limits
TICK_SIZE             = 0.01      # 1 cent default
MIN_NOTIONAL_USD      = 5.0       # typical minimum per market

# Order-type latency assumptions (used by backtester only)
MARKETABLE_DELAY_S    = 3.0       # 3-second placement delay on Polymarket
HEARTBEAT_INTERVAL_S  = 10.0      # WS keepalive

# Spread / slippage estimates (when L2 book not available)
DEFAULT_SPREAD        = 0.02      # 2¢ typical on liquid weather buckets
THIN_SPREAD           = 0.06      # 6¢ on secondary markets
SLIPPAGE_BPS_PER_USD  = 0.05      # +0.05% slippage per $1 traded above $5


Role = Literal["maker", "taker"]


@dataclass
class FillResult:
    """Result of a simulated fill including fee accounting."""
    avg_price:     float    # effective entry/exit price after slippage
    fee_usd:       float    # absolute fee paid (negative = rebate received)
    fee_rate:      float    # signed fee rate at this fill
    fill_size_usd: float    # notional filled
    role:          Role
    note:          str = ""


def taker_fee_rate(price: float) -> float:
    """Probability-weighted taker fee rate at this price.

    fee = PEAK × 4 × p × (1 − p)

    At p=0.5 → 1.25%
    At p=0.2 → 0.80%
    At p=0.05 → 0.24%
    At p=0.01 → 0.05%
    """
    p = max(0.001, min(0.999, price))
    return WEATHER_PEAK_FEE_RATE * 4.0 * p * (1.0 - p)


def maker_rebate_rate(counterparty_price: float) -> float:
    """Rebate the maker earns when their order fills.

    Maker pays nothing themselves; earns MAKER_REBATE_FRAC of the taker fee
    paid by the counterparty.
    """
    return MAKER_REBATE_FRAC * taker_fee_rate(counterparty_price)


def estimate_spread(bucket_volume_usd: float = 0.0) -> float:
    """Heuristic spread estimate when L2 not available.

    Liquid markets (NYC/London with active LP bots): ~2¢
    Thin markets (secondary cities, deep tails): up to 6¢+
    """
    if bucket_volume_usd >= 5_000:
        return DEFAULT_SPREAD
    if bucket_volume_usd >= 500:
        return DEFAULT_SPREAD * 1.5
    return THIN_SPREAD


def simulate_taker_fill(
    intended_price: float,
    notional_usd:   float,
    spread:         float = DEFAULT_SPREAD,
) -> FillResult:
    """Simulate a FAK taker fill: crosses the spread, pays the fee.

    Effective price = intended_price + ½ spread + size-based slippage.
    Fee charged at fee_rate(effective_price).
    """
    half_spread = spread / 2.0
    size_slip   = max(0.0, notional_usd - MIN_NOTIONAL_USD) * SLIPPAGE_BPS_PER_USD / 10_000.0
    eff_price   = min(0.99, intended_price + half_spread + size_slip)
    rate        = taker_fee_rate(eff_price)
    fee         = max(MIN_FEE_USD, notional_usd * rate)
    return FillResult(
        avg_price=eff_price,
        fee_usd=fee,
        fee_rate=rate,
        fill_size_usd=notional_usd,
        role="taker",
        note=f"spread={spread:.3f} slip={size_slip:.4f}",
    )


def simulate_maker_fill(
    intended_price: float,
    notional_usd:   float,
    spread:         float = DEFAULT_SPREAD,
    fill_probability: float = 0.55,
) -> FillResult | None:
    """Simulate a GTC post-only maker fill.

    Returns None if the resting order doesn't get filled (fill_probability gate).
    When it does fill:
      - effective price = intended_price (we set it; counterparty crosses to us)
      - we earn rebate based on counterparty fee
    """
    if fill_probability < 1.0:
        import random
        if random.random() > fill_probability:
            return None

    # Counterparty paid taker fee at our maker price; we earn rebate
    rate_signed = -maker_rebate_rate(intended_price)
    fee_signed  = notional_usd * rate_signed   # negative = rebate inflow
    return FillResult(
        avg_price=intended_price,
        fee_usd=fee_signed,
        fee_rate=rate_signed,
        fill_size_usd=notional_usd,
        role="maker",
        note="rebate received",
    )


def round_trip_cost(entry_price: float, exit_price: float, notional_usd: float,
                    entry_role: Role = "maker", exit_role: Role = "taker",
                    spread: float = DEFAULT_SPREAD) -> dict:
    """Total cost of an entry+exit round trip at given roles.

    Used by the backtester to compute net edge after execution costs.

    Returns: {"total_fee_usd", "entry_fee", "exit_fee", "net_edge_pct"}
    """
    entry = (simulate_maker_fill(entry_price, notional_usd, spread, 1.0) if entry_role == "maker"
             else simulate_taker_fill(entry_price, notional_usd, spread))
    exit_ = (simulate_maker_fill(exit_price, notional_usd, spread, 1.0) if exit_role == "maker"
             else simulate_taker_fill(exit_price, notional_usd, spread))
    if entry is None or exit_ is None:
        return {"total_fee_usd": 0.0, "entry_fee": 0.0, "exit_fee": 0.0, "filled": False}
    total_fee = entry.fee_usd + exit_.fee_usd
    # Net edge of round trip ignoring outcome (cost-only view)
    return {
        "total_fee_usd": round(total_fee, 4),
        "entry_fee":     round(entry.fee_usd, 4),
        "exit_fee":      round(exit_.fee_usd, 4),
        "fee_drag_pct":  round(total_fee / notional_usd * 100.0, 3),
        "filled":        True,
    }


# ── Strategy execution profiles ──────────────────────────────────────────────
# Encodes "how does each strategy actually fill" for the backtester.
# Each profile: (entry_role, exit_role, default_spread, expected_fill_prob)

STRATEGY_PROFILES = {
    "STRAT_1_OVERNIGHT": ("maker", "taker", DEFAULT_SPREAD, 0.70),  # GTC entry, FAK if loser
    "STRAT_2_BRACKET":   ("maker", "taker", DEFAULT_SPREAD, 0.60),  # both legs need fills
    "STRAT_3_INTRADAY":  ("taker", "taker", DEFAULT_SPREAD, 0.95),  # FAK in + FAK out
    "STRAT_4_TAIL":      ("taker", "settle", THIN_SPREAD,    0.85), # FAK in, hold to resolution (no exit fee)
    "STRAT_5_NWPLAG":    ("taker", "taker", DEFAULT_SPREAD, 0.90),  # FAK in, FAK out on reprice
    "STRAT_6_CITYCTR":   ("maker", "settle", DEFAULT_SPREAD, 0.50), # GTC in, hold to resolution
    "STRAT_7_NOSIDE":    ("maker", "taker", DEFAULT_SPREAD, 0.60),  # GTC NO-token, FAK if confirmed loser
}


def profile_for(strategy_tag: str) -> tuple[str, str, float, float]:
    """Return (entry_role, exit_role, default_spread, fill_probability)."""
    return STRATEGY_PROFILES.get(strategy_tag, ("taker", "taker", DEFAULT_SPREAD, 0.95))
