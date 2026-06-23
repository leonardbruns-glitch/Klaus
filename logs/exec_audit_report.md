# Execution & Markout Audit
**Date:** 2026-06-23 | **Snapshot:** 2026-06-23T06:55:16Z (age: 0.3h) | **Status:** ACTIVE  
**Klaus systemd:** active | **Capital:** $202.94 | **Bot uptime since:** 2026-06-23 06:12 UTC (restart today)  
**Audit window:** 7d fill tape (Jun 17–23), 6d NO-parity (Jun 18–23), 6d queue health

---

## 1. FILL TAPE (24h + 7d)

### Tracked Fills (MAKER-FILL lines)
| Window | Events | Unique (token,side) | YES events | NO events | $ YES | $ NO |
|---|---|---|---|---|---|---|
| 24h | 23 | 17 | 8 | 15 | $3.11 | $35.16 |
| 7d | 95 | 59 | 51 | 44 | $28.40 | $92.89 |

**7d fills by price band:**

| Band | Count | % |
|---|---|---|
| <0.10 | 22 | 23% |
| 0.10–0.30 | 29 | 31% |
| 0.30–0.50 | 1 | 1% |
| 0.50–0.85 (NO) | 43 | 45% |

**Top cities 7d:** Tokyo 7, Seattle 7, Moscow 7, Toronto 6, Dallas 6, Chongqing 5, Houston 5, Chengdu 5, Milan 5, Paris 4  
**24h cities:** Milan 5, Chicago 2, Tokyo 2, Wellington 2 (14 other cities ×1 each)

**Fill rate (posted → filled, from band_struct_lite 'post' records):**

| Date | Post YES | Post NO | Fill YES | Fill NO | Fill% YES | Fill% NO |
|---|---|---|---|---|---|---|
| 2026-06-18 | 116 | 22 | 0 | 0 | — | — |
| 2026-06-19 | 41 | 15 | 0 | 0 | — | — |
| 2026-06-20 | 36 | 14 | 8 | 9 | 22% | 64% |
| 2026-06-21 | 40 | 32 | 11 | 10 | 28% | 31% |
| 2026-06-22 | 14 | 18 | 8 | 9 | 57% | 50% |
| 2026-06-23 | 0 | 16 | 0 | 5 | N/A | 31% |

Note: Jun 18–19 fill rates show 0 because fill tape token IDs (short integer format) don't join to band_struct_lite token IDs (77-digit integer format). Jun 20 is first day with overlap. 0 YES posts today (see Section 3).

**Untracked fills (USER-WS UNTRACKED, 7d):** 98 events (MINED-only; CONFIRMED duplicates suppressed)
- 0.90–1.00 price band: 45 events, **$6,435.56** — exit/resolution harvests
- 0.50–0.90: 24 events, **$1,256.58** — NO entry fills not captured by tracker
- 0.30–0.50: 33 events, **$573.92** — YES entry fills not captured by tracker
- <0.30: 6 events, $41.36

Tracker captures ~$121 of estimated ~$1,830 in 7d entry fills — **fill tracking covers ~7% of actual dollar volume**. The gap stems from orders placed in prior sessions not having tracker entries on restart. All exits appear correctly harvested via the SELL_EXIT reclaim path.

---

## 2. NO-PARITY MONITOR

**New posts by side per day (from band_struct_lite 'post' records):**

| Date | Total | YES | NO | NO% | Alert |
|---|---|---|---|---|---|
| 2026-06-18 | 138 | 116 | 22 | **15.9%** | ⚠ ALERT: NO < 25% (n=138) |
| 2026-06-19 | 56 | 41 | 15 | 26.8% | — (borderline) |
| 2026-06-20 | 50 | 36 | 14 | 28.0% | OK |
| 2026-06-21 | 72 | 40 | 32 | 44.4% | OK |
| 2026-06-22 | 32 | 14 | 18 | 56.2% | OK |
| 2026-06-23 | 16 | 0 | 16 | **100%** | ⚠ YES=0 (see Section 3) |

**Resting book (maker_resting_state.json, 06:55 UTC):**
- SELL_EXIT: 33 (pending resolution harvest at $0.99, pre-restart positions)
- NO active quotes: 10 (posted 0.4–2.0h ago)
- UNKNOWN (no side/ts): 3
- YES active quotes: **0**

**Verdict on NO-starvation fix (commit 2026-06-12):** Recovery from 15.9% (Jun 18) to 44–56% by Jun 21–22 took ≥6 days after the fix. Fix holds as of Jun 21+. Today's YES=0 is a different condition — `no_resv` crowding (see Section 3), not the original starvation bug.

