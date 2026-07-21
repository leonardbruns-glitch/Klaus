# Klaus PnL Ledger — 2026-07-21 (Day-End Report)

Generated: 2026-07-21T23:37Z  
Snapshot: 2026-07-21T23:27:52Z (age: ~10 min — VALID)  
System: `klaus systemd: active` ✓  
Data source: data-mirror branch via GitHub MCP (git fetch timed out; direct API used)

---

## 1. P&L EXPLAIN (UTC day 2026-07-21)

| Item | Amount | Source |
|---|---|---|
| Capital — prior report (Jul-20 ledger) | $21.495442 | pnl_ledger_state.json |
| Capital — now (bankroll.json) | $21.495442 | bankroll.json (saved ~11:03 UTC) |
| CLOB-actual verification | $21.495442 | Morning EVOLVE 11:40Z (exact match) |
| Capital delta | **$0.00** | |

### Attribution by leg

| Leg | PnL | Evidence |
|---|---|---|
| trades.jsonl fills (ts_close in Jul-21 UTC) | $0.00 | Exec audit commit `a0050d061`: fills=0, 0 alerts |
| RECYCLE099 (exit099_live.jsonl) | $0.00 | File absent for 2026-07-21 — no convergence sells |
| STWA resolutions (WEATHER_\* in trades.jsonl) | $0.00 | Morning EVOLVE 11:40Z: "weather $0 (0 trades.jsonl WEATHER_STWA settlements)" |
| Maker rebate accrual | $0.00 | No maker fills today (see §3); maker_resting_state.json = {} |
| **Total attributed** | **$0.00** | |

**UNEXPLAINED = $0.00** — No model deficiency. Capital frozen, attribution complete.

### STWA open positions — resolution status

Three positions remain open and unresolved (confirmed zero settlements today):

| Entry date | Horizon | Cost | Tokens | Status |
|---|---|---|---|---|
| Jul-17 | d+3 | $8.060 | 4095117 / 1055101 / 1046907 | Overdue — no resolution yet |
| Jul-18 | d+2 | $3.590 | 7094108612094851 | Overdue — no resolution yet |
| Jul-19 | d+1 | $2.926 | 5717613767097074 (146.33 sh @ $0.02, MAKER) | Overdue — no resolution yet |

All three were filled as UNTRACKED positions; the bot's position tracker is blind to them. Capital is confirmed unchanged as of the 11:40Z CLOB-actual check. Evening slot (21:58Z) cites equity "$21.50" with no CLOB-actual re-run — residual uncertainty exists for the 10h window post-morning-check. Resolution, if it occurs, will appear as an unexplained capital jump in tomorrow's ledger; that will NOT be noise — flag it for investigation.

Note on Jul-19 position: 146.33 shares purchased at $0.02 = $2.926 cost. If this resolves YES, payout = $146.33 (+$143.40 net). This is the single most consequential pending event in the portfolio.

---

## 2. COMPOUNDING SCOREBOARD

### Equity estimate

| Component | Value | Confidence |
|---|---|---|
| Wallet (CLOB-actual, 11:40Z) | $21.495 | HIGH — independently verified |
| STWA open at cost (untracked) | $14.576 | LOW — cost basis only; bot is blind to these |
| **equity_est** | **$36.071** | ESTIMATE — caveat below |

**CAVEAT:** equity_est=$36.071 assumes STWA positions are worth their entry cost. True equity range:
- Floor: $21.495 (all three STWA resolve NO — total cost lost)
- Best case: $21.495 + $143.40 (Jul-19 YES) + ~$2.56 (Jul-17/18 high-price YES) ≈ $167+ 
- The Jul-19 $0.02 position creates enormous positive skew. It is the dominant risk event.

Prior $14.576 estimate is unchanged from Jul-20 ledger (no resolutions).

### Compounding metrics

| Metric | Today | Jul-20 | Benchmark (badatmath) |
|---|---|---|---|
| fills_usd | $0 | $0 | high daily |
| turns/day | 0.0 | 0.0 | ~1.0× equity/day |
| ROI/turn | N/A | N/A | ~10–20% |
| Deployed fraction | 40.4% ($14.576 / $36.071) | 40.4% | N/A |
| Open positions (tracked) | 0 | 0 | — |

**Day 2 consecutive zero-fill days.** Bot is in pure shadow/collection mode. No equity is compounding. Badatmath reference (1.0× equity/day at 10–20%/turn) is irrelevant while all paths are disarmed — there is nothing to benchmark against until a path re-arms.

---

## 3. EXPECTED MAKER REBATES

| Period | Maker fills | Expected rebate |
|---|---|---|
| Today (Jul-21) | 0 | $0.00 |
| Cumulative (all history) | unchanged | **$3.917** (upper bound) |

maker_resting_state.json = {} — no active maker quotes, no ongoing accrual.

Last maker fill: Jul-19 02:14Z — token 5717613767097074 @ $0.02, 146.33 shares (MAKER side).  
Expected rebate on that fill: 146.33 × 0.05 × 0.02 × 0.98 × 0.25 ≈ **$0.036** — already included in cumulative.

