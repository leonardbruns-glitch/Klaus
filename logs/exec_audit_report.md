# Klaus Band Execution & Markout Audit
**Date:** 2026-07-19  
**Snapshot:** 2026-07-19T07:09:12Z (age < 6h ✓)  
**System:** `klaus systemd: active` ✓  
**Capital:** $43.27 (bankroll.json; daily start $37.57 → +$5.70 day-to-date from sniper)  
**Trades total (all-time):** 8,227

---

## CONTEXT: Band Maker Status

**BAND_LIVE = False** (wound down 2026-07-06; equity $108.35 < 50% · 30d-HW $222.90 charter trigger)  
**BAND_NO_ENABLED = False** (rail-halt 2026-07-02; 7d realized WR 39.2%, n=51)  
**BAND_YES_LIVE_MIN_DOUT = 9** (standalone YES paused 2026-07-03; 9=never fires)  
**BAND_PAIR_FAV_ENABLED = True** (parameter set, but gated by BAND_LIVE=False)  
**MAKER_SHADOW_ENABLED = True** (shadow quoting active; not live)  
**BAND_SHADOW = True** (band shadow evaluation active; not live)

The band maker strategy has been fully wound down since 2026-07-06. Shadow loggers are healthy: `band_struct` 2,151 rows by 07:09, `maker_shadow` 27,544 rows, `thermo_maker` 5,564 rows — all consistent with normal shadow-mode rates. Active live strategy is UPDOWN sniper only; its fills appear in the log as `[USER-WS] UNTRACKED FILL` warnings outside the band tracker's scope and are noted where relevant.

---

## Section 1 — Fill Tape (24h + 7d)

### Band [MAKER-FILL] fills

| Window | Fills (n) | $ filled | By side | By price band |
|---|---|---|---|---|
| 24h (Jul 18 07:09 → Jul 19 07:09) | **0** | $0.00 | — | — |
| 7d (Jul 12 → Jul 19 07:09) | **0** | $0.00 | — | — |

No `[MAKER-FILL]` lines appear in `maker_fills_recent.log`. Structurally expected: `band_posted_state.json` last posting activity 2026-07-06 ($48.01 spent); no band tokens posted since. Fill rate: undefined (denominator = 0 posts).

### UNTRACKED fills visible in maker_fills_recent.log (out of band-maker scope)

Counted as MATCHED-status events only (each fill generates MATCHED → MINED → CONFIRMED; counted once). The 7d log window covers Jul 16–19 only (earlier dates not present).

| Day | Fills (n) | MAKER | TAKER | MAKER price range | TAKER price range |
|---|---|---|---|---|---|
| Jul 16 | 12 | 4 | 8 | 0.02–0.98 (3 BUY, 1 SELL) | 0.95–0.999 (7 BUY, 1 SELL) |
| Jul 17 | 14 | 5 | 9 | 0.02–0.06 (5 BUY; 2 split) | 0.89–0.99 (8 BUY, 1 SELL) |
| Jul 18 | 5 | 2 | 3 | 0.08 BUY, 0.92 SELL | 0.97–0.98 BUY |
| Jul 19 (to 07:09) | 4 | 1 | 3 | 0.02 BUY | 0.88–0.98 BUY |
| **7d total** | **35** | **12** | **23** | | |
| **24h total** | **5** | **1** | **4** | 0.02 BUY | 0.88–0.98 BUY |

