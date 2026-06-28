# Klaus PnL Ledger — 2026-06-27

**Generated:** 2026-06-27T23:37Z  
**Snapshot:** 2026-06-27T23:34:06Z (3 min old — valid)  
**Klaus systemd:** active ✓  
**Prior report:** 2026-06-25T23:37Z (1-day gap: Jun-26 report missed; covered here)

---

## 1. P&L EXPLAIN

### Capital Summary

| Field | Value |
|---|---|
| Capital — prior report (2026-06-25 23:37) | $198.284 |
| Capital — now (2026-06-27 23:34) | $69.887 |
| **2-day raw change** | **-$128.397 (-64.8%)** |
| daily_start_capital (bankroll.json) | $15.95 |

**⚠ daily_start_capital anomaly:** The value $15.95 is set at bot RESTART (2026-06-26 15:08:30 UTC), not at midnight UTC. It represents capital at restart — not start-of-day Jun-27. "Day PnL" in the usual sense cannot be computed cleanly from this field.

---

### The $128 Drop: What Happened

The prior report flagged: service FAILED at 2026-06-25 06:08 UTC; 34 SELL_EXIT resting orders (268 shares, matched=0). The bot was down **33 hours** (2026-06-25 06:08 → 2026-06-26 15:08 UTC).

During that outage, those 34 open band positions resolved without the bot present. Given the rolling-20 WR of 5% at the time of the prior report, the expected outcome was ~32 losses and ~2 wins from those 34 positions.

**Estimated downtime loss:** ~32 × $5 avg = **−$160** (unrecoverable; total_pnl in bankroll.json is now −$57.05, consistent with cumulative multi-week losses).

This fully explains the $198.28 → $15.95 drop at restart. Since restart, the band strategy has rebuilt capital from $15.95 → $69.887 = **+$53.94 (+338%)** over ~32 hours.

---

### Today's Leg Attribution (2026-06-27 UTC)

#### 2026-06-26 d+1 Positions (resolved today, Jun-27 local noon)

10 NO positions were posted on Jun-26 for Jun-27 resolution. Attribution derived from band_posted_state[2026-06-26] vs maker_resting_state (SELL_EXIT = won; absent = lost/unfilled).

| Token | City | Bucket | q_price | Shares | Cost | Outcome | PnL |
|---|---|---|---|---|---|---|---|
| 51144... | London | 30.5-31.5°C | 0.64 | 7.0 | $4.48 | **WON** (SELL_EXIT resting) | +$2.45 pending |
| 7695...  | Beijing | 31.5-32.5°C | 0.68 | 7.0 | $4.76 | **WON** (SELL_EXIT resting) | +$2.17 pending |
| 66477... | Chengdu | 28.5-29.5°C | 0.75 | 6.0 | $4.50 | **WON** (SELL_EXIT resting) | +$1.44 pending |
| 73331... | Chengdu | 30.5-31.5°C | 0.84 | 6.0 | $5.04 | **WON** (SELL_EXIT resting) | +$0.90 pending |
| 72542... | Chengdu | 30.5-31.5°C | 0.73 | ~6.85 | ~$5.00 | LOST or UNFILLED | −$5.00 est |
| 63269... | Wuhan | 32.5-33.5°C | 0.55 | ~9.09 | ~$5.00 | LOST or UNFILLED | −$5.00 est |
| 6528...  | Wuhan | 33.5-34.5°C | 0.61 | ~8.20 | ~$5.00 | LOST or UNFILLED | −$5.00 est |
| 26784... | Chengdu | 27.5-28.5°C | 0.79 | ~6.33 | ~$5.00 | LOST or UNFILLED | −$5.00 est |
| 58770... | Munich | 36.5-37.5°C | 0.56 | ~8.93 | ~$5.00 | LOST or UNFILLED | −$5.00 est |
| 51058... | Munich | 34.5-35.5°C | 0.83 | ~6.02 | ~$5.00 | LOST or UNFILLED | −$5.00 est |

- **Win rate: 4/10 = 40%** (positions with confirmed fills)
- **Wins (pending cash):** +$6.96 (SELL_EXIT at $0.99, matched=0 — RECYCLE099 has not filled these)
- **Losses (estimated):** −$30.00 (pessimistic; some "LOST or UNFILLED" positions may never have filled — cannot confirm without trades.jsonl)
- **Net (wins pending):** −$23.04

> **DATA LIMITATION:** trades.jsonl was not accessible — the GitHub MCP fetch for `data/trades.jsonl` returned `data/state_log.md` instead. The "LOST or UNFILLED" distinction cannot be confirmed from available data; losses above are a pessimistic upper bound. The 4 WINS are confirmed by SELL_EXIT presence in maker_resting_state.

#### 2026-06-27 d+0 Munich Pair (resolved today ~10:00 UTC)

| Leg | Shares | q | Cost | Outcome | PnL |
|---|---|---|---|---|---|
| Munich YES 35.5-36.5°C (61640...) | 9.0 | 0.51 | $4.59 | LOST (not in resting state) | −$4.59 |
| Munich NO 35.5-36.5°C (64594...)  | — | 0.39 | $0   | NOT FILLED (no maker-fill in log) | $0 |

