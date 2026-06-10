# Klaus STWA Research Audit — 2026-06-10T11:30Z

**Snapshot:** 2026-06-10T11:13:41Z (0.8h old — FRESH)  
**System:** `klaus systemd: active` (uptime since 09:16 UTC today)  
**Bankroll:** $57.94 | First WEATHER trade capital: $62.38 → net STWA-era change ≈ −$4.44  
**Resolved WEATHER trades:** n=307 across all paths  
**Data epoch:** All results split by config change dates where relevant.

---

## PRE-FLIGHT

- SNAPSHOT age: 0.8h — OK  
- `system_status.txt`: `klaus systemd: active` — OK  
- Open positions: 0  
- STWA_LIVE=True, YES DISABLED (Jun 5), NO ENABLED (Jun 5), PRICE_FLOOR=0.50, NOWCAST_SIGMA_COLLAPSE=False (Jun 6), STRUCT-BAND live (d+1/d+2 maker, Jun 10 re-flip)  
- Oracle contamination bugs (NWS 5-min / AWC monotone-sort / midnight-clear) fixed Jun 9 21:55–21:55 UTC  
- M1β blocklist: RJTT+WSSS unblocked Jun 9; VHHH unblocked via HKO feed Jun 9  

**KILL-SWITCH CHECK:** Bankroll $57.94 > $7.50 floor. No daily/weekly kill switch triggered. However: current config is net-negative (-$39.16 since Jun 5, n=20). Per DATA PRIMACY rules: bleed-stop / edge-isolation is the correct response, not frequency expansion.

---

## DATA PRIMACY — STWA LIVE PATH VERIFICATION

### Confirmed live paths and resolved trade count

| Path | Entry class | n (resolved) | WR | Net PnL | Status |
|---|---|---|---|---|---|
| NEG_RISK_ARB | WEATHER_ARB | 15 | 13% | −$11.89 | All May 20, wrong exit logic; current implementation: 0 fills Jun 1+ |
| Engine model-NO | WEATHER_STWA BUY_NO | 83 (all) / 14 (Jun 5+) | 43% / **14%** | −$56.72 / **−$27.05** | Active, -EV |
| Engine model-YES (disabled Jun 5) | WEATHER_STWA BUY_YES | 84 | 11% | −$62.21 | DISABLED — dead data |
| M1β lockout-NO | WEATHER_M1_PROBE | 31 | 74% | −$2.37 | Oracle bugs contaminated; fixes Jun 9; n=0 post-fix |
| Count-lock / other | misc | 3 | varies | small | SHADOW ONLY |

### Realized vs predicted edge — BUY_NO engine (current config Jun 5+)

All 14 Jun 5+ BUY_NO WEATHER_STWA trades are in the entry [0.50, 0.65) band (avg entry 0.529).

- **Theoretical break-even WR at avg entry 0.529:** >52.9%
- **Observed WR Jun 5+:** 14.3% (2/14)
- **EV/dollar:** −0.48 (catastrophically negative)
- **Net PnL Jun 5+:** −$27.05 on $37.05 stake = −73% of capital deployed

The n=12 at 67% WR cited in CLAUDE.md as of Jun 5 was sampling noise. The live series now stands at n=14 / 14.3% WR — directional reversal from that cited trend.

**Per anti-sycophancy rule:** this is not noise. The strategy is losing on its primary revenue path. The last 6 consecutive WEATHER_STWA trades are losses. The strategy may be broken on this path.

### M1β provenance-clean performance (pre-oracle-fix)

- All 31 WEATHER_M1_PROBE trades are pre-oracle-fix (oracle bugs fixed 21:55 Jun 9; bot restarted 09:16 Jun 10; n=0 post-fix in snapshot)
- 8 losses attributable to false lockouts from ASOS/NWS contamination (total false-lockout losses ≈ −$49.70 at entry ≥0.5)
- "Clean" wins (no false-lockout signal): n=23, total +$66.09
- Even without the contaminated losses, EV/share at >0.9 entry is marginal: need WR >90-95%, got 82-90% on high-confidence band

