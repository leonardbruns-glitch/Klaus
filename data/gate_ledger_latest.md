# Gate Ledger — refreshed 2026-07-20 11:30 UTC (EVOLVE daily, morning slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 11:28Z +
`analysis/crypto/updown_asset_grade.py` 11:30Z + live tape
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
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **25** | **96.0%** (24W/1L) | **−$1.02 sim** | CI-lo 0.8046 vs BE 0.9673 — **point WR is BELOW breakeven**; accrual 2→25 in 13.5h (~40/day, n≥100 ETA ~07-22); needs n≥100 AND CI-lo > BE AND owner floor re-waiver; kill rule: n≥100 with point < BE → class closed | **COLLECTING — trending toward the KILL branch, not the pass branch** |
| CROSSING p≥0.995 5m, all-history (baseline) | 144 | 97.2% | +$6.70 sim | CI-lo 0.9308 vs BE 0.9637 — point clears, CI-lo does NOT (unchanged verdict since the weekly) | reference only (pre-cut rows never count for re-entry) |
| ~~First-fire "candidate slice"~~ | 74 | 98.6% | +$10.22 | CI-lo 0.9273 vs BE 0.9606 — **CONDEMNED, biased population** (fires trigger on CROSSING 0.995; this slice grades at FIRST p≥0.99 snap; the 07-19 loss was invisible to it) | **VOID — never cite** |
| Unfiltered pool (TRUE labels) | 204 | 96.1% | −0.40%/$ | CI [0.925,0.980] vs BE 0.963; 15m n=15 WR 86.7% −$7.29 is the bleed; 5m step n=189 WR 96.8% +$3.21 | v1 pool REJECTED (unchanged) |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py` 11:30Z)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 86 | 96.5% CI[0.902,0.988] | 0.965 | +$0.01 | n=50 WR 96.0% CI-lo 0.865 BE 0.964 −$1.23 | COLLECTING |
| eth | 10 | 10/10 W | 0.973 | +$1.40 | n=4 4W | COLLECTING |
| xrp | 6 | 6/6 W | 0.972 | +$0.86 | n=1 1W | COLLECTING |
| sol | 1 | 1/1 W | 0.906 | +$0.52 | — | COLLECTING |
| doge | 1 | 1/1 W | 0.963 | +$0.19 | — | COLLECTING |

Alt-asset 5m shadow recorders (enabled 07-19 19:05Z) verified writing today:
~11,000 5m snaps each (eth/sol/xrp/doge) + btc 23,129 by 11:26Z. No cell is
near its own n≥100 gate; promotion is not a live question.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 settled days (07-15..07-19): 1.097 / 1.003 / 0.967 / 0.849 / 1.106.
  Only 07-19 grazes the line; not sustained. Band dark.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles at 11:25Z today), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped. Disk 85% / 15G free (stable vs 83% after yesterday's
reclaim; lag_ws_events.jsonl 8.1G structural fix remains owner-only per the
standing escalation). Redemption sniper-held guard review closed KEEP (see
ledger 2026-07-20).
