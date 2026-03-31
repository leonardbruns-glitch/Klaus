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
# Asset name aliases (module-level — reused across discovery, RTDS, and stubs)
# Polymarket uses full names in slugs/questions; Chainlink oracle may send either.
# ---------------------------------------------------------------------------
_SLUG_ALIASES: Dict[str, List[str]] = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}
_QUESTION_ALIASES: Dict[str, List[str]] = {
    "BTC": ["BTC", "Bitcoin", "BITCOIN"],
    "ETH": ["ETH", "Ethereum", "ETHEREUM"],
    "SOL": ["SOL", "Solana", "SOLANA"],
}


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
    side: str           # YES / NO  (UP maps to YES, DOWN maps to NO)
    question: str
    end_date_iso: str
    active: bool = True
    market_type: str = "target"     # "updown" (5M/15M) or "target" (price target)
    window_end_ts: float = 0.0      # unix ts when this market resolves
    window_seconds: int = 300       # window duration: 300 (5M) or 900 (15M)
    neg_risk: bool = False          # True for multi-outcome (neg-risk) markets
    tick_size: str = "0.01"         # CLOB order price tick size per market


@dataclass
class ExternalSignal:
    """Optional external data (funding rate, spot momentum, VPIN, macro)."""
    ts: float
    asset: str
    funding_rate: Optional[float] = None     # annualised perp funding
    spot_momentum_5m: Optional[float] = None # % change on spot last 5 min
    spot_momentum_15m: Optional[float] = None
    realized_vol_1h: Optional[float] = None  # annualised
    spot_price: Optional[float] = None       # current Binance spot price (absolute)
    spot_momentum_1m: Optional[float] = None # % change on spot last 1 min
    # VPIN (Volume-Synchronized Probability of Informed Trading)
    # Measures order flow toxicity from Binance aggTrade stream.
    # vpin_score: 0-1 (0.5=neutral, >0.60=elevated toxicity → big move imminent)
    # vpin_direction: +1=buy-dominant, -1=sell-dominant (sign of recent imbalance)
    vpin_score: Optional[float] = None
    vpin_direction: Optional[int] = None
    # LLM macro signal: signed confidence in [−0.12, +0.12]
    # Positive = bullish (BUY_YES), Negative = bearish (BUY_NO)
    macro_boost: Optional[float] = None
    # Window open prices (Binance candle open = asset price at window start)
    # Used by WindowSniper to compute delta from window open → fair value
    spot_window_open_5m: Optional[float] = None   # Binance price at 5M window open
    spot_window_open_15m: Optional[float] = None  # Binance price at 15M window open


# ---------------------------------------------------------------------------
# VPIN — Volume-Synchronized Probability of Informed Trading
# ---------------------------------------------------------------------------

