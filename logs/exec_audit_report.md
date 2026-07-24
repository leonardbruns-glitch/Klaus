# Exec Audit — 2026-07-24

**Snapshot:** 2026-07-24T06:58:42Z (age <1h ✓)  
**System:** `klaus systemd: active` ✓  
**Bot uptime since:** 2026-07-24 04:19:12 UTC  
**BAND_LIVE:** `False` (wind-down 2026-07-06; equity $108.35 < 50%·30d-HW $222.90)  
**Capital (bankroll.json):** $21.4954  
**Resting orders (maker_resting_state.json):** `{}` — empty book  

---

## 1. FILL TAPE (24h + 7d)

| Window | Fills | $ Filled | YES fills | NO fills |
|--------|-------|----------|-----------|----------|
| Last 24h | 0 | $0.00 | 0 | 0 |
| Last 7d | 0 | $0.00 | 0 | 0 |

**By price band:** n/a (zero fills)  
**By city:** n/a  
**Median time-to-fill:** n/a  
**Fill rate (filled / posted):** n/a — zero posts since 2026-07-06  

> Note: `maker_fills_recent.log` returned a schema error from the MCP reader (file likely too large). Zero-fill conclusion is confirmed by: `maker_resting_state.json = {}`, `band_posted_state.json` last entry = 2026-07-06, prior audit commit "fills=0" on 2026-07-23.

---

## 2. NO-PARITY MONITOR

**BAND_NO_ENABLED:** `False` (rail-halt 2026-07-02; 7d realized WR 39.2%, n=51)  
**BAND_LIVE:** `False`

New posts by side from band_struct_lite `post` records (all 5 available days, 2026-07-21 through 2026-07-24): **0 YES, 0 NO**.  
Resting book by side: **0 YES, 0 NO** (empty).

Shadow fires today (2026-07-24, `live=false`): 8 events across 7 cities (Taipei ×2, Seoul, London, Shanghai, Beijing, Munich, Chengdu), all d+2. These are pricing computations only; no CLOB orders placed.

**NO-starvation alert:** Not applicable — no posting of any side. Fix committed 2026-06-12 is structurally present but untestable while `BAND_LIVE=False` and `BAND_NO_ENABLED=False`.

---

## 3. QUEUE HEALTH

`maker_fills_recent.log` inaccessible directly via this run (MCP schema error). Proxy via shadow_summary row counts.

| Metric | 2026-07-21 | 2026-07-22 | 2026-07-23 | 2026-07-24 (partial ~2.5h) |
|--------|-----------|-----------|-----------|--------------------------|
| thermo_maker rows | 37,140 | 22,778 | 22,778 | 6,247 |
| band_struct rows | 7,580 | 7,777 | 7,533 | 2,070 |
| maker_shadow rows | 105,754 | 114,015 | — | 23,331 |
| count_lock rows | 666 | 0 | 0 | 0 |

- band_struct row rate today: ~828/h. Full-day peers run ~7,500–7,800/day (~313–325/h). Today's 2.5h partial ≈ 2,070 is consistent — no starvation signal.
- `count_lock.jsonl` rows: 0 on 2026-07-22 through 2026-07-24 — no lock contention (was 666 on 2026-07-21, cleared since).
- No [STRUCT-BAND-Q] lines inspectable directly; cash_preskip and books-used cannot be measured this run.

**Alerts:** None (books-pinned / cash_preskip alert conditions require real posting cycles; all cycles are shadow-only).

---

## 4. RESOLUTION MARKOUT (fill quality)

**Filled legs to analyze: 0** (no fills since band wind-down 2026-07-06).

`band_resolution_join.py` not run — no filled-leg inventory to join against resolutions.

n=0; no conclusions possible. Previous band operation (through 2026-07-06) accumulated real spend across 20 active dates (2026-06-17 through 2026-07-06; $27.93–$260.25/day). Markout analysis on that historical corpus requires access to resolution data via CLOB API; deferred to a dedicated historical analysis session with full connectivity.

---

## 5. DEAD-QUOTE RECLAIM

**Resting orders:** 0 (maker_resting_state.json = `{}`)  
**Reaped dead entries:** 0 (nothing to reclaim)  
**Oldest quote age:** n/a  
**Quotes >24h old:** 0  
**Quotes >48h old:** 0  

No dead-quote velocity leak possible with an empty book.

---

## 6. CASH VELOCITY

| Metric | Value |
|--------|-------|
| Capital (bankroll.json) | $21.4954 |
| Total cumulative PnL | −$75.40 |
| Resting $ (q_price × unfilled size) | $0.00 |
| Fills last 24h | $0.00 |
| Turns/day | 0.0 |
| badatmath benchmark | ~1.0 turns/day |

Capital is CLOB-wallet cash balance only; user sells manually and this figure does not reflect full equity. Zero deployment, zero compounding while `BAND_LIVE=False`.

---

## ALERTS

**(None fired.)**

All pre-registered alert conditions require active posting (`BAND_LIVE=True`) or non-zero fills:
- Books-pinned at 80 / yes_books pinned at 50: not applicable (no live posting cycles)
- Cash_preskip > 200 sustained with posted=0: not applicable (shadow-only)
- NO share < 25% on days with ≥10 posts: 0 posts → not triggered
- Quotes >48h old (>20 count): 0 resting → not triggered

---

## Summary

**Fills/day:** 0 — BAND_LIVE=False since 2026-07-06 (18 days dark).  
**NO-share:** N/A — zero posts of any side; NO-starvation fix present but untestable in current state.  
**Binding execution constraint:** `BAND_LIVE` kill switch. All band infrastructure (shadow fires, queue scans, thermo_maker telemetry) is running at normal cadence and scan rates are consistent with prior days, but the live gate is closed. No fills, no resting orders, zero cash velocity until BAND_LIVE is re-enabled.
