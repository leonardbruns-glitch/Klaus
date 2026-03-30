"""
Klaus — Binance-to-Polymarket Lag Analysis

Run this after 2-3 days of data collection to answer:
  "Does Binance price movement precede Polymarket updown token repricing
   by 30+ seconds — and is the lag large enough to trade?"

Usage:
    python3 analytics/lag_analysis.py
    python3 analytics/lag_analysis.py --asset BTC
    python3 analytics/lag_analysis.py --min-move 0.3

What it does:
  For each observation where Binance moved ≥ threshold % in 1m/5m:
    - Look forward 30s, 60s, 120s in the log for the same token
    - Check if Polymarket price moved in the same direction as Binance
    - Compute win rate, average move size, and lag distribution

Verdict thresholds (what makes lag trading viable):
  - Win rate > 55% at 30s lookahead → lag exists and is consistent
  - Average Polymarket move > 0.03 (3pp) → large enough to cover ~1.8% fees
  - Both needed simultaneously → actual edge
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

LOG_PATH = Path("logs/lag_observations.jsonl")


def load_observations(path: Path) -> List[dict]:
    if not path.exists():
        print(f"ERROR: {path} not found. Run the bot for 2-3 days first.")
        sys.exit(1)
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def analyse(
    records: List[dict],
    asset_filter: Optional[str] = None,
    min_binance_move_pct: float = 0.2,   # only look at observations where Binance moved ≥ this %
    lookahead_seconds: List[int] = None,
) -> None:
    if lookahead_seconds is None:
        lookahead_seconds = [30, 60, 120]

    if asset_filter:
        records = [r for r in records if r["asset"].upper() == asset_filter.upper()]

    # Only updown markets; filter out records with missing Binance data
    records = [
        r for r in records
        if r.get("market_type") == "updown"
        and r.get("binance_spot") is not None
        and r.get("binance_1m_pct") is not None
        and r.get("polymarket_price") is not None
        and r.get("polymarket_price") > 0
    ]

    if not records:
        print("No valid updown observations found.")
        return

    print(f"\n{'='*60}")
    print(f"BINANCE → POLYMARKET LAG ANALYSIS")
    print(f"{'='*60}")
    print(f"Total observations: {len(records)}")
    print(f"Assets: {sorted(set(r['asset'] for r in records))}")
    print(f"Date range: {_ts_str(records[0]['ts'])} → {_ts_str(records[-1]['ts'])}")
    print(f"Min Binance 1m move filter: ±{min_binance_move_pct}%\n")

    # Index by token_id for fast forward-lookup
    by_token: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by_token[r["token_id"]].append(r)

    # Sort each token's observations by ts
    for tid in by_token:
        by_token[tid].sort(key=lambda x: x["ts"])

    # ── Core analysis ─────────────────────────────────────────────────────────
    for lookahead in lookahead_seconds:
        print(f"--- Lookahead: {lookahead}s ---")
        _analyse_lookahead(records, by_token, lookahead, min_binance_move_pct)
        print()

    # ── Lag distribution: when does Polymarket actually reprice? ─────────────
    print("--- Lag distribution (how long until Polymarket moves ≥ 0.02 in Binance direction) ---")
    _analyse_lag_distribution(records, by_token, min_binance_move_pct)
    print()

    # ── Correlation: Binance 1m pct vs Polymarket move ───────────────────────
    print("--- Binance 1m move vs Polymarket 30s move (correlation) ---")
    _analyse_correlation(records, by_token, 30)
    print()

    # ── Per-asset breakdown ───────────────────────────────────────────────────
    print("--- Per-asset win rate at 60s lookahead ---")
    for asset in sorted(set(r["asset"] for r in records)):
        asset_records = [r for r in records if r["asset"] == asset]
        print(f"  {asset}:", end=" ")
        _analyse_lookahead(asset_records, by_token, 60, min_binance_move_pct, compact=True)

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("VERDICT")
    print(f"{'='*60}")
    _print_verdict(records, by_token, min_binance_move_pct)


def _analyse_lookahead(
    records: List[dict],
    by_token: Dict[str, List[dict]],
    lookahead: int,
    min_move: float,
    compact: bool = False,
) -> None:
    wins = losses = skipped = 0
    move_sizes = []

    for r in records:
        binance_move = r.get("binance_1m_pct", 0) or 0
        if abs(binance_move) < min_move:
            continue

        # Find the observation for this token ~lookahead seconds later
        future = _find_future(by_token[r["token_id"]], r["ts"], lookahead)
        if future is None:
            skipped += 1
            continue

        current_price = r["polymarket_price"]
        future_price = future["polymarket_price"]
        token_move = future_price - current_price

        # Binance direction: positive = up = expect YES token to rise
        # For YES tokens: binance_move > 0 → expect token_move > 0
        # For NO tokens: binance_move > 0 → expect token_move < 0 (NO falls when YES rises)
        if r["side"] == "YES":
            expected_direction = 1 if binance_move > 0 else -1
        else:
            expected_direction = -1 if binance_move > 0 else 1

        actual_direction = 1 if token_move > 0.005 else (-1 if token_move < -0.005 else 0)

        if actual_direction == 0:
            skipped += 1
            continue
        elif actual_direction == expected_direction:
            wins += 1
            move_sizes.append(abs(token_move))
        else:
            losses += 1
            move_sizes.append(abs(token_move))

    total = wins + losses
    if total == 0:
        if compact:
            print(f"insufficient data (skipped={skipped})")
        else:
            print(f"  Insufficient data (skipped={skipped}, need more observations)")
        return

    wr = wins / total * 100
    avg_move = sum(move_sizes) / len(move_sizes) if move_sizes else 0

    if compact:
        print(f"WR={wr:.1f}% ({wins}/{total}) avg_move={avg_move:.4f} skip={skipped}")
    else:
        print(f"  Win rate:     {wr:.1f}%  ({wins}W / {losses}L, {skipped} skipped)")
        print(f"  Avg token move: {avg_move:.4f} ({avg_move*100:.2f}pp)")
        print(f"  Break-even WR needed: ~55% (to cover 1.8% round-trip fee)")
        verdict = "EDGE EXISTS" if wr > 55 and avg_move > 0.03 else (
                  "WEAK" if wr > 52 else "NO EDGE")
        print(f"  → {verdict}")


def _analyse_lag_distribution(
    records: List[dict],
    by_token: Dict[str, List[dict]],
    min_move: float,
) -> None:
    lag_buckets = defaultdict(int)  # seconds → count of times Polymarket caught up within that time

    for r in records:
        binance_move = r.get("binance_1m_pct", 0) or 0
        if abs(binance_move) < min_move:
            continue

        token_obs = by_token[r["token_id"]]
        start_price = r["polymarket_price"]
        start_ts = r["ts"]

        if r["side"] == "YES":
            expected_up = binance_move > 0
        else:
            expected_up = binance_move < 0  # NO rises when YES falls

        # Walk forward until token moves ≥ 0.02 in expected direction
        caught_up = False
        for obs in token_obs:
            if obs["ts"] <= start_ts:
                continue
            if obs["ts"] > start_ts + 300:  # max 5 min
                break
            move = obs["polymarket_price"] - start_price
            if expected_up and move >= 0.02:
                elapsed = int(obs["ts"] - start_ts)
                bucket = (elapsed // 15) * 15  # round to 15s buckets
                lag_buckets[bucket] += 1
                caught_up = True
                break
            elif not expected_up and move <= -0.02:
                elapsed = int(obs["ts"] - start_ts)
                bucket = (elapsed // 15) * 15
                lag_buckets[bucket] += 1
                caught_up = True
                break

        if not caught_up:
            lag_buckets[999] += 1  # never caught up within window

    if not lag_buckets:
        print("  Not enough data.")
        return

    total = sum(lag_buckets.values())
    never = lag_buckets.pop(999, 0)

    print(f"  (n={total+never} events where Binance moved ≥{min_move}%)")
    cumulative = 0
    for bucket in sorted(lag_buckets.keys()):
        count = lag_buckets[bucket]
        cumulative += count
        pct = count / total * 100 if total > 0 else 0
        cum_pct = cumulative / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  ≤{bucket+15:3d}s: {count:4d} ({pct:5.1f}%)  cumulative={cum_pct:.1f}%  {bar}")
    print(f"  Never:  {never:4d} ({never/(total+never)*100:.1f}% of events never repriced ≥0.02 within 5min)")


def _analyse_correlation(
    records: List[dict],
    by_token: Dict[str, List[dict]],
    lookahead: int,
) -> None:
    pairs = []
    for r in records:
        binance_move = r.get("binance_1m_pct")
        if binance_move is None:
            continue
        future = _find_future(by_token[r["token_id"]], r["ts"], lookahead)
        if future is None:
            continue
        token_move = future["polymarket_price"] - r["polymarket_price"]
        # Normalise NO tokens: NO rising = negative correlation with Binance up
        if r["side"] == "NO":
            token_move = -token_move
        pairs.append((binance_move, token_move))

    if len(pairs) < 10:
        print("  Not enough data for correlation.")
        return

    # Pearson correlation
    n = len(pairs)
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den_x = sum((x - mx) ** 2 for x in xs) ** 0.5
    den_y = sum((y - my) ** 2 for y in ys) ** 0.5
    corr = num / (den_x * den_y) if den_x * den_y > 1e-10 else 0

    print(f"  Pearson r = {corr:.4f}  (n={n} pairs)")
    if corr > 0.3:
        print("  → STRONG positive correlation: Binance predicts Polymarket direction")
    elif corr > 0.1:
        print("  → WEAK correlation: some signal but noisy")
    else:
        print("  → NO correlation: Binance moves do not predict Polymarket token direction")


def _print_verdict(
    records: List[dict],
    by_token: Dict[str, List[dict]],
    min_move: float,
) -> None:
    # Quick 60s win rate check at different Binance move thresholds
    for threshold in [0.1, 0.2, 0.3, 0.5]:
        wins = losses = 0
        moves = []
        for r in records:
            binance_move = r.get("binance_1m_pct", 0) or 0
            if abs(binance_move) < threshold:
                continue
            future = _find_future(by_token[r["token_id"]], r["ts"], 60)
            if future is None:
                continue
            token_move = future["polymarket_price"] - r["polymarket_price"]
            if r["side"] == "NO":
                token_move = -token_move
            expected = 1 if binance_move > 0 else -1
            actual = 1 if token_move > 0.005 else (-1 if token_move < -0.005 else 0)
            if actual == 0:
                continue
            if actual == expected:
                wins += 1
                moves.append(abs(token_move))
            else:
                losses += 1
                moves.append(abs(token_move))

        total = wins + losses
        if total < 5:
            continue
        wr = wins / total * 100
        avg_move = sum(moves) / len(moves) if moves else 0
        viable = "✓ VIABLE" if wr > 55 and avg_move > 0.03 else "✗ not viable"
        print(f"  Binance ≥{threshold:.1f}%: WR={wr:.1f}% ({total} samples) avg_move={avg_move:.4f}  {viable}")

    print(f"""
