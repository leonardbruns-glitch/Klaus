# Execution & Markout Audit — 2026-07-07

**Snapshot**: 2026-07-07T07:00:49Z · **Klaus HEAD**: 64afd79c0 · **Auditor**: exec-audit-agent  
**System status**: `active` (uptime since 2026-07-06 22:08 UTC · open positions: 0)  
**Data quality**: SNAPSHOT < 6h old; maker_resting_state={} (no live book); BAND_LIVE=False (wind-down rail since 2026-07-06 21:53 UTC)

---

## §1 FILL TAPE

### 24-hour window (2026-07-06 07:00 → 2026-07-07 07:00 UTC)

| Metric | Value |
|---|---|
| Registered fills | 6 |
| + Increments | 8 |
| Total fills (all types) | 14 events |
| YES fills (registered) | 4 · $13.06 |
| NO fills (registered) | 2 · $4.44 |
| Moscow NO increments | 6 · $5.02 @ 0.060 (see §4) |
| **Total $ filled (24h)** | **$25.52** |
| NO fill share (by $, all) | 49% |
| NO fill share (by registered count) | 33% |

**24h fill detail:**

| Timestamp UTC | City | Side | Type | Shares | Price | $ |
|---|---|---|---|---|---|---|
| 07:29 | Chongqing | NO | registered | 0.1 | 0.320 | $0.03 |
| 07:30–07:32 | Chongqing | NO | increment ×2 | 9.4 | 0.320 | $3.01 |
| 07:38 | Chongqing | YES | registered | 8.1 | 0.530 | $4.29 |
| 07:52 | Chongqing | YES | registered | 1.9 | 0.530 | $1.01 |
| 11:07 | Munich | YES | registered | 9.0 | 0.440 | $3.96 |
| 12:26–12:31 | Moscow | NO | increment ×6 | 83.5 | 0.060 | $5.02 |
| 12:53 | Munich | NO | registered | 9.8 | 0.450 | $4.41 |
| 14:18 | Munich | YES | registered | 10.0 | 0.380 | $3.80 |

### 7-day window (all log, 2026-07-04 to 2026-07-06)

| Day | Posted tokens | Registered fills | Fill rate | YES fills | NO fills | NO share |
|---|---|---|---|---|---|---|
| 2026-07-04 | 12 | 4 | 33% | 4 · $10.8 | 0 | 0% |
| 2026-07-05 | 8 | 8 | 100% | 6 · $19.4 | 2 · $4.6 | 25% |
| 2026-07-06 | 10 | 11 | ≥100%* | 7 · $19.7 | 4 · $12.1 | 36% |
| **7d total** | **30** | **23** | — | **17 · $49.9** | **6 · $16.7** | **26% ($)** |

*Jul 6 has 11 registered fills for 10 posted tokens — 1 fill appears to be from a residual pre-date position.

**Price band breakdown (7d registered):**

| Band | n | YES/NO | $ |
|---|---|---|---|
| < 0.10 | 0 | — | — |
| 0.10–0.30 | 0 | — | — |
| 0.30–0.50 | 18 | 13/5 | $50.39 |
| 0.50–0.85 | 5 | 4/1 | $16.27 |

All fills in [0.30–0.85]; zero fills in extreme-odds bands. Fee zone is moderate. Consistent with BAND_PX_MIN=0.10, BAND_PX_CEIL=0.45, BAND_NO_MIN=0.52.

**Fills by city (7d registered):**

| City | n | YES $ | NO $ |
|---|---|---|---|
| Munich | 5 | $14.22 | $4.41 |
| Seoul | 2 | $8.86 | — |
| Shanghai | 4 | $8.75 | $4.05 |
| Taipei | 1 | $4.29 | — |
| Tokyo | 3 | $5.85 | — |
| Wuhan | 3 | $1.13 | $4.04 |
| Chongqing | 3 | $5.30 | $0.03 |
| Beijing | 1 | $1.53 | — |
| Moscow | 1 | — | $4.20 |

**Note — untracked fills (USER-WS):** 50 fill events in 7d with "no tracker entry, no open position." Notable Jul 6 untracked MAKER fills: BUY 1,473 sh @ $0.999 (~$1,471); BUY ~264 sh @ $0.86–0.94 (~$230); BUY 101 sh @ $0.99 (~$100). These appear to be manual user trades or a parallel strategy on the same account. **Capital reconciliation via bankroll.json is unreliable** — consistent with existing CAVEAT.

---

## §2 NO-PARITY MONITOR

**Posts by side from band_struct_lite (5-day window):**

| Day | Total posts | YES | NO | NO share | Alert? |
|---|---|---|---|---|---|
| 2026-07-03 | 138 | 107 | 31 | **22%** | **YES — <25% with n≥10** |
| 2026-07-04 | 12 | 6 | 6 | 50% | OK |
| 2026-07-05 | 14 | 7 | 7 | 50% | OK |
| 2026-07-06 | 12 | 6 | 6 | 50% | OK |
| 2026-07-07 | 0 | 0 | 0 | — | BAND_LIVE=False |

