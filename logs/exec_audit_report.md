# Exec Audit — 2026-06-15T10:31Z

**Snapshot age:** 0.2h (fresh)  
**System status:** `active` (bot uptime since 2026-06-15 05:52 UTC)  
**Capital (bankroll.json):** $270.83 | bankroll is CAVEAT — manual sells not modeled  
**Band config authoritative source:** `band_config.txt` (2026-06-15 snapshot)

---

## Section 1 — Fill Tape (24h + 7d)

### Registered fills (`[MAKER-FILL] registered` lines)

| Date | YES fills | YES $ | NO fills | NO $ | Total fills | Total $ | NO-share |
|---|---|---|---|---|---|---|---|
| 2026-06-12 | 27 | $48.6 | 4 | $19.2 | 31 | $67.8 | 12.9% |
| 2026-06-13 | 27 | $51.8 | 15 | $47.7 | 42 | $99.5 | 35.7% |
| 2026-06-14 | 30 | $52.8 | 13 | $47.7 | 43 | $100.5 | 30.2% |
| 2026-06-15 (partial to 10:31Z) | 14 | $15.9 | 3 | $9.9 | 17 | $25.8 | 17.6% |

**7-day totals:** 133 registered fills; steady-state ~40–43/day on Jun 13–14.

### 24h breakdown (last 24h to 10:31Z)

- **Fills:** 54 (YES=40, NO=14)  
- **$ filled:** YES=$60.44, NO=$51.76, **Total=$112.20**

**By price band (24h):**

| Band | n | $ |
|---|---|---|
| <0.10 | 5 | $3.66 |
| 0.10–0.30 | 26 | $37.47 |
| 0.30–0.50 | 10 | $24.21 |
| 0.50–0.85 | 13 | $46.86 |

**Top cities (24h):** Jeddah 5, London 5, Chongqing 4, Helsinki 3, Taipei 3, Guangzhou 3, Chengdu 3, Beijing 3, Warsaw 3.

### UNTRACKED fills (`[USER-WS] UNTRACKED FILL`)

- **7d CONFIRMED:** 146 — nearly equal volume to registered (133)  
- **24h CONFIRMED:** 58  
- **24h untracked notional:** $2,860 (BUT: majority are high-price SELL_EXIT resolution payouts and NO complement fills at 0.70–0.99, not new maker exposure)

| Price range | 7d count |
|---|---|
| <0.50 | 30 |
| 0.50–0.70 | 17 |
| 0.70–0.85 | 40 |
| 0.85–0.99 | 20 |
| ≥0.99 | 39 |

The ≥0.85 bucket (59 events) are SELL_EXIT fills and resolution payouts. The 0.70–0.85 bucket likely represents the NO complement fills when YES positions fill (YES at 0.20 → NO complement buy-through at 0.78). None of these appear to be new maker exposure being missed, but the `UNTRACKED` log entry remains an accounting gap.

---

## Section 2 — NO-Parity Monitor

### New posts by side (from `band_struct_lite` `post` records)

| Date | YES posts | NO posts | Total | NO-share | Alert? |
|---|---|---|---|---|---|
| 2026-06-10 | 2 | 4 | 6 | 66.7% | — (n<10) |
| 2026-06-11 | 54 | 14 | 68 | 20.6% | ⚠ ALERT |
| 2026-06-12 | 82 | 3 | 85 | 3.5% | ⚠ ALERT |
| 2026-06-13 | 43 | 16 | 59 | 27.1% | OK |
| 2026-06-14 | 67 | 20 | 87 | 23.0% | ⚠ ALERT |
| 2026-06-15 | 62 | 4 | 66 | 6.1% | ⚠ ALERT |

### FIRE records (first-fire per `(cid, side)`)

| Date | YES fire | NO fire | Total | NO-share | Alert? |
|---|---|---|---|---|---|
| 2026-06-10 | 47 | 0 | 47 | 0.0% | ⚠ ALERT |
| 2026-06-11 | 110 | 71 | 181 | 39.2% | OK |
| 2026-06-12 | 189 | 41 | 230 | 17.8% | ⚠ ALERT |
| 2026-06-13 | 190 | 14 | 204 | 6.9% | ⚠ ALERT |
| 2026-06-14 | 193 | 18 | 211 | 8.5% | ⚠ ALERT |
| 2026-06-15 | 136 | 4 | 140 | 2.9% | ⚠ ALERT |

### Resting book (live, excluding SELL_EXIT)

- YES resting: 43 orders, **$40.67**  
- NO resting: 5 orders, **$12.95**  
- NO $ share in resting: **24.2%** (marginally below 25% target)

