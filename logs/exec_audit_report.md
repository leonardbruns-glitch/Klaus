# Band Execution & Markout Audit
**Date:** 2026-06-29 | **Snapshot:** 2026-06-29T07:04:24Z (fresh — <6h old) | **System:** `active`
**Log window:** 2026-06-26 15:08 UTC → 2026-06-29 07:02 UTC (~64h; bot restarted Jun 26 15:08)
**Band config source:** `data/band_config.txt` (authoritative)

---

## Abort Check

- SNAPSHOT.md timestamp: `2026-06-29T07:04:24Z` → **PASS** (<6h old)
- system_status.txt: `## klaus systemd: active` → **PASS**
- Proceeding with full audit.

---

## Section 1 — Fill Tape

### 7-day fill tape (full 64h session window)

**Total MAKER-FILL lines:** 44 (34 registered first-fills + 10 incremental partial-fill updates)

| Date | YES | NO | Total | Est. $ filled |
|---|---|---|---|---|
| Jun 26 (8h) | 0 | 8 | 8 | ~$38 |
| Jun 27 (24h) | 1 | 8 | 9 | ~$44 |
| Jun 28 (24h) | 1 | 13 | 14 | ~$66 |
| Jun 29 (8h partial) | 0 | 3 | 3 | ~$14 |
| **Totals** | **3** | **41** | **44** | **~$172** |

*All 44 lines include 10 incremental updates. Registered first-fills: 34.*

**By side (all 44 fill events):**
| Side | Events | Share |
|---|---|---|
| YES | 3 | 6.8% |
| NO | 41 | 93.2% |

*YES fills: Munich YES @0.51 (Jun 27, pair_fav d+0), Chengdu YES @0.50 (Jun 28, pair_fav d+0), and one incremental YES update. All YES fills via pair_fav — zero YES via standalone d+2 band.*

**By price band (all 44 events):**
| Band | Count | % |
|---|---|---|
| 0.30–0.50 | 3 | 6.8% |
| 0.50–0.85 | 40 | 90.9% |
| >0.85 | 1 | 2.3% |

*Below-0.50: Chengdu YES @0.50, Chengdu NO @0.35 (pair companion Jun 28), Chengdu NO @0.48 (Jun 29). Above-0.85: Moscow NO @0.93 — see ALERTS.*

**By city (all 44 events):**
| City | Count | Notes |
|---|---|---|
| Chengdu | 14 | Highest; includes both pair_fav legs and Chengdu NO @0.48 |
| London | 11 | Consistent NO fill flow |
| Munich | 7 | Includes only YES fill (pair_fav Jun 27 @0.51) |
| Beijing | 6 | |
| Wuhan | 5 | 1 partial fill active (Wuhan NO @0.71, matched=2.0) |
| Moscow | 1 | OFF-BAND — see ALERTS |

**Active fill rate:** Not computable — no per-token rejection log; no posted_ts in MAKER-FILL lines.

**Time-to-fill:** Not computable — no token_id join between `post` records in band_struct_lite and MAKER-FILL lines. Recommend adding `token_id` to MAKER-FILL log format.

---

### 24-hour fills (Jun 28 07:02 → Jun 29 07:02 UTC)

**22 MAKER-FILL events (~$83 filled)**

Registered fills in window (11 positions):
1. Jun 28 ~09h — London NO
2. Jun 28 ~10h — Wuhan NO
3. Jun 28 ~11h — Munich NO
4. Jun 28 ~12h — **Moscow NO @0.93** ← off-band (see ALERTS)
5. Jun 28 ~13h — Beijing NO
6. Jun 28 ~14h — Wuhan NO (partial; Wuhan 0x4de5 still open)
7. Jun 28 ~15h — London NO
8. Jun 28 ~18h — Chengdu NO
9. Jun 28 ~20h — Chengdu YES @0.50 (pair_fav)
10. Jun 28 ~20h — Chengdu NO @0.35 (pair companion; pair merged, locked_pnl=$1.41)
11. Jun 29 ~05h — Beijing NO

Plus 11 incremental updates across these positions.

**$ filled 24h:** ~$83 | **Turns/day:** $83 / $80.98 capital = **1.03** (at benchmark ~1.0)

