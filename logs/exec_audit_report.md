# Exec Audit Report — 2026-07-22

**Snapshot**: 2026-07-22T07:01:00Z (age < 6h ✓)  
**System**: `klaus systemd: active` ✓  
**BAND_LIVE**: False (wind-down 2026-07-06: equity $108.35 < 50%·30d-HW $222.90)  
**BAND_NO_ENABLED**: False (rail-halt 2026-07-02: 7d WR 39.2%, n=51)  
**BAND_PAIR_FAV_ENABLED**: True (shadow-only; BAND_LIVE=False blocks live execution)  
**Open positions**: 0  
**Capital**: $21.495 (bankroll.json — manual sells not reflected in PnL; total_pnl=-$75.40)  

---

## 1. Fill Tape (24h + 7d)

**[MAKER-FILL] lines in tape**: 0  
**[STRUCT-BAND-Q] lines in tape**: 0  
**Fills 24h**: 0  
**Fills 7d**: 0  
**$ filled 24h**: $0  
**$ filled 7d**: $0  
**Fill rate**: N/A — no posts since 2026-07-06 (BAND_LIVE=False)

**By side**: N/A (zero fills)  
**By price band**: N/A (zero fills)  
**By city**: N/A (zero fills)  
**Median time-to-fill**: N/A (no first-post timestamps to join against)  

**UNTRACKED FILL note** (not maker activity):  
`Jul 19 07:59:43–07:59:53` — 3 websocket state events (MATCHED/MINED/CONFIRMED) for a single user manual TAKER BUY: token `9728083448649713…`, size=23.5 shares, price=0.94. Bot logged as UNTRACKED because no open tracker entry exists. This is a manual trade at $0.94 (near-certainty bucket), likely a user-initiated position outside the maker loop. $22.09 in proceeds logged to the WS feed but not attributed to any strategy.

**Last live posting date**: 2026-07-06 ($48.01 spent, 10 tokens posted per band_posted_state.json).

---

## 2. NO-Parity Monitor

**Live posts in 7d window**: 0 (BAND_LIVE=False throughout)  
**Resting book by side**: YES=0, NO=0 (maker_resting_state.json = `{}`)  

**Shadow fire breakdown (band_struct_lite, last 2 days)**:

| Date | Fires (live=false) | YES shadow legs | NO shadow legs |
|---|---|---|---|
| 2026-07-21 | 10 | 60 yes_capture_shadow | 0 |
| 2026-07-22 | ~8 (to 07:01 UTC) | 60+ yes_capture_shadow | 0 |

**NO share of shadow fires**: 0% on both days (BAND_NO_ENABLED=False by policy since 2026-07-02).

**Alert: NO posts < 25%** — DOES NOT FIRE. No live posting exists; shadow-only NO=0% is expected policy, not a starvation bug. The 2026-06-12 NO-starvation fix is irrelevant during a BAND_NO_ENABLED=False period — the fix addressed the armed-but-not-firing condition; the current state is deliberately unarmed.

**NO-starvation fix status**: Cannot verify for Jul period because BAND_NO_ENABLED was killed 2026-07-02, 10 days before any re-arm would matter. Fix holds for the Jun 12–Jul 02 window where it was active (no regression observed in that window's last committed audits).

---

## 3. Queue Health

**[STRUCT-BAND-Q] lines**: 0 — no live posting cycles have run since BAND_LIVE=False.  
**Shadow engine cadence**: Active. band_struct_lite entries appear every ~300s (BAND_MD_TTL=300). Multi-day shadow scan running normally across 10 cities, d+0/d+1/d+2.

**Per-day queue stats (cash_preskip, books_used, yes_books, posted/cycle)**: UNAVAILABLE — [STRUCT-BAND-Q] is only written on live posting cycles. Zero cycles = zero rows.

**Alert: books pinned at 80 or yes_books pinned at 50**: CANNOT ASSESS — no queue data.
**Alert: cash_preskip > 200 sustained while posted=0 (deployment stall)**: CANNOT ASSESS — no queue data.

**Shadow engine health check** (proxy for book-fetch health):
- d+0: mostly `converged` or `no_band` (summer mid-day, markets saturated or thin)
- d+1: `sum_gate` on all cities today (sum_ask > BAND_SUM_MAX=0.85, books too expensive to enter)
- d+2: 8 `fire` records (live=false), sum_ask range 0.57–0.845 — within target range
- Scanning is reaching books and returning valid quotes. No fetch-starvation signal.

---

## 4. Resolution Markout (Fill Quality)

**Filled legs in 7d window**: 0  
**n for analysis**: 0 (below threshold for any conclusion)  

No markout computation possible. Historical fills pre-2026-07-06 are outside the 7d window and not in the current maker_fills_recent.log tape.

**Winner's curse assessment**: SKIP — n=0, no data.

---

## 5. Dead-Quote Reclaim

**'reaped dead entry' lines in tape**: 0  
**$ freed by reclaim**: $0  
**Resting quotes total**: 0 (maker_resting_state.json = `{}`)  
**Oldest quote age**: N/A  
**Quotes > 24h old**: 0  
**Quotes > 48h old**: 0  

**Alert: > 20 quotes older than 48h**: DOES NOT FIRE — 0 resting quotes.

Velocity note: BAND_RECLAIM_AGE_S=2h and BAND_PAIR_RECLAIM_AGE_S=8h would trigger reclaim on any aged orders, but the book is empty; reclaim has nothing to act on.

---

## 6. Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $21.495 |
| Resting $ (q_price × (size−matched)) | $0.00 |
| Fills $ last 24h | $0.00 |
| Turns/day (fills$/capital) | 0.00 |
| Benchmark (badatmath) | ~1.0 turn/day |

**Cash fully idle.** $21.50 sitting uninvested. Zero equity is deployed in resting quotes or open fills. No carry on any position.

BAND_PHASE2_CAPITAL threshold ($600) is 28× current capital — phase 2/3 mechanics are irrelevant in the current regime.

---

## ALERTS

No pre-registered alert conditions fired.

All alert gates require either live posting (NO-parity, queue health, dead-quote) or live fills (markout, fill tape). BAND_LIVE=False blanks all gates.

**No-fire is valid output** — reporting zero, not padding.

---

## 3-Line Summary

**Fills/day**: 0 — BAND_LIVE=False since 2026-07-06; zero maker activity in the 7d window; last live fill pre-dates tape.

**NO-share**: N/A — no live posts; shadow fires confirm 0% NO by policy (BAND_NO_ENABLED=False; intentional kill, not starvation bug).

**Binding execution constraint**: BAND_LIVE kill. Capital $21.50, far below the $222.90 30d-HW that triggered the Jul 06 wind-down. Gate unblocks when G8 validates (currently n=57, CI-lo vs BE gap not cleared) or user manually re-arms; until then, all bands shadow-only and cash is fully idle.
