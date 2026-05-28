# VOLARB Alpha Scout — 2026-05-28T12:46Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-28T12:31:13Z (~15 min old — FRESH) |
| Klaus state | active (bankroll $95.304, bankroll.json saved_ts 2026-05-28T12:25:51Z) |
| Klaus HEAD | 26cec6db |
| Capital | $95.304 |
| VOLARB n (live era, bond_entry_class=='VOLARB', is_live=True, ts_open ≥ 1778965200) | **887 — FROZEN 9.4 days** |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~15 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as **PASS** (consistent with all prior cycles)
- Last Scout commit: prior cycle 2026-05-28T00:42Z (~12h ago, ≥8h threshold) — **PROCEED**
- CODE_DESYNC: VOLARB retired (last trade 2026-05-19T02:50Z); LDA is now active strategy (n=1081 trades) — **N/A for VOLARB post-mortem**
- Delta vs prior scout: **Δn=0, dataset fully frozen** — all cell statistics identical to prior cycle

**Aggregate VOLARB ($1-equiv, kline_pnl, kline_pnl>0 WR — canonical per research_status.md §1):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (kline_pnl>0) | 31.6% (277/876) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| 12h delta n | 0 | frozen |
| Days since last trade | 9.4 | — |

**Note on WR vs prior scout:** Prior cycle reported WR=34.6% using net_pnl>0 (307/887). Canonical metric per research_status.md §1 is kline_pnl; correct WR=31.6% (277/876 kn). Both confirm far-below-CI performance; no change to conclusions.

---

## Continuity vs Prior Scout (2026-05-28T00:42Z, ~12h ago)

**Investigations carried over (zero-delta confirmed):**
- H1 (per-asset alpha): DISCARD cycle 2. All assets BELOW_CI. Reproduced below (cycle 3 terminal confirm).
- H3 (per-ask-band): DISCARD cycle 2. All n≥100 bands BELOW_CI. Reproduced below (cycle 3 terminal confirm).
- H7 (watchlist trajectories): CONFIRMED CLOSED cycle 2. All cells zero-delta.

**Resolved/closed since prior:**
- H5 (seconds-to-resolution): DISCARD confirmed prior cycle. Re-run this cycle with proxy method; confirms DISCARD.
- H6 (direction asymmetry): DISCARD confirmed prior cycle. Re-confirmed zero-delta.
- H4 (longshot Phase 2): MOOT confirmed prior cycle. Re-confirmed shadow file = 0 bytes.

**New investigations this cycle:** H5 first full proxy run (term_remaining_s field absent, proxy via ts_open mod 300).

---

## Investigations

### H1: Per-Asset Alpha

- **HYPOTHESIS:** Per-asset kEV divergence may reveal whether any individual asset met the baseline CI=[+$0.244,+$0.352]/trade. BTC was highest-performing in backtest projection.
- **METHOD:** Slice VOLARB (n=887, kn=876) by `asset`. kEV = kline_pnl/stake (normalised to $1-equiv). CI95 normal approx. Dedup by first-fire trade_id. n<100 = INCONCLUSIVE.
- **RESULT:**

| Asset | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | Δn vs prior |
|---|---|---|---|---|---|---|---|---|
| BTC | 286 | 283 | 31.1% | +$0.039 | −$0.159 | +$0.237 | **BELOW_CI** | 0 |
| ETH | 305 | 301 | 30.2% | −$0.075 | −$0.245 | +$0.095 | **BELOW_CI** | 0 |
| SOL | 296 | 292 | 33.6% | −$0.030 | −$0.202 | +$0.142 | **BELOW_CI** | 0 |

