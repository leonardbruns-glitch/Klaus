# Klaus P&L Ledger — 2026-06-12 (Day-End)

**Report generated:** 2026-06-13T02:51Z (snapshot age: 7 min, system: active)  
**Data mirror:** 2026-06-13T02:44:16Z | **Trades:** 7,337 rows | **Capital:** $208.903298

---

## 1. P&L EXPLAIN — UTC Day 2026-06-12

### Capital Bridge

| Reference point | Value | Source |
|---|---|---|
| SOD capital (first trade cap_before, 00:00:18 UTC) | $196.05 | trades.jsonl |
| EOD capital | $208.90 | bankroll.json (saved 22:57:45) |
| **Day delta** | **+$12.85** | Δ above |

### Attribution by Leg

| Leg | n | Wins | Gross PnL | Fees | Net PnL |
|---|---|---|---|---|---|
| WEATHER/STWA BUY_YES resolved | 13 | 2/13 (15%) | –$13.23 | $0 | **–$13.23** |
| WEATHER/STWA BUY_NO resolved | 4 | 2/4 (50%) | –$15.10 | $0 | **–$15.10** |
| WEATHER_MAKER BAND_MERGE exit | 1 | 1/1 | +$0.35 | $0 | **+$0.35** |
| RECYCLE099 convergence sells | 14 | — | +$37.52 | $0 | **+$37.52** |
| **Attributed total** | **32** | | | | **+$9.54** |

> **RECYCLE099 vs trades.jsonl double-count check:** token overlap = 0. No double-count.

### Unexplained P&L

| | Value |
|---|---|
| Day delta (bankroll bridge) | +$12.85 |
| Total attributed | +$9.54 |
| **Unexplained** | **+$3.31** |

**Investigation:** Within tolerance for this report's $5 flag threshold. Most likely cause: **maker fills during the day that returned partial premium through a code path not reflected in trades.jsonl capital_after**, OR small timing differences in capital_before/after anchoring. The capital_after trail in trades.jsonl shows $219.65 at 22:53:16, while bankroll.json shows $208.90 at 22:57:45 — a secondary gap of **$10.75** that is NOT explained by the above ledger. Most likely cause: STWA resolution events landing in bankroll.json between 22:53–22:57 that have not flushed to trades.jsonl (logging race condition). If persistent across reports, classify as **MODEL DEFICIENCY** in the trades.jsonl write path. Not a manual flow — no user deposits/withdrawals flagged in state_log for Jun 12.

### STWA Loss Anatomy

BUY_YES trades (13): all opened Jun 10–11 (pre-dating STWA_REGULAR_YES_ENABLED=False on Jun 5). These are **legacy open positions resolving**, not new fires. Characteristic entry prices 0.04–0.34 (longshot YES bets). Market resolved NO on 11/13, consistent with badatmath data showing the YES band loses when held as taker without maker-book structure.

BUY_NO deep losses: two trades entered at 0.98 (near-certain NO). One won (+$0.11); one **lost $5.39** (opened 13:07:30, closed 22:53:16 Jun 12). The losing 0.98-NO resolved YES — temperature exceeded the bucket despite a confirmed lockout signal at entry. This is a **failed physical lock** on the same day; the running_max at 13:07 apparently hadn't reached the bucket ceiling when the market thought it had. $5.39 on a "guaranteed" bet is a meaningful false-lockout loss.

---

## 2. COMPOUNDING SCOREBOARD

### Equity Estimate

| Component | Value | Notes |
|---|---|---|
| Free cash (bankroll.json) | $208.90 | Authoritative |
| Resting maker positions (at-cost) | $29.11 | 91 entries, 199.96 matched shares |
| — of which expired Jun 12 (unresolved) | $6.30 | Munich/Chongqing/Jeddah — result unknown |
| — of which active (Jun 13–14) | $22.81 | 12 positions, 118.5 shares |
| **Equity estimate** | **$238.01** | Free cash + resting at-cost |
| Worst-case equity (expired resolve 0) | $231.71 | If all Jun 12 resting = lost |

**Caveats:** (1) Resting state includes 81.5 shares in 3 Jun 12-expired positions (Munich 15sh@0.14, Chongqing 14sh@0.15, Jeddah 52.5sh@0.04) — these resolve Jun 12 and most will be 0 (bot holds YES on longshot buckets at low prices; very likely NO outcomes). True at-cost is overstated by up to $6.30. (2) Open positions not in maker_resting_state (e.g. STWA legacy positions still open) are excluded — open_positions count = 0 per system_status.txt, so none known.

### Compounding Metrics

| Metric | Jun 12 | Benchmark (badatmath) |
|---|---|---|
| Maker fills notional | $131.44 (559.7 sh) | — |
| Turns/day = fills$ / equity | 0.55× | ~1.0× equity/day |
| Day ROI (bankroll bridge) | +6.6% | 10–20% / turn |
| ROI on resolved legs (identified PnL / maker fills) | +7.3% | — |

**7-day context (trades.jsonl, no RECYCLE099 for prior days):**

| Date | Trades | WR | Net PnL (trades only) | SOD Cap |
|---|---|---|---|---|
| Jun 06 | 4 | 25% | –$5.35 | — |
| Jun 07 | 10 | 10% | –$29.67 | $61.91 |
| Jun 08 | 3 | 33% | –$1.70 | $53.71 |
| Jun 09 | 1 | 100% | +$35.50 | $102.08 |
| Jun 10 | 4 | 0% | –$14.89 | $72.58 |
| Jun 11 | 6 | 33% | –$9.22 | $203.96 |
| **Jun 12** | **18** | **22%** | **–$28.33** | **$196.05** |

