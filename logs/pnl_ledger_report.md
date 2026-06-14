# Klaus PnL Ledger — 2026-06-14

*Generated: 2026-06-14T23:37Z | Snapshot age: 8 min | System: active*

---

## 1. P&L EXPLAIN — UTC Day 2026-06-14

### Capital Movements
| Item | Value |
|---|---|
| Prior-day capital (Jun 13 23:37 ledger) | **$246.4027** |
| End-of-day capital (Jun 14 23:04 snapshot) | **$267.0358** |
| Observed Δcapital | **+$20.6331** |

### Attribution Table
| Source | Events | $ PnL | Note |
|---|---|---|---|
| RECYCLE099 (exit099_live, overnight 01–08h) | 3 | +$17.0960 | Convergence sells pre-first-resolution |
| RECYCLE099 (exit099_live, daytime 09–19h) | 11 | +$80.1666 | 133 total shares, avg entry 0.337 → 0.99 |
| Band/STWA YES wins (STWA_RESOLVED) | 4 | +$11.0854 | 4 YES legs resolved correct |
| Band/STWA NO win (STWA_RESOLVED) | 1 | +$2.0000 | NO leg resolved correct |
| BAND_MERGE gain | 1 | +$0.3200 | Pair-merge profitable |
| STWA resolution losses (YES wrong) | 34 | −$69.7630 | YES legs resolved NO |
| STWA resolution losses (NO wrong) | 6 | −$17.0374 | NO legs resolved YES |
| **Total attributed** | **41 trades + 14 exit099** | **+$10.7822** | |
| **UNEXPLAINED** | | **+$9.8509** | **See below** |

### Unexplained P&L: +$9.85 — MODEL DEFICIENCY

The unexplained gap exceeds the $5 flag threshold. Root cause investigation:

**Evidence**: 96 UNTRACKED WS fill events logged today (total "size" token 6,527, but MINED+CONFIRMED are duplicates → ~48 unique fills). At least one confirmed partial-untrack: token `5553569321...` — exit099_live logged 7.0 shares at 0.64→0.99 (+$2.47), but the WS feed shows an actual fill of **22.39 shares at 0.99** for the same token at 01:06 UTC. Untracked portion: ~15.4 sh × (0.99 − 0.64) ≈ **+$5.39** unbooked.

**Cause**: exit099_live shadow logger records the RECYCLE099 code path's own count, but the actual Polymarket order book may fill larger quantities (e.g., previously posted maker resting orders executing at convergence outside the RECYCLE099 tracking context). Additional similar gaps on other tokens likely account for the remaining ~$4.46.

**Classification: MODEL DEFICIENCY** — exit099_live and the untracked-WS fill count are the two sides of the same bookkeeping gap. bankroll.capital receives the cash; trades.jsonl and exit099 do not log the full fill volume. This has been flagged in prior sessions; root-cause fix required in the shadow logger.

### Resolution Breakdown Detail
| Direction | n | PnL | Stake | WR |
|---|---|---|---|---|
| BUY_YES (STWA_RESOLVED) | 34 | −$69.76 | $82.23 | 11.8% |
| BUY_NO (STWA_RESOLVED + BAND_MERGE) | 7 | −$16.40 | $26.30 | 28.6% |
| **TOTAL resolutions (trades.jsonl)** | **41** | **−$86.48** | **$108.54** | **12.2%** |

Loss profile: all STWA losers have net_pnl = −stake (exit_price=0.0, market resolved opposite). Winners have exit_price=1.0 and gross payoff of 4×–7× (entry 0.12–0.25). Band YES base stakes: predominantly $2.10 (14 shares × 0.15 entry).

---

## 2. COMPOUNDING SCOREBOARD

### Equity Estimate
| Component | Value | Caveat |
|---|---|---|
| Free cash (bankroll.capital) | $267.04 | Confirmed, from bankroll.json saved_ts Jun 14 23:04 |
| Resting (future, d+1..d+2) at cost | +$12.92 | 7 positions: Guangzhou/Chengdu/Jeddah/London/Helsinki Jun 15–16 |
| **Equity estimate (conservative)** | **$279.96** | Excludes stale |
| Stale resting at cost (past end_date) | +$25.73 | 12 positions Jun 12–14 past resolution; **likely worthless** |
| Equity estimate (upper, incl stale) | $305.69 | **Do NOT use; stale positions almost certainly $0 at resolution** |

**CAVEAT**: Equity estimate is free_cash + matched_future_resting_at_cost only. Open positions from maker fills not yet resolved (d+1 onwards) are held at cost, not at fair value. Stale positions (Jun 12–14) are flagged as likely worthless and excluded from the primary estimate; if correct, this means ~$25.73 of unrealized loss has not yet appeared in trades.jsonl.

