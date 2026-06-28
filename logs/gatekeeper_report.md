# Gate-Keeper Ledger — 2026-06-28T09:07Z

**Snapshot:** 2026-06-28T08:55:16Z (age: 0h ✓)  **System:** active ✓  
**Bankroll:** $79.19 | **Bot uptime since:** 2026-06-26T15:08:30Z (~42h continuous)  
**Prior run:** 2026-06-27T10:30Z

---

## Gate Ledger

| Gate | n | n_prev | +24h | WR | ROI | CI95 (%) | Status | ETA |
|---|---|---|---|---|---|---|---|---|
| BAND_YES (all slices) | 5978 | 5924 | +54 | — | — | BLOCKED | COLLECTING | CI-blocked¹ |
| BAND_NO + PAIR_FAV | 237 | 227 | +10 | — | — | BLOCKED | COLLECTING | CI-blocked¹ |
| FILLED_VS_FIRED | 47 | 37 | +10 | — | — | BLOCKED | COLLECTING | CI-blocked¹ |
| BASKET_EXIT | VOID | VOID | n/a | — | — | — | VOID | n/a |
| THERMO_MAKER_NO | 3 | 3 | +0 | 33.3% | −66% | [−132.6, +0.7] | COLLECTING | ∞ (paused)² |
| M1_BETA_LOCKOUT | 31 | 31 | +0 | 74.2% | −0.6% | [−20.6, +24.4] | AMBIGUOUS | ∞ (stalled)³ |
| SUM_POSTED [0.70–0.85] | 2964 | 2958 | +6 | — | — | BLOCKED | COLLECTING | CI-blocked¹ |

¹ Gamma API returns 403 from cloud sandbox — `band_resolution_join.py` cannot fetch winner flags. All BAND-family ROI/CI calculations remain blocked. n counts accumulate from shadow files only.  
² `THERMO_MAKER_LIVE=False` since 2026-06-23 18:40. Engine logs candidates only; 0 fills/day. n=3 < kill-gate threshold of 20. CI barely straddles 0 — *not* a green signal, just underpowered.  
³ `metar_lockout.jsonl` contains only `metar_lockout_candidate` records (4,321 today). No `placed` or `fired` records observed. M1β probe appears inactive. n frozen at 31 for 16+ consecutive days.

---

## State Transitions vs Prior Run

**No gates newly reached READY or REJECTED.**

Changes observed:
- **FILLED_VS_FIRED n=47 (crossed n≥40 watch threshold).** Was 37; +10 unique "registered" fills from maker_fills_recent.log (all Band-NO, plus 2 Band-YES: Munich and Chengdu). This is now inside the "winner's-curse watch item" zone (gate spec: n≥40 filled = Exec Auditor flag). No ROI computation possible without Gamma resolutions. The Exec Auditor should note this when it next runs.
- **BAND_NO_PAIR_FAV n=237 (+10).** Now >2× the 100-leg threshold; accumulating at ~10/day from the narrow-start NO overlay (d+1/d+2, off=0, 5-city allowlist).
- **BAND_YES n=5978 (+54).** Accumulating at ~54/day from shadow; narrow-start YES regime (d+2 only). No CI transition possible.
- **SUM_POSTED [0.70–0.85] n=2964 (+6).** Low rate consistent with narrow-start ~4–6 legs/day at sum_posted in the gate window.
- **M1_BETA_LOCKOUT:** now stalled 16 days (was 15 at prior run). No change in n, WR, CI, or status.

**VPS-side context (not updated this run — Gamma blocked):** Prior VPS run showed YES +7.6% at n=3,418 resolved (Jun17 entry). This is informational only; the cloud-side gate requires its own CI-clean join.

---

## Structural Blockers (all persistent from prior run)

1. **Gamma API 403 from cloud container** — ROI/CI blocked for BAND_YES, BAND_NO_PAIR_FAV, FILLED_VS_FIRED, SUM_POSTED. `band_resolution_join.py` times out on first network call. No workaround available in this environment. Needs VPS-side run or manual resolution pull.
2. **THERMO_MAKER_LIVE=False** — kill gate n=20 unreachable at rate=0. n stuck at 3.
3. **metar_lockout.jsonl candidates-only** — WEATHER_M1_PROBE inactive; n=31 frozen. Shadow logger runs but logs no placed orders.

---

## PROPOSED ACTIONS (human review)

No gates newly hit READY or REJECTED this run.

### Standing recommendation (prior run, still pending)

**Gate: M1_BETA_LOCKOUT**  
**Action:** REVERT `METAR_LOCKOUT_TEMP_FLOOR` from 0.2°C back to 0.5°C floor  
**Trigger:** Standing rule from 2026-06-09 — once n≥100: WR≥95% AND +EV = keep, else revert. Gate is AMBIGUOUS at n=31 (CI straddles 0: [−20.6, +24.4]) and has been frozen for 16 days with the logger producing zero placed-order records. The thin-margin [0.2, 0.5)°C slice is unvalidated and cannot accumulate evidence while the shadow logger logs candidates only.  
**Human action required — do NOT implement automatically.**

### Advisory (not a gate verdict)

**FILLED_VS_FIRED watch activated (n=47 ≥ 40):** The Exec Auditor should flag this on its next run. Once Gamma is reachable (VPS-side), compute filled-leg ROI vs all-fires ROI per slice to check for winner's curse (systematically filling on the worst legs). No action from this gate keeper — observation only.

---

## Gate-Keeper Notes

- All CI assertions use n ≥ threshold as prerequisite. No gate is near a verdict this run — every actionable gate is CI-blocked by Gamma 403, not by sample size.
- n counts are first-fire-deduped per (cid, offset) for YES; per (cid, offset) for NO. Sum_posted fires are deduped per (city, date) — one event per market. No fire-weighting.
- BASKET_EXIT is permanently VOID (state_log 2026-06-22T07:35 — tautological WR, wrong metric, CI invalid). Not revisited.
- THERMO CI barely not-rejected (upper bound +0.7% > 0) — this is noise at n=3, not a green signal. Kill gate is n≥20 resolved, which requires re-enabling the engine.
