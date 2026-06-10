#!/usr/bin/env python3
"""Quantify the MINT-AND-DUMP primitive on locked buckets.

Primitive: split $1 -> YES+NO, sell the doomed YES into the stale bid (taker),
hold the certain NO to batch resolution (local midnight +0.6-1.6h).
Economically identical to buying NO at (1 - yes_bid) -- but executable when the
NO side has NO ask at all (the one-sided-book slice our buy-NO lockout cannot touch).

Data: logs/shadow/hot/<date>/metar_lockout.jsonl (schema 2) -- every record is a
bucket whose broad-feed running_max passed the padded ceiling, with full 3-level
YES+NO CLOB books.

Caveats handled:
  - record's running_max_c is the BROAD feed (NMS/SYNOP included), not official-only
    -> require margin >= MARGIN_MIN_C (default 1.0C) and exclude wrong-oracle ICAOs.
  - fill_path in the log references the stale Gamma bid; we recompute from raw books.
  - stale bids persist across snapshots -> capacity per (token,day) = MAX single-
    snapshot harvest (conservative), plus a replenishment upper bound.

Outputs per-day capacity of: buy-NO path, mint-dump path, and the MINT-ONLY slice
(YES bid >= BID_FLOOR present while zero NO-ask profit at the same snapshot).
"""
import json, glob, sys
from collections import defaultdict

MARGIN_MIN_C = 1.0          # broad-feed margin proxy for "official lockout"
BID_FLOOR    = 0.01         # YES bid levels below this: fee/dust, ignore
NO_ASK_MAX   = 0.99         # buy-NO profit only counts from asks <= this
FEE_BASE     = 0.05         # taker fee ~ FEE_BASE * p * (1-p) per share (1.25% peak)
BLOCK_ICAO   = {"ZGSZ"}     # wrong-oracle (Shenzhen 27% match). VHHH reported separately.

def fee(p, size):
    return FEE_BASE * p * (1.0 - p) * size

def snap_metrics(r):
    yb = (r.get("yes_book") or {}).get("bids") or []
    na = (r.get("no_book") or {}).get("asks") or []
    nb = (r.get("no_book") or {}).get("bids") or []
    # mint-dump: revenue = sum b*size - fee, capital = shares * $1
    mint_net, mint_sh = 0.0, 0.0
    for lvl in yb:
        b, s = float(lvl["price"]), float(lvl["size"])
        if b < BID_FLOOR:
            continue
        mint_net += b * s - fee(b, s)
        mint_sh  += s
    # buy-NO: profit = (1-a)*size for asks <= NO_ASK_MAX
    no_profit, no_cost = 0.0, 0.0
    for lvl in na:
        a, s = float(lvl["price"]), float(lvl["size"])
        if a > NO_ASK_MAX:
            continue
        no_profit += (1.0 - a) * s - fee(a, s)
        no_cost   += a * s
    # split-sell both legs (zero-capital arb): pair depth at top of book
    arb = 0.0
    if yb and nb:
        b1, bs = float(yb[0]["price"]), float(yb[0]["size"])
        n1, ns = float(nb[0]["price"]), float(nb[0]["size"])
        edge = b1 + n1 - 1.0 - FEE_BASE * (b1*(1-b1) + n1*(1-n1))
        if edge > 0 and b1 >= BID_FLOOR:
            arb = edge * min(bs, ns)
    return mint_net, mint_sh, no_profit, no_cost, arb

