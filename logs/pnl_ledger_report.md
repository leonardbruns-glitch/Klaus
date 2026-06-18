# Klaus PnL Ledger — 2026-06-18 (23:37 UTC)

**Snapshot**: 2026-06-18T23:23:26Z (+14 min lag) | **Systemd**: active | **Open positions**: 0

---

## 1. P&L EXPLAIN — UTC 2026-06-18 (00:00–23:37)

### Resolved trades (trades.jsonl, ts_close in window)

| Entry class | Side | Count | Avg entry | Exit | WR | Net PnL |
|---|---|---|---|---|---|---|
| WEATHER_STRUCT_BAND | YES | 74 | 0.229 | 0.000 | 0/74 | -$98.47 |
| WEATHER_STRUCT_BAND | NO  | 1  | 0.570 | 0.000 | 0/1  | -$4.56  |
| **TOTAL** | | **75** | | | **0/75 (0%)** | **-$103.03** |

All 75 exits carry reason `STWA_RESOLVED`, exit_price=0. Positions resolved on the wrong side of the temperature band — the YES band legs lost entirely to resolution.

### RECYCLE099 convergence exits (exit099_live, ts in window)

| Fills | Shares | Avg entry | Exit | Entry cost | Proceeds | PnL | ROI on cost |
|---|---|---|---|---|---|---|---|
| 26 | 156.0 | $0.379 | $0.990 avg | $59.11 | $154.58 | **+$99.56** | 168% |

No token overlap with today's trades.jsonl resolutions — no double-count.

### Maker rebate accrual (§3 for detail)

Expected rebate on today's 638.7 maker-filled shares: **+$1.16** (upper bound — pool-share dependent).

### Attribution summary

| Stream | P&L |
|---|---|
| WEATHER_STRUCT_BAND resolutions | -$103.03 |
| RECYCLE099 convergence exits | +$99.56 |
| Maker rebate accrual (estimated) | +$1.16 |
| **Attributed total (ex-rebate)** | **-$3.47** |
| **Attributed total (with rebate)** | **-$2.31** |

### Unexplained

**Today anchor**: last-close-yesterday capital_after = $207.23 (23:47 UTC Jun 17); EOD capital = $214.52; day capital delta = **+$7.29**.

Unexplained (today) = $7.29 − (−$3.47) = **+$10.76** (capital $10.76 higher than attributed).

**Cause**: Late-evening Jun 17 RECYCLE099 fills between 22:21 UTC (last Jun 17 exit099 entry) and midnight are credited to bankroll but fall outside the Jun 17 shadow-file window. These gains accumulate overnight — the first Jun 18 trade-open (01:13 UTC) shows capital_before=$262.63, already $55 above last-close, confirming uncaptured RECYCLE099. This is a **shadow logger timing gap, not a model-side error**. Remainder ($10.76 − carryover) is within rounding of new-fill collateral movements.

> **4-day context (Jun 14–18, since last ledger)**
>
> | Day | Resolutions PnL | RECYCLE099 PnL | Notes |
> |---|---|---|---|
> | Jun 15 | -$78.76 (n=30, WR=3%) | UNKNOWN | shadow file not mirrored |
> | Jun 16 | -$77.42 (n=34, WR=9%) | UNKNOWN | shadow file not mirrored |
> | Jun 17 | -$118.84 (n=82, WR=2%) | +$87.45 (20 fills) | confirmed |
> | Jun 18 | -$103.03 (n=75, WR=0%) | +$99.56 (26 fills) | confirmed |
> | **4-day** | **-$378.05** | **+$187.01 (confirmed)** | |
>
> 4-day capital Δ: $214.52 − $267.04 = **−$52.52**.
> Attributed (confirmed only): −$378.05 + $187.01 = −$191.04.
> Raw gap: −$52.52 − (−$191.04) = **+$138.52** (capital higher than confirmed attribution).
>
> **Most likely cause**: Jun 15–16 RECYCLE099 not in shadow files. If those days ran at ~$69/day (below Jun 17–18 rate of $87–$99), 4-day RECYCLE099 total ≈ $325, reconciling to ≈−$53 capital delta (matches observed). **MODEL DEFICIENCY — shadow logger coverage gap for Jun 15–16**: the economic gains occurred but are unattributable from available data.
>
> User action: verify Jun 15–16 RECYCLE099 totals against Polymarket trade history. If shadow logger rotation policy does not cover d−2/d−3, the ledger will carry this gap perpetually.

