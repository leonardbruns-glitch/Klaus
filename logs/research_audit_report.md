# Klaus Research Audit — 2026-07-27T10:30Z

**STALL (day 4)** — `system_status.txt: failed/unknown`. Pre-registered abort condition met (missing `'klaus systemd: active'`). All specialist reports aborted/STALLed today. Snapshot 2026-07-27T10:11Z (fresh, <6h; data valid). Service intentionally offline since 2026-07-24T10:09Z per owner directive (EVOLVE `ddbcecdd1`; daily+liveness timers disabled; loop WEEKLY-ONLY). Analysis proceeds on fresh mirror data; no live execution metrics available.

**Capital**: $88.750373 ($21.50 CLOB + $67.25 owner on-chain injection, EVOLVE-documented to the cent). Open positions: 0. Fills since Jul-6: 0. Turns/day: 0. Zero-fill streak: day 7.

---

## 1. Primary Bottleneck for Compounding

**Binding constraint: system intentionally offline + zero live paths.** Ranked:

1. **Equity deployed = 0%** — No band path can fire. `BAND_LIVE=False` (Jul-6 EVOLVE wind-down: equity $108.35 < 50%·30d-HW $222.90; current $88.75 is further below this charter threshold). Capital $88.75 < ruin_floor $89.16 (by $0.41) — mechanical band block even if `BAND_LIVE` were re-armed.
2. **Turns/day = 0** — 7 consecutive zero-fill days (since Jul-6). Not a signal quality problem; system is offline.
3. **All gate verdicts unfavorable** — G3 winner's curse confirmed (filled WR −75.8% vs sim +11.5%); G8 KILLED; G5/G6 REJECTED; G1/G2a/G7 AMBIGUOUS with band-dark inertia. No READY gate exists to unlock a live path.
4. **S3 dispersion inversion (day 25)** — disp_ratio=0.781 persisting. The edge variable for the band system shows sustained inversion; this is the forward-looking bottleneck if/when service restarts.

The compounding multiplier is (0 ROI/turn × 0 turns/day × 0% deployed) = 0. No parameter change moves this while the system is offline with all paths disarmed.

---

## 2. Existing-System Optimization

All four specialist reports returned ABORT/STALL. No fills, no fill ratios, no queue cycle data, no calibration updates, no resting orders. The optimization surface is flat for live execution.

**Collective implications from specialist reports:**

| Issue | Implication | Confidence | Effort |
|---|---|---|---|
| Capital $0.41 below band ruin_floor ($88.75 vs $89.16) | Mechanical band block even if `BAND_LIVE` re-armed. Owner on-chain injection of ≥$0.50 clears it. | High (gatekeeper confirmed) | Zero (deposit only) |
| S3 disp_ratio=0.781 (day 25 of inversion) | Band edge assumption (dispersion premium) may be structurally compromised. Restoring service without investigating S3 risks firing into degraded edge. | Medium (isotonic staleness confounds) | High (requires fresh band fills to confirm; offline isotonic refit is a proxy) |
| S4 isotonic curve ~51d stale | Probability→price translation unreliable. If/when band restarts, isotonic refresh is first priority. | Medium | Medium (run isotonic refit on VPS) |

Expected delta from capital injection alone: clears mechanical blocker; no strategy benefit while `BAND_LIVE=False`.

---

## 3. Gate Pipeline Review

**From gatekeeper_report.md (today, 2026-07-27T~09:20Z, fresh):**

| Gate | Status | Notes / Next Action |
|---|---|---|
| G8 UPDOWN_CROSSING | ★ **REJECTED** (formalized EVOLVE 07-26) | Graveyard #15. Human confirmation receipt required; audit residual code paths. |
| G2b PAIR_FAV_NO | COLLECTING (9 live fills; inert, band dark) | No acceleration possible while `BAND_LIVE=False`. CF ROI +52.9% biased per state_log Jul-11. |
| G2c PAIR_FAV_YES | COLLECTING (9 live fills; inert, band dark) | No acceleration possible while `BAND_LIVE=False`. |
| G1, G2a, G7 | AMBIGUOUS (sim UB; G3 blocks re-enable) | Winner's curse fix required before any sim-CI argument is valid. |
| G3 FILLED_vs_FIRED | WATCH_ITEM (blocks G1 + G7) | Winner's curse confirmed CI [−75%,−34%]. Root cause analysis (Experiment B) is the gating prereq. |
| G5 THERMO_MAKER | REJECTED | No reconsideration without explicit human directive. |
| G6 M1 LOCKOUT | REJECTED | No reconsideration without explicit human directive. |

**No gate is newly READY. No gate is close to READY while the system is offline.**

Only actionable offline work: G3 winner's curse root cause analysis (Experiment B), which can rehabilitate the G1/G7 sim-CI arguments without requiring any live fills.

---

## 4. Assumption Attack

The band system's edge rests on three load-bearing assumptions. Today's evidence:

