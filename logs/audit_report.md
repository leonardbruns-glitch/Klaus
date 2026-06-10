# VOLARB Quantitative Audit — 2026-06-10 06:13 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-10T06:09:46Z (4 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $69.16 (prior audit 2026-06-10T00:07Z: $93.96; Δ=−$24.80 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 25th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~676h retired) |
| drift_status | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition not met |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **25th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched (state_log).
- 2026-05-19: `volarb_strategy=None`, import removed (state_log).
- 2026-05-29: CLAUDE.md fully reoriented to STWA. No crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed.
- `EDGE_FLOOR` on dev branch is a per-asset dict (`EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}`); the audit prompt's scalar `0.15→0.17` raise is structurally inapplicable as written.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (4 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($69.16) |
| Code drift guard | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition false; dev branch levers at lines 46–65 intact |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-10T00:09Z .. 2026-06-10T06:09Z
**VOLARB trades in window: 0** (strategy retired ~676h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.087, +$0.220] | straddles zero; entirely below baseline CI |

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.183, +$0.358] | BELOW CI lower; straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.293, +$0.238] | BELOW CI lower; PF<1.0; straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower; straddles 0 | WATCHLIST |

### Per-Hour-UTC (hours with n≥40 shown)

| dimension | cell | n | WR% | PF | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | 1.953 | +$0.784 | [+$0.191, +$1.406] | CI lo above baseline lo | WATCHLIST (n<100) |
| hour | H02 | 64 | 40.6 | 1.185 | +$0.196 | [−$0.360, +$0.820] | straddles 0 | WATCHLIST (n<100) |
| hour | H11 | 71 | 35.2 | 1.196 | +$0.191 | [−$0.340, +$0.741] | straddles 0 | WATCHLIST (n<100) |
| hour | H14 | 47 | 29.8 | 0.894 | −$0.107 | [−$0.708, +$0.491] | straddles 0 | WATCHLIST (n<100) |
| hour | H22 | 40 | 32.5 | 0.872 | −$0.137 | [−$0.727, +$0.553] | straddles 0 | WATCHLIST (n<100) |
| hour | H23 | 57 | 33.3 | 1.004 | +$0.004 | [−$0.540, +$0.582] | straddles 0 | WATCHLIST (n<100) |

No per-hour cell reaches n≥100. No lever decisions possible.

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.302, +$0.661] | BELOW CI lower; straddles 0 | WATCHLIST (n<100) |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.265] | BELOW CI lower; PF<1.0 | WATCHLIST |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.120 | [−$0.108, +$0.357] | BELOW CI lower; straddles 0 | WATCHLIST |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.280, +$0.472] | BELOW CI lower; straddles 0 | WATCHLIST |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.997, +$1.697] | n<100 — collect | n<40 — collect |

No ask-band cell reaches n≥100 AND CI95 upper < 0. No lever candidates.

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60):** n=8. Threshold for action: n≥100 AND EV<−$0.10 AND CI95 upper<0. **NOT MET** (n<<100; CI upper = +$1.697). No lever candidate.
- **REM_MAX_S probe [260,280):** `term_remaining_s = 0.0` for all 885 trades — field not populated during VOLARB live era. **INOPERABLE.** Cannot evaluate. (Proxy via hold_seconds [260,280) gives n=100 but hold_seconds ≠ remaining time at entry; invalid substitute.)
- **REM_MIN_S probe [60,80):** Same — `term_remaining_s` unpopulated. hold_seconds proxy [60,80): n=2. **INOPERABLE.**
- **ASK_DEPTH_MULT probe:** `slippage_entry = 0.0` for all trades — adverse-selection slippage not measured. Cannot evaluate.

---

## Proposed Patch (capped at 1)

**NO PATCH.**

Patch-decision evaluation:

| lever | data criteria met? | suppression reason |
|---|---|---|
| EDGE_FLOOR raise (0.15→0.17) | YES (n=885≥200; EV=+$0.062<+$0.10; PF=1.061<1.10; CI_lo=−$0.087<0) | (1) `strategy/volarb.py` is dead code on VPS since 2026-05-19 — edit has zero operational effect. (2) `EDGE_FLOOR` is a per-asset dict on dev branch; scalar edit inapplicable. |
| ASK_CEIL lower (0.60→0.55) | NO | n=8 in [0.50,0.60) — n<100 threshold not met. |
| REM_MAX_S lower (280→260) | NO | `term_remaining_s` unpopulated — probe inoperable. |
| REM_MIN_S raise (60→80) | NO | Same — inoperable. |
| ASK_DEPTH_MULT raise | NO | Slippage field unavailable; adverse-selection evidence condition not met. |

---

## Watchlist (40≤n<100 and per-asset/per-hour findings)

All per-asset cells suppressed — strategy RETIRED, no operational lever exists.

| cell | n | EV/trade | CI95 | delta vs prior audit | note |
|---|---|---|---|---|---|
| BTC (asset) | 286 | +$0.083 | [−$0.183, +$0.358] | Δ=0 | Unchanged; strategy retired |
| ETH (asset) | 305 | −$0.035 | [−$0.293, +$0.238] | Δ=0 | PF<1.0; strategy retired |
| SOL (asset) | 294 | +$0.142 | [−$0.125, +$0.410] | Δ=0 | Strategy retired |
| ask [0.20,0.30) | 227 | −$0.003 | [−$0.276, +$0.265] | Δ=0 | PF<1.0 — negative EV band |
| ask [0.30,0.40) | 390 | +$0.120 | [−$0.108, +$0.357] | Δ=0 | Largest band; anchors overall EV |
| H01 | 66 | +$0.784 | [+$0.191, +$1.406] | Δ=0 | Only cell with both CI bounds >0; retired before reaching n≥100 |

---

## Skipped — User Override (state_log)

| entry | reason |
|---|---|
| EDGE_FLOOR scalar raise | state_log 2026-05-17 10:20 UTC: user lowered EDGE_FLOOR 0.30→0.10 after observing no EV improvement from tightening. Any raise without explicit user instruction violates this directive. Also structurally inapplicable (per-asset dict on dev branch). |
| Per-asset / per-hour blocks | Audit mandate: "per-asset / per-hour block frozensets do NOT exist in Phase 1 and Auditor must not introduce them." Confirmed — watchlisted only, never patched. |

---

## Run Notes

This is the **25th consecutive audit** with Δ=0 VOLARB trades. The VOLARB dataset is permanently closed (strategy deactivated 2026-05-19). Future audits will continue to report Δ=0 unless the strategy is re-activated on the VPS. These audits serve as continuity records only. No analysis can change the outcome: no patch is warranted when the subject strategy is dead code.