- **CONCLUSION: DISCARD (terminal re-confirm, cycle 3).** All three assets n≥100. All CI_hi below baseline lower (+$0.244). BTC best (kEV=+$0.039, CI_hi=+$0.237 — marginally below floor). ETH worst (kEV=−$0.075). Dataset frozen — will not change. Corrected WR (kline_pnl basis): BTC 31.1%, ETH 30.2%, SOL 33.6% (vs prior cycle's net_pnl-based: BTC 32.9%, ETH 32.5%, SOL 38.5%).
- **FAILURE_MET:** Yes — all three n≥100 assets BELOW_CI.
- **IF_DEPLOYED:** N/A — strategy retired.

---

### H3: Per-Ask-Band EV

- **HYPOTHESIS:** Specific ask-price bands may show positive kEV despite negative aggregate. Tighter ASK_CEIL gate could rescue EV if a contiguous range is positive.
- **METHOD:** Slice by entry_price bands. n<100 = INCONCLUSIVE.
- **RESULT:**

| Ask Band | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | Decision |
|---|---|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 91 | 15.4% | +$0.032 | −$0.480 | +$0.544 | STRADDLES_CI | n<100 → **INCONCLUSIVE** |
| [0.20, 0.30) | 227 | 227 | 24.7% | −$0.053 | −$0.273 | +$0.166 | **BELOW_CI** | n≥100, flagged |
| [0.30, 0.40) | 390 | 382 | 35.6% | +$0.010 | −$0.128 | +$0.147 | **BELOW_CI** | n≥100, flagged (dominant; 44% of volume) |
| [0.40, 0.50) | 158 | 156 | 42.9% | −$0.007 | −$0.189 | +$0.175 | **BELOW_CI** | n≥100, flagged |
| [0.50, 0.60) | 9 | 8 | 37.5% | −$0.282 | −$0.974 | +$0.410 | STRADDLES_CI | n<100 → **INCONCLUSIVE** |

- **CONCLUSION: DISCARD (terminal re-confirm, cycle 3).** All n≥100 bands BELOW_CI. [0.30,0.40) is dominant band (n=390, 44% of entries), kEV=+$0.010 technically positive but CI_hi=+$0.147 well below +$0.244 baseline floor. [0.10,0.20) (n=91): WR=15.4% — near-total adverse selection in deep-longshot territory; will never reach n=100 (strategy retired). No ask-gate tightening could salvage strategy.
- **FAILURE_MET:** Yes — all n≥100 bands BELOW_CI.
- **IF_DEPLOYED:** N/A — strategy retired.

---

### H5: seconds_to_resolution Slice (Entry Timing)

- **HYPOTHESIS:** Entries with more time remaining may have higher EV due to Chainlink heartbeat and liquidity effects. A "sweet spot" time-remaining band may show positive kEV.
- **METHOD:** `term_remaining_s` field exists in VOLARB records but is all-zero (field not populated in VOLARB-era code). `sniper_lag_remaining` also all-zero. Proxy: `rem_at_entry = 300 - (ts_open mod 300)` approximates seconds-to-window-close at entry. Bands per spec: [60,100), [100,160), [160,220), [220,280)s. n<100 = INCONCLUSIVE.
- **DATA NOTE:** Exact `term_remaining_s` field: DATA_MISSING (all zeros). Proxy via window position used as best approximation. Proxy fidelity limited: assumes entries land uniformly in window; actual signal latency may add 5–30s offset. Treat proxy results with caution.
- **RESULT:**

| rem_at_entry band (proxy) | n | kn | WR% | kEV/$1 | CI95 lower | CI95 upper | vs_CI | Decision |
|---|---|---|---|---|---|---|---|---|
| [60, 100)s | 14 | 14 | 0.0% | −$1.061 | −$1.147 | −$0.975 | N/A | n<100 → **INCONCLUSIVE** |
| [100, 160)s | 65 | 64 | 29.7% | +$0.221 | −$0.298 | +$0.740 | STRADDLES_CI | n<100 → **INCONCLUSIVE** |
| [160, 220)s | 187 | 187 | 33.2% | +$0.044 | −$0.192 | +$0.279 | STRADDLES_CI | n≥100 — STRADDLES, CI too wide |
| [220, 280)s | 619 | 609 | 32.2% | −$0.042 | −$0.160 | +$0.076 | **BELOW_CI** | n≥100, flagged |

- **Distribution note:** 70% of entries (619/887) land in [220,280)s band — late-window entries dominate. Only 14 entries in [60,100)s (near-deadline) and 65 in [100,160)s.

- **CONCLUSION: DISCARD.** Dominant band [220,280)s (n=619): BELOW_CI — kEV=−$0.042, CI_hi=+$0.076 well below +$0.244 floor. [160,220)s (n=187): STRADDLES_CI — kEV=+$0.044, CI_hi=+$0.279 technically above CI lower (+$0.244) but CI very wide and kEV point estimate is +$0.044 — no actionable signal. Dataset frozen — no additional data will accrue. The proxy method itself adds uncertainty.
- **FAILURE_MET:** Yes for dominant band [220,280)s. [160,220)s straddles — not a SIGNAL_FOUND (kEV too low, CI too wide, proxy uncertainty, frozen dataset).
- **IF_DEPLOYED:** N/A — strategy retired. Restricting to rem_at_entry∈[160,220)s (n=187, 21% of entries) at kEV=+$0.044/$1 would not clear the baseline even under optimistic CI.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — continue collecting (n=887 FROZEN).**

VOLARB is permanently retired. All investigations are terminal post-mortem confirms:
- H1 per-asset: DISCARD (cycle 3) — zero delta, all assets BELOW_CI
- H3 per-ask-band: DISCARD (cycle 3) — zero delta, all n≥100 bands BELOW_CI
- H5 entry timing proxy: DISCARD (cycle 1 full run) — dominant band BELOW_CI, straddle band has insufficient kEV

No VOLARB-targeted implementation is warranted. Active strategy is LDA.

---

## Closed-Family Confirmations (This Cycle)

| Family | Prior Status | Re-confirmed this cycle |
|---|---|---|
| H1 per-asset (VOLARB) | DISCARD cycle 2 | DISCARD cycle 3 — zero delta, all BELOW_CI |
| H3 per-ask-band (VOLARB) | DISCARD cycle 2 | DISCARD cycle 3 — zero delta, all BELOW_CI |
| H7 watchlist trajectories | CONFIRMED CLOSED cycle 2 | CONFIRMED CLOSED cycle 3 — zero delta |
| H6 direction asymmetry (VOLARB) | DISCARD cycle 1 | Re-confirmed: up kEV=−$0.029, down kEV=−$0.019, both BELOW_CI, zero delta |
| H4 longshot Phase 2 (VOLARB) | MOOT cycle 2 | MOOT cycle 3 — shadow_volarb_longshot_shadow.jsonl = 0 bytes, absent from shadow_summary |
| H5 seconds-to-resolution (VOLARB) | DISCARD prior cycle (term_remaining_s all-zero) | DISCARD confirmed — proxy analysis: dominant band [220,280) BELOW_CI, DATA_MISSING for exact field |

---

## Open Requests for Auditor / Shadow Validator

**VOLARB-specific:**
- No cells trending to n≥100: dataset frozen at 887, strategy retired 2026-05-19.
- No shadow loggers for VOLARB past threshold: volarb_longshot_shadow.jsonl = 0 bytes, never deployed.
- Phase 2 longshot recorder: MOOT — strategy retired, no build needed.

**Active strategy context (LDA) — observations for human review:**
- `exit_policy_shadow` is active at ~2,300–2,600 rows/day (hot/2026-05-2x/). Has crossed 500-row threshold per §5. Shadow Validator should validate this logger.
- **NEW LOGGERS NOT IN research_status.md §5 manifest (flag for human review):**
  - `stwa_signals.jsonl`: n=11,811 (2026-05-27), n=16,400 (2026-05-28 partial). Active, significant volume. STWA = new sub-system?
  - `stwa_state.jsonl`: n=36,216 (2026-05-27), n=53,244 (2026-05-28 partial). Active, high volume.
  - `m1_beta_probe.jsonl`: n=28 (05-26), n=76 (05-27), n=30 (05-28 partial). Beta probe for M1 strategy?
  - `metar_lockout.jsonl`: n=9,000–11,700/day. Weather-related lockout system.
  - `ladder.jsonl`: n=1–34/day. Small volume.
  - None of these appear in research_status.md §5 manifest — **manifest is stale**.
- `order_lifecycle.jsonl` (today): n=22 — healthy, orders placing.
- `discover_signal.jsonl` (today): n=94 — active discovery. Note: DISCOVER strategy is OFF per §2; these may be orphaned or used for signal monitoring.

---

*Report generated by Klaus Alpha Scout | VOLARB data frozen 2026-05-19T02:50Z | Active strategy: LDA | snapshot_ts: 2026-05-28T12:31:13Z*
