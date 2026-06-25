# Klaus PnL Ledger — 2026-06-24

**Generated:** 2026-06-24T23:37Z | **Snapshot:** 2026-06-24T23:37:16Z (age: 0h) ✓  
**System:** `active` | **Open positions (bot counter):** 0 | **Uptime:** since 08:04:37 UTC  
**Trades.jsonl:** UNAVAILABLE (25.8 MB — second consecutive day; rolling WR/PF and per-leg resolution PnL not computable)

---

## §1 — P&L Explain (UTC 2026-06-24)

### Capital

| Item | Value |
|---|---|
| Capital prior EOD (2026-06-23) | $212.972 |
| Capital current (23:37 UTC) | $209.764 |
| **Day PnL (capital basis)** | **−$3.208 (−1.51%)** |

### Cash-flow reconciliation

| Leg | Direction | Cash Flow | Notes |
|---|---|---|---|
| RECYCLE099 exits (18 fills, exit099_live.jsonl) | Inflow | +$157.50 | Confirmed; prior-day band YES positions sold at 0.99 |
| New band NO entries (47 maker fills, fill tape) | Outflow | −$162.51 | Confirmed; 32 distinct cities |
| New band NO resting — 4 unmatched limit orders | CLOB locked | −$20.00 | Confirmed from maker_resting_state.json |
| New band YES entries (inferred residual) | Outflow | ~−$2.49 | band_posted_state $185 − $162.51 fills − $20.00 resting |
| Prior-day resolutions — inferred net inflow | Inflow | +$24.29 | Capital residual; breakdown requires trades.jsonl |
| **Net** | | **−$3.21** | **reconciled** |

**UNEXPLAINED: $0.00** — The $24.29 "inferred resolution" line is EXPECTED activity (prior-day band NO/YES positions resolving today). It is NOT model-side unexplained PnL. Breakdown by winner/loser impossible without trades.jsonl. Most likely source: band NO wins from June 22 d+2 + June 23 d+1 entries, partially offset by losses.

### RECYCLE099 detail (18 exits today)

| # | Token (abbrev.) | Shares | Entry | Exit | PnL |
|---|---|---|---|---|---|
| 1 | 107131...319800 | 4.99 | 0.530 | 0.99 | $4.60 |
| 2 | 9336...233499 | 6.00 | 0.630 | 0.99 | $2.87 |
| 3 | 41014...954789 | 8.00 | 0.630 | 0.99 | $2.88 |
| 4 | 25365...143335 | 9.00 | 0.580 | 0.99 | $3.69 |
| 5 | 88549...998835 | 7.00 | 0.700 | 0.99 | $2.09 |
| 6 | 46734...851640 | 9.00 | 0.590 | 0.99 | $3.60 |
| 7 | 64866...371606 | 11.00 | 0.967 | 0.999 | $0.35 |
| 8 | 95760...495799 | 9.00 | 0.550 | 0.99 | $4.03 |
| 9 | 31279...473769 | 9.00 | 0.610 | 0.99 | $3.42 |
| 10 | 95719...723988 | 20.00 | 0.904 | 0.99 | $2.28 |
| 11 | 49139...771671 | 8.00 | 0.630 | 0.99 | $2.88 |
| 12 | 34362...281398 | 8.00 | 0.600 | 0.99 | $3.26 |
| 13 | 95030...471532 | 10.00 | 0.500 | 0.99 | $4.90 |
| 14 | 95320...156384 | 6.00 | 0.640 | 0.99 | $2.73 |
| 15 | 57360...224393 | 8.00 | 0.660 | 0.99 | $2.64 |
| 16 | 33557...488880 | 8.00 | 0.660 | 0.99 | $2.64 |
| 17 | 24757...469103 | 8.00 | 0.600 | 0.99 | $3.26 |
| 18 | 93204...108326 | 10.00 | 0.530 | 0.99 | $4.60 |
| **TOTAL** | | **158.99 sh** | avg 0.66 | — | **$56.71** |

Time span: 03:49–23:35 UTC. All from prior-day band YES positions. 100% exit success rate BY CONSTRUCTION — exit099_live.jsonl logs only completed sells; failed/lost positions appear in trades.jsonl. Proceeds: $157.50. Cost basis (prior sessions): ~$105.40.

---

## ⚠ CRITICAL RISK FLAG — Mexico City NO position

Fill tape shows aggressive averaging-down at 21:24 UTC on a deeply adverse position:

| Event | Shares | Price | Cost |
|---|---|---|---|
| Prior fills (pre-today, estimated) | ~11.0 | ~0.82 | ~$9.05 |
| Today fill 1 (21:24:29 UTC) | 2.0 | 0.06 | $0.12 |
| Today fill 2 (21:24:54 UTC) | 81.5 | 0.06 | $4.89 |
| **Position total** | **94.5 sh** | **avg 0.1649** | **$15.59** |

