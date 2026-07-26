# PnL Ledger — 2026-07-26 (STALL, day 3)

**ABORT: `system_status.txt` missing `'klaus systemd: active'` — status: `failed unknown`. Day 3 of service failure. Full pipeline skipped per protocol. Key capital event noted below.**

---

## Operational Snapshot

| Field | Value |
|---|---|
| Snapshot age | **4 min** (23:33:06 UTC) — fresh |
| `klaus systemd` | **FAILED/UNKNOWN** (day 3; last active 2026-07-24T10:09Z) |
| data-mirror timer | Running (independent snapshot; 8228 rows) |
| Capital | **$88.750373** (from $21.495442 yesterday; +$67.255) |
| Open positions | 0 |
| Loop mode | WEEKLY-ONLY (daily+liveness timers disabled per owner 07-24 shutdown) |
| BAND_LIVE | False (disarmed Jul-6) |
| BAND_NO | Disabled Jul-2 |
| STWA / UPDOWN paths | All disabled |
| Maker resting | {} (no resting orders) |
| G8 gate | **KILLED** — n=127 WR 0.9528 < BE 0.9651 (EVOLVE commit 07-26) |
| Zero-fill streak | **Day 7** |
| Cum. expected rebate | $3.917 upper bound (no new fills since BAND_LIVE disabled Jul-6) |

---

## Section 1 — P&L Explain (UTC 2026-07-26)

| Leg | Class | Net PnL |
|---|---|---|
| trades.jsonl resolved today | (none — bot service failed) | $0.00 |
| RECYCLE099 exits today | (none) | $0.00 |
| Maker rebate accrual today | (none — no fills) | $0.00 |
| **Total attributed** | | **$0.00** |

**Capital delta**: $88.750373 − $21.495442 = **+$67.254931**

**Attribution**: EVOLVE commit `ddbcecdd1` (07-26, 2026) documents: *"equity $88.750373 CLOB-exact = $21.50 + $67.25 owner-manual (on-chain to the cent), bankroll synced."*

Owner deposited **$67.25** manually on-chain today. Bot trading contributed $0.00.

**UNEXPLAINED = $67.254931 − $67.25 = $0.005** (rounding in EVOLVE commit display vs bankroll.json precision — **NOT a model deficiency**; well below $5 investigation threshold).

---

## Section 2 — Compounding Scoreboard

| Metric | Today | 7-day trend |
|---|---|---|
| equity_est | **$88.750** (cash only; 0 open positions, 0 resting orders) | was $21.495 (pre-deposit) |
| deployed fraction | 0% | 0% streak |
| fills_usd today | $0.00 | $0 since Jul-6 |
| turns/day | **0** | 0.0 for 7 consecutive days |
| ROI/turn (resolved legs) | N/A | N/A |

**Equity estimate caveat**: cash-only; no CLOB check possible while service is down. EVOLVE commit confirms $88.750373 CLOB-exact as of today's weekly review.

**vs benchmark**: badatmath benchmark = ~1.0× equity/day at 10-20%/turn. Klaus: **0 turns, $0 deployed, 0 fills** for 7 consecutive days. No compounding is occurring.

Note: the equity *number* jumped 4× today but this is entirely from the owner injection, not from strategy returns. The compounding engine has been fully idle since Jul-6 (BAND_LIVE disabled) and has no live paths as of the Jul-26 EVOLVE.

---

## Section 3 — Expected Maker Rebates

| Metric | Value |
|---|---|
| New maker fills today | 0 |
| Expected rebate today | $0.00 |
| Cumulative expected (upper bound) | **$3.917** (unchanged from Jul-6) |
| Rebate payout status | UNKNOWN — user must verify pUSD receipt |

Cumulative expected $3.917 exceeds the $1 minimum accrual threshold. **No payout has been recorded in any session.** Owner must check Polymarket wallet for pUSD deposits. Mid-price fills (p near 0.5) are quadratically highest-earning — the bulk of this estimate came from BAND_LIVE era fills at near-0.5 prices before Jul-6 disarm.

---

## Section 4 — Kill-Switch Proximity

| Switch | Threshold | Status |
|---|---|---|
| Day PnL halt | < −$10 | **CLEAR** — $0.00 |
| Weekly floor | < $75 | **CLEAR** — $88.75 ✓ (was BREACHED yesterday at $21.50; cleared by owner deposit) |
| Ruin floor | < $50 | **CLEAR** — $88.75 ✓ (was BREACHED yesterday; cleared by deposit) |
| 20-trade WR | < 30% | **N/A** — 0 fires, measurement window void |
| 20-trade PF | < 0.8 | **N/A** — 0 fires |
| G8 certainty-taker gate | pre-registered kill at n≥100 WR<BE | **FORMALLY KILLED** — n=127 WR 0.9528 < BE 0.9651 (pooled 5-asset n=469 WR 0.964 < 0.965); also graveyard #15 (inverse divergence-fade, WR 0.074 vs BE 0.126 n=136) and #16 (t_left dead-zone, 8/17 losses outside) |
| Bot service | systemd active | **FAILED** (day 3) |
| All live paths | any enabled | **NONE** (all disarmed; loop weekly-only) |

**CAVEAT**: WR/PF kill-switches (30%/0.8) were specified for the taker era. The maker band book wins ~22% of YES legs by design at 4–5× payoff. A kill-switch re-derivation proposal is pending with the user; do NOT trigger halts on WR alone. No current WR/PF measurement is possible (0 fires).

**Floor recovery note**: yesterday's capital-floor breaches ($21.50 < both $75 and $50 floors) are now cleared by the owner's on-chain deposit. The old "owner-waived, persistent" caveat from prior sessions is no longer applicable.

---

## Section 5 — Day Verdict

**STALL (day 3) — equity up 4× from owner deposit, not strategy. Capital $88.750373 (floors now CLEAR). Bot service failed for 3 consecutive days. G8 certainty-taker path formally killed in today's EVOLVE at n=127. Zero live paths remain. Loop mode WEEKLY-ONLY. No fills since Jul-6 (7 consecutive zero-fill days). Binding constraint: service failure + all paths disarmed. SSH to VPS required before any restart can be considered.**

---

*Generated 2026-07-26T23:37 UTC by PnL Ledger agent (STALL protocol, day 3)*
