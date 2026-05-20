# VOLARB Quantitative Audit — 2026-05-20 12:14 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-20T12:03:41Z (10.7 min old — FRESH) |
| Klaus state | active (systemd: active, CAS_LOWASK, 0 open positions) |
| Capital | $60.13 (prior audit 2026-05-19 00:16 UTC: $105.59 → **−$45.46 Δ** — CAS_LOWASK, not VOLARB) |
| VOLARB n (live era, deduped) | 885 (prior: 825, Δ=+60 — last VOLARB trade 2026-05-19 02:50 UTC) |
| drift_status | OK — data-mirror has no strategy/volarb.py; dev branch parameters confirmed current |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation) |
| Open audit PRs | NONE |

**STRATEGY STATUS: RETIRED.** VOLARB was disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched),
formally retired 2026-05-19 (volarb_strategy=None, import removed). All 885 trades are
historical. No parameter change has operational effect.

**EDGE_FLOOR NOTE:** Audit prompt assumes `EDGE_FLOOR=0.15` ("current"). Actual code has
`EDGE_FLOOR_DEFAULT=0.10` (user-lowered 2026-05-17 10:20 UTC, state_log). The prescribed
patch "(0.15→0.17)" is incoherent with actual code state. Third consecutive audit noting
same discrepancy.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (10.7 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($60.13) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE (GitHub API confirmed) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK) |
| DATA_CORRUPT | NO |

---

## Overall VOLARB Performance (full window, 2026-05-16 21:00 – 2026-05-19 02:50 UTC)

| metric | value | backtest baseline ($1-equiv) | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | 51.7% (backtest) | WELL BELOW |
| PF | 1.061 | — | — |
| net_sum | +$54.69 | — | — |
| EV/trade | +$0.062 | CI=[+$0.244, +$0.352] | BELOW CI lower |
| CI95 | [−$0.087, +$0.220] | [+$0.244, +$0.352] | CI ranges do not overlap |
| fee_bleed | 1.7% of gross wins | <20% kill-switch | OK |

### Current-Config Subset (hour_utc ∈ {1, 2, 11, 18} — hours gate-allowed by live code)

| metric | this audit | prior audit (2026-05-19 00:16) | Δ |
|---|---|---|---|
| n | 226 | 169 | +57 |
| WR | 43.4% | 45.6% | −2.2pp |
| PF | 1.407 | 1.633 | −0.226 |
| EV/trade | +$0.378 | +$0.531 | −$0.153 |
| CI95 | [+$0.069, +$0.692] | [+$0.164, +$0.896] | CI lower dropped toward zero |

Current-config still positive (CI lower > 0) but deteriorating. Moot: strategy retired.

### EDGE_FLOOR Patch Condition Check

| condition | required | actual | pass? |
|---|---|---|---|
| n ≥ 200 | n≥200 | 885 | PASS |
| EV/trade < +$0.10 | <$0.10 | $0.062 | PASS |
| PF < 1.10 | <1.10 | 1.061 | PASS |
| CI95 lower < 0 | <0 | −$0.087 | PASS |

All four conditions satisfied. **NO PATCH** — two independent blockers:
1. Strategy retired. Editing `EDGE_FLOOR_DEFAULT` in unreachable code has no effect.
2. Code-value mismatch. Prescribed patch "(0.15→0.17)" references a stale value; actual
   constant is 0.10 per user directive (state_log 2026-05-17 10:20 UTC). Raising it would
   contradict that explicit instruction.

---

## 6h Recency Cells (n≥10 threshold)

Window: 2026-05-18 20:50 UTC .. 2026-05-19 02:50 UTC (final 6h of VOLARB operation).

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| (SOL, [30%,40%)) | 12 | 25.0% | −$7.58 | −$0.632 | FLAG (EV<−$0.50) |
| (SOL, [40%,50%)) | 15 | 33.3% | −$9.01 | −$0.601 | FLAG (EV<−$0.50) |
| (BTC, [30%,40%)) | 24 | 41.7% | +$6.97 | +$0.290 | OK |
| (ETH, [30%,40%)) | 22 | 45.5% | +$9.29 | +$0.422 | OK |

SOL bled in the final hours. Strategy was already being replaced; not actionable.

---

## Full-Window Cell Scan (2026-05-16 21:00 – 2026-05-19 02:50 UTC)

### b. Per-Asset

| asset | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| BTC | 286 | 32.9% | 1.08 | +$23.74 | +$0.083 | [−$0.183, +$0.358] | IN_CI | WATCH (n≥100, EV below $0.244) |
| ETH | 305 | 32.5% | 0.97 | −$10.78 | −$0.035 | [−$0.293, +$0.238] | BELOW_CI | WATCH |
| SOL | 294 | 38.8% | 1.14 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | IN_CI | WATCH (n≥100, EV below $0.244) |

