# Research Audit 2026-08-15T1030Z — STALL day 22

**ABORT: `systemd: failed/unknown` (not active) — service down since 2026-07-24 10:09 UTC (day 22). All four specialist reports confirm abort (exec 07:07, calib 08:07, gatekeeper 09:13, pnl 23:37 prior day). Snapshot fresh (2026-08-15T09:06Z, <1h old). Bankroll $88.750373, 0 open positions, 0 live paths. No analysis fabricated.**

---

## Stall Context (from specialist reports — no fabrication)

| Field | Value |
|---|---|
| Service status | failed/unknown — intentional (owner shutdown 2026-07-24 10:09 UTC, EVOLVE 2026-07-26) |
| Stall duration | 22 days |
| Trade rows | 8,228 (unchanged since stall; last fill ~2026-07-19) |
| Capital | $88.750373 (frozen, CLOB-exact) |
| Open positions | 0 |
| Consecutive zero-fill days | 26 |
| BAND_LIVE | False |
| BAND_NO_ENABLED | False |
| STWA_REGULAR_YES/NO_ENABLED | False |
| All gates | COLLECTING/null — ETAs all infinity |

## Delta vs Prior Report (2026-08-14)

| Metric | 2026-08-14 | 2026-08-15 | Change |
|---|---|---|---|
| Stall day | 21 | 22 | +1 |
| disp_ratio7 alert run | 19 | 20 | +1 |
| Isotonic days since promotion | 69 | 70 | +1 |
| Bankroll | $88.750373 | $88.750373 | 0 |
| Trade rows | 8,228 | 8,228 | 0 |
| Open positions | 0 | 0 | 0 |

## Shadow Loggers (from calib_monitor — active without VPS)

| Logger | Rows today (through 08:05 UTC) |
|---|---|
| flb_screener.jsonl | 1,262,560 |
| updown_sniper/snap_20260815.jsonl | 67,627 |
| maker_flow.jsonl | 36,855 |
| minmax_coherence.jsonl | 522 |
| count_lock.jsonl | 582 |
| badatmath_watch.jsonl | 11 (all ladder type, 0 fill_joins) |

## Critical Pre-Resume Gates (state unchanged from prior report)

1. **disp_ratio7 = 0.781** (last known 2026-07-26; threshold 1.10; **20th consecutive alert firing**). Edge premise unverified 22 days. The band strategy's central load-bearing assumption (implied sigma > realized sigma by ≥10%) was last measured 29pp BELOW threshold. Do NOT re-enable any live path until fresh disp_ratio7 ≥ 1.10 confirmed over ≥7 resolved days post-restart.

2. **Isotonic promotion pending (70 days)** — Candidate (refit 2026-07-23, n_live=3,392) materially outperforms deployed (refit 2026-06-06, n_live=0). Material gap:

   | p_cal grid | deployed | candidate | delta |
   |---|---|---|---|
   | 0.95 | 0.3822 | 0.4374 | **+5.5pp** |
   | 1.00 | 0.6316 | 0.8000 | **+16.8pp** |
   | 0.00–0.90 | within ±2pp | — | immaterial |

   Promote immediately upon VPS restart, **before** any live trading resumes.

3. **G8 updown_crossing KILLED (2026-07-26)** — WR 0.9528 < BE 0.9651 at n=127. Permanent. Do not revisit.

## PROPOSED ACTIONS (human review)

**No action taken — stall protocol active.** Unanimous recommendation from all four specialist reports:

1. **SSH to VPS → `systemctl start klausbot`** — immediately restores STWA pricer, band_struct, THERMO, M1-beta; shadow loggers already accumulating data (22 days of screener + updown sniper rows ready for analysis).
2. **Allow 1–2 settled market days post-restart** — fresh disp_ratio7 computation requires resolved labels, which take ≥1 settlement cycle after pricer comes online.
3. **Promote isotonic candidate on restart** (before live trading) — material calibration improvement banked 70 days; will shift high-confidence signal p_cal from ~0.38 → ~0.44.
4. **disp_ratio7 is the hard gate** — do not set BAND_LIVE=True until fresh disp_ratio7 ≥ 1.10 confirmed over ≥7 consecutive resolved days. Last known value (0.781) is materially below threshold and 22 days stale.

*Nothing changed today. Stall continues. Compounding clock stopped at day 22.*
