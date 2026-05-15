# Alpha Scout Report — 2026-05-15 00:16 UTC

**Method:** Codebase audit — VPS SSH unreachable (59th consecutive session).
**Connectivity:** `ssh` binary absent in sandbox; TCP port 22 egress blocked. `trades.jsonl` and shadow JSONL inaccessible.
**Data sources:** git log HEAD=51c95cf; late_direction_arb.py; data/shadow/_schema/v1.json; analytics/multi_exit_replay.py; analytics/lda_loss_analysis.py; analytics/lda_snap60_scan.py; prior scout reports.
**Bankroll snapshot:** $84.61 (bankroll.json, ts=2026-05-08 19:26 UTC — 148.8h stale). Actual capital unknown. LDA code header: n=69 live direction WR=89.7%.

---

## STRATEGY CONTEXT — READ FIRST

Active strategy: **LDA (Late Direction Arb)**, running since 2026-05-12. **BOND disabled since 2026-05-10.**

All four mandated investigations target `signal_source=='BOND'` fields. **All four yield n=0.** This is the 59th consecutive session with this conflict; it will continue until BOND is re-enabled or the mandate is updated.

Since the last scout report (2026-05-14 00:13 UTC), 9 LDA commits landed:

| Commit | Change |
|---|---|
| 4a750a6 | lda: block B3 [180,300s) all assets all hours — user instruction |
| b554350 | lda: block BTC B3 H21 — shadow n=15, thin |
| 040251c | lda: cumulative bucket Kelly targets — B3=50% B2=75% B1=100% |
| 25d0d11 | lda: re-enable B3 ETH+BTC with new hour blocks; add SOL B1/B2 blocks |
| d02d7c8 | lda: block H05+H07 all assets B1+B2 — EV negative |
| 3076e41 | lda: block B3 [180,300s) all assets — user instruction |
| 12a700a | lda: per-asset window Kelly cap |
| 9774288 | lda: BNC-tiered half-Kelly replaces flat two-tier stakes |
| 6eabbac | lda: ETH B1/B3 + BTC B1/B2/B3 hour gates |

B3 [180-300s) is now **fully blocked all assets all hours** (user instruction 2026-05-14). This is the largest structural gate change since LDA launch.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance 5s spot velocity at entry (`binance_vel_5s_pct`) predicts YES direction above the baseline set by the 5m candle return alone.

**RESULT:**
n=0 for `signal_source=='BOND'` (BOND disabled 2026-05-10). LDA analog: `binance_ret_30s_pct` and `binance_ret_60s_pct` are logged in shadow (schema v1 fields 41-42) and loaded in `lda_loss_analysis.py` (lines 131-132). These shorter-horizon returns offer a finer-grained view of momentum at entry. No WR bucket analysis has been published for either.

A specific cross-signal hypothesis (not in prior reports): if `binance_ret_5m_pct > 0` but `binance_ret_1m_pct < 0`, the 1m trend is already reversing against the 5m direction bet. This 5m/1m **divergence flag** could identify entries where the price momentum has already peaked.

**MATH:**
```
binance_1m_divergence = (sign(binance_ret_5m_pct) != sign(binance_ret_1m_pct))
```
`binance_ret_1m_pct` is logged in shadow at every market_timeline tick (schema v1 field 53, loaded in lda_loss_analysis.py line 131).

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Yes — no bucket WR data. `binance_vel_5s_pct` had feature separation < 0.125 in n=2,643 shadow analysis (prior report). `binance_1m_divergence` is a new candidate, not yet analyzed. VPS required.

VPS analysis script (add to lda_loss_analysis.py first_fire loop):
```python
# In first_fire dict, add:
# "bnc_1m": r.get("binance_ret_1m_pct"),
# "bnc_5m": r.get("binance_ret_5m_pct"),

divergent = [r for r in rows if r.get("bnc_1m") is not None and
             (r["bnc_5m"] > 0) != (r["bnc_1m"] > 0)]
aligned   = [r for r in rows if r.get("bnc_1m") is not None and
             (r["bnc_5m"] > 0) == (r["bnc_1m"] > 0)]
for label, subset in [("5m/1m ALIGNED", aligned), ("5m/1m DIVERGENT", divergent)]:
    if not subset: print(f"{label}: n=0"); continue
    wr = sum(1 for r in subset if r["correct"]) / len(subset)
    print(f"{label}: n={len(subset):4d} WR={wr:.1%}")
```

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Thin/dead markets (low tick count before entry) predict lower direction WR. LDA proxy: `ob_book_depth_size` (absolute depth) and the new `ob_depth_delta_1s` (depth rate of change at entry).

