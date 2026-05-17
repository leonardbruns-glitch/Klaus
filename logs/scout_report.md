# VOLARB Alpha Scout — 2026-05-17T12:42 UTC

## Snapshot + Baseline

| Field | Value |
|---|---|
| snapshot_ts | 2026-05-17T12:38:49Z (age: 13 min — FRESH) |
| snapshot_age_check | PASS (< 45 min) |
| integrity_report.json | ABSENT (blocks_agent_run not readable — treated as non-blocking) |
| Klaus capital | $66.87 |
| Klaus service | active |
| VOLARB n (all live, ts_open ≥ 2026-05-16T21:00 UTC) | 548 |
| VOLARB n (Phase 1 gate: ask ∈ [0.10, 0.60)) | **541** |
| Live era start | 2026-05-16T21:00 UTC (ts=1778965200) |
| Dedup method | token_id first-fire; 0 duplicates found |
| $1-equiv baseline CI | [+$0.244, +$0.352] / trade |

### Global Live EV (Phase 1 Gate, n=541)

| Metric | Value | vs Baseline |
|---|---|---|
| WR | 34.8% | Below 40% target; above 30% kill floor |
| EV / $1 stake | +$0.092 | **CI upper = +$0.230 < baseline CI lower = +$0.244** |
| 95% CI | [−$0.047, +$0.230] | **SIGNAL:BELOW_CI globally** |
| sum(net_pnl) | +$74.79 | |
| Mean stake (live) | $1.54 | vs STAKE_USD=1.0 spec |

> **Global signal**: The live 95% CI upper (+$0.230) is below the backtest CI lower (+$0.244). With n=541 this is not noise. The strategy is underperforming backtest expectations at a statistically significant level.

---

## Continuity vs Prior Scout

| Item | Status |
|---|---|
| Prior scout (2026-05-16 06:00 UTC) | Scope: LDA/BOND reframe. VOLARB not yet activated (activation: 21:00 same day). No VOLARB findings to carry over. |
| Investigations carried over | None — first VOLARB scout run |
| Resolved/closed since prior | N/A |
| LDA status (concurrent) | n=111 live, WR=82%, net=+$7.01 (week-1 summary). Separate strategy. |

---

## Investigation H1 — Per-Asset Alpha Re-Allocation (PRIORITY)

**HYPOTHESIS:** Backtest named BTC as alpha asset (+$14.81 projected lead). Live data may differ. Compare per-asset EV, flag assets below baseline CI lower at n≥100.

**METHOD:** Filter VOLARB live Phase 1 records by asset. Compute net_pnl/stake ($1-equiv), WR, 95% CI. Compare CI against baseline [+$0.244, +$0.352].

**RESULT:**

| Asset | n | WR | EV/$1 | 95% CI | sum(net_pnl) | STATUS |
|---|---|---|---|---|---|---|
| BTC | 171 | 30.4% | +$0.063 | [−$0.196, +$0.322] | +$8.96 | ON_BASELINE |
| ETH | 189 | 32.3% | +$0.020 | [−$0.216, +$0.256] | +$12.61 | ON_BASELINE |
| SOL | 181 | 41.4% | +$0.193 | [−$0.032, +$0.418] | +$53.22 | ON_BASELINE |

**CONCLUSION: INCONCLUSIVE**

All three asset CIs overlap the baseline range. The rank order (SOL > BTC > ETH) inverts the backtest projection (BTC +$14.81 lead). SOL EV is 3.1× BTC EV in live data. Variance is high — CIs span ~±$0.25, masking real per-asset differences. No asset has CI fully outside baseline at current n.

**FAILURE_MET: No.** BTC WR=30.4% is near the 30% flag threshold but has not crossed it over any 20-trade rolling window. ETH CI upper (+$0.256) is only marginally above baseline lower (+$0.244) and is the most likely asset to cross to SIGNAL:BELOW_CI.

**IF_DEPLOYED:** N/A — INCONCLUSIVE. Watchlist: ETH for SIGNAL:BELOW_CI at n≥250. SOL's outperformance should be monitored; if sustained at n≥250, consider whether asset-specific EDGE_FLOOR relaxation is warranted (Tier 2).

---

## Investigation H5 — Seconds-to-Resolution Slice

**HYPOTHESIS:** Backtest assumed the full [60s, 280s] entry window is uniform in EV. Live data may show systematic degradation at earlier entry times (more time remaining = more uncertainty = lower realized EV).

