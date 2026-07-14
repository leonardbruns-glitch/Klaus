# Gate-Keeper Ledger — 2026-07-14T09:15Z

**Run ts:** 2026-07-14T09:15:40Z  
**Snapshot ts:** 2026-07-14T08:59:16Z (age: 16 min — OK)  
**Snapshot commit:** ab7d1768c  
**Prior run ts:** 2026-07-13T09:00:00Z (+24h)  
**System:** `klaus systemd: active` — PASS  
**Bankroll:** $34.69 (prior: $87.40 → **−$52.71 / −60.3% in 24h**)  
**Band dark:** day 8 (BAND_LIVE=False since 2026-07-06T22:08Z)  

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (per slice) | 934 resolved | 0 | 15.3% | +4.0%† | [−10.9, +21.1] | **AMBIGUOUS** | ∞ (band dark) |
| G2a BAND_NO d+1/d+2 | 115 resolved | 0 | 68.7%‡ | +1.3% | [−11.9, +12.7] | **AMBIGUOUS** | ∞ (disabled) |
| G2b PAIR_FAV YES | 9 post-guard | 0 | — | — | — | **COLLECTING** | ∞ (band dark) |
| G2c PAIR_FAV NO | 9 post-guard | 0 | — | — | — | **COLLECTING** | ∞ (band dark) |
| G3 FILLED_VS_FIRED | 75 filled | 0 | 17.3% | −75.8% | [−75.0, −34.2] | **WATCH_ITEM** | n/a |
| G4 BASKET_EXIT | — | — | — | — | — | **VOID** | retired |
| G5 THERMO_MAKER_NO | 125 resolved | 0 | — | 0.0% | [−9.0, +2.0] | **REJECTED** | done |
| G6 M1_BETA_LOCKOUT | 31 resolved | 0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | done |
| G7 SUM_POSTED [0.70,0.85] | 382 resolved | 0 | — | +11.5%† | [−11.4, +38.9] | **AMBIGUOUS** | ∞ (band dark) |

† ROI is an **UPPER BOUND**, not an estimator — winner's curse confirmed (G3 WATCH_ITEM, state_log 2026-07-11 22:15Z). No gate may cite these values as re-enable evidence.  
‡ Shadow WR only; live n=51 WR=39.2% (effectively REJECTED per Jul-02 EVOLVE decision).

---

## State Transitions vs Prior Run

**None.** All 7 gates hold identical n, status, and CI from the 2026-07-13T09:00Z run.

