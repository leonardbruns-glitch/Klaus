# Band Execution & Markout Audit — 2026-07-12

**Snapshot**: `2026-07-12T10:54:09Z` (fresh, within 6h) | **System**: active (uptime from 2026-07-11T22:06Z)
**Capital**: $124.275284 (daily_start $165.730744; −$41.45 likely deployed today in open PAIR_FAV positions — CAVEAT applies)
**BAND_LIVE**: False (wind-down 2026-07-06; equity $108.35 < 50%·30d-HW $222.90; day 6 of dark)
**BAND_NO_ENABLED**: False (rail-halt 2026-07-02, WR 39.2% n=51; day 10)
**BAND_PAIR_FAV_ENABLED**: True (re-enabled per Jul 12 review, per Jul 11 EVOLVE intent)
**STWA_REGULAR_YES/NO_ENABLED**: False

---

## Section 1 — Fill Tape (24h + 7d)

### Klaus maker fills (band/maker tape)

| Window | [MAKER-FILL] lines | Fills | $ filled | By side | By price band |
|---|---|---|---|---|---|
| Last 24h | 0 | 0 | $0 | — | — |
| Last 7d | 0 | 0 | $0 | — | — |

Zero `[MAKER-FILL]` lines and zero `[STRUCT-BAND-Q]` lines in the 7-day journal tape. No Klaus-registered maker fills in any price band, city, or side. Consistent with BAND_LIVE=False since 2026-07-06 (day 6 of dark at snapshot). Last registered band posts: 2026-07-06 (10 tokens, $48.01 spent); no `band_posted_state.json` entries for Jul 07–12.

Fill rate: **0 fills / 0 live posts** (band dark — denominator is zero).

### UNTRACKED fills observed via WS (sprint_ladder / PAIR_FAV — NOT in band tape)

All fills in `maker_fills_recent.log` carry the `[USER-WS] UNTRACKED FILL — no tracker entry, no open position` tag. These are fills on the Klaus wallet registered by the WS but unknown to the band/maker tracker. Based on price ranges (0.35–0.52), sizes (10–68 shares), and behavior (taker sweeps + hold-to-resolution exits at 0.99+), these are sprint_ladder or PAIR_FAV trades managed by a different module.

Unique fill events by day (deduped to MATCHED status only):

| Date (UTC) | Event type | Token (short) | Side | Price | Shares | trader_side |
|---|---|---|---|---|---|---|
| Jul 10 01:30 | BUY | 4663735... | BUY | 0.370 | 47.77 | TAKER |
| Jul 10 02:30 | BUY | 1671958... | BUY | 0.420 | 17.70 | TAKER |
| Jul 10 03:40 | BUY | 1132101... | BUY | 0.500 | 31.25 | TAKER |
| Jul 10 08:40 | EXIT | 4663735... | SELL | 0.992 | 47.00 | TAKER |
| Jul 11 05:00 | BUY | 7867586... | BUY | 0.350 | 66.50 | TAKER |
| Jul 11 10:20 | EXIT | 7867586... | SELL | 0.998 | 66.00 | TAKER |
| Jul 11 11:40 | BUY | 8345106... | BUY | 0.520 | 15.49 | MAKER (×2) |
| Jul 11 11:40 | BUY | 3195317... | BUY | 0.470 | 68.26 | TAKER |
| Jul 11 16:21 | BUY | 3510955... | BUY | 0.440 | 49.50 | TAKER |
| Jul 12 02:00 | BUY (PAIR) | 7506477... | BUY | 0.400 | 42.97 | TAKER+MAKER |
| Jul 12 07:00 | BUY (PAIR) | 5472978... | BUY | ~0.473 | 47.24 | TAKER+MAKER |
| Jul 12 07:08 | SELL (PAIR leg) | 5472978... | SELL | 0.480 | 7.64 | MAKER |

**Jul 12 detail (from `user_ws.jsonl`)**: Two orders on Klaus wallet confirmed. Order 1 (02:00Z): BUY YES 42.97@0.40, fully filled (MATCHED) via taker sweeps + CLOB-paired fills — PAIR_FAV structure visible (NO buyer at 0.60 matched via pairing). Order 2 (07:00Z): BUY YES 51.31@0.48, partially filled 47.24 shares at avg ~$0.473 (swept YES sells at 0.47, filled as MAKER via NO buyer at 0.52 for 5.88 shares, filled as MAKER via YES seller at 0.48 for 7.64 shares); order cancelled at 07:08Z with 4.07 shares unmatched.

Jul 12 PAIR_FAV deployed capital: ~$17.19 + ~$22.36 = **~$39.55** (open, resting at resolution).

---

