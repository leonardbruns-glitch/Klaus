# VOLARB Quantitative Audit — 2026-05-24 00:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-24T00:07:50Z (≈4.6 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $31.70 (prior audit 2026-05-22 18:10 UTC: $32.34 → **−$0.64 Δ** — CAS_LOWASK/weather, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **117h+ retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation — CLOSED) |
| Open audit PRs | NONE (GitHub MCP confirmed) |
| Run | **7th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.** VOLARB entries disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched).
Formally retired 2026-05-19 (`volarb_strategy=None`, import removed, CLAUDE.md rewritten).
All 885 trades are historical. No parameter change to `strategy/volarb.py` has operational effect.

**CODE MISMATCH NOTE (7th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`
(prescribing raise 0.15→0.17). Actual code: `EDGE_FLOOR_DEFAULT=0.10`, `EDGE_FLOOR_BY_ASSET
={"BTC":0.10,"ETH":0.10,"SOL":0.10}` — set by explicit user instruction 2026-05-17 10:20 UTC
(state_log). Raising 0.15→0.17 is inapplicable; the current value is 0.10. Adapting the raise
to 0.10→0.12 is also deferred: (a) strategy is retired; (b) microshadow evidence (n=214) shows
edge[0.10,0.15) is the *best* performing band (WR=48.1% EV=+$0.252) — raising the floor would
exclude the positive-EV range, contradicting the fix intent; (c) explicit user instruction set 0.10.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (4.6 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($31.70) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE (GitHub MCP confirmed) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK/weather) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-23T18:07Z .. 2026-05-24T00:07Z
**VOLARB trades in window: 0** (strategy retired 117h+ ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | — |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (post first-fire dedup) unchanged since 2026-05-19T02:50:33Z.
Baseline $1-equiv CI = [+$0.244, +$0.352] per audit protocol.

### Overall

| metric | value | backtest baseline ($1-equiv) | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 (mid) | BELOW CI lower |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.092, +$0.216] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.092)
→ All 4 criteria MET — **NO PATCH** (see Proposed Patch section for reasons).

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | −$0.180 | +$0.346 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | −$0.299 | +$0.234 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | −$0.127 | +$0.417 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |

All three assets below baseline CI lower at n≥100. No asset CI entirely negative (CI_hi > 0 for all).

### Per-Hour-UTC (n≥10 shown)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | status |
|---|---|---|---|---|---|---|---|---|---|
| hour_utc | H00 | 39 | 35.9 | 1.360 | +$12.46 | +$0.320 | −$0.410 | +$1.062 | n<40 ignore |
| hour_utc | H01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | +$0.142 | +$1.410 | ABOVE baseline ★ |
| hour_utc | H02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | −$0.388 | +$0.795 | WATCHLIST |
| hour_utc | H03 | 36 | 44.4 | 1.374 | +$13.38 | +$0.372 | −$0.455 | +$1.149 | n<40 ignore |
| hour_utc | H04 | 37 | 32.4 | 0.873 | −$5.42 | −$0.147 | −$0.871 | +$0.634 | n<40 ignore |
| hour_utc | H05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | −$1.383 | −$0.230 | n<40 ignore |
| hour_utc | H06 | 35 | 31.4 | 1.020 | +$0.72 | +$0.021 | −$0.713 | +$0.780 | n<40 ignore |
| hour_utc | H07 | 31 | 19.4 | 0.617 | −$13.60 | −$0.439 | −$1.146 | +$0.325 | n<40 ignore |
| hour_utc | H08 | 35 | 28.6 | 1.498 | +$14.30 | +$0.409 | −$0.401 | +$1.305 | n<40 ignore |
| hour_utc | H09 | 28 | 14.3 | 0.438 | −$15.75 | −$0.563 | −$1.077 | +$0.058 | n<40 ignore |
| hour_utc | H10 | 38 | 34.2 | 1.162 | +$5.34 | +$0.141 | −$0.487 | +$0.813 | n<40 ignore |
| hour_utc | H11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | −$0.344 | +$0.747 | WATCHLIST |
| hour_utc | H12 | 36 | 36.1 | 0.970 | −$1.20 | −$0.033 | −$0.768 | +$0.740 | n<40 ignore |
| hour_utc | H13 | 36 | 33.3 | 1.022 | +$0.83 | +$0.023 | −$0.722 | +$0.783 | n<40 ignore |
| hour_utc | H14 | 47 | 29.8 | 0.894 | −$5.05 | −$0.108 | −$0.681 | +$0.493 | WATCHLIST (neg EV) |
| hour_utc | H15 | 36 | 30.6 | 0.898 | −$4.45 | −$0.124 | −$0.899 | +$0.702 | n<40 ignore |
| hour_utc | H16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | −$1.291 | −$0.049 | n<40 ignore |
| hour_utc | H17 | 21 | 38.1 | 0.752 | −$8.14 | −$0.388 | −$2.087 | +$1.057 | n<40 ignore |
| hour_utc | H18 | 25 | 60.0 | 1.406 | +$7.53 | +$0.301 | −$0.497 | +$1.108 | n<40 ignore |
| hour_utc | H21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | −$0.059 | +$1.277 | n<40 ignore |
| hour_utc | H22 | 40 | 32.5 | 0.872 | −$5.48 | −$0.137 | −$0.788 | +$0.543 | WATCHLIST (neg EV) |
| hour_utc | H23 | 57 | 33.3 | 1.004 | +$0.24 | +$0.004 | −$0.576 | +$0.605 | WATCHLIST |

No hour cell has n≥100.

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.00,0.10) | 10 | 0.0 | 0.000 | −$9.11 | −$0.911 | −$1.097 | −$0.742 | n<40 ignore | — |
| ask_band | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | −$0.303 | +$0.666 | BELOW CI lower | WATCHLIST |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | −$0.268 | +$0.265 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | −$0.105 | +$0.359 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | −$0.300 | +$0.461 | BELOW CI lower | n≥100, EV<$0.244, CI_lo<$0.244 |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | −$2.004 | +$1.697 | n<40 ignore | — |

---

## Lever Probes

**ASK_CEIL probe [0.50,0.60):**
n=8, EV=−$0.157, CI95=[−$2.004, +$1.697]
Criteria: n≥100=**NO** (8<100) → **NOT MET**

**REM_MAX_S probe [260,280):**
n=221, EV=−$0.004, CI95=[−$0.320, +$0.316]
Criteria: n≥100=YES · EV<−$0.10=**NO** (−$0.004 > −$0.10) → **NOT MET**

**REM_MIN_S probe [60,80):**
n=8, EV=−$1.076, CI95=[−$1.339, −$0.838] — CI entirely negative, but n<100
Criteria: n≥100=**NO** (8<100) → **NOT MET**
(Informational: if VOLARB is ever reactivated, this is the first lever to pull — REM_MIN_S 60→80.)

**ASK_DEPTH_MULT probe:**
No `slippage_entry` data in VOLARB trade log → adverse selection unquantifiable → **NOT MET**

---

## Proposed Patch (capped at 1)

**NO PATCH.**

Reasons, in priority order:
1. **Strategy retired** — `volarb_strategy=None` by explicit user instruction 2026-05-19. Any scalar edit to `strategy/volarb.py` has zero operational effect on live trading.
2. **No lever probe criteria fully met** — ASK_CEIL n=8 (need ≥100), REM_MAX_S EV=−$0.004 (need <−$0.10), REM_MIN_S n=8 (need ≥100), ASK_DEPTH_MULT no slippage data.
3. **EDGE_FLOOR raise deferred** — all 4 overall criteria technically met (n=885, EV=+$0.062<$0.10, PF=1.061<1.10, CI_lo=−$0.092<0), but: (a) strategy is retired so no live impact; (b) current EDGE_FLOOR is 0.10 not 0.15, making the prescribed 0.15→0.17 patch inapplicable; (c) microshadow (n=214 matched) documents edge[0.10,0.15) WR=48.1% EV=+$0.252 — the best edge band — raising EDGE_FLOOR above 0.10 would exclude positive-EV trades; (d) explicit user instruction set 0.10 after observing 0.30 and 0.15 didn't improve EV/trade.

---

## Watchlist (40≤n<100 with EV below baseline CI lower or negative EV)

Δ vs prior audit (2026-05-22 18:10 UTC): **UNCHANGED** — dataset permanently closed, n=885 static.

| cell | n | EV/trade | CI95 | Δ vs prior | note |
|---|---|---|---|---|---|
| H02 | 64 | +$0.196 | [−$0.388, +$0.795] | UNCHANGED | positive but below baseline CI lower ($0.244) |
| H11 | 71 | +$0.191 | [−$0.344, +$0.747] | UNCHANGED | positive but below baseline CI lower |
| H14 | 47 | −$0.108 | [−$0.681, +$0.493] | UNCHANGED | negative EV; CI straddles zero |
| H22 | 40 | −$0.137 | [−$0.788, +$0.543] | UNCHANGED | negative EV; CI straddles zero |
| H23 | 57 | +$0.004 | [−$0.576, +$0.605] | UNCHANGED | near-zero EV; CI straddles zero |
| ask[0.10,0.20) | 91 | +$0.149 | [−$0.303, +$0.666] | UNCHANGED | WR=18.7% low; EV below baseline CI lower |

None of these cells will cross n≥100 — VOLARB dataset is permanently closed.

**Informational (n<40, not watchlist):** H05 WR=14.3% EV=−$0.861, H16 WR=16.7% EV=−$0.715,
H07 WR=19.4% EV=−$0.439. Worst VOLARB hours. Block first if strategy ever reactivated.

---

## Skipped — User Override (state_log)

| decision | date | source |
|---|---|---|
| VOLARB globally disabled (volarb_strategy=None) | 2026-05-19 | User instruction |
| EDGE_FLOOR lowered 0.30→0.10 | 2026-05-17 10:20 UTC | User instruction |
| ASK_FLOOR lowered 0.10→0.00 (longshots activated) | 2026-05-17 | User instruction |
| EDGE_FLOOR raise (any) | — | Deferred: strategy retired + microshadow evidence + user-set 0.10 |

---

## Auditor Notes

**7th consecutive audit** finding n=885, Δ=0. VOLARB dataset permanently closed
(strategy retired 2026-05-19T19:56Z). Further audits are informational-only unless
the strategy is reactivated with a new activation timestamp.

If VOLARB is reactivated: raise REM_MIN_S 60→80 first (CI entirely negative in [60,80)s);
target H01 for maximum edge (only hour with CI95 above zero: EV=+$0.784 CI=[+$0.142,+$1.410]);
avoid H05/H16/H07 (worst hours). Do not reuse the closed 885-trade window as live evidence.
