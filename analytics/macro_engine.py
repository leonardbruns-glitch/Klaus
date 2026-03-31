"""
Klaus — LLM Macro Engine

Uses Claude AI to interpret sudden BTC price moves during macro event windows
and generate directional trading signals for Polymarket updown markets.

Edge thesis:
  - At 13:30 UTC (CPI, NFP, PPI, jobless claims), BTC often moves sharply
  - Polymarket updown tokens reprice 30–120 seconds AFTER spot moves
  - Claude interprets whether the initial move is likely to sustain or fade
  - This generates a high-confidence directional boost for that 2-minute window

Architecture:
  - Monitors 13:25–13:45 UTC (macro event window)
  - Triggers when BTC moves ≥ TRIGGER_PCT in the last 60 seconds
  - Calls Claude Haiku (~0.3s response, ~$0.001/call) for interpretation
  - MacroSignal is valid for SIGNAL_VALID_SECONDS (120s)
  - 3-minute cooldown between triggers to avoid spam

Setup:
  Set ANTHROPIC_API_KEY in .env to enable. Engine silently disables if not set.
  Cost estimate: at most 20 calls/day if macro window fires every day = ~$0.02/day

Thursday special: weekly jobless claims at 13:30 UTC = most consistent edge.
Also fires on: CPI (monthly), NFP (first Friday), PPI (monthly), FOMC days.
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

# ── Configuration ─────────────────────────────────────────────────────────────
MACRO_WINDOW_HOUR = 13          # 13:xx UTC
MACRO_WINDOW_MIN_START = 25     # start watching at 13:25
MACRO_WINDOW_MIN_END = 45       # stop at 13:45
TRIGGER_PCT = 0.35              # BTC 1m move ≥ 0.35% = possible macro reaction
SIGNAL_VALID_SECONDS = 120      # signal expires after 2 minutes
COOLDOWN_SECONDS = 180          # 3 min between LLM calls (prevent spam)
PRICE_BASELINE_RESET_S = 90     # reset price baseline every 90s if no trigger


@dataclass
class MacroSignal:
    """
    Directional signal from LLM macro interpretation.
    direction: +1 = bullish (buy YES/UP token), -1 = bearish (buy NO/DOWN token)
    confidence: 0.5–0.95 (Claude's estimated probability the move sustains)
    """
    ts: float
    direction: int               # +1 = bullish, -1 = bearish
    confidence: float            # 0.5–0.95
    trigger_pct: float           # BTC % move that triggered this
    reasoning: str               # Claude's one-sentence explanation
    valid_until: float = 0.0

    def __post_init__(self) -> None:
        if self.valid_until == 0.0:
            self.valid_until = self.ts + SIGNAL_VALID_SECONDS

    def is_valid(self) -> bool:
        return time.time() < self.valid_until

    def boost_for_direction_yes(self) -> float:
        """
        Returns a float in [-0.12, +0.12] for adding to external_boost.
        Positive = supports BUY_YES, Negative = opposes BUY_YES.
        """
        if not self.is_valid():
            return 0.0
        # Scale: confidence 0.5 → 0 boost, 0.95 → 0.12 boost
        magnitude = (self.confidence - 0.5) / 0.45 * 0.12
        return magnitude * self.direction  # +1=YES, -1=NO


class MacroEngine:
    """
    LLM-powered macro event detector.
    Call tick(btc_price) every 5 seconds from the main scan loop.
    """

    def __init__(self) -> None:
        self.current_signal: Optional[MacroSignal] = None
        self._baseline_price: Optional[float] = None
        self._baseline_ts: float = 0.0
        self._last_trigger_ts: float = 0.0
        self._api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self._enabled: bool = bool(self._api_key)
        if not self._enabled:
            logger.info("MacroEngine disabled (ANTHROPIC_API_KEY not set) — set in .env to enable LLM macro signals")

    # ── Public interface ──────────────────────────────────────────────────────

    def get_signal(self) -> Optional[MacroSignal]:
        """Returns current valid MacroSignal, or None if expired/absent."""
        if self.current_signal and self.current_signal.is_valid():
            return self.current_signal
        return None

    async def tick(self, btc_price: Optional[float]) -> Optional[MacroSignal]:
        """
        Feed current BTC spot price. Returns a MacroSignal when LLM fires.
        Call every ~5 seconds from the scan loop.
        Safe to call when not in macro window — returns None immediately.
        """
        if not self._enabled:
            return None
        if not self._in_macro_window():
            # Reset baseline when window closes
            if self._baseline_price is not None:
                self._baseline_price = None
            return None
        if btc_price is None or btc_price <= 0:
            return None

        now = time.time()

        # Return existing valid signal (don't re-fire within validity window)
        if self.current_signal and self.current_signal.is_valid():
            return self.current_signal

        # Initialise baseline
        if self._baseline_price is None:
            self._baseline_price = btc_price
            self._baseline_ts = now
            return None

        # Enforce cooldown
        if now - self._last_trigger_ts < COOLDOWN_SECONDS:
            return None

        # Compute move vs baseline
        elapsed = now - self._baseline_ts
        pct_change = (btc_price - self._baseline_price) / self._baseline_price * 100

        # Refresh baseline periodically even if no trigger
        if elapsed > PRICE_BASELINE_RESET_S:
            self._baseline_price = btc_price
            self._baseline_ts = now

        # Check trigger threshold
        if abs(pct_change) < TRIGGER_PCT:
            return None

        # ── TRIGGER ──────────────────────────────────────────────────────────
        logger.info(
            "MacroEngine TRIGGER: BTC %+.3f%% in %.0fs at %s — querying Claude Haiku",
            pct_change, elapsed,
            datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        )
        self._last_trigger_ts = now
        self._baseline_price = btc_price
        self._baseline_ts = now

        signal = await self._query_claude(pct_change, btc_price, elapsed)
        if signal:
            self.current_signal = signal
            logger.info(
                "MacroEngine SIGNAL: %s conf=%.2f expires_in=%.0fs | %s",
                "BULLISH (+YES)" if signal.direction > 0 else "BEARISH (+NO)",
                signal.confidence,
                signal.valid_until - now,
                signal.reasoning[:120],
            )
        return signal

    # ── Internal ──────────────────────────────────────────────────────────────

    def _in_macro_window(self) -> bool:
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour != MACRO_WINDOW_HOUR:
            return False
        return MACRO_WINDOW_MIN_START <= now_utc.minute <= MACRO_WINDOW_MIN_END

    async def _query_claude(
        self, pct_change: float, btc_price: float, elapsed_s: float
    ) -> Optional[MacroSignal]:
        """
        Call Claude Haiku to interpret the BTC price move.
        Uses raw aiohttp (no anthropic SDK dependency).
        Response time: typically 300–800ms with Haiku.
        """
        direction_word = "UP" if pct_change > 0 else "DOWN"
        abs_pct = abs(pct_change)
        now_utc = datetime.now(timezone.utc)
        time_str = now_utc.strftime("%H:%M UTC")

        # Is today Thursday? Weekly jobless claims are the most consistent signal.
        weekday = now_utc.weekday()  # 0=Mon, 3=Thu, 4=Fri
        day_context = ""
        if weekday == 3:
            day_context = "Today is Thursday — very likely US weekly jobless claims data."
        elif weekday == 4:
            day_context = "Today is Friday — may be US NFP (Non-Farm Payrolls) if first Friday of month."
        else:
            day_context = "Possible CPI, PPI, or other US macro data release."

        move_context = (
            "small/ambiguous" if abs_pct < 0.3 else
            "moderate — consistent with macro surprise" if abs_pct < 0.8 else
            "large — significant macro shock"
        )

        prompt = (
            f"You are a quant trader specialised in crypto reaction to macro data.\n"
            f"BTC just moved {direction_word} {abs_pct:.3f}% (to ${btc_price:,.0f}) over {elapsed_s:.0f}s at {time_str}.\n"
            f"{day_context}\n"
            f"Move size assessment: {move_context}.\n\n"
            f"Will BTC continue this {direction_word} move for the next 2–5 minutes, "
            f"or fade back?\n"
            f"Context: initial macro reactions have ~75% continuation rate; "
            f"larger moves ({'>'}0.5%) tend to sustain; "
            f"moves during low-liquidity windows can be noise.\n\n"
            f'Respond ONLY with valid JSON (no markdown): '
            f'{{"direction":"UP" or "DOWN","confidence":0.50-0.95,"reasoning":"one sentence max 20 words"}}'
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
                "max_tokens": 120,
                "messages": [{"role": "user", "content": prompt}],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.debug("Claude API %d: %s", resp.status, body[:200])
                        return None
                    data = await resp.json()

            raw_text = data["content"][0]["text"].strip()

            # Strip markdown code fences if present
            if "```" in raw_text:
                parts = raw_text.split("```")
                # pick the part that looks like JSON
                for part in parts:
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        raw_text = part
                        break

            result = json.loads(raw_text)
            direction_str = result.get("direction", "").upper()
            direction = 1 if direction_str == "UP" else -1
            confidence = float(result.get("confidence", 0.6))
            confidence = max(0.5, min(0.95, confidence))
            reasoning = str(result.get("reasoning", ""))

            return MacroSignal(
                ts=time.time(),
                direction=direction,
                confidence=confidence,
                trigger_pct=pct_change,
                reasoning=reasoning,
            )

        except json.JSONDecodeError as exc:
            logger.debug("MacroEngine JSON parse error: %s | raw=%s", exc, raw_text[:200] if 'raw_text' in dir() else "?")
            return None
        except Exception as exc:
            logger.debug("MacroEngine Claude call failed: %s", exc)
            return None
