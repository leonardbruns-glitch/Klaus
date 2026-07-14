# Band Execution & Markout Audit — 2026-07-14

**Snapshot**: `2026-07-14T06:57:07Z` (fresh if routine runs before 12:57Z UTC) | **System**: active (restart 2026-07-13T22:06:10Z)
**Capital**: $34.6929 (daily_start $34.7427; CAVEAT: manual sells not reflected — do not conclude PnL from this alone)
**BAND_LIVE**: False (wind-down 2026-07-06; equity $108.35 < 50%·30d-HW $222.90; day 8 of dark)
**BAND_NO_ENABLED**: False (rail-halt 2026-07-02, WR 39.2% n=51; day 12)
**BAND_PAIR_FAV_ENABLED**: True (gated by BAND_LIVE=False for live execution)
**STWA_REGULAR_YES/NO_ENABLED**: False
**Active live strategy**: UPDOWN-SNIPER (live since ~2026-07-13T10Z on owner floor waiver; sniper fills now dominate the tape)

---

## Section 1 — Fill Tape (24h + 7d)

### Band maker fills (registered via [MAKER-FILL])

| Window | [MAKER-FILL] lines | [STRUCT-BAND-Q] lines | Klaus-registered fills | $ filled |
|---|---|---|---|---|
| Last 24h | **0** | **0** | 0 | $0 |
| Last 7d | **0** | **0** | 0 | $0 |

Zero `[MAKER-FILL]` or `[STRUCT-BAND-Q]` lines in the 7-day tape. BAND_LIVE=False since Jul 06 (day 8). All band maker pipeline metrics (fill count, fill rate, time-to-fill, city breakdown) are unavailable.

### UNTRACKED fills observed via user WS (all strategies — NOT band maker tape)

All entries in `maker_fills_recent.log` carry `[USER-WS] UNTRACKED FILL — no tracker entry, no open position`. These are fills on the Klaus wallet registered by the WS but unknown to the band/maker tracker.

**Character shift at Jul 13 10:49Z**: Pre-Jul 13 fills are large-lot (33–68 shares, prices 0.40–0.52), consistent with residual PAIR_FAV/BAND runoff. Jul 13 10:49Z onwards: small-lot (~5–6 shares, prices 0.92–0.99, $5–6 notional) = UPDOWN-SNIPER taker orders.

**24h window (Jul 13 ~10:49Z to Jul 14 ~07:00Z) — UPDOWN-SNIPER only:**

| Time (UTC) | Token (short) | Side | Price | Shares | Notional | trader_side | Notes |
|---|---|---|---|---|---|---|---|
| Jul 13 10:49 | 7664067… | BUY | 0.990 | 39.39 | $38.99 | TAKER | Entry |
| Jul 13 10:49 | 7664067… | SELL | 0.920 | 39.25 | $36.11 | TAKER | Early exit −7.1% |
| Jul 13 12:29 | 7678294… | BUY | 0.960 | 5.50 | $5.28 | TAKER | Entry (exit not in tape) |
| Jul 13 12:34 | 9373565… | BUY | 0.030 | 35.17 | $1.06 | MAKER | NO certainty cell |
| Jul 13 12:35 | 4306971… | SELL | 0.990 | 5.50 | $5.45 | TAKER | Resolution exit (+) |
| Jul 13 16:49 | 6224974… | BUY | 0.970 | 5.50 | $5.34 | TAKER | Entry |
| Jul 13 16:49 | 6224974… | SELL | 0.730 | 5.40 | $3.94 | TAKER | Exit at **−24.7%** |
| Jul 13 20:13 | 7811631… | BUY | 0.970 | 6.00 | $5.82 | TAKER | Entry |
| Jul 13 20:13 | 7811631… | SELL | 0.960 | 6.00 | $5.76 | TAKER | Exit −1.0% |
| Jul 13 20:43 | 2634559… | BUY | 0.960 | 5.18 | $4.97 | TAKER | Entry |
| Jul 13 20:43 | 2634559… | SELL | 0.950 | 5.00 | $4.75 | TAKER | Exit −1.0% |
| Jul 13 22:09 | 2737864… | BUY | 0.970 | 5.50 | $5.34 | TAKER | Entry |
| Jul 13 22:09 | 2737864… | SELL | 0.950 | 5.40 | $5.13 | TAKER | Exit −2.1% |
| Jul 13 22:59 | 2611012… | BUY | 0.920 | 5.50 | $5.06 | TAKER | Entry |
| Jul 13 22:59 | 2611012… | SELL | 0.950 | 5.50 | $5.23 | TAKER | Exit +3.3% |
| Jul 14 02:14 | 3199513… | BUY | 0.040 | 40.00 | $1.60 | MAKER | NO certainty cell |
| Jul 14 02:15 | 1078405… | SELL | 0.990 | 5.00 | $4.95 | TAKER | Resolution exit (+) |
| Jul 14 04:29 | 6572132… | BUY | 0.980 | 5.50 | $5.39 | TAKER | Entry |
| Jul 14 04:29 | 6572132… | SELL | 0.990 | 5.50 | $5.45 | TAKER | Exit +1.0% |

