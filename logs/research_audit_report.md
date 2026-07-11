# Research Audit — 2026-07-11T10:45Z

**Snapshot**: `2026-07-11T10:18:31Z` (age: 27 min — FRESH ✅)
**System**: `active` ✅ (uptime from 2026-07-08T22:03Z)
**Capital**: $163.164 all-cash (CLOB-actual, reconciled Jul 10 22:20Z)
**Band**: DARK day 5 — BAND_LIVE=False since 2026-07-06; freeze EXPIRED 2026-07-10 21:53Z; EVOLVE maintained dark
**Specialist reports read**:
- `exec_audit_report.md` 07:07Z ✅ (fresh)
- `calib_monitor_report.md` 08:30Z ✅ (fresh)
- `gatekeeper_report.md` 09:03Z ✅ (fresh)
- `pnl_ledger_report.md` 23:37Z Jul 10 ✅ (18h — within 36h)

All four reports present, none stale. System active confirmed via system_status.txt.

---

## 1. Primary Bottleneck for Compounding

**Bottleneck: Equity deployed = $0 (zero turns/day, engine dark day 5).**

The proximate cause is BAND_LIVE=False. The binding cause behind it is **S3: the dispersion gauge** — the band's load-bearing edge variable — has been inverted on all 13 confirmed days since Jun 28. Market books price LESS uncertainty than temperatures actually realise (disp_ratio range Jun 28–Jul 10: 0.62–1.23; 1/13 days ≥1.10; median-city ≤0.80 on ALL 8 Jul days per EVOLVE + exec_audit). A strategy that sells overpriced dispersion earns nothing — and loses — when dispersion is underpriced by the market.

The compounding formula is ROI/turn × turns/day × equity deployed. All three factors are non-functional:
- **Turns/day**: 0 (0 maker fills in 7d; 0 live posts Jul 8–11)
- **ROI/turn**: undefined (last simulated G7 = +14.3% AMBIGUOUS, CI[−8.7%, +41.6%] straddles zero, n=396)
- **Equity deployed**: $0 out of $163 available

The shadow pipeline is healthy (14–19 fire-class records/day, ~100k maker_shadow rows/day) — the machinery is running and discarding output. This is not a data or reliability problem. It is an **edge-existence problem**: the band's premise is not supported by current market regime.

**Rank vs alternatives:**
1. Equity deployed → 0 (structural, edge-regime driven)
2. Dispersion edge (S3) → inverted 13/13 days; not a tunable parameter
3. ROI/turn → undefined without data; G2c CF trend is the only CI-positive signal
4. Fills → 0 maker fills; winner's curse unresolved (5 consecutive audit alerts)
5. Calibration → settled lane 9 days stale; isotonic plateau structural
6. Risk frame, reliability → healthy; not the constraint

---

## 2. Existing-System Optimization

### A. G2c PAIR_FAV_NO chicken-and-egg — highest expected delta, medium effort
**Finding (gatekeeper_report)**: PAIR_FAV_NO counterfactual n=32, ROI +52.9%, CI [+12.6, +85.5]. CI lower bound positive — the **only active gate with lower bound above zero**. The pair strategy is convergence-based (locks ≥$0.10/share when Σ≤0.90) and does NOT depend on the dispersion premium currently inverted. Yet live pair accumulation is frozen: BAND_LIVE=False blocks new pair fires, and BAND_LIVE re-enable requires pair_fav n≥40 first (n=9 today).

**Expected delta**: Breaking this deadlock allows G2c to reach n=40 TREND threshold in ~8 pair fires from re-enable at 11/day. G3 (FILLED_VS_FIRED n=37) crosses watch threshold in 3 more fills. Gatekeeper explicitly flags: "chicken-and-egg — accumulation only possible while BAND_LIVE=True."

**Confidence**: TREND only (n=32 CF). CI lower positive is directionally meaningful but below n=40 decision floor.
**Effort**: Jul 12 structural decision — config change only.

### B. Ladder drawdown -$40.90 in 24h — capital preservation flag
**Finding (gatekeeper_report)**: Bankroll dropped $204.064 (Jul 10 09:00Z) → $163.164 (Jul 11 09:03Z) = **-$40.90 in 24h while band is completely dark**. Source: untracked ladder sleeve (sprint ladder). Several Jul 9–11 BUYs visible in exec_audit tape (at p=0.35–0.55) have no corresponding SELL → likely resolved NO. The Jul 11 05:00Z BUY ($23.28 at p=0.35) adds fresh exposure. Gatekeeper explicitly flags: "Warrants Exec Auditor review."

