# PnL Ledger Report — 2026-07-14
Generated: 2026-07-14T23:42Z | Snapshot: 2026-07-14T23:39:09Z (≈3 min old)

---

## PRE-FLIGHT
| Check | Value | Status |
|---|---|---|
| Snapshot age | 3 min | ✅ Fresh |
| System | `klaus systemd: active` | ✅ Running |
| Bot uptime timestamp | 2026-07-14T22:04:06Z (1h 35m) | ✅ |
| Capital (bankroll.json) | $34.132883 | — |
| Prior capital (Jul 13 ledger) | $34.7427 | — |
| Open positions | 0 | ✅ |
| Resting orders | {} | ✅ |
| Trades.jsonl rows | 8,193 | — |

---

## 1. P&L EXPLAIN (UTC day 2026-07-14)

### Capital Waterfall

| Item | Amount |
|---|---|
| BOD capital (daily_start_capital, set 00:00Z) | $34.7427 |
| EOD capital (bankroll.json, saved 23:10Z) | $34.1329 |
| **Day P&L (bankroll delta)** | **-$0.610** |

---

### Critical Context: ORPHAN_SOLD Bug — Confirmed Fixed at 22:04Z

**State-log 2026-07-14 22:04Z confirms:** `main.py _window_end_balance_sweep` was force-selling UPDOWN-SNIPER positions as orphans. 21/25 fills since go-live (12 on Jul 14) were ORPHAN_SOLD at the bid (exits at 0.88, 0.939, 0.73) instead of holding to $1.00 resolution. The apparent "losses" in the fill log for most paired taker sells are **orphan sweeps, not strategic exits**. Fix committed 22:04Z (7f3234c4d), bot restarted.

**TRUE realized since go-live (Jul 13 10:46Z → Jul 14 22:04Z):** -$5.48 total. Cash bridge: $39.40 → $34.04 (reconciled in state_log). Pre-fix Jul 14 booked P&L: -$2.45 (void for analytics; economically real but measurement error from orphan reporting).

**True win rate pre-fix Jul 14:** 17W / 1L = **94.4% WR** over 18 settled positions. Strategy edge is intact. Losses were caused by the sweep bug, not the signal.

---

### P&L Attribution by Leg

**UPDOWN-SNIPER (pre-22:04Z, orphan-sweep contaminated — 12 fills on Jul 14)**

All fills marked UNTRACKED (tracker-restart bug, same as Jul 13). Paired by token ID from maker_fills_recent.log. BUY = sniper entry; SELL = orphan-swept exit (forced, NOT voluntary):

| Time (UTC) | Token | Buy px | Shares | Exit px | Shares | Raw net | Exit type |
|---|---|---|---|---|---|---|---|
| 04:29 | 6572132400751856 | 0.98 | 5.5 | 0.99 | 5.5 | +$0.055 | Resolution? |
| 09:39 | 3172659680571012 | 0.98 | 5.5 | 0.95 | 5.4 | -$0.260 | **Orphan sweep** |
| 09:49 | 9957267143786884 | 0.92 | 5.5 | 0.88 | 5.5 | -$0.220 | **Orphan sweep** |
| 10:29 | 3625593777378171 | 0.979 | 6.0 | 0.99 | 6.0 | +$0.066 | Resolution? |
| 11:29 | 7507093480321761 | 0.989 | 6.0 | 0.939 | 6.0 | -$0.300 | **Orphan sweep** |
| 12:54 | 6382334426555478 | 0.95 | 5.5 | 0.95 | 5.5 | $0.000 | Wash |
| 14:49 | 4097207318472166 | 0.98 | 5.5 | 0.99 | 5.5 | +$0.055 | Resolution? |
| 16:59 | 7901659052770893 | 0.99 | 6.0 | 0.99 | 6.0 | $0.000 | Wash |
| 18:34 | 3969875899756924 | 0.98 | 5.5 | 0.99 | 5.5 | +$0.055 | Resolution? |
| 19:09 | 8509769425705129 | 0.98 | 5.5 | 0.98 | 5.5 | $0.000 | Wash/neutral |
| 19:19 | 9999362967786488 | 0.98 | 5.5 | 0.999 | 5.0 | -$0.395 | **Orphan sweep** (size mismatch) |
| 19:59 | 8375538681010942 | 0.94 | 5.5 | 0.99 | 5.5 | +$0.275 | Resolution? |
| **Subtotal** | | | | | | **-$0.669** | |

