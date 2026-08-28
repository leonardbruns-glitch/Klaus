# Winner's-Curse Cross-Tab — 2026-07-11 22:15Z (VPS, EVOLVE evening actuator)

Resolves the exec-audit alert open 5 consecutive days ("markout gap / winner's
curse direction unresolved — formal per-leg split requires VPS data"). Input to
the **Jul 12 structural review** (band re-enable / micro-stake PAIR_FAV).

Script: `analysis/weather/winners_curse_crosstab_0711.py` (re-runnable).
Realized side: `trades.jsonl` rows tagged `WEATHER/<city>/WEATHER_MAKER`,
06-11→07-06 era, resolution-settled (exit 0.0/1.0 only — **no survivorship
bias**: zero 0.99-recycle exits in this set; 19 BAND_MERGE exits excluded,
net +$9.29). Simulated side: band_struct first-fire legs joined to Gamma
(identical logic to `band_resolution_join.py`).

## Headline

| Basis | n | WR | avg px | ROI |
|---|---|---|---|---|
| **Realized maker fills** (Jun era) | 75 | 17.3% | 0.417 | **−75.8%** (net −$173.78 / $229.36 staked) |
| Simulated same-era join (state_log 06-17, n=3,418) | 3,418 | — | — | YES **+7.6%** / NO **+3.7%** |
| Simulated tonight (Jul-era legs, n=678) | 678 | — | — | YES +4.8% / NO +35.8% |

Gap ≈ **−80pp conditional on fill**, era-matched at the aggregate level.

## Per-cell (side × days_out × price band), realized vs Jul-era sim

Every cell with sim support shows the same sign — realized WR collapses at the
SAME quote level:

| Cell | filled n / WR | sim n / WR |
|---|---|---|
| NO d+1 px 0.60–0.85 | 15 / **20.0%** | 14 / **92.9%** (px 0.667 vs 0.696) |
| NO d+1 px 0.45–0.60 | 6 / 16.7% | 1 / 100% |
| YES d+1 px 0.00–0.10 | 2 / 0% | 45 / 11.1% |
| YES d+1 px 0.10–0.20 | 4 / 0% | 44 / 20.5% |
| YES d+2 px 0.10–0.20 | 6 / 0% | 253 / 13.8% |
| YES d+2 px 0.20–0.30 | 2 / 0% | 49 / 26.5% |

A favorite-NO filled at 0.667 that wins 20% of the time is not slice
composition — it is being filled selectively on favorites that WIN.

## Caveats (honest)

- n=75 realized = 40–99 **trend-grade**, not n≥100 decision-grade. Direction is
  unambiguous (13W/62L; the 06-18 markout study n=902 found the same sign at
  fill time: our fills +0.07¢ vs badatmath +1.16¢).
- Era mismatch in the per-cell table: fills are June (peak 06-19), sim legs are
  Jul 01–11 (hot-log retention). The aggregate comparison against the 06-17
  join (n=3,418, same era as the fills) carries the era-matched conclusion.
- D1 (filled-vs-never-filled within one sim universe) is void — only 3/75
  filled markets appear in the Jul-era shadow window.

## Verdict for Jul 12

1. **Winner's curse CONFIRMED in direction** (trend-grade): the simulated
   all-fires ROI (G1/G7/band_resolution_join) systematically overstates
   fill-conditioned reality by more than the entire claimed edge. **No YES/NO
   band re-enable may be justified from simulated join ROI alone** — the sim is
   an upper bound, not an estimator. This also re-confirms the graveyard entry
   ("maker at touch = −EV via adverse selection") for our band implementation.
2. **The PAIR_FAV path is the exception, conditionally**: a completed pair
   (both legs filled, Σ≈0.885) pays $1.00 regardless of outcome — adverse
   selection cannot touch a co-filled pair. The damage channel is the NAKED leg
   (one-sided fill: pair-era one-sided YES n=10 WR 10%). The 07-05 clip-guard
   (skip pair when NO leg not restable within 1¢ of touch) exists precisely to
   force co-fillability. A micro-stake PAIR_FAV re-enable **with the clip-guard
   binding and a co-fill kill condition** is NOT invalidated by tonight's
   finding; naked-leg exposure is.
3. G2c's +52.9% CF ROI (n=32) is counterfactual (fires, not fills) — apply the
   same suspicion: the co-fill RATE, not the CF ROI, is the number the Jul 12
   decision should weight.