### Day Compounding Metrics
| Metric | Today | Jun 13 baseline | badatmath bench |
|---|---|---|---|
| Capital | $267.04 | $246.40 | — |
| Capital Δ% | **+8.37%** | +18.0% | — |
| Equity (conservative) | $279.96 | $274.42 | — |
| Equity Δ% | **+2.0%** | — | — |
| Maker fills ($) | $111.29 | $144.94 | — |
| Fills shares | 319.6 | 360.8 | — |
| Turns/day (fills/equity) | **0.40** | 0.528 | ~1.0x |
| ROI/turn (net_attr/fills$) | **9.7%** | ~20.7% | 10–20% |
| Exit099 events | 14 | 9 | — |
| Exit099 PnL | +$97.26 | +$79.15 | — |

**Trend vs baseline**: Exit099 volume grew (9 → 14 events, +$18.11 more PnL) — positive signal. Maker fills slightly lower ($144.94 → $111.29 deployed). Turns/day declined (0.53 → 0.40); still well below the badatmath benchmark of ~1.0x equity/day. The primary gap to badatmath is fill velocity, not ROI/turn.

---

## 3. EXPECTED MAKER REBATES

Calculation basis: weather taker feeRate=0.05; rebate_share=0.25 (25% of pool estimated).  
Formula used: `expected_rebate ≈ Σ(shares × 0.05 × q_price × (1 − q_price)) × 0.25`

| Item | Value |
|---|---|
| Today's maker fills | 319.60 shares |
| Expected rebate today (est) | **$0.7781** |
| Prior cumulative (thru Jun 13) | $2.3523 |
| **Cumulative expected rebate** | **$3.1304** |
| Min $1 accrual threshold | **EXCEEDED** |

⚠️ **ACTION FOR USER**: Cumulative expected rebate exceeds $1.00. Verify pUSD receipt from Polymarket rebate pool. No payout has been recorded in this ledger. Payouts land daily in pUSD; if not received, check Polymarket account balance or contact market maker desk.

**Highest-earning mid-price fills today** (p near 0.5, max p*(1-p)):
- Sao Paulo NO @ 0.56 (+8.1 sh) — q*(1-q)=0.246, top rebate contributor
- Jeddah NO @ 0.56 (+4.5 sh, prior) — similar profile
- Karachi YES @ 0.38 (+2.2 sh) — moderate contributor

---

## 4. KILL-SWITCH PROXIMITY

### Metrics
| Metric | Value | Floor | Status |
|---|---|---|---|
| Rolling 20 WR (BAND/STWA resolved) | **15.0%** (3W/17L) | 30% | ⚠️ FLAG |
| Rolling 20 PF (BAND/STWA resolved) | **0.136** (6.77/49.76) | 0.80 | ⚠️ FLAG |
| Day PnL (capital) | +$20.63 | −$10 halt | ✅ OK |
| Capital vs weekly floor (−25%) | $267.04 vs ~$200.28 | $200.28 | ✅ OK (+$66.76 buffer) |
| Capital vs ruin floor (−50%) | $267.04 vs ~$133.52 | $133.52 | ✅ OK (+$133.52 buffer) |

### MANDATORY CAVEAT — DO NOT HALT ON WR/PF ALONE
The 30% WR and 0.80 PF floors were calibrated for the **taker era** (independent entry/exit per trade). In the current maker-band book:
- Band buys YES at 0.06–0.35 entry price; loss when it resolves NO is −stake; WIN when resolves YES is 3×–16× payoff
- Structural YES resolution WR is expected ~15–22% (most legs don't hit the exact bucket)
- **Profitability comes from RECYCLE099 convergence** (+$97.26 today) NOT from resolution WR
- A PF of 0.136 on resolutions alone is expected and does NOT indicate strategy failure if RECYCLE099 is operating

**Status**: Kill-switch re-derivation for maker-era (based on RECYCLE099 hit rate, convergence margin, stale loss rate) is **pending with user**. No halt recommended solely on WR/PF basis.

**Real risk to monitor**: If RECYCLE099 volume drops significantly while resolution losses continue, the model stops working. Today RECYCLE099 > resolution losses by $10.78, so model is net positive. Watch for days where RECYCLE099 PnL < resolution losses — that would be the real halt signal.

---

## 5. DAY VERDICT

**Did equity compound today?** YES — capital **+8.37%** ($267.04 vs $246.40). Conservative equity **+2.0%** ($279.96 vs $274.42).

**Binding constraint**: Not cash (adequate) and not fills (active at 319 shares/82 events). Constraint is **resolution mix and stale position risk** — $25.73 of positions past end_date still sitting in resting state unbooked; if all expired wrong, equity absorbs that loss when eventually settled. RECYCLE099 engine healthy (14 exits, +$97.26) and growing vs yesterday.

**Secondary concern**: Unexplained PnL gap (+$9.85, MODEL DEFICIENCY) has now appeared in consecutive sessions. Prior session flagged untracked WS fills (54 events); today 96 events. The shadow logger consistently under-counts actual Polymarket fills. This is not a risk per se (it's excess PnL landing), but means the accounting model is structurally incomplete.
