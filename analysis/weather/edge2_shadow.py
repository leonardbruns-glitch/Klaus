#!/usr/bin/env python3
"""
edge2_shadow.py — forward shadow logger for EDGE 2: Order-Flow Imbalance
Resolution Follow (research finding 2026-06-02, see analysis/weather/conservation_alpha.py).

THESIS (proven on 3.6d of tape, 90 resolved events): a bucket's rolling 600s
order-flow imbalance predicts its RESOLUTION beyond its current price. Net-bought
mid-priced buckets resolve ABOVE their mid; net-sold ones resolve BELOW — a ~15pp
buy-vs-sell resolution spread at mid 0.4-0.6, net edge ~+3.3pp/contract after a 2.5c
one-way spread. Backtest was edge-measured-vs-mid; this logs the SAME signal LIVE with
the real entry mid + fillable depth so it can be joined to resolution for a forward
WR/EV check at n>=100/band BEFORE any capital.

STANDALONE + READ-ONLY (mirrors maker_flow_probe.py). Does NOT import or touch the live
engine; cannot affect trading. No capital, no orders. Kill = stop the process.

Signal (per bucket = per condition_id):
  - maintain rolling OFI = sum(signed $notional)/sum(|$notional|) over OFI_WIN secs,
    where ask-side(+) = (outcome=Yes & BUY) or (outcome=No & SELL)  [YES-buy pressure],
          bid-side(-) = (outcome=Yes & SELL) or (outcome=No & BUY)  [YES-sell pressure];
  - fire when |OFI| >= OFI_MIN and rolling vol >= VOL_MIN and YES-mid in [MID_LO, MID_HI];
  - direction = BUY_YES if OFI>0 else BUY_NO (follow the flow); dedup one fire/bucket/day.
On fire: fetch the real CLOB book once, log entry mid + best bid/ask + fillable depth on
the trade side + seconds-to-close, to logs/shadow/hot/<date>/edge2_shadow.jsonl.

Run:  python3 analysis/weather/edge2_shadow.py            # loops every POLL_SEC
      python3 analysis/weather/edge2_shadow.py --once      # single pass (test)
"""
import asyncio
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

GAMMA    = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
CLOB     = "https://clob.polymarket.com"
POLL_SEC = 120
TRADES_LIMIT = 500
BATCH    = 10

OFI_WIN  = 600.0     # rolling window (s) — matches backtest
OFI_MIN  = 0.30      # |OFI| trigger
VOL_MIN  = 50.0      # min rolling $ volume to trust the imbalance
MID_LO, MID_HI = 0.20, 0.80
DEPTH_BAND = 0.03    # sum fillable depth within 3c of touch on the trade side


