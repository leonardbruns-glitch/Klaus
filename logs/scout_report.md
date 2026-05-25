# VOLARB Alpha Scout — 2026-05-25T00:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-25T00:38:13Z (~4 min old — FRESH) |
| Klaus state | active (LDA/WEATHER strategy per lda_status.txt) |
| Klaus HEAD | 273dee64 |
| Capital | $31.363007 (bankroll.json) |
| VOLARB n (live era, all is_live==True) | **887 — FROZEN** (unchanged since 2026-05-19 02:50 UTC) |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight:**
- snapshot_ts age: ~4 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as PASS (no `blocks_agent_run`)
- Last scout: 2026-05-24T00:47Z (~23h 55m ago — > 8h threshold, proceed)
- CODE_DESYNC check: not applicable (VOLARB retired; no active gate branch to diff)

**⚠ VOLARB IS RETIRED — POST-MORTEM ONLY.**
Strategy last fired 2026-05-19 02:50 UTC (6.0 days ago). All subsequent trades are WEATHER/LDA.
VOLARB n is permanently frozen at 887. No gate changes are possible or actionable.

**Aggregate VOLARB performance (final — stake-normalised $1-equiv):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| WR (net_pnl>0) | 34.6% (307/887) | below 40% backtest expectation |
| EV/trade ($1-equiv, net_pnl/stake) | +$0.038 | CI=[−$0.065, +$0.142] — BELOW baseline CI lower |
| EV/trade ($1-equiv, kline_pnl/stake) | −$0.023 | resolution metric — negative |
| Profit factor | 1.055 | above 0.8 kill-switch floor |
| Fee bleed | 1.8% of gross wins | well below 20% ceiling |
| kline vs net divergence | −$81.63 | PROFIT_TARGET mark-to-market ≠ resolution |
| Total net_pnl | +$49.82 | across 2.2 days |

**Exit reason breakdown (n=887):**

| Exit Reason | n | WR% | EV/stake |
|---|---|---|---|
| BOND_RESOLVED_NO | 575 | 0.0% | −$1.008 |
| PROFIT_TARGET | 267 | 100.0% | +$2.071 |
| VOLARB_KLINE_WIN | 17 | 100.0% | +$2.283 |
| WINDOW_OUTCOME | 9 | 100.0% | +$2.127 |
| VOLARB_TP20 | 8 | 100.0% | +$0.244 |
| INVERTED_TP | 6 | 100.0% | +$0.795 |
| BOND_TIME_EXIT | 3 | 0.0% | −$0.708 |
| BOND_EXPIRED_UNSOLD | 1 | 0.0% | −$1.000 |

64.8% of VOLARB positions resolved as BOND_RESOLVED_NO (expiry at zero). All net_pnl "wins" came from early exits — none from holding to resolution. This confirms the kline/net divergence: PROFIT_TARGET exits captured mark-to-market gains that later reversed; kline_pnl (−$0.023/$1) is the resolution-correct metric.

---

## Continuity vs Prior Scout (2026-05-24T00:47Z)

**Investigations carried over from prior scout:**
- H1 (per-asset): ETH confirmed BELOW_CI at n=305; BTC marginal WITHIN_CI; SOL WITHIN_CI. H7 this cycle adds 24h trajectory comparison.
- H3 (per-ask-band): All three n≥100 bands ([0.20,0.30), [0.30,0.40), [0.40,0.50)) confirmed BELOW_CI. Frozen.
- H6 (direction asymmetry): Both 'up' and 'down' confirmed BELOW_CI at n≥100. 'Up' stronger drag. Frozen.

**Resolved/closed since prior scout:**
- H5 (term_remaining_s logging bug) — closed by prior; re-confirmed DATA_MISSING this cycle (all 887 rows have term_remaining_s=0).
- All three prior SIGNAL_FOUND families (H1/ETH, H3/all-bands, H6/both-directions) now treated as permanent post-mortem findings.

**Investigations selected this cycle: H2, H4, H7** (H2 and H4 are new; H7 adds 24h trajectory comparison not done by prior).

---

## Investigation H2 — Per-Hour EV Breakdown

**HYPOTHESIS:** The backtest found no hours warranting a block gate. Live VOLARB data, spread across 53.8 hours, may reveal specific UTC hours with concentrated negative EV, flagging hour-level gates for a potential VOLARB Phase 2.

