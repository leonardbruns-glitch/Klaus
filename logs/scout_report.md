# Alpha Scout Report — 2026-05-14 00:13 UTC

**Method:** Codebase audit — VPS SSH unreachable (≥56th consecutive session, confirmed by e3396a6 "session 55")
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked. `trades.jsonl` and shadow JSONL inaccessible.
**Data sources used:** git log HEAD=fc5a87d; state_log.md; strategy/late_direction_arb.py; analytics/lda_loss_analysis.py; data/shadow/timeline.py; prior scout report 2026-05-13.
**Bankroll snapshot:** $84.61 (bankroll.json, ts=2026-05-08, 6 days stale). Actual USDC was $132.84 as of 2026-05-13 19:30 per state_log (CLOB get-balance-allowance).

---

## STRATEGY CONTEXT — READ FIRST

Active strategy: **LDA (Late Direction Arb)**, deployed 2026-05-12 21:41 UTC.
BOND has been disabled since 2026-05-10. All four mandated investigations use BOND-specific fields
(`term_tok_tick_count_5s`, `term_token_delta_5s` as raw price delta, `signal_source=='BOND'`).

**All four mandated investigations are INCONCLUSIVE on their original BOND framing (n=0).**
Pivot sections below remap each to its LDA-native equivalent using fields that DO exist in shadow data.

**Critical undeployed finding from 2026-05-13 19:30 (state_log):**
`ASK_FLOOR 0.60 → 0.80 + block SOL_UP = +$15.71 over n=83 vs −$131.32 baseline (n=172 total).`
Marked "NO DEPLOY pending user review." ASK_FLOOR still = 0.60 in live code as of HEAD (fc5a87d).
This is the most actionable existing signal. It is NOT a new discovery — it requires user authorization.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance 5s spot velocity at entry (`binance_vel_5s_pct`) predicts YES direction above
the baseline set by the 5m candle return alone.

**RESULT:**
`binance_vel_5s_pct` accumulated in shadow since commit 0f3fc21 (2026-05-10). The feature separation
analysis underlying the BNC-decay deployment (n=2,643 shadow windows, 2026-05-13 ~19:30) ranked features:

| Rank | Feature | Separation |
|------|---------|------------|
| 1 | `signed_binance_ret_5m` at entry tick | 0.661 |
| 2 | `ob_book_depth_size` | 0.125 |
| 3+ | All others (including `binance_vel_5s_pct`) | < 0.125 |

`binance_vel_5s_pct` was included in the analysis but did not rank in the top 2. Separation < 0.125.

**MATH:** `binance_vel_5s_pct = (spot_now - spot_5s_ago) / spot_5s_ago × 100` (percentage, 5-second window).
This is distinct from `binance_ret_5m_pct` (5-minute candle since open). Both measure direction but at
different time horizons. The 5m return is the primary signal AND the deployed BNC-decay filter — it subsumes
the directional information in vel_5s at the current threshold architecture.

**CONCLUSION:** INCONCLUSIVE — feature separation < 0.125 means weak signal, but WR bucket analysis
(vel_5s_signed > 0 vs < 0 within the already-confirmed bnc_5m > 0 population) has NOT been run.
Bucketed analysis may reveal a residual effect even at low separation. VPS script needed.

**FAILURE_MET:** Yes — WR difference across momentum direction buckets unknown; feature separation < 0.125
suggests it is likely < 5pp net of the primary bnc_5m filter, but this is not confirmed.

VPS analysis script (run at `/root/Klaus`):
```python
import json, glob, os, math
from collections import defaultdict

SHADOW_ROOT = "logs/shadow/hot"
STAKE = 5.0

resolutions = {}
for p in sorted(glob.glob(f"{SHADOW_ROOT}/*/window_resolution.jsonl")):
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            resolutions[(r["condition_id"], r["window_end_ts"], r.get("window_size_s", 300))] = r["moved_up"]

first_fire = {}
for p in sorted(glob.glob(f"{SHADOW_ROOT}/*/market_timeline.jsonl")):
    with open(p) as f:
        for line in f:
            try: r = json.loads(line)
            except: continue
            if r.get("record_type") != "market_timeline": continue
            wsz = r.get("window_size_s", 300)
            if wsz != 300: continue
            rem = r.get("seconds_to_resolution", 0.0)
            ask = r.get("best_ask", 0.0)
            bnc = r.get("binance_ret_5m_pct")
            vel = r.get("binance_vel_5s_pct")
            if not (8 <= rem <= 300) or not (0.60 <= ask <= 0.98): continue
            if bnc is None or abs(bnc) < 0.05: continue
            odir = r.get("outcome_dir", "")
            if ("up" if bnc > 0 else "down") != odir: continue
            cid = r.get("condition_id", ""); wend = r.get("window_end_ts", 0)
            key = (cid, wend, wsz)
            if key not in resolutions: continue
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {"rem": rem, "odir": odir, "bnc": bnc, "vel": vel,
                                   "ask": ask, "correct": (odir == "up") == resolutions[key]}

rows = list(first_fire.values())
# Bucket by SIGNED vel_5s (sign = bet direction)
buckets = defaultdict(lambda: {"n": 0, "w": 0})
for r in rows:
    v = r["vel"]
    if v is None: continue
    sv = v if r["odir"] == "up" else -v
    b = "<-0.03%" if sv < -0.03 else ("-0.03 to 0%" if sv < 0 else ("0 to +0.03%" if sv < 0.03 else "+0.03%+"))
    buckets[b]["n"] += 1
    if r["correct"]: buckets[b]["w"] += 1
for b in ["<-0.03%", "-0.03 to 0%", "0 to +0.03%", "+0.03%+"]:
    v = buckets[b]
    wr = v["w"]/v["n"] if v["n"] else 0
    print(f"{b:>20}: n={v['n']:4d} WR={wr:.1%}")
```

