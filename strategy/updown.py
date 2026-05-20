"""
CryptoUpDown — 15-minute BTC/ETH/SOL Up-or-Down Polymarket prediction markets.

Signal: same cross-asset synchrony as CAS. At the start of each 15-minute window,
check Binance 5m partial return for BTC/ETH/SOL. If 2-of-3 assets are aligned
(≥ THR_PCT in same direction) AND the third confirms (same sign), buy the matching
Up/Down token for ALL three assets at that direction.

Market slug pattern: {btc,eth,sol}-updown-15m-{window_start_unix}
Resolution: Chainlink {asset}-USD price at window end > window start = Up wins.

Edge: CAS shows ~52-55% WR on cross-asset synchrony signal. Up/Down markets price
near 50/50 → edge directly applicable.

Entry: 30-90s after window start while price is still ~0.50.
Hold to resolution (15 minutes).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

GAMMA_BASE   = "https://gamma-api.polymarket.com"
ASSETS       = ("BTC", "ETH", "SOL")
THR_PCT      = 0.005       # 5m partial return threshold (same as CAS)
STAKE_USD    = 20.0        # per asset per window
MAX_ENTRY_DELAY_S = 120.0  # don't enter if >2 min past window start
DRY_RUN_LOG  = False       # if True, log but don't buy (set False to go live)


class CryptoUpDown:
    def __init__(self, bot) -> None:
        self.bot = bot
        self._fired_windows: set[int] = set()   # window_start_ts already fired
        self._task: Optional[asyncio.Task] = None
        logger.info("[UD] CryptoUpDown strategy initialized stake=$%.0f/asset", STAKE_USD)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="updown_loop")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("[UD] tick error")
            # Sleep until 35s after the next 15-min boundary
            now = time.time()
            next_window = (int(now) // 900 + 1) * 900
            sleep_s = next_window - now + 35.0
            await asyncio.sleep(sleep_s)

    async def _tick(self) -> None:
        now = time.time()
        window_start = (int(now) // 900) * 900  # floor to 15-min boundary

        # Don't fire the same window twice, don't fire if we're too late
        if window_start in self._fired_windows:
            return
        since_start = now - window_start
        if since_start > MAX_ENTRY_DELAY_S:
            return

        # Evaluate cross-asset synchrony signal
        feed = self.bot.feed
        partials: dict[str, float] = {}
        for a in ASSETS:
            spot = feed._spot_price.get(a, 0.0)
            o5m  = feed._spot_open_5m.get(a, 0.0)
            if not spot or not o5m:
                logger.debug("[UD] no kline data for %s, skipping window %d", a, window_start)
                return
            partials[a] = (spot - o5m) / o5m * 100.0

        btc_r, eth_r, sol_r = partials["BTC"], partials["ETH"], partials["SOL"]
        logger.info("[UD] W%d +%.0fs  BTC=%+.3f%% ETH=%+.3f%% SOL=%+.3f%%",
                    window_start, since_start, btc_r, eth_r, sol_r)

        # Gate: all three same sign, and at least two exceed THR_PCT
        up_count   = sum(1 for r in (btc_r, eth_r, sol_r) if r >= THR_PCT)
        down_count = sum(1 for r in (btc_r, eth_r, sol_r) if r <= -THR_PCT)
        all_up     = all(r >= 0 for r in (btc_r, eth_r, sol_r))
        all_down   = all(r <= 0 for r in (btc_r, eth_r, sol_r))

        if up_count >= 2 and all_up:
            direction = "Up"
        elif down_count >= 2 and all_down:
            direction = "Down"
        else:
            logger.info("[UD] W%d no signal (up=%d down=%d all_up=%s all_down=%s)",
                        window_start, up_count, down_count, all_up, all_down)
            return

        logger.info("[UD] W%d SIGNAL=%s  BTC=%+.3f%% ETH=%+.3f%% SOL=%+.3f%%",
                    window_start, direction, btc_r, eth_r, sol_r)
        self._fired_windows.add(window_start)

        # Fetch and enter all three assets concurrently
        tasks = [
            self._enter_asset(a.lower(), window_start, direction)
            for a in ASSETS
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _enter_asset(self, asset_lower: str, window_start: int, direction: str) -> None:
        try:
            market = await self._fetch_market(asset_lower, window_start)
            if not market:
                logger.warning("[UD] %s W%d: market not found", asset_lower.upper(), window_start)
                return

            import json as _json
            outcomes  = market.get("outcomes", ["Up", "Down"])
            _prices_raw = market.get("outcomePrices", '["0.5", "0.5"]')
            prices_s  = _json.loads(_prices_raw) if isinstance(_prices_raw, str) else _prices_raw
            token_ids = market.get("clobTokenIds", [])
            end_date  = market.get("endDate", "?")

            if len(outcomes) < 2 or len(token_ids) < 2 or len(prices_s) < 2:
                logger.warning("[UD] %s W%d: bad market structure outcomes=%s prices=%s tokens=%d",
                               asset_lower.upper(), window_start, outcomes, prices_s, len(token_ids))
                return

            # Determine which token index corresponds to the direction we want
            try:
                dir_idx = outcomes.index(direction)
            except ValueError:
                logger.warning("[UD] %s W%d: direction %s not in outcomes %s",
                               asset_lower.upper(), window_start, direction, outcomes)
                return

            token_id  = token_ids[dir_idx]
            ask_price = float(prices_s[dir_idx])
            cid       = market.get("conditionId", "")

            if ask_price <= 0.10 or ask_price >= 0.90:
                logger.info("[UD] %s W%d %s: price %.3f out of range, skip",
                            asset_lower.upper(), window_start, direction, ask_price)
                return

            logger.info("[UD] %s W%d %s: token=%s price=%.3f stake=$%.0f end=%s%s",
                        asset_lower.upper(), window_start, direction,
                        token_id[:16], ask_price, STAKE_USD, end_date[:16],
                        " [DRY]" if DRY_RUN_LOG else "")

            if DRY_RUN_LOG:
                return

            from strategy.momentum import Direction as Dir
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=ask_price,
                stake_usd=STAKE_USD,
                direction=Dir.BUY_YES,
                neg_risk=False,
                fast_fail=True,
            )
            from execution.order_manager import OrderStatus
            if fill.status == OrderStatus.FILLED and fill.total_size > 0:
                self.bot.risk.open_position(
                    token_id=token_id,
                    condition_id=cid,
                    asset=asset_lower.upper(),
                    direction="UP" if direction == "Up" else "DOWN",
                    side="YES",
                    shares=fill.total_size,
                    entry_price=fill.avg_fill_price,
                    stake_usd=STAKE_USD,
                    bond_entry_class="UPDOWN",
                    bond_outcome_direction="up" if direction == "Up" else "down",
                    window_end_ts=window_start + 900,
                )
                logger.info("[UD] %s W%d FILLED %s shares=%.1f @ %.4f",
                            asset_lower.upper(), window_start, direction,
                            fill.total_size, fill.avg_fill_price)
            else:
                logger.warning("[UD] %s W%d fill failed: %s",
                               asset_lower.upper(), window_start, getattr(fill, "error", "?"))
        except Exception:
            logger.exception("[UD] %s W%d enter error", asset_lower.upper(), window_start)

    async def _fetch_market(self, asset_lower: str, window_start: int) -> Optional[dict]:
        slug = f"{asset_lower}-updown-15m-{window_start}"
        url  = f"{GAMMA_BASE}/markets?slug={slug}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data[0] if data else None
        except Exception as e:
            logger.debug("[UD] fetch error for %s: %s", slug, e)
            return None
