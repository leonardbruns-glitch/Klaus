"""Backtest harness for the weather strategy on validated US/UK/JP markets.

Two modes:

  1. PERFECT FORECAST:  assume P_model = δ on the actually-resolved bucket.
     Tells us the upper-bound EV per city — what we'd make if we always knew
     the answer. If this is small, no forecasting effort can save the strategy.

  2. NOISY FORECAST:    forecast ~ Normal(actual, σ_err) with σ_err swept over
     [0.5, 1.0, 1.5, 2.0, 3.0]°C. Monte Carlo across N draws per market.
     Tells us how forecast-skill maps to profitability — directly answers
     "what σ does our real forecaster need to beat?".

Inputs:
  - Resolved Polymarket markets from gamma /public-search per city
  - Bucket close asks from each market's gamma event payload
  - Resolved WU "High Temp" via the local wu_high_scraper module

Outputs:
  - Per-city, per-σ_err: n trades, WR, EV/trade, total PnL (per $1 stake)
  - Per-bucket-tier breakdown (which ask ranges are juicy)

Usage:
    python3 -m analysis.weather.backtest --days 30 --stake 1.0
    python3 -m analysis.weather.backtest --days 30 --city nyc --out /tmp/bt.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import statistics
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from analysis.weather.stations import STATIONS, Station
from analysis.weather.wu_high_scraper import scrape_many

GAMMA_EVENT  = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_HISTORY = "https://clob.polymarket.com/prices-history"
USER_AGENT   = "Klaus-WeatherBot/1.0 backtest"
MIN_EDGE     = 0.05   # only consider bets with model_p > ask + this
SIGMA_SWEEP_C = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]   # σ_err values to sweep
MC_DRAWS_PER_MARKET = 200
RNG_SEED = 1729

# Markets trade AFTER the weather day ends, between ~22:30 UTC same-day and
# resolution ~07:00 UTC next day. Price converges to 1.0 fast (~4h for NYC).
# We sample entry price at this offset past the FIRST observed trade — small
# enough to capture pre-convergence price, large enough to be reachable by a
# poll-based scanner with realistic discovery latency.
ENTRY_OFFSET_MIN_AFTER_FIRST_TRADE = 5


# ---------- HTTP helpers ----------

def _http_get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- Polymarket discovery ----------

@dataclass
class BucketView:
    label: str            # e.g. "78-79°F", "26°C or higher", "18°C"
    lo_inclusive: float   # in market-unit (F or C)
    hi_exclusive: float
    is_winner: bool
    yes_token_id: Optional[str] = None  # CLOB token ID for the YES side
    entry_price: Optional[float] = None  # price at ENTRY_OFFSET_MIN past first-trade
    entry_ts: Optional[int] = None
    n_history_points: int = 0
    history: list = field(default_factory=list)  # full [{'t':int,'p':float}] for post-entry walks


@dataclass
class MarketView:
    city_slug: str
    icao: str
    valid_day: date
    unit: str             # "F" or "C"
    slug: str
    buckets: list[BucketView]
    resolved_high_market_unit: Optional[float] = None
    resolved_high_c: Optional[float] = None


def _parse_bucket(label: str, unit: str) -> tuple[float, float]:
    """Convert a bucket label to (lo_inclusive, hi_exclusive) in market unit.

    Examples (unit=F, 2°F wide):
      "95°F or below"   -> (-inf, 96)
      "78-79°F"         -> (78, 80)
      "82-83°F"         -> (82, 84)
      "108°F or higher" -> (108, +inf)

    Examples (unit=C, 1°C wide):
      "18°C"            -> (18, 19)
      "26°C or higher"  -> (26, +inf)
      "12°C or below"   -> (-inf, 13)
    """
    nums = [int(x) for x in re.findall(r"\d+", label)]
    if "or below" in label.lower():
        return (float("-inf"), nums[0] + 1.0)
    if "or higher" in label.lower() or "or above" in label.lower():
        return (float(nums[0]), float("inf"))
    if len(nums) == 2:
        return (float(nums[0]), float(nums[1]) + 1.0)
    if len(nums) == 1:
        return (float(nums[0]), float(nums[0]) + 1.0)
    raise ValueError(f"can't parse bucket label: {label!r}")


_MONTHS = ["january","february","march","april","may","june",
           "july","august","september","october","november","december"]


def discover_resolved(city_slug: str, days_back: int) -> list[MarketView]:
    """Iterate over the last N days and probe each expected slug directly.

    /public-search and /events both bias toward high-volume markets and miss
    the long tail of small weather markets; slug construction is deterministic.
    """
    today = datetime.now(timezone.utc).date()
    out: list[MarketView] = []
    station = STATIONS[city_slug]
    for delta in range(1, days_back + 1):
        day = today - timedelta(days=delta)
        slug = (f"highest-temperature-in-{city_slug}-on-"
                f"{_MONTHS[day.month - 1]}-{day.day}-{day.year}")
        try:
            full = _http_get_json(GAMMA_EVENT.format(slug=slug))
        except Exception:
            continue
        if not full.get("closed"):
            continue
        valid_day = day
        buckets: list[BucketView] = []
        for m in full.get("markets", []):
            label = m.get("groupItemTitle") or m.get("question", "")
            if not label:
                continue
            try:
                lo, hi = _parse_bucket(label, station.unit)
            except ValueError:
                continue
            try:
                prices = json.loads(m.get("outcomePrices", '["0","0"]'))
            except (json.JSONDecodeError, TypeError):
                prices = ["0", "0"]
            is_winner = prices and prices[0] == "1"
            # clobTokenIds[0] = YES side; we trade YES across bucket portfolio.
            try:
                token_ids = json.loads(m.get("clobTokenIds", "[]"))
                yes_token = token_ids[0] if token_ids else None
            except (json.JSONDecodeError, TypeError, IndexError):
                yes_token = None
            buckets.append(BucketView(
                label=label,
                lo_inclusive=lo,
                hi_exclusive=hi,
                is_winner=bool(is_winner),
                yes_token_id=yes_token,
            ))
        if not buckets:
            continue
        out.append(MarketView(
            city_slug=city_slug,
            icao=station.icao,
            valid_day=valid_day,
            unit=station.unit,
            slug=slug,
            buckets=buckets,
        ))
    return out


# ---------- CLOB entry-price attachment ----------

def _fetch_history(token_id: str) -> list[dict]:
    """Returns sorted list of {'t': unix_int, 'p': price_float}. Empty on failure."""
    try:
        r = _http_get_json(f"{CLOB_HISTORY}?market={token_id}&interval=max")
    except Exception:
        return []
    return r.get("history", [])


def attach_entry_prices(markets: list[MarketView],
                        offset_min: int = ENTRY_OFFSET_MIN_AFTER_FIRST_TRADE) -> None:
    """For each bucket, fetch CLOB price history and pick the trade closest to
    (first_trade_ts + offset_min). Mutates buckets in place."""
    for m in markets:
        for b in m.buckets:
            if not b.yes_token_id:
                continue
            hist = _fetch_history(b.yes_token_id)
            b.n_history_points = len(hist)
            if not hist:
                continue
            first_ts = hist[0]["t"]
            target_ts = first_ts + offset_min * 60
            # Walk to find the closest point at or after target_ts; fallback to last
            chosen = hist[-1]
            for pt in hist:
                if pt["t"] >= target_ts:
                    chosen = pt
                    break
            b.entry_price = float(chosen["p"])
            b.entry_ts = int(chosen["t"])
            b.history = hist


# ---------- Resolved-high attachment ----------

async def attach_resolved_highs(markets: list[MarketView]) -> None:
    """Use the WU scraper to populate resolved_high_* on each market.
    Mutates in place. Cities/dates are deduped before scraping."""
    if not markets:
        return
    # Group by (city, date) to dedupe scrapes
    seen: dict[tuple[str, date], list[MarketView]] = {}
    for m in markets:
        seen.setdefault((m.city_slug, m.valid_day), []).append(m)

    station_list = [STATIONS[c] for (c, _d) in sorted({(c, d) for (c, d) in seen}, key=lambda x: (x[0], x[1]))]
    # We need per-(station, date) targeted scrapes; reuse scrape_many but build
    # one pass per unique date set per station to keep the browser alive.
    # Simplest: iterate cities, for each city scrape its specific date list.
    from analysis.weather.wu_high_scraper import scrape_one
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1800},
            locale="en-US",
        )
        page = await ctx.new_page()
        for (city_slug, day), mlist in sorted(seen.items()):
            station = STATIONS[city_slug]
            res = await scrape_one(page, station, day)
            high_f = res.get("high_f")
            high_c = res.get("high_c")
            if high_f is None:
                continue
            for m in mlist:
                if m.unit == "F":
                    m.resolved_high_market_unit = high_f
                else:
                    # Market is in °C; resolution unit is WU's converted °C
                    m.resolved_high_market_unit = round(high_c)
                m.resolved_high_c = high_c
        await browser.close()


# ---------- EV / portfolio math ----------

def _gauss_cdf(x: float, mean: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf((x - mean) / (sigma * math.sqrt(2.0))))


def _bucket_prob_normal(lo: float, hi: float, mean: float, sigma: float) -> float:
    p_lo = 0.0 if lo == float("-inf") else _gauss_cdf(lo, mean, sigma)
    p_hi = 1.0 if hi == float("inf") else _gauss_cdf(hi, mean, sigma)
    return max(0.0, p_hi - p_lo)


def evaluate_market(m: MarketView, forecast_mean_market_unit: float,
                    forecast_sigma_market_unit: float, stake: float = 1.0) -> dict:
    """Given a market view and a forecast (mean, sigma), simulate what bets
    we'd place and what PnL would result. Returns:
      {
        'n_bets': int,
        'pnl': float,
        'bets': [
          {'bucket': str, 'ask': float, 'p_model': float, 'edge': float,
           'won': bool, 'pnl': float},
          ...
        ],
        'skipped_reason': str | None,
      }
    """
    if m.resolved_high_market_unit is None:
        return {"n_bets": 0, "pnl": 0.0, "bets": [], "skipped_reason": "no_resolution"}

    bets = []
    total_pnl = 0.0
    for b in m.buckets:
        if b.entry_price is None or b.entry_price <= 0.0 or b.entry_price >= 1.0:
            continue
        p_model = _bucket_prob_normal(b.lo_inclusive, b.hi_exclusive,
                                      forecast_mean_market_unit, forecast_sigma_market_unit)
        edge = p_model - b.entry_price
        if edge < MIN_EDGE:
            continue
        # Bet: pay entry_price, receive 1 if winner else 0
        won = b.is_winner
        pnl = (1.0 - b.entry_price) * stake if won else -b.entry_price * stake
        total_pnl += pnl
        bets.append({
            "bucket": b.label,
            "entry_price": b.entry_price,
            "p_model": round(p_model, 4),
            "edge": round(edge, 4),
            "won": won,
            "pnl": round(pnl, 4),
        })
    return {"n_bets": len(bets), "pnl": round(total_pnl, 4), "bets": bets, "skipped_reason": None}


# ---------- Replay drivers ----------

def replay_perfect(markets: list[MarketView], stake: float = 1.0) -> dict:
    """Perfect-forecast: forecast = actual, σ → 0+. Equivalent to: only bet
    the winning bucket if its ask provides edge ≥ MIN_EDGE."""
    rows = []
    total_pnl = 0.0
    total_bets = 0
    wins = 0
    for m in markets:
        if m.resolved_high_market_unit is None:
            continue
        # Find the winning bucket and its ask
        winners = [b for b in m.buckets if b.is_winner]
        if not winners:
            continue
        wb = winners[0]
        if wb.entry_price is None or wb.entry_price <= 0.0 or wb.entry_price >= 1.0:
            continue
        # Implied edge under perfect forecast = 1 - entry_price
        edge = 1.0 - wb.entry_price
        if edge < MIN_EDGE:
            continue
        pnl = (1.0 - wb.entry_price) * stake   # always wins under perfect forecast
        total_pnl += pnl
        total_bets += 1
        wins += 1
        rows.append({
            "city": m.city_slug, "date": m.valid_day.isoformat(),
            "bucket": wb.label, "entry_price": wb.entry_price,
            "edge": round(edge, 4), "pnl": round(pnl, 4),
        })
    return {
        "mode": "perfect",
        "n_markets_with_resolution": sum(1 for m in markets if m.resolved_high_market_unit is not None),
        "n_bets": total_bets,
        "wins": wins,
        "win_rate": (wins / total_bets) if total_bets else 0.0,
        "total_pnl": round(total_pnl, 4),
        "ev_per_bet": round(total_pnl / total_bets, 4) if total_bets else None,
        "bets": rows,
    }


def replay_noisy(markets: list[MarketView], sigma_err_c: float,
                 stake: float = 1.0, mc_draws: int = MC_DRAWS_PER_MARKET,
                 seed: int = RNG_SEED) -> dict:
    """Noisy-forecast: per market, draw `mc_draws` forecast errors from
    N(0, sigma_err_c) and evaluate. Averages PnL over draws."""
    import random
    rng = random.Random(seed)

    n_markets = 0
    sum_pnl = 0.0
    sum_n_bets = 0.0
    sum_wins = 0.0

    for m in markets:
        if m.resolved_high_market_unit is None:
            continue
        n_markets += 1
        # σ in market unit: if market is °F, multiply σ_err_c by 9/5
        sigma_unit = sigma_err_c * (9.0/5.0 if m.unit == "F" else 1.0)
        actual = m.resolved_high_market_unit
        m_pnl = 0.0
        m_bets = 0
        m_wins = 0
        for _ in range(mc_draws):
            err = rng.gauss(0.0, sigma_unit)
            mean_fc = actual + err
            # Use a forecast sigma slightly larger than σ_err to model real-world spread.
            # MVP: forecast_sigma = max(sigma_unit, 0.5) — leaves room for nonzero p_model.
            fc_sigma = max(sigma_unit, 0.5)
            r = evaluate_market(m, mean_fc, fc_sigma, stake=stake)
            m_pnl += r["pnl"]
            m_bets += r["n_bets"]
            m_wins += sum(1 for b in r["bets"] if b["won"])
        sum_pnl += m_pnl / mc_draws
        sum_n_bets += m_bets / mc_draws
        sum_wins += m_wins / mc_draws

    return {
        "mode": "noisy",
        "sigma_err_c": sigma_err_c,
        "mc_draws_per_market": mc_draws,
        "n_markets_with_resolution": n_markets,
        "avg_bets_per_market": round(sum_n_bets / n_markets, 3) if n_markets else None,
        "avg_pnl_per_market": round(sum_pnl / n_markets, 4) if n_markets else None,
        "avg_win_rate": round(sum_wins / sum_n_bets, 4) if sum_n_bets > 0 else None,
        "total_expected_pnl": round(sum_pnl, 4),
    }


# ---------- Fee-aware replay (strategy-level) ----------

def replay_with_fees(
    markets: list[MarketView],
    sigma_err_c: float,
    strategy_tag: str = "STRAT_1_OVERNIGHT",
    stake: float = 20.0,
    mc_draws: int = MC_DRAWS_PER_MARKET,
    seed: int = RNG_SEED,
) -> dict:
    """Noisy-forecast replay with realistic Polymarket fees, maker rebates,
    and spread/slippage. Uses strategy execution profile to determine roles.

    PnL accounting:
      gross_pnl = (1 − eff_entry_price) if winner else (−eff_entry_price)
      net_pnl   = gross_pnl − entry_fee − exit_fee     (per share notional)
      win_rate, profit_factor, fee_drag computed across all simulated bets.
    """
    import random
    from strategy.fee_model import (
        profile_for, simulate_taker_fill, simulate_maker_fill,
        estimate_spread, DEFAULT_SPREAD, MAKER_REBATE_FRAC,
    )

    rng = random.Random(seed)
    entry_role, exit_role, profile_spread, fill_prob = profile_for(strategy_tag)

    sum_gross_pnl = 0.0
    sum_net_pnl   = 0.0
    sum_fees      = 0.0
    sum_rebates   = 0.0
    n_bets        = 0
    n_wins        = 0
    n_unfilled    = 0
    bets_log: list[dict] = []

    for m in markets:
        if m.resolved_high_market_unit is None:
            continue
        sigma_unit = sigma_err_c * (9.0 / 5.0 if m.unit == "F" else 1.0)
        actual     = m.resolved_high_market_unit

        for _ in range(mc_draws):
            err     = rng.gauss(0.0, sigma_unit)
            mean_fc = actual + err
            fc_sig  = max(sigma_unit, 0.5)

            # Determine the SINGLE best-edge bucket to bet (matches live behaviour)
            best = None
            best_edge = -1.0
            for b in m.buckets:
                if b.entry_price is None or b.entry_price <= 0.01 or b.entry_price >= 0.99:
                    continue
                p_model = _bucket_prob_normal(b.lo_inclusive, b.hi_exclusive, mean_fc, fc_sig)
                e = p_model - b.entry_price
                if e >= MIN_EDGE and e > best_edge:
                    best_edge = e
                    best = (b, p_model, e)

            if best is None:
                continue

            bucket, p_model, edge = best

            # Simulate entry fill
            if entry_role == "maker":
                fill = simulate_maker_fill(bucket.entry_price, stake, profile_spread, fill_prob)
                if fill is None:
                    n_unfilled += 1
                    continue
            else:
                fill = simulate_taker_fill(bucket.entry_price, stake, profile_spread)

            eff_entry = fill.avg_price
            entry_fee = fill.fee_usd
            n_bets   += 1

            # Outcome
            won = bucket.is_winner
            if won:
                n_wins += 1

            # Per-share notional: assume we hold to resolution (settlement = $1 if win, $0 if lose).
            # Position size in shares = stake / eff_entry; payout = shares × $1 if win.
            shares = stake / eff_entry if eff_entry > 0 else 0.0
            if won:
                # For "settle" exit role, no exit fee (resolution payout). For "taker", exit at $1.
                if exit_role == "settle":
                    gross = shares * 1.0 - stake
                    exit_fee = 0.0
                else:
                    # Exit fee at p≈0.99 = ~0.05% — negligible
                    exit_fill = simulate_taker_fill(0.99, shares * 1.0, profile_spread)
                    gross = shares * exit_fill.avg_price - stake
                    exit_fee = exit_fill.fee_usd
            else:
                # Loser: sells before resolution at salvage bid, or holds to $0.
                if exit_role == "settle":
                    gross = -stake
                    exit_fee = 0.0
                else:
                    salvage_price = max(0.01, eff_entry * 0.30)  # rough salvage at 30% of entry
                    exit_fill = simulate_taker_fill(salvage_price, shares * salvage_price, profile_spread)
                    gross = shares * exit_fill.avg_price - stake
                    exit_fee = exit_fill.fee_usd

            net = gross - entry_fee - exit_fee
            if entry_fee < 0: sum_rebates += abs(entry_fee)
            else: sum_fees += entry_fee
            if exit_fee > 0: sum_fees += exit_fee

            sum_gross_pnl += gross
            sum_net_pnl   += net

            if mc_draws == 1:  # only log individual bets in deterministic mode
                bets_log.append({
                    "city": m.city_slug, "date": m.valid_day.isoformat(),
                    "bucket": bucket.label, "entry_price": bucket.entry_price,
                    "eff_entry": round(eff_entry, 4),
                    "edge": round(edge, 4), "won": won,
                    "gross_pnl": round(gross, 3),
                    "entry_fee": round(entry_fee, 3),
                    "exit_fee":  round(exit_fee, 3),
                    "net_pnl":   round(net, 3),
                })

    avg_bets_per_draw = n_bets / mc_draws if mc_draws > 0 else 0
    wins_per_draw     = n_wins / mc_draws if mc_draws > 0 else 0
    win_rate = (n_wins / n_bets) if n_bets > 0 else None
    profit_factor = None
    if sum_net_pnl != 0:
        wins_pnl   = sum(b["net_pnl"] for b in bets_log if b["won"]) if bets_log else None
        losses_pnl = sum(-b["net_pnl"] for b in bets_log if not b["won"]) if bets_log else None
        if losses_pnl and losses_pnl > 0 and wins_pnl is not None:
            profit_factor = round(wins_pnl / losses_pnl, 3)

    return {
        "mode":                   "fees_aware",
        "strategy":               strategy_tag,
        "execution_profile":      {
            "entry_role": entry_role, "exit_role": exit_role,
            "default_spread": profile_spread, "fill_probability": fill_prob,
        },
        "sigma_err_c":            sigma_err_c,
        "stake_per_bet":          stake,
        "n_bets_total":           n_bets,
        "n_unfilled_maker":       n_unfilled,
        "fill_rate_maker":        round(n_bets / (n_bets + n_unfilled), 3) if entry_role == "maker" and (n_bets + n_unfilled) > 0 else None,
        "avg_bets_per_draw":      round(avg_bets_per_draw, 2),
        "win_rate":               round(win_rate, 4) if win_rate is not None else None,
        "profit_factor":          profit_factor,
        "gross_pnl_total":        round(sum_gross_pnl, 2),
        "net_pnl_total":          round(sum_net_pnl, 2),
        "net_pnl_per_bet":        round(sum_net_pnl / n_bets, 3) if n_bets > 0 else None,
        "fees_paid_total":        round(sum_fees, 2),
        "rebates_earned_total":   round(sum_rebates, 2),
        "fee_drag_pct_of_stake":  round(sum_fees / (n_bets * stake) * 100.0, 3) if n_bets > 0 else None,
        "rebate_offset_pct":      round(sum_rebates / (n_bets * stake) * 100.0, 3) if n_bets > 0 else None,
    }


def compare_strategies(markets: list[MarketView], sigma_err_c: float, stake: float = 20.0,
                        strategies: list[str] | None = None, mc_draws: int = 50,
                        seed: int = RNG_SEED) -> dict:
    """Run replay_with_fees across multiple strategy execution profiles.

    Useful for: "given the same forecast skill, which execution profile yields the
    best risk-adjusted return after fees?"
    """
    strategies = strategies or [
        "STRAT_1_OVERNIGHT", "STRAT_2_BRACKET", "STRAT_3_INTRADAY",
        "STRAT_4_TAIL", "STRAT_5_NWPLAG", "STRAT_6_CITYCTR", "STRAT_7_NOSIDE",
    ]
    out = {}
    for tag in strategies:
        out[tag] = replay_with_fees(markets, sigma_err_c=sigma_err_c, strategy_tag=tag,
                                    stake=stake, mc_draws=mc_draws, seed=seed)
    # Rank by net_pnl_per_bet
    ranked = sorted(out.items(), key=lambda kv: kv[1].get("net_pnl_per_bet") or -999, reverse=True)
    return {
        "sigma_err_c":  sigma_err_c,
        "stake":        stake,
        "mc_draws":     mc_draws,
        "n_markets":    sum(1 for m in markets if m.resolved_high_market_unit is not None),
        "results":      out,
        "ranked":       [{"strategy": k, "net_pnl_per_bet": v.get("net_pnl_per_bet")} for k, v in ranked],
    }


# ---------- CLI ----------

def _cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30, help="lookback window in days")
    ap.add_argument("--city", action="append", help="restrict to one or more city slugs (default: all 7)")
    ap.add_argument("--stake", type=float, default=1.0, help="$ per bet")
    ap.add_argument("--out", help="JSON output file (full per-market replay)")
    ap.add_argument("--compare-strategies", action="store_true",
                    help="Run fee-aware multi-strategy comparison at σ=0.7°C (realistic skill)")
    ap.add_argument("--strategy-sigma", type=float, default=0.7,
                    help="σ_err (°C) for the fee-aware strategy comparison")
    ap.add_argument("--strategy-stake", type=float, default=20.0,
                    help="$ per bet for fee-aware replay (must match real-world stake size)")
    args = ap.parse_args()

    cities = args.city or list(STATIONS.keys())
    print(f"Discovering resolved markets across {cities} (last {args.days}d)...", file=sys.stderr)
    markets: list[MarketView] = []
    for c in cities:
        ms = discover_resolved(c, args.days)
        print(f"  {c}: {len(ms)} resolved markets", file=sys.stderr)
        markets.extend(ms)
    print(f"Total markets: {len(markets)}", file=sys.stderr)

    print("Attaching CLOB entry prices (history at first_trade + offset)...", file=sys.stderr)
    attach_entry_prices(markets)

    print("Scraping WU resolved highs (Playwright)...", file=sys.stderr)
    asyncio.run(attach_resolved_highs(markets))

    n_resolved = sum(1 for m in markets if m.resolved_high_market_unit is not None)
    print(f"  resolved: {n_resolved}/{len(markets)}", file=sys.stderr)

    # 1. Perfect-forecast replay
    perfect = replay_perfect(markets, stake=args.stake)
    print("\n=== PERFECT-FORECAST REPLAY ===")
    print(f"  markets with resolution: {perfect['n_markets_with_resolution']}")
    print(f"  bets placed:             {perfect['n_bets']}")
    print(f"  win rate:                {perfect['win_rate']*100:.1f}%  (should be 100% by definition)")
    print(f"  total PnL @ ${args.stake}/bet: ${perfect['total_pnl']:.2f}")
    if perfect['ev_per_bet'] is not None:
        print(f"  EV per bet:              ${perfect['ev_per_bet']:.3f}")

    # 2. Noisy-forecast σ sweep
    print("\n=== NOISY-FORECAST SWEEP ===")
    print(f"{'σ_err (°C)':<12} {'avg bets/mkt':<14} {'avg PnL/mkt':<14} {'avg WR':<10} {'total exp PnL':<14}")
    sweep_results = []
    for s in SIGMA_SWEEP_C:
        r = replay_noisy(markets, sigma_err_c=s, stake=args.stake)
        sweep_results.append(r)
        print(f"{s:<12} {str(r['avg_bets_per_market']):<14} {str(r['avg_pnl_per_market']):<14} "
              f"{str(r['avg_win_rate']):<10} {str(r['total_expected_pnl']):<14}")

    # Per-city perfect-mode breakdown
    print("\n=== PER-CITY (perfect mode) ===")
    by_city: dict[str, list[dict]] = {}
    for b in perfect["bets"]:
        by_city.setdefault(b["city"], []).append(b)
    for city in sorted(by_city):
        rows = by_city[city]
        pnl = sum(r["pnl"] for r in rows)
        print(f"  {city:<14} n_bets={len(rows):<3} total_pnl=${pnl:.2f}  avg_entry={statistics.fmean([r['entry_price'] for r in rows]):.3f}")

    # 3. Fee-aware strategy comparison (optional)
    strategy_compare = None
    if args.compare_strategies:
        print("\n=== FEE-AWARE STRATEGY COMPARISON ===")
        print(f"   σ_err={args.strategy_sigma}°C  stake=${args.strategy_stake}")
        strategy_compare = compare_strategies(
            markets,
            sigma_err_c=args.strategy_sigma,
            stake=args.strategy_stake,
            mc_draws=50,
        )
        print(f"{'Strategy':<22} {'n_bets':<7} {'WR':<7} {'net/bet':<10} {'fee_drag%':<10} {'fill%':<7}")
        for tag, r in strategy_compare["results"].items():
            print(f"  {tag:<20} {r['n_bets_total']:<7} "
                  f"{(r['win_rate']*100 if r['win_rate'] else 0):.1f}%   "
                  f"${r.get('net_pnl_per_bet', 0) or 0:<8.3f} "
                  f"{r.get('fee_drag_pct_of_stake', 0) or 0:<8.2f}% "
                  f"{(r.get('fill_rate_maker') or 1.0)*100:.0f}%")
        print("\nRanked by net_pnl/bet (best execution profile):")
        for row in strategy_compare["ranked"]:
            print(f"  {row['strategy']:<22}  ${row['net_pnl_per_bet']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({
                "cities": cities,
                "days_back": args.days,
                "stake": args.stake,
                "n_markets": len(markets),
                "n_resolved": n_resolved,
                "perfect": perfect,
                "sweep": sweep_results,
                "strategy_compare": strategy_compare,
            }, f, indent=2)
        print(f"\nFull replay written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    _cli()
