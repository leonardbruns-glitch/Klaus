# Klaus Research Audit — 2026-07-18T1011Z

**Generated:** 2026-07-18T10:11Z (automated)
**Reports consumed:**
- exec_audit_report.md — 2026-07-18T07:09Z ✓
- calib_monitor_report.md — 2026-07-18T08:11Z ✓
- gatekeeper_report.md — 2026-07-18T09:11Z ✓
- pnl_ledger_report.md — 2026-07-17T23:37Z ✓ (<36h)

**Snapshot:** 2026-07-18T10:11:35Z (age < 6h ✓) | **System:** active ✓
**Capital:** $37.57 | **Band:** DARK day 12 | **Sniper kill-watch:** 18/18W clean (day 2)
**Sole live revenue engine:** UPDOWN sniper (candidate P_MIN≥0.995, Kelly 0.50)

---

## 1. Primary Compounding Bottleneck

**Fill rate / market cadence — 21.7% FOK miss rate (5 of ~23 attempted fires on Jul-17) and ~1 qualifying market/hr.**

Compounding equation breakdown (from pnl_ledger Jul-17):
- ROI/turn: 3.62% (sniper-only 3.77%)
- Turns/day: 6.37× ($202.8 fills / $31.83 avg equity)
- Equity deployed: $37.57, scaling correctly via Kelly ($13.7→$18.1 clip by end of day)

Multiplier levers in descending binding order today:

| Lever | Current state | Marginal value | Binding? |
|---|---|---|---|
| Fill rate | 78.3% (5 FOK misses) | +$0.58/recovered miss at $16 clip | **YES — primary** |
| Market cadence | ~1 qualifying/hr | +3.62% × Kelly clip per added turn | **YES — co-primary** |
| ROI/turn | 3.62% | stable, P_MIN constraint correct | No |
| Equity deployed | $37.57 | Kelly already deployed; growing | No |
| Capital | $37.57 | growing from sniper, not the ceiling | No |

**Quantified drag:** 5 misses/day × 3.62% ROI/turn × ~$16 avg clip = ~$2.90/day in foregone compounding — roughly half of yesterday's +$7.34 gain. At 26%/day compound rate (unsustainable but illustrative), each missed turn represents ~$0.58 → $1.16 in second-order compounding loss within 24h.

**Source:** pnl_ledger — "Binding constraint: fill rate (78.3%, 5 FOK misses at $0 cost) and market cadence (~1 fire/hr in observed window). Not capital, not edge." exec_audit confirms 14-23 sniper fills/day (Jul 15-17) at consistent entry/exit spreads, no adversarial degradation.

---

## 2. Existing-System Optimization

What the four reports collectively imply:

### a. FOK Miss Root-Cause Diagnosis [HIGH impact, LOW effort]
- **What:** 5 FOK misses on Jul-17. All at zero cash cost but full compounding drag. FOK at p=0.87-0.99 should fill near-instantly unless (i) price moved past limit by order submission, or (ii) order routing has >1s latency, or (iii) P_MIN was met at signal time but not at submit time.
- **Expected delta:** +2-3 recovered turns/day if latency is the cause → +$1.16-$1.74/day at current capital → +3-5%/day compound improvement.
- **Confidence:** medium (cause unknown until instrumented).
- **Effort:** 1 dev session to add `ts_signal`, `ts_order_submit` fields to sniper log; 24h to accumulate.

### b. Anomalous MAKER SELL Fill Classification [GATE UNBLOCKING, LOW effort]
- **What:** 2 unclassified MAKER SELL@0.92-0.96 on record (Jul-16 21:39Z token 1399483673820402; Jul-18 00:54Z token 2664940529472113 paired with BUY@0.08×44.9sh token 7094108612094851). G3 n=75 frozen pending classification. WC gap confirmed (sim ROI +7.6% vs filled -75.8%, CI entirely negative).
- **Expected delta:** unblocks G3 progression and either confirms band-system WC (closing the re-enable argument) or reveals benign pair-strategy explanation. Highest VOI of any non-code action available.
- **Confidence:** high the classification matters; outcome unknown until done.
- **Effort:** 30min Polymarket UI token lookup (gatekeeper flags this overdue twice).