**RESULT:**
n=0 for `signal_source=='BOND'` (`term_tok_tick_count_5s` not logged in LDA). LDA proxies:

| Signal | Shadow field | Feature rank (n=2,643) | LDA deployed? |
|---|---|---|---|
| OB depth level | `ob_book_depth_size` | **#2 (sep=0.125)** | No gate |
| Depth rate-of-change | `ob_depth_delta_1s` | Not yet ranked | No gate |

`ob_depth_delta_1s` is a **new candidate** not covered in prior reports. It measures `ob_book_depth_size - prev_depth` (logged in holdpath.py line 116; schema v1.json line 198). Currently used only as an **exit** signal in `multi_exit_replay.py` (depth_collapse < -50 for 2 consecutive ticks). The **entry-time** value of this field has never been analyzed as a filter. A negative delta at the moment of entry means market makers are actively pulling liquidity — a potential adverse selection signal distinct from absolute depth.

**PROPOSED_GATE (entry filter, requires VPS confirmation):**
```python
# In late_direction_arb.py schedule_if_ready(), after existing rem/ask checks:
depth_delta = rec.get("ob_depth_delta_1s", 0.0)
if depth_delta < -50.0:  # depth actively collapsing at entry — MM retreat signal
    return  # skip; threshold from bucket analysis
```

**CONCLUSION:** INCONCLUSIVE (no live bucket data)
**FAILURE_MET:** Yes for BOND framing (n=0). Unknown for LDA proxies — bucket WR split requires VPS.

VPS analysis script (`ob_depth_delta_1s` at first-fire):
```python
# Add to first_fire dict: "ddelta": r.get("ob_depth_delta_1s", 0.0)
from collections import defaultdict
buckets = defaultdict(lambda: {"n": 0, "w": 0})
for r in rows:
    d = r.get("ddelta", 0.0) or 0.0
    b = "collapse(<-50)" if d < -50 else ("shrinking(-50 to -10)" if d < -10 else
        ("flat(-10 to +10)" if d < 10 else "growing(10+)"))
    buckets[b]["n"] += 1
    if r["correct"]: buckets[b]["w"] += 1
for b in ["collapse(<-50)", "shrinking(-50 to -10)", "flat(-10 to +10)", "growing(10+)"]:
    v = buckets[b]
    wr = v["w"]/v["n"] if v["n"] else 0.0
    print(f"{b:>30}: n={v['n']:4d} WR={wr:.1%}")
```

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Token ask flat in the 5s before entry (`term_token_delta_5s` near zero) underperforms active entries due to thin/uninformed order flow.

**RESULT:**
n=0 for `signal_source=='BOND'`. LDA proxy: `tok_delta_5s` logged in shadow (schema field 56). Feature separation < 0.125 in prior n=2,643 analysis — not in top 2.

**Partially deployed** (new finding this cycle): LDA code header states "dead2 removed" — `ask[0.80,0.90)` entries with `rem>60s` are blocked (commit history, 2026-05-09). Evidence basis: n=27/80 shadow entries in this zone. This is a structural proxy for the dead-drift gate (no momentum → overpriced entries in the 0.80-0.90 band). The explicit `tok_delta_5s` bucket gate remains undeployed and unanalyzed.

Additional note: `tok_snap_60s` (token ask % change vs 60s ago) was analyzed in an ablation (main.py:2777) on n=499 and found to be r=0.71 correlated with `tok_delta_5s`, deemed redundant, and removed. The dedicated scan script `analytics/lda_snap60_scan.py` exists to re-analyze this for LDA specifically (ablation was BOND-era).

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Yes — WR difference across dead-drift buckets unknown. Feature separation < 0.125 suggests WR spread is likely < 5pp, but not confirmed at bucket level. "Dead2 removal" covers the structural case; explicit `|tok_delta_5s|` threshold gate is a marginal refinement at best.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset consistently outperforms; stake weighting should differ by asset.

**RESULT (code-derived):**
- LDA code header: n=69 live direction WR=89.7% (all assets combined, as of last VPS sync)
- Per-asset breakdown not accessible; expected ~23 trades per asset if uniform — below n=20 threshold individually
- Prior finding (state_log 2026-05-13 19:30, n=172 shadow): SOL_UP identified as dominant loser; blocking SOL_UP showed +$15.71 improvement over n=83
- Current code: `_SOL_BLOCKED_ALL = frozenset({7, 9})` plus extensive per-asset/hour gates — differential treatment already partially deployed

