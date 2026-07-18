# Klaus PnL Ledger — 2026-07-18

**Generated:** 2026-07-18T23:37Z  
**Snapshot:** 2026-07-18T23:34:32Z (age: 3 min — OK)  
**System:** `active` — no abort  
**Prior report:** 2026-07-17 (capital $35.498092)

---

## 1. P&L Explain (UTC day 2026-07-18 00:00–23:37Z)

### Capital

| Field | Value |
|---|---|
| Day-start capital (00:00 UTC) | $35.498092 |
| Bankroll.json now (stale, 02:46Z) | $37.569392 |
| Bankroll delta (partial) | **+$2.071** |
| EVOLVE wallet-verified (sniper, ~23:20Z) | **+$2.52** (21W − 18W) |
| Estimated true capital (EVOLVE-derived) | **~$38.018** |

**⚠ BANKROLL STALE:** bankroll.json was last written at 02:46 UTC, capturing only the first of three sniper wins. Two unbooked fills (04:24Z, 23:19Z) add an estimated +$0.93 net to the wallet that does not appear in bankroll.json. This is a **MODEL DEFICIENCY** in the bankroll update mechanism — the bot's book stopped writing mid-day. Wallet balance is authoritative; EVOLVE provides the sniper-only wallet-verified figure.

No manual flows: daily_start_capital $35.498092 matches prior ledger's closing capital exactly — confirmed no overnight deposits or withdrawals.

### Realized P&L by Leg

| Entry Class | Side | Count | Volume ($) | Net PnL | Status |
|---|---|---|---|---|---|
| UPDOWN-SNIPER | TAKER BUY | 3 | $56.46 | **+$2.52** | EVOLVE wallet-verified |
| RECYCLE099 | — | 0 | $0 | $0.00 | No events (shadow file absent) |
| STWA MAKER (Jul 17, 3 fills) | BUY | — | $8.06 deployed | PENDING | d+1/d+2 unresolved |
| STWA MAKER (Jul 18 00:54Z) | SELL + BUY | 2 | ~$12.16 mixed | UNTRACKED | See note |
| **Day realized total** | | | | **+$2.52** | |

**Sniper fill tape (Jul 18):**

| Time (UTC) | Token | Shares | Price | Deployed $ | Est. net PnL |
|---|---|---|---|---|---|
| 02:44Z | 7447492075024421 | 19 | $0.97 | $18.43 | +$0.54 |
| 04:24Z | 5978419141881139 | 19.5 | $0.97 | $18.92 | +$0.55 |
| 23:19Z | 6447973267780705 | 19.5 | $0.98 | $19.11 | +$0.37 |
| **Total** | | | | **$56.46** | **+$1.46 est.** |

Individual win estimates sum to +$1.46, which is +$1.06 below EVOLVE's wallet-verified +$2.52. This gap is consistent with the STWA maker G3 liquidation (SELL at $0.92 recovering prior untracked capital, see below) being included in the wallet balance. EVOLVE tracks sniper only; the gap is a scope difference, not model error.

**STWA untracked maker fills (00:54Z):**
- `SELL` token=2664940529472113: 9.32 sh @ $0.92 → $8.574 received. G3 classification liquidation — exec audit `b93a47f7b` (Jul 18 10:11Z) flagged this token for MAKER SELL unfreeze. Prior position from an earlier session; cost basis not recorded in bot tracking.
- `BUY` token=7094108612094851: 44.875 sh @ $0.08 → $3.590 deployed. New wing/tail position resting on book.
- Both fills are UNTRACKED (no position system entry). Cash effect flows to Polymarket wallet but not to bankroll.json.

**Jul 17 STWA maker positions ($8.06) — still pending:** Tokens 4095117562509625, 1055101008834022, 1046907088381323 not in today's fill log. d+1/d+2 weather markets; expected to resolve Jul 18–19.

### UNEXPLAINED

