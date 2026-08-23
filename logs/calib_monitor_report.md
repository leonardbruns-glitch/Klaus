# Calibration & Dispersion Monitor — 2026-08-23

**STALLED — data-mirror has not pushed since 2026-08-16T11:26:01Z (7 days dead). Cannot compute any metrics. VPS data-mirror service requires immediate investigation.**

## Abort Condition

| Check | Result |
|---|---|
| Last data-mirror commit | `2026-08-16T11:26:01Z` |
| Age at report time | ~167 hours |
| Threshold | 6 hours |
| Verdict | **ABORT — stale by 161 hours** |

## What This Means

The VPS running Klaus has not pushed a snapshot to the `data-mirror` branch in 7 days. All five pipeline sections (Settled Lane, Proxy Lane, Dispersion Gauge, Isotonic Staleness, State) require live data from this branch and cannot run.

Possible causes:
- Klaus systemd service crashed or was stopped
- VPS is unreachable / rebooted without auto-restart
- data-mirror push cron failed (auth, disk, or network issue)
- Repository access revoked

## Required Action

SSH to the VPS and check:
1. `systemctl status klaus` — is the service running?
2. `journalctl -u klaus -n 100` — any crash logs?
3. `git -C /path/to/Klaus push origin data-mirror` — can it push?

No calibration assessment possible until the mirror resumes. This monitor will re-run on its next scheduled firing; if data-mirror is still stale, it will abort again.

## ALERTS

- **[OPERATIONAL]** data-mirror dead 7 days — no model or dispersion data available. Klaus may be running blind or not running at all.