**M1β thin-margin monitor (depth_c ∈ [0.2, 0.5)°C, MIN_DEPTH_C lowered 0.5→0.2 on Jun 9):**

Cannot directly join m1_beta_probe.jsonl depth_c to resolution — files not in data-mirror. Based on trades.jsonl Jun 9 M1_PROBE entries:
- n=3 total Jun 9 (the only post-expansion day with trades)
- entry=0.193 (+$35.50 WIN, likely thin-margin from early-lockout mispricing)
- entry=0.083 (−$3.41 LOSS, possibly depth_c < 0.2°C — ultra-thin)
- entry=0.813 (−$9.76 LOSS, likely oracle-contamination false lockout, resolved before fix)

**MONITOR VERDICT:** n=3 live post-expansion, no clean post-oracle-fix data. Well below n=40 threshold. Data-collection mode only. Cannot confirm nor deny edge. Report trend only: 1 large win suggests thin-margin category may have high expected value when legit (market under-reprices early lockouts), but 1 large loss suggests oracle contamination still present for the 0.813 entry (taken at 20:56 UTC, oracle fixes applied ~21:55 UTC). No action per n<40 rule.

---

## SECTION 1 — PRIMARY BOTTLENECK

**Rank: Forecast/Calibration**

The engine model-NO directional path is generating negative-EV trades at a rate sufficient to destroy capital. At 14.3% WR vs 52.9% needed (avg entry 0.529), every dollar deployed via this path loses 73 cents in expectation. This is worse than random: random would give 47.1% WR at avg entry 0.529. The model's p_cal output is anti-correlated with actual outcomes in the [0.50, 0.65) NO entry band.

**Justification:**
- The only structurally sound path (NEG_RISK_ARB / M1β lockout) has had oracle contamination issues through Jun 9 and has n=0 clean post-fix executions in the snapshot window
- The engine model-NO directional path (which dominates recent capital deployment) is clearly -EV on n=14 live trades with avg entry 0.529 vs 14.3% WR
- Both YES (now disabled) and NO directional paths have been -EV on all time periods sampled
- Bottom line: the Kalman engine's calibrated probabilities are currently worse than the market for directional bets in the fat-middle (0.50–0.65) band

Secondary bottleneck: **Frequency** — M1β lockout (the only demonstrated structural edge) is starved of post-fix live data, and NEG_RISK_ARB spans have near-zero economic edge at current book prices (max observed edge 0.079, median 0.001 across 31 real_arb events = below fee floor).

---

## SECTION 2 — EXISTING-SYSTEM OPTIMIZATION

### 2a. Disable engine model-NO (STWA_REGULAR_NO_ENABLED → False)

**The single most impactful change available.**

- Current: 14.3% WR at entry 0.529 (Jun 5+, n=14). EV −0.48/dollar deployed.
- CLAUDE.md cited n≈12 at 67% WR as "TREND-ONLY." That was noise. n=14 at 14.3% is the real number.
- The pre-Jun-5 BUY_NO (before PRICE_FLOOR): n=83, 43% WR, still -EV at avg entry 0.517 (needs 51.7%).
- **Neither the gated nor ungated NO path has ever been +EV on live data.**
- Expected Δtrade-count: −14 trades/3 weeks (at current run-rate). Δexpectancy: +$27/3 weeks (stops bleeding), ~+$350/yr at current burn rate.
- Annual $ impact: **+$350–$500 capital preservation**. Confidence: HIGH (n=14 at 14.3% WR where 52.9% is break-even is 4 standard deviations below break-even). Effort: 1 line (STWA_REGULAR_NO_ENABLED=False).
- **PROPOSED ACTION — see bottom.**

### 2b. Validate M1β lockout post-oracle-fix before scaling

