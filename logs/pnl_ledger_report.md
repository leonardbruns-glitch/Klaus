# Klaus PnL Ledger — 2026-07-23 (UTC)

**Generated:** 2026-07-23T23:39Z  
**Snapshot:** 2026-07-23T23:39:46Z (0.0h old — current)  
**System:** `klaus systemd: active`  
**Capital (CLOB-exact):** $21.495442 — confirmed by EVOLVE evening slot 22:08Z ("wallet $21.495442 CLOB-actual == bankroll exact")

---

## Section 1 — P&L Explain (UTC day 2026-07-23)

### Capital Bridge

| Item | Value |
|---|---|
| Capital at prior report (2026-07-22) | $21.495442 |
| Capital now (bankroll.json / CLOB-verified) | $21.495442 |
| **Capital delta** | **$0.00** |

### Attributed P&L

| Leg | Entry class / source | Fills | Net PnL |
|---|---|---|---|
| Bot fills | All live paths (BAND_LIVE=False, STWA disabled) | 0 | $0.00 |
| RECYCLE099 | exit099_live.jsonl 2026-07-23 — file absent (no activity) | 0 | $0.00 |
| Maker rebate accrual | maker_resting_state={}, no live orders | — | $0.00 |
| **Total attributed** | | | **$0.00** |

**UNEXPLAINED P&L: $0.00** (capital delta $0.00 − attributed $0.00). No MODEL DEFICIENCY on the P&L line.

### Critical Update — STWA "Open Positions" Confirmed Phantom

Prior ledger (Jul-20 through Jul-22) tracked three STWA positions at $14.576 cost with up to +$143 upside:

- Jul-17 multi-leg: $8.060 at cost
- Jul-18 single-leg: $3.590 at cost
- Jul-19 YES leg (146.33sh @ $0.02): $2.926 at cost, $143.40 upside

**EVOLVE morning slot (Jul-23 11:55Z) ran a data-api wallet audit and found:**  
*"408 positions ALL $0.00, last on-chain activity 07-19T07:59:46Z (the fatal fire), no 146.33sh token exists, pnl_ledger token id truncated garbage → the 3 'overdue STWA opens' ($14.58 cost, $143 upside) are PHANTOM; equity = $21.4954 cash exactly."*

**Impact:** $14.576 of "equity at cost" and $143.40 of upside tracked in prior ledger states were phantom. The +$143 wildcard that prior reports flagged as a possible windfall does not exist. No cash impact on today's P&L (the positions were already excluded from `capital` when purchased; the error was in equity_est, not in the P&L bridge). This constitutes a **MODEL DEFICIENCY in prior reports** — the ledger tracked positions using truncated/garbage token IDs and did not independently verify via on-chain wallet audit.

---

## Section 2 — Compounding Scoreboard

### Equity Estimate

| Item | Amount | Notes |
|---|---|---|
| Wallet cash | $21.495 | CLOB-exact, EVOLVE-confirmed |
| Open positions at cost | $0.00 | Confirmed: 0 open positions (system_status), STWA phantom resolved |
| **Equity_est today** | **$21.495** | **CLOB-exact. No caveats — wallet audit confirmed.** |
| Prior equity_est (Jul-22) | $36.071 | Inflated by $14.576 phantom STWA positions — MODEL DEFICIENCY, now corrected |
| **Write-down** | **-$14.576** | Structural correction; not a realized loss; cash balance never included this |

CAVEAT: Equity_est is now more reliable than in prior reports — the phantom positions have been excised and the remaining $21.495 is CLOB-verified. No further open positions exist.

### Compounding Metrics

| Metric | Today | 7d context |
|---|---|---|
| Fills (USD) | $0 | Day 4 consecutive zero-fill days |
| Deployed fraction | 0% | All paths disarmed |
| Turns/day | 0 | N/A |
| ROI/turn | N/A | Last realized turn: 2026-07-19 (fatal sniper loss) |
| Day PnL | $0.00 (0.00%) | Flat for 4th consecutive day |

**7d realized (from EVOLVE evening, Jul-23):** -$6.34 (sniper tape: 22 settles 21W/1L; weather: $0). All losses pre-cut.

**Benchmark comparison:** badatmath (reference maker) runs ~1.0× equity/day at 10-20%/turn. Klaus is at 0 turns/day, 0% deployed. The gap is structural — all live paths are disarmed by kill-floors and gate logic, not by signal absence.

---

## Section 3 — Expected Maker Rebates

