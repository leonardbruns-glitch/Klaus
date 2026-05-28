# VOLARB Quantitative Audit — 2026-05-28 12:17 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-28T12:01:03Z (16 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $95.30 (unchanged vs prior audit 2026-05-28 06:15 UTC — no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — no new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~225h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE |
| Run | **14th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- All 885 trades are historical. Any parameter change to `strategy/volarb.py` has zero operational effect.

**CODE MISMATCH NOTE (14th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual dev branch code: `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` / `EDGE_FLOOR_DEFAULT=0.10`
(per-asset dict; no scalar `EDGE_FLOOR`), set by explicit user instruction 2026-05-17 10:20 UTC (state_log).
Prompt's "0.15 → 0.17 raise" is inapplicable to actual code structure. Not patching dead code.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (16 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($95.30) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE (confirmed via GitHub MCP) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-28T06:01Z .. 2026-05-28T12:01Z
**VOLARB trades in window: 0** (strategy retired ~225h ago; last trade 2026-05-19T02:50:33Z)

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
| CI95 EV/trade | [−$0.097, +$0.219] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.097)
→ All 4 criteria technically MET — **suppressed: strategy RETIRED**. Patch has zero operational effect.
→ Additional suppression: `EDGE_FLOOR` is not a scalar in dev branch; it is a per-asset dict.

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +23.74 | +0.083 | [−0.175, +0.348] | BELOW CI lower (+0.244) | BELOW_CI |
| asset | ETH | 305 | 32.5% | 0.966 | −10.78 | −0.035 | [−0.294, +0.232] | BELOW CI lower | BELOW_CI |
| asset | SOL | 294 | 38.8% | 1.140 | +41.74 | +0.142 | [−0.125, +0.413] | BELOW CI lower | BELOW_CI |

All three assets BELOW_CI at n≥100. No per-asset lever in this audit spec. All → watchlist (strategy retired).

### Per-Hour UTC

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | status |
|---|---|---|---|---|---|---|---|---|---|
| hour | H00 | 39 | 35.9% | 1.360 | +12.46 | +0.320 | −0.412 | +1.097 | COLLECT |
| hour | H01 | 66 | 48.5% | 1.953 | +51.76 | +0.784 | **+0.174** | +1.413 | WATCHLIST |
| hour | H02 | 64 | 40.6% | 1.185 | +12.56 | +0.196 | −0.384 | +0.806 | WATCHLIST |
| hour | H03 | 36 | 44.4% | 1.374 | +13.38 | +0.372 | −0.424 | +1.144 | COLLECT |
| hour | H04 | 37 | 32.4% | 0.873 | −5.42 | −0.147 | −0.880 | +0.610 | COLLECT |
| hour | H05 | 35 | 14.3% | 0.359 | −30.13 | −0.861 | −1.391 | −0.225 | COLLECT |
| hour | H06 | 35 | 31.4% | 1.020 | +0.72 | +0.021 | −0.709 | +0.809 | COLLECT |
| hour | H07 | 31 | 19.4% | 0.616 | −13.60 | −0.439 | −1.090 | +0.332 | COLLECT |
| hour | H08 | 35 | 28.6% | 1.498 | +14.30 | +0.409 | −0.395 | +1.305 | COLLECT |
| hour | H09 | 28 | 14.3% | 0.438 | −15.75 | −0.563 | −1.092 | +0.068 | COLLECT |
| hour | H10 | 38 | 34.2% | 1.162 | +5.34 | +0.141 | −0.503 | +0.827 | COLLECT |
| hour | H11 | 71 | 35.2% | 1.196 | +13.53 | +0.191 | −0.353 | +0.753 | WATCHLIST |
| hour | H12 | 36 | 36.1% | 0.970 | −1.20 | −0.033 | −0.743 | +0.765 | COLLECT |
| hour | H13 | 36 | 33.3% | 1.022 | +0.83 | +0.023 | −0.704 | +0.780 | COLLECT |
| hour | H14 | 47 | 29.8% | 0.894 | −5.05 | −0.108 | −0.683 | +0.508 | WATCHLIST |
| hour | H15 | 36 | 30.6% | 0.898 | −4.45 | −0.124 | −0.900 | +0.726 | COLLECT |
| hour | H16 | 30 | 16.7% | 0.428 | −21.46 | −0.715 | −1.297 | −0.034 | COLLECT |
| hour | H17 | 21 | 38.1% | 0.752 | −8.14 | −0.388 | −2.034 | +1.024 | COLLECT |
| hour | H18 | 25 | 60.0% | 1.406 | +7.53 | +0.301 | −0.495 | +1.115 | COLLECT |
| hour | H21 | 39 | 51.3% | 1.873 | +23.67 | +0.607 | −0.053 | +1.255 | COLLECT |
| hour | H22 | 40 | 32.5% | 0.872 | −5.48 | −0.137 | −0.779 | +0.543 | WATCHLIST |
| hour | H23 | 57 | 33.3% | 1.004 | +0.24 | +0.004 | −0.576 | +0.586 | WATCHLIST |

