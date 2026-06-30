# Klaus Gate-Keeper Report — 2026-06-30

**Run:** 2026-06-30T09:14Z | **Snapshot:** 2026-06-30T09:06:12Z (8 min old) | **Bot:** active  
**Bankroll:** $94.04 (+$13.06 vs prior $80.98 = **+16.1% in 24h**) | **Consecutive wins:** 2  
**Resting:** 2 MAKER orders, 15 SELL_EXIT orders | **Open positions:** 0

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 (lower, upper) | Status | ETA to threshold |
|------|---|------|----|-----|---------------------|--------|-----------------|
| BAND_YES | 6,044 | +45 | — | — | blocked (Gamma 403) | COLLECTING | n>>threshold; CI blocked |
| BAND_NO_PAIR_FAV | 253 | +10 | — | — | blocked (Gamma 403) | COLLECTING | n>>threshold; CI blocked |
| FILLED_VS_FIRED | 74 | +14 | — | — | blocked (Gamma 403) | COLLECTING | **~1.9d → Jul 2** |
| BASKET_EXIT | VOID | — | — | — | — | **VOID** | Permanently retired Jun22 |
| THERMO_MAKER_NO | 3 | +0 | 33.3% | −66.0% | (−132.6, +0.7) | COLLECTING | never (engine paused) |
| M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | (−20.6, +24.4) | **AMBIGUOUS** | never (stalled 18d) |
| SUM_POSTED 0.70–0.85 | 3,001 | +19 | — | — | blocked (Gamma 403) | COLLECTING | n>>threshold; CI blocked |

**Threshold:** BAND_YES/NO/SUM_POSTED = 100 legs per slice; FILLED_VS_FIRED = 40 watch / 100 decision; THERMO = 20 kill; M1_BETA = 100.

---

## State Transitions vs Prior Run (2026-06-29T09:13Z)

**None.** No gate crossed READY or REJECTED. All statuses unchanged.

Structural blockers (identical to prior run):
1. **Gamma API 403 from cloud container** — ROI/CI blocked for BAND_YES, BAND_NO_PAIR_FAV, FILLED_VS_FIRED, SUM_POSTED. First-fire dedup counts are accurate; resolution truth is inaccessible.
2. **THERMO_MAKER_LIVE=False** — kill gate n=20 unreachable; rate=0 indefinitely.
3. **metar_lockout.jsonl candidates-only** — M1_BETA_LOCKOUT stalled 18 consecutive days; 0 placed orders.

---

## Gate Notes

### 1. BAND_YES — n=6,044 (+45) | COLLECTING
- +45 legs since prior: 16 from Jun29 14:47–22:40 UTC (4 events × 4–5 legs: Wuhan d+1, Wuhan d+1, Chengdu d+1, Chengdu d+0); 29 from Jun30 00:02–05:09 UTC (7 events: Chengdu d+1/d+0, Beijing d+2, Chengdu d+2, Wuhan d+2, London d+2, Munich d+2).
- Rate: ~32.7 legs/day (elevated vs prior 19/day — new d+1/d+2 windows opening throughout the day cycle).
- All fires within BAND_PX_CEIL constraints: d+0 sum=0.155–0.24 (below 0.25 cap), d+1/d+2 sum=0.57–0.768.
- Today's yes_capture_shadow: 29 records (d+2 Chengdu repeating — shadow-only, no capital deployed for YES yet per BAND_YES_LIVE_MIN_DOUT=2).
- **Resolution blocked.** CI cannot clear zero without Gamma access.

### 2. BAND_NO_PAIR_FAV — n=253 (+10) | COLLECTING
- +10 NO legs since prior: Jun29 PM — London d+1 @0.66, Munich d+1 @0.69, Wuhan d+1 ×3 @0.66–0.84, Chengdu d+1 ×2 @0.76–0.85, Beijing d+1 @0.68, Chengdu d+1 @0.85 (total 7 legs after 09:13 UTC); Jun30 AM — London d+1 @0.66, Munich d+1 @0.73, Beijing d+1 @0.66 (3 legs).
- 0 pair_fav fires since prior.
- All NO asks within [0.52, 0.85] band (BAND_NO_MIN/MAX), at d+1 only (BAND_NO_MIN_DOUT=1).
- **Resolution blocked.** Note: NO-starvation fix was Jun12; n=253 accumulates from then.

### 3. FILLED_VS_FIRED — n=74 (+14) | COLLECTING ⚠️ APPROACHING THRESHOLD
- +14 fills since prior (1 YES + 13 NO):
  - Jun29 09:14 London YES @0.45 (+$0.70), Jun29 10:47 Wuhan NO @0.70 (+$2.30), Jun29 13:03 Munich NO @0.65 (+$7.80), Jun29 13:07 Wuhan NO @0.84 (+$5.30), Jun29 13:53 Wuhan NO @0.69 (+$5.00), Jun29 14:28 Munich NO @0.84 (+$6.00), Jun29 16:58 Wuhan NO @0.71 (+$8.00), Jun29 18:07 Chengdu NO @0.74 (+$7.00), Jun29 18:29 Chengdu NO @0.84 (+$6.00), Jun29 18:31 Wuhan NO @0.81 (+$7.00), Jun29 21:25 Beijing NO @0.67 (+$8.00), Jun30 04:22 Munich NO @0.72 (+$6.50), Jun30 07:10 Munich NO @0.67 (+$8.00), Jun30 08:40 Beijing NO @0.65 (+$7.80).