**CONCLUSION:** INCONCLUSIVE — n per asset below the n≥20 floor required by the mandate.
**FAILURE_MET:** Yes for 48h window (n<20 per asset likely). No for all-time shadow analysis (n≥20 per asset likely in shadow, but exact split unavailable without VPS).

---

## Novel Signals — New This Cycle

Two **new, unanalyzed candidates** identified from codebase audit. Neither was covered in prior reports.

### Novel 1: `ob_depth_delta_1s` as Entry Filter

**Field:** `ob_depth_delta_1s` = `ob_book_depth_size(t) - ob_book_depth_size(t-1s)`
**Schema:** shadow v1.json line 198; logged in data/shadow/holdpath.py line 116
**Current use:** Exit-only, in `multi_exit_replay.py` (depth_collapse = delta < -50 for 2 consecutive ticks)
**Proposed use:** Entry gate — skip if depth actively collapsing at the entry tick
**Hypothesis:** Negative depth delta at entry = MM pulling quotes = adverse selection in progress = lower WR
**Why non-obvious:** `ob_book_depth_size` (absolute level) already ranked #2 in feature analysis. `ob_depth_delta_1s` (rate of change) is orthogonal to it — a market can have high absolute depth but still be losing liquidity rapidly. The rate of change may predict short-horizon WR better than the level.
**Why not yet analyzed:** The field is logged in hold_path.jsonl (post-entry) but NOT in market_timeline.jsonl (pre-entry). The first-fire analysis scripts read market_timeline only. A VPS script would need to join hold_path.jsonl at the entry tick (first tick within the entry rem window) to market_timeline.jsonl. This is a schema gap, not a data gap.

**VPS feasibility check:**
```python
# Join hold_path first tick to market_timeline first-fire:
# hold_path.jsonl has (condition_id, window_end_ts, ts_s, ob_depth_delta_1s)
# Match on (cid, wend) where hold_path ts_s is within 2s of first_fire ts_s
```

**Failure criteria:** n<20 per depth-delta bucket, or WR spread <5pp between collapse (<-50) and stable.

### Novel 2: `binance_ret_5m` vs `binance_ret_1m` Divergence Flag

**Fields:** `binance_ret_5m_pct` (deployed signal) + `binance_ret_1m_pct` (logged, unused)
**Schema:** shadow v1.json lines 43 and 53; both loaded in lda_loss_analysis.py lines 131-132
**Hypothesis:** When the 5m return is positive (BET_UP) but the 1m return is negative, the momentum that created the signal has already reversed. These "stale momentum" entries may resolve against direction at higher rates.
**Why non-obvious:** The 5m return is the primary deployed signal. A 1m divergence check is a *time-decay* test of that signal — it measures whether the signal is still valid at entry time, not just at window open.
**Status:** `binance_ret_1m_pct` is collected in shadow and loaded in lda_loss_analysis.py but no bucket WR table has been published. The lda_wrong_cases.py script (on VPS) may have already examined it; unknown.
**Math:** `divergence = sign(bnc_5m) != sign(bnc_1m)`

**Failure criteria:** n<20 per group (aligned vs divergent), or WR difference <5pp.

---

## Previously Identified, Still Unanalyzed Variables

All from prior reports; none promoted to SIGNAL_FOUND yet (VPS required):

| Variable | Shadow field | First logged | Hypothesis | Priority |
|---|---|---|---|---|
| `ob_book_depth_size` | market_timeline | 2026-05-08 | #2 feature (sep=0.125); thin books → lower WR | **P1** |
| `arb_sum_yes_no` | market_timeline | 2026-05-08 | sum<1.0 = MM retreat → thin market | P2 |
| `tok_decel_ratio` | market_timeline | 2026-05-09 | decel<0.5 = momentum fading → lower WR | P3 |
| `ask_stale_s` | market_timeline | 2026-05-09 | stale>5s = MM not tracking price → lower WR | P3 |
| `vpin_score` | market_timeline | 2026-05-09 | high VPIN = informed flow = mixed direction for WR | P4 |

---

## Priority Signal for Next Implementation

**ob_book_depth_size gate for LDA** remains the highest-priority unimplemented signal from prior analysis. Separation=0.125 (n=2,643), no LDA gate exists.

**NEW this cycle:** Before implementing the depth *level* gate, first check `ob_depth_delta_1s` at entry time. If depth is actively collapsing (delta < -50), it is a stronger signal than the level alone. The two filters are complementary:
- Level gate (ob_book_depth_size < 100): skip thin markets
- Delta gate (ob_depth_delta_1s < -50): skip markets losing liquidity regardless of current level

