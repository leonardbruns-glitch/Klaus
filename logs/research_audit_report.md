# Klaus Research Audit — 2026-07-28T10:20Z

**STALL (day 5)** — `system_status.txt: failed/unknown` (missing `'klaus systemd: active'`). Pre-registered abort condition met. No fabricated analysis beyond this line. See 2026-07-27T10:30Z report for last full seven-section audit; all sections stand unchanged.

---

## Status Snapshot (from today's fresh mirror, 2026-07-28T10:16Z)

| Field | Value | Delta vs 2026-07-27 |
|---|---|---|
| Stall day | **5** | +1 |
| Service last active | 2026-07-24T10:09Z | — |
| Capital | **$88.750373** ($21.50 CLOB + $67.25 owner on-chain) | $0.00 |
| Open positions | 0 | 0 |
| Zero-fill streak | **Day 8** | +1 |
| `BAND_LIVE` | False (day 22 dark) | — |
| `BAND_NO_ENABLED` | False | — |
| `BAND_YES_LIVE_MIN_DOUT` | 9 (standalone YES paused) | — |
| G8 UPDOWN_CROSSING | **REJECTED** — graveyard #15 (EVOLVE 07-26 `ddbcecdd1`) | — |
| disp_ratio S3 | **0.781** (day 26 of inversion) | +1 day |
| Isotonic staleness S4 | **~52d** | +1d |
| Capital vs ruin_floor | $88.75 vs $89.16 — **$0.41 below** (band mechanically blocked) | $0.00 |
| Weekly kill-switch floor | CLEAR — $88.75 > $75 | — |
| Ruin kill-switch floor | CLEAR — $88.75 > $50 | — |
| Live paths | **NONE** | — |

---

## Specialist Reports — 2026-07-28 (all ABORT/STALL, all within 36h window)

| Report | Timestamp | Status | Key carry-forward |
|---|---|---|---|
| `exec_audit_report.md` | 07:13Z today (fresh) | **ABORT day 5** | No fills, no resting orders, no execution data producible |
| `calib_monitor_report.md` | 08:07Z today (fresh) | **STALL** | brier7=0.055 disp_ratio=0.781 CARRIED; S3 day ~26; S4 isotonic ~52d stale |
| `gatekeeper_report.md` | ~09:00Z today (fresh) | **STALL run 8** | All gates +0; G8 kill confirmed; no transitions; capital still $0.41 below ruin_floor |
| `pnl_ledger_report.md` | 23:37Z 2026-07-27 (35h, within window) | **ABORT** | day=$0.00; turns=0; zero-fill streak day 8; pUSD rebate est. $3.917 UB unchecked |

---

## State Changes vs 2026-07-27T10:30Z

**None.** +0 gate transitions. +0 fill events. +0 capital change. All four specialists returned ABORT/STALL. disp_ratio and isotonic staleness each advanced by one day. G8 kill remains the only recent transition (EVOLVE 07-26, already captured yesterday).

---

## Sections 1–7 Status

All seven sections of the 2026-07-27T10:30Z report remain authoritative and unrepeated here per abort protocol. In brief:

1. **Bottleneck**: Equity deployed = 0% (system offline, all paths dark). Compounding = 0.
2. **Optimization**: Zero action surface (no fills, no queue, no book). Only offline levers: isotonic refit + G3 root cause.
3. **Gate pipeline**: No gate READY. G3 winner's curse blocks G1/G7 sim-CI. G5/G6 REJECTED (no reconsider without human). G2b/G2c inert at 9 live fills (band dark).
4. **Assumption attack**: Dispersion premium THREATENED (S3 day 26); fills adversely selected CONFIRMED (G3 CI entirely negative); recycle MOOT (0 open positions).
5. **Market intelligence** (competitor posture, day mod 3 = 0): badatmath_watch.jsonl unavailable from this environment (git fetch timed out); no fresh delta. Last known: band structure stable; Klaus absent from market 21 days.
6. **Experiments**: A (isotonic refit, VPS, 2h, zero cost), B (G3 winner's curse subgroup analysis, offline, 1d, zero cost), C (PAIR_FAV markout check, shadow data, 2h, zero cost) — all open, none started.
7. **Single best action**: Experiment A — isotonic recalibration. The disp_ratio question gates everything downstream. Concrete first step: `grep -r 'isotonic' analytics/ --include='*.py' -l` on VPS in next EVOLVE session to locate refit entry point.

---

## One Open Admin Item (from pnl_ledger)

**pUSD rebate check**: Cumulative expected rebate $3.917 upper bound (unchanged since Jul-6 wind-down). Owner to verify pUSD deposits in Polymarket wallet — may be unclaimed. ≥$1 accrual threshold likely met. No code action; owner wallet check only.

---

## PROPOSED ACTIONS (human review)

*Unchanged from 2026-07-27T10:30Z. Reprinted for continuity:*

1. **Isotonic recalibration** (Experiment A) — `analytics/isotonic_fit.py` next EVOLVE session. Required prereq before any `BAND_LIVE` re-arm cost-benefit discussion. Zero capital at risk.
2. **G3 winner's curse subgroup analysis** (Experiment B) — 1d offline task on `trades.jsonl`. Determines whether taker-band or maker-only is the correct long-run architecture. Gating prereq for G1/G7 re-enable.
3. **Capital buffer injection** — ≥$0.50 on-chain to clear ruin_floor ($88.75 → ≥$89.25). Low priority until isotonic question answered (mechanical blocker only, not edge question).
4. **G8 graveyard confirmation** — Administrative: confirm no residual updown certainty-taker code paths remain in live codebase. EVOLVE `ddbcecdd1` documented the kill; code audit is optional follow-up.
5. **pUSD rebate check** — Owner to verify unclaimed pUSD in Polymarket wallet (est. ≥$3.92 upper bound). No action from scheduled agents.

---

*Generated 2026-07-28T10:20Z by Research Audit agent (STALL protocol, day 5). System offline since 2026-07-24T10:09Z per owner directive (weekly-loop-only mode, EVOLVE `ddbcecdd1`). Snapshot: 2026-07-28T10:16Z (4 min old, fresh). Specialist reports all within 36h window. Next scheduled EVOLVE: est. 2026-07-31.*