How to interpret:
  WR > 55% AND avg_move > 0.03 at some threshold → lag edge exists, implement the strategy
  WR 50-55% → marginal, not enough to overcome fees
  WR < 50%  → Binance is anti-predictive or random — do NOT implement
""")


def _find_future(obs_list: List[dict], start_ts: float, target_delta: int) -> Optional[dict]:
    """Find the observation closest to start_ts + target_delta seconds."""
    target_ts = start_ts + target_delta
    best = None
    best_diff = float("inf")
    for obs in obs_list:
        if obs["ts"] <= start_ts:
            continue
        diff = abs(obs["ts"] - target_ts)
        if diff < best_diff and diff < target_delta * 0.5:  # must be within 50% of target window
            best_diff = diff
            best = obs
    return best


def _ts_str(ts: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyse Binance→Polymarket lag")
    parser.add_argument("--asset", help="Filter by asset (BTC/ETH/SOL)")
    parser.add_argument("--min-move", type=float, default=0.2,
                        help="Min Binance 1m move %% to include (default 0.2)")
    parser.add_argument("--log", default=str(LOG_PATH), help="Path to lag_observations.jsonl")
    args = parser.parse_args()

    LOG_PATH_ARG = Path(args.log)
    observations = load_observations(LOG_PATH_ARG)
    print(f"Loaded {len(observations)} raw observations from {LOG_PATH_ARG}")
    analyse(observations, asset_filter=args.asset, min_binance_move_pct=args.min_move)
