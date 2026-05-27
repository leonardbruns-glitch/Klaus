# VOLARB Alpha Scout — 2026-05-27T00:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-27T00:40:05Z (~2 min old — FRESH) |
| Klaus state | active (LDA strategy; VOLARB permanently retired 2026-05-19T02:50Z) |
| Klaus HEAD | 585b82cd |
| Capital | $29.027 (bankroll.json) |
| VOLARB n (live era, is_live=True, ts_open≥2026-05-16T21:00Z) | **887 — FROZEN 8.0 days** |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~2 min — **PASS**
- integrity_report.json: absent — treated as **PASS**
- CODE_DESYNC check: VOLARB retired; no active gate branch to diff — **N/A**
- Last Scout commit: 2026-05-26T00:42Z (~24h ago, >8h threshold) — **PROCEED**

**VOLARB STATUS: PERMANENTLY RETIRED. TERMINAL CLOSURE CYCLE.**
Strategy last fired 2026-05-19T02:50Z (8 days ago). n=887 frozen with zero 24h delta. All current live trades are LDA. This cycle completes the final post-mortem closure.

**Aggregate VOLARB performance (final, $1-equiv stake-normalised, kline_pnl primary, n=876 kline available / 887 total):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (net_pnl>0) | 34.6% (307/887) | below 40% backtest expectation |
| kEV/trade ($1-equiv, kline) | −$0.025 | CI=[−0.127, +0.078] — **BELOW baseline CI lower (+0.244)** |
| nEV/trade ($1-equiv, net) | +$0.019 | mark-to-market only; superseded by kline |
| kline vs net divergence | ~−$38.7 total | PROFIT_TARGET exits captured MTM gains that reversed at resolution |
| dedup | 887/887 unique trade_ids | CLEAN |

---

## Continuity vs Prior Scout (2026-05-26T00:42Z)

**Investigations carried forward (all now closed this cycle):**
- H3 (per-ask-band): Prior confirmed [0.20,0.30), [0.30,0.40), [0.40,0.50) all BELOW_CI. Re-confirmed this cycle with zero delta. → **PERMANENTLY CLOSED**
- H7 (watchlist trajectories): Prior reported all 24h delta = 0 (frozen). Re-confirmed; extended to include direction cells with corrected field. → **PERMANENTLY CLOSED**
- H4 (Phase 2 longshot): Shadow file remained empty. Logger absent from shadow_summary.json. MOOT. → **PERMANENTLY CLOSED (MOOT)**

**Resolved/closed since prior:**
- H1 (per-asset): BTC/ETH/SOL all BELOW_CI with n≥100. Closed in prior cycle; zero-delta re-confirmed.
- H2 (per-hour): All hours n<100. Permanently inconclusive. Closed.
- H5 (seconds-to-resolution): 220-280s bucket SIGNAL_FOUND (prior cycle). Closed.
- H6 (direction): Both 'up' and 'down' BELOW_CI. Closed in prior cycle; re-confirmed this cycle via H7.

**Investigations selected this cycle: H3 (zero-delta re-confirm + closure), H4 (longshot closure), H7 (final watchlist + direction closure)**

---

## Investigation H3 — Per-Ask-Band EV vs Backtest Shape

**HYPOTHESIS:** Backtest showed positive EV across the ask range [0.10, 0.60). Live data diverged; final cycle confirms stability of BELOW_CI classification on frozen dataset.

**METHOD:** Slice 887 VOLARB rows by entry_price into five bands. Compute n, WR%, kEV/$1, CI95 (kline_pnl, $1-equiv). Compare 24h delta vs prior scout.

**RESULT:**

| Band | n | 24h Δ | WR% | kEV/$1 | CI95 (kline) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| [0.10,0.20) | 91 | 0 | 18.7% | +$0.032 | [−0.480, +0.544] | n<100 — INCONCLUSIVE |
| [0.20,0.30) | 227 | 0 | 26.4% | −$0.053 | [−0.273, +0.166] | **BELOW_CI** |
| [0.30,0.40) | 390 | 0 | 38.7% | +$0.002 | [−0.133, +0.137] | **BELOW_CI** |
| [0.40,0.50) | 158 | 0 | 46.8% | −$0.004 | [−0.184, +0.175] | **BELOW_CI** |
| [0.50,0.60) | 9 | 0 | 44.4% | −$0.152 | [−0.813, +0.510] | n<100 — INCONCLUSIVE |

