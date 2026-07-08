# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-08 21:53Z evening run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-08 ~22:00Z (fires 16,429 raw
→ 794 deduped first-fire legs, 548 unique markets, **623 resolved** — +32 vs the
07-07 evening run). Join is window-relative (hot-log window), not cumulative. CIs are
Wilson 95% on WR mapped through ROI = WR/quote − 1.
**Standing caveat: conditional-on-fill at OUR shadow quotes** — this class of join
showed +8% while live fills realized −4.9% (06-18) and −45% (06-26→07-03 tape). It
gates SHADOW→further validation, not straight to live.

**CONTEXT 07-08 evening: WIND-DOWN RE-BREACHED — this was a breached-rail day
(cutting, not optimizing).** Equity **$83.93** (cash $59.59 CLOB-actual + Chicago
ladder shot at cost $24.34) = **37.7% of 30d-HW $222.90**, back below the 50% line
($111.45) after the 07-08 China ladder losses (Shanghai −$6.84 + Guangzhou −$43.78,
authorized coin-flips). Tracked capital $84.47 < ruin_floor $89.16 → engine
no-new-entries armed. Daily realized −38% of daily_start $136.77 re-trips the −14%
rail → **no size/ceiling increases until 2026-07-10 21:53Z**. Actions tonight (commit
64a4e312b): MIN_LOCKOUT_LIVE re-cut to False (rail-driven; posted 0 orders in its 7h
owner-directed re-enable, cost ≈$0; the 197/197 evidence stands — re-enable is now
rail-conditional only) + kernel-floor guard ($40 tracked) added to sprint_ladder.py
fire path (INVARIANTS #2 had no mechanical enforcement for the cron ladder). 7d
realized **−$98.81 PF 0.095 (n=36)** — all from paths cut 07-02/07-06; engine
resolved rows today: 0. Live surface: NEG_RISK_ARB + RECYCLE099 + redemption
(+ principal-authorized sprint ladder, outside charter scope).

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 506 | 14.6% | 0.145 | +0.7% | [−18.5%, +23.9%] | AMBIGUOUS ≈ zero edge. Path OFF (07-03 cut + wind-down) |
| BAND YES d+2 | 356 | 13.2% | 0.136 | −2.9% | [−25.9%, +25.8%] | AMBIGUOUS |
| BAND YES d+1 | 132 | 17.4% | 0.165 | +5.5% | [−27.9%, +50.2%] | AMBIGUOUS — point-positive, CI ±40pp, conditional-on-fill; NOT actionable |
| BAND YES d+0 | 18 | 22.2% | 0.183 | +21.3% | [−50.8%, +147.1%] | COLLECTING (n<40) |
| BAND NO (d+1) | 55 | 74.5% | 0.711 | +4.8% | [−13.2%, +18.4%] | COLLECTING (n<100), CI straddles 0. favNO stays HALTED |
| PAIR_FAV YES legs | 31 | 32.3% | 0.454 | −28.9% | [−59.1%, +9.8%] | COLLECTING (n<40); pre-guard naked-leg contamination dominates d+1/d+2 |
| PAIR_FAV NO legs | 31 | 67.7% | 0.430 | +57.4% | [+16.6%, +89.4%] | COLLECTING (n<40) — only CI-clear slice; co-filled pair net ≈ +13%/pair-share. Pairs OFF (wind-down); post-guard accrual FROZEN while BAND_LIVE=False (pair branch nests inside the YES posting loop — counterfactual does not accrue during wind-down; n≈9/side since 07-05 guard) |
| PAIR clipped subset | — | — | — | — | — | GATED OFF 07-05 (clip-guard); accrual frozen with band off; review 07-19 |
| M1β lockout MAX family (taker) | 58 exec | — | — | EV −6.5%/fill | — | **KILLED 07-08** (divergence study, 5d early): all 58 executable lockouts sat at divergent stations {VHHH,ZGSZ,UUWW}; clean-station taker capacity = 0. UUWW blocklisted; margin reverted 0.5→1.0 |
| MIN_LOCKOUT (daily-min) maker | 197 | 100% @margin≥1.0 | — | — | CI-low 98.1% (Wilson) | **Evidence gate PASSED** (lockout_divergence_0708, n=363 family) but LIVE OFF — enabled 07-08 15:10 (owner), re-cut 21:53 on wind-down rail re-breach; posted 0 orders while live. Re-enable condition: equity ≥ 50%·30d-HW, nothing else outstanding |
| YES-CAPTURE shadow | 248 | — | — | markout med −1.9¢, 95% adverse | — | INFORMATIONAL — winner's curse re-confirmed 07-08; do not promote |
| TEMPORAL_LOCK (P5) taker | 472 | — | — | −EV all slices after 1.25% fee | — | **KILLED 07-08** (shadow sweep); scanner also has a d+1 date-join bug — fix before ANY future P5 use |
| COUNT_LOCK | 16 cand/11d | — | — | — | — | **KILLED 07-08**: 0 ever executable |
| MINMAX coherence | 11 baskets/11d | — | — | ~$5-15/wk | — | DEFERRED 07-08: 9/11 ≤1¢ margin (fees eat); needs new executor; revisit if frequency rises |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04; review 07-18 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; stays armed (free option) |
| Band dial time-series | 28 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS; do not interpret) |
| Isotonic settled-lane rebuild (PA-1) | — | — | — | — | — | **TOP QUEUED LEVER** (calib + research audits agree): live-refit cron inactive since Jun 9, gauge degenerate; candidate map NOT deployable per calib report. Deferred tonight ONLY on rail state — first non-breached morning slot should run the fresh VPS refit |
| Band re-enable trigger | — | — | — | — | — | Equity leg LOST again 07-08 (37.7% of HW). disp_ratio gauge stale pending PA-1. Post-guard pair accrual frozen while band off (structural: needs shadow-mode band posting to accrue — note for weekly) |

**This run: 0 promotions (breached-rail day, steps 3–4 skipped per prompt), 2 cuts
(MIN_LOCKOUT_LIVE off, ladder kernel floor). Interactive-session changes 07-08
14:30–15:35 (owner directive) registered retroactively in ledger.jsonl — they were
deployed without ledger pre-registration.**

Sprint-30 (day 5.99 tonight): equity **$83.93** vs day-5 target ≈ $206 → ≈ **−$122
behind**; the 23:50Z cron will restate. Ladder lifetime: **11 fired, 10 resolved,
4W/6L, net ≈ +$14** (post-07-08: Shanghai −$6.84, Guangzhou −$43.78, Chicago $24.34
open, settles ~05:00Z 07-09); sleeve **$70.40**; 3/3 daily fires used; settlement
≤36h intact; cron healthy (10-min syslog cadence; recurring benign
`400 Could not create api key` client noise since ≥07-04, fires/settles unaffected).
p≈ask coin-flips per design; stated per kernel honesty rule.
