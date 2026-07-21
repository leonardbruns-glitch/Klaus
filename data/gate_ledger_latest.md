# Gate Ledger — refreshed 2026-07-21 21:58 UTC (EVOLVE daily; evening slot — 21:53Z run died on usage credits before any measurement, this is the retry-on-default-model recovery)

Source: `analysis/crypto/shadow_grade.py --refetch` +
`analysis/crypto/updown_asset_grade.py` + live tape
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
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **55** | **98.2%** (54W/1L) | **+$3.45 sim** | CI-lo 0.9039 vs BE 0.9696 — point WR well above breakeven; accrual 38→55 in ~13.5h (~30/day, consistent with prior estimate); n≥100 ETA ~07-22/07-23 | **COLLECTING — CI gap narrowing (was 0.865 at n=38), still short** |
| CROSSING p≥0.995 5m, all-history (baseline) | 174 | 97.7% | +$11.17 sim | CI-lo 0.9424 vs BE 0.9651 — point clears, CI-lo does NOT (gap now only ~0.023, narrowest yet) | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 90 | 98.9% | +$12.72 | CI-lo 0.9397 vs BE 0.9623 — biased-population caveat unchanged; historical record only | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 250 | 96.8% | +0.31%/$ | step 300s n=226 WR 97.3% +$9.26; step 900s n=24 WR 91.7% −$5.37 is the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 110 | 97.3% CI[0.923,0.991] | 0.965 | +$4.70 | n=67 WR 97.0% CI-lo 0.898 BE 0.963 +$2.14 | COLLECTING (unfiltered count past n≥100; p≥.995 sub-slice still short) |
| eth | 18 | 18/18 W | 0.964 | +$3.40 | n=5 5W | COLLECTING |
| xrp | 10 | 10/10 W | 0.967 | +$1.70 | n=2 2W | COLLECTING |
| doge | 5 | 5/5 W | 0.948 | +$1.41 | n=3 3W | COLLECTING |
| sol | 4 | 4/4 W | 0.956 | +$0.95 | n=1 1W | COLLECTING |

BTC unfiltered graded count has crossed n≥100 (110) at WR 97.3% vs BE 96.5% — still
COLLECTING, not a promotion signal on its own (this is the unfiltered pool, not the
operative p≥0.995-crossing gate, and the path is cut regardless). No alt-asset cell is
within reach of n≥100. Promotion is not a live question yet.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 FULL settled days (07-16..07-20): 1.003 / 0.967 / 0.849 / 1.106 /
  1.256. Two of five clear 1.10 but three don't — not sustained.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles at 11:24Z today), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped (journal shows continuous run since the 07-18 20:03Z deploy,
no relaunches). Disk 89% used / 11G free — watch, not urgent (prior 07-19
reclaim holding). Backlog: the 07-21 11:23Z slot died immediately on usage
credits before any measurement (`logs/evolve/run_daily_2026-07-21T112300Z.log`)
— nothing to recover, this slot covers the day fresh. Ledger reviews due today
(07-21): split-fill top-up commit and wedge-watchdog retro-registration, both
closed KEEP below (no fires since the cut means neither has fresh exercise
evidence, but no revert condition tripped either).
