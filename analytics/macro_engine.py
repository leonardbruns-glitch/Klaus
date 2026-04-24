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


class _RateLimitError(Exception):
    """Raised on HTTP 429 — caller should retry, not store a SKIP decision."""
    def __init__(self, retry_after: float = 15.0):
        self.retry_after = retry_after


# ── Trigger thresholds by session ─────────────────────────────────────────────
# High-volume session hours UTC: London open, NYSE open/macro, Asia open
_HIGH_VOLUME_HOURS = {8, 9, 13, 14, 15, 22, 23, 0}
_TRIGGER_PCT_HIGH = 0.25    # flat — same threshold all hours, collect data first
_TRIGGER_PCT_LOW  = 0.25    # same as active (no quiet-hour penalty)

# ── Signal parameters ─────────────────────────────────────────────────────────
SIGNAL_VALID_SECONDS = 120   # signal lasts 2 minutes
COOLDOWN_ACTIVE = 60         # 1 min cooldown during high-volume sessions
COOLDOWN_QUIET = 180         # 3 min cooldown during quiet hours
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
        # Pre-session brief: track last briefed session hour to fire once per session
        self._last_session_brief_hour: int = -1
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
        ext_signals: Optional[dict] = None,
    ) -> Optional[MacroSignal]:
        """
        Feed current BTC spot price, optional VPIN data, and full ext_signals dict.
        Triggers LLM when:
          - BTC moves ≥ threshold (0.25% in active sessions, 0.40% in quiet hours)
          - OR VPIN exceeds 0.65 with a clear direction

        ext_signals: {asset: ExternalSignal} — if provided, enriches Claude context
        with ETH/SOL moves and cross-asset VPIN.

        Returns MacroSignal when LLM fires, else None (cached signal still accessible
        via get_signal()).
        """
        if not self._enabled:
            return None
        if btc_price is None or btc_price <= 0:
            return None

        now = time.time()
        hour_utc = datetime.now(timezone.utc).hour
        is_active = hour_utc in _HIGH_VOLUME_HOURS

        # ── Pre-session brief: fire once at the start of each session window ──
        session_start_hours = {8, 13, 22}
        if hour_utc in session_start_hours and hour_utc != self._last_session_brief_hour:
            self._last_session_brief_hour = hour_utc
            await self._session_brief(btc_price, hour_utc, ext_signals)

        # Return existing valid signal
        if self.current_signal and self.current_signal.is_valid():
            return self.current_signal

        # Session-aware cooldown: 60s active sessions, 180s quiet hours
        cooldown = COOLDOWN_ACTIVE if is_active else COOLDOWN_QUIET
        if now - self._last_trigger_ts < cooldown:
            return None

        # Determine trigger threshold for current hour
        trigger_pct = _TRIGGER_PCT_HIGH if is_active else _TRIGGER_PCT_LOW

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
            pct_change, btc_price, elapsed, trigger_type, vpin_score, vpin_direction,
            ext_signals=ext_signals,
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
            session_desc = f"off-peak hours ({now_utc.strftime('%H:%M')} UTC)"

        is_active = hour in _HIGH_VOLUME_HOURS
        sustain_note = "high-liquidity session — strong trend initiation" if is_active else "standard session — evaluate edge on merit"

        # Build candidate table for the prompt
        rows = []
        short_ids = {}  # short_key → token_id
        for i, c in enumerate(candidates):
            key = f"T{i+1}"
            short_ids[key] = c["token_id"]
            direction_word = "UP" if c["delta_pct"] > 0 else "DOWN"
            remaining = int(c["window_seconds"] * (1.0 - c["elapsed_pct"]))
            lag_pct = c.get("lag_remaining_pct", 0.0)
            vpin_str = ""
            if c.get("vpin_score") and c["vpin_score"] > 0:
                vpin_agrees = (
                    (c["side"] == "YES" and (c.get("vpin_direction") or 0) > 0)
                    or (c["side"] == "NO" and (c.get("vpin_direction") or 0) < 0)
                )
                vpin_str = f" | VPIN={c['vpin_score']:.2f} {'✓' if vpin_agrees else '✗'}"
            rows.append(
                f"[{key}] {c['asset']} {c['side']} | Binance {direction_word} {abs(c['delta_pct']):.3f}% "
                f"| PM lag={lag_pct:.0%} remaining (FV={c['fair_value']:.3f} ask={c['token_ask']:.3f}) "
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

        briefing_system = (
            "You are an expert quant trader specializing in Polymarket crypto binary markets. "
            "You evaluate 15-minute BTC/ETH/SOL up/down contracts. "
            "Your edge: Binance spot moves, but Polymarket takes 30-120s to fully reprice. "
            "PM lag % = how much of the expected Binance move Polymarket has NOT yet priced in. "
            "lag=100% means PM hasn't moved at all — maximum opportunity. "
            "lag=20% means PM has mostly repriced — thin edge, be selective. "
            "FV = sigmoid fair value given Binance delta. High lag + high FV = strong entry. "
            "Only SKIP if lag is thin, correlation conflicts, or session quality is poor."
        )

        prompt = (
            f"Time: {now_utc.strftime('%H:%M')} UTC | {session_desc}\n"
            f"Capital: ${capital:.0f} | {sustain_note}\n\n"
            f"OPPORTUNITIES (Binance moved, Polymarket hasn't fully repriced yet):\n"
            f"{candidates_text}\n\n"
            f"{correlation_note}"
            f"PM lag % = fraction of expected move still unpriced. Higher = more edge remaining. "
            f"VPIN ✓ = informed order flow confirms direction.\n"
            f"Rank and decide ENTER or SKIP. High lag (>70%) = strong prior for ENTER.\n\n"
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
                "system": briefing_system,
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
        spot_price: Optional[float] = None,
        spot_change_pct: Optional[float] = None,
        breach_price: Optional[float] = None,
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

        is_active = hour in _HIGH_VOLUME_HOURS

        # Spot price momentum context: is the underlying asset confirming the trade?
        spot_line = ""
        if spot_price and spot_price > 0:
            spot_line = f"Spot {asset}: ${spot_price:,.2f}"
            if spot_change_pct is not None:
                move_word = "moving WITH" if (
                    (direction == "BUY_YES" and spot_change_pct > 0)
                    or (direction == "BUY_NO" and spot_change_pct < 0)
                ) else "moving AGAINST"
                spot_line += f" ({spot_change_pct:+.3f}% — {move_word} thesis)"
            spot_line += " | "

        # L6: breach drift — is adverse move slowing (wick) or accelerating (genuine reversal)?
        breach_line = ""
        if breach_price is not None and breach_price > 0:
            drift_pct = (current_price - breach_price) / breach_price
            if drift_pct > 0.005:
                drift_desc = f"RECOVERING +{drift_pct:.1%} since breach — wick signal"
            elif drift_pct < -0.005:
                drift_desc = f"CONTINUING {drift_pct:.1%} since breach — genuine reversal signal"
            else:
                drift_desc = f"FLAT {drift_pct:+.1%} since breach — inconclusive"
            breach_line = f"Price at SL breach: {breach_price:.4f} | Drift since breach: {drift_desc} | "

        exit_system = (
            "You are an expert quant trader managing open positions in Polymarket crypto binary markets. "
            "These are 5-minute and 15-minute up/down binary contracts. A token resolves to 0 (loss) or 1 (full win). "
            "Round-trip taker fees are ~3.6% at p=0.50. Exit timing is the hardest part — "
            "lock in gains too early and you miss the full move; hold too long and reversals erase profits. "
            "VPIN declining = informed flow leaving = reversal risk rising. "
            "RECOVERING breach drift = price bouncing after SL hit = likely wick, prefer HOLD."
        )

        prompt = (
            f"Managing open binary position at {now_utc.strftime('%H:%M')} UTC.\n\n"
            f"POSITION: {asset} {direction}\n"
            f"Entry: {entry_price:.4f} | Current: {current_price:.4f} | Move: {move_pct:+.1%}\n"
            f"Held: {time_held_s:.0f}s | Window closes in: {time_remaining_s:.0f}s\n"
            f"Unrealized P&L: ${pnl_usd:+.3f} on ${stake:.2f} stake\n"
            f"{breach_line}{spot_line}{vpin_line}Breakeven (after fees): {breakeven_price:.4f}\n\n"
            f"CONTEXT:\n"
            f"- Binary: resolves 0 or 1 in {time_remaining_s:.0f}s\n"
            f"- If thesis holds: token approaches 0.95+ before expiry\n"
            f"- Current price {'ABOVE' if current_price > breakeven_price else 'BELOW'} breakeven\n"
            f"- Session: {'active (moves sustain ~70%)' if is_active else 'quiet (40% reversal rate)'}\n\n"
            f"OPTIONS:\n"
            f"- HOLD: thesis valid, more upside before window closes\n"
            f"- EXIT_NOW: lock in P&L ({pnl_usd:+.3f}), risk/reward deteriorated\n"
            f"- TIGHTEN_STOP: stay in but set trailing stop at cost+X%\n\n"
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
                "system": exit_system,
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
                "EXIT ADVICE %s/%s → %s conf=%.2f move=%+.1f%% remaining=%.0fs | %s",
                asset, direction, action, confidence,
                move_pct, time_remaining_s, reason,
            )
            return (action, tighten_sl, confidence, reason)

        except Exception as exc:
            logger.debug("EXIT ADVICE failed (%s) — defaulting HOLD", exc)
            return ("HOLD", None, 0.5, f"failed ({type(exc).__name__}) — HOLD")

    async def bond_advisor(
        self,
        asset: str,
        direction: str,
        entry_price: float,
        bond_entry_class: str,
        bond_entry_zone: str,
        bond_delta_at_entry: float,
        bond_delta_accel_30s: float,
        bond_edge_drift_30s: float,
        bond_smooth_delta_60s: float,
        vpin: float,
        edge: float,
        window_size_s: int,
        window_remaining_s: float,
        recent_history: list | None = None,
        research_notes: list | None = None,
    ) -> dict:
        """
        Agentic entry decision. Opus requests whatever data it wants via tools,
        then calls take or skip. No pre-selected context forced on it.
        Returns {"decision": "TAKE"/"SKIP", "confidence": float, "reason": str,
                 "shadow_tp_pct": float, "shadow_sl_pct": float}.
        """
        import json as _json
        if not self._enabled:
            return {"decision": "TAKE", "confidence": 0.5, "reason": "LLM disabled"}

        now_utc = datetime.now(timezone.utc)
        zone = bond_entry_zone or (bond_entry_class.split("/")[0] if bond_entry_class else "?")

        # Catalog keys match tool names exactly so lookups work
        _catalog: dict = {
            "get_market_info": {
                "time_utc": now_utc.strftime("%H:%M"),
                "asset": asset,
                "direction": direction,
                "token_price": round(entry_price, 4),
                "window_minutes": window_size_s // 60,
                "remaining_seconds": round(window_remaining_s),
                "zone": zone,
                "entry_class": bond_entry_class,
            },
            "get_signals": {
                "spot_delta_pct": round(bond_delta_at_entry, 4),
                "delta_accel_30s": round(bond_delta_accel_30s, 4),
                "smooth_delta_60s": round(bond_smooth_delta_60s, 4),
                "edge": round(edge, 4),
                "edge_drift_30s": round(bond_edge_drift_30s, 4),
                "vpin": round(vpin, 3),
            },
        }

        if recent_history:
            rows = []
            for h in recent_history[:15]:
                pnl = float(h.get("shadow_gross_pnl", 0) or 0)
                rows.append({
                    "asset": h.get("asset", "?"),
                    "direction": h.get("direction", "?"),
                    "zone": h.get("zone", "?"),
                    "decision": h.get("llm_decision", "?"),
                    "conf": round(float(h.get("llm_conf", 0) or 0), 2),
                    "exit_reason": h.get("exit_reason", "open"),
                    "pnl": round(pnl, 2),
                })
            _catalog["get_history"] = rows
        else:
            _catalog["get_history"] = []

        _catalog["get_research_notes"] = research_notes or []

        tools = [
            # Data pre-loaded in first message — only terminal tools exposed.
            {
                "name": "take",
                "description": "Enter this trade.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "direction":   {"type": "string",  "description": "UP or DOWN"},
                        "confidence":  {"type": "number",  "description": "0–1 edge strength estimate"},
                        "reason":      {"type": "string",  "description": "Concise explanation of edge"},
                        "edge_type":   {"type": "string",  "description": "trend|reversal|mean_reversion|noise|structural|unknown"},
                    },
                    "required": ["direction", "confidence", "reason", "edge_type"],
                },
            },
            {
                "name": "skip",
                "description": "Pass on this candidate.",
                "input_schema": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                },
            },
        ]
        system_prompt = (
            "You are an autonomous market intelligence and trade selection agent operating in "
            "live binary 5-minute markets (BTC, ETH, SOL).\n\n"
            "Your objective is to identify whether a statistically meaningful edge exists in "
            "the current opportunity.\n\n"
            "You have full freedom to:\n"
            "- Query any available market data or history\n"
            "- Analyze regime, microstructure, momentum, and anomalies\n"
            "- Form multiple competing hypotheses\n"
            "- Reject trades aggressively when uncertain or noisy\n\n"
            "You must NOT design trade mechanics.\n"
            "You do NOT set TP, SL, or position sizing.\n\n"
            "Your only allowed outputs are:\n"
            "- take(direction, confidence, reason, edge_type)\n"
            "- skip(reason)\n\n"
            "Where:\n"
            "- direction = UP or DOWN\n"
            "- confidence = 0–1 subjective estimate of edge strength\n"
            "- edge_type = one of: trend, reversal, mean_reversion, noise, structural, unknown\n\n"
            "Rules:\n"
            "- Only take trades when a clear edge exists beyond noise.\n"
            "- If uncertain, choose skip.\n"
            "- Do not overtrade.\n"
            "- Do not assume reversibility of price moves as justification.\n\n"
            "---\n\n"
            "Before making a decision, you MUST work through these steps:\n\n"
            "Step 1 — Evaluate BOTH sides:\n"
            "1. Assume UP is correct:\n"
            "   - What would need to happen for UP to win at expiry?\n"
            "   - Is current price underestimating that probability?\n\n"
            "2. Assume DOWN is correct:\n"
            "   - What would need to happen for DOWN to win?\n"
            "   - Is current price underestimating that probability?\n\n"
            "Step 2 — Estimate mispricing magnitude:\n"
            "- How large is the mispricing for UP? (small / moderate / large)\n"
            "- How large is the mispricing for DOWN? (small / moderate / large)\n\n"
            "Step 3 — Apply asymmetry filter:\n"
            "- Only act if ONE side is CLEARLY more mispriced than the other.\n"
            "- If both are weak, both are similar, or you cannot distinguish → SKIP.\n"
            "- Prefer strong asymmetry over frequent trading.\n\n"
            "Do NOT base your decision on current price movement alone.\n\n"
            "---\n\n"
            "On momentum signals (delta, acceleration):\n"
            "Price movement may be used as SUPPORTING CONTEXT — not as the primary reason.\n"
            "It is a context modifier, not a decision driver.\n\n"
            "Hard rule: If your reasoning is primarily:\n"
            "- 'negative delta → skip'\n"
            "- 'no acceleration → skip'\n"
            "- 'momentum is weak → skip'\n"
            "- 'no strong signal → skip'\n"
            "- 'unclear direction → skip'\n"
            "- 'waiting for confirmation → skip'\n\n"
            "...you are thinking like a trader, not a probability engine. Go back to Step 1.\n\n"
            "You are a probability arbitrage engine under time constraint.\n"
            "Your job: find asymmetric mispricings. Act only on clear asymmetry.\n\n"
            "---\n\n"
            "On provided signals (edge, delta, acceleration, VPIN):\n"
            "These are derived model outputs. They may be misleading or wrong.\n"
            "Do NOT treat them as truth or final judgment.\n\n"
            "You must independently reason about outcome probability, even if signals suggest otherwise.\n\n"
            "If a signal says 'no edge' or 'negative edge', you must still evaluate whether "
            "the market price itself is mispriced. Signals can be wrong. Price can still be wrong.\n\n"
            "You are ALLOWED to disagree with all provided signals.\n"
            "If your independent reasoning contradicts them, follow your reasoning.\n\n"
            "You are not an interpreter of this system's model.\n"
            "You are a challenger of it."
        )
        direction_label = "UP" if "YES" in direction else "DOWN"

        # Pre-load all data into first message — LLM decides in 1 round, not 4-6.
        # Tools still available for follow-up questions if needed.
        _preload = (
            f"Market data (pre-loaded):\n\n"
            f"**Market info**: {json.dumps(_catalog['get_market_info'])}\n\n"
            f"**Signals**: {json.dumps(_catalog['get_signals'])}\n\n"
            f"**History** (last {len(_catalog.get('get_history', []))} trades): "
            f"{json.dumps(_catalog.get('get_history', []))}\n\n"
            f"**Research notes** (last {len(_catalog.get('get_research_notes', []))} findings): "
            f"{json.dumps(_catalog.get('get_research_notes', []))}\n\n"
            f"All data is above. Call take() or skip() now. Do not output text."
        )
        messages: list = [{"role": "user", "content": _preload}]
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                for _ in range(6):
                    payload = {
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 400,
                        "system": system_prompt,
                        "tools": tools,
                        "messages": messages,
                    }
                    async with sess.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status == 429:
                            raise _RateLimitError(float(resp.headers.get("retry-after", 15)))
                        if resp.status != 200:
                            body = await resp.text()
                            raise Exception(f"API {resp.status}: {body[:60]}")
                        data = await resp.json()

                    content_blocks = data.get("content", [])
                    tool_results = []
                    terminal = None

                    for block in content_blocks:
                        if block.get("type") != "tool_use":
                            continue
                        name = block["name"]
                        inp = block.get("input", {})
                        bid = block["id"]

                        if name == "take":
                            terminal = {
                                "decision":      "TAKE",
                                "conf":          max(0.5, min(0.95, float(inp.get("confidence", 0.6)))),
                                "reason":        str(inp.get("reason", ""))[:80],
                                "edge_type":     str(inp.get("edge_type", "unknown")),
                                "shadow_tp_pct": 15.0,
                                "shadow_sl_pct": 12.0,
                            }
                            break
                        elif name == "skip":
                            terminal = {
                                "decision":      "SKIP",
                                "conf":          0.5,
                                "reason":        str(inp.get("reason", ""))[:80],
                                "shadow_tp_pct": 15.0,
                                "shadow_sl_pct": 12.0,
                            }
                            break
                        elif name in _catalog:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": bid,
                                "content": json.dumps(_catalog[name]),
                            })
                        else:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": bid,
                                "content": f"Unknown tool: {name}",
                                "is_error": True,
                            })

                    if terminal:
                        logger.info(
                            "BOND_LLM %s/%s → %s conf=%.2f entry=%.3f zone=%s edge=%s | %s",
                            asset, direction_label, terminal["decision"], terminal["conf"],
                            entry_price, zone, terminal.get("edge_type", "?"),
                            terminal["reason"],
                        )
                        return terminal

                    # LLM output text without calling a terminal tool — nudge it to decide
                    if data.get("stop_reason") == "end_turn":
                        messages.append({"role": "assistant", "content": content_blocks})
                        messages.append({"role": "user", "content": "Do NOT output text. Call take() or skip() tool now."})
                        continue

                    if not tool_results:
                        break

                    messages.append({"role": "assistant", "content": content_blocks})
                    messages.append({"role": "user", "content": tool_results})

            return {"decision": "SKIP", "conf": 0.5, "reason": "no terminal decision",
                    "shadow_tp_pct": 15.0, "shadow_sl_pct": 12.0}

        except _RateLimitError:
            raise
        except Exception as exc:
            logger.warning("bond_advisor failed (%s) — default SKIP", exc)
            return {"decision": "SKIP", "confidence": 0.5, "reason": f"API {type(exc).__name__}: {str(exc)[:40]}",
                    "shadow_tp_pct": 15.0, "shadow_sl_pct": 12.0}

    async def bond_exit_advisor(
        self,
        asset: str,
        direction: str,
        entry_price: float,
        current_price: float,
        pnl_pct: float,
        held_s: float,
        remaining_s: float,
        bond_delta: float = 0.0,
        vpin: float = 0.0,
        entry_reason: str = "",
        entry_tp_pct: float = 0.0,
        entry_sl_pct: float = 0.0,
        highest_price: float = 0.0,
        lowest_price: float = 0.0,
        recent_history: list | None = None,
        research_notes: list | None = None,
    ) -> dict:
        """
        Agentic exit decision via aiohttp tool-use loop.
        Haiku requests whatever data it wants, then calls exit_now or hold.
        """
        if not self._enabled:
            return {"decision": "HOLD", "reason": "LLM disabled", "conf": 0.5}

        # Catalog keys match tool names exactly
        _catalog = {
            "get_position": {
                "asset": asset,
                "direction": direction,
                "entry_price": round(entry_price, 4),
                "current_price": round(current_price, 4),
                "pnl_pct": round(pnl_pct, 2),
                "held_seconds": round(held_s),
                "remaining_seconds": round(remaining_s),
                "peak_price": round(highest_price, 4),
                "trough_price": round(lowest_price, 4),
                "entry_thesis": entry_reason,
                "entry_tp_pct": entry_tp_pct,
                "entry_sl_pct": entry_sl_pct,
            },
            "get_market_flow": {
                "binance_delta_pct": round(bond_delta, 3),
                "vpin": round(vpin, 3),
            },
        }

        if recent_history:
            rows = []
            for h in recent_history[:15]:
                pnl = float(h.get("shadow_gross_pnl", 0) or 0)
                rows.append({
                    "asset": h.get("asset", "?"),
                    "direction": h.get("direction", "?"),
                    "zone": h.get("zone", "?"),
                    "entry_decision": h.get("llm_decision", "?"),
                    "exit_reason": h.get("exit_reason", "open"),
                    "held_seconds": h.get("hold_seconds", 0),
                    "pnl": round(pnl, 2),
                    "entry_thesis": (h.get("llm_reason", "") or "")[:60],
                })
            _catalog["get_history"] = rows
        else:
            _catalog["get_history"] = []

        _catalog["get_research_notes"] = research_notes or []

        tools = [
            # Data pre-loaded in first message — only terminal tools exposed.
            {
                "name": "exit_now",
                "description": "Close the position immediately.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["confidence", "reason"],
                },
            },
            {
                "name": "hold",
                "description": "Keep holding. You will be called again in ~10 seconds.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["confidence", "reason"],
                },
            },
        ]

        system_prompt = (
            "Exit agents fail when they \"think like traders.\" So we remove creativity almost entirely.\n\n"
            "You are an autonomous position monitoring agent in a live binary market.\n\n"
            "Your objective is to determine whether the original trade hypothesis is still "
            "valid or has been invalidated.\n\n"
            "You have access to:\n"
            "- Current position state\n"
            "- Market flow and price evolution\n"
            "- Relevant recent market context\n\n"
            "You must NOT generate new trade ideas.\n"
            "You must NOT optimize exits.\n"
            "You must NOT scalp or micro-time exits.\n\n"
            "Your only outputs are:\n"
            "- hold(reason)\n"
            "- exit_now(confidence, reason)\n\n"
            "Rules:\n"
            "- Exit ONLY if the original hypothesis is invalidated or risk regime has clearly changed.\n"
            "- Otherwise hold.\n"
            "- Do not react to short-term noise unless structural break is detected.\n"
            "- Do not \"take profit early\" unless thesis is broken."
        )
        _exit_preload = (
            f"Position data (pre-loaded):\n\n"
            f"**Position**: {json.dumps(_catalog['get_position'])}\n\n"
            f"**Market flow**: {json.dumps(_catalog['get_market_flow'])}\n\n"
            f"**History** (last {len(_catalog.get('get_history', []))} trades): "
            f"{json.dumps(_catalog.get('get_history', []))}\n\n"
            f"**Research notes**: {json.dumps(_catalog.get('get_research_notes', []))}\n\n"
            f"All data is above. Call exit_now() or hold() now. Do not output text."
        )
        messages: list = [{"role": "user", "content": _exit_preload}]
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                for _ in range(5):
                    payload = {
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 300,
                        "system": system_prompt,
                        "tools": tools,
                        "messages": messages,
                    }
                    async with sess.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 429:
                            raise _RateLimitError(float(resp.headers.get("retry-after", 15)))
                        if resp.status != 200:
                            body = await resp.text()
                            raise Exception(f"API {resp.status}: {body[:60]}")
                        data = await resp.json()

                    content_blocks = data.get("content", [])
                    tool_results = []
                    terminal = None

                    for block in content_blocks:
                        if block.get("type") != "tool_use":
                            continue
                        name = block["name"]
                        inp = block.get("input", {})
                        bid = block["id"]

                        if name == "exit_now":
                            terminal = {
                                "decision": "EXIT",
                                "conf": max(0.5, min(0.95, float(inp.get("confidence", 0.7)))),
                                "reason": str(inp.get("reason", ""))[:80],
                            }
                            break
                        elif name == "hold":
                            terminal = {
                                "decision": "HOLD",
                                "conf": max(0.5, min(0.95, float(inp.get("confidence", 0.7)))),
                                "reason": str(inp.get("reason", ""))[:80],
                            }
                            break
                        elif name in _catalog:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": bid,
                                "content": json.dumps(_catalog[name]),
                            })
                        else:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": bid,
                                "content": f"Unknown tool: {name}",
                                "is_error": True,
                            })

                    if terminal:
                        logger.info(
                            "bond_exit_advisor %s/%s → %s conf=%.2f rem=%.0fs | %s",
                            asset, direction, terminal["decision"],
                            terminal["conf"], remaining_s, terminal["reason"],
                        )
                        return terminal

                    if data.get("stop_reason") == "end_turn" or not tool_results:
                        break

                    messages.append({"role": "assistant", "content": content_blocks})
                    messages.append({"role": "user", "content": tool_results})

            return {"decision": "HOLD", "conf": 0.5, "reason": "no terminal decision"}

        except Exception as exc:
            logger.debug("bond_exit_advisor failed (%s) — HOLD", exc)
            return {"decision": "HOLD", "conf": 0.5, "reason": f"API error: {type(exc).__name__}"}

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _query_claude(
        self,
        pct_change: float,
        btc_price: float,
        elapsed_s: float,
        trigger_type: str,
        vpin_score: Optional[float],
        vpin_direction: Optional[int],
        ext_signals: Optional[dict] = None,
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

        # Multi-asset context: ETH and SOL correlated moves within 10-30s
        cross_asset_lines = []
        if ext_signals:
            for asset in ("ETH", "SOL"):
                ext = ext_signals.get(asset)
                if ext and ext.spot_price and ext.spot_price > 0:
                    vpin_str = ""
                    if ext.vpin_score and ext.vpin_score > 0:
                        flow = "buy" if (ext.vpin_direction or 0) > 0 else "sell"
                        vpin_str = f" VPIN={ext.vpin_score:.2f}({flow})"
                    cross_asset_lines.append(
                        f"{asset}: ${ext.spot_price:,.2f}{vpin_str}"
                    )
            # Funding rate context
            for asset in ("BTC", "ETH"):
                ext = ext_signals.get(asset)
                if ext and ext.funding_rate and abs(ext.funding_rate) > 0.0001:
                    apr = ext.funding_rate * 3 * 365 * 100  # 8h rate → APR%
                    if abs(apr) > 30:
                        bias = "crowded longs" if apr > 0 else "crowded shorts"
                        cross_asset_lines.append(
                            f"{asset} funding: {apr:+.0f}% APR ({bias})"
                        )

        cross_asset_text = ""
        if cross_asset_lines:
            cross_asset_text = "Cross-asset: " + " | ".join(cross_asset_lines) + "\n"

        system_prompt = (
            "You are an expert quant trader specializing in Polymarket crypto binary markets. "
            "You have deep knowledge of BTC/ETH/SOL microstructure, VPIN order flow analysis, "
            "and Polymarket's 30-120s repricing lag after sharp spot moves. "
            "Your job is to assess whether a triggered move will sustain for 2-5 minutes "
            "so Polymarket updown tokens can reprice. Be concise and precise."
        )

        prompt = (
            f"Session: {session}\n"
            f"Trigger: {move_desc}\n"
            f"{cross_asset_text}\n"
            f"Will BTC continue {direction_word} for the next 2–5 minutes, or reverse?\n"
            f"Key factors:\n"
            f"- High-volume session moves sustain ~70%; quiet-hour moves reverse ~40%\n"
            f"- VPIN>0.65 = institutional flow, strong sustain signal\n"
            f"- Cross-asset confirmation (ETH/SOL same direction) = more conviction\n"
            f"- Funding rate extremes (>80% APR) = crowded → higher reversal risk\n\n"
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
                "system": system_prompt,
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

    async def _session_brief(
        self,
        btc_price: float,
        hour: int,
        ext_signals: Optional[dict] = None,
    ) -> None:
        """
        Fire a single LLM call at the start of each session window (08/13/22 UTC)
        to establish session context and prime the macro engine's outlook.
        Result is stored in current_signal if conviction is high enough.
        ~$0.001 per call, fires 3×/day max.
        """
        if not self._enabled:
            return

        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()

        if hour == 8:
            session_name = "London open"
            session_note = "high-liquidity trend-initiation; EUR macro data often releases here"
        elif hour == 13:
            day_note = ""
            if weekday == 3:
                day_note = " Thursday = weekly US jobless claims at 13:30 — strongest weekly edge"
            elif weekday == 4:
                day_note = " Check if it's first Friday (NFP)"
            session_name = f"NYSE open{day_note}"
            session_note = "highest-edge window; US macro drives BTC 0.3-1.5% moves in seconds"
        else:
            session_name = "Asia open"
            session_note = "BTC-native liquidity; Shanghai/Tokyo traders set overnight direction"

        # Cross-asset snapshot
        asset_lines = []
        if ext_signals:
            for asset in ("BTC", "ETH", "SOL"):
                ext = ext_signals.get(asset)
                if ext and ext.spot_price and ext.spot_price > 0:
                    funding_str = ""
                    if ext.funding_rate and abs(ext.funding_rate) > 0.0001:
                        apr = ext.funding_rate * 3 * 365 * 100
                        funding_str = f" funding={apr:+.0f}%APR"
                    asset_lines.append(f"{asset}=${ext.spot_price:,.2f}{funding_str}")

        asset_text = " | ".join(asset_lines) if asset_lines else f"BTC=${btc_price:,.0f}"

        system_prompt = (
            "You are an expert quant trader specializing in Polymarket crypto binary markets. "
            "You trade BTC/ETH/SOL 5-minute and 15-minute up/down binary contracts. "
            "Your edge is the 30-120 second information lag between Binance spot moves "
            "and Polymarket token repricing."
        )

        prompt = (
            f"Session: {session_name} just opened ({now_utc.strftime('%H:%M')} UTC)\n"
            f"Markets: {asset_text}\n"
            f"Context: {session_note}\n\n"
            f"Based on the current price levels and session characteristics, "
            f"what is the directional bias for BTC over the next 30-90 minutes? "
            f"Are there any structural reasons to be bullish or bearish?\n\n"
            f'Respond ONLY with JSON: {{"direction":"UP"or"DOWN"or"NEUTRAL","confidence":0.50-0.95,'
            f'"reasoning":"max 20 words"}}'
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
                "max_tokens": 100,
                "system": system_prompt,
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
                        return
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()
            if "```" in raw_text:
                for part in raw_text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        raw_text = part
                        break

            result = json.loads(raw_text)
            direction_str = result.get("direction", "NEUTRAL").upper()
            confidence = max(0.5, min(0.95, float(result.get("confidence", 0.6))))
            reasoning = str(result.get("reasoning", ""))

            logger.info(
                "SESSION BRIEF [%s %02d:00 UTC] → %s conf=%.2f | %s",
                session_name, hour, direction_str, confidence, reasoning,
            )

            # Only prime current_signal if Claude has real conviction (>0.65)
            # and a clear direction — don't bias signal on NEUTRAL
            if direction_str in ("UP", "DOWN") and confidence >= 0.65:
                self.current_signal = MacroSignal(
                    ts=time.time(),
                    direction=1 if direction_str == "UP" else -1,
                    confidence=confidence,
                    trigger_pct=0.0,
                    reasoning=f"[Session brief] {reasoning}",
                    trigger_type="session_brief",
                    valid_until=time.time() + SIGNAL_VALID_SECONDS * 3,  # 6-min validity
                )

        except Exception as exc:
            logger.debug("Session brief failed: %s", exc)
