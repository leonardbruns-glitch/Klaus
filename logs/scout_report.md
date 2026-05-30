# VOLARB Alpha Scout — 2026-05-30T00:44Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-30T00:37:23Z (~7 min old — FRESH) |
| Klaus state | active (bankroll $95.304, saved_ts 2026-05-30T00:37:23Z) |
| Klaus HEAD | efdfef73 |
| Capital | $95.304 |
| VOLARB live n | **887 — FROZEN 11.4 days** |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~7 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as **PASS**
- Last Scout commit: prior cycle 2026-05-28T12:46Z (~36h ago, ≥8h threshold) — **PROCEED**
- CODE_DESYNC: VOLARB retired (last trade 2026-05-19T02:50Z); LDA now active — **N/A for post-mortem**
- Delta vs prior scout: **Δn=0, dataset fully frozen** — all cell statistics identical to prior cycle

**Aggregate VOLARB ($1-equiv, kline_pnl basis — canonical per research_status.md §1):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (kline_pnl>0) | 31.6% (277/876 kn) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| Days since last trade | 11.4 | — |
| 36h delta n | 0 | frozen |

---

## Continuity vs Prior Scout (2026-05-28T12:46Z, ~36h ago)

**Investigations carried over (zero-delta confirmed):**
- H1 (per-asset alpha): DISCARD terminal confirmed cycle 3 (prior). All three assets BELOW_CI. Zero-delta — terminal status stands.
- H3 (per-ask-band): DISCARD terminal confirmed cycle 3 (prior). All n≥100 bands BELOW_CI. Zero-delta — terminal status stands.
- H5 (seconds-to-resolution proxy): DISCARD confirmed prior cycle. Dominant band [220,280)s BELOW_CI. Zero-delta — terminal status stands.
- H6 (direction asymmetry): DISCARD confirmed (both up n=393 and down n=494 BELOW_CI). Zero-delta.
- H4 (longshot Phase 2): MOOT — shadow file 0 bytes, no volarb key in shadow_summary.

**Resolved/closed since prior:** None — all families already terminal. Dataset frozen.

**New work this cycle:** H2 full 24-hour UTC breakdown (not run with this granularity in prior reports).

---

## Investigations (3 selected: H1 terminal re-confirm, H2 new per-hour, H6 terminal re-confirm)

### H1: Per-Asset Alpha (Terminal Re-confirm, Cycle 4)

- **HYPOTHESIS:** Individual assets might show positive kEV above baseline CI despite aggregate being BELOW_CI.
- **METHOD:** Slice VOLARB (n=887, kn=876) by `asset` field. kEV = kline_pnl/stake normalised to $1-equiv. Normal CI95. First-fire dedup by trade_id. n<100 = INCONCLUSIVE.
- **RESULT:**

| Asset | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | Δn vs prior |
|---|---|---|---|---|---|---|---|---|
| BTC | 286 | 283 | 31.1% | +$0.039 | −$0.159 | +$0.237 | **BELOW_CI** | 0 |
| ETH | 305 | 301 | 30.2% | −$0.075 | −$0.245 | +$0.095 | **BELOW_CI** | 0 |
| SOL | 296 | 292 | 33.6% | −$0.030 | −$0.202 | +$0.142 | **BELOW_CI** | 0 |

- **CONCLUSION: DISCARD (terminal re-confirm, cycle 4).** All three assets n≥100. All CI_hi below baseline lower (+$0.244). BTC best (kEV=+$0.039, CI_hi=+$0.237 — marginally below floor). ETH worst (kEV=−$0.075). Dataset permanently frozen — will not change.
- **FAILURE_MET:** yes — all three n≥100 assets BELOW_CI.
- **IF_DEPLOYED:** N/A — VOLARB strategy permanently retired.

---

### H2: Per-Hour UTC EV Distribution (New This Cycle)

