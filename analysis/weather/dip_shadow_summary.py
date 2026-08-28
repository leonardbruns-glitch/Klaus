"""Validate the SAFE dip-buy (no-look-ahead) from logs/shadow/hot/<date>/dip_shadow.jsonl.

The logger (weather_arb._m1_beta_probe_evaluate) records, with zero look-ahead, every
cheap-NO candidate on a STRONG OFFICIAL lockout: official running_max ≥ margin past the
ceiling (AWC/NWS-clean ⇒ bucket physically impossible) AND a dipped real NO ask. This
joins each no_tok to its Gamma resolution and sweeps the (official-margin, dip) box so
we can see whether buying the dip is a real edge — and at which thresholds — BEFORE any
live re-enable. (The killed dip-rebuy fired on sub-hourly ASOS @ no_ask≤0.25 = false
lockouts; this one only fires on a strong official margin.)

Per no_tok we take the DEEPEST observed dip (min no_ask) as the entry. Buy NO at that
ask → wins (pays 1) if the bucket resolved NO.

Usage (VPS): PYTHONPATH=/root/Klaus python3 -m analysis.weather.dip_shadow_summary [YYYY-MM-DD|all]
"""
import json, sys, statistics, urllib.request, time
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
GAMMA = "https://gamma-api.polymarket.com/markets?clob_token_ids="
_cache = {}


def no_won(no_tok):
    """True if no_tok's NO side resolved YES (paid 1); False if lost; None if unresolved."""
    if no_tok in _cache:
        return _cache[no_tok]
    res = None
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(GAMMA + no_tok, headers=UA), timeout=20))
        m = r[0] if isinstance(r, list) and r else (r if isinstance(r, dict) else None)
        if m and m.get("closed"):
            toks = m.get("clobTokenIds"); pr = m.get("outcomePrices")
            toks = json.loads(toks) if isinstance(toks, str) else toks
            pr = [float(x) for x in (json.loads(pr) if isinstance(pr, str) else pr)]
            if toks and pr and no_tok in toks and sum(1 for p in pr if p >= 0.99) == 1:
                res = pr[toks.index(no_tok)] >= 0.99
    except Exception:
        res = None
    _cache[no_tok] = res
    time.sleep(0.15)
    return res


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    base = Path(__file__).resolve().parents[2] / "logs" / "shadow" / "hot"
    paths = [base / date_str / "dip_shadow.jsonl"] if date_str != "all" else sorted(base.glob("*/dip_shadow.jsonl"))
    rows = []
    for p in paths:
        if Path(p).exists():
            for line in open(p):
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    if not rows:
        print(f"no dip_shadow rows for {date_str}"); return

    # deepest dip per no_tok (best entry), keep its margin/depth
    best = {}
    for r in rows:
        t = r["no_tok"]
        if t not in best or r["no_ask"] < best[t]["no_ask"]:
            best[t] = r
    print(f"dip candidates: {len(rows)} snapshots over {len(best)} buckets (resolving via Gamma...)")

    joined = []
    for t, r in best.items():
        won = no_won(t)
        if won is not None:
            joined.append((r, won))
    n = len(joined)
    print(f"resolved buckets: {n}")
    if not n:
        return

    # sweep the (official-margin, dip) box
    print(f"\n{'min_margin':>10} {'no_ask<=':>8} {'n':>4} {'NO-won%':>8} {'meanEV':>8} {'total':>8} {'meanAsk':>8} {'meanDepth':>9}")
    for mg in (1.0, 1.5, 2.0):
        for dip in (0.95, 0.85, 0.70, 0.50):
            cell = [(r, won) for (r, won) in joined
                    if r["official_margin_c"] >= mg and r["no_ask"] <= dip]
            if not cell:
                continue
            ev = [( (1 - r["no_ask"]) if won else (-r["no_ask"]) ) for (r, won) in cell]
            wr = sum(1 for (_, w) in cell if w) / len(cell)
            asks = [r["no_ask"] for (r, _) in cell]
            deps = [(r.get("no_depth_usd") or 0) for (r, _) in cell]
            print(f"{mg:>10.1f} {dip:>8.2f} {len(cell):>4} {100*wr:>7.0f}% {statistics.mean(ev):>+8.3f} "
                  f"{sum(ev):>+8.2f} {statistics.mean(asks):>8.3f} {statistics.mean(deps):>9.0f}")
    print("\n(buy NO at the dipped ask; +EV with high NO-won% = safe dip-buy box. n≥100 in a cell before live.)")
    # losers (NO lost despite strong official margin) = the danger cases — inspect
    losers = [(r, w) for (r, w) in joined if not w]
    if losers:
        print(f"\n{len(losers)} STRONG-margin dip(s) where NO LOST (false lockout — the risk):")
        for r, _ in losers[:12]:
            print(f"  {r['city']:<13} bucket_hi={r['hi_c']} margin={r['official_margin_c']}°C "
                  f"no_ask={r['no_ask']} depth=${r.get('no_depth_usd')}")


if __name__ == "__main__":
    main()
