# Gate-Keeper Ledger — 2026-07-10T09:00Z

**Snapshot:** 2026-07-10T09:00:16Z (age: 0 min) ✓  
**System:** `klaus systemd: active` ✓  
**Capital:** $204.064 | 30d-HW: $222.90 | Equity rail (50%): $111.45 → **MET** ✓  
**Wind-down:** BAND_LIVE=False since 07-06 22:08Z (43h dark at snapshot)  
**Freeze:** −14% freeze expires **tonight 07-10 21:53Z**  
**Prior run:** 2026-07-07T09:03:00Z (3 days ago)  
**Band shadow confirmation:** band_struct_lite 07-07..07-10 parsed; all 4 days = **0 post records**, only md_shadow scans. BAND_SHADOW inert while BAND_LIVE=False.

---

## Gate Ledger

> **n** = resolved legs (first-fire dedup) used for CI. **+Δ** = change since prior run (07-07T09:03Z). CI95 = Wilson bootstrap on per-leg ROI. Threshold n=100 per gate definition.

| Gate | n (resolved) | +Δ | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| **G1** BAND_YES all slices | 934 | 0 | 15.3% | +4.0% | [−10.9, +21.1] | **AMBIGUOUS** | ∞ dark; VPS join +marginal today |
| **G2a** BAND_NO d+1 shadow | 115s / 51L | 0 | 68.7%s / 39.2%L | +1.3%s | [−11.9, +12.7]s | **AMBIGUOUS** (s) / eff. REJECTED (L) | ∞ BAND_NO_ENABLED=False |
| **G2b** PAIR_FAV_YES (post-guard) | 9 (no resolved) | 0 | — | — | — | **COLLECTING** | rate=0; ~2.8d to n=40 from re-enable |
| **G2c** PAIR_FAV_NO (post-guard) | 9 (no resolved); †cf n=32 | 0 | — | +52.9%†cf / +13.0%†pp | [+12.6, +85.5]†cf | **COLLECTING** (n<100) | n<40 = trend only; ~8.3d to n=100 from re-enable |
| **G3** FILLED-vs-FIRED | 37 fills | 0 | — | — | — | **COLLECTING** | 3 fills to watch-trigger; requires BAND_LIVE |
| **G4** BASKET_EXIT | — | — | — | — | — | **VOID** | Permanently retired 06-22 |
| **G5** THERMO_MAKER_NO | 125 | 0 | — | ≈0% | [−9, +2] | **REJECTED** | Action complete 07-04 |
| **G6** M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | Action complete 07-04 |
| **G7** SUM_POSTED [0.70,0.85] | **382** ↑NEW | **+382r** | — | **+11.5%** | **[−11.4, +38.9]** | ~~COLLECTING~~ → **AMBIGUOUS** | ~1,528r to READY at current ROI; ∞ dark |

†cf = counterfactual VPS join 07-07 EVOLVE (pre+post guard shadow NO legs, n=32).  
†pp = per-pair $ ROI from 07-09 EVOLVE combined join (n=30 pairs).  
s = shadow data. L = live data (authoritative for re-enable decisions).

---

## State Transitions vs Prior Run (07-07T09:03Z)

| Gate | Prior Status | Current Status | Driver |
|---|---|---|---|
| **G7 SUM_POSTED [0.70,0.85]** | COLLECTING (n=0 resolved) | **AMBIGUOUS** (n=382) | 07-09 22:20Z EVOLVE: VPS band_resolution_join.py → n=382, ROI +11.5%, Wilson CI=[−11.4,+38.9]; CI straddles 0 |
| All others | (unchanged) | (unchanged) | — |

---

## PROPOSED ACTIONS (human review)

**No gate newly READY or REJECTED this run.** No flag/param changes recommended.

---

## Advisory Notes

**[URGENT — VPS JOIN]** band_resolution_join.py was recommended to run at 07-10 11:23Z per 07-09 audit. G1 and G7 will receive marginal increments from pre-dark tail settlements (markets posted before 07-06 but resolved since 07-09). Expected +5–20 resolved total. G7 will remain AMBIGUOUS regardless.

**[EQUITY RAIL CLEARED — STRUCTURAL DECISION PENDING 07-12]** Capital $204.06 (09:00Z) exceeds the $111.45 re-enable rail. The −14% freeze expires **tonight at 21:53Z**. After expiry, the equity condition for BAND_LIVE re-enable is fully met. The only remaining binding blocker is the **pre-registered pair post-guard n≥40 condition (currently n=9, frozen while dark)**. Weekly slot 07-12 must decide: (a) create shadow-posting mode to accumulate pair_fav while BAND_LIVE=False, or (b) amend the re-enable condition. Human decision required before the compounding engine can restart.

**[G2c TREND — NOT A GATE VERDICT]** PAIR_FAV_NO counterfactual (07-07 EVOLVE VPS join): n=32 shadow NO legs, ROI=+52.9%, CI=[+12.6, +85.5]. The CI lower bound (+12.6%) clears zero — this is the only gate with an unambiguously positive CI at present. However: **n=32 < 40 is a trend, not a decision; n < 100 does not meet the pre-registered gate threshold.** Do not re-enable on this basis. At rate ~11 pairs/day post re-enable, n=100 requires ~8 live days.

**[G7 CI PATH — AMBIGUOUS IS CORRECT]** ROI +11.5% with CI lower bound −11.4% is not an edge. To push CI_lower > 0 at the current ROI estimate: approximately n~1,528 resolved are needed (4× current, assuming ROI holds). At ~50 shadow fires/day when live, that is ~23 days of active firing post re-enable. Do not label this "promising" — it is a wide interval around an uncertain mean. The verdict is AMBIGUOUS.

**[G1 BAND_YES — STALE JOIN]** n=934 resolved was from a window-relative join (Jul05 22:25Z). The 07-09 EVOLVE ran a separate join (n=591 total, band YES n=465, ROI=−5.4%, CI=[−24.7,+17.9]) showing a more negative point estimate. Both aggregation windows straddle 0. Status unchanged: AMBIGUOUS. The YES cut is re-confirmed by the 07-09 join.

**[CAPITAL RECOVERY — CONTEXT ONLY]** Bankroll $204.06 vs $42.02 at prior gatekeeper run (+$162 in 3 days). Recovery is entirely via sprint ladder — **not from the band engine**. Engine flow = 0 throughout. Ruin floor ($89.16) safely below current capital. All band/engine gates remain frozen.

**[BAND DARK CONFIRMATION]** band_struct_lite files parsed for 07-07, 07-08, 07-09, 07-10: all contain ONLY md_shadow scan records (155/147/143/133 per day respectively). **Zero post records across all 4 days confirmed.** BAND_SHADOW=True flag is inert while BAND_LIVE=False. Shadow fire counter has not grown since 07-06 22:08Z.

---

*Report generated: 2026-07-10T09:00Z. Next gatekeeper: at BAND_LIVE re-enable or weekly 07-12 slot, whichever comes first. REPORT-ONLY — implement nothing.*
