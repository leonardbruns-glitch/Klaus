"""Two-sided crypto updown arb strategy.

When YES_ask + NO_ask < 0.99 for a 5-min window, buy both tokens simultaneously.
Profit = (1 - sum_ask) × n_shares at resolution, direction-independent.

Exit:
  1. sum_bid >= 1.00  → sell both legs immediately (edge captured, capital recycled)
  2. T-4s before window end → sell both legs as fallback

Config (env vars, read at import time via .env):
  CRYPTO_ARB_STAKE    default 5.0   $ per leg
  CRYPTO_ARB_EDGE     default 0.015 min net edge after fees (fraction)
  CRYPTO_ARB_MAX_POS  default 3     max concurrent positions
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

STAKE        = float(os.getenv("CRYPTO_ARB_STAKE",   "5.0"))
MIN_EDGE     = float(os.getenv("CRYPTO_ARB_EDGE",    "0.015"))
MAX_POS      = int(os.getenv("CRYPTO_ARB_MAX_POS",   "3"))
EXIT_BEFORE  = 4.0   # seconds before window end


def _fee(p: float) -> float:
    d = abs(p - 0.50)
    if d >= 0.15:
        return 0.005
    return 0.018 - 0.013 * (d / 0.15)


def _net_edge(ask_yes: float, ask_no: float) -> float:
    return 1.0 - ask_yes - ask_no - _fee(ask_yes) - _fee(ask_no)


class CryptoArbStrategy:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.enabled: bool = False

        # cid → {token_yes, token_no, shares, ask_yes, ask_no, cost, window_end_ts, asset}
        self._positions: Dict[str, dict] = {}
        # condition_ids currently in-flight (entry not yet settled)
        self._in_flight: Set[str] = set()
        # condition_ids traded this window (dedup until window expires)
        self._traded: Set[Tuple[str, int]] = set()  # (cid, window_end_ts)
        # exit tasks keyed by cid
        self._exit_tasks: Dict[str, asyncio.Task] = {}
        # monitor task (started once)
        self._monitor_task: Optional[asyncio.Task] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start_monitor(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(
                self._monitor_loop(), name="crypto_arb_monitor"
            )

    # ── Scan (called from main bot loop) ─────────────────────────────────────

    async def scan(self) -> None:
        if not self.enabled:
            return
        self.start_monitor()

        now = time.time()
        # GC stale dedup entries
        self._traded = {(c, w) for c, w in self._traded if w > now - 60}

        seen_cids: Set[str] = set()

        for token_id, token in list(self.bot.feed.tokens.items()):
            try:
                cid = getattr(token, "condition_id", "") or ""
                if not cid or cid in seen_cids:
                    continue
                seen_cids.add(cid)

                wend = int(getattr(token, "window_end_ts", 0))
                if (cid, wend) in self._traded:
                    continue
                if cid in self._in_flight or cid in self._positions:
                    continue
                if len(self._positions) >= MAX_POS:
                    continue

                spec = self._should_fire(cid, token_id, token, now)
                if spec is None:
                    continue

                self._traded.add((cid, wend))
                self._in_flight.add(cid)
                asyncio.create_task(
                    self._enter(cid, *spec),
                    name=f"crypto_arb_enter_{cid[:8]}",
                )
            except Exception:
                logger.exception("[CRYPTO_ARB] scan error cid=%s", cid[:12] if cid else "?")

    def _should_fire(self, cid: str, token_id: str, token, now: float):
        """Return (yes_tid, no_tid, ask_yes, ask_no, ask_size_yes, ask_size_no, n_shares, wend, asset)
        or None."""
        # 5-min windows only
        if int(getattr(token, "window_seconds", 0)) != 300:
            return None
        wend = getattr(token, "window_end_ts", 0)
        if wend <= 0:
            return None
        rem = wend - now
        if rem < 30:
            return None

        asset = str(getattr(token, "asset", "")).upper()
        if asset not in ("ETH", "BTC", "SOL"):
            return None

        # Get this token's OB
        ob = self.bot.feed.get_order_book(token_id)
        if ob is None or not ob.asks:
            return None
        ask_a = ob.asks[0][0]
        sz_a  = ob.asks[0][1]

        # Find peer (same condition_id, different token)
        peer_tid = peer_ask = peer_sz = None
        for ptid, ptok in self.bot.feed.tokens.items():
            if ptid == token_id:
                continue
            if getattr(ptok, "condition_id", "") != cid:
                continue
            pob = self.bot.feed.get_order_book(ptid)
            if pob is None or not pob.asks:
                return None
            peer_tid  = ptid
            peer_ask  = pob.asks[0][0]
            peer_sz   = pob.asks[0][1]
            break

        if peer_tid is None or peer_ask is None:
            return None

        arb_sum = ask_a + peer_ask
        if arb_sum >= 0.99:
            return None
        if _net_edge(ask_a, peer_ask) < MIN_EDGE:
            return None

        # Determine YES/NO order (outcome_dir: "up" = YES side)
        outcome_dir = getattr(token, "outcome_direction", "")
        if outcome_dir == "up":
            yes_tid, no_tid = token_id, peer_tid
            ask_yes, ask_no = ask_a, peer_ask
            sz_yes, sz_no   = sz_a, peer_sz
        else:
            yes_tid, no_tid = peer_tid, token_id
            ask_yes, ask_no = peer_ask, ask_a
            sz_yes, sz_no   = peer_sz, sz_a

        n_shares = min(sz_yes, sz_no, STAKE / ask_yes, STAKE / ask_no)
        n_shares = round(n_shares, 2)
        if n_shares < 1.0:
            return None

        return yes_tid, no_tid, ask_yes, ask_no, sz_yes, sz_no, n_shares, int(wend), asset

    # ── Entry ────────────────────────────────────────────────────────────────

    async def _enter(
        self, cid: str,
        yes_tid: str, no_tid: str,
        ask_yes: float, ask_no: float,
        sz_yes: float, sz_no: float,
        n_shares: float, wend: int, asset: str,
    ) -> None:
        from execution.order_manager import OrderStatus
        slug = f"{asset}_arb_{wend}"
        try:
            logger.info(
                "[CRYPTO_ARB] enter %s  sum=%.3f  n=%.1f  cost=$%.2f  edge=%.2f%%",
                slug, ask_yes + ask_no, n_shares,
                n_shares * (ask_yes + ask_no), _net_edge(ask_yes, ask_no) * 100,
            )

            await self.bot.orders.refresh_usdc_allowance()

            fill_yes, fill_no = await asyncio.gather(
                self.bot.orders.arb_buy(yes_tid, ask_yes, n_shares),
                self.bot.orders.arb_buy(no_tid,  ask_no,  n_shares),
                return_exceptions=True,
            )

            ok_yes = not isinstance(fill_yes, Exception) and fill_yes.status == OrderStatus.FILLED
            ok_no  = not isinstance(fill_no,  Exception) and fill_no.status  == OrderStatus.FILLED

            if ok_yes and ok_no:
                cost = fill_yes.avg_fill_price * fill_yes.total_size + fill_no.avg_fill_price * fill_no.total_size
                pos = {
                    "cid": cid, "asset": asset, "wend": wend,
                    "yes_tid": yes_tid, "no_tid": no_tid,
                    "shares": min(fill_yes.total_size, fill_no.total_size),
                    "ask_yes": fill_yes.avg_fill_price,
                    "ask_no":  fill_no.avg_fill_price,
                    "cost": cost,
                }
                self._positions[cid] = pos
                logger.info(
                    "[CRYPTO_ARB] filled %s  yes=%.3f no=%.3f  cost=$%.2f  locked=$%.3f",
                    slug, pos["ask_yes"], pos["ask_no"], cost,
                    pos["shares"] * (1.0 - pos["ask_yes"] - pos["ask_no"]),
                )
                # Schedule T-4s exit
                exit_at = wend - EXIT_BEFORE
                self._exit_tasks[cid] = asyncio.create_task(
                    self._exit_at_t4(cid, exit_at),
                    name=f"crypto_arb_exit_{cid[:8]}",
                )

            elif ok_yes and not ok_no:
                logger.warning("[CRYPTO_ARB] partial YES filled — emergency sell YES")
                await self._emergency_sell(yes_tid, fill_yes.total_size, fill_yes.avg_fill_price, slug)
                await self._cancel_both(yes_tid, no_tid)

            elif ok_no and not ok_yes:
                logger.warning("[CRYPTO_ARB] partial NO filled — emergency sell NO")
                await self._emergency_sell(no_tid, fill_no.total_size, fill_no.avg_fill_price, slug)
                await self._cancel_both(yes_tid, no_tid)

            else:
                err_y = str(fill_yes) if isinstance(fill_yes, Exception) else getattr(fill_yes, "error", "?")
                err_n = str(fill_no)  if isinstance(fill_no,  Exception) else getattr(fill_no,  "error", "?")
                logger.info("[CRYPTO_ARB] miss %s (yes=%s no=%s)", slug, err_y, err_n)
                await self._cancel_both(yes_tid, no_tid)

        except Exception:
            logger.exception("[CRYPTO_ARB] enter error %s", cid[:12])
        finally:
            self._in_flight.discard(cid)

    async def _cancel_both(self, yes_tid: str, no_tid: str) -> None:
        from py_clob_client_v2.clob_types import OrderMarketCancelParams
        for tid in (yes_tid, no_tid):
            try:
                if self.bot.orders._client:
                    await asyncio.to_thread(
                        self.bot.orders._client.cancel_market_orders,
                        OrderMarketCancelParams(asset_id=tid),
                    )
            except Exception as e:
                logger.debug("[CRYPTO_ARB] cancel %s: %s", tid[:12], e)

    async def _emergency_sell(self, token_id: str, shares: float, entry: float, slug: str) -> None:
        from execution.order_manager import OrderStatus
        try:
            results = await self.bot.orders.cascade_sell(
                token_id=token_id, total_shares=shares, current_price=entry,
                reason="CRYPTO_ARB_PARTIAL", neg_risk=None, tick_size="0.01", force_exit=True,
            )
            sold = sum(r.total_size for r in (results or []) if r.status == OrderStatus.FILLED)
            logger.warning("[CRYPTO_ARB] emergency sell %s: %.2f shares sold", slug, sold)
        except Exception:
            logger.exception("[CRYPTO_ARB] emergency sell failed %s", slug)

    # ── Exit ─────────────────────────────────────────────────────────────────

    async def _monitor_loop(self) -> None:
        """Every 5s: sell both legs if sum_bid >= 1.00."""
        while True:
            await asyncio.sleep(5)
            for cid in list(self._positions):
                try:
                    await self._check_exit(cid)
                except Exception:
                    logger.exception("[CRYPTO_ARB] monitor error %s", cid[:12])

    async def _check_exit(self, cid: str) -> None:
        pos = self._positions.get(cid)
        if not pos:
            return
        ob_yes = self.bot.feed.get_order_book(pos["yes_tid"])
        ob_no  = self.bot.feed.get_order_book(pos["no_tid"])
        if not ob_yes or not ob_no:
            return
        bid_yes = ob_yes.bids[0][0] if ob_yes.bids else 0.0
        bid_no  = ob_no.bids[0][0]  if ob_no.bids  else 0.0
        if bid_yes + bid_no >= 1.00:
            logger.info(
                "[CRYPTO_ARB] recovery exit %s  sum_bid=%.4f (%.3f+%.3f)",
                pos["asset"], bid_yes + bid_no, bid_yes, bid_no,
            )
            await self._sell_both(cid, bid_yes, bid_no)

    async def _exit_at_t4(self, cid: str, exit_at: float) -> None:
        try:
            await asyncio.sleep(max(0.0, exit_at - time.time()))
            if cid not in self._positions:
                return
            pos = self._positions[cid]
            ob_yes = self.bot.feed.get_order_book(pos["yes_tid"])
            ob_no  = self.bot.feed.get_order_book(pos["no_tid"])
            bid_yes = ob_yes.bids[0][0] if (ob_yes and ob_yes.bids) else 0.0
            bid_no  = ob_no.bids[0][0]  if (ob_no  and ob_no.bids)  else 0.0
            logger.info(
                "[CRYPTO_ARB] T-4s exit %s  sum_bid=%.4f", pos["asset"], bid_yes + bid_no,
            )
            await self._sell_both(cid, bid_yes, bid_no)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[CRYPTO_ARB] T-4s exit error %s", cid[:12])
        finally:
            self._exit_tasks.pop(cid, None)

    async def _sell_both(self, cid: str, bid_yes: float, bid_no: float) -> None:
        from execution.order_manager import OrderStatus
        pos = self._positions.pop(cid, None)
        if not pos:
            return
        # Cancel any scheduled T-4s exit since we're exiting now
        task = self._exit_tasks.pop(cid, None)
        if task and not task.done():
            task.cancel()

        shares = pos["shares"]
        res_yes, res_no = await asyncio.gather(
            self.bot.orders.cascade_sell(
                token_id=pos["yes_tid"], total_shares=shares, current_price=bid_yes,
                reason="CRYPTO_ARB_EXIT", neg_risk=None, tick_size="0.01", force_exit=True,
            ),
            self.bot.orders.cascade_sell(
                token_id=pos["no_tid"],  total_shares=shares, current_price=bid_no,
                reason="CRYPTO_ARB_EXIT", neg_risk=None, tick_size="0.01", force_exit=True,
            ),
            return_exceptions=True,
        )
        recv = 0.0
        for res in (res_yes, res_no):
            if isinstance(res, list):
                recv += sum(r.avg_fill_price * r.total_size for r in res if r.status == OrderStatus.FILLED)
        pnl = recv - pos["cost"]
        logger.info(
            "[CRYPTO_ARB] closed %s  recv=$%.2f  cost=$%.2f  pnl=$%+.3f",
            pos["asset"], recv, pos["cost"], pnl,
        )
