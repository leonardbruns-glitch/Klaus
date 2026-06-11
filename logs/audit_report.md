# VOLARB Quantitative Audit — 2026-06-11 00:13 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-11T00:07:08Z (6 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $76.95 (prior audit 2026-06-10T18:20Z: $91.26; Δ=−$14.31 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 27th consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~21.4 days retired) |
| drift_status | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition not met |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **27th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched (state_log).
- 2026-05-19: `volarb_strategy=None`, import removed (state_log).
- 2026-05-29: CLAUDE.md fully reoriented to STWA; no crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `term_remaining_s = 0.0` for all 885 trades (field populated by LDA/TERMINAL, not VOLARB); REM probes use `math.ceil(ts_open/300)*300 − ts_open` as the approximation.
- `EDGE_FLOOR` on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` / `EDGE_FLOOR_DEFAULT=0.10`; audit-spec scalar `0.15→0.17` is structurally inapplicable.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (6 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($76.95) |
| Code-drift guard | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition false; dev branch levers intact at lines 46–65 |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-10T18:07Z .. 2026-06-11T00:07Z
**VOLARB trades in window: 0** (strategy retired ~21 days ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.084, +$0.209] | straddles zero; below baseline CI entirely |

### Per-Asset (all n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.352] | BELOW CI lower | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.301, +$0.233] | BELOW CI lower; PF<1.0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.126, +$0.405] | BELOW CI lower | WATCHLIST |

### Per-Hour-UTC (no hour reaches n≥100; all WATCHLIST n=40–99 or IGNORE n<40)

| dimension | cell | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | +$0.784 | [+$0.163, +$1.385] | WATCHLIST — positive outlier; CI_lo>0 but n<100 |
| hour | H02 | 64 | 40.6 | +$0.196 | [−$0.391, +$0.776] | WATCHLIST — positive trend |
| hour | H11 | 71 | 35.2 | +$0.191 | [−$0.369, +$0.785] | WATCHLIST — positive trend |
| hour | H22 | 40 | 32.5 | −$0.137 | [−$0.791, +$0.500] | WATCHLIST — negative trend (straddles zero) |
| hour | H23 | 57 | 33.3 | +$0.004 | [−$0.570, +$0.606] | WATCHLIST — flat |
| hour | H14 | 47 | 29.8 | −$0.108 | [−$0.647, +$0.538] | WATCHLIST — negative trend |
| hour | H05 | 35 | 14.3 | −$0.861 | [−$1.406, −$0.215] | IGNORE (n<40) — worst hour; CI above zero only barely missing |
| hour | H16 | 30 | 16.7 | −$0.715 | [−$1.273, −$0.054] | IGNORE (n<40) — strong negative signal |

### Per-Ask-Band (vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.00,0.10) | 10 | 0.0 | 0.000 | −$9.11 | −$0.911 | [−$1.093, −$0.742] | BELOW CI lower | IGNORE (n<40) |
| ask_band | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.312, +$0.663] | BELOW CI lower | WATCHLIST (n=91<100) |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.275, +$0.264] | BELOW CI lower; PF<1.0 | WATCHLIST→n≥100 |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.128, +$0.350] | BELOW CI lower | WATCHLIST→n≥100 |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.294, +$0.466] | BELOW CI lower | WATCHLIST→n≥100 |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.690] | n<40 | IGNORE |

---

## Lever Probes

### ASK_CEIL probe [0.50,0.60)
n=8 — **SKIP** (need n≥100). Lever condition not evaluated.

### REM_MAX_S probe rem∈[260,280)
n=221, EV=−$0.004, CI95=[−$0.321, +$0.314]
CI95 upper = +$0.314 > 0 → **lever condition NOT met** (need CI95_upper < 0).
REM distribution: [220,240)=342, [260,280)=221 dominate; [60,80)=8, [80,100)=6, [240,260)=54.

### REM_MIN_S probe rem∈[60,80)
n=8 — **SKIP** (need n≥100). Lever condition not evaluated.

### ASK_DEPTH_MULT probe (adverse selection)
`slippage_entry` = 0.0 for all 885 trades (CLOB fills at limit; no slippage recorded).
No adverse-selection evidence. n<200 overall → lever condition not met regardless.

---

## Proposed Patch (capped at 1)

**NO PATCH.**

Reasons (all must hold simultaneously for a patch):

1. **Δn=0** — This is the 27th consecutive audit on the same closed 885-trade dataset. No new information since prior audit.

2. **Strategy disabled** — VOLARB entries were disabled 2026-05-17 and fully removed 2026-05-19 (`volarb_strategy=None`). The VPS does not load or call `strategy/volarb.py`. Any scalar edit has zero operational effect. Generating a patch PR on a retired strategy would be noise.

3. **EDGE_FLOOR structural inapplicability** — Conditions for the EDGE_FLOOR raise (n=885≥200 ✓, EV=+$0.062<+$0.10 ✓, PF=1.061<1.10 ✓, CI_lo=−$0.084<0 ✓) are technically met, but the scalar on dev branch is `EDGE_FLOOR_DEFAULT=0.10` (not `0.15` as the audit spec assumes). The specified patch `0.15→0.17` is structurally inapplicable as written. Applying an ad-hoc `0.10→0.12` would not correspond to any pre-registered lever value.

4. **No lever probe clears** — REM_MAX_S [260,280) has CI_hi=+$0.314 > 0 → no go. ASK_CEIL and REM_MIN_S both n<100 → skip. ASK_DEPTH_MULT has zero adverse-selection evidence.

Prior audit (2026-06-10 18:20 UTC) reached identical conclusion for identical reasons.

---

## Watchlist (40≤n<100 AND per-asset/per-hour findings without actionable lever)

All cells flagged below are on a CLOSED, RETIRED dataset. No operational action is possible until VOLARB is re-enabled with a new deployment.

| cell | n | EV/trade | CI95 | delta vs prior | note |
|---|---|---|---|---|---|
| ETH (asset) | 305 | −$0.035 | [−$0.301, +$0.233] | no change (Δn=0) | PF<1.0; most negative asset |
| [0.20,0.30) band | 227 | −$0.003 | [−$0.275, +$0.264] | no change | PF<1.0; flat EV |
| H01 | 66 | +$0.784 | [+$0.163, +$1.385] | no change | Best hour; CI_lo>0 but n<100 |
| H05 | 35 | −$0.861 | [−$1.406, −$0.215] | no change | Worst hour; n<40 IGNORE |
| H16 | 30 | −$0.715 | [−$1.273, −$0.054] | no change | Strong negative; n<40 IGNORE |
| [0.10,0.20) band | 91 | +$0.149 | [−$0.312, +$0.663] | no change | 1 trade from n≥100 threshold; still WATCHLIST |

---

## Skipped — User Override (state_log)

- `EDGE_FLOOR` lowered to 0.10 by explicit user instruction 2026-05-17 10:20 UTC (from 0.30 after live performance analysis). This overrides the audit spec's scalar assumption of 0.15.
- `ASK_FLOOR=0.00` (longshot band open): user instruction 2026-05-17 (from 0.10). Not a target lever in this protocol.
- `VOLARB_TP20` exit: deployed 2026-05-17 18:00 UTC; partially explains the 267 PROFIT_TARGET exits in the dataset.

---

## Context Note

The VOLARB dataset is closed and the strategy is retired. Capital is now running STWA (weather arb). The audit continues because the data-mirror still pushes `trades.jsonl` including the 885 historical VOLARB records, and the scheduled agent has not been decommissioned. If VOLARB is never re-enabled, these audits will be perpetually NO_PATCH. Consider decommissioning the VOLARB audit cron once the user confirms VOLARB is permanently retired.