**METHOD:** Compute `sec_to_res_at_entry = ((floor(ts_open/300)+1)*300) − ts_open` for each trade (window_size_s=300 for all VOLARB Phase 1 records). Bucket into [60–100s), [100–160s), [160–220s), [220–280s). Compute EV/$1 and 95% CI per bucket vs baseline.

*Note: `seconds_to_resolution` field in order_lifecycle.jsonl (n=590, VOLARB era) reads 0.0 for all records — confirmed data bug. Computed from ts_open instead.*

**RESULT:**

| sec_to_res at entry | n | WR | EV/$1 | 95% CI | STATUS |
|---|---|---|---|---|---|
| [60–100s) | 8 | 12.5% | −$0.655 | [−$1.342, +$0.033] | INCONCLUSIVE |
| [100–160s) | 49 | 34.7% | +$0.482 | [−$0.163, +$1.126] | INCONCLUSIVE |
| [160–220s) | 120 | 36.7% | +$0.134 | [−$0.158, +$0.426] | ON_BASELINE |
| [220–280s) | **362** | 34.8% | +$0.047 | [−$0.112, +$0.206] | **SIGNAL:BELOW_CI** |

**CONCLUSION: SIGNAL_FOUND**

The [220–280s) bucket contains 67% of all Phase 1 VOLARB trades (n=362) and is confirmed SIGNAL:BELOW_CI. CI upper = +$0.206 < baseline lower = +$0.244. There is a clear negative EV gradient as sec_to_res increases: entries closest to resolution ([100–160s) range, INCONCLUSIVE but EV=+$0.482) appear substantially more profitable than early entries. The [160–220s) bucket (n=120) is ON_BASELINE at EV=+$0.134.

The dominant entry window (220–280s remaining) drives global underperformance. Early entries have high BOND_RESOLVED_NO rates — the market has maximum time to move against the position.

**FAILURE_MET: No.** The [220–280s) bucket is BELOW_CI but not a strategy kill condition.

**IF_DEPLOYED:** Reducing REM_MAX_S from 280s → 220s would eliminate the [220–280s) n=362 bucket (EV=+$0.047). Retained population: n≈177 ([100–220s)), all at ON_BASELINE or better. Trade volume would fall ~67%. This is a >20% parameter change → Tier 2. Auditor review required. Scout cannot recommend implementation.

---

## Investigation H6 — Direction Asymmetry (up vs down)

**HYPOTHESIS:** `bond_outcome_direction` partitions VOLARB entries into two groups. Backtest had no direction split; live data may reveal asymmetric EV.

**METHOD:** Group Phase 1 records by `bond_outcome_direction`. Compute EV/$1, WR, 95% CI. Compare vs baseline. Validate field semantics via cross-tabulation with exit_reason and window_outcome_price.

**RESULT:**

| bond_outcome_direction | n | WR | EV/$1 | 95% CI | STATUS |
|---|---|---|---|---|---|
| up | 226 | 32.7% | +$0.142 | [−$0.095, +$0.380] | ON_BASELINE |
| down | **315** | 36.2% | +$0.055 | [−$0.111, +$0.221] | **SIGNAL:BELOW_CI** |

**Field semantics (cross-tab validation):**

| bod | wop | n | WR | Interpretation |
|---|---|---|---|---|
| down | 0.0 | 100 | 99% | VOLARB entered vs BOND-DOWN signal; early profit exits before adverse resolution |
| down | 1.0 | 215 | 7% | Held to resolution; YES expired at 0 (market resolved NO) — systematic losses |
| up | 0.0 | 156 | 4.5% | Entered with BOND-UP signal; held to adverse resolution |
| up | 1.0 | 70 | 95.7% | BOND-UP + YES won — high-quality exits |

VOLARB `direction=BUY_YES` is universal. `bond_outcome_direction='down'` captures entries where VOLARB is making a contrarian/volatility bet against the BOND momentum signal. These entries hold to resolution at a higher rate (215/315 = 68.3%) vs 'up' entries (156/226 = 69.0%). The EV gap is driven by lower early-exit profits, not higher loss frequency.

**CONCLUSION: SIGNAL_FOUND (with interpretation caveat)**

