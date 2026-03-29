"""
Klaus — Order Manager
Handles Polymarket CLOB order placement, cascade selling, fill tracking,
and slippage measurement.

CLOB API reference: https://docs.polymarket.com/#create-order
Auth: L1 auth (wallet private key + CLOB API credentials)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import logging

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import MarketOrderArgs, OrderType
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    CLOB_CLIENT_AVAILABLE = False

from config import CONFIG
from strategy.momentum import Direction

logger = logging.getLogger("execution")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class OrderSide(Enum):
    BUY = auto()
    SELL = auto()


class OrderStatus(Enum):
    PENDING = auto()
    FILLED = auto()
    PARTIAL = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass
class Fill:
    order_id: str
    token_id: str
    side: OrderSide
    price: float
    size: float
    fee: float
    ts: float = field(default_factory=time.time)
    slippage: float = 0.0    # abs(intended_price - fill_price)


@dataclass
class OrderResult:
    status: OrderStatus
    fills: List[Fill] = field(default_factory=list)
    avg_fill_price: float = 0.0
    total_size: float = 0.0
    total_fee: float = 0.0
    slippage: float = 0.0
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CLOB auth helper
# ---------------------------------------------------------------------------

def _build_clob_client() -> Optional[Any]:
    """Builds py-clob-client instance from config credentials."""
    if not CLOB_CLIENT_AVAILABLE:
        logger.warning("py_clob_client not installed — running in stub mode")
        return None
    cfg = CONFIG
    if not cfg.wallet_private_key:
        logger.warning("No wallet private key configured — stub mode")
        return None
    try:
        client = ClobClient(
            host=cfg.markets.clob_api_url,
            chain_id=137,       # Polygon mainnet
            key=cfg.wallet_private_key,
            creds=None,         # credentials set separately if needed
        )
        return client
    except Exception as exc:
        logger.error("Failed to build CLOB client: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Order Manager
# ---------------------------------------------------------------------------

class OrderManager:
    """
    Places and manages orders on the Polymarket CLOB.
    Supports: market buy, cascade sell (tranche exit), slippage tracking.
    """

    def __init__(self) -> None:
        self.cfg = CONFIG.execution
        self.fee_cfg = CONFIG.fees
        self._client = _build_clob_client() if not CONFIG.dry_run else None
        self._session: Optional[aiohttp.ClientSession] = None
        self._pending_orders: Dict[str, Dict] = {}   # order_id → metadata
        self.fill_history: List[Fill] = []

    async def start(self) -> None:
        if AIOHTTP_AVAILABLE:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    # ── Market buy ────────────────────────────────────────────────────────────

    async def market_buy(
        self,
        token_id: str,
        intended_price: float,
        stake_usd: float,
        direction: Direction,
    ) -> OrderResult:
        """
        Buy `stake_usd` worth of YES or NO token at market.
        Returns OrderResult with fills, average price, and slippage.
        """
        if CONFIG.dry_run:
            return self._simulate_fill(token_id, intended_price, stake_usd, OrderSide.BUY)

        size = round(stake_usd / intended_price, 2) if intended_price > 0 else 0
        if size <= 0:
            return OrderResult(status=OrderStatus.FAILED, error="Invalid size")

        for attempt in range(self.cfg.retry_attempts):
            try:
                result = await self._submit_market_order(
                    token_id, OrderSide.BUY, size, intended_price
                )
                if result.status == OrderStatus.FILLED:
                    return result
                await asyncio.sleep(self.cfg.retry_delay * (2 ** attempt))
            except Exception as exc:
                logger.error("Buy attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(self.cfg.retry_delay * (2 ** attempt))

        return OrderResult(status=OrderStatus.FAILED, error="All retry attempts exhausted")

    # ── Cascade sell ─────────────────────────────────────────────────────────

    async def cascade_sell(
        self,
        token_id: str,
        total_shares: float,
        current_price: float,
        reason: str = "cascade",
    ) -> List[OrderResult]:
        """
        Exit a position in N tranches to minimise market impact.
        Tranche sizes: 33% / 33% / 34% with `cascade_interval` seconds between.
        Returns list of OrderResult per tranche.
        """
        n = self.cfg.cascade_levels
        results = []
        remaining = total_shares

        for i in range(n):
            is_last = (i == n - 1)
            tranche_size = (
                remaining if is_last
                else round(total_shares * self.cfg.cascade_pct, 4)
            )
            if tranche_size <= 0:
                break

            logger.info(
                "Cascade sell tranche %d/%d: size=%.4f @ ~%.4f | reason=%s",
                i + 1, n, tranche_size, current_price, reason,
            )

            if CONFIG.dry_run:
                result = self._simulate_fill(
                    token_id, current_price, tranche_size * current_price, OrderSide.SELL
                )
            else:
                result = await self._submit_market_order(
                    token_id, OrderSide.SELL, tranche_size, current_price
                )

            results.append(result)
            remaining -= tranche_size

            if i < n - 1:
                await asyncio.sleep(self.cfg.cascade_interval)

        return results

    # ── CLOB submission ───────────────────────────────────────────────────────

    async def _submit_market_order(
        self,
        token_id: str,
        side: OrderSide,
        size: float,
        intended_price: float,
    ) -> OrderResult:
        """
        Submit a market order via py-clob-client.
        Validates slippage against tolerance threshold.
        """
        if self._client is None:
            return OrderResult(status=OrderStatus.FAILED, error="No CLOB client")

        try:
            args = MarketOrderArgs(
                token_id=token_id,
                amount=size,
            )
            resp = self._client.create_market_order(args)
            if not resp:
                return OrderResult(status=OrderStatus.FAILED, error="Empty response")

            fill_price = float(resp.get("average_price", intended_price))
            fill_size = float(resp.get("size_matched", 0))
            fee = float(resp.get("fee", 0))
            slippage = abs(fill_price - intended_price)

            if slippage > self.cfg.slippage_tolerance:
                logger.warning(
                    "Slippage %.4f exceeds tolerance %.4f",
                    slippage, self.cfg.slippage_tolerance,
                )

            fill = Fill(
                order_id=resp.get("order_id", ""),
                token_id=token_id,
                side=side,
                price=fill_price,
                size=fill_size,
                fee=fee,
                slippage=slippage,
            )
            self.fill_history.append(fill)

            return OrderResult(
                status=OrderStatus.FILLED,
                fills=[fill],
                avg_fill_price=fill_price,
                total_size=fill_size,
                total_fee=fee,
                slippage=slippage,
                raw=resp,
            )

        except Exception as exc:
            logger.error("Order submission error: %s", exc)
            return OrderResult(status=OrderStatus.FAILED, error=str(exc))

    # ── Dry-run simulation ────────────────────────────────────────────────────

    def _simulate_fill(
        self,
        token_id: str,
        price: float,
        stake_usd: float,
        side: OrderSide,
    ) -> OrderResult:
        """Simulates a fill for dry-run testing; adds tiny random slippage."""
        import random
        slip = random.uniform(0, 0.003)
        fill_price = price + (slip if side == OrderSide.BUY else -slip)
        fill_price = max(0.01, min(0.99, fill_price))
        size = stake_usd / fill_price if fill_price > 0 else 0
        fee = stake_usd * (
            CONFIG.fees.extreme_fee_rate
            if price < CONFIG.fees.extreme_low or price > CONFIG.fees.extreme_high
            else CONFIG.fees.middle_fee_rate
        )

        fill = Fill(
            order_id=f"dry_{token_id[:6]}_{int(time.time())}",
            token_id=token_id,
            side=side,
            price=fill_price,
            size=size,
            fee=fee,
            slippage=slip,
        )
        self.fill_history.append(fill)
        logger.debug("[DRY RUN] %s %.4f @ %.4f fee=%.4f", side.name, size, fill_price, fee)

        return OrderResult(
            status=OrderStatus.FILLED,
            fills=[fill],
            avg_fill_price=fill_price,
            total_size=size,
            total_fee=fee,
            slippage=slip,
        )

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel_order(self, order_id: str) -> bool:
        if CONFIG.dry_run:
            return True
        if self._client is None:
            return False
        try:
            self._client.cancel(order_id)
            return True
        except Exception as exc:
            logger.error("Cancel failed for %s: %s", order_id, exc)
            return False