| Metric | Value |
|---|---|
| Today's live maker fills | 0 (maker_resting_state={}, BAND_LIVE=False) |
| Today's expected rebate | $0.00 |
| **Cumulative expected rebate (UPPER BOUND)** | **$3.917** |
| Last new accrual | 2026-07-06 (BAND_LIVE disabled) |

The $3.917 cumulative accrued entirely before Jul-6 when BAND_LIVE was disabled. No new maker fills are possible while BAND_LIVE=False. The cumulative figure is an upper bound — actual pool share depends on competing makers and daily pUSD distributions.

**Action item (user-verifiable):** Cumulative expected rebate $3.917 exceeds the $1.00 minimum accrual for pUSD payout. The user should verify receipt of pUSD in the Polymarket wallet. No payout has ever been recorded in the ledger.

Band shadow activity today (band_struct_lite.jsonl): shadow scan active across all cities for d+0/d+1/d+2, generating fire-eligible quotes in shadow mode only (live=false). Multiple shadow "fire" events logged (Seoul d+2, Tokyo d+2, Taipei d+2, Chengdu d+2). These produce no cash flows — shadow mode only. The rebate calculation formula (shares × 0.05 × p × (1−p) × 0.25) applies only to executed live fills. All today's band activity is shadow; rebate = $0.

---

## Section 4 — Kill-Switch Proximity

### Thresholds

| Kill switch | Threshold | Current | Status |
|---|---|---|---|
| Day PnL halt | −$10.00 | $0.00 | ✓ CLEAR |
| Ruin floor (capital) | $50.00 | $21.495 | ✗ BREACHED (owner-waived, persistent) |
| Weekly floor (capital) | $75.00 | $21.495 | ✗ BREACHED (owner-waived, persistent) |
| Kernel floor (re-arm gate) | $40.00 | $21.495 | ✗ BELOW — blocks all re-arms without owner |
| G8 gate (primary) | CI-lo ≥ BE ~0.965 | CI-lo 0.889 | ✗ KILL-LOCKED |

### G8 Gate Detail

| Metric | Value |
|---|---|
| n (settled since cut) | 88 |
| Record | 84W / 4L |
| Point WR | 0.9545 |
| Breakeven WR | ~0.9649 |
| Gap (point vs BE) | −0.0104 |
| CI-lo (Wilson) | ~0.889 |
| Best-case at n=100 | 0.9600 — **cannot clear BE** |
| Kill ETA | ~2026-07-25 (accrual ~7/day, n=100 in ~1.7 days) |
| Kill action | Gate auto-executes at first n≥100 reading with point < BE |
| Review date | Rolls with the data (registered 07-24) |

**All active paths:** BAND_LIVE=False (Jul-6, equity < 50% HW $222.90) · BAND_NO=False (Jul-2, 7d WR 39.2%) · STWA_REGULAR=False (disabled) · LDA=STOPPED (rolling-20 −$36.39) · UPDOWN_STOP=ACTIVE · Maker shadow: running, 0 live orders.

**CAVEAT on WR/PF floors:** The CLAUDE.md taker-era kill floors (WR >40%, PF >1.3) are inapplicable to the current maker/sniper architecture. The G8 gate CI-lo vs breakeven is the correct kill instrument. The sniper wins ~95%+ of YES legs by design (small-positive edge, high WR, limited-payout structure) — halt decisions based on raw WR alone would be misleading. Kill-switch re-derivation is pending with the owner.

**All-history context (per EVOLVE evening):** n=207 all-history, WR 0.9662, CI-lo 0.9319 vs BE 0.9638. The all-history gate is marginally below BE; the post-cut gate (n=88) is the active decision instrument.

---

## Section 5 — Day Verdict

**FLAT** — equity did not compound today (day PnL $0.00, 0.00%). Binding constraint: all trading paths disarmed by kill-floor hierarchy + G8 gate KILL-LOCKED.

**Structural event today:** STWA "open positions" tracked in prior ledger reports (Jul-20 through Jul-22) confirmed phantom via on-chain wallet audit. Equity_est written down from $36.071 to $21.495 (−$14.576 correction; no cash impact). The +$143 YES wildcard that prior reports flagged no longer exists.

**G8 gate kill imminent:** Formalizes at n≥100 (~Jul-25). At ~7 settles/day, the gate resolves in approximately 1-2 trading days. Owner decision point on restart or strategy pivot.

**Five-day view:** Day 4 of zero fills (all pre-Jul-19), Day 4 of $0.00 PnL. Pattern is structural, not temporary — the disarm conditions (equity < $40 kernel floor, G8 kill-locked) will not self-resolve. A config reset or capital injection is required to resume any live path.
