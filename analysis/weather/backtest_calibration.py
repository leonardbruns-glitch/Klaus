"""Calibration backtest: do our model's bucket probabilities match realized
resolution frequency, stratified by entry-price ask band?

Two questions:
  1. CALIBRATION: per ask band, is mean(model_p) ≈ realized win rate?
     If yes -> model is honest in that band. If no -> model is over/under-confident.
  2. STRATEGY EV: per ask band, what is realized EV/bet (raw and 2% taker-fee)?

Methodology:
  - Fetch all resolved markets for `--city` in the last `--days` days.
  - For each market: simulate a forecast = actual + N(0, σ=1.2°C), `--mc-draws` times.
  - For each (market, draw, bucket): compute model_p under that forecast.
  - Apply edge filter (model_p - entry_price >= --min-edge) to gate "would we bet?".
  - Record (entry_price, model_p, won, pnl_raw, pnl_fee) per selected bucket.
  - Aggregate by entry-price band.

Usage:
    python3 -m analysis.weather.backtest_calibration --city london --days 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass

from analysis.weather.backtest import (
    attach_entry_prices,
    attach_resolved_highs,
    discover_resolved,
    _bucket_prob_normal,
)
from analysis.weather.stations import STATIONS


ASK_BANDS = [
    (0.00, 0.02),
    (0.02, 0.05),
    (0.05, 0.10),
    (0.10, 0.20),
    (0.20, 0.40),
    (0.40, 1.00),
]
SIGMA_ERR_C_DEFAULT = 1.2
MC_DRAWS_DEFAULT = 200
MIN_EDGE_DEFAULT = 0.03
FEE_RATE_DEFAULT = 0.02
STAKE = 1.0
RNG_SEED = 1729

# Scalp parameters
SCALP_TARGET_ABS = 0.03       # min absolute profit per share to scalp ($)
SCALP_TARGET_EDGE_FRAC = 0.5  # capture this fraction of (model_p - entry) edge
SCALP_DISCOUNT = 0.90         # ceiling: TP <= model_p * this (executability buffer)


def _scalp_tp(entry: float, model_p: float) -> float:
    """Take-profit price: capture min(SCALP_TARGET_ABS, frac of edge), capped
    below model_p × SCALP_DISCOUNT so we don't ask for more than fair."""
    target = entry + max(SCALP_TARGET_ABS, SCALP_TARGET_EDGE_FRAC * (model_p - entry))
    ceiling = model_p * SCALP_DISCOUNT
    return min(target, ceiling)


def _walk_scalp(history: list[dict], entry_ts: int, tp: float):
    """Find first history point after entry_ts with p >= tp.
    Returns (fill_ts, fill_price) or None.

    Caveat: history is last-TRADE prices. A trade at >= tp doesn't guarantee
    our limit sell of additional size would also fill, but it's the cleanest
    proxy we have without an L2 book replay."""
    for pt in history:
        ts = int(pt["t"])
        if ts <= entry_ts:
            continue
        p = float(pt["p"])
        if p >= tp:
            return (ts, p)
    return None


def _band_of(price: float) -> tuple[float, float] | None:
    for lo, hi in ASK_BANDS:
        if lo <= price < hi:
            return (lo, hi)
    return None


@dataclass
class BandStats:
    bets: int = 0
    wins: int = 0
    distinct_market_buckets: set = None
    sum_entry: float = 0.0
    sum_model_p: float = 0.0
    sum_pnl_raw: float = 0.0
    sum_pnl_fee: float = 0.0
    # Scalp counterfactuals
    scalp_fills: int = 0          # times TP got hit before resolution
    scalp_fills_on_winner: int = 0
    scalp_fills_on_loser: int = 0
    sum_pnl_scalp_raw: float = 0.0
    sum_pnl_scalp_fee: float = 0.0
    sum_hold_seconds: float = 0.0       # capital-time under hold-to-resolution
    sum_scalp_seconds: float = 0.0      # capital-time under scalp-or-hold

    def __post_init__(self):
        if self.distinct_market_buckets is None:
            self.distinct_market_buckets = set()


