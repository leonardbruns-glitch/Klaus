# Klaus PnL Ledger — 2026-07-10
**Generated:** 2026-07-10T23:37Z (scheduled day-end run)
**Snapshot age:** 10 min (2026-07-10T23:26:56Z) — FRESH ✓
**System:** `active` ✓

> **NOTE — 3-DAY LEDGER GAP:** Prior ledger ran 2026-07-07T23:37Z. Runs for Jul 08 and Jul 09 were missed (cloud routine stale; state_log flagged this at 65h+ lag). Capital gap Jul 07→10 is noted in Section 1; today's report covers the Jul 10 UTC window only.

---

## 1. P&L Explain — 2026-07-10 UTC

### Capital Anchors
| Field | Value | Source |
|---|---|---|
| Capital (start of day) | $158.630 | bankroll.json `daily_start_capital` |
| Capital (snapshot 23:26Z) | $163.164 | bankroll.json `capital` |
| Day delta | **+$4.535** | delta |
| Prior ledger capital (Jul 07) | $136.766 | pnl_ledger_state.json |
| 3-day total Jul 07→10 | **+$26.398** | gap not covered by prior runs |

### Today's Fills by Leg

**Engine (BAND/STWA/RECYCLE099):** $0.00. `BAND_LIVE=False` since 2026-07-06 wind-down, day 4. All 19 band shadow fire events today ran with `live=false`. Last RECYCLE099 exit: 2026-07-06 17:02Z (+$4.95, shares=9 entry=0.44 exit=0.99).

**UNTRACKED TAKER fills (Jul 10, via WebSocket `[USER-WS]`):** These are fills on positions placed by a prior bot instance (PIDs 274925/424674, pre-Jul-08 restart at 22:03Z). The current instance (PID 468863) has no tracker entry for them — they generate cash flows that DO appear in `bankroll.capital` once settled.

| Time (UTC) | Token | Side | Shares | Price | Cost/Proceeds | Resolution |
|---|---|---|---|---|---|---|
| 01:30Z | `4663735390478197` | BUY | 47.77 | $0.37 | -$17.67 | — |
| 02:30Z | `1671958678319565` | BUY | 17.7 | $0.42 | -$7.43 | Open? |
| 03:40Z | `1132101340603498` | BUY | 31.25 | $0.50 | -$15.63 | Open? |
| 08:40Z | `4663735390478197` | SELL | 47.0 | $0.992 | +$46.62 | Resolved YES |

**Gross P&L from settled leg (token 4663...):** +$46.62 − $17.67 = **+$28.95** pre-fee. Estimated taker fee (p=0.37, ~2%): −$0.35 buy + −$0.05 sell ≈ **+$28.55 net**.

**Open UNTRACKED BUYs at snapshot:** Tokens 1671... and 1132... had no visible SELL in the 7-day log tail. Their cost ($7.43 + $15.63 = **$23.06**) is already deducted from capital; if open, they represent deployed equity not reflected in cash. Status at 23:26Z: unknown (bot shows `open_positions=0` but this only counts tracked positions).

### Attribution Bottom-Up

| Component | PnL | Note |
|---|---|---|
| Engine (BAND/STWA) | $0.00 | Dark, day 4 |
| RECYCLE099 | $0.00 | No file for Jul 10 |
| UNTRACKED — token 4663 resolved | +$28.55 | Net after estimated fees |
| UNTRACKED — tokens 1671+1132 cost deployed | −$23.06 | Cost spent, proceeds unknown |
| **Total attributed** | **+$5.49** | |
| **Actual day delta** | **+$4.535** | |
| **UNEXPLAINED** | **−$0.96** | |

**Most likely cause of unexplained −$0.96:** Fee estimation error (taker fee model rough; actual fees may be higher) and 0.77 unaccounted shares (47.77 bought vs 47 sold on token 4663). Below $5 threshold. **NOT MODEL DEFICIENCY.**

### 3-Day Gap Attribution (Jul 07→10, informational)
From maker_fills_recent.log, Jul 08-09 UNTRACKED fills visible:
- Jul 08 buys: 18@0.38, 130.5@0.34, 44.25@0.55 (3 prior-instance positions)
- Jul 09 sells: 44@0.996 (+$19.48 gross win), 129@0.992 (+$76.50 gross win)
- Jul 09 buys: 129@0.399, 37@0.38, 10@0.53 (more ladder/prior-instance positions)

Not all Jul 08 buys have matching sells in the 7d log → some resolved via auto-settlement with no SELL event logged. The +$21.86 capital gain Jul 07→10-start is consistent with a mix of resolved YES positions from prior-instance ladder shots. Attribution is approximate; primary cause is unbooked auto-resolution of pre-restart UNTRACKED positions. **NOT MODEL DEFICIENCY — known tracking gap from bot restart cycle.**

---

## 2. Compounding Scoreboard

