# Gate-Keeper Validation Report — 2026-06-14T10:23Z

**Snapshot age**: 20 min (2026-06-14T10:03:51Z) — VALID  
**System**: `klaus systemd: active` (uptime since 2026-06-12 19:23 UTC)  
**Capital**: $270.13  
**Prior run**: 2026-06-13T09:22:09Z  

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|------|---|------|----|-----|------|--------|-----------------|
| BAND_YES (all slices) | 2116 | +386 | — | — | — | COLLECTING† | N/A (resolution blocked) |
| BAND_NO + PAIR_FAV | 24 | +10 | — | — | — | COLLECTING | ~6d (~Jun 20) |
| FILLED_VS_FIRED | 122 | +6 | — | — | — | COLLECTING | n>40 ✓ but CI blocked |
| BASKET_EXIT | 56 | +18 | — | — | — | COLLECTING | ~2.4d (~Jun 16–17) |
| THERMO_MAKER_NO | 19 | +6 | — | — | — | COLLECTING | ~1d kill gate (Jun 15) |
| M1_BETA_LOCKOUT | 1 | 0 | — | — | — | COLLECTING | dormant |
| SUM_POSTED_0.70–0.85 | 761 | +108† | — | — | — | COLLECTING† | N/A (resolution blocked) |

†BAND_YES and SUM_POSTED_0.70–0.85: n-threshold is MET (≥100) for all live slices, but cannot advance
to READY/REJECTED/AMBIGUOUS because resolution truth is unavailable (Gamma API 403, CLOB API 403 —
persistent environment block). Held at COLLECTING pending resolution join fix.

†+24h for SUM_POSTED_0.70–0.85 uses sum_ask [0.70,0.85] for continuity with prior state (n=284→392).
Proper metric (sum_posted ∈ [0.70,0.85]) gives n=761 across 6 days of post-V3 shadow data.

---

## State Transitions vs Prior

**No gate transitions this run.** All gates carry forward COLLECTING status.

Primary blocker: **Gamma API 403 + CLOB API 403** — both blocked from this container's IP address (Cloudflare WAF). This is the same blocker as the prior run. Resolution joins CANNOT be executed here. The canonical validator (`analysis/weather/band_resolution_join.py`) was called but timed out after 120s (Gamma 403 on first fetch). No fallback is used — resolution truth = Gamma winner flags, period.

---

## Per-Gate Detail

### GATE 1 — BAND_YES  *(scale-up gate, state_log 2026-06-11)*

**Method**: first-fire dedup per (cid, days_out, side) from `band_struct_lite.jsonl` across Jun 9–14.  
2889 raw YES fire-legs → **2116 deduped YES legs** (1256 unique markets).

Per live-posted slice counts (d≤2, off≤1 — the actual live posting rules):

| days_out | offset | n | ≥100? |
|----------|--------|---|-------|
| 0 | 0 | 150 | ✓ |
| 0 | 1 | 261 | ✓ |
| 1 | 0 | 175 | ✓ |
| 1 | 1 | 329 | ✓ |
| 2 | 0 | 205 | ✓ |
| 2 | 1 | 362 | ✓ |

**All live-posted slices ≥ 100 (min = 150 at d=0/off=0).** Threshold is comprehensively met.  
Top price-band slice: d=2, off=1, pb=[0.10–0.20] at n=184 (was 145 in prior note).  
Shadow also logs off=2 (n=634 total) for potential future wing re-evaluation; d=0 off=2 = n=69 (below 100).

**Resolution**: 0 resolved — Gamma 403 blocks all joins.  
**Rate**: 443 deduped YES legs/day (all live slices combined).  
**+24h**: +386 deduped YES legs (1730→2116 since 09:22 yesterday).  
**Status**: COLLECTING — fire count sufficient; resolution unavailable.

---

### GATE 2 — BAND_NO + PAIR_FAV  *(threshold n=100, accumulation from 2026-06-12 fix)*

**NO legs**:
- 101 total deduped fire_no records
- **77 pre-fix (excluded)** — Jun 11 + early Jun 12 before NO-starvation fix (2026-06-12 13:05 UTC)
- **24 post-fix** (Jun 12: 3, Jun 13: 14, Jun 14: 7)