def evaluate_calibration(city: str, days: int, sigma_err_c: float,
                          mc_draws: int, min_edge: float, fee_rate: float,
                          seed: int = RNG_SEED) -> dict:
    print(f"Discovering resolved markets for {city} ({days}d back)...", file=sys.stderr)
    markets = discover_resolved(city, days)
    print(f"  found {len(markets)} markets", file=sys.stderr)

    print("Attaching CLOB entry prices...", file=sys.stderr)
    attach_entry_prices(markets)

    print("Scraping WU resolved highs (Playwright)...", file=sys.stderr)
    asyncio.run(attach_resolved_highs(markets))

    n_resolved = sum(1 for m in markets if m.resolved_high_market_unit is not None)
    print(f"  resolved: {n_resolved}/{len(markets)}", file=sys.stderr)
    if n_resolved == 0:
        return {"error": "no resolved markets"}

    rng = random.Random(seed)
    bands: dict[tuple[float, float], BandStats] = {b: BandStats() for b in ASK_BANDS}
    # Also a "would have bet, any band" tally for headline numbers
    total_bets = 0
    total_pnl_raw = 0.0
    total_pnl_fee = 0.0

    # Also: bucket-level (without edge filter) calibration — does the raw model match?
    # Each (market, bucket) contributes ONCE here, with its mean model_p averaged across draws.
    raw_per_bucket: list[dict] = []

    for m in markets:
        if m.resolved_high_market_unit is None:
            continue
        sigma_unit = sigma_err_c * (9.0 / 5.0 if m.unit == "F" else 1.0)
        actual = m.resolved_high_market_unit
        # Accumulators for raw (no edge filter) calibration: per bucket across draws.
        raw_acc: dict[str, dict] = {}
        for _ in range(mc_draws):
            err = rng.gauss(0.0, sigma_unit)
            mean_fc = actual + err
            fc_sigma = max(sigma_unit, 0.5)
            for b in m.buckets:
                if b.entry_price is None or b.entry_price <= 0.0 or b.entry_price >= 1.0:
                    continue
                band = _band_of(b.entry_price)
                if band is None:
                    continue
                p_model = _bucket_prob_normal(b.lo_inclusive, b.hi_exclusive, mean_fc, fc_sigma)

                # Raw per-bucket (no edge filter)
                k = b.label
                if k not in raw_acc:
                    raw_acc[k] = {"entry_price": b.entry_price, "is_winner": b.is_winner,
                                  "band": band, "model_p_sum": 0.0, "draws": 0}
                raw_acc[k]["model_p_sum"] += p_model
                raw_acc[k]["draws"] += 1

                # Edge-filtered tally
                edge = p_model - b.entry_price
                if edge < min_edge:
                    continue
                won = b.is_winner
                pnl_raw = (1.0 - b.entry_price) * STAKE if won else -b.entry_price * STAKE
                fee = fee_rate * STAKE
                pnl_fee = pnl_raw - fee
                bs = bands[band]
                bs.bets += 1
                bs.wins += int(won)
                bs.distinct_market_buckets.add((m.slug, b.label))
                bs.sum_entry += b.entry_price
                bs.sum_model_p += p_model
                bs.sum_pnl_raw += pnl_raw
                bs.sum_pnl_fee += pnl_fee
                total_bets += 1
                total_pnl_raw += pnl_raw
                total_pnl_fee += pnl_fee

                # --- SCALP-OR-HOLD counterfactual ---
                tp = _scalp_tp(b.entry_price, p_model)
                fill = _walk_scalp(b.history, b.entry_ts, tp)
                # Hold-to-resolution time = last history point - entry
                if b.history:
                    resolve_ts = int(b.history[-1]["t"])
                else:
                    resolve_ts = b.entry_ts
                hold_seconds = max(0, resolve_ts - b.entry_ts)
                if fill is not None:
                    scalp_ts, scalp_p = fill
                    scalp_pnl_raw = (scalp_p - b.entry_price) * STAKE
                    scalp_seconds = max(0, scalp_ts - b.entry_ts)
                    bs.scalp_fills += 1
                    if won:
                        bs.scalp_fills_on_winner += 1
                    else:
                        bs.scalp_fills_on_loser += 1
                else:
                    # No fill -> degenerate to hold-to-resolution
                    scalp_pnl_raw = pnl_raw
                    scalp_seconds = hold_seconds
                scalp_pnl_fee = scalp_pnl_raw - fee
                bs.sum_pnl_scalp_raw += scalp_pnl_raw
                bs.sum_pnl_scalp_fee += scalp_pnl_fee
                bs.sum_hold_seconds += hold_seconds
                bs.sum_scalp_seconds += scalp_seconds

        for k, v in raw_acc.items():
            raw_per_bucket.append({
                "market": m.slug,
                "bucket": k,
                "entry_price": v["entry_price"],
                "is_winner": v["is_winner"],
                "band": v["band"],
                "mean_model_p": v["model_p_sum"] / v["draws"] if v["draws"] else 0.0,
            })

    # Build calibration table (raw, no edge filter)
    raw_band: dict[tuple[float, float], dict] = defaultdict(lambda: {"n": 0, "wins": 0, "sum_mp": 0.0, "sum_entry": 0.0})
    for row in raw_per_bucket:
        b = row["band"]
        raw_band[b]["n"] += 1
        raw_band[b]["wins"] += int(row["is_winner"])
        raw_band[b]["sum_mp"] += row["mean_model_p"]
        raw_band[b]["sum_entry"] += row["entry_price"]

    print("\n=== RAW CALIBRATION (every bucket, no edge filter) ===")
    print("Each row = distinct (market, bucket) pair. mean_p_model averaged across MC draws.")
    print(f"{'band':<14} {'n_buckets':<11} {'mean_entry':<12} {'mean_p_model':<14} "
          f"{'realized_WR':<14} {'calib_delta':<14} {'mkt_implied_WR':<15}")
    for band in ASK_BANDS:
        d = raw_band[band]
        if d["n"] == 0:
            print(f"[{band[0]:.2f},{band[1]:.2f})   {0:<11} -            -              -              -              -")
            continue
        n = d["n"]
        mean_entry = d["sum_entry"] / n
        mean_mp = d["sum_mp"] / n
        wr = d["wins"] / n
        calib = wr - mean_mp
        mkt_wr_diff = wr - mean_entry  # if WR > mean_entry, buckets in this band are *underpriced*
        print(f"[{band[0]:.2f},{band[1]:.2f})   {n:<11} {mean_entry:<12.3f} {mean_mp:<14.3f} "
              f"{wr:<14.3f} {calib:<+14.3f} {mkt_wr_diff:<+15.3f}")

    print("\n=== STRATEGY (edge filter >= {:.2f}) ===".format(min_edge))
    print(f"Each row = one MC draw × bucket that passed the edge filter "
          f"(so divide bets/{mc_draws} for per-realization scale).")
    print(f"{'band':<14} {'bets':<8} {'bets/draw':<11} {'unique':<8} "
          f"{'mean_entry':<12} {'mean_p_model':<14} {'realized_WR':<14} "
          f"{'calib_delta':<14} {'EV/bet_raw':<12} {'EV/bet_fee':<12}")
    for band in ASK_BANDS:
        bs = bands[band]
        if bs.bets == 0:
            print(f"[{band[0]:.2f},{band[1]:.2f})   {0:<8} {0:<11} {0:<8} -            -              -              -              -            -")
            continue
        ev_raw = bs.sum_pnl_raw / bs.bets
        ev_fee = bs.sum_pnl_fee / bs.bets
        mean_entry = bs.sum_entry / bs.bets
        mean_mp = bs.sum_model_p / bs.bets
        wr = bs.wins / bs.bets
        calib = wr - mean_mp
        print(f"[{band[0]:.2f},{band[1]:.2f})   {bs.bets:<8} {bs.bets/mc_draws:<11.2f} "
              f"{len(bs.distinct_market_buckets):<8} {mean_entry:<12.3f} {mean_mp:<14.3f} "
              f"{wr:<14.3f} {calib:<+14.3f} {ev_raw:<+12.4f} {ev_fee:<+12.4f}")

    # Scalp-or-hold comparison
    print(f"\n=== SCALP-OR-HOLD vs HOLD-TO-RESOLUTION ===")
    print(f"TP rule: entry + max({SCALP_TARGET_ABS}, {SCALP_TARGET_EDGE_FRAC}×edge), "
          f"capped at fair × {SCALP_DISCOUNT}")
    print(f"{'band':<14} {'bets':<8} {'fill_rate':<11} {'fill_on_W':<10} "
          f"{'fill_on_L':<10} {'EV_hold_raw':<13} {'EV_scalp_raw':<14} "
          f"{'avg_hold_h':<12} {'avg_scalp_h':<13} {'$/$-day_hold':<13} {'$/$-day_scalp':<14}")
    for band in ASK_BANDS:
        bs = bands[band]
        if bs.bets == 0:
            continue
        fill_rate = bs.scalp_fills / bs.bets
        ev_hold = bs.sum_pnl_raw / bs.bets
        ev_scalp = bs.sum_pnl_scalp_raw / bs.bets
        avg_hold_h = (bs.sum_hold_seconds / bs.bets) / 3600
        avg_scalp_h = (bs.sum_scalp_seconds / bs.bets) / 3600
        # $/$-day = pnl / (entry × days). Avoid div0.
        hold_cap_days = (bs.sum_entry * (bs.sum_hold_seconds / max(1, bs.bets))) / 86400
        scalp_cap_days = (bs.sum_entry * (bs.sum_scalp_seconds / max(1, bs.bets))) / 86400
        # Use per-bet means: $-day per bet = entry × (seconds/bet)/86400
        mean_entry_b = bs.sum_entry / bs.bets
        hold_dollar_days = mean_entry_b * avg_hold_h / 24
        scalp_dollar_days = mean_entry_b * avg_scalp_h / 24
        roi_hold = ev_hold / hold_dollar_days if hold_dollar_days > 0 else float('nan')
        roi_scalp = ev_scalp / scalp_dollar_days if scalp_dollar_days > 0 else float('nan')
        wr_on_winners = bs.scalp_fills_on_winner / max(1, bs.wins)
        wr_on_losers = bs.scalp_fills_on_loser / max(1, bs.bets - bs.wins)
        print(f"[{band[0]:.2f},{band[1]:.2f})   {bs.bets:<8} {fill_rate:<11.3f} "
              f"{wr_on_winners:<10.3f} {wr_on_losers:<10.3f} {ev_hold:<+13.4f} "
              f"{ev_scalp:<+14.4f} {avg_hold_h:<12.1f} {avg_scalp_h:<13.1f} "
              f"{roi_hold:<+13.3f} {roi_scalp:<+14.3f}")

    # Headline
    print(f"\nTotal selected bets (all bands): {total_bets} ({total_bets/mc_draws:.1f}/draw)")
    if total_bets:
        print(f"  Total PnL raw  per $1: ${total_pnl_raw/mc_draws:.2f}  EV/bet=${total_pnl_raw/total_bets:+.4f}")
        print(f"  Total PnL fee  per $1: ${total_pnl_fee/mc_draws:.2f}  EV/bet=${total_pnl_fee/total_bets:+.4f}")

    # Underdog vs Favourite split
    print("\n=== UNDERDOG vs FAVOURITE ===")
    underdog_bets, underdog_pnl_raw, underdog_pnl_fee, underdog_wins = 0, 0.0, 0.0, 0
    fav_bets, fav_pnl_raw, fav_pnl_fee, fav_wins = 0, 0.0, 0.0, 0
    UNDERDOG_MAX = 0.20
    for band, bs in bands.items():
        if band[1] <= UNDERDOG_MAX:
            underdog_bets += bs.bets
            underdog_pnl_raw += bs.sum_pnl_raw
            underdog_pnl_fee += bs.sum_pnl_fee
            underdog_wins += bs.wins
        else:
            fav_bets += bs.bets
            fav_pnl_raw += bs.sum_pnl_raw
            fav_pnl_fee += bs.sum_pnl_fee
            fav_wins += bs.wins
    if underdog_bets:
        print(f"  UNDERDOG (entry<{UNDERDOG_MAX:.2f}):  n={underdog_bets} ({underdog_bets/mc_draws:.1f}/draw)  "
              f"WR={underdog_wins/underdog_bets:.3f}  "
              f"EV/bet_raw=${underdog_pnl_raw/underdog_bets:+.4f}  "
              f"EV/bet_fee=${underdog_pnl_fee/underdog_bets:+.4f}  "
              f"PnL/draw=${underdog_pnl_raw/mc_draws:+.2f}")
    else:
        print(f"  UNDERDOG (entry<{UNDERDOG_MAX:.2f}):  n=0")
    if fav_bets:
        print(f"  FAVOURITE (entry>={UNDERDOG_MAX:.2f}): n={fav_bets} ({fav_bets/mc_draws:.1f}/draw)  "
              f"WR={fav_wins/fav_bets:.3f}  "
              f"EV/bet_raw=${fav_pnl_raw/fav_bets:+.4f}  "
              f"EV/bet_fee=${fav_pnl_fee/fav_bets:+.4f}  "
              f"PnL/draw=${fav_pnl_raw/mc_draws:+.2f}")
    else:
        print(f"  FAVOURITE (entry>={UNDERDOG_MAX:.2f}): n=0")

    return {
        "city": city,
        "days": days,
        "sigma_err_c": sigma_err_c,
        "mc_draws": mc_draws,
        "min_edge": min_edge,
        "fee_rate": fee_rate,
        "n_markets_resolved": n_resolved,
        "raw_per_bucket": raw_per_bucket,
        "underdog": {"bets": underdog_bets, "wins": underdog_wins,
                     "pnl_raw_per_draw": underdog_pnl_raw / mc_draws,
                     "pnl_fee_per_draw": underdog_pnl_fee / mc_draws},
        "favourite": {"bets": fav_bets, "wins": fav_wins,
                      "pnl_raw_per_draw": fav_pnl_raw / mc_draws,
                      "pnl_fee_per_draw": fav_pnl_fee / mc_draws},
    }


