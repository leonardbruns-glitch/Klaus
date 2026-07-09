# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-09 21:53Z evening run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-09 ~22:00Z (fires 16,893 raw
→ 803 deduped first-fire legs, 557 unique markets, **654 resolved**) plus NEW
`analysis/weather/band_sum_posted_slice.py` (G7 sum_posted slice + per-market-date
regime table — the analysts' PA-1 ask, run tonight instead of the dead morning slot).
Join is window-relative (hot-log window), not cumulative. CIs are Wilson 95% on WR
mapped through ROI = WR/quote − 1.
**Standing caveat: conditional-on-fill at OUR shadow quotes** — this class of join
showed +8% while live fills realized −4.9% (06-18) and −45% (06-26→07-03 tape). It
gates SHADOW→further validation, not straight to live.

**CONTEXT 07-09 evening: rails CLEAR — first non-breached slot since 07-07.**
Equity **$158.63** (all cash, CLOB-actual; 0 open ladder shots, 0 engine positions)
= **71.2% of 30d-HW $222.90** > the 50% line $111.45. Tracked $158.63 > ruin_floor
$89.16 (engine no-new-entries dis-armed). Daily realized **+$74.70** on daily_start
$83.93 (+89%) — all sprint ladder (Chicago +$19.91, Tokyo 30°C +~$76 via the FIRST
live 0.99-early-exit, Guangzhou −$14.06, Tel Aviv −$5.30). 7d realized (trades.jsonl)
**−$79.36 PF 0.116 n=32** — all from paths cut 07-02/07-06 (band remnants −$56.27,
Moscow M1β −$24.65); engine resolved rows today: 0; post-wind-down engine flow ≈ 0.
−14% freeze (07-08 breach) runs to **07-10 21:53Z**: no size/ceiling increases.
Live surface unchanged: NEG_RISK_ARB + RECYCLE099 + redemption (+ ladder).

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 555 | 14.8% | 0.145 | +1.6% | straddles 0 | AMBIGUOUS ≈ zero edge. Path OFF (07-03 cut + wind-down) |
| BAND YES d+2 | 399 | 13.3% | 0.137 | −2.9% | straddles 0 | AMBIGUOUS (the drag) |
| BAND YES d+1 | 133 | 18.0% | 0.164 | +9.8% | ±~40pp | AMBIGUOUS — point-positive, conditional-on-fill; NOT actionable |
| BAND YES d+0 | 23 | 21.7% | 0.184 | +18.2% | wide | COLLECTING (n<40) |
| BAND NO (d+1) | 39 | 74.4% | 0.698 | +6.5% | straddles 0 | COLLECTING (n<100). favNO stays HALTED |
| PAIR_FAV combined | 30 pairs | — | 0.885/pair | **+13.0%/$ (+0.115/pair)** | n<40 | COLLECTING; legs: YES_PAIR −33.6% / NO_PAIR +61.6% |
| PAIR post-clip-guard | **0 resolved** | — | — | — | — | **ACCRUAL STRUCTURALLY FROZEN** while BAND_LIVE=False (pair branch nests in YES loop). Gate "post-guard n≥40" is UNREACHABLE while dark → weekly 07-12 must decide: wire band shadow-posting OR amend the re-enable condition |
| **G7 SUM_POSTED [0.70,0.85] YES** | **382** | 16.5% | 0.148 | **+11.5%** | **[−11.4%, +38.9%]** | **AMBIGUOUS — NOT READY** (n cleared, CI straddles zero). Gatekeeper's 5-days-overdue ask is now ANSWERED |
| G7 SUM_POSTED <0.70 YES | 163 | 10.4% | 0.139 | −24.8% | [−52.3%, +15.9%] | AMBIGUOUS, points negative |
| M1β lockout MAX family (taker) | 58 exec | — | — | EV −6.5%/fill | — | KILLED 07-08 (divergence study); UUWW blocklisted; margin 1.0 |
| MIN_LOCKOUT (daily-min) maker | 197 | 100% @margin≥1.0 | — | — | CI-low 98.1% | Evidence gate PASSED; LIVE OFF (07-08 rail re-cut). Equity rail now CLEAR — re-enable **deferred to the 07-11 ledger review** (72h anti-thrash: param changed 07-08 21:53). Expected cost of deferral ≈ $0 (posted 0 orders in its 7h live window; 31 candidates/cycle, ~0 executable) |
| TEMPORAL_LOCK (P5) taker | 472 | — | — | −EV all slices | — | KILLED 07-08; scanner d+1 date-join bug outstanding — fix before ANY P5 reuse |
| COUNT_LOCK | 16 cand/11d | — | — | — | — | KILLED 07-08: 0 ever executable |
| MINMAX coherence | 11 baskets/11d | — | — | ~$5-15/wk | — | DEFERRED (fees eat 9/11; needs new executor) |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04; review 07-18 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000 (Seoul probe tonight: $0.0018/sh partial, 7/11 legs fillable — no fire); stays armed (free option) |
| Band dial time-series | 29 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS; do not interpret) |
| Isotonic (PA-1 / Experiment 3) | 4,752 live pairs / 11 days | — | — | — | — | **ANSWERED — no action.** Refit cron is NOT dead (prior ledger claim wrong): it runs daily 09:30, log fresh. Guard held LEGITIMATELY (cal_days 11<14; OOS cal Brier not improved). Fresh candidate ON JULY DATA still flat g≈0.376 for p∈[0.35,0.85] ⇒ **plateau is structural, not staleness**. Guard auto-promotes at cal_days≥14 (~07-12) iff OOS improves. Do NOT lean on p_cal for mid-range live gates |