ETH is weakest: EV negative, CI upper ($0.238) below baseline lower ($0.244). All three
assets below backtest CI lower ($0.244). No per-asset lever exists in Phase 1; watchlist only.

### c. Per-Hour UTC (all COLLECTING — no cell at n≥100)

| H | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9% | 1.36 | +$12.46 | +$0.320 | [−$0.394, +$1.074] | IN_CI | COLLECTING |
| H01 | 66 | 48.5% | 1.95 | +$51.76 | +$0.784 | [+$0.191, +$1.406] | ABOVE_CI | COLLECTING |
| H02 | 64 | 40.6% | 1.18 | +$12.56 | +$0.196 | [−$0.360, +$0.820] | IN_CI | COLLECTING |
| H03 | 36 | 44.4% | 1.37 | +$13.38 | +$0.372 | [−$0.411, +$1.147] | IN_CI | COLLECTING |
| H04 | 37 | 32.4% | 0.87 | −$5.42 | −$0.146 | [−$0.838, +$0.576] | IN_CI | COLLECTING |
| H05 | 35 | 14.3% | 0.36 | −$30.13 | −$0.861 | [−$1.388, −$0.236] | BELOW_CI | COLLECTING |
| H06 | 35 | 31.4% | 1.02 | +$0.72 | +$0.021 | [−$0.722, +$0.761] | IN_CI | COLLECTING |
| H07 | 31 | 19.4% | 0.62 | −$13.60 | −$0.439 | [−$1.125, +$0.314] | IN_CI | COLLECTING |
| H08 | 35 | 28.6% | 1.50 | +$14.30 | +$0.409 | [−$0.385, +$1.239] | IN_CI | COLLECTING |
| H09 | 28 | 14.3% | 0.44 | −$15.75 | −$0.563 | [−$1.092, +$0.069] | BELOW_CI | COLLECTING |
| H10 | 38 | 34.2% | 1.16 | +$5.34 | +$0.141 | [−$0.483, +$0.813] | IN_CI | COLLECTING |
| H11 | 71 | 35.2% | 1.20 | +$13.53 | +$0.191 | [−$0.340, +$0.741] | IN_CI | COLLECTING |
| H12 | 36 | 36.1% | 0.97 | −$1.20 | −$0.033 | [−$0.785, +$0.716] | IN_CI | COLLECTING |
| H13 | 36 | 33.3% | 1.02 | +$0.83 | +$0.023 | [−$0.701, +$0.827] | IN_CI | COLLECTING |
| H14 | 47 | 29.8% | 0.89 | −$5.05 | −$0.107 | [−$0.708, +$0.491] | IN_CI | COLLECTING |
| H15 | 36 | 30.6% | 0.90 | −$4.45 | −$0.124 | [−$0.910, +$0.709] | IN_CI | COLLECTING |
| H16 | 30 | 16.7% | 0.43 | −$21.46 | −$0.715 | [−$1.315, −$0.057] | BELOW_CI | COLLECTING |
| H17 | 21 | 38.1% | 0.75 | −$8.14 | −$0.387 | [−$2.031, +$1.041] | IN_CI | COLLECTING |
| H18 | 25 | 60.0% | 1.41 | +$7.53 | +$0.301 | [−$0.495, +$1.171] | IN_CI | COLLECTING |
| H20 | 3 | 100.0% | — | +$9.05 | +$3.016 | — | ABOVE_CI | COLLECTING (n<40, ignore) |
| H21 | 39 | 51.3% | 1.87 | +$23.67 | +$0.607 | [−$0.046, +$1.264] | IN_CI | COLLECTING |
| H22 | 40 | 32.5% | 0.87 | −$5.48 | −$0.137 | [−$0.727, +$0.553] | IN_CI | COLLECTING |
| H23 | 57 | 33.3% | 1.00 | +$0.24 | +$0.004 | [−$0.540, +$0.582] | IN_CI | COLLECTING |

No hour reaches n≥100. Notable extremes: H05 (WR=14.3%, CI both negative) and H16
(WR=16.7%, CI upper=−$0.057 < 0) — both n<40, below watchlist threshold.

### d. Per-Ask-Band

