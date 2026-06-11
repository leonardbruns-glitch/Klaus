# VOLARB Quantitative Audit — 2026-06-11 06:15 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-11T05:55:16Z (19.9 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $79.60 (prior audit 2026-06-11T00:13Z: $76.95; Δ=+$3.65 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 28th consecutive audit with zero new unique trades; last trade 2026-05-19T02:50:33Z, ~22.4 days retired) |
| drift_status | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition false |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m — CLOSED DATASET) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **28th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched (state_log).
- 2026-05-19: `volarb_strategy=None`, import removed (state_log).
- 2026-05-29: CLAUDE.md fully reoriented to STWA; no crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `EDGE_FLOOR` on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10` (lines 46–47); audit-spec scalar `0.15→0.17` has no matching target in the code.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (19.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($79.60) |
| Code-drift guard | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition false |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-10T23:55Z .. 2026-06-11T05:55Z (cutoff_ts=1781135716)

**VOLARB trades in window: 0** — last trade 2026-05-19T02:50:33Z (~22 days before window start)

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
| CI95 EV/trade | [−$0.093, +$0.219] | straddles zero; below baseline CI entirely |

### Per-Asset (all n≥100; vs baseline CI [+$0.244, +$0.352])

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.174, +$0.346] | BELOW CI lower | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.292, +$0.228] | BELOW CI lower; PF<1.0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.413] | BELOW CI lower | WATCHLIST |

### Per-Hour-UTC (no hour reaches n≥100; all WATCHLIST/IGNORE)

| dimension | cell | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | +$0.784 | [+$0.181, +$1.414] | WATCHLIST — CI_lo>0; strongest positive outlier; n<100 |
| hour | H02 | 64 | 40.6 | +$0.196 | [−$0.392, +$0.808] | WATCHLIST |
| hour | H11 | 71 | 35.2 | +$0.191 | [−$0.347, +$0.751] | WATCHLIST |
| hour | H14 | 47 | 29.8 | −$0.107 | [−$0.675, +$0.512] | WATCHLIST (trending negative) |
| hour | H22 | 40 | 32.5 | −$0.137 | [−$0.776, +$0.538] | WATCHLIST |
| hour | H23 | 57 | 33.3 | +$0.004 | [−$0.569, +$0.595] | WATCHLIST |

### Per-Ask-Band

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| ask_band | [0.00, 0.10) | 10 | — | — | — | — | IGNORE n<40 |
| ask_band | [0.10, 0.20) | 91 | 18.7 | +$0.149 | [−$0.308, +$0.648] | BELOW CI lower | WATCHLIST (n=91) |
| ask_band | [0.20, 0.30) | 227 | 26.4 | −$0.003 | [−$0.276, +$0.277] | BELOW CI lower | WATCHLIST |
| ask_band | [0.30, 0.40) | 390 | 38.7 | +$0.120 | [−$0.117, +$0.352] | BELOW CI lower | WATCHLIST |
| ask_band | [0.40, 0.50) | 157 | 47.1 | +$0.085 | [−$0.282, +$0.470] | BELOW CI lower | WATCHLIST |
| ask_band | [0.50, 0.60) | 8 | 50.0 | −$0.157 | [−$1.991, +$1.690] | — | IGNORE n<40 |

---

## Lever Probes

- **ASK_CEIL probe** [0.50, 0.60): n=8 EV=−$0.157 CI=[−$1.991, +$1.690] — **NOT TRIGGERED** (n=8 < 100)
- **REM_MAX_S probe** [260, 280): n=221 EV=−$0.004 CI=[−$0.332, +$0.317] — **NOT TRIGGERED** (CI upper = +$0.317 > 0)
- **REM_MIN_S probe** [60, 80): n=8 EV=−$1.075 CI=[−$1.339, −$0.837] — **NOT TRIGGERED** (n=8 < 100; probe requires n≥100)
- **ASK_DEPTH_MULT probe**: no adverse-selection slippage evidence in trade fields; n<200 overall condition not applicable — NOT TRIGGERED

---

## Proposed Patch (capped at 1)

**NO PATCH**

### EDGE_FLOOR raise conditions evaluated (0.15 → 0.17):

| condition | required | actual | met? |
|---|---|---|---|
| n_total ≥ 200 | ≥ 200 | 885 | ✓ |
| overall EV/trade < +$0.10 | < $0.10 | +$0.062 | ✓ |
| overall PF < 1.10 | < 1.10 | 1.061 | ✓ |
| CI95 lower < 0 | < 0 | −$0.093 | ✓ |

**All four conditions are formally met. Patch is withheld for two structural reasons:**

1. **Lever inapplicable — code mismatch**: The audit spec describes `EDGE_FLOOR (current 0.15)` and the patch as `0.15 → 0.17`. The actual code (`strategy/volarb.py:46–47`) has no scalar `EDGE_FLOOR = 0.15`; it has `EDGE_FLOOR_BY_ASSET = {"BTC": 0.10, "ETH": 0.10, "SOL": 0.10}` and `EDGE_FLOOR_DEFAULT = 0.10`. The `0.15 → 0.17` surgical edit has no matching token in the code.

2. **Zero operational effect — strategy retired**: `volarb_strategy = None` since 2026-05-19 (state_log). The VPS does not import or execute `strategy/volarb.py`. Editing a dead file generates a noise PR with no trading effect.

Anti-sycophancy: overall EV is *positive* (+$0.062/trade, sum +$54.69). The deficit vs backtest CI (+$0.244) is structural model underperformance documented over 27 prior audits on an identical, closed dataset. Δ=0 new trades. No new information.

---

## Watchlist (40≤n<100 AND per-asset/per-hour findings without block lever)

Summary: 10 cells tracked (prior audit: 9; Δ=+1 — ask-band [0.10,0.20) n=91 just below action threshold). Dataset CLOSED; watchlist is archival only.

| dimension | cell | n | WR% | EV/trade | CI95 | Δ vs prior | note |
|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | +$0.083 | [−$0.174, +$0.346] | 0 | BELOW baseline CI; PF 1.085 |
| asset | ETH | 305 | 32.5 | −$0.035 | [−$0.292, +$0.228] | 0 | BELOW baseline CI; PF<1.0 — weakest asset |
| asset | SOL | 294 | 38.8 | +$0.142 | [−$0.125, +$0.413] | 0 | BELOW baseline CI; best live asset |
| hour | H01 | 66 | 48.5 | +$0.784 | [+$0.181, +$1.414] | 0 | POSITIVE outlier — CI_lo>0; only cell clearly beating baseline |
| hour | H02 | 64 | 40.6 | +$0.196 | [−$0.392, +$0.808] | 0 | above-average WR |
| hour | H11 | 71 | 35.2 | +$0.191 | [−$0.347, +$0.751] | 0 | flat, wide CI |
| hour | H14 | 47 | 29.8 | −$0.107 | [−$0.675, +$0.512] | 0 | below-average WR; trending negative |
| hour | H22 | 40 | 32.5 | −$0.137 | [−$0.776, +$0.538] | 0 | below-average WR |
| hour | H23 | 57 | 33.3 | +$0.004 | [−$0.569, +$0.595] | 0 | flat |
| ask_band | [0.10, 0.20) | 91 | 18.7 | +$0.149 | [−$0.308, +$0.648] | new | n approaching 100; low WR, positive EV from longshot payoffs |

---

## Skipped — User Override (state_log)

None — no VOLARB cells were user-unblocked in state_log.

---

*Note: Watchlist Δ=0 across all existing cells because the dataset is closed (VOLARB retired 2026-05-19; no new entries can ever arrive). Entries preserved for archival continuity only.*
