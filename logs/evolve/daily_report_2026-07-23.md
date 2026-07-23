# EVOLVE daily report — 2026-07-23 (morning slot, 11:23 UTC)

## Health
All three services active (`klaus`, `klaus_updown_sniper`, `klaus_updown_shadow`);
zero liveness-watchdog restarts since 07-14; no crashloop flag; no backlog (07-22
evening slot ended rc=0). `git pull`: 5 cloud-analyst log commits, no code, no
restart needed. `logs/UPDOWN_STOP` present and honored (tape shows only
`stop_file` skips). Disk reclaim round 3 executed this slot: gzip of shadow/hot
07-16..07-20 → disk 87%→**71%** (28G free), no data deleted.

## Equity & PnL — wildcard CLOSED, equity now exact
**Equity $21.4954 — cash only, CONFIRMED on-chain this slot.** Full data-api
audit of the wallet: 408 positions held, total current value **$0.0000** (losing
-token residue). The pnl_ledger's "$143 STWA Jul-19 wildcard" (and the Jul-17/18
"overdue opens", $14.58 combined at cost) is **PHANTOM** — the wallet's last
on-chain activity of ANY kind was 2026-07-19T07:59:46Z (the fatal sniper fire),
no 146.33-share position exists, and the ledger-state token id is 16-digit
truncated garbage (real ids ~77 digits). The equity uncertainty band
[$21.50–$167] that cloud reports have carried for 3+ days collapses to the point
**$21.50**. 7d realized: $0.00 (zero fills, zero settles, wallet static since
07-19). Equity remains BELOW the $40 kernel floor — rail-breach posture held,
any live re-arm is owner-only.

## Sniper gate — the number the loop turns on (BAD NIGHT)
**CROSSING p≥0.995 5m post-cut: n=85, 81W/4L, WR 0.9529, CI-lo 0.8852 vs
breakeven 0.9644, sim PnL −$5.85 → point WR BELOW breakeven, slice
net-negative, for the first time.** Two new losses landed overnight (was 70W/2L
n=72 at the 07-22 evening slot; +13 settles, 2 losses).

**KILL-LOCK:** with 4 losses at n=85, the best-case point WR at n=100 is
96/100 = 0.9600 < BE 0.9644. The pre-registered GATE KILL (post-cut n≥100 ∧
point WR < BE) is now mathematically unavoidable unless the next 15 fills drag
the slice avg-ask below 0.960 (would need ~0.935 avg — implausible at p≥0.995).
At the current 13–16 settles/day, n≥100 lands ~07-24 morning; **that slot
executes the kill: experiment KILLED, BTC-5m certainty class closed, graveyard
entry.** Not killed early today at n=85 — pre-registered gates execute as
written, and there is no operational difference (path already cut, $0 at risk).

## Capacity cells — class-wide deterioration
Per-asset (`updown_asset_grade.py`): **btc n=132 → REJECTED** (first cell past
n≥100; WR 0.962 < BE 0.963, −$0.84; p≥.995 sub-slice n=80 WR 0.950 −$4.90).
**doge 16W/1L (first loss, −$1.49)**, **sol 16W/1L (first loss, −$2.36)**,
**xrp 20W/2L (−$5.76; p≥.995 slice −$7.74)**. eth 35/35W (+$6.04) is the only
loss-free cell — and its record matches what every other cell looked like
before its first losses arrived. 4 of 5 assets net-negative sim. The failure is
the certainty-taker CLASS (one loss at ~0.96 asks erases ~25 wins), not a
BTC-specific defect. Promotion is nowhere near a live question.

## Weather (maintenance)
Band re-enable trigger NOT met: pooled disp_ratio 07-18..07-22 = 0.849 / 1.106 /
1.256 / 0.787 / 0.876 (07-22 finalized DOWN from yesterday's partial 1.105).
NEG_RISK_ARB/RECYCLE099 alive in-code, mechanically blocked by ruin_floor
$89.16 > equity (intended). Zero real weather positions (on-chain confirmed).
Synoptic NMS feed still HTTP 403 — no live impact while weather is dark.

## Actions taken
1. (bookkeeping) Disk reclaim round 3 — gzip shadow/hot 07-16..07-20, 87%→71%,
   registered in ledger.jsonl, review 07-26.
2. (bookkeeping) Wildcard closure — on-chain wallet audit, phantom STWA
   positions falsified, gate ledger + this report carry the correction for the
   cloud analysts.
3. Gate ledger refreshed (kill-lock math recorded); experiments.jsonl updated
   (crossing gate → COLLECTING-KILL-LOCKED; multiasset cells → class-wide
   deterioration noted).

**Live changes: ZERO** (0/2 cap used; 18th consecutive zero-live-change slot).
Rail-breach day (equity < $40 floor) — cutting/measurement only, per prompt.

## Actions rejected
- Early kill of `updown_crossing_reenable_gate` at n=85: rejected — the
  pre-registered condition evaluates at n≥100; killing early changes the rules
  mid-experiment for zero operational benefit.
- Any weather/band action: trigger not met (2 of 5 days ≥1.10, streak reset).

## Experiments
- `updown_crossing_reenable_gate`: COLLECTING-KILL-LOCKED, review 07-24 —
  expected to formalize KILL at n≥100 tomorrow.
- `updown_multiasset_15m`: COLLECTING, review 07-26 — btc cell REJECTED by
  grader; eth the only clean cell.
- All others unchanged (killed/void/standing per experiments.jsonl).

## Standing risks
1. **Capital $21.50 < $40 kernel floor** — nothing can trade; owner decision
   (deposit or wind-down) is the only path back to live.
2. Certainty-taker class failing uniformly as n grows — if tomorrow's kill
   lands, the loop has NO candidate live path; next value is honest reporting
   + cheap shadow accrual (eth cell, weather triggers), not new risk.
3. Disk accrual ~4G/day from live-append shadow feeds — round-3 reclaim buys
   ~5 days; structural fix (rotate/cap the growers) remains owner-only per the
   07-19 escalation.
4. pnl_ledger cloud routine carries phantom-position state — corrected in this
   report + gate ledger; if its next report still cites the wildcard, its
   state file needs a manual purge (VPS-side fix, trivial, flagged not done —
   the state file belongs to the cloud routine's write path).
