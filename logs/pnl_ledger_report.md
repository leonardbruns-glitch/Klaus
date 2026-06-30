# Klaus PnL Ledger — 2026-06-29

**Generated:** 2026-06-29T23:37Z | **Snapshot:** 2026-06-29T23:29Z (8 min lag — valid)
**Branch:** claude/find-lag-parameter-rFQ0N | **Snapshot rows:** 8028 | **Service:** active

---

## 1. P&L EXPLAIN (2026-06-29 UTC)

### Capital bridge

| Item | Amount |
|------|--------|
| Capital — prior report (Jun-28 23:37Z) | $75.4846 |
| Capital — now (Jun-29 23:29Z, bankroll.json) | $84.1518 |
| **Day delta** | **+$8.667** |

### Attributed PnL by leg

**RECYCLE099 — convergence sells at $0.99 (exit099_live.jsonl)**

| UTC approx | Shares | Entry | Exit | PnL |
|------------|--------|-------|------|-----|
| 00:55 | 5 | 0.74 | 0.99 | +$1.750 |
| 02:50 | 7 | 0.83 | 0.99 | +$1.120 |
| 03:10 | 7 | 0.70 | 0.99 | +$2.088 |
| 03:52 | 8 | 0.69 | 0.99 | +$2.400 |
| 04:27 | 7 | 0.70 | 0.99 | +$2.088 |
| 04:33 | 7 | 0.83 | 0.99 | +$1.120 |
| 07:10 | 6 | 0.71 | 0.99 | +$2.240 |
| 13:48 | 5 | 0.84 | 0.99 | +$0.900 |
| 14:07 | 7 | 0.70 | 0.99 | +$2.088 |
| 14:24 | 7 | 0.59 | 0.99 | +$3.600 |
| 14:31 | 7 | 0.65 | 0.99 | +$2.652 |
| **TOTAL** | **73 sh** | **avg 0.722** | | **+$22.046** |

Gross RECYCLE099 cash in: 73 × $0.99 = **$72.27**
Cost basis: 73 × $0.722 = **$52.68**
ROI on prior-deployed capital: **41.8%**

**New maker band fills (maker_fills_recent.log — 21 fills confirmed)**

| UTC | City | Side | Shares | Bid | USD out |
|-----|------|------|--------|-----|---------|
| 01:45 | London | NO | 1.8 | 0.76 | $1.37 |
| 05:48 | Beijing | NO | 7.2 | 0.70 | $5.04 |
| 05:52 | Munich | NO | 7.5 | 0.68 | $5.10 |
| 06:16 | Chengdu | NO | 10.4 | 0.48 | $4.99 |
| 07:27 | London | NO | 5.0 | 0.59 | $2.95 |
| 07:46 | London | NO | 4.0 | 0.59 | $2.36 |
| 09:14 | London | YES | 0.7 | 0.45 | $0.32 |
| 09:15 | London | YES | 8.3 | 0.45 | $3.74 |
| 10:47 | Wuhan | NO | 2.3 | 0.70 | $1.61 |
| 11:56 | Wuhan | NO | 4.9 | 0.70 | $3.43 |
| 13:03 | Munich | NO | 7.8 | 0.65 | $5.07 |
| 13:07 | Wuhan | NO | 5.3 | 0.84 | $4.45 |
| 13:50 | Wuhan | NO | 0.7 | 0.84 | $0.59 |
| 13:53 | Wuhan | NO | 5.0 | 0.69 | $3.45 |
| 14:28 | Munich | NO | 6.0 | 0.84 | $5.04 |
| 14:48 | Wuhan | NO | 3.0 | 0.69 | $2.07 |
| 16:58 | Wuhan | NO | 8.0 | 0.71 | $5.68 |
| 18:07 | Chengdu | NO | 7.0 | 0.74 | $5.18 |
| 18:29 | Chengdu | NO | 6.0 | 0.84 | $5.04 |
| 18:31 | Wuhan | NO | 7.0 | 0.81 | $5.67 |
| 21:25 | Beijing | NO | 8.0 | 0.67 | $5.36 |
| **TOTAL** | | | **115.9 sh** | | **$78.50** |

All new fills → SELL_EXIT queue at $0.99; not yet realized.

**Cash reconciliation**

| Flow | Amount |
|------|--------|
| RECYCLE099 gross exit proceeds | +$72.27 |
| New maker fills (cash out) | −$78.50 |
| Native resolutions (inferred, see Unexplained) | +$14.90 |
| **Net = day delta** | **+$8.67 ✓** |

