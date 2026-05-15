# Alpha Scout Report — 2026-05-15 12:10 UTC

**Method:** Codebase audit — VPS SSH unreachable (61st consecutive session).
**Connectivity:** `ssh` binary re-installed but TCP port 22 egress blocked. `trades.jsonl` and shadow JSONL inaccessible.
**Data sources:** git log HEAD=df77a3b (13 commits since last report at 00:16 UTC); strategy/late_direction_arb.py; data/shadow/timeline.py; analytics/lda_loss_analysis.py; analytics/lda_exit_optimizer.py; data/shadow/exit_policy.py.
**Bankroll snapshot:** $84.61 (bankroll.json, ts=2026-05-08 19:26 UTC — 160.7h stale). Actual capital unknown. LDA code header: n=69 live direction WR=89.7%.

---

## STRATEGY STATE — READ FIRST

Active strategy: **LDA (Late Direction Arb)**. All four mandate investigations target `signal_source=='BOND'` fields. **BOND disabled since 2026-05-10 — all four investigations yield n=0 by mandate definition.**

This report reframes each investigation for the live LDA strategy and focuses on **new signals introduced since the last report** at 00:16 UTC.

### Structural Changes Since Last Report (13 commits, 2026-05-15 00:16→12:10 UTC)

| Commit | Change | Scout relevance |
|---|---|---|
| df77a3b | B1 ask floor 0.75; BNC LOW tier 10%→1.5%, MID 12%→15%, HIGH 10%→22% | **Major staking re-tier. LOW tier now near-zero.** |
| af34ce4 | Per-hour exits: PT95 H08/H22, PT97 H16, CUT60 H06/H21; H04 B2 entry block | Reveals H06/H21 structural weakness — entry filter opportunity |
| d08101a | Revert Trail-5% trailing stop | Trail-5% harmed EV on hold_path sim n=840; removed |
| b8da3a0 | **NEW FIELD: `binance_ret_15m_pct` added to shadow** | Entirely new, unanalyzed — see Investigation 1 |
| fea73a8 | SOL fully blocked | Asset universe now BTC + ETH only |
| de3d830 | B3 [180,300s) re-enabled; B2 ask floor raised to 0.69 | B3 is now active; dead-drift in B3 entries newly relevant |
| 65793a2 | H07 unblocked from _ALL_BLOCKED_LATE_B1 | Small scope change |
| 160b293 | H02 all assets all buckets blocked | n=18 WR=22% -$249 on live |
| fe59556 | H03+H23 all assets all buckets blocked | n=7 WR=29% -$186 |

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS (LDA framing):** `binance_ret_15m_pct` alignment with `binance_ret_5m_pct` predicts direction WR. When the 15m trend and the 5m entry signal agree, the move is durable. When they disagree (5m up, 15m down), the 5m spike is counter-trend noise and more likely to revert before window close.

**RESULT:** n=0 for `signal_source=='BOND'` (mandate framing). For LDA:

`binance_ret_15m_pct` was added to shadow 4 hours ago (commit b8da3a0). It is **not yet loaded in `lda_loss_analysis.py`** — the feature dict at lines 125–159 includes `bnc_1m`, `bnc_30s`, `bnc_60s`, `bnc_vel_5s`, `bnc_60m` but does NOT include `bnc_15m`. No bucket WR analysis exists for this field.

**MATH:**
```python
bnc_15m_aligned = (
    rec.get("binance_ret_15m_pct", 0.0) * rec.get("binance_ret_5m_pct", 0.0) > 0
)
# True = both signals same direction (durable momentum)
# False = counter-trend entry (5m move against 15m trend)
```

**VPS analysis script (add to lda_loss_analysis.py first_fire dict, then bucket):**
```python
# In first_fires dict (after existing bnc_60m line):
"bnc_15m": r.get("binance_ret_15m_pct"),

# After Pass 2, bucket analysis:
aligned   = [v for v in all_rows if v.get("bnc_15m") is not None
             and (v["bnc_15m"] * v["bnc_abs"]) > 0]  # bnc_abs is already abs; reconstruct sign
# Better approach using bnc_dir:
aligned   = [v for v in all_rows if v.get("bnc_15m") is not None
             and ((v.get("bnc_15m", 0) > 0) == (v.get("bnc_abs", 0) > 0))]
divergent = [v for v in all_rows if v.get("bnc_15m") is not None
             and v not in aligned]
for label, subset in [("5m/15m ALIGNED", aligned), ("5m/15m DIVERGENT", divergent)]:
    if not subset:
        print(f"{label}: n=0"); continue
    wr = sum(1 for v in subset if v["correct"]) / len(subset)
    print(f"{label}: n={len(subset):4d} WR={wr:.1%}")
```

