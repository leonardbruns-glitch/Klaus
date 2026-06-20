# Klaus Band Maker — Execution & Markout Audit
**Date:** 2026-06-20 | **Snapshot:** 2026-06-20T06:58:40Z (age: <1h — fresh) | **Bot:** systemd active (uptime since 2026-06-19T00:17 UTC)

---

## 1. FILL TAPE — 24h + 7d

### Registered fills (new positions, "registered" lines only; excludes increment events)

| Day | YES fills | YES $ | NO fills | NO $ | Total | NO fill share |
|---|---|---|---|---|---|---|
| Jun 18 | 56 | $62.43 | 13 | $52.34 | 69 | 18% |
| Jun 19 | 22 | $29.57 | 16 | $60.75 | 38 | 42% |
| Jun 20 (07h) | 8 | $9.89 | 0 | $0.00 | 8 | 0% |
| **7d total** | **86** | **$101.89** | **29** | **$113.09** | **115** | **25%** |

Total 7d fill $ (shares × entry price): **$214.97**  
Total events including increments (same-token add-ons): 170

### By price band (all 7d fills, both sides)

| Band | Count | Share |
|---|---|---|
| < 0.10 | 28 | 16% |
| 0.10 – 0.30 | 78 | 46% |
| 0.30 – 0.50 | 18 | 11% |
| 0.50 – 0.85 | 46 | 27% |

YES fills are heavily concentrated in 0.10–0.30 (band YES). NO fills cluster in 0.50–0.85 (BAND_NO_MIN=0.52 config). No fills at tail-NO (>0.85) — BAND_TAILNO_VALIDATED=False is holding.

### Top-filled cities (7d, registered positions)
Taipei (9), Tokyo (7), Chongqing (7), Chengdu (7), Warsaw (6), Seattle (6)

### Time-to-fill
Cannot compute: token IDs in MAKER-FILL log (12-digit truncated) do not match token IDs in band_struct_lite posts. Direct post→fill latency is unmeasured.

### Fill rate (posted → filled unique tokens)
Band_posted_state posted tokens vs MAKER-FILL registered tokens cannot be reliably joined for the same reason. Jun 18 had 95 posted / ~69 registered fills; Jun 19 had 44 posted / 38 fills. Rates appear healthy but cannot be confirmed precisely.

---

## 2. NO-PARITY MONITOR

### Posts by side (band_struct_lite `record=post`)

| Date | YES posts | NO posts | Total | NO share | Alert? |
|---|---|---|---|---|---|
| 2026-06-15 | (not fetched) | — | — | — | — |
| 2026-06-16 | 109 | 12 | 121 | **9%** | **🔴 ALERT** |
| 2026-06-17 | 169 | 10 | 179 | **5%** | **🔴 ALERT** |
| 2026-06-18 | 116 | 22 | 138 | **15%** | **🔴 ALERT** |
| 2026-06-19 | 41 | 15 | 56 | **26%** | OK (≥25%) |
| 2026-06-20 | 3 | 1 | 4 | 25% | OK (n<10) |

**Context:** The `fix(BAND): NO-starvation` commit landed 2026-06-12. Despite this, Jun 16-18 (three days with ≥10 posts) all remained below 25%. The recent commits `feat(BAND): favNO TOP priority + REVERSE phase ladder` and `feat(BAND): promote d+1 NO to rank 1` (most recent two in system_status) have pulled the share up to 25–26% on Jun 19-20. The fix is holding at minimum viable threshold but with no margin.

### Resting book by side (active, excluding SELL_EXIT)
- YES: 11 orders, $8.19 resting  
- NO: 2 orders, $5.01 resting (Munich NO @0.64 — 99.8% filled/closing; Denver NO @0.62 — fresh 1h old, end_date today 12:00 UTC)
- Resting book NO share by value: **38%** (healthy — NO quota has higher per-order stake $5 vs YES $1.20-3.00 base)

---

## 3. QUEUE HEALTH

### STRUCT-BAND-Q cycle statistics

