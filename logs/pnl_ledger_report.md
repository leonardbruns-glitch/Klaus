# Klaus PnL Ledger — 2026-07-28

**STALL (day 5) — `system_status.txt` shows `failed/unknown`, not `active`. Pipeline exited after abort check.**

---

## Abort Summary

| field | value |
|---|---|
| snapshot_ts | 2026-07-28T23:30:14Z (7 min old — FRESH) |
| bot service | **FAILED** — last active 2026-07-24T10:09:19Z (day 5 of failure) |
| capital | $88.750373 (CLOB-exact; unchanged from yesterday) |
| daily_start_capital | $88.750373 (bankroll.json matches) |
| day PnL | $0.00 |
| fills today | 0 |
| open positions | 0 |
| shadow dir (2026-07-28) | absent — confirms 0 fills |
| consecutive zero-fill days | **9** |
| live paths | **NONE** (BAND_LIVE=False, BAND_NO=DISABLED, STWA=DISABLED, G8=FORMALLY KILLED) |

---

## Kill-Switch Proximity

| check | value | status |
|---|---|---|
| Day PnL vs -$10 halt | $0.00 | CLEAR |
| Capital vs $75 weekly floor | $88.750 | CLEAR |
| Capital vs $50 ruin floor | $88.750 | CLEAR |
| G8 gate | WR 0.9528 < BE 0.9651 (n=127) | **FORMALLY KILLED** (EVOLVE 2026-07-26) |
| BAND_LIVE | False | DISARMED Jul-6 |
| BAND_NO | False | DISABLED Jul-2 |
| STWA_REGULAR | False | DISABLED |
| UPDOWN_STOP | ACTIVE | KILLED |
| All live paths | NONE | LOOP WEEKLY-ONLY |

CAVEAT: WR/PF floors were specified for taker era; kill-switch re-derivation pending. No action warranted on WR alone — there are no firing paths to halt.

---

## Expected Maker Rebates

Cumulative expected (upper bound): **$3.917** — unchanged from yesterday. No new fills since BAND_LIVE disabled Jul-6.

**ACTION REQUIRED for owner:** Cumulative exceeds $1 min accrual threshold. Verify pUSD receipt in Polymarket wallet. No payout has ever been recorded in any session.

---

## Unexplained PnL

$0.00 — capital flat at $88.750373 vs prior report $88.750373. No delta, nothing to explain.

---

## Day Verdict

**STALL (day 5)** — equity did not compound (0%). Bot service FAILED for 5 consecutive days. 9 consecutive zero-fill days. No live paths remain. SSH to VPS required to diagnose systemd failure before any restart.
