# Klaus Execution Audit — 2026-06-26T07:13Z

**ABORT: Klaus systemd service is `failed` — bot has been down for ~25h (last active 2026-06-24T08:04:37 UTC; crashed ~2026-06-25T06:08 UTC per prior audit). Snapshot is fresh (2 min). No new fill, queue, or markout data to audit.**

---

## Status

| Field | Value |
|---|---|
| Snapshot age | 2 min (fresh; data-mirror timer running) |
| Bot service | **failed** (day 2 of outage) |
| Last systemd ActiveEnterTimestamp | 2026-06-24T08:04:37 UTC |
| Estimated crash time | 2026-06-25T06:08 UTC (per 2026-06-25 audit) |
| Outage duration | ~25h |
| Bankroll | $198.28 capital |
| Open positions | 0 |
| VPS HEAD commit | `d156804a2` feat(BAND): sigma-reality verdict + badatmath-YES forensic |

## Prior Crash Context (from 2026-06-25 audit, still unresolved)

Last log entries before silence were two `[USER-WS] UNTRACKED FILL` lines on `token=9519811215283860` side=BUY price=0.34 size=18.42. No ERROR/Traceback in final 200 log lines — silent crash, suspected in the `d156804a2` co-fill pairing / sigma-reality verdict path triggered by an untracked fill event.

## What Has NOT Changed

- Bot not restarted in the ~25h since yesterday's ABORT report
- No new fills (positions=0, fill tape has advanced 0 rows since 2026-06-25T06:08)
- `BAND_LIVE=True` flag still set; bot is armed but not running

## ALERTS

None pre-registered fired (full audit aborted — two consecutive ABORT cycles indicate persistent outage requiring manual intervention).

---

**3-line summary:**  
Fills/day: 0 (bot down, no fills since 2026-06-25T06:08 UTC). NO-share: N/A. **Binding constraint: bot has been failed for ~25h; restart and root-cause `d156804a2` UNTRACKED FILL crash path urgently.**
