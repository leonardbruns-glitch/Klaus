# EVOLVE Daily Report — 2026-07-13 (evening slot 21:53Z; covers 07-12 + 07-13 backlog)

## First paragraph, honestly
The system is in a deep drawdown and below every capital floor. Equity is **$34.86
cash, zero open positions** (reconcile_positions.py 22:00Z) = **15.6% of the 30d
high-water $222.90**. The 48h collapse ($205.76 → $34.86) is **100% sprint-ladder
variance shots** (0W/7L, −$164.7 at cost, 07-11→07-13) plus a true −$4.29 day-1 on
UPDOWN-SNIPER. The ladder was disarmed by the interactive session at 09:25Z
(INVARIANTS #2); the kernel floor breach was explicitly owner-waived at 10:46Z to arm
UPDOWN-SNIPER. `klaus` is active with fresh cycles; engine weather paths are fully
dark (0 resolved engine trades in 7d) and mechanically blocked by ruin_floor $89.16.

## Service health
- `klaus` active, restarted 22:06Z after MIN_LOCKOUT revert; fresh `[WA]` cycle lines.
- `klaus_updown_sniper` + `klaus_updown_shadow` active, restarted 22:04Z with fixes.
- Sprint ladder cron healthy in DRY mode (10-min cadence, DRY_FIRE path verified).
- Data-mirror VPS-side healthy: 15-min pushes landing (cap $34.8585 fresh). The
  pnl_ledger/calib "22h stale" aborts are cloud-reader-side, not mirror-side.
- Backlog: 07-12 both slots + 07-13 morning died on Claude session limits; this run
  covered their review dates and reports.

## Equity & PnL
- Equity $34.86 (all cash). 7d: −$170.90 (equity 07-06 ~$108 → 34.86 net of the 07-09/10
  recovery peak; trajectory $205.76 on 07-11 → $34.86 on 07-13).
- Today realized: ladder settles Toronto −$16.42, Tokyo −$23.12, Shanghai −$23.68
  (all fired pre-disarm); UPDOWN-SNIPER TRUE −$4.29 (4W/1L; booked −$9.79 was phantom).
- Engine paths: $0 (dark). trades.jsonl 7d resolved n=0.

## Actions taken (all cuts/fixes — breached-rail day, STEPS 3–4 skipped per prompt)
1. **UPDOWN settle-booking bug fixed** (updown_sniper.py + updown_shadow.py):
   pre-resolution Gamma outcomePrices (sum exactly 1.0) were accepted and winner
   defaulted to "Down" → **84/196 of today's shadow labels wrong; a true WIN booked as
   a −$5.33 loss** (wallet redeemed +$5.50, confirmed by cash reconcile). Winner now
   requires exact sorted(outcomePrices)==[0,1]; positions are never booked without a
   true resolution. All pre-fix updown shadow grades are void → REGRADE (experiments).
2. **SIG_FLOOR 0.5bp/√s** added to sniper p_model (Tier-1 risk-tighten, health
   severity): the day's one true loss fired at sig1s 0.195bp/√s → p_model 0.9996,
   then a 13bp (6z) reversal. Full-day tape on TRUE labels: policy v1 = 8 fires 7W/1L
   −$4.02; with floor = 6 fires 6W/0L +$0.83. The floor can only remove fires.
3. **State corrected to wallet truth** (realized −9.79 → −4.29). The −$6 day-stop had
   tripped on phantom accounting and blocked a further winning fire.
4. **MIN_LOCKOUT_LIVE True → False** — pre-registered 07-11 revert_condition fired
   (equity <50% 30d-HW at a 21:53Z computation). 0 orders posted while live; $0 impact.
5. Reviews closed (backlog): fill-cost recording KEEP; PAIR clip-guard EXTEND→07-20;
   07-06 wind-down KEEP (deepened); ladder retro-reg + KERNEL_FLOOR guard OBSOLETE by
   disarm — guard flaw recorded (at-cost masking; re-arm must mark-to-market).

## Actions REJECTED (with the failed gate)
- **Any weather-path optimization** — breached-rail day (equity 15.6% of HW): cutting
  only. Fresh join (n=741) YES sim +6.7% remains an UPPER BOUND (winner's curse n=75
  realized −75.8%); does not qualify as enabling evidence.
- **Overriding owner-set sniper rails (clip/day-stop)** — owner sized them at arm time
  today; same-day override would re-litigate an explicit owner decision. Tension
  recorded in ESCALATIONS (worst-case day ≈ 32% of current equity).
- **Killing UPDOWN-SNIPER outright** — charter path-cut needs PF<0.8 over ≥20 resolved;
  n=5 (TRUE 4W/1L). Its true day-1 result is one σ-junk loss, now guarded by SIG_FLOOR.
- **Re-seeding the ladder sleeve** — ladder disarmed by INVARIANTS #2; owner re-arm only.

## Experiments
- `updown_sniper_live`: COLLECTING, day 1 TRUE 4W/1L −$4.29; kill = PF<0.8 @ n≥20, or
  2 further true losses at floored p_model≥0.99, or owner word. Review 07-16.
- `updown_shadow_offline_gate`: REGRADE-REQUIRED (labels bug); nightly re-join of snaps
  to post-resolution Gamma truth; accumulate to n≥100. Review 07-15.
- `band_reenable_trigger` (S3): unmet (1/14 days ≥1.10, never 2 consecutive).
- `pair_clip_cofill`: frozen, 0 post-guard live pairs possible while dark.

## Standing risks
1. Equity $34.86 below all floors; only live path is owner-waived UPDOWN-SNIPER.
   One worst-case sniper day ≈ −$11 ≈ 32% of equity — see ESCALATIONS for the
   proportionality flag (deposit or shrink rails).
2. UPDOWN edge is unproven at n=5 true fires; the tape-cell evidence (WR 0.95–1.0)
   conditions on ask, while the live policy conditions on model-market disagreement —
   selection against our own model error is the residual worry. The n≥100 regraded
   shadow gate decides.
3. Cloud analyst lanes read stale midnight snapshots ("bankroll $87.40" vs true
   $34.86); their staleness alarms are reader-side. VPS gate ledger is the truth file.
4. Weekly slot 07-12 (13:41Z) also died on session limits — BAND_LIVE structural
   decision (pair shadow-posting mode) remains unmade; next weekly 07-19.