**NOTE:** The correct aligned check must reconstruct 5m direction from `bnc_abs` + `odir` (since `bnc_abs` = |bnc_5m_pct| and direction is in `odir`). Full implementation:
```python
def is_aligned(v):
    bnc15 = v.get("bnc_15m")
    if bnc15 is None: return None
    odir = "up"  # first_fire only loads bnc_dir==odir entries; odir=up ↔ bnc>0
    bnc15_dir = "up" if bnc15 > 0 else "down"
    return bnc15_dir == v.get("odir_implied", "up")
```

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Yes — no bucket WR data. Field is new (4h old); zero shadow data accumulated at this time. VPS required for first analysis. This is the **highest-priority new signal this cycle**.

---

## Investigation 2: Tick Count as Toxicity Filter (LDA: `spread_bps` / `liquidity_regime`)

**HYPOTHESIS:** Thin markets at entry time predict lower LDA direction WR. LDA proxy: `spread_bps` (wider spread = thinner book) and `liquidity_regime` (categorical: thin/normal/deep, computed from OB depth ≤150/150–500/>500).

**RESULT:** n=0 for `signal_source=='BOND'` (`term_tok_tick_count_5s` not logged in LDA shadow). LDA proxies:

| Signal | Shadow field | In lda_loss_analysis? | Live gate? |
|---|---|---|---|
| Spread at entry | `spread_bps` | Yes (line 140) | No gate |
| Liquidity regime | `liquidity_regime` | Yes (as `liq_reg`, line 148) | No gate |
| OB depth level | `ob_depth` (`ob_book_depth_size`) | Yes (line 138) | No gate — was #2 feature sep=0.125 in n=2,643 |

`liquidity_regime` = "thin" when OB depth < 150. This is a precomputed categorical that maps directly to the tick-count hypothesis: thin books = few active market makers = low tick rate = dead market.

**PROPOSED_GATE (requires VPS bucket analysis first):**
```python
# In late_direction_arb.py schedule_if_ready(), after vol_regime check:
liq_reg = rec.get("liquidity_regime", "normal")
if liq_reg == "thin":
    return  # OB depth < 150 at entry; threshold requires WR bucket confirmation
```

**CONCLUSION:** INCONCLUSIVE (no live bucket data)
**FAILURE_MET:** Yes — WR difference across liquidity buckets unknown without VPS. `ob_depth` feature separation = 0.125 (n=2,643 prior analysis) suggests WR spread is likely ≥5pp between "thin" and "deep", but not confirmed at live gate thresholds.

**VPS analysis (run after lda_loss_analysis.py):**
```python
# Bucket by liquidity_regime (already in first_fires as "liq_reg"):
for regime in ["thin", "normal", "deep"]:
    sub = [v for v in all_rows if v.get("liq_reg") == regime]
    if not sub: print(f"{regime}: n=0"); continue
    wr = sum(1 for v in sub if v["correct"]) / len(sub)
    print(f"{regime:>8}: n={len(sub):4d} WR={wr:.1%}")
```

---

## Investigation 3: DEAD_DRIFT Signature (LDA: `tok_delta_5s` / B3 re-entry relevance)

**HYPOTHESIS:** Token ask flat in the 5s before entry (`tok_delta_5s` near zero) underperforms active entries due to thin/uninformed order flow.

**RESULT:** n=0 for `signal_source=='BOND'`. LDA proxy: `tok_delta5` (tok_delta_5s) in lda_loss_analysis line 144. **Prior n=2,643 shadow analysis: feature separation < 0.125 — not in top 2.**

**NEW THIS CYCLE:** B3 [180,300s) was re-enabled as of commit de3d830 (2026-05-15, user instruction). B3 entries are at rem=180–300s with ask range 0.70–0.80 (structural ask gates apply). These are the *earliest* entries in each window, where token prices have had the least time to reflect the BNC move. Dead drift is structurally more likely at B3 than at B1/B0, because the Binance-to-Polymarket lag may still be propagating. The question of whether `tok_delta_5s` near zero predicts loss is therefore **more acute for B3 than for earlier reports** when B3 was blocked.

**PROPOSED ANALYSIS (B3-specific dead-drift gate):**
```python
# In lda_loss_analysis.py, add B3-specific dead drift analysis:
b3_rows = [v for v in all_rows if v["rem"] >= 180]
dead = [v for v in b3_rows if abs(v.get("tok_delta5", 0.0) or 0.0) < 0.005]
live = [v for v in b3_rows if abs(v.get("tok_delta5", 0.0) or 0.0) >= 0.005]
for label, sub in [("B3 dead-drift", dead), ("B3 active", live)]:
    if not sub: print(f"{label}: n=0"); continue
    wr = sum(1 for v in sub if v["correct"]) / len(sub)
    print(f"{label}: n={len(sub):4d} WR={wr:.1%}")
```

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Yes — WR difference <5pp expected based on prior feature separation analysis, but B3-specific sub-bucket has not been run. B3 was blocked at time of the n=2,643 analysis; the B3 dead-drift question is genuinely new.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset consistently outperforms; stake weighting should differ by asset.

