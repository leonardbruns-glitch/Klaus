# Research Audit — 2026-08-05T1100Z

**STALL (day 12) — ABORT: `system_status.txt` shows `failed unknown` (not active). Owner-disabled daily/liveness timers; loop WEEKLY-ONLY since 2026-07-26 EVOLVE. Analysis limited to structural facts from today's specialist reports — no fabrication on dead data.**

---

## Specialist Reports

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-08-05T07:03Z | ABORT — systemd failed day 12; no fills; all band/maker/STWA paths disabled |
| calib_monitor_report.md | 2026-08-05T08:20Z | ABORT — data-mirror read failure (probe couldn't find live data files); DISPERSION GAUGE unavailable |
| gatekeeper_report.md | 2026-08-05 | ABORT — STALL day 16; band dark day 30; **capital $0.41 below ruin_floor** |
| pnl_ledger_report.md | 2026-08-04T23:37Z | STALL — 16 consecutive zero-fill days; capital $88.750373 unchanged |

All four reports within 36h window. No raw-mirror fallback required — facts drawn directly from reports.

Note: calib_monitor failed to read data-mirror (reported branch as stale/empty); the snapshot IS fresh (2026-08-05T10:20:16Z, <6h). Calib monitor likely had a path/ref configuration error. DISPERSION GAUGE last known value: **0.781** (S3 day 24, carried from 2026-07-26). No weather-band trigger update possible this run.

---

## Critical Structural Facts

### 1. Capital below ruin_floor — mechanical block on all band paths

Capital: **$88.750373** | Engine ruin_floor: **$89.16** | Gap: **−$0.41**

Per gatekeeper_report: "All band paths mechanically blocked." This is harder than the system-down blocker — even a service restart cannot arm any band engine at current equity. The ruin_floor check runs before any market scan.

Note: the $88.75 figure includes $67.25 owner-manual injections (BTC-updown round trips 2026-07-24/25, CLOB-verified). Loop realized $0.00 since 2026-07-06 (BAND_LIVE=False) and $0.00 in updown since 2026-07-19 (UPDOWN_STOP).

### 2. Band dark — day 30

BAND_LIVE=False since 2026-07-06T22:08Z per EVOLVE wind-down (equity $108.35 < 50%·30d-HW $222.90). Zero band resolutions in 30 days. All band gate clocks (G1, G2a/b/c, G7) paused indefinitely. No data accruing.

### 3. Winner's curse confirmed (G3) — sim figures are upper bounds only

Filled ROI: **−75.8%** vs sim +7.6% (n=75, CI=[−75.0%, −34.2%]). The adverse-selection gap between simulation and realized is structural. Any ROI estimate for G1 (+4.0%†) or G7 (+11.5%†) should be read as upper bounds, not edge estimates. The dagger is load-bearing.

### 4. UPDOWN path permanently closed

G8 REJECTED at n=127 (WR 0.9528 < BE 0.9651, CI-lo 0.9008, sim −$8.88). Graveyard #15. UPDOWN_STOP permanent. No re-enable instrument exists. Rescue strata (margin_strata, t_left dead-zone, eth clean-cell) all broke out-of-sample. Inverse probe (divergence_fade) killed same run (graveyard #16). Class closed.

### 5. Gate ledger snapshot (no accrual since 2026-07-24)

| Gate | n | WR | Status |
|---|---|---|---|
| G1 BAND_YES | 934 | 15.3% | AMBIGUOUS (sim UB only; band dark) |
| G2a BAND_NO d1 | 115 | 68.7% | AMBIGUOUS (NO disabled; winner's curse unresolved) |
| G2b/c PAIR_FAV | 9 | — | COLLECTING (n<<40; band dark) |
| G3 FILLED-vs-FIRED | 75 | 17.3% filled | WATCH_ITEM — adverse selection confirmed |
| G5 THERMO_MAKER | 125 | — | REJECTED (human directive) |
| G6 M1_BETA_LOCKOUT | 31 | 74.2% | REJECTED (human directive) |
| G7 SUM_POSTED | 382 | — | AMBIGUOUS (sim UB only; band dark) |
| G8 UPDOWN_CROSSING | 127 | 95.3% | REJECTED — graveyard #15 |

---

## 1. Primary Bottleneck

**Capital $0.41 below ruin_floor ($88.75 vs $89.16) — mechanical block preceding all other analysis.**

Rank: equity deployed > system. Even if the system restarts today, zero capital can be deployed to any band path. The compounding formula (ROI/turn × turns/day × equity deployed) evaluates to zero at every factor simultaneously — system down (turns/day=0), band dark (equity deployed=0), ruin_floor breached (even if 1 and 2 were fixed). This is the tightest constraint.

---

## 2. Existing-System Optimization Signals

**No optimization signals available.** No fills in 16 days. All specialist reports ABORT/STALL. Band dark day 30. Calib monitor failed. Winner's curse (G3) means even hypothetical resumed-band performance estimates are upper bounds with CI crossing zero.

There is nothing in today's reports that implies an over-restrictive cap or idle cash that could be unlocked without owner action first. The system is not throttling itself — it is correctly blocked by capital and service state.

---

## 3. Gate Pipeline Review

No gates are READY. No gates are newly REJECTED this run. All gate ETA clocks paused (band dark + system failed).

G2b/c PAIR_FAV at n=9 are the only gates technically COLLECTING, but accrual rate is zero while BAND_LIVE=False. ETA: indefinite.

Accelerating accumulation without degrading expectancy is impossible while the system is down and band is dark. Breadth expansion is inert.

---

## 4. Assumption Attack

### A. Dispersion premium persists
**Status: UNVERIFIABLE.** Calib monitor failed; DISPERSION GAUGE last reading 0.781 (2026-07-26, S3 day 24 — 10 days stale). The 2of5 trigger for band re-arm was NOT met on the last monitored window (07-18..23). Cannot assess whether dispersion has recovered, decayed further, or crossed the band trigger threshold during the 10-day gap. **Risk: band could meet trigger and we wouldn't know.**

### B. Fills are not adversely selected
**THREATENED.** G3 (n=75, CI=[−75%, −34.2%]) is the clearest falsification of this assumption in the dataset. Filled ROI −75.8% vs simulation +7.6%. The adverse selection is structural — our limit orders are filled when the market moves against us. This assumption must be treated as false until a structural fix is validated.

### C. Recycle velocity scales
**UNTESTABLE.** RECYCLE099 requires live band posts to generate exit flow. Band dark day 30 → zero recycle events → velocity cannot be measured. Assumption neither supported nor threatened — data collection halted.

---

## 5. Market Intelligence (day-of-month 5 mod 3 = 2 — Platform Mechanics)

No live access to docs.polymarket.com or announcements this run (sandbox environment, no outbound fetch). Calib monitor also failed external reads. Carrying forward last known: fee schedule and maker-rebate structure unchanged as of 2026-07-26 EVOLVE. No delta to report. **Flag for owner: 10 days of platform changes unmonitored.**

---

## 6. Experiments

_Standard protocol: three experiments, cheap/fast/falsifiable. All deferred — with system dead, band dark, and no accrual, no experiment can be run or measured. Carrying null entry per ANTI-SYCOPHANCY rule: a null day with no viable experiments is valid output._

**EXP-A (deferred): Dispersion gauge recovery check**
Hypothesis: disp_ratio has recovered to ≥1.10 in ≥2 of the 5 cities since 2026-07-23, meeting band trigger.
Data needed: calib_monitor running with correct data-mirror path.
Time: 1 run. Cost: near-zero. Success metric: disp_ratio reading by city, trigger assessment.
Decision-if-yes: band trigger met → adds pressure to restart decision. Decision-if-no: band remains dark regardless of service state.
**Blocked by: calib_monitor path error (fix first) + system down.**

**EXP-B (deferred): Ruin_floor threshold review**
Hypothesis: ruin_floor $89.16 is a derived constant (e.g., HWM-based) that will drift as time passes with no trades — it may already be ≤$88.75 or can be amended.
Data needed: inspect stwa_engine.py ruin_floor derivation.
Time: 10 min read. Cost: zero. Success metric: confirm whether floor is static or dynamic; if dynamic, current value.
Decision-if-yes (static $89.16): $0.42 injection required OR charter amendment (7d + second reading). Decision-if-no (dynamic, already ≤$88.75): band paths unblocked on capital dimension on restart.
**Blocked by: sandbox cannot read VPS source; owner can check directly.**

**EXP-C (deferred): calib_monitor path fix**
Hypothesis: calib_monitor is reading a stale/wrong ref for data-mirror (it reported branch as empty when snapshot was fresh at 10:20 UTC).
Data needed: calib_monitor script path config.
Time: 15 min. Cost: zero. Success metric: calib_monitor successfully reads today's disp_ratio.
Decision-if-yes: dispersion gauge restored, market intelligence resumes. Decision-if-no: deeper data-mirror config issue.
**Blocked by: sandbox read-only; owner fix on VPS.**

---

## 7. Single Best Action

**Check whether ruin_floor is static or dynamic (EXP-B) — 10-minute read on the VPS.**

Sourcing from gatekeeper_report (capital $88.75 < ruin_floor $89.16, all band paths mechanically blocked).

Rationale: The $0.41 gap is tiny. If ruin_floor is a dynamic/HWM-derived constant that has already drifted below $88.75 (10+ days of no trades with no HWM updates), the capital block may already be cleared — and restart becomes the single unblocking action. If ruin_floor is hardcoded at $89.16, a $0.42 injection is the minimum viable unlock. Either outcome is a binary decision node that costs 10 minutes and determines whether service restart alone is sufficient.

Concrete first step: `SSH 45.85.251.173 → grep -n ruin_floor strategy/stwa_engine.py`

---

## PROPOSED ACTIONS (human review)

1. **EXP-B: Check ruin_floor derivation** (10 min, SSH) — determines whether $0.42 injection is needed or restart alone suffices.
2. **Fix calib_monitor data-mirror path** — dispersion gauge has been dark 10 days; band trigger unmonitorable.
3. **If restarting**: resolve capital block first (injection or ruin_floor confirmed dynamic), then `systemctl start klaus`. No code changes required for restart.
4. **If not restarting**: no action needed; all gates frozen, zero burn rate, next weekly 2026-08-09.

_No strategy code or gate changes implemented. All items above require human decision._