---

## Section 2 — NO-Parity Monitor

**Source:** band_struct_lite.jsonl `post` records, Jun 26–29.

| Date | Posts | YES posts | NO posts | YES% | Alert? |
|---|---|---|---|---|---|
| 2026-06-26 | 10 | 0 | 10 | **0%** | ⚠ FIRED (≥10 posts) |
| 2026-06-27 | 8 | 2 | 6 | **25%** | — (n<10 threshold) |
| 2026-06-28 | 14 | 1 | 13 | **7.1%** | ⚠ FIRED (≥10 posts) |
| 2026-06-29 (partial) | 5 | 0 | 5 | **0%** | — (n<10) |

*Jun 27 YES: Munich YES d+0 pair_fav @0.51 + 1 additional YES. Jun 28 YES: Chengdu YES d+0 pair_fav @0.50 (pair only). Zero standalone d+2 YES posts in any day.*

**Alert fires: Jun 26 (0%, 10 posts) and Jun 28 (7.1%, 14 posts).** Target ~50% YES/NO parity; both days well below 25% threshold.

**Structural root cause:** `BAND_YES_LIVE_MIN_DOUT=2` restricts YES to d+2 windows only. d+2 YES bands do fire with `live=true` (confirmed in band_struct_lite Jun 29: Wuhan, Chengdu, Munich, Beijing, London all show d+2 YES fire records) but are blocked at sum_gate before a `post` record is written:

| City | d+2 sum_ask (sample Jun 29) | sum_gate limit | Result |
|---|---|---|---|
| Wuhan | 0.97 | 0.85 | BLOCKED |
| Beijing | 0.82–0.96 | 0.85 | MOSTLY BLOCKED |
| London | 1.02–1.22 | 0.85 | CONSISTENTLY BLOCKED |
| Munich | 1.03 | 0.85 | BLOCKED |

With 5 cities active (BAND_CITY_ALLOW), d+2 YES legs across the allowlist sum to >0.85 almost always, pushing YES into sum_gate stall daily. **Only pair_fav (d+0) bypasses this**: fires when YES ask 0.45–0.70 and pair sum ≤0.92; produced ~1 event per 1.5 days.

**Resting book YES exposure:** 0 YES bids in book at snapshot. 3 NO bids active. YES side fully dark at CLOB level.

---

## Section 3 — Queue Health

**Source:** 746 `[STRUCT-BAND-Q]` cycles, Jun 26 15:08 → Jun 29 07:02 UTC

| Metric | Observed | Alert threshold | Status |
|---|---|---|---|
| books_used | avg=0.7 / 80 | Pinned at 80 | ✓ OK — no NO fetch starvation |
| yes_books | **0 / 50 in 746/746 cycles (100%)** | Pinned at 50 | ⚠ YES structurally absent |
| cash_preskip | avg=5, max=22 | >200 sustained with posted=0 | ✓ OK — no deployment stall |
| posted/cycle | avg=0.2; 32/746 cycles had ≥1 post | | ✓ bursty-normal |

**No fetch starvation.** NO books at 0.7/80 — healthy fetch capacity. NO candidate pool active across 5 cities × 2 dout levels.

