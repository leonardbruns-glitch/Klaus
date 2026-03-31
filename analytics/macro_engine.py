"""
Klaus — LLM Signal Engine

Uses Claude AI to interpret sharp BTC price moves and VPIN order flow spikes,
generating directional trading signals for Polymarket updown markets all day.

Edge thesis:
  - Any time BTC moves sharply (≥ trigger threshold), Polymarket tokens lag
    spot by 30–120 seconds before repricing
  - Claude interprets whether the move is likely to sustain or fade
  - VPIN > 0.65 from Binance aggTrade = informed order flow = additional trigger

Trigger thresholds by session (UTC):
  - High-activity sessions (08:00, 13:30, 23:00): 0.25% BTC move
  - All other hours: 0.40% BTC move
  These windows cover London open, NYSE open/macro data, and Asia open.

Cooldown: 3 minutes between LLM calls (prevents spam, ~$0.001/call with Haiku).
Signal validity: 120 seconds (the Polymarket repricing lag window).

Max cost: ~30 calls/day in active market = ~$0.03/day. Negligible.

Setup: set ANTHROPIC_API_KEY in .env to enable.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("macro_engine")

# ── Trigger thresholds by session ─────────────────────────────────────────────
# High-volume session hours UTC: London open, NYSE open/macro, Asia open
_HIGH_VOLUME_HOURS = {8, 9, 13, 14, 15, 22, 23, 0}
_TRIGGER_PCT_HIGH = 0.25    # 0.25% move during high-volume sessions
_TRIGGER_PCT_LOW  = 0.40    # 0.40% move during quiet hours

# ── Signal parameters ─────────────────────────────────────────────────────────
SIGNAL_VALID_SECONDS = 120   # signal lasts 2 minutes
COOLDOWN_SECONDS = 180       # 3 min between LLM calls
PRICE_BASELINE_RESET_S = 90  # reset price reference every 90s if no trigger

# ── VPIN trigger ──────────────────────────────────────────────────────────────
VPIN_TRIGGER_THRESHOLD = 0.65  # VPIN above this = informed flow, also query LLM


@dataclass
class MacroSignal:
    """
    Directional signal from LLM interpretation of BTC price/flow data.
    direction: +1 = bullish (buy YES/UP token), -1 = bearish (buy NO/DOWN token)
    confidence: 0.5–0.95 (Claude's estimated probability the move sustains)
    """
    ts: float
    direction: int               # +1 = bullish, -1 = bearish
    confidence: float            # 0.5–0.95
    trigger_pct: float           # BTC % move that triggered this (0 = VPIN trigger)
    reasoning: str               # Claude's one-sentence explanation
    trigger_type: str = "price"  # "price" or "vpin"
    valid_until: float = 0.0

    def __post_init__(self) -> None:
        if self.valid_until == 0.0:
            self.valid_until = self.ts + SIGNAL_VALID_SECONDS

    def is_valid(self) -> bool:
        return time.time() < self.valid_until

    def boost_for_direction_yes(self) -> float:
        """
        Signed float in [-0.12, +0.12] added to external_boost in momentum scorer.
        Positive = supports BUY_YES. Negative = supports BUY_NO.
        Scales linearly: confidence 0.5 → 0, confidence 0.95 → ±0.12.
        """
        if not self.is_valid():
            return 0.0
        magnitude = (self.confidence - 0.5) / 0.45 * 0.12
        return magnitude * self.direction


class MacroEngine:
    """
    LLM-powered signal engine. Fires all day on sharp BTC moves or VPIN spikes.
    Call tick() every scan cycle (~5s) from the main loop.
    """

    def __init__(self) -> None:
        self.current_signal: Optional[MacroSignal] = None
        self._baseline_price: Optional[float] = None
        self._baseline_ts: float = 0.0
        self._last_trigger_ts: float = 0.0
        self._api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self._enabled: bool = bool(self._api_key)
        # market_briefing cache: (ts, {token_id: result_dict})
        # Keyed by frozenset of candidate token_ids. 20s TTL — one call per scan burst.
        self._briefing_cache: Optional[tuple] = None
        self._briefing_cache_key: frozenset = frozenset()
        self._briefing_ttl: float = 20.0
        # advise_exit cache: {token_id: (ts, action, tighten_sl_pct, confidence, reason)}
        # 30s TTL — don't re-query every OB scan second.
        self._exit_advice_cache: dict = {}
        self._exit_advice_ttl: float = 30.0
        if not self._enabled:
            logger.info(
                "MacroEngine disabled — set ANTHROPIC_API_KEY in .env to enable LLM signals"
            )

    # ── Public interface ──────────────────────────────────────────────────────

    def get_signal(self) -> Optional[MacroSignal]:
        """Returns current valid MacroSignal, or None if expired/absent."""
        if self.current_signal and self.current_signal.is_valid():
            return self.current_signal
        return None

    async def tick(
        self,
        btc_price: Optional[float],
        vpin_score: Optional[float] = None,
        vpin_direction: Optional[int] = None,
    ) -> Optional[MacroSignal]:
        """
        Feed current BTC spot price and optional VPIN data.
        Triggers LLM when:
          - BTC moves ≥ threshold (0.25% in active sessions, 0.40% in quiet hours)
          - OR VPIN exceeds 0.65 with a clear direction

        Returns MacroSignal when LLM fires, else None (cached signal still accessible
        via get_signal()).
        """
        if not self._enabled:
            return None
        if btc_price is None or btc_price <= 0:
            return None

        now = time.time()

        # Return existing valid signal
        if self.current_signal and self.current_signal.is_valid():
            return self.current_signal

        # Cooldown check
        if now - self._last_trigger_ts < COOLDOWN_SECONDS:
            return None

        # Determine trigger threshold for current hour
        hour_utc = datetime.now(timezone.utc).hour
        trigger_pct = (
            _TRIGGER_PCT_HIGH if hour_utc in _HIGH_VOLUME_HOURS
            else _TRIGGER_PCT_LOW
        )

        # Initialise or refresh baseline price
        if self._baseline_price is None:
            self._baseline_price = btc_price
            self._baseline_ts = now
            return None

        elapsed = now - self._baseline_ts
        pct_change = (btc_price - self._baseline_price) / self._baseline_price * 100

        if elapsed > PRICE_BASELINE_RESET_S:
            self._baseline_price = btc_price
            self._baseline_ts = now

        # ── Check triggers ────────────────────────────────────────────────────
        trigger_type = None
        trigger_context = ""

        if abs(pct_change) >= trigger_pct:
            trigger_type = "price"
            trigger_context = f"BTC moved {pct_change:+.3f}% in {elapsed:.0f}s"

        elif (vpin_score is not None
              and vpin_score > VPIN_TRIGGER_THRESHOLD
              and vpin_direction is not None
              and vpin_direction != 0):
            trigger_type = "vpin"
            flow_word = "buy" if vpin_direction == 1 else "sell"
            trigger_context = (
                f"VPIN={vpin_score:.3f} (>{VPIN_TRIGGER_THRESHOLD}) "
                f"with dominant {flow_word} flow"
            )
            # Use recent price direction as the candidate trigger_pct for context
            pct_change = (btc_price - self._baseline_price) / self._baseline_price * 100

        if trigger_type is None:
            return None

        # ── Fire LLM ──────────────────────────────────────────────────────────
        logger.info(
            "MacroEngine TRIGGER [%s] at %s UTC: %s — querying Claude Haiku",
            trigger_type,
            datetime.now(timezone.utc).strftime("%H:%M:%S"),
            trigger_context,
        )
        self._last_trigger_ts = now
        self._baseline_price = btc_price
        self._baseline_ts = now

        signal = await self._query_claude(
            pct_change, btc_price, elapsed, trigger_type, vpin_score, vpin_direction
        )
        if signal:
            self.current_signal = signal
            logger.info(
                "MacroEngine SIGNAL [%s]: %s conf=%.2f expires_in=%.0fs | %s",
                trigger_type,
                "BULLISH (+YES)" if signal.direction > 0 else "BEARISH (+NO)",
                signal.confidence,
                signal.valid_until - now,
                signal.reasoning[:120],
            )
        return signal

    async def market_briefing(
        self,
        candidates: list,
        open_count: int = 0,
        capital: float = 100.0,
    ) -> dict:
        """
        Holistic multi-candidate evaluation — ONE API call for ALL sniper opportunities.

        Replaces per-token evaluate_sniper_trade(). The key upgrade: Claude sees the
        FULL portfolio picture simultaneously:
          - All competing opportunities ranked by quality
          - Correlation between assets (don't double-up on BTC+ETH same direction)
          - Capital context (already 2 positions open → be more selective)
          - Session quality applied across all candidates at once

        candidates: list of dicts with keys:
            token_id, asset, side, delta_pct, fair_value, token_ask, edge,
            elapsed_pct, window_seconds, vpin_score, vpin_direction

        Returns: {token_id: {"decision": "ENTER"/"SKIP", "priority": int,
                              "confidence": float, "reason": str}}
        Defaults to ENTER for all candidates on any failure.
        """
        if not self._enabled:
            return {c["token_id"]: {"decision": "ENTER", "priority": i+1,
                                     "confidence": 0.5, "reason": "LLM disabled"}
                    for i, c in enumerate(candidates)}

        if not candidates:
            return {}

        now = time.time()
        now_utc = datetime.now(timezone.utc)
        cache_key = frozenset(c["token_id"] for c in candidates)

        # Return cached briefing if still fresh and candidates unchanged
        if (self._briefing_cache is not None
                and cache_key == self._briefing_cache_key
                and now - self._briefing_cache[0] < self._briefing_ttl):
            _, cached_result = self._briefing_cache
            logger.debug("BRIEFING (cached) %d candidates", len(candidates))
            return cached_result

        hour = now_utc.hour
        if hour in (8, 9):
            session_desc = "London open — high liquidity, strong trend initiation"
        elif hour in (13, 14, 15):
            day_note = " | Thursday=jobless claims" if now_utc.weekday() == 3 else ""
            session_desc = f"NYSE open / US macro{day_note}"
        elif hour in (22, 23, 0):
            session_desc = "Asia open — BTC-native liquidity"
        else:
            session_desc = f"quiet hours ({now_utc.strftime('%H:%M')} UTC) — 40% reversal rate"

        is_active = hour in _HIGH_VOLUME_HOURS
        sustain_note = "moves sustain ~70% of the time" if is_active else "moves reverse ~40% — higher bar required"

        # Build candidate table for the prompt
        rows = []
        short_ids = {}  # short_key → token_id
        for i, c in enumerate(candidates):
            key = f"T{i+1}"
            short_ids[key] = c["token_id"]
            direction_word = "UP" if c["delta_pct"] > 0 else "DOWN"
            remaining = int(c["window_seconds"] * (1.0 - c["elapsed_pct"]))
            vpin_str = ""
            if c.get("vpin_score") and c["vpin_score"] > 0:
                vpin_agrees = (
                    (c["side"] == "YES" and (c.get("vpin_direction") or 0) > 0)
                    or (c["side"] == "NO" and (c.get("vpin_direction") or 0) < 0)
                )
                vpin_str = f" | VPIN={c['vpin_score']:.2f} {'✓' if vpin_agrees else '✗'}"
            rows.append(
                f"[{key}] {c['asset']} {c['side']} | {direction_word} {abs(c['delta_pct']):.3f}% "
                f"| FV={c['fair_value']:.3f} ask={c['token_ask']:.3f} edge={c['edge']:+.3f} "
                f"| {c['elapsed_pct']:.0%} elapsed {remaining}s left{vpin_str}"
            )
        candidates_text = "\n".join(rows)

        # Correlation warning context
        assets_in_play = [c["asset"] for c in candidates]
        correlation_note = ""
        if len(set(assets_in_play)) < len(assets_in_play):
            correlation_note = "NOTE: Multiple tokens for same asset — pick at most one.\n"
        if open_count > 0:
            correlation_note += f"NOTE: {open_count} position(s) already open — be selective.\n"

        prompt = (
            f"You are a quant trader. Time: {now_utc.strftime('%H:%M')} UTC | {session_desc}\n"
            f"Capital: ${capital:.0f} | {sustain_note}\n\n"
            f"BINARY MARKET OPPORTUNITIES (each resolves to 0 or 1):\n"
            f"{candidates_text}\n\n"
            f"{correlation_note}"
            f"FV = sigmoid model fair probability. Edge = FV - ask. "
            f"VPIN ✓ = order flow confirms direction. ✗ = opposes.\n"
            f"Rank and decide ENTER or SKIP. Take at most 1–2 of the best. "
            f"Skip correlated trades and weak-edge trades.\n\n"
            f"Respond ONLY with JSON array (one entry per opportunity, sorted best-first):\n"
            f'[{{"id":"T1","decision":"ENTER"or"SKIP","priority":1,'
            f'"confidence":0.50-0.95,"reason":"max 10 words"}}]'
        )

        try:
            import aiohttp
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }

            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("BRIEFING API %d — defaulting all ENTER", resp.status)
                        return {c["token_id"]: {"decision": "ENTER", "priority": i+1,
                                                 "confidence": 0.5, "reason": "API error"}
                                for i, c in enumerate(candidates)}
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()
            if "```" in raw_text:
                for part in raw_text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("["):
                        raw_text = part
                        break

            items = json.loads(raw_text)
            result = {}
            for item in items:
                key = item.get("id", "")
                full_token_id = short_ids.get(key)
                if not full_token_id:
                    continue
                decision = item.get("decision", "ENTER").upper()
                if decision not in ("ENTER", "SKIP"):
                    decision = "ENTER"
                result[full_token_id] = {
                    "decision": decision,
                    "priority": int(item.get("priority", 99)),
                    "confidence": max(0.5, min(0.95, float(item.get("confidence", 0.6)))),
                    "reason": str(item.get("reason", ""))[:80],
                }

            # Fill missing candidates with ENTER default
            for c in candidates:
                if c["token_id"] not in result:
                    result[c["token_id"]] = {"decision": "ENTER", "priority": 99,
                                              "confidence": 0.5, "reason": "not in briefing — default ENTER"}

            # Cache result
            self._briefing_cache = (now, result)
            self._briefing_cache_key = cache_key

            vetoed = sum(1 for v in result.values() if v["decision"] == "SKIP")
            logger.info(
                "BRIEFING: %d candidates | %d vetoed | session=%s",
                len(candidates), vetoed,
                "active" if is_active else "quiet",
            )
            for c in candidates:
                r = result[c["token_id"]]
                logger.info(
                    "  [%s] %s/%s → %s p=%d conf=%.2f | %s",
                    "✓" if r["decision"] == "ENTER" else "✗",
                    c["asset"], c["side"], r["decision"],
                    r["priority"], r["confidence"], r["reason"],
                )
            return result

        except Exception as exc:
            logger.warning("BRIEFING failed (%s) — defaulting all ENTER", exc)
            return {c["token_id"]: {"decision": "ENTER", "priority": i+1,
                                     "confidence": 0.5, "reason": f"briefing failed: {type(exc).__name__}"}
                    for i, c in enumerate(candidates)}

    async def advise_exit(
        self,
        token_id: str,
        asset: str,
        direction: str,
        entry_price: float,
        current_price: float,
        time_held_s: float,
        time_remaining_s: float,
        stake: float,
        vpin_score: Optional[float] = None,
        vpin_direction: Optional[int] = None,
    ) -> tuple:
        """
        Exit management advisor for open positions.

        The hardest problem in trading is exit timing — when to take profits vs hold,
        when to cut early vs let it breathe. Our rule-based exits handle clear cases
        (TP at +25%, SL at -35%) but miss the gray zone: +8% with 90s remaining,
        or -5% with momentum reversing. This is where the LLM earns its keep.

        Fires when a position is in the "uncertain zone":
          - Rule-based exits haven't triggered yet
          - Held > 60s (confirmed entry, not a wick)
          - -20% < move < +22% (not yet at profit target or stop)
          - > 60s remaining in window

        Returns: (action, tighten_sl_pct, confidence, reason)
          action: "HOLD" | "EXIT_NOW" | "TIGHTEN_STOP"
          tighten_sl_pct: float (e.g. 0.05 = set SL at cost+5%) or None
        Defaults to HOLD on any failure.
        """
        if not self._enabled:
            return ("HOLD", None, 0.5, "LLM disabled — default HOLD")

        now = time.time()

        # Check cache — don't re-query every second
        cached = self._exit_advice_cache.get(token_id)
        if cached is not None:
            cache_ts, action, tighten_sl, conf, reason = cached
            if now - cache_ts < self._exit_advice_ttl:
                logger.debug(
                    "EXIT ADVICE (cached) %s → %s conf=%.2f | %s",
                    asset, action, conf, reason,
                )
                return (action, tighten_sl, conf, reason)

        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        move_pct = (current_price - entry_price) / entry_price
        pnl_usd = (current_price - entry_price) * (stake / entry_price)
        breakeven_price = entry_price * 1.018  # ~1.8% round-trip fee at 0.50 odds

        # VPIN context
        vpin_line = ""
        if vpin_score is not None:
            flow_word = "buying" if (vpin_direction or 0) > 0 else "selling"
            vpin_line = f"VPIN={vpin_score:.3f} ({flow_word} flow) | "

        # Is the price trend aligned with our direction?
        # direction for sniper is always "token going UP = profit"
        # move_pct > 0 always means we're in profit

        is_active = hour in _HIGH_VOLUME_HOURS

        prompt = (
            f"Managing open binary market position at {now_utc.strftime('%H:%M')} UTC.\n\n"
            f"POSITION: {asset} {direction}\n"
            f"Entry: {entry_price:.4f} | Current: {current_price:.4f} | Move: {move_pct:+.1%}\n"
            f"Held: {time_held_s:.0f}s | Window closes in: {time_remaining_s:.0f}s\n"
            f"Unrealized P&L: ${pnl_usd:+.3f} on ${stake:.2f} stake\n"
            f"{vpin_line}Breakeven price (after fees): {breakeven_price:.4f}\n\n"
            f"CONTEXT:\n"
            f"- Binary market: resolves to 0 or 1 in {time_remaining_s:.0f}s\n"
            f"- If thesis correct: token prices toward 0.95+ before expiry\n"
            f"- If thesis wrong: token prices toward 0.05-\n"
            f"- Current price {'above' if current_price > breakeven_price else 'BELOW'} breakeven\n"
            f"- Session: {'active (moves sustain ~70%)' if is_active else 'quiet (40% reversal rate)'}\n\n"
            f"OPTIONS:\n"
            f"- HOLD: thesis still valid, more upside likely before window closes\n"
            f"- EXIT_NOW: lock in P&L ({pnl_usd:+.3f}), risk/reward no longer favors holding\n"
            f"- TIGHTEN_STOP: stay in but protect against reversal — "
            f"set stop at cost+X% (specify tighten_sl_pct, e.g. 0.05 = stop at cost+5%)\n\n"
            f'Respond ONLY with JSON: {{"action":"HOLD"or"EXIT_NOW"or"TIGHTEN_STOP",'
            f'"tighten_sl_pct":null or 0.03-0.20,"confidence":0.50-0.95,"reason":"max 10 words"}}'
        )

        try:
            import aiohttp
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 80,
                "messages": [{"role": "user", "content": prompt}],
            }

            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    if resp.status != 200:
                        logger.debug("EXIT ADVICE API %d — defaulting HOLD", resp.status)
                        return ("HOLD", None, 0.5, "API error — HOLD")
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()
            if "```" in raw_text:
                for part in raw_text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        raw_text = part
                        break

            result = json.loads(raw_text)
            action = result.get("action", "HOLD").upper()
            if action not in ("HOLD", "EXIT_NOW", "TIGHTEN_STOP"):
                action = "HOLD"
            tighten_sl = result.get("tighten_sl_pct")
            if tighten_sl is not None:
                tighten_sl = max(0.03, min(0.20, float(tighten_sl)))
            confidence = max(0.5, min(0.95, float(result.get("confidence", 0.6))))
            reason = str(result.get("reason", ""))[:80]

            self._exit_advice_cache[token_id] = (now, action, tighten_sl, confidence, reason)

            logger.info(
                "EXIT ADVICE %s/%s → %s conf=%.2f move=%+.1%% remaining=%.0fs | %s",
                asset, direction, action, confidence,
                move_pct, time_remaining_s, reason,
            )
            return (action, tighten_sl, confidence, reason)

        except Exception as exc:
            logger.debug("EXIT ADVICE failed (%s) — defaulting HOLD", exc)
            return ("HOLD", None, 0.5, f"failed ({type(exc).__name__}) — HOLD")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _query_claude(
        self,
        pct_change: float,
        btc_price: float,
        elapsed_s: float,
        trigger_type: str,
        vpin_score: Optional[float],
        vpin_direction: Optional[int],
    ) -> Optional[MacroSignal]:
        """Call Claude Haiku for directional interpretation. ~300–800ms latency."""
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        time_str = now_utc.strftime("%H:%M UTC")
        weekday = now_utc.weekday()

        # Session context
        if hour in (8, 9):
            session = "London open (08:00 UTC) — elevated liquidity, trend-initiation phase"
        elif hour in (13, 14, 15):
            day_note = ""
            if weekday == 3:
                day_note = " — Thursday: likely US weekly jobless claims at 13:30"
            elif weekday == 4:
                day_note = " — Friday: possible NFP if first Friday of month"
            session = f"NYSE open / US macro window (13:30 UTC){day_note}"
        elif hour in (22, 23, 0):
            session = "Asia open (23:00 UTC) — BTC-native liquidity, often trend-setting"
        else:
            session = f"mid-session ({time_str}) — lower liquidity"

        direction_word = "UP" if pct_change >= 0 else "DOWN"
        abs_pct = abs(pct_change)

        if trigger_type == "vpin":
            flow_word = "aggressive buying" if (vpin_direction or 0) > 0 else "aggressive selling"
            move_desc = (
                f"Binance aggTrade stream shows VPIN={vpin_score:.3f} "
                f"with {flow_word} (informed order flow signal). "
                f"BTC is {direction_word} {abs_pct:.3f}% vs 90s ago at ${btc_price:,.0f}."
            )
        else:
            move_desc = (
                f"BTC moved {direction_word} {abs_pct:.3f}% to ${btc_price:,.0f} "
                f"over {elapsed_s:.0f}s."
            )

        prompt = (
            f"You are a quant trader in crypto prediction markets.\n"
            f"Session: {session}\n"
            f"{move_desc}\n\n"
            f"Will BTC continue {direction_word} for the next 2–5 minutes, or reverse?\n"
            f"Consider: sharp moves in high-volume sessions sustain ~70% of the time; "
            f"VPIN spikes precede directional moves; quiet-hour moves fade more often (~40%).\n\n"
            f'Respond ONLY with valid JSON: '
            f'{{"direction":"UP" or "DOWN","confidence":0.50-0.95,'
            f'"reasoning":"max 15 words"}}'
        )

        raw_text = ""
        try:
            import aiohttp
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            }

            async with aiohttp.ClientSession() as session_http:
                async with session_http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        logger.debug("Claude API %d: %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()
            if "```" in raw_text:
                for part in raw_text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        raw_text = part
                        break

            result = json.loads(raw_text)
            direction = 1 if result.get("direction", "").upper() == "UP" else -1
            confidence = max(0.5, min(0.95, float(result.get("confidence", 0.6))))
            reasoning = str(result.get("reasoning", ""))

            return MacroSignal(
                ts=time.time(),
                direction=direction,
                confidence=confidence,
                trigger_pct=pct_change,
                reasoning=reasoning,
                trigger_type=trigger_type,
            )

        except json.JSONDecodeError as exc:
            logger.debug("MacroEngine JSON parse error: %s | raw=%s", exc, raw_text[:200])
            return None
        except Exception as exc:
            logger.debug("MacroEngine Claude call failed: %s", exc)
            return None
