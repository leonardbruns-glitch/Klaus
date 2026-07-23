# Gate Ledger — refreshed 2026-07-23 11:45 UTC (EVOLVE daily, morning slot)

Source: `analysis/crypto/shadow_grade.py --refetch` +
`analysis/crypto/updown_asset_grade.py` + live tape
(`logs/updown_sniper.jsonl`) + wallet reconcile ($21.4954 CLOB-actual, bot.log
11:26Z this slot; 0 opens, 0 fires/settles since the cut — only `stop_file`
skips on the tape; SETTLE count still 88).
**Context: UPDOWN-SNIPER CUT 2026-07-19 11:26Z (`logs/UPDOWN_STOP`, charter PF
rail). System fully risk-off: sniper stopped, weather dark, engine ruin_floor
$89.16 blocks NEG_RISK/RECYCLE entries, ladder disarmed. Equity $21.50 < $40
kernel floor — any live re-arm is owner-only. Burn rate zero; shadow accrues
free.**

## EQUITY CONFIRMED ON-CHAIN (2026-07-23, this slot) — wildcard CLOSED

Full data-api audit of the wallet
(0x21fBa7a743155A9cBE0e04b2C815bC954459842c): **408 positions held, total
currentValue $0.0000** — pure residue of losing tokens (winners were
sold/redeemed in-era). **True equity = $21.4954 cash, exactly. No pending
upside.** The pnl_ledger's "STWA Jul-19 YES leg 146.33sh ⇒ +$143 wildcard" is
**PHANTOM**: no position of that size exists on-chain, the wallet's LAST
activity of any kind (trade/redeem/merge) was 2026-07-19T07:59:46Z (the fatal
$22.18 sniper fire itself), and the ledger-state token id
(`5717613767097074`, 16 digits) is truncated garbage — real CTF token ids are
~77 digits. Same verdict for the Jul-17 ($8.06) and Jul-18 ($3.59) "overdue
STWA opens": no on-chain fills exist on those days. The pnl_ledger equity
band [$21.50–$167] collapses to the point $21.50. Cloud analysts: stop citing
the wildcard; attribute any future capital jump to actual on-chain activity.

## Sniper gates (lead rows)

| Slice | n | WR | ROI | CI / note | Verdict |
|---|---|---|---|---|---|
| **CROSSING p≥0.995 5m, POST-CUT — THE re-enable gate** | **85** | **95.29%** (81W/4L) | **−$5.85 sim** | CI-lo 0.8852 vs BE 0.9644 — **TWO new losses overnight** (was 70W/2L n=72 at 07-22 22:10Z; +13 settles, 2 losses). Point WR is now BELOW breakeven and slice sim-PnL is NEGATIVE for the first time. | **COLLECTING — KILL-LOCKED: with 4 losses at n=85, best-case point WR at n=100 = 96/100 = 0.9600 < BE 0.9644. The pre-registered GATE KILL (post-cut n≥100 ∧ point WR < BE) is now unavoidable unless the next 15 fills' avg ask ≈0.935 (implausible at p≥0.995; slice avg has held ~0.964). At 13–16 settles/day, n≥100 lands ~07-24 morning — that slot executes the kill: experiment KILLED, BTC-5m certainty class closed, graveyard entry.** |
| CROSSING p≥0.995 5m, all-history (baseline) | 204 | 96.57% | +$1.87 sim | CI-lo 0.9309 vs BE 0.9636 — point barely clears, CI-lo does not | reference only (pre-cut rows never count for re-entry) |
| CANDIDATE p≥0.995 5m-only (pre-cut pool) | 104 | 96.15% | +$0.48 | CI-lo 0.9053 vs BE 0.9598 — biased population | **VOID for decisions — never cite** |
| Unfiltered pool (TRUE labels, all steps) | 304 | 96.4% | −$1.13 (−0.07%/$) | step 300s n=273 WR 96.7% +$2.87; step 900s n=31 WR 93.5% −$4.01 remains the bleed | v1 pool reference only |
| CANDIDATE live tape (07-16 14:59Z → cut) | 27 settles | 96.3% (26W/1L) | −$4.64, PF 0.79 | unchanged | **CLOSED — do not pool** |
| KELLY | — | — | — | owner-waived era ended with the cut | **OFF** |

## Capacity cells — per-asset (`updown_asset_grade.py`, 2026-07-23)

| Asset | graded | WR | BE | pnl | p≥.995 sub-slice | Verdict |
|---|---|---|---|---|---|---|
| btc | 132 | 96.2% CI[0.914,0.984] | 0.963 | −$0.84 | n=80 WR 95.0% CI-lo 0.878 BE 0.960 **−$4.90** | **REJECTED** — first cell past n≥100: point WR below BE, CI-lo nowhere near |
| doge | 17 | **16W/1L — FIRST LOSS** 94.1% < BE 0.959 | 0.959 | **−$1.49** | n=9 9W +$2.45 | COLLECTING |
| eth | 35 | 35/35 W CI[0.901,1.000] | 0.967 | +$6.04 | n=11 11W +$2.03 | COLLECTING — **only loss-free cell left** |
| sol | 17 | **16W/1L — FIRST LOSS** 94.1% < BE 0.965 | 0.965 | **−$2.36** | n=5 5W | COLLECTING |
| xrp | 22 | 20W/2L 90.9% < BE 0.960 | 0.960 | **−$5.76** | n=9 7W/2L WR 0.778 **−$7.74** | COLLECTING — worst cell |

**Cross-cell read (honest):** the one-loss-erases-25-wins asymmetry landed in
EVERY cell overnight — doge and sol took their first losses, xrp its second,
btc (the only n≥100 cell) crossed into REJECTED, and the operative post-cut
gate went point-negative. 4 of 5 assets are now net-negative sim. This is not
a BTC-specific failure: the certainty-taker class (buy ~0.96 avg ask on
p≥0.995 model certainty) is failing uniformly wherever n grows. eth's 35/35
is the pattern every other cell showed before its first losses arrived
(btc was 26W/1L at cut; xrp was 14/14W on 07-21). Promotion is not a live
question; the live question is whether ANY cell survives its own n≥100.

## Weather rows (maintenance)

- Band re-enable trigger (settled disp_ratio ≥1.10 × 5d sustained): **NOT
  met** — pooled ratio last 5 settled days (07-18..07-22): 0.849 / 1.106 /
  1.256 / 0.787 / **0.876** (07-22 finalized at n=43, DOWN from yesterday's
  partial 1.105 at n=21). 2 of 5 clear 1.10; streak reset by 07-21 and 07-22.
- NEG_RISK_ARB / RECYCLE099: alive ([WA] cycles running this slot), 0 fills —
  engine ruin_floor $89.16 blocks new entries mechanically (intended).
- Residual weather positions: ZERO real — on-chain audit above confirms all
  408 held tokens are worthless residue.
- NMS note: Synoptic feed HTTP 403 persists (bot.log 11:26Z); weather dark,
  no live impact.

## Health (this slot)

All three services active; liveness watchdog zero restarts since 07-14; no
backlog (07-22 evening ended rc=0). `git pull`: 5 cloud-analyst log commits,
no code, no restart. Disk 87% / 13G free at slot start (~4G/day accrual);
reclaim round 3 this slot: gzip -1 of shadow/hot 07-16..07-20 (16.3G
plaintext, ~15:1 expected → ~15G freed). 7d realized: $0 (no fills, no
settles, wallet static at $21.4954 since 07-19).