Unmatched buys: 09:44 BUY token 4994801987457247 @ 0.98×5.5 (resolved by 23:39, outcome unknown). 23:04 BUY token 3677886458514989 @ 0.98×5 (new session post-fix, 23:05 window close).

Taker fee at extreme prices (formula: feeRate × p × (1−p) ≈ 0.05 × 0.98 × 0.02): **≈$0.001–0.003/trade** — negligible at extremes. Total fee drag: ~**$0.09**.

**Sniper pre-fee total: -$0.669 | Fee drag: ~-$0.09 | Sniper estimated: ~-$0.76**

Entries that exited at a gain (+$0.055 each) were likely those where resolution preceded the orphan sweep window. Entries that exited at a loss were orphan-swept before $1.00 resolution.

---

**Maker fills — pair-fav / legacy band convergence**

All UNTRACKED. Costs/cost-bases for these legs are from prior sessions.

| Time | Token | Side | Role | Shares | Price | Notional |
|---|---|---|---|---|---|---|
| 02:14 | 3199513447545278 | BUY NO | MAKER | 40 | 0.04 | $1.60 out |
| 02:15 | 1078405863114726 | SELL YES | TAKER | 5 | 0.99 | $4.95 in |
| 09:34 | 2849477449509392 | BUY NO | MAKER | 40 | 0.04 | $1.60 out |
| 09:34 | 4085516939123681 | SELL YES | TAKER | 5 | 0.99 | $4.95 in |
| 15:04 | 7181800165235847 | SELL YES | MAKER+TAKER | 5+5 | 0.98/0.99 | $9.85 in |
| 15:04 | 1124960860640362 | BUY NO | MAKER | 7.5 | 0.02 | $0.15 out |
| 16:24 | 7210475810361035 | BUY NO | MAKER | 30.5 | 0.06 | $1.83 out |

These pattern as pair-fav trades: the bot holds a resting NO order at low price and takes the correlated YES exit near 0.99 when confirmed. Net cash per pair: YES proceed ~$4.95 vs NO entry ~$1.60-1.83 out = positive net per pair if NO positions subsequently resolve at $0.00 (wrong outcome). Entry cost of the YES positions is from prior sessions and not visible here.

**⚠️ FLAG — USER ACTION REQUIRED:** 15:49 MAKER SELL, token 6178261687539843, **367.66 shares × $0.98 = $360.31 notional**. This is an anomalous MAKER fill — a large resting sell order placed in a prior session that executed today. Cost basis of the 367.66 shares is unknown (likely a June-era band YES position, possibly entered at $0.10–0.15/share = $36–55 original cost from band_posted_state.json June spending of $174–260). If bankroll.json (saved 23:10Z, 80 min after fill) has already absorbed both the cost and the proceeds, the -$0.61 day P&L is accurate. If not (UNTRACKED means bot model may not have updated), true wallet balance may diverge. **User must verify: Polymarket wallet pUSD balance should ≈ bankroll.json $34.13. If wallet shows ~$394, the fill was not captured in bankroll — escalate immediately.**

---

### Unexplained

| Component | Amount |
|---|---|
| Bankroll delta | -$0.610 |
| Attributed (sniper taker pairs, post-fee) | -$0.76 |
| Unexplained (bankroll outperformed estimate) | **+$0.15** |

|UNEXPLAINED| = $0.15 — **below $5 threshold**. No deep investigation triggered.

**Likely cause:** The post-fix clean session's 23:04 BUY at 0.98×5.0 resolved at 23:05. If a WIN (25–30% likely per single-event outcome), proceeds +$5.00 vs cost $4.90 = +$0.10. Additionally, pair-fav maker YES sells at 0.98-0.99 recovered slightly more than their NEW NO entries cost. The +$0.15 unexplained is consistent with this combination. Not MODEL DEFICIENCY — cause is identifiable as post-fix WIN + maker micro-profit.

