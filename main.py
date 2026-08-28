"""
Klaus — Momentum Scalper
Main async event loop: data → strategy → risk → execution → feedback.

Usage:
    python main.py                     # dry run (default)
    POLYMARKET_API_KEY=... python main.py  # live (set dry_run=False in config)

Loop cadence:
    - Every 1 second:  order-book scan for all open positions (exit check)
    - Every 5 seconds: full market sweep for new signals
    - Every 30 minutes: print feedback report
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import logging.handlers
import math
from collections import deque
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional, Set

# ---------------------------------------------------------------------------
# pre_score schema (Layer 1, strictly pre-causal entry quality)
# ---------------------------------------------------------------------------
# Bump _PRE_SCORE_VERSION whenever the feature set, weights, or thresholds
# change. The schema hash is computed from the feature tuple below and
# logged + persisted with every entry. If you change a feature without
# updating both the version AND the tuple, the hash diverges from the
# version string — that mismatch is the leakage detector.
#
# Each tuple entry: (feature_name:type, version_token).
# version_token must encode the data window or source so any silent change
# (e.g. switching from backward to forward window) bumps the hash.
_PRE_SCORE_VERSION = "v1_2026_04_observation"
_PRE_SCORE_FEATURE_SCHEMA = (
    ("accel_sustained:bool", "v1"),
    ("has_hist:bool",        "v1"),
    ("delta_accel_30s:f",    "v1:bw30s"),   # bw30s = backward 30s window
    ("edge_drift_30s:f",     "v1:bw30s"),
    ("stab_class:str",       "v1:5flags_t0"),
    ("vel_for_stab:f",       "v1:t0"),
    ("class_ev:f",           "v1:EV_PRIOR_v1_2026_04_freeze"),
    ("token_dir_sign:f",     "v1:t0"),
)
_PRE_SCORE_SCHEMA_HASH = hashlib.sha256(
    "|".join(f"{n}@{v}" for n, v in _PRE_SCORE_FEATURE_SCHEMA).encode()
).hexdigest()[:8]

from config import CONFIG
from data.feeds import PolymarketFeed
from data.shadow import ShadowPipeline, TimelineSampler, ResolutionWriter, ExitPolicyShadow, DiscoverSignalRecorder, emit_token_trade, emit_binance_trade, emit_ob_delta
from strategy.momentum import MomentumScorer, Direction, FeeZone, SignalBreakdown, calculate_tp_sl, TPSLLevels
from strategy.window_sniper import WindowSniper, SniperBlock, SniperSignal, _session_min_delta, CONTRARIAN_MAX_ASK, CONTRARIAN_DELTA_ENABLED, BOND_ENABLED, SNIPER_ENABLED, MOM_ENABLED
from risk.manager import RiskManager, ExitStage
from analytics.lag_observations import log_lag_observation
from analytics.macro_engine import MacroEngine, _RateLimitError
from analytics.research_agent import ResearchAgent
from execution.order_manager import OrderManager, OrderResult, OrderStatus
from execution.redemption import Redeemer
from analytics.feedback import FeedbackEngine
from analytics.research import ResearchEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            "logs/bot.log", maxBytes=50_000_000, backupCount=5
        ),
    ],
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Shadow monitor — counterfactual analysis for blocked sniper signals
# ---------------------------------------------------------------------------

def _ladder_open_cost() -> float:
    """Cost basis of OPEN sprint-ladder shots (logs/sprint_ladder_state.json).

    The ladder trades the same wallet but outside risk.open_positions, so
    cash-based bankroll syncs read every ladder fire as a loss (2026-07-05
    ESCALATIONS: capital $39.69 < $40 ruin floor while true equity $217).
    Tracked capital = cash + engine positions at cost + ladder shots at cost.
    """
    try:
        with open("logs/sprint_ladder_state.json") as _f:
            _s = json.load(_f)
        return float(sum(sh.get("stake", 0.0) for sh in _s.get("shots", [])
                         if sh.get("status") == "open"))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# BOND total-loss cooldown helpers
# ---------------------------------------------------------------------------

_BOND_TOTAL_LOSS_COOLDOWN_S         = 20 * 60  # 20 min base
_BOND_TOTAL_LOSS_COOLDOWN_REDUCED_S = 10 * 60  # 10 min in high-WR hours
_BOND_TOTAL_LOSS_COOLDOWN_MIN_N     = 20        # min trades per hour to trust WR


def _compute_terminal_hour_wr(trades_path: str = "logs/trades.jsonl") -> dict:
    """Per-UTC-hour WR for live TERMINAL trades — used to reduce total-loss cooldown."""
    import datetime as _dt
    from collections import defaultdict as _dd
    hw: dict = _dd(int)
    ht: dict = _dd(int)
    try:
        with open(trades_path) as f:
            for line in f:
                try:
                    t = json.loads(line)
                    if not t.get("is_live"):
                        continue
                    if t.get("bond_entry_class") != "TERMINAL":
                        continue
                    ts = t.get("ts_open", 0)
                    if not ts:
                        continue
                    h = _dt.datetime.utcfromtimestamp(float(ts)).hour
                    ht[h] += 1
                    if float(t.get("net_pnl", 0.0)) > 0:
                        hw[h] += 1
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception as exc:
        logging.getLogger("main").warning("terminal_hour_wr compute failed: %s", exc)
    return {h: hw[h] / ht[h] for h in ht if ht[h] >= _BOND_TOTAL_LOSS_COOLDOWN_MIN_N}


_COOLDOWN_STATE_FILE = "logs/cooldown_state.json"


def _load_cooldown_state() -> dict:
    """Load persisted total-loss cooldown timestamps so restarts don't reset them."""
    try:
        with open(_COOLDOWN_STATE_FILE) as f:
            data = json.load(f)
        now = time.time()
        # Discard entries that are already past the max cooldown window
        return {k: v for k, v in data.items()
                if now - float(v) < _BOND_TOTAL_LOSS_COOLDOWN_S}
    except Exception:
        return {}


def _save_cooldown_state(state: dict) -> None:
    """Persist total-loss cooldown timestamps to disk."""
    try:
        os.makedirs("logs", exist_ok=True)
        with open(_COOLDOWN_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as exc:
        logger.warning("Failed to save cooldown state: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WEATHER_CLASSES_SET = frozenset({
    "WEATHER_ARB", "WEATHER_INTRADAY", "WEATHER_TAIL",
    "WEATHER_NOSIDE", "WEATHER_CITYCTR", "WEATHER_BRACKET",
    "WEATHER_M1_PROBE", "WEATHER_STWA",
})


def _build_weather_extra(
    meta: dict,
    bond_entry_class: str,
    exit_price: float,
    shares: float,
    entry_price: float,
    stake: float,
    net_pnl: float | None,
) -> dict:
    """Build extra_fields for record_trade for WEATHER_* positions.

    Pulls weather_* metadata from meta (populated at entry).
    For resolution exits (exit_price ≥ 0.99 or ≤ 0.01) also sets
    entered_correctly and kline_pnl immediately — no backfill needed.
    For intraday exits leaves them None; the backfill loop fills them in.
    """
    extra: dict = {k: v for k, v in meta.items() if k.startswith("weather_")}
    if bond_entry_class not in _WEATHER_CLASSES_SET:
        return extra
    if exit_price >= 0.99:
        extra["entered_correctly"] = True
        extra["kline_pnl"] = round(net_pnl, 4) if net_pnl is not None else round(shares * (1.0 - entry_price), 4)
    elif exit_price <= 0.01:
        extra["entered_correctly"] = False
        extra["kline_pnl"] = round(net_pnl, 4) if net_pnl is not None else round(-stake, 4)
    return extra


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

class KlausBot:
    """Top-level orchestrator."""

    def __init__(self) -> None:
        self.feed = PolymarketFeed()
        self.scorer = MomentumScorer()
        self.risk = RiskManager()
        self.orders = OrderManager()
        self.analytics = FeedbackEngine()
        self.research = ResearchEngine(self.feed, self.scorer)
        self.macro_engine = MacroEngine()
        self.research_agent = ResearchAgent(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        self.sniper = WindowSniper()
        self._running = False
        self._last_report_ts = 0.0
        # track entry metadata for trade recording
        self._open_meta: Dict[str, dict] = {}
        self._pos_log_ts: Dict[str, float] = {}   # last log time per position
        # Shadow monitor dedup: track (token_id, window_end_ts) already being monitored
        # to avoid spawning a new task every 0.2s scan cycle for the same block.
        self._shadow_active: Set[tuple] = set()
        # Last known external signals per asset — shared between signal loop (writer)
        # and OB scan loop (reader). Used by advise_exit without a separate fetch.
        self._last_ext_signals: Dict[str, object] = {}
        # Reversal stop confirmation: counts consecutive 1s OB checks where spot is
        # above the adverse threshold. Fire only when count >= 2 — filters single-tick noise.
        self._rev_breach_count: Dict[str, int] = {}
        # BOND_DIR_REVERSAL confirmation: consecutive scans where window delta has reversed.
        # Requires 5 consecutive checks (~5s sustained) before firing exit.
        self._dir_rev_count: Dict[str, int] = {}
        # Buy attempt tracking for session report
        self._buy_tried: int = 0
        self._buy_filled: int = 0
        self._buy_failed_reasons: Dict[str, int] = {}
        # Residual share tracker: shares that survived a partial cascade_sell at close.
        # Format: token_id → {shares, asset, neg_risk, tick_size, attempts, last_try}
        # Background sweep retries every 60s up to 10 attempts (~10 min).
        self._residual_pending: Dict[str, dict] = {}
        # Exit concurrency guard: prevents multiple cascade_sells firing on the same
        # token while the first is still awaiting CLOB fills (OB scan runs every 200ms,
        # stage-1 cascade takes ~6s — without this lock, 30 concurrent cascades drain
        # the CLOB balance to near-zero by tranche 3, leaving shares unsold).
        self._exit_in_progress: set = set()
        # Pending entries: token_ids approved but _enter_position not yet complete.
        # Guards against race between spike path and 5s sweep both approving the
        # same token before either has called open_position(). Checked synchronously
        # (before first await) so asyncio single-thread guarantee makes it race-free.
        self._pending_entries: set = set()
        # Asset-level entry lock: prevents duplicate positions when spike + scan
        # both approve the same asset before either fill is confirmed.
        # Checked synchronously (before first await) — race-free in asyncio.
        self._pending_asset_entries: set = set()
        # Event-driven spike dedup: tracks last spike entry attempt per asset.
        # Separate from the 5s sweep — prevents double-entry when both paths fire.
        self._last_spike_ts: Dict[str, float] = {}
        # Post-entry price snapshots for path classification.
        # token_id → {30: price_at_T30s, 60: price_at_T60s}
        # Populated in _check_open_positions; consumed and cleared at close.
        self._entry_snaps: Dict[str, Dict[int, float]] = {}
        # BOND_PRICE_SL confirmation counter: increments each scan price is below 50%.
        # SL only fires after 7 consecutive scans (~7s) to filter stop-hunt wicks.
        self._sl_below_count: Dict[str, int] = {}
        # Positions that have had the T+30s stall check (one-shot per position).
        self._stall_checked: set = set()
        # Per-token rolling snapshot: deque of (ts, bond_delta, edge) for acceleration/drift.
        self._bond_snapshots: Dict[str, deque] = {}
        # Peak bond_move reached per position (for trailing stop on winners).
        self._peak_bond_move: Dict[str, float] = {}
        # Trough bond_move + peak timestamp per position (for compression /
        # expansion detection in STALL and EXHAUSTION).
        self._trough_bond_move: Dict[str, float] = {}
        self._peak_ts: Dict[str, float] = {}
        # COMPRESSION BIAS RULE: consecutive-scan confirmation counters for
        # STALL and EXHAUSTION. In compression, require multi-scan persistence
        # before firing — prevents single-snapshot noise from triggering exit.
        self._stall_conf_count: Dict[str, int] = {}
        self._exhaustion_conf_count: Dict[str, int] = {}
        self._early_loss_conf_count: Dict[str, int] = {}
        self._early_chop_count: Dict[str, int] = {}
        # Non-binding LLM bond advisor: token_id → {decision, conf, reason}
        # Populated async after BOND entry; consumed and cleared at record_trade time.
        self._bond_llm_decisions: Dict[str, dict] = {}
        # LLM independent trader: open shadow positions keyed by token_id.
        # Populated pre-gate by _bond_llm_independent_eval; exited in _check_open_positions.
        self._llm_shadow_positions: Dict[str, dict] = {}
        # Running LLM eval tasks — prevents double-firing while a task is in-flight.
        self._llm_eval_pending: Set[str] = set()
        # Serialize entry evals — one at a time prevents 429 bursts.
        self._llm_eval_semaphore = asyncio.Semaphore(1)
        # Global cooldown after 429 — all entry evals blocked until this timestamp.
        self._llm_rate_limit_until = 0.0
        # Per-window TERMINAL dedup: set of (asset, window_end_ts_rounded) already traded.
        # Prevents re-entry into the same asset after TP/exit within the same window.
        self._terminal_traded_windows: set = set()
        # Total-loss cooldown: asset → ts of last BOND total loss (resolved NO / expired unsold)
        self._bond_total_loss_ts: Dict[str, float] = _load_cooldown_state()
        # Regime cooldown: global BOND entry pause after heavy single loss or back-to-back losses.
        # Tier 1: single loss <= -$7 → 5m pause. Tier 2: 2nd loss <= -$5 in 30m → 10m pause.
        self._regime_cooldown_until: float = 0.0
        self._last_regime_loss_ts: float = 0.0
        # Hourly WR for TERMINAL trades (computed once at startup from trades.jsonl)
        self._terminal_hour_wr: dict = _compute_terminal_hour_wr()
        # Tokens where TERMINAL TP level has been touched — TP price becomes trail floor.
        self._terminal_tp_touched: set = set()
        # Per-token ask price history for pre-entry trajectory: {token_id: deque[(ts, ask)]}
        # Updated every bond scan; used to compute term_token_delta_30s / _60s at entry.
        self._token_ask_history: Dict[str, deque] = {}
        # Window-anchored pre-entry snap references: ask captured at fixed remaining thresholds.
        # Keys: token_id → {150: ask, 120: ask, 90: ask}
        # 150s = 60s before window opens, 120s = 30s before, 90s = at window open.
        self._term_pre_snap_refs: Dict[str, Dict[int, float]] = {}
        # RSI and size-weighted ask VWAP captured once at remaining≤90s (entry zone opens).
        # Frozen pre-entry so they can serve as future gate candidates.
        self._term_pre_entry_obs: Dict[str, dict] = {}
        # Completed LLM decisions awaiting next scan for real entry.
        # TAKE: consumed (popped) when real trade fires.
        # SKIP: kept in dict until token leaves feed (prevents re-eval in same window).
        self._llm_ind_decisions: Dict[str, dict] = {}
        # Active exit polling for open BOND positions.
        self._llm_exit_decisions: Dict[str, dict] = {}   # token_id → {decision, conf, reason}
        self._llm_exit_pending: Set[str] = set()          # tasks currently in flight
        self._llm_exit_last_eval: Dict[str, float] = {}   # token_id → last eval timestamp
        # Peak-stability tracker: timestamp of first scan where bond_move
        # dropped below 80% of peak after peak_ts. Absence = no breach yet.
        # Used by TRAIL_SL to distinguish a held peak (stable consolidation)
        # from a wick peak (immediate reversal).
        self._peak_breach_ts: Dict[str, float] = {}
        # 2-stage zombie gate state.
        # Stage 1 (T+30s): sets token_id → flag_ts when mfe<3% and snap30<5%.
        # Stage 2 (T+50s): exits as ZOMBIE_EARLY_EXIT when also mae>25% and bounce<8%.
        self._zombie_flag_ts: Dict[str, float] = {}
        # Trajectory snapshots for structure_state classification (T+60s).
        # token_id → {t_sec: value_pct} at t ∈ {10, 30, 60}.
        # Used to compute MFE slope, monotonic expansion, early adverse timing.
        self._traj_mfe: Dict[str, Dict[int, float]] = {}
        self._traj_mae: Dict[str, Dict[int, float]] = {}
        self._price_at_t10s: Dict[str, float] = {}
        # 5s intra-hold bid snapshots for trajectory analysis.
        # token_id → next elapsed_s at which to log.
        self._traj_snap_next: Dict[str, float] = {}
        # Stop-hunt wick confirmation for BOND_SL_20.
        # When SL fires with zero favorable move and fast hold (≤60s), we arm
        # a 25s timer rather than selling immediately. If price recovers above
        # -15% in that window the wick is cancelled; otherwise SL executes.
        # Pattern confirmed 2026-04-23 (ETH YES EARLY-A-PRE: -29% wick, +81% snap-back in 30s).
        self._bond_sl_arm_ts: Dict[str, float] = {}
        # Wick confirmation for BOND_CATASTROPHIC (-15% SL).
        # Data: 34% of BOND_CATASTROPHIC exits are flash crashes — token drops -15%+
        # then recovers to entry within 30s while spot barely moves (+0.002%).
        # Fix: wait 8s before exiting. If price recovers above -12%: cancel and hold.
        # If still below -15% after 8s: genuine failure, exit immediately.
        # Hard bypass when bond_remaining < 15s (no time to wait).
        self._catas_breach_ts: Dict[str, float] = {}
        # Wick event metadata: keyed by token_id, stores breach context for recovery-time logging.
        self._catas_breach_info: Dict[str, dict] = {}
        # Cancel count: incremented each time wick timer is cancelled for a position.
        # Second breach skips the 10s timer — sawtooth oscillation is not a wick.
        self._catas_cancel_count: Dict[str, int] = {}
        # post_bc_reversal_rate tracker: set at first ARM, persists through cancels.
        # Records whether price recovers above entry after a BC breach.
        # Cleared at position exit — not at cancel — so it captures the full trajectory.
        self._bc_arm_tracker: Dict[str, dict] = {}
        # PAE: Persistent Adverse Exit — tracks how long bid has been ≥5% below entry.
        # _pae_above_since: when bid recovered above -5%; timer only resets after 5s sustained recovery.
        self._pae_below_since: Dict[str, float] = {}
        self._pae_above_since: Dict[str, float] = {}
        # Shadow exit logger: bid-depth + velocity rules, log-only.
        # _shadow_fired: token_id → True once first-fire event has been emitted.
        # _shadow_velocity_buf: token_id → [(ts, bid)] for ~20s history at 1s sampling.
        # Joinable to trades.jsonl via (token_id, ts_open) → logs/exit_shadow.jsonl.
        self._shadow_fired: Dict[str, bool] = {}
        self._shadow_velocity_buf: Dict[str, list] = {}
        # Shadow market observation engine (Phase 2).
        # Runs parallel to live trading; reads only from feed caches.
        # Logs to logs/shadow/hot/<date>/{market_timeline,gate_trace,window_resolution}.jsonl.
        self.shadow_pipeline = ShadowPipeline()
        self.shadow_timeline = TimelineSampler(self, self.shadow_pipeline)
        self.shadow_resolution = ResolutionWriter(self, self.shadow_pipeline)
        # Exit-policy shadow (Deliverable 3 of 2026-05-08 audit). Hooks into
        # TimelineSampler via getattr; no start/stop needed (stateless writer).
        self.shadow_exit_policy = ExitPolicyShadow(self.shadow_pipeline)
        # Phase 2 Discovery — Step 3 passive recorder (2026-05-10).
        # Records first-fire raw state for the single surviving signal family
        # (arb<0.99 + DOWN + ask 0.10-0.55 + rem 60-240). Hooked from
        # TimelineSampler via getattr. Zero impact on execution path.
        self.shadow_discover_signal = DiscoverSignalRecorder(self.shadow_pipeline)
        # Phase 2 Discovery — live entry path (2026-05-10).
        # GATED OFF (.enabled=False). Activate only after live-vs-replay
        # validation passes. Per user instruction, BOND must be disabled
        # when this is enabled — only one strategy active at a time.
        from strategy.discover_strategy import DiscoverStrategy
        self.discover_strategy = DiscoverStrategy(self)
        # CRYPTO_ARB — DISABLED 2026-05-21: weather-only live mode
        self.crypto_arb = None
        self.oracle_sweeper = None  # permanently off; replaced by LDA
        from strategy.late_direction_arb import LateDirectionArb
        self.lda_strategy = LateDirectionArb(self)
        # LDA disabled 2026-05-17 (user instruction).
        self.lda_strategy.enabled = False
        # VOLARB disabled 2026-05-19 (user instruction).
        self.volarb_strategy = None
        # CAS-LowAsk — DISABLED 2026-05-21: weather-only live mode
        self.cas_lowask_strategy = None
        # SPORTS_COPY — slippage-tolerant wallet copy-trade. Shadow mode on first deploy.
        # 5 wallets selected from 1.06M-wallet harvest (2026-05-19); combined 157 cycles, 539 trades/30d.
        from strategy.sports_copy import SportsCopy
        self.sports_copy = SportsCopy(self)
        self.sports_copy.live_mode = False   # PAUSED — shadow only
        # CryptoUpDown — 15-min BTC/ETH/SOL Up-or-Down markets, CAS synchrony signal
        from strategy.updown import CryptoUpDown
        self.updown_strategy = CryptoUpDown(self)
        # WeatherArb — daily city temperature prediction market arb vs Open-Meteo forecasts
        from strategy.weather_arb import WeatherArb
        self.weather_arb = WeatherArb(self)
        # NWP-LAG — HFT-style scheduler firing at known NWP publish slots.
        # Subsumes the slow overnight scan; faster latency-arb against model updates.
        from strategy.nwp_lag import NwpLagArbitrage
        self.nwp_lag = NwpLagArbitrage(self)
        # CITY-CENTRE ARB — structural retail-mispricing harvester. GTC maker, hold to resolution.
        from strategy.city_centre_arb import CityCentreArb
        self.city_centre_arb = CityCentreArb(self)
        from strategy.no_side_arb import NoSideArb
        self.no_side_arb = NoSideArb(self)
        # Safety guards: $40 ring-fenced sub-bankroll, $10/trade cap, -$10/day kill
        # Gap sweeper DISABLED alongside oracle sweep (same deployment batch).
        self.gap_sweeper = None
        self.redeemer = Redeemer(
            clob_client=self.orders._client,
            proxy_wallet=CONFIG.funder_address or "",
            private_key=CONFIG.wallet_private_key or "",
            signature_type=CONFIG.signature_type,
            dry_run=CONFIG.dry_run,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self.feed.start()
        _bond_tp = self._ws_bond_tp_check
        _carb = self.crypto_arb.on_book_update if self.crypto_arb else None
        _cas_bbo = self._cas_on_bbo
        _wa_bbo = self.weather_arb._on_weather_bbo if self.weather_arb else None
        async def _bbo_chain(tid: str, bid: float) -> None:
            await _bond_tp(tid, bid)
            if _carb: await _carb(tid, bid)
            await _cas_bbo(tid)
            if _wa_bbo: await _wa_bbo(tid, bid)
        self.feed._on_bbo_update = _bbo_chain
        await self.orders.start()
        self._running = True
        mode = "DRY RUN" if CONFIG.dry_run else "LIVE"

        # ── Bankroll sync: reconcile tracked capital with actual Polymarket balance ──
        # GET /balance-allowance is not CF-blocked — works from any machine.
        # Corrects drift from manual trades, crashed sessions, or manual deposits.
        #
        # Sync capital = unspent USDC cash + value of open positions (cost basis:
        # remaining_shares × entry_price — same convention as STWA held_k).
        # fetch_usdc_balance() returns CASH ONLY, so we add the deployed position
        # value back. This lets the bot reconcile to TRUE capital on every startup
        # EVEN WITH POSITIONS OPEN, instead of freezing on a stale number and never
        # seeing deposits (principle: always reflect real wallet state). Cost-basis
        # slightly overcounts losers vs live MTM — accepted for a bankroll/sizing
        # figure; it self-corrects to realized cash as positions resolve.
        now_ts = time.time()
        if not CONFIG.dry_run:
            real_balance = self.orders.fetch_usdc_balance()
            if real_balance is not None:
                pos_value = sum(p.remaining_shares * p.entry_price
                                for p in self.risk.open_positions.values())
                pos_value += _ladder_open_cost()
                true_capital = real_balance + pos_value
                tracked = self.risk.bankroll.capital
                delta = true_capital - tracked
                if abs(delta) > 0.05:  # $0.05 tolerance for rounding
                    logger.warning(
                        "BANKROLL SYNC: tracked=%.2f  cash=%.2f + positions=%.2f = actual=%.2f  delta=%+.2f — syncing",
                        tracked, real_balance, pos_value, true_capital, delta,
                    )
                else:
                    logger.info(
                        "Bankroll verified: tracked=%.2f matches cash+positions=%.2f",
                        tracked, true_capital,
                    )
                self.risk.bankroll.capital = true_capital
                self.risk.bankroll._save()
            else:
                logger.warning("BANKROLL SYNC failed: fetch_usdc_balance returned None — using tracked=%.2f", self.risk.bankroll.capital)

        logger.info("=" * 50)
        logger.info("Klaus Momentum Scalper — %s", mode)
        logger.info("Capital: $%.2f | Base stake: $%.2f | Scaled: $%.2f",
                    self.risk.bankroll.capital, CONFIG.bankroll.base_stake, CONFIG.bankroll.scaled_stake)
        logger.info("Markets: %s", CONFIG.markets.tracked_assets)
        logger.info("=" * 50)

        # Register event-driven delta spike callback.
        # Fires immediately from Binance aggTrade when asset delta crosses 0.03%.
        # Bypasses the 5s signal loop — detects lag the moment it opens.
        self.feed.register_delta_spike_callback(self._on_delta_spike)

        # Pre-warm py_clob_client caches (neg_risk + fee_rate) for all tracked tokens.
        # Without this, the first order per token triggers GET /neg-risk + GET /fee-rate
        # before submitting, adding ~2s of latency and causing the sniper to miss fills.
        if not CONFIG.dry_run:
            self.orders.prewarm_token_caches(self.feed.tokens)

        # Replay resolution tasks missed due to previous restarts (within 15min)
        asyncio.create_task(self._replay_pending_resolutions())

        # Start shadow observation engine (last — needs feed/_session live).
        await self.shadow_pipeline.start()
        await self.shadow_timeline.start()
        await self.shadow_resolution.start()
        if self.gap_sweeper is not None:
            await self.gap_sweeper.start()
        # Wire shadow trade-tape callbacks (event-driven; persist what feeds.py
        # currently discards: Polymarket trades + Binance aggTrades).
        self.feed._shadow_emit_clob_trade = lambda token_id, ev: emit_token_trade(
            self.shadow_pipeline, self, token_id, ev
        )
        self.feed._shadow_emit_binance_trade = lambda asset, price, qty, ibm, ets: emit_binance_trade(
            self.shadow_pipeline, asset, price, qty, ibm, ets
        )
        # Tier 1: OB delta event-stream recorder. Fires from feeds.py per WS
        # price_change/best_bid_ask. Top-5-level filter inside the emitter.
        self.feed._shadow_emit_ob_delta = lambda token_id, ev: emit_ob_delta(
            self.shadow_pipeline, self, token_id, ev
        )
        # Tier 1: order lifecycle recorder. Wires shadow pipeline into OrderManager
        # so every submit/fill event is logged to order_lifecycle.jsonl.
        self.orders._shadow_pipeline = self.shadow_pipeline
        # Tier 1: liquidation recorder. Wires shadow pipeline into feeds.py
        # so Binance forceOrder events are persisted (previously memory-only).
        self.feed._shadow_pipeline = self.shadow_pipeline
        # Gap sweeper: wire ob_delta callback so GapSweeper tracks last-quote timestamps.
        if self.gap_sweeper is not None:
            self.feed._gap_sweeper_cb = self.gap_sweeper.on_ob_event

    async def stop(self) -> None:
        self._running = False
        # Stop shadow first so queue can drain before feed/orders shut down.
        try:
            await self.shadow_timeline.stop()
            await self.shadow_resolution.stop()
            _sweeper = getattr(self, "oracle_sweeper", None)
            if _sweeper is not None:
                await _sweeper.stop()
            _lda = getattr(self, "lda_strategy", None)
            if _lda is not None:
                await _lda.stop()
            _volarb = getattr(self, "volarb_strategy", None)
            if _volarb is not None:
                await _volarb.stop()
            _cas = getattr(self, "cas_lowask_strategy", None)
            if _cas is not None:
                await _cas.stop()
            _scp = getattr(self, "sports_copy", None)
            if _scp is not None:
                await _scp.stop()
            _gap = getattr(self, "gap_sweeper", None)
            if _gap is not None:
                await _gap.stop()
            await self.shadow_pipeline.stop()
        except Exception:
            logger.exception("shadow stop failed")
        await self.feed.stop()
        await self.orders.stop()
        report = self.analytics.generate_claude_report()
        logger.info("\nFINAL REPORT:\n%s", report)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        await self.start()

        # Thread-based event loop watchdog — asyncio coroutines cannot monitor
        # each other when the loop itself is blocked (sync call, CPU-bound work,
        # deadlock). A daemon thread runs independently and kills the process if
        # the loop stops pinging within the threshold. systemd/launchd restarts.
        _watchdog_last_ping = [time.monotonic()]
        _WATCHDOG_THRESHOLD = 45.0  # seconds without a ping before hard kill

        def _watchdog_thread():
            import sys
            time.sleep(_WATCHDOG_THRESHOLD + 5)  # initial grace period
            while True:
                time.sleep(10.0)
                age = time.monotonic() - _watchdog_last_ping[0]
                if age > _WATCHDOG_THRESHOLD:
                    print(
                        f"WATCHDOG FATAL: event loop stalled {age:.0f}s — forcing restart",
                        file=sys.stderr, flush=True,
                    )
                    os._exit(1)  # bypass Python cleanup — systemd will restart

        import threading
        _wdt = threading.Thread(target=_watchdog_thread, daemon=True, name="loop-watchdog")
        _wdt.start()

        # Startup orphan sweep: sell any untracked token balances left over from
        # previous sessions. Delayed 10s to let the feed populate token list first.
        asyncio.create_task(self._startup_orphan_sweep())

        # ── 2026-05-21: LEGACY STRATEGIES PAUSED — exclusive weather focus ──
        # Code path preserved (importable, instantiable) so re-enabling is one-line.
        # Capital, scan cycles, and CLOB calls are reserved for weather strategies.
        if False:   # SPORTS_COPY — paused 2026-05-21
            try:
                await self.sports_copy.start()
            except Exception:
                logger.exception("sports_copy start failed")
        if False:   # CryptoUpDown — paused 2026-05-21
            try:
                self.updown_strategy.start()
            except Exception:
                logger.exception("updown_strategy start failed")

        # WeatherArb — daily temperature prediction arb (DRY_RUN_LOG=True initially)
        try:
            self.weather_arb.start()
        except Exception:
            logger.exception("weather_arb start failed")

        if False:  # NWP-LAG — paused 2026-05-22: STRAT_1-only mode
            try:
                self.nwp_lag.start()
            except Exception:
                logger.exception("nwp_lag start failed")

        if False:  # CITY-CENTRE ARB — paused 2026-05-22: STRAT_1-only mode
            try:
                self.city_centre_arb.start()
            except Exception:
                logger.exception("city_centre_arb start failed")

        if False:  # NO-SIDE ARB — paused 2026-05-22: STRAT_1-only mode
            try:
                self.no_side_arb.start()
            except Exception:
                logger.exception("no_side_arb start failed")

        ob_task = asyncio.create_task(self._ob_scan_loop())
        signal_task = asyncio.create_task(self._signal_loop())
        report_task = asyncio.create_task(self._report_loop())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(_watchdog_last_ping))
        research_task = asyncio.create_task(self.research.run())
        prewarm_task = asyncio.create_task(self._prewarm_loop())
        redeem_task = asyncio.create_task(self.redeemer.run_loop(interval_s=60.0))
        weather_backfill_task = asyncio.create_task(self._weather_backfill_loop())

        try:
            # return_exceptions=True: one task crashing doesn't cancel the others.
            # Each loop already catches exceptions internally; this is a safety net
            # for exceptions that escape the loop (startup errors, NameError, etc.)
            results = await asyncio.gather(
                ob_task, signal_task, report_task, heartbeat_task,
                research_task, prewarm_task, redeem_task, weather_backfill_task,
                return_exceptions=True,
            )
            for i, r in enumerate(results):
                if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                    logger.error("Task %d exited with exception: %s", i, r)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    # ── 1-second OB scan: monitor open positions ──────────────────────────────

    async def _ob_scan_loop(self) -> None:
        _scp_tick = 0
        while self._running:
            try:
                await self._check_open_positions()
            except Exception as exc:
                logger.error("OB scan error: %s", exc)
            # SPORTS_COPY stop/take check every ~5s
            _scp_tick += 1
            if _scp_tick >= 5:
                _scp_tick = 0
                try:
                    _scp = getattr(self, "sports_copy", None)
                    if _scp is not None and _scp.enabled:
                        await _scp.check_stop_take()
                except Exception:
                    logger.exception("sports_copy stop/take check failed")
            await asyncio.sleep(CONFIG.execution.ob_scan_interval)

    def _mark_bond_total_loss(self, asset: str) -> None:
        """Record timestamp of a BOND total loss to arm the re-entry cooldown."""
        self._bond_total_loss_ts[asset] = time.time()
        _save_cooldown_state(self._bond_total_loss_ts)
        logger.warning(
            "BOND_TOTAL_LOSS_COOLDOWN armed %s — %dm cooldown starts now (asset key=%r)",
            asset, _BOND_TOTAL_LOSS_COOLDOWN_S // 60, asset,
        )

    async def _cas_on_bbo(self, token_id: str) -> None:
        """CAS evaluation triggered by WS BBO update — replaces 1s scan lag."""
        try:
            _cas = getattr(self, "cas_lowask_strategy", None)
            if _cas is None:
                return
            token = self.feed.tokens.get(token_id)
            if token is None or token.window_seconds != 300:
                return
            ob = self.feed.order_books.get(token_id)
            if ob is None or not ob.asks:
                return
            import time as _time
            now = _time.time()
            remaining = token.window_end_ts - now
            ask = ob.asks[0][0]

            # Track ask change history for age/velocity metrics (change events only)
            if not hasattr(self, "_cas_ask_changes"):
                self._cas_ask_changes: dict = {}
            changes = self._cas_ask_changes.setdefault(token_id, [])
            if not changes or changes[-1][1] != ask:
                changes.append((now, ask))
                cutoff = now - 35.0
                self._cas_ask_changes[token_id] = [(t, a) for t, a in changes if t >= cutoff]
                changes = self._cas_ask_changes[token_id]
            ask_age_ms = round((now - changes[-1][0]) * 1000)
            _ref_30 = next((a for t, a in reversed(changes) if t <= now - 30.0), None)
            ask_delta_30s = round(ask - _ref_30, 4) if _ref_30 is not None else 0.0

            rec = {
                "token_id":              token_id,
                "condition_id":          token.condition_id,
                "asset":                 token.asset,
                "window_end_ts":         token.window_end_ts,
                "window_size_s":         token.window_seconds,
                "seconds_to_resolution": remaining,
                "outcome_dir":           token.outcome_direction,
                "outcome_side":          token.side,
                "best_ask":              ask,
                "ob_top1_ask_size":      ob.asks[0][1],
                "tok_snap_30s":          0.0,
                "ask_age_ms":            ask_age_ms,
                "ask_delta_30s":         ask_delta_30s,
            }
            # Pre-seed shadow + pre-signing at rem=85-95s, once per (asset, window)
            if 85.0 <= remaining <= 95.0:
                self._cas_preseed_shadow(token, ob.asks[0][0], remaining)
                asyncio.create_task(self.orders.presign_for_cas(
                    token_id, ob.asks[0][0],
                    stake_usd=5.0,
                    neg_risk=token.neg_risk,
                    tick_size=token.tick_size,
                ))
            await _cas.schedule_if_ready(rec)
        except Exception:
            pass

    def _cas_preseed_shadow(self, token, ask: float, remaining: float) -> None:
        """Log Binance signal state at rem≈90s for pre-seed directional agreement analysis."""
        try:
            import time as _time, json as _json, os as _os
            key = (token.asset, int(token.window_end_ts))
            if not hasattr(self, "_preseed_logged"):
                self._preseed_logged: set = set()
            if key in self._preseed_logged:
                return
            self._preseed_logged.add(key)

            feed = self.feed
            now = _time.time()
            asset = token.asset.upper()

            def _bnc_ret(secs):
                hist = feed._price_history.get(asset)
                spot = feed._spot_price.get(asset, 0.0)
                if not hist or not spot:
                    return 0.0
                cutoff = now - secs
                ref = next((p for ts, p in hist if ts <= cutoff), None)
                return (spot - ref) / ref * 100.0 if ref else 0.0

            partial_5m = 0.0
            spot = feed._spot_price.get(asset, 0.0)
            o5m = feed._spot_open_5m.get(asset, 0.0)
            if spot and o5m:
                partial_5m = (spot - o5m) / o5m * 100.0

            rec = {
                "record_type":    "preseed_shadow",
                "ts":             now,
                "asset":          asset,
                "window_end_ts":  token.window_end_ts,
                "outcome_dir":    token.outcome_direction,
                "outcome_side":   token.side,
                "rem":            round(remaining, 1),
                "ask":            ask,
                "bnc_ret_30s":    round(_bnc_ret(30), 4),
                "bnc_ret_60s":    round(_bnc_ret(60), 4),
                "bnc_partial_5m": round(partial_5m, 4),
            }
            log_dir = "logs/shadow"
            _os.makedirs(log_dir, exist_ok=True)
            with open(f"{log_dir}/preseed_shadow.jsonl", "a") as f:
                f.write(_json.dumps(rec) + "\n")
        except Exception:
            pass

    async def _ws_bond_tp_check(self, token_id: str, bid_price: float) -> None:
        """Instant BOND TP triggered by WS BBO update — no 1s scan delay."""
        try:
            pos = self.risk.open_positions.get(token_id)
            if pos is None or not pos.is_bond or token_id in self._exit_in_progress:
                return
            if pos.entry_price <= 0:
                return
            # WEATHER_ARB instant scalp on BBO: mid-band entries get a custom TP
            # equal to entry + max($0.03, 0.5 × edge), capped at fair × 0.9.
            # Favourite-band entries store scalp_tp=0.0 and skip this — they hold
            # until PROFIT_TARGET at 0.99 or natural resolution.
            if getattr(pos, "bond_entry_class", "").startswith("WEATHER_"):
                _scalp_tp = float(self._open_meta.get(token_id, {}).get("scalp_tp", 0.0))
                if _scalp_tp > 0 and bid_price >= _scalp_tp:
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        "WEATHER_SCALP_TP(WS) %s | bid=%.4f tp=%.4f ep=%.4f",
                        token_id[:12], bid_price, _scalp_tp, pos.entry_price,
                    )
                    try:
                        await self._exit_position(token_id, bid_price, "WEATHER_SCALP_TP")
                    finally:
                        self._exit_in_progress.discard(token_id)
                    return
            if bid_price >= 0.99 and getattr(pos, "bond_entry_class", "") not in ("LDA", "CAS_LOWASK", "WEATHER_M1_PROBE"):
                self._exit_in_progress.add(token_id)
                logger.info(
                    "PROFIT_TARGET(WS) %s/%s | bid=%.4f ep=%.4f",
                    pos.asset, pos.direction.name, bid_price, pos.entry_price,
                )
                try:
                    await self._exit_position(token_id, bid_price, "PROFIT_TARGET")
                finally:
                    self._exit_in_progress.discard(token_id)
        except Exception as exc:
            logger.error("_ws_bond_tp_check error: %s", exc)

    async def _check_open_positions(self) -> None:
        positions = list(self.risk.open_positions.items())
        if not positions:
            return

        # Fetch all OBs in parallel — no reason to wait sequentially
        obs = await asyncio.gather(
            *[self.feed.fetch_order_book(tid) for tid, _ in positions],
            return_exceptions=True,
        )

        for (token_id, pos), ob in zip(positions, obs):
            # If OB is unavailable but window is expiring, force-exit immediately.
            # This was broken by no_trade_last_sec 60→10: at T-10s OBs are often
            # empty/None for near-resolved tokens, causing the skip below to fire
            # and EXIT_WINDOW_END to never trigger.
            if ob is None or isinstance(ob, Exception):
                now_ts = time.time()
                remaining_ts = pos.window_end_ts - now_ts if pos.window_end_ts > 0 else 999
                if pos.is_bond:
                    # BOND positions hold to window outcome — never force-exit via OB_NOOB.
                    # OB commonly goes None in the last 45s of updown markets (thinning liquidity).
                    # Exception: window has ended and position is stuck (bid was <0.90 at T=0).
                    # Check CLOB balance — if 0, token settled on-chain; purge the record.
                    if pos.window_end_ts > 0 and remaining_ts < -30 and token_id not in self._exit_in_progress:
                        _settled_bal = self.orders.fetch_token_balance(token_id)
                        if _settled_bal is not None and _settled_bal < 0.05:
                            logger.info(
                                "BOND_SETTLED %s: balance=%.4f 30s post-window — %s",
                                token_id[:12], _settled_bal,
                                "redeemed win" if token_id in self.redeemer.confirmed_winners else "resolved NO",
                            )
                            _bs_meta = self._open_meta.pop(token_id, {})
                            self._pos_log_ts.pop(token_id, None)
                            _is_redeemed_win = token_id in self.redeemer.confirmed_winners
                            # LDA + VOLARB: Redeemer doesn't track these — use kline to determine outcome
                            if not _is_redeemed_win and getattr(pos, "bond_entry_class", "") in ("LDA", "VOLARB", "CAS_LOWASK") and pos.window_end_ts > 0:
                                try:
                                    import aiohttp as _aiohttp_bs
                                    _bs_sym_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
                                    _bs_sym = _bs_sym_map.get(pos.asset.upper())
                                    _bs_wsz = pos.window_seconds or 300
                                    _bs_kl_int = "5m" if _bs_wsz == 300 else "15m"
                                    _bs_wstart_ms = int((pos.window_end_ts - _bs_wsz) * 1000)
                                    async with self.feed._session.get(
                                        "https://api.binance.com/api/v3/klines",
                                        params={"symbol": _bs_sym, "interval": _bs_kl_int,
                                                "startTime": _bs_wstart_ms, "limit": 1},
                                        timeout=_aiohttp_bs.ClientTimeout(total=5),
                                    ) as _bs_kr:
                                        if _bs_kr.status == 200:
                                            _bs_kl = await _bs_kr.json()
                                            if _bs_kl and len(_bs_kl[0]) >= 5:
                                                _bs_kl_up  = float(_bs_kl[0][4]) >= float(_bs_kl[0][1])
                                                _bs_bet_up = getattr(pos, "bond_outcome_direction", "up") == "up"
                                                _is_redeemed_win = (_bs_bet_up == _bs_kl_up)
                                except Exception as _bs_kl_exc:
                                    logger.debug("BOND_SETTLED LDA kline check failed: %s", _bs_kl_exc)
                            _bs_exit_price = 1.0 if _is_redeemed_win else 0.0
                            _bs_class = getattr(pos, "bond_entry_class", "")
                            if _is_redeemed_win and _bs_class == "LDA":
                                _bs_reason = "LDA_KLINE_WIN"
                            elif _is_redeemed_win and _bs_class == "VOLARB":
                                _bs_reason = "VOLARB_KLINE_WIN"
                            elif _is_redeemed_win and _bs_class == "CAS_LOWASK":
                                _bs_reason = "CAS_KLINE_WIN"
                            elif _is_redeemed_win:
                                _bs_reason = "REDEEMED"
                            else:
                                _bs_reason = "BOND_SETTLED"
                            _pnl = self.risk.close_position(token_id, _bs_exit_price, _bs_reason)
                            if not _is_redeemed_win:
                                self._mark_bond_total_loss(pos.asset)
                            if _pnl is not None:
                                _bs_sig = _bs_meta.get("signal") or SignalBreakdown(
                                    direction=pos.direction, entry_price=pos.entry_price,
                                    composite=0.0, confidence=0.0, breakout_score=0.0,
                                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                    reason="bond_settled",
                                )
                                try:
                                    self.analytics.record_trade(
                                        token_id=token_id, asset=pos.asset, direction=pos.direction,
                                        entry_price=pos.entry_price, exit_price=_bs_exit_price,
                                        stake=pos.stake, shares=pos.shares,
                                        entry_fill=_bs_meta.get("entry_fill"), exit_fills=[],
                                        exit_reason=_bs_reason, signal=_bs_sig,
                                        ts_open=_bs_meta.get("ts_open", pos.open_ts), ts_close=now_ts,
                                        capital_before=self.risk.bankroll.capital - _pnl,
                                        heat_check_active=_bs_meta.get("heat_check", False),
                                        consecutive_wins=_bs_meta.get("consecutive_wins", 0),
                                        best_ask=pos.best_ask,
                                        net_pnl_actual=_pnl,
                                        market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                                        is_live=not CONFIG.dry_run,
                                        signal_source=_bs_meta.get("signal_source", "BOND"),
                                        window_size_s=_bs_meta.get("window_size_s") or pos.window_seconds or 0,
                                        pre_entry_momentum_pct=_bs_meta.get("pre_entry_momentum_pct", 0.0),
                                        bond_outcome_direction=pos.bond_outcome_direction,
                                        bond_delta_accel_30s=float(getattr(_bs_sig, "bond_delta_accel_30s", 0.0) or 0.0),
                                        bond_edge_drift_30s=float(getattr(_bs_sig, "bond_edge_drift_30s", 0.0) or 0.0),
                                        bond_accel_sustained=bool(getattr(_bs_sig, "bond_accel_sustained", False)),
                                        bond_has_hist=bool(getattr(_bs_sig, "bond_has_hist", False)),
                                    )
                                except Exception as _bse:
                                    logger.error("record_trade BOND_SETTLED failed: %s", _bse)
                    continue
                if pos.window_end_ts > 0 and remaining_ts <= 45:
                    logger.warning(
                        "OB UNAVAILABLE near window end %s (%.0fs remaining) — "
                        "checking CLOB balance then force-purging",
                        token_id[:12], remaining_ts,
                    )
                    # Verify shares actually exist before trying to sell.
                    # If balance=0 the position was already sold (manually or by previous exit).
                    _balance = self.orders.fetch_token_balance(token_id)
                    if _balance is None or _balance < 0.05:
                        # Nothing to sell — just purge the tracking record.
                        logger.warning(
                            "OB_NOOB_PURGE %s: balance=%.4f — position closed externally, purging record",
                            token_id[:12], _balance or 0.0,
                        )
                        _pnl = self.risk.close_position(token_id, pos.entry_price, "NOOB_EXTERNALLY_SOLD")
                        _noob_meta = self._open_meta.pop(token_id, {})
                        self._pos_log_ts.pop(token_id, None)
                        if _pnl is not None:
                            _noob_sig = _noob_meta.get("signal") or SignalBreakdown(
                                direction=pos.direction, entry_price=pos.entry_price,
                                composite=0.0, confidence=0.0, breakout_score=0.0,
                                trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                reason="noob_externally_sold",
                            )
                            try:
                                self.analytics.record_trade(
                                    token_id=token_id, asset=pos.asset, direction=pos.direction,
                                    entry_price=pos.entry_price, exit_price=pos.entry_price,
                                    stake=pos.stake, shares=pos.shares,
                                    entry_fill=_noob_meta.get("entry_fill"), exit_fills=[],
                                    exit_reason="NOOB_EXTERNALLY_SOLD", signal=_noob_sig,
                                    ts_open=_noob_meta.get("ts_open", pos.open_ts), ts_close=now_ts,
                                    capital_before=self.risk.bankroll.capital - _pnl,
                                    heat_check_active=_noob_meta.get("heat_check", False),
                                    consecutive_wins=_noob_meta.get("consecutive_wins", 0),
                                    best_ask=pos.best_ask,
                                    net_pnl_actual=_pnl,
                                    market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                                    is_live=not CONFIG.dry_run,
                                    signal_source=_noob_meta.get("signal_source", "SNIPER"),
                                    window_size_s=_noob_meta.get("window_size_s") or pos.window_seconds or 0,
                                    bond_delta_accel_30s=float(getattr(_noob_sig, "bond_delta_accel_30s", 0.0) or 0.0),
                                    bond_edge_drift_30s=float(getattr(_noob_sig, "bond_edge_drift_30s", 0.0) or 0.0),
                                    bond_accel_sustained=bool(getattr(_noob_sig, "bond_accel_sustained", False)),
                                    bond_has_hist=bool(getattr(_noob_sig, "bond_has_hist", False)),
                                )
                            except Exception as _ne:
                                logger.error("record_trade NOOB_EXTERNALLY_SOLD failed: %s", _ne)
                    elif token_id not in self._exit_in_progress:
                        self._exit_in_progress.add(token_id)
                        try:
                            await self._exit_position(token_id, pos.entry_price, "EXIT_WINDOW_END_NOOB")
                        finally:
                            self._exit_in_progress.discard(token_id)
                continue
            current_price = ob.bids[0][0] if len(ob.bids) > 0 else ob.mid

            # Guard: corrupt/zero entry_price would cause division-by-zero in
            # move_pct and incorrect SL/TP comparisons. Skip rather than act on garbage.
            if not pos.entry_price or pos.entry_price <= 0:
                logger.error(
                    "GUARD: %s entry_price=%.6f — skipping exit check (corrupt state)",
                    token_id[:12], pos.entry_price,
                )
                continue

            # ── Weather price path snapshot every 15 minutes ─────────────────
            if getattr(pos, "bond_entry_class", "").startswith("WEATHER_"):
                _w_meta = self._open_meta.get(token_id)
                if _w_meta is not None:
                    _snap_now = time.time()
                    if _snap_now - _w_meta.get("_price_snap_ts", 0) >= 900:
                        _w_meta.setdefault("weather_price_path", []).append(
                            [round(_snap_now, 1), round(current_price, 4)]
                        )
                        _w_meta["_price_snap_ts"] = _snap_now

            # ── Position status log every 5s ─────────────────────────────────
            now = time.time()
            if now - self._pos_log_ts.get(token_id, 0) >= 5.0:
                self._pos_log_ts[token_id] = now
                held = now - pos.open_ts
                move_pct = (current_price - pos.entry_price) / pos.entry_price * 100
                unreal_pnl = (current_price - pos.entry_price) * pos.remaining_shares
                win_str = "+" if unreal_pnl >= 0 else "-"
                win_emoji = "▲" if unreal_pnl >= 0 else "▼"
                remaining_sec = max(0, pos.window_end_ts - now) if pos.window_end_ts > 0 else 0
                logger.info(
                    "POSITION %s %s %s | entry=%.4f curr=%.4f move=%+.1f%% | "
                    "PnL=%s$%.3f | TP=%.4f SL=%.4f | hold=%ds%s",
                    win_emoji, pos.asset, pos.direction.name,
                    pos.entry_price, current_price, move_pct,
                    win_str, abs(unreal_pnl),
                    pos.tp, pos.sl, int(held),
                    f" | window={remaining_sec:.0f}s" if remaining_sec > 0 else "",
                )

            # ── Post-entry path snapshots (T+30s, T+60s) ─────────────────────
            # Captured once per threshold — used by path classifier at close
            # and by cascade-abort Rule B at T+60s (bond positions only).
            _held_for_snap = now - pos.open_ts
            _snaps = self._entry_snaps.setdefault(token_id, {})
            if 30 not in _snaps and _held_for_snap >= 30:
                _snaps[30] = current_price
                if pos.is_bond and pos.entry_price > 0:
                    pos.entry_snap_30s_pct = round(
                        (current_price - pos.entry_price) / pos.entry_price * 100, 2
                    )
            if 60 not in _snaps and _held_for_snap >= 60:
                _snaps[60] = current_price
                if pos.is_bond and pos.entry_price > 0:
                    pos.entry_snap_60s_pct = round(
                        (current_price - pos.entry_price) / pos.entry_price * 100, 2
                    )

            # ── Trajectory snapshots (T+10s, T+30s, T+60s) for structure_state ──
            # Captures running MFE/MAE at three checkpoints so slope, monotonic
            # expansion, and early-adverse timing can be computed at T+60s.
            _traj_mfe_pos = self._traj_mfe.setdefault(token_id, {})
            _traj_mae_pos = self._traj_mae.setdefault(token_id, {})
            if pos.entry_price > 0:
                _mfe_pct_now = (
                    (pos.highest_price - pos.entry_price) / pos.entry_price * 100
                    if pos.highest_price > pos.entry_price else 0.0
                )
                _mae_pct_now = (
                    (pos.entry_price - pos.lowest_price) / pos.entry_price * 100
                    if pos.lowest_price > 0 and pos.lowest_price < pos.entry_price else 0.0
                )
                for _t_sec in (10, 30, 60):
                    if _t_sec not in _traj_mfe_pos and _held_for_snap >= _t_sec:
                        _traj_mfe_pos[_t_sec] = _mfe_pct_now
                        _traj_mae_pos[_t_sec] = _mae_pct_now

            # ── BOND: time-based exit (bypasses normal TP/SL logic) ──────────
            if pos.is_bond and pos.window_end_ts > 0:
                bond_remaining = max(0.0, pos.window_end_ts - now)
                bond_move = (current_price - pos.entry_price) / pos.entry_price
                _held_s = now - pos.open_ts

                # ── MFE/MAE tracker (needed for close logging) ────────────────
                if bond_move > self._peak_bond_move.get(token_id, -999.0):
                    self._peak_bond_move[token_id] = bond_move
                    self._peak_ts[token_id] = now
                    self._peak_breach_ts.pop(token_id, None)
                elif token_id not in self._peak_ts:
                    self._peak_ts[token_id] = pos.open_ts
                if bond_move < self._trough_bond_move.get(token_id, 999.0):
                    self._trough_bond_move[token_id] = bond_move
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                    pos.highest_price_ts = now - pos.open_ts
                if current_price < pos.lowest_price:
                    pos.lowest_price = current_price
                    pos.lowest_price_ts = now - pos.open_ts
                    pos.mae_bounce_peak = current_price
                    pos.mae_bounce_start_ts = now
                elif (pos.mae_bounce_start_ts > 0
                      and (now - pos.mae_bounce_start_ts) <= 10.0
                      and current_price > pos.mae_bounce_peak):
                    pos.mae_bounce_peak = current_price

                # traj_snaps.jsonl retired 2026-05-09 — subsumed by shadow hold_path table (Phase 2)

                # ── EXIT_SHADOW: bid-depth + velocity rule logger (log-only) ────
                # Records first moment proposed bid-depth or velocity-stall rules
                # would have fired. No position action taken. Output joinable to
                # trades.jsonl via (token_id, ts_open) → logs/exit_shadow.jsonl.
                # Rule A (depth):     best_bid_size < pos.shares * 1.2
                # Rule B (velocity):  rem<60s AND no upward bid progress over 15s
                if bond_remaining <= 90.0 and not self._shadow_fired.get(token_id):
                    _sh_ob = self.feed.get_order_book(token_id)
                    if _sh_ob is not None and _sh_ob.bids:
                        _sh_bid_size = _sh_ob.bids[0][1]
                        _sh_pos_shares = float(getattr(pos, "shares", 0) or 0)
                        _sh_buf = self._shadow_velocity_buf.setdefault(token_id, [])
                        if not _sh_buf or now - _sh_buf[-1][0] >= 1.0:
                            _sh_buf.append((now, current_price))
                            while _sh_buf and now - _sh_buf[0][0] > 20.0:
                                _sh_buf.pop(0)
                        _sh_p15 = next((p for t, p in _sh_buf if now - t >= 14.0), None)
                        _rule_a = _sh_pos_shares > 0 and _sh_bid_size < _sh_pos_shares * 1.2
                        _rule_b = (
                            bond_remaining < 60.0
                            and _sh_p15 is not None
                            and current_price <= _sh_p15
                        )
                        if _rule_a or _rule_b:
                            self._shadow_fired[token_id] = True
                            try:
                                with open(os.path.join("logs", "exit_shadow.jsonl"), "a") as _shf:
                                    _shf.write(json.dumps({
                                        "event": "first_fire",
                                        "ts": round(now, 3),
                                        "token_id": token_id,
                                        "trade_id": getattr(self.analytics, "last_trade_id", None),
                                        "open_ts": round(pos.open_ts, 3),
                                        "asset": pos.asset,
                                        "direction": pos.direction.name,
                                        "entry_price": round(pos.entry_price, 4),
                                        "fire_price": round(current_price, 4),
                                        "fire_rem_s": round(bond_remaining, 1),
                                        "fire_pnl_pct": round(bond_move * 100, 2),
                                        "pos_shares": round(_sh_pos_shares, 2),
                                        "best_bid_size": round(_sh_bid_size, 2),
                                        "depth_ratio": round(_sh_bid_size / _sh_pos_shares, 3) if _sh_pos_shares else None,
                                        "price_15s_ago": round(_sh_p15, 4) if _sh_p15 is not None else None,
                                        "rule_a_depth": _rule_a,
                                        "rule_b_velocity": _rule_b,
                                    }) + "\n")
                            except Exception:
                                pass

                # ── BOND_LOSER_CUT: staged early exit for confirmed losers ──────
                # TERMINAL-only. Fires before T-3 TIME_EXIT to cut deeply-red
                # trades that never showed real green. Two stages:
                #   S1 (rem 20–30s): bid ≤ −10% AND mfe_so_far < 3%
                #   S2 (rem ≤ 20s):  bid ≤ −5%  AND mfe_so_far < 3%
                # Evidence: May 2–7 traj_snaps n=569 matched, precision 70–87%
                # train/test; +$55 / 25% bleed cut on May 5–7 TERMINAL.
                if (pos.bond_entry_class == "TERMINAL"
                        and bond_remaining <= 30.0
                        and token_id not in self._exit_in_progress):
                    _lc_bp = bond_move * 100.0
                    _lc_mfe = (
                        (pos.highest_price - pos.entry_price) / pos.entry_price * 100.0
                        if pos.highest_price > pos.entry_price else 0.0
                    )
                    _lc_fire = False
                    _lc_stage = ""
                    if bond_remaining > 20.0 and _lc_bp <= -10.0 and _lc_mfe < 3.0:
                        _lc_fire = True
                        _lc_stage = "S1_T30"
                    elif bond_remaining <= 20.0 and _lc_bp <= -5.0 and _lc_mfe < 3.0:
                        _lc_fire = True
                        _lc_stage = "S2_T20"
                    if _lc_fire:
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_LOSER_CUT %s/%s | %s rem=%.0fs bp=%+.1f%% mfe=%+.1f%% — early exit",
                            pos.asset, pos.direction.name, _lc_stage,
                            bond_remaining, _lc_bp, _lc_mfe,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_LOSER_CUT")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                # ── Scale-in: smooth runner at T+20-75s ──────────────────────────
                # Trigger: fav ≥ 25% (peak gain from entry), adv < 8% (clean run —
                # no significant wick), drawdown from peak ≤ 20% (still near high).
                # Stake = original stake (same size). One-shot per trade.
                if (False  # SCALE_IN disabled — need n≥100 BOND scale-in samples to evaluate
                        and not pos.scale_in_done
                        and 20.0 <= _held_s <= 75.0
                        and bond_remaining >= 45.0
                        and pos.entry_price > 0
                        and pos.highest_price > pos.entry_price
                        and token_id not in self._exit_in_progress):
                    _si_fav = (pos.highest_price - pos.entry_price) / pos.entry_price
                    _si_adv = (
                        (pos.entry_price - pos.lowest_price) / pos.entry_price
                        if pos.lowest_price < pos.entry_price else 0.0
                    )
                    _si_ddown = (pos.highest_price - current_price) / pos.highest_price
                    if _si_fav >= 0.25 and _si_adv < 0.08 and _si_ddown <= 0.20:
                        _si_stake = pos.stake
                        _tok_si = self.feed.tokens.get(token_id)
                        _neg_risk_si = getattr(_tok_si, "neg_risk", False) if _tok_si else False
                        _tick_si = getattr(_tok_si, "tick_size", "0.01") if _tok_si else "0.01"
                        logger.info(
                            "SCALE_IN_TRIGGER %s/%s | fav=%.1f%% adv=%.1f%% "
                            "ddown_from_high=%.1f%% held=%.0fs stake=$%.2f",
                            pos.asset, pos.direction.name,
                            _si_fav * 100, _si_adv * 100,
                            _si_ddown * 100, _held_s, _si_stake,
                        )
                        try:
                            _si_fill = await self.orders.limit_buy(
                                token_id, current_price, _si_stake,
                                pos.direction,
                                neg_risk=_neg_risk_si,
                                tick_size=_tick_si,
                            )
                            if (_si_fill.status == OrderStatus.FILLED
                                    and _si_fill.total_size > 0):
                                self.risk.add_to_position(
                                    token_id=token_id,
                                    add_shares=_si_fill.total_size,
                                    add_fill_price=_si_fill.avg_fill_price or current_price,
                                    add_stake=_si_stake,
                                )
                                pos.scale_in_done = True
                                logger.info(
                                    "SCALE_IN_FILLED %s/%s | +%.2f shares @ %.4f "
                                    "blended_entry=%.4f",
                                    pos.asset, pos.direction.name,
                                    _si_fill.total_size,
                                    _si_fill.avg_fill_price or current_price,
                                    pos.entry_price,
                                )
                            else:
                                logger.warning(
                                    "SCALE_IN_FAIL %s/%s | status=%s err=%s",
                                    pos.asset, pos.direction.name,
                                    _si_fill.status, _si_fill.error,
                                )
                        except Exception as _si_exc:
                            logger.warning(
                                "SCALE_IN_ERROR %s/%s: %s",
                                pos.asset, pos.direction.name, _si_exc,
                            )

                # ── LLM adaptive exit: re-evaluates every 10s (5s when <60s left) ──
                # Disabled for TERMINAL entries (pure rule-based, exit at window end).
                _poll_interval = 5.0 if bond_remaining < 60.0 else 10.0
                _last_eval = self._llm_exit_last_eval.get(token_id, 0.0)
                _due_for_eval = (
                    self.macro_engine._enabled
                    and token_id not in self._llm_exit_pending
                    and (now - _last_eval) >= _poll_interval
                    and getattr(pos, "bond_entry_class", "") != "TERMINAL"
                    and not getattr(pos, "bond_entry_class", "").startswith("WEATHER_")
                )
                if _due_for_eval:
                    _ext_pos = self._last_ext_signals.get(pos.asset)
                    _pos_delta = 0.0
                    if _ext_pos and _ext_pos.spot_price:
                        _ref5 = _ext_pos.spot_window_open_5m or 0.0
                        if _ref5 > 0:
                            _pos_delta = (_ext_pos.spot_price - _ref5) / _ref5 * 100
                    asyncio.create_task(
                        self._bond_llm_exit_eval(
                            token_id=token_id,
                            pos=pos,
                            current_price=current_price,
                            bond_delta=_pos_delta,
                            vpin=float(getattr(_ext_pos, 'vpin_score', 0.0) or 0.0) if _ext_pos else 0.0,
                            remaining_s=bond_remaining,
                        ),
                        name=f'llm_exit_{pos.asset}_{token_id[:8]}',
                    )

                _exit_dec = self._llm_exit_decisions.pop(token_id, None)
                if _exit_dec and _exit_dec.get('decision') == 'EXIT':
                    if token_id not in self._exit_in_progress:
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            'LLM_EXIT %s/%s conf=%.2f | move=%+.1f%% held=%.0fs rem=%.0fs | %s',
                            pos.asset, pos.direction.name,
                            _exit_dec.get('conf', 0.0), bond_move * 100,
                            _held_s, bond_remaining, _exit_dec.get('reason', ''),
                        )
                        try:
                            await self._exit_position(token_id, current_price, 'LLM_EXIT')
                        finally:
                            self._exit_in_progress.discard(token_id)
                    continue

                # ── Mechanical fallback: honour LLM's own entry targets when API down ─
                # Fires when API key absent OR no successful exit eval in last 30s.
                # Uses the TP/SL absolute prices the LLM set at entry — not new rules.
                _last_good_eval = self._llm_exit_last_eval.get(token_id, 0.0)
                _api_dead = (
                    not self.macro_engine._enabled
                    or (_held_s > 30.0 and (now - _last_good_eval) > 30.0)
                )
                # TERMINAL trail stop active: BOND_TRAIL_TP fires at peak-5% once
                # peak >= +10%. Separate from LLM TP/SL fallback below.
                _is_terminal_pos = getattr(pos, "bond_entry_class", "") == "TERMINAL"

                if (_api_dead
                        and token_id not in self._exit_in_progress
                        and _held_s >= 5.0):
                    _mech_reason: str | None = None
                    if pos.tp > 0 and current_price >= pos.tp and not _is_terminal_pos:
                        _mech_reason = f'price {current_price:.4f} >= tp {pos.tp:.4f}'
                        _mech_label = 'LLM_TP_FALLBACK'
                    elif pos.sl > 0 and current_price <= pos.sl and not _is_terminal_pos and not pos.is_bond:
                        _mech_reason = f'price {current_price:.4f} <= sl {pos.sl:.4f}'
                        _mech_label = 'LLM_SL_FALLBACK'
                    else:
                        _mech_reason = None
                    if _mech_reason:
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            '%s %s/%s | %s | move=%+.1f%% rem=%.0fs',
                            _mech_label, pos.asset, pos.direction.name,
                            _mech_reason, bond_move * 100, bond_remaining,
                        )
                        try:
                            await self._exit_position(token_id, current_price, _mech_label)
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                # ── Safety net 1: catastrophic SL with wick confirmation ─────────
                # 34% of BOND_CATASTROPHIC exits are flash crashes: token recovers
                # to entry within 30s, spot barely moves (+0.002%). Wait 10s before
                # exiting to filter these false stops. Hard bypass at bond_remaining<15s.
                # 8s→10s: 9 of 13 missed recoveries fell at 8.2–9.6s (scan-loop timing
                # artifacts, not genuine slow wicks). 10s catches 49/53 vs 40/53 at 8s.
                # Hold-time wick window: analysis (Apr26+28, n=126) shows BC exits at
                # hold>35s are 70-90% false positives (EV +$0.70-$1.01/trade vs exit).
                # Fast crashes (<15s) are 68% genuine — keep 10s there.
                # Hypothesis confirmed at n<100; monitor bc_hold_bucket in wick_events.jsonl.
                _is_terminal = getattr(pos, "bond_entry_class", "") == "TERMINAL"
                _sl_threshold = -2.0  # BC disabled: -1.0 still fired at move=-1.0 (price→0); -2.0 is truly unreachable (max loss=-1.0)
                if (bond_move <= _sl_threshold
                        and getattr(pos, "bond_entry_class", "") != "LDA"
                        and token_id not in self._exit_in_progress):
                    _breach_ts = self._catas_breach_ts.get(token_id, 0.0)
                    _hold_s_at_breach = now - getattr(pos, "open_ts", now)
                    _bc_hold_bucket = "late" if _hold_s_at_breach > 35.0 else ("fast" if _hold_s_at_breach < 15.0 else "mid")
                    # Depth-aware wick: min_price>0.65→88%FP extend, min_price<0.50→52%FP exit fast (n=70 matched)
                    if _breach_ts > 0:
                        _known_min = self._catas_breach_info.get(token_id, {}).get('min_price', current_price)
                        _depth_ratio = _known_min / pos.entry_price if pos.entry_price > 0 else 1.0
                        if _depth_ratio < 0.60:    # crash >-40%: likely genuine, exit immediately
                            _wick_wait = 0.0
                        elif _depth_ratio > 0.77:  # shallow <-23%: 88% FP, extend wick
                            _wick_wait = 20.0
                        else:
                            _wick_wait = 15.0
                    else:
                        _wick_wait = 15.0          # first breach tick, no depth data yet
                    _hard_bypass = bond_remaining < 10.0   # raised from 15s: bypass was 79% FP (n=29)
                    _already_cancelled = self._catas_cancel_count.get(token_id, 0) >= 1
                    if _hard_bypass or _already_cancelled or (_breach_ts > 0 and (now - _breach_ts) >= _wick_wait):
                        # Confirmed genuine failure (wick_wait elapsed) or deadline/re-breach forcing exit
                        _elapsed = now - _breach_ts if _breach_ts > 0 else 0.0
                        _exit_reason_tag = 'bypass' if _hard_bypass else ('re-breach' if _already_cancelled else f'confirmed {_elapsed:.1f}s')
                        _info = self._catas_breach_info.pop(token_id, {})
                        self._catas_breach_ts.pop(token_id, None)
                        self._catas_cancel_count.pop(token_id, None)
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            'BOND_CATASTROPHIC %s/%s | move=%+.1f%% — %s, force exit',
                            pos.asset, pos.direction.name, bond_move * 100, _exit_reason_tag,
                        )
                        try:
                            with open(os.path.join("logs", "wick_events.jsonl"), "a") as _wf:
                                _wf.write(json.dumps({
                                    "event_type": "WICK_CONFIRM",
                                    "ts": now,
                                    "asset": pos.asset,
                                    "direction": pos.direction.name,
                                    "entry_price": pos.entry_price,
                                    "breach_price": _info.get("breach_price", current_price),
                                    "breach_move_pct": round(_info.get("breach_move_pct", bond_move * 100), 3),
                                    "exit_price": current_price,
                                    "exit_move_pct": round(bond_move * 100, 3),
                                    "min_price_during_wick": _info.get("min_price", current_price),
                                    "elapsed_timer_s": round(_elapsed, 2),
                                    "bond_remaining_at_breach_s": round(_info.get("bond_remaining", bond_remaining), 1),
                                    "was_bypass": _hard_bypass,
                                    "hold_s_at_breach": round(_hold_s_at_breach, 1),
                                    "bc_hold_bucket": _bc_hold_bucket,
                                    "wick_window_s": _wick_wait,
                                    "exit_reason_tag": _exit_reason_tag,
                                }) + "\n")
                            await self._exit_position(token_id, current_price, 'BOND_CATASTROPHIC')
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue
                    else:
                        # First breach or still within wick window — start/continue timer
                        if _breach_ts == 0.0:
                            self._catas_breach_ts[token_id] = now
                            self._catas_breach_info[token_id] = {
                                "breach_price": current_price,
                                "breach_move_pct": round(bond_move * 100, 3),
                                "min_price": current_price,
                                "bond_remaining": bond_remaining,
                                "hold_s_at_breach": round(_hold_s_at_breach, 1),
                                "bc_hold_bucket": _bc_hold_bucket,
                            }
                            # First ARM only — track whether price ever recovers above entry
                            if token_id not in self._bc_arm_tracker:
                                self._bc_arm_tracker[token_id] = {
                                    "arm_ts": now,
                                    "entry_price": pos.entry_price,
                                    "breach_price": current_price,
                                    "breach_move_pct": round(bond_move * 100, 3),
                                    "bc_hold_bucket": _bc_hold_bucket,
                                    "hold_s_at_breach": round(_hold_s_at_breach, 1),
                                    "bond_remaining_at_breach_s": round(bond_remaining, 1),
                                    "asset": pos.asset,
                                    "reversed": False,
                                }
                            logger.info(
                                'BOND_CATASTROPHIC_ARM %s/%s | move=%+.1f%% rem=%.0fs — arming wick timer (%.0fs)',
                                pos.asset, pos.direction.name, bond_move * 100, bond_remaining, _wick_wait,
                            )
                            with open(os.path.join("logs", "wick_events.jsonl"), "a") as _wf:
                                _wf.write(json.dumps({
                                    "event_type": "WICK_ARM",
                                    "ts": now,
                                    "asset": pos.asset,
                                    "direction": pos.direction.name,
                                    "entry_price": pos.entry_price,
                                    "breach_price": current_price,
                                    "breach_move_pct": round(bond_move * 100, 3),
                                    "bond_remaining_at_breach_s": round(bond_remaining, 1),
                                    "hold_s_at_breach": round(_hold_s_at_breach, 1),
                                    "bc_hold_bucket": _bc_hold_bucket,
                                    "wick_window_s": _wick_wait,
                                }) + "\n")
                        else:
                            # Still in timer window — track deepest drop
                            _info = self._catas_breach_info.get(token_id)
                            if _info and current_price < _info.get("min_price", current_price):
                                _info["min_price"] = current_price
                elif bond_move > -0.12 and token_id in self._catas_breach_ts:
                    # Price recovered above -12%: flash crash confirmed, cancel timer.
                    # Track cancel count — second breach skips the timer entirely.
                    _breach_ts_cancel = self._catas_breach_ts.pop(token_id, now)
                    _info = self._catas_breach_info.pop(token_id, {})
                    self._catas_cancel_count[token_id] = self._catas_cancel_count.get(token_id, 0) + 1
                    _recovery_s = round(now - _breach_ts_cancel, 2)
                    logger.info(
                        'BOND_CATASTROPHIC_CANCEL %s/%s | move=%+.1f%% recovered in %.1fs — wick cleared',
                        pos.asset, pos.direction.name, bond_move * 100, _recovery_s,
                    )
                    _hold_s_cancel = now - getattr(pos, "open_ts", now)
                    _bc_hold_bucket_cancel = "late" if _hold_s_cancel > 35.0 else ("fast" if _hold_s_cancel < 15.0 else "mid")
                    with open(os.path.join("logs", "wick_events.jsonl"), "a") as _wf:
                        _wf.write(json.dumps({
                            "event_type": "WICK_CANCEL",
                            "ts": now,
                            "asset": pos.asset,
                            "direction": pos.direction.name,
                            "entry_price": pos.entry_price,
                            "breach_price": _info.get("breach_price", pos.entry_price * (1 + _info.get("breach_move_pct", -15) / 100)),
                            "breach_move_pct": _info.get("breach_move_pct", None),
                            "min_price_during_wick": _info.get("min_price", None),
                            "recovery_price": current_price,
                            "recovery_move_pct": round(bond_move * 100, 3),
                            "recovery_time_s": _recovery_s,
                            "bond_remaining_at_breach_s": round(_info.get("bond_remaining", bond_remaining), 1),
                            "hold_s_at_breach": round(_info.get("hold_s_at_breach", _hold_s_cancel), 1),
                            "bc_hold_bucket": _info.get("bc_hold_bucket", _bc_hold_bucket_cancel),
                        }) + "\n")

                # ── post_bc_reversal_rate check ───────────────────────────────────
                # Tracks whether price recovers above entry after a BC breach.
                # Survives wick cancels — measures the full-recovery rate, not just
                # the -12% wick threshold. Cleared at position exit (not here).
                _arm = self._bc_arm_tracker.get(token_id)
                if _arm and not _arm["reversed"] and current_price >= _arm["entry_price"]:
                    _arm["reversed"] = True
                    _elapsed_to_rev = round(now - _arm["arm_ts"], 1)
                    with open(os.path.join("logs", "wick_events.jsonl"), "a") as _wf:
                        _wf.write(json.dumps({
                            "event_type": "WICK_REVERSAL",
                            "ts": now,
                            "asset": _arm["asset"],
                            "direction": pos.direction.name,
                            "entry_price": _arm["entry_price"],
                            "breach_price": _arm["breach_price"],
                            "breach_move_pct": _arm["breach_move_pct"],
                            "reversal_price": current_price,
                            "elapsed_to_reversal_s": _elapsed_to_rev,
                            "bc_hold_bucket": _arm["bc_hold_bucket"],
                            "hold_s_at_breach": _arm["hold_s_at_breach"],
                            "bond_remaining_at_breach_s": _arm["bond_remaining_at_breach_s"],
                        }) + "\n")

                # BOND_TRAIL_TP disabled — replaced by fixed +10% TP below

                # ── PAE: Persistent Adverse Exit ─────────────────────────────────
                # Exit if bid ≥5% below entry for 20 continuous seconds.
                # Data: t_adv>20s trades WR=29%, net=-$805 (n=623); tokens that stay
                # down after 20s resolve against us 70%+ of the time with no BC SL.
                # Timer only resets if bid recovers above -5% for ≥5s (sustained
                # recovery). Brief pops above threshold don't wipe the clock.
                # Bypass inside T-30s: at T-10s we exit anyway; PAE in the final 30s
                # fires into a thin, depressed bid on windows that still resolve YES.
                # Depth gate: only fire after hold timer with depth ≥ threshold.
                #
                # EARLY-WINDOW BYPASS (ep<0.80, rem>90s):
                # n=83 PAE fires across BTC/ETH/SOL, WR=0%, -$160. COR=65-70%
                # (direction correct; token recovers before resolution). PAE assumes
                # no recovery time — valid for terminal (rem≤90s), wrong here.
                # Resume normal PAE once rem≤90s to protect the terminal zone.
                #
                # Terminal entries (ep>=0.80): thresholds below apply as before.
                #   Term   rem>180s:   20% depth, 40s hold
                #   Term   90-180s:    15% depth, 30s hold
                #   Term   <90s:       12% depth, 20s hold
                _early_window_bypass = pos.entry_price < 0.80 and bond_remaining > 90.0
                if bond_remaining > 180.0:
                    _pae_fire_depth = 0.20
                    _pae_hold_s     = 40.0
                elif bond_remaining > 90.0:
                    _pae_fire_depth = 0.15
                    _pae_hold_s     = 30.0
                else:
                    _pae_fire_depth = 0.12
                    _pae_hold_s     = 20.0
                _pae_depth = -bond_move  # positive = how far below entry
                if False and not _early_window_bypass and bond_remaining > 30.0 and token_id not in self._exit_in_progress:  # PAE disabled
                    if _pae_depth >= 0.05:
                        # Below threshold — start or continue below-timer; clear above-timer
                        self._pae_above_since.pop(token_id, None)
                        if token_id not in self._pae_below_since:
                            self._pae_below_since[token_id] = now
                        elif now - self._pae_below_since[token_id] >= _pae_hold_s:
                            if _pae_depth < _pae_fire_depth:
                                # Shallow confirmation — transient dip, hold position
                                logger.info(
                                    "BOND_PAE %s: shallow %.1f%% (<%.0f%%) after %.0fs — holding"
                                    " | rem=%.0fs",
                                    pos.asset, _pae_depth * 100, _pae_fire_depth * 100,
                                    _pae_hold_s, bond_remaining,
                                )
                            else:
                                _held_below = now - self._pae_below_since[token_id]
                                logger.info(
                                    "BOND_PAE %s: %.0fs below entry | bid=%.4f ep=%.4f"
                                    " (%.1f%% adv) rem=%.0fs thr=%.0f%%",
                                    pos.asset, _held_below, current_price,
                                    pos.entry_price, _pae_depth * 100, bond_remaining,
                                    _pae_fire_depth * 100,
                                )
                                self._exit_in_progress.add(token_id)
                                self._pae_below_since.pop(token_id, None)
                                try:
                                    await self._exit_position(
                                        token_id, current_price, "BOND_PAE"
                                    )
                                finally:
                                    self._exit_in_progress.discard(token_id)
                                continue
                    else:
                        # Above threshold — only reset below-timer after 5s sustained recovery
                        if token_id in self._pae_below_since:
                            if token_id not in self._pae_above_since:
                                self._pae_above_since[token_id] = now
                            elif now - self._pae_above_since[token_id] >= 5.0:
                                self._pae_below_since.pop(token_id, None)
                                self._pae_above_since.pop(token_id, None)
                        else:
                            self._pae_above_since.pop(token_id, None)
                else:
                    # In bypass: clear PAE timers so a stale below-clock can't fire
                    # immediately once rem crosses 90s into the terminal zone.
                    if _early_window_bypass:
                        self._pae_below_since.pop(token_id, None)
                        self._pae_above_since.pop(token_id, None)

                # ── INVERTED_TP: exit at +75% on inverted (low-price) entries ────
                # DISCOVER excluded 2026-05-10: must hold to PT0.95 / T-15 / T-5.
                # LDA excluded 2026-05-13: holds to early-entry T-60/T-50 exits or
                # post-window kline check; entry×1.5 fires too early at low ask (0.63→0.945).
                _inv_tp = pos.entry_price * 1.50
                if (current_price >= _inv_tp
                        and getattr(pos, "bond_entry_class", "") not in ("DISCOVER", "LDA", "VOLARB", "CAS_LOWASK")
                        and not getattr(pos, "bond_entry_class", "").startswith("WEATHER_")
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'INVERTED_TP %s/%s | bid=%.4f ep=%.4f tp=%.4f remaining=%.1fs',
                        pos.asset, pos.direction.name, current_price,
                        pos.entry_price, _inv_tp, bond_remaining,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'INVERTED_TP')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── PROFIT_TARGET: exit at bid ≥ 0.99 ───────────────────────────
                # Raised 0.95→0.99 on 2026-05-11 (user instruction: DISCOVER hold to
                # near-certainty, otherwise time exit only).
                if (current_price >= 0.99
                        and getattr(pos, "bond_entry_class", "") not in ("LDA", "CAS_LOWASK")
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'PROFIT_TARGET %s/%s | bid=%.4f ep=%.4f remaining=%.1fs',
                        pos.asset, pos.direction.name, current_price,
                        pos.entry_price, bond_remaining,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'PROFIT_TARGET')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── BOND_PT95_TIMEOUT: TERMINAL held ≥30s, bid below entry → exit ──
                # Conditional on bid < entry_price (Phase 2 shadow 2026-05-08, n=246):
                # at T+30s, winners (PT_YES/PT_NO) are at +2–6% above entry while
                # losers (MISS_NO) are at −22%. Hard timeout was cutting 55% of PT
                # hitters before they reached 0.95. Conditional preserves those while
                # still dumping positions that are already underwater at T+30s.
                _held_s_pt95 = (now - pos.open_ts) if pos.open_ts > 0 else 0.0
                if (getattr(pos, "bond_entry_class", "") == "TERMINAL"
                        and _held_s_pt95 >= 30.0
                        and current_price < pos.entry_price
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'BOND_PT95_TIMEOUT %s/%s | held=%.1fs bid=%.4f ep=%.4f rem=%.1fs (bid<entry — exiting)',
                        pos.asset, pos.direction.name, _held_s_pt95, current_price,
                        pos.entry_price, bond_remaining,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'BOND_PT95_TIMEOUT')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── Early-entry exits: T-60s sell>0.90 + T-50s unconditional ────
                # Applies when position was entered with >180s remaining (early window).
                # Prevents BOND_EXPIRED_UNSOLD on long-hold positions; captures profit
                # at 0.90 if market hasn't walked to 0.99 yet.
                _is_early_entry = (
                    pos.open_ts > 0
                    and pos.window_end_ts > 0
                    and (pos.window_end_ts - pos.open_ts) > 180.0
                    and getattr(pos, "bond_entry_class", "") not in ("DISCOVER", "LDA", "VOLARB")
                )
                if (_is_early_entry
                        and bond_remaining <= 60.0
                        and current_price > 0.90
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'BOND_TIME_EXIT %s/%s | early T-%.0fs bid=%.4f>0.90 — profit capture',
                        pos.asset, pos.direction.name, bond_remaining, current_price,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'BOND_TIME_EXIT')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue
                if (_is_early_entry
                        and bond_remaining <= 50.0
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'BOND_TIME_EXIT %s/%s | early T-%.0fs unconditional bid=%.4f',
                        pos.asset, pos.direction.name, bond_remaining, current_price,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'BOND_TIME_EXIT')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── LDA universal PT0.95 (May 15 hold-path analysis) ────────────
                # 39 losses peaked ≥0.95 before reversing → save $312 net of $45 win cost.
                # Fires at bid≥0.95 with >15s remaining (last 15s: auto-redemption imminent).
                if (getattr(pos, "bond_entry_class", "") == "LDA"
                        and current_price >= 0.95
                        and bond_remaining > 15.0
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'LDA_PT95 %s/%s | bid=%.4f ep=%.4f rem=%.1fs',
                        pos.asset, pos.direction.name,
                        current_price, pos.entry_price, bond_remaining,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'LDA_PT95')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── LDA per-hour exits (per-hour×bucket analysis 2026-05-15) ────────
                # PT exits: H08+H22 → bid≥0.95; H16 → bid≥0.97 (superseded by universal PT above)
                # Cut exits: H06+H21 → at rem≤60s, bid < entry×0.95 (i.e. down >5%)
                if getattr(pos, "bond_entry_class", "") == "LDA" and pos.window_end_ts > 0:
                    _lda_hour = datetime.fromtimestamp(pos.window_end_ts, tz=timezone.utc).hour
                    _lda_pt   = (
                        (_lda_hour in (8, 22) and current_price >= 0.95)
                        or (_lda_hour == 16    and current_price >= 0.97)
                    )
                    _lda_cut  = (
                        _lda_hour in (6, 21)
                        and bond_remaining <= 60.0
                        and current_price < pos.entry_price * 0.95
                    )
                    if (_lda_pt or _lda_cut) and token_id not in self._exit_in_progress:
                        _lda_exit_reason = (
                            ("LDA_PT97" if _lda_hour == 16 else "LDA_PT95")
                            if _lda_pt else "LDA_CUT60"
                        )
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            '%s %s/%s | bid=%.4f ep=%.4f rem=%.1fs H%02d',
                            _lda_exit_reason, pos.asset, pos.direction.name,
                            current_price, pos.entry_price, bond_remaining, _lda_hour,
                        )
                        try:
                            await self._exit_position(token_id, current_price, _lda_exit_reason)
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                # ── DISCOVER T-5 deadline backup ─────────────────────────────────
                # Primary exit is the T-15 asyncio task in discover_strategy.py.
                # This is a safety net if that task dies (exception, restart).
                # Fires before BOND_DEADLINE T-3 to leave cascade_sell room.
                if (getattr(pos, "bond_entry_class", "") == "DISCOVER"
                        and bond_remaining <= 5.0
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'DISCOVER_DEADLINE %s/%s | remaining=%.1fs — T-5 backup exit bid=%.4f',
                        pos.asset, pos.direction.name, bond_remaining, current_price,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'DISCOVER_DEADLINE')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── T-3s hard gate: unconditional sell ───────────────────────────
                # LDA + VOLARB + CAS_LOWASK excluded: all hold to resolution, Redeemer/kline collect $1.00.
                if (bond_remaining <= 3.0
                        and getattr(pos, "bond_entry_class", "") not in ("LDA", "VOLARB", "CAS_LOWASK")
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'BOND_DEADLINE %s/%s | remaining=%.1fs — T-3s forced exit bid=%.4f',
                        pos.asset, pos.direction.name, bond_remaining, current_price,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'BOND_DEADLINE')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # ── Window outcome: hold to resolution ────────────────────────────
                # Only sell if bid is ≥0.90 — indicates YES resolution is near.
                # A bid of 0.01 means the market is going NO: selling at 0.01
                # destroys a winning position for 1% of payout. Let losers settle
                # at $0 via redemption; winners sell at ~0.99 here.
                if bond_remaining == 0.0 and token_id not in self._exit_in_progress:
                    if current_price < 0.90:
                        elapsed_post = time.time() - pos.window_end_ts if pos.window_end_ts > 0 else 0
                        if current_price < 0.05 and elapsed_post > 60:
                            # LDA: bid=0 post-window for BOTH win and loss (MMs withdraw).
                            # Check kline open vs close to determine actual outcome.
                            _wo_exit_price  = 0.0
                            _wo_exit_reason = "BOND_RESOLVED_NO"
                            _wo_class = getattr(pos, "bond_entry_class", "")
                            if _wo_class in ("LDA", "VOLARB", "CAS_LOWASK") and pos.window_end_ts > 0:
                                try:
                                    import aiohttp as _aiohttp
                                    _sym_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
                                    _sym = _sym_map.get(pos.asset.upper())
                                    _wsz_s = pos.window_seconds or 300
                                    _kl_int = "5m" if _wsz_s == 300 else "15m"
                                    _wstart_ms = int((pos.window_end_ts - _wsz_s) * 1000)
                                    async with self.feed._session.get(
                                        "https://api.binance.com/api/v3/klines",
                                        params={"symbol": _sym, "interval": _kl_int,
                                                "startTime": _wstart_ms, "limit": 1},
                                        timeout=_aiohttp.ClientTimeout(total=5),
                                    ) as _kr:
                                        if _kr.status == 200:
                                            _kl = await _kr.json()
                                            if _kl and len(_kl[0]) >= 5:
                                                _kl_up  = float(_kl[0][4]) >= float(_kl[0][1])
                                                _bet_up = getattr(pos, "bond_outcome_direction", "up") == "up"
                                                if _bet_up == _kl_up:
                                                    _wo_exit_price  = 1.0  # token auto-redeems at $1.00
                                                    if _wo_class == "VOLARB":
                                                        _wo_exit_reason = "VOLARB_KLINE_WIN"
                                                    elif _wo_class == "CAS_LOWASK":
                                                        _wo_exit_reason = "CAS_KLINE_WIN"
                                                    else:
                                                        _wo_exit_reason = "LDA_KLINE_WIN"
                                except Exception:
                                    pass  # fetch failed — default to BOND_RESOLVED_NO
                            logger.info(
                                'WINDOW_OUTCOME %s/%s | bid=%.4f elapsed=%.0fs — %s',
                                pos.asset, pos.direction.name, current_price, elapsed_post,
                                "kline win, booking redemption" if _wo_exit_reason == "LDA_KLINE_WIN"
                                else "resolved NO, booking loss",
                            )
                            _wo_meta = self._open_meta.pop(token_id, {})
                            self._pos_log_ts.pop(token_id, None)
                            _wo_pnl = self.risk.close_position(token_id, _wo_exit_price, _wo_exit_reason)
                            if _wo_exit_reason == "BOND_RESOLVED_NO":
                                self._mark_bond_total_loss(pos.asset)
                            if _wo_pnl is not None:
                                _wo_sig = _wo_meta.get("signal") or SignalBreakdown(
                                    direction=pos.direction, entry_price=pos.entry_price,
                                    composite=0.0, confidence=0.0, breakout_score=0.0,
                                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                    reason="bond_resolved_no",
                                )
                                _wo_snaps = self._entry_snaps.pop(token_id, {})
                                _ep_wo = pos.entry_price
                                _s30_wo = _wo_snaps.get(30, 0.0)
                                _s60_wo = _wo_snaps.get(60, 0.0)
                                _r30_wo = (_s30_wo - _ep_wo) / _ep_wo * 100 if _ep_wo > 0 and _s30_wo > 0 else None
                                _r60_wo = (_s60_wo - _ep_wo) / _ep_wo * 100 if _ep_wo > 0 and _s60_wo > 0 else None
                                _lowest_wo = pos.lowest_price
                                _highest_wo = pos.highest_price
                                _max_adv_wo = ((_ep_wo - _lowest_wo) / _ep_wo * 100) if _ep_wo > 0 and _lowest_wo > 0 else 0.0
                                _hold_s_wo = time.time() - _wo_meta.get("ts_open", pos.open_ts)
                                _path_class_wo, _path_conf_wo, _path_reason_wo = _classify_path(
                                    r30=_r30_wo, r60=_r60_wo, max_adv_pct=_max_adv_wo, hold_s=_hold_s_wo,
                                    exit_reason=_wo_exit_reason, exit_price=_wo_exit_price, entry_price=_ep_wo,
                                )
                                _bounce_pct_wo = 0.0
                                if (pos.entry_price > 0 and pos.mae_bounce_peak > 0
                                        and pos.lowest_price > 0 and pos.mae_bounce_peak > pos.lowest_price):
                                    _bounce_pct_wo = (pos.mae_bounce_peak - pos.lowest_price) / pos.entry_price * 100
                                _bond_llm_wo = self._bond_llm_decisions.pop(token_id, {})
                                _wo_token_meta = self.feed.tokens.get(token_id)
                                _wo_spot_exit = self.feed._spot_price.get(pos.asset.upper(), 0.0)
                                try:
                                    self.analytics.record_trade(
                                        token_id=token_id, asset=pos.asset, direction=pos.direction,
                                        entry_price=pos.entry_price, exit_price=_wo_exit_price,
                                        stake=pos.stake, shares=pos.shares,
                                        entry_fill=_wo_meta.get("entry_fill"), exit_fills=[],
                                        exit_reason=_wo_exit_reason, signal=_wo_sig,
                                        ts_open=_wo_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                                        capital_before=self.risk.bankroll.capital - _wo_pnl,
                                        heat_check_active=_wo_meta.get("heat_check", False),
                                        consecutive_wins=_wo_meta.get("consecutive_wins", 0),
                                        best_ask=pos.best_ask,
                                        net_pnl_actual=_wo_pnl,
                                        market_type=getattr(_wo_token_meta, "market_type", "unknown"),
                                        is_live=not CONFIG.dry_run,
                                        signal_source=_wo_meta.get("signal_source", "BOND"),
                                        window_size_s=_wo_meta.get("window_size_s") or pos.window_seconds or 0,
                                        ob_depth_at_entry=_wo_meta.get("ob_depth_at_entry", 0.0),
                                        pre_entry_momentum_pct=_wo_meta.get("pre_entry_momentum_pct", 0.0),
                                        spot_at_entry=_wo_meta.get("spot_at_entry", 0.0),
                                        spot_at_exit=_wo_spot_exit,
                                        signal_to_fill_ms=_wo_meta.get("signal_to_fill_ms", 0.0),
                                        llm_rec=_wo_meta.get("llm_rec", ""),
                                        llm_rec_conf=_wo_meta.get("llm_rec_conf", 0.0),
                                        max_price_seen=_highest_wo,
                                        min_price_seen=_lowest_wo,
                                        highest_price_ts=pos.highest_price_ts,
                                        lowest_price_ts=pos.lowest_price_ts,
                                        binance_price_at_entry=pos.binance_price_at_entry,
                                        binance_reversal_count_at_exit=pos.binance_reversal_count,
                                        velocity_5s_pct=_wo_meta.get("velocity_5s_pct", 0.0),
                                        move_age_s=_wo_meta.get("move_age_s", 999.0),
                                        path_class=_path_class_wo,
                                        path_confidence=_path_conf_wo,
                                        path_reason=_path_reason_wo,
                                        entry_snap_30s_pct=_r30_wo if _r30_wo is not None else 0.0,
                                        entry_snap_60s_pct=_r60_wo if _r60_wo is not None else 0.0,
                                        bond_entry_class=pos.bond_entry_class,
                                        bond_outcome_direction=getattr(_wo_sig, "bond_outcome_direction", "") or getattr(pos, "bond_outcome_direction", ""),
                                        bond_macro_regime=pos.bond_macro_regime,
                                        mae_bounce_10s_pct=_bounce_pct_wo,
                                        bond_stab_class=getattr(_wo_sig, "bond_stab_class", ""),
                                        bond_stability_score=int(getattr(_wo_sig, "bond_stability_score", 0)),
                                        bond_stab_xp_bad=bool(getattr(_wo_sig, "bond_stab_xp_bad", False)),
                                        bond_stab_slip_bad=bool(getattr(_wo_sig, "bond_stab_slip_bad", False)),
                                        bond_stab_delta_bad=bool(getattr(_wo_sig, "bond_stab_delta_bad", False)),
                                        bond_stab_edge_weak=bool(getattr(_wo_sig, "bond_stab_edge_weak", False)),
                                        bond_stab_vel_flat=bool(getattr(_wo_sig, "bond_stab_vel_flat", False)),
                                        bond_delta_accel_30s=float(getattr(_wo_sig, "bond_delta_accel_30s", 0.0) or 0.0),
                                        bond_accel_15s=float(getattr(_wo_sig, "bond_accel_15s", 0.0) or 0.0),
                                        bond_edge_drift_30s=float(getattr(_wo_sig, "bond_edge_drift_30s", 0.0) or 0.0),
                                        bond_accel_sustained=bool(getattr(_wo_sig, "bond_accel_sustained", False)),
                                        bond_has_hist=bool(getattr(_wo_sig, "bond_has_hist", False)),
                                        bond_smooth_delta_60s=float(getattr(_wo_sig, "bond_smooth_delta_60s", 0.0) or 0.0),
                                        bond_entry_zone=str(getattr(_wo_sig, "bond_entry_zone", "") or ""),
                                        pre_score=float(getattr(_wo_sig, "pre_score", 0.0) or 0.0),
                                        pre_score_version=str(getattr(_wo_sig, "pre_score_version", "") or ""),
                                        pre_score_schema_hash=str(getattr(_wo_sig, "pre_score_schema_hash", "") or ""),
                                        pre_score_validity=str(getattr(_wo_sig, "pre_score_validity", "") or ""),
                                        pre_score_accel=float(getattr(_wo_sig, "pre_score_accel", 0.0) or 0.0),
                                        pre_score_daccel=float(getattr(_wo_sig, "pre_score_daccel", 0.0) or 0.0),
                                        pre_score_edge=float(getattr(_wo_sig, "pre_score_edge", 0.0) or 0.0),
                                        pre_score_stab=float(getattr(_wo_sig, "pre_score_stab", 0.0) or 0.0),
                                        pre_score_vel=float(getattr(_wo_sig, "pre_score_vel", 0.0) or 0.0),
                                        pre_score_class=float(getattr(_wo_sig, "pre_score_class", 0.0) or 0.0),
                                        bond_llm_decision=_bond_llm_wo.get("decision", ""),
                                        bond_llm_conf=float(_bond_llm_wo.get("conf", 0.0)),
                                        bond_llm_reason=_bond_llm_wo.get("reason", ""),
                                        bond_llm_tp_pct=float(_bond_llm_wo.get("shadow_tp_pct", 0.0)),
                                        bond_llm_sl_pct=float(_bond_llm_wo.get("shadow_sl_pct", 0.0)),
                                        term_vpin=float(getattr(_wo_sig, "term_vpin", 0.0) or 0.0),
                                        term_spot_delta_5s=float(getattr(_wo_sig, "term_spot_delta_5s", 0.0) or 0.0),
                                        term_spot_delta_30s=float(getattr(_wo_sig, "term_spot_delta_30s", 0.0) or 0.0),
                                        term_spot_delta_60s=float(getattr(_wo_sig, "term_spot_delta_60s", 0.0) or 0.0),
                                        term_spot_delta_5m=float(getattr(_wo_sig, "term_spot_delta_5m", 0.0) or 0.0),
                                        term_ask_spread_pct=float(getattr(_wo_sig, "term_ask_spread_pct", 0.0) or 0.0),
                                        term_ask_qty=float(getattr(_wo_sig, "term_ask_qty", 0.0) or 0.0),
                                        term_ob_imbalance=float(getattr(_wo_sig, "term_ob_imbalance", 0.0) or 0.0),
                                        term_ob_depth=float(getattr(_wo_sig, "term_ob_depth", 0.0) or 0.0),
                                        term_remaining_s=float(getattr(_wo_sig, "term_remaining_s", 0.0) or 0.0),
                                        term_token_delta_3s=float(getattr(_wo_sig, "term_token_delta_3s", 0.0) or 0.0),
                                        term_token_delta_5s=float(getattr(_wo_sig, "term_token_delta_5s", 0.0) or 0.0),
                                        term_tok_tick_count_5s=int(getattr(_wo_sig, "term_tok_tick_count_5s", 0) or 0),
                                        term_tok_tick_count_30s=int(getattr(_wo_sig, "term_tok_tick_count_30s", 0) or 0),
                                        term_ask_stale_s=float(getattr(_wo_sig, "term_ask_stale_s", 999.0) or 999.0),
                                        term_tok_decel_ratio=float(getattr(_wo_sig, "term_tok_decel_ratio", 0.0) or 0.0),
                                        term_token_delta_30s=float(getattr(_wo_sig, "term_token_delta_30s", 0.0) or 0.0),
                                        term_token_delta_60s=float(getattr(_wo_sig, "term_token_delta_60s", 0.0) or 0.0),
                                        term_binance_1m_pct=getattr(_wo_sig, "term_binance_1m_pct", None),
                                        term_binance_5m_pct=getattr(_wo_sig, "term_binance_5m_pct", None),
                                        term_binance_60m_pct=getattr(_wo_sig, "term_binance_60m_pct", None),
                                        term_pre_snap_60s=float(getattr(_wo_sig, "term_pre_snap_60s", 0.0) or 0.0),
                                        term_pre_snap_30s=float(getattr(_wo_sig, "term_pre_snap_30s", 0.0) or 0.0),
                                        term_pre_snap_open=float(getattr(_wo_sig, "term_pre_snap_open", 0.0) or 0.0),
                                        term_snap60_eff=float(getattr(_wo_sig, "term_snap60_eff", 0.0) or 0.0),
                                        term_snap30_eff=float(getattr(_wo_sig, "term_snap30_eff", 0.0) or 0.0),
                                        term_rsi=float(getattr(_wo_sig, "term_rsi", 0.0) or 0.0),
                                        term_ask_vwap=float(getattr(_wo_sig, "term_ask_vwap", 0.0) or 0.0),
                                        traj_mfe_10s=float(self._traj_mfe.get(token_id, {}).get(10, 0.0)),
                                        traj_mae_10s=float(self._traj_mae.get(token_id, {}).get(10, 0.0)),
                                        traj_mfe_30s=float(self._traj_mfe.get(token_id, {}).get(30, 0.0)),
                                        traj_mae_30s=float(self._traj_mae.get(token_id, {}).get(30, 0.0)),
                                        price_at_t10s=self._price_at_t10s.get(token_id),
                                        extra_fields=_build_weather_extra(
                                            _wo_meta, pos.bond_entry_class, _wo_exit_price,
                                            pos.shares, pos.entry_price, pos.stake, _wo_pnl,
                                        ),
                                    )
                                except Exception as _woe:
                                    logger.error("record_trade BOND_RESOLVED_NO failed: %s", _woe)
                            # Schedule resolution backfill so trades.jsonl gets
                            # entered_correctly + kline_pnl patched. Other exit
                            # paths do this; without it, BOND_RESOLVED_NO and
                            # LDA_KLINE_WIN rows stay unresolved and break WR.
                            _wo_post_kwargs = dict(
                                token_id=token_id,
                                trade_id=self.analytics.last_trade_id,
                                asset=pos.asset,
                                direction=pos.direction.name,
                                exit_price=_wo_exit_price,
                                exit_reason=_wo_exit_reason,
                                entry_price=pos.entry_price,
                                window_end_ts=pos.window_end_ts,
                                binance_price_at_entry=pos.binance_price_at_entry,
                                condition_id=getattr(pos, "condition_id", ""),
                                outcome_direction=getattr(pos, "bond_outcome_direction", "up") or "up",
                            )
                            if pos.window_end_ts > 0:
                                try:
                                    os.makedirs("logs", exist_ok=True)
                                    with open(os.path.join("logs", "pending_resolutions.jsonl"), "a") as _pf:
                                        _pf.write(json.dumps(_wo_post_kwargs) + "\n")
                                except Exception:
                                    pass
                            asyncio.create_task(self._track_post_exit(**_wo_post_kwargs))
                            # Full cleanup — mirrors _exit_position
                            self._dir_rev_count.pop(token_id, None)
                            self._term_pre_snap_refs.pop(token_id, None)
                            self._term_pre_entry_obs.pop(token_id, None)
                            self._sl_below_count.pop(token_id, None)
                            self._stall_checked.discard(token_id)
                            self._peak_bond_move.pop(token_id, None)
                            self._trough_bond_move.pop(token_id, None)
                            self._peak_ts.pop(token_id, None)
                            self._stall_conf_count.pop(token_id, None)
                            self._exhaustion_conf_count.pop(token_id, None)
                            self._early_loss_conf_count.pop(token_id, None)
                            self._peak_breach_ts.pop(token_id, None)
                            self._zombie_flag_ts.pop(token_id, None)
                            self._traj_mfe.pop(token_id, None)
                            self._traj_mae.pop(token_id, None)
                            self._price_at_t10s.pop(token_id, None)
                            self._traj_snap_next.pop(token_id, None)
                            self._bond_sl_arm_ts.pop(token_id, None)
                            self._catas_breach_ts.pop(token_id, None)
                            self._catas_cancel_count.pop(token_id, None)
                            self._pae_below_since.pop(token_id, None)
                            self._pae_above_since.pop(token_id, None)
                            self._bc_arm_tracker.pop(token_id, None)
                            self._terminal_tp_touched.discard(token_id)
                            continue
                        logger.info(
                            'WINDOW_OUTCOME %s/%s | bid=%.4f < 0.90 — likely NO resolution, '
                            'holding for settlement (no sell)',
                            pos.asset, pos.direction.name, current_price,
                        )
                        continue
                    # LDA: always hold — token auto-redeems at $1.00 (win) or $0 (loss).
                    # Never sell via CLOB; BOND_SETTLED kline-check path handles resolution.
                    if getattr(pos, "bond_entry_class", "") == "LDA":
                        continue
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        'WINDOW_OUTCOME %s/%s | window closed bid=%.4f — selling at resolution',
                        pos.asset, pos.direction.name, current_price,
                    )
                    try:
                        await self._exit_position(token_id, current_price, 'WINDOW_OUTCOME')
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # Still holding — LLM said HOLD, next eval in ~10s
                continue


            _pos_ext = self._last_ext_signals.get(pos.asset)
            _binance_spot = self.feed._spot_price.get(pos.asset.upper(), 0.0)
            decision = self.risk.check_exit_conditions(
                token_id, current_price, ext=_pos_ext, binance_spot=_binance_spot
            )

            if decision is None:
                if pos.window_end_ts > 0:
                    time_held = now - pos.open_ts
                    remaining = max(0.0, pos.window_end_ts - now)
                    move_pct = (current_price - pos.entry_price) / pos.entry_price

                    # ── LLM SL-breach override: wick vs genuine reversal ──────
                    # When the SL timer is running but hasn't expired, ask Claude once.
                    # T00042: 0.59→0.44 in 25s (bot-painted stop), price recovered 0.78.
                    # Mechanical timer is blind to this. LLM sees VPIN/spot context.
                    # Guard: skip LLM query on weak entries (edge < 0.06, elapsed < 30%) —
                    # LLM has no signal advantage at 10-22s into a 5m window; let the
                    # mechanical 12s wick timer run without LLM interference. T00090.
                    _meta = self._open_meta.get(token_id, {})
                    _sig = _meta.get("signal")
                    _entry_edge = getattr(_sig, "edge", 1.0) if _sig else 1.0
                    _entry_elapsed = getattr(_sig, "elapsed_pct", 1.0) if _sig else 1.0
                    _weak_entry = _entry_edge < 0.06 and _entry_elapsed < 0.40
                    # Note: if _weak_entry=True, sl_breach_ts stays set → in_uncertain_zone
                    # below cannot fire (guards on sl_breach_ts == 0.0). Intentional: weak
                    # entries in breach are handled by mechanical wick timer only, not LLM.
                    if pos.sl_breach_ts > 0 and not pos.sl_breach_llm_queried and not _weak_entry:
                        pos.sl_breach_llm_queried = True
                        # Bypass stale cache — fresh read on breach
                        self.macro_engine._exit_advice_cache.pop(token_id, None)
                        ext = self._last_ext_signals.get(pos.asset)
                        action, tighten_sl, conf, adv_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                            breach_price=pos.sl_breach_price if pos.sl_breach_price > 0 else None,
                        )
                        if action == "HOLD" and conf >= 0.65:
                            # LLM says wick — reset breach timer, stay in
                            pos.sl_breach_ts = 0.0
                            pos.sl_breach_llm_queried = False  # allow re-query if price dips again
                            logger.info(
                                "LLM WICK OVERRIDE %s/%s (conf=%.2f move=%+.1f%%) — SL breach reset | %s",
                                pos.asset, pos.direction.name, conf, move_pct * 100, adv_reason,
                            )
                        elif action == "EXIT_NOW" and conf >= 0.65:
                            # LLM confirms reversal — but don't bypass wick timer entirely.
                            # T00090: BTC/YES wicked to -27% at 22s, LLM said EXIT_NOW, price
                            # then recovered to +40%. The LLM has almost no signal at 22s.
                            # Fix: LLM vote REDUCES wick confirmation window (12s → 4s for 5m,
                            # 20s → 8s for 15m), but doesn't bypass it. If price recovers
                            # above threshold before the reduced timer expires, the position
                            # is saved — the wick cleared before LLM could do damage.
                            is_5m_pos = pos.window_seconds < 900
                            reduced_confirm = 4 if is_5m_pos else 8
                            breach_age = now - pos.sl_breach_ts
                            if breach_age >= reduced_confirm:
                                logger.info(
                                    "LLM CONFIRMS EXIT %s/%s (conf=%.2f move=%+.1f%% held %.0fs) "
                                    "— breach age %.0fs ≥ %ds | %s",
                                    pos.asset, pos.direction.name, conf, move_pct * 100,
                                    time_held, breach_age, reduced_confirm, adv_reason,
                                )
                                await self._exit_position(token_id, current_price, "LLM_CONFIRMS_SL")
                                continue
                            else:
                                logger.info(
                                    "LLM EXIT_NOW %s/%s but breach only %.0fs old (need %ds) "
                                    "— waiting for wick to clear | %s",
                                    pos.asset, pos.direction.name, breach_age,
                                    reduced_confirm, adv_reason,
                                )
                        else:
                            logger.info(
                                "LLM SL CONSULT %s/%s → %s conf=%.2f — letting timer run | %s",
                                pos.asset, pos.direction.name, action, conf, adv_reason,
                            )

                    # ── LLM exit advisor: DISABLED — observational only ───────
                    # LLM_EXIT_NOW caused early exits at loss (T00153: -$0.894, T00157: -$0.648).
                    # Same pattern as entry veto: LLM hurts more than helps.
                    # Tracking recommendations vs outcomes for future validation.
                    is_15m_trade = pos.window_seconds >= 900
                    llm_min_hold = 180 if is_15m_trade else 15
                    in_uncertain_zone = (
                        time_held > llm_min_hold
                        and -0.35 < move_pct < 0.22
                        and remaining > 60
                        and pos.exit_stage.name == "NONE"
                        and pos.sl_breach_ts == 0.0  # breach handled above
                    )
                    if in_uncertain_zone:
                        ext = self._last_ext_signals.get(pos.asset)
                        action, tighten_sl, conf, adv_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                        )
                        if action == "EXIT_NOW":
                            logger.info(
                                "LLM WOULD-EXIT %s/%s (conf=%.2f move=%+.1f%%) — tracking only | %s",
                                pos.asset, pos.direction.name,
                                conf, move_pct * 100, adv_reason,
                            )
                        elif action == "TIGHTEN_STOP" and tighten_sl is not None:
                            logger.info(
                                "LLM WOULD-TIGHTEN %s/%s → -%.0f%% (conf=%.2f) — tracking only | %s",
                                pos.asset, pos.direction.name,
                                tighten_sl * 100, conf, adv_reason,
                            )

                    # ── LLM stage-2 advisor: DISABLED — observational only ───
                    # Same rationale as exit advisor above: tracking only, no stops tightened.
                    if (pos.exit_stage.name == "STAGE_1_DONE"
                            and time_held > 15
                            and 0.15 < move_pct < 0.45
                            and remaining > 60
                            and pos.sl_breach_ts == 0.0):
                        ext = self._last_ext_signals.get(pos.asset)
                        s2_action, s2_tighten, s2_conf, s2_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake * 0.40,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                        )
                        logger.info(
                            "LLM STAGE2 WOULD-%s %s/%s (conf=%.2f move=%+.1f%%) — tracking only | %s",
                            s2_action, pos.asset, pos.direction.name,
                            s2_conf, move_pct * 100, s2_reason,
                        )

                # ── T+30s: zombie candidate flag (snapshot — loser detection) ──
                # Kept snapshot-based: detecting losers at T+30s only needs the
                # current MFE and snap30. Trajectory structure is evaluated at
                # T+60s once enough history exists for slope computation.
                _z_hold = now - pos.open_ts
                _z_snap30 = self._entry_snaps.get(token_id, {}).get(30, 0.0)
                _z_mfe_pct = (
                    (pos.highest_price - pos.entry_price) / pos.entry_price * 100
                    if pos.entry_price > 0 and pos.highest_price > pos.entry_price
                    else 0.0
                )
                _open_meta_t = self._open_meta.setdefault(token_id, {})

                if (
                    _z_hold >= 30.0
                    and _z_snap30 > 0
                    and pos.entry_price > 0
                    and not pos.is_bond
                    and token_id not in self._zombie_flag_ts
                ):
                    _z_snap30_pct = (_z_snap30 - pos.entry_price) / pos.entry_price * 100
                    if _z_mfe_pct < 3.0 and _z_snap30_pct < 5.0:
                        self._zombie_flag_ts[token_id] = now
                        logger.info(
                            "ZOMBIE_CANDIDATE %s/%s | hold=%.0fs snap30=%+.2f%% mfe=%.2f%%",
                            pos.asset, pos.direction.name,
                            _z_hold, _z_snap30_pct, _z_mfe_pct,
                        )

                # ── Zombie Stage 2: confirm + exit at T+50s (MAE > 25%) ────────
                if (
                    token_id in self._zombie_flag_ts
                    and _z_hold >= 50.0
                    and pos.entry_price > 0
                    and token_id not in self._exit_in_progress
                ):
                    _z_mae_pct = (
                        (pos.entry_price - pos.lowest_price) / pos.entry_price * 100
                        if pos.lowest_price > 0 else 0.0
                    )
                    _z_bounce_pct = (
                        (pos.mae_bounce_peak - pos.lowest_price) / pos.lowest_price * 100
                        if pos.lowest_price > 0 and pos.mae_bounce_peak > pos.lowest_price
                        else 0.0
                    )
                    _z_snap30_pct = (
                        (_z_snap30 - pos.entry_price) / pos.entry_price * 100
                        if _z_snap30 > 0 else 0.0
                    )
                    if _z_mfe_pct >= 10.0:
                        self._zombie_flag_ts.pop(token_id, None)  # runner — clear flag
                    elif (
                        _z_mfe_pct < 5.0
                        and _z_mae_pct > 25.0
                        and _z_bounce_pct < 8.0
                    ):
                        _z_pnl_est = (current_price - pos.entry_price) * pos.remaining_shares
                        logger.info(
                            "ZOMBIE_EARLY_EXIT %s/%s | hold=%.0fs snap30=%+.2f%% "
                            "mfe=%.2f%% mae=%.2f%% bounce=%.2f%% PnL≈$%+.3f",
                            pos.asset, pos.direction.name,
                            _z_hold, _z_snap30_pct, _z_mfe_pct,
                            _z_mae_pct, _z_bounce_pct, _z_pnl_est,
                        )
                        self._zombie_flag_ts.pop(token_id, None)
                        self._exit_in_progress.add(token_id)
                        try:
                            await self._exit_position(token_id, current_price, "ZOMBIE_EARLY_EXIT")
                        finally:
                            self._exit_in_progress.discard(token_id)

                # ── T+60s: trajectory-based structure_state classification ────
                # Uses MFE/MAE snapshots at T=10, 30, 60 to classify the trade's
                # structural trajectory (not a risk score — a trajectory type).
                #
                #   structure_state ∈ {RUNNER, NEUTRAL, DEAD_DRIFT}
                #
                # RUNNER     = mfe_60 ≥ 5% AND mfe expanding AND no early adverse
                # DEAD_DRIFT = delayed-decay pattern: flat MFE + gradual MAE
                #              accumulation + no bounce formation
                # NEUTRAL    = everything else (includes early-collapse cases
                #              already handled by ZOMBIE_EARLY_EXIT / SL logic)
                #
                # runner_confidence is TRAJECTORY-BASED:
                #   slope_score × expansion_score × (1 − early_adverse_penalty)
                # No snapshot-only heuristics.
                #
                # DEAD_DRIFT_EXIT fires only when structure_state == DEAD_DRIFT
                # and MAE < 15% (excludes losers routed via ZOMBIE_EARLY_EXIT).
                _traj_mfe_map = self._traj_mfe.get(token_id, {})
                _traj_mae_map = self._traj_mae.get(token_id, {})
                if (
                    _z_hold >= 60.0
                    and pos.entry_price > 0
                    and not pos.is_bond
                    and "structure_state" not in _open_meta_t
                    and 10 in _traj_mfe_map and 30 in _traj_mfe_map and 60 in _traj_mfe_map
                ):
                    mfe_10, mfe_30, mfe_60 = (
                        _traj_mfe_map[10], _traj_mfe_map[30], _traj_mfe_map[60]
                    )
                    mae_10, mae_30, mae_60 = (
                        _traj_mae_map[10], _traj_mae_map[30], _traj_mae_map[60]
                    )
                    mfe_slope = (mfe_60 - mfe_10) / 50.0     # %/s over 50s window
                    bounce_pct = (
                        (pos.mae_bounce_peak - pos.lowest_price) / pos.lowest_price * 100
                        if pos.lowest_price > 0 and pos.mae_bounce_peak > pos.lowest_price
                        else 0.0
                    )

                    is_runner = (
                        mfe_60 >= 5.0
                        and mfe_slope > 0.05            # expanding MFE
                        and mfe_60 > mfe_30             # still growing second half
                        and mae_10 < 3.0                # no early adverse spike
                    )
                    is_dead_drift = (
                        mfe_60 < 3.0
                        and mfe_slope <= 0.01           # flat/decaying
                        and mae_60 > mae_30             # MAE still accumulating
                        and mae_30 > mae_10             # gradual, not early spike
                        and bounce_pct < 3.0            # no recovery formed
                    )
                    if is_runner:
                        structure_state = "RUNNER"
                    elif is_dead_drift:
                        structure_state = "DEAD_DRIFT"
                    else:
                        structure_state = "NEUTRAL"

                    _slope_score = min(1.0, max(0.0, mfe_slope / 0.1))
                    _expansion_score = 1.0 if (mfe_60 > mfe_30 > mfe_10) else 0.0
                    _early_adv_pen = min(1.0, max(0.0, mae_10 / 8.0))
                    runner_conf = round(
                        max(0.0, (0.6 * _slope_score + 0.4 * _expansion_score))
                        * (1.0 - _early_adv_pen),
                        3,
                    )

                    # Scaling tier — hard lock on DEAD_DRIFT, target multiplier
                    # for RUNNER. Total stake target = base × multiplier; add-on
                    # capital = (multiplier − 1) × base. One-shot: structure_state
                    # presence in _open_meta gates re-evaluation.
                    if structure_state == "DEAD_DRIFT":
                        _scale_mult = 1.0
                    elif structure_state == "RUNNER" and runner_conf > 0.90:
                        _scale_mult = 2.0
                    elif structure_state == "RUNNER" and runner_conf > 0.75:
                        _scale_mult = 1.5
                    else:
                        _scale_mult = 1.0
                    scale_tier = f"{_scale_mult:.1f}x"

                    _open_meta_t["structure_state"] = structure_state
                    _open_meta_t["runner_conf"] = runner_conf
                    logger.info(
                        "STRUCTURE %s/%s | state=%-10s conf=%.3f scale=%s | "
                        "mfe[10/30/60]=%.1f/%.1f/%.1f%% mae[10/30/60]=%.1f/%.1f/%.1f%% "
                        "slope=%+.3f%%/s bounce=%.1f%%",
                        pos.asset, pos.direction.name,
                        structure_state, runner_conf, scale_tier,
                        mfe_10, mfe_30, mfe_60, mae_10, mae_30, mae_60,
                        mfe_slope, bounce_pct,
                    )

                    # ── Mid-trade scale-up execution (RUNNER only) ────────────
                    # Places an additional market_buy worth (mult − 1) × base
                    # stake. On fill, risk.add_to_position() merges shares with a
                    # share-weighted blended entry_price. TP/SL absolute prices
                    # are kept unchanged — runner thesis assumes price keeps
                    # moving toward original TP. Fail-soft: any error leaves the
                    # original position intact and untouched.
                    if (
                        _scale_mult > 1.0
                        and "scaled" not in _open_meta_t
                        and token_id in self.risk.open_positions
                        and token_id not in self._exit_in_progress
                    ):
                        _add_stake = round(pos.stake * (_scale_mult - 1.0), 2)
                        _ob_scale = self.feed.get_order_book(token_id)
                        _ask_scale = (
                            _ob_scale.asks[0][0] if _ob_scale and _ob_scale.asks else 0.0
                        )
                        if _ask_scale > 0 and _add_stake >= 1.0:
                            _tok_meta = self.feed.tokens.get(token_id)
                            _neg_risk = getattr(_tok_meta, "neg_risk", False) if _tok_meta else False
                            _tick_size = getattr(_tok_meta, "tick_size", "0.01") if _tok_meta else "0.01"

                            _open_meta_t["scaled"] = True
                            logger.info(
                                "RUNNER_SCALE_ATTEMPT %s/%s | conf=%.3f tier=%s | "
                                "add_stake=$%.2f @ ask=%.4f | base_stake=$%.2f",
                                pos.asset, pos.direction.name,
                                runner_conf, scale_tier,
                                _add_stake, _ask_scale, pos.stake,
                            )
                            try:
                                _scale_fill = await self.orders.market_buy(
                                    token_id=token_id,
                                    intended_price=_ask_scale,
                                    stake_usd=_add_stake,
                                    direction=pos.direction,
                                    neg_risk=_neg_risk,
                                    tick_size=_tick_size,
                                )
                                if (
                                    _scale_fill is not None
                                    and getattr(_scale_fill, "status", None) == OrderStatus.FILLED
                                    and getattr(_scale_fill, "total_size", 0) > 0
                                    and getattr(_scale_fill, "avg_fill_price", 0) > 0
                                ):
                                    self.risk.add_to_position(
                                        token_id=token_id,
                                        add_shares=_scale_fill.total_size,
                                        add_fill_price=_scale_fill.avg_fill_price,
                                        add_stake=_add_stake,
                                    )
                                else:
                                    logger.warning(
                                        "RUNNER_SCALE_FAIL %s/%s | status=%s size=%.4f price=%.4f — "
                                        "position unchanged",
                                        pos.asset, pos.direction.name,
                                        getattr(_scale_fill, "status", "?"),
                                        getattr(_scale_fill, "total_size", 0.0),
                                        getattr(_scale_fill, "avg_fill_price", 0.0),
                                    )
                            except Exception as _scale_exc:
                                logger.error(
                                    "RUNNER_SCALE_ERROR %s/%s — %s",
                                    pos.asset, pos.direction.name, _scale_exc,
                                    exc_info=True,
                                )

                    # DEAD_DRIFT_EXIT — structure-based trigger
                    if (
                        structure_state == "DEAD_DRIFT"
                        and mae_60 < 15.0
                        and token_id in self.risk.open_positions
                        and token_id not in self._exit_in_progress
                    ):
                        _dd_pnl_est = (current_price - pos.entry_price) * pos.remaining_shares
                        logger.info(
                            "DEAD_DRIFT_EXIT %s/%s | hold=%.0fs mfe_60=%.2f%% mae_60=%.2f%% "
                            "slope=%+.3f%%/s bounce=%.2f%% PnL≈$%+.3f",
                            pos.asset, pos.direction.name,
                            _z_hold, mfe_60, mae_60, mfe_slope, bounce_pct, _dd_pnl_est,
                        )
                        self._exit_in_progress.add(token_id)
                        try:
                            await self._exit_position(token_id, current_price, "DEAD_DRIFT_EXIT")
                        finally:
                            self._exit_in_progress.discard(token_id)
                continue

            if token_id in self._exit_in_progress:
                continue  # cascade already running for this token — skip to avoid concurrent sells
            if decision.partial:
                # Stage-1: sell 95 %, leave 5 % riding
                self._exit_in_progress.add(token_id)
                try:
                    await self._partial_exit(token_id, current_price, decision.reason)
                finally:
                    self._exit_in_progress.discard(token_id)
            else:
                self._exit_in_progress.add(token_id)
                try:
                    await self._exit_position(token_id, current_price, decision.reason)
                finally:
                    self._exit_in_progress.discard(token_id)

        # ── LLM independent trader: shadow position monitoring ────────────────
        # Check every open LLM shadow position against current OB price.
        # Exits on TP hit, SL hit, or window close — exactly like a real position.
        _now_ts = time.time()
        for _sid, _spos in list(self._llm_shadow_positions.items()):
            _sob = self.feed.get_order_book(_sid)
            _sbid = _sob.bids[0][0] if (_sob and _sob.bids) else 0.0
            if _sbid <= 0:
                continue
            _stp  = _spos["entry_price"] * (1.0 + _spos["tp_pct"] / 100.0)
            _ssl  = _spos["entry_price"] * (1.0 - _spos["sl_pct"] / 100.0)
            _srem = _spos["window_end_ts"] - _now_ts

            _sexit_reason = None
            _sexit_price  = _sbid
            if _sbid >= _stp:
                _sexit_reason = "LLM_TP"
                _sexit_price  = _stp
            elif _sbid <= _ssl:
                _sexit_reason = "LLM_SL"
                _sexit_price  = _ssl
            elif _srem <= 30:
                _sexit_reason = "LLM_TIME"

            if _sexit_reason:
                del self._llm_shadow_positions[_sid]
                _sshares  = _spos["stake"] / _spos["entry_price"] if _spos["entry_price"] > 0 else 0
                _spnl     = round((_sexit_price - _spos["entry_price"]) * _sshares, 4)
                _shold    = round(_now_ts - _spos["entry_ts"], 1)
                logger.info(
                    "LLM_IND EXIT %s/%s %s | entry=%.3f exit=%.3f pnl=%+.3f hold=%.0fs",
                    _spos["asset"], _spos["direction"], _sexit_reason,
                    _spos["entry_price"], _sexit_price, _spnl, _shold,
                )
                self._write_llm_shadow({
                    "record_type": "llm_exit",
                    "ts": _now_ts,
                    "token_id": _sid,
                    "asset": _spos["asset"],
                    "direction": _spos["direction"],
                    "exit_reason": _sexit_reason,
                    "entry_price": _spos["entry_price"],
                    "exit_price": round(_sexit_price, 4),
                    "hold_seconds": _shold,
                    "shadow_gross_pnl": _spnl,
                    "stake": _spos["stake"],
                    "tp_pct": _spos["tp_pct"],
                    "sl_pct": _spos["sl_pct"],
                    "zone": _spos.get("zone", ""),
                    "llm_conf": _spos["conf"],
                    "llm_reason": _spos.get("reason", ""),
                })

    # ── 5-second signal loop: scan for new entries ────────────────────────────

    async def _on_delta_spike(self, asset: str, delta_pct: float, spot_price: float) -> None:
        """
        Event-driven entry: fires immediately from Binance aggTrade when delta
        vs 5m window open crosses 0.03%. Bypasses the 5s signal sweep cycle.

        Flow: aggTrade tick → delta threshold → this callback → sniper.score()
              → risk.evaluate() → _enter_position() if approved.
        PM OB is served from the 1s REST cache — at most 1s stale, still 4s ahead
        of the sweep cycle. The sniper's own gates (lag, edge, elapsed) filter quality.
        """
        if not SNIPER_ENABLED:
            return
        now = time.time()
        # Hour gates removed — all UTC hours permitted.

        # Per-asset debounce — feeds.py debounces at 1.5s, this adds a session-level guard.
        # Timestamp set BEFORE the guard check to prevent two concurrent callbacks both
        # passing when they arrive within the same event loop tick.
        last = self._last_spike_ts.get(asset, 0)
        self._last_spike_ts[asset] = now
        if now - last < 1.5:
            return

        logger.info(
            "SPIKE %s | delta=%+.3f%% price=%.2f — immediate sniper eval",
            asset, delta_pct, spot_price,
        )

        ext = self._last_ext_signals.get(asset)
        if ext is None:
            # Fall back to a fresh fetch if not yet cached
            try:
                ext = await self.feed.fetch_external_signals(asset)
            except Exception as _e:
                logger.warning("SPIKE %s | ext signal fetch failed: %s — spike skipped", asset, _e)
                return
        if ext is None:
            return

        _queued_this_spike: set = set()  # condition dedup within this spike

        for token_id, token in list(self.feed.tokens.items()):
            if token.asset != asset or token.market_type != "updown":
                continue
            if token_id in self.risk.open_positions:
                continue
            # Pre-evaluate check: skip if asset is already locked by a concurrent
            # entry path (spike or scan loop). evaluate() has this check too, but
            # an early guard here prevents the evaluate() call entirely — cleaner
            # and eliminates any edge case where the lock state changes mid-loop.
            if asset in self.risk._pending_assets:
                logger.debug(
                    "SPIKE SKIP %s — asset already in _pending_assets (concurrent entry in progress)",
                    asset,
                )
                break  # no point checking other tokens for this asset
            if asset in self._pending_asset_entries:
                logger.debug(
                    "SPIKE SKIP %s — asset already in _pending_asset_entries",
                    asset,
                )
                break
            if token.window_end_ts > 0:
                remaining = token.window_end_ts - now
                if remaining < CONFIG.execution.no_trade_last_sec:
                    continue

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            _ask = ob.asks[0][0] if ob.asks else ob.mid
            if _ask < 0.05 or _ask > 0.95:
                continue

            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            sniper_sig = self.sniper.score(token, ob, ext, now=time.time())
            if sniper_sig is None:
                continue
            if sniper_sig.entry_price <= 0:
                continue

            # ── Velocity gate (event-driven path) ────────────────────────────
            # Mirrors the gate in _signal_loop. Without this, aggTrade-triggered
            # entries bypass velocity filtering entirely — confirmed root cause of
            # vel=+0.050% NO trade firing at 14:35 (VELOCITY_EXIT -$6.08).
            _vel_spike, _ = self.feed.get_velocity_5s(token.asset)
            _VEL_THRESHOLD_SPIKE = 0.001
            _vel_against_spike = (
                (token.side == "NO"  and _vel_spike >  _VEL_THRESHOLD_SPIKE) or
                (token.side == "YES" and _vel_spike < -_VEL_THRESHOLD_SPIKE)
            )
            if _vel_against_spike:
                logger.info(
                    "SPIKE VELOCITY_GATE %s/%s | vel=%+.4f%% against direction — skip",
                    token.asset, token.side, _vel_spike,
                )
                continue

            _cid = token.condition_id or ""
            if _cid and _cid in _queued_this_spike:
                continue

            tpsl = calculate_tp_sl(sniper_sig.entry_price, sniper_sig.direction, bars_5m, ob)
            decision = self.risk.evaluate(
                token_id, sniper_sig, tpsl,
                condition_id=_cid,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=0.0,
                is_sniper=True,
                window_seconds=getattr(token, "window_seconds", 0),
            )

            if not decision.approved:
                logger.debug("SPIKE REJECTED %s/%s: %s", token.asset, token.side, decision.reason)
                continue

            if token_id in self._exit_in_progress:
                continue

            logger.info(
                "SPIKE ENTRY %s/%s | entry=%.4f edge=%.3f lag=%.0f%% | %s",
                token.asset, token.side,
                sniper_sig.entry_price, sniper_sig.edge,
                sniper_sig.lag_remaining_pct * 100,
                sniper_sig.reason,
            )

            if _cid:
                _queued_this_spike.add(_cid)

            asyncio.create_task(
                self._enter_position(token_id, token.asset, sniper_sig, tpsl, decision),
                name=f"spike_{asset}_{token.side}",
            )

    async def _refresh_ext_signals(self) -> None:
        """Fetch Binance ext signals for all tracked assets and cache in _last_ext_signals.
        Called every signal loop iteration regardless of SNIPER_ENABLED so BOND scanner
        always has delta data (BOND skip 'delta unavailable' when SNIPER disabled)."""
        ext_results = await asyncio.gather(
            *[self.feed.fetch_external_signals(a) for a in CONFIG.markets.tracked_assets],
            return_exceptions=True,
        )
        self._last_ext_signals = {
            asset: (r if not isinstance(r, Exception) else None)
            for asset, r in zip(CONFIG.markets.tracked_assets, ext_results)
        }

    async def _signal_loop(self) -> None:
        _consecutive_errors = 0
        _entries_blocked = False
        while self._running:
            try:
                await self.feed.poll_order_books()
                await self.feed.update_bars()
                await self._refresh_ext_signals()
                if _entries_blocked:
                    logger.info("Signal loop recovered — entries unblocked")
                    _entries_blocked = False
                _consecutive_errors = 0  # reset on success
                await self._scan_for_signals()
                try:
                    await self._scan_bond_entries()
                except Exception as _bond_exc:
                    logger.error(
                        "BOND SCAN LOOP ERROR (isolated) — bond scan skipped this cycle: %s",
                        _bond_exc, exc_info=True,
                    )
                # Phase 2 Discovery live entry path. Internally gated off via
                # self.discover_strategy.enabled = False; this is a no-op until
                # explicitly enabled. Isolated try/except so a bug in the
                # discover path can never block BOND or sniper signals.
                try:
                    await self.discover_strategy.scan()
                except Exception as _disc_exc:
                    logger.error(
                        "DISCOVER SCAN ERROR (isolated): %s",
                        _disc_exc, exc_info=True,
                    )
                # crypto_arb disabled 2026-05-21
                await self._scan_reversal_candidates()
                if self.research_agent.due():
                    asyncio.create_task(
                        self.research_agent.run(self.feed.tokens),
                        name="research_agent_cycle",
                    )
            except Exception as exc:
                _consecutive_errors += 1
                tb = traceback.format_exc()
                if _consecutive_errors > 3:
                    if not _entries_blocked:
                        logger.critical(
                            "Signal loop CRITICAL: %d consecutive errors — entries BLOCKED. "
                            "Last error: %s\n%s",
                            _consecutive_errors, exc, tb,
                        )
                        _entries_blocked = True
                    # Skip _scan_for_signals when data pipeline is broken
                else:
                    logger.error("Signal loop error: %s\n%s", exc, tb)
            await asyncio.sleep(CONFIG.markets.scan_interval)

    # ── High-probability bond scanner ────────────────────────────────────────

    async def _scan_bond_entries(self) -> None:
        """
        Bond strategy: buy high-probability tokens near window close, exit by time.

        15m windows: buy when ask ≥ 0.66 AND remaining ≤ 4 min, sell at T-30s.
        5m windows:  buy when ask ≥ 0.66 AND remaining ≤ 1.5 min, sell at T-20s.

        Edge: token at 0.70+ has already committed to an outcome. Capture final
        repricing walk to ~1.0 as window closes. Works in quiet/trending markets;
        prior losses were in high-volatility bearish conditions.
        """
        if not BOND_ENABLED:
            logger.debug("[BOND] disabled — skipping")
            return
        now = time.time()
        _utc_t    = time.gmtime(now)
        _utc_hour = _utc_t.tm_hour
        _utc_min  = _utc_t.tm_min
        _b_total = _b_in_window = _b_ask_skip = _b_fired = _b_mom_skip = 0
        # Purge expired window keys (window ended > 120s ago)
        self._terminal_traded_windows = {
            (a, wt) for a, wt in self._terminal_traded_windows if wt > now - 120
        }
        logger.debug("[BOND] scan entered — %d tokens tracked", len(self.feed.tokens))

        for token_id, token in list(self.feed.tokens.items()):
          try:
            if token.market_type != "updown":
                continue
            if token.window_end_ts <= 0:
                continue
            # Record ask price history for pre-entry trajectory (all updown tokens, every scan)
            _ob_hist = self.feed.get_order_book(token_id)
            if _ob_hist and _ob_hist.asks:
                _ask_now = _ob_hist.asks[0][0]
                if token_id not in self._token_ask_history:
                    self._token_ask_history[token_id] = deque(maxlen=200)
                self._token_ask_history[token_id].append((now, _ask_now))
                # Window-anchored pre-entry snap references: capture ask at fixed
                # remaining thresholds (150s, 120s, 90s) once per threshold per window.
                _remaining_now = token.window_end_ts - now
                _snap_refs = self._term_pre_snap_refs.setdefault(token_id, {})
                for _thresh in (150, 120, 90):
                    if _thresh not in _snap_refs and _remaining_now <= _thresh:
                        _snap_refs[_thresh] = _ask_now
                # Pre-entry RSI + VWAP: frozen once at remaining≤90s (entry zone opens)
                _pre_obs = self._term_pre_entry_obs.setdefault(token_id, {})
                if "rsi" not in _pre_obs and _remaining_now <= 90:
                    _hist_rsi = self._token_ask_history.get(token_id)
                    _pre_rsi = 0.0
                    if _hist_rsi and len(_hist_rsi) >= 2:
                        _rp = [p for _, p in _hist_rsi]
                        _rc = [_rp[i+1] - _rp[i] for i in range(len(_rp)-1)]
                        _rg = [max(c, 0.0) for c in _rc]
                        _rl = [abs(min(c, 0.0)) for c in _rc]
                        _rag = sum(_rg) / len(_rg)
                        _ral = sum(_rl) / len(_rl)
                        _pre_rsi = round(100.0 - 100.0 / (1.0 + _rag / _ral), 2) if _ral > 0 else 100.0
                    _pre_vwap = 0.0
                    if _ob_hist and _ob_hist.asks:
                        _vt = sum(sz for _, sz in _ob_hist.asks)
                        if _vt > 0:
                            _pre_vwap = round(sum(px * sz for px, sz in _ob_hist.asks) / _vt, 4)
                    _pre_obs["rsi"] = _pre_rsi
                    _pre_obs["vwap"] = _pre_vwap
            if token_id in self.risk.open_positions:
                continue
            # 2026-05-07 user instruction: 2 BOND positions max concurrent (across all assets)
            if sum(1 for p in self.risk.open_positions.values() if p.is_bond) >= 2:
                continue
            if any(p.asset == token.asset and p.is_bond for p in self.risk.open_positions.values()):
                continue  # already holding this asset in a different window
            if token.asset in self.risk._pending_assets:
                continue
            if token.asset in self._pending_asset_entries:
                continue
            _b_total += 1

            # Hour blocks: ALL UNBLOCKED 2026-05-02 (user instruction — accumulate fresh data).
            # Prior blocked set for reference: {0, 2, 3, 4, 5, 6, 7, 17, 19, 23}
            # Prior minute blocks for reference:
            #   14:45–15:45 UTC (PF=0.32-0.43 n=112, 15min analysis 2026-05-01)
            #   16:55–17:00 UTC (tail of H16 into blocked H17)
            # Evidence behind prior blocks:
            #   H02 PF=0.19 | H05 PF=0.21 | H03 WR=14.3% | H00+H23 user-instructed
            #   H04/H06/H07/H17/H19: no gate produces PF≥1 (48h WOP+PAE sim 2026-05-01)
            # Re-block only at n≥100 per hour in current terminal era.

            _wkey = (token.asset, round(token.window_end_ts))
            if _wkey in self._terminal_traded_windows:
                continue  # already traded this asset in this window

            _window_s = getattr(token, "window_seconds", 0)
            if not (250 <= _window_s < 900):
                continue  # 5m only

            remaining = token.window_end_ts - now
            if remaining <= 25:
                continue  # enter with >25s remaining; 15-25s WR=20% (n=5)
            if remaining > 90:
                continue  # TERMINAL zone only — skip early window entries (rem>90s)
            if _utc_hour == 21 and remaining > 60:
                continue  # H21: rem cap 60s (n=78 TERMINAL, rem<=60 saves +$61 net vs baseline)
            _bond_blocked = getattr(CONFIG.edge, "bond_blocked_hours_utc", [])
            if not CONFIG.dry_run and _bond_blocked and _utc_hour in _bond_blocked:
                continue
            # Total-loss cooldown: skip for 20 min after a NO resolution / expired-unsold.
            # Reduced to 10 min if current hour has ≥90% WR (n≥20) in historical TERMINAL data.
            if not CONFIG.dry_run:
                _tl_ts = self._bond_total_loss_ts.get(token.asset, 0.0)
                if _tl_ts > 0:
                    _tl_elapsed = now - _tl_ts
                    _tl_wr = self._terminal_hour_wr.get(_utc_hour, 0.0)
                    _tl_limit = (_BOND_TOTAL_LOSS_COOLDOWN_REDUCED_S if _tl_wr >= 0.90
                                 else _BOND_TOTAL_LOSS_COOLDOWN_S)
                    if _tl_elapsed < _tl_limit:
                        logger.info(
                            "[BOND] total_loss_cooldown %s — %.0fs remaining "
                            "(h%02d wr=%.0f%% limit=%dm)",
                            token.asset, _tl_limit - _tl_elapsed,
                            _utc_hour, _tl_wr * 100, _tl_limit // 60,
                        )
                        continue
            # Regime cooldown: pause all BOND entries after heavy loss or back-to-back losses.
            if not CONFIG.dry_run and now < self._regime_cooldown_until:
                logger.info(
                    "[BOND] regime_cooldown %s — %.0fs remaining",
                    token.asset, self._regime_cooldown_until - now,
                )
                continue
            _b_in_window += 1

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            if time.time() - ob.ts > 3.0:
                continue  # OB snapshot >3s old: WS and REST both lagging, skip entry
            ask = ob.asks[0][0] if ob.asks else None
            _ask_max = 0.93  # 0.95→0.93 2026-05-09: enforce 2-cent gap below PT0.95 exit (entries at ask 0.94/0.95 had ≤+1.06% upside; 14% of shadow gated entries in [0.93,0.96) dead zone)
            _elapsed_s = _window_s - remaining
            _ask_floor = 0.78  # 2026-05-07: 0.80→0.78 (gate-survivors [0.78,0.80) n=3 reliable, 3/3 dir-right)
            if ask is None or not (_ask_floor <= ask <= _ask_max):
                logger.info(
                    "[BOND] ask_skip %s/%s ask=%s floor=%.2f rem=%.0fs",
                    token.asset, token.side, f"{ask:.4f}" if ask else "None", _ask_floor, remaining,
                )
                _b_ask_skip += 1
                continue

            cid = getattr(token, "condition_id", "") or ""
            _token_dir  = getattr(token, "outcome_direction", "up")
            _elapsed_pct = 1.0 - remaining / max(1, token.window_seconds)
            _wlabel      = f"{token.window_seconds // 60}m"

            # ── TERMINAL observation metrics (data collection only) ──────────
            _asset_up = token.asset.upper()
            # Kline-based Binance momentum (same source as ext_signals in main scan loop)
            _term_ext = self._last_ext_signals.get(token.asset)
            _term_binance_1m  = _term_ext.spot_momentum_1m  if _term_ext else None
            _term_binance_5m  = _term_ext.spot_momentum_5m  if _term_ext else None
            _term_binance_60m = _term_ext.spot_momentum_60m if _term_ext else None
            # VPIN
            _vpin_t = self.feed.vpin_trackers.get(_asset_up)
            _term_vpin = round(_vpin_t.vpin, 4) if (_vpin_t and getattr(_vpin_t, "_trade_count", 0) > 50) else 0.0
            # Spot price deltas from price_history deque
            _spot_now = self.feed._spot_price.get(_asset_up, 0.0)
            _hist_q   = self.feed._price_history.get(_asset_up)
            def _hist_delta(hist, secs):
                if not hist or not _spot_now:
                    return 0.0
                cutoff = now - secs
                ref = None
                for ts, p in hist:
                    if ts <= cutoff:
                        ref = p
                return round((_spot_now - ref) / ref * 100, 4) if ref and ref > 0 else 0.0
            _term_d5s = _hist_delta(_hist_q, 5)
            _term_d30 = _hist_delta(_hist_q, 30)
            _term_d60 = _hist_delta(_hist_q, 60)
            _open_5m  = self.feed._spot_open_5m.get(_asset_up, 0.0)
            _term_d5m = round((_spot_now - _open_5m) / _open_5m * 100, 4) if _open_5m > 0 and _spot_now > 0 else 0.0
            # Fallback: ext_signals fetch failed → use direct kline-cache deltas
            # _term_d5m (open→now of current 5m bar) ≈ spot_momentum_5m (prev-bar→now)
            # _term_d60 (60s price-history delta) ≈ spot_momentum_1m
            if _term_binance_5m is None and _term_d5m != 0.0:
                _term_binance_5m = _term_d5m
            if _term_binance_1m is None and _term_d60 != 0.0:
                _term_binance_1m = _term_d60
            # Order book metrics
            _best_bid  = ob.bids[0][0] if ob.bids else 0.0
            _term_sprd = round((ask - _best_bid) / ask * 100, 4) if _best_bid > 0 else 0.0
            _term_aqty = round(ob.asks[0][1], 2) if ob.asks else 0.0
            _a3 = sum(q for _, q in ob.asks[:3])
            _b3 = sum(q for _, q in ob.bids[:3])
            _term_ob_depth = round(_b3 + _a3, 2)
            _term_imb  = round((_b3 - _a3) / (_b3 + _a3), 4) if (_b3 + _a3) > 0 else 0.0
            if _term_imb < 0.0:
                continue  # ob_imb floor 0.0 (was 0.20): signal_analysis 25-90s n=2614 solo-fail YES=89.9% vs pass-baseline 76.0%; negative imb in live ep range resolves YES more than gate-passers; existing UP/DOWN ceilings guard high-positive zone

            # ── Dead-zone / volatility filters ─────────────────────────────────
            # All three read from closed kline buffers (populated by WS, not REST).
            # Gates default OFF (threshold=0) — logged always; block only when enabled.
            _dz = CONFIG.dead_zone
            _dz_range = self.feed.get_60m_range_usd(token.asset)
            _dz_er    = self.feed.get_er(token.asset, n=14)
            _dz_atr   = self.feed.get_atr_ratio(token.asset)

            # Dynamic range threshold: use % of spot if configured, else fixed USD.
            _range_thresh = 0.0
            if _dz.range_use_pct and _spot_now > 0:
                _range_thresh = _spot_now * _dz.range_pct_of_price
            elif _dz.range_min_usd > 0:
                _range_thresh = _dz.range_min_usd

            _dz_range_block = (
                _range_thresh > 0 and _dz_range > 0 and _dz_range < _range_thresh
            )
            _dz_er_block  = _dz.er_min > 0 and _dz_er < _dz.er_min
            _dz_atr_block = _dz.atr_spike_ratio > 0 and _dz_atr > _dz.atr_spike_ratio

            logger.info(
                "[BOND] dead_zone %s/%s | range_60m=%.1f(thr=%.0f,blk=%s)"
                " er=%.3f(min=%.2f,blk=%s) atr_ratio=%.2f(max=%.1f,blk=%s)",
                token.asset, token.side,
                _dz_range, _range_thresh, _dz_range_block,
                _dz_er, _dz.er_min, _dz_er_block,
                _dz_atr, _dz.atr_spike_ratio, _dz_atr_block,
            )

            if _dz_range_block:
                logger.info(
                    "[BOND] dead_zone_range_skip %s/%s | 60m_range=%.1f < %.0f — flat market",
                    token.asset, token.side, _dz_range, _range_thresh,
                )
                _b_mom_skip += 1
                continue

            if _dz_er_block:
                logger.info(
                    "[BOND] dead_zone_er_skip %s/%s | er=%.3f < %.2f — choppy/directionless",
                    token.asset, token.side, _dz_er, _dz.er_min,
                )
                _b_mom_skip += 1
                continue

            if _dz_atr_block:
                logger.info(
                    "[BOND] dead_zone_atr_skip %s/%s | atr_ratio=%.2f > %.1f — volatility spike",
                    token.asset, token.side, _dz_atr, _dz.atr_spike_ratio,
                )
                _b_mom_skip += 1
                continue

            # Binance momentum (both-rising) gate removed: n=43, below n=100 threshold.
            # Data is still logged (term_binance_1m_pct, term_binance_5m_pct) for accumulation.

            # Token ask price trajectory: was the token rising or falling before entry?
            def _token_delta(hist, secs):
                if not hist or not ask:
                    return 0.0
                cutoff = now - secs
                ref = None
                for ts, p in hist:
                    if ts <= cutoff:
                        ref = p
                return round((ask - ref) / ref * 100, 4) if ref and ref > 0 else 0.0
            _tok_hist = self._token_ask_history.get(token_id)
            _term_tok_d3   = _token_delta(_tok_hist, 3)
            _term_tok_d5   = _token_delta(_tok_hist, 5)
            _term_tok_d30  = _token_delta(_tok_hist, 30)
            _term_tok_d60  = _token_delta(_tok_hist, 60)
            _term_tok_tick5 = sum(1 for ts, _ in (_tok_hist or []) if ts >= now - 5.0)

            if _utc_hour == 21 and _term_tok_d30 >= 35:
                logger.info("[BOND] h21_tok_skip %s/%s tok_d30=%.1f >= 35 rem=%.0fs",
                            token.asset, token.side, _term_tok_d30, remaining)
                _b_mom_skip += 1
                continue

            # Tick count 30s: distinct ask price changes in last 30s (wider window than 5s)
            _term_tok_tick_count_30s = 0
            if _tok_hist:
                _hist30 = [(ts, p) for ts, p in _tok_hist if ts >= now - 30.0]
                if len(_hist30) >= 2:
                    _prev_p = _hist30[0][1]
                    for _, _cp in _hist30[1:]:
                        if abs(_cp - _prev_p) > 0.001:
                            _term_tok_tick_count_30s += 1
                            _prev_p = _cp

            # Ask staleness: seconds since ask last changed in scan-loop history.
            # move_age_s from WS is 999 for 97% of trades (WS ticks too sparse).
            # This uses the ~2s scan-loop samples which are always populated.
            _term_ask_stale_s = 999.0
            if _tok_hist and ask is not None:
                _hist_list = list(_tok_hist)
                for _hts, _hp in reversed(_hist_list):
                    if abs(_hp - ask) > 0.005:
                        _term_ask_stale_s = round(now - _hts, 1)
                        break
                else:
                    if _hist_list:
                        _term_ask_stale_s = round(now - _hist_list[0][0], 1)

            # Deceleration ratio: d5s / d30s. Near 0 = momentum stalled at entry.
            # Valid only when |d30| >= 0.5% (otherwise ratio is noise).
            _term_tok_decel_ratio = 0.0
            if abs(_term_tok_d30) >= 0.5:
                _term_tok_decel_ratio = round(
                    max(-3.0, min(3.0, _term_tok_d5 / _term_tok_d30)), 4
                )

            # Trajectory fields for report analysis (bond_delta_accel_30s etc.)
            # Map token ask velocity → bond_delta_accel_30s (fraction: +0.05 = token up 5% in 30s)
            _tok_accel = round(_term_tok_d30 / 100.0, 4)
            _tok_drift  = round(_term_tok_d30 / 100.0, 4)
            _tok_sust   = bool(_term_tok_d30 > 0.5 and _term_tok_d60 > 0.5)
            _tok_has_hist = False
            if _tok_hist:
                _cutoff30 = now - 30.0
                for _hts, _ in _tok_hist:
                    if _hts <= _cutoff30:
                        _tok_has_hist = True
                        break
            if not _tok_has_hist:
                continue  # no 30s price history: WR=60% avg=-$0.27 (n=209 vs has_hist WR=64% avg=+$0.03)

            # RSI and ask VWAP: read from pre-entry snapshot frozen at remaining=90s
            _pre_obs = self._term_pre_entry_obs.get(token_id, {})
            _term_rsi = _pre_obs.get("rsi", 0.0)
            _term_ask_vwap = _pre_obs.get("vwap", 0.0)

            # Flat drift gate removed: n=56, below n=100 threshold; derived from TREND
            # strategy data, not validated on TERMINAL entries specifically.
            signal = SniperSignal(
                asset=token.asset,
                side=token.side,
                asset_direction=1,
                delta_pct=0.0,
                fair_value=1.0,
                token_ask=ask,
                edge=round(1.0 - ask, 4),
                entry_price=ask,
                confidence=ask,
                composite=round(1.0 - ask, 4),
                direction=Direction.BUY_YES,
                fee_zone=FeeZone.EXTREME,
                elapsed_pct=_elapsed_pct,
                reason=f"TERMINAL_{_wlabel} ask={ask:.3f} rem={remaining:.0f}s",
                signal_source="BOND",
                is_bond=True,
                bond_exit_sec=3,
                bond_outcome_direction=_token_dir,
                bond_entry_class="TERMINAL",
            )
            # Attach TERMINAL observations to signal for downstream logging
            signal.term_vpin          = _term_vpin
            signal.term_binance_1m_pct  = _term_binance_1m
            signal.term_binance_5m_pct  = _term_binance_5m
            signal.term_binance_60m_pct = _term_binance_60m
            signal.term_spot_delta_5s  = _term_d5s
            signal.term_spot_delta_30s = _term_d30
            signal.term_spot_delta_60s = _term_d60
            signal.term_spot_delta_5m  = _term_d5m
            signal.term_ask_spread_pct = _term_sprd
            signal.term_ask_qty        = _term_aqty
            signal.term_ob_imbalance     = _term_imb
            signal.term_ob_depth         = _term_ob_depth
            signal.term_remaining_s      = round(remaining, 1)
            signal.term_token_delta_3s   = _term_tok_d3
            signal.term_token_delta_5s   = _term_tok_d5
            signal.term_token_delta_30s  = _term_tok_d30
            signal.term_token_delta_60s  = _term_tok_d60
            signal.term_tok_tick_count_5s  = _term_tok_tick5
            signal.term_tok_tick_count_30s = _term_tok_tick_count_30s
            signal.term_ask_stale_s        = _term_ask_stale_s
            signal.term_tok_decel_ratio    = _term_tok_decel_ratio
            # Window-anchored pre-entry snaps: % change from fixed remaining thresholds to now.
            # pre_snap_60s: ask at remaining=150s → now (60s before window to entry)
            # pre_snap_30s: ask at remaining=120s → now (30s before window to entry)
            # pre_snap_open: ask at remaining=90s  → now (window-open to entry)
            _snap_refs = self._term_pre_snap_refs.get(token_id, {})
            def _anchored_snap(ref_ask):
                return round((ask - ref_ask) / ref_ask * 100, 4) if ref_ask and ref_ask > 0 else 0.0
            signal.term_pre_snap_60s  = _anchored_snap(_snap_refs.get(150, 0.0))
            signal.term_pre_snap_30s  = _anchored_snap(_snap_refs.get(120, 0.0))
            signal.term_pre_snap_open = _anchored_snap(_snap_refs.get(90, 0.0))
            signal.term_rsi           = _term_rsi
            signal.term_ask_vwap      = _term_ask_vwap

            # Ask-history gate: stale ask = ghost order / thin market.
            # stale>=4s: WR drops, dominant losers (T02829 -$9.94, T02814 -$7.22) in 4–7s zone.
            # Blocked net=-$35.07 across 72 trades (3-day sample). 7-10s WR=100% is n=12 noise.
            if _term_ask_stale_s >= 4.0:
                continue

            # snap60/snap30 computed for logging only — gates removed 2026-05-09 (Model A)
            # Phase 2 ablation (n=499): snap30/snap60 r=0.71 (redundant); ob_imb orthogonal
            # and dominant; snap gates compressed throughput for no net EV gain.
            _snap60_val = signal.term_pre_snap_60s
            _snap30_val = signal.term_pre_snap_30s
            _snap60_eff = _snap60_val if _snap60_val != 0.0 else _term_tok_d60
            _snap30_eff = _snap30_val if _snap30_val != 0.0 else _term_tok_d30
            signal.term_snap60_eff = round(_snap60_eff, 4)
            signal.term_snap30_eff = round(_snap30_eff, 4)

            # 5s momentum gate — two independent failure modes:
            # DOWN (<-3%): token falling = ETH reversing up = buying the reversal.
            #   Evidence: T03840_ETH tok_d5=-4.40% → -$35.29. Threshold -3% (not -2%)
            #   to release T03774/T03823 winners at -2.3%.
            # UP (>10%): token overbought in final 5s = snap-back risk.
            #   May6-7: 4 losers avg -$22 all had d5>10%; 5-10% bucket is 100% WR (n=9)
            #   so that zone must stay open. Low-d5 UP losers (3-4%) are a snap60 problem.
            if (_token_dir == "down" and _term_tok_d5 < -3.0) or (_token_dir == "up" and _term_tok_d5 > 10.0):
                logger.info(
                    "[BOND] tok5_gate %s/%s | tok_d5=%.1f%% dir=%s — adverse 5s momentum, skip",
                    token.asset, token.side, _term_tok_d5, _token_dir,
                )
                _b_mom_skip += 1
                continue

            # d5s > 25%: micro blow-off — token spiked >25% in 5s before entry, reversal risk
            # n=49 Apr28+: WR=43% PF=0.47 net=-$18.4; rest WR=66% PF=1.15 net=+$25.7; user-authorised Tier 2
            if _term_tok_d5 > 25.0:
                logger.info(
                    "[BOND] d5s_blowoff %s/%s | d5s=%.1f%% — micro blow-off skip (>25%%)",
                    token.asset, token.side, _term_tok_d5,
                )
                _b_mom_skip += 1
                continue

            # SOL spread > 3%: wide spread = market-maker uncertainty; dir_acc drops below 80%
            # spread 1-2% bucket: WR=73%, net=+$9.18, dir_acc=92% (n=26 Apr28-29)
            # spread >3%: net=-$12.17 drag; snap+spread≤3 is only profitable SOL combo
            if token.asset == "SOL" and (_term_sprd or 0.0) > 3.0:
                logger.info(
                    "[BOND] sol_spread %s/%s | spread=%.1f%% — wide spread skip",
                    token.asset, token.side, _term_sprd or 0.0,
                )
                _b_mom_skip += 1
                continue

            # ETH tok_delta_30s ≥ 100%: ETH 30s overextension — WR=42.9% (n=7, user-auth Tier2 2026-05-02)
            if token.asset == "ETH" and _term_tok_d30 >= 100.0:
                logger.info(
                    "[BOND] eth_td30_overext %s/%s | td30=%.1f%% — ETH 30s overextension skip",
                    token.asset, token.side, _term_tok_d30,
                )
                _b_mom_skip += 1
                continue

            # ── G1 regime filter — session-adaptive bands (user-auth 2026-05-07, Tier 2) ──
            # YES UP only. Per-session counterfactual on macro-populated subset (n=145 pre-May7):
            #   universal [0%, +0.30%]: pre-May7 +$17, May7 -$22 (vs current [-0.3,+1.5] -$54/-$157)
            #   per-session optimum bands (in-sample fitted, expect 50-70% of gain OOS):
            #     ASIA  (00-08): [-0.05%, +0.25%] — n=71, optimum +$17 vs ungated -$164
            #     LDN   (08-13): [ 0.00%, +0.30%] — universal default (n=18 too thin)
            #     US    (13-18): [ 0.00%, +0.30%] — universal default (n=17 too thin)
            #     LATE  (18-24): [+0.05%, +0.25%] — n=50, optimum +$25 vs ungated -$56
            # Skip gate if 60m return unavailable (<61 closed 1m bars since startup)
            if 0 <= _utc_hour < 8:
                _g1_lo, _g1_hi, _g1_sess = -0.05, 0.25, "ASIA"
            elif 8 <= _utc_hour < 13:
                _g1_lo, _g1_hi, _g1_sess = 0.00, 0.30, "LDN"
            elif 13 <= _utc_hour < 18:
                _g1_lo, _g1_hi, _g1_sess = 0.00, 0.30, "US"
            else:
                _g1_lo, _g1_hi, _g1_sess = 0.05, 0.25, "LATE"
            logger.info(
                "[BOND] G1_check %s/%s | sess=%s band=[%+.2f%%,%+.2f%%] G1_60m=%s",
                token.asset, token.side, _g1_sess, _g1_lo, _g1_hi,
                f"{_term_binance_60m:+.3f}%" if _term_binance_60m is not None else "None(bypassed)",
            )
            if (_token_dir == "up"
                    and _term_binance_60m is not None
                    and not (_g1_lo <= _term_binance_60m <= _g1_hi)):
                logger.info(
                    "[BOND] G1_regime_skip %s/%s | sess=%s G1_60m=%+.3f%% outside [%+.2f%%,%+.2f%%]",
                    token.asset, token.side, _g1_sess, _term_binance_60m, _g1_lo, _g1_hi,
                )
                _b_mom_skip += 1
                continue

            # ── DOWN session-conditional G1 (user-auth 2026-05-07, Tier 2 — thin-sample exception) ──
            # LATE DOWN: skip if Bnc60m > 0% (band [-inf, 0%]). Spot rising in last hour while
            # entering DOWN in LATE session = bad. n=42 macro era, +$17.60 in-sample vs ungated -$2.92.
            # CAVEAT: load-bearing bucket [0%, +0.25%) is n=5; ~$15 of edge from 1 BOND_EXPIRED_UNSOLD outlier.
            # Deployed under user override of n>=40-per-bucket rule. Re-evaluate at n>=40 in [0,+0.25%).
            # ASIA/LDN/US DOWN: no gate (per-session optimums are negligible or n<20).
            if (_token_dir == "down"
                    and _g1_sess == "LATE"
                    and _term_binance_60m is not None
                    and _term_binance_60m > 0.0):
                logger.info(
                    "[BOND] G1_down_late_skip %s/%s | sess=LATE G1_60m=%+.3f%% > 0%% — DOWN late+rising-spot skip",
                    token.asset, token.side, _term_binance_60m,
                )
                _b_mom_skip += 1
                continue

            # ── ETH UP regime asymmetry (user-auth 2026-05-07, Tier 2 — thin-sample exception) ──
            # ETH UP is mean-reverting in rising-spot regimes: bnc60m≥0% n=38 avg -$1.39,
            # bnc60m<0% n=15 avg +$0.95. Bot enters UP into rallies that revert at resolution.
            # cor% (resolution rate) is healthy 57-64% across imb thresholds — not a base-rate
            # problem; it's a regime-selection problem orthogonal to imb. Tier 2 with n=53
            # macro-populated trades; deployed under user override of n≥100 rule by symmetry
            # with LATE DOWN gate above. Re-evaluate at n≥100 macro era.
            if (token.asset == "ETH"
                    and _token_dir == "up"
                    and _term_binance_60m is not None
                    and _term_binance_60m > 0.0):
                logger.info(
                    "[BOND] G1_eth_up_skip %s/%s | G1_60m=%+.3f%% > 0%% — ETH UP rising-spot mean-reverts skip",
                    token.asset, token.side, _term_binance_60m,
                )
                _b_mom_skip += 1
                continue

            # Binance slow-bleed regime: spot falling -0.05% to -0.02% in 5m
            # n=233 PF=0.95 net=-$8.47; fast falls (<-0.05%) are fine (PF=2.31, market already priced)
            # Only applies to YES UP: for YES DOWN a falling spot is favourable.
            # Skip gate if value is None/0.0 (not captured) to avoid false blocks
            if (_token_dir == "up"
                    and _term_binance_5m is not None and _term_binance_5m != 0.0
                    and -0.05 <= _term_binance_5m < -0.02):
                logger.info(
                    "[BOND] binance_slowbleed %s/%s | b5m=%.4f%% — spot slow-bleed skip (UP only)",
                    token.asset, token.side, _term_binance_5m,
                )
                _b_mom_skip += 1
                continue

            # ── Direction-aware Binance momentum gates (user-auth 2026-05-04, Tier 2) ──
            # YES UP: skip if BTC trending down in last 1m (W avg=+0.0028, L avg=-0.0023, Δ=0.0051**)
            # UTC 22 exception: mean-reversion regime, Bnc signal inverts — gate disabled.
            if (_token_dir == "up" and _utc_hour != 22
                    and _term_binance_1m is not None and _term_binance_1m != 0.0
                    and _term_binance_1m < 0.0):
                logger.info(
                    "[BOND] bnc_dir_skip %s/%s | dir=UP b1m=%.4f%% — BTC falling, skip YES UP",
                    token.asset, token.side, _term_binance_1m,
                )
                _b_mom_skip += 1
                continue
            # YES DOWN: skip if BTC trending up in last 1m (need BTC down to win)
            if (_token_dir == "down"
                    and _term_binance_1m is not None and _term_binance_1m != 0.0
                    and _term_binance_1m > 0.0):
                logger.info(
                    "[BOND] bnc_dir_skip %s/%s | dir=DOWN b1m=%.4f%% — BTC rising, skip YES DOWN",
                    token.asset, token.side, _term_binance_1m,
                )
                _b_mom_skip += 1
                continue
            # YES DOWN: skip if ask queue > 200 shares (huge wall signals high resolution risk)
            # UTC 20 trade #1: askq=632.6 alone cost -$9.81; n=small but asymmetric risk
            if (_token_dir == "down" and _term_aqty > 200.0):
                logger.info(
                    "[BOND] down_askq_skip %s/%s | askq=%.1f — massive ask wall, skip YES DOWN",
                    token.asset, token.side, _term_aqty,
                )
                _b_mom_skip += 1
                continue

            # ── Layer 1: Market structure filter (hard gate) ─────────────────────────
            # BTC YES DOWN only: skip if OB too thick — token can't walk to 1.0 through wall.
            # Sim n=102: depth>2000 → 8 BTC-DOWN trades (2W/6L -$21.97), net +$22.07.
            # Uses _term_ob_depth (top-3 bid+ask); ob_depth_at_entry (top-5) runs ~20% higher.
            if (_token_dir == "down" and token.asset == "BTC"
                    and _term_ob_depth > 2000.0):
                logger.info(
                    "[BOND] L1_depth_skip %s/%s | dir=DOWN ob_depth=%.1f — thick book >2000, skip",
                    token.asset, token.side, _term_ob_depth,
                )
                _b_mom_skip += 1
                continue

            # ── Layer 2: Momentum exhaustion filter (hard gate) ──────────────────────
            # YES DOWN: skip if tok30 > 40 — YES token already running hard, move is mature.
            # Validation n=35 DOWN: >40 → 9 trades (1W/8L -$21.20), net +$21.20.
            # Only 1 winner above 40 (UTC20 BTC td30=68.6 +$1.12 TP) vs 8 PAE losses.
            # Universal across BTC/ETH/SOL and all hours — no asset/hour carve-outs needed.
            if (_token_dir == "down" and _term_tok_d30 > 40.0):
                logger.info(
                    "[BOND] L2_tok30_exhaust %s/%s | dir=DOWN tok30=%.1f%% — exhausted >40, skip",
                    token.asset, token.side, _term_tok_d30,
                )
                _b_mom_skip += 1
                continue

            # ── Per-asset pre-entry gates (user-authorised 2026-05-03, n<100 Tier 2) ──
            # BTC: require positive sustained momentum (daccel>+0.01 AND accel_sustained)
            # flat daccel: n=38 WR=37% net=-$151; not_sustained: n=54 WR=43% net=-$169
            if token.asset == "BTC" and _tok_accel <= 0.01:
                logger.info(
                    "[BOND] btc_daccel_skip %s/%s | daccel=%.4f tok_d30=%.1f%% — flat/counter skip",
                    token.asset, token.side, _tok_accel, _term_tok_d30,
                )
                _b_mom_skip += 1
                continue
            if token.asset == "BTC" and not _tok_sust:
                logger.info(
                    "[BOND] btc_sust_skip %s/%s | sust=False tok_d30=%.1f%% tok_d60=%.1f%% — not sustained",
                    token.asset, token.side, _term_tok_d30, _term_tok_d60,
                )
                _b_mom_skip += 1
                continue
            # BTC: late entry (elapsed>=0.85): n=27 WR=52% net=-$113 avg=-$4.19
            if token.asset == "BTC" and _elapsed_pct >= 0.85:
                logger.info(
                    "[BOND] btc_late_skip %s/%s | elapsed=%.3f — late BTC entry skip",
                    token.asset, token.side, _elapsed_pct,
                )
                _b_mom_skip += 1
                continue
            # BTC: thin OB (top-3 depth<500): n=20 WR=35% net=-$86
            if token.asset == "BTC" and _term_ob_depth < 500:
                logger.info(
                    "[BOND] btc_depth_skip %s/%s | ob_depth=%.1f — thin BTC book skip",
                    token.asset, token.side, _term_ob_depth,
                )
                _b_mom_skip += 1
                continue
            # ETH: flat tok_d30 (0,2%): n=26 WR=38% net=-$92; negative tok_d OK (WR=69%)
            # 0.0 = not captured (logging gap) — exempt to avoid false blocks
            if token.asset == "ETH" and 0.0 < _term_tok_d30 < 2.0:
                logger.info(
                    "[BOND] eth_tokd30_skip %s/%s | tok_d30=%.1f%% — ETH flat momentum [0,2) skip",
                    token.asset, token.side, _term_tok_d30,
                )
                _b_mom_skip += 1
                continue
            # ETH: no sustained momentum — tok_d30>0.5% AND tok_d60>0.5% required
            # 2026-05-05: n=13 ETH, 0 winners had sust=False; T03710 (-$4.57) had tok_d30=0%
            if token.asset == "ETH" and not _tok_sust:
                logger.info(
                    "[BOND] eth_sust_skip %s/%s | sust=False tok_d30=%.1f%% tok_d60=%.1f%% — ETH flat momentum skip",
                    token.asset, token.side, _term_tok_d30, _term_tok_d60,
                )
                _b_mom_skip += 1
                continue
            # ETH: thin OB (top-3 depth<100): n=11 WR=18% net=-$65
            if token.asset == "ETH" and _term_ob_depth < 100:
                logger.info(
                    "[BOND] eth_depth_skip %s/%s | ob_depth=%.1f — thin ETH book skip",
                    token.asset, token.side, _term_ob_depth,
                )
                _b_mom_skip += 1
                continue
            # ── Layer 3: Cross-asset regime modifier ─────────────────────────────────
            # ETH YES UP: require BTC positive momentum ≥ +0.015% (not just non-negative).
            # ETH UP WR=41% -$15.40; flat BTC (0 to +0.015%) provides no UP support for ETH.
            # Global UP gate already blocks bnc<0. This tightens ETH UP only (not UTC22).
            # ETH DOWN: no additional restriction — already profitable (WR=55% +$13.93).
            if (token.asset == "ETH" and _token_dir == "up" and _utc_hour != 22
                    and _term_binance_1m is not None and _term_binance_1m != 0.0
                    and _term_binance_1m < 0.0150):
                logger.info(
                    "[BOND] L3_eth_bnc_skip %s/%s | dir=UP b1m=%.4f%% — ETH UP needs BTC≥+0.015%%",
                    token.asset, token.side, _term_binance_1m,
                )
                _b_mom_skip += 1
                continue

            # SOL: late entry (elapsed>=0.75): n=29 WR=65% net=-$46
            if token.asset == "SOL" and _elapsed_pct >= 0.75:
                logger.info(
                    "[BOND] sol_late_skip %s/%s | elapsed=%.3f — late SOL entry skip",
                    token.asset, token.side, _elapsed_pct,
                )
                _b_mom_skip += 1
                continue

            # SOL DOWN: thin OB (top-3 depth<100). Apr28-May7 n=45 PF=0.47 net=-$44.61;
            # survivors n=86 PF=0.98 net=-$0.85. Direction-specific: SOL UP unaffected
            # (depth<100 on UP would kill +$15 of edge). Mirrors ETH depth<100 gate.
            if token.asset == "SOL" and _token_dir == "down" and _term_ob_depth < 100:
                logger.info(
                    "[BOND] sol_dn_depth_skip %s/%s | ob_depth=%.1f — thin SOL DOWN book skip",
                    token.asset, token.side, _term_ob_depth,
                )
                _b_mom_skip += 1
                continue

            # Gate A: YES DOWN ep>=0.92 — universal ceiling (raised 0.88->0.92 2026-05-07)
            if _token_dir == "down" and ask >= 0.92:
                logger.info(
                    "[BOND] down_ep_skip %s/%s | ep=%.4f — YES DOWN ep>=0.92 skip",
                    token.asset, token.side, ask,
                )
                _b_mom_skip += 1
                continue

            # Gate D: YES UP decel≥2.0 — sharp reversal in progress (n=2 WR=0%, Tier2 2026-05-05)
            if _token_dir == "up" and _term_tok_decel_ratio >= 2.0:
                logger.info(
                    "[BOND] up_decel_skip %s/%s | decel=%.4f — YES UP decel≥2.0 skip",
                    token.asset, token.side, _term_tok_decel_ratio,
                )
                _b_mom_skip += 1
                continue

            # ── Layer 4: Microstructure noise — log-only, no gate ────────────────────
            # Track ask_stale distribution: stale<1.0 = active repricing = potential volatility.
            # Sim showed stale<0.5 fires 0 trades (floor at 0.5s); stale<1.0 filters 30 (13W/17L).
            # Log here (post all hard gates) to build distribution for future threshold decision.
            if _term_ask_stale_s < 1.0:
                logger.info(
                    "[BOND] L4_stale_monitor %s/%s | dir=%s stale=%.1f sprd=%.2f%% depth=%.1f — log only",
                    token.asset, token.side, _token_dir,
                    _term_ask_stale_s, _term_sprd, _term_ob_depth,
                )

            # Trajectory fields (populate bond_ fields so report sections work)
            signal.bond_delta_accel_30s  = _tok_accel
            signal.bond_edge_drift_30s   = _tok_drift
            signal.bond_accel_sustained  = _tok_sust
            signal.bond_has_hist         = _tok_has_hist

            tpsl = TPSLLevels(
                take_profit=min(0.99, round(ask + 0.04, 4)),
                stop_loss=round(ask * 0.85, 4),
                tp_pct=round(0.04 / ask * 100, 1),
                sl_pct=15.0,
                risk_reward=0.0,
            )

            decision = self.risk.evaluate(
                token_id, signal, tpsl,
                condition_id=cid,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=0.0,
                is_sniper=False,
                window_seconds=getattr(token, "window_seconds", 0),
                bond_entry_class="TERMINAL",
                bond_macro_regime="TERMINAL",
            )

            if not decision.approved:
                logger.info("TERMINAL REJECTED %s/%s: %s", token.asset, token.side, decision.reason)
                continue

            # Equity-based stake sizing: snap60+rem tiers (user-authorised May 6)
            # Tiers floored at base_stake so they never reduce below the configured flat stake.
            # Tier 1: snap60≥50% → 18% of equity; Tier 2: snap60≥20%+rem≥75s → 14% of equity
            _capital = self.risk.bankroll.capital
            _base = CONFIG.bankroll.base_stake
            if _snap60_eff >= 50.0:
                decision.stake = max(_base, round(_capital * 0.18, 2))
                logger.info(
                    "[BOND] stake_tier1 %s/%s | snap60=%.1f%% cap=$%.2f → stake=$%.2f (18%% floor base=$%.2f)",
                    token.asset, token.side, _snap60_eff, _capital, decision.stake, _base,
                )
            elif _snap60_eff >= 20.0 and remaining >= 75.0:
                decision.stake = max(_base, round(_capital * 0.14, 2))
                logger.info(
                    "[BOND] stake_tier2 %s/%s | snap60=%.1f%% rem=%.0fs cap=$%.2f → stake=$%.2f (14%% floor base=$%.2f)",
                    token.asset, token.side, _snap60_eff, remaining, _capital, decision.stake, _base,
                )
            else:
                decision.stake = _base

            # Gate C: YES UP snap30≥60% — blow-off pattern, reduce stake to 30% (Tier2 2026-05-05)
            if _token_dir == "up" and _snap30_eff >= 60.0:
                _orig_stake = decision.stake
                decision.stake = max(5.0, round(decision.stake * 0.30, 2))
                logger.info(
                    "[BOND] up_snap30_reduce %s/%s | snap30=%.1f%% stake $%.2f→$%.2f — blow-off stake cut",
                    token.asset, token.side, _snap30_eff, _orig_stake, decision.stake,
                )

            # ── Session × Direction stake multiplier (user-auth 2026-05-07, Tier 2) ──
            # Per-session direction-asymmetric sizing. Pre-May7 evidence per cell:
            #   ASIA UP   n=200 avg -$0.22 → 0.5x   |  ASIA DOWN → 1.0x
            #   LDN  UP   n=176 avg -$0.12 → 1.0x   |  LDN  DOWN → 1.0x (rolled back 2026-05-07: full-era n=171
            #                                                   was contaminated by pre-May-5 era; May 5+ n=18
            #                                                   WR 83.3% +$0.44/trade — cell is profitable)
            #   US   UP   n=234 avg +$0.16 → 1.5x   |  US   DOWN → 1.0x
            #   LATE UP   n=314 avg -$0.33 → 0.3x   |  LATE DOWN → 1.0x
            # DOWN era split: Apr24-May4 n=704 -$92.22; May5-May6 n=82 +$11.98 — DOWN currently profitable
            # across all sessions; no DOWN multipliers needed. Re-evaluate at n>=100 May 5+ per session.
            # Floor at $5 to avoid sub-min-share orders. Applied AFTER all other sizing logic.
            _sxd_mult = {
                ("up",   "ASIA"): 0.5, ("up",   "LDN"): 1.0, ("up",   "US"): 1.5, ("up",   "LATE"): 0.3,
                ("down", "ASIA"): 1.0, ("down", "LDN"): 1.0, ("down", "US"): 1.0, ("down", "LATE"): 1.0,
            }.get((_token_dir, _g1_sess), 1.0)
            if _sxd_mult != 1.0:
                _pre_sxd = decision.stake
                decision.stake = max(5.0, round(decision.stake * _sxd_mult, 2))
                logger.info(
                    "[BOND] sxd_stake %s/%s | sess=%s dir=%s mult=%.1fx stake $%.2f→$%.2f",
                    token.asset, token.side, _g1_sess, _token_dir, _sxd_mult, _pre_sxd, decision.stake,
                )

            # ── IMMEDIATE SAFETY CAP (2026-05-08) ────────────────────────────
            # Hard $7 per-trade cap while PT0.95+30s exit is being battle-tested.
            # User-authorised "capped exposure" mode during active drawdown. Reverts
            # when shadow validation completes or user lifts the cap.
            _SAFETY_STAKE_CAP = 7.0
            if decision.stake > _SAFETY_STAKE_CAP:
                _pre_cap = decision.stake
                decision.stake = _SAFETY_STAKE_CAP
                logger.info(
                    "[BOND] safety_cap %s/%s | stake $%.2f→$%.2f (cap=$%.2f)",
                    token.asset, token.side, _pre_cap, decision.stake, _SAFETY_STAKE_CAP,
                )

            if _ask_floor == 0.52:
                # Early window: invert — gates fired on _token_dir side, buy opposite instead.
                _inv_dir = "down" if _token_dir == "up" else "up"
                _inv_id: str | None = None
                _inv_ask: float | None = None
                for _pid, _pt in self.feed.tokens.items():
                    if _pid == token_id:
                        continue
                    if getattr(_pt, "condition_id", "") != cid:
                        continue
                    _pob = self.feed.get_order_book(_pid)
                    if _pob and _pob.asks:
                        _inv_id = _pid
                        _inv_ask = _pob.asks[0][0]
                        break
                if _inv_id is None or _inv_ask is None:
                    logger.warning(
                        "[BOND] INVERT_NO_PARTNER %s/%s — no partner ask, skipping",
                        token.asset, token.side,
                    )
                    continue
                _inv_side = getattr(self.feed.tokens[_inv_id], "side", "?")
                signal.side                   = _inv_side
                signal.entry_price            = _inv_ask
                signal.token_ask              = _inv_ask
                signal.edge                   = round(1.0 - _inv_ask, 4)
                signal.composite              = round(1.0 - _inv_ask, 4)
                signal.confidence             = _inv_ask
                signal.bond_outcome_direction = _inv_dir
                signal.reason                 = f"TERMINAL_INVERT_{_wlabel} ask={_inv_ask:.3f} rem={remaining:.0f}s"
                tpsl = TPSLLevels(
                    take_profit=min(0.99, round(_inv_ask + 0.04, 4)),
                    stop_loss=round(_inv_ask * 0.85, 4),
                    tp_pct=round(0.04 / _inv_ask * 100, 1),
                    sl_pct=15.0,
                    risk_reward=0.0,
                )
                logger.info(
                    "TERMINAL ENTRY %s/%s [%s] | ask=%.4f rem=%.0fs | stake=$%.2f (INVERTED from %s/%.4f)",
                    token.asset, _inv_side, _wlabel, _inv_ask, remaining, decision.stake, token.side, ask,
                )
            else:
                # Late/TERMINAL window: buy the token that passed the gates directly.
                _inv_id   = token_id
                _inv_ask  = ask
                _inv_side = token.side
                _inv_dir  = _token_dir
                logger.info(
                    "TERMINAL ENTRY %s/%s [%s] | ask=%.4f rem=%.0fs | stake=$%.2f",
                    token.asset, token.side, _wlabel, ask, remaining, decision.stake,
                )

            # ── SNAP shadow gate (observability only — no execution effect) ────
            _snap_60 = float(getattr(signal, "term_pre_snap_60s", 0.0) or 0.0)
            _snap_30 = float(getattr(signal, "term_pre_snap_30s", 0.0) or 0.0)
            # Stage 3 shadow log (2026-05-07): tag entries that pass current gates
            # but would fail under a 25% snap60_eff floor. Goal: 48h tracking to
            # decide if Stage 3 floor is worth promoting from log-only to enforced.
            if _snap60_eff < 25.0:
                logger.info(
                    "[SIGNAL_PASS][STAGE_3_REJECT] %s/%s | snap60_eff=%.1f%% (floor=25) ask=%.4f rem=%.0fs dir=%s tok_id=%s",
                    token.asset, _inv_side, _snap60_eff, _inv_ask, remaining, _inv_dir, _inv_id,
                )
            # snap_shadow.jsonl retired 2026-05-09 — subsumed by gate_trace in shadow substrate

            # ── Entry stability classification (observability only) ────────────
            # Decomposable instability labels — one signal per dimension, no
            # composite black boxes. DOES NOT affect execution: entries proceed
            # regardless of stab_class.
            #
            # Goal: causal attribution. Which instability dimension correlates
            _b_fired += 1
            self._terminal_traded_windows.add(_wkey)  # lock this asset×window — no re-entry
            asyncio.create_task(
                self._enter_position(_inv_id, token.asset, signal, tpsl, decision),
                name=f"bond_{token.asset}_{_inv_dir}",
            )
            asyncio.create_task(
                self._record_terminal_final_price(
                    _inv_id, token.asset, _inv_side,
                    token.window_end_ts, _inv_ask,
                ),
                name=f"wfp_{token.asset}_{_inv_dir}",
            )
          except Exception as _bond_tok_exc:
            logger.error(
                "BOND SCAN ERROR %s/%s — skipping token: %s",
                getattr(token, "asset", "?"), getattr(token, "side", "?"),
                _bond_tok_exc, exc_info=True,
            )

        try:
            _bond_status = "TERMINAL FIRED" if _b_fired else "TERMINAL WAITING"
            logger.info(
                "[BOND] %s | updown=%d in_window=%d ask_skip=%d mom_skip=%d fired=%d",
                _bond_status, _b_total, _b_in_window, _b_ask_skip, _b_mom_skip, _b_fired,
            )
            # Self-healing: if no updown tokens are tracked at all, the feed lost
            # them (discovery timeout / Cloudflare blip). Reset the 60s throttle so
            # the very next poll_order_books triggers an immediate re-discovery
            # instead of waiting up to 60 more seconds. This avoids the need to
            # restart the bot after transient network failures.
            if _b_total == 0 and not getattr(self.feed, "_stub_mode", False):
                self.feed._last_discovery_ts = 0.0
                logger.warning(
                    "[BOND] zero updown tokens tracked — resetting discovery throttle for immediate refresh"
                )
        except Exception as _sum_exc:
            logger.error("[BOND] summary log failed: %s", _sum_exc)

    # ── Reversal candidate shadow logger ─────────────────────────────────────

    async def _scan_reversal_candidates(self) -> None:
        """
        Shadow-observe late-window reversal opportunities. No live trading.

        Fires when:
          - dominant token (ask ≥ 0.70) has the underlying spot moving AGAINST it
          - 30–90 s remaining in a 5m window
          - |delta_against| ≥ 0.05% (deliberately low for observation coverage)

        Logs to logs/reversal_cands.jsonl. Analyse with:
            python3 analytics/reversal_log.py
        """
        _DOM_MIN       = 0.70    # dominant token threshold
        _DOM_MAX       = 0.90    # cap — above 0.90 underdog is illiquid
        _DELTA_MIN     = 0.05    # min |delta| against dominant (low for coverage)
        _REM_MIN       = 30.0    # seconds
        _REM_MAX       = 90.0    # seconds

        now = time.time()
        seen_conditions: set = set()

        for token_id, token in list(self.feed.tokens.items()):
            if token.market_type != "updown":
                continue
            if not (250 <= getattr(token, "window_seconds", 0) < 900):
                continue  # 5m only for now
            if token.window_end_ts <= 0:
                continue

            remaining = token.window_end_ts - now
            if not (_REM_MIN <= remaining <= _REM_MAX):
                continue

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            dom_ask = ob.asks[0][0] if ob.asks else None
            if dom_ask is None or not (_DOM_MIN <= dom_ask <= _DOM_MAX):
                continue

            cid = getattr(token, "condition_id", "") or ""
            if not cid or cid in seen_conditions:
                continue
            seen_conditions.add(cid)

            # Find the partner token (same condition, opposite side)
            underdog_id: str | None = None
            underdog_token = None
            underdog_ask: float | None = None
            for other_id, other in self.feed.tokens.items():
                if other_id == token_id:
                    continue
                if getattr(other, "condition_id", "") != cid:
                    continue
                other_ob = self.feed.get_order_book(other_id)
                if other_ob is None:
                    continue
                other_ask = other_ob.asks[0][0] if other_ob.asks else None
                if other_ask is None:
                    continue
                underdog_id = other_id
                underdog_token = other
                underdog_ask = other_ask
                break

            if underdog_id is None or underdog_ask is None:
                continue

            # Get delta for this asset
            _ext = getattr(self, "_last_ext_signals", {}).get(token.asset)
            if not _ext or not _ext.spot_price:
                continue
            _ref = _ext.spot_window_open_5m or 0.0
            if _ref <= 0:
                continue
            _delta = (_ext.spot_price - _ref) / _ref * 100

            # Is the underlying moving AGAINST the dominant token?
            _dom_dir = getattr(token, "outcome_direction", "up")
            _against = (
                (_dom_dir == "up"   and _delta <= -_DELTA_MIN) or
                (_dom_dir == "down" and _delta >= _DELTA_MIN)
            )
            if not _against:
                continue

            # Deduplicate: only log each condition once per scan cycle
            _rev_key = f"{cid}_{remaining:.0f}"
            _seen_rev = getattr(self, "_rev_cand_logged", set())
            if _rev_key in _seen_rev:
                continue
            _seen_rev.add(_rev_key)
            self._rev_cand_logged = _seen_rev

            logger.info(
                "REVERSAL_CAND %s dom=%s(%.3f) underdog=%s(%.3f) δ=%+.3f%% "
                "against_%s rem=%.0fs — shadow logging, no trade",
                token.asset, token.side, dom_ask,
                underdog_token.side if underdog_token else "?", underdog_ask,
                _delta, _dom_dir, remaining,
            )

            asyncio.create_task(
                self._monitor_reversal_candidate(
                    underdog_id=underdog_id,
                    underdog_ask=underdog_ask,
                    dominant_ask=dom_ask,
                    dominant_side=token.side,
                    asset=token.asset,
                    delta_pct=_delta,
                    remaining_s=remaining,
                    window_end_ts=token.window_end_ts,
                    window_seconds=getattr(token, "window_seconds", 0),
                ),
                name=f"rev_monitor_{token.asset}",
            )

    async def _monitor_reversal_candidate(
        self,
        underdog_id: str,
        underdog_ask: float,
        dominant_ask: float,
        dominant_side: str,
        asset: str,
        delta_pct: float,
        remaining_s: float,
        window_end_ts: float,
        window_seconds: int,
    ) -> None:
        """Track underdog price snapshots after REVERSAL_CAND detection."""
        from analytics.reversal_log import log_reversal_cand

        ts_detected = time.time()

        async def _snap(delay_s: float) -> float | None:
            await asyncio.sleep(delay_s)
            ob = self.feed.get_order_book(underdog_id)
            if ob and ob.asks:
                return ob.asks[0][0]
            return None

        ask_10s = await _snap(10.0)
        ask_20s = await _snap(10.0)   # cumulative 20s
        ask_30s = await _snap(10.0)   # cumulative 30s

        # Wait until just after window end
        wait_to_end = (window_end_ts + 4.0) - time.time()
        if wait_to_end > 0:
            await asyncio.sleep(min(wait_to_end, 200.0))

        ask_final: float | None = None
        ob = self.feed.get_order_book(underdog_id)
        if ob and ob.asks:
            ask_final = ob.asks[0][0]

        log_reversal_cand(
            ts=ts_detected,
            asset=asset,
            dominant_side=dominant_side,
            dominant_ask=dominant_ask,
            underdog_token_id=underdog_id,
            underdog_ask=underdog_ask,
            delta_pct=delta_pct,
            remaining_s=remaining_s,
            window_seconds=window_seconds,
            ask_at_10s=ask_10s,
            ask_at_20s=ask_20s,
            ask_at_30s=ask_30s,
            ask_at_window_end=ask_final,
        )

    async def _scan_for_signals(self) -> None:
        if not SNIPER_ENABLED and not MOM_ENABLED:
            return
        from strategy.sniper_runner import scan_signals
        await scan_signals(self)

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter_position(self, token_id, asset, signal, tpsl, decision,
                              llm_rec: str = "", llm_rec_conf: float = 0.0) -> None:
        # Synchronous guard (no await before this) — prevents race between spike path
        # and sweep both approving the same token. _pending_entries is checked and set
        # atomically before any await point, so asyncio single-thread makes this safe.
        if token_id in self.risk.open_positions or token_id in self._pending_entries:
            logger.warning(
                "ENTRY GUARD %s/%s — already open or pending (token), skipping duplicate",
                asset, token_id[:8],
            )
            return
        # Asset-level guard: catches spike+scan race where different token_ids
        # for the same asset both pass the token-level check above.
        if asset in self._pending_asset_entries:
            logger.warning(
                "ENTRY GUARD %s — already pending entry for this asset, skipping duplicate",
                asset,
            )
            return
        for pos in self.risk.open_positions.values():
            if pos.asset == asset:
                logger.warning("ENTRY GUARD %s — already have open position, skipping", asset)
                return
        self._pending_entries.add(token_id)
        self._pending_asset_entries.add(asset)
        try:
            await self._enter_position_inner(token_id, asset, signal, tpsl, decision,
                                             llm_rec=llm_rec, llm_rec_conf=llm_rec_conf)
        except Exception as _entry_exc:
            # Any exception in _enter_position_inner must clear the risk manager's
            # _pending_assets lock. Without this, the asset is permanently locked
            # until restart — bot stops entering that asset silently.
            self.risk._pending_assets.discard(asset)
            # Same for condition dedup: exception before fill means no trade happened.
            _cid_exc = getattr(self.feed.tokens.get(token_id), "condition_id", "")
            if _cid_exc:
                self.risk._traded_conditions.discard(_cid_exc)
            logger.error(
                "ENTRY EXCEPTION %s — _pending_assets cleared, re-raising: %s",
                asset, _entry_exc,
            )
            raise
        finally:
            self._pending_entries.discard(token_id)
            self._pending_asset_entries.discard(asset)

    async def _enter_position_inner(self, token_id, asset, signal, tpsl, decision,
                                    llm_rec: str = "", llm_rec_conf: float = 0.0) -> None:
        capital_before = self.risk.bankroll.capital
        ts_open = time.time()

        # Capture entry-context data before placing order
        _ext_entry = self._last_ext_signals.get(asset)
        spot_at_entry = _ext_entry.spot_price if _ext_entry and _ext_entry.spot_price else 0.0
        pre_entry_momentum_pct = _ext_entry.spot_momentum_1m if _ext_entry and _ext_entry.spot_momentum_1m else 0.0
        _ob_entry = self.feed.get_order_book(token_id)
        ob_depth_at_entry = 0.0
        if _ob_entry:
            _bid_depth = sum(qty for _, qty in (_ob_entry.bids[:5] if _ob_entry.bids else []))
            _ask_depth = sum(qty for _, qty in (_ob_entry.asks[:5] if _ob_entry.asks else []))
            ob_depth_at_entry = _bid_depth + _ask_depth

        if ob_depth_at_entry == 0.0:
            logger.warning("OB_DEPTH_GATE %s: no cached order book at entry, skipping", asset)
            self._pending_entries.discard(token_id)
            self._pending_asset_entries.discard(asset)
            return
        if ob_depth_at_entry < 50:
            logger.warning("OB_DEPTH_GATE %s: ob_depth=%.1f < 50 (45%% NO-resolution rate), skipping", asset, ob_depth_at_entry)
            self._pending_entries.discard(token_id)
            self._pending_asset_entries.discard(asset)
            return

        token_meta = self.feed.tokens.get(token_id)
        self._buy_tried += 1
        fill = await self.orders.market_buy(
            token_id=token_id,
            intended_price=signal.entry_price,
            stake_usd=decision.stake,
            direction=signal.direction,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
        )

        if fill.avg_fill_price == 0:
            reason = fill.error or "unknown"
            self._buy_failed_reasons[reason] = self._buy_failed_reasons.get(reason, 0) + 1
            logger.error("Fill failed for %s: %s", asset, reason)
            self.risk._pending_assets.discard(asset)  # release lock on fill failure
            # Release condition dedup lock: the trade never actually happened, so
            # the same condition must be eligible for re-entry on the next signal.
            _cid_fail = getattr(self.feed.tokens.get(token_id), "condition_id", "")
            if _cid_fail:
                self.risk._traded_conditions.discard(_cid_fail)
            return

        # Slippage guard: two tiers.
        # Tier 1 (entry_slip_cap): fill is >3.5% ABOVE the signal price — we paid more
        # than expected, meaning PM moved up between signal and fill. Our fair-value
        # model used the pre-fill price; the entry is now anchored to a worse basis.
        # At 3.5% above signal price the fee-adjusted edge is materially degraded.
        # (Different from Tier 2: Tier 1 = fill too expensive; Tier 2 = fill too cheap)
        #
        # PREVIOUS BEHAVIOR (WRONG): sell immediately on slip cap breach.
        # Problem: the fill already happened — selling immediately adds another round
        # of fees and potentially exits at a worse price (observed: fill=0.64, sold=0.56
        # → -12.5% loss on a position that would have won). 2026-04-14.
        # NEW BEHAVIOR: warn and continue tracking at actual fill price. The fill is done,
        # the edge still exists (slightly reduced). Normal exit logic manages it.
        _slip_cap = self.risk.exec_cfg.entry_slip_cap  # 0.035 = 3.5%
        _slip_above = (fill.avg_fill_price - signal.entry_price) / signal.entry_price if signal.entry_price > 0 else 0
        if _slip_above > _slip_cap:
            logger.warning(
                "ENTRY_SLIP_CAP %s: fill=%.4f vs signal=%.4f (+%.1f%% > cap %.1f%%) "
                "— tracking at fill price (position already open, selling would lose more)",
                asset, fill.avg_fill_price, signal.entry_price,
                _slip_above * 100, _slip_cap * 100,
            )

        # Tier 2: if fill is >10¢ below limit, the market moved hard against
        # us mid-order — signal is invalidated. Close immediately rather than enter
        # a position anchored to a stale thesis. (T00026: limit=0.495 fill=0.310)
        slippage_on_entry = signal.entry_price - fill.avg_fill_price
        if slippage_on_entry >= 0.10:
            self._buy_failed_reasons["slippage_abort"] = \
                self._buy_failed_reasons.get("slippage_abort", 0) + 1
            logger.warning(
                "SLIPPAGE ABORT %s: fill=%.4f vs limit=%.4f (slippage=%.4f >= 0.10) "
                "— market moved against signal mid-order, not opening position",
                asset, fill.avg_fill_price, signal.entry_price, slippage_on_entry,
            )
            # Immediately sell back what we just bought to recover capital.
            # If the sell fails (exception), fall through to track the position normally
            # rather than leaving tokens in the wallet as an untracked orphan.
            _token_meta_sa = self.feed.tokens.get(token_id)
            try:
                await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=fill.total_size,
                    current_price=fill.avg_fill_price,
                    reason="SLIPPAGE_ABORT",
                    neg_risk=getattr(_token_meta_sa, "neg_risk", False),
                    tick_size=getattr(_token_meta_sa, "tick_size", "0.01"),
                )
                self.risk._pending_assets.discard(asset)  # release lock on slippage abort
                return
            except Exception as _sa_exc:
                logger.error(
                    "SLIPPAGE_ABORT cascade_sell failed for %s (%s) — "
                    "tracking position at fill price instead to avoid orphan",
                    asset, _sa_exc,
                )
                # Fall through: open_position() below will track it and clear _pending_assets

        self._buy_filled += 1

        # Fill quality log: tracks gap between signal ask and actual fill for all BOND entries.
        # Existing SLIPPAGE_ABORT fires at >0.10 below signal; this covers the 0–0.10 gray zone.
        # T03720 (2026-05-05): signal=0.83 fill=0.73 slip=0.10 — just missed the abort threshold.
        if getattr(signal, "signal_source", "") == "BOND" or True:
            _fill_gap = signal.entry_price - fill.avg_fill_price
            if abs(_fill_gap) > 0.005:
                logger.info(
                    "[BOND] fill_quality %s: fill=%.4f signal=%.4f gap=%+.4f (%+.1f%%)",
                    asset, fill.avg_fill_price, signal.entry_price,
                    -_fill_gap, -_fill_gap / signal.entry_price * 100 if signal.entry_price else 0,
                )

        # Use actual fill cost as stake — CLOB 5-share minimum may require more than
        # the risk-approved stake (e.g. $1 stake but minimum order is $3.45 at price 0.69).
        actual_stake = fill.avg_fill_price * fill.total_size
        if actual_stake <= 0:
            actual_stake = decision.stake  # fallback to approved stake if fill data incomplete

        # Recalculate TP/SL from actual fill price if it differs significantly from the
        # limit price (>2 ticks). Pre-fill tpsl uses signal.entry_price which can be
        # far from actual fill when the market moves between signal and execution —
        # e.g. limit=0.495 fill=0.310 would put SL=0.480 above entry, triggering instantly.
        token = self.feed.tokens.get(token_id)
        fill_slippage = abs(fill.avg_fill_price - signal.entry_price)
        if fill_slippage > 0.02:
            ob_now = self.feed.get_order_book(token_id)
            bars_now = self.feed.get_bars_5m(token_id)
            tpsl = calculate_tp_sl(fill.avg_fill_price, signal.direction, bars_now, ob_now)
            logger.info(
                "TP/SL recalculated from actual fill %.4f (limit was %.4f, slippage=%.4f): "
                "TP=%.4f SL=%.4f",
                fill.avg_fill_price, signal.entry_price, fill_slippage,
                tpsl.take_profit, tpsl.stop_loss,
            )

        pos = self.risk.open_position(
            token_id=token_id,
            asset=asset,
            direction=signal.direction,
            stake=actual_stake,
            entry_price=fill.avg_fill_price,
            tpsl=tpsl,
            condition_id=getattr(token, "condition_id", ""),
            window_end_ts=getattr(token, "window_end_ts", 0.0),
            window_seconds=getattr(token, "window_seconds", 0),
            quality_score=getattr(signal, "quality_score", 0),
            binance_price_at_entry=(
                self.feed._spot_price.get(asset.upper(), 0.0)
                or spot_at_entry  # fallback: ext signal spot price captured before order
            ),
            entry_delta_pct=abs(getattr(signal, "delta_pct", 0.0)) / 100,  # convert % → fraction
            entry_lag_pct=getattr(signal, "lag_remaining_pct", 0.0),
            entry_fair_value=getattr(signal, "fair_value", 0.0),
            is_bond=getattr(signal, "is_bond", False),
            bond_exit_sec=getattr(signal, "bond_exit_sec", 0),
            bond_outcome_direction=getattr(signal, "bond_outcome_direction", "down"),
            bond_entry_class=getattr(signal, "bond_entry_class", ""),
            bond_macro_regime=getattr(signal, "bond_macro_regime", ""),
        )

        # Verify actual CLOB balance immediately after fill — CLOB may credit slightly
        # fewer shares than stake/price due to rounding or fee deduction from token amount.
        # Using the authoritative balance eliminates "not enough balance" errors at exit
        # and ensures the cascade sells exactly what we own, not what we computed we own.
        if not CONFIG.dry_run:
            _clob_balance = self.orders.fetch_token_balance(token_id)
            if _clob_balance is not None and _clob_balance > 0:
                computed = pos.shares
                if abs(_clob_balance - computed) > 0.05:
                    logger.info(
                        "BALANCE VERIFY %s: computed=%.4f CLOB=%.4f — using CLOB value",
                        asset, computed, _clob_balance,
                    )
                pos.shares = round(_clob_balance, 4)
                pos.remaining_shares = round(_clob_balance, 4)
            else:
                logger.warning(
                    "BALANCE VERIFY %s: CLOB returned %.4f — keeping computed %.4f",
                    asset, _clob_balance or 0.0, pos.shares,
                )
            # FIX: double-fill orphan prevention. CF retry loop can place 2-3 orders that
            # all fill; the initial balance check above may miss fills that haven't
            # propagated to the CLOB read-replica yet (typically <1s latency).
            # Recheck after 1.5s to absorb any late-arriving duplicate fill tokens into
            # the tracked position so normal exit logic sells them all (no orphans).
            asyncio.create_task(self._deferred_balance_sync(token_id, asset))

        signal_to_fill_ms = (time.time() - ts_open) * 1000.0
        _vel_5s, _ = self.feed.get_velocity_5s(asset)
        # Prefer scan-loop ask history for move_age (WS ticks too sparse → 999 for 97% of trades).
        _tok_hist_ep = self._token_ask_history.get(token_id)
        _entry_ask = getattr(signal, "entry_price", None) or getattr(signal, "token_ask", None)
        if _tok_hist_ep and _entry_ask:
            _hist_ep = list(_tok_hist_ep)
            _token_move_age = 999.0
            for _hts, _hp in reversed(_hist_ep):
                if abs(_hp - _entry_ask) > 0.005:
                    _token_move_age = round(time.time() - _hts, 1)
                    break
            else:
                if _hist_ep:
                    _token_move_age = round(time.time() - _hist_ep[0][0], 1)
        else:
            _token_move_age = self.feed.get_token_move_age(token_id)

        self._open_meta[token_id] = {
            "signal": signal,
            "signal_source": getattr(signal, "signal_source", "SNIPER")
                             if hasattr(signal, "delta_pct") else "MOMENTUM",
            "entry_fill": fill,
            "ts_open": ts_open,
            "capital_before": capital_before,
            "heat_check": decision.is_scaled,
            "consecutive_wins": self.risk.bankroll.consecutive_wins,
            "window_size_s": getattr(token, "window_seconds", 0) or pos.window_seconds,
            "spot_at_entry": spot_at_entry,
            "pre_entry_momentum_pct": pre_entry_momentum_pct,
            "ob_depth_at_entry": ob_depth_at_entry,
            "signal_to_fill_ms": signal_to_fill_ms,
            "llm_rec": llm_rec,
            "llm_rec_conf": llm_rec_conf,
            "velocity_5s_pct": _vel_5s,
            "move_age_s": _token_move_age,
        }

        # Persist term_ signal fields so they survive a bot restart.
        # On restart _open_meta is empty; _exit_position reads this back
        # and stamps the recovered fields onto the SignalBreakdown stub.
        _term_fields = [
            "term_vpin", "term_binance_1m_pct", "term_binance_5m_pct", "term_binance_60m_pct",
            "term_spot_delta_5s", "term_spot_delta_30s", "term_spot_delta_60s",
            "term_spot_delta_5m", "term_ask_spread_pct", "term_ask_qty",
            "term_ob_imbalance", "term_ob_depth", "term_remaining_s",
            "term_token_delta_3s", "term_token_delta_5s", "term_tok_tick_count_5s",
            "term_tok_tick_count_30s", "term_ask_stale_s", "term_tok_decel_ratio",
            "term_token_delta_30s", "term_token_delta_60s",
            "term_pre_snap_60s", "term_pre_snap_30s", "term_pre_snap_open",
            "term_rsi", "term_ask_vwap",
            "bond_has_hist", "bond_accel_sustained", "bond_outcome_direction",
        ]
        _sig_snapshot = {f: getattr(signal, f, None) for f in _term_fields}
        try:
            _smf = "logs/open_signal_meta.json"
            _sm = {}
            if os.path.exists(_smf):
                with open(_smf) as _f:
                    _sm = json.load(_f)
            _sm[token_id] = _sig_snapshot
            with open(_smf + ".tmp", "w") as _f:
                json.dump(_sm, _f)
            os.replace(_smf + ".tmp", _smf)
        except Exception as _e:
            logger.debug("open_signal_meta write failed: %s", _e)

        # BOND: time exit at T-30s
        _bond_wend = getattr(self.feed.tokens.get(token_id), "window_end_ts", 0.0)
        if _bond_wend > 0 and pos is not None:
            asyncio.create_task(
                self._bond_precise_timer(token_id, _bond_wend, pos.bond_exit_sec or 30),
                name=f"bond_timer_{token_id[:8]}",
            )

    # ── LLM independent trader ───────────────────────────────────────────────

    def _read_llm_shadow_history(self, n: int = 15) -> list:
        """
        Read the last n completed (entry + exit joined) LLM decisions from
        logs/llm_shadow.jsonl for history injection into bond_advisor calls.

        Returns a list of dicts (newest first), each containing the entry
        fields merged with exit outcome fields (exit_reason, shadow_gross_pnl).
        Open positions (no exit yet) are included as partial records so the LLM
        can see its most recent choices even if outcomes aren't known yet.
        """
        import json as _json
        import os as _os
        _path = _os.path.join(
            _os.path.dirname(self.analytics.cfg.trade_log), "llm_shadow.jsonl"
        )
        if not _os.path.exists(_path):
            return []
        try:
            entries: dict = {}
            exits: dict = {}
            with open(_path) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if not _line:
                        continue
                    try:
                        _r = _json.loads(_line)
                    except _json.JSONDecodeError:
                        continue
                    _tid = _r.get("token_id", "")
                    if _r.get("record_type") == "llm_entry":
                        entries[_tid] = _r
                    elif _r.get("record_type") == "llm_exit":
                        exits[_tid] = _r

            merged = []
            for _tid, _e in entries.items():
                if _tid in exits:
                    merged.append({**_e, **exits[_tid]})
                else:
                    merged.append(_e)

            # Newest first, cap at n
            merged.sort(key=lambda x: x.get("ts", 0), reverse=True)
            return merged[:n]
        except Exception as _exc:
            logger.debug("_read_llm_shadow_history failed: %s", _exc)
            return []

    def _read_research_notes(self, n: int = 10) -> list:
        """Return the n most recent research findings for injection into bond_advisor."""
        import json as _json, os as _os
        _path = _os.path.join(
            _os.path.dirname(self.analytics.cfg.trade_log), "research_notes.jsonl"
        )
        if not _os.path.exists(_path):
            return []
        try:
            rows = []
            with open(_path) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line:
                        try:
                            rows.append(_json.loads(_line))
                        except Exception:
                            pass
            rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
            return rows[:n]
        except Exception as _exc:
            logger.debug("_read_research_notes failed: %s", _exc)
            return []

    def _write_llm_shadow(self, record: dict) -> None:
        import json as _json
        import os as _os
        _path = _os.path.join(
            _os.path.dirname(self.analytics.cfg.trade_log), "llm_shadow.jsonl"
        )
        try:
            with open(_path, "a") as _f:
                _f.write(_json.dumps(record) + "\n")
        except Exception as _exc:
            logger.debug("_write_llm_shadow failed: %s", _exc)

    async def _bond_llm_independent_eval(
        self,
        token_id: str,
        asset: str,
        direction: str,
        entry_price: float,
        zone: str,
        entry_class_hint: str,
        bond_delta: float,
        delta_accel: float,
        edge_drift: float,
        smooth_delta: float,
        vpin: float,
        edge: float,
        adjusted_edge: float,
        macro_regime: str,
        has_hist: bool,
        window_end_ts: float,
        window_size_s: int,
        remaining_s: float,
    ) -> None:
        """
        Fully independent LLM trader. Called pre-gate on every BOND candidate.

        The LLM sees raw signals only — no rule thresholds, no gate names.
        It decides TAKE/SKIP with its own TP% and SL%. Decision is stored in
        _llm_ind_decisions[token_id]; next scan cycle picks it up and enters a
        real trade (TAKE) or continues silently (SKIP).
        Results also logged to logs/llm_shadow.jsonl for analysis.
        """
        self._llm_eval_pending.add(token_id)
        now = time.time()
        recent_history = self._read_llm_shadow_history(n=15)
        research_notes = self._read_research_notes(n=10)
        # Skip immediately if we're in a rate-limit cooldown
        if time.time() < self._llm_rate_limit_until:
            self._llm_eval_pending.discard(token_id)
            return

        try:
            async with self._llm_eval_semaphore:
                if time.time() < self._llm_rate_limit_until:
                    return  # cooldown set while waiting for semaphore
                result = await self.macro_engine.bond_advisor(
                    asset=asset,
                    direction="BUY_YES" if direction == "YES" else "BUY_NO",
                    entry_price=entry_price,
                    bond_entry_class=entry_class_hint,
                    bond_entry_zone=zone,
                    bond_delta_at_entry=bond_delta,
                    bond_delta_accel_30s=delta_accel,
                    bond_edge_drift_30s=edge_drift,
                    bond_smooth_delta_60s=smooth_delta,
                    vpin=vpin,
                    edge=edge,
                    window_size_s=window_size_s,
                    window_remaining_s=remaining_s,
                    recent_history=recent_history,
                    research_notes=research_notes,
                )
        except _RateLimitError as _rle:
            self._llm_rate_limit_until = time.time() + _rle.retry_after
            logger.warning("LLM_EVAL 429 %s/%s — cooldown %.0fs", asset, direction, _rle.retry_after)
            return  # don't store decision; token retries after cooldown
        finally:
            self._llm_eval_pending.discard(token_id)

        # Store decision for next scan cycle to consume
        result["ts"] = now
        self._llm_ind_decisions[token_id] = result

        self._write_llm_shadow({
            "record_type": "llm_entry",
            "ts": now,
            "token_id": token_id,
            "asset": asset,
            "direction": direction,
            "entry_price": entry_price,
            "zone": zone,
            "entry_class": entry_class_hint,
            "bond_delta": round(bond_delta, 4),
            "delta_accel": round(delta_accel, 4),
            "edge_drift": round(edge_drift, 4),
            "smooth_delta": round(smooth_delta, 4),
            "vpin": round(vpin, 3),
            "edge": round(edge, 4),
            "adjusted_edge": round(adjusted_edge, 4),
            "macro_regime": macro_regime,
            "has_hist": has_hist,
            "window_end_ts": window_end_ts,
            "window_size_s": window_size_s,
            "remaining_s": round(remaining_s, 0),
            "stake_assumed": self.risk.bankroll.current_stake,
            "llm_decision": result["decision"],
            "llm_conf": result.get("conf", 0.5),
            "llm_reason": result.get("reason", ""),
            "llm_tp_pct": result.get("shadow_tp_pct", 0.0),
            "llm_sl_pct": result.get("shadow_sl_pct", 0.0),
        })

        elapsed = time.time() - now
        logger.info(
            "LLM_EVAL %s/%s → %s conf=%.2f edge=%s call=%.1fs rem≈%.0fs | %s",
            asset, direction, result["decision"],
            result.get("conf", 0.5),
            result.get("edge_type", "?"),
            elapsed, remaining_s - elapsed,
            result.get("reason", ""),
        )

    # ── BOND LLM adaptive exit poller ────────────────────────────────────────

    async def _bond_llm_exit_eval(
        self,
        token_id: str,
        pos,
        current_price: float,
        bond_delta: float,
        vpin: float,
        remaining_s: float,
    ) -> None:
        """
        Ask Opus: EXIT or HOLD on this open BOND position?
        Fires every 10s (5s when <60s remaining). Result stored in
        _llm_exit_decisions[token_id] and consumed on the next scan.
        """
        self._llm_exit_pending.add(token_id)
        try:
            _held = time.time() - pos.open_ts
            _pnl_pct = ((current_price - pos.entry_price) / pos.entry_price * 100
                        if pos.entry_price > 0 else 0.0)
            _llm_rec = self._bond_llm_decisions.get(token_id, {})
            result = await self.macro_engine.bond_exit_advisor(
                asset=pos.asset,
                direction=pos.direction.name,
                entry_price=pos.entry_price,
                current_price=current_price,
                pnl_pct=_pnl_pct,
                held_s=_held,
                remaining_s=remaining_s,
                bond_delta=bond_delta,
                vpin=vpin,
                entry_reason=_llm_rec.get("reason", ""),
                entry_tp_pct=float(_llm_rec.get("shadow_tp_pct", 0.0) or 0.0),
                entry_sl_pct=float(_llm_rec.get("shadow_sl_pct", 0.0) or 0.0),
                position_type=_llm_rec.get("position_type", "momentum"),
                expected_duration_sec=float(_llm_rec.get("expected_duration_sec", 180) or 180),
                edge_type=_llm_rec.get("edge_type", "continuation"),
                highest_price=pos.highest_price,
                lowest_price=pos.lowest_price,
                recent_history=self._read_llm_shadow_history(n=15),
                research_notes=self._read_research_notes(n=5),
            )
            self._llm_exit_decisions[token_id] = result
            self._llm_exit_last_eval[token_id] = time.time()
        except Exception as _exc:
            logger.debug("_bond_llm_exit_eval error (%s)", _exc)
        finally:
            self._llm_exit_pending.discard(token_id)

    # ── BOND LLM shadow advisor ───────────────────────────────────────────────

    async def _bond_llm_advisor(
        self, token_id: str, signal, pos, entry_price: float
    ) -> None:
        """
        Non-blocking LLM shadow advisor for BOND entries. Fires after position opens,
        stores decision in _bond_llm_decisions[token_id] for logging at close.
        Never cancels or modifies the trade — pure observation and data collection.
        """
        window_remaining_s = max(0.0, pos.window_end_ts - time.time()) if pos.window_end_ts > 0 else 0.0
        try:
            result = await self.macro_engine.bond_advisor(
                asset=pos.asset,
                direction=pos.direction.name,
                entry_price=entry_price,
                bond_entry_class=getattr(signal, "bond_entry_class", ""),
                bond_entry_zone=getattr(signal, "bond_entry_zone", ""),
                bond_delta_at_entry=float(getattr(signal, "bond_delta_at_entry", 0.0) or 0.0),
                bond_delta_accel_30s=float(getattr(signal, "bond_delta_accel_30s", 0.0) or 0.0),
                bond_edge_drift_30s=float(getattr(signal, "bond_edge_drift_30s", 0.0) or 0.0),
                bond_smooth_delta_60s=float(getattr(signal, "bond_smooth_delta_60s", 0.0) or 0.0),
                vpin=float(getattr(signal, "vpin", 0.0) or 0.0),
                edge=float(getattr(signal, "edge", 0.0) or 0.0),
                window_size_s=int(pos.window_seconds or 900),
                window_remaining_s=window_remaining_s,
            )
            self._bond_llm_decisions[token_id] = result
        except Exception as exc:
            logger.debug("_bond_llm_advisor task error (%s)", exc)
            self._bond_llm_decisions[token_id] = {"decision": "", "conf": 0.0, "reason": "task error"}

    # ── TERMINAL window-final-price snapshot ─────────────────────────────────

    async def _record_terminal_final_price(
        self,
        token_id: str,
        asset: str,
        side: str,
        window_end_ts: float,
        entry_ask: float,
    ) -> None:
        """Sleep until T-1s, capture token ask, write to logs/window_final_prices.jsonl."""
        delay = window_end_ts - 1.0 - time.time()
        if delay > 0.05:
            await asyncio.sleep(delay)
        ob = self.feed.get_order_book(token_id)
        final_price: Optional[float] = ob.asks[0][0] if (ob and ob.asks) else None
        if final_price is None:
            hist = self._token_ask_history.get(token_id)
            if hist:
                final_price = hist[-1][1]
        if final_price is None:
            logger.debug("wfp: no price for %s/%s at T-1s", asset, side)
            return
        record = {
            "token_id": token_id,
            "asset": asset,
            "side": side,
            "window_end_ts": round(window_end_ts, 3),
            "entry_ask": entry_ask,
            "final_price": round(final_price, 4),
            "recorded_at": round(time.time(), 3),
        }
        try:
            import json as _json_wfp
            with open("logs/window_final_prices.jsonl", "a") as _wfp_f:
                _wfp_f.write(_json_wfp.dumps(record) + "\n")
        except Exception as _wfp_exc:
            logger.warning("wfp log failed: %s", _wfp_exc)

    # ── BOND precise timer ────────────────────────────────────────────────────

    async def _bond_precise_timer(
        self, token_id: str, window_end_ts: float, exit_sec: int
    ) -> None:
        """Sleeps until window_end_ts - exit_sec, then fires unconditional TIME_EXIT."""
        wait_s = (window_end_ts - exit_sec) - time.time()
        if wait_s > 0:
            await asyncio.sleep(wait_s)

        if token_id not in self.risk.open_positions:
            return
        pos = self.risk.open_positions.get(token_id)
        if pos is None or not getattr(pos, "is_bond", False):
            return
        if token_id in self._exit_in_progress:
            return

        ob = self.feed.get_order_book(token_id)
        current_price = (
            ob.bids[0][0] if (ob and ob.bids)
            else (pos.entry_price if pos else 0.50)
        )
        actual_remaining = max(0.0, window_end_ts - time.time())
        logger.info(
            "BOND_TIMER %s: precise exit firing | remaining=%.1fs target=T-%ds",
            pos.asset if pos else token_id[:8], actual_remaining, exit_sec,
        )
        self._exit_in_progress.add(token_id)
        try:
            await self._exit_position(token_id, current_price, "BOND_TIME_EXIT")
        finally:
            self._exit_in_progress.discard(token_id)

    # ── Double-fill protection ────────────────────────────────────────────────

    async def _deferred_balance_sync(self, token_id: str, asset: str, delay: float = 1.5) -> None:
        """
        Re-check CLOB token balance 1.5s after position open to absorb any
        CF-retry double-fill shares that hadn't propagated to the read-replica yet.

        Race scenario: CF 403 on attempt-0 → sleep 0.5s → pop_fill_for_token
        finds nothing (WS latency ~400ms) → attempt-1 also fills → position opened
        with attempt-1's shares → attempt-0's tokens arrive in wallet ~200ms later →
        initial balance check misses them → they become orphans at window-end.

        This deferred check runs after the propagation window and absorbs the extra
        shares into the tracked position so the normal exit logic sells all of them.
        """
        await asyncio.sleep(delay)
        if CONFIG.dry_run:
            return
        pos = self.risk.open_positions.get(token_id)
        if pos is None:
            return  # position already closed before recheck fired
        balance = self.orders.fetch_token_balance(token_id)
        if balance is not None and balance > pos.remaining_shares + 0.05:
            extra = round(balance - pos.remaining_shares, 4)
            logger.warning(
                "DEFERRED BALANCE SYNC %s: %.4f tracked → %.4f CLOB "
                "(%.4f extra shares from CF-retry double-fill — absorbed into position)",
                asset, pos.remaining_shares, balance, extra,
            )
            pos.shares = round(balance, 4)
            pos.remaining_shares = round(balance, 4)

    # ── Exit helpers ──────────────────────────────────────────────────────────

    def _calc_exit_price(self, exit_fills, fallback: float) -> float:
        # Only include fills that have a confirmed price. WS-confirmation misses
        # leave avg_fill_price=0 on the OrderResult; including those zeros dilutes
        # the weighted average (0 × shares adds to denominator, not numerator).
        valid = [f for f in exit_fills if f.avg_fill_price > 0 and f.total_size > 0]
        total_size = sum(f.total_size for f in valid)
        return (
            sum(f.avg_fill_price * f.total_size for f in valid) / total_size
            if valid and total_size > 0 else fallback
        )

    async def _bond_partial_tp_sell(
        self,
        token_id: str,
        fraction: float,
        current_price: float,
        reason: str,
    ) -> None:
        """Sell `fraction` of remaining BOND shares as a partial TP capture.
        Does NOT close the position — remaining shares continue under SL/trailing.
        """
        pos = self.risk.open_positions.get(token_id)
        if not pos or pos.remaining_shares < 0.05:
            return
        token_meta = self.feed.tokens.get(token_id)
        sell_shares = round(pos.remaining_shares * fraction, 4)
        if sell_shares < 0.01:
            return
        fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=sell_shares,
            current_price=current_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,
        )
        sold = sum(f.total_size for f in fills)
        fill_price = self._calc_exit_price(fills, current_price)
        if sold > 0:
            pos.remaining_shares = max(0.0, round(pos.remaining_shares - sold, 4))
            self.risk._save_positions()
            # Store BOND partial-TP fills so when TIME_EXIT later calls _exit_position
            # the weighted-avg exit price includes these tranches. Without this the
            # final exit's analytics_exit_price falls back to entry_price when the
            # final cascade returns 0 fills (resting / already sold) → trade logged
            # at ep=xp with fee-only PnL even though real partial profits happened.
            meta = self._open_meta.get(token_id)
            if meta is not None:
                meta.setdefault("stage1_fills", []).extend(fills)
            logger.info(
                "BOND_PARTIAL_TP %s/%s [%s] sold=%.4f @ %.4f remaining=%.4f "
                "entry=%.4f gain=%+.1f%%",
                pos.asset, pos.direction.name, reason,
                sold, fill_price, pos.remaining_shares,
                pos.entry_price,
                (current_price - pos.entry_price) / pos.entry_price * 100,
            )
        else:
            logger.warning(
                "BOND_PARTIAL_TP %s/%s [%s] 0 fills — will retry next scan",
                pos.asset, pos.direction.name, reason,
            )

    async def _partial_exit(self, token_id: str, live_price: float, reason: str) -> None:
        """Stage-1: sell 60%, leave 40% for stage-2 with floor stop at cost+12%."""
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        # 60/40 split: sell 60% at stage-1, leave 40% riding to stage-2 (+35% target).
        # Floor stop at cost+12% protects the 40% from reversing to a loss.
        residual_value = pos.remaining_shares * 0.40 * live_price
        sell_pct = 0.60 if residual_value >= 1.50 else 1.0
        if sell_pct == 1.0:
            logger.info(
                "Stage-1 selling 100%% — 40%% residual=$%.2f < $1.50 CLOB minimum",
                residual_value,
            )

        token_meta = self.feed.tokens.get(token_id)
        sell_shares = round(pos.remaining_shares * sell_pct, 4)
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=sell_shares,
            current_price=live_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,  # P5: single-shot — eliminates 3-tranche CLOB lag partial-sell bug
        )
        sold = sum(f.total_size for f in exit_fills)

        if sold == 0:
            # Reconcile against actual CLOB balance — fills may have landed on Polymarket
            # but WS confirmation was dropped. Without this, bot retries with stale quantity,
            # CLOB rejects (insufficient balance), shares left unsold at window resolution.
            actual_balance = self.orders.fetch_token_balance(token_id)
            if actual_balance is not None:
                discrepancy = pos.remaining_shares - actual_balance
                if discrepancy > 0.05:
                    logger.warning(
                        "FILL RECONCILE %s/%s: bot=%.4f shares CLOB=%.4f — "
                        "%.4f sold without confirmation, updating tracking",
                        pos.asset, pos.direction.name,
                        pos.remaining_shares, actual_balance, discrepancy,
                    )
                    pos.remaining_shares = round(actual_balance, 4)
                if actual_balance < 0.05:
                    logger.info(
                        "FILL RECONCILE %s/%s: CLOB balance=0 — all shares sold, "
                        "forcing STAGE_1_DONE",
                        pos.asset, pos.direction.name,
                    )
                    pos.exit_stage = ExitStage.STAGE_1_DONE
                    return

            pos.stage1_attempts += 1
            if pos.stage1_attempts >= 3:
                logger.warning(
                    "STAGE-1 FORCE-DONE %s/%s: %d failed attempts (0 fills each) — "
                    "forcing STAGE_1_DONE, hard exit will close remaining %.4f shares",
                    pos.asset, pos.direction.name, pos.stage1_attempts, pos.remaining_shares,
                )
                pos.exit_stage = ExitStage.STAGE_1_DONE
            else:
                logger.warning(
                    "STAGE-1 ZERO FILLS %s/%s (attempt %d/3) — will retry next scan",
                    pos.asset, pos.direction.name, pos.stage1_attempts,
                )
            return

        s1_fill_price = self._calc_exit_price(exit_fills, live_price)
        self.risk.record_stage1_sell(token_id, sold, sell_price=s1_fill_price)
        # Store stage-1 fills so analytics can compute accurate weighted exit price
        meta = self._open_meta.get(token_id)
        if meta is not None:
            meta.setdefault("stage1_fills", []).extend(exit_fills)
        logger.info(
            "STAGE-1 %s %s | sold=%.4f @ %.4f | reason=%s",
            pos.asset, pos.direction.name, sold, s1_fill_price, reason,
        )

        # When stage-1 sold 100% (residual below $1.50 CLOB minimum), close and
        # record the trade immediately — remaining_shares=0 means stage-2 would
        # fire with an empty cascade, producing EXTERNALLY_SOLD with PnL≈0.
        _pos_after = self.risk.open_positions.get(token_id)
        if sell_pct == 1.0 and _pos_after is not None and _pos_after.remaining_shares < 0.05:
            _meta = self._open_meta.get(token_id, {})
            _all_shares = pos.shares
            _net_pnl = self.risk.close_position(
                token_id, s1_fill_price, reason, shares_override=_all_shares,
            )
            self._open_meta.pop(token_id, None)
            self._pos_log_ts.pop(token_id, None)
            if _net_pnl is not None:
                _entry_fill = _meta.get("entry_fill") or OrderResult(
                    status=OrderStatus.FILLED, avg_fill_price=pos.entry_price,
                    total_size=_all_shares, slippage=0.0,
                )
                _signal = _meta.get("signal") or SignalBreakdown(
                    direction=pos.direction, entry_price=pos.entry_price,
                    composite=0.0, confidence=0.0, breakout_score=0.0,
                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                    reason="stage1_full_exit",
                )
                _token_meta = self.feed.tokens.get(token_id)
                try:
                    self.analytics.record_trade(
                        token_id=token_id, asset=pos.asset, direction=pos.direction,
                        entry_price=pos.entry_price, exit_price=s1_fill_price,
                        stake=pos.stake, shares=_all_shares,
                        entry_fill=_entry_fill, exit_fills=exit_fills,
                        exit_reason=reason,
                        signal=_signal,
                        ts_open=_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                        capital_before=self.risk.bankroll.capital - _net_pnl,
                        heat_check_active=_meta.get("heat_check", False),
                        consecutive_wins=_meta.get("consecutive_wins", 0),
                        best_ask=pos.best_ask,
                        net_pnl_actual=_net_pnl,
                        market_type=getattr(_token_meta, "market_type", "unknown"),
                        is_live=not CONFIG.dry_run,
                        signal_source=_meta.get("signal_source", "BOND" if pos.is_bond else "SNIPER"),
                        window_size_s=_meta.get("window_size_s") or pos.window_seconds or 0,
                        spot_at_entry=_meta.get("spot_at_entry", 0.0),
                        spot_at_exit=0.0,
                        signal_to_fill_ms=_meta.get("signal_to_fill_ms", 0.0),
                        ob_depth_at_entry=_meta.get("ob_depth_at_entry", 0.0),
                        pre_entry_momentum_pct=_meta.get("pre_entry_momentum_pct", 0.0),
                        max_price_seen=pos.highest_price,
                        min_price_seen=pos.lowest_price,
                        bond_entry_class=pos.bond_entry_class,
                        bond_macro_regime=pos.bond_macro_regime,
                    )
                except Exception as _s1e:
                    logger.error("record_trade STAGE1_FULL_EXIT failed: %s", _s1e)
            return  # fully closed — skip stage-2 CLOB sync

        # CLOB balance sync: verify remaining_shares matches reality before stage-2.
        # CLOB cache lag can cause cascade_sell to fill a slightly different amount,
        # leaving remaining_shares out of sync. Sync now so stage-2 sells the right qty.
        if not CONFIG.dry_run and token_id in self.risk.open_positions:
            await asyncio.sleep(1.5)  # let CLOB balance settle
            _clob_remaining = self.orders.fetch_token_balance(token_id)
            _pos = self.risk.open_positions.get(token_id)
            if _clob_remaining is not None and _pos is not None:
                if abs(_clob_remaining - _pos.remaining_shares) > 0.05:
                    logger.warning(
                        "STAGE-1 SYNC %s/%s: tracked=%.4f CLOB=%.4f — correcting to CLOB value",
                        _pos.asset, _pos.direction.name,
                        _pos.remaining_shares, _clob_remaining,
                    )
                    _pos.remaining_shares = round(_clob_remaining, 4)
                    self.risk._save_positions()
                else:
                    logger.debug(
                        "STAGE-1 SYNC %s/%s: %.4f shares confirmed on CLOB",
                        _pos.asset, _pos.direction.name, _clob_remaining,
                    )

        # POST-STAGE1 SWEEP REMOVED:
        # Originally needed when stage-1 used 3 tranches — tranche 3 failed due to
        # CLOB balance lag, leaving shares unsold. Sweep caught them immediately.
        # Now stage-1 is single-shot (force_exit=True), so no tranche lag occurs.
        # More importantly: with 60/40 split, the 40% remaining after stage-1 is
        # INTENTIONAL stage-2 inventory. Sweep was selling it at the stale stage-1
        # price instead of letting it ride to +45% / trailing stop.

    async def _exit_position(self, token_id: str, live_price: float, reason: str) -> None:
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        # LDA never sells via CLOB for WINDOW_OUTCOME — token auto-redeems at resolution.
        # Guard at line ~1720 should catch this, but bond_entry_class can be "" on restart.
        # Defensive fallback: skip the cascade_sell entirely; BOND_SETTLED kline path closes it.
        _meta_src = self._open_meta.get(token_id, {}).get("signal_source", "")
        if reason == "WINDOW_OUTCOME" and (
            getattr(pos, "bond_entry_class", "") == "LDA" or _meta_src == "LDA"
        ):
            logger.warning(
                "LDA WINDOW_OUTCOME blocked: %s/%s — skipping CLOB sell, "
                "BOND_SETTLED kline path will record outcome",
                pos.asset, pos.direction.name,
            )
            return

        meta = self._open_meta.get(token_id, {})
        _ext_exit = self._last_ext_signals.get(pos.asset)
        spot_at_exit = _ext_exit.spot_price if _ext_exit and _ext_exit.spot_price else 0.0

        token_meta = self.feed.tokens.get(token_id)
        # Mandatory exits (TIME_EXIT, WINDOW_END, HARD_EXIT, REVERSAL, VELOCITY,
        # SIGNAL_FLIPPED, PRICE_FLOOR, CATASTROPHIC_SL) MUST fill at any cost —
        # allow 10% price stepdown so thin OBs near window close don't cause a
        # sell-resting spin loop (Guard 1 retry every 4.5s → window closes → ep=xp).
        # Profit exits (PROFIT_*, MOON_BAG*, RATCHET*, BOND_TP*) hold their price
        # and retry with a fresh OB price next scan — Guard 1 handles that cleanly.
        _PROFIT_REASONS = ("PROFIT", "MOON_BAG", "RATCHET", "BOND_TP", "BOND_EXHAUSTION", "BOND_TRAIL_SL")
        _allow_stepdown = not any(r in reason for r in _PROFIT_REASONS)
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=pos.remaining_shares,
            current_price=live_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,  # full exits must always succeed regardless of notional value
            allow_stepdown=_allow_stepdown,
        )

        # Combine stage-1 + stage-2 fills for full-position PnL accounting.
        # Must be done BEFORE close_position so bankroll uses the same weighted
        # avg price as analytics — not just the 5% stage-2 tranche.
        stage1_fills = meta.get("stage1_fills", [])
        all_exit_fills = stage1_fills + exit_fills
        sold_shares = sum(f.total_size for f in all_exit_fills)

        stage1_done = pos.exit_stage.name == "STAGE_1_DONE"
        this_sell = sum(f.total_size for f in exit_fills)   # this cascade attempt only
        expected_this_sell = pos.remaining_shares            # what we tried to sell

        # Ghost position guard: MUST run BEFORE Guard 1 (which returns early on 0 fills).
        # CLOB balance=0 means we never owned these tokens — cancel-race false positive.
        # Close at 0 immediately so bot stops retrying and capital tracking stays honest.
        # EXCEPTION: if entry_fill exists in meta, the position was real (we have proof of
        # purchase). CLOB balance=0 then means it was sold/resolved externally — reclassify
        # as EXTERNALLY_SOLD so the EXT path handles it (not recorded as full $0 loss).
        # 2026-04-16: ETH GHOST_POSITION fired on a real position that resolved externally.
        ghost_detected = any(
            "GHOST_POSITION" in (getattr(r, "error", "") or "")
            for r in exit_fills
        )
        if ghost_detected:
            _ghost_check_meta = self._open_meta.get(token_id, {})
            _has_entry_fill = _ghost_check_meta.get("entry_fill") is not None
            if _has_entry_fill:
                # Real position confirmed by entry_fill — reclassify to EXTERNALLY_SOLD
                # so EXT path uses entry_price fallback (not full $0 loss).
                logger.warning(
                    "GHOST→EXT reclassify %s/%s — entry_fill exists, position was real. "
                    "CLOB balance=0 means externally sold/resolved. Using EXT path.",
                    pos.asset, pos.direction.name,
                )
                for _r in exit_fills:
                    if "GHOST_POSITION" in (getattr(_r, "error", "") or ""):
                        _r.error = _r.error.replace("GHOST_POSITION", "EXTERNALLY_SOLD")
                # Fall through to ext_sold_detected block below
            else:
                logger.error(
                    "GHOST POSITION purged: %s/%s — stake=$%.2f recorded as total loss. "
                    "Cancel-race false positive in earlier session.",
                    pos.asset, pos.direction.name, pos.stake,
                )
                ghost_pnl = self.risk.close_position(token_id, 0.0, "GHOST_POSITION", shares_override=pos.shares)
                _ghost_meta = self._open_meta.pop(token_id, {})
                self._pos_log_ts.pop(token_id, None)
                self._dir_rev_count.pop(token_id, None)
                self._entry_snaps.pop(token_id, None)
                self._term_pre_snap_refs.pop(token_id, None)
                self._term_pre_entry_obs.pop(token_id, None)
                self._sl_below_count.pop(token_id, None)
                self._stall_checked.discard(token_id)
                self._peak_bond_move.pop(token_id, None)
                self._trough_bond_move.pop(token_id, None)
                self._peak_ts.pop(token_id, None)
                self._stall_conf_count.pop(token_id, None)
                self._exhaustion_conf_count.pop(token_id, None)
                self._early_loss_conf_count.pop(token_id, None)
                self._early_chop_count.pop(token_id, None)
                self._peak_breach_ts.pop(token_id, None)
                self._zombie_flag_ts.pop(token_id, None)
                self._traj_mfe.pop(token_id, None)
                self._traj_mae.pop(token_id, None)
                self._price_at_t10s.pop(token_id, None)
                self._traj_snap_next.pop(token_id, None)
                self._terminal_tp_touched.discard(token_id)
                if ghost_pnl is not None:
                    _ghost_signal = _ghost_meta.get("signal") or SignalBreakdown(
                        direction=pos.direction, entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="ghost_position",
                    )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=0.0,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=_ghost_meta.get("entry_fill"), exit_fills=[],
                            exit_reason="GHOST_POSITION", signal=_ghost_signal,
                            ts_open=_ghost_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital - ghost_pnl,
                            heat_check_active=_ghost_meta.get("heat_check", False),
                            consecutive_wins=_ghost_meta.get("consecutive_wins", 0),
                            best_ask=pos.best_ask,
                            net_pnl_actual=ghost_pnl,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=_ghost_meta.get("signal_source", "SNIPER"),
                            window_size_s=_ghost_meta.get("window_size_s") or pos.window_seconds or 0,
                            bond_outcome_direction=pos.bond_outcome_direction,
                            bond_delta_accel_30s=float(getattr(_ghost_signal, "bond_delta_accel_30s", 0.0) or 0.0),
                            bond_edge_drift_30s=float(getattr(_ghost_signal, "bond_edge_drift_30s", 0.0) or 0.0),
                            bond_accel_sustained=bool(getattr(_ghost_signal, "bond_accel_sustained", False)),
                            bond_has_hist=bool(getattr(_ghost_signal, "bond_has_hist", False)),
                        )
                    except Exception as _e:
                        logger.error("record_trade GHOST_POSITION failed: %s", _e)
                return

        # Externally sold guard: balance < 0.01 shares = sold manually outside the bot.
        # Also catches ORDERBOOK_NOT_FOUND (market resolved before our sell executed) —
        # without this, Guard 1 retries for 5–15s then records nothing, causing silent
        # capital loss that only surfaces at the hourly USDC reconcile.
        ext_sold_detected = any(
            "EXTERNALLY_SOLD" in (getattr(r, "error", "") or "")
            or "ORDERBOOK_NOT_FOUND" in (getattr(r, "error", "") or "")
            for r in exit_fills
        )
        if ext_sold_detected:
            # Use weighted avg price across ALL fills (stage-1 + stage-2 attempt),
            # same as the normal exit path. This prevents gross_pnl from being
            # computed as (stage2_price - entry) × full_shares when stage1 already
            # sold 60% at a different price — which inflated gross/fee in the log.
            import re as _re
            # Only trust live_price if a price is embedded in the fill error — that
            # means the CLOB confirmed the fill price. If no price is in the error
            # (network-miss: our cascade timed out but order executed on Polymarket),
            # fall back to entry_price so we record a flat exit instead of a phantom
            # profit/loss at whatever the OB happens to show now (2026-04-16 bug:
            # cascade failed on REVERSAL_STOP, TIME_EXIT_EXT used resolution price
            # $0.96 while actual fill was $0.55 → fee ≈ gross, bankroll overstated ~$5).
            _price_found_in_error = False
            _exit_price_uncertain = False
            _raw_exit = live_price if live_price > 0 else pos.entry_price  # use trigger price, not entry
            for _r in exit_fills:
                _err = getattr(_r, "error", "") or ""
                _m = _re.search(r'price=([0-9.]+)', _err)
                if _m:
                    _raw_exit = float(_m.group(1))
                    _price_found_in_error = True
                    break
            if not _price_found_in_error:
                # No price in error message — cascade_sell confirmation was dropped
                # (CF block / WS miss). Query CLOB trade history to recover the
                # actual exit price. This fixes the bankroll drift seen 2026-04-16
                # where real losses of ~$2 were recorded as -$0.10 (fee only).
                # 4s delay: CLOB /trades indexing can lag 2-5s for fresh fills.
                await asyncio.sleep(4.0)
                try:
                    _clob_sells = await asyncio.to_thread(
                        self.orders.fetch_recent_token_sells,
                        token_id,
                        pos.open_ts,
                    )
                    if _clob_sells:
                        _total_sz = sum(s for _, s in _clob_sells)
                        _total_val = sum(p * s for p, s in _clob_sells)
                        if _total_sz > 0:
                            _raw_exit = round(_total_val / _total_sz, 6)
                            _price_found_in_error = True
                            logger.info(
                                "EXT price recovered from CLOB history: %s/%s → %.4f "
                                "(%d fill(s), %.4f shares total)",
                                pos.asset, pos.direction.name,
                                _raw_exit, len(_clob_sells), _total_sz,
                            )
                except Exception as _clob_exc:
                    logger.warning(
                        "fetch_recent_token_sells %s failed: %s", token_id[:8], _clob_exc
                    )
            _is_resolved_zero = False
            if not _price_found_in_error:
                # Check if the token resolved worthless (wrong direction).
                # A best bid < $0.02 with no sell fills = token expired at $0,
                # not an external sell. Record the real loss instead of entry_price.
                # Must use a fresh fetch here — cached OB still shows pre-close bid
                # (e.g. 0.85) after ORDERBOOK_NOT_FOUND, bypassing the < 0.02 check.
                _ob_chk = await self.feed.fetch_order_book(token_id)
                _best_bid_chk = _ob_chk.bids[0][0] if (_ob_chk and _ob_chk.bids) else 0.0
                if _best_bid_chk < 0.02:
                    # Low bid may mean resolved worthless OR GTC sold before resolution
                    # but CLOB indexing hadn't caught up in 4s. Retry once at +8s.
                    await asyncio.sleep(8.0)
                    try:
                        _clob_retry = await asyncio.to_thread(
                            self.orders.fetch_recent_token_sells,
                            token_id, pos.open_ts,
                        )
                        if _clob_retry:
                            _tsz = sum(s for _, s in _clob_retry)
                            _tval = sum(p * s for p, s in _clob_retry)
                            if _tsz > 0:
                                _raw_exit = round(_tval / _tsz, 6)
                                _price_found_in_error = True
                                logger.info(
                                    "EXT price recovered on low-bid retry: %s/%s → %.4f "
                                    "(%d fill(s), %.4f shares)",
                                    pos.asset, pos.direction.name, _raw_exit,
                                    len(_clob_retry), _tsz,
                                )
                    except Exception as _clob_retry_exc:
                        logger.warning(
                            "CLOB retry on low-bid failed %s: %s",
                            token_id[:12], _clob_retry_exc,
                        )
                    if not _price_found_in_error:
                        _raw_exit = 0.0
                        _is_resolved_zero = True
                        logger.warning(
                            "EXTERNALLY_SOLD %s/%s — token resolved worthless "
                            "(best_bid=%.4f), recording full loss exit_price=0.0000",
                            pos.asset, pos.direction.name, _best_bid_chk,
                        )
                else:
                    # Shares not confirmed sold — check CLOB balance before giving up.
                    # If balance > 0, shares are still in wallet (thin OB stalled the exit).
                    # Force-sell them now before closing position tracking.
                    _residual_bal = await asyncio.to_thread(
                        self.orders.fetch_token_balance, token_id
                    ) if not CONFIG.dry_run else None
                    if _residual_bal and _residual_bal > 0.05:
                        logger.warning(
                            "EXTERNALLY_SOLD %s/%s — CLOB balance=%.4f shares still in wallet "
                            "(thin OB stalled exit). Force-selling before close.",
                            pos.asset, pos.direction.name, _residual_bal,
                        )
                        _ob_now = self.feed.get_order_book(token_id)
                        _bid_now = _ob_now.bids[0][0] if (_ob_now and _ob_now.bids) else _best_bid_chk
                        _rescue_fills = await self.orders.cascade_sell(
                            token_id=token_id,
                            total_shares=_residual_bal,
                            current_price=_bid_now if _bid_now > 0.001 else 0.01,
                            reason="EXT_RESCUE",
                            neg_risk=getattr(token_meta, "neg_risk", False),
                            tick_size=getattr(token_meta, "tick_size", "0.01"),
                            force_exit=True,
                        )
                        _rescued = sum(f.total_size for f in _rescue_fills)
                        if _rescued > 0:
                            all_exit_fills.extend(_rescue_fills)
                            _rescue_val = sum(f.avg_fill_price * f.total_size for f in _rescue_fills)
                            _raw_exit = round(_rescue_val / _rescued, 6)
                            _price_found_in_error = True
                            logger.info(
                                "EXT_RESCUE %s/%s: sold %.4f shares @ %.4f",
                                pos.asset, pos.direction.name, _rescued, _raw_exit,
                            )
                        else:
                            logger.warning(
                                "EXT_RESCUE %s/%s failed — using live_price=%.4f as fallback",
                                pos.asset, pos.direction.name, _raw_exit,
                            )
                    else:
                        _exit_price_uncertain = True
                        logger.warning(
                            "EXTERNALLY_SOLD %s/%s — no fill price in error or CLOB history, "
                            "CLOB balance=%.4f (sold externally or resolved). "
                            "using live_price=%.4f as placeholder; will correct at resolution",
                            pos.asset, pos.direction.name,
                            _residual_bal if _residual_bal is not None else -1.0, _raw_exit,
                        )
            if not _is_resolved_zero:
                _raw_exit = _raw_exit if _raw_exit > 0 else pos.entry_price
            # Weighted avg across all fills gives correct gross_pnl when stage-1
            # already sold 60% at a different price. Falls back to _raw_exit if
            # no fills with sizes are present (e.g. pure externally-sold dust).
            exit_price = self._calc_exit_price(all_exit_fills, _raw_exit)
            logger.warning(
                "EXTERNALLY_SOLD purged: %s/%s — closing at weighted_price %.4f "
                "(raw=%.4f). Shares already sold externally, stopping retry loop.",
                pos.asset, pos.direction.name, exit_price, _raw_exit,
            )
            pnl = self.risk.close_position(token_id, _raw_exit, reason)
            _ext_meta = self._open_meta.pop(token_id, {})
            self._pos_log_ts.pop(token_id, None)
            self._dir_rev_count.pop(token_id, None)
            _ext_snaps      = self._entry_snaps.pop(token_id, {})
            _ext_traj_mfe   = self._traj_mfe.pop(token_id, {})
            _ext_traj_mae   = self._traj_mae.pop(token_id, {})
            _ext_price_t10s = self._price_at_t10s.pop(token_id, None)
            self._sl_below_count.pop(token_id, None)
            self._stall_checked.discard(token_id)
            self._peak_bond_move.pop(token_id, None)
            self._trough_bond_move.pop(token_id, None)
            self._peak_ts.pop(token_id, None)
            self._stall_conf_count.pop(token_id, None)
            self._exhaustion_conf_count.pop(token_id, None)
            self._early_loss_conf_count.pop(token_id, None)
            self._early_chop_count.pop(token_id, None)
            self._peak_breach_ts.pop(token_id, None)
            self._zombie_flag_ts.pop(token_id, None)
            self._terminal_tp_touched.discard(token_id)
            if pnl is not None:
                _signal = _ext_meta.get("signal")
                if _signal is None:
                    _signal = SignalBreakdown(
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="externally_sold",
                    )
                capital_before = self.risk.bankroll.capital - pnl
                # exit_reason = real trigger (STOP_LOSS / PROFIT_1 / HARD_EXIT / etc.)
                # with _EXT suffix to flag that the position was already gone at sell time
                _logged_reason = f"{reason}_EXT" if reason != "EXTERNALLY_SOLD" else "EXTERNALLY_SOLD"
                _ext_s30 = _ext_snaps.get(30, 0.0)
                _ext_s60 = _ext_snaps.get(60, 0.0)
                _ext_r30 = (_ext_s30 - pos.entry_price) / pos.entry_price * 100 if pos.entry_price > 0 and _ext_s30 > 0 else None
                _ext_r60 = (_ext_s60 - pos.entry_price) / pos.entry_price * 100 if pos.entry_price > 0 and _ext_s60 > 0 else None
                _ext_max_adv = ((pos.entry_price - pos.lowest_price) / pos.entry_price * 100
                               if pos.entry_price > 0 and pos.lowest_price > 0 else 0.0)
                _ext_path_cls, _ext_path_conf, _ext_path_rsn = _classify_path(
                    r30=_ext_r30, r60=_ext_r60,
                    max_adv_pct=_ext_max_adv,
                    hold_s=time.time() - pos.open_ts,
                    exit_reason=_logged_reason,
                    exit_price=exit_price,
                    entry_price=pos.entry_price,
                )
                try:
                    self.analytics.record_trade(
                        token_id=token_id,
                        asset=pos.asset,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        stake=pos.stake,
                        shares=pos.shares,
                        entry_fill=_ext_meta.get("entry_fill"),
                        exit_fills=all_exit_fills,
                        exit_reason=_logged_reason,
                        signal=_signal,
                        ts_open=_ext_meta.get("ts_open", pos.open_ts),
                        ts_close=time.time(),
                        capital_before=capital_before,
                        heat_check_active=_ext_meta.get("heat_check", False),
                        consecutive_wins=_ext_meta.get("consecutive_wins", 0),
                        best_ask=pos.best_ask,
                        net_pnl_actual=pnl,
                        market_type=getattr(token_meta, "market_type", "unknown"),
                        is_live=not CONFIG.dry_run,
                        signal_source=_ext_meta.get("signal_source", "BOND" if pos.is_bond else "SNIPER"),
                        window_size_s=_ext_meta.get("window_size_s") or pos.window_seconds or 0,
                        spot_at_entry=_ext_meta.get("spot_at_entry", 0.0),
                        spot_at_exit=spot_at_exit,
                        signal_to_fill_ms=_ext_meta.get("signal_to_fill_ms", 0.0),
                        ob_depth_at_entry=_ext_meta.get("ob_depth_at_entry", 0.0),
                        pre_entry_momentum_pct=_ext_meta.get("pre_entry_momentum_pct", 0.0),
                        max_price_seen=pos.highest_price,
                        min_price_seen=pos.lowest_price,
                        highest_price_ts=pos.highest_price_ts,
                        lowest_price_ts=pos.lowest_price_ts,
                        bond_entry_class=pos.bond_entry_class,
                        bond_macro_regime=pos.bond_macro_regime,
                        bond_outcome_direction=getattr(_signal, "bond_outcome_direction", "") or pos.bond_outcome_direction,
                        move_age_s=_ext_meta.get("move_age_s", 999.0),
                        velocity_5s_pct=_ext_meta.get("velocity_5s_pct", 0.0),
                        term_vpin=float(getattr(_signal, "term_vpin", 0.0) or 0.0),
                        term_spot_delta_5s=float(getattr(_signal, "term_spot_delta_5s", 0.0) or 0.0),
                        term_spot_delta_30s=float(getattr(_signal, "term_spot_delta_30s", 0.0) or 0.0),
                        term_spot_delta_60s=float(getattr(_signal, "term_spot_delta_60s", 0.0) or 0.0),
                        term_spot_delta_5m=float(getattr(_signal, "term_spot_delta_5m", 0.0) or 0.0),
                        term_ask_spread_pct=float(getattr(_signal, "term_ask_spread_pct", 0.0) or 0.0),
                        term_ask_qty=float(getattr(_signal, "term_ask_qty", 0.0) or 0.0),
                        term_ob_imbalance=float(getattr(_signal, "term_ob_imbalance", 0.0) or 0.0),
                        term_ob_depth=float(getattr(_signal, "term_ob_depth", 0.0) or 0.0),
                        term_remaining_s=float(getattr(_signal, "term_remaining_s", 0.0) or 0.0),
                        term_token_delta_3s=float(getattr(_signal, "term_token_delta_3s", 0.0) or 0.0),
                        term_token_delta_5s=float(getattr(_signal, "term_token_delta_5s", 0.0) or 0.0),
                        term_token_delta_30s=float(getattr(_signal, "term_token_delta_30s", 0.0) or 0.0),
                        term_token_delta_60s=float(getattr(_signal, "term_token_delta_60s", 0.0) or 0.0),
                        term_tok_tick_count_5s=int(getattr(_signal, "term_tok_tick_count_5s", 0) or 0),
                        term_tok_tick_count_30s=int(getattr(_signal, "term_tok_tick_count_30s", 0) or 0),
                        term_ask_stale_s=float(getattr(_signal, "term_ask_stale_s", 999.0) or 999.0),
                        term_tok_decel_ratio=float(getattr(_signal, "term_tok_decel_ratio", 0.0) or 0.0),
                        term_binance_1m_pct=getattr(_signal, "term_binance_1m_pct", None),
                        term_binance_5m_pct=getattr(_signal, "term_binance_5m_pct", None),
                        term_binance_60m_pct=getattr(_signal, "term_binance_60m_pct", None),
                        term_pre_snap_60s=float(getattr(_signal, "term_pre_snap_60s", 0.0) or 0.0),
                        term_pre_snap_30s=float(getattr(_signal, "term_pre_snap_30s", 0.0) or 0.0),
                        term_pre_snap_open=float(getattr(_signal, "term_pre_snap_open", 0.0) or 0.0),
                        term_snap60_eff=float(getattr(_signal, "term_snap60_eff", 0.0) or 0.0),
                        term_snap30_eff=float(getattr(_signal, "term_snap30_eff", 0.0) or 0.0),
                        term_rsi=float(getattr(_signal, "term_rsi", 0.0) or 0.0),
                        term_ask_vwap=float(getattr(_signal, "term_ask_vwap", 0.0) or 0.0),
                        exit_price_uncertain=_exit_price_uncertain,
                        traj_mfe_10s=float(_ext_traj_mfe.get(10, 0.0)),
                        traj_mae_10s=float(_ext_traj_mae.get(10, 0.0)),
                        traj_mfe_30s=float(_ext_traj_mfe.get(30, 0.0)),
                        traj_mae_30s=float(_ext_traj_mae.get(30, 0.0)),
                        price_at_t10s=_ext_price_t10s,
                        entry_snap_30s_pct=pos.entry_snap_30s_pct,
                        entry_snap_60s_pct=pos.entry_snap_60s_pct,
                        path_class=_ext_path_cls,
                        path_confidence=_ext_path_conf,
                        path_reason=_ext_path_rsn,
                        bond_delta_accel_30s=float(getattr(_signal, "bond_delta_accel_30s", 0.0) or 0.0),
                        bond_edge_drift_30s=float(getattr(_signal, "bond_edge_drift_30s", 0.0) or 0.0),
                        bond_accel_sustained=bool(getattr(_signal, "bond_accel_sustained", False)),
                        bond_has_hist=bool(getattr(_signal, "bond_has_hist", False)),
                    )
                except Exception as _rec_exc:
                    logger.error("record_trade EXTERNALLY_SOLD failed: %s", _rec_exc)
            asyncio.create_task(self._track_post_exit(
                token_id=token_id,
                trade_id=self.analytics.last_trade_id,
                asset=pos.asset,
                direction=pos.direction.name,
                exit_price=exit_price,
                exit_reason=_logged_reason,
                entry_price=pos.entry_price,
                window_end_ts=pos.window_end_ts,
                binance_price_at_entry=pos.binance_price_at_entry,
                condition_id=getattr(pos, "condition_id", ""),
                outcome_direction=getattr(pos, "bond_outcome_direction", "up") or "up",
            ))
            if pos.window_end_ts > 0:
                try:
                    os.makedirs("logs", exist_ok=True)
                    with open(os.path.join("logs", "pending_resolutions.jsonl"), "a") as _pf:
                        _pf.write(json.dumps(dict(
                            token_id=token_id,
                            trade_id=self.analytics.last_trade_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            exit_price=exit_price,
                            exit_reason=_logged_reason,
                            entry_price=pos.entry_price,
                            window_end_ts=pos.window_end_ts,
                            binance_price_at_entry=pos.binance_price_at_entry,
                            condition_id=getattr(pos, "condition_id", ""),
                        )) + "\n")
                except Exception:
                    pass
            return

        # Guard 1: zero sell before stage-1 → network/CLOB error, retry next scan.
        # Calling close_position on 0 fills ghosts the position: bot records a loss
        # while shares remain on Polymarket (T00011: 4.9 ETH shares left to resolve).
        if sold_shares <= 0 and not stage1_done:
            # Exception: if the bond window has already expired, CLOB will never
            # accept another sell — retrying is pointless. Resolve the position now
            # using OB bid to determine if token went to $1 (win) or $0 (loss).
            _now_g1 = time.time()
            # VOLARB skips this immediate-force-close: VOLARB holds to redemption
            # (the kline-decision path at WINDOW_OUTCOME catches the actual outcome
            # after 60s post-window). Force-closing at $0 here would zero out winners.
            _g1_skip_volarb = getattr(pos, "bond_entry_class", "") == "VOLARB"
            if pos.window_end_ts > 0 and _now_g1 > pos.window_end_ts + 5.0 and not _g1_skip_volarb:
                _g1_ob   = self.feed.get_order_book(token_id)
                _g1_bid  = _g1_ob.bids[0][0] if (_g1_ob and _g1_ob.bids) else 0.0
                _g1_ask  = _g1_ob.asks[0][0] if (_g1_ob and _g1_ob.asks) else 0.0
                _g1_price = 0.0  # stale OB bid (resting PROFIT_TARGET at 0.99) is not settlement; always NO
                logger.warning(
                    "BOND_EXPIRED_UNSOLD %s/%s — window expired %.0fs ago, 0 fills. "
                    "OB bid=%.4f ask=%.4f → closing at %.4f",
                    pos.asset, pos.direction.name, _now_g1 - pos.window_end_ts,
                    _g1_bid, _g1_ask, _g1_price,
                )
                _g1_pnl  = self.risk.close_position(token_id, _g1_price, "BOND_EXPIRED_UNSOLD")
                self._mark_bond_total_loss(pos.asset)
                _g1_meta = self._open_meta.pop(token_id, {})
                # Pop analytics data before cleanup so record_trade can use them
                _g1_snaps = self._entry_snaps.pop(token_id, {})
                _g1_traj_mfe = self._traj_mfe.pop(token_id, {})
                _g1_traj_mae = self._traj_mae.pop(token_id, {})
                _g1_price_at_t10s = self._price_at_t10s.pop(token_id, None)
                _bond_llm_g1 = self._bond_llm_decisions.pop(token_id, {})
                if _g1_pnl is not None:
                    _g1_signal = _g1_meta.get("signal") or SignalBreakdown(
                        direction=pos.direction, entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="bond_expired_unsold",
                    )
                    _ep_g1 = pos.entry_price
                    _s30_g1 = _g1_snaps.get(30, 0.0)
                    _s60_g1 = _g1_snaps.get(60, 0.0)
                    _r30_g1 = (_s30_g1 - _ep_g1) / _ep_g1 * 100 if _ep_g1 > 0 and _s30_g1 > 0 else None
                    _r60_g1 = (_s60_g1 - _ep_g1) / _ep_g1 * 100 if _ep_g1 > 0 and _s60_g1 > 0 else None
                    _lowest_g1 = pos.lowest_price
                    _highest_g1 = pos.highest_price
                    _max_adv_g1 = ((_ep_g1 - _lowest_g1) / _ep_g1 * 100) if _ep_g1 > 0 and _lowest_g1 > 0 else 0.0
                    _hold_s_g1 = _now_g1 - _g1_meta.get("ts_open", pos.open_ts)
                    _path_class_g1, _path_conf_g1, _path_reason_g1 = _classify_path(
                        r30=_r30_g1, r60=_r60_g1, max_adv_pct=_max_adv_g1, hold_s=_hold_s_g1,
                        exit_reason="BOND_EXPIRED_UNSOLD", exit_price=_g1_price, entry_price=_ep_g1,
                    )
                    _bounce_pct_g1 = 0.0
                    if (pos.entry_price > 0 and pos.mae_bounce_peak > 0
                            and pos.lowest_price > 0 and pos.mae_bounce_peak > pos.lowest_price):
                        _bounce_pct_g1 = (pos.mae_bounce_peak - pos.lowest_price) / pos.entry_price * 100
                    _g1_spot_exit = self.feed._spot_price.get(pos.asset.upper(), 0.0)
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=_g1_price,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=_g1_meta.get("entry_fill"), exit_fills=[],
                            exit_reason="BOND_EXPIRED_UNSOLD", signal=_g1_signal,
                            ts_open=_g1_meta.get("ts_open", pos.open_ts), ts_close=_now_g1,
                            capital_before=self.risk.bankroll.capital - _g1_pnl,
                            heat_check_active=_g1_meta.get("heat_check", False),
                            consecutive_wins=_g1_meta.get("consecutive_wins", 0),
                            best_ask=pos.best_ask,
                            net_pnl_actual=_g1_pnl,
                            market_type=getattr(token_meta, "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=_g1_meta.get("signal_source", "BOND"),
                            window_size_s=_g1_meta.get("window_size_s") or pos.window_seconds or 0,
                            ob_depth_at_entry=_g1_meta.get("ob_depth_at_entry", 0.0),
                            pre_entry_momentum_pct=_g1_meta.get("pre_entry_momentum_pct", 0.0),
                            spot_at_entry=_g1_meta.get("spot_at_entry", 0.0),
                            spot_at_exit=_g1_spot_exit,
                            signal_to_fill_ms=_g1_meta.get("signal_to_fill_ms", 0.0),
                            llm_rec=_g1_meta.get("llm_rec", ""),
                            llm_rec_conf=_g1_meta.get("llm_rec_conf", 0.0),
                            max_price_seen=_highest_g1,
                            min_price_seen=_lowest_g1,
                            highest_price_ts=pos.highest_price_ts,
                            lowest_price_ts=pos.lowest_price_ts,
                            binance_price_at_entry=pos.binance_price_at_entry,
                            binance_reversal_count_at_exit=pos.binance_reversal_count,
                            velocity_5s_pct=_g1_meta.get("velocity_5s_pct", 0.0),
                            move_age_s=_g1_meta.get("move_age_s", 999.0),
                            path_class=_path_class_g1,
                            path_confidence=_path_conf_g1,
                            path_reason=_path_reason_g1,
                            entry_snap_30s_pct=_r30_g1 if _r30_g1 is not None else 0.0,
                            entry_snap_60s_pct=_r60_g1 if _r60_g1 is not None else 0.0,
                            bond_entry_class=pos.bond_entry_class,
                            bond_outcome_direction=getattr(_g1_signal, "bond_outcome_direction", "") or getattr(pos, "bond_outcome_direction", ""),
                            bond_macro_regime=pos.bond_macro_regime,
                            mae_bounce_10s_pct=_bounce_pct_g1,
                            bond_stab_class=getattr(_g1_signal, "bond_stab_class", ""),
                            bond_stability_score=int(getattr(_g1_signal, "bond_stability_score", 0)),
                            bond_stab_xp_bad=bool(getattr(_g1_signal, "bond_stab_xp_bad", False)),
                            bond_stab_slip_bad=bool(getattr(_g1_signal, "bond_stab_slip_bad", False)),
                            bond_stab_delta_bad=bool(getattr(_g1_signal, "bond_stab_delta_bad", False)),
                            bond_stab_edge_weak=bool(getattr(_g1_signal, "bond_stab_edge_weak", False)),
                            bond_stab_vel_flat=bool(getattr(_g1_signal, "bond_stab_vel_flat", False)),
                            bond_delta_accel_30s=float(getattr(_g1_signal, "bond_delta_accel_30s", 0.0) or 0.0),
                            bond_accel_15s=float(getattr(_g1_signal, "bond_accel_15s", 0.0) or 0.0),
                            bond_edge_drift_30s=float(getattr(_g1_signal, "bond_edge_drift_30s", 0.0) or 0.0),
                            bond_accel_sustained=bool(getattr(_g1_signal, "bond_accel_sustained", False)),
                            bond_has_hist=bool(getattr(_g1_signal, "bond_has_hist", False)),
                            bond_smooth_delta_60s=float(getattr(_g1_signal, "bond_smooth_delta_60s", 0.0) or 0.0),
                            bond_entry_zone=str(getattr(_g1_signal, "bond_entry_zone", "") or ""),
                            pre_score=float(getattr(_g1_signal, "pre_score", 0.0) or 0.0),
                            pre_score_version=str(getattr(_g1_signal, "pre_score_version", "") or ""),
                            pre_score_schema_hash=str(getattr(_g1_signal, "pre_score_schema_hash", "") or ""),
                            pre_score_validity=str(getattr(_g1_signal, "pre_score_validity", "") or ""),
                            pre_score_accel=float(getattr(_g1_signal, "pre_score_accel", 0.0) or 0.0),
                            pre_score_daccel=float(getattr(_g1_signal, "pre_score_daccel", 0.0) or 0.0),
                            pre_score_edge=float(getattr(_g1_signal, "pre_score_edge", 0.0) or 0.0),
                            pre_score_stab=float(getattr(_g1_signal, "pre_score_stab", 0.0) or 0.0),
                            pre_score_vel=float(getattr(_g1_signal, "pre_score_vel", 0.0) or 0.0),
                            pre_score_class=float(getattr(_g1_signal, "pre_score_class", 0.0) or 0.0),
                            bond_llm_decision=_bond_llm_g1.get("decision", ""),
                            bond_llm_conf=float(_bond_llm_g1.get("conf", 0.0)),
                            bond_llm_reason=_bond_llm_g1.get("reason", ""),
                            bond_llm_tp_pct=float(_bond_llm_g1.get("shadow_tp_pct", 0.0)),
                            bond_llm_sl_pct=float(_bond_llm_g1.get("shadow_sl_pct", 0.0)),
                            term_vpin=float(getattr(_g1_signal, "term_vpin", 0.0) or 0.0),
                            term_spot_delta_5s=float(getattr(_g1_signal, "term_spot_delta_5s", 0.0) or 0.0),
                            term_spot_delta_30s=float(getattr(_g1_signal, "term_spot_delta_30s", 0.0) or 0.0),
                            term_spot_delta_60s=float(getattr(_g1_signal, "term_spot_delta_60s", 0.0) or 0.0),
                            term_spot_delta_5m=float(getattr(_g1_signal, "term_spot_delta_5m", 0.0) or 0.0),
                            term_ask_spread_pct=float(getattr(_g1_signal, "term_ask_spread_pct", 0.0) or 0.0),
                            term_ask_qty=float(getattr(_g1_signal, "term_ask_qty", 0.0) or 0.0),
                            term_ob_imbalance=float(getattr(_g1_signal, "term_ob_imbalance", 0.0) or 0.0),
                            term_ob_depth=float(getattr(_g1_signal, "term_ob_depth", 0.0) or 0.0),
                            term_remaining_s=float(getattr(_g1_signal, "term_remaining_s", 0.0) or 0.0),
                            term_token_delta_3s=float(getattr(_g1_signal, "term_token_delta_3s", 0.0) or 0.0),
                            term_token_delta_5s=float(getattr(_g1_signal, "term_token_delta_5s", 0.0) or 0.0),
                            term_tok_tick_count_5s=int(getattr(_g1_signal, "term_tok_tick_count_5s", 0) or 0),
                            term_tok_tick_count_30s=int(getattr(_g1_signal, "term_tok_tick_count_30s", 0) or 0),
                            term_ask_stale_s=float(getattr(_g1_signal, "term_ask_stale_s", 999.0) or 999.0),
                            term_tok_decel_ratio=float(getattr(_g1_signal, "term_tok_decel_ratio", 0.0) or 0.0),
                            term_token_delta_30s=float(getattr(_g1_signal, "term_token_delta_30s", 0.0) or 0.0),
                            term_token_delta_60s=float(getattr(_g1_signal, "term_token_delta_60s", 0.0) or 0.0),
                            term_binance_1m_pct=getattr(_g1_signal, "term_binance_1m_pct", None),
                            term_binance_5m_pct=getattr(_g1_signal, "term_binance_5m_pct", None),
                            term_binance_60m_pct=getattr(_g1_signal, "term_binance_60m_pct", None),
                            term_pre_snap_60s=float(getattr(_g1_signal, "term_pre_snap_60s", 0.0) or 0.0),
                            term_pre_snap_30s=float(getattr(_g1_signal, "term_pre_snap_30s", 0.0) or 0.0),
                            term_pre_snap_open=float(getattr(_g1_signal, "term_pre_snap_open", 0.0) or 0.0),
                            term_snap60_eff=float(getattr(_g1_signal, "term_snap60_eff", 0.0) or 0.0),
                            term_snap30_eff=float(getattr(_g1_signal, "term_snap30_eff", 0.0) or 0.0),
                            term_rsi=float(getattr(_g1_signal, "term_rsi", 0.0) or 0.0),
                            term_ask_vwap=float(getattr(_g1_signal, "term_ask_vwap", 0.0) or 0.0),
                            traj_mfe_10s=float(_g1_traj_mfe.get(10, 0.0)),
                            traj_mae_10s=float(_g1_traj_mae.get(10, 0.0)),
                            traj_mfe_30s=float(_g1_traj_mfe.get(30, 0.0)),
                            traj_mae_30s=float(_g1_traj_mae.get(30, 0.0)),
                            price_at_t10s=_g1_price_at_t10s,
                            window_outcome_price=0.0,
                        )
                    except Exception as _g1e:
                        logger.error("record_trade BOND_EXPIRED_UNSOLD failed: %s", _g1e)
                # Full cleanup — mirrors _exit_position
                for _d in (self._pos_log_ts, self._dir_rev_count, self._sl_below_count,
                           self._peak_bond_move, self._trough_bond_move, self._peak_ts,
                           self._stall_conf_count, self._exhaustion_conf_count,
                           self._early_loss_conf_count, self._early_chop_count,
                           self._peak_breach_ts, self._zombie_flag_ts,
                           self._term_pre_snap_refs, self._term_pre_entry_obs,
                           self._bond_sl_arm_ts, self._catas_breach_ts,
                           self._catas_cancel_count, self._pae_below_since,
                           self._pae_above_since, self._bc_arm_tracker):
                    _d.pop(token_id, None)
                self._stall_checked.discard(token_id)
                self._terminal_tp_touched.discard(token_id)
                return
            if token_id in self.risk.open_positions:
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "EXIT RETRY: cascade sold 0 shares for %s/%s (network/CLOB error) — "
                "position kept open, retrying next OB scan",
                pos.asset, pos.direction.name,
            )
            return

        # Guard 1b: stage-2 cascade sold nothing. Check actual CLOB balance before
        # retrying — if balance=0, the shares resolved or were sold externally.
        # Previous behaviour (infinite reset loop) left positions stuck forever.
        _DUST_SHARES = 0.05           # below this, accept residual as done
        if this_sell <= 0 and stage1_done and expected_this_sell > _DUST_SHARES:
            _s2_balance = self.orders.fetch_token_balance(token_id)
            if _s2_balance is None or _s2_balance < 0.05:
                # Balance gone — resolved or sold externally. Close the record.
                # Compute weighted exit price across stage-1 fills + live_price for remaining,
                # and use all shares so bankroll captures 100% of the trade PnL.
                logger.warning(
                    "STAGE-2 balance=0 for %s/%s — shares resolved/sold, closing record",
                    pos.asset, pos.direction.name,
                )
                _s2_meta = self._open_meta.get(token_id, {})
                _s1_fills = _s2_meta.get("stage1_fills", [])
                if _s1_fills and pos.shares > 0:
                    _s1_sold = sum(f.total_size for f in _s1_fills)
                    _s1_notional = sum(f.avg_fill_price * f.total_size for f in _s1_fills)
                    _s2_remaining = max(0.0, pos.shares - _s1_sold)
                    _w_price = (_s1_notional + live_price * _s2_remaining) / pos.shares
                    _s2r_exit_price = round(_w_price, 6)
                    pnl = self.risk.close_position(token_id, _s2r_exit_price, "STAGE2_RESOLVED",
                                                   shares_override=pos.shares)
                else:
                    _s2r_exit_price = live_price
                    pnl = self.risk.close_position(token_id, _s2r_exit_price, "STAGE2_RESOLVED")
                _s2r_all_shares = pos.shares
                _s2r_entry_fill = _s2_meta.get("entry_fill")
                _s2r_signal = _s2_meta.get("signal")
                self._open_meta.pop(token_id, None)
                self._pos_log_ts.pop(token_id, None)
                self._dir_rev_count.pop(token_id, None)
                self._entry_snaps.pop(token_id, None)
                self._term_pre_snap_refs.pop(token_id, None)
                self._term_pre_entry_obs.pop(token_id, None)
                self._sl_below_count.pop(token_id, None)
                self._stall_checked.discard(token_id)
                self._peak_bond_move.pop(token_id, None)
                self._trough_bond_move.pop(token_id, None)
                self._peak_ts.pop(token_id, None)
                self._stall_conf_count.pop(token_id, None)
                self._exhaustion_conf_count.pop(token_id, None)
                self._early_loss_conf_count.pop(token_id, None)
                self._peak_breach_ts.pop(token_id, None)
                if pnl is not None:
                    if _s2r_entry_fill is None:
                        _s2r_entry_fill = OrderResult(
                            status=OrderStatus.FILLED, avg_fill_price=pos.entry_price,
                            total_size=pos.shares, slippage=0.0,
                        )
                    if _s2r_signal is None:
                        _s2r_signal = SignalBreakdown(
                            direction=pos.direction, entry_price=pos.entry_price,
                            composite=0.0, confidence=0.0, breakout_score=0.0,
                            trend_score=0.0, volume_score=0.0, ob_score=0.0,
                            fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                            reason="stage2_resolved",
                        )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=_s2r_exit_price,
                            stake=pos.stake, shares=_s2r_all_shares,
                            entry_fill=_s2r_entry_fill, exit_fills=_s1_fills,
                            exit_reason="STAGE2_RESOLVED", signal=_s2r_signal,
                            ts_open=_s2_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital - pnl,
                            heat_check_active=_s2_meta.get("heat_check", False),
                            consecutive_wins=_s2_meta.get("consecutive_wins", 0),
                            best_ask=pos.best_ask,
                            net_pnl_actual=pnl,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=_s2_meta.get("signal_source", "SNIPER"),
                            window_size_s=_s2_meta.get("window_size_s") or pos.window_seconds or 0,
                        )
                    except Exception as _s2re:
                        logger.error("record_trade STAGE2_RESOLVED failed: %s", _s2re)
                asyncio.create_task(self._track_post_exit(
                    token_id=token_id,
                    trade_id=self.analytics.last_trade_id,
                    asset=pos.asset,
                    direction=pos.direction.name,
                    exit_price=_s2r_exit_price,
                    exit_reason="STAGE2_RESOLVED",
                    entry_price=pos.entry_price,
                    window_end_ts=pos.window_end_ts,
                    binance_price_at_entry=pos.binance_price_at_entry,
                    condition_id=getattr(pos, "condition_id", ""),
                    outcome_direction=getattr(pos, "bond_outcome_direction", "up") or "up",
                ))
                return
            # Shares still exist — reset and retry next cycle
            if token_id in self.risk.open_positions:
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "STAGE-2 sold 0 of %.4f %s shares (CLOB=%.4f) — retrying next scan",
                expected_this_sell, pos.asset, _s2_balance,
            )
            return

        # Guard 2: significant partial fill → update remaining and retry.
        # Applies to both full exits (not stage1_done) and PROFIT_2 (stage1_done):
        # if <80% of remaining filled, update count and retry rather than ghost-closing.
        # Dust residuals (<0.10 shares) are accepted and position is closed.
        _PARTIAL_FILL_THRESH = 0.80   # require selling ≥80% of remaining
        if (this_sell < expected_this_sell * _PARTIAL_FILL_THRESH
                and expected_this_sell > _DUST_SHARES):
            if token_id in self.risk.open_positions:
                if this_sell > 0:
                    self.risk.open_positions[token_id].remaining_shares = max(
                        0.0, expected_this_sell - this_sell
                    )
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "PARTIAL EXIT %s/%s: sold %.4f of %.4f shares (%.0f%%) — "
                "updating remaining, retrying next scan",
                pos.asset, pos.direction.name,
                this_sell, expected_this_sell,
                100 * this_sell / expected_this_sell if expected_this_sell > 0 else 0,
            )
            return

        stage2_fallback = self._calc_exit_price(exit_fills, live_price)

        # Weighted avg exit price across ALL tranches (stage-1 95% + stage-2 5%).
        analytics_exit_price = self._calc_exit_price(all_exit_fills, stage2_fallback)
        # Capture from pos before close_position pops it from the dict.
        all_shares = pos.shares
        _highest_price = pos.highest_price
        _lowest_price = pos.lowest_price

        # Residual share recovery: if cascade_sell partially filled, try one immediate
        # retry before closing the position. If that also fails, queue for background sweep.
        _DUST_THRESHOLD = 0.10
        if sold_shares < all_shares - _DUST_THRESHOLD:
            residual = round(all_shares - sold_shares, 4)
            logger.warning(
                "RESIDUAL SHARES: %.4f %s unsold (sold %.4f of %.4f) — attempting immediate sweep",
                residual, pos.asset, sold_shares, all_shares,
            )
            try:
                sweep_fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=residual,
                    current_price=live_price,
                    reason="RESIDUAL_SWEEP",
                    neg_risk=getattr(token_meta, "neg_risk", False),
                    tick_size=getattr(token_meta, "tick_size", "0.01"),
                    force_exit=True,
                )
                swept = sum(f.total_size for f in sweep_fills)
                if swept > 0:
                    all_exit_fills.extend(sweep_fills)
                    sold_shares += swept
                    residual = round(all_shares - sold_shares, 4)
                    analytics_exit_price = self._calc_exit_price(all_exit_fills, stage2_fallback)
                    logger.info("RESIDUAL SWEEP: recovered %.4f shares immediately", swept)
            except Exception as _sweep_exc:
                logger.warning("RESIDUAL SWEEP failed: %s", _sweep_exc)

            if residual > _DUST_THRESHOLD:
                # Queue for background retry — sweep loop will retry every 60s
                self._residual_pending[token_id] = {
                    "shares": residual,
                    "asset": pos.asset,
                    "neg_risk": getattr(token_meta, "neg_risk", False),
                    "tick_size": getattr(token_meta, "tick_size", "0.01"),
                    "attempts": 0,
                    "last_try": 0.0,
                    "entry_price": pos.entry_price,
                    "stake": pos.stake,
                    "ts_open": meta.get("ts_open", pos.open_ts),
                    "signal_source": meta.get("signal_source", "SNIPER"),
                    "window_size_s": meta.get("window_size_s", 0),
                    "market_type": getattr(token_meta, "market_type", "unknown"),
                }
                logger.warning(
                    "RESIDUAL QUEUED: %.4f %s shares → background sweep will retry every 60s",
                    residual, pos.asset,
                )

        # ── Exit-price CLOB recovery (WS confirmation dropped) ────────────
        # cascade_sell can return fills with avg_fill_price=0 when the
        # WebSocket fill confirmation is dropped (Cloudflare blip / latency).
        # _calc_exit_price filters those out and falls back to entry_price,
        # which makes profitable BOND_TP / TP exits log as gross PnL=0
        # (entry == exit) and recorded a loss equal to fees only — even
        # though the actual on-chain fills were profitable.
        # Symptom: "ep=0.5400 xp=0.5400 net=-$0.35" when Polymarket UI
        # shows 17 shares bought @ 56¢, sold @ 75¢/94¢ for ~+$4.78 gross.
        # Fix: when we sold shares but every fill came back price=0, query
        # CLOB trade history and compute the real weighted-avg exit price.
        _valid_exit_fills = [
            f for f in all_exit_fills
            if f.avg_fill_price > 0 and f.total_size > 0
        ]
        if not _valid_exit_fills and sold_shares > 0:
            await asyncio.sleep(4.0)  # CLOB /trades indexing lag
            try:
                _clob_sells = await asyncio.to_thread(
                    self.orders.fetch_recent_token_sells,
                    token_id,
                    pos.open_ts,
                )
                if _clob_sells:
                    _rec_sz = sum(s for _, s in _clob_sells)
                    _rec_val = sum(p * s for p, s in _clob_sells)
                    if _rec_sz > 0:
                        _recovered_exit = round(_rec_val / _rec_sz, 6)
                        logger.info(
                            "EXIT_PRICE_RECOVERED %s/%s [%s] | fallback=%.4f → "
                            "CLOB=%.4f (%d fill(s), %.4f shares) — WS dropped",
                            pos.asset, pos.direction.name, reason,
                            analytics_exit_price, _recovered_exit,
                            len(_clob_sells), _rec_sz,
                        )
                        analytics_exit_price = _recovered_exit
            except Exception as _rec_exc:
                logger.warning(
                    "Exit price CLOB recovery failed for %s [%s]: %s",
                    token_id[:8], reason, _rec_exc,
                )

        capital_before = meta.get("capital_before", self.risk.bankroll.capital)

        # Sum actual fees from BOTH entry and exit fills (CLOB-reconciled).
        # Polymarket charges taker fee on each side of the trade independently.
        # Previous code only summed exit fees — missing the entry-side fee.
        # Falls back to estimated (risk manager config) when actual=0 (timing lag,
        # dry-run, or maker orders with zero fee).
        entry_fill = meta.get("entry_fill")
        entry_fee = (
            sum(f.fee for f in entry_fill.fills if f.fee > 0)
            if (entry_fill and entry_fill.fills) else 0.0
        )
        exit_fee = sum(f.fee for r in all_exit_fills for f in r.fills if f.fee > 0)
        actual_fee_total = (entry_fee + exit_fee) if (entry_fee + exit_fee) > 0 else None

        # Pass full shares + weighted avg price so bankroll records 100% of trade PnL.
        # Without shares_override, close_position uses remaining_shares (5% after
        # stage-1 sell), silently missing the 95% stage-1 tranche in bankroll.
        net_pnl = self.risk.close_position(
            token_id, analytics_exit_price, reason,
            shares_override=all_shares,
            actual_fee=actual_fee_total,
        )

        if net_pnl is not None:
            # entry_fill and signal: use from meta if available; construct
            # minimal placeholders if the position was restored from disk and
            # meta wasn't populated for this session.
            entry_fill = meta.get("entry_fill")
            signal = meta.get("signal")

            if entry_fill is None:
                # Position was recovered from disk; synthesize a minimal entry fill
                # so analytics can still record the trade.
                entry_fill = OrderResult(
                    status=OrderStatus.FILLED,
                    avg_fill_price=pos.entry_price,
                    total_size=pos.shares,
                    slippage=0.0,
                )

            if signal is None:
                # Build a minimal signal stub so analytics doesn't crash.
                signal = SignalBreakdown(
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    composite=0.0,
                    confidence=0.0,
                    breakout_score=0.0,
                    trend_score=0.0,
                    volume_score=0.0,
                    ob_score=0.0,
                    fee_zone=FeeZone.FAT_MIDDLE,
                    external_boost=0.0,
                    reason="recovered_from_disk",
                )
                # Restore term_ fields saved at entry so logs aren't all-zero
                # for positions that were open across a bot restart.
                try:
                    _smf = "logs/open_signal_meta.json"
                    if os.path.exists(_smf):
                        with open(_smf) as _f:
                            _sm = json.load(_f)
                        for _k, _v in _sm.get(token_id, {}).items():
                            setattr(signal, _k, _v)
                except Exception as _e:
                    logger.debug("open_signal_meta restore failed: %s", _e)

            token_meta = self.feed.tokens.get(token_id)
            # ── Path classification ───────────────────────────────────────────
            _snaps = self._entry_snaps.pop(token_id, {})
            _ep = pos.entry_price
            _s30 = _snaps.get(30, 0.0)
            _s60 = _snaps.get(60, 0.0)
            _r30 = (_s30 - _ep) / _ep * 100 if _ep > 0 and _s30 > 0 else None
            _r60 = (_s60 - _ep) / _ep * 100 if _ep > 0 and _s60 > 0 else None
            _max_adv = ((_ep - _lowest_price) / _ep * 100) if _ep > 0 and _lowest_price > 0 else 0.0
            _max_fav = ((_highest_price - _ep) / _ep * 100) if _ep > 0 and _highest_price > 0 else 0.0
            _hold_s = time.time() - meta.get("ts_open", pos.open_ts)
            _path_class, _path_conf, _path_reason = _classify_path(
                r30=_r30, r60=_r60, max_adv_pct=_max_adv, hold_s=_hold_s,
                exit_reason=reason, exit_price=analytics_exit_price, entry_price=_ep,
            )
            logger.info(
                "PATH_CLASS %s/%s [%s] | conf=%d | %s | r30=%s r60=%s max_adv=%.1f%%",
                pos.asset, pos.direction.name, _path_class, _path_conf, _path_reason,
                f"{_r30:+.1f}%" if _r30 is not None else "—",
                f"{_r60:+.1f}%" if _r60 is not None else "—",
                _max_adv,
            )

            _bounce_pct = 0.0
            if (pos.entry_price > 0 and pos.mae_bounce_peak > 0
                    and pos.lowest_price > 0 and pos.mae_bounce_peak > pos.lowest_price):
                _bounce_pct = (pos.mae_bounce_peak - pos.lowest_price) / pos.entry_price * 100

            _bond_llm = self._bond_llm_decisions.pop(token_id, {})
            try:
                self.analytics.record_trade(
                    token_id=token_id,
                    asset=pos.asset,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=analytics_exit_price,
                    stake=pos.stake,
                    shares=all_shares,
                    entry_fill=entry_fill,
                    exit_fills=all_exit_fills,
                    exit_reason=reason,
                    signal=signal,
                    ts_open=meta.get("ts_open", pos.open_ts),
                    ts_close=time.time(),
                    capital_before=capital_before,
                    # capital_after computed inside record_trade as capital_before + net_pnl
                    heat_check_active=meta.get("heat_check", False),
                    consecutive_wins=meta.get("consecutive_wins", 0),
                    best_ask=pos.best_ask,
                    net_pnl_actual=net_pnl,
                    market_type=getattr(token_meta, "market_type", "unknown"),
                    is_live=not CONFIG.dry_run,
                    signal_source=meta.get("signal_source", "BOND" if pos.is_bond else "MOMENTUM"),
                    window_size_s=meta.get("window_size_s") or pos.window_seconds or 0,
                    spot_at_entry=meta.get("spot_at_entry", 0.0),
                    spot_at_exit=spot_at_exit,
                    signal_to_fill_ms=meta.get("signal_to_fill_ms", 0.0),
                    ob_depth_at_entry=meta.get("ob_depth_at_entry", 0.0),
                    pre_entry_momentum_pct=meta.get("pre_entry_momentum_pct", 0.0),
                    llm_rec=meta.get("llm_rec", ""),
                    llm_rec_conf=meta.get("llm_rec_conf", 0.0),
                    max_price_seen=_highest_price,
                    min_price_seen=_lowest_price,
                    highest_price_ts=pos.highest_price_ts,
                    lowest_price_ts=pos.lowest_price_ts,
                    binance_price_at_entry=pos.binance_price_at_entry,
                    binance_reversal_count_at_exit=pos.binance_reversal_count,
                    velocity_5s_pct=meta.get("velocity_5s_pct", 0.0),
                    move_age_s=meta.get("move_age_s", 999.0),
                    path_class=_path_class,
                    path_confidence=_path_conf,
                    path_reason=_path_reason,
                    entry_snap_30s_pct=_r30 if _r30 is not None else 0.0,
                    entry_snap_60s_pct=_r60 if _r60 is not None else 0.0,
                    bond_entry_class=pos.bond_entry_class,
                    bond_outcome_direction=getattr(signal, "bond_outcome_direction", "") or getattr(pos, "bond_outcome_direction", ""),
                    bond_macro_regime=pos.bond_macro_regime,
                    mae_bounce_10s_pct=_bounce_pct,
                    bond_stab_class=getattr(signal, "bond_stab_class", ""),
                    bond_stability_score=int(getattr(signal, "bond_stability_score", 0)),
                    bond_stab_xp_bad=bool(getattr(signal, "bond_stab_xp_bad", False)),
                    bond_stab_slip_bad=bool(getattr(signal, "bond_stab_slip_bad", False)),
                    bond_stab_delta_bad=bool(getattr(signal, "bond_stab_delta_bad", False)),
                    bond_stab_edge_weak=bool(getattr(signal, "bond_stab_edge_weak", False)),
                    bond_stab_vel_flat=bool(getattr(signal, "bond_stab_vel_flat", False)),
                    bond_delta_accel_30s=float(getattr(signal, "bond_delta_accel_30s", 0.0) or 0.0),
                    bond_accel_15s=float(getattr(signal, "bond_accel_15s", 0.0) or 0.0),
                    bond_edge_drift_30s=float(getattr(signal, "bond_edge_drift_30s", 0.0) or 0.0),
                    bond_accel_sustained=bool(getattr(signal, "bond_accel_sustained", False)),
                    bond_has_hist=bool(getattr(signal, "bond_has_hist", False)),
                    bond_smooth_delta_60s=float(getattr(signal, "bond_smooth_delta_60s", 0.0) or 0.0),
                    bond_entry_zone=str(getattr(signal, "bond_entry_zone", "") or ""),
                    pre_score=float(getattr(signal, "pre_score", 0.0) or 0.0),
                    pre_score_version=str(getattr(signal, "pre_score_version", "") or ""),
                    pre_score_schema_hash=str(getattr(signal, "pre_score_schema_hash", "") or ""),
                    pre_score_validity=str(getattr(signal, "pre_score_validity", "") or ""),
                    pre_score_accel=float(getattr(signal, "pre_score_accel", 0.0) or 0.0),
                    pre_score_daccel=float(getattr(signal, "pre_score_daccel", 0.0) or 0.0),
                    pre_score_edge=float(getattr(signal, "pre_score_edge", 0.0) or 0.0),
                    pre_score_stab=float(getattr(signal, "pre_score_stab", 0.0) or 0.0),
                    pre_score_vel=float(getattr(signal, "pre_score_vel", 0.0) or 0.0),
                    pre_score_class=float(getattr(signal, "pre_score_class", 0.0) or 0.0),
                    bond_llm_decision=_bond_llm.get("decision", ""),
                    bond_llm_conf=float(_bond_llm.get("conf", 0.0)),
                    bond_llm_reason=_bond_llm.get("reason", ""),
                    bond_llm_tp_pct=float(_bond_llm.get("shadow_tp_pct", 0.0)),
                    bond_llm_sl_pct=float(_bond_llm.get("shadow_sl_pct", 0.0)),
                    term_vpin=float(getattr(signal, "term_vpin", 0.0) or 0.0),
                    term_spot_delta_5s=float(getattr(signal, "term_spot_delta_5s", 0.0) or 0.0),
                    term_spot_delta_30s=float(getattr(signal, "term_spot_delta_30s", 0.0) or 0.0),
                    term_spot_delta_60s=float(getattr(signal, "term_spot_delta_60s", 0.0) or 0.0),
                    term_spot_delta_5m=float(getattr(signal, "term_spot_delta_5m", 0.0) or 0.0),
                    term_ask_spread_pct=float(getattr(signal, "term_ask_spread_pct", 0.0) or 0.0),
                    term_ask_qty=float(getattr(signal, "term_ask_qty", 0.0) or 0.0),
                    term_ob_imbalance=float(getattr(signal, "term_ob_imbalance", 0.0) or 0.0),
                    term_ob_depth=float(getattr(signal, "term_ob_depth", 0.0) or 0.0),
                    term_remaining_s=float(getattr(signal, "term_remaining_s", 0.0) or 0.0),
                    term_token_delta_3s=float(getattr(signal, "term_token_delta_3s", 0.0) or 0.0),
                    term_token_delta_5s=float(getattr(signal, "term_token_delta_5s", 0.0) or 0.0),
                    term_tok_tick_count_5s=int(getattr(signal, "term_tok_tick_count_5s", 0) or 0),
                    term_tok_tick_count_30s=int(getattr(signal, "term_tok_tick_count_30s", 0) or 0),
                    term_ask_stale_s=float(getattr(signal, "term_ask_stale_s", 999.0) or 999.0),
                    term_tok_decel_ratio=float(getattr(signal, "term_tok_decel_ratio", 0.0) or 0.0),
                    term_token_delta_30s=float(getattr(signal, "term_token_delta_30s", 0.0) or 0.0),
                    term_token_delta_60s=float(getattr(signal, "term_token_delta_60s", 0.0) or 0.0),
                    term_binance_1m_pct=getattr(signal, "term_binance_1m_pct", None),
                    term_binance_5m_pct=getattr(signal, "term_binance_5m_pct", None),
                    term_binance_60m_pct=getattr(signal, "term_binance_60m_pct", None),
                    term_pre_snap_60s=float(getattr(signal, "term_pre_snap_60s", 0.0) or 0.0),
                    term_pre_snap_30s=float(getattr(signal, "term_pre_snap_30s", 0.0) or 0.0),
                    term_pre_snap_open=float(getattr(signal, "term_pre_snap_open", 0.0) or 0.0),
                    term_snap60_eff=float(getattr(signal, "term_snap60_eff", 0.0) or 0.0),
                    term_snap30_eff=float(getattr(signal, "term_snap30_eff", 0.0) or 0.0),
                    term_rsi=float(getattr(signal, "term_rsi", 0.0) or 0.0),
                    term_ask_vwap=float(getattr(signal, "term_ask_vwap", 0.0) or 0.0),
                    traj_mfe_10s=float(self._traj_mfe.get(token_id, {}).get(10, 0.0)),
                    traj_mae_10s=float(self._traj_mae.get(token_id, {}).get(10, 0.0)),
                    traj_mfe_30s=float(self._traj_mfe.get(token_id, {}).get(30, 0.0)),
                    traj_mae_30s=float(self._traj_mae.get(token_id, {}).get(30, 0.0)),
                    price_at_t10s=self._price_at_t10s.get(token_id),
                    extra_fields=_build_weather_extra(
                        meta, pos.bond_entry_class, analytics_exit_price,
                        all_shares, pos.entry_price, pos.stake, net_pnl,
                    ),
                )
            except Exception as _rec_exc:
                logger.error("record_trade failed (trade still closed): %s", _rec_exc)

            # Regime cooldown arming (BOND only, live only).
            if pos.is_bond and not CONFIG.dry_run and net_pnl is not None:
                _rc_now = time.time()
                if net_pnl <= -7.0:
                    # Tier 1: single heavy loss (≥70% of stake) → 5m pause.
                    self._regime_cooldown_until = max(self._regime_cooldown_until, _rc_now + 300)
                    logger.warning(
                        "[BOND] REGIME_COOLDOWN T1 armed — net_pnl=%.2f, 5m pause until %s",
                        net_pnl, time.strftime("%H:%M:%S", time.gmtime(self._regime_cooldown_until)),
                    )
                if net_pnl <= -5.0:
                    # Tier 2: back-to-back losses (2nd ≤-$5 in 30m) → 10m pause.
                    if self._last_regime_loss_ts > 0 and (_rc_now - self._last_regime_loss_ts) <= 1800:
                        self._regime_cooldown_until = max(self._regime_cooldown_until, _rc_now + 600)
                        logger.warning(
                            "[BOND] REGIME_COOLDOWN T2 armed — 2nd loss=%.2f in %.0fs, 10m pause until %s",
                            net_pnl, _rc_now - self._last_regime_loss_ts,
                            time.strftime("%H:%M:%S", time.gmtime(self._regime_cooldown_until)),
                        )
                    self._last_regime_loss_ts = _rc_now

        self._open_meta.pop(token_id, None)
        self._pos_log_ts.pop(token_id, None)
        self._dir_rev_count.pop(token_id, None)
        self._entry_snaps.pop(token_id, None)
        self._term_pre_snap_refs.pop(token_id, None)
        self._term_pre_entry_obs.pop(token_id, None)
        self._sl_below_count.pop(token_id, None)
        self._stall_checked.discard(token_id)
        self._peak_bond_move.pop(token_id, None)
        self._trough_bond_move.pop(token_id, None)
        self._peak_ts.pop(token_id, None)
        self._stall_conf_count.pop(token_id, None)
        self._exhaustion_conf_count.pop(token_id, None)
        self._early_loss_conf_count.pop(token_id, None)
        self._peak_breach_ts.pop(token_id, None)
        self._zombie_flag_ts.pop(token_id, None)
        self._traj_mfe.pop(token_id, None)
        self._traj_mae.pop(token_id, None)
        self._price_at_t10s.pop(token_id, None)
        self._traj_snap_next.pop(token_id, None)
        self._bond_sl_arm_ts.pop(token_id, None)
        self._catas_breach_ts.pop(token_id, None)
        self._catas_cancel_count.pop(token_id, None)
        self._pae_below_since.pop(token_id, None)
        self._pae_above_since.pop(token_id, None)
        self._shadow_fired.pop(token_id, None)
        self._shadow_velocity_buf.pop(token_id, None)
        # Log outcome for BC-armed positions that never fully reversed
        _arm_exit = self._bc_arm_tracker.pop(token_id, None)
        if _arm_exit:
            with open(os.path.join("logs", "wick_events.jsonl"), "a") as _wf:
                _wf.write(json.dumps({
                    "event_type": "WICK_ARM_CLOSED",
                    "ts": time.time(),
                    "asset": _arm_exit["asset"],
                    "exit_reason": reason,
                    "entry_price": _arm_exit["entry_price"],
                    "breach_price": _arm_exit["breach_price"],
                    "breach_move_pct": _arm_exit["breach_move_pct"],
                    "reversed": _arm_exit["reversed"],
                    "elapsed_total_s": round(time.time() - _arm_exit["arm_ts"], 1),
                    "bc_hold_bucket": _arm_exit["bc_hold_bucket"],
                    "hold_s_at_breach": _arm_exit["hold_s_at_breach"],
                    "bond_remaining_at_breach_s": _arm_exit["bond_remaining_at_breach_s"],
                }) + "\n")
        self._terminal_tp_touched.discard(token_id)
        bankroll = self.risk.bankroll.summary()
        logger.info(
            "EXIT %s %s | reason=%s | PnL=$%.3f | capital=$%.2f | streak=%d",
            pos.asset, pos.direction.name, reason,
            net_pnl or 0, bankroll["capital"], bankroll["consecutive_wins"],
        )

        # Post-exit price tracking — answers "was our exit right?"
        # Samples token price at T+30s, T+60s, T+120s after exit.
        # For SL exits: also samples at window_end+60s to capture resolution outcome.
        # Logs to logs/post_exit.jsonl for strategy analysis.
        _post_exit_kwargs = dict(
            token_id=token_id,
            trade_id=self.analytics.last_trade_id,
            asset=pos.asset,
            direction=pos.direction.name,
            exit_price=analytics_exit_price,
            exit_reason=reason,
            entry_price=pos.entry_price,
            window_end_ts=pos.window_end_ts,
            binance_price_at_entry=pos.binance_price_at_entry,
            condition_id=getattr(pos, "condition_id", ""),
            outcome_direction=getattr(pos, "bond_outcome_direction", "up") or "up",
        )
        # Persist to disk so restarts don't lose the resolution task
        if pos.window_end_ts > 0:
            try:
                os.makedirs("logs", exist_ok=True)
                with open(os.path.join("logs", "pending_resolutions.jsonl"), "a") as _pf:
                    _pf.write(json.dumps(_post_exit_kwargs) + "\n")
            except Exception:
                pass
        asyncio.create_task(self._track_post_exit(**_post_exit_kwargs))

    async def _track_post_exit(
        self,
        token_id: str,
        trade_id: str,
        asset: str,
        direction: str,
        exit_price: float,
        exit_reason: str,
        entry_price: float,
        window_end_ts: float = 0.0,
        binance_price_at_entry: float = 0.0,
        condition_id: str = "",
        outcome_direction: str = "up",
    ) -> None:
        """Sample token price at T+30s, T+60s, T+120s after exit.
        For SL exits: also samples at window_end_ts+60s to capture window resolution outcome.
        Tells us whether the exit was correct (price continued) or premature (price recovered).
        Also samples Binance spot at each time point to measure correlation:
          binance_move_at_exit_pct  — how far Binance moved from entry at exit moment
          binance_move_t30s/t60s    — Binance move at T+30s/60s (confirms or diverges)
        Logs 'resolved_correctly' — key metric for diagnosing premature SL exits.
        """
        import json as _json
        log_path = os.path.join("logs", "post_exit.jsonl")
        samples = {}
        binance_samples = {}  # Binance move % from entry at each time point
        # Binance move at exit moment (before any sleep) — key correlation metric.
        # binance_move_at_exit_pct > 0 for BUY_NO = Binance has recovered (reversed).
        # binance_move_at_exit_pct ≈ 0 = Binance flat while PM dropped (PM-specific event).
        # binance_move_at_exit_pct < 0 for BUY_NO = Binance confirming our direction.
        _b_exit = self.feed._spot_price.get(asset.upper(), 0.0)
        binance_move_at_exit_pct = None
        if _b_exit > 0 and binance_price_at_entry > 0:
            binance_move_at_exit_pct = round(
                (_b_exit - binance_price_at_entry) / binance_price_at_entry * 100, 4
            )

        async def _fetch_chainlink_oracle_price(asset: str) -> float | None:
            """Fetch authoritative Chainlink oracle price (source of truth for Polymarket resolution).
            Uses Chainlink Data Feeds JSON RPC interface via Ethereum mainnet.
            Falls back to None if unavailable."""
            if not hasattr(self.feed, "_session"):
                return None

            # Chainlink oracle addresses for Ethereum mainnet
            _chainlink_feeds = {
                "BTC": "0xf4030086522a99af011f1890a0d02786031b67f7",
                "ETH": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
                "SOL": "0x24379f51d3147dafbc5ddfb4b1e07b25e47fafea",
            }

            _feed_addr = _chainlink_feeds.get(asset.upper())
            if not _feed_addr:
                return None

            try:
                # Query latest Chainlink oracle round data
                # Using Alchemy RPC (public endpoint, no key required for basic queries)
                _rpc_url = "https://eth-mainnet.alchemyapi.io/v2/demo"

                # Chainlink AggregatorV3 latestRoundData() call
                _contract_abi = [{"inputs":[],"name":"latestRoundData","outputs":[{"name":"roundId","type":"uint80"},{"name":"answer","type":"int256"},{"name":"startedAt","type":"uint256"},{"name":"updatedAt","type":"uint256"},{"name":"answeredInRound","type":"uint80"}],"stateMutability":"view","type":"function"}]

                # Simple JSON-RPC eth_call to get price
                _payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [
                        {
                            "to": _feed_addr,
                            "data": "0xfeaf968c",  # latestRoundData() function selector
                        },
                        "latest"
                    ],
                    "id": 1,
                }

                import aiohttp as _aiohttp
                async with self.feed._session.post(
                    _rpc_url,
                    json=_payload,
                    timeout=_aiohttp.ClientTimeout(total=5),
                ) as _resp:
                    if _resp.status == 200:
                        _data = await _resp.json()
                        if "result" in _data and _data["result"] != "0x":
                            # Parse the returned uint256 (scaled by 1e8 for crypto pairs)
                            _hex_result = _data["result"]
                            if len(_hex_result) >= 66:  # 0x + 64 hex chars for answer (second return value)
                                _answer_hex = "0x" + _hex_result[66:130]  # Extract answer field
                                _answer_raw = int(_answer_hex, 16)
                                _oracle_price = _answer_raw / 1e8  # Chainlink returns prices scaled by 10^8
                                return round(_oracle_price, 8)
            except Exception as _e:
                logger.debug("CHAINLINK oracle fetch %s: %s", asset, _e)

            return None

        # Resolution task: polls Gamma API starting at window_end+10s.
        # Runs concurrently with the T+30/60/120 price sampling loop.
        async def _capture_resolution() -> None:
            if not window_end_ts:
                return
            # Polymarket 5m up/down markets resolve based on Chainlink BTC/ETH/SOL
            # price at window_end vs window_start. outcomePrices in the Gamma API is
            # the CLOB price (collapses to 0 for all tokens after market close) — it
            # does NOT reflect oracle settlement. Binance 5m klines use the same 300s
            # grid and agree directionally with Chainlink >99% of the time.
            # Wait 35s past window_end so the 5m kline is fully closed.
            _wait = max(35.0, window_end_ts + 35.0 - time.time())
            if _wait > 910:
                return  # window too far out, skip
            if _wait > 0:
                await asyncio.sleep(_wait)
            try:
                _wop: float | None = None
                _chainlink_price: float | None = None
                _resolution_method = "unknown"

                # Fetch Chainlink oracle price (Polymarket's authoritative source)
                _chainlink_price = await _fetch_chainlink_oracle_price(asset)
                if _chainlink_price is not None:
                    logger.debug("RESOLUTION chainlink %s: $%.8f", trade_id[:12], _chainlink_price)

                # Primary: Binance 5m kline open vs close for the exact window.
                _symbol_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
                _symbol = _symbol_map.get(asset.upper())
                _window_start_ms = int((window_end_ts - 300) * 1000)
                if _symbol and getattr(self.feed, "_session", None):
                    import aiohttp as _aiohttp
                    try:
                        async with self.feed._session.get(
                            "https://api.binance.com/api/v3/klines",
                            params={"symbol": _symbol, "interval": "5m",
                                    "startTime": _window_start_ms, "limit": 1},
                            timeout=_aiohttp.ClientTimeout(total=8),
                        ) as _resp:
                            if _resp.status == 200:
                                _klines = await _resp.json()
                                if _klines and len(_klines[0]) >= 5:
                                    _open  = float(_klines[0][1])
                                    _close = float(_klines[0][4])
                                    _wop = 1.0 if _close >= _open else 0.0
                                    _resolution_method = f"kline:{_open:.2f}->{_close:.2f}"
                                    if _chainlink_price is not None:
                                        _resolution_method += f" (chainlink: ${_chainlink_price:.8f})"
                    except Exception as _ke:
                        logger.debug("RESOLUTION kline fetch %s: %s", trade_id[:12], _ke)

                if _wop is not None:
                    # _wop=1.0 means price went UP (kline close>=open); 0.0 means DOWN.
                    # For YES UP: correct if price went UP (_wop>=0.5).
                    # For YES DOWN: correct if price went DOWN (_wop<0.5).
                    _entered_correctly = (_wop >= 0.5) if outcome_direction == "up" else (_wop < 0.5)
                    _res_rec = {
                        "trade_id": trade_id,
                        "record_type": "resolution",
                        "window_outcome_price": _wop,
                        "chainlink_price": _chainlink_price if _chainlink_price is not None else 0.0,
                        "entered_correctly": _entered_correctly,
                        "resolution_delay_s": round(time.time() - window_end_ts),
                        "exit_reason": exit_reason,
                        "resolution_method": _resolution_method,
                    }
                    with open(log_path, "a") as _rf:
                        _rf.write(_json.dumps(_res_rec) + "\n")
                    # Patch trades.jsonl so wop and entered_correctly are queryable
                    # without joining post_exit — rewrite matching line in place.
                    _trades_path = os.path.join("logs", "trades.jsonl")
                    try:
                        _lines = []
                        _pnl_delta = 0.0
                        with open(_trades_path) as _tf:
                            for _tl in _tf:
                                try:
                                    _tr = _json.loads(_tl.strip())
                                    if _tr.get("trade_id") == trade_id:
                                        _tr["window_outcome_price"] = _wop
                                        _tr["chainlink_price"] = _chainlink_price if _chainlink_price is not None else 0.0
                                        _tr["entered_correctly"] = _entered_correctly
                                        # kline_pnl: canonical ground-truth PnL if held to resolution.
                                        # WIN = guaranteed redemption at $1/share; LOSE = token worthless.
                                        # net_pnl stays as actual realized; kline_pnl is the analysis truth.
                                        _tr_shares = _tr.get("shares", 0.0)
                                        _tr_ep     = _tr.get("entry_price", 0.0)
                                        _tr_stake  = _tr.get("stake", _tr_ep * _tr_shares)
                                        _tr_fee    = _tr.get("fee_paid", 0.0)
                                        if _entered_correctly:
                                            _tr["kline_pnl"] = round(_tr_shares * (1.0 - _tr_ep) - _tr_fee, 4)
                                        else:
                                            _tr["kline_pnl"] = round(-_tr_stake - _tr_fee, 4)
                                        # CAS_LOWASK holds to resolution — patch exit_price and net_pnl
                                        # to reflect actual resolution (1.0 win / 0.0 loss).
                                        # _pnl_delta intentionally left 0: BANKROLL_AUTO_CORRECT already
                                        # reconciles the wallet after expiry; patching bankroll here
                                        # would double-count.
                                        if (_tr.get("bond_entry_class") == "CAS_LOWASK"
                                                and _tr.get("exit_reason") == "BOND_EXPIRED_UNSOLD"):
                                            _corr_exit = 1.0 if _entered_correctly else 0.0
                                            _cas_delta = (_corr_exit - _tr.get("exit_price", 0.0)) * _tr_shares
                                            _tr["exit_price"] = _corr_exit
                                            _tr["exit_reason"] = "BOND_RESOLVED_YES" if _entered_correctly else "BOND_RESOLVED_NO"
                                            _tr["gross_pnl"] = round(_tr_shares * _corr_exit - _tr_stake, 4)
                                            _tr["net_pnl"] = round(_tr.get("net_pnl", 0.0) + _cas_delta, 4)
                                            _tr["capital_after"] = round(_tr.get("capital_after", 0.0) + _cas_delta, 4)
                                        elif _tr.get("exit_price_uncertain"):
                                            # Correct exit_price and net_pnl using resolution.
                                            # exit_price was a live-bid fallback; wop is authoritative.
                                            _corr_ep = 0.99 if _entered_correctly else 0.01
                                            _old_ep = _tr.get("exit_price", 0.0)
                                            _old_pnl = _tr.get("net_pnl", 0.0)
                                            _pnl_delta = (_corr_ep - _old_ep) * _tr_shares
                                            _tr["exit_price"] = round(_corr_ep, 4)
                                            _tr["gross_pnl"] = round(_tr.get("gross_pnl", 0.0) + _pnl_delta, 4)
                                            _tr["net_pnl"] = round(_old_pnl + _pnl_delta, 4)
                                            _tr["capital_after"] = round(_tr.get("capital_after", 0.0) + _pnl_delta, 4)
                                            _tr["exit_price_uncertain"] = False
                                            logger.info(
                                                "RESOLUTION corrected uncertain exit %s: "
                                                "ep %.4f→%.4f pnl %.4f→%.4f delta=%.4f",
                                                trade_id[:12], _old_ep, _corr_ep,
                                                _old_pnl, _tr["net_pnl"], _pnl_delta,
                                            )
                                        _lines.append(_json.dumps(_tr) + "\n")
                                    else:
                                        _lines.append(_tl)
                                except Exception:
                                    _lines.append(_tl)
                        with open(_trades_path, "w") as _tf:
                            _tf.writelines(_lines)
                        # Correct bankroll if exit_price was uncertain
                        if _pnl_delta != 0.0:
                            self.risk.bankroll.capital += _pnl_delta
                            self.risk.bankroll.save()
                            logger.info(
                                "RESOLUTION bankroll corrected by %.4f → %.4f",
                                _pnl_delta, self.risk.bankroll.capital,
                            )
                    except Exception as _pe:
                        logger.debug("trades.jsonl resolution patch failed: %s", _pe)
                    logger.info(
                        "RESOLUTION %s/%s [%s] | outcome=%.1f correct=%s delay=%ds method=%s",
                        asset, direction, exit_reason, _wop, _entered_correctly,
                        round(time.time() - window_end_ts), _resolution_method,
                    )
                else:
                    logger.debug("RESOLUTION %s [%s] | no outcome resolved", trade_id[:12], exit_reason)
            except Exception as _re:
                logger.debug("resolution capture failed %s: %s", trade_id[:12], _re)

        if window_end_ts > 0:
            asyncio.create_task(_capture_resolution())

        elapsed = 0
        for delay in (30, 60, 120):
            await asyncio.sleep(delay - elapsed)
            elapsed = delay
            try:
                # Always use live fetch — in-memory cache (best_ask / _order_books)
                # is stale or empty after exit, giving null samples. fetch_order_book
                # makes a real API call and is confirmed working (same path as
                # window_outcome_price which is always populated).
                price = 0.0
                token = self.feed.tokens.get(token_id)
                if token and hasattr(token, "best_ask") and token.best_ask > 0:
                    price = token.best_ask
                if not price:
                    _ob = await self.feed.fetch_order_book(token_id)
                    if _ob and _ob.asks:
                        price = _ob.asks[0][0]
                samples[f"t{delay}s"] = round(price, 4) if price else None
                # Binance spot at this time point — measures whether Binance
                # is confirming, diverging, or reversing vs our entry direction.
                _b_now = self.feed._spot_price.get(asset.upper(), 0.0)
                if _b_now > 0 and binance_price_at_entry > 0:
                    _b_move = (_b_now - binance_price_at_entry) / binance_price_at_entry * 100
                    binance_samples[f"binance_move_t{delay}s_pct"] = round(_b_move, 4)
            except Exception:
                samples[f"t{delay}s"] = None

        # Accumulate all post-exit prices for window_max_adv computation.
        # Starts from T+30/60/120 samples; extended by continuous sampling until
        # window_end (added below). Entry_price is used as reference for adverse %.
        _post_exit_prices: list[float] = [p for p in samples.values() if p]

        # ── Write T+30/60/120 record immediately after samples are collected ──────
        # Previous bug: write was deferred until after window_end + 60s wait,
        # meaning for a 15m trade exited at elap=0.07, the write happened ~15 min
        # later — after restarts or session ends, data was lost.
        # Fix: write now with what we have; resolution outcome appended separately.
        _is_sl_exit = exit_reason.startswith("STOP_LOSS") or exit_reason in (
            "CIRCUIT_BREAKER", "TRAIL_STOP", "STOP_LOSS_EXT",
            "VELOCITY_EXIT", "SL_15S", "PRICE_FLOOR", "RATCHET_SL",
        ) or "TIGHT_SL" in exit_reason
        move_from_exit = {}
        for k, p in samples.items():
            if p and exit_price > 0:
                move_from_exit[k] = round((p - exit_price) / exit_price * 100, 2)

        move_from_entry = {}
        for k, p in samples.items():
            if p and entry_price > 0:
                move_from_entry[k] = round((p - entry_price) / entry_price * 100, 2)

        record = {
            "trade_id": trade_id,
            "asset": asset,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "drawdown_pct": round((entry_price - exit_price) / entry_price * 100, 1) if entry_price > 0 else None,
            "sl_tier": (
                "T1_30pct" if entry_price > 0 and (entry_price - exit_price) / entry_price <= 0.35
                else "T2_50pct" if entry_price > 0 and (entry_price - exit_price) / entry_price <= 0.55
                else "T3_catastrophic"
            ) if exit_reason in ("STOP_LOSS", "STOP_LOSS_EXT") else None,
            **samples,
            "move_from_entry_pct": move_from_entry,
            "move_from_exit_pct": move_from_exit,
            # Resolution fields — populated below after window ends, null for now
            "window_outcome_price": None,
            "entered_correctly": None,
            "resolution_delay_s": None,
            "window_end_ts": window_end_ts if window_end_ts > 0 else None,
            "binance_move_at_exit_pct": binance_move_at_exit_pct,
            **binance_samples,
        }

        try:
            os.makedirs("logs", exist_ok=True)
            with open(log_path, "a") as f:
                f.write(_json.dumps(record) + "\n")
            logger.info(
                "POST_EXIT %s/%s [%s] | exit=%.4f | +30s=%s +60s=%s +120s=%s",
                asset, direction, exit_reason, exit_price,
                samples.get("t30s"), samples.get("t60s"), samples.get("t120s"),
            )
        except Exception as exc:
            logger.debug("post_exit log failed: %s", exc)

        # ── Continuous sampling from T+120s to window_end ──────────────────────
        # Fills the gap between our exit and window resolution, giving a real
        # picture of "where did the market go after we left". Used to compute
        # window_max_adv_from_entry_pct (worst price vs entry across full window).
        # Samples every 60s; stops 5s before window_end to avoid racing the
        # final resolution fetch.
        if window_end_ts > 0:
            _now_inner = time.time()
            if _now_inner < window_end_ts - 5 and window_end_ts - _now_inner <= 900:
                while True:
                    _gap = window_end_ts - time.time() - 5
                    if _gap <= 0:
                        break
                    await asyncio.sleep(min(60.0, _gap))
                    try:
                        _p_cont = 0.0
                        _tok_c = self.feed.tokens.get(token_id)
                        if _tok_c and hasattr(_tok_c, "best_ask") and _tok_c.best_ask > 0:
                            _p_cont = _tok_c.best_ask
                        if not _p_cont:
                            _ob_c = await self.feed.fetch_order_book(token_id)
                            if _ob_c and _ob_c.asks:
                                _p_cont = _ob_c.asks[0][0]
                        if _p_cont:
                            _post_exit_prices.append(round(_p_cont, 4))
                    except Exception:
                        pass

        # Resolution is now captured by the concurrent _capture_resolution() task
        # fired at the start of this function — no duplicate block needed here.

    # expo_shadow_resolve retired 2026-05-09 — subsumed by shadow window_resolution + market_timeline join

    # ── Pending resolution replay (restart recovery) ─────────────────────────

    async def _replay_pending_resolutions(self) -> None:
        """Re-schedule post-exit resolution tasks lost due to bot restarts."""
        pending_path = os.path.join("logs", "pending_resolutions.jsonl")
        post_exit_path = os.path.join("logs", "post_exit.jsonl")
        if not os.path.exists(pending_path):
            return
        # Load trade_ids already resolved
        completed: set = set()
        if os.path.exists(post_exit_path):
            try:
                with open(post_exit_path) as f:
                    for line in f:
                        try:
                            rec = json.loads(line.strip())
                            if rec.get("trade_id"):
                                completed.add(rec["trade_id"])
                        except Exception:
                            pass
            except Exception:
                pass
        now = time.time()
        replayed = 0
        try:
            with open(pending_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                        tid = rec.get("trade_id")
                        wend = rec.get("window_end_ts", 0)
                        if not tid or tid in completed:
                            continue
                        if wend == 0 or wend + 900 < now:
                            continue  # too stale (>15 min past window end)
                        asyncio.create_task(self._track_post_exit(**rec))
                        replayed += 1
                    except Exception:
                        pass
        except Exception:
            pass
        if replayed > 0:
            logger.info("Replayed %d pending resolution tasks from previous session", replayed)

    # ── Residual share sweep ──────────────────────────────────────────────────

    async def _sweep_residuals(self) -> None:
        """Retry selling shares that survived partial cascade_sell at position close."""
        if not self._residual_pending:
            return
        now = time.time()
        to_remove = []
        for token_id, r in list(self._residual_pending.items()):
            if now - r["last_try"] < 60:
                continue
            if r["attempts"] >= 10:
                logger.error(
                    "RESIDUAL ABANDONED: %.4f %s shares after 10 attempts (~10 min) — "
                    "forcing bankroll update and removing from pending.",
                    r["shares"], r["asset"],
                )
                try:
                    _res_pnl = self.risk.close_position(token_id, 0.50, "RESIDUAL_ABANDONED", shares_override=r["shares"])
                    if _res_pnl is not None:
                        try:
                            self.analytics.record_trade(
                                token_id=token_id, asset=r["asset"], direction=Direction.BUY_YES,
                                entry_price=r.get("entry_price", 0.50), exit_price=0.50,
                                stake=r.get("stake", 0.0), shares=r["shares"],
                                entry_fill=None, exit_fills=[],
                                exit_reason="RESIDUAL_ABANDONED", signal=SignalBreakdown(
                                    direction=Direction.BUY_YES, entry_price=0.50,
                                    composite=0.0, confidence=0.0, breakout_score=0.0,
                                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                    reason="residual_abandoned",
                                ),
                                ts_open=r.get("ts_open", time.time()), ts_close=time.time(),
                                capital_before=self.risk.bankroll.capital - _res_pnl,
                                heat_check_active=False, consecutive_wins=0,
                                best_ask=r.get("best_ask", 0.0),
                                net_pnl_actual=_res_pnl,
                                market_type=r.get("market_type", "unknown"),
                                is_live=not CONFIG.dry_run,
                                signal_source=r.get("signal_source", "SNIPER"),
                                window_size_s=r.get("window_size_s", 0),
                            )
                        except Exception as _re:
                            logger.error("record_trade RESIDUAL_ABANDONED failed: %s", _re)
                except Exception as _close_err:
                    logger.error("RESIDUAL ABANDONED close_position failed: %s", _close_err)
                to_remove.append(token_id)
                continue
            r["attempts"] += 1
            r["last_try"] = now
            try:
                fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=round(r["shares"], 4),
                    current_price=0.50,   # mid estimate; CLOB adjusts to actual bid
                    reason="RESIDUAL_RETRY",
                    neg_risk=r["neg_risk"],
                    tick_size=r["tick_size"],
                    force_exit=True,
                )
                sold = sum(f.total_size for f in fills)
                if sold > 0:
                    r["shares"] = round(r["shares"] - sold, 4)
                    logger.info(
                        "RESIDUAL RETRY %s: sold %.4f shares (attempt %d, %.4f remaining)",
                        r["asset"], sold, r["attempts"], r["shares"],
                    )
                if r["shares"] <= 0.05:
                    to_remove.append(token_id)
            except Exception as exc:
                logger.warning("RESIDUAL RETRY %s attempt %d failed: %s",
                               r["asset"], r["attempts"], exc)
        for tid in to_remove:
            self._residual_pending.pop(tid, None)

    # ── 10-second CLOB heartbeat ──────────────────────────────────────────────

    async def _heartbeat_loop(self, _watchdog_ping: list = None) -> None:
        """Keep CLOB session alive; prevents silent GTC order cancellation."""
        _hb_failures = 0
        _last_reconcile_ts = 0.0
        _RECONCILE_INTERVAL = 300   # reconcile bankroll vs actual USDC every 5 min
        _RECONCILE_DRIFT_WARN = 0.50  # warn if internal vs actual diverges > $0.50
        _RECONCILE_DRIFT_CORRECT = 2.00  # auto-correct if divergence > $2.00
        _last_full_orphan_scan_ts = 0.0
        _FULL_ORPHAN_SCAN_INTERVAL = 120  # full balance sweep every 2min — 5m windows need fast detection
        while self._running:
            await asyncio.sleep(10)
            # Ping watchdog — proves event loop is alive to the daemon thread
            if _watchdog_ping is not None:
                _watchdog_ping[0] = time.monotonic()
            try:
                # post_heartbeat() call removed 2026-06-10: it sent a FRESH uuid4
                # every call — never a registered heartbeat — so every POST 400'd
                # ("Invalid Heartbeat ID", 6.7k errors since the service rolled out
                # 06-08). A REAL registered heartbeat would arm the CLOB dead-man
                # switch (cancel all GTC orders on a 15s gap) — the opposite of
                # what hold-to-resolution resting maker orders want.
                # 2026-07-04 EVOLVE: maybe_reset_daily() had ZERO callers, so
                # daily_start_capital froze ($15.95 vs capital $100.94) and the
                # 14% intraday loss halt could never trip. Wired here (integer
                # day compare, cheap at 10s cadence).
                self.risk.bankroll.maybe_reset_daily()
                await self._sweep_residuals()
                # Periodic full scan: force_all=True every 5min catches orphans created
                # mid-session (not just near window-close). Without this, an orphan can
                # sit undetected for up to 13min (15m window) until the 120s horizon fires.
                _now_hb = time.time()
                if _now_hb - _last_full_orphan_scan_ts >= _FULL_ORPHAN_SCAN_INTERVAL:
                    logger.debug("HEARTBEAT: periodic full orphan scan (force_all=True)")
                    await self._window_end_balance_sweep(force_all=True)
                    _last_full_orphan_scan_ts = _now_hb
                else:
                    await self._window_end_balance_sweep()
                _hb_failures = 0  # reset on success

                # ── Hourly bankroll reconciliation ───────────────────────────
                # Compare internal capital estimate to actual Polymarket USDC balance.
                # Drift sources: fee estimation errors, orphan sells, crash-recovery gaps.
                # Auto-corrects large divergences; warns on small ones.
                now = time.time()
                if (now - _last_reconcile_ts >= _RECONCILE_INTERVAL
                        and not CONFIG.dry_run):
                    _last_reconcile_ts = now
                    actual_usdc = self.orders.fetch_usdc_balance()
                    if actual_usdc is not None:
                        internal = self.risk.bankroll.capital
                        # capital = cash + open-position cost basis, so reconcile
                        # works with positions open (always reflect real wallet).
                        pos_value = sum(p.remaining_shares * p.entry_price
                                        for p in self.risk.open_positions.values())
                        pos_value += _ladder_open_cost()
                        actual_usdc = actual_usdc + pos_value
                        drift = actual_usdc - internal
                        if abs(drift) >= _RECONCILE_DRIFT_WARN:
                            logger.warning(
                                "BANKROLL DRIFT: internal=$%.2f actual=$%.2f drift=%+.2f",
                                internal, actual_usdc, drift,
                            )
                        if abs(drift) >= _RECONCILE_DRIFT_CORRECT:
                            logger.warning(
                                "BANKROLL AUTO-CORRECT: $%.2f → $%.2f (drift=%+.2f)",
                                internal, actual_usdc, drift,
                            )
                            self.risk.bankroll.capital = actual_usdc
                            self.risk.bankroll._save()
                            self.analytics._write_jsonl(CONFIG.analytics.trade_log, {
                                "record_type": "CAPITAL_CORRECTION",
                                "ts": time.time(),
                                "source": "BANKROLL_AUTO_CORRECT",
                                "capital_before": internal,
                                "capital_after": actual_usdc,
                                "correction_delta": round(drift, 4),
                                "is_live": not CONFIG.dry_run,
                            })
                        else:
                            logger.debug(
                                "Bankroll reconcile OK: internal=$%.2f actual=$%.2f drift=%+.2f",
                                internal, actual_usdc, drift,
                            )

            except Exception as exc:
                _hb_failures += 1
                if _hb_failures >= 2:
                    logger.critical(
                        "Heartbeat CRITICAL failure #%d: %s — GTC orders may expire",
                        _hb_failures, exc,
                    )
                else:
                    logger.warning("Heartbeat failure #%d: %s", _hb_failures, exc)

    # ── Window-end CLOB balance sweep ─────────────────────────────────────────

    async def _window_end_balance_sweep(self, force_all: bool = False) -> None:
        """
        For every tracked updown token within 120s of window close, fetch the
        actual CLOB balance and force-sell any non-zero holding.

        Catches shares that survived partial cascades or came from sessions the
        bot didn't track — anything sitting in the wallet that will resolve at
        0 or 1 without being sold.

        force_all=True: bypass the 120s time window check — used at startup to
        immediately sell orphan tokens from previous sessions (otherwise they
        wait up to 13 minutes before the normal sweep catches them).
        """
        if CONFIG.dry_run:
            return
        now = time.time()
        _WINDOW_END_HORIZON = 120  # seconds before close to start checking

        # UPDOWN-SNIPER holds updown tokens to redemption by design (separate
        # process, shared wallet) — its positions never appear in
        # risk.open_positions, so without this guard the sweep force-sells its
        # winners at the bid and the sniper's settle bookkeeping diverges from
        # wallet truth. Fail-open: unreadable state file → empty set.
        _sniper_held: set = set()
        try:
            with open("logs/updown_sniper_state.json") as _snf:
                _snst = json.load(_snf)
            _sniper_held = {
                str(v.get("token"))
                for v in (_snst.get("open") or {}).values()
                if v.get("token")
            }
        except Exception:
            pass

        for token_id, token in list(self.feed.tokens.items()):
            if token.market_type != "updown":
                continue
            if token.window_end_ts <= 0:
                continue
            time_to_close = token.window_end_ts - now
            # Only act in the final 120s window, or if already past close (up to 60s after),
            # OR if force_all=True (startup sweep — sell any untracked balance immediately).
            if not force_all and not (-60 <= time_to_close <= _WINDOW_END_HORIZON):
                continue

            # Rate-limit: don't hammer CLOB for the same token more than once per 30s
            _last_key = f"_webs_{token_id}"
            if now - self._open_meta.get(_last_key, 0) < 30:
                continue
            self._open_meta[_last_key] = now

            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(
                None, self.orders.fetch_token_balance, token_id
            )
            if balance is None or balance < 0.05:
                continue

            asset = token.asset
            side = getattr(token, "side", "?")

            # Update tracked position's remaining_shares if we have one
            if token_id in self.risk.open_positions:
                pos = self.risk.open_positions[token_id]
                if abs(balance - pos.remaining_shares) > 0.05:
                    logger.warning(
                        "WINDOW-END SYNC %s/%s: tracked=%.4f CLOB=%.4f — correcting",
                        asset, side, pos.remaining_shares, balance,
                    )
                    pos.remaining_shares = round(balance, 4)
                # Let the normal exit loop handle it (will fire HARD_EXIT or FLOOR_SELL)
                continue

            # Orphaned balance — not in tracked positions. Force-sell immediately.
            if token_id in self._exit_in_progress:
                continue
            # Skip tokens with an in-flight entry — limit_buy's orphan-recovery
            # check waits up to 20s to confirm FAILED orders actually filled.
            # Without this, the sweep races the recovery and force-sells shares
            # before open_position() can track them as a normal position.
            if token_id in self._pending_entries:
                continue
            # Held by the updown sniper (hold-to-redemption policy) — not an
            # orphan; the Redeemer converts winners to cash after resolution.
            if token_id in _sniper_held:
                continue
            token_meta = self.feed.tokens.get(token_id)
            ob = self.feed.get_order_book(token_id)
            sell_price = ob.bids[0][0] if (ob and ob.bids) else 0.50
            # Skip dust below CLOB $1 minimum (+50% buffer). Cannot be sold —
            # retry loop was hammering /trades every 30s forever.
            if balance * sell_price < 1.50:
                continue
            logger.warning(
                "WINDOW-END ORPHAN %s/%s: %.4f shares in CLOB wallet, not tracked — force-selling",
                asset, side, balance,
            )
            self._exit_in_progress.add(token_id)
            try:
                orphan_fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=balance,
                    current_price=sell_price,
                    reason="ORPHAN_SELL",
                    neg_risk=getattr(token_meta, "neg_risk", False),
                    tick_size=getattr(token_meta, "tick_size", "0.01"),
                    force_exit=True,
                )
                sold = sum(f.total_size for f in orphan_fills)
                avg_price = (
                    sum(f.avg_fill_price * f.total_size for f in orphan_fills) / sold
                    if sold > 0 else sell_price
                )
                if sold > 0:
                    logger.info(
                        "ORPHAN SOLD %s/%s: %.4f shares @ %.4f",
                        asset, side, sold, avg_price,
                    )
                    # Recover entry price from CLOB BUY history so PnL is real.
                    # Orphans arise when entry filled on Polymarket but wasn't tracked
                    # locally (CF block during confirmation). The CLOB has the buy fill.
                    _orphan_entry_price = 0.0
                    if not CONFIG.dry_run:
                        await asyncio.sleep(1.5)
                        try:
                            _all_fills = await asyncio.to_thread(
                                self.orders.fetch_recent_token_sells,
                                token_id,
                                time.time() - 900,  # last 15 min
                            )
                            # Buys are fills priced meaningfully below the exit price.
                            _buy_fills = [
                                (p, s) for p, s in _all_fills
                                if p < avg_price * 0.97
                            ]
                            if _buy_fills:
                                _b_sz  = sum(s for _, s in _buy_fills)
                                _b_val = sum(p * s for p, s in _buy_fills)
                                if _b_sz > 0:
                                    _orphan_entry_price = round(_b_val / _b_sz, 6)
                                    logger.info(
                                        "ORPHAN entry recovered from CLOB: %s/%s ep=%.4f "
                                        "(%d buy fill(s), %.4f shares)",
                                        asset, side, _orphan_entry_price,
                                        len(_buy_fills), _b_sz,
                                    )
                        except Exception as _ce:
                            logger.warning("ORPHAN CLOB entry lookup failed: %s", _ce)

                    self.analytics.record_orphan_sell(
                        token_id=token_id,
                        asset=asset,
                        side=side,
                        shares_sold=sold,
                        avg_exit_price=avg_price,
                        is_live=not CONFIG.dry_run,
                        avg_entry_price=_orphan_entry_price,
                    )
                    # Reconcile bankroll from actual CLOB USDC balance — ground truth.
                    # Guard: skip if other positions are open (raw USDC excludes locked capital).
                    if not CONFIG.dry_run and not self.risk.open_positions:
                        await asyncio.sleep(2.0)
                        try:
                            _real_bal = await asyncio.to_thread(self.orders.fetch_usdc_balance)
                            if _real_bal is not None:
                                _real_bal += _ladder_open_cost()
                                _old_cap = self.risk.bankroll.capital
                                _delta   = round(_real_bal - _old_cap, 4)
                                self.risk.bankroll.capital = round(_real_bal, 4)
                                self.risk.bankroll._save()
                                logger.warning(
                                    "Post-orphan bankroll reconciled: $%.2f → $%.2f (delta=%+.2f)",
                                    _old_cap, _real_bal, _delta,
                                )
                                self.analytics._write_jsonl(CONFIG.analytics.trade_log, {
                                    "record_type": "CAPITAL_CORRECTION",
                                    "ts": time.time(),
                                    "source": "POST_ORPHAN_RECONCILE",
                                    "capital_before": _old_cap,
                                    "capital_after": round(_real_bal, 4),
                                    "correction_delta": _delta,
                                    "is_live": True,
                                })
                            else:
                                logger.warning("Post-orphan USDC balance fetch returned None")
                        except Exception as _re:
                            logger.warning("Post-orphan bankroll reconcile failed: %s", _re)
                    elif not CONFIG.dry_run and self.risk.open_positions:
                        logger.info(
                            "Post-orphan reconcile skipped: %d position(s) still open",
                            len(self.risk.open_positions),
                        )
                else:
                    logger.warning(
                        "ORPHAN SELL FAILED %s/%s: %.4f shares unsold",
                        asset, side, balance,
                    )
            except Exception as _e:
                logger.error("ORPHAN SELL error %s: %s", token_id[:12], _e)
            finally:
                self._exit_in_progress.discard(token_id)

    # ── Startup orphan sweep ──────────────────────────────────────────────────

    async def _startup_orphan_sweep(self) -> None:
        """
        On startup:
        1. Validate tracked positions — if CLOB balance = 0, the user sold manually
           last session. Close the position record immediately rather than tracking
           a ghost forever.
        2. Sell any untracked token balances from previous sessions.

        Waits 10s for feed to populate before scanning.
        """
        if CONFIG.dry_run:
            return
        await asyncio.sleep(10.0)
        logger.info("STARTUP ORPHAN SWEEP: validating tracked positions and orphan balances...")

        # Step 1: validate tracked positions have actual CLOB balances
        for token_id, pos in list(self.risk.open_positions.items()):
            try:
                balance = self.orders.fetch_token_balance(token_id)
                if balance is None:
                    logger.warning(
                        "STARTUP: can't verify balance for tracked %s/%s — will retry via normal loop",
                        pos.asset, pos.direction.name,
                    )
                    continue
                if balance < 0.05:
                    # Guard: if position was opened very recently, CLOB balance may not
                    # have propagated yet (fresh buy shows 0 for up to ~30s).
                    # Don't close a position that was just bought this session.
                    _pos_age_s = time.time() - pos.open_ts
                    if _pos_age_s < 120:
                        logger.warning(
                            "STARTUP: %s/%s balance=0 but position only %.0fs old — "
                            "CLOB propagation lag, skipping close, normal loop will handle",
                            pos.asset, pos.direction.name, _pos_age_s,
                        )
                        continue
                    # WEATHER_M1_PROBE and other hold-to-resolution strategies don't have
                    # CLOB resting orders — balance API returning 0 under load is a known
                    # failure mode. Never orphan-close these; their strategy modules handle exits.
                    _ec_orphan = getattr(pos, "bond_entry_class", "")
                    if _ec_orphan.startswith("WEATHER_") or _ec_orphan == "SPORTS_COPY":
                        logger.warning(
                            "STARTUP: %s/%s is %s with balance=0 — preserving (balance API may be stale)",
                            pos.asset, pos.direction.name, _ec_orphan,
                        )
                        continue
                    # Shares are gone — sold last session (cascade or manual).
                    # Try CLOB history to recover actual exit price before closing flat.
                    logger.warning(
                        "STARTUP: %s/%s has 0 CLOB balance — querying CLOB history for exit price",
                        pos.asset, pos.direction.name,
                    )
                    _startup_exit_price = pos.entry_price  # fallback: flat
                    try:
                        _clob_sells = await asyncio.to_thread(
                            self.orders.fetch_recent_token_sells,
                            token_id,
                            pos.open_ts,
                        )
                        if _clob_sells:
                            _sz = sum(s for _, s in _clob_sells)
                            _val = sum(p * s for p, s in _clob_sells)
                            if _sz > 0:
                                _startup_exit_price = round(_val / _sz, 6)
                                logger.info(
                                    "STARTUP: %s/%s exit price recovered from CLOB → %.4f",
                                    pos.asset, pos.direction.name, _startup_exit_price,
                                )
                    except Exception as _ce:
                        logger.warning("STARTUP CLOB recovery %s failed: %s", token_id[:8], _ce)
                    pnl = self.risk.close_position(token_id, _startup_exit_price, "STARTUP_EXTERNALLY_SOLD")
                    meta = self._open_meta.get(token_id, {})
                    _sig = meta.get("signal") or SignalBreakdown(
                        direction=pos.direction, entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="startup_externally_sold",
                    )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=_startup_exit_price,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=meta.get("entry_fill"), exit_fills=[],
                            exit_reason="STARTUP_EXTERNALLY_SOLD", signal=_sig,
                            ts_open=meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital,
                            heat_check_active=False, consecutive_wins=0,
                            best_ask=pos.best_ask,
                            net_pnl_actual=pnl or 0.0,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=meta.get("signal_source", "SNIPER"),
                            window_size_s=meta.get("window_size_s") or pos.window_seconds or 0,
                            bond_delta_accel_30s=float(getattr(_sig, "bond_delta_accel_30s", 0.0) or 0.0),
                            bond_edge_drift_30s=float(getattr(_sig, "bond_edge_drift_30s", 0.0) or 0.0),
                            bond_accel_sustained=bool(getattr(_sig, "bond_accel_sustained", False)),
                            bond_has_hist=bool(getattr(_sig, "bond_has_hist", False)),
                        )
                    except Exception as _e:
                        logger.error("record_trade STARTUP_EXTERNALLY_SOLD failed: %s", _e)
                    self._open_meta.pop(token_id, None)
                else:
                    _token_in_feed = token_id in self.feed.tokens
                    _ec_startup = getattr(pos, "bond_entry_class", "")
                    if not _token_in_feed and (_ec_startup.startswith("WEATHER_") or _ec_startup == "SPORTS_COPY"):
                        # Sports + Weather tokens are never subscribed to the WS feed — that's
                        # expected. Their own strategy modules manage exits over REST polling.
                        logger.info(
                            "STARTUP: %s/%s is %s, not in WS feed — keeping position",
                            pos.asset, pos.direction.name,
                            getattr(pos, "bond_entry_class", ""),
                        )
                    elif not _token_in_feed:
                        # Shares confirmed on CLOB but token is no longer in the feed
                        # (window expired and was removed). The normal exit loop iterates
                        # self.feed.tokens only — it will never fire for this token.
                        # Force-sell immediately to recover the capital.
                        logger.warning(
                            "STARTUP: %s/%s has %.4f shares but token NOT in feed "
                            "(window expired?) — force-selling orphan",
                            pos.asset, pos.direction.name, balance,
                        )
                        self._exit_in_progress.add(token_id)
                        try:
                            ob = self.feed.get_order_book(token_id)
                            sell_price = ob.bids[0][0] if (ob and ob.bids) else 0.50
                            orphan_fills = await self.orders.cascade_sell(
                                token_id=token_id,
                                total_shares=balance,
                                current_price=sell_price,
                                reason="ORPHAN_SELL",
                                neg_risk=False,
                                tick_size="0.01",
                                force_exit=True,
                            )
                            sold = sum(f.total_size for f in orphan_fills)
                            avg_price = (
                                sum(f.avg_fill_price * f.total_size for f in orphan_fills) / sold
                                if sold > 0 else sell_price
                            )
                            if sold > 0:
                                logger.info(
                                    "STARTUP ORPHAN SOLD %s/%s: %.4f shares @ %.4f",
                                    pos.asset, pos.direction.name, sold, avg_price,
                                )
                                if not CONFIG.dry_run:
                                    _proceeds = round(sold * avg_price, 4)
                                    self.risk.bankroll.capital = round(
                                        self.risk.bankroll.capital + _proceeds, 4
                                    )
                                    self.risk.bankroll._save()
                                    logger.warning(
                                        "STARTUP ORPHAN PROCEEDS +$%.4f → cap=$%.2f",
                                        _proceeds, self.risk.bankroll.capital,
                                    )
                            else:
                                logger.warning(
                                    "STARTUP ORPHAN SELL FAILED %s/%s: %.4f shares unsold",
                                    pos.asset, pos.direction.name, balance,
                                )
                            self.risk.close_position(
                                token_id,
                                avg_price if sold > 0 else pos.entry_price,
                                "ORPHAN_SELL",
                            )
                            self._open_meta.pop(token_id, None)
                        except Exception as _oe:
                            logger.error(
                                "STARTUP ORPHAN SELL (tracked) failed for %s: %s",
                                token_id[:12], _oe,
                            )
                        finally:
                            self._exit_in_progress.discard(token_id)
                    else:
                        logger.info(
                            "STARTUP: %s/%s confirmed %.4f shares on CLOB — tracking continues",
                            pos.asset, pos.direction.name, balance,
                        )
            except Exception as _e:
                logger.error("STARTUP balance check failed for %s: %s", token_id[:12], _e)

        # Step 2: sell untracked orphan balances from previous sessions
        await self._window_end_balance_sweep(force_all=True)

        # Step 3: write recovery records for expired stage-1 positions.
        # These are positions where stage-1 sold 60% of shares but bot crashed before stage-2.
        # The window expired so we can't sell the remaining 40% — but we can log what we know.
        # stage1_sell_price was saved to disk by record_stage1_sell; remaining shares were
        # likely resolved on-chain. Record the stage-1 profit so WR/PnL stats are accurate.
        for r in self.risk._expired_stage1_positions:
            try:
                s1_price = r.get("stage1_sell_price", 0.0)
                entry = r["entry_price"]
                shares = r["shares"]
                remaining = r["remaining_shares"]
                s1_shares = round(shares - remaining, 4)
                if s1_price <= 0 or s1_shares <= 0:
                    logger.warning(
                        "RECOVERY SKIP %s/%s: missing stage-1 price (%.4f) or shares (%.4f) — "
                        "no stage1_sell_price saved (old version); skipping recovery record",
                        r["asset"], r["direction"], s1_price, s1_shares,
                    )
                    continue
                # Stage-1 was profitable (that's why it fired). Remaining 40% resolved on-chain.
                # Use entry_price as the conservative floor for remaining shares
                # (worst case: resolved at 0, they lost the 40% stake = entry * remaining).
                gross_s1 = s1_shares * (s1_price - entry)
                gross_remaining = remaining * (entry - entry)  # 0 — can't know resolution
                gross_pnl = round(gross_s1 + gross_remaining, 6)
                # Fee estimate: extreme odds for most SNIPER trades
                fee_rate = CONFIG.fees.extreme_fee_rate if entry < 0.30 or entry > 0.70 else CONFIG.fees.middle_fee_rate
                exit_notional = s1_price * s1_shares
                entry_notional = entry * shares
                fee_est = round((entry_notional + exit_notional) * fee_rate, 6)
                net_pnl = round(gross_pnl - fee_est, 6)
                now_ts = time.time()
                self.analytics._trade_counter += 1
                trade_id = f"T{self.analytics._trade_counter:05d}_{r['asset']}_{int(r['open_ts'])}_RECOVERED"
                self.analytics.last_trade_id = trade_id
                record = {
                    "trade_id": trade_id,
                    "token_id": r["token_id"],
                    "asset": r["asset"],
                    "direction": r["direction"],
                    "market_type": "updown",
                    "signal_source": "SNIPER",
                    "exit_reason": "STAGE1_RECOVERY",
                    "ts_open": r["open_ts"],
                    "ts_close": r.get("window_end_ts", now_ts),
                    "entry_price": entry,
                    "exit_price": s1_price,
                    "stake": r["stake"],
                    "shares": shares,
                    "gross_pnl": gross_pnl,
                    "fee_paid": fee_est,
                    "net_pnl": net_pnl,
                    "slippage_entry": 0.0,
                    "slippage_exit": 0.0,
                    "hold_seconds": round(r.get("window_end_ts", now_ts) - r["open_ts"], 1),
                    "hour_utc": int(time.gmtime(r["open_ts"]).tm_hour),
                    "window_size_s": r.get("window_size_s", 0),
                    "is_live": not CONFIG.dry_run,
                    "capital_before": self.risk.bankroll.capital - net_pnl,
                    "capital_after": self.risk.bankroll.capital,
                    "note": (
                        f"STAGE-1 RECOVERY: sold {s1_shares:.4f} of {shares:.4f} shares @ {s1_price:.4f}. "
                        f"Remaining {remaining:.4f} shares expired on-chain (resolution unknown). "
                        "Bot crashed between stage-1 and stage-2. PnL reflects stage-1 only."
                    ),
                }
                self.analytics._write_jsonl(CONFIG.trade_log, record)
                logger.warning(
                    "STAGE-1 RECOVERY %s/%s: stage-1 PnL=%.4f logged as %s "
                    "(remaining %.4f shares expired unlogged)",
                    r["asset"], r["direction"], net_pnl, trade_id, remaining,
                )
            except Exception as _e:
                logger.error("STAGE-1 RECOVERY failed for %s/%s: %s", r.get("asset"), r.get("direction"), _e)
        self.risk._expired_stage1_positions.clear()

        logger.info("STARTUP ORPHAN SWEEP: complete")

        # Second sweep at t+30s — catches tokens that weren't in self.feed.tokens
        # at the t+10s sweep because the feed loads asynchronously. Tokens for
        # windows that started recently often appear 15-25s after bot startup.
        asyncio.create_task(self._delayed_orphan_sweep())

    async def _delayed_orphan_sweep(self) -> None:
        """Second orphan sweep at t+30s after startup to catch late-loading tokens."""
        await asyncio.sleep(20.0)  # 10s (first sweep) + 20s = t+30s total
        logger.info("STARTUP ORPHAN SWEEP (delayed): scanning for late-loaded tokens...")
        await self._window_end_balance_sweep(force_all=True)
        logger.info("STARTUP ORPHAN SWEEP (delayed): complete")

    # ── 250s prewarm loop: refresh py_clob_client cache before 300s TTL expires ──

    async def _prewarm_loop(self) -> None:
        """Refresh neg_risk + fee_rate caches every 250s (TTL=300s in py_clob_client)."""
        while self._running:
            await asyncio.sleep(250)
            if not CONFIG.dry_run:
                self.orders.prewarm_token_caches(self.feed.tokens)

    # ── 30-min report loop ────────────────────────────────────────────────────

    async def _weather_backfill_loop(self) -> None:
        """Runs weather resolution backfill on startup (after 2 min) then every 4 h.

        Patches entered_correctly + kline_pnl + weather metadata for intraday
        exits and STARTUP_EXTERNALLY_SOLD orphans where the Polymarket market has
        since resolved.  Resolution exits (exit_price→1.0/0.0) are handled
        immediately at record_trade time via extra_fields; this loop covers the
        remaining cases.
        """
        await asyncio.sleep(120)   # let startup settle
        while self._running:
            try:
                from analytics.backfill_weather_resolution import run_backfill
                await asyncio.to_thread(run_backfill)
            except Exception as _wbf_e:
                logger.warning("weather backfill error: %s", _wbf_e)
            await asyncio.sleep(4 * 3600)

    async def _report_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1800)
            self.analytics.inject_telemetry(
                connectivity=self.feed.connectivity_stats(),
                order_latency=self.orders.latency_stats(),
            )
            report = self.analytics.generate_claude_report()
            # Append buy attempt stats to the report
            failed = self._buy_tried - self._buy_filled
            fail_rate = failed / self._buy_tried if self._buy_tried else 0
            buy_lines = [
                "",
                "BUY EXECUTION",
                f"  Attempted:  {self._buy_tried}",
                f"  Filled:     {self._buy_filled}",
                f"  Failed:     {failed}  ({fail_rate:.0%})",
            ]
            if self._buy_failed_reasons:
                buy_lines.append("  Failure reasons:")
                for reason, count in sorted(self._buy_failed_reasons.items(),
                                            key=lambda x: -x[1]):
                    buy_lines.append(f"    {count}× {reason}")
            logger.info("\n%s\n%s", report, "\n".join(buy_lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _classify_path(
    r30: Optional[float],
    r60: Optional[float],
    max_adv_pct: float,
    hold_s: float,
    exit_reason: str,
    exit_price: float,
    entry_price: float,
) -> tuple:
    """
    Classify post-entry price path into SMOOTH_RUNNER / EARLY_CHOP / DEAD_DRIFT.

    Diagnostic label only — no entry/exit logic uses this output.

    Returns (path_class: str, confidence: int 0-100, reason: str).
    """
    ep = entry_price
    xp = exit_price
    exit_pct = (xp - ep) / ep * 100 if ep > 0 else 0.0
    _tp_exit = exit_reason in ("BOND_TP_95", "BOND_TP_95_EXT", "BOND_TP_99", "SNIPER_TP", "TP_STAGE1", "TP_STAGE2", "BOND_EXHAUSTION_EXIT", "BOND_TRAIL_SL")
    _sl_exit = "SL" in exit_reason or "STOP" in exit_reason or "PRICE_SL" in exit_reason

    # ── SMOOTH_RUNNER ────────────────────────────────────────────────────────
    # Immediate follow-through, no significant adverse excursion, TP likely.
    smooth_score = 0
    smooth_reasons = []

    if r30 is not None and r30 >= 10:
        smooth_score += 35
        smooth_reasons.append(f"r30={r30:+.1f}%≥+10%")
    elif r30 is not None and r30 >= 5:
        smooth_score += 15
        smooth_reasons.append(f"r30={r30:+.1f}%")

    if max_adv_pct < 10:
        smooth_score += 20
        smooth_reasons.append(f"max_adv={max_adv_pct:.1f}%<10%")

    if _tp_exit and exit_pct >= 15:
        smooth_score += 30
        smooth_reasons.append(f"TP exit +{exit_pct:.1f}%")

    if r60 is not None and r60 >= 15:
        smooth_score += 15
        smooth_reasons.append(f"r60={r60:+.1f}%≥+15%")

    # ── EARLY_CHOP ───────────────────────────────────────────────────────────
    # Significant adverse dip but recovery — OB noise / wick-driven.
    chop_score = 0
    chop_reasons = []

    if max_adv_pct >= 15 and max_adv_pct <= 50:
        chop_score += 35
        chop_reasons.append(f"max_adv={max_adv_pct:.1f}% (15–50%)")

    if r30 is not None and -15 <= r30 < 5:
        chop_score += 20
        chop_reasons.append(f"r30={r30:+.1f}% (noise range)")

    if _sl_exit and exit_pct > -50:
        # SL fired but not catastrophic — could be dirty-path exit
        chop_score += 20
        chop_reasons.append(f"SL but moderate exit {exit_pct:.1f}%")
    elif _tp_exit and max_adv_pct >= 15:
        # TP but had adverse excursion first
        chop_score += 25
        chop_reasons.append(f"TP after {max_adv_pct:.1f}% dip")

    if r60 is not None and r30 is not None and r60 > r30 and r30 < 0:
        chop_score += 20
        chop_reasons.append(f"recovery r30={r30:+.1f}%→r60={r60:+.1f}%")

    # ── DEAD_DRIFT ───────────────────────────────────────────────────────────
    # No sustained directional movement; flat path with micro-reversals.
    drift_score = 0
    drift_reasons = []

    if r30 is not None and -10 <= r30 <= 8:
        drift_score += 30
        drift_reasons.append(f"r30={r30:+.1f}% (flat)")

    if r60 is not None and -10 <= r60 <= 8:
        drift_score += 20
        drift_reasons.append(f"r60={r60:+.1f}% (flat)")

    if max_adv_pct < 15 and not _tp_exit and exit_pct < 15:
        drift_score += 25
        drift_reasons.append("no expansion, no TP")

    if hold_s >= 60 and exit_pct < 10 and not _tp_exit:
        drift_score += 15
        drift_reasons.append(f"held {hold_s:.0f}s without direction")

    # ── Decision ─────────────────────────────────────────────────────────────
    if r30 is None and r60 is None:
        # Insufficient data (trade < 30s) — use exit outcome only
        if _tp_exit and exit_pct >= 15:
            return "SMOOTH_RUNNER", 50, f"short hold, TP +{exit_pct:.1f}% (no snaps)"
        elif _sl_exit:
            return "EARLY_CHOP", 40, f"short hold, SL {exit_pct:.1f}% (no snaps)"
        return "DEAD_DRIFT", 30, f"short hold {hold_s:.0f}s, no snaps"

    scores = {
        "SMOOTH_RUNNER": smooth_score,
        "EARLY_CHOP": chop_score,
        "DEAD_DRIFT": drift_score,
    }
    winner = max(scores, key=scores.__getitem__)
    conf = min(100, scores[winner])
    if winner == "SMOOTH_RUNNER":
        return winner, conf, "; ".join(smooth_reasons) or "smooth"
    elif winner == "EARLY_CHOP":
        return winner, conf, "; ".join(chop_reasons) or "chop"
    else:
        return winner, conf, "; ".join(drift_reasons) or "drift"


async def _main() -> None:
    bot = KlausBot()

    loop = asyncio.get_running_loop()

    def _shutdown(sig):
        logger.info("Shutdown signal %s received", sig)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, _shutdown, s)

    await bot.run()


if __name__ == "__main__":
    import atexit

    _PID_FILE = os.path.join(os.path.dirname(__file__), "logs", "bot.pid")

    # Refuse to start if another instance is already running.
    if os.path.exists(_PID_FILE):
        try:
            _existing_pid = int(open(_PID_FILE).read().strip())
            os.kill(_existing_pid, 0)          # signal 0 = existence check
            print(
                f"ERROR: bot already running as PID {_existing_pid}. "
                f"Kill it first: kill {_existing_pid}",
                file=sys.stderr,
            )
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # stale PID file — previous run didn't clean up

    with open(_PID_FILE, "w") as _f:
        _f.write(str(os.getpid()))

    @atexit.register
    def _remove_pid():
        try:
            os.unlink(_PID_FILE)
        except FileNotFoundError:
            pass

    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop event loop active — improved timer precision + I/O throughput")
    except ImportError:
        logger.info("uvloop not installed — using default asyncio event loop")
    asyncio.run(_main())
