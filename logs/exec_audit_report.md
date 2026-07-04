# Klaus Band Execution & Markout Audit
**Date:** 2026-07-04T07:00Z  
**Snapshot:** 2026-07-04T07:00:09Z (fresh, <6h)  
**System:** active | HEAD aff5c01ec | Capital: $40.96  
**Engine posture:** PAIR_FAV only (BAND_NO halted 2026-07-02, standalone YES paused 2026-07-03)

---

## Section 1 — Fill Tape (24h + 7d)

**7-day window:** Jul 01–Jul 04 07:00 UTC  
**Total fills:** 30 (from `maker_fills_recent.log`)  
**Fill rate:** ~10/day avg (Jul 01: 11, Jul 02: 13, Jul 03: 6, Jul 04: 0 so far)

| Day | YES fills | NO fills | Total |
|-----|-----------|----------|-------|
| Jul 01 | 0 | 11 | 11 |
| Jul 02 | 1 | 12 | 13 |
| Jul 03 | 6 | 0 | 6 |
| Jul 04 | 0 | 0 | 0 |
| **Total** | **7** | **23** | **30** |

**Notional filled (est.):** ~$3/fill avg × 30 = ~$90 gross (rough; exact sizes not in fill-tape format)  
**YES fills:** Jul 02-03 only (PAIR_FAV YES legs after BAND_NO halt)  
**NO fills:** Jul 01-02 dominant (BAND_NO active + pair_fav NO legs)  
**Median time-to-fill:** not recoverable from log format (no queue-entry timestamps in fill lines)

---

## Section 2 — NO-Parity Monitor

| Day | YES posts | NO posts | Total | NO share | Status |
|-----|-----------|----------|-------|----------|--------|
| Jul 01 | <50% | >50% | ~20 | >50% | OK (BAND_NO dominant) |
| Jul 02 | mixed | mixed | ~10 | ~50% | OK (transition day) |
| **Jul 03** | **107** | **31** | **138** | **22.5%** | **ALERT** |
| Jul 04 | 1 | 1 | 2 | 50% | OK |

**ALERT FIRED — Jul 03 NO share = 22.5% (threshold: <25% on days with ≥10 posts)**

Root cause: one-time transition artifact. On Jul 03, standalone YES band posted 77 d+2 YES legs (Munich d+2 dominated) while BAND_NO was already halted from Jul 02 and BAND_YES_LIVE_MIN_DOUT=9 had not yet fully taken effect. Post-transition (Jul 04+): structurally fixed at 50% via pair_fav. No ongoing NO-starvation regression.

---

## Section 3 — Queue Health (STRUCT-BAND-Q)

**698 STRUCT-BAND-Q lines** parsed from `maker_fills_recent.log`.

| Metric | Observed | Alert threshold | Status |
|--------|----------|-----------------|--------|
| books | 2–12 (variable) | Pinned at 80 | OK |
| yes_books | 1–6 (variable) | Pinned at 50 | OK |
| cash_preskip | 0 most cycles | >200 sustained with posted=0 | OK |
| posted/cycle | 0–1 (low but expected) | — | OK |

No starvation signals. Low posted/cycle is architectural: PAIR_FAV only fires when both YES+NO legs pass sum_gate (sum_ask < 0.90). Jul 04 band_struct_lite shows frequent `sum_gate` rejections for d+1 cities (sum_ask ≥ 0.85), which explains zero posts today. Not a bug — correct gate behavior.

---

## Section 4 — Resolution Markout (Winner's Curse Test)

**n = 21 fills** with recoverable fill price (partial — full size not in log format)  
**Decision threshold: n ≥ 40. Current n = 21. Status: INCONCLUSIVE — data collection phase.**

Filled-vs-all-fires ROI comparison not computable at this n. No winner's curse conclusion warranted.

**exit099 recycle outcomes (proxy for directional markout):**

| Day | Recycles | Total PnL | Avg PnL/trade |
|-----|----------|-----------|---------------|
| Jul 01 | 8 | $11.90 | $1.49 |
| Jul 02 | 7 | $18.43 | $2.63 |
| Jul 03 | 4 | $10.42 | $2.61 |
| **3-day total** | **19** | **$40.75** | **$2.14** |

All 19 exit099 recycled positions profitable (market moved further into filled direction in every case). Suggestive directional signal but not a formal winner's curse test — revisit at n ≥ 40 fills.

---

## Section 5 — Dead-Quote Reclaim

**Reaped dead entry lines in maker_fills_recent.log:** 0  
**Reclaim trigger:** BAND_RECLAIM_AGE_S = 2h (entry bids); BAND_PAIR_RECLAIM_AGE_S = 8h (pair legs)

**Current resting orders (maker_resting_state.json):** 5 orders, all SELL_EXIT at $0.99

| Position | Side | Size | Age (est.) | Type |
|----------|------|------|------------|------|
| Munich YES (Jul 02) | SELL | 9.0 | ~48h | exit099 resting |
| Munich YES (Jul 03) | SELL | 9.0 | ~24h | exit099 resting |
| Tokyo YES (Jul 03) | SELL | 9.0 | ~24h | exit099 resting |
| Munich YES (Jul 03) | SELL | 9.0 | ~18h | exit099 resting |
| Tokyo YES (Jul 03) | SELL | 9.0 | <24h | exit099 resting |

Oldest resting SELL_EXIT: ~48h (Munich YES Jul 02). These are intentional exit-at-0.99 holds, not dead entry bids. No reclaim trigger applies.

**No dead-quote reclaim alerts.**

---

## Section 6 — Cash Velocity

| Metric | Value |
|--------|-------|
| Capital | $40.96 |
| Fills $ last 24h | $0 (Jul 04 fills = 0 so far) |
| Fills $ last 7d | ~$90 gross est. (30 fills) |
| Turns/day (est.) | ~$12.86/day ÷ $40.96 = **0.31 t/day** |
| badatmath benchmark | ~1.0 t/day |

Cash velocity: 0.31 t/day vs 1.0 benchmark (31% of target). Binding constraint: PAIR_FAV-only posture. BAND_NO halted + standalone YES paused leaves only pair completion (both legs must clear sum_gate simultaneously). d+1 sum_gate rejections on Jul 04 show the gate is catching most opportunities. Velocity recovers when BAND_NO or standalone YES re-enable.

---

## ALERTS

### ALERT: NO-PARITY — Jul 03 NO share = 22.5% (threshold <25%, n=138)
Pre-registered alert condition: YES. Alert fires.  
Assessment: Transition artifact. BAND_NO halted Jul 02; standalone YES still running d+2 posts Jul 03 morning before BAND_YES_LIVE_MIN_DOUT=9 took effect. Jul 04 back to 50%. No code change required.

---

## Summary

- **Fills:** avg 10/day (Jul 1–3); 0 today (Jul 04, sum_gate rejecting d+1 opportunities). All 19 exit099 recycles profitable ($40.75 total, $2.14/trade avg). Resolution markout INCONCLUSIVE (n=21 < 40 decision threshold).
- **NO share:** 22.5% Jul 03 (ALERT — one-time transition artifact, structurally fixed at 50% on Jul 04+ via PAIR_FAV only).
- **Binding execution constraint:** PAIR_FAV-only posture (BAND_NO halted, standalone YES paused) caps velocity at ~0.31 t/day vs 1.0 benchmark; recovery requires re-enabling at least one additional engine.
