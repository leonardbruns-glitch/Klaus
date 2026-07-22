# Gate Ledger — refreshed 2026-07-22 22:10 UTC (EVOLVE daily, evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` +
`analysis/crypto/updown_asset_grade.py` + live tape
(`logs/updown_sniper.jsonl`) + wallet reconcile ($21.495442 CLOB-actual,
unchanged since the 07-19 11:26Z cut, 0 opens, 0 fires/settles since — only
`stop_file` skips on the tape; SETTLE count still 88).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail: candidate tape PF 0.79 over 27 settles). System fully risk-off: sniper
stopped, weather dark, engine ruin_floor $89.16 blocks NEG_RISK/RECYCLE entries,
ladder disarmed. Equity $21.50 < $40 kernel floor — any live re-arm is
owner-only. Burn rate zero; shadow accrues free.**

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **72** | **97.2%** (70W/2L) | **+$1.84 sim** | CI-lo 0.9043 vs BE 0.9665 — no new loss since the morning slot (was 63W/2L n=65); point +0.0057 over BE; accrual 65→72 in ~10.5h (~16/day); n≥100 ETA ~07-24 | **COLLECTING — PASS-BRANCH MATH (new): at WR 0.972 the Wilson CI-lo cannot clear BE before n≈3000+; even loss-free to WR≈0.98 needs n≈400+. Realistic outcomes: KILL branch at n≥100 (2+ more losses ⇒ point<BE) or indefinite grind. Re-arm is owner-only regardless (equity < $40 floor)** |
| CROSSING p≥0.995 5m, all-history (baseline) | 191 | 97.4% | +$9.56 sim | CI-lo 0.9402 vs BE 0.9643 — point clears, CI-lo does NOT (gap ~0.024) | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 97 | 97.9% | +$9.55 | CI-lo 0.9279 vs BE 0.9605 — biased-population caveat unchanged | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 286 | 96.9% | +0.34%/$ | step 300s n=257 WR 97.3% +$9.27; step 900s n=29 WR 93.1% −$4.45 is the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 123 | 96.7% CI[0.919,0.987] | 0.963 | +$2.61 | n=73 WR 95.9% CI-lo 0.886 BE 0.961 **−$1.16 (point BELOW BE)** | COLLECTING — p≥.995 sub-slice still point-negative |
| eth | 29 | 29/29 W | 0.966 | +$5.22 | n=10 10W | COLLECTING |
| xrp | 18 | **17W/1L — FIRST LOSS** WR 94.4% < BE 96.1% | 0.961 | **−$1.50** | n=6 5W/1L WR 0.833 −$3.34 | COLLECTING — one loss at these asks erased ~5 wins; certainty-taker asymmetry now visible in a second asset |
| doge | 14 | 14/14 W | 0.956 | +$3.28 | n=9 9W | COLLECTING |
| sol | 11 | 11/11 W | 0.966 | +$2.00 | n=3 3W | COLLECTING |

BTC unfiltered graded n=123 WR 96.7% vs BE 96.3% — past n≥100 in count but the
CI-lo (0.919) is far below BE and the operative p≥0.995 slice is point-NEGATIVE
(−$1.16 on n=73). XRP flipped from 14/14W to net-negative on a single loss —
the same one-loss-erases-the-slice asymmetry that killed the BTC candidate
tape. No alt-asset cell is within reach of n≥100. Promotion is not a live
question.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 settled days (07-18..07-22): 0.849 / 1.106 / 1.256 / 0.787 / 1.105
  (07-22 partial, n=21). Only 2 of 5 clear 1.10; 07-21 at 0.787 anchors a reset
  streak.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles running 21:55Z this slot,
  MIN_LOCKOUT shadow logging 35 candidates / 0 live posts), 0 fills — engine
  ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.
- NMS note: Synoptic feed returning HTTP 403 (WARNING in bot.log); weather is
  dark so no live impact — feed-key check is a weather-era task.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped. `git pull`: already up to date (no code, no restart). Disk
85% / 15G free (83% this morning, ~2.5G/day accrual → next reclaim round due
~07-26; structural fix for lag_ws_events.jsonl 8.3G + market_ticks.jsonl 2.5G
live-appends remains owner-only per the 07-19 escalation). Reviews closed this
slot: execution/redemption.py `_redeem_pending` sniper-held exclusion (due
07-20, missed by the 07-20/21 slots, caught by reconciliation — KEEP, both
revert conditions untripped, guard inert while the path is cut). 7d realized:
sniper tape −$14.86 over settles in window (all pre-cut); weather $0; wallet
static.
