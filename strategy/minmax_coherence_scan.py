#!/usr/bin/env python3
"""Min/max cross-book coherence scanner (SHADOW — READ-ONLY, no order path).

H48/H61 validator (docs/MARKET_VULNERABILITY_MAP.md). Daily-MIN temperature
ladders exist on Polymarket but the live engine ingests zero of them
(discovery hardwired to 'highest-temperature'). MIN and MAX ladders for the
same city-day resolve on the same temperature path, so in rounded-degree
space (resolution rounds to whole degrees, and round(min) <= round(max)):

    {round(max) >= t}  UNION  {round(min) <= t-1}  =  EVERYTHING
    (if max < t then min <= max <= t-1)

so for any integer t aligned to bucket boundaries of BOTH ladders, buying the
YES spanning set of max-buckets >= t plus the YES spanning set of
min-buckets <= t-1 pays AT LEAST $1 per unit (possibly $2 if both true).
Total best-ask cost < $1 = model-free coherence violation — the cross-event
generalization of NEG_RISK_ARB. Nobody quotes the two books jointly.

Per (city, date) pair this logs:
  1. COVERAGE ARB: min over aligned t of the two-set cost; HARD < 0.97
     (fee+slip buffer), SOFT < 1.00. Per-leg asks + fillable units recorded.
  2. MIN-LADDER Σask: within-event neg-risk sum on the min event (the live
     NEG_RISK_ARB never sees these books).
  3. MIN-LOCKOUT METER (today, city-local, only): running-min from Open-Meteo
     (PROXY obs — model blend, NOT the official METAR oracle; capacity survey
     only, never a trading signal) -> buckets physically NO-dead, best NO ask
     and $ depth within 5c. Margin = 0.5 rounding + ~0.5C proxy buffer
     (1.0 native deg C, 1.4 deg F).
  4. BID-INCOHERENCE diagnostic: max over t of Sigma-bids on the two
     mutually-exclusive sets {max<t}, {min>=t} minus 1 (books jointly
     claiming an impossibility; not directly executable, logged only).

Output: logs/shadow/hot/<UTC-date>/minmax_coherence.jsonl (one record per
city-date per run; runs are snapshots, joined later) + stdout cron summary.
No bot state touched. No orders. Same family directive as count_lock_scan:
SHADOW ONLY until user instruction.
"""
import json, re, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.load(open(ROOT / "config/stwa_params.json"))["stations"]
# wrong-oracle blocklist mirrors current M1B census (06-09): HKO / Shenzhen
ORACLE_BLOCK = {"hong-kong", "shenzhen"}
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
HARD_COST, SOFT_COST = 0.97, 1.00
UA = {"User-Agent": "klaus-minmax-coherence"}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _city_slug(title):
    try:
        s = title.split(" in ")[1].split(" on ")[0].strip().lower().replace(" ", "-")
        return s
    except Exception:
        return None


def _date_from_title(title):
    m = re.search(r" on (\w+) (\d+)", title)
    if not m:
        return None
    try:
        mon = datetime.strptime(m.group(1)[:3], "%b").month
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    year = now.year
    # cross-year guard (December titles scanned in January etc.)
    if mon == 12 and now.month == 1:
        year -= 1
    elif mon == 1 and now.month == 12:
        year += 1
    return f"{year:04d}-{mon:02d}-{int(m.group(2)):02d}"


def parse_bucket(q):
    """(lo, hi, unit) in rounded-integer space; hi/lo None = open end."""
    ql = q.lower()
    m = re.search(r"(-?\d+)\s*°\s*([cf])\s*or below", ql)
    if m:
        return None, int(m.group(1)), m.group(2)
    m = re.search(r"(-?\d+)\s*°\s*([cf])\s*or (?:above|higher)", ql)
    if m:
        return int(m.group(1)), None, m.group(2)
    m = re.search(r"(?:between )?(-?\d+)\s*(?:°\s*[cf]?\s*)?(?:-|–|to|and)\s*(-?\d+)\s*°\s*([cf])", ql)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    m = re.search(r"be (-?\d+)\s*°\s*([cf])\b", ql)
    if m:
        return int(m.group(1)), int(m.group(1)), m.group(2)
    return None


def ladder(event):
    """Parse one event -> sorted [{lo,hi,yes_tok,question}], unit, contiguous?"""
    rows, units = [], set()
    for mkt in event.get("markets", []) or []:
        if mkt.get("closed"):
            continue
        b = parse_bucket(mkt.get("question", ""))
        if not b:
            continue
        lo, hi, unit = b
        units.add(unit)
        toks = mkt.get("clobTokenIds")
        toks = json.loads(toks) if isinstance(toks, str) else (toks or [])
        rows.append({"lo": lo, "hi": hi, "yes_tok": toks[0] if toks else None,
                     "question": mkt.get("question", "")})
    if not rows or len(units) != 1:
        return None, None, False
    rows.sort(key=lambda r: (-1e9 if r["lo"] is None else r["lo"]))
    contig = all(rows[i]["hi"] is not None and rows[i + 1]["lo"] == rows[i]["hi"] + 1
                 for i in range(len(rows) - 1))
    return rows, units.pop(), contig


