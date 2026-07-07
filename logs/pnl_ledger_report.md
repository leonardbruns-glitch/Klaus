# Klaus PnL Ledger — 2026-07-07
*Generated 2026-07-07T23:37Z | Snapshot 2026-07-07T23:29:34Z (age: 8 min — OK) | System: active*

> **Prior run was STALL ABORT** (data-mirror dead 20.7h, stale capital $42.02). This run has fresh data. Full pipeline executed.

---

## § 1 — P&L Explain (UTC Day 2026-07-07)

### Capital Reference Points

| Checkpoint | Time (UTC) | Tracked Capital | Cash | Note |
|---|---|---|---|---|
| Prior ledger (stale) | 02:57Z | $108.35 | $42.02 | Fixed comparator reveals: 2 open ladder shots at cost ($66.33) were invisible to tracker; cash-only read was misleading |
| Bot restart + comparator fix | 11:36–11:40Z | $108.35 | $42.02 | Explicit reconciliation: 108.35 − 21.37 − 44.96 = 42.02 ✓ |
| Evening EVOLVE | 22:10Z | $136.77 | $136.77 | Both shots resolved; 0 open positions, 0 resting orders |
| Snapshot (this run) | 23:29Z | **$136.77** | **$136.77** | Authoritative |

**Day P&L (tracked capital basis): $136.77 − $108.35 = +$28.41 (+26.2%)**

### Attribution by Leg

| Leg | Entry | Exit | Shares | Cost | Proceeds | Net PnL | Source |
|---|---|---|---|---|---|---|---|
| Sprint Ladder – Tokyo 26°C (d+0) | 00:00Z BUY @ $0.37 | Resolved NO (lost) | 56 | $21.37 | $0.00 | **−$21.37** | state_log 22:10Z; fill tape 00:00Z |
| Sprint Ladder – Singapore 32°C (d+0) | 02:00Z BUY @ $0.46 | Resolved YES (won) | 94.75 | $44.96 | $94.75 | **+$49.79** | state_log 22:10Z; fill tape 02:00Z; user_ws.jsonl payout 16:47Z |
| Engine / Band (BAND_LIVE=False) | — | — | — | $0 | $0 | **$0.00** | exec audit §2: 0 posts Jul 7 |
| RECYCLE099 / exit099 today | — | — | — | — | — | **$0.00** | exit099_live.jsonl absent (confirmed) |
| **Total attributed** | | | | | | **+$28.42** | |
| **Day P&L (tracked capital)** | | | | | | **+$28.41** | bankroll.json delta |
| **UNEXPLAINED** | | | | | | **−$0.01** | Rounding only |

**UNEXPLAINED = −$0.01.** Full attribution achieved. Not MODEL DEFICIENCY — this is pure rounding in the sleeve/bankroll arithmetic.

### Morning Capital Gap Explained

The prior STALL ABORT flagged $42.02 → $108.35 (+$66.33) as unexplained. The state_log 11:40Z resolves it definitively: the tracked-capital **comparator was broken** — it read cash only ($42.02) rather than cash + open ladder shots at cost. The comparator fix at restart exposed:
`$108.35 = $42.02 cash + $21.37 Tokyo shot + $44.96 Singapore shot`
No manual deposit. No unbooked resolution. Hardware/code bug only.

**This was NOT a capital event. The bot's daily-loss halt was falsely tripped all morning because of it** — the halt saw a “−61% loss” that was actually 61% of equity converted to live positions.

---

## § 2 — Compounding Scoreboard

### Equity Estimate

| Component | Value | Caveat |
|---|---|---|
| Cash (bankroll.json) | $136.77 | Authoritative; CLOB-verified by EVOLVE |
| Open engine positions | $0.00 | maker_resting_state = {} |
| Open ladder shots | $0.00 | Both resolved; 0 open |
| **equity_est** | **$136.77** | Cash only; complete at time of snapshot |

Caveats: (1) Sprint ladder sleeve balance ($145.36) is a separate accounting pool — it is NOT additive to bankroll capital (costs already expensed, wins already repatriated); (2) open-position CLOB value not independently verified (no CLOB API access this run, but open_positions = 0 so moot).

### Turn Rate & ROI

| Metric | Today | Benchmark (badatmath) |
|---|---|---|
| Band fills $ | $0.00 | — |
| Band turns/day | **0.00** | ~1.0 |
| Sprint ladder deployed today | $66.33 (2 shots) | — |
| Sprint ladder ROI/shot (net) | +$28.42 on $66.33 = **+42.8%** | — |
| Engine ROI/turn | N/A (0 turns) | 10-20%/turn |

**Band is fully halted.** 0 turns/day for the engine. Compounding today is entirely sprint-ladder-driven: a single net positive binary (1W, 1L → +$28.42 net on $66.33 deployed).

### 7-Day Trend (band engine only)

| Period | Fills $/day | Turns/day | Net P&L |
|---|---|---|---|
| Jul 4 | $10.8 | ~0.07 | (not yet attributed in this ledger series) |
| Jul 5 | $24.0 | ~0.18 | (prior ledger) |
| Jul 6 | $31.8 (halted 22:08) | ~0.22 | (prior ledger) |
| Jul 7 | $0.00 | 0.00 | **WIND-DOWN — band off** |

7d band engine P&L: −$118.43 on n=42 resolved (per state_log 22:10Z). PF 0.088. All from paths already cut before Jul 7; post-wind-down band flow −$4.22 (legacy dust).

---

## § 3 — Expected Maker Rebates

