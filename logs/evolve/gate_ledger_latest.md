# Gate Ledger — refreshed 2026-07-13 22:10 UTC (EVOLVE evening slot)

Source: `band_resolution_join.py` run ON-BOX 22:05Z (n=741 resolved deduped legs this
join era) + gatekeeper 07-13 + live path logs. **Context: equity $34.86 CLOB-actual =
15.6% of 30d-HW $222.90 — kernel floor breached (owner-waived for UPDOWN-SNIPER only);
all weather live paths mechanically blocked by engine ruin_floor $89.16 and now
flag-dark too. Sim-join ROI is an UPPER BOUND (winners_curse_crosstab_0711); no re-enable
may cite it alone.**

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| BAND YES all (sim join, this era) | 689 | 15.5% | 0.146 | +6.7% | sim upper bound | AMBIGUOUS (dark; rail + curse) |
| BAND YES off±0 | 145 | 15.2% | 0.225 | −32.4% | sim; negative even as upper bound | REJECTED at center |
| BAND YES off±2 | 271 | 14.0% | 0.097 | +45.1% | sim upper bound | AMBIGUOUS |
| YES_PAIR (post-guard era) | 26 | 30.8% | 0.451 | −31.8% | naked-leg curse visible | COLLECTING/NEGATIVE |
| NO_PAIR (post-guard era) | 26 | 69.2% | 0.433 | +59.8% | co-fill pays regardless | COLLECTING (n<40) |
| G3 FILLED_VS_FIRED (realized) | 75 | 17.3% | 0.417 | −75.8% | realized fills 06-11..07-06 | CONFIRMED winner's curse |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |
| S3 disp_ratio ≥1.10×5d | 14d | — | — | — | 1/14 days above, never 2 consecutive | CONDITION NOT MET |
| UPDOWN-SNIPER live (07-13) | 5 fires | 80% TRUE (4W/1L) | 0.97 | −$4.29 | booked −$9.79 was PHANTOM (settle bug, fixed 22:05Z); true loss = one σ-junk fire | COLLECTING (n<40) |
| UPDOWN policy sim on true labels (07-13 tape) | 8 | 87.5% | 0.97 | −$4.02/$40 | one σ-junk loss; with SIG_FLOOR 0.5bp: 6/6 W +$0.83 | COLLECTING |
| UPDOWN shadow n≥100 offline gate | ~194 windows/day | — | — | — | **RES LABELS 84/196 WRONG pre-fix — regrade required from raw snaps + Gamma truth** | REGRADE (fix live 22:05Z) |

Notes:
- Recorder/sniper settlement bug (fixed 2026-07-13 22:05Z, both files): Gamma
  `outcomePrices` polled pre-resolution sum to exactly 1.0 → `winner` defaulted to
  outcomes[1]="Down". 84/196 res labels wrong on 07-13; ALL prior shadow grades for
  updown must be re-derived from snaps joined to post-resolution Gamma truth
  (fetch pattern preserved in daily report 07-13).
- TRUE Chainlink-vs-Binance basis (07-13, n=192 windows): 5 disagreements, all with
  |Binance close-move| < 1bp. 6bp MOVE_FLOOR is a sound fire-time basis guard.
- σ-junk fire mode (real): sig1s 0.195bp/√s → p_model 0.9996 → 13bp reversal (6z) loss.
  SIG_FLOOR=0.5bp/√s deployed 22:05Z (fires-subset-only tightening).
- Data-mirror VPS-side confirmed HEALTHY (15-min pushes landing, cap fresh $34.8585);
  pnl_ledger/calib staleness is in the cloud readers, not the mirror.
