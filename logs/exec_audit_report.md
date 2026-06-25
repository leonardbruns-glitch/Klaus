# Klaus Execution Audit — 2026-06-25T07:25Z

**ABORT: `system_status.txt` missing 'klaus systemd: active' — service reports `failed / unknown`. Bot is down.**

---

## Status

| Field | Value |
|---|---|
| Snapshot age | 13 min (fresh; data-mirror timer still running) |
| Bot service | **failed / unknown** |
| Last systemd active entry | Wed 2026-06-24 08:04:37 UTC (~23h ago) |
| Last log activity | 2026-06-25 06:08:38 UTC (STRUCT-BAND-Q at 06:07:31, fill at 06:08:29) |
| Likely crash window | 06:08–07:10 UTC today (~1h 2min before snapshot) |
| Bankroll | $198.28 capital |
| Open positions | 0 |
| VPS HEAD commit | d156804a2 feat(BAND): sigma-reality verdict + badatmath-YES forensic |

## Crash Context

Last two log entries before silence:

```
Jun 25 06:08:30 [USER-WS] UNTRACKED FILL: token=9519811215283860 side=BUY price=0.34 size=18.42 status=MINED trader_side=MAKER — no tracker entry, no open position
Jun 25 06:08:38 [USER-WS] UNTRACKED FILL: token=9519811215283860 side=BUY price=0.34 size=18.42 status=CONFIRMED trader_side=MAKER — no tracker entry, no open position
```

No ERROR/Traceback/CRITICAL in final 200 log lines. Crash appears silent — possible unhandled exception downstream of UNTRACKED FILL processing in the new `d156804a2` code path (sigma-reality verdict + co-fill pairing logic).

## Pre-Crash Fill Summary (observable, not audited)

| Period | Fills | Note |
|---|---|---|
| Today 2026-06-25 (pre-crash) | 9 | All NO; last: Seattle NO +$8 @ 0.66 |
| Yesterday 2026-06-24 | 47 | Last normal trading day |

## Queue Health (last cycles before crash)

STRUCT-BAND-Q snapshot (06:02–06:07 UTC):
- `books=0-1/80`, `yes_books=0/50`, `posted=0-1/cycle`
- `cash_preskip=93–125`, `queue=206–208`, `no_cands=175`, `yes_resv_skip=73–92`
- Pattern: nearly all cycles posting=0 with cash available. YES entirely absent from posts. Consistent with NO-only phase.

## ALERTS

None pre-registered fired (full audit aborted — bot must be restarted before further analysis is meaningful).

---

**3-line summary:**
Fills/day: 9 today (pre-crash, ~06:08 cutoff) vs 47 yesterday. NO-share: not computed (ABORT). **Binding constraint: bot is down — restart required immediately.**
