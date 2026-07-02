# Research Audit — 2026-07-02T11:30Z

**Analyst:** Research agent (claude/find-lag-parameter-rFQ0N)
**Snapshot:** 2026-07-02T11:23:06Z — FRESH (7 min) ✓
**System:** `klaus systemd: active` ✓
**Capital:** $76.31 (bankroll.json) — ⚠️ $1.31 above $75 weekly floor (cash only)
**Equity estimate:** ~$185 (cash + SELL_EXIT pending + open book)

**Specialist reports consumed:**
- exec_audit_report.md — 2026-07-01T07:14Z (25h old — within 36h window ✓)
- calib_monitor_report.md — 2026-07-01T08:05Z (26h old ✓)
- gatekeeper_report.md — 2026-07-01T12:30Z (23h old ✓)
- pnl_ledger_report.md — 2026-07-01T23:37Z (12h old ✓)

**Data gap note:** git fetch failed (remote timeout); all data read via GitHub MCP from `data-mirror` HEAD (eea69c19). State_log was oversized to read directly; tail extracted via shadow_summary. maker_fills_recent.log Jul 2 section extracted via Python parse.

---

## Pre-flight

| Check | Value | Status |
|---|---|---|
| Snapshot age | 7 min (2026-07-02T11:23:06Z) | PASS ✓ |
| system_status.txt | `klaus systemd: active` | PASS ✓ |
| Exec audit age | 25h (within 36h) | PASS ✓ |
| Calib monitor age | 26h (within 36h) | PASS ✓ |
| Gatekeeper age | 23h (within 36h) | PASS ✓ |
| PnL ledger age | 12h | PASS ✓ |

**Proceed: YES.**

---

## 1 — Primary Bottleneck: Dispersion Collapse → BAND_NO Revenue Outage

**Bottleneck ranked: dispersion edge collapse, which triggered BAND_NO_ENABLED=False this morning — shutting off ~80% of the system's historical fill velocity.**

The EVOLVE system committed `0835b2492` at bot startup today (06:14 UTC per system_status.txt) with the message: *"risk(BAND): halt favorite-NO overlay — charter 7d-PF rail breached (BAND_NO_ENABLED=False)"*. band_config.txt confirms: `BAND_NO_ENABLED = False # 2026-07-02 EVOLVE rail-halt: 7d realized band-NO n=51 WR 39.2%`.

Calib_monitor (08:05 UTC Jul 1) provided the mechanistic explanation one session earlier:

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Dispersion ratio (all cities) | **0.470** | 1.10 | ESCALATED ⚠️ |
| Dispersion ratio d+2 | 0.550 | 1.10 | ESCALATED ⚠️ |
| Fires resolving outside ladder | **52% (12/23)** | — | STRUCTURAL |
| Beijing ratio | 0.278 | — | WORST |
| Chengdu ratio | 0.310 | — | BAD |
| Munich ratio | **0.939** | — | Near break-even |
| Wuhan ratio | **0.969** | — | Near break-even |

**Consequence today (Jul 2 STRUCT-BAND-Q queue lines, 00:00–11:23 UTC):**
All 130 sampled Jul 2 BAND-Q cycles show `no_cands=0`, `posted=0`. The system is generating zero new maker positions. Only residual SELL_EXIT clearing (+$9.17 from 4 RECYCLE099 exits today) and prior NO inventory draining are producing cash flow. Cash recovered from $72 to $76 during the session — consistent with SELL_EXIT fills arriving.

**Why "dispersion" outranks prior bottleneck ("turns/day / city breadth"):**
Yesterday's audit ranked city breadth as the primary bottleneck. That remains the medium-term constraint. But today a new acute layer has appeared: the revenue engine itself is OFF. There is no city breadth to optimize when `no_cands=0`. The bottleneck hierarchy is: (1) dispersion fix → re-enable NO band, (2) then city expansion for turns/day.

