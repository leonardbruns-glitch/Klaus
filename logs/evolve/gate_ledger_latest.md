# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-04 21:53Z run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-04 ~22:00Z (fires 23,179 raw
→ 1,221 deduped first-fire legs, 935 unique markets, 1,067 resolved). CIs are Wilson
95% on WR vs the mean posted quote (breakeven proxy). **Standing caveat: this join is
conditional-on-fill at OUR shadow quotes** — the same class of join showed +8% while
live fills realized −4.9% (06-18) and −45% (06-26→07-03 tape). It gates SHADOW→further
validation, not straight to live.

| Gate / slice | n | WR | avg quote | ROI | Wilson CI (WR) | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 934 | 15.3% | 0.147 | +4.0% | [13.1%, 17.8%] | AMBIGUOUS — CI straddles quote 0.147; n met, direction unconfirmed |
| BAND YES d+2 | 672 | 14.4% | 0.137 | +5.4% | [12.0%, 17.3%] | AMBIGUOUS — CI straddles 0.137 |
| BAND YES d+1 | 190 | 17.4% | 0.165 | +5.3% | [12.7%, 23.4%] | AMBIGUOUS |
| BAND YES d+0 | 72 | 18.1% | 0.196 | −7.8% | [11.1%, 28.0%] | COLLECTING (n<100), point-negative |
| BAND NO (all, d+1) | 115 | 68.7% | 0.678 | +1.3% | [59.7%, 76.4%] | AMBIGUOUS — CI straddles 0.678. Live favNO stays HALTED (07-02 rail: live n=51 WR 39.2% @ 0.655) |
| PAIR_FAV YES legs | 9 | 55.6% | 0.460 | +20.7% | — | COLLECTING (n<40) |
| PAIR_FAV NO legs | 9 | 44.4% | 0.428 | +3.7% | — | COLLECTING (n<40) |
| YES-CAPTURE shadow 0.30–0.45 d+2 | 398 | 21.1% | 0.093 would-quote | +126% | — | INFORMATIONAL ONLY — would-post join (analyzer FIXED today after 3 days of false "0 snapshots"; cwd bug). Winner's-curse rule: cannot justify live. Needs a live-fill validation design |
| YES-CAPTURE shadow all 0.10–0.45 | 726 | 16.3% | 0.080 would-quote | +103% | — | same caveat |
| THERMO_MAKER_NO | 125 (external join 07-03) | — | — | EV −9..+2%/sh ≈ 0 | — | **REJECTED — killed formally today.** Flag already False since 06-23; n=20 kill gate pre-resolved by the n=125 falsification |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] (ROI CI, gatekeeper) | **REJECTED — param REVERTED 0.2→0.5°C today** (commit 2813daa1e). 22-day stall, capacity zero |
| M1β lockout (validated ≥0.5°C) | — | — | — | — | — | CAPACITY DEAD (07-03 sweep: 0 buyable asks; min-side only @0.999). Path stays armed, harvests nothing |
| NEG_RISK_ARB | — | — | — | — | — | CAPACITY DEAD 9 consecutive days (Σask floor pinned 1.000) |
| PEAKSCALP Phase-1 | 427 resolved | 86.7% raw | — | −1.4%/$ after fee (buyable slice) | — | REJECTED 07-03 (NO-GO); shadow logger keeps accruing |
| BASKET_EXIT | — | — | — | — | — | VOID (06-22 tautology; do not revisit) |
| Band dial time-series | 23 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS) |
| Band re-enable trigger | — | — | — | — | — | disp_ratio 0.34 (d+2) .. 0.82 (d+0) vs 1.10 threshold — NOT MET, 7+ days |

**This run: 0 READY → live, 2 REJECTED (THERMO formalized, M1β thin-margin), rest COLLECTING.**

Sprint-30 (day 1.1): equity $125.56 (cash $74.45 + positions mark $51.11) vs target
~$101.3 → **+$24.3 ahead** (one 0.40-ask ladder win; luck, not edge — logged honestly).
Ladder tally: 2 fired / 1 won (+$63.50 net) / 1 open / 0 lost.
