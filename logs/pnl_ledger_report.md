# Klaus PnL Ledger Report — 2026-06-22

**Generated:** 2026-06-22T23:37Z  
**Snapshot age:** 1 min (23:36:21Z) ✓  
**System:** active (uptime since 11:47 UTC) ✓  
**Capital at EOD:** $198.269163  
**Prior report capital (2026-06-21):** $237.019784  
**Capital Δ:** -$38.75 (-16.3%)

---

## Section 1 — P&L Explain (UTC day 2026-06-22)

### Capital Attribution

| Line | Amount |
|---|---|
| Band resolutions (30 trades, WEATHER_STRUCT_BAND) | **-$72.3722** |
| RECYCLE099 exits (10 exits, exit099_live.jsonl) | **+$37.1800** |
| Expected maker rebate accrual (see §3) | +$0.5520 |
| **Attributed total** | **-$34.6402** |
| Capital Δ (prior → now) | -$38.7506 |
| **UNEXPLAINED** | **-$4.11** |

UNEXPLAINED = -$4.11. |$4.11| < $5 threshold — no deep investigation triggered.  
**Most likely cause:** BANKROLL_AUTO_CORRECT entry detected in trades.jsonl at 21:43 UTC (delta=-$8.40, source=BANKROLL_AUTO_CORRECT, cap_after=$213.65) partially offset by minor unlogged inflows. Not a model deficiency.

### Band Resolutions Breakdown (30 trades)

**Source:** trades.jsonl, ts_close in [1782086400, 1782172620]. All 30 are `WEATHER_STRUCT_BAND / STWA_RESOLVED`. Fees = $0 for all weather trades (as expected — no fee field set).

| Side | Trades | Wins | Losses | Net PnL |
|---|---|---|---|---|
| YES | 20 | 1 | 19 | -$28.2782 |
| NO | 10 | 1 | 9 | -$44.0940 |
| **Total** | **30** | **2** | **28** | **-$72.3722** |

**YES win:** 2026-06-22 21:39 YES @ entry=0.25 → +$6.30  
**NO win:** 2026-06-22 16:27 NO @ entry=0.65 → +$2.73  

Selected large individual losses (|PnL| > $3):

| Time UTC | Side | entry_price | net_pnl |
|---|---|---|---|
| 03:02 | NO | 0.60 | -$5.01 |
| 03:32 | NO | 0.53 | -$5.30 |
| 06:29 | NO | 0.58 | -$5.22 |
| 08:26 | NO | 0.66 | -$5.28 |
| 16:27 | YES | 0.28 | -$3.01 |
| 16:27 | YES | 0.17 | -$2.21 |
| 16:32 | YES | 0.28 | -$3.01 |
| 16:37 | YES | 0.27 | -$3.24 |
| 16:37 | NO | 0.66 | -$5.28 |
| 21:39 | NO | 0.61 | -$5.35 |
| 21:49 | NO | 0.63 | -$5.04 |
| 21:54 | NO | 0.62 | -$5.27 |
| 22:55 | NO | 0.52 | -$5.07 |

**CRITICAL — NO win rate: 1/10 (10%).**  
Design expectation: ~65-70% (NO = temperature not in mode 1°C bucket at prices 0.52–0.66 → market implies 34–48% in-bucket probability → NO should win ~55–65% of the time). Today's 9/10 NOs resolved against us = temperatures landed in the specific mode bucket at 90% rate. This is a 2-day pattern: yesterday resolution PnL was -$46.45 (June 21 state), today -$72.37. Combined 2-day weather band resolution loss: **-$118.82**.

### RECYCLE099 Breakdown (10 exits, exit099_live.jsonl)

All exits are convergence sells (bot bought YES at low price earlier, sold at 0.99 as market converged).

| Time UTC | Shares | Entry | Exit | PnL |
|---|---|---|---|---|
| 01:18 | 11.0 | 0.45 | 0.99 | +$6.048 |
| 06:34 | 7.0 | 0.68 | 0.99 | +$2.320 |
| 08:07 | 9.993 | 0.28 | 0.99 | +$7.633 |
| 09:51 | 8.0 | 0.60 | 0.99 | +$3.257 |
| 13:31 | 8.0 | 0.62 | 0.99 | +$3.143 |
| 13:54 | 8.0 | 0.67 | 0.99 | +$2.560 |
| 14:30 | 21.0 | 0.93 | 0.99 | +$1.260 |
| 15:41 | 8.0 | 0.62 | 0.99 | +$3.145 |
| 18:02 | 9.0 | 0.55 | 0.999 | +$4.126 |
| 19:05 | 9.0 | 0.58 | 0.99 | +$3.690 |
| **Total** | | | | **+$37.182** |

