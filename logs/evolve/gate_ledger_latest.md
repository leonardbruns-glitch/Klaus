# Gate Ledger — refreshed 2026-07-16 11:35 UTC (EVOLVE morning slot)

Source: `analysis/crypto/shadow_grade.py --refetch` 11:26Z + live sniper tape
wallet-truth join + `settled_disp_ratio.py` (rows through 07-15).
**Context: UPDOWN-SNIPER PATH CUT this slot (`logs/UPDOWN_STOP` 11:27Z) — charter
path-cut rail fired: post-fix live tape PF 0.43 < 0.8 over 36 resolved, and today's
DAILY_STOP −4.5 was breached at −$7.43 (13W/2L). Cash $26.55 CLOB-actual, 0 open.
The cut is a RAILS action, not an edge falsification — the shadow gate point
estimate still clears breakeven (see below). Shadow recorder unaffected; tape
keeps accumulating toward the re-enable gate.**

## Sniper gates (lead rows)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| UPDOWN shadow offline gate (TRUE labels ≥07-13 22:05Z) | **99** | **97.0%** | 0.963 | +0.77%/$ ($+3.79 on $495) | Wilson CI **[91.5, 99.0]** vs breakeven WR ≈96.3 — point clears, **CI-lo does NOT** | COLLECTING → re-decide at **n≥150** (prompt rule for straddle at n≥100) |
| — step 300s (5m) | 94 | 97.9% | — | +$7.64 | dominant cell, carries the whole edge | COLLECTING |
| — step 900s (15m) | 5 | 80.0% | — | −$3.86 | 1 loss incl. today's live breaching loss | **gate separately at re-enable** |
| — p_model ≥ 0.995 | 39 | **100%** | — | +$9.00 | zero losses | post-hoc slice — pre-registered for re-enable policy |
| — p_model < 0.995 | 60 | 95.0% | — | −$5.21 | **ALL 6 losses (3 shadow + 3 live) sit here**; below breakeven | leading re-enable candidate: P_MIN 0.99→0.995 |
| UPDOWN-SNIPER live post-fix tape (07-14 22:04Z → cut) | **36 settles** | **91.7%** (33W/3L) | 0.962 | **−$8.14** | PF **0.43** (< charter 0.8 rail over ≥20 resolved) → **PATH CUT**; losses label-verified vs Gamma; wallet reconciles to 5¢ | **STOPPED-BY-RAIL** |
| KELLY activation (pre-registered 27f70c6ce) | — | — | — | — | requires n≥100 AND CI-lo > breakeven; at n=99 CI-lo 91.5 < 96.3 | **NOT MET — flag stays OFF; moot while path stopped** |
| eth/sol/xrp 15m capacity cells | 6,270 snaps each today | — | — | — | day 2 of ≥2d recording requirement (started 07-15 15:02Z); BTC-only filter keeps them out of this gate | COLLECTING — first per-asset grade 07-17 |

## Weather rows (maintenance)

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| S3 disp_ratio ≥1.10×5d (band re-enable trigger) | rows→07-15 | — | — | — | last 5 settled days pooled: 0.762 / 0.718 / 0.816 / 0.675 / 0.942 / 1.097 — all <1.10 | **CONDITION NOT MET** |
| NEG_RISK_ARB (always-on) | — | — | — | — | loop alive in klaus (fresh [WA] cycle 11:29Z); last fill activity 07-14 19:20Z; engine ruin_floor $89.16 blocks new entries at equity $26.55 | FUNCTIONING (entry-blocked by rail) |
| RECYCLE099 (always-on) | — | — | — | — | no held winners to recycle; loop alive | FUNCTIONING (idle) |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |

Notes:
- Sniper economics at avg ask 0.963: win ≈ +$0.19/fire vs loss ≈ −$4.85/fire
  (5-share CLOB min) → breakeven WR ≈ 96.3%. The live tape ran 91.7% over 36; the
  shadow tape (all eligible windows, rails-free) ran 97.0% over 99. The divergence
  is coverage (live caught 36 of 99 windows but ALL 3 of the losing ones), plus
  ~9% probability of ≥3 losses in 36 even at true WR 0.97 — not label disagreement.
  Rails don't wait for significance; the gate does. Both did their jobs today.
- Re-enable gate (pre-registered in ledger.jsonl 11:33Z): shadow n≥150 with Wilson
  CI-lo > the re-enable policy's own avg-ask breakeven; candidate policy
  {P_MIN 0.995, 5m-only} graded as its own slice; restart at minimum size.
- System is now fully risk-off: sniper stopped, engine entries blocked by
  ruin_floor $89.16 (0.40 × 30d-HW ratchet), weather flags dark. Equity $26.55 is
  frozen absent auto-redeem dust inflows. Burn rate zero; shadow evidence free.
