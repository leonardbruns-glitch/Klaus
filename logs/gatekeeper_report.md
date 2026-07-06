# Klaus Gate-Keeper Report — 2026-07-06

**Run timestamp:** 2026-07-06T09:10Z  
**Snapshot:** `data-mirror:4ce9f72b` — 2026-07-06T08:59:16Z (≤15min old ✓)  
**System:** `klaus systemd: active` ✓  
**Bankroll:** $141.74 cash; daily_start $217.44 (intraday PnL −$75.70 / −34.8%; 0 open positions); consecutive_wins 7  
**Prior gatekeeper run:** 2026-07-05T09:30Z (elapsed ~23.7h)  
**Resolution source:** EVOLVE VPS `band_resolution_join.py` — Jul04 21:53Z (last full join, n=934 all-time). EVOLVE Jul05 22:25Z ran a *window-relative* rerun (n=788); cloud Gamma API still 403/timeout — VPS remains sole resolution path.

**KEY EVENT THIS RUN:** PAIR_FAV mechanism fix deployed Jul05 22:20Z (commit `365d59d04`). Prior pair_fav fires (n=9 each) confirmed as contaminated by naked-YES degeneration (42/43 pairs pinned at qy+qn=0.90, co-fill rate 26% vs expected ~100%). Gate 2b/2c counts RESTART from clip-guard activation. This is the dominant change vs prior.

---

## Gate Ledger

CI95: ROI confidence interval from Wilson 95% WR bounds → ROI = WR/quote − 1. "BLOCKED" = Gamma 403 cloud; VPS only.  
n column: n_resolved for CI-computable gates; n_fires for CI-blocked gates.  
‡ = count restarts post clip-guard (Jul05 22:20Z); pre-guard n discarded (contaminated).

| Gate | n | +24h | WR | ROI | CI95 (ROI) | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1 BAND_YES (all) | 934 res | +0 res / +5 fires | 15.3% | +4.0% | [−10.9%, +21.1%] | **AMBIGUOUS** | CI must shift; awaits VPS join |
| 1a d+2 | 672 res | — | 14.4% | +5.4% | [−12.4%, +26.3%] | AMBIGUOUS | — |
| 1b d+1 | 190 res | — | 17.4% | +5.3% | [−23.0%, +41.8%] | AMBIGUOUS | — |
| 1c d+0 | 72 res | — | 18.1% | −7.8% | (n<100) | COLLECTING | ~2d to n=100 |
| 2a BAND_NO d+1 | 115 res | +0 | 68.7%† | +1.3%† | [−11.9%, +12.7%] | **AMBIGUOUS** | N/A (NO disabled) |
| 2b PAIR_FAV YES | 5‡ | +5‡ (restart) | — | — | (n<40) | COLLECTING | ~9d to n=100 |
| 2c PAIR_FAV NO | 5‡ | +5‡ (restart) | — | — | (n<40) | COLLECTING | ~9d to n=100 |
| 3 FILLED_VS_FIRED | ~37 fills | +13 | — | — | BLOCKED | COLLECTING | ~5h to n=40 watch |
| 4 BASKET_EXIT | — | — | — | — | — | **VOID** | N/A — retired Jun22 |
| 5 THERMO_MAKER_NO | 125 ext | +0 | ≈mkt | EV ≈ 0 | n/a | **REJECTED** | N/A |
| 6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** | N/A |
| 7 SUM_POSTED 0.70–0.85 | >3,076 fires | +~20 est | — | — | BLOCKED | COLLECTING | VPS join needed |

†Shadow-join only. Live WR=39.2% at comparable quote — effectively REJECTED by live data. BAND_NO_ENABLED=False is the correct protection.  
‡ Mechanism-contaminated prior n=9 discarded. Post-guard fires only (Jul06 00:00Z onward). Rate ~11 pairs/day.

---

## Gate-by-Gate Notes

### Gate 1 — BAND_YES

- **Fires:** 6158 all-time (prior) + ~5 new pair_fav YES fires (Jul06). Standalone YES paused (BAND_YES_LIVE_MIN_DOUT=9 since Jul03).
- **Resolved:** 934 (Jul04 21:53Z VPS join, last full). EVOLVE Jul05 22:25Z ran a window-relative rerun (n=788 — smaller window; no new all-time CI). CI unchanged: [−10.9%, +21.1%] straddles 0 → **AMBIGUOUS** (no change).
- **Shadow/live divergence:** disp_ratio 0.34–0.82 vs 1.10 re-enable threshold — NOT MET. Standalone YES remains correctly paused.
- **No change in gate status or deployment posture.**

