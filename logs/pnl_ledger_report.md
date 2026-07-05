# Klaus PnL Ledger — 2026-07-05
*Generated 2026-07-05T23:37Z (snapshot age: 3 min) | System: active*

---

## § 1 — P&L EXPLAIN (UTC Day 2026-07-05)

| | |
|---|---|
| daily_start_capital | $87.171204 |
| capital_now (23:34Z snapshot) | $217.438664 |
| **Day Δ** | **+$130.267** |

### Cash-Flow Attribution

| Event | Time (UTC) | Entry Class | Gross In | Gross Out | Net PnL | Notes |
|---|---|---|---|---|---|---|
| Settlement batch 1 (prior-day band wins) | ~08:28 | WEATHER_STRUCT_BAND | **+$76.21** | — | **unknown cost basis** | cap proxy +$71; ~$5 reserve delta; multiple markets resolving together |
| Tokyo WON 101.25sh (batch 2 / ladder) | ~21:29 | WEATHER_STRUCT_BAND | **+$101.25** | — | **~+$53.66** | state_log confirmed: "Tokyo settle WON +101.25sh"; entry ~$0.47 avg (fill tape Jul 3 @0.47, Jul 4 @0.43); cap +$91 |
| Taipei YES exit099 (11sh, $0.39→$0.99) | 06:42 (buy 01:34) | WEATHER_STRUCT_BAND | +$10.89 | −$4.29 | **+$6.60** | same-day cycle; confirmed in exit099_live.jsonl |
| Moscow NO recycle099 (6sh, $0.84→$0.99) | 13:29 (buy 12:48) | WEATHER_STRUCT_BAND | +$5.94 | −$5.04 | **+$0.90** | same-day cycle; confirmed in exit099_live.jsonl |
| New maker fills — 6 cities, 8 legs | various | WEATHER_STRUCT_BAND | — | −$56.01 | PENDING | Wuhan NO/Seoul YES/2×Tokyo YES/Munich YES/Shanghai YES; all open; incl. Taipei+Moscow costs |
| UNTRACKED fills (token 3217…) | 12:48–13:29 | UNKNOWN | +$1.70 | −$9.71 | **−$8.01** | 60.69sh BUY@0.16 + 170sh SELL@0.01; bot has no tracker entry; likely legacy position resolving to near-zero; UNBOOKED in trades.jsonl |
| **TOTAL** | | | **+$195.99** | **−$65.72** | | **Net: +$130.27 ✓** |

### Cash Reconciliation
Cash flows balance to +$130.27 within $0.01 rounding. **No unexplained cash.** Capital change is fully explainable as two settlement waves + same-day exit099 cycles + UNTRACKED legacy fills.

### PnL Attribution (where cost basis is known)

| Source | Net PnL |
|---|---|
| Tokyo batch 2 (101.25sh, entry ~$0.47) | +$53.66 |
| Taipei YES exit099 | +$6.60 |
| Moscow NO recycle099 | +$0.90 |
| UNTRACKED fills (unbooked) | −$8.01 |
| **Settlement batch 1 (prior-day positions)** | **UNKNOWN — trades.jsonl required** |
| Subtotal (identified) | **+$53.15** |

**UNEXPLAINED PnL: ~$27 — MODEL DEFICIENCY.**
Cash fully reconciles. The ~$77 gap ($130.27 − $53.15) splits between batch 1 net profit and batch 1 cost recovery. Batch 1 gross was $76.21; at estimated avg entry ~$0.35, cost ~$26.67 → batch 1 pnl ~$49.54, residual model gap ~$27. Cause: trades.jsonl (26 MB, 8 084 rows) unavailable to this run; batch 1 positions' cost basis cannot be retrieved without it. This is NOT a capital discrepancy — it is an attribution limit of the no-file-access path. Manual flow: NONE detected (intraday STRUCT-BAND-Q cap readings explain all movements without a deposit signal).

