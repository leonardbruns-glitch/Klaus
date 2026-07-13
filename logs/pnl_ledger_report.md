# Klaus PnL Ledger — 2026-07-13 UTC
_Generated: 2026-07-13T23:37Z | Snapshot: 2026-07-13T23:36:35Z (fresh, 1 min) | Service: active_

---

## SECTION 1 — P&L EXPLAIN

### Capital Frame

| Item | Value | Source |
|---|---|---|
| Day start capital | $103.824444 | bankroll.json `daily_start_capital` (set at midnight UTC) |
| Capital now | $34.7427 | bankroll.json `capital` (saved 23:39 UTC) |
| **Day P&L (raw)** | **−$69.082** | Delta above |
| Day vs prior report (Jul 10) | −$128.42 | $163.16 → $103.82 (Jul 10→13 start) + today |
| Cumulative total_pnl | −$75.397 | bankroll.json `total_pnl` |

Note: `bankroll.json` is not authoritative for manual flows. The -$69.08 day figure assumes no user deposit/withdrawal on Jul 13. **FLAG**: if any deposit/withdrawal occurred today, this figure is wrong — user must confirm.

---

### Attributed P&L by Leg

All fills are **UNTRACKED** (no tracker entry, no open position) and appear as ORPHAN exits in trades.jsonl with `entry_price: 0.0` and `net_pnl: 0.0`. Attribution uses maker_fills_recent.log (7d tape) cross-referenced with order_lifecycle.jsonl. The `entry_class` field is absent from all 8,157 rows in trades.jsonl — classification below is inferred from token/price/size signatures.

| Time UTC | Class | Side | Shares | Entry $ | Exit $ | Attributed Net | Confidence |
|---|---|---|---|---|---|---|---|
| 03:40 | SPRINT_LADDER | BUY_YES | 51.50 | 0.449 | ~0 (inferred) | **−$23.12** | ESTIMATE |
| 05:10 | SPRINT_LADDER | BUY_YES | 45.00 | 0.526 | ~0 (inferred) | **−$23.67** | ESTIMATE |
| 10:49 | UPDOWN_SNIPER | BUY_YES | 39.25 | 0.990 | 0.920 | **−$2.89** | CONFIRMED |
| 12:29 | UPDOWN_SNIPER | BUY_YES | 5.50 | 0.960 | unresolved | **?** | UNKNOWN |
| 12:34 | WEATHER_BAND_NO (maker) | BUY_NO | 35.17 | 0.030 | unresolved | **?** | UNKNOWN |
| 12:35 | UPDOWN_SNIPER | BUY_NO | 5.50 | ~0.03 (inferred) | 0.980 | **~+$5.2** | ESTIMATE |
| 16:49 | UPDOWN_SNIPER | BUY_YES | 5.40 | 0.970 | 0.730 | **−$1.39** | CONFIRMED |
| 20:13 | UPDOWN_SNIPER | BUY_NO | 6.00 | 0.970 | 0.960 | **−$0.06** | CONFIRMED |
| 20:43 | UPDOWN_SNIPER | BUY_YES | 5.00 | 0.960 | 0.950 | **−$0.22** | CONFIRMED |
| 22:09 | UPDOWN_SNIPER | BUY_YES | 5.335 | 0.970 | 0.950 | **−$0.21** | CONFIRMED |
| 22:59 | UPDOWN_SNIPER | BUY_NO | 5.50 | 0.920 | 0.950 | **+$0.17** | CONFIRMED |

**UPDOWN_SNIPER subtotal (confirmed):** −$4.60 (6 confirmed round-trips, 1 win / 5 losses)
**SPRINT_LADDER subtotal (estimated):** −$46.79 (both shots assumed full-loss; consistent with "0W/7L −$165 since Jul 11" ladder record)

**Total attributed: ~−$51.4** (point estimate assuming ladder resolves 0)

---

### Unexplained P&L

| Item | $USD |
|---|---|
| Capital delta (ground truth) | −69.082 |
| Attributed (ladder + sniper confirmed/estimated) | −51.4 |
| **UNEXPLAINED** | **−$17.7** |

**|UNEXPLAINED| = $17.7 > $5 → Investigation required.**

Most likely causes (ranked):

1. **Prior-session tracker-restart positions resolving today** (PRIMARY): Tracker-restart bug confirmed in prior_state. PID 871954 ran Jul 12 00:00–22:06 UTC. Any maker-resting band or STWA positions opened in that session would surface as CONFIRMED fills without tracker entries when they resolved. These would not appear in today's maker_fills_recent.log if the fill event was logged by the prior PID but the resolution event fell today. Volume consistent: $17.7 is within one or two large untracked band fills.