### Gate 2 — BAND_NO + PAIR_FAV

**2a — BAND_NO d+1 (standalone NO):** BAND_NO_ENABLED=False since Jul02. n=115 resolved (VPS Jul04 shadow join), AMBIGUOUS, CI=[−11.9%, +12.7%]. Live n=51 WR=39.2% vs shadow 68.7% — winner's-curse confirmed. No new data, no change.

**2b/2c — PAIR_FAV YES/NO — MECHANISM FIX DEPLOYED:**

State_log Jul05 22:20Z documents that 42/43 pair posts Jul03–Jul05 were degenerate: `qy + qn = 0.90` (the hard Σ cap) forced NO quote >1¢ below touch, collapsing pairs into naked mode-YES posts. Evidence: 24h fill tape = 19 YES / 5 NO fills (~26% co-fill vs ~100% expected), resolved one-sided YES n=10 WR=10% avg quote 0.46, pair-slice 7d net −$28..−$32, PF≈0.1. Clip-guard (`365d59d04`) deployed at 22:20Z: skip any pair where Σ cap forces NO bid >1¢ below NO touch. Co-filled pairs confirmed to work (same-bucket YES −100% + NO +120–126% ⇒ +10%/pair).

**Prior n=9 each (COLLECTING) is contaminated and discarded.** The n=9 WR/ROI point estimates (+20.7% YES, +3.7% NO from prior report) were from the defective mechanism and must not be carried forward.

Post-guard fires (Jul06 00:00–09:00Z, band_struct_lite confirmed): **n=5 complete pairs** (5 YES + 5 NO; cities Wuhan, Shanghai, Beijing, Chongqing, Munich; all d+0). Rate ~11 pairs/day based on 10.8h window.

- ETA to n=40: ~3 days (2026-07-09 est)
- ETA to n=100: ~9 days (2026-07-15 est)
- **Status: COLLECTING RESTART.** Both sub-legs reset to n=5 post-guard.

### Gate 3 — FILLED_VS_FIRED

- **n_fills (rolling 7d tape):** 37 est (+13 since prior). New registered fills since Jul05 09:30: 6 on Jul05 afternoon (Seoul/Tokyo/Moscow/Munich/Shanghai/Tokyo), 7 on Jul06 00:00–07:52 (Wuhan NO, Wuhan YES, Shanghai NO, Shanghai YES, Beijing YES, Chongqing NO, Chongqing YES).
- **Fill rate:** ~13/day (past 24h); prior was ~6.9/day. Rate increase consistent with clip-guard improving pair co-fill (post-guard: 3 NO fills on Jul06 vs 1 NO in prior tape).
- **Threshold n=40 watch trigger:** ETA ~5 hours (3 more fills needed at current rate).
- **When n=40 crossed:** EVOLVE VPS must run filled-vs-fires divergence join per slice. This is a winner's-curse watch item, not a direct scale-up gate.
- **Status: COLLECTING.** CI still blocked (Gamma 403 cloud).

### Gate 4 — BASKET_EXIT

**VOID** — permanently retired Jun22T07:35 (4 fatal structural flaws). No change, do not revisit.

### Gate 5 — THERMO_MAKER_NO

**REJECTED** — no change. THERMO_MAKER_LIVE=False since Jun23. EV≈0 at n=125 external falsification. Human may upgrade to VOID (semantics only).

### Gate 6 — M1_BETA_LOCKOUT

**REJECTED** — no change. METAR_LOCKOUT_TEMP_FLOOR=0.5°C (commit 2813daa1e). Capacity=0. Standing item closed.

### Gate 7 — SUM_POSTED 0.70–0.85

- **n_fires:** >3,076 est (+~20 since prior). `sum_posted` field absent from band_struct_lite; exact increment unquantifiable from cloud. Full band_struct.jsonl (768KB hot file) or VPS join required.
- **Note on post-guard rate:** PAIR_FAV posts at ~10–12 leg-pairs/day. The qy+qn for genuine pairs (post-guard: both legs at touch) will typically land in 0.80–0.90 range — likely ABOVE the 0.85 gate ceiling. The clip-guard may reduce future accumulation into the [0.70, 0.85] slice as degenerate pairs (which had artificially low Σ) are filtered out. Rate effect unknown; does not matter since n_fires >> 100 already.
- **Status: COLLECTING.** CI is the sole blocker; n threshold crossed long ago. EVOLVE must run `band_resolution_join.py` with `sum_posted` filter applied on deduped first-fire legs.

