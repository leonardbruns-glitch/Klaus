# Band Execution & Markout Audit — 2026-07-10

**Snapshot**: `2026-07-10T06:57:55Z` (fresh, 13 min old) | **System**: active (uptime from 2026-07-08T22:03Z)
**Capital**: $158.63 all-cash (CLOB-actual, reconciled 2026-07-09 21:53Z per state_log)
**BAND_LIVE**: False (wind-down 2026-07-06, equity $108.35 < 50%·30d-HW $222.90; freeze to 2026-07-10 21:53Z)
**BAND_NO_ENABLED**: False (rail-halt 2026-07-02, WR 39.2% n=51)
**BAND_PAIR_FAV_ENABLED**: True | **STWA_REGULAR_YES/NO_ENABLED**: False

---

## Section 1 — Fill Tape (24h + 7d)

### Klaus MAKER fills
| Window | [MAKER-FILL] lines | Fills (unique events) | $ filled | By side | By price band |
|---|---|---|---|---|---|
| Last 24h | 0 | 0 | $0 | — | — |
| Last 7d | 0 | 0 | $0 | — | — |

The 7-day journal tape (`maker_fills_recent.log`) contains **zero `[MAKER-FILL]` lines**. No Klaus-registered maker fills in any price band, for any city, on either side. This is the expected outcome of `BAND_LIVE=False` since 2026-07-06.

### UNTRACKED taker fills (user's ladder — NOT Klaus maker)
The log contains 11 unique fill events tagged `[USER-WS] UNTRACKED FILL / trader_side=TAKER` — these are the user's badatmath-style ladder positions observed via WebSocket. They are **not** registered in Klaus's tracker and are reported here for completeness only.

| Date | Event | Token (short ID) | Side | Price | Shares | $ deployed |
|---|---|---|---|---|---|---|
| Jul 08 01:00 | BUY | 5176413... | BUY | 0.38 | 18 | $6.84 |
| Jul 08 01:10 | BUY | 5725835... | BUY | 0.34 | 130.5 | $44.37 |
| Jul 08 16:50 | BUY | 5035223... | BUY | 0.55 | 44.25 | $24.34 |
| Jul 09 00:10 | SELL (0.99+ exit) | 5035223... | SELL | 0.996 | 44 | +$43.82 |
| Jul 09 00:10 | BUY | 4409657... | BUY | 0.399 | 129 | $51.50 |
| Jul 09 01:00 | BUY | 9106278... | BUY | 0.38 | 37 | $14.06 |
| Jul 09 07:30 | SELL (0.99+ exit) | 4409657... | SELL | 0.992 | 129 | +$127.97 |
| Jul 09 07:40 | BUY | 3360836... | BUY | 0.53 | 10 | $5.30 |
| Jul 10 01:30 | BUY | 4663735... | BUY | 0.37 | 47.77 | $17.67 |
| Jul 10 02:30 | BUY | 1671958... | BUY | 0.42 | 17.7 | $7.43 |
| Jul 10 03:40 | BUY | 1132101... | BUY | 0.50 | 31.25 | $15.63 |

Last-posted tokens (band_posted_state.json): 10 tokens on 2026-07-06 ($48.01). No entries for Jul 07–10. Fill rate for Jul 04–06 band posts: **0 confirmed fills** in the 7d tape — all prior quotes cleared via market resolution (weather markets expire same-day/next-day; CLOB order books clear on resolution).

---

## Section 2 — NO-Parity Monitor

**Source**: `band_struct_lite.jsonl` per-day; `maker_resting_state.json` (resting book).

| Date | YES posts | NO posts | NO share | ≥10 posts? | ALERT? |
|---|---|---|---|---|---|
| 2026-07-05 | 7 | 7 | **50%** | Yes (14) | No |
| 2026-07-06 | 6 | 6 | **50%** | Yes (12) | No |
| 2026-07-07 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-08 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-09 | 0 | 0 | N/A | No | N/A (dark) |
| 2026-07-10 | 0 | 0 | N/A | No | N/A (dark) |

