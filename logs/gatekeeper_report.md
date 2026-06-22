# Klaus Gate-Keeper Report
**Run:** 2026-06-22T09:11:00Z | **Snapshot age:** 0.2h (FRESH) | **System:** `klaus systemd: active`
**Branch:** `claude/find-lag-parameter-rFQ0N` | **Capital:** $232.59 | **Prior run:** 2026-06-21T09:20:00Z

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1. BAND_YES (scale-up gate) | 5,419 | +265 | — | — | blocked | COLLECTING | Blocked (Gamma 403) |
| 2. BAND_NO + PAIR_FAV | 144 | +16 | — | — | blocked | COLLECTING | Blocked (Gamma 403) |
| 3. FILLED_VS_FIRED (winner's curse) | 110 | +2 | YES 60% / NO 40% | — | blocked | COLLECTING | Blocked (CID join) |
| 4. BASKET_EXIT ⚠ FATALLY FLAWED | 33 | +17 | 100%* | +145.5%* | [−45.1%, +336.1%] | VOID† | Gate retired |
| 5. THERMO_MAKER_NO (kill gate n=20) | 3 | +0 | 33.3% | −66.0% | [−132.6%, +0.7%] | COLLECTING / STALLED | INFINITE (0 fills/day) |
| 6. M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | COLLECTING / STALLED | INFINITE (0 fires/day) |
| 7. SUM_POSTED 0.70–0.85 | 2,643 | +170 | — | — | blocked | COLLECTING | Blocked (Gamma 403) |

*Gate 4 asterisks: WR=100% and ROI are artifacts of circular construction; see fatal-flaw audit below.
†Gate 4 VOID per state_log 2026-06-22T07:35 — four independent fatal errors, superseded by RECYCLE099.

---

## Gate Narratives

### Gate 1 — BAND_YES (scale-up gate)
**n = 5,419** (+265 since prior run)

Leg-level count: unique `(cid, days_out)` from `quotes[]` inside `reason=fire` events across `band_struct_lite.jsonl` files.

| Day | Legs fired |
|---|---|
| Jun 17 | 679 |
| Jun 18 | 629 |
| Jun 19 | 230 |
| Jun 20 | 260 |
| Jun 21 | 234 (prior had 206 through 09:20; +28 remainder this run) |
| Jun 22 | 237 (through 08:58 UTC snapshot) |

Rate: ~235 legs/day. Threshold for CI requires n=100 **resolved** per slice (days_out × offset × price band). The 5,419 fired legs need Gamma winner-flag resolution joins to compute per-slice ROI — blocked by Gamma 403 from container. VPS must run `analysis/weather/band_resolution_join.py`. CI blocked, gate remains **COLLECTING**.

---

### Gate 2 — BAND_NO + PAIR_FAV
**n = 144** (+16 since prior run)

Dedup: unique `cid` from `reason=fire_no / pair_fav / pair_samebucket` events.

| Day | Count |
|---|---|
| Jun 17 | 10 |
| Jun 18 | 22 |
| Jun 19 | 15 |
| Jun 20 | 13 |
| Jun 21 | 29 (prior had 17; +12 remainder this run) |
| Jun 22 | 4 (through 08:58 UTC, day is early) |

**n crossed 100 on Jun 20** (first flagged in prior run Jun21T09:20). CI still blocked by Gamma 403. Rate: ~14–20/day. BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 LIVE. Gate has been above threshold for **2 consecutive runs without a CI verdict**. VPS must run resolution join immediately — the NO engine is running live against an unvalidated edge gate.

---

### Gate 3 — FILLED-vs-FIRED divergence
**n = 110** (+2 fills since prior run, 7d rolling window)

Source: `maker_fills_recent.log`, parsed `[MAKER-FILL] registered` lines, deduped by `(token_partial, side)`.

- YES fills: 66 (60.0%) — up from 60 (55.6%)
- NO fills: 44 (40.0%) — **down** from 48 (44.4%)

NO fill rate regressed from 44% (prior, Jun21T09:20) to 40% despite `favNO TOP priority` (Jun19T00:30 change). Jun22 partial day shows 1 YES / 5 NO (6 fills), so today's intraday rate is NO-heavy — the regression is a denominator effect from YES-heavy Jun19–20 days.

By day: Jun19=27, Jun20=37, Jun21=40, Jun22=6 (partial).

Resolution join (filled-leg ROI vs all-fires ROI per slice) remains **blocked from container**. VPS must execute before Jun18 fills age out of the 7d window (~4 days remaining). Gate **COLLECTING**.

---

### Gate 4 — BASKET EXIT ⚠ GATE RETIRED

**STATE_LOG ENTRY 2026-06-22 07:35 UTC declares Gate 4 fatally flawed. Four independent fatal errors:**

1. **Tautological WR.** `all_green` is defined as every leg bid > entry price → cash > cost → ROI > 0 **by construction**. Selecting `all_green=True` and reporting "WR=100%, beat cost" is circular. Not an edge signal.

2. **Not baskets.** 18/19 verified closers are `n_legs=1` — single cheap-YES legs that converged toward $1.00 (Denver +3087%, Beijing +509%, Wuhan +235%). These are RECYCLE099 winners relabeled as "baskets."

3. **CI internally inconsistent.** The prior report's "+22.7% mean / CI[+11.5%, +34.0%]" is incompatible with Denver (+3087%) and Beijing (+509%) being in the n=16 sample (which forces mean ≥ 200%). CI was computed on a different, likely winsorized subset. On n=33 verified baskets (this run): mean=+145.5%, std=537.5%, CI95=**[−45.1%, +336.1%]** — straddles zero, dominated by two outliers.

4. **Wrong metric.** Decision-relevant is exit-vs-hold, not exit-vs-cost. Among verified closers: cash/max\_hold median = 0.920; **0/19 have cash ≥ max\_hold**. Holding the winning leg always pays more than the mirror-bid cash-out. Denver: cash=$38.24 vs hold=$40.00 = early exit **donates $1.76**.

**Disposition:** Gate 4 is **VOID**. Redundant with RECYCLE099 (which harvests convergence at ~0.99≈par vs basket-exit's ~0.92×max\_hold = strictly worse). Do not build a basket-exit executor. Do not promote at n=100. No flag/param change warranted.

Physical n=33 (+17 from prior 16) for archival record only.

---

### Gate 5 — THERMO UPPER-TAIL MAKER-NO
**n = 3** (+0, **STALLED 10+ days**)

Kill gate threshold: n = 20 resolved.

3 resolved legs: +$0.11@0.98 (ROI+2%), −$5.67@0.81 (ROI−100%), −$5.39@0.98 (ROI−100%).
WR = 1/3 = 33.3%, ROI = −66.0%, CI95 = [−132.6%, +0.7%] (barely straddles zero — one more adverse fill pushes CI fully negative).

`thermo_maker.jsonl` today: 9,099 candidate rows with record_type=`thermo_maker_candidate` — **zero fire records** across all available days. No fills above `BAND_NO_MAX=0.85` in `maker_fills_recent.log`. Fill rate = 0/day.

Gate **STALLED / COLLECTING**. ETA to kill threshold n=20: **INFINITE** at current fill rate.

---

### Gate 6 — M1-BETA LOCKOUT SLICES
**n = 31** (+0, **STALLED 12+ days**)

Source: `metar_lockout.jsonl`. Candidate rows today: 6,132 — **zero fire records** across all available days (Jun17–22 per-day files all empty/missing). Thin-margin [0.2, 0.5)°C slice produces no fires.

**Provenance flag (reproduced from prior):** n=31 basis unverifiable from available data. Only 1 confirmed M1-style WEATHER trade visible in `trades.jsonl` (May-26, Moscow). VPS operator: verify the 31-trade basis; if unverifiable, reset to n=1.

CI95 = [−20.6%, +24.4%] (straddles zero, reproduced from prior state). Standing rule from 2026-06-09: at n≥100, WR≥95% AND +EV = keep; else **REVERT to 0.5°C floors**. Cannot evaluate. Gate **STALLED / COLLECTING**.

---

### Gate 7 — SUM-POSTED 0.70–0.85 Slice
**n = 2,643** (+170 since prior run)

Unique `(cid, days_out)` YES legs from `reason=fire` where `band sum_posted ∈ [0.70, 0.85]`.

| Day | Count | % of YES fires |
|---|---|---|
| Jun 17 | 316 | 47% |
| Jun 18 | 282 | 45% |
| Jun 19 | 147 | 64% |
| Jun 20 | 172 | 66% |
| Jun 21 | 135 (prior had 126; +9 remainder this run) | 58% |
| Jun 22 | 161 (through 08:58 UTC) | 68% |

Fraction trending up (47%→68%) post-Jun18 config (PX_CEIL 0.30 + strict-rank queue). Rate: ~155/day. Same Gamma 403 blocks CI computation. Clean-window boundary: Jun19T00:30 UTC (same as Gate 1). **VPS resolution join needed.** Gate **COLLECTING**.

---

## State Transitions vs Prior Run (2026-06-21T09:20Z)

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| 1. BAND_YES | COLLECTING | COLLECTING | +265 legs; CI still blocked |
| 2. BAND_NO_PAIR_FAV | COLLECTING (n=128) | COLLECTING (n=144) | +16; **2nd run above n=100 with no CI — urgent** |
| 3. FILLED_VS_FIRED | COLLECTING (n=108) | COLLECTING (n=110) | +2 fills; NO rate regressed 44%→40% |
| 4. BASKET_EXIT | COLLECTING (n~72 est) | **VOID / RETIRED** | State_log 2026-06-22 07:35 — 4 fatal flaws; gate dropped |
| 5. THERMO_MAKER_NO | STALLED (n=3) | STALLED (n=3) | +0; CI upper barely positive |
| 6. M1_BETA_LOCKOUT | STALLED (n=31) | STALLED (n=31) | +0; provenance still unverified |
| 7. SUM_POSTED | COLLECTING (n=2473) | COLLECTING (n=2643) | +170; fraction of YES fires rising |

**No gates newly READY. No gates newly REJECTED.**

---

## PROPOSED ACTIONS (human review)

No gates newly READY or REJECTED this run. Three items require human attention:

### ACTION-A — VPS Resolution Join [Gates 1, 2, 7 — URGENT for Gate 2]
Gate 2 (BAND_NO_PAIR_FAV, n=144) has been above the n=100 threshold for **2 consecutive runs** without a CI verdict. BAND_NO is **LIVE at $5/stake**. Until Gamma resolution truth is established, the NO engine runs without a validated edge gate.

```bash
# On VPS — reconstruct layout for band_resolution_join.py
for D in $(ls logs/shadow/); do
  mkdir -p logs/shadow/hot/$D
  cp logs/shadow/$D/band_struct_lite.jsonl logs/shadow/hot/$D/band_struct.jsonl
done
python3 analysis/weather/band_resolution_join.py
```
The lite files preserve first-fire dedup + all posts. If script errors on layout, implement the join minimally against Gamma winner flags — never substitute price-drift for resolution truth.

### ACTION-B — Filled-vs-Fired Join [Gate 3 — TIME-SENSITIVE]
Jun18 fills age out of the 7d rolling window in ~4 days. n=110 fills (YES=66, NO=44) available. VPS must run the filled-leg ROI vs all-fires-ROI join per slice before that window closes.

### ACTION-C — Gate 4 Formal Close [Documentation]
Gate 4 has been declared void in state_log (2026-06-22 07:35). Recommend human confirmation that Gate 4 is dropped from the active ledger and no basket-exit executor will be built. No code/param change needed.

---

## Bankroll Context
Capital: $232.59 | Phase 1 (P2 threshold $600) | Total trades: 3,507 | Total PnL: +$34.78

---

*Gate-Keeper Validator — REPORT ONLY. No strategy code edited, no flags flipped.*
