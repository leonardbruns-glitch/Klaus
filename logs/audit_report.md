# VOLARB Quantitative Audit — 2026-05-27 00:14 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-27T00:10:04Z (4.3 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $29.03 (prior audit 2026-05-26 00:14 UTC: $30.94 → **−$1.91 Δ** — CAS_LOWASK/weather, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~189h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation — CLOSED) |
| Open audit PRs | NONE |
| Run | **10th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.** VOLARB entries disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched).
Formally retired 2026-05-19 (`volarb_strategy=None`, import removed, CLAUDE.md rewritten).
All 885 trades are historical. No parameter change to `strategy/volarb.py` has operational effect.

**CODE MISMATCH NOTE (10th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual final code: `EDGE_FLOOR_DEFAULT=0.10`, set by explicit user instruction 2026-05-17 10:20 UTC
(state_log). Prompt's 0.15→0.17 raise inapplicable; adapted 0.10→0.12 also suppressed — strategy
retired and user instruction overrides.

**REM FIELD NOTE:** `term_remaining_s` is 0.0 for all 885 VOLARB trades — field was not populated in
the VOLARB era (added in TERMINAL era). REM_MAX_S and REM_MIN_S lever probes have n=0; no data.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (4.3 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($29.03) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK/weather) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-26T18:10:04Z .. 2026-05-27T00:10:04Z
**VOLARB trades in window: 0** (strategy retired ~189h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | — |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (post first-fire dedup per `(asset, round(ts_open))`) — unchanged since audit #2.
Baseline $1-equiv CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.084, +$0.210] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.084)
→ All 4 criteria MET — **NO PATCH** (see Proposed Patch section for reasons).

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.08 | +$23.74 | +$0.083 | [−$0.180, +$0.341] | BELOW_EV | watchlist |
| asset | ETH | 305 | 32.5% | 0.97 | −$10.78 | −$0.035 | [−$0.302, +$0.252] | BELOW_CI★ | watchlist |
| asset | SOL | 294 | 38.8% | 1.14 | +$41.74 | +$0.142 | [−$0.127, +$0.415] | BELOW_EV | watchlist |

No asset reaches n≥100 AND CI_hi<baseline_CI_lo threshold for watchlist→lever promotion; all CI upper bounds exceed +$0.244.

### Per-Hour-UTC (watchlist range 40≤n<100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5% | 1.95 | +$51.76 | +$0.784 | [+$0.163, +$1.422] | ABOVE CI | OK |
| hour | H02 | 64 | 40.6% | 1.18 | +$12.56 | +$0.196 | [−$0.376, +$0.803] | BELOW_EV | watchlist |
| hour | H11 | 71 | 35.2% | 1.20 | +$13.53 | +$0.191 | [−$0.340, +$0.764] | BELOW_EV | watchlist |
| hour | H14 | 47 | 29.8% | 0.89 | −$5.05 | −$0.108 | [−$0.711, +$0.505] | BELOW_EV | watchlist |
| hour | H22 | 40 | 32.5% | 0.87 | −$5.49 | −$0.137 | [−$0.798, +$0.588] | BELOW_EV | watchlist |
| hour | H23 | 57 | 33.3% | 1.00 | +$0.24 | +$0.004 | [−$0.562, +$0.587] | BELOW_EV | watchlist |

