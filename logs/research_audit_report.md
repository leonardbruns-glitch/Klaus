# Klaus Research Audit — 2026-07-03T19:10Z

**Snapshot**: 2026-07-03T18:49:05Z (age: ~21 min — VALID ✓)
**System**: `klaus systemd: active` ✓
**Bankroll**: $79.57 (bankroll.json at 18:49Z) / $82.30 (gatekeeper at 12:43Z — see §1 note)
**Open positions**: 0
**Config era**: BAND-V3 + pair_fav + RECYCLE099; BAND_NO_ENABLED=False (Jul 02 06:14Z EVOLVE halt)

**Specialist report coverage**:
| Report | Timestamp | Age at audit | Status |
|---|---|---|---|
| exec_audit_report.md | 2026-07-03T07:08Z | ~12h | VALID |
| calib_monitor_report.md | 2026-07-03T08:09Z | ~11h | VALID |
| gatekeeper_report.md | 2026-07-03T12:43Z | ~6.5h | VALID (freshest) |
| pnl_ledger_report.md | 2026-07-01T23:37Z | ~43h | STALE — >36h. Using gatekeeper for P&L delta. |

**pnl_ledger stale note**: Jul 01 report shows $76.69 capital and −$7.46 two-day delta; gatekeeper at 12:43 today shows $82.30 (+$3.26 from prior $79.04, with 3 RECYCLE099 exits totaling +$7.77). Delta between gatekeeper ($82.30) and bankroll.json ($79.57 at 18:49Z) is −$2.73 and likely reflects new maker bids placed between 12:43–18:49Z that depleted cash without yet generating fills. No crisis inferred.

**EVOLVE status flag**: EVOLVE loop was phantom-dead Jul 01–03 (TAMPER test line left in INVARIANTS.md post build-session, never removed). Fixed 14:05 UTC today; daily cycle manually triggered immediately after. 4 prior daily cycles had 0 successful runs. **Any "autonomous" EVOLVE changes reported Jul 01–03 before 14:05 UTC are phantom** — wiring test was failing silently. First real EVOLVE cycle ran today ≥14:05Z. Post-cycle output (logs/evolve/) not visible from this sandbox.

---

## 1. Primary Bottleneck

**EQUITY DEPLOYED** — 0.43 turns/day vs 1.0 badatmath benchmark. Root cause is structural, not operational.

From exec_audit_report: standalone NO was 80% of fill notional pre-halt. Post-halt (Jul 02 06:14Z), only pair_fav provides NO exposure. YES d+2 band fills thin (yes_books=0 consistently; pair_cands=1.6–1.8/cycle with fill rate of ~3–4 events/day). Total notional per day has dropped from $67.55 (Jul 01, heavy NO day) to ~$18–19/day post-halt.