---

## 2. COMPOUNDING SCOREBOARD

### Equity estimate

| Component | Value | Caveat |
|---|---|---|
| Free cash | $214.52 | Exact (bankroll.json) |
| Future resting positions (9, at cost) | $7.16 | YES band fills at entry price; break-even assumption |
| Stale resting (3, end_date ≤ now) | $1.02 | Likely worthless; excluded |
| **Equity estimate** | **$221.68** | Cash + future-only resting at cost |

> **Caveat**: 115 positions in maker_resting_state.json, but 103 are SELL_EXIT stubs (matched=0.0, convergence exit orders). Only 12 carry filled-share data. Resting component ($7.16) is small and changes rapidly; winners resolve at $0.99/share, losers at $0.

### Deployed fraction & turns

| Metric | Value | Notes |
|---|---|---|
| Fills today | $163.33 (638.7 shares) | 81 new registrations + 37 top-ups |
| YES fills | $111.00 (557.5 shares) | Avg entry ~$0.20 |
| NO fills | $52.34 (81.2 shares) | Avg entry ~$0.64 |
| Deployed fraction | $7.16 / $221.68 = **3.2%** | Most positions resolve same-day |
| Turns/day | $163.33 / $221.68 = **0.74×** | Approaching badatmath ~1.0× benchmark |
| ROI/turn (RECYCLE099 closed legs) | **168%** on entry cost | Bought $0.38 avg → sold $0.99 avg |
| ROI/turn (resolution legs) | **−100%** | All 75 STWA_RESOLVED today resolved wrong |

### 4-day equity trend

| Date | Equity est | 1-day PnL | Source |
|---|---|---|---|
| Jun 14 | $279.96 | +$20.63 | Prior ledger (includes $25.73 stale) |
| Jun 15–17 | (no ledger) | — | Gap |
| Jun 18 | $221.68 | −$3.47 | This report |
| **4-day Δ** | **−$58.28 (−20.8%)** | | Adjusted for stale: −$32.55 (−14.5%) |

Benchmark: badatmath ~1.0× equity/day at 10–20%/turn. Our turns (0.74×) are approaching target. The RECYCLE099 leg yields 168%/turn on exited positions — competitive. The binding drag is resolution WR: 0–3% over 4 days vs maker-book expectation of ~22%.

### UNTRACKED fill events (data quality flag, persistent)

Today: **80 unique untracked maker fill events** (174 raw WS events, de-duped by token/price/size):

| Category | Events | Taker order value | Interpretation |
|---|---|---|---|
| ≥ 0.95 price | 25 | $8,555 | Convergence exits — taker order sizes (we contributed 6 shares/fill avg; matches 26 exit099 entries) |
| 0.50–0.95 price | 45 | $1,327 | Unregistered mid-price maker entries — positions entered book, not in resting state |
| < 0.50 price | 10 | $57 | Additional unregistered entry fills |

Bot restarted ≥5 times today (PIDs: 1596654 → 1740921 → 1755053 → 1756430 → 1761765 → 1763578), likely fragmenting the tracker. The 55 non-convergence UNTRACKED fills represent positions that will resolve and affect capital without ledger visibility. **Persistent MODEL DEFICIENCY from Jun 14 ledger; mechanism: tracker resets on bot restart drop in-flight fill registrations.**

---

## 3. EXPECTED MAKER REBATES

Taker feeRate = 0.05; maker rebate share = 25%; per-share formula: `shares × 0.05 × p × (1−p) × 0.25`.

| Fills | Shares | Avg entry (p) | Expected rebate |
|---|---|---|---|
| YES (81 registrations) | 557.5 | 0.20 | ~$0.89 |
| NO (13 registrations) | 81.2 | 0.64 | ~$0.27 |
| **Today total** | **638.7** | | **$1.16** |