**METHOD:** Slice 887 VOLARB trades by hour_utc. Compute n, WR, EV/stake (net_pnl/stake), kEV/stake (kline_pnl/stake), CI95. Flag hours with n≥100 and CI upper < +$0.244. n<100 = INCONCLUSIVE.

**RESULT (all 23 UTC hours with VOLARB data):**

| Hour | n | WR% | EV/$1 | kEV/$1 | CI95_lo | CI95_hi | vs_baseline_CI |
|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9% | +0.305 | −0.053 | −0.292 | +0.902 | n<100 (39) |
| H01 | 66 | 48.5% | +0.538 | +0.389 | +0.089 | +0.988 | n<100 (66) |
| H02 | 64 | 40.6% | +0.133 | +0.064 | −0.217 | +0.483 | n<100 (64) |
| H03 | 37 | 43.2% | +0.188 | +0.120 | −0.270 | +0.647 | n<100 (37) |
| H04 | 37 | 32.4% | −0.084 | −0.001 | −0.531 | +0.364 | n<100 (37) |
| H05 | 35 | 14.3% | −0.539 | −0.536 | −0.928 | −0.150 | n<100 (35) |
| H06 | 36 | 30.6% | −0.034 | −0.135 | −0.532 | +0.465 | n<100 (36) |
| H07 | 31 | 19.4% | −0.267 | −0.332 | −0.884 | +0.349 | n<100 (31) |
| H08 | 35 | 28.6% | +0.394 | +0.256 | −0.423 | +1.211 | n<100 (35) |
| H09 | 28 | 14.3% | −0.456 | −0.452 | −0.973 | +0.061 | n<100 (28) |
| H10 | 38 | 34.2% | +0.010 | −0.061 | −0.469 | +0.489 | n<100 (38) |
| H11 | 71 | 35.2% | +0.086 | +0.097 | −0.298 | +0.470 | n<100 (71) |
| H12 | 36 | 36.1% | +0.006 | −0.226 | −0.471 | +0.483 | n<100 (36) |
| H13 | 36 | 33.3% | +0.007 | +0.017 | −0.486 | +0.500 | n<100 (36) |
| H14 | 47 | 29.8% | −0.190 | −0.249 | −0.560 | +0.180 | n<100 (47) |
| H15 | 36 | 30.6% | +0.135 | +0.154 | −0.480 | +0.749 | n<100 (36) |
| H16 | 30 | 16.7% | −0.556 | −0.551 | −0.960 | −0.152 | n<100 (30) |
| H17 | 21 | 38.1% | −0.079 | −0.242 | −0.638 | +0.480 | n<100 (21) |
| H18 | 25 | 60.0% | +0.218 | +0.685 | −0.272 | +0.708 | n<100 (25) |
| H20 | 3 | 100.0% | +1.591 | +1.617 | +1.453 | +1.728 | n<100 (3) |
| H21 | 39 | 51.3% | +0.304 | +0.257 | −0.122 | +0.730 | n<100 (39) |
| H22 | 40 | 32.5% | −0.123 | −0.193 | −0.530 | +0.284 | n<100 (40) |
| H23 | 57 | 33.3% | −0.007 | −0.043 | −0.395 | +0.381 | n<100 (57) |

Maximum per-hour n: H11=71. No hour reaches n≥100.

**Archival flagging (n≥25, not actionable):**
- H05 (n=35): WR 14.3%, EV −$0.539/$1, CI [−0.928, −0.150] — CI entirely below zero. Would be BLOCK at n≥100.
- H16 (n=30): WR 16.7%, EV −$0.556/$1, CI [−0.960, −0.152] — same profile.
- H09 (n=28): WR 14.3%, EV −$0.456/$1, CI [−0.973, +0.061] — borderline.
- H01 (n=66): WR 48.5%, EV +$0.538/$1 — potential positive outlier; too wide CI.

**CONCLUSION: INCONCLUSIVE.** No hour has n≥100. The 53.8h window distributed trades too thinly (mean 38.6/hour) to reach flagging threshold. H05 and H16 show structurally alarming patterns (WR<20%, CI entirely negative) that would have been strong block candidates at n≥100 — archival only.

**FAILURE_MET:** No — n<100 for all cells.

**IF_DEPLOYED:** N/A — VOLARB retired. H05 and H16 block gates would have been the priority lever if data continued accumulating.

---

## Investigation H4 — Phase 2 Longshot Gate Prep (ask < 0.10)

