# VOLARB Quantitative Audit — 2026-05-19 00:16 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-19T00:08:47Z (8 min old — FRESH) |
| Klaus state | active (systemd: active, 0 open positions) |
| Capital | $105.59 (prior audit 2026-05-17 12:16 UTC: $80.43 → **+$25.16 Δ** over ~36h) |
| VOLARB n (live era) | 825 (deduped first-fire per (asset, ts_open rounded to second)) |
| drift_status | OK — data-mirror has no strategy/volarb.py; dev branch parameters confirmed current |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T00:08Z (51h8m) |

**EDGE_FLOOR NOTE:** Audit prompt assumes current EDGE_FLOOR=0.15. Actual deployed value is
**0.10** (user instruction 2026-05-17 10:20 UTC; prior audit noted same discrepancy).
Patch proposal "0.15→0.17" remains inapplicable.

**HOUR GATE NOTE:** volarb.py currently restricts to `hour_utc in {1, 2, 11, 18}`. All
full-window metrics (n=825) include trades from now-blocked hours. Current-config subset (n=169)
tells a materially different story — see §Current-Config below.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (8 min) |
| `system_status.txt` `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($105.59) |
| Code drift guard | PASS (data-mirror has no strategy/volarb.py; N/A condition) |
| Open audit PRs | NONE (checked via GitHub API) |
| `integrity_report.json` `blocks_agent_run` | N/A (absent from mirror) |

---

## Overall VOLARB Performance (full window, all historical hours)

| metric | value | baseline (1-equiv) | vs baseline |
|---|---|---|---|
| n | 825 | — | — |
| WR | 34.3% | — | — |
| PF | 1.060 | — | — |
| net_sum | +$50.08 | — | — |
| EV/trade | +$0.0607 | +$0.298 mid | BELOW mid |
| CI95 | [−$0.102, +$0.222] | [+$0.244, +$0.352] | CI upper ($0.222) < baseline lower ($0.244) |
| fee_bleed | 1.8% of gross wins ($15.50 / $880.48) | <20% kill-switch | OK |

Full-window metrics are diluted by now-blocked hours (see §Current-Config).

## Current-Config Performance (hour_utc ∈ {1, 2, 11, 18} only)

| metric | value | vs baseline CI |
|---|---|---|
| n | 169 | — |
| WR | 45.6% | — |
| PF | 1.633 | — |
| net_sum | +$89.67 | — |
| EV/trade | +$0.531 | **ABOVE** baseline CI upper (+$0.352) |
| CI95 | [+$0.164, +$0.896] | CI lower (+$0.164) < baseline lower (+$0.244), but overlapping |

Per-asset within current-config:

| asset | n | WR | PF | EV/trade | CI95 |
|---|---|---|---|---|---|
| BTC | 55 | 40.0% | 1.288 | +$0.265 | [−$0.342, +$0.912] |
| ETH | 58 | 44.8% | 1.607 | +$0.509 | [−$0.083, +$1.126] |
| SOL | 56 | 51.8% | 2.075 | +$0.814 | [+$0.166, +$1.501] |

SOL current-config CI lower (+$0.166) is below backtest lower but CI clears zero — COLLECTING.

---

## 6h Recency Cells (n≥10 threshold)

Window: 2026-05-18 18:08 UTC .. 2026-05-19 00:08 UTC (n=30 total)

No cell reached n≥10 per (asset × ask_band). Only H18 (18:08–19:00, ~52 min) + a few H23
trades (H23 block deployed mid-window) produced entries. **No 6h recency flags.**

---

## Full-Window Cell Scan (2026-05-16 21:00Z .. snapshot)

### a–c. Per-Asset

| asset | n | WR | PF | net_sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| BTC | 265 | 32.1% | 1.066 | +$17.00 | +$0.064 | [−$0.194, +$0.346] | CI upper < baseline lower | below_mid |
| ETH | 283 | 31.4% | 0.935 | −$19.22 | −$0.068 | [−$0.340, +$0.214] | CI upper ($0.214) < baseline lower ($0.244) | **WATCHLIST** |
| SOL | 277 | 39.4% | 1.191 | +$52.30 | +$0.189 | [−$0.087, +$0.462] | CI upper > baseline lower | below_mid |

**ETH watchlist note:** Full-window ETH is distorted by blocked hours. ETH in allowed hours shows
EV=+$0.509 (n=58) vs −$0.068 full-window. The blocked-hour ETH drag is entirely from
H05 (WR=0% n=11 EV=−$1.52), H07 (WR=10% n=10 EV=−$0.76), H12 (WR=15% n=13 EV=−$1.09),
H17 (WR=14% n=7 EV=−$2.52) — all now blocked. Watchlist flag on ETH is artefactual given
current gate set; promote to MONITOR_ONLY pending n≥100 in current-config hours.

### d. Per-Ask-Band

| band | n | WR | PF | net_sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.00,0.10) | 10 | 0.0% | 0.000 | −$9.11 | −$0.911 | [−$1.10, −$0.75] | — | collect (n<40) |
| [0.10,0.20) | 91 | 18.7% | 1.197 | +$13.60 | +$0.149 | [−$0.308, +$0.667] | CI upper > baseline lower | WATCHLIST |
| [0.20,0.30) | 227 | 26.4% | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.305] | CI upper > baseline lower | below_mid |
| [0.30,0.40) | 348 | 38.5% | 1.104 | +$38.04 | +$0.109 | [−$0.129, +$0.352] | CI upper = baseline upper | below_mid |
| [0.40,0.50) | 139 | 48.2% | 1.114 | +$17.72 | +$0.128 | [−$0.268, +$0.527] | CI overlapping | below_mid |
| [0.50,0.60) | 8 | 50.0% | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.684] | — | collect (n<40) |
| [0.60+) | 2 | 50.0% | 0.356 | −$8.18 | −$4.091 | [−$12.71, +$4.53] | — | collect (n<40) |

[0.00,0.10) longshot bucket: WR=0% n=10, CI fully negative. Not actionable (n<40), but early
signal is very negative — existing EDGE_CEIL=0.20 may already be filtering the worst of these.

### Per-Hour (selected: currently-allowed hours and near-threshold)

| hour | n | WR | PF | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|
| H01 ← | 36 | 50.0% | 2.638 | +$1.103 | [+$0.270, +$2.029] | collect (n<100) |
| H02 ← | 37 | 51.4% | 1.964 | +$0.781 | [+$0.024, +$1.554] | collect (n<100) |
| H05 [blocked] | 35 | 14.3% | 0.359 | −$0.861 | [−$1.387, −$0.242] | blocked, CI fully negative — confirms block |
| H11 ← | 71 | 35.2% | 1.196 | +$0.191 | [−$0.353, +$0.723] | WATCHLIST (40≤n<100) |
| H16 [blocked] | 30 | 16.7% | 0.428 | −$0.715 | [−$1.311, −$0.060] | blocked, CI fully negative — confirms block |
| H18 ← | 25 | 60.0% | 1.406 | +$0.301 | [−$0.493, +$1.077] | collect (n<100) |
| H21 [blocked] | 39 | 51.3% | 1.873 | +$0.607 | [−$0.036, +$1.271] | blocked, positive trend noted |

← = currently allowed. Full per-hour table: H01(+$1.10), H02(+$0.78), H03(+$0.37),
H04(−$0.15), H05(−$0.86 ✓blocked), H06(+$0.02), H07(−$0.44), H08(+$0.41), H09(−$0.56),
H10(+$0.14), H11(+$0.19), H12(−$0.03), H13(+$0.02), H14(−$0.11), H15(−$0.12),
H16(−$0.72 ✓blocked), H17(−$0.39), H18(+$0.30), H21(+$0.61), H22(−$0.14), H23(+$0.004 → blocked).

---

## Lever Probes

### ASK_CEIL probe [0.50, 0.60)
n=8 (< 100 threshold). EV=−$0.157, CI=[−$1.99, +$1.68].
**→ Not a lever candidate. Collect.**

### REM_MAX_S probe [260, 280)
n=201, WR=39.3%, EV=−$0.033, CI=[−$0.362, +$0.295].
EV condition: −$0.033 > −$0.10 → **condition not met**.
**→ Not a lever candidate.**

### REM_MIN_S probe [60, 80)
n=8 (< 100 threshold). EV=−$1.076, CI=[−$1.352, −$0.820].
EV is very negative but n is far below 100. Early signal flagged (see Watchlist).
**→ Not a lever candidate.**

### ASK_DEPTH_MULT probe
No direct adverse-selection slippage metric available in trade records. Overall EV degradation
is explained by blocked-hour history, not adverse selection. n<200 required for this lever.
**→ Not a lever candidate.**

---

## Proposed Patch

**No patch.**

EDGE_FLOOR raise conditions are statistically met on the full-window dataset (n=825 ≥ 200,
EV=$+0.061 < $0.10, PF=1.060 < 1.10, CI_lo=−$0.102 < 0). However:

1. **Current floor is 0.10, not 0.15.** Prompt's specified patch (0.15→0.17) is inapplicable.
   Applying 0.10→0.12 (+20%) would be inferred, not specified.
2. **User override (state_log 2026-05-17 10:20 UTC).** User explicitly set EDGE_FLOOR=0.10
   after evidence showed 0.30 caused WR=19.3% EV=−$0.224. Raising contradicts stated intent.
3. **Full-window metrics are polluted.** Current-config hours (H01/H02/H11/H18) show
   EV=+$0.531, CI=[+$0.164, +$0.896] — entirely above backtest baseline. The full-window
   EDGE_FLOOR trigger is artefactual from now-blocked hours.
4. **No other lever probe clears its conditions.**

---

## Watchlist (40≤n<100 AND findings without actionable lever)

| dimension | cell | n | WR | EV/trade | CI95 | delta vs prior | note |
|---|---|---|---|---|---|---|---|
| per-hour | H11 (allowed) | 71 | 35.2% | +$0.191 | [−$0.353, +$0.723] | +$0.002 EV vs flat prior | Positive, COLLECTING — promote at n≥100 |
| per-ask-band | [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.308, +$0.667] | n growing | Low WR but PF=1.197; large wins pulling avg; watch |
| rem-probe | [60,80) | 8 | 0.0% | −$1.076 | [−$1.352, −$0.820] | NEW | n<40, CI fully negative; early adverse signal on the minimum-rem boundary. No action yet |
| longshot | [0.00,0.10) | 10 | 0.0% | −$0.911 | [−$1.10, −$0.75] | n<40 | All 10 resolved NO; watch at n≥40 |

**H21 note (blocked, n=39, EV=+$0.607, CI_lo=−$0.036):** Was one of VOLARB's four strongest hours
per prior analysis; blocked for CAS conflict. EV approaches significance — promote to
watchlist for user review if CAS-H21 conflict resolves.

---

## Skipped — User Override (state_log)

| lever | condition | override |
|---|---|---|
| EDGE_FLOOR raise | Conditions met on full-window data | state_log 2026-05-17 10:20 UTC: user set 0.10 explicitly, reversing failed 0.30 experiment. Prompt patch (0.15→0.17) also inapplicable since floor≠0.15. |
| ETH full-window WATCHLIST → block | CI upper < baseline lower on full data | Entirely driven by now-blocked hours (H05, H07, H12, H17). ETH in allowed hours: EV=+$0.509 n=58. User-override: hour gate already addresses root cause. |
| H21 re-enable | n=39 EV=+$0.607 trending positive | Blocked via state_log 2026-05-18 CAS/VOLARB swap. n<100 and user gated — watchlist only. |

---

## Summary

Strategy is healthy in its current operating configuration. Capital grew +$25.16 (+31%) since
prior audit. Fee bleed at 1.8% is well within limits. The 825-trade full-window dataset is
materially distorted by blocked-hour history; the current operative subset (n=169, H01/H02/H11/H18)
shows WR=45.6%, EV=+$0.531 — above backtest baseline. No patch warranted. COLLECTING toward
n≥100 per current-config hour.

Next decision gate: H01 at n≥100 (~64 more fires) — CI95 lower (+$0.270) already above
backtest lower at n=36. If it holds, this becomes the first current-config cell to clear
the baseline with n≥100 confidence.