| Day | Cycles | Avg posted/cycle | Avg cash_preskip | Avg books/80 | Avg yes_books/50 | Zero-post cycles |
|---|---|---|---|---|---|---|
| Jun 18 | 253 | **6.7** | $116 | 1.2 | 0.4 | 65% |
| Jun 19 | 280 | 0.8 | $95 | 0.3 | 0.1 | 84% |
| Jun 20 | 82 | **0.0** | **$142** | **0.1** | 0.1 | **96%** |

**Books not pinned at ceiling.** books=0.1/80 on Jun 20 — this is NOT the fetch-starvation pattern (books pinned at 80). The engine is simply not fetching books because there are no reclaim candidates (existing orders within reclaim thresholds).

**Cash_preskip $142 sustained, posted=0.** With capital=$213.09, BAND_NO_CASH_RESERVE=0.30 → reserve=$63.93 → deployable=$149.16. Cash already committed: ~$141. Free headroom: **~$8** — insufficient to post any meaningful new quotes (YES min stake ~$1.20 × size, NO min $5). This is "book at capacity" behavior, not a system fault.

**Implication:** Most capital ($141/$149 deployable) is locked in resting bids. New posts are blocked until positions resolve, fill, or reclaim fires. The BAND_RECLAIM_AGE_S=2h threshold appears not triggering because existing orders are either young or close to their posted price (within BAND_RECLAIM_BEHIND=0.02 of touch). **This is the binding execution constraint today.**

---

## 4. RESOLUTION MARKOUT (Fill Quality — Adverse Selection Test)

### Data limitations
Gamma API returned HTTP 403 Forbidden from this execution environment. Cannot run `analysis/weather/band_resolution_join.py` or query per-condition resolution outcomes. **Winner's curse test is INCOMPLETE — cannot confirm or deny.**

### Available signal: recycle099 (confirmed YES winners)

| Day | n winners | Cost basis | PnL | Avg entry | ROI on winners |
|---|---|---|---|---|---|
| Jun 15 | 13 | $54.57 | $47.56 | 0.553 | +87% |
| Jun 16 | 10 | $75.65 | $84.31 | 0.476 | +111% |
| Jun 17 | 19 | $34.12 | $87.45 | 0.314 | +256% |
| Jun 18 | 26 | $59.11 | $99.56 | 0.350 | +168% |
| Jun 19 | 19 | $32.41 | $78.58 | 0.288 | +242% |
| Jun 20 (07h) | 1 | $5.36 | $2.56 | 0.670 | +48% |
| **Total** | **88** | **$261.21** | **$400.02** | **0.345 avg** | **+153%** |

ROI by entry price band (winners only):
- < 0.10: n=4 avg ROI **+1116%**
- 0.10–0.30: n=34 avg ROI **+420%**
- 0.30–0.50: n=26 avg ROI **+192%**
- 0.50–0.85: n=25 avg ROI **+46%**

### What we cannot say
Without the all-fires baseline (requires `logs/shadow/hot/*/band_struct.jsonl` not available locally, or Gamma API not accessible): cannot compute whether filled-leg ROI is above or below the unconditional ROI. The recycle099 figures are winners-only — losing positions (expired at 0) are not counted here.

### Structural note
67 SELL_EXIT orders at $0.999 represent **filled positions awaiting resolution exit** — these are likely additional winners not yet settled, not dead positions. 309 UNTRACKED FILL events (716 shares matched) in the tape, prices scattered from 0.33 to 0.99, likely dominated by SELL_EXIT settlements coming through the WS.

**Markout verdict: DATA-LIMITED. Cannot confirm or rule out winner's curse at current data access.**

---

## 5. DEAD-QUOTE RECLAIM

### Reclaim log events
Zero `reaped dead entry` lines in 7d tape — this event is not emitted at the current log verbosity level. Cannot directly audit reclaim velocity from fills log alone.

### Resting quote age audit

| Age | Count | Note |
|---|---|---|
| > 48h, < 90% filled (true dead) | **2** | Legacy inactive strategies (WEATHER_THERMO, WEATHER_M1_PROBE), end_date Jun 17-18, ts=0 — never had a timestamp. Not BAND positions. |
| > 48h, ≥ 99.8% filled (effectively closed) | 5 | Moscow YES 66h @0.20 (99.8%), Paris YES 56h @0.08 (100%), Warsaw YES 55h @0.08 (100%), Wuhan YES 52h @0.33 (99.9%), Chengdu YES 51h @0.25 (99.9%) — essentially done, residual dust |
| 24–48h | 1 | Panama City YES 46h @0.04 (100% filled) |
| < 24h | 9 | Moscow YES 21h @0.22; Denver NO 1h @0.62; etc. |