No hour reaches n≥100 (dataset CLOSED at 885 total; per-hour max is H11 n=71).

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| band | [0.00,0.10) | 10 | 0.0% | 0.00 | −$9.11 | −$0.911 | [−$1.101, −$0.750] | n<40 | ignore |
| band | [0.10,0.20) | 91 | 18.7% | 1.20 | +$13.60 | +$0.149 | [−$0.302, +$0.627] | BELOW_EV | watchlist |
| band | [0.20,0.30) | 227 | 26.4% | 1.00 | −$0.73 | −$0.003 | [−$0.285, +$0.267] | BELOW_EV | n≥100 |
| band | [0.30,0.40) | 390 | 38.7% | 1.11 | +$46.99 | +$0.121 | [−$0.119, +$0.362] | BELOW_EV | n≥100 |
| band | [0.40,0.50) | 157 | 47.1% | 1.07 | +$13.38 | +$0.085 | [−$0.315, +$0.446] | BELOW_EV | n≥100 |
| band | [0.50,0.60) | 8 | 50.0% | 0.88 | −$1.25 | −$0.157 | [−$1.991, +$1.703] | n<40 | ignore |

All n≥100 bands have CI upper bounds overlapping or exceeding +$0.244; no band reaches BELOW_CI★.

---

## Lever Probes

- **ASK_CEIL [0.50,0.60):** n=8 EV=−$0.157 CI=[−$1.991, +$1.703] → **collecting** (n<100; threshold not met)
- **REM_MAX_S [260,280):** n=0 → **no data** (`term_remaining_s`=0.0 for all VOLARB trades; field unpopulated in VOLARB era)
- **REM_MIN_S [60,80):** n=0 → **no data** (same; rem field unpopulated)
- **ASK_DEPTH_MULT:** no adverse-selection slippage metric available; not evaluated

---

## Proposed Patch (capped at 1)

**NO PATCH.**

Mechanical EDGE_FLOOR raise criteria are ALL MET:
- n=885 ≥ 200 ✓
- EV=+$0.062 < +$0.10 ✓
- PF=1.061 < 1.10 ✓
- CI_lo=−$0.084 < 0 ✓

Suppressed for three independent reasons, any one of which is sufficient:

1. **Strategy retired.** VOLARB was disabled 2026-05-17 19:56 UTC and formally removed 2026-05-19.
   `strategy/volarb.py` is absent from the VPS data-mirror. Editing dead code creates noise, not signal.

2. **Evidence not decisive.** CI95=[−$0.084, +$0.210] straddles zero. The strategy produced
   positive net PnL (+$54.69) and positive EV. Underperformance is *relative to backtest baseline*,
   not absolute. "IFF evidence is decisive" — it is not.

3. **User instruction override.** EDGE_FLOOR was explicitly lowered to 0.10 by user on 2026-05-17
   10:20 UTC (state_log) after live model showed r≈0 predictive power. Raising it back overrides
   the last explicit user instruction without new evidence (dataset is frozen; no new VOLARB data
   will arrive).

This is the 10th consecutive NO_PATCH verdict on a frozen n=885 dataset.

---

## Watchlist (40≤n<100, EV below baseline CI lower +$0.244)

*Unchanged from prior 9 audits — dataset is closed.*

| dim | cell | n | WR | EV/trade | CI95 | Δ vs prior |
|---|---|---|---|---|---|---|
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.798, +$0.588] | unchanged |
| hour | H14 | 47 | 29.8% | −$0.108 | [−$0.711, +$0.505] | unchanged |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.562, +$0.587] | unchanged |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.340, +$0.764] | unchanged |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.376, +$0.803] | unchanged |
| band | [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.302, +$0.627] | unchanged |

All cells also had n<100 in prior audits; no promotions to lever candidates possible (dataset CLOSED).

---

## Skipped — User Override (state_log)

- **EDGE_FLOOR raise** suppressed: user instruction 2026-05-17 10:20 UTC lowered to 0.10; strategy retired.
- **Per-asset/per-hour blocks** not introduced: no lever exists in Phase 1; goes to watchlist only per audit rules.

---

## Termination Recommendation

**This audit series has run 10 consecutive sessions on a frozen, closed dataset (last VOLARB trade
2026-05-19 02:50 UTC). No new information is possible. Continuing to schedule this audit produces
no value. Recommend: cancel the VOLARB Auditor scheduled task, or redirect it to the active
strategy (CAS_LOWASK). Signal this to the user.**