**Verdict:** The NO-starvation fix committed on 2026-06-12 is NOT holding. Post NO-share has collapsed to 6.1% today and the fire-side NO-share is 2.9% — the most starved it has been in the observed window. Jun 11 shows a single well-balanced day (39% NO fire-share) then immediate regression. The `BAND_NO_CASH_RESERVE=0.0` change on 2026-06-15 (unreserving NO cash pool) should theoretically help, but Jun 15 data is already worse. Likely cause: YES markets vastly outnumber qualifying NO markets in the CLOB; NO candidates average 155–165/cycle while posted NO barely registers.

---

## Section 3 — Queue Health

Source: `[STRUCT-BAND-Q]` lines; new fields `yes_resv_skip` and `yes_cap` present from Jun 15 onward.

### Per-day aggregates

| Date | Cycles | avg cash_preskip | avg books/80 | avg yes_books/50 | avg posted/cycle | books pinned @80 | yes_books pinned @50 |
|---|---|---|---|---|---|---|---|
| 2026-06-12 | 130 | 196.6 | 0.3 | 0.3 | 1.70 | 0 | 0 |
| 2026-06-13 | 280 | 205.7 | 0.2 | 0.2 | 0.21 | 0 | 0 |
| 2026-06-14 | 279 | 163.7 | 0.3 | 0.2 | 0.31 | 0 | 0 |
| 2026-06-15 | 121 | 247.0 | 0.9 | 0.5 | 3.25 | 0 | 0 |

**No fetch starvation** (books never pinned at 80, yes_books never pinned at 50).

### Cash > 200 with posted = 0

| Date | Cycles triggered | % of total |
|---|---|---|
| 2026-06-12 | 71/130 | 54.6% |
| 2026-06-13 | 151/280 | 53.9% |
| 2026-06-14 | 106/279 | 38.0% |
| 2026-06-15 | 63/121 | 52.1% |

These cycles have high available cash but no new valid markets to post — the queue of 280–340 markets is mostly already-covered. This is NOT a deployment stall (the bot posts in other cycles of the same day and no_cands is 130–165/cycle) but reflects low daily posting throughput relative to the market universe covered.

### Jun 15 hour-by-hour (new `yes_resv_skip` field)

| UTC hour | avg yes_cap | resv_skip/hr | cycles w/ post |
|---|---|---|---|
| 00–04 | 0.6–2.0 | 267–952 | 0–1/12 |
| 05 | 2.70 | 140 | 4/12 |
| 06–10 | 1.1–2.1 | 0 | 3–4/12 |

At midnight the YES capacity budget (`yes_cap`) is nearly exhausted from prior-day posting, so the bot hits `yes_resv_skip` on almost every candidate until the budget recharges. The 05:00 burst (avg_posted=28 driven by new-market discovery) confirms normal operation resuming after budget recycle.

---

## Section 4 — Resolution Markout (Fill Quality)

**Network status:** Gamma API returns HTTP 403 → `band_resolution_join.py` cannot be run; all-fires comparison unavailable.

**Proxy:** trades.jsonl WEATHER `STWA_RESOLVED` events, June 10+ (n=82 resolved positions: 68 YES, 14 NO).

### YES resolved (n=68, trend-grade at 40–99)

| Price band | n | Wins | WR | Breakeven WR | avg ROI |
|---|---|---|---|---|---|
| <0.10 | 2 | 0 | 0.0% | ~6% | −100% |
| 0.10–0.30 | 50 | 2 | 4.0% | ~19.3% | −79.3% |
| 0.30–0.50 | 16 | 1 | 6.2% | ~33.1% | −81.1% |
| **Combined** | **68** | **3** | **4.4%** | ~**18%** | **~−80%** |

### NO resolved (n=14, data-collection grade)

- WR = 21.4% (3/14); breakeven ~46% (avg NO entry 0.57); avg ROI ≈ −17.6%
- n too small for conclusions; trend is below breakeven.

### Exit099 winners (separate accounting)

- **52 `recycle099` events** across Jun 10–15: total P&L **$249.09**  
- Avg per event: $4.79 (entries ranging 0.04–0.97, exits at 0.99)
- These are the winning YES legs — entry at low price, held to near-resolution, sold at 0.99.

### Winner's-curse assessment

