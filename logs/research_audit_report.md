# Research Audit — 2026-07-17T10:30Z

**Specialist reports consumed:**
- exec_audit_report.md — 2026-07-17T07:08:32Z ✓
- calib_monitor_report.md — 2026-07-17T08:21Z ✓
- gatekeeper_report.md — 2026-07-17T09:15Z ✓
- pnl_ledger_report.md — 2026-07-15T23:37Z ✓ (prior day, within 36h window; Jul 16 evening covered by state_log 22:08Z)

**SNAPSHOT:** 2026-07-17T10:11:16Z — age ~20 min, FRESH  
**System:** `klaus systemd: active` ✓ PROCEEDING  
**Bankroll:** $31.757 | Daily start: $28.157 | Today P&L: +$3.600 (+12.8%) | Total cumulative PnL: −$75.40

---

## 1. Primary Bottleneck: Capital Below Ruin Floor

**Bottleneck: Capital recovery** — $31.76 vs ruin_floor $89.16 (35.6% of threshold)

All band engine paths are mechanically blocked. BAND_LIVE=False (day 11), NEG_RISK_ARB entry-blocked, zero live weather positions. The updown sniper running the candidate policy {P_MIN≥0.995, 5m-only, KELLY_FRAC=0.50} is the **sole active revenue stream**. Per gatekeeper_report: "Capital $31.757 below engine ruin_floor $89.16 (35.6%) — all band re-enable paths mechanically blocked."

Context: capital peaked at a 30d-HWM of $222.90 (band_config.txt BAND_LIVE comment); the charter kill-switch triggered at 50% of HWM ($111.45). From $31.76, clearing ruin_floor ($89.16) requires +181% — approximately 40 uninterrupted winning sniper fires at current Kelly sizing (~$15.88/clip, +4.72%/win per shadow slice).

Today's trajectory is positive: bankroll.json daily_start=$28.157 → $31.757 = +$3.60 (2 confirmed capital-correction pairs at base of trades.jsonl, both wins). However, sniper appears idle from ~02:24Z to 10:11Z (~8hr gap, no new capital-correction entries, maker_fills_recent.log ends 02:24Z). This is consistent with state_log 22:08Z "candidate ~4× more selective than v1" but warrants monitoring.

**Critical caveat:** Candidate live n ≈ 9-13 (5 confirmed post-waiver per state_log 22:08Z + 2 confirmed today — direct count impeded by TRACKER_RESTART_BUG, pnl_ledger). Shadow candidate slice n=44 (gatekeeper). Both are well below the n=100 decision threshold. The current positive run is consistent with a WR=0.988 process on a small sample; it does not confirm edge. Do not expand stake, lower P_MIN, or re-enable band on this alone.

Turns/day and ROI/turn are secondary bottlenecks only once capital recovers past $89.16. The binding variable right now is **fire frequency on a single asset (BTC)** at ~1/hr, throttled by P_MIN selectivity.

---

## 2. Existing System Optimization

### a) Disk — CRITICAL (operational threat, highest urgency)
- system_status.txt: 97% used, 4GB remaining
- calib_monitor_report: "96% full, 4GB approaching critical"
- shadow_summary.json shows hot/2026-07-07 and hot/2026-07-08 directories present and stale; binance_trade alone is ~370MB/day × 2 stale days ≈ 740MB; metar_lockout, ob_delta, market_timeline each ~600MB–1.4GB per stale day directory — estimated 5–10GB freeable from 07-07/07-08 alone
- These files are analysis-dead for the current strategy (sniper uses none of them)
- **Expected delta:** prevent service halt; confidence HIGH; effort LOW
- If disk fills while sniper is firing mid-session, the service may crash and an open position would be unmonitored

### b) Orphan MAKER orders on CLOB (exec_audit ALERT 1 HIGH)
- exec_audit: 12 MAKER fills UNTRACKED through Jul 15 02:40Z restart; maker_resting_state={}
- Evidence of post-restart persistence: Jul 16 fills BUY@$0.09×86.608sh ($7.79), BUY@$0.06×30.5sh ($1.83)
- Stale resting BUY stubs at $0.02–$0.09 are weather-band orphans being hit by informed takers; we bear the loss if the market resolves YES
- **Expected delta:** recover idle capital + eliminate adversely-selected maker exposure; confidence HIGH; effort LOW

### c) eth/sol/xrp per-asset shadow grade — standing item (TODAY)
- state_log 22:08Z: "eth/sol/xrp day-2 tapes complete (12,002 snaps each); first per-asset grade 07-17"
- This is a queued standing item, not a new proposal
- If positive (point WR ≥ BE ~96.3% at p≥0.995 filter), fire cadence expands to ~3-4×/hr
- **Expected delta:** 3-4× turns/day → proportional acceleration of capital recovery to $89.16; confidence MEDIUM (no grade yet); effort LOW