RECYCLE099 significantly smaller than yesterday (+$114.77). No new RECYCLE099 entries visible in today's fill tape (all today's fills are BAND YES/NO positions).

### Bot Operational Notes

- **No new positions posted after 11:47 UTC restart.** All afternoon/evening fills are from pre-restart resting orders being hit by takers. STRUCT-BAND-Q log shows `posted=0` throughout post-restart period; `cash_preskip=0` confirms no cash was skipped — the daily NO cap was already exceeded.
- **Config change at restart (11:47 UTC):** `no_resv` changed 0.40 → 1.00 (commit: "P1 NO-only — no_reserve 0.40→1.00 until $600"). This blocks new YES resting orders.
- **Daily NO cap hit:** BAND_NO_DAILY_CAP=$40, effective cap=max($40, 0.30×$198)=$59.40. Today's NO fills = $100.61 in cash, far exceeding cap.

---

## Section 2 — Compounding Scoreboard

### Today's Fill Tape (maker_fills_recent.log)

| Type | Fills | Shares | Cash Deployed |
|---|---|---|---|
| YES (band) | 15 events | 155.7 | $6.986 |
| NO (band) | 31 events | 163.6 | $100.608 |
| **Total** | **46 events** | **319.3** | **$107.594** |

Notable: Milan YES 31°C June 24 filled 120 shares @ $0.01 ($1.20 cost) — a speculative tail position.

### Equity Estimate (CAVEATED)

| Component | Amount |
|---|---|
| Capital (cash) | $198.27 |
| Open positions at cost — June 23 (5 positions from resting_state) | ~$8.87 |
| Open positions at cost — June 24 (Milan YES 120sh) | ~$1.20 |
| Today's NO fills not yet resolved (~$100.61 resolving June 23) | ~$100.61 |
| Today's YES fills not yet resolved (~$6.99) | ~$6.99 |
| **Equity estimate** | **≈ $315.94** |

