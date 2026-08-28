# EVOLVE Daily Report — 2026-07-22 (morning slot, 11:23Z)

## Health & equity (first)
- **All three services active** (`klaus`, `klaus_updown_sniper`, `klaus_updown_shadow`);
  liveness watchdog **zero restarts since 07-14**; wedge watchdog untripped; no
  CRASHLOOP.flag; no backlog (07-21 evening slot ended rc=0).
- **Equity $21.4954** (CLOB-actual, == bankroll.json exact), **0 open positions**,
  0 fires / 0 settles since the 07-19 11:26Z cut — tape shows only `stop_file`
  skips, SETTLE count still 88. Equity remains **below the $40 kernel floor**:
  standing rail-breach posture, measure-only day, any live re-arm is owner-only.
- **7d realized: sniper tape −$14.86 over 54 settles** (all pre-cut; the window
  still straddles the 07-19 Kelly-clip loss). Weather $0 (0 trades.jsonl rows).
  Burn rate zero; shadow accrual free.

## Sniper gate (the number the loop turns on)
`shadow_grade.py --refetch` 11:32Z — **CROSSING p≥0.995 5m POST-CUT:
n=65, WR 0.9692 (63W/2L), CI-lo 0.8946 vs BE 0.9661, sim +$0.77 → COLLECTING.**

**A second post-cut loss landed since yesterday evening** (was 56W/1L at n=57).
Point WR clears breakeven by only 0.0031 now. Accrual 57→65 in ~13.5h (~14/day);
n≥100 ETA ~07-24/07-25. Trajectory note: with 2 losses at n=65, roughly 2 more
losses by n=100 would put point WR below breakeven — the pre-registered KILL
branch (class closed). Neither pass nor kill triggers today; the gate decides
itself within ~2-3 days.

All-history crossing: n=184 WR 0.9728 CI-lo 0.9380 vs BE 0.9641 (point clears,
CI does not — reference only). The first-fire CANDIDATE slice (n=94 WR 0.9787)
remains VOID for decisions (biased population).

## Capacity cells (per-asset, 11:35Z)
btc graded n=119 WR 0.966 vs BE 0.963 +$1.98 — margin shrank from 07-21 (0.974);
**the operative p≥0.995 sub-slice flipped point-negative: n=71 WR 0.958 < BE
0.961, −$1.50.** eth 25/25W, xrp 14/14W, doge 11/11W, sol 5/5W — all COLLECTING,
none near n≥100. Promotion is not a live question.

## Weather (maintenance)
Settled disp_ratio 07-17..07-21 = 0.967 / 0.849 / 1.106 / 1.256 / **0.787** —
07-21 settled down from its 0.882 partial read; the ≥1.10×5d streak reset. Band
re-enable **NOT met**. NEG_RISK_ARB / RECYCLE099 alive ([WA] cycle 11:25Z),
mechanically blocked from entries by ruin_floor $89.16.

## Actions taken
1. **Reviews closed (both due today, both KEEP, bookkeeping):**
   - UUWW oracle blocklist + `MAKER_EXERCISE_LIVE_MIN_MARGIN_C` 1.0 — revert
     condition (n≥100 clean UUWW contradicting divergence) never fired; zero new
     UUWW data since the lockout family went dark; code verified in place.
   - 07-19 disk reclaim — no analysis needed the gzipped days; prune cron
     deleted 07-10/07-11 on schedule anyway.
2. **Infra health (bookkeeping, not vs 2-cap): disk reclaim round 2.** Disk hit
   94% / 5.9G free (~2.5G/day accrual — ~2 days from a disk-full sensor-blinding
   event). Gzipped plaintext `logs/shadow/hot/2026-07-{13,14,15}` (11.7G →
   808M); all three days outside every active analysis window. Result: **83% /
   17G free.** lag_ws_events.jsonl (8.3G) + market_ticks.jsonl (2.5G)
   live-appends remain owner-only per the 07-19 escalation. Ledger entry, review
   07-25.

## Actions rejected / not taken
- **Live changes: 0/2.** Rail-breach day (equity < kernel floor, path cut) —
  charter posture is measure-and-cut, not optimize. No candidate cleared any
  gate; nothing to act on.
- No re-enable case written to PENDING_HUMAN: gate n=65 < 100 (and CI-lo 0.895
  is nowhere near BE 0.966 anyway).

