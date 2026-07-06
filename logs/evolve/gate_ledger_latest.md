# Gate ledger — VPS ground truth (EVOLVE daily 2026-07-06 21:53Z run)

Source: `band_resolution_join.py` run ON the VPS 2026-07-06 ~22:00Z (fires 13,771 raw
→ 685 deduped first-fire legs, 446 unique markets, 520 resolved). Join is
window-relative (hot-log window), not cumulative. CIs are Wilson 95% on WR mapped
through ROI = WR/quote − 1. **Standing caveat: conditional-on-fill at OUR shadow
quotes** — this class of join showed +8% while live fills realized −4.9% (06-18) and
−45% (06-26→07-03 tape). It gates SHADOW→further validation, not straight to live.

**CONTEXT 07-06: charter drawdown rail breached (equity $108.35 < 50%·30d-HW $111.45;
daily realized ~−47%). WIND-DOWN deployed this run (commit fccd5e46e): BAND_LIVE,
M1_BETA_PROBE_ENABLED, MIN_LOCKOUT_LIVE all False. Live surface = NEG_RISK_ARB +
RECYCLE099 + redemption (+ principal-authorized sprint ladder, outside charter scope).
All shadow loggers unchanged.**

| Gate / slice | n | WR | avg quote | ROI | ROI CI95 | Verdict |
|---|---|---|---|---|---|---|
| BAND YES (all) | 388 | 13.4% | 0.147 | −9.1% | [−29.5%, +16.7%] | AMBIGUOUS, point-negative. Path OFF (07-03 cut re-confirmed; now also rail wind-down) |
| BAND YES d+2 | 277 | 12.6% | 0.138 | −8.2% | [−33.4%, +23.4%] | AMBIGUOUS |
| BAND YES d+1 | 84 | 15.5% | 0.167 | −7.2% | [−44.4%, +48.1%] | AMBIGUOUS |
| BAND YES d+0 | 27 | 14.8% | 0.187 | −20.7% | [−68.4%, +73.6%] | COLLECTING (n<40), point-negative |
| BAND NO (d+1) | 74 | 74.3% | 0.708 | +5.0% | [−10.6%, +17.1%] | COLLECTING (n<100), CI straddles 0. favNO stays HALTED (07-02 rail: live n=51 WR 39.2%) |
| PAIR_FAV YES legs | 29 | 34.5% | 0.458 | −24.8% | [−56.4%, +15.0%] | COLLECTING (n<40). d+0 subset +4.6% (n=19); d+1/d+2 −70..−100% (n=10) = pre-guard naked-leg contamination |
| PAIR_FAV NO legs | 29 | 65.5% | 0.427 | +53.4% | [+10.8%, +87.5%] | COLLECTING (n<40). Co-filled pair net ≈ +13%/pair — merge works WHEN both legs fill. **Live pairs now OFF (wind-down); counterfactual keeps accruing via shadow-quote rows + pair_clip_skip** |
| PAIR clipped subset | — | — | — | — | — | GATED OFF 07-05 (clip-guard 365d59d04); counterfactual accruing |
| M1β lockout family | — | — | — | — | — | **LIVE OFF 07-06 (this run).** Moscow false lockout −$24.65: UUWW 11:55Z SPECI 23.0°C vs next hourly 22.0°C; running_max locked 23.0; market resolved 22°C ⇒ official-feed max diverged 1°C from WU oracle on ONE uncorroborated ob. Fire depth=0.5 = gate minimum, NO@0.94 (breakeven WR 94%). Third false-lockout incident in class. Re-enable: non-US SPECI-vs-resolution divergence study + n≥100 clean join |
| MIN_LOCKOUT (daily-min) | — | — | — | — | — | LIVE OFF 07-06 (same provenance class, running_min never validated vs resolution). Shadow logger on |
| YES-CAPTURE shadow | — | — | — | — | — | INFORMATIONAL ONLY (92% adverse markout 07-05 — winner's-curse fills) |
| THERMO_MAKER_NO | 125 | — | — | EV≈0 | — | REJECTED (07-03) |
| M1β thin-margin [0.2,0.5)°C | 31 | 74.2% | — | −0.6% | [−20.6%, +24.4%] | REJECTED — reverted 07-04 |
| NEG_RISK_ARB | — | — | — | — | — | Σask floor pinned ~1.000; stays armed (free option) |
| PEAKSCALP Phase-1 | 427 | 86.7% raw | — | −1.4%/$ after fee | — | REJECTED 07-03 (NO-GO); shadow accrues |
| Band dial time-series | ~25 resolved days | — | — | — | — | COLLECTING (gate n≥90 days OOS) |
| Band re-enable trigger | — | — | — | — | — | disp_ratio gauge STALE (window locked Jun28–Jul2, isotonic plateau); last 0.34–0.82 vs 1.10 — NOT MET. Now ALSO requires equity ≥ 50%·30d-HW (wind-down) |

**This run: 0 READY → live, 3 live paths WOUND DOWN per drawdown rail (BAND/pair,
M1β, MIN_LOCKOUT), rest COLLECTING/REJECTED unchanged.**

Sprint-30 (day 3.4): equity ~$108.35 vs target ~$146 → **~−$38 behind** (was +$80
ahead 24h ago — the gap swing IS the ladder variance). Ladder tally: 8 fired lifetime,
6 resolved 3W/3L net +$56.94, sleeve $116.94 (arithmetic exact vs fills). 07-06 both
shots LOST (Singapore 31°C, Shanghai 34°C, $45 each). p≈ask coin-flips per design;
stated per kernel honesty rule.
