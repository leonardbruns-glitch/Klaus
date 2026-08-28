#!/usr/bin/env python3
"""PEAKSCALP scorer v2 — survivorship-free.

v1 counted every post-t* print on the (ex-post) winner bucket as capture.
Wrong: the running max passes through lower buckets; buying "the current
running-max bucket" buys those too. v2:

  1. GATE TEST (no prints needed): for every bucket the official running max
     entered on every city-day, find the first obs time the q-table gate
     passes (q(city, month, local_hour, headroom) >= Q_GATE while run_max in
     bucket). Did that bucket win? -> realized gate WR on live 2026 data.
  2. GATED CAPTURE: prints on the gated bucket AFTER gate-pass at
     price <= q*SELL - EDGE_MIN, scored at EV = (q*SELL - p)*size (q-priced,
     not ex-post), plus ex-post for reference. Latency split after gate-pass.

Uses /tmp/peakscalp_backtest.json for ladder list (winner q/cid per city-day)
+ fresh IEM obs + data-api prints.
"""
import json, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from strategy.weather_arb import ICAO_UTC_OFFSET_H, _parse_outcome

HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
SELL = 0.999
EDGE_MIN = 0.02
Q_GATES = [0.985, 0.995]
DS = {"d02": 0.2, "d04": 0.4, "d06": 0.6, "d10": 1.0}

QTAB = json.load(open("/root/Klaus/config/peakscalp_q.json"))

def q_lookup(city, month, hour, headroom):
    cell = (QTAB.get(city, {}).get(f"m{month}", {}) or {}).get(f"h{hour}")
    if not cell:
        return None
    best = None
    for k, d in DS.items():
        if d <= headroom + 1e-9 and k in cell:
            best = cell[k] if best is None else max(best, cell[k])
    return best

def get(u, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers=HDR)
            return json.loads(urllib.request.urlopen(req, timeout=25).read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.2)

def iem_hourly(icao, d1, d2, tries=4):
    p = urllib.parse.urlencode({
        "station": icao, "data": "tmpf", "year1": d1.year, "month1": d1.month,
        "day1": d1.day, "year2": d2.year, "month2": d2.month, "day2": d2.day,
        "tz": "UTC", "format": "onlycomma", "latlon": "no", "direct": "no",
        "report_type": "2"})
    url = f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?{p}"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDR)
            raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
            break
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(8.0)
    out = []
    for ln in raw.strip().split("\n"):
        if ln.startswith("#") or ln.startswith("station"):
            continue
        parts = ln.split(",")
        if len(parts) < 3:
            continue
        try:
            ts = datetime.fromisoformat(parts[1]).replace(tzinfo=timezone.utc)
            tf = float(parts[2])
        except Exception:
            continue
        out.append((ts, (tf - 32.0) * 5.0 / 9.0))
    return sorted(out)