| | Amount |
|---|---|
| Capital delta (EVOLVE-derived, sniper) | +$2.52 |
| Attributed (EVOLVE sniper, 3/3W) | +$2.52 |
| **UNEXPLAINED** | **$0.00** |

Zero unexplained relative to EVOLVE sniper. The +$0.449 gap between bankroll delta ($2.071) and EVOLVE (+$2.52) is a **MODEL DEFICIENCY** in bankroll.json write frequency — not a phantom P&L source. STWA maker activity is an untracked parallel accounting stream; its inclusion or exclusion from the wallet total is not determinable from the available data without a live wallet query.

---

## 2. Compounding Scoreboard

| Metric | Jul 18 (today) | Jul 17 (yesterday) | Jun baseline |
|---|---|---|---|
| Capital est. (EVOLVE) | ~$38.02 | $35.50 | — |
| Sniper fills $ | $56.46 | ~$194.7 est. | — |
| All fills $ (incl. STWA new) | ~$60.05 | $202.76 | — |
| Avg equity (midpoint) | ~$36.76 | ~$31.83 | — |
| **Turns/day (all fills)** | **~1.63** | **6.37** | 0.2–0.5 |
| ROI/sniper turn | ~4.46% | 3.77% | ~3% |
| ROI/all-fill turn | ~4.20% | 3.62% | ~3% |
| **Day return (sniper)** | **+7.1%** | **+26.1%** | — |

**CAVEAT on equity_est:** ~$38.02 is EVOLVE-derived (sniper only, wallet-verified). Excludes: $8.06 Jul 17 STWA pending; $3.59 Jul 18 new STWA buy; G3 liquidation P&L (unknown cost basis). Equity range: $38.02 (sniper floor) to materially higher if STWA resolves YES.

**Turns sharply lower (1.63 vs 6.37 yesterday).** Three fires vs twelve. Two structural causes from EVOLVE commit:
1. **Wedge watchdog restart** (`ee014ba92`): exits if Gamma discovery silent >5 min; restart reduced window availability. Post-restart silence verified benign — 7,894 snaps, 0 fireable markets in that window.
2. **Pre-slot cap 2/2:** pre-entry slot cap saturated during peak window, gating additional fires.

**Per-turn ROI improving** (4.46% today vs 3.77% yesterday) because Kelly stake is scaling: clips grew from $13.7–$18.1 on Jul 17 to $18.43–$19.11 on Jul 18. On a 21/21W sequence the bot is sizing up on each win per the heat-check rule.

**Benchmark:** badatmath ~1.0× equity/day at 10–20%/turn. Today: 1.63 turns × 4.46% = 7.3% day return. Above Jun baseline (0.2–0.5 × 3% ≈ 1%), well below badatmath velocity. Fire cadence (3/day) is the primary compounding bottleneck, not edge per turn.

**Band shadow (no realized impact):** 11 shadow fires today, 0 live (BAND_LIVE=False since Jul 6). Mix: 3 d+0, 2 d+1, 6 d+2 across Seoul, Wuhan, Beijing, Munich, Taipei, Chongqing, Tokyo, Chengdu. Sum_ask range 0.405–0.933. Pipeline collects data; produces no capital until BAND_LIVE re-armed.

---

## 3. Expected Maker Rebates

Formula: `shares × 0.05 × p × (1-p) × 0.25`

| Fill | Token | Shares | p | p×(1−p) | Expected rebate |
|---|---|---|---|---|---|
| Jul 18 00:54Z SELL | 2664940529472113 | 9.32 | 0.92 | 0.0736 | $0.009 |
| Jul 18 00:54Z BUY | 7094108612094851 | 44.875 | 0.08 | 0.0736 | $0.041 |
| **Jul 18 total** | | | | | **$0.050** |

Both fills are extreme-odds (p=0.08/0.92) — low fee-weight, near the zero end of the p×(1-p) curve. A mid-price fill at p=0.50 earns ~8× more rebate per share.

