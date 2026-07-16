# Research Audit — 2026-07-16

**Generated:** 2026-07-16T10:40Z  
**Snapshot:** 2026-07-16T10:21:35Z (age ~19 min — FRESH ✅)  
**Klaus service:** active ✅  
**Bankroll:** $26.547453 | **Open positions:** 0  
**Band status:** DARK — day 10 (BAND_LIVE=False since 2026-07-06)  
**Data access:** DEGRADED (git fetch blocked — all data via GitHub MCP; state_log.md inaccessible at 494k chars; shadow_summary.json inaccessible at 304k chars)  
**research_status.md:** STALE — last updated 2026-05-16 (LDA era, pre-sniper). Does not reflect current UPDOWN-SNIPER primary strategy or band wind-down. Not used as ground truth.

**Specialist reports consumed:**
- exec_audit_report.md: 2026-07-16T07:04Z ✅
- calib_monitor_report.md: 2026-07-16T08:30Z ✅
- gatekeeper_report.md: 2026-07-16T09:13Z ✅
- pnl_ledger_report.md: 2026-07-15T23:37Z ✅ (yesterday 23:37Z — within 36h)

---

## §1 — PRIMARY BOTTLENECK

**Capital depletion from an unconfirmed-edge sniper, compounded by an apparent daily stop breach.**

The compounding equation is (ROI/turn) × (turns/day) × (equity deployed). All three terms are impaired:

- **Equity deployed:** $26.55 — already 29.8% of the engine ruin floor ($89.16). Band re-enable requires $89.16. At current net PnL rate the band is unreachable.
- **ROI/turn:** Sniper nominal WR = 98.7% (n=76) but CI-lo = 92.9%, which is BELOW breakeven of 96.2% (gatekeeper, commit e7bb33bf6). Kelly is OFF. Each loss consumes ~$4.20–4.63 = ~15–17% of remaining bankroll; each win returns ~$0.20–0.80 net. The payoff asymmetry is severe and the edge is statistically unconfirmed.
- **Turns/day:** 2.54 (pnl_ledger), but each turn is near-fully deployed capital (~$4.50 stake vs $26.55 bankroll = 17%). High turns on a small edge with binary outcomes = high ruin risk.

**Critical new finding this session — DAILY STOP APPEARS BREACHED:**

| Metric | Value |
|---|---|
| Daily start Jul-16 | $33.856 (gatekeeper) |
| Bankroll at 10:21Z snapshot | $26.547 |
| Intraday PnL Jul-16 | **−$7.31** |
| Sniper DAILY_STOP threshold | **−$4.50** |
| Breach amount | **−$2.81 beyond stop** |

At 07:31Z the gatekeeper saved capital at $31.07 with intraday = −$2.79 (within stop). Between 09:05Z (gatekeeper snapshot, still $31.07) and 10:21Z (data-mirror snapshot), capital fell an additional $4.52, indicating another sniper loss. Total day loss of −$7.31 is 163% of the −$4.50 daily stop.

**The daily stop did not prevent the additional fire.** Either the stop mechanism is not enforced at fire-time, or the win at 07:31Z (+$0.81 net) reset the running-loss counter, allowing re-entry that subsequently lost. This is the binding operational failure today.

**Rank:** Capital deployed is the primary bottleneck in abstraction, but **daily stop enforcement** is the specific mechanism failing today — it is what is actively consuming the remaining capital.

---

## §2 — EXISTING-SYSTEM OPTIMIZATION

All band/STWA/PAIR_FAV engines are dark. The only active revenue system is UPDOWN-SNIPER. Analysis confined to sniper + infrastructure.

