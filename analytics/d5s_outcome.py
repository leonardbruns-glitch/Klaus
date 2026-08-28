import json, datetime

with open("/root/Klaus/logs/trades.jsonl") as f:
    trades = [json.loads(l) for l in f if l.strip()]

try:
    with open("/root/Klaus/logs/post_exit.jsonl") as f:
        post_exit = [json.loads(l) for l in f if l.strip()]
except FileNotFoundError:
    post_exit = []

# Build resolution map: trade_id -> outcome record
resolutions = {}
for r in post_exit:
    tid = r.get("trade_id")
    if tid and r.get("record_type") == "resolution":
        resolutions[tid] = r

# Last 2 days: Apr 29-30 UTC
apr29 = datetime.datetime(2026, 4, 29, tzinfo=datetime.timezone.utc).timestamp()

live = [t for t in trades
        if t.get("is_live") == True
        and t.get("entry_price", 0) > 0
        and t.get("ts_open", 0) >= apr29
        and not t.get("trade_id", "").endswith("_ORPHAN")
        and t.get("bond_entry_class") == "TERMINAL"]

# Attach resolution data
for t in live:
    tid = t.get("trade_id")
    res = resolutions.get(tid, {})
    t["_wop"]      = res.get("window_outcome_price")
    t["_resolved"] = res.get("resolved")          # True/False if available
    t["_res_side"] = res.get("resolution_side")   # "YES"/"NO" if available

has_d5s = [t for t in live if t.get("term_token_delta_5s") is not None]
has_wop  = [t for t in live if t.get("_wop") is not None]
has_both = [t for t in live
            if t.get("term_token_delta_5s") is not None
            and t.get("_wop") is not None]

print("=" * 90)
print("D5S vs WINDOW OUTCOME — Apr 29-30 (TERMINAL, live, non-orphan)")
print("=" * 90)
print("Total n=%d | has d5s: %d | has wop: %d | has both: %d" % (
      len(live), len(has_d5s), len(has_wop), len(has_both)))
print()

# Determine YES win: wop >= 0.90 (token resolved YES), NO win: wop <= 0.15
def outcome(t):
    wop = t.get("_wop")
    if wop is None:
        return "unknown"
    if wop >= 0.90:
        return "YES"
    if wop <= 0.15:
        return "NO"
    return "mid"  # didn't reach resolution (PAE exit before window close)

for t in live:
    t["_outcome"] = outcome(t)

# ── 1. Overall outcome distribution ─────────────────────────────────────────
print("─" * 70)
print("1. OVERALL OUTCOME DISTRIBUTION (all live last 2 days)")
print("─" * 70)
for o in ["YES", "NO", "mid", "unknown"]:
    g = [t for t in live if t.get("_outcome") == o]
    if not g: continue
    net = sum(t.get("net_pnl", 0) for t in g)
    wins = [t for t in g if t.get("net_pnl", 0) > 0]
    print("  %-10s  n=%4d  WR=%3.0f%%  net=%+8.2f" % (
          o, len(g), len(wins)/len(g)*100, net))

# ── 2. D5S buckets vs window outcome ─────────────────────────────────────────
print()
print("─" * 70)
print("2. D5S BUCKETS vs WINDOW OUTCOME (has_both n=%d)" % len(has_both))
print("─" * 70)
d5s_cuts = [(-999, -5), (-5, 0), (0, 2), (2, 5), (5, 10), (10, 20), (20, 9999)]

def avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v)/len(v), 3) if v else None

print("  %-22s  %4s  %5s  %5s  %5s  %7s  %7s" % (
      "bucket", "n", "YES%", "NO%", "mid%", "avg_wop", "avg_pnl"))
print("  " + "-" * 68)
for lo, hi in d5s_cuts:
    lo_l = str(lo) if lo > -999 else "<-5"
    hi_l = str(hi) if hi < 9999 else "+"
    g = [t for t in has_both if lo <= (t.get("term_token_delta_5s") or 0) < hi]
    if not g:
        continue
    yes_n  = sum(1 for t in g if t["_outcome"] == "YES")
    no_n   = sum(1 for t in g if t["_outcome"] == "NO")
    mid_n  = sum(1 for t in g if t["_outcome"] == "mid")
    wops   = avg([t["_wop"] for t in g])
    avg_pnl = avg([t.get("net_pnl", 0) for t in g])
    print("  %-22s  %4d  %5.0f%%  %5.0f%%  %5.0f%%  %7s  %7s" % (
          "d5s [%s, %s)" % (lo_l, hi_l),
          len(g),
          yes_n/len(g)*100, no_n/len(g)*100, mid_n/len(g)*100,
          "%.3f" % wops if wops else "—",
          "%+.3f" % avg_pnl if avg_pnl is not None else "—"))

