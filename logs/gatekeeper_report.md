# Klaus Gate-Keeper Report — 2026-07-13

**Run timestamp:** 2026-07-13T09:00Z  
**Prior run:** 2026-07-11T09:03Z (+48h gap)  
**Snapshot age:** 1h (2026-07-13T08:58:39Z — within 6h limit ✓)  
**System status:** `active` ✓  
**Bankroll:** $87.40 (⚠️ BELOW ruin_floor $89.16 per state_log Jul-12 19:20Z)  
**Band dark:** Day 7 (BAND_LIVE=False since 2026-07-06 22:08Z)

---

## Gate Ledger

| Gate | n | +48h | WR | ROI | CI95 | Status | ETA |
|------|---|------|----|-----|------|--------|-----|
| G1 BAND_YES (all slices) | 934 | +0 | 15.3% | +4.0%† | [−10.9, +21.1] | AMBIGUOUS | ∞ (band dark) |
| G2a BAND_NO d+1 (shadow) | 115 | +0 | 68.7% | +1.3% | [−11.9, +12.7] | AMBIGUOUS* | ∞ (disabled) |
| G2b PAIR_FAV YES (post-guard) | 9 | +0 | N/A | N/A | N/A | COLLECTING | ∞ (band dark) |
| G2c PAIR_FAV NO (post-guard) | 9 | +0 | N/A | N/A | N/A | COLLECTING | ∞ (band dark) |
| G3 FILLED_VS_FIRED | **75** | **+38** | 17.3% | **−75.8%** | **[−75%, −34%]** | **⚠️ WATCH_ITEM** | n/a (threshold crossed) |
| G4 BASKET_EXIT | — | — | — | — | — | VOID (retired) | — |
| G5 THERMO_MAKER_NO | 125 | +0 | — | ~0% | [−9, +2] | REJECTED | done |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6, +24.4] | REJECTED | done |
| G7 SUM_POSTED [0.70, 0.85] | 382 | +0 | — | +11.5%† | [−11.4, +38.9] | AMBIGUOUS | ∞ (band dark) |

† **ROI declared UPPER BOUND (not estimator)** per winner's curse analysis (state_log 2026-07-11 22:15Z). Simulation CI is biased — band re-enable may NOT cite G1 or G7 sim ROI as evidence.  
\* G2a BAND_NO shadow AMBIGUOUS but irrelevant: live n=51 WR=39.2% = effectively REJECTED. BAND_NO_ENABLED=False, not to be re-enabled on shadow CI alone.

---

## State Transitions vs Prior Run (2026-07-11T09:03Z)

| Gate | Prior status | Current status | Trigger |
|------|-------------|----------------|---------|
| **G3 FILLED_VS_FIRED** | COLLECTING (n=37) | **WATCH_ITEM (n=75)** | n crossed pre-registered threshold of 40 filled resolves; winner's curse analysis (state_log Jul-11 22:15Z) provides n=75 with ROI=−75.8% vs sim+7.6% |
| All others | unchanged | unchanged | Band dark day 7, 0 new posts |

**Newly READY:** 0  
**Newly REJECTED:** 0  

---

## G3 WATCH_ITEM — Detail

**Pre-registered rule:** n ≥ 40 filled resolves → "winner's-curse watch item for the Exec Auditor"

**Source:** `analysis/weather/winners_curse_crosstab_0711.py` + `state_log 2026-07-11 22:15Z`

**Finding:**
- n=75 WEATHER_MAKER fills resolved (06-11..07-06 all-time VPS join)
- WR: 13W / 62L = 17.3% at avg entry px 0.417
- Filled ROI: −75.8% ($−173.78 / $229.36 invested)
- Sim (same-era shadow) ROI: +7.6% (n=3,418)
- **Gap: −83.4pp, filled vs fired**

**CI on filled ROI (Wilson method on WR, with avg_px=0.417):**
- WR Wilson 95% CI: [10.4%, 27.4%]
- Translated to ROI: [−75.0%, −34.2%]
- **CI entirely negative: both bounds < 0**

**Per-cell same sign:** filled WR=20% (n=15) vs sim=92.9% (n=14) on NO d+1 0.60–0.85 — winner's curse is structural across slices, not a single-cell artifact.

**Exception noted in state_log:** Co-filled PAIR (Σask ≤ 0.92 pays 1.0 on completion regardless) — adverse selection lives in the naked leg only. PAIR_FAV co-fill rate under Jul-05 clip-guard may be viable; do not conflate with naked-leg ROI.

**Blocker implication:** State_log explicitly: *"no YES/NO band re-enable may cite sim ROI alone."* This blocks any READY verdict for G1 and G7 based on shadow CI.

---

