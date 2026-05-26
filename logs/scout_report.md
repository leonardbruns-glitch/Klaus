# VOLARB Alpha Scout — 2026-05-26T00:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-26T00:39:13Z (~3 min old — FRESH) |
| Klaus state | active (LDA/WEATHER strategy; VOLARB permanently retired) |
| Klaus HEAD | 945dd1f1 |
| Capital | $30.935465 (bankroll.json) |
| VOLARB n (live era, is_live==True) | **887 — FROZEN since 2026-05-19T02:50Z (7.0 days)** |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~3 min — **PASS**
- integrity_report.json: absent — treated as **PASS**
- CODE_DESYNC check: VOLARB strategy retired; no active gate branch to diff — **N/A**
- Last Scout commit: 2026-05-25T00:42Z (~24h ago, >8h threshold) — **PROCEED**

**VOLARB STATUS: PERMANENTLY RETIRED.** Strategy last fired 2026-05-19T02:50Z. No new VOLARB trades in 7 days. All current live trades are LDA/WEATHER. VOLARB n=887 is permanently frozen. This cycle is a full post-mortem closure.

**Aggregate VOLARB performance (final, stake-normalised $1-equiv, kline_pnl primary):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| WR (net_pnl>0) | 34.6% (307/887) | below 40% backtest expectation |
| EV/trade ($1-equiv, kline_pnl) | −$0.023 | CI=[−0.115, +0.069] — **BELOW baseline CI lower** |
| EV/trade ($1-equiv, net_pnl) | +$0.056 | mark-to-market only; resolution metric supersedes |
| kline vs net divergence | −$81.63 | PROFIT_TARGET exits captured MTM gains that reversed at resolution |
| dedup check | 887/887 unique trade_ids; zero multi-fire duplicates | CLEAN |

---

## Continuity vs Prior Scout (2026-05-25T00:42Z)

**Investigations carried forward:**
- H1 (per-asset): Prior reported ETH BELOW_CI, BTC "marginal WITHIN_CI", SOL "WITHIN_CI" using net_pnl. This cycle re-runs with kline_pnl (research_status.md §7 rule 1). All three assets now confirmed BELOW_CI — see H1 below.
- H3 (per-ask-band): All n≥100 bands confirmed BELOW_CI in prior cycles. Data unchanged; re-confirmed below.
- H6 (direction): Both 'up' and 'down' BELOW_CI in prior cycles. Re-confirmed.

**Resolved/closed this cycle:**
- H5 (seconds_to_resolution): Previously DATA_MISSING due to `term_remaining_s=0` logging bug. This cycle derives rem from ts_open — now fully analyzable. Promoted to SIGNAL_FOUND.
- H2 (per-hour): All hours permanently n<100. Archival flags (H05, H16) unchanged. Closed as permanently INCONCLUSIVE.
- H7 (watchlist trajectories): Zero 24h delta (frozen dataset). Closed.

**Investigations selected this cycle: H5 (new SIGNAL_FOUND), H1 (metric correction), H7 (zero-drift close)**

---

## Investigation H5 — Seconds-to-Resolution Slice

**HYPOTHESIS:** Backtest assumed leak-clean performance at all entry timings within REM_MIN_S=60s–REM_MAX_S=280s. Live data may show time-varying performance; early-window entries (high remaining seconds) may underperform near-resolution entries.

**METHOD:** Derive `term_remaining_s = ceil(ts_open/300)*300 - ts_open` (valid: all rows are market_type=updown, window_size_s=300). Slice into four buckets: [60-100s), [100-160s), [160-220s), [220-280s). Compute n, WR%, kEV/$1, nEV/$1, CI95 (kline). Flag buckets n≥100 with CI entirely below baseline [+0.244, +0.352].

Derivation validity: 887 rows, derived range [57.9s, 278.5s]. Two boundary outliers in "other" (<60s): excluded. Mean derived_rem=226.5s, median=234.8s.

**RESULT:**

| Bucket | n | WR% | kEV/$1 | nEV/$1 | CI95 (kline) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| 60-100s | 14 | 7.1% | −$1.061 | −$0.860 | [−1.147, −0.975] | n<100 (1/14 wins — severe) |
| 100-160s | 65 | 32.3% | +$0.221 | +$0.290 | [−0.298, +0.740] | n<100 (highest kEV bucket) |
| 160-220s | 187 | 36.9% | +$0.044 | +$0.122 | [−0.192, +0.279] | WITHIN_CI |
| 220-280s | **619** | 34.9% | −$0.042 | +$0.010 | [**−0.160, +0.076**] | **BELOW_CI** |