| Item | Finding | Expected Delta | Confidence | Effort |
|---|---|---|---|---|
| Daily stop enforcement | Mechanism appears to allow fire past −$4.50 limit (see §1). If a win resets the loss counter, the stop is effectively paused after any win that follows a partial-day loss — the correct implementation accumulates from day_start, not from last win. | Caps maximum daily loss at −$4.50 vs the −$7.31 seen today. At current WR, saves approximately 1 loss event every 3–5 days. | HIGH (arithmetic, not model-dependent) | LOW (1 code read + 1-line fix if confirmed) |
| TRACKER_RESTART_BUG | 100% of fills are UNTRACKED (exec_audit). No TP/SL management on open positions, no per-trade PnL, no proper stop enforcement at position level. Has persisted since the Jul-15 02:40Z restart. | Restoring position tracking would enable per-trade TP/SL, reduce PnL attribution gap, and allow sniper Kelly to be computed properly. | HIGH (root cause identified: in-memory position state reset at restart) | MEDIUM (requires persistent state write on fire + read at startup) |
| Disk at 97%+ full | system_status.txt (07:04Z): 97G volume, 89G used, 4G free. pnl_ledger (23:37Z yesterday): 98%, 3G free. At current shadow log write rate (~175 band_struct records/day + 246 fill-tape lines/3d + thermo/metar candidates: 13k+16k in the gate run), free space is shrinking. Bot crash on full disk is a silent capital risk. | Prevent silent crash. No PnL improvement but avoids total service loss. | HIGH | LOW (log rotation or manual purge of old shadow files) |
| $360 MAKER SELL anomaly | Jul-14 15:49Z, 367.66 sh @$0.98 = $360.31. Source unknown. Third consecutive report without resolution (exec_audit CARRY-ALERT-3). If this represents pre-existing band positions still filling from before Jul-6 wind-down, more similar fills may follow — these are adversely selected (filled when market has moved). | Resolve source first. If pre-shutdown resting orders, net effect depends on current vs. entry price. | LOW (no data to assess without condition_id mapping) | HIGH (requires CLOB position lookup on VPS) |

---

## §3 — GATE PIPELINE REVIEW

**All gates frozen at day 10 of band dark. Zero resolutions flowing. No ETAs.**

| Gate | Status | Blocking condition | Acceleration path |
|---|---|---|---|
| G1: BAND_YES | AMBIGUOUS (n=934, CI [−10.9,+21.1] straddles 0) | BAND_LIVE=False freezes resolutions. G3 winner's curse means all ROI figures are upper bounds. | Cannot accelerate without band live — which requires capital >$89.16 first. |
| G2a: BAND_NO d+1 | AMBIGUOUS (live n=51, WR=39.2% effectively REJECTED) | BAND_NO_ENABLED=False since Jul-02. 39.2% WR at n=51 is a near-REJECT. | n=51 data sufficient for a REJECT verdict. Human should confirm REJECT vs wait-for-more. |
| G2b/G2c: PAIR_FAV YES/NO | COLLECTING (n=9) | Requires BAND_LIVE=True; rate ~11/day → n=40 in ~8.3d post-re-enable. | Cannot collect without BAND_LIVE. Cannot re-enable BAND_LIVE without $89.16 capital. |
| G3: FILLED_vs_FIRED | WATCH_ITEM (n=75, fill ROI −75.8% vs sim +7.6%, CI [−75.0,−34.2]) | Winner's curse CONFIRMED. Jul-05 clip-guard cross-tab OUTSTANDING (mandatory pre-band-re-enable). | Human must complete the Jul-05 cross-tab to close G3. This is the blocker for any band re-enable even after capital recovers. |
| G5: THERMO_MAKER_NO | REJECTED | Final. 13,122 shadow candidates accumulating uselessly. | Kill THERMO shadow logging to recover disk space (shadow files are 13k+ rows and growing). |
| G6: M1_BETA_LOCKOUT | REJECTED | Final. 16,844 shadow candidates accumulating (14,722 just on Jul-16). | Kill M1_BETA shadow logging. Same disk concern. |
| G7: SUM_POSTED [0.70,0.85] | AMBIGUOUS (n=382, CI [−11.4,+38.9]) | Frozen. Shadow rate ~9/day. CI straddles 0; not a re-enable signal. | No acceleration possible while dark. |

