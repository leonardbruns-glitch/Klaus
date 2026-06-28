# Band Execution & Markout Audit
**Date:** 2026-06-28 | **Snapshot:** 2026-06-28T07:09:16Z (3 min old — FRESH) | **System:** `active`
**Log window:** 2026-06-26 15:10 UTC → 2026-06-28 07:07 UTC (40h; bot restarted Jun 26 15:08)
**Band config source:** `data/band_config.txt` (authoritative)

---

## Section 1 — Fill Tape

### 24-hour fills (Jun 27 07:07 → Jun 28 07:07 UTC)

| # | Time | City | Side | Token prefix | Shares | @ Price | $ Cost |
|---|---|---|---|---|---|---|---|
| 1 | Jun 27 08:04 | Munich | YES | 616406621944 | 9.0 | 0.51 | $4.59 |
| 2 | Jun 27 09:38 | Beijing | NO | 738702285635 | 7.0 | 0.83 | $5.81 |
| 3 | Jun 27 10:46 | London | NO | 106705757421 | 7.8 | 0.65 | $5.07 |
| 4 | Jun 27 14:04 | London | NO | 534820913164 | 7.5 | 0.68 | $5.10 |
| 5 | Jun 27 16:15 | London | NO | 554237344056 | 7.0 | 0.81 | $5.67 |
| 6 | Jun 27 16:19 | Chengdu | NO | 758095436135 | 7.0 | 0.74 | $5.18 |
| 7 | Jun 27 16:56 | Wuhan | NO | 555065471118 | 8.0 | 0.69 | $5.52 |
| 8 | Jun 28 04:44 | Munich | NO | 152718649601 | 7.0 | 0.72 | $5.04 |
| 9 | Jun 28 06:04 | London | NO | 400597240669 | 7.9 | 0.59 | $4.66 |
| 10 | Jun 28 06:17 | Chengdu | YES | 103216932731 | 9.4 | 0.50 | $4.70 |
| 11 | Jun 28 06:39 | Chengdu | NO | 315836606637 | 9.4 | 0.35 | $3.29 |

**24h totals:** 11 new positions (9 NO, 2 YES) | **$ filled: ~$54.63**
YES fills: $9.29 (17.0%) | NO fills: $45.34 (83.0%)

*Note: entries 10+11 are a matched pair (cond 0x845aac61 — pair_fav Chengdu d+0). The Chengdu merge record at 07:07 confirms pair locked: edge=0.15, locked_pnl=$1.41.*

### 7-day fill tape (full 40h window)

**Total: 27 MAKER-FILL events → 20 new positions + 7 increments**

| Side | New positions | Increments | % of new |
|---|---|---|---|
| NO | 18 | 6 | 90% |
| YES | 2 | 1 | 10% |

By price band (new positions only):
| Band | Count | % |
|---|---|---|
| <0.30 | 0 | 0% |
| 0.30–0.50 | 1 | 5% |
| 0.50–0.85 | 19 | 95% |
| >0.85 | 0 | 0% |

*The single below-0.50 fill is the Chengdu pair-NO leg at 0.35 (paired with YES @0.50; locked edge is 0.15).*

By city (new positions):
| City | NO fills | YES fills | Total |
|---|---|---|---|
| London | 6 | 0 | 6 |
| Chengdu | 5 | 2 | 7 |
| Munich | 4 | 1 | 5 |
| Beijing | 2 | 0 | 2 |
| Wuhan | 2 | 0 | 2 |

**Fill rate (approx):** ~23 tokens posted in window → ~20 registered fills → ~87% fill rate.
*Denominator is imprecise: unfilled orders from late Jun 28 have not resolved yet.*

**Time-to-first-fill (where post ts known):**
- London NO 400597240669: posted Jun 28 ~05:04 (ts 1782624288), filled Jun 28 06:04 → ~60 min
- Beijing NO 152718649601: posted Jun 28 ~05:40 (ts 1782626439), not yet filled as of snapshot
- Munich NO 15271864: posted Jun 28 ~04:37, filled Jun 28 04:44 → ~7 min
- London NO 106705757421: posted Jun 27 10:38, filled Jun 27 10:46 → ~8 min
*Median time-to-fill from available pairs: ~33 min (n=4 pairs, high variance).*