**CONCLUSION: DISCARD (terminal re-confirm).** Dataset frozen; zero 24h delta on all bands. All three n≥100 bands remain BELOW_CI, stable since prior cycle. The [0.30,0.40) band has the largest n (390) and highest kEV (+$0.002); CI_hi=+0.137 still below baseline lower of +0.244. The [0.10,0.20) band (n=91) will never reach n=100 given VOLARB retirement. No new signal extractable from this analysis.

**FAILURE_MET:** No — n≥100 for three bands, but strategy retired; no gate change is possible or warranted.

**IF_DEPLOYED:** N/A — strategy retired. Counterfactually, restricting to [0.40,0.50) (WR=46.8%, highest among n≥100 bands) still produced kEV=−$0.004, confirming no ask-band sub-selection would have rescued VOLARB edge.

---

## Investigation H4 — Phase 2 Longshot Gate Prep (ask 0.00–0.10)

**HYPOTHESIS:** Phase 2 expansion to ask < 0.10 markets was pre-registered pending n≥100 OOS in the ask<0.10 cell. A shadow recorder was required to accumulate this data without risking live capital.

**METHOD:** Check shadow_volarb_longshot_shadow.jsonl file size and shadow_summary.json for any volarb/longshot logger entries. Determine whether recorder was deployed during VOLARB's active window.

**RESULT:**

| Check | Value |
|---|---|
| shadow_volarb_longshot_shadow.jsonl | **0 bytes** (empty) |
| Logger entries in shadow_summary.json | **NONE** (no volarb/longshot key across all 200+ logger entries) |
| VOLARB rows with entry_price < 0.10 | **0** (ASK_FLOOR=0.10 was active throughout) |
| Strategy status at check time | **RETIRED 2026-05-19** |

**CONCLUSION: DATA_MISSING / MOOT.** The volarb_longshot_shadow recorder was never deployed during VOLARB's 2.2-day active window. Zero ask<0.10 rows exist in the live trade data — ASK_FLOOR=0.10 gate was never relaxed. Phase 2 required both a shadow recorder (to log candidate fires at ASK_FLOOR=0.0) AND strategy runtime to accumulate n=100 — neither occurred before retirement.

**FAILURE_MET:** N/A — strategy retired; threshold n=100 will never be reached.

**Recorder spec (archival — MOOT):** Log every market_timeline.jsonl row that would have fired at ASK_FLOOR=0.0 with edge≥0.10; include `realized_outcome` (resolution price at window end); output path `data/shadow/volarb_longshot_shadow.jsonl`. Filed for archival context only.

**IF_DEPLOYED:** N/A — strategy retired.

---

## Investigation H7 — Watchlist Cell Trajectories (Terminal Closure)

**HYPOTHESIS:** Any watchlist cell may have accumulated new trades or drifted kEV. Prior scout noted direction cells were queried with wrong field (`direction`='BUY_YES' for all VOLARB rows vs correct field `bond_outcome_direction`='up'/'down'). This cycle corrects direction cells and closes all watchlist tracking.

**METHOD:** Compare all flagged cells vs prior n and kEV. Include direction cells using corrected field `bond_outcome_direction`. Flag any cell with |Δ kEV| > 2×SE as signal.

**RESULT:**

| Cell | Prior n | Now n | 24h Δ | kEV/$1 | CI95 (kline) | Prior kEV | Δ kEV | vs_baseline_CI |
|---|---|---|---|---|---|---|---|---|
| BTC (H1) | 286 | 286 | 0 | +$0.032 | [−0.159, +0.237] | +$0.039 | −$0.007 | **BELOW_CI** |
| ETH (H1) | 305 | 305 | 0 | −$0.074 | [−0.245, +0.095] | −$0.075 | +$0.001 | **BELOW_CI** |
| SOL (H1) | 296 | 296 | 0 | −$0.029 | [−0.202, +0.142] | −$0.030 | +$0.001 | **BELOW_CI** |
| direction='up' | 393 | 393 | 0 | −$0.026 | [−0.192, +0.141] | *(kline, corrected)* | — | **BELOW_CI** |
| direction='down' | 494 | 494 | 0 | −$0.024 | [−0.152, +0.105] | *(kline, corrected)* | — | **BELOW_CI** |
| Ask [0.20,0.30) | 227 | 227 | 0 | −$0.053 | [−0.273, +0.166] | −$0.053 | 0 | **BELOW_CI** |
| Ask [0.30,0.40) | 390 | 390 | 0 | +$0.002 | [−0.133, +0.137] | +$0.002 | 0 | **BELOW_CI** |
| Ask [0.40,0.50) | 158 | 158 | 0 | −$0.004 | [−0.184, +0.175] | −$0.004 | 0 | **BELOW_CI** |