---

## Investigation 2: OB Depth as Toxicity Filter

**HYPOTHESIS (mandate: tick count; LDA proxy: `ob_book_depth_size`):**
Thin orderbooks (low top-3 depth) predict lower direction WR. Deep OBs signal liquid, informed-flow-aligned markets.

**RESULT:**
`ob_book_depth_size` = #2 feature in the full feature separation analysis (0.125). This is the single
most discriminating undeployed signal. No WR bucket breakdown has been published.

| Feature | Separation | Status |
|---------|------------|--------|
| signed_binance_ret_5m | 0.661 | DEPLOYED (BNC-decay) |
| ob_book_depth_size | 0.125 | **NOT deployed, no gate** |
| All others | < 0.125 | Not deployed |

Existing depth gates: SOL depth<100 block (state_log 2026-05-07), ETH depth<100, BTC depth<500
— but these are BOND-era (window_sniper.py/main.py), not LDA. LDA has NO depth gate currently.

**PROPOSED_GATE:** If bucket analysis shows WR difference ≥ 5pp between depth<100 and depth≥200:
add `ob_book_depth_size < 100 → skip` in `strategy/late_direction_arb.py` `schedule_if_ready()`.

**FAILURE_MET:** Unknown — bucket analysis not yet run.

VPS analysis script:
```python
# (load first_fire as above, add "depth": r.get("ob_book_depth_size") to first_fire dict)
from collections import defaultdict
buckets = defaultdict(lambda: {"n": 0, "w": 0})
for r in rows:
    d = r.get("depth") or 0
    b = "<100" if d < 100 else ("100-200" if d < 200 else ("200-500" if d < 500 else "500+"))
    buckets[b]["n"] += 1
    if r["correct"]: buckets[b]["w"] += 1
for b in ["<100", "100-200", "200-500", "500+"]:
    v = buckets[b]
    wr = v["w"]/v["n"] if v["n"] else 0
    avg_ask = sum(r["ask"] for r in rows if r.get("depth",0) < (100 if b=="<100" else 999)) / max(1, v["n"])
    ev = wr * STAKE * (1 - avg_ask) / avg_ask - (1 - wr) * STAKE
    print(f"{b:>8}: n={v['n']:4d} WR={wr:.1%} EV/trade={ev:+.3f}")
```

**CONCLUSION:** INCONCLUSIVE (bucket WR unknown). Promoted to **Priority 1** based on feature separation rank.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Token ask flat in the 5s before LDA entry (`tok_delta_5s` near zero) underperforms active
(moving) entries due to thin/uninformed order flow.

**RESULT:**
`tok_delta_5s` is logged in shadow as percentage change (commit 61ac630, 2026-05-09). The mandate's
`|term_token_delta_5s| < 0.005` raw-price threshold ≈ `|tok_delta_5s| < 0.6%` in percentage terms
(at avg ask ~0.83: 0.005/0.83 = 0.60%).

| Group | n | WR | Source |
|-------|---|----|--------|
| Dead drift (|tok_delta_5s| < 0.6%) | Unknown (VPS) | Unknown | shadow JSONL |
| Active (|tok_delta_5s| ≥ 0.6%) | Unknown (VPS) | Unknown | shadow JSONL |

`tok_delta_5s` was included in the feature separation analysis (n=2643) but did not rank in top 2.
Separation < 0.125 — directional difference likely small but bucket analysis not confirmed.

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Unknown — WR difference across dead-drift buckets not yet run. Feature separation
< 0.125 suggests WR spread is likely < 5pp, but the mandate criterion requires explicit confirmation.

VPS analysis script:
```python
# (load first_fire as above, add "tok_d5": r.get("tok_delta_5s") to first_fire dict)
dead  = [r for r in rows if abs(r.get("tok_d5") or 0) < 0.6]
active = [r for r in rows if abs(r.get("tok_d5") or 0) >= 0.6]
for label, subset in [("dead_drift |d5|<0.6%", dead), ("active |d5|>=0.6%", active)]:
    if not subset: print(f"{label}: n=0"); continue
    wr = sum(1 for r in subset if r["correct"]) / len(subset)
    print(f"{label}: n={len(subset):4d} WR={wr:.1%}")
```

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset consistently outperforms others; SOL_UP is the dominant loser.

