"""
Klaus — Data Feeds
Pulls live Polymarket CLOB data: order books, price bars, and optional signals.
All data is normalised into typed dataclasses before reaching strategy logic.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import logging

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from config import CONFIG

logger = logging.getLogger("feeds")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    """One OHLCV candle (primary = 5-min, secondary = 15-min)."""
    ts: float           # unix timestamp of bar open
    open: float
    high: float
    low: float
    close: float
    volume: float       # notional traded (sum of fill sizes)


@dataclass
class OrderBook:
    """Snapshot of the Polymarket order book for one token."""
    ts: float
    token_id: str
    asset: str          # e.g. "BTC"
    side: str           # "YES" or "NO"
    bids: List[Tuple[float, float]]   # [(price, size), ...] best first
    asks: List[Tuple[float, float]]
    mid: float = 0.0
    spread: float = 0.0
    bid_depth: float = 0.0   # total $ on best 5 bid levels
    ask_depth: float = 0.0
    imbalance: float = 0.5   # bid / (bid + ask) depth; > 0.6 = bullish

    def __post_init__(self) -> None:
        if self.bids and self.asks:
            best_bid = self.bids[0][0]
            best_ask = self.asks[0][0]
            self.mid = (best_bid + best_ask) / 2
            self.spread = best_ask - best_bid
        depth_levels = 5
        self.bid_depth = sum(p * s for p, s in self.bids[:depth_levels])
        self.ask_depth = sum(p * s for p, s in self.asks[:depth_levels])
        total = self.bid_depth + self.ask_depth
        self.imbalance = self.bid_depth / total if total > 0 else 0.5


@dataclass
class MarketToken:
    """A tradeable binary token on Polymarket."""
    token_id: str
    condition_id: str
    asset: str          # BTC / ETH / SOL
    side: str           # YES / NO
    question: str
    end_date_iso: str
    active: bool = True


@dataclass
class ExternalSignal:
    """Optional external data (funding rate, spot momentum, etc.)."""
    ts: float
    asset: str
    funding_rate: Optional[float] = None     # annualised perp funding
    spot_momentum_5m: Optional[float] = None # % change on spot last 5 min
    spot_momentum_15m: Optional[float] = None
    realized_vol_1h: Optional[float] = None  # annualised


# ---------------------------------------------------------------------------
# Rolling bar builder
# ---------------------------------------------------------------------------

class BarBuilder:
    """Aggregates tick-level trade data into fixed-interval OHLCV bars."""

    def __init__(self, interval: int, max_bars: int) -> None:
        self.interval = interval
        self.bars: deque[Bar] = deque(maxlen=max_bars)
        self._current: Optional[Bar] = None

    def update(self, price: float, size: float, ts: float) -> Optional[Bar]:
        """Feed a trade tick; returns a completed bar when the interval closes."""
        bar_open_ts = (ts // self.interval) * self.interval
        completed = None

        if self._current is None:
            self._current = Bar(bar_open_ts, price, price, price, price, size)
        elif bar_open_ts > self._current.ts:
            completed = self._current
            self.bars.append(completed)
            self._current = Bar(bar_open_ts, price, price, price, price, size)
        else:
            c = self._current
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price
            c.volume += size

        return completed

    def close_bar_now(self, ts: float) -> Optional[Bar]:
        """Force-close the current bar (e.g. on flush)."""
        if self._current:
            self._current.close = self._current.close
            self.bars.append(self._current)
            closed = self._current
            self._current = None
            return closed
        return None

    def get_bars(self, n: int) -> List[Bar]:
        return list(self.bars)[-n:]


# ---------------------------------------------------------------------------
# Polymarket CLOB client
# ---------------------------------------------------------------------------

class PolymarketFeed:
    """
    Async interface to Polymarket CLOB API.
    Handles: token discovery, order book polling, trade stream simulation.

    Docs: https://docs.polymarket.com  (CLOB v2)
    """

    CLOB = CONFIG.markets.clob_api_url
    GAMMA = CONFIG.markets.gamma_api_url

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self.tokens: Dict[str, MarketToken] = {}        # token_id → token
        self.asset_tokens: Dict[str, List[str]] = {}    # asset → [token_ids]
        self.order_books: Dict[str, OrderBook] = {}     # token_id → latest OB
        self.bar_builders_5m: Dict[str, BarBuilder] = {}
        self.bar_builders_15m: Dict[str, BarBuilder] = {}
        self._running = False
        self._last_ob_ts: Dict[str, float] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not AIOHTTP_AVAILABLE:
            logger.warning("aiohttp not installed — feed running in stub mode")
            self._running = True
            self._populate_stub_tokens()
            await self._warmup_stub_bars()
            return
        self._session = aiohttp.ClientSession(
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10),
        )
        self._running = True
        await self._discover_markets()
        logger.info("Feed started; tracking %d tokens", len(self.tokens))

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()

    # ── Market discovery ─────────────────────────────────────────────────────

    async def _discover_markets(self) -> None:
        """Fetch active markets from Gamma API and filter to tracked assets."""
        if not self._session:
            return
        tracked = CONFIG.markets.tracked_assets
        url = f"{self.GAMMA}/markets"
        params = {"active": "true", "closed": "false", "limit": 500}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error("Gamma API error %s", resp.status)
                    return
                markets = await resp.json()
        except Exception as exc:
            logger.error("Market discovery failed: %s", exc)
            return

        for market in markets:
            question = market.get("question", "")
            # Rough filter: keep only daily/weekly price resolution markets
            asset_match = next(
                (a for a in tracked if a.upper() in question.upper()), None
            )
            if not asset_match:
                continue
            tokens_data = market.get("tokens", [])
            for t in tokens_data:
                token_id = t.get("token_id", "")
                if not token_id:
                    continue
                side = "YES" if t.get("outcome", "").upper() == "YES" else "NO"
                token = MarketToken(
                    token_id=token_id,
                    condition_id=market.get("condition_id", ""),
                    asset=asset_match,
                    side=side,
                    question=question,
                    end_date_iso=market.get("end_date_iso", ""),
                    active=market.get("active", True),
                )
                self.tokens[token_id] = token
                self.asset_tokens.setdefault(asset_match, []).append(token_id)
                self.bar_builders_5m[token_id] = BarBuilder(
                    CONFIG.markets.bar_interval_primary,
                    CONFIG.markets.history_bars,
                )
                self.bar_builders_15m[token_id] = BarBuilder(
                    CONFIG.markets.bar_interval_secondary,
                    CONFIG.markets.history_bars,
                )

        logger.info("Discovered %d tokens across %s", len(self.tokens), tracked)

    # ── Order book polling ────────────────────────────────────────────────────

    async def fetch_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Fetch and parse CLOB order book for one token."""
        if not self._session:
            return self._stub_order_book(token_id)
        url = f"{self.CLOB}/book"
        params = {"token_id": token_id}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception as exc:
            logger.debug("OB fetch error %s: %s", token_id[:8], exc)
            return None

        token = self.tokens.get(token_id)
        asset = token.asset if token else "UNKNOWN"
        side = token.side if token else "UNKNOWN"

        def parse_levels(raw: list) -> List[Tuple[float, float]]:
            return sorted(
                [(float(lvl["price"]), float(lvl["size"])) for lvl in raw],
                key=lambda x: x[0],
                reverse=True,
            )

        bids = parse_levels(data.get("bids", []))
        asks = parse_levels(data.get("asks", []))
        # asks should be ascending; re-sort
        asks = sorted(asks, key=lambda x: x[0])

        ob = OrderBook(
            ts=time.time(),
            token_id=token_id,
            asset=asset,
            side=side,
            bids=bids,
            asks=asks,
        )
        self.order_books[token_id] = ob
        self._last_ob_ts[token_id] = ob.ts
        return ob

    async def poll_order_books(self) -> None:
        """Poll all tracked tokens; respects scan interval."""
        tasks = [self.fetch_order_book(tid) for tid in self.tokens]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── Price bar updates from last trade ────────────────────────────────────

    async def fetch_last_trade(self, token_id: str) -> Optional[Tuple[float, float]]:
        """Returns (price, size) of the most recent trade, or None."""
        if not self._session:
            return None
        url = f"{self.CLOB}/last-trade-price"
        params = {"token_id": token_id}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                price = float(data.get("price", 0))
                size = float(data.get("size", 0))
                return price, size
        except Exception:
            return None

    async def update_bars(self) -> None:
        """Push latest trade into bar builders for all tokens."""
        import random
        now = time.time()
        for token_id in list(self.tokens.keys()):
            result = await self.fetch_last_trade(token_id)
            if result:
                price, size = result
            elif not self._session:
                # Stub mode: derive tick from current OB mid with small walk
                ob = self.order_books.get(token_id)
                if ob is None:
                    continue
                price = max(0.01, min(0.99, ob.mid + random.gauss(0, 0.004)))
                size = random.uniform(50, 500)
            else:
                continue
            self.bar_builders_5m[token_id].update(price, size, now)
            self.bar_builders_15m[token_id].update(price, size, now)

    # ── External signals ─────────────────────────────────────────────────────

    async def fetch_external_signals(self, asset: str) -> Optional[ExternalSignal]:
        """
        Fetch optional external signals: perp funding rate, spot momentum.
        Source: Binance public API (no auth required).
        Only applied if they improve edge; never blocks a high-edge trade.
        """
        if not self._session:
            return None
        symbol_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
        symbol = symbol_map.get(asset.upper())
        if not symbol:
            return None

        signal = ExternalSignal(ts=time.time(), asset=asset)

        # Funding rate (Binance perp)
        try:
            url = "https://fapi.binance.com/fapi/v1/premiumIndex"
            async with self._session.get(url, params={"symbol": symbol}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    signal.funding_rate = float(data.get("lastFundingRate", 0)) * 365 * 100
        except Exception:
            pass  # signal is optional; never blocks trade

        # Spot klines for momentum
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": symbol, "interval": "5m", "limit": 4}
            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    klines = await resp.json()
                    if len(klines) >= 2:
                        c1 = float(klines[-2][4])  # prev close
                        c0 = float(klines[-1][4])  # last close
                        signal.spot_momentum_5m = (c0 - c1) / c1 * 100
            params["interval"] = "15m"
            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    klines = await resp.json()
                    if len(klines) >= 2:
                        c1 = float(klines[-2][4])
                        c0 = float(klines[-1][4])
                        signal.spot_momentum_15m = (c0 - c1) / c1 * 100
        except Exception:
            pass

        return signal

    # ── Convenience accessors ─────────────────────────────────────────────────

    def get_bars_5m(self, token_id: str, n: int = 20) -> List[Bar]:
        builder = self.bar_builders_5m.get(token_id)
        return builder.get_bars(n) if builder else []

    def get_bars_15m(self, token_id: str, n: int = 20) -> List[Bar]:
        builder = self.bar_builders_15m.get(token_id)
        return builder.get_bars(n) if builder else []

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        return self.order_books.get(token_id)

    # ── Stub helpers (dry-run / no-network mode) ──────────────────────────────

    def _populate_stub_tokens(self) -> None:
        """Create synthetic YES+NO tokens for each tracked asset."""
        import uuid
        for asset in CONFIG.markets.tracked_assets:
            for side in ("YES", "NO"):
                token_id = f"stub_{asset}_{side}_{uuid.uuid4().hex[:8]}"
                token = MarketToken(
                    token_id=token_id,
                    condition_id=f"stub_cond_{asset}",
                    asset=asset,
                    side=side,
                    question=f"Will {asset} be above threshold on expiry?",
                    end_date_iso="2099-12-31T00:00:00Z",
                    active=True,
                )
                self.tokens[token_id] = token
                self.asset_tokens.setdefault(asset, []).append(token_id)
                self.bar_builders_5m[token_id] = BarBuilder(
                    CONFIG.markets.bar_interval_primary,
                    CONFIG.markets.history_bars,
                )
                self.bar_builders_15m[token_id] = BarBuilder(
                    CONFIG.markets.bar_interval_secondary,
                    CONFIG.markets.history_bars,
                )
        logger.info("Stub mode: created %d synthetic tokens", len(self.tokens))

    async def _warmup_stub_bars(self) -> None:
        """
        Seed bar builders with 50 synthetic bars so the strategy has history.
        Simulates realistic binary market price walk with occasional momentum bursts.
        """
        import random
        import math
        now = time.time()
        interval_5m = CONFIG.markets.bar_interval_primary
        n_bars = CONFIG.markets.history_bars

        for token_id, token in self.tokens.items():
            # Each asset starts at a different base probability
            base = {"BTC": 0.42, "ETH": 0.38, "SOL": 0.28}.get(token.asset, 0.35)
            if token.side == "NO":
                base = 1.0 - base

            price = base
            for i in range(n_bars):
                bar_ts = now - (n_bars - i) * interval_5m
                # Random walk with mean reversion + occasional momentum burst
                drift = random.gauss(0, 0.012)
                # Mean reversion toward 0.5
                drift += (0.5 - price) * 0.03
                # Momentum burst (20% chance)
                if random.random() < 0.20:
                    drift += random.choice([-1, 1]) * random.uniform(0.02, 0.05)

                price = max(0.05, min(0.95, price + drift))
                spread = random.uniform(0.005, 0.018)
                high = min(0.99, price + random.uniform(0, spread * 2))
                low = max(0.01, price - random.uniform(0, spread * 2))
                volume = random.uniform(200, 3000)
                # Volume spike on momentum bars
                if abs(drift) > 0.025:
                    volume *= random.uniform(1.5, 3.0)

                # Push open + intermediate ticks into bar builders
                for p, v, offset in [
                    (price - drift, volume * 0.25, 0),
                    (low,           volume * 0.25, interval_5m * 0.3),
                    (high,          volume * 0.25, interval_5m * 0.6),
                    (price,         volume * 0.25, interval_5m * 0.9),
                ]:
                    self.bar_builders_5m[token_id].update(p, v, bar_ts + offset)
                    self.bar_builders_15m[token_id].update(p, v, bar_ts + offset)

            # Seed initial order book from final price
            self.order_books[token_id] = self._make_stub_order_book(
                token_id, price
            )

        logger.info("Stub warmup complete: %d bars seeded per token", n_bars)

    def _make_stub_order_book(self, token_id: str, mid: float) -> OrderBook:
        """Build a realistic stub order book around a given mid price."""
        import random
        token = self.tokens.get(token_id)
        spread = random.uniform(0.005, 0.015)
        bids = [
            (round(max(0.01, mid - spread * (i + 1)), 4),
             round(random.uniform(100, 800), 2))
            for i in range(5)
        ]
        asks = [
            (round(min(0.99, mid + spread * (i + 1)), 4),
             round(random.uniform(100, 800), 2))
            for i in range(5)
        ]
        # Occasionally skew depth to trigger OB imbalance signal
        if random.random() < 0.35:
            scale = random.uniform(1.5, 2.5)
            if random.random() < 0.5:
                bids = [(p, round(s * scale, 2)) for p, s in bids]
            else:
                asks = [(p, round(s * scale, 2)) for p, s in asks]
        return OrderBook(
            ts=time.time(),
            token_id=token_id,
            asset=token.asset if token else "BTC",
            side=token.side if token else "YES",
            bids=bids,
            asks=asks,
        )

    def _stub_order_book(self, token_id: str) -> OrderBook:
        """Refresh stub order book with a small random walk from last mid."""
        import random
        existing = self.order_books.get(token_id)
        last_mid = existing.mid if existing else 0.35
        drift = random.gauss(0, 0.008)
        new_mid = max(0.05, min(0.95, last_mid + drift))
        ob = self._make_stub_order_book(token_id, new_mid)
        self.order_books[token_id] = ob
        return ob
