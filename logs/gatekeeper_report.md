# Klaus Gate-Keeper Report — 2026-06-23

**Run:** 2026-06-23T12:29:31Z (snapshot age <1h, fresh) | **Service:** active | **Capital:** $231.21  
**Prior run:** 2026-06-22T09:11:00Z | **Branch:** claude/find-lag-parameter-rFQ0N  
**Data source:** GitHub MCP API (git fetch timed out in container; all counts from direct reads of data-mirror branch)

---

## CONTEXT: Config Changes Since Prior Run

| Time (UTC) | Change | Gate Impact |
|---|---|---|
| Jun22 11:45 | P1 no_reserve 0.40→1.00 (NO-only until $600) — deploy PENDING user nod | YES fire rate will collapse post-restart |
| Jun23 06:12 | Phantom breaker fix (statusless dead-order leak) + 25-entry prune + restart | Cash gate unblocked; capital redeployed to resting favNO; NO-only live |

Post-restart STRUCT-BAND-Q tail (12:18–12:28 UTC): cap=$229–231, no_resv=1.00, posted=0, cash_preskip=0.  
`posted=0` with `cash_preskip=0` = capital fully deployed in resting NO orders, no new slots — healthy.

---

## GATE LEDGER

| Gate | n | n_prev | +since_prior | WR | ROI | CI95 | Status | Threshold | ETA |
|---|---|---|---|---|---|---|---|---|---|
| 1. BAND_YES | 5,676 | 5,419 | +257 | — | — | **BLOCKED** | COLLECTING | 100 ✓ | CI blocked (VPS join) |
| 2. BAND_NO_PAIR_FAV | 177 | 144 | +33 | — | — | **BLOCKED** | COLLECTING | 100 ✓ | CI blocked (VPS join) |
| 3. FILLED_VS_FIRED | 102 | 110 | −8 † | — | — | **BLOCKED** | COLLECTING | 40 ✓ | CI blocked (VPS join) |
| 4. BASKET_EXIT | 33 | 33 | 0 | 1.0 | +145.5% | — | **VOID** | retired | — |
| 5. THERMO_MAKER_NO | 3 | 3 | 0 | 33.3% | −66.0% | [−132.6%, +0.7%] | COLLECTING | 20 (kill) | INFINITE |
| 6. M1_BETA_LOCKOUT | 31 * | 31 | 0 | 74.2% | −0.6% | [−20.6%, +24.4%] | COLLECTING | 100 | INFINITE |
| 7. SUM_POSTED 0.70–0.85 | 2,824 | 2,643 | +181 | — | — | **BLOCKED** | COLLECTING | 100 ✓ | CI blocked (VPS join) |

† FILLED_VS_FIRED: net decrease because Jun19 fills (27) aged out of the 7d rolling window; new Jun22/23 fills only partially offset (+31). Jun20 count also dropped 37→25 (possibly closed positions pruned from rolling log). Structural YES/NO ratio flipped: prior YES 60% / NO 40% → current YES 41% / NO 59%.

\* M1_BETA n=31 provenance remains unverifiable — only 1 confirmed M1 trade in trades.jsonl. See Gate 6.

---

## GATE DETAILS

### Gate 1 — BAND_YES (COLLECTING, n=5,676 >> threshold 100)

Sources (band_struct_lite.jsonl, unique (cid, days_out) per reason=fire):
- Jun22 full day: 269 YES fires; +32 since prior run cutoff (prior had 237 through 08:58)
- Jun23 through 12:28 UTC: 225 YES fires (199 pre-restart 00:04–06:12 / 26 post-restart 06:12–12:28)

**Fire rate shift:** pre-restart era ~630/day → post-restart ~26/6h ≈ **104/day (↓87%)**. Caused by P1 no_reserve=1.00 allocating all cycle headroom to NO; YES orders can't clear the cash gate.

Gate already 57× above threshold. Rate collapse doesn't threaten threshold, but means future accumulation is much slower. **CI computation is the only remaining blocker** — Gamma API returns 403 from container. VPS must run `analysis/weather/band_resolution_join.py`.

### Gate 2 — BAND_NO_PAIR_FAV (COLLECTING, n=177 >> threshold 100) ⚠ URGENT

Sources (band_struct_lite.jsonl, unique cid per reason=fire_no/pair_fav/pair_samebucket):
- Jun22 full day: 18 NO fires; +14 since prior run cutoff (prior had 4 through ~09:11)
- Jun23 through 12:28 UTC: 19 NO fires (8 pre-restart / 11 post-restart)

**Fire rate post-restart:** ~11/6h ≈ **44/day (↑from prior ~20/day)**. NO-only mode is feeding this engine.

**This gate has been above threshold (n=100) since Jun20 — 3+ days — with the NO engine LIVE at BAND_NO_STAKE=$5/fire, no_reserve=1.00, ~44 fires/day.** The pre-registered gate has never had CI computed. Total capital exposure is real and growing. Resolution join on VPS is the most urgent missing step.

### Gate 3 — FILLED_VS_FIRED (COLLECTING, n=102 >> threshold 40)

Sources (maker_fills_recent.log, unique (tok_partial[:12], side) from [MAKER-FILL] registered lines):
- Jun20=25, Jun21=40, Jun22=23 (NO=20/YES=3), Jun23=14 (NO=14/YES=0)
- Jun19 fills (27) aged out of 7d window

