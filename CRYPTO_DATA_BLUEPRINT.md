# CRYPTO DATA BLUEPRINT — what we have accumulated (for designing a new strategy)

Scope: BTC / ETH / SOL on Polymarket up/down markets (5-min = `window_size_s 300`, 15-min = `900`),
signal-sourced from Binance futures + Coinbase. Two collection eras with different schema fidelity.
All paths under `/root/Klaus/`. Generated from on-disk audit 2026-06-05.

================================================================================
## 0. THE TWO ERAS (read first)
================================================================================
- LEGACY  (Apr 14 → ~May 25): top-level `logs/*.jsonl`. Lower fidelity, ~1s ticks, flat schemas.
- TIER-1   (May 26 → Jun 5):   `logs/shadow/hot/<date>/*.jsonl`. `schema_version:2`, ms-stamped,
                                exchange timestamps, full L2 book, regime tags. THIS IS THE GOLD.
- LIVE TRADES (real fills): Apr 14 → May 21 only (`logs/trades.jsonl`). No live crypto fills after.
- The two eras DO NOT share a schema → a normalization/join layer is needed to span them.

Universal join keys: `token_id`, `condition_id`, `window_end_ts`, `asset`, time (`ts_s`/`ts`).

================================================================================
## 1. UPSTREAM LIVE FEEDS (data/feeds.py)
================================================================================
Binance Futures  wss://fstream.binance.com/ws
  - aggTrade   → tick trades (price, qty, taker side)         [→ binance_trade]
  - kline      → 5m + 15m OHLC, window-open prices            [→ window_resolution]
  - forceOrder → liquidations $long/$short (60s)              [→ trades.liq_*]
  - funding    → annualised perp funding APR                  [→ trades.funding_rate_pct]
  - derived    → VPIN / order-flow toxicity                   [→ vpin_score]
Coinbase spot poll → cross-exchange divergence                [→ cross_exchange_div_pct]
Polymarket CLOB  wss://ws-subscriptions-clob.polymarket.com   → full L2 order book [→ ob_delta]
Polymarket RTDS  wss://ws-live-data.polymarket.com            → last-trade prints  [→ token_trade]
Polymarket Gamma REST → market metadata / resolution / creation events

================================================================================
## 2. FEATURE STREAMS (model inputs)
================================================================================

### 2a. market_timeline   [TIER-1, ~10.1M recs, 13.6GB]  ★ primary feature panel
logs/shadow/hot/<date>/market_timeline.jsonl
Per-token time-evolving state. Fields:
  schema_version, record_type, ts_s, ts_ms_local, token_id, condition_id, asset,
  outcome_dir, outcome_side, window_end_ts, window_size_s, seconds_to_resolution,
  weekday, hour_utc, minute_utc, session_bucket,
  best_bid, best_ask, mid, spread_abs, spread_bps,
  ob_top1_bid_size, ob_top1_ask_size, ob_imb_top3, ob_book_depth_size,
  ob_levels_bid, ob_levels_ask, ob_quote_age_ms,
  tok_snap_30s, tok_snap_60s, tok_history_seconds,
  binance_spot, binance_vel_5s_pct, binance_ret_30s_pct, binance_ret_60s_pct,
  binance_ret_1m_pct, binance_ret_5m_pct, binance_ret_15m_pct, binance_ret_60m_pct,
  peer_token_id, peer_bid, peer_ask, peer_age_ms, arb_sum_yes_no,
  vol_regime, trend_regime, liquidity_regime, macro_event_window,
  vpin_score, tok_delta_5s, tok_decel_ratio, ask_stale_s

### 2b. binance_trade   [TIER-1, ~26.1M recs, 5.6GB]  ★ raw tick tape
  schema_version, record_type, ts_s, ts_ms_local, exchange_ts_ms, asset,
  price, qty, is_buyer_maker, taker_side

### 2c. ob_delta   [TIER-1, ~7.9M recs, 5.3GB]  ★ full L2 order-book event stream
  ...token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts,
  seconds_to_resolution, event_type, level_price, level_size, level_side, level_hash,
  level_rank, best_bid_at_event, best_ask_at_event, ask_top3, bid_top3

### 2d. token_trade   [TIER-1, ~2.0M recs, 1.1GB]  Polymarket executed prints
  ...price, size, side, transaction_hash, fee_rate_bps, seconds_to_resolution

### 2e. LEGACY feature streams (Apr 14 → May 25)
market_ticks.jsonl    [~6.3M] ts, token_id, asset, side, market_type, price, score,
                              confidence, direction, breakout, trend, volume, ob_imb, hour_utc
lag_ws_events.jsonl   [~18.3M] ts, src(binance|poly_ask|poly_snap), asset, outcome, token_id, ask
lag_observations.jsonl[49,182] ts, asset, token_id, side, market_type, window_end_ts, remaining_s,
                              polymarket_price, binance_spot, binance_1m_pct, _5m_pct, _15m_pct
volarb_microshadow.jsonl       ts_s, token_id, asset, ask, mid, model_p, edge, ob_quote_age_ms,
                              binance_ret_15m_pct, spread_bps, arb_sum_yes_no, *_regime, ob_*, r1/r3_pass

================================================================================
## 3. LABEL / OUTCOME STREAMS (supervised targets)
================================================================================

### 3a. window_resolution   [TIER-1, 12,018 labeled windows]  ★ THE CLEAN LABEL SET
logs/shadow/hot/<date>/window_resolution.jsonl
  ts_resolved_s, condition_id, asset, outcome_dir, window_end_ts, window_size_s,
  binance_open_5m, binance_close_5m, binance_high_5m, binance_low_5m,
  realized_move_pct, moved_up, resolved_yes, resolution_method,
  resolution_delay_s, resolution_source
