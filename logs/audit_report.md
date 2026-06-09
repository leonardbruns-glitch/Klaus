# VOLARB Quantitative Audit — 2026-06-09 18:11 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-09T18:02:36Z (9 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $115.12 (prior audit 2026-06-09T06:13Z: $70.22; Δ=**+$44.90** — STWA activity, not VOLARB) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 23rd consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~646h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **23rd consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten.
- 2026-05-29: CLAUDE.md fully reoriented to STWA. No crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not load or call it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed.
- EDGE_FLOOR on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` (per-asset dict, not scalar); the audit prompt's scalar `0.15→0.17` raise is structurally inapplicable.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($115.12) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-09T12:02Z .. 2026-06-09T18:02Z
**VOLARB trades in window: 0** (strategy retired ~646h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.092, +$0.214] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.092)
- → All 4 criteria technically met. **SUPPRESSED — two grounds:**
  1. Strategy RETIRED on VPS since 2026-05-19: any edit to `strategy/volarb.py` has zero operational effect.
  2. EDGE_FLOOR is a per-asset dict on dev branch (`EDGE_FLOOR_BY_ASSET`), not a scalar; the scalar `0.15→0.17` raise is inapplicable as written.

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.180, +$0.345] | BELOW CI lower; CI straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.299, +$0.233] | BELOW CI lower; PF<1.0; CI straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.127, +$0.417] | BELOW CI lower; CI straddles 0 | WATCHLIST |

### Per-Hour UTC (n≥40 shown; no cell at n≥100)

| dim | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline | status |
|---|---|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | [+$0.152, +$1.423] | above baseline; CI strictly positive | WATCHLIST (n<100) |
| hour | H02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | [−$0.406, +$0.781] | below CI lower; CI straddles 0 | WATCHLIST (n<100) |
| hour | H11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | [−$0.328, +$0.749] | below CI lower; CI straddles 0 | WATCHLIST (n<100) |
| hour | H21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | [−$0.077, +$1.271] | n<40 — ignored | IGNORE |
| hour | H05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | [−$1.377, −$0.248] | n<40 — ignored | IGNORE |
| hour | H16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | [−$1.294, −$0.043] | n<40 — ignored | IGNORE |

Note: No per-hour cell reached n≥100; all hour cells are WATCHLIST or IGNORE tier only. H01 shows the strongest positive trend (WR=48.5%, CI strictly positive at n=66) but cannot trigger a patch at n<100.

### Per-Ask-Band

| dim | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline | status |
|---|---|---|---|---|---|---|---|---|---|
| ask | [0.00,0.10) | 10 | 0.0 | 0.000 | −$9.11 | −$0.911 | [−$1.108, −$0.741] | n<40 — ignored | IGNORE |
| ask | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.301, +$0.656] | below CI lower; CI straddles 0 | WATCHLIST (n<100) |
| ask | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.268, +$0.273] | below CI lower; CI straddles 0 | WATCHLIST |
| ask | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.113, +$0.360] | below CI lower; CI straddles 0 | WATCHLIST |
| ask | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.292, +$0.465] | below CI lower; CI straddles 0 | WATCHLIST |
| ask | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$2.004, +$1.697] | n<40 — ignored | IGNORE |

---

## Lever Probes

- **ASK_CEIL probe** [0.50, 0.60): n=8 — **BELOW THRESHOLD** (need n≥100). No candidate.
- **REM_MAX_S probe** [260, 280)s: `term_remaining_s=0.0` for all 885 trades — **FIELD ABSENT**. Probe impossible.
- **REM_MIN_S probe** [60, 80)s: `term_remaining_s=0.0` for all 885 trades — **FIELD ABSENT**. Probe impossible.
- **ASK_DEPTH_MULT probe**: No adverse-selection slippage evidence in trade schema; field not logged. No candidate.

---

## Proposed Patch (capped at 1)

**no patch**

Grounds:
1. VOLARB strategy retired on VPS 2026-05-19. `strategy/volarb.py` is not loaded, imported, or called by the running bot. Any scalar edit has zero operational effect.
2. REM probes are structurally impossible: `term_remaining_s` was not populated in live VOLARB trades (all 885 = 0.0).
3. ASK_CEIL probe: n=8 in [0.50,0.60), below the n≥100 lever threshold.
4. EDGE_FLOOR raise: all 4 criteria met numerically, but suppressed on grounds (1) + EDGE_FLOOR is a per-asset dict (`EDGE_FLOOR_BY_ASSET`), not the scalar the lever specifies.

---

## Watchlist (40≤n<100 AND per-asset/per-hour findings)

Δ vs prior audit (2026-06-09T06:13Z): all cells unchanged (Δn=0).

| cell | n | EV | CI95 | trend | delta_vs_prior |
|---|---|---|---|---|---|
| BTC (asset) | 286 | +$0.083 | [−$0.180, +$0.345] | flat; CI straddles 0 | 0 new trades |
| ETH (asset) | 305 | −$0.035 | [−$0.299, +$0.233] | negative; PF<1.0 | 0 new trades |
| SOL (asset) | 294 | +$0.142 | [−$0.127, +$0.417] | modest positive | 0 new trades |
| H01 (hour) | 66 | +$0.784 | [+$0.152, +$1.423] | strong positive; CI > 0 (promising) | 0 new trades |
| H02 (hour) | 64 | +$0.196 | [−$0.406, +$0.781] | weak positive | 0 new trades |
| H11 (hour) | 71 | +$0.191 | [−$0.328, +$0.749] | weak positive | 0 new trades |
| [0.10,0.20) (ask) | 91 | +$0.149 | [−$0.301, +$0.656] | weak positive | 0 new trades |
| [0.20,0.30) (ask) | 227 | −$0.003 | [−$0.268, +$0.273] | flat | 0 new trades |
| [0.30,0.40) (ask) | 390 | +$0.121 | [−$0.113, +$0.360] | flat/positive | 0 new trades |
| [0.40,0.50) (ask) | 157 | +$0.085 | [−$0.292, +$0.465] | weak positive | 0 new trades |

**No watchlist cell will ever cross n≥100 from its current state.** VOLARB is retired. These entries are historical artifacts only.

---

## Skipped — User Override (state_log)

- H11 unblock (2026-05-19): user explicitly unblocked H11 for CAS_LOWASK; no VOLARB implication.
- ASK_FLOOR=0.00: user instruction 2026-05-17; Phase 2 gated per lever rules — NOT touched.
- EDGE_FLOOR=0.10 (per-asset dict): set by user instruction 2026-05-17 10:20 UTC; overrides the prompt's scalar 0.15 baseline.
- STAKE_USD, MAX_CONCURRENT: never touched (Phase 1 gated).

---

*Audit run: 23rd consecutive. Dataset closed 2026-05-19. No further patch opportunities exist without strategy re-activation.*
