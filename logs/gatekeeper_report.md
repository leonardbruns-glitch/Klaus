# Gate-Keeper Report — 2026-07-02

**Run:** 2026-07-02T12:45Z (snapshot: 2026-07-02T12:39:09Z, age: 6 min ✓)
**System:** `active` ✓ | **Bankroll:** $79.04 (prior $91.72, −$12.68; 9 YES positions resting at 0.99 hold ~$45 deployed notional — not realized loss)
**Prior run:** 2026-07-01T12:30:00Z | **Δt:** ~24.25h
**Structural blockers:** Gamma API 403 (cloud) blocks ROI/CI on BAND_YES / BAND_NO / FILLED_VS_FIRED / SUM_POSTED; THERMO paused (rate=0); M1_BETA stalled Day 20 (rate=0); **NEW: BAND_NO_ENABLED=False (EVOLVE rail-halt, 2026-07-02 ~06:14Z).**

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI 95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| BAND_YES (per-slice d×off×band) | 6,114† | +33† | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403) |
| BAND_NO + PAIR_FAV | 266† | +4† | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403); **rate=0** (EVOLVE halt) |
| FILLED_VS_FIRED (watch n≥40; gate n≥100) | 97† | +11† | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403); n~97→100 est. Jul 3 |
| BASKET_EXIT | VOID | — | — | — | — | **VOID** | Permanently retired |
| THERMO_MAKER_NO (kill gate n=20) | 3 | 0 | 33.3% | −66.0% | [−132.6, 0.7] | **COLLECTING** | ∞ (engine paused) |
| M1_BETA_LOCKOUT (n=100; WR≥95%+EV) | 31 | 0 | 74.2% | −0.6% | [−20.6, 24.4] | **AMBIGUOUS** | ∞ (Day 20 stall) |
| SUM_POSTED 0.70–0.85 | 3,035† | +16† | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403) |

† Estimated from prior confirmed rate; Gamma 403 prevents direct computation from cloud.

---

## State Transitions vs Prior Run (2026-07-01T12:30Z)

| Gate | Prior Status | Current Status | Trigger |
|---|---|---|---|
| BAND_YES | COLLECTING | COLLECTING | No change; rate continuing |
| BAND_NO_PAIR_FAV | COLLECTING | **COLLECTING + rate=0** | **NEW: BAND_NO_ENABLED=False (EVOLVE rail-halt, Jul02 ~06:14Z)** |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | n approaching threshold; no CI unlock |
| BASKET_EXIT | VOID | VOID | No change |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | No change |
| M1_BETA_LOCKOUT | AMBIGUOUS | AMBIGUOUS | Day 20 stall; REVERT now Day 5 unactioned |
| SUM_POSTED 0.70–0.85 | COLLECTING | COLLECTING | BAND_NO halt does not affect YES leg count |

**No gates moved to READY or REJECTED this run.**

---

## New Events Since Prior Run

### 1. BAND_NO_ENABLED=False — EVOLVE Rail-Halt (2026-07-02 ~06:14Z) ★ KEY EVENT

EVOLVE v2's daily actuator triggered `BAND_NO_ENABLED=False` on 2026-07-02. Trigger condition: 7-day realized band-NO n=51, WR=39.2%, profit-factor rail breached. Bot restarted at 06:14 UTC today with NO overlay disabled.

**Gate implications:**
- Gate 2 (BAND_NO_PAIR_FAV): accumulation rate drops to 0 indefinitely. n=266 is the final count unless flag is re-enabled.
- PAIR_FAV (BAND_PAIR_FAV_ENABLED=True still set, but effectively halted — pair requires both YES and NO legs; NO disabled).
- EVOLVE's verdict (n=51 WR=39.2% PF breach) is an **independent rejection signal** for this gate. If Gamma 403 is ever resolved, this gate is expected to show REJECTED based on the same realized data EVOLVE used. No CI required to act: the live halt is already the correct response.

**Gate-keeper note:** The CI gate has not been formally computed (Gamma 403), but EVOLVE's realized-data trigger pre-empts the formal verdict. This is exactly what a guard rail should do — stop capital deployment before the gate keeper can compute on cloud-blocked data.

### 2. Bankroll −$12.68 in 24h ($91.72 → $79.04)

All 9 resting SELL_EXIT orders (sizes: 9, 9, 8, 8, 8, 8, 8, 7, 7 = 72 shares total) are YES positions resting at 0.99, matched=0. Capital is deployed, not lost. Five exit099 recycles completed today (Jul02 06:35–12:41 UTC):

| Token (short) | Shares | Entry | Exit | PnL |
|---|---|---|---|---|
| 1054...3421 | 5.0 | 0.71 | 0.99 | +$2.24 |
| 8764...9701 | 7.0 | 0.74 | 0.99 | +$1.75 |
| 1079...2141 | 6.0 | 0.82 | 0.99 | +$1.11 |
| 8014...7052 | 9.0 | 0.55 | 0.999 | +$4.04 |
| 5453...4324 | 7.0 | 0.64 | 0.99 | +$2.73 |

