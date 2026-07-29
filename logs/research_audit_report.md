# Research Audit — 2026-07-29 — STALL (Day 6, Run 10)

**ABORT CONDITION MET**: `system_status.txt` shows `failed/unknown` — not `active`. Analysis below synthesizes today's four specialist reports (all fresh, all aborting on the same condition). No new analysis fabricated on absent execution data.

**Snapshot**: 2026-07-29T10:23:16Z (fresh, <6h). Bot last active: 2026-07-24T10:09:19Z (~120h dead). Owner-directed shutdown 2026-07-24; daily + liveness timers disabled; loop WEEKLY-ONLY per EVOLVE 2026-07-26 (commit `ddbcecdd1`). Equity: $88.750373 (flat since Jul-6). 9 consecutive zero-fill days. 0 live paths.

Specialist report coverage: exec_audit 07:06Z ✓ | calib_monitor 08:07Z ✓ | gatekeeper 09:07Z ✓ | pnl_ledger 23:30Z prior day ✓ (all fresh, all STALL/ABORT).

---

## 1. Primary Bottleneck for Compounding

**System offline (owner-directed) — zero turns/day.** The compounding expression (ROI/turn × turns/day × equity) is identically zero on all three factors. No marginal parameter tuning applies.

When/if service restarts, the secondary bottleneck is **zero live firing paths** — every monetizable channel is disabled, formally rejected, or mechanically blocked:

| Path | Status | Reason |
|---|---|---|
| BAND_LIVE | False | Day 23 dark (Jul-6); capital $0.41 below ruin_floor $89.16 |
| BAND_NO_ENABLED | False | WR 39.2% n=51 live; formally disabled Jul-2 |
| G8 UPDOWN_CROSSING | KILLED | WR 0.9528 < BE 0.9651 n=127; graveyard #15 (EVOLVE Jul-26) |
| STWA_REGULAR_YES/NO | Both False | Disabled |
| UPDOWN_STOP | ACTIVE | PF 0.79 < 0.80 charter rail (Jul-19) |
| LDA | STOPPED | Rolling-20 PnL below threshold |
| G5 THERMO / G6 M1 LOCKOUT | REJECTED | Human directive required to reconsider |

BAND_PAIR_FAV_ENABLED=True is the only True live-path flag, but it is inert while BAND_LIVE=False.

**Justification from reports**: gatekeeper_report STALL run 9 lists all structural blockers above. exec_audit_report confirms 0 fills, 0 resting activity. pnl_ledger confirms 9 zero-fill days.

---

## 2. Existing-System Optimization

No code optimization is actionable on a dead system with zero firing paths. From specialist reports:

| Item | Expected Delta | Confidence | Effort | Blocker |
|---|---|---|---|---|
| SSH + diagnose systemd failure | Enables restart decision | N/A — prerequisite | ~1h | VPS access |
| Capital injection ~$0.50 (to clear ruin_floor $89.16) | Unblocks band path mechanically | Low (BAND_LIVE=False; needs explicit re-enable separately) | Owner decision | Owner action |
| Verify maker rebates ($3.917 expected) | Recover pUSD from Polymarket wallet | High (mechanism exists) | 10 min | Owner login |

BAND_PAIR_FAV_ENABLED=True: at restart + capital injection, pair-fav would resume quoting. But gate G2b/G2c have only n=9 live fills each, clouded by CF bias (state_log Jul-11). Not re-enableable on data this thin — shadow accumulation required first.

**No idle cash to unlock** — no live path exists for cash to enter. Cash "velocity" = $0 by design.

---

## 3. Gate Pipeline Review

From gatekeeper_report 2026-07-29T09:07:16Z (STALL run 9):

**No gates READY. No gates newly REJECTED this run. All counters frozen at +0.**

| Gate | n (auth) | Status | Path to READY |
|---|---|---|---|
| G1 BAND_YES | 934 sim | AMBIGUOUS | G3 winner's curse blocks sim-CI re-enable; band dark |
| G2b PAIR_FAV_NO | 9 live | COLLECTING | Band dark; CF bias; ETA indeterminate |
| G2c PAIR_FAV_YES | 9 live | COLLECTING | Band dark; CF bias; ETA indeterminate |
| G3 WINNER'S CURSE | 75 filled | WATCH_ITEM | Confirms adversarial selection; hard blocker on G1/G7 |
| G5 THERMO | 125 | **REJECTED** | Human directive required — no reconsideration |
| G6 M1 LOCKOUT | 31 | **REJECTED** | Human directive required — no reconsideration |
| G7 SUM_POSTED | 382 sim | AMBIGUOUS | Band dark; G3 blocks sim-CI |
| G8 UPDOWN_CROSSING | 127 | **KILLED** (Jul-26) | Graveyard #15. Class closed. |