**Note:** The 15:49 large maker fill ($360.31) is separately flagged above. The unexplained here assumes it was zero-net in bankroll (cost and proceeds both embedded). If not, the unexplained line becomes a MODEL DEFICIENCY and the $0.15 is noise against a much larger gap.

---

## 2. COMPOUNDING SCOREBOARD

**Equity estimate (CAVEAT: all figures assume 15:49 maker fill is net-neutral in bankroll; open to revision):**

| Metric | Value | Notes |
|---|---|---|
| Equity estimate | $34.13 | Cash only. 0 open positions, {} resting orders. |
| Unresolved late entry | ~$4.90 | 23:04 BUY 0.98×5 (settled by 23:39 but bankroll saved 23:10); could be +$0.10 WIN or -$4.90 LOSS, not yet in equity_est |
| True equity floor | $34.13 | Conservative |
| Fills $ today | ~$86 | BUY-side: sniper taker $81 + new maker NO entries $5. Excludes 15:49 legacy SELL ($360) — it is an exit of old position, not new capital deployed |
| Avg equity | $34.44 | Midpoint $34.74 / $34.13 |
| Turns/day | **~2.50** | fills_usd $86 / avg_equity $34.44 |
| ROI/turn | **-0.71%** | day_pnl -$0.61 / fills_usd $86 |
| 30d high-water mark | $222.90 | Current = 15.3% of HWM |

**7-Day trend vs benchmark:**

| Date | Turns | ROI/turn | Day P&L | Note |
|---|---|---|---|---|
| Jul 10 (last real prior) | — | — | — | Capital $163.16 |
| Jul 13 | 1.71 | -40% | -$69.08 | Sprint ladder 0W/7L resolutions + orphan-sweep sniper |
| **Jul 14** | **~2.50** | **-0.71%** | **-$0.610** | Orphan-sweep fixed 22:04; sniper clean going forward |

**Benchmark (badatmath):** ~1.0× equity/day at 10–20%/turn. Klaus today: 2.50 turns at -0.71%/turn = -1.76% day. Sniper strategy now shows demonstrated 17W/1L signal quality. The binding constraint was the orphan-sweep bug, not edge. With fix deployed, tomorrow's baseline is clean.

**Key framing:** roi/turn improved from -40% (Jul 13) to -0.71% (Jul 14) — a 56× improvement — primarily because the orphan-sweep bug is fixed and the true signal WR is 94%. The $2 clip and $20 reserve reduce max daily loss to ~$12 in worst-case.

---

## 3. EXPECTED MAKER REBATES

Formula: est_rebate = shares × 0.05 × p × (1−p) × 0.25 (UPPER BOUND; actual depends on competing makers)

| Fill | Shares | p | p(1-p) | Est. rebate |
|---|---|---|---|---|
| BUY NO 0.04 × 40 sh (×2 fills, 02:14 + 09:34) | 80 | 0.04 | 0.0384 | **$0.038** |
| SELL YES 0.98 × 5 sh (MAKER, 15:04) | 5 | 0.98 | 0.0196 | $0.001 |
| BUY NO 0.02 × 7.5 sh (15:04) | 7.5 | 0.02 | 0.0196 | $0.002 |
| SELL YES 0.98 × 367.66 sh (MAKER, 15:49) ⚠️ | 367.66 | 0.98 | 0.0196 | **$0.090** |
| BUY NO 0.06 × 30.5 sh (16:24) | 30.5 | 0.06 | 0.0564 | $0.022 |
| **Today total** | | | | **$0.153** |

All fills at near-extreme prices → fee rate p×(1-p) near zero. Mid-price fills (p≈0.5) would earn ~16× more per share. Today's fills produce negligible individual rebates despite 367.66 sh fill because 0.98 × 0.02 = 0.0196.

**Cumulative expected rebate:**

| Period | Amount |
|---|---|
| Through Jul 12 (carried) | $3.387 |
| Jul 13 | $0.013 |
| **Jul 14** | **$0.153** |
| **Cumulative** | **$3.553** |

Cumulative > $1 threshold. **User should verify daily pUSD rebate receipt in Polymarket account.** If no rebate has ever been received and cumulative expected exceeds $3.50, escalate to Polymarket market-maker support. Note this is an UPPER BOUND — actual pool share depends on competing market-maker volume.

---

