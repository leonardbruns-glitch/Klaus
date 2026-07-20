# Klaus Band Execution & Markout Audit
**Date:** 2026-07-20
**Snapshot:** 2026-07-20T07:07:38Z (age < 6h ✓)
**System:** `klaus systemd: active` ✓
**Capital:** $21.495 (bankroll.json — CAVEAT: includes manual sells; do not read as bot-only P&L)
**Open positions:** 0 | **Resting orders:** 0

---

## CONTEXT: Band Maker Status

**BAND_LIVE = False** (wound down 2026-07-06; equity $108.35 < 50%·30d-HW $222.90 charter trigger)
**BAND_NO_ENABLED = False** (rail-halt 2026-07-02; 7d realized WR 39.2%, n=51)
**BAND_YES_LIVE_MIN_DOUT = 9** (standalone YES paused 2026-07-03; 9=never fires)
**BAND_PAIR_FAV_ENABLED = True** (parameter set, gated by BAND_LIVE=False)
**MAKER_SHADOW_ENABLED = True** (shadow quoting active; no execution)
**BAND_SHADOW = True** (band shadow evaluation active; no execution)

The band maker strategy has been fully wound down since 2026-07-06. Shadow engine is running
and healthy — band_struct_lite for 2026-07-20 shows `"live": false` fire records firing
normally across all 10 cities through 07:07Z. Active live strategy is UPDOWN sniper only.

---

## Section 1 — Fill Tape (24h + 7d)

### Band [MAKER-FILL] fills

| Window | Fills (n) | $ filled | By side | By price band |
|---|---|---|---|---|
| 24h (Jul 19 07:07 → Jul 20 07:07) | **0** | $0.00 | — | — |
| 7d (Jul 13 → Jul 20 07:07) | **0** | $0.00 | — | — |

Zero `[MAKER-FILL]` lines in `maker_fills_recent.log`. Structurally expected: last band
post date in `band_posted_state.json` is 2026-07-06. Fill rate: undefined (0 posts since
wind-down).

### Untracked fills (out of band-maker scope — user manual / UPDOWN sniper)

Counted MATCHED-status only (each event triplicated to MATCHED/MINED/CONFIRMED; counted once).
Log covers Jul 17–19 UTC (earlier days absent from this mirror).

| Day | Fills (n) | MAKER | TAKER | Notable |
|---|---|---|---|---|
| Jul 17 | 11 | 5 | 6 | MAKER at 0.02–0.06 (150+78+33+25 sh); TAKER at 0.94–0.99 |
| Jul 18 | 5 | 2 | 3 | MAKER BUY@0.08 (44.9 sh) + SELL@0.92 (9.32 sh); TAKER at 0.97–0.98 |
| Jul 19 | 7 | 1 | 6 | MAKER BUY@0.02 (146.33 sh); TAKER at 0.88–0.98 |
| **7d total** | **23** | **8** | **15** | |
| **24h total** | **7** | **1** | **6** | Jul 19 only |

All untracked — no tracker entry, no open position in bot scope.
Price band breakdown (7d): <0.10: 7 MAKER fills; 0.10–0.85: 0; >0.85: 16 TAKER fills.
Bimodal pattern consistent with orphaned legacy CLOB resting orders at extreme-low YES prices
(pre-wind-down residuals being swept) + UPDOWN sniper buying at near-resolution prices.

Time-to-fill on band maker: **not computable** (0 posts since Jul 6; no post-ts to join).

---

## Section 2 — NO-Parity Monitor

**Status: Vacuous — BAND_NO_ENABLED=False, zero posts in all audit days.**

| Date | New YES posts | New NO posts | NO share | ≥10 posts? | Alert? |
|---|---|---|---|---|---|
| 2026-07-17 | 0 | 0 | — | No | — |
| 2026-07-18 | 0 | 0 | — | No | — |
| 2026-07-19 | 0 | 0 | — | No | — |
| 2026-07-20 (to 07:07) | 0 | 0 | — | No | — |

`band_posted_state.json` last key: 2026-07-06. `maker_resting_state.json`: `{}` (0 YES, 0 NO).
NO-starvation fix (2026-06-12 commit `fix(BAND): NO-starvation`) holds vacuously — no posts of
either side since wind-down. Fix re-validation deferred until band goes live and ≥10 posts/day.

