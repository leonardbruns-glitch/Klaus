#!/usr/bin/env python3
"""Tape-sim of band maker quote PRICING models (offline, zero capital).

PURPOSE (2026-06-12): the badatmath quote-watch (n=1,889 buy-fill joins) showed
he rests deep value bids (44% at touch only; NO side 31%) and pair-quotes both
sides of a bucket (pair VWAP sum median 0.90). Before changing live quoting,
measure on OUR tape what each pricing model would have filled and earned:

  inputs  band_struct.jsonl  md_shadow/fire records = candidate buckets + the
                             live model's quote (bid_quote) + gamma ask, per
                             ~300s cycle
          maker_flow.jsonl   public weather taker tape (data-api poll); a SELL
                             print at price p fills any resting bid > p
                             (certain) or == p (queue-optimistic)
          gamma API          resolution (outcomePrices) per conditionId

  fill rule  quote q active from each fire ts until the next fire for the same
             bucket (or local midnight). STRICT fill = SELL trade price < q.
             TOUCH fill = price <= q. One fill per bucket-side-day; shares =
             stake / q (NO stake = NO_STAKE).

  variants   LIVE   q_yes = logged bid_quote          q_no = PAIR_CAP - q_yes
             DEEP3  q_yes = ask - 0.03                q_no = PAIR_CAP - q_yes
             DEEP5  q_yes = ask - 0.05                q_no = PAIR_CAP - q_yes
             (q_no clamped to [NO_MIN, NO_MAX]; NO offset rules NOT applied —
              identical bucket set across variants isolates pricing.)

  outputs    per variant: quotes, fills (strict/touch), pair completions,
             merge-locked $, unpaired resolution PnL, ROI on filled cost.

Decision gate: n>=100 RESOLVED simulated fills per variant before any live
quoting change (CLAUDE.md rule).
"""
import json
import glob
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta

PAIR_CAP = 0.88     # simulated same-bucket YES+NO bid sum (live cap is 0.92)
NO_MIN, NO_MAX = 0.52, 0.85
NO_STAKE = 3.0
HOT = "/root/Klaus/logs/shadow/hot"
VARIANTS = {
    "LIVE":  lambda ask, bid_quote: bid_quote,
    "DEEP3": lambda ask, bid_quote: round(ask - 0.03, 3),
    "DEEP5": lambda ask, bid_quote: round(ask - 0.05, 3),
}

# city -> UTC offset hours (market day = local calendar day)
TZ = {"karachi": 5, "madrid": 2, "amsterdam": 2, "tokyo": 9, "jeddah": 3,
      "munich": 2, "moscow": 3, "wuhan": 8, "chongqing": 8, "taipei": 8,
      "seoul": 9, "qingdao": 8, "san francisco": -7, "seattle": -7,
      "london": 1, "singapore": 8, "helsinki": 3, "denver": -6, "paris": 2,
      "ankara": 3, "beijing": 8, "chengdu": 8, "guangzhou": 8, "shanghai": 8,
      "nyc": -4, "austin": -5, "chicago": -5, "atlanta": -4, "miami": -4,
      "dallas": -5, "houston": -5, "boston": -4, "philadelphia": -4,
      "toronto": -4, "los angeles": -7, "phoenix": -7, "wellington": 12,
      "sydney": 10, "melbourne": 10, "brisbane": 10, "auckland": 12,
      "hong kong": 8, "shenzhen": 8, "mumbai": 5.5, "delhi": 5.5,
      "new delhi": 5.5, "bangkok": 7, "manila": 8, "jakarta": 7,
      "kuala lumpur": 8, "sao paulo": -3, "buenos aires": -3,
      "mexico city": -6, "bogota": -5, "lima": -5, "rio de janeiro": -3,
      "cairo": 3, "lagos": 1, "nairobi": 3, "johannesburg": 2,
      "istanbul": 3, "rome": 2, "berlin": 2, "vienna": 2, "warsaw": 2,
      "stockholm": 2, "oslo": 2, "copenhagen": 2, "dublin": 1, "lisbon": 1,
      "barcelona": 2, "athens": 3, "kyiv": 3, "minneapolis": -5, "denver2": -6}


def day_end_utc(date_iso: str, city: str) -> float:
    off = TZ.get(city.lower(), 0)
    d = datetime.strptime(date_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d - timedelta(hours=off) + timedelta(days=1)).timestamp()


def load_fires(days):
    """(city, date, cid) -> list of (ts, ask, bid_quote, stake, lo, hi, off, tok)."""
    out = defaultdict(list)
    for day in days:
        try:
            fh = open(f"{HOT}/{day}/band_struct.jsonl")
        except FileNotFoundError:
            continue
        for line in fh:
            if '"reason": "fire"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for q in r.get("quotes", []):
                if not q.get("cid") or not q.get("tok"):
                    continue
                out[(r["city"], r["date"], q["cid"])].append(
                    (r["ts"], q["ask"], q["bid_quote"], q["stake"],
                     q["lo"], q["hi"], q["off"], q["tok"]))
    for v in out.values():
        v.sort()
    return out


