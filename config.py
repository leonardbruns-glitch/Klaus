"""
Klaus Momentum Scalper — Configuration
All tunable parameters in one place. Python validates; Claude proposes changes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import os


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

@dataclass
class BankrollConfig:
    total: float = 300.0
    base_stake: float = 15.0          # 5 % of capital
    scaled_stake: float = 30.0        # 10 % — unlocked after heat_trigger_wins
    heat_trigger_wins: int = 2        # consecutive wins to unlock scaling
    max_open_positions: int = 3       # never overexpose
    max_daily_loss: float = 60.0      # 20 % drawdown → halt


@dataclass
class FeeConfig:
    # Polymarket charges up to 1.80 % near 0.50 odds
    extreme_fee_rate: float = 0.005   # < 0.35 or > 0.65 region
    middle_fee_rate: float = 0.018    # 0.35 – 0.65 "fat middle"
    extreme_low: float = 0.35         # below this = extreme YES
    extreme_high: float = 0.65        # above this = extreme NO
    middle_min_confidence: float = 0.80   # only enter fat middle at ≥ 80 % confidence


@dataclass
class MomentumConfig:
    # ── 5-min breakout ──────────────────────────────────────────────────────
    breakout_lookback: int = 10        # bars for range high/low calculation
    volume_surge_mult: float = 1.5     # volume vs rolling average to confirm breakout

    # ── 15-min trend alignment ───────────────────────────────────────────────
    ema_fast: int = 5                  # 15-min fast EMA period
    ema_slow: int = 15                 # 15-min slow EMA period

    # ── Order-book imbalance ─────────────────────────────────────────────────
    ob_imbalance_thresh: float = 0.60  # bid / (bid + ask) depth ratio

    # ── Composite scoring thresholds ────────────────────────────────────────
    min_score: float = 0.60            # minimum score to consider any entry
    # weights (must sum to 1.0)
    w_breakout: float = 0.35
    w_trend: float = 0.25
    w_volume: float = 0.20
    w_ob: float = 0.20


@dataclass
class ExecutionConfig:
    ob_scan_interval: float = 1.0      # seconds between order-book refreshes
    hard_exit_seconds: int = 180       # forced exit if not profitable within 3 min
    cascade_levels: int = 3            # sell in 3 tranches
    cascade_pct: float = 0.333        # fraction of position per tranche
    cascade_interval: float = 2.0     # seconds between cascade tranches
    slippage_tolerance: float = 0.02   # reject fill if slippage > 2 %
    retry_attempts: int = 3
    retry_delay: float = 0.5           # seconds between retries


@dataclass
class MarketConfig:
    # Token IDs are looked up dynamically; these are human labels for filtering
    tracked_assets: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])

    clob_api_url: str = "https://clob.polymarket.com"
    gamma_api_url: str = "https://gamma-api.polymarket.com"

    bar_interval_primary: int = 300    # 5-min bars in seconds
    bar_interval_secondary: int = 900  # 15-min bars in seconds
    history_bars: int = 50             # bars to keep in rolling window

    scan_interval: float = 5.0         # seconds between full market sweeps


@dataclass
class AnalyticsConfig:
    log_dir: str = "logs"
    trade_log: str = "logs/trades.jsonl"
    session_log: str = "logs/session.jsonl"
    edge_drift_window: int = 20        # trades for rolling edge calc
    fee_bleed_threshold: float = 0.30  # alert if fees > 30 % of gross profit
    min_win_rate: float = 0.52         # below this → flag strategy drift


@dataclass
class KlausConfig:
    bankroll: BankrollConfig = field(default_factory=BankrollConfig)
    fees: FeeConfig = field(default_factory=FeeConfig)
    momentum: MomentumConfig = field(default_factory=MomentumConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    markets: MarketConfig = field(default_factory=MarketConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)

    # ── Auth ─────────────────────────────────────────────────────────────────
    polymarket_api_key: str = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_KEY", "")
    )
    polymarket_api_secret: str = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_SECRET", "")
    )
    polymarket_api_passphrase: str = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_PASSPHRASE", "")
    )
    wallet_private_key: str = field(
        default_factory=lambda: os.getenv("WALLET_PRIVATE_KEY", "")
    )

    # ── Safety ───────────────────────────────────────────────────────────────
    dry_run: bool = True   # ← set False only when live credentials are loaded


CONFIG = KlausConfig()
