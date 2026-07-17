# Band Execution & Markout Audit — 2026-07-17

**Snapshot**: `2026-07-17T07:08:32Z` (age < 6h ✓)  
**System**: `klaus systemd: active` ✓  
**Auditor**: exec-audit-agent  
**Source branch**: `data-mirror` (commit `361ec8504`)

---

## Live Configuration (band_config.txt — authoritative)

| Flag | Value | Notes |
|---|---|---|
| `BAND_LIVE` | **False** | Wind-down since 2026-07-06: equity $108.35 < 50%·30d-HW $222.90 |
| `BAND_NO_ENABLED` | **False** | Rail-halt since 2026-07-02: 7d realized WR 39.2% (n=51) |
| `BAND_YES_LIVE_MIN_DOUT` | 9 | Standalone YES paused (d+0..d+8 never fire live) |
| `BAND_PAIR_FAV_ENABLED` | True | Shadow-only while BAND_LIVE=False |
| `MAKER_SHADOW_ENABLED` | True | Shadow quote tracking active |
| `STWA_REGULAR_YES_ENABLED` | False | Disabled 2026-06-05 |
| `STWA_REGULAR_NO_ENABLED` | False | Disabled 2026-06-11 |

**Effective state**: Engine is running and generating shadow fires, but BAND_LIVE=False blocks all capital deployment. No new maker bids posted since 2026-07-06.

---

## Section 1 — Fill Tape (24h + 7d)

### Format finding
The `maker_fills_recent.log` file contains **exclusively `[USER-WS] UNTRACKED FILL` warnings** — zero `[MAKER-FILL]` structured entries, zero `[STRUCT-BAND-Q]` queue stats, zero `reaped dead entry` lines. The band maker's structured fill logger produced no output because no positions were opened by the current bot instance. All fills observed are from pre-wind-down legacy orders.

### 7-day tape (Jul 14–17, window captured at 07:08Z)

| Metric | Value |
|---|---|
| Total CONFIRMED fills | 78 |
| MAKER fills | 12 |
| TAKER fills | 66 |
| 24h CONFIRMED fills (Jul 17 to snapshot) | 3 |
| 24h fill value (TAKER sells) | $43.92 |

**By trader_side (CONFIRMED):**

| Side | Count | Total Value | Price Range |
|---|---|---|---|
| MAKER | 12 | ~$518.57 | $0.02–$0.98 |
| TAKER | 66 | $412.41 | $0.87–$0.999 |

**MAKER fill detail:**

| Subtype | Count | Total | Interpretation |
|---|---|---|---|
| BUY at $0.02–$0.09 | 8 | $11.07 | Adverse fills — old YES bids on near-zero legs resting on CLOB; outcome resolved against band |
| SELL at $0.96–$0.98 | 4 | $507.50 | Exit fills — YES positions held to near-resolution, maker sell orders filled |

Notable MAKER SELL fills:
- Jul 14 15:49 — 367.66 shares @ $0.98 = **$360.31**
- Jul 16 21:39 — 147.05 shares @ $0.96 = **$141.17**
- Jul 14 15:04 — 5.0 shares @ $0.98 = $4.90

**By price band (CONFIRMED):**

| Price Band | Count | Value |
|---|---|---|
| < 0.10 | 8 | $13.07 |
| 0.10 – 0.30 | 0 | $0.00 |
| 0.30 – 0.50 | 0 | $0.00 |
| 0.50 – 0.85 | 0 | $0.00 |
| > 0.85 | 70 | $919.90 |

**TAKER fills (66, user manual sell-exits):** Daily breakdown:
- Jul 14: 26 fills, $139.77
- Jul 15: 19 fills, $90.82
- Jul 16: 18 fills, $137.91
- Jul 17 (to 07:08Z): 3 fills, $43.92

**Fill rate**: Not applicable — no new posts since 2026-07-06. All fills are exits from the pre-wind-down portfolio.

---

## Section 2 — NO-Parity Monitor

**band_posted_state.json**: Last tokens posted 2026-07-06 (10 tokens, $48.01). No posts on Jul 7–17.

**maker_resting_state.json**: `{}` — empty (zero live resting orders per bot state).

**Shadow fires by side (Jul 12–17, 5 days, n=64 fires):**

