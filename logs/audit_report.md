# VOLARB Quantitative Audit — 2026-06-06 06:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-06T05:54:41Z (17 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $54.59 (prior audit 2026-06-04T06:12Z: $54.99; Δ=−$0.40 — STWA losses, no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — 18th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~579h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **18th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- 2026-05-29: CLAUDE.md fully reoriented to STWA (weather arb). No crypto at all.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not run it.
- Dev branch has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10` (per-user instruction 2026-05-17 10:20 UTC). Audit prompt's scalar `EDGE_FLOOR = 0.15 → 0.17` is inapplicable as specified.
- `term_remaining_s` = 0.0 for all 885 trades; REM probes cannot be computed from this dataset.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (17 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($54.59) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-06T00:00Z .. 2026-06-06T05:54Z
**VOLARB trades in window: 0** (strategy retired ~579h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.094, +$0.212] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.094)
- → All 4 criteria technically met. **SUPPRESSED — (1) strategy RETIRED, zero operational effect; (2) EDGE_FLOOR is per-asset dict on dev branch; scalar 0.15→0.17 raise inapplicable as specified.**

### Per-Asset (n≥100 for all three)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.358] | EV below CI lower (+$0.244); CI straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.305, +$0.233] | EV below CI lower; PF<1.0; CI straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.122, +$0.414] | EV below CI lower (+$0.244); CI straddles 0 | WATCHLIST |

### Per-Hour UTC (all n<100 → all COLLECTING)

| hour | n | WR% | PF | sum | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9 | 1.360 | +$12.46 | +$0.320 | [−$0.381, +$1.070] | COLLECTING |
| H01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | [+$0.164, +$1.411] | COLLECTING — fully positive CI (n=66, not yet actionable) |
| H02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | [−$0.392, +$0.792] | COLLECTING |
| H03 | 36 | 44.4 | 1.374 | +$13.38 | +$0.372 | [−$0.426, +$1.190] | COLLECTING |
| H04 | 37 | 32.4 | 0.873 | −$5.42 | −$0.147 | [−$0.872, +$0.607] | COLLECTING |
| H05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | [−$1.404, −$0.255] | COLLECTING — CI entirely <0 (n<40; observe only) |
| H06 | 35 | 31.4 | 1.020 | +$0.72 | +$0.021 | [−$0.691, +$0.769] | COLLECTING |
| H07 | 31 | 19.4 | 0.616 | −$13.60 | −$0.439 | [−$1.112, +$0.334] | COLLECTING |
| H08 | 35 | 28.6 | 1.498 | +$14.30 | +$0.409 | [−$0.388, +$1.299] | COLLECTING |
| H09 | 28 | 14.3 | 0.438 | −$15.75 | −$0.563 | [−$1.084, +$0.058] | COLLECTING |
| H10 | 38 | 34.2 | 1.162 | +$5.34 | +$0.141 | [−$0.501, +$0.813] | COLLECTING |
| H11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | [−$0.349, +$0.763] | COLLECTING |
| H12 | 36 | 36.1 | 0.970 | −$1.20 | −$0.033 | [−$0.755, +$0.734] | COLLECTING |
| H13 | 36 | 33.3 | 1.022 | +$0.83 | +$0.023 | [−$0.714, +$0.775] | COLLECTING |
| H14 | 47 | 29.8 | 0.894 | −$5.05 | −$0.108 | [−$0.689, +$0.504] | COLLECTING |
| H15 | 36 | 30.6 | 0.898 | −$4.45 | −$0.124 | [−$0.886, +$0.699] | COLLECTING |
| H16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | [−$1.301, −$0.052] | COLLECTING — CI entirely <0 (n<40; observe only) |
| H17 | 21 | 38.1 | 0.752 | −$8.14 | −$0.388 | [−$2.088, +$1.025] | COLLECTING |
| H18 | 25 | 60.0 | 1.406 | +$7.53 | +$0.301 | [−$0.486, +$1.133] | COLLECTING |
| H21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | [−$0.040, +$1.280] | COLLECTING |
| H22 | 40 | 32.5 | 0.872 | −$5.48 | −$0.137 | [−$0.770, +$0.551] | COLLECTING |
| H23 | 57 | 33.3 | 1.004 | +$0.24 | +$0.004 | [−$0.580, +$0.607] | COLLECTING |

*H19 n=0 (blocked at deploy); H20 n=3 (omitted — trivially small).*

### Per-Ask-Band (entry_price as ask proxy)

| band | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.299, +$0.667] | COLLECTING (n<100) | COLLECTING |
| [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.272, +$0.276] | EV below CI lower; CI straddles 0 | **WATCHLIST** |
| [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.112, +$0.356] | EV below CI lower; CI straddles 0 | **WATCHLIST** |
| [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.301, +$0.464] | EV below CI lower; CI straddles 0 | **WATCHLIST** |
| [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$2.004, +$1.690] | COLLECTING (n=8) | COLLECTING |

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI95=[−$2.004, +$1.690]. n≥100: **NO** (n=8). Not a lever candidate — dataset too thin. Insufficient data.
- **REM_MAX_S probe [260,280):** n=0 (`term_remaining_s` = 0.0 for all 885 trades — field not populated in VOLARB resolution path). **Probe impossible.** Cannot evaluate.
- **REM_MIN_S probe [60,80):** n=0 (same reason). **Probe impossible.** Cannot evaluate.
- **ASK_DEPTH_MULT probe:** n≥200 overall met but no per-depth adverse-selection signal extractable. EV degradation uniform across bands, not depth-specific. Not a lever candidate.

---

## Proposed Patch

**no patch**

Rationale (stack-ranked by −EV × n):
1. **EDGE_FLOOR raise (0.15 → 0.17):** All 4 numeric criteria met (n=885, EV=+$0.062, PF=1.061, CI_lo=−$0.094). Suppressed on two independent grounds: (a) VOLARB retired — VPS does not load `strategy/volarb.py`; the edit is dead code; (b) dev branch uses `EDGE_FLOOR_BY_ASSET = {"BTC":0.10,"ETH":0.10,"SOL":0.10}` (per-user instruction 2026-05-17 10:20 UTC), not a scalar `EDGE_FLOOR = 0.15` — the specified patch does not apply to this codebase state. Patching would violate both the operational-effect requirement and the "NEVER add per-asset blocks" cardinality rule.
2. **ASK_CEIL lower (0.60 → 0.55):** n=8 in [0.50,0.60). n≥100 not met. No patch.
3. **REM_MAX_S / REM_MIN_S:** n=0 in both probe windows. No patch.
4. **ASK_DEPTH_MULT raise:** No adverse-selection evidence. No patch.

---

## Watchlist (40≤n<100 or per-asset/per-hour findings)

Δ vs prior audit: dataset frozen (Δ=0 new trades). All entries carry over verbatim.

| dimension | cell | n | EV/trade | CI95 | note |
|---|---|---|---|---|---|
| asset | BTC | 286 | +$0.083 | [−$0.177, +$0.358] | EV below baseline CI lower; straddles 0 |
| asset | ETH | 305 | −$0.035 | [−$0.305, +$0.233] | PF<1.0; only net-loss asset |
| asset | SOL | 294 | +$0.142 | [−$0.122, +$0.414] | best asset; EV still below CI lower |
| ask-band | [0.20,0.30) | 227 | −$0.003 | [−$0.272, +$0.276] | net-neutral; EV below CI lower |
| ask-band | [0.30,0.40) | 390 | +$0.121 | [−$0.112, +$0.356] | most liquid band; EV below CI lower |
| ask-band | [0.40,0.50) | 157 | +$0.085 | [−$0.301, +$0.464] | EV below CI lower |
| hour | H05 | 35 | −$0.861 | [−$1.404, −$0.255] | CI entirely <0 (n<40 — observe only) |
| hour | H16 | 30 | −$0.715 | [−$1.301, −$0.052] | CI entirely <0 (n<40 — observe only) |
| hour | H01 | 66 | +$0.784 | [+$0.164, +$1.411] | **fully positive CI** — strongest hour (n=66, n<100) |
| hour | H21 | 39 | +$0.607 | [−$0.040, +$1.280] | near-fully positive CI (n=39) |

**Dataset is frozen.** No watchlist cell will cross n≥100 without VOLARB re-activation.

---

## Skipped — User Override (state_log)

- 2026-05-19: `volarb_strategy=None` — user explicitly retired VOLARB. No parameter change overrides this.
- 2026-05-17 10:20 UTC: `EDGE_FLOOR 0.30 → 0.10 globally` — user instruction in state_log; any raise above 0.10 would contradict a logged user directive without explicit re-instruction.

---

## Scheduling Note

This is the **18th consecutive audit with Δ=0 new VOLARB trades.** Dataset is frozen. Unless VOLARB is re-activated on VPS, all future VOLARB audits will produce identical output. Recommend suspending the VOLARB auditor cadence or redirecting to the active STWA strategy.