**Price band breakdown (7d, all UNTRACKED):**
- <0.10: 10 fills (9 MAKER BUY at 0.02/0.06/0.08; 1 TAKER BUY at 0.02 — note: there's no TAKER in this range, all low-price buys are MAKER)
- 0.85–1.00: 25 fills (all TAKER near-resolution buys at 0.88–0.999 + MAKER SELLs at 0.92/0.96/0.98)
- 0.10–0.85: 0 fills

This bimodal pattern (extreme-low MAKER entries + near-resolution TAKER buys) is consistent with: legacy band resting orders at extreme YES prices still on CLOB (pre-wind-down, orphaned) + sniper strategy buying near resolution.

**Notable MAKER events (untracked, likely orphaned legacy CLOB orders):**

| Date | Token | Side | Price | Shares | Est. $ |
|---|---|---|---|---|---|
| Jul 16 21:39 | 1399483673820402 | SELL | 0.96 | 147.05 | **$141.17 proceeds** |
| Jul 17 13:34 | 4095117562509625 | BUY | 0.06 | 58.33 (split) | $3.50 cost |
| Jul 17 18:34 | 1055101008834022 | BUY | 0.02 | 150.00 | $3.00 cost |
| Jul 17 18:44 | 1046907088381323 | BUY | 0.02 | 78.00 | $1.56 cost |
| Jul 18 00:54 | 7094108612094851 | BUY | 0.08 | 44.88 | $3.59 cost |
| Jul 18 00:54 | 2664940529472113 | SELL | 0.92 | 9.32 | $8.57 proceeds |
| Jul 19 02:14 | 5717613767097074 | BUY | 0.02 | 146.33 | $2.93 cost |

The $141.17 SELL proceeds on Jul 16 (token 1399483673820402) is by far the largest single event. Research audit commit `b68f21d43` (Jul 18 10:11Z) already flagged both 1399483673820402 and 2664940529472113 as "G3 unfreeze" candidates needing classification. Total 7d untracked MAKER proceeds: ~$150.86; total 7d untracked MAKER cost: ~$15.78 — net positive from exits, but all without entry tracking context.

Time-to-fill on band maker: not computable (0 posts since Jul 6; no `band_struct` post-ts to join against).

---

## Section 2 — NO-Parity Monitor

**Status: Vacuous — BAND_NO_ENABLED=False, zero posts in audit window.**

| Date | New posts YES | New posts NO | NO share | ≥10 posts? |
|---|---|---|---|---|
| 2026-07-16 | 0 | 0 | — | No |
| 2026-07-17 | 0 | 0 | — | No |
| 2026-07-18 | 0 | 0 | — | No |
| 2026-07-19 (to 07:09) | 0 | 0 | — | No |

`band_posted_state.json`: last date key is 2026-07-06. Resting book (`maker_resting_state.json = {}`): 0 YES, 0 NO.

NO-starvation fix (commit `fix(BAND): NO-starvation` 2026-06-12): holds vacuously — no posts of either side since wind-down.

**Alert: NO share < 25% with ≥10 posts → NOT FIRED** (0 posts on all days).

---

## Section 3 — Queue Health

**Status: Vacuous — zero [STRUCT-BAND-Q] lines; resting book empty.**

No `[STRUCT-BAND-Q]` lines in `maker_fills_recent.log`. Band posting engine has not run a live cycle since Jul 6.

### Shadow engine activity (band_struct, shadow mode)

Shadow data from `shadow_summary.json` (row counts for today vs prior days):

| Date | band_struct rows | maker_shadow rows | thermo_maker rows | maker_flow rows |
|---|---|---|---|---|
| Jul 14 | 7,591 | 88,176 | 44,432 | 128,480 |
| Jul 15 | 7,733 | 107,855 | 42,243 | 269,769 |
| Jul 16 | 7,595 | 104,621 | 38,377 | 288,025 |
| Jul 17 | 7,629 | 99,693 | 33,569 | 287,318 |
| Jul 18 | 7,586 | 87,175 | 24,956 | 284,464 |
| Jul 19 (07h in) | 2,151 | 27,544 | 5,564 | 39,501 |

Jul 19 totals at 7/24 of day = 29% of day elapsed. Expected full-day rates: `band_struct` ~7,400, `maker_shadow` ~94K, `thermo_maker` ~19K (thermo rate appears depressed today vs prior days — 5,564/(7/24)×24≈19K vs 24K–44K range; monitor). All shadow loggers are running; no evidence of fetch starvation or deployment stall.

**Alerts: NOT FIRED** — `[STRUCT-BAND-Q]` data unavailable (BAND_LIVE=False); fetch starvation and cash_preskip alerts untestable.

---

## Section 4 — Resolution Markout (Fill Quality)

**Status: Cannot compute — 0 band [MAKER-FILL] fills to join against resolutions.**

n = 0. Below 40-fill threshold for any conclusions per ground rules.

`band_resolution_join.py` would receive an empty fill input; not run.

Winner's curse assessment: **deferred — insufficient data.**

The 12 untracked MAKER fills in the 7d window have no entry-context in the tracker (no condition_id, no entry_ts, no entry_price recorded). The large exits (1399483673820402 SELL@0.96, 2664940529472113 SELL@0.92) suggest these are resolving profitably, but without entry cost the actual ROI is unknown. Entry classification flagged by research audit for those two tokens.

---

## Section 5 — Dead-Quote Reclaim

**Status: Nothing to reclaim — resting book is empty.**

| Metric | Value |
|---|---|
| Resting orders (`maker_resting_state.json`) | **0** |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |
| "reaped dead entry" lines in log (7d) | 0 |
| $ freed by reclaim | $0 |

`maker_resting_state.json = {}`. No orders placed after Jul 6; no age to accumulate.

`BAND_RECLAIM_AGE_S = 2h`, `BAND_PAIR_RECLAIM_AGE_S = 8h` — armed but have no resting quotes to evaluate.

**Observed: 12 untracked MAKER fills in 7d suggest legacy CLOB orders (placed pre-Jul 6 wind-down) are still resting on the CLOB and occasionally matching.** These orders are invisible to the current tracker (not in `maker_resting_state`); the bot restarted 2026-07-17 22:05 UTC and did not re-register them. This is not a dead-quote reclaim alert per spec (pre-registered alert is for *tracked* quotes >48h), but it is a data integrity observation: fills are accruing with no entry context. The most recent untracked MAKER fill is 02:14 UTC Jul 19 (5717613767097074 BUY@0.02, 146.33 shares). Total orphaned MAKER fills since Jul 16: 12 events, ~$15.78 in costs, ~$150.86 in proceeds — net positive but unaccountable.

**Alert: >20 quotes older than 48h → NOT FIRED** (0 tracked resting orders).

---

## Section 6 — Cash Velocity

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll.json) | **$43.27** | — |
| Daily start capital | $37.57 | — |
| Resting $ (band maker) | $0.00 | — |
| Band fills $ last 24h | $0.00 | — |
| Band turns/day | **0.0** | ~1.0 (badatmath) |
| UPDOWN sniper turns/day (rough) | ~6+ | — |