### d) Fill logger dark (exec_audit ALERT 2 MEDIUM + pnl_ledger TRACKER_RESTART_BUG)
- Zero [SNIPER-FILL] structured log lines; all sniper fills arrive as CAPITAL_CORRECTION rows
- pnl_ledger: "14 of 20 fills invisible to analytics"
- Without structured fill logging: intra-session monitoring is blind, candidate live n count is estimated not counted, per-trade diagnostics unavailable
- **Expected delta:** enable real-time edge monitoring and accurate gate progress; confidence HIGH; effort MEDIUM

---

## 3. Gate Pipeline

**0 READY. 0 newly READY or REJECTED since last run. All band gates frozen by structural blockers.**

Structural blockers (gatekeeper_report, all unchanged):
1. BAND_LIVE=False (mechanical — requires capital > ruin_floor AND owner action)
2. Capital $31.76 < ruin_floor $89.16
3. Winner's curse CONFIRMED (G3 WATCH_ITEM: filled WR=17.3%, ROI=−75.8% vs sim +7.6%; gap −83.4pp — simulation ROI values are upper bounds only)
4. disp_ratio7=0.704 (15 consecutive days below 1.10 threshold; n=110 decision-grade)

**Shadow accumulation by gate (band gates frozen at AMBIGUOUS):**
| Gate | Status | Shadow n | +/day | ETA |
|------|--------|----------|-------|-----|
| G1 BAND_YES | AMBIGUOUS | 136 | +13 | FROZEN |
| G7 SUM_0.70_0.85 | AMBIGUOUS | 92 | +9 | FROZEN |
| G2b PAIR_FAV_YES | COLLECTING | 9 | ~0 | FROZEN |
| G2c PAIR_FAV_NO | COLLECTING | 9 | ~0 | FROZEN |
| G5 THERMO_MAKER | REJECTED | — | — | N/A |
| G6 M1_BETA | REJECTED | — | — | N/A |

**Candidate sniper gate (pre-registered; not in formal ledger):**
- Shadow slice (p≥0.995, 5m-only): n=44, WR=1.000, CI-lo=0.9197 vs BE=0.9557 — COLLECTING
- Needs n≈84 for CI-lo to clear zero-loss criterion; n≥150 total shadow for formal gate (waived by owner once at waiver 14:59Z Jul 16; re-engage formal gate)
- At ~13 shadow/day + live fires: n=100 shadow in ~4d BTC-only pace, ~1-2d if eth/sol/xrp expand scope
- Live tape n≈9-13 estimated; cannot count cleanly until TRACKER_RESTART_BUG fixed

**What would accelerate accumulation WITHOUT degrading expectancy:**
- Run eth/sol/xrp per-asset grade today → if positive, breadth expansion multiplies shadow fires per day without changing the P_MIN filter (breadth, not threshold relaxation)
- Do NOT lower P_MIN to accumulate faster — the loss-structure evidence (all v1 losses in p<0.995, zero candidate losses) is the load-bearing justification for the policy; degrading the filter also degrades the evidence base

---

## 4. Assumption Attack

The three load-bearing assumptions of the band system today:

### Assumption 1: Dispersion premium persists (weather market YES maker edge)
**Status: VIOLATED — do not re-enable band on this assumption**
- disp_ratio7=0.704 (calib_monitor S3-d15 DECISION-GRADE); threshold=1.10; n=110 (first decision-grade sample)
- 15th consecutive day below threshold; trend worsening (0.765 → 0.704 over measured period)
- Sub-segment breakdown: EU=0.628, Asia=0.714, d+1=0.635, d+2=0.594 — all below 1.0
- calib_monitor states explicitly: "Band market-making edge against temperature dispersion is NOT present in current market conditions"
- Today's partial disp_ratio reading (n=17, ratio=2.406 from state_log 22:08Z) is small-sample noise; 7d n=110 figure is authoritative and the decision-grade signal
- Additional structural problem: isotonic calibration plateau collapse — ALL p_raw∈[0.30, 0.95] → p_cal=0.3801 flat (calib_monitor S4); zero discriminative power across 65% of the probability range. Refit required before any band re-enable regardless of dispersion recovery.

### Assumption 2: Fills are not adversely selected (maker quotes fill at fair value)
**Status: VIOLATED — winner's curse confirmed**
- G3 WATCH_ITEM (gatekeeper): filled WR=17.3%, ROI=−75.8% vs sim +7.6%; gap −83.4pp
- maker_fills_recent.log corroborates: MAKER BUY fills at $0.02–$0.09 on near-zero weather tokens — being taker-hit by informed flow against stale resting quotes
- UNTRACKED orphan orders mean the adverse selection cannot be fully characterized
- This assumption fails independently of dispersion recovery — even if disp_ratio crossed 1.10, the maker quote structure would still face the same informed-taker adverseness unless G3 WATCH_ITEM gap closes first

