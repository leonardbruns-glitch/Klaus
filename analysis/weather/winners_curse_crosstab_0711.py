#!/usr/bin/env python3
"""Winner's-curse cross-tab (exec-audit alert, 5 consecutive days; feeds the
Jul-12 structural review).

Question: is the gap between settled band-path PnL (PF ~0.1) and the simulated
all-fires baseline (+ROI) adverse SELECTION (we get filled exactly when the
quote is wrong) or COMPOSITION (fills landed in slices that are bad in the
simulation too)?

Method:
  A. realized maker fills = trades.jsonl rows tagged WEATHER/<city>/WEATHER_MAKER
     (registered maker fills, resolution-settled; BAND_MERGE exits excluded from
     WR, reported separately).
  B. simulated universe = band_struct md_shadow fires deduped first-per-
     (cid,days_out,side) — identical logic to band_resolution_join.py.
  C. token_id -> conditionId via Gamma; each fill matched to its sim leg.
  D. The decisive split: sim legs on markets WHERE WE FILLED vs sim legs where
     we never filled, same quote basis. Winner's curse <=> WR(filled) <<
     WR(not-filled) at comparable quotes. Plus per-cell (side x days_out x
     price band) realized-vs-sim ROI.

Run:  PYTHONPATH=/root/Klaus python3 analysis/weather/winners_curse_crosstab_0711.py
"""
import json, glob, time, datetime, urllib.request, re
from collections import defaultdict

def get(url):
    for _ in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.0)
    return None

def winner(op):
    try:
        p = json.loads(op)
        if float(p[0]) > 0.5: return 0
        if float(p[1]) > 0.5: return 1
    except Exception:
        pass
    return None

