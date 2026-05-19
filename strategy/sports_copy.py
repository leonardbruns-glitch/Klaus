"""
SPORTS_COPY — slippage-tolerant wallet copy-trade strategy.

Polls 5 hand-picked profitable Polymarket wallets every 30s for new trades.
When a watched wallet BUYs a token, fires our own limit BUY at wallet_price + slippage.
When the same wallet SELLs a position we hold, mirrors the SELL with slippage.
Plus stop-loss and take-profit exits independent of wallet signals.

Wallets selected from 1.06M-wallet harvest (2026-05-19):
  Combined 157 closed cycles, 539 trades in last 30 days, ROI 60-660% per cycle.
  All passed strict gates: active ≤14d, n_closed≥8, ROI≥50%, PnL≥$1k,
  basket $5-$300, avg_px≥$0.02, ≥10 trades/30d.

Default mode: SHADOW (log signals only, no orders). Flip ENABLED + LIVE_MODE
to True after shadow validation of signal flow.

Position tag: bond_entry_class = "SPORTS_COPY"
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Set, Tuple, Optional, List

import urllib.request
import urllib.error

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)

# ── Watched wallets (from FINAL_SELECTION 2026-05-19) ───────────────────────
# All passed strict gates: active ≤14d, n_closed≥8, ROI≥50%, PnL≥$1k,
# basket $5-$300, avg_px≥$0.02, ≥10 trades/30d.
WATCHED_WALLETS: dict = {
    # ── Top 5 anchor set ──
    "0x551c8f09fffa54889974a101e2af2b92c13dfe91": "W01_551c8f_PnL6k_R221_n37_155td",
    "0xf7c4415e79a85796cb74eeb137bc6dc704a35919": "W02_f7c441_PnL13k_R660_n21_123td",
    "0xd3d3d44acadda7bf4aea7769db7379383635bb8e": "W03_d3d3d4_PnL14k_R60_n42_anchor",
    "0x72d7d09901f00ba306e53b46483dc75ac2d01b97": "W04_72d7d0_PnL13k_R68_n29_152td",
    "0xdb7118f26824cfbc472aa512c798f31b665410cd": "W05_db7118_PnL5k_R102_n28",
    # ── Expanded set (ranks 6-15) ──
    "0x9b7ac362d911e3483bdf0fb95a423278bc54bc22": "W06_9b7ac3_PnL5k_R79_n27",
    "0xfb851ce2fdff625431ea2daf84ea7115af0a8464": "W07_fb851c_PnL8k_R64_n22",
    "0xb86d9f73e6bd90fb19743b59704ec6bf2d593c53": "W08_b86d9f_PnL4k_R84_n40_robust",
    "0x38faf5932f8339b700c56058c0e46848ae7f87b5": "W09_38faf5_PnL6k_R61_n44_most_robust",
    "0x99c4f423fd680fde2703619dfa51128866cb0c89": "W10_99c4f4_PnL5k_R76_n29",
    "0x4b5faccc9a9704b5c10ceb20cbdd6b4da27d1ae6": "W11_4b5fac_PnL7k_R102_n20",
    "0x7203d27522b0144113c36d25485c557c9185795a": "W12_7203d2_PnL8k_R99_n17",
    "0x412fe1a101554f0b382181c3af932e4b2d8030fa": "W13_412fe1_PnL33k_R172_n10_TOP_PNL",
    "0xe2160eb837cd17de5915d460b1d69b5ba2ac7448": "W14_e2160e_PnL25k_R83_n64_TOP_ROBUST",
    "0x18957f220cc100740b7e511b589aa6850380efd2": "W15_18957f_PnL4k_R51_n26",
    # ── Crazy-consistent-ROI expansion (ranks 16-25) ──
    # ROI×log(n_closed) ranking — high ROI weighted by robustness
    "0xd08e8f5efb47d9ff61c30e9c8546f82f7f2a2f7c": "W16_d08e8f_PnL10k_R287_n12",
    "0x338c97a8b46d22ee7c5e41f1f6276ac91e6cbef7": "W17_338c97_R260_n12_113td_BUSY",
    "0x74cde94b1c38800647dd77f52020325dfc272319": "W18_74cde9_R255_n12_micro12",
    "0xd33459882d3c1d7d4a3e100e1572d1ef4ac1fcc2": "W19_d33459_R224_n11_micro19_88sp",
    "0x1fc8b33bba54c22972a1b5786a567ae5ff45f45b": "W20_1fc8b3_R182_n14_micro20",
    "0xc8649c1893aded2f12472b44a9aaa911b6dc97df": "W21_c8649c_R152_n8",
    "0xb14cde67552e838e1a3a789995f65ab3c2887355": "W22_b14cde_R118_n14_87sp",
    "0xd91a972191b5d08671f38a0439214c49947f211c": "W23_d91a97_R102_n17_87sp",
    "0x75f3b857f3c66f8307418e64df6b49d1b0150e78": "W24_75f3b8_R85_n28_92sp_robust",
    "0xfdeada41afd6a2d91698f29a90e8017c31276951": "W25_fdeada_R121_n9_74td_86sp",
}

# ── Knobs ────────────────────────────────────────────────────────────────────
POLL_INTERVAL_S      = 30.0      # how often to scan each wallet for new trades
COPY_FRAC            = 0.30      # we stake 30% of wallet's notional
MAX_STAKE_FRAC       = 0.05      # capped at 5% of CAS-protected sub-bankroll per trade
MAX_STAKE_USD        = 10.0      # hard cap per trade (small per-trade keeps CAS unblocked)
MIN_STAKE_USD        = 1.0       # CLOB min
SLIP_BUY             = 0.05      # we pay 5c more than wallet
SLIP_SELL            = 0.05      # we get 5c less when selling
ASK_FLOOR            = 0.05      # don't chase below 5c (no fill depth)
ASK_CEIL             = 0.85      # don't chase above 85c (poor R:R)
TRADE_AGE_MAX_S      = 120.0     # ignore wallet trades older than 2 min

# Exit policy (revised 2026-05-19 23:15):
# - Primary exit: MIRROR WALLET'S SELL. The wallet is the truth signal — if it
#   hasn't sold, it sees more upside than we do. Don't pre-empt it.
# - Stop loss as catastrophe brake only. Percentage-based so it scales: a 50%
#   drawdown from entry. Absolute floor of $0.20 so micro-bets ride to res.
# - No take profit. Trust the wallet's exit timing.
STOP_LOSS_PCT        = 0.50      # exit if bid <= entry * (1 - 0.50)
STOP_LOSS_MIN_USD    = 0.20      # only fire if loss-per-share absolute is ≥ 20c

# ── CAS protection — sub-bankroll model ────────────────────────────────────
# CAS uses up to ~$60 (3 concurrent × $20). We reserve the rest for CAS and
# only deploy SPORTS_COPY within a ring-fenced sub-bankroll. Position-count
# is NOT capped — only total dollar exposure is. That way many small signals
# (e.g., $3 micro-basket copies) don't block on count.
SPORTS_COPY_SUB_BANKROLL_USD = 40.0   # max TOTAL exposure across all SPORTS_COPY positions
DAILY_PNL_FLOOR              = -10.0  # halt if daily copy PnL < -$10
# No MAX_CONCURRENT — exposure-capped instead. If avg basket is $3, we could
# hold 13 concurrent positions without blocking signal flow.

DATA_API = "https://data-api.polymarket.com"
UA = {"User-Agent": "klaus-copy/1.0"}

SHADOW_LOG_DIR = Path("logs/shadow")
SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)
SHADOW_LOG_PATH = SHADOW_LOG_DIR / "sports_copy_signals.jsonl"


def _http_get_json(url: str, timeout: float = 12.0) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logger.debug("[copy] http get failed %s: %s", url[:80], e)
        return None


class SportsCopy:
    """Slippage-tolerant wallet copy-trade strategy."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        # SAFE DEFAULT: live=False, shadow=True. Flip when ready to deploy capital.
        self.enabled: bool = True
        self.live_mode: bool = False          # False = shadow log only, no orders
        # Per-wallet seen-trade dedup (tx hashes seen)
        self._seen_tx: dict = {w: set() for w in WATCHED_WALLETS}
        self._tasks: list = []
        # Position tracking: token_id → wallet that triggered
        self._position_origin: dict = {}
        self._pending_buys: Set[str] = set()
        # PnL tracking for kill switch
        self.daily_pnl: float = 0.0
        self._daily_pnl_day: str = time.strftime("%Y-%m-%d", time.gmtime())

    async def start(self) -> None:
        """Spawn the wallet-poll loop."""
        if not self.enabled:
            return
        self._tasks.append(asyncio.create_task(self._poll_loop()))
        logger.info("[copy] started; live_mode=%s wallets=%d",
                    self.live_mode, len(WATCHED_WALLETS))

    async def stop(self) -> None:
        self.enabled = False
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # ── Main loop ────────────────────────────────────────────────────────────
    async def _poll_loop(self) -> None:
        # First pass: prime seen_tx with last ~50 trades per wallet so we don't
        # mirror historical activity on startup.
        await self._prime_seen()
        while self.enabled:
            try:
                self._roll_daily()
                if self.daily_pnl <= DAILY_PNL_FLOOR:
                    logger.warning("[copy] daily PnL floor hit ($%.2f); paused", self.daily_pnl)
                    await asyncio.sleep(POLL_INTERVAL_S * 5)
                    continue
                for wallet, label in WATCHED_WALLETS.items():
                    await self._poll_one(wallet, label)
                await asyncio.sleep(POLL_INTERVAL_S)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[copy] poll loop error")
                await asyncio.sleep(POLL_INTERVAL_S)

    async def _prime_seen(self) -> None:
        for wallet in WATCHED_WALLETS:
            trades = await asyncio.get_event_loop().run_in_executor(
                None, _http_get_json,
                f"{DATA_API}/trades?user={wallet}&limit=50")
            if isinstance(trades, list):
                for t in trades:
                    tx = t.get("transactionHash")
                    if tx:
                        self._seen_tx[wallet].add(tx)
        logger.info("[copy] primed seen-tx counts: %s",
                    {w[:10]: len(s) for w, s in self._seen_tx.items()})

    def _roll_daily(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self._daily_pnl_day:
            logger.info("[copy] daily PnL reset (was $%.2f on %s)",
                        self.daily_pnl, self._daily_pnl_day)
            self.daily_pnl = 0.0
            self._daily_pnl_day = today

    async def _poll_one(self, wallet: str, label: str) -> None:
        trades = await asyncio.get_event_loop().run_in_executor(
            None, _http_get_json,
            f"{DATA_API}/trades?user={wallet}&limit=20")
        if not isinstance(trades, list):
            return
        # Process in chronological order (API returns newest-first)
        for t in reversed(trades):
            tx = t.get("transactionHash")
            if not tx or tx in self._seen_tx[wallet]:
                continue
            self._seen_tx[wallet].add(tx)
            # Reject stale trades on first observation (warmup race)
            ts = t.get("timestamp") or 0
            age = time.time() - ts
            if age > TRADE_AGE_MAX_S:
                self._log_shadow({
                    "event": "stale_signal", "wallet": wallet, "label": label,
                    "tx": tx, "age_s": age, "trade": t,
                })
                continue
            await self._on_wallet_trade(wallet, label, t)

    # ── Trade handling ───────────────────────────────────────────────────────
    async def _on_wallet_trade(self, wallet: str, label: str, trade: dict) -> None:
        side = trade.get("side")
        token_id = str(trade.get("asset") or "")
        price = float(trade.get("price") or 0)
        size = float(trade.get("size") or 0)
        ts = trade.get("timestamp")
        slug = trade.get("slug", "")[:60]

        log_base = {
            "event": "wallet_trade", "wallet": wallet, "label": label,
            "side": side, "token_id": token_id, "price": price, "size": size,
            "ts": ts, "slug": slug, "live_mode": self.live_mode,
        }

        if side == "BUY":
            await self._consider_copy_buy(wallet, label, trade, log_base)
        elif side == "SELL":
            await self._consider_mirror_sell(wallet, label, trade, log_base)
        else:
            self._log_shadow({**log_base, "event": "unknown_side"})

    async def _consider_copy_buy(self, wallet: str, label: str, trade: dict, log_base: dict) -> None:
        token_id = str(trade["asset"])
        wallet_px = float(trade["price"])
        wallet_sz = float(trade["size"])
        wallet_notional = wallet_px * wallet_sz

        # Skip if already holding this token (don't double-up)
        if token_id in self.bot.risk.open_positions:
            self._log_shadow({**log_base, "event": "skip_already_held"})
            return

        # Bankroll halted? (shared with CAS)
        bankroll = self.bot.risk.bankroll
        if bankroll.is_ruined or bankroll.is_halted:
            self._log_shadow({**log_base, "event": "skip_bankroll_halt"})
            return

        # ── CAS protection: ring-fenced exposure budget ──
        # Sum current $ deployed across SPORTS_COPY positions.
        current_sports_exposure = sum(
            float(getattr(p, "stake", 0.0))
            for p in self.bot.risk.open_positions.values()
            if getattr(p, "bond_entry_class", "") == "SPORTS_COPY"
        )
        headroom = SPORTS_COPY_SUB_BANKROLL_USD - current_sports_exposure
        if headroom < MIN_STAKE_USD:
            self._log_shadow({**log_base, "event": "skip_subbankroll_full",
                              "current_exposure": current_sports_exposure,
                              "budget": SPORTS_COPY_SUB_BANKROLL_USD})
            return

        # Stake sizing — capped by (a) wallet's notional share, (b) per-trade cap,
        # (c) remaining sub-bankroll headroom. NOT by total bankroll percent (that
        # would shrink as CAS deploys; we use a fixed budget instead).
        stake_target = min(
            wallet_notional * COPY_FRAC,
            MAX_STAKE_USD,
            headroom,
        )
        if stake_target < MIN_STAKE_USD:
            self._log_shadow({**log_base, "event": "skip_stake_too_small", "stake": stake_target})
            return

        # Price gate
        target_price = min(wallet_px + SLIP_BUY, ASK_CEIL)
        if target_price < ASK_FLOOR:
            self._log_shadow({**log_base, "event": "skip_below_ask_floor", "target_px": target_price})
            return

        # Fetch current book to confirm fillability
        book = None
        try:
            book = self.bot.feed.get_order_book(token_id)
        except Exception:
            pass
        if book is None or not book.asks:
            self._log_shadow({**log_base, "event": "skip_no_book"})
            return

        cur_ask = book.asks[0][0]
        cur_ask_size = book.asks[0][1]
        if cur_ask > target_price:
            self._log_shadow({**log_base, "event": "skip_ask_above_target",
                              "target_px": target_price, "cur_ask": cur_ask})
            return
        # Fill at cur_ask (better than target)
        our_price = cur_ask
        our_shares = min(stake_target / our_price, cur_ask_size)
        our_stake = our_shares * our_price
        if our_stake < MIN_STAKE_USD:
            self._log_shadow({**log_base, "event": "skip_filled_too_small", "shares": our_shares})
            return

        # ── SHADOW MODE: log intent, do not fire ──
        if not self.live_mode:
            self._log_shadow({
                **log_base, "event": "SHADOW_WOULD_BUY",
                "our_price": our_price, "our_shares": our_shares, "our_stake": our_stake,
                "cur_ask": cur_ask, "cur_ask_size": cur_ask_size, "n_open": n_open,
            })
            return

        # ── LIVE MODE: fire ──
        if token_id in self._pending_buys:
            return
        self._pending_buys.add(token_id)
        try:
            fill = await asyncio.wait_for(
                self.bot.orders.limit_buy(
                    token_id=token_id,
                    intended_price=our_price,
                    stake_usd=our_stake,
                    direction=Direction.BUY_YES,
                    fast_fail=True,
                ),
                timeout=4.0,
            )
        except asyncio.TimeoutError:
            self._log_shadow({**log_base, "event": "BUY_TIMEOUT"})
            self._pending_buys.discard(token_id)
            return
        except Exception as e:
            logger.exception("[copy] limit_buy error")
            self._log_shadow({**log_base, "event": "BUY_ERROR", "err": str(e)})
            self._pending_buys.discard(token_id)
            return
        finally:
            self._pending_buys.discard(token_id)

        from execution.order_manager import OrderStatus
        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            self._log_shadow({**log_base, "event": "BUY_NOT_FILLED",
                              "fill_status": str(fill.status), "err": getattr(fill, "error", "?")})
            return

        actual_stake = fill.avg_fill_price * fill.total_size
        self._log_shadow({
            **log_base, "event": "BUY_FILLED",
            "fill_price": fill.avg_fill_price, "fill_size": fill.total_size,
            "actual_stake": actual_stake,
        })

        try:
            self.bot.risk.open_position(
                token_id=token_id,
                asset=trade.get("slug", "copy")[:20],
                direction=Direction.BUY_YES,
                stake=actual_stake,
                entry_price=fill.avg_fill_price,
                tpsl=TPSLLevels(
                    take_profit=0.0, stop_loss=0.0,
                    tp_pct=0.0, sl_pct=0.0, risk_reward=0.0,
                ),
                quality_score=0,
                binance_price_at_entry=0.0,
                is_bond=True,
                bond_outcome_direction="copy",
                bond_entry_class="SPORTS_COPY",
            )
            self._position_origin[token_id] = (wallet, time.time())
        except Exception:
            logger.exception("[copy] open_position error")

    async def _consider_mirror_sell(self, wallet: str, label: str, trade: dict, log_base: dict) -> None:
        token_id = str(trade["asset"])
        pos = self.bot.risk.open_positions.get(token_id)
        if not pos or getattr(pos, "bond_entry_class", "") != "SPORTS_COPY":
            self._log_shadow({**log_base, "event": "sell_no_match"})
            return
        origin = self._position_origin.get(token_id)
        if not origin or origin[0] != wallet:
            self._log_shadow({**log_base, "event": "sell_wallet_mismatch", "origin": origin})
            return
        wallet_sell_px = float(trade["price"])
        target_sell_px = max(wallet_sell_px - SLIP_SELL, 0.01)

        if not self.live_mode:
            self._log_shadow({
                **log_base, "event": "SHADOW_WOULD_SELL",
                "wallet_sell_px": wallet_sell_px, "target_sell_px": target_sell_px,
                "entry_px": getattr(pos, "entry_price", 0.0),
            })
            return

        # LIVE: market sell via order manager (caller-provided exit path)
        try:
            await self.bot._exit_position(token_id, target_sell_px, "SPORTS_COPY_MIRROR_SELL")
            self._log_shadow({**log_base, "event": "SELL_FIRED",
                              "target_px": target_sell_px})
        except Exception:
            logger.exception("[copy] mirror sell error")

    # ── Catastrophe stop-loss only (called periodically from main bot tick) ──
    # No take-profit — wallet's SELL is the truth signal.
    async def check_stop_take(self) -> None:
        """Called by main bot loop ~every 5s. Percentage stop-loss only."""
        for token_id, pos in list(self.bot.risk.open_positions.items()):
            if getattr(pos, "bond_entry_class", "") != "SPORTS_COPY":
                continue
            try:
                book = self.bot.feed.get_order_book(token_id)
            except Exception:
                continue
            if not book or not book.bids:
                continue
            cur_bid = book.bids[0][0]
            entry = float(getattr(pos, "entry_price", 0.0))
            if entry <= 0:
                continue
            # Percentage drawdown from entry
            dd_pct = (entry - cur_bid) / entry
            shares = float(getattr(pos, "shares", 0.0))
            loss_per_share_usd = entry - cur_bid

            # Only fire stop if BOTH %dd is large AND absolute loss is meaningful
            # (so a 50% drop on a $0.04 token = $0.02/share doesn't trigger)
            if dd_pct >= STOP_LOSS_PCT and loss_per_share_usd >= STOP_LOSS_MIN_USD:
                if not self.live_mode:
                    self._log_shadow({"event": "SHADOW_WOULD_STOP", "token_id": token_id,
                                       "entry": entry, "cur_bid": cur_bid,
                                       "dd_pct": dd_pct, "loss_per_sh": loss_per_share_usd})
                    continue
                try:
                    await self.bot._exit_position(token_id, cur_bid, "SPORTS_COPY_STOP")
                    self._log_shadow({"event": "STOP_FIRED", "token_id": token_id,
                                       "entry": entry, "exit_bid": cur_bid,
                                       "dd_pct": dd_pct})
                except Exception:
                    logger.exception("[copy] stop-loss exit failed")

    # ── Shadow logging ───────────────────────────────────────────────────────
    def _log_shadow(self, entry: dict) -> None:
        try:
            entry["ts_log"] = time.time()
            with open(SHADOW_LOG_PATH, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