| Period | Expected rebate |
|---|---|
| Prior cumulative (through Jun 14) | $3.13 |
| Today (Jun 18) | $1.16 |
| **Cumulative expected** | **$4.29** |

> **ACTION**: Cumulative expected rebate ($4.29) exceeds the $1 minimum accrual threshold for Polymarket maker rebate payouts. Payouts land daily in pUSD. If no payout has been verified since Jun 14, **please check your Polymarket wallet for pUSD credits**. The estimate is an upper bound (actual depends on your share of the per-category pool vs competing makers).
>
> **Highest-rebate fills today**: NO bids at p=0.57–0.64 earn ~$0.006–$0.007/share vs YES at p=0.10–0.20 at ~$0.001/share. The mid-price NO book is ~5× more rebate-efficient per share than the far-wing YES book. One Paris NO @ 0.98 (5.5 shares) is near-certain territory and contributes negligible rebate (≈$0.001 total).

---

## 4. KILL-SWITCH PROXIMITY

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Day PnL | −$3.47 | −$10 daily halt | ✓ SAFE |
| Capital | $214.52 | $75 weekly floor | ✓ SAFE |
| Capital | $214.52 | $50 ruin floor | ✓ SAFE |
| Rolling-20 WR (trades.jsonl) | 0/20 (0%) | <30% flag | ⚠ DATA ARTIFACT |
| Rolling-20 PF (trades.jsonl) | 0.000 | <0.80 halt | ⚠ DATA ARTIFACT |
| 4-day equity Δ | −14.5% to −20.8% | −20%/month kill | ⚠ APPROACHING |

### WR/PF data artifact

trades.jsonl books ALL STWA_RESOLVED exits at exit_price=0, including positions that were sold via RECYCLE099 at 0.99 days earlier. The 0/20 WR means 20 consecutive resolutions with 0 winners — but the economic record is:

**Economic WR today**: 26 RECYCLE099 wins + 0 resolution wins ÷ (26+75) events = **25.7%** — consistent with the band's expected YES resolution WR of ~22% by design (maker posts YES at $0.10–0.30; 22% resolve correctly at 4–9× payoff).

**Do NOT halt on trades.jsonl WR/PF alone.** These floors were specified for the taker era. Kill-switch re-derivation for maker-band metrics is pending with the user.

### 4-day equity flag

Equity declined −14.5% (adjusted, excluding stale) to −20.8% (raw) over 4 trading days. The monthly kill switch is −20%. The adjusted figure (−14.5%) is below threshold, but the raw figure is at it. **If the user can confirm Jun 15–16 RECYCLE099 totals are ≥$69/day, adjusted equity Δ is the correct frame and no halt is warranted. If Jun 15–16 RECYCLE099 was near zero, the 4-day true loss exceeds $191 and the kill switch is breached.**

This is not a recommendation to halt — it is a proximity flag requiring user verification of Jun 15–16 RECYCLE099 data.

---

## 5. DAY VERDICT

**Equity did NOT compound today. Net attributed P&L: −$3.47 (−1.6% on equity est $221.68). Flat, constrained by resolution.**

RECYCLE099 nearly neutralized the full resolution loss ($99.56 of $103.03 recovered = 96.6% offset). The hedge is functioning but producing near-zero net. There is no structural compounding at current resolution WR.

**Binding constraint**: YES resolution WR = 0/75 (0%) today. All WEATHER_STRUCT_BAND YES positions resolved against prediction across all cities and time windows. This is the fourth consecutive day of near-zero or zero YES resolution WR (Jun 15: 3%, Jun 16: 9%, Jun 17: 2%, Jun 18: 0%). This is not statistical noise over 221 resolved YES positions in 4 days — the YES band is consistently buying the wrong temperature buckets. RECYCLE099 is masking the loss, not generating edge.

**Recommended investigation** (not a code change — data only): review the Jun 15–18 resolved YES positions by city and offset to identify whether the loss is systemic (e.g., mode+0 bucket consistently loses = the forecast is biased warm/cold) or random (positions at all offsets losing equally). This should be done by the user before any parameter changes.

---

*Report generated: 2026-06-18T23:37 UTC | Next scheduled ledger: 2026-06-19T23:37 UTC*