## Section 2 — NO-Parity Monitor

**Source**: `band_struct_lite.jsonl` per day (Jul 07–12); `maker_resting_state.json`.

| Date | YES posts | NO posts | PAIR_FAV posts | NO share | ≥10 posts? | ALERT? |
|---|---|---|---|---|---|---|
| 2026-07-07 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-08 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-09 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-10 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-11 | 0 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-12 | 0 | 0 | 0 | N/A | No | N/A (dark) |

Zero `post` records in `band_struct_lite.jsonl` for any day Jul 07–12. `maker_resting_state.json = {}`. Resting book: 0 YES, 0 NO, 0 PAIR.

**NO-starvation fix** (committed 2026-06-12) cannot be verified in the current dark window — no posts, no denominator. Last confirmed parity: Jul 01–06 at ~50% per Jul 11 audit. No regression evidence, no confirming data.

Shadow band (md_shadow records, no live execution) Jul 12 scan breakdown (120 records, partial day to 10:54Z):

| Reason | Count | Meaning |
|---|---|---|
| yes_capture_shadow | 62 | Shadow would post YES leg |
| no_band | 28 | No valid band found |
| sum_gate | 20 | Σ ask ≥ BAND_SUM_MAX (0.85) |
| converged | 14 | Price converged, no edge |
| **fire** | **13** | **Full shadow band would post if BAND_LIVE=True** |

13 `fire` events on Jul 12 (vs 16 on Jul 07) — shadow scanner finding valid opportunities at normal cadence. All blocked by BAND_LIVE=False. d+2 dominates (87/120 records), consistent with BAND_NO_MIN_DOUT=1 / BAND_MD_HORIZON=2.

---

## Section 3 — Queue Health

**Source**: `[STRUCT-BAND-Q]` lines in `maker_fills_recent.log`; `band_struct_lite.jsonl` shadow scan rates.

| Metric | Value | Notes |
|---|---|---|
| [STRUCT-BAND-Q] lines in 7d tape | **0** | No live posting cycles since BAND_LIVE=False |
| Mean cash_preskip | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| Mean books used (x/80) | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| Mean yes_books (x/50) | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| Posted/cycle | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| Books pinned at 80? | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| yes_books pinned at 50? | Cannot evaluate | No [STRUCT-BAND-Q] lines |
| cash_preskip > 200, posted=0? | Cannot formally evaluate | $124.28 all-cash, $0 band-deployed |
| Shadow fire rate (Jul 12 partial) | **13 fire / 120 shadow scans** | Normal cadence |
| Shadow fire rate (Jul 07) | **16 fire / 175 shadow scans** | Comparable |

Queue health metrics are inaccessible without live posting cycles. The deployment stall condition (BAND_LIVE=False, all capital in CLOB cash, 0 band orders) is structural — a deliberate wind-down, not a fetch-starvation regression. Shadow machinery is fully functional: scan rate and fire-event rate are consistent across Jul 07 and Jul 12.

No `exit099_live.jsonl` entries in hot shadow dirs for Jul 07–12: confirms 0 live positions at the 0.99+ exit threshold.

---

## Section 4 — Resolution Markout (Fill Quality)

**Source**: Jul 11 EVOLVE commit `491d8a2d4`; prior exec audit findings (Jul 11); `band_posted_state.json` last live dates.

### Registered band fills in tape: none
Zero `[MAKER-FILL]` lines in 7d window. No per-leg fill/resolution pairs exist for formal markout computation. `band_resolution_join.py` requires live fill records — unavailable.

### Prior markout finding (carries from Jul 11 audit, n=75 trend)
From Jul 11 EVOLVE commit: *"winner's curse RESOLVED (realized -75.8% vs sim +7.6%, n=75 trend)"*

| Metric | Value | Grade |
|---|---|---|
| Realized ROI (filled band legs, Jul 11 data) | **−75.8%** | n=75, trend (40–99) |
| Simulated all-fires ROI (same period) | **+7.6%** | n=75, trend |
| Gap | **−83.4pp** | adverse-selection direction |
| Status | **Acknowledged in EVOLVE; unresolved by data** | Band dark prevents accumulation |

"RESOLVED" in the EVOLVE commit means acknowledged and documented, not corrected — no mechanism has been deployed to address adverse selection, and the band remains dark so no new data can accumulate to confirm or deny. The gap at n=75 is PLAUSIBLE (trend-grade), not decision-grade (n≥100 required).

**WINNER'S-CURSE DIRECTION**: Resting bids are getting hit selectively when the market moves against the quote. This is the same pattern that killed the prior Maker MVP. The gap is large enough at n=75 to warrant ongoing monitoring; cannot be dismissed as noise.

