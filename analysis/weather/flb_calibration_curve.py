"""FAVORITE-LONGSHOT CALIBRATION CURVE — is the bias real at SCALE? (READ-ONLY)

De-overfit test for the favorite-longshot NO strategy. Instead of trusting the
n=37 entered-trade slice, this measures the bias across EVERY bucket we have a
book snapshot for (~358k maker_shadow rows).

METHOD (self-contained, no slow Gamma join):
- Group maker_shadow.jsonl by (day, city, bucket=yes_tok).
- OUTCOME label per (day,city): the winning bucket = the one whose FINAL (latest-ts)
  yes mid-price converged highest. Require a clean winner (exactly one bucket with
  final yes_mid > 0.70) — by close the daily max is decided, so the market prices
  the winner ~1.0 / losers ~0.0. (Label is market-convergence-derived; cross-check
  vs Gamma UMA later. Circularity-free: we test whether the EARLY ask predicts the
  outcome, not whether the late price equals it.)
- PREDICTOR: the LAST PRE_PEAK yes_ask / no_ask for each bucket (the entry-time price,
  no look-ahead — pre-peak is hours before the converged label).
- Bin by ask; report realized YES/NO rate vs ask + per-share EV net of fee.

FLB signature: low-ask bins realized < ask (longshots OVERpriced → fade);
high-ask bins realized > ask (favorites UNDERpriced → buy). A flat curve
(realized ≈ ask everywhere) = efficient market = the strategy is an artifact.

    PYTHONPATH=/root/Klaus python3 analysis/weather/flb_calibration_curve.py
"""
from __future__ import annotations
import glob, json
from collections import defaultdict


def fee(p):  # prob-weighted taker fee on the traded price
    return 0.0125 * 4 * p * (1 - p)


def main():
    files = sorted(glob.glob("logs/shadow/hot/*/maker_shadow.jsonl"))
    # (day,city) -> bucket_tok -> list of (ts, phase, yes_ask, no_ask, yes_mid)
    obs = defaultdict(lambda: defaultdict(list))
    for f in files:
        day = f.split("/")[-2]
        for line in open(f):
            try:
                d = json.loads(line)
            except Exception:
                continue
            yb, ya = d.get("yes_bid"), d.get("yes_ask")
            nb, na = d.get("no_bid"), d.get("no_ask")
            if ya is None:
                continue
            ymid = ((yb + ya) / 2) if (yb is not None and ya is not None) else ya
            obs[(day, d["city"])][d["yes_tok"]].append(
                (d["ts"], d.get("phase"), ya, na, ymid, d["lo"], d["hi"]))

    # Build per-bucket (predictor ask, realized outcome)
    yes_rows = []   # (yes_ask, won)
    no_rows = []    # (no_ask, no_won)  no_won = 1 - won
    n_citydays = n_clean = 0
    for (day, city), buckets in obs.items():
        n_citydays += 1
        finals = {}   # tok -> final yes_mid
        for tok, rows in buckets.items():
            rows.sort(key=lambda r: r[0])
            finals[tok] = rows[-1][4]
        winners = [t for t, m in finals.items() if m is not None and m > 0.70]
        if len(winners) != 1:
            continue   # ambiguous / no clean winner — skip
        n_clean += 1
        win_tok = winners[0]
        for tok, rows in buckets.items():
            pre = [r for r in rows if r[1] == "PRE_PEAK"]
            if not pre:
                continue
            _, _, ya, na, _, lo, hi = pre[-1]   # last pre-peak snapshot
            won = 1 if tok == win_tok else 0
            if ya is not None and 0 < ya < 1:
                yes_rows.append((ya, won))
            if na is not None and 0 < na < 1:
                no_rows.append((na, 1 - won))

    def curve(rows, label):
        bins = [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, .5),
                (.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.0)]
        print(f"\n=== {label} calibration curve (n={len(rows)}) ===")
        print("ask_bin     mean_ask  realized   n      EV/sh(net fee)  signal")
        for lo, hi in bins:
            sub = [(a, w) for a, w in rows if lo <= a < hi]
            if len(sub) < 20:
                continue
            ma = sum(a for a, _ in sub) / len(sub)
            rr = sum(w for _, w in sub) / len(sub)
            ev = (rr - ma) - fee(ma)
            sig = "BUY +EV" if ev > 0.01 else ("fade/-EV" if ev < -0.01 else "efficient")
            print("[%.1f,%.1f)    %.3f     %.3f    %-5d  %+.4f        %s"
                  % (lo, hi, ma, rr, len(sub), ev, sig))

    print("city-days=%d  clean-winner city-days=%d (%.0f%%)"
          % (n_citydays, n_clean, 100 * n_clean / max(n_citydays, 1)))
    curve(yes_rows, "BUY_YES (predictor = pre-peak yes_ask)")
    curve(no_rows, "BUY_NO  (predictor = pre-peak no_ask)")


if __name__ == "__main__":
    main()
