# Gate-Keeper Report — 2026-07-15

**Run timestamp:** 2026-07-15T09:15:00Z (approx)
**Snapshot:** 2026-07-15T09:01:39Z (age ~14 min — FRESH)
**Prior run:** 2026-07-14T09:15:40Z
**Band dark:** Day 9 (BAND_LIVE=False since 2026-07-06T22:08Z)
**Bankroll:** $36.54 (was $34.69 at prior run, +$1.85 / +5.3% — UPDOWN-SNIPER)
**Capital vs engine ruin floor ($89.16):** 40.9% — mechanically blocked
**Open positions:** 0

---

## STRUCTURAL BLOCKERS (unchanged from prior run)

1. **BAND_LIVE=False** (day 9) — zero resolutions flowing into any band gate. All n-counts frozen.
2. **Capital $36.54 < engine ruin_floor $89.16** — all band paths mechanically blocked regardless of gate status.
3. **Winner's curse CONFIRMED** (G3, n=75): sim ROI is an UPPER BOUND. G1 and G7 AMBIGUOUS CI cannot serve as re-enable evidence.
4. **Pre-registered re-enable condition unmet:** pair_fav n≥40 requires BAND_LIVE=True first (n=9, frozen).
5. **VPS band_resolution_join.py** network-blocked in sandbox — no CLOB winner-flag refresh possible. Resolution truth requires VPS run.

---

## LEDGER TABLE

| Gate | n (resolved) | +24h new | WR | ROI | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1: BAND_YES | 934 | 0 | 15.3% | +4.0%* | [−10.9, +21.1] | **AMBIGUOUS** | N/A — n≥threshold, CI straddles 0; band dark prevents new resolutions |
| G2a: BAND_NO d+1 (shadow) | 115 | 0 | 68.7% | +1.3% | [−11.9, +12.7] | **AMBIGUOUS** | N/A — BAND_NO_ENABLED=False; live n=51 WR=39.2% effectively REJECTED |
| G2b: PAIR_FAV YES | 9 | 0 | — | — | — | **COLLECTING** | ~8.3d from band re-enable (rate ~11/day) |
| G2c: PAIR_FAV NO | 9 | 0 | — | — | — | **COLLECTING** | ~8.3d from band re-enable (rate ~11/day) |
| G3: FILLED_vs_FIRED | 75 (filled) | 0 | 17.3% | −75.8% (filled) vs +7.6% (sim) | [−75.0, −34.2] | **WATCH_ITEM** | 75≥40 — already triggered; frozen (0 new band fills) |
| G4: BASKET_EXIT | — | — | — | — | — | **VOID** | Permanently retired (Jun-22) |
| G5: THERMO_MAKER_NO | 125 | 0 | — | 0.0% | [−9.0, +2.0] | **REJECTED** | Done |
| G6: M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | Done (EVOLVE Jul-04) |
| G7: SUM_POSTED [0.70,0.85] | 382 | 0 | — | +11.5%* | [−11.4, +38.9] | **AMBIGUOUS** | N/A — n≥threshold, CI straddles 0; band dark prevents new resolutions |

*ROI marked with * = UPPER BOUND per winner's curse analysis (state_log Jul-11 22:15Z). Do NOT cite as evidence for re-enable.

### Shadow Fire Counts (counterfactual only — no resolution truth)

| Gate | Shadow fires all-time | New since prior run | Since wind-down |
|---|---|---|---|
| G1 (BAND_YES, all fires) | ~6,370 est. | +20 (Jul-14: 10, Jul-15 partial: 10) | 107 |
| G7 (sum_posted [0.70,0.85]) | 3,159 | +10 (Jul-14: 4, Jul-15 partial: 6) | 72 |

Shadow fires per day (Jul-14 confirmed): 10 total, 4 in G7 range.
Shadow fires per day (Jul-15 partial, ~9h): 10 total, 6 in G7 range (d+2 heavy today).

**Reminder:** Shadow fires are counterfactual. Without resolution truth from CLOB winner flags, they cannot move gate status. Winner's curse means shadow ROI is unreliable anyway.

---

## STATE TRANSITIONS vs PRIOR RUN

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | AMBIGUOUS | No change |
| G2a BAND_NO d+1 | AMBIGUOUS | AMBIGUOUS | No change |
| G2b PAIR_FAV YES | COLLECTING | COLLECTING | No change |
| G2c PAIR_FAV NO | COLLECTING | COLLECTING | No change |
| G3 FILLED_vs_FIRED | WATCH_ITEM | WATCH_ITEM | No change |
| G4 BASKET_EXIT | VOID | VOID | No change |
| G5 THERMO_MAKER_NO | REJECTED | REJECTED | No change |
| G6 M1_BETA_LOCKOUT | REJECTED | REJECTED | No change |
| G7 SUM_POSTED | AMBIGUOUS | AMBIGUOUS | No change |

**No status transitions this run.** Band dark prevents all resolution-based gate movement.

---

## OBSERVATIONS (not gate decisions)

### UPDOWN-SNIPER Activity
- maker_fills_recent.log shows active SNIPER fills today (Jul-15: multiple BUY@0.90–0.983 clips $5, 0 paired SELLs logged yet in this snapshot). Capital rose $36.54 from $34.69 (+$1.85).
- This is **NOT a canonical gate** in this ledger. Exec Auditor owns SNIPER monitoring.
- Prior state alert noted pre-registered SNIPER n≥100 fill-sim gate target ~Jul-15T10:00Z; that is outside scope here.

### G3 WATCH_ITEM: All Fills Remain UNTRACKED
- 7d fill tape (Jul-12 to Jul-15) contains zero MAKER-FILL or STRUCT-BAND-Q entries.
- All fills are UNTRACKED sprint/ladder/orphan-sell/sniper events.
- n=75 frozen. Exec Auditor co-fill cross-tab remains the outstanding action.

### G2c PAIR_FAV_NO Counterfactual CI
- Prior: CF CI=[+12.6, +85.5] at n=32 qualified — but winner's curse blocker applies.
- State: unchanged. Co-fill cross-tab remains unresolved. No re-enable recommendation possible.

### Band Struct Today (Jul-15 partial, confirmed from lite file)
- Fires seen: Beijing d+1 (sum_posted=0.74), Wuhan/Seoul/Shanghai/Chongqing/Chengdu d+2 (0.84, 0.72, 0.81, 0.77, 0.85)
- d+0 lone fire: Munich d+0 sum_posted=0.24 (below G7 floor)
- All fires counterfactual. No BAND_LIVE posts made.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run.**

No flag or parameter changes are proposed by this report.

Pending human actions carried forward from prior runs:
1. **G3 Exec Auditor cross-tab** (mandatory before any band re-enable): filled-leg co-fill rate for Jul-05 clip-guard period. Outstanding action from state_log Jul-11.
2. **Band re-enable path**: Requires (a) capital recovery above engine ruin_floor $89.16 AND (b) pair_fav n≥40 post-guard. Both conditions unmet. No timeline established.
3. **SNIPER audit (non-gate)**: EVOLVE Jul-14 cut CLIP_USD 5→2, RESERVE_USD 2→20. Post-cut performance (+$1.85 today) is preliminary — review after n≥20 fill-sim fires.

---

*Gate-Keeper is REPORT-ONLY. It does not edit strategy code or flip flags.*
*Resolution truth = CLOB/Gamma winner flags only. No price-drift proxies.*
*CI must clear zero before READY. A REJECTED verdict saves capital — stated plainly.*
