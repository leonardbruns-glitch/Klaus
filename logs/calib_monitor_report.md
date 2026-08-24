# Calibration & Dispersion Monitor — 2026-08-24

**STALLED — data-mirror last push 2026-08-16T11:26:01Z (~188.9h / 7.87 days stale, threshold 6h). No live pricer/band/resolution data available. Abort per pre-registered rule. Second consecutive stall report (2026-08-23 was 167h).**

## Abort Condition

| Check | Result |
|---|---|
| Last data-mirror commit | `762a6d4` — `snapshot 2026-08-16T11:26:01Z` |
| Report time (UTC) | `2026-08-24T08:22:43Z` |
| Age | ~188.9 hours (7.87 days) |
| Threshold | 6 hours |
| `system_status.txt` klaus systemd | `failed / unknown` (required: `active`) |
| Verdict | **ABORT — both gates failed** |

Snapshot deltas since prior stall report (2026-08-23):
- Data-mirror HEAD unchanged (`762a6d4`, same 2026-08-16 push). Push cron not recovered.
- Ledger context (last state_log entry 2026-07-26): owner-shutdown of `klaus` + timers on 2026-07-24 was deliberate and remains in force per charter (weekly-only loop, no auto-restart). System is in a documented stopped state, not a crash.
- SNAPSHOT.md still reports `klaus service: failed / unknown` and 0 open positions; equity $88.75 CLOB-verified as of the last mirror push.

## Pipeline Impact

All five sections require live pricer_eval, band_struct_lite, and CLOB resolution joins from windows resolved in the last 7 days. No such data exists post-2026-08-16, so:

| Section | Status |
|---|---|
| 1. Settled lane (Brier / ECE / rank-rho) | **NO DATA** — carry prior `brier7=0.0548`, `disp_ratio=0.781` from 2026-07-25 for reference only; not decision-grade. |
| 2. Proxy lane (mid-vs-p_cal divergence) | **NO DATA** |
| 3. Dispersion gauge (implied/realized width ratio) | **NO DATA** — last measured 7d median 0.781 (already below 1.10 alert threshold at last live reading; whether it has recovered is unknowable). |
| 4. Isotonic staleness | **NO DATA** — cannot compare deployed vs candidate map without live refit output. |
| 5. State transitions | Written as `null` metrics + STALLED alert. |

The 2026-07-25 reading of `disp_ratio7 = 0.781` was already an ALERT (< 1.10). Whether the dispersion premium has recovered, decayed further, or is moot (nothing trading) cannot be determined from this branch. This is the pre-registered alarm the edge rests on, and it has been dark for 189h.

## Required Action (unchanged from prior report)

Owner-side intervention required — this monitor cannot self-heal:
1. SSH to VPS (45.85.251.173 per state log) and verify `klaus_data_mirror.timer` and its service unit. Timer was not part of the 07-24 owner shutdown per ledger, so its silence is unexpected.
2. Confirm push cron auth (git credentials, disk headroom — was 72% used at last push).
3. If klaus itself is intended to remain owner-shutdown per charter, the mirror timer should still push so calibration monitoring can resume. If mirror is being kept dark deliberately, retire this monitor from the schedule until it is re-armed.

## ALERTS (pre-registered)

- **[STALLED]** data-mirror ≥ 6h old (actual 188.9h). Pipeline aborted.
- **[STALLED]** `klaus systemd` not `active` (`failed / unknown`). Second gate fired.
- Neither ALERT is a calibration verdict — they are operational gates that block calibration measurement. The last live calibration reading (2026-07-25: `disp_ratio7=0.781`) already tripped the dispersion alarm; it has neither been refuted nor re-confirmed since.

No calibration or dispersion metrics computed this run. Will re-run on next scheduled firing; if mirror is still cold, will abort again.