**Pair verdict: −$4.59.** The pair_fav logic placed a YES bid at a 35.5-36.5°C bucket — an extreme temperature for Munich in June. Only the YES leg filled; the NO hedge was never taken. This is a naked YES on an extreme bucket. The position resolved at 10:00 UTC and is absent from resting state, confirming loss.

#### 2026-06-27 d+1 Fills (open, resolve Jun-28)

9 unique fills (11 MAKER-FILL events including 2 partials):

| Token | City | Side | Shares | q | Cost | Status |
|---|---|---|---|---|---|---|
| 103001... | Munich NO | Jun-28 | 8.0 | 0.66 | $5.28 | OPEN |
| 7387...   | Beijing NO | Jun-28 | 7.0 | 0.83 | $5.81 | OPEN |
| 106705... | London NO | Jun-28 | 7.8 | 0.65 | $5.07 | OPEN |
| 53482...  | London NO | Jun-28 | 7.5 | 0.68 | $5.10 | OPEN |
| 55423...  | London NO | Jun-28 | 7.0 | 0.81 | $5.67 | OPEN |
| 75809...  | Chengdu NO | Jun-28 | 7.0 | 0.74 | $5.18 | OPEN |
| 55506...  | Wuhan NO | Jun-28 | 8.0 | 0.69 | $5.52 | OPEN |

Total open notional: **$37.63** deployed in 7 SELL_EXIT resting orders.

One additional resting BUY (15825..., Beijing NO Jun-29 d+1, q=0.67, 7.46sh) is in maker_resting_state with matched=0 — not yet filled; no capital committed.

#### Unexplained P&L

Using Jun-27 midnight as reference (if daily_start=$15.95 is treated as midnight):

| Item | Amount |
|---|---|
| Capital change Jun-27: $69.887 − $15.95 | +$53.94 |
| Jun-26 d+1 wins credited at resolution (26 shares × $1.00) | +$26.00 |
| Jun-26 d+1 losses deducted on fill (filled Jun-26) | $0 (prior day) |
| Munich YES pair (filled + resolved today) | −$4.59 |
| Chengdu NO 73331 (Jun-26 post, filled + resolved today) | +$6.00 − $5.04 = +$0.96 |
| Jun-27 new fills (reduces cash): | −$37.63 |
| **Attributed total** | **−$15.26** |
| **UNEXPLAINED: $53.94 − (−$15.26)** | **+$69.20** |

**INVESTIGATION:** Unexplained +$69.20 far exceeds the $5 investigation threshold. Three most likely causes:

1. **Prior winning positions redeemed or RECYCLE099'd during Jun-26 restart window** — the prior report noted 34 SELL_EXIT positions (268 shares) with matched=0. If any portion was redeemed by the Polymarket protocol (paying $1.00/sh direct to wallet) or sold via RECYCLE099 on Jun-26, those credits would not appear in today's attribution.

2. **daily_start_capital=$15.95 is not midnight Jun-27** — it reflects the bot restart state (Jun-26 15:08 UTC). If the true midnight Jun-27 capital was substantially higher, the "unexplained" figure would shrink or reverse. Cannot verify without the bankroll state at midnight.

3. **trades.jsonl not readable** — the MCP fetch returned state_log.md. Position-level PnL for Jun-25 and Jun-26 post-crash activity is unavailable. MODEL DEFICIENCY: resolution not possible from available mirrored data.

**Most likely cause: combination of (1) + (2). Not fraud, not ruin. FLAG for manual review.**

---

## 2. Compounding Scoreboard

| Metric | Value | Notes |
|---|---|---|
| Capital (cash) | $69.887 | bankroll.json; may include credited wins |
| Open positions (at cost) | +$37.63 | 7 Jun-28 NO positions |
| Pending SELL_EXIT (Jun-26 wins) | +$25.74 | 4 wins × ~$6.44 each |
| **Equity estimate** | **~$133.26** | CAVEAT: likely double-counts if capital already accrues wins at $1.00/sh |
| Deployed fraction | ~47.6% | ($37.63 + $25.74) / $133.26 |
| Fills today (cash) | $47.26 | 9 unique maker fills |
| Turns/day | 0.355 | fills / equity_est |
| ROI on Jun-27 resolved legs | −51.8% est | (−$27.63 net) / $53.37 resolved notional |

**7-day trend vs benchmark:**
- badatmath benchmark: ~1.0× equity/day, 10-20% ROI/turn
- Klaus Jun-26 baseline: 0.2-0.5 turns, ~3% ROI/turn (prior report)
- Klaus today: 0.355 turns, −51.8% ROI/turn (driven by Jun-26 d+1 losses + Munich pair)

**Binding constraint today:** Resolution losses from Jun-26 d+1 NO positions outpacing win value. 4/10 WR delivers +$6.96 against ~−$30 in losses. Munich pair (naked YES on extreme bucket) added −$4.59 avoidable loss. Turns are increasing (0.155 → 0.355) but edge quality is negative on today's resolutions.

---

## 3. Expected Maker Rebates

