"""
Sniper and momentum signal scanner.

Inactive when SNIPER_ENABLED=False and MOM_ENABLED=False (both currently False).
Called from KlausBot._scan_for_signals() via lazy import only when a flag is True.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, Set

if TYPE_CHECKING:
    from main import KlausBot

from config import CONFIG
from strategy.window_sniper import (
    SniperBlock,
    _session_min_delta,
    CONTRARIAN_MAX_ASK,
    CONTRARIAN_DELTA_ENABLED,
    SNIPER_ENABLED,
    MOM_ENABLED,
)
from strategy.momentum import Direction, calculate_tp_sl, TPSLLevels
from analytics.shadow_log import log_shadow_result
from analytics.lag_observations import log_lag_observation

logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Shadow monitor — counterfactual analysis for blocked sniper signals
# ---------------------------------------------------------------------------

async def _shadow_monitor(block: SniperBlock, feed,
                          active_set: set, dedup_key: tuple,
                          llm_boost: float = 0.0) -> None:
    """
    After the sniper blocks a candidate trade, watch the token's ask price at
    +30s, +60s, +120s, and at window close. Log what would have happened if
    we had entered at block.token_ask.

    This gives us the data to answer: "Are our blocks correct, or are we
    leaving profitable trades on the table?"

    Analysis: check logs/shadow_blocks.jsonl after 50+ blocks.
    """
    checkpoints = [30.0, 60.0, 120.0, 180.0]
    results: dict = {}
    start = time.time()
    time_remaining = block.window_end_ts - start

    if time_remaining <= 5:
        return  # window almost over — no useful data to collect

    for delay in checkpoints:
        target_ts = start + delay
        sleep_for = target_ts - time.time()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

        # Window expired before checkpoint — record None and stop
        if time.time() >= block.window_end_ts:
            break

        ob = feed.get_order_book(block.token_id)
        ask = ob.asks[0][0] if (ob and ob.asks) else None
        results[f"ask_at_{int(delay)}s"] = ask

    # Wait for window close to get final ask (resolution proxy).
    # Cap at 1200s (20 min) to cover 15m windows blocked early in the window.
    # Previous cap of 120s was too short — most blocks happen at 25-60% elapsed,
    # leaving 6-11 minutes until close which was silently skipped.
    window_close_wait = block.window_end_ts - time.time()
    if 0 < window_close_wait <= 1200:
        await asyncio.sleep(window_close_wait + 2.0)  # +2s settle
        ob = feed.get_order_book(block.token_id)
        ask_final = ob.asks[0][0] if (ob and ob.asks) else None
    else:
        ask_final = None

    log_shadow_result(
        block=block,
        ask_at_30s=results.get("ask_at_30s"),
        ask_at_60s=results.get("ask_at_60s"),
        ask_at_120s=results.get("ask_at_120s"),
        ask_at_180s=results.get("ask_at_180s"),
        ask_at_window_end=ask_final,
        llm_boost=llm_boost,
    )

    label = f"{block.asset}/{block.side} [{block.block_reason}]"
    max_ask = max((v for v in [
        results.get("ask_at_30s"), results.get("ask_at_60s"),
        results.get("ask_at_120s"), ask_final
    ] if v is not None), default=None)
    active_set.discard(dedup_key)  # allow future windows to register new monitors

    if max_ask is not None:
        pnl = (max_ask - block.token_ask) / block.token_ask
        would_win = max_ask >= block.token_ask * 1.20
        logger.info(
            "SHADOW %s | entry_ask=%.3f max_ask=%.3f pnl=%+.1f%% would_win=%s "
            "(lag=%.0f%% edge=%+.3f fv=%.3f)",
            label, block.token_ask, max_ask, pnl * 100, would_win,
            block.lag_remaining_pct * 100, block.edge, block.fair_value,
        )


# ---------------------------------------------------------------------------
# Signal scanner
# ---------------------------------------------------------------------------

async def scan_signals(bot: "KlausBot") -> None:
    # Periodic updown token count — fires every ~10s to confirm discovery health
    now_ts = time.time()
    if now_ts - getattr(bot, "_last_updown_log_ts", 0) > 10:
        bot._last_updown_log_ts = now_ts
        updown_tokens = [t for t in bot.feed.tokens.values() if t.market_type == "updown"]
        if updown_tokens:
            logger.info(
                "UPDOWN tokens in feed: %d | %s",
                len(updown_tokens),
                ", ".join(
                    f"{t.asset}/{t.side}/{t.window_seconds//60}m"
                    for t in updown_tokens[:8]
                ),
            )
        else:
            logger.warning(
                "UPDOWN MISSING: no updown tokens in feed (total=%d tokens) — "
                "discovery failed to find 5M/15M updown markets",
                len(bot.feed.tokens),
            )

    # Ext signals already fetched by _refresh_ext_signals() earlier this loop tick.
    ext_signals = dict(bot._last_ext_signals)

    # ── LLM Signal Engine: inject Claude signal into external signals ────────
    # Fires all day on sharp BTC moves (≥0.25% in active sessions, ≥0.40% quiet)
    # OR when VPIN > 0.65 (informed order flow detected on Binance aggTrade).
    btc_ext = ext_signals.get("BTC")
    btc_spot = btc_ext.spot_price if btc_ext else None
    btc_vpin = btc_ext.vpin_score if btc_ext else None
    btc_vpin_dir = btc_ext.vpin_direction if btc_ext else None
    try:
        macro_signal = await asyncio.wait_for(
            bot.macro_engine.tick(
                btc_spot, vpin_score=btc_vpin, vpin_direction=btc_vpin_dir,
                ext_signals=ext_signals,
            ),
            timeout=8.0,
        )
    except asyncio.TimeoutError:
        logger.warning("MacroEngine tick timeout (8s) — skipping LLM signal this cycle")
        macro_signal = None
    if macro_signal is None:
        macro_signal = bot.macro_engine.get_signal()  # use cached if still valid
    if macro_signal:
        # Inject signed boost into ALL asset ext signals
        # BTC moves propagate to ETH/SOL within 10–30s (correlated assets)
        for asset in CONFIG.markets.tracked_assets:
            ext = ext_signals.get(asset)
            if ext is not None:
                ext.macro_boost = macro_signal.boost_for_direction_yes()

    # Cache for OB scan loop (advise_exit needs VPIN without a separate fetch)
    bot._last_ext_signals = ext_signals

    # ── Cross-asset cascade: score all tokens, find lead signals ─────────
    # When a strong leader (BTC) fires, follower assets (ETH, SOL) get a
    # reduced effective min_score to catch the correlated wave.
    lead_assets: Set[str] = set()
    all_scores: Dict[str, float] = {}
    for token_id, token in bot.feed.tokens.items():
        ob = bot.feed.get_order_book(token_id)
        if ob is not None and ob.mid > 0 and (ob.mid < 0.05 or ob.mid > 0.95):
            continue  # near-resolved, skip
        bars_5m = bot.feed.get_bars_5m(token_id, n=30)
        bars_15m = bot.feed.get_bars_15m(token_id, n=30)
        if len(bars_5m) < 12:
            continue
        sig = bot.scorer.score(bars_5m, bars_15m, ob, ext_signals.get(token.asset))
        all_scores[token_id] = sig.composite
        if (sig.composite >= CONFIG.edge.cascade_trigger_score
                and token.asset in CONFIG.edge.cascade_assets):
            lead_assets.add(token.asset)

    # Build set of follower assets that get score discount this cycle
    discounted_assets: Set[str] = set()
    for leader in lead_assets:
        for follower in CONFIG.edge.cascade_assets.get(leader, []):
            discounted_assets.add(follower)
            logger.debug("CASCADE: %s lead → %s gets %.2f score discount",
                         leader, follower, CONFIG.edge.cascade_score_discount)

    # Volatile-hours gate removed — all UTC hours permitted.

    # ── Phase 1: scan all tokens, collect sniper candidates + run momentum ──
    # Sniper candidates are queued for a single LLM briefing call (not per-token).
    # Momentum (non-updown) tokens are evaluated and entered inline as before.
    sniper_queue: list = []  # [(token_id, token, signal, tpsl, decision, ext)]
    _queued_conditions: set = set()  # dedup: one entry per condition_id per scan cycle
    _updown_scanned = 0
    _updown_fired = 0

    for token_id, token in bot.feed.tokens.items():
        # Skip tokens already in open positions
        if token_id in bot.risk.open_positions:
            continue

        # Skip tokens whose asset is locked by a concurrent entry (spike or this loop).
        # evaluate() has this check too, but an early guard here avoids the full
        # scoring pipeline for tokens we can't trade anyway.
        if token.asset in bot.risk._pending_assets:
            continue
        if token.asset in bot._pending_asset_entries:
            continue

        # Skip tokens that are in the no-trade final window — saves scan noise
        # and avoids scoring dead markets (near-expiry prices are extreme/meaningless).
        if token.window_end_ts > 0:
            remaining_window = token.window_end_ts - time.time()
            if remaining_window < CONFIG.execution.no_trade_last_sec:
                continue

        ob = bot.feed.get_order_book(token_id)

        # Skip near-resolved tokens — they produce entry=0 and will never trade.
        # Check ask price directly (mid can be 0 when there are no bids, which
        # hides near-dead tokens from the mid-based filter).
        if ob is not None:
            _ask = ob.asks[0][0] if ob.asks else ob.mid
            if _ask < 0.05 or _ask > 0.95:
                continue
            # Target markets with no valid OB (ask=0) have no edge and no fills.
            # Skip them rather than wasting a scan cycle on entry=0.0000 noise.
            if token.market_type == "target" and _ask <= 0:
                continue
            # Target NO tokens structurally fail the min_no price gate every scan
            # when priced below 1 - max_entry_price. Skip before scoring to avoid
            # INFO log spam on entries that can never pass risk evaluation.
            if token.market_type == "target" and token.side.upper() == "NO":
                _min_no = 1.0 - bot.risk.edge_cfg.max_entry_price
                if _ask < _min_no:
                    logger.debug(
                        "SCAN SKIP %s/%s: NO ask=%.4f < min_no=%.4f (structural)",
                        token.asset, token.side, _ask, _min_no,
                    )
                    continue

        bars_5m = bot.feed.get_bars_5m(token_id, n=30)
        bars_15m = bot.feed.get_bars_15m(token_id, n=30)
        ext = ext_signals.get(token.asset)

        # ── Window Sniper: primary signal for updown markets ─────────────
        # Detects mid-window mispriced certainty (fair value vs token ask).
        # Fires when: 35–80% elapsed, asset moved >0.20% (active) / >0.35% (quiet), edge ≥ 0.02–0.04.
        # SniperSignal is compatible with risk manager (same fields: composite,
        # confidence, entry_price, direction, fee_zone, reason).
        sniper_sig = None
        if (token.market_type == "updown"
                and token.asset not in CONFIG.edge.sniper_excluded_assets):
            _updown_scanned += 1
            sniper_sig = bot.sniper.score(token, ob, ext, now=time.time())

        # ── Velocity gate: skip if Binance momentum is against trade direction ──
        # NO trade requires price still falling (vel < 0); YES requires rising (vel > 0).
        # Flat/cold (|vel| ≤ 0.001%) allowed through — no data is not a bad signal.
        # Live data: vel against direction → 0W/4L on SNI NO trades.
        if sniper_sig is not None:
            _vel_now, _ = bot.feed.get_velocity_5s(token.asset)
            _VEL_THRESHOLD = 0.001   # % — dead zone for flat/no-data
            _vel_against = (
                (token.side == "NO"  and _vel_now >  _VEL_THRESHOLD) or
                (token.side == "YES" and _vel_now < -_VEL_THRESHOLD)
            )
            if _vel_against:
                logger.info(
                    "SNIPER VELOCITY_GATE %s/%s | vel=%+.4f%% against direction — skip",
                    token.asset, token.side, _vel_now,
                )
                sniper_sig = None

        if sniper_sig is not None:
            _updown_fired += 1
            # Log the sniper detection here; briefing decision logged after the call
            _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
            logger.info(
                "SCAN [SNIPER] %s/%s [%s] | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
                token.asset, token.side, _wlabel,
                sniper_sig.composite, sniper_sig.confidence,
                sniper_sig.entry_price, sniper_sig.direction.name,
                sniper_sig.reason or "no signal",
            )

            if token.market_type == "updown" and ext is not None:
                log_lag_observation(
                    ts=time.time(), asset=token.asset, token_id=token_id,
                    side=token.side, market_type=token.market_type,
                    window_end_ts=token.window_end_ts,
                    polymarket_price=sniper_sig.entry_price,
                    binance_spot_price=ext.spot_price,
                    binance_1m_pct=ext.spot_momentum_1m,
                    binance_5m_pct=ext.spot_momentum_5m,
                    binance_15m_pct=ext.spot_momentum_15m,
                )

            if sniper_sig.entry_price <= 0:
                logger.warning("SKIP %s/%s — zero entry price", token.asset, token.side)
                continue

            tpsl = calculate_tp_sl(sniper_sig.entry_price, sniper_sig.direction, bars_5m, ob)
            decision = bot.risk.evaluate(
                token_id, sniper_sig, tpsl,
                condition_id=token.condition_id,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=0.0,
                is_sniper=True,
                window_seconds=getattr(token, "window_seconds", 0),
            )

            if not decision.approved:
                logger.info("  └─ REJECTED: %s", decision.reason)
            else:
                _cid = token.condition_id or ""
                if _cid and _cid in _queued_conditions:
                    logger.info("  └─ SKIP %s/%s — condition already queued this cycle", token.asset, token.side)
                else:
                    sniper_queue.append((token_id, token, sniper_sig, tpsl, decision, ext))
                    if _cid:
                        _queued_conditions.add(_cid)
            continue  # updown token handled — skip momentum path

        elif token.market_type == "updown" and CONTRARIAN_DELTA_ENABLED:
            # ── Delta contrarian: small Binance move → buy opposite direction ──
            # Fires when abs(delta) in [0.05%, 0.06%] and this token is OPPOSITE
            # to the Binance direction. Hypothesis: small moves reverse before PM reprices.
            # Half stake (qs=0). No lag/edge gates.
            if token.asset not in CONFIG.edge.sniper_excluded_assets:
                _dc_sig = bot.sniper.score_delta_contrarian(token, ob, ext, now=time.time())
                if _dc_sig is not None:
                    _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
                    logger.info(
                        "SCAN [DELTA_CONTRARIAN] %s/%s [%s] | entry=%.4f delta=%+.3f%% elapsed=%.0f%%",
                        token.asset, token.side, _wlabel,
                        _dc_sig.entry_price, _dc_sig.delta_pct, _dc_sig.elapsed_pct * 100,
                    )
                    _dc_tpsl = calculate_tp_sl(_dc_sig.entry_price, _dc_sig.direction, bars_5m, ob)
                    _dc_decision = bot.risk.evaluate(
                        token_id, _dc_sig, _dc_tpsl,
                        condition_id=token.condition_id,
                        window_end_ts=token.window_end_ts,
                        asset=token.asset,
                        market_type=token.market_type,
                        cascade_discount=0.0,
                        is_sniper=True,
                        window_seconds=getattr(token, "window_seconds", 0),
                    )
                    if _dc_decision.approved:
                        _dc_decision.stake = max(1.0, round(_dc_decision.stake / 2, 2))
                        _cid = token.condition_id or ""
                        if _cid and _cid in _queued_conditions:
                            logger.info("  └─ DELTA_CONTRARIAN SKIP %s/%s — condition already queued", token.asset, token.side)
                        else:
                            sniper_queue.append((token_id, token, _dc_sig, _dc_tpsl, _dc_decision, ext))
                            if _cid:
                                _queued_conditions.add(_cid)
                    else:
                        logger.info("  └─ DELTA_CONTRARIAN REJECTED: %s", _dc_decision.reason)

        if token.market_type == "updown":
            # ── Contrarian check: buy cheap side when opponent is ≥0.90 early ──
            # When the opposite token is at ≥0.90 in the first 40% of the window,
            # the cheap side (~0.10) may offer mean-reversion value.
            # Normal sniper skips this token (ask < MIN_TOKEN_ASK=0.35 or wrong side).
            # This path catches the contrarian opportunity independently.
            if (ob is not None and ob.asks
                    and ob.asks[0][0] <= CONTRARIAN_MAX_ASK
                    and token.asset not in CONFIG.edge.sniper_excluded_assets):
                # Find the paired opposite token for this window
                _opponent_ask = 0.0
                for _tid, _t in bot.feed.tokens.items():
                    if (_t.asset == token.asset
                            and _t.side != token.side
                            and abs(_t.window_end_ts - token.window_end_ts) < 5):
                        _opp_ob = bot.feed.get_order_book(_tid)
                        if _opp_ob and _opp_ob.asks:
                            _opponent_ask = _opp_ob.asks[0][0]
                        break
                if _opponent_ask > 0:
                    _cntr_sig = bot.sniper.score_contrarian(token, ob, _opponent_ask, ext, now=time.time())
                    if _cntr_sig is not None:
                        _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
                        logger.info(
                            "SCAN [CONTRARIAN] %s/%s [%s] | entry=%.4f opponent=%.3f elapsed=%.0f%%",
                            token.asset, token.side, _wlabel,
                            _cntr_sig.entry_price, _opponent_ask, _cntr_sig.elapsed_pct * 100,
                        )
                        # Custom TP/SL: fixed percentages sized for low-price reversal plays.
                        # TP=+150% (buy 0.10, target 0.25), SL=−50% (0.10→0.05). RR=3:1.
                        # Break-even WR=25%. Normal calculate_tp_sl uses ATR which is
                        # tiny for a 0.10 token → would produce useless tight targets.
                        _ep = _cntr_sig.entry_price
                        _cntr_tpsl = TPSLLevels(
                            take_profit=round(min(0.98, _ep * 2.5), 4),
                            stop_loss=round(max(0.01, _ep * 0.50), 4),
                            tp_pct=150.0,
                            sl_pct=50.0,
                            risk_reward=3.0,
                        )
                        _cntr_decision = bot.risk.evaluate(
                            token_id, _cntr_sig, _cntr_tpsl,
                            condition_id=token.condition_id,
                            window_end_ts=token.window_end_ts,
                            asset=token.asset,
                            market_type=token.market_type,
                            cascade_discount=0.0,
                            is_sniper=True,
                            window_seconds=getattr(token, "window_seconds", 0),
                        )
                        if _cntr_decision.approved:
                            _ccid = token.condition_id or ""
                            if _ccid and _ccid in _queued_conditions:
                                logger.info("  └─ CONTRARIAN SKIP %s/%s — condition already queued", token.asset, token.side)
                            else:
                                # Half stake: contrarian is speculative — $10 base → $5 per contrarian trade
                                _cntr_decision.stake = max(1.0, round(_cntr_decision.stake / 2, 2))
                                sniper_queue.append(
                                    (token_id, token, _cntr_sig, _cntr_tpsl, _cntr_decision, ext)
                                )
                                if _ccid:
                                    _queued_conditions.add(_ccid)
                        else:
                            logger.info("  └─ CONTRARIAN REJECTED: %s", _cntr_decision.reason)

            # Sniper didn't fire on this updown token → skip entirely.
            # Momentum scorer on updown markets has confirmed ZERO edge:
            # 19 live trades, WR=36.8%, losses score HIGHER than wins (0.531 vs 0.511).
            # Breakout and trend signals are anti-predictive on updown markets.
            # Only the Window Sniper (fair-value model) is allowed to enter updown.
            if ob is not None:
                logger.debug(
                    "UPDOWN SKIP %s/%s | sniper=None ask=%.3f | "
                    "window_end=%s window=%ds",
                    token.asset, token.side,
                    ob.asks[0][0] if ob.asks else 0,
                    token.window_end_ts, token.window_seconds,
                )
            # Shadow monitor: spawn once per (token_id, window_end_ts) —
            # not every scan cycle. The sniper repopulates last_block every
            # 0.2s; dedup via _shadow_active prevents duplicate tasks.
            block = bot.sniper.last_block.pop((token.asset, token.side), None)
            if block is not None and block.token_id == token_id:
                dedup_key = (block.token_id, block.window_end_ts)
                if dedup_key not in bot._shadow_active:
                    bot._shadow_active.add(dedup_key)
                    _macro_sig = bot.macro_engine.get_signal()
                    _llm_boost = _macro_sig.boost_for_direction_yes() if _macro_sig else 0.0
                    asyncio.create_task(
                        _shadow_monitor(block, bot.feed, bot._shadow_active, dedup_key,
                                        llm_boost=_llm_boost),
                        name=f"shadow_{token.asset}_{token.side}",
                    )
            continue
        else:
            # Non-updown (price-target markets): use momentum scorer
            # Re-enabled 2026-04-18 at 0.5× stake for data collection.
            if not MOM_ENABLED:
                continue

            # Skip long-dated target markets (e.g. "Will BTC hit $150k by Dec 31?").
            # MOM has no edge on markets that resolve months away — their price
            # reflects long-term probability, not 5-min momentum. The HARD_EXIT
            # at 180s caps individual loss but bleeds fees. Only enter if resolution
            # is within 24 hours.
            if token.window_end_ts > 0 and (token.window_end_ts - time.time()) > 86_400:
                continue

            if len(bars_5m) < 12:
                continue  # not enough bar history yet

            signal = bot.scorer.score(bars_5m, bars_15m, ob, ext)
            signal_source = "MOMENTUM"

            # For NO tokens: scorer labels uptrend as BUY_YES (rising token price).
            # Flip so direction reflects the actual trade: rising NO = BUY_NO.
            if token.side == "NO" and signal.direction != Direction.NO_TRADE:
                signal.direction = (
                    Direction.BUY_NO
                    if signal.direction == Direction.BUY_YES
                    else Direction.BUY_YES
                )

        # Only log NO_TRADE at DEBUG — SCAN cycle summary covers the quiet state.
        # Log at INFO when something actionable is happening (score > 0 with direction).
        _log_fn = logger.debug if signal.direction == Direction.NO_TRADE else logger.info
        _mtype = (f"{token.window_seconds//60}m" if token.market_type == "updown" and token.window_seconds
                  else token.market_type)
        _log_fn(
            "SCAN [%s] %s/%s [%s] | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
            signal_source,
            token.asset, token.side, _mtype,
            signal.composite, signal.confidence,
            signal.entry_price, signal.direction.name,
            signal.reason or "no signal",
        )

        if signal.direction == Direction.NO_TRADE:
            continue

        # Lag research: record Binance price + Polymarket price every scan.
        # No trading logic affected. Used by analytics/lag_analysis.py.
        # (Updown lag logging happens in the sniper path above.)
        if ext is not None:
            log_lag_observation(
                ts=time.time(),
                asset=token.asset,
                token_id=token_id,
                side=token.side,
                market_type=token.market_type,
                window_end_ts=token.window_end_ts,
                polymarket_price=signal.entry_price,
                binance_spot_price=ext.spot_price,
                binance_1m_pct=ext.spot_momentum_1m,
                binance_5m_pct=ext.spot_momentum_5m,
                binance_15m_pct=ext.spot_momentum_15m,
            )

        # Route YES tokens to BUY_YES trades, NO tokens to BUY_NO trades.
        # Momentum path: NO token with BUY_YES after flip → redirect to YES counterpart.
        if token.side == "YES" and signal.direction == Direction.BUY_NO:
            continue
        if token.side == "NO" and signal.direction == Direction.BUY_YES:
            yes_token_id = next(
                (tid for tid, t in bot.feed.tokens.items()
                 if t.condition_id and t.condition_id == token.condition_id
                 and t.side == "YES" and tid not in bot.risk.open_positions),
                None,
            )
            if not yes_token_id:
                continue  # no YES counterpart available
            # Redirect: trade YES token at the mirror price (1 - no_price)
            token_id = yes_token_id
            token = bot.feed.tokens[yes_token_id]
            signal.entry_price = round(1.0 - signal.entry_price, 4)
            logger.info(
                "  └─ REDIRECT NO→YES: using %s YES token @ %.4f (NO was %.4f)",
                token.asset, signal.entry_price, 1.0 - signal.entry_price,
            )

        if signal.entry_price <= 0:
            logger.warning("SKIP %s/%s — zero entry price (bad feed data)", token.asset, token.side)
            continue

        tpsl = calculate_tp_sl(signal.entry_price, signal.direction, bars_5m, ob)
        decision = bot.risk.evaluate(
            token_id, signal, tpsl,
            condition_id=token.condition_id,
            window_end_ts=token.window_end_ts,
            asset=token.asset,
            market_type=token.market_type,
            cascade_discount=CONFIG.edge.cascade_score_discount
                if token.asset in discounted_assets else 0.0,
            window_seconds=getattr(token, "window_seconds", 0),
        )

        if not decision.approved:
            logger.info("  └─ REJECTED: %s", decision.reason)
            continue

        # MOMENTUM: trade at 0.5× size while the strategy is re-validating
        if signal_source == "MOMENTUM":
            _orig_stake = decision.stake
            decision.stake = max(1.0, round(_orig_stake * 0.50, 2))
            logger.info(
                "  └─ MOMENTUM stake reduction %s: $%.2f → $%.2f (0.5×)",
                token.asset, _orig_stake, decision.stake,
            )

        cascade_tag = " [CASCADE]" if token.asset in discounted_assets else ""
        logger.info(
            "  └─ SIGNAL%s %s | %s %s | entry=%.4f conf=%.2f score=%.2f | %s",
            cascade_tag, token.asset, signal.direction.name, signal.fee_zone.name,
            signal.entry_price, signal.confidence, signal.composite,
            signal.reason,
        )
        await bot._enter_position(token_id, token.asset, signal, tpsl, decision)

    # ── Scan cycle summary ─────────────────────────────────────────────────
    # Show asset deltas so user can see why sniper is/isn't firing
    _delta_parts = []
    for _a in CONFIG.markets.tracked_assets:
        _ext = ext_signals.get(_a)
        if _ext and _ext.spot_price:
            _parts = []
            if _ext.spot_window_open_5m:
                _d5 = (_ext.spot_price - _ext.spot_window_open_5m) / _ext.spot_window_open_5m * 100
                _parts.append(f"5m={_d5:+.3f}%")
            if _ext.spot_window_open_15m:
                _d15 = (_ext.spot_price - _ext.spot_window_open_15m) / _ext.spot_window_open_15m * 100
                _parts.append(f"15m={_d15:+.3f}%")
            if _parts:
                _delta_parts.append(f"{_a}[{' '.join(_parts)}]")
    _thr_5m = _session_min_delta(is_15m=False)
    _thr_15m = _session_min_delta(is_15m=True)
    _threshold_str = f"5m≥{_thr_5m:.2f}% / 15m≥{_thr_15m:.2f}%"
    _status = "SNIPER WAITING" if _updown_fired == 0 else f"SNIPER FIRED={_updown_fired}"
    logger.info(
        "[SNIPER] %s | %d updown scanned | deltas: %s | need %s",
        _status, _updown_scanned,
        " ".join(_delta_parts) if _delta_parts else "no Binance data",
        _threshold_str,
    )

    # ── Phase 2: LLM briefing for all sniper candidates ───────────────────
    # ONE call with ALL candidates → Claude sees portfolio context, ranks by quality.
    # Much more powerful than per-token calls: can avoid correlated duplicates,
    # can deprioritize weak edges when capital is limited.
    if sniper_queue:
        briefing_candidates = [
            {
                "token_id": tid,
                "asset": tok.asset,
                "side": tok.side,
                "delta_pct": sig.delta_pct,
                "fair_value": sig.fair_value,
                "token_ask": sig.token_ask,
                "edge": sig.edge,
                "lag_remaining_pct": sig.lag_remaining_pct,
                "elapsed_pct": sig.elapsed_pct,
                "window_seconds": tok.window_seconds,
                "vpin_score": (ex.vpin_score if ex else None),
                "vpin_direction": (ex.vpin_direction if ex else None),
            }
            for tid, tok, sig, tpsl, dec, ex in sniper_queue
        ]
        # Briefing disabled: LLM veto never fires (always overridden), adds 1-2s
        # latency before order placement, kills fills on fast-moving tokens.
        briefing = {}

        # Sort by LLM priority (lower = better), then enter
        sniper_queue.sort(key=lambda x: briefing.get(x[0], {}).get("priority", 99))

        for token_id, token, signal, tpsl, decision, ext in sniper_queue:
            # Re-check: another iteration may have filled max positions
            if token_id in bot.risk.open_positions:
                continue

            b = briefing.get(token_id, {})
            llm_decision = b.get("decision", "ENTER")
            llm_conf = b.get("confidence", 0.5)
            llm_reason = b.get("reason", "")

            # LLM veto DISABLED — track recommendation vs outcome instead.
            # Log what the LLM would have done so we can validate its accuracy later.
            if llm_decision == "SKIP":
                logger.info(
                    "  └─ LLM WOULD-VETO %s/%s (conf=%.2f) — entering anyway for data: %s",
                    token.asset, token.side, llm_conf, llm_reason,
                )

            if not SNIPER_ENABLED:
                logger.info(
                    "  └─ SNIPER GATED (SNIPER_ENABLED=False) %s/%s — skipping entry",
                    token.asset, token.side,
                )
                continue
            logger.info(
                "  └─ SNIPER ENTER %s/%s [p=%d conf=%.2f] | entry=%.4f edge=%.3f | %s",
                token.asset, token.side,
                b.get("priority", 99), llm_conf,
                signal.entry_price, signal.edge,
                llm_reason or signal.reason,
            )
            await bot._enter_position(token_id, token.asset, signal, tpsl, decision,
                                      llm_rec=llm_decision, llm_rec_conf=llm_conf)

    # ── Bond scan moved to _signal_loop — runs independently of sniper ──────
    # (removed from here so sniper's early return doesn't block BOND)
