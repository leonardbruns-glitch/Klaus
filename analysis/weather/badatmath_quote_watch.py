#!/usr/bin/env python3
"""badatmath quote-placement watcher (read-only; cron */2).

PURPOSE (2026-06-11): before changing OUR quote pricing to mirror him, OBSERVE
where his bids actually rest. His fills are public (~1-2 min indexing lag) and
a maker fill prints AT the maker's bid level — joining each fresh fill to the
real CLOB book at detection time measures his depth directly:
  - fill_price == pre-fill best bid  -> he was quoting AT the touch
  - fill_price <  best bid           -> taker swept the book to reach a DEEP bid
  - size remaining at his level      -> residual resting bid (no requote needed)
Plus one ladder sweep per pass (rotating): full bid ladders on an event he just
traded -> whole-ladder coverage, rest-state pair sums (yes_bid_i + no_bid_i via
the mirror identity no_bid = 1 - yes_ask), and bucket count vs our band gates.

Output: logs/shadow/hot/<date>/badatmath_watch.jsonl
  record=fill_join  one row per new fill of his, with book state at detection
  record=ladder     one row per swept ladder

Decision this feeds (2-3 days of data): whether to replace BAND_QUOTE_FRAC
join-the-spread quoting with value-priced deep bids. n>=100 fill_joins before
any conclusion; mind detect_lag_s (book state is post-fill by that much).
"""
import json, os, time, urllib.request
from datetime import datetime, timezone

W = "0x8fbd7cf5f806f563080864694415829f7229a959"
STATE = "/root/Klaus/logs/badatmath_watch_state.json"
OUT_DIR = "/root/Klaus/logs/shadow/hot"
MAX_JOINS_PER_PASS = 25
LADDER_SWEEP_COOLDOWN_S = 3600


def get(url, timeout=15):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception:
            time.sleep(0.7)
    return None


def book(token_id):
    b = get(f"https://clob.polymarket.com/book?token_id={token_id}")
    if not b:
        return None
    bids = sorted((float(x["price"]), float(x["size"])) for x in b.get("bids", []))[::-1][:5]
    asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))[:5]
    return {"bids": bids, "asks": asks}


def main():
    now = time.time()
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {"seen": [], "last_ts": now - 600, "swept": {}}
    seen = set(tuple(x) for x in st.get("seen", []))

    acts = get(f"https://data-api.polymarket.com/activity?user={W}&limit=200") or []
    fills = [a for a in acts
             if a.get("type") == "TRADE"
             and a.get("eventSlug", "").startswith(("highest-temperature", "lowest-temperature"))
             and a.get("timestamp", 0) > st.get("last_ts", 0) - 30]
    out_path = os.path.join(OUT_DIR, datetime.now(timezone.utc).date().isoformat())
    os.makedirs(out_path, exist_ok=True)
    out = open(os.path.join(out_path, "badatmath_watch.jsonl"), "a")

    new_seen, joined = [], 0
    recent_events = []
    for a in sorted(fills, key=lambda x: x["timestamp"]):
        key = (a.get("transactionHash"), a.get("asset"), a.get("timestamp"),
               a.get("side"), round(a.get("usdcSize", 0), 4))
        if key in seen:
            continue
        new_seen.append(list(key))
        recent_events.append(a.get("eventSlug", ""))
        if joined >= MAX_JOINS_PER_PASS or a.get("side") != "BUY":
            continue
        bk = book(a["asset"])
        joined += 1
        rec = {"ts": now, "record": "fill_join",
               "fill_ts": a["timestamp"], "detect_lag_s": round(now - a["timestamp"], 1),
               "title": a.get("title", "")[:60], "event": a.get("eventSlug", ""),
               "outcome": a.get("outcome"), "price": a.get("price"),
               "size": a.get("size"), "usdc": a.get("usdcSize"),
               "cid": a.get("conditionId"), "token": a.get("asset")}
        if bk and bk["bids"]:
            bb, ba = bk["bids"][0][0], (bk["asks"][0][0] if bk["asks"] else None)
            p = float(a.get("price") or 0)
            rec.update({
                "best_bid": bb, "best_ask": ba,
                "fill_vs_best_bid": round(p - bb, 4),
                "at_touch": abs(p - bb) < 0.0015,
                "residual_at_level": next((s for q, s in bk["bids"]
                                           if abs(q - p) < 0.0015), 0.0),
                "book_bids": bk["bids"], "book_asks": bk["asks"]})
        out.write(json.dumps(rec) + "\n")

    # one rotating ladder sweep per pass: rest-state quote surface on an event
    # he just traded (coverage, pair sums at rest, depth profile)
    swept = st.get("swept", {})
    target = next((e for e in dict.fromkeys(reversed(recent_events))
                   if now - swept.get(e, 0) > LADDER_SWEEP_COOLDOWN_S), None)
    if target:
        evs = get(f"https://gamma-api.polymarket.com/events?slug={target}")
        mkts = (evs[0].get("markets", []) if evs else [])[:14]
        rows = []
        for m in mkts:
            try:
                toks = json.loads(m.get("clobTokenIds", "[]"))
            except Exception:
                toks = []
            if not toks:
                continue
            bk = book(toks[0])
            if not bk:
                continue
            rows.append({"q": m.get("question", "")[-22:],
                         "bids": bk["bids"][:3], "asks": bk["asks"][:3]})
        out.write(json.dumps({"ts": now, "record": "ladder", "event": target,
                              "n_buckets": len(rows), "books": rows}) + "\n")
        swept[target] = now
    out.close()

    st["seen"] = (st.get("seen", []) + new_seen)[-3000:]
    st["last_ts"] = max([st.get("last_ts", 0)] + [a["timestamp"] for a in fills] or [now])
    st["swept"] = {k: v for k, v in swept.items() if now - v < 86400}
    json.dump(st, open(STATE, "w"))
    print(f"{datetime.now(timezone.utc).isoformat()} new_fills={len(new_seen)} "
          f"joined={joined} sweep={'1' if target else '0'}")


if __name__ == "__main__":
    main()
