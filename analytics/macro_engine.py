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
        # Per-token sniper eval cache: {token_id: (ts, "ENTER"/"SKIP", confidence, reason)}
        # Prevents re-querying Claude for the same opportunity every scan cycle.
        self._sniper_eval_cache: dict = {}
        self._sniper_eval_ttl: float = 45.0   # reuse cached decision for 45s
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

    async def evaluate_sniper_trade(
        self,
        token_id: str,
        asset: str,
        side: str,
        delta_pct: float,
        fair_value: float,
        token_ask: float,
        edge: float,
        elapsed_pct: float,
        window_seconds: int,
        vpin_score: Optional[float] = None,
        vpin_direction: Optional[int] = None,
    ) -> tuple:
        """
        Ask Claude whether to ENTER or SKIP a specific sniper trade.

        Unlike tick() (which asks "will BTC go up?"), this asks:
        "Given ALL the context of THIS trade — is the edge real and should we enter?"

        Uses full position context: timing, mispricing magnitude, order flow, urgency.
        Defaults to ENTER on any failure (non-blocking — never stops a valid trade).

        Returns: ("ENTER" | "SKIP", confidence: float, reason: str)
        """
        if not self._enabled:
            return ("ENTER", 0.5, "LLM disabled — defaulting ENTER")

        now = time.time()

        # Check cache: reuse recent decision for this token to avoid spam
        cached = self._sniper_eval_cache.get(token_id)
        if cached is not None:
            cache_ts, decision, conf, reason = cached
            if now - cache_ts < self._sniper_eval_ttl:
                logger.debug(
                    "SNIPER EVAL (cached) %s/%s → %s conf=%.2f | %s",
                    asset, side, decision, conf, reason,
                )
                return (decision, conf, reason)

        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour

        # Session context
        if hour in (8, 9):
            session_desc = "London open (08:00 UTC) — high liquidity, strong trend initiation"
        elif hour in (13, 14, 15):
            weekday = now_utc.weekday()
            day_note = ""
            if weekday == 3:
                day_note = " — Thursday: weekly US jobless claims at 13:30 UTC"
            elif weekday == 4:
                day_note = " — Friday: possible NFP"
            session_desc = f"NYSE open / US macro{day_note}"
        elif hour in (22, 23, 0):
            session_desc = "Asia open (23:00 UTC) — BTC-native liquidity"
        else:
            session_desc = f"quiet hours ({now_utc.strftime('%H:%M')} UTC) — lower liquidity, higher reversal rate"

        direction_word = "UP" if delta_pct > 0 else "DOWN"
        abs_delta = abs(delta_pct)
        remaining_seconds = int(window_seconds * (1.0 - elapsed_pct))

        vpin_line = ""
        if vpin_score is not None and vpin_score > 0:
            flow_word = "aggressive buying" if (vpin_direction or 0) > 0 else "aggressive selling"
            vpin_agrees = (
                (side == "YES" and (vpin_direction or 0) > 0)
                or (side == "NO" and (vpin_direction or 0) < 0)
            )
            agree_str = "AGREES with our trade" if vpin_agrees else "OPPOSES our trade"
            vpin_line = (
                f"- Binance VPIN (order flow toxicity): {vpin_score:.3f} — "
                f"{flow_word} ({agree_str})\n"
            )

        prompt = (
            f"You are a quantitative trader reviewing a live Polymarket trade opportunity.\n"
            f"Session: {session_desc}\n\n"
            f"Trade: BUY {asset} {side} token on Polymarket binary updown market\n"
            f"- Asset moved {direction_word} {abs_delta:.3f}% from window open\n"
            f"- Window elapsed: {elapsed_pct:.0%} ({remaining_seconds}s remaining in {window_seconds}s window)\n"
            f"- Fair value (sigmoid model): {fair_value:.3f} | Token ask: {token_ask:.3f} | Edge: {edge:+.3f}\n"
            f"{vpin_line}"
            f"\nKey context:\n"
            f"- Edge = (model fair value) - (current market price). Positive = token underpriced.\n"
            f"- This market resolves at the EXACT moment the window ends (T=0 snapshot).\n"
            f"- A {abs_delta:.3f}% move at {session_desc.split(' —')[0]} "
            f"{'typically sustains 65-70%' if hour in _HIGH_VOLUME_HOURS else 'reverses ~45% of the time during quiet hours'}.\n"
            f"- We need the token to finish above {token_ask:.3f} (our cost) to profit.\n\n"
            f"Should we ENTER this trade or SKIP it? Consider: edge quality, time remaining, "
            f"session strength, move magnitude, and reversal risk.\n\n"
            f'Respond ONLY with valid JSON: '
            f'{{"decision":"ENTER" or "SKIP","confidence":0.50-0.95,'
            f'"reasoning":"max 15 words"}}'
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

            async with aiohttp.ClientSession() as session_http:
                async with session_http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    if resp.status != 200:
                        logger.debug("SniperEval API %d — defaulting ENTER", resp.status)
                        return ("ENTER", 0.5, "API error — defaulting ENTER")
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()
            if "```" in raw_text:
                for part in raw_text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        raw_text = part
                        break

            result = json.loads(raw_text)
            decision = result.get("decision", "ENTER").upper()
            if decision not in ("ENTER", "SKIP"):
                decision = "ENTER"
            confidence = max(0.5, min(0.95, float(result.get("confidence", 0.6))))
            reason = str(result.get("reasoning", ""))[:120]

            # Cache the decision
            self._sniper_eval_cache[token_id] = (now, decision, confidence, reason)

            logger.info(
                "SNIPER EVAL %s/%s → %s conf=%.2f edge=%.3f elapsed=%.0f%% | %s",
                asset, side, decision, confidence, edge, elapsed_pct * 100, reason,
            )
            return (decision, confidence, reason)

        except Exception as exc:
            logger.debug("SniperEval Claude call failed: %s — defaulting ENTER", exc)
            return ("ENTER", 0.5, f"eval failed ({type(exc).__name__}) — defaulting ENTER")

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