- Rate: 14/day. **ETA to n=100: ~1.9 days (≈ Jul 2, 2026).**
- >40 watch threshold active. Exec Auditor should schedule VPS-side resolution join **immediately** — n=100 is 2 days away.
- Fill composition (recent): heavily NO-weighted (13/14 = 93%), prices 0.65–0.84. The single YES fill (London 0.45) is consistent with pair_fav or a rare YES fill.
- **Winner's-curse watch**: at n=100, compare filled-leg ROI vs all-fires ROI to detect adverse selection signal.

### 4. BASKET_EXIT — VOID
Permanently retired Jun22T07:35. 4 fatal structural flaws. No further reporting.

### 5. THERMO_MAKER_NO — n=3 resolved | COLLECTING
- No change. THERMO_MAKER_LIVE=False since Jun23 18:40. Rate=0.
- Prior stats: WR=33.3%, ROI=−66.0%, CI95=(−132.6, +0.7) — CI barely straddles zero at n=3; pure noise, not signal.
- Kill gate n=20 UNREACHABLE while engine is paused.
- thermo_maker.jsonl today: 9,641 candidate records, 0 fires/placed.
- Status will not change until engine re-activated.

### 6. M1_BETA_LOCKOUT — n=31 AMBIGUOUS ⚠️ 18 DAYS STALLED — HUMAN ACTION REQUIRED
- No change. metar_lockout.jsonl: 5,231 candidates today, 0 placed/fired.
- Prior stats: WR=74.2%, ROI=−0.6%, CI95=(−20.6, +24.4). CI straddles 0 → AMBIGUOUS.
- **Stalled 18 consecutive days** (prior noted 17). No new data accumulation. Gate threshold n=100 unreachable at rate=0.
- **Standing rule triggered Jun13**: stalled >2 weeks → REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5C floors.
- **Proposed Jun27, still unactioned as of Jun30 = day 18.** Every additional day without action is 24h of no M1 probe data.

### 7. SUM_POSTED 0.70–0.85 — n=3,001 (+19) | COLLECTING
- +19 legs since prior: Jun29 PM — Wuhan d+1 @sum=0.840 (4 legs), Wuhan d+1 @sum=0.847 (5 legs), Chengdu d+1 @sum=0.847 (5 legs) = 14 legs; Jun30 AM — Chengdu d+1 @sum=0.768 (5 legs) = 5 legs.
- n=3,001 >> threshold 100. Rate ~13.8 legs/day (slowed from prior 16.4/day; fewer bands in range today).
- Note: Jun30 d+2 fires (Beijing, Chengdu, Wuhan, London, Munich) all have sum_posted 0.57–0.68 — BELOW the 0.70 floor; not counted. Only Chengdu d+1 with sum=0.768 qualifies today.
- **Resolution blocked.** ROI/CI computation requires Gamma API.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run.** No parameter changes proposed.

### Standing Proposal (unchanged since Jun27, day 18):
**M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5C floors**
- Gate: M1_BETA_LOCKOUT
- Action: Set `METAR_LOCKOUT_TEMP_FLOOR = 0.5` (restore from thin-margin [0.2, 0.5) slice)
- Reason: n=31 AMBIGUOUS, CI straddles 0, stalled 18 consecutive days, no placed orders observed, standing rule requires REVERT at >2 weeks stalled
- Status: PROPOSED — human must implement; gatekeeper does NOT implement strategy code
- Standing since: 2026-06-27T10:30Z

---

## Advisory

1. **FILLED_VS_FIRED n=74 → n=100 in ~1.9 days (≈ Jul 2):** Exec Auditor must schedule VPS-side resolution join NOW. The cloud container cannot reach Gamma API. Without VPS-side join at n=100, winner's-curse detection is blind when it matters most.

2. **Bankroll +16.1% in 24h ($80.98 → $94.04):** Exceeds daily target pace (+16% = strong). Current performance is being driven by NO fills at 0.65–0.84 prices — these are high-quality fills (the upper end of the NO range). Monitor for reversion once tonight's bands settle.

3. **Capital at $94.04 = 31.4% above prior run ($80.98):** Approaching BAND_PHASE2_CAPITAL threshold ($600) is distant, but growth pace is healthy. Consecutive wins = 2 (heat-check state maintained).

4. **THERMO_MAKER_NO and M1_BETA_LOCKOUT both stalled indefinitely:** Two of 7 gates are permanently blocked without human intervention. Combined, they represent meaningful strategy surface area that is accumulating zero validation data.

5. **YES fires today are shadow-only (yes_capture_shadow, no capital):** 29 shadow YES records for Chengdu d+2 cycling through today. These are informational — BAND_YES_LIVE_MIN_DOUT=2 is functioning correctly, and live YES posts do appear at d+2 (7 new fires in Jun30 lite for target dates 2026-07-01/07-02).
