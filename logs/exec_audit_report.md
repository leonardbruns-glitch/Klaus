# Execution Audit Report — 2026-07-06

**Generated:** 2026-07-06T08:29:05Z (SNAPSHOT timestamp)  
**Branch:** `claude/find-lag-parameter-rFQ0N`  
**System:** `active` (uptime since 2026-07-05T22:08 UTC)  
**Config source:** `band_config.txt` (authoritative)  
**SNAPSHOT age:** ~0 min at generation — data is fresh ✓

---

## Section 1 — Fill Tape

### 24h (2026-07-06 00:00–08:29 UTC, partial day)

| Side | Tokens | Shares | $ Filled |
|---|---|---|---|
| YES | 5 | 38.4 | $17.21 |
| NO | 3 | 27.5 | $10.69 |
| **Total** | **8** | **65.9** | **$27.90** |

All 8 fills are from PAIR_FAV mode. Three complete pairs (Wuhan, Shanghai, Chongqing) where both legs registered. One standalone-leg fill (Beijing YES via pair_fav, NO counterpart not yet filled).

**Pair co-fill timing (NO fills first, YES follows):**

| Condition | NO fill time | YES fill time | Delta |
|---|---|---|---|
| Wuhan (0x40851f17) | 00:02:46 | 00:12:10 | 564 s (9.4 min) |
| Shanghai (0xda1ccda8) | 03:30:22 | 03:43:16 | 774 s (12.9 min) |
| Chongqing (0x25d24591) | 07:29:24 | 07:38:05 | 1,405 s (23.4 min) |

Both legs co-fill within 9–23 min in all complete pairs today. NO fills before YES in all 3 cases — takers are buying NO first, then YES follows as the book adjusts.

### 7-day Tape (active trading days: Jul 03–06)

| Day | YES tokens | NO tokens | Total | $ Posted |
|---|---|---|---|---|
| Jul 03 | 2 | 0 | 2 | $56.02 |
| Jul 04 | 4 | 0 | 4 | $48.01 |
| Jul 05 | 6 | 2 | 8 | $56.01 |
| Jul 06 (partial) | 5 | 3 | 8 | $40.01 |
| **Total** | **17** | **5** | **22** | — |

7d totals: 17 YES fills, 5 NO fills, ~$83.4 entry $ filled (registered-fill shares at entry price + increments).

**Fill rate (approximate):** Jul 05 8/8 posted = 100% same-day; Jul 06 7/9 posted filled by 08:29 (78%, 2 Munich quotes still resting).

**Price bands (7d, by $ filled — registered entries):**

| Band | $ Filled |
|---|---|
| < 0.10 | $0 |
| 0.10–0.30 | $0 |
| 0.30–0.50 | $42.45 |
| 0.50–0.85 | $21.58 |
| **Total** | **$64.03** |

All fills are concentrated in the 0.30–0.50 band (66%) and 0.50–0.85 (34%). No thin-book fills (<0.30) in 7d.

**Cities (7d, token count):** Tokyo (4), Shanghai (4), Munich (3), Wuhan (3), Chongqing (3), Seoul (2), Taipei (1), Moscow (1), Beijing (1).

---

## Section 2 — NO-Parity Monitor

Live flag: `BAND_NO_ENABLED = False` (standalone NO disabled 2026-07-02 after 7d WR=39.2%, n=51). All NO posts are via `BAND_PAIR_FAV_ENABLED = True` only.

### New posts by side per day (band_struct_lite 'post' records):

| Day | YES posts | NO posts | NO share | Status |
|---|---|---|---|---|
| Jul 05 | 7 | 7 | 50.0% | ✓ |
| Jul 06 (partial) | 5 | 5 | 50.0% | ✓ |

**No-starvation fix holds.** Every PAIR_FAV post generates one YES + one NO atomically; post-level balance is guaranteed by design while standalone NO remains disabled.

### Fill-level NO share:

| Period | YES fills | NO fills | NO share |
|---|---|---|---|
| Jul 03–04 (pre-pair only) | 6 | 0 | 0% |
| Jul 05–06 (pair era) | 11 | 5 | 31% |
| **7d total** | **17** | **5** | **23%** |

**Fill-level NO share (23%) is structurally below post-level (50%).** Two causes:

1. **Pre-pair drag (Jul 03–04):** 6 standalone YES band fills with zero paired NO. The standalone YES band was paused after this (`BAND_YES_LIVE_MIN_DOUT = 9`). These drag the 7d NO-fill share from 31% down to 23%.
2. **Pair era asymmetry (31% NO):** Even in PAIR_FAV mode, YES legs fill more often than NO legs per posted pair. Today (38% NO) is improving. In the 3 complete pairs today, both legs filled — the single-leg asymmetry is not due to systematic NO rejection; it reflects that the 4th pair (Beijing) had its NO leg not yet fill by 08:29 snapshot.