**Structural shift:** YES fills have nearly stopped (Jun22: 3, Jun23: 0) since NO-only mode. Winner's curse analysis is now predominantly a NO fill question. Prior YES adverse selection (~1.3c/sh vs badatmath) may not carry forward to NO fills.

Blocker: CID-resolution join required for ROI computation. VPS only.

### Gate 4 — BASKET_EXIT (VOID)

Retired Jun22T07:35 (4 fatal flaws confirmed). Status permanently VOID. n=33 archival.

### Gate 5 — THERMO_MAKER_NO (COLLECTING, STALLED, n=3)

n=3 resolved; kill gate = first 20 resolved. Zero new fills in 7d archive.  
Current CI95=[−132.6%, **+0.7%**] — barely straddles zero. One more losing fill flips CI fully negative → REJECTED at threshold.

thermo_maker.jsonl not present in dated shadow archive subdirectories (data/shadow/YYYY-MM-DD/); only in VPS hot logs. Large candidate row counts (26k-34k/day) but the prior state confirmed zero fire events. **THERMO engine appears silently stalled — no fires in 10+ days with large candidate pool.**

ETA: INFINITE at 0 fills/day.

### Gate 6 — M1_BETA_LOCKOUT (COLLECTING, STALLED, n=31*)

Zero new fires in 12+ days. metar_lockout.jsonl not in dated archives.  
Standing rule: at n>=100, WR>=95% AND +EV = keep; else REVERT to 0.5°C floors.  
CI95=[−20.6%, +24.4%] straddles zero — inconclusive even if basis is valid.  
**n=31 basis remains unverifiable** — only 1 confirmed M1 probe trade in trades.jsonl. VPS operator should verify; if unverifiable, reset to n=1.

ETA: INFINITE at 0 fires/day.

### Gate 7 — SUM_POSTED 0.70–0.85 (COLLECTING, n=2,824 >> threshold 100)

Sources (band_struct_lite.jsonl, unique (cid, days_out) per reason=fire where sum_posted ∈ [0.70, 0.85]):
- Jun22 full day: 184 sp_7085 fires; +23 since prior run (prior had 161 through ~09:11)
- Jun23 through 12:28: 158 sp_7085 fires (70.2% of 225 YES fires)

Fraction stable and rising: Jun17 47% → Jun19 64% → Jun23 70%. Post-YES-collapse the fraction holds.

CI blocker: same as Gate 1. Clean-window boundary Jun19T00:30 UTC still valid.

---

## STATE TRANSITIONS VS PRIOR RUN

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| BAND_YES | COLLECTING | COLLECTING | none |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | none |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | none |
| BASKET_EXIT | VOID | VOID | none |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | none |
| M1_BETA_LOCKOUT | COLLECTING | COLLECTING | none |
| SUM_POSTED_0.70_0.85 | COLLECTING | COLLECTING | none |

**Zero transitions this run.** Every gate that has exceeded its n-threshold remains COLLECTING because `band_resolution_join.py` has never been executed on the VPS. This is the third consecutive run with this finding.

---

## PROPOSED ACTIONS (human review — REPORT ONLY, no code changes)

### ACTION 1 [URGENT] — Execute VPS resolution join

Gates 1, 2, 3, and 7 are all above their n-threshold. None can produce a CI verdict without Gamma API access, which the container cannot reach (403). The VPS has this access.

```bash
# On the VPS:
cd /root/Klaus
# Set up layout the join script expects:
for D in 2026-06-18 2026-06-19 2026-06-20 2026-06-21 2026-06-22 2026-06-23; do
  mkdir -p logs/shadow/hot/$D
  # band_struct_lite.jsonl is at data/shadow/$D/band_struct_lite.jsonl on the VPS
  cp data/shadow/$D/band_struct_lite.jsonl logs/shadow/hot/$D/band_struct.jsonl 2>/dev/null
done
python3 analysis/weather/band_resolution_join.py
```

Priority order for the join: Gate 2 (NO engine fully live, $5/fire, 44 fires/day, zero CI) > Gate 1 (YES engine slower but large n) > Gate 7 (slice analysis) > Gate 3 (fill comparison).

### ACTION 2 [WATCH] — Gate 5 (THERMO_MAKER_NO) at edge of kill

CI=[−132.6%, **+0.7%**] with n=3. One more loss = CI fully negative = recommended kill. If THERMO engine is silently broken (zero fires 10d), verify it's armed. If firing and losing: when kill threshold (n=20) is reached with CI<0, recommend disabling the thermo-maker-NO logic.

### ACTION 3 [PROVENANCE] — Gate 6 (M1_BETA) basis reset

If the 31-trade basis cannot be confirmed from trades.jsonl or VPS logs, reset Gate 6 to n=1 and note the reset date. The gate is stalled at zero fires regardless.

---

## ACCUMULATION RATES (post Jun23 06:12 restart)

| Gate | Post-restart rate | Pre-restart rate | Change |
|---|---|---|---|
| BAND_YES | ~104/day | ~630/day | **↓87%** |
| BAND_NO_PAIR_FAV | ~44/day | ~20/day | **↑120%** |
| FILLED_VS_FIRED (fills) | ~27/day | ~25/day | ~flat |
| SUM_POSTED 0.70–0.85 | ~73/day | ~350/day | **↓79%** |
| THERMO | 0/day | 0/day | stalled |
| M1_BETA | 0/day | 0/day | stalled |

---

*Anti-sycophancy check: No gates promoted. CI must clear zero; n=5,676 is not a substitute for a CI verdict. Gate 2 running live capital without validated CI is a risk fact, not a compliment.*
