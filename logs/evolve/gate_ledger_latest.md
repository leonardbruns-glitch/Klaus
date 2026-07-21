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
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **57** | **98.3%** (56W/1L) | **+$4.16 sim** | CI-lo 0.9071 vs BE 0.9683 — point WR well above breakeven; accrual 55→57 in ~10.25h (~4.7/hr, slower than the 30/day trend — small-sample noise); n≥100 ETA still ~07-22/07-23 pending accrual pickup | **COLLECTING — CI gap roughly flat (0.904→0.907), still short** |
| CROSSING p≥0.995 5m, all-history (baseline) | 176 | 97.7% | +$11.88 sim | CI-lo 0.9430 vs BE 0.9647 — point clears, CI-lo does NOT (gap ~0.022, consistent with last reading) | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 91 | 98.9% | +$13.18 | CI-lo 0.9403 vs BE 0.9618 — biased-population caveat unchanged; historical record only | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 260 | 96.9% | +0.46%/$ | step 300s n=233 WR 97.4% +$10.79; step 900s n=27 WR 92.6% −$4.89 is the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 116 | 97.4% CI[0.927,0.991] | 0.964 | +$6.09 | n=68 WR 97.1% CI-lo 0.899 BE 0.963 +$2.60 | COLLECTING (unfiltered count past n≥100; p≥.995 sub-slice still short) |
| eth | 20 | 20/20 W | 0.965 | +$3.69 | n=5 5W | COLLECTING |
| xrp | 12 | 12/12 W | 0.963 | +$2.36 | n=4 4W | COLLECTING |
| doge | 8 | 8/8 W | 0.947 | +$2.26 | n=6 6W | COLLECTING |
| sol | 4 | 4/4 W | 0.956 | +$0.95 | n=1 1W | COLLECTING |

BTC unfiltered graded count remains past n≥100 (116, up from 110) at WR 97.4% vs BE
96.4% — still COLLECTING, not a promotion signal on its own (this is the unfiltered
pool, not the operative p≥0.995-crossing gate, and the path is cut regardless). No
alt-asset cell is within reach of n≥100. Promotion is not a live question yet.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 FULL settled days (07-17..07-21, 07-21 partial n=20): 0.967 / 0.849 /
  1.106 / 1.256 / 0.882. Two of five clear 1.10 but three don't — not sustained.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles continuing this slot), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped (journal shows continuous run since the 07-18 20:03Z deploy,
no relaunches). Disk 91% used / 8.4G free — up from 89% this morning, still
watch-not-urgent but trending; next slot should re-check the KEEP_DAYS=10 prune
cron is still running. `git pull --rebase` brought nothing new (already up to
date). No ledger reviews due this slot (the two 07-21 reviews were closed this
morning); `updown_crossing_reenable_gate` measurement updated above (routine,
not a review-date trigger).