### Intraday Capital Timeline (STRUCT-BAND-Q "cap" proxy)
```
00:01  $87   ← midnight reset, matches daily_start
00:06  $42   ← Jul 4 GTC reserve (~$45 pending orders)
04:58  $38   ← Taipei YES cost confirmed ($4.29)
06:45  $45   ← Taipei exit $10.89 in (+$7 net)
08:28  $116  ← SETTLEMENT BATCH 1 (+$71 available cap, $76.21 true cash)
11:17  $116  ← Tokyo/Seoul fills registering (no cap change yet)
13:00  $57   ← Jul 4 GTC confirms + Seoul/Tokyo/Munich cost confirms (−$59)
13:25  $40   ← Moscow NO buy + UNTRACKED BUY confirm (−$17); sensor seam fired ($39.69)
13:31  $41   ← Moscow/UNTRACKED exits recover partially
15:30  $36   ← Munich YES confirm
15:35  $134  ← BOT RESTART — true wallet balance read; $98 reserve over-count corrected
16:32  $130  ← Shanghai YES confirm
21:29  $221  ← SETTLEMENT BATCH 2 / TOKYO WON (+$91 cap, $101.25 true cash)
22:45  $217  ← Minor confirm (Tokyo/other)
23:31  $217  ← matches bankroll final $217.44 ✓
```

*Note: "cap" = deployable capital after GTC order reserves, not total wallet cash. The two settlement events are unambiguous step-changes against a flat baseline.*

---

## § 2 — Compounding Scoreboard

### Equity Estimate

| Component | Value | Caveat |
|---|---|---|
| Cash (bankroll.json) | $217.44 | authoritative |
| Munich YES open (ladder) | $26.07 @ $0.47 | from state_log 22:25Z; settlement <36h |
| Today's maker fills (6 legs, unresolved) | ~$21.05 at cost | Wuhan/Seoul/2×Tokyo/Munich/Shanghai |
| SELL_EXIT resting (5 legs, 41sh @ ~$0.40 est.) | ~$16.40 at cost | maker_resting_state.json; matched=0 |
| **equity_est** | **~$280.96** | |

**CAVEAT:** All open positions resolve binary (0 or 1). Range: $217.44 (all lose) to ~$280+ (all win). Cost-basis equity overstates expected value for YES legs at $0.44–0.49 probability. State_log EVOLVE at 22:25Z computed equity $222.90 (cash $196.83 + Munich $26.07, excluding maker fills); that figure predates the 21:29 Tokyo settlement. Bankroll capital since risen to $217.44 (cap confirmed at 23:31Z).

### Turn Velocity & ROI/Turn

| Metric | Today (Jul 5) | Jul 3 (prior report) | Badatmath benchmark |
|---|---|---|---|
| equity_est | $280.96 | $137.32 | — |
| fills_usd | $56.01 | $45.62 | — |
| turns/day | **0.20** | 0.33 | ~1.0 |
| ROI/turn (resolved, identified) | **~80%** | 25.4% | 10–20% |

*ROI/turn = net pnl on identified resolved legs / their cost basis. Excludes batch 1 (unknown cost). Includes UNTRACKED loss (−$8.01). If batch 1 pnl ~$49.54, blended ROI/turn across all resolved today = ($53.15 + $49.54) / ($66.63 + ~$26.67) = $102.69 / $93.30 ≈ **110%**.*

**7-day trend:** Turns down 0.33 → 0.20 (fill-rate compression: PAIR_FAV clip-guard cut the naked-YES posts 07-03→07-05; repair deployed 22:20Z today). ROI/turn dramatically up vs baseline (weather band YES convergence $0.35→$1.00 = 185% gross). Capital base 2-day change: $86.74 → $217.44 (+$130.70, +150.7%) — driven by settled band inventory, not turn velocity. Velocity is the binding constraint; capital is not.

---

## § 3 — Expected Maker Rebates

**Formula:** expected_rebate = Σ(shares × 0.05 × p × (1−p)) × 0.25 (upper bound; actual depends on pool competition)

### Today's Fills

| Leg | Shares | Price p | p×(1−p) | Est. Rebate |
|---|---|---|---|---|
| Taipei YES | 11.0 | 0.39 | 0.2379 | $0.033 |
| Wuhan NO | 1.0 | 0.44 | 0.2464 | $0.003 |
| Seoul YES | 9.0 | 0.49 | 0.2499 | $0.028 |
| Tokyo YES (11:16) | 9.0 | 0.46 | 0.2484 | $0.028 |
| Moscow NO | 6.0 | 0.84 | 0.1344 | $0.010 |
| Munich YES | 9.0 | 0.46 | 0.2484 | $0.028 |
| Shanghai YES | 9.0 | 0.44 | 0.2464 | $0.028 |
| Tokyo YES (18:51) | 9.0 | 0.44 | 0.2464 | $0.028 |
| **Total** | | | | **$0.186** |

Mid-price fills (Seoul $0.49, both Tokyo $0.46/$0.44, Munich $0.46, Shanghai $0.44) are the highest-earning per share. Moscow NO @0.84 earns 46% less per share than a mid-price fill despite larger stake.

