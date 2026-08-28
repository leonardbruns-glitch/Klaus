#!/usr/bin/env python3
"""YES-CAPTURE shadow analyzer (2026-06-23) — reads the read.

Consumes reason=yes_capture_shadow rows (logged by the band cycle, no capital) and
answers the two questions that decide whether we can re-enable YES:

  (1) WR-bid  (bucket edge): do the d+2 0.10-0.45 buckets WE select resolve YES at a
      rate >= our would_quote?  edge = WR - would_quote, by price-zone & offset.
      This is the spread-capture edge ASSUMING neutral fills. Resolution via gamma
      (closed=true, outcomePrices) — same source as band_resolution_join.py.

  (2) Markout (adverse fill): reconstruct would-be fills from the token's public trade
      tape — any SELL printing <= would_quote after our snapshot ts = a would-be fill;
      measure the price drift to the LAST trade before resolution. Positive = clean
      (price rose after our buy), negative = adverse (we'd be run over). Best-effort:
      if the trades endpoint is unavailable, (1) still reports.

Run on the VPS (gamma 403s cloud IPs). n>=100 resolved before any decision.
DECISION GATE (to re-enable YES per the phasing plan): WR-bid edge > 0 AND markout
not adverse (>= ~0) at n>=100 in the 0.10-0.45 zone. Else stay NO-only.
"""
import json, glob, urllib.request, urllib.parse, time, collections, statistics as st

W_TRADES = "https://data-api.polymarket.com/trades"
GAMMA = "https://gamma-api.polymarket.com/markets"


def get(url):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            time.sleep(0.6)
    return None


def winner(op):
    """outcomePrices -> 1 if YES won, 0 if NO won, None if unresolved/ambiguous."""
    try:
        p = json.loads(op) if isinstance(op, str) else op
        y = float(p[0])
        if y > 0.99:
            return 1
        if y < 0.01:
            return 0
    except Exception:
        pass
    return None


# ---- load shadow rows, dedup to first snapshot per token ----
rows = {}
# 2026-07-04 EVOLVE fix: relative glob returned 0 files under cron (cwd=/root,
# not /root/Klaus) — analyzer reported "0 snapshots" for 3 days while the shadow
# logged 30-85 rows/day. Absolute path, cwd-independent.
for f in sorted(glob.glob("/root/Klaus/logs/shadow/hot/2026-*/band_struct.jsonl")):
    for l in open(f):
        try:
            r = json.loads(l)
        except Exception:
            continue
        if r.get("reason") != "yes_capture_shadow":
            continue
        tok = r.get("token")
        if tok and (tok not in rows or r["ts"] < rows[tok]["ts"]):
            rows[tok] = r
shadows = list(rows.values())
print(f"yes_capture_shadow snapshots (deduped per token): {len(shadows)}")
if not shadows:
    print("no data yet — accruing. re-run after a few days."); raise SystemExit

# ---- resolution join (batch cids) ----
cids = sorted({r["cid"] for r in shadows if r.get("cid")})
res = {}
for i in range(0, len(cids), 50):
    q = "&".join(f"condition_ids={c}" for c in cids[i:i + 50])
    d = get(f"{GAMMA}?{q}&closed=true&limit=200")
    for m in (d or []):
        res[m.get("conditionId")] = winner(m.get("outcomePrices"))

resolved = [r for r in shadows if res.get(r["cid"]) is not None]
print(f"resolved: {len(resolved)} / {len(shadows)}")


def zone(px):
    return ("0.10-0.20" if px < 0.20 else "0.20-0.30" if px < 0.30
            else "0.30-0.45")


def report_wr(rs, label):
    if not rs:
        print(f"  {label:14} n=0"); return
    wr = sum(res[r["cid"]] == 1 for r in rs) / len(rs)
    q = st.mean(float(r["would_quote"]) for r in rs)
    # dedup-ROI: win pays $1/share, cost = would_quote
    roi = (wr - q) / q if q > 0 else 0.0
    print(f"  {label:14} n={len(rs):4} WR={wr:.3f} would_quote={q:.3f} "
          f"edge={100*(wr-q):+.2f}pp ROI={100*roi:+.1f}%")


print("\n=== (1) WR-bid by PRICE ZONE (best_ask) ===")
for z in ("0.10-0.20", "0.20-0.30", "0.30-0.45"):
    report_wr([r for r in resolved if zone(float(r["best_ask"])) == z], z)
report_wr(resolved, "ALL 0.10-0.45")
print("\n=== WR-bid by OFFSET from mode ===")
byoff = collections.defaultdict(list)
for r in resolved:
    byoff[r.get("off")].append(r)
for off in sorted(k for k in byoff if k is not None):
    report_wr(byoff[off], f"off={off:+d}")

# ---- (2) markout via tape (best-effort) ----
print("\n=== (2) MARKOUT — would-be fills reconstructed from trade tape ===")
mk, filled = [], 0
for r in resolved[:400]:   # cap network
    cid = r["cid"]; q = float(r["would_quote"]); t0 = r["ts"]
    d = get(f"{W_TRADES}?market={cid}&limit=500")
    if not isinstance(d, list) or not d:
        continue
    trs = sorted((t for t in d
                  if t.get("asset") == r["token"]
                  and str(t.get("side", "")).upper() == "SELL"
                  and t.get("timestamp", 0) >= t0
                  and float(t.get("price", 9) or 9) <= q + 1e-9),
                 key=lambda t: t["timestamp"])
    if not trs:
        continue
    filled += 1
    # markout = (last pre-resolution trade price on this token) - would_quote
    last = sorted((t for t in d if t.get("asset") == r["token"]),
                  key=lambda t: t["timestamp"])[-1]
    mk.append(float(last.get("price", q)) - q)
if mk:
    mk.sort()
    print(f"  would-be fills reconstructed: {filled} (of {min(len(resolved),400)} probed)")
    print(f"  markout (last_px - would_quote): med={st.median(mk):+.4f} "
          f"mean={st.mean(mk):+.4f}  adverse(<0)={100*sum(1 for x in mk if x<0)/len(mk):.0f}%")
else:
    print("  no tape markout (endpoint empty/unavailable) — rely on WR-bid above")

print("\nGATE: re-enable YES only if WR-bid edge>0 AND markout not adverse at n>=100.")