**Jul 3 context:** Structurally explained — BAND_YES_LIVE_MIN_DOUT was still at a permissive value (standalone YES d+2 firing: 77 YES d+2 posts vs 1 NO d+2). BAND_NO_ENABLED had been halted 2026-07-02; BAND_YES_LIVE_MIN_DOUT=9 (pause) was set on 2026-07-03. Imbalance occurred during the shutdown transition period, not a recurrence of the pre-Jun-12 starvation bug.

**Post-Jul 3 book (Jul 4–6):** Perfect 50/50 posts — pairs only (BAND_PAIR_FAV_ENABLED=True), one YES + one NO per event. NO-starvation fix confirmed holding for pair mode.

**Resting book:** Empty `{}` at snapshot. No live orders. Consistent with BAND_LIVE=False since 22:08 UTC Jul 6.

**Fill-side NO share (24h):** 33% by registered count, 49% by $. Disparity driven by Moscow NO increments at 0.060 inflating NO $ — see §4.

---

## §3 QUEUE HEALTH

Source: 563 [STRUCT-BAND-Q] lines (Jul 4–6).

| Day | Cycles | Avg cash_preskip | Avg books/80 | Max books | Avg yes_books/50 | Avg posted/cycle | Total posted |
|---|---|---|---|---|---|---|---|
| 2026-07-04 | 164 | $1 | 0.2 | 6 | 0.0 | 0.34 | 56 |
| 2026-07-05 | 228 | $0 | 0.1 | 2 | 0.0 | 0.26 | 60 |
| 2026-07-06 | 171 | $0 | 1.3 | 4 | 0.0 | 0.27 | 46 |

**24h window (Jul 6 07:00–07:00):** 113 cycles · avg_cash=$0 · avg_books=1.7/80 · avg_yes=0/50 · total_posted=4

**No pinning at books=80 or yes_books=50.** Fetch starvation regression absent.

**cash_preskip = $0–1 all days:** Engine sees near-zero available cash before skip logic each cycle. With capital $42 and BAND_PHASE2_CAPITAL=$600, phase 1 limits apply. Natural capital constraint, not a bug.

**yes_books = 0 all days:** Consistent with BAND_YES_LIVE_MIN_DOUT=9 (standalone YES paused) and BAND_SAMEDAY_LIVE=False.

**2026-07-07 posts = 0:** BAND_LIVE=False prevents all posting. Shadow scans continue (119 md_shadow records through 06:06 UTC). 14 cities showing converged bands in shadow (Seoul d+0 0.465, Tokyo d+0 0.355, Wuhan d+0 0.324, Chengdu d+0 0.305, London d+0 0.455, Munich d+2 0.500, etc.) — demand visible but deployment gate closed.

No deployment stall pattern (cash_preskip >200 all day with posted=0). Zero-posted on Jul 7 is regime-change (BAND_LIVE=False), not a fetch/connectivity stall.

---

## §4 RESOLUTION MARKOUT

**Network status:** CLOB API unavailable in this execution environment. `band_resolution_join.py` not run. Markout analysis from price-movement signal in fill log only.

**Observable adverse case — Moscow NO:**

| Event | Timestamp | Shares | Price | $ |
|---|---|---|---|---|
| Registered fill | 2026-07-05 12:48:17 | +5.0 | 0.840 | $4.20 |
| Increment | 2026-07-05 12:48:25 | +1.0 | 0.840 | $0.84 |
| *Entry cost basis* | | *6.0 sh* | *0.840* | *$5.04* |
| Increments ×6 | 2026-07-06 12:26–12:31 | +83.5 | **0.060** | $5.01 |

Moscow NO entered at $0.840 (Jul 5). On Jul 6, the same token received large increment fills at $0.060 — a 93% adverse price move in 24 hours. Consistent with the market learning Moscow resolved YES (temperature in-band), making the NO token near-worthless. The system commit "WIND-DOWN bookkeeping: Moscow false-lockout attribution" (Jul 6 21:53) confirms this event was reviewed.

**Winner's curse diagnosis (PLAUSIBLE):** Maker posted NO at 0.840, near BAND_NO_MAX=0.85. The fill was accepted because better-informed takers were willing to sell NO (go long YES) at that price. Next-day convergence to 0.060 = NO losing. This is the classic maker adverse-selection pattern.

**n=1 event (Moscow NO), n=23 total 7d registered fills** — below n=40 threshold. No formal ROI(filled) vs ROI(all-fires) comparison possible without CLOB resolution data. Flag: monitor NO fills near BAND_NO_MAX=0.85 boundary when band restarts.

