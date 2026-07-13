# Research Audit — 2026-07-13T14:00Z

**Generated:** 2026-07-13T14:00Z  
**Data snapshot:** 2026-07-13T13:46:35Z (fresh, 2h20m old ✓)  
**System status:** active ✓ (uptime from 2026-07-11T22:06Z)  
**Bankroll:** $84.69 (< ruin_floor $89.16; −$2.71 vs gatekeeper-prior $87.40 at 09:00Z)  
**Specialist reports consumed:**
- exec_audit: 2026-07-12T10:54Z (~27h, within 36h ✓)
- calib_monitor: 2026-07-13T07:58Z (6h ✓)
- gatekeeper: 2026-07-13T09:00Z (5h ✓)
- pnl_ledger: 2026-07-13T23:37Z ABORT (2nd consecutive; data from 00:51Z, structurally guaranteed stale)

**⚠ research_status.md: 58 DAYS STALE (2026-05-16). Describes LDA strategy — does NOT reflect current band-first maker system. Do NOT treat as ground truth.**

---

## 1. Primary Bottleneck: Inverted Dispersion Premium

**Bottleneck ranking position: DISPERSION EDGE (rank 7 in normal operation; elevated to survival-level today)**

The band's core premise — that Polymarket weather ladders price MORE uncertainty than temperatures actually deliver — has been falsified for 15 consecutive confirmed days.

From calib_monitor (Section 3): 7d median dispersion ratio ≤0.80 (S3 alert day 11). Official gauge Jun 28–Jul 2: 0.663–0.976 (all < 1.0). Jul 3–10 EVOLVE-confirmed: 1/8 days ≥1.10, median-city ratio ≤0.80 on ALL 8 days. Model-proxy off-mode ratios Jul 11=0.153, Jul 12=0.615 (directional only, not official). Re-enable condition = ratio ≥1.10 for 5 consecutive confirmed days. **NOT MET on any window since Jun 28.**

This inversion is the root cause of the entire capital situation:

