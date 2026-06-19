# Gate-Keeper Report — 2026-06-19

**Snapshot**: 2026-06-19T09:00:06Z (< 6h old ✓) | **System**: active ✓ | **Bankroll**: $249.75

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1. BAND_YES | 4643 | +271 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |
| 2. BAND_NO_PAIR_FAV | 90 | +8 | — | — | [Gamma 403] | COLLECTING | **~0.8d** (10 needed) |
| 3. FILLED_VS_FIRED | 291 | +9 | — | — | [CID join blocked] | COLLECTING | n>>40; join blocked |
| 4. BASKET_EXIT | 48 | +0 | — | — | [Gamma 403] | COLLECTING | ~2.7d (~19/day) |
| 5. THERMO_MAKER_NO | 3 | +0 | 33.3% | −64.7% | [−130%, +0.7%] | COLLECTING | STALLED (0 fills 7d) |
| 6. M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | COLLECTING | STALLED (0 fires 10d) |
| 7. SUM_POSTED_0.70_0.85 | 2174 | +155 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |

**No READY. No REJECTED. All gates COLLECTING.**

---

## Gate Detail

### Gate 1 — BAND_YES (scale-up gate)
- **n**: 4643 (+271 from prior 4372)
- **Sources**: Jun13=776 (prior), Jun14=809, Jun15=765, Jun16=800, Jun17=679, Jun18=629 (full day, was 543 at prior snapshot), Jun19=185 (partial to 09:00 UTC)
- **Cross-check**: Jun14-18 lite files yield 3682 legs; prior Jun14-18 was 3596 (delta +86 = Jun18 morning→full day +86, consistent)
- **Status**: n=4643 >> threshold 100, but **resolution truth is blocked** (Gamma API returns 403 from container). VPS-side `band_resolution_join.py` cron should be feeding resolved ROI — results are not appearing in data-mirror.
- **Rate**: ~271/day (Jun19 partial extrapolates to ~530/day at full run); accumulation is not the bottleneck.
- **No status change** from prior.

### Gate 2 — BAND_NO_PAIR_FAV
- **n**: 90 (+8 from prior 82)
- **Sources by day**:
  - Jun12 (~3, prior), Jun13 (15, prior) = 18
  - Jun14: fire_no=18; Jun15: fire_no=4; Jun16: pair_fav=11; Jun17: pair_fav=6 + pair_samebucket=4 = 10; Jun18: fire_no=20 + pair_samebucket=2 = 22 (was 0 at prior snapshot); Jun19 partial: fire_no=7
  - Total Jun14-19: 72; Grand total: 90
- **Note**: Jun18 prior showed 0 (before posting window). Full-day Jun18 = 22, which drove the +8 delta net.
- **Threshold**: 100. **10 more needed.** At ~12/day rate → **ETA ~0.8 days** (threshold likely crossed Jun19-20).
- **CI**: Gamma 403 blocks all resolution joins from container. VPS cron needed.
- **Methodology note**: "post records side=NO" from prior = now logging as reason=fire_no/pair_fav/pair_samebucket. Counting is consistent (dedup by cid+days_out per day). The Jun18 fire_no=20 surge coincides with BAND_NO_ENABLED=True + favNO promotion (config changes Jun18 21:55 UTC + 22:05 UTC).

### Gate 3 — FILLED_VS_FIRED
- **n**: ~291 (+9 from prior 282)
- **New Jun19 fills to snapshot**: YES=4, NO=5 = 9 registered positions
- **Jun17-19 tape**: Jun17=69 registered, Jun18=81 registered, Jun19=9 (to 09:00 UTC)
- **Note**: Jun16=77 from prior has aged out of the 7-day rolling log window. Prior Jun17 count discrepancy (prior=127 vs tape=69) suggests prior counted all MAKER-FILL lines including accumulating fills on existing positions; current count is "registered" (new position) events only.
- **Blocker**: CID join (truncated 8-char hex in log vs full 66-char conditionId in trades.jsonl) remains unresolved. Cannot compute filled-leg ROI vs all-fires ROI per slice.
- **YES/NO split (Jun17-19)**: YES=138, NO=21. NO share=13.2% of fills — much lower than 30-40% NO-reserve weight in the posting queue, suggesting NO fill-rate is still thin relative to YES despite priority.

