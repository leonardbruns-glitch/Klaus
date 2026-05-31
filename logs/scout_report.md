# VOLARB Alpha Scout — 2026-05-31T00:43Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-31T00:37:33Z (~5.5 min old — FRESH) |
| Klaus state | active (bankroll $95.30, saved_ts 2026-05-27T11:26Z) |
| Klaus HEAD | efdfef73 (matches system — CODE_DESYNC: PASS) |
| Capital | $95.30 |
| VOLARB live n | **887 — FROZEN 11.4 days** (Δn=0 vs prior cycle) |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |
| LDA live n | 1053 trades (active strategy, not in scope) |

**Pre-flight results:**
- snapshot_ts age: ~5.5 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as **PASS**
- Last Scout commit: 2026-05-30T00:44Z (~24h ago, ≥8h threshold) — **PROCEED**
- CODE_DESYNC: SNAPSHOT HEAD=efdfef73 matches system — **PASS**
- Δn since prior scout: **Δn=0** — dataset permanently frozen at n=887

**Incidental system alert (not in Scout mandate — flag to Watchdog):**
- Disk 100% full: 92G/97G used, 1G free. Data writes at risk.

**Aggregate VOLARB ($1-equiv, kline_pnl basis — canonical per research_status.md §1):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (kline_pnl>0) | 31.6% (277/876 kn) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| Days since last trade | 11.9 | — |
| 24h delta n | 0 | permanently frozen |

---

## Continuity vs Prior Scout (2026-05-30T00:44Z, ~24h ago)

**Investigations carried over (zero-delta confirmed):**
- H1 (per-asset alpha): DISCARD terminal cycle 4 confirmed. Δn=0 — terminal stands.
- H3 (per-ask-band): DISCARD terminal confirmed. Δn=0 — terminal stands.
- H5 (seconds-to-resolution): DISCARD terminal confirmed prior cycle. Δn=0. Note: `term_remaining_s=0.0` for all VOLARB rows (field unpopulated at entry; residual analysis from prior cycles used computed proxy). Terminal stands.
- H6 (direction asymmetry): DISCARD terminal confirmed cycle 4. Δn=0 — terminal stands.
- H2 (per-hour, cross-LDA flag): DATA_MISSING in VOLARB (n<100 per hour); cross-LDA flag open → investigated this cycle (see H2 below).
- H4 (Phase 2 longshot recorder): MOOT (0 bytes prior cycle) → investigated this cycle for formal closure (see H4 below).

**Resolved/closed since prior:** None new. All families already terminal or MOOT.

---

## Investigations (3 selected: H7, H2-cross-LDA, H4)

### H7: Watchlist Cell Trajectories

**HYPOTHESIS:** Previously-flagged cells (per-asset, per-ask-band, direction) may show 24h drift away from their terminal DISCARD status.

**METHOD:** Recompute all n≥100 cell statistics at current n=887. Compare to prior-cycle values. Δn=0 → no arithmetic change possible; statistical confirmation only.

**RESULT:**

*Per-asset (kline_pnl basis, $1-equiv):*

| Asset | kn | WR% | kEV/$1 | CI95 | vs_CI | Δn vs prior |
|---|---|---|---|---|---|---|
| BTC | 283 | 31.1% | +$0.039 | [−$0.159, +$0.237] | **DISCARD** (CI_hi<+0.244) | 0 |
| ETH | 301 | 30.2% | −$0.075 | [−$0.245, +$0.095] | **DISCARD** | 0 |
| SOL | 292 | 33.6% | −$0.030 | [−$0.202, +$0.142] | **DISCARD** | 0 |

*Per-ask-band (kline_pnl basis, $1-equiv):*

| Band | kn | WR% | kEV/$1 | CI95 | vs_CI | Δn |
|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 15.4% | +$0.032 | [−$0.480, +$0.544] | INCONCLUSIVE (n<100) | 0 |
| [0.20, 0.30) | 227 | 24.7% | −$0.053 | [−$0.273, +$0.166] | **DISCARD** | 0 |
| [0.30, 0.40) | 382 | 35.6% | +$0.010 | [−$0.128, +$0.147] | **DISCARD** | 0 |
| [0.40, 0.50) | 156 | 42.9% | −$0.007 | [−$0.189, +$0.175] | **DISCARD** | 0 |
| [0.50, 0.60) | 8 | 37.5% | −$0.282 | [−$0.974, +$0.410] | INCONCLUSIVE (n<100) | 0 |

*Direction asymmetry:*

| Direction | kn | WR% | kEV/$1 | CI95 | vs_CI | Δn |
|---|---|---|---|---|---|---|
| up | 389 | 28.5% | −$0.029 | [−$0.197, +$0.140] | **DISCARD** | 0 |
| down | 487 | 34.1% | −$0.019 | [−$0.149, +$0.111] | **DISCARD** | 0 |

**CONCLUSION: DISCARD (terminal re-confirm, cycle 5).** Δn=0 across every cell. All n≥100 cells remain DISCARD (CI_hi < baseline lower +$0.244). No 24h drift possible. Watchlist cells are permanently terminal.

**FAILURE_MET:** yes — all n≥100 cells DISCARD; dataset frozen.

**IF_DEPLOYED:** N/A — VOLARB permanently retired.

---

### H2: Per-Hour Cross-LDA Follow-up (from prior cross-flag)

**HYPOTHESIS:** Prior scout flagged H01 (kEV=+$0.389, n=66) and H18 (kEV=+$0.685, n=17) in VOLARB as positive outliers worth monitoring in LDA (n≈1053, sufficient for n≥100/hour). If these hours show positive kEV in LDA too, it would constitute a cross-strategy directional signal.

