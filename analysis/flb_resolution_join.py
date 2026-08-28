"""
FLB-maker resolution join (read-only) — does buying the favorite at the maker bid
actually resolve +EV? The definitive test of the favorite-longshot MAKER thesis.

Reads logs/shadow/flb_screener.jsonl (would-REST favorite candidates logged live),
dedupes to first-seen per market, fetches ACTUAL Gamma resolution, and computes
realized PnL/share of "buy the favorite at proposed_maker_px, hold to resolution":
    win  (favorite YES resolves 1) →  +(1 - maker_px)
    loss (favorite resolves 0)     →  -maker_px

Splits by in-play vs pre-game, price band, and category. This is the only honest
arbiter of whether the FLB-maker edge survives the favorite's loss rate. NOTE: the
"would-rest" fill is optimistic (assumes we get filled at the bid) — fill-rate is a
separate question the live maker must answer; this bounds the EV ceiling.

Run: python3 analysis/flb_resolution_join.py
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from pathlib import Path

SHADOW = Path("logs/shadow/flb_screener.jsonl")
GAMMA = "https://gamma-api.polymarket.com/markets"


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-flb/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def load_candidates():
    """first-seen per condition_id."""
    first = {}
    if not SHADOW.exists():
        return first
    for l in SHADOW.open():
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        cid = r.get("condition_id")
        if not cid:
            continue
        if cid not in first or r.get("ts", "") < first[cid].get("ts", ""):
            first[cid] = r
    return first


def fetch_resolutions(cids):
    """{condition_id: (closed, outcomePrices[])} via Gamma, batched."""
    out = {}
    cids = list(cids)
    for i in range(0, len(cids), 20):
        batch = cids[i:i + 20]
        q = urllib.parse.urlencode([("condition_ids", c) for c in batch] + [("limit", 100)])
        try:
            data = _get(f"{GAMMA}?{q}")
        except Exception as e:
            print("gamma batch error:", e)
            continue
        for m in data:
            cid = m.get("conditionId")
            if not cid:
                continue
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except Exception:
                    prices = None
            out[cid] = (bool(m.get("closed")), prices)
    return out


def main():
    cands = load_candidates()
    print(f"FLB screener candidates (unique markets, first-seen): {len(cands)}")
    if not cands:
        print("No candidates yet — let the screener (strategy/flb_screener.py --loop) run, retry in a few hours.")
        return
    res = fetch_resolutions(cands.keys())
    rows = []
    closed = 0
    for cid, c in cands.items():
        cl, prices = res.get(cid, (False, None))
        if not cl or not prices:
            continue
        fav_idx = c.get("fav_idx", 0)
        try:
            fav_px_resolved = float(prices[fav_idx])
        except Exception:
            continue
        won = fav_px_resolved >= 0.99
        if not (won or fav_px_resolved <= 0.01):
            continue  # ambiguous
        closed += 1
        mk = c.get("proposed_maker_px")
        if mk is None:
            continue
        pnl = (1.0 - mk) if won else (-mk)
        rows.append({
            "cat": c.get("category", "?"), "in_play": c.get("in_play", False),
            "maker_px": mk, "fav_last": c.get("fav_last"), "won": won, "pnl": pnl,
            "q": c.get("question", "")[:50],
        })

    print(f"resolved & scorable: {closed}")
    if not rows:
        print("Nothing resolved yet. Re-run after markets settle (~24h+).")
        return

    def agg(label, sub):
        if not sub:
            return
        n = len(sub); w = sum(1 for r in sub if r["won"])
        ev = sum(r["pnl"] for r in sub) / n
        print(f"  {label:<26s} n={n:<4} WR={100*w/n:5.1f}%  EV/share={ev:+.4f}")

    print(f"\n*** FLB-MAKER realized EV (buy favorite at maker bid, hold to resolution) ***")
    agg("ALL", rows)
    agg("in-play (live game)", [r for r in rows if r["in_play"]])
    agg("pre-game / static", [r for r in rows if not r["in_play"]])
    print("\nby favorite price band:")
    for lo, hi, name in [(0.70, 0.80, "0.70-0.80"), (0.80, 0.90, "0.80-0.90"),
                         (0.90, 0.97, "0.90-0.97"), (0.97, 1.01, "0.97-0.99")]:
        agg(f"  fav {name}", [r for r in rows if lo <= (r["maker_px"] or 0) < hi])
    print("\nby category (top):")
    bycat = defaultdict(list)
    for r in rows:
        bycat[r["cat"]].append(r)
    for cat, sub in sorted(bycat.items(), key=lambda kv: -len(kv[1]))[:8]:
        agg(f"  {cat[:22]}", sub)

    print("\nHONEST READ: EV/share here is the CEILING (assumes we fill at the bid). "
          "If even this ceiling is <=0, FLB-maker is falsified. If >0, the live "
          "maker must then prove fill-rate clears the same bar.")


if __name__ == "__main__":
    main()
