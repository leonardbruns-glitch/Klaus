"""ROLE-MISPRICE — cross-bucket persistent misallocation by bucket ROLE vs ACTUAL
resolution (READ-ONLY). NOT event-driven.

For each resolved city-day:
  - rank buckets by REAL market YES price (entry-price = CLOB history at
    first_trade + 5min, the standing pre-convergence price).
  - assign ROLES:
      FAVORITE      = argmax price
      2ND_FAV       = 2nd-highest price
      MODE_MINUS_1  = the priced neighbor one degree BELOW the price-mode bucket
      MODE_PLUS_1   = the priced neighbor one degree ABOVE the price-mode bucket
      NEAR_TAIL     = buckets 2-3 degrees from the mode (either side)
      FAR_TAIL      = buckets >=4 degrees from the mode (incl open-ended ends)
    (MODE = the price-argmax bucket = FAVORITE. The +/-1 / near / far are by
     integer-degree distance of bucket center from the mode center.)

Per role, across ALL resolved city-days:
  1. realized WR vs market-implied price (= mean entry price) -> role MISPRICE
     (= WR - mean_price), and NET EV/contract of trading the role
     (buy if underpriced, sell if overpriced) after the prob-weighted taker fee.
  2. persistence: same-sign misprice across cities + split-half (even/odd day
     index) -> STRUCTURAL role bias, independent of the favorite-longshot
     price band effect.
  3. control for price band: bin each (role, observation) by price band and
     report the WITHIN-BAND role residual (role mean misprice minus the band's
     own mean misprice) -> isolates a role effect from a pure price-band effect.
  4. capacity + n per role.

    PYTHONPATH=/root/Klaus python3 analysis/weather/role_misprice.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.stations import STATIONS
from strategy.fee_model import taker_fee_rate

DAYS_BACK = 12
MIN_PX, MAX_PX = 0.01, 0.99   # tradeable / non-degenerate quote band
PRICE_BANDS = [(0.00, 0.02), (0.02, 0.05), (0.05, 0.10),
               (0.10, 0.20), (0.20, 0.40), (0.40, 1.00)]

# Cities with no/contaminated oracle or known station mismatch — exclude from
# resolution-truth analysis (per CLAUDE.md / state log).
BLOCK_CITIES = {"hong-kong"}


def band_of(px):
    for lo, hi in PRICE_BANDS:
        if lo <= px < hi:
            return (lo, hi)
    return (0.40, 1.00)


def bucket_center_deg(b):
    """Integer-degree center of a bucket in market unit. Open-ended buckets get
    a sentinel one step beyond the finite extreme (handled by caller via
    distance ranking)."""
    lo, hi = b.lo_inclusive, b.hi_exclusive
    if lo == float("-inf"):
        return ("open_lo", hi)        # below everything
    if hi == float("inf"):
        return ("open_hi", lo)        # above everything
    return ("mid", 0.5 * (lo + hi))


def collect():
    """Return list of city-day dicts with priced buckets (real CLOB + Gamma res)."""
    cities = [c for c in STATIONS if c not in BLOCK_CITIES]
    out = []
    for c in cities:
        try:
            ms = discover_resolved(c, DAYS_BACK)
        except Exception as e:
            print(f"  discover {c}: {str(e)[:50]}", file=sys.stderr)
            continue
        if not ms:
            continue
        try:
            attach_entry_prices(ms)
        except Exception as e:
            print(f"  attach {c}: {str(e)[:50]}", file=sys.stderr)
            continue
        for m in ms:
            # priced, non-degenerate buckets only
            pb = []
            for b in m.buckets:
                if b.entry_price is None:
                    continue
                if not (MIN_PX <= b.entry_price <= MAX_PX):
                    continue
                pb.append(b)
            if len(pb) < 4:
                continue
            # exactly one winner among ALL buckets (clean resolution)
            winners = [b for b in m.buckets if b.is_winner]
            if len(winners) != 1:
                continue
            out.append({"city": c, "day": m.valid_day, "unit": m.unit,
                        "priced": pb, "winner": winners[0]})
        print(f"  {c}: {sum(1 for x in out if x['city']==c)} clean city-days",
              file=sys.stderr)
    return out


def assign_roles(cd):
    """Assign one role per priced bucket. Returns list of obs dicts:
       {role, price, won, city, day, center_kind, deg_dist}"""
    pb = cd["priced"]
    # rank by price desc
    ranked = sorted(pb, key=lambda b: b.entry_price, reverse=True)
    fav = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    # mode center = favorite center (use finite center; if fav open-ended, use its finite edge)
    fk, fc = bucket_center_deg(fav)
    mode_center = fc  # numeric anchor

    obs = []
    for b in pb:
        kind, cen = bucket_center_deg(b)
        # degree distance from mode center
        if kind == "mid":
            dist = abs(cen - mode_center)
        else:
            # open-ended: treat as just beyond the finite extreme -> large dist
            # but if the favorite itself is this open bucket, dist 0
            dist = abs(cen - mode_center)
        # signed distance (for +1 / -1 discrimination); use center diff
        signed = cen - mode_center

        # role assignment priority: FAVORITE / 2ND_FAV by rank; else by degree distance
        if b is fav:
            role = "FAVORITE"
        elif second is not None and b is second:
            role = "2ND_FAV"
        else:
            # by degree distance to the price-mode bucket
            d = round(dist)
            if d <= 0:
                role = "MODE_PM1"          # same center as mode but not fav/2nd (rare ties)
            elif d == 1:
                role = "MODE_PLUS_1" if signed > 0 else "MODE_MINUS_1"
            elif d in (2, 3):
                role = "NEAR_TAIL"
            else:
                role = "FAR_TAIL"
            # open-ended buckets that are far -> FAR_TAIL regardless
            if kind in ("open_lo", "open_hi") and d >= 2:
                role = "FAR_TAIL"
        obs.append({
            "role": role, "price": b.entry_price, "won": bool(b.is_winner),
            "city": cd["city"], "day": cd["day"], "unit": cd["unit"],
            "deg_signed": signed, "kind": kind,
        })
    return obs


def role_stats(rows):
    if not rows:
        return None
    px = np.array([r["price"] for r in rows])
    won = np.array([1.0 if r["won"] else 0.0 for r in rows])
    wr = won.mean()
    mean_px = px.mean()
    misprice = wr - mean_px      # >0 = underpriced (buy), <0 = overpriced (sell)
    # NET EV/contract: trade in the misprice direction, prob-weighted taker fee.
    # BUY YES: EV = (won - price) - fee(price);  SELL YES (=buy NO at 1-price):
    #   EV = ((1-won) - (1-price)) - fee(1-price) = (price - won) - fee(1-price)
    ev_buy = won - px - np.array([taker_fee_rate(p) for p in px])
    ev_sell = px - won - np.array([taker_fee_rate(1.0 - p) for p in px])
    # choose the side matching the misprice sign (the actionable side)
    if misprice >= 0:
        side, ev = "BUY", ev_buy
    else:
        side, ev = "SELL", ev_sell
    return {
        "n": len(rows), "wr": float(wr), "mean_price": float(mean_px),
        "misprice": float(misprice), "side": side,
        "net_ev": float(ev.mean()),
        "net_ev_buy": float(ev_buy.mean()), "net_ev_sell": float(ev_sell.mean()),
        "ev_se": float(ev.std(ddof=1) / np.sqrt(len(rows))) if len(rows) > 1 else float("nan"),
    }


def main():
    print("collecting resolved city-days (real CLOB + Gamma resolution)...",
          file=sys.stderr)
    cds = collect()
    print(f"\nTOTAL clean resolved city-days: {len(cds)}", file=sys.stderr)
    if not cds:
        print("NO DATA"); return

    # assign a stable day-index per city for split-half (even/odd of sorted days)
    all_obs = []
    for cd in cds:
        all_obs.extend(assign_roles(cd))

    ROLES = ["FAVORITE", "2ND_FAV", "MODE_PLUS_1", "MODE_MINUS_1",
             "NEAR_TAIL", "FAR_TAIL", "MODE_PM1"]

    by_role = defaultdict(list)
    for o in all_obs:
        by_role[o["role"]].append(o)

    print(f"\nTotal priced bucket-observations: {len(all_obs)}")
    print(f"City-days: {len(cds)}  | cities: {len({cd['city'] for cd in cds})}")

    # ---- 1. per-role misprice + net EV ----
    print("\n================= (1) PER-ROLE MISPRICE + NET EV/CONTRACT =================")
    print(f"{'role':<14}{'n':>6}{'mean_px':>10}{'WR':>9}{'misprice':>11}"
          f"{'side':>6}{'net_EV':>10}{'EV_se':>9}")
    role_summ = {}
    for role in ROLES:
        st = role_stats(by_role[role])
        if st is None:
            continue
        role_summ[role] = st
        print(f"{role:<14}{st['n']:>6}{st['mean_price']:>10.3f}{st['wr']:>9.3f}"
              f"{st['misprice']:>+11.3f}{st['side']:>6}{st['net_ev']:>+10.4f}"
              f"{st['ev_se']:>9.4f}")

    # ---- 2. persistence: split-half (even/odd day) + per-city sign agreement ----
    print("\n================= (2) PERSISTENCE (structural, not noise) =================")
    # day index per city
    city_days = defaultdict(set)
    for cd in cds:
        city_days[cd["city"]].add(cd["day"])
    day_rank = {}
    for c, days in city_days.items():
        for i, d in enumerate(sorted(days)):
            day_rank[(c, d)] = i

    print(f"{'role':<14}{'misprice_all':>14}{'half_even':>11}{'half_odd':>11}"
          f"{'same_sign':>11}{'cities+':>9}{'cities-':>9}{'city_consistency':>18}")
    persist = {}
    for role in ROLES:
        rows = by_role[role]
        if len(rows) < 20:
            continue
        even = [r for r in rows if day_rank[(r["city"], r["day"])] % 2 == 0]
        odd = [r for r in rows if day_rank[(r["city"], r["day"])] % 2 == 1]
        m_all = role_stats(rows)["misprice"]
        m_e = role_stats(even)["misprice"] if even else float("nan")
        m_o = role_stats(odd)["misprice"] if odd else float("nan")
        same = (np.sign(m_e) == np.sign(m_o)) and not (np.isnan(m_e) or np.isnan(m_o))
        # per-city misprice sign
        pc = defaultdict(list)
        for r in rows:
            pc[r["city"]].append(r)
        signs = []
        for c, rr in pc.items():
            if len(rr) < 3:
                continue
            signs.append(np.sign(role_stats(rr)["misprice"]))
        cpos = sum(1 for s in signs if s > 0)
        cneg = sum(1 for s in signs if s < 0)
        consistency = max(cpos, cneg) / len(signs) if signs else float("nan")
        persist[role] = {"m_all": m_all, "m_even": m_e, "m_odd": m_o,
                         "same_sign": bool(same), "cities_pos": cpos,
                         "cities_neg": cneg, "consistency": consistency}
        print(f"{role:<14}{m_all:>+14.3f}{m_e:>+11.3f}{m_o:>+11.3f}"
              f"{str(bool(same)):>11}{cpos:>9}{cneg:>9}{consistency:>18.2f}")

    # ---- 3. control for price band: within-band role residual ----
    print("\n================= (3) ROLE EFFECT CONTROLLING FOR PRICE BAND =================")
    print("within-band role residual = role's misprice in a band MINUS that band's overall misprice")
    # band-level misprice baseline (all roles pooled)
    band_rows = defaultdict(list)
    for o in all_obs:
        band_rows[band_of(o["price"])].append(o)
    band_misprice = {}
    for bnd, rows in band_rows.items():
        st = role_stats(rows)
        band_misprice[bnd] = st["misprice"] if st else float("nan")
    print(f"  band baseline misprice (FLB control): "
          + "  ".join(f"[{b[0]:.2f},{b[1]:.2f})={band_misprice[b]:+.3f}(n={len(band_rows[b])})"
                      for b in PRICE_BANDS if b in band_misprice))

    print(f"\n{'role':<14}{'band':<14}{'n':>6}{'mean_px':>9}{'WR':>8}"
          f"{'role_mp':>9}{'band_mp':>9}{'residual':>10}")
    role_resid = defaultdict(list)   # role -> list of (residual, n)
    for role in ROLES:
        for bnd in PRICE_BANDS:
            rr = [o for o in by_role[role] if band_of(o["price"]) == bnd]
            if len(rr) < 8:
                continue
            st = role_stats(rr)
            resid = st["misprice"] - band_misprice.get(bnd, 0.0)
            role_resid[role].append((resid, len(rr)))
            print(f"{role:<14}[{bnd[0]:.2f},{bnd[1]:.2f})  {st['n']:>6}"
                  f"{st['mean_price']:>9.3f}{st['wr']:>8.3f}{st['misprice']:>+9.3f}"
                  f"{band_misprice.get(bnd,0.0):>+9.3f}{resid:>+10.3f}")

    print("\n  n-weighted MEAN within-band residual per role (structural role bias after FLB control):")
    for role in ROLES:
        lst = role_resid.get(role)
        if not lst:
            continue
        w = sum(n for _, n in lst)
        wr_resid = sum(r * n for r, n in lst) / w
        print(f"    {role:<14} residual={wr_resid:+.4f}  (n={w}, bands={len(lst)})")

    # ---- 4. capacity per role ----
    print("\n================= (4) CAPACITY PER ROLE =================")
    # capacity proxy: per-role mean price * typical fillable shares.
    # We don't have live depth here; report n city-days, n obs, mean price,
    # and frequency (obs per city-day) so capacity can be reasoned about.
    n_cd = len(cds)
    print(f"{'role':<14}{'n_obs':>8}{'obs/cityday':>13}{'mean_px':>10}{'n_cities':>10}")
    for role in ROLES:
        rows = by_role[role]
        if not rows:
            continue
        ncit = len({r["city"] for r in rows})
        print(f"{role:<14}{len(rows):>8}{len(rows)/n_cd:>13.2f}"
              f"{np.mean([r['price'] for r in rows]):>10.3f}{ncit:>10}")

    # ---- machine-readable dump ----
    dump = {
        "n_city_days": len(cds),
        "n_cities": len({cd["city"] for cd in cds}),
        "roles": role_summ,
        "persistence": persist,
        "band_baseline_misprice": {f"{b[0]:.2f}-{b[1]:.2f}": band_misprice.get(b)
                                   for b in PRICE_BANDS},
        "within_band_residual": {role: (sum(r*n for r,n in lst)/sum(n for _,n in lst)
                                        if (lst:=role_resid.get(role)) else None)
                                 for role in ROLES},
    }
    with open("/tmp/role_misprice_out.json", "w") as f:
        json.dump(dump, f, indent=2, default=str)
    print("\n[dump] /tmp/role_misprice_out.json")


if __name__ == "__main__":
    main()