### A. Dispersion premium persists
**Status: THREATENED — S3 day 25, disp_ratio=0.781**

The dispersion premium is the fundamental edge claim: Klaus's Kalman/STWA forecast is more disperse (confident at extremes) than market prices. disp_ratio=0.781 means the market is currently *more* disperse than our model — the band's YES leg is quoting into a market that is already wider than our calibration, meaning the "cheap" asks we post are not cheap relative to a better-calibrated reference. This has persisted for ≥25 days (calib_monitor_report carried values; no update possible while dark).

Three candidate causes (not mutually exclusive):
- **S4 isotonic staleness (51d)**: The isotonic curve mapping model scores to prices was fit on a pre-July pool; July temperature dynamics may differ structurally (higher variance, different city mix). Stale curve → mis-scaled probabilities → apparent dispersion inversion.
- **Seasonal regime shift**: July is a high-variance month for temperature in many of the 51 cities. If the band's training data underweights high-variance periods, it will appear overconfident (under-disperse) relative to current market pricing.
- **Market learning**: Competing bots (badatmath class and similar) may have improved calibration, narrowing the information gap the band system exploited.

Evidence quality: **Medium** — S4 staleness confounds interpretation. Cannot distinguish "model is wrong" from "model is mis-scaled" without a fresh isotonic refit.

### B. Fills are not adversely selected
**Status: CONFIRMED THREAT — G3 winner's curse, CI [−75%,−34%]**

G3 FILLED_vs_FIRED: the subset of orders that actually fill generates WR=17.3% filled vs WR=7.6% sim. The 10pp gap in the *correct* direction (filled WR > sim WR, meaning fills happen when the market moves toward our position) is winner's curse: when Klaus fills easily, it is because a faster market participant has already priced the move. The entire CI for filled ROI [−75%,−34%] is negative at n=75 filled. This hard-blocks all sim-CI arguments for G1 and G7; no re-enable can cite shadow performance alone.

Evidence quality: **High** — n=75 filled, CI entirely negative; not a small-sample artifact.

### C. Recycle velocity scales (RECYCLE099 convergence)
**Status: MOOT — 0 open positions, 0 resting orders**

RECYCLE099 has nothing to recycle. Cannot be tested while system is offline. Structurally sound by design (convergence to 0.99 is arithmetic), but fill-rate dependency is inherited from assumption B. Last known state: 0 open positions confirmed by system_status.txt.

---

## 5. Market Intelligence — Competitor Posture (day 27 mod 3 = 0)

**Caveat: `data/shadow/badatmath_watch*` unavailable — git fetch timed out in network-constrained environment. Analysis from last known committed state only.**

From state_log and prior audits:
- **badatmath**: Primary mirror model. Our PAIR_FAV system explicitly mirrors their YES bid + NO bid pair structure. Last known: consistent band quoting across 51 cities; d+0/d+1/d+2 structure stable; median NO fill ~$5.16.
- **Klaus's absence**: BAND_LIVE=False since Jul-6 (21 days); service offline since Jul-24. badatmath has operated without Klaus competition for 21 days. If their fill rates have improved in this period, it confirms Klaus was providing meaningful liquidity (supports re-entry value). If unchanged, our order flow was market noise.
- **Updown market**: G8 killed (WR 95.28% < BE 96.51% at n=127). No updown competitive intelligence needed — class is closed.
- **No fresh delta available** — badatmath_watch log requires VPS access or network-available session.

---

## 6. Three Experiments

### Experiment A: Isotonic Recalibration (VPS, next EVOLVE)
- **Hypothesis**: S4 (51d stale isotonic curve) is the primary driver of S3 (disp_ratio=0.781 inversion). Refreshing the isotonic fit on the current 8228-row resolved pool will restore disp_ratio ≥1.0 within 3 days of deployment.
- **Data**: `data/trades.jsonl` (8228 rows; available on VPS) + Gamma resolution fetch (Gamma API accessible from VPS).
- **Time**: 2h VPS session.
- **Cost**: VPS hourly rate only; no capital at risk.
- **Success metric**: After deploying refreshed isotonic curve, disp_ratio ≥1.0 on the next calib_monitor run (within 72h of refit).
- **Decision if yes**: S3 was a calibration staleness artifact → dispersion premium thesis survives → proceed to BAND_LIVE re-arm cost-benefit analysis (subject to charter amendment criteria and capital floor).
- **Decision if no**: S3 reflects a structural regime change → do NOT re-arm band at current capital levels; treat band system as requiring full strategy review before restart.