**24h counts:** 12 unique token events (19 fill records deduped); 9 BUY / 10 SELL; 2 MAKER-side (NO certainty cells at 0.03–0.04); buy notional ~$78.9, sell notional ~$76.8.

**By price band (24h):**

| Band | Fill count | Notional | Notes |
|---|---|---|---|
| <0.10 | 2 | $2.66 | MAKER — NO certainty cells |
| 0.10–0.30 | 0 | $0 | — |
| 0.30–0.50 | 0 | $0 | — |
| 0.50–0.85 | 0 | $0 | — |
| >0.85 | 17 | $152.99 | UPDOWN-SNIPER YES entries/exits |

**7d window (Jul 11–14):** Additional large-lot fills Jul 11–12 (PAIR_FAV runoff): SELL 0.998×66 ($65.87), BUY 0.47×68.26 ($32.08), BUY 0.44×49.50 ($21.78), BUY 0.52×15.49 ($8.05 MAKER), BUY 0.52×31 ($16.12), BUY 0.47×33.72 ($15.85), plus mixed 0.40-range pair fills ~$52. Jul 13 pre-sniper: BUY 0.449×51.5 ($23.12), BUY 0.526×45 ($23.67). 7d total: ~25–28 token events, ~$390–430 notional.

---

## Section 2 — NO-Parity Monitor

**Source**: `band_struct_lite.jsonl` daily dirs Jul 09–14; `maker_resting_state.json`; `band_config.txt`.

**Live posts by side:**

| Date | YES live | NO live | Total live | NO share | ≥10 posts? | ALERT? |
|---|---|---|---|---|---|---|
| 2026-07-09 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-10 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-11 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-12 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-13 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-14 | 0 | 0 | 0 | N/A | No | N/A (dark) |

`maker_resting_state.json = {}`. Zero resting orders. Alert threshold (NO share <25% on days ≥10 live posts) cannot fire.

**Shadow scan summary (`fire` records only):**

| Date | YES shadow fires | NO shadow fires | live=True fires | Notes |
|---|---|---|---|---|
| 2026-07-13 | 11 | 0 | 0 | all shadow; BAND_NO_ENABLED=False |
| 2026-07-14 (to ~07Z) | 7 | 0 | 0 | d+2 fires: Munich, Seoul, Shanghai, Taipei, Beijing, Tokyo; d+1: Munich |

NO-starvation fix (2026-06-12) is unverifiable in the dark window — no live-post denominator. Last confirmed ~50% parity: Jul 01–06.