### c. STWA Shadow Maker Orphan Position Tracking [DATA INTEGRITY, ZERO cost]
- **What:** $8.06 in BUY@0.02-0.06 shadow-maker fills open and untracked (pnl_ledger Section 1): tokens 4095117562509625 ($3.50), 1055101008834022 ($3.00), 1046907088381323 ($1.56). Logged as "UNTRACKED FILL" in WS. `open_positions=0` in position system — these are invisible to risk management.
- **Risk:** if they resolve YES (unlikely at 2-6¢ implied) = large unbooked upside. If NO = silent loss absorbed from capital already deployed. Position system underreports risk while these are open.
- **Expected delta:** data integrity — correctly accounting for ~18% of current capital ($8.06/$37.57) in untracked exposure. Also sets baseline for whether shadow-maker orphan orders are positive or negative EV.
- **Confidence:** high this needs attention; outcome depends on resolution (d+1 = today, d+2 = Jul-19).
- **Effort:** track by checking resolution of the 3 token markets in next 24-48h.

### d. Disk Space Monitoring [RISK MITIGATION]
- **What:** System disk at 98% full (90G/97G, 3GB free per today's snapshot). Yesterday's pnl_ledger reported 92G/1GB — improvement suggests cleanup occurred overnight (2G freed). Still critical: shadow logs growing ~0.1MB/session each, 18+ active shadow loggers.
- **Risk profile:** reduced vs yesterday but not resolved. If log writes fail silently, all four scheduled report pipelines become stale without alert.
- **Expected delta:** prevents log corruption. No compounding upside, but prevents compounding destruction.
- **Effort:** 15-30min SSH prune of shadow logs >7d (only 5-day retention required per SNAPSHOT.md spec).

---

## 3. Gate Pipeline Review

From gatekeeper_report 2026-07-18T09:11Z:

**No gates hit READY or REJECTED this cycle. No status changes.**

| Gate | Status | Live n | Shadow n | CI | Nearest path |
|---|---|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | 934 | +154 shadow | [-10.9,+21.1] | Blocked (WC confirmed; shadow CI uncountable) |
| G2b PAIR_FAV_YES | COLLECTING | 9 | — | — | ~8.3d from re-enable; blocked by capital floor |
| G2c PAIR_FAV_NO | COLLECTING | 9 | — | — | same |
| G3 FILLED_VS_FIRED | WATCH_ITEM | 75 (frozen) | — | [-75.0,-34.2] | Unfreeze requires classifying 2 anomalous SELLs |
| G4 BASKET_EXIT | VOID | — | — | — | Permanent |
| G5 THERMO_MAKER | REJECTED | 125 | — | [-9.0,+2.0] | — |
| G6 M1_BETA_LOCKOUT | REJECTED | 31 | — | [-20.6,+24.4] | — |
| G7 SUM_POSTED [0.70,0.85] | AMBIGUOUS | 382 | +100 shadow | [-11.4,+38.9] | Blocked (WC confirmed; shadow CI = upper bound only) |

**Structural dead-end on band gates:** G2b/G2c require n=40 live fires, which requires BAND_LIVE=True, which requires capital ≥ ruin floor ($89.16). At $37.57 (42.1% of floor), band re-enable is mechanically blocked regardless of gate status. Recovery path: sniper compounds to $89.16. At Jul-17's +26%/day rate (exceptional): ~4 trading days. At conservative +5%/day: ~35 days.

**Winner's curse blocker (hard rule):** G1 and G7 shadow CI cannot be cited as supporting band re-enable. G3 WC gap confirmed (n=75, CI entirely negative). Any band re-enable case must first resolve the WC gap — i.e., explain why filled ROI was -75.8% vs simulated +7.6%.

**Acceleration without degrading expectancy:** No valid breadth/depth lever exists while BAND_LIVE=False. The one unblocking action available: classify G3 anomalous MAKER SELL fills (30min, zero risk) to unfreeze G3 n from 75 and clarify whether the WC blocker is structural or a classification artifact.

---

## 4. Assumption Attack

The three load-bearing assumptions of the band system today:

### A. Dispersion premium persists (market-implied sigma > true sigma ~1.3°C)
- **7d evidence:** S3-d16 ALERT — disp_ratio7 ≈0.70, 16 consecutive days below 1.10 threshold (calib_monitor). All 6 prior monitoring days: ratio 0.652–0.765, 0 rows above 1.10.
- **NEW on 07-17 (first recovery signal):** 2 of 23 fire rows exceeded 1.10 for the first time: Wuhan d0 ratio=1.183 (mode_ask 0.255), Chengdu d0 ratio=1.136 (mode_ask 0.265). Asia d0 daily median improved to 0.841 from trailing ~0.744.
- **d+1 posture:** fully sum-gated every day (all BAND_CITY_ALLOW cities Σask≥0.85 = exec_audit confirms zero d+1 viable shadow fires). d+1 edge does not exist in current market regime.
- **d+2 posture:** 5-9 shadow fires/day, ratio ≈0.57 — still deeply inverted.
- **Verdict: THREATENED.** Assumption fails system-wide. Recovery signal is real but localized (2 cities, d0 only, mode_ask≤0.265 tier). 3-5 sessions of sustained multi-city improvement required before posture revision. Band correctly dark.

### B. Fills are not adversely selected vs simulated fires
- **Evidence:** G3 WATCH_ITEM confirmed — sim ROI +7.6% vs actual filled ROI -75.8% (n=75), gap -83.4pp, CI entirely negative [-75.0, -34.2]. Winner's curse fully confirmed at decision-grade n.
- **New data point (Jul-18 gatekeeper):** 2nd anomalous MAKER SELL@0.92-0.96 on record, pattern: SELL-high + BUY-low on likely complementary legs. Still unclassified.
- **Verdict: BREACHED** for band maker. The fills we receive are systematically the adversely-selected tail of available fire opportunities. This cannot be fixed by parameter tuning — it is a structural property of maker quoting in competitive markets. Note: this assumption is irrelevant to UPDOWN sniper (different mechanism, taker-initiated fills near resolution events, no adverse selection evidence).

### C. Recycle velocity scales (band capital cycles fast enough to compound meaningfully)
- **Evidence:** vacuous — BAND_LIVE=False since Jul-6 (day 12). Zero live cycles. Shadow engine shows 14-19 fire candidates/day (exec_audit), which represents the potential pool, but no actual recycle cadence to measure.
- **Verdict: UNTESTABLE.** The shadow engine's d+2 cadence (5-9 fires/day at $3 BAND_BASE_STAKE = ~$15-27/day notional if live) would represent meaningful velocity at current capital — but the WC gap means any recycle would be -EV until that gap is resolved.

**Summary table:**

| Assumption | Verdict | Key number |
|---|---|---|
| Dispersion premium persists | THREATENED | disp_ratio7≈0.70; 2/23 rows recovered Jul-17 |
| Fills not adversely selected | BREACHED | filled ROI -75.8% vs sim +7.6%, CI [-75,-34] |
| Recycle velocity scales | UNTESTABLE | BAND_LIVE=False day 12; shadow=14-19 candidates/day |

---

## 5. Market Intelligence — Competitor Posture (day 18 mod 3 = 0)

**Badatmath delta (gatekeeper watch):** Net=+0 in 24h. Configuration stable, no new city additions observed. Badatmath's band system remains LIVE (no wind-down observable from shadow tracking). Their capital estimated well above our $89.16 ruin floor — their BAND_LIVE gate is not triggered. Their PAIR_FAV fills at YES $0.45-0.70 / NO paired continue.

**Competitive niche analysis (from exec_audit fill tape):**
- Sniper pattern: TAKER BUY@0.87-0.99 → TAKER SELL@0.99-0.999 within 1-3 min (confirmed pairs on Jul-16 and Jul-17). This is the high-confidence near-resolution arbitrage pattern.
- No evidence of front-running on sniper fills: entry/exit spreads are consistent, no sign of adversarial participants degrading fill quality in the sniper domain.
- CLAUDE.md baseline: "73% of arb profits go to sub-100ms bots." However, near-resolution binary certainty markets (P≥0.995) are structurally different from price-discovery arb: the speed advantage is less relevant when the outcome is ~certain. Our competitive moat is selectivity (P_MIN 0.995 filter), not speed.

**Shadow-maker counterpart observation:** The BUY@0.02-0.06 shadow-maker fills (3 events Jul-17) show other participants selling cheap YES into our resting maker bids. These could be: (a) bots liquidating stale long YES positions before resolution, (b) bots delta-hedging paired NO positions, or (c) adverse selection from informed sellers. Experiment 3 below will disambiguate.

**Leaderboard wallet teardown:** data-api access unavailable in sandbox (git fetch timeout, network proxy blocks git protocol). Unable to pull specific wallet analytics beyond what's observable in maker fill tape. No additional intelligence available this cycle on top-wallet behavior.

---

## 6. Three Experiments

### Experiment 1 — FOK Miss Latency Instrumentation [HIGH VoI]
- **Hypothesis:** ≥60% of FOK misses on the sniper occur because >1.5s elapsed between signal generation (P_MIN threshold met) and CLOB order receipt, during which time the market moved past the fill window.
- **Data:** Add `ts_signal_fire`, `ts_order_submitted`, `ts_clob_response` timestamps to sniper log for each fired attempt (both fills and misses). Run for 24-48h.
- **Time:** 1 dev session to instrument; 24h accumulation.
- **Cost:** $0 capital. Zero risk (logging only).
- **Success metric:** If median signal→submit latency >1.5s on misses AND <0.5s on fills → latency is the cause.
- **Decision if YES:** Optimize submit path (async order pre-staging, reduce round-trips between signal and CLOB POST). Expected recovery: 3-5 turns/day (+$1.74-$2.90/day at current capital).
- **Decision if NO:** Latency not the cause → investigate whether P_MIN=0.995 is met at signal time but price reverts before order arrives (would indicate a different threshold timing fix, or that misses are structurally unavoidable at this selectivity level).

### Experiment 2 — Wuhan/Chengdu d0 Asia Dispersion Edge Persistence [MEDIUM VoI]
- **Hypothesis:** The Jul-17 first-recovery signal (Wuhan d0 ratio=1.183, Chengdu d0 ratio=1.136 at mode_ask≤0.265) represents a persistent localized edge in these two cities' same-day markets at tight odds, not a one-day anomaly.
- **Data:** Monitor band_struct_lite for Wuhan and Chengdu d0 only (already running via shadow engine). Requires zero additional instrumentation.
- **Time:** 5 days passive collection.
- **Cost:** $0 capital.
- **Success metric:** ≥4 of next 5 monitoring sessions show ratio>1.10 for Wuhan OR Chengdu d0, with mode_ask≤0.265 fires available ≥2 sessions.
- **Decision if YES:** Flag for targeted 2-city d0 re-enable pilot at minimum stake ($3 BAND_BASE_STAKE, max 2 legs/day) once and only once: (i) capital exceeds ruin floor ($89.16), (ii) G3 WC gap resolved, (iii) isotonic refit completed. Decision if NO: Jul-17 was a one-day fluctuation; maintain full dark posture.
- **Note:** This experiment costs nothing and the data is already flowing. It is purely an observation-and-classification task.

### Experiment 3 — STWA Shadow Maker Orphan Fill Outcome Tracking [LOW effort, HIGH data quality]
- **Hypothesis:** The 3 BUY@0.02-0.06 shadow-maker fills ($8.06 deployed Jul-17) resolve YES at a rate >5%, making them positive-EV entries (a 6¢ YES paying $1 = 1567% return; need >6% hit rate to break even vs taker fees).
- **Data:** When tokens 4095117562509625 ($3.50, p=0.06), 1055101008834022 ($3.00, p=0.02), 1046907088381323 ($1.56, p=0.02) resolve (d+1 = today, d+2 = Jul-19), check winner outcome vs filled YES side.
- **Time:** 1-3 days (d+1 resolves today).
- **Cost:** $0 (already deployed).
- **Success metric:** ≥2 of 3 resolve YES → track shadow-maker orphan ROI going forward as a separate line item.
- **Decision if YES:** Shadow-maker is producing cheap positive-EV YES fills via resting bids — authorize it to continue and begin tracking ROI separately from sniper. Decision if NO: 0 of 3 YES → sellers are informed (selling cheap YES into our bid because they know NO is near-certain) = classic adverse selection. Recommend adding cancellation guard to remove orphan-pattern resting orders before they accumulate.

---

## 7. Single Best Action

**Classify the 2 anomalous MAKER SELL fills (G3 overdue item).**

- **Action:** Look up token IDs `1399483673820402` (Jul-16 21:39Z SELL@0.96×147.05sh) and `2664940529472113` (Jul-18 00:54Z SELL@0.92×9.32sh, paired with BUY@0.08×44.9sh token `7094108612094851`) on Polymarket. Identify the market name, resolution date, and winner. Determine if the SELL was before or after resolution.
- **Why this:** No gate hit READY or REJECTED this cycle (gatekeeper confirmed). Per protocol, classifying the standing overdue item is the default candidate. The gatekeeper flagged this as overdue on both Jul-17 and Jul-18 runs. G3 is frozen at n=75 — the WC gap (-83.4pp, CI entirely negative) is the standing blocker for any band re-enable argument at any future capital level. Classification takes 30min and has binary high-value outcomes: (a) SELL was benign pair-arbitrage → unfreezes G3 n, allows the WC analysis to progress with full data, (b) SELL was premature exit of winning position or system bug → critical finding requiring immediate investigation and potential guard implementation.
- **Concrete first step:** Open Polymarket market for token `1399483673820402`. Check if the market resolved YES or NO. If YES and the SELL@0.96 happened before resolution → this was a profitable early exit (benign). If NO → the SELL was selling a winning NO position or hedging a YES position that lost (different interpretation). Repeat for Jul-18 pair.
- **Source:** gatekeeper_report 2026-07-18T09:11Z, G3 section: "EXEC AUDITOR REQUIRED — Classify 2 anomalous MAKER SELL fills before next G3 update (overdue since Jul-17)."
- **Compounding impact / effort:** (high gate clarity × high P(success at 30min lookup)) / (trivial effort) = highest unblocked ratio in today's action set.

---

## PROPOSED ACTIONS (human review)

*The following require human decision. Research agent does not implement.*

| # | Action | Urgency | Effort | Compounding impact |
|---|---|---|---|---|
| PA-1 | Classify 2 anomalous MAKER SELL fills (tokens 1399483673820402, 2664940529472113) | HIGH (overdue) | 30min | Unblocks G3; closes/opens band re-enable path |
| PA-2 | Track resolution of 3 shadow-maker orphan fills (d+1 today, d+2 Jul-19) | HIGH (time-sensitive) | 15min | Determines if shadow-maker is +EV or adversely selected; $8.06 exposed |
| PA-3 | Instrument FOK miss timestamps (ts_signal, ts_submit) | MEDIUM | 1 dev session | +$1.74-$2.90/day if latency confirmed as cause |
| PA-4 | Prune shadow logs >7d to free disk headroom | MEDIUM | 30min SSH | Prevents silent log corruption; 3GB free currently |
| PA-5 | Isotonic full refit with OOS validation (S4 alert, deployed 42d) | LOW (band dark) | ~1 data session | Prerequisite for any future BAND_LIVE re-enable; no immediate compounding impact while band dark |

*PA-1 and PA-2 are time-sensitive: PA-2 tokens begin resolving today (d+1). PA-1 is overdue since Jul-17.*

---

*Research agent: research-agent@klaus | Snapshot: 2026-07-18T10:11:35Z | Capital: $37.57 | Sniper: 18/18W kill-watch clean day 2 | Band: dark day 12 | Primary bottleneck: FOK fill rate 78.3% (5 misses/day ≈ $2.90 foregone compounding)*
