# PnL Ledger — 2026-07-25 (STALL, day 2)

**ABORT: `system_status.txt` missing `'klaus systemd: active'` — status: `failed unknown`. Two consecutive stall days (Jul-24, Jul-25). Full pipeline skipped per protocol.**

> Bot service FAILED for second consecutive day. data-mirror timer still running independently (snapshot age 8 min at run time). All trading paths were already disarmed. Capital unchanged. G8 kill-formalization expected at n≥100 today — SSH required to confirm count and diagnose service failure.

---

## Operational Snapshot

| Field | Value |
|---|---|
| Snapshot age | **8 min** (23:29:16 UTC) — fresh |
| `klaus systemd` | **FAILED/UNKNOWN** (day 2; last active 2026-07-24T10:09Z) |
| data-mirror timer | Running (independent; flb_screener mtime 23:27Z) |
| Capital | **$21.495442** (bankroll.json saved_ts 1784887763; unchanged since Jul-23 CLOB verify) |
| Open positions | 0 |
| BAND_LIVE | False (disarmed Jul-6) |
| BAND_NO | Disabled Jul-2 |
| STWA paths | All disabled |
| UPDOWN_STOP | Active |
| Maker resting | {} (no resting orders) |
| G8 gate | KILL-LOCKED — n=88 (84W/4L) at Jul-23 evening; n≥100 forecast for Jul-25 |
| Zero-fill streak | **Day 6** |
| Cum. expected rebate | $3.917 upper bound (no new fills since BAND_LIVE disabled Jul-6) |

---

## Why No Full Report

Protocol: abort if `system_status.txt` missing `'klaus systemd: active'`. File shows `failed\nunknown`. This is the second consecutive stall day. Full P&L pipeline skipped to avoid false attribution with stale trading state.

## Known State (from prior ledger Jul-24 + bankroll.json)

- Capital $21.495442 — CLOB-verified Jul-23 22:08 UTC; bankroll.json confirms unchanged.
- All paths disarmed before service failure. Zero fills possible regardless of bot status.
- P&L delta: **$0.00**. Unexplained: **$0.00**. No attributed items.
- G8 at n=88 on Jul-23 evening, accruing ~7/day → n≥100 expected today Jul-25. Kill formalization is imminent or already crossed. Confirming requires SSH or the next EVOLVE commit.
- FLB screener still logging (947k rows, mtime 23:27Z) — background scraper is alive; only the bot trading service is down.

## Actions Required

1. **SSH to VPS** — `journalctl -u klaus -n 100` to see why the service failed. Started 2026-07-24T10:09Z, failed at unknown time. Likely: Python startup exception, OOM, or systemd crash.
2. **Confirm G8 n-count** — if n≥100 and WR still below BE 0.9649, kill formally applies. No restart without owner decision.
3. **Verify pUSD rebate receipt** — cumulative expected $3.917 > $1 minimum accrual threshold. Check Polymarket wallet for pUSD deposits (payouts land daily).
4. **No capital risk today** — all paths disarmed; service failure changes nothing about deployed capital ($0 deployed).

---
*Generated 2026-07-25T23:37 UTC by PnL Ledger agent (STALL protocol, day 2)*