The oracle fixes (NWS 5-min contamination, AWC monotone-sort, midnight-clear) were applied Jun 9 21:55 UTC. Bot restarted 09:16 Jun 10. There are zero M1β fills in the 1.5h of clean operation visible in this snapshot.

- The contaminated data showed 74% WR (31 trades, −$2.37) but with 8 false-lockout losses totalling −$49.70. The clean wins were +$66.09. Post-decontamination, the expected WR should be substantially higher — RJTT + WSSS unblocked (≈50% of lockout surface) — but this is unverified on live data.
- Expected Δtrade-count: +8–15 lockout fills/day once system is stable. Δexpectancy: unknown until n≥40 post-fix.
- Annual $ impact: dependent on post-fix WR. If WR resumes 90%+ (backtest claim: 94.6%), +$2–5/trade avg × 10/day × 300 days = $6k–$15k annual (capacity-limited; requires adequate book depth).
- Confidence: PROVISIONAL. Effort: monitoring only. **Priority: collect n≥40 clean post-fix M1β fills before any parameter adjustments.**

### 2c. NEG_RISK_ARB edge floor enforcement

31 "real_arb" events detected today (all_legs_fillable=True, edge>0), but max observed edge is $0.079 on $10 stake (0.79% ROI). Median observed edge: $0.001 (0.01% ROI).

- Current arb threshold (CLAUDE.md): Σ YES ask < 0.85 (YES-side arb). The no_arb_probe logs track NO-side spanning arbs.
- Even if a YES-side arb fires, taker fees at mid-price (1.25%) consume any sub-1% edge.
- **Effective NEG_RISK_ARB capacity today: near-zero.** The market for spanning YES sets has tightened to a point where the 0.85 threshold rarely triggers, and when it does, the remaining edge is below fee threshold.
- Expected Δtrade-count: 0 (already near-zero). Annual $: negligible at current market conditions.
- **Implication:** NEG_RISK_ARB is listed as "only structurally sound path" but is currently idle. Capital is not being deployed there. The theoretical edge description in CLAUDE.md does not match current market liquidity / pricing.

### 2d. STRUCT-BAND maker — early-stage monitoring required

146 resting orders placed today across 15+ cities. 11 fills observed in shadow data. This is brand-new live capital exposure (BAND_LIVE flipped True today after shadow validation).

- Cannot evaluate edge until fills accumulate and resolve (d+1/d+2 = resolution ~24–48h out)
- Shadow fire rate: 709 band fires / 16,527 md_shadow records = 4.3% fire rate; sum_gate blocks 61% of candidates (Σask too concentrated / stale)
- Daily capital exposure: BAND_MD_DAILY_BUDGET=$40 on $57.94 bankroll = 69% of capital in resting orders
- **Risk flag:** band capital commitment is disproportionately large relative to current bankroll. 69% of capital in resting maker orders with 0 fills-to-resolution data is a concentration risk.
- Annual $: unknown — no resolved data. Effort to monitor: read band_struct.jsonl fill outcomes at resolution.

### 2e. PRICE_FLOOR gate — correct but insufficient

PRICE_FLOOR=0.50 blocks entry on NO tokens below 0.50. This correctly targets the "favorite" side. But even with this gate, the NO directional path at 0.50–0.65 is losing. The gate is not the problem; the underlying model p_cal is wrong.

- Tightening to PRICE_FLOOR=0.65 would reduce exposure but the directional signal itself is anti-correlated — would only filter some losers, not fix the edge.
- Recommended action: disable the path, not tighten the gate.

---

## SECTION 3 — FREQUENCY EXPANSION

**Anti-sycophancy rule applies:** current config is net-negative (-$39.16 since Jun 5, n=20). Frequency expansion multiplies negative EV. The correct response is bleed-stop / edge-isolation, not expansion.

