# Research Audit — 2026-07-30T10:29Z

**STALL — DAY 7.** `system_status.txt` shows `failed/unknown`. ABORT condition met (missing `'klaus systemd: active'`). SNAPSHOT fresh (2026-07-30T10:24:17Z, ~5 min old). Data is current; bot is not. Following prior-run precedent (07-25, 07-26 audits) of substantive STALL analysis on fresh data.

---

## Data Sources Consumed

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-07-30T07:07Z | ABORT/STALL |
| calib_monitor_report.md | 2026-07-30T08:08Z | ABORT/STALL |
| gatekeeper_report.md | 2026-07-30T09:15Z | ABORT/STALL |
| pnl_ledger_report.md | 2026-07-29T23:37Z | ABORT/STALL |
| data-mirror SNAPSHOT | 2026-07-30T10:24Z | FRESH |
| state_log.md last entry | 2026-07-26T14:57Z | 4d ago |

All four specialist reports fired and aborted today. No specialist computed new execution, calibration, gate, or P&L data — system has been dark since 2026-07-24T10:09Z. All metrics below are carried from last-computed windows or read directly from config/mirror.

---

## System Snapshot

| Field | Value |
|---|---|
| Capital | $88.750373 |
| Band ruin floor | $89.16 (BAND_PHASE2 gate) |
| Gap to ruin floor | **−$0.41** (mechanically blocks all band paths) |
| Total PnL lifetime | −$75.40 (n=3,093 trades) |
| Open positions | 0 |
| Service alive | NO — `failed/unknown` day 7 |
| BAND_LIVE | False — day 24 dark (since 2026-07-06T22:08Z) |
| BAND_NO_ENABLED | False — rail-halt 2026-07-02 (live WR 39.2%) |
| UPDOWN_STOP | Present — PERMANENT (graveyard #15, EVOLVE 2026-07-26) |
| LDA_STOP | Active (rolling-20 worst −$36.39 < −$30 threshold) |
| Loop mode | WEEKLY-ONLY (daily + liveness timers owner-disabled 2026-07-24) |
| Next EVOLVE weekly | ~2026-08-02 |

---

## 1. Primary Bottleneck for Compounding

**Bottleneck: Service dead (VPS systemd `failed/unknown`).** Compounding = ROI/turn × turns/day × equity deployed. Turns/day = 0 since 2026-07-24. The multiplier is zero regardless of ROI or equity.

Ranking justification against the full list:

1. **Equity deployed / turns/day** — both zero (service dead). This dominates all others.
2. ROI/turn — cannot be measured; last fill was 2026-07-24 before the shutdown.
3. Fills / NO-parity / queue health — not producible (exec_audit aborted, 0 fills in 10d).
4. Calibration / dispersion edge — secondary concern; disp_ratio 0.781 (INVERTED, d28) means even a running system has no band edge. This is the second-order bottleneck once service is restored.
5. Risk frame — capital $0.41 below ruin floor; mechanically correct but irrelevant while system is stopped.
6. Data reliability — fresh (SNAPSHOT 5 min old). Not a bottleneck.

**Source:** exec_audit (fills=N/A), pnl_ledger (turns=0, roi/turn=N/A, 10 consecutive zero-fill days), system_status.txt (`failed/unknown`).

---

## 2. Existing-System Optimization

The four reports collectively describe a system with $0 deployed, 0 turns/day, and all execution paths disabled. There is no active system to optimize — only preconditions to meet before any optimization is relevant.

What the reports collectively imply:

**a. Capital floor gap ($0.41) is trivial in dollar terms but mechanically blocking.**
Gatekeeper confirms capital $88.750373 < $89.16 ruin floor. BAND_PHASE2_CAPITAL=600.0 is far beyond current equity — the $89.16 floor is a charter rule, not a code constant. A $0.41 injection (or a charter re-read to clarify what the ruin floor actually protects) is the cheapest unblock. Expected delta if cleared: unlocks the mechanical path but NOT the live band (BAND_LIVE=False requires human decision separately). Confidence: high. Effort: trivial.

**b. Dispersion inversion (disp_ratio7=0.781, day 28) makes band re-enable net-negative.**
Calib monitor (carried 07-24): all 3 regions inverted, 0/6 days above 1.10 in last computed window (07-18..07-23). The band earns by harvesting implied-vs-realized dispersion premium. At ratio < 1.0 the market is underpricing realized dispersion — the band posts YES at prices that are systematically too high. Any BAND_LIVE=True decision in this regime would bleed. Expected delta of re-enabling band in current disp regime: negative. Confidence: high (n~105, decision-grade). Effort: low (just don't re-enable).

**c. Winner's curse on fills (G3 confirmed, n=75) invalidates G1 and G7 ROI figures as actionable.**
Gatekeeper: G3 filled WR 17.3% vs simulated 7.6%, CI entirely negative [−75.0, −34.2]%. G1 BAND_YES ROI +4.0% and G7 SUM_POSTED ROI +11.5% are upper-bound ceiling estimates, not expected values. The actual expected filled ROI is materially lower (possibly negative). This is a structural blocker on both gates regardless of capital or dispersion recovery. Expected delta of treating G1/G7 as READY: false positive — would re-enable a negative-EV path. Confidence: high (G3 n=75, CI unambiguous). Effort: zero (block stands).

**d. No idle cash, no starved queue, no over-restrictive caps to relax.**
With BAND_LIVE=False and service down, all caps (BAND_NO_DAILY_CAP=40, BAND_MD_DAILY_BUDGET=9999) are inert. Queue rank weights and reclaim parameters are irrelevant. There is nothing to tune until the system fires again.

---

## 3. Gate Pipeline Review

From gatekeeper_report.md (09:15 UTC today). All counts frozen — system dead, zero accumulation possible.

| Gate | n | Status | To Nearest Transition | Accelerant |
|---|---|---|---|---|
| G1 BAND_YES per slice | 934 | AMBIGUOUS | G3 WC must clear first; G3 needs n=25 more (currently n=75, threshold n=100) | None while band dark |
| G2a BAND_NO_d1 shadow | 115 | AMBIGUOUS | Shadow n≥100 passed; live n=51 WR 39.2% REJECTED — shadow CI cannot override live | Re-enable only if live WR recovers |
| G2b PAIR_FAV_YES | 9 | COLLECTING | Need ~91 fills; frozen while BAND_LIVE=False | Restart service + enable BAND_LIVE |
| G2c PAIR_FAV_NO | 9 | COLLECTING | Need ~91 fills; frozen while BAND_LIVE=False | Same |
| G3 FILLED_vs_FIRED | 75 | WATCH_ITEM | Need 25 fills to hit n=100; but CI entirely negative already | Restart service; don't expect pass |
| G5 THERMO_MAKER_NO | 125 | REJECTED | Human directive required; ROI net fees −EV | N/A |
| G6 M1_BETA_LOCKOUT | 31 | REJECTED | Human directive required (EVOLVE Jul-04) | N/A |
| G7 SUM_POSTED [0.70,0.85] | 382 | AMBIGUOUS | G3 WC ceiling; band dark day 24 | Same as G2b/G2c |
| G8 UPDOWN_CROSSING | 127 | REJECTED | Graveyard #15; class closed (EVOLVE 2026-07-26) | Permanently dead |

**Nearest gate to transition:** G3 FILLED_vs_FIRED at n=75 needs 25 more fills. However, this gate's CI is already entirely negative. Reaching n=100 will formalize the REJECTION, not unlock anything. The nearest gate that could produce a positive transition does not exist in the current portfolio — G2b/G2c PAIR_FAV at n=9 are the only genuinely open gates, but both are frozen by BAND_LIVE=False.

**What would accelerate accumulation WITHOUT degrading expectancy:** Restart service in shadow-only mode (BAND_LIVE=False). PAIR_FAV_SHADOW=True and BAND_PAIR_SHADOW=True are both enabled in band_config.txt — shadow quotes continue to log would-fire events even without live capital. This accumulates G2b/G2c data at zero cost. The constraint is the service must be running.

---

## 4. Assumption Attack

The three load-bearing assumptions of the band system today:

### A. Dispersion premium persists (implied > realized spread)

**Status: FALSIFIED at current measurement (day 28 consecutive inversion).**

Calib monitor: disp_ratio7 = 0.781, threshold > 1.10. All three regions sub-1.0 (EU 0.789, Asia 0.743, US/Other 0.789). Daily trend 07-18..07-23: 0.485 / 0.925 / 0.779 / 0.783 / 0.851 / 0.762. Zero of six days above threshold. The last state_log reading (07-22 evening) showed the 07-21 value finalized at 0.787 (pulled back from 1.256 partial), and 07-22 evening at 1.105 partial. The ratio is oscillating between 0.7 and 1.1 with no sustained premium. BAND_LIVE=False since 07-06 (day 24) is a correct response to this — the halt predates the n~105 decision-grade estimate but is confirmed by it.

Threat level: HIGH. This is the foundation of the entire band model. A ratio < 1.0 means the band posts YES at prices that are too expensive for realized outcomes. Without premium recovery, the expected band ROI is structurally negative.

### B. Fills are not adversely selected (winner's curse absent)

**Status: CONFIRMED THREAT — winner's curse structurally present (G3, n=75, decision-grade).**

Gatekeeper: G3 FILLED_vs_FIRED shows filled WR 17.3% vs simulated WR 7.6% — a 10pp gap. The CI on filled ROI is entirely negative [−75.0, −34.2]%. This means: our CLOB quotes get hit preferentially by informed takers when the market is moving against our position. MMs and informed flow see the same (or faster) signal, lift our YES quotes when they expect NO to win, and let our quotes rest when they expect YES to win. This is structural (CLOB market design) and cannot be patched by parameter tuning within the current quote strategy. It blocks G1 and G7 as noted above.

Threat level: HIGH. This assumption was foundational and is now contradicted by n=75 live data. It requires architectural response (e.g., shift to maker-resting quotes with explicit adverse-selection filtering) not parameter tweaks.

### C. Recycle velocity scales with capital and fill rate

**Status: INDETERMINATE — system dark, no measurement possible.**

Band has been dark 24 days (BAND_LIVE=False since 07-06) and service has been dead 7 days. RECYCLE099 (exit099_live) has generated zero events. BAND_RECLAIM_AGE_S=2h means resting quotes age out quickly; if recycle velocity matters, the entire resting book has cleared. Cannot measure scaling behavior. The assumption is neither supported nor threatened by today's data — it is simply untestable.

Threat level: UNKNOWN. If the system restarts and fills resume, this becomes the first thing to measure: does recycle cadence (BAND_RECLAIM_PER_CYCLE=10 fetches/300s) match expected turnover?

---

## 5. Market Intelligence — Competitor Posture (day-of-month 30 mod 3 = 0)

**Data gap: maker_fills_recent.log failed to retrieve (MCP schema error). Shadow files unavailable (git network timeout). badatmath_watch delta and leaderboard teardown cannot be produced from available data this run.**

What CAN be read from band_config.txt as of 2026-07-30T10:24Z:

- `BAND_REALBOOK_YES = True`: we mirror badatmath's real CLOB book (gate G1 passed n=741 fill-joins). This is unchanged since 2026-06-11. No delta.
- `BAND_YES_LIVE_MIN_DOUT = 9` (`# 2026-07-03 PAUSED standalone YES band`): standalone YES band has been dark since 07-03 independent of BAND_LIVE. We are not competing with badatmath on YES standalone.
- `PAIR_FAV_ENABLED = True`, `BAND_PAIR_SHADOW = True`: pair-fav YES+NO is the live strategy overlay, but frozen by BAND_LIVE=False. If badatmath continues posting in the pair-fav bucket, he is accumulating fills while we are dark.
- `BAND_NO_ENABLED = False`: we are absent from the NO market entirely (rail-halted 07-02).

Net competitive delta: **we are completely absent from all weather markets** for 24+ days. Any edge in our strategy that depends on market presence (queue priority, reclaim, spread capture) has been fully forfeited. Whether badatmath or other bots have filled our absence in the book is unknown without fresh shadow data. This gap should be explicitly noted as a data debt to resolve on next VPS restart.

---

## 6. Experiments

### Experiment 1: Dispersion Regime Autocorrelation

**Hypothesis:** disp_ratio oscillates on 5–10 day timescales between inverted (<1.0) and premium (>1.10) regimes; a 3-consecutive-day streak above 1.10 is a reliable leading indicator of a sustained premium window (≥5 days > 1.10) that would justify band re-enable.

**Data needed:** All historical daily disp_ratio values (available in calib_monitor commit history, ~30+ days).
**Time:** 2 analyst-hours to extract from commit log and compute autocorrelation.
**Cost:** Zero.
**Success metric:** Lag-1 autocorrelation > 0.5 AND conditional probability P(next day > 1.10 | 3d streak > 1.10) > 0.70.
**Decision-if-yes:** Adopt 3-consecutive-day trigger as the band re-enable criterion (it's already informally in use; this validates it statistically).
**Decision-if-no:** Single-day disp_ratio is noisy; increase the streak threshold to 5+ days or abandon ratio-based gating in favor of a longer EMA.

**Value-of-information:** HIGH. Band re-enable timing is the highest-leverage decision available once capital/service prerequisites are met. A falsifiable trigger prevents both premature re-enable (during inversion) and indefinite delay (if ratio recovers).

---

### Experiment 2: Winner's Curse Subgroup Analysis (G3)

**Hypothesis:** The G3 winner's curse (filled WR 17.3% vs sim 7.6%, n=75) is concentrated in a subset of market conditions (e.g., final 30 minutes before resolution, high-delta cities, specific BAND_WING=2 shoulder legs) rather than being uniform across all fills.

**Data needed:** The 75 G3 filled trades + band_resolution_join output (both should be on VPS in logs/shadow/). Fields: fill time vs resolution, city, offset from mode, market odds at fill, subsequent resolution outcome.
**Time:** 3 analyst-hours once VPS access is restored.
**Cost:** Zero.
**Success metric:** ≥1 sub-cell where filled WR is within 2pp of simulated WR AND sub-cell contains ≥20 observations.
**Decision-if-yes:** Filter out winner's-curse-concentrated conditions in PAIR_FAV quote logic; re-evaluate G1/G7 ROI with filtered population.
**Decision-if-no:** Winner's curse is systemic and uniform → only a maker-resting (never-taker) architecture can eliminate it; taker-fills must be abandoned.

**Value-of-information:** HIGH. G3 currently blocks G1, G7, and all BAND_YES re-enable arguments. If subgroups survive, it reopens two gates. If uniform, it closes the taker model permanently.

---

### Experiment 3: Shadow-Only Restart Validity Check

**Hypothesis:** Restarting the VPS service with BAND_LIVE=False, BAND_NO_ENABLED=False, UPDOWN_STOP present (no live capital deployed) allows the shadow loggers to resume accumulating G2b/G2c/G7 data and the dispersion ratio to resume being monitored, with zero live-capital risk.

**Data needed:** band_config.txt flags (already read — PAIR_FAV_SHADOW=True, BAND_PAIR_SHADOW=True, MAKER_SHADOW_ENABLED=True confirm shadow mode is wired).
**Time:** 30 minutes to SSH, restart service, verify journalctl shows shadow events and no CLOB order submissions.
**Cost:** Zero (no capital risk; existing VPS subscription covers the server).
**Success metric:** After restart, shadow_summary.json updates within 15 minutes, system_status.txt shows `active`, and trades.jsonl count does not increase (confirming no live fires).
**Decision-if-yes:** Keep service running in shadow-only mode indefinitely; resume gate accumulation.
**Decision-if-no (shadow fires produce live orders despite BAND_LIVE=False):** Emergency stop, debug config flag propagation. This would be a serious bug.

**Value-of-information:** HIGH. This is the cheapest possible restart path. It unblocks all monitoring and data accumulation without requiring capital injection, dispersion recovery, or BAND_LIVE decision. It turns $0 turns/day into measurable gate accumulation.

---

## 7. Single Best Action

**SSH to VPS (45.85.251.173) and restart the service in shadow-only mode.**

**Justification:** This is the fourth consecutive audit (07-25, 07-26×2, 07-30) recommending this as the best action. The gatekeeper_report (09:15 today) explicitly lists VPS restart as the first of three mandatory preconditions. The action:
- Costs nothing (no capital at risk — BAND_LIVE=False already configured)
- Unblocks ALL monitoring (dispersion ratio, shadow gate accumulation, disp_ratio trend visibility)
- Allows G2b/G2c PAIR_FAV to accumulate from n=9 toward n=100
- Resumes the calib_monitor dispersion pipeline (currently dark since 07-24)
- Does NOT require capital injection ($0.41 ruin-floor gap) or human BAND_LIVE decision

**Concrete first step:** `ssh root@45.85.251.173` → `systemctl start klaus` → `journalctl -u klaus -f --since now` → confirm shadow events appear and no `ORDER_PLACED` lines in output.

**Why not earlier actions first:** Capital injection ($0.41) unblocks nothing without service restart. Band re-enable is net-negative while disp_ratio=0.781. No gate is READY to promote. Killing G8 was already executed (EVOLVE 07-26). The service restart is the only unblock that chains into everything else.

---

## PROPOSED ACTIONS (human review)

1. **SSH to VPS and restart service in shadow-only mode** (BAND_LIVE=False, UPDOWN_STOP in place, no live fires). Verify shadow loggers activate. No capital at risk. [RECOMMENDED — 4th consecutive audit]

2. **Band re-enable pre-conditions checklist** — before any BAND_LIVE=True decision, all three must be true simultaneously:
   - (a) Capital ≥ $89.16 (currently $0.41 short)
   - (b) disp_ratio7 > 1.10 for ≥3 consecutive days (currently 0.781, 28d inverted)
   - (c) G3 FILLED_vs_FIRED clears at n≥100 OR winner's curse subgroup analysis identifies safe fill conditions
   None of (a), (b), (c) are currently met.

3. **Do not re-enable any rejected gate** (G5 THERMO, G6 M1_BETA, G8 UPDOWN) without explicit user directive. All three have pre-registered human-review requirements.

4. **Isotonic calibration file**: deployed version 54d stale (2026-06-06); candidate from 2026-07-23 has 2 material tail diffs but OOS brier worse than raw. Human review required before promotion. Do not auto-promote. [FROM calib_monitor S4 CARRIED]

---

## STALL COUNTER

| Metric | Value | Trend |
|---|---|---|
| Service dead hours | ~142h | +24h/day |
| Band dark days | 24 | +1/day |
| disp_inversion days (est) | 28 | +1/day |
| Consecutive zero-fill days | 10 | +1/day |
| Gates READY | 0 | flat |
| Gates REJECTED | 3 (G5, G6, G8) | flat |
| Capital gap to ruin floor | −$0.41 | flat |

No action available at loop level. All paths blocked. Human SSH intervention is the only unblock.
