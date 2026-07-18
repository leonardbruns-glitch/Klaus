# Gate Ledger — refreshed 2026-07-18 22:05 UTC (EVOLVE evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 21:57Z + candidate live tape
(`logs/updown_sniper.jsonl`) + wallet reconcile + `analysis/crypto/updown_asset_grade.py`
+ `settled_disp_ratio.json` (settled through 07-17).
**Context: CANDIDATE {P_MIN 0.995, 5m-only} live since 07-16 14:59Z by OWNER
WAIVER; Kelly sizing (FRAC 0.50, CLIP_CAP $100, RESERVE $5, serial rule,
MAX_LOSSES_DAY 1) by owner waivers 2+3 — Tier-3 owner-only; the loop runs the
kill-watch. v1 tape (PF 0.43, n=36) CLOSED — never pooled. Sniper was DARK
11:30–19:57Z today (process wedge from the 11:30 deploy restart; diagnosed and
watchdog-fixed 20:03Z, commit ee014ba92 — see state_log).**

## Sniper gates (lead rows)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| **CANDIDATE slice, pooled (p≥0.995 & 5m, TRUE labels)** | **55** | **100%** (55/55) | — | **+$12.25** | Wilson CI-lo **0.9347** vs slice breakeven **0.9583** — does NOT clear yet; zero-loss clear ≈ n=84–88 | **COLLECTING** |
| CANDIDATE live tape (since 14:59Z waiver) | **21 settles** | **100%** (21W/0L) | 0.965 avg ask | booked **+$11.54** (wallet-true ≈ +$12.3 incl. the pre-fix split-fill +$0.79) | Kelly clips $12.3→$18.9; fill rate 21/27 (77.8%), 6 FOK misses $0 cost; kill-watch (a) 0/3 losses (b) slice point 1.000 > BE (c) PF rail (21≥20 settles): 0 losses → PASS | kill-watch **CLEAN day 3** |
| UPDOWN shadow offline gate, POOLED unfiltered (v1 policy) | **156** | **96.2%** | 0.963 | **−0.26%/$** (−$2.01/$780) | Wilson CI [91.9, 98.2] vs BE ≈96.3 — point below breakeven past the n≥150 re-decide point (5m n=145 WR 97.2% +$6.10; 15m n=11 WR 81.8% −$8.12 is the bleed) | v1 pool **REJECTED** (cut 07-16 stands); edge lives in the candidate slice only |
| RE-ENABLE formal gate (07-16 11:33Z pre-registration) | 156 total | — | — | — | candidate slice CI-lo 0.9347 < slice BE 0.9583 → formal gate still UNMET (path live by owner waiver, not by gate) | UNMET — COLLECTING |
| KELLY activation gate (pre-registered 27f70c6ce) | — | — | — | — | own condition (n≥100 AND CI-lo>BE on candidate slice) still UNMET (n=55, 0.9347 < 0.9583) | ON BY OWNER WAIVER — not by gate; Tier-3 owner-only |
| v1 live tape (07-14 fix → cut 07-16 11:27Z) | 36 | 91.7% | 0.962 | −$8.14, PF 0.43 | cut by charter rail | **CLOSED — do not pool** |

## Capacity cells — per-asset grade (v1 gates, 15m snaps, day 3–4)

| Cell | fires | graded | WR | BE | Verdict |
|---|---|---|---|---|---|
| eth 15m | 3 | 3 | 3/3 | 0.963 | COLLECTING — ~0.8 fires/day: n≥100 months away at v1 gates |
| xrp 15m | 4 | 4 | 4/4 | 0.972 | COLLECTING — same capacity problem |
| sol 15m | 0 | 0 | — | — | v1 gates have never fired in 4 days |
| btc (same sim, ref) | 68 | 62 | 96.8% | 0.966 | consistent with pooled gate; its p≥.995 sub-slice n=36 WR 97.2% |

→ Binding constraint is fires/day, not win rate. Cells need their own gate
sweep (weekly item) before promotion is a live question. Candidate policy is
5m-only and BTC-15m measures −EV — a 15m-based non-BTC cell needs its own
policy, not the candidate's.

## Measurement notes (this slot's findings)

- **8.2h dark period today (11:30–19:57Z):** the 11:30 deploy restart wedged the
  sniper process (alive per systemd, zero outbound HTTP). Diagnosed + fixed
  20:03Z with an in-process wedge watchdog (exit if Gamma discovery silent
  >300s; systemd relaunches). Since the 20:03 restart: 0 sniper events, and the
  shadow recorded 7,894 snaps with **0 fireable BTC candidates** in the same
  window → post-fix silence is a quiet market, NOT a re-wedge (during the
  actual wedge the shadow saw 660 fireable snaps the sniper missed). Watchdog
  has not tripped (no relaunches since 20:03).
- **Wallet truth: $38.11 free USDC, 0 opens (sniper + weather).** Delta since
  07-17 23:50Z +$2.62 vs booked +$1.91 — gap fully attributed: +$0.79
  wallet-true on the 00:54Z pre-fix split-fill fire, −$0.08 unbooked taker
  fees. No unattributed flows.
- **7d realized (raw tape −$8.23 / 82 settles) decomposes by era:** pre-07-14
  fix VOID rows −$11.63 (25), dead v1 tape −$8.14 (36), candidate tape
  **+$11.54 (21W/0L)**. trades.jsonl 7d: $0.00 (23 ORPHAN bookkeeping rows) —
  weather contributed nothing, as expected while dark.
- Fire cadence: 3 settles today, all 00:00–04:30Z (then the wedge ate the day).
  Live n=100 ETA pushed right by the dark hours; pooled candidate slice hits
  its n≈84–88 zero-loss CI clear first.

## Weather rows (maintenance)

| Slice | n | note | Verdict |
|---|---|---|---|
| S3 disp_ratio ≥1.10 sustained 5d (band re-enable) | settled days | pooled_ratio 07-13 0.675 / 07-14 0.942 / 07-15 1.097 / 07-16 1.003 / 07-17 0.967 (median_city_ratio all ≤0.892) | **CONDITION NOT MET** |
| NEG_RISK_ARB (always-on) | — | klaus alive, fresh [WA] cycles 21:55Z; engine ruin_floor $89.16 blocks entries at $38.11 equity | FUNCTIONING (entry-blocked by rail) |
| RECYCLE099 (always-on) | — | engine-position scan only; idle with weather dark, 0 weather opens | FUNCTIONING (idle) |
| MIN_LOCKOUT maker | 197/197 | evidence gate passed; flag re-cut 07-13 on equity rail; 37 locked candidates/cycle, 0 posts | READY-ON-RAIL-CLEAR |