### Today
Band posts: 0 (BAND_LIVE=False). Maker fills today: 0. Expected rebate today: **$0.00**.

### 7-Day Band Fill Tape (Jul 4–6, 23 registered fills)

| Fill group | n | Approx shares | p̄ | Expected rebate = Σ(sh·0.05·p·(1−p)·0.25) |
|---|---|---|---|---|
| YES fills [0.30–0.50] | 13 | ~80 shares | 0.44 | ~$0.22 |
| NO fills [0.30–0.50] | 5 | ~30 shares | 0.41 | ~$0.06 |
| YES/NO fills [0.50–0.85] excl. Moscow | 4 | ~23 shares | 0.54 | ~$0.07 |
| Moscow NO increments @ 0.06 | 83.5 sh | 83.5 | 0.06 | ~$0.06 |
| **7d new rebate estimate** | | | | **~$0.41** |

*Upper bound — actual pool share depends on competing makers. Moscow NO at p=0.06 contributes minimally despite large share count (quadratic penalty near extremes). Highest-earning fills were the mid-price YES at p≈0.44–0.46 (Munich, Tokyo, Seoul, Shanghai).*

### Cumulative

| Period | Expected rebate | Note |
|---|---|---|
| Through Jul 5 ledger | $2.757 | Carried from prior state |
| Jul 6–7 new | ~$0.41 | From Jul 4–6 fill tape; 0 new today |
| **Cumulative** | **~$3.17** | Upper bound |

**FLAG (carried forward):** Cumulative expected rebate **$3.17 > $1 minimum**. Polymarket pays maker rebates daily in pUSD, min $1 accrual. No receipt has been recorded in available data across any ledger run. **User should verify pUSD receipt in Polymarket account.** If no receipt has arrived despite >$3 cumulative, post to Polymarket Discord #market-makers with wallet address.

---

## § 4 — Kill-Switch Proximity

*CAVEAT: WR/PF floors were specified for the taker era. Maker band book wins ~22% of YES legs by design at 4–5× payoff (pairs = composite ~60% WR on full-pair). Reporting proximity only — do NOT trigger WR/PF halts on taker-era thresholds.*

| Gate | Threshold | Current | Status |
|---|---|---|---|
| Day PnL halt | < −$10/day | +$28.41 | CLEAR |
| Weekly floor | capital < $75 | $136.77 | CLEAR (+$61.77 buffer) |
| Ruin floor (ratcheted) | $89.16 (0.40 × $222.90 HW) | $136.77 | CLEAR (+$47.61 buffer, 34.8% above) |
| Wind-down equity rail | < 50% × $222.90 = $111.45 | $136.77 = 61.4% of HW | **CLEARED** (re-enable withheld) |
| −14% daily freeze | active until 07-08 21:53Z | (expires tomorrow) | Active — no size/ceiling increases today |
| LDA rolling-20 net | STOP at < −$36.39 | −$19.71 | Approaching; −$16.68 buffer |
| Disp ratio | ≥1.10 to re-enable | 0.817 (stale ≥4 days) | STALE — gauge locked; Jul 3 partial 0.521°C |

### Kill-Switch Re-Derivation Status
Pending (noted in prior ledger as PENDING WITH USER). The LDA-era WR/PF floors are structurally mismatched to the current band maker book. LDA rolling-20 at −$19.71 is approaching the STOP threshold but most LDA trades are from the pre-wind-down cut paths. The −$36.39 STOP trigger would not be meaningful grounds for halting the band engine (which is already halted for separate charter reasons).

### Band Re-Enable Gate (most proximate constraint)
Re-enable of BAND_LIVE requires simultaneously: (1) equity ≥ 50% HW [$111.45] — **now cleared at $136.77**; (2) post-guard pair n≀40 positive trend — current n≈9/side (need ~31 more pair fills, shadow-only accrual); (3) −14% freeze expiry — **07-08 21:53Z** (tomorrow). The pair n gate is the binding constraint; at current shadow fill-rate it may take several more days of live operation to reach n=40.

---

## § 5 — Day Verdict

**YES — equity compounded today: +$28.41 (+26.2% on tracked start $108.35).**

- Binding constraint: BAND_LIVE=False (charter wind-down rail, equity $108.35 < $111.45 threshold at start of day)
- Engine contribution: $0.00 (band fully halted, 0 posts, 0 fills, 0 turns)
- All compounding from sprint ladder: Singapore WIN (+$49.79) minus Tokyo LOSS (−$21.37) = +$28.42 net
- Unexplained: −$0.01 (rounding). Full bottom-up attribution achieved

**Wind-down equity rail cleared intra-day** (21:53Z: equity $136.77 = 61.4% of HW). Re-enable remains withheld: pair n≈9/side (gate requires 40), disp_ratio stale at 0.817, −14% freeze active until tomorrow 21:53Z. Capital continues growing with band dormant.

**Operational note:** The tracked-capital comparator was broken until today's 11:40Z fix. The false daily-halt trip, the STALL ABORT this morning (stale $42.02 reading), and the misleading kill-switch breach flags from the prior run are all explained by the same root cause. The fix is now deployed and verified.

**Sprint ladder lifetime: 8/8 resolved, 4W/4L, +$85.36 net, sleeve $145.36.** Day 5 of sprint; estimated remaining gap ~−$23.75 (day 4 gap −$52.16 + today's +$28.41).

---
*Report generated by pnl-ledger-agent | snapshot age 8 min | trades.jsonl: not directly accessed (26MB); attribution derived from state_log 22:10Z + maker_fills_recent.log + exit099_live + band_struct_lite | full pipeline executed*