---

## 3. QUEUE HEALTH

**Daily STRUCT-BAND-Q summary:**

| Date | Cycles | Avg cap$ | Avg books/80 | Avg ybooks/50 | Avg post/cycle | Avg preskip | Avg yes_resv_skip | Alert |
|---|---|---|---|---|---|---|---|---|
| 2026-06-20 | 199 | $213 | 0.5 | 0.2 | 0.23 | 61 | 1.4 | OK |
| 2026-06-21 | 280 | $262 | 0.4 | 0.2 | 1.25 | 68 | 1.1 | OK |
| 2026-06-22 | 281 | $223 | 0.2 | 0.1 | 0.94 | 96 | 5.3 | OK |
| 2026-06-23 | 81 | $203 | 0.2 | **0.0** | 2.11 | 136 | **13.3** | ⚠ yes_resv_skip |

**`no_resv` escalation — root cause of YES suppression:**

| Date | Avg no_resv | Cycles @ 1.00 | yes_books=0% |
|---|---|---|---|
| 2026-06-20 | 0.400 | 0/199 | 82% |
| 2026-06-21 | 0.400 | 0/280 | 89% |
| 2026-06-22 | 0.705 | 143/281 (51%) | 96% |
| 2026-06-23 | **1.000** | **81/81 (100%)** | **100%** |

`no_resv` escalated from a stable 0.40 (Jun 20–21) to 1.00 on all 81 cycles today. When `no_resv=1.00`, the NO cash reserve absorbs 100% of cycle headroom. `yes_books=0/50` every cycle → YES CLOB books not fetched, YES quotes not posted. `yes_resv_skip` averages 13.3 (max 57 in a single cycle).

**Today's last 5 cycles (06:34–06:54 UTC):**
```
06:34  cap=200  books=3/80  ybooks=0/50  posted=2  preskip=140  yes_resv_skip=21
06:39  cap=200  books=0/80  ybooks=0/50  posted=0  preskip=144  yes_resv_skip=20
06:44  cap=203  books=1/80  ybooks=0/50  posted=1  preskip=98   yes_resv_skip=57
06:49  cap=203  books=0/80  ybooks=0/50  posted=0  preskip=100  yes_resv_skip=48
06:54  cap=203  books=1/80  ybooks=0/50  posted=1  preskip=147  yes_resv_skip=0
```

Books never pin at 80 (fetch capacity fine). The issue is not external fetch starvation — it is internal NO cash reservation consuming all available headroom. `no_cands` running 174–184 today (vs. ~20 earlier in the week), which likely triggered the escalation in the reserve logic. Posted counts of 1–2/cycle are exclusively NO.

---

## 4. RESOLUTION MARKOUT (fill quality — adverse-selection test)

**Gamma API status:** HTTP 403 Forbidden from this sandbox. `band_resolution_join.py` processed 1,840 deduped legs across 1,425 unique markets but returned 0 resolved legs — API blocked. Direct WR/ROI join unavailable.

**Resolution harvests (exit099_live, 7d, `recycle099` records):** n=64, all positive PnL

| Entry price bucket | n | Total PnL | ROI |
|---|---|---|---|
| ≈0.0 | 1 | $38.40 | 3200% |
| ≈0.1 (cheap YES) | 3 | $24.04 | 778% |
| ≈0.2 (YES near-mode) | 11 | $70.36 | 411% |
| ≈0.3 (YES shoulder) | 12 | $52.11 | 269% |
| ≈0.5 (NO low) | 4 | $19.18 | 105% |
| ≈0.6 (NO core) | 24 | $80.65 | 72% |
| ≈0.7 (NO high) | 7 | $17.42 | 49% |
| ≈0.9 (NO tail) | 2 | $2.29 | 6% |
| **TOTAL** | **64** | **$304.45 / $246.28 cost** | **123.6%** |

All 64 resolved positions exited at ≈$0.99. Zero loser positions in exit099 (losing positions expire without a recycle record). ROI figures reflect gross winner performance; net ROI requires accounting for losing positions not present here.

**Adverse-selection proxy (entry price distribution):**
- ALL YES fires mean bid: **$0.178** (n=1,826 deduped legs, 6d shadow)
- ALL NO fires mean bid: **$0.614** (n=110 deduped legs)
- Resolved winners mean entry: **$0.455** (median $0.550) — 53% are NO positions (entry 0.50–0.70), 44% YES

