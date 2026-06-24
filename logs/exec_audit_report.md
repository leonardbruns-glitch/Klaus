# Execution & Markout Audit
**Date:** 2026-06-24 | **Snapshot:** 2026-06-24T06:56:06Z (age: <1h) | **Status:** ACTIVE  
**Klaus systemd:** active | **Capital:** $211.95 | **Bot uptime since:** 2026-06-24 00:10:06 UTC (restart today)  
**Audit window:** 4d fill tape (Jun 21–24), 6d NO-parity (Jun 19–24), 4d queue health  
**Data note:** maker_fills_recent.log covers Jun 21–24 only (log rolled/truncated before Jun 21); band_config.txt authoritative for live flags.

---

## 1. FILL TAPE (24h + 7d)

### Tracked Fills (MAKER-FILL lines)

**Log window: Jun 21 07:26 UTC → Jun 24 06:56 UTC (~4 days)**

| Metric | 4-day total | Last 24h |
|---|---|---|
| Registered fills (new positions) | 87 | 27 |
| Increment fills (+maker sh) | 80 | 34 |
| All MAKER-FILL events | 180 | 61 |
| $ filled — registered only | $281.87 | $108.24 |
| $ filled — all events | $448.52 | $196.91 |
| YES fills (registered) | 20 (23%) | **0 (0%)** |
| NO fills (registered) | 67 (77%) | **27 (100%)** |

**4-day by price band (registered fills):**

| Band | n | $ |
|---|---|---|
| <0.10 | 5 | $2.93 |
| 0.10–0.30 | 15 | $17.95 |
| 0.30–0.50 | 1 | $2.07 |
| 0.50–0.85 | 65 | $253.10 |
| >0.85 | 1 | $5.82 |

Dominant band: 0.50–0.85 (75% of fills, 90% of $). Last 24h: **100% of fills in 0.50–0.85** — no YES fills, no sub-0.50 fills at all.

**By date:**

| Date | Registered fills | $ (registered) |
|---|---|---|
| 2026-06-21 | 32 | $78.62 |
| 2026-06-22 | 23 | $72.52 |
| 2026-06-23 | 27 | $105.95 |
| 2026-06-24 (to 06:56 UTC) | 5 | $24.78 |

**Top cities (4d, registered):** Dallas 6, Toronto 5, London 5, Shanghai 5, Seattle 4, Ankara 4, Chengdu 4.

**Fill rate (rough):** Posted tokens/day ≈ 33–72 range. Fill events/day ≈ 23–32. Approximately 70–85% of posted positions eventually get taken, but timing mismatch (fills can lag posts by days) makes per-day fill rate unreliable from this alignment.

---

## 2. NO-PARITY MONITOR

Source: band_struct_lite.jsonl `record='post'` entries per day.

| Date | Total posts | YES | NO | NO share | Note |
|---|---|---|---|---|---|
| 2026-06-19 | 56 | 41 | 15 | 26.8% | |
| 2026-06-20 | 50 | 36 | 14 | 28.0% | |
| 2026-06-21 | 72 | 40 | 32 | 44.4% | |
| 2026-06-22 | 32 | 14 | 18 | 56.3% | |
| 2026-06-23 | 46 | **0** | 46 | **100%** | P1 NO-only active |
| 2026-06-24 | 8 | **0** | 8 | **100%** | Partial (n<10 threshold) |

**Formal alert (<25% NO on ≥10 posts):** Not fired. Min NO share was 26.8% (Jun 19), above threshold.

**Context:** 2026-06-23 and 2026-06-24 show 100% NO — this is the opposite of the NO-starvation bug (fixed 2026-06-12). Current state is intentional: commit `feat(BAND): P1 NO-only — no_reserve 0.40->1.00 until $600 (user)` set `BAND_NO_CASH_RESERVE = 1.00`, which starves YES posts entirely until capital reaches $600. Confirmed by all Jun 24 STRUCT-BAND-Q cycles showing `no_resv=1.00` and `yes_resv_skip=46–66 per cycle`.

**Resting book (maker_resting_state, excl. SELL_EXIT):**
- Active YES bids: **0**
- Active NO bids: 4 (Helsinki 0.62, Seattle 0.63, Manila 0.62, Madrid 0.64 — all posted <2h ago)
- SELL_EXIT at 0.99: 37 orders, 403 shares (see §5)

---

## 3. QUEUE HEALTH

Source: STRUCT-BAND-Q lines (840 total across 4 days).

