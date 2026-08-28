"""
Favorite-Longshot MAKER screener (read-only; ZERO capital risk).

The chosen money-maker (project_flb_maker_strategy) is: harvest the favorite-
longshot bias as a FEE-FREE MAKER, cross-category. The weather maker is already
live (MAKER_EXERCISE_LIVE) on locked buckets; this screener proves whether
fillable FLB maker setups exist OUTSIDE weather (sports/politics/etc.) before we
risk a dollar on untested cross-category live orders.

For each active liquid market it pulls the live CLOB book for the FAVORITE token
and logs whether there is room to REST a maker bid inside the spread on the
favorite (the underpriced side). No orders are placed.

Setup logged when: favorite best-ask >= FAV_MIN (favorite), spread >= MIN_SPREAD
(room to improve the bid), and book depth is real. Output → logs/shadow/flb_screener.jsonl.

Run: python3 strategy/flb_screener.py            # one live scan
     python3 strategy/flb_screener.py --loop 300 # every 5 min
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB_BOOK = "https://clob.polymarket.com/book"
OUT = Path("logs/shadow/flb_screener.jsonl")

FAV_MIN     = 0.70    # favorite leg priced >= this (widened from 0.80 for fairer shot)
EDGE_MIN    = 0.01    # log only if maker capture (p_fair - maker_px) >= this
MIN_DEPTH_SH = 20     # >= this many shares resting at the favorite inside levels
SKIP_WORDS  = ("temperature", "highest temp", "weather", "°f", "°c")  # weather = already covered


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-flb/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_markets(limit=400):
    """Active, liquid markets sorted by 24h volume."""
    q = urllib.parse.urlencode({
        "closed": "false", "active": "true", "archived": "false",
        "liquidity_num_min": 5000, "order": "volume24hr", "ascending": "false",
        "limit": limit,
    })
    try:
        return _get(f"{GAMMA}?{q}")
    except Exception as e:
        print("gamma fetch error:", e); return []


def book_bbo(token_id):
    """Return (best_bid, best_ask, bid_depth_sh, ask_depth_sh) for a token, or None."""
    try:
        b = _get(f"{CLOB_BOOK}?token_id={token_id}")
    except Exception:
        return None
    bids = b.get("bids") or []
    asks = b.get("asks") or []
    if not bids or not asks:
        return None
    # CLOB book: bids ascending, asks descending → best bid = max price bid, best ask = min price ask
    try:
        bb = max(bids, key=lambda x: float(x["price"]))
        ba = min(asks, key=lambda x: float(x["price"]))
        bid_sh = sum(float(x["size"]) for x in bids if abs(float(x["price"]) - float(bb["price"])) < 1e-9)
        ask_sh = sum(float(x["size"]) for x in asks if abs(float(x["price"]) - float(ba["price"])) < 1e-9)
        return (float(bb["price"]), float(ba["price"]), bid_sh, ask_sh)
    except Exception:
        return None


def scan():
    mkts = fetch_markets()
    now = datetime.now(timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    setups = []
    scanned = 0
    cats = {}
    for m in mkts:
        q = (m.get("question") or "").lower()
        if any(w in q for w in SKIP_WORDS):
            continue
        toks = m.get("clobTokenIds")
        if isinstance(toks, str):
            try: toks = json.loads(toks)
            except Exception: toks = None
        if not toks or len(toks) != 2:
            continue
        prices = m.get("outcomePrices")
        if isinstance(prices, str):
            try: prices = json.loads(prices)
            except Exception: prices = None
        if not prices or len(prices) != 2:
            continue
        try:
            p0 = float(prices[0]); p1 = float(prices[1])
        except Exception:
            continue
        # favorite = the side priced >= FAV_MIN
        fav_idx = 0 if p0 >= p1 else 1
        if max(p0, p1) < FAV_MIN:
            continue
        scanned += 1
        fav_tok = toks[fav_idx]
        bbo = book_bbo(fav_tok)
        if not bbo:
            continue
        bb, ba, bid_sh, ask_sh = bbo
        spread = round(ba - bb, 4)
        if ask_sh < MIN_DEPTH_SH:
            continue
        # maker bid: improve by 1c if there's room (spread>=2c), else JOIN the best bid.
        maker_px = round(bb + 0.01, 2) if spread >= 0.02 else round(bb, 2)
        p_fav = max(p0, p1)
        mid = round((bb + ba) / 2.0, 4)
        # Log EVERY liquid favorite as a would-REST candidate. The REAL FLB test is
        # the resolution join (does buying the favorite at maker_px resolve +EV?),
        # NOT spread-capture-vs-last. edge-vs-last is kept only as a weak proxy.
        edge = round(p_fav - maker_px, 4)
        # in-play detection: game already started but market still open = live game
        in_play = False
        gst = m.get("gameStartTime") or m.get("startDate") or m.get("startDateIso")
        if gst:
            try:
                t0 = datetime.fromisoformat(str(gst).replace("Z", "+00:00"))
                in_play = t0 < datetime.now(timezone.utc)
            except Exception:
                pass
        cat = (m.get("category") or m.get("seriesSlug") or "other")
        cats[cat] = cats.get(cat, 0) + 1
        rec = {
            "ts": now, "category": cat, "in_play": in_play, "question": m.get("question", "")[:90],
            "condition_id": m.get("conditionId"), "fav_token": fav_tok, "fav_idx": fav_idx,
            "end_date": m.get("endDate"), "fav_last": p_fav, "mid": mid,
            "best_bid": bb, "best_ask": ba, "spread": spread,
            "ask_depth_sh": round(ask_sh, 1), "bid_depth_sh": round(bid_sh, 1),
            "proposed_maker_px": maker_px, "gross_edge": edge,
            "vol24": m.get("volume24hr"), "liquidity": m.get("liquidityNum") or m.get("liquidity"),
        }
        setups.append(rec)
        with OUT.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    return scanned, setups, cats


def main():
    loop = 0
    if "--loop" in sys.argv:
        try: loop = int(sys.argv[sys.argv.index("--loop") + 1])
        except Exception: loop = 300
    while True:
        scanned, setups, cats = scan()
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] favorites scanned={scanned} "
              f"FLB-maker setups={len(setups)} by_cat={cats}")
        if setups:
            setups.sort(key=lambda r: -(r['gross_edge'] or 0))
            print("  top setups (gross_edge desc):")
            inplay_n = sum(1 for r in setups if r.get("in_play"))
            print(f"  in-play setups: {inplay_n}/{len(setups)}")
            for r in setups[:10]:
                live = "LIVE" if r.get("in_play") else "pre "
                print(f"    [{live}] {r['category'][:10]:10} edge={r['gross_edge']:+.3f} "
                      f"bid/ask={r['best_bid']}/{r['best_ask']} spr={r['spread']} "
                      f"depth={r['ask_depth_sh']}sh | {r['question'][:50]}")
        if not loop:
            break
        time.sleep(loop)


if __name__ == "__main__":
    main()