**D+1 market scan (Jul 14)**: All 10 cities hit `sum_gate` for Jul 15 (Σask 0.89–1.014). The entire d+1 slate is blocked — markets for tomorrow's weather have converged inside band width. Only d+2 (Jul 16) shows viable shadow fire opportunities.

---

## Section 3 — Queue Health

**Source**: `[STRUCT-BAND-Q]` lines in fill tape; `maker_resting_state.json`.

| Metric | Value |
|---|---|
| [STRUCT-BAND-Q] lines in 7d tape | **0** |
| Live posting cycles | 0 |
| Mean cash_preskip | Cannot evaluate |
| Mean books used (x/80) | Cannot evaluate — books pinned alert also cannot evaluate |
| Mean yes_books (x/50) | Cannot evaluate — yes_books pinned alert also cannot evaluate |
| posted/cycle | Cannot evaluate |
| Resting orders | **0** |
| Band shadow scan cadence | Functional (5-min intervals, consistent fire events) |

No pre-registered alert conditions can be evaluated without `[STRUCT-BAND-Q]` data. Band engine is dark by design (BAND_LIVE=False), not a fetch-starvation regression. Shadow scanning continues normally.

---

## Section 4 — Resolution Markout (Fill Quality)

### Band maker fill markout
Cannot compute: zero `[MAKER-FILL]` entries. `band_resolution_join.py` requires a fill tape — unavailable.

**Prior finding carries from Jul 12 audit (n=75, trend):**

| Metric | Value |
|---|---|
| Realized ROI, filled band legs | −75.8% |
| Simulated all-fires ROI (same slice) | +7.6% |
| Gap (adverse selection) | **−83.4pp** |
| Status | Band dark since Jul 06 — no new observations accumulating |

The −83.4pp gap at n=75 is trend-grade (not decision-grade; need n≥100). Unresolved by any code change. BAND_LIVE=False prevents accumulation of new fill data to confirm or deny. This finding must be addressed before any BAND_LIVE re-enable.

### UPDOWN-SNIPER fill markout (observable round-trips, n=7)

n=7 — data collection phase. No conclusions per ground rules (n<40).

| Token (short) | Entry px | Exit px | Net/sh | Net $ | Result |
|---|---|---|---|---|---|
| 7664067… | 0.990 | 0.920 | −0.070 | −$2.75 | LOSS |
| 6224974… | 0.970 | 0.730 | −0.240 | −$1.30 | **LOSS (worst)** |
| 7811631… | 0.970 | 0.960 | −0.010 | −$0.06 | loss |
| 2634559… | 0.960 | 0.950 | −0.010 | −$0.05 | loss |
| 2737864… | 0.970 | 0.950 | −0.020 | −$0.11 | loss |
| 2611012… | 0.920 | 0.950 | +0.030 | +$0.17 | WIN |
| 6572132… | 0.980 | 0.990 | +0.010 | +$0.06 | win |

WR: **2/7 = 28.6%** (below 40% target; n<40 = trend only). Net from observable pairs: **−$4.04**.

Two additional resolution exits at 0.99 (tokens 4306971…, 1078405…) suggest some positions close profitably, but entry prices are not in this tape window.

**Markout observation (n<40, not conclusive):** The two worst exits (−7.1% and −24.7%) are positions where the market moved against the entry before the stop fired. Token 6224974… (entry 0.97, exit 0.73) is a −24.7% drawdown on a position that started at 97¢ certainty — consistent with the G3 watch item raised before go-live: *"filled ROI −75.8% vs sim +7.6%"*. The mechanism is the same: the sniper fills when a certainty signal is triggered, but the signal selects for adverse moves. Not confirmed at n=7; monitor through n=40.

Capital moved $39.40 → $34.69 = **−$4.71 (~24h since go-live)**. Consistent with observed round-trip losses above.

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|---|---|
| Resting quotes | **0** |
| "reaped dead entry" lines in 7d tape | **0** |
| Quotes >24h old | **0** |
| Quotes >48h old | **0** (alert threshold) |
| $ freed by reclaim (7d) | $0 |