**RECYCLE inventory depletion timeline:** With BAND_NO_ENABLED=False, no new NO positions are being created. The SELL_EXIT pipeline (63 shares at 0.99 as of yesterday + today's 4 recycles) will fully exhaust within 2–4 days. Once cleared, RECYCLE099 cash flow drops to ~$0/day. The system will then be running on PAIR_FAV alone — which is currently producing 0 posted/cycle.

---

## 2 — Existing-System Optimization

### 2a. Munich+Wuhan Selective NO Reinstatement
**Source:** calib_monitor S3 per-city breakdown; band_config.txt BAND_CITY_ALLOW.

The dispersion collapse is city-specific. Munich (0.939) and Wuhan (0.969) are near break-even — their implied_std tracks realized temperature error. Beijing (0.278) and Chengdu (0.310) are the sources of both the dispersion collapse AND the 3 NO losses that drove the EVOLVE rail halt ($15.29 in losses per pnl_ledger S1).

**Proposal:** Reinstate `BAND_NO_ENABLED=True` with `BAND_CITY_ALLOW = {"munich", "wuhan"}` only (removing Beijing, Chengdu, London from the NO path until the pricer cold-bias is corrected). London has n=1 dispersion data point (ratio 0.408) — too thin to categorize.

**Expected delta:** ~2 cities × 2–3 NO fills/day × $5 stake = **+$20–30/day fill velocity restored.** At 35% RECYCLE ROI that's ~$7–10/day gross revenue vs current $0.
**Confidence:** Medium-high. Munich/Wuhan dispersion ratios are based on n=5 city-dates each — enough for directional confidence, not n≥40 CI threshold.
**Effort:** LOW — 2-line config change.
**Prerequisite:** VPS resolution join (see §2b) — per-city NO ROI on actual fills, not just dispersion proxy.

### 2b. VPS Resolution Join — CRITICAL PATH, FOURTH CONSECUTIVE AUDIT, EMERGENCY
**Source:** gatekeeper advisory #1 (days overdue); exec_audit S4; calib_monitor S3.

This has appeared in audits Jun 29, Jun 30, Jul 1, and now Jul 2 as P0 action. Still unactioned.

Running `band_resolution_join.py` on VPS:
- Converts BAND_YES (n=6,081), BAND_NO+PAIR_FAV (n=262), SUM_POSTED (n=3,019) from BLOCKED → CI-computable simultaneously
- Provides FILLED_VS_FIRED n=100 winner's-curse verdict (ETA today per gatekeeper; Jun 28 fills age out Jul 5 — **3 days remaining**)
- Produces per-city NO ROI rows that answer whether Munich/Wuhan NO reinstatement is safe

**Expected delta:** 4 simultaneous gate CI verdicts; city reinstatement decision becomes data-driven.
**Confidence:** HIGH. VPS has API access; join logic exists.
**Effort:** LOW (one command on VPS).
**Urgency: MAXIMUM — fourth consecutive audit naming this. FILLED_VS_FIRED n=100 crosses today.**

### 2c. BAND_NO_CASH_RESERVE Drag with NO Disabled
**Source:** Jul 2 STRUCT-BAND-Q log lines; band_config.txt.

`BAND_NO_CASH_RESERVE = 0.30` allocates $76 × 0.30 = $22.8 of capital as a NO reserve. With `BAND_NO_ENABLED=False`, this reserve serves no purpose — there are no NO posts to fund. Jul 2 early cycles show `yes_resv_skip=15–25/cycle`, which collapses to 0 as cap grows. Setting `BAND_NO_CASH_RESERVE=0.0` temporarily (while NO is off) would make the full capital available for PAIR_FAV candidates.

**Expected delta:** PAIR_FAV candidates that currently fail the cash pre-skip gate would reach price evaluation. Requires code verification that yes_resv_skip IS the reserve counter and not a d+2-filter label.
**Confidence:** Medium.
**Effort:** LOW (1-line change, easily reverted when NO re-enabled).

### 2d. M1_BETA_LOCKOUT REVERT (Day 5 of proposal, Day 20 of stall)
**Source:** gatekeeper_report.md (Proposed Actions, carry-over).

Standing rule from Jun 13: stalled >14 days → REVERT `METAR_LOCKOUT_TEMP_FLOOR` to 0.5°C. metar_lockout.jsonl has n=11,564 rows today (2026-07-02T11:23 mtime), meaning the engine IS logging candidates — but the gate's placed-order counter remains at n=31. The logger rows likely represent evaluated candidates that fail the current temp floor. Reverting to 0.5°C would let lower-delta candidates through to placement.

**Expected delta:** Resumes M1 gate accumulation (gate not live; no capital at risk during accumulation).
**Confidence:** HIGH (standing rule triggered).
**Effort:** trivial.

### 2e. Weekly Floor Safety (cash only: $1.31 cushion)
**Source:** pnl_ledger S4 kill-switch proximity.

Cash capital $76.31 is $1.31 above the $75 weekly halt floor. **This is cash-only.** Equity estimate including SELL_EXIT pending (~$62) is ~$139 — well clear. The floor proximity is not an immediate operational risk, but **no new positions should be posted that would deplete cash below $75 before SELL_EXIT orders clear.** With BAND_NO_ENABLED=False and PAIR_FAV not firing, this condition is satisfied by design. Once SELL_EXIT clears, cash restores to ~$139 and the floor is no longer a constraint.

| Optimization | Impact | Confidence | Effort | Priority |
|---|---|---|---|---|
| Munich+Wuhan NO reinstatement | +$20–30/day revenue | Med-high (post-join) | LOW | 1 (after join) |
| VPS resolution join | 4 gate CIs + per-city verdict | HIGH | LOW | 0 — EMERGENCY |
| NO_CASH_RESERVE=0.0 while NO off | Frees PAIR_FAV cash | Medium | trivial | 2 |
| M1_BETA REVERT | Unblocks 20d stall | HIGH (rule-based) | trivial | 3 |
| Weekly floor (no new depleting posts) | Risk management | HIGH | zero | auto-satisfied |

---

## 3 — Gate Pipeline Review

**Source:** gatekeeper_report.md 2026-07-01T12:30Z + today's observed data.

| Gate | n (Jul 1) | Status | Blocker | Acceleration path |
|---|---|---|---|---|
| FILLED_VS_FIRED | 86 (+12) | COLLECTING ⚠️ **hits n=100 TODAY** | VPS join needed | Run band_resolution_join.py IMMEDIATELY |
| BAND_NO + PAIR_FAV | 262 (+9) | CI BLOCKED | Gamma 403 | VPS join (same command) |
| BAND_YES | 6,081 (+37) | CI BLOCKED | Gamma 403 | VPS join (same command) |
| SUM_POSTED 0.70–0.85 | 3,019 (+18) | CI BLOCKED | Gamma 403 | VPS join (same command) |
| M1_BETA_LOCKOUT | 31 (+0) | AMBIGUOUS, day 20 stall | METAR floor too high | Revert METAR_LOCKOUT_TEMP_FLOOR=0.5 |
| THERMO_MAKER_NO | 3 (+0) | FROZEN (engine paused) | Capital <$600 (BAND_PHASE2) | Awaits capital growth to $600 |
| BASKET_EXIT | VOID | Permanently retired | — | Do not revisit |

**Nearest READY:** FILLED_VS_FIRED at n=86 + today's fills ≈ n≥98. VPS join needed **before end of day** to compute CI before the 7-day window drops Jun 28 fills (Jul 5 deadline).

**Acceleration WITHOUT degrading expectancy:**
- VPS join is the only action that moves 4 gates simultaneously without touching any expectancy-affecting parameter.
- City breadth expansion (after join validates Munich/Wuhan): adds fire candidates, increasing BAND_NO and SUM_POSTED n accumulation rate. Not appropriate until per-city verdict from join.
- M1 REVERT: pure accumulation action, no capital at risk.

---

## 4 — Assumption Attack

### Assumption 1: Dispersion Premium Persists (band edge)
**Premise:** Market underprices tail probability on temperature; NO on off-mode buckets is cheap relative to realized resolution probability.

**Status: THREATENED FOR BEIJING/CHENGDU; NEAR-INTACT FOR MUNICH/WUHAN.**

Calib_monitor shows ratio 0.470 overall (Beijing 0.278, Chengdu 0.310, Munich 0.939, Wuhan 0.969). This is now **confirmed** by EVOLVE's WR measurement: n=51 band-NO positions, 7d WR 39.2% — below the 40% minimum floor. Three specific NO resolutions in pnl_ledger closed at $0.00 (Beijing Jun 30, Chengdu Jun 29, Munich Jun 30 — note Munich is near break-even in dispersion but appeared in the loss set, possibly a single bad-luck event vs structural).

The key distinction for preserving any NO-band thesis:

| City | Dispersion ratio | Mechanism verdict | 7d data verdict |
|---|---|---|---|
| Beijing | 0.278 | Pricer cold by 3–4°C | In the loss set |
| Chengdu | 0.310 | Pricer cold by 3–6°C | In the loss set |
| Munich | 0.939 | Pricer tracks reality | In loss set (1 event; small n) |
| Wuhan | 0.969 | Pricer tracks reality | No loss event in pnl data |
| London | 0.408 (n=1) | Insufficient data | Not in loss set |

RECYCLE099 n=20 exits all positive (35% ROI) support the premise that NO positions converge correctly on average. But this data is from the aggregate 5-city pool — it cannot be disaggregated to city without the VPS join. If Beijing/Chengdu drive most of the wins (via "even wrong-mode NO wins when it's far from the mode"), the aggregate looks healthy while the loss positions accumulate separately.

**Decision rule:** Do NOT re-enable NO for Beijing/Chengdu until per-city ROI from VPS join clears zero. Munich/Wuhan selective reinstatement is low-risk given dispersion ratios near 1.0.

### Assumption 2: Fills Are Not Adversely Selected
**Premise:** NO bids at 0.52–0.85 attract uninformed flow; fills not concentrated on pre-resolve moves.

**Status: SUPPORTED DIRECTIONALLY, FORMALLY UNVERIFIABLE until n=100.**

RECYCLE099 n=20 exits all positive (avg entry 0.733, exit 0.99, 3-day average ROI 35%). No adverse convergence pattern (fills converge to 1.0, not 0.0). The 2h reclaim timer prevents stale-order adverse fills. Today's 4 RECYCLE exits (+$9.17) continue the pattern.

Threat: exec_audit flagged untracked wallet fills of 703.56 shares @ 0.98 on the same wallet (Jul 1 11:30 UTC) — this actor operates in the near-par zone but does NOT target our entry range (0.52–0.85). The PAIR_FAV YES fill at 0.38 (vs YES_MIN=0.45 gate) is a one-instance gate anomaly that needs code-side resolution but doesn't invalidate the broader fill quality.

**Formal verdict pending VPS join (FILLED_VS_FIRED n~100 window closes today).**

### Assumption 3: RECYCLE Velocity Scales
**Premise:** SELL_EXIT queue converts existing NO inventory to cash at 35% ROI, funding new posts continuously.

**Status: SUPPORTED NOW, BUT FINITE WINDOW.**

Today's 4 RECYCLE exits (+$9.17 gross) confirm the mechanism is active. Shadow exit099_live.jsonl shows:
- 05:55 UTC: 5 sh @ 0.71 → 0.99, +$2.24
- 08:55 UTC: 7 sh @ 0.74 → 0.99, +$1.75
- 08:55 UTC: 6 sh @ 0.82 → 0.99, +$1.11
- 11:39 UTC: 9 sh @ 0.55 → 0.999, +$4.04

**Critical constraint:** RECYCLE inventory is depleting. With `BAND_NO_ENABLED=False` since today's start, no new NO positions are being built. The SELL_EXIT pipeline (63 shares yesterday + declining with exits) will exhaust in approximately **2–4 days** at the current drain rate. After that, RECYCLE099 revenue drops to $0 and the only active revenue path is PAIR_FAV — which is currently posting 0/cycle.

**Implication:** The Munich+Wuhan NO reinstatement timeline is not "nice to have" — it is the rebuild of the inventory that fuels all downstream revenue. Without it, the system goes idle within a week.

---

## 5 — Market Intelligence (Day 2 % 3 = 2 → Platform Mechanics)

**Source:** band_config.txt comments, shadow_summary.json maker_flow mtime, pnl_ledger S3 rebate table.

**Fee schedule (no changes detected):**
band_config.txt last fee-related comment: `"Fee reform 2026-03-30: 8 new categories added; updown BTC/ETH/SOL rates unchanged (~1.56% at 50%)"`. No new fee-change comments appear in today's band_config.txt. Weather market maker fee formula in pnl_ledger confirms `feeRate=0.05, maker share=25%` — unchanged. maker_flow.jsonl cadence is continuous (Jun 22–Jul 2, 235K–527K rows/day), no discontinuity suggesting fee-mechanics change.

**Maker rebate status — pUSD accrual overdue:**
Cumulative estimated rebate from pnl_ledger S3: $2.379 (above the $1.00 minimum payout threshold since Jun 29, flagged by two prior ledger reports). No confirmed pUSD receipt in funder wallet visible in available data. **Delta vs state_log: this has been flagged for 3 consecutive sessions without closure.** User should verify pUSD in Polygon funder wallet immediately; if absent, raise with Polymarket #support citing cumulative rebate calculation.

**Liquidity rewards / VIP tier:**
No announcement visible in any log or config comment. maker_shadow.jsonl continues at steady cadence (n=40,931 Jul 2 partial day vs ~100,000–117,000 full day prior days) — no discontinuity suggesting a liquidity rewards regime change.

**metar_lockout anomaly (new, platform-adjacent):**
metar_lockout.jsonl has n=11,564 rows through 11:23 UTC today — roughly 50% of a full-day rate. The engine IS evaluating METAR lockout candidates in volume. But the M1_BETA gate's placed-order counter is frozen at n=31 (day 20). This means the METAR lockout engine generates candidates but they fail the downstream CLOB placement gate (most likely: METAR_LOCKOUT_TEMP_FLOOR too high, filtering all real-CLOB opportunities). The engine is healthy; the gate parameter is the blocker.

**No competitor or product-census changes detected.** badatmath_watch.jsonl is current (n=4,423 rows through 11:22 Jul 2), but fill_join records require VPS-side analysis to compute fill deltas.

---

## 6 — Experiments

### Experiment 1: Munich+Wuhan NO Band Reinstatement (Selective Re-enable)
**Hypothesis:** Reinstating `BAND_NO_ENABLED=True` with `BAND_CITY_ALLOW = {"munich", "wuhan"}` will produce ≥50% WR and >0% net ROI over 7d (n≥20 NO fills), restoring ~$7–10/day gross revenue without the Beijing/Chengdu model risk.

**Data needed:** VPS band_resolution_join.py per-city ROI breakdown (Munich+Wuhan historical NO fills from n=262 BAND_NO pool). This is the prerequisite — run join first.

**Time:** VPS join today + 7 days live validation.

**Cost:** ~$5/fill × estimated 4–6 fills/day = $20–30/day capital deployed (within current $76 bankroll risk tolerance given $62 SELL_EXIT incoming).

**Success metric:** 7d WR ≥ 55%, net ROI (after losses) > 0%, no new dispersion alert fires for Munich/Wuhan, RECYCLE099 continues generating positive exits.

**Decision if YES:** Expand BAND_CITY_ALLOW to 6th city (London or Paris; shadow first per prior protocol). EVOLVE rail lifts automatically when 7d PF clears threshold.

**Decision if NO (per-city data shows Munich or Wuhan net-negative):** Maintain full BAND_NO halt. Investigate whether the pricer cold-bias extends to all European cities. Do not expand until pricer is corrected.

---

### Experiment 2: PAIR_FAV Cash Drain Diagnosis
**Hypothesis:** `BAND_NO_CASH_RESERVE=0.30` is starving PAIR_FAV candidates even with NO disabled — setting `BAND_NO_CASH_RESERVE=0.0` while NO is off will convert pair_cands=1–3/cycle from 0-posted to ≥0.5 fills/day.

**Data:** Jul 2 STRUCT-BAND-Q lines show `pair_cands=1–3` but `posted=0` throughout. `cash_preskip=0` in most cycles — suggesting cash is NOT the immediate filter, but the reserve may be reducing the deployable pool for pair evaluation in a non-visible way.

**Time:** Immediate — within 1 cycle (5 minutes) of flag change, a PAIR_FAV candidate would either post or continue failing at the price gate.

**Cost:** $0 if pair still fails price gate; $3–5 × estimated 1–2 fills if it succeeds.

**Success metric:** At least 1 PAIR_FAV post in first 3 cycles after flag change (vs current 0/cycle sustained pattern).

**Decision if YES (pairs fire):** Keep `BAND_NO_CASH_RESERVE=0.0` while NO is disabled; revert to 0.30 when Munich+Wuhan NO re-enabled. Confirms reserve was blocking PAIR_FAV.

**Decision if NO (pairs still 0/cycle):** Price gate is the bottleneck. Check d+0 YES ask levels on the 5 cities at 11–14 UTC (the current posting window). If YES asks are below BAND_PAIR_FAV_YES_MIN=0.45 universally, lower the gate by 0.05 in shadow and track resulting candidates.

---

### Experiment 3: Temperature Pricer Cold-Bias Correction (Beijing/Chengdu)
**Hypothesis:** Adding a seasonal correction offset of +3°C to the Kalman/STWA mode for Beijing and Chengdu during June–August (summer heat wave season) would shift the ladder to the correct temperature range, restoring dispersion ratio >1.0 and enabling those cities to re-enter the NO allowlist.

**Pre-condition:** Must first confirm from VPS resolution join that Beijing/Chengdu NO fills were indeed bleed (not just 3 unlucky events). If per-city ROI is positive despite the dispersion alert, the correction is not needed.

**Time:** 7 days shadow validation with corrected mode vs actual resolution (5 cities × 7 days = 35 data points, similar to current n=23 in calib_monitor).

**Cost:** $0 during shadow phase. If live-tested: ~$5/fill × 4–6/day = $20–30/day.

**Success metric:** Shadow dispersion ratio for Beijing/Chengdu shifts from 0.28–0.31 to >0.80 with the +3°C correction applied. Out-of-ladder rate drops from 52% to <20%.

**Decision if YES:** Re-enable Beijing/Chengdu with the corrected pricer. Full 5-city NO band at lower risk. Monthly seasonal offset update becomes part of pricer maintenance.

**Decision if NO (offset doesn't fix ladder coverage):** The pricer architecture itself is the issue (not a simple offset). Deeper investigation into Kalman observation weights / climatology data source for these cities required.

---

## 7 — Single Best Action

**Run `band_resolution_join.py` on VPS before end of day.**

**Sources cited:**
- gatekeeper_report.md (S3 Advisory #1): *"Exec Auditor MUST schedule VPS-side resolution join before Jul 3 — Gamma API 403 blocks cloud-side join. Winner's-curse detection blind without it."*
- calib_monitor_report.md (S3 ESCALATED): *"ACTION REQUIRED: Review band temperature pricer for Beijing/Chengdu; investigate heat-wave climatology offset. Munich/Wuhan performing adequately."* — per-city ROI is the ground truth that resolves this.
- pnl_ledger_report.md (S2): FILLED_VS_FIRED ETA n=100 "≈ Jul 2 late."
- This is the **fourth consecutive audit** naming this as the single best action. The deadline (Jun 28 fills age out Jul 5) is now 3 days away.

**Why this, not Munich+Wuhan reinstatement directly:**
The reinstatement decision requires per-city ROI data. Running the join *is* how you get that data. It also simultaneously delivers CI verdicts for BAND_YES, BAND_NO, and SUM_POSTED — converting 4 BLOCKED gates to COMPUTING in a single execution. P(success) ≈ 0.95 (VPS has API access, join logic exists, data is on-disk). Compounding impact is maximum: it either confirms Munich+Wuhan reinstatement (~$7–10/day revenue recovered) or identifies that the entire NO book is bleed (prevents further losses). Either way the compounding decision is made from data.

**Concrete first step:**
```bash
# On VPS:
cd /root/Klaus
python3 analysis/weather/band_resolution_join.py 2>&1 | tee /tmp/band_join_20260702.log
# Review per-city output; push result file to data-mirror or commit to dev branch
```

After the join output is available:
1. If Munich+Wuhan per-city ROI > 0%: implement `BAND_NO_ENABLED=True, BAND_CITY_ALLOW={"munich","wuhan"}` as the immediate follow-on.
2. If Beijing/Chengdu ROI < 0%: confirm they stay out of the allowlist until pricer is corrected (Experiment 3).
3. CI on BAND_YES/BAND_NO/SUM_POSTED: if CI clears zero → gate READY; if straddles → continue collecting.

---

## PROPOSED ACTIONS (human review)

*Research agent is REPORT ONLY. State-altering actions require human implementation.*

**P0 — EMERGENCY (end of day today, Jul 2):**
- [ ] **Run `band_resolution_join.py` on VPS.** FILLED_VS_FIRED hits n≈100 today; Jun 28 fills age out Jul 5. Gamma 403 blocks cloud CI. Fourth consecutive audit, same action, same urgency. *(Gatekeeper advisory #1; pnl_ledger S2; calib S3)*

**P1 — After VPS join runs:**
- [ ] **Munich+Wuhan NO selective reinstatement** (if per-city ROI > 0%): `BAND_NO_ENABLED=True`, `BAND_CITY_ALLOW={"munich","wuhan"}`. Restores ~$20–30/day fill velocity and rebuilds RECYCLE inventory before pipeline exhausts in 2–4 days. *(§2a; §6 Experiment 1)*
- [ ] **Temperature pricer cold-bias correction for Beijing/Chengdu** (if per-city ROI < 0%): shadow-test +3°C seasonal offset for Jun–Aug. *(§6 Experiment 3)*

**P1 — Today, parallel to join:**
- [ ] **REVERT M1_BETA_LOCKOUT: `METAR_LOCKOUT_TEMP_FLOOR = 0.5°C`.** Day 20 stall, day 5 of proposal, standing rule triggered at day 14. Zero capital risk (gate not live). *(Gatekeeper "Proposed Actions" carry-over)*
- [ ] **Set `BAND_NO_CASH_RESERVE=0.0` while BAND_NO_ENABLED=False.** Removes dead-weight reserve. Reverts to 0.30 when NO re-enabled. *(§2c; §6 Experiment 2)*
- [ ] **Verify PAIR_FAV YES gate (code read).** Chengdu YES fill at 0.38 vs gate=0.45. Confirm this was a fill-time price race, not a gate bypass. *(exec_audit S4 FLAG)*

**P2 — This week:**
- [ ] **Verify pUSD maker rebate receipt** (~$2.38 estimated accrued, above $1 threshold). Check Polygon funder wallet; escalate to Polymarket #support if absent. Third consecutive session flagging this. *(pnl_ledger S3)*
- [ ] **Cancel remaining Moscow open orders** if any survive (legacy pre-allowlist order, NOT in BAND_CITY_ALLOW). *(gatekeeper advisory #2; exec_audit ALERTS)*
- [ ] **Weekly floor monitoring:** Once SELL_EXIT clears, cash restores to ~$139. No new position should be posted that depletes cash below $75 before that clearing. Current state (BAND_NO=False, PAIR_FAV=0/cycle) satisfies this automatically.

---

## 3-Line Summary

**Capital at risk:** $76.31 cash ($1.31 above $75 weekly floor); equity ~$185 (SELL_EXIT pending adding ~$62). Today's 4 RECYCLE099 exits (+$9.17) partially offset yesterday's 3 NO-loss resolutions (−$15.29 net). BAND_NO halted by EVOLVE this morning; all Jul 2 queue cycles show no_cands=0, posted=0 — system has zero new inventory being built.

**Primary threat:** RECYCLE inventory (the only active revenue source) depletes within 2–4 days as existing SELL_EXIT orders clear. Munich+Wuhan NO reinstatement must be decided promptly to rebuild inventory before pipeline exhausts. The prerequisite is the VPS resolution join, named P0 for the fourth consecutive session.

**Gates:** FILLED_VS_FIRED crosses n=100 today; CI blocked by Gamma 403 unless VPS join runs before Jul 5. One command on VPS simultaneously unblocks 4 gate CIs and delivers the per-city verdict needed to either reinstate Munich+Wuhan NO or confirm full NO halt. No other action has comparable leverage.

---

*Research audit complete. Snapshot 2026-07-02T11:23:06Z (7 min old). Four specialist reports consumed (all within 36h). Raw data: maker_fills_recent.log Jul 2 lines (130 STRUCT-BAND-Q events); exit099_live.jsonl (4 Jul 2 recycles); bankroll.json; band_config.txt; shadow_summary.json (351 logger entries through Jul 2). git fetch unavailable (remote timeout) — GitHub MCP used for all reads. State_log not read directly (file too large for MCP); state inferred from band_config comments, system_status commits, and specialist reports.*
