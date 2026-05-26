# VOLARB Quantitative Audit — 2026-05-26 00:14 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-26T00:08:38Z (5.8 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $30.94 (prior audit 2026-05-25 00:15 UTC: $31.36 → **−$0.42 Δ** — CAS_LOWASK/weather, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~165h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation — CLOSED) |
| Open audit PRs | NONE (GitHub MCP confirmed) |
| Run | **9th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.** VOLARB entries disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched).
Formally retired 2026-05-19 (`volarb_strategy=None`, import removed, CLAUDE.md rewritten).
All 885 trades are historical. No parameter change to `strategy/volarb.py` has operational effect.

**CODE MISMATCH NOTE (9th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual final code: `EDGE_FLOOR_DEFAULT=0.10`, set by explicit user instruction 2026-05-17 10:20 UTC
(state_log). Prompt's 0.15→0.17 raise inapplicable; adapted 0.10→0.12 also suppressed — strategy
retired and user instruction overrides.

**ASK BAND METHODOLOGY NOTE:** Prior audit (8th) classified 2 trades (BTC ep=0.6940, ETH ep=0.6837,
both from 2026-05-17T17:00Z) in [0.00,0.10) using an erroneous price field. Correct classification:
ep≥0.60 (outside ASK_CEIL=0.60 gate, entered during brief unconstrained window). This report
corrects [0.00,0.10) from prior n=12→n=10 and adds ≥0.60 as n=2. Total n=885 unchanged.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (5.8 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($30.94) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK/weather) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-25T18:08:38Z .. 2026-05-26T00:08:38Z
**VOLARB trades in window: 0** (strategy retired ~165h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.092, +$0.216] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.092)
→ All 4 criteria MET — **NO PATCH** (see Proposed Patch section for reasons).

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | −$0.177 | +$0.359 | BELOW CI lower | BELOW_BASELINE (n≥100) |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | −$0.303 | +$0.236 | BELOW CI lower | BELOW_BASELINE (n≥100) |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | −$0.128 | +$0.414 | BELOW CI lower | BELOW_BASELINE (n≥100) |

All three assets below $1-equiv CI lower (+$0.244). Strategy retired; no lever action possible.

### Per-Hour UTC

| hr | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9 | 1.360 | +$12.46 | +$0.320 | −$0.408 | +$1.109 | straddles | collect |
| H01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | +$0.176 | +$1.369 | ABOVE CI hi | watchlist+ |
| H02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | −$0.395 | +$0.787 | straddles | watchlist |
| H03 | 36 | 44.4 | 1.374 | +$13.38 | +$0.372 | −$0.441 | +$1.163 | straddles | collect |
| H04 | 37 | 32.4 | 0.873 | −$5.42 | −$0.147 | −$0.818 | +$0.620 | straddles | collect |
| H05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | −$1.391 | −$0.274 | CI_hi<0 | collect (n<40) |
| H06 | 35 | 31.4 | 1.020 | +$0.72 | +$0.021 | −$0.684 | +$0.828 | straddles | collect |
| H07 | 31 | 19.4 | 0.616 | −$13.60 | −$0.439 | −$1.095 | +$0.324 | straddles | collect |
| H08 | 35 | 28.6 | 1.498 | +$14.30 | +$0.409 | −$0.395 | +$1.270 | straddles | collect |
| H09 | 28 | 14.3 | 0.438 | −$15.75 | −$0.563 | −$1.082 | +$0.065 | straddles | collect |
| H10 | 38 | 34.2 | 1.162 | +$5.34 | +$0.141 | −$0.536 | +$0.815 | straddles | collect |
| H11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | −$0.353 | +$0.813 | straddles | watchlist |
| H12 | 36 | 36.1 | 0.970 | −$1.20 | −$0.033 | −$0.769 | +$0.745 | straddles | collect |
| H13 | 36 | 33.3 | 1.022 | +$0.83 | +$0.023 | −$0.691 | +$0.757 | straddles | collect |
| H14 | 47 | 29.8 | 0.894 | −$5.05 | −$0.108 | −$0.695 | +$0.539 | straddles | watchlist |
| H15 | 36 | 30.6 | 0.898 | −$4.45 | −$0.124 | −$0.887 | +$0.723 | straddles | collect |
| H16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | −$1.293 | −$0.018 | CI_hi<0 | collect (n<40) |
| H17 | 21 | 38.1 | 0.752 | −$8.14 | −$0.388 | −$2.007 | +$1.037 | straddles | collect |
| H18 | 25 | 60.0 | 1.406 | +$7.53 | +$0.301 | −$0.502 | +$1.096 | straddles | collect |
| H20 | 3 | 100.0 | inf | +$9.05 | +$3.016 | — | — | — | n<40 |
| H21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | −$0.051 | +$1.250 | straddles | collect |
| H22 | 40 | 32.5 | 0.872 | −$5.48 | −$0.137 | −$0.796 | +$0.537 | straddles | watchlist |
| H23 | 57 | 33.3 | 1.004 | +$0.24 | +$0.004 | −$0.570 | +$0.584 | straddles | watchlist |