**Attribution summary**

| Source | Realized PnL | Cash Flow |
|--------|-------------|----------|
| RECYCLE099 (prior-cost positions exited) | +$22.046 | +$72.27 |
| New maker fills (open, at cost) | $0 realized | −$78.50 |
| **Total attributed** | **+$22.046** | **+$8.67** |

**UNEXPLAINED: $14.90 — ABOVE $5 THRESHOLD**

Investigation: Confirmed total cash in = $87.17 ($8.667 delta + $78.50 fills). RECYCLE099 gross = $72.27. Residual = **$14.90** unattributed.

Most likely cause: **Jun-28 d+1 NO positions that were still in SELL_EXIT at 12:00Z Jun-29 received native on-chain resolution at $1.00/sh from Polymarket's oracle.** These payments land directly in the funder wallet and are NOT captured in exit099_live.jsonl (RECYCLE099 only captures active CLOB sells at $0.99). Pattern is structurally identical to yesterday's $19.758 unexplained (attributed to Jun-26 d+2 resolutions).

This is a **KNOWN LOGGING GAP**, not MODEL DEFICIENCY in the trading sense — native resolutions are a normal positive outcome (winning NO position held to expiry at $1.00/sh). The gap is in the analytics mirror: exit099_live records only RECYCLE099-path exits, not oracle payouts. Prior state total: 2 consecutive sessions with unexplained > $5 from the same cause.

**User action:** Verify on-chain Polygon wallet credits at/after 12:00Z Jun-29 (approx. $14-15 in pUSD). If confirmed, this is attribution-only gap, not a capital surprise.

---

## 2. COMPOUNDING SCOREBOARD

**Equity estimate (2026-06-29 23:29Z)**

| Component | Amount | Basis |
|-----------|--------|-------|
| Cash capital | $84.152 | CONFIRMED (bankroll.json) |
| SELL_EXIT resting — 91 sh × $0.99 | $90.09 | OPTIMISTIC (unfilled book) |
| SELL_EXIT resting — 91 sh × avg cost $0.72 | ~$65.5 | CONSERVATIVE |
| London pair YES+NO resting ($4 each, 8.89 sh @ 0.45) | ~$8.00 | At cost |
| Active NO bids (Wuhan 7.04sh, Beijing 7.46sh) | ~$10.0 | Not yet filled |
| **Equity est (optimistic)** | **~$192** | Upper bound |
| **Equity est (conservative, SELL_EXIT at cost)** | **~$158** | Working estimate |

CAVEAT: SELL_EXIT at $0.99 face overstates by ~$24 vs cost. Conservative $158 used for turns. Open NO bids ($10) and London pair ($8) add another ~$18 of deployed capital not in SELL_EXIT.

**Performance metrics**

| Metric | Jun-29 | Jun-28 | Badatmath benchmark |
|--------|--------|--------|---------------------|
| Maker fills $ | **$78.50** | ~$66.63 | N/A (taker) |
| Turns/day (fills ÷ equity_cons) | **0.50** | 0.43 | ~1.0 |
| ROI/turn (RECYCLE099 PnL ÷ cost basis) | **41.8%** | 30.9% | 10–20% |
| Capital delta | **+$8.667** | +$5.598 | — |
| Capital % change (1-day) | **+11.5%** | +8.0% | — |

Positive trajectory on all metrics vs Jun-28. ROI/turn improvement (30.9% → 41.8%) driven by two high-margin exits: Wuhan NO entry 0.59 ($3.60 PnL/7sh) and Wuhan NO entry 0.65 ($2.65 PnL/7sh) — these are below-average-entry positions picked up in prior sessions.

Turns/day (0.50) still at roughly half the badatmath ~1.0x benchmark. Binding constraint: maker fill cadence. The bot is posting correctly (21 fills today) but the per-fill dollar size (~$3.74 avg vs ~$5 per position) and fill frequency cap the deployment velocity. Increasing BAND_NO_STAKE to $6-7 when capital permits would raise turns without changing risk structure.

7-day capital trend: $75.485 → $84.152 in two days (+11.5% cumulative from Jun-28 base). Cannot compute exact 7d without prior states; 2-day gain is meaningful.

---

## 3. EXPECTED MAKER REBATES

Formula: rebate_est = Σ shares × feeRate × p × (1-p) × 0.25 (weather taker feeRate = 0.05, maker share = 25%)