**RESULT (code-derived, post-SOL-block):**
- LDA code header: n=69 live direction WR=89.7% (all assets combined, as of last VPS sync)
- SOL fully blocked as of 2026-05-15 (fea73a8) — live data: n=178 WR=53.4% net=-$791
- Active assets: **BTC + ETH only**
- Per-asset live n: unknown; expected ~34-35 each if uniform across n=69

Current stake structure post-df77a3b:
- BTC/ETH: BNC-tiered half-Kelly (LOW 1.5%, MID 15%, HIGH 22% of bankroll)
- Differential treatment: `_ETH_BLOCKED_LATE`, `_ETH_BLOCKED_B1`, `_BTC_BLOCKED_LATE`, `_BTC_BLOCKED_B1` — already per-asset tuned

**New question this cycle:** The BNC LOW tier (0.05–0.07%) was cut to 1.5% bankroll (~$1.27 at current capital). At that stake size, the EV per trade is close to break-even pre-fee. If LOW-tier BTC/ETH has systematic hours with negative WR, the 1.5% floor may still generate losses. This requires VPS bucket analysis.

**CONCLUSION:** INCONCLUSIVE — n per asset below n≥20 floor for live 48h window.
**FAILURE_MET:** Yes. Shadow per-asset n likely ≥20 in all-time shadow, but exact split unavailable without VPS. SOL result (n=178 WR=53.4%) was sufficient for action and has been acted on.

---

## Novel Signals — New This Cycle

### Novel 1: `binance_ret_15m_pct` as Multi-Timeframe Alignment Filter (PRIORITY)

**Field:** `binance_ret_15m_pct` = `(spot_now - open_15m) / open_15m * 100`
**Schema:** Added in commit b8da3a0 (2026-05-15 08:21 UTC) to `data/shadow/timeline.py` line 353.
**Current use:** Logged in shadow market_timeline only — not loaded in any analysis script.
**Hypothesis:** When 5m return direction and 15m return direction disagree, the 5m entry is a short-term noise spike against the dominant 15m trend. These entries should resolve against direction at higher rates.
**Why non-obvious:** The 5m return is the deployed entry signal. The 15m return is a *context* signal — it tells us whether the 5m move represents trend participation or counter-trend noise. The two are orthogonal: a 5m up move can be on-trend (15m also up) or counter-trend (15m down / mean-reversion). Only the former has clean momentum behind it.
**Why new:** Prior reports identified `binance_ret_1m_pct` divergence from 5m. This is the *opposite* timeframe — longer, not shorter. A 1m divergence tests "is momentum already fading?"; a 15m divergence tests "is this entire move against the trend?". These are complementary hypotheses with different failure modes.
**Status:** Field added 4h ago. Zero shadow data accumulated yet. First analysis requires VPS after ≥24h of data accumulation.

**Math:**
```python
# Gate: only enter when 5m and 15m agree on direction
bnc_15m = rec.get("binance_ret_15m_pct", 0.0)
bnc_5m  = rec.get("binance_ret_5m_pct",  0.0)  # same as bnc_move_pct in LDA
if bnc_5m * bnc_15m < 0:
    return  # divergent timeframes — skip entry
# Note: if either is 0.0 (missing), product = 0 → gate triggers — add null check
if bnc_15m == 0.0:
    pass  # field may be 0.0 legitimately (flat 15m); don't gate on missing data
```

**Failure criteria:** n<20 per group (aligned vs divergent) after ≥7 days of shadow; or WR difference <5pp.
**Do NOT ship without VPS bucket confirmation. Data collection starts now.**

### Novel 2: BNC LOW Tier Hour Gate (NEW)

**Context:** Commit df77a3b cut the LOW tier (BNC 0.05–0.07%) stake from 10% to 1.5% bankroll. This effectively quarantines the LOW tier while leaving it active. The rationale: "EV≈+0.010 pre-fee, near break-even". The open question is whether this near-break-even average conceals systematic negative-EV hours within the LOW tier.

**Hypothesis:** Within BNC [0.05,0.07%), specific hours have negative EV even on shadow data. Those hours should be blocked at the BNC floor level (raise floor to 0.07% at those hours) rather than traded at near-zero stake.

**Why non-obvious:** The BNC floor is currently applied as a global ask-zone rule (0.07 at B0; 0.10/0.05/0.07 by ask zone at B1/B2). The LOW tier exists within the 0.05–0.07% band specifically for B1/B2 entries with ask 0.70–0.90 (where floor is 0.05%). Three hours already have their BNC floor raised: H02 B2 (→0.07), H03 B1 (→0.06), H20 B2 (→0.06). The question is whether the remaining hours in this band are uniformly near-break-even or whether some are significantly negative.