No hour reaches n≥100. H01 CI_lo=+$0.174 (above zero, strongest signal in dataset).

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95_lo | CI95_hi | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|---|
| ask_band | <0.10 | 10 | 0.0% | 0.000 | −9.11 | −0.911 | −1.108 | −0.744 | — | COLLECT |
| ask_band | [0.10,0.20) | 91 | 18.7% | 1.197 | +13.60 | +0.149 | −0.307 | +0.639 | BELOW CI lower | WATCHLIST |
| ask_band | [0.20,0.30) | 227 | 26.4% | 0.997 | −0.73 | −0.003 | −0.281 | +0.275 | BELOW CI lower | BELOW_CI |
| ask_band | [0.30,0.40) | 390 | 38.7% | 1.115 | +46.99 | +0.121 | −0.120 | +0.351 | BELOW CI lower | BELOW_CI |
| ask_band | [0.40,0.50) | 157 | 47.1% | 1.075 | +13.38 | +0.085 | −0.285 | +0.474 | BELOW CI lower | BELOW_CI |
| ask_band | [0.50,0.60) | 8 | 50.0% | 0.881 | −1.25 | −0.157 | −1.991 | +1.684 | — | COLLECT |

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI95=[−$1.991, +$1.684]
  → NOT a lever candidate (n<100). No action.

- **REM_MAX_S probe [260,280):** n=221, EV=−$0.004, CI95=[−$0.336, +$0.312]
  → NOT a lever candidate (CI upper > 0 at +$0.312; does not clear the threshold). No action.

- **REM_MIN_S probe [60,80):** n=8, EV=−$1.076, CI95=[−$1.339, −$0.837]
  → NOT a lever candidate (n<100). VOLARB rarely entered near the floor (entry distribution skewed late; p5=133s). Moot given strategy retirement.

- **ASK_DEPTH_MULT probe:** No adverse-selection slippage evidence in trade fields; overall EV positive (+$0.062). Conditions not met. No action.

---

## Proposed Patch (capped at 1)

**no patch**

Reason: VOLARB strategy is fully retired as of 2026-05-19 (per user instruction; state_log confirmed).
`strategy/volarb.py` does not exist on the live VPS (absent from data-mirror snapshot).
Any edit to the dev-branch file is dead code with zero operational effect.

Despite EDGE_FLOOR raise criteria being technically satisfied (n=885, EV=+$0.062<+$0.10,
PF=1.061<1.10, CI_lo=−$0.097<0), applying the patch would alter a disabled file, add noise to
the branch history, and create a PR that cannot improve live performance. Suppressed per
anti-sycophancy rule: do not generate noise PRs.

---

## Watchlist (40≤n<100; delta vs prior audit 06:15 UTC)

All cells unchanged (Δ=0 new trades). Dataset closed at n=885; no cell will ever cross n≥100.

| cell | n | WR% | EV/trade | CI95_lo | CI95_hi | delta vs prior | note |
|---|---|---|---|---|---|---|---|
| H01 | 66 | 48.5% | +0.784 | **+0.174** | +1.413 | Δ=0 | STRONGEST — CI_lo above zero |
| H02 | 64 | 40.6% | +0.196 | −0.384 | +0.806 | Δ=0 | Positive EV, CI straddles zero |
| H11 | 71 | 35.2% | +0.191 | −0.353 | +0.753 | Δ=0 | Unblocked in CAS per state_log |
| H14 | 47 | 29.8% | −0.108 | −0.683 | +0.508 | Δ=0 | Negative EV, CI straddles zero |
| H22 | 40 | 32.5% | −0.137 | −0.779 | +0.543 | Δ=0 | At n=40 floor; low WR |
| H23 | 57 | 33.3% | +0.004 | −0.576 | +0.586 | Δ=0 | Near-flat EV |
| [0.10,0.20) | 91 | 18.7% | +0.149 | −0.307 | +0.639 | Δ=0 | Low WR; positive sum |

Watchlist is informational only — relevant only if VOLARB is ever re-activated.

---

## Skipped — User Override (state_log)

| item | state_log entry | action |
|---|---|---|
| EDGE_FLOOR raise | 2026-05-17 10:20 UTC: EDGE_FLOOR lowered to 0.10 by explicit user instruction | Not raising; also moot — strategy retired |
| EDGE_FLOOR_BY_ASSET | 2026-05-17 07:26 / 07:44 UTC: per-asset dict introduced by user | Structural change; not touched |
| H11 unblock | 2026-05-19 19:XX UTC: H11 unblocked for CAS live testing per user instruction | VOLARB-only context; CAS decision is independent |

---

## Termination Recommendation

This is the **14th consecutive audit** with Δ=0 new VOLARB trades (strategy retired 2026-05-19,
~225h ago). The dataset is closed at n=885. No cell can reach n≥100. No lever can be triggered.

**Recommended action for user:** Deactivate or re-target scheduled VOLARB audits. The audit
framework should be aimed at the active strategy (CAS_LOWASK / STWA / weather arb) or the
scheduled job should be suspended until `research_status.md` is updated with a new mandate.
Continuing VOLARB audits produces identical no-patch reports with zero actionable output.

If VOLARB is ever re-activated: re-register mandate with new activation timestamp and reset n counters.
