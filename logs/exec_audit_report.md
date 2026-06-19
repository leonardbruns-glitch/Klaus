# Klaus BAND Execution & Markout Audit
**Date:** 2026-06-19 | **SNAPSHOT:** 2026-06-19T06:58:39Z (age < 1h — VALID)
**System:** `klaus systemd: active` | Uptime since 2026-06-19 00:17:28 UTC (restart at midnight)
**Band config authoritative:** band_config.txt @ same snapshot timestamp
**Capital:** $224.29 | **Phase:** 1 | **Bot HEAD:** 648c8796

---

## Section 1 — Fill Tape

### 24-Hour Window (2026-06-18 07:00 → 2026-06-19 07:00)

| Metric | Value |
|---|---|
| Total fill events ([MAKER-FILL]) | 72 |
| Total $ filled (registered fills) | $122.70 |
| YES fill events | 50 (69%) |
| YES $ filled | $47.49 (avg $0.95/event) |
| NO fill events | 22 (31%) |
| NO $ filled | $75.21 (avg $3.42/event) |

**By price band (24h):**

| Band | Events | $ | Sides |
|---|---|---|---|
| < 0.10 | 11 | $7.50 | YES×11 |
| 0.10–0.30 | 30 | $27.74 | YES×30 |
| 0.30–0.50 | 9 | $12.24 | YES×9 |
| 0.50–0.85 | 20 | $64.69 | NO×20 |

NO fills concentrate entirely in the 0.50–0.85 band (avg price ≈ $0.63); YES fills are all sub-0.50 (consistent with near-mode YES band: `BAND_PX_CEIL=0.30`).

**By city (24h top 10):**
Warsaw 6×/$14.31, Seattle 6×/$10.79, NYC 5×/$9.32, Taipei 5×/$2.47, Moscow 4×/$6.17, Ankara 4×/$6.47, Toronto 4×/$6.35, Austin 3×/$3.36, Dallas 3×/$3.70, Busan 3×/$3.94

**7-Day Summary:**

| Date | Fill Events | YES | NO | $ Filled |
|---|---|---|---|---|
| 2026-06-17 | 87 | 81 | 6 | $111.55 |
| 2026-06-18 | 102 | 83 | 19 | $142.71 |
| 2026-06-19 (partial, 7h) | 5 | 2 | 3 | $9.34 |

**Daily fill rate (posted tokens vs uniquely-filled tokens):**

| Date | Posted Tokens | Filled Tokens | Fill Rate |
|---|---|---|---|
| 2026-06-17 | 71 | 70 | **98.6%** |
| 2026-06-18 | 95 | 74 | **77.9%** |
| 2026-06-19 (7h) | 8 | 4 | 50.0% (partial) |

Fill rates are extremely high — nearly every posted position attracts a taker. Post volume is the binding throughput constraint, not fill probability.

**Time-to-fill:** Could not compute median — insufficient post→fill timestamp overlap across available lite files and fill log. Registered fill format does not carry original post timestamp inline.

**Unregistered fills (UNTRACKED FILL at 0.99 — exits):**
319 total lines (7d), 156 in 24h. These are WebSocket-detected MAKER fills at price=0.99 where the bot's tracker has no matching open position. Confirmed dollar values in 24h: **$4,697** (71 confirmed events; top sizes: 378.4 sh, 147.6 sh, 110.3 sh at $0.99). Scale far exceeds bot capital ($224) — nearly all originate from user-manual positions resolving, not bot-placed orders. Tracker gap is pre-existing and correctly flagged. *No code change in scope.*

---

## Section 2 — NO-Parity Monitor

Source: `record=post` entries in per-day `band_struct_lite.jsonl` files.

| Date | YES Posts | NO Posts | Total | NO Share | ALERT? |
|---|---|---|---|---|---|
| 2026-06-14 | 67 | 20 | 87 | 23.0% | **YES** |
| 2026-06-15 | 178 | 4 | 182 | 2.2% | **YES (severe)** |
| 2026-06-16 | 109 | 12 | 121 | 9.9% | **YES** |
| 2026-06-17 | 169 | 10 | 179 | 5.6% | **YES** |
| 2026-06-18 | 116 | 22 | 138 | 15.9% | **YES** |
| 2026-06-19 | 8 | 1 | 9 | 11.1% | n<10 |