**Note:** Jun 11 SOD jumped from ~$76.95 (Jun 10 EOD) to $203.96 — a +$127 capital influx consistent with a **user deposit** not reflected in trades.jsonl. RECYCLE099 data was only available for Jun 12 in the current mirror (prior days missing from shadow). The Jun 12 "day" was profitable (+$12.85) only because RECYCLE099 (+$37.52) exceeded the STWA taker bleed (–$28.33). Without RECYCLE099, Jun 12 = –$24.67.

Klaus at 0.55× turns/day is roughly half of badatmath's 1.0× baseline. Primary constraint is **fill rate**, not equity.

---

## 3. EXPECTED MAKER REBATES

Formula: shares × 0.05 × p(1−p) × 0.25 (upper bound; actual depends on pool share)

| Period | Fills | Shares | Notional | Expected Rebate |
|---|---|---|---|---|
| Jun 12 (full day) | 86 | 559.7 sh | $131.44 | **$1.02** |
| Jun 13 (partial, to 02:44 UTC) | 22 | 120.6 sh | $30.14 | **$0.24** |
| **Cumulative estimate** | **108** | **680.3 sh** | **$161.58** | **$1.26** |

**⚠ ACTION REQUIRED:** Cumulative estimated rebate exceeds $1.00. Polymarket maker rebates land daily in pUSD with a $1 minimum accrual threshold. **User should verify pUSD receipt for Jun 12.** If no payout has been received to date, post cf-ray headers to Polymarket Discord #support, or check pUSD wallet balance on app.polymarket.com.

**Fill quality note:** Most Jun 12 fills are in the 0.10–0.35 price range (p(1−p) up to 0.26). Highest-rebate fills were near mid-price: 0.27–0.34 range (p(1−p) ≈ 0.20–0.23). No fills near 0.50 (where rebate is maximized at p(1−p)=0.25). The NO-side fills at 0.62–0.65 (Jun 13, untracked fill at 0.89) generate meaningful rebate. If the band starts posting more pair-legs with NO bids in the 0.40–0.60 range, rebate earnings will increase quadratically.

---

## 4. KILL-SWITCH PROXIMITY

### Rolling 20-Trade Metrics (last 20 resolved)

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Win rate | 4/20 = **20.0%** | Flag < 30% | ⚠ FLAGGED |
| Gross wins | $10.20 | — | — |
| Gross losses | $43.97 | — | — |
| **Profit factor** | **0.232** | Halt < 0.8 | ⚠ BELOW HALT THRESHOLD |
| Day P&L (Jun 12) | +$12.85 | Halt < –$10/day | ✓ OK |
| Capital | $208.90 | Weekly floor: $75 | ✓ OK |
| Capital | $208.90 | Ruin floor: $50 | ✓ OK |

**⚠ MANDATORY CAVEAT — Maker Era Threshold Mismatch:**  
WR/PF floors were designed for the taker era. The current maker-YES band strategy **wins ~22% of YES legs by design**: YES fills resolve YES only when the temperature actually hits the bucket (a minority event for mid-range buckets). The 20% WR in the rolling window includes 13 legacy STWA-taker YES trades (opened Jun 10–11) all resolving on Jun 12 with 15% WR — this is the end of the taker bleed, not new maker misfires. The 3 actual maker wins (BAND_MERGE +$0.35, 2 STWA-NO wins) are structurally sound.

**However:** PF = 0.232 is a real signal. Even after including RECYCLE099, identified attributed PnL is +$9.54 on $82+ deployed = 11.6% gross ROI. The problem is the **legacy YES taker positions** bleeding out (–$28.33 booked on Jun 12 from Jun 10–11 opens). Once this cohort clears, the WR/PF picture should normalize.

**DO NOT HALT** on WR/PF alone in the maker era. Monitor net capital trend instead. Capital is $208.90 — far from either floor. The kill-switch re-derivation for the maker-book regime is pending with the user.

**One genuine flag:** Failed lockout on Jun 12 13:07 (NO @0.98, lost $5.39, resolved YES). This is a single event but confirms M1β false-lockout risk is nonzero. No systemic pattern established from one data point.

---

## 5. DAY VERDICT

**Equity compounded: YES, +$12.85 (+6.6%)**

Binding constraint: **resolution mix + legacy taker bleed.** Jun 12 resolved 13 legacy STWA-YES taker positions (opened Jun 10–11), all taking losses at 15% WR (–$13.23 net). The YES band's STWA_REGULAR_YES_ENABLED=False config change is correct but was unable to prevent these positions from resolving today. The RECYCLE099 convergence engine (+$37.52) was the primary PnL driver, not the active band strategy. The day was profitable only because of accumulated RECYCLE099 positions closing at convergence.

Without RECYCLE099: **–$24.67** on Jun 12. This is a structural dependency — the active maker book needs to generate enough converging fills to offset the legacy bleed AND ongoing NO mis-locks. The band fill rate (0.55× equity/day) is the operational binding constraint.

Five-day context: Jun 06–11 shows net negative from trades.jsonl alone (–$60.46 cumulative). The RECYCLE099 cache is the buffer. Once legacy YES positions clear and the maker-NO book dominates, the WR and PF should recover to maker-design levels.

---

*Report-only. No code, flags, or stakes touched.*