**No BAND dead quotes >48h with meaningful unfilled exposure. ALERT threshold not triggered.**

The 2 legacy dead quotes (Madrid THERMO @0.99, Chicago M1_PROBE @0.94) have ts=0 (no timestamp) — they predate the current resting-state format and will never reclaim because the strategies that created them are disabled. They sit harmlessly in the resting state with $10 exposure but their markets are already expired.

---

## 6. CASH VELOCITY

### Capital position
- Bankroll (bankroll.json): **$213.09** (CAVEAT: user executes manual sells outside bot accounting; do not infer P&L or ruin from this figure alone)
- Active maker resting (YES + NO, excl. SELL_EXIT): **$23.19** (15 orders)
- SELL_EXIT resting: **$786.29 face value** at $0.999 (67 orders — pending resolution exits)
- Committed capital (engine cash_preskip): ~**$141** (includes cost basis of filled-but-unresolved positions)

### Fills and turns
| Day | Fills $ (shares × price) | Turns/day (fills$/capital) |
|---|---|---|
| Jun 18 | $114.76 | 0.54 |
| Jun 19 | $90.32 | 0.42 |
| Jun 20 (07h) | $9.89 | 0.16 projected |

Benchmark (badatmath): ~1.0 equity turns/day at 10-20% ROI/turn. Our turns are 0.42-0.54, roughly **half the benchmark rate.** Two structural reasons: (a) $213 capital base is far below badatmath scale, limiting position count; (b) BAND maker holds to resolution (12-48h horizon) vs intraday cycling. Both reduce nominal turn count without implying inferior economics.

---

## ALERTS

### 🔴 ALERT-1: NO-PARITY — Three consecutive days below 25% threshold (Jun 16-18)
- Jun 16: NO share of posts = **9%** (n=121, ≥10 threshold triggered)
- Jun 17: NO share = **5%** (n=179)
- Jun 18: NO share = **15%** (n=138)
- Status: Partially resolved. Jun 19 recovered to **26%** (OK). Jun 20 at **25%** (n=4, below n=10 threshold). The fix is holding but with no margin. Monitor for regression.
- Root cause window: The Jun 16-17 collapse occurred despite the Jun-12 starvation fix, likely due to subsequent YES-priority commits (YES ceiling changes, days-out priority queue) overriding the NO fix. The two most recent commits (favNO TOP priority + d+1 NO rank 1) appear to be correcting this.

### 🟡 ALERT-2: QUEUE STALL — Jun 20 96% zero-post cycles, headroom ~$8
- Pattern: cash_preskip=$141-159, capital=$213, reserve=$64 → ~$8 free → no posts since ~06:15 UTC (one cycle at ~03:30 posted 2)
- This is NOT books-pinned (books=0.1/80, not 80/80): not fetch starvation
- This IS "capital fully deployed" — resting bids + filled-unresolved cost basis consumes near all deployable capital
- No code action needed (self-resolving as positions settle), but velocity is at zero until resolution frees capital

---

## SUMMARY

**Fills/day:** ~53 registered fills/day (Jun 18-19 avg). Declining: 8 in first 7h Jun 20, rate ~27/day projected. Temporary — capital headroom exhausted.

**NO-share:** Post-side NO has recovered from 5% nadir (Jun 17) to 26% (Jun 19) following favNO priority commits. Fill-side NO at 42% Jun 19 (healthy, NO stakes are larger). Jun 20 at 0 NO fills (only 7h, 1 new NO order posted, hasn't filled). Net: improvement trend is real but the NO-parity floor sits at ~25% with no buffer.

**Binding execution constraint today:** Capital headroom exhausted (~$8 free of $149 deployable). New quotes blocked. Self-resolving: as the 67 SELL_EXIT positions settle and the 5 near-fully-filled YES positions close out, capital recycles. No operational action available from here — this is the expected state when the book is fully loaded.