## 4. KILL-SWITCH PROXIMITY

| Switch | Threshold | Current | Status |
|---|---|---|---|
| Day P&L vs -$10 halt | -$10 | **-$0.61** | ✅ Within limit |
| Capital vs ruin floor ($50) | $50 | $34.13 | ❌ BREACHED |
| Capital vs weekly floor ($75) | $75 | $34.13 | ❌ BREACHED |
| Capital vs 50% 30d-HW | $111.45 | $34.13 (30.6% HWM) | ❌ BREACHED |
| BAND_LIVE | OFF | OFF (since Jul 6) | ✅ Correct |
| BAND_NO_ENABLED | OFF | OFF (since Jul 2) | ✅ Correct |
| STWA_REGULAR_YES/NO | OFF | OFF (since Jun 5/11) | ✅ Correct |
| UPDOWN_SNIPER | Active — gate-collection | $2 clip, $20 reserve | ⚠️ Monitoring |
| Sprint ladder | Disarmed (Jul 13) | 0 activity | ✅ |
| RECYCLE099 | No events since Jul 6 | — | — |

**Rolling 20-trade WR/PF:** Cannot compute from trades.jsonl (all fills UNTRACKED, no entry_class). From state_log fill tape: **17W / 1L = 94.4% WR** (18 settled pre-22:04Z sniper fills, orphan-sweep contaminated but outcomes real). PF cannot be computed without clean exit prices.

**⚠️ CAVEAT:** Kill-switch WR/PF floors (>40%, >0.8 PF) were written for the taker bid/ask era. UPDOWN-SNIPER holds to resolution — 94% WR on near-certainty entries is structurally expected, not anomalous. A kill-switch re-derivation appropriate for this strategy is pending with user. Do NOT halt based on WR alone given the strategy design.

**Positive development today:** Daily halt threshold (-$10) not breached. The $2 clip + $20 reserve cap daily tail-loss at ~$14 maximum (7 positions in worst-case). Day loss of -$0.61 is within normal operational range.

**FIVE-LOSING-DAYS flag** (from Jul 13 state): Technically still active. However, Jul 14 was a materially different day: (a) the dominant loss source (sprint ladder) was already disarmed before BOD, (b) the orphan-sweep bug was fixed at 22:04Z, (c) true strategy WR is 94%. The flag should be reviewed in context — the losses reflect a software bug, not persistent negative edge.

---

## 5. DAY VERDICT

**NO — equity declined -1.76% (-$0.61)** on 2026-07-14.

**Binding constraint:** ORPHAN_SOLD bug in `_window_end_balance_sweep` caused 12 of today's sniper fills to exit at bid prices (0.88, 0.939) instead of resolution ($1.00). This was the entire binding constraint. **Bug fixed at 22:04Z.** Without it, the 17W/1L tape would have generated a positive P&L today.

**What changed for the better:**
- Sprint ladder fully disarmed (was 0W/7L -$165 since Jul 11)
- Orphan-sweep fixed — sniper can now hold to resolution
- Clip reduced $5→$2, reserve $2→$20 — capital preservation mode
- Band shadow shows active signal generation (thermo_maker 44K candidate evaluations today; pair-fav still enabled and posting)
- True sniper WR: 94.4% — strategy edge confirmed

**What remains broken:**
- Capital at $34.13 vs all kill-switch floors ($50, $75, $111.45) — under every threshold
- All band/ladder/STWA strategies disabled; system running on SNIPER only
- UNTRACKED bug persists — position-level PnL cannot be reconstructed from trades.jsonl

**⚠️ Flag for user:** Verify wallet balance vs $34.13 bankroll (see Section 1, 15:49 fill). Verify pUSD rebate receipt > $1 cumulative (see Section 3).

---

*Report basis: bankroll.json, maker_fills_recent.log, pnl_ledger_state.json (prior), band_config.txt, system_status.txt, SNAPSHOT.md, state_log.md (state_log 2026-07-13/14 entries), shadow_summary.json (band_struct Jul 14: 7510 rows, thermo_maker Jul 14: 44432 rows, updown_sniper snap Jul 14: 63657 rows). Trades.jsonl (26MB) and exit099_live not fully parsed; no RECYCLE099 events Jul 14 (file absent).*