**HYPOTHESIS:** Phase 2 VOLARB (ASK_CEIL=0.10) was gated on n≥100 OOS shadow observations in the sub-0.10 band. A shadow recorder should have been logging every market_timeline row that would have fired at ASK_FLOOR=0.0 with edge≥0.10, including realized outcomes.

**METHOD:** Check all 219 shadow loggers in shadow_summary.json for any volarb_longshot or equivalent recorder. If absent, propose recorder spec.

**RESULT:**
- Searched all 219 loggers across dates 2026-05-08 through 2026-05-25 (today).
- **No `volarb_longshot_shadow.jsonl` found.** No logger with "volarb" in the name exists in the manifest.
- Closest logger: `market_timeline.jsonl` (500K–1M rows/day per date partition), which records per-window OB+spot+features but does not include post-resolution outcome tracking in query-accessible form on data-mirror.

**Proposed recorder spec (archival — relevant if VOLARB Phase 2 is reconsidered):**

```
Logger: data/shadow/volarb_longshot_shadow.jsonl
Trigger: per 5m updown market at T+30s–T+120s post-window-open
  WHERE entry_price < 0.10
    AND edge (1/entry_price - 1) >= 0.10
    AND market.acceptingOrders == True
    AND rem_seconds in [60, 280]
Record per eval:
  {
    "ts": float,              # eval Unix timestamp
    "condition_id": str,      # market dedup key
    "window_end_ts": int,     # 5m window end epoch
    "asset": str,             # BTC/ETH/SOL
    "direction": str,         # up/down
    "ask": float,             # entry_price at eval
    "edge": float,            # 1/ask - 1
    "rem_seconds": float,     # seconds to resolution at eval
    "ob_depth_usd": float,    # ask-side depth (liquidity gate)
    "resolution_price": float|null,   # filled post-resolution (1.0=win, 0.0=loss)
    "kline_pnl_equiv": float|null,    # (resolution_price - ask) per $1 stake
    "would_fire": bool        # True if all Phase2 gates pass
  }
Pre-registration threshold: n >= 100 rows with resolution_price filled
File rotation: daily hot/<YYYY-MM-DD>/volarb_longshot_shadow.jsonl
```

**Current OOS count:** 0 — logger never deployed.

**CONCLUSION: DATA_MISSING.** Phase 2 shadow recorder was never built. Recorder spec proposed. Moot unless VOLARB reboot is explicitly ordered.

**FAILURE_MET:** N/A — no data.

**IF_DEPLOYED:** Cannot estimate without OOS data. Backtest covered ask 0.10–0.60 only; no analog for sub-0.10 band. Edge at ask=0.05 is +1900% (extreme convexity) — the question is whether WR at that level exceeds the ~5% required for positive EV.

---

## Investigation H7 — Watchlist Cell Trajectories (24h vs Full Window)

**HYPOTHESIS:** Prior scout flagged H1/ETH, H3/(three bands), H6/(both directions) as SIGNAL_FOUND (BELOW_CI). The final 24h of VOLARB trading (2026-05-18 02:50 – 2026-05-19 02:50 UTC, n=140) may show 2-sigma drift from full-window EV, indicating accelerating regime change.

**METHOD:** Split by ts_open ≥ (last_ts − 86400). Full window n=887, last-24h n=140. For each prior-flagged cell, compute EV/$1-stake for both windows. Flag drift where 24h EV falls outside the full-window 95% CI (2σ threshold).

**RESULT (last-24h cutoff: 2026-05-18 02:50 UTC):**

| Cell | Full n | Full EV/$1 | Full vs_CI | 24h n | 24h EV/$1 | 24h vs_CI | Drift (2σ) |
|---|---|---|---|---|---|---|---|
| H1/ETH | 305 | −$0.031 | BELOW_CI | 47 | −$0.034 | WITHIN_CI† | stable |
| H1/BTC | 286 | +$0.054 | WITHIN_CI | 48 | +$0.045 | WITHIN_CI | stable |
| **H1/SOL** | **296** | **+$0.094** | **WITHIN_CI** | **45** | **−$0.130** | **WITHIN_CI†** | **DRIFT ⚠ (watchlist only, n24h<100)** |
| H6/up | 393 | −$0.004 | BELOW_CI | 77 | −$0.155 | BELOW_CI | stable |
| H6/down | 494 | +$0.072 | BELOW_CI | 63 | +$0.105 | WITHIN_CI† | stable |
| H3/[0.20,0.30) | 227 | −$0.006 | BELOW_CI | 18 | −$0.336 | n<20 | n24h<20 |
| H3/[0.30,0.40) | 390 | +$0.068 | BELOW_CI | 77 | +$0.068 | WITHIN_CI† | stable |
| H3/[0.40,0.50) | 158 | +$0.044 | BELOW_CI | 34 | −$0.106 | WITHIN_CI† | stable |

