# Calib Monitor Report — 2026-08-01

**STALL — systemd failed/unknown. Pipeline aborted. Day 9 consecutive abort.**

All metrics carried from last computed run 2026-07-24. No fresh pricer data processed.

---

## 0. ABORT CONDITION

`system_status.txt` contains `failed unknown` — does NOT contain `klaus systemd: active`.
Bot last active: 2026-07-24T10:09:19 UTC (~190h / ~7.9 days dead as of snapshot 2026-08-01T08:07:05Z).
Owner-directed shutdown 2026-07-24; daily+liveness timers disabled; loop weekly-only.
Snapshot: 2026-08-01T08:07:05Z (fresh, ~8h old — within 6h abort threshold as of run time).

Shadow directories checked:
- 2026-07-27 through 2026-07-31: `badatmath_watch.jsonl` only — no pricer files
- 2026-08-01: no directory (system not running)
- Root shadow: `badatmath_watch.jsonl`, `count_lock.jsonl`, `minmax_coherence.jsonl` — no pricer

No `stwa_pricer_eval_s50.jsonl` or `band_struct_lite.jsonl` found for any day since 07-24.
No pricer data has been generated since the system went down.

---

## 1. SETTLED LANE (carried — no new resolution joins possible)

| Metric | Value | Source | Threshold | Status |
|---|---|---|---|---|
| 7d Brier | 0.0548 | CARRIED 07-24 | >0.15 alert | OK |
| 7d ECE | 0.0277 | CARRIED 07-24 | >0.05 alert | OK |
| 7d rank-rho | 0.426 | CARRIED 07-24 | <+0.15 alert | OK |

n_carry = 33,363 resolved rows. No new settlements processed (system down).
No S1 alerts fired.

---

## 2. PROXY LANE (carried — no new pricer rows)

No p_cal vs market-mid divergence data available. System down since 07-24.
No shadow pricer files for any day from 07-27 through 08-01.
No early-warning computation possible.

---

## 3. DISPERSION GAUGE ⚠️ ALERT CARRIED — CRITICAL

**7d median implied/realized width ratio = 0.781** (threshold: >1.10)
**THE DISPERSION EDGE IS INVERTED. Day 30 consecutive (estimate).**

The band harvests the premium that market-implied dispersion exceeds true dispersion.
At ratio=0.781, the market is pricing LESS spread than actually resolves. The edge is not
merely compressing — it is running backwards. The band cannot profit in this regime.

| Region | disp_ratio7 | Status |
|---|---|---|
| EU | 0.789 | INVERTED (<1.0) |
| Asia | 0.743 | INVERTED (<1.0) |
| US/Other | 0.789 | INVERTED (<1.0) |

All three regions below 1.0. Daily trend (last computed window 07-18..07-23):

| Date | ratio |
|---|---|
| 2026-07-18 | 0.485 |
| 2026-07-19 | 0.925 |
| 2026-07-20 | 0.779 |
| 2026-07-21 | 0.783 |
| 2026-07-22 | 0.851 |
| 2026-07-23 | 0.762 |

0/6 days above threshold in last computed window. 07-24 through 08-01 not computed (system down).
No trend improvement to report. Alert persists at decision-grade n~105 (from 07-24 compute).

BAND_LIVE=False since 2026-07-06 (day 26 dark). The live halt predates this monitor
but the dispersion inversion is an independent confirmation the halt was correct.
The inversion pre-existed the halt and remains unresolved.

---

## 4. ISOTONIC STALENESS ⚠️ ALERT CARRIED

| Item | Value |
|---|---|
| Deployed refit date | 2026-06-06T22:27:08Z (~55d stale) |
| Candidate refit date | 2026-07-23T09:30:44Z (~9d old) |
| Max absolute diff | 0.1684 |
| Material diffs >0.05 | 2 |
| OOS verdict | brier_cal (0.0638) >= brier_raw (0.0637) — no calibration value added |

Deployed vs candidate diff (full grid — candidate minus deployed):

| grid | deployed | candidate | diff |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0042 | +0.004 |
| 0.05 | 0.0695 | 0.0708 | +0.001 |
| 0.10 | 0.1340 | 0.1255 | −0.009 |
| 0.15 | 0.1828 | 0.1831 | +0.000 |
| 0.20 | 0.2663 | 0.2697 | +0.003 |
| 0.25 | 0.3557 | 0.3373 | −0.018 |
| 0.30–0.85 | 0.3801 | 0.3748 | −0.005 |
| 0.90 | 0.3801 | 0.3919 | +0.012 |
| **0.95** | **0.3822** | **0.4374** | **+0.055 ← MATERIAL** |
| **1.00** | **0.6316** | **0.8000** | **+0.168 ← MATERIAL** |

Both material diffs push the high tail upward (candidate inflates p_cal at 0.95 and 1.0).
Promotion NOT recommended. OOS brier not better than raw. Human review required.
Live-refit cron status: unknown (system down since 07-24; cron presumably also dead).

---

## 5. STATE TRANSITION

| Field | 07-31 | 08-01 | Transition |
|---|---|---|---|
| pipeline_status | ABORTED | ABORTED | day 8 → day 9 consecutive abort |
| system_alive | false | false | systemd still failed/unknown |
| disp_inversion_days | 29 (est) | 30 (est) | +1, no reversal |
| BAND_LIVE | False | False | day 25 → day 26 dark |
| isotonic deployed age | ~55d | ~55d | unchanged (no new refit) |
| isotonic candidate age | ~8d | ~9d | +1d |
| bot_dead_hours | ~166h | ~190h | +24h |

No transitions in alert status. All 3 alerts persist unchanged.

---

## ALERTS

**[SYSTEM]** `## klaus systemd: failed/unknown` — pipeline aborted. Snapshot fresh (2026-08-01T08:07:05Z). Bot last active: 2026-07-24T10:09:19 UTC (~190h / ~7.9 days dead). Owner-directed shutdown; daily+liveness timers disabled; loop weekly-only. Day 9 consecutive abort.

**[S3 CARRIED — PRE-REGISTERED]** `disp_ratio7 = 0.781 < 1.10` — INVERTED DISPERSION EDGE — day 30 consecutive (estimate) — decision-grade n~105 — all 3 regions below 1.0 — 0/6 days above threshold in last computed window (07-18..07-23). Fresh data unavailable; alert persists.

**[S4 CARRIED — PRE-REGISTERED]** Isotonic deployed ~55d stale (2026-06-06); candidate 2026-07-23 (~9d old) with 2 material tail diffs (grid 0.95: +0.055, grid 1.0: +0.168); OOS brier_cal >= brier_raw; human review required before any promotion.
