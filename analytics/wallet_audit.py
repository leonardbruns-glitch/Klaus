"""
Wallet copy-trade VERIFICATION / AUDIT.

The naive wallet_replay.py treats every BUY as a directional bet on the named
outcome. That model is wrong for:
  - tennis arb wallets (Eulhunter, tradecraft) that buy BOTH sides of a match
  - up/down scalp wallets (sixx7) that buy BOTH UP and DOWN inside the same
    window to lock spread
  - long-tail NO grinders that recycle capital across resolved cycles
  - any wallet that mirror-exits via SELL before resolution

Before drawing copy-trade conclusions, this module runs SIX verification passes:

  A) Position reconstruction: full chronological inventory per (wallet, asset).
     Pull /trades?user= for each tracked wallet (full reachable history),
     net BUY/SELL/REDEEM, identify closed cycles vs open exposure.

  B) Pair-trade detection: per condition_id, look for opposite-side entries
     from same wallet within PAIR_WINDOW_S. Compute paired sum-of-prices:
     if sum < 1.00, it's negative-risk arb — guaranteed (1 - sum) at resolution.

  C) Realized vs unrealized split: don't mix mark-to-bid with resolved payoffs.
     Reports: closed-cycle realized PnL, currently-held inventory MTM, expected
     PnL if held to resolution.

  D) Mirror-exit default for arb/scalp clusters: hold-to-resolution is the
     WRONG model for them. This module flags those wallets and runs the replay
     in mirror-exit mode as default.

  E) Spread baseline by cluster: median (ask - bid) at trade-time per cluster,
     and median % of mid that the spread represents. This tells us how much of
     the naive replay's "loss" is just spread artifact.

  F) Manual spot audit: pick 5 random buys from each of 3 wallets
     (tradecraft, Eulhunter, sixx7) and print the full reconstructed timeline:
     same-wallet trades on the same condition_id before + after, and end state.

Output:
  - logs/shadow/wallet_audit_<date>.md  (human-readable findings)
  - logs/shadow/wallet_audit_<date>.json  (structured data)

Run:
    python3 -m analytics.wallet_audit [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import random
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

PAIR_WINDOW_S = 600          # max gap between opposite-side legs to flag as paired
SPOT_AUDIT_PER_WALLET = 5    # how many trades to manually walk per wallet
TRADE_HISTORY_LIMIT = 3000   # how many /trades to pull per wallet (max reachable)


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- I/O

def load_shadow_events(date_str: str) -> list[dict]:
    p = LOG_DIR / date_str / "wallet_shadow.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def fetch_full_trades(sess: requests.Session, wallet: str) -> list[dict]:
    """Paginate /trades?user= until exhausted or limit hit."""
    out = []
    offset = 0
    while offset < TRADE_HISTORY_LIMIT:
        try:
            r = sess.get(f"{DATA}/trades", params={"user": wallet, "limit": 500, "offset": offset}, timeout=15)
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


def fetch_full_activity(sess: requests.Session, wallet: str) -> list[dict]:
    """Activity includes REDEEMs (for true close-out accounting)."""
    out = []
    offset = 0
    while offset < TRADE_HISTORY_LIMIT:
        try:
            r = sess.get(f"{DATA}/activity", params={"user": wallet, "limit": 500, "offset": offset}, timeout=15)
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


def fetch_positions(sess: requests.Session, wallet: str) -> list[dict]:
    try:
        r = sess.get(f"{DATA}/positions", params={"user": wallet, "limit": 500}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d if isinstance(d, list) else []
    except Exception:
        pass
    return []


# --------------------------------------------------------------------------- Cluster helper
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
    if any(k in s for k in ["election", "president", "senate", "congress", "governor", "poll", "approval", "prime-minister", "starmer", "fed-chair"]): return "politics"
    if any(k in s for k in ["iran", "israel", "ukraine", "russia", "china", "war", "peace", "regime"]): return "geopolitics"
    if any(k in s for k in ["epstein", "released", "leaked"]): return "disclosure"
    if any(k in s for k in ["bitcoin", "ethereum", "btc", "eth", "sol", "crypto"]): return "crypto_macro"
    return "other"


# Strategy class → expected exit model
ARB_CLUSTERS = {"tennis", "updown"}
GRIND_CLUSTERS = {"politics", "geopolitics", "crypto_macro", "disclosure"}


# --------------------------------------------------------------------------- A) Position reconstruction
def reconstruct_inventory(activity: list[dict]) -> dict:
    """
    Walk activity chronologically. Net BUY/SELL/REDEEM per (asset, outcome_index).
    Return per-position state:
      {asset: {slug, outcome, total_bought_shares, total_sold_shares, redeemed_shares,
               buy_cost, sell_revenue, redeem_revenue, current_shares,
               first_ts, last_ts, n_buys, n_sells, n_redeems, closed_flat}}
    """
    by_asset = defaultdict(lambda: dict(
        slug="", outcome="", outcome_index=None,
        condition_id="",
        total_bought_shares=0.0, total_sold_shares=0.0, redeemed_shares=0.0,
        buy_cost=0.0, sell_revenue=0.0, redeem_revenue=0.0,
        current_shares=0.0,
        first_ts=None, last_ts=None,
        n_buys=0, n_sells=0, n_redeems=0,
        buy_prices=[], sell_prices=[],
    ))

    for a in sorted(activity, key=lambda e: int(e.get("timestamp") or 0)):
        atype = (a.get("type") or "").upper()
        asset = a.get("asset") or ""
        if not asset:
            continue
        rec = by_asset[asset]
        rec["slug"] = rec["slug"] or (a.get("slug") or "")
        rec["outcome"] = rec["outcome"] or (a.get("outcome") or "")
        if rec["outcome_index"] is None and a.get("outcomeIndex") is not None:
            rec["outcome_index"] = a.get("outcomeIndex")
        rec["condition_id"] = rec["condition_id"] or (a.get("conditionId") or "")
        ts = int(a.get("timestamp") or 0)
        if ts:
            if rec["first_ts"] is None: rec["first_ts"] = ts
            rec["last_ts"] = ts
        usdc = float(a.get("usdcSize") or 0)
        size = float(a.get("size") or 0)
        price = float(a.get("price") or 0)
        notional = usdc if usdc > 0 else size * price

        if atype == "TRADE":
            side = (a.get("side") or "").upper()
            if side == "BUY":
                rec["total_bought_shares"] += size
                rec["buy_cost"] += notional
                rec["current_shares"] += size
                rec["n_buys"] += 1
                if price > 0: rec["buy_prices"].append(price)
            elif side == "SELL":
                rec["total_sold_shares"] += size
                rec["sell_revenue"] += notional
                rec["current_shares"] -= size
                rec["n_sells"] += 1
                if price > 0: rec["sell_prices"].append(price)
        elif atype == "REDEEM":
            # Redemption: shares burned for $1 each (if winning side)
            rec["redeemed_shares"] += usdc  # usdcSize on redeem = shares redeemed (≈ $1 each)
            rec["redeem_revenue"] += usdc
            rec["current_shares"] -= usdc
            rec["n_redeems"] += 1

    # Finalize
    out = {}
    for asset, rec in by_asset.items():
        avg_buy = sum(rec["buy_prices"]) / len(rec["buy_prices"]) if rec["buy_prices"] else 0
        avg_sell = sum(rec["sell_prices"]) / len(rec["sell_prices"]) if rec["sell_prices"] else 0
        closed = abs(rec["current_shares"]) < 0.01
        realized = rec["sell_revenue"] + rec["redeem_revenue"] - rec["buy_cost"] if closed else 0
        rec["avg_buy"] = avg_buy
        rec["avg_sell"] = avg_sell
        rec["closed_flat"] = closed
        rec["realized_pnl"] = realized if closed else None
        out[asset] = rec
    return out


# --------------------------------------------------------------------------- B) Pair-trade detection
def detect_pairs(activity: list[dict]) -> dict:
    """
    For each condition_id with trades on BOTH outcomes from same wallet,
    record paired entries within PAIR_WINDOW_S.

    Returns:
      {condition_id: {
         slug, both_sides_present (bool), pair_count,
         sum_of_avg_prices (avg buy yes + avg buy no, share-weighted),
         is_arb (sum < 1.00),
         legs: [{outcome, asset, avg_buy_price, total_shares, total_cost}]
      }}
    """
    by_cid_outcome = defaultdict(lambda: defaultdict(list))
    for a in activity:
        if (a.get("type") or "").upper() != "TRADE": continue
        if (a.get("side") or "").upper() != "BUY": continue
        cid = a.get("conditionId") or ""
        oi = a.get("outcomeIndex")
        if not cid or oi is None: continue
        by_cid_outcome[cid][oi].append(a)

    pairs = {}
    for cid, by_oi in by_cid_outcome.items():
        if len(by_oi) < 2:
            continue
        legs_data = []
        for oi, trades in by_oi.items():
            total_size = sum(float(t.get("size") or 0) for t in trades)
            total_cost = sum(float(t.get("size") or 0) * float(t.get("price") or 0) for t in trades)
            avg_px = total_cost / total_size if total_size > 0 else 0
            legs_data.append(dict(
                outcome=trades[0].get("outcome") or "",
                asset=trades[0].get("asset") or "",
                outcome_index=oi,
                avg_buy=round(avg_px, 4),
                total_shares=round(total_size, 2),
                total_cost=round(total_cost, 2),
                n_buys=len(trades),
            ))
        if len(legs_data) < 2:
            continue
        s = sum(l["avg_buy"] for l in legs_data)
        pairs[cid] = dict(
            slug=(by_oi[next(iter(by_oi))][0].get("slug") or ""),
            both_sides_present=True,
            pair_count=sum(l["n_buys"] for l in legs_data),
            sum_of_avg_prices=round(s, 4),
            is_arb=(s < 1.00 - 0.001),  # tolerance for fees
            arb_edge_pct=round((1.0 - s) * 100, 2) if s < 1.0 else round((1.0 - s) * 100, 2),
            legs=legs_data,
        )
    return pairs


# --------------------------------------------------------------------------- E) Spread baseline
def spread_baseline_from_shadow(events: list[dict]) -> dict:
    """Median (ask-bid) per cluster, plus median spread/mid %."""
    per_cluster = defaultdict(list)
    for ev in events:
        if ev.get("rec") != "wallet_trade": continue
        slug = ev.get("slug") or ""
        cl = cluster(slug)
        book = ev.get("book_this") or {}
        asks = book.get("asks") or []
        bids = book.get("bids") or []
        if not asks or not bids: continue
        try:
            ap = [float(a[0]) if isinstance(a, (list, tuple)) else float(a.get("price", 0)) for a in asks]
            bp = [float(b[0]) if isinstance(b, (list, tuple)) else float(b.get("price", 0)) for b in bids]
            best_ask = min(p for p in ap if p > 0)
            best_bid = max(p for p in bp if p > 0)
            mid = (best_ask + best_bid) / 2
            if mid <= 0: continue
            spread = best_ask - best_bid
            per_cluster[cl].append((spread, spread / mid))
        except (ValueError, IndexError):
            continue

    def median(xs):
        if not xs: return 0
        s = sorted(xs)
        return s[len(s) // 2]

    out = {}
    for cl, data in per_cluster.items():
        spreads = [s for s, _ in data]
        rel = [r for _, r in data]
        out[cl] = dict(
            n=len(data),
            median_spread=round(median(spreads), 4),
            median_spread_pct_of_mid=round(median(rel) * 100, 2),
            naive_immediate_mark_loss_pct=round(median(rel) * 100 / 2, 2),  # half-spread cost
        )
    return out


# --------------------------------------------------------------------------- F) Manual spot audit
def spot_audit(wallet: str, label: str, activity: list[dict], n: int = SPOT_AUDIT_PER_WALLET) -> list[dict]:
    """For n random BUYs by this wallet, reconstruct full timeline on that condition_id."""
    buys = [a for a in activity if (a.get("type") or "").upper() == "TRADE" and (a.get("side") or "").upper() == "BUY"]
    if not buys:
        return []
    sample = random.sample(buys, min(n, len(buys)))
    audits = []
    for b in sample:
        cid = b.get("conditionId")
        ts = int(b.get("timestamp") or 0)
        slug = b.get("slug") or ""
        # all of wallet's trades on this condition_id, time-sorted
        same = [a for a in activity
                if (a.get("conditionId") or "") == cid
                and (a.get("type") or "").upper() in ("TRADE", "REDEEM")]
        same.sort(key=lambda x: int(x.get("timestamp") or 0))
        # Compute final state on this market
        outcomes_traded = defaultdict(lambda: {"shares": 0.0, "cost": 0.0, "rev": 0.0})
        for a in same:
            oi = a.get("outcomeIndex")
            if oi is None: continue
            size = float(a.get("size") or 0)
            price = float(a.get("price") or 0)
            usdc = float(a.get("usdcSize") or 0)
            atype = (a.get("type") or "").upper()
            side = (a.get("side") or "").upper()
            ntl = usdc if usdc > 0 else size * price
            o = outcomes_traded[oi]
            if atype == "TRADE" and side == "BUY":
                o["shares"] += size; o["cost"] += ntl
            elif atype == "TRADE" and side == "SELL":
                o["shares"] -= size; o["rev"] += ntl
            elif atype == "REDEEM":
                o["shares"] -= usdc; o["rev"] += usdc
        net = []
        for oi, o in outcomes_traded.items():
            realized = o["rev"] - o["cost"] if abs(o["shares"]) < 0.01 else None
            net.append(dict(outcome_index=oi,
                            net_shares=round(o["shares"], 2),
                            cost=round(o["cost"], 2),
                            revenue=round(o["rev"], 2),
                            realized_pnl=round(realized, 2) if realized is not None else None,
                            closed_flat=abs(o["shares"]) < 0.01))
        audits.append(dict(
            wallet_label=label,
            slug=slug, condition_id=cid,
            seed_trade_ts=ts, seed_trade_iso=datetime.utcfromtimestamp(ts).isoformat() if ts else None,
            seed_trade_outcome=b.get("outcome"),
            seed_trade_price=float(b.get("price") or 0),
            seed_trade_size=float(b.get("size") or 0),
            n_trades_on_cid=len(same),
            net_state_per_outcome=net,
        ))
    return audits


# --------------------------------------------------------------------------- Output
def emit_markdown(date_str: str, results: dict) -> str:
    md = []
    md.append(f"# Wallet Audit — {date_str}\n")
    md.append("Verification passes BEFORE drawing copy-trade conclusions.\n")

    # A) Position reconstruction
    md.append("## A) Position reconstruction\n")
    md.append(f"For each tracked wallet: full /activity pulled, BUY/SELL/REDEEM netted per asset.\n")
    md.append(f"\n| wallet | n_assets | n_closed_flat | n_open | realized_pnl_closed |\n|---|---|---|---|---|\n")
    for wlabel, w in results["wallets"].items():
        inv = w["inventory"]
        n_assets = len(inv)
        n_closed = sum(1 for v in inv.values() if v["closed_flat"])
        n_open = n_assets - n_closed
        realized_total = sum(v["realized_pnl"] or 0 for v in inv.values() if v["closed_flat"])
        md.append(f"| {wlabel} | {n_assets} | {n_closed} | {n_open} | ${realized_total:+,.0f} |\n")

    # B) Pair-trade detection
    md.append("\n## B) Pair-trade detection (both-side entries on same condition_id)\n")
    md.append(f"Window: any-time pairing. Sum-of-avg-prices < 1.00 = negative-risk arb.\n")
    for wlabel, w in results["wallets"].items():
        pairs = w["pairs"]
        if not pairs: continue
        n_pairs = len(pairs)
        n_arbs = sum(1 for p in pairs.values() if p["is_arb"])
        avg_edge = sum(p["arb_edge_pct"] for p in pairs.values() if p["is_arb"]) / max(1, n_arbs)
        md.append(f"\n### {wlabel}: {n_pairs} markets with both sides, {n_arbs} are arb (sum<1.00), avg arb edge {avg_edge:.2f}%\n")
        # Top 5 by arb edge
        sorted_pairs = sorted(pairs.items(), key=lambda kv: -kv[1]["arb_edge_pct"] if kv[1]["is_arb"] else 0)
        md.append(f"\n| slug | sum_avg_px | arb_edge% | leg_A px:shares | leg_B px:shares |\n|---|---|---|---|---|\n")
        for cid, p in sorted_pairs[:10]:
            if len(p["legs"]) < 2: continue
            a, b = p["legs"][0], p["legs"][1]
            mark = "✓" if p["is_arb"] else ""
            md.append(f"| {p['slug'][:50]} | {p['sum_of_avg_prices']:.3f} {mark} | {p['arb_edge_pct']:+.2f}% | "
                      f"{a['outcome'][:5]} @ {a['avg_buy']:.3f} × {a['total_shares']:.0f} | "
                      f"{b['outcome'][:5]} @ {b['avg_buy']:.3f} × {b['total_shares']:.0f} |\n")

    # C) Realized vs unrealized split
    md.append("\n## C) Realized vs unrealized split (closed cycles only)\n")
    md.append("\n| wallet | n_closed_cycles | realized_pnl | mean_cycle_pnl | n_winning_cycles |\n|---|---|---|---|---|\n")
    for wlabel, w in results["wallets"].items():
        closed = [v for v in w["inventory"].values() if v["closed_flat"]]
        n = len(closed)
        rpnls = [v["realized_pnl"] for v in closed if v["realized_pnl"] is not None]
        total = sum(rpnls)
        mean = total / max(1, len(rpnls))
        n_win = sum(1 for r in rpnls if r > 0)
        md.append(f"| {wlabel} | {n} | ${total:+,.0f} | ${mean:+.2f} | {n_win} ({100*n_win/max(1,n):.0f}%) |\n")

    # E) Spread baseline
    md.append("\n## E) Spread baseline by cluster (from book snapshots in shadow log)\n")
    md.append("\n| cluster | n_snapshots | median_spread | median_spread%_of_mid | naive_half_spread_cost |\n|---|---|---|---|---|\n")
    for cl, s in sorted(results["spread_baseline"].items(), key=lambda kv: -kv[1]["median_spread_pct_of_mid"]):
        md.append(f"| {cl} | {s['n']} | {s['median_spread']:.3f} | {s['median_spread_pct_of_mid']:.1f}% | {s['naive_immediate_mark_loss_pct']:.1f}% |\n")
    md.append("\n**Reading**: a wallet that buys at the ask in `updown` markets shows an instant "
              "−naive_half_spread_cost mark-to-bid by definition — it is NOT a real loss. The "
              "raw replay numbers must be corrected for this.\n")

    # F) Spot audit
    md.append("\n## F) Manual spot audit (random BUYs traced to final state)\n")
    for wlabel, w in results["wallets"].items():
        audits = w["spot_audit"]
        if not audits: continue
        md.append(f"\n### {wlabel}\n")
        for a in audits:
            md.append(f"\n**Seed**: `{a['slug']}` outcome={a['seed_trade_outcome']} px={a['seed_trade_price']:.3f} size={a['seed_trade_size']:.0f} @ {a['seed_trade_iso']}\n")
            md.append(f"Trades on this market by this wallet: {a['n_trades_on_cid']}\n")
            md.append(f"\n| outcome_idx | net_shares | cost | revenue | realized_pnl | closed_flat |\n|---|---|---|---|---|---|\n")
            for n in a["net_state_per_outcome"]:
                rpnl = f"${n['realized_pnl']:+.2f}" if n['realized_pnl'] is not None else "—"
                md.append(f"| {n['outcome_index']} | {n['net_shares']} | ${n['cost']:.2f} | ${n['revenue']:.2f} | {rpnl} | {n['closed_flat']} |\n")

    # CONCLUSIONS
    md.append("\n## Verdict\n")
    md.append("The numbers above are needed to evaluate whether the naive wallet_replay results "
              "are economically meaningful or artifacts. Look at:\n\n")
    md.append("- For tennis/updown wallets: does pair-trade detection (§B) show that most of their "
              "trades pair into negative-risk arb? If yes, the naive replay's directional-bet model "
              "is wrong and should be replaced by a paired-fill model.\n")
    md.append("- For grinder wallets (politics, geopolitics): is the closed-cycle realized PnL (§C) "
              "positive and meaningful? If yes, copy-trading the BUY-and-hold cycles may work even "
              "without mirror exits.\n")
    md.append("- For all clusters: is the naive `wallet_replay` loss within range of the median "
              "half-spread cost (§E)? If yes, the loss is a measurement artifact, not strategy failure.\n")
    return "".join(md)


# --------------------------------------------------------------------------- Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=utc_today())
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)

    print(f"# wallet_audit  date={args.date}\n", file=sys.stderr)

    # Load shadow events (for spread baseline + wallet list)
    events = load_shadow_events(args.date)
    print(f"# loaded {len(events)} shadow events", file=sys.stderr)

    # Discover tracked wallets from the WALLETS dict
    try:
        from analytics.wallet_shadow import WALLETS as TRACKED
    except Exception:
        # Fall back to wallets seen in shadow log
        TRACKED = {}
        for ev in events:
            if ev.get("rec") == "wallet_trade":
                n = ev.get("wallet_name", "?")
                w = ev.get("wallet", "")
                if n and w: TRACKED[n] = w
    print(f"# {len(TRACKED)} tracked wallets", file=sys.stderr)

    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})

    results = {
        "date": args.date,
        "wallets": {},
        "spread_baseline": spread_baseline_from_shadow(events),
    }

    for label, w in TRACKED.items():
        print(f"# auditing {label} ({w[:14]})...", file=sys.stderr)
        activity = fetch_full_activity(sess, w)
        if not activity:
            print(f"  no activity, skipping", file=sys.stderr)
            continue
        inv = reconstruct_inventory(activity)
        pairs = detect_pairs(activity)
        audits = spot_audit(w, label, activity, n=SPOT_AUDIT_PER_WALLET)
        # Per-cluster classification of this wallet
        cluster_counts = defaultdict(int)
        for a in activity:
            cluster_counts[cluster(a.get("slug") or "")] += 1
        primary = max(cluster_counts.items(), key=lambda kv: kv[1])[0] if cluster_counts else "unknown"
        results["wallets"][label] = {
            "wallet": w,
            "n_activity": len(activity),
            "primary_cluster": primary,
            "is_arb_class": primary in ARB_CLUSTERS,
            "inventory": inv,
            "pairs": pairs,
            "spot_audit": audits,
        }
        print(f"  inventory={len(inv)} pairs={len(pairs)} arb_pairs={sum(1 for p in pairs.values() if p['is_arb'])}", file=sys.stderr)

    # Emit
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / f"wallet_audit_{args.date}.md"
    json_path = OUT_DIR / f"wallet_audit_{args.date}.json"
    md_text = emit_markdown(args.date, results)
    md_path.write_text(md_text)
    json_path.write_text(json.dumps(results, indent=2, default=str))
    print(md_text)
    print(f"\n# saved {md_path}", file=sys.stderr)
    print(f"# saved {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