### Gate 4 — BASKET_EXIT
- **n**: 48 (no confirmed change from prior)
- **Available data**: Jun15 per-day file = 19 resolved all_green baskets (t_close in past). Jun19 rolling file = 16 unique all_green baskets with t_close Jun19-20 (all pending, not yet resolved). Jun13 (19) and Jun18 partial (10) from prior state, files no longer in data-mirror archive (7d rolling purge).
- **Jun19 pending**: 16 baskets with t_close tonight/tomorrow. Will add to n once resolved.
- **Rate**: ~19/day confirmed by Jun13 (19) and Jun15 (19) data points.
- **ETA to 100**: need 52 more at ~19/day = ~2.7 days.
- **Blocker**: Resolution truth (Gamma) needed for cash-out vs hold ROI computation. Per-day basket files age out before they can be joined.

### Gate 5 — THERMO_MAKER_NO (kill gate threshold: n=20)
- **n**: 3 (+0)
- **trades.jsonl**: 0 WEATHER_THERMO trades. **maker_fills_recent.log**: 0 THERMO entries in 7-day tape (Jun12-19).
- **thermo_maker.jsonl**: 12,882 candidate records today (system scanning), but no fills materializing.
- **Resolved trades**: 3 (from prior: +0.11 @ entry 0.98, −5.67 @ entry 0.81, −5.39 @ entry 0.98)
- **WR**: 1/3 = 33.3% | **ROI**: −64.7% | **CI95 (recomputed from trade PnLs)**: [−130.0%, +0.7%]
  - CI straddles zero but upper bound is barely positive (+0.7%). At n=3 this is noise.
  - Prior CI was [−103.4%, +2.0%] — difference due to exact stake reconstruction method.
- **STALLED**: 0 fills in 7+ days. Strategy scans 12k+ candidates/day but never triggers.
- **Kill gate**: needs n=20. At 0/day current rate → ETA INFINITE.
- **Directional signal at n=3**: 2/3 trades are large losses (entries ≥0.81, losses −5.67 and −5.39), consistent with tail-NO adverse selection in upper-tail markets. One more loss would push CI entirely negative. Not a verdict yet (n=3 << 20), but the direction is unfavorable.

### Gate 6 — M1_BETA_LOCKOUT (thin-margin [0.2,0.5)C slice)
- **n**: 31 (+0 from prior — no change)
- **Provenance flag**: trades.jsonl shows only 1 M1_BETA_PROBE signal_source trade (Moscow, May-26, pnl=−1.65). Prior n=31 came from a prior agent's analysis of what may have been an older metar_lockout.jsonl schema (v1 with fire records). Current schema_version=2 logs candidates only. **The 31-trade basis is unverified from available data-mirror files.** Carried forward from prior state with flag.
- **Current metar_lockout.jsonl**: 2545 records today, all schema_version=2, record_type=metar_lockout_candidate. **Thin-margin [0.2,0.5)C bucket candidates: 0** (all candidates are ≥0.5C buckets — bucket_lo ranges from 12.5°C to 29.5°C). The specific slice Gate 6 monitors is not generating candidates today.
- **WR**: 74.2% (from prior, unmodified) | **ROI**: −0.6% | **CI95**: [−20.6%, +24.4%] straddles zero
- **STALLED 10+ days**. ETA INFINITE. The positive WR (74.2%) is misleading given ROI is −0.6% (small wins, occasional large losses).

### Gate 7 — SUM_POSTED_0.70_0.85
- **n**: 2174 (+155 from prior 2019)
- **Sources**: Jun13=338 (prior), Jun14=384, Jun15=360, Jun16=348, Jun17=316, Jun18=282 (full day, was 273 at prior), Jun19=146 (partial)
- **Rate**: ~155/day (accumulates with YES band fires). High rate driven by the widened YES band (BAND_YES_MAX_OFF=2 added Jun18 14:44 UTC).
- **Blocker**: Gamma 403 from container. Same blocker as Gate 1.
- **Status**: n=2174 >> threshold 100. CI blocked. COLLECTING.

---

## State Transitions vs Prior (2026-06-18T10:17Z)