class VPINTracker:
    """
    Computes VPIN from Binance aggTrade stream using volume buckets.

    Algorithm (Easley, López de Prado, O'Hara 2010):
      1. Accumulate notional volume into equal-sized buckets
      2. Within each bucket, classify trades as BUY (m=False) or SELL (m=True)
      3. VPIN = rolling mean of |buy_vol - sell_vol| / total_vol over N buckets
      4. VPIN direction = sign of recent imbalance sum

    Thresholds (crypto-calibrated):
      VPIN > 0.60 → elevated toxicity, directional move likely
      VPIN > 0.70 → extreme — strong move loading
      Direction +1 = buy-dominated (bullish), -1 = sell-dominated (bearish)

    Bucket size $2M chosen so buckets close every ~30-90s on BTC futures,
    giving a 50-bucket window of ~25-75 minutes of market microstructure.
    """

    BUCKET_USD = 2_000_000   # $2M notional per bucket
    N_BUCKETS = 50           # rolling 50-bucket window

    def __init__(self) -> None:
        from collections import deque
        self._buy_vol: float = 0.0
        self._sell_vol: float = 0.0
        self._total_vol: float = 0.0
        self._imbalances: deque = deque(maxlen=self.N_BUCKETS)  # signed imbalances
        self.vpin: float = 0.5        # neutral start
        self.direction: int = 0       # 0=unknown, +1=bullish, -1=bearish
        self._trade_count: int = 0    # trades processed (for startup diagnostics)

    def update(self, price: float, qty: float, is_buyer_maker: bool) -> None:
        """
        Feed one aggTrade event.
        is_buyer_maker=True  → seller was aggressor (SELL market order) → sell pressure
        is_buyer_maker=False → buyer was aggressor (BUY market order)  → buy pressure
        """
        notional = price * qty
        if is_buyer_maker:
            self._sell_vol += notional
        else:
            self._buy_vol += notional
        self._total_vol += notional
        self._trade_count += 1

        if self._total_vol >= self.BUCKET_USD:
            total = self._buy_vol + self._sell_vol
            if total > 1e-9:
                signed_imb = (self._buy_vol - self._sell_vol) / total
                self._imbalances.append(signed_imb)

            # Recompute VPIN + direction
            if self._imbalances:
                self.vpin = sum(abs(b) for b in self._imbalances) / len(self._imbalances)
                avg_imb = sum(self._imbalances) / len(self._imbalances)
                self.direction = 1 if avg_imb > 0.05 else (-1 if avg_imb < -0.05 else 0)

            # Reset bucket
            self._buy_vol = 0.0
            self._sell_vol = 0.0
            self._total_vol = 0.0


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

    def seed(self, bars: List[Bar]) -> None:
        """Prepopulate from historical data (e.g. on startup warmup)."""
        for b in bars:
            self.bars.append(b)

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

    # WebSocket endpoints
    CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    RTDS_WS = "wss://ws-live-data.polymarket.com"
    BINANCE_WS = "wss://fstream.binance.com/ws"

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self.tokens: Dict[str, MarketToken] = {}        # token_id → token
        self.asset_tokens: Dict[str, List[str]] = {}    # asset → [token_ids]
        self.order_books: Dict[str, OrderBook] = {}     # token_id → latest OB
        self.bar_builders_5m: Dict[str, BarBuilder] = {}
        self.bar_builders_15m: Dict[str, BarBuilder] = {}
        self._running = False
        self._stub_mode = False   # True when using synthetic data (live discovery failed)
        self._last_ob_ts: Dict[str, float] = {}
        self._last_discovery_ts: float = 0.0    # for periodic re-discovery
        # WebSocket live data
        self.oracle_prices: Dict[str, float] = {}       # asset → Chainlink oracle price
        self.funding_rates: Dict[str, float] = {}       # asset → annualised funding rate
        self._ws_tasks: List[asyncio.Task] = []
        self._ws_ob_ts: Dict[str, float] = {}           # token_id → last WS OB update ts
        # Queue for sending new token subscriptions to the running CLOB WS.
        # refresh_markets() puts new token_id lists here; _run_clob_ws() drains it.
        self._clob_ws_sub_queue: asyncio.Queue = asyncio.Queue()
        # VPIN trackers per asset (fed from Binance aggTrade WebSocket)
        self.vpin_trackers: Dict[str, VPINTracker] = {
            "BTC": VPINTracker(),
            "ETH": VPINTracker(),
            "SOL": VPINTracker(),
        }
        # Binance spot kline cache — populated by _run_binance_kline_ws()
        # Replaces REST kline polling in fetch_external_signals() (saves 150-450ms/scan)
        self._spot_price: Dict[str, float] = {}       # asset → latest 1m close
        self._spot_prev_1m: Dict[str, float] = {}     # asset → last CLOSED 1m close
        self._spot_prev_5m: Dict[str, float] = {}     # asset → last CLOSED 5m close
        self._spot_prev_15m: Dict[str, float] = {}    # asset → last CLOSED 15m close
        self._spot_open_5m: Dict[str, float] = {}     # asset → current 5m candle open
        self._spot_open_15m: Dict[str, float] = {}    # asset → current 15m candle open
        self._kline_ts: Dict[str, float] = {}         # asset → last kline update ts

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not AIOHTTP_AVAILABLE:
            logger.warning("aiohttp not installed — feed running in stub mode")
            self._running = True
            self._stub_mode = True
            self._populate_stub_tokens()
            await self._warmup_stub_bars()
            return
        import ssl
        # macOS Python installers ship without system CA certs; use certifi if
        # available, otherwise disable verification (safe for known Polymarket hosts)
        try:
            import certifi
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10),
        )
        self._running = True
        self._last_discovery_ts = time.time()   # prevent double-discovery on first poll
        await self._discover_markets()

        # If live discovery returned nothing (network issue, SSL, etc.) fall back
        # to synthetic stub data so the bot can still run and generate feedback
        if not self.tokens:
            logger.warning(
                "No live tokens discovered — falling back to stub simulation mode"
            )
            self._stub_mode = True
            self._populate_stub_tokens()
            await self._warmup_stub_bars()
        else:
            # Seed bar history from CLOB prices-history so scoring starts immediately
            await self._warmup_live_bars()
            # Launch WebSocket subscriptions for real-time data
            self._ws_tasks = [
                asyncio.create_task(self._run_clob_ws()),
                asyncio.create_task(self._run_rtds_ws()),
                asyncio.create_task(self._run_binance_ws()),
                asyncio.create_task(self._run_binance_kline_ws()),
            ]

        logger.info("Feed started; tracking %d tokens", len(self.tokens))

    async def stop(self) -> None:
        self._running = False
        for t in self._ws_tasks:
            t.cancel()
        self._ws_tasks.clear()
        if self._session:
            await self._session.close()

    # ── WebSocket feeds ───────────────────────────────────────────────────────

    async def _run_clob_ws(self) -> None:
        """
        Subscribe to Polymarket CLOB WebSocket for real-time order book updates.
        Uses custom_feature_enabled=True to get best_bid_ask push events
        (fires only on BBO change, lower noise than full book stream).
        Reconnects automatically on disconnect. PING every 10s required.
        """
        import json as _json
        _PING_INTERVAL = 9.0  # slightly under 10s CLOB timeout

        while self._running:
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    _ssl_ctx = _ssl.create_default_context()
                    _ssl_ctx.check_hostname = False
                    _ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as ws_session:
                    async with ws_session.ws_connect(
                        self.CLOB_WS, ssl=_ssl_ctx, heartbeat=_PING_INTERVAL
                    ) as ws:
                        # Subscribe to all currently tracked tokens
                        token_ids = list(self.tokens.keys())
                        subscribed: set = set(token_ids)
                        await ws.send_str(_json.dumps({
                            "auth": {},
                            "type": "subscribe",
                            "channel": "market",
                            "assets_ids": token_ids,
                            "custom_feature_enabled": True,
                        }))
                        logger.info("CLOB WebSocket: subscribed to %d tokens", len(token_ids))

                        # Use wait_for loop instead of async-for so we can drain
                        # the re-subscription queue between messages.
                        # refresh_markets() puts newly discovered token IDs into
                        # _clob_ws_sub_queue; we subscribe them here within 2s.
                        while self._running:
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                            except asyncio.TimeoutError:
                                # No message — drain pending subscriptions
                                while not self._clob_ws_sub_queue.empty():
                                    new_ids = self._clob_ws_sub_queue.get_nowait()
                                    truly_new = [i for i in new_ids if i not in subscribed]
                                    if truly_new:
                                        await ws.send_str(_json.dumps({
                                            "auth": {},
                                            "type": "subscribe",
                                            "channel": "market",
                                            "assets_ids": truly_new,
                                            "custom_feature_enabled": True,
                                        }))
                                        subscribed.update(truly_new)
                                        logger.info(
                                            "CLOB WebSocket: re-subscribed to %d new tokens "
                                            "(%d total)", len(truly_new), len(subscribed),
                                        )
                                continue

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                # Also drain sub queue after each message (low-traffic periods)
                                while not self._clob_ws_sub_queue.empty():
                                    new_ids = self._clob_ws_sub_queue.get_nowait()
                                    truly_new = [i for i in new_ids if i not in subscribed]
                                    if truly_new:
                                        await ws.send_str(_json.dumps({
                                            "auth": {},
                                            "type": "subscribe",
                                            "channel": "market",
                                            "assets_ids": truly_new,
                                            "custom_feature_enabled": True,
                                        }))
                                        subscribed.update(truly_new)
                                        logger.info(
                                            "CLOB WebSocket: re-subscribed to %d new tokens "
                                            "(%d total)", len(truly_new), len(subscribed),
                                        )
                                try:
                                    events = _json.loads(msg.data)
                                    if not isinstance(events, list):
                                        events = [events]
                                    for ev in events:
                                        await self._handle_clob_ws_event(ev)
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("CLOB WS disconnected (%s) — reconnecting in 2s", exc)
                await asyncio.sleep(2)

    async def _handle_clob_ws_event(self, ev: dict) -> None:
        """Process a single CLOB WebSocket event and update order_books."""
        import json as _json
        ev_type = ev.get("event_type", ev.get("type", ""))
        asset_id = ev.get("asset_id", ev.get("market", ""))

        if ev_type in ("book", "price_change", "best_bid_ask"):
            token = self.tokens.get(asset_id)
            if token is None:
                return
            bids_raw = ev.get("bids", [])
            asks_raw = ev.get("asks", [])
            # best_bid_ask event has single price/size fields
            if ev_type == "best_bid_ask":
                best_bid = ev.get("best_bid")
                best_ask = ev.get("best_ask")
                # Merge with existing OB if we only have BBO update
                existing = self.order_books.get(asset_id)
                if existing and best_bid and best_ask:
                    bids_raw = [[str(best_bid), str(existing.bids[0][1] if existing.bids else 100)]]
                    asks_raw = [[str(best_ask), str(existing.asks[0][1] if existing.asks else 100)]]
                    bids_raw += [[str(b[0]), str(b[1])] for b in existing.bids[1:5]]
                    asks_raw += [[str(a[0]), str(a[1])] for a in existing.asks[1:5]]

            def _parse_levels(levels):
                result = []
                for level in levels:
                    try:
                        p = float(level[0] if isinstance(level, (list, tuple)) else level.get("price", 0))
                        s = float(level[1] if isinstance(level, (list, tuple)) else level.get("size", 0))
                        if p > 0:
                            result.append((p, s))
                    except Exception:
                        pass
                return sorted(result, reverse=(ev_type != "asks"))

            bids = sorted(_parse_levels(bids_raw), reverse=True)
            asks = sorted(_parse_levels(asks_raw))

            if bids or asks:
                ob = OrderBook(
                    ts=time.time(), token_id=asset_id,
                    asset=token.asset, side=token.side,
                    bids=bids, asks=asks,
                )
                self.order_books[asset_id] = ob
                self._ws_ob_ts[asset_id] = time.time()

        elif ev_type == "last_trade_price":
            price = ev.get("price")
            size = ev.get("size", 1.0)
            if price and asset_id in self.tokens:
                try:
                    p, s = float(price), float(size)
                    if p > 0:
                        self.bar_builders_5m.get(asset_id) and self.bar_builders_5m[asset_id].update(p, s)
                        self.bar_builders_15m.get(asset_id) and self.bar_builders_15m[asset_id].update(p, s)
                        self._ws_ob_ts[asset_id] = time.time()
                except Exception:
                    pass

    async def _run_rtds_ws(self) -> None:
        """
        Subscribe to Polymarket RTDS for real-time Chainlink oracle prices.
        These are the exact prices Polymarket uses to settle 5M windows.
        Stores in self.oracle_prices[asset] for use in risk/strategy.
        Bug: market/event slug filters silently drop messages — use empty filter.
        PING every 5s required.
        """
        import json as _json
        _PING_INTERVAL = 4.5

        while self._running:
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    _ssl_ctx = _ssl.create_default_context()
                    _ssl_ctx.check_hostname = False
                    _ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as ws_session:
                    async with ws_session.ws_connect(
                        self.RTDS_WS, ssl=_ssl_ctx, heartbeat=_PING_INTERVAL
                    ) as ws:
                        # Empty assets_ids filter — use client-side filtering (known bug)
                        sub_msg = _json.dumps({
                            "type": "subscribe",
                            "channel": "live_activity_updates",
                            "assets_ids": [],
                        })
                        await ws.send_str(sub_msg)
                        logger.info("RTDS WebSocket: subscribed to Chainlink oracle feed")

                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = _json.loads(msg.data)
                                    events = data if isinstance(data, list) else [data]
                                    for ev in events:
                                        ticker = ev.get("ticker", ev.get("asset", ""))
                                        price = ev.get("price", ev.get("outcome_price"))
                                        if price and ticker:
                                            # Map ticker to asset (e.g. "BTC/USD" or "BITCOIN/USD" → "BTC")
                                            ticker_up = str(ticker).upper()
                                            for asset, aliases in _QUESTION_ALIASES.items():
                                                if any(a.upper() in ticker_up for a in aliases):
                                                    try:
                                                        self.oracle_prices[asset] = float(price)
                                                    except Exception:
                                                        pass
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("RTDS WS disconnected (%s) — reconnecting in 3s", exc)
                await asyncio.sleep(3)

    async def _run_binance_ws(self) -> None:
        """
        Subscribe to Binance futures WebSocket for:
          1. markPrice@1s  — real-time funding rates (annualised)
          2. aggTrade      — individual trade stream for VPIN computation

        VPIN (Volume-Synchronized Probability of Informed Trading) measures order
        flow toxicity. VPIN > 0.60 + directional imbalance = momentum signal.
        This replaces the broken volume signal in the composite scorer.
        """
        import json as _json
        _SYMBOL_MAP = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}
        # Combined stream: markPrice (funding) + aggTrade (VPIN)
        _STREAMS = "/".join(
            f"{s}@markPrice@1s/{s}@aggTrade"
            for s in _SYMBOL_MAP.values()
        )
        _URL = f"{self.BINANCE_WS}/{_STREAMS}"

        while self._running:
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    _ssl_ctx = _ssl.create_default_context()
                    _ssl_ctx.check_hostname = False
                    _ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as ws_session:
                    async with ws_session.ws_connect(_URL, ssl=_ssl_ctx, heartbeat=20) as ws:
                        logger.info("Binance WS: subscribed to markPrice + aggTrade for BTC/ETH/SOL")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = _json.loads(msg.data)
                                    # Combined stream format: {"stream":"btcusdt@markPrice@1s","data":{...}}
                                    stream_name = data.get("stream", "")
                                    ev = data.get("data", data)
                                    event_type = ev.get("e", "")

                                    if event_type == "markPriceUpdate":
                                        # ── Funding rate ───────────────────
                                        symbol = ev.get("s", "").upper()
                                        funding = ev.get("r")  # current funding rate
                                        if funding:
                                            for asset, sym in _SYMBOL_MAP.items():
                                                if symbol == sym.upper():
                                                    try:
                                                        # Annualise: rate * 3 intervals/day * 365 * 100
                                                        self.funding_rates[asset] = float(funding) * 3 * 365 * 100
                                                    except Exception:
                                                        pass

                                    elif event_type == "aggTrade":
                                        # ── VPIN computation ───────────────
                                        symbol = ev.get("s", "").upper()
                                        try:
                                            price = float(ev.get("p", 0))
                                            qty = float(ev.get("q", 0))
                                            is_buyer_maker = bool(ev.get("m", False))
                                            if price > 0 and qty > 0:
                                                for asset, sym in _SYMBOL_MAP.items():
                                                    if symbol == sym.upper():
                                                        self.vpin_trackers[asset].update(
                                                            price, qty, is_buyer_maker
                                                        )
                                                        break
                                        except Exception:
                                            pass

                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Binance WS disconnected (%s) — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _run_binance_kline_ws(self) -> None:
        """
        Subscribe to Binance SPOT kline streams (1m/5m/15m) for BTC/ETH/SOL.
        Caches: spot_price, spot_window_open_5m/15m, momentum values.
        Replaces 9 REST calls per scan with zero-latency in-memory lookups.
        Reconnects automatically on disconnect.
        """
        import json as _json
        _SYMBOL_MAP = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}
        _INTERVALS = ["1m", "5m", "15m"]
        _STREAMS = "/".join(
            f"{sym}@kline_{iv}"
            for sym in _SYMBOL_MAP.values()
            for iv in _INTERVALS
        )
        _URL = f"wss://stream.binance.com:9443/stream?streams={_STREAMS}"

        while self._running:
            try:
                import ssl as _ssl
                try:
                    import certifi as _certifi
                    _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
                except ImportError:
                    _ssl_ctx = _ssl.create_default_context()
                    _ssl_ctx.check_hostname = False
                    _ssl_ctx.verify_mode = _ssl.CERT_NONE

                async with aiohttp.ClientSession() as ws_session:
                    async with ws_session.ws_connect(_URL, ssl=_ssl_ctx, heartbeat=20) as ws:
                        logger.info("Binance kline WS: subscribed to 1m/5m/15m for BTC/ETH/SOL")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = _json.loads(msg.data)
                                    ev = data.get("data", data)
                                    if ev.get("e") != "kline":
                                        continue

                                    k = ev["k"]
                                    symbol = ev.get("s", "").upper()   # e.g. "BTCUSDT"
                                    interval = k.get("i", "")          # "1m", "5m", "15m"
                                    is_closed = k.get("x", False)      # True = candle closed

                                    # Resolve asset name
                                    asset = None
                                    for a, sym in _SYMBOL_MAP.items():
                                        if symbol == sym.upper():
                                            asset = a
                                            break
                                    if asset is None:
                                        continue

                                    close = float(k.get("c", 0))
                                    open_ = float(k.get("o", 0))
                                    if close <= 0:
                                        continue

                                    now_ts = time.time()

                                    if interval == "1m":
                                        # spot_price = latest 1m close (ticks on every trade)
                                        self._spot_price[asset] = close
                                        self._kline_ts[asset] = now_ts
                                        # momentum = (current - prev_closed) / prev_closed
                                        # Only update prev when candle actually closes
                                        if is_closed:
                                            self._spot_prev_1m[asset] = close

                                    elif interval == "5m":
                                        self._spot_open_5m[asset] = open_
                                        if is_closed:
                                            self._spot_prev_5m[asset] = close

                                    elif interval == "15m":
                                        self._spot_open_15m[asset] = open_
                                        if is_closed:
                                            self._spot_prev_15m[asset] = close

                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Binance kline WS disconnected (%s) — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    # ── Market discovery ─────────────────────────────────────────────────────

    async def _discover_markets(self) -> None:
        """
        Fetch active markets from Gamma API and filter to tracked assets.

        Gamma API returns (all list fields are JSON-encoded strings):
          clobTokenIds:  "[\"token_id_up\", \"token_id_down\"]"   ← JSON string!
          outcomes:      "[\"Up\", \"Down\"]"                     ← JSON string!
          outcomePrices: "[\"0.52\", \"0.48\"]"                   ← JSON string!
          conditionId:   "0x..."
          endDate:       "2026-01-15T14:15:00Z"
          acceptingOrders: true / false
          liquidityClob: 10000.0
        """
        if not self._session:
            return
        import datetime as _dt
        import math as _math
        tracked = CONFIG.markets.tracked_assets
        url = f"{self.GAMMA}/markets"

        # Strategy: first try direct slug lookup for current 5M/15M windows
        # (slugs are deterministic: btc-updown-5m-{window_ts}).
        # Fall back to bulk scan if slug lookup returns nothing.
        now_ts = int(time.time())
        intervals = [300, 900]   # 5M and 15M
        direct_slugs = []
        for asset in tracked:
            for slug_prefix in _SLUG_ALIASES.get(asset, [asset.lower()]):
                for interval in intervals:
                    w_ts = now_ts - (now_ts % interval)
                    direct_slugs.append(f"{slug_prefix}-updown-{interval//60}m-{w_ts}")
                    # Also include next window (already accepting orders 2-3 min early)
                    direct_slugs.append(f"{slug_prefix}-updown-{interval//60}m-{w_ts + interval}")

        # Use a short per-request timeout for discovery so network outages
        # fail fast (3s) instead of blocking for the full 10s session timeout.
        import aiohttp as _aiohttp
        _disc_timeout = _aiohttp.ClientTimeout(total=3)

        async def _fetch_slug(slug: str):
            try:
                async with self._session.get(
                    url, params={"slug": slug}, timeout=_disc_timeout
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                pass
            return None

        markets = []
        slug_results = await asyncio.gather(*[_fetch_slug(s) for s in direct_slugs])
        for data in slug_results:
            if data is None:
                continue
            if isinstance(data, list):
                markets.extend(data)
            elif isinstance(data, dict):
                markets.append(data)

        # Skip bulk scan if slug requests all failed (network is down)
        network_ok = any(d is not None for d in slug_results)

        # Bulk scan fallback for target markets (price prediction, non-updown)
        if network_ok:
            try:
                async with self._session.get(
                    url, params={"active": "true", "closed": "false", "limit": 500},
                    timeout=_disc_timeout,
                ) as resp:
                    if resp.status == 200:
                        bulk = await resp.json()
                        if isinstance(bulk, list):
                            markets.extend(bulk)
            except Exception as exc:
                if not markets:
                    logger.error("Market discovery failed: %s", exc)
        else:
            logger.error("Market discovery failed: all slug requests failed (network down?)")
            return

        # Deduplicate by conditionId
        seen_conditions: set = set()
        unique_markets = []
        for m in markets:
            cid = m.get("conditionId", m.get("id", ""))
            if cid and cid not in seen_conditions:
                seen_conditions.add(cid)
                unique_markets.append(m)
        markets = unique_markets
        logger.debug("Market discovery: %d unique markets to process", len(markets))

        import json as _json

        def _parse_json_field(val, default):
            if isinstance(val, str):
                try:
                    return _json.loads(val)
                except Exception:
                    return default
            return val if val is not None else default

        now = _dt.datetime.utcnow().timestamp()
        for market in markets:
            # Skip non-tradeable markets early
            if not market.get("acceptingOrders", True):
                continue
            if market.get("closed", False) or market.get("archived", False):
                continue

            question = market.get("question", "")
            slug_field = market.get("slug", "").lower()
            q_upper = question.upper()
            asset_match = next(
                (
                    a for a in tracked
                    if any(alias.upper() in q_upper for alias in _QUESTION_ALIASES.get(a, [a]))
                    or any(alias in slug_field for alias in _SLUG_ALIASES.get(a, [a.lower()]))
                ),
                None,
            )
            if not asset_match:
                continue

            # Detect market type: 5M/15M Up/Down vs longer-duration price target.
            # Gamma slugs encode resolution: btc-updown-15m-1768220100
            slug = market.get("slug", "")
            slug_lo = slug.lower()
            q_lo = question.lower()
            is_updown = (
                "updown" in slug_lo
                or "up-or-down" in slug_lo
                or "up-down" in slug_lo
                or "up or down" in q_lo
                or "go up or down" in q_lo
            )
            # Only care about short-duration updown (5m or 15m)
            if is_updown:
                is_short = "5m" in slug_lo or "15m" in slug_lo or "5 min" in q_lo or "15 min" in q_lo
                if not is_short:
                    is_updown = False  # skip longer-duration updown markets
            market_type = "updown" if is_updown else "target"

            # Liquidity filter for price-target markets only.
            # Updown (5M/15M) windows start with thin books — filtering by liquidity
            # drops fresh windows that haven't accumulated depth yet.
            if market_type == "target":
                liquidity = float(market.get("liquidityClob", market.get("liquidityNum", 0)) or 0)
                if liquidity < 200:
                    continue

            # Parse resolution timestamp
            end_date_str = market.get("endDate", market.get("end_date_iso", ""))
            window_end_ts = 0.0
            if end_date_str:
                try:
                    end_dt = _dt.datetime.fromisoformat(
                        end_date_str.replace("Z", "+00:00")
                    )
                    window_end_ts = end_dt.timestamp()
                except Exception:
                    pass

            condition_id = market.get("conditionId", market.get("condition_id", ""))
            neg_risk = bool(market.get("negRisk", False))
            # tick_size: clamp to one of the 4 valid SDK values to avoid KeyError
            # in ROUNDING_CONFIG. str(float) can produce "0.10000000000000001" etc.
            _VALID_TICKS = ("0.0001", "0.001", "0.01", "0.1")
            raw_tick = market.get("orderPriceMinTickSize", market.get("minTickSize", 0.01))
            try:
                tick_f = float(raw_tick) if raw_tick else 0.01
                # find smallest valid tick >= tick_f
                tick_size = next((t for t in _VALID_TICKS if float(t) >= tick_f - 1e-9), "0.01")
            except Exception:
                tick_size = "0.01"

            # Gamma returns clobTokenIds + outcomes as JSON-encoded strings,
            # e.g. clobTokenIds = "[\"id1\",\"id2\"]" — must call json.loads().
            # Guard: accept both string (Gamma) and list (legacy/CLOB) formats.
            raw_ids = _parse_json_field(market.get("clobTokenIds"), [])
            outcomes = _parse_json_field(market.get("outcomes"), [])
            # outcomePrices gives current market prices — use to seed OB on discovery
            outcome_prices_raw = _parse_json_field(market.get("outcomePrices"), [])
            outcome_prices = []
            for p in outcome_prices_raw:
                try:
                    outcome_prices.append(float(p))
                except (ValueError, TypeError):
                    outcome_prices.append(0.0)

            if not raw_ids:
                # Try legacy CLOB field name (tokens list of dicts)
                raw_ids = [
                    t.get("token_id", "") for t in market.get("tokens", [])
                ]
                outcomes = [
                    t.get("outcome", "") for t in market.get("tokens", [])
                ]

            for i, token_id in enumerate(raw_ids):
                if not token_id:
                    continue
                outcome_label = outcomes[i] if i < len(outcomes) else ("YES" if i == 0 else "NO")
                # UP / YES → YES side; DOWN / NO → NO side
                side = "YES" if outcome_label.upper() in ("YES", "UP", "TRUE", "1") else "NO"

                # Skip already-expired tokens
                if window_end_ts > 0 and window_end_ts < now:
                    continue

                token = MarketToken(
                    token_id=token_id,
                    condition_id=condition_id,
                    asset=asset_match,
                    side=side,
                    question=question,
                    end_date_iso=end_date_str,
                    active=market.get("active", True),
                    market_type=market_type,
                    window_end_ts=window_end_ts,
                    window_seconds=900 if "15m" in slug.lower() else 300,
                    neg_risk=neg_risk,
                    tick_size=tick_size,
                )
                is_new = token_id not in self.tokens
                self.tokens[token_id] = token
                if is_new:
                    # Only add to index and initialise builders for new tokens.
                    # Existing tokens keep their accumulated bar history.
                    self.asset_tokens.setdefault(asset_match, []).append(token_id)
                    self.bar_builders_5m[token_id] = BarBuilder(
                        CONFIG.markets.bar_interval_primary,
                        CONFIG.markets.history_bars,
                    )
                    self.bar_builders_15m[token_id] = BarBuilder(
                        CONFIG.markets.bar_interval_secondary,
                        CONFIG.markets.history_bars,
                    )
                    # Seed order book from Gamma outcomePrices (saves first OB fetch)
                    if i < len(outcome_prices) and outcome_prices[i] > 0:
                        self.order_books[token_id] = self._make_stub_order_book(
                            token_id, outcome_prices[i]
                        )

        logger.info(
            "Discovered %d tokens across %s (updown=%d target=%d)",
            len(self.tokens), tracked,
            sum(1 for t in self.tokens.values() if t.market_type == "updown"),
            sum(1 for t in self.tokens.values() if t.market_type == "target"),
        )

        # Warn if any tracked asset has zero updown tokens (slug mismatch or no active markets)
        for asset in tracked:
            has_updown = any(
                t.asset == asset and t.market_type == "updown"
                for t in self.tokens.values()
            )
            if not has_updown:
                logger.warning(
                    "DISCOVERY GAP: no updown tokens found for %s "
                    "(slug lookup may have failed or no active markets)",
                    asset,
                )

    # ── Order book polling ────────────────────────────────────────────────────

    async def fetch_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Fetch and parse CLOB order book for one token."""
        if not self._session or self._stub_mode:
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

    async def refresh_markets(self) -> None:
        """
        Periodically re-discover markets to pick up new 5M/15M windows.
        Also purges expired tokens from tracking (avoids scanning dead markets).
        Called every ~60 seconds from poll_order_books.
        Skipped in stub mode.
        """
        if self._stub_mode or not self._session:
            return
        now = time.time()
        if now - self._last_discovery_ts < 60:
            return
        self._last_discovery_ts = now

        # Purge expired tokens (window_end_ts > 0 and in the past, or within final
        # no_trade_last_sec — those will never receive a new entry and just add noise).
        no_trade_guard = CONFIG.execution.no_trade_last_sec
        expired = [
            tid for tid, t in self.tokens.items()
            if t.window_end_ts > 0 and t.window_end_ts - now < no_trade_guard
        ]
        for tid in expired:
            self.tokens.pop(tid, None)
            self.order_books.pop(tid, None)
            self.bar_builders_5m.pop(tid, None)
            self.bar_builders_15m.pop(tid, None)
            self._last_ob_ts.pop(tid, None)
            # Clean up asset_tokens index
            for asset_list in self.asset_tokens.values():
                if tid in asset_list:
                    asset_list.remove(tid)
        if expired:
            logger.info("Purged %d expired tokens", len(expired))

        prev_count = len(self.tokens)
        prev_ids = set(self.tokens.keys())
        await self._discover_markets()
        new_count = len(self.tokens)
        if new_count != prev_count:
            logger.info(
                "Market refresh: %d → %d tokens (+%d)",
                prev_count, new_count, new_count - prev_count,
            )
            # Enqueue new token IDs so the CLOB WS subscribes to them
            # within 2 seconds (the wait_for timeout in _run_clob_ws).
            new_ids = [tid for tid in self.tokens if tid not in prev_ids]
            if new_ids and not self._stub_mode:
                await self._clob_ws_sub_queue.put(new_ids)
                logger.debug("Queued %d new tokens for WS re-subscription", len(new_ids))

    async def poll_order_books(self) -> None:
        """
        Poll all tracked tokens; re-discover new markets every 60s.
        Skips REST fetch for tokens whose OB was recently updated via WebSocket
        (within 1.5s) to reduce REST load and Cloudflare trigger risk.
        """
        await self.refresh_markets()
        now = time.time()
        tokens_needing_rest = [
            tid for tid in list(self.tokens)
            if now - self._ws_ob_ts.get(tid, 0) > 1.5
        ]
        if tokens_needing_rest:
            tasks = [self.fetch_order_book(tid) for tid in tokens_needing_rest]
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Price bar updates from last trade ────────────────────────────────────

    async def fetch_last_trade(self, token_id: str) -> Optional[Tuple[float, float]]:
        """Returns (price, size) of the most recent trade, or None."""
        if not self._session or self._stub_mode:
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

    async def _warmup_live_bars(self) -> None:
        """
        Seed 5m and 15m bar builders from CLOB prices-history on startup.
        Without this, the bot waits 60+ min for bars to accumulate from live ticks.
        Fetches up to 2h of history per token (24+ 5m bars, 8+ 15m bars).
        Uses a semaphore to avoid hammering the CLOB API with 56 concurrent requests.
        """
        if not self._session or not self.tokens:
            return

        now = int(time.time())
        sem = asyncio.Semaphore(6)  # max 6 concurrent CLOB requests

        async def _fetch_and_seed(token_id: str, interval_min: int, builder) -> int:
            async with sem:
                try:
                    url = f"{self.CLOB}/prices-history"
                    params = {
                        "market": token_id,
                        "startTs": now - 30 * interval_min * 60,  # 30 bars of history
                        "endTs": now,
                        "fidelity": interval_min,
                    }
                    async with self._session.get(
                        url, params=params,
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as resp:
                        if resp.status != 200:
                            return 0
                        data = await resp.json()
                        history = data.get("history", [])
                        if not history:
                            return 0
                        bars = []
                        for entry in history[:-1]:  # skip last (in-progress bar)
                            p = float(entry.get("p", 0))
                            t = float(entry.get("t", 0))
                            if p > 0 and t > 0:
                                bars.append(Bar(ts=t, open=p, high=p, low=p, close=p, volume=100.0))
                        builder.seed(bars)
                        return len(bars)
                except Exception:
                    return 0

        tasks = []
        for token_id in list(self.tokens.keys()):
            b5 = self.bar_builders_5m.get(token_id)
            b15 = self.bar_builders_15m.get(token_id)
            if b5:
                tasks.append(_fetch_and_seed(token_id, 5, b5))   # 5-min candles for 5m builder
            if b15:
                tasks.append(_fetch_and_seed(token_id, 15, b15))  # 15-min candles for 15m builder

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = sum(r for r in results if isinstance(r, int))
        logger.info("Bar warmup: seeded %d bars across %d tokens", total, len(self.tokens))

    async def update_bars(self) -> None:
        """
        Push latest trade into bar builders for all active tokens.

        Fixes two performance issues from sequential implementation:
        1. Sequential REST calls (50+ tokens × 50ms each = 2-3s blocking the scan cycle)
           → replaced with asyncio.gather for parallel fetching
        2. Near-resolved tokens (price <0.05 or >0.95) waste REST calls and will
           never qualify for entry → skip them, use OB mid directly
        """
        import random
        now = time.time()
        token_ids = list(self.tokens.keys())

        # Skip REST for near-resolved tokens — they'll never enter and just waste calls.
        # Use OB mid directly for them (they're not trading anyway).
        rest_ids = []
        ob_only_ids = []
        for tid in token_ids:
            ob = self.order_books.get(tid)
            mid = ob.mid if ob else 0.0
            if not self._stub_mode and 0.05 < mid < 0.95:
                rest_ids.append(tid)
            else:
                ob_only_ids.append(tid)

        # Parallel REST fetch for active tokens
        results = await asyncio.gather(
            *[self.fetch_last_trade(tid) for tid in rest_ids],
            return_exceptions=True,
        )

        for token_id, result in zip(rest_ids, results):
            if isinstance(result, Exception) or result is None or result[0] <= 0:
                ob = self.order_books.get(token_id)
                if ob is None or ob.mid <= 0:
                    continue
                if self._stub_mode:
                    price = max(0.01, min(0.99, ob.mid + random.gauss(0, 0.004)))
                    size = random.uniform(50, 500)
                else:
                    price = ob.mid
                    size = 1.0
            else:
                price, size = result
            self.bar_builders_5m[token_id].update(price, size, now)
            self.bar_builders_15m[token_id].update(price, size, now)

        # OB-only path for near-resolved tokens (no REST)
        for token_id in ob_only_ids:
            ob = self.order_books.get(token_id)
            if ob is None or ob.mid <= 0:
                continue
            if self._stub_mode:
                price = max(0.01, min(0.99, ob.mid + random.gauss(0, 0.004)))
                size = random.uniform(50, 500)
            else:
                price = ob.mid
                size = 1.0
            self.bar_builders_5m[token_id].update(price, size, now)
            self.bar_builders_15m[token_id].update(price, size, now)

    # ── External signals ─────────────────────────────────────────────────────

    async def fetch_external_signals(self, asset: str) -> Optional[ExternalSignal]:
        """
        Fetch optional external signals: perp funding rate, spot momentum.
        Source: Binance public API (no auth required).
        Only applied if they improve edge; never blocks a high-edge trade.
        """
        if not self._session or self._stub_mode:
            return None
        symbol_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
        symbol = symbol_map.get(asset.upper())
        if not symbol:
            return None

        signal = ExternalSignal(ts=time.time(), asset=asset)

        # Funding rate: prefer live WebSocket data (1s updates), fall back to REST
        if asset.upper() in self.funding_rates:
            signal.funding_rate = self.funding_rates[asset.upper()]
        else:
            try:
                url = "https://fapi.binance.com/fapi/v1/premiumIndex"
                async with self._session.get(url, params={"symbol": symbol}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        signal.funding_rate = float(data.get("lastFundingRate", 0)) * 365 * 100
            except Exception:
                pass  # signal is optional; never blocks trade

        # Spot klines: use WebSocket cache (zero-latency) or fall back to REST.
        # _run_binance_kline_ws() keeps these dicts updated in real-time.
        _KLINE_STALE_S = 3.0  # fall back to REST if cache not updated in 3s
        kline_fresh = (time.time() - self._kline_ts.get(asset.upper(), 0)) < _KLINE_STALE_S

        if kline_fresh:
            # ── Fast path: serve from in-memory kline cache (sub-millisecond) ──
            c0 = self._spot_price.get(asset.upper())
            c1_1m = self._spot_prev_1m.get(asset.upper())
            c1_5m = self._spot_prev_5m.get(asset.upper())
            c1_15m = self._spot_prev_15m.get(asset.upper())
            open_5m = self._spot_open_5m.get(asset.upper())
            open_15m = self._spot_open_15m.get(asset.upper())

            if c0:
                signal.spot_price = c0
            if c0 and c1_1m and c1_1m > 0:
                signal.spot_momentum_1m = (c0 - c1_1m) / c1_1m * 100
            if c0 and c1_5m and c1_5m > 0:
                signal.spot_momentum_5m = (c0 - c1_5m) / c1_5m * 100
            if c0 and c1_15m and c1_15m > 0:
                signal.spot_momentum_15m = (c0 - c1_15m) / c1_15m * 100
            if open_5m:
                signal.spot_window_open_5m = open_5m
            if open_15m:
                signal.spot_window_open_15m = open_15m
        else:
            # ── Slow path: REST fallback when WS hasn't delivered data yet ──
            # Happens during initial startup (~5s) before first kline event arrives.
            try:
                url = "https://api.binance.com/api/v3/klines"
                params = {"symbol": symbol, "interval": "1m", "limit": 3}
                async with self._session.get(url, params=params) as resp:
                    if resp.status == 200:
                        klines = await resp.json()
                        if len(klines) >= 2:
                            c1 = float(klines[-2][4])
                            c0 = float(klines[-1][4])
                            signal.spot_price = c0
                            signal.spot_momentum_1m = (c0 - c1) / c1 * 100
                params["interval"] = "5m"
                params["limit"] = 4
                async with self._session.get(url, params=params) as resp:
                    if resp.status == 200:
                        klines = await resp.json()
                        if len(klines) >= 2:
                            signal.spot_momentum_5m = (
                                (float(klines[-1][4]) - float(klines[-2][4]))
                                / float(klines[-2][4]) * 100
                            )
                        if len(klines) >= 1:
                            signal.spot_window_open_5m = float(klines[-1][1])
                params["interval"] = "15m"
                async with self._session.get(url, params=params) as resp:
                    if resp.status == 200:
                        klines = await resp.json()
                        if len(klines) >= 2:
                            signal.spot_momentum_15m = (
                                (float(klines[-1][4]) - float(klines[-2][4]))
                                / float(klines[-2][4]) * 100
                            )
                        if len(klines) >= 1:
                            signal.spot_window_open_15m = float(klines[-1][1])
            except Exception:
                pass

        # VPIN: from aggTrade WebSocket (live only, not available in stub)
        vpin_tracker = self.vpin_trackers.get(asset.upper())
        if vpin_tracker and vpin_tracker._trade_count > 100:
            # Only include once we have enough trade history (>100 trades)
            signal.vpin_score = round(vpin_tracker.vpin, 4)
            signal.vpin_direction = vpin_tracker.direction

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
        """Create synthetic UP/DOWN tokens for each tracked asset (5M/15M style)."""
        import uuid
        for asset in CONFIG.markets.tracked_assets:
            for side in ("YES", "NO"):
                label = "Up" if side == "YES" else "Down"
                token_id = f"stub_{asset}_{side}_{uuid.uuid4().hex[:8]}"
                token = MarketToken(
                    token_id=token_id,
                    condition_id="",  # empty = no dedup (real markets rotate conditionId each window)
                    asset=asset,
                    side=side,
                    question=f"Will {asset} go up or down in the next 15 minutes? ({label})",
                    end_date_iso="2099-12-31T00:00:00Z",
                    active=True,
                    market_type="updown",
                    window_end_ts=0.0,  # 0 = no expiry guard (stub only; live uses real endDate)
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
            # 5M/15M Up/Down markets: UP and DOWN tokens both trade near $0.47-$0.53
            # (roughly coin-flip probability). Small random offset per asset.
            base_offsets = {"BTC": 0.02, "ETH": -0.01, "SOL": 0.03}
            offset = base_offsets.get(token.asset, 0.0)
            base = 0.50 + offset if token.side == "YES" else 0.50 - offset

            price = base
            for i in range(n_bars):
                bar_ts = now - (n_bars - i) * interval_5m
                # Random walk with mean reversion + occasional momentum burst
                drift = random.gauss(0, 0.012)
                # Mean reversion toward base (keeps YES tokens near 0.20-0.25,
                # NO tokens near 0.75-0.80 — stays in EXTREME fee zone)
                drift += (base - price) * 0.05
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