| Date | Cycles | cash\_preskip mean | books mean /80 | books max | yes\_books mean /50 | yes\_books max | posted/cycle | zero-posted | yes\_resv\_skip (recent) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-21 | 199 | 41 | 0.46 | 12 | 0.20 | 6 | 1.66 | 83% | 12 |
| 2026-06-22 | 281 | 96 | 0.19 | 10 | 0.06 | 4 | 0.94 | 94% | — |
| 2026-06-23 | 278 | 74 | 0.24 | 16 | 0.00 | 0 | 2.61 | 91% | — |
| 2026-06-24 | 82 | 124 | 0.09 | 2 | 0.00 | 0 | 1.84 | 93% | 46–66 |

**Registered alerts — none fired:**
- `books ≥ 78` (fetch starvation): 0/840 cycles. Max observed: 16. No regression.
- `yes_books ≥ 48`: 0/840 cycles. Max observed: 6. No regression.
- `cash_preskip > 200 with posted=0`: 0 occurrences. Max cash_preskip observed: 175.

**Key observations:**
- Jun 24 tail: `yes_resv_skip = 46–66` per cycle (most recent 20 cycles). Every cycle is blocking ~50 YES candidates due to `no_resv=1.00`. This is working as designed — not a bug.
- `yes_books = 0.00` on Jun 23–24: fully consistent with NO-only mode. YES book capacity is reserved but never used.
- Cash preskip trending up: median ≈5 (Jun 21) → 116 (Jun 22) → 122 (Jun 24). Capital is being reserved/skipped each cycle but rising faster than deployment burns it — consistent with NO-fill capital returning and few fresh YES posts absorbing it.
- Queue depth growing: ~129 resting orders (Jun 21) → 173 (Jun 24). Fill/reclaim is not clearing the queue as fast as posts accumulate.
- 93% of Jun 24 cycles post zero. Bot is live and scanning; the rarity of actual posts is structural (most NO candidates either already have resting quotes or exceed `BAND_NO_MAX` or are skipped for other reasons).

---

## 4. RESOLUTION MARKOUT

Source: `exit099_live.jsonl` (today) and archived per-day files.

**Completed recycle099 exits (sold at 0.99 before or at resolution):**

| Date | Exits | Total PnL | Avg ROI | Entry range | Notable |
|---|---|---|---|---|---|
| 2026-06-21 | 14 | $76.37 | 186% | 0.17–0.67 | Two deep YES: 0.17→0.99 (482%) |
| 2026-06-22 | 11 | $43.74 | 102% | 0.24–0.93 | One near-par: 0.93→0.99 (6%) |
| 2026-06-23 | 18 | $77.00 | 187% | 0.06–0.97 | Outliers: 0.06→0.99 (1550%), 0.10→0.99 (899%) |
| 2026-06-24 | 3 | $10.35 | 73% | 0.53–0.63 | Normal NO closes |
| **4-day total** | **46** | **$207.46** | | | |

**n=46. Below 100 — trend only, no decision-grade conclusions.**

