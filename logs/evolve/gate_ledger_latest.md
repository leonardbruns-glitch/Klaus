# Gate Ledger — refreshed 2026-07-15 11:36 UTC (EVOLVE morning slot)

Source: `band_resolution_join.py` run ON-BOX 11:27Z (n=672 resolved deduped legs this
join era) + `settled_disp_ratio.py` (rolling-dates fix, rows through 07-14) +
`analysis/crypto/shadow_grade.py --refetch` 11:30Z + live sniper tape wallet-truth.
**Context: cash $37.01 (11:23Z), 0 open positions = 16.6% of 30d-HW $222.90 — kernel
floor $40 breached (standing 07-13 owner waiver, UPDOWN-SNIPER only); all weather live
paths mechanically blocked by engine ruin_floor $89.16 and flag-dark (band dark day 9).
Sim-join ROI is an UPPER BOUND (winners_curse_crosstab_0711); no re-enable may cite it
alone.**

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| BAND YES all (sim join, this era) | 646 | 15.9% | 0.146 | +9.4% | sim upper bound | AMBIGUOUS (dark; rail + curse) |
| BAND YES off±0 | 133 | 17.3% | 0.226 | −23.5% | sim; negative even as upper bound | REJECTED at center |
| BAND YES off±2 | 259 | 12.7% | 0.095 | +33.5% | sim upper bound | AMBIGUOUS |
| YES_PAIR (post-guard era) | 13 | 38.5% | 0.443 | −13.1% | naked-leg curse visible | COLLECTING/NEGATIVE |
| NO_PAIR (post-guard era) | 13 | 61.5% | 0.427 | +44.2% | co-fill pays regardless | COLLECTING (n<40) |
| G3 FILLED_VS_FIRED (realized) | 75 | 17.3% | 0.417 | −75.8% | realized fills 06-11..07-06 | CONFIRMED winner's curse |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |
| S3 disp_ratio ≥1.10×5d | rows→07-14 | — | — | — | **feed RESTORED 07-15** (hard-coded DATES list ended 07-10 — script bug, not a dead upstream; now rolls last 18 day-dirs). Pooled 07-11..07-14: 0.718 / 0.816 / 0.675 / 0.942 — all <1.10 | CONDITION NOT MET |
| UPDOWN-SNIPER live post-fix tape (07-14 22:04Z →) | 9 fills / 9 settles | 100% | 0.955 | +$2.08 on ~$42.4 (+4.9%/$) | hold-to-redemption clean; state reconciles (open={}); 3 FAILED fires = missed crosses, $0 effect | COLLECTING (n<40) |
| UPDOWN shadow offline regrade (TRUE labels ≥07-13 22:05Z) | 32 | 96.9% | 0.964 | +0.59%/$ | Wilson CI [84.3, 99.4] vs breakeven WR ≈96.4 — **CI does not clear breakeven** | COLLECTING (~41 true-labeled incl. live; gate n≥100) |
| UPDOWN-SNIPER effective clip | — | — | — | — | **CLOB 5-share buy min ⇒ true fire cost $4.50–4.95, not $2** — every post-fix fill was exactly 5.0 sh. Rails re-based on est_cost=max(CLIP,5·ask) + DAILY_STOP 6→4.5 (commit 7e569bb46, 11:34Z) | RAILS CORRECTED |

Notes:
- The 07-14 "CLIP $2" ledger entry never reduced per-fire exposure — order_manager
  snaps BUY size up to the exchange 5-share minimum. Runway math must use ~$4.9/fire:
  one full-clip loss ≈ 14% of equity, hence the day now halts on realized ≤ −$4.5.
- Reserve gate now stops fires at wallet < $20 + est_cost (~$24.9 at ask 0.98); before
  the fix it could take the wallet to ~$17.1.
- Sniper economics at avg ask 0.955: win +$0.235/fire vs loss −$4.78/fire → breakeven
  WR ≈ 95.3%. The regraded shadow WR point estimate (96.9%) is above, the CI is not.
  This stays a gate-collection path, not a compounding engine, until n≥100.
- band dark day 9; audit.log: "no WEATHER trades in last 1d" ×6 days — expected, not
  an anomaly, while flags are dark and ruin_floor blocks entries.
