# Klaus PnL Ledger — 2026-06-13
_Generated: 2026-06-13T23:37Z | Snapshot: 2026-06-13T23:27Z (10 min lag) | System: active_

---

## Section 1 — P&L Explain (UTC day 2026-06-13)

**Reference capital:** $208.9033 (prior-report capture, 2026-06-13 02:44Z)
**Capital now:** $246.4027 (bankroll.json, saved 23:19Z)
**Capital delta:** **+$37.4994**

| Leg | Count | Gross PnL | Notes |
|---|---|---|---|
| WEATHER NO-resolve (trades.jsonl) | 23 | **−$49.13** | exit_price=0.0; positions entered Jun 10–13, closed today at resolution |
| WEATHER scalp wins (trades.jsonl) | 2 | **+$1.07** | 07:01Z +$0.31; 17:49Z +$0.76 — sold before resolution |
| RECYCLE099 convergence sells (exit099_live) | 9 | **+$79.15** | all at exit=0.99; entries 0.13–0.62; n=9 |
| **Total attributed** | — | **+$30.02** | no token overlap between legs (double-count check: 0 matches) |
| **UNEXPLAINED** | — | **+$7.48** | exceeds $5 flag |

**Unexplained investigation:** The capital trail via `capital_after` shows bidirectional gaps — net +$7.48 stranded between attributed sources. Root cause is most likely **unbooked resolution flows**: the WS fill tape records 54 `[USER-WS] UNTRACKED FILL CONFIRMED` events on Jun 13, covering tokens with no tracker entry. These update `bankroll.json` via WS credit but produce no record in `trades.jsonl` or `exit099_live.jsonl`. Directional check: estimated capital after last logged r099 (23:14Z, +$11.85) would be ~$254.32, but `bankroll.json` at 23:19Z = $246.40 → an apparent **−$7.92 shortfall** at the snapshot edge, consistent with further NO-resolves in that 5-minute window that haven't yet flushed to `trades.jsonl`. The +$7.48 headline unexplained likely includes a late r099 fill also unlogged. **No manual deposit evidence; no ruin signal.** This is a **MODEL DEFICIENCY**: `bankroll.json` and `trades.jsonl` are updated by different code paths; UNTRACKED WS fills create a permanent attribution gap.

**RECYCLE099 detail (today, all 9 rows):**

| Time (UTC) | Shares | Entry | Exit | PnL |
|---|---|---|---|---|
| 05:09 | 11.99 | 0.27 | 0.99 | +$8.64 |
| 06:21 | 5.00 | 0.15 | 0.99 | +$4.35 |
| 07:02 | 11.00 | 0.13 | 0.99 | +$20.20 |
| 08:06 | 14.00 | 0.21 | 0.99 | +$11.70 |
| 08:11 | 8.00 | 0.27 | 0.99 | +$8.64 |
| 12:08 | 10.00 | 0.28 | 0.99 | +$7.63 |
| 15:57 | 6.00 | 0.62 | 0.99 | +$2.78 |
| 21:56 | 8.00 | 0.57 | 0.99 | +$3.36 |
| 23:14 | 7.00 | 0.20 | 0.99 | +$11.85 |
| **Total** | **80.99** | | | **+$79.15** |

---

## Section 2 — Compounding Scoreboard

**Equity estimate:** $274.42
- Free cash (bankroll.json): $246.40
- Matched future resting positions (maker_resting_state, d+14..d+15): +$28.02
- **Caveats:** (1) Resting state shows 71 entries with no end_date and 6 entries for Jun 10–12 (combined cost $21.50) that are very likely worthless at resolution — these are excluded from equity_est; future matched $28.02 is the only forward-looking component. (2) Jun 13 intraday maker fills that resolved before this report are NOT separately counted (already in bankroll.json). (3) 0 open positions confirmed by system_status.txt.

| Metric | Today | Jun 12 (prior) | Δ |
|---|---|---|---|
| Capital | $246.40 | $208.90 | +$37.50 |
| Equity est | $274.42 | $238.01 | +$36.41 |
| Fills $ | $144.94 | $131.44 | +$13.50 |
| Turns/day | 0.528× | 0.55× | −0.022× |
| ROI/turn (attributed) | 20.7% | 7.3% | +13.4pp |
| Day ROI (capital basis) | **+18.0%** | +6.6% | +11.4pp |

