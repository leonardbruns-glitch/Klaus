# VOLARB Quantitative Audit — 2026-06-12T06:11:51Z

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-12T06:08:52Z (3 min old — FRESH) |
| Klaus state | active (systemd: active; 0 open positions; STWA/weather bot running) |
| Capital | $202.46 (prior audit 2026-06-12T00:14Z: $190.66; Δ=+$11.80 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 32nd consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~24.2 days retired) |
| drift_status | N/A — data-mirror does not contain `strategy/volarb.py`; mirror-file-present condition FALSE → DEPLOY_LAG not triggered. Dev-branch code has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}`; spec's scalar `EDGE_FLOOR=0.15` does not match current code. |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — **CLOSED DATASET**) |
| Open `audit/volarb-*` PRs | NONE (GitHub confirmed) |
| Run | **32nd consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: PERMANENTLY RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19 UTC: `volarb_strategy=None`, import removed from `main.py`. Residual exit-path checks kept for wallet recovery only.
- 2026-05-29 UTC: CLAUDE.md reoriented to STWA; all crypto/VOLARB sections removed.
- `strategy/volarb.py` not loaded on the live VPS. **Any patch to this file has ZERO operational effect.**

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (3 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($202.46) |
| Code-drift guard | mirror-file-present condition FALSE (data-mirror is data-only; no `strategy/volarb.py`) → DEPLOY_LAG not triggered |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-11T20:09Z .. 2026-06-12T06:09Z

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50Z (~24.2 days before window start). Dataset fully closed.

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 deduped (first-fire per `(asset, round(ts_open))`). Δ=0 vs prior 31 audits.
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
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower | WATCHLIST (strategy retired) |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.223] | BELOW CI lower; PF<1.0 | WATCHLIST (strategy retired) |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower | WATCHLIST (strategy retired) |

### Per-Hour-UTC (n≥40 cells only; none reach n≥100)

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| hour_utc | H01 | 66 | 48.5 | +$0.784 | [+$0.174, +$1.415] | CI lower > baseline lower | WATCHLIST (positive outlier) |
| hour_utc | H02 | 64 | 40.6 | +$0.196 | [−$0.360, +$0.796] | BELOW CI lower | WATCHLIST |
| hour_utc | H11 | 71 | 35.2 | +$0.191 | [−$0.356, +$0.743] | BELOW CI lower | WATCHLIST |
| hour_utc | H14 | 47 | 29.8 | −$0.107 | [−$0.694, +$0.492] | BELOW CI lower | WATCHLIST |
| hour_utc | H21 | 39 | 51.3 | +$0.607 | [−$0.052, +$1.261] | BELOW CI lower (n<40 borderline) | WATCHLIST |
| hour_utc | H22 | 40 | 32.5 | −$0.137 | [−$0.768, +$0.540] | BELOW CI lower | WATCHLIST |
| hour_utc | H23 | 57 | 33.3 | +$0.004 | [−$0.553, +$0.597] | BELOW CI lower | WATCHLIST |

### Per-Ask-Band (entry_price; n≥40 cells shown)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | n/a | +$13.55 | +$0.149 | [−$0.308, +$0.661] | BELOW CI lower | WATCHLIST |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.984 | −$0.63 | −$0.003 | [−$0.276, +$0.274] | BELOW CI lower; PF<1.0 | ACTION-CANDIDATE (strategy retired) |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.111 | +$46.72 | +$0.120 | [−$0.108, +$0.355] | BELOW CI lower | ACTION-CANDIDATE (strategy retired) |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.091 | +$13.36 | +$0.085 | [−$0.281, +$0.474] | BELOW CI lower | ACTION-CANDIDATE (strategy retired) |
| ask_band | [0.50,0.60) | 8 | 50.0 | — | −$1.26 | −$0.157 | [−$1.991, +$1.684] | n<40 → IGNORE | IGNORE |

---

## Lever Probes

**Note:** `term_remaining_s` field in trades.jsonl is logged at resolution (all values = 0.0). REM-based probes cannot be executed on this dataset. ASK_DEPTH_MULT slippage proxy: `slippage_entry` all 0.0 — no adverse-selection signal measurable.

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI95=[−$1.991, +$1.684] → n<100 → **NO lever candidate**
- **REM_MAX_S probe [260,280):** n=0 (`term_remaining_s` = 0 at resolution for all trades) → **NO lever candidate**
- **REM_MIN_S probe [60,80):** n=0 (same reason) → **NO lever candidate**
- **ASK_DEPTH_MULT probe:** slippage_entry all 0.0; no adverse-selection evidence → **NO lever candidate**

---

## Proposed Patch (capped at 1)

**NO PATCH**

Numerical EDGE_FLOOR raise conditions are met (n=885≥200, EV=+$0.062<+$0.10, PF=1.061<1.10, CI lower=−$0.093<0). However:

1. **Strategy is permanently retired.** `volarb_strategy=None` since 2026-05-19. `strategy/volarb.py` is not imported or instantiated on the live VPS. A scalar edit to this file has **zero operational effect**.
2. **Spec's EDGE_FLOOR=0.15 reference is stale.** Current dev-branch code has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` — not the scalar 0.15 the patch spec targets. The edit as specified cannot be applied cleanly.
3. **Anti-sycophancy rule applied:** "No patch is the correct output when data is clean. Don't generate noise PRs." A patch to a non-running file with no path to deployment is a noise PR.

---

## Watchlist (Δ vs prior audit 2026-06-12T00:14Z)

All watchlist cells are **unchanged** (Δ=0 new trades). No new entrants. No exits.

| cell | n | EV/trade | trend | delta vs prior |
|---|---|---|---|---|
| BTC (asset) | 286 | +$0.083 | flat | 0 |
| ETH (asset) | 305 | −$0.035 | flat | 0 |
| SOL (asset) | 294 | +$0.142 | flat | 0 |
| H01 (positive outlier) | 66 | +$0.784 | flat | 0 |
| H11 | 71 | +$0.191 | flat | 0 |
| [0.10,0.20) ask-band | 91 | +$0.149 | flat | 0 |

---

## Skipped — User Override (state_log)

No active user overrides found in state_log relevant to VOLARB lever decisions. VOLARB was retired by user instruction (2026-05-17 19:56 UTC → 2026-05-19 UTC). All state_log VOLARB entries post-date the dataset.

---

*32nd consecutive NO_PATCH audit. Dataset closed. Strategy retired. This audit series terminates unless VOLARB is reactivated.*
