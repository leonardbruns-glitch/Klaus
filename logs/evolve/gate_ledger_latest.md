# Gate Ledger — refreshed 2026-07-15 22:15 UTC (EVOLVE evening slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 22:02Z + live sniper tape
wallet-truth join + `settled_disp_ratio.py` (rows through 07-15 partial) + shadow
snap depth scan (`snap_20260715.jsonl`).
**Context: cash $38.48 (22:00Z), 0 open positions — below the $40 kernel floor
(standing 07-13 owner waiver, UPDOWN-SNIPER only) but +$4.44 since the 07-14 22:04Z
fixes. All weather live paths remain mechanically blocked by engine ruin_floor and
flag-dark. 2 live-effect changes already made today (rails 11:34Z, frequency 14:35Z)
— daily anti-thrash cap consumed; this slot is measurement + bookkeeping only.**

## Sniper gates (lead rows)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| UPDOWN shadow offline gate (TRUE labels ≥07-13 22:05Z) | **76** | **98.7%** | 0.962 | +2.66%/$ ($+10.09 on $380) | Wilson CI **[92.9, 99.8]** vs breakeven WR ≈96.2 — point clears, **CI-lo does NOT** | **COLLECTING** (gate n≥100; ~1d to n=100 at post-14:35Z fire rate) |
| — step 300s (5m) | 72 | 98.6% | — | +$8.93 | dominant cell | COLLECTING |
| — step 900s (15m) | 4 | 100% | — | +$1.16 | tiny | COLLECTING |
| UPDOWN-SNIPER live post-fix tape (07-14 22:04Z →) | 17 fills / 17 settles | **100%** | 0.955 | **+$3.64** | hold-to-redemption clean; open={}; consec_loss 0; day realized +$3.54 | COLLECTING (n<40) |
| Sniper execution quality | 22 fire attempts | fill rate **77.3%** | — | — | 5 FAILED = FOK missed a moved/consumed ask, $0 cost; 1 partial fill 3.19 sh (5-sh min applies to order, not fill) | ACCEPTABLE — offline gate n grows on windows, not fills |
| Depth headroom for KELLY sizer (certainty cell, today) | 1,475 snaps | — | — | — | touch ask depth: p10 $31 / med $791 / p75 $2,855; **92% of snaps hold ≥26 sh (≈$25 CLIP_CAP)** | DEPTH NOT BINDING at activation size |
| eth/sol/xrp 15m capacity cells | ~3.9k snaps each | — | — | — | recording since 07-15 15:16Z — **day 1 of ≥2d** requirement; BTC-only filter keeps them out of the live gate ledger | COLLECTING (own n≥100 gate each) |
| KELLY activation (pre-registered 27f70c6ce) | — | — | — | — | requires n≥100 AND CI-lo > breakeven; at n=76 CI-lo 92.9 < 96.2 | **NOT MET — flag stays OFF** |

## Weather rows (maintenance)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| S3 disp_ratio ≥1.10×5d (band re-enable trigger) | rows→07-15 | — | — | — | last 5 settled days: 0.718 / 0.816 / 0.675 / 0.942 / 1.040(07-15 partial, n=20) — all <1.10 | **CONDITION NOT MET** |
| NEG_RISK_ARB (always-on) | — | — | — | — | last activity 07-14 19:20Z (sibling neg-risk fill lock ⇒ it traded); loop alive in klaus | FUNCTIONING |
| RECYCLE099 (always-on) | — | — | — | — | no held winners to recycle (expected while paths dark); loop alive | FUNCTIONING (idle) |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |
| BAND YES/PAIR (sim join rows, morning slot) | 646/13/13 | — | — | — | unchanged from 11:36Z refresh — see git history of this file | AMBIGUOUS / dark |

Notes:
- Sniper economics at avg ask 0.962: win +$0.19/fire vs loss −$4.81/fire (5-share
  CLOB min) → breakeven WR ≈ 96.2%. Point estimate 98.7% is above; the Wilson CI
  lower bound (92.9%) is not. **No sizing change until n≥100 with CI-lo clearing** —
  the pre-registered Kelly activation stays untriggered.
- Wallet reconciliation 07-14 22:04Z → now: observed +$4.44 vs tape-explained +$3.64.
  Residual **+$0.80 unattributed INFLOW** — most plausibly Polymarket auto-redeem of
  residual weather winner dust (Redeemer log: 7 confirmed winners on disk, 100
  "redeemable" dust positions; auto-redeems arrive with no bot tx). Open watch item,
  not a loss; if a residual OUTFLOW ever appears, that is a bug hunt before any fire.
- klaus self-healed once since last slot: 07-15 02:40Z internal watchdog killed a
  stalled event loop (curl 30s timeout in fetch_token_balance) → systemd restart,
  clean recovery. Recurring pattern worth a fix only if frequency rises.
