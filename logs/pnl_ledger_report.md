# PnL Ledger — 2026-08-08

**ABORT — STALL DAY 15: `system_status.txt` shows `failed/unknown`, not `active` (bot last live 2026-07-24T10:09:19Z). Capital $88.750373 — unchanged for 15 consecutive days. 20 zero-fill days. No live paths.**

*Full 5-section analysis skipped per abort protocol. System is intentionally down per owner directive 2026-07-24 ("daily+liveness timers disabled → loop WEEKLY-ONLY").*

---

## Capital & Kill-Switch Quick-Ref

| Metric | Value | Status |
|---|---|---|
| Capital 2026-08-08 | $88.750373 | Unchanged — day 15 |
| Day PnL | $0.00 | 0 fills, service down |
| Capital vs yesterday | $0.00 delta | — |
| Unexplained PnL | $0.00 | No delta to explain |
| Capital vs ruin floor ($50) | +$38.75 above | CLEAR |
| Capital vs weekly floor ($75) | +$13.75 above | CLEAR |
| Day PnL vs halt (−$10) | $0.00 | CLEAR |
| G8 gate (CROSSING) | FORMALLY KILLED | WR 0.9528 < BE 0.9651 (n=127) |
| BAND\_LIVE | False | DISARMED 2026-07-06 |
| BAND\_NO | False | DISABLED 2026-07-02 |
| STWA\_REGULAR | Disabled | — |
| All live trading paths | **NONE** | LOOP WEEKLY-ONLY |
| Bot service | **FAILED — day 15** | SSH required |
| Consecutive zero-fill days | **20** | — |

## Rebate Flag (carry-forward)

Expected maker rebate cumulative: **$3.917 upper bound** — unchanged since BAND_LIVE was disabled 2026-07-06. This exceeds the Polymarket $1 minimum accrual threshold. User should verify pUSD receipt in Polymarket wallet. No payout has been recorded in any prior session.

## Resumption Path

Per owner directive 2026-07-24: bot intentionally stopped, daily and liveness timers disabled, loop WEEKLY-ONLY. The research audit from this morning (2026-08-08T10:28Z) recommended `systemctl start klausbot` — but that audit predates confirmation that the shutdown was owner-directed. Confirm intent before restarting. SSH to VPS required for any restart.

Data-mirror timer is running and healthy: snapshot `2026-08-08T23:36:06Z` (< 1 min old at report time). CLOB open positions: 0. Trade log rows: 8228 (unchanged day 15).

*Capital composition per EVOLVE commit ddbcecdd1 2026-07-26: $21.50 CLOB liquid + $67.25 owner-manual on-chain = $88.750373 exact.*