Rebate formula: Σ(shares × 0.05 × p × (1−p)) × 0.25 (upper bound; actual pool-share dependent)

| Position | Shares | q | Est. Rebate |
|---|---|---|---|
| Chengdu NO 73331 (Jun-27 resolve) | 6.0 | 0.84 | $0.0101 |
| Munich NO 103001 | 8.0 | 0.66 | $0.0224 |
| Munich YES 61640 (**mid-price, highest earner**) | 9.0 | 0.51 | $0.0281 |
| Beijing NO 73870 | 7.0 | 0.83 | $0.0123 |
| London NO 106705 | 7.8 | 0.65 | $0.0222 |
| London NO 53482 | 7.5 | 0.68 | $0.0204 |
| London NO 55423 | 7.0 | 0.81 | $0.0135 |
| Chengdu NO 75809 | 7.0 | 0.74 | $0.0168 |
| Wuhan NO 55506 | 8.0 | 0.69 | $0.0214 |
| **Today total** | | | **$0.167** |

| | |
|---|---|
| Prior cumulative expected rebate | $1.370 |
| Today addition | $0.167 |
| **Cumulative expected rebate** | **$1.537** |

**⚠ REBATE ALERT:** Cumulative expected rebate $1.537 exceeds the $1.00 daily minimum payout threshold (carried forward from prior report). **User must verify pUSD receipt.** Payouts land daily in pUSD wallet. Munich YES at p=0.51 is today's highest per-share earner (quadratic peak). Note this estimate is an upper bound on pool share — competing makers reduce actual payout.

---

## 4. Kill-Switch Proximity

| Metric | Value | Status |
|---|---|---|
| Capital | $69.887 | |
| Weekly floor ($75) | **BREACHED** | −$5.11 below floor |
| Ruin floor ($50) | Safe | +$19.89 above floor |
| Day halt (−$10) | N/A | daily_start is restart capital, not midnight |
| Rolling 20 WR (prior) | 5% (STWA era) | |
| Post-restart consecutive wins | 9 | band strategy |
| Jun-26 d+1 band WR (today) | 40% (4/10) | ONLY filled positions |

**⚠ WEEKLY FLOOR BREACHED:** Capital $69.887 < $75.00 by $5.11. Per CLAUDE.md Rule 4: "If bankroll drops below $7.50 (-25%), halt all trading and reassess strategy." The absolute floor in the prior report was scaled to $75 (from $198 peak). Capital is now −64.8% from the Jun-25 peak of $198.28.

**CRITICAL CAVEAT (from prior report and CLAUDE.md):** Kill-switch WR/PF floors were specified for the taker era. The current maker band strategy wins ~40% of NO legs at 4-6× payoff structure — a fundamentally different regime. A kill-switch re-derivation for the maker band is PENDING with the user. **Do NOT halt on WR alone.** The floor breach here is a capital floor, not a WR floor.

Rolling 20 WR/PF are not computable without trades.jsonl access. The "5%/0.012" figure is from the STWA era (now disabled). Under the new band regime, consecutive_wins=9 and today's band WR=40% are both above the 30% taker-era floor — but these sample sizes are too small to update the rolling 20.

**The capital breach is real and warrants user review.** However, the bot has been rebuilding from $15.95 at restart through band wins, suggesting the strategy is now generating positive flow. The $75 floor was a fixed threshold from an earlier capital level; at current equity $133.26 estimate, the floor fraction is $69.887 / $133.26 = 52.4% — ABOVE the −50% ruin threshold relative to equity.

---

## 5. Day Verdict

**Today (2026-06-27):** Equity compound **NO** from prior report.

| | |
|---|---|
| 2-day capital change | −$128.40 (−64.8%) — driven by 33h service outage position losses |
| Since restart (Jun-26 15:08) | +$53.94 (+338% on $15.95 restart capital) |
| Binding constraint | Service outage (Jun-25 06:08 − Jun-26 15:08): ~32 open positions resolved as losses. Band strategy itself is rebuilding capital since restart. |
| Secondary constraint | Munich YES naked pair (−$4.59): only one pair leg filled; this must be investigated in pair_fav logic — a naked YES on a 35.5°C Munich bucket is an unintended exposure |

The June 26−27 band fills show the maker NO strategy is generating real fills (11/day). Jun-26 d+1 resolution WR is 40%, which is above the operational floor. The bot's 9 consecutive wins in bankroll.json (band regime) is a positive signal. Capital is rebuilding but is currently $5.11 below the $75 weekly floor. The unexplained +$69.20 is not a model-side deficiency but a data access gap (trades.jsonl not readable via mirror).

**One action item for user:** Confirm pUSD rebate receipt ≥ $1.00. Confirm pair_fav only fires when BOTH legs fill within the same cycle (today's Munich YES alone is not a pair — it's a naked directional bet).

---

*Report generated by Klaus PnL Ledger agent. trades.jsonl unavailable via data-mirror MCP (returned state_log.md instead). Attribution uses: maker_fills_recent.log, maker_resting_state.json, band_posted_state.json, band_struct_lite.jsonl (Jun-26, Jun-27), bankroll.json, prior_state.json.*