**Other fills:** All in [0.30–0.50] range — balanced spread around 50% fair value. No further adverse markout pattern visible in log.

---

## §5 DEAD-QUOTE RECLAIM

| Metric | Value |
|---|---|
| maker_resting_state entries | **0** (empty `{}`) |
| Reaped lines in 7d log | 0 |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |

No reclaim alerts. Empty resting state consistent with BAND_LIVE=False (halted 22:08 UTC Jul 6); all prior positions resolved or filled. Zero $ tied up in maker book. Reclaim machinery will have work when band restarts.

---

## §6 CASH VELOCITY

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $42.02 |
| Resting $ (maker_resting_state) | $0.00 |
| Fills last 24h (all types) | $25.52 |
| Turns/day | **0.61** |
| Benchmark (badatmath) | ~1.0 |

**Capital caveat:** bankroll.json shows daily_start_capital=$108.35 vs current $42.02 (-61% single reading). This is almost certainly polluted by untracked fills ($1,471 MAKER harvest Jul 6 07:55, ~$230 MAKER buys Jul 6 12:17, ~$100 MAKER Jul 6 17:02). The charter wind-down rail triggered at equity $108.35 vs charter threshold $111.45 (50% · 30d-HW $222.90). Current $42 may reflect timing of untracked position marking, not gross realized loss. Do not conclude ruin from this figure alone.

**Turns at 0.61/day:** Reflects last active session (Jul 6) before halt. With BAND_LIVE=False, turns go to 0 effective Jul 7 until ban is lifted. Badatmath 1.0/day benchmark is moot during voluntary halt.

**Fills/day trend (last 3 active days):**
- Jul 4: 4 registered fills, ~$10.8
- Jul 5: 8 registered fills, ~$24.0
- Jul 6: 11 registered fills, ~$31.8 (before halt at 22:08)

Fill activity was accelerating into the halt. 7d average $22.2/day fills against $42 capital = ~0.53 baseline turns/day. Thin but functional when band is live.

---

## ALERTS

| # | Category | Fired? | Detail |
|---|---|---|---|
| A1 | BAND_LIVE=False | **FIRED** | Charter drawdown rail triggered 2026-07-06 21:53 UTC; equity $108.35 < threshold $111.45 (50%·30d-HW $222.90). BAND_LIVE, M1_BETA_PROBE_ENABLED, MIN_LOCKOUT_LIVE all False. 0 posts on Jul 7. Shadow sees 14 converged opportunities (cannot deploy). |
| A2 | NO-parity <25% on day ≥10 posts | **FIRED** | 2026-07-03: 22% NO (31/138 posts). Explained by shutdown transition (standalone YES d+2 still firing while NO band already halted Jul 2). Post-Jul 3 pairs maintain 50/50. Not a structural regression. |
| A3 | Potential winner's curse — Moscow NO | **FIRED (PLAUSIBLE, n=1)** | Moscow NO entered @ 0.840 (Jul 5), increments at 0.060 next day (Jul 6). 93% adverse move near BAND_NO_MAX=0.85 boundary. n<40; no formal ROI comparison possible without CLOB network access. Monitor NO fills at BAND_NO_MAX when band restarts. |
| A4 | Untracked fill volume | **FIRED** | ~$1,800 in MAKER fills on Jul 6 untracked by bot (Jul 6 07:55: $1,471; 12:17–12:31: $230; 17:02: $100). Capital from bankroll.json cannot be reconciled. Not a bot bug — these are outside the tracker's scope. |
| A5 | Books pinned at 80 | Not fired | Max 6/80. |
| A6 | yes_books pinned at 50 | Not fired | Max 0/50. |
| A7 | Quotes >48h old | Not fired | Resting state empty. |
| A8 | cash_preskip >200 with posted=0 all day | Not fired | cash_preskip ≈ $0 all days (capital-constrained, not stalled). |

---

## 3-LINE SUMMARY

**Fills/day:** 6 registered in 24h ($25.52 total incl. increments); 7d average 7.7 registered/day. Fill rate 100% Jul 5–6; 33% Jul 4. All fills in [0.30–0.85] price band, zero extreme-odds activity.

**NO-share:** Posts 50/50 Jul 4–6 (pair mode healthy). Jul 3 imbalance (22%) traced to shutdown-transition, not bug regression. Fill-side NO share 33% by count / 25% by $ over 7d — consistent with pairs plus lower NO fill-probability.

**Binding execution constraint today:** BAND_LIVE=False (charter drawdown rail, fired Jul 6). Zero active posting, zero turns, zero cash velocity. Shadow sees 14 converged markets (Seoul, Tokyo, Wuhan, Chengdu, London, Munich d+2, etc.) unable to deploy. Secondary: winner's curse signal on Moscow NO near BAND_NO_MAX boundary — confirm when band restarts.
