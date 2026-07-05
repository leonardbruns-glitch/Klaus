# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-05 21:53Z run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-05 ~22:00Z (fires 15,879 raw
→ 968 deduped first-fire legs, 751 unique markets, 788 resolved). **n DROPPED vs the
07-04 run (1,067 resolved) because the hot-log source window rolled — the join is
window-relative, not cumulative.** CIs are Wilson 95% on WR mapped through
ROI = WR/quote − 1. **Standing caveat: this join is conditional-on-fill at OUR shadow
quotes** — the same class of join showed +8% while live fills realized −4.9% (06-18)
and −45% (06-26→07-03 tape). It gates SHADOW→further validation, not straight to live.

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 670 | 14.3% | 0.147 | −2.7% | [−19.2%, +16.9%] | AMBIGUOUS, point-negative. Path stays OFF (07-03 cut correct) |
| BAND YES d+2 | 498 | 13.5% | 0.139 | −3.4% | [−22.8%, +20.4%] | AMBIGUOUS |
| BAND YES d+1 | 134 | 17.2% | 0.165 | +3.9% | [−29.0%, +48.1%] | AMBIGUOUS |
| BAND YES d+0 | 38 | 15.8% | 0.188 | −16.2% | (n<40) | COLLECTING, point-negative |
| BAND NO (d+1) | 80 | 76.2% | 0.704 | +8.3% | [−6.5%, +19.7%] | COLLECTING (n<100), CI straddles 0. Live favNO stays HALTED (07-02 rail: live n=51 WR 39.2%) |
| PAIR_FAV YES legs | 19 | 42.1% | 0.455 | −7.4% | [−49.1%, +40.1%] | COLLECTING (n<40). **Live divergence: fill tape 3.5d = 19 YES vs 5 NO fills (~26% co-fill); one-sided YES n=10 WR 10%** |
| PAIR_FAV NO legs | 19 | 57.9% | 0.433 | +33.9% | [−16.2%, +77.5%] | COLLECTING (n<40). Co-filled pairs net ~+10%/pair (d+1/d+2 Y −100% + N +120-126% same buckets) — the merge works WHEN both legs fill |
| PAIR clipped subset | — | — | — | 7d realized −$28..−$32, PF≈0.1, n=16-18 records | — | **GATED OFF 07-05 (clip-guard, commit 365d59d04)** — NO leg Σ-capped >1¢ behind touch ⇒ not co-fillable at post; slice moved to shadow counterfactual (pair_clip_skip rows) |
| YES-CAPTURE shadow 0.30–0.45 d+2 | 726 snaps/joined earlier | — | would-quote | +103–126% | — | INFORMATIONAL ONLY; 07-05 markout check: **92% adverse (med −2.9¢)** ⇒ would-fills are winner's-curse fills. Cannot justify live |
| THERMO_MAKER_NO | 125 | — | — | EV ≈ 0 | — | REJECTED (07-03 falsification; formalized 07-04) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted to ≥0.5°C 07-04 (commit 2813daa1e) |
| M1β lockout (validated ≥0.5°C) | — | — | — | — | — | Armed; capacity returned briefly 07-04 (Moscow fills +$16.30 redeemed 07-05); otherwise 0 buyable asks |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; karachi NO-side probe showed ARB=True at edge 0.000–0.002 (≤0.2%, below min edge — correctly not fired) |
| PEAKSCALP Phase-1 | 427 | 86.7% raw | — | −1.4%/$ after fee | — | REJECTED 07-03 (NO-GO); shadow keeps accruing |
| Band dial time-series | 24 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS) |
| Band re-enable trigger | — | — | — | — | — | disp_ratio gauge STALE 3 days (calib monitor window locked Jun28–Jul2; isotonic plateau degeneracy). Last reading 0.34–0.82 vs 1.10 — NOT MET |
| Isotonic live refit | — | — | — | — | — | Cron HEALTHY, guard HELD legitimately (cal_days 10<14; OOS cal Brier worse). Candidate refreshed. NOT broken — closes the research-audit "refit cron diagnosis" best-action |

**This run: 0 READY → live, 1 slice GATED OFF (PAIR clipped subset → shadow), rest COLLECTING/REJECTED unchanged.**

Sprint-30 (day 2.6): equity ~$222.90 (cash $196.83 + Munich ladder shot $26.07 at cost)
vs target $128 → **~+$95 ahead**. Ladder tally: 6 fired lifetime / 3 won (Shanghai,
Seattle, Tokyo) / 1 lost (Munich 07-03) / 1 open (Munich 25°C, $26.07 @ 0.47, resolves
~22:00Z) / sleeve $206.94. Gains are coin-flip variance + one lockout capacity window —
not compounding edge; stated per kernel honesty rule.
