# PnL Ledger — 2026-07-24 (STALL)

**STALL: `klaus systemd: failed` — bot service failed as of last snapshot (23:26 UTC); started 10:09 UTC, status unknown/failed by snapshot time. Report aborted per protocol. One-line header below; full pipeline skipped.**

> Bot service FAILED (started 10:09 UTC, failed at unknown time before 23:26 UTC). data-mirror timer still running (fresh snapshot 14 min before run). All trading paths were already disarmed before failure. Capital unchanged. G8 kill-formalization (~Jul-25) now imminent — SSH verification required.

---

## Operational Snapshot (from bankroll.json + system_status.txt)

| Field | Value |
|---|---|
| Snapshot age | 13 min (23:26 UTC) — fresh |
| `klaus systemd` | **FAILED** (started 10:09 UTC) |
| data-mirror timer | Running (independent) |
| Capital | **$21.495442** (unchanged from Jul-23) |
| Open positions | 0 |
| BAND_LIVE | False (disarmed Jul-6) |
| STWA paths | All disabled |
| UPDOWN_STOP | Active |
| G8 gate | KILL-LOCKED (n=88, 84W/4L, WR 0.9545 < BE 0.9649) |
| Zero-fill streak | **Day 5** (streak from Jul-20) |
| Cum. expected rebate | $3.917 (no new fills) |

## Why No Full Report

Protocol: abort if `system_status.txt` missing `'klaus systemd: active'`. File shows `failed`. Data-mirror is fresh (13 min) but trading pipeline state is uncertain. Full P&L pipeline skipped to avoid false attribution.

## Known State (from prior ledger Jul-23)

- Capital $21.495442 — CLOB-verified Jul-23 22:08 UTC; bankroll.json confirms unchanged today.
- All paths disarmed well before today's failure. No fills were possible regardless.
- P&L delta: $0.00. Unexplained: $0.00. No new attributed items.
- G8 kill was forecast to formalize "~Jul-25 at n>=100" (~7 settlements/day). Today is Jul-24. Kill may have already crossed n=100 — confirming requires SSH or tomorrow's EVOLVE commit.

## Action Required

1. **SSH to VPS** — diagnose why `klaus.service` failed. Likely causes: Python exception at startup, OOM, or systemd crash. Check `journalctl -u klaus -n 50`.
2. **Confirm G8 n-count** — if n>=100 and WR still below BE 0.9649, kill formally applies. No restart without owner decision.
3. **Verify pUSD rebate receipt** — cumulative expected $3.917 > $1 minimum. Check Polymarket wallet for pUSD deposits.
4. **No trading action needed today** — all paths disarmed; service failure changes nothing about deployed capital.

---
*Generated 2026-07-24T23:40 UTC by PnL Ledger agent (STALL protocol)*