### Experiment B: G3 Winner's Curse Root Cause (offline data analysis)
- **Hypothesis**: The fill/sim WR gap (+10pp, winner's curse) is concentrated in a specific identifiable subgroup (e.g., by time-of-day, bucket offset, days-out, or EV range) rather than uniform across all fills. Identifying the clean subgroup rehabilitates partial sim-CI arguments for G1/G7.
- **Data**: `data/trades.jsonl` fill timestamps vs posted timestamps; available from data-mirror (8228 rows).
- **Time**: 1d analysis session (no VPS required).
- **Cost**: Zero.
- **Success metric**: Identify ≥1 subgroup where filled ROI CI crosses zero and n≥30 fills — i.e., where winner's curse is absent or reversed.
- **Decision if yes**: Condition-gated re-enable possible → G1/G7 sim-CI arguments partially rehabilitated for the clean subgroup; taker band returns only under those conditions.
- **Decision if no**: Universal adverse selection confirmed at all observable subgroup splits → maker-only architecture is the correct long-run path; taker band does not return regardless of calibration.

### Experiment C: PAIR_FAV Markout Check (offline, shadow data)
- **Hypothesis**: The 9 live PAIR_FAV fills collected before wind-down (G2b/G2c COLLECTING) show neutral or positive markout on the NO leg, distinguishing PAIR_FAV from the adversely-selected standalone band.
- **Data**: `data/maker_fills_recent.log` + `data/shadow/band_struct*` (available on data-mirror if shadow files present; confirm via shadow_summary.json).
- **Time**: 2h data analysis.
- **Cost**: Zero.
- **Success metric**: NO leg fill price vs prevailing touch at +1h resolution computed for ≥6 of 9 fills; WR vs naive benchmark (≥50% correct direction).
- **Decision if yes (neutral/positive markout)**: PAIR_FAV NO is not adversely selected; prioritize enabling when service restarts + capital clears ruin_floor.
- **Decision if no (negative markout)**: PAIR_FAV NO also adversely selected → maker-mode PAIR_FAV is required; no taker restart of any band leg.

---

## 7. Single Best Action

**Experiment A: Isotonic Recalibration on VPS (next EVOLVE session, est. 2026-07-31)**

**Justification from specialist reports**:
- *Calib monitor*: S3 disp_ratio=0.781 (day 25) + S4 isotonic 51d stale — two causally linked alerts. The isotonic staleness is the one of the two that can be fixed in a single VPS session.
- *Gatekeeper*: No READY gates; capital $0.41 below ruin_floor — nothing can be moved remotely. The isotonic refit is the only high-value action that doesn't require a live system.
- *PnL ledger*: 0 turns, 0 fills, 0 ROI. Compounding is fully stalled; the calibration question is the key gating prereq before any restart argument can be made.
- *Exec audit*: ABORT — confirms no execution path exists to generate data; the offline diagnostic is the only productive use of the stall period.

The dispersion premium is the load-bearing assumption for the entire band system. disp_ratio=0.781 for 25 consecutive days is the single most important unanswered question. The isotonic refit is the cheapest possible test: 2h of VPS time, zero capital at risk, binary answer. Everything else (G2b/G2c fill accumulation, G3 root cause, band re-arm) depends on this answer first.

**Concrete first step**: In next EVOLVE session, before any config change: `python3 analytics/isotonic_fit.py --trades data/trades.jsonl --plot` to view current vs stale calibration curve shape. If the file/script doesn't exist: `grep -r 'isotonic' analytics/ --include='*.py' -l` to locate the refit entry point.

G8 graveyard confirmation is a close second (human receipt required per gatekeeper) but is administrative, not edge-generating.

---

## PROPOSED ACTIONS (human review)

1. **Isotonic recalibration** (Experiment A) — run `analytics/isotonic_fit.py` in next EVOLVE session. Required prereq before any `BAND_LIVE` re-arm discussion. Zero capital at risk.
2. **Capital buffer** — inject ≥$0.50 on-chain to clear ruin_floor ($88.75 → ≥$89.25). Eliminates mechanical band block. Low priority until isotonic question answered.
3. **G3 winner's curse analysis** (Experiment B) — 1d offline data task on `trades.jsonl`. Determines whether taker band or maker-only is the correct long-run architecture.
4. **G8 graveyard confirmation** — EVOLVE already killed (graveyard #15). Human to confirm no residual code paths for updown certainty-taker remain in live codebase. Administrative.
5. **Maker rebate payout check** — Cumulative expected rebate $3.917 upper bound (unchanged since Jul-6 wind-down). Owner should verify pUSD deposits in Polymarket wallet — may be unclaimed. Requires ≥$1 accrual (confirmed met).

---

*Generated 2026-07-27T10:30Z by Research Audit agent. STALL day 4 (intentional owner shutdown; weekly-only loop). System offline since 2026-07-24T10:09Z. Snapshot: 2026-07-27T10:11Z (fresh, <1h). Prior specialist reports: exec_audit 07:07Z, calib_monitor 08:07Z, gatekeeper ~09:20Z, pnl_ledger 23:37Z (07-26) — all within 36h, all aborted/STALLed. Next scheduled EVOLVE: est. 2026-07-31.*
