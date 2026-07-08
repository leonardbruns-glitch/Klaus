# Band Execution & Markout Audit — 2026-07-08

**Snapshot**: `2026-07-08T07:06:16Z` (fresh, <6h) | **System**: active | **Capital**: $136.77 (all cash)
**BAND_LIVE**: False (wind-down Jul 6 22:08, equity $108.35 < threshold $111.45)
**BAND_NO_ENABLED**: False (rail-halt Jul 2, WR 39.2%) | **BAND_PAIR_FAV_ENABLED**: True | **BAND_YES_LIVE_MIN_DOUT**: 9

---

## §1 FILL TAPE

### Last 24h (cutoff 2026-07-07 07:06Z → 2026-07-08 07:06Z)
- Fill events: **0**
- Fill volume: **$0.00**
- Bot dark since BAND_LIVE=False at 2026-07-06 22:08 UTC

### Last 7d (2026-07-01 → 2026-07-08)
- Fill events: **32** (17 registered + 15 increments via maker fill cascade)
- Fill volume: **$70.73**
- Date range: Jul 5 07:11 – Jul 6 17:04 UTC (all fills in 2-day window)
- Avg fills/active day: ~16/day

| Side | Events | Volume |
|------|--------|--------|
| YES  | 18     | $45.58 |
| NO   | 14     | $25.15 |
| NO share | 44% count | 36% $ |

| Price Band  | Events | Notes |
|-------------|--------|-------|
| <0.10       | 6      | Moscow NO DCA at 0.060 |
| 0.10–0.30   | 0      | — |
| 0.30–0.50   | 22     | Primary operating band |
| 0.50–0.85   | 4      | Near BAND_NO_MAX boundary |

| City       | Events | Volume |
|------------|--------|--------|
| Moscow     | 8      | $10.05 |
| Munich     | 4      | $16.31 |
| Shanghai   | 4      | $11.97 |
| Chongqing  | 5      | $8.34  |
| Tokyo      | 4      | $8.10  |
| Wuhan      | 4      | $8.01  |
| Beijing    | 2      | $3.54  |
| Seoul      | 1      | $4.41  |

**Untracked fills (USER-WS, outside bot scope — sprint ladder / parallel strategy)**:
- Jul 6 07:55: 1473sh @ 0.999 = $1,471.81
- Jul 6 12:17–12:31: ~246sh @ 0.83–0.94 = $232.49
- Jul 6 17:02: 101sh @ 0.99 = $100.00

---

## §2 NO-PARITY

### Post parity (band_struct_lite.jsonl, live fires only)

| Date   | YES posts | NO posts | NO share | Status |
|--------|-----------|----------|----------|--------|
| Jul 3  | 107       | 31       | 22.5%    | ALERT (<25%, n=138) |
| Jul 4  | 8         | 8        | 50.0%    | OK |
| Jul 5  | 8         | 8        | 50.0%    | OK |
| Jul 6  | 8         | 8        | 50.0%    | OK |
| Jul 7  | 0         | 0        | —        | BAND_LIVE=False |
| Jul 8  | 0         | 0        | —        | BAND_LIVE=False |

**Jul 3 explanation**: Transitional period. BAND_NO_ENABLED was disabled Jul 2; standalone YES was still active (BAND_YES_LIVE_MIN_DOUT=2) until 19:25 UTC Jul 3 when the threshold was raised to 9. The excess YES posts are from solo standalone YES, not a regression of the Jun-12 NO-starvation bug fix. Post-transition Jul 4-6 shows exactly 50/50 pair parity.

**NO posts despite BAND_NO_ENABLED=False**: All NO `post` records on Jul 3-6 are pair_fav completion legs (BAND_PAIR_FAV_ENABLED=True), not standalone NO overlay (BAND_NO_ENABLED). Expected behavior.

**Fill-side NO share**: 44% by count, 36% by $ — consistent with NO leg pricing at lower absolute price in pair_fav (YES anchored 0.45–0.70, NO complement).

**Resting book**: `maker_resting_state.json = {}` — no resting quotes, consistent with BAND_LIVE=False.

---

## §3 QUEUE HEALTH

**Coverage**: 323 cycles (Jul 5-6 only). No STRUCT-BAND-Q data for Jul 7-8.
**Logging gap**: Jul 6 17:04 → Jul 8 07:06 (38h). Cause: process restart after BAND_LIVE wind-down at Jul 6 22:08 (new PIDs 195955, 274925). Not fetch starvation — bot is active but old strategy process that generated STRUCT-BAND-Q lines is not running.

| Metric | Jul 5 | Jul 6 | Threshold | Status |
|--------|-------|-------|-----------|--------|
| books max | 4/80 | 4/80 | ≥50 = ALERT | OK |
| yes_books | 0/50 | 0/50 | ≥50 = ALERT | OK (structural) |
| cash_preskip | $0.00 | $0.00 | >$200 = ALERT | OK |
| posted mean/cycle | 0.37 | 0.27 | — | — |

**yes_books = 0 all 323 cycles**: Structural — BAND_YES_LIVE_MIN_DOUT=9 means standalone YES never fires in d+0 to d+2 windows; pair_fav YES legs may not increment this counter. Not an alert (threshold is pinned AT 50).

**cash_preskip = $0.00 all cycles**: Bot was capital-constrained ($42 tracked at time), not stalled by position count. No skip-due-to-cash events.

