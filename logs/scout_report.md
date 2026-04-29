# Alpha Scout Report — 2026-04-29 00:34 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (7th consecutive session)
**Data:** Quantitative summaries from commits `a82824b`→`5f61ade` (Apr 28 12:32–21:27 UTC)
**Known gap:** `trades.jsonl` logging broken ~19:38–20:19 UTC Apr 28 (fixed in `0235959`)

---

## Investigation 1: Cross-Exchange Lead-Lag

**Status: INCONCLUSIVE**

- Binance both-rising gate reverted in `0ddb49e` (adversarial audit): based on n=43 UP-window trades, below n=100 threshold. WR delta was real (24–36pp) but single-cohort; rejected.
- Mandated 5s delta field still missing: `pre_entry_momentum_pct` logs 1m kline, not 5s spot delta.
- Re-evaluate at n≥100 UP-window trades.

**Action required:** Add `binance_spot_5s_delta` to logging schema. Candidate: `(spot_now - spot_5s_ago) / spot_5s_ago` from Binance WS kline buffer at entry time.

---

## Investigation 2: Token Tick Count (5s window)

**Status: DISCARD**

Winning and losing trades share median `term_tok_tick_count_5s` = 8 — zero separation at any threshold. 5s window is too narrow at 2s scan cadence.

**Action:** Switch to 30s window. `term_tok_tick_count_30s` added in `b5fdc62` (~10h old as of this report). Re-run Investigation 2 once n≥80 trades accumulate with the new field.

---

## Investigation 3: Dead Drift Signature (30s)

**Status: SIGNAL_CANDIDATE**

Prior DISCARD reversed by new TERMINAL-era data:

| Bucket | n | WR | Notes |
|---|---|---|---|
| Flat token \|d30\| < 0.5% | ~subset | 53% | 12pp below overall |
| Overall TERMINAL | ~677 | 65% | Baseline |

12pp WR gap exceeds the 5pp monitoring threshold. Prior gate in `0ddb49e` was reverted because it was derived from TREND-era data (wrong population).

`term_tok_decel_ratio` is the implementation vehicle.

**Action: Do not gate.** Accumulate n≥40 flat-drift TERMINAL trades before any implementation. Field is ~10h old; counts not yet sufficient.

---

## Investigation 4: Asset-Specific Edge

**Status: INCONCLUSIVE**

No per-asset commit data available this cycle; n per bucket unverifiable from commit-embedded summaries. Carry forward from Apr-28 manual report (BTC PF=1.31, SOL PF=1.16, ETH PF=1.01 driven by 0.79–0.81 bucket).

---

## New Signals This Cycle

### BC Hold-Bucket Asymmetry (`149ca66`)

n=126 BC wick events. Hold>35s: FP rate 70–90%; EV of holding instead of BC exit = +$0.70–$1.01/trade in the 18s wick window.

**Status:** SIGNAL_CANDIDATE — n=126 is above the 100-trade floor for the overall finding, but sub-buckets are INDICATIVE. Do not implement a persistence timer yet; log post-confirmation price data first (see BC persistence audit).

### OB Depth Gate (`575012a`)

ob_depth<50 at entry: 45% NO-resolution rate vs <5% above. n=11 — NOISE. Do not gate.

### H21 Entry-Price Correction (`0ddb49e`)

Prior H21 block was based on wrong population (all-hours data). Corrected: H21 n=46, WR=65%, PF=1.19 — unblocked. Block threshold requires n≥100.

---

## Schema Actions Outstanding

| Field | Action | Priority |
|---|---|---|
| `binance_spot_5s_delta` | Add to logging schema | High — blocks Investigation 1 |
| `term_tok_tick_count_30s` | Live since `b5fdc62`; accumulate n≥80 | Medium |
| `term_tok_decel_ratio` | Live since `b5fdc62`; accumulate n≥40 TERMINAL flat-drift trades | Medium |

---

## Priority Queue for Next Cycle

| Priority | Item | Threshold | Status |
|---|---|---|---|
| 1 | Add `binance_spot_5s_delta` logging | — | Not logged |
| 2 | Dead drift (30s) gate | n≥40 flat-drift TERMINAL | ~10h data only |
| 3 | BC hold-bucket persistence | n≥100 per sub-bucket | See BC audit |
| 4 | Tick count (30s) | n≥80 with new field | ~10h data only |
| 5 | OB depth<50 | n≥100 | n=11 only |