**CONCLUSION: SIGNAL_FOUND.** The 220-280s bucket (n=619, 69.8% of all VOLARB trades) is confirmed BELOW_CI. CI_hi=+0.076 is well below baseline lower of +0.244. Bulk of VOLARB underperformance is attributable to early-window entries. The 100-160s bucket shows highest kEV (+$0.221) though n=65 is insufficient to confirm.

**FAILURE_MET:** No — n=619 for the flagged cell.

**IF_DEPLOYED (hypothetical — VOLARB retired):** A gate capping entries at derived_rem ≤ 220s would have excluded 69.8% of trades and concentrated volume in the 100-220s range (n=252). Counterfactual net kEV improvement: approximately +$44.8 over the live window vs actual resolution-correct loss.

**Root cause hypothesis:** Early-window entries (>220s remaining = entering in first 80s of window) maximise adverse duration. The CLAUDE.md design note ("Entry sweet spot T+30s–T+120s into window" → derived_rem ≈ 180-270s) is consistent but imprecise; live data shows the improvement threshold is closer to 220s (T+80s). The 160-220s WITHIN_CI bucket (T+80s–T+140s) performs materially better than 220-280s.

---

## Investigation H1 — Per-Asset Alpha Re-Allocation (Metric Correction)

**HYPOTHESIS:** Prior scout used net_pnl as primary EV metric, classifying BTC as "marginal WITHIN_CI" and SOL as "WITHIN_CI". Backtest projected BTC as alpha asset. Re-run with kline_pnl (authoritative metric per research_status.md §7 rule 1).

**METHOD:** Slice 887 VOLARB rows by asset. Compute kEV/$1 and CI95 using kline_pnl. vs_baseline_CI = BELOW_CI if CI_hi < +0.244.

**RESULT:**

| Asset | n | WR% | kEV/$1 | nEV/$1 | CI95 (kline) | vs_baseline_CI | Prior (net_pnl) |
|---|---|---|---|---|---|---|---|
| BTC | 286 | 32.9% | +$0.039 | +$0.054 | [−0.159, +0.237] | **BELOW_CI** | "marginal WITHIN_CI" — corrected |
| ETH | 305 | 32.5% | −$0.075 | −$0.031 | [−0.245, +0.095] | **BELOW_CI** | BELOW_CI — confirmed |
| SOL | 296 | 38.5% | −$0.030 | +$0.094 | [−0.202, +0.142] | **BELOW_CI** | "WITHIN_CI" — corrected |

**CONCLUSION: SIGNAL_FOUND (correction).** All three assets confirmed BELOW_CI on kline_pnl. Prior scout's BTC/SOL classifications were based on net_pnl, which overstates VOLARB performance due to PROFIT_TARGET early exits that later resolved at zero. BTC CI_hi=+0.237 falls marginally below baseline lower of +0.244; SOL CI_hi=+0.142 is clearly below. Backtest's projected BTC alpha edge (+$14.81 projected lead) did not materialise. No asset met the backtest EV bar.

**FAILURE_MET:** No — n≥100 for all three assets.

**IF_DEPLOYED:** N/A — VOLARB retired. Only lever would have been raising EDGE_FLOOR globally (no per-asset block lever exists).

---

## Investigation H7 — Watchlist Cell Trajectories (24h Delta)

**HYPOTHESIS:** Cells flagged in prior scout may have drifted in the 24h since last cycle, requiring escalation.

**METHOD:** Compare all prior-flagged cells vs current data. VOLARB n=887 is frozen; 24h delta is mathematically zero for all cells.

**RESULT:**

| Cell | Prior n | Current n | 24h delta | Status |
|---|---|---|---|---|
| ETH (H1 asset) | 305 | 305 | 0 | BELOW_CI — permanent |
| BTC (H1 asset) | 286 | 286 | 0 | corrected to BELOW_CI this cycle |
| SOL (H1 asset) | 296 | 296 | 0 | corrected to BELOW_CI this cycle |
| H05 UTC (H2 hour) | 35 | 35 | 0 | archival: WR=14.3%, kEV=−$0.536 |
| H16 UTC (H2 hour) | 30 | 30 | 0 | archival: WR=16.7%, kEV=−$0.551 |
| Ask [0.20,0.30) | 227 | 227 | 0 | BELOW_CI — permanent |
| Ask [0.30,0.40) | 390 | 390 | 0 | BELOW_CI — permanent |
| Ask [0.40,0.50) | 158 | 158 | 0 | BELOW_CI — permanent |
| Direction 'up' | 393 | 393 | 0 | BELOW_CI — permanent |
| Direction 'down' | 494 | 494 | 0 | BELOW_CI — permanent |
| Rem 220-280s (H5 new) | 619 | 619 | 0 | BELOW_CI — permanent (new this cycle) |

