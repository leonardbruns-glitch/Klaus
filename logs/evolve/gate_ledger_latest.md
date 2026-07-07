# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-07 11:23Z run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-07 ~11:30Z (fires 14,163 raw
→ 746 deduped first-fire legs, 505 unique markets, 530 resolved). Join is
window-relative (hot-log window), not cumulative. CIs are Wilson 95% on WR mapped
through ROI = WR/quote − 1. **Standing caveat: conditional-on-fill at OUR shadow
quotes** — this class of join showed +8% while live fills realized −4.9% (06-18) and
−45% (06-26→07-03 tape). It gates SHADOW→further validation, not straight to live.

**CONTEXT 07-07: WIND-DOWN PERSISTS.** Equity $108.35 (cash $42.02 + 2 ladder shots
at actual cost $66.33) = 48.6% of 30d-HW $222.90 < 50% rail. 7d realized −$128.38
PF 0.085 (n=45) — ALL of it from paths already cut (band YES/maker −$105, M1β Moscow
−$24.65). No live-effect optimization today (breached-rail day). Live surface
unchanged: NEG_RISK_ARB + RECYCLE099 + redemption (+ principal-authorized sprint
ladder, outside charter scope). All shadow loggers accruing.

**Mirror-health note for cloud analysts:** pnl_ledger 07-07 "DATA MIRROR DEAD /
20h stale" is FALSE — `klaus_data_mirror.service` pushed 111 snapshots on Jul 6 with
zero gaps and is current (last push 11:20:35Z Jul 7). The stall was on the analyst's
fetch side; its own "Generated 2026-07-07T23:37Z" timestamp is impossible. Treat that
report's capital/position numbers as last-known-good, not as an outage signal.

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 404 | 13.6% | 0.148 | −8.1% | [−28.3%, +16.9%] | AMBIGUOUS, point-negative. Path OFF (07-03 cut + 07-06 wind-down re-confirmed) |
| BAND YES d+2 | 290 | 12.8% | 0.138 | −7.2% | [−31.9%, +23.8%] | AMBIGUOUS |
| BAND YES d+1 | 88 | 15.9% | 0.168 | −5.4% | [−42.1%, +48.5%] | AMBIGUOUS |
| BAND YES d+0 | 26 | 15.4% | 0.188 | −18.1% | [−67.3%, +78.4%] | COLLECTING (n<40), point-negative |
| BAND NO (d+1) | 62 | 75.8% | 0.711 | +6.6% | [−10.2%, +19.2%] | COLLECTING (n<100), CI straddles 0. favNO stays HALTED (07-02 rail: live n=51 WR 39.2%) |
| PAIR_FAV YES legs | 32 | 34.4% | 0.455 | −24.4% | [−55.1%, +13.6%] | COLLECTING (n<40); pre-guard naked-leg contamination dominates d+1/d+2 (−74..−100%) |
| PAIR_FAV NO legs | 32 | 65.6% | 0.429 | +52.9% | [+12.6%, +85.5%] | COLLECTING (n<40). Co-filled pair net ≈ +13%/pair-share — merge works WHEN both legs fill. Live pairs OFF (wind-down); counterfactual accrues (shadow-quote rows + pair_clip_skip). Gatekeeper post-guard count n=9/side (+4 on 07-06, accrual stopped at wind-down 22:08Z) |
| PAIR clipped subset | — | — | — | — | — | GATED OFF 07-05 (clip-guard 365d59d04); counterfactual accruing |
| M1β lockout family | — | — | — | — | — | LIVE OFF 07-06. Moscow false lockout −$24.65 (UUWW SPECI 23.0°C vs hourly 22.0°C; third incident in class). Re-enable: lockout_oracle_divergence study (review 07-13) + n≥100 clean join |
| MIN_LOCKOUT (daily-min) | — | — | — | — | — | LIVE OFF 07-06 (same provenance class). Shadow logger on (37 locked candidates seen this morning, 0 posts ✓) |
| YES-CAPTURE shadow | — | — | — | — | — | INFORMATIONAL ONLY — 07-07 run: 225 would-be fills, markout med −1.9¢ / mean −3.7¢, 95% adverse = winner's-curse confirmation, do not promote |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; stays armed (free option) |
| PEAKSCALP Phase-1 | 427 | 86.7% raw | — | −1.4%/$ after fee | — | REJECTED 07-03 (NO-GO); shadow accrues |
| Band dial time-series | 27 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS; 27 days = noise, do not interpret) |
| Band re-enable trigger | — | — | — | — | — | disp_ratio 0.817 LOCKED (gauge window Jun28–Jul2, isotonic plateau blocks refresh; Jul 3 partial 0.521°C = continued compression) vs 1.10 trigger — NOT MET. ALSO requires equity ≥ 50%·30d-HW (wind-down) |

**This run: 0 READY → live, 0 new cuts (everything bleeding was already off),
wind-down verified holding (posted=0, MIN_LOCKOUT 0 posts, band queue silent).**

Sprint-30 (day 4.0 at 23:50Z tracker): equity $108.35 vs target $160.51 → **−$52.16
behind**. Ladder tally: 8 fired lifetime, 6 resolved 3W/3L net +$56.94; 2 open today
(Tokyo 26°C 56sh @0.37 **partial fill $21.37 of intended $45** + Singapore 32°C
94.75sh @0.462 $44.96). Sleeve reconciled 26.94 → **$50.61** against data-api fills
(state had deducted intended stakes; cash cross-check exact: 108.35−21.37−44.96 =
42.02 ✓). p≈ask coin-flips per design; stated per kernel honesty rule.
