# Gate Ledger — refreshed 2026-07-17 22:15 UTC (EVOLVE evening slot; morning slot died on session limit — backlog covered here)

Source: `analysis/crypto/shadow_grade.py --refetch` 21:56Z + candidate live tape
(`logs/updown_sniper.jsonl`) + data-api wallet-truth join +
`analysis/crypto/updown_asset_grade.py` (NEW, first per-asset grade) +
`settled_disp_ratio.py` (rows through 07-17 partial).
**Context: CANDIDATE {P_MIN 0.995, 5m-only} live since 07-16 14:59Z by OWNER
WAIVER; Kelly sized fires (FRAC 0.50, CLIP_CAP $100, RESERVE $5, serial rule,
MAX_LOSSES_DAY 1) by owner waivers 2+3. Sizing Tier-3 owner-only; the loop runs
the kill-watch. v1 tape (PF 0.43, n=36) CLOSED — never pooled.**

## Sniper gates (lead rows)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| **CANDIDATE slice, pooled (p≥0.995 & 5m, TRUE labels)** | **51** | **100%** (51/51) | — | **+$11.73** | Wilson CI-lo **0.9300** vs slice breakeven **0.9570** — does NOT clear yet; zero-loss clear at n≈84 | **COLLECTING** (143/150 toward n≥150 re-decide) |
| CANDIDATE live tape (since 14:59Z waiver) | **18 settles** | **100%** (18W/0L) | 0.965 avg fill | booked **+$9.63**; wallet-true **+$9.02** | Kelly clips $13.7→$18.1 compounding; 5 FOK misses $0 cost (78.3% fill); kill-watch: 0/3 losses, slice point > BE, PF n/a (<20 settles — crosses 20 next slot) | kill-watch **CLEAN** |
| UPDOWN shadow offline gate, POOLED unfiltered | **143** | **95.8%** | 0.963 | **−0.60%/$** (−$4.27/$715) | Wilson CI [91.1, 98.1] vs BE ≈96.3 — **point now BELOW breakeven**; 5m n=134 WR 97.0% +$4.13, 15m n=9 WR 77.8% −$8.41 | v1-policy pool measures **−EV** → the candidate cut was right; edge lives entirely in the candidate slice |
| KELLY activation gate (pre-registered 27f70c6ce) | — | — | — | — | own condition (n≥100 AND CI-lo>BE on candidate slice) still UNMET (0.930 < 0.957) | ON BY OWNER WAIVER — not by gate; Tier-3 owner-only |
| v1 live tape (07-14 fix → cut 07-16 11:27Z) | 36 | 91.7% | 0.962 | −$8.14, PF 0.43 | cut by charter rail | **CLOSED — do not pool** |

## Capacity cells — FIRST PER-ASSET GRADE (v1 gates on 3d of 15m snaps)

| Cell | fires (3d) | graded | WR | BE | Verdict |
|---|---|---|---|---|---|
| eth 15m | 2 | 2 | 2/2 | 0.958 | COLLECTING — **~0.7 fires/day: n≥100 is months away at v1 gates** |
| xrp 15m | 3 | 3 | 3/3 | 0.972 | COLLECTING — same capacity problem |
| sol 15m | 0 | 0 | — | — | v1 gates never fired in 3 days |
| btc (same sim, ref) | 61 | 55 | 96.4% | 0.965 | consistent with pooled gate |

→ Promotion is not a live question until the cells get their own gate sweep
(weekly item): the binding constraint is fires/day, not win rate.

## Measurement notes (this slot's findings)

- **Redemption poach FIXED (commit 8616a0975, live change 1/2 today):**
  `execution.redemption` was market-selling sniper wins at 0.99/0.999 in the
  resolution→auto-redeem gap (2/23 fills poached: −$0.19 vs redemption; ~$1.10
  per poach at $100 clips). Now skips sniper-held tokens (sweep-fix pattern).
- **Unbooked taker fees:** actual buy cost runs ~0.15% (0–0.35%/fire, +$0.416
  on $276 of buys) above the tape's shares×px booking → true breakeven sits
  ~0.1–0.2pp above shadow_grade's avg-ask BE. Does not flip any verdict today
  (candidate slice point is 1.000). Weekly: consider fee-aware BE in the grader.
- **Wallet truth: $35.50 free USDC, 0 opens.** Reconciles to $0.003 against
  data-api activity since 07-16 22:08Z ($28.16). +26%/day, all sniper.
- Candidate economics at Kelly 0.50 unchanged: one loss erases ~25 wins AND
  ends the day (MAX_LOSSES_DAY=1); the kill-watch (≥3 candidate losses
  pre-n=100 / pooled slice point < BE / PF<0.8 over ≥20) is the binding rail.
- Fire cadence day 2: 12 settles in 22h (~0.55/h) + 5 FOK misses; live n=100
  ETA ~1 week at this rate; the pooled slice hits n≈84 zero-loss clear sooner.

## Weather rows (maintenance)

| Slice | n | note | Verdict |
|---|---|---|---|
| S3 disp_ratio ≥1.10 sustained 5d (band re-enable) | settled rows | 07-13 0.675 / 07-14 0.942 / 07-15 1.097 / 07-16 1.003 / 07-17 1.001 (n=24 partial). Yesterday's 07-16 partial read 2.406 → settled at 1.003: partial-day rows overshoot, only settled rows count | **CONDITION NOT MET** |
| NEG_RISK_ARB (always-on) | — | klaus alive, fresh [WA] cycles 22:06Z post-restart; ruin_floor $89.16 blocks engine entries at $35.50 equity | FUNCTIONING (entry-blocked by rail) |
| RECYCLE099 (always-on) | — | scans engine positions only (verified in code this slot); it was NOT the poacher | FUNCTIONING (idle) |
| MIN_LOCKOUT maker | 197/197 | evidence gate passed; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |
