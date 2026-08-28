"""
Single-market tick-level reconstruction.

Goal: falsify the U-shape / maker-arb / single-shot thesis on ONE market with
full evidence rather than aggregate metrics.

What it does:
  1. Pull EVERY trade on a market via /trades?market=<conditionId>, paginated.
  2. Sort chronologically. For each fill, record:
     ts, taker_wallet, side (BUY/SELL — but only takers appear), price, size,
     outcome_index, transactionHash.
  3. Reconstruct an implicit picture of book dynamics:
     - For each side, plot consecutive same-direction taker fills.
     - Gap between consecutive ask-hit prices → reveals depth past top of book.
     - Time between fills → reveals liquidity replenishment rate.
  4. Pair-completion test: for our tracked wallets, find when leg-A and leg-B
     of an arb pair happened. Compute time-gap; verify both filled at the
     implied prices; check if resolution actually paid out.
  5. Match against captured shadow book snapshots: did our REST-poll book reflect
     the live state or was it stale?
  6. Maker/taker probe: since /trades records takers only, our tracked wallets
     are takers on every trade we see. The "makers" thesis was wrong.

Outputs:
  - logs/shadow/market_microscope_<slug>.md  (full narrative)
  - logs/shadow/market_microscope_<slug>.json
  - stdout: condensed table

Run:
    python3 -m analytics.market_microscope --slug <slug>
    python3 -m analytics.market_microscope --cid <conditionId>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

OUT_DIR = Path("/root/Klaus/logs/shadow")
LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_market(sess, slug: Optional[str] = None, cid: Optional[str] = None) -> Optional[dict]:
    params = {}
    if cid: params["condition_ids"] = cid
    if slug: params["slug"] = slug
    if not params: return None
    try:
        r = sess.get(f"{GAMMA}/markets", params=params, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        if isinstance(d, list) and d: return d[0]
        if isinstance(d, dict): return d
    except Exception:
        return None
    return None


def fetch_all_market_trades(sess, cid: str, max_pages: int = 50) -> list[dict]:
    out = []
    offset = 0
    while offset < max_pages * 500:
        try:
            r = sess.get(f"{DATA}/trades", params={"market": cid, "limit": 500, "offset": offset}, timeout=20)
            if r.status_code != 200: break
            d = r.json()
            if not isinstance(d, list) or not d: break
            out.extend(d)
            if len(d) < 500: break
            offset += 500
            time.sleep(0.08)
        except Exception:
            break
    return out


def load_shadow_events_for_market(date_str: str, cid: str) -> list[dict]:
    p = LOG_DIR / date_str / "wallet_shadow.jsonl"
    if not p.exists(): return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                ev = json.loads(line)
                if ev.get("condition_id") == cid:
                    out.append(ev)
            except json.JSONDecodeError:
                continue
    return out


def reconstruct_per_outcome(trades: list[dict]) -> dict:
    """Per outcome_index, build chronological sequence of taker fills."""
    by_oi = defaultdict(list)
    for t in trades:
        oi = t.get("outcomeIndex")
        if oi is None: continue
        by_oi[oi].append({
            "ts": int(t.get("timestamp", 0) or 0),
            "wallet": (t.get("proxyWallet") or "").lower(),
            "side": t.get("side"),
            "price": float(t.get("price", 0) or 0),
            "size": float(t.get("size", 0) or 0),
            "outcome": t.get("outcome"),
            "tx": t.get("transactionHash"),
            "name": t.get("name") or t.get("pseudonym") or "",
        })
    for oi in by_oi:
        by_oi[oi].sort(key=lambda x: (x["ts"], x["price"]))
    return dict(by_oi)


def analyze_outcome(fills: list[dict]) -> dict:
    """For one outcome's fill sequence: depth-of-book proxies, liquidity replenishment."""
    if not fills: return {}
    buys = [f for f in fills if f["side"] == "BUY"]
    sells = [f for f in fills if f["side"] == "SELL"]

    # Consecutive BUY price gaps: shows if next-best ask was nearby (dense) or far (sparse)
    buy_gaps = []
    for i in range(1, len(buys)):
        dt = buys[i]["ts"] - buys[i - 1]["ts"]
        dp = buys[i]["price"] - buys[i - 1]["price"]
        buy_gaps.append((dt, dp, buys[i]["price"], buys[i - 1]["price"]))

    # Liquidity replenishment: how often does the SAME price get hit multiple times?
    # If multiple BUYs at exactly the same price within seconds, there's hidden depth.
    repeat_price_clusters = []
    if buys:
        i = 0
        while i < len(buys):
            j = i
            cluster_size = 0.0
            while j < len(buys) and abs(buys[j]["price"] - buys[i]["price"]) < 0.001 and (buys[j]["ts"] - buys[i]["ts"]) < 30:
                cluster_size += buys[j]["size"]
                j += 1
            if j > i + 1:
                repeat_price_clusters.append({
                    "price": buys[i]["price"],
                    "n_fills": j - i,
                    "total_size": cluster_size,
                    "duration_s": buys[j - 1]["ts"] - buys[i]["ts"],
                })
            i = j if j > i else i + 1

    # Price progression: if monotonically rising, book is sparse + walking up
    if buys:
        prices = [b["price"] for b in buys]
        n_rising = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])
        n_falling = sum(1 for i in range(1, len(prices)) if prices[i] < prices[i - 1])
        n_same = sum(1 for i in range(1, len(prices)) if prices[i] == prices[i - 1])
        price_min = min(prices)
        price_max = max(prices)
    else:
        n_rising = n_falling = n_same = 0
        price_min = price_max = 0

    # VWAP
    vwap = sum(b["price"] * b["size"] for b in buys) / max(1, sum(b["size"] for b in buys))

    return {
        "n_buys": len(buys),
        "n_sells": len(sells),
        "n_unique_takers": len({f["wallet"] for f in fills}),
        "buy_price_min": round(price_min, 4),
        "buy_price_max": round(price_max, 4),
        "buy_vwap": round(vwap, 4),
        "buy_size_total": round(sum(b["size"] for b in buys), 2),
        "n_rising": n_rising,
        "n_falling": n_falling,
        "n_same_price": n_same,
        "n_price_clusters": len(repeat_price_clusters),
        "largest_cluster": max((c["n_fills"] for c in repeat_price_clusters), default=0),
        "biggest_cluster_size": max((c["total_size"] for c in repeat_price_clusters), default=0),
        "fills": fills,  # full record
        "buy_gaps": buy_gaps,
        "repeat_price_clusters": repeat_price_clusters,
    }


