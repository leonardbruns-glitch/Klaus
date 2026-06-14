# Band Execution & Markout Audit — 2026-06-14

**Snapshot:** 2026-06-14T07:02:16Z — age <8 min ✓  
**System:** `klaus systemd: active` ✓ (uptime since 2026-06-12 19:23 UTC)  
**Capital:** $267.24 | **Data window:** 7d fill tape, 5d band_struct_lite, all resolved band trades

---

## 1. FILL TAPE

### 24h (since 2026-06-13 07:10 UTC)
| Metric | Value |
|---|---|
| Total fill events | 66 |
| $ filled | $97.90 |
| YES fills | 46 events / $58.26 |
| NO fills | 16 events / $50.21 |
| NO share of $ | **51.4%** — healthy |

### 7d
| Metric | Value |
|---|---|
| Total fill events | 239 |
| $ filled | $336.90 |
| Fills/day avg | 34.1/day / $48.13/day |
| YES fills | 171 events / $226.97 |
| NO fills | 47 events / $164.61 |
| NO share of $ | **42.1%** — acceptable |

### Price Band Breakdown (7d)
| Band | n | $ |
|---|---|---|
| <0.10 | 20 | $8.40 |
| 0.10–0.30 | 124 | $170.80 |
| 0.30–0.50 | 28 | $48.10 |
| 0.50–0.85 | 46 | $164.28 |

Dominant band is 0.10–0.30 (YES legs) and 0.50–0.85 (NO legs at 0.52–0.85). Normal distribution for the strategy.

### Top Fill Cities (7d by $)
London ($40.91), Beijing ($32.93), Jeddah ($25.58), Munich ($23.13), Taipei ($21.12)

### Fill Rate by Day
| Date | Posted Tokens | Token-Matched Fills | Fill Rate | $ Spent |
|---|---|---|---|---|
| 2026-06-11 | 16 | 16 | 100% | $56.4 |
| 2026-06-12 | 42 | 42 | 100% | $216.3 |
| 2026-06-13 | 42 | 42 | 100% | $174.0 |
| 2026-06-14 | 11 | 3 | 27% | $36.3 |

Jun 14 fill rate at 27% reflects a session still in progress at snapshot time (07:10 UTC). 100% fill rate on posted tokens Jun 11–13 indicates strong taker demand for the posted bids — which is itself an adverse-selection warning (see §4).

### Time-to-Fill
Matched sample n=5 (lite-file fire ts → first MAKER-FILL ts): median **1.7h**, all <6h. Low-n — trend only.

### Reconcile Errors
2 `[MAKER-FILL] reconcile failed` events (Jun 12 17:51 UTC, Jun 14 00:05 UTC). No apparent fill count impact; isolated incidents.

---

## 2. NO-PARITY MONITOR

### New Posts by Side (band_struct_lite fire/fire_no records)
| Date | YES fires | NO fires | NO share | Status |
|---|---|---|---|---|
| 2026-06-11 | 110 | 71 | **39.2%** | LOW |
| 2026-06-12 | 189 | 41 | **17.8%** | *** ALERT |
| 2026-06-13 | 191 | 14 | **6.8%** | *** ALERT |
| 2026-06-14 (07:10) | 135 | 4 | **2.9%** | *** ALERT |

### Resting Book by Side (excl SELL_EXIT)
| Side | Orders | Status |
|---|---|---|
| YES | 23 | — |
| NO | 5 | — |
| **NO share** | **17.9%** | *** ALERT (target ~50%) |

### Diagnosis
The NO-starvation fix committed 2026-06-12 (`fix(BAND): NO-starvation`) did NOT hold. NO share peaked at 39% on Jun 11 (pre-fix baseline), dropped to 18% on Jun 12 (fix day), and has continued declining: 6.8% Jun 13, 2.9% today. The fix introduced cash pre-checks and YES sub-budget (50/80 books), but NO candidate rotation is not producing sufficient fires relative to YES. The resting book reflects this: 5 NO vs 23 YES active bids. Today's full band_struct.jsonl has 5,302 YES fire records vs only 4 `fire_no` records — the NO candidate pool appears near-exhausted.

---

## 3. QUEUE HEALTH