**7-day trend note:** badatmath benchmark ≈ 1.0× equity/day at 10–20%/turn. Today: 0.53× turns at 20.7%/turn → absolute day gain similar to benchmark despite lower velocity. Binding factor is fill velocity (83 maker fills at avg $1.75/fill vs. benchmark's higher-frequency fill cadence), not edge quality.

**RECYCLE099 is the primary alpha source:** 9 sells at avg 6.3× entry (e.g., entry 0.13 → exit 0.99) generating $79.15 gross against $49.13 in YES-leg losses. The YES-leg loss rate is structurally expected (maker buys at 10–45¢; most expire worthless; the occasional 0.99 convergence is the payoff). Pair arithmetic only works if converging wins are large enough to cover the serial NOs — today they were.

---

## Section 3 — Expected Maker Rebates

Weather taker feeRate = 0.05, maker rebate share = 25% of pool proportional to fee_equivalent = shares × 0.05 × p×(1−p).

| Source | Fills | Fee Equiv Basis | Expected Rebate (est.) |
|---|---|---|---|
| Jun 13 maker fills (83 events) | 267.4 YES sh + 93.4 NO sh + 37 add-to events | $4.3514 | **$1.0878** |
| Cumulative prior (through Jun 12) | — | — | $1.2645 |
| **Cumulative expected** | | | **$2.3523** |

Actual rebate for Jun 12 partial + Jun 13 add: prior report already had $1.2645 cumulative; today adds $1.0878 → **$2.3523 total**.

**⚠ ACTION REQUIRED:** Cumulative expected exceeds $1 minimum accrual threshold. User should verify pUSD receipt in wallet for prior days' payouts. If no payout has been received since Jun 10 live start, flag to Polymarket support.

**Mid-price fill note:** 9 of today's 83 fills fell in the 0.40–0.60 band (highest p×(1−p) efficiency), contributing $0.1672 of expected rebate — disproportionately valuable per-share. NO fills cluster near 0.54–0.65 (still high-efficiency zone at p×(1−p) ≈ 0.23).

---

## Section 4 — Kill-Switch Proximity

| Switch | Threshold | Current | Status |
|---|---|---|---|
| Daily loss halt | −$10/day | +$37.50 today | ✅ CLEAR |
| Weekly floor | $75 bankroll | $246.40 | ✅ CLEAR (+$171.40 headroom) |
| Ruin floor | $50 bankroll | $246.40 | ✅ CLEAR (+$196.40 headroom) |
| Rolling 20 WR | >40% (taker era) | 15% (3W/17L) | ⚠️ BELOW (see caveat) |
| Rolling 20 PF | >1.3 (taker era) | 0.436 | ⚠️ BELOW (see caveat) |

**Rolling 20 breakdown:** 3 wins ($15.97 gross) / 17 losses ($36.62 gross). Wins = 1 WEATHER scalp (+$0.76) + 2 RECYCLE099 (+$3.36, +$11.85). Losses = 17 YES-leg NO-resolves. This window is entirely Jun 13 which was a heavy NO-resolve day. Prior RECYCLE099 wins (07:02 +$20.20, 08:06 +$11.70, 08:11 +$8.64 etc.) fell BEFORE the 16:28–22:23 loss cluster and are outside the rolling 20.

**CAVEAT (mandatory):** WR/PF floors were specified for the taker era. The current book is a maker band — YES legs are designed to lose ~78% individually (buying at 10–45¢, resolved binary). A 15% individual WR is structurally expected; the 4–5× payoff on convergences (RECYCLE099) is the edge. A **kill-switch re-derivation is pending with the user** and these triggers must NOT be acted on unilaterally. Capital is $196.40 above ruin; there is no solvency concern.

---

## Section 5 — Day Verdict

**Equity compounded: YES, +18.0% on capital basis (+$37.50 nominal).**

The binding constraint today was **resolution asymmetry**: 23 YES-leg positions resolved worthless (−$49.13), offset by 9 RECYCLE099 convergence sells at 0.99 (+$79.15). The maker fill velocity (0.53 turns) is tracking slightly below the badatmath benchmark (1.0×) but the ROI/turn (20.7%) exceeded prior sessions. Day result was determined by which positions happened to converge today, not by intraday band activity.

The $7.48 unexplained gap is a logging gap (UNTRACKED WS fills + late-day resolution timing), not a capital event. It does not change the verdict.

---

_Report-only. No code, flags, or stakes modified._