def main():
    files = sorted(glob.glob("/root/Klaus/logs/shadow/hot/*/metar_lockout.jsonl"))
    # per (token, end_date): track peaks
    tok = {}
    n_rows = n_used = 0
    for fp in files:
        day = fp.split("/")[-2]
        with open(fp) as f:
            for line in f:
                n_rows += 1
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("record_type") != "metar_lockout_candidate":
                    continue
                hi = r.get("bucket_hi_c_padded")
                rm = r.get("running_max_c")
                if hi is None or rm is None or (rm - hi) < MARGIN_MIN_C:
                    continue
                if r.get("icao") in BLOCK_ICAO:
                    continue
                n_used += 1
                mint, msh, nop, noc, arb = snap_metrics(r)
                key = (r["token_id"], r.get("end_date") or day)
                t = tok.setdefault(key, {
                    "city": r.get("city"), "icao": r.get("icao"), "day": day,
                    "q": (r.get("question") or "")[:70],
                    "mint_max": 0.0, "mint_sh_at_max": 0.0,
                    "no_max": 0.0, "arb_max": 0.0,
                    "mint_only_max": 0.0,      # best mint harvest while NO path = $0
                    "mint_incr_max": 0.0,      # best (mint - no) when mint beats no
                    "snaps": 0, "mint_prev": 0.0, "mint_replen": 0.0,
                    "margin_max": 0.0, "first_ts": r.get("ts_utc"),
                })
                t["snaps"] += 1
                t["margin_max"] = max(t["margin_max"], rm - hi)
                if mint > t["mint_max"]:
                    t["mint_max"], t["mint_sh_at_max"] = mint, msh
                t["no_max"] = max(t["no_max"], nop)
                t["arb_max"] = max(t["arb_max"], arb)
                if nop <= 0.0 and mint > t["mint_only_max"]:
                    t["mint_only_max"] = mint
                if mint - nop > t["mint_incr_max"]:
                    t["mint_incr_max"] = mint - nop
                # replenishment upper bound: sum of increases in snapshot harvest
                if mint > t["mint_prev"]:
                    t["mint_replen"] += mint - t["mint_prev"]
                t["mint_prev"] = mint

    print(f"rows={n_rows} used(margin>={MARGIN_MIN_C}C, ex-{','.join(BLOCK_ICAO)})={n_used} "
          f"token-days={len(tok)}")

    per_day = defaultdict(lambda: defaultdict(float))
    vhhh_mint = 0.0
    for (tid, ed), t in tok.items():
        d = t["day"]
        if t["icao"] == "VHHH":
            vhhh_mint += t["mint_only_max"]
            continue
        per_day[d]["mint"] += t["mint_max"]
        per_day[d]["mint_only"] += t["mint_only_max"]
        per_day[d]["mint_incr"] += max(0.0, t["mint_incr_max"])
        per_day[d]["no"] += t["no_max"]
        per_day[d]["arb"] += t["arb_max"]
        per_day[d]["replen"] += t["mint_replen"]

    print("\nday          buyNO$  mint$  mintONLY$  mintINCR$  splitarb$  replenUB$")
    tots = defaultdict(float)
    for d in sorted(per_day):
        v = per_day[d]
        print(f"{d}  {v['no']:7.2f} {v['mint']:7.2f} {v['mint_only']:9.2f} "
              f"{v['mint_incr']:9.2f} {v['arb']:9.2f} {v['replen']:9.2f}")
        for k in v: tots[k] += v[k]
    nd = max(1, len(per_day))
    print(f"AVG/day      {tots['no']/nd:7.2f} {tots['mint']/nd:7.2f} "
          f"{tots['mint_only']/nd:9.2f} {tots['mint_incr']/nd:9.2f} "
          f"{tots['arb']/nd:9.2f} {tots['replen']/nd:9.2f}")
    print(f"VHHH (HK, oracle=HKO since 06-09) mint_only total excluded above: ${vhhh_mint:.2f}")

    # top token-days by mint-only harvest
    rows = sorted(tok.items(), key=lambda kv: -kv[1]["mint_only_max"])[:15]
    print("\nTOP mint-ONLY token-days (harvest unreachable by buy-NO):")
    print("city            day        net$   shares$1cap  margin  snaps  question")
    for (tid, ed), t in rows:
        if t["mint_only_max"] <= 0: break
        print(f"{t['city']:<15} {t['day']}  {t['mint_only_max']:6.2f}  "
              f"{t['mint_sh_at_max']:8.0f}    {t['margin_max']:5.2f}  {t['snaps']:5d}  {t['q']}")

    # dump per-token-day table for resolution join
    out = "/tmp/mint_dump_tokendays.json"
    with open(out, "w") as f:
        json.dump([{ "token_id": tid, "end_date": ed, **{k: v for k, v in t.items()
                     if k not in ("mint_prev",)}} for (tid, ed), t in tok.items()], f)
    print(f"\nwrote {out} ({len(tok)} token-days) for resolution join")

if __name__ == "__main__":
    main()