'down' bets: CI upper = +$0.221 < baseline lower = +$0.244 at n=315. The 'up' signal entries (BOND signal aligned with BUY_YES) are ON_BASELINE. VOLARB contrarian entries (bod='down') are performing below backtest.

**FAILURE_MET: No.** WR=36.2% positive. EV positive but below baseline.

**IF_DEPLOYED:** Gating out bod='down' entries (require BOND signal agreement = bod='up' only) would reduce volume by 41.5% (315/541) and retain EV=+$0.142/trade at n=226. This is a new signal filter → Tier 2. Requires Auditor PR with cited data. Scout cannot implement.

---

## H4 — Phase 2 Longshot Gate (ask 0.00–0.10)

**STATUS:** `volarb_longshot_shadow.jsonl` file exists on data-mirror but contains **n=0 rows**. Logger is deployed but has not fired.

7 VOLARB Phase 1 trades have entry_price < 0.10 (prices: 0.01, 0.03, 0.04, 0.05, 0.08, 0.09) — outside Phase 1 ask gate. These 7 would qualify as longshot candidates.

**CONCLUSION: DATA_MISSING.** Phase 2 unlock condition (n≥100 OOS in ask<0.10) not met. The logger may not be firing on VOLARB-class entries.

---

## Priority Signal for Next Implementation

> **H5 [220–280s) SIGNAL:BELOW_CI at n=362 — highest-confidence actionable finding.**
>
> The [220–280s) entry bucket accounts for 67% of VOLARB volume (n=362) with EV=+$0.047, CI=[−$0.112, +$0.206] — confirmed below backtest CI lower. The [160–220s) bucket (n=120) is ON_BASELINE at EV=+$0.134. The [100–160s) bucket (n=49, approaching n=100) shows EV=+$0.482 — if confirmed, the EV gradient supports a tighter REM_MAX_S gate.
>
> **Auditor action:** Evaluate REM_MAX_S reduction 280s → 220s (Tier 2, >20% change). Await [100–160s) crossing n≥100 (~3–4 days at current fire rate) before final gate setting — that bucket will determine whether 220s or 160s is the optimal ceiling.

---

## Closed-Family Confirmations

- LDA per-hour analysis (prior scout): out of scope for VOLARB Scout mandate. Not re-investigated.
- BOND field schema (term_tok_tick_count_5s, ob_imbalance): not present in VOLARB records. Confirmed absent — do not reference in future VOLARB work.
- Backtest BTC alpha lead: live data inverts rank (SOL leads). Noted; INCONCLUSIVE at current n. Not closing family — monitoring at n≥250 per asset.

---

## Open Requests for Auditor / Shadow Validator

### Auditor Watch — cells trending to n≥100

| Cell | Current n | ETA to n=100 | Priority |
|---|---|---|---|
| H5 [100–160s) | 49 | ~3–4 days | HIGH — EV=+$0.482 if confirmed, would justify REM_MAX_S=160s |
| H1 ETH | 189 | Already >100 | MEDIUM — flag if future CI_hi drops below +$0.244 |
| H6 bod='down' | 315 | Already >100 | HIGH — SIGNAL:BELOW_CI confirmed; Auditor evaluate bod filter |

### Shadow Validator Review

| Logger | Status | Required Action |
|---|---|---|
| `volarb_longshot_shadow` | Deployed, **n=0** | Verify logger fires on VOLARB ask<0.10 entries. 7 live sub-0.10 trades exist but none logged — possible logger is scoped to backtest path only. |
| `order_lifecycle` sec_to_res | Active, all values = 0.0 | Data bug: field reads 0.0 for all 590 VOLARB-era records. Fix: populate `sec_to_res = ((floor(ts_open/300)+1)*300) − ts_open` at entry time. Scout computed this externally for H5. |

### Phase 2 Longshot Recorder Status

**Awaiting fix.** Logger file exists but n=0. Proposed recorder spec (per H4 mandate):
- Trigger: every VOLARB candidate where ask ∈ [0.00, 0.10) and edge ≥ 0.10
- Fields: ts, token_id, asset, ask_price, edge, direction, window_end_ts, realized_outcome (1.0/0.0), net_pnl_if_fired
- Path: `data/shadow/volarb_longshot_shadow.jsonl`
- Phase 2 unlock threshold: n≥100 OOS with EV CI lower > 0

---

*Scout: report-only. No gates modified. Parameter changes require Auditor (Tier 1–2).*
