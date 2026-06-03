# VOLARB Quantitative Audit — 2026-06-03 06:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-03T06:08:49Z (4 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $55.91 (prior audit 2026-06-03T00:12Z: $117.69; Δ=−$61.78 — STWA losses, no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — 2 raw new rows but both collapse to existing dedup keys; last unique trade 2026-05-19T02:50:33Z, **~363h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **16th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- 2026-05-29: CLAUDE.md fully reoriented to STWA (weather arb). No crypto at all.
- All 885 trades are historical. **Any parameter change to `strategy/volarb.py` has zero operational effect.**

**CODE MISMATCH NOTE (16th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15` (scalar).
Actual dev branch: `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` / `EDGE_FLOOR_DEFAULT=0.10` (per-asset dict).
Per explicit user instruction 2026-05-17 10:20 UTC (state_log). Prompt's "0.15 → 0.17 raise" is inapplicable.

**REM FIELD NOTE:** `term_remaining_s` is present in schema but uniformly zero for all 885 trades — not logged at entry time. REM_MAX_S and REM_MIN_S probes cannot be computed from this dataset.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (4 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($55.91) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-03T00:08Z .. 2026-06-03T06:08Z
**VOLARB trades in window: 0** (strategy retired ~363h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`).
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower (+$0.244) |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.085, +$0.214] | [+$0.244, +$0.352] | **STRADDLES ZERO** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.085)
- → All 4 criteria technically met. **SUPPRESSED — strategy RETIRED; also EDGE_FLOOR is per-asset dict on dev branch, not scalar; 0.15→0.17 raise inapplicable as-specified.**

### Per-Asset (n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +23.74 | +0.083 | [−0.180, +0.346] | STRADDLES_ZERO / BELOW_CI_LOWER | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −10.78 | −0.035 | [−0.303, +0.239] | STRADDLES_ZERO / BELOW_CI_LOWER | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +41.74 | +0.142 | [−0.127, +0.421] | STRADDLES_ZERO / BELOW_CI_LOWER | WATCHLIST |

All three assets: EV CI lower < +$0.244 baseline → BELOW_BASELINE. None cross CI_lo<0 → no lever candidate.

### Per-Hour-UTC (n≥100: none; watchlist 40≤n<100 and notable COLLECT shown)

| hour | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9 | 1.360 | +12.46 | +0.320 | [−0.401, +1.071] | STRADDLES_ZERO | COLLECT |
| H01 | 66 | 48.5 | 1.953 | +51.76 | +0.784 | [+0.155, +1.405] | BELOW_CI_LOWER | **WATCHLIST** |
| H02 | 64 | 40.6 | 1.185 | +12.56 | +0.196 | [−0.382, +0.796] | STRADDLES_ZERO | WATCHLIST |
| H03 | 36 | 44.4 | 1.374 | +13.38 | +0.372 | [−0.420, +1.190] | STRADDLES_ZERO | COLLECT |
| H04 | 37 | 32.4 | 0.873 | −5.42 | −0.147 | [−0.868, +0.609] | STRADDLES_ZERO | COLLECT |
| H05 | 35 | 14.3 | 0.359 | −30.13 | −0.861 | [−1.384, −0.242] | **BELOW_ZERO** | COLLECT |
| H06 | 35 | 31.4 | 1.020 | +0.72 | +0.021 | [−0.692, +0.797] | STRADDLES_ZERO | COLLECT |
| H07 | 31 | 19.4 | 0.616 | −13.60 | −0.439 | [−1.127, +0.323] | STRADDLES_ZERO | COLLECT |
| H08 | 35 | 28.6 | 1.498 | +14.30 | +0.409 | [−0.378, +1.275] | STRADDLES_ZERO | COLLECT |
| H09 | 28 | 14.3 | 0.438 | −15.75 | −0.563 | [−1.087, +0.081] | STRADDLES_ZERO | COLLECT |
| H10 | 38 | 34.2 | 1.162 | +5.34 | +0.141 | [−0.509, +0.793] | STRADDLES_ZERO | COLLECT |
| H11 | 71 | 35.2 | 1.196 | +13.53 | +0.191 | [−0.345, +0.753] | STRADDLES_ZERO | WATCHLIST |
| H12 | 36 | 36.1 | 0.970 | −1.20 | −0.033 | [−0.776, +0.737] | STRADDLES_ZERO | COLLECT |
| H13 | 36 | 33.3 | 1.022 | +0.83 | +0.023 | [−0.728, +0.797] | STRADDLES_ZERO | COLLECT |
| H14 | 47 | 29.8 | 0.894 | −5.05 | −0.108 | [−0.680, +0.511] | STRADDLES_ZERO | WATCHLIST |
| H15 | 36 | 30.6 | 0.898 | −4.45 | −0.124 | [−0.917, +0.712] | STRADDLES_ZERO | COLLECT |
| H16 | 30 | 16.7 | 0.428 | −21.46 | −0.715 | [−1.311, −0.049] | **BELOW_ZERO** | COLLECT |
| H17 | 21 | 38.1 | 0.752 | −8.14 | −0.388 | [−2.022, +1.050] | STRADDLES_ZERO | COLLECT |
| H18 | 25 | 60.0 | 1.406 | +7.53 | +0.301 | [−0.487, +1.135] | STRADDLES_ZERO | COLLECT |
| H20 | 3 | 100.0 | inf | +9.05 | +3.016 | [+2.966, +3.116] | AT/ABOVE | COLLECT |
| H21 | 39 | 51.3 | 1.873 | +23.67 | +0.607 | [−0.070, +1.280] | STRADDLES_ZERO | COLLECT |
| H22 | 40 | 32.5 | 0.872 | −5.48 | −0.137 | [−0.774, +0.522] | STRADDLES_ZERO | WATCHLIST |
| H23 | 57 | 33.3 | 1.004 | +0.24 | +0.004 | [−0.570, +0.621] | STRADDLES_ZERO | WATCHLIST |

