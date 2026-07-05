# Exec Audit Report — 2026-07-05T07:11Z

**Snapshot age**: 7 min (2026-07-05T07:04:40Z → audit at 07:11Z) — FRESH  
**Klaus systemd**: active  
**Data sources**: data-mirror branch via GitHub MCP; fill tape covers 2026-07-02T07:07Z onward (log reset at bot restart); band_struct_lite for 2026-07-01 through 2026-07-05  

**Active engines (from band_config.txt — authoritative):**
- `BAND_PAIR_FAV_ENABLED = True` — sole active posting engine
- `BAND_NO_ENABLED = False` — standalone NO disabled 2026-07-02 (EVOLVE rail-halt, n=51 WR 39.2%)
- `BAND_YES_LIVE_MIN_DOUT = 9` — standalone YES paused 2026-07-03 (9 = never fires)
- `BAND_LIVE = True`; base_stake $3.0 (YES legs), no_stake $5.0 (NO legs)

---

## §1 — Fill Tape

### Coverage note
Fill log starts 2026-07-02T07:07Z (bot restart/log rotation). Effective window: **3.5 days** (not 7d). No fills data exists for 2026-06-28 through 2026-07-01.

Total fills in log: **24** (16 `registered` new positions + 8 `maker_sh` partial add-ons)

### 24-hour window (since 2026-07-04T07:11Z)

| Side | Fills | Shares | Notional |
|---|---|---|---|
| YES | 6 | 36.5 | **$16.84** |
| NO | 1 | 1.0 | **$0.44** |
| **Total** | **7** | **37.5** | **$17.28** |

Fill-side NO-share (24h): **14%**

Price band distribution (24h):

| Band | Fills | Notional |
|---|---|---|
| < 0.10 | 0 | $0.00 |
| 0.10–0.30 | 0 | $0.00 |
| 0.30–0.50 | 4 | $8.77 |
| 0.50–0.85 | 3 | $8.51 |
| > 0.85 | 0 | $0.00 |

Cities (24h): Munich $4.06, Seoul $4.45, Shanghai $3.78, Taipei $4.29, Tokyo $0.26, Wuhan $0.44

### 7-day window (effective: 2026-07-02 to 2026-07-05)

| Side | Fills | Shares | Notional |
|---|---|---|---|
| YES | 19 | 99.4 | **$46.05** |
| NO | 5 | 27.9 | **$13.62** |
| **Total** | **24** | **127.3** | **$59.67** |

