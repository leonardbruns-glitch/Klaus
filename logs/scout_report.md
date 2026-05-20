# VOLARB Alpha Scout — 2026-05-20T00:42 UTC

## Snapshot + Baseline

| Field | Value |
|---|---|
| snapshot_ts | 2026-05-20T00:27:56Z (age: 14.5 min — FRESH) |
| snapshot_age_check | PASS (< 45 min) |
| integrity_report.json | ABSENT — treated as non-blocking |
| Klaus capital | $130.564 |
| Klaus service | active |
| VOLARB n (live era, all) | 887 |
| VOLARB n (Phase 1 gate: ask ∈ [0.10,0.60), deduplicated) | **875** |
| Live era start | 2026-05-16T21:00 UTC (ts=1778965200) |
| Data window | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (~58h) |
| Dedup method | first-fire per token_id — 0 duplicates |
| $1-equiv baseline CI | [+$0.244, +$0.352] / trade |

### Global Live EV (Phase 1 Gate, n=875)

| Metric | Value | vs Baseline |
|---|---|---|
| WR | 35.0% | Below 40% target; above 30% kill floor |
| EV / $1 stake | +$0.052 | **CI upper = +$0.156 < baseline CI lower = +$0.244** |
| 95% CI | [−$0.053, +$0.156] | **SIGNAL:BELOW_CI globally** |
| sum(net_pnl) | +$45.19 | Down from +$74.79 at prior scout (n=547) → recent trades net negative |
| Prior scout global EV | +$0.092 (n=541) | Degraded to +$0.052 at n=875 |

> **Global signal hardening.** CI upper fell from +$0.230 (prior scout, n=541) → +$0.156 (current, n=875). The strategy is underperforming backtest at increasing statistical confidence.

---

## Continuity vs Prior Scout

| Item | Status |
|---|---|
| Prior scout | 2026-05-17T12:42 UTC, n=541 (543 after Phase 1 filter) |
| Investigations carried over | H5 (SIGNAL_FOUND), H6 (SIGNAL_FOUND — direction asymmetry), H1 (INCONCLUSIVE → promote) |
| Resolved/closed since prior | None |
| New findings this cycle | ETH crossed BELOW_CI at n=301; 'up' direction degraded; sniper_edge=0 data integrity flag |

---

## Investigation H5 — Seconds-to-Resolution Slice *(SIGNAL_FOUND — CONFIRMED STRENGTHENED)*

**HYPOTHESIS:** The [220–280s) entry bucket drives global underperformance. Prior scout found SIGNAL:BELOW_CI at n=362.

**METHOD:** Compute sec_to_res = next_window_boundary − ts_open. Bucket into [60–100s), [100–160s), [160–220s), [220–280s). EV/$1 (net_pnl/stake), WR, 95% CI vs baseline [+$0.244, +$0.352]. n≥100 required for STATUS verdict.

**RESULT:**

| sec_to_res at entry | n | WR | EV/$1 | CI_lo | CI_hi | STATUS |
|---|---|---|---|---|---|---|
| [60–100s) | 8 | 12.5% | −$0.654 | −$1.341 | +$0.033 | INCONCLUSIVE |
| [100–160s) | 62 | 33.9% | +$0.353 | −$0.186 | +$0.892 | INCONCLUSIVE |
| [160–220s) | **186** | 37.1% | +$0.128 | −$0.108 | +$0.363 | ON_BASELINE |
| [220–280s) | **617** | 34.8% | +$0.011 | −$0.107 | +$0.129 | **SIGNAL:BELOW_CI** |

> **Signal hardened.** [220–280s) CI upper dropped from +$0.206 (prior, n=362) → +$0.129 (current, n=617). This bucket is 70.5% of all Phase 1 trades and is the primary drag on global EV. The [160–220s) bucket (n=186) remains ON_BASELINE at EV=+$0.128 — its CI crosses the baseline range, meaning trades entered 160–220s before resolution are performing as expected.

**CONCLUSION: SIGNAL_FOUND** (confirmed from prior scout, statistically stronger)

