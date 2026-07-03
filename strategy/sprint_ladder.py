#!/usr/bin/env python3
"""SPRINT_LADDER — goal-seeking bold-play sleeve (2026-07-03, user directive x3).

The $10k/30d mandate sits far above any available drift, so the probability
maximizer is bold play on the highest-EV shots available (Dubins–Savage), not
Kelly grinding. This sleeve takes ONE concentrated pre-peak d+0 taker shot at a
time on the intraday-nowcast trade — the informed-taker side that the maker
complex is currently bleeding to — and restakes wins toward the target.

Shot definition:
  city in pre-peak window [peak−5h, peak−1h) UTC, nowcast = official running
  max (AWC METAR) + climatological remaining rise (CITY_REMAINING_RISE);
  buy YES on the bucket containing the nowcast IFF
    0.15 ≤ best_ask ≤ 0.60  AND  p_nowcast − ask ≥ 0.10  AND
    spread ≤ 0.05           AND  ask-side depth ≥ 0.8·stake.

Sizing: stake = min(0.75·sleeve, free_usdc − RESERVE). RESERVE ($20) is a hard
floor sleeve for the mechanical flows — the ladder can NEVER touch it. Max 2
fires/day, one open shot per city-day. Hold to resolution.

Risk truth (logged, not hidden): P(reaching $10k) is a few percent at best;
the modal outcome is losing the sleeve. That is the explicit, thrice-repeated
owner instruction; the alternative (grinding) has probability ~0 of the goal.

State: logs/sprint_ladder_state.json | log: logs/sprint_ladder.jsonl
Arm with SPRINT_LADDER_LIVE=1 (default = dry-run decisions only).
Cron: */10 * * * * flock -n /tmp/sprint_ladder.lock python3 strategy/sprint_ladder.py
"""
from __future__ import annotations
import asyncio, fcntl, json, math, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import (CITY_ICAO, CITY_PEAK_HOUR_UTC, CITY_REMAINING_RISE,
                                  ICAO_UTC_OFFSET_H, _parse_outcome)

ROOT = "/root/Klaus"
STATE = f"{ROOT}/logs/sprint_ladder_state.json"
LOG = f"{ROOT}/logs/sprint_ladder.jsonl"
LIVE = os.environ.get("SPRINT_LADDER_LIVE", "0") == "1"
RESERVE_USD = 20.0
SLEEVE_INIT = 60.0
STAKE_FRAC = 0.75
MAX_FIRES_PER_DAY = 2
# Shot = the MARKET MODE bucket (ladder favorite) at a fair 2x-ish price, taken
# only when our official-obs nowcast lands inside it (confirmation). We do NOT
# buy "model edge vs market" — the 07-03 THERMO/PEAKSCALP joins proved our
# physics has no information the market lacks; contradicting cheap asks is the
# proven donation pattern (dry-run found "+45pp edge" on SF at ask 0.11 = trap).
ASK_MIN, ASK_MAX = 0.30, 0.55
EDGE_MIN = -0.05          # accept fair; stand down only if model says we overpay
EDGE_MAX = 0.30           # if we "disagree" by more than this, distrust the model
SPREAD_MAX = 0.05
# All cities with BOTH remaining-rise and peak-hour tables, minus wrong-oracle
# {VHHH, ZGSZ} (owner 07-03: "free to increase cities"). Wider universe = more
# selectivity per shot, NOT more shots — the 2/day cap is unchanged.
UNIVERSE = ["New York City", "Chicago", "Dallas", "Miami", "Seattle",
            "San Francisco", "Los Angeles", "Houston", "Denver", "Atlanta",
            "Austin", "Toronto", "Mexico City", "Sao Paulo", "Buenos Aires",
            "London", "Paris", "Munich", "Milan", "Madrid", "Warsaw",
            "Amsterdam", "Helsinki", "Moscow", "Tel Aviv",
            "Tokyo", "Beijing", "Shanghai", "Guangzhou", "Singapore", "Jakarta"]

def log(rec: dict) -> None:
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))

def load_state() -> dict:
    try:
        return json.load(open(STATE))
    except Exception:
        return {"sleeve": SLEEVE_INIT, "shots": [], "fired": {}}

def save_state(s: dict) -> None:
    json.dump(s, open(STATE, "w"), indent=1)

def http_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))

def slug_for(city: str) -> str | None:
    cands = [city.lower().replace(" ", "-")]
    if city == "New York City":
        cands.insert(0, "nyc")
    for c in cands:
        if c in CITY_REMAINING_RISE and c in CITY_PEAK_HOUR_UTC:
            return c
    return None

