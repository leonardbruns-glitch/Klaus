# VOLARB Quantitative Audit — 2026-06-10 18:20 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-10T18:03:09Z (12 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $91.26 (prior audit 2026-06-10T06:13Z: $69.16; Δ=+$22.10 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 26th consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~688h retired) |
| drift_status | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition not met |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **26th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched (state_log).
- 2026-05-19: `volarb_strategy=None`, import removed (state_log).
- 2026-05-29: CLAUDE.md fully reoriented to STWA; no crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) permanently blocked for this dataset.
- `EDGE_FLOOR` on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}`; the audit prompt's scalar `0.15→0.17` raise is structurally inapplicable as written.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (12 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($91.26) |
| Code drift guard | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition false; dev branch levers intact at lines 46–65 |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-10T12:20Z .. 2026-06-10T18:20Z
**VOLARB trades in window: 0** (strategy retired ~688h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`). Δ vs prior audit = 0.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | vs baseline |
|---|---|---|
| n | 885 | — |
| WR | 34.7% | below backtest ~51.7% |
| PF | 1.061 | below target >1.30 |
| EV/trade | +$0.062 | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — |
| CI95 EV/trade | [−$0.084, +$0.221] | entirely below baseline CI; straddles zero |

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.164, +$0.367] | BELOW CI lower | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.282, +$0.216] | BELOW CI lower; PF<1.0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.131, +$0.446] | BELOW CI lower | WATCHLIST |

### Per-Hour-UTC (n≥10 shown; none reach n≥100)

| dimension | cell | n | WR% | EV/trade | status |
|---|---|---|---|---|---|
| hour | H00 | 42 | 47.6 | +$0.794 | n<100, trend-only |
| hour | H01 | 52 | 42.3 | +$0.497 | n<100, trend-only |
| hour | H02 | 66 | 40.9 | +$0.375 | n<100, trend-only |
| hour | H03 | 51 | 41.2 | +$0.210 | n<100, trend-only |
| hour | H05 | 36 | 19.4 | −$0.754 | n<40, collect |
| hour | H06 | 35 | 20.0 | −$0.492 | n<40, collect |
| hour | H07 | 35 | 22.9 | −$0.423 | n<40, collect |
| hour | H08 | 33 | 21.2 | −$0.050 | n<40, collect |
| hour | H11 | 59 | 35.6 | +$0.116 | n<100, trend-only |
| hour | H12 | 51 | 31.4 | −$0.014 | n<100, trend-only |
| hour | H15 | 47 | 36.2 | +$0.229 | n<100, trend-only |
| hour | H16 | 36 | 16.7 | −$0.814 | n<40, collect; worst hour |
| hour | H17 | 29 | 27.6 | −$0.680 | n<40, collect |
| hour | H18 | 23 | 69.6 | +$0.654 | n<40, collect |
| hour | H21 | 24 | 58.3 | +$0.759 | n<40, collect |
| hour | H22 | 36 | 38.9 | +$0.243 | n<40, collect |
| hour | H23 | 55 | 29.1 | −$0.270 | n<100, trend-only |

No hour reaches n≥100 → no per-hour lever action eligible.

### Per-Ask-Band

| dimension | cell | n | WR% | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | +$13.60 | +$0.149 | [−$0.314, +$0.644] | n<100 | COLLECT |
| ask_band | [0.20,0.30) | 227 | 26.4 | −$0.73 | −$0.003 | [−$0.266, +$0.274] | **BELOW CI lower** | WATCHLIST |
| ask_band | [0.30,0.40) | 390 | 38.7 | +$47.01 | +$0.121 | [−$0.111, +$0.351] | **BELOW CI lower** | WATCHLIST |
| ask_band | [0.40,0.50) | 157 | 47.1 | +$13.38 | +$0.085 | [−$0.254, +$0.498] | **BELOW CI lower** | WATCHLIST |
| ask_band | [0.50,0.60) | 8 | 50.0 | −$1.25 | −$0.157 | [−$2.004, +$1.690] | n<100 | COLLECT |

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60)**: n=8, EV=−$0.157, CI95=[−$2.004, +$1.690]. Gate: n≥100 **NOT MET**. No action.
- **REM_MAX_S probe [260,280)**: n=0 (`term_remaining_s=0.0` uniformly — field not populated at trade-time). Gate: n≥100 **NOT MET**. No action.
- **REM_MIN_S probe [60,80)**: n=0 (same reason). Gate: n≥100 **NOT MET**. No action.
- **ASK_DEPTH_MULT probe**: No adverse-selection slippage data in VOLARB records. No action.