# ── 3. D5S vs outcome by asset ────────────────────────────────────────────────
print()
print("─" * 70)
print("3. D5S vs OUTCOME BY ASSET")
print("─" * 70)
for asset in ["BTC", "ETH", "SOL"]:
    ag = [t for t in has_both if t.get("asset") == asset]
    if not ag:
        continue
    print("\n  %s (n=%d):" % (asset, len(ag)))
    print("  %-22s  %4s  %5s  %5s  %5s  %7s  %7s" % (
          "bucket", "n", "YES%", "NO%", "mid%", "avg_wop", "avg_pnl"))
    print("  " + "-" * 68)
    for lo, hi in d5s_cuts:
        lo_l = str(lo) if lo > -999 else "<-5"
        hi_l = str(hi) if hi < 9999 else "+"
        g = [t for t in ag if lo <= (t.get("term_token_delta_5s") or 0) < hi]
        if not g:
            continue
        yes_n = sum(1 for t in g if t["_outcome"] == "YES")
        no_n  = sum(1 for t in g if t["_outcome"] == "NO")
        mid_n = sum(1 for t in g if t["_outcome"] == "mid")
        wops  = avg([t["_wop"] for t in g])
        avg_pnl = avg([t.get("net_pnl", 0) for t in g])
        print("  %-22s  %4d  %5.0f%%  %5.0f%%  %5.0f%%  %7s  %7s" % (
              "d5s [%s, %s)" % (lo_l, hi_l),
              len(g),
              yes_n/len(g)*100, no_n/len(g)*100, mid_n/len(g)*100,
              "%.3f" % wops if wops else "—",
              "%+.3f" % avg_pnl if avg_pnl is not None else "—"))

# ── 4. Negative d5s deep dive ────────────────────────────────────────────────
print()
print("─" * 70)
print("4. NEGATIVE D5S DEEP DIVE — trades where token was falling at entry")
print("─" * 70)
neg_d5s = [t for t in has_both if (t.get("term_token_delta_5s") or 0) < 0]
print("n=%d" % len(neg_d5s))
if neg_d5s:
    print()
    print("  %-24s  %-5s  %5s  %6s  %6s  %6s  %6s  %6s  %-10s  %-22s" % (
          "trade_id", "asset", "ep", "d5s", "snap30", "depth", "wop", "pnl", "outcome", "exit_reason"))
    print("  " + "-" * 110)
    for t in sorted(neg_d5s, key=lambda x: (x.get("term_token_delta_5s") or 0)):
        def f(v, fmt_s="%6.2f"): return fmt_s % v if v is not None else "     —"
        ts = datetime.datetime.fromtimestamp(t.get("ts_open",0), tz=datetime.timezone.utc)
        print("  %-24s  %-5s  %5.3f  %6s  %6s  %6s  %6s  %6s  %-10s  %-22s  %s" % (
              t.get("trade_id","")[:24],
              t.get("asset",""),
              t.get("entry_price", 0),
              f(t.get("term_token_delta_5s")),
              f(t.get("term_pre_snap_30s")),
              f(t.get("term_ob_depth"), "%6.0f"),
              f(t.get("_wop")),
              f(t.get("net_pnl", 0)),
              t.get("_outcome",""),
              str(t.get("exit_reason",""))[:22],
              ts.strftime("%m-%d %H:%M")))

# ── 5. Sensitivity: gate on d5s < threshold ──────────────────────────────────
print()
print("─" * 70)
print("5. SENSITIVITY: block if d5s < X (has_both)")
print("─" * 70)
print("  %-12s  %4s  %5s  %8s  %5s  |  %4s  %5s  %8s" % (
      "threshold", "blk", "WR", "net", "bigL", "pass", "WR", "net"))
