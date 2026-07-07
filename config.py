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
    total: float = 109.66             # updated: 2026-04-18, capital=$109.66
    base_stake: float = 50.0          # 2026-05-07 (user directive: 30→50, concurrent cap 1)
    scaled_stake: float = 50.0        # flat — heat-check disabled
    heat_trigger_wins: int = 999      # heat-check disabled — all 4 heat losses were SL exits costing -$14.36
    max_open_positions: int = 2       # 2026-05-07 user instruction: 1→2 BOND positions max concurrent
    max_daily_loss_pct: float = 0.14   # 2026-06-05: armed ~-$10/day halt — the ONE backstop on the loosened band gate (ruin_floor stays off per user)
    weekly_floor: float = 0.0         # disabled
    ruin_floor: float = 89.16         # RATCHETED 2026-07-07 (EVOLVE daily): 0.40 × trailing-30d high-water $222.90 (measured 2026-07-05) per INVARIANTS #2 formula, HW > $100. Comparator now tracks cash + engine positions + ladder-at-cost (main._ladder_open_cost), so this no longer false-trips on ladder fires. Ratchet-up-only; unattended agents may never lower it. (Was 40.0, armed 2026-07-02.)
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
    min_hold_seconds: float = 30.0     # Phase 1 immunity zone — soft exits disabled before this
    signal_flip_delay: float = 5.0     # Phase 2: SIGNAL_FLIPPED must persist this long before firing
    pt_objective: float = 0.22         # Stage-1 profit target (flat 22%)
    max_trade_duration: float = 210.0  # Phase 3: hard close at this many seconds
    entry_slip_cap: float = 0.035      # reject fill if entry slippage > 3.5%
    catastrophic_sl_pct: float = 0.45  # Phase 1 only: exit immediately if loss exceeds this


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
    # n=540 data: hr=07 WR=12.5% (n=8, PF=0.13) — kill switch threshold.
    # hr=02 CONFIRMED BLOCKED: n=15 old WR=26.7% + n=8 recent WR=0% = n=23 combined,
    #   consistent 0-27% WR across both datasets. -$5.58 in last 25 trades alone.
    #   Single macro snap reversal at 02:xx hit BTC+ETH+SOL simultaneously (correlated loss).
    #   Meets kill switch criteria (<35% WR over 20+ trades). Blocked 2026-04-12.
    # hr=06 BLOCKED 2026-04-15: BOND data n=14 WR=29% net=-$18.09 (European open volatility)
    # hr=08 BLOCKED 2026-04-15: BOND data n=11 WR=45% net=-$18.86 (European open volatility)
    # hr=13,14 BLOCKED 2026-04-15: sniper data WR=25% n=12 avg=-$3.5 (NYSE open volatility)
    # hr=22 is the crown jewel: WR=73.3%, PF=7.10, +$69.8 (n=30) — never block.
    blocked_hours_utc: List[int] = field(default_factory=lambda: [])
    # Full-hour BOND block: no entries at all during these UTC hours.
    # 00=midnight reset, 08=EU open, 13=NYSE open, 18=NYSE midday spike, 20=late US session.
    bond_blocked_hours_utc: List[int] = field(default_factory=lambda: [])
    bond_volatile_hour_starts: List[int] = field(default_factory=lambda: [6])  # first 15 min only
    bond_volatile_minutes_gate: int = 15

    # Macro event score discount: REMOVED — live data shows UTC 13-14h is the worst
    # performing window (n=12, WR=25%, avg=-$3.5). Discount was sending more trades into
    # the worst hours. Keep macro_window_hours for future reference only.
    macro_window_hours: List[int] = field(default_factory=lambda: [13, 14])
    macro_score_discount: float = 0.0   # disabled: live data n=12 WR=25% avg=-$3.5 at UTC 13-14h

    # Per-asset minimum momentum score multiplier — disabled 2026-04-08.
    # Was BTC=1.40 based on n=12 WR=25% (stale). N=31 BTC now shows WR=51.6%.
    # BTC still protected by per_asset_min_delta_pct=0.13 + lag kill zones.
    asset_score_multiplier: dict = field(default_factory=lambda: {
        "BTC": 1.0,
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

    # Per-asset minimum delta (absolute %). Takes precedence over global _session_min_delta.
    # Full delta analysis 2026-04-12 (delta x asset x WR):
    #
    #   BTC 0.12-0.18%: n=73  WR=46.7%  net=-$32.30 — broken across all sub-buckets
    #   BTC 0.18-0.22%: n=4   WR=75%    net=+$7.71  — first profitable BTC zone
    #   BTC 0.22-0.28%: n=5   WR=60%    net=+$5.57
    #
    #   ETH 0.12-0.18%: n=41  WR=41%    net=-$38.57 — catastrophic; 0.15-0.18 avg=-$2.45/trade
    #   ETH 0.18-0.22%: n=11  WR=63.6%  net=+$13.02 — clean reversal, first profitable ETH zone
    #   ETH 0.22+:      n=7   WR=100%   net=+$15.95
    #
    #   SOL 0.12-0.15%: n=44  WR=63.6%  net=+$21.70 — best performing zone across all assets
    #   SOL 0.15-0.18%: n=16  WR=56.2%  net=+$2.41
    #   SOL 0.18-0.22%: n=8   WR=37.5%  net=-$13.64 — drops off hard (watch for max_delta gate)
    #
    # YES vs NO at delta>=0.18: YES WR=100% n=9 net=+$14.55 vs NO WR=47% n=19 net=-$1.15
    # Asymmetry noted — Binance up-moves close PM lag more reliably than down-moves.
    # Not gated yet (n=9 YES is thin); collect 20+ before adding directional filter.
    per_asset_min_delta_pct: dict = field(default_factory=lambda: {
        "BTC": 0.0,   # 2026-04-22 (user directive: upstream floor off; per-mode enforced)
        "ETH": 0.0,
        "SOL": 0.0,
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
class DeadZoneConfig:
    """
    Flat-market / volatility filters for TERMINAL entries.
    All thresholds default to 0.0 (disabled). Enable after reviewing logs.

    How to read the log fields (all prefixed term_dz_):
      term_dz_range_usd   — 60-min BTC H-L range in USD
      term_dz_er          — Kaufman ER (0=chop, 1=clean trend)
      term_dz_atr_ratio   — current 15-min ATR / 4h baseline ATR

    Enable a gate by setting the threshold to a non-zero value in this config.
    Recommended starting values once n≥100: range_min_usd=50, er_min=0.25, atr_spike_ratio=1.5
    """
    # Minimum 60-min spot H-L range (USD). Skip if BTC < this (flat/dead market).
    # Dynamic alternative: set range_pct_of_price=0.001 and range_use_pct=True
    # for 0.1% of spot price (≈$100 at BTC=$100k), which scales with price.
    range_min_usd: float = 0.0           # 0 = disabled
    range_pct_of_price: float = 0.001    # 0.1% of spot — used only when range_use_pct=True
    range_use_pct: bool = False          # if True, use pct threshold instead of fixed USD

    # Kaufman Efficiency Ratio minimum (14-period 1m closes).
    # Below this = price is chopping, not trending. 0 = disabled.
    er_min: float = 0.0                  # 0 = disabled; suggested 0.25 after validation

    # Relative ATR spike ratio. If current 15-min ATR > ratio × 4h baseline, skip.
    # Protects against whipsaw conditions (high spreads, rapid reversals).
    # 0.0 = disabled; >0 enables the gate.
    atr_spike_ratio: float = 0.0         # 0 = disabled; suggested 1.5 after validation


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
    dead_zone: DeadZoneConfig = field(default_factory=DeadZoneConfig)

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
        default_factory=lambda: os.getenv("DRY_RUN", "true").strip().lower() != "false"
    )


CONFIG = KlausConfig()