**53 UNTRACKED FILL events (prior session):** WS notified fills on orders placed before the Jun 26 15:08 restart. Includes a `size=627.6` Beijing NO @ 0.167 (nominal ~$104.8 entry value) and settlement-adjacent sells at 0.997–0.999. These are orphaned state — not tracked in current session P&L. No action required, but they confirm prior-session activity was large.

---

## Section 2 — NO-Parity Monitor

**Source:** band_struct_lite.jsonl `post` records + band_posted_state.json, Jun 26–28.
**NO-starvation fix commit:** Jun 12 ('fix(BAND): NO-starvation'). **Verification required.**

| Date | Total posted | YES | NO | YES% | Status |
|---|---|---|---|---|---|
| 2026-06-26 | 10 | 0 | 10 | **0%** | ⚠ ALERT |
| 2026-06-27 | 8 | 1 | 7 | **12.5%** | ⚠ ALERT |
| 2026-06-28 | 5 | 1 | 4 | **20%** | n<10, borderline |

*YES posts both come from **pair_fav** fires (Munich d+0 pair Jun 27, Chengdu d+0 pair Jun 28). Zero standalone YES band posts in the window.*

**ALERT: YES share below 25% on BOTH days with ≥10 posts (0% Jun 26, 12.5% Jun 27).**

Root-cause signal: `[STRUCT-BAND-Q]` shows `yes_books=0/50` on every single cycle across 40h. The YES d+2 band fires ARE computing (band_struct_lite Jun 28 shows `fire, live=true` records for Chengdu/Beijing/Wuhan/London/Munich d+2 YES), but zero YES tokens appear in band_posted_state from these fires. Only pair_fav YES posts reach the book.

**Hypothesis:** BAND_YES_LIVE_MIN_DOUT=2 is enabled and YES d+2 fires are generated, but either:
(a) `yes_resv_skip` counter (rising 0→8 over 40h) indicates YES candidates are being eliminated in the queue stage before firing, OR
(b) The YES d+2 orders are being placed but not tracked in band_posted_state (silent CLOB rejection / state-tracking gap).

The Jun 12 NO-starvation fix may have over-corrected: YES is now severely crowded out in the operational 3-day window. YES exposure flows **only** through pair_fav (d+0 pairs), which fires infrequently. This is a structural book imbalance.

**Resting book (snapshot 07:09 UTC):**
- Active maker bids: 2 orders, both NO (London NO @ 0.59, Beijing NO @ 0.71)
- SELL_EXIT: 10 orders @ 0.99 (resolved/recycled positions)
- YES maker bids in book: **0**

**System reports 0 open positions** — the SELL_EXIT orders at 0.99 are not being counted as open positions (correct; they are exit orders, not entries).

---

## Section 3 — Queue Health

**Source:** 467 `[STRUCT-BAND-Q]` lines, Jun 26 15:10 → Jun 28 07:07

| Metric | Range observed | Alert threshold | Status |
|---|---|---|---|
| books (NO) | 0–9 / 80 | Pinned at 80 = fetch starvation | ✓ OK |
| yes_books | 0 / 50 (always) | Pinned at 50 = YES fetch starvation | ✓ No starvation (but 0 always = structural) |
| cash_preskip | 9 (stable) | >200 sustained with posted=0 | ✓ OK |
| posted/cycle | mostly 0, peaks 104 | | ✓ bursty but expected |
| queue depth | 7–34 (current 22) | | ✓ healthy range |
| no_cands | 18–22 | | ✓ candidate pool healthy |
| pair_cands | 0–1 | | ✓ low but pair fires occasionally |
| yes_resv_skip | 0→8 (growing) | | ⚠ flag |
| cap | $188 → $16 → $66 | | see note |

**No fetch starvation detected.** Books running 0-9 of 80 available slots — NO book fetches are well within capacity. no_cands=18-22 indicates a healthy pool of NO candidates per cycle.

**YES books = 0 throughout.** Not a starvation signal — it means YES bands simply aren't making it into the active book. See Section 2.

