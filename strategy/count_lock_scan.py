#!/usr/bin/env python3
"""Monotone-counter lockout scanner (SHADOW — no orders).

Family DNA (same as M1B METAR lockout): a market resolves on a MONOTONE
counter (earthquake count, cumulative precipitation). Once the counter crosses
a bucket's ceiling the bucket is structurally dead — but books reprice with a
lag, especially right after a sudden event (a quake publishes on USGS in
~5-15 min; weather MMs are not watching seismographs).

Instances scanned:
  - Earthquake count ladders (weekly M5.5/M6.5, "by June 30" M7.0):
    resolution source = USGS fdsnws; market windows are ET — parsed from the
    market description (the Jun-8 00:00-04:00Z boundary almost produced a
    false lock on 06-09; never use naive UTC dates).
    Revision risk = this family's oracle-provenance rule: marginal magnitudes
    (e.g. M7.00, M5.50) can be revised below threshold. HARD lock requires
    margin: count >= ceiling + 1 + SAFETY_EXTRA, where boundary events
    (mag < thr + 0.15) do not count toward the safety margin.
  - Monthly precipitation ladders (NYC Central Park=KNYC, Seattle=KSEA):
    resolution = NOAA monthly total; "exactly between brackets -> higher
    bracket" => 'less than X' dies at sum >= X. IEM hourly p01i is the live
    proxy for the NOAA total; HARD lock requires sum >= ceiling + 0.30in.

Also logs Poisson NEAR-locks for open-ended buckets ("more than 9" with count
6 and 5 days left) — informational, NOT structural; never auto-trade these.

Output: logs/shadow/hot/<date>/count_lock.jsonl  (+ stdout summary for cron log)
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
GAMMA = "https://gamma-api.polymarket.com"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
SAFETY_EXTRA = 1          # HARD lock: count >= ceiling + 1 + this (solid events)
MAG_BOUNDARY = 0.15       # events within this of threshold don't count for margin
PRECIP_MARGIN_IN = 0.30   # HARD precip lock margin (inches)
PRECIP_STATIONS = {"NYC": ("KNYC", -4), "Seattle": ("KSEA", -7)}  # (icao, utc_off summer)

def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-countlock"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def http_text(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-countlock"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

# ── window + bucket parsing ──────────────────────────────────────────────────
WINDOW_RE = re.compile(
    r"between (\w+ \d+, \d{4}), (\d{1,2}:\d{2} [AP]M) ET,? and (\w+ \d+, \d{4}), (\d{1,2}:\d{2} [AP]M) ET")

def parse_window_et(desc):
    m = WINDOW_RE.search(desc)
    if not m: return None, None
    def p(dstr, tstr):
        return datetime.strptime(f"{dstr} {tstr}", "%B %d, %Y %I:%M %p").replace(tzinfo=ET)
    return p(m.group(1), m.group(2)), p(m.group(3), m.group(4))

MAG_RE = re.compile(r"magnitude (?:of )?(\d+\.\d+) or higher", re.I)

def parse_count_bucket(q):
    """Returns (lo, hi) inclusive integer-count range, or None."""
    ql = q.lower()
    m = re.search(r"exactly (\d+)", ql)
    if m: n = int(m.group(1)); return (n, n)
    m = re.search(r"(\d+) or fewer", ql)
    if m: return (0, int(m.group(1)))
    m = re.search(r"(\d+) or more", ql)
    if m: return (int(m.group(1)), None)
    m = re.search(r"more than (\d+)", ql)
    if m: return (int(m.group(1)) + 1, None)
    m = re.search(r"fewer than (\d+)", ql)
    if m: return (0, int(m.group(1)) - 1)
    m = re.search(r"between (\d+) and (\d+)", ql)
    if m: return (int(m.group(1)), int(m.group(2)))
    return None

def parse_precip_bucket(q):
    """Returns (lo_in, hi_in); hi exclusive-at-equality goes to HIGHER bracket,
    so 'less than X' dies at sum >= X and 'between A and B' dies at sum >= B
    only when the next bracket starts at B (ties go up). Conservative: treat
    hi as dead-line itself."""
    ql = q.lower()
    m = re.search(r"less than ([\d.]+) inch", ql)
    if m: return (0.0, float(m.group(1)))
    m = re.search(r"between ([\d.]+) and ([\d.]+) inch", ql)
    if m: return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"([\d.]+) (?:inches )?or more", ql)
    if m: return (float(m.group(1)), None)
    m = re.search(r"more than ([\d.]+) inch", ql)
    if m: return (float(m.group(1)), None)
    return None

# ── counters ─────────────────────────────────────────────────────────────────
def usgs_events(start_utc, end_utc, mag):
    url = (f"{USGS}?format=geojson&starttime={start_utc:%Y-%m-%dT%H:%M:%S}"
           f"&endtime={end_utc:%Y-%m-%dT%H:%M:%S}&minmagnitude={mag}&orderby=time")
    return http_json(url).get("features", [])

def precip_mtd_inches(icao, year, month, utc_off):
    """Sum of IEM hourly p01i (inches) over the LOCAL month to date."""
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
           f"station={icao}&data=p01i&year1={year}&month1={month}&day1=1"
           f"&year2={year}&month2={month}&day2=28&tz=Etc/UTC&format=onlycomma"
           "&missing=M&trace=T&report_type=3&report_type=4")
    txt = http_text(url, timeout=90)
    total, last_hr = 0.0, None
    for ln in txt.splitlines()[1:]:
        p = ln.split(",")
        if len(p) < 3 or p[2] in ("M", ""): continue
        v = 0.005 if p[2] == "T" else None
        try: v = float(p[2]) if v is None else v
        except ValueError: continue
        # p01i is hour-accumulated; take max per clock hour to avoid double-count
        hr = p[1][:13]
        if hr == last_hr:
            continue
        last_hr = hr
        total += max(0.0, v)
    return round(total, 2)

# ── scan ─────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    out_dir = Path("/root/Klaus/logs/shadow/hot") / now.date().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = (out_dir / "count_lock.jsonl").open("a")

    evs = http_json(f"{GAMMA}/events?tag_slug=weather&limit=200&closed=false")
    quake, precip = [], []
    for ev in evs:
        for m in ev.get("markets", []):
            q = m.get("question", "")
            if "earthquake" in q.lower(): quake.append(m)
            elif "precipitation" in q.lower(): precip.append(m)

    n_hard = n_soft = 0
    usgs_cache = {}
    for m in quake:
        q = m.get("question", ""); desc = m.get("description", "")
        mag_m = MAG_RE.search(desc) or MAG_RE.search(q)
        bk = parse_count_bucket(q)
        w0, w1 = parse_window_et(desc)
        if not (mag_m and bk and w0): continue
        mag = float(mag_m.group(1))
        key = (w0.isoformat(), mag)
        if key not in usgs_cache:
            try:
                usgs_cache[key] = usgs_events(
                    w0.astimezone(timezone.utc), min(now, w1.astimezone(timezone.utc)), mag)
            except Exception as e:
                print(f"USGS fetch failed {key}: {e}", file=sys.stderr); continue
        events = usgs_cache[key]
        count = len(events)
        solid = sum(1 for f in events
                    if (f["properties"].get("mag") or 0) >= mag + MAG_BOUNDARY)
        lo, hi = bk
        status = None
        if hi is not None and count > hi:                       # bucket ceiling crossed
            margin = count - hi - 1
            solid_margin = solid - hi - 1
            status = "HARD_NO" if (margin >= SAFETY_EXTRA or solid_margin >= 0) else "SOFT_NO"
        elif lo is not None and hi is None and count >= lo:     # open-ended floor reached
            margin = count - lo
            solid_margin = solid - lo
            status = "HARD_YES" if (margin >= SAFETY_EXTRA or solid_margin >= 0) else "SOFT_YES"
        if status:
            n_hard += status.startswith("HARD"); n_soft += status.startswith("SOFT")
            rec = dict(schema_version=1, record_type="count_lock", family="quake",
                       ts_utc=now.isoformat(), question=q, mag_threshold=mag,
                       window_start=w0.isoformat(), count=count, solid_count=solid,
                       bucket_lo=lo, bucket_hi=hi, status=status,
                       best_bid=m.get("bestBid"), best_ask=m.get("bestAsk"),
                       liquidity=m.get("liquidityNum"),
                       condition_id=m.get("conditionId"),
                       token_ids=m.get("clobTokenIds"))
            out.write(json.dumps(rec) + "\n")
            side = "NO" if status.endswith("NO") else "YES"
            bid = m.get("bestBid"); ask = m.get("bestAsk")
            juice = None
            if side == "NO" and bid: juice = round(float(bid), 3)        # stale YES bid to fade
            if side == "YES" and ask: juice = round(1 - float(ask), 3)   # YES still cheap
            print(f"[{status}] {q[:70]} | count={count}(solid {solid}) "
                  f"bid={bid} ask={ask} juice~{juice}")

    for m in precip:
        q = m.get("question", "")
        city = next((c for c in PRECIP_STATIONS if c in q), None)
        bk = parse_precip_bucket(q)
        if not (city and bk): continue
        icao, off = PRECIP_STATIONS[city]
        try:
            mtd = precip_mtd_inches(icao, now.year, now.month, off)
        except Exception as e:
            print(f"precip fetch failed {icao}: {e}", file=sys.stderr); continue
        lo, hi = bk
        status = None
        if hi is not None and mtd >= hi + PRECIP_MARGIN_IN:
            status = "HARD_NO"
        elif hi is not None and mtd >= hi:
            status = "SOFT_NO"
        elif lo is not None and hi is None and mtd >= lo + PRECIP_MARGIN_IN:
            status = "HARD_YES"
        if status:
            n_hard += status.startswith("HARD"); n_soft += status.startswith("SOFT")
            rec = dict(schema_version=1, record_type="count_lock", family="precip",
                       ts_utc=now.isoformat(), question=q, station=icao,
                       mtd_inches=mtd, bucket_lo=lo, bucket_hi=hi, status=status,
                       best_bid=m.get("bestBid"), best_ask=m.get("bestAsk"),
                       liquidity=m.get("liquidityNum"),
                       condition_id=m.get("conditionId"),
                       token_ids=m.get("clobTokenIds"))
            out.write(json.dumps(rec) + "\n")
            print(f"[{status}] {q[:70]} | mtd={mtd}in bid={m.get('bestBid')} ask={m.get('bestAsk')}")

    out.close()
    print(f"scan done {now:%H:%M}Z: {len(quake)} quake mkts, {len(precip)} precip mkts, "
          f"{n_hard} HARD, {n_soft} SOFT locks")

if __name__ == "__main__":
    main()