**PAIR_FAV legs**: **0 across all 6 days** — `BAND_PAIR_FAV_ENABLED=True` but zero `pair_fav` reason records in shadow. No converged-ladder pair fires observed in the data window.

**n = 24 (post-fix NO only)**  
**+24h**: +10 (was 14, now 24)  
**Rate**: 12.6/day  
**ETA**: (100−24)/12.6 = **6.0 days → ~Jun 20**  
**Resolution**: 0 resolved — Gamma blocked.  
**Status**: COLLECTING.

Note: `BAND_NO_CASH_RESERVE=0.50` splits the free-cash pool 50/50 between YES and NO. The 2026-06-14 audit proposed reverting to 0.0 (Tier-2) to unify the pool and potentially double NO fire rate (~12→~25/day, cutting ETA to ~3d). Not yet applied; remains a human decision.

---

### GATE 3 — FILLED_VS_FIRED  *(watch threshold n=40 filled)*

From `maker_fills_recent.log` (Jun 11–14 rolling window):  
- **127 MAKER-FILL events** / **122 unique condition IDs**
- YES fills: 91 | NO fills: 36
- Date range: Jun 11 10:39 → Jun 14 10:08

**+24h**: +6 unique CIDs (was 116)  
**Watch threshold (n=40)**: MET — winner's-curse watch item active.  
**Resolution**: Gamma 403 blocks join → divergence metric uncomputable.

**Critical artifact**: `trades.jsonl` WEATHER_MAKER exit records (n=9) show 5 STWA_RESOLVED exits at exit_price=0.00 (all losses) + 4 BAND_MERGE exits (all wins). This data is **BIASED TOWARD LOSERS** — winning positions are harvested via RECYCLE099 at 0.99 (recorded in `exit099_live.jsonl`, excluded from `trades.jsonl` WEATHER_MAKER path). Any `trades.jsonl`-based ROI for this gate would severely understate actual fill ROI. Canonical join (Gamma winner flags × fire log) is the only valid approach.

**RECYCLE099 context** (not a gate metric, but the directional profitability signal): 45 exits across Jun 9–14, total PnL +$196.05. This is the strongest available evidence that YES legs are resolving correctly; it does not meet CI gate standards.

**Status**: COLLECTING.

---

### GATE 4 — BASKET_EXIT  *(threshold n=100 basket-days)*

From `basket_exit_shadow.jsonl` (logger started 2026-06-12 06:14 UTC):

| Metric | Value |
|--------|-------|
| Total basket-days observed | **56** |
| Prior run | 38 (+18) |
| Resolved (t_close < now) | 32 |
| Ever all_green | 27 |
| Resolved AND all_green | **15** |

**+24h**: +18 basket-days  
**Rate**: ~18/day  
**ETA to n=100**: (100−56)/18 = **~2.4 days → ~Jun 16–17**

**Metric** (cash-out vs hold for all_green resolved baskets): **uncomputable** — need Gamma resolution flags to determine whether held legs actually won. The `max_hold` field ($1/sh × shares) is the theoretical max; actual hold outcome requires external resolution truth.

15 all_green resolved baskets have accumulated — these will be the first cohort for the cash-out analysis once Gamma access is restored or the join runs from the VPS directly.

**Status**: COLLECTING (n < 100; metric uncomputable).

---

### GATE 5 — THERMO_MAKER_NO  *(pre-registered kill gate: first 20 resolved)*

