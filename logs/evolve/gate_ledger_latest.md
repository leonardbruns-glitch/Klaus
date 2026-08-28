# Gate Ledger — refreshed 2026-07-23 22:05 UTC (EVOLVE daily, evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` +
`analysis/crypto/updown_asset_grade.py` + live tape
(`logs/updown_sniper.jsonl`) + wallet reconcile ($21.495442 CLOB-actual this
slot, == bankroll.json exact; 0 opens, 0 fires/settles since the cut — only
`stop_file` skips on the tape; SETTLE count still 88).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail). System fully risk-off: sniper stopped, weather dark, engine ruin_floor
$89.16 blocks NEG_RISK/RECYCLE entries, ladder disarmed. Equity $21.50 < $40
kernel floor — any live re-arm is owner-only. Burn rate zero; shadow accrues
free.**

## EQUITY (confirmed on-chain 2026-07-23 morning — wildcard CLOSED)

True equity = **$21.4954 cash, exactly**; the 408 held tokens are worthless
residue (data-api audit, morning slot). The pnl_ledger "STWA wildcard +$143"
is PHANTOM (truncated token id, no on-chain fills on the claimed days; last
wallet activity 2026-07-19T07:59:46Z = the fatal sniper fire). Cloud
analysts: do not cite the wildcard; the equity band collapses to $21.50.

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **88** | **95.45%** (84W/4L) | **−$5.52 sim** | CI-lo 0.8889 vs BE 0.9649 — no new loss since morning (+3 settles, all W); point WR still BELOW breakeven, slice sim-PnL still negative | **COLLECTING — KILL-LOCKED: with 4 losses at n=88, best-case point WR at n=100 = 96/100 = 0.9600 < BE 0.9649. The pre-registered GATE KILL (post-cut n≥100 ∧ point WR < BE) remains unavoidable on any realistic ask path. ACCRUAL SLOWED: 85→88 in ~10.5h (~7/day vs 13–16/day earlier) — n≥100 ETA slips to ~07-25; the kill executes whenever n≥100 lands, review date 07-24 rolls forward if needed. $0 at risk meanwhile.** |
| CROSSING p≥0.995 5m, all-history (baseline) | 207 | 96.62% | +$2.21 sim | CI-lo 0.9319 vs BE 0.9638 — point barely clears, CI-lo does not | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 105 | 96.19% | +$0.57 | CI-lo 0.9061 vs BE 0.9600 — biased population | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 315 | 96.5% | +$0.12 (+0.01%/$) | step 300s n=283 WR 96.8% +$3.97; step 900s n=32 WR 93.8% −$3.86 remains the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | unchanged | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`, 2026-07-23 21:56Z)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 134 | 96.3% CI[0.916,0.984] | 0.963 | −$0.65 | n=81 WR 95.1% CI-lo 0.880 BE 0.961 **−$4.81** | **REJECTED** — point WR at BE, CI-lo nowhere near |
| doge | 20 | 19W/1L 95.0% < BE 0.961 | 0.961 | **−$1.06** | n=11 11W +$2.79 | COLLECTING |
| eth | 38 | 38/38 W CI[0.908,1.000] | 0.968 | +$6.32 | n=13 13W +$2.22 | COLLECTING — **only loss-free cell left** |
| sol | 17 | 16W/1L 94.1% < BE 0.965 | 0.965 | **−$2.36** | n=5 5W +$0.70 | COLLECTING |
| xrp | 23 | 21W/2L 91.3% < BE 0.961 | 0.961 | **−$5.67** | n=9 7W/2L WR 0.778 **−$7.74** | COLLECTING — worst cell |

**Cross-cell read (unchanged from morning, still honest):** 4 of 5 assets are
net-negative sim; btc (the only n≥100 cell) is REJECTED; the certainty-taker
class (buy ~0.96 avg ask on p≥0.995 model certainty) is failing uniformly
wherever n grows. eth's 38/38 (CI-lo 0.908 vs BE 0.968) is the same pattern
every other cell showed before its first losses arrived. Promotion is not a
live question; the live question is whether ANY cell survives its own n≥100.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT
  met** — pooled ratio last 5 settled days (07-18..07-22): 0.849 / 1.106 /
  1.256 / 0.787 / 0.876. 2 of 5 clear 1.10. 07-23 partial reads 1.091 at n=20
  of ~40 expected — not settled, excluded per the 07-20 precedent.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles at 21:54Z this slot,
  LOCKOUT_SHADOW + MIN_LOCKOUT logging candidates, 0 live posts), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically (intended).
- Residual weather positions: ZERO real (on-chain audit, morning slot).

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; no
backlog (07-23 morning ended rc=0). `git pull`: already up to date — no code,
no restart. Disk 73% / 26G free (round-3 reclaim holding). 7d realized:
sniper tape −$6.34 over 22 settles (21W/1L — the window now spans the
candidate-era wins and the 07-19 −$22.09 fatal loss; zero fills since);
weather $0 (0 trades.jsonl WEATHER_STWA rows). Live-effect changes today:
0/2 across both slots.