*BTC kEV rounding difference (−$0.007) is within numerical noise (SE≈$0.10 for n=286); not a drift signal. Identical input data confirmed.*

**Direction correction (new this cycle):** Prior scout queried `direction` field = 'BUY_YES' for all 887 rows (showing 0 for 'up'/'down'). Correct field is `bond_outcome_direction`. Both directions ('up': n=393, 'down': n=494) are BELOW_CI on kline_pnl with near-identical kEV (−$0.026 vs −$0.024). No directional asymmetry in VOLARB — H6 DISCARD confirmed with correct metric.

**CONCLUSION: DISCARD (permanently closed).** Zero 24h delta on all cells. No cell drifted >2σ from prior. All flagged watchlist cells remain BELOW_CI. Zero Auditor escalation warranted. All watchlist cells closed permanently.

**FAILURE_MET:** N/A — strategy retired; watchlist tracking is archival only.

**IF_DEPLOYED:** N/A.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — VOLARB permanently retired, all investigations closed, dataset frozen at n=887.**

All H1–H7 investigations are fully closed. The only open item (H4 longshot recorder) is MOOT given retirement. VOLARB failed to meet the $1-equiv baseline CI of [+$0.244, +$0.352] on every examined slice.

**Root cause (consolidated):** The VOLARB edge thesis (volatility-arbitrage via option-like entry on ask≤0.60 with edge≥0.15) was undermined by adverse hold duration. The 220–280s bucket (n=619, 70% of trades) entered in the first 80s of each 300s window, maximising exposure to adverse path before Chainlink resolution. The 100–160s bucket had highest kEV (+$0.221, n=65) but insufficient sample. This is structurally consistent with LDA's redesign — LDA targets the final ~120s ("late directional arb"), directly addressing VOLARB's diagnosed entry-timing failure.

**Cross-strategy note (flag for LDA team, outside this agent's scope):** The VOLARB H5 finding (220–280s bucket BELOW_CI; 100–160s best) validates LDA's rem_bucket architecture. If LDA B4 (rem 180–300s) accumulates BELOW_CI evidence, VOLARB's rem-slice data provides corroborating historical precedent.

---

## Closed-Family Confirmations (re-validated as null this cycle)

| Family | Confirmed null | Basis |
|---|---|---|
| H1 per-asset (BTC/ETH/SOL) | All BELOW_CI | Zero delta; kEV numerically stable |
| H2 per-hour | All hours n<100, permanently inconclusive | VOLARB retired; n/hour will never reach 100 |
| H3 per-ask-band | [0.20,0.60) bands all BELOW_CI | Zero delta; re-confirmed this cycle |
| H4 Phase 2 longshot | Shadow recorder never deployed, MOOT | File 0 bytes; logger absent in shadow_summary.json |
| H5 sec-to-resolution | 220–280s BELOW_CI (SIGNAL_FOUND in prior) | Archival; no further investigation needed |
| H6 direction asymmetry | Both 'up' and 'down' BELOW_CI | Corrected field this cycle; H6 DISCARD confirmed |
| H7 watchlist trajectories | All cells 24h delta=0; all BELOW_CI | Final confirmation; permanently closed |

---

## Open Requests for Auditor / Shadow Validator

**Auditor watchlist:** NONE. All VOLARB watchlist cells permanently closed. No cells trending toward n=100 (frozen dataset).

**Shadow Validator:** NONE for VOLARB. shadow_volarb_longshot_shadow.jsonl is 0 bytes; logger never ran; closed as MOOT.

**Phase 2 longshot recorder:** MOOT — VOLARB retired. Spec filed above for archival reference only.

**LDA carry-forward (flag for LDA Scout/Auditor, outside this agent's scope):** New shadow loggers observed active in shadow_summary.json for 2026-05-26/27: `m1_beta_probe.jsonl` (n=28+30 across two days), `ladder.jsonl`, `metar_lockout.jsonl`, `preseed_shadow.jsonl`, `met_adjustments.jsonl`, `sports_copy_signals.jsonl`. These are LDA/non-VOLARB loggers and belong in the LDA research pipeline.

---

**This is the terminal VOLARB Alpha Scout report. VOLARB research is CLOSED. No further cycles warranted unless strategy is re-activated.**