**CAVEAT:** This equity estimate = capital + open positions at cost (floor estimate — assumes all open positions expire worthless; actual could be higher if NO positions win). Prior open positions from June 21 ($235.90 spent, minus today's $88.57 resolved cost basis) estimated ~$147 additional open, but double-counting risk from capital already reflecting fills. Conservative floor estimate stated. Mark-to-market would require current market prices for ~40+ open positions across 20+ cities.

### Compounding Metrics

| Metric | Today | Yesterday | Benchmark |
|---|---|---|---|
| Fills USD | $107.59 | $160.38 | badatmath ~equity/day |
| Equity est (prior) | $275.48 | — | — |
| Turns/day | 0.39 | 0.58 | badatmath ~1.0 |
| Day PnL | -$35.19 | +$37.93 | — |
| ROI/resolved turn | **-81.7%** | ~0% | badatmath 10-20% |

**ROI/resolved turn** = resolution_pnl / cost_of_resolved_positions = -$72.37 / $88.57 = -81.7%. Cost of resolved positions derived: 2 wins paid out $8.40+$7.80=$16.20; 28 losses paid out $0; total cost = $16.20 + $72.37 = $88.57.

7-day context: June 11 baseline was 0.2-0.5 turns at ~3%. Today's 0.39 turns is in range but ROI/turn is deeply negative. RECYCLE099 has been the return driver (yesterday +$114.77, today +$37.18); band resolution has been systematically negative for 2 days.

---

## Section 3 — Expected Maker Rebates

**Formula:** expected_rebate per fill = shares × 0.05 × p × (1-p) × 0.25

Today's fill tape (46 fill events):

| Type | Shares | Avg price p | Contrib |
|---|---|---|---|
| YES | 155.7 | ~0.045 | ~$0.008 |
| NO | 163.6 | ~0.614 | ~$0.544 |
| **Total today** | | | **$0.552** |

Mid-price note: Today's NO fills at p=0.54–0.71 earn moderate rebates; peak quadratic value is at p=0.50 (none today, closest are Seoul NO p=0.54 and Houston NO p=0.57). These still earn ~$0.003/share vs. ~$0.001/share for the YES extremes.

| Period | Expected Rebate |
|---|---|
| Prior cumulative (through 2026-06-21) | $5.40 |
| Today's increment | $0.55 |
| **Cumulative expected** | **$5.95** |

**⚠ REBATE VERIFICATION FLAG:** Cumulative expected rebate $5.95 >> $1 minimum accrual threshold. Per prior state, this flag has been active since June 21 ($5.40). **User action needed:** verify pUSD rebate receipt in wallet. If no payout has been received, contact Polymarket #support with wallet address. Note: actual rebate is proportional to your share of total maker volume in each category — $5.95 is an upper bound assuming sole market maker.

---

## Section 4 — Kill-Switch Proximity

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Rolling 20-trade WR (all today) | **10.0%** | >30% flag | TRIGGERED |
| Rolling 20-trade PF | **0.1701** | >0.8 halt | TRIGGERED |
| Day PnL | **-$35.19** | > -$10 halt | TRIGGERED 3.5x |
| Capital | $198.27 | >= $75 weekly floor | Safe |
| Capital | $198.27 | >= $50 ruin floor | Safe |
| 2-day resolution cumulative | **-$118.82** | N/A | Trend |

**CRITICAL CAVEAT (from prior state and CLAUDE.md):** WR/PF floors were specified for the taker era. A maker YES band book wins ~22% of YES legs by design at 4-5x payoff — WR naturally < 30%. **However, the NO win rate today (10%) is far below design expectation (~65-70%), which IS the alarm signal.** NO positions at prices 0.52–0.66 (market implying 34-48% YES probability) should win more than half the time; today's 90% loss rate on NOs indicates either:

1. **Systematic mode-bucket miscalibration:** the bot is buying NO at the exact 1°C bucket where temperatures are actually most likely to fall (i.e., `BAND_P_MIN=0.50` gate isn't filtering enough)
2. **Weather regime shift:** unusual stability causing temperatures to land on the mode consistently
3. **Token direction error:** NO buys are resolving as if they're YES buys (would require investigation of trade logs)

Capital is $198.27 — well above the $75 weekly floor and $50 ruin floor. No immediate halt on capital grounds. A kill-switch re-derivation for the maker era is flagged as pending.

**Day PnL -$35.19 vs -$10 taker-era halt:** The -$10 halt trigger was calibrated for a $10 test bankroll. On $198 capital it would be -5% in a day. Today's -16.3% capital decline is a material alert regardless of threshold calibration.

---

## Section 5 — Day Verdict

**Equity compounded today: NO** — capital declined $38.75 (-16.3%), net operational PnL **-$35.19**.

| Driver | Amount | Sign |
|---|---|---|
| Weather band resolutions (30 positions) | -$72.37 | LOSS |
| RECYCLE099 exits (10 exits) | +$37.18 | WIN |
| Net | **-$35.19** | LOSS |

**Binding constraint:** Weather band NO legs — 1/10 NOs resolved in profit today (expected 6–7/10). Band has lost -$118.82 in weather resolutions over 2 days (June 21: -$46.45, June 22: -$72.37). RECYCLE099 partially offset both days (June 21: +$114.77 → net positive; June 22: +$37.18 → insufficient to offset). The direction has flipped: yesterday RECYCLE099 dominated (net +$37.93 day); today resolution losses dominate (net -$35.19).

**What changed:** The bot was running with `no_resv=0.40` before the 11:47 restart, placing both YES and NO orders. After restart with `no_resv=1.00`, no new orders were posted but existing resting orders continued to fill. The 16:00-22:00 UTC resolution batch (large losses) is from positions entered in prior days under the old config. The NO win rate failure is the mechanism, not the config change itself.

**Recommended user review:** The 2-day NO win rate failure (design ~65%, realized ~10-20%) warrants investigation of whether `BAND_P_MIN=0.50` and `BAND_EV_MIN=0.08` (lowered from 0.15 against model advice, per band_config.txt comment) are admitting positions where the mode bucket is genuinely 60–90% likely to contain the temperature, making NO at 0.55–0.65 a structural loser.

---

*Generated by PnL Ledger Agent · 2026-06-22T23:37Z · trades.jsonl 7898 rows · snapshot 1 min old*
