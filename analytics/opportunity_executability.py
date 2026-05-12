"""
Opportunity executability — would a follower have actually filled?

Uses ACTUAL SUBSEQUENT PRINTS (not synthetic books) to measure whether
liquidity was available to later takers at the same-or-better price after
each tracked-wallet fill.

Critical answers:
  A) Pair-window reconstruction — when did sum<1 first appear, when did it
     close, peak edge over window.
  B) Counterfactual fill availability — for each wallet fill, how much volume
     traded at same-or-better price in subsequent {1,3,5,10,30,60,300}s windows.
  C) Realized-edge decomposition — gross arb - fees - slippage from wallet's
     price.
  D) Hedge-delay risk — interim MTM exposure of leg A while waiting for leg B.
  E) Capacity at each lag — cumulative shares fillable, slippage curve.

Tier classification output:
  Tier 0 (REST viable) — opportunity persists ≥60s with significant capacity
  Tier 1 (Standard WS viable) — opportunity persists 1-30s
  Tier 2 (Low-latency WS) — opportunity dies <1s (we cannot measure this from
                            REST data — flagged as unmeasurable)
  Tier 3 (Queue/MM) — only the wallet got the size; later takers got worse fills

Inputs:
  - Shadow log: logs/shadow/hot/<date>/wallet_shadow.jsonl
  - /trades?market=<cid> for each unique market in shadow log

Outputs:
  - logs/shadow/executability_<date>.md
  - logs/shadow/executability_<date>.json

CRITICAL CAVEAT documented inline: REST timestamps are integer-second resolution.
Sub-second analysis impossible from public API; WS would be needed.

Run:
    python3 -m analytics.opportunity_executability [--date YYYY-MM-DD]
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

LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
OUT_DIR = Path("/root/Klaus/logs/shadow")
DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

# REST gives integer-second timestamps; finer resolution is impossible.
LAG_BUCKETS_S = [0, 1, 2, 3, 5, 10, 30, 60, 300]
PAIR_WINDOW_LOOKBACK_S = 7200   # how far back to scan for sum<1 windows
FEE_BPS = 200                   # 2% taker each leg


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cluster(slug: str) -> str:
    s = (slug or "").lower()
    if "updown" in s: return "updown"
    if any(k in s for k in ["atp-", "wta-", "tennis"]): return "tennis"
    if any(k in s for k in ["lol-", "cs2-", "esport"]): return "esports"
    if any(k in s for k in ["election", "president", "starmer", "trump", "congress", "poll", "approval"]): return "politics"
    if any(k in s for k in ["iran", "israel", "ukraine", "russia", "china", "war", "peace", "regime"]): return "geopolitics"
    if any(k in s for k in ["bitcoin", "ethereum", "btc", "eth", "sol", "crypto"]): return "crypto_macro"
    if any(k in s for k in ["fifa", "nba", "nfl", "mlb", "nhl", "soccer", "tennis"]): return "sport_other"
    return "other"


def load_shadow_buys(date_str: str) -> list[dict]:
    p = LOG_DIR / date_str / "wallet_shadow.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("rec") != "wallet_trade": continue
            if (ev.get("side") or "").upper() != "BUY": continue
            out.append(ev)
    return out


def fetch_all_market_trades(sess, cid: str, max_pages: int = 40) -> list[dict]:
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
            time.sleep(0.05)
        except Exception:
            break
    return out


# --------------------------------------------------------------------------- B: counterfactual fills
def counterfactual_fill_capacity(wallet_fill: dict, market_trades: list[dict]) -> dict:
    """
    For a BUY at price P on asset A at time T:
      For each lag bucket Δ:
        Look at trades on asset A between T (exclusive) and T+Δ (inclusive)
        with side=BUY and price <= P + 1¢ (tolerance for tick noise).
        Sum size = total subsequent capacity at same-or-better price.
        Best price after = cheapest subsequent BUY on the same asset.
    """
    ts = int(wallet_fill.get("ts", 0) or 0)
    asset = wallet_fill.get("asset", "")
    wp = float(wallet_fill.get("price", 0) or 0)
    if not (ts and asset and wp > 0):
        return {}
    # Filter to same asset, after T
    follow = [t for t in market_trades
              if t.get("asset") == asset
              and int(t.get("timestamp", 0) or 0) > ts
              and (t.get("side") or "").upper() == "BUY"]
    follow.sort(key=lambda t: int(t.get("timestamp", 0) or 0))
    out = {}
    for lag in LAG_BUCKETS_S:
        cutoff = ts + lag
        window = [t for t in follow if int(t.get("timestamp", 0) or 0) <= cutoff]
        if not window:
            out[lag] = dict(n_fills=0, size_at_or_below=0.0, best_price=None, n_unique_takers=0, n_size_at_wp=0)
            continue
        at_or_below = [t for t in window if float(t.get("price", 0) or 0) <= wp + 0.011]
        size_at = sum(float(t.get("size", 0) or 0) for t in at_or_below)
        best_after = min((float(t.get("price", 0) or 0) for t in window), default=None)
        n_takers = len({t.get("proxyWallet", "") for t in at_or_below})
        out[lag] = dict(
            n_fills=len(at_or_below),
            size_at_or_below=round(size_at, 2),
            best_price=round(best_after, 4) if best_after is not None else None,
            n_unique_takers=n_takers,
            n_size_at_wp=sum(1 for t in at_or_below if abs(float(t.get("price", 0) or 0) - wp) < 0.005),
        )
    return out


def half_life_seconds(buckets: dict, max_lag: int = 300) -> Optional[int]:
    """Approx: smallest lag where size_at_or_below(lag) >= 0.5 * size_at_or_below(max_lag)."""
    total = buckets.get(max_lag, {}).get("size_at_or_below", 0)
    if total <= 0:
        return None
    target = total * 0.5
    for lag in LAG_BUCKETS_S:
        if buckets.get(lag, {}).get("size_at_or_below", 0) >= target:
            return lag
    return None


# --------------------------------------------------------------------------- A: pair-window duration
def find_pair_windows(market_trades: list[dict]) -> list[dict]:
    """
    Sweep trades chronologically. Track best (lowest) BUY price seen on each outcome
    using actual prints as proxy for available asks. Detect intervals when
    sum_min_buy_yes + sum_min_buy_no < 1.00.
    """
    by_oi = defaultdict(list)
    for t in market_trades:
        oi = t.get("outcomeIndex")
        if oi is None: continue
        if (t.get("side") or "").upper() != "BUY": continue
        by_oi[oi].append((int(t.get("timestamp", 0) or 0), float(t.get("price", 0) or 0), float(t.get("size", 0) or 0)))
    for oi in by_oi:
        by_oi[oi].sort()
    if len(by_oi) < 2:
        return []
    # Walk a unified timeline. For each second, what was the most-recent BUY price on each outcome?
    all_ts = sorted({ts for fills in by_oi.values() for ts, _, _ in fills})
    if not all_ts:
        return []
    windows = []
    open_w = None
    last_price = {oi: None for oi in by_oi}
    # Iterate every event ts; for each oi, recompute the most recent BUY price ≤ this ts
    indices = {oi: 0 for oi in by_oi}
    for ts in all_ts:
        for oi, fills in by_oi.items():
            while indices[oi] < len(fills) and fills[indices[oi]][0] <= ts:
                last_price[oi] = fills[indices[oi]][1]
                indices[oi] += 1
        prices = [p for p in last_price.values() if p is not None]
        if len(prices) < 2: continue
        s = sum(prices)
        is_arb = s < 1.0
        if is_arb and open_w is None:
            open_w = dict(start_ts=ts, peak_edge=1.0 - s)
        elif is_arb and open_w is not None:
            open_w["peak_edge"] = max(open_w["peak_edge"], 1.0 - s)
        elif (not is_arb) and open_w is not None:
            open_w["end_ts"] = ts
            open_w["duration_s"] = ts - open_w["start_ts"]
            windows.append(open_w)
            open_w = None
    if open_w is not None:
        last_ts = max(all_ts)
        open_w["end_ts"] = last_ts
        open_w["duration_s"] = last_ts - open_w["start_ts"]
        windows.append(open_w)
    return windows


# --------------------------------------------------------------------------- D: hedge-delay risk
def hedge_delay_exposure(wallet_fills_on_market: list[dict], market_trades: list[dict]) -> dict:
    """
    For wallet's two-leg trades on this market: between first leg-A fill and
    first leg-B fill, what was the worst MTM on leg-A?

    Estimate MTM at each second using the most recent trade price on the SAME
    outcome as leg-A.
    """
    # Group wallet trades by outcome
    by_oi = defaultdict(list)
    for f in wallet_fills_on_market:
        oi = f.get("outcome_index") if "outcome_index" in f else f.get("outcomeIndex")
        if oi is None: continue
        by_oi[oi].append(f)
    if len(by_oi) < 2:
        return {}
    # leg A = first by ts; leg B = second
    firsts = [(oi, min(int(f.get("ts", 0) or 0) for f in fills)) for oi, fills in by_oi.items()]
    firsts.sort(key=lambda x: x[1])
    leg_a_oi, leg_a_ts = firsts[0]
    leg_b_oi, leg_b_ts = firsts[1]
    leg_a_fill = min(by_oi[leg_a_oi], key=lambda f: int(f.get("ts", 0) or 0))
    leg_a_price = float(leg_a_fill.get("price", 0) or 0)
    leg_a_size = float(leg_a_fill.get("size", 0) or 0)
    # Find all trades on leg_a's asset between leg_a_ts and leg_b_ts
    leg_a_asset = leg_a_fill.get("asset", "")
    interim = [t for t in market_trades
               if t.get("asset") == leg_a_asset
               and leg_a_ts < int(t.get("timestamp", 0) or 0) < leg_b_ts]
    if not interim:
        return dict(leg_a_ts=leg_a_ts, leg_b_ts=leg_b_ts, gap_s=leg_b_ts - leg_a_ts,
                    leg_a_price=leg_a_price, worst_mtm_loss_pct=0.0, n_interim_trades=0)
    interim_prices = [float(t.get("price", 0) or 0) for t in interim]
    worst_price = min(interim_prices)
    worst_loss = (worst_price - leg_a_price) / leg_a_price if leg_a_price > 0 else 0
    return dict(
        leg_a_ts=leg_a_ts,
        leg_b_ts=leg_b_ts,
        gap_s=leg_b_ts - leg_a_ts,
        leg_a_price=leg_a_price,
        leg_a_size=leg_a_size,
        worst_interim_price=round(worst_price, 4),
        worst_mtm_loss_pct=round(worst_loss * 100, 2),
        n_interim_trades=len(interim),
    )


# --------------------------------------------------------------------------- Tier classification
def tier_from_half_life(half_life_s: Optional[int], capacity_at_5s: float) -> str:
    if half_life_s is None or capacity_at_5s == 0:
        return "Tier_3_queue_only"  # no follow-on volume
    if half_life_s >= 60:
        return "Tier_0_REST_viable"
    if half_life_s >= 5:
        return "Tier_1_standard_WS"
    if half_life_s >= 1:
        return "Tier_2_low_latency_WS"
    return "Tier_2_low_latency_WS"


# --------------------------------------------------------------------------- Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=utc_today())
    args = ap.parse_args()
    print(f"# opportunity_executability  date={args.date}", file=sys.stderr)

    shadow_buys = load_shadow_buys(args.date)
    print(f"# loaded {len(shadow_buys)} BUY events from shadow log", file=sys.stderr)
    if not shadow_buys:
        return

    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})

    # Group by condition_id
    by_cid = defaultdict(list)
    for ev in shadow_buys:
        cid = ev.get("condition_id")
        if cid: by_cid[cid].append(ev)
    print(f"# {len(by_cid)} unique markets", file=sys.stderr)

    per_wallet_capacity = defaultdict(lambda: defaultdict(list))   # wallet -> lag -> list[size]
    per_cluster_capacity = defaultdict(lambda: defaultdict(list))  # cluster -> lag -> list[size]
    per_wallet_halflife = defaultdict(list)
    per_cluster_halflife = defaultdict(list)
    per_wallet_tiers = defaultdict(lambda: defaultdict(int))
    fill_records = []
    pair_windows_all = []
    hedge_records = []

    for i, (cid, fills) in enumerate(by_cid.items()):
        if (i + 1) % 5 == 0:
            print(f"# market {i+1}/{len(by_cid)}...", file=sys.stderr)
        trades = fetch_all_market_trades(sess, cid)
        if not trades: continue
        # B: counterfactual capacity per fill
        for ev in fills:
            wname = ev.get("wallet_name", "?")
            slug = ev.get("slug") or ""
            cl = cluster(slug)
            buckets = counterfactual_fill_capacity(ev, trades)
            if not buckets: continue
            hl = half_life_seconds(buckets, max_lag=300)
            cap5 = buckets.get(5, {}).get("size_at_or_below", 0)
            tier = tier_from_half_life(hl, cap5)
            per_wallet_tiers[wname][tier] += 1
            per_wallet_halflife[wname].append(hl if hl is not None else 999)
            per_cluster_halflife[cl].append(hl if hl is not None else 999)
            for lag in LAG_BUCKETS_S:
                size = buckets.get(lag, {}).get("size_at_or_below", 0)
                per_wallet_capacity[wname][lag].append(size)
                per_cluster_capacity[cl][lag].append(size)
            fill_records.append(dict(
                wallet=wname, cluster=cl, ts=int(ev.get("ts", 0) or 0),
                price=float(ev.get("price", 0) or 0),
                slug=slug,
                capacity_by_lag={str(k): v["size_at_or_below"] for k, v in buckets.items()},
                half_life_s=hl,
                tier=tier,
            ))
        # A: pair windows for this market
        windows = find_pair_windows(trades)
        if windows:
            for w in windows:
                pair_windows_all.append({**w, "slug": fills[0].get("slug") if fills else "?",
                                         "cluster": cluster(fills[0].get("slug") if fills else "")})
        # D: hedge-delay exposure for each tracked wallet on this market
        by_wallet = defaultdict(list)
        for f in fills:
            by_wallet[f.get("wallet_name", "?")].append(f)
        for wname, w_fills in by_wallet.items():
            # Add outcome_index from shadow log if present
            for f in w_fills:
                if "outcome_index" not in f:
                    f["outcome_index"] = f.get("outcomeIndex") if "outcomeIndex" in f else None
                    if f["outcome_index"] is None and "outcome" in f:
                        # cannot resolve without market metadata; skip
                        pass
            exp = hedge_delay_exposure(w_fills, trades)
            if exp:
                exp["wallet"] = wname
                exp["slug"] = w_fills[0].get("slug") if w_fills else "?"
                hedge_records.append(exp)

    # ------ AGGREGATE OUTPUT ------
    def percentile(xs, p):
        if not xs: return 0
        s = sorted(xs)
        return s[min(len(s) - 1, int(len(s) * p))]

    md = []
    md.append(f"# Opportunity Executability — {args.date}\n")
    md.append(f"\n**Caveat**: `/trades` returns integer-second timestamps. Sub-second analysis "
              f"is impossible from REST API; flagged below where relevant.\n")

    # Per-cluster summary
    md.append("\n## B) Counterfactual fill capacity by cluster\n")
    md.append("\nFor each tracked-wallet fill, sum of shares traded at the same-or-better price "
              "in subsequent windows. Higher = more liquidity remained for late takers.\n")
    md.append("\n| cluster | n_fills | half-life median | cap_1s | cap_3s | cap_5s | cap_10s | cap_30s | cap_60s | cap_300s |\n|---|---|---|---|---|---|---|---|---|---|\n")
    for cl, lag_dict in sorted(per_cluster_capacity.items()):
        n = len(lag_dict[0])
        hls = [h for h in per_cluster_halflife[cl] if h != 999]
        hl_med = percentile(hls, 0.5) if hls else "—"
        row = [cl, n, hl_med]
        for lag in [1, 3, 5, 10, 30, 60, 300]:
            sizes = lag_dict.get(lag, [])
            med = percentile(sizes, 0.5)
            row.append(f"{med:,.0f}")
        md.append("| " + " | ".join(str(x) for x in row) + " |\n")

    # Tier distribution per wallet
    md.append("\n## Tier classification per wallet\n")
    md.append("\nTier 0: half-life ≥60s — REST polling viable\n")
    md.append("Tier 1: half-life 5-60s — standard WS viable\n")
    md.append("Tier 2: half-life <5s — low-latency required (NOTE: cannot resolve sub-second from REST)\n")
    md.append("Tier 3: no follow-on volume at price — queue/MM only\n")
    md.append("\n| wallet | n_fills | Tier_0 | Tier_1 | Tier_2 | Tier_3 |\n|---|---|---|---|---|---|\n")
    for w in sorted(per_wallet_tiers.keys()):
        tiers = per_wallet_tiers[w]
        n = sum(tiers.values())
        t0 = tiers.get("Tier_0_REST_viable", 0)
        t1 = tiers.get("Tier_1_standard_WS", 0)
        t2 = tiers.get("Tier_2_low_latency_WS", 0)
        t3 = tiers.get("Tier_3_queue_only", 0)
        md.append(f"| {w} | {n} | {t0} ({100 * t0 / max(1, n):.0f}%) | {t1} ({100 * t1 / max(1, n):.0f}%) | "
                  f"{t2} ({100 * t2 / max(1, n):.0f}%) | {t3} ({100 * t3 / max(1, n):.0f}%) |\n")

    # A: pair windows
    md.append("\n## A) Pair-window reconstruction\n")
    md.append(f"\nIntervals where sum_min_buy_yes + sum_min_buy_no < 1.00 (using actual trade prints):\n")
    if pair_windows_all:
        durs = [w["duration_s"] for w in pair_windows_all]
        edges = [w["peak_edge"] * 100 for w in pair_windows_all]
        md.append(f"\n| metric | value |\n|---|---|\n")
        md.append(f"| n_windows_detected | {len(pair_windows_all)} |\n")
        md.append(f"| median duration (s) | {percentile(durs, 0.5)} |\n")
        md.append(f"| p95 duration (s) | {percentile(durs, 0.95)} |\n")
        md.append(f"| max duration (s) | {max(durs)} |\n")
        md.append(f"| median peak edge | {percentile(edges, 0.5):.2f}% |\n")
        md.append(f"| max peak edge | {max(edges):.2f}% |\n")
        # Top 10 windows
        md.append(f"\nTop 10 windows by duration:\n\n| slug | cluster | duration_s | peak_edge% |\n|---|---|---|---|\n")
        pair_windows_all.sort(key=lambda w: -w["duration_s"])
        for w in pair_windows_all[:10]:
            md.append(f"| {w.get('slug','')[:50]} | {w.get('cluster','')} | {w['duration_s']} | {w['peak_edge']*100:.2f}% |\n")
    else:
        md.append("\nNo pair windows detected (sum < 1.00 never persisted across both outcomes' last-trade prices).\n")

    # D: hedge-delay risk
    md.append("\n## D) Hedge-delay risk — interim MTM exposure on leg A while waiting for leg B\n")
    if hedge_records:
        gaps = [h["gap_s"] for h in hedge_records]
        losses = [h["worst_mtm_loss_pct"] for h in hedge_records]
        md.append(f"\n| metric | value |\n|---|---|\n")
        md.append(f"| n_pairs | {len(hedge_records)} |\n")
        md.append(f"| median gap_s | {percentile(gaps, 0.5)} |\n")
        md.append(f"| p95 gap_s | {percentile(gaps, 0.95)} |\n")
        md.append(f"| median worst MTM loss | {percentile(losses, 0.5):.2f}% |\n")
        md.append(f"| p95 worst MTM loss | {percentile(losses, 0.95):.2f}% |\n")
        md.append(f"\nTop 10 by worst MTM loss:\n\n| wallet | slug | gap_s | leg_a_px | worst_px | loss% |\n|---|---|---|---|---|---|\n")
        hedge_records.sort(key=lambda h: h["worst_mtm_loss_pct"])
        for h in hedge_records[:10]:
            md.append(f"| {h.get('wallet')} | {h.get('slug','')[:35]} | {h['gap_s']} | "
                      f"{h['leg_a_price']:.3f} | {h.get('worst_interim_price', '—')} | {h['worst_mtm_loss_pct']:+.2f}% |\n")
    else:
        md.append("\nNo two-leg pairs found in shadow window.\n")

    # C: edge decomposition
    md.append("\n## C) Realized-edge decomposition (rough — pair-window based)\n")
    if pair_windows_all:
        gross_med = percentile([w["peak_edge"] * 100 for w in pair_windows_all], 0.5)
        # 2-leg taker fee = 4% of stake, but more precisely ~2% × 2 of cost.
        # Net edge if we filled both legs at the SUM=peak_edge prices.
        fee_drag = (FEE_BPS / 10000.0) * 2 * 100
        md.append(f"\n| component | value |\n|---|---|\n")
        md.append(f"| median gross arb (peak_edge) | {gross_med:.2f}% |\n")
        md.append(f"| 2-leg taker fee drag | -{fee_drag:.2f}% |\n")
        md.append(f"| net (ignore slippage) | {gross_med - fee_drag:.2f}% |\n")
        md.append(f"| slippage if we paid 1 tick worse than implied | -1% to -3% |\n")
        md.append(f"| net realistic | {gross_med - fee_drag - 2:.2f}% |\n")
        md.append(f"\n**Caveat**: peak_edge uses minimum BUY prints as proxy for asks; real asks may be higher.\n")

    # Final verdict
    md.append("\n## Verdict — what infra capability boundary matters\n")
    md.append("\nReading the tier distribution above:\n")
    md.append("- If most fills are **Tier 0**: REST polling improvements (5s→1s cadence) would unlock the strategy. No WS pivot needed.\n")
    md.append("- If most fills are **Tier 1**: standard WebSocket (our existing CLOB WS in `data/feeds.py`) is the unlock. ~4-7 day infra work.\n")
    md.append("- If most fills are **Tier 2** (and capacity_1s/3s are tiny): we cannot determine this from REST data; would need WS to even measure. Implies sub-second decay → likely uncompetitive at retail latency anyway.\n")
    md.append("- If most fills are **Tier 3**: the wallets are queue-position dependent (resting limit orders at the front of the queue). Copying as a taker won't work; would need to BECOME a maker.\n")

    md_str = "".join(md)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / f"executability_{args.date}.md"
    json_path = OUT_DIR / f"executability_{args.date}.json"
    md_path.write_text(md_str)
    json_path.write_text(json.dumps({
        "date": args.date,
        "per_wallet_tiers": dict(per_wallet_tiers),
        "fill_records": fill_records[:500],   # sample
        "pair_windows": pair_windows_all,
        "hedge_records": hedge_records,
    }, default=str, indent=2))
    print(md_str)
    print(f"\n# saved {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