| Side | Legs | Share |
|---|---|---|
| YES | 290+ | 100% |
| NO | 0 | 0% |

NO-parity alert threshold: < 25% NO share on days with ≥10 live posts. **Vacuous — zero live posts exist.** The NO=0% reading is not a bug; it reflects BAND_NO_ENABLED=False.

**NO-starvation fix verification (2026-06-12 commit)**: Cannot be verified — no live NO posting has occurred since the fix date falls within the active period, but BAND_NO_ENABLED=False before live data for this audit window exists. Code fix is present; live verification requires re-enabling BAND_NO.

---

## Section 3 — Queue Health

**Source**: `[STRUCT-BAND-Q]` lines — **Count: 0** (no queue stats logged to fill tape during window).

**Shadow engine activity (from band_struct_lite per day):**

| Date | Records | Shadow Fires | Live Fires | Reasons |
|---|---|---|---|---|
| 2026-07-12 | 169 | 14 | 0 | no_band:40 converged:24 sum_gate:29 fire:14 |
| 2026-07-13 | 167 | 11 | 0 | no_band:42 converged:25 sum_gate:29 fire:11 |
| 2026-07-14 | 168 | 10 | 0 | no_band:37 converged:30 sum_gate:29 fire:10 |
| 2026-07-15 | 174 | 15 | 0 | no_band:44 converged:22 sum_gate:29 fire:15 |
| 2026-07-16 | 163 | 14 | 0 | no_band:42 converged:18 sum_gate:29 fire:14 |
| 2026-07-17 (partial) | ~60 | 10 | 0 | — |

The engine completes cycles and generates 10–15 shadow fires/day across 8–10 cities (London, Beijing, Munich, Wuhan, Chengdu, Seoul, Shanghai, Taipei, Chongqing, Tokyo). `sum_gate` fires at 29/day every day = consistent gate hitting (sum_ask ≥ BAND_SUM_MAX=0.85 on most markets, meaning markets are efficiently priced within the band sum).

**Books pinned at 80 / yes_books at 50**: Cannot assess — no [STRUCT-BAND-Q] lines. Shadow engine running implies fetches complete.

**Deployment stall pattern (cash_preskip > 200, posted=0)**: Cannot quantify, but capital is intentionally idle by BAND_LIVE=False charter mandate — not a technical stall.

---

## Section 4 — Resolution Markout (Fill Quality)

**Status**: Partial — band_resolution_join.py cannot be run (git fetch timed out; CLOB API access via live execution path not available in audit environment). Formal winner's-curse computation requires resolution data and is deferred.

**Observable data:**

MAKER SELL exit fills at $0.96–$0.98 (n=4, $507.50 total). Given `BAND_PX_CEIL = 0.45` (max entry for d+1/d+2) and `BAND_PX_CEIL_D0 = 0.25` (max entry d+0), the implied ROI on these exits is:

| Entry price assumption | Exit price | Implied ROI |
|---|---|---|
| $0.25 (d+0 max) | $0.96–$0.98 | 284–292% |
| $0.45 (d+1/2 max) | $0.96–$0.98 | 113–118% |
| $0.15 (typical mid-band) | $0.96–$0.98 | 540–553% |

MAKER BUY fills at $0.02–$0.09 (n=8, $11.07 total): These are adverse fills on resting YES bids where the underlying resolved NO. Positions at $0.04–$0.09 entry are now near-zero. These represent losses, but dollar magnitude is small.

**n = 12 MAKER fills. Below 40-trade floor — data collection only, no edge conclusions.**

**Winner's-curse test**: Cannot run formally. The MAKER BUY adverse fills ($11.07) vs MAKER SELL wins ($507.50) suggest fill asymmetry in favor of the maker, but this is exit-period liquidation, not representative of fill selection during active posting.

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|---|---|
| Reaped dead entry lines (7d) | 0 |
| Live resting quotes | 0 (maker_resting_state = {}) |
| Quotes older than 24h | 0 |
| Quotes older than 48h | 0 |

**Alert threshold** (> 20 quotes older than 48h): **Does not fire.** No live quotes exist per bot state.