---

## State Transitions vs Prior (2026-07-05T09:30Z)

| Gate | Prior Status | Current Status | Driver |
|---|---|---|---|
| BAND_YES | AMBIGUOUS | AMBIGUOUS | No change — standalone paused, no new VPS join |
| BAND_NO d+1 | AMBIGUOUS | AMBIGUOUS | No change — NO disabled |
| PAIR_FAV YES | COLLECTING (n=9, contaminated) | **COLLECTING RESTART** (n=5, post-guard) | Clip-guard Jul05 22:20Z invalidated pre-guard mechanism |
| PAIR_FAV NO | COLLECTING (n=9, contaminated) | **COLLECTING RESTART** (n=5, post-guard) | Same |
| FILLED_VS_FIRED | COLLECTING (n=24) | COLLECTING (n≈37) | +13 fills; approaching n=40 watch trigger |
| BASKET_EXIT | VOID | VOID | No change |
| THERMO_MAKER_NO | REJECTED | REJECTED | No change |
| M1_BETA_LOCKOUT | REJECTED | REJECTED | No change |
| SUM_POSTED 0.70–0.85 | COLLECTING | COLLECTING | No change; +~20 est fires |

**This run: 0 READY, 0 REJECTED, 0 AMBIGUOUS transitions. 2 gate data resets (PAIR_FAV 2b/2c — mechanism fix).**

---

## PROPOSED ACTIONS (human review)

Gates newly hitting READY: **none.**  
Gates newly hitting REJECTED: **none.**

No flag or parameter changes are warranted by this run. The clip-guard mechanism fix and PAIR_FAV data reset are already actioned in code.

**Pending watch item:** Gate 3 (FILLED_VS_FIRED) will cross n=40 within ~5 hours. When crossed, the next EVOLVE VPS run should include a fill-vs-fire ROI comparison per slice. This is cloud-blocked (Gamma 403); VPS-only task.

---

## Advisory

1. **PAIR_FAV data reset is the dominant news:** The prior n=9 WR/ROI estimates (+20.7% YES, +3.7% NO) must be retired — they were from naked-YES posts, not genuine pairs. The good news: co-filled pairs confirm +10%/pair EV (state_log Jul05 22:20Z verified join). Post-guard n=5 is the correct counter. ETA to meaningful CI (n=40 resolved) requires ~3 days of fires + VPS join.

2. **Fill rate increase post-clip-guard:** Prior rate 6.9/day, current 13/day. The clip-guard likely improves NO co-fill rate (more genuine pairs resting on book at correct prices → both legs fill). Expect fill rate to stabilize at ~8–12/day once the initial clipped-pair-flush clears.

3. **Capital drawdown today (informational):** daily_start $217.44, current $141.74 = −$75.70 (−34.8%). 0 open positions. Drop occurred before 07:34 UTC (cap=$125 at 07:34, recovering to $142 by 08:56). Consistent with 7+ resolved positions on Jul06 before 07:30. Not a gate subject but warrants EVOLVE diagnosis.

4. **BAND_YES re-enable trigger unchanged:** disp_ratio 0.34–0.82 vs 1.10 threshold — NOT MET. Standalone YES remains correctly paused. EVOLVE Jul05 window-join n=788 (vs prior 934) — window shrinkage suggests recent window-limited join, not full-history CI refresh.

5. **SUM_POSTED gate urgency:** n_fires >> 100 for months; CI is the only thing standing between this and a verdict. One EVOLVE VPS run with `sum_posted in [0.70, 0.85]` filter on the deduped first-fire file would deliver a verdict. This gate has been stuck on "VPS join needed" for multiple weeks.

6. **BAND_NO: winner's-curse is decision-grade.** Shadow WR=68.7% vs live WR=39.2% at nearly identical quotes. No new data this run. BAND_NO_ENABLED=False is permanently correct until a fresh live fill tape (post-guard, at least n=40 fills) produces a clean estimate.