From `thermo_maker.jsonl` (today's snapshot, 10,954 rows, 79 distinct city/date/bucket events):

- **19 candidates** with `end_date < 2026-06-14` (past resolution time):
  - Dallas Jun 13: 2 candidates (buckets 38.6°C, 39.7°C) — no_ask=None (orders not fetchable at snapshot time)
  - San Francisco Jun 13: 4 candidates (27.5–30.8°C) — no_ask=None
- **+24h**: +6 (was 13; prior run covered pre-Jun-13 candidates)
- **Actual bets placed**: estimated ≤ 7–10 (cap = 3 posts/day × ~2.5 days since Jun 11 22:40)
- **WR/ROI**: uncomputable — Gamma 403 blocks resolution join

**Kill gate status**: n=19 candidates logged past resolution date. The gate counts actual **placed-and-resolved** NO bets, not monitored candidates. True placed count is bounded by daily cap and likely ≤ 10. Resolution join is required to verify outcomes and compute WR.

At current rate (+6 candidates/day with end_date passing), 1 more calendar day pushes logged candidates past 20. Whether actual resolved *bets* reach 20 is separate and depends on fill rate.

**Status**: COLLECTING — one step below kill threshold on candidates; actual resolved bets likely fewer.

---

### GATE 6 — M1_BETA_LOCKOUT  *(threshold n=100 lockout trades)*

- **metar_lockout.jsonl**: 0 rows across all 6 shadow days — strategy not firing
- **trades.jsonl**: 1 WEATHER/Moscow/M1_BETA_PROBE trade (BUY_YES @0.80, net_pnl=−$1.65, Jun ~2026-05-26 by trade_id timestamp)
- **+24h**: 0 (no new M1 probe trades or lockout records)

**Status**: COLLECTING — strategy dormant; thin-margin [0.2,0.5)°C slice probe not accumulating.

---

### GATE 7 — SUM_POSTED_0.70–0.85  *(threshold n=100, V3 gate extension slice)*

Two counting methods (both well above threshold):

| Metric | n | Notes |
|--------|---|-------|
| sum_ask ∈ [0.70,0.85] | **392** | Consistent with prior run n=284; sum_ask includes wings not posted |
| sum_posted ∈ [0.70,0.85] | **761** | Correct V3 metric; 368 pre-V3 legs lack sum_posted field |

**+24h**: +108 (sum_ask basis, for prior continuity)  
**Rate** (sum_posted): ~159/day  
**Resolution**: 0 resolved — Gamma 403 blocks join.  
**Status**: COLLECTING — n-threshold comprehensively exceeded; same resolution block as GATE 1.

Context: V3 (Jun 11) raised BAND_SUM_MAX 0.70→0.85. Gate 7 tracks whether the new [0.70,0.85] zone (badatmath's full-hist: +13% ROI at n=46 trend) holds for OUR fires. Without resolution, fire counts are available but outcome distribution is unknown.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.**

Resolution truth is unavailable for all gates. The n-threshold for GATE 1 (BAND_YES, all live slices) and GATE 7 (SUM_POSTED) is comprehensively met and the system is staged to deliver a READY or REJECTED verdict the moment Gamma API access is restored. All other gates remain below their n-thresholds regardless of resolution.

**The single action that would unlock all six resolution-dependent gates simultaneously**: run `analysis/weather/band_resolution_join.py` directly on the Klaus VPS (which has QuantVPS Dublin IP not blocked by Cloudflare) and push results to the data-mirror branch. The cron agent in this container cannot do this.

---

## Risk Flags (not gate transitions — for human awareness)

**1. KILL SWITCH STALE** *(surfaced 2026-06-14 05:55 UTC audit, Tier-3 action)*  
`daily_start_capital=$15.95` vs current capital $264 → the −$10/day halt fires only at $5.95, which is ~$258 below current capital. `ruin_floor=0` is also stale. Both guards are effectively disabled at current capital. Re-anchoring to current capital is a pre-requisite for any scaling decision.

**2. Gamma/CLOB 403 is the gate system's persistent blocker**  
Same 403 block in every gatekeeper run since inception. Gates 1, 3, 7 are fully staged (n >> threshold) and would likely produce actionable verdicts on first successful resolution join. Fix requires running the join from the VPS directly, not from this container.

**3. PAIR_FAV accumulation = 0**  
6 days of shadow data with `PAIR_FAV_ENABLED=True`, zero pair_fav fires. Gate 2 accumulates only via NO legs. Current evidence: no converged ladders have met the [0.45,0.70] YES ask window + Σ ≤ 0.90 condition simultaneously in the data window.

**4. Cash-saturation binding constraint limits gate accumulation rates**  
2026-06-14 audit: free USDC ~$45, resting bids ~$37–73, effective YES cap ~$1.61/cycle → posted=0 in ~90% of cycles. This directly limits NO and YES fire accumulation rates. Gate 2 ETA (~6d) and Gate 4 ETA (~2.4d) both depend on maintaining current posting rates.