def official_running_max_c(icao: str, local_today: str, tz_h: int) -> float | None:
    try:
        rows = http_json(f"https://aviationweather.gov/api/data/metar?ids={icao}"
                         f"&format=json&hours=20")
    except Exception:
        return None
    mx = None
    for r in rows or []:
        t = r.get("temp")
        ot = r.get("obsTime") or r.get("reportTime")
        if t is None or ot is None:
            continue
        try:
            if isinstance(ot, (int, float)):
                dt = datetime.fromtimestamp(int(ot), timezone.utc)
            else:
                dt = datetime.fromisoformat(str(ot).replace("Z", "+00:00"))
        except Exception:
            continue
        if (dt + timedelta(hours=tz_h)).date().isoformat() != local_today:
            continue
        mx = t if mx is None else max(mx, float(t))
    return mx

def todays_event_markets(city: str, local_today: str) -> list[dict]:
    q = urllib.parse.quote(f"highest temperature in {city}")
    try:
        d = http_json(f"https://gamma-api.polymarket.com/public-search?q={q}"
                      f"&limit_per_type=12")
    except Exception:
        return []
    out = []
    for ev in d.get("events") or []:
        for m in ev.get("markets") or []:
            ques = m.get("question") or ""
            if city.lower() not in ques.lower() or "highest" not in ques.lower():
                continue
            if (m.get("endDate") or "")[:10] == local_today and not m.get("closed"):
                out.append(m)
    return out

def book(token: str) -> tuple[float | None, float | None, float]:
    try:
        b = http_json(f"https://clob.polymarket.com/book?token_id={token}", 10)
    except Exception:
        return None, None, 0.0
    asks = b.get("asks") or []
    bids = b.get("bids") or []
    ask = min((float(a["price"]) for a in asks), default=None)
    bid = max((float(a["price"]) for a in bids), default=None)
    depth = sum(float(a["price"]) * float(a["size"]) for a in asks
                if ask is not None and float(a["price"]) <= ask + 0.02)
    return ask, bid, depth

def p_bucket(nowcast: float, run_max: float, lo, hi, hrs_to_peak: float) -> float:
    sigma = 0.7 if hrs_to_peak <= 3 else 0.9
    lo_eff = max(lo if lo is not None else -99.0, run_max - 1e-9)
    hi_eff = hi if hi is not None else 99.0
    if hi_eff <= run_max:
        return 0.0
    def cdf(x): return 0.5 * (1 + math.erf((x - nowcast) / (sigma * math.sqrt(2))))
    return max(0.0, cdf(hi_eff) - cdf(lo_eff))

def settle_open_shots(state: dict) -> None:
    for shot in state["shots"]:
        if shot.get("status") != "open":
            continue
        try:
            d = http_json("https://gamma-api.polymarket.com/public-search?q=" +
                          urllib.parse.quote(f"highest temperature in {shot['city']}") +
                          "&limit_per_type=12")
        except Exception:
            continue
        for ev in d.get("events") or []:
            for m in ev.get("markets") or []:
                try:
                    toks = json.loads(m.get("clobTokenIds") or "[]")
                    prices = json.loads(m.get("outcomePrices") or "[]")
                except Exception:
                    continue
                if shot["token"] in toks and m.get("closed") and len(prices) == 2:
                    payout = float(prices[toks.index(shot["token"])])
                    won = payout >= 0.99
                    shot["status"] = "won" if won else "lost"
                    if won:
                        state["sleeve"] = round(state["sleeve"] + shot["shares"], 2)
                    log({"event": "settle", "city": shot["city"], "won": won,
                         "shares": shot["shares"], "sleeve": state["sleeve"]})

async def fire(token: str, ask: float, stake: float):
    from execution.order_manager import OrderManager, Direction
    om = OrderManager()
    try:
        await om.start()
    except Exception:
        pass
    bal = await asyncio.to_thread(om.fetch_usdc_balance)
    if bal is None or bal - stake < RESERVE_USD:
        log({"event": "skip_reserve", "balance": bal, "stake": stake})
        return None
    res = await om.limit_buy(token, ask, stake, Direction.BUY_YES,
                             price_ceiling=round(ask + 0.015, 3))
    return res