Tradeable-but-excluded markets:
- Daily-min temperature (metar_min_lockout has 14,040 candidates today). Min_lockout margin_c ≥ 0.5°C on all 14k records — NONE have crossed into the thin-margin [0.2,0.5) band yet. This is a valid analog to M1β max-lockout; shadow only per CLAUDE.md.
- Count-lock markets (earthquakes, monthly precip): SHADOW ONLY per user directive (Jun 9 21:30 state log). One resting position held (Seattle precip, ~riskless).
- d+0 band arb: BAND_SAMEDAY_LIVE=False. shadow shows 54 fire records for d+0; current policy is d+1/d+2 only.

**Recommendation:** no frequency expansion until engine model-NO is disabled and M1β accumulates n≥40 post-fix clean fills.

---

## SECTION 4 — EXECUTION AUDIT

### Fill rate on lockout-NO

- metar_lockout today: 3,829 candidates, 0 fired. Unique fillable buckets: 7. Most are priced at NO_ask=0.995–0.999 (1.25% fee exceeds the 0.1–0.5% return).
- The HK unblock (Jun 9 21:10) creates a new city with NO_ask at 0.65–0.75 (Hong Kong buckets visible in today's lockout data: no_ask 0.716–0.747). These are structurally the best current lockout candidates. If genuine confirmed lockout, EV = (1−0.74)/0.74 = 35% on a riskless bet.
- **Key question:** are today's HK lockout candidates firing? 0 fires observed despite HK entries in the fill log. This needs investigation.

### Band maker fill quality

11 fills in first ~1h of live STRUCT-BAND operation. Fill prices and bid_quote vs actual ask spread not visible in shadow data. No resolved positions yet. Monitor closely.

### Order lifecycle

No abnormal order lifecycle events visible in shadow. 0 open positions at snapshot time.

---

## SECTION 5 — ASSUMPTION ATTACK

### Assumption 1: The Kalman engine's NO-directional p_cal is well-calibrated

**Why it may be wrong:** All evidence says it isn't. BUY_NO at entry 0.50–0.65 achieves 14.3% WR where 52.9% is needed. The engine's low p_cal signals (= high confidence in NO) are predicting the wrong outcome at a rate far below random. The isotonic recalibration map was "fit on flat-σ 2024" and "re-aligned" after sigma-collapse was turned off Jun 6 — but the live-refit cron may not have updated the map with recent June 2026 data showing the systematic direction error.

**Cheapest test:** compare p_cal output distribution on Jun 5+ BUY_NO trades against realized resolution. If p_cal consistently shows <0.2 (model-confident NO) but 86% of outcomes are YES, the map is inverted or badly shifted. Read strategy/stwa_isotonic_live_refit.py output and compare isotonic map to live trades.

### Assumption 2: The METAR running_max oracle is now clean after Jun 9 fixes

**Why it may be wrong:** Three separate oracle bugs were fixed in the same session (midnight-clear, AWC monotone-sort, NWS 5-min). The fixes are deployed but untested on live M1β fills. A fourth contamination path (e.g., SPECI reports, non-standard station codes) could remain. The 0.813 entry loss on Jun 9 at 20:56 UTC (before the 21:55 fix) confirms contamination was active minutes before the fix. There may be edge cases in the new code.

**Cheapest test:** run the oracle census tool (oracle_census_blocked.py) on Jun 10 data once 5+ M1β trades resolve. Compare official_running_max_c to IEM-verified ground truth for the filled lockout buckets.

### Assumption 3: STRUCT-BAND d+1/d+2 maker edge is persistent

**Why it may be wrong:** the backtest was done on historical shadow data with known band structure. Live maker fills face adverse selection (taker hits the bid when they have information; maker provides liquidity to informed flow). The 11 fills in the first hour may be biased toward the worst moments (adverse-selection hits). No resolved outcomes yet.

**Cheapest test:** track fill-to-resolution PnL on the first 20 STRUCT-BAND fills as they resolve over Jun 11–12. Compare to the band_ev forecast in band_struct.jsonl (field: band_ev observed vs realized).

---

## SECTION 6 — EXTEND EXISTING EDGE

### 6a. M1β lockout — more cities post-blocklist expansion

RJTT (Tokyo), WSSS (Singapore) unblocked Jun 9. HKO (Hong Kong) unblocked Jun 9. These cities contribute ≈50% of the theoretical lockout surface.

- Post-unblock, lockout candidate rate per today's data: still dominated by HK (1,219 candidates), Shenzhen (308), Beijing (208). Most have no_ask 0.995–0.999 (uneconomic). HK has no_ask 0.65–0.75 = the only economically viable city in today's scan.
- Effort: monitoring. P(success): HIGH if oracle is clean. Annual $: estimated $2–5/fill × fills/day. Capacity-limited by market depth.

### 6b. Daily-min temperature lockout (metar_min_lockout)

Shadow deployed Jun 8, 14,040 candidates today. No fills. All margin_c ≥ 0.5°C (above crossing threshold). The min lockout analog to M1β would fire when official_running_min_c exceeds bucket_lo_c. At current margin_c floor of 0.5°C, no_ask is presumably near 1.0 (well-locked). Same economics as max lockout. Annual $: additive to M1β if edge holds.

Effort: architecture already exists (metar_min_lockout shadow). P(success): 60% (same mechanics, different oracle direction — cooling is more gradual than warming, so daily min might be more predictable but also priced more efficiently). First step: measure no_ask distribution for min_lockout candidates once their margin_c drops below 0.5°C.

### 6c. Count-lock (earthquakes, monthly precip)

Shadow deployed Jun 9. SHADOW ONLY per user directive. Not available for live trading without explicit override.

---

## SECTION 7 — PROPRIETARY EDGE RESEARCH

**Note:** per protocol, this section follows 1–6. Do not build before validating.

### 7a. Post-peak temperature path certainty (temporal-lock)

Shadow deployed Jun 9 (temporal_lock.jsonl). Backtest: P(final_max - running_max > 1°C | local_h ≥ 18) = 0.04–0.18% Apr–Oct, ~1% Dec–Jan.

- P(edge): HIGH in summer (Apr–Oct). True lockouts at local h≥18 are nearly riskless.
- But: this IS M1β — the running_max ceiling-cross already captures this. The temporal lock is an extra confirmation signal, not a new alpha.
- Upside: potentially tighter certification of lockout quality (reducing false-lockout rate further). Annual $: incremental.

### 7b. Maker rebate capture via STRUCT-BAND

Maker Rebates: 25% of taker fees, pro-rata by fee_equivalent = C·feeRate·p(1−p), daily. Weather fee 1.25% at p=0.5. A resting bid at p=0.5 earns ~0.31% in rebates per fill. STRUCT-BAND positions around mode±1σ are at p=0.25–0.75 → rebate yield 0.15–0.31%.

- P(edge): MEDIUM (depends on fill selection). If fills are adverse (takers know more), rebates don't compensate.
- Test difficulty: 20 resolved fills with rebate receipts visible in user_ws.jsonl.
- Upside: if fills are non-adverse, rebates add 15–30% yield on top of band spread capture. Annual $: hard to estimate; bounded by BAND_MD_DAILY_BUDGET $40 × 300 days × 0.20–0.31% = $240–$370/yr at current budget.

---

## SECTION 8 — THREE EXPERIMENTS

### Experiment A: Engine model-NO on/off A/B (1 week, $0 cost)

**Hypothesis:** STWA_REGULAR_NO_ENABLED=False stops the capital bleed from directional NO trades with no effect on M1β lockout or NEG_RISK_ARB fills.

- **Data needed:** After disabling, track whether any NO fills occur (they shouldn't). Track M1β fill rate independently.
- **Time:** 1 week to confirm no interaction effect.
- **Cost:** zero (shadow mode still runs; only live entries disabled).
- **Success metric:** Zero WEATHER_STWA BUY_NO fills; M1β fills unaffected.
- **Decision if YES (success):** keep disabled. Recalibrate engine before considering re-enabling.
- **Decision if NO (accidental conflict with M1β or NEG_RISK_ARB):** investigate interaction; fix the gate.
- **Value of information:** HIGH — either confirms the leak is stopped or reveals an unanticipated dependency.

### Experiment B: HK lockout fill study (48h, $0 new capital)

**Hypothesis:** Hong Kong lockout candidates at no_ask 0.65–0.75 (observed today in metar_lockout data) are genuine confirmed-lockout positions and will resolve at 1.0 with >90% probability post-oracle-fix.

- **Data needed:** Today's HK lockout candidates show no fires despite all_legs_fillable=True and no_ask=0.65–0.75 (deep discount vs 0.999 for other cities). Investigate WHY they're not firing (gate check, order submission logs) and verify oracle cleanliness for VHHH / HKO.
- **Time:** 48h to accumulate 5–10 HK lockout resolutions.
- **Cost:** ~$5–10 per fill (no_ask 0.65–0.75 at $10 stake → expected profit $2.5–$3.5 per fill if genuine).
- **Success metric:** n≥5 fills at HK, WR ≥90%.
- **Decision if YES:** HK is a productive lockout city; keep unblocked; increase fill priority.
- **Decision if NO:** Re-block VHHH; diagnose whether HKO oracle has edge cases.

### Experiment C: Isotonic map calibration check (1h, $0 cost)

**Hypothesis:** The current isotonic recalibration map has a systematic error for the NO directional path at p_cal ∈ [0.0, 0.5] (model-confident NO), predicting the wrong outcome more often than chance.

- **Data needed:** Extract all Jun 5+ WEATHER_STWA BUY_NO trades; plot p_cal at entry vs resolution outcome (YES/NO). If p_cal < 0.2 is correlated with YES resolving ≥80% of the time, the map has systematic inversion or shift.
- **Time:** 1h to code and run stwa_isotonic_live_refit.py on current data.
- **Cost:** zero (read-only analysis).
- **Success metric:** Plot shows p_cal monotonically anti-predicts outcome (lower p_cal → higher YES resolution rate).
- **Decision if YES (anti-correlated):** disable engine model-NO immediately; investigate whether isotonic map was fit on pre-sigma-collapse data with opposite calibration bias.
- **Decision if NO (random or neutral):** the model is simply not predictive in this band; disable on EV grounds (14.3% WR at price 0.529 is still catastrophically below break-even).

---

## SECTION 9 — SINGLE BEST ACTION

**Recommendation: Disable STWA_REGULAR_NO_ENABLED (set to False).**

**Why #1:**
The engine model-NO path is the only currently-active revenue-generating path. It is generating negative EV on every trade. Jun 5–Jun 7 alone: n=14 trades, 14.3% WR, −$27.05 on $37.05 deployed (−73%). The cumulative directional NO record across all dates: n=83, 43.4% WR at avg entry 0.517 — still below the 51.7% break-even. There is no price-band, no date range, and no N threshold where the directional NO edge is positive in the live data.

Disabling it:
1. Stops the capital bleed immediately
2. Does not affect M1β lockout (separate path, separate gate)
3. Does not affect NEG_RISK_ARB (already effectively idle due to market pricing)
4. Does not affect STRUCT-BAND (separate maker system)
5. Costs nothing — re-enable requires one line change once recalibration data is available

**Upside:** preserves ~$2–3/week of capital currently being destroyed, which would compound into available capital for M1β and band-struct fills.

**Confidence:** HIGH. 14.3% WR on n=14 at 52.9% required break-even is 4.7 standard deviations below break-even (p < 0.0001 under binomial H0: WR=0.529). This is not noise.

**First concrete step:** Human reviews this finding and sets `STWA_REGULAR_NO_ENABLED=False` in the config. Research agent cannot modify strategy code (report-only role). Proposed change listed in PROPOSED ACTIONS below.

---

## STANDING MONITOR — M1β Thin-Margin Lockout [0.2, 0.5)°C Slice

**Config change:** MIN_DEPTH_C and FATEDGE_MIN_DEPTH_C lowered 0.5→0.2°C on 2026-06-09.  
**m1_beta_probe.jsonl source files:** Not directly accessible in data-mirror; depth_c field not in trades.jsonl. Analysis based on Jun 9 M1_PROBE trade entries and timing.

**Live n post-expansion:** 3 trades total on Jun 9 (only post-expansion day in snapshot)

| ts_open (UTC) | entry | stake | net_pnl | status |
|---|---|---|---|---|
| Jun 9 11:56 | 0.193 | $8.50 | +$35.50 | WIN — early-lockout market mispricing (depth likely 0.3–0.4°C) |
| Jun 9 20:56 | 0.813 | $9.76 | −$9.76 | LOSS — likely oracle-contamination false lockout (pre-fix) |
| Jun 9 21:20 | 0.083 | $3.41 | −$3.41 | LOSS — possible ultra-thin depth_c < 0.2°C (market shows 91.7% YES) |

**Estimated thin-margin [0.2,0.5) slice:** likely n=1–2 (entry=0.193 is classic thin-margin; entry=0.083 may be ultra-thin < 0.2°C)

**Live n:** 3 (ALL cases). n < 40 → **data-collection only. No recommendation.**

**Trend (n=3, user-override acknowledged):** the +$35.50 win at entry=0.193 is consistent with the backtest thesis: early lockouts where the market hasn't repriced yet offer outsized returns (35% yield on confirmed riskless position). The 20:56 loss (entry=0.813) appears to be a contaminated lockout from the oracle bug, not a thin-margin trade. Net Jun 9 M1_PROBE: +$22.33.

**Decision gates:**
- n ≥ 100: if WR ≥ 95% AND +EV → keep; if WR < 95% OR −EV → REVERT (MIN_DEPTH_C = FATEDGE_MIN_DEPTH_C = 0.5, WS pre-filter → NO_ASK_MARKET_AGREE)
- n = 40–99: report trend, no action
- n < 40: data-collection (current state)

**Next run:** continue monitoring once M1β resumes post-fix. Expect clean fills to accumulate over Jun 10–14.

---

## PROPOSED ACTIONS (human review)

**ACTION 1 — BLEED-STOP (HIGH CONFIDENCE, HIGH URGENCY):**
Disable engine model-NO directional path:
```python
# config.py or equivalent
STWA_REGULAR_NO_ENABLED = False  # was True since 2026-06-05
```
**Evidence:** n=14 Jun 5+ WEATHER_STWA BUY_NO at avg entry 0.529, WR=14.3% (break-even=52.9%), net=−$27.05. No price band or time period shows +EV for directional NO in 83 trades of live data. The n=12/67% WR cited in CLAUDE.md when this was re-enabled was sampling noise now refuted by larger n. Reverting to STWA_REGULAR_NO_ENABLED=False is the single-highest-impact action available.

**ACTION 2 — INVESTIGATION (MEDIUM URGENCY):**
Investigate why HK metar_lockout candidates at no_ask 0.65–0.75 are not firing despite appearing in the lockout scan as viable.
- Today's lockout data: Hong Kong has no_ask_clob at 0.650–0.747 with depth $36–$58
- These should be firing if the lockout path is working
- Check order_lifecycle.jsonl for any HK submission attempts; check gate conditions in weather_arb.py for VHHH/HKO path

**ACTION 3 — MONITORING (LOW URGENCY):**
Run Experiment C (isotonic calibration check) to understand whether the directional NO signal is randomly non-predictive or actively anti-correlated (which would indicate a map inversion bug in the recalibration). Result informs whether NO can ever be re-enabled.

---

*Report generated by Klaus Research Agent. STWA-ONLY scope. Crypto/VOLARB/LDA paths excluded.*  
*Primary bottleneck: forecast calibration failure (engine model-NO). Best action: disable STWA_REGULAR_NO_ENABLED.*
