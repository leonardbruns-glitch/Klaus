"""Forward calibration monitor — re-test the cited YES-overconfidence findings on
CLEAN Gamma resolution, post-contamination-fix.

The "raw p 4.3x overconfident / single modal bucket 26% vs model-claimed 53%"
findings were measured while the σ-collapse contamination (running_max → M0 → σ floor)
was INFLATING model confidence. This tool recomputes them against Gamma-settled highs
(logs/weather/forecast_actuals_gamma.jsonl, built by reconcile_actuals_gamma.py) so we
can see what the calibration actually is now, per the n>=100 rule.

Truth source = Gamma settlement (the only real-money oracle). Model side = the live
pricer eval log p_cal (logs/shadow/hot/<date>/stwa_pricer_eval.jsonl). One snapshot per
(city, valid_day, bucket): the LAST PRE_PEAK eval (the window YES is gated to, and where
the overconfidence claim lives).

Metrics:
  * modal-bucket: mean(claimed p_cal of the argmax bucket) vs realized WR  -> overconfidence
  * Brier + reliability table (ECE) over all active buckets
  * split pre/post the 2026-06-04 13:45 UTC σ-collapse fix (commit 14505049)

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.forward_calibration
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.forward_calibration --phase PRE_PEAK
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from analysis.weather.stations import STATIONS

ROOT = Path(__file__).parent.parent.parent
SHADOW = ROOT / "logs" / "shadow" / "hot"
CORPUS = ROOT / "logs" / "weather" / "forecast_actuals_gamma.jsonl"
FIX_TS = 1780580700.0          # 2026-06-04 13:45 UTC — σ-collapse fix (commit 14505049)


def load_corpus() -> dict[tuple[str, str], float]:
    """(slug, valid_day) -> Gamma-settled daily high °C."""
    out = {}
    if not CORPUS.exists():
        return out
    for line in CORPUS.open():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "actual" and r.get("wu_high_c") is not None:
            out[(r["city_slug"], r["valid_day"])] = float(r["wu_high_c"])
    return out


def local_day(ts: float, slug: str) -> str:
    st = STATIONS.get(slug)
    tz = ZoneInfo(st.tz) if (st and st.tz) else timezone.utc
    return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")


def iter_evals(phase_filter: str | None):
    for day_dir in sorted(SHADOW.glob("2026-*")):
        f = day_dir / "stwa_pricer_eval.jsonl"
        if not f.exists():
            continue
        for line in f.open():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if phase_filter and r.get("phase") != phase_filter:
                continue
            yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="PRE_PEAK", help="phase to snapshot (default PRE_PEAK)")
    args = ap.parse_args()

    corpus = load_corpus()
    if not corpus:
        print("no Gamma corpus — run reconcile_actuals_gamma.py --backfill ... --write first")
        return

    # last snapshot per (city, valid_day, lo, hi): keep the eval with max ts
    snap: dict[tuple, dict] = {}
    for r in iter_evals(args.phase):
        city = r.get("city")
        ts = r.get("ts")
        if city is None or ts is None:
            continue
        vday = local_day(ts, city)
        key = (city, vday, round(r["lo"], 2), round(r["hi"], 2))
        if key not in snap or ts > snap[key]["ts"]:
            snap[key] = r

    # join to Gamma truth; build per-bucket records + per-city-day modal pick
    buckets: list[dict] = []
    cityday_rows: dict[tuple, list] = defaultdict(list)
    for (city, vday, lo, hi), r in snap.items():
        high = corpus.get((city, vday))
        if high is None:
            continue
        win = 1 if (lo <= high <= hi) else 0
        rec = {"city": city, "day": vday, "lo": lo, "hi": hi,
               "p": float(r.get("p_cal", 0.0)), "win": win, "ts": r["ts"]}
        buckets.append(rec)
        cityday_rows[(city, vday)].append(rec)

    if not buckets:
        print("no (city,day) overlap between pricer evals and Gamma corpus yet.")
        return

    def report(tag: str, recs: list[dict], cds: dict):
        if not recs:
            print(f"\n[{tag}] no data")
            return
        p = np.array([b["p"] for b in recs])
        w = np.array([b["win"] for b in recs])
        brier = float(np.mean((p - w) ** 2))
        # modal bucket per city-day
        claimed, realized, n_cd = [], [], 0
        for (_, _), rows in cds.items():
            active = [x for x in rows if x["p"] > 0]
            if not active:
                continue
            m = max(active, key=lambda x: x["p"])
            claimed.append(m["p"])
            realized.append(m["win"])
            n_cd += 1
        print(f"\n[{tag}]  bucket snapshots={len(recs)}  city-days={n_cd}  Brier={brier:.4f}")
        if n_cd:
            cl, rl = float(np.mean(claimed)), float(np.mean(realized))
            ratio = cl / rl if rl > 0 else float('inf')
            gate = "" if n_cd >= 100 else f"  [n={n_cd}<100: PROVISIONAL, do not act]"
            print(f"  MODAL bucket: claimed p={cl:.3f}  realized WR={rl:.3f}  "
                  f"overconfidence={ratio:.2f}x{gate}")
        # reliability (deciles over active buckets)
        act = [(b["p"], b["win"]) for b in recs if b["p"] > 0.02]
        if act:
            print("  reliability (active buckets, p>0.02):")
            print(f"    {'p_bin':>10} {'n':>5} {'mean_p':>7} {'win_freq':>9}")
            ap_, aw = np.array([x[0] for x in act]), np.array([x[1] for x in act])
            ece = 0.0
            for lo_b in np.arange(0.0, 1.0, 0.1):
                msk = (ap_ >= lo_b) & (ap_ < lo_b + 0.1)
                if msk.sum() == 0:
                    continue
                mp, wf, nb = ap_[msk].mean(), aw[msk].mean(), int(msk.sum())
                ece += (nb / len(ap_)) * abs(mp - wf)
                print(f"    [{lo_b:.1f},{lo_b+0.1:.1f}) {nb:5d} {mp:7.3f} {wf:9.3f}")
            print(f"    ECE={ece:.4f}")

    pre = [b for b in buckets if b["ts"] < FIX_TS]
    post = [b for b in buckets if b["ts"] >= FIX_TS]
    pre_cd = {k: v for k, v in cityday_rows.items() if v and v[0]["ts"] < FIX_TS}
    post_cd = {k: v for k, v in cityday_rows.items() if v and v[0]["ts"] >= FIX_TS}

    days = sorted({b["day"] for b in buckets})
    print(f"phase={args.phase}  Gamma corpus city-days={len(corpus)}  "
          f"joined day span {days[0]}..{days[-1]}")
    report("ALL", buckets, cityday_rows)
    report("PRE-fix (σ-collapse contaminated)", pre, pre_cd)
    report("POST-fix (2026-06-04 13:45+)", post, post_cd)
    print("\nNOTE: pricer reflects the σ-collapse fix only — the Gamma-actuals MATRIX "
          "refit is not yet deployed. Re-run as post-fix days settle toward n>=100.")


if __name__ == "__main__":
    main()
