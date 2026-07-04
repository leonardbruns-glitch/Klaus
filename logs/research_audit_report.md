# Klaus Research Audit — 2026-07-04

**Date:** 2026-07-04T10:30Z
**Snapshot:** 2026-07-04T10:17:46Z (age 13 min — fresh)
**System:** `active` | HEAD `aff5c01ec` | Cash: $40.96 (bankroll.json authoritative)
**Engine posture:** PAIR_FAV only (BAND_NO halted 07-02; standalone YES paused 07-03; SPRINT_LADDER armed 07-03 20:00 UTC, ~$45 deployed overnight)
**Specialist reports read:** exec_audit (07:07Z), calib_monitor (08:07Z), gatekeeper (09:07Z), pnl_ledger (00:39Z Jul 4)
**Data note:** git fetch/push times out in cloud container — mirror and report data accessed via GitHub MCP.

---

## 1. PRIMARY BOTTLENECK — PAIR_FAV firing rate = 0 today, RECYCLE099 pipeline seeding halted

**Bottleneck rank: turns/day = 0 on Jul 04** (exec_audit §6; calib_monitor §5)

The compounding formula is ROI/turn × turns/day × equity deployed. ROI/turn is excellent at +25.4% (RECYCLE099 convergence at 0.63-0.68 → 0.99). Turns/day is the binding variable: 0.31x average Jul 01-03, falling to **0 today**. No new PAIR_FAV entries today means no RECYCLE099 positions seeded, no convergence gains tomorrow.

**Mechanism chain (all sourced from specialist reports):**

1. **Band YES halted** (BAND_YES_LIVE_MIN_DOUT=9 since Jul 03 19:25). Correct: calib_monitor S3 alert persists — disp_ratio 0.817 (d+0 bound) / ~0.34 (d+2), 7+ consecutive days below 1.10 re-enable threshold. Resolved tape Jun 26-Jul 03: −$137/$303 staked (−45%).

2. **Band NO halted** (BAND_NO_ENABLED=False, Jul 02 EVOLVE rail-halt). Correct: 7d WR 39.2% at avg ask 0.655 → EV ≈ −8%. n=51.

3. **PAIR_FAV-only posture**: sum_gate (BAND_PAIR_SUM_MAX=0.90) rejecting **all** d+1 pair candidates today. exec_audit §3 confirms `pair_cands=0` vs `no_cands=17-18`. London d+1 today: YES ask ~0.45 + NO ask ~0.48 = sum ~0.93 > gate (calib_monitor §2 London detail). Not a misconfiguration — correct gate behavior on elevated d+1 sum_ask.

4. **Maker pool constrained to ≤$16.38.** MAKER_CASH_FRAC reduced 0.90→0.40 (Jul 03 20:05, SPRINT30 expansion state_log). On $40.96 cash: 0.40 × $40.96 = **$16.38 maker pool**. BAND_BASE_STAKE=$3 with BAND_BELL=(1.0, 0.45, 0.22) → typical 2-leg pair costs ~$8-9. Pool allows only 1-2 pairs even when sum_gate clears.

5. **SPRINT_LADDER deployed ~$45 overnight.** bankroll.json: $86.74 (00:39Z pnl_ledger) → $40.96 (10:17Z). Consistent with max stake = min(75%·$60, $45) — one SPRINT_LADDER shot consumed ~52% of prior-day equity. Cash reduction directly constrains RECYCLE099 pipeline via maker pool.

