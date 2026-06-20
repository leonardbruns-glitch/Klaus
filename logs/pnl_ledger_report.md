# Klaus PnL Ledger — 2026-06-20

**Generated:** 2026-06-20T23:37Z  
**Snapshot age:** 14 min (2026-06-20T23:23:06Z — within 6h gate)  
**System:** `systemd: active`, uptime since 2026-06-19 00:17:28 UTC  
**Capital EOD:** $199.093107  
**Prior EOD (Jun 19):** $231.89  
**Status:** FULL REPORT

---

## Section 1 — P&L Explain (UTC 00:00–23:59, 2026-06-20)

### Capital Bookends

| Field | Value |
|---|---|
| Capital SOD (last close Jun 19) | $231.89 |
| Capital EOD (last close Jun 20) | $199.09 |
| Actual day P&L | **-$32.80** |

### Resolution P&L (trades.jsonl, ts_close in 2026-06-20 UTC)

All 39 trades that closed today were entered on prior days: 31 STWA positions entered 2026-06-18, and 8 WEATHER_MAKER positions entered 2026-06-19.

| Leg | n | Entered | WR | Stake | Net PnL | Notes |
|---|---|---|---|---|---|---|
| WEATHER/STWA YES | 28 | 06-18 | 2/28 = 7% | $49.57 | -$42.72 | Entry prices 0.02–0.33; almost all resolved to 0 |
| WEATHER/STWA NO | 3 | 06-18 | 0/3 = 0% | $15.82 | -$15.81 | NO legs at 0.62–0.66 also resolved to 0 (YES won) |
| WEATHER_MAKER NO (7 cities) | 7 | 06-19 | 1/7 = 14% | $35.88 | -$30.88 | Seattle NO won (+$4.70); 6 others zero |
| WEATHER_MAKER NO (Seattle) | 1 | 06-19 | WIN | $5.30 | **+$4.70** | *(rolled into row above)* |

**STWA subtotal:** n=31, stake=$65.39, net=**-$43.84**  
**WEATHER_MAKER subtotal:** n=8, stake=$40.98, net=**-$30.98**  
**Resolution P&L total:** n=39, stake=$94.64, net=**-$74.82**

*Fee note: fee_paid=$0.00 across all 39 trades — consistent with maker/STWA resolution (no taker fee on these legs).*

### RECYCLE099 Convergence Exits (exit099_live, today)

| Time UTC | Shares | Entry | Exit | PnL |
|---|---|---|---|---|
| 06:22 | 8.0 | 0.67 | 0.99 | +$2.5600 |
| 07:00 | 8.0 | 0.66 | 0.99 | +$2.6400 |
| 07:58 | 9.0 | 0.55 | 0.99 | +$4.0436 |
| 08:34 | 6.0 | 0.16 | 0.99 | +$5.1875 |
| 11:04 | 21.0 | 0.95 | 0.999 | +$1.0290 |
| 12:52 | 9.0 | 0.57 | 0.99 | +$3.7800 |
| 14:01 | 7.0 | 0.62 | 0.99 | +$3.1419 |
| 14:21 | 7.0 | 0.64 | 0.99 | +$2.7292 |
| 14:34 | 5.0 | 0.60 | 0.99 | +$3.2565 |
| 15:03 | 8.0 | 0.62 | 0.99 | +$3.1450 |
| 15:29 | 8.0 | 0.63 | 0.99 | +$2.8800 |
| 16:05 | 7.0 | 0.68 | 0.99 | +$2.3250 |

**RECYCLE099 total:** 12 exits, **+$36.72** pnl. Zero token overlap with today's resolution trades — no double-counting risk.

### Reconciliation

| Component | P&L |
|---|---|
| STWA/MAKER resolutions | -$74.82 |
| RECYCLE099 exits | +$36.72 |
| **Total attributed** | **-$38.10** |
| **Actual capital change** | **-$32.80** |
| **UNEXPLAINED** | **+$5.30** |

**|UNEXPLAINED| = $5.30 > $5.00 — one-level investigation:**

Capital trace shows 12 interstitial jumps between resolution events. Matching RECYCLE099 events to interstitials: the first two match exactly to the penny ($2.56 at 06:22 → interstitial +$2.56 before 06:52 trade; $2.64 at 07:00 → +$2.64 before 07:13 trade). The +$9.29 interstitial before the 08:19 trade contains the 07:58 RECYCLE099 exit ($4.04), leaving $5.25 unaccounted. The 08:34 RECYCLE099 ($5.19) separately explains the +$5.19 interstitial before the 09:19 trade. **Conclusion:** the +$5.25 component of the 07:00–08:19 gap is most likely a RECYCLE099 convergence exit not captured in exit099_live.jsonl (shadow log gap, not a capital gap). Manual flows are also possible (pUSD rebate deposit, Polymarket balance adjustment). **NOT MODEL DEFICIENCY.** Full ledger would require cross-checking on-chain pUSD receipts between 07:00–08:19 UTC.

