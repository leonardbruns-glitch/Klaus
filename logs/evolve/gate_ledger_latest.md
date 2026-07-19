# Gate Ledger — refreshed 2026-07-19 14:20 UTC (EVOLVE weekly slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 13:52Z (with the new CROSSING
slice) + live tape (`logs/updown_sniper.jsonl`) + wallet reconcile ($21.4954
CLOB-actual == bankroll exact, 0 opens).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail: candidate tape PF 0.79 over 27 settles). System fully risk-off: sniper
stopped, weather dark, engine ruin_floor $89.16 blocks NEG_RISK/RECYCLE entries,
ladder disarmed. Equity $21.50 < $40 kernel floor — any live re-arm is
owner-only. Burn rate zero; shadow accrues free.**

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT (ts>1784460372) — THE re-enable gate** | **0** | — | — | needs n≥100 AND CI-lo > slice breakeven; ~20 candidates/day → n≥100 ≈ 07-24 | **COLLECTING from zero** |
| CROSSING p≥0.995 5m, all-history (baseline) | 119 | 97.5% | +$7.72 sim | CI-lo 0.9285 vs BE 0.9630 — point clears, CI-lo does NOT | reference only (pre-cut rows never count for re-entry) |
| ~~First-fire "candidate slice"~~ | 59 | 100% | +$13.43 | **CONDEMNED — biased population.** Live fires trigger on p_model CROSSING 0.995; this slice graded windows at their FIRST p≥0.99 snap, excluding late-crossers. The 07-19 −$22.09 loss (first snap 0.9902, fired at 0.9953) was invisible to it. | **VOID — never cite** |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | **−$4.64, PF 0.79** | one crossing-fire loss at Kelly clip $22.09 (50.6% of wallet) erased all 26 wins ($17.45); kill-watch (c) PF<0.8 over ≥20 → cut | **CLOSED — do not pool** |
| v1 pool (unfiltered, TRUE labels) | 169 | 95.9% | −0.51%/$ | CI [91.7,98.0] vs BE 0.962; 15m n=11 WR 81.8% −$8.12 is the bleed | v1 **REJECTED** (07-16 cut re-confirmed) |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (v1 gates, 15m snaps)

Unchanged from 07-18: eth 3+/3W, xrp 4+/4W, sol 0 — capacity 0–1 fires/day/asset
at v1 gates; each needs its own gate sweep before promotion is a live question
(flagged for next weekly; not started 07-19 — one-experiment rule, and the
crossing gate is the binding measurement).

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d): **NOT met** — last 5
  settled days 0.942 / 1.097 / 1.003 / 0.967 / ~0.74. Band stays dark.
- NEG_RISK_ARB / RECYCLE099: enabled per charter carve-out, **0 fills this week**
  (engine ruin_floor $89.16 blocks new entries mechanically).
- Lockout family: all off; evidence base unchanged (197/197 margin≥1.0).

## Measurement notes

- Gate-population bug found by the (dead) 07-19 morning daily and finished by the
  weekly: see experiment `updown_crossing_reenable_gate` in experiments.jsonl.
- Kelly sizing question from research audit 07-19 answered: clip = KELLY_FRAC ×
  live `fetch_usdc_balance()` at fire time (updown_sniper.py:273) — not stale
  bankroll.json. The −50.6%-of-wallet loss was the declared worst case of the
  owner's 50%-Kelly structure operating as designed, not a sizing bug.