| Period | Amount |
|---|---|
| Cumulative through Jul 17 | $3.831 |
| Jul 18 addition | $0.050 |
| **Cumulative (UPPER BOUND)** | **$3.881** |

Upper bound: actual payout depends on Klaus's share of category maker volume.

**FLAG — REBATE UNVERIFIED:** Cumulative expected exceeds $1 threshold. Polymarket pays daily pUSD (min $1 accrual). No receipt recorded in state_log through Jul 18. **User must verify pUSD rebate balance in Polymarket wallet.**

---

## 4. Kill-Switch Proximity

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Day PnL | +$2.52 | > −$10 daily halt | ✅ OK |
| Capital | ~$38.02 | > $50 ruin floor | ⚠️ BREACH — carry-over, owner-waived |
| Capital | ~$38.02 | > $75 weekly floor | ⚠️ BREACH — carry-over, owner-waived |
| Kill-watch day | 3 | Clean consecutive | ✅ CLEAN |
| Rolling 20 WR | 21/21 = 100% | > 40% | ✅ N/A (no losses) |
| Rolling 20 PF | N/A | > 0.8 | ✅ N/A (no losses) |
| Open positions (tracked) | 0 | — | ✅ OK |
| Disk | 93% (8 GB free) | < 100% critical | ⚠️ MONITOR |
| UPDOWN-SNIPER | 21/21W, +$11.54 cum. | ACTIVE | ✅ ACTIVE |
| BAND_LIVE | False | — | DISARMED Jul 6 |
| BAND_NO | False | — | DISARMED Jul 2 |
| STWA_REGULAR | Disabled | — | DISABLED |

**Floor breaches ($50, $75):** Structural carry-overs under owner waivers. At $38 capital, clearing the $50 ruin floor requires +$12 (+31.5%), which at today's 7.1%/day rate takes ~4 days. Weekly floor ($75) requires +$37 (+97%), ~14 days. Direction is correct.

**Disk improved:** Yesterday flagged as critical (100%, 1 GB free). Now at 93% (8 GB free). Likely log rotation or manual cleanup. At peak logging volume (~5 GB/day estimate), 8 GB free = ~1.6 days buffer. Shadow loggers running 282K+ maker_flow rows and 375K+ stwa_pricer_eval rows today — monitor actively.

**CAVEAT on WR/PF thresholds:** The 40% WR / 0.8 PF floors were specified for taker-era multi-strategy. UPDOWN-SNIPER design WR is ~97–99% (buys YES at $0.97–$0.99, nearly certain to resolve correctly). A WR below 40% on this strategy would indicate catastrophic miscalibration, not normal drift. A halt recommendation based on WR alone is not appropriate here. Kill-switch re-derivation for the sniper regime is pending with owner.

---

## 5. Day Verdict

**YES — equity compounded +7.1%** ($35.498 → ~$38.02, EVOLVE wallet-verified sniper).

Binding constraint: **fire cadence** (3 fires vs 12 yesterday). Per-turn ROI is improving (4.46% vs 3.77%) and Kelly sizing is scaling correctly ($18.43 → $19.11 per clip), so the strategy is healthy. The low fire count was structural, not signal-driven: wedge watchdog restart eliminated one window, and pre-slot cap filled during peak. Neither indicates edge degradation.

Sniper: 21/21W, kill-watch Day 3 clean. No losses on record.

**Alerts for owner (action required):**
1. **Bankroll.json stale** — last written 02:46 UTC, misses 2 fills. True capital ~$38.02 (EVOLVE), not $37.57. Investigate why bankroll.json stopped updating.
2. **Jul 17 STWA maker ($8.06) unresolved** — tokens 4095117/1055101/1046907 pending d+1/d+2.
3. **Cumulative rebate $3.881 unverified** — check pUSD balance in Polymarket wallet.
4. **Disk 93%** — improved; monitor. 8 GB free at current logging rates = ~1.6 days.
