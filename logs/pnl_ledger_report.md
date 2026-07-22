# Klaus PnL Ledger — 2026-07-22 (Day-End 23:37 UTC)

**Snapshot age:** 11 min (2026-07-22T23:26:16Z) — FRESH, abort condition not triggered  
**System status:** `klaus systemd: active` — operational  
**Prior-state date:** 2026-07-21 | Prior capital: $21.495442

---

## Section 1 — P&L Explain (UTC day 2026-07-22)

### Capital Delta

| Item | Value |
|---|---|
| Capital (prior ledger, Jul-21) | $21.495442 |
| Capital (bankroll.json, saved 00:00:09 UTC, stale 23.4h) | $21.495442 |
| **Net capital delta** | **$0.00** |

> **BANKROLL STALE — 5th consecutive day.** `bankroll.json` written at midnight (00:00:09 UTC) and not updated during the day. CLOB cash not independently verified today (the morning research audit at 10:45Z reported "equity deployed $0" but did not explicitly confirm CLOB balance — contrast with yesterday's 11:40Z EVOLVE which stated CLOB-actual $21.495442 exactly). Capital figure is inferred from stale data + exec-audit fills=0, not CLOB-confirmed. **MODEL DEFICIENCY — bankroll.json write frequency.** Fifth consecutive flag (Jul-18/19/20/21/22).

### Attributed P&L Legs

| Leg | Realized P&L | Source |
|---|---|---|
| Bot fills (taker/maker) | $0.00 | Exec audit 2026-07-22: fills=0, BAND_LIVE=False, 0 alerts |
| RECYCLE099 convergence sells | $0.00 | `data/shadow/2026-07-22/exit099_live.jsonl` absent |
| STWA resolutions | $0.00 | No resolution events visible; positions remain overdue-unresolved (see note) |
| Maker rebate accrual | $0.00 | `maker_resting_state.json = {}` — no resting orders |
| **Total attributed** | **$0.00** | |

**STWA positions note:** Three positions bought Jul-17/18/19 totalling $14.576 at cost remain unresolved. All were flagged "overdue_unresolved" as of the Jul-21 ledger (resolution dates passed Jul-20). No resolution event observed in today's data (no bankroll jump, no entry in trades.jsonl detectable via exec audit, exit099 absent). `Open positions: 0` in system_status may indicate bot state only, not Polymarket on-chain settlement. These positions are NOT double-counted in the cash figure — the $14.576 was already spent; the $21.495 is liquid cash only. True equity delta awaits resolution. Most likely explanation for "overdue": Polymarket weather market resolution latency or extended dispute window.

### UNEXPLAINED P&L

UNEXPLAINED = delta_capital - attributed = $0.00 - $0.00 = **$0.00**

Clean. No model-deficiency alarm on the P&L line today. Zero-fill mode is fully consistent with $0 delta.

---

## Section 2 — Compounding Scoreboard

### Equity Estimate (Jul-22)

| Component | Value | Caveat |
|---|---|---|
| CLOB liquid cash | $21.495 | Stale bankroll.json; CLOB not re-verified today |
| STWA Jul-17 open (3 tokens) | $8.060 at cost | Overdue; true value in {$0, $24+ per leg depending on settlement} |
| STWA Jul-18 open (1 token) | $3.590 at cost | Overdue |
| STWA Jul-19 open (146.33sh @ $0.02) | $2.926 at cost | Overdue; YES upside approx +$143 if market resolves YES |
| **equity_est (at cost)** | **$36.071** | UNCHANGED from Jul-21 — no new fills, no resolutions |

**CAVEAT:** Equity range [$21.495 (all NO/zero) to $167+ (Jul-19 YES: 146.33sh pays $1.00 = +$143.40)]. The $36.071 figure has been static for 3+ days and is increasingly unreliable as the overdue positions create an unobservable equity uncertainty band. True equity cannot be confirmed without a CLOB wallet inspection.

### Throughput & Turns

| Metric | Today (Jul-22) | Jul-21 | 7d Trend |
|---|---|---|---|
| Fills (USD) | $0.00 | $0.00 | $0 every day since Jul-19 |
| Turns/day | N/A | N/A | Day 3 consecutive zero-fills |
| ROI/turn | N/A | N/A | N/A |
| Equity deployed | 0% | 0% | All paths disarmed since Jul-6 (BAND_LIVE) / Jul-2 (BAND_NO) |

**vs. benchmark:** Reference operator (badatmath) targets ~1.0x equity/day turns at 10-20%/turn. Klaus at 0 turns/day = 0% of the benchmark throughput. This is deliberate — G8 gate is collecting, not live. The gap is structural until the gate resolves.

**G8 gate shadow throughput:** n=72 (70W/2L) as of evening EVOLVE. Shadow WR 97.2%. Rate: ~15 new observations/day (n=57 to 72 today). Shadow data is not real capital — it does not contribute to fills or turns.

---

## Section 3 — Expected Maker Rebates

No maker fills today (maker_resting_state = {}, exec audit fills=0, no thermo_maker.jsonl for Jul-22).

| Metric | Value |
|---|---|
| New rebate accrual today | $0.00 |
| Cumulative expected (upper bound) | $3.917 (unchanged from Jul-21) |

> **USER ACTION REQUIRED:** Cumulative expected maker rebates exceed $1.00 threshold ($3.917 upper bound). Polymarket maker rebates land daily in pUSD, min $1 accrual threshold. If no pUSD credit has been received in the wallet since these fills, verify receipt. This is an upper-bound estimate — actual depends on competing maker volume in each category. No new mid-price fills today to report (no fills = no rebate exposure).

---

## Section 4 — Kill-Switch Proximity

### Floors

| Check | Status |
|---|---|
| Day PnL $0.00 vs -$10 daily halt | **CLEAR** |
| Capital $21.495 vs $75 weekly floor | **BREACHED** — $53.51 below floor; carry-over waiver in effect |
| Capital $21.495 vs $50 ruin floor | **BREACHED** — $28.51 below floor; carry-over waiver in effect |
| Capital $21.495 vs $40 kernel floor | **BELOW KERNEL** — blocks all path re-arms without owner authorization |

### G8 Gate (SNIPER-only operative kill mechanism)

| Field | Value |
|---|---|
| n (observations) | 72 |
| Wins / Losses | 70W / 2L |
| WR (point) | 97.2% |
| CI-lo (approx) | ~0.904 |
| Breakeven rate (BE) | ~0.968 |
| Gap (CI-lo vs BE) | ~-0.064 (CI-lo below BE = KILL signal) |
| PASS branch reachable? | NO — EVOLVE: "pass-branch unreachable before n=400-3000" |
| KILL branch ETA | ~n=100 (~Jul-23 per prior research forecast) |
| **Trajectory** | **KILL is the realistic resolution** |

**2nd loss event:** The 2nd cumulative gate loss materialized between the Jul-21 evening EVOLVE (56W/1L at n=57) and today's morning EVOLVE (63W/2L at n=65). The "xrp cell first loss (17W/1L -$1.50)" noted in the evening EVOLVE is the XRP sub-cell's first individual loss within the broader G8 dataset — paper/shadow tracking only (fills=0 confirmed).

> **WR/PF CAVEAT:** The CLAUDE.md WR (<30%) and PF (<0.8) kill floors were written for the taker-era bot. The sniper/G8 design targets ~98% WR on YES legs with 4-5x payoffs; standard WR thresholds do not apply. The G8 gate (CI-lo vs BE) is the correct kill instrument for the current architecture. Kill-switch re-derivation with the owner is listed as pending.

### Operational Flags

| Flag | Status |
|---|---|
| BAND_LIVE | False (cut Jul-6, equity < 50% of 30d HW $222.90) |
| BAND_NO_ENABLED | False (cut Jul-2, 7d WR 39.2%) |
| STWA_REGULAR YES/NO | Disabled |
| UPDOWN_STOP | Active |
| LDA | Stopped (rolling-20 net -$36.39 < -$30 rail) |
| MAKER_SHADOW_ENABLED | True — shadow only, no live fills |
| BAND_PAIR_FAV_ENABLED | True — but gated by BAND_LIVE=False |
| Disk (23:26Z snapshot) | **85%** (79G used / 97G, 15G free) |

**Disk:** Significantly improved from the 94% crisis earlier today. The EVOLVE daily commit confirmed "disk reclaim round 2 (94%->83%)." By 23:26Z the disk has grown back to 85% (2pp drift in ~12h ~250MB/h logging rate). At this rate, next critical threshold (~94%) is ~8-9 days away. Monitor; no immediate action needed tonight.

---

## Section 5 — Day Verdict

**FLAT — equity neither compounded nor declined today. Day PnL $0.00 (0.00%). Day 3 of consecutive zero-fill days.**

Binding constraint: all live trading paths disarmed (BAND_LIVE=False, BAND_NO disabled, STWA stopped, UPDOWN stopped, LDA stopped). Capital $21.495 is $18.51 below the $40 kernel floor that gates any re-arm. No path to fills without owner-authorized re-arm.

**G8 gate is the critical path:** n=72, 70W/2L. EVOLVE has declared the pass-branch unreachable; KILL at n~100 is the most likely resolution (~Jul-23). Owner should prepare the next-phase decision (restart with new design vs wind-down).

**STWA wildcard:** 3 positions ($14.576 at cost) remain overdue-unresolved from Jul-17/18/19. A YES resolution on the Jul-19 leg (146.33sh) would deliver ~+$143 to the wallet without any bot action. This event, if it occurs, will appear as a large unexplained capital jump in the next ledger — attribute to STWA FIRST before flagging as unexplained.