def _log_dir() -> Path:
    d = (Path(__file__).resolve().parents[2] / "logs" / "shadow" / "hot"
         / datetime.now(timezone.utc).date().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dedup_key(t: dict) -> str:
    h = t.get("transactionHash") or t.get("transaction_hash") or ""
    a = t.get("asset") or t.get("asset_id") or t.get("token_id") or ""
    ts = t.get("timestamp") or t.get("ts") or ""
    return f"{h}|{a}|{ts}"


def _signed_notional(t: dict):
    """(+abs) for YES-buy pressure, (-abs) for YES-sell pressure; abs notional."""
    try:
        pr = float(t.get("price"))
        sz = float(t.get("size"))
    except (TypeError, ValueError):
        return None
    notion = pr * sz
    oc = str(t.get("outcome", "")).lower()
    sd = str(t.get("side", "")).upper()
    ask = (oc == "yes" and sd == "BUY") or (oc == "no" and sd == "SELL")
    return (notion if ask else -notion), notion


async def _get_json(sess, url):
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def fetch_active_weather_markets(sess) -> dict:
    """{cid: {q, tokens[yes,no], end}} for OPEN weather markets (paginated)."""
    out, offset = {}, 0
    while True:
        page = await _get_json(
            sess, f"{GAMMA}/events?closed=false&limit=100&offset={offset}&tag_slug=weather")
        if not page:
            break
        for ev in page:
            for m in ev.get("markets", []):
                if m.get("closed", False):
                    continue
                cid = m.get("conditionId")
                if not cid:
                    continue
                toks_raw = m.get("clobTokenIds", "[]")
                try:
                    toks = json.loads(toks_raw) if isinstance(toks_raw, str) else toks_raw
                except Exception:
                    toks = []
                if len(toks) < 2:
                    continue
                out[cid] = {"q": m.get("question", ""), "tokens": toks,
                            "end": m.get("endDate", ""), "slug": m.get("slug", "")}
        if len(page) < 100:
            break
        offset += len(page)
    return out


async def _poll_trades(sess, cid):
    rows = await _get_json(sess, f"{DATA_API}/trades?market={cid}&limit={TRADES_LIMIT}")
    return cid, (rows or [])


def _book_mid_depth(book, side):
    """YES book -> (mid, best_bid, best_ask, fillable_usd on `side`)."""
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return None
    try:
        bb = max(float(b["price"]) for b in bids)
        ba = min(float(a["price"]) for a in asks)
    except (KeyError, ValueError):
        return None
    mid = 0.5 * (bb + ba)
    # BUY_YES fills off asks; BUY_NO (short YES) fills off the YES bids (mirror of NO asks)
    levels = asks if side == "BUY_YES" else bids
    touch = ba if side == "BUY_YES" else bb
    usd = 0.0
    for lv in levels:
        try:
            p = float(lv["price"]); s = float(lv["size"])
        except (KeyError, ValueError):
            continue
        if abs(p - touch) <= DEPTH_BAND:
            usd += p * s
    return mid, bb, ba, usd


async def one_pass(sess, ofi_state, seen, logged, ef):
    markets = await fetch_active_weather_markets(sess)
    cids = list(markets.keys())
    now = time.time()
    n_sig = 0
    for i in range(0, len(cids), BATCH):
        batch = cids[i:i + BATCH]
        results = await asyncio.gather(*[_poll_trades(sess, c) for c in batch])
        for cid, trades in results:
            q = ofi_state.setdefault(cid, deque())
            for t in trades:
                if not isinstance(t, dict):
                    continue
                k = _dedup_key(t)
                if k in seen:
                    continue
                seen.add(k)
                sn = _signed_notional(t)
                if sn is None:
                    continue
                try:
                    tts = float(t.get("timestamp") or t.get("ts") or now)
                except (TypeError, ValueError):
                    tts = now
                q.append((tts, sn[0], sn[1]))
            # expire old
            while q and now - q[0][0] > OFI_WIN:
                q.popleft()
            if cid in logged or not q:
                continue
            tot = sum(a for _, _, a in q)
            if tot < VOL_MIN:
                continue
            ofi = sum(s for _, s, _ in q) / tot
            if abs(ofi) < OFI_MIN:
                continue
            # qualifying flow imbalance -> fetch book once, validate mid band, log
            yes_tok = markets[cid]["tokens"][0]
            book = await _get_json(sess, f"{CLOB}/book?token_id={yes_tok}")
            if not book:
                continue
            side = "BUY_YES" if ofi > 0 else "BUY_NO"
            md = _book_mid_depth(book, side)
            if md is None:
                continue
            mid, bb, ba, usd = md
            if not (MID_LO <= mid <= MID_HI):
                continue
            end = markets[cid]["end"]
            sec_to_close = None
            try:
                ec = datetime.fromisoformat(end.replace("Z", "+00:00"))
                sec_to_close = (ec - datetime.now(timezone.utc)).total_seconds()
            except Exception:
                pass
            rec = {
                "ts": now, "cid": cid, "q": markets[cid]["q"], "slug": markets[cid]["slug"],
                "yes_token": yes_tok, "ofi": round(ofi, 4), "rolling_vol_usd": round(tot, 2),
                "n_trades_win": len(q), "direction": side,
                "entry_yes_mid": round(mid, 4), "best_bid": round(bb, 4), "best_ask": round(ba, 4),
                "spread": round(ba - bb, 4), "fillable_usd_side": round(usd, 2),
                "end_date": end, "sec_to_close": (round(sec_to_close) if sec_to_close is not None else None),
            }
            ef.write(json.dumps(rec) + "\n")
            logged.add(cid)
            n_sig += 1
        await asyncio.sleep(0.3)
    ef.flush()
    return len(cids), n_sig


async def main():
    once = "--once" in sys.argv
    ofi_state, seen, logged = {}, set(), set()
    cur_day = datetime.now(timezone.utc).date().isoformat()
    print(f"[edge2_shadow] start once={once} poll={POLL_SEC}s "
          f"OFI>={OFI_MIN} vol>=${VOL_MIN} mid[{MID_LO},{MID_HI}]", flush=True)
    async with aiohttp.ClientSession() as sess:
        while True:
            t0 = time.time()
            day = datetime.now(timezone.utc).date().isoformat()
            if day != cur_day:          # daily reset of one-fire-per-bucket dedup
                logged.clear(); cur_day = day
            try:
                with (_log_dir() / "edge2_shadow.jsonl").open("a") as ef:
                    n_mkt, n_sig = await one_pass(sess, ofi_state, seen, logged, ef)
                print(f"[edge2_shadow] {datetime.now(timezone.utc).isoformat()} "
                      f"markets={n_mkt} new_signals={n_sig} logged_today={len(logged)} "
                      f"({time.time() - t0:.1f}s)", flush=True)
            except Exception as e:
                print(f"[edge2_shadow] pass error: {e}", flush=True)
            if once:
                break
            await asyncio.sleep(max(5.0, POLL_SEC - (time.time() - t0)))


if __name__ == "__main__":
    asyncio.run(main())