2. **Sprint Ladder exit not at zero**: The ladder exit price is estimated as 0. If a ladder shot partially resolved (e.g., weather condition DID occur on one city), the actual loss would be lower and the unexplained gap would be larger. Conversely, if ladder exit price > 0, estimated loss < actual, implying more unexplained P&L.

3. **12:29 YES + 12:34 NO open legs**: UPDOWN YES 5.5sh @0.96 and band NO 35.17sh @0.03 have no matching exits in today's log. If YES resolves to 0: −$5.28 added loss. If NO resolves to 0: −$1.05 added loss (band NO at 0.03 ≈ ~97% YES probability; likely also lost).

4. **Manual flows**: Cannot rule out without user confirmation. **FLAG for user.**

**ASSESSMENT: NOT noise. PRIMARY cause = tracker-restart bug (MODEL DEFICIENCY), not manual flows, but manual flows must be user-verified.**

---

## SECTION 2 — COMPOUNDING SCOREBOARD

### Equity Estimate

| Item | Value | Caveat |
|---|---|---|
| Cash (bankroll.json) | $34.743 | Authoritative for cash |
| Resting maker orders | $0.00 | maker_resting_state.json = `{}` |
| Open positions | $0.00 | system_status: 0 open positions at 23:36 UTC |
| **Equity estimate** | **$34.743** | Cash floor only. Resting-order cost included only if mirrored. Bot restart at 22:06 UTC clears any pre-restart open-position state. |

### Fills & Turns

| Metric | Value | Method |
|---|---|---|
| BUY-side notional (entries) | ~$118.62 | 2 ladder ($46.79) + 8 UPDOWN-SNIPER entries (~$71.83), all UNTRACKED |
| SELL-side notional (exits) | ~$66.22 | 7 ORPHAN exits via order_lifecycle.jsonl |
| Average equity during day | ~$69.28 | ($103.82 + $34.74) / 2 |
| **Turns/day** | **~1.71×** | $118.62 / $69.28 avg equity |
| Gross P&L | −$69.08 | Capital delta |
| **ROI/turn** | **~−40%** | −$69.08 / ($69.28 × 1.71) |

**CAVEATS**: Equity denominator uses a simple average; intraday capital was non-linear (large drops at ladder resolution). Turns figure is a lower bound — untracked prior-session fills not captured in maker_fills_recent.log are excluded.

### 7-Day Trend vs Benchmark

| Period | Capital | Day PnL | Turns (est) | ROI/turn |
|---|---|---|---|---|
| Jul 10 (last real report) | $163.16 | — | — | — |
| Jul 11 (ABORT day 1) | ~$165.73 → ? | unknown | unknown | unknown |
| Jul 12 (ABORT day 2) | $165.73 → $103.82 | −$61.91 | unknown | negative |
| **Jul 13 (today)** | $103.82 → $34.74 | **−$69.08** | **~1.71×** | **−40%** |

**Benchmark**: badatmath ~1.0× equity/day at 10-20%/turn. Our Jun 11 baseline: ~0.2-0.5 turns at ~3%.

Today's turn rate (1.71×) exceeds benchmark but ROI/turn is sharply negative. High turnover amplifying losses, not returns. The sprint ladder contributed outsized notional (2 large shots at $23-24 each) with zero confirmed wins since Jul 11.

---

## SECTION 3 — EXPECTED MAKER REBATES

### Today's Maker Fills

| Time | Token (short) | Side | Shares | Price p | p×(1−p) | Est. Rebate |
|---|---|---|---|---|---|---|
| 12:34 | 9373... | BUY_NO (MAKER) | 35.17 | 0.030 | 0.0291 | $0.013 |

Formula: `shares × 0.05 × p × (1−p) × 0.25`

**Today's expected maker rebate: $0.013** (negligible; p=0.03 is near-extreme where fee earnings collapse)

Note: BAND_LIVE=False since Jul 6. Maker fills today appear to be residual from prior sessions or UPDOWN-SNIPER band overlap. No new maker-band fills expected while live flag is off.

### Cumulative Expected Rebates

| Period | Expected |
|---|---|
| Through Jul 10 (carried from prior state) | $3.17 |
| Jul 11–12 (untracked, prior state estimate) | $0.22 |
| Jul 13 (today) | $0.01 |
| **Cumulative total (upper bound)** | **$3.40** |

**⚠️ USER ACTION REQUIRED**: Cumulative expected rebate $3.40 exceeds the $1.00 pUSD minimum payout threshold. Actual rebate = pool-share of Polymarket maker category fees — $3.40 is an upper bound, not a guarantee. If no pUSD rebate has been received since band trading began (Jun 17), user should verify wallet for pUSD deposits. Payouts land daily in pUSD; if none received despite continuous band activity Jun 17–Jul 6, there may be an eligibility or category-mapping issue.