### Per-Day Summary (from [STRUCT-BAND-Q] lines)
| Date | Cycles | avg cash_preskip | avg books/80 | avg yes_books/50 | avg posted/cycle | books pinned | yes_books pinned |
|---|---|---|---|---|---|---|---|
| 2026-06-12 | 130 | $197 | 0.3 | 0.3 | 1.7 | 0% | 0% |
| 2026-06-13 | 280 | $206 | 0.2 | 0.2 | 0.2 | 0% | 0% |
| 2026-06-14 (07:10) | 82 | $215 | 0.1 | 0.1 | 0.1 | 0% | 0% |

### 24h Detail (n=279 cycles)
- avg cash_preskip: **$202** — capital available (no cash starvation)
- avg books used: **0.20/80** — far from fetch saturation ceiling
- avg yes_books: **0.10/50** — far from YES sub-budget cap
- avg posted/cycle: **0.20** — 55 total posts in 24h
- Books pinned at 80: **0%**
- YES books pinned at 50: **0%**

No fetch starvation or yes-book-cap regression detected. $202 avg cash_preskip with only 0.2 books/80 used strongly implies the binding limit is the candidate queue (not capital or fetch budget). The sharp decline in posted/cycle from 1.7 (Jun 12) to 0.1 (Jun 14) correlates directly with the NO fire-rate collapse — fewer unique valid candidates are clearing all gates per cycle.

---

## 4. RESOLUTION MARKOUT

### Methodology
`trades.jsonl` filtered to `bond_entry_class=WEATHER_STRUCT_BAND` + `exit_reason=STWA_RESOLVED`. n=44 resolved legs (41 YES, 3 NO). Date range: Jun 10–13. Separately, `exit099_live.jsonl` tracks 0.99-recycle exits (n=35). Breakeven WR = entry price (market-efficient null). `band_resolution_join.py` not present; network calls not made. n=41 YES is at the trend/decision boundary (40–99 = trend only, <100 for decisions).

### YES Fills — Resolved (n=41)
| Metric | Value |
|---|---|
| Win rate | **4.9%** (2/41 resolved YES) |
| Avg entry price | **20.4¢** |
| Breakeven WR | 20.4% |
| Shortfall vs breakeven | **−15.6 pp** |
| Adverse selection ratio | **0.24×** (observed WR / market-implied WR) |
| EV per $1 staked | **−$0.76** |
| Total resolved YES P&L | −$83.62 on $85.08 stake |

**WINNER'S CURSE: CONFIRMED (trend-grade, n=41)**

The bot is filled on YES legs at 0.24× the market's implied probability. When the maker bid is 2¢ below the ask, informed takers hit the bid only when true probability is materially below the quoted price. The 100% token fill rate on all posted days reinforces this: every posted bid is getting hit, which in a market with any informed participants is a warning signal, not a success metric.

### Recycle Offsets
| Population | n | Cost | P&L | ROI |
|---|---|---|---|---|
| Resolved (STWA_RESOLVED) | 44 | $97.35 | −$79.13 | −81% |
| Recycled at 0.99 | 35 | $132.40 | +$142.25 | +107% |
| **Combined realized** | **79** | **$229.75** | **+$63.12** | **+27.5%** |

The positive net result is driven entirely by the 0.99-recycle pathway. When the market moves in our direction early enough to exit before resolution, the positions are highly profitable. The resolved-at-zero YES legs are the ones where the taker was informed and we held to worthless expiry. Strategy is profitable now because the recycle rate is high — if recycle rate declines or if more positions are held to resolution, the adverse selection on filled legs will dominate.

### Price Band Markout (YES, resolved)
| Band | n | WR | Breakeven | Verdict |
|---|---|---|---|---|
| <0.10 | 1 | 0% | 4% | n/a |
| 0.10–0.30 | 33 | **6%** | 18% | adversely selected |
| 0.30–0.50 | 7 | **0%** | 33% | adversely selected |

The 0.30–0.50 band (n=7, WR=0%) is the worst slice. Seven fills, zero wins, 33¢ avg breakeven. These are likely shoulder legs (|off|=1) where `BAND_YES_MAX_OFF_D0=0` limits d+0 but multi-day shoulders may still pass. `BAND_PX_CEIL=0.45` allows these.

### NO Fills — Resolved (n=3)
Data collection only. WR=33% vs breakeven 57% — also below breakeven, but n=3.