**NO-starvation fix holds.** On both active posting days captured in the 7d window (Jul 05–06), YES and NO posts are exactly 1:1. This is structurally correct: `BAND_NO_ENABLED=False` but `BAND_PAIR_FAV_ENABLED=True`, and pair_fav posts both a YES and a NO leg per pair — so the balance is inherent to the strategy, not a gate outcome. The fix committed 2026-06-12 (`fix(BAND): NO-starvation`) remains structurally intact.

Resting book: `maker_resting_state.json = {}` — zero resting orders on either side. No SELL_EXIT entries to exclude.

---

## Section 3 — Queue Health

**Source**: `[STRUCT-BAND-Q]` lines in `maker_fills_recent.log`; `count_lock.jsonl` row counts; today's `band_struct` shadow records.

| Metric | Value | Notes |
|---|---|---|
| [STRUCT-BAND-Q] lines in 7d tape | **0** | No active posting cycles since BAND_LIVE=False |
| count_lock.jsonl rows (Jul 07–10) | **0, 0, 0, 0** | Gate has fired on nothing |
| band_struct shadow records today | **2,018 md_shadow, 0 post** | Shadow scan running; no live quotes |
| Books pinned at 80? | Cannot evaluate | No cycles logged |
| yes_books pinned at 50? | Cannot evaluate | No cycles logged |
| cash_preskip > 200 sustained? | Cannot evaluate | No cycles logged |

Queue cycle logging (`[STRUCT-BAND-Q]`) is gated on live posting activity. With `BAND_LIVE=False`, no cycles run and no queue stats emit. This is not a logging fault — the band's shadow scan loop (`md_shadow` records: 2,018 today through 06:54Z) confirms the underlying market scan is alive and healthy. The book-fetch pipeline is functional; the issue is that its output is discarded without live quotes.

Deployment stall gate (cash_preskip > 200 + posted=0): cannot formally evaluate, but consistent with stall — $158.63 cash, $0 deployed, 4 days dark.

---

## Section 4 — Resolution Markout (Fill Quality)

**Data sources**: `maker_fills_recent.log` (7d tape, zero [MAKER-FILL]), `state_log.md` (aggregate 7d path PnL), `band_resolution_join.py` (NOT yet run — scheduled for VPS at 11:23Z today per state_log).

### Registered fills: none evaluable in tape window
With zero `[MAKER-FILL]` lines in the 7d window, per-leg entry/exit markout from the tape is not computable. Prior fills (pre-Jul 02 NO halt, pre-Jul 06 LIVE halt) are outside the tape's observable window.

### Aggregate evidence from state_log (7d settled paths)
From `state_log.md` 2026-07-09 22:20Z entry:

> *"7d realized −$79.36 PF 0.116 n=32 ALL from paths cut 07-02/07-06, engine flow ≈0"*

- 7d settled band paths: **n=32, PnL −$79.36, PF 0.116**
- These are band positions that were entered pre-halt and resolved (settled by weather markets) in the last 7 days
- PF 0.116 = deeply loss-dominant; gross winners / gross losers ≈ 11.6 cents on the dollar

### Simulated all-fires baseline (band_sum_posted_slice.py)
From same state_log entry:

> *"G7 SUM_POSTED[0.70,0.85] n=382 ROI +11.5% Wilson[−11.4%,+38.9%] = AMBIGUOUS NOT READY"*
> *"pairs combined +13.0%/$ n=30 but POST-guard resolved=0"*

- Simulated all-fires ROI for the G7 band's [0.70–0.85 sum_posted] slice: **+11.5%** (Wilson CI straddles 0 — not decision-grade)
- Pairs simulated: +13.0% but zero POST-guard-resolved legs → no live confirmation

### **WINNER'S CURSE FLAG (PLAUSIBLE — insufficient formal data)**
The direction is consistent with winner's curse: **filled/settled paths are realizing PF 0.116 while the simulated all-fires baseline projects +11.5%**. Klaus is selectively filled when his quotes are wrong (adverse-selection against his resting bids). This is the same failure mode that killed the prior Maker MVP.

However, formal per-leg split (filled-subset ROI vs all-fires ROI at the same price band / city / days_out slice) requires `band_resolution_join.py` output, which is pending the VPS run at 11:23Z today. **No decision-grade conclusion on winner's curse severity is possible until that join runs.**

n=32 is below the n≥40 threshold for decision-grade conclusions.

---

## Section 5 — Dead-Quote Reclaim