print("  " + "-" * 70)
for thresh in [-5, -3, -2, -1, 0, 1, 2, 3, 5]:
    blocked = [t for t in has_both if (t.get("term_token_delta_5s") or 0) < thresh]
    passed  = [t for t in has_both if (t.get("term_token_delta_5s") or 0) >= thresh]
    if not blocked:
        continue
    bw = [t for t in blocked if t.get("net_pnl", 0) > 0]
    pw = [t for t in passed  if t.get("net_pnl", 0) > 0]
    bn = sum(t.get("net_pnl", 0) for t in blocked)
    pn = sum(t.get("net_pnl", 0) for t in passed)
    bbl = sum(1 for t in blocked if t.get("net_pnl", 0) <= -1.0)
    print("  d5s < %+3d    %4d  %5.0f%%  %+8.2f  %5d  |  %4d  %5.0f%%  %+8.2f" % (
          thresh, len(blocked), len(bw)/len(blocked)*100, bn, bbl,
          len(passed), len(pw)/len(passed)*100, pn))

# ── 6. D5S vs outcome: positive d5s wins that went NO anyway ─────────────────
print()
print("─" * 70)
print("6. HIGH D5S BUT STILL WENT NO (false positives)")
print("─" * 70)
high_d5s_no = [t for t in has_both
               if (t.get("term_token_delta_5s") or 0) >= 5
               and t["_outcome"] == "NO"]
print("d5s>=5 but resolved NO: n=%d" % len(high_d5s_no))
for t in sorted(high_d5s_no, key=lambda x: x.get("net_pnl", 0)):
    def f(v, fmt_s="%6.2f"): return fmt_s % v if v is not None else "     —"
    ts = datetime.datetime.fromtimestamp(t.get("ts_open",0), tz=datetime.timezone.utc)
    print("  %-24s  %-5s  ep=%5.3f  d5s=%6.2f  snap30=%6.2f  depth=%5.0f  pnl=%+6.2f  %s" % (
          t.get("trade_id","")[:24],
          t.get("asset",""),
          t.get("entry_price", 0),
          t.get("term_token_delta_5s") or 0,
          t.get("term_pre_snap_30s") or 0,
          t.get("term_ob_depth") or 0,
          t.get("net_pnl", 0),
          ts.strftime("%m-%d %H:%M")))

# ── 7. D5S vs snap30 combined vs outcome ─────────────────────────────────────
print()
print("─" * 70)
print("7. D5S × SNAP30 COMBINED vs OUTCOME")
print("─" * 70)
has_all = [t for t in has_both if t.get("term_pre_snap_30s") is not None]
print("Has d5s + snap30 + wop: n=%d" % len(has_all))
print()
snap_cuts = [(-999, 0), (0, 20), (20, 50), (50, 9999)]
d5s_simple = [(-999, 0), (0, 5), (5, 9999)]
print("  %-30s  %4s  %5s  %5s  %5s  %7s" % ("bucket", "n", "YES%", "NO%", "mid%", "avg_pnl"))
print("  " + "-" * 60)
for slo, shi in snap_cuts:
    slo_l = "<0" if slo < -100 else str(slo)
    shi_l = "+" if shi > 9000 else str(shi)
    for dlo, dhi in d5s_simple:
        dlo_l = "<0" if dlo < -100 else str(dlo)
        dhi_l = "+" if dhi > 9000 else str(dhi)
        g = [t for t in has_all
             if slo <= (t.get("term_pre_snap_30s") or 0) < shi
             and dlo <= (t.get("term_token_delta_5s") or 0) < dhi]
        if len(g) < 3:
            continue
        yes_n = sum(1 for t in g if t["_outcome"] == "YES")
        no_n  = sum(1 for t in g if t["_outcome"] == "NO")
        mid_n = sum(1 for t in g if t["_outcome"] == "mid")
        ap    = avg([t.get("net_pnl", 0) for t in g])
        label = "snap[%s,%s) × d5s[%s,%s)" % (slo_l, shi_l, dlo_l, dhi_l)
        print("  %-30s  %4d  %5.0f%%  %5.0f%%  %5.0f%%  %7s" % (
              label, len(g),
              yes_n/len(g)*100, no_n/len(g)*100, mid_n/len(g)*100,
              "%+.3f" % ap if ap is not None else "—"))