def load_tape(days):
    """token -> sorted [(trade_ts, price, side)], plus cid -> set(tokens)."""
    tape = defaultdict(list)
    cid_toks = defaultdict(set)
    for day in days:
        try:
            fh = open(f"{HOT}/{day}/maker_flow.jsonl")
        except FileNotFoundError:
            continue
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            a, c = r.get("asset"), r.get("conditionId")
            if not a or not c:
                continue
            tape[a].append((r.get("timestamp", 0), float(r.get("price", 0)),
                            r.get("side", "")))
            cid_toks[c].add(a)
    for v in tape.values():
        v.sort()
    return tape, cid_toks


def first_fill(tape_rows, segments, strict=True):
    """segments = [(t0, t1, q)]; return (ts, price, q) of first SELL crossing."""
    for t0, t1, q in segments:
        for ts, p, side in tape_rows:
            if ts < t0 or side != "SELL":
                continue
            if ts >= t1:
                break
            if (p < q) if strict else (p <= q):
                return ts, p, q
    return None


def fetch_resolutions(cids):
    hdr = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    res = {}
    # CLOB registry: gamma drops resolved weather markets from condition_ids
    # lookups; clob.polymarket.com/markets/<cid> keeps them with winner flags.
    for c in sorted(cids):
        url = "https://clob.polymarket.com/markets/" + c
        try:
            req = urllib.request.Request(url, headers=hdr)
            m = json.load(urllib.request.urlopen(req, timeout=20))
            if m.get("closed"):
                for t in m.get("tokens", []):
                    if t.get("outcome") == "Yes" and t.get("winner") is not None:
                        res[c] = 1.0 if t["winner"] else 0.0
        except Exception:
            pass
        time.sleep(0.08)
    return res


def main(days):
    fires = load_fires(days)
    tape, cid_toks = load_tape(days)
    print(f"buckets quoted: {len(fires)}; tape tokens: {len(tape)}")

    resolutions = fetch_resolutions({cid for _, _, cid in fires})
    print(f"resolutions fetched: {len(resolutions)}")

    for vname, price_fn in VARIANTS.items():
        for strict in (True, False):
            stats = dict(q=0, yfill=0, nfill=0, pair=0, merge_usd=0.0,
                         cost=0.0, pay=0.0, res_n=0, res_cost=0.0, res_pay=0.0)
            for (city, date, cid), rows in fires.items():
                t_end = day_end_utc(date, city)
                yes_tok = rows[0][7]
                no_tok = next((t for t in cid_toks.get(cid, ()) if t != yes_tok), None)
                # piecewise quote segments
                seg_y, seg_n = [], []
                for i, (ts, ask, bq, stake, lo, hi, off, tok) in enumerate(rows):
                    t1 = rows[i + 1][0] if i + 1 < len(rows) else t_end
                    qy = max(0.01, min(round(ask - 0.01, 3), price_fn(ask, bq)))
                    qn = round(PAIR_CAP - qy, 3)
                    seg_y.append((ts, t1, qy))
                    if NO_MIN <= qn <= NO_MAX:
                        seg_n.append((ts, t1, qn))
                stats["q"] += 1
                fy = first_fill(tape.get(yes_tok, ()), seg_y, strict)
                fn = (first_fill(tape.get(no_tok, ()), seg_n, strict)
                      if no_tok and seg_n else None)
                stake = rows[0][3]
                shy = stake / fy[2] if fy else 0.0
                shn = NO_STAKE / fn[2] if fn else 0.0
                if fy:
                    stats["yfill"] += 1
                    stats["cost"] += shy * fy[2]
                if fn:
                    stats["nfill"] += 1
                    stats["cost"] += shn * fn[2]
                if fy and fn:
                    stats["pair"] += 1
                    m = min(shy, shn)
                    stats["merge_usd"] += m * (1 - fy[2] - fn[2])
                    shy, shn = shy - m, shn - m
                yres = resolutions.get(cid)
                if yres is not None and (fy or fn):
                    stats["res_n"] += 1
                    c = (shy * fy[2] if fy else 0) + (shn * fn[2] if fn else 0)
                    p = shy * yres + shn * (1 - yres)
                    stats["res_cost"] += c
                    stats["res_pay"] += p
            mode = "strict" if strict else "touch "
            roi = ((stats["res_pay"] - stats["res_cost"]) / stats["res_cost"]
                   if stats["res_cost"] else 0.0)
            print(f"{vname:<6}{mode} quoted={stats['q']:>5} "
                  f"Yfill={stats['yfill']:>4} Nfill={stats['nfill']:>4} "
                  f"pairs={stats['pair']:>4} merge=${stats['merge_usd']:>7.2f} "
                  f"| resolved buckets={stats['res_n']:>4} "
                  f"cost=${stats['res_cost']:>8.2f} pay=${stats['res_pay']:>8.2f} "
                  f"unpaired-ROI={roi:>7.1%}")


if __name__ == "__main__":
    days = sys.argv[1:] or ["2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]
    main(days)
