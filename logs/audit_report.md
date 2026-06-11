# VOLARB Quantitative Audit — 2026-06-11 12:18 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-11T11:58:54Z (19.4 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $101.48 (prior audit 2026-06-11T06:15Z: $79.60; Δ=+$21.88 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 29th consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~23.0 days retired) |
| drift_status | N/A — data-mirror contains only `data/` directory; `strategy/volarb.py` not present on mirror; mirror-file-present condition false → no DEPLOY_LAG |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — CLOSED DATASET) |
| Open `audit/volarb-*` PRs | NONE (GitHub search confirmed) |
| Run | **29th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched (state_log).
- 2026-05-19: `volarb_strategy=None`, import removed (state_log).
- 2026-05-29: CLAUDE.md fully reoriented to STWA; no crypto strategy running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- Dev branch `EDGE_FLOOR` is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10` (volarb.py lines 46–47). The audit-spec scalar target `0.15→0.17` has no matching code target.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (19.4 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($101.48) |
| Code-drift guard | N/A — mirror-file-present condition false (data-mirror is data-only) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-11T05:58Z .. 2026-06-11T11:58Z

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50:33Z (~23 days before window start)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 deduped (first-fire per `(asset, round(ts_open))`). Δ=0 vs prior.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | vs baseline |
|---|---|---|
| n | 885 | — |
| WR | 34.7% | below backtest ~51.7% |
| PF | 1.061 | below target >1.30 |
| EV/trade | +$0.062 | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — |
| CI95 EV/trade (bootstrap n=5000) | [−$0.085, +$0.214] | straddles zero; below baseline CI entirely |

### Per-Asset (n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.174, +$0.346] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.292, +$0.228] | BELOW CI lower; PF<1.0; CI95 upper > 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.413] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |

All three assets: EV below baseline CI lower, but CI95 upper > 0 — insufficient to declare negative edge. Dataset closed; no new data forthcoming.

### Per-Hour-UTC (no hour reaches n≥100)

All hours n < 100 → WATCHLIST or COLLECT per rules. Notable cells:

| dimension | cell | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | +$0.784 | [+$0.162, +$1.409] | WATCHLIST — only hour with CI_lo > 0; n<100, no action |
| hour | H21 | 39 | 51.3 | +$0.607 | [−$0.061, +$1.290] | COLLECT — n<40 for action |
| hour | H16 | 30 | 16.7 | −$0.715 | [−$1.299, −$0.030] | COLLECT — second-worst; n<40 |
| hour | H05 | 35 | 14.3 | −$0.861 | [−$1.387, −$0.231] | COLLECT — worst hour; CI entirely negative but n<40 |

### Per-Ask-Band (full window; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.317, +$0.665] | BELOW CI lower | WATCHLIST (n<100) |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.271] | BELOW CI lower; PF≈1.0; CI95 upper > 0 | WATCHLIST |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.118, +$0.349] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.280, +$0.462] | BELOW CI lower; CI95 upper > 0 | WATCHLIST |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.997, +$1.684] | COLLECT (n<40) |

---

## Lever Probes

### ASK_CEIL probe: EV of trades in [0.50, 0.60)
- **n=8** — far below n≥100 threshold.
- EV=−$0.157, CI95=[−$1.997, +$1.684] — interval too wide to inform.
- **LEVER CANDIDATE: NO (n<100).**

### REM_MAX_S probe: EV of trades with hold_seconds in [260, 280)
*(hold_seconds used as proxy for sec_to_res_at_entry; VOLARB holds to resolution)*
- **n=100**, EV=+$0.452, CI95=[+$0.015, +$0.906] — positive; CI95 upper > 0.
- Lever condition requires EV < −$0.10 AND CI95 upper < 0. Neither holds.
- **LEVER CANDIDATE: NO (positive EV in probe window).**
- Data observation: hold_seconds ≥280 bucket (n=419, EV=−$1.389, WR=4.1%, CI95=[−$1.499, −$1.278]) is severely negative — represents 47% of all trades. This falls outside the nominal REM_MAX_S=280 gate, suggesting settlement timing regularly pushes fills past the window boundary. No lever covers this per Phase 1 spec; flagged for user review (see Watchlist).

### REM_MIN_S probe: EV of trades with hold_seconds in [60, 80)
- **n=2** — no data.
- **LEVER CANDIDATE: NO (n<100).**

### ASK_DEPTH_MULT probe
- `ob_depth_at_entry` populated as zero throughout dataset — field not recorded for VOLARB fills.
- No adverse-selection slippage evidence measurable from available fields.
- Overall EV positive (+$0.062); degrading-EV condition not met.
- **LEVER CANDIDATE: NO.**

---

## Proposed Patch (capped at 1)

**no patch**

Statistical conditions for EDGE_FLOOR raise are technically satisfied (n=885≥200, EV=$0.062<$0.10, PF=1.061<1.10, CI_lo=−$0.085<0). However, two hard overrides block the patch:

1. **User override (state_log 2026-05-17 10:20 UTC):** User explicitly directed EDGE_FLOOR 0.30→0.10 globally. Raising it back contradicts a recorded user instruction and violates the "never re-tighten a cell the user explicitly opened" rule.
2. **Strategy retired (state_log 2026-05-19):** `volarb_strategy=None`; VPS does not load or call `strategy/volarb.py`. Any edit has zero operational effect and would be a noise commit.

Additionally: the dev branch uses the `EDGE_FLOOR_BY_ASSET` dict (not a scalar `EDGE_FLOOR=0.15`), so the proposed `0.15→0.17` change has no syntactic target.

No other lever crossed its trigger threshold.

---

## Watchlist (40≤n<100 or notable findings without applicable lever)

All items unchanged from prior audit; dataset closed (Δ=0).

| cell | n | EV | CI95 | Δ vs prior | note |
|---|---|---|---|---|---|
| asset / ETH | 305 | −$0.035 | [−$0.292, +$0.228] | unchanged | Only asset with negative EV; PF 0.966; CI95 upper > 0 prevents lever |
| hour / H01 | 66 | +$0.784 | [+$0.162, +$1.409] | unchanged | Best hour; CI_lo > 0; if VOLARB ever re-enabled, prioritise H01 |
| hour / H05 | 35 | −$0.861 | [−$1.387, −$0.231] | unchanged | CI entirely negative; worst hour (n<40, no action) |
| hold_rem / [280,∞) | 419 | −$1.389 | [−$1.499, −$1.278] | unchanged | 47% of trades outside nominal REM_MAX_S; gate timing issue — user should investigate whether sec_to_res measurement at fill differs from entry decision |
| overall EV | 885 | +$0.062 | [−$0.085, +$0.214] | unchanged | Live EV is 25% of backtest CI lower ($0.244); VOLARB never replicated live edge |

---

## Skipped — User Override (state_log)

| item | state_log entry | decision |
|---|---|---|
| EDGE_FLOOR raise (statistical trigger met) | 2026-05-17 10:20 UTC: user set EDGE_FLOOR 0.30→0.10 globally | Skipped — explicit user instruction to lower; raising back contradicts it |
| VOLARB strategy itself | 2026-05-17 19:56 UTC (disable) + 2026-05-19 (remove import) | Any volarb.py patch is moot — user retired the strategy; no operational effect |
