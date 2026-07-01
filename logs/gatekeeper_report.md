# Gate-Keeper Report — 2026-07-01

**Run:** 2026-07-01T12:30Z (snapshot: 2026-07-01T12:22:38Z, age: 7 min ✓)
**System:** `active` ✓ | **Bankroll:** $91.72 (prior $94.04, −$2.32; capital deployed in 10 Jul01 fills)
**Prior run:** 2026-06-30T09:14:00Z | **Δt:** ~27.3h
**Structural blockers:** Gamma API 403 (cloud) blocks ROI/CI on BAND_YES / BAND_NO / FILLED_VS_FIRED / SUM_POSTED; THERMO paused (rate=0); M1_BETA stalled (rate=0).

---

## Gate Ledger

| Gate | n | +27h | WR | ROI | CI 95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| BAND_YES (per-slice d×off×band) | 6,081 | +37 | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403) |
| BAND_NO + PAIR_FAV | 262 | +9 | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403) |
| FILLED_VS_FIRED (n≥40 watch, n≥100 gate) | 86 | +12 | — | — | BLOCKED | **COLLECTING** | ~1d (Jul 2) |
| BASKET_EXIT | VOID | — | — | — | — | **VOID** | Permanently retired |
| THERMO_MAKER_NO (kill gate n=20) | 3 | 0 | 33.3% | −66% | [−132.6, 0.7] | **COLLECTING** | ∞ (engine paused) |
| M1_BETA_LOCKOUT (n=100; WR≥95%+EV) | 31 | 0 | 74.2% | −0.6% | [−20.6, 24.4] | **AMBIGUOUS** | ∞ (day 19 stall) |
| SUM_POSTED 0.70–0.85 | 3,019 | +18 | — | — | BLOCKED | **COLLECTING** | CI gate (Gamma 403) |

**n counts:** BAND_YES/NO/SUM = cumulative first-fire legs by unique cid. FILLED_VS_FIRED = cumulative registered positions since gate start (Jun 12). THERMO/M1_BETA = resolved outcomes joined from shadow logs.

---

## Delta Detail Since Prior Run (Jun 30 09:14Z)

### BAND_YES (+37 new YES-leg first-fires)
- **Jun 30 after cutoff (+9):** Chengdu d+2 fire — 5 new cids (mode shifted, new legs); Munich d+1 YES fire — 4 new cids.
- **Jul 01 (+28):** All d+2 fires for July 3 date (brand-new markets): London d+2 (4 legs), Munich d+2 (5), Beijing d+2 (5), Wuhan d+2 (5), Chengdu d+2 (5); Wuhan d+1 YES fire (4 legs).
- YES live only at d+2 (`BAND_YES_LIVE_MIN_DOUT=2`). City allowlist (5 cities) is active as of latest commit. YES shadow firing for d+2 London/Munich/Beijing/Wuhan/Chengdu confirmed.
- n >> per-slice threshold of 100. CI remains BLOCKED — resolution truth unavailable from cloud (Gamma 403 persists).

### BAND_NO + PAIR_FAV (+9 new first-fires)
- **Jun 30 after cutoff (+4):** London off=2 (0xe4d89c5f), Munich off=2 (0x65ee0ccd), Wuhan off=0 (0x3a7f6bce), Beijing off=0 (0x9dde45d1).
- **Jul 01 (+5):** Munich off=0 (0x3074cfe4, former YES shadow leg → first NO fire), Chengdu off=0 (0xc60aed6d), London off=0 (0x47ca59a6), Wuhan off=2 (0xc137df61); Chengdu d+0 PAIR_FAV (0x44ebc1ef, both legs filled, locked PnL $1.43).
- All within d+1/d+2 (`BAND_NO_MIN_DOUT=1`), BAND_NO_SKIP_OFF1=True active, prices 0.47–0.85.
- n=262 >> 100. CI BLOCKED.

### FILLED_VS_FIRED (+12 new registered positions; log has 49 [MAKER-FILL] lines)
- **Jun 30 after cutoff (+3):** London NO 0xdcce (0.64), Munich NO 0x65ee (0.83), London NO 0xe4d8 (0.84).
- **Jul 01 (+9):** Beijing NO 0x5ac9 (0.67), Munich NO 0x3074 (0.62), Chengdu NO 0x44eb (0.47 pair_fav), London NO 0x47ca (0.63), Chengdu YES 0x44eb (0.38 pair_fav), Wuhan NO 0x3a7f (0.71), Chengdu NO 0xc60a (0.74), Wuhan NO 0xc137 (0.82), Munich NO 0xda8c (0.64).
- **Jul 01 flag — Moscow NO 0xb234 (+1, 11:06 UTC):** Moscow is NOT in `BAND_CITY_ALLOW = {"chengdu","london","beijing","munich","wuhan"}`. This fill (0.93 → above NO_MAX=0.85) is from a pre-allowlist resting order. Count included (n=86 with Moscow) or n=85 without. Exec Auditor should verify and cancel any open Moscow orders.
- Current n: **86 fills** (74 prior + 12 new) / **85 ex-Moscow**.
- Rate: ~10.7/day. **ETA to n=100: ~1.3 days (≈ Jul 2 late).**
- **n >> 40:** Winner's-curse watch is ACTIVE. VPS-side resolution join must be run before Jul 3.
- Price anomalies in log: Chengdu NO @ 0.48 (Jun29, cond=0x664b7956) below BAND_NO_MIN=0.52 — probable pre-rule order; Moscow NO @ 0.93 above BAND_NO_MAX=0.85 and outside city allowlist.
- Fill avg NO price (ex-pair_fav): ~0.716. Fill avg pair_fav: YES 0.38 + NO 0.47.