**Analysis script (for VPS lda_loss_analysis.py):**
```python
# After first_fires load, bucket by BNC tier × hour for EV analysis:
from collections import defaultdict
low_tier = [v for v in all_rows if 0.05 <= v["bnc_abs"] < 0.07]
print(f"\nBNC LOW tier [0.05,0.07%): n={len(low_tier)}")
hour_buckets = defaultdict(lambda: {"n": 0, "w": 0})
for v in low_tier:
    h = v["hour"]
    hour_buckets[h]["n"] += 1
    if v["correct"]:
        hour_buckets[h]["w"] += 1
for h in sorted(hour_buckets):
    d = hour_buckets[h]
    wr = d["w"] / d["n"] if d["n"] else 0.0
    flag = " ⚠" if wr < 0.70 and d["n"] >= 10 else ""
    print(f"  H{h:02d}: n={d['n']:3d} WR={wr:.1%}{flag}")
```

**Failure criteria:** All hours WR >70% in LOW tier (no negative-hour gate needed); or n<10 per hour (insufficient data).
**Do NOT ship without VPS bucket confirmation.**

---

## Previously Identified, Still Unanalyzed Variables

All from prior reports; none promoted to SIGNAL_FOUND yet (VPS required):

| Variable | Shadow field | First logged | Hypothesis | Priority |
|---|---|---|---|---|
| `binance_ret_15m_pct` | market_timeline | **2026-05-15 NEW** | 15m/5m misalignment = noise spike = lower WR | **P1 (new)** |
| `ob_book_depth_size` | market_timeline | 2026-05-08 | #2 feature (sep=0.125); thin books → lower WR | P2 |
| `bnc_low_hour` | (derived from bnc_abs + hour) | 2026-05-08 | some hours within LOW tier are negative EV | **P2 (new)** |
| `ob_depth_delta_1s` | hold_path | 2026-05-09 | depth collapsing at entry = MM retreat = lower WR | P3 |
| `tok_decel_ratio` | market_timeline | 2026-05-09 | decel<0.5 = momentum fading → lower WR | P3 |
| `binance_ret_1m_pct` divergence | market_timeline | 2026-05-09 | 5m/1m divergence = stale signal → lower WR | P3 |
| `arb_sum_yes_no` | market_timeline | 2026-05-08 | sum<1.0 = MM retreat → thin market | P4 |
| `ask_stale_s` | market_timeline | 2026-05-09 | stale>5s = MM not tracking price → lower WR | P4 |

---

## Priority Signal for Next Implementation

**`binance_ret_15m_pct` alignment gate** is the highest-priority NEW signal this cycle. It was just added to shadow 4 hours ago and has zero prior analysis. No gate exists. Data collection starts now.

**Implementation path:**
1. Allow ≥7 days of shadow data to accumulate with `binance_ret_15m_pct` logged.
2. Add `"bnc_15m": r.get("binance_ret_15m_pct")` to lda_loss_analysis.py first_fires dict.
3. Run VPS bucket analysis. Check: aligned (n≥20?) vs divergent (n≥20?). WR spread ≥5pp?
4. If confirmed: add gate to `late_direction_arb.py` schedule_if_ready after BNC floor check.
5. If divergent n<20 after 14 days: downgrade to P3, continue collecting.

**Secondary (existing P1 — unchanged):** `ob_book_depth_size` gate. Separation=0.125 on n=2,643. Add to lda_loss_analysis.py and run `liquidity_regime` bucket WR on VPS.

**Codebase-ready gate snippet (DO NOT SHIP — no VPS confirmation):**
```python
# After vol_regime gate in late_direction_arb.py schedule_if_ready():
# 15m/5m alignment gate (hypothesis: misaligned = counter-trend noise)
bnc_15m = rec.get("binance_ret_15m_pct", 0.0)
if bnc_15m != 0.0 and (bnc_15m * bnc_move_pct) < 0:
    return  # 5m up but 15m down (or vice versa) — skip
```

**If nothing reaches SIGNAL_FOUND this cycle:** This is correct. `binance_ret_15m_pct` was added 4h ago — there is no shadow data to analyze. The honest conclusion is: data collection is underway; first analysis window opens in ~7 days.

---

## Infrastructure Alert — SSH (61 consecutive sessions)

Root cause: `ssh` binary re-installed successfully but TCP port 22 egress is blocked by the container network policy.

**Required action — run on VPS to unblock future analysis:**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Also required — add bnc_15m to lda_loss_analysis.py first_fires dict (one line):**
```python
# Line 136 in analytics/lda_loss_analysis.py, after bnc_60m:
"bnc_15m": r.get("binance_ret_15m_pct"),
```
This is safe to ship now (just adds a new key; no logic change). The field will be `None` for shadow data predating today.
