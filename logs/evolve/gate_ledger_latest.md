# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-10 21:53Z evening run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-10 ~22:00Z (fires 18,600 raw
→ 829 deduped first-fire legs, 586 unique markets, **671 resolved**), plus
`band_sum_posted_slice.py` (747 deduped YES legs), plus NEW
`analysis/weather/settled_disp_ratio.py` — the S3 dispersion gauge UNBLOCKED (cloud
lane was 8 days label-stale; labels only computable on this box).
Join is window-relative (hot-log window), not cumulative — per-slice n can SHRINK
day-over-day as old days rotate out (BAND NO d+1 n 39→24 today is retention, not
data loss). CIs are Wilson 95% on WR mapped through ROI = WR/quote − 1.
**Standing caveat: conditional-on-fill at OUR shadow quotes** — this class of join
showed +8% while live fills realized −4.9% (06-18) and −45% (06-26→07-03 tape). It
gates SHADOW→further validation, not straight to live.

**CONTEXT 07-10 evening: rails CLEAR second consecutive slot; the −14% freeze
EXPIRED at this slot (21:53Z) with no re-trip.** Equity **$163.16** (all cash
CLOB-actual; 0 open ladder shots, 0 engine positions) = **73.2% of 30d-HW $222.90**
> the 50% line $111.45; tracked > ruin_floor $89.16. Daily realized **+$4.53** on
daily_start $158.63 (+2.9%) — all sprint ladder (Guangzhou +$30.00, Tokyo −$15.72,
Shanghai −$7.41 = +$6.87 fills-basis; −$2.3 residual = payout/proxy dust, zero
engine flow all day). 7d realized (trades.jsonl) **−$71.52 PF 0.108 n=26** — every
row opened 07-02→07-06, i.e. 100% tail from paths already cut; post-cut engine
flow = 0. The morning 11:23Z slot died on session limits — this run covered the
full 07-10 backlog. Live surface unchanged: NEG_RISK_ARB + RECYCLE099 + redemption
(+ ladder cron).

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 589 | 14.6% | 0.144 | +1.2% | straddles 0 | AMBIGUOUS ≈ zero edge. Path OFF |
| BAND YES d+2 | 432 | 13.4% | 0.136 | −1.1% | straddles 0 | AMBIGUOUS (the drag) |
| BAND YES d+1 | 131 | 17.6% | 0.162 | +8.2% | straddles 0 | AMBIGUOUS — conditional-on-fill; NOT actionable |
| BAND YES d+0 | 26 | 19.2% | 0.195 | −1.1% | wide | COLLECTING (n<40; 07-09 read +18.2% n=23 — sign flipped on 3 legs = noise) |
| BAND NO (d+1) | 24 | 79.2% | 0.686 | +15.4% | straddles 0 | COLLECTING (n<100; window shrank 39→24). favNO stays HALTED |
| PAIR_FAV combined | 29 pairs | — | 0.885/pair | **+13.1%/$** | n<40 | COLLECTING — stable vs 07-09 (+13.0% n=30); legs: YES_PAIR −31.4% / NO_PAIR +59.5% |
| PAIR post-clip-guard | **0 resolved** | — | — | — | — | **ACCRUAL STRUCTURALLY FROZEN** while BAND_LIVE=False (pair branch nests in YES loop). Gate "post-guard n≥40" UNREACHABLE while dark → weekly 07-12 decides: band shadow-posting mode OR condition amendment |
| **G7 SUM_POSTED [0.70,0.85] YES** | **396** | 16.7% | 0.146 | **+14.3%** | **[−8.7%, +41.6%]** | **AMBIGUOUS — NOT READY** (CI straddles; n +14 vs 07-09, drifting up not converging) |
| G7 SUM_POSTED <0.70 YES | 183 | 9.8% | 0.140 | −29.8% | [−55.0%, +7.1%] | point-NEGATIVE, near-significant — argues against ever re-enabling the sub-0.70 book |
| M1β lockout MAX family (taker) | 58 exec | — | — | EV −6.5%/fill | — | KILLED 07-08 (divergence study); UUWW blocklisted; margin 1.0 |
| MIN_LOCKOUT (daily-min) maker | 197 | 100% @margin≥1.0 | — | — | CI-low 98.1% | Evidence gate PASSED; LIVE OFF (07-08 rail re-cut). Rail clear 2 slots now — re-enable at the **07-11 ledger review** (72h anti-thrash ends 07-11 ~22:05Z). Expected cost of deferral ≈ $0 (0 posts in its 7h live window; ~32 candidates/cycle, ~0 executable) |
| TEMPORAL_LOCK (P5) taker | 472 | — | — | −EV all slices | — | KILLED 07-08; scanner d+1 date-join bug outstanding — fix before ANY P5 reuse |
| COUNT_LOCK | 16 cand/11d | — | — | — | — | KILLED 07-08: 0 ever executable |
| MINMAX coherence | 11 baskets/11d | — | — | ~$5-15/wk | — | DEFERRED (fees eat 9/11; needs new executor) |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04; review 07-18 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; stays armed (free option); 0 fires today |
| Band dial time-series | 29 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS; do not interpret) |
| Isotonic (PA-1) | — | — | — | — | — | CLOSED no-defect 07-09; plateau STRUCTURAL; auto-promote ~07-12 iff OOS Brier improves; do NOT lean on mid-range p_cal |