**ALERT — NO-parity below 25% threshold on ALL five measurable days.** Target is ≈50% (matching badatmath's book composition). The NO-starvation bug reportedly fixed 2026-06-12 is either not effective or has regressed. Jun 15 is the worst day: 4 NO posts out of 182 total (2.2%).

**Resting book (live, maker_resting_state.json):**
- Active maker quotes: 15 total — YES×12, NO×1, unknown×2
- NO share of live resting book: **6.7%** (1 of 15)
- Consistent with the flow data — the resting book reflects chronic NO starvation

Config check: `BAND_NO_ENABLED=True`, `BAND_NO_STAKE=5.0`, `BAND_NO_SKIP_OFF1=True` (never NO on ±1 shoulders), `BAND_NO_MIN=0.52`, `BAND_NO_MAX_DOUT=2`, `BAND_NO_DAILY_CAP=40.0` — all configured. The constraint appears upstream of the `post` record, within the `fire_no` evaluation or execution path.

---

## Section 3 — Queue Health

Source: 558 `[STRUCT-BAND-Q]` cycles across Jun 17–19.

| Date | Cycles | AvgCash | AvgBks/80 | Pinned? | AvgYBks/50 | Pinned? | AvgPosted | Zero-Post% | AvgNOcands |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-17 | 198 | $127 | 1.5 | No | 0.7 | No | 3.6 | 60% | 117 |
| 2026-06-18 | 278 | $113 | 1.2 | No | 0.4 | No | 6.2 | 64% | 144 |
| 2026-06-19 | 82 | $148 | **0.2** | No | **0.1** | No | **2.1** | **91%** | 190 |

No books-pinned-at-80 events on any day. The pattern today is the opposite: books near zero, not saturated.

**Today (Jun 19) by UTC hour:**

| Hr | N | AvgPost | Zero% | Bks/80 | YBks/50 | NOcands | YRsvSkip |
|---|---|---|---|---|---|---|---|
| 00 | 12 | 14.0 | 92% | 0.2 | 0.1 | 138 | 0.0 |
| 01 | 12 | 0.1 | 92% | 0.2 | 0.1 | 165 | 7.2 |
| 02 | 12 | 0.1 | 92% | 0.2 | 0.1 | 149 | 0.8 |
| 03 | 12 | 0.1 | 92% | 0.2 | 0.1 | 151 | 0.4 |
| 04 | 11 | 0.0 | 100% | 0.0 | 0.0 | 275 | 4.9 |
| 05 | 12 | 0.0 | 100% | 0.0 | 0.0 | 246 | 10.1 |
| 06 | 11 | 0.5 | 73% | 0.8 | 0.4 | 211 | 3.1 |

**ALERT — Jun 19 zero-post rate 91% vs 60–64% on prior days; books=0.2/80.**

Characteristics of the failure mode:
- `cash_preskip=$148` — not cash-starved (≈70% of capital, consistent with `BAND_NO_CASH_RESERVE=0.30` holding 30% for NO)
- `no_cands=190+` — ample NO opportunities every cycle, not being converted
- `yes_resv_skip` peaks 10.1/cycle at hr 05 — YES candidates are blocked BEFORE order book fetch
- When `yes_resv_skip>0` and `books=0` in the same cycle, the skip mechanism consumes the YES allocation without triggering a book poll

Probable cause: `BAND_NO_CASH_RESERVE=0.30` (introduced 2026-06-18) interacting with the days-out priority queue (`BAND_PROPORTIONAL_QUEUE=False`, set same day) is creating YES headroom contention in the early-morning low-activity window. Initial restart burst at hr 00 posted 9 tokens (across 1–2 productive cycles), exhausting eligible near-mode slots. Subsequent cycles find nothing new to post because: (a) eligible d+1/d+2 YES slots are already resting, and (b) the NO reserve check is blocking YES candidates from reaching the book-fetch stage. Hours 04–05 UTC are the quietest window globally; the 100% zero-post rate there may normalize after the peak window opens (13:00+ UTC).

Not classified as "fetch starvation regression" (books not pinned at 80). Classified as deployment stall: cash_preskip > $100 sustained while posted≈0 across most cycles.

---

## Section 4 — Resolution Markout

**Network constraint:** Sandbox has no egress to `gamma-api.polymarket.com` (all requests blocked). `band_resolution_join.py` returned 0 resolved legs — today's markets are open, and historical `logs/shadow/hot/<date>/band_struct.jsonl` files are not available on the audit branch. **The adverse-selection comparison (filled-ROI vs all-fires-ROI) cannot be computed here.** Run `band_resolution_join.py` on the VPS.

**Partial observable: winner exits only** (`exit099_live.jsonl`, `record=recycle099`)

| Date | n Winners | AvgEntry | Cost $ | PnL $ | ROI |
|---|---|---|---|---|---|
| 2026-06-16 | 10 | 0.476 | $75.65 | $84.31 | +111.5% |
| 2026-06-17 | 20 | 0.347 | $40.06 | $87.45 | +218.3% |
| 2026-06-18 | 26 | 0.350 | $59.11 | $99.56 | +168.4% |
| 2026-06-19 (7h) | 3 | 0.263 | $4.17 | $11.67 | +279.9% |
| **TOTAL** | **59** | **0.366** | **$178.98** | **$282.99** | **+158.1%** |

Winner exits by entry price band (winner-only ROI):

| Band | n | ROI |
|---|---|---|
| < 0.10 | 4 | +1728% |
| 0.10–0.30 | 23 | +409% |
| 0.30–0.50 | 21 | +188% |
| 0.50–0.85 | 4 | +44% |

**Hard caveat:** These 59 are winners only. Loser exits (resolved to 0.00) have no log record — the SELL_EXIT at 0.99 simply never fills, and the entry cost is a total loss. The 101 SELL_EXIT orders resting in the book contain a mix of future winners and future losers. True net ROI = winner_pnl − Σ(entry_cost × loser_shares); the loser set is unknown.

n=59 is trend-grade (40–99). No winner's-curse flag can be raised or cleared without the all-fires comparison. **Section 4 INCOMPLETE — compute on VPS.**

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|---|---|
| "reaped dead entry" log lines (7d) | 0 |
| Reclaim log mentions | 0 |
| Total resting orders | 116 |
| SELL_EXIT orders | 101 |
| Active maker bids | 15 |
| Oldest resting quote | 42.5h |
| Orders > 24h | 5 |
| Orders > 48h | **0** |

**No ALERT.** Zero orders older than 48h (alert threshold: >20 orders >48h). Five orders in the 24–48h window are within normal reclaim lag (`BAND_RECLAIM_AGE_S=7200` = 2h reclaim for directional legs; `BAND_PAIR_RECLAIM_AGE_S=28800` = 8h for pair legs). Absence of reaped-dead log lines in a 7-day window suggests either (a) reclaim is running but not logging reaps, or (b) all resting quotes remain competitive. Neither is an alert condition given zero quotes >48h.

SELL_EXIT face value resting: **$754.61** — positions pending market resolution, not stale capital.

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $224.29 |
| Active maker bids deployed | $21.11 (9.4% of capital) |
| SELL_EXIT face value resting | $754.61 |
| Registered maker fills — 24h | $122.70 |
| Untracked exit fills — 24h | ~$4,697 (manual/unregistered; not bot PnL) |
| **Equity turns/day (fills only)** | **0.55×** |
| Badatmath benchmark | ~1.0×/day |

The $4,697 untracked daily exit flow is almost certainly from user-manual positions (sizes up to 4,365 sh on a $224 bot balance — physically impossible as bot-placed). Excluded from bot velocity calculation.

Bot equity turns at **0.55×/day** — below badatmath's ~1.0× benchmark. The gap is not from poor fill rates (78–99% of posted tokens fill) but from low posting volume:
- Only $21 of capital deployed in live maker bids at snapshot (9.4%)
- 91% zero-post rate today limits new deployment
- ~$136 of free YES capital available but not reaching book-fetch stage (yes_resv_skip)

---

## ALERTS (pre-registered, fired)

### ALERT 1 — NO-PARITY BELOW 25%
- **Scope:** Every day with n≥10 posts (Jun 14–18, 5 of 5 days)
- **Values:** 23.0%, 2.2%, 9.9%, 5.6%, 15.9% — all below 25% threshold; Jun 15 is severe
- **Live resting book:** 1 NO of 15 active quotes (6.7%)
- **Context:** BAND_NO_ENABLED=True, NO config intact. "NO-starvation fix" of 2026-06-12 not holding
- **Recommended action (VPS):** Trace `fire_no` generation counts vs `post` counts for NO — check if fire_no records are being generated but not executed, or if generation itself is failing

### ALERT 2 — DEPLOYMENT STALL (Jun 19)
- **Scope:** 91% zero-post cycles on Jun 19 vs 60–64% baseline
- **Signature:** `books=0.2/80`, `yes_resv_skip` up to 10.1/cycle, `cash_preskip=$148`, `no_cands=190+`
- **Cash starvation?** No — cash_preskip is healthy
- **Books pinned at 80?** No — books are near zero, not saturated
- **Best candidate cause:** `BAND_NO_CASH_RESERVE=0.30` (added 2026-06-18) + rank-mode queue (`BAND_PROPORTIONAL_QUEUE=False`, same day) blocking YES book fetches in early-morning quiet window after midnight restart
- **May self-resolve** after peak window opens (13:00 UTC); monitor next STRUCT-BAND-Q report after 13:00 UTC

---

## Summary (3 lines)

**Fills/day:** ~95/day baseline (Jun 17–18); fill rate per posted token 78–99% — quoting execution is clean when the bot posts. Today only 5 fills in 7h post-restart.

**NO share:** 2.2%–23.0% across 5 days — chronically below 25% target; fix from 2026-06-12 is not holding. Live resting book 6.7% NO.

**Binding execution constraint today:** Book fetch rate. Bot restarted 00:17 UTC, posted 9 tokens in initial burst, then 91% of subsequent cycles fetched 0 books and posted 0 quotes — yes_resv_skip mechanism blocking YES candidates, NO starvation blocking NO candidates, leaving $136 of YES capacity idle. Monitor after 13:00 UTC.
