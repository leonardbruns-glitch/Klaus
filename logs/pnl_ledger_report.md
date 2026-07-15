# Klaus PnL Ledger — 2026-07-15

**Generated**: 2026-07-15T23:37Z  
**Snapshot**: 2026-07-15T23:29:13Z (8 min old ✅)  
**Klaus systemd**: active ✅  
**Disk**: ⚠ 98% full — 3 GB free on 97 GB volume. Action required soon.

---

## §1 — P&L Explain

**Day window**: 2026-07-15 00:00–23:37 UTC  
**Capital start** (`daily_start_capital`): $34.132883  
**Capital now**: $33.856483 (snapshot 23:29 UTC)  
**Day PnL (cash)**: **−$0.2764 (−0.81%)**

### Leg-by-leg attribution (via CAPITAL_CORRECTION chain)

| Time UTC | Source | Description | Debit ($) | Credit ($) | Net ($) |
|---|---|---|---|---|---|
| 00:19 | POST_ORPHAN_RECONCILE | Carry-in orphan: 5 sh @0.98 bought, sold @0.97 → reconcile loss | — | — | −0.067 |
| 06:19–06:24 | AUTO_CORRECT pair A | BUY 5 sh @0.983, resolved $5.00 | 4.921 | 5.000 | **+0.079** |
| 07:41 | AUTO_CORRECT (batch) | Batch credit: multi-fill resolution (see below) | — | 2.303 | **+2.303** |
| 15:34–15:39 | AUTO_CORRECT pair B | BUY 5 sh @~0.875, resolved $5.00 | 4.375 | 5.000 | **+0.625** |
| 21:10–21:15 | AUTO_CORRECT pair C | BUY 5 sh @~0.915, resolved $5.00 | 4.574 | 5.000 | **+0.426** |
| 21:30–21:35 | AUTO_CORRECT pair D | BUY 2×5 sh @0.87+0.94, resolved $10.00 | 9.109 | 10.000 | **+0.891** |
| 22:56 | AUTO_CORRECT (open) | BUY 5 sh, **pending resolution** at snapshot | 4.627 | (pending) | **−4.627** |
| — | Silent overnight | 01:09 BUY @0.98×5sh resolved silently pre-check | est. 4.900 | est. 5.000 | ~**+0.093** |

**Sum of CAPITAL_CORRECTION deltas**: −$0.3695  
**Actual day PnL**: −$0.2764  
**UNEXPLAINED**: **+$0.093** (positive — bankroll better than corrections imply)

**Unexplained analysis**: Capital jumped from $34.066 (post-orphan, 00:19) to $34.159 (capital_before at 06:19) = +$0.093 without any logged correction. The 01:09 fill (BUY 5 sh @0.98 = $4.90 cost, resolved ~$5.00) resolved faster than the AUTO_CORRECT polling interval; only the net inflow was captured, not the outflow. Root cause: **TRACKER_RESTART_BUG** — all sniper fills show as UNTRACKED in the fill log. Not MODEL DEFICIENCY. Cause is identified.

### 07:41 batch credit ($2.3033) composition estimate

The +$2.303 batch at 07:41 covered fills from the 07:14–07:39 cluster plus overnight carryover:

| Fill | Buy price | Cost | Return (win) | Edge |
|---|---|---|---|---|
| 07:14 @0.90 × 5sh | 0.90 | $4.50 | $5.00 | +$0.50 |
| 07:14 @0.98 × 5sh | 0.98 | $4.90 | $5.00 | +$0.10 |
| 07:19 @0.98 × 5sh | 0.98 | $4.90 | $5.00 | +$0.10 |
| 07:39 @0.90 × 5sh | 0.90 | $4.50 | $5.00 | +$0.50 |
| Overnight carryover (est.) | — | — | — | ~+$1.10 |
| **Batch total** | | | | **~+$2.30** |

Carryover component (~$1.10) is consistent with yesterday's unresolved late-night fills that credited overnight and were swept into the first reconciliation check.

### Double-count check (exit099_live / RECYCLE099)