Coverage (balanced classes):
  BTC 5m n=3004 (48% up) | BTC 15m n=1002 (46%)
  ETH 5m n=3004 (48% up) | ETH 15m n=1002 (47%)
  SOL 5m n=3004 (51% up) | SOL 15m n=1002 (48%)
  → 9,012 × 5-min  +  3,006 × 15-min

### 3b. window_final_prices.jsonl [LEGACY]  token_id, asset, side, window_end_ts,
                                            entry_ask, final_price, recorded_at

================================================================================
## 4. EXECUTION-REALISM / HOLD-PATH STREAMS (for backtest fidelity)
================================================================================
hold_path.jsonl        [TIER-1 ~1.16M] counterfactual price path after a hypothetical fire:
  fire_ask, fire_ts_s, fire_sec_to_res, seconds_held, bid, ask, mid, spread_abs,
  pnl_pct, mae, mfe, bid_velocity_1s, ob_imb_top3, ob_book_depth_size,
  ob_depth_delta_1s, ob_quote_age_ms, binance_spot, binance_ret_5m_pct, *_regime
gate_trace.jsonl       [TIER-1 ~10.1M] every entry-gate eval: ask, gate_results,
  all_pass, first_failed_gate, strategy_version, would_take_at_ask
order_lifecycle.jsonl  [TIER-1] event, order_id, side, intended_price/size,
  realized_price/size, latency_ms, cf_attempts   (REAL fill latency & slippage)
exit_policy_shadow.jsonl[TIER-1] policy_id, exit_trigger, clean_pnl_pct,
  realistic_pnl_pct, fill_ok, hold_seconds, snap30, snap60, bnc_5m_pct
discover_signal.jsonl  [TIER-1] passive DISCOVER signal log (ask/bid/peer/arb_sum)
LEGACY: exit_shadow.jsonl, snap_shadow.jsonl, post_exit.jsonl, traj_snaps.jsonl, wick_events.jsonl

================================================================================
## 5. LIVE TRADES — REAL CAPITAL  [logs/trades.jsonl]
================================================================================
6,073 crypto trades, Apr 14 → May 21.  Split: 5m≈5,907 / 15m≈166 / older≈349.
Strategy tags: TERMINAL 2708, LDA 1081, VOLARB 887, BOND 446, CAS_LOWASK 178, SNIPER 154, MOMENTUM 43.
~90 fields incl. real PnL + every entry feature snapshot:
  trade_id, token_id, asset, direction, market_type, ts_open, ts_close, entry_price, exit_price,
  stake, shares, gross_pnl, fee_paid, net_pnl, slippage_entry, slippage_exit, exit_reason,
  signal_source, breakout_score, trend_score, volume_score, ob_score, intrawindow_score,
  composite_score, confidence, fee_zone, external_boost, atr_percentile, atr_current, hurst,
  sniper_delta_pct, sniper_fair_value, sniper_edge, sniper_vpin, sniper_llm_boost,
  sniper_pm_ask_at_trigger, sniper_pm_drift_at_entry, sniper_lag_remaining, quality_score, regime,
  binance_price_at_entry, binance_reversal_count_at_exit, window_size_s, hour_utc, hold_seconds,
  spot_at_entry, spot_at_exit, signal_to_fill_ms, ob_depth_at_entry, pre_entry_momentum_pct,
  max_price_seen, min_price_seen, max_favourable_pct, max_adverse_pct, t_fav_s, t_adv_s,
  window_outcome_price, entered_correctly, llm_rec, llm_rec_conf, heat_check_active,
  consecutive_wins_at_entry, capital_before, capital_after, is_live, cond_wr, cond_n,
  liq_long_60s, liq_short_60s, funding_rate_pct, coinbase_price, cross_exchange_div_pct,
  velocity_5s_pct, move_age_s
(6 historical backups: logs/trades.jsonl.bak* for pre/post-fix comparison.)

================================================================================
## 6. VOLUME SUMMARY (crypto only)
================================================================================
  binance_trade        ~26,100,000   tick tape
  lag_ws_events        ~18,300,000   raw WS (binance+poly)
  market_timeline      ~10,100,000   feature panel
  gate_trace           ~10,100,000   gate evals
  ob_delta              ~7,900,000   L2 book deltas
  market_ticks          ~6,300,000   legacy ticks
  token_trade           ~2,000,000   poly prints
  hold_path             ~1,160,000   hold paths
  window_resolution         12,018   ★ labels (5m+15m)
  trades (live fills)        6,073   ★ real PnL
  ----------------------------------------------------
  CRYPTO TOTAL          ~82,000,000 records

================================================================================
## 7. KNOWN GAPS / CAVEATS
================================================================================
- Rich Tier-1 features (market_timeline/ob_delta) exist ONLY May 26→Jun 5 (11 days).
- Real live fills exist ONLY Apr 14→May 21, under the OLD schema → labels-with-fills and
  rich-features barely overlap in time. window_resolution is the bridge (synthetic labels for the
  feature era; use trades.jsonl for fill/slippage realism).
- 5m has ~3x the labels of 15m; 15m live-trade n is too small (166) to fit alone.
- Funding/liq/VPIN/coinbase live only as point snapshots inside trades.jsonl (not continuous series).
- Classes are balanced ~48-51% up → near-coinflip base rate; edge must come from features, not prior.