**Most important gate item today:** G3 Jul-05 cross-tab is the outstanding mandatory human action that blocks band re-enable regardless of capital recovery. That work is overdue since Jul-11.

**Disk alert (derived from gate data):** G5 and G6 shadow loggers are generating 29k+ rows per run while their gates are permanently REJECTED. These are pure disk waste. Recommend disabling both shadow loggers by human directive.

---

## §4 — ASSUMPTION ATTACK

The band system rests on three load-bearing assumptions. Status as of today:

**Assumption 1: Dispersion premium persists — the market over-estimates temperature spread, giving YES band a structural edge.**

**STATUS: DIRECTLY FALSIFIED.** calib_monitor S3 alert has fired for 14 consecutive days. Fresh direct measurement today (n=68, not carry-forward): median disp_ratio = **0.765** (threshold 1.10). All 68 observations are below 1.10; 65 of 68 are inverted (implied_sigma < true_sigma). The market is now UNDER-dispersed relative to true temperature variance. This is the inverse of the required condition — the YES band has negative structural edge at today's pricing. Trend: flat / no recovery signal (first-half mean 0.775, second-half 0.774).

This is the core finding. The band edge does not exist at current market prices, independent of any other system health metrics.

**Assumption 2: Fills are not adversely selected — maker orders fill randomly, not against us when the market has moved.**

**STATUS: CONFIRMED AGAINST (G3, n=75).** Fill ROI = −75.8% vs simulated fire ROI = +7.6%. CI = [−75.0, −34.2] — does not include zero. Winner's curse confirmed. The 8 residual MAKER fills in the 7d exec tape at <0.10 (prices 0.02–0.09) reinforce this: low-probability legs filling are filling because the market has already moved away from the mode, making those fills adversely selected by construction.

**Assumption 3: Recycle velocity scales — RECYCLE099 exits flow freely and don't create exit bottlenecks.**

**STATUS: UNTESTABLE / MOOT.** No exit099_live.jsonl exists for Jul-15 (file absent). Zero RECYCLE099 events since band went dark Jul-6. Cannot assess; irrelevant while band is dark. This assumption will need re-verification when/if band re-enables.

**Summary:** Both testable load-bearing assumptions are falsified. The band cannot generate edge in today's market regime, confirmed by independent calibration and fill-quality measurements.

---

## §5 — MARKET INTELLIGENCE (Rotation [1]: Market Census)

*Day 16 mod 3 = 1 → Market census: new weather cities/products on Gamma; depth changes in our 51.*

**Access constraint:** Gamma public search and Polymarket market feed are inaccessible without direct HTTP or git fetch. Reporting from shadow data only (indirect census).

**Cities active in shadow fire observations (Jul-11–16, n=68 fire rows):**

| City | Shadow fires | Days-out mix |
|---|---|---|
| Beijing | present all 5 days | d+1, d+2 dominant |
| Chengdu | present all 5 days | d+2 dominant |
| Chongqing | present 4/5 days | d+2 dominant |
| London | present 3/5 days | d+1 mix |
| Munich | present all 5 days | d+1, d+2 mix |
| Seoul | present all 5 days | d+1, d+2 |
| Shanghai | present 4/5 days | d+2 dominant |
| Taipei | present all 5 days | d+1, d+2 |
| Tokyo | present 3/5 days | d+2 dominant |
| Wuhan | present all 5 days | d+2 dominant |

