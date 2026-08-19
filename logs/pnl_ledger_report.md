# Klaus PnL Ledger — 2026-08-19 (STALL ABORT)

**Generated:** 2026-08-19T23:37 UTC  
**Status:** ABORTED — data mirror stale, service offline

---

## ABORT CONDITION MET

| Check | Value | Threshold | Result |
|---|---|---|---|
| Snapshot age | 84 hours (last: 2026-08-16T11:26:01Z) | ≤ 6h | **FAIL** |
| Klaus service | `failed unknown` | `active` | **FAIL** |

Both abort conditions are triggered simultaneously. The `data-mirror` timer pushes every 15 minutes; a 3-day gap indicates either the timer service died or the VPS is unreachable entirely. No P&L attribution, compounding score, or kill-switch proximity can be computed without a current snapshot.

---

## LAST KNOWN STATE (from stale snapshot)

| Field | Value | As-of |
|---|---|---|
| Capital | $88.75 | 2026-08-16T11:26:01Z |
| trades.jsonl rows | 8,228 | 2026-08-16T11:26:01Z |
| Klaus HEAD | ddbcecdd1 | 2026-08-16T11:26:01Z |

**Capital delta since last PnL ledger run is UNKNOWN** — 84h of trades unattributed. Do not assume ruin or windfall; manual flows are also possible.

---

## RECOMMENDED ACTIONS

1. `ssh <vps>` — verify VPS is reachable
2. `systemctl status klaus` — check if service crashed or was stopped
3. `systemctl status klaus_data_mirror.timer` — check if mirror timer is alive
4. `journalctl -u klaus -n 100` — inspect crash reason if stopped
5. If both services dead: `systemctl start klaus_data_mirror.timer && systemctl start klaus` after verifying capital is within safe bounds
6. Do **not** restart trading without first reading current capital; the bot's internal bankroll state may be stale

---

*Sections 1–5 (P&L Explain, Compounding Scoreboard, Maker Rebates, Kill-Switch Proximity, Day Verdict) are omitted — data prerequisite not met.*