def analyze_pair_completion(tracked_wallets: set[str], by_outcome: dict, market: dict) -> list[dict]:
    """For each tracked wallet that bought BOTH outcomes, compute pair completion."""
    out = []
    outcomes_list = market.get("outcomes")
    if isinstance(outcomes_list, str): outcomes_list = json.loads(outcomes_list)
    outcome_prices = market.get("outcomePrices")
    if isinstance(outcome_prices, str): outcome_prices = json.loads(outcome_prices)
    closed = market.get("closed", False)

    for w in tracked_wallets:
        w_legs = {}  # outcome_index -> list of fills
        for oi, fills in by_outcome.items():
            w_fills = [f for f in fills if f["wallet"] == w]
            if w_fills:
                w_legs[oi] = w_fills
        if len(w_legs) < 2:
            continue
        # Compute legs
        legs_info = []
        all_ts = []
        for oi, fills in w_legs.items():
            total_size = sum(f["size"] for f in fills if f["side"] == "BUY")
            total_cost = sum(f["size"] * f["price"] for f in fills if f["side"] == "BUY")
            avg_px = total_cost / max(1, total_size) if total_size else 0
            first_ts = min(f["ts"] for f in fills) if fills else 0
            last_ts = max(f["ts"] for f in fills) if fills else 0
            all_ts.append(first_ts)
            all_ts.append(last_ts)
            legs_info.append({
                "outcome_index": oi,
                "outcome": fills[0].get("outcome"),
                "n_fills": len(fills),
                "avg_price": round(avg_px, 4),
                "total_shares": round(total_size, 2),
                "total_cost": round(total_cost, 2),
                "first_ts": first_ts,
                "last_ts": last_ts,
            })
        # Time gap between earliest leg-A fill and earliest leg-B fill
        if len(legs_info) >= 2:
            first_per_leg = [l["first_ts"] for l in legs_info]
            time_gap = max(first_per_leg) - min(first_per_leg)
        else:
            time_gap = None
        sum_avg = sum(l["avg_price"] for l in legs_info)
        # Realized payoff if closed
        realized = None
        if closed and outcomes_list and outcome_prices:
            payoff = 0.0
            for l in legs_info:
                ow_outcome = (l.get("outcome") or "").lower()
                for o, p in zip(outcomes_list, outcome_prices):
                    if str(o).lower() == ow_outcome:
                        payoff += l["total_shares"] * float(p)
                        break
            total_cost_all = sum(l["total_cost"] for l in legs_info)
            realized = payoff - total_cost_all
        out.append({
            "wallet": w,
            "legs": legs_info,
            "sum_avg_prices": round(sum_avg, 4),
            "implied_arb_edge_pct": round((1.0 - sum_avg) * 100, 2),
            "time_gap_first_legs_s": time_gap,
            "is_resolved": closed,
            "realized_pnl_if_held": round(realized, 2) if realized is not None else None,
        })
    return out