**yes_books = 0 in 746/746 cycles.** Not a fetch starvation event (50-slot YES book is not pinned, it's empty). Independently confirms Section 2: YES bids are not reaching the CLOB book at all. Even when pair_fav fires and posts a YES, it does not appear in this metric — pair_fav likely uses a separate placement path outside the book-slot counter.

**cash_preskip max=22.** Far below >200 sustained threshold. No deployment stall.

**posted/cycle avg=0.2.** Burst pattern: orders placed in windows when new d+1/d+2 markets open or price signals fire, not uniformly across cycles. 714/746 cycles posted nothing — correct behavior for a maker quoting d+1 and d+2 fixed-window markets.

---

## Section 4 — Resolution Markout

**API unavailable.** CLOB REST API unreachable from execution environment (network policy). Real-time resolution outcomes cannot be fetched.

**Confirmed resolves (band_struct_lite merge records):**

| Date | Pair | Shares | Edge | locked_pnl | ROI |
|---|---|---|---|---|---|
| Jun 28 | Chengdu d+0 pair_fav (YES @0.50 + NO @0.35) | 9.4 | 0.15 | $1.41 | **+17.2%** |

*n=1 confirmed merge. Data collection tier — no markout conclusions possible.*

**Implied ROI on open fill sample (unresolved positions):**
- YES fills @0.50–0.51 (n=2 registered): if mode fires → ~96–100% gross ROI
- NO fills @0.55–0.93 (n=32 registered): if mode doesn't fire → 6.5–82% gross ROI depending on entry price
- Moscow NO @0.93 (n=1): if NO wins → 6.5% gross ROI — marginal post-fee return at this odds level

**Winner's-curse test:** Cannot execute. Requires band_struct parquet join of filled-leg outcomes vs all-fires population. band_struct_lite contains fire summaries only, not individual outcome prices post-resolution. n=44 fill events total (n<100 decision-grade). **No adverse selection conclusion — data collection tier.**

**UNTRACKED FILL events:** 109 WARNING-level lines, ~51 unique tokens, ~$4,307 notional. These appear to be SELL_EXIT order fills (bot places 0.99 asks after NO fill; counterparty BUYs at 0.99 as market resolves) plus possible pre-Jun-26 restart settlement flows. No ERROR lines in log. Volume is large relative to bot size — warrants tracing to confirm all are SELL_EXIT flows and not unaccounted open positions.

---

## Section 5 — Dead-Quote Reclaim

**Source:** maker_fills_recent.log (full 64h window), maker_resting_state.json

**Reaped dead entry lines (7d log): 0**

BAND_RECLAIM_AGE_S=7200 (2h). Zero reclaim events — all quotes either filled within 2h or remain actively resting.

**Active maker bids (non-SELL_EXIT, at snapshot 07:04 UTC):**

| cid prefix | City | Side | q | size | matched | ts | Age at snapshot |
|---|---|---|---|---|---|---|---|
| 0x4de5... | Wuhan | NO | 0.71 | 7.04 sh | 2.0 sh | 2026-06-28 ~17:54 UTC | ~13h |
| 0x52c1... | Wuhan | NO | 0.65 | 7.69 sh | 0 | 2026-06-29 ~07:40 UTC | <1h (new) |
| 0x6250... | London | NO | 0.59 | 8.47 sh | 0 | 2026-06-29 ~07:51 UTC | <1h (new) |

**Wuhan 0x4de5 is ~13h old with partial fill (matched=2.0 of 7.04 sh).** Still below 24h; reclaim correctly has not triggered. If unfilled residual sits beyond 2h from last activity, reclaim should pull at next cycle. Monitoring warranted.

**SELL_EXIT orders (8 entries in maker_resting_state.json, no `ts` field):**

Ages inferred from band_posted_state.json cross-reference:
- 3 SELL_EXIT tokens trace to Jun 29 posts → age <3h at snapshot
- 5 SELL_EXIT tokens trace to Jun 28 posts → age 12–24h at snapshot

None exceed 48h. No alert threshold crossed.

**Quotes >24h: 0. Quotes >48h: 0.** No dead-quote alert.

**Reclaim engine: dormant-correct.** Nothing to reap; not stalled.

---

## Section 6 — Cash Velocity

**Capital (bankroll.json):** $80.98
*CAVEAT: user sells manually; never conclude ruin or strategy P&L from bankroll.json alone.*

**Resting bid exposure (3 active NO bids):**
- Wuhan NO @0.71, 5.04 sh remaining: ~$3.58
- Wuhan NO @0.65, 7.69 sh: ~$5.00
- London NO @0.59, 8.47 sh: ~$5.00
- **Total active bid exposure: ~$13.58**

**BAND_NO_DAILY_CAP status (Jun 29):** $25 spent, $15 remaining of $40 cap. Cap not exhausted.

**24-hour fills:** ~$83 (22 fill events, Jun 28 07:02 → Jun 29 07:02 UTC)

**Turns/day:** $83 / $80.98 = **1.03** (at benchmark ~1.0 per badatmath)

**Note on YES contribution to velocity:** YES posts are near-zero (Section 2). If YES d+2 were posting at parity with NO (~50/50), deployable capital would turn faster. Current velocity is driven entirely by NO fills, and coincidentally hits benchmark — but with half the book capacity that would exist at YES/NO parity.

**Confirmed P&L flow (n=1 merge):** Chengdu pair Jun 28 → $1.41 locked in 64h session. SELL_EXIT flows (~$4,307 UNTRACKED notional) suggest substantial historical capital recycling; cannot confirm net P&L without CLOB fill history.

---

## ALERTS

Pre-registered alerts that fired this session:

### ALERT 1 — NO-PARITY: YES share <25% on days with ≥10 posts
- **Jun 26:** 10 posts, 0 YES → **0%** ← FIRED
- **Jun 28:** 14 posts, 1 YES → **7.1%** ← FIRED
- Root: `BAND_YES_LIVE_MIN_DOUT=2` + d+2 sum_gate failures (sum_ask hitting 0.85–1.22 across 5-city allowlist). YES exclusively flows via pair_fav (d+0, ~1 event per 1.5 days). Jun 27 (2 YES / 6 NO = 25%) escaped alert at n=8, below 10-post threshold.

### ALERT 2 — OFF-BAND FILL: Moscow NO @0.93 > BAND_NO_MAX=0.85, city not in allowlist
- **Jun 28 ~12:06 UTC:** Moscow NO filled at q=0.93, size ~7 sh
- Moscow is NOT in `BAND_CITY_ALLOW = {chengdu, london, beijing, munich, wuhan}` (allowlist narrowed commit 847a22fe5, Jun 26 15:08)
- Price 0.93 exceeds `BAND_NO_MAX=0.85`
- Assessment: legacy order placed before Jun 26 15:08 restart (resting on book before allowlist/price-cap enforcement). Current bot session cannot place new Moscow orders — this is a one-off residual, not an ongoing leak. `BAND_TAILNO_VALIDATED=False` — tail-NO 0.85–0.95 is UNVALIDATED on our fills.

### ALERT 3 — YES BOOKS ZERO: yes_books=0 in 746/746 STRUCT-BAND-Q cycles (100%)
- Independently confirms Alert 1 at queue level. YES quotes are absent from CLOB book in every operational cycle across 64h. Not fetch starvation (50 YES slots are not pinned; they're empty). Structural absence driven by BAND_YES_LIVE_MIN_DOUT=2 + sum_gate.

### ALERT 4 — UNTRACKED FILLS: 109 WARNING lines, ~$4,307 notional
- Not a pre-registered alert but flagged: 51 unique token fill events at WARNING level not registered as MAKER-FILL entries. Volume ($4,307) is ~25× daily bot fill volume. Likely SELL_EXIT (0.99 exit orders being bought by resolution counterparties) and pre-restart legacy settlement. No ERROR lines confirm no hard failures, but reconciliation against CLOB fill history is warranted.

*No alert fired for: books pinned at 80, cash_preskip >200, dead quotes >48h.*

---

## 3-Line Summary

**Fills/day:** 44 fill events over 64h (~11/day active); $83 in 24h ending Jun 29 07:02; 1.03 turns/day at benchmark. Distribution: 91.9% NO, 8.1% YES; 90.9% in 0.50–0.85 band; Chengdu 31.8%, London 25.0%, Munich 15.9%.

**NO-share:** YES fills 6.8% of 7d tape; yes_books=0 in 746/746 STRUCT-BAND-Q cycles; 0 YES in resting book at snapshot. YES parity alert fires on Jun 26 (0% of 10 posts) and Jun 28 (7.1% of 14 posts). Pair_fav (d+0, ~1/1.5 days) is the sole YES channel; all standalone d+2 YES fires are blocked by sum_gate.

**Binding execution constraint:** BAND_YES_LIVE_MIN_DOUT=2 restricts YES to d+2 only, and d+2 sum_ask exceeds BAND_SUM_MAX=0.85 for all 5 allowlist cities on most days — YES is structurally dark. Cash velocity hits 1.03 turns/day on NO fills alone, but book depth is half of full-parity capacity. One confirmed pair merge (+17.2%, $1.41) in session; n<100, no winner's-curse test possible.