**Expected delta**: Reviewing ladder stake sizing / KERNEL_FLOOR_USD guard prevents recurrence. The ladder sleeve lifetime result (7W/10L n=17, net +$117) is positive but the Jul 8–11 sub-window is net negative. The KERNEL_FLOOR_USD=40 guard exists (added Jul 8 state_log) but the drawdown still occurred.
**Effort**: Investigation + possible KERNEL_FLOOR adjustment; no code change required.

### C. Winner's curse unresolved — blocks re-enable gate
**Finding (exec_audit_report)**: Settled band paths PF 0.108 n=26 vs simulated G7 ROI +14.3% AMBIGUOUS. Direction consistent with classic maker adverse selection (resting bids hit selectively when market moves against the quote). Formal per-leg split at (city / days_out / price_band) requires band_resolution_join.py VPS output — not surfaced to cloud audits. Alert persists 5 consecutive days.

**Expected delta**: Resolving this (via VPS cross-tab) either (a) confirms adverse selection → CLOB pricing adjustment before re-enable, or (b) rejects it → clears the blocking concern for Jul 12 decision. Either answer is worth having immediately.
**Effort**: ~30 min VPS operator run.

### D. Isotonic plateau — structural, no near-term delta
**Finding (calib_monitor_report)**: p_cal flat ~0.376 for market prices 0.30–0.90, confirmed structural by Jul 9 PA-1 audit. Auto-promote expected ~Jul 12 but will NOT resolve the plateau. Model has zero discrimination for 60% of the band's operating range. This is an architecture-level finding; it confirms the band's ROI must come from structural over-dispersion (currently inverted), not model skill.

**Expected delta**: ~0 near-term. Do not manually promote. Allow auto-promote to run. Long-term architectural fix deferred.
**Effort**: Zero (do nothing).

---

## 3. Gate Pipeline Review

From gatekeeper_report (09:03Z Jul 11). Fifth consecutive frozen day. All gate n-values unchanged.

| Gate | n today | Status | ETA from re-enable | Notes |
|---|---|---|---|---|
| **G2c** PAIR_FAV_NO | 32 CF | **COLLECTING — CI lower positive** | ~8d at 11 pairs/day | Only gate with CI lower bound >0; chicken-and-egg blocks |
| **G3** FILLED_VS_FIRED | 37 | COLLECTING | ~3 fills = watch | 3 fills from n=40 watch; frozen dark |
| G2b PAIR_FAV_YES | 9 live | COLLECTING | ~8d at 11/day | Frozen dark |
| G7 SUM_POSTED [0.70–0.85] | 382 | AMBIGUOUS CI[−11.4,+38.9] | ~31d at 50/day | Long road; not near-term priority |
| G1 BAND_YES | 934 | AMBIGUOUS CI[−10.9,+21.1] | Very long | CI too wide at current n |
| G5 THERMO | 125 | **REJECTED** ✓ | Done | Complete |
| G6 M1β | 31 | **REJECTED** ✓ | Done | Complete |

**G2c is the nearest and most actionable gate**. CI lower bound is already positive at n=32 CF. Eight more real pair fires from re-enable would reach n=40 TREND. The pair edge is convergence-based, making it the correct candidate for a constrained re-enable even while the YES dispersion band remains dark.

**What would accelerate accumulation WITHOUT degrading expectancy:**
1. **Micro-stake BAND_LIVE re-enable for pairs only** (see Section 7). BAND_YES_LIVE_MIN_DOUT=9 already gates standalone YES; only PAIR_FAV would fire. This is the primary lever and the Jul 12 structural decision.
2. **Condition amendment (secondary option)**: if owner approves, converting G2c pre-reg from "live n≥40" to "n≥40 including CF shadow" would trigger immediately (n=32 + ~8 shadow days). This is a definition change, not a data change — requires owner sign-off.
3. **Do NOT increase stake size to accumulate faster** — n below 40, no justification.

G1 and G7 are too far from READY (~31 days each from re-enable) to prioritize accumulation strategy around them.

---

## 4. Assumption Attack

### Assumption 1: Dispersion premium persists (implied σ > realized σ)
**Status: THREATENED — 13/13 confirmed days inverted.**

Confirmed data Jun 28–Jul 10 (exec_audit + calib_monitor): disp_ratio range 0.62–1.23, only 1/13 days ≥1.10 (Jul 7 at 1.228; never two consecutive). Median-city ≤0.80 ALL 8 Jul days. Market books are pricing LESS uncertainty than temperatures actually realise — the opposite of the band's required condition.

