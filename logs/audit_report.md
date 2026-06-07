# VOLARB Quantitative Audit — 2026-06-07 06:11 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-07T05:55:13Z (16 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $60.95 (prior audit 2026-06-06T06:12Z: $54.59; Δ=+$6.36 — STWA gains) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — 19th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~580h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **19th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- 2026-05-29: CLAUDE.md fully reoriented to STWA (weather arb). No crypto at all.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not run it.
- Dev branch has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10` (per-user instruction 2026-05-17 10:20 UTC). Audit prompt's scalar `EDGE_FLOOR = 0.15 → 0.17` is inapplicable as specified.
- `term_remaining_s` = 0.0 for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed from this dataset.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (16 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($60.95) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-07T00:11Z .. 2026-06-07T06:11Z
**VOLARB trades in window: 0** (strategy retired ~580h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.092, +$0.216] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.092)
- → All 4 criteria technically met. **SUPPRESSED — (1) strategy RETIRED: any edit to `strategy/volarb.py` has zero operational effect; (2) EDGE_FLOOR is a per-asset dict on dev branch (`EDGE_FLOOR_BY_ASSET`), not a scalar; the scalar `0.15→0.17` raise specified in the audit prompt is inapplicable as written.**

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.359] | EV below CI lower (+$0.244); CI straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.303, +$0.236] | EV below CI lower; PF<1.0; CI straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.128, +$0.414] | EV below CI lower (+$0.244); CI straddles 0 | WATCHLIST |

No per-asset cell meets BELOW criteria for a lever (CI_lo < 0 required; all three straddle zero — no lever on per-asset alone).

### Per-Hour UTC (all n<100 → COLLECTING or WATCHLIST, none actionable)

| H | n | WR% | EV/trade | status |
|---|---|---|---|---|
| H00 | 39 | 35.9 | +$0.320 | COLLECTING |
| H01 | 66 | 48.5 | +$0.784 | WATCHLIST (positive) |
| H02 | 64 | 40.6 | +$0.196 | WATCHLIST |
| H03 | 36 | 44.4 | +$0.372 | COLLECTING |
| H04 | 37 | 32.4 | −$0.147 | COLLECTING |
| H05 | 35 | 14.3 | −$0.861 | COLLECTING |
| H06 | 35 | 31.4 | +$0.021 | COLLECTING |
| H07 | 31 | 19.4 | −$0.439 | COLLECTING |
| H08 | 35 | 28.6 | +$0.409 | COLLECTING |
| H09 | 28 | 14.3 | −$0.563 | COLLECTING |
| H10 | 38 | 34.2 | +$0.141 | COLLECTING |
| H11 | 71 | 35.2 | +$0.191 | WATCHLIST |
| H12 | 36 | 36.1 | −$0.033 | COLLECTING |
| H13 | 36 | 33.3 | +$0.023 | COLLECTING |
| H14 | 47 | 29.8 | −$0.108 | WATCHLIST |
| H15 | 36 | 30.6 | −$0.124 | COLLECTING |
| H16 | 30 | 16.7 | −$0.715 | COLLECTING |
| H17 | 21 | 38.1 | −$0.388 | COLLECTING |
| H18 | 25 | 60.0 | +$0.301 | COLLECTING |
| H20 | 3 | 100.0 | +$3.016 | COLLECTING |
| H21 | 39 | 51.3 | +$0.607 | COLLECTING |
| H22 | 40 | 32.5 | −$0.137 | WATCHLIST |
| H23 | 57 | 33.3 | +$0.004 | WATCHLIST |

No per-hour cell reaches n≥100. Maximum is H01 (n=66). Dataset frozen — these cells will never cross the threshold.

### Per-Ask-Band

| band | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 18.7 | +$0.149 | [−$0.314, +$0.671] | below CI lower; CI straddles 0 | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4 | −$0.003 | [−$0.271, +$0.268] | below CI lower; CI straddles 0 | n≥100; CI straddles 0 — no lever |
| [0.30, 0.40) | 390 | 38.7 | +$0.121 | [−$0.105, +$0.357] | below CI lower; CI straddles 0 | n≥100; CI straddles 0 — no lever |
| [0.40, 0.50) | 157 | 47.1 | +$0.085 | [−$0.303, +$0.472] | below CI lower; CI straddles 0 | n≥100; CI straddles 0 — no lever |
| [0.50, 0.60) | 8 | 50.0 | −$0.157 | [−$1.991, +$1.690] | n<100 | COLLECTING |

No ask-band cell meets ASK_CEIL lever criteria (ASK_CEIL requires CI95 upper < 0; all bands have CI_hi > 0).

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60):** n=8, EV=−$0.157, CI95=[−$1.99, +$1.69] → **INSUFFICIENT** (n=8 < 100). Not a lever candidate.
- **REM_MAX_S probe [260, 280):** n=0 — `term_remaining_s`=0.0 for all 885 trades (field not populated in VOLARB era). **DATA ABSENT — cannot compute.**
- **REM_MIN_S probe [60, 80):** n=0 — same. **DATA ABSENT — cannot compute.**
- **ASK_DEPTH_MULT probe:** No adverse-selection slippage field logged. Overall EV=+$0.062 (positive, not degrading). **No evidence criterion met — not a lever candidate.**

---

## Proposed Patch

**No patch.**

Reasons (in priority order):
1. **Strategy retired** — VOLARB has not fired since 2026-05-19T02:50Z (~580h). Any edit to `strategy/volarb.py` has zero operational effect.
2. **EDGE_FLOOR lever inapplicable as specified** — dev branch uses `EDGE_FLOOR_BY_ASSET` dict, not a scalar; the `0.15→0.17` edit in the audit prompt cannot be applied.
3. **REM probes impossible** — `term_remaining_s`=0.0 across all 885 trades; [260,280) and [60,80) cells contain n=0.
4. **ASK_CEIL probe n=8** — three orders of magnitude below the n≥100 gate.
5. **ASK_DEPTH_MULT** — no adverse-selection evidence; EV>0 overall.

All 4 EDGE_FLOOR criteria are numerically satisfied but the patch is suppressed on grounds 1+2. Consistent with prior 18 audits.

---

## Watchlist (40≤n<100, vs prior audit)

| cell | n | EV/trade | CI95 | delta vs prior |
|---|---|---|---|---|
| asset: BTC | 286 | +$0.083 | [−$0.177, +$0.359] | Δ=0 |
| asset: ETH | 305 | −$0.035 | [−$0.303, +$0.236] | Δ=0 |
| asset: SOL | 294 | +$0.142 | [−$0.128, +$0.414] | Δ=0 |
| ask [0.10,0.20) | 91 | +$0.149 | [−$0.314, +$0.671] | Δ=0 |
| H01 | 66 | +$0.784 | — | Δ=0 |
| H02 | 64 | +$0.196 | — | Δ=0 |
| H11 | 71 | +$0.191 | — | Δ=0 |
| H14 | 47 | −$0.108 | — | Δ=0 |
| H22 | 40 | −$0.137 | — | Δ=0 |
| H23 | 57 | +$0.004 | — | Δ=0 |

All Δ=0. Dataset is permanently frozen at n=885. Watchlist cells will never graduate to n≥100.

---

## Skipped — User Override (state_log)

No cells marked as user-overridden for VOLARB.

---

## Note for User

The VOLARB audit mandate is fully exhausted. The dataset is closed at n=885 and no new trades will ever arrive. Consider decommissioning this scheduled audit — there is no further actionable signal to extract.
