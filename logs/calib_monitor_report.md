# Calib Monitor Report — 2026-07-31

**STALL — systemd failed/unknown. Pipeline aborted. Day 8 consecutive abort.**

All metrics carried from last computed run 2026-07-24. No fresh pricer data processed.

---

## 0. ABORT CONDITION

`system_status.txt` contains `failed unknown` — does NOT contain `klaus systemd: active`.
Bot last active: 2026-07-24T10:09:19 UTC (~166h dead as of snapshot time 2026-07-31T08:00:46Z).
Owner-directed shutdown 2026-07-24; daily+liveness timers disabled; loop weekly-only.
Snapshot: 2026-07-31T08:00:46Z (fresh, < 1h old). Data mirror is updating; service is not.

Shadow directories contain only `badatmath_watch.jsonl` for 2026-07-26 through 2026-07-30.
No `stwa_pricer_eval_s50.jsonl` or `band_struct_lite.jsonl` files found — no pricer data
has been generated since the system went down.

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
Shadow files: only badatmath_watch.jsonl present for 07-26 through 07-30.
No early-warning computation possible.

---

## 3. DISPERSION GAUGE ⚠️ ALERT CARRIED — CRITICAL

**7d median implied/realized width ratio = 0.781** (threshold: >1.10)
**THE DISPERSION EDGE IS INVERTED. Day 29 consecutive (estimate).**

The band harvests the premium that market-implied dispersion exceeds true dispersion.
At ratio=0.781, the market is pricing LESS spread than actually resolves — the edge is not merely
compressing, it is running backwards. The band cannot profit in this regime.

| Region | disp_ratio7 | Status |
|---|---|---|
| EU | 0.789 | INVERTED (<1.0) |
| Asia | 0.743 | INVERTED (<1.0) |
| US/Other | 0.789 | INVERTED (<1.0) |

All three regions sub-1.0. Daily trend (last computed window 07-18..07-23):

| Date | ratio |
|---|---|
| 2026-07-18 | 0.485 |
| 2026-07-19 | 0.925 |
| 2026-07-20 | 0.779 |
| 2026-07-21 | 0.783 |
| 2026-07-22 | 0.851 |
| 2026-07-23 | 0.762 |

0/6 days above threshold in last computed window. 07-24 through 07-31 not computed (system down).
No trend improvement to report. Alert persists at decision-grade n~105.

BAND_LIVE=False since 2026-07-06 (day 25 dark). The live halt predates this monitor
but the dispersion inversion is an independent confirmation the halt was correct.

---

## 4. ISOTONIC STALENESS ⚠️ ALERT CARRIED

| Item | Value |
|---|---|
| Deployed refit date | 2026-06-06T22:27:08Z (~55d stale) |
| Candidate refit date | 2026-07-23T09:30:44Z (~8d old) |
| Max absolute diff | 0.1684 |
| Material diffs >0.05 | 2 |
| OOS verdict | brier_cal (0.0638) >= brier_raw (0.0637) — no calibration value added |

Material tail diffs (carried):
- grid 0.95: +0.0552 (0.3822 → 0.4374)
- grid 1.0: +0.1684 (0.6316 → 0.8000) — both push high tail upward

Promotion NOT recommended. OOS brier is not better than raw. Human review required.
Live-refit cron status: unknown (system down since 07-24).

---

## 5. STATE TRANSITION

| Field | 07-30 | 07-31 | Transition |
|---|---|---|---|
| pipeline_status | ABORTED | ABORTED | day 7 → day 8 consecutive abort |
| system_alive | false | false | systemd still failed/unknown |
| disp_inversion_days | 28 (est) | 29 (est) | +1, no reversal |
| BAND_LIVE | False | False | day 24 → day 25 dark |
| isotonic deployed age | ~54d | ~55d | +1d stale |
| bot_dead_hours | ~142h | ~166h | +24h |

---

## ALERTS

**[SYSTEM]** `## klaus systemd: failed/unknown` — pipeline aborted. Snapshot fresh (2026-07-31T08:00:46Z, < 1h old). Bot last active: 2026-07-24T10:09:19 UTC (~166h / ~7 days dead). Owner-directed shutdown; daily+liveness timers disabled. Day 8 consecutive abort.

**[S3 CARRIED — PRE-REGISTERED]** `disp_ratio7 = 0.781 < 1.10` — INVERTED DISPERSION EDGE — day 29 consecutive (estimate) — decision-grade n~105 — all 3 regions below 1.0 — 0/6 days above threshold in last computed window (07-18..07-23). Fresh data unavailable; alert persists.

**[S4 CARRIED — PRE-REGISTERED]** Isotonic deployed ~55d stale (2026-06-06); candidate 2026-07-23 with 2 material tail diffs (grid 0.95: +0.055, grid 1.0: +0.168); OOS brier_cal >= brier_raw; human review required before any promotion.