**yes_resv_skip rising.** Started at 0 (Jun 26), growing to 7-8 by Jun 28 07:07. This counter represents YES candidates skipped per cycle due to reserve/capital constraints. If this represents the YES d+2 candidates being blocked by BAND_NO_CASH_RESERVE=0.30 (reserving 30% for NO) combined with the capital drop ($188→$16 mid-session), YES candidates would be consistently starved of slots. Cap has since recovered to $66 but yes_resv_skip remains elevated.

**Cap trajectory:** $188 at session start (Jun 26 15:10), fell to $16 range as orders were placed (capital deployed in resting orders), recovered to $60-75 as positions resolved and recycled through exit099. Currently $66 (bankroll.json).

**Cash_preskip = 9 (stable):** Low and consistent throughout. No deployment stall pattern.

**posted=0 most cycles:** Orders are posted in bursts (when new d+1/d+2 markets open or price moves trigger fire), not every cycle. This is normal for the band strategy.

---

## Section 4 — Resolution Markout

**Source:** exit099_live.jsonl 2026-06-27 (5 records). No exit099_live.jsonl found for Jun 28 (none created yet).

**All resolved positions from Jun 27 data:**

| Token (prefix) | City | Side | Entry | Shares | Exit | PnL | ROI |
|---|---|---|---|---|---|---|---|
| 72542285... | Chengdu | NO | 0.73 | 6.0 | 0.99 | $1.82 | +35.6% |
| 63269744... | Wuhan | NO | 0.55 | 9.0 | 0.99 | $4.04 | +80.0% |
| 51058967... | Munich | NO | 0.82 | 6.0 | 0.99 | $1.11 | +20.7% |
| 58770758... | Munich | NO | 0.60 | 7.99 | 0.99 | $3.26 | +65.0% |
| 61640662... | Munich | YES | 0.51 | 5.0 | 0.99 | $4.32 | +94.1% |

**n=5. Data collection tier — no edge conclusions.**

5/5 exits at 0.99 = all positions resolved as WINNERS (NO tokens where outcome did not occur; YES token where outcome did occur). Win rate: 100% on n=5, meaningless statistically.

Average ROI on resolved positions: **+59.1%** (n=5)
Range: +20.7% (Munich NO @0.82) to +94.1% (Munich YES @0.51)

**Winner's curse test:** Cannot perform the all-fires vs filled-legs comparison — `band_resolution_join.py` requires full `band_struct.jsonl` files (>16MB/day, not available via API slice). The band_struct_lite contains fire summaries only, not individual leg outcomes. Full markout requires: reconstruct full band_struct from lite files OR access the parquet exports. Flagged as incomplete; re-run when paths.parquet/entries.parquet are regenerated.

**Qualitative signal:** Entry prices for filled NO legs (0.55–0.84) are consistent with the strategy hypothesis that high-odds NO positions (opponent likely to not hit the mode) win. The Munich YES @0.51 fill is a pair leg completing a locked-edge trade — not an adverse selection signal.

**No winner's curse detected in available data, but n is too small to rule it out.**

---

## Section 5 — Dead-Quote Reclaim

**Source:** maker_fills_recent.log (all 548 lines), maker_resting_state.json

**Reaped dead entries:** **0** (zero `reaped dead entry` lines in full 40h log)

**Active maker quotes (resting state, as of 07:09 UTC):**

| Order | City | Side | q_price | Size | Matched | Remaining | Age |
|---|---|---|---|---|---|---|---|
| 0x3f5e... | London | NO | 0.59 | 8.47 | 7.92 | 0.55 sh | ~2h05m |
| 0x9129... | Beijing | NO | 0.71 | 7.04 | 0.00 | 7.04 sh | ~1h27m |

Both orders are **<2h old** — below BAND_RECLAIM_AGE_S=7200s threshold. No reclaim should have fired, and none did. ✓

**London NO** is 93.5% filled (matched=7.92 of 8.47). Fill likely completed to 7.92 immediately but residual 0.55 sh is still resting. This is normal.