---

## Proposed Patch

**no patch**

### Decision rationale

**EDGE_FLOOR raise (0.15 → 0.17)** — numeric conditions:
- n≥200: ✓ (885)
- EV/trade < +$0.10: ✓ (+$0.062)
- PF<1.10: ✓ (1.061)
- CI95 lower < 0: ✓ (−$0.084)

**BLOCKED — structural mismatch.** Dev branch `strategy/volarb.py:46` defines `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}`, not a scalar 0.15. The prompt's `0.15→0.17` edit is inapplicable; rewriting the dict would be a redesign, not a lever tweak. State_log confirms floor was set to 0.10 per-asset by user instruction 2026-05-17 10:20 UTC — overrides any scalar raise.

**Additionally**: VOLARB fully retired (entries disabled 2026-05-17 19:56 UTC; import removed 2026-05-19); `strategy/volarb.py` not loaded at runtime. Any edit has zero operational effect.

**All other levers**: ASK_CEIL n=8 (<100); REM_MAX_S n=0; REM_MIN_S n=0; ASK_DEPTH_MULT no slippage data. None eligible.

→ **NO PATCH — 26th consecutive NO_PATCH. Dataset closed (Δ=0). Strategy retired.**

---

## Watchlist (Δ vs prior audit 2026-06-10T06:13Z = 0)

| type | cell | n | EV/trade | CI95 | note |
|---|---|---|---|---|---|
| asset | BTC | 286 | +$0.083 | [−$0.164, +$0.367] | n≥100; EV below +$0.244 baseline CI lower |
| asset | ETH | 305 | −$0.035 | [−$0.282, +$0.216] | n≥100; EV below +$0.244; PF<1.0 |
| asset | SOL | 294 | +$0.142 | [−$0.131, +$0.446] | n≥100; EV below +$0.244 |
| ask_band | [0.20,0.30) | 227 | −$0.003 | [−$0.266, +$0.274] | n≥100; EV below +$0.244 |
| ask_band | [0.30,0.40) | 390 | +$0.121 | [−$0.111, +$0.351] | n≥100; EV below +$0.244 |
| ask_band | [0.40,0.50) | 157 | +$0.085 | [−$0.254, +$0.498] | n≥100; EV below +$0.244 |
| hour | H05 | 36 | −$0.754 | n/a | n<40 collect; worst-cluster (H05–H07 WR 19–23%) |
| hour | H06 | 35 | −$0.492 | n/a | n<40 collect; worst-cluster |
| hour | H16 | 36 | −$0.814 | n/a | n<40 collect; single worst hour |

Watchlist count: **9** (Δ=0 — frozen dataset, same 9 items as prior audit).

---

## Skipped — User Override (state_log)

- **EDGE_FLOOR=0.10/asset**: user-set 2026-05-17 10:20 UTC (volarb.py:46); overrides any scalar raise framing.
- **ASK_FLOOR=0.00**: user instruction 2026-05-17 UTC (longshot bucket activated); per audit mandate, never touch ASK_FLOOR.
- **term_remaining_s field**: not populated in VOLARB trades (logged as 0.0 at trade-time); user did not backfill; REM_MIN_S / REM_MAX_S probes permanently blocked for this dataset.