**METHOD:** Slice LDA trades (n=1053, kn=861) by UTC hour. Compute kEV = kline_pnl/stake normalized to $1-equiv. Normal CI95. n<100 per hour = INCONCLUSIVE. Check H01 and H18 specifically vs baseline CI.

**RESULT:**

*Selected hours (cross-flag targets + notable cells):*

| Hour UTC | LDA n | WR% | kEV/$1 | CI95 | vs_CI | VOLARB signal |
|---|---|---|---|---|---|---|
| H01 | 2 | 100.0% | +$0.194 | [+$0.064, +$0.325] | INCONCLUSIVE (n=2) | +$0.389 in VOLARB |
| H14 | 71 | 71.8% | −$0.089 | [−$0.221, +$0.043] | INCONCLUSIVE (n<100) | — |
| H17 | 74 | 68.9% | −$0.138 | [−$0.269, −$0.007] | INCONCLUSIVE (n<100) | — |
| H18 | 55 | 74.5% | −$0.096 | [−$0.240, +$0.047] | INCONCLUSIVE (n<100) | +$0.685 in VOLARB |

*No LDA hour reaches n≥100 (max n=74 at H17).* LDA aggregate: n=861, WR=70.8%, kEV=−$0.173, CI=[−$0.228, −$0.118]. LDA's negative kEV reflects its high-ask (0.75+) entry regime — structurally different from VOLARB's [0.10,0.60) range; do not compare on VOLARB baseline.

**CONCLUSION: DATA_MISSING.** No LDA hour cell reaches n≥100. Cross-LDA validation is not viable at current LDA per-hour data density. H01 (n=2) and H18 (n=55, kEV=−$0.096) do not confirm the VOLARB positive patterns. **Closing the cross-LDA flag from prior scout.** Reopen only if: (a) LDA per-hour n reaches ≥100 AND (b) mandate expands to include LDA hourly audit.

**FAILURE_MET:** no — no LDA hour has n≥100; CI test not valid. DATA_MISSING is correct verdict.

**IF_DEPLOYED:** N/A — no actionable signal.

---

### H4: Phase 2 Longshot Recorder Status

**HYPOTHESIS:** A `volarb_longshot_shadow.jsonl` recorder was proposed for tracking ask<0.10 VOLARB candidates with realized outcomes. Phase 2 gate prep requires n≥100 OOS at ask<0.10.

**METHOD:** Check shadow_summary.json and data-mirror shadow directory for `volarb_longshot_shadow` key or file.

**RESULT:**
- `volarb_longshot_shadow.jsonl`: **absent** from `data/shadow/` on data-mirror
- shadow_summary.json: no `volarb` or `longshot` key present
- shadow_summary.json loggers: all dated `hot/2026-05-08/` (pre-VOLARB activation 2026-05-16)
- VOLARB ask<0.10 cell: within live n=887, this sub-population has n=91 in [0.10,0.20) band — ask<0.10 cell size is unknown but likely n<91; cannot reach n≥100 OOS threshold

**CONCLUSION: MOOT.** VOLARB strategy retired 2026-05-19 (11.9 days ago). Recorder was never deployed during VOLARB's 2.2-day active window. Dataset is frozen — no new VOLARB entries possible. Phase 2 longshot gate prep has no deployment target. **Formally close the Phase 2 longshot item.** No recorder spec needed.

**FAILURE_MET:** N/A — strategy retired before threshold was reachable.

**IF_DEPLOYED:** N/A.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — VOLARB dataset permanently frozen (n=887). All H-families either DISCARD terminal (cycles 1–5) or MOOT. Strategy retired 2026-05-19.**

**Recommendation to Auditor/Watchdog:** This is cycle 5 of zero-delta. VOLARB post-mortem is complete. The Scout agent assigned to this investigation pool has exhausted all viable hypotheses. Recommend halting VOLARB Scout cycles and redirecting Scout mandate to LDA (active strategy, n=1053 and growing) if further investigation is warranted.

---

## Closed-Family Confirmations

Re-validated as null this cycle (Δn=0 prevents new conclusions; terminal statuses reconfirmed):

| Family | Status | Reconfirmed |
|---|---|---|
| H1 per-asset alpha | DISCARD terminal | cycle 5 (Δn=0) |
| H2 per-hour UTC | DATA_MISSING + cross-LDA flag CLOSED | this cycle |
| H3 per-ask-band | DISCARD terminal | cycle 5 (Δn=0) |
| H4 Phase 2 longshot | MOOT | this cycle (formally closed) |
| H5 sec-to-res | DISCARD terminal | cycle 5 (Δn=0) |
| H6 direction asymmetry | DISCARD terminal | cycle 5 (Δn=0) |
| H7 watchlist trajectories | DISCARD terminal | this cycle |

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:**
- None — VOLARB dataset frozen. No cells will cross any threshold.

**Shadow loggers past threshold:**
- volarb_longshot_shadow: never deployed, now MOOT (strategy retired).
- No VOLARB-era shadow loggers exist in data-mirror.

**Phase 2 longshot recorder status:** CLOSED (MOOT — see H4).

**Auditor watch items from this cycle:**
- None in VOLARB scope.
- *Incidental:* Disk 100% full (92G/97G). If shadow/trade logging is failing silently, this is the likely cause. Watchdog should check `SHADOW_LOGGER_STALLED` alert.

**Recommendation:** Halt VOLARB Scout (this report family). Rotate Scout mandate to LDA hourly audit once LDA reaches n≥100 per hour (current max n=74 at H17; at current LDA fire rate, estimate n≥100/hr in approximately 7–14 days for peak hours H13–H18).
