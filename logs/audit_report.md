# VOLARB Quantitative Audit — 2026-06-12T12:20:39Z

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-12T11:57:16Z (17.9 min old — FRESH) |
| Klaus state | active (systemd: active; 0 open positions; STWA/weather bot running) |
| Capital | $225.67 (prior audit 2026-06-12T06:11Z: $202.46; Δ=+$23.21 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 33rd consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~24.4 days retired) |
| drift_status | N/A — data-mirror does not contain `strategy/volarb.py`; mirror-file-present condition FALSE → DEPLOY_LAG not triggered. Dev-branch code has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10`; spec's scalar `EDGE_FLOOR=0.15` does not match current code. |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — **CLOSED DATASET**) |
| Open `audit/volarb-*` PRs | NONE (GitHub confirmed) |
| Run | **33rd consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: PERMANENTLY RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19 UTC: `volarb_strategy=None`, import removed from `main.py`. Residual exit-path checks kept for wallet recovery only.
- 2026-05-29 UTC: CLAUDE.md reoriented to STWA; all crypto/VOLARB sections removed.
- `strategy/volarb.py` not loaded on the live VPS. **Any patch to this file has zero operational effect.**

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (17.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($225.67) |
| Code-drift guard | mirror-file-present condition FALSE → DEPLOY_LAG not triggered |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-12T06:20Z .. 2026-06-12T12:20Z

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50Z (~24.4 days before window start). Dataset fully closed.

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 deduped (first-fire per `(asset, round(ts_open))`). Δ=0 vs prior 32 audits.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | vs baseline |
|---|---|---|
| n | 885 | — |
| WR | 34.7% | well below backtest ~51.7% |
| PF | 1.061 | below target >1.30 |
| EV/trade | +$0.062 | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — |
| CI95 EV/trade (bootstrap n=5000) | [−$0.085, +$0.214] | straddles zero; entirely below baseline CI |

### Per-Asset (all n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.174, +$0.357] | BELOW CI lower | WATCHLIST (strategy retired) |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.304, +$0.235] | BELOW CI lower; PF<1.0 | WATCHLIST (strategy retired) |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower | WATCHLIST (strategy retired) |

### Per-Hour-UTC (n≥40 cells shown; none reach n≥100)

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| hour_utc | H01 | 66 | 48.5 | +$0.784 | [+$0.162, +$1.409] | CI lower > baseline lower | WATCHLIST (positive outlier) |
| hour_utc | H02 | 64 | 40.6 | +$0.196 | [−$0.398, +$0.788] | BELOW CI lower | WATCHLIST |
| hour_utc | H11 | 71 | 35.2 | +$0.191 | [−$0.346, +$0.761] | BELOW CI lower | WATCHLIST |
| hour_utc | H14 | 47 | 29.8 | −$0.107 | [−$0.671, +$0.519] | BELOW CI lower | WATCHLIST |
| hour_utc | H21 | 39 | 51.3 | +$0.607 | [−$0.061, +$1.290] | BELOW CI lower (borderline) | WATCHLIST |
| hour_utc | H22 | 40 | 32.5 | −$0.137 | [−$0.788, +$0.548] | BELOW CI lower | WATCHLIST |
| hour_utc | H23 | 57 | 33.3 | +$0.004 | [−$0.550, +$0.622] | BELOW CI lower | WATCHLIST |

### Per-Ask-Band (entry_price; n≥40 cells shown)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 101 | 16.8 | 1.057 | +$4.49 | +$0.044 | [−$0.375, +$0.505] | BELOW CI lower | WATCHLIST |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.271] | BELOW CI lower; PF<1.0 | WATCHLIST (strategy retired) |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.120 | [−$0.118, +$0.349] | BELOW CI lower | WATCHLIST (strategy retired) |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.280, +$0.462] | BELOW CI lower | WATCHLIST (strategy retired) |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.997, +$1.684] | n<40 → IGNORE | IGNORE |

---

## Lever Probes

**Methodology note (correction vs prior reports):** `term_remaining_s` is logged at resolution (all values 0.0). Remaining seconds at entry recomputed as `window_start + 300 − ts_open` where `window_start = floor(ts_open / 300) × 300`. Validated: for BOND_RESOLVED_NO exits (n=573), `|hold_seconds − rem_computed|` median = 60.9s (resolution delay), confirming correctness.

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI95=[−$1.997, +$1.684] → **n<100 → NO lever candidate**
- **REM_MAX_S probe [260,280):** n=221, WR=39.8%, PF=0.996, EV=−$0.004, CI95=[−$0.319, +$0.318] → CI95 upper > 0; EV not < −$0.10 → **NOT a lever candidate**
- **REM_MIN_S probe [60,80):** n=8, WR=0.0%, EV=−$1.076, CI95=[−$1.338, −$0.836] → **n<100 → NO lever candidate** (alarming WR/EV; COLLECTING)
- **ASK_DEPTH_MULT probe:** `slippage_entry` all 0.0 across 885 trades → no adverse-selection evidence → **NO lever candidate**

---

## Proposed Patch (capped at 1)

**NO PATCH**

EDGE_FLOOR raise conditions are numerically triggered (n=885≥200 ✓, EV=+$0.062<+$0.10 ✓, PF=1.061<1.10 ✓, CI lower=−$0.085<0 ✓). Patch withheld for three independent reasons:

1. **Strategy permanently retired.** `volarb_strategy=None` since 2026-05-19. `strategy/volarb.py` is not imported or instantiated on the live VPS. A scalar edit to this file has **zero operational effect**.
2. **Spec EDGE_FLOOR=0.15 reference is stale.** Dev-branch code has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10`. The named patch target (scalar 0.15) does not exist in current code.
3. **Anti-sycophancy rule:** Patching a non-running file with no deployment path is a noise PR regardless of numerical trigger status. "No patch is the correct output when data is clean. Don't generate noise PRs."