- **HYPOTHESIS:** Certain UTC hours may show positive kEV above baseline CI. Hours 01-02 UTC and 13-14 UTC (macro release) are primary candidates.
- **METHOD:** Slice VOLARB (n=887) by `hour_utc` field (0-23). kEV = kline_pnl/stake at $1-equiv. Normal CI95. n<100 = INCONCLUSIVE. Active era: 2026-05-16T21:00 – 2026-05-19T02:50 (53.8h).
- **DATA NOTE:** No hour reaches n≥100 in the VOLARB era. Max n=71 at H11. All cells INCONCLUSIVE by rule.
- **RESULT (all INCONCLUSIVE; showing full table):**

| Hour UTC | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI |
|---|---|---|---|---|---|---|---|
| H00 | 39 | 39 | 28.2% | −$0.053 | −$0.556 | +$0.450 | INCONCLUSIVE (n<100) |
| H01 | 66 | 66 | 45.5% | **+$0.389** | −$0.022 | +$0.800 | INCONCLUSIVE (n<100) |
| H02 | 64 | 64 | 37.5% | +$0.064 | −$0.288 | +$0.415 | INCONCLUSIVE (n<100) |
| H03 | 37 | 37 | 40.5% | +$0.120 | −$0.337 | +$0.578 | INCONCLUSIVE (n<100) |
| H04 | 37 | 37 | 35.1% | −$0.001 | −$0.460 | +$0.457 | INCONCLUSIVE (n<100) |
| H05 | 35 | 35 | 14.3% | −$0.536 | −$0.927 | −$0.145 | INCONCLUSIVE (n<100) |
| H06 | 36 | 36 | 27.8% | −$0.135 | −$0.612 | +$0.342 | INCONCLUSIVE (n<100) |
| H07 | 31 | 31 | 16.1% | −$0.332 | −$0.953 | +$0.288 | INCONCLUSIVE (n<100) |
| H08 | 35 | 35 | 25.7% | +$0.255 | −$0.542 | +$1.053 | INCONCLUSIVE (n<100) |
| H09 | 28 | 28 | 14.3% | −$0.452 | −$0.973 | +$0.070 | INCONCLUSIVE (n<100) |
| H10 | 38 | 38 | 31.6% | −$0.061 | −$0.535 | +$0.413 | INCONCLUSIVE (n<100) |
| H11 | 71 | 71 | 35.2% | +$0.097 | −$0.290 | +$0.485 | INCONCLUSIVE (n<100) |
| H12 | 36 | 36 | 27.8% | −$0.226 | −$0.675 | +$0.223 | INCONCLUSIVE (n<100) |
| H13 | 36 | 36 | 33.3% | +$0.017 | −$0.481 | +$0.515 | INCONCLUSIVE (n<100) |
| H14 | 47 | 47 | 27.7% | −$0.249 | −$0.611 | +$0.113 | INCONCLUSIVE (n<100) |
| H15 | 36 | 36 | 30.6% | +$0.154 | −$0.470 | +$0.779 | INCONCLUSIVE (n<100) |
| H16 | 30 | 30 | 16.7% | −$0.551 | −$0.959 | −$0.144 | INCONCLUSIVE (n<100) |
| H17 | 21 | 20 | 30.0% | −$0.242 | −$0.810 | +$0.326 | INCONCLUSIVE (n<100) |
| H18 | 25 | 17 | 58.8% | **+$0.685** | −$0.032 | +$1.402 | INCONCLUSIVE (n<100) |
| H19 | 0 | 0 | N/A | N/A | N/A | N/A | NO_DATA |
| H20 | 3 | 3 | 100.0% | +$1.617 | +$1.478 | +$1.756 | INCONCLUSIVE (n<100) |
| H21 | 39 | 37 | 43.2% | +$0.257 | −$0.235 | +$0.749 | INCONCLUSIVE (n<100) |
| H22 | 40 | 40 | 30.0% | −$0.193 | −$0.590 | +$0.204 | INCONCLUSIVE (n<100) |
| H23 | 57 | 57 | 28.1% | −$0.043 | −$0.505 | +$0.419 | INCONCLUSIVE (n<100) |

