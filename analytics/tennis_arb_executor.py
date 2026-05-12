"""
Tennis arbitrage executor.

Extends the WS scanner with live order execution.

On ARB_OPPORTUNITY (net_edge > MIN_NET_EDGE_PCT):
  1. Refresh USDC allowance once
  2. Fire both legs in parallel via asyncio.gather
     - Both legs sign simultaneously (CPU, no lock)
     - Submissions serialized through _session_lock (~200ms gap)
  3. Handle partial fills: immediately sell the filled leg at market
  4. Track open positions, monitor for exit (winner bid > 0.95)
  5. Log all arb trades to logs/tennis_arb_trades.jsonl
  6. Persist positions across restarts via logs/tennis_arb_positions.json

Key invariant: EQUAL shares on both legs.
  Cost = N * (ask_a + ask_b). Guaranteed return = N * $1.00 via resolution.
  Profit = N * (1.0 - ask_a - ask_b) - fees.

Orphan safety: main.py orphan sweep only acts on market_type=="updown".
  Tennis neg-risk tokens are NOT touched by the orphan sweep.

RPC: NOT required. SIGNATURE_TYPE=1 (proxy wallet) — all exits via CLOB sell,
  not on-chain. Existing Redeemer handles winning position redemption.

Run as standalone:
    python3 -m analytics.tennis_arb_executor

or via systemd alongside main.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from analytics.tennis_arb_ws_scanner import TennisArbWS, net_edge_pct, LOG_DIR
from config import CONFIG
from execution.order_manager import OrderManager, OrderStatus

# ── Config ────────────────────────────────────────────────────────────────────

MAX_CAPITAL_PER_ARB = float(os.getenv("TENNIS_ARB_MAX_CAPITAL", "30"))   # $ total both legs
MIN_NET_EDGE_PCT    = float(os.getenv("TENNIS_ARB_MIN_EDGE", "3.0"))     # % net after fees

POSITIONS_FILE = Path("logs/tennis_arb_positions.json")
TRADES_LOG     = Path("logs/tennis_arb_trades.jsonl")

logger = logging.getLogger("tennis_arb_exec")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_trade(rec: dict) -> None:
    TRADES_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, separators=(",", ":"), default=str)
    with TRADES_LOG.open("a") as f:
        f.write(line + "\n")


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Executor ──────────────────────────────────────────────────────────────────

class TennisArbExecutor(TennisArbWS):
    """
    Inherits the WS scanner. Overrides _maybe_log_arb to trigger execution
    when a true arb opportunity is detected.
    """

    def __init__(self) -> None:
        super().__init__()
        self.orders = OrderManager()
        # cid → position dict (persisted to disk)
        self.arb_positions: dict[str, dict] = {}
        # cids currently being entered (prevent double-fire)
        self._in_flight: set[str] = set()
        self._load_positions()

    # ── Position persistence ──────────────────────────────────────────────────

    def _load_positions(self) -> None:
        if POSITIONS_FILE.exists():
            try:
                data = json.loads(POSITIONS_FILE.read_text())
                self.arb_positions = data
                logger.info("Loaded %d open arb positions from disk", len(data))
            except Exception as exc:
                logger.warning("Could not load positions file: %s", exc)

    def _save_positions(self) -> None:
        POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        POSITIONS_FILE.write_text(json.dumps(self.arb_positions, indent=2, default=str))

    # ── WS scanner override ───────────────────────────────────────────────────

    async def _maybe_log_arb(self, cid: str, src_token: str) -> None:
        """Log as usual, then attempt execution if edge is sufficient."""
        await super()._maybe_log_arb(cid, src_token)

        tokens = self.cid_to_tokens.get(cid)
        if not tokens or len(tokens) != 2:
            return
        ba = self.best_ask.get(tokens[0])
        bb = self.best_ask.get(tokens[1])
        if not ba or not bb:
            return

        ask_a, sz_a = ba
        ask_b, sz_b = bb
        if ask_a <= 0 or ask_b <= 0:
            return

        net = net_edge_pct(ask_a, ask_b)
        if net * 100 < MIN_NET_EDGE_PCT:
            return

        # One position per market at a time
        if cid in self._in_flight or cid in self.arb_positions:
            return

        # Equal shares capped by book depth and capital limit
        n_shares = min(sz_a, sz_b, MAX_CAPITAL_PER_ARB / (ask_a + ask_b))
        n_shares = round(n_shares, 2)
        if n_shares < 5.0:
            logger.debug("ARB SKIP: n=%.1f < 5 for %s (sum=%.3f)", n_shares, cid[:12], ask_a + ask_b)
            return

        self._in_flight.add(cid)
        asyncio.create_task(
            self._execute_arb(cid, tokens[0], tokens[1], ask_a, ask_b, sz_a, sz_b, n_shares)
        )

    # ── Execution ─────────────────────────────────────────────────────────────

    async def _execute_arb(
        self,
        cid: str,
        token_a: str,
        token_b: str,
        ask_a: float,
        ask_b: float,
        sz_a: float,
        sz_b: float,
        n_shares: float,
    ) -> None:
        meta_a = self.token_meta.get(token_a, {})
        slug      = meta_a.get("slug", "?")
        outcomes  = meta_a.get("outcomes") or []
        cost_est  = n_shares * (ask_a + ask_b)
        ts_start  = time.time()

        logger.info(
            "ARB EXECUTE: %s  sum=%.3f  n=%.1f  cost=$%.2f  net_edge=%.2f%%",
            slug, ask_a + ask_b, n_shares, cost_est,
            net_edge_pct(ask_a, ask_b) * 100,
        )

        try:
            if CONFIG.dry_run:
                logger.info("ARB DRY-RUN: would buy %.1f x %.3f + %.3f", n_shares, ask_a, ask_b)
                _log_trade({
                    "rec": "arb_dryrun", "ts": ts_start, "iso": _iso(),
                    "cid": cid, "slug": slug, "outcomes": outcomes,
                    "ask_a": ask_a, "ask_b": ask_b, "n_shares": n_shares, "cost_est": cost_est,
                })
                return

            # Single allowance refresh before both orders
            await self.orders.refresh_usdc_allowance()

            # Fire both legs simultaneously
            # create_order (signing) runs in parallel for both; post_order
            # serializes through _session_lock (~200ms gap between submissions)
            fill_a, fill_b = await asyncio.gather(
                self.orders.arb_buy(token_a, ask_a, n_shares),
                self.orders.arb_buy(token_b, ask_b, n_shares),
                return_exceptions=True,
            )

            ok_a = isinstance(fill_a, object) and not isinstance(fill_a, Exception) \
                   and fill_a.status == OrderStatus.FILLED
            ok_b = isinstance(fill_b, object) and not isinstance(fill_b, Exception) \
                   and fill_b.status == OrderStatus.FILLED

            if ok_a and ok_b:
                # Perfect: both legs filled — locked arb
                actual_a   = fill_a.avg_fill_price
                actual_b   = fill_b.avg_fill_price
                shares_a   = fill_a.total_size
                shares_b   = fill_b.total_size
                cost       = shares_a * actual_a + shares_b * actual_b
                locked_edge = min(shares_a, shares_b) * (1.0 - actual_a - actual_b)

                position = {
                    "cid":        cid,
                    "slug":       slug,
                    "outcomes":   outcomes,
                    "token_a":    token_a,
                    "token_b":    token_b,
                    "fill_a":     actual_a,
                    "fill_b":     actual_b,
                    "shares_a":   shares_a,
                    "shares_b":   shares_b,
                    "cost":       cost,
                    "locked_edge": locked_edge,
                    "ts_entry":   ts_start,
                    "status":     "BOTH_FILLED",
                }
                self.arb_positions[cid] = position
                self._save_positions()
                _log_trade({"rec": "arb_entry", "ts": ts_start, "iso": _iso(), **position})
                logger.info(
                    "ARB FILLED: %s  fill=%.3f+%.3f  cost=$%.2f  locked=$%.2f",
                    slug, actual_a, actual_b, cost, locked_edge,
                )

            elif ok_a and not ok_b:
                err_b = str(fill_b) if isinstance(fill_b, Exception) else getattr(fill_b, "error", "?")
                logger.warning("ARB PARTIAL: leg_a filled, leg_b failed (%s) — emergency sell A", err_b)
                await self._emergency_sell(token_a, fill_a.total_size, fill_a.avg_fill_price, slug, "PARTIAL_SELL_A")

            elif ok_b and not ok_a:
                err_a = str(fill_a) if isinstance(fill_a, Exception) else getattr(fill_a, "error", "?")
                logger.warning("ARB PARTIAL: leg_b filled, leg_a failed (%s) — emergency sell B", err_a)
                await self._emergency_sell(token_b, fill_b.total_size, fill_b.avg_fill_price, slug, "PARTIAL_SELL_B")

            else:
                err_a = str(fill_a) if isinstance(fill_a, Exception) else getattr(fill_a, "error", "?")
                err_b = str(fill_b) if isinstance(fill_b, Exception) else getattr(fill_b, "error", "?")
                logger.info("ARB MISS: neither leg filled for %s (a=%s b=%s)", slug, err_a, err_b)
                # Cancel any resting/delayed orders so they don't fill later without a hedge.
                # "Unfilled: delayed" means the order was accepted by CLOB but our code
                # returned before waiting — the order remains live until explicitly cancelled.
                for tid in (token_a, token_b):
                    try:
                        if self.orders._client:
                            from py_clob_client_v2.clob_types import OrderMarketCancelParams
                            await asyncio.to_thread(
                                self.orders._client.cancel_market_orders,
                                OrderMarketCancelParams(asset_id=tid),
                            )
                    except Exception as _ce:
                        logger.debug("ARB MISS cancel %s: %s", tid[:12], _ce)
                _log_trade({
                    "rec": "arb_miss", "ts": ts_start, "iso": _iso(),
                    "cid": cid, "slug": slug,
                    "ask_a": ask_a, "ask_b": ask_b, "sum_ask": ask_a + ask_b,
                    "err_a": err_a, "err_b": err_b,
                })

        except Exception as exc:
            logger.error("ARB EXECUTE error %s: %s", cid[:12], exc, exc_info=True)
        finally:
            self._in_flight.discard(cid)

    # ── Emergency sell (partial fill cleanup) ─────────────────────────────────

    async def _emergency_sell(
        self,
        token_id: str,
        shares: float,
        entry_price: float,
        slug: str,
        reason: str,
    ) -> None:
        """Market-sell a partial fill immediately to eliminate naked directional exposure."""
        try:
            results = await self.orders.cascade_sell(
                token_id=token_id,
                total_shares=shares,
                current_price=entry_price,
                reason=f"ARB_{reason}",
                neg_risk=None,
                tick_size="0.01",
                force_exit=True,
            )
            sold   = sum(r.total_size for r in results if r.status == OrderStatus.FILLED)
            total  = sum(r.avg_fill_price * r.total_size for r in results if r.status == OrderStatus.FILLED)
            avg_p  = total / sold if sold > 0 else 0.0
            pnl    = sold * (avg_p - entry_price)
            logger.warning(
                "ARB EMERGENCY SELL %s: %.2f shares @ %.4f  pnl=$%.2f", slug, sold, avg_p, pnl
            )
            _log_trade({
                "rec":          "arb_emergency_exit",
                "ts":           time.time(),
                "iso":          _iso(),
                "token_id":     token_id,
                "slug":         slug,
                "reason":       reason,
                "shares_sold":  sold,
                "exit_price":   avg_p,
                "entry_price":  entry_price,
                "pnl":          pnl,
            })
        except Exception as exc:
            logger.error("ARB EMERGENCY SELL failed %s: %s", token_id[:12], exc)

    # ── Position monitor ──────────────────────────────────────────────────────

    async def _monitor_positions_loop(self) -> None:
        """Check open arb positions every 5s for exit opportunities."""
        while True:
            await asyncio.sleep(5)
            for cid in list(self.arb_positions):
                try:
                    await self._check_exit(cid)
                except Exception as exc:
                    logger.warning("Position monitor error %s: %s", cid[:12], exc)

    async def _check_exit(self, cid: str) -> None:
        pos = self.arb_positions.get(cid)
        if not pos:
            return

        bid_a = self.best_bid.get(pos["token_a"], (0.0, 0.0))[0]
        bid_b = self.best_bid.get(pos["token_b"], (0.0, 0.0))[0]

        # Symmetric arb recovery exit: both bids sum to ≥1.00 — sell both legs now,
        # capturing the edge without waiting for resolution. This fires when MMs reprice
        # both sides upward after the arb window closes.
        if bid_a + bid_b >= 1.00 and pos.get("shares_a", 0) > 0 and pos.get("shares_b", 0) > 0:
            logger.info(
                "ARB RECOVERY EXIT: %s sum_bid=%.4f (%.4f+%.4f)",
                pos["slug"], bid_a + bid_b, bid_a, bid_b,
            )
            await asyncio.gather(
                self._sell_leg(cid, pos, "a", bid_a),
                self._sell_leg(cid, pos, "b", bid_b),
            )
            return


    async def _sell_leg(self, cid: str, pos: dict, leg: str, current_bid: float) -> None:
        token_id = pos[f"token_{leg}"]
        shares   = pos[f"shares_{leg}"]
        entry    = pos[f"fill_{leg}"]
        slug     = pos["slug"]

        try:
            results = await self.orders.cascade_sell(
                token_id=token_id,
                total_shares=shares,
                current_price=current_bid,
                reason="ARB_WIN_TAKE",
                neg_risk=None,
                tick_size="0.01",
                force_exit=True,
            )
            sold  = sum(r.total_size for r in results if r.status == OrderStatus.FILLED)
            total = sum(r.avg_fill_price * r.total_size for r in results if r.status == OrderStatus.FILLED)
            avg_p = total / sold if sold > 0 else 0.0
            pnl   = sold * (avg_p - entry)
            logger.info(
                "ARB WIN SOLD %s leg_%s: %.2f shares @ %.4f  pnl=$%.2f",
                slug, leg, sold, avg_p, pnl,
            )
            _log_trade({
                "rec":        "arb_win_exit",
                "ts":         time.time(),
                "iso":        _iso(),
                "cid":        cid,
                "slug":       slug,
                "leg":        leg,
                "shares":     sold,
                "exit_price": avg_p,
                "entry_price": entry,
                "pnl":        pnl,
            })
            pos[f"shares_{leg}"] = 0.0

            # Remove position once both legs are closed
            if pos.get("shares_a", 0) <= 0 and pos.get("shares_b", 0) <= 0:
                pos["status"] = "EXITED"
                del self.arb_positions[cid]
            self._save_positions()

        except Exception as exc:
            logger.error("ARB WIN SELL failed %s leg_%s: %s", cid[:12], leg, exc)

    # ── Pre-warm CLOB caches for new tokens ───────────────────────────────────

    async def _prewarm_tokens(self, token_ids: list[str]) -> None:
        """Pre-fetch neg_risk + fee_rate cache for new tokens (prevents 2s first-order penalty)."""
        fake_meta = {tid: {} for tid in token_ids}
        try:
            await asyncio.to_thread(self.orders.prewarm_token_caches, fake_meta)
            logger.debug("Pre-warmed %d tokens", len(token_ids))
        except Exception as exc:
            logger.debug("Prewarm failed: %s", exc)

    # ── Entry point ───────────────────────────────────────────────────────────

    async def ws_loop(self) -> None:  # type: ignore[override]
        await self.orders.start()
        asyncio.create_task(self._monitor_positions_loop())
        try:
            await super().ws_loop()
        finally:
            await self.orders.stop()

    def _register_market(self, m: dict) -> list[str]:
        """Register market and schedule pre-warming of any new tokens."""
        new_tokens = super()._register_market(m)
        if new_tokens:
            asyncio.create_task(self._prewarm_tokens(new_tokens))
        return new_tokens


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    from config import CONFIG as _cfg
    logger.info(
        "tennis_arb_executor starting  max_capital=$%.0f  min_edge=%.1f%%  dry_run=%s",
        MAX_CAPITAL_PER_ARB, MIN_NET_EDGE_PCT, _cfg.dry_run,
    )
    executor = TennisArbExecutor()
    asyncio.run(executor.ws_loop())


if __name__ == "__main__":
    main()