What today's reports show: The model-proxy gauge (p_cal vs realized, calib_monitor Section 3) reads favorably — 5-day pooled median 1.34, trending up. But this is the WRONG numerator: the band's EV depends on MARKET pricing vs realized, not model pricing vs realized. The model-proxy's favorable reading does NOT indicate restored edge.

**What would restore confidence in this assumption**: Official VPS gauge ≥1.10 for 5 consecutive confirmed days. Not achievable from today's data. The Jul 12 structural review must weigh whether any new information has emerged (e.g., if band_resolution_join.py ran at Jul 10 11:23Z and produced Jul 3–10 data showing a recent trend reversal). Current confirmed data argues against re-enable of the YES dispersion band.

### Assumption 2: Fills are not adversely selected (winner's curse absent)
**Status: PLAUSIBLE THREAT — directional evidence, unresolved 5 consecutive audit days.**

Settled band paths PF 0.108 (n=26, pre-cut) vs simulated all-fires G7 ROI +14.3% AMBIGUOUS. Direction consistent with classic maker adverse selection. Formal resolution requires per-leg fill/resolution cross-tab from band_resolution_join.py — data on VPS, not yet surfaced.

What today's reports show: The alert is unchanged from Jul 7–10. No new evidence in either direction. n=26 is below the n≥40 decision floor, so the signal cannot be acted on, but it also cannot be dismissed. The directional gap has persisted across 5 audit reports, which is not noise.

**What would resolve this assumption**: VPS cross-tab (see Section 6, Experiment 2). This should run TODAY before the Jul 12 re-enable decision. If adverse selection is confirmed, CLOB pricing needs adjustment before any re-enable. If rejected, the cleared path to re-enable is cleaner.

### Assumption 3: Recycle velocity scales (RECYCLE099 adds cash turns)
**Status: UNMEASURABLE — zero live recycles since Jul 06; dark for 5 days.**

exit099_live.jsonl rows = 0 for Jul 7–11. Last confirmed RECYCLE099 exit: Jul 06 +$4.95. Zero data in current dark window. The mechanism worked on the sprint ladder (Jul 09 state_log: Tokyo +$76 early-exit validates the 0.99-exit velocity upgrade). Whether it works equivalently for 2-leg PAIR_FAV positions (where the YES and NO legs move inversely) has not been tested.

**At current capital and base stake**: If band re-enables at 14–19 fires/day with ~30% reaching 0.99+ in the weather window, RECYCLE099 generates roughly $2–4/day in recycled cash. Plausible but untested on pairs.

**Regime threat**: In a low-dispersion environment, YES markets may resolve near 0.5 more often rather than near certainty, reducing recycle velocity. This assumption is most at-risk exactly when S3 fires.

---

## 5. Market Intelligence — Platform Mechanics (Day 11 mod 3 = 2)

**Rotation**: [2] Platform mechanics — fee schedule / maker-rebate / liquidity-rewards changes. Delta vs state_log knowledge.

**Scope note**: Live access to docs.polymarket.com and Discord #announcements is not available from this sandboxed environment. This section reports from band_config.txt (live snapshot 10:18Z), pnl_ledger_report, and state_log. Flag items for operator verification against live platform.

### Fee schedule — no detected changes
band_config.txt live snapshot shows taker fee model unchanged: BAND_EV_MIN=0.08, BAND_ASK_MIN=0.05. No new fee-tier flag variables in config. Last recorded fee structure change: 2026-03-30 (8 new categories, updown BTC/ETH/SOL rates unchanged ~1.56% at 50%). pnl_ledger confirms fee behavior at p=0.37, 0.42, 0.50 all consistent with prior model. **No delta detected from Mar 30 baseline.**

### Maker rebate — accumulation stalled at $3.17
pnl_ledger cumulative expected maker rebate: **$3.17**, unchanged for 5+ days (last accrual was pre-Jul-06). Zero new maker fills since Jul 06 = zero new rebate accrual. The $3.17 exceeds the $1 minimum payout threshold. **Action (pnl_ledger flag, carried forward)**: Verify $3.17 receipt in Polymarket account. If not received, post to #support with wallet address. The rebate is stale and may require prompting the platform.

pnl_ledger Section 3 notes: Token 1132101 was bought at p=0.50 (max fee bucket) as taker. If this had been a maker fill, it would earn the highest rebate per dollar. This is an argument for prioritizing maker-entry over taker-entry at mid-price markets when band re-enables.

