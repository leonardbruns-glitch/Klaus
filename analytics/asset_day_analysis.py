import json, datetime

with open("/root/Klaus/logs/trades.jsonl") as f:
    trades = [json.loads(l) for l in f if l.strip()]

today_start = datetime.datetime(2026, 4, 30, tzinfo=datetime.timezone.utc).timestamp()

live = [t for t in trades
        if t.get("is_live") == True
        and t.get("entry_price", 0) > 0
        and t.get("ts_open", 0) >= today_start
        and not t.get("trade_id", "").endswith("_ORPHAN")
        and t.get("bond_entry_class") == "TERMINAL"]

def stats_row(g, label, indent=0):
    sp = " " * indent
    if not g:
        print("%s%-45s  n=  0" % (sp, label))
        return
    wins  = [t for t in g if t.get("net_pnl", 0) > 0]
    big_L = [t for t in g if t.get("net_pnl", 0) <= -1.0]
    net   = sum(t.get("net_pnl", 0) for t in g)
    gw    = sum(t.get("net_pnl", 0) for t in wins)
    gl    = sum(t.get("net_pnl", 0) for t in g if t.get("net_pnl", 0) <= 0)
    pf    = abs(gw / gl) if gl else float("inf")
    wr    = len(wins) / len(g)
    avg_ep = sum(t.get("entry_price", 0) for t in g) / len(g)
    print("%s%-45s  n=%3d  WR=%3.0f%%  PF=%5.2f  net=%+7.2f  big_L=%d  avg_ep=%.3f" % (
          sp, label, len(g), wr*100, pf, net, len(big_L), avg_ep))

def avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v)/len(v), 3) if v else None

def fmt(v):
    return "%+.2f" % v if v is not None else "—"

print("=" * 100)
print("ALL-DAY PER-ASSET ANALYSIS — Apr 30 (TERMINAL era, live, non-orphan)")
print("=" * 100)
print("Total n=%d" % len(live))
print()

# ── 1. Overall by asset ──────────────────────────────────────────────────────
print("─" * 70)
print("1. OVERALL BY ASSET")
print("─" * 70)
for asset in ["BTC", "ETH", "SOL", "ALL"]:
    g = live if asset == "ALL" else [t for t in live if t.get("asset") == asset]
    stats_row(g, asset)

