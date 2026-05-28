# VOLARB Alpha Scout — 2026-05-28T00:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-28T00:39:14Z (~3 min old — FRESH) |
| Klaus state | active (last live trade: SNIPER 2026-05-27T00:28Z) |
| Klaus HEAD | ad0bf61d |
| Capital | $95.304 (bankroll.json, saved_ts 2026-05-27T11:25:51Z) |
| VOLARB n (live era, bond_entry_class=='VOLARB', is_live=True, ts_open ≥ 1778965200) | **887 — FROZEN 8.9 days** |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~3 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as **PASS** (consistent with prior cycles)
- Last Scout commit: prior cycle 2026-05-27T12:42Z (~12h ago, >8h threshold) — **PROCEED**
- CODE_DESYNC: VOLARB retired (last trade 2026-05-19T02:50Z); LDA is now active strategy — **N/A for VOLARB post-mortem**

**VOLARB STATUS: PERMANENTLY RETIRED. Terminal closure cycle confirmed.**
Strategy last fired 2026-05-19T02:50Z. n=887 frozen; zero delta across all cells vs prior scout (12h ago).

**Aggregate VOLARB ($1-equiv, kline_pnl, net_pnl>0 WR):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (net_pnl>0) | 34.6% (307/887) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| 12h delta n | 0 | frozen |
| Days since last trade | 8.9 | — |

---

## Continuity vs Prior Scout (2026-05-27T12:42Z, ~12h ago)

**Investigations carried forward (all zero-delta confirmed this cycle):**
- H5 (seconds-to-resolution): Prior DISCARD. Re-confirmed: [220-280)s n=609 kEV=−$0.042, [60-100)s n=14 kEV=−$1.061. Dataset frozen — **CONFIRMED CLOSED**
- H6 (direction asymmetry): Prior DISCARD. Re-confirmed: 'up' kEV=−$0.029, 'down' kEV=−$0.019, both BELOW_CI. Dataset frozen — **CONFIRMED CLOSED**
- H4 (longshot Phase 2): Prior MOOT. Re-confirmed: `volarb_longshot_shadow` absent from shadow_summary.json. Recorder was never deployed; strategy retired. — **CONFIRMED MOOT**

**Promoted to this cycle (full tables not shown in prior):**
- H1 (per-asset): Prior carried-forward summary only. Full table provided below.
- H3 (per-ask-band): Prior carried-forward summary only. Full table provided below.
- H7 (watchlist trajectories): Re-confirmed zero-delta; SOL data resolved (was truncated in prior).

---

## Investigation H1 — Per-Asset Alpha Re-Allocation

**HYPOTHESIS:** Backtest projected BTC as the dominant alpha asset (+$14.81 projected lead at $5 stake). Live data may confirm or contradict this ranking; per-asset kEV divergence informs whether global EDGE_FLOOR raise would disproportionately affect one asset.

**METHOD:** Slice VOLARB live rows (n=887, kline_pnl available=876) by `asset`. Compute n, kn, WR (net_pnl>0), kEV/$1-equiv = kline_pnl/stake, CI95 (normal approximation), vs_baseline_CI=[+$0.244, +$0.352]. Compare to prior scout summary for delta check.

**RESULT:**

| Asset | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | 12h Δn |
|---|---|---|---|---|---|---|---|---|
| BTC | 286 | 283 | 32.9% | +$0.039 | −$0.159 | +$0.237 | **BELOW_CI** | 0 |
| ETH | 305 | 301 | 32.5% | −$0.075 | −$0.245 | +$0.095 | **BELOW_CI** | 0 |
| SOL | 296 | 292 | 38.5% | −$0.030 | −$0.202 | +$0.142 | **BELOW_CI** | 0 |

**Notes:**
- All three assets meet n≥100 for flagging. All have CI_hi below baseline lower (+$0.244): BTC CI_hi=+$0.237, ETH CI_hi=+$0.095, SOL CI_hi=+$0.142.
- **BTC is the best-performing asset** (kEV=+$0.039), consistent with backtest ranking, but CI_hi=+$0.237 is still just below the +$0.244 baseline floor.
- ETH is worst (kEV=−$0.075), inverting the backtest +$2.53 expectation.
- SOL showed best WR% (38.5%) but negative kEV due to fee + slippage erosion at ~38¢ average entry.
- Per-asset block lever does not exist in VOLARB; the only actionable response would have been raising EDGE_FLOOR globally — now moot.

