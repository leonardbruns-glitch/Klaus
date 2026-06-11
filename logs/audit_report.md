# VOLARB Quantitative Audit — 2026-06-11 18:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-11T18:01:47Z (10.4 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather; 0 open positions) |
| Capital | $196.78 (prior audit 2026-06-11T12:18Z: $101.48; Δ=+$95.30 — STWA activity, bankroll-proportional stakes deployment, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 30th consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~23.2 days retired) |
| drift_status | N/A — data-mirror does not contain `strategy/volarb.py`; mirror-file-present condition false → no DEPLOY_LAG. Dev-branch code has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` dict — spec's scalar `EDGE_FLOOR=0.15` does not exist. |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — CLOSED DATASET) |
| Open `audit/volarb-*` PRs | NONE (GitHub confirmed) |
| Run | **30th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19 UTC: `volarb_strategy=None`, import removed from main.py.
- 2026-05-29 UTC: CLAUDE.md reoriented to STWA; all crypto/VOLARB sections removed.
- `strategy/volarb.py` not present on live mirror. **Any patch to this file has zero operational effect.**

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (10.4 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($196.78) |
| Code-drift guard | mirror-file-present condition FALSE (data-mirror is data-only; no `strategy/volarb.py`) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-11T12:01Z .. 2026-06-11T18:01Z

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50Z (~23.2 days before window start). Dataset fully closed.

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 deduped (first-fire per `(asset, round(ts_open))`). Δ=0 vs prior.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | vs baseline |
|---|---|---|
| n | 885 | — |
| WR | 34.7% | well below backtest ~51.7% |
| PF | 1.061 | below target >1.30 |
| EV/trade | +$0.062 | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — |
| CI95 EV/trade (bootstrap n=5000) | [−$0.093, +$0.217] | straddles zero; entirely below baseline CI |

### Per-Asset (n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.343] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.299, +$0.236] | BELOW CI lower; PF<1.0; CI95 straddles zero | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.128, +$0.408] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |

### Per-Hour-UTC (no hour n≥100; watchlist entries n=40–71)

| hour | n | WR% | EV/trade | status |
|---|---|---|---|---|
| H00 | 39 | 35.9 | +$0.320 | n<40 — ignore |
| H01 | 66 | 48.5 | +$0.784 | WATCH (40≤n<100) |
| H02 | 64 | 40.6 | +$0.196 | WATCH |
| H03 | 36 | 44.4 | +$0.372 | n<40 — ignore |
| H04 | 37 | 32.4 | −$0.147 | n<40 — ignore |
| H05 | 35 | 14.3 | −$0.861 | n<40 — ignore |
| H06 | 35 | 31.4 | +$0.021 | n<40 — ignore |
| H07 | 31 | 19.4 | −$0.439 | n<40 — ignore |
| H08 | 35 | 28.6 | +$0.409 | n<40 — ignore |
| H09 | 28 | 14.3 | −$0.563 | n<40 — ignore |
| H10 | 38 | 34.2 | +$0.141 | n<40 — ignore |
| H11 | 71 | 35.2 | +$0.191 | WATCH |
| H12 | 36 | 36.1 | −$0.033 | n<40 — ignore |
| H13 | 36 | 33.3 | +$0.023 | n<40 — ignore |
| H14 | 47 | 29.8 | −$0.108 | WATCH (negative EV) |
| H15 | 36 | 30.6 | −$0.124 | n<40 — ignore |
| H16 | 30 | 16.7 | −$0.716 | n<40 — ignore |
| H17 | 21 | 38.1 | −$0.388 | n<40 — ignore |
| H18 | 25 | 60.0 | +$0.301 | n<40 — ignore |
| H21 | 39 | 51.3 | +$0.607 | n<40 — ignore |
| H22 | 40 | 32.5 | −$0.137 | WATCH (negative EV) |
| H23 | 57 | 33.3 | +$0.004 | WATCH |

*No hour reaches n≥100 → no lever activation possible from hour dimension.*

### Per-Ask-Band (vs baseline CI [+$0.244, +$0.352])

| band | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.305, +$0.645] | n<100 — BELOW baseline; COLLECTING | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.280, +$0.285] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| [0.30, 0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.110, +$0.356] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| [0.40, 0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.281, +$0.470] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| [0.50, 0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$2.004, +$1.697] | n<100 — ignore | IGNORE |

*Note: `term_remaining_s` was zero-filled for all VOLARB-era records — field was not logged at entry time. REM probes are N/A.*

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60)**: n=8, EV=−$0.157, CI95=[−$2.004, +$1.697] → **NOT LEVER CANDIDATE** (n=8 < 100 minimum)
- **REM_MAX_S probe [260, 280)**: `term_remaining_s` not populated in VOLARB era (all zeros). n=0 → **N/A**
- **REM_MIN_S probe [60, 80)**: same — `term_remaining_s` not populated. n=0 → **N/A**
- **ASK_DEPTH_MULT probe**: No adverse-selection slippage data at sufficient n. Not triggered.

---

## Proposed Patch (capped at 1)

**NO PATCH**

EDGE_FLOOR raise data criteria: ALL PASS (n=885≥200 ✓, EV=+$0.062<+$0.10 ✓, PF=1.061<1.10 ✓, CI95_lo=−$0.093<0 ✓).

Two hard blockers prevent patch:

1. **Strategy fully retired.** VOLARB was disabled 2026-05-17 19:56 UTC and `volarb_strategy=None` removed from `main.py` on 2026-05-19. Live bot does not import or instantiate `strategy/volarb.py`. Any edit to this file has zero operational effect.

2. **Code target mismatch.** Audit spec targets scalar `EDGE_FLOOR = 0.15 → 0.17`. Dev-branch code has `EDGE_FLOOR_BY_ASSET = {"BTC": 0.10, "ETH": 0.10, "SOL": 0.10}` (line 46) + `EDGE_FLOOR_DEFAULT = 0.10` (line 47). Scalar `EDGE_FLOOR` at 0.15 does not exist. Conforming edit would require modifying a dict at values that differ from the spec's stated starting point — outside the 1-scalar-edit cap by design.

→ NO_PATCH is the correct output. Generating a patch PR against a dead, mismatched file would be noise.

---

## Watchlist (40≤n<100; unchanged vs prior; dataset closed)

All watchlist items Δ=0 vs prior audit (30th consecutive no-change).

| dimension | cell | n | EV/trade | note | Δ vs prior |
|---|---|---|---|---|---|
| asset | BTC | 286 | +$0.083 | n≥100; CI95 upper >0; not negative | unchanged |
| asset | ETH | 305 | −$0.035 | n≥100; PF<1.0; worst asset | unchanged |
| asset | SOL | 294 | +$0.142 | n≥100; best asset | unchanged |
| ask_band | [0.10,0.20) | 91 | +$0.149 | n<100; monitor | unchanged |
| ask_band | [0.20,0.30) | 227 | −$0.003 | n≥100; near-zero EV | unchanged |
| ask_band | [0.30,0.40) | 390 | +$0.121 | n≥100; EV below baseline CI | unchanged |
| ask_band | [0.40,0.50) | 157 | +$0.085 | n≥100; EV below baseline CI | unchanged |
| hour | H01 | 66 | +$0.784 | 40≤n<100; positive EV; monitor | unchanged |
| hour | H02 | 64 | +$0.196 | 40≤n<100; below baseline | unchanged |
| hour | H11 | 71 | +$0.191 | 40≤n<100; below baseline | unchanged |
| hour | H14 | 47 | −$0.108 | 40≤n<100; negative EV | unchanged |
| hour | H22 | 40 | −$0.137 | 40≤n<100; negative EV | unchanged |
| hour | H23 | 57 | +$0.004 | 40≤n<100; near-zero EV | unchanged |

**Watchlist count: 5 per-hour + 3 per-asset + 4 per-band = 12 cells (same as prior audit).**

---

## Skipped — User Override (state_log)

No active VOLARB parameter overrides in `state_log.md`. All VOLARB-era entries are historical operational records (2026-05-16 to 2026-05-19). Strategy is retired; override tracking not applicable.

---

## Audit Conclusion

**30th consecutive NO_PATCH on a closed dataset.** VOLARB retired 23.2 days ago. EDGE_FLOOR data trigger fires correctly but is blocked by two structural conditions (retired strategy, code mismatch). Recommend scheduling this audit routine to pause until VOLARB is reactivated or the routine is explicitly decommissioned.