`maker_resting_state.json = {}`. All prior BAND quotes (last batch Jul 06, 10 tokens, $48.01) have cleared via weather market resolution. No velocity leak. Alert (>20 quotes older than 48h) does not fire.

---

## Section 6 — Cash Velocity

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll.json) | **$34.69** | CAVEAT applies |
| Daily start capital (Jul 14) | $34.74 | — |
| Resting $ (band maker) | **$0** | — |
| Band maker fills 24h | **$0** | — |
| Band maker equity turns/day | **0.0** | badatmath ≈1.0 |
| UPDOWN-SNIPER buy volume 24h | ~$78.9 | — |
| UPDOWN-SNIPER equity turns/day | **~2.2** ($78.9 / ~$37 avg capital) | badatmath ≈1.0 |
| Observed ROI/turn (sniper, n=7 pairs) | **~−10.9%** (−$4.04 / $37) | badatmath +10–20%/turn |

Band maker is 0.0 turns/day (day 8 of dark). UPDOWN-SNIPER turns at ~2.2x/day — faster cadence than badatmath's benchmark — but at negative observed ROI on visible trades. Capital is not idle but return stream is negative in observable data (n<40; trend only).

---

## ALERTS

### ⚠ ALERT 1 — UPDOWN-SNIPER EARLY ADVERSE FILLS (n=7, data collection)

Observable round-trips: WR **2/7 (28.6%)**, net **−$4.04**, capital **−$4.71 in ~24h** since go-live. Worst exit: token 6224974…, entry 0.97, exit 0.73 (−24.7% on position). Five of seven visible round-trips are losses. This echoes the pre-live G3 watch item (filled ROI −75.8% vs sim +7.6%). n<40 = no conclusions; this is a data-collection observation. **The −$6/day day-stop has consumed $4.71 of $6 ($0.05 on Jul 14 so far); if the remaining 24h adds similar losses the day-stop fires.**

### ⚠ ALERT 2 — WINNER'S CURSE TREND (BAND, n=75, carries from Jul 12 audit)

Realized band-leg ROI **−75.8%** vs simulated all-fires **+7.6%** (n=75, trend). Gap: **−83.4pp** in adverse-selection direction. Band dark since Jul 06 — no new data accumulating. No corrective mechanism deployed. BAND_LIVE re-enable requires addressing this before accumulating new fill inventory.

---

### Alerts that DID NOT fire:
- NO-parity <25% on days ≥10 live posts: not evaluable (0 live posts)
- Books pinned at 80 (fetch starvation regression): not evaluable (no STRUCT-BAND-Q data)
- yes_books pinned at 50: not evaluable
- Dead-quotes >20 older than 48h: **does not fire** (0 resting quotes)
- Cash_preskip >200 sustained with posted=0: not formally evaluable (no queue data)

---

## 3-Line Summary

**Fills/day**: 0 band maker fills (dark day 8); ~12 UPDOWN-SNIPER token events in 24h (~$78.9 buy notional, all UNTRACKED by band tape); 7d tape also contains Jul 11–12 large-lot PAIR_FAV runoff fills (0.40–0.52 range, now cleared).

**NO-share**: N/A — 0 live band posts since Jul 06; BAND_NO_ENABLED=False since Jul 02; shadow scanner healthy, d+1 markets fully sum-gated (Jul 15), d+2 showing 7 shadow fires (Jul 16); NO-starvation fix unverifiable in dark window.

**Binding execution constraint**: UPDOWN-SNIPER is the sole active revenue engine (day 1 live); early observable data shows WR 2/7 and −$4.71 drawdown consuming 79% of the −$6/day day-stop rail, with adverse-exit pattern resembling the pre-live G3 winner's-curse watch item — the day-stop is the proximate risk gate today.