**CONCLUSION: DISCARD (terminal re-confirm).** All 3 assets BELOW_CI at n≥100. Dataset frozen; results will not change.

**FAILURE_MET:** Yes — all three assets at n≥100 fall below CI lower (+$0.244). EDGE_FLOOR=0.15 was insufficient to screen negative-EV entries for any asset in live conditions.

**IF_DEPLOYED:** N/A — strategy retired. Counterfactual: raising EDGE_FLOOR from 0.15 to ~0.40+ would have reduced n substantially but still may not have rescued EV; all ask-band cells (H3) were also BELOW_CI.

---

## Investigation H3 — Per-Ask-Band EV vs Backtest Shape

**HYPOTHESIS:** Backtest assumed uniform positive EV across ASK_FLOOR=0.10 to ASK_CEIL=0.60. Live data may reveal band-specific divergence. Low-ask bands (near 0.10) have fee advantages; high-ask bands (near 0.60) carry heavier fee burden. If a specific band shows positive kEV, a tighter ask gate could rescue EV.

**METHOD:** Slice VOLARB live rows by `entry_price` band. Compute n, kn, WR, kEV/$1-equiv, CI95, vs_baseline_CI. Flag bands at n≥100 below CI lower as candidates for exclusion gate.

**RESULT:**

| Ask Band | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | Decision |
|---|---|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 91 | 18.7% | +$0.032 | −$0.480 | +$0.544 | STRADDLES_CI | n<100 → **INCONCLUSIVE** |
| [0.20, 0.30) | 227 | 227 | 26.4% | −$0.053 | −$0.273 | +$0.166 | **BELOW_CI** | n≥100, flagged |
| [0.30, 0.40) | 390 | 382 | 38.7% | +$0.010 | −$0.128 | +$0.147 | **BELOW_CI** | n≥100, flagged (bulk) |
| [0.40, 0.50) | 158 | 156 | 46.8% | −$0.007 | −$0.189 | +$0.175 | **BELOW_CI** | n≥100, flagged |
| [0.50, 0.60) | 9 | 8 | 44.4% | −$0.282 | −$0.974 | +$0.410 | STRADDLES_CI | n<100 → **INCONCLUSIVE** |

**Notes:**
- **[0.30,0.40) is the dominant band** (n=390, 44% of all entries), kEV=+$0.010. Despite best WR%, CI_hi=+$0.147 is still well below baseline lower (+$0.244).
- **[0.40,0.50)** highest WR% (46.8%) but kEV=−$0.007. At 40–50¢ entry, fees + slippage dominate.
- **[0.20,0.30)** worst kEV (−$0.053) among n≥100 bands. Low-ask fee advantage did not materialise; adverse selection likely dominated.
- **[0.10,0.20)** (n=91): WR=18.7% alarmingly low. CI straddles but 18.7% WR suggests near-total adverse selection in deep-longshot territory. Will never reach n=100 (strategy retired).
- Backtest uniform-EV shape assumption was **not validated**. No band shows a path to positive kEV.

**CONCLUSION: DISCARD (terminal re-confirm).** All n≥100 bands BELOW_CI. No ask-gate tightening could salvage the strategy. Dataset frozen.

**FAILURE_MET:** Yes — n≥100 bands [0.20,0.30), [0.30,0.40), [0.40,0.50) all BELOW_CI.

**IF_DEPLOYED:** N/A — strategy retired. Narrowing ASK_CEIL to <0.30 would have captured n=91+227=318 entries (36% of volume) with kEV=−$0.027 aggregate — still negative.

---

## Investigation H7 — Watchlist Cell Trajectories (Terminal Closure)

**HYPOTHESIS:** All VOLARB cells frozen since retirement 2026-05-19T02:50Z. This cycle verifies zero delta persists, and provides the first full SOL reading (truncated in prior scout report).

**METHOD:** Compare current n and kEV for all three asset cells vs prior scout values. Flag any cell with |Δ kEV| > 2×SE as drift signal.

**RESULT:**

| Cell | Prior n | Now n | Δn | Prior kEV | Now kEV | Δ kEV | Status |
|---|---|---|---|---|---|---|---|
| BTC | 286 | 286 | **0** | +$0.039 | +$0.039 | $0.000 | ZERO_DELTA |
| ETH | 305 | 305 | **0** | −$0.075 | −$0.075 | $0.000 | ZERO_DELTA |
| SOL | *(truncated)* | 296 | — | *(N/A)* | −$0.030 | — | FIRST_FULL_READ |