### Liquidity-rewards — no delta detected
No new liquidity-rewards announcements in state_log since Jun 12 (the NO-starvation fix era). No new config flags for reward multipliers. **Operator should verify** against current docs.polymarket.com: (a) whether weather ladder markets have updated point multipliers affecting maker ROI calculus; (b) whether maker rebate redistribution mechanics have changed (last confirmed: 100% of taker fees redistributed to makers in that market).

---

## 6. Three Experiments

### Experiment 1: Micro-stake PAIR_FAV-only re-enable
**Hypothesis**: Enabling BAND_LIVE=True with BAND_BASE_STAKE=$0.50 and BAND_MD_DAILY_BUDGET=$5.00 (hard cap), while keeping BAND_YES_LIVE_MIN_DOUT=9 (standalone YES never fires) and BAND_NO_ENABLED=False, would accumulate live PAIR_FAV fills to break the G2c chicken-and-egg without material capital risk. PAIR_FAV convergence edge (Σ lock ≥$0.10/share) is orthogonal to the dispersion regime.

**Data needed**: ~10 live PAIR_FAV pair fires; weather resolution in 24–48h.
**Time**: ~5 days to reach G2c n=40 TREND threshold; ~3 fills for G3 watch threshold.
**Cost**: Maximum $5.00/day deployed = $25 total if run 5 days at 0 wins (worst case -$25 on $163 bankroll = -15.3%, well above ruin floor $50).
**Success metric**: G2c reaches n=40 with CI lower bound remaining positive; G3 crosses n=40 watch; winner's curse per-leg comparison becomes available from live data.
**Decision if yes (CI positive at n=40)**: Full stake re-enable for PAIR_FAV; evaluate YES dispersion band separately.
**Decision if no (CI goes negative at n=40)**: G2c killed — CF at n=32 was noise; pair strategy falsified; no band re-enable until dispersion gauge recovers.
**Prerequisite**: Winner's curse cross-tab (Experiment 2) must clear first — if adverse selection is confirmed, adjust CLOB pricing before committing any capital.

### Experiment 2: Winner's curse formal measurement on VPS (prerequisite for Exp 1)
**Hypothesis**: The PF 0.108 (settled n=26) vs simulated +14.3% gap is measurable at (city, days_out, price_band) slice level from data already on VPS. If FILLED-leg PF significantly underperforms UNFILLED-fired-leg simulated ROI at the same slice, adverse selection is confirmed.

**Data needed**: band_resolution_join.py cross-tab output with per-leg filled flag. Data already exists on VPS — band shadow logs have been running continuously.
**Time**: ~30 minutes of VPS operator work.
**Cost**: Zero capital. Operator time only.
**Success metric**: Formal per-leg comparison at slice level; statistical significance or lack thereof.
**Decision if confirmed (FILLED PF < UNFILLED)**: Before any re-enable, adjust CLOB pricing to bid 1–2% inside current touch (reduce adverse selection probability); or switch to partial-FOK for markets where book depth is thin.
**Decision if not confirmed (PFs roughly equal)**: Winner's curse hypothesis rejected; settled PF 0.108 reflects n=26 noise + pre-cut era; cleared path for Jul 12 re-enable decision.

### Experiment 3: Daily dispersion proxy from s50 eval files
**Hypothesis**: stwa_pricer_eval_s50.jsonl files (already in data-mirror daily) contain p_cal distributions that can be joined with Gamma resolution outcomes to compute a daily dispersion proxy (model-implied σ / realized σ) for cloud audit use, without waiting for VPS band_resolution_join.py. If this proxy correlates with the official VPS gauge at r>0.70, the 9-day settled-lane staleness problem in calib_monitor is partially resolved.

**Data needed**: s50 eval files (present in data-mirror); Gamma resolution API call for outcome labels. ~50 lines of Python join script.
**Time**: ~2 hours to build; <1 minute daily cron.
**Cost**: Zero capital. Minor VPS cron slot.
**Success metric**: Proxy disp_ratio correlates with official VPS gauge r>0.70 over Jun 28–Jul 10 holdout (13 confirmed official data points available).
**Decision if yes (r>0.70)**: Daily dispersion proxy deployed to calib_monitor; staleness period shrinks from 9 days to 1 day; re-enable trigger evaluable daily.
**Decision if no (r<0.50)**: Model-σ is not a usable proxy for market-σ; the architecture gap is fundamental; accept official VPS gauge with its ~9-day lag as structural.

---

## 7. Single Best Action

**Action: Run the winner's curse cross-tab (Experiment 2) on VPS today, then at the Jul 12 structural review, implement micro-stake PAIR_FAV-only re-enable (Experiment 1) conditioned on the cross-tab showing no confirmed adverse selection.**