Today exit099 PnL: **+$11.87** across 5 recycles.

### 3. M1_BETA_LOCKOUT — Day 20 Stall, Proposal Day 5 Unactioned

metar_lockout.jsonl confirmed absent from all shadow directories (hot + 2026-07-02 through 2026-06-27 — 6 dated dirs checked). n=31, rate=0. The standing rule (triggered Jun 13: >14d stall → REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5C) was proposed Jun 27 and remains unactioned for **5 consecutive days**. This is now overdue by the standing rule.

### 4. FILLED_VS_FIRED — Approaching n=100 Threshold

Estimated n=97 (prior 86, rate ~10.7/day, 24.25h elapsed, +11 est. fills). Threshold n=100 expected ~Jul 3 morning. **However:** Gamma 403 blocks resolution join from cloud, so crossing n=100 will not unlock CI computation without a VPS-side resolution run. The threshold crossing is a counting milestone only — no verdict until VPS run.

### 5. No Change: Gamma 403 Cloud Blocker Persists

No evidence of Gamma API recovery in this run. 4 of 7 active gates remain CI-blocked. VPS-side `analysis/weather/band_resolution_join.py` run remains the single highest-leverage unblocking action.

---

## PROPOSED ACTIONS (human review required — gate keeper REPORT ONLY, never implements)

**No gates are READY or REJECTED by CI verdict this run.**

### Action 1 — M1_BETA_LOCKOUT: REVERT (URGENT — Day 5, Standing Rule)

> **Proposed flag change:** `METAR_LOCKOUT_TEMP_FLOOR = 0.5` (revert thin-margin [0.2, 0.5)C slice to 0.5C floor)

**Reason:** Gate n=31 AMBIGUOUS, rate=0, stalled 20 consecutive days. metar_lockout.jsonl absent from all shadow directories — no new observations are being logged. Standing rule from 2026-06-13: >14d stall with gate n=100 unreachable → REVERT. Current CI: WR=74.2%, ROI=−0.6%, CI95=[−20.6, 24.4] — straddles 0, no positive edge proven. Thin-margin slice has generated zero data for 20 days. Reverting eliminates unproven capital risk in [0.2, 0.5)C band.

**Proposal origin:** 2026-06-27 (Day 1). **Now Day 5 with no human action.**

### Action 2 — BAND_NO_PAIR_FAV: Advisory (No Flag Flip Needed)

EVOLVE independently halted BAND_NO (n=51 WR=39.2% PF breach, 2026-07-02). Gate 2 accumulation rate is now 0. This is the correct outcome — the EVOLVE guard rail pre-empted the formal gate rejection. **No additional flag change is required.** Human should note: if BAND_NO is ever re-enabled by a future EVOLVE actuator, Gate 2 CI must be re-evaluated before allowing accumulation to restart without prejudice.

### Action 3 — FILLED_VS_FIRED + All Gamma-Blocked Gates: VPS Resolution Join (Urgent)

> **Required action (Exec Auditor, VPS-side):** Run `analysis/weather/band_resolution_join.py` on VPS before 2026-07-03.

FILLED_VS_FIRED expected to cross n=100 by Jul 3 morning. Without VPS resolution data, the threshold crossing produces no verdict. Running the join would simultaneously unblock CI computation for **BAND_YES**, **BAND_NO_PAIR_FAV**, **FILLED_VS_FIRED**, and **SUM_POSTED_0.70_0.85** — 4 gates in one run. This is the single highest-leverage action available to the gate keeper system.

---

## Structural Blockers (all carry-forward)

1. **Gamma API 403 (cloud container)** — ROI/CI blocked for BAND_YES, BAND_NO, FILLED_VS_FIRED, SUM_POSTED. Fix: VPS-side resolution join.
2. **THERMO_MAKER_LIVE=False** — kill gate n=20 unreachable at rate=0. Paused since Jun 23.
3. **metar_lockout.jsonl absent** from all shadow directories — M1_BETA_LOCKOUT stalled since Jun 13.
4. **BAND_NO_ENABLED=False** (NEW, 2026-07-02) — Gate 2 accumulation halted. EVOLVE-triggered, not gate keeper action.

---

## Fill Anomalies (carry-forward, human review outstanding)

| Token | Price | Issue |
|---|---|---|
| Moscow NO 0xb2342854 | 0.93 | City NOT in BAND_CITY_ALLOW; above NO_MAX=0.85; pre-allowlist legacy. Check for remaining open Moscow resting orders — cancel if found. |
| Chengdu pair_fav NO 0x44ebc1ef | 0.47 | Below BAND_NO_MIN=0.52; pair_fav logic bypasses NO_MIN — verify intentional. Pair completed Jul01 (+$1.43). |
| Chengdu NO 0x664b7956 | 0.48 | Below NO_MIN=0.52; Jun12 starvation-fix era, pre-rule (grandfathered). |