**Source**: `maker_resting_state.json`; "reaped dead entry" lines in `maker_fills_recent.log`.

| Metric | Value |
|---|---|
| Resting quotes | **0** |
| "reaped dead entry" lines in 7d tape | **0** |
| Quotes older than 24h | **0** |
| Quotes older than 48h | **0** |
| $ freed by reclaim in 7d | **$0** |

`maker_resting_state.json = {}`. All prior band quotes (last posted Jul 06: 10 tokens, $48.01; Jul 04–05: additional 20 tokens) have cleared. No reclaim was needed — weather markets for those dates resolved by Jul 07–08, and the CLOB cancels maker orders on market resolution automatically. The `BAND_RECLAIM_AGE_S = 2h` reclaim cycle appears not to run when `BAND_LIVE=False`, but this is irrelevant since zero quotes remain.

No velocity leak. No aged quotes.

---

## Section 6 — Cash Velocity

**Source**: `bankroll.json`; `maker_resting_state.json`; fill tape; `state_log.md`.

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll.json) | **$158.63** | (CAVEAT: user ladder positions not tracked here) |
| Resting $ (Klaus maker) | **$0.00** | — |
| Klaus maker fills 24h | **$0** | — |
| Klaus maker fills 7d | **$0** | — |
| Effective equity turns/day | **0.0** | badatmath ≈1.0 |
| Ladder taker activity (UNTRACKED) | ~$40.73 new Jul 10; $127.97 exit Jul 09 | User ladder only |

Klaus's equity velocity is **0.0 turns/day**. Capital is fully parked in CLOB cash. The band is not working it.

The user's ladder (UNTRACKED by Klaus) continues to deploy capital: 3 new ladder BUY entries on Jul 10 (~$40.73 total), with 2 large profitable exits on Jul 09 ($43.82 and $127.97 returns). The Jul 09 total ladder realized per state_log: **+$74.70 (+89% daily)** from 4 ladder fires. This ladder activity is invisible to Klaus's bankroll tracking beyond what the user manually reconciles.

Freeze expires: **2026-07-10 21:53Z** (~14h45m from snapshot time). Rail status per state_log Jul 09 21:53Z: CLEAR (equity 71.2% of 30d-HW > 50% rail; tracked > ruin_floor $89.16).

---

## ALERTS

### ⚠ ALERT 1 — BAND DARK 4 CONSECUTIVE DAYS (Intended, but binding execution constraint)
**BAND_LIVE=False** since 2026-07-06. Zero maker posts Jul 07–10. This is the intended wind-down state. However, the pre-registered re-enable condition (post-guard n≥40 resolved) is **UNREACHABLE while dark** — the band cannot accumulate post-guard data when it's not posting. Per state_log 2026-07-09: structural decision deferred to weekly 2026-07-12 (shadow-posting mode vs condition amendment). The band will remain dark beyond tonight's freeze expiry unless the weekly decision changes the re-enable path.

### ⚠ ALERT 2 — MARKOUT GAP: WINNER'S CURSE DIRECTION UNRESOLVED
7d settled paths show PF 0.116 (n=32), deeply negative, against a simulated all-fires baseline of +11.5% (AMBIGUOUS). This directional gap is consistent with adverse-selection winner's curse but is not formally confirmed: `band_resolution_join.py` has not yet run (scheduled 11:23Z today). The formal markout split (filled-subset ROI vs all-fires ROI by slice) must be completed before any re-enable decision. If the join confirms winner's curse at n≥40, the fill-quality problem is structural and re-enabling without a quote-improvement mechanism would replicate the prior Maker MVP failure.

---

## 3-Line Summary

**Fills/day**: 0 Klaus maker fills (band dark Jul 07–10); 7d settled band paths at PF 0.116 n=32 — deeply negative but pre-halt positions, formal per-leg markout pending `band_resolution_join.py` run at 11:23Z today.

**NO-share**: 50% on last two active posting days (Jul 05–06, 14 and 12 posts respectively); NO-starvation fix structurally intact via pair_fav mechanics.

**Binding execution constraint**: `BAND_LIVE=False` — the band's re-enable gate (post-guard n≥40) is unreachable while dark, deferring to the Jul 12 weekly structural decision; freeze expires 21:53Z tonight but does not automatically re-enable the band.
