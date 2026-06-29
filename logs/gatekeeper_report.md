# Gate-Keeper Ledger — 2026-06-29T09:13Z

**Snapshot:** 2026-06-29T09:05:26Z (age: 8 min ✓)  **System:** active ✓  
**Bankroll:** $80.98 | **Bot uptime since:** 2026-06-26T15:08:30Z (~66h continuous)  
**Prior run:** 2026-06-28T09:07Z

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 (ROI) | Status | ETA |
|---|---|---|---|---|---|---|---|
| BAND_YES | 5,999 | +21 | blocked | blocked | blocked (Gamma 403) | **COLLECTING** | ∞ (CI blocked) |
| BAND_NO + PAIR_FAV | 243 | +6 | blocked | blocked | blocked (Gamma 403) | **COLLECTING** | ∞ (CI blocked) |
| FILLED_VS_FIRED | 60 fills | +13 | blocked | blocked | blocked (Gamma 403) | **COLLECTING (>40 WATCH)** | ~3d to n=100 fills |
| BASKET_EXIT | VOID | — | — | — | — | **VOID** | — |
| THERMO_MAKER_NO | 3 | +0 | 33.3% | −66% | [−132.6%, +0.7%] | **COLLECTING** | ∞ (engine paused) |
| M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **AMBIGUOUS** | ∞ (stalled 17d) |
| SUM_POSTED 0.70–0.85 | 2,982 | +18 | blocked | blocked | blocked (Gamma 403) | **COLLECTING** | ∞ (CI blocked) |

---

## State Transitions vs Prior Run (2026-06-28T09:07Z)

None. All gates remain in prior status. No new READY or REJECTED verdicts.

### Changes in detail

**BAND_YES** (n 5,978 → 5,999, +21 legs):
- Fire source: 4 legs from Jun28 afternoon + 17 legs from Jun29 morning
- Regime: d+2 YES only, 5-city allowlist (Chengdu/London/Beijing/Munich/Wuhan), rate ≈19/day
- VPS informational (not verifiable here): +7.6% ROI at n=3,418 resolved as of Jun17 — carried forward, unconfirmed
- STRUCT-BAND-Q status Jun29 08:14–09:00: `posted=0`, `books=2–3/80` — no new YES posts this morning (NO-only mode, P1 no_reserve=1.00 correct)
- CI remains blocked. Gamma 403 from cloud container (same as Jun27/28 runs).

**BAND_NO + PAIR_FAV** (n 237 → 243, +6):
- +5 fire_no legs (all days_out=1), +1 pair_fav leg
- Rate ≈5.5/day. Fire count at 243 far exceeds n=100 threshold; CI gating is the only blocker.
- Moscow NO fill Jun28 12:06 @ 0.93: **Moscow is NOT in BAND_CITY_ALLOW**. Confirmed legacy position placed pre-Jun26 (before city-filter added) and filled post-narrow-start. Not a city-filter bug — shadow shows Moscow as `no_band` (scan-only) on Jun29. No action.

**FILLED_VS_FIRED** (n 47 → 60, +13 fills):
- 13 new MAKER-FILL registered events since prior run:
  - Jun28: Beijing NO ×1, Moscow NO ×1, London NO ×2, Wuhan NO ×2, Chengdu NO ×2 = 8 new
  - Jun29: Beijing NO, Munich NO, Chengdu NO, London NO = 4 new (through 07:27 UTC)
- Moscow NO (Jun28 12:06 @ 0.93) = legacy pre-city-filter position. Noted above.
- At 11.8 fills/day, n=100 reached in approximately 3 days. **Exec Auditor action becomes more pressing.**
- CI for filled-leg ROI vs all-fires ROI still blocked by Gamma 403. VPS-side resolution join required.

**BASKET_EXIT**: VOID — permanently retired Jun22T07:35. Not revisited.

**THERMO_MAKER_NO** (n=3, unchanged):
- THERMO_MAKER_LIVE=False since Jun23 18:40. All thermo_maker.jsonl records are `thermo_maker_candidate` — 0 fires, 0 placements.
- n=3, WR=33.3%, ROI=−66%, CI=[−132.6%, +0.7%]. CI barely straddles zero at n=3 — noise, not signal.
- Kill gate (n=20) unreachable while paused. Status frozen.

**M1_BETA_LOCKOUT** (n=31, unchanged — stalled 17 days):
- metar_lockout.jsonl today: 3,500 `metar_lockout_candidate` records, 0 placed/fired.
- WR=74.2%, ROI=−0.6%, CI=[−20.6%, +24.4%] — CI straddles zero = AMBIGUOUS. No new data.
- Standing rule (stalled >2 weeks → REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C) first triggered Jun13 (prior prior run, proposed Jun27). Still no human action.
- **STALLED 17 days. Standing rule active for 4 consecutive runs.**

**SUM_POSTED 0.70–0.85** (n 2,964 → 2,982, +18 legs):
- 18 new YES fires where sum_posted ∈ [0.70, 0.85]. Rate ≈16.4/day.
- Fire count 2,982 far exceeds n=100 threshold. Awaiting Gamma resolution for ROI/CI.

---

## PROPOSED ACTIONS (human review — READY/REJECTED gates only)

No gates newly hit READY or REJECTED this run.

### Carry-forward standing proposals (not newly triggered, but unactioned)

**M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C**
- Reason: n=31, AMBIGUOUS (CI straddles 0), stalled 17 consecutive days, logger running but 0 placed orders for 17 days. Standing rule from 2026-06-09: "once n≥100 WR≥95% AND +EV = keep, else REVERT to 0.5°C floors." Gate has been stalled since Jun13 (n crossed to 31 and stopped).
- CI condition (straddles 0) alone is NOT the trigger; the trigger is the 2-week stall with 0 accumulation. The m1 probe generates no live orders.
- **Human action required. Do NOT implement automatically.** This proposal has stood since Jun27.

---

## Structural Blockers

1. **Gamma API 403 from cloud container** — blocks ROI/CI computation for BAND_YES, BAND_NO+PAIR_FAV, FILLED_VS_FIRED, SUM_POSTED. All four gates are fire-count-accumulating but resolution-truth-blind. VPS-side resolution join (band_resolution_join.py) is the only path to CI verdicts.
2. **THERMO_MAKER_LIVE=False** — kill gate n=20 unreachable. n=3 frozen indefinitely.
3. **metar_lockout.jsonl candidates-only** — M1_BETA_LOCKOUT stalled 17 days, 0 placed orders.

---

## Advisory (non-gate observations)

- **FILLED_VS_FIRED at n=60** — Exec Auditor should prioritize VPS-side resolution join now. At 11.8 fills/day, n=100 arrives in ~3 days. The winner's-curse gap (filled-leg ROI vs all-fires ROI) is material to the NO stake sizing question.
- **STRUCT-BAND-Q morning pattern**: `posted=0`, `books=2–3/80`, 18–20 NO candidates, queue=9–11. Consistent with NO-only P1 mode where existing queue already covers top-ranked cells and morning market liquidity is thin (Jun29 Asian-morning UTC). Not a blocker — healthy pattern.
- **Bankroll $80.98** (+$1.79 since prior run). 13 new maker fills in 24h = strongest fill-rate day since narrow-start (Jun26). NO fills accumulating cleanly across 5 allowed cities.