# ── A. realized maker fills ────────────────────────────────────────────────
T0 = datetime.datetime(2026, 6, 11, tzinfo=datetime.timezone.utc).timestamp()
fills, merges = [], []
for l in open("logs/trades.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("record_type") or r.get("asset") != "WEATHER": continue
    if r.get("ts_open", 0) < T0: continue
    if "WEATHER_MAKER" not in str(r.get("signal_source", "")): continue
    (merges if r.get("exit_reason") == "BAND_MERGE" else fills).append(r)
print(f"realized maker fills since 06-11: {len(fills)} settled + {len(merges)} BAND_MERGE (excluded)")

# ── B. simulated first-fire legs (same dedup as band_resolution_join) ──────
raw = []
for f in sorted(glob.glob("logs/shadow/hot/*/band_struct.jsonl")):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("record") != "md_shadow": continue
        ts = float(r.get("ts") or 0.0)
        if r.get("reason") == "fire":
            for q in r.get("quotes", []):
                if q.get("cid"):
                    raw.append({"cid": q["cid"], "side": "YES", "ts": ts,
                                "bid": float(q["bid_quote"]), "off": q.get("off"),
                                "days_out": r.get("days_out"), "city": r.get("city")})
        elif r.get("reason") == "fire_no":
            if r.get("cid"):
                raw.append({"cid": r["cid"], "side": "NO", "ts": ts,
                            "bid": float(r["bid_quote"]), "off": r.get("off"),
                            "days_out": r.get("days_out"), "city": r.get("city")})
first = {}
for L in sorted(raw, key=lambda x: x["ts"]):
    first.setdefault((L["cid"], L["days_out"], L["side"]), L)
legs = list(first.values())
print(f"sim legs (deduped first-fire, YES/NO only): {len(legs)}")

# ── C. token -> market map + resolutions ───────────────────────────────────
tokens = sorted(set(r["token_id"] for r in fills))
tok2mkt = {}
B = 20
for i in range(0, len(tokens), B):
    q = "&".join(f"clob_token_ids={t}" for t in tokens[i:i+B])
    d = get(f"https://gamma-api.polymarket.com/markets?{q}&closed=true&limit=200")
    for m in d or []:
        try: toks = json.loads(m.get("clobTokenIds") or "[]")
        except Exception: toks = []
        for j, t in enumerate(toks):
            tok2mkt[t] = {"cid": m.get("conditionId"), "q": m.get("question", ""),
                          "win": winner(m.get("outcomePrices")), "idx": j,
                          "end": m.get("endDate", "")}
print(f"token->market mapped: {len([t for t in tokens if t in tok2mkt])}/{len(tokens)}")

cids = sorted(set(l["cid"] for l in legs))
res = {}
for i in range(0, len(cids), B):
    q = "&".join(f"condition_ids={c}" for c in cids[i:i+B])
    d = get(f"https://gamma-api.polymarket.com/markets?{q}&closed=true&limit=200")
    for m in d or []:
        res[m.get("conditionId")] = winner(m.get("outcomePrices"))

MONTHS = {m: i+1 for i, m in enumerate(
    ["january","february","march","april","may","june","july","august",
     "september","october","november","december"])}
def mkt_date(question, end):
    m = re.search(r"on (\w+) (\d+)", question or "")
    if m and m.group(1).lower() in MONTHS:
        return datetime.date(2026, MONTHS[m.group(1).lower()], int(m.group(2)))
    if end:
        try: return datetime.date.fromisoformat(end[:10])
        except Exception: pass
    return None

# enrich fills
rows = []
for r in fills:
    mk = tok2mkt.get(r["token_id"])
    if not mk or mk["win"] is None: continue
    side = "YES" if r["direction"] == "BUY_YES" else "NO"
    won = (mk["win"] == 0) == (side == "YES")
    d = mkt_date(mk["q"], mk["end"])
    od = datetime.datetime.fromtimestamp(r["ts_open"], datetime.timezone.utc).date()
    dout = min(max((d - od).days, 0), 2) if d else None
    rows.append({"cid": mk["cid"], "side": side, "px": r["entry_price"],
                 "stake": r["stake"], "pnl": r["net_pnl"], "won": won,
                 "days_out": dout, "q": mk["q"]})
print(f"fills joined to resolution: {len(rows)}")

def pxband(p):
    for lo, hi in ((0, .10), (.10, .20), (.20, .30), (.30, .45), (.45, .60), (.60, .85), (.85, 1.0)):
        if lo <= p < hi: return f"{lo:.2f}-{hi:.2f}"
    return "?"

def agg_fill(rs):
    n = len(rs); st = sum(r["stake"] for r in rs); pn = sum(r["pnl"] for r in rs)
    wr = sum(r["won"] for r in rs) / n if n else 0
    px = sum(r["px"] for r in rs) / n if n else 0
    return n, wr, px, (100 * pn / st if st else 0)

def agg_sim(ls):
    ls = [l for l in ls if res.get(l["cid"]) is not None]
    n = len(ls)
    if not n: return 0, 0, 0, 0
    cost = sum(l["bid"] for l in ls)
    win = sum(1 for l in ls if res[l["cid"]] == (0 if l["side"] == "YES" else 1))
    return n, win / n, cost / n, (100 * (win - cost) / cost if cost else 0)

# ── D1. the decisive split: sim WR on filled vs never-filled markets ───────
filled_keys = set((r["cid"], r["side"]) for r in rows)
sim_filled  = [l for l in legs if (l["cid"], l["side"]) in filled_keys]
sim_unfilled = [l for l in legs if (l["cid"], l["side"]) not in filled_keys]
print("\n== D1: winner's-curse split (sim quote basis, same universe) ==")
for label, ls in (("sim legs on FILLED (cid,side)", sim_filled),
                  ("sim legs NEVER filled", sim_unfilled)):
    n, wr, px, roi = agg_sim(ls)
    print(f"  {label:32} n={n:4d} WR={100*wr:5.1f}% quote={px:.3f} ROI={roi:+6.1f}%")

# ── D2. realized vs sim per cell ───────────────────────────────────────────
print("\n== D2: realized (actual fills) vs simulated, per cell ==")
print(f"  {'cell':28} {'n_f':>4} {'WR_f':>6} {'px_f':>6} {'ROI_f':>8} | {'n_s':>5} {'WR_s':>6} {'px_s':>6} {'ROI_s':>8}")
cells = sorted(set((r["side"], r["days_out"], pxband(r["px"])) for r in rows))
for side, dout, pb in cells:
    fr = [r for r in rows if r["side"] == side and r["days_out"] == dout and pxband(r["px"]) == pb]
    sl = [l for l in legs if l["side"] == side and l["days_out"] == dout and pxband(l["bid"]) == pb]
    nf, wrf, pxf, roif = agg_fill(fr)
    ns, wrs, pxs, rois = agg_sim(sl)
    print(f"  {side} d+{dout} px {pb:11} {nf:4d} {100*wrf:5.1f}% {pxf:6.3f} {roif:+7.1f}% | {ns:5d} {100*wrs:5.1f}% {pxs:6.3f} {rois:+7.1f}%")

n, wr, px, roi = agg_fill(rows)
print(f"\n  ALL realized fills: n={n} WR={100*wr:.1f}% avg_px={px:.3f} ROI={roi:+.1f}%  "
      f"(net ${sum(r['pnl'] for r in rows):+.2f} on ${sum(r['stake'] for r in rows):.2f} staked)")
if merges:
    print(f"  BAND_MERGE exits (excluded): n={len(merges)} net ${sum(r['net_pnl'] for r in merges):+.2f}")