### Assumption 3: Recycle velocity scales with held positions
**Status: VACUOUS — untestable**
- RECYCLE099/RECLAIM logic alive but idle; zero band positions to recycle
- Historical performance is pre-winner's-curse awareness regime
- Do not cite historical recycle returns as evidence for re-enable case; treat as unvalidated on current dispersion/capital regime

---

## 5. Market Intelligence — Platform Mechanics (17 mod 3 = 2)

**Fee structure interaction with candidate policy:**
Candidate fires at p≥0.995 → observed TAKER fill prices 0.96-0.99 in maker_fills_recent.log (post-waiver Jul 16 15:49-18:36Z: fills at 0.98, size 14; Jul 17 02:24Z BUY@0.98, size 14.5). At prices >0.95, Polymarket taker fees approach 0% (fee schedule: ~3.15% at 0.50 odds, ~0% at extremes — band_config.txt comment, CLOB research 2026-03-30). The candidate policy's core fee advantage is operating in the near-zero-cost zone; this aligns with the edge being real (margin after fees still positive at sub-1% taker cost).

**Maker orphan economics (weather band legacy):**
MAKER fills at $0.02–$0.09 have near-zero maker rebate at these extreme prices; full loss if market resolves YES. The Jul 16 SELL@$0.96 × 147.05sh ($141.17) and Jul 14 SELL@$0.98 × 367.66sh ($360.31) are weather-band YES position exits — exec_audit reports $932.48 cumulative net exit proceeds Jul 14-17, indicating large legacy positions fully or mostly settled this week. This is residual wind-down, not active strategy.

**Maker rebates:** Cumulative $3.559 (pnl_ledger). Verify pUSD receipt on Polymarket account (pnl_ledger pending item since Jul 15).

**Platform/fee changes since last known state:** None detected in mirror data. shadow_summary.json hot/ directories through 07-09; no fee-schedule or maker-rebate announcement entries visible. Delta vs state_log knowledge: zero. Fee structure unchanged (8 categories, updown BTC/ETH/SOL rates ~1.56% at 50% unchanged per 2026-03-30 research).

---

## 6. Three Experiments

### Experiment A: eth/sol/xrp per-asset shadow grade (STANDING ITEM — TODAY)
**Hypothesis:** ETH, SOL, XRP updown markets exhibit the same structural edge as BTC at the candidate policy filter (WR ≥ BE ~96.3% at p≥0.995, 5m-only)  
**Data:** 12,002 snaps per asset already recorded (state_log 22:08Z Jul 16); run shadow_grade with candidate policy filter per asset  
**Time:** ~1 hour  
**Cost:** Zero — shadow already recording  
**Success metric:** Per-asset point WR ≥ BE (~96.3%) with n≥20 at filter; CI-lo direction positive  
**Decision if YES:** Add asset(s) to candidate policy → ~3-4× fire cadence → n=100 shadow in ~1-2d → candidate gate accelerates; cite gatekeeper (candidate n=44, needs n≈84)  
**Decision if NO:** Confirm BTC-only policy; do not dilute P_MIN gate with unvalidated assets; note each asset may have different BE (different avg fill prices)

### Experiment B: Orphan CLOB order audit and cancel
**Hypothesis:** Stale MAKER BUY orders from the weather band era (pre-Jul-06) still rest on CLOB at $0.02–$0.09; cancelling them recovers capital and eliminates adverse fill exposure  
**Data:** exec_audit ALERT 1 HIGH — 12 MAKER fills UNTRACKED through Jul 15 restart; maker_resting_state={}; Jul 16 BUY@$0.09×86.6sh and BUY@$0.06×30.5sh filled post-restart (evidence stubs persisted through service restart)  
**Time:** Immediate (<1hr)  
**Cost:** Zero (cancel orders = free)  
**Success metric:** CLOB query returns zero open orders at price <$0.10; any recovered capital registers in wallet  
**Decision if YES (orphans found):** Cancel all; add startup order-audit to pre-flight checklist; close exec_audit ALERT 1  
**Decision if NO (clean):** Close ALERT 1; document that UNTRACKED fills reflect settled positions not resting stubs