**Caveat**: See ALERTS — the bot's resting state (`{}`) may not reflect actual CLOB state. UNTRACKED FILL activity on Jul 14–16 with `trader_side=MAKER` confirms real CLOB orders exist that the bot doesn't track. Some of those positions may still be resting and not captured in maker_resting_state.json.

---

## Section 6 — Cash Velocity

| Metric | Value | Notes |
|---|---|---|
| Capital (bankroll.json) | $30.56 | CAVEAT: user sells manually; not a reliable PnL measure |
| Resting $ (bot state) | $0.00 | Empty book per maker_resting_state |
| Fills last 24h (Jul 17) | $43.92 | 3 TAKER sell exits; no maker fills |
| Turns/day (exit value / capital) | 1.44× | Liquidation velocity, not strategy velocity |
| Net exit proceeds Jul 14–17 | $932.48 | TAKER $412.41 + MAKER SELL $507.50 + MAKER BUY ($11.07 outflow) |
| Capital deployed in shadow | $0 | BAND_LIVE=False |

**Historical context (band_posted_state.json — active period Jun 17 – Jul 6):**
- 496 tokens posted over 20 days ($2,204.23 total capital deployed)
- Average: 24.8 tokens/day, $110.21/day deployed
- Average stake per token: $2.57 (early Jun) rising to $8.75 (late Jun) as band tuning evolved
- Peak day: 2026-06-18, 94 tokens, $260.25

Benchmark vs badatmath (1.0 turn/day at 10–20% ROI/turn): Not applicable in wind-down mode. The $110/day deployment rate during active period implies moderate velocity; without matching fill data for that period, ROI/turn cannot be computed here.

---

## ALERTS

### ALERT 1 — UNTRACKED RESTING ORDERS ON CLOB (Confirmed)

**Severity: HIGH — operational integrity**

The fill tape contains 12 MAKER-side CONFIRMED fills ($518.57 total) between Jul 14–16, all logged as `UNTRACKED FILL: no tracker entry, no open position`. This means:

1. Real resting orders exist on the Polymarket CLOB that the bot's tracker has no record of.
2. `maker_resting_state.json = {}` — the bot's own state file shows zero resting orders. This is a false negative.
3. The MAKER BUY fills at $0.02–$0.09 (adverse fills) confirm orders are resting at low prices. Some of these may still be active and await resolution.
4. The MAKER SELL fills at $0.96–$0.98 (large: $360 and $141) confirm high-value resting sells existed and were filled — these have been cleared. But additional small BUY stubs may still be resting.
5. This untracked exposure persists across the bot restart on 2026-07-15 02:40Z (Jul 14 MAKER fills pre-restart; Jul 15–16 fills post-restart) — the restart did NOT clean up untracked CLOB state.

**Potential cause**: Orders placed before BAND_LIVE=False (2026-07-06) were not cancelled when the band went to wind-down mode. The CLOB has GTC orders resting; the bot's maker_resting_state lost sync with actual CLOB state.

### ALERT 2 — FILL LOGGER DARK (Structural gap)

**Severity: MEDIUM — observability**

Zero `[MAKER-FILL]` lines in the 7-day fill tape. While explained by BAND_LIVE=False (no new bids), the UNTRACKED fills reveal that fills ARE occurring — they're just not being captured by the structured fill logger. When BAND_LIVE is re-enabled, verify that maker_fills_recent.log begins producing `[MAKER-FILL]` lines; an UNTRACKED FILL flood would indicate a tracker bug that persists into the live period.

---

## Summary (3 lines)

**Fills/day**: 0 bot-tracked fills/day (band in wind-down since Jul 6). 78 CONFIRMED fills in 7d tape are all UNTRACKED exits from pre-wind-down inventory — $932.48 net exit proceeds (Jul 14–17), $43.92 on Jul 17 (partial).

**NO-share**: 0% NO (BAND_NO_ENABLED=False; vacuous check — no live posts at all since Jul 6).

**Binding execution constraint today**: BAND_LIVE=False (charter wind-down mandate). Shadow engine is healthy (10–15 fires/day across 10 cities, sum_gate ratio normal). One structural concern: untracked CLOB resting orders (ALERT 1) represent unknown exposure; residual BUY stubs at $0.02–$0.09 may still be resting and should be verified/cancelled.
