"""
Taker sniper strategy layer for experimental V2.

Flow:
    WS price_changes → BookState (per token) → EMA fair price
    → SniperSignal when ask < fair * (1 - threshold)
    → TakerOrderBuilder → pre_flight_check → POST /order

This module is credential-free. Order building and submission
are handled in main.py so credentials stay in one place.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("strategy")

# ── Strategy parameters ───────────────────────────────────────────────────────

SNIPE_THRESHOLD  = 0.01   # trigger when ask < fair * (1 - 0.01)
MAX_SNIPE_USDC   = 10.0   # max spend per snipe on experimental branch
EMA_ALPHA        = 0.15   # higher = more responsive; lower = smoother
EMA_WARMUP       = 10     # minimum mid-price samples before sniping
MIN_SIZE_USDC    = 1.0    # ignore asks too small to be worth chasing


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SniperSignal:
    token_id:    str
    side:        str    # always "BUY" — we're buying the underpriced token
    price:       float  # the ask price we intend to take
    size_usdc:   float  # USDC to spend (≤ MAX_SNIPE_USDC)
    fair_price:  float  # EMA estimate at signal time
    discount_pct: float  # (fair - price) / fair, e.g. 0.015 = 1.5% discount
    ts:          float  # monotonic timestamp for latency tracking


@dataclass
class _BookSide:
    best:   Optional[float]         = None
    levels: dict[float, float]      = field(default_factory=dict)

    def update(self, price: float, size: float) -> None:
        if size == 0.0:
            self.levels.pop(price, None)
        else:
            self.levels[price] = size
        self.best = min(self.levels) if self.levels else None

    def set_best(self, price: float) -> None:
        """Fast path: set best from the WS best_bid/best_ask hint."""
        self.best = price


class _TokenBook:
    """Bid + ask book state plus EMA fair price for a single token."""

    def __init__(self, token_id: str) -> None:
        self.token_id = token_id
        self.bids     = _BookSide()
        self.asks     = _BookSide()
        self._ema:    Optional[float] = None
        self._n:      int = 0

    # ── Book updates ─────────────────────────────────────────────────────────

    def on_buy_update(self, price: float, size: float, best_bid: Optional[float]) -> None:
        """BUY-side price_changes event — updates bid book."""
        self.bids.update(price, size)
        if best_bid is not None:
            self.bids.set_best(best_bid)
        self._tick_ema()

    def on_sell_update(self, price: float, size: float) -> None:
        """SELL-side price_changes event — updates ask book."""
        self.asks.update(price, size)
        self._tick_ema()

    def _tick_ema(self) -> None:
        mid = self.mid
        if mid is None:
            return
        if self._ema is None:
            self._ema = mid
        else:
            self._ema = EMA_ALPHA * mid + (1 - EMA_ALPHA) * self._ema
        self._n += 1

    # ── Derived values ────────────────────────────────────────────────────────

    @property
    def mid(self) -> Optional[float]:
        b, a = self.bids.best, self.asks.best
        if b and a and b < a:
            return (b + a) / 2
        if b:  # no ask yet — use bid as proxy during warm-up
            return b
        return None

    @property
    def fair_price(self) -> Optional[float]:
        return self._ema if self._n >= EMA_WARMUP else None

    @property
    def warmed_up(self) -> bool:
        return self._n >= EMA_WARMUP

    def __repr__(self) -> str:
        return (
            f"Book({self.token_id[:8]}… "
            f"bid={self.bids.best} ask={self.asks.best} "
            f"fair={self._ema:.4f} n={self._n})"
            if self._ema else f"Book({self.token_id[:8]}… warming {self._n}/{EMA_WARMUP})"
        )


# ── Strategy layer ────────────────────────────────────────────────────────────

class StrategyLayer:
    """
    Maintains per-token order book state and emits SniperSignals.

    Usage:
        strategy = StrategyLayer()
        for signal in strategy.process(ws_event):
            await execute_snipe(signal)
    """

    def __init__(
        self,
        snipe_threshold: float = SNIPE_THRESHOLD,
        max_usdc:        float = MAX_SNIPE_USDC,
    ) -> None:
        self.snipe_threshold = snipe_threshold
        self.max_usdc        = max_usdc
        self._books: dict[str, _TokenBook] = {}

    def _book(self, token_id: str) -> _TokenBook:
        if token_id not in self._books:
            self._books[token_id] = _TokenBook(token_id)
        return self._books[token_id]

    def process(self, event: dict) -> list[SniperSignal]:
        """
        Process one price_changes WS event.

        Event shape from Polymarket market channel:
        {
            "market": "0x...",
            "price_changes": [{
                "asset_id": "<token_id>",
                "price":    "0.107",    # price level being updated
                "size":     "53.32",    # new size at level (0 = removed)
                "side":     "BUY",      # BUY = bid side, SELL = ask side
                "best_bid": "0.107",    # current best bid (BUY updates only)
                "hash":     "..."
            }]
        }
        """
        signals: list[SniperSignal] = []
        now = time.monotonic()

        for change in event.get("price_changes", []):
            token_id = str(change.get("asset_id", ""))
            side     = change.get("side", "")
            if not token_id or side not in ("BUY", "SELL"):
                continue

            try:
                price = float(change["price"])
                size  = float(change.get("size", 0))
            except (KeyError, ValueError):
                continue

            best_bid_raw = change.get("best_bid")
            best_bid = float(best_bid_raw) if best_bid_raw else None

            book = self._book(token_id)

            if side == "BUY":
                book.on_buy_update(price, size, best_bid)

            elif side == "SELL":
                book.on_sell_update(price, size)

                # ── Snipe check ───────────────────────────────────────────
                # Condition: someone is offering to sell at price below our
                # EMA fair value by more than snipe_threshold.
                if size == 0:
                    continue  # level removed, nothing to take

                size_usdc = size * price
                if size_usdc < MIN_SIZE_USDC:
                    continue  # too thin to bother

                fair = book.fair_price
                if fair is None:
                    continue  # EMA still warming up

                if price >= fair * (1 - self.snipe_threshold):
                    continue  # not cheap enough

                # Signal — cap size to max_usdc
                snipe_usdc  = min(size_usdc, self.max_usdc)
                discount    = (fair - price) / fair

                sig = SniperSignal(
                    token_id    = token_id,
                    side        = "BUY",
                    price       = price,
                    size_usdc   = round(snipe_usdc, 2),
                    fair_price  = round(fair, 5),
                    discount_pct = round(discount, 4),
                    ts          = now,
                )
                signals.append(sig)
                log.info(
                    "SNIPE SIGNAL | token=%s… | ask=%.4f | fair=%.4f | "
                    "discount=%.2f%% | size=$%.2f",
                    token_id[:12], price, fair, discount * 100, snipe_usdc,
                )

        return signals

    def book_summary(self) -> str:
        lines = [repr(b) for b in self._books.values()]
        return "\n".join(lines) if lines else "(no books yet)"