**SOL full detail (first complete reading this cycle):**

| Asset | n | kn | WR% | kEV/$1 | CI95 | vs_CI |
|---|---|---|---|---|---|---|
| SOL | 296 | 292 | 38.5% | −$0.030 | [−$0.202, +$0.142] | **BELOW_CI** |

**CONCLUSION: DISCARD (terminal re-confirm).** Zero delta on BTC/ETH. SOL first-read confirms BELOW_CI consistent with aggregate. No drift detected. Watchlist monitoring for VOLARB permanently closed.

**FAILURE_MET:** No drift detected. All cells ZERO_DELTA or first-confirmed BELOW_CI.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — continue collecting (n=887, frozen).**

All three investigated hypotheses (H1, H3, H7) and all prior hypotheses (H2, H4, H5, H6) return DISCARD or INCONCLUSIVE with zero delta.

**Cross-strategy note for LDA team (informational only; no gate change):**
VOLARB H3 per-ask-band analysis shows [0.20,0.30) had the worst kEV (−$0.053) despite fee advantage at low asks. This is consistent with adverse selection dominating fee economics at deep-longshot prices — low-ask tokens may be correctly priced by the market as unlikely to resolve YES. LDA's B1 ask gate [0.60,0.90) avoids this zone entirely. This is confirmatory context for LDA's existing gate design; no LDA change is recommended or implied.

---

## Closed-Family Confirmations

| Family | Status | Last n | kEV | Confirmation |
|---|---|---|---|---|
| H1 per-asset (BTC/ETH/SOL) | CLOSED/BELOW_CI | 286/305/296 | +0.039/−0.075/−0.030 | ✓ Full table re-confirmed this cycle |
| H2 per-hour | CLOSED/INCONCLUSIVE | <100/hour max | — | ✓ Permanently inconclusive; no change |
| H3 per-ask-band | CLOSED/BELOW_CI | 91/227/390/158/9 | see table | ✓ Full table re-confirmed this cycle |
| H4 longshot Phase 2 | MOOT | 0 shadow rows | — | ✓ Recorder absent; strategy retired |
| H5 seconds-to-resolution | CLOSED/BELOW_CI | 609 (220-280s) | −$0.042 | ✓ Prior carried over; zero delta |
| H6 direction asymmetry | CLOSED/BELOW_CI | 393/494 | −$0.029/−$0.019 | ✓ Prior carried over; zero delta |
| H7 watchlist trajectories | CLOSED/ZERO_DELTA | 286/305/296 | see H1 table | ✓ Confirmed this cycle |

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within 24h (Auditor watch):**
None. VOLARB dataset frozen at n=887. No new entries will arrive. VOLARB Auditor watch permanently closed.

**Shadow loggers past threshold (Validator review):**
- `volarb_longshot_shadow`: **ABSENT** from shadow_summary.json. Recorder never deployed before strategy retirement. Phase 2 longshot OOS validation was never completed. Moot.
- No other VOLARB-specific shadow loggers exist.

**Phase 2 longshot recorder status:** NOT DEPLOYED / MOOT (strategy retired 2026-05-19T02:50Z).

**Capital anomaly (open, flagged prior cycle — no response observed):**
SNIPER 2026-05-27T00:28Z shows capital_after=$27.98 in trades.jsonl. bankroll.json shows capital=$95.304 (saved 2026-05-27T11:25Z). The +$67.3 discrepancy is unexplained by any row in trades.jsonl. Likely a user capital injection between 00:28Z and 11:25Z. Flagging again for human acknowledgement. Outside VOLARB scope.

**VOLARB Scout termination recommendation:**
All H1–H7 families are closed. Dataset is frozen at 887 rows. Continued VOLARB Scout cycles produce zero-delta confirmation only with no actionable output. Recommend ceasing scheduled VOLARB Scout runs. If the strategy is re-activated (new `bond_entry_class=='VOLARB'` rows appear in data-mirror), this report template provides the baseline for a fresh cycle.

**Active strategy LDA note:**
This Scout is VOLARB-scoped. LDA (signal_source=='LDA', 1053 rows in trades.jsonl) is out of scope but has open candidates in research_status.md §3. LDA Scout/Auditor should run independently per their runbook.
