# EVOLVE daily report — 2026-07-18 (evening slot 21:53Z; morning slot died rc=1 at 11:32Z after committing its work)

## Health
All three services active at 22:05Z (`klaus`, `klaus_updown_sniper`, `klaus_updown_shadow`);
no CRASHLOOP.flag, no UPDOWN_STOP. **But the sniper was DARK 8.2h today (11:30–19:57Z):**
the 11:30 deploy restart left the process wedged from birth — alive per systemd, zero
outbound HTTP — while the shadow logged 660 fireable candidate snaps it never saw.
Diagnosed and fixed 20:03Z (in-process wedge watchdog: self-exit if Gamma discovery
silent >5min, systemd relaunches; commit ee014ba92, retro-registered in ledger, review
07-21). Post-restart silence verified benign: shadow saw 7,894 snaps / **0 fireable**
BTC candidates since 20:03Z → quiet market, not a re-wedge; watchdog untripped.
Liveness-watchdog log otherwise clean; backlog check: morning slot's work (split-fill
fix 5b06af1c8 + 4 review-closes) landed before it died — no unworked backlog.

## Equity & PnL
- **Wallet $38.11 free USDC, 0 open positions** (sniper + weather). Day booked +$1.91
  (3/3 wins pre-wedge); wallet-true ≈ +$2.62 — gap fully attributed (+$0.79 pre-fix
  split-fill on the 00:54Z fire, −$0.08 unbooked taker fees). Reconciles to cents.
- 7d realized −$8.23 raw over 82 settles, decomposed: VOID pre-07-14-fix rows −$11.63,
  dead v1 tape −$8.14 (cut 07-16, PF 0.43), **candidate tape +$11.54 (21W/0L)**.
  trades.jsonl 7d: $0.00 (ORPHAN bookkeeping rows only) — weather dark, as intended.
- Equity $38.11 sits below the $40 kernel figure. The owner's 07-16 interactive waiver
  (trading authorized from $26.55, per the 07-13 owner-escalation precedent) governs;
  three prior slots upheld this reading and equity has risen daily since ($26.55 →
  $38.11, +43% in 2 days). Engine weather paths are separately entry-blocked by their
  ratcheted floor ($89.16). Kill-watch remains the operative control.

## Sniper gate status (the number the loop turns on)
- **CANDIDATE slice (p≥0.995, 5m-only, true labels): n=55, WR 1.000, CI-lo 0.9347 vs
  slice BE 0.9583 → COLLECTING** (zero-loss CI clear ≈ n=84–88).
- Candidate live tape since 07-16 14:59Z waiver: **27 fires / 21 fills (77.8%) /
  21W-0L, +$11.54 booked**, Kelly clips $12.3→$18.9, 6 FOK misses at $0 cost.
- Kill-watch CLEAN day 3 on all three terms: (a) 0/3 candidate live losses;
  (b) slice point WR 1.000 > BE; (c) PF rail first measurable today (21 ≥ 20
  settles): zero losses → PASS.
- Pooled v1-policy gate n=156 WR 0.962 < BE 0.963 past the n≥150 re-decide point —
  the 07-16 cut is re-confirmed (15m slice n=11 WR 0.818 −$8.12 is the bleed).
- Kelly formal gate (n≥100 AND CI-lo>BE) still UNMET — ON by owner waiver, Tier-3.

## Actions taken today (cap 2/2, both before this slot)
1. Split-fill top-up `_reconcile_fill` (commit 5b06af1c8, morning slot, ledger 1/2,
   review 07-21) — measurement-integrity tighten.
2. Wedge watchdog (commit ee014ba92, 20:03Z session, retro-registered this slot,
   review 07-21) — health tighten.
- **This slot: 0 live changes** (measurement + bookkeeping only, cap exhausted and
  no gate produced a candidate action anyway).

## Actions REJECTED / not taken
- Kelly activation by gate: REJECTED — n=55 < 100 and CI-lo 0.9347 < BE 0.9583.
- Gate kill / UPDOWN_STOP: REJECTED — all kill-watch terms clean.
- eth/sol/xrp cell promotion: REJECTED — eth n=3, xrp n=4, sol n=0 (capacity-bound;
  per-asset gate sweep is the weekly item; 15m-based cells must not inherit the
  5m-only candidate policy since BTC-15m measures −EV).
- Weather band re-enable: CONDITION NOT MET — settled disp_ratio 07-13..07-17 =
  0.675 / 0.942 / 1.097 / 1.003 / 0.967, never ≥1.10, let alone 5d sustained.

## Experiments
- `updown_sniper_candidate_live` — EXTENDED, review 07-20 (kill-watch each slot).
- `updown_shadow_offline_gate` — EXTENDED, review 07-21; v1 pool REJECTED at n≥150,
  candidate slice COLLECTING toward n≈84–88.
- `updown_multiasset_15m` — unchanged, review 07-21 (day 3–4 tapes: eth 3/3W, xrp
  4/4W, sol 0 fires).
- Weather standing condition `band_reenable_trigger` — not met (above).

## Standing risks
1. **Silent-failure surface remains wider than the watchdog:** gj() maps all errors
   to None and pre-rail gates are silent continues — the watchdog now bounds
   discovery wedges (~5min) but a signal-path wedge with live discovery would still
   look like a quiet market. Mitigation available if it recurs: shadow-vs-live
   fireable-snap cross-check (used twice today) could be mechanized.
2. Concentration: 100% of live edge in one cell (BTC-5m certainty-taker) at 50%
   Kelly per fire; MAX_LOSSES_DAY=1 caps a bad day at ~−50% of wallet. Declared
   ceiling stands — next raise needs evidence/cells/capital, not nerve.
3. Zero-loss streak (42/42 shadow-era + 21/21 live) still cannot bound WR below
   ~0.935 — the first live loss is the most informative event ahead; kill-watch
   terms are pre-registered for it.
4. Wedge cost ~8h of cadence today → live n=100 ETA slips ~1 day (~1 week out).