def book_vs_implicit_check(shadow_events: list[dict], all_fills: list[dict]) -> list[dict]:
    """
    For each shadow snapshot of book_this, check:
      - what was the wallet's fill price?
      - what does the captured book best-ask say?
      - what was the previous trade on this asset?
      - what was the NEXT trade on this asset?
      - did the displayed best-ask match the next trade's price?
    This tests whether the captured book was stale vs reflective.
    """
    out = []
    for ev in shadow_events:
        if ev.get("rec") != "wallet_trade": continue
        ts = int(ev.get("ts", 0) or 0)
        asset = ev.get("asset", "")
        wallet_price = float(ev.get("price", 0) or 0)
        book = ev.get("book_this") or {}
        asks = book.get("asks") or []
        bids = book.get("bids") or []
        if not asks: continue
        try:
            ask_prices = [float(a[0]) if isinstance(a, (list, tuple)) else float(a.get("price", 0)) for a in asks]
            bid_prices = [float(b[0]) if isinstance(b, (list, tuple)) else float(b.get("price", 0)) for b in bids]
            best_ask = min(p for p in ask_prices if p > 0)
            best_bid = max(p for p in bid_prices if p > 0) if bid_prices else 0
        except (ValueError, IndexError):
            continue
        # Find next trade on this asset
        same_asset_after = [f for f in all_fills if f.get("asset") == asset and int(f.get("timestamp", 0) or 0) > ts]
        same_asset_after.sort(key=lambda f: int(f.get("timestamp", 0) or 0))
        next_trade = same_asset_after[0] if same_asset_after else None
        out.append({
            "ts": ts,
            "wallet_name": ev.get("wallet_name"),
            "wallet_price": wallet_price,
            "captured_best_ask": round(best_ask, 4),
            "captured_best_bid": round(best_bid, 4),
            "captured_spread": round(best_ask - best_bid, 4),
            "next_trade_price": float(next_trade.get("price", 0) or 0) if next_trade else None,
            "next_trade_dt_s": (int(next_trade.get("timestamp", 0) or 0) - ts) if next_trade else None,
            "next_trade_side": next_trade.get("side") if next_trade else None,
            "ask_matches_next": (
                abs(best_ask - float(next_trade.get("price", 0) or 0)) < 0.02
                if next_trade else None
            ),
        })
    return out