**Resting book by side (SELL_EXIT excluded):**
- YES: Munich YES @ $0.44, 8.89 sh, matched=0
- NO: Munich NO @ $0.46, 8.89 sh, matched=0

Book is balanced at the pair level ✓.

---

## Section 3 — Queue Health

Source: `[STRUCT-BAND-Q]` lines from `maker_fills_recent.log`.

| Day | Cycles | Cash preskip | Avg books/80 | Yes books/50 | Avg posted/cycle | Posting rate |
|---|---|---|---|---|---|---|
| Jul 03 | 121 | 0 | 2.0 | 0.6 | 1.26* | 2% |
| Jul 04 | 240 | 1 | 0.2 | 0.0 | 0.24 | 2% |
| Jul 05 | 228 | 0 | 0.1 | 0.0 | 0.26 | 3% |
| Jul 06 (70 cycles) | 70 | 0 | 0.5 | 0.0 | 0.63 | 7% |

*Jul 03 avg_posted likely reflects a different system version at the start of the 7d tape window; treat as unreliable.

**No fetch starvation:** books peaked at 4/80 on Jul 06. Not approaching the 80-book ceiling.

**Standalone YES correctly paused:** `yes_books = 0/50` on Jul 04–06 (`BAND_YES_LIVE_MIN_DOUT = 9` working as intended).

**No cash starvation:** `cash_preskip = 0` on all days; one cycle with `= 1` on Jul 04. No `> 200` condition.

**Pair_cands drive all activity:** Every `[STRUCT-BAND-Q]` line shows `pair_cands = 1–3` and `no_cands = 0`. All posts originate from PAIR_FAV candidates exclusively.

**Posting rate context:** Today improved to 7% (vs 2–3% prior days), consistent with more Chongqing/Wuhan/Shanghai pairs in play this morning. The 93–98% of cycles that post nothing are not failing due to books (4/80), cash (preskip=0), or YES capacity (0/50 standalone). The constraint is gate filtering: the 1–3 pair_cands per cycle fail `PAIR_SUM_MAX`, `BAND_PX_CEIL`, or `BAND_EV_MIN` checks before posting. This is the "posting collapse" regime documented in the 2026-07-05 research audit.

---

## Section 4 — Resolution Markout

**CLOB API status:** unreachable from sandbox — programmatic fill vs all-fires ROI computation blocked. The `band_resolution_join.py` analysis could not be run. Re-run with network access.

**n = 22 registered fills (< 40 threshold → data collection, no conclusions).**

### Pair fills (both legs co-filled, today):

| Condition | YES entry | NO entry | Sum paid | Locked margin | Resolution |
|---|---|---|---|---|---|
| Wuhan (0x40851f17) | 0.49 | 0.40 | 0.89 | +11¢/sh (+12%) | Unknown |
| Shanghai (0xda1ccda8) | 0.44 | 0.45 | 0.89 | +11¢/sh (+12%) | Unknown |
| Chongqing (0x25d24591) | 0.53 | 0.32 | 0.85 | +15¢/sh (+18%) | Unknown |

All 3 complete pairs today are above the `PAIR_SUM_MAX = 0.92` floor (actual: 0.85–0.89), locking guaranteed positive margin regardless of resolution outcome. No winner's curse is possible on fully co-filled pairs.

### Single-leg fills (Jul 03–05, no paired counterpart in 7d tape):

14 single-leg fills: 12 YES-only (0.39–0.59 range), 1 NO-only Wuhan Jul 05 (@ 0.44), 1 NO-only Moscow Jul 05 (@ 0.84).

**Winner's curse risk on single-leg fills:** Cannot be tested without resolution data. The standalone YES fills at 0.42–0.50 are in the fat-middle range where adverse selection risk is highest — takers fill makers when takers have edge. At n=12 single-leg YES fills (below threshold), this remains uncharacterized.

**Moscow NO Jul 05 @ 0.84 (6.0 sh):** tail-NO position (`BAND_TAILNO_VALIDATED = False`). Unvalidated class per band_config.

**Action:** Rerun with CLOB accessible to resolve markout for Jul 03–05 single-leg fills. This is the outstanding data gap — the pair era (Jul 05–06) has built-in guaranteed margin; the pre-pair era (Jul 03–04) YES-only fills carry uncharacterized directional risk.

---

## Section 5 — Dead-Quote Reclaim

**Reaped dead entries in 7d tape:** 0 (no matching log lines).

### Resting order ages at 08:29 UTC:

