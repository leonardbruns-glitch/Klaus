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
        now = time.time()
        for token_id in list(self.tokens.keys()):
            result = await self.fetch_last_trade(token_id)
            if result:
                price, size = result
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

    def _stub_order_book(self, token_id: str) -> OrderBook:
        """Returns a synthetic order book for testing without network."""
        import random
        mid = random.uniform(0.20, 0.80)
        spread = random.uniform(0.005, 0.02)
        bids = [(round(mid - spread * (i + 1), 4), round(random.uniform(50, 500), 2))
                for i in range(5)]
        asks = [(round(mid + spread * (i + 1), 4), round(random.uniform(50, 500), 2))
                for i in range(5)]
        token = self.tokens.get(token_id)
        return OrderBook(
            ts=time.time(),
            token_id=token_id,
            asset=token.asset if token else "BTC",
            side=token.side if token else "YES",
            bids=bids,
            asks=asks,
        )