### Experiment C: TRACKER_RESTART_BUG dry-run reproduction and fix
**Hypothesis:** The bug causing sniper fills to log as CAPITAL_CORRECTION rather than structured [SNIPER-FILL] rows can be reproduced in dry-run and fixed in ≤4h; after fix, candidate live n becomes a reliable counter  
**Data:** pnl_ledger: "TRACKER_RESTART_BUG: 14 of 20 fills invisible to analytics"; currently candidate n is estimated from capital-correction pairs (imprecise)  
**Time:** 2–4hr  
**Cost:** Low (code change, zero capital risk)  
**Success metric:** Dry-run test fire produces structured [SNIPER-FILL] line; live tape n becomes auditable  
**Decision if YES:** Deploy fix; candidate n counter becomes trustworthy for gate progression tracking  
**Decision if NO (deeper issue):** Document capital-correction arithmetic as the n-estimation workaround; defer fix; flag as gap in the gate progression evidence chain

---

## 7. Single Best Action

**Run the eth/sol/xrp per-asset shadow grade — TODAY (standing item from state_log 22:08Z Jul 16)**

*Cited reports: gatekeeper_report (candidate slice n=44, needs n≈84–100, ~4d ETA at BTC-only pace); pnl_ledger (turns/day=2.54× is the compounding ceiling on single-asset); state_log (grade queued: "first per-asset grade 07-17")*

**Rationale:** The compounding equation is `ROI/turn × turns/day × equity_deployed`. ROI/turn is positive on available evidence (+2.4%/fire estimated live, +4.72% shadow slice). Equity_deployed cannot grow until capital clears $89.16 (ruin_floor). The binding lever on capital recovery speed is **turns/day** — currently ~1/hr on BTC alone (state_log 22:08Z). If eth/sol/xrp grade positive at p≥0.995, fire cadence expands to 3-4×/hr. At 0.50 Kelly ≈ $15.88/clip, this raises daily compounding throughput from ~$0.60/hr to ~$2.40/hr. Capital recovery from $31.76 to $89.16 (~40 clean wins at current pace) compresses from ~4-5d clean-run to ~1-2d clean-run.

**This is already queued — it requires no new decision, only execution of the standing item.**

**Concrete first step:** `python3 shadow_grade.py --asset eth --policy p995_5m`, then repeat for sol and xrp. If any asset point WR ≥ BE with n≥20 at filter, stage as candidate expansion under the pre-registered gate.

**Operational prerequisite (blocking):** Disk cleanup must happen first. At 97% capacity with shadow loggers writing continuously and hot/2026-07-07 and hot/2026-07-08 directories present (estimated 5-10GB freeable), the service risks crashing before the grade can even run. Clean stale shadow directories, especially binance_trade (~370MB/day × 2 stale days = ~740MB minimum) and market_timeline (~1.36GB/stale day).

---

## PROPOSED ACTIONS (human review)

**[IMMEDIATE — operational]**
1. Disk cleanup: remove hot/2026-07-07 and hot/2026-07-08 shadow directories (especially binance_trade, market_timeline, ob_delta — estimated 5-10GB total). Target <80% disk utilization. Risk: zero (analysis-dead files for current strategy).

**[TODAY — standing item]**
2. eth/sol/xrp per-asset shadow grade. Pre-registered standing item from state_log Jul 16 22:08Z. Run shadow_grade per asset with candidate policy filter (p≥0.995, 5m-only). If positive, expand sniper to multi-asset breadth. Do NOT lower P_MIN to force positive grade.

**[IMMEDIATE — capital safety]**
3. CLOB orphan order audit: query open orders; cancel any at price <$0.10 with no current strategy justification. Close exec_audit ALERT 1. Recover idle capital, eliminate adverse MAKER exposure.

**[MEDIUM — analytics / gate tracking]**
4. Fix TRACKER_RESTART_BUG: sniper fills must produce structured [SNIPER-FILL] lines so candidate live n is accurately counted and per-trade diagnostics work.

**[WATCH — band re-enable conditions]**
5. disp_ratio7 day 15 inversion (0.704, n=110 DECISION-GRADE): band re-enable requires (a) disp_ratio ≥ 1.10 on n≥100 AND (b) capital ≥ $89.16 AND (c) isotonic refit (current model 41d old, plateau collapse). Today's partial disp_ratio reading (n=17, 2.406) is noise — do not act on it. Monitor 07-17 end-of-day figure.

**[PENDING — gatekeeper standing item]**
6. Classify MAKER SELL@0.96 token 1399483673820402 (Jul-16T21:39Z, 147.05sh). G3 co-fill cross-tab under Jul-05 clip-guard. Outstanding since Jul 11.

---

*Primary bottleneck: capital below ruin_floor ($31.76/$89.16) | Sole live revenue: sniper candidate n≈9-13 live, n=44 shadow | Best action: eth/sol/xrp per-asset grade (standing item)*