**SELL_EXIT orders (10):** These are positions exiting at 0.99. No timestamps in state for these orders. If any are >48h old and stuck at 0.99 without filling (e.g., market never resolved), they would represent a velocity leak. Cannot confirm ages without timestamps. The system_status shows 0 open positions — system appears to be tracking these as closed.

**No quotes >24h old identified in resting state.** No ALERT.

**Reclaim engine health:** BAND_RECLAIM_AGE_S=2h, BAND_RECLAIM_PER_CYCLE=10 books/cycle. With only 2 active maker bids (both <2h old), reclaim correctly has nothing to reap. Engine is dormant-correct, not stalled.

---

## Section 6 — Cash Velocity

**From bankroll.json (saved 2026-06-28 06:43 UTC):**
- Capital: **$65.79**
- total_pnl: -$57.19 (cumulative, includes pre-BAND strategy losses — do not interpret as band P&L)
- consecutive_wins: 4
- total_trades: 2994

**Capital breakdown (estimated):**
| Component | Value |
|---|---|
| Capital available | $65.79 |
| Active maker bids | ~$5.32 (London $0.32 residual + Beijing $5.00) |
| SELL_EXIT positions (entry cost est.) | ~$35–45 (10 positions, avg 6.7 sh @ avg 0.65 entry) |
| Undeployed | ~$15–25 |

**24h fills: ~$54.63** (11 positions filled, as detailed in Section 1)

**Capital turns/day:** $54.63 / $65.79 = **0.83 turns/day**

**Benchmark:** badatmath ~1.0 equity turns/day at 10-20% ROI/turn. Klaus is at 0.83 — **17% below benchmark.**

The gap vs badatmath is likely structural: badatmath runs both YES and NO at full frequency, with ~50/50 YES/NO book balance. Klaus YES posts are almost entirely absent (Section 2) — roughly half the potential book is idle. If YES d+2 posts were running at target, turns/day would approach 1.0.

**Resolved P&L (Jun 27 exit099 sample, n=5):**
Total locked PnL from 5 exits: $14.55 over ~12h active window = ~$29.10/day equivalent P&L flow
Average per resolved position: $2.91

---

## ALERTS

Pre-registered alerts that fired:

### ALERT 1: YES share of new posts < 25% on days with ≥10 posts
- **Jun 26:** 10 posts, 0 YES → **0% YES share** ← FIRED
- **Jun 27:** 8 posts, 1 YES (pair_fav only) → **12.5% YES share** ← FIRED
- Root cause: YES d+2 standalone bands firing (`live=true` in band_struct_lite) but zero YES tokens reaching band_posted_state. `yes_books=0/50` in every STRUCT-BAND-Q cycle confirms YES books are empty throughout. Only pair_fav YES orders reach the book. The Jun 12 NO-starvation fix holds for NO (NO is well-represented) but YES is now the starved side.

### ALERT 2: yes_resv_skip counter rising
- Growing 0→8 per cycle by Jun 28, suggesting YES d+2 candidates are being eliminated in queue scoring before fires. Not a standalone pre-registered alert but directly explains Alert 1.

*(No alert fired for: books pinned at 80, cash_preskip >200 with posted=0, dead quotes >48h.)*

---

## 3-Line Summary

**Fills/day:** ~13 fill events/day (11 distinct new positions/day); $ filled ~$54.63 in 24h; 0.83 turns/day vs 1.0 benchmark; all fills 0.50–0.85 band except one pair-NO leg at 0.35.

**NO-share:** 90% of posts are NO (0% YES on Jun 26, 12.5% Jun 27). YES d+2 standalone bands fire live but produce zero resting orders — `yes_books=0/50` every cycle. Only pair_fav YES (d+0) posts live, ~1/day. Jun 12 NO-starvation fix over-corrected: YES is now the starved side.

**Binding execution constraint:** YES band orders are not reaching the CLOB book despite `live=true` fire signals in the shadow logger. `yes_resv_skip` rising (8 as of 07:07) points to capital-reserve gating or queue-stage elimination — the YES d+2 engine is firing into a void. Until this is diagnosed, Klaus is posting ~half of badatmath's book depth, and YES-side edge is captured only via infrequent pair_fav events.
