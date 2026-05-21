"""
STRATEGY — NO_SIDE ARBITRAGE.

Edge thesis:
    Mirror of overnight NWP arb but on the NO side. When the modal bucket is
    OVERPRICED on Polymarket (poly_yes ≥ 0.50 but our model gives it materially
    less probability), the NO token is correspondingly UNDERPRICED.

    NO token costs (1 − poly_yes); pays $1 if outcome NOT in this bucket.
    Profit per share if win = poly_yes (since we paid 1 − poly_yes for $1 payout).

Backtest verdict (6mo, 23 cities):
    n=26, WR=92.3%, EV/bet=+$11.80, PF=8.70, total +$307.
    Low fire-rate because synthetic market priced efficiently. Live retail
    noise is wider — expect 3-5× more fires in production.

Mechanism:
    1. Scan all today's-market buckets for negRisk events.
    2. Get ensemble μ + σ; compute fair_prob per bucket.
    3. Find bucket where poly_yes ≥ 0.50 AND fair_prob ≤ poly_yes − EDGE_MIN.
    4. Compute NO ask = 1 − poly_yes + spread. Compute NO fair = 1 − fair_prob.
    5. If edge_no = no_fair − no_ask ≥ NOSIDE_EDGE_MIN → place GTC maker order
       on the NO token at (no_ask − 1¢) to earn rebate.
    6. Hold to resolution. NO wins if actual ≠ bucket.

This is essentially the inverse of STRAT_1 — we capture the opposite-side
mispricing that STRAT_1 ignored.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta, date
from typing import Optional

logger = logging.getLogger(__name__)


# ── Strategy parameters ──────────────────────────────────────────────────────
NOSIDE_ENABLED            = True
NOSIDE_MIN_POLY_YES       = 0.50    # only consider NO when YES priced as majority
NOSIDE_MAX_POLY_YES       = 0.85    # very-deep favorites are reliably right
NOSIDE_EDGE_MIN           = 0.08    # net edge after rebate
NOSIDE_BANKROLL_FRAC      = 0.10    # 10% of bankroll reserved
NOSIDE_PER_POSITION       = 0.04    # 4% per position
NOSIDE_MIN_STAKE          = 5.0
NOSIDE_MAX_STAKE          = 20.0
NOSIDE_MAX_CONCURRENT     = 3
NOSIDE_SCAN_INTERVAL_S    = 3600    # 1h scan loop


class NoSideArb:
    """NO-side mirror of STRAT_1 — maker GTC on NO tokens, hold to resolution."""

    def __init__(self, bot) -> None:
        self.bot      = bot
        self._task: Optional[asyncio.Task] = None
        self._fired:  set[str] = set()      # NO token_ids already entered
        self._enabled = NOSIDE_ENABLED

    def start(self) -> None:
        if not self._enabled:
            logger.info("[NOSIDE] disabled by config")
            return
        self._task = asyncio.create_task(self._loop(), name="no_side_arb_loop")
        logger.info("[NOSIDE] started — fires when YES≥%.2f, edge≥%.2f",
                    NOSIDE_MIN_POLY_YES, NOSIDE_EDGE_MIN)

    async def _loop(self) -> None:
        await asyncio.sleep(180.0)  # wait for bot + weather_arb init
        while True:
            try:
                await self._scan()
            except Exception:
                logger.exception("[NOSIDE] scan error")
            await asyncio.sleep(NOSIDE_SCAN_INTERVAL_S)

    async def _scan(self) -> None:
        from analysis.weather.daily_audit import is_killed
        if is_killed("WEATHER_NOSIDE"):
            logger.info("[NOSIDE] auto-killed by daily_audit — skipping scan")
            return
        wa = getattr(self.bot, "weather_arb", None)
        if wa is None:
            return
        await wa._refresh_today_markets()
        markets = wa._today_markets_cache or []
        if not markets:
            return

        if len(self._fired) >= NOSIDE_MAX_CONCURRENT:
            logger.info("[NOSIDE] %d slots full", len(self._fired))
            return

        from strategy.weather_arb import (
            CITY_NAME_TO_SLUG, CITY_SIGMA_C, _outcome_prob, _parse_outcome,
            _parse_token_ids,
        )
        from strategy.fee_model import MAKER_REBATE_FRAC, taker_fee_rate

        now_utc = datetime.now(timezone.utc)
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        today_str = date.today().isoformat()

        scanned_cities: set[str] = set()
        entries_made = 0

        for entry in markets:
            city = entry["city"]
            mkt  = entry["mkt"]
            if mkt.get("closed", False):
                continue
            token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            if len(token_ids) < 2:
                # negRisk markets expose [YES, NO] — single-token markets skip
                continue
            yes_token, no_token = token_ids[0], token_ids[1]
            if no_token in self._fired or no_token in wa._fired_tokens:
                continue
            # Conflict gate: skip if we already hold YES for this bucket
            if yes_token in wa._fired_tokens:
                continue

            end_date = mkt.get("endDate", "")[:10]
            if end_date not in (today_str, tomorrow_str):
                continue

            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            poly_yes   = float(prices[0])
            if poly_yes < NOSIDE_MIN_POLY_YES or poly_yes > NOSIDE_MAX_POLY_YES:
                continue

            lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
            if lo_c is None and hi_c is None:
                continue

            scanned_cities.add(city)
            slug = CITY_NAME_TO_SLUG.get(city, "")

            if end_date == today_str:
                # Today's market: use live METAR nowcast (same signal as INTRADAY)
                icao = entry.get("icao", "")
                obs  = wa._icao_metar_cache.get(icao) if icao else None
                if obs is None:
                    obs = await wa._refresh_open_meteo_live(entry["lat"], entry["lon"])
                if not obs:
                    continue
                running_max = obs.get("running_max_c")
                temp_c_obs  = obs.get("temp_c")
                sky_cover   = obs.get("sky_cover", "CLR")
                if running_max is None or temp_c_obs is None:
                    continue
                try:
                    mu_now, sigma_now = await wa._nowcast_max(
                        entry["lat"], entry["lon"], running_max, temp_c_obs,
                        sky_cover, city,
                    )
                except Exception:
                    continue
                fair_yes = _outcome_prob(mu_now, lo_c, hi_c, sigma_now)
            else:
                # Tomorrow's market: use overnight NWP ensemble (same signal as OVERNIGHT)
                try:
                    forecast = await wa._get_forecast(entry["lat"], entry["lon"],
                                                      today_str, tomorrow_str, city)
                except Exception:
                    continue
                if not forecast or tomorrow_str not in forecast:
                    continue
                mu_ens, sigma_ens = forecast[tomorrow_str]
                cal_sigma = CITY_SIGMA_C.get(slug, {}).get(now_utc.month, sigma_ens)
                fair_yes = _outcome_prob(mu_ens, lo_c, hi_c, cal_sigma)
            # We buy NO when YES is overpriced
            if fair_yes > poly_yes - NOSIDE_EDGE_MIN:
                continue   # YES is not overpriced enough

            no_ask  = 1.0 - poly_yes + 0.01           # 1¢ spread cross
            no_fair = 1.0 - fair_yes
            edge_no_gross = no_fair - no_ask
            rebate_rate   = MAKER_REBATE_FRAC * taker_fee_rate(no_ask)
            edge_no_net   = edge_no_gross + rebate_rate
            if edge_no_net < NOSIDE_EDGE_MIN:
                continue

            logger.info(
                "[NOSIDE] CANDIDATE %s bucket=[%.1f,%.1f) yes=%.3f fair_yes=%.3f "
                "NO_ask=%.3f NO_fair=%.3f edge_NO=%.3f",
                city, lo_c if lo_c is not None else -99, hi_c if hi_c is not None else 99,
                poly_yes, fair_yes, no_ask, no_fair, edge_no_net,
            )

            if await self._execute_maker_entry(
                wa, city, mkt, no_token, no_ask, no_fair, lo_c, hi_c, edge_no_net,
            ):
                entries_made += 1
                if entries_made + len(self._fired) >= NOSIDE_MAX_CONCURRENT:
                    return

        logger.debug("[NOSIDE] scan done — %d cities scanned, %d new entries",
                     len(scanned_cities), entries_made)

    async def _execute_maker_entry(self, wa, city: str, mkt: dict, no_token: str,
                                     no_ask: float, no_fair: float,
                                     lo_c: Optional[float], hi_c: Optional[float],
                                     edge_net: float) -> bool:
        """GTC post-only maker entry on the NO token at (no_ask − 1¢)."""
        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus

        bankroll = wa._get_bankroll()
        kelly_f = edge_net / max(0.01, 1.0 - no_ask)
        raw_stake = bankroll * NOSIDE_PER_POSITION * kelly_f
        stake = max(NOSIDE_MIN_STAKE,
                    min(NOSIDE_MAX_STAKE,
                        bankroll * NOSIDE_BANKROLL_FRAC,
                        raw_stake))

        maker_price = round(max(0.01, no_ask - 0.01), 4)
        logger.info(
            "[NOSIDE] ENTRY %s NO@%.3f stake=$%.1f bucket=[%s,%s)",
            city, maker_price, stake,
            f"{lo_c:.1f}" if lo_c is not None else "-inf",
            f"{hi_c:.1f}" if hi_c is not None else "+inf",
        )
        try:
            fill = await self.bot.orders.limit_buy(
                token_id=no_token,
                intended_price=maker_price,
                stake_usd=stake,
                direction=_Dir.BUY_NO,
                neg_risk=mkt.get("negRisk", True),
                fast_fail=False,
            )
            if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
                logger.info("[NOSIDE] no immediate fill %s — order rests on book", city)
                self._fired.add(no_token)
                wa._fired_tokens.add(no_token)
                return True

            self.bot.risk.open_position(
                token_id=no_token,
                asset="WEATHER",
                direction=_Dir.BUY_NO,
                stake=fill.total_size * fill.avg_fill_price,
                entry_price=fill.avg_fill_price,
                tpsl=_TPSL(take_profit=0.0, stop_loss=0.0,
                            tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
                condition_id=mkt.get("conditionId", ""),
                window_end_ts=0.0,
                is_bond=True,
                bond_outcome_direction="down",   # NO = "outcome NOT in bucket"
                bond_entry_class="WEATHER_NOSIDE",
            )
            meta = self.bot._open_meta.setdefault(no_token, {})
            meta["signal_source"] = f"WEATHER/{city}/STRAT_7_NOSIDE"
            meta["city"] = city
            self._fired.add(no_token)
            wa._fired_tokens.add(no_token)
            logger.info("[NOSIDE] FILLED %s NO@%.4f size=%.0f tag=NOSIDE",
                        city, fill.avg_fill_price, fill.total_size)
            return True
        except Exception:
            logger.exception("[NOSIDE] order error %s", city)
            return False