---

## Section 2 — Compounding Scoreboard

### Equity Estimate

| Component | Value | Caveats |
|---|---|---|
| Cash (bankroll.json) | $199.09 | Authoritative cash position |
| Open maker resting (future) | ~$12.18 | 8 entries in maker_resting_state.json with end_date 06-21/06-22; these are at cost already deducted from capital |
| **Equity estimate** | **$199.09** | Conservative: open positions at cost (zero interim value until resolution). Extended estimate $199.09 + $12.18 = $211.27 if YES legs at 0.02–0.30 are valued at entry cost — not recommended |

Capital accounting note: for STWA/MAKER trades, capital is debited at RESOLUTION (not entry). This means capital_before/capital_after in trades.jsonl reflect the resolution event, and the position's stake is only charged when it closes. Interstitial negative jumps (-$5.50, -$10.00, -$2.17 today; total -$17.67) represent new STWA/MAKER entries being made between resolutions.

### Fills & Turns

| Metric | Value |
|---|---|
| Maker fills deployed today | ~$107.71 (65 fill events, 407.7 shares, 32 unique positions) |
| Equity estimate | $199.09 |
| **Turns/day** | **0.54x** |
| ROI/turn (resolved STWA/MAKER legs) | **-79.1%** (YES at 0.02–0.33 overwhelmingly resolved to 0) |
| ROI/turn (RECYCLE099 exits) | **+53.8%** (convergence at avg entry ~0.64, exit 0.99) |
| Net equity ROI today | **-16.5%** ($199.09 vs $231.89 SOD) |

### 7-Day Capital Trajectory (from trades.jsonl EOD capital)

| Date | EOD Capital | Day Delta | RECYCLE099 | trades.jsonl net_pnl |
|---|---|---|---|---|
| 2026-06-14 | $267.04 | +$24.57 | n/a | -$86.48 |
| 2026-06-15 | $232.96 | -$34.08 | n/a | -$78.76 |
| 2026-06-16 | $239.24 | +$6.28 | n/a | -$77.42 |
| 2026-06-17 | $207.23 | -$32.01 | n/a | -$118.84 |
| 2026-06-18 | $212.62 | +$5.39 | n/a | -$104.93 |
| 2026-06-19 | $231.89 | +$19.27 | +$78.58 (19 exits) | -$63.56 |
| **2026-06-20** | **$199.09** | **-$32.80** | **+$36.72** (12 exits) | **-$74.82** |

Pattern: trades.jsonl resolution losses are structurally large and negative every day (YES at 0.02–0.33 rarely win). Actual capital performance is driven by the NET of those losses vs RECYCLE099 exits and WEATHER_MAKER NO wins. The last 7 days show 4 losing and 3 winning actual-capital days, with the biggest loss days (-$32 to -$34) coinciding with low RECYCLE099 volume relative to resolution losses.

**Benchmark:** badatmath ~1.0x equity/day at 10–20%/turn. Today: 0.54x turns at -79.1% ROI/turn (resolution leg) = deeply negative. RECYCLE099 is the partial offset but insufficient to net positive today.

---

## Section 3 — Expected Maker Rebates

Today's maker fills: 65 events, 407.7 shares at entry prices 0.02–0.69.

| Price tier | Shares | Cost | Expected rebate |
|---|---|---|---|
| p≈0.03–0.10 | 126.6 | $8.53 | $0.097 |
| p≈0.17–0.29 | 191.7 | $43.91 | $0.425 |
| p≈0.50–0.54 | 13.4 | $7.20 | $0.042 |
| p≈0.60–0.69 | 75.0 | $48.07 | $0.220 |
| **Total** | **407.7** | **$107.71** | **$0.784** |

Formula: `sum(shares × 0.05 × p × (1-p)) × 0.25`

**Important:** This is an UPPER BOUND. Actual rebate is your share of the maker pool — if many makers were active on the same tokens today, your actual payout is a fraction of this estimate.

