"""
Dense-observation forecast-edge VALIDATION (Stage-1 gate).

Thesis: the market prices a city's daily max off ONE official station + public NWP.
A dense network of nearby stations (Synoptic/MADIS mesonet) carries information about
the air mass that the single station misses. If, at a PRE-PEAK time t, the dense
network predicts the OFFICIAL station's eventual daily max better than the official
station's own reading at t, then dense obs are a proprietary forecast input.

This is a resolution-grounded backtest (target = official station's realized daily max),
read-only, no capital. Gate: if dense features cut leave-one-out MAE of the remaining
rise materially below the official-only baseline → proceed to Stage-2 (vs market price).

Run: python3 -m analysis.weather.dense_obs_validate
"""
from __future__ import annotations
import os, json, time, math, urllib.request, urllib.parse
from collections import defaultdict
from datetime import datetime, timezone

KEY = ""
for _l in open("/root/Klaus/.env"):
    if _l.startswith("SYNOPTIC_API_KEY="):
        KEY = _l.strip().split("=", 1)[1]

# (city, official STID, lat, lon) — COASTAL / complex-terrain: where the single
# official station mis-represents the air mass (sea-breeze, microclimates) = the
# only place dense obs can physically add beyond the official station.
CITIES = [
    ("san-francisco", "KSFO", 37.62, -122.37),
    ("los-angeles",   "KLAX", 33.94, -118.41),
    ("san-diego",     "KSAN", 32.73, -117.18),
    ("seattle",       "KSEA", 47.44, -122.31),
    ("miami",         "KMIA", 25.79, -80.29),
]
RADIUS_MI   = 20
HISTORY_DAYS = 12
PREPEAK_HOUR_UTC = 16   # ~late-morning/noon local for these cities → clearly pre-peak

def fetch_city(lat, lon):
    end = time.strftime("%Y%m%d%H%M", time.gmtime())
    start = time.strftime("%Y%m%d%H%M", time.gmtime(time.time() - HISTORY_DAYS * 86400))
    params = {"token": KEY, "radius": f"{lat},{lon},{RADIUS_MI}", "start": start, "end": end,
              "vars": "air_temp", "obtimezone": "utc", "units": "temp|C", "limit": "50"}
    url = "https://api.synopticdata.com/v2/stations/timeseries?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "klaus"}), timeout=40) as r:
        return json.loads(r.read())

def series(stn):
    obs = stn.get("OBSERVATIONS", {}) or {}
    dts = obs.get("date_time") or []
    tmp = obs.get("air_temp_set_1") or []
    out = []
    for d, t in zip(dts, tmp):
        if t is None: continue
        try: ts = datetime.fromisoformat(d.replace("Z", "+00:00")).timestamp()
        except Exception: continue
        out.append((ts, float(t)))
    out.sort()
    return out

def temp_at(s, target_ts, tol=2400):
    """nearest obs within tol seconds"""
    best = None
    for ts, t in s:
        dt = abs(ts - target_ts)
        if dt <= tol and (best is None or dt < best[0]): best = (dt, t)
    return best[1] if best else None

def day_max(s, day0, day1):
    vals = [t for ts, t in s if day0 <= ts < day1]
    return max(vals) if vals else None