| band | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| <0.10 | 10 | 0.0% | 0.00 | −$9.11 | −$0.911 | [−$1.105, −$0.740] | BELOW_CI | COLLECTING (n<40) |
| [0.10,0.20) | 91 | 18.7% | 1.20 | +$13.60 | +$0.149 | [−$0.302, +$0.661] | IN_CI | COLLECTING (n=40–99) |
| [0.20,0.30) | 227 | 26.4% | 1.00 | −$0.73 | −$0.003 | [−$0.276, +$0.265] | IN_CI | WATCH (n≥100, EV below $0.244) |
| [0.30,0.40) | 390 | 38.7% | 1.11 | +$46.99 | +$0.120 | [−$0.108, +$0.357] | IN_CI | WATCH (n≥100, EV below $0.244) |
| [0.40,0.50) | 157 | 47.1% | 1.07 | +$13.38 | +$0.085 | [−$0.280, +$0.472] | IN_CI | WATCH (n≥100, EV below $0.244) |
| [0.50,0.60) | 8 | 50.0% | 0.88 | −$1.25 | −$0.157 | [−$1.997, +$1.697] | IN_CI | COLLECTING (n<40) |
| ≥0.60 | 2 | 50.0% | 0.36 | −$8.18 | −$4.091 | — | — | COLLECTING (n<40, ignore) |

Longshot bucket <0.10 (activated 2026-05-17): n=10, WR=0%, CI fully negative. Catastrophic
as warned. Not lever-actionable at n<40.

---

## Lever Probes

| probe | n | WR | EV | CI95 | lever_candidate | result |
|---|---|---|---|---|---|---|
| ASK_CEIL [0.50,0.60) | 8 | 50.0% | −$0.157 | [−$1.997, +$1.697] | n<100 → NO | NO_ACTION |
| REM_MAX_S [260,280) | 221 | 39.8% | −$0.004 | [−$0.340, +$0.326] | CI upper > 0 → NO | NO_ACTION |
| REM_MIN_S [60,80) | 8 | 0.0% | −$1.075 | [−$1.338, −$0.830] | n<100 → NO | NO_ACTION |
| ASK_DEPTH_MULT | — | — | — | slippage=0 throughout | no adverse-selection evidence | NO_ACTION |

REM_MIN_S [60,80) has n=8, CI fully negative — a real signal, but n<100 is hard. Not
lever-actionable. REM distribution: rem[100,140) is best bucket (WR=37.5%, EV=+$0.630);
very early entries (rem<100) worst (WR=7.1%, EV=−$0.698).

---

## Proposed Patch

**no patch**

No lever probe meets all required conditions. EDGE_FLOOR raise conditions are statistically
met (n=885, EV=$0.062<$0.10, PF=1.061<1.10, CI_lo=−$0.087<0) but is blocked by: (1)
strategy retired; (2) prescribed patch incoherent with actual code value (0.10 ≠ 0.15).

---

## Watchlist (40≤n<100 or n≥100 below baseline, with Δ vs prior audit)

| dimension | cell | n | WR | EV/trade | CI95 | Δ vs prior | status |
|---|---|---|---|---|---|---|---|
| asset | ETH | 305 | 32.5% | −$0.035 | [−$0.293, +$0.238] | new (not individually tracked prior) | DETERIORATING |
| asset | BTC | 286 | 32.9% | +$0.083 | [−$0.183, +$0.358] | new | WATCH |
| asset | SOL | 294 | 38.8% | +$0.142 | [−$0.125, +$0.410] | new | WATCH |
| ask_band | [0.20,0.30) | 227 | 26.4% | −$0.003 | [−$0.276, +$0.265] | new | WATCH |
| ask_band | [0.30,0.40) | 390 | 38.7% | +$0.120 | [−$0.108, +$0.357] | new | WATCH |
| ask_band | [0.40,0.50) | 157 | 47.1% | +$0.085 | [−$0.280, +$0.472] | new | WATCH |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.360, +$0.820] | — | COLLECTING (n=40–99) |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.340, +$0.741] | — | COLLECTING (n=40–99) |
| hour | H14 | 47 | 29.8% | −$0.107 | [−$0.708, +$0.491] | — | COLLECTING (n=40–99) |
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.727, +$0.553] | — | COLLECTING (n=40–99) |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.540, +$0.582] | — | COLLECTING (n=40–99) |

All watchlist items are moot — VOLARB is retired. No re-enablement path without explicit
user instruction and model retrain.

---

## Skipped — User Override (state_log)

| item | state_log entry | action blocked |
|---|---|---|
| EDGE_FLOOR raise | 2026-05-17 10:20 UTC: user explicitly lowered to 0.10 after 0.30 experiment failed | Would contradict user directive |
| Any parameter edit | 2026-05-19: strategy retired, volarb_strategy=None | No operational target |

---

## Structural Note

Third consecutive audit with no actionable patch. Root cause is strategy retirement, not
insufficient data. VOLARB (23h live, WR=34.7%, EV=$0.062) was superseded by CAS_LOWASK on
2026-05-17. If this audit cron continues to run, consider: (1) suspending until VOLARB is
re-enabled; (2) updating audit prompt's EDGE_FLOOR assumption from 0.15 to 0.10; (3) noting
that current-config hour subset {1,2,11,18} was added post-operation and is a retrospective
filter, not a prospective cohort (its positive EV does not imply the gate would produce same
results if re-deployed).
