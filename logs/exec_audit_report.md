# Klaus Band Execution & Markout Audit
**Date:** 2026-07-18  
**Snapshot:** 2026-07-18T07:09:05Z (age < 6h ✓)  
**System:** `klaus systemd: active` ✓  
**Capital:** $37.57 (bankroll.json)  
**Trades total (all-time):** 8,225

---

## CONTEXT: Band Maker Status

**BAND_LIVE = False** (wound down 2026-07-06; equity $108.35 < 50% · 30d-HW $222.90 charter trigger)  
**BAND_NO_ENABLED = False** (rail-halt 2026-07-02; 7d realized WR 39.2%, n=51)  
**BAND_YES_LIVE_MIN_DOUT = 9** (standalone YES paused 2026-07-03; 9=never fires)  
**BAND_PAIR_FAV_ENABLED = True** (parameter set, but gated by BAND_LIVE=False)  
**MAKER_SHADOW_ENABLED = True** (shadow quoting active; not live)  
**BAND_SHADOW = True** (band shadow evaluation active; not live)

The band maker strategy has been fully wound down since 2026-07-06. All sections below report against the band-maker tracking framework. The active live strategy is the UPDOWN sniper (`strategy.weather_arb`); its fills appear in the log as `[USER-WS] UNTRACKED FILL` warnings outside the band tracker's scope and are noted separately.

---

## Section 1 — Fill Tape (24h + 7d)

### Band [MAKER-FILL] fills

| Window | Fills (n) | $ filled | By side | By price band |
|---|---|---|---|---|
| 24h (Jul 17 07:09 → Jul 18 07:09) | **0** | $0.00 | — | — |
| 7d (Jul 11 → Jul 18 07:09) | **0** | $0.00 | — | — |

No `[MAKER-FILL]` lines appear in `maker_fills_recent.log`. The log's 7d window (starting Jul 15) contains zero band-maker registrations. This is structurally expected: `band_posted_state.json` shows last posting activity on **2026-07-06** (spent=$48.01); no band tokens have been posted since.

Fill rate: undefined (posted tokens since Jul 6 = 0; denominator = 0).

### UPDOWN sniper fills (UNTRACKED — out of band-maker scope)

All fill events in the log are `[USER-WS] UNTRACKED FILL` from `strategy.weather_arb`. Counted as unique CONFIRMED status events:

| Day | Fills (n) | Trader-side: TAKER | Trader-side: MAKER | Notes |
|---|---|---|---|---|
| Jul 15 | 17 | 15 | 2 | TAKER BUY @ 0.87–0.98; MAKER BUY @ 0.02 |
| Jul 16 | 23 | 18 | 5 | TAKER BUY/SELL @ 0.95–0.999; MAKER BUY @ 0.02–0.09; MAKER SELL @ 0.96–0.98 |
| Jul 17 | 14 | 10 | 4 | TAKER BUY @ 0.89–0.98; MAKER BUY @ 0.02–0.06 |
| Jul 18 (partial, to 07:09) | 4 | 2 | 2 | TAKER BUY @ 0.97; MAKER BUY @ 0.08, SELL @ 0.92 |
| **7d total** | **58** | **45** | **13** | |
| **24h total** | **15** | **12** | **3** | |

Price band distribution (sniper, 7d): all 45 TAKER fills at >0.85 (YES near resolution); all 13 MAKER fills at <0.10 (low-price entries / NO legs). Zero fills in 0.10–0.85 band.

Entry/exit pattern observed: TAKER BUY at 0.87–0.99 followed by TAKER SELL at 0.99–0.999 within 1–3 minutes on the same token (confirmed pairs on Jul 16 token 6582394037728816: BUY@0.98→SELL@0.999 in 2 min; Jul 17 token 1127887226699687: BUY@0.94→SELL@0.99 in 2 min).

Time-to-fill on band maker: cannot compute (0 posts since Jul 6, no `band_struct` post timestamps to join).

---

## Section 2 — NO-Parity Monitor

**Status: Vacuous — BAND_NO_ENABLED=False, zero posts in audit window.**

| Date | New posts (YES) | New posts (NO) | NO share | >=10 posts? |
|---|---|---|---|---|
| 2026-07-15 | 0 | 0 | — | No |
| 2026-07-16 | 0 | 0 | — | No |
| 2026-07-17 | 0 | 0 | — | No |
| 2026-07-18 (partial) | 0 | 0 | — | No |

`band_struct_lite.jsonl` for Jul 15–18 shows **zero NO records** across all dates. All band activity is shadow-only (`live: false`). YES capture shadow records exist (51–64/day) but are shadow-mode evaluations that do not result in live orders.

Resting book by side (`maker_resting_state.json = {}`): 0 YES orders, 0 NO orders.

NO-starvation bug fix (2026-06-12 commit `fix(BAND): NO-starvation`): holds vacuously. No posts of any side to stave.

**Alert: NO share < 25% with ≥10 posts → NOT FIRED** (0 posts on all days).

---

## Section 3 — Queue Health

**Status: Vacuous — zero [STRUCT-BAND-Q] lines in log, resting book empty.**