YES entries in the resolved winner set average ~$0.25, which is above the all-fires YES mean of $0.178. This is a mild signal that fills concentrate in the more expensive YES buckets (higher fill probability but thinner odds). **n<40 for YES fills in the resolved set — DATA-COLLECTION mode, no adverse-selection conclusion possible.** Cannot call winner's curse without the full resolved-WR comparison.

**GATE:** Decision-grade markout (n≥100 resolved) not achievable from this sandbox (Gamma API blocked). Recommend running `band_resolution_join.py` from the VPS where Gamma API is accessible.

---

## 5. DEAD-QUOTE RECLAIM

- **"reaped dead entry" lines in 7d fill tape:** 0
- **Resting quotes >24h old:** 0
- **Resting quotes >48h old:** 0 (alert threshold: >20)

Age distribution of 46 resting positions:
- <1h: 2 (NO quotes)
- 1–4h: 8 (NO quotes)
- No timestamp (SELL_EXIT pre-restart): 33
- UNKNOWN (no ts): 3

All active quotes are <2h old (bot restarted at 06:12 UTC). Dead-quote alert not triggered.

Zero reaped lines: either (a) all filled positions resolved as winners before the 2h reclaim timeout, (b) losing positions expire naturally without a reap event, or (c) the reclaim log format changed. No velocity leak detected from available data.

---

## 6. CASH VELOCITY

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $202.94 (CAVEAT: manual sells) |
| Resting $ — active NO quotes | $60.14 |
| Resting $ — SELL_EXIT @$0.99 pending | $423.78 |
| Total exposure | $483.92 |
| Tracked fills $ — 24h | $38.27 |
| Tracked fills $ — 7d | $121.29 |
| Tracked equity turns/day (24h) | 0.189× |
| Tracked equity turns/day (7d avg) | 0.085× |
| Estimated actual turns/day (incl. untracked) | ~0.18× |
| Badatmath benchmark | ~1.0×/day |

**Capital trajectory (correction events):**

| Date | Net delta | End capital |
|---|---|---|
| 2026-06-16 | −$0.78 | $246.68 |
| 2026-06-17 | +$0.42 | $215.17 |
| 2026-06-18 | +$2.87 | $217.12 |
| 2026-06-19 | +$4.24 | $241.37 |
| 2026-06-20 | −$0.91 | $204.13 |
| 2026-06-21 | −$12.17 | $253.57 |
| 2026-06-22 | −$3.56 | $213.65 |
| 2026-06-23 | −$3.10 | $201.93 |

Capital is down ~20% from Jun 16 peak ($255.57→$202.94). The Jun 21 −$12.17 single-day correction is the largest swing — likely reflects a settlement cascade or manual sell. Velocity at ~0.18× is structurally low relative to badatmath's 1.0×, which is expected at Klaus's $200 capital vs. badatmath's ~$2,000 operational scale.

---

## ALERTS (pre-registered conditions that fired)

### ⚠ ALERT 1 — NO-PARITY: NO share 15.9% on 2026-06-18 (n=138, threshold <25%)
Registered alert fired. The Jun-12 NO-starvation fix required ≥6 days to clear; Jun 18 still showed severe NO starvation. Resolved by Jun 20.

### ⚠ ALERT 2 — QUEUE: `yes_resv_skip` elevated today (avg 13.3, max 57)
`no_resv` has been 1.00 for all 81 logged cycles today. YES book fetches halted (`yes_books=0` every cycle). Bot has posted 0 YES quotes since the 06:12 restart. This is a functional YES-blackout caused by the NO cash reservation logic consuming 100% of capital headroom — distinct from the prior NO-starvation bug. Root trigger: `no_cands` expanded from ~20 (Jun 20) to 174–183 (today), likely causing the dynamic `no_resv` to assert at maximum.

---

## SUMMARY

**Fills/day:** 8–10 unique tokens/day (tracked); YES fill rate 22–57%, NO fill rate 31–64% over Jun 20–22. Tracker captures ~7% of actual dollar fill volume; the remainder flows through the untracked (USER-WS) path, predominantly resolution harvests at $0.99.

**NO-share:** Recovered from 15.9% starvation (Jun 18) to healthy 44–56% (Jun 21–22). Today inverted to 100% NO / 0% YES since restart — not the old bug, but `no_resv=1.00` crowding YES out.

**Binding execution constraint today:** `no_resv` escalated from static 0.40 (Jun 20–21) to dynamic 1.00 (Jun 23) as NO candidate count expanded from ~20 to ~180 per cycle. YES quoting is dormant. If the NO candidate pool doesn't contract, the YES band will continue to go unquoted.