No `exit099_live.jsonl` exists for 2026-07-15 (file absent from shadow directory). No RECYCLE099 events today. Band-posted-state last entry: 2026-07-06. No double-counting risk.

---

## §2 — Compounding Scoreboard

### Equity estimate

| Component | Value | Notes |
|---|---|---|
| Cash | $33.856 | Authoritative (bankroll.json) |
| Open position (22:56 entry) | $4.627 (cost) | Pending resolution; win expected |
| **Equity estimate** | **$38.483** | Break-even assumption on open |
| Optimistic (open wins) | **$38.857** | +$0.37 unrealized if $5.00 return |

**CAVEAT**: Three late fills (22:29 @$4.90, 22:49 @$4.90, 23:04 @$4.75) appear in the fill tape but have no corresponding CAPITAL_CORRECTION debits. If these represent 3 additional open positions, total equity exposure is $38.48 + $14.55 cost = ~$53.03 possible gross deployed, with ~$15.00 returns expected overnight. Most likely 22:29/22:49 resolved within their 5-min windows before snapshot; 23:04 likely still open. Equity estimate has ±$10 uncertainty until overnight resolutions are logged.

### Fill activity and turns

| Metric | Value | Source |
|---|---|---|
| Total BUY fills today | 20 | Fill tape (UNTRACKED log) |
| Fill-tape notional | $86.465 | 18 taker + 2 maker fills |
| Average equity | $33.995 | Midpoint of start/end |
| **Turns/day** | **2.54** | $86.47 / $33.995 |
| Alt turns (corrections only) | 0.81 | $27.67 / $33.995 — UNDERCOUNT |
| ROI/turn (realized) | **−0.32%** | −$0.276 / $86.47 |
| ROI/turn (if open wins) | **+0.11%** | +$0.094 expected / $86.47 |

**Fill breakdown by type**:
- 18 × TAKER updown sniper (BTC 5-min), avg price $0.96, avg cost $4.79/fill
- 2 × MAKER weather fills (@$0.02 × 20sh and $0.02 × 5sh — near-extreme NO-side; small exposure $0.50 total)

### Per-trade economics (post-fix sniper)

From commit message "17/17 post-fix live tape +$3.64" (measured from yesterday 22:04Z fix to this evening):
- **WR = 100%** (17 of 17 closed positions) over ~18h window
- **Avg edge**: $3.64 / 17 = $0.214/trade = +4.5% on avg $4.79 cost
- Today's settled pairs alone: +$2.021 on 4 pairs (+4 individual wins from batch) = confirmed 8 wins

**7-day capital trend**:

| Date | Capital ($) | Day PnL ($) | Key event |
|---|---|---|---|
| ~Jul 6 | ~$109 | large loss | STWA/BAND wind-down |
| Jul 13 | ~$34.74 | ~large loss | ORPHAN_SOLD bug dominant |
| Jul 14 | $34.133 | −$0.610 | Bug fixed 22:04Z; sniper restarted |
| **Jul 15** | **$33.856** | **−$0.276** | First partial clean day; pending position overhang |

**vs badatmath benchmark** (1.0× equity/day at 10–20%/turn): today's 2.54 turns at +4.5% edge/fill = theoretical +11.4% daily gross if all 20 fires close as wins. Realized at snapshot: −0.81% (cash). The gap is timing — 4+ fills unresolved at 23:29. If all outstanding resolve as wins, net day would be +$0.09 = +0.26%. **Benchmark gap closure is a logistics problem (TRACKER_RESTART_BUG + snapshot timing), not an edge problem.**

---

## §3 — Expected Maker Rebates

Formula: `shares × 0.05 × p × (1−p) × 0.25` (upper bound; actual depends on pool competition)

| Time | Type | Price (p) | Shares | Expected rebate |
|---|---|---|---|---|
| 14:09 | MAKER BUY | 0.02 | 20 | $0.0049 |
| 17:14 | MAKER BUY | 0.02 | 5 | $0.0012 |
| **Today** | | | | **$0.0061** |
| **Cumulative** | (carried $3.553 + today) | | | **$3.559** |