**FAILURE_MET: No.** The [220–280s) bucket is definitively below backtest CI but is not a kill-switch condition. WR=34.8% remains above the 30% kill floor.

**IF_DEPLOYED:** Tightening REM_MAX_S from 280s → 220s eliminates the [220–280s) drag (n=617, EV=+$0.011). Retained pool: n≈248 ([100–220s)), all at ON_BASELINE or better. Trade volume falls ~70%. This is a >20% parameter change → Tier 2. Auditor authority only.

---

## Investigation H1 — Per-Asset Alpha Re-Allocation *(SIGNAL_FOUND — ETH NEW)*

**HYPOTHESIS:** Live per-asset EV has diverged from backtest projections. ETH watchlisted by prior scout at n=189 for potential SIGNAL:BELOW_CI. Validate at current n.

**METHOD:** Filter Phase 1 by `asset`. EV/$1, WR, 95% CI. Compare vs baseline [+$0.244, +$0.352].

**RESULT:**

| Asset | n | WR | EV/$1 | CI_lo | CI_hi | vs_baseline_CI |
|---|---|---|---|---|---|---|
| BTC | 282 | 33.0% | +$0.064 | −$0.128 | +$0.257 | ON_BASELINE |
| ETH | **301** | 32.9% | −$0.018 | −$0.193 | **+$0.156** | **SIGNAL:BELOW_CI** |
| SOL | 292 | 39.0% | +$0.112 | −$0.065 | +$0.288 | ON_BASELINE |

**Trajectory (prior vs recent ~60h):**

| Asset | Prior n | Prior EV | Recent n | Recent EV | Drift z |
|---|---|---|---|---|---|
| ETH | 191 | +$0.010 | 110 | −$0.067 | 0.44 (stable — was already negative) |
| SOL | 183 | +$0.192 | 109 | −$0.023 | **1.15** (deteriorating) |
| BTC | 173 | +$0.083 | 109 | +$0.035 | 0.24 (stable) |

**CONCLUSION: SIGNAL_FOUND** (ETH crosses BELOW_CI at n=301; prior scout predicted this at n≥250)

ETH CI upper (+$0.156) is below baseline CI lower (+$0.244). No per-asset block lever exists in Phase 1 — the only actionable response is raising EDGE_FLOOR globally (Tier 2). SOL drift z=1.15 is pre-signal; flag for Auditor watchlist at n≥300. BTC remains ON_BASELINE.

**FAILURE_MET: No.** ETH WR=32.9% is above 30% floor. No individual asset triggers kill switch.

**IF_DEPLOYED:** No direct lever; only global EDGE_FLOOR increase (Tier 2, Auditor). Eliminating ETH trades would remove n=301 (34.4% of volume) but no explicit asset gate exists.

---

## Investigation H7 — Watchlist Cell Trajectories *(SIGNAL_FOUND — 'up' direction degraded)*

**HYPOTHESIS:** Cells signaled in prior scout (H5 [220–280s), H6 direction='down') may have stabilized or worsened. New development: 'up' direction degraded from ON_BASELINE → BELOW_CI.

**METHOD:** Split at prior scout cutoff (2026-05-17T12:42 UTC). Prior era n=547; recent (~60h) n=328. Compute cell EV and 95% CI for each period. Flag cells where |delta_EV| > 2σ pooled SE.

**RESULT:**

| Cell | Prior n | Prior EV | Prior STATUS | Recent n | Recent EV | Recent STATUS | Drift z |
|---|---|---|---|---|---|---|---|
| [220–280s) | 368 | +$0.051 | BELOW_CI | 249 | −$0.048 | BELOW_CI | **0.83** |
| direction='up' | 226 | +$0.142 | ON_BASELINE | 157 | −$0.147 | BELOW_CI | **1.67** |
| direction='down' | 321 | +$0.059 | BELOW_CI | 171 | +$0.100 | ON_BASELINE | −0.30 |
| asset=ETH | 191 | +$0.010 | BELOW_CI | 110 | −$0.067 | BELOW_CI | 0.44 |
| asset=SOL | 183 | +$0.192 | ON_BASELINE | 109 | −$0.023 | ON_BASELINE | 1.15 |

