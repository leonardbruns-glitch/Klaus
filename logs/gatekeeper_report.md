# Klaus Gate-Keeper Report — 2026-07-05

**Run timestamp:** 2026-07-05T09:30Z  
**Snapshot:** `data-mirror:81dab1e` — 2026-07-05T09:06:56Z (≤30min old ✓)  
**System:** `klaus systemd: active` ✓  
**Bankroll:** $115.99 cash (bankroll.json); daily_start $87.17; consecutive_wins 1  
**Prior run:** 2026-07-04T09:02Z (elapsed ~24.5h)  
**Resolution source:** EVOLVE VPS `band_resolution_join.py` — 2026-07-04 21:53Z (fires 23,179 raw → 1,221 deduped first-fire legs, 935 unique markets, 1,067 resolved). Cloud Gamma API still 403/timeout; VPS is sole resolution path.

---

## Gate Ledger

CI95 column: ROI confidence interval derived from Wilson 95% WR bounds mapped through ROI = WR/quote − 1 (monotonic transform). "BLOCKED" = Gamma 403 from cloud; VPS only.  
n column: n_resolved (for CI-computable gates) or n_fires (CI-blocked gates).

| Gate | n | +24h | WR | ROI | CI95 (ROI) | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1 BAND_YES (all) | 934 res | +5 est | 15.3% | +4.0% | [−10.9%, +21.1%] | **AMBIGUOUS** ↑ | CI must shift |
| 1a BAND_YES d+2 | 672 res | — | 14.4% | +5.4% | [−12.4%, +26.3%] | AMBIGUOUS | CI must shift |
| 1b BAND_YES d+1 | 190 res | — | 17.4% | +5.3% | [−23.0%, +41.8%] | AMBIGUOUS | CI must shift |
| 1c BAND_YES d+0 | 72 res | — | 18.1% | −7.8% | (n<100) | COLLECTING | ~2d to n=100 |
| 2a BAND_NO d+1 | 115 res | +0 | 68.7% | +1.3% | [−11.9%, +12.7%] | **AMBIGUOUS** ↑ | CI must shift |
| 2b PAIR_FAV YES | 9 res | +1 est | 55.6% | +20.7% | (n<40) | COLLECTING | ~15d to n=40 |
| 2c PAIR_FAV NO | 9 res | +1 est | 44.4% | +3.7% | (n<40) | COLLECTING | ~15d to n=40 |
| 3 FILLED_VS_FIRED | 24 fills | +3 est | — | — | BLOCKED | COLLECTING | ~2d to n=40 fills |
| 4 BASKET_EXIT | — | — | — | — | — | **VOID** | N/A — retired Jun22 |
| 5 THERMO_MAKER_NO | 125 ext | +0 | ≈mkt | EV ≈ 0 | n/a | **REJECTED** ↑ | N/A |
| 6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** ↑ | N/A |
| 7 SUM_POSTED 0.70–0.85 | ~3,056 fires | +20 est | — | — | BLOCKED | COLLECTING | VPS join needed |

↑ = status changed from prior run.

---

## Gate-by-Gate Notes

### Gate 1 — BAND_YES (YES legs per slice: days_out × offset × price band)

- **Fires (all-time):** ~6,158 est. (+5 pair_fav YES since prior; standalone YES paused BAND_YES_LIVE_MIN_DOUT=9 since Jul03 19:25). Only pair_fav YES accumulates (~2–3/day observed today).
- **Resolved (VPS):** 934 deduped first-fire legs. Threshold n=100 met long ago. CI is the gate.
- **d+2 (n=672):** WR=14.4% vs quote 0.137. ROI CI [−12.4%, +26.3%]. CI_lower < 0 → AMBIGUOUS.
- **d+1 (n=190):** WR=17.4% vs quote 0.165. ROI CI [−23.0%, +41.8%]. CI_lower < 0 → AMBIGUOUS.
- **d+0 (n=72):** WR=18.1%, ROI=−7.8%. n<100 → COLLECTING.
- **Status change: COLLECTING → AMBIGUOUS.** Prior status was COLLECTING because cloud Gamma 403 blocked CI entirely. EVOLVE VPS now provides CI. Status improvement is *data quality only* — CI straddles 0, no deployment action warranted.
- **CRITICAL CAVEAT (shadow/live divergence):** This join is conditional-on-fill at our shadow quotes. The same methodology showed +8% shadow while live fills realized −4.9% (Jun 18) and −45% (Jun 26–Jul 3 tape, −$137/$303 staked). AMBIGUOUS on shadow does NOT licence re-arming standalone YES. The standalone paused at Jul03 19:25 remains correct.
- **Band re-enable trigger:** disp_ratio 0.34 (d+2)..0.82 (d+0) vs 1.10 threshold — NOT MET, 7+ days.

### Gate 2 — BAND_NO + PAIR_FAV legs