| Metric | Value | Caveat |
|---|---|---|
| Equity (capital only) | **$163.16** | Cash. AUTHORITATIVE floor. |
| Equity (upper bound) | **~$186.22** | If 2 open UNTRACKED BUYs resolve YES (+$23.06 proceeds) |
| True equity estimate | **$163.16–$186.22** | Exact value unknown; 2 untracked positions unresolved |
| Deployed fraction (untracked) | ~14.1% | $23.06 / $163.16 |
| Engine fills today ($) | $0.00 | BAND_LIVE=False |
| Engine turns/day | 0.00 | — |
| Engine ROI/turn | N/A | — |

**7-day compounding trend (engine only):**

| Date | Capital | Engine Fills | Turns | Notes |
|---|---|---|---|---|
| Jul 07 | $136.77 | $0 | 0 | Sprint ladder +$28.42 |
| Jul 08 | ~$136.77* | $0 | 0 | Prior-instance fills untracked |
| Jul 09 | ~$158.63* | $0 | 0 | Prior-instance fills untracked |
| **Jul 10** | **$163.16** | **$0** | **0** | UNTRACKED fills +$4.53 net |

*Estimated from bankroll progression; Jul 08-09 runs were missed.

**vs benchmark:** badatmath runs ~1.0× equity/day at 10-20%/turn. Klaus engine = **0 turns** for 4 consecutive days. The +$26.40 capital gain since Jul 07 is entirely from prior-instance UNTRACKED positions resolving, not from the current engine. This is not compounding — it is the wind-down tail of pre-restart positions paying out.

**Shadow fire volume today:** 19 fire events (all `live=false`), 11 cities, d+1/d+2 focus. Shadow book is active; live posts are gated by `BAND_LIVE=False`. If BAND_LIVE were enabled, the engine would have fired today.

---

## 3. Expected Maker Rebates

**Today's fills:** All 4 fills (3 BUY, 1 SELL) are tagged `trader_side=TAKER`. No maker fills today. No maker orders resting (`maker_resting_state={}`).

| Type | Fills $ | Expected Rebate |
|---|---|---|
| Maker fills today | $0 | $0.00 |
| Taker fills today | ~$87.35 notional | $0.00 (taker = pays fee, no rebate) |

**Cumulative expected rebate:** $3.17 (carried from Jul 07; no new accrual).

> **USER ACTION:** Cumulative expected maker rebate ($3.17) exceeds the $1 minimum payout threshold. Payouts land daily in pUSD. Verify receipt in your Polymarket account. If no payout has been received, post to Polymarket Discord #support with your wallet address. Note: this is the *upper-bound pool-share estimate* — actual may be lower depending on competing maker volume.

> **Note on mid-price fill:** Token 1132101340603498 was bought at p=0.50 (exact mid). This is the quadratically highest fee bucket (p*(1-p)=0.25 maximum). Had this been a maker fill instead of taker, it would earn the highest rebate per dollar. Flag for maker-strategy consideration if BAND_LIVE is re-enabled.

---

## 4. Kill-Switch Proximity

| Check | Threshold | Current | Status |
|---|---|---|---|
| Day PnL vs halt | −$10.00 | +$4.53 | **CLEAR** (buffer $14.53) |
| Capital vs weekly floor | $75.00 | $163.16 | **CLEAR** (buffer +$88.16, 117.5%) |
| Capital vs ruin floor | $50.00 | $163.16 | **CLEAR** (buffer +$113.16, 226%) |
| Rolling 20-trade WR | flag <30% | N/A — 0 engine fills Jul 07-10 | **N/A** |
| Rolling 20-trade PF | flag <0.8 | N/A | **N/A** |

**Rolling WR/PF context:** state_log reports 7d realized −$71.52, PF 0.108, n=26 — but ALL 26 are pre-wind-down tail-NO positions (opened Jul 02-06). Post-cut engine flow = 0. These numbers reflect the closed tail book, not ongoing engine performance.

> **CAVEAT:** WR and PF kill-switch thresholds were designed for the taker-era strategy. The current maker/band book wins ~22% of YES legs by design at 4-5× payoff structure. Reporting WR/PF proximity here for completeness only. **Do NOT recommend halt on WR alone.** Kill-switch re-derivation for maker era is pending with user.

---

## 5. Day Verdict

**Equity compounded: YES — +2.86%** (capital $158.63 → $163.16, +$4.53).

Source of gain: entirely from UNTRACKED fills (1 resolved prior-instance position, net ~+$28.55; partially offset by 2 unresolved BUY costs still deployed −$23.06). Engine contribution: $0.

**Binding constraint:** `BAND_LIVE=False` (day 4). The shadow band engine fired 19 times today across 11 cities — it is calibrated and would trade if enabled. The re-enable decision is scheduled for the weekly review (target 2026-07-12). Standalone-YES band premise remains dead through Jul 10: disp_ratio trigger met on only 1/8 days (Jul 3-10), never 2 consecutive, median-city ≤0.80 all days.

**Operational note:** `BAND_LIVE=False` freeze expired (was Jul-08 21:53Z). G7 pair evidence gate: n=29 pair combined ROI +13.1%, ambiguous at n — collection continues. MIN_LOCKOUT_LIVE re-enable deferred to Jul 11 (72h anti-thrash ends 22:05Z). No live changes today.

**Capital trajectory is healthy** ($163.16 vs $50 ruin floor). No action required on capital.

---