rows = []  # (city, off_t, net_max_t, net_mean_t, net_p90_t, net_spread, target)
for city, stid, lat, lon in CITIES:
    try:
        d = fetch_city(lat, lon)
    except Exception as e:
        print(f"  {city}: fetch failed {e}"); continue
    stns = d.get("STATION", [])
    off = next((series(s) for s in stns if s.get("STID") == stid), None)
    others = [series(s) for s in stns if s.get("STID") != stid]
    others = [s for s in others if len(s) >= 12]
    if not off or len(others) < 5:
        print(f"  {city}: official={'ok' if off else 'MISSING'} dense_n={len(others)} — skip"); continue
    # iterate days (UTC midnights)
    now = time.time()
    for k in range(1, HISTORY_DAYS):
        day0 = (int(now // 86400) - k) * 86400
        day1 = day0 + 86400
        t_pre = day0 + PREPEAK_HOUR_UTC * 3600
        target = day_max(off, day0, day1)
        off_t  = temp_at(off, t_pre)
        if target is None or off_t is None: continue
        net = [temp_at(s, t_pre) for s in others]
        net = [x for x in net if x is not None]
        if len(net) < 5: continue
        net.sort()
        net_max = net[-1]; net_mean = sum(net) / len(net)
        net_p90 = net[int(0.9 * (len(net) - 1))]; net_spread = net[-1] - net[0]
        # only keep genuine pre-peak rows (official still climbs to target)
        if target - off_t < 0.3:  # already at/past peak by t_pre → not a pre-peak forecast row
            continue
        rows.append((city, off_t, net_max, net_mean, net_p90, net_spread, target, day0))
    print(f"  {city}: usable pre-peak day-rows so far = {sum(1 for r in rows if r[0]==city)}")

print(f"\n=== Dense-obs validation: n={len(rows)} city-days ===")
if len(rows) < 10:
    print("insufficient rows — widen history/cities"); raise SystemExit

# remaining rise = target - off_t  (what NWP/the market must forecast)
def mae(pred, tgt): return sum(abs(p - g) for p, g in zip(pred, tgt)) / len(pred)

# per-city demeaning to remove station-level offsets (compare SIGNAL not level)
import statistics as st
cmean = defaultdict(list)
for r in rows: cmean[r[0]].append(r)

# Feature matrix: predict remaining_rise from network signals (net_max-off, net_mean-off, spread)
# Baseline = city-mean remaining rise (best you can do w/o the network: climatology).
# Leave-one-out: does adding network features beat the climatology baseline OOS?
def loo_mae(feat_fn):
    preds, gts = [], []
    for i, r in enumerate(rows):
        city = r[0]; rr_i = r[6] - r[1]
        train = [x for j, x in enumerate(rows) if j != i and x[0] == city]
        if len(train) < 4:
            train = [x for j, x in enumerate(rows) if j != i]
        Y = [x[6] - x[1] for x in train]              # remaining rise
        X = [feat_fn(x) for x in train]
        # simple 1-feature OLS through demeaned: rr = a + b*feat
        mx = sum(X)/len(X); my = sum(Y)/len(Y)
        cov = sum((x-mx)*(y-my) for x, y in zip(X, Y)); var = sum((x-mx)**2 for x in X) or 1e-9
        b = cov/var; a = my - b*mx
        pred = a + b*feat_fn(r)
        preds.append(r[1] + pred); gts.append(r[6])   # predicted daily max
    return mae(preds, gts)

# baseline: climatology remaining rise (city mean), no network
def base_mae():
    preds, gts = [], []
    for i, r in enumerate(rows):
        city = r[0]
        train = [x for j, x in enumerate(rows) if j != i and x[0] == city]
        if not train: train = [x for j, x in enumerate(rows) if j != i]
        rr = sum(x[6]-x[1] for x in train)/len(train)
        preds.append(r[1] + rr); gts.append(r[6])
    return mae(preds, gts)

b0 = base_mae()
m_netmax = loo_mae(lambda r: r[2]-r[1])    # net_max − official
m_netmean= loo_mae(lambda r: r[3]-r[1])    # net_mean − official
m_p90    = loo_mae(lambda r: r[4]-r[1])    # net_p90 − official
m_spread = loo_mae(lambda r: r[5])         # network spread
# correlation of best signal w/ remaining rise
RR = [r[6]-r[1] for r in rows]; SIG = [r[2]-r[1] for r in rows]
mr, ms = sum(RR)/len(RR), sum(SIG)/len(SIG)
cov = sum((a-mr)*(b-ms) for a,b in zip(RR,SIG)); sr=math.sqrt(sum((a-mr)**2 for a in RR)); ss=math.sqrt(sum((b-ms)**2 for b in SIG))
corr = cov/(sr*ss) if sr*ss>0 else 0
print(f"mean remaining rise (off_t→peak): {st.mean(RR):.2f}°C  (this is what NWP/market forecast)")
print(f"corr(net_max−off, remaining_rise): {corr:+.2f}")
print(f"\nLeave-one-out daily-max MAE (lower = better):")
print(f"  baseline (climatology rise, NO network): {b0:.3f}°C")
print(f"  + net_max−off feature:                   {m_netmax:.3f}°C   ({100*(b0-m_netmax)/b0:+.1f}%)")
print(f"  + net_mean−off feature:                  {m_netmean:.3f}°C   ({100*(b0-m_netmean)/b0:+.1f}%)")
print(f"  + net_p90−off feature:                   {m_p90:.3f}°C   ({100*(b0-m_p90)/b0:+.1f}%)")
print(f"  + network spread feature:                {m_spread:.3f}°C   ({100*(b0-m_spread)/b0:+.1f}%)")
best = min(m_netmax, m_netmean, m_p90, m_spread)
print(f"\nvs CLIMATOLOGY: dense best = {100*(b0-best)/b0:+.1f}% MAE")

# ── THE REAL GATE: vs NWP (what the market actually uses) ──────────────────────
COORD = {c: (lat, lon) for c, stid, lat, lon in CITIES}
def fetch_nwp(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&daily=temperature_2m_max&past_days=14&forecast_days=1&timezone=UTC")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "klaus"}), timeout=30) as r:
        j = json.loads(r.read())
    dd = j.get("daily", {}); return {d: m for d, m in zip(dd.get("time", []), dd.get("temperature_2m_max", [])) if m is not None}
nwp_map = {}
for c, stid, lat, lon in CITIES:
    try: nwp_map[c] = fetch_nwp(lat, lon)
    except Exception as e: nwp_map[c] = {}
def datestr(d0): return time.strftime("%Y-%m-%d", time.gmtime(d0))
rn = [(r, nwp_map.get(r[0], {}).get(datestr(r[7]))) for r in rows]
rn = [(r, n) for r, n in rn if n is not None]
print(f"\n=== THE REAL GATE — vs NWP (the market's input), n={len(rn)} ===")
if len(rn) >= 10:
    import numpy as np
    def loo_multi(feat_fns):
        preds, gts = [], []
        for i, (r, n) in enumerate(rn):
            tr = [(rr, nn) for j, (rr, nn) in enumerate(rn) if j != i]
            X = np.array([[f(rr, nn) for f in feat_fns] + [1.0] for rr, nn in tr])
            Y = np.array([rr[6] for rr, nn in tr])
            coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
            x = np.array([f(r, n) for f in feat_fns] + [1.0])
            preds.append(float(x @ coef)); gts.append(r[6])
        return mae(preds, gts)
    nwp_only   = mae([n for r, n in rn], [r[6] for r, n in rn])
    F_nwp      = [lambda r, n: n]                                  # blind NWP
    F_market   = [lambda r, n: n, lambda r, n: r[1]]              # NWP + official current temp (the MARKET's nowcast)
    F_dense    = [lambda r, n: n, lambda r, n: r[1],
                  lambda r, n: r[4], lambda r, n: r[2], lambda r, n: r[5]]  # + net_p90, net_max, spread
    m_nwp = loo_multi(F_nwp); m_mkt = loo_multi(F_market); m_dns = loo_multi(F_dense)
    print(f"  NWP blind forecast:                 {nwp_only:.3f}°C")
    print(f"  NWP (LOO-recalibrated):             {m_nwp:.3f}°C")
    print(f"  NWP + official current temp = MARKET:{m_mkt:.3f}°C   <- the real baseline")
    print(f"  MARKET + dense network:             {m_dns:.3f}°C   ({100*(m_mkt-m_dns)/m_mkt:+.1f}% vs market)")
    edge = m_dns < m_mkt - 0.03
    print(f"\n*** VERDICT: beyond (NWP + official nowcast), dense obs "
          f"{'ADD edge → worth building' if edge else 'add little — the official single-station nowcast already captures it; marginal'} "
          f"({100*(m_mkt-m_dns)/m_mkt:+.1f}%) ***")
else:
    print("  NWP join too thin — inconclusive")
