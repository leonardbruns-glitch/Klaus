# VOLARB Quantitative Audit — 2026-05-28 06:15 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-28T06:12:41Z (3.3 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $95.30 (unchanged from prior audit 2026-05-28 00:18 UTC — no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~219h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE |
| Run | **13th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- All 885 trades are historical. Any parameter change to `strategy/volarb.py` has zero operational effect.

**CODE MISMATCH NOTE (13th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual code: `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` / `EDGE_FLOOR_DEFAULT=0.10`
(per-asset dict; no scalar `EDGE_FLOOR`), set by explicit user instruction 2026-05-17 10:20 UTC
(state_log). Prompt's "0.15 → 0.17 raise" is inapplicable.

**REM FIELD NOTE:** `term_remaining_s` is 0.0/None for all 885 VOLARB trades — field was not
populated in the VOLARB era. REM_MAX_S and REM_MIN_S lever probes: n=0 in both windows. No data.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (3.3 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($95.30) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-28T00:12Z .. 2026-05-28T06:12Z
**VOLARB trades in window: 0** (strategy retired ~219h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`).
Backtest $1-equiv CI baseline = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.092, +$0.216] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.092)
→ All 4 criteria technically MET — suppressed: strategy RETIRED. Patch has zero operational effect.

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.344] | BELOW CI lower | watchlist |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.78 | −$0.035 | [−$0.286, +$0.234] | BELOW CI lower | watchlist |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.74 | +$0.142 | [−$0.126, +$0.412] | BELOW CI lower | watchlist |

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.00,0.10) | 10 | 0.0% | 0.000 | −$9.11 | −$0.911 | [−$1.107,−$0.742] | BELOW (n<100) | n<40 ignore |
| ask_band | [0.10,0.20) | 91 | 18.7% | 1.197 | +$13.60 | +$0.149 | [−$0.302,+$0.647] | BELOW CI lower | watchlist |
| ask_band | [0.20,0.30) | 227 | 26.4% | 0.997 | −$0.73 | −$0.003 | [−$0.267,+$0.266] | BELOW CI lower | watchlist |
| ask_band | [0.30,0.40) | 390 | 38.7% | 1.115 | +$46.99 | +$0.120 | [−$0.111,+$0.364] | BELOW CI lower | watchlist |
| ask_band | [0.40,0.50) | 157 | 47.1% | 1.075 | +$13.38 | +$0.085 | [−$0.303,+$0.475] | BELOW CI lower | watchlist |
| ask_band | [0.50,0.60) | 8 | 50.0% | 0.881 | −$1.25 | −$0.157 | [−$2.016,+$1.690] | insufficient | n<40 ignore |

### Per-Hour UTC

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| hour | H00 | 39 | 35.9% | +$0.320 | [−$0.377,+$1.080] | BELOW (n<100) | n<100 collect |
| hour | H01 | 66 | 48.5% | +$0.784 | [+$0.172,+$1.411] | ABOVE CI lower | watchlist |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.389,+$0.795] | BELOW (n<100) | n<100 collect |
| hour | H03 | 36 | 44.4% | +$0.372 | [−$0.389,+$1.199] | BELOW (n<100) | n<40 ignore |
| hour | H04 | 37 | 32.4% | −$0.146 | [−$0.872,+$0.593] | BELOW (n<100) | n<40 ignore |
| hour | H05 | 35 | 14.3% | −$0.861 | [−$1.385,−$0.234] | BELOW (n<100) | n<40 ignore |
| hour | H06 | 35 | 31.4% | +$0.021 | [−$0.689,+$0.776] | BELOW (n<100) | n<40 ignore |
| hour | H07 | 31 | 19.4% | −$0.439 | [−$1.106,+$0.343] | BELOW (n<100) | n<40 ignore |
| hour | H08 | 35 | 28.6% | +$0.409 | [−$0.394,+$1.308] | BELOW (n<100) | n<40 ignore |
| hour | H09 | 28 | 14.3% | −$0.563 | [−$1.080,+$0.034] | BELOW (n<100) | n<40 ignore |
| hour | H10 | 38 | 34.2% | +$0.141 | [−$0.492,+$0.800] | BELOW (n<100) | n<40 ignore |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.334,+$0.742] | BELOW (n<100) | n<100 collect |
| hour | H12 | 36 | 36.1% | −$0.033 | [−$0.738,+$0.748] | BELOW (n<100) | n<40 ignore |
| hour | H13 | 36 | 33.3% | +$0.023 | [−$0.669,+$0.818] | BELOW (n<100) | n<40 ignore |
| hour | H14 | 47 | 29.8% | −$0.107 | [−$0.698,+$0.512] | BELOW (n<100) | watchlist |
| hour | H15 | 36 | 30.6% | −$0.124 | [−$0.896,+$0.740] | BELOW (n<100) | n<40 ignore |
| hour | H16 | 30 | 16.7% | −$0.715 | [−$1.304,−$0.036] | BELOW (n<100) | n<40 ignore |
| hour | H17 | 21 | 38.1% | −$0.387 | [−$2.050,+$1.006] | BELOW (n<100) | n<40 ignore |
| hour | H18 | 25 | 60.0% | +$0.301 | [−$0.490,+$1.146] | BELOW (n<100) | n<40 ignore |
| hour | H21 | 39 | 51.3% | +$0.607 | [−$0.066,+$1.280] | BELOW (n<100) | n<40 ignore |
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.796,+$0.543] | BELOW (n<100) | watchlist |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.552,+$0.598] | BELOW (n<100) | n<100 collect |

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60):** n=8 — FAR below n≥100 threshold. CI95=[−$2.016,+$1.690] encompasses zero. NO lever candidate. Insufficient data.
- **REM_MAX_S probe [260, 280):** n=0 — `term_remaining_s` field was not populated in the VOLARB era (all trades = 0.0/None). Data structurally absent. NO lever candidate.
- **REM_MIN_S probe [60, 80):** n=0 — same reason. NO lever candidate.
- **ASK_DEPTH_MULT probe:** No slippage or adverse-selection fields available in VOLARB trade records. NO lever candidate.

---

## Proposed Patch (capped at 1)

**no patch**

Reasons:
1. Strategy RETIRED 2026-05-19. Any edit to `strategy/volarb.py` has zero operational effect.
2. EDGE_FLOOR raise: all 4 criteria technically met (n=885≥200, EV=+$0.062<+$0.10, PF=1.061<1.10, CI_lo=−$0.092<0) — suppressed because strategy is retired and prompt's scalar `EDGE_FLOOR` does not match actual per-asset dict (`EDGE_FLOOR_BY_ASSET`; all 0.10 per 2026-05-17 user instruction).
3. ASK_CEIL, REM_MAX_S, REM_MIN_S: all probes have n=0 or n<<100.
4. ASK_DEPTH_MULT: no slippage evidence.

---

## Watchlist (40≤n<100 trending negative; n≥100 BELOW CI lower)

Δ vs prior audit (2026-05-28 00:18 UTC): **unchanged** (Δ=0 new trades; all 7 cells identical)

| # | dimension | cell | n | EV/trade | CI95 | note |
|---|---|---|---|---|---|---|
| 1 | asset | BTC | 286 | +$0.083 | [−$0.177,+$0.344] | n≥100, EV BELOW CI lower +$0.244 |
| 2 | asset | ETH | 305 | −$0.035 | [−$0.286,+$0.234] | n≥100, EV BELOW CI lower; only asset with negative EV |
| 3 | asset | SOL | 294 | +$0.142 | [−$0.126,+$0.412] | n≥100, EV BELOW CI lower; highest EV asset |
| 4 | ask_band | [0.10,0.20) | 91 | +$0.149 | [−$0.302,+$0.647] | 40≤n<100, EV below +$0.244 baseline |
| 5 | ask_band | [0.20,0.30) | 227 | −$0.003 | [−$0.267,+$0.266] | n≥100, EV≈0; only ask band with negative point EV |
| 6 | ask_band | [0.30,0.40) | 390 | +$0.120 | [−$0.111,+$0.364] | n≥100, largest cell, BELOW CI lower |
| 7 | ask_band | [0.40,0.50) | 157 | +$0.085 | [−$0.303,+$0.475] | n≥100, BELOW CI lower |

Additional (40≤n<100, not in prior watch=7 count but noted for completeness):
- H14 (n=47, EV=−$0.107): negative trend; no lever exists for VOLARB per-hour blocks
- H22 (n=40, EV=−$0.137): negative trend; same constraint

---

## Skipped — User Override (state_log)

- **EDGE_FLOOR:** User explicitly lowered to 0.10 (dict form) on 2026-05-17 10:20 UTC (state_log). Prompt's "0.15 → 0.17 raise" is a pre-registered action that conflicts with user's subsequent override. Not applied.
- **ASK_FLOOR:** Phase 2 gated per prompt. Not touched.

---

## Status

**NO_PATCH** — strategy retired 2026-05-19, n=885 Δ=0, 13th consecutive audit with no new data. Dataset CLOSED; watchlist frozen at 7 items. No operational effect from any parameter change.
