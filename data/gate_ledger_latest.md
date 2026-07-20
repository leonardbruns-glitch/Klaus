# Gate Ledger — refreshed 2026-07-20 22:00 UTC (EVOLVE daily, evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 21:59Z +
`analysis/crypto/updown_asset_grade.py` 22:00Z + live tape
(`logs/updown_sniper.jsonl`) + wallet reconcile ($21.495442 CLOB-actual,
unchanged since the 07-19 11:26Z cut, 0 opens, 0 fires/settles since — only
`stop_file` skips on the tape).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail: candidate tape PF 0.79 over 27 settles). System fully risk-off: sniper
stopped, weather dark, engine ruin_floor $89.16 blocks NEG_RISK/RECYCLE entries,
ladder disarmed. Equity $21.50 < $40 kernel floor — any live re-arm is
owner-only. Burn rate zero; shadow accrues free.**

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **38** | **97.4%** (37W/1L) | **+$0.61 sim** | CI-lo 0.8650 vs BE 0.9701 — point WR back ABOVE breakeven (was below at the 11:30Z reading, n=25, 0.960<0.9673); CI-lo still far under BE; needs n≥100 AND CI-lo > BE AND owner floor re-waiver; kill rule: n≥100 with point < BE → class closed | **COLLECTING — point flipped back above BE, CI nowhere close** |
| CROSSING p≥0.995 5m, all-history (baseline) | 157 | 97.5% | +$8.33 sim | CI-lo 0.9363 vs BE 0.9647 — point clears, CI-lo does NOT (unchanged verdict since the weekly) | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 80 | 98.75% | +$10.84 | CI-lo 0.9325 vs BE 0.9620 — same biased-population caveat as the first-fire slice; historical record only | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 225 | 96.4% | −0.08%/$ | 5m n=206 WR 97.1% +$5.52; 15m n=19 WR 89.5% −$6.45 is the bleed | v1 pool REJECTED (unchanged) |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py` 22:00Z)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 95 | 96.8% CI[0.911,0.989] | 0.966 | +$1.32 | n=56 WR 96.4% CI-lo 0.879 BE 0.965 −$0.51 | COLLECTING (closest to n≥100 of any cell) |
| eth | 12 | 12/12 W | 0.968 | +$2.01 | n=4 4W | COLLECTING |
| xrp | 8 | 8/8 W | 0.966 | +$1.41 | n=2 2W | COLLECTING |
| sol | 4 | 4/4 W | 0.956 | +$0.95 | n=1 1W | COLLECTING |
| doge | 3 | 3/3 W | 0.950 | +$0.81 | n=1 1W | COLLECTING |

No cell is within reach of n≥100 today; alt-asset recorders continue accruing
at their 07-19 19:05Z rate. Promotion is not a live question yet.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 FULL settled days (07-15..07-19): 1.097 / 1.003 / 0.967 / 0.849 /
  1.106. Only 07-19 grazes the line; not sustained. 07-20 is still accruing
  (partial day, pooled 1.196 on 19/~38 expected buckets — not a settled read).
  Band dark.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles at 21:57Z today), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped. Backlog note: the 07-20 11:23Z slot died on session limits
(`logs/evolve/run_daily_2026-07-20T112316Z.log`) but had already produced real
measurement + a review closure before dying, uncommitted; this slot picked up
and committed that work rather than redoing it. Ledger: closed the overdue
(review_date 07-18) `updown_sniper_live` v1-tape experiment as SUPERSEDED
(folded into `updown_crossing_reenable_gate`); no other reviews due.
