"""Resolution-bias backtest — is Polymarket weather resolution the max of routine
HOURLY METARs (≈1°F below the true diurnal peak), and does the book overprice the
physical-peak bin?

THESIS (from a 2026-06-02 n=12 probe): resolution = WU daily high = max of routine
hourly METAR obs, which misses the between-ob peak → sits ~1°F below the ASOS
period max (the 4-group / what forecasts show). On ~50% of US city-days that puts
the resolved bin one 2°F-bin BELOW the physical-peak bin. If the market prices on
the physical peak, the peak-bin is systematically overpriced.

Reuses backtest.discover_resolved + attach_entry_prices for the market side
(buckets, winner, CLOB price history). Adds the METAR side from the Iowa State
Mesonet archive (historical raw METARs incl. the 1-group/4-group remark groups).

Routine-hourly isolation: Mesonet returns 5-minute ASOS obs too; the OFFICIAL
hourly METARs (what WU/resolution sees) carry an SLP group in RMK — 5-min obs do
not. We take routine obs only (and SPECIs, which also carry richer RMK).

Modes:
  --validate   reproduce known AWC values for a few city-days (parser check)
  --mechanism  join to Gamma resolution; resolution=hourly confirm rate, gap, cross
  --ev         + attach CLOB entry prices; EV of fade-peak-bin / buy-hourly-bin

Usage (run on VPS):
  PYTHONPATH=/root/Klaus python3 -m analysis.weather.resolution_bias_backtest --validate
  PYTHONPATH=/root/Klaus python3 -m analysis.weather.resolution_bias_backtest --mechanism --days 45
  PYTHONPATH=/root/Klaus python3 -m analysis.weather.resolution_bias_backtest --ev --days 45
"""
from __future__ import annotations
import argparse, json, re, statistics, time, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from analysis.weather.stations import STATIONS

UA = {"User-Agent": "Klaus-WeatherBot/1.0 resbias"}
MESO = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"


def cToF(c): return c * 9 / 5 + 32


# ---------- Mesonet historical METARs ----------

def fetch_metars(icao: str, d0: date, d1: date) -> list[tuple[datetime, str]]:
    """Raw METARs for icao over UTC [d0, d1). Mesonet station id = icao minus K (US)."""
    mid = icao[1:] if (icao.startswith("K") and len(icao) == 4) else icao
    time.sleep(5.0)  # Mesonet rate-limits (HTTP 429) — throttle between pulls
    url = (f"{MESO}?station={mid}&data=metar&tz=Etc/UTC&format=comma&latlon=no&missing=M"
           f"&year1={d0.year}&month1={d0.month}&day1={d0.day}"
           f"&year2={d1.year}&month2={d1.month}&day2={d1.day}")
    try:
        txt = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()
    except Exception as e:
        print(f"  mesonet fetch err {icao}: {str(e)[:60]}")
        return []
    out = []
    for line in txt.splitlines():
        if line.startswith("#") or line.startswith("station,") or not line.strip():
            continue
        parts = line.split(",", 2)
        if len(parts) < 3:
            continue
        try:
            t = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append((t, parts[2]))
    return out


def _T(raw):
    m = re.search(r" T([01])(\d{3})([01])(\d{3})", raw)
    return (-1 if m.group(1) == '1' else 1) * int(m.group(2)) / 10.0 if m else None


def _G4(raw):
    m = re.search(r" 4([01])(\d{3})([01])(\d{3})", raw)
    return (-1 if m.group(1) == '1' else 1) * int(m.group(2)) / 10.0 if m else None


def day_maxes(metars, tz: str, day: date, unit: str):
    """(hourly_max, period_max) in market unit for local `day`.
    hourly_max = max routine-hourly METAR temp (SLP-bearing obs only, ≈ resolution).
    period_max = max 24h-max group (4-group) reported just after local midnight."""
    z = ZoneInfo(tz) if tz else timezone.utc
    lo = datetime(day.year, day.month, day.day, tzinfo=z).astimezone(timezone.utc)
    hi = lo + timedelta(hours=24)
    by_hour = {}
    g4 = []
    for t, raw in metars:
        if lo <= t < hi and (" SLP" in raw) and (_T(raw) is not None):
            by_hour[t.hour] = _T(raw)          # routine hourly ob (latest in hour)
        if hi <= t < hi + timedelta(hours=6):  # 4-group at local midnight
            v = _G4(raw)
            if v is not None:
                g4.append(v)
    if not by_hour:
        return None, None
    hmax_c = max(by_hour.values())
    pmax_c = max(g4) if g4 else hmax_c
    conv = cToF if unit == "F" else (lambda c: c)
    return conv(hmax_c), conv(pmax_c)