**Fill quality (winner's curse test):**

Cannot compute fill-vs-all-fires ROI: Polymarket resolution API not called; unresolved positions' outcomes unavailable locally. Resolution markout requires joining fill prices to token resolution outcomes which requires live API access.

What the exits-only data shows:
- All 46 recycle099 exits are wins (by definition — these are positions sold at 0.99 before resolution)
- NO entries (price 0.52–0.71): ROI 50–90%, consistent across all days
- Deep YES entries (price 0.06–0.17): 482–1550% ROI — these are unlikely buckets that resolved correctly; no apparent adverse selection signal in the visible wins
- Jun 22 outlier (entry=0.93) and Jun 23 outlier (entry=0.97): single-digit ROI positions at near-certain bands — tail-NO or final-leg risk, low margin

**Visible untracked loss (not in exit099):**
- 2026-06-24 06:20 UTC: `[USER-WS] UNTRACKED FILL: token=6132737408678472 side=SELL price=0.01 size=497.94` — a position resolved against us and settled at $0.01/share. Approximate loss: cost basis unknown, but at any typical entry price (0.15–0.70), this represents a loss of $74–$349 on a single position. Not reflected in exit099 (which only logs successful 0.99 sales).
- The bot logged this as "UNTRACKED" — likely a pre-restart position (restart at 00:10 UTC) whose in-memory tracker was wiped, so the fill cannot be matched to an open entry.

**Winner's curse verdict:** Inconclusive at n=46. Exits-only data is inherently right-censored (only shows wins). The untracked $0.01 resolution is a confirmed loss from outside the exit099 window. No structural adverse-selection signal visible, but insufficient data for a clean adverse-selection test. Revisit at n≥100 exits with resolution join.

---

## 5. DEAD-QUOTE RECLAIM

**Reaped lines:** 0 in full 4-day log. No dead-entry reclaim events logged.

**Resting order ages:**

| Category | Count | Timestamps | Age |
|---|---|---|---|
| Active NO bids | 4 | Present | <2h (all posted Jun 24 05:23–06:55 UTC) |
| SELL_EXIT at 0.99 | 37 | **Absent** | Unknown |

The 37 SELL_EXIT orders lack `ts` fields in maker_resting_state.json — age cannot be directly determined. Cross-reference via band_posted_state.json: token `69650423459742...` (SELL_EXIT, size=119 shares) appears in the Jun 22 posted token list → **minimum age ≥48h** as of Jun 24 snapshot. This is the largest single SELL_EXIT position (119 shares, $117.81 notional at 0.99).

**>48h count:** At least 1 confirmed. Total unknown without ts data; all 37 SELL_EXIT orders could plausibly date from Jun 22 or earlier (37 > the ≥20 alert threshold) but cannot be confirmed without timestamps.

**No formal alert fires:** Alert requires confirmed count >20 quotes >48h; cannot confirm from available data.

Notable: Total SELL_EXIT backlog = 403 shares @ 0.99 = $399 notional. These are positions awaiting either a taker (someone buys at 0.99) or resolution (if correct, receive $1.00/share). Unmoved matched=0 on all 37 suggests zero fills since the snapshot.

---

## 6. CASH VELOCITY

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $211.95 |
| Active bid capital resting | ~$20 (4 NO bids × ~$5 each) |
| SELL_EXIT notional | $399 (403 shares @ 0.99, cost basis unknown) |
| $ filled — all MAKER-FILL (4d) | $448.52 |
| Avg $ fills/day (4d) | $112.13 |
| Capital turns/day (4d avg) | **0.53** |
| $ filled last 24h (all events) | $196.91 |
| Capital turns last 24h | 0.93 |
| badatmath benchmark | ~1.0 turns/day |

**Daily posted deployment (band_posted_state):**

| Date | $ spent | Tokens posted |
|---|---|---|
| 2026-06-17 | $174.70 | 69 |
| 2026-06-18 | $260.25 | 93 |
| 2026-06-19 | $145.80 | 44 |
| 2026-06-20 | $145.60 | 33 |
| 2026-06-21 | $235.90 | 45 |
| 2026-06-22 | $114.00 | 27 |
| 2026-06-23 | $230.00 | 36 |
| 2026-06-24 (partial) | $40.00 | 7 |

Average daily deployment Jun 19–23: $174.26. Capital turns from fills (0.53×) lag deployment rate (~0.82×), implying some fraction of posted capital is sitting in unfilled resting orders or SELL_EXIT backlog.

**Velocity constraint:** $399 in SELL_EXIT orders is effectively locked capital — it cannot be redeployed until either someone takes the 0.99 sell or the positions resolve. Combined with the P1 NO-only mode (no YES absorption of freed capital), cash preskip is rising each cycle ($124 mean Jun 24) as NO-fill proceeds accumulate but the next NO round hasn't cleared yet.

---

## ALERTS

**Pre-registered alerts that actually fired (only these listed):**

| Alert | Condition | Status |
|---|---|---|
| NO share <25% (≥10 posts) | NO share on any day | **NOT FIRED** — min was 26.8% (Jun 19) |
| books pinned at 80 | any cycle books ≥78 | **NOT FIRED** — max was 16/80 |
| yes\_books pinned at 50 | any cycle yes\_books ≥48 | **NOT FIRED** — max was 6/50 |
| cash\_preskip >200 with posted=0 | deployment stall | **NOT FIRED** — max was 175 |
| >20 quotes >48h | SELL\_EXIT age | **INDETERMINATE** — ts absent in 37 SELL\_EXIT orders; at least 1 confirmed ≥48h (119-share Jun 22 position); cannot determine if total >20 |

---

## Summary

**Fills/day:** 87 registered fills/$282 + 80 increments/$167 = $449 total over 4 days (~$112/day, 0.53 capital turns); last 24h: 61 fill events/$197, all NO, all in 0.50–0.85 band.

**NO share:** 100% of posts are NO since Jun 23 — intentional P1 NO-only mode (`no_resv=1.00`, `yes_resv_skip=46–66/cycle`). No formal <25% alert. YES posts and YES fills are at zero by design until capital reaches $600.

**Binding constraint today:** Cash preskip rising ($124 mean, Jun 24) while 93% of cycles post zero; capital turns at 0.53× vs. 1.0× benchmark. Two structural blockers: (1) $399 in SELL_EXIT backlog not recycling (all 37 orders matched=0 at snapshot), including a ≥48h-old 119-share position; (2) one untracked $0.01 loss resolution (498 shares) confirms adverse outcomes exist outside the wins-only exit099 view.