No `[STRUCT-BAND-Q]` lines appear in `maker_fills_recent.log`. The band posting engine has not fired a live cycle since BAND_LIVE was set False on Jul 6.

`maker_resting_state.json = {}` — 0 resting orders.

### Shadow engine activity (what would fire if BAND_LIVE=True)

Derived from `band_struct_lite.jsonl` (shadow evaluation, `live=false`):

| Date | Shadow fires | Sum-gate | Converged | No-band | YES cap. shadows |
|---|---|---|---|---|---|
| 2026-07-15 | 15 (d0=0, d1=6, d2=9) | 29 | 22 | 44 | 64 |
| 2026-07-16 | 14 (d0=1, d1=5, d2=8) | 29 | 18 | 42 | 60 |
| 2026-07-17 | 19 (d0=4, d1=6, d2=9) | 29 | 23 | 39 | 51 |
| 2026-07-18 (to 07:09) | ~9 (d0=3, d1=0, d2=6) | ~10 | ~4 | ~6 | many |

**Structural observation:** d+1 is **entirely sum-gated every day** (all 10 BAND_CITY_ALLOW cities hit `sum_ask ≥ BAND_SUM_MAX=0.85`; d+1 market consensus is highly efficient, leaving no positive-EV band gap). d+2 is the primary viable horizon (5–9 cities fire daily in shadow). d+0 is dominated by `converged` (mode has resolved visually) and `no_band` (too few interior valid legs).

**Alerts: NOT FIRED** — books pinned at 80 and cash_preskip > 200 are untestable (no `[STRUCT-BAND-Q]` data).

---

## Section 4 — Resolution Markout (Fill Quality)

**Status: Cannot compute — 0 band [MAKER-FILL] fills to join against resolutions.**

`maker_fills_recent.log` contains zero `[MAKER-FILL]` entries. There are no filled band legs whose outcome can be compared to the all-fires simulated ROI. `band_resolution_join.py` would receive an empty fill input.

n = 0 (below 40-fill threshold; no conclusions possible per audit ground rules).

Winner's curse assessment: **deferred — insufficient data.**

Last band-maker fills on record: prior to Jul 6 (not in the 7d log window). Earlier fill quality data from `band_posted_state.json` shows the last significant posting day was Jun 22–Jun 25 at the $114–$235 scale; those resolutions would require the older logs to assess markout.

---

## Section 5 — Dead-Quote Reclaim

**Status: Nothing to reclaim — resting book is empty.**

| Metric | Value |
|---|---|
| Resting orders (maker_resting_state.json) | **0** |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |
| "reaped dead entry" lines in log (7d) | 0 |
| $ freed by reclaim | $0 |

`maker_resting_state.json = {}`. No orders were placed after Jul 6 to accumulate stale age.

`BAND_RECLAIM_AGE_S = 2h` (config), `BAND_PAIR_RECLAIM_AGE_S = 8h` — both thresholds are armed but have no resting quotes to evaluate.

**Alert: >20 quotes older than 48h → NOT FIRED** (0 resting).

---

## Section 6 — Cash Velocity

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll.json) | $37.57 | — |
| Resting $ (band maker) | $0.00 | — |
| Band fills $ last 24h | $0.00 | — |
| Band turns/day | **0.0** | ~1.0 (badatmath) |

Capital note: $37.57 is the tracker value; manual sells are not reflected here. Total PnL per tracker: -$75.40.

UPDOWN sniper (out of scope, for context): 15 fill events in 24h; notional deployed ~$149 (TAKER BUY entries at 0.89–0.98 × 14.75–19.5 shares); proceeds from exits ~$25 (2 TAKER SELL events at 0.99). Not attributable to band-maker execution.

---

## ALERTS

**No pre-registered alerts fired.**

| Alert condition | Threshold | Observed | Fired? |
|---|---|---|---|
| NO share < 25% with ≥10 posts | Any day ≥10 posts | 0 posts | No |
| books used pinned at 80 | Most cycles | No [STRUCT-BAND-Q] data | No |
| yes_books pinned at 50 | Most cycles | No [STRUCT-BAND-Q] data | No |
| cash_preskip > 200, posted=0 all day | Sustained | No [STRUCT-BAND-Q] data | No |
| Quotes > 48h old (>20) | >20 | 0 resting | No |

All alert conditions are either non-triggering or untestable (the [STRUCT-BAND-Q] alerts require live band posting cycles which have not occurred since Jul 6).

---

## Summary (3 lines)

**Fills/day:** 0 band [MAKER-FILL] fills (band wound down since Jul 6); 14–17 UPDOWN sniper fills/day visible in log (UNTRACKED, out of scope for this audit).

**NO-share:** 0% (vacuous) — BAND_NO_ENABLED=False since Jul 2, BAND_LIVE=False since Jul 6; no posts of either side in the audit window.

**Binding execution constraint:** `BAND_LIVE=False` is the single gate blocking all band activity. Shadow engine shows d+2 viable (5–9 cities/day pass gates), d+1 sum-gated every day (Σask ≥ 0.85, no re-entry without market regime change), d+0 mostly converged. Zero capital deployed via band maker; zero markout data accumulating.