- **CONCLUSION: DATA_MISSING.** No hour cell reaches n≥100. All INCONCLUSIVE by rule — no CI test is valid. H01 point estimate (kEV=+$0.389, WR=45.5%, n=66) is the most interesting but CI lower = −$0.022 barely straddles zero. H05, H07, H09, H16 show severely negative kEV (WR ~14-17%) — potential adverse-hour pattern but again n<100. VOLARB is retired; these patterns cannot be actioned. **Cross-LDA flag:** H01 positive pattern warrants monitoring in the larger LDA dataset (n≈5891 live) where n≥100/hour is achievable.
- **FAILURE_MET:** no — no cell has n≥100, so no CI test is valid. DATA_MISSING is the correct verdict.

---

### H6: Direction Asymmetry — bond_outcome_direction (Terminal Re-confirm)

- **HYPOTHESIS:** Entries in `up` direction may perform differently from `down` direction — potential for directional gate.
- **METHOD:** Slice VOLARB by `bond_outcome_direction` field (up/down). kEV=$1-equiv. CI95. n<100=INCONCLUSIVE.
- **RESULT:**

| Direction | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI |
|---|---|---|---|---|---|---|---|
| down | 494 | 487 | 34.1% | −$0.019 | −$0.149 | +$0.111 | **BELOW_CI** |
| up | 393 | 389 | 28.5% | −$0.029 | −$0.197 | +$0.140 | **BELOW_CI** |

- **CONCLUSION: DISCARD (terminal re-confirm).** Both directions n≥100, both BELOW_CI. `down` entries marginally better WR (34.1% vs 28.5%) but kEV essentially flat (−$0.019 vs −$0.029) — no actionable asymmetry. Both CI_hi values (+$0.111, +$0.140) well below baseline floor (+$0.244). A direction gate cannot rescue the strategy.
- **FAILURE_MET:** yes — both n≥100 directions BELOW_CI.
- **IF_DEPLOYED:** N/A — strategy retired.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — continue collecting (n=887 FROZEN).**

VOLARB is permanently retired. Complete post-mortem summary:
- H1 (per-asset): DISCARD — all 3 assets BELOW_CI (n≥100 each)
- H2 (per-hour): DATA_MISSING — no hour reaches n≥100; H01 shows positive point estimate but CI too wide
- H3 (per-ask-band): DISCARD — all n≥100 bands BELOW_CI
- H5 (timing proxy): DISCARD — dominant band [220,280)s BELOW_CI; [160,220)s straddles but kEV=+$0.044 too low
- H6 (direction): DISCARD — both up/down BELOW_CI (n≥100 each)
- H4 (longshot Phase 2): MOOT — shadow file 0 bytes, not deployed

No cell from any H family shows ABOVE_CI or SIGNAL_FOUND at n≥100. The VOLARB post-mortem is conclusive: strategy had negative EV across all slices examined.

---

## Closed-family confirmations

- **H1 per-asset alpha**: DISCARD — terminal (cycle 4 re-confirm, zero-delta)
- **H3 per-ask-band**: DISCARD — terminal (cycle 4 re-confirm, zero-delta)
- **H5 timing-proxy slice**: DISCARD — terminal (cycle 3 re-confirm, zero-delta)
- **H6 direction asymmetry**: DISCARD — terminal (cycle 2 re-confirm, zero-delta)
- **H4 longshot Phase 2**: MOOT — shadow not deployed, zero-delta

---

## Open requests for Auditor / Shadow Validator

- **Cells trending to n≥100 within next 24h:** None. VOLARB dataset is permanently frozen. No cell can reach n≥100 by organic growth.
- **Shadow loggers past threshold:** None. `volarb_longshot_shadow.jsonl` = 0 bytes. No volarb key in `shadow_summary.json`.
- **Phase 2 longshot recorder status:** NOT deployed — proposed in prior cycles, moot given VOLARB retirement.
- **Cross-LDA watch (not a patch recommendation):** H01 UTC positive pattern in VOLARB (WR=45.5%, kEV=+$0.389, n=66 — inconclusive) warrants the Auditor checking LDA H01 cell size and EV. If LDA H01 is not already blocked and n≥100 with positive kEV, it may be an existing edge the LDA gate set has already captured or may need to capture.

---

*Generated by VOLARB Alpha Scout at 2026-05-30T00:44Z. Dataset frozen at n=887 (last trade 2026-05-19T02:50Z, 11.4 days ago). All VOLARB investigations terminal. No code was modified.*