---

## §4 RESOLUTION MARKOUT

**n = 9 exits in 7d** — below n=40 threshold. DATA COLLECTION only; no edge claims.

| Date   | Type              | Entry  | Exit  | PnL     | Asset                  |
|--------|-------------------|--------|-------|---------|------------------------|
| Jul 3  | recycle099 ×4     | 0.63–0.68 | 0.99 | $10.41 total | weather markets |
| Jul 5  | exit099 STRUCT    | 0.39   | 0.99  | $6.60   | WEATHER_STRUCT_BAND    |
| Jul 5  | recycle099        | 0.84   | 0.99  | $0.90   | weather market         |
| Jul 6  | recycle099        | 0.46   | 0.999 | $4.851  | weather market         |
| Jul 6  | exit099 M1_PROBE  | 0.0919 | 0.99  | $23.602 | WEATHER_M1_PROBE       |
| Jul 6  | recycle099        | 0.44   | 0.99  | $4.95   | weather market         |

**Jul 4, Jul 7, Jul 8**: No exit099 shard files present (exit099_live logger STALE since Jul 6 17:02 — expected given BAND_LIVE=False).

**Moscow NO adverse case** (winner's curse signal, n=1):
- Entry: 0.840 (Jul 5, near BAND_NO_MAX=0.85)
- Next-day DCA: 83.5sh @ 0.060 = 93% adverse price move
- Classic adverse selection: takers knew temperature was in YES band and sold NO into us
- n=1, below n=40 threshold — PLAUSIBLE flag, not formal finding
- Action: monitor BAND_NO_MAX boundary hits in future cycles; no rule change at n=1

**band_resolution_join.py**: Cannot run — no network CLOB access in this environment. Markout bucket analysis deferred.

---

## §5 DEAD QUOTE RECLAIM

- Reaped lines in maker_fills_recent.log: **0**
- Resting quotes: **0** (maker_resting_state.json = {})
- Capital tied in resting orders: **$0**

No reclaim events to analyze. Resting state being empty is consistent with BAND_LIVE=False — all quotes cancelled or expired before wind-down.

**BAND_RECLAIM_AGE_S** = 7200s (2h) | **BAND_PAIR_RECLAIM_AGE_S** = 28800s (8h)
No quotes resting long enough to trigger either threshold.

---

## §6 CASH VELOCITY

| Metric | Value |
|--------|-------|
| Capital (all-cash) | $136.77 |
| Open engine positions | 0 |
| Open ladder shots | 0 |
| Resting order $ | $0.00 |
| Fills last 24h | $0.00 |
| Turns/day (24h) | 0.0 |

**Velocity benchmark** (1.0 turns/day) is moot during voluntary BAND_LIVE=False halt.

**Shadow pipeline**: 10+ converged d+2 markets (Tokyo, Taipei, Wuhan, Chengdu, Beijing, Shanghai, Chongqing, Seoul, Munich, London) show shadow fires with live=false — sum_gate blocked (sum_ask 0.91–0.993 for d+1; d+2 has genuine demand but deployment gate closed). Shadow demand exists; capital deployed = $0.

**Re-enable conditions (none met)**:
- Equity ≥50%·HW: need equity ≥$111.45; current $136.77 BUT wind-down rail tracks HW $222.90; recheck at EVOLVE 21:53Z Jul 8
- Pair n ≥40 positive trend: n≈9/side (far below threshold)
- disp_ratio ≥1.10×5d: current 0.817 (below 1.10)
- -14% freeze: lifts Jul 8 21:53Z per EVOLVE schedule

---

## ALERTS

| # | Rule | Fired? | Value | Notes |
|---|------|--------|-------|-------|
| A1 | NO-share <25% (posts, n≥10) | **FIRED** | 22.5% (Jul 3, n=138) | Transitional: YES-pause cutover, not NO-starvation regression |
| A2 | books ≥50 (queue pinned) | Not fired | max 4/80 | — |
| A3 | cash_preskip >$200 | Not fired | $0.00 all cycles | — |
| A4 | Resting quote >48h | Not fired | 0 resting quotes | — |

**1 alert fired**. A1 is explained by the Jul 2→3 transition (BAND_NO_ENABLED disabled, standalone YES not yet paused). Jul 4-6 post parity is 50/50 — no structural regression.

---

## 3-LINE SUMMARY

**Fills**: 0 events/$0 in last 24h (bot dark since Jul 6 22:08). When active Jul 5-6: 32 fills, $70.73, ~16/day, all in 0.30–0.85 price band. NO fill-share 44% count / 36% $ — consistent with pair_fav geometry (NO leg priced lower).

**NO-parity**: Jul 4-6 posts exactly 50/50 (pair mode healthy post-transition). Jul 3 fired A1 at 22.5% — transitional artifact of YES-pause cutover, not NO-starvation regression. Jul 7-8: zero posts (BAND_LIVE=False). Resting book empty.

**Binding constraint**: BAND_LIVE=False (wind-down rail Jul 6 22:08, equity $108.35 < $111.45). Zero posting / turns / velocity since. Re-enable gate: none of 3 conditions met (pair n≈9/40, disp_ratio 0.817/1.10, -14% freeze lifts 21:53Z Jul 8). 10+ shadow d+2 markets converged but undeployable. Secondary flag: Moscow NO winner's curse near BAND_NO_MAX=0.85 (n=1, monitor only).