## Regime check — YES would-post ROI by MARKET date
| date | n | WR | quote | ROI | ROI CI95 |
|---|---|---|---|---|---|
| 07-05 | 46 | 15.2% | 0.151 | +0.5% | [−50.0, +86.3] |
| 07-06 | 97 | 14.4% | 0.151 | −4.3% | [−41.6, +51.1] |
| 07-07 | 71 | 15.5% | 0.147 | +5.3% | [−39.7, +74.3] |
| 07-08 | 80 | 17.5% | 0.137 | +27.6% | [−21.8, +98.7] |
| 07-09 | 88 | 13.6% | 0.141 | −3.5% | [−43.6, +58.0] |
| 07-10 | 68 | 13.2% | 0.143 | −7.4% | [−50.2, +62.8] |

Points oscillate around zero, every CI huge — neither inversion nor recovery
confirmed. Unchanged from 07-09.

## S3 DISPERSION GAUGE — UNBLOCKED (the 07-10 headline)

`analysis/weather/settled_disp_ratio.py` (NEW, committed): full pricer_eval files
(not s50 subsamples), last PRE_PEAK ladder per city-date d+0, implied σ =
p_cal-normalized std (°C) of the ladder vs realized = |resolved bucket − mode
bucket|, resolved label = final official-floored running_max at last pre-close
snapshot. Cross-validation on the overlap window (Jun 30–Jul 2, where the cloud
settled lane published 0.976/0.866/0.858): this method reads 1.081/1.001/0.944 —
consistently a touch HIGHER than the cloud lane, so any inversion it shows is not
a harsh-method artifact. (Jun 28–29 hot files already rotated out.)

| Market date | n | impl σ | real | pooled ratio | median city ratio |
|---|---|---|---|---|---|
| 07-03 | 41 | 0.852 | 1.005 | 0.848 | 0.527 |
| 07-04 | 39 | 0.787 | 0.886 | 0.889 | 0.722 |
| 07-05 | 37 | 0.820 | 0.931 | 0.881 | 0.703 |
| 07-06 | 39 | 0.777 | 0.632 | **1.228** | 0.798 |
| 07-07 | 37 | 0.800 | 1.081 | 0.740 | 0.578 |
| 07-08 | 40 | 0.815 | 0.983 | 0.829 | 0.578 |
| 07-09 | 41 | 0.850 | 1.117 | 0.762 | 0.709 |
| 07-10 | 21 | 0.886 | 1.429 | 0.620 | 0.736 (partial-day) |

**Verdict: the standing re-enable trigger (disp_ratio ≥ 1.10 for 5 consecutive
days) is NOT met — 1 of 8 new days above 1.10, never 2 consecutive; median-city
ratio ≤ 0.80 on every day.** The market keeps pricing LESS dispersion than
realizes; the standalone-YES band premise remains dead through 07-10. This answers
calib-monitor S3 (8-day stale) and research-audit A1 ("do not re-enable before
seeing Jul 3–9 dispersion") — seen, and it says NO. Data:
`analysis/weather/settled_disp_ratio.json` (410 city-date rows, committed).

## Decision memo for the 07-12 weekly (band deadlock)

All three re-enable arguments now have fresh data, and none clears:
1. Pre-registered binding condition (post-guard pair n≥40): frozen at 0, structural.
2. Standing disp trigger (≥1.10 × 5d): measured, NOT met (table above).
3. G7 [0.70,0.85]: n=396 AMBIGUOUS, CI [−8.7, +41.6], needs ~4× n for CI-clear.
The only CI-clear positive anywhere remains PAIR_FAV NO counterfactual (+52.9%
CI [+12.6,+85.5] n=32, gatekeeper G2c — trend, n<40). If the weekly breaks the
deadlock, the cheapest gate-respecting path is shadow-posting mode (accrues G2b/G2c
post-guard n at ~11 pairs/day with zero capital), NOT a live flip — and the
dispersion table above argues the standalone-YES half of the band stays dead
regardless of what the pair decision is.

## Other VPS-only readouts

- **yes_capture (would-post markout)**: 301 reconstructed fills, med −0.019,
  94% adverse — winner's-curse signature intact; informational only (charter rule:
  maker-book markout never justifies a live change).
- **Sprint ladder** (owner-mandated, outside charter flag scope): lifetime 17
  resolved 7W/10L (WR 41.2% vs avg fill ~0.43 — at-ask coin-flips per design),
  net ≈ +$117 redemption-basis lifetime; today 3/3 fires, +$6.87 fills-basis.
  Sleeve $179.69, event arithmetic exact (131.92 + 47.77 Guangzhou credit).
  Cron healthy — log silent 17:10→22:00 is the benign cap-reached/no-open-shots
  early-exit path (syslog shows all 10-min firings; 0 tracebacks). Watch item
  unchanged: negative-model-edge fires 0W/2L (n=2; tuning rule needs n≥10).
- **Sprint-30**: day 7 of 30 tonight; equity $163.16 vs day-7 target ≈ $256 →
  ≈ −$93 behind (23:50Z cron restates).
