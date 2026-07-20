# Gate-Keeper Report — 2026-07-20

**Run at**: 2026-07-20T09:09Z  
**Snapshot**: data-mirror 2026-07-20T09:09:08Z (snapshot age: fresh, <1h)  
**System**: `klaus systemd: active`  
**Capital**: $21.495 (ruin_floor $89.16 — capital is 24.1% of ruin_floor; ALL band paths mechanically blocked)  
**System posture**: FULLY RISK-OFF — UPDOWN_STOP present (cut 07-19 11:26Z), BAND_LIVE=False (day 14), weather dark, NEG_RISK/RECYCLE ruin-floor-blocked, ladder disarmed.  
**Prior run**: 2026-07-19T09:19Z

---

## GATE LEDGER

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (YES legs, per-slice) | 934 resolved | 0 | 15.3% | **+4.0%\*** | [−10.9, +21.1] | **AMBIGUOUS** | Indefinite (band dark, no resolutions) |
| G2a BAND_NO d+1 | 115 resolved | 0 | 68.7% | +1.3% | [−11.9, +12.7] | **AMBIGUOUS†** | Indefinite (BAND_NO_ENABLED=False) |
| G2b PAIR_FAV_YES | 9 post-guard | 0 | — | — | — | **COLLECTING** | ~8d from band re-enable |
| G2c PAIR_FAV_NO | 9 post-guard | 0 | — | — | — | **COLLECTING** | ~8d from band re-enable |
| G3 FILLED vs FIRED (winner's curse) | 75 filled | 0 | 17.3% filled | −75.8% filled vs +7.6% sim | [−75.0, −34.2] | **WATCH_ITEM** | No new fills (all paths stopped) |
| G4 BASKET_EXIT | VOID | — | — | — | — | **VOID** | — (permanently retired 06-22) |
| G5 THERMO_MAKER_NO | 125 resolved | 0 | — | 0.0% | [−9.0, +2.0] | **REJECTED** | — (human decision 07-04; no reconsideration without directive) |
| G6 M1_BETA_LOCKOUT | 31 resolved | 0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | — (human decision 07-04) |
| G7 SUM_POSTED [0.70,0.85] | 382 resolved | 0 | — | **+11.5%\*** | [−11.4, +38.9] | **AMBIGUOUS** | Indefinite (band dark, no resolutions) |
| **G8 CROSSING post-cut (NEW)** | **2 post-cut** | **+2 (NEW GATE)** | **50.0%** | **−$4.88 sim** | **[0.03, 0.97]** | **COLLECTING** | **~5–22d to n=100\*\*** |

\* ROI is UPPER BOUND — winner's curse confirmed (G3 filled WR=17.3% vs sim WR; DO NOT cite G1/G7 sim CI as re-enable evidence)  
† Live n=51 WR=39.2% is effectively REJECTED; shadow CI AMBIGUOUS but irrelevant — do not re-enable on shadow CI alone  
\*\* Rate uncertain at n=2: BTC-only ~0.19 events/h in first 10h post-cut; multi-asset (5x) shadow active since 19:05Z Jul-19, speedup 3–5× expected but unconfirmed. Low end ~5d, high end ~22d to n=100.

---

## STATE TRANSITIONS vs PRIOR RUN (2026-07-19T09:19Z)

### NEW GATE REGISTERED
**G8 UPDOWN_CROSSING** — `updown_crossing_reenable_gate` registered by EVOLVE-WEEKLY 2026-07-19 14:30Z (after the prior gatekeeper run at 09:19Z). This gate did not appear in the prior `gatekeeper_state.json`. First tracking in this run.

Pre-registered pass conditions (ALL required):
1. Post-cut CROSSING (p_model≥0.995, 5m any asset) n≥100
2. CI-lo > BE=0.9629
3. Owner floor re-waiver (equity $21.50 < $40 kernel floor — waiver chain ended with cut; ESCALATIONS #1)
4. Min-size restart

Kill rule (armed immediately): if WR_post_cut falls below BE=0.9629 on sufficient n at the next EVOLVE review, recommend staying CUT.

Evidence as of gate_ledger 22:05Z Jul-19 (most recent authoritative grade from `shadow_grade.py --refetch`):
- POST-CUT n=2: 1W/1L, WR=50.0%, sim ROI=−$4.88
- All-history CROSSING n=121: WR=0.9669, CI-lo=0.9181 vs BE=0.9629 (point barely clears, CI-lo does NOT)
- n=121 is reference only — pre-cut rows cannot count for re-entry
- The first post-cut loss (Jul-19, Down@0.93 resolved Up, lost by 0.2bp) is real data, not noise

**No flag change. Gate added to state as COLLECTING.**

### UNCHANGED GATES (no status transitions)
All G1–G7 gates: 0 new resolutions in the past 24h. System fully stopped — no mechanism to add resolution truth to any gate. All statuses frozen.

Shadow file size updates (informational, no gate impact):
- `data/shadow/thermo_maker.jsonl`: 4.487MB (+427KB since prior; REJECTED G5, rolling accumulation, no resolutions)
- `data/shadow/metar_min_lockout.jsonl`: 8.912MB (+432KB since prior; REJECTED G6, rolling accumulation)
- G1 shadow fires since wind-down: ~176 estimated (+13 at rate 13/day; counterfactual only, no resolution truth)
- G7 shadow fires since wind-down: ~116 estimated (+9 at rate 8.6/day; counterfactual only)

---

## DETAILED GATE NOTES

### G1: BAND_YES (days_out 0/1/2 × offset 0/1/2 × price band)
Threshold n=100/side. **Already exceeded** (n=934) but CI straddles 0 → AMBIGUOUS.
- Winner's curse CONFIRMED (G3, n=75 filled, WR=17.3% vs sim WR). CI from simulation is an UPPER BOUND. Do not use G1 sim CI as re-enable evidence.
- Resolution n frozen at 934 since Jul-06 22:08Z (band dark day 14).
- Today's band_struct_lite (00:01–09:01Z Jul-20, 132 records): 0 fire records, 20 sum_gate rejections, 118 md_shadow records. Consistent with BAND_LIVE=False.
- Capital $21.50 < ruin_floor $89.16 — band re-enable mechanically blocked regardless of CI.
- Re-enable pre-condition: post-guard PAIR_FAV n≥40 (n=9, frozen) also not met.

### G2a: BAND_NO d+1
Threshold n=100. n=115 (exceeded). CI straddles 0 → AMBIGUOUS.
- **Live n=51 WR=39.2% is the operative number** — effectively REJECTED by real fills.
- BAND_NO_ENABLED=False since Jul-02 (7d realized n=51 WR 39.2% rail). No new fires possible.
- Shadow CI AMBIGUOUS is irrelevant — live result dominates.

### G2b/G2c: PAIR_FAV YES/NO
- n=9 post-guard (frozen since Jul-06). Rate ~11/day when live.
- PAIR_FAV_ENABLED=True in config but BAND_LIVE=False blocks execution.
- PAIR_FAV_NO counterfactual CI [+12.6,+85.5] at n_CF=32: BIASED by winner's curse (state_log Jul-11 22:15Z). Do not re-enable on CF ROI alone.

### G3: FILLED vs FIRED (winner's curse watch)
Threshold n=40 (met; 75 filled resolutions). Status WATCH_ITEM.
- Gap confirmed: filled WR=17.3%, sim WR≈76%. Gap=−83.4pp. CI for filled: [−75.0, −34.2] (entirely negative).
- This is why G1/G7 sim ROI must be treated as upper bounds.
- No new fills since prior (UPDOWN_STOP + band dark + sniper stopped).
- **Exec Auditor backlog unresolved**: Jul-16 SELL@0.96 (token=1399483673820402) + Jul-18 SELL@0.92 (token=2664940529472113) + Jul-18 companion BUY@0.08 (token=7094108612094851) + 4th orphan MAKER BUY@0.02 Jul-19 02:14Z (token=5717613767097074) — n conservatively held at 75 until classified.

### G5: THERMO_MAKER_NO
Threshold: first 20 resolved (pre-registered Jul-11 22:40). n=125 (threshold met). 
REJECTED by EVOLVE Jul-04 21:53Z (human decision). ROI=0.0%, CI=[−9.0,+2.0]. Shadow rolling but no resolutions possible (THERMO_MAKER_LIVE=False since Jun-23).
No reconsideration without explicit human directive.

### G6: M1_BETA_LOCKOUT
Threshold n=100 with WR≥95% AND +EV. n=31, WR=74.2%, ROI=−0.6%.
REJECTED by EVOLVE Jul-04 21:53Z (human decision). MIN_LOCKOUT_LIVE=False since Jul-13.
Revert-to-0.5C-floors recommendation stands (state_log 2026-06-09).

### G7: SUM_POSTED [0.70, 0.85]
Threshold n=100 (met; n=382). CI straddles 0 → AMBIGUOUS.
- ROI=+11.5% is UPPER BOUND (winner's curse blocker — G3 confirmed).
- Band dark = no new resolutions. Shadow accumulating counterfactually (~116 est total).
- Gate inert while band dark.

### G8: UPDOWN_CROSSING post-cut (NEW THIS RUN)
See STATE TRANSITIONS above.
- n=2, CI meaningless (WR could be anywhere in [0.03, 0.97] at n=2).
- First loss in the first 2 events is directionally concerning — consistent with the cut being right.
- All-history n=121 reference: CI-lo=0.9181 vs BE=0.9629 → history-population does NOT clear CI.
- **Multi-asset shadow (5 assets: BTC/ETH/SOL/XRP/DOGE, 5m) active since 19:05Z Jul-19.** First per-asset 5m grade expected ~Jul-21 when snaps span ≥2 days. This should accelerate n-collection 3–5×.
- **No morning EVOLVE slot committed yet today** (as of snapshot 09:09Z Jul-20) — the gate_ledger and crossing count are as of 22:05Z Jul-19. Actual n may be slightly higher; next EVOLVE daily will update.
- Kill rule: armed. If point WR < BE=0.9629 at n≥20, recommend staying CUT at next EVOLVE review.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED in this run.**

All gates remain frozen in their prior status. The single new development is the addition of G8 (UPDOWN_CROSSING post-cut) to the ledger as COLLECTING. No flags to flip.

**Standing blockers for any gate to move off COLLECTING/AMBIGUOUS:**
1. G1/G7/G2b/G2c: Require BAND_LIVE re-enable AND capital above ruin_floor ($89.16) AND owner re-waiver. None are close.
2. G8: Requires n≥100 post-cut CROSSING events + CI-lo > BE + owner floor re-waiver. Currently n=2, ETA 5–22d.
3. All gates: Winner's curse (G3) is a hard blocker on any sim-CI-based re-enable argument for band paths.

**G3 Exec Auditor backlog** (not a gate change, but informational escalation): 4 unclassified fills remain from Jul-16/Jul-18/Jul-19. This needs owner resolution to unfreeze G3 n. Not a gatekeeper action.

---

*Sources: data-mirror SHA c58852e (2026-07-20T09:09:08Z) · gate_ledger_latest.md 22:05Z Jul-19 · gatekeeper_state.json prior run 09:19Z Jul-19 · updown_sniper.jsonl 596 records · band_struct_lite.jsonl 2026-07-20 132 records · maker_fills_recent.log last fill 07:59Z Jul-19 · state_log.md EVOLVE-WEEKLY 14:30Z Jul-19*
