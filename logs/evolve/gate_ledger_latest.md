# Gate Ledger — refreshed 2026-07-22 11:40 UTC (EVOLVE daily, morning slot)

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
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **65** | **96.9%** (63W/2L) | **+$0.77 sim** | CI-lo 0.8946 vs BE 0.9661 — **a SECOND post-cut loss landed since 07-21** (was 56W/1L); point WR now clears breakeven by only 0.0031; accrual 57→65 in ~13.5h (~14/day); n≥100 ETA ~07-24/07-25 | **COLLECTING — point margin thin, CI far short; 2 losses at n=65 means ≥2 more losses by n=100 likely trips the KILL branch (point<BE)** |
| CROSSING p≥0.995 5m, all-history (baseline) | 184 | 97.3% | +$8.50 sim | CI-lo 0.9380 vs BE 0.9641 — point clears, CI-lo does NOT (gap ~0.026, slightly wider than 07-21's ~0.022) | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 94 | 97.9% | +$8.86 | CI-lo 0.9257 vs BE 0.9606 — biased-population caveat unchanged | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 274 | 96.7% | +0.22%/$ | step 300s n=246 WR 97.2% +$7.77; step 900s n=28 WR 92.9% −$4.75 is the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 119 | 96.6% CI[0.917,0.987] | 0.963 | +$1.98 | n=71 WR 95.8% CI-lo 0.883 BE 0.961 **−$1.50 (point BELOW BE)** | COLLECTING — the p≥.995 sub-slice flipped point-negative this slot |
| eth | 25 | 25/25 W | 0.964 | +$4.74 | n=7 7W | COLLECTING |
| xrp | 14 | 14/14 W | 0.959 | +$3.03 | n=5 5W | COLLECTING |
| doge | 11 | 11/11 W | 0.952 | +$2.79 | n=7 7W | COLLECTING |
| sol | 5 | 5/5 W | 0.955 | +$1.20 | n=1 1W | COLLECTING |

BTC unfiltered graded n=119 WR 96.6% vs BE 96.3% — past n≥100 in count but the
margin shrank again (97.4%→96.6% since 07-21) and the operative p≥0.995 slice is
point-NEGATIVE (−$1.50 on n=71). No alt-asset cell is within reach of n≥100.
Promotion is not a live question.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT met**
  — last 5 settled days (07-17..07-21): 0.967 / 0.849 / 1.106 / 1.256 / 0.787.
  07-21 settled DOWN to 0.787 (from 0.882 partial) — the streak reset; only 2 of
  5 clear 1.10.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycle 11:25Z this slot), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged. UUWW blocklist + margin 1.0
  review closed KEEP today (no contradicting data; path dark).

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; wedge
watchdog untripped. `git pull` brought cloud-analyst log files only (no code, no
restart). Disk hit 94% / 5.9G free at slot start (~2.5G/day accrual) — second
reclaim round executed this slot: gzip of plaintext shadow/hot 07-13..07-15
(11.7G, outside every active analysis window; settled_disp_ratio 5d reads
07-17+, sniper graders read `logs/shadow/updown_sniper/`). Structural fix
(lag_ws_events.jsonl 8.3G, market_ticks.jsonl 2.5G live-appends) remains
owner-only per the 07-19 escalation. Reviews closed today: UUWW
blocklist+margin (KEEP), 07-19 disk reclaim (KEEP). 7d realized: sniper tape
−$14.86 over 54 settles (all pre-cut; window still straddles the 07-19 loss);
weather $0.