---

## 5. DEAD-QUOTE RECLAIM

### Reaped Lines
`reaped dead entry`: **0 events** in 7d tape. Reclaim mechanism (`BAND_RECLAIM_AGE_S=21600`, 6h) has not triggered once in the observable window.

### Age Distribution (active maker bids, excl SELL_EXIT)
- Total active bids: 29
- >24h old: **12**
- >48h old: **7**

### Stale Positions on Past-Resolution Markets
| City | Side | Price | Remaining Shares | Age | End Date |
|---|---|---|---|---|---|
| Seattle | NO | 0.56 | **4.64** | 59h | **2026-06-10** — resolved |
| Seoul | NO | 0.63 | **4.13** | 59h | **2026-06-11** — resolved |
| Guangzhou | YES | 0.15 | **8.82** | 59h | **2026-06-13** — resolved |

Three resting bids on markets that have already resolved. These cannot fill. Estimated stranded capital: ~$3.40 face at bid price. Additional >24h quotes with today end_date (Karachi YES remaining=5.72, Helsinki YES remaining=2.24) may also become dead by end of day.

SELL_EXIT orders: all 74 at age ≈0h (freshly placed at last restart) — no dead sell exits.

**ALERT: Reclaim mechanism is not detecting past-end-date resting orders. 3 quotes are stranded on closed markets.**

---

## 6. CASH VELOCITY

| Metric | Value | Note |
|---|---|---|
| Capital | $267.24 | user-managed; 594 auto-corrections ($7,781 net), not pure bot P&L |
| Active maker bids (YES/NO) | $39.59 | live inventory cost |
| SELL_EXIT pending at 0.99 | $705.87 | unrealized; depends on takers hitting asks |
| Fills 24h | $97.90 | registered fill events |
| Turns/day | **0.37×** | vs badatmath benchmark ~1.0 |
| Total posted spend (4d) | $483.00 | |

Turns/day at 0.37× reflects the posting velocity collapse (0.2 posts/cycle). Jun 12 posted 1.7/cycle; Jun 14 posts 0.1/cycle — a 17× reduction. Even at Jun 12's rate the turn was modest; at current rate it is 5× below benchmark. The $705.87 SELL_EXIT inventory would improve velocity if it clears, but no SELL_EXIT fills have registered in the resting state (matched=0 across all 74 orders).

---

## ALERTS

| # | Alert | Severity |
|---|---|---|
| **A1** | NO share of new fires: 2.9% today, 6.8% Jun 13, 17.8% Jun 12 — declining every day since Jun 11 peak (39.2%). Jun 12 starvation fix did not hold. | **CRITICAL** |
| **A2** | Resting book NO share: 17.9% (5 NO vs 23 YES). Target ~50%. | **HIGH** |
| **A3** | WINNER'S CURSE on YES resolved fills: WR=4.9% vs 20.4% breakeven; adverse selection ratio 0.24×; EV=−$0.76/$1 (trend-grade, n=41) | **HIGH** |
| **A4** | 3 resting maker bids on past-resolution markets (Seattle NO end=Jun-10, Seoul NO end=Jun-11, Guangzhou YES end=Jun-13); reclaim not triggering on closed markets | **MEDIUM** |

No alerts for: books pinned at 80 (0%), YES books pinned at 50 (0%), cash_preskip >$200 with sustained zero posts (posts are low but nonzero), SELL_EXIT >24h (none), >20 quotes >48h (only 7).

---

## 3-LINE SUMMARY

**Fills/day:** 34/day, $48/day (7d avg); 100% token fill rate on all complete posting days; NO share of fill-$ is 51% in 24h (healthy in $-terms despite low absolute NO count).

**NO-share:** CRITICAL — new fires are 2.9% NO today (down from 39% on Jun 11), resting book is 17.9% NO; Jun 12 starvation fix is not holding and the NO candidate pool appears near-exhausted, driving the 17× collapse in posting velocity.

**Binding constraint:** YES winner's curse on resolved legs (WR=4.9% vs 20.4% breakeven, EV=−$0.76/$1) — current profitability depends entirely on the 0.99-recycle pathway; if recycle rate declines or more positions hold to resolution, the fill-quality deficit will dominate net P&L.