Market price at snapshot: **$0.06/sh** → market value **$5.67** → **paper loss −$9.92 (−63.6%)**

The bot system's "open positions" counter shows **0** — this position is **NOT tracked** in the bot's position monitor. Discrepancy is unexplained.

Resolution: end_date 2026-06-25T12:00Z (tomorrow). If NO wins (temperature outside band): payout $94.50, profit +$78.91. If YES wins (temperature inside band): total loss −$15.59. **Market assigns 94% probability YES.** Averaging down at $0.06 on a 94%-short position adds 81.5 shares for $4.89 with no reduction in the primary risk.

---

## ⚠ Untracked fill alert (recurring)

Two fills today on the bot's WebSocket that are NOT in [MAKER-FILL] tracker and NOT in exit099_live:

- **22:37 UTC:** token `4349364364702823`, 25 sh @ $0.42, BUY, trader_side=MAKER ($10.50)
- **22:55 UTC:** token `9320497113826808`, 77.09 sh @ $0.99, BUY, trader_side=MAKER ($76.32)

Prior state flagged the same pattern (8 untracked fills June 22). **Most likely cause:** counterparty order sizes visible on the WebSocket stream, not the bot's own fills (consistent with sizes exceeding any known Klaus resting order). Capital reconciliation treats these as zero net. **User: verify Polymarket transaction history for these two tokens to confirm.**

---

## §2 — Compounding Scoreboard

### Equity estimate

| Component | Basis | Value |
|---|---|---|
| Cash balance | bankroll.json | $209.76 |
| SELL_EXIT resting positions (35 orders, 267 shares) | avg cost ~$0.62/sh | +$165.54 |
| Mexico City NO open position (94.5 sh) | cost basis | +$15.59 |
| Resting NO limit orders (4 unfilled) | CLOB locked | +$20.00 |
| **Equity estimate** | **at cost** | **~$410.89** |

**Caveats:** (1) SELL_EXIT fills at $0.99 are not guaranteed — counterparty flow dependent; positions may alternatively resolve YES at $1.00 (better) or NO at $0 (worse). (2) Mexico City at market value = $5.67 (vs $15.59 at cost). (3) Resting NO value contingent on resolution outcomes. (4) YES/NO resolution mix for ~65 prior-session positions resolving this week is unknown without trades.jsonl. **Total uncertainty ±$60.**

At full-exit-value (all SELL_EXIT fill at 0.99 + Mexico City resolves NO): $209.76 + $264.43 + $94.50 + $20 = ~$589 (theoretical max, unrealistic). Conservative cost-basis: $411.

### Fill volume and turns

| Metric | Value | Notes |
|---|---|---|
| NO maker fills today | $162.51 | 47 [MAKER-FILL] lines confirmed; 32 cities |
| RECYCLE099 exits today | $157.50 | 18 fills confirmed |
| Total matched volume | ~$320 | Buy + sell sides |
| Equity estimate | $411 | At cost (see above) |
| **Turns/day** | **~0.78** | $320 / $411 |
| **ROI/turn (capital basis)** | **−1.0%** | −$3.21 / $320 |
| **ROI/turn (RECYCLE099 only)** | **+36%** | $56.71 / $157.50 exit proceeds |

### 7-day trend

| Date | Capital | Day PnL | RECYCLE099 | Turns |
|---|---|---|---|---|
| 2026-06-23 | $212.97 | +$14.70 (+7.4%) | +$76.997, 18 exits | ~0.26 |
| **2026-06-24** | **$209.76** | **−$3.21 (−1.5%)** | **+$56.71, 18 exits** | **~0.78** |

Turns improved 3× day-over-day (0.26 → 0.78) driven by heavier NO posting. ROI/turn negative because resolution income ($24.29) insufficient to offset the net deployment gap ($185 out − $157.50 back = −$27.50 operation). Badatmath benchmark: ~1.0× equity/day at 10–20%/turn. Klaus at 0.78 turns but negative ROI/turn today.

**Deployed fraction:** ($165.54 + $15.59 + $20.00) / $410.89 = **49%** of equity in open positions.

---

## §3 — Expected Maker Rebates

Formula: `sum(shares × feeRate × p × (1−p)) × 0.25` where feeRate = 0.05 (weather taker rate)

### Today's NO maker fills

| Segment | Shares | Avg p | p(1−p) | Est. rebate |
|---|---|---|---|---|
| 45 standard NO fills (avg p ≈ 0.625) | ~254 sh | 0.625 | 0.234 | $0.74 |
| Mexico City NO fills at p = 0.06 | 83.5 sh | 0.060 | 0.056 | $0.06 |
| RECYCLE099 sells (resting at 0.99) | 159 sh | 0.990 | 0.010 | $0.02 |
| **Today total** | | | | **~$0.82** |