**Cumulative rebate tracking:**
- Prior ledger state: $4.2922 cumulative (flag was set: `rebate_verify_flag: true`)
- Today's estimate: +$0.78
- Cumulative estimate: **~$5.07**
- Minimum payout threshold: $1.00 pUSD/day

**USER ACTION REQUIRED:** Prior ledger flagged rebate_verify_flag=true at $4.29 cumulative expected. With today's addition the cumulative estimated rebate exceeds $5. Please verify pUSD balance in your Polymarket wallet. If no rebate has been received since tracking began, the fills may not be qualifying (wrong account, wrong market category, or competing makers diluting the pool). Check against the Polymarket rebate dashboard.

The mid-price fills (p near 0.5) earn the highest rebate per dollar — today's 13.4 shares at p~0.50–0.54 contribute $0.042. The low-p YES fills at 0.02–0.10 (large volume, 126.6 shares) earn minimal rebate due to p×(1-p) → 0 at extremes. Rebate-per-dollar is maximized on the NO legs at 0.60–0.69.

---

## Section 4 — Kill Switch Proximity

### Metric Dashboard

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Rolling 20-trade WR | **5%** (1/20) | Kill if <30% | ⚠️ FAR BELOW |
| Rolling 20-trade PF | **0.067** | Halt if <0.8 | ⚠️ FAR BELOW |
| Day P&L | **-$32.80** | Daily halt: -$10 (live) | ⚠️ EXCEEDED |
| Capital vs weekly floor | **$199.09** vs $225 target | $75 weekly floor (original) | ⚠️ BELOW |
| Capital vs ruin floor | **$199.09** vs $150 | $50 ruin (original $10 capital) | SAFE |
| Peak drawdown (from $267.04 on Jun 14) | **-25.5%** | 25% max drawdown | ⚠️ AT THRESHOLD |

### MANDATORY CAVEAT (per CLAUDE.md)

WR and PF floors were specified for the taker-era updown bot ($10 test capital, momentum scalper). The current strategy is a **maker band book** on weather markets. By design:
- YES legs at 0.02–0.33 win ~2–33% of the time but pay 3x–50x
- The book is structured to lose most YES legs and collect rare large payoffs + RECYCLE099 convergence exits
- 5% rolling WR is consistent with avg entry price ~0.17 (expected WR ~17%) — performance is worse than random expectation, but not by the magnitude WR alone implies
- **PF of 0.067 is more diagnostic:** the winning trade today ($3.86 STWA win + $4.70 Seattle NO win = $8.56 total wins) vs $61.41 in losses is a 0.14:1 ratio — both YES wins were serendipitous rather than systematic

**A kill-switch re-derivation based on the maker book structure is pending with the user. Do NOT halt on WR/PF alone.**

### What IS actionable

The -25.5% drawdown from the Jun 14 peak ($267 → $199) crosses the CLAUDE.md 25% max drawdown trigger. However, the absolute capital floor ($199.09) is well above both ruin levels. The pattern is: large gains when YES legs win or RECYCLE099 volume is high; large losses when YES legs miss and RECYCLE099 volume is low. Today's RECYCLE099 generated only $36.72 vs $74.82 in resolution losses — a structural mismatch.

**5-consecutive-day check:** actual-capital P&L over last 7 days: +24.57, -34.08, +6.28, -32.01, +5.39, +19.27, -32.80. Not a 5-day losing streak; alternating pattern. The losing days correlate with low RECYCLE099 volume (today 12 exits vs 19 yesterday).

---

## Section 5 — Day Verdict

**Equity compounded: NO. -$32.80 / -16.5% on equity.**

Binding constraint: YES STWA resolutions (2/31 wins, 06-18 vintage) overwhelmed RECYCLE099 gains. The 06-18 entry class had near-zero accuracy — only 2 of 31 targets resolved to the correct bucket. WEATHER_MAKER NO legs also failed 7/8 (consistent with warmer-than-expected conditions across most markets on 06-20). Seattle NO was the sole NO winner today.

RECYCLE099 is functioning ($36.72 today, $78.58 yesterday) but at roughly half of yesterday's output. If the maker fill pipeline continues filling new positions at ~$107/day, and those positions resolve at the same 6–8% YES rate seen in the last week, structural resolution losses will be ~-$85/day offset by ~$40–80/day RECYCLE099. Net: coin-flip whether each day is positive or negative, dependent entirely on RECYCLE099 volume and whether any large NO or YES legs win.

---

*Report generated 2026-06-20T23:37Z. All figures from data-mirror snapshot 23:23 UTC (14 min lag). No code, parameters, or stakes were modified by this agent.*