## Experiments
- `updown_crossing_reenable_gate` — COLLECTING, updated with today's reading;
  review 07-24 (may coincide with the gate resolving itself).
- `updown_multiasset_15m` — COLLECTING, per-asset counts updated; review 07-26.
- No experiments past review date today.

## Standing risks
1. **Gate trending toward the thin edge:** the post-cut slice's point margin is
   +0.0031 over breakeven with the CI 7 points below it. If the class is dead,
   the kill lands at n≥100 within days — do not anticipate it, let the
   pre-registered rule decide.
2. **Disk:** structural growth (two live-append jsonl files, 10.8G combined)
   is untouchable without owner; compression buys ~5-6 days per round.
3. Equity $21.50: one path from here — a CI-clearing measurement, then an owner
   floor/capital decision. Nothing the loop can legally arm today.

---

# Evening slot addendum — 2026-07-22 22:10 UTC

## Health & equity
All three services active; no watchdog restarts; no crashloop; `UPDOWN_STOP`
present. Wallet $21.495442 CLOB-actual, unchanged — 0 fires, 0 settles, burn
rate zero. Disk 85% / 15G free (~2.5G/day accrual; next reclaim ~07-26).
No backlog: the 11:23Z slot ended rc=0.

## Sniper gate (the number the loop turns on)
**CROSSING p≥0.995 5m post-cut: n=72 (70W/2L), WR 0.9722, CI-lo 0.9043 vs
breakeven 0.9665, sim +$1.84 — COLLECTING.** No new loss since the morning
(65→72 all wins); point margin recovered slightly to +0.0057. Accrual ~16/day;
n≥100 ETA ~07-24.

**Pass-branch math (computed this slot, worth stating plainly):** at the
current WR 0.972 the Wilson CI-lo cannot clear breakeven 0.9665 before
n≈3000+; even a loss-free run lifting WR to ~0.98 needs n≈400+. The
pre-registered pass branch (CI-lo > BE at n≥100) is mathematically out of
reach at n=100 with ≥1 loss. The gate will realistically resolve via the KILL
branch (2+ more losses by n=100 ⇒ point < BE) or grind on as COLLECTING. This
is not a reason to change the gate — it is pre-registered and re-arm is
owner-only anyway (equity $21.50 < $40 kernel floor). But nobody should read
"COLLECTING" as "almost ready."

## Per-asset cells
XRP took its **first loss**: 18 graded, 17W/1L, WR 0.944 < BE 0.961, pnl
−$1.50 (p≥.995 sub-slice 5W/1L, −$3.34). One loss at ~0.96 asks erases ~5
wins — the same asymmetry that produced the BTC candidate-tape PF 0.79 cut,
now visible in a second asset. BTC p≥.995 sub-slice remains point-negative
(n=73, WR 0.959 < BE 0.961, −$1.16). eth 29/29W, doge 14/14W, sol 11/11W —
all far from n≥100.

## Weather (maintenance)
Band trigger NOT met (07-18..07-22 settled disp_ratio: 0.849 / 1.106 / 1.256 /
0.787 / 1.105-partial — 2 of 5 clear). NEG_RISK_ARB / RECYCLE099 / lockout
shadows all cycling normally, 0 fills (ruin_floor blocks entries). Synoptic
NMS feed 403ing — no live impact while weather is dark; noted for weather-era
maintenance.

## Actions
- **Live changes: 0/2 today.** Rail-breach posture (equity < kernel floor,
  path cut) — measurement and bookkeeping only, per charter.
- REVIEW-CLOSE (bookkeeping): `execution/redemption.py _redeem_pending`
  sniper-held exclusion, due 07-20, missed by the 07-20/21 slots and caught by
  this slot's reconciliation sweep → **KEEP** (zero redemption activity since
  the cut; both revert conditions untripped; guard fail-open and inert with an
  empty open-dict).
- Experiments updated: `updown_crossing_reenable_gate` (n=72 reading +
  pass-branch math), `updown_multiasset_15m` (XRP first loss).

## Standing risks (unchanged in kind, sharpened in detail)
1. Gate: KILL branch is the realistic resolution; let the pre-registered rule
   decide at n≥100 (~07-24).
2. Disk: compression buys ~5-6 days/round; structural fix owner-only.
3. Equity $21.50: nothing the loop can legally arm; owner decision required
   for any re-entry regardless of gate outcome.