Note: This fill is at an extreme price (p=0.02), which is the LOWEST rebate region. Mid-price fills (p≈0.50) earn ~6.25× more rebate per dollar of notional. The portfolio has no mid-price maker exposure.

**ACTION REQUIRED (user):** Cumulative expected rebate $3.917 > $1 minimum payout threshold. Verify pUSD receipt in Polymarket wallet. If no payout has been received despite $3.917 accrued, contact Polymarket support. Note: actual payout depends on competing makers in the same category — $3.917 is an upper bound, not guaranteed.

---

## 4. KILL-SWITCH PROXIMITY

### Hard floors

| Trigger | Threshold | Current | Status |
|---|---|---|---|
| Day PnL halt | -$10/day | $0.00 | CLEAR |
| Weekly floor | $75 | $21.495 | BREACHED (-$53.51) — owner-waived, carry-over |
| Ruin floor | $50 | $21.495 | BREACHED (-$28.51) — owner-waived, carry-over |
| Kernel re-arm floor | $40 | $21.495 | BELOW floor — charter blocks ALL re-arms without owner approval |

### G8 sniper gate (operative re-enable gate)

| Metric | Value | Notes |
|---|---|---|
| n (post-cut shadow ticks) | 57 (56W / 1L) | +2 ticks vs morning (Jul-21: 55→57) |
| WR | 0.9825 | Point well above breakeven |
| CI-lo (95%) | 0.9071 | Source: evening EVOLVE 21:58Z |
| Breakeven (BE) | 0.9683 | Gate pass requires CI-lo ≥ BE |
| CI gap | 0.0612 | Not closing fast; ~flat vs morning (0.066→0.061) |
| Accrual rate | ~19 ticks/day (slowed from ~30/day at morning check) | Evening: 4.7/hr vs 30/day |
| ETA to n=100 | ~Jul-23 at current pace | Estimate only |

**Research audit (11:05Z today):** "G8 KILL likely at n=100 (CI-lo 86.5% vs BE 97.0%, geometrically cannot clear." Note: the 11:05Z CI-lo of 86.5% reflects n=38 data; with n=57 the CI-lo has recovered to 90.7%, which is still far below BE=96.8%. The "geometrically cannot clear" concern from the morning has moderated slightly but the fundamental gap persists.

### Path status

| Path | Status | Trigger for re-enable |
|---|---|---|
| UPDOWN sniper | CUT (Jul-19 11:26Z) | G8 gate pass (n≥100, CI-lo ≥ BE) + owner + kernel floor |
| BAND_LIVE | DISARMED (Jul-6) | Weather band trigger not met (2/5 days clear 1.10) |
| BAND_NO | DISABLED (Jul-2) | 7d WR 39.2% (rail halt) |
| STWA_REGULAR_YES | DISABLED (Jun-5) | Calibration curve issue |
| STWA_REGULAR_NO | DISABLED (Jun-11) | 0 fires in 48h while armed |
| LDA | STOPPED | Rolling-20 net -$36.39 < -$30 |
| NEG_RISK/RECYCLE | Armed but blocked | Ruin floor ($21.50 < $40 kernel) |

**CAVEAT:** WR/PF kill-switch floors from the original spec (taker era) are inapplicable to the current sniper design where WR ~98% is by construction (4-5× payoff on ~22% YES-win rate). The G8 PF-rail is the correct instrument for the sniper; traditional WR thresholds should not be used to trigger halts. Kill-switch re-derivation pending with owner.

**DISK ALERT:** 91% used (8.4G free) per evening EVOLVE. Up from 87% on Jul-20, 83% on Jul-19. Trend is +2%/day. At this rate: <8G free within 1 day, <4G free within ~3 days. Shadow logs (updown_sniper/snap_20260721.jsonl = 75MB, sniper snap 20260720 = 78MB, etc.) are the primary consumers. Owner should run cleanup or archive rotation before disk becomes a service risk.

---

## 5. DAY VERDICT

**FLAT** — equity neither compounded nor declined. Day PnL = **$0.00** (0.00%).

Wallet capital confirmed $21.495442 (CLOB-actual 11:40Z); unchanged from Jul-20. Day 2 of consecutive zero-fill mode post-PF-rail cut (Jul-19 11:26Z).

**Binding constraint:** All live trading paths disarmed. Equity $21.50 is below the $40 kernel floor; charter requires owner approval for any re-arm regardless of gate status. G8 gate (n=57, CI-lo 0.907 vs BE 0.968) is still collecting — neither pass nor kill branch triggered.

**Pending event:** 3 STWA positions ($14.576 total at cost) remain unresolved. The Jul-19 position (146.33 shares at $0.02) carries +$143 YES upside. Unexpected capital change in tomorrow's ledger, if any, should be attributed to STWA resolution first before flagging as MODEL DEFICIENCY.

**Next decision gate:** G8 n≥100 (~Jul-23 at current accrual rate). Research audit (11:05Z) forecasts KILL; CI is currently recovering but mathematically unlikely to clear BE by n=100 at 56W/1L. Owner should prepare for the kill or conditional-restart decision by Jul-23.