### Cumulative Estimate

| Period | Rebate |
|---|---|
| Through Jul 3 (prior report) | $2.493 |
| Jul 4 (Seoul/Shanghai/Tokyo/Munich fills) | $0.078 |
| Jul 5 (today) | $0.186 |
| **Cumulative expected** | **$2.757** |

**FLAG — USER ACTION REQUIRED:** Cumulative expected rebate $2.757 exceeds minimum $1 payout threshold. Polymarket rebates land daily in pUSD. No rebate receipt has been recorded in any available data source. Please verify: (1) pUSD balance in your Polymarket account, (2) whether any rebate payouts have arrived since trading began. If cumulative realized payout = $0 and expected > $2, contact Polymarket support — pool share calculation may require volume thresholds not yet met, or there may be a wallet configuration issue.

---

## § 4 — Kill-Switch Proximity

### Hard Gates

| Gate | Threshold | Current | Status |
|---|---|---|---|
| Day PnL halt | < −$10 | **+$130.27** | ✅ CLEAR (+$140 above) |
| Weekly floor | capital < $75 | $217.44 | ✅ CLEAR (+$142.44 above) |
| Ruin floor | capital < $50 | $217.44 | ✅ CLEAR (+$167.44 above) |
| Daily loss from start | daily_start − $10 = $77.17 | $217.44 | ✅ CLEAR |

### Rolling WR/PF (last 20 resolved trades)

CANNOT COMPUTE — trades.jsonl not accessible to this run. Available proxy data:

- **7d realized PF: 0.09** (state_log 22:25Z: "−$96.44 PF 0.09 but −$68 of it from paths already cut 07-02/07-03")
- Active path (PAIR_FAV post clip-guard): state_log reports "co-filled pairs DO work (~+10%/pair)" but prior to clip-guard fix "one-sided YES n=10 WR 10%" (degraded mode)
- Clip-guard fix deployed **22:20Z today** — the naked-YES surface that caused WR 10% is now blocked; future resolved-leg WR should reflect genuine pair co-fills
- STWA_REGULAR disabled; BAND_NO disabled 07-02. WR/PF reflects these now-cut paths disproportionately.

**Intraday sensor event:** Ruin-floor cash-proxy hit $39.69 at ~13:25Z (cap timeline). State_log confirms: "capital $39.69 <$40 intraday while true equity $217 — conversion not loss; protective, self-resolves at redemption." Sensor was the cash-proxy surrogate for tracked capital while ladder positions exist outside risk.open_positions. NOT a genuine ruin event. Re-derivation of the ruin-floor comparator deferred to morning slot per state_log (requires touching capital plumbing while ladder positions live).

**CAVEAT — Kill-switch re-derivation pending (user acknowledged):** WR/PF floors were specified for the taker era. Current maker band book wins ~22% of YES legs by design at 4–5× payoff. PF < 0.8 must NOT trigger a halt alone in the maker era. Per prior state and state_log: kill-switch re-derivation is an open action item. Do not halt on raw WR/PF until maker-era thresholds are established.

---

## § 5 — Day Verdict

**YES — equity compounded materially. Cash +$130.27 (+149.4% vs $87.17 daily start); equity_est +$143 to ~$281 (+51.0% vs prior equity_est $137.32).**

Two weather band settlement batches drove the day: batch 1 (~08:28 UTC, prior-day positions, $76.21 gross) and the state_log-confirmed Tokyo ladder win (~21:29 UTC, 101.25sh at $1.00, $101.25 gross). exit099 added +$7.50 net. UNTRACKED legacy fills cost −$8.01 (unbooked).

**Binding constraint: settlement timing, not capital.** Turn velocity 0.20x/day remains well below the badatmath 1.0x benchmark. Today's equity gain came from prior-period inventory resolving — not from today's 8 new maker fills ($30.38 deployed, all open). Capital base is now strong ($217 cash, $281 equity), and the pair clip-guard fix deployed tonight should restore genuine co-fill economics. The next lever is isotonic refit cron (calibration gauge degenerate 3d, blocking band re-enable tree per state_log) and the ruin-floor comparator → tracked-capital upgrade (deferred from tonight).

---
*Report generated by pnl-ledger-agent | data-mirror snapshot 2026-07-05T23:34:39Z (age 3 min) | trades.jsonl: not accessible (26 MB); attribution uses shadow files, fill tape, state_log*
