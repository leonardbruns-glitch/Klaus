# Calibration & Dispersion Monitor — 2026-08-22

**STATUS: STALL — ABORT**

---

## Abort Condition

Data-mirror branch last snapshot: `2026-08-16T11:26:01Z`  
Age at run time: **~6 days** (threshold: 6 hours)  
Abort rule triggered: snapshot > 6h old.

## Continuity Note

This is the seventh consecutive monitoring session to abort with the same stall:
- 2026-08-22 07:11 UTC — Exec Audit ABORTED (data-mirror 6d stale)
- 2026-08-21 10:26 UTC — Research Audit STALLED (data-mirror 5d stale)
- 2026-08-21 08:16 UTC — Calib Monitor STALL (systemd-failed day 28, snapshot 5d stale)
- 2026-08-21 07:14 UTC — Exec Audit ABORT (systemd failed, snapshot 5d stale)
- 2026-08-20 10:27 UTC — Research Audit STALL (data-mirror runtime files absent)

Prior commit messages reference VPS systemd as **failed**. The data-mirror push timer has not run since 2026-08-16T11:26:01Z.

## No Data Available

No analysis can be performed without live data. Sections 1–5 of the pipeline (Settled Lane, Proxy Lane, Dispersion Gauge, Isotonic Staleness, State diff) are all blocked.

## ALERTS

No pre-registered calibration alerts can be evaluated. The absence of data is itself the operative condition.

**Action required (human):** SSH to VPS and check/restart the Klaus systemd service and data-mirror push timer. Until data-mirror resumes pushing, all monitoring routines will continue to abort.