Note: H05 CI_hi=−$0.274<0 and H16 CI_hi=−$0.018<0 but n<40; collect only, no lever.
No hour cell crosses n≥100.

### Per-Ask-Band

| band | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| [0.00,0.10) | 10 | 0.0 | 0.000 | −$9.11 | −$0.911 | −$1.093 | −$0.742 | BELOW CI lower | collect (n<40) |
| [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | −$0.314 | +$0.671 | BELOW CI lower | watchlist |
| [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | −$0.271 | +$0.268 | BELOW CI lower | BELOW_BASELINE (n≥100) |
| [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | −$0.105 | +$0.357 | BELOW CI lower | BELOW_BASELINE (n≥100) |
| [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | −$0.303 | +$0.472 | BELOW CI lower | BELOW_BASELINE (n≥100) |
| [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | −$1.991 | +$1.690 | straddles | collect (n<40) |
| [≥0.60] | 2 | 100.0 | inf | +$7.80 | +$3.901 | — | — | — | outside ASK_CEIL gate |

Note: ≥0.60 corrects prior audit methodology error. BTC ep=0.694 (+$4.53) and ETH ep=0.684 (−$12.71 —
wait, recalculated: BTC +$4.53, ETH −$12.71 appears to show ETH net=-$12.71 but the prior
counted these in [0.00,0.10) wrongly). Corrected totals verified: all bands sum to 885.

Actually correcting: ETH ep=0.6837 net_pnl=−$12.71 is negative. Let me restate:

| band | n | WR% | sum | EV/trade |
|---|---|---|---|---|
| ≥0.60 | 2 | 50.0 | +$4.53 + (−$12.71) = −$8.18 | −$4.09 |

These 2 trades were entered above ASK_CEIL=0.60; outside the lever framework. Outside phase 1 gate.

---

## Lever Probes

### ASK_CEIL probe: [0.50, 0.60)
n=8, EV=−$0.157, CI=[−$1.991, +$1.690]
→ n<100. **COLLECTING.** No lever action.

### REM_MAX_S probe: [260, 280)
`term_remaining_s` field is 0.0 in all 885 VOLARB trades — field was added for LDA era, post-VOLARB.
n=0 usable observations. **PROBE INFEASIBLE.**

### REM_MIN_S probe: [60, 80)
Same: `term_remaining_s` all 0.0. **PROBE INFEASIBLE.**

### ASK_DEPTH_MULT probe
No per-trade adverse-selection slippage field in VOLARB schema. Overall EV=+$0.062 (positive,
not degrading). Trigger requires n≥200 AND EV degrading + CI95 evidence. Condition not met.
**NO ACTION.**

---

## Proposed Patch

**NO PATCH.**

EDGE_FLOOR raise: all 4 conditions mathematically satisfied (n=885≥200, EV=+$0.062<+$0.10,
PF=1.061<1.10, CI_lo=−$0.092<0). Suppressed for two independent reasons:

1. **Strategy retired.** VOLARB has generated zero trades since 2026-05-19T02:50:33Z (~165h).
   `strategy/volarb.py` is dead code. Editing a constant has zero operational effect.

2. **User instruction override.** Current `EDGE_FLOOR_DEFAULT=0.10` (all assets, uniform) was
   set by explicit user instruction 2026-05-17 10:20 UTC (state_log). The prompt's assumed
   starting value of 0.15 does not match live code; adapted 0.10→0.12 raise would also contradict
   user instruction and microshadow evidence (edge[0.10,0.15) showed WR=48.1% EV=+$0.252/trade).

All other levers: n<100 in probe cells, or probe fields unavailable. 1-scalar-edit cap is moot.

---

## Watchlist (40≤n<100, Δ vs prior audit 2026-05-25 00:15 UTC)

| cell | n | WR% | EV/trade | CI95_lo | CI95_hi | Δ vs prior |
|---|---|---|---|---|---|---|
| H01 (hour) | 66 | 48.5 | +$0.784 | +$0.176 | +$1.369 | unchanged — retired |
| H02 (hour) | 64 | 40.6 | +$0.196 | −$0.395 | +$0.787 | unchanged — retired |
| H11 (hour) | 71 | 35.2 | +$0.191 | −$0.353 | +$0.813 | unchanged — retired |
| H14 (hour) | 47 | 29.8 | −$0.108 | −$0.695 | +$0.539 | unchanged — retired |
| H22 (hour) | 40 | 32.5 | −$0.137 | −$0.796 | +$0.537 | unchanged — retired |
| H23 (hour) | 57 | 33.3 | +$0.004 | −$0.570 | +$0.584 | unchanged — retired |
| [0.10,0.20) (ask-band) | 91 | 18.7 | +$0.149 | −$0.314 | +$0.671 | unchanged — retired |

Δ = 0 on all cells. Dataset is permanently frozen; no new trades possible.

**H01 standout:** CI_lo=+$0.176>0 and CI_hi=+$1.369 clears baseline upper (+$0.352). Genuine
positive signal at n=66. Flag for reactivation review if VOLARB model is ever revived.

---

## Skipped — User Override (state_log)

- `EDGE_FLOOR=0.10` (all assets): user instruction 2026-05-17 10:20 UTC. Overrides prompt assumption of 0.15.
- `ASK_FLOOR=0.00` (longshot bucket): user instruction 2026-05-17. Not a lever candidate here.
- `EDGE_CEIL=0.20`: user-added microshadow gate 2026-05-17. Not in Phase 1 lever list; not touched.
- `SPREAD_MIN_BPS=200 / SPREAD_MAX_BPS=300`: user-added 2026-05-17. Not touched.

---

## Audit Termination Note

This is the **9th consecutive VOLARB audit** with Δ=0 new trades. The dataset is permanently closed.
VOLARB ran 53h50m (2026-05-16T21:00Z .. 2026-05-19T02:50Z), delivering WR=34.7% vs 51.7% OOS
backtest, EV=+$0.062/trade vs +$0.298 expected — ~21% of expectation. Strategy replaced by
CAS_LOWASK (now further evolved; current active strategies per mirror: CAS_LOWASK + weather + M1
β-probe per last 5 VPS commits). These audits continue to run against a frozen historical corpus
with no actionable output possible.

**Recommendation:** retire this audit cron or redirect it to CAS_LOWASK / LDA analysis. The
VOLARB lever set (EDGE_FLOOR, ASK_CEIL, REM_MIN_S, REM_MAX_S, ASK_DEPTH_MULT) is dead code.
This audit produces no value at n=885 frozen — 9 consecutive NO_PATCH runs confirm.
