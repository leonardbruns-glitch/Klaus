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

---

# EVENING ADDENDUM — 21:53 UTC slot

**Health:** all three services active; watchdog zero restarts since 07-14; no
CRASHLOOP flag; no backlog (morning slot ended rc=0); `git pull` already up to
date (no code, no restart). Disk 73% / 26G free — round-3 reclaim holding.

**Equity:** $21.495442 CLOB-actual, == bankroll.json exact, 0 opens, 0
fires/settles since the 07-19 cut (tape = stop_file skips only). Still below
the $40 kernel floor → measure-only slot, re-arm remains owner-only. 7d
realized: sniper tape −$6.34 over 22 settles (21W/1L — candidate-era wins plus
the 07-19 −$22.09 fatal loss now dominate the window); weather $0.

**Gate (the operative number, shadow_grade --refetch 21:56Z):** CROSSING
p≥0.995 5m post-cut **n=88 (84W/4L), WR 0.9545, CI-lo 0.8889 vs BE 0.9649,
sim −$5.52** — +3 settles since morning, all wins, no state change: point WR
still below breakeven, KILL-LOCK math unchanged (best-case 96/100 = 0.9600 <
BE at n=100). **Accrual slowed to ~7/day (was 13–16), so n≥100 slips to
~07-25**; the pre-registered kill executes at whichever slot first reads
n≥100 with point < BE. Not killed early — gates run as written, $0 at risk
meanwhile. All-history n=207 WR 0.9662 CI-lo 0.9319 vs BE 0.9638 (point
clears, CI does not — unchanged).

**Cells (updown_asset_grade 21:56Z):** btc n=134 REJECTED (WR 0.963 = BE,
−$0.65); doge 19W/1L −$1.06; sol 16W/1L −$2.36; xrp 21W/2L −$5.67; eth 38/38
+$6.32 sole loss-free cell (CI-lo 0.908 vs BE 0.968, far from clearing). No
promotion candidate.

**Weather:** band trigger NOT met (07-18..07-22 settled: 0.849/1.106/1.256/
0.787/0.876, 2 of 5; 07-23 partial 1.091 n=20 excluded as unsettled).
NEG_RISK/RECYCLE alive ([WA] 21:54Z), ruin_floor-blocked, 0 fills.

**Actions taken:** measurement + bookkeeping only — gate ledger refreshed,
experiments.jsonl evening readings appended, state_log appended. **Live
changes: ZERO (0/2 across both slots; 19th consecutive zero-live-change
slot).** No ledger reviews due (all closed through 07-22; next: crossing-gate
review 07-24, disk-reclaim r3 07-26, multiasset 07-26).

**Standing risks:** unchanged from the morning report, with one update — the
kill now likely formalizes 07-24 evening or 07-25 rather than 07-24 morning
(accrual slowdown). The consequence stands: when it lands, the loop has no
candidate live path, and with equity at $21.50 the only route back to live
trading is an owner decision.