## Structural Blockers (unchanged)

1. BAND_LIVE=False since Jul-06 22:08Z — day 7 of darkness. All G1/G7/G2 shadow accumulation frozen.
2. Pre-registered BAND_LIVE re-enable condition: post-guard pair n ≥ 40 UNMET (n=9). Frozen while band dark.
3. Winner's curse (G3 WATCH_ITEM): sim ROI is an upper bound. No re-enable on shadow CI alone.
4. S3 dispersion gauge: UNBLOCKED but trigger NOT met (Jul3–10: 1/8 days ≥ 1.10, never 2 consecutive). Standalone YES band premise dead through Jul-10.
5. G2a BAND_NO: live n=51 WR=39.2% = effectively REJECTED. Do not re-enable.
6. 07-12 structural BAND_LIVE decision: Not taken (system_status commits show no Jul-12 EVOLVE/structural change). Still pending as of this run.

---

## Alerts

### ⚠️ CRITICAL: Bankroll Below Ruin Floor
- **Current:** $87.40 (Jul-13 08:58Z)
- **Ruin floor:** $89.16 (dynamic, per state_log Jul-12 19:20Z)
- **Prior run:** $163.16 (Jul-11 09:03Z) → **−$75.76 (−46.4%) in 48h**
- **Prior alarm already fired:** −$40.90 (−20%) Jul-10→Jul-11
- **Source:** Sprint/ladder UNTRACKED TAKER fills (Jul-11..Jul-13 in maker_fills_recent.log), not band trades
- **Jul-13 intraday:** $103.82 start → $87.40 = −$16.42 so far today. Two large open BUY fills visible (51.5 sh @0.449, 45 sh @0.526 — no exit yet in log)
- **Band is NOT the source** (0 band fires since Jul-06). Draws are from sprint/ladder system.

### ⚠️ G3 WATCH_ITEM — New Transition (see detail above)
- n=75 crossed n=40 threshold
- Filled ROI −75.8% vs sim +7.6% → −83.4pp gap
- CI entirely negative [−75%, −34%]
- Exec Auditor mandate: flag and investigate co-fill rate on PAIR leg

### INFO: G2c PAIR_FAV NO counterfactual CI qualified
- Counterfactual n=32 ROI=+52.9% CI=[+12.6,+85.5] (reported as trend prior run)
- State_log Jul-11 22:15Z: "CF ROI +52.9% n=32 inherits the sim bias"
- Do not use as re-enable evidence. Pair co-fill at clip-guard is the relevant measure.

### INFO: Jul-12 structural slot — no decision taken
- Owner directive Jul-12 19:20Z: "switch to BTC 5/15m $10k, no restrictions" — DECLINED with evidence (3rd audit). Ladder remains active.
- No BAND_LIVE re-enable decision taken Jul-12 per system_status commit log.
- Next structural slot not pre-registered; recommend human sets one.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED. No flag changes recommended.**

Watch items for human attention (report-only, no implementation):

1. **BANKROLL CRITICAL:** Capital $87.40 < ruin_floor $89.16. Sprint/ladder system is burning cash. Exec Auditor should audit Jul-11..Jul-13 untracked fills and reconcile sleeve vs capital.

2. **G3 WATCH_ITEM active:** Exec Auditor should cross-tab co-fill rate on the PAIR leg (co-filled pairs pay 1.0 regardless of leg outcome) vs naked-leg fills. If co-fill rate is high at clip-guard, PAIR_FAV may retain edge despite naked-leg winner's curse.

3. **Structural decision:** BAND_LIVE re-enable condition (pair n≥40) is unreachable while band dark. Human must either: (a) amend the pre-registered condition to allow shadow-posting mode to accumulate pair data, or (b) accept that re-enable path is indefinitely blocked. This was pending from Jul-09 EVOLVE; not addressed Jul-12.

---

## Gate Accumulation Rates

| Gate | Rate (posts/day when live) | Days to threshold (from re-enable) | Note |
|------|---------------------------|--------------------------------------|------|
| G1 BAND_YES | ~50 resolves/day (historic) | n=934 >> 100; CI is blocker, not n | sim CI is upper-bound bias |
| G2b/G2c PAIR_FAV | ~11/day when live | ~8.3d to n=100 from re-enable | band dark = 0/day |
| G3 FILLED_VS_FIRED | n/a (n=75 > 40) | WATCH_ITEM active | no pre-reg threshold beyond 40 |
| G7 SUM_POSTED | ~50 resolves/day | ~1,528 needed to push CI lower; ~30.6d | sim CI upper-bound bias |

---

*Report generated by Klaus Gate-Keeper Agent. REPORT-ONLY: no code or flag changes made.*