Capital note (CAVEAT): bankroll.json reflects bot's internal tracker; user manual sells not reflected. Total PnL per tracker: -$75.40 cumulative.

UPDOWN sniper (out of scope, context only): 5 fill events in 24h — 4 TAKER BUY at 0.88–0.98 (entry, ~$82 notional deployed), 0 TAKER SELL exits visible in 24h window; 1 MAKER BUY at 0.02 (orphaned legacy). PnL ledger Jul 17 reported +$7.34 day at 6.37 turns (not from band; 100% from sniper).

---

## ALERTS

**No pre-registered alerts fired.**

| Alert condition | Threshold | Observed | Fired? |
|---|---|---|---|
| NO share < 25% with ≥10 posts | Any day ≥10 posts | 0 posts (vacuous) | **No** |
| books used pinned at 80 | Most cycles | No [STRUCT-BAND-Q] data | **No** |
| yes_books pinned at 50 | Most cycles | No [STRUCT-BAND-Q] data | **No** |
| cash_preskip > 200, posted=0 all day | Sustained | No [STRUCT-BAND-Q] data | **No** |
| Quotes > 48h old (>20) | >20 | 0 tracked resting orders | **No** |

All alert conditions are non-triggering or untestable (STRUCT-BAND-Q requires live band posting cycles which have not occurred since Jul 6). The untracked MAKER fills (orphaned legacy CLOB orders) are not covered by a pre-registered alert condition and are reported as an observation only.

---

## Summary (3 lines)

**Fills/day:** 0 registered [MAKER-FILL] band fills (day 13 of wind-down); 5 UNTRACKED fills in 24h window (1 MAKER orphan at 0.02 + 4 sniper TAKER at 0.88–0.98); 35 UNTRACKED in visible 7d window with 12 orphaned MAKER events (~$150.86 proceeds, $15.78 costs — untracked, no entry context).

**NO-share:** 0% vacuous — BAND_NO_ENABLED=False since Jul 2, BAND_LIVE=False since Jul 6; zero posts of either side in audit window.

**Binding execution constraint:** `BAND_LIVE=False` is the sole gate. Shadow engine healthy (band_struct, maker_shadow, thermo_maker all running at expected rates). d+1 is fully sum-gated every day (Σask ≥ 0.85); d+2 viable in shadow. All capital velocity currently comes from UPDOWN sniper exclusively; band maker contributes $0 fills and $0 turns.