**Python gate (add to late_direction_arb.py schedule_if_ready() after rem/ask checks):**
```python
# OB depth gates — skip thin or collapsing markets (feature_sep=0.125, n=2643 for level)
ob_depth = rec.get("ob_book_depth_size", 999.0)
ob_depth_delta = rec.get("ob_depth_delta_1s", 0.0)
if ob_depth < 100 or ob_depth_delta < -50:
    return  # confirm thresholds from bucket analysis first — do NOT ship without VPS confirmation
```

**Failure criteria:** n<20 per bucket; or WR spread <5pp between thin/collapsing and normal/stable.
**Do NOT ship without VPS bucket confirmation.**

**Secondary (requires VPS bucket analysis):** `binance_1m_divergence` — run lda_loss_analysis.py with the snippet from Investigation 1, check if WR difference between aligned and divergent groups reaches 5pp threshold on n≥20 per group.

---

## Infrastructure Alert — SSH (59 consecutive sessions)

Root cause: `ssh` binary unavailable in sandbox; port 22 egress blocked.

**The ob_depth_delta_1s entry analysis requires an additional join step** (hold_path.jsonl not currently queried by market_timeline-based scripts). Run this on the VPS before deploying:

```bash
cd /root/Klaus

# Step 1: standard feature analysis (covers ob_depth level + arb_sum + tok_decel + vpin)
python3 analytics/lda_loss_analysis.py > /tmp/lda_loss_$(date +%H%M).txt

# Step 2: new — depth delta at entry (hold_path join)
python3 - << 'EOF' >> /tmp/lda_loss_$(date +%H%M).txt
import json, glob, os
from collections import defaultdict
SHADOW_ROOT = "logs/shadow/hot"
resolutions = {}
for p in sorted(glob.glob(f"{SHADOW_ROOT}/*/window_resolution.jsonl")):
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            resolutions[(r["condition_id"], r["window_end_ts"])] = r["moved_up"]
first_fire = {}
for p in sorted(glob.glob(f"{SHADOW_ROOT}/*/market_timeline.jsonl")):
    with open(p) as f:
        for line in f:
            try: r = json.loads(line)
            except: continue
            if r.get("record_type") != "market_timeline": continue
            rem = r.get("seconds_to_resolution", 0.0)
            ask = r.get("best_ask", 0.0)
            bnc = r.get("binance_ret_5m_pct")
            if not (8 <= rem <= 300) or not (0.60 <= ask <= 0.98): continue
            if bnc is None or abs(bnc) < 0.05: continue
            odir = r.get("outcome_dir", "")
            if ("up" if bnc > 0 else "down") != odir: continue
            cid = r.get("condition_id", ""); wend = r.get("window_end_ts", 0)
            key = (cid, wend)
            if key not in resolutions: continue
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {"rem": rem, "odir": odir, "ts": r.get("ts_s", 0),
                                   "correct": (odir=="up") == resolutions[key]}
# Join hold_path at entry tick
for p in sorted(glob.glob(f"{SHADOW_ROOT}/*/hold_path.jsonl")):
    with open(p) as f:
        for line in f:
            try: r = json.loads(line)
            except: continue
            cid = r.get("condition_id", ""); wend = r.get("window_end_ts", 0)
            key = (cid, wend)
            if key not in first_fire: continue
            if "ddelta" in first_fire[key]: continue  # already joined
            if abs(r.get("ts_s", 0) - first_fire[key]["ts"]) <= 3:
                first_fire[key]["ddelta"] = r.get("ob_depth_delta_1s", None)
rows = [v for v in first_fire.values() if v.get("ddelta") is not None]
print(f"\nob_depth_delta_1s at entry — n with joined hold_path: {len(rows)}")
buckets = defaultdict(lambda: {"n": 0, "w": 0})
for r in rows:
    d = r["ddelta"]
    b = "collapse(<-50)" if d < -50 else ("shrink(-50:-10)" if d < -10 else ("flat" if d < 10 else "grow(10+)"))
    buckets[b]["n"] += 1
    if r["correct"]: buckets[b]["w"] += 1
for b in ["collapse(<-50)", "shrink(-50:-10)", "flat", "grow(10+)"]:
    v = buckets[b]
    wr = v["w"]/v["n"] if v["n"] else 0.0
    print(f"{b:>25}: n={v['n']:4d} WR={wr:.1%}")
EOF

# Step 3: push logs to repo
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)"
git push origin claude/find-lag-parameter-rFQ0N
```