**Rolling EV by 100-trade chunk (chronological):**

| Chunk | Mid date | n | EV/$1 | WR |
|---|---|---|---|---|
| [1–100] | 05-16T22:21 | 100 | +$0.040 | 39% |
| [101–200] | 05-17T01:06 | 100 | **+$0.564** | 44% |
| [201–300] | 05-17T03:51 | 100 | +$0.046 | 38% |
| [301–400] | 05-17T06:36 | 100 | **−$0.217** | 23% |
| [401–500] | 05-17T10:00 | 100 | +$0.146 | 32% |
| [501–600] | 05-17T12:50 | 100 | −$0.012 | 34% |
| [601–700] | 05-17T15:36 | 100 | **−$0.176** | 27% |
| [701–800] | 05-18T11:11 | 100 | +$0.073 | 41% |
| [801–875] | 05-19T01:41 | 75 | −$0.017 | 37% |

**CONCLUSION: SIGNAL_FOUND** (direction='up' cell crossed from ON_BASELINE → BELOW_CI; z=1.67, approaching 2σ)

- [220–280s): STABLE at BELOW_CI — no additional deterioration, signal confirmed.
- direction='up': **NEW degradation** — prior ON_BASELINE → now BELOW_CI in recent 60h. z=1.67 is pre-2σ but trending. WR dropped 32.7% → 28.0% in recent era.
- direction='down': **IMPROVING** from BELOW_CI → ON_BASELINE in recent 60h. The 'down' H6 signal from prior scout may be resolving.
- SOL: drift z=1.15 — not yet 2σ but EV swung from +$0.192 → −$0.023 in recent period.
- Rolling EV: no secular trend; variance is high. Chunks [301–400] and [601–700] were loss-heavy.

**FAILURE_MET: No.** No cell exceeds 2σ drift. direction='up' at z=1.67 warrants Auditor watchlist.

**IF_DEPLOYED:** N/A — z<2σ; still SIGNAL_FOUND but below threshold for direction-split gating.

---

## Additional Findings (not primary investigations)

### H3 — Per-Ask-Band (supplemental)

| Band | n | EV/$1 | STATUS |
|---|---|---|---|
| [0.10,0.20) | 91 | +$0.160 | INCONCLUSIVE |
| [0.20,0.30) | 227 | −$0.006 | **BELOW_CI** |
| [0.30,0.40) | 390 | +$0.068 | **BELOW_CI** |
| [0.40,0.50) | 158 | +$0.044 | **BELOW_CI** |
| [0.50,0.60) | 9 | −$0.158 | INCONCLUSIVE |

All three n≥100 bands are BELOW_CI. The underperformance is not isolated to a specific ask range — it is uniform across the Phase 1 gate. This corroborates the global SIGNAL:BELOW_CI and the H5 finding that entry timing (not ask level) is the primary EV driver.

### H4 — Phase 2 Longshot Gate (DATA_MISSING)

`volarb_longshot_shadow.jsonl` is **ABSENT** from the shadow manifest (confirmed: no logger registered in shadow_summary.json post-activation). Shadow loggers present post-activation: binance_trade, discover_signal, exit_policy_shadow, gate_trace, hold_path, market_timeline, ob_delta, order_lifecycle, shadow_telemetry, token_trade, wallet_shadow, window_resolution.

**Proposed recorder spec:**
- **Source:** `strategy/volarb.py` entry point, after gate evaluation
- **File:** `data/shadow/volarb_longshot_shadow.jsonl`
- **Trigger:** Every market_timeline row where: `ask < 0.10 AND sniper_edge >= 0.10 AND rem_s ∈ [60,280]` (would have fired at ASK_FLOOR=0.0)
- **Required fields:** `{ts, token_id, asset, entry_price_would_be, sniper_edge, rem_s, window_end_ts, realized_outcome_price, net_pnl_would_be}`
- **Pre-registered n threshold:** n=100 before Shadow Validator analyzes
- **Status: NOT DEPLOYED — requires Tier 2 build**