### BASKET_EXIT
VOID — permanently retired Jun 22 (4 fatal structural flaws). Not revisited.

### THERMO_MAKER_NO (+0, rate=0)
Engine `THERMO_MAKER_LIVE=False` since Jun 23 18:40. No new fires. n=3 resolved (all from shadow log before pause). CI straddles zero at n=3 — noise only, not informative. Kill gate n=20 unreachable at rate=0. No change.

### M1_BETA_LOCKOUT (+0, rate=0, **day 19 stall**)
`metar_lockout.jsonl` absent from all shadow directories (data/shadow/, 2026-07-01/, 2026-06-30/). Engine is not logging candidates OR logs are not being captured by data mirror. n=31, CI=[−20.6, 24.4], WR=74.2%, ROI=−0.6% — AMBIGUOUS. CI straddles zero: cannot confirm or reject at current n.
- **Standing rule (Jun 13):** stalled > 2 weeks → REVERT `METAR_LOCKOUT_TEMP_FLOOR` to 0.5°C floors.
- **Proposed Jun 27:** REVERT action recommended (day 1).
- **Today (Jul 01):** Day 4 of unactioned proposal. Day 19 of zero accumulation.
- Gate n=100 is **unreachable** at current rate=0. Standing rule requires action.

### SUM_POSTED 0.70–0.85 (+18 new legs)
- **Jun 30 after cutoff (+4):** Munich d+1 fire (sum_posted=0.836, 4 legs).
- **Jul 01 (+14):** Beijing d+2 (sum_posted=0.775, 5 legs), Wuhan d+2 (sum_posted=0.835, 5 legs), Wuhan d+1 (sum_posted=0.83, 4 legs).
- London d+2 (0.585), Munich d+2 (0.645), Chengdu d+2 (0.625) were BELOW 0.70 floor — not counted.
- n=3,019 >> 100. CI BLOCKED (Gamma 403). The V3 gate extension was based on competitor's curve at n=46 TREND — our own curve needs resolution truth.

---

## State Transitions vs Prior Run

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| BAND_YES | COLLECTING | COLLECTING | None |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | None |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | None (approaching n=100) |
| BASKET_EXIT | VOID | VOID | None |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | None |
| M1_BETA_LOCKOUT | AMBIGUOUS | AMBIGUOUS | None (day 19 → proposal day 4) |
| SUM_POSTED 0.70–0.85 | COLLECTING | COLLECTING | None |

**No status changes this run.** All gates remain in prior status. Gamma 403 remains the primary structural blocker for 4 of 6 active gates.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.**

### Carry-over: M1_BETA_LOCKOUT — REVERT [day 4 of proposal, day 19 of stall]
- **Gate:** M1_BETA_LOCKOUT
- **Action:** Set `METAR_LOCKOUT_TEMP_FLOOR = 0.5` (revert from current sub-0.5°C thin-margin slice behavior)
- **Standing rule trigger:** Jun 13 (stalled > 14 days without reaching n=100)
- **First proposed:** Jun 27 (this run = day 4 unactioned)
- **Rationale:** n=31 AMBIGUOUS at day 19 stall; CI straddles zero; metar_lockout.jsonl absent from shadow directories; engine accumulates 0 placed orders per day. Gate n=100 unreachable at rate=0. Standing rule from Jun 09 mandates REVERT when n<100 data cannot be collected.
- **Human action required:** YES (gatekeeper is report-only)

---

## Advisory (non-gate items, for human awareness)

1. **FILLED_VS_FIRED approaching n=100 (ETA ~Jul 2):** Exec Auditor MUST schedule VPS-side resolution join before Jul 3 — Gamma API 403 blocks cloud-side join. Winner's-curse detection blind without it. The fills log shows 86 registered fills; the 7-day window will start losing Jun 28 fills on Jul 5.

2. **Moscow NO fill outside city allowlist (Jul 01 11:06, cond=0xb2342854, price=0.93):** Moscow is not in `BAND_CITY_ALLOW`. This fill (above BAND_NO_MAX=0.85) appears to be a pre-allowlist resting order that filled after the city restriction was deployed. Exec Auditor should: (a) check for any remaining open Moscow resting orders and cancel them; (b) determine if the pre-allowlist fill has a valid resolution to settle.

3. **Pair_fav working — locked $1.43 (Jul 01 ~07:00Z):** Chengdu d+0 pair 0x44ebc1ef: NO leg filled at 0.47, YES leg filled at 0.38, 9.5 shares, locked PnL = $1.43 (margin on completion). This is the first observed pair_fav completion in the fills log. Pair_fav NO at 0.47 is below `BAND_NO_MIN=0.52` — confirm pair_fav intentionally bypasses NO_MIN (it should per PAIR_FAV logic).

4. **Bankroll context:** $91.72 vs $94.04 prior (−$2.32). With 10+ fills active and resting NO orders (BAND_NO_STAKE=$5 each), capital is deployed. Not a realized loss — fills will settle as weather resolves. Daily start capital = $15.95 (likely reset from a different baseline).

5. **Chengdu NO 0.48 fill (Jun 29, cond=0x664b7956):** Below BAND_NO_MIN=0.52. This was likely a pre-Jun-12 order from the "NO starvation" era when floors were lower. No action needed unless similar fills appear post-Jun12.

6. **Gamma 403 blocker:** Now blocking 4 of 6 active gates' CI computation. This has been ongoing for multiple runs with no documented fix attempt. The VPS-side band_resolution_join.py route is the prescribed workaround — once run, it will unlock BAND_YES, BAND_NO, and SUM_POSTED CI simultaneously.

---
*Gate-keeper is REPORT ONLY. Human flips all flags. CI must clear zero before any READY verdict. n=40–99 is a trend, not a decision.*