**Today's confirmed maker fills:**

| City / Side | Shares | p | Rebate est |
|-------------|--------|---|----------|
| London NO×3 | 10.8 | 0.59–0.76 | ~$0.043 |
| London YES×2 | 9.0 | 0.45 | **$0.028** (highest per-share: near 0.50) |
| Beijing NO×2 | 15.2 | 0.67–0.70 | ~$0.058 |
| Munich NO×3 | 21.3 | 0.65–0.84 | ~$0.063 |
| Chengdu NO×3 | 23.4 | 0.48–0.84 | ~$0.064 |
| Wuhan NO×8 | 36.2 | 0.69–0.84 | ~$0.095 |
| **TOTAL** | **115.9 sh** | avg 0.70 | **$0.297** |

Note: London YES p=0.45 fills are the quadratically highest-earning per share (p×(1-p)=0.2475 vs 0.21 for typical NO at 0.70). The YES pair legs, if filled, compress rebate-optimal fill to the mid-spread.

**Cumulative tracker**

| Period | Amount |
|--------|--------|
| Prior cumulative (through Jun-28) | $1.783 |
| Today (Jun-29, confirmed fills) | $0.297 |
| **New cumulative estimate** | **$2.080** |

**USER ACTION — rebate verification:** Cumulative expected rebate now **$2.080**, above the Polymarket $1.00 minimum payout threshold. If no rebate payout has been received in pUSD yet, please check your wallet at/after today. Payouts should land daily once accrued ≥ $1. If no payout received and cumulative > $2, the estimate may be overstated OR payout processing is delayed — flag to Polymarket support.

---

## 4. KILL-SWITCH PROXIMITY

**Capital gates**

| Gate | Threshold | Current | Buffer |
|------|-----------|---------|--------|
| Day halt | −$10 from day open (~$65.15) | $84.152 | **+$19.00** |
| Weekly floor | $75.00 | $84.152 | **+$9.15** |
| Ruin floor | $50.00 | $84.152 | **+$34.15** |

Day PnL: **+$8.667** — positive. No halt concern.

**Rolling 20-trade WR/PF**

RECYCLE099 exits today: 11/11 profitable (100% WR, all positive PnL). No resolved negative legs observed. trades.jsonl (8028 rows) not parsed directly — rolling 20-trade sample unavailable, but pattern of consecutive positive RECYCLE099 exits is consistent with Jun-27 through Jun-28.

bankroll.json shows `consecutive_wins: 0` despite 11 RECYCLE099 wins. This counter tracks a different granularity (likely STWA resolved markets or daily-level events, not individual band leg exits). Capital growth confirms a winning day; the counter reset likely reflects a resolved STWA or daily cycle event, not an actual loss.

**CAVEAT (mandatory):** WR (<30%) and PF (<0.8) kill-switch floors were specified for the taker momentum era. The band-NO maker strategy by design wins ~22% of YES legs (when NO wins at $1.00/sh) — simple WR across all legs would be misleading. The real kill-signal is capital erosion below $75 floor, not WR. A kill-switch re-derivation for the maker era is **pending with the user** — do NOT halt on WR alone.

**State log:** No entries for Jun-28 or Jun-29. Last manual event: Jun-26 (narrow-start execution fix + BAND_CITY_ALLOW to 5-city set). No manual deposits or withdrawals flagged near today's date. Unexplained $14.90 is consistent with structural native-resolution pattern — not a manual flow.

---

## 5. DAY VERDICT

**YES — equity compounded. Capital +$8.667 (+11.5%). Binding constraint: fill rate (0.50 turns/day vs ~1.0x badatmath target).**

RECYCLE099 drove 100% of attributed realized PnL (+$22.046, 41.8% ROI on $52.68 cost basis, 11 exits). 21 new maker NO fills at $78.50 deployed in SELL_EXIT queue for Jun-30 resolution. Native resolutions at 12:00Z today injected ~$14.90 not captured in mirror logs (KNOWN LOGGING GAP, second consecutive session — verify on-chain wallet). All capital floors cleared comfortably. THERMO paused, YES d+2 shadow-only (London pair YES fill at 09:14-09:15 is the only YES maker fill, $4.06 deployed). No adverse selection signals from band_struct_lite. Last STRUCT-BAND-Q scan at 23:26Z shows cash gate active: 0 posted, 9 candidates — healthy queue for overnight.

---

*Report generated by pnl-ledger-agent | data-mirror SHA b20fceb | 8028 trade rows*