# ── 2. By asset × hour ──────────────────────────────────────────────────────
print()
print("─" * 70)
print("2. BY ASSET × HOUR")
print("─" * 70)
hours_seen = sorted(set(
    int((t.get("ts_open", 0) - today_start) // 3600)
    for t in live
))
for asset in ["BTC", "ETH", "SOL"]:
    print("\n  %s:" % asset)
    for h in range(24):
        h_start = today_start + h * 3600
        h_end   = h_start + 3600
        g = [t for t in live if t.get("asset") == asset
             and h_start <= t.get("ts_open", 0) < h_end]
        if not g:
            continue
        stats_row(g, "  %02dh UTC" % h, indent=4)

# ── 3. By asset × exit reason ────────────────────────────────────────────────
print()
print("─" * 70)
print("3. BY ASSET × EXIT REASON")
print("─" * 70)
exit_reasons = sorted(set(t.get("exit_reason", "?") for t in live))
for asset in ["BTC", "ETH", "SOL"]:
    print("\n  %s:" % asset)
    for reason in exit_reasons:
        g = [t for t in live if t.get("asset") == asset
             and t.get("exit_reason") == reason]
        if not g:
            continue
        stats_row(g, "  %s" % reason, indent=4)

# ── 4. By asset × entry price bucket ─────────────────────────────────────────
print()
print("─" * 70)
print("4. BY ASSET × ENTRY PRICE BUCKET")
print("─" * 70)
ep_cuts = [(0.70, 0.76), (0.76, 0.80), (0.80, 0.82), (0.82, 0.84),
           (0.84, 0.86), (0.86, 0.88), (0.88, 0.92), (0.92, 1.0)]
for asset in ["BTC", "ETH", "SOL"]:
    print("\n  %s:" % asset)
    for lo, hi in ep_cuts:
        g = [t for t in live if t.get("asset") == asset
             and lo <= t.get("entry_price", 0) < hi]
        if not g:
            continue
        stats_row(g, "  ep [%.2f, %.2f)" % (lo, hi), indent=4)

# ── 5. Signal averages by asset × outcome ────────────────────────────────────
print()
print("─" * 70)
print("5. SIGNAL AVERAGES BY ASSET × OUTCOME")
print("─" * 70)
signals = [
    ("term_pre_snap_30s",    "snap30"),
    ("term_pre_snap_60s",    "snap60"),
    ("term_ob_depth",        "depth"),
    ("term_ob_imbalance",    "imbalance"),
    ("term_tok_decel_ratio", "decel"),
    ("term_token_delta_5s",  "d5s"),
    ("term_binance_1m_pct",  "b1m"),
]
for asset in ["BTC", "ETH", "SOL"]:
    ag = [t for t in live if t.get("asset") == asset]
    wins  = [t for t in ag if t.get("net_pnl", 0) > 0]
    losers= [t for t in ag if t.get("net_pnl", 0) <= 0]
    big_L = [t for t in ag if t.get("net_pnl", 0) <= -1.0]
    print("\n  %s (n=%d  wins=%d  losers=%d  big_L=%d):" % (
          asset, len(ag), len(wins), len(losers), len(big_L)))
    print("    %-14s  %9s  %9s  %9s" % ("signal", "wins", "losers", "big_L"))
    print("    " + "-" * 46)
    for field, label in signals:
        vw = avg([t.get(field) for t in wins])
        vl = avg([t.get(field) for t in losers])
        vb = avg([t.get(field) for t in big_L])
        print("    %-14s  %9s  %9s  %9s" % (
              label,
              fmt(vw) if vw is not None else "—",
              fmt(vl) if vl is not None else "—",
              fmt(vb) if vb is not None else "—"))

# ── 6. thin_snap30 gate effectiveness by asset ───────────────────────────────
print()
print("─" * 70)
print("6. THIN_SNAP30 GATE BY ASSET (snap30<0 AND depth<200)")
print("─" * 70)
for asset in ["BTC", "ETH", "SOL", "ALL"]:
    ag = live if asset == "ALL" else [t for t in live if t.get("asset") == asset]
    has_both = [t for t in ag
                if t.get("term_pre_snap_30s") is not None
                and t.get("term_ob_depth") is not None
                and t.get("term_ob_depth", 0) > 0]
    blocked = [t for t in has_both
               if t.get("term_pre_snap_30s", 0) < 0
               and t.get("term_ob_depth", 0) < 200]
    passed  = [t for t in has_both if t not in blocked]
    print("\n  %s (has_both n=%d):" % (asset, len(has_both)))
    stats_row(blocked, "  BLOCKED (thin+falling)", indent=4)
    stats_row(passed,  "  PASSED", indent=4)

# ── 7. Big losers trade-by-trade ─────────────────────────────────────────────
print()
print("─" * 70)
print("7. ALL BIG LOSERS TODAY (net_pnl <= -1.0), sorted worst first")
print("─" * 70)
big_L_all = [t for t in live if t.get("net_pnl", 0) <= -1.0]
print("  %-24s  %-5s  %5s  %6s  %6s  %6s  %6s  %6s  %6s  %-22s" % (
      "trade_id", "asset", "ep", "snap30", "depth", "decel", "d5s", "imb", "pnl", "exit_reason"))
print("  " + "-" * 110)
for t in sorted(big_L_all, key=lambda x: x.get("net_pnl", 0)):
    def f(v, fmt_s="%6.2f"): return fmt_s % v if v is not None else "     —"
    print("  %-24s  %-5s  %5.3f  %6s  %6s  %6s  %6s  %6s  %+6.2f  %-22s" % (
          t.get("trade_id","")[:24],
          t.get("asset",""),
          t.get("entry_price", 0),
          f(t.get("term_pre_snap_30s")),
          f(t.get("term_ob_depth"), "%6.0f"),
          f(t.get("term_tok_decel_ratio")),
          f(t.get("term_token_delta_5s")),
          f(t.get("term_ob_imbalance")),
          t.get("net_pnl", 0),
          str(t.get("exit_reason",""))[:22]))

# ── 8. SOL deep dive ─────────────────────────────────────────────────────────
print()
print("─" * 70)
print("8. SOL ALL TRADES TODAY — chronological")
print("─" * 70)
sol = sorted([t for t in live if t.get("asset") == "SOL"], key=lambda x: x.get("ts_open", 0))
print("  %-24s  %5s  %6s  %6s  %6s  %6s  %6s  %6s  %-22s" % (
      "trade_id", "ep", "snap30", "depth", "decel", "d5s", "imb", "pnl", "exit_reason"))
print("  " + "-" * 105)
for t in sol:
    flag = "★" if t.get("net_pnl", 0) <= -1.0 else " "
    def f(v, fmt_s="%6.2f"): return fmt_s % v if v is not None else "     —"
    ts = datetime.datetime.fromtimestamp(t.get("ts_open",0), tz=datetime.timezone.utc)
    print("  %s%-24s  %5.3f  %6s  %6s  %6s  %6s  %6s  %+6.2f  %-22s  %s" % (
          flag,
          t.get("trade_id","")[:24],
          t.get("entry_price", 0),
          f(t.get("term_pre_snap_30s")),
          f(t.get("term_ob_depth"), "%6.0f"),
          f(t.get("term_tok_decel_ratio")),
          f(t.get("term_token_delta_5s")),
          f(t.get("term_ob_imbalance")),
          t.get("net_pnl", 0),
          str(t.get("exit_reason",""))[:22],
          ts.strftime("%H:%M")))

# ── 9. ETH deep dive ─────────────────────────────────────────────────────────
print()
print("─" * 70)
print("9. ETH ALL TRADES TODAY — chronological")
print("─" * 70)
eth = sorted([t for t in live if t.get("asset") == "ETH"], key=lambda x: x.get("ts_open", 0))
print("  %-24s  %5s  %6s  %6s  %6s  %6s  %6s  %6s  %-22s" % (
      "trade_id", "ep", "snap30", "depth", "decel", "d5s", "imb", "pnl", "exit_reason"))
print("  " + "-" * 105)
for t in eth:
    flag = "★" if t.get("net_pnl", 0) <= -1.0 else " "
    def f(v, fmt_s="%6.2f"): return fmt_s % v if v is not None else "     —"
    ts = datetime.datetime.fromtimestamp(t.get("ts_open",0), tz=datetime.timezone.utc)
    print("  %s%-24s  %5.3f  %6s  %6s  %6s  %6s  %6s  %+6.2f  %-22s  %s" % (
          flag,
          t.get("trade_id","")[:24],
          t.get("entry_price", 0),
          f(t.get("term_pre_snap_30s")),
          f(t.get("term_ob_depth"), "%6.0f"),
          f(t.get("term_tok_decel_ratio")),
          f(t.get("term_token_delta_5s")),
          f(t.get("term_ob_imbalance")),
          t.get("net_pnl", 0),
          str(t.get("exit_reason",""))[:22],
          ts.strftime("%H:%M")))