**RESULT (from state_log 2026-05-13 19:30):**

| Asset/Dir | kline_pnl (n=172 total) | Notes |
|-----------|--------------------------|-------|
| ALL combined | -$131.32 total | WR=72.8% per-trade, 73.9% per-window |
| SOL_UP (blocked) | Dominant loser | Best filter: +block SOL_UP = +$15.71 improvement over n=83 |
| BTC | Unknown (VPS) | n=8 only in prior BOND_RNO analysis |
| ETH | Unknown (VPS) | Active |
| SOL | Unknown (VPS) | Post-fix (BOND_RNO 60→180s) data accumulating |

n=172 total across 3 assets (expected ~57 per asset) — n≥20 threshold likely met per asset,
but exact breakdown unknown.

**CONCLUSION:** PARTIAL SIGNAL — SOL_UP identified as dominant loser at n=83. INCONCLUSIVE on
per-asset WR breakdown (exact split on VPS only).

**FAILURE_MET:** No for SOL_UP finding (n=83 ≥ 20). Yes for full per-asset breakdown (exact split unknown).

VPS script:
```bash
cd /root/Klaus && python3 analytics/lda_live_performance.py
```

---

## Novel Variables — Not Yet Bucket-Analyzed

The following fields are logged in shadow JSONL since May 8-10 and were included in the full
feature comparison in `lda_loss_analysis.py`, but no bucket WR table has been published.
All had feature separation < 0.125 (below ob_depth) based on the BNC-decay analysis output.

| Variable | Shadow field | First logged | Hypothesis | Status |
|----------|-------------|--------------|------------|--------|
| `arb_sum_yes_no` | `arb_sum_yes_no` | 2026-05-08 (eba3c8c) | sum<1.0 = MM retreat = thin market → lower WR | **Unanalyzed at bucket level** |
| `tok_decel_ratio` | `tok_decel_ratio` | 2026-05-09 (61ac630) | decel<0.5 = momentum fading → lower WR | **Unanalyzed at bucket level** |
| `ask_stale_s` | `ask_stale_s` | 2026-05-09 (61ac630) | stale>5s = MM not tracking price → lower WR | **Unanalyzed at bucket level** |
| `vpin_score` | `vpin_score` | 2026-05-09 (61ac630) | high VPIN = informed flow = ambiguous WR direction | **Unanalyzed at bucket level** |

To analyze all at once on VPS: `python3 analytics/lda_loss_analysis.py` (reads shadow, compares all
features WIN vs LOSS, prints WR by ask×rem zone, per-asset breakdown).

---

## Priority Signal for Next Implementation

**Primary: Deploy OB Depth gate for LDA (if VPS bucket analysis confirms ≥ 5pp WR spread)**

`ob_book_depth_size` was the #2 discriminating feature (separation 0.125) in the n=2,643 shadow analysis.
No LDA gate exists for depth today. The BOND-era depth gates (SOL<100, ETH<100, BTC<500 in window_sniper.py)
do NOT apply to LDA. This is an implementable gate if data confirms.

**Variable name:** `ob_book_depth_size` (b3 + a3: sum of top-3 bid and ask quantity in shadow records)
**Math:** `ob_book_depth_size = sum(q for _,q in ob.bids[:3]) + sum(q for _,q in ob.asks[:3])`

Python gate (add to `late_direction_arb.py` `schedule_if_ready()` after the rem/ask checks):
```python
# OB depth gate — thin books suppress direction WR (feature_separation=0.125, n=2643)
ob_depth = rec.get("ob_book_depth_size", 999.0)
if ob_depth < 100:  # ~X% of signals; confirm threshold from bucket analysis
    return
```

**Failure criteria:** n<20 per depth bucket, or WR spread < 5pp between thin (<100) and normal (≥200).
Do NOT ship until VPS bucket analysis confirms.

---

**Secondary (user authorization required — NOT scout territory):**
`ASK_FLOOR 0.60 → 0.80 + block SOL_UP` was proposed 2026-05-13 19:30 (state_log). n=83. Impact: +$15.71
vs -$131 baseline (n=172). Still pending user review. ASK_FLOOR = 0.60 in live code.

---

## Infrastructure Alert — SSH (≥56 consecutive sessions)

Root cause: TCP port 22 egress blocked at sandbox network boundary. SSH binary absent.
**Required action (manual, on VPS):**
```bash
cd /root/Klaus
python3 analytics/lda_loss_analysis.py > /tmp/lda_loss_$(date +%H%M).txt
python3 analytics/lda_live_performance.py >> /tmp/lda_loss_$(date +%H%M).txt
cat /tmp/lda_loss_*.txt
# Then: git add logs/ && git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)" && git push
```
Every cycle without VPS sync delays actionable gate decisions by ~24h. The ob_depth gate, arb_sum bucket,
and asset-level WR split cannot be confirmed until this runs.
