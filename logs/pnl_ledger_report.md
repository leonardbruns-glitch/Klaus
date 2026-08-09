# PnL Ledger — 2026-08-09

**ABORT — STALL DAY 16: `system_status.txt` shows `failed/unknown`, not `active` (bot last live 2026-07-24T10:09:19Z). Capital $88.750373 — unchanged for 16 consecutive days. 21 zero-fill days. No live paths.**

*Full 5-section analysis skipped per abort protocol. System is intentionally down per owner directive 2026-07-24 ("daily+liveness timers disabled → loop WEEKLY-ONLY").*

---

## Capital & Kill-Switch Quick-Ref

| Metric | Value | Status |
|---|---|---|
| Capital 2026-08-09 | $88.750373 | Unchanged — day 16 |
| Day PnL | $0.00 | 0 fills, service down |
| Capital delta vs yesterday | $0.00 | — |
| Unexplained PnL | $0.00 | No delta to explain |
| Capital vs ruin floor ($50) | +$38.75 above | CLEAR |
| Capital vs weekly floor ($75) | +$13.75 above | CLEAR |
| Day PnL vs halt (−$10) | $0.00 | CLEAR |
| G8 gate (CROSSING) | FORMALLY KILLED | WR 0.9528 < BE 0.9651 (n=127) |
| BAND\_LIVE | False | DISARMED 2026-07-06 |
| BAND\_NO | False | DISABLED 2026-07-02 |
| STWA\_REGULAR | Disabled | — |
| All live trading paths | **NONE** | LOOP WEEKLY-ONLY |
| Bot service | **FAILED — day 16** | SSH required |
| Consecutive zero-fill days | **21** | — |

## Rebate Flag (carry-forward)

Expected maker rebate cumulative: **$3.917 upper bound** — unchanged since BAND_LIVE was disabled 2026-07-06. Exceeds Polymarket $1 minimum accrual threshold. User should verify pUSD receipt in Polymarket wallet. No payout recorded in any prior session.

## System State

- Data-mirror timer: RUNNING and healthy. Snapshot `2026-08-09T23:27:32Z` (0.16h old at report time).
- CLOB open positions: 0.
- Trade log rows: 8228 (unchanged from yesterday; last actual trade 2026-07-19T08:02:53Z).
- bankroll.json last saved: 2026-07-31T14:35:00Z (stale — bot is down; file is data-mirror copy of on-disk state).

*Capital composition per EVOLVE commit ddbcecdd1 2026-07-26: $21.50 CLOB liquid + $67.25 owner-manual on-chain = $88.750373 exact.*