**Alert — NO share < 25% on any day with ≥10 posts: NOT FIRED** (0 posts on all days).

---

## Section 3 — Queue Health

**Status: Vacuous — zero [STRUCT-BAND-Q] lines; BAND_LIVE=False suppresses live cycles.**

No `[STRUCT-BAND-Q]` lines in `maker_fills_recent.log`. No cycle metrics (cash_preskip,
books_used, yes_books, posted/cycle) to report.

### Shadow engine activity observed (band_struct_lite 2026-07-20, 00:00–07:07Z)

| Approx time | Scope | Fires (live=false) | Sum-gate blocks | Notes |
|---|---|---|---|---|
| ~00:01Z | d+0/d+1, all cities | 1 | 9 d+1 blocked (sum_ask ≥ 0.85) | Wuhan d+1 fires: 4 legs, sum_ask=0.845 |
| ~01:13–01:47Z | d+0 spot rechecks | 1 | — | Beijing d+0: 3 legs, sum_ask=0.589 |
| ~04:13–04:55Z | d+2, all cities | 7 | 3 sum-gates | London, Munich, Seoul, Taipei, Chongqing, Tokyo, Shanghai fire |
| ~07:07Z | Taipei d+1 rescan | 0 | — | Converged (mode_ask=0.455) |

Shadow fires are structurally sound (n_legs=3–5, sum_ask=0.61–0.845, bell-shaped stake
weights). Engine is alive and would post if re-armed.

**Alert — books pinned at 80 or yes_books pinned at 50: NOT FIRED** (no queue data).
**Alert — cash_preskip >200 sustained with posted=0: NOT FIRED** (no queue data).

---

## Section 4 — Resolution Markout (Fill Quality / Winner's Curse)

**Status: Cannot compute — 0 band [MAKER-FILL] fills available.**

n = 0. Below the 40-fill threshold for any conclusions.

`band_resolution_join.py` not run — empty fill input.

Winner's curse assessment: **deferred indefinitely until band re-arms and fills accumulate.**
Last confirmed band fill data predates the 7d tape window (before 2026-07-06 wind-down).

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|---|---|
| `maker_resting_state.json` entries | **0** |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |
| "reaped dead entry" lines (7d log) | 0 |
| $ freed by reclaim | $0.00 |

Resting book is empty; nothing to reclaim. `BAND_RECLAIM_AGE_S=7200s` and
`BAND_PAIR_RECLAIM_AGE_S=28800s` are configured but have no quotes to evaluate.

**Alert — >20 quotes older than 48h: NOT FIRED** (0 resting quotes).

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $21.495 |
| Resting $ (Σ q_price × unmatched size) | $0.00 |
| Band fills $ last 24h | $0.00 |
| Turns/day (band) | 0.00 |
| Benchmark (badatmath ~1.0 turn/day) | — |

Capital has declined from $37.57 daily_start on Jul 19 to $21.50 — the EVOLVE weekly
report (2026-07-19) attributes this to a −$22.09 sniper loss at 50%-Kelly sizing and an
overall −82% week. Do not read the $21.50 figure as band-driven; band has generated $0 fills.

---

## ALERTS

*Pre-registered alerts that actually fired: **none**.*

| Alert condition | Status |
|---|---|
| NO share of new posts < 25% on any day with ≥10 posts | NOT FIRED (0 posts) |
| Books pinned at 80 / yes_books pinned at 50 most cycles | NOT FIRED (no queue data) |
| cash_preskip > 200 sustained, posted=0 all day | NOT FIRED (no queue data) |
| >20 quotes older than 48h | NOT FIRED (0 resting quotes) |
| Winner's curse: filled ROI << all-fires ROI at n≥40 | NOT FIRED (n=0 fills) |

---

## Summary

**Fills/day: 0** — band wound down 2026-07-06; zero registered fills in the 7d tape.
**NO-share: N/A** — 0 posts since 2026-07-02; parity fix holds vacuously, unverifiable.
**Binding execution constraint: BAND_LIVE=False** (charter equity-floor trigger); shadow engine
is healthy and structurally firing across all 10 cities, but no capital deployment until
charter conditions are met.