**Justification for bottleneck rank (turns/day over equity deployed, ROI/turn, calibration, dispersion):** ROI/turn is strong (+25.4%); the question is volume. Dispersion edge recovery and calibration staleness are upstream pre-conditions but are not immediately actionable (neither today's sum_gate clearance nor the isotonic refit resolves intraday). The turns/day collapse is the observable throttle on compounding right now.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

Derived from the four specialist reports' collective implications:

**A. RECYCLE099 pipeline is the only confirmed positive-EV flow — but maker pool is undersized**
- n=19 recycles, 100% profitable, $40.75 over 3 days, $2.14/trade avg (exec_audit §4)
- Current maker pool: $16.38 → supports ~1-2 PAIR_FAV entries/cycle vs 7-8/day at peak (Jul 01-02)
- **Expected delta:** Each additional PAIR_FAV entry seeded produces ~$2.14 in recycle profit 1-3 days later. Raising MAKER_CASH_FRAC from 0.40 to 0.65 adds ~$10 to the pool → 2-3 additional entries possible when sum_gate clears.
- **Confidence:** MEDIUM (depends on sum_ask returning below 0.90)
- **Effort:** LOW (single parameter, reversible; but **blocked** until sum_gate clears — irrelevant on a 0-fires day)

**B. City universe expansion (5→10 cities for PAIR_FAV, 15→31 for SPRINT_LADDER) — utilization unmeasured**
- 0 fires from new cities (gatekeeper §G2; Tokyo d0 sum=1.02 per exec_audit). Summer heat may systematically elevate sum_ask on new cities.
- **Expected delta:** 0 until market structure allows sum_ask < 0.90 on new-universe city pairs.
- **Confidence:** LOW (0 data points)
- **Effort:** ZERO (already done)

**C. THERMO_MAKER_NO formal retirement — gate hygiene, zero capital impact**
- n=125 external falsification pre-resolves the n=20 kill gate as REJECTED (state_log Jul 03 19:45; EV −9..+2%/share ≈ 0). Engine permanently off. Kill gate unreachable.
- **Expected delta:** 0 financial. Reduces gatekeeper ledger noise.
- **Confidence:** VERY HIGH
- **Effort:** MINIMAL (state_log entry + config update)

**D. M1_BETA_LOCKOUT revert (stalled DAY 7, gatekeeper §G6)**
- Rate=0, capacity=0 (all asks @0.999). Market has priced the lockout signal out. REVERT to 0.5°C floor does not restore capacity but closes a stale unvalidated slice.
- **Expected delta:** 0 financial. Stops the 22-day stall from continuing indefinitely.
- **Confidence:** HIGH
- **Effort:** LOW

**E. MAKER_CASH_FRAC=0.40 compresses RECYCLE099 pipeline to prioritize SPRINT_LADDER cash reserve**
- state_log Jul 03 20:05 confirms this is intentional — "ladder is mandate priority." Documented trade-off.
- The compounding tension: RECYCLE099 (validated positive flow, n=19) depends on PAIR_FAV seeding; PAIR_FAV seeding depends on maker pool; maker pool deliberately compressed.
- **Expected delta from reverting MAKER_CASH_FRAC to 0.65:** +$4-8/day in RECYCLE099 gains when sum_gate clears. Quantification pending Experiment 3 natural observation.
- **Confidence:** MEDIUM
- **Effort:** LOW (single parameter)

---

## 3. GATE PIPELINE REVIEW

**0 READY, 0 REJECTED this run** (gatekeeper_report — all gates collecting or structurally blocked).

| Gate | n | Status | Blocker | Unlock ETA |
|---|---|---|---|---|
| 1 BAND_YES | ~6,153 | CI-BLOCKED | Gamma API 403 from cloud | EVOLVE VPS join 11:23Z today |
| 2 BAND_NO_PAIR_FAV | ~275 | CI-BLOCKED | Gamma API 403 from cloud | EVOLVE VPS join 11:23Z today |
| 3 FILLED_VS_FIRED | ~112 | CI-BLOCKED | Gamma API 403 from cloud | EVOLVE VPS join 11:23Z today |
| 5 THERMO_MAKER_NO | 3 (n=125 ext) | pre-REJECTED | Human retirement decision | Immediate |
| 6 M1_BETA_LOCKOUT | 31 | AMBIGUOUS/stalled 22d | Market capacity=0 | Never (market-structural) |
| 7 SUM_POSTED 0.70-0.85 | ~3,036 | CI-BLOCKED | Gamma API 403 from cloud | EVOLVE VPS join 11:23Z today |

**EVOLVE at 11:23Z today is the single highest-leverage event.** `band_resolution_join.py` on VPS unblocks CI computation for Gates 1, 2, 3, 7 simultaneously. Both Gate 1 (n=6,153) and Gate 2 (n=275) are above the n=100 decision threshold — CI computation could flip either gate READY or REJECTED same-day.

**What would accelerate accumulation WITHOUT degrading expectancy:**
- Gates 1, 2: city universe already expanded to 10. No additional parameter change justified without EVOLVE CI result.
- Gate 5: Formal VOID now — evidence exists. Human decision only.
- Gate 6: Capacity=0 regardless of parameter changes. Revert closes unvalidated slice hygienically.

**Negative finding:** Do NOT lower BAND_EV_MIN or BAND_PAIR_SUM_MAX to accelerate gate accumulation — would trade gate quality for quantity on unvalidated parameters.

---

## 4. ASSUMPTION ATTACK

**Assumption 1: Dispersion premium persists (band earns by selling overpriced probability wings)**

Evidence today (calib_monitor §3):
- d+0 implied sigma (proxy, cleaned): 0.906°C vs 7d baseline 0.994°C → **−8.9%**, declining 3 consecutive readings
- d+2 operative estimate: ~0.34, re-enable threshold 1.10 → **−69% short**
- 7d ratio: 0.817 (d+0 bound), all 5 measured dates Jun 28-Jul 2 below 1.10
- **Jul 04 d+0: GAUGE DEGENERATE** — 0 finite ratio pairs (isotonic plateau assigns p_cal=0 to all non-winning buckets post-resolution; 8/10 POST_PEAK city-days n_nonzero=1)
- Badatmath (primary mirror): 7d net −$11,307 same week (state_log Jul 03 19:45)

**VERDICT: BROKEN — AND UNMEASURABLE.** Premium absent in all available data. Gauge methodology has failed — recovery cannot be detected even if occurring. Band correctly halted. Critical risk: 5-consecutive-day re-enable criterion is currently impossible to evaluate from cloud data.

**Assumption 2: Fills are not adversely selected (winner's curse)**

Evidence today (exec_audit §4):
- n=21 fills — INCONCLUSIVE (formal threshold n=40)
- 19/19 exit099 recycles profitable ($40.75) — inconsistent with severe adverse selection
- No resolution markout computable (VPS join required; EVOLVE today)

**VERDICT: AMBIGUOUS.** Positive directional evidence but no formal clearance. EVOLVE at 11:23Z is the unlock for Gate 3 (FILLED_VS_FIRED).

**Assumption 3: Recycle velocity scales with available maker-pool capital**

Evidence today:
- Recycle trend: Jul 01=8 → Jul 02=7 → Jul 03=4 → Jul 04=0
- MAKER_CASH_FRAC: 0.90 → 0.40 (Jul 03 20:05), maker pool: ~$55-78 (Jul 01-02 est.) → $16.38 today
- Cash: $86.74 → $40.96 overnight (SPRINT_LADDER $45 shot)

**VERDICT: THREATENED.** Declining trend is partly market cycle (elevated sum_ask) and partly structural (pool halved). Natural experiment Jul 04-06 will confirm which is binding. If sum_ask normalizes but recycles remain at 0-2/day → maker pool is the constraint.

---

## 5. MARKET CENSUS (day-of-month mod 3 = 1)

**Universe changes vs last known state:**

| Dimension | Prior | Current | Change date |
|---|---|---|---|
| BAND_CITY_ALLOW | 5 cities | 10 cities (+tokyo/seoul/taipei/shanghai/chongqing) | Jul 03 20:05 |
| SPRINT_LADDER universe | 15 cities | 31 cities (+16 global) | Jul 03 20:05 |
| PAIR_FAV fires from new cities | — | 0 (Tokyo d0 sum=1.02, rejected) | Jul 04 |

**Depth signals (exec_audit §3, Jul 01-04 STRUCT-BAND-Q tape):**
- `no_cands=17-18` stable on Jul 04: NO-side supply not the issue.
- `yes_books=0/50` on Jul 04 cycles: YES-side book discovery may be absent for new-universe cities. If pair_cands=0 is from missing YES books (not sum_gate), parameter fix is wrong remedy.
- d+1 London sum_ask today ≈ 0.93 (YES ~0.45 + NO ~0.48 from calib_monitor §2) — above 0.90 gate.

**Competitor census:**
- badatmath: 7d net −$11,307 per state_log Jul 03 19:45. Full band structure running, bleeding. DO NOT increase band breadth.
- No new competitor signals.

**New products:**
- No new weather market types detected. NHC named-storm count ladders flagged in state_log as Aug-Sept watchlist item — not yet live.

---

## 6. THREE EXPERIMENTS

### Experiment 1 — Market-bid dispersion proxy (restore gauge measurement)
**Hypothesis:** Using raw CLOB best-bid prices from band_struct.jsonl bypasses the stale 28-day isotonic map and restores non-degenerate dispersion ratio measurement, allowing the 5-consecutive-day re-enable criterion to be assessed.

**Data:** band_struct.jsonl bid columns per city-day (VPS shadow logger). Compute `impl_sigma = sqrt(Σ bid_i × (mid_i − Σ bid_i × mid_i)²)` per city-day; compare to `realized_dev` from resolution records.

**Time:** 1 day to implement; 5 days to accumulate re-enable criterion readings.
**Cost:** 0 capital. ~2h dev time on VPS.
**Success metric:** ≥5 allowlist cities produce finite disp_ratio values.

**Decision if ratio ≥ 1.10 for 5 consecutive days:** propose BAND_YES_LIVE_MIN_DOUT=2 re-enable for human review.
**Decision if ratio < 1.10 confirmed:** edge definitively absent; maintain pause; SPRINT_LADDER + RECYCLE099 are the only flows.

**Value of information: HIGH** — resolves largest strategic uncertainty at zero capital cost.

---

### Experiment 2 — PAIR_FAV sum_gate shadow (diagnose pair_cands=0 root cause)
**Hypothesis:** pair_cands=0 despite no_cands=17-18 is caused by either (a) sum_gate rejecting pairs at sum_ask 0.88-0.90, or (b) YES books absent for matched NO candidates. These require orthogonal fixes.

**Data:** Add rejection-reason logging to STRUCT-BAND-Q cycles (`pair_fail_reason=sum_gate|no_yes_book|no_match`). Run 2 days.
**Time:** 2 days shadow. ~1h implementation.
**Cost:** 0 capital.
**Success metric:** ≥10 rejections categorized by reason.

**Decision if sum_gate dominant:** lower BAND_PAIR_SUM_MAX 0.90→0.88 for human review.
**Decision if missing YES books dominant:** fix YES book discovery for new BAND_CITY_ALLOW cities.

**Value of information: MEDIUM-HIGH** — distinguishes two root causes with orthogonal remedies.

---

### Experiment 3 — MAKER_CASH_FRAC sensitivity (natural experiment Jul 04-06)
**Hypothesis:** The declining RECYCLE099 trend correlates with maker pool size, not market cycle alone.

**Data:** Daily bankroll.json cash at 00:00Z + STRUCT-BAND-Q `posted` count + trades.jsonl RECYCLE099 count. 3 data points exist; SPRINT_LADDER variability Jul 04-06 creates natural variance.
**Time:** 3-5 days observational. 0 implementation cost.
**Cost:** 0 capital.
**Success metric:** Spearman ρ > 0.7 between daily maker pool $ and next-day recycle count.

**Decision if confirmed:** raise MAKER_CASH_FRAC to 0.65 + add $15 hard floor for PAIR_FAV seeding. Propose for human review.
**Decision if no correlation:** RECYCLE099 is supply-limited by sum_ask structure. No parameter change.

**Value of information: MEDIUM** — confirms whether SPRINT30 expansion created structural RECYCLE099 drag.

---

## 7. SINGLE BEST ACTION

**Implement market-bid dispersion proxy in today's EVOLVE VPS run (11:23Z).**

**Evidence chain (three specialist reports):**
- calib_monitor S3: disp_ratio below 1.10 for 7+ consecutive days; gauge degenerate Jul 04 (0 finite ratio pairs). Re-enable criterion CANNOT BE ASSESSED from cloud data — not failing, literally uncomputable.
- calib_monitor S4: both isotonic configs stale 25-28 days; plateau (grid 0.30-0.90 → p_cal=0.3801) is the proximate cause. Isotonic refit is the permanent fix but takes weeks.
- exec_audit §6: turns/day = 0.31x. Recovery path requires band re-enable, which requires disp_ratio criterion, which requires measurement.
- gatekeeper §structural: EVOLVE at 11:23Z is the authorized VPS execution path for today.

**Concrete first step:** In today's EVOLVE daily run, add `compute_bid_dispersion()` to `compute_calib_metrics.py` on the VPS. Function reads band_struct.jsonl bid columns for BAND_CITY_ALLOW cities, computes `impl_sigma` from raw bids (no isotonic transform), logs `disp_ratio_bid = impl_sigma / realized_dev` per city-day. Output added to calib_monitor_report.md as "MARKET-BID DISPERSION (isotonic-free)" section. Run daily alongside existing S3 gauge.

**Why this over alternatives:**
- Retiring THERMO (PA-2) is valid but moves no compounding needle.
- Raising MAKER_CASH_FRAC is blocked today (sum_gate rejecting all pairs regardless of pool size).
- sum_gate shadow (Experiment 2) is second priority — addresses the symptom, not the upstream cause.
- Dispersion proxy addresses the root cause of the entire band being locked in an unobservable state.

---

## PROPOSED ACTIONS (human review)

**PA-1 [CRITICAL — today 11:23Z EVOLVE]:** Add market-bid dispersion proxy (`compute_bid_dispersion()`) to `compute_calib_metrics.py` on VPS. Restores re-enable measurement. Zero capital risk.

**PA-2 [HYGIENE — immediate]:** Formally retire Gate 5 (THERMO_MAKER_NO → VOID). n=125 falsification pre-resolves n=20 kill gate as REJECTED.

**PA-3 [HYGIENE — unactioned DAY 7]:** REVERT METAR_LOCKOUT_TEMP_FLOOR 0.2→0.5°C. Closes 22-day stall on unvalidated slice.

**PA-4 [MONITOR — natural experiment]:** Observe MAKER_CASH_FRAC=0.40 vs RECYCLE099 cadence Jul 04-06. If ρ > 0.7: propose raising to 0.65 + $15 hard floor for PAIR_FAV seeding capital.

**PA-5 [MONITOR — SPRINT_LADDER]:** Track first shot resolution. P(sleeve ruin) ≈ 97% per state_log Jul 03 20:00. If won: assess compound vs bank. If lost: assess remaining cash vs MAKER_CASH_FRAC floor impact.

**PA-6 [2-DAY SHADOW — Experiment 2]:** Add pair rejection-reason logging to STRUCT-BAND-Q. Diagnoses sum_gate vs missing YES books as pair_cands=0 root cause.

---

*No strategy code or gate flags were modified by this report. All state-altering items are under PROPOSED ACTIONS (human review) only.*
