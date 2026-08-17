# Klaus Band Execution & Markout Audit — 2026-08-17

**ABORT: Two conditions met — analysis not performed.**

1. **Snapshot stale**: data-mirror snapshot_ts = 2026-08-16T11:26:01Z; now 2026-08-17 UTC (~24h old; threshold 6h). Data cannot be trusted as live.
2. **Service dead**: `system_status.txt` reports `failed unknown` — does not contain `active`. Bot has not fired since 2026-07-24 10:09:19 UTC (~24 days down).

No fills have occurred. Running pipeline analysis on a dead system would fabricate data.

---

*3-line summary: fills/day = N/A (system down ~24 days). NO-share = N/A. Binding constraint = VPS systemd unit in failed/unknown state; no trades, no resting quotes, no new data since 2026-07-24.*