†24h CI spans zero (wide at n=34–77); formally WITHIN_CI but imprecise.

**H1/SOL DRIFT detail:**
- Full-window 95% CI: [−$0.081, +$0.269]
- Last-24h EV: −$0.130 (below full CI lower of −$0.081) → 2σ drift confirmed
- n24h=45: below 100-threshold → watchlist only per decision rule
- Pattern: SOL's positive full-window EV (+$0.094) was concentrated in the first ~1.2 days; final 24h reversed sharply (negative EV −$0.130, WR < 40%). Consistent with a late-era regime change in SOL updown markets.

**H6/up trajectory note:** EV deteriorated from −$0.004 (full) to −$0.155 (last 24h). Formally stable (−$0.155 is within full CI [−$0.173, +$0.164]), but directional worsening is consistent with prior scout's "BUY_YES drag accelerating" observation.

**CONCLUSION: H1/SOL 2σ DRIFT detected at n24h=45 — watchlist only.** All other prior SIGNAL_FOUND cells are stable (no new divergence beyond already-confirmed BELOW_CI status). No new SIGNAL_FOUND from H7.

**FAILURE_MET:** No — n24h<100 for all cells.

**IF_DEPLOYED:** N/A — retired. SOL final-24h reversal would have prompted SOL-specific EDGE_FLOOR elevation or temporary gate.

---

## Priority Signal for Next Implementation

**VOLARB is retired. No actionable signal this cycle — post-mortem complete (n=887 frozen).**

| Investigation | Conclusion | Actionable? |
|---|---|---|
| H2 (per-hour) | INCONCLUSIVE — all n<100; H05/H16 visually alarming | No |
| H4 (Phase 2 longshot) | DATA_MISSING — recorder never built; spec proposed | No (VOLARB retired) |
| H7 (watchlist trajectories) | H1/SOL DRIFT at n24h=45; all others stable | No (n<100) |

Prior SIGNAL_FOUND cells (H1/ETH, H3/all-bands, H6/both-directions) are permanently confirmed. kline EV −$0.023/$1-stake is the resolution-correct final verdict.

---

## Closed-Family Confirmations

Re-validated as null this cycle (prevents re-investigation):

| Family | Closed since | Confirmation |
|---|---|---|
| H5 / term_remaining_s logging bug | Prior scout | All 887 rows have term_remaining_s=0. Permanently DATA_MISSING. |
| H1/ETH BELOW_CI | Prior scout | n=305, EV=−$0.031, CI upper=+$0.141. Frozen. |
| H3/[0.20,0.30) BELOW_CI | Prior scout | n=227, EV=−$0.006, CI upper=+$0.216. Frozen. |
| H3/[0.30,0.40) BELOW_CI | Prior scout | n=390, EV=+$0.068, CI upper=+$0.203. Frozen. |
| H3/[0.40,0.50) BELOW_CI | Prior scout | n=158, EV=+$0.044, CI upper=+$0.221. Frozen. |
| H6/up BELOW_CI | Prior scout | n=393, EV=−$0.004, CI upper=+$0.164. Frozen. |
| H6/down BELOW_CI | Prior scout | n=494, EV=+$0.072, CI upper=+$0.201. Frozen. |
| VOLARB Phase 1 strategy | Retired 2026-05-19 | n=887 final, all aggregate metrics below baseline. |

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:** None — VOLARB data is frozen; no accumulation possible.

**Shadow loggers past threshold:** None — no VOLARB-specific loggers exist (see H4).

**Phase 2 longshot recorder status:** NOT DEPLOYED. Recorder spec proposed in H4. Moot unless VOLARB reboot is explicitly ordered by user.

**Auditor note (LDA):** lda_status.txt shows rolling-20 = −$19.71 (STOP threshold at −$30 triggered at worst −$36.39). Capital $31.36. LDA H10 UTC (n=19, WR=63.2%, net=−$32.20) is the primary loss concentration in the 10-day live window. Scout does not audit LDA but flags for Auditor awareness: H10 at n=19 is approaching the n≥40 watchlist threshold — if 21 more H10 trades fire, Auditor should evaluate a block gate.