def _cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--city", action="append",
                    help="city slug; repeat for multiple (default: london only). "
                         "Use --all for all 7 validated cities.")
    ap.add_argument("--all", action="store_true",
                    help="run on all 7 validated cities")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--sigma-err-c", type=float, default=SIGMA_ERR_C_DEFAULT,
                    help="forecast error σ in °C (default 1.2, matches live ensemble)")
    ap.add_argument("--mc-draws", type=int, default=MC_DRAWS_DEFAULT)
    ap.add_argument("--min-edge", type=float, default=MIN_EDGE_DEFAULT,
                    help="minimum (model_p - entry_price) to bet")
    ap.add_argument("--fee-rate", type=float, default=FEE_RATE_DEFAULT,
                    help="taker fee rate (default 0.02 = 2%% of stake)")
    ap.add_argument("--out", help="JSON output file")
    args = ap.parse_args()

    if args.all:
        cities = list(STATIONS.keys())
    elif args.city:
        cities = args.city
    else:
        cities = ["london"]

    for c in cities:
        if c not in STATIONS:
            print(f"ERROR: unknown city {c}. Known: {sorted(STATIONS)}", file=sys.stderr)
            return 2

    all_results = {}
    for c in cities:
        print(f"\n{'='*70}\n  CITY: {c}\n{'='*70}", file=sys.stderr)
        result = evaluate_calibration(c, args.days, args.sigma_err_c,
                                       args.mc_draws, args.min_edge, args.fee_rate)
        all_results[c] = result

    # Cross-city aggregation if >1 city
    if len(cities) > 1:
        print(f"\n{'='*70}\n  AGGREGATE ACROSS {len(cities)} CITIES\n{'='*70}")
        # Just report headline per-city table for now
        print(f"\n{'city':<14} {'underdog_n':<11} {'underdog_EV_fee':<16} "
              f"{'fav_n':<8} {'fav_EV_fee':<11} {'total_PnL/draw_fee':<18}")
        for c, r in all_results.items():
            u = r.get("underdog", {})
            f = r.get("favourite", {})
            u_ev = (u["pnl_fee_per_draw"] / max(1, u["bets"]/args.mc_draws)) if u.get("bets") else 0.0
            f_ev = (f["pnl_fee_per_draw"] / max(1, f["bets"]/args.mc_draws)) if f.get("bets") else 0.0
            total_fee = (u.get("pnl_fee_per_draw", 0.0) + f.get("pnl_fee_per_draw", 0.0))
            print(f"{c:<14} {u.get('bets', 0):<11} ${u_ev:<+15.4f} "
                  f"{f.get('bets', 0):<8} ${f_ev:<+10.4f} ${total_fee:<+17.2f}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nFull output -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