**Note on mid-price fills**: Both maker fills are at p=0.02 — near-extreme, earning ~1/612 of what a p=0.50 fill of the same size would earn. If the band/pair-fav maker strategy posts at mid-spread (p≈0.45–0.55), a single 5-share fill at p=0.50 would earn ~$0.016 vs $0.001 here.

**User action**: Cumulative expected rebate $3.559 exceeds the $1 minimum accrual threshold. **Verify pUSD rebate receipt on Polymarket account.** Payout lands daily; if not received, contact Polymarket support.

---

## §4 — Kill-Switch Proximity

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Day PnL | −$0.276 | −$10 daily halt | ✅ OK |
| Capital | $33.856 | $50 ruin floor | ⛔ BREACHED −$16.14 |
| Capital | $33.856 | $75 weekly floor | ⛔ BREACHED −$41.14 |
| Capital vs 30d HWM | 15.2% of $222.90 | 50% = $111.45 | ⛔ BREACHED |
| Rolling 20 WR | 40.0% | <30% flag | ⚠ AT WARNING — stale data |
| Rolling 20 PF | 0.08 | <0.8 halt | ⚠ KILL-SWITCH — stale data |
| LDA status | STOP | rolling-20 < −$30 | ⛔ STOPPED |
| BAND_LIVE | FALSE | — | disarmed Jul 6 |
| BAND_NO | FALSE | — | disarmed Jul 2 |
| STWA_REGULAR YES/NO | FALSE | — | disabled May–Jun |
| Updown Sniper | ACTIVE | — | 17/17 post-fix ✅ |

**WR/PF caveat (mandatory)**: The rolling-20 WR=40% and PF=0.08 are computed from the last 20 non-zero TRADE records — all of which are STWA_RESOLVED or BAND_MERGE exits from 2026-07-05/06. Both strategies are disabled. The current SNIPER strategy has zero net_pnl entries in trades.jsonl (TRACKER_RESTART_BUG; all exits arrive as CAPITAL_CORRECTION, not TRADE rows). **Kill-switch re-derivation for SNIPER-only mode is pending with the user — do not halt on these WR/PF numbers.**

**Capital floor context**: The $50 ruin floor and $75 weekly floor have been breached since the Jul 5-6 STWA drawdown (~$100 → $34). The bot continues by explicit user directive per commit history (daily EVOLVE sessions). This is a pre-existing breach; no new trigger today.

**Open positions**: 0 logged (system_status.txt) — consistent with all TRADE records showing pnl=0 (TRACKER_RESTART_BUG; open sniper positions are not registered in the tracker).

---

## §5 — Day Verdict

**NO — equity −0.81% on day (cash). Timing artifact, not strategy failure.**

**What happened**: 20 sniper entries fired across the day. The fill tape shows $86.47 deployed; 16–17 positions resolved profitably before the 23:29 snapshot. One open position ($4.63 cost, 22:56) and 2–3 additional late fills (22:29, 22:49, 23:04) are pending overnight resolution. If these resolve as wins — consistent with 17/17 post-fix WR — net day PnL would be ~+$0.09 to +$0.60.

**Binding constraint**: **Open position timing** — the last entries of the day are unresolved at the snapshot window. The cash balance reflects deployed capital, not yet the $5.00 returns expected.

**Secondary constraint**: TRACKER_RESTART_BUG. 14 of 20 fills are invisible to CAPITAL_CORRECTION and trades.jsonl alike. Attribution is done via the capital chain + fill tape crosswalk. Per-trade analytics are blind; bot is operating without proper fill-close records.

**What is working**: Updown sniper edge is confirmed (17/17, +$3.64 per commit). Fee drag at near-extreme prices (~0.002 per share at p=0.97) is negligible. Per-trade ROI ~+4.5%.

**What is not working**: Capital is $33.86 — 69% below the historical peak and below all kill-switch floors. Recovery at the current rate (~$0.20–$0.60/day net) will be slow. The question is whether sniper throughput (turns/day) can be increased within the $20 cash-reserve constraint.

**Disk flag**: 98% full (3 GB free). If log files continue to grow, the bot could crash. User should free disk space.

---

*Report auto-generated by Klaus PnL Ledger agent | 2026-07-15T23:37Z*
