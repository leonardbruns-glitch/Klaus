# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-07 21:53Z evening run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-07 ~22:00Z (fires 14,733 raw
→ 762 deduped first-fire legs, 507 unique markets, **591 resolved** — +61 vs the
morning run as 07-06/07-07 markets settled). Join is window-relative (hot-log window),
not cumulative. CIs are Wilson 95% on WR mapped through ROI = WR/quote − 1.
**Standing caveat: conditional-on-fill at OUR shadow quotes** — this class of join
showed +8% while live fills realized −4.9% (06-18) and −45% (06-26→07-03 tape). It
gates SHADOW→further validation, not straight to live.

**CONTEXT 07-07 evening: WIND-DOWN HOLDS, but the equity rail CLEARED intra-day.**
Equity **$136.77** (all cash; zero open ladder shots, zero engine positions at cost)
= **61.4% of 30d-HW $222.90** — back above the 50% wind-down line ($111.45) after
Singapore 32°C won (+$49.79 net) against Tokyo 26°C lost (−$21.37). Re-enable is
**withheld on evidence, not capital**: (1) post-guard pair count still n≈9/side vs the
n≥40 positive-trend condition written 07-06; (2) disp_ratio 0.817 < 1.10 trigger,
gauge window stale (isotonic plateau); (3) the −14% daily-loss freeze bars
size/ceiling increases until 07-08 21:53Z; (4) today's 2-live-change cap already spent
(morning: comparator+ratchet, ladder fill-cost). 7d realized **−$118.43 PF 0.088
(n=42)** — all from paths already cut; flow since wind-down = −$4.22 (two legacy
pre-cut YES dust legs resolving). Live surface unchanged: NEG_RISK_ARB + RECYCLE099 +
redemption (+ principal-authorized sprint ladder, outside charter scope).

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 465 | 14.0% | 0.148 | −5.4% | [−24.7%, +17.9%] | AMBIGUOUS, point-negative. Path OFF (07-03 cut + 07-06 wind-down) |
| BAND YES d+2 | 327 | 12.8% | 0.138 | −7.2% | [−30.4%, +22.2%] | AMBIGUOUS |
| BAND YES d+1 | 112 | 17.0% | 0.167 | +1.8% | [−33.1%, +49.8%] | AMBIGUOUS — first n>100 YES slice with a positive point est., but CI ±40pp and conditional-on-fill; NOT actionable |
| BAND YES d+0 | 26 | 15.4% | 0.188 | −18.1% | [−67.2%, +78.5%] | COLLECTING (n<40), point-negative |
| BAND YES offset±2 | 175 | 11.4% | 0.103 | +10.7% | [−27.2%, +64.7%] | AMBIGUOUS; cheap-tail graveyard class — informational only |
| BAND NO (d+1) | 62 | 75.8% | 0.711 | +6.6% | [−10.2%, +19.2%] | COLLECTING (n<100), CI straddles 0. favNO stays HALTED (07-02 rail: live n=51 WR 39.2%) |
| PAIR_FAV YES legs | 32 | 34.4% | 0.455 | −24.4% | [−55.1%, +13.7%] | COLLECTING (n<40); pre-guard naked-leg contamination dominates d+1/d+2 (−74..−100%) |
| PAIR_FAV NO legs | 32 | 65.6% | 0.429 | +52.9% | [+12.6%, +85.5%] | COLLECTING (n<40) — only slice with CI clear of zero, but n and the fill-conditioning caveat gate it. Co-filled pair net ≈ +13%/pair-share. Live pairs OFF (wind-down); counterfactual accrues (shadow-quote rows + pair_clip_skip). Post-guard count n≈9/side (accrual frozen at wind-down 07-06 22:08Z) |
| PAIR clipped subset | — | — | — | — | — | GATED OFF 07-05 (clip-guard 365d59d04); counterfactual accruing; review 07-19 |
| M1β lockout family | — | — | — | — | — | LIVE OFF 07-06. Moscow false lockout −$24.65 (UUWW SPECI class, 3rd incident). Re-enable: lockout_oracle_divergence study (review 07-13) + n≥100 clean join |
| MIN_LOCKOUT (daily-min) | — | — | — | — | — | LIVE OFF 07-06 (same provenance class). Shadow on (29 locked candidates 21:58Z cycle, 0 posts ✓) |
| YES-CAPTURE shadow | — | — | — | — | — | INFORMATIONAL ONLY — 07-07: 225 would-be fills, markout med −1.9¢ / 95% adverse = winner's curse re-confirmed; do not promote |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04; review 07-18 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; stays armed (free option) |
| PEAKSCALP Phase-1 | 427 | 86.7% raw | — | −1.4%/$ after fee | — | REJECTED 07-03 (NO-GO); shadow accrues |
| Band dial time-series | 27 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS; 27 days = noise, do not interpret) |
| Band re-enable trigger | — | — | — | — | — | Equity leg MET 07-07 pm (61.4% of HW). Evidence legs NOT met: disp_ratio 0.817 < 1.10 (gauge stale), post-guard pairs n≈9/side < 40. Freeze until 07-08 21:53Z regardless |

**This run: 0 READY → live, 0 new cuts (nothing live is bleeding — post-wind-down
realized flow is −$4.22 of legacy dust). Morning deploys verified: ruin_floor=89.16
in config.py, BANKROLL SYNC tracking cash+ladder (136.77 exact vs CLOB balance),
daily reset firing (last_utc_day=20641, daily_start 108.35), ladder fill-cost
recording proven by today's settle arithmetic (50.61 + 94.75 = 145.36 sleeve ✓,
42.02 + 94.75 = 136.77 cash ✓).**

Sprint-30 (day 4.99): equity **$136.77** vs day-4 target $160.51 → **≈ −$45 behind**
(tracker line 07-06 23:50Z read −$52.16; tonight's 23:50Z cron will restate). Ladder
lifetime: **8 fired, 8 resolved, 4W/4L, net +$85.36**; sleeve **$145.36**, zero open
shots, settlement ≤36h intact (Tokyo settled 15:30Z, Singapore 16:40Z same day).
Note for analysts: sleeve $145.36 > free cash $136.77 — the engine side has net
negative cash contribution in the shared wallet; next fire is bounded by
min(75%·sleeve, $45) AND live balance − $20 reserve, so this is bookkeeping skew,
not an over-commitment risk. p≈ask coin-flips per design; stated per kernel honesty
rule.