Other levers: ASK_CEIL n=8 (COLLECTING), REM_MAX_S EV=−$0.004 CI straddles zero (NOT triggered), REM_MIN_S n=8 (COLLECTING), ASK_DEPTH_MULT no slippage signal (NOT triggered).

---

## Watchlist (Δ=0 vs prior audit; frozen dataset)

12 cells carried forward unchanged. No promotion possible on frozen data.

| cell | n | EV/trade | CI95 | delta_vs_prior | notes |
|---|---|---|---|---|---|
| asset: ETH | 305 | −$0.035 | [−$0.304, +$0.235] | unchanged | only asset with negative sum; PF<1.0 |
| asset: BTC | 286 | +$0.083 | [−$0.174, +$0.357] | unchanged | positive sum; below baseline CI lower |
| asset: SOL | 294 | +$0.142 | [−$0.125, +$0.410] | unchanged | best asset EV; below baseline CI lower |
| ask_band [0.20,0.30) | 227 | −$0.003 | [−$0.276, +$0.271] | unchanged | PF<1.0; flat EV |
| ask_band [0.30,0.40) | 390 | +$0.120 | [−$0.118, +$0.349] | unchanged | largest cell; below baseline CI |
| ask_band [0.40,0.50) | 157 | +$0.085 | [−$0.280, +$0.462] | unchanged | high WR 47.1%; wide CI |
| ask_band [0.10,0.20) | 101 | +$0.044 | [−$0.375, +$0.505] | unchanged | low WR 16.8%; positive only via large win size |
| hour H01 | 66 | +$0.784 | [+$0.162, +$1.409] | unchanged | **positive outlier; CI lower > baseline lower** |
| hour H11 | 71 | +$0.191 | [−$0.346, +$0.761] | unchanged | CI straddles zero |
| hour H02 | 64 | +$0.196 | [−$0.398, +$0.788] | unchanged | CI straddles zero |
| hour H22 | 40 | −$0.137 | [−$0.788, +$0.548] | unchanged | negative EV; wide CI |
| hour H23 | 57 | +$0.004 | [−$0.550, +$0.622] | unchanged | flat EV; CI straddles zero |

---

## Skipped — User Override (state_log)

None. No state_log entries override cell-level analysis.

---

## Notes

- **REM_MIN_S [60,80) alarm:** n=8, WR=0%, EV=−$1.076, CI95=[−$1.338, −$0.836]. Insufficient sample to act (n<100). If VOLARB were reactivated, this cell would be a priority probe target.
- **Dataset frozen since 2026-05-19T02:50Z.** n will not increase. Scheduled VOLARB audits produce no actionable output. Consider suspending this audit schedule.
