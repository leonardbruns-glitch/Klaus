"""
Taker-trade harvester for weather TEMPERATURE markets (read-only, no capital).

Goal ([[project_mm_fingerprint_metagame]] pivot): reverse-engineer the active TAKERS.
data-api /trades.proxyWallet == the taker, and each record carries outcome (Yes/No),
side, price, size, ts, and wallet name. We harvest resolved temp markets, join Gamma
resolution, and compute per-trade MARK-TO-RESOLUTION PnL so we can profile who wins,
who loses systematically, and who trades mechanically.

mark-to-resolution PnL per trade (held to resolution; sums correctly over buy+sell):
  token_won = 1 if (outcome==Yes & yes_res>=.99) or (outcome==No & yes_res<=.01) else 0
  BUY :  pnl = size * (token_won - price)
  SELL:  pnl = size * (price - token_won)
This values a wallet's NET flow at resolution — a clean skill proxy (caveat: positions
opened before our window add noise; averages out for high-volume wallets).

Run: python3 analysis/weather/taker_harvest.py [date_min] [date_max] [max_markets]
Out: data/taker_trades.parquet
"""
from __future__ import annotations
import sys, json, time, urllib.request
import pandas as pd

sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events, parse_weather_question

DATE_MIN = sys.argv[1] if len(sys.argv) > 1 else "2026-05-15"
DATE_MAX = sys.argv[2] if len(sys.argv) > 2 else "2026-05-29"
MAX_MARKETS = int(sys.argv[3]) if len(sys.argv) > 3 else 600
PAGE_CAP = 2500          # max trades/market
OUT = f"data/taker_trades_{DATE_MIN}_{DATE_MAX}.parquet"


def get(url):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "k"}), timeout=25).read())


def all_trades(cid):
    out = []
    for off in range(0, PAGE_CAP, 500):
        try:
            r = get(f"https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}")
        except Exception:
            break
        if not r:
            break
        out += r
        if len(r) < 500:
            break
        time.sleep(0.03)
    return out


def main():
    print(f"fetching Gamma weather resolution {DATE_MIN}..{DATE_MAX} ...")
    _tok, cond = fetch_weather_events(DATE_MIN, DATE_MAX)

    temp_cids = []
    for cid, e in cond.items():
        q = (e.get("question") or "").lower()
        if "temperature in" not in q:
            continue
        p = e.get("outcomePrices") or []
        try:
            y = float(p[0])
        except Exception:
            continue
        if e.get("closed") and (y >= 0.99 or y <= 0.01):
            temp_cids.append(cid)
    print(f"resolved TEMP markets: {len(temp_cids)} (harvesting up to {MAX_MARKETS})")

    rows = []
    for i, cid in enumerate(temp_cids[:MAX_MARKETS]):
        e = cond[cid]
        yes_res = float(e["outcomePrices"][0])
        meta = parse_weather_question(e.get("question", ""))
        city = meta.get("weather_city")
        date = meta.get("weather_date")
        lo_c = meta.get("weather_threshold_lo_c_padded")
        hi_c = meta.get("weather_threshold_hi_c_padded")
        unit = meta.get("weather_unit")
        btype = meta.get("weather_bucket_type")
        for t in all_trades(cid):
            try:
                price = float(t.get("price")); size = float(t.get("size"))
            except Exception:
                continue
            outcome = t.get("outcome")            # 'Yes' / 'No'
            if outcome not in ("Yes", "No"):
                continue
            side = t.get("side")                  # 'BUY' / 'SELL'
            token_won = 1.0 if ((outcome == "Yes" and yes_res >= 0.99) or
                                (outcome == "No" and yes_res <= 0.01)) else 0.0
            pnl = size * (token_won - price) if side == "BUY" else size * (price - token_won)
            ts = int(t.get("timestamp") or 0)
            rows.append({
                "wallet": (t.get("proxyWallet") or "").lower(),
                "name": t.get("name") or t.get("pseudonym") or "",
                "side": side, "outcome": outcome, "outcome_idx": t.get("outcomeIndex"),
                "price": price, "size": size, "notional": price * size,
                "ts": ts, "hour_utc": time.gmtime(ts).tm_hour if ts else -1,
                "cid": cid, "city": city, "date": date,
                "bucket_lo_c": lo_c, "bucket_hi_c": hi_c, "unit": unit, "btype": btype,
                "yes_res": yes_res, "token_won": token_won, "pnl_m2r": pnl,
            })
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{min(MAX_MARKETS,len(temp_cids))} markets | {len(rows):,} trades")

    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}: {len(df):,} trades | {df.wallet.nunique():,} takers | "
          f"{df.cid.nunique()} markets | {df.city.nunique()} cities | "
          f"dates {df.date.min()}..{df.date.max()}")
    print(f"side: {df.side.value_counts().to_dict()}")
    print(f"net mark-to-res PnL across all takers: ${df.pnl_m2r.sum():,.0f} "
          f"(should be ~ -fees/spread paid to MMs; sign sanity)")


if __name__ == "__main__":
    main()
