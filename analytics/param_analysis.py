#!/usr/bin/env python3
"""
Parameter Analysis — deep dive into what entry conditions actually predict outcomes.

Outputs:
  1. Individual parameter WR breakdowns (lag, delta, elapsed, QS, hour, asset, etc.)
  2. 2D combo grids (lag×delta, lag×elapsed, delta×elapsed)
  3. Sequential filter table — what happens to n and WR as we tighten each gate
  4. Exit reason × after-exit price data (was the exit correct?)
  5. Slippage impact on WR

Usage:
    python3 analytics/param_analysis.py [--asset BTC|ETH|SOL] [--since YYYY-MM-DD] [--last N]
"""

import json, os, sys, datetime
from collections import defaultdict
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
TRADES_PATH    = os.path.join(REPO_ROOT, "logs", "trades.jsonl")
POST_EXIT_PATH = os.path.join(REPO_ROOT, "logs", "post_exit.jsonl")

# ─── CLI flags ───────────────────────────────────────────────────────────────
FILTER_ASSET = None
FILTER_SINCE = None
FILTER_LAST  = None
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--asset" and i+1 < len(sys.argv)-1:
        FILTER_ASSET = sys.argv[i+2].upper()
    if arg == "--since" and i+1 < len(sys.argv)-1:
        try:
            FILTER_SINCE = datetime.datetime.strptime(sys.argv[i+2], "%Y-%m-%d").timestamp()
        except ValueError:
            pass
    if arg == "--last" and i+1 < len(sys.argv)-1:
        try:
            FILTER_LAST = int(sys.argv[i+2])
        except ValueError:
            pass

# ─── Data loading ─────────────────────────────────────────────────────────────