No hour cell reaches n≥100. H05 and H16 have CI entirely below zero but are COLLECT-tier (n<40); informational only.

### Per-Ask-Band

| band | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.00, 0.10) | 10 | 0.0 | 0.000 | −9.11 | −0.911 | [−1.100, −0.742] | BELOW_ZERO | COLLECT |
| [0.10, 0.20) | 91 | 18.7 | 1.197 | +13.60 | +0.149 | [−0.304, +0.656] | STRADDLES_ZERO | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4 | 0.997 | −0.73 | −0.003 | [−0.275, +0.278] | STRADDLES_ZERO | BELOW_BASELINE |
| [0.30, 0.40) | 390 | 38.7 | 1.115 | +46.99 | +0.121 | [−0.110, +0.354] | STRADDLES_ZERO | BELOW_BASELINE |
| [0.40, 0.50) | 157 | 47.1 | 1.075 | +13.38 | +0.085 | [−0.282, +0.469] | STRADDLES_ZERO | BELOW_BASELINE |
| [0.50, 0.60) | 8 | 50.0 | 0.881 | −1.25 | −0.157 | [−2.010, +1.665] | STRADDLES_ZERO | COLLECT |

No ask-band cell crosses n≥100 AND CI_upper<0 → no lever candidate.

---

## Lever Probes

**ASK_CEIL probe [0.50, 0.60):**
n=8 (need n≥100). Threshold unmet. CI=[−2.010, +1.665]. **No candidate.**

**REM_MAX_S probe [260, 280):**
`term_remaining_s` uniformly 0 for all 885 trades — not logged at entry. **Cannot compute.** n=0 in range.

**REM_MIN_S probe [60, 80):**
Same field issue. **Cannot compute.** n=0 in range.

**ASK_DEPTH_MULT probe:**
No adverse-selection slippage metric available in schema. **N/A.**

---

## Proposed Patch (capped at 1)

**NO PATCH.**

Three independent suppression grounds, each sufficient alone:
1. **Strategy RETIRED** (2026-05-19): `strategy/volarb.py` is dead code. Any scalar edit has zero live effect.
2. **EDGE_FLOOR structural mismatch**: Dev branch uses `EDGE_FLOOR_BY_ASSET` dict (user directive 2026-05-17 10:20 UTC), not the scalar `0.15` assumed by the prompt. The 0.15→0.17 raise is inapplicable as-specified.
3. **Lever probe thresholds unmet**: ASK_CEIL n=8 (<100), REM probes n=0 (field all zeros), ASK_DEPTH_MULT no metric available.

Overall EDGE_FLOOR raise criteria are numerically satisfied (n=885, EV=+$0.062<+$0.10, PF=1.061<1.10, CI_lo=−$0.085<0) — suppressed by grounds 1+2.

---

## Watchlist (40≤n<100 and per-asset n≥100 below baseline)

Delta from prior audit (2026-06-03 00:12 UTC): **all cells frozen** — Δn=0 across every cell.

### Per-Asset (n≥100)

| cell | n | WR% | EV/trade | CI95 | trend vs prior |
|---|---|---|---|---|---|
| BTC | 286 | 32.9 | +$0.083 | [−0.180, +0.346] | UNCHANGED (Δn=0) |
| ETH | 305 | 32.5 | −$0.035 | [−0.303, +0.239] | UNCHANGED; only asset with negative EV |
| SOL | 294 | 38.8 | +$0.142 | [−0.127, +0.421] | UNCHANGED (Δn=0) |

### Per-Hour (40≤n<100)

| cell | n | WR% | EV/trade | CI95 | note |
|---|---|---|---|---|---|
| H01 | 66 | 48.5 | +$0.784 | [+0.155, +1.405] | Best hour; CI_lo>0 but below backtest baseline |
| H02 | 64 | 40.6 | +$0.196 | [−0.382, +0.796] | Borderline positive |
| H11 | 71 | 35.2 | +$0.191 | [−0.345, +0.753] | User unblocked H11 (2026-05-19) for CAS testing |
| H14 | 47 | 29.8 | −$0.108 | [−0.680, +0.511] | Negative EV; CI straddles |
| H22 | 40 | 32.5 | −$0.137 | [−0.774, +0.522] | Negative EV; CI straddles |
| H23 | 57 | 33.3 | +$0.004 | [−0.570, +0.621] | Flat |

### Per-Ask-Band (40≤n<100)

| cell | n | WR% | EV/trade | CI95 | note |
|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 18.7 | +$0.149 | [−0.304, +0.656] | Low WR; EV positive from large wins; high variance |

---

## Skipped — User Override (state_log)

| item | override | source |
|---|---|---|
| EDGE_FLOOR scalar | Lowered 0.30→0.10 per user directive 2026-05-17 10:20 UTC; prompt's 0.15 baseline was never the live value | state_log |
| EDGE_FLOOR_BY_ASSET | Per-asset dict introduced by user 2026-05-17 07:26 UTC; replaces scalar form | state_log |
| H11 | User unblocked for CAS testing 2026-05-19 19:XX UTC; VOLARB context moot | state_log |
| ASK_FLOOR | User lowered to 0.00 (2026-05-17); Phase 2 gated per prompt — not touched | state_log |

---

## Operational Note

Dataset is **permanently closed** at n=885. No new VOLARB trades are possible; strategy has been retired for ~15 days. Subsequent audits will produce identical output (Δn=0). The current bot runs STWA (weather arb). This audit agent should be stood down or redirected to STWA parameters.