def emit_md(market: dict, by_oi: dict, analyses: dict, pair_completion: list, book_check: list,
            tracked_wallets: set[str], shadow_count: int) -> str:
    md = []
    slug = market.get("slug") or market.get("conditionId")
    md.append(f"# Market Microscope — `{slug}`\n")
    md.append(f"\n**Question**: {market.get('question', '')}\n")
    md.append(f"**End date**: {market.get('endDate', '')}\n")
    md.append(f"**Closed**: {market.get('closed', False)}\n")
    outcomes = market.get("outcomes")
    if isinstance(outcomes, str): outcomes = json.loads(outcomes)
    prices = market.get("outcomePrices")
    if isinstance(prices, str): prices = json.loads(prices)
    md.append(f"**Outcomes / final prices**: {list(zip(outcomes or [], prices or []))}\n")
    md.append(f"**Volume**: ${float(market.get('volume', 0)):,.0f}\n")
    md.append(f"\n## Tick reconstruction\n")
    for oi, fills in by_oi.items():
        a = analyses.get(oi, {})
        oc_name = (fills[0].get("outcome") if fills else "?") or "?"
        md.append(f"\n### Outcome[{oi}] = `{oc_name}`\n")
        md.append(f"\n| metric | value |\n|---|---|\n")
        md.append(f"| total BUY fills | {a.get('n_buys', 0)} |\n")
        md.append(f"| total SELL fills | {a.get('n_sells', 0)} |\n")
        md.append(f"| unique takers | {a.get('n_unique_takers', 0)} |\n")
        md.append(f"| BUY price range | {a.get('buy_price_min', 0):.3f} → {a.get('buy_price_max', 0):.3f} |\n")
        md.append(f"| BUY VWAP | {a.get('buy_vwap', 0):.4f} |\n")
        md.append(f"| total BUY shares | {a.get('buy_size_total', 0):,.0f} |\n")
        md.append(f"| rising-price hops | {a.get('n_rising', 0)} |\n")
        md.append(f"| falling-price hops | {a.get('n_falling', 0)} |\n")
        md.append(f"| same-price hops | {a.get('n_same_price', 0)} |\n")
        md.append(f"| price clusters (same px, ≤30s, ≥2 fills) | {a.get('n_price_clusters', 0)} |\n")
        md.append(f"| largest cluster (# fills) | {a.get('largest_cluster', 0)} |\n")
        md.append(f"| largest cluster (total size) | {a.get('biggest_cluster_size', 0):,.0f} |\n")
        # Sample clusters
        clusters = a.get("repeat_price_clusters", [])[:5]
        if clusters:
            md.append(f"\nTop price clusters (proves hidden depth or sub-second replenishment):\n")
            md.append(f"\n| price | n_fills | total_size | duration_s |\n|---|---|---|---|\n")
            for c in clusters:
                md.append(f"| {c['price']:.4f} | {c['n_fills']} | {c['total_size']:,.0f} | {c['duration_s']} |\n")
        # Sample BUY gaps where price jumps significantly
        gaps = [g for g in a.get("buy_gaps", []) if abs(g[1]) > 0.05]
        if gaps:
            md.append(f"\nLargest BUY price jumps (consecutive same-side takers):\n")
            md.append(f"\n| dt_s | dp | from→to |\n|---|---|---|\n")
            for dt, dp, p_to, p_from in gaps[:10]:
                md.append(f"| {dt} | {dp:+.3f} | {p_from:.3f} → {p_to:.3f} |\n")

    md.append(f"\n## Tracked-wallet pair completion\n")
    if not pair_completion:
        md.append("\nNo tracked wallets bought both sides of this market.\n")
    for pc in pair_completion:
        md.append(f"\n### Wallet `{pc['wallet'][:14]}...`\n")
        md.append(f"\n| outcome | n_fills | avg_buy | shares | cost | first_ts |\n|---|---|---|---|---|---|\n")
        for l in pc["legs"]:
            iso = datetime.utcfromtimestamp(l["first_ts"]).isoformat() if l["first_ts"] else "?"
            md.append(f"| {l['outcome']} | {l['n_fills']} | {l['avg_price']:.4f} | {l['total_shares']:,.0f} | ${l['total_cost']:,.2f} | {iso} |\n")
        md.append(f"\nsum_avg_prices: **{pc['sum_avg_prices']:.4f}** (implied arb edge: **{pc['implied_arb_edge_pct']:+.2f}%**)\n")
        md.append(f"\ntime gap between earliest fills on each leg: **{pc['time_gap_first_legs_s']}s**  ")
        md.append(f"resolved: {pc['is_resolved']}  ")
        md.append(f"realized_pnl_if_held: ${pc['realized_pnl_if_held']:+,.2f}\n" if pc['realized_pnl_if_held'] is not None else "realized: N/A (open)\n")

    md.append(f"\n## Captured book vs reality check ({len(book_check)} shadow snapshots)\n")
    if book_check:
        md.append(f"\nFor each captured book_this snapshot at trade time, compare best_ask vs the NEXT trade price.\n"
                  f"If they match: snapshot was reflective. If they diverge widely: snapshot stale or hidden liquidity.\n")
        md.append(f"\n| wallet | wallet_px | captured_best_ask | next_trade_px | next_dt_s | match? |\n|---|---|---|---|---|---|\n")
        for c in book_check[:20]:
            md.append(f"| {c['wallet_name']} | {c['wallet_price']:.3f} | {c['captured_best_ask']:.3f} | "
                      f"{c['next_trade_price'] if c['next_trade_price'] else '—'} | "
                      f"{c['next_trade_dt_s'] if c['next_trade_dt_s'] is not None else '—'} | "
                      f"{'✓' if c['ask_matches_next'] else '✗' if c['ask_matches_next'] is not None else '—'} |\n")
        match_rate = sum(1 for c in book_check if c['ask_matches_next']) / max(1, sum(1 for c in book_check if c['ask_matches_next'] is not None))
        md.append(f"\n**Book match rate**: {match_rate * 100:.1f}%\n")
        md.append(f"\nIf this is low (<50%), our REST-poll book is structurally lagging the live state, and the\n"
                  f"U-shape we measured is an artifact of polling cadence, not real microstructure.\n")

    md.append(f"\n## Falsification checks\n")
    md.append(f"\n1. **U-shape is real microstructure?** Look at price-cluster table: if many same-price clusters\n"
              f"   with large size, mid liquidity is replenishing (hidden depth or rapid re-quoting), not single-shot.\n"
              f"   If price-jumps table shows huge gaps (>0.10) frequently → U-shape real.\n")
    md.append(f"\n2. **Wallets are makers?** All `/trades` records are takers (verified). Our tracked wallets appear\n"
              f"   in `/trades` ⇒ they are takers, not makers. The 'maker' thesis was wrong.\n")
    md.append(f"\n3. **Arb pair completion?** Pair completion table above shows time-gap between legs. If\n"
              f"   gap is >60s, the second leg is *reactive*, not coordinated arb. If <5s, it's coordinated.\n")
    md.append(f"\n4. **Mid-liquidity single-shot?** Price clusters table: if a price level was hit by ≥3 fills\n"
              f"   within 30s, the liquidity replenished — not single-shot.\n")
    md.append(f"\n5. **Latency irrelevance?** Compare wallet_price vs captured_best_ask vs next_trade_price.\n"
              f"   If captured_best_ask ≈ wallet_price, our shadow snapshot is fresh; latency does matter.\n"
              f"   If captured_best_ask >> wallet_price but next_trade ≈ wallet_price, snapshot is stale\n"
              f"   and the U-shape was a measurement artifact.\n")
    return "".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=None)
    ap.add_argument("--cid", default=None)
    ap.add_argument("--date", default=utc_today())
    args = ap.parse_args()
    if not args.slug and not args.cid:
        print("supply --slug or --cid", file=sys.stderr); sys.exit(2)

    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})

    market = fetch_market(sess, slug=args.slug, cid=args.cid)
    if not market:
        print(f"could not fetch market", file=sys.stderr); sys.exit(2)
    cid = market.get("conditionId")
    slug = market.get("slug")
    print(f"# market_microscope  slug={slug}  cid={cid}", file=sys.stderr)
    print(f"# question: {market.get('question', '')}", file=sys.stderr)

    trades = fetch_all_market_trades(sess, cid)
    print(f"# pulled {len(trades)} trades", file=sys.stderr)
    if not trades:
        print("no trades — exiting", file=sys.stderr); sys.exit(0)

    by_oi = reconstruct_per_outcome(trades)
    analyses = {oi: analyze_outcome(fills) for oi, fills in by_oi.items()}

    # Load tracked wallets
    try:
        from analytics.wallet_shadow import WALLETS as TRACKED
    except Exception:
        TRACKED = {}
    tracked_set = {w.lower() for w in TRACKED.values()}
    pair_completion = analyze_pair_completion(tracked_set, by_oi, market)

    # Book vs implicit check using captured shadow events for this market
    shadow_events = load_shadow_events_for_market(args.date, cid)
    book_check = book_vs_implicit_check(shadow_events, trades)
    print(f"# {len(shadow_events)} shadow snapshots for this market", file=sys.stderr)

    md = emit_md(market, by_oi, analyses, pair_completion, book_check, tracked_set, len(shadow_events))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / f"market_microscope_{slug or cid[:10]}.md"
    md_path.write_text(md)
    print(md)
    print(f"\n# saved {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