def load_trades():
    trades, skip = [], 0
    with open(TRADES_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if not t.get("is_live"):
                skip += 1; continue
            if (t.get("entry_price") or 0) == 0:
                skip += 1; continue
            # normalise PnL field
            t["_pnl"] = t.get("net_pnl") or t.get("pnl") or t.get("gross_pnl") or 0.0
            # optional filters
            if FILTER_ASSET and t.get("asset","").upper() != FILTER_ASSET:
                continue
            if FILTER_SINCE and (t.get("ts_open") or 0) < FILTER_SINCE:
                continue
            trades.append(t)
    if FILTER_LAST and len(trades) > FILTER_LAST:
        trades = trades[-FILTER_LAST:]
    print(f"Loaded {len(trades)} live trades (skipped {skip} orphans/dry-runs)")
    return trades

def load_post_exit():
    """Load post_exit.jsonl keyed by trade_id."""
    post = {}
    if not os.path.exists(POST_EXIT_PATH):
        return post
    with open(POST_EXIT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            tid = r.get("trade_id","")
            if tid and r.get("record_type") != "resolution":
                post[tid] = r
    return post

# ─── Stats helpers ────────────────────────────────────────────────────────────

def stats(ts):
    n = len(ts)
    if n == 0:
        return dict(n=0, wr=None, avg_w=None, avg_l=None, pf=None, net=0)
    wins   = [t["_pnl"] for t in ts if t["_pnl"] > 0]
    losses = [t["_pnl"] for t in ts if t["_pnl"] <= 0]
    nw = len(wins)
    wr = nw / n * 100
    avg_w = sum(wins)/len(wins) if wins else 0
    avg_l = sum(losses)/len(losses) if losses else 0
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw/gl if gl > 0 else float("inf")
    return dict(n=n, wr=wr, avg_w=avg_w, avg_l=avg_l, pf=pf, net=sum(t["_pnl"] for t in ts))

def _g(d, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default

def bucket(v, breaks, labels):
    """Map float v to a label using upper-bound breakpoints."""
    for bp, lbl in zip(breaks, labels):
        if v < bp:
            return lbl
    return labels[-1]

# ─── Display helpers ──────────────────────────────────────────────────────────

W = 78
SEP = "=" * W

def hdr(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def tbl(rows, col=22):
    """rows = [(label, stats_dict)]"""
    h = f"{'Bucket':<{col}} {'n':>5}  {'WR%':>6}  {'avg_W':>7}  {'avg_L':>8}  {'PF':>5}  {'net':>8}"
    print(h); print("-"*len(h))
    for lbl, s in rows:
        if s["n"] == 0: continue
        wr   = f"{s['wr']:5.1f}%" if s['wr'] is not None else "  —  "
        aw   = f"${s['avg_w']:+.3f}" if s['avg_w'] else "   —   "
        al   = f"${s['avg_l']:+.3f}" if s['avg_l'] else "   —   "
        pf   = f"{s['pf']:5.2f}" if s['pf'] not in (None, float("inf")) else ("  ∞  " if s['pf'] else "  —  ")
        net  = f"${s['net']:+.3f}"
        print(f"{lbl:<{col}} {s['n']:>5}  {wr:>6}  {aw:>7}  {al:>8}  {pf:>5}  {net:>8}")

def spread(rows):
    wrs = [s["wr"] for _, s in rows if s["n"] >= 5 and s["wr"] is not None]
    return max(wrs) - min(wrs) if len(wrs) >= 2 else 0.0

# ─── Individual analyses ──────────────────────────────────────────────────────

LAG_BREAKS  = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
LAG_LABELS  = ["<0.35","0.35–0.45","0.45–0.55","0.55–0.65","0.65–0.75","0.75–0.85","0.85+"]

DELTA_BREAKS = [0.08, 0.10, 0.12, 0.15, 0.20]
DELTA_LABELS = ["<0.08","0.08–0.10","0.10–0.12","0.12–0.15","0.15–0.20","0.20+"]

ELAP_BREAKS  = [0.10, 0.20, 0.35, 0.50, 0.65]
ELAP_LABELS  = ["<0.10","0.10–0.20","0.20–0.35","0.35–0.50","0.50–0.65","0.65+"]

SLIP_BREAKS  = [0.005, 0.01, 0.02, 0.035, 0.05]
SLIP_LABELS  = ["<0.5%","0.5–1%","1–2%","2–3.5%","3.5–5%","5%+"]

def get_lag(t):   return _g(t,"sniper_lag_remaining","lag_remaining","lag")
def get_delta(t): return abs(_g(t,"sniper_delta_pct","delta_pct",default=0) or 0)
def get_elap(t):  return _g(t,"sniper_elapsed_pct","elapsed_pct")
def get_slip(t):
    # slip_e is fraction (not pct) in trades.jsonl
    v = _g(t,"slippage_entry","slip_e")
    return abs(v) if v is not None else None

def grp_by(trades, keyfn):
    g = defaultdict(list)
    for t in trades:
        k = keyfn(t)
        if k is not None:
            g[k].append(t)
    return g

def analyse_1d(trades, keyfn, breaks, labels):
    g = defaultdict(list)
    for t in trades:
        v = keyfn(t)
        if v is None: continue
        g[bucket(float(v), breaks, labels)].append(t)
    return [(lbl, stats(g[lbl])) for lbl in labels]

def analyse_exit_reason(trades):
    g = defaultdict(list)
    for t in trades:
        r = (t.get("exit_reason") or "?").replace("_EXT","")
        g[r].append(t)
    ordered = sorted(g.keys(), key=lambda k: -len(g[k]))
    return [(r, stats(g[r])) for r in ordered[:15]]

def analyse_qs(trades):
    g = defaultdict(list)
    for t in trades:
        qs = t.get("quality_score")
        if qs is None: continue
        g[int(qs)].append(t)
    return [(f"QS={q}", stats(g[q])) for q in sorted(g.keys())]

def analyse_hour(trades):
    g = defaultdict(list)
    for t in trades:
        h = t.get("hour_utc")
        if h is None: continue
        g[int(h)].append(t)
    return [(f"hr={h:02d}UTC", stats(g[h])) for h in sorted(g.keys()) if stats(g[h])["n"] >= 3]

def analyse_asset(trades):
    g = grp_by(trades, lambda t: t.get("asset"))
    return [(a, stats(g[a])) for a in sorted(g.keys())]

def analyse_regime(trades):
    g = grp_by(trades, lambda t: t.get("regime"))
    return [(r, stats(g[r])) for r in sorted(g.keys())]

def analyse_direction(trades):
    g = grp_by(trades, lambda t: t.get("direction","").replace("TradeDirection.",""))
    return [(d, stats(g[d])) for d in sorted(g.keys())]

def analyse_window(trades):
    g = defaultdict(list)
    for t in trades:
        ws = t.get("window_size_s") or 0
        lbl = f"{ws//60}m" if ws else "?"
        g[lbl].append(t)
    return [(lbl, stats(g[lbl])) for lbl in ["5m","15m","?"] if g[lbl]]

# ─── 2D Combo grid ───────────────────────────────────────────────────────────

def combo_grid(trades, row_fn, row_breaks, row_labels,
               col_fn, col_breaks, col_labels,
               row_name="row", col_name="col"):
    """Print a 2D WR/n grid. Cell = WR%(n)."""
    grid = {r: {c: [] for c in col_labels} for r in row_labels}
    for t in trades:
        rv = row_fn(t); cv = col_fn(t)
        if rv is None or cv is None: continue
        rb = bucket(float(rv), row_breaks, row_labels)
        cb = bucket(float(cv), col_breaks, col_labels)
        grid[rb][cb].append(t)

    col_w = 13
    row_w = 12
    header = f"{'':>{row_w}}" + "".join(f"{c:^{col_w}}" for c in col_labels)
    print(f"\n  {row_name} \\ {col_name}")
    print(header)
    print("-" * len(header))
    for rl in row_labels:
        row_cells = []
        for cl in col_labels:
            s = stats(grid[rl][cl])
            if s["n"] == 0:
                cell = "   —   "
            elif s["n"] < 3:
                cell = f"  ?({s['n']})"
            else:
                cell = f"{s['wr']:.0f}%({s['n']})"
            row_cells.append(f"{cell:^{col_w}}")
        print(f"{rl:>{row_w}}" + "".join(row_cells))

# ─── Sequential filter table ─────────────────────────────────────────────────

def sequential_filter_table(trades):
    """
    Show how WR and n change as we progressively tighten each gate.
    Starts from the full set and applies each filter cumulatively.
    """
    hdr("SEQUENTIAL FILTER TABLE  (each row adds one more gate on top)")

    rows = [
        ("All live trades",                     lambda t: True),
        ("lag ≥ 0.30",                          lambda t: (get_lag(t) or 0) >= 0.30),
        ("lag ≥ 0.35",                          lambda t: (get_lag(t) or 0) >= 0.35),
        ("lag ≥ 0.40",                          lambda t: (get_lag(t) or 0) >= 0.40),
        ("lag ≥ 0.50",                          lambda t: (get_lag(t) or 0) >= 0.50),
        ("lag ≥ 0.60",                          lambda t: (get_lag(t) or 0) >= 0.60),
        ("lag ≥ 0.40 + delta ≥ 0.08%",         lambda t: (get_lag(t) or 0) >= 0.40 and get_delta(t) >= 0.08),
        ("lag ≥ 0.40 + delta ≥ 0.10%",         lambda t: (get_lag(t) or 0) >= 0.40 and get_delta(t) >= 0.10),
        ("lag ≥ 0.40 + delta ≥ 0.12%",         lambda t: (get_lag(t) or 0) >= 0.40 and get_delta(t) >= 0.12),
        ("lag ≥ 0.40 + delta ≥ 0.15%",         lambda t: (get_lag(t) or 0) >= 0.40 and get_delta(t) >= 0.15),
        ("lag ≥ 0.50 + delta ≥ 0.10%",         lambda t: (get_lag(t) or 0) >= 0.50 and get_delta(t) >= 0.10),
        ("lag ≥ 0.50 + delta ≥ 0.12%",         lambda t: (get_lag(t) or 0) >= 0.50 and get_delta(t) >= 0.12),
        ("lag ≥ 0.60 + delta ≥ 0.10%",         lambda t: (get_lag(t) or 0) >= 0.60 and get_delta(t) >= 0.10),
        ("lag ≥ 0.60 + delta ≥ 0.12%",         lambda t: (get_lag(t) or 0) >= 0.60 and get_delta(t) >= 0.12),
        ("lag ≥ 0.50 + delta ≥ 0.10% + QS≥2",  lambda t: (get_lag(t) or 0) >= 0.50 and get_delta(t) >= 0.10 and (t.get("quality_score") or 0) >= 2),
        ("lag ≥ 0.50 + delta ≥ 0.10% + QS≥3",  lambda t: (get_lag(t) or 0) >= 0.50 and get_delta(t) >= 0.10 and (t.get("quality_score") or 0) >= 3),
        ("lag ≥ 0.40 + elap 0.45–0.80",         lambda t: (get_lag(t) or 0) >= 0.40 and 0.45 <= (get_elap(t) or 0) <= 0.80),
        ("lag ≥ 0.50 + elap 0.45–0.80",         lambda t: (get_lag(t) or 0) >= 0.50 and 0.45 <= (get_elap(t) or 0) <= 0.80),
        ("lag ≥ 0.50 + elap 0.45–0.80 + δ≥0.10", lambda t: (get_lag(t) or 0) >= 0.50 and 0.45 <= (get_elap(t) or 0) <= 0.80 and get_delta(t) >= 0.10),
        ("slip_e ≤ 3.5% only",                  lambda t: (get_slip(t) or 0) <= 0.035),
        ("slip_e ≤ 2.0% only",                  lambda t: (get_slip(t) or 0) <= 0.020),
    ]

    h = f"{'Filter':<47} {'n':>5}  {'WR%':>6}  {'net':>8}  {'PF':>5}"
    print(h); print("-"*len(h))
    for label, fn in rows:
        subset = [t for t in trades if fn(t)]
        s = stats(subset)
        if s["n"] == 0:
            print(f"{label:<47} {'0':>5}  {'—':>6}  {'—':>8}  {'—':>5}")
            continue
        wr = f"{s['wr']:5.1f}%"
        net = f"${s['net']:+.3f}"
        pf = f"{s['pf']:5.2f}" if s['pf'] != float("inf") else "  ∞  "
        print(f"{label:<47} {s['n']:>5}  {wr:>6}  {net:>8}  {pf:>5}")

# ─── Exit quality using post_exit data ───────────────────────────────────────

def exit_quality_table(trades, post):
    """For each exit reason, show avg price movement after exit (using post_exit.jsonl)."""
    if not post:
        print("  (no post_exit.jsonl found — skipping)")
        return

    g = defaultdict(list)
    for t in trades:
        tid = t.get("trade_id","")
        pe  = post.get(tid)
        if not pe:
            continue
        mfe = pe.get("move_from_exit_pct", {})
        reason = (t.get("exit_reason") or "?").replace("_EXT","")
        pnl = t["_pnl"]
        g[reason].append({
            "pnl": pnl,
            "t30":  mfe.get("t30s"),
            "t60":  mfe.get("t60s"),
            "t120": mfe.get("t120s"),
        })

    # Sort by frequency
    ordered = sorted(g.keys(), key=lambda k: -len(g[k]))
    h = f"{'Exit Reason':<22} {'n':>5}  {'WR%':>6}  {'avg+30s':>8}  {'avg+60s':>8}  {'avg+120s':>9}  note"
    print(h); print("-"*len(h))

    for reason in ordered[:15]:
        rows_r = g[reason]
        nr = len(rows_r)
        n_wins = sum(1 for r in rows_r if r["pnl"] > 0)
        wr = n_wins/nr*100 if nr else 0

        def _avg(key):
            vals = [r[key] for r in rows_r if r[key] is not None]
            return sum(vals)/len(vals) if vals else None

        t30  = _avg("t30")
        t60  = _avg("t60")
        t120 = _avg("t120")

        def _fmt(v):
            return f"{v:+.1f}%" if v is not None else "   —   "

        # Classify: if avg after-exit is significantly positive, exit was premature
        note = ""
        if t60 is not None and t60 > 5 and wr < 50:
            note = " ← EARLY EXIT (price continued up after)"
        elif t60 is not None and t60 < -5:
            note = " ✓ exit was correct (price fell after)"

        print(f"{reason:<22} {nr:>5}  {wr:>5.1f}%  {_fmt(t30):>8}  {_fmt(t60):>8}  {_fmt(t120):>9}  {note}")

# ─── Per-asset breakdown ──────────────────────────────────────────────────────

def per_asset_detail(trades):
    assets = sorted(set(t.get("asset","?") for t in trades))
    for asset in assets:
        sub = [t for t in trades if t.get("asset") == asset]
        if len(sub) < 5:
            continue
        hdr(f"ASSET: {asset}  (n={len(sub)})")
        print("  — by lag:"); tbl(analyse_1d(sub, get_lag, LAG_BREAKS, LAG_LABELS))
        print("  — by delta:"); tbl(analyse_1d(sub, get_delta, DELTA_BREAKS, DELTA_LABELS))
        print("  — by elapsed:"); tbl(analyse_1d(sub, get_elap, ELAP_BREAKS, ELAP_LABELS))

# ─── Correlation summary ──────────────────────────────────────────────────────

def corr_summary(sections):
    hdr("SIGNAL STRENGTH RANKING  (WR spread across buckets with n≥5)")
    h = f"{'Parameter':<45} {'WR spread':>10}"
    print(h); print("-"*55)
    for name, rows_data in sorted(sections, key=lambda x: -spread(x[1])):
        sp = spread(rows_data)
        flag = "  *** strong" if sp >= 30 else ("  ** moderate" if sp >= 15 else "")
        print(f"{name:<45} {sp:>9.1f}%{flag}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(TRADES_PATH):
        print(f"ERROR: {TRADES_PATH} not found", file=sys.stderr); sys.exit(1)

    trades = load_trades()
    if not trades:
        print("No live trades found."); return

    post = load_post_exit()

    n  = len(trades)
    nw = sum(1 for t in trades if t["_pnl"] > 0)
    net = sum(t["_pnl"] for t in trades)

    print(f"\n{'='*W}")
    filters = []
    if FILTER_ASSET: filters.append(f"asset={FILTER_ASSET}")
    if FILTER_SINCE: filters.append(f"since={datetime.datetime.utcfromtimestamp(FILTER_SINCE).date()}")
    suffix = f"  [{', '.join(filters)}]" if filters else ""
    print(f"  PARAMETER ANALYSIS — {n} live trades | WR={nw/n*100:.1f}% | net=${net:+.3f}{suffix}")
    print(f"  post_exit records loaded: {len(post)}")
    print(f"{'='*W}")

    if n < 20:
        print(f"\n  *** n={n} < 20 — DATA COLLECTION MODE. Patterns below are tentative.")
        print(f"  *** Do not act on any single-parameter finding below n=20.")

    # ── Individual breakdowns ─────────────────────────────────────────────────
    sections = []

    def section(title, rows_data):
        hdr(title)
        tbl(rows_data)
        sections.append((title, rows_data))

    section("LAG (lag_remaining fraction — 1.0 = 100% of move unpriced by PM)",
            analyse_1d(trades, get_lag, LAG_BREAKS, LAG_LABELS))

    section("DELTA PCT (|Binance move from window open|)",
            analyse_1d(trades, get_delta, DELTA_BREAKS, DELTA_LABELS))

    section("ELAPSED PCT (fraction of window elapsed at entry)",
            analyse_1d(trades, get_elap, ELAP_BREAKS, ELAP_LABELS))

    section("ENTRY SLIPPAGE (fill vs signal price, as fraction)",
            analyse_1d(trades, get_slip, SLIP_BREAKS, SLIP_LABELS))

    section("QUALITY SCORE", analyse_qs(trades))
    section("ASSET", analyse_asset(trades))
    section("DIRECTION", analyse_direction(trades))
    section("WINDOW SIZE", analyse_window(trades))
    section("REGIME", analyse_regime(trades))
    section("HOUR UTC (n≥3)", analyse_hour(trades))
    section("EXIT REASON", analyse_exit_reason(trades))

    # ── 2D Combo grids ────────────────────────────────────────────────────────
    hdr("2D COMBO GRID: LAG × DELTA  (cell = WR%(n), — = 0 trades, ? = n<3)")
    combo_grid(trades, get_lag, LAG_BREAKS, LAG_LABELS,
                       get_delta, DELTA_BREAKS, DELTA_LABELS,
                       row_name="lag", col_name="|delta|%")

    hdr("2D COMBO GRID: LAG × ELAPSED PCT")
    combo_grid(trades, get_lag, LAG_BREAKS, LAG_LABELS,
                       get_elap, ELAP_BREAKS, ELAP_LABELS,
                       row_name="lag", col_name="elapsed")

    hdr("2D COMBO GRID: DELTA × ELAPSED PCT")
    combo_grid(trades, get_delta, DELTA_BREAKS, DELTA_LABELS,
                       get_elap, ELAP_BREAKS, ELAP_LABELS,
                       row_name="|delta|%", col_name="elapsed")

    hdr("2D COMBO GRID: LAG × QUALITY SCORE")
    qs_breaks = [1, 2, 3, 4]; qs_labels = ["QS=0","QS=1","QS=2","QS=3","QS≥4"]
    combo_grid(trades, get_lag, LAG_BREAKS, LAG_LABELS,
                       lambda t: t.get("quality_score"), qs_breaks, qs_labels,
                       row_name="lag", col_name="QS")

    # ── Sequential filter table ───────────────────────────────────────────────
    sequential_filter_table(trades)

    # ── Exit quality ──────────────────────────────────────────────────────────
    hdr("EXIT QUALITY  (avg price move AFTER exit — positive = price rose = early exit)")
    exit_quality_table(trades, post)

    # ── Per-asset detail ──────────────────────────────────────────────────────
    per_asset_detail(trades)

    # ── Correlation ranking ───────────────────────────────────────────────────
    corr_summary(sections)

    # ── Key findings ──────────────────────────────────────────────────────────
    hdr("KEY FINDINGS & INTERPRETATION")
    print("""
  WR spread ≥30pp → parameter has strong predictive signal (validate with n≥20)
  WR spread 15–30pp → moderate signal, worth monitoring
  WR spread <15pp  → no meaningful edge in this dimension at current n

  2D GRIDS: cells with WR>60% AND n≥5 are the high-conviction entry zones.
            cells with WR<35% AND n≥5 are zones to block.

  SEQUENTIAL FILTER: shows which gate combinations preserve WR while cutting n.
                     Best gate = highest WR increase per % of n lost.

  EXIT QUALITY: positive after-exit means the exit was premature (price kept going).
                If SIGNAL_FLIPPED/VELOCITY_EXIT show +10%+ after-exit avg → false positives.
                If HARD_EXIT shows +5%+ after-exit → max_trade_duration too short.

  SLIPPAGE: if WR drops sharply above 2-3% slip → entry_slip_cap is working correctly.
            if WR is similar across slip bands → slippage is not a major driver.
""")
    print(SEP)


if __name__ == "__main__":
    main()