def book(token_id):
    """(best_ask, ask_units_within_5c, best_bid, bid_usd_within_5c) of YES book."""
    try:
        b = _get(f"{CLOB}/book?token_id={token_id}")
    except Exception:
        return None, 0.0, None, 0.0
    asks = [(float(l["price"]), float(l["size"])) for l in (b.get("asks") or [])]
    bids = [(float(l["price"]), float(l["size"])) for l in (b.get("bids") or [])]
    ba, au, bb, bu = None, 0.0, None, 0.0
    if asks:
        ba = min(p for p, _ in asks)
        au = sum(s for p, s in asks if p - ba <= 0.05)
    if bids:
        bb = max(p for p, _ in bids)
        bu = sum(p * s for p, s in bids if bb - p <= 0.05)
    return ba, au, bb, bu


def _utc_offset(lat, lon):
    """Station UTC offset (s) via Open-Meteo timezone=auto (offset ONLY —
    never temps: 06-10 verification showed gridpoint temps run 1-2C below
    official METARs and manufacture false locks, the M1B bug class)."""
    u = (f"https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lon:.3f}"
         f"&timezone=auto")
    return int(_get(u).get("utc_offset_seconds", 0))


def running_min_today(icao, lat, lon, local_date):
    """OFFICIAL running-min (deg C) for the station-local calendar day from
    AWC METARs/SPECIs — the same provenance rule as the resolution oracle.
    Returns (rmin_c, set_local_hour) or (None, None)."""
    off = _utc_offset(lat, lon)
    local_now = datetime.now(timezone.utc) + timedelta(seconds=off)
    if local_now.strftime("%Y-%m-%d") != local_date:
        return None, None  # market date is not "today" at the station
    d = _get(f"https://aviationweather.gov/api/data/metar?ids={icao}"
             f"&hours=36&format=json")
    temps = []
    for m in d:
        v = m.get("temp")
        ts = m.get("reportTime") or m.get("receiptTime")
        if v is None or not ts:
            continue
        try:
            utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        loc = utc + timedelta(seconds=off)
        if loc.strftime("%Y-%m-%d") == local_date:
            temps.append((loc.hour, float(v)))
    if not temps:
        return None, None
    rmin = min(v for _, v in temps)
    rhr = min(temps, key=lambda x: x[1])[0]
    return rmin, rhr


def coverage_scan(max_rows, min_rows):
    """All aligned t: cost of YES{max>=t} + YES{min<=t-1}. Needs books loaded.

    Guarantee requires the selected buckets to cover [t,inf) and (-inf,t-1]
    EXACTLY, so the ladders must be contiguous (checked by caller) AND
    open-ended at the relevant edge: max ladder needs an 'or above' top
    (hi None), min ladder an 'or below' bottom (lo None).
    """
    if not any(r["hi"] is None for r in max_rows):
        return []
    if not any(r["lo"] is None for r in min_rows):
        return []
    max_lo = {r["lo"] for r in max_rows if r["lo"] is not None}
    min_hi = {r["hi"] for r in min_rows if r["hi"] is not None}
    out = []
    for t in sorted(max_lo):
        if (t - 1) not in min_hi:
            continue
        # {max >= t}: buckets entirely at/above t (incl. open-top, lo>=t)
        legs_max = [r for r in max_rows if r["lo"] is not None and r["lo"] >= t]
        # {min <= t-1}: buckets entirely at/below t-1 (incl. open-bottom, hi<=t-1)
        legs_min = [r for r in min_rows if r["hi"] is not None and r["hi"] <= t - 1]
        legs = legs_max + legs_min
        if any(r["ask"] is None for r in legs):
            continue
        cost = sum(r["ask"] for r in legs)
        units = min(r["ask_units"] for r in legs)
        # bid-side incoherence on the complements {max<t}, {min>=t}
        comp = [r for r in max_rows if r["hi"] is not None and r["hi"] <= t - 1] + \
               [r for r in min_rows if r["lo"] is not None and r["lo"] >= t]
        bid_sum = sum(r["bid"] for r in comp if r["bid"] is not None)
        out.append({"t": t, "cost": round(cost, 4), "n_legs": len(legs),
                    "units_fillable": round(units, 1),
                    "legs": [{"q": r["question"][-40:], "ask": r["ask"]} for r in legs],
                    "comp_bid_sum": round(bid_sum, 4)})
    return out