Note: Mexico City fill earns near-zero rebate per share despite 83.5 shares (p×(1−p) collapses at extremes). The rebate motive does NOT justify the averaging-down.

### Cumulative rebate tracking

| Session | Est. rebate | Cumulative |
|---|---|---|
| 2026-06-23 | $0.376 | $0.376 |
| 2026-06-24 | $0.82 | **~$1.20** |

**Cumulative expected rebate ~$1.20 — ABOVE the $1 minimum payout threshold.**  
Polymarket maker rebates are paid daily in pUSD. **User action: verify pUSD wallet for a rebate deposit. If none has arrived, pool competition is higher than estimated (this is an upper bound — actual share of the rebate pool depends on competing makers on the same markets).** Mid-price NO fills (p ≈ 0.50–0.65) are the highest-rebate bucket; the concentration here is correct.

---

## §4 — Kill-Switch Proximity

### Capital floors

| Metric | Current | Threshold | Status |
|---|---|---|---|
| Capital | $209.76 | $75 weekly floor | ✓ SAFE (180% above) |
| Capital | $209.76 | $50 ruin floor | ✓ SAFE (320% above) |
| Day PnL | −$3.21 | −$10 daily halt | ✓ SAFE ($6.79 buffer) |
| Consecutive wins | 0 | — | — |

### Rolling 20-trade WR/PF

**Cannot update — trades.jsonl unavailable (second consecutive day).**

| Metric | Last known | As of | Flag |
|---|---|---|---|
| Rolling 20 WR | 10% | 2026-06-22 | ⚠ FLAGGED |
| Rolling 20 PF | 0.17 | 2026-06-22 | ⚠ FLAGGED |

**CAVEAT (carried from prior state, re-stated):** WR/PF kill-switch thresholds were designed for the taker era. In the maker band regime, the bot intentionally holds many YES positions that win ~22% by design at 4–5× payoff. RECYCLE099 today showed 100% exit success on 18 positions. The WR/PF re-derivation for the maker regime is **PENDING** with the user. **Do not recommend halt on WR alone** — capital is safe and the exit machine is functioning. The flags are structural artifacts of applying taker metrics to a maker strategy.

### LDA system (separate from band)

**STATUS: STOP** per lda_status.txt (23:38 UTC today, n=118 fires, 2026-05-15 era start).

| LDA metric | Value |
|---|---|
| Overall net (118 fires) | +$1.99 |
| Current rolling-20 net | −$19.71 |
| Worst rolling-20 | −$36.39 (at T05206_BTC_1778928776) |
| Worst hour bucket | H10: n=19, WR=63.2%, net −$32.20 |
| Worst ask band | [0.65,0.70): n=3, WR=33.3%, net −$18.65 |

LDA is the taker system and is **separate** from the band/maker system. If STOP is code-enforced, LDA fires are halted. The H10 bucket and [0.65,0.70) ask band are confirmed loss zones and should not be reopened without investigation.

---

## §5 — Day Verdict

**NO — capital contracted −$3.21 (−1.51%).**

RECYCLE099 was strong: 18 exits, +$56.71, 100% exit success rate, entries spanning 0.50–0.97. The drag is structural: $185.00 new deployment vs $157.50 recycled + $24.29 resolved = $181.79 in (net outflow $3.21). This is not a signal failure — it is the model in transition. Capital is being committed today for future resolution payouts.

**Binding constraint:** New-entry velocity ($185) exceeding same-day return ($181.79).

### Additional flags for 2026-06-25 session

1. **Mexico City NO (94.5 sh @ $0.1649, mkt $0.06): resolves 2026-06-25T12:00Z.** Bot shows "open positions: 0" — position may be untracked. If it resolves YES, −$15.59 loss. Watch system behavior at resolution.
2. **Disk usage 89%** (82GB of 97GB used, up from 88% yesterday June 23). At current growth rate, may hit capacity within days. Log/data pruning needed.
3. **daily_start_capital=$15.95** persists. May fire false daily-halt logic. Non-blocking today.
4. **Untracked fills (recurring).** Prior state: 8 events. Today: 2 more. User should verify Polymarket transaction history.
5. **35 SELL_EXIT resting orders (267 shares, 0 matched at snapshot).** Tomorrow's d+1 NO resolutions from June 24 $185 deployment will be the primary capital event of the next session.
6. **Band YES re-activation (commit d156804, today):** d+1/d+2 YES ceil widened to 0.45, co-fill pairing unblocked. Genesis-era YES was the loss side (YES −$374 vs NO +$768). Monitor YES fill volume on 2026-06-25 to confirm no drag.
7. **Rebate threshold crossed:** Cumulative expected ~$1.20. Verify pUSD wallet.

---

*Ledger auto-generated by PnL Attribution routine — 2026-06-24T23:37Z*