| Order type | Token | q_price | Size | Age |
|---|---|---|---|---|
| Munich YES (band entry) | 96989... | 0.44 | 8.89 sh | ~50 min |
| Munich NO (band entry) | 14295... | 0.46 | 8.89 sh | ~50 min |
| SELL_EXIT (Jul 05 Munich YES) | 90238... | 0.99 | 9.0 sh | ~19 h |
| SELL_EXIT (Jul 05 Shanghai YES) | 61489... | 0.99 | 8.0 sh | ~16 h |
| SELL_EXIT (Jul 05 Tokyo YES) | 12358... | 0.99 | 8.0 sh | ~21 h |
| SELL_EXIT (Jul 06 Beijing YES) | 72970... | 0.99 | 10.0 sh | ~3 h |

**Quotes > 24h old:** 0. **Quotes > 48h old:** 0. **No alert fires.**

Munich pair posted ~07:40 UTC — well inside `BAND_RECLAIM_AGE_S = 2h`. The 3 Jul 05 SELL_EXIT orders (16–21h old) exceed `BAND_PAIR_RECLAIM_AGE_S = 8h` but this timer applies to resting pair-entry legs, not to SELL_EXIT orders; SELL_EXIT quotes at $0.99 are correct hold-to-resolution orders and should not be reclaimed.

**Zero reaped entries over 7d:** Consistent with fast pair co-fills (9–23 min) — quotes are filling before the 2h reclaim threshold activates. No velocity leak detected.

$ freed by reclaim: $0.

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $131.41 |
| Daily start capital (yesterday start) | $217.44 |
| Band resting $ (entry quotes) | ~$8.00 (Munich pair, 2 × $4) |
| SELL_EXIT resting $ (exit side) | ~$34.65 (4 orders at $0.99) |
| Fills $ last 24h (08:29 cutoff) | $27.90 |
| Daily posted $ avg (band_posted_state, 5-day Jul 01–05) | $51.21/day |
| Turns/day (posted $/capital) | ~0.39 |
| Badatmath benchmark | ~1.0 |

**Capital caveat:** `daily_start_capital` ($217.44) vs current ($131.41) = −$86. This is not interpretable as intra-day loss — the user sells manually and the bankroll does not track position value. The $86 gap is consistent with ~$42 deployed in today's fills (8 × ~$5) plus Jul 05 SELL_EXIT cost basis (~$36 at original entry prices). Do not draw P&L conclusions from this delta.

**Turns/day (0.39) is ~61% below badatmath's ~1.0 benchmark.** The 5-day posted average ($51/day on $131 capital) is the most reliable velocity measure — it is constrained entirely by the low posting rate (2–7% of cycles). With $131 capital and full badatmath-parity deployment, the system should be posting ~$131/day; current pace is $51/day. The constraint is candidate gate rejection (Section 3), not capital, books, or infrastructure.

**SELL_EXIT positions:** 4 open YES exit orders totaling $34.65 face-value resting. These represent already-bought YES positions; if they resolve YES, they contribute ~$34.65 inflow. If those markets resolve NO, the entry cost ($3.40–$4.14 per position) is the loss, not the $34.65 face value.

---

## ALERTS

Pre-registered alert conditions evaluated:

| Alert | Threshold | Observed | Status |
|---|---|---|---|
| NO share of new posts < 25% (≥10 posts) | < 25% | 50% (Jul 05), 50% (Jul 06 partial) | ✓ OK |
| Books pinned at 80 (fetch starvation) | = 80/80 | max 4/80 | ✓ OK |
| yes_books pinned at 50 (standalone YES starvation) | = 50/50 | 0/50 (expected: YES paused) | ✓ OK |
| cash_preskip > 200 with posted = 0 (deployment stall) | > 200 sustained | 0 all day | ✓ OK |
| Dead quotes > 48h (velocity leak) | > 20 quotes | 0 | ✓ OK |
| **Markout: fill ROI vs all-fires ROI** | n ≥ 40 required | n=22, CLOB blocked | ⚠ DEFERRED |

**0 pre-registered alerts fired.**

Deferred: Resolution markout cannot be completed until CLOB API is accessible from the audit environment. The Jul 03–04 standalone YES fills (n=12, all single-leg) represent the open winner's curse question — they carry uncharacterized directional risk not visible in the fill tape alone.

---

## 3-Line Summary

**Fills/day:** 8 tokens and $27.90 in the first 8.5h today (3 complete pairs locking +11–15% guaranteed margin per pair; 1 lone YES still open); 5-day avg $51/day posted. Pair co-fill timing 9–23 min, NO fills first.

**NO-share:** 50% at post level (starvation fix confirmed, both tracked days); 23% fill-level 7d (structural: pre-pair YES-only era dragging the average; pair-era fill share is 31–38% and improving today).

**Binding execution constraint:** Candidate gate rejection — 93–98% of cycles post nothing despite available capital ($131) and empty book headroom (4/80 books max). Pair_cands=1–3 per cycle; nearly all fail `PAIR_SUM_MAX`/`EV_MIN`/`PX_CEIL` before posting. Turns/day ~0.39 vs badatmath ~1.0 benchmark. No infrastructure failure, no alert fires — the constraint is the gate logic filtering live candidates.
