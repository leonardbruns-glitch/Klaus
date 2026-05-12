"""
Wallet copy-trade SIMULATOR / REPLAY.

For each trade in logs/shadow/hot/<date>/wallet_shadow.jsonl:
  1. Apply configurable lag (250ms / 1s / 3s / 5s).
  2. Estimate executable fill against the recorded book snapshot:
     - Walk the asks: ask[0], ask[1], ... until our stake is filled.
     - Sweep cost = weighted avg of consumed levels.
     - If stake exceeds available top-5 liquidity, record partial / unfilled.
  3. Two replay modes:
     - hold-to-resolution: hold until market closes; payoff = outcome × shares × (1-fee).
     - mirror-exit: when the SAME wallet sells/redeems the same asset later, exit at that price.
  4. Resolution lookup via Gamma /markets (closed + outcomePrices).
     Open positions marked to current best-bid (CLOB /book).
  5. Per-wallet metrics: PnL, EV/trade, fill success %, slippage paid, max drawdown,
     fees-adjusted returns. Latency sensitivity = same trades run at each lag.
  6. Wallet correlation: trades on same condition_id within CORR_WINDOW_S of each other.
     Multi-wallet agreement = expectancy uplift when ≥2 tracked wallets enter same market.

Outputs:
  - stdout: ranked table per latency, cluster breakdown, correlation matrix
  - logs/shadow/wallet_replay_<date>.json: full structured results
  - logs/shadow/wallet_replay_<date>.csv: per-trade replay (one row per fill)

Run:
    python3 -m analytics.wallet_replay [--date YYYY-MM-DD] [--stake 5] [--mode hold|mirror]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
OUT_DIR = Path("/root/Klaus/logs/shadow")
DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

DEFAULT_STAKE = 5.0
FEE_BPS = 200                       # 2% Polymarket taker fee both legs effectively
DEFAULT_LATENCIES = [0.25, 1.0, 3.0, 5.0, 10.0]
CORR_WINDOW_S = 120                 # synchronized-entry window for correlation
SLIPPAGE_PER_SEC = 0.005            # 0.5¢ per second of lag, additive on top of book walk
MIN_FILL_PCT = 0.10                 # below this, count as unfilled

# Cluster mapping (mirror analytics/wallet_hunt2.py)
def cluster(slug: str) -> str:
    s = (slug or "").lower()
    if "updown" in s: return "updown"
    if any(k in s for k in ["atp-", "wta-", "tennis"]): return "tennis"
    if any(k in s for k in ["nba", "wnba", "basketball"]): return "basketball"
    if any(k in s for k in ["nfl", "football"]): return "nfl"
    if any(k in s for k in ["mlb", "baseball"]): return "mlb"
    if any(k in s for k in ["nhl", "hockey"]): return "nhl"
    if any(k in s for k in ["fifa", "world-cup", "soccer", "laliga", "epl", "ucl", "liga"]): return "soccer"
    if any(k in s for k in ["lol-", "cs2-", "dota", "valorant", "esport"]): return "esports"
    if any(k in s for k in ["ufc", "mma", "boxing"]): return "combat"
    if any(k in s for k in ["election", "president", "senate", "congress", "governor", "poll", "approval", "prime-minister", "starmer", "fed-chair", "fed-rate", "interest-rate"]): return "politics"
    if any(k in s for k in ["iran", "israel", "ukraine", "russia", "china", "war", "peace", "strike", "regime", "nuclear", "sanction", "hormuz", "gaza"]): return "geopolitics"
    if any(k in s for k in ["cpi", "inflation", "recession", "jobs", "unemployment", "gdp"]): return "macro_eco"
    if any(k in s for k in ["epstein", "released", "leaked", "revealed", "disclose"]): return "disclosure"
    if any(k in s for k in ["pandemic", "virus", "flu", "outbreak", "hanta", "measles"]): return "health"
    if any(k in s for k in ["bitcoin", "ethereum", "btc", "eth", "sol", "crypto", "solana", "cardano", "xrp"]): return "crypto_macro"
    if any(k in s for k in ["oscar", "grammy", "emmy", "movie", "box-office", "show"]): return "entertainment"
    if any(k in s for k in ["weather", "temperature", "snow", "rain", "hurricane", "tornado"]): return "weather"
    return "other"


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- I/O
def load_events(date_str: str):
    p = LOG_DIR / date_str / "wallet_shadow.jsonl"
    if not p.exists():
        print(f"no shadow log at {p}", file=sys.stderr)
        return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _normalize_book_side(side) -> list[tuple[float, float]]:
    """Return list of (price, size) tuples."""
    levels: list[tuple[float, float]] = []
    if not side:
        return levels
    for x in side:
        if isinstance(x, (list, tuple)) and len(x) >= 2:
            try:
                levels.append((float(x[0]), float(x[1])))
            except (TypeError, ValueError):
                continue
        elif isinstance(x, dict):
            try:
                levels.append((float(x.get("price", 0)), float(x.get("size", 0))))
            except (TypeError, ValueError):
                continue
    return levels


def normalize_book(book: Optional[dict]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    if not book:
        return [], []
    asks = _normalize_book_side(book.get("asks"))
    bids = _normalize_book_side(book.get("bids"))
    asks.sort(key=lambda x: x[0])           # ascending: cheapest first
    bids.sort(key=lambda x: -x[0])          # descending: highest first
    return asks, bids


# --------------------------------------------------------------------------- Fill model
def compute_fill(asks: list[tuple[float, float]],
                 stake_usd: float,
                 wallet_price: float,
                 lag_s: float) -> dict:
    """
    Walk the asks to fill stake_usd. Apply per-second slippage on top of book walk.

    Returns dict:
      avg_price, shares, cost, filled_pct, slip_vs_wallet, levels_consumed
    """
    if not asks:
        # Wallet swept everything; we couldn't get in
        return dict(avg_price=0.0, shares=0.0, cost=0.0, filled_pct=0.0,
                    slip_vs_wallet=0.0, levels_consumed=0)
    # Time-decay adjustment: book moves up SLIPPAGE_PER_SEC × lag_s
    lag_slip = lag_s * SLIPPAGE_PER_SEC
    cost_remaining = stake_usd
    total_cost = 0.0
    total_shares = 0.0
    levels_consumed = 0
    for price, size in asks:
        effective_px = min(0.999, price + lag_slip)
        if effective_px <= 0:
            continue
        level_capacity_usd = size * effective_px
        if cost_remaining <= level_capacity_usd:
            shares_here = cost_remaining / effective_px
            total_cost += cost_remaining
            total_shares += shares_here
            cost_remaining = 0
            levels_consumed += 1
            break
        else:
            total_cost += level_capacity_usd
            total_shares += size
            cost_remaining -= level_capacity_usd
            levels_consumed += 1
    if total_shares <= 0:
        return dict(avg_price=0.0, shares=0.0, cost=0.0, filled_pct=0.0,
                    slip_vs_wallet=0.0, levels_consumed=0)
    avg_price = total_cost / total_shares
    filled_pct = min(1.0, (stake_usd - cost_remaining) / max(1e-9, stake_usd))
    slip = max(0.0, avg_price - wallet_price) if wallet_price > 0 else 0.0
    return dict(avg_price=avg_price, shares=total_shares, cost=total_cost,
                filled_pct=filled_pct, slip_vs_wallet=slip,
                levels_consumed=levels_consumed)


# --------------------------------------------------------------------------- Resolution / mark
def resolve_or_mark(condition_id: str,
                    slug: str,
                    outcome: str,
                    asset: str,
                    sess: requests.Session,
                    cache_resolve: dict,
                    cache_mark: dict) -> dict:
    """
    Return: {resolved: bool, payout: 0/1 if resolved, mark: float if not, source: str}
    """
    key = condition_id or slug
    if key in cache_resolve:
        return cache_resolve[key]
    try:
        params = {"condition_ids": condition_id} if condition_id else {"slug": slug}
        r = sess.get(f"{GAMMA}/markets", params=params, timeout=10)
        if r.status_code == 200:
            d = r.json()
            md = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else None)
            if md and md.get("closed"):
                outcomes = md.get("outcomes")
                prices = md.get("outcomePrices")
                if isinstance(outcomes, str): outcomes = json.loads(outcomes)
                if isinstance(prices, str): prices = json.loads(prices)
                if outcomes and prices:
                    for o, p in zip(outcomes, prices):
                        if str(o).strip().lower() == str(outcome or "").strip().lower():
                            res = dict(resolved=True, payout=float(p), mark=float(p), source="resolved")
                            cache_resolve[key] = res
                            return res
    except Exception:
        pass
    # Not resolved → mark to current best-bid
    if asset in cache_mark:
        m = cache_mark[asset]
    else:
        m = None
        try:
            r = sess.get(f"{CLOB}/book", params={"token_id": asset}, timeout=6)
            if r.status_code == 200:
                d = r.json()
                bids = _normalize_book_side(d.get("bids"))
                m = max((p for p, _ in bids), default=0.0)
        except Exception:
            m = None
        cache_mark[asset] = m if m is not None else 0.0
    out = dict(resolved=False, payout=None, mark=cache_mark[asset] or 0.0, source="mark_to_bid")
    cache_resolve[key] = out
    return out


# --------------------------------------------------------------------------- Mirror-exit detection
def detect_exit(ev: dict, future_events: list, max_window_s: int = 3 * 3600) -> Optional[dict]:
    """
    Find the SAME wallet selling the SAME asset within max_window_s after ev.
    Used in mirror-exit mode to track when the wallet closes a position.
    """
    w = ev.get("wallet")
    asset = ev.get("asset")
    ts = int(ev.get("ts", 0))
    if not (w and asset and ts):
        return None
    for nxt in future_events:
        nts = int(nxt.get("ts", 0))
        if nts <= ts:
            continue
        if nts - ts > max_window_s:
            break
        if nxt.get("wallet") != w:
            continue
        if nxt.get("asset") != asset:
            continue
        if (nxt.get("side") or "").upper() == "SELL":
            return nxt
    return None


def detect_merge_exit(ev: dict, future_events: list, max_window_s: int = 24 * 3600) -> Optional[dict]:
    """
    Find a wallet_merge event from the same wallet on the same condition_id after ev.

    A MERGE means the wallet burned YES+NO pairs for $1 each per matched share.
    For our copy: if the wallet merged on this condition_id, AND we copied both
    legs, our copy can also merge → exit at $1.00 per share.

    NOTE: this UPPER-BOUNDS copy-trade PnL — it assumes our shadow copied BOTH
    legs. If only one leg was copied, we cannot merge alone.
    """
    w = ev.get("wallet")
    cid = ev.get("condition_id")
    ts = int(ev.get("ts", 0))
    if not (w and cid and ts):
        return None
    for nxt in future_events:
        if nxt.get("rec") != "wallet_merge":
            continue
        nts = int(nxt.get("ts", 0))
        if nts <= ts:
            continue
        if nts - ts > max_window_s:
            break
        if nxt.get("wallet") != w:
            continue
        if nxt.get("condition_id") != cid:
            continue
        return nxt
    return None


# --------------------------------------------------------------------------- Simulator core
def simulate(events: list, stake_usd: float, lag_s: float, mode: str,
             sess: requests.Session, cache_resolve: dict, cache_mark: dict) -> tuple[list, dict]:
    """
    Returns (per_trade_records, per_wallet_summary)
    """
    events_sorted = sorted(events, key=lambda e: int(e.get("ts", 0) or 0))
    fills = []
    wallet_pnl_series: dict[str, list[float]] = defaultdict(list)

    for i, ev in enumerate(events_sorted):
        if ev.get("rec") != "wallet_trade":
            continue
        if (ev.get("side") or "").upper() != "BUY":
            continue  # SELLs handled implicitly by mirror-exit detection

        wname = ev.get("wallet_name", "?")
        slug = ev.get("slug") or ""
        cl = cluster(slug)
        wallet_price = float(ev.get("price") or 0)
        asset = ev.get("asset") or ""
        cid = ev.get("condition_id") or ""
        outcome = ev.get("outcome") or ""

        asks, _ = normalize_book(ev.get("book_this"))
        fill = compute_fill(asks, stake_usd, wallet_price, lag_s)

        if fill["filled_pct"] < MIN_FILL_PCT:
            fills.append(dict(
                wallet=wname, cluster=cl, ts=int(ev.get("ts", 0) or 0),
                slug=slug, outcome=outcome, condition_id=cid, asset=asset,
                wallet_price=wallet_price, stake=stake_usd,
                fill_price=0.0, shares=0.0, filled_pct=fill["filled_pct"],
                slip=0.0, levels=fill["levels_consumed"],
                resolved=False, payout=None, mark=0.0, mode=mode,
                pnl_gross=0.0, pnl_net=0.0, status="UNFILLED",
            ))
            continue

        cost = fill["cost"]
        shares = fill["shares"]

        # Exit logic
        exit_price = None
        status = "OPEN"
        if mode == "merge":
            merge_ev = detect_merge_exit(ev, events_sorted[i + 1:])
            if merge_ev is not None:
                exit_price = 1.0  # MERGE pays $1 per matched share
                status = "EXIT_MERGE"
        if exit_price is None and mode == "mirror":
            exit_ev = detect_exit(ev, events_sorted[i + 1:])
            if exit_ev is not None:
                exit_price = float(exit_ev.get("price") or 0)
                status = "EXIT_MIRROR"
        if exit_price is None:
            r = resolve_or_mark(cid, slug, outcome, asset, sess, cache_resolve, cache_mark)
            if r["resolved"]:
                exit_price = r["payout"] or 0.0
                status = "RESOLVED"
            else:
                exit_price = r["mark"]
                status = "OPEN_MARK"

        # Apply fee on exit (taker rebate / fee). Fee applies only on positive payouts above cost.
        gross_payout = shares * exit_price
        fee = gross_payout * (FEE_BPS / 10000.0) if exit_price > 0 else 0.0
        pnl_gross = gross_payout - cost
        pnl_net = pnl_gross - fee

        fills.append(dict(
            wallet=wname, cluster=cl, ts=int(ev.get("ts", 0) or 0),
            slug=slug, outcome=outcome, condition_id=cid, asset=asset,
            wallet_price=wallet_price, stake=stake_usd,
            fill_price=round(fill["avg_price"], 5),
            shares=round(shares, 4),
            filled_pct=round(fill["filled_pct"], 3),
            slip=round(fill["slip_vs_wallet"], 5),
            levels=fill["levels_consumed"],
            resolved=(status == "RESOLVED"),
            payout=exit_price if status == "RESOLVED" else None,
            mark=exit_price,
            mode=mode,
            pnl_gross=round(pnl_gross, 4),
            pnl_net=round(pnl_net, 4),
            status=status,
        ))
        wallet_pnl_series[wname].append(pnl_net)

    # Aggregate per-wallet
    per_wallet = {}
    for w, series in wallet_pnl_series.items():
        # Need to walk fills for this wallet to compute richer stats
        w_fills = [f for f in fills if f["wallet"] == w]
        n_total = len(w_fills)
        n_filled = sum(1 for f in w_fills if f["status"] != "UNFILLED")
        n_resolved = sum(1 for f in w_fills if f["status"] == "RESOLVED")
        n_resolved_won = sum(1 for f in w_fills if f["status"] == "RESOLVED" and f["pnl_net"] > 0)
        n_open = sum(1 for f in w_fills if f["status"] in ("OPEN", "OPEN_MARK"))
        n_mirror = sum(1 for f in w_fills if f["status"] == "EXIT_MIRROR")
        n_merge = sum(1 for f in w_fills if f["status"] == "EXIT_MERGE")
        cost_total = sum(f["stake"] * f["filled_pct"] for f in w_fills)
        pnl_resolved = sum(f["pnl_net"] for f in w_fills if f["status"] == "RESOLVED")
        pnl_open = sum(f["pnl_net"] for f in w_fills if f["status"] in ("OPEN", "OPEN_MARK"))
        pnl_mirror = sum(f["pnl_net"] for f in w_fills if f["status"] == "EXIT_MIRROR")
        pnl_merge = sum(f["pnl_net"] for f in w_fills if f["status"] == "EXIT_MERGE")
        pnl_total = pnl_resolved + pnl_open + pnl_mirror + pnl_merge
        slip_total = sum(f["slip"] * f["shares"] for f in w_fills)

        # Running cumulative PnL & drawdown
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for v in series:
            cum += v
            if cum > peak: peak = cum
            dd = peak - cum
            if dd > max_dd: max_dd = dd

        ev_trade = (pnl_total / n_filled) if n_filled else 0.0
        wr_resolved = (n_resolved_won / n_resolved) if n_resolved else 0.0
        roi = (pnl_total / cost_total) if cost_total > 0 else 0.0

        per_wallet[w] = dict(
            n_total=n_total, n_filled=n_filled, fill_pct=round(100 * n_filled / max(1, n_total), 1),
            n_resolved=n_resolved, n_resolved_won=n_resolved_won, wr_resolved=round(wr_resolved, 3),
            n_open=n_open, n_mirror=n_mirror, n_merge=n_merge,
            cost=round(cost_total, 2),
            pnl_resolved=round(pnl_resolved, 2),
            pnl_open=round(pnl_open, 2),
            pnl_mirror=round(pnl_mirror, 2),
            pnl_merge=round(pnl_merge, 2),
            pnl_total=round(pnl_total, 2),
            ev_trade=round(ev_trade, 4),
            roi=round(roi, 4),
            slip_total=round(slip_total, 2),
            max_drawdown=round(max_dd, 2),
        )
    return fills, per_wallet


# --------------------------------------------------------------------------- Correlation
def correlation_analysis(events: list, window_s: int = CORR_WINDOW_S):
    """
    Build a co-occurrence matrix: for each pair of tracked wallets, count
    times they entered the same condition_id within `window_s`.

    Returns:
      pair_counts: {(w1,w2): n}
      market_groups: {condition_id: [(ts, wallet)]}
      multi_agree: list of (condition_id, [wallets], avg_pnl) tuples
    """
    events_sorted = sorted(events, key=lambda e: int(e.get("ts", 0) or 0))
    by_cid: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for ev in events_sorted:
        if ev.get("rec") != "wallet_trade": continue
        if (ev.get("side") or "").upper() != "BUY": continue
        cid = ev.get("condition_id")
        if not cid: continue
        by_cid[cid].append((int(ev.get("ts", 0) or 0), ev.get("wallet_name", "?")))

    pair_counts: dict[tuple, int] = defaultdict(int)
    multi_agree = []  # (cid, [wallets within window])
    for cid, trades in by_cid.items():
        # group by ts within window
        if len(trades) < 2:
            continue
        trades.sort()
        # Sliding window across all trades on this cid
        seen_pairs = set()
        i = 0
        # First, find any cluster of wallets within window
        wallets_in_window: set[str] = set()
        anchor_ts = trades[0][0]
        for ts, w in trades:
            if ts - anchor_ts > window_s:
                anchor_ts = ts
                wallets_in_window = set()
            wallets_in_window.add(w)
            if len(wallets_in_window) >= 2:
                multi_agree.append((cid, sorted(wallets_in_window), ts))
        # Pair counts: any two trades on same cid (regardless of window)
        wallets_on_cid = list({w for _, w in trades})
        for a in range(len(wallets_on_cid)):
            for b in range(a + 1, len(wallets_on_cid)):
                key = tuple(sorted([wallets_on_cid[a], wallets_on_cid[b]]))
                pair_counts[key] += 1
    return pair_counts, by_cid, multi_agree


# --------------------------------------------------------------------------- Output
def print_summary_table(per_wallet: dict, label: str):
    print(f"\n=== {label} ===")
    print(f"{'wallet':<26} {'tot':>4} {'fill':>4} {'fpct':>5} {'res':>4} {'won':>4} {'wr%':>5} {'cost':>8} {'res_p':>8} {'open_p':>8} {'TOTAL':>9} {'ROI%':>7} {'EV':>7} {'maxDD':>8}")
    items = sorted(per_wallet.items(), key=lambda kv: -kv[1]["pnl_total"])
    for w, s in items:
        print(f"{w:<26} {s['n_total']:>4} {s['n_filled']:>4} {s['fill_pct']:>4.0f}% "
              f"{s['n_resolved']:>4} {s['n_resolved_won']:>4} {s['wr_resolved']*100:>4.0f}% "
              f"${s['cost']:>6,.0f} ${s['pnl_resolved']:>+6,.0f} ${s['pnl_open']:>+6,.0f} "
              f"${s['pnl_total']:>+7,.0f} {s['roi']*100:>+6.1f}% {s['ev_trade']:>+6.3f} ${s['max_drawdown']:>6,.0f}")


def print_cluster_breakdown(fills_by_latency: dict, latency_label: float):
    """Group fills by cluster, print PnL roll-up."""
    fills = fills_by_latency[latency_label]
    by_cluster = defaultdict(lambda: {"n": 0, "n_filled": 0, "n_resolved": 0,
                                       "n_won": 0, "cost": 0.0, "pnl": 0.0})
    for f in fills:
        c = by_cluster[f["cluster"]]
        c["n"] += 1
        if f["status"] != "UNFILLED": c["n_filled"] += 1
        if f["status"] == "RESOLVED": c["n_resolved"] += 1
        if f["status"] == "RESOLVED" and f["pnl_net"] > 0: c["n_won"] += 1
        c["cost"] += f["stake"] * f["filled_pct"]
        c["pnl"] += f["pnl_net"]
    print(f"\n=== CLUSTER BREAKDOWN at lag={latency_label}s ===")
    print(f"{'cluster':<14} {'n':>5} {'filled':>7} {'resolved':>9} {'won':>5} {'wr%':>5} {'cost':>9} {'pnl':>9} {'ROI%':>7}")
    for c, s in sorted(by_cluster.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = (s["n_won"] / s["n_resolved"]) * 100 if s["n_resolved"] else 0
        roi = (s["pnl"] / s["cost"]) * 100 if s["cost"] else 0
        print(f"{c:<14} {s['n']:>5} {s['n_filled']:>7} {s['n_resolved']:>9} {s['n_won']:>5} {wr:>4.0f}% ${s['cost']:>7,.0f} ${s['pnl']:>+7,.0f} {roi:>+6.1f}%")


def print_latency_sensitivity(by_lat: dict):
    print(f"\n=== LATENCY SENSITIVITY ===")
    print(f"{'lag(s)':<8} {'sum_pnl':>10} {'sum_cost':>10} {'sum_roi%':>9} {'avg_slip':>9} {'fill%':>6}")
    for lag in sorted(by_lat.keys()):
        pw = by_lat[lag]["per_wallet"]
        sp = sum(s["pnl_total"] for s in pw.values())
        sc = sum(s["cost"] for s in pw.values())
        ss = sum(s["slip_total"] for s in pw.values())
        nt = sum(s["n_total"] for s in pw.values())
        nf = sum(s["n_filled"] for s in pw.values())
        fp = 100 * nf / max(1, nt)
        roi = 100 * sp / max(1, sc)
        print(f"{lag:<8.2f} ${sp:>+8,.1f} ${sc:>9,.1f} {roi:>+8.2f}% ${ss:>8,.2f} {fp:>5.1f}%")


def print_correlation(pair_counts: dict, by_cid: dict, multi_agree: list):
    print(f"\n=== WALLET CORRELATION (co-trades on same condition_id) ===")
    if not pair_counts:
        print("  no co-trades detected")
        return
    items = sorted(pair_counts.items(), key=lambda kv: -kv[1])
    print(f"  {'wallet_a':<26} {'wallet_b':<26} {'shared_markets':>14}")
    for (a, b), n in items[:25]:
        print(f"  {a:<26} {b:<26} {n:>14}")
    # Multi-wallet agreement frequency
    cid_with_multi = len({c for c, _, _ in multi_agree})
    print(f"\n  markets with ≥2 tracked wallets within {CORR_WINDOW_S}s: {cid_with_multi}")
    # Top-mentioned markets
    cid_count: dict[str, set[str]] = defaultdict(set)
    for c, ws, _ in multi_agree:
        cid_count[c].update(ws)
    top = sorted(cid_count.items(), key=lambda kv: -len(kv[1]))[:10]
    if top:
        print(f"  top markets (by # wallets):")
        for c, ws in top:
            print(f"    {c[:18]}...  {len(ws)} wallets: {sorted(ws)}")


def export_csv(fills: list, path: Path):
    if not fills:
        return
    cols = ["ts", "wallet", "cluster", "slug", "condition_id", "asset", "outcome",
            "wallet_price", "stake", "fill_price", "shares", "filled_pct",
            "slip", "levels", "resolved", "payout", "mark", "mode",
            "pnl_gross", "pnl_net", "status"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in fills:
            w.writerow(r)


# --------------------------------------------------------------------------- Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=utc_today())
    ap.add_argument("--stake", type=float, default=DEFAULT_STAKE)
    ap.add_argument("--mode", choices=["hold", "mirror", "merge"], default="hold",
                    help="hold-to-resolution, mirror wallet SELL, or merge (uses /activity MERGE events)")
    ap.add_argument("--latencies", type=float, nargs="*", default=DEFAULT_LATENCIES)
    ap.add_argument("--csv-lag", type=float, default=3.0,
                    help="which lag's fills to export to CSV")
    args = ap.parse_args()

    events = load_events(args.date)
    print(f"# wallet_replay  date={args.date}  stake=${args.stake:.2f}  mode={args.mode}")
    print(f"# loaded {len(events)} events from shadow log")
    if not events:
        return

    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})

    cache_resolve: dict = {}
    cache_mark: dict = {}

    by_lat = {}
    for lag in args.latencies:
        fills, per_wallet = simulate(events, args.stake, lag, args.mode,
                                     sess, cache_resolve, cache_mark)
        by_lat[lag] = {"fills": fills, "per_wallet": per_wallet}

    # 1) Per-latency per-wallet summary
    for lag in sorted(by_lat.keys()):
        print_summary_table(by_lat[lag]["per_wallet"], f"WALLETS at lag={lag}s ({args.mode})")

    # 2) Cluster breakdown for the middle latency (3s)
    mid_lag = min(args.latencies, key=lambda x: abs(x - 3.0))
    print_cluster_breakdown({lag: by_lat[lag]["fills"] for lag in by_lat}, mid_lag)

    # 3) Latency sensitivity
    print_latency_sensitivity(by_lat)

    # 4) Correlation analysis (lag-independent)
    pair_counts, by_cid, multi_agree = correlation_analysis(events)
    print_correlation(pair_counts, by_cid, multi_agree)

    # 5) Save JSON + CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"wallet_replay_{args.date}.json"
    json_path.write_text(json.dumps({
        "date": args.date,
        "stake": args.stake,
        "mode": args.mode,
        "by_latency": {str(k): {"per_wallet": v["per_wallet"]} for k, v in by_lat.items()},
        "correlation": {
            "pair_counts": {f"{a}||{b}": n for (a, b), n in pair_counts.items()},
            "markets_with_multi_agree": len({c for c, _, _ in multi_agree}),
        }
    }, default=str, indent=2))
    csv_path = OUT_DIR / f"wallet_replay_{args.date}_lag{args.csv_lag}.csv"
    if args.csv_lag in by_lat:
        export_csv(by_lat[args.csv_lag]["fills"], csv_path)
        print(f"\nsaved {csv_path}")
    print(f"saved {json_path}")


if __name__ == "__main__":
    main()
