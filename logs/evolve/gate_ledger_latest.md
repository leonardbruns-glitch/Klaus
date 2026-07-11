# Gate Ledger — VPS ground truth, refreshed 2026-07-11 22:15Z (EVOLVE evening)

Source: `band_resolution_join.py` run 2026-07-11 ~21:57Z on VPS (fires 20,901 raw
→ 839 deduped first-fire legs, 596 unique markets, **resolved n=678**). Shadow
hot-log retention now spans 2026-07-01..07-11 only (June legs rotated out —
cumulative gate counts in gatekeeper_report track the longer history).
NEW tonight: winner's-curse cross-tab (`winners_curse_crosstab_0711.md`) —
**simulated join ROI is an upper bound, not an estimator** (realized fills
−75.8% vs same-era sim +7.6%, n=75 trend-grade). Read it before treating any
row below as live-EV.

**CONTEXT 07-11 evening: rails CLEAR third consecutive slot.** Equity **$205.76**
(cash $143.34 CLOB-actual + 2 open ladder shots at TRUE cost $62.42 — London
reconciled 31.75→40.03 vs data-api, MexCity fee-inclusive 21.78→22.39) = **92.3%
of 30d-HW $222.90**; tracked > ruin_floor $89.16. Daily realized +$42.33
(ladder Guangzhou: cost 24.03, 0.99-exit +65.86 + 0.5 sh residual redeem).
Engine 7d realized flow: $0 (all engine paths were dark).

| Slice (Jul-era window) | n res | WR | avg quote | ROI (sim, cond. on fill) | Verdict |
|---|---|---|---|---|---|
| ALL YES legs | 605 | 15.2% | 0.145 | +4.8% | sim-only; winner's-curse discount applies |
| YES d+0 | 27 | 18.5% | 0.186 | −0.6% | COLLECTING |
| YES d+1 | 137 | 17.5% | 0.161 | +8.8% | COLLECTING |
| YES d+2 | 441 | 14.3% | 0.138 | +3.7% | COLLECTING |
| YES off±0 (mode) | 128 | 18.0% | 0.224 | −19.9% | NEGATIVE trend |
| YES off±2 | 236 | 12.7% | 0.095 | +33.7% | sim-only, curse-discount |
| ALL NO legs | 15 | 93.3% | 0.687 | +35.8% | n<40 DATA-COLLECTION |
| YES_PAIR legs | 29 | 31.0% | 0.452 | −31.4% | pair leg split — see combined |
| NO_PAIR legs | 29 | 69.0% | 0.433 | +59.5% | pair leg split — see combined |
| **PAIR combined** (Σ=0.885) | 29 | — | — | **≈+13.0%/pair locked when co-filled** | COLLECTING (n<40); co-fill enforcement = the gate |
| Realized maker fills 06-11..07-06 | 75 | 17.3% | 0.417 | **−75.8% REALIZED** | winner's curse confirmed (trend) |

Gate-keeper cumulative view (unchanged today, band dark day 5): G1 n=934
AMBIGUOUS CI[−10.9,+21.1] · G2c PAIR_FAV_NO CF n=32 ROI +52.9% CI[+12.6,+85.5]
· G3 n=37 · G7 n=382 AMBIGUOUS CI[−11.4,+38.9] · G5/G6 REJECTED (done).

**Flags live right now**: BAND_LIVE=False (dark day 5, S3 trigger unmet:
disp_ratio ≥1.10 on 1/13 confirmed days, median-city ≤0.80 all Jul days) ·
MIN_LOCKOUT_LIVE=True (re-enabled 07-11 22:06Z per pre-registered review;
197/197 margin≥1.0 evidence; $5 maker) · NEG_RISK_ARB + RECYCLE099 on ·
taker YES/NO off · THERMO off · M1β off.

**For the Jul 12 structural review** — the decision-relevant facts:
1. Winner's curse resolved (direction): sim ROI ≠ live ROI; any YES/NO band
   re-enable must cite REALIZED fills or co-fill-locked structures.
2. PAIR_FAV micro-stake is the one structure adverse selection cannot touch
   *when co-filled*; clip-guard (07-05) + a naked-leg kill condition are the
   gates that matter, not CF ROI.
3. S3 dispersion premise still inverted (13/13 confirmed days) — standalone
   YES band premise remains dead.
4. Sub-0.70 book slice sim ROI −29.8% CI[−55,+7.1] (07-10 run) — gate it out of
   any re-enable regardless.
