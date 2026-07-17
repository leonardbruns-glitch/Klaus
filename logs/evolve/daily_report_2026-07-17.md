# EVOLVE daily report — 2026-07-17 (evening slot 21:53Z; morning 11:23Z slot died on session limit, backlog covered here)

## Health
All three services active (`klaus`, `klaus_updown_sniper`, `klaus_updown_shadow`);
liveness watchdog log clean since 07-14 (no restarts needed). No CRASHLOOP flag,
no UPDOWN_STOP. `klaus` restarted once by this run at 22:05Z to deploy the
redemption guard — fresh `[WA]` cycle verified 22:06:50Z.

## Equity & PnL
- **Wallet: $35.50 free USDC, 0 open positions anywhere.** Reconciles to $0.003
  against data-api activity — fully attributed, no unknown flows.
- Candidate live tape since the 07-16 14:59Z waiver: **18/18 wins, booked
  +$9.63, wallet-true +$9.02** (+34% on the $26.55 waiver-day base in ~31h).
- 7d realized context: v1 tape −$8.14 (cut 07-16) + candidate +$9.02 → sniper
  net ≈ +$0.9 since the 07-14 orphan-fix; weather paths dark, $0.
- Equity remains below the $89.16 engine ruin_floor — all engine paths stay
  entry-blocked; the sniper (own rails) is the sole live path by owner waiver.

## Sniper gate — the number the loop turns on
- **CANDIDATE slice (p≥0.995, 5m): n=51, WR 1.000, CI-lo 0.9300 vs slice
  breakeven 0.9570 → COLLECTING.** Point clears; CI-lo clears at ≈n=84 if losses
  stay zero. 143/150 graded toward the n≥150 re-decide.
- Pooled unfiltered gate: n=143, WR 0.958 **below** BE 0.963 (−0.60%/$) — the
  v1 policy measures −EV at n>100; the 15m step (n=9, WR 0.778, −$8.41) is the
  main bleed. This retroactively validates the 07-16 cut; kills apply per-slice.
- Kill-watch: (a) candidate live losses 0/3; (b) slice point 1.000 > BE;
  (c) PF n/a (<20 settles — crosses 20 next slot). **CLEAN.**
- Kelly: pre-registered gate still unmet (CI-lo < BE); ON by owner waiver,
  sizing Tier-3 owner-only. Clips $13.7→$18.1 tracking 0.50×(wallet−5).

## Actions taken (live-effect: 1 of 2 cap)
1. **`execution/redemption.py` sniper-held exclusion (commit 8616a0975,
   Tier-1).** Wallet-truth audit found the engine's redemption module racing PM
   auto-redeem on every sniper win and market-selling 2/23 fills at 0.99/0.999
   in the resolution→auto-redeem gap (−$0.176 on 07-17 = 24% of that fire's
   profit; ~$1.10/poach at $100 clips). Same fail-open guard as the 07-14 sweep
   fix. Deployed, restarted, verified. Sibling finding: ~0.15% unbooked taker
   fees on fills (+$0.416/$276) — documented, no verdict flipped; weekly to
   consider fee-aware breakeven in the grader.

Shadow-only (not vs cap): new `analysis/crypto/updown_asset_grade.py` per-asset
grader; gate ledger / experiments / state_log refreshed; two due reviews closed
(07-14 sweep exclusion → KEEP; 07-14 CLIP/RESERVE → SUPERSEDED by owner waivers).

## Actions rejected / not taken
- No candidate policy change (kill-watch clean, n<100 — nothing to decide).
- No Kelly gate action (owner-owned; gate condition unmet but waived).
- No weather re-enable: disp_ratio settled 5d 0.675/0.942/1.097/1.003/1.001 —
  all <1.10, condition NOT met (07-16 partial 2.406 settled to 1.003 — only
  settled rows count).
- No per-asset cell promotion: **first grade shows the v1 gates produce ~0–1
  fires/day/asset on eth/sol/xrp 15m (eth 2, xrp 3, sol 0 in 3 days)** — n≥100
  is months away; cells need their own gate sweep (weekly item) before
  promotion is a live question.

## Experiments
- `updown_sniper_candidate_live` COLLECTING — day 2, 18/18 W, kill-watch clean.
- `updown_shadow_offline_gate` COLLECTING — 143/150; candidate slice carries
  the entire measured edge.
- `updown_multiasset_15m` COLLECTING — first per-asset grade done; review
  extended to 07-21 (capacity, not accuracy, is the open question).

## Standing risks
- **One candidate loss ≈ −$18 (full clip) and ends the day** (MAX_LOSSES_DAY 1);
  at 50% Kelly a losing streak is ruin-shaped if true WR < ~0.965. The
  kill-watch triggers are the only brake — they were checked this slot and are
  armed.
- Session-limit slot deaths continue (3 of last 6 slots): each gap delays the
  kill-watch by up to 10.5h. Mechanical rails (MAX_LOSSES_DAY, in-flight stop,
  UPDOWN_STOP file) carry the risk between slots.
- Taker-fee booking gap (~0.15%) slightly understates all live breakevens.