Shadow dirs for 2026-07-27 and 2026-07-28 contain only `badatmath_watch.jsonl` — no band_struct, thermo_maker, metar_lockout, exit099_live, or basket_exit_shadow. All accumulators frozen while system is down.

**To accelerate accumulation without degrading expectancy:** shadow-only restart (BAND_LIVE=False, BAND_NO=False, all live flags untouched) would resume G2b/G2c observation counts and fresh dispersion data without deploying capital or requiring gate promotion.

---

## 4. Assumption Attack

The band system rests on three load-bearing assumptions. Status from today's reports:

**A. Dispersion premium persists (market-implied spread > realized spread)**
- Status: **DECISIVELY THREATENED** (calib_monitor_report, S3 CARRIED, pre-registered)
- disp_ratio7 = 0.781 vs threshold >1.10 — inverted edge, estimated day 27 consecutive
- All three regions sub-1.0: EU 0.789, Asia 0.743, US/Other 0.789
- Last computed window (Jul-18..Jul-23): 0/6 days above threshold
- Fresh computation unavailable — system dark since Jul-24
- BAND_LIVE was disabled Jul-6 (day 23 dark); dispersion inversion is independent confirmation the halt was correct
- **The core band edge premise does not hold in the current regime**

**B. Fills are not adversely selected (winner's curse bounded)**
- Status: **CONFIRMED ADVERSE** (gatekeeper_report G3, n=75, WATCH_ITEM)
- Filled WR 17.3% vs sim WR 7.6% — gap −83.4 pp
- Fill rate ~8% (75 filled / 934 sim) confirms adversarial selection at the book
- Live ROI CI: [−75.0%, −34.2%] — entirely negative
- G3 blocks all sim-CI arguments for G1 and G7 re-enable
- **Falsified. Winner's curse is structural at n=75 — not small-sample noise**

**C. Recycle velocity scales with capital deployed**
- Status: **MOOT** (system down, 0 recycles executing since Jul-6)
- Cannot evaluate at n=0 post-disable
- When/if restated: assumption (C) depends on (A) — if dispersion inverted, recycled NO at 0.99+ is not harvesting margin, it is closing into an adverse book

Net: Two of three foundational assumptions are falsified or moot. The band system has no demonstrated edge in the current regime. Prior halt decisions at G2b WR 39.2% and BAND_LIVE=False are confirmed correct by this analysis.

---

## 5. Market Intelligence — [2] Platform Mechanics

*(Day-of-month 29 mod 3 = 2: platform mechanics rotation)*

**Unable to access external URLs today** (git fetch and outbound HTTPS both failing in this sandbox environment; proxy/network issue). Reporting only what is knowable from mirror data and band_config.

**From band_config.txt (known):**
- Maker rebate: 100% of taker fees redistributed (CLAUDE.md); MAKER_SHADOW_ENABLED=True; mechanism in place
- Weather market taker fees: not explicitly coded in config (updown ~1.56% at 50%; weather market fee schedule unknown from config alone)
- BAND_SUM_MAX=0.85 caps YES band to ≥15¢/sh locked; BAND_PAIR_SUM_MAX=0.90 caps pair-fav to ≥10¢/sh

**Concrete payout item (pnl_ledger_report):** $3.917 cumulative expected maker rebates, unverified receipt. No payout has been recorded in any session. This exceeds the $1 min accrual threshold — owner should check Polymarket wallet for pUSD balance. Even a partial rebate return would push equity above ruin_floor $89.16 ($88.75 + $0.42 needed).

**Delta vs state_log knowledge:** No new fee schedule changes noted in any config comment or commit since Jul-26. Jul-26 EVOLVE commit makes no mention of platform mechanics change. Treating as no delta pending external check.

---

## 6. Experiments

Three experiments designed for before or during a service restart: cheap, fast, falsifiable, high value-of-information.

**Experiment A: Dispersion pulse check (Jul-24..Jul-29 gap)**
- Hypothesis: disp_ratio may have recovered above 1.0 in the 5-day dark period; we cannot make a correct band restart decision without this measurement
- Data: SSH to VPS → run `shadow_grade.py` (or equivalent Kalman scoring on any cached forecast vs market-mid data) on the Jul-24..Jul-29 period manually, without restarting the full service
- Time: 30–60 min
- Cost: $0 (no trades)
- Success metric: ratio >1.10 for 3+ consecutive days in the gap → begin band restart sequence; ratio remains <1.0 → extend halt, edge not recovered
- Decision-if-yes: Re-examine BAND_LIVE re-enable (capital injection + human gate review required)
- Decision-if-no: No change to halt; next pulse check in 1 week

**Experiment B: Maker rebate wallet audit**
- Hypothesis: $3.917 in cumulative expected rebates has been paid into pUSD and is unclaimed; recovering even $0.42 of it puts equity above ruin_floor $89.16
- Data: Login to polymarket.com wallet; check pUSD balance vs prior withdrawals
- Time: 10 min
- Cost: $0
- Success metric: pUSD balance ≥$1 → withdraw to USDC, push to bankroll.json, document in state_log
- Decision-if-yes: Execute withdrawal; clears the $0.41 ruin_floor gap; document new equity
- Decision-if-no: Rebate mechanism not paying out or threshold not met; remove from expected-rebates tracking

**Experiment C: Shadow-only restart (minimum-risk intelligence gathering)**
- Hypothesis: Restarting the service with all live flags False (BAND_LIVE=False, BAND_NO=False, live taker paths disabled) resumes shadow data accumulation (pair-fav shadow, dispersion metrics, badatmath_watch, gate counters) without deploying any capital
- Data: SSH → `sudo systemctl start klaus` → confirm shadow dirs writing → run for 24–72h → compute disp_ratio on Jul-29+ data
- Time: 2h setup; 1–3 days accumulation
- Cost: $0 (shadow only; no capital deployed)
- Success metric: Shadow dirs populating band_struct.jsonl, dispersion computable from fresh window; confirms service is healthy
- Decision-if-yes: disp_ratio and gate accumulators live again; unblocks Experiment A data and G2b/G2c accumulation; review in 72h
- Decision-if-no: Service crashes again in shadow mode → systemic dependency/config issue; SSH deeper diagnosis required

---

## 7. Single Best Action

**SSH to VPS → restart service in shadow-only mode (Experiment C).**

**Rationale:** The system cannot make any informed restart decision without fresh dispersion data — the calib_monitor has been carrying the Jul-24 measurement for 6 days and disp_ratio trend cannot be evaluated without fresh computation. Shadow restart costs $0, risks $0, and unblocks the two key intelligence gaps (dispersion measurement, G2b/G2c counter accumulation) that must precede any capital deployment decision. It is the minimal necessary action.

**Supporting evidence from specialist reports:**
- gatekeeper_report (run 9): "SSH to VPS if/when path forward intended. Burn rate zero — timing not urgent." Day 6 now; not truly urgent but every dark day is a frozen gate counter.
- calib_monitor_report: disp_ratio 0.781 inverted, no fresh computation possible without service; band restart decision literally impossible to make correctly without fresh measurements
- exec_audit_report: 0 fills, 0 resting activity; nothing to lose by restarting in shadow mode

**Sequencing (Experiment C + B combined, 2–3h total):**
1. SSH → `sudo systemctl status klaus` (diagnose failure reason)
2. Fix failure (likely OOM, crash loop, or timer race from Jul-24 shutdown)
3. `sudo systemctl start klaus` → verify `active (running)` → confirm shadow dirs writing
4. While waiting: login to Polymarket wallet → check pUSD rebate balance (Experiment B)
5. 24h later: read fresh shadow data → compute disp_ratio → post to state_log
6. Decision point: if disp_ratio >1.10 for 3+ days → begin band re-enable discussion; if still inverted → hold, check again in 1 week

**What this action does NOT do:** It does not re-enable any live path, does not require capital injection, does not promote any gate. It is purely intelligence-gathering.

---

## PROPOSED ACTIONS (human review)

1. **[HIGH PRIORITY] SSH + shadow restart** (Experiment C above): restart service in fully-shadow mode to resume intelligence gathering. Unblocks fresh dispersion data and gate counter accumulation. Risk: $0. Effort: ~2h.

2. **[10-MIN QUICK WIN] Maker rebate wallet check** (Experiment B): check Polymarket pUSD wallet for $3.917+ accrued rebates. If present, withdrawal of even $0.42 clears the ruin_floor gap mechanically.

3. **[HOLD] No live path re-enable** until: (a) fresh disp_ratio >1.10 for 3+ consecutive days, AND (b) capital ≥ $89.16 ruin_floor. Both conditions unmet. Recommended sequence: Experiment C → pulse check → capital decision.

4. **[NO ACTION] G8 graveyard receipt**: confirmed in EVOLVE 2026-07-26 (commit `ddbcecdd1`). No outstanding code action.

5. **[NO ACTION] G5/G6**: both REJECTED by explicit human directive. No reconsideration without owner override.

---

*Run ts: 2026-07-29T~10:35Z | Snapshot ts: 2026-07-29T10:23:16Z (fresh, <1h old at run time) | System: failed/unknown day 6 | Band dark day 23 | STALL run 10 | Specialist reports: exec ✓ 07:06Z | calib ✓ 08:07Z | gate ✓ 09:07Z | pnl ✓ 23:30Z prior*
