# VOLARB Quantitative Audit — 2026-06-12T00:14:24Z

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-12T00:05:32Z (8.9 min old — FRESH) |
| Klaus state | active (systemd: active; 0 open positions; STWA/weather bot running) |
| Capital | $190.66 (prior audit 2026-06-11T18:19Z: $196.78; Δ=−$6.12 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 31st consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~23.9 days retired) |
| drift_status | N/A — data-mirror does not contain `strategy/volarb.py`; mirror-file-present condition FALSE → no DEPLOY_LAG. Dev-branch code has restructured `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_CEIL=0.20` + `SPREAD_MIN_BPS=200`/`SPREAD_MAX_BPS=300` — spec's scalar `EDGE_FLOOR=0.15` does not exist in current code. |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — **CLOSED DATASET**) |
| Open `audit/volarb-*` PRs | NONE (GitHub confirmed) |
| Run | **31st consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: PERMANENTLY RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19 UTC: `volarb_strategy=None`, import removed from `main.py`. Residual exit-path checks kept for wallet recovery only.
- 2026-05-29 UTC: CLAUDE.md reoriented to STWA; all crypto/VOLARB sections removed.
- `strategy/volarb.py` not loaded on the live VPS. **Any patch to this file has ZERO operational effect.**

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (8.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($190.66) |
| Code-drift guard | mirror-file-present condition FALSE (data-mirror is data-only; no `strategy/volarb.py`) → DEPLOY_LAG not triggered |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-11T18:05Z .. 2026-06-12T00:05Z

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50Z (~23.9 days before window start). Dataset fully closed.

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 deduped (first-fire per `(asset, round(ts_open))`). Δ=0 vs prior 30 audits.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | vs baseline |
|---|---|---|
| n | 885 | — |
| WR | 34.7% | well below backtest ~51.7% |
| PF | 1.061 | below target >1.30 |
| EV/trade | +$0.062 | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — |
| CI95 EV/trade (bootstrap n=5000) | [−$0.097, +$0.219] | straddles zero; entirely below baseline CI |

### Per-Asset (n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower; CI upper > 0 | WATCHLIST (strategy retired) |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.232] | BELOW CI lower; PF<1.0; CI straddles zero | WATCHLIST (strategy retired) |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.413] | BELOW CI lower; CI upper > 0 | WATCHLIST (strategy retired) |

### Per-Hour-UTC (n≥40 only; no hour reaches n≥100)

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| hour_utc | H01 | 66 | 48.5 | +$0.784 | [+$0.174, +$1.413] | CI lower > baseline lower | WATCHLIST (positive outlier) |
| hour_utc | H02 | 64 | 40.6 | +$0.196 | [−$0.384, +$0.807] | BELOW CI lower | WATCHLIST |
| hour_utc | H11 | 71 | 35.2 | +$0.191 | [−$0.352, +$0.754] | BELOW CI lower | WATCHLIST |
| hour_utc | H14 | 47 | 29.8 | −$0.107 | [−$0.683, +$0.508] | BELOW CI lower | WATCHLIST (negative) |
| hour_utc | H22 | 40 | 32.5 | −$0.137 | [−$0.779, +$0.545] | BELOW CI lower | WATCHLIST (negative) |
| hour_utc | H23 | 57 | 33.3 | +$0.004 | [−$0.576, +$0.586] | BELOW CI lower | WATCHLIST |

### Per-Ask-Band (vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | 0.784 | +$13.55 | +$0.149 | [−$0.307, +$0.641] | BELOW CI lower; n=40–99 | WATCHLIST |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.944 | −$0.63 | −$0.003 | [−$0.281, +$0.276] | BELOW CI lower; CI straddles zero | WATCHLIST (n≥100) |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.107 | +$46.82 | +$0.120 | [−$0.120, +$0.351] | BELOW CI lower | WATCHLIST (n≥100) |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.163 | +$13.40 | +$0.085 | [−$0.284, +$0.475] | BELOW CI lower | WATCHLIST (n≥100) |
| ask_band | [0.50,0.60) | 8 | 50.0 | 1.164 | −$1.26 | −$0.157 | [−$1.991, +$1.684] | n<40 | COLLECT |

---

## Lever Probes

**ASK_CEIL probe** [0.50, 0.60): n=**8** — lever condition FAILS (requires n≥100). Not actionable.

**REM_MAX_S probe** [260, 280)s: `sec_to_res` at entry is not stored in trades.jsonl. `term_remaining_s` records 0.0 at resolution (not at entry). Probe uncomputable from available data.

**REM_MIN_S probe** [60, 80)s: same — no `sec_to_res` at entry field present. Uncomputable.

**ASK_DEPTH_MULT probe**: no adverse-selection slippage signal isolatable; overall EV degradation is diagnosed but strategy retired — zero operational effect even if conditions were met. No trigger.

---

## Proposed Patch

**no patch**

All lever conditions fail:

| lever | condition | result |
|---|---|---|
| EDGE_FLOOR raise (0.15→0.17) | n≥200 AND EV<+$0.10 AND PF<1.10 AND CI95 lower<0 | Data conditions MET (n=885, EV=+$0.062, PF=1.061, CI lower=−$0.097) — but scalar `EDGE_FLOOR` does not exist; replaced by per-asset dict + ceiling. Architectural change required (Tier 2), not a 1-scalar edit. And strategy is retired: zero operational effect. |
| ASK_CEIL lower (0.60→0.55) | n≥100 in [0.50,0.60) | n=8 — **FAILS n≥100** |
| REM_MAX_S lower (280→260) | n≥100 in [260,280)s | sec_to_res at entry not stored — **uncomputable** |
| REM_MIN_S raise (60→80) | n≥100 in [60,80)s | sec_to_res at entry not stored — **uncomputable** |
| ASK_DEPTH_MULT raise | n≥200 AND EV degrading AND adverse-selection evidence | strategy retired; operationally inert regardless |

Primary reason: **VOLARB strategy is retired and not running. Any patch to `strategy/volarb.py` is operationally inert.**

---

## Watchlist (40≤n<100 AND per-asset/per-hour findings without block lever)

Δ vs prior audit (2026-06-11T18:19Z, watch=12): dataset unchanged (Δ=0 new trades) — all positions identical to prior run. No promotions, no new entries, no exits possible (dataset closed).

| cell | n | EV/trade | CI95 | delta vs prior | note |
|---|---|---|---|---|---|
| asset: BTC | 286 | +$0.083 | [−$0.175, +$0.348] | unchanged | n≥100, below baseline; strategy retired |
| asset: ETH | 305 | −$0.035 | [−$0.294, +$0.232] | unchanged | n≥100, PF<1.0; strategy retired |
| asset: SOL | 294 | +$0.142 | [−$0.125, +$0.413] | unchanged | n≥100, below baseline; strategy retired |
| hour: H01 | 66 | +$0.784 | [+$0.174, +$1.413] | unchanged | positive outlier; n<100 |
| hour: H02 | 64 | +$0.196 | [−$0.384, +$0.807] | unchanged | below baseline; n<100 |
| hour: H11 | 71 | +$0.191 | [−$0.352, +$0.754] | unchanged | below baseline; n<100 |
| hour: H14 | 47 | −$0.107 | [−$0.683, +$0.508] | unchanged | negative EV; n<100 |
| hour: H22 | 40 | −$0.137 | [−$0.779, +$0.545] | unchanged | negative EV; n<100 |
| hour: H23 | 57 | +$0.004 | [−$0.576, +$0.586] | unchanged | flat; n<100 |
| ask_band: [0.10,0.20) | 91 | +$0.149 | [−$0.307, +$0.641] | unchanged | below baseline; n=40–99 |
| ask_band: [0.20,0.30) | 227 | −$0.003 | [−$0.281, +$0.276] | unchanged | n≥100 below baseline; retired |
| ask_band: [0.30,0.40) | 390 | +$0.120 | [−$0.120, +$0.351] | unchanged | n≥100 below baseline; retired |

Watchlist promotion threshold (n≥100) will never be crossed — dataset is closed.

---

## Skipped — User Override (state_log)

No state_log entries override Auditor action on any VOLARB lever for this audit. The strategy retirement itself is a user instruction (2026-05-17 19:56 UTC). All prior gate decisions (EDGE_FLOOR progression, ASK_FLOOR, hour blocks) are superseded by retirement.

---

## Code Structure Note (non-actionable)

Audit spec assumes scalar `EDGE_FLOOR = 0.15`. Current `strategy/volarb.py` at HEAD has:
- `EDGE_FLOOR_BY_ASSET = {"BTC": 0.10, "ETH": 0.10, "SOL": 0.10}` + `EDGE_FLOOR_DEFAULT = 0.10`
- `EDGE_CEIL = 0.20` (upper cap on model edge — new)
- `SPREAD_MIN_BPS = 200.0` / `SPREAD_MAX_BPS = 300.0` (new spread gate)

This evolution is fully documented in state_log (2026-05-17 07:26, 07:44, 12:30 UTC entries). Should VOLARB be revived, the Auditor spec's EDGE_FLOOR lever must be updated to reflect per-asset dict granularity.

---

*Audit produced by Klaus Auditor agent — report only, no patch applied.*
