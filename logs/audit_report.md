# VOLARB Quantitative Audit — 2026-06-10 00:07 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-10T00:05:20Z (2 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $93.96 (prior audit 2026-06-09T18:11Z: $115.12; Δ=−$21.16 — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 24th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~670h retired) |
| drift_status | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition not met |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **24th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten.
- 2026-05-29: CLAUDE.md fully reoriented to STWA. No crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed.
- EDGE_FLOOR on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` (per-asset dict); the audit prompt's scalar `0.15→0.17` raise is structurally inapplicable.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (2 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($93.96) |
| Code drift guard | N/A — data-mirror has no `strategy/volarb.py`; mirror-file-present condition not met; dev branch has levers at lines 59–65 |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-09T18:05Z .. 2026-06-10T00:05Z
**VOLARB trades in window: 0** (strategy retired ~670h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`). Δ vs prior audit = 0.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.093, +$0.217] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.093)
- → All 4 criteria technically met. **SUPPRESSED — two grounds:**
  1. Strategy RETIRED on VPS since 2026-05-19: any edit to `strategy/volarb.py` has zero operational effect.
  2. EDGE_FLOOR is a per-asset dict on dev branch (`EDGE_FLOOR_BY_ASSET`), not a scalar; the scalar `0.15→0.17` raise is inapplicable as written.

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower; straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.223] | BELOW CI lower; PF<1.0; straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower; straddles 0 | WATCHLIST |

**Per-asset patch authority**: n≥100 per asset, but EV is above the −$0.10 lever trigger in all cells. Per-asset/per-hour blocks are not Phase 1 levers (prohibited by audit mandate); goes to watchlist only.

### Per-Hour (n≥40; no hour reaches n≥100)

| cell | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|
| H01 | 66 | 48.5 | +$0.784 | [+$0.174, +$1.415] | WATCHLIST — positive; CI_lo > 0 (notable) |
| H02 | 64 | 40.6 | +$0.196 | [−$0.360, +$0.796] | WATCHLIST |
| H11 | 71 | 35.2 | +$0.191 | [−$0.356, +$0.743] | WATCHLIST |
| H14 | 47 | 29.8 | −$0.108 | [−$0.694, +$0.492] | WATCHLIST — marginal negative |
| H21 | 39 | 51.3 | +$0.607 | [−$0.052, +$1.261] | COLLECT — trending positive |
| H22 | 40 | 32.5 | −$0.137 | [−$0.768, +$0.540] | WATCHLIST — marginal negative |
| H23 | 57 | 33.3 | +$0.004 | [−$0.553, +$0.597] | WATCHLIST |

No per-hour cell reaches n≥100. Cannot add per-hour blocks (no Phase 1 lever; goes to watchlist).

### Per-Ask-Band

| band | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|
| [0.10, 0.20) | 91 | 18.7 | +$0.149 | [−$0.308, +$0.661] | BELOW CI lower; straddles 0 | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4 | −$0.003 | [−$0.276, +$0.274] | BELOW CI lower; straddles 0 | WATCHLIST (n≥100) |
| [0.30, 0.40) | 390 | 38.7 | +$0.121 | [−$0.108, +$0.355] | BELOW CI lower; straddles 0 | WATCHLIST (n≥100) |
| [0.40, 0.50) | 157 | 47.1 | +$0.085 | [−$0.281, +$0.474] | BELOW CI lower; straddles 0 | WATCHLIST (n≥100) |
| [0.50, 0.60) | 8 | 50.0 | −$0.157 | [−$1.991, +$1.684] | n<40 | COLLECT |

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60)**: n=8 — far below n≥100 threshold. **Not a lever candidate.**
- **REM_MAX_S probe [260, 280)**: **UNCOMPUTABLE** — `term_remaining_s=0.0` for all 885 trades. Field not populated at trade-log time for this strategy era. Not a lever candidate.
- **REM_MIN_S probe [60, 80)**: **UNCOMPUTABLE** — same as above. Not a lever candidate.
- **ASK_DEPTH_MULT probe**: `slippage_entry` mean = 0.0000 across n=885 — no adverse-selection signal. Slippage evidence absent. Not a lever candidate.

---

## Proposed Patch (capped at 1)

**no patch**

Grounds:
1. **Strategy retired**: VOLARB has been off VPS since 2026-05-19T00:00Z. Any edit to `strategy/volarb.py` has zero live effect.
2. **EDGE_FLOOR structure mismatch**: dev branch uses `EDGE_FLOOR_BY_ASSET` dict, not the scalar assumed by the `0.15→0.17` patch spec.
3. **No lever probe clears n≥100**: ASK_CEIL n=8; REM probes uncomputable; ASK_DEPTH_MULT no adverse-selection evidence.
4. Dataset is closed and stable at n=885 for 22+ days.

---

## Watchlist (Δ vs prior audit: 0 changes — dataset closed)

| dimension | cell | n | EV/trade | CI95 | delta_vs_prior | note |
|---|---|---|---|---|---|---|
| asset | BTC | 286 | +$0.083 | [−$0.175, +$0.348] | Δ=0 | straddles 0; strategy retired |
| asset | ETH | 305 | −$0.035 | [−$0.294, +$0.223] | Δ=0 | PF<1.0; worst asset; retired |
| asset | SOL | 294 | +$0.142 | [−$0.125, +$0.410] | Δ=0 | best asset; still straddles 0; retired |
| ask_band | [0.20,0.30) | 227 | −$0.003 | [−$0.276, +$0.274] | Δ=0 | below baseline; retired |
| ask_band | [0.30,0.40) | 390 | +$0.121 | [−$0.108, +$0.355] | Δ=0 | largest cell; straddles 0; retired |
| ask_band | [0.40,0.50) | 157 | +$0.085 | [−$0.281, +$0.474] | Δ=0 | straddles 0; retired |
| hour | H01 | 66 | +$0.784 | [+$0.174, +$1.415] | Δ=0 | only cell with CI_lo>0; informative for revival |
| hour | H21 | 39 | +$0.607 | [−$0.052, +$1.261] | Δ=0 | trending positive; COLLECT |
| hour | H14 | 47 | −$0.108 | [−$0.694, +$0.492] | Δ=0 | marginal negative |

All watchlist cells are unchanged vs prior audit (Δ=0 new trades). Dataset fully closed.

---

## Skipped — User Override (state_log)

None applicable to active levers. Historical EDGE_FLOOR directives (2026-05-17) predate and are superseded by the 2026-05-19 full disable.