Mid-price fills (p near 0.5) earn quadratically more — all today's maker fills were at p=0.03 (near-extreme), earning ~$0/fill. The bulk of rebate expectation ($3.17) accumulated during the Jun band era when YES bids were posted at 0.10–0.45.

---

## SECTION 4 — KILL-SWITCH PROXIMITY

| Switch | Value | Floor | Status |
|---|---|---|---|
| Day P&L vs −$10 halt | −$69.08 | −$10 | **BREACHED ×6.9** |
| Capital vs ruin floor ($89.16 in live config) | $34.74 | $89.16 | **BREACHED** |
| Capital vs 50% × 30d-HW ($222.90) | $34.74 | $111.45 | **BREACHED** |
| Capital vs CLAUDE.md max drawdown ($75) | $34.74 | $75 | **BREACHED** |
| Equity as % of 30d-HW | 15.6% | 50% | **BREACHED** |
| EVOLVE rail action | MIN_LOCKOUT reverted | — | **ACTIVE — 0 orders since 22:06 UTC** |
| SPRINT_LADDER | 0W/7L −$165 since Jul 11 | — | **DISARMED** |
| BAND_LIVE | False | — | Disarmed Jul 6 |
| BAND_NO_ENABLED | False | — | Disarmed Jul 2 |
| LDA | STOP (rolling-20 −$36.39) | −$30 | Stopped |
| UPDOWN_SNIPER | 1W/5L today visible | — | Live but EVOLVE-locked |

### Rolling 20-Trade WR / PF

Rolling 20 from prior_state.json (last known good): WR=40.0% (8/20), PF=0.08.
These 20 trades are from Jul 6 band wind-down cluster and are now 7 days old. PF=0.08 is a **CRITICAL BREACH** of the 0.8 halt threshold.

Today's UPDOWN-SNIPER results add: 1W/5L visible = 16.7% WR on confirmed round-trips. If added to rolling 20: estimated rolling WR ≈ 36% (falling), PF worsens.

**⚠️ IMPORTANT CAVEAT**: The WR/PF kill-switch floors (30% WR, PF 0.8) were specified for the taker-era BTC/ETH/SOL momentum strategy. UPDOWN-SNIPER is a certainty-cell strategy — it buys at extreme prices (0.92-0.99) and holds until resolution or stop-out. WR is structurally lower (many small losses, occasional large wins). **Do not recommend halt on WR alone.** The relevant kill signal here is the EVOLVE rail (equity below 50% of 30d-HW), which has already fired and locked the bot.

**Kill-switch re-derivation proposal remains pending with user.**

### Current Operational State

All major strategies disabled or locked as of 23:36 UTC:
- MIN_LOCKOUT_LIVE reverted → sniper cannot open new positions
- SPRINT_LADDER disarmed
- BAND_LIVE=False, BAND_NO_ENABLED=False
- LDA in STOP
- **Bot is in de facto shutdown with 0 open positions and 0 resting orders**

---

## SECTION 5 — DAY VERDICT

**Equity compounded today: NO. −66.5% from start ($103.82 → $34.74).**

Binding constraint: SPRINT_LADDER adversarial resolutions (primary — ~$46.79 estimated loss from 2 shots, consistent with 0W/7L history). Secondary: UPDOWN_SNIPER edge is negative at the current certainty-cell threshold (5 losses, 1 winner on confirmed round-trips today; large 39sh position at 10:49 lost $2.89 on a 0.99 entry priced with near-zero fee margin).

The 16:49 trade (BUY YES @0.97 → SELL @0.73, −$1.39) was a severe adverse move: price dropped from 0.97 to 0.73 in seconds, suggesting the sniper is not reliably entering at resolution-edge and is taking directional risk, not certainty risk.

**Three consecutive days of significant loss (Jul 11 unknown, Jul 12 −$61.91, Jul 13 −$69.08). EVOLVE rail has fired correctly. Bot is locked. Capital at $34.74 is 15.6% of 30d peak.**

**Five losing sessions since last real report (Jul 10). The sprint ladder configuration is demonstrably broken (0W/7L). UPDOWN-SNIPER requires re-evaluation before any capital deployment resumes.**

---

_Data sources: bankroll.json, maker_fills_recent.log, order_lifecycle.jsonl, band_struct_lite.jsonl (168 rows, live=False), lda_status.txt, system_status.txt, integrity_report.json, prior ledger state (2026-07-13 ABORT). trades.jsonl: 7 ORPHAN rows, entry_class field absent in all 8,157 rows (MODEL DEFICIENCY). exit099_live.jsonl: not present for 2026-07-13._
