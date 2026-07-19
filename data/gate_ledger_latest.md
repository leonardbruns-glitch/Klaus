# Gate Ledger — refreshed 2026-07-19 22:05 UTC (EVOLVE daily, evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 21:58Z +
`analysis/crypto/updown_asset_grade.py` + live tape (`logs/updown_sniper.jsonl`)
+ wallet reconcile ($21.4954 CLOB-actual, unchanged since the 11:26Z cut, 0 opens,
0 fires/settles since — only `stop_file` skips on the tape).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail: candidate tape PF 0.79 over 27 settles). System fully risk-off: sniper
stopped, weather dark, engine ruin_floor $89.16 blocks NEG_RISK/RECYCLE entries,
ladder disarmed. Equity $21.50 < $40 kernel floor — any live re-arm is
owner-only. Burn rate zero; shadow accrues free.**

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **2** | **50.0%** | **−$4.88 sim** | first two post-cut events split 1W/1L; CI-lo 0.0945 vs BE 0.9580 (meaningless at n=2, but the first loss is data, not noise); needs n≥100 AND CI-lo > BE AND owner floor re-waiver | **COLLECTING — early tape consistent with the cut being right** |
| CROSSING p≥0.995 5m, all-history (baseline) | 121 | 96.7% | +$2.85 sim | CI-lo 0.9181 vs BE 0.9629 — point barely clears, CI-lo does NOT; WR fell 0.9748→0.9669 since the weekly (2 new events, 1 loss) | reference only (pre-cut rows never count for re-entry) |
| 19:05Z regrade cross-check (updown_margin_strata, Gamma truth, 7d) | 129 | 96.9% | +0.6%/$ | CI-lo 0.923 — no cell clears CI; mv≥8bp stratum (n=64 W=63, +2.1%/$, CI-lo 0.917) pre-registered for the gate review, trend-flag only | corroborates: no CI-cleared edge exists yet |
| ~~First-fire "candidate slice"~~ | 61 | 98.4% | +$8.55 | **CONDEMNED — biased population** (fires trigger on CROSSING 0.995; this slice grades at FIRST p≥0.99 snap; the 07-19 loss was invisible to it) | **VOID — never cite** |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins; kill-watch (c) → cut | **CLOSED — do not pool** |
| v1 pool (unfiltered, TRUE labels) | 171 | 95.3% | −1.08%/$ | CI [0.910,0.976] vs BE 0.962; 15m n=11 WR 81.8% −$8.12 is the bleed | v1 **REJECTED** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset

15m-snap cells (v1 gates, `updown_asset_grade.py` 21:59Z): btc n=69 WR 0.957
CI[0.880,0.985] −$3.07; eth n=3 3W; xrp n=5 5W; sol/doge 0 graded — all
COLLECTING, months from n≥100 at current capacity.
**NEW since 19:05Z: eth/sol/xrp/doge 5m shadow snaps live** (verified writing —
each ~360 snaps in the recent tail alongside btc; t_left≤120s zone). Expected
n-collection speedup ~3–5× for `updown_crossing_reenable_gate` breadth once
these accrue; first per-asset 5m grade when snaps span ≥2 days (~07-21).

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d): **NOT met** — last 5
  settled days (07-14..07-18): 0.942 / 1.097 / 1.003 / 0.967 / 0.849. Band dark.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles at 21:56Z), 0 fills — engine
  ruin_floor $89.16 blocks new entries mechanically.
- Lockout family: all off; evidence base unchanged.

## Infra note (this slot)

Disk was 95% (4.8G free) with ~3–4G/day intraday shadow accrual before the 04:00
prune cron. Reclaimed without deleting any data: journal vacuum (3.0G freed) +
gzip of the 3 oldest shadow/hot day dirs (07-10/11/12 — already scheduled for
prune deletion within 1–3 days; compression preserves them instead). Structural
fix (lag_ws_events.jsonl 8.1G live-append, market_ticks.jsonl 2.5G) remains an
owner call — escalated 07-19 19:05Z entry stands.