- **Band dark day 8:** BAND_LIVE=False since Jul-06 22:08Z. Zero post records confirmed across all 6 daily band_struct_lite files (Jul-09 through Jul-14). Shadow fire events accumulate (~11–15 first-fire dedup'd fires/day in lite files) but these are counterfactual and carry the same winner's curse bias — they do not resolve and cannot advance any gate.
- **G3 WATCH_ITEM holds:** maker_fills_recent.log (Jul-11 through Jul-14) contains zero MAKER-FILL or STRUCT-BAND-Q entries. All 108 logged fill lines are UNTRACKED sprint/ladder/orphan-sell events. No new band-attributed fills.
- **G5/G6 REJECTED:** no new thermo or metar-lockout fills (services dark; only candidate records logged).

---

## Context Changes Since Prior Run (not gate transitions)

### Capital Erosion
- Prior bankroll: $87.40 (itself below ruin_floor $89.16)
- Current bankroll: **$34.69** (−$52.71 / −60.3% in 24h)
- Source per state_log: SPRINT_LADDER UNTRACKED taker fills + UPDOWN-SNIPER day-1 losses (−$4.29 true net after settle-bug fix)
- SPRINT_LADDER disarmed 2026-07-13T09:25Z (kernel floor breach; 0W/7L −$164.7 all-time)

### UPDOWN-SNIPER (not a canonical gate — context only)
- Went live 2026-07-13T10:46Z (owner "go live" = INVARIANTS #2 floor waiver recorded)
- Day-1 (true labels, post settle-bug-fix): 5 fires, 4W/1L, net −$4.29
- Settle-bug fixed 2026-07-13T22:05Z (84/196 prior resolution labels were wrong; day-1 corrected)
- SIG_FLOOR 0.5bp/√s deployed (removes σ-collapse fires; floored tape 6W/0L +$0.83 vs v1 7W/1L −$4.02)
- Both services restarted 22:06Z
- Pre-registered gate: n≥100 fill-sim offline → NOT YET MET (~24–36h from go-live = ~Jul-15 10:00Z)
- trades.jsonl: 0 closed sniper trades logged (orphan-sell entries only; sniper trades may be in separate shadow log)

### MIN_LOCKOUT_LIVE Revert
- Pre-registered revert condition fired: equity $34.86 = 15.6% of 30d-HW $222.90 < 50% rail
- MIN_LOCKOUT_LIVE set False 2026-07-13T22:08Z per EVOLVE commit
- 0 orders posted during 2d live window (engine ruin_floor $89.16 mechanically blocked all entries)
- G6 status unchanged (REJECTED since Jul-04); this revert has no gate impact

---

## Shadow Fire Accumulation (informational, not gate-advancing)

Band still dark → resolution data frozen. Shadow fires accumulate as counterfactual.

| Day | Band shadow fires (lite, dedup'd) | G7 [0.70–0.85] |
|---|---|---|
| 2026-07-09 | 16 | 13 |
| 2026-07-10 | 19 | 12 |
| 2026-07-11 | 18 | 13 |
| 2026-07-12 | 14 | 9 |
| 2026-07-13 | 11 | 9 |
| 2026-07-14 (partial ~9h, lite) | 7 | 6 |

Average rate when band live (historical): ~50 posts/day. At this rate:
- G2b/G2c pair n→100: ~8.3d from re-enable
- G7 resolved n already ≥ threshold (n=382); CI is the blocker, not count

---

## Structural Blockers (unchanged)

1. **WIND-DOWN active:** BAND_LIVE=False since Jul-06 22:08Z. All band gates frozen.
2. **Winner's curse CONFIRMED (G3):** sim ROI is UPPER BOUND. G1 +4.0% and G7 +11.5% are NOT valid re-enable evidence. Exception: co-filled PAIR (adverse selection only in naked leg).
3. **Pre-registered re-enable condition UNMET:** post-guard pair n≥40 required; current n=9 (frozen). Cannot re-enable without this.
4. **G2a BAND_NO:** live n=51 WR=39.2% effectively REJECTED (shadow AMBIGUOUS is irrelevant).
5. **Capital at $34.69:** below SPRINT_LADDER kernel floor $40, well below engine ruin_floor $89.16. UPDOWN-SNIPER is the only active live strategy.
6. **VPS join unconfirmed:** band_resolution_join.py join refresh since Jul-10 11:23Z unconfirmed (network-blocked in this sandbox; GitHub MCP used for data access). n=934/382 held. Flag for VPS operator.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run.**

All gates are frozen in their prior-run state. No flag or parameter change is proposed.

**Standing watch items (from prior runs, unchanged):**

- **[G3 WATCH_ITEM]** Winner's curse gap confirmed at n=75 filled (ROI −75.8% vs sim +7.6% = −83.4pp). Exec Auditor cross-tab of co-fill rate under Jul-05 clip-guard remains mandatory before any band re-enable discussion.
- **[CAPITAL CRITICAL]** $34.69 is 38.9% of engine ruin_floor $89.16. The only path that does not require a deposit is UPDOWN-SNIPER growing capital back. Monitor sniper gate (n≥100 fill-sim, target ~Jul-15 10:00Z).
- **[BAND RE-ENABLE BLOCKED]** Three independent blockers must ALL clear before band re-enable: (a) pair n≥40 post-guard, (b) winner's curse cross-tab closes, (c) explicit owner instruction. None are close.
