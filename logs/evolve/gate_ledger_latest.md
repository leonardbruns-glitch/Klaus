# Gate Ledger — refreshed 2026-07-16 22:05 UTC (EVOLVE evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 21:58Z + candidate live tape
(`logs/updown_sniper.jsonl`) wallet-truth join + `settled_disp_ratio.py` (rows
through 07-16 partial).
**Context: CANDIDATE {P_MIN 0.995, 5m-only} went LIVE 14:59Z by OWNER WAIVER of
the n≥150 re-enable gate, then OWNER WAIVERS 2+3 activated sized fires
(UPDOWN_KELLY=1, KELLY_FRAC 0.50, CLIP_CAP $100, RESERVE $5, serial-fire rule,
MAX_LOSSES_DAY 1). See ledger.jsonl 14:59/15:06/15:14Z for full kill-watch terms.
Sizing is Tier-3 owner-only; the loop's job is the kill-watch. The v1 tape
(PF 0.43, n=36, cut 11:27Z) is CLOSED and never pools into candidate rails.**

## Sniper gates (lead rows)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| **CANDIDATE slice, pooled (p≥0.995 & 5m, TRUE labels)** | **44** | **100%** (44/44) | — | **+$10.46** | Wilson CI-lo **0.9197** vs slice breakeven **0.9557** — does NOT clear yet; at zero losses clears at n≈84 | **COLLECTING** (117/150 total graded) |
| CANDIDATE live tape (fires since 14:59Z waiver) | **5 settles** | **100%** (5W/0L) | 0.972 fill | **+$1.70** on ~$69 = +2.5%/$ | Kelly-sized clips $13.7–14.2 verified; 1 FOK miss $0 cost; serial-fire skips logged working | kill-watch CLEAN: 0/3 losses, PF n/a (<20), slice point 1.00 > BE |
| UPDOWN shadow offline gate, pooled (TRUE labels ≥07-13 22:05Z) | **117** | **96.6%** | 0.963 | +0.29%/$ ($+1.72 on $585) | Wilson CI [91.5, 98.7] vs breakeven ≈96.3 — point clears, CI-lo does not | COLLECTING → n≥150 |
| — step 300s (5m) | 111 | 97.3% | — | +$5.43 | dominant cell | COLLECTING |
| — step 900s (15m) | 6 | 83.3% | — | −$3.71 | excluded from candidate policy | stays excluded |
| KELLY activation gate (pre-registered 27f70c6ce) | — | — | — | — | own condition (n≥100 AND CI-lo>BE on candidate slice) still UNMET (CI-lo 0.9197 < 0.9557) | **ON BY OWNER WAIVER 2/3** — not by gate; Tier-3 owner-only |
| v1 live tape (07-14 22:04Z → cut 11:27Z) | 36 | 91.7% | 0.962 | −$8.14 | PF 0.43 → path cut by rail | **CLOSED — do not pool** |
| eth/sol/xrp 15m capacity cells | 12,002 snaps each today | — | — | — | day 2 healthy (btc 57,878); btc-* filter keeps them out of this ledger | COLLECTING — first per-asset grade 07-17 slot |

## Weather rows (maintenance)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| S3 disp_ratio ≥1.10×5d (band re-enable trigger) | rows→07-16 | — | — | — | last 5 settled days: 0.816 / 0.675 / 0.942 / 1.097 / 2.406 — the 2.406 is TODAY PARTIAL (n=17 markets), not a sustained-5d signal | **CONDITION NOT MET** — watch 07-17 full-day row |
| NEG_RISK_ARB (always-on) | — | — | — | — | klaus alive, fresh [WA] cycles 21:58Z; engine ruin_floor $89.16 blocks entries at equity $28.16 | FUNCTIONING (entry-blocked by rail) |
| RECYCLE099 (always-on) | — | — | — | — | no held winners; loop alive | FUNCTIONING (idle) |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |

Notes:
- Wallet truth: $28.16 free USDC, 0 open positions anywhere. Back-chained from
  the last fire's Kelly clip (last_clip $13.79 = 0.50 × $27.58, +$0.57 win →
  $28.15) — reconciles to 1¢; full-day chain from the morning's $26.55 closes to
  ~10¢ (<0.4% equity). No unattributed inflow this slot.
- Candidate economics at Kelly 0.50: clip ≈ $14, win ≈ +$0.28–0.57/fire, loss ≈
  −$14/fire (full clip) → slice breakeven WR ≈ 95.6% at avg ask 0.956. One loss
  erases ~25 wins AND ends the day (MAX_LOSSES_DAY=1). Growth ≈ +1–2%/fire if
  the 44/44 slice edge is real; ruin-shaped if true WR < ~0.965 — that is what
  the kill-watch (≥3 candidate losses pre-n=100 / pooled point < BE / PF<0.8
  over ≥20) exists to catch.
- Fire cadence since waiver: 6 fires in ~6.2h (~1/h) — the candidate policy is
  ~4× more selective than v1 (P_MIN 0.995 + 5m-only). n=100 live fills ETA
  ~4 days at this rate; the pooled slice hits its n≈84 zero-loss clear sooner.
- stop_file caveat from the morning slot RESOLVED: `why=stop_file` skip lines
  logged 14:43–14:45Z before the waiver removed the file — the code path fired
  as designed.
