"""
Tail Resolution-Determinability scanner (read-only).

The contrarian edge (project: think-small-where-giants-wont): thousands of
neglected illiquid Polymarket markets are priced by a handful of inattentive
retail traders. The automatable, uncompeted edge is to find markets whose
outcome is DETERMINABLE NOW (the event already happened / the fact is public)
but whose price still reflects UNCERTAINTY — then bet the known side and hold
to resolution (redemption is free; no exit liquidity needed).

Cleanest signal = OVERDUE markets: endDate passed, still open, price in [0.15,0.85].
The event is decided; the market hasn't caught up. Also flags long-dated
near-certain favorites (capital-lock discount) and decided-keyword markets.

Output → logs/shadow/tail_resolver.jsonl, ranked for fact-determination.

Run: python3 strategy/tail_resolver.py
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com/markets"
OUT = Path("logs/shadow/tail_resolver.jsonl")
LIQ_MAX = 3000     # neglected tail: below this the funded bots don't bother
DECIDED_HINTS = ("did ", "by june", "by may", "by july", "in 2025", "final", "winner of")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "klaus-tail/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_tail(pages=4, per=500):
    """Active, open, low-liquidity markets ending soonest (catches overdue)."""
    out = []
    for pg in range(pages):
        q = urllib.parse.urlencode({
            "closed": "false", "active": "true", "archived": "false",
            "liquidity_num_max": LIQ_MAX, "order": "endDate", "ascending": "true",
            "limit": per, "offset": pg * per,
        })
        try:
            batch = _get(f"{GAMMA}?{q}")
        except Exception as e:
            print("fetch error:", e); break
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per:
            break
    return out


def main():
    now = datetime.now(timezone.utc)
    mk = fetch_tail()
    print(f"tail markets pulled (liq<=${LIQ_MAX}): {len(mk)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cands = []
    for m in mk:
        pr = m.get("outcomePrices")
        if isinstance(pr, str):
            try: pr = json.loads(pr)
            except Exception: pr = None
        if not pr or len(pr) != 2:
            continue
        try: p_yes = float(pr[0])
        except Exception: continue
        fav = max(p_yes, 1 - p_yes)
        ed = m.get("endDate")
        days = None
        if ed:
            try: days = (datetime.fromisoformat(ed.replace("Z", "+00:00")) - now).total_seconds() / 86400
            except Exception: pass
        q = (m.get("question") or "")
        overdue = (days is not None and days < 0)
        uncertain = 0.15 <= fav <= 0.85
        decided_hint = any(h in q.lower() for h in DECIDED_HINTS)
        # score: overdue+uncertain is the prime determinable-mispricing
        score = 0
        if overdue and uncertain: score = 100        # event passed, priced uncertain = GOLD
        elif overdue:             score = 60          # event passed, near-certain (small edge)
        elif uncertain and decided_hint and days is not None and days < 14: score = 50
        elif days is not None and days < 7 and uncertain: score = 30  # resolving soon, still uncertain
        if score == 0:
            continue
        toks = m.get("clobTokenIds")
        if isinstance(toks, str):
            try: toks = json.loads(toks)
            except Exception: toks = None
        rec = {
            "score": score, "overdue": overdue, "days": round(days, 1) if days is not None else None,
            "p_yes": round(p_yes, 3), "fav": round(fav, 3), "liq": m.get("liquidityNum"),
            "vol": m.get("volume"), "question": q[:120],
            "description": (m.get("description") or "")[:400],
            "condition_id": m.get("conditionId"), "tokens": toks, "end_date": ed,
        }
        cands.append(rec)
        with OUT.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    cands.sort(key=lambda r: (-r["score"], (r["days"] if r["days"] is not None else 0)))
    overdue_unc = [c for c in cands if c["score"] == 100]
    print(f"\ndeterminable-mispricing candidates: {len(cands)}  "
          f"(OVERDUE+uncertain={len(overdue_unc)}, the prime targets)")
    print("\n=== TOP CANDIDATES (research the fact → bet the known side) ===")
    for c in cands[:18]:
        tag = "OVERDUE+UNC" if c["score"] == 100 else "overdue" if c["overdue"] else f"soon({c['days']}d)"
        print(f"  [{c['score']:3}] {tag:11} p_yes={c['p_yes']:.2f} liq=${c['liq']} | {c['question'][:78]}")
    print("\nFull records (with resolution descriptions) in logs/shadow/tail_resolver.jsonl")


if __name__ == "__main__":
    main()