## Regime check — YES would-post ROI by MARKET date (answers calib_monitor's stale settled lane)
| date | n | WR | quote | ROI | ROI CI95 |
|---|---|---|---|---|---|
| 07-02 | 46 | 8.7% | 0.138 | −36.9% | [−75.1, +47.5] |
| 07-03 | 40 | 15.0% | 0.138 | +9.1% | [−48.7, +111.4] |
| 07-04 | 38 | 15.8% | 0.139 | +13.5% | [−46.5, +118.6] |
| 07-05 | 46 | 15.2% | 0.151 | +0.5% | [−50.0, +86.3] |
| 07-06 | 97 | 14.4% | 0.151 | −4.3% | [−41.6, +51.1] |
| 07-07 | 71 | 15.5% | 0.147 | +5.3% | [−39.7, +74.3] |
| 07-08 | 80 | 17.5% | 0.137 | +27.6% | [−21.8, +98.7] |
| 07-09 | 77 | 13.0% | 0.143 | −8.9% | [−49.4, +56.3] |

**Reading:** Jul 3–9 shows NEITHER confirmed dispersion inversion NOR confirmed
recovery — every per-day CI is huge, points oscillate around zero. The research-audit
scenario "inversion persisted all week ⇒ hold dark regardless of equity" is NOT
confirmed; neither is its opposite.

## Decision memo for the 07-10 21:53Z slot (research-audit PA-2)
- Equity rail: CLEARED ($158.63 = 71% HW). −14% freeze: expires at that slot.
- Analysts' proposed OR-condition: G7 READY → **NO (AMBIGUOUS)**; disp_ratio
  recovery ≥1.10 → **NOT CONFIRMED** (table above). Neither branch satisfied.
- The BINDING pre-registered condition (07-06 cut): equity AND **post-guard pair
  n≥40 positive trend**. Post-guard resolved = 0 and cannot accrue while dark.
  ⇒ A daily slot should NOT flip BAND_LIVE on a weaker after-the-fact condition;
  the deadlock (band shadow-posting mode vs condition amendment) is the weekly
  07-12 structural decision.

**This run: 0 live-effect changes** (first non-breached day; the two candidates —
MIN_LOCKOUT re-enable, BAND re-enable — both fail anti-thrash/pre-registered gates;
deferred to 07-11 review and weekly 07-12 respectively, with ≈$0 expected cost).

Sprint-30 (day 6.99 tonight): equity **$158.63** vs day-7 target ≈ $256 → ≈ **−$98
behind**; 23:50Z cron restates. Ladder lifetime: **14 fired, 14 resolved, 6W/8L,
WR 42.9% vs avg fill 0.434** (at-ask coin-flips per design); lifetime net ≈ **+$110**
(redemption/sale proceeds − recorded cost; supersedes the mis-added ≈+$14 in the
07-08 ledger — that same-10-shot set nets ≈ +$35). Sleeve **$172.82**, event
arithmetic reconciles EXACTLY (43.82 + 129 Tokyo credit). First live 0.99-early-exit
WORKED (Tokyo 30°C sold ~0.99 intraday, capital recycled same day — validates the
07-08 velocity upgrade ahead of its 07-12 review). 3/3 daily fires used; settlements
≤36h intact; cron healthy (benign recurring `400 Could not create api key` noise).
Watch (n=2, no action): negative-model-edge fires now 0W/2L (Munich −0.049,
Tel Aviv −0.034); tuning rule needs n≥10 systematic.