| Gate | Prior Status | Current Status | Delta-n | Transition |
|---|---|---|---|---|
| BAND_YES | COLLECTING | COLLECTING | +271 | None |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | +8 | None — approaching threshold |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | +9 | None |
| BASKET_EXIT | COLLECTING | COLLECTING | +0 | None — 16 pending (Jun19) |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | +0 | None — CI recomputed [−130%,+0.7%] |
| M1_BETA_LOCKOUT | COLLECTING | COLLECTING | +0 | None — prior n=31 provenance flagged |
| SUM_POSTED_0.70_0.85 | COLLECTING | COLLECTING | +155 | None |

**No status transitions this run.**

---

## Structural Blockers

1. **Gamma 403 from container** blocks resolution truth for Gates 1, 2, 7 (all n >> 100) and Gate 4. The VPS-side `band_resolution_join.py` cron (noted fixed Jun17 05:45) must produce resolved ROI data and push it to data-mirror. Until then, these gates are permanently stuck at COLLECTING regardless of n.

2. **Gate 2 threshold imminent** (~1 day): When n crosses 100, the VPS must immediately run the resolution join for fire_no/pair_fav/pair_samebucket legs or Gate 2 will be n≥100 with AMBIGUOUS status (same blocker). Pre-stage the join script now.

3. **CID join blocker (Gate 3)**: maker_fills_recent.log truncated hex vs full conditionId. Requires a VPS-side join tool.

4. **Gate 6 n=31 unverifiable**: Only 1 M1_BETA_PROBE trade in trades.jsonl. VPS operator should confirm whether the 31-trade history is in the VPS logs and what the correct signal_source tag is.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run. No flag/param changes proposed.**

### Watch items (not action triggers):

**W1 — Gate 2 threshold imminent (~1 day)**
VPS operator: pre-stage `band_resolution_join.py` to run on fire_no + pair_fav + pair_samebucket legs as soon as n≥100. If CI_lower > 0 at n=100 → READY (scale-up gate for BAND_NO at proven slices). If CI_upper ≤ 0 → REJECTED (stop NO band for that sub-slice). If CI straddles 0 → AMBIGUOUS, extend.

**W2 — THERMO trending REJECTED**
At n=3, CI upper = +0.7%. One more loss → CI entirely negative. Gate is STALLED (0 fills 7d) and structurally cannot reach n=20 at current rate. Human decision point: wait for the kill gate, or pre-empt given 7-day zero-fire period and CI near-negative. **Not a recommendation to act — surfacing for human awareness.**

**W3 — Jun18 config churn measurement boundary**
Seven band config changes Jun18 11:30-23:59 UTC, final change Jun19 00:30 UTC. Clean-window starts Jun19 00:30 UTC. When the Gamma resolution join runs, split the ROI computation at this boundary to separate contaminated pre-freeze data from the clean forward window.

**W4 — Gate 6 M1_BETA_LOCKOUT n=31 provenance check**
Verify on VPS: `grep -i M1_BETA_PROBE /path/to/old_metar_lockout.jsonl | wc -l`. If unverifiable, reset Gate 6 to n=1 (the one confirmed trade in trades.jsonl) and restate WR/ROI accordingly.

---

## Operational Context (informational)

- **Bankroll**: $249.75
- **Exit099 (RECYCLE099) Jun14-19**: 90 exits, **+$441.89 gross** (maker YES legs redeemed at 0.99)
- **WEATHER/STWA (held-loser) stream**: 486 resolved trades, WR=17.5%, Net −$627.19 (positions that lost at resolution)
- **favNO fill rate**: Jun17-19 tape = 21 NO fills vs 138 YES fills (13.2% NO share). Config as of Jun19 00:30 UTC has favNO at rank 0 (top priority). Monitor for NO-share improvement.
- **Maker markout gap**: Jun18 analysis showed our fills ~1.3¢/sh adversely selected vs badatmath, structural (stale directional legs run over by informed flow). Churn fix (8h pair reclaim vs 2h) is the current lever. No gate implications.

---

*Report generated 2026-06-19. Data source: data-mirror snapshot 2026-06-19T09:00:06Z. Gamma API inaccessible from container — all ROI/CI for Gates 1–4, 7 remain BLOCKED pending VPS-side resolution joins.*