### Data Integrity Flag: sniper_edge = 0.000 for all VOLARB trades

`sniper_edge` is 0.000 for all 875 Phase 1 VOLARB records (min=max=mean=0). This field should contain the VOLARB edge score per the strategy spec (EDGE_FLOOR=0.15). Either the field is written as a separate field (possibly `sniper_pm_ask_at_trigger` is the edge proxy), or the field is not being populated for VOLARB fills. This does not affect the current analysis (which uses `net_pnl`), but blocks future edge-bucketing studies. Recommend Auditor verify field routing in `strategy/volarb.py`.

### H2 — Per-Hour EV (supplemental, all INCONCLUSIVE)

Notable hours approaching significance:
- H05 (n=35): EV=−$0.539, CI=[−$0.928, −$0.150] — both bounds negative; would be BELOW_CI at n≥100
- H16 (n=30): EV=−$0.556, CI=[−$0.960, −$0.152] — same pattern
- H01 (n=66): EV=+$0.538, CI=[+$0.089, +$0.988] — would be ABOVE_CI at n≥100
- All hours INCONCLUSIVE. H05 and H16 are watchlist candidates at n≥40 each.

---

## Priority Signal for Next Implementation

**Strongest confirmed signal: H5 — [220–280s) entry timing**
- n=617, EV=+$0.011, CI upper +$0.129 < baseline lower +$0.244
- Signal hardens every cycle (prior CI upper was +$0.206, now +$0.129)
- 70.5% of trade volume is in this bucket; it explains the global BELOW_CI

**Secondary signal: H1 — ETH asset**
- n=301, EV=−$0.018, CI upper +$0.156 < baseline lower +$0.244
- Prior scout predicted this crossing; confirmed

**Pre-signal watchlist:**
- direction='up': z=1.67 (→ 2σ threshold at ~n=200 more recent trades)
- SOL: z=1.15 recent deterioration (promote to watchlist from ON_BASELINE)
- H05/H16 UTC hours: EV < 0, approaching significance at n≥100

> Both H5 and H1 findings require Tier 2 action (Auditor). Scout cannot implement.

---

## Closed-Family Confirmations (null re-validated)

- direction='down' asymmetry: RESOLVING — recent 60h ON_BASELINE. Prior BELOW_CI signal weakening. Do not re-investigate without fresh data.
- BTC asset: stable ON_BASELINE at n=282; no deviation. Re-validate at n≥350.
- Per-ask-band: uniform BELOW_CI confirms issue is not band-specific; H3 investigation can be CLOSED as contributing finding rather than actionable signal.

---

## Open Requests for Auditor / Shadow Validator

### Auditor watch (cells trending to n≥100 in next 24h)

| Cell | Current n | Est. daily fill rate | ETA to n≥100 |
|---|---|---|---|
| [100–160s) bucket | 62 | ~15–20/day | ~2–3 days |
| H01 UTC (ABOVE_CI candidate) | 66 | ~10–15/day | ~2–4 days |
| H05 UTC (BELOW_CI candidate) | 35 | ~6–10/day | ~7 days |
| direction='up' recent era | 157 | ~25/day | Already ≥100; re-check z-score in next scout |

**Priority Auditor action:** H5 [220–280s) SIGNAL_FOUND at n=617 and ETH SIGNAL_BELOW_CI at n=301 both exceed n≥100 threshold. Auditor Tier 2 review of REM_MAX_S and EDGE_FLOOR warranted.

### Shadow Validator (loggers past threshold)

- No VOLARB-specific shadow loggers are registered post-activation
- `exit_policy_shadow.jsonl` (2026-05-16 to 2026-05-20) has n≥2428 rows — Shadow Validator may run VOLARB-era exit analysis if schema aligns

### Phase 2 longshot recorder

**Status: NOT DEPLOYED.** Recorder spec above (H4 section). Requires Tier 2 build before Phase 2 gate evaluation can proceed. Pre-registered n threshold: 100 OOS trades in ask<0.10 cell.
