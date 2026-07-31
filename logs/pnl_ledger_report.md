# PnL Ledger — 2026-07-31 — **STALL (day 7)**

**ABORT:** `system_status.txt` shows `failed / unknown` — not `active`. Protocol requires stall header only.

---

## Abort Diagnostics

| Field | Value |
|---|---|
| Snapshot timestamp | 2026-07-31T23:30:46Z |
| Snapshot age at report | ~7 min — **FRESH** (well within 6h) |
| Bot service status | **FAILED / UNKNOWN** (last active: 2026-07-24T10:09:19Z) |
| Days since last active | **7** |
| Zero-fill days consecutive | **12** |
| Trade rows in trades.jsonl | 8,228 (unchanged from prior 6 reports) |
| Capital (bankroll.json) | **$88.750373** (unchanged since EVOLVE 2026-07-26; CLOB-exact per commit ddbcecdd1) |
| Open positions | 0 |
| Resting maker orders | 0 |

---

## Live Path Status (all disarmed)

| Path | Status | Disabled since |
|---|---|---|
| STWA Regular YES/NO | DISABLED | 2026-06-05 / 2026-06-11 |
| BAND_LIVE (band taker) | DISARMED | 2026-07-06 (equity < 50% 30d-HW) |
| BAND_NO | DISABLED | 2026-07-02 (7d WR 39.2%) |
| G8 certainty-taker | **FORMALLY KILLED** | 2026-07-26 (WR 0.9528 < BE 0.9651, n=127) |
| UPDOWN_STOP | ACTIVE | — |
| Loop cadence | WEEKLY-ONLY | 2026-07-24 (owner directive) |

No live path exists. The bot service failing is moot for fills but must be fixed before any strategy revival.

---

## Capital & Kill-Switch Proximity

| Check | Value | Threshold | Status |
|---|---|---|---|
| Day P&L vs -$10 halt | $0.00 | -$10 | CLEAR |
| Capital vs $75 weekly floor | $88.750 | $75 | CLEAR (+$13.75 headroom) |
| Capital vs $50 ruin floor | $88.750 | $50 | CLEAR (+$38.75 headroom) |
| Rolling 20-trade WR/PF | N/A (0 fills in 12 days) | WR<30% / PF<0.8 | N/A |

**CAVEAT:** WR/PF kill-switch floors were specified for the taker era. Maker band YES legs win ~22% by design at 4–5x payoff; a WR-only kill on maker performance would be invalid. Re-derivation proposal pending with user.

---

## Expected Maker Rebates (unchanged)

Cumulative expected rebate: **$3.917 (upper bound)**. No new fills since BAND_LIVE disabled 2026-07-06. Rebate pool accrues daily; min $1 accrual before payout. This figure has exceeded $1 for multiple sessions with no payout recorded. **User must verify pUSD receipt in Polymarket wallet.**

---

## Day Verdict

**STALL (day 7)** — equity flat at $88.750373. Bot service failed for 7 consecutive days; 12 consecutive zero-fill days. No live path exists. Data-mirror timer is running independently (snapshot fresh). No action possible from this session.

**Required action: SSH to VPS → diagnose and restart `systemd` service.**

Next EVOLVE window: 2026-08-02 (weekly cadence). Service diagnosis should precede that session.