**Citations from specialist reports:**

- **gatekeeper_report (09:03Z)**: "Binding pre-reg condition UNMET: pair_fav n=9, need n>=40 — accumulation only possible while BAND_LIVE=True (chicken-and-egg)." And: "G2c counterfactual n=32, ROI +52.9%, CI=[+12.6, +85.5] — CI lower positive." This is the only evidence in the entire gate ledger pointing to a positive lower CI.
- **exec_audit_report (07:07Z)**: "Re-enable decision at Jul 12 weekly must resolve [winner's curse] before going live." The winner's curse question is the blocking gate before any capital deployment.
- **calib_monitor_report (08:30Z)**: "This gauge argues for continued shadow operation [for YES dispersion band]" — but PAIR_FAV convergence edge does not require dispersion premium; this alert is BAND_YES-specific, not PAIR_FAV-specific.
- **pnl_ledger_report (23:37Z Jul 10)**: "If BAND_LIVE were enabled, the engine would have fired [19 events] today." The shadow machinery is primed and waiting.

**Why PAIR_FAV does not require dispersion gauge clearance**: PAIR_FAV fires when a YES/NO pair can be posted such that Σ(YES_ask + NO_ask) ≤ BAND_PAIR_SUM_MAX=0.90, locking ≥$0.10/share regardless of outcome. This is a convergence trade, not a dispersion trade. It profits from the Σ<1.00 pricing inefficiency in the pair, not from overpriced tails. The S3 dispersion alert is about the standalone YES band, not about pair convergence.

**Concrete first step (today, Jul 11)**: VPS operator runs band_resolution_join.py with per-leg filled-vs-fired output and posts result to state_log. Takes ~30 minutes. This is the prerequisite.

**Concrete second step (Jul 12 structural review)**:
- If cross-tab shows no confirmed adverse selection: propose BAND_LIVE=True, BAND_BASE_STAKE=0.50, BAND_MD_DAILY_BUDGET=5.00, BAND_YES_LIVE_MIN_DOUT=9 (unchanged — standalone YES stays gated), BAND_NO_ENABLED=False (unchanged). This is a constrained data-collection re-enable, not a full band re-enable.
- If cross-tab confirms adverse selection: do NOT re-enable; first adjust CLOB pricing (bid 1–2% inside touch), then re-enable at micro-stake.
- Formally document PAIR_FAV as a separate strategy with a separate edge mechanism from the YES dispersion band. Its re-enable condition should not be coupled to S3.

**Note on ladder**: The -$40.90 drawdown from the untracked ladder sleeve (gatekeeper alert) is the second-priority item. Operator should identify which Jul 9–11 tokens resolved NO, verify the KERNEL_FLOOR_USD=40 guard is functioning as designed, and determine whether the current 3-fires-per-cycle cap is appropriate relative to a $163 bankroll. This is a parallel track — it does not block the Jul 12 band decision.

---

## PROPOSED ACTIONS (human review — no code changes made)

- [ ] **VPS operator TODAY**: Run `band_resolution_join.py` with per-leg filled-vs-fired cross-tab at (city / days_out / price_band) slice. Publish results to state_log before Jul 12 structural review. **This is the prerequisite gate for the Jul 12 re-enable decision.**
- [ ] **Jul 12 structural review**: Decide BAND_LIVE re-enable path conditioned on cross-tab result. Proposed: micro-stake PAIR_FAV-only (BAND_BASE_STAKE=0.50, BAND_MD_DAILY_BUDGET=5.00, standalone YES DOUT=9 unchanged, BAND_NO_ENABLED=False). PAIR_FAV is convergence-based; treat its re-enable as separate from the YES dispersion gate (S3).
- [ ] **Jul 12**: Formally decouple PAIR_FAV gate (convergence edge, CI lower positive at n=32) from YES dispersion gate (S3, inverted 13/13 days). Document separate re-enable conditions.
- [ ] **Jul 12**: Investigate and reconcile -$40.90 ladder drawdown (Jul 10 09:00Z → Jul 11 09:03Z). Identify which tokens resolved NO. Verify KERNEL_FLOOR_USD=40 guard. Review stake sizing relative to current $163 bankroll.
- [ ] **Ongoing**: Verify $3.17 maker rebate received in Polymarket account. If not received, post wallet to #support.

---

*Research audit 2026-07-11T10:45Z. Snapshot 10:18Z (27 min at run time). System active confirmed. All four specialist reports read. REPORT ONLY — no strategy code or flags modified.*