def round_bin(val_unit: float, unit: str):
    """Map a market-unit temperature to its bucket key (matches Polymarket bins)."""
    r = round(val_unit)
    if unit == "F":
        return (r // 2) * 2  # 2°F bins keyed by their even floor: 92,93 -> 92
    return r                  # 1°C bins


# ---------- validate ----------

def cmd_validate():
    # Known AWC values: KMIA 5/31 h93/p95, 6/1 h92/p94 ; KAUS 5/31 h89/p90
    cases = [("miami", "KMIA", date(2026, 5, 31)), ("miami", "KMIA", date(2026, 6, 1)),
             ("austin", "KAUS", date(2026, 5, 31)), ("chicago", "KORD", date(2026, 6, 1)),
             ("houston", "KIAH", date(2026, 6, 1))]
    for slug, icao, day in cases:
        st = STATIONS.get(slug)
        tz = getattr(st, "tz", "") if st else ""
        ms = fetch_metars(icao, day, day + timedelta(days=2))
        h, p = day_maxes(ms, tz, day, "F")
        print(f"{slug:<9} {day} icao={icao} tz={tz}  hourly_max={h}F  period_max(4grp)={p}F  n_metars={len(ms)}")


# ---------- mechanism + EV ----------

def _load_market(slug, days):
    from analysis.weather.backtest import discover_resolved
    return discover_resolved(slug, days)


def cmd_run(days: int, do_ev: bool, cities: list[str]):
    from analysis.weather.backtest import attach_entry_prices
    rows = []           # per resolved city-day
    for slug in cities:
        st = STATIONS.get(slug)
        if not st or getattr(st, "unit", "") != "F":
            continue
        try:
            mkts = _load_market(slug, days)
        except Exception as e:
            print(f"  discover err {slug}: {str(e)[:60]}")
            continue
        if not mkts:
            continue
        if do_ev:
            try:
                attach_entry_prices(mkts)
            except Exception as e:
                print(f"  prices err {slug}: {str(e)[:60]}")
        # one Mesonet pull covering all the days for this city
        days_set = sorted({m.valid_day for m in mkts})
        d_lo = min(days_set); d_hi = max(days_set) + timedelta(days=2)
        ms = fetch_metars(st.icao, d_lo, d_hi)
        for m in mkts:
            winner = next((b for b in m.buckets if b.is_winner), None)
            if winner is None:
                continue
            h, p = day_maxes(ms, getattr(st, "tz", ""), m.valid_day, "F")
            if h is None:
                continue
            hbin, pbin = round_bin(h, "F"), round_bin(p, "F")
            # winner bin key from its bounds (lo_inclusive is even floor for 2F bins)
            wlo = winner.lo_inclusive
            wbin = None if wlo in (float("-inf"),) else int((round(wlo) // 2) * 2)
            rows.append({"city": slug, "day": m.valid_day.isoformat(),
                         "hourly": h, "period": p, "gap": round(p - h, 2),
                         "hbin": hbin, "pbin": pbin, "wbin": wbin,
                         "winner_label": winner.label, "cross": hbin != pbin,
                         "win_is_h": wbin == hbin, "win_is_p": wbin == pbin,
                         "buckets": m.buckets})
    _report(rows, do_ev)


def _report(rows, do_ev):
    n = len(rows)
    if not n:
        print("no joined city-days"); return
    closed = [r for r in rows if r["wbin"] is not None]  # exclude open-ended tail winners
    gaps = [r["gap"] for r in rows]
    cross = [r for r in rows if r["cross"]]
    print(f"\n=== MECHANISM (n={n} resolved city-days; {len(closed)} closed-bin winners) ===")
    print(f"gap (period-hourly): mean={statistics.mean(gaps):+.2f}F med={statistics.median(gaps):+.2f}F max={max(gaps):+.1f}F")
    print(f"bin-cross (period vs hourly differ): {len(cross)}/{n} = {100*len(cross)/n:.0f}%")
    if closed:
        wh = sum(r["win_is_h"] for r in closed); wp = sum(r["win_is_p"] for r in closed)
        print(f"resolution == hourly-max bin: {wh}/{len(closed)} = {100*wh/len(closed):.0f}%")
        print(f"resolution == period-max bin: {wp}/{len(closed)} = {100*wp/len(closed):.0f}%")
        cc = [r for r in closed if r["cross"]]
        if cc:
            wch = sum(r["win_is_h"] for r in cc)
            print(f"  on CROSS days (n={len(cc)}): winner==hourly-bin {wch}/{len(cc)} = {100*wch/len(cc):.0f}%  "
                  f"(==period-bin {sum(r['win_is_p'] for r in cc)}/{len(cc)})")
    if not do_ev:
        return
    # EV: on cross days, buy YES on the hourly-bin at its entry price; compare to
    # buying YES on the period (physical-peak) bin. PnL/$1: win→(1-price), lose→-price.
    def bin_entry(r, binkey):
        for b in r["buckets"]:
            blo = b.lo_inclusive
            if blo == float("-inf"):
                continue
            if int((round(blo) // 2) * 2) == binkey and b.entry_price is not None:
                return b.entry_price, b.entry_ts
        return None, None

    # entry timing: local hour of the period-bin entry (post-peak ⇒ fade is executable)
    from zoneinfo import ZoneInfo as _ZI
    ent_hours = []
    for r in [r for r in rows if r["cross"] and r["wbin"] is not None]:
        _, ets = bin_entry(r, r["pbin"])
        if ets:
            tzn = getattr(STATIONS.get(r["city"]), "tz", "") or "UTC"
            ent_hours.append(datetime.fromtimestamp(ets, _ZI(tzn)).hour)
    if ent_hours:
        import collections as _c
        post = sum(1 for h in ent_hours if h >= 17 or h <= 3)  # after ~peak (incl. evening/overnight)
        print(f"\nperiod-bin entry local-hour: median={statistics.median(ent_hours)} "
              f"post-peak(>=17 or <=3): {post}/{len(ent_hours)} = {100*post/len(ent_hours):.0f}%  "
              f"hist={dict(sorted(_c.Counter(ent_hours).items()))}")
    ev_h, ev_p, fade_no, pbin_px = [], [], [], []
    for r in [r for r in rows if r["cross"] and r["wbin"] is not None]:
        ph, _ = bin_entry(r, r["hbin"]); pp, _ = bin_entry(r, r["pbin"])
        if ph is not None:
            ev_h.append((1 - ph) if r["win_is_h"] else (-ph))
        if pp is not None:
            ev_p.append((1 - pp) if r["win_is_p"] else (-pp))      # buy period-bin YES
            pbin_px.append(pp)
            no_cost = 1.0 - pp                                      # buy period-bin NO ≈ 1-yes
            fade_no.append((1 - no_cost) if (not r["win_is_p"]) else (-no_cost))
    print(f"\n=== EV on CROSS days (per $1 stake, entry @ first-trade+5min; ~0 fees) ===")
    if ev_h:
        print(f"buy HOURLY-bin YES : n={len(ev_h)} WR={100*sum(x>0 for x in ev_h)/len(ev_h):.0f}% "
              f"meanEV={statistics.mean(ev_h):+.3f} total={sum(ev_h):+.2f}")
    if ev_p:
        print(f"buy PERIOD-bin YES : n={len(ev_p)} WR={100*sum(x>0 for x in ev_p)/len(ev_p):.0f}% "
              f"meanEV={statistics.mean(ev_p):+.3f}  (mean YES entry px={statistics.mean(pbin_px):.3f})")
    if fade_no:
        print(f"FADE PERIOD-bin NO : n={len(fade_no)} WR={100*sum(x>0 for x in fade_no)/len(fade_no):.0f}% "
              f"meanEV={statistics.mean(fade_no):+.3f} total={sum(fade_no):+.2f}  <-- the thesis edge")
    print("(period-bin YES entry px = the size of the mispricing; fade-NO meanEV>0 ⇒ real edge)")


US_DEFAULT = ["miami", "dallas", "houston", "austin", "chicago", "atlanta",
              "losangeles", "phoenix", "nyc", "denver", "seattle", "boston"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--mechanism", action="store_true")
    ap.add_argument("--ev", action="store_true")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--cities", default=",".join(US_DEFAULT))
    a = ap.parse_args()
    if a.validate:
        cmd_validate()
    else:
        cmd_run(a.days, a.ev, [c.strip() for c in a.cities.split(",") if c.strip()])