### Untracked ladder/PAIR_FAV markout (observation only)
Visible ladder exits in the 7d WS tape: Jul 10 SELL 47@0.992 (entry 0.37 → +168% raw), Jul 11 SELL 66@0.998 (entry 0.35 → +185% raw). These are TAKER ladder trades, not maker bids — they are NOT subject to adverse selection because they are directional entries. No winner's curse concern for this leg.

---

## Section 5 — Dead-Quote Reclaim

**Source**: `maker_resting_state.json`; "reaped dead entry" lines in `maker_fills_recent.log`.

| Metric | Value |
|---|---|
| Resting quotes | **0** |
| "reaped dead entry" lines in 7d tape | **0** |
| Quotes older than 24h | **0** |
| Quotes older than 48h | **0** |
| $ freed by reclaim in 7d | **$0** |

`maker_resting_state.json = {}`. All prior quotes (last batch: Jul 06, 10 tokens, $48.01) have cleared via weather market resolution. No velocity leak. `BAND_RECLAIM_AGE_S = 2h` reclaim does not run when `BAND_LIVE=False` — immaterial given empty resting state.

---

## Section 6 — Cash Velocity

**Source**: `bankroll.json`; `maker_resting_state.json`; fill tape; `user_ws.jsonl`.

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll.json) | **$124.275284** | CAVEAT: manual ladder/PAIR_FAV not tracked here |
| Daily start capital (Jul 12) | **$165.730744** | — |
| Daily deployed (PAIR_FAV, today) | **~$39.55** (open, unresolved) | — |
| Resting $ (band maker) | **$0.00** | — |
| Band maker fills 24h | **$0** | — |
| Band maker fills 7d | **$0** | — |
| Band equity turns/day | **0.0** | badatmath ≈1.0 |
| PAIR_FAV turns/day (untracked) | **~0.24** ($39.55/$165.73) | — |
| Total effective turns/day | **~0.24** | badatmath ≈1.0 |

Klaus's band maker velocity is 0.0 turns/day (day 6 of dark). PAIR_FAV is active and deployed ~$39.55 today (2 transactions confirmed via `user_ws.jsonl`), but these are UNTRACKED by the band/maker tape. Effective total velocity ~0.24 turns/day vs badatmath's ~1.0 benchmark. Capital efficiency is suppressed by the band-dark constraint and by PAIR_FAV being the sole active channel.

All capital above the ~$39.55 deployment ($124.28 - $39.55 ≈ $84.73) is idle in CLOB cash, generating no maker rebates.

---

## ALERTS

### ⚠ ALERT 1 — BAND DARK DAY 6
**BAND_LIVE=False** since 2026-07-06. Zero maker posts Jul 07–12. Shadow scanner healthy and finding **13 fire events** on Jul 12 (normal cadence, opportunities present). The band is dark by deliberate design (equity wind-down: $108.35 < 50%·30d-HW $222.90 at trigger; current $124.28 still below threshold). Per Jul 11 EVOLVE: "micro-stake PAIR_FAV re-enable at Jul 12 review" was the planned action — PAIR_FAV_ENABLED is now True and producing trades, but the standalone YES/NO band engine remains dark. No automated re-enable path exists for BAND_LIVE; requires explicit user decision.

### ⚠ ALERT 2 — WINNER'S CURSE TREND (n=75, carries from Jul 11)
Realized band-leg ROI **−75.8%** vs simulated all-fires **+7.6%** (n=75, 40–99 = trend only). Gap is **−83.4pp** in the adverse-selection direction. Acknowledged in Jul 11 EVOLVE as "RESOLVED" (meaning documented, not corrected). Band dark prevents accumulation of new data to update n. Alert carries over. A formal per-leg split at (city, days_out, price_band) slice level requires `band_resolution_join.py` output cross-tabulated against the fill tape — not achievable from this audit's data scope. Re-enable decision at Jul 12 weekly must address this before going live.

---

## 3-Line Summary

**Fills/day**: 0 (band dark day 6; BAND_LIVE=False since Jul 06; shadow finding 13 fire events today but all blocked; PAIR_FAV active via separate module, ~$39.55 deployed today, untracked in band tape).

**NO-share**: N/A (0 posts Jul 07–12; BAND_NO_ENABLED=False day 10; NO-starvation fix unverifiable in dark window; last confirmed ~50% parity Jul 01–06).

**Binding execution constraint**: BAND_LIVE=False wind-down gate (equity $124.28 vs HW; user Jul 12 review is the re-enable decision point) + winner's-curse trend (n=75, −83pp gap) unresolved by data — band should not go live without addressing adverse-selection before accumulating more fill inventory.
