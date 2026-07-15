# Klaus Band Execution & Markout Audit — 2026-07-15

**Snapshot**: 2026-07-15T07:00:05Z  |  **Klaus service**: active  |  **Uptime since**: 2026-07-15T02:40:11Z  
**Capital**: $34.24  |  **Resting $**: $0.00  |  **Open positions**: 0  
**Data freshness**: ✓ (<6h old — proceeding)

---

## PREAMBLE — Band Engine Status

`BAND_LIVE = False` (wind-down triggered 2026-07-06: equity $108.35 < 50%·30d-HW $222.90).  
`BAND_NO_ENABLED = False` (disabled 2026-07-02: 7d realized WR 39.2% n=51).  
`BAND_YES_LIVE_MIN_DOUT = 9` (standalone YES paused).  
`BAND_PAIR_FAV_ENABLED = True` but gated by `BAND_LIVE = False` — inoperative.

**Result**: The band/maker execution engine has been fully offline since 2026-07-06. All six sections below reflect this reality. Sections that require live fills or resting orders report zero.

---

## §1 — FILL TAPE (24h + 7d)

### Log Format Audit
The fill log (`maker_fills_recent.log`) contains **zero** `[MAKER-FILL]` lines, **zero** `[STRUCT-BAND-Q]` lines, and **zero** `reaped dead entry` lines across the entire 7-day window.

All lines are `[USER-WS] UNTRACKED FILL: ... no tracker entry, no open position` — the bot is receiving WebSocket fill events for trades it has no tracker state for.

### Fill Count (MATCHED events only, deduplicated)

| Date | Fill Events | Band | Non-band | Notes |
|---|---|---|---|---|
| Jul 12 | 4 | 0 | 4 | 2 TAKER (fat middle, large: 31–34 sh); 2 MAKER |
| Jul 13 | 17 | 0 | 17 | 2 large TAKER fat-middle (45–51 sh); 1 MAKER @0.03; rest thermo/sniper pairs |
| Jul 14 | 35 | 0 | 35 | 4 MAKER at extreme prices (0.02–0.06); 1 MAKER SELL @0.98 size=367.66 (anomaly); rest sniper/thermo pairs |
| Jul 15 (00:00–07:00) | 4 | 0 | 4 | Thermo BUY+SELL pairs |
| **7d total** | **60** | **0** | **60** | 100% untracked |

### $ Filled (24h: Jul 14 07:00 – Jul 15 07:00)

| Side | Gross notional | Notes |
|---|---|---|
| BUY | ~$92 | 17 BUY events; TAKER at 0.92–0.989; MAKER at 0.02–0.06 |
| SELL | ~$449 | Includes 367.66 sh × $0.98 MAKER anomaly ($360.3) |
| **Total notional** | **~$541** | Ex-anomaly: ~$181 |

### By price band (all 60 fills)
| Price band | Fill count | $ notional | Maker/Taker |
|---|---|---|---|
| <0.10 | 6 BUY | $5.5 | All MAKER |
| 0.10–0.30 | 0 | — | — |
| 0.30–0.50 | 5 | ~$107 | All TAKER, large sizes (31–51 sh) |
| 0.50–0.85 | 3 SELL | ~$22 | TAKER |
| >0.85 | 46 | ~$406 | Mixed; $360 from single MAKER anomaly |

### Fill rate
- Band posted tokens: 0 (since Jul 6); fill rate: N/A.
- Non-band fill rate not measurable (no posting record for these strategies).

---

## §2 — NO-PARITY MONITOR

`band_posted_state.json` last entry: **2026-07-06**. No posts since.  
`maker_resting_state.json`: **{}** (empty — zero resting orders of any kind).  
`band_struct_lite.jsonl` (today): all `"fire"` records carry `"live": false` (shadow only); no `"post"` records.

**Post counts by side since Jul 6**: N/A (no live posts).  
**NO share of new posts**: N/A.

Historical context: BAND_NO_ENABLED was disabled Jul 2 (before BAND_LIVE disabled Jul 6). The NO-starvation fix from 2026-06-12 cannot be verified on zero new posts.

**ALERT**: NO-PARITY not verifiable — band offline. Last known NO-enable window was Jun 12–Jul 2.

---

## §3 — QUEUE HEALTH

No `[STRUCT-BAND-Q]` lines in fill tape (expected: present each 300s cycle if band is live).

`count_lock.jsonl` row count: 0 for every day Jul 10–15 (confirmed via shadow_summary) — confirms zero live band posting cycles.