def main():
    rows = json.load(open("/tmp/peakscalp_backtest.json"))
    ladders = [r for r in rows if r.get("tstar")]
    print(f"city-days from v1: {len(ladders)}")

    # obs per station (re-fetch, slow but cached per station)
    obs = {}
    for icao in sorted({L["icao"] for L in ladders}):
        try:
            obs[icao] = iem_hourly(icao, datetime(2026, 5, 31), datetime(2026, 6, 11))
        except Exception as e:
            print(f"  IEM fail {icao}: {e}")
        time.sleep(2.0)
    print(f"IEM stations: {len(obs)}")

    results = {g: {"entries": 0, "wins": 0, "loss_usd_unit": 0.0,
                   "cap_ev": 0.0, "cap_expost": 0.0, "prints": 0,
                   "lat": defaultdict(float), "daily": defaultdict(float),
                   "city": defaultdict(float)} for g in Q_GATES}

    for L in ladders:
        o = obs.get(L["icao"])
        if not o or L["lo"] is None or L["hi"] is None:
            continue
        tz_h = ICAO_UTC_OFFSET_H.get(L["icao"], 0)
        width = L["hi"] - L["lo"]
        if not (0.4 <= width <= 1.3):   # °C-padded bucket width (1.0 °C / ~1.11 °F)
            continue
        day0 = datetime.fromisoformat(L["day"]).replace(tzinfo=timezone.utc) - timedelta(hours=tz_h)
        day1 = day0 + timedelta(hours=24)
        city = L["city"].replace(" ", "-")
        month = int(L["day"][5:7])

        # walk obs; track bucket index of run_max on the winner-aligned grid
        run = -999.0
        gate_pass = {g: {} for g in Q_GATES}   # bucket_idx -> (ts, q) first pass
        for ts, tc in o:
            if not (day0 <= ts < day1):
                continue
            run = max(run, tc)
            bidx = int((run - L["lo"]) // width)   # 0 = winner bucket
            b_hi = L["lo"] + (bidx + 1) * width
            headroom = b_hi - run
            lh = (ts + timedelta(hours=tz_h)).hour
            if lh < 11:
                continue
            q = q_lookup(city, month, lh, headroom)
            if q is None:
                continue
            for g in Q_GATES:
                if q >= g and bidx not in gate_pass[g]:
                    gate_pass[g][bidx] = (ts, q)
        final_bidx = 0  # winner bucket by construction
        for g in Q_GATES:
            for bidx, (ts, q) in gate_pass[g].items():
                R = results[g]
                R["entries"] += 1
                if bidx == final_bidx:
                    R["wins"] += 1
                else:
                    R["loss_usd_unit"] += 1.0   # unit-stake loss counter

        # prints for the winner bucket (bidx 0) after gate pass
        need = any(0 in gate_pass[g] for g in Q_GATES)
        if not need:
            continue
        prints = []
        off = 0
        while True:
            try:
                tr = get(f"https://data-api.polymarket.com/trades?market={L['cid']}&limit=500&offset={off}")
            except Exception:
                break
            if not tr:
                break
            prints.extend(tr)
            if len(tr) < 500 or off > 4000:
                break
            off += 500
            time.sleep(0.12)
        for g in Q_GATES:
            if 0 not in gate_pass[g]:
                continue
            t_gate, q_gate_val = gate_pass[g][0]
            tg = int(t_gate.timestamp())
            R = results[g]
            for x in prints:
                try:
                    px, sz = float(x["price"]), float(x["size"])
                    ts_p = int(x["timestamp"])
                except Exception:
                    continue
                if x.get("outcome") != "Yes" or x.get("side") != "BUY":
                    continue
                if ts_p < tg:
                    continue
                cap_px = q_gate_val * SELL - EDGE_MIN
                if px > cap_px:
                    continue
                ev = (q_gate_val * SELL - px) * sz
                R["cap_ev"] += ev
                R["cap_expost"] += (SELL - px) * sz
                R["prints"] += 1
                R["daily"][L["day"]] += ev
                R["city"][L["city"]] += ev
                dt_s = ts_p - tg
                for lo_s, hi_s, lbl in ((0, 300, "0-5m"), (300, 900, "5-15m"),
                                        (900, 3600, "15-60m"), (3600, 10**9, ">60m")):
                    if lo_s <= dt_s < hi_s:
                        R["lat"][lbl] += ev
        time.sleep(0.1)

    for g in Q_GATES:
        R = results[g]
        n, w = R["entries"], R["wins"]
        print(f"\n=== Q_GATE {g} ===")
        print(f"gate entries {n}, wins {w}, realized WR {w/max(1,n):.4f} "
              f"(table predicts >= {g})")
        print(f"gated capture: EV ${R['cap_ev']:.2f} | ex-post ${R['cap_expost']:.2f} "
              f"| prints {R['prints']}")
        nd = len(R["daily"]) or 1
        print(f"per-day EV: ${R['cap_ev']/nd:.2f}/day over {len(R['daily'])} days")
        print("latency after gate-pass:", {k: round(v, 2) for k, v in sorted(R["lat"].items())})
        top = sorted(R["city"].items(), key=lambda kv: -kv[1])[:8]
        print("top cities:", [(c, round(v, 2)) for c, v in top])
    json.dump({str(g): {k: (dict(v) if isinstance(v, defaultdict) else v)
                        for k, v in R.items()} for g, R in results.items()},
              open("/tmp/peakscalp_v2.json", "w"), default=str)
    print("\nwrote /tmp/peakscalp_v2.json")

if __name__ == "__main__":
    main()
