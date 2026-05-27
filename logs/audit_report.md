# VOLARB Quantitative Audit — 2026-05-27 12:18 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-27T12:01:52Z (16.2 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $95.30 (prior audit 2026-05-27 00:14 UTC: $29.03 → **+$66.27 Δ** — CAS_LOWASK/weather growth, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~198h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation — CLOSED) |
| Open audit PRs | NONE |
| Run | **11th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- All 885 trades are historical. Any parameter change to `strategy/volarb.py` has zero operational effect.

**CODE MISMATCH NOTE (11th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual code: `EDGE_FLOOR_DEFAULT=0.10` (per-asset dict, no scalar `EDGE_FLOOR`), set by explicit user
instruction 2026-05-17 10:20 UTC (state_log). Prompt's "0.15 → 0.17 raise" inapplicable.

**REM FIELD NOTE:** `term_remaining_s` is 0.0/None for all 885 VOLARB trades — field was not
populated in the VOLARB era. REM_MAX_S and REM_MIN_S lever probes: n=0 in both windows. No data.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (16.2 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($95.30) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK/weather) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-27T06:01Z .. 2026-05-27T12:01Z
**VOLARB trades in window: 0** (strategy retired ~198h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`).
Backtest $1-equiv CI baseline = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.089, +$0.213] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.089)
→ All 4 criteria technically MET — suppressed: strategy RETIRED (see Proposed Patch section).

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.083 | [−$0.181, +$0.349] | BELOW_CI_LOWER | watchlist |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.78 | −$0.035 | [−$0.309, +$0.239] | BELOW_CI_LOWER | watchlist |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.74 | +$0.142 | [−$0.123, +$0.412] | BELOW_CI_LOWER | watchlist |

All three assets n≥100 with EV below CI lower (+$0.244). No per-asset lever exists in Phase 1 — watchlist.

### Per Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.00,0.10) | 10 | 0.0% | 0.000 | −$9.11 | −$0.911 | [−$1.105,−$0.745] | — | COLLECT (n<40) |
| ask_band | [0.10,0.20) | 91 | 18.7% | 1.197 | +$13.60 | +$0.149 | [−$0.308,+$0.649] | BELOW_CI_LOWER | watchlist |
| ask_band | [0.20,0.30) | 227 | 26.4% | 0.997 | −$0.73 | −$0.003 | [−$0.274,+$0.281] | BELOW_CI_LOWER | watchlist |
| ask_band | [0.30,0.40) | 390 | 38.7% | 1.115 | +$46.99 | +$0.121 | [−$0.107,+$0.351] | BELOW_CI_LOWER | watchlist |
| ask_band | [0.40,0.50) | 157 | 47.1% | 1.075 | +$13.38 | +$0.085 | [−$0.295,+$0.468] | BELOW_CI_LOWER | watchlist |
| ask_band | [0.50,0.60) | 8 | 50.0% | 0.881 | −$1.25 | −$0.157 | [−$2.004,+$1.697] | — | COLLECT (n<40) |

Note: [0.00,0.10) longshot bucket — n=10, WR=0%, EV=−$0.911/trade, CI95 entirely negative.
Backtest projected 88% of total PnL from this band; live data cleanly falsified this at n=10.
n<40 → no action; directional signal noted in watchlist.

### Per UTC Hour (n≥40)

| dimension | cell | n | WR% | PF | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| hour_utc | H01 | 66 | 48.5% | 1.953 | +$0.784 | [+$0.152,+$1.403] | BELOW_CI_LOWER | watchlist |
| hour_utc | H02 | 64 | 40.6% | 1.185 | +$0.196 | [−$0.398,+$0.792] | BELOW_CI_LOWER | watchlist |
| hour_utc | H11 | 71 | 35.2% | 1.196 | +$0.191 | [−$0.365,+$0.754] | BELOW_CI_LOWER | watchlist |
| hour_utc | H14 | 47 | 29.8% | 0.894 | −$0.108 | [−$0.697,+$0.508] | BELOW_CI_LOWER | watchlist |
| hour_utc | H22 | 40 | 32.5% | 0.872 | −$0.137 | [−$0.783,+$0.558] | BELOW_CI_LOWER | watchlist |
| hour_utc | H23 | 57 | 33.3% | 1.004 | +$0.004 | [−$0.578,+$0.592] | BELOW_CI_LOWER | watchlist |

H01 is the single absolute-positive-CI hour (lower bound +$0.152) but still below the backtest CI
lower of +$0.244. No hour reached n≥100. All watchlist-only.

---

## Lever Probes

### ASK_CEIL probe [0.50, 0.60)
n=8 (far below n≥100 threshold). CI95=[−$2.004, +$1.697].
**Lever candidate: NO** (n<100).

### REM_MAX_S probe [260, 280)
n=0 — `term_remaining_s` not populated in VOLARB era (field added in TERMINAL strategy era).
**Lever candidate: NO** (n=0, field absent).

### REM_MIN_S probe [60, 80)
n=0 — same reason.
**Lever candidate: NO** (n=0, field absent).

### ASK_DEPTH_MULT probe
n≥200 overall satisfied (885), but no adverse-selection slippage evidence in VOLARB schema isolatable
to depth-driven fill degradation. EV degradation from overall metrics does not meet the "degrading
+ slippage evidence" dual requirement.
**Lever candidate: NO**.

---

## Proposed Patch

**NO PATCH.**

Reasons (ordered by priority):

1. **VOLARB is RETIRED.** Strategy disabled 2026-05-17 19:56 UTC, formally removed 2026-05-19.
   `volarb_strategy=None` in `main.py`. Any edit to `strategy/volarb.py` has zero operational
   effect. Dead code modification is noise.

2. **EDGE_FLOOR criteria met but prompt baseline is stale.** Criteria are technically satisfied
   (n≥200 ✓, EV<+$0.10 ✓, PF<1.10 ✓, CI_lo<0 ✓) — but the prompt's "EDGE_FLOOR=0.15 → 0.17"
   does not match actual code. Actual: `EDGE_FLOOR_DEFAULT=0.10`, set by user instruction
   2026-05-17 10:20 UTC. User explicitly lowered the floor after observing no EV improvement at
   higher values. Raise is doubly suppressed: (a) retired strategy, (b) user override.

3. **ASK_CEIL, REM levers: n far below threshold.** ASK_CEIL n=8; REM n=0 (field absent).
   n≥100 required. Not met.

4. **Longshot ASK_FLOOR note (user-decision, not Auditor lever).** [0.00,0.10) has n=10, 0 wins,
   EV=−$0.911/trade. If VOLARB is ever reactivated, ASK_FLOOR should be raised back to 0.10 before
   re-enabling. Auditor cannot touch ASK_FLOOR (Phase 2 gated); flagged for user review.

---

## Watchlist (40≤n<100 / n≥100 findings without available lever)

| cell | n | EV/trade | CI95 | trend vs prior audit |
|---|---|---|---|---|
| BTC (asset) | 286 | +$0.083 | [−$0.181,+$0.349] | UNCHANGED (Δn=0) |
| ETH (asset) | 305 | −$0.035 | [−$0.309,+$0.239] | UNCHANGED (Δn=0) |
| SOL (asset) | 294 | +$0.142 | [−$0.123,+$0.412] | UNCHANGED (Δn=0) |
| ask [0.10,0.20) | 91 | +$0.149 | [−$0.308,+$0.649] | UNCHANGED |
| ask [0.20,0.30) | 227 | −$0.003 | [−$0.274,+$0.281] | UNCHANGED |
| ask [0.30,0.40) | 390 | +$0.121 | [−$0.107,+$0.351] | UNCHANGED |
| ask [0.40,0.50) | 157 | +$0.085 | [−$0.295,+$0.468] | UNCHANGED |
| H01 | 66 | +$0.784 | [+$0.152,+$1.403] | UNCHANGED — strongest hour |
| H02 | 64 | +$0.196 | [−$0.398,+$0.792] | UNCHANGED |
| H11 | 71 | +$0.191 | [−$0.365,+$0.754] | UNCHANGED |
| H14 | 47 | −$0.108 | [−$0.697,+$0.508] | UNCHANGED |
| H22 | 40 | −$0.137 | [−$0.783,+$0.558] | UNCHANGED |
| H23 | 57 | +$0.004 | [−$0.578,+$0.592] | UNCHANGED |

All cells frozen (Δn=0) since audit #2. Strategy retired — watchlist will never advance.

**Special note — [0.00,0.10) longshot bucket (n=10, below watchlist threshold):**
Live data unambiguously falsifies backtest projection. If VOLARB is reactivated, ASK_FLOOR
must be raised from 0.00 back to 0.10 before re-enabling. User-decision item only.

---

## Skipped — User Override (state_log)

- **EDGE_FLOOR=0.10 (user instruction 2026-05-17 10:20 UTC):** Auditor raise to 0.15/0.17
  overruled. state_log records user explicitly directed lower to 0.10 after live analysis
  showed no EV improvement at higher floors.
- **ASK_FLOOR=0.00 (user instruction 2026-05-17):** Auditor has no lever authority (Phase 2
  gated). Longshot bucket data supports raising back to 0.10, but this is user-decision only.
- **VOLARB retired (user instruction 2026-05-17 19:56 UTC + 2026-05-19):** No code changes
  to retired strategy without explicit user instruction to reactivate.