def main():
    now = datetime.now(timezone.utc)
    outdir = ROOT / "logs/shadow/hot" / now.date().isoformat()
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "minmax_coherence.jsonl"

    search = _get(f"{GAMMA}/public-search?q=lowest+temperature&limit_per_type=60")
    min_events = [e for e in search.get("events", []) if not e.get("closed")
                  and "lowest temperature" in e.get("title", "").lower()]
    print(f"[{now:%Y-%m-%d %H:%M}Z] open daily-MIN events: {len(min_events)}")

    summary = []
    for ev in min_events:
        title = ev.get("title", "")
        city = _city_slug(title)
        date = _date_from_title(title)
        if not city or not date:
            continue
        st = PARAMS.get(city)
        min_rows, unit, contig = ladder(ev)
        if not min_rows:
            print(f"  {title:<48} — ladder parse failed, skip")
            continue

        # matching MAX event by slug swap, else by search fallback
        max_event = None
        slug = ev.get("slug", "")
        if slug.startswith("lowest-"):
            try:
                hits = _get(f"{GAMMA}/events?slug={slug.replace('lowest', 'highest', 1)}")
                if hits:
                    max_event = hits[0]
            except Exception:
                pass
        max_rows = max_unit = None
        max_contig = False
        if max_event and not max_event.get("closed"):
            max_rows, max_unit, max_contig = ladder(max_event)

        # books (YES side; NO derived by mirror)
        for r in min_rows + (max_rows or []):
            r["ask"], r["ask_units"], r["bid"], r["bid_usd"] = \
                (book(r["yes_tok"]) if r["yes_tok"] else (None, 0.0, None, 0.0))
            time.sleep(0.04)

        min_sum_ask = (round(sum(r["ask"] for r in min_rows), 4)
                       if all(r["ask"] is not None for r in min_rows) else None)

        cov = []
        if max_rows and unit == max_unit and contig and max_contig:
            cov = coverage_scan(max_rows, min_rows)
        best = min(cov, key=lambda c: c["cost"]) if cov else None

        # min-lockout meter (today only, proxy obs, oracle-clean cities only)
        lock = None
        if st and city not in ORACLE_BLOCK:
            try:
                rmin_c, rhr = running_min_today(st["icao"], st["lat"], st["lon"], date)
            except Exception:
                rmin_c, rhr = None, None
            if rmin_c is not None:
                is_f = st.get("unit", "C") == "F"
                rmin_native = rmin_c * 9 / 5 + 32 if is_f else rmin_c
                # official obs: 0.5 rounding + 0.1C buffer (1.1F)
                margin = 1.1 if is_f else 0.6
                dead = []
                for r in min_rows:
                    if r["lo"] is not None and r["lo"] - rmin_native >= margin:
                        no_ask = round(1 - r["bid"], 3) if r["bid"] is not None else None
                        dead.append({"lo": r["lo"], "hi": r["hi"], "no_ask": no_ask,
                                     "no_usd": round(r["bid_usd"], 2)})
                lock = {"obs_src": "AWC-METAR", "rmin_c": round(rmin_c, 1),
                        "set_local_hr": rhr, "n_dead": len(dead),
                        "dead_no_usd": round(sum(d["no_usd"] for d in dead), 2),
                        "dead": dead}

        rec = {"ts": now.isoformat(timespec="seconds"), "city": city, "date": date,
               "unit": unit, "title": title, "has_max_pair": bool(max_rows),
               "min_ladder_n": len(min_rows), "min_sum_ask": min_sum_ask,
               "coverage_best": best, "coverage_all": cov, "min_lockout": lock,
               "oracle_blocked": city in ORACLE_BLOCK}
        with open(outfile, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

        flag = ""
        if best and best["cost"] < HARD_COST:
            flag = f"  *** HARD COVERAGE ARB cost={best['cost']} t={best['t']} ***"
        elif best and best["cost"] < SOFT_COST:
            flag = f"  [soft arb cost={best['cost']} t={best['t']}]"
        if min_sum_ask is not None and min_sum_ask < 0.85:
            flag += f"  *** MIN NEGRISK Σask={min_sum_ask} ***"
        lk = (f" lock:{lock['n_dead']}bkt ${lock['dead_no_usd']:.0f}" if lock else "")
        print(f"  {city:<14} {date} pair={'Y' if max_rows else 'n'} "
              f"Σask_min={min_sum_ask} best_cov={best['cost'] if best else '—'}{lk}{flag}")
        summary.append((city, date, best["cost"] if best else None,
                        lock["dead_no_usd"] if lock else 0.0))

    tot_lock = sum(s[3] for s in summary)
    n_cov = sum(1 for s in summary if s[2] is not None and s[2] < SOFT_COST)
    print(f"  == pairs={len(summary)}  soft/hard coverage arbs={n_cov}  "
          f"locked-min NO depth=${tot_lock:.0f}")


if __name__ == "__main__":
    main()