Fill-side NO-share (7d): **21%** (consistent with prior audit's 22%)

Price band distribution (7d):

| Band | Fills | Notional |
|---|---|---|
| < 0.10 | 0 | $0.00 |
| 0.10–0.30 | 0 | $0.00 |
| 0.30–0.50 | 17 | $36.81 |
| 0.50–0.85 | 7 | $22.86 |
| > 0.85 | 0 | $0.00 |

Cities (7d): London $12.33 (5 fills), Munich $13.33 (4 fills), Beijing $3.96 (4 fills), Chengdu $8.01 (3 fills), Wuhan $5.03 (3 fills), Tokyo $4.49 (2 fills), Seoul $4.45 (1), Taipei $4.29 (1), Shanghai $3.78 (1)

**Peak day**: 2026-07-03 — 17 of 24 total fills. The only day with meaningful book depth (mean 1.28/80 books used, 39% of cycles with ≥1 resting quote). Explains clustered fill activity.

**Fill-side YES dominance**: 79% of fills by count, 77% by notional. Persistent across the window. See §4 for markout implications.

---

## §2 — NO-Parity Monitor

**Method**: Post counts from `band_struct_lite.jsonl` `record="post"` per day; resting book from `maker_resting_state.json` (SELL_EXIT excluded). Alert: NO-share of posts < 25% on days with ≥10 posts.

| Date | YES posts | NO posts | Total | NO-share | ≥10 posts? | Alert |
|---|---|---|---|---|---|---|
| 2026-07-01 | ~1 | ~13 | ~14 | ~93% | YES | CLEAR (NO > 25%) |
| 2026-07-02 | 2 | 3 | 5 | 60% | NO | — |
| 2026-07-03 | ~4–5 | ~4–5 | 9 | ~47–50% | NO | — |
| 2026-07-04 | 6 | 6 | 12 | **50%** | YES | CLEAR |
| 2026-07-05 | 2 | 2 | 4 | 50% | NO (partial) | — |

_2026-07-01: pre-BAND_NO_ENABLED=False; dominated by standalone fire_no posts. 2026-07-03: estimated from token count=9 in band_posted_state; pair_fav dominant after BAND_NO halt; lite file too large to inline._

**Resting book (excl. SELL_EXIT)**:
- Active YES resting: **0**
- Active NO resting: **0**
- Sole resting order: 1× SELL_EXIT Munich YES @ $0.99 × 6.0 sh = $5.94 notional, age ~8h

**Structural note**: With pair_fav as the sole engine, YES and NO legs post simultaneously per firing event — parity is mechanically enforced at 50/50. The 2026-06-12 NO-starvation fix holds; the remaining risk is pair_fav condition starvation (not config asymmetry).

**NO-parity alert**: NOT fired. NO-share ≥ 25% on all qualifying days.

---

## §3 — Queue Health

Source: 659 `[STRUCT-BAND-Q]` cycles, 2026-07-02 through 2026-07-05 (4 partial days).

| Date | Cycles | cash_preskip (mean) | books (mean/80) | yes_books (mean/50) | posted/cycle | books max |
|---|---|---|---|---|---|---|
| 2026-07-02 | 136 | 0.00 | 0.01 | 0.00 | 0.419 | 2/80 |
| 2026-07-03 | 207 | 0.00 | 1.28 | 0.37 | 0.787 | 6/80 |
| 2026-07-04 | 240 | 1.10 | 0.19 | 0.00 | 0.242 | 6/80 |
| 2026-07-05 | 76 | 0.78 | 0.05 | 0.00 | 0.053 | 2/80 |

**No capacity alerts**: books peaked at 6/80 (7.5%); yes_books peaked at 4/50 (8%). Neither pinned near ceiling.

**No cash_preskip alert**: max mean ~1.10. Never approached 200.

**Near-zero book pattern**: books = 0 in 61–99% of cycles across all days. The system scans correctly but finds minimal CLOB book depth to pair against on most cycles. This is a market-liquidity condition, not a fetch-starvation regression.

**2026-07-05 posting collapse**: 76 cycles so far at 0.053 posts/cycle = ~4 posts in 7h. Compare to 0.787/cycle on 2026-07-03 (best day). Books also near-zero today (97% of cycles = 0). Pair_fav conditions are not presenting — sum_gate rejections dominate (consistent with md_shadow records showing sum_ask ≥ 0.85 blocking d+1/d+2 city slots).

---

## §4 — Resolution Markout (Fill Quality / Winner's Curse)

**n = 24 fills (n < 40) → DATA COLLECTION PHASE. No conclusions drawn.**

Full resolution markout requires `band_resolution_join.py` against local shadow logs. Condition IDs in the fill tape are 4-byte truncated hex (e.g. `cond=0x454b22f4`) — insufficient for direct CLOB resolution API. Complete joins deferred to when local shadow is accessible.

**Preliminary directional observation (informational only, n=24)**:

All 24 fills are in the 0.30–0.85 fat-middle — peak taker-fee territory (~3.15% at 50% odds). Specifically, 71% of fills land in 0.30–0.50: as maker buying YES at these prices, we expect to be paid $1.00/share if YES resolves. At 0.40 entry, implied win rate break-even (net of fees) is approximately 43%.

Fill-side YES dominance (79% YES, persistent across 3.5 days) is the primary quality flag. Two readings:

1. **Benign**: pair_fav YES legs are priced more competitively (closer to best bid) and attract taker flow naturally.
2. **Winner's curse**: takers preferentially hit YES because they hold an informational edge (e.g. intraday weather signal). If our filled YES positions resolve NO at rates meaningfully above their entry-price-implied probability, adverse selection is confirmed.

Flag for next audit when n reaches 40. At that point, compare realized win rate on filled YES vs. simulated win rate on all-fires YES for the same city/days_out/price-band slice.

**Status**: INCONCLUSIVE (n < 40). Monitor.

---

## §5 — Dead-Quote Reclaim

- `reaped dead entry` lines in 7d log: **0**
- Resting orders > 24h: **0** (only resting order is SELL_EXIT Munich YES, age ~8h)
- Resting orders > 48h: **0**

`BAND_RECLAIM_AGE_S = 7200` (2h) is configured for entry bids; `BAND_PAIR_RECLAIM_AGE_S = 28800` (8h) for pair legs. Zero reclaim log lines have appeared since the log window began 2026-07-02. Possible interpretations: (a) all entry bids filled or aged out cleanly within the 2h window without the WARNING-level reclaim log being reached, or (b) reclaim events log at a different severity not captured in this tape. The near-empty resting book (0 active maker positions) is consistent with normal cycling.

**Alert (>20 quotes older than 48h)**: NOT fired. Zero qualifying quotes.

---

## §6 — Cash Velocity

| Metric | Value | Notes |
|---|---|---|
| Capital | $44.92 | bankroll.json; manual sells excluded from PnL |
| Resting $ | $5.94 | SELL_EXIT only; 0 active maker positions |
| Fills $ (24h) | $17.28 | YES $16.84 + NO $0.44 |
| Fills $ (7d log) | $59.67 | 3.5-day effective window (~$17/day avg) |
| Turns/day (24h basis) | **0.38×** | $17.28 ÷ $44.92 |
| badatmath benchmark | ~1.0× | target equity turn/day |

**Velocity at 38% of benchmark.** Structural causes:
- `BAND_NO_ENABLED=False` removes ~50% of historically intended posting volume
- `BAND_YES_LIVE_MIN_DOUT=9` removes standalone YES
- pair_fav only fires when `qy + qn ≤ 0.90` for both legs simultaneously — sum_gate blocks most city/day slots (observed: `sum_gate` is the 2nd-most-common md_shadow reject reason)

2026-07-05 is the lowest-velocity session: 4 posts, 1 fill, $0.44 notional in 7h. If sustained through day-end, this will be the lowest-fill day of the log window.

**Capital note**: `daily_start_capital = $87.17` vs current $44.92 reflects manual owner withdrawals, not strategy losses. Do not read as ruin signal.

---

## Alerts

Pre-registered alerts that fired this run: **none**

| Check | Result |
|---|---|
| NO posts < 25% on days ≥10 posts | CLEAR — 50% on 2026-07-04 |
| Books pinned at 80 | CLEAR — max 6/80 |
| yes_books pinned at 50 | CLEAR — max 4/50 |
| cash_preskip > 200 sustained with posted=0 | CLEAR — max ~1.1 mean |
| >20 quotes older than 48h | CLEAR — 0 quotes in resting book |

---

## Summary

**Fills/day**: ~7 fills/day equivalent over the 3.5-day effective log window. 24h rate: 7 fills, $17.28 notional, 0.38× equity turns vs 1.0× badatmath benchmark.

**NO-share (posts)**: 50% on both qualifying days — mechanically guaranteed by pair_fav-only posture. Fill-side NO-share is 21% (persistent YES-dominant fill pattern); not a post-parity alert but warrants markout scrutiny at n ≥ 40.

**Binding execution constraint today**: POSTING RATE COLLAPSE. 2026-07-05 shows 0.053 posts/cycle (4 posts, 1 fill in 7h) — the session floor. With pair_fav as the sole engine and resting book empty, zero capital is currently working. Throughput recovery requires pair_fav conditions to present (sum_gate clearing simultaneously for YES + NO legs in the same city/day slot) or re-enabling an additional posting engine.
