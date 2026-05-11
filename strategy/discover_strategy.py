"""Phase 2 Discovery — single-signal live entry path.

DISABLED BY DEFAULT (`self.enabled = False`). Enable by setting
`bot.discover_strategy.enabled = True` AND disabling BOND
(`BOND_ENABLED = False` in main.py) — only one strategy active at a time
per user instruction.

Signal (mirrors data/shadow/discover_signal.matches() exactly):
    arb_sum_yes_no in (0, 0.99)
    AND outcome_dir == "down"
    AND best_ask in [0.10, 0.40]
    AND seconds_to_resolution in [60, 240]
    AND window_size_s == 300                   # 5m only

Entry: adaptive stake.
    floor = max($1, 5 * ask)                   # Polymarket $1 + 5-share min
    target = $5
    fill = min(target, ask_size * ask)         # depth-limited
    skip if fill < floor

Exit: T-15s via asyncio.create_task scheduled at entry time.

Risk caps:
    daily_loss_limit:        -$10  (halt for the day)
    max_concurrent:           3 positions
    consecutive_loss_halt:    5 consecutive losses → halt until manual reset

Position tracking uses risk.open_positions with bond_entry_class="DISCOVER"
so the existing kill-switch / capital tracker still applies. The position
monitor in main.py must skip TP/SL checks for DISCOVER positions (handled
via is_bond=True + the T-15 sell scheduled here).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Set, Tuple, Dict

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)


class DiscoverStrategy:
    def __init__(self, bot) -> None:
        self.bot = bot
        # ACTIVE 2026-05-10: switched on at restart together with BOND_ENABLED=False.
        # Flip back to False to disable; flip BOND_ENABLED=True in window_sniper.py
        # to revert to the prior strategy. Only one of the two should be True.
        self.enabled: bool = True
        # Per-window dedup: (token_id, window_end_ts).
        self._traded_windows: Set[Tuple[str, int]] = set()
        # token_id -> exit task
        self._exit_tasks: Dict[str, asyncio.Task] = {}
        # Sizing
        self.target_stake: float = 3.00
        self.entry_floor_usd: float = 1.00
        self.share_min: int = 5
        # Risk caps (separate from BOND).
        # 2026-05-10: user-authorised override — no killswitches for this run.
        # daily_loss_limit and consecutive_loss_halt set to values that cannot
        # trigger. max_concurrent kept at 3 as a position-sizing bound, not a halt.
        self.daily_loss_limit: float = float("-inf")
        self.max_concurrent: int = 3
        self.consecutive_loss_halt: int = 10**9
        # State
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: str = ""
        self._consecutive_losses: int = 0
        self._halted: bool = False
        # Exit cadence: sell EXIT_BEFORE_END_S seconds before window_end.
        self.exit_before_end_s: float = 15.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _maybe_reset_daily(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_pnl_date:
            if self._daily_pnl_date:
                logger.info(
                    "[DISCOVER] daily reset: prior date=%s pnl=%+.2f",
                    self._daily_pnl_date, self._daily_pnl,
                )
            self._daily_pnl = 0.0
            self._daily_pnl_date = today

    def _open_count(self) -> int:
        return sum(
            1 for p in self.bot.risk.open_positions.values()
            if getattr(p, "bond_entry_class", "") == "DISCOVER"
        )

    # ── Scan ─────────────────────────────────────────────────────────────────

    async def scan(self) -> None:
        if not self.enabled:
            return
        if self._halted:
            return
        self._maybe_reset_daily()
        if self._daily_pnl <= self.daily_loss_limit:
            if not self._halted:
                logger.warning(
                    "[DISCOVER] daily_loss_halt: pnl=%+.2f <= limit=%+.2f",
                    self._daily_pnl, self.daily_loss_limit,
                )
                self._halted = True
            return
        if self._open_count() >= self.max_concurrent:
            return
        # GC stale dedup (windows ended >5min ago)
        now = time.time()
        self._traded_windows = {
            (tid, wend) for (tid, wend) in self._traded_windows
            if wend > now - 300
        }
        for token_id, token in list(self.bot.feed.tokens.items()):
            try:
                spec = self._should_fire(token_id, token, now)
                if spec is None:
                    continue
                # Acquire window lock BEFORE await — single-threaded asyncio
                # makes this race-safe.
                wend = int(getattr(token, "window_end_ts", 0))
                key = (token_id, wend)
                if key in self._traded_windows:
                    continue
                self._traded_windows.add(key)
                await self._enter(token_id, token, now, spec)
            except Exception:
                logger.exception("[DISCOVER] scan failed token=%s", token_id[:12])

    def _should_fire(self, token_id: str, token, now: float):
        """Return (signal_class, target_stake_usd, outcome_dir) or None.

        S2: arb<0.99 + DOWN + ask 0.10-0.40 + rem 60-180, $3 stake.
            rem tightened 60-240 -> 60-180 on 2026-05-10: n=160 CI [+0.27,+3.07]
            cleanly positive vs n=218 rem 60-240 CI [+0.01,+2.31] just barely.

        S3 (UP) was deployed 2026-05-10 22:25 UTC and reverted 2026-05-10 22:35 UTC:
        the headline EV mixed 5m + 15m windows; 5m-only S3 cell n=105 EV +$1.37
        CI [-0.22, +2.96] does not pass CI-lo > 0.
        """
        # 5m only
        if int(getattr(token, "window_seconds", 0)) != 300:
            return None
        # Asset whitelist: BTC + ETH only (SOL EV +$0.32/trade, marginal — blocked 2026-05-10)
        if str(getattr(token, "asset", "")).upper() not in ("BTC", "ETH"):
            return None
        wend = getattr(token, "window_end_ts", 0)
        if wend <= 0:
            return None
        rem = wend - now
        # Already traded this window?
        if (token_id, int(wend)) in self._traded_windows:
            return None
        # Position open already (other path)?
        if token_id in self.bot.risk.open_positions:
            return None
        # Need order book + peer book for arb
        ob = self.bot.feed.get_order_book(token_id)
        if ob is None or not ob.asks:
            return None
        ask = ob.asks[0][0]
        ask_size = ob.asks[0][1]
        # S2 (DOWN) only
        outcome_dir = getattr(token, "outcome_direction", "")
        if outcome_dir != "down":
            return None
        if not (60 <= rem <= 180):
            return None
        if not (0.10 <= ask <= 0.40):
            return None
        signal_class = "S2"
        target_stake = 3.00
        # Find peer for arb_sum
        cid = getattr(token, "condition_id", "") or ""
        if not cid:
            return None
        peer_ask = 0.0
        for ptid, ptok in self.bot.feed.tokens.items():
            if ptid == token_id:
                continue
            if getattr(ptok, "condition_id", "") != cid:
                continue
            pob = self.bot.feed.get_order_book(ptid)
            if pob is None or not pob.asks:
                return None
            peer_ask = pob.asks[0][0]
            break
        if peer_ask <= 0:
            return None
        arb_sum = ask + peer_ask
        if not (0.0 < arb_sum < 0.99):
            return None
        # Adaptive feasibility check (same as live execution)
        floor = max(self.entry_floor_usd, self.share_min * ask)
        if ask_size < self.share_min:
            return None
        inventory = ask * ask_size
        fill = min(target_stake, inventory)
        if fill < floor:
            return None
        return (signal_class, target_stake, outcome_dir)

    # ── Entry ────────────────────────────────────────────────────────────────

    async def _enter(self, token_id: str, token, now: float, spec) -> None:
        signal_class, target_stake, outcome_dir = spec
        ob = self.bot.feed.get_order_book(token_id)
        ask = ob.asks[0][0]
        ask_size = ob.asks[0][1]
        wend = int(getattr(token, "window_end_ts", 0))
        rem = wend - now

        floor = max(self.entry_floor_usd, self.share_min * ask)
        inventory = ask * ask_size
        target_fill = min(target_stake, inventory)
        target_fill = max(target_fill, floor)  # ensure floor met (guarded above)

        logger.info(
            "[DISCOVER:%s] enter %s/%s ask=%.4f size=%.1f rem=%.0fs target_fill=$%.2f dir=%s",
            signal_class, token.asset, getattr(token, "side", "?"),
            ask, ask_size, rem, target_fill, outcome_dir,
        )

        # Place market_buy via existing OrderManager (handles 5-share min snap).
        fill = await self.bot.orders.market_buy(
            token_id=token_id,
            intended_price=ask,
            stake_usd=target_fill,
            direction=Direction.BUY_YES,
            neg_risk=getattr(token, "neg_risk", False),
            tick_size=getattr(token, "tick_size", "0.01"),
        )
        if fill.avg_fill_price == 0 or fill.total_size == 0:
            logger.warning(
                "[DISCOVER] fill failed %s: %s",
                token.asset, fill.error or "unknown",
            )
            # Release window lock so a later tick can retry (rare).
            self._traded_windows.discard((token_id, wend))
            return

        actual_stake = fill.avg_fill_price * fill.total_size
        # Track in risk so the bot's existing capital/kill-switch math applies.
        # is_bond=True suppresses TP/SL — we exit via the scheduled task only.
        # bond_entry_class="DISCOVER" lets the position monitor skip BOND-specific exits.
        tpsl = TPSLLevels(
            take_profit=0.0,
            stop_loss=0.0,
            tp_pct=0.0,
            sl_pct=0.0,
            risk_reward=0.0,
        )
        # Build a minimal "signal" object the risk tracker can read.
        class _Sig:
            signal_source = "DISCOVER"
            entry_price = fill.avg_fill_price
            direction = Direction.BUY_YES
        sig = _Sig()

        try:
            self.bot.risk.open_position(
                token_id=token_id,
                asset=token.asset,
                direction=Direction.BUY_YES,
                stake=actual_stake,
                entry_price=fill.avg_fill_price,
                tpsl=tpsl,
                condition_id=getattr(token, "condition_id", ""),
                window_end_ts=wend,
                window_seconds=int(getattr(token, "window_seconds", 300)),
                quality_score=0,
                binance_price_at_entry=self.bot.feed._spot_price.get(
                    token.asset.upper(), 0.0
                ),
                is_bond=True,
                bond_outcome_direction=outcome_dir,
                bond_entry_class="DISCOVER",
            )
        except Exception:
            logger.exception("[DISCOVER] risk.open_position failed %s", token.asset)
            return

        # Schedule T-15 sell.
        exit_at = wend - self.exit_before_end_s
        task = asyncio.create_task(
            self._exit_at_t15(token_id, exit_at, fill.total_size, token.asset),
            name=f"discover_exit_{token_id[:8]}",
        )
        self._exit_tasks[token_id] = task

    # ── Exit ─────────────────────────────────────────────────────────────────

    async def _exit_at_t15(
        self, token_id: str, exit_at_ts: float, shares: float, asset: str,
    ) -> None:
        try:
            sleep_s = max(0.0, exit_at_ts - time.time())
            await asyncio.sleep(sleep_s)
            pos = self.bot.risk.open_positions.get(token_id)
            if pos is None:
                logger.info("[DISCOVER] T-15 fire %s — position already closed", asset)
                return
            ob = self.bot.feed.get_order_book(token_id)
            cur_bid = ob.bids[0][0] if (ob and ob.bids) else 0.0
            tok = self.bot.feed.tokens.get(token_id)
            _neg = bool(getattr(tok, "neg_risk", False)) if tok else False
            _tick = str(getattr(tok, "tick_size", "0.01")) if tok else "0.01"
            logger.info(
                "[DISCOVER] T-15 sell %s shares=%.4f bid=%.4f",
                asset, shares, cur_bid,
            )
            results = await self.bot.orders.cascade_sell(
                token_id=token_id,
                total_shares=shares,
                current_price=cur_bid,
                reason="DISCOVER_T15",
                neg_risk=_neg,
                tick_size=_tick,
                force_exit=True,
            )
            # P&L bookkeeping (rough — use first-fill price; risk manager will
            # do its own bookkeeping when the position closes).
            recv = sum(r.avg_fill_price * r.total_size for r in (results or [])
                       if getattr(r, "avg_fill_price", 0))
            if recv > 0 and pos is not None:
                trade_pnl = recv - pos.stake
                self._daily_pnl += trade_pnl
                if trade_pnl < 0:
                    self._consecutive_losses += 1
                    if self._consecutive_losses >= self.consecutive_loss_halt:
                        logger.warning(
                            "[DISCOVER] consec_loss_halt: %d consecutive losses",
                            self._consecutive_losses,
                        )
                        self._halted = True
                else:
                    self._consecutive_losses = 0
                logger.info(
                    "[DISCOVER] closed %s pnl=%+.2f daily=%+.2f consec_losses=%d",
                    asset, trade_pnl, self._daily_pnl, self._consecutive_losses,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[DISCOVER] T-15 sell failed %s", asset)
        finally:
            self._exit_tasks.pop(token_id, None)
