# Gate Ledger — refreshed 2026-07-14 22:15 UTC (EVOLVE evening slot; morning slot died on session limit, this run covers the full day)

Source: `band_resolution_join.py` run ON-BOX 22:08Z (n=760 resolved deduped legs this
join era) + `settled_disp_ratio.py` 22:12Z + wallet-truth reconciliation of the
UPDOWN-SNIPER tape. **Context: equity $34.04 CLOB-actual cash, 0 open positions =
15.3% of 30d-HW $222.90 — kernel floor $40 breached (owner-waived 07-13 for
UPDOWN-SNIPER only); all weather live paths mechanically blocked by engine ruin_floor
$89.16 and flag-dark. Sim-join ROI is an UPPER BOUND (winners_curse_crosstab_0711);
no re-enable may cite it alone.**

| Slice | n | WR | avg quote | ROI | CI / note | Verdict |
|---|---|---|---|---|---|---|
| BAND YES all (sim join, this era) | 722 | 15.5% | 0.146 | +6.3% | sim upper bound | AMBIGUOUS (dark; rail + curse) |
| BAND YES off±0 | 151 | 16.6% | 0.226 | −26.7% | sim; negative even as upper bound | REJECTED at center |
| BAND YES off±2 | 286 | 13.3% | 0.097 | +37.5% | sim upper bound | AMBIGUOUS |
| YES_PAIR (post-guard era) | 19 | 31.6% | 0.457 | −30.8% | naked-leg curse visible | COLLECTING/NEGATIVE |
| NO_PAIR (post-guard era) | 19 | 68.4% | 0.422 | +62.0% | co-fill pays regardless | COLLECTING (n<40) |
| G3 FILLED_VS_FIRED (realized) | 75 | 17.3% | 0.417 | −75.8% | realized fills 06-11..07-06 | CONFIRMED winner's curse |
| MIN_LOCKOUT maker | 197/197 | 100% | margin≥1.0 | — | evidence gate PASSED; flag re-cut 07-13 on equity rail | READY-ON-RAIL-CLEAR |
| S3 disp_ratio ≥1.10×5d | — | — | — | — | pooled 0.71–0.86 all full days Jul 4–10; source rows END 07-11 (n=15 degenerate) — settled-data feed degraded, matches calib_monitor alert | CONDITION NOT MET |
| UPDOWN-SNIPER live tape (go-live 07-13 10:46Z → 07-14 22:03Z) | 25 tracked fires (+1 untracked 39sh @10:49Z) | booked 76% | 0.97 | TRUE −$5.48 (booked −$11.63 INVALID) | **21/25 fills were force-sold at the bid by the engine's window-end orphan sweep** (main.py) — booked labels wrong in BOTH directions (phantom redemption wins; 3 "full losses" actually stop-lossed at 0.95/0.95/0.73). Fixed 22:04Z: sweep now skips sniper-held tokens. | TAPE VOID pre-22:04Z; gate n≥100 restarts on clean hold-to-redemption samples |
| UPDOWN-SNIPER clip/reserve | — | — | — | — | CLIP $5→$2, RESERVE $2→$20 deployed 22:04Z (gate-collection mode; path stops at wallet <$22) | COLLECTING |
| UPDOWN shadow offline gate | regrade from 07-13 snaps | — | — | — | settle-bug fixed 22:05Z 07-13; regrade review 07-15 | REGRADE IN PROGRESS |

Notes:
- **Orphan-sweep interference (found + fixed this run)**: the sniper runs as a separate
  process on the shared wallet; its holds never enter `risk.open_positions`, so
  `_window_end_balance_sweep` treated every sniper fill as an orphan and force-sold at
  the bid in the final 120s (12 ORPHAN_SELLs on 07-14 alone; slippage to 0.88 and
  0.939). Every pre-22:04Z live sniper sample measured "sniper + accidental stop-loss",
  not the registered hold-to-redemption policy. Wallet-truth per-fill join:
  `logs/evolve/daily_report_2026-07-14.md`.
- Cash trajectory fully reconciled: $39.40 (go-live) − $2.89 (untracked 10:49Z fill,
  39.25sh @0.99 sold @0.92) − $2.59 (tracked fills true) ≈ $34.04 now. No unexplained
  leak.
- Redeemer is wallet-wide (data-api `redeemable`), so post-fix sniper winners still
  convert to cash within ~5 min; losers are worthless dust (the 100 "redeemable"
  curPrice=0 stale positions in the log are resolved losers — noise).
- Sniper order-failure mode observed 21:09Z/21:39Z: 2 consecutive FIREs with
  OrderStatus.FAILED, 0 shares (ask taken before our cross landed) — missed fills,
  no capital effect; monitor frequency.