**Depth observation:** sum_gate (BAND_SUM_MAX=0.85) is blocking the majority of d+1/d+2 candidates. Observed sum_posted values from Jul-16 shadow fires: Seoul d+1=0.80, Taipei d+1=0.84, Seoul d+2=0.84/0.76, Wuhan d+2=0.63/0.84, Shanghai d+2=0.84, Chongqing d+2=0.62/0.68, Chengdu d+2=0.61, Munich d+2=0.69/0.73. The majority of observed values cluster at 0.60–0.84 — just below and above the 0.85 gate. This is consistent with prior-session findings that the sum gate is the primary capacity constraint on shadow fires. However, given disp_ratio=0.765, opening the sum gate to raise fire count would be ill-advised — the edge doesn't exist to fill additional volume into.

**Delta vs state_log knowledge:** No new city additions or Polymarket weather product changes can be confirmed from shadow data alone. No structural depth changes observed within the 51-city set; fire frequency is stable at 10–18/day across the 5-day window.

**Gamma/Polymarket direct census required on next VPS access to detect any product changes.**

---

## §6 — THREE EXPERIMENTS

### Experiment A: Daily-Stop Loss Counter Reset Test

**Hypothesis:** The sniper's running daily loss counter is reset or paused by any winning position, allowing continued firing after a partial-day loss + subsequent win. This would explain how capital fell from −$2.79 (within −$4.50 stop, 07:31Z) to −$7.31 (breach) later the same day.

**Data needed:** Read `strategy/updown_sniper.py` (or equivalent) and find the daily_loss tracking logic. Specifically: is `daily_loss` computed as `session_start_capital − current_capital` (correct) or as a running sum that resets/pauses on wins (broken)?

**Time:** 15 minutes. **Cost:** 0. **Success metric:** Either (a) confirm the bug and produce a 1-line fix, or (b) confirm the stop is computed correctly, requiring alternative explanation for today's breach.

**Decision if confirmed-bug:** Apply fix immediately (Tier 1 — bug fix with clear root cause). Capital bleed from stop-bypass is material at $26.55 bankroll.  
**Decision if correct-code:** Investigate alternative cause (e.g., two rapid consecutive losses before stop check ran). Tighten check interval to every-fire rather than every-cycle.

---

### Experiment B: Sniper N-to-Kelly Horizon Computation

**Hypothesis:** At n=76 WR=98.7% CI-lo=92.9%, the minimum n required to push CI-lo above the 96.2% breakeven (at 95% Wilson confidence) is approximately n=300–600 trades. At 20 fires/day, this is 15–30 calendar days — and the capital trajectory at current net daily PnL cannot sustain the bot for that long.

**Data needed:** Python Wilson interval calculation over n ∈ {76, 100, 200, 300, 500} at p_hat=0.987. Compare to capital sustainability at −$0.30 net/day (pnl_ledger Jul-15 baseline).

**Time:** 20 minutes. **Cost:** 0. **Success metric:** A specific n_target and calendar-date estimate for Kelly re-enable, plus a minimum capital floor required to survive until that n is reached.

**Decision if Kelly-horizon > capital-survival-horizon:** The sniper is playing a negative expected-value game vs. ruin probability. Reduce stake or halt pending a capital infusion. Quantifies urgency.  
**Decision if horizon is achievable:** Raises confidence; sets a monitoring milestone for the EVOLVE session.

---

### Experiment C: G2a BAND_NO d+1 Formal REJECT

**Hypothesis:** The existing n=51 data on BAND_NO d+1 (WR=39.2%) is sufficient to issue a formal REJECT verdict without waiting for band re-enable to bring in more resolutions.

**Data needed:** Wilson 95% CI on n=51, p_hat=0.392. Compare CI upper bound to the breakeven win rate for BAND_NO (which depends on the NO ask price; typical ask 0.52–0.85, so breakeven ranges 52–85%). If CI-upper < breakeven even at the most generous (lowest) ask tier, this is a REJECT.

**Time:** 10 minutes. **Cost:** 0. **Success metric:** Formal REJECT verdict with CI math, or "still ambiguous — need n=100."

