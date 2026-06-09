# VOLARB Quantitative Audit — 2026-06-09 06:13 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-09T05:55:06Z (17 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $70.22 (prior audit 2026-06-08T18:15Z: $70.00; Δ=**+$0.22**) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 22nd consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~630h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **22nd consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten.
- 2026-05-29: CLAUDE.md fully reoriented to STWA. No crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not run it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed.
- EDGE_FLOOR on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` (per-asset dict), not scalar 0.15; the audit prompt's `0.15→0.17` raise is structurally inapplicable.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (17 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($70.22) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-09T00:00Z .. 2026-06-09T05:55Z
**VOLARB trades in window: 0** (strategy retired ~630h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`). Δ vs prior audit = 0.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.093, +$0.217] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.093)
- → All 4 criteria technically met. **SUPPRESSED** — two grounds:
  1. Strategy RETIRED on VPS since 2026-05-19: any edit to `strategy/volarb.py` has zero operational effect.
  2. EDGE_FLOOR is a per-asset dict on dev branch (`EDGE_FLOOR_BY_ASSET`), not a scalar; the scalar `0.15→0.17` raise is inapplicable as written.

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower; CI straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.223] | BELOW CI lower; PF<1.0; CI straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower; CI straddles 0 | WATCHLIST |

### Per-Hour-UTC (n≥40 shown; 5000-round bootstrap CI95)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline | status |
|---|---|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | [+$0.174, +$1.416] | ABOVE baseline — CI strictly positive | trend-pos (n<100) |
| hour | H02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | [−$0.360, +$0.796] | straddles 0 | trend-neg (n<100) |
| hour | H05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | [−$1.393, −$0.241] | CI upper < 0 | n<100, watch (35) |
| hour | H11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | [−$0.356, +$0.743] | straddles 0 | trend-neg (n<100) |
| hour | H14 | 47 | 29.8 | 0.894 | −$5.05 | −$0.108 | [−$0.694, +$0.492] | straddles 0 | trend-neg (n<100) |
| hour | H16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | [−$1.305, −$0.038] | CI upper < 0 | n<40, ignore |
| hour | H21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | [−$0.052, +$1.261] | straddles 0 | watchlist-size (n<100) |
| hour | H22 | 40 | 32.5 | 0.872 | −$5.48 | −$0.137 | [−$0.768, +$0.540] | straddles 0 | trend-neg (n<100) |
| hour | H23 | 57 | 33.3 | 1.004 | +$0.24 | +$0.004 | [−$0.553, +$0.597] | straddles 0 | trend-neg (n<100) |

No per-hour cell reaches n≥100; no hour-level patch lever triggered.

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10, 0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.308, +$0.661] | BELOW CI lower; straddles 0 | watchlist-size (40≤n<100) |
| ask_band | [0.20, 0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.274] | BELOW CI lower; PF<1.0 | WATCHLIST |
| ask_band | [0.30, 0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.120 | [−$0.108, +$0.355] | BELOW CI lower; CI straddles 0 | WATCHLIST |
| ask_band | [0.40, 0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.281, +$0.474] | BELOW CI lower; CI straddles 0 | WATCHLIST |
| ask_band | [0.50, 0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.684] | n<40 — ignore | n<40, ignore |

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60):** n=8 — NOT a lever candidate (n<100 threshold not met; CI95=[−$1.991, +$1.684] extremely wide)
- **REM_MAX_S probe [260, 280):** n=0 — NOT evaluated. `term_remaining_s` field is 0.0 for all 885 VOLARB trades (field not populated during VOLARB era). Cannot assess.
- **REM_MIN_S probe [60, 80):** n=0 — NOT evaluated. Same reason as REM_MAX_S.
- **ASK_DEPTH_MULT probe:** mean slippage_entry=$0.00000 across n=885; zero trades with slippage_entry>$0.01. No adverse-selection evidence. NOT a lever candidate.

---

## Proposed Patch

**no patch**

Rationale:
1. **Strategy retired** (2026-05-19): `strategy/volarb.py` not loaded on VPS. Any scalar edit has zero operational effect — a noise PR.
2. **Structural mismatch**: EDGE_FLOOR on dev branch is `EDGE_FLOOR_BY_ASSET` (per-asset dict at 0.10 each), not the scalar 0.15 the prompt assumes. The `0.15→0.17` raise is inapplicable without a schema redesign, which exceeds the 1-scalar-edit cap.
3. **All other lever probes** failed n≥100 gate (ASK_CEIL n=8; REM probes n=0; ASK_DEPTH_MULT no evidence).
4. EDGE_FLOOR criteria are technically satisfied (n=885≥200, EV=$0.062<$0.10, PF=1.061<1.10, CI_lo=−$0.093<0) but suppression is correct: dead code + structural mismatch.

---

## Watchlist (40≤n<100, per-asset/per-hour findings; dataset closed — no delta expected)

| cell | n | WR% | EV/trade | CI95 | delta vs prior | note |
|---|---|---|---|---|---|---|
| H01 | 66 | 48.5 | +$0.784 | [+$0.174, +$1.416] | unchanged | best hour; CI strictly positive; VOLARB re-activation priority |
| H05 | 35 | 14.3 | −$0.861 | [−$1.393, −$0.241] | unchanged | worst hour; CI upper < 0 |
| H21 | 39 | 51.3 | +$0.607 | [−$0.052, +$1.261] | unchanged | second-best hour |
| ask [0.10,0.20) | 91 | 18.7 | +$0.149 | [−$0.308, +$0.661] | unchanged | positive sum despite low WR |
| ETH (asset) | 305 | 32.5 | −$0.035 | [−$0.294, +$0.223] | unchanged | only asset with negative EV and PF<1.0 |

---

## Skipped — User Override (state_log)

None applicable. Dataset fully closed; no live override decisions pending.

---

## Status

`NO_PATCH | n=885 (Δ=0) | watch=5 | run=22`

Strategy retired. Patch suppressed: dead code + structural mismatch (EDGE_FLOOR_BY_ASSET ≠ scalar 0.15).
This audit will produce identical no-patch results until VOLARB is re-activated or this mandate is retired.
