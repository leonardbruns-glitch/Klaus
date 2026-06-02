"""Forward (no-look-ahead) validation of the resolution hourly-sampling fade edge.

Reads logs/shadow/hot/<date>/fade_shadow.jsonl (written live by stwa_engine: post-peak
snapshots of the bins just ABOVE running_max + their LIVE NO ask), joins each fade
bin's no_tok to its Gamma resolution, and reports the forward fade WR/EV.

Per city-day we take the LAST post-peak snapshot (closest to lock) and the PRIME
fade bin (rank_above==0 = bin immediately above the hourly running_max). Buying NO
at the logged live ask wins if that bin did NOT resolve YES.

Everything is real-time at log time ⇒ no look-ahead, no selection-on-winners.

Usage (VPS): PYTHONPATH=/root/Klaus python3 -m analysis.weather.fade_shadow_summary [YYYY-MM-DD]
"""
import json, sys, statistics, urllib.request, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
GAMMA = "https://gamma-api.polymarket.com/markets?clob_token_ids="
_cache = {}


def no_won(no_tok):
    """Return True if the NO side of no_tok's market resolved YES (i.e. NO paid 1),
    False if it lost, None if unresolved/unknown."""
    if no_tok in _cache:
        return _cache[no_tok]
    res = None
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(GAMMA + no_tok, headers=UA), timeout=20))
        m = r[0] if isinstance(r, list) and r else (r if isinstance(r, dict) else None)
        if m and m.get("closed"):
            toks = json.loads(m.get("clobTokenIds", "[]")) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", [])
            pr = json.loads(m.get("outcomePrices", "[]")) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices", [])
            pr = [float(x) for x in pr]
            if toks and pr and no_tok in toks and (sum(1 for p in pr if p >= 0.99) == 1):
                idx = toks.index(no_tok)
                res = pr[idx] >= 0.99  # did the NO token pay 1?
    except Exception:
        res = None
    _cache[no_tok] = res
    time.sleep(0.15)
    return res


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    base = Path(__file__).resolve().parents[2] / "logs" / "shadow" / "hot"
    paths = [base / date_str / "fade_shadow.jsonl"] if date_str != "all" else sorted(base.glob("*/fade_shadow.jsonl"))
    snaps = []
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p):
            try:
                snaps.append(json.loads(line))
            except Exception:
                pass
    if not snaps:
        print(f"no fade_shadow rows for {date_str}"); return
    # last post-peak snapshot per (city, utc-day)
    last = {}
    for s in snaps:
        day = datetime.fromtimestamp(s["ts"], timezone.utc).date().isoformat()
        k = (s["city"], day)
        if k not in last or s["ts"] > last[k]["ts"]:
            last[k] = s
    print(f"snapshots={len(snaps)}  city-days={len(last)}  (resolving prime fade bins via Gamma...)")

    fade_ev, fade_win, prices, depths = [], 0, [], []
    n_priced = 0
    rows = []
    for (city, day), s in sorted(last.items()):
        prime = next((b for b in s["fade_bins"] if b.get("rank_above") == 0), None)
        if not prime:
            continue
        na = prime.get("no_ask")
        won = no_won(prime["no_tok"])
        if won is None:
            continue
        rows.append((city, day, prime, won, na))
        if won:
            fade_win += 1
        if na is not None and 0 < na < 1:
            n_priced += 1
            prices.append(na); depths.append(prime.get("no_depth_usd") or 0)
            fade_ev.append((1 - na) if won else (-na))  # buy NO at ask; +1 if NO paid
    n = len(rows)
    print(f"\n=== FORWARD FADE (prime bin = immediately above hourly running_max) ===")
    print(f"resolved city-days: {n}")
    if n:
        print(f"prime-bin NO won (fade correct): {fade_win}/{n} = {100*fade_win/n:.0f}%")
    if fade_ev:
        print(f"buy NO @ live ask: n_priced={n_priced} meanEV={statistics.mean(fade_ev):+.3f} "
              f"total={sum(fade_ev):+.2f} mean_ask={statistics.mean(prices):.3f} "
              f"mean_depth=${statistics.mean(depths):.0f}")
        print("(meanEV>0 with non-trivial ask ⇒ forward-confirmed; n≥100 before sizing)")
    for city, day, prime, won, na in rows[:25]:
        print(f"  {city:<14} {day} bin[{prime['lo']},{prime['hi']}] no_ask={na} fair={prime.get('fair')} "
              f"depth=${prime.get('no_depth_usd')} -> NO {'WON' if won else 'lost'}")


if __name__ == "__main__":
    main()