**Sub-component 2a — BAND_NO d+1 (standalone NO):**
- n=115 resolved (EVOLVE VPS). WR=68.7% vs quote 0.678. ROI=+1.3%, CI [−11.9%, +12.7%]. CI straddles 0 → AMBIGUOUS.
- **Status change: COLLECTING → AMBIGUOUS.** Same data-quality upgrade as Gate 1.
- **CRITICAL — shadow/live divergence:** EVOLVE notes "Live favNO stays HALTED (07-02 rail: live n=51 WR 39.2% @ 0.655)." Shadow WR=68.7% vs live WR=39.2% at nearly identical avg quote (0.678 shadow, 0.655 live) is a winner's-curse signal of the first order. Live realized ROI ≈ −42% vs shadow +1.3%. **BAND_NO_ENABLED=False is the correct protection. Do NOT re-enable based on shadow CI.** This gate would be effectively REJECTED on live data.

**Sub-component 2b/2c — PAIR_FAV YES/NO:**
- n=9 resolved each (EVOLVE VPS). Both well below n=40 CI floor → COLLECTING.
- PAIR_FAV YES: WR=55.6%, avg quote 0.460, ROI=+20.7%. Promising point estimate but n=9 is noise.
- PAIR_FAV NO: WR=44.4%, avg quote 0.428, ROI=+3.7%. Positive but trivially small n.
- Fires growing at ~2 legs/day (pair_fav engine active; 2 pair_fav rows in today's band_struct through 09:07Z). ETA to n=40 resolved: ~15 days.
- +24h fires: +2 est. (today's band_struct shows 2 pair_fav rows total before 09:07 UTC).

### Gate 3 — FILLED_VS_FIRED (fill ROI vs all-fires ROI; winner's-curse watch)

- **n_fills (7d rolling tape):** 24 confirmed fills (exec_audit Jul 5 07:11Z: 24 fills in 3.5d effective window since log reset Jul 2 07:07Z; 16 registered + 8 maker_sh add-ons). Rolling fill rate ≈ 6.9/day.
- **+24h fills:** +7 (exec_audit 24h window: 6 YES, 1 NO; cities Munich/Seoul/Shanghai/Taipei/Tokyo/Wuhan).
- **Threshold:** n=40 fills for winner's-curse watch verdict. At ~6.9/day, ETA ≈ 2.3 days.
- **CI:** BLOCKED (Gamma 403 from cloud; EVOLVE VPS did not run a slice-level divergence join). Winner's-curse gap (filled vs all-fires ROI) uncomputed.
- **Status: COLLECTING** (n=24 < 40). Prior gate-3 n=112 was total fires; this run uses fills as the correct metric per gate definition.

### Gate 4 — BASKET_EXIT

**VOID** — permanently retired Jun22T07:35 (4 fatal structural flaws: tautological WR, wrong metric, invalid CI, single-leg artifact). Do not revisit.

### Gate 5 — THERMO_MAKER_NO (upper-tail maker-NO kill gate)

- **n=3 formal** (THERMO engine has been off since Jun23); n=125 external falsification join (Jul03 19:45 state_log + EVOLVE Jul04 21:53Z).
- **+24h:** +0. THERMO_MAKER_LIVE=False. Rate=0.
- **Status change: COLLECTING → REJECTED.** EVOLVE Jul04 21:53Z: "REJECTED — killed formally today. Flag already False since 06-23; n=20 kill gate pre-resolved by the n=125 falsification." At n=125 resolved candidates, WR tracks market price at every ask band; EV range −9..+2%/share ≈ 0. The pre-registered n=20 kill gate would have fired REJECTED. Engine is permanently paused.
- **Action already complete:** THERMO_MAKER_LIVE=False since Jun23 18:40; no flag change needed.
- **Residual:** prior proposed action was to set status VOID. REJECTED is the technically correct terminus per the kill-gate protocol (n≥20 would have REJECTED). Human may upgrade to VOID for clarity if preferred — semantics only.

### Gate 6 — M1_BETA_LOCKOUT (thin-margin [0.2, 0.5)°C slice)

- **n=31 resolved.** WR=74.2%, ROI=−0.6%, CI95=[−20.6%, +24.4%]. CI straddles 0 → AMBIGUOUS at n=31.
- **+24h:** +0. Rate=0. metar_lockout.jsonl now has 3,253 rows today (scanner running; was empty in prior days), but these are candidate evaluation records — zero trade fires. METAR_LOCKOUT_TEMP_FLOOR reverted to 0.5°C in commit 2813daa1e, removing the thin-margin [0.2, 0.5)°C slice from scope.
- **Status change: AMBIGUOUS → REJECTED.** EVOLVE Jul04 21:53Z: "REJECTED — param REVERTED 0.2→0.5°C today (commit 2813daa1e). 22-day stall, capacity zero." Revert was the standing proposed action from prior runs (7 days unactioned as of prior run); EVOLVE actioned it.
- **Action already complete:** METAR_LOCKOUT_TEMP_FLOOR=0.5°C in commit 2813daa1e. Human: verify revert is active in live config and acknowledge close of the 7-day standing item.
- **Residual — validated ≥0.5°C slice:** EVOLVE: "CAPACITY DEAD (07-03 sweep: 0 buyable asks; min-side only @0.999). Path stays armed, harvests nothing." Not a gate issue — market-efficiency issue. Standing item: monitor for capacity restoration.

### Gate 7 — SUM_POSTED 0.70–0.85 slice

- **n_fires (est):** ~3,056 (+20 est since prior; today's band_struct has 166 rows with sum_posted in [0.70, 0.85] through 09:07Z vs 2,843 total rows). Threshold n=100 met long ago.
- **CI:** BLOCKED. EVOLVE VPS Jul04 21:53Z did not run a slice-specific join for this sub-range. Same Gamma 403 cloud blocker as Gates 1–3.
- **Status: COLLECTING.** No resolution truth available; cannot compute ROI CI.
- **Rate:** ~20 fires/day in this sum-range. n is not the bottleneck; VPS slice-level join is.

---

## State Transitions vs Prior (2026-07-04T09:02Z)

| Gate | Prior Status | Current Status | Driver |
|---|---|---|---|
| BAND_YES | COLLECTING | **AMBIGUOUS** | EVOLVE VPS resolved 934 legs; CI straddles 0 |
| BAND_NO d+1 | COLLECTING | **AMBIGUOUS** | EVOLVE VPS resolved 115 legs; CI straddles 0 |
| PAIR_FAV YES/NO | COLLECTING | COLLECTING | n=9 res each; no change |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | 24 fills in tape; no resolution join |
| BASKET_EXIT | VOID | VOID | No change |
| THERMO_MAKER_NO | COLLECTING | **REJECTED** | EVOLVE Jul04 21:53Z formalized; n=125 EV≈0 |
| M1_BETA_LOCKOUT | AMBIGUOUS | **REJECTED** | EVOLVE Jul04 21:53Z; param reverted 2813daa1e |
| SUM_POSTED 0.70–0.85 | COLLECTING | COLLECTING | CI still blocked; VPS slice join not run |

**This run: 0 READY, 2 REJECTED (THERMO formalized, M1β reverted), 2 newly AMBIGUOUS (BAND_YES, BAND_NO).**

---

## PROPOSED ACTIONS (human review)

Gates newly hitting READY: **none.**  
Gates newly hitting REJECTED: **2 — actions already taken by EVOLVE.**

| Gate | Verdict | Exact flag/param | Action status |
|---|---|---|---|
| THERMO_MAKER_NO | **REJECTED** | `THERMO_MAKER_LIVE=False` — already set Jun23 18:40; no code change needed. Human may upgrade gate status to VOID (semantics only). | **Complete** (EVOLVE Jul04 21:53Z) |
| M1_BETA_LOCKOUT | **REJECTED** | `METAR_LOCKOUT_TEMP_FLOOR` reverted 0.2°C → 0.5°C — commit 2813daa1e already applied. Human: verify in live band_config.txt and acknowledge 7-day standing item closed. | **Complete** (EVOLVE commit 2813daa1e) |

**No gates require human flag changes. Review/acknowledge actions above.**

---

## Advisory (not gate verdicts)

1. **BAND_NO live/shadow gap is a winner's-curse signal:** Shadow n=115 WR=68.7% vs live n=51 WR=39.2% at comparable quotes. This gap is decision-grade evidence against ever re-enabling standalone band-NO. BAND_NO_ENABLED=False is correct indefinitely until live fills rebuild a clean tape.

2. **YES-CAPTURE shadow 0.30–0.45 d+2 (informational, not a pre-registered gate):** EVOLVE found n=398, +126% would-post ROI (after a 3-day analyzer cwd bug fix). Winner's-curse rule: cannot justify live without a fill-confirmed validation design. EVOLVE correctly flagged this as INFORMATIONAL ONLY.

3. **PAIR_FAV point estimates (n=9 each):** YES +20.7%, NO +3.7% — intriguing but statistically meaningless at n=9. No action until n=40+ resolved. Rate ~2/day.

4. **FILLED_VS_FIRED threshold approach:** n=24 fills, threshold=40. ETA ~2.3 days at 6.9/day. When crossed, EVOLVE should run a fill-vs-fire ROI comparison (not cloud-feasible due to Gamma 403 — VPS job).

5. **Sprint-30 (Day 2+):** equity ~$115.99 cash (bankroll.json). EVOLVE Jul04 21:53Z showed $125.56 with $51.11 in positions mark. Monitor-only per CHARTER; not a gate subject.

6. **EVOLVE daily schedule note (ESCALATIONS.md):** 4 of 5 daily slots Jul02–Jul04 died on session-limit before doing work. Jul04 21:53Z was the FIRST completed daily run. Today's scheduled slot (11:23 UTC) may or may not complete. If it completes, check gate_ledger_latest.md for updated PAIR_FAV n and a possible FILLED_VS_FIRED divergence check.

7. **BAND_YES re-enable trigger:** disp_ratio 0.34 (d+2)..0.82 (d+0) vs 1.10 threshold — NOT MET, 7+ consecutive days. Standalone YES band remains correctly paused.