**Decision if REJECT confirmed:** Human directive to move G2a from AMBIGUOUS to REJECTED in the gatekeeper ledger. Cleans the open gate count and prevents future confusion about whether NO-side can be re-enabled without additional data.  
**Decision if still ambiguous:** Carry forward as is, pending band re-enable to accumulate more resolutions.

---

## §7 — SINGLE BEST ACTION

**Investigate and fix the daily stop breach (Experiment A first step: read the stop-loss logic).**

**Why this:**
- The daily stop of −$4.50 was designed as a hard guardrail against catastrophic intraday drawdown
- Today it failed: capital dropped −$7.31 on the day (gatekeeper Jul-16 + snapshot), a 163% overshoot of the limit
- At $26.55 bankroll, one more unguarded losing day puts the system below any rational ruin floor ($15–20 range where even a single sniper stake is >20% of capital)
- The exec_audit confirms 100% UNTRACKED fills — meaning no per-position stop management exists either; the daily stop is the *only* risk management layer, and it may be broken
- This is higher impact than any calibration or gate optimization: those are theoretical future edges, this is preventing immediate ruin

**Concrete first step:** On VPS, run:
```bash
grep -n "daily_loss\|daily_stop\|DAILY_STOP\|day_loss\|session_start" strategy/updown_sniper.py | head -40
```
Then check whether the daily loss accumulator is computed as `(daily_start_capital − current_capital)` evaluated at every pre-fire gate check, or whether it uses a running sum that can reset.

**Expected outcome:** Either a 1-line fix is identified and applied (Tier 1, autonomous), or the breach is explained by legitimate mechanics (e.g., two losses faster than the check could fire), which requires tightening the check frequency.

**Supporting data:** gatekeeper_report.md (09:13Z): capital $31.07, intraday −$2.79, daily stop −$4.50 (within limit). data-mirror snapshot (10:21Z): capital $26.55 = −$7.31 intraday. Breach of −$2.81. Exec_audit confirms TRACKER_RESTART_BUG — no per-position safety net exists.

---

## PROPOSED ACTIONS (human review)

1. **[URGENT] Daily stop investigation:** Verify whether the −$7.31 Jul-16 intraday loss (vs −$4.50 stop) reflects a mechanism bug or rapid-fire coincidence. Fix before next sniper cycle if bug confirmed.

2. **[DISK] Log space:** system_status.txt shows 97% disk usage (4 GB free). pnl_ledger says 98% / 3 GB free. G5 and G6 shadow loggers (REJECTED gates) are generating 13k+ and 16k+ rows per run. Consider disabling THERMO_MAKER and M1_BETA shadow logging to reclaim disk space and prevent silent bot crash.

3. **[GATE] G2a formal REJECT decision:** n=51 BAND_NO d+1 at WR=39.2% may be sufficient for a REJECT. Human to confirm or run Experiment C to formalize.

4. **[GATE] G3 Jul-05 cross-tab:** Outstanding mandatory human action since Jul-11. Blocks all band re-enable paths. No timeline provided in any specialist report; this is the longest-standing open action.

5. **[ANOMALY] $360 MAKER SELL (Jul-14, CARRY-ALERT-3):** Three consecutive reports without resolution. Source remains unknown. If residual pre-shutdown band bids are still resting on CLOB, they represent active adverse-selection exposure with no position management. Requires CLOB lookup on VPS to resolve.

6. **[INTEL] research_status.md:** File is 61 days stale (updated 2026-05-16, describes LDA strategy). Scheduled agents reading this as ground truth receive incorrect mandates. Requires human update to reflect current UPDOWN-SNIPER primary strategy and band wind-down state.

---

*Research Audit is REPORT-ONLY — no code edits, no flag changes, no gate promotions/kills.*  
*All ROI figures for band gates are UPPER BOUNDS per winner's curse (G3, n=75, CI [−75.0,−34.2]).*  
*Dispersion edge is INVERTED (disp_ratio=0.765, day 14 of S3 alert) — band re-enable requires dispersion recovery before any other consideration.*