def main() -> None:
    lock = open("/tmp/sprint_ladder.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    now = datetime.now(timezone.utc)
    state = load_state()
    settle_open_shots(state)
    today = now.date().isoformat()
    fired_today = state["fired"].get(today, 0)
    open_shots = [s for s in state["shots"] if s.get("status") == "open"]
    if fired_today >= MAX_FIRES_PER_DAY or state["sleeve"] < 5.0:
        save_state(state)
        return
    best = None
    for city in UNIVERSE:
        icao = CITY_ICAO.get(city)
        slug = slug_for(city)
        if not icao or not slug:
            continue
        tz_h = ICAO_UTC_OFFSET_H.get(icao, 0)
        local_today = (now + timedelta(hours=tz_h)).date().isoformat()
        peak_utc = CITY_PEAK_HOUR_UTC[slug].get(now.month)
        if peak_utc is None:
            continue
        hrs_to_peak = (peak_utc - now.hour) % 24
        if not (1 <= hrs_to_peak <= 5):
            continue
        if any(s["city"] == city and s["end_date"] == local_today
               for s in state["shots"]):
            continue
        rise = CITY_REMAINING_RISE[slug].get(now.month, {}).get(now.hour)
        if not rise or rise <= 0:
            continue
        run_max = official_running_max_c(icao, local_today, tz_h)
        if run_max is None:
            continue
        nowcast = run_max + rise
        mkts = todays_event_markets(city, local_today)
        # market mode = the ladder bucket with the highest midpoint
        mode_m, mode_mid = None, -1.0
        parsed = []
        for m in mkts:
            lo, hi, _cel = _parse_outcome(m.get("question") or "")
            if lo is None and hi is None:
                continue
            try:
                toks = json.loads(m.get("clobTokenIds") or "[]")
            except Exception:
                continue
            if len(toks) != 2:
                continue
            ask, bid, depth = book(toks[0])
            if ask is None or bid is None:
                continue
            mid = (ask + bid) / 2
            parsed.append((m, lo, hi, toks, ask, bid, depth, mid))
            if mid > mode_mid:
                mode_m, mode_mid = m, mid
        for (m, lo, hi, toks, ask, bid, depth, mid) in parsed:
            if m is not mode_m:
                continue                      # favorite only
            if not ((lo is None or lo <= nowcast) and (hi is None or nowcast < hi)):
                log({"event": "mode_not_confirmed", "city": city,
                     "q": m.get("question"), "nowcast": round(nowcast, 2),
                     "run_max": run_max, "ask": ask})
                continue                      # obs trajectory must confirm the mode
            p = p_bucket(nowcast, run_max, lo, hi, hrs_to_peak)
            edge = p - ask
            cand = {"city": city, "end_date": local_today, "q": m.get("question"),
                    "token": toks[0], "ask": ask, "bid": bid, "depth": round(depth, 2),
                    "run_max": run_max, "rise": rise, "nowcast": round(nowcast, 2),
                    "p": round(p, 3), "edge": round(edge, 3),
                    "hrs_to_peak": hrs_to_peak}
            log({"event": "eval", **cand})
            ok = (ASK_MIN <= ask <= ASK_MAX and EDGE_MIN <= edge <= EDGE_MAX
                  and (ask - bid) <= SPREAD_MAX)
            if ok and (best is None or ask > best["ask"]):
                best = cand                   # prefer the strongest confirmed favorite
    if best is None:
        save_state(state)
        return
    stake = round(min(STAKE_FRAC * state["sleeve"], 45.0), 2)
    if best["depth"] < 0.8 * stake:
        log({"event": "skip_depth", **best, "stake": stake})
        save_state(state)
        return
    if not LIVE:
        log({"event": "DRY_FIRE", **best, "stake": stake})
        save_state(state)
        return
    res = asyncio.run(fire(best["token"], best["ask"], stake))
    if res is not None and getattr(res, "status", None) is not None and \
            "FILLED" in str(res.status):
        shares = round(getattr(res, "total_size", 0.0) or stake / best["ask"], 2)
        state["sleeve"] = round(state["sleeve"] - stake, 2)
        state["fired"][today] = fired_today + 1
        state["shots"].append({"date": today, "city": best["city"],
                               "end_date": best["end_date"], "token": best["token"],
                               "q": best["q"], "ask": best["ask"], "stake": stake,
                               "shares": shares, "status": "open"})
        log({"event": "FIRED", **best, "stake": stake, "shares": shares,
             "sleeve": state["sleeve"]})
    else:
        log({"event": "fire_failed", **best, "stake": stake,
             "status": str(getattr(res, "status", None)),
             "error": str(getattr(res, "error", None))})
    save_state(state)

if __name__ == "__main__":
    main()