The bottleneck has a structural sub-cause: **band_resolution_join.py has never successfully run on the VPS.** This blocks the CI gate for BAND_YES, FILLED_VS_FIRED, and SUM_POSTED_0.70_0.85 simultaneously. Until CI is resolved:
- We cannot confirm YES d+2 has positive expectancy (dispersion ratio d+2 = 0.340 per prior cycle, well below 1.10 threshold)
- We cannot confirm FILLED_VS_FIRED (n=107 — just crossed threshold; winner's curse unknown at n=28 per exec_audit)
- We cannot determine if d+2 YES at sum_posted 0.70–0.85 is the productive slice

EVOLVE was designed to run the join daily. EVOLVE was phantom-dead for 2 days. EVOLVE ran for the first time today at ≥14:05Z. Whether the join completed is unknown from this sandbox but is the highest-value outstanding unknown in the system.

**Ranking of bottlenecks** (for prioritization):
1. Equity deployed — 0.43 turns/day (consequence of NO halt + thin YES fills)
2. ROI/turn — dispersion ratio d+2 = 0.340, sub-threshold; YES band EV unvalidated
3. Data — winner's curse, CI gates, dispersion gauge all blocked by Gamma 403 / join
4. Fills — queue healthy (books/80 = 0.2–1.2), not a binding constraint
5. Calibration — passing (Brier7=0.053, ECE7=0.019) ✅

---

## 2. Existing-System Optimization

Items implied by the four specialist reports, ordered by expected delta:

**A. Confirm EVOLVE join output (today, ≥14:05Z)**
- Expected delta: HIGH if run completed — would unlock CI verdicts for 4 gates simultaneously
- Confidence: medium (EVOLVE ran but join outcome unknown)
- Effort: 1 VPS command (`cat logs/evolve/gate_ledger_latest.md`)
- Source: gatekeeper_report "VPS-side band_resolution_join.py is the critical path. Overdue."

**B. Jeddah off-allowlist fire audit**
- Evidence: gatekeeper advisory #2 — `{city: "jeddah", reason: "fire", live: True, sum_ask: 0.33}` in band_struct_lite without md_shadow record. Jeddah NOT in BAND_CITY_ALLOW.
- Expected delta: risk containment (prevent silent capital bleed into unapproved markets)
- Confidence: high (the log entry is unambiguous; whether a real order was placed is unknown)
- Effort: 1 VPS command (`grep jeddah data/maker_resting_state.json`)
- Source: gatekeeper advisory #2; exec_audit Moscow precedent

**C. Wuhan pricer gap**
- Evidence: calib_monitor — 0 pricer rows for Wuhan today vs 5-city allowlist active. Wuhan pair fills ARE occurring (exec_audit shows Wuhan NO pair Jul 03 ~03:59Z). Pricer may have skipped Wuhan at 08:09 snapshot timing.
- Expected delta: LOW (timing artifact likely; band is still quoting via BAND_REALBOOK_YES path)
- Confidence: high (likely transient)
- Effort: 0 (monitor tomorrow's calib report)

**D. M1_BETA_LOCKOUT revert (zero immediate effect, pre-stage for NO re-enable)**
- Evidence: gatekeeper M1 gate — DAY 21 stall, standing rule triggered Jun 13 (>14d stall → revert), proposal standing since Jun 27 (DAY 6 UNACTIONED)
- Caveat: metar_lockout.jsonl shows n_rows=12,450 today in shadow_summary (hot/2026-07-03 path), directly contradicting gatekeeper's "absent from all shadow directories." Discrepancy likely: gatekeeper checks data/shadow/YYYY-MM-DD/ path; shadow_summary indexes data/shadow/hot/YYYY-MM-DD/. Logger is probably running but in the hot/ subdirectory. Gate freeze at n=31 is therefore because lockout-NO live trades are suppressed (BAND_NO_ENABLED=False), not because the logger is dead.
- Expected delta: ZERO while BAND_NO_ENABLED=False. Pre-stages for NO re-enable.
- Confidence: high (CI straddles zero at n=31; standing rule is unambiguous)
- Effort: 1 config change
- Source: gatekeeper Gate 6 detail

**E. RECYCLE099 velocity decline trajectory**
- Evidence: exec_audit — today's 3 recycles (+$7.77) are processing pre-halt NO inventory (SELL_EXIT orders from positions placed before Jul 02). Once current 5 SELL_EXIT orders clear (Jul 03 positions resolve today; Jul 04 positions tomorrow), the recycle pipeline is exhausted unless new NO positions are placed.
- Expected delta: recycle revenue → $0/day post-clearing absent NO re-enable
- Confidence: high
- Effort: 0 (already understood; monitor)

**F. Beijing Jul 04 YES partial fill**
- Evidence: gatekeeper advisory #4 — pair bid 29526700... matched=2/8.89 shares, paired NO order (69599736...) not in maker_resting_state.
- Expected delta: misaligned partial pair (YES filled, NO unclear) → potential unhedged YES position
- Confidence: medium (NO may have filled separately without appearing in resting state snapshot)
- Effort: 1 VPS check

---

## 3. Gate Pipeline Review

From gatekeeper_report (12:43Z — freshest specialist data):

| Gate | n | Status | Blocker | ETA | Path to READY |
|---|---|---|---|---|---|
| 1 BAND_YES | ~6,147 | COLLECTING | Gamma 403 only | Tomorrow if EVOLVE ran today | band_resolution_join.py |
| 2 BAND_NO_PAIR_FAV | ~272 | COLLECTING | Gamma 403 + EVOLVE halt | Blocked (dual) | NO WR must recover first; CI won't help while halt stands |
| 3 FILLED_VS_FIRED | ~107† | COLLECTING | Gamma 403 only | Tomorrow if EVOLVE ran today | band_resolution_join.py — n just crossed 100 |
| 4 BASKET_EXIT | VOID | — | Retired Jun 22 | Never | — |
| 5 THERMO_MAKER_NO | 3 | COLLECTING | Rate=0 (THERMO_LIVE=False) | Never (kill at n=20) | Need THERMO re-enable; no case for it |
| 6 M1_BETA_LOCKOUT | 31 | AMBIGUOUS | Rate=0 (NO halted) | Never at current rate | Revert TEMP_FLOOR; zero CI path |
| 7 SUM_POSTED_0.70_0.85 | ~3,035 | COLLECTING | Gamma 403 only | Tomorrow if EVOLVE ran today | band_resolution_join.py |

**Gates nearest READY**: 1 and 3 (n-complete, Gamma 403 is sole blocker). Gate 3 crossed n=100 this cycle — it is now the HIGHEST PRIORITY join target because it measures FILLED_VS_FIRED quality (winner's curse) and has the freshest n boundary.

**What would accelerate accumulation WITHOUT degrading expectancy**:
- Gates 1, 3, 7: n already >> 100. Breadth changes are irrelevant — only the join matters.
- Gate 2: n >> 100 but dual-blocked. Standalone NO WR must recover above charter rail; accumulation is moot until then.
- Gate 6: revert TEMP_FLOOR eliminates the stalled gate cleanly (CI cannot improve at rate=0). Pre-stages for NO re-enable.
- Gate 5: kill signal at n=20 is the action; n=3 → will never reach kill gate unless THERMO re-enables.

---

## 4. Assumption Attack

### Assumption 1: Dispersion premium persists (market implied < realized)

The band earns by posting at market-implied prices that are systematically overpriced relative to realized weather variance. This requires dispersion ratio > 1.10.

**What supports it**: Nothing in today's reports. Calib_monitor: d+0 ratio = 0.817 (7d median, all 5 days sub-1.10, no recovery trend). Prior cycle d+2 estimate = 0.340 (operative for active YES positions at BAND_YES_LIVE_MIN_DOUT=2). No day in 5-day window breaches 1.10. Jun 29 worst: 0.663. Jun 30 best: 0.976 — still below threshold.

**What threatens it**: The d+2 ratio of 0.340 means realized temperature deviation exceeds the market's implied spread at 2-day horizon. The wing prices are NOT systematically overpriced; they may be underpriced. If confirmed with resolution-joined data, YES d+2 fills are negative EV from a pure dispersion standpoint.

**Verdict: SEVERELY THREATENED.** This is the most urgent structural risk. BAND_NO_ENABLED=False correctly removed the NO side (WR=39.2%<50%). YES continues on the same structural headwind, unvalidated in this data window. Only band_resolution_join.py output can confirm or deny.

### Assumption 2: Fills are not adversely selected (winner's curse)

**What supports it**: 2 confirmed pair merges (Jul 01: locked_pnl=$1.425, Jul 03: locked_pnl=$0.89). Pair structure partially immunizes: filling both YES+NO at sum ≤ 0.90 locks ≥ $0.10/sh at close regardless of outcome.

**What threatens it**: n=28 total fills — winner's curse unassessable per exec_audit. Moscow NO at 0.93 (outside allowlist) filled — extreme-price fill at adverse level. Three consecutive NO losses ($15.29, Jul 01 pnl_ledger) from Beijing/Chengdu/Munich resolving YES — may reflect adverse selection in the high-confidence NO bucket rather than random variance. Pair merges are the only confirmed-positive data points.

**Verdict: UNCERTAIN. Pair_fav partially de-risks via locked spread; standalone YES d+2 fills unknown. Priority: resolve at n≥40 via join.**

### Assumption 3: RECYCLE099 velocity scales

**What supports it**: 3 recycles today (+$7.77), clear mechanism (SELL_EXIT at 0.99 filled as resolution approaches). Consistent with Jun 29 pattern (+$22.05 from RECYCLE099 per pnl_ledger). Net velocity historically reliable.

**What threatens it**: RECYCLE099 depends on new NO positions entering the pipeline. BAND_NO_ENABLED=False → zero new NO fills → zero future SELL_EXIT → recycle pipeline exhausts when current 5 orders clear (Jul 03–04). Today's recycles are the last of the pre-halt inventory. Recycle revenue → ~$0/day by Jul 05 unless NO is re-enabled.

**Verdict: THREATENED MEDIUM-TERM. Critical dependency on NO re-enable.**

---

## 5. Market Intelligence — [0] Competitor Posture (Jul 3 mod 3 = 0)

**badatmath_watch delta** (from shadow_summary.json, 2026-07-03T18:49Z):

| Date | n_rows | mtime |
|---|---|---|
| Jun 29 | 9,733 | 23:58Z |
| Jun 30 | 10,058 | 23:58Z |
| Jul 01 | 7,861 | 23:58Z |
| Jul 02 | 5,025 | 23:54Z |
| **Jul 03** | **16** | **18:28Z** |

**Jul 03: 16 rows vs 5,000–10,000 on prior days. A 300× drop.** The logger last wrote at 18:28Z and is otherwise current (hot/2026-07-03/badatmath_watch.jsonl). Two interpretations: (a) badatmath dramatically reduced Polymarket weather activity today — possible (July 4 US holiday weekend); (b) the watcher has a detection issue. Given the logger IS writing (18:28Z entry), interpretation (a) is more likely.

**Implication**: Reduced badatmath volume is net-positive for our maker fills. Badatmath typically takes the other side of weather books as a counterparty. If they're idle today, adverse selection pressure is also lower — our maker fills may be cleaner today than average.

**Leaderboard wallet teardown**: Cannot access Polymarket data-api from this sandbox. Prior state_log intelligence: detect_lag_s=50.6s on Jun 23 (within our 30s–2min copyable window). No new data.

**agent_context/research_status.md stale flag**: File is from 2026-05-16 and describes the defunct LDA strategy (BTC/ETH/SOL binary markets). This is dead context — completely mismatched to the current BAND strategy. Agents consuming research_status.md as ground truth will receive LDA runbooks and fields that do not apply. This file should be updated or deprecated.

---

## 6. Experiments

### Experiment A — pair_fav dispersion independence test

**Hypothesis**: d+0 pair_fav fills (locked spread ≥ $0.08–0.10/sh at close) have positive EV independent of the general dispersion ratio alert, because they harvest the YES+NO bid spread simultaneously rather than individual wing mispricings. The dispersion gauge measures spread risk for one-sided positions; pairs cancel it.

**Data**: band_struct_lite pair merge records — n=2 resolved (Jul 01: $1.425 locked, 9.5sh; Jul 03: $0.89 locked, 8.9sh). At 5–6 pair fills/day → n≥40 by ~Jul 10.

**Time**: ~7 days (passive — pairs already accumulating).

**Cost**: $0.

**Success metric**: n≥40 resolved pairs, mean locked_pnl/share ≥ $0.05, CI lower bound > 0.

**Decision-if-yes**: Pair_fav is a structurally independent positive-EV channel. Expand BAND_CITY_ALLOW for pair_fav scope to 7–8 cities to increase pair_cands from ~1.6 to ~3.0/cycle.

**Decision-if-no**: Pair margins eroded; tighten BAND_PAIR_SUM_MAX to 0.88 or reduce BAND_PAIR_FAV_YES_MAX.

---

### Experiment B — Jeddah expand_city allowlist bypass audit

**Hypothesis**: The expand_city scanner has a code path that bypasses BAND_CITY_ALLOW, potentially placing live orders in unapproved cities.

**Data**: (1) `grep jeddah data/maker_resting_state.json` — check for Jeddah resting order; (2) Code review of expand_city path in stwa_engine.py for allowlist check.

**Time**: Immediate (2 VPS commands).

**Cost**: $0 to check. If order exists: cancel (blocks ~$3–5 unapproved exposure).

**Success metric**: Clear answer — order exists (cancel + patch) OR no order (add guard to code path).

**Decision-if-order-exists**: Cancel immediately; add `if city not in BAND_CITY_ALLOW: continue` in expand_city before any live order placement.

**Decision-if-no-order**: Expand_city is already shadow-only or gated; document and confirm.

---

### Experiment C — metar_lockout path discrepancy / Gate 6 root cause

**Hypothesis**: gatekeeper reports metar_lockout.jsonl ABSENT from shadow directories. But shadow_summary shows hot/2026-07-03/metar_lockout.jsonl at n=12,450. Discrepancy is path: gatekeeper checks data/shadow/YYYY-MM-DD/; logger writes data/shadow/hot/YYYY-MM-DD/. If logger IS running, Gate 6 freeze is NO-halt suppression, not logger death.

**Data**: `ls /root/Klaus/data/shadow/2026-07-03/metar_lockout.jsonl` vs `ls /root/Klaus/data/shadow/hot/2026-07-03/metar_lockout.jsonl`.

**Time**: Immediate.

**Cost**: $0.

**Success metric**: Confirm which path exists and whether events include lockout-NO candidates.

**Decision-if-hot-path-exists**: Logger running; gate freeze is NO-halt-blocked. Revert TEMP_FLOOR immediately (zero effect now; pre-stages for NO re-enable). Gate 6 ETA changes from "never" to "conditional on NO re-enable."

**Decision-if-neither-path**: Logger genuinely dead; revert proposal valid as-is; gate permanently at n=31.

---

## 7. Single Best Action

**Check EVOLVE daily cycle output + verify Jeddah order.**

Two VPS commands, sequential:

```bash
# 1. Confirm EVOLVE ran band_resolution_join.py today
cat /root/Klaus/logs/evolve/gate_ledger_latest.md 2>/dev/null | head -60 \
  || echo "No EVOLVE output yet"

# 2. Verify no Jeddah off-allowlist order resting
grep -i jeddah /root/Klaus/data/maker_resting_state.json \
  && echo "JEDDAH ORDER FOUND - CANCEL" \
  || echo "No Jeddah order — OK"
```

**Why this wins**:

From gatekeeper_report: "VPS-side band_resolution_join.py is the critical path. Unblocks CI for gates 1, 2, 3, and 7 simultaneously in one run. Overdue. Gate 3 has now crossed n=100." EVOLVE ran for the first time today (≥14:05Z, post-phantom fix). If the join ran, CI verdicts for 4 gates are in git now. A READY verdict on BAND_YES validates YES d+2 edge and enables stake/breadth scaling — the highest compounding lever available. A REJECTED verdict stops capital allocation into a negative-EV channel. Either outcome resolves the dominant uncertainty.

From exec_audit_report (Moscow precedent) and gatekeeper advisory #2: Jeddah live=True without allowlist check is an open capital risk. 30-second check prevents potential silent bleed in an unscreened market.

**P(success)**: ~0.85 (EVOLVE ran; join likely completed). **Effort**: 2 commands. **Compounding impact**: resolves the highest-value unknown in the system.

---

## PROPOSED ACTIONS (human review)

### PA-1: Revert METAR_LOCKOUT_TEMP_FLOOR to 0.5°C
**Gate**: M1_BETA_LOCKOUT (Gate 6)
**Action**: Set `METAR_LOCKOUT_TEMP_FLOOR = 0.5` in stwa_engine.py.
**Evidence**: n=31, AMBIGUOUS (CI=[−20.6, +24.4], straddles zero). Rate=0 for 21 consecutive days. Standing rule triggered Jun 13 (>14d stall → revert). Proposal standing since Jun 27 — DAY 6 UNACTIONED. metar_lockout.jsonl likely running in hot/ path (n=12,450 today per shadow_summary) but gate cannot grow while BAND_NO_ENABLED=False suppresses live trades.
**Immediate effect**: ZERO (NO halted). Pre-stages for NO re-enable.
**Human required**: YES — code change.

### PA-2: Audit expand_city scanner for BAND_CITY_ALLOW enforcement
**Action**: Verify and enforce BAND_CITY_ALLOW in expand_city code path.
**Evidence**: Jeddah `live: True` fire in band_struct_lite without md_shadow (gatekeeper advisory #2). Moscow precedent: $5.58 at risk in off-allowlist position (exec_audit).
**Human required**: YES — code review + possible patch.

### PA-3: Resolve Beijing Jul 04 pair partial fill
**Action**: Verify Beijing YES partial (2/8.89 matched) has corresponding NO fill or cancel unhedged leg.
**Evidence**: gatekeeper advisory #4.
**Human required**: Preferred.

### PA-4: Update agent_context/research_status.md to BAND strategy
**Action**: Rewrite to describe BAND-V3 strategy state, gates, and agent runbooks. Current file describes defunct LDA strategy from May 2026 — misguides any agent consuming it as ground truth.
**Human required**: YES — process document.

---

*Research audit agent @claude | 2026-07-03T19:10Z | Branch: claude/find-lag-parameter-rFQ0N*
*Primary bottleneck: equity deployed 0.43 turns/day (NO halt + unvalidated YES d+2 dispersion) | Best action: check EVOLVE join output + verify Jeddah off-allowlist fire*
