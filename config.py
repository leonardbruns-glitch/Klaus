"""
Klaus Momentum Scalper — Configuration
All tunable parameters in one place. Python validates; Claude proposes changes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import os

try:
    from dotenv import load_dotenv
    # Load explicitly from the directory containing this file, not cwd.
    # load_dotenv() without a path walks up the directory tree and can pick up
    # a stale .env in a parent directory.
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

@dataclass
class BankrollConfig:
    total: float = 200.0              # updated: $100→$200 deposit (2026-04-05)
    base_stake: float = 20.0          # raised $10→$20 (user instruction 2026-04-08; surgical lag filter deployed)
    # Scale-up tiers (static sizing — Kelly deferred until n≥50 with stable per-regime WR):
    #   Tier 1: $10 — was active
    #   Tier 2: $20 — now (user instruction 2026-04-08, surgical lag filter reduces stop exposure)
    #   Tier 3: $25 — after confirmed WR>55% over 50+ live trades post-filter
    # Kelly deferred: edge is regime-dependent (WR swings 0%→80% by regime);
    # stop-hunting creates fat-tailed losses that break Kelly variance assumptions.
    scaled_stake: float = 20.0        # flat — heat-check disabled; raise per tiers above
    heat_trigger_wins: int = 999      # heat-check disabled — all 4 heat losses were SL exits costing -$14.36
    max_open_positions: int = 3       # data collection phase — allow more concurrent trades
    max_daily_loss: float = 100.0     # user-set: no intraday halt
    post_close_cooldown: float = 0.0  # disabled — data collection phase
    min_entry_price: float = 0.03     # reject tokens below 3¢ (near-zero liquidity)


@dataclass
class FeeConfig:
    # Polymarket taker fees — updated 2026-03-30: new fee categories added.
    # Updown crypto (BTC/ETH/SOL): peak taker fee raised 1.56% → 1.80% at 0.50 odds.
    # Formula: fee = C × p × feeRate × (p × (1-p))^exponent
    # Near extremes (p < 0.35 or p > 0.65): fee approaches ~0%.
    extreme_fee_rate: float = 0.005   # < 0.35 or > 0.65 region
    middle_fee_rate: float = 0.018    # raised 0.016→0.018: updown peak now 1.80% at p=0.50
    extreme_low: float = 0.35         # below this = extreme YES
    extreme_high: float = 0.65        # above this = extreme NO
    middle_min_confidence: float = 0.52   # loosened 0.80→0.52: data collection phase
    updown_min_confidence: float = 0.52   # loosened 0.62→0.52: fee math is theory, not validated data
    # Research (Reichenbach & Walther 2025, 124M trades): YES tokens systematically
    # overpriced. Slight NO bias in ambiguous signals is academically supported.


@dataclass
class MomentumConfig:
    # ── 5-min breakout ──────────────────────────────────────────────────────
    breakout_lookback: int = 10        # bars for range high/low calculation
    volume_surge_mult: float = 2.0     # raised 1.5→2.0: research says ≥2× confirms genuine
                                       # momentum vs noise (2-3× confirmed by practitioner data)

    # ── 15-min trend alignment ───────────────────────────────────────────────
    ema_fast: int = 5                  # 15-min fast EMA period
    ema_slow: int = 15                 # 15-min slow EMA period

    # ── Order-book imbalance ─────────────────────────────────────────────────
    ob_imbalance_thresh: float = 0.60  # bid / (bid + ask) depth ratio

    # ── Composite scoring thresholds ────────────────────────────────────────
    min_score: float = 0.35            # 15m only mode — sniper composite threshold
    # weights (must sum to 1.0)
    # Rebalanced 2026-03-30: added intrawindow_delta ("king signal" per Archetapp research);
    # reduced trend weight (EMA5/15 on 15-min bars = 75/225-min MAs, too slow for 5-min windows);
    # increased OB weight (R²=0.65 for short-interval price variance per academic research).
    w_breakout: float = 0.25           # was 0.35
    w_trend: float = 0.10             # was 0.25; lagging signal demoted (EMA5/15 on 15-min bars
                                       # = 75/225-min MAs, too slow for 5-min windows)
    w_volume: float = 0.20
    w_ob: float = 0.25               # was 0.20; OB imbalance IR>0.65 → 58% accuracy
    w_intrawindow: float = 0.20      # intra-window delta ("king signal" per Archetapp research)

    # ── Regime filters ───────────────────────────────────────────────────────
    # ATR percentile gate: skip entries when current ATR(14) is below the 30th
    # percentile of the last 50 bars. Research: momentum edge concentrates in
    # higher-vol regimes; sub-30th percentile is near-random walk territory.
    atr_regime_percentile: float = 0.40    # raised 0.30→0.40: 20-trade data low-ATR WR=33% vs high-ATR=50%

    # Hurst exponent: estimated via R/S method on last hurst_window bars.
    # H < hurst_min = mean-reverting → currently logged only (soft gate).
    # Upgrade to hard gate once we have sufficient live data to calibrate.
    hurst_window: int = 60             # bars for Hurst estimate
    hurst_min: float = 0.45           # below this = mean-reverting regime (soft flag)


@dataclass
class ExecutionConfig:
    ob_scan_interval: float = 1.0      # seconds between order-book refreshes
    hard_exit_seconds: int = 240       # raised 180→240: lag_analysis shows main PM reprice at 135-225s
                                       # 180s was cutting trades right before the repricing cluster
    no_trade_last_sec: int = 45        # exit 45s before window end — OBs thin below this
    entry_price_buffer: float = 0.05   # limit buy at price * (1 + buffer), capped at 0.30
    cascade_levels: int = 3            # sell in 3 tranches
    cascade_pct: float = 0.333        # fraction of position per tranche
    cascade_interval: float = 2.0     # seconds between cascade tranches
    slippage_tolerance: float = 0.02   # reject fill if slippage > 2 %
    retry_attempts: int = 3
    retry_delay: float = 0.5           # seconds between retries


@dataclass
class EdgeConfig:
    """
    Parameters derived from baseline bot performance analysis + market research.

    Baseline bot findings (38 trades):
      - 14:00 UTC: 46% WR, $+12.92  ← all the edge lives here
      - 15:00+:     0% WR, -$5.98   ← pure capital destruction
      - ETH: 30% WR  │  SOL: 17%  │  BTC: 6% (near-worthless)
      - All P&L from PROFIT_1 exits; stop losses are small but frequent

    Market research findings:
      - 13:30 UTC = CPI/NFP/PPI/claims release → 30s-2min Polymarket mispricing lag
      - 14:00-15:00 UTC = NYSE open spillover (academic: Bitcoin options peak)
      - Thursday 13:30 UTC = weekly jobless claims (consistent edge every week)
      - Simple arbitrage dead (2.7s avg); information lag arbitrage still viable
      - 170+ bots active; top 3 wallets made $4.2M/yr automated
    """
    # Trading hours gate (UTC). Set to [] to trade all hours.
    # Was [13,14,15] based on 38-trade baseline data — too small a sample to restrict.
    # Strategy: trade all hours, collect data, then tighten to proven edge windows.
    allowed_hours_utc: List[int] = field(default_factory=lambda: [])

    # Blocked hours (UTC). Takes precedence over allowed_hours_utc.
    # Empty = no hours blocked (collect data at all hours post-fix).
    # Pre-fix T42-T51 data showed UTC 13-14h WR=22%, but those losses predate the
    # funding gate fix, VPIN gate removal, and briefing latency removal. Not valid
    # evidence against 13-14h under the current signal stack.
    blocked_hours_utc: List[int] = field(default_factory=lambda: [])

    # Macro event score discount: REMOVED — live data shows UTC 13-14h is the worst
    # performing window (n=12, WR=25%, avg=-$3.5). Discount was sending more trades into
    # the worst hours. Keep macro_window_hours for future reference only.
    macro_window_hours: List[int] = field(default_factory=lambda: [13, 14])
    macro_score_discount: float = 0.0   # disabled: live data n=12 WR=25% avg=-$3.5 at UTC 13-14h

    # Per-asset minimum momentum score multiplier.
    # BTC live data: n=12 WR=25% avg=-$1.88 — requires 40% higher composite score.
    # ETH: n=12 WR=50% avg=-$1.26 — no penalty, needs more data.
    # SOL: n=22 WR=45% avg=-$1.24 — no penalty, largest sample.
    asset_score_multiplier: dict = field(default_factory=lambda: {
        "BTC": 1.40,  # live data n=12 WR=25%: needs 40% higher score to qualify
        "ETH": 1.0,
        "SOL": 1.0,
    })

    # Entry price sweet spot from data: best trades entered 0.245–0.260.
    # Tighten max_entry from 0.30 to 0.27 to avoid overpriced tokens.
    max_entry_price: float = 0.27

    # Intrawindow delta cap for updown markets (which skip max_entry_price).
    # Research (Archetapp token pricing model): BTC delta > 0.10% from window open
    # → token already at $0.80–$0.97. At this point the market has fully priced
    # the outcome and fee-adjusted edge shrinks dramatically. Skip entries where
    # our intrawindow_score implies delta > this threshold.
    # Calibrated: 0.10 sensitivity (3% token move = score 1.0 at sensitivity=0.03)
    # → 0.08 delta score cap ≈ ~2.4% token move → entry price in $0.72–$0.80 range.
    max_intrawindow_score: float = 0.85  # skip if intrawindow_s alone > 0.85 (fully priced)

    # Assets paused from the Window Sniper based on live WR data.
    # SOL paused: 28.6% WR over 7 sniper trades (live data 2026-03-31).
    # Revisit when SOL has 20+ sniper trades with confirmed edge.
    sniper_excluded_assets: List[str] = field(default_factory=lambda: [])  # all assets active — gathering data

    # Per-asset minimum delta override (absolute %). Takes precedence over the global
    # _session_min_delta when set for a given asset.
    # BTC live data (n=22): delta > -0.10% → WR=17% (-$12.19); delta > -0.12% → WR=44% (-$14.10).
    # BTC reprices faster than ETH/SOL — weak BTC moves recover within the window.
    # Require delta ≥ 0.12% for BTC entries. SOL/ETH unaffected (wins at 0.10-0.11%).
    per_asset_min_delta_pct: dict = field(default_factory=lambda: {
        "BTC": 0.13,  # raised 0.12→0.13: delta -0.119/-0.120 both STOP_LOSS (-$6.49 each); 0.13 blocks both
    })

    # Cross-asset cascade: when one asset fires a strong signal, correlated
    # assets get a score discount (easier entry) — BTC moves first, ETH/SOL follow.
    # Research: crypto assets correlate within 10-30s on macro moves.
    cascade_trigger_score: float = 0.55     # lead asset must score above this
    cascade_score_discount: float = 0.06    # subtract from min_score for followers
    cascade_assets: dict = field(default_factory=lambda: {
        "BTC": ["ETH", "SOL"],   # BTC leads → discount ETH, SOL
        "ETH": ["SOL"],          # ETH leads → discount SOL
    })


@dataclass
class MarketConfig:
    # Token IDs are looked up dynamically; these are human labels for filtering
    tracked_assets: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])

    clob_api_url: str = "https://clob.polymarket.com"
    gamma_api_url: str = "https://gamma-api.polymarket.com"

    bar_interval_primary: int = 300    # 5-min bars in seconds
    bar_interval_secondary: int = 900  # 15-min bars in seconds
    history_bars: int = 50             # bars to keep in rolling window

    scan_interval: float = 0.2         # seconds between full market sweeps (was 1.0s; 0.2 = 5× faster detection)


@dataclass
class SignalGatesConfig:
    """
    Feature flags for new signal gates. All default OFF (data collection only).

    Each gate starts as False — data is LOGGED but trading is NOT affected.
    Enable a gate only after reviewing cond_wr / liq / funding / coinbase_div
    fields in trades.jsonl and confirming the signal has predictive value.

    NEVER enable a gate without n≥20 trades showing the correlation.
    """
    # ── Signal 1: Conditional WR gate ────────────────────────────────────────
    # Blocks entries where our historical WR for (regime, window_size_s) < min_wr
    # AND we have at least min_n trades of evidence.
    # Data shows QUIET_DEAD=0% WR, QUIET_FLOW=33% WR — enable after n≥10 per bucket.
    conditional_wr_gate: bool = False      # True = block low-WR conditions
    conditional_wr_min:  float = 0.35     # minimum WR to allow entry
    conditional_wr_min_n: int = 10        # minimum n before gate activates

    # ── Signal 2: Liquidation cascade gate ───────────────────────────────────
    # Blocks entry if a large cascade liquidation happened in the last 60s
    # IN THE SAME DIRECTION as our trade (indicates price may still be in free-fall).
    # Example: we want BUY_YES (price up), but $2M of long liquidations just fired
    # → someone pushed price down to trigger those longs → cascade may continue.
    liquidation_gate: bool = False         # True = block on large cascade
    liquidation_threshold: float = 500_000 # $ threshold for "large" liquidation

    # ── Signal 3: Funding rate gate ───────────────────────────────────────────
    # Blocks/reduces confidence when funding rate is extreme AND aligns with
    # our direction (crowded trade = vulnerable to flush).
    # funding_rate in ExternalSignal is annualised APR (e.g. 0.0001*3*365*100=10.95%).
    # 8h rate equivalent: APR / (3*365) * 100 → 10.95% APR = 0.01% per 8h.
    # ENABLED: live data n=11 negative-funding trades → WR=18.2%, −$29.3 net.
    # Negative funding (shorts crowded) + BUY_NO (also short) = crowded flush risk.
    # 3% APR threshold was too aggressive: it blocked ALL NO trades in normal bear markets
    # (observed: ETH -4.4% APR, SOL -12.1% APR both blocked → zero NO trades possible).
    # -4.4% to -12% APR is normal crypto bear market funding, not crowded-short extreme.
    # True squeeze risk = -30% to -200% APR (capitulation events). Raised to 20% APR.
    # n=11 original data doesn't specify funding level of losing trades — 3% was not justified.
    funding_gate: bool = True              # ENABLED: data confirms crowded-short flush pattern
    funding_extreme_apr: float = 20.0     # raised 3→20%: 3% blocked all NO in normal bear market; true crowded shorts = -30%+ APR

    # ── Signal 4: Cross-exchange divergence gate ──────────────────────────────
    # Blocks entry if Binance moved significantly but Coinbase price hasn't moved
    # (divergence > threshold). Large divergence = Binance-isolated move = suspicious.
    # Normal divergence is <0.05% due to arbitrageurs. >0.15% = uncorroborated move.
    cross_exchange_gate: bool = False      # True = block on large divergence
    cross_exchange_div_threshold: float = 0.20  # % divergence to consider suspicious


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
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    signal_gates: SignalGatesConfig = field(default_factory=SignalGatesConfig)

    # ── Auth ─────────────────────────────────────────────────────────────────
    # Accepts old-bot naming (PRIVATE_KEY / FUNDER_ADDRESS) or Klaus naming.
    wallet_private_key: str = field(
        default_factory=lambda: (
            lambda k: k[2:] if k.startswith(("0x", "0X")) else k
        )(os.getenv("PRIVATE_KEY", os.getenv("WALLET_PRIVATE_KEY", "")).strip())
    )
    funder_address: str = field(
        default_factory=lambda: os.getenv("FUNDER_ADDRESS", "").strip()
    )
    signature_type: int = field(
        default_factory=lambda: int(os.getenv("SIGNATURE_TYPE", "0"))
    )

    # ── Safety ───────────────────────────────────────────────────────────────
    # Set DRY_RUN=false in .env (or change here) to go live.
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "true").lower() != "false"
    )


CONFIG = KlausConfig()