At n=68 YES positions (trend-grade, not yet decision-grade):  
- Fill-conditional WR (4.4%) is **≈ 4.5× below breakeven** in the 0.10–0.30 band  
- This is consistent with **adverse selection (winner's curse)**: the bot is getting filled when better-informed sellers cross the spread — the true probability of the event is materially lower than the badatmath model price  
- Counter-evidence: exit099 shows $249 in profits on the small fraction that do resolve YES, suggesting the model does identify the correct bucket; the problem is low base-rate events  
- Full winner's-curse verdict requires all-fires comparison (Gamma API blocked). **Flag: possible winner's curse, confirm at n≥100 with API access.**

---

## Section 5 — Dead-Quote Reclaim

- **"reaped dead entry" lines in fill tape:** 0 (reclaim not logging to fill tape, or zero reclaims occurred)
- **`BAND_RECLAIM_AGE_S`:** 2h (reduced from 6h as of today)
- **Resting quotes >24h old:** 18  
- **Resting quotes >48h old:** 14 (threshold: >20 → **alert NOT triggered**)
- **Oldest resting quote:** 86.6h (Seattle None, end_date=2026-06-10 — expired market)
- **Stale orders (end_date before today):** 15 orders with `end_date ≤ 2026-06-14`, mostly fully matched (matched≈size) or zero-shares expired markets

The 2h reclaim tightening is very recent (today's config change). The 14 quotes >48h and 15 stale-end-date orders should be swept by the new 2h window in the next reclaim cycle. Monitoring recommended to confirm the 2h reclaim actually fires and the stale orders are cleaned.

---

## Section 6 — Cash Velocity

| Metric | Value | Benchmark |
|---|---|---|
| Capital | $270.83 | — |
| Active maker resting (YES+NO) | $53.62 | — |
| SELL_EXIT resting (at 0.99) | $682.11 | — |
| Fills $ today (partial 10:31Z) | $25.82 | — |
| Fills $/day (Jun 13–14 avg) | ~$105/day | — |
| **Turns/day** | **0.41** | **~1.0 (badatmath)** |

The $682 SELL_EXIT resting is large relative to capital ($270) — this represents resolved-or-nearly-resolved positions sitting at exit bids of $0.99 waiting to be swept. These are not new maker exposure but do represent a large volume of orders in the book.

**Turns at 0.41/day** is 59% below the badatmath benchmark of 1.0. The breadth-over-size shift (BAND_STAKE_FRAC_YES 0.010→0.005 today; BAND_BASE_STAKE 3→1 also today) will reduce per-stake $ but increase fill count — expect turns ratio to remain well below 1.0 until NO coverage improves meaningfully.

---

## ALERTS

**1. ⚠ NO-SHARE ALERT (FIRED, repeated):** NO-share of new posts < 25% on Jun 12 (3.5%, n=85), Jun 14 (23.0%, n=87), Jun 15 (6.1%, n=66). NO starvation persists despite the 2026-06-12 fix. Today is the worst day on record (2.9% NO fire-share). The `BAND_NO_CASH_RESERVE=0.0` change has not yet improved this — the constraint appears to be market structure (very few qualifying NO positions, not cash availability). The `BAND_NO_SKIP_OFF1=True` gate and `BAND_NO_MIN=0.52` floor may be eliminating most NO candidates.

**2. ⚠ WINNER'S CURSE FLAG (PENDING CONFIRMATION):** YES fill-conditional WR = 4.4% across all price bands vs breakeven ~18%. At n=68 (trend-grade). ROI at 0.10–0.30 band: −79.3%. This implies the fills are occurring on events that the CLOB has already discounted below the bot's quote price — classic adverse selection. Full confirmation requires Gamma API all-fires comparison (currently blocked). Bot is getting filled when smart money is selling; winning positions (exit099 $249) do exist but are too rare.

**3. ⚠ CASH>200/POSTED=0 CYCLES (INFORMATIONAL):** 38–54% of cycles across all days show high available cash but zero posts. NOT a deployment stall — the bot does post in other cycles. Cause: the market universe is largely already covered, and yes_cap budget is exhausted late UTC night. No action needed if confirmed expected.

---

## 3-Line Summary

**Fills/day:** 40–43 registered fills/day (stable Jun 13–15); $100–112/day; 0.41 turns/day (41% of badatmath benchmark). Fill count is solid but dollar velocity lags.

**NO-share:** 6.1% today — structural NO starvation is NOT fixed. Jun 12 commit claimed to fix it; it relapsed immediately. The resting book has only 5 NO orders vs 43 YES. This is the book symmetry problem, not a cash problem.

**Binding execution constraint today:** NO-starvation is limiting book symmetry and likely the +EV hedge against YES adverse selection; secondary constraint is the pending winner's-curse signal on YES (WR 4.4% vs 18% breakeven at n=68, Gamma API confirmation blocked).