1. **Band correctly dark (day 7).** Zero YES/NO posts Jul 7–13. Shadow scanner finds 13 fire events/120 scans on Jul 12 — engine sees opportunities, but deploying into inverted dispersion generates structural losses. Correct response: stay dark. [exec_audit Section 3]
2. **Winner's curse layered on top.** Even before the inversion was confirmed, G3 WATCH_ITEM (n=75): filled ROI −75.8% vs sim +7.6%, gap −83.4pp. CI entirely negative [−75%, −34%]. Per-cell: NO d+1 0.60–0.85 filled WR 20% vs sim 92.9%. Adverse selection is structural across slices. [gatekeeper G3]
3. **Capital forced into variance alternatives.** Sprint_ladder (directional, high-variance) ran 0W/7L −$164.7 Jul 11–13. True equity fell to $39.45 at 09:20Z (below INVARIANTS #2 $40 floor, $50 ruin floor, $75 weekly floor). [state_log Jul-13 09:20Z]
4. **Current capital: $84.69 < ruin_floor $89.16.** Ladder disarmed at 09:20Z Jul 13. UPDOWN-SNIPER went live at 10:46Z on explicit owner floor waiver. This is the only active profit-seeking engine. [system_status commits; gatekeeper alert]
5. **PF = 0.08 on last 20 trades** (10× below 0.8 kill threshold). All 20 trades from 2026-07-06 single session, reflecting winner's curse on the now-disabled band. Not current engine behavior. [pnl_ledger Section 4]

**Why not equity deployed or turns/day?** The band IS finding 10–13 shadow fire opportunities per day. The constraint is not opportunity scarcity — it is that deploying into an inverted dispersion premium is a negative-EV trade. Lifting BAND_LIVE without fixing dispersion would deploy capital at a structural loss.

**Timeframe to unblock:** Requires VPS `band_resolution_join.py` to confirm ≥1.10 for 5 consecutive days. Cannot evaluate here. Not met on any recent day.

---

## 2. Existing-System Optimization

| Item | Observation | Expected delta | Confidence | Effort |
|---|---|---|---|---|
| Data-mirror push at 23:37Z | PnL ledger 2nd consecutive ABORT. Snapshot pushes at ~00:51Z; 23:37Z report is structurally guaranteed 22h46m stale. Full-day attribution permanently blind. [pnl_ledger] | Restores day-end PnL diagnostics; one-day lag at most | HIGH | Trivial — VPS cron at 22:00Z or 23:00Z |
| Settled-lane calibration | Brier/ECE/Rho locked Jun 28–Jul 2, day 11 stale. Brier 0.053 looks healthy but predates S3 inversion and winner's curse period — actively misleading if cited. [calib_monitor Section 1] | Restores honest calibration monitoring | HIGH | VPS pipeline: flow band_resolution_join.py output to data-mirror |
| UPDOWN-SNIPER day-stop rail | $5 clip, $15 max open, day-halt −$6 or 3 consecutive losses. With $84.69 capital and $2 reserve: 3 consecutive max-clip losses trigger halt before depleting capital. Rail correctly sized. [state_log Jul-13 10:46Z] | Limits daily loss to $6 (7.1% of current capital) | HIGH | Already implemented |
| Sprint_ladder disarm | Correctly disarmed 09:20Z Jul 13 on INVARIANTS #2 floor breach. 0W/7L −$164.7 streak stopped. [state_log Jul-13 09:20Z] | Stops active capital destruction | HIGH | Done |
| PAIR_FAV independence from BAND_LIVE | PAIR_FAV=True but 0 live fills because BAND_LIVE=False. Co-filled pairs (Σask≤0.92, pays 1.0 on completion) are structurally adverse-selection-immune — different from naked-leg band. [state_log Jul-11 22:15Z; exec_audit Section 6: $39.55 deployed Jul 12 in 2 transactions = 0.24 turns/day when live] | +0.24 turns/day, ~$20-40/cycle deployed | SPECULATIVE — n=9, CI not computable | Medium (VPS co-fill cross-tab first; then config flag) |

**Not actionable this session:** BAND_LIVE re-enable (dispersion not met, G3 active), BAND_NO re-enable (live WR 39.2% n=51 = REJECTED), standalone YES (BAND_YES_LIVE_MIN_DOUT=9 = never fires).

---

## 3. Gate Pipeline Review

| Gate | Status | n | Nearest lever | What accelerates (breadth only) |
|---|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS (∞) | 934 | Blocked by G3 + S3 | Nothing — sim CI is upper bound, band dark |
| G2b PAIR_FAV YES | COLLECTING | 9 | n≥40 needed (~8.3d at 11/day when live) | Re-enable PAIR_FAV; post more city-buckets |
| G2c PAIR_FAV NO | COLLECTING | 9 | Same | Same |
| G3 FILLED_VS_FIRED | WATCH_ITEM | 75 | CI [−75%, −34%] entirely negative. Band dark freezes new data. | Co-fill subset analysis (VPS) — may create structural exception |
| G5 THERMO_MAKER_NO | REJECTED | 125 | Done (~0% ROI, CI [−9, +2]) | N/A |
| G6 M1_BETA_LOCKOUT | REJECTED | 31 | Done (WR 74.2%, ROI −0.6%, CI [−20.6, +24.4]) | N/A |
| G7 SUM_POSTED | AMBIGUOUS (∞) | 382 | Same sim CI bias as G1 | Same block |

**Nearest to READY:** None. G2b/G2c (PAIR_FAV) is nominally closest but requires BAND_LIVE or structural flag separation AND the G3 co-fill exception to be demonstrated. Both conditions unverified.

**Sole credible acceleration path without degrading expectancy:** VPS cross-tab of G3 by co_fill_status. State_log (Jul-11 22:15Z) explicitly records: "Co-filled PAIR pays 1.0 on completion regardless — adverse selection lives in the naked leg only." If ≥7/9 resolved PAIR_FAV fills were co-fills with ROI>0, this creates a gatekeeper-endorsed structural exception. Breadth not stake.

---

## 4. Assumption Attack

### A1: Dispersion premium persists (implied σ > realized σ)
**Status: FALSIFIED. Day 11, 15 consecutive confirmed days below threshold.**

Official data Jun 28–Jul 2: ratios 0.663–0.976. Jul 3–10: 1/8 days ≥1.10, median-city ≤0.80 on all 8. Jul 11–12 model-proxy: 0.153 and 0.615 (not official). [calib_monitor Section 3]

This is not a bad-luck streak. Fifteen market-days without a single 5-day window at ratio ≥1.10 is structural. The market prices temperature uncertainty BELOW what temperatures actually deliver. The band sells overpriced dispersion — but dispersion is currently underpriced. Selling it at a discount to true risk is the loss mechanism.

**Potential reversal signal:** A weather-regime shift toward more settled temperatures (lower realized σ) OR market participants systematically widening their quotes (higher implied σ). Neither visible in today's data. PRE_PEAK sigma from proxy (0.927–0.998°C, Jul 11–12) is stable, not rising.

### A2: Fills are not adversely selected (resting bids hit at fair value)
**Status: STRUCTURALLY THREATENED. n=75, CI [−75%, −34%] entirely negative.**

G3 WATCH_ITEM detail: per-cell decomposition shows same sign across slices (NO d+1 0.60–0.85: filled WR 20% n=15 vs sim 92.9% n=14). Not a single-cell artifact. [gatekeeper G3]

Mechanism: resting bids get hit when the market moves against the quote. Informed flow sweeps maker offers precisely when the offer has become mispriced. This matches the pattern that killed the prior Maker MVP.

**The one exception (from state_log Jul-11 22:15Z):** Co-filled PAIR legs, where Σask≤0.92 forces both legs to fill simultaneously — once co-filled, the payout is locked at 1.0 regardless of individual leg outcome. Adverse selection cannot occur post-co-fill. This exception is untested at n≥40.

### A3: Recycle velocity scales (RECYCLE099 compounds turns/day)
**Status: UNTESTABLE — zero data since Jul 6.**

Zero exit099_live.jsonl entries Jul 7–13. [exec_audit Section 3] Band dark = no positions = no recycle events. Cannot support or threaten this assumption. It remains theoretically sound but empirically unverified.

**Net verdict:** Two of three load-bearing assumptions broken (A1 falsified, A2 structurally threatened), one untestable. Band must remain dark. The BAND_LIVE=False decision is correct on all available evidence.

---

## 5. Market Intelligence — Market Census (13 mod 3 = 1)

**Rotation:** New weather cities/products on Gamma; depth changes in our 51.

**Signal from shadow scan data (no direct Gamma API access available in this environment):**

Shadow fire rate trend:
- Jul 7 (dark day 1): 16 fire / 175 shadow scans = **9.1%**
- Jul 12 (dark day 6): 13 fire / 120 shadow scans = **10.8%**

Opportunity supply is stable to marginally improving over the 6-day dark window. No liquidity collapse or city-set shrinkage detectable from shadow scanner behavior. d+2 dominates in both days (87/120 Jul 12 records), consistent with BAND_MD_HORIZON=2 and BAND_NO_MIN_DOUT=1 configuration. No structural horizon shift.

**Limitations:** Authoritative city/product census requires direct Gamma API call. BAND_CITY_ALLOW in band_config.txt is truncated in available data (ends at line 607 before city list closes). No evidence of new city additions or removals in available logs. BAND_TAILNO_VALIDATED=False — tail-NO 0.85–0.95 market remains structurally unvalidated on Klaus fills (BAND_PHASE2_CAPITAL=$600 threshold not reached at $84.69).

**Delta vs last state_log:** No material change detected. Market census is inconclusive without direct Gamma API; shadow fire rate stability is the only confirming signal.

---

## 6. Three Experiments

### E1 — UPDOWN-SNIPER Side-Mapping Validation (24–72h)
**Hypothesis:** Near-certainty buys (p_model≥0.99, ask∈[0.90,0.97(15m)/0.99(5m)], |move|≥6bps, t_left∈[5s,120s(15m)/30s(5m)]) deliver WR≥0.90 on Klaus's own fills, consistent with two-era tape analysis (WR 0.95–1.00 in certainty cells, n=923k).  
**Data:** logs/shadow/updown_sniper/*.jsonl + CLOB fill resolutions. Need 50 resolved fires.  
**Time:** 24–72h (fire rate unknown; p≥0.99 is selective; ~380 windows/day but most fail the gate).  
**Cost:** ≤$6 (day-stop fires first).  
**Success metric:** 50 resolved fires, WR≥0.90, net ROI>0 after fee=0.07·p·(1−p).  
**Decision-if-yes:** Continue live at $5 clip; plan scale to $10 at n=100.  
**Decision-if-no:** Side-mapping may be inverted OR winner's curse applies even in certainty cells. Halt via logs/UPDOWN_STOP; audit outcomeIndex join from scratch.

### E2 — PAIR_FAV Co-Fill vs Naked-Leg Adverse Selection (<1h, VPS)
**Hypothesis:** G3's −75.8% filled ROI applies exclusively to naked resting bids. Co-filled PAIR legs (both legs fill simultaneously, Σask≤0.92, resolution pays 1.0 regardless of leg outcome) are adverse-selection-immune by construction.  
**Data:** VPS cross-tab: n=9 resolved PAIR_FAV fills split by (co_filled: True/False). Specifically: fraction that completed as co-fills vs left a naked leg.  
**Time:** <1h (data exists on VPS in maker_fills_recent.log + pair_fav shadow).  
**Cost:** $0 (analysis only).  
**Success metric:** ≥7/9 resolved PAIR_FAV fills were co-filled; co-fill subset ROI>0.  
**Decision-if-yes:** PAIR_FAV has structural adverse-selection immunity. Argue for flag-level separation from BAND_LIVE. Re-enable PAIR_FAV to accumulate G2b/G2c toward n≥40. This is the only credible path back to maker deployment at scale.  
**Decision-if-no:** PAIR_FAV leg fill pattern mirrors naked-band adverse selection. Keep dark alongside BAND_LIVE.

### E3 — Data-Mirror 22:00Z Push Cron (<10 min, VPS)
**Hypothesis:** Adding a daily 22:00Z UTC push to data-mirror ends the structural ABORT on the PnL ledger report (currently guaranteed because the only push is ~00:51Z, yielding 22h46m stale by 23:37Z report time).  
**Data:** None — pure implementation.  
**Time:** <10 min (crontab -e on VPS).  
**Cost:** Negligible (one extra git push/day).  
**Success metric:** Jul 14 PnL ledger (23:37Z) generates non-ABORT result with day-end capital and full attribution.  
**Decision-if-yes:** Permanent operational improvement. Deploy.  
**Decision-if-no:** If ABORT persists after fix, bankroll.json may not save at midnight as assumed. Deeper investigation needed.

---

## 7. Single Best Action

**Validate UPDOWN-SNIPER side-mapping on first live settlement (within next 24h).**

**Justification from specialist reports:**

The gatekeeper (09:00Z) flags bankroll $87.40 < ruin_floor $89.16 as CRITICAL. Current snapshot shows $84.69 — the ruin floor breach has deepened by $2.71 in 5h (likely UPDOWN-SNIPER taker fees or fires since 10:46Z arm). The sprint_ladder (the primary bleed source, 0W/7L −$164.7) is correctly disarmed. The UPDOWN-SNIPER is now the sole profit-seeking engine, live since 10:46Z on an explicit owner floor waiver.

State_log (10:46Z) notes: *"side-mapping verifies on first live settles — verified instead by construction (Gamma outcomes[i]≡clobTokenIds[i], tape outcomeIndex join WR 1.0 in target cells)."* Construction-level verification is appropriate pre-live. It is NOT equivalent to an observed live settlement. If outcomeIndex mapping is inverted, the system will buy the wrong token in certainty cells at 0.90–0.97 and receive 0.0 on resolution — a systematic 90–97% loss per fire.

**Concrete first step:** On VPS, watch logs/shadow/updown_sniper/ for the first resolved fire. Confirm: (a) token bought = decided side (UP→YES token, DOWN→NO token), (b) resolution payout = $1.00/share. If both confirmed: side-mapping validated, continue. If payout = $0: halt via `touch logs/UPDOWN_STOP`, pause UPDOWN_LIVE=0, audit Gamma outcomeIndex vs CLOB token assignment.

This costs $0 additional, takes minutes on first settlement, and is the highest-value-of-information check available given the capital is at ruin-floor levels with a newly armed system that bypassed its n≥100 gate.

---

## PROPOSED ACTIONS (human review)

**DO NOT implement without explicit owner instruction. Research-only output.**

1. **[CRITICAL — OPERATIONAL] VPS: add 22:00Z data-mirror push cron.** Two consecutive ABORT days on PnL ledger = permanently blind day-end diagnostics. Fix: `crontab -e` on VPS, add `0 22 * * * cd /root/Klaus && git add -A data/ && git commit -m "data-mirror 22:00Z push" --allow-empty && git push -f origin HEAD:data-mirror`. [E3]

2. **[CRITICAL — RISK] Monitor UPDOWN-SNIPER first settlement within 24h.** Confirm side-mapping by construction holds in live trade (payout = $1.00/share on decided side). Watch day-stop rail (−$6 or 3 consecutive losses). If payout = $0: halt immediately (`touch logs/UPDOWN_STOP`). [E1, Section 7]

3. **[IMPORTANT] VPS: cross-tab PAIR_FAV n=9 by co_fill status.** Only credible path back to maker deployment at scale without resolving the G3 winner's curse block. Low effort, high VoI. [E2, Section 3]

4. **[INFORMATIONAL] Calibration pipeline staleness (day 11).** VPS `band_resolution_join.py` has run through at least Jul 10 but output does not flow to data-mirror. Brier 0.053 is a dangerously misleading signal — it predates S3 inversion and winner's curse. Fix: pipe scoring output to a committed file in data/. [calib_monitor Section 1]

5. **[INFORMATIONAL] Update research_status.md.** File is 58 days stale (still describes LDA strategy). Any scheduled agent reading it will operate on wrong mandates. Update to reflect current band-first maker system, gate ledger, and UPDOWN-SNIPER addition.

6. **[HARD NO] Do NOT re-enable BAND_LIVE.** S3 day 11, ratio ≤0.80, G3 CI entirely negative, re-enable condition NOT MET on any confirmed day since Jun 28. [calib_monitor Section 3, gatekeeper Structural Blockers]

7. **[HARD NO] Do NOT re-enable BAND_NO.** Live n=51 WR 39.2% = REJECTED. [gatekeeper G2a]

---

*Report generated by Klaus Research Agent. REPORT-ONLY: no code or config changes made.*  
*Data: snapshot 2026-07-13T13:46:35Z. Specialist reports: exec_audit (Jul-12 10:54Z, 27h), calib_monitor (Jul-13 07:58Z, 6h), gatekeeper (Jul-13 09:00Z, 5h), pnl_ledger (Jul-13 23:37Z ABORT, structurally stale). research_status.md treated as stale (2026-05-16, 58d).*
