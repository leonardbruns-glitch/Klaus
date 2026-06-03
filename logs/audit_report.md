# VOLARB Quantitative Audit — 2026-06-03 00:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-03T00:05:32Z (6.9 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $117.69 (prior audit 2026-05-28 12:17 UTC: $95.30; Δ=+$22.39 — STWA gains, no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — no new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~357h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **15th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten.
- 2026-05-29: CLAUDE.md fully reoriented to STWA (weather arb). No crypto at all.
- All 885 trades are historical. Any parameter change to `strategy/volarb.py` has **zero operational effect**.

**CODE MISMATCH NOTE (15th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15` (scalar).
Actual dev branch: `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` / `EDGE_FLOOR_DEFAULT=0.10` (per-asset dict).
Per explicit user instruction 2026-05-17 10:20 UTC (state_log). Prompt's "0.15 → 0.17 raise" is inapplicable.

**REM FIELD NOTE:** `rem_s` at entry is not logged. Reconstruction via `hold_seconds` is invalid — 97% of exits are BOND_RESOLVED_NO (573) or PROFIT_TARGET (267), not time-based. Only 3 BOND_TIME_EXIT trades exist. REM probes cannot be computed from this dataset.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (6.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($117.69) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-02T18:12Z .. 2026-06-03T00:12Z
**VOLARB trades in window: 0** (strategy retired ~357h ago; last trade 2026-05-19T02:50:33Z)

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
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower (+$0.244) |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.084, +$0.210] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.084)
→ All 4 criteria technically MET — **suppressed: strategy RETIRED**. Patch has zero operational effect.
→ Additional suppression: `EDGE_FLOOR` is not a scalar in dev branch; it is a per-asset dict per user directive.

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.359] | BELOW CI lower (+$0.244) | BELOW_CI |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.78 | −$0.035 | [−$0.300, +$0.234] | BELOW CI lower | BELOW_CI |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.74 | +$0.142 | [−$0.126, +$0.405] | BELOW CI lower | BELOW_CI |

All three assets BELOW baseline CI lower bound at n≥100. No per-asset lever exists (per-asset blocks are Phase-2 gated per mandate).

### Per-Hour UTC (selected; no cell reaches n≥100)

| hour | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|
| H01 | 66 | 48.5% | +$0.784 | [+$0.163, +$1.386] | WATCHLIST (n<100) |
| H02 | 64 | 40.6% | +$0.196 | [−$0.391, +$0.780] | WATCHLIST |
| H05 | 35 | 14.3% | −$0.861 | [−$1.406, −$0.214] | n<40; ignore |
| H09 | 28 | 14.3% | −$0.563 | [−$1.071, +$0.052] | n<40; ignore |
| H11 | 71 | 35.2% | +$0.191 | [−$0.369, +$0.785] | WATCHLIST |
| H14 | 47 | 29.8% | −$0.107 | [−$0.647, +$0.539] | WATCHLIST |
| H16 | 30 | 16.7% | −$0.715 | [−$1.273, −$0.052] | n<40; ignore |
| H22 | 40 | 32.5% | −$0.137 | [−$0.790, +$0.503] | WATCHLIST |
| H23 | 57 | 33.3% | +$0.004 | [−$0.570, +$0.613] | WATCHLIST |

Max hour n=66 (H01). No per-hour cell reaches n≥100. Per-hour blocks are Phase-2 gated per mandate regardless.

### Per-Ask-Band (entry_price as ask proxy)

| band | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|
| [0.00,0.10) | 10 | 0.0% | −$0.911 | [−$1.093, −$0.742] | COLLECTING (n<40) |
| [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.312, +$0.665] | WATCHLIST (n<100) |
| [0.20,0.30) | 227 | 26.4% | −$0.003 | [−$0.275, +$0.264] | OK (CI_hi=+$0.264>0) |
| [0.30,0.40) | 390 | 38.7% | +$0.120 | [−$0.128, +$0.350] | OK (CI_hi=+$0.350>0) |
| [0.40,0.50) | 157 | 47.1% | +$0.085 | [−$0.294, +$0.466] | OK (CI_hi=+$0.466>0) |
| [0.50,0.60) | 8 | 50.0% | −$0.157 | [−$1.991, +$1.690] | COLLECTING (n<40) |

No ask-band cell meets the lever condition (n≥100 AND CI_hi<0).

---

## Lever Probes

**ASK_CEIL probe [0.50, 0.60):**
n=8, WR=50.0%, EV=−$0.157, CI=[−$1.991, +$1.690]. **COLLECTING.** n<100. Lever NOT triggered.

**REM_MAX_S probe [260, 280):**
DATA UNAVAILABLE. `rem_s` at entry not logged in VOLARB records. 97% of exits are resolution-based (BOND_RESOLVED_NO + PROFIT_TARGET), not time-based. Only 3 BOND_TIME_EXIT trades exist; probe not computable. n=0.

**REM_MIN_S probe [60, 80):**
DATA UNAVAILABLE. Same reason. n=0.

**ASK_DEPTH_MULT probe:**
`slippage_entry` is 0.0 for all records. No adverse-selection evidence. Overall EV degrades vs backtest but CI straddles zero. Criteria not met.

---

## Proposed Patch

**no patch**

Suppression reasons (priority order):
1. **Strategy RETIRED** — `strategy/volarb.py` does not exist on the VPS (data-mirror confirms). Any edit has zero operational effect.
2. **EDGE_FLOOR raise** — All 4 arithmetic criteria met (n=885, EV=+$0.062<$0.10, PF=1.061<1.10, CI_lo=−$0.084<0). Suppressed: (a) retired; (b) EDGE_FLOOR is a per-asset dict in actual code, not the scalar `0.15` the raise targets; (c) explicit user override on this parameter (state_log 2026-05-17 10:20 UTC).
3. **ASK_CEIL** — n=8 in [0.50,0.60). Threshold n≥100 not met.
4. **REM_MAX_S / REM_MIN_S** — rem_s at entry not logged; probes not computable.
5. **ASK_DEPTH_MULT** — no adverse-selection slippage evidence; criteria not met.

---

## Watchlist (40≤n<100; frozen — strategy retired, n cannot grow)

| cell | n | WR% | EV/trade | CI95 | Δ vs prior | note |
|---|---|---|---|---|---|---|
| ask [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.312,+$0.665] | unchanged | n<100; won't cross |
| H01 | 66 | 48.5% | +$0.784 | [+$0.163,+$1.386] | unchanged | strongest hour; n<100 |
| H11 | 71 | 35.2% | +$0.191 | [−$0.369,+$0.785] | unchanged | n<100 |
| H14 | 47 | 29.8% | −$0.107 | [−$0.647,+$0.539] | unchanged | n<100; negative trend |
| H22 | 40 | 32.5% | −$0.137 | [−$0.790,+$0.503] | unchanged | n<100 |
| H23 | 57 | 33.3% | +$0.004 | [−$0.570,+$0.613] | unchanged | n<100 |

All watchlist cells are terminal observations. n cannot grow (VOLARB retired).

---

## Skipped — User Override (state_log)

| parameter | override | state_log entry | action |
|---|---|---|---|
| EDGE_FLOOR (global) | lowered 0.30→0.10, user directive | 2026-05-17 10:20 UTC | no patch; user override + strategy retired |
| EDGE_FLOOR_BY_ASSET | per-asset dict replaces scalar | 2026-05-17 07:26 UTC | audit prompt's scalar target inapplicable |
| H04-H10 block | "monitor only, no parameter change" | 2026-05-17 12:30 UTC | hour blocks Phase-2 gated per mandate |