Shadow maker (`MAKER_SHADOW_ENABLED = True`) is running; `maker_shadow.jsonl` shows 28k rows today (shadow observations only, not live orders).

`band_struct.jsonl` still writing ~7600–7700 rows/day — this is shadow data (observation + evaluation), not live orders.

**ALERT**: Queue health cannot be measured — band engine offline. No `[STRUCT-BAND-Q]` lines observed.

---

## §4 — RESOLUTION MARKOUT (Fill Quality / Adverse-Selection Test)

**n = 0 band fills in 7d window.** No maker fill tape exists to join to resolution outcomes. Markout analysis requires at minimum n=40 fills on the same slice.

Non-band fills in the tape are all UNTRACKED — no entry price or intent is recorded, so adverse-selection analysis is impossible for these either.

Residual resting band orders from pre-shutdown (Jun 17–Jul 6) may be filling as late entrants on deep-discount buckets; several <0.10 MAKER fills in the tape are consistent with this, but without tracker entries or condition_id mapping, resolution cannot be confirmed.

**No winner's curse assessment possible — n=0 tracked fills.**

---

## §5 — DEAD-QUOTE RECLAIM

`maker_resting_state.json` = `{}`.  
Resting orders: **0**. Oldest quote age: N/A. Quotes >24h: **0**. Quotes >48h: **0**.  
`reaped dead entry` lines in fill tape: **0**.

**Dead-quote velocity is clean** — nothing to reclaim, nothing stale. This is consistent with band having been offline for 9 days.

---

## §6 — CASH VELOCITY

| Metric | Value | Notes |
|---|---|---|
| Capital (bankroll.json) | $34.24 | CAVEAT: manual sells not reflected; do not infer PnL from this alone |
| Resting $ | $0.00 | No open maker orders |
| Fills $ last 24h (ex-anomaly) | ~$181 | 24 events; all untracked; ex the $360 MAKER SELL |
| Fills $ last 24h (incl anomaly) | ~$541 | Includes 367.66 sh × $0.98 |
| Band turns/day | 0.0 | Engine offline |
| Non-band gross turns/day (ex-anomaly) | ~5.3× | $181/$34.24 — all from thermo/sniper, all untracked |

**Badatmath benchmark**: ~1.0 equity turn/day at 10–20% ROI/turn. Klaus band is at 0.0.

**Anomaly**: A single MAKER SELL of 367.66 shares at $0.98 (total $360.31) occurred at 2026-07-14 15:49 UTC. This is 10.5× the total reported capital and is almost certainly a pre-existing position or manual exit. It is fully untracked by the bot.

---

## ALERTS

Three pre-registered alerts fired:

### ALERT-1: BAND FULLY OFFLINE (9 days)
- `BAND_LIVE=False` since 2026-07-06, `BAND_NO_ENABLED=False` since 2026-07-02
- Zero new posts, zero resting orders, zero fill tape attribution
- All band_struct fire records carry `"live": false` (shadow only)
- **Scope**: Expected state given charter rail-halt; noting for continuity.

### ALERT-2: UNTRACKED FILL FLOOD — POST-RESTART TRACKER BLINDNESS
- Bot restarted 2026-07-15T02:40:11Z; all 60 fills in 7d window are UNTRACKED
- The bot is receiving WS fill events but has no tracker state for any of them
- Fill pattern (buy+sell pairs at 0.92–0.99 with ~5–6 sh, TAKER) is consistent with thermo/sniper positions opened in prior sessions
- **Action required**: confirm whether persistent position state is loaded at startup or only held in-memory; if in-memory, each restart creates tracker blindness for all open positions

### ALERT-3: ANOMALOUS $360 MAKER SELL (2026-07-14 15:49)
- token=6178261687539843, SELL @0.98, size=367.66 shares, trader_side=MAKER
- Notional = $360.31 vs reported capital of $34.24 (10.5× capital)
- Fully untracked ("no tracker entry, no open position")
- Cannot determine source: pre-existing position, manual order, or prior-session leftover
- Same day: BUY @0.02 7.5sh MAKER at 15:04, BUY @0.06 30.5sh MAKER at 16:24 — consistent with residual band orders still resting on CLOB

---

## SUMMARY

**fills/day**: 0 (band), ~17 (non-band, all untracked) | **NO-share**: N/A (engine offline) | **Binding execution constraint today**: Band maker engine is fully offline (BAND_LIVE=False); no fills, no resting orders, no queue health to measure. The active constraint is tracker blindness — 100% of fills seen by the bot are untracked, including a $360 MAKER SELL of unknown origin. Until band restarts, execution audit has nothing to measure on the primary strategy.