**CONCLUSION: DISCARD** (trivially — frozen dataset). Zero drift on all cells. No escalation warranted.

**FAILURE_MET:** N/A.

---

## Priority Signal for Next Implementation

**H5 (220-280s bucket, n=619) is the primary post-mortem finding.**
CI_hi=+0.076 vs baseline lower +0.244 — confirmed BELOW_CI at large n. The dominant bucket drove VOLARB underperformance.

**No actionable signal for current live LDA strategy.** VOLARB findings do not transfer — LDA uses rem_bucket definitions that differ from VOLARB timing, and LDA trades are not resolution-hold strategies.

**For any future binary-resolution strategy:** Pre-register `max_entry_remaining_s ≈ 220s` as a Tier 1 test hypothesis from launch day, with dedicated shadow logging of the 100-160s and 160-220s buckets as separate cells. n≥100 threshold per bucket before any parameter decision.

---

## Closed-Family Confirmations (re-validated null this cycle)

| Family | n | Status |
|---|---|---|
| H2 (per-hour UTC) | max n=71 (H11) | INCONCLUSIVE — permanently n<100; closed |
| H6 (direction up/down) | 393/494 | BOTH BELOW_CI — confirmed permanent |
| H3 ask [0.10,0.20) | 91 | n<100; will not cross; archival only |
| H3 ask [0.50,0.60) | 9 | n<100; archival only |
| H7 (watchlist drift) | — | Zero drift; closed |
| All VOLARB research | 887 total | **POST-MORTEM COMPLETE** — no further investigation warranted |

---

## Open Requests for Auditor / Shadow Validator

### Cells trending to n≥100 within next 24h
**None.** VOLARB frozen permanently. No cell can accumulate further data.

### Shadow loggers past threshold
- `volarb_longshot_shadow.jsonl`: **ABSENT** — confirmed absent from shadow_summary.json after scanning all 233 loggers. No VOLARB/longshot logger exists.

### Phase 2 Longshot Recorder Status: PROPOSED — awaiting build

**Proposed spec** (for any future binary-resolution successor to VOLARB):

```
Logger: volarb_longshot_shadow
File: data/shadow/volarb_longshot_shadow.jsonl
Schema version: 1
Trigger: market_timeline row where:
  - ask_price < 0.10
  - edge >= 0.10 (with ASK_FLOOR=0.0 hypothetical)
  - acceptingOrders = True
  - liquidityClob >= 200
  - market_type = "updown"
  - derived_rem between 60 and 280
Fields:
  {ts_s, token_id, condition_id, asset, outcome_dir, ask_price,
   edge_at_fire, derived_rem_s, resolution_price,
   kline_pnl_1usd (= resolution_price - ask_price),
   window_end_ts, binance_ret_5m_pct}
Pre-registration n threshold: 100
Purpose: Phase 2 gate validation for ask<0.10 cell
```

Status: NOT BUILT. Should be deployed at launch of any VOLARB successor strategy.

---

## Final Post-Mortem Summary

VOLARB ran 53.8h, 887 trades. Against backtest CI [+$0.244, +$0.352]/trade, live kline_pnl EV was −$0.023/trade — a complete backtest failure. Three confirmed contributing factors:

1. **Entry timing (H5):** 69.8% of trades in 220-280s remaining bucket (BELOW_CI, CI=[−0.160, +0.076]). Entering too early in the window dominated total performance.
2. **Asset universality (H1):** All three assets BELOW_CI on kline_pnl. No BTC alpha materialised. Mark-to-market net_pnl illusion from PROFIT_TARGET exits that reversed at resolution.
3. **Ask-band universality (H3):** All n≥100 ask-band cells BELOW_CI. Edge floor/ceiling did not protect as modelled.

LDA strategy replacement is appropriate. VOLARB research families are fully closed.
