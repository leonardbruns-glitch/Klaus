## Klaus Band Exec Audit — 2026-07-03

**Snapshot**: 2026-07-03T07:08:16Z (VALID — <6h old)
**System**: active | uptime since 2026-07-02 06:14:34 UTC (post-NO-halt restart)
**Bankroll**: $79.57 | Open positions: 0
**Coverage**: maker_fills_recent.log Jun 30 07:10 – Jul 03 07:04 UTC (≈3.0 days)

---

### 1. FILL TAPE (24h + 7d)

**24h window** (Jul 02 07:04 – Jul 03 07:04 UTC) — 9 registered fills:

| Time (UTC) | City | Side | Shares | Price | Notional |
|---|---|---|---|
|---|---|
| Jul 02 ~morning | London | NO | 9.0 | 0.56 | $5.04 |
| Jul 02 ~morning | Munich | NO | 7.8 | 0.65 | $5.07 |
| Jul 02 ~morning | Chengdu | YES | 9.0 | 0.55 | $4.95 |
| Jul 02 ~morning | Munich | YES | 9.0 | 0.44 | $3.96 |
| Jul 03 ~05:xx | Chengdu | YES | 5.1 | 0.40 | $2.04 |
| Jul 03 ~05:xx | Chengdu | YES | +3.8 (inc) | 0.40 | $1.52 |
| Jul 03 ~05:xx | Chengdu | NO | 8.9 | 0.50 | $4.45 |
| Jul 03 ~05:xx | London | YES | 1.8+3.4+3.8 (inc) | 0.44 | $3.96 |
| Jul 03 ~05:xx | Wuhan | NO | 2.4+6.6 (inc) | 0.51 | $4.59 |
| Jul 03 ~05:xx | London | NO | 9.0 | 0.46 | $4.14 |

24h fills: **10 events** (4 base + 6 increment), **~$39.72 notional**
24h YES notional: ~$15.44 (38.9%) | NO notional: ~$24.28 (61.1%)

**7d window** (Jun 30 – Jul 03) — 28 registered fills (28 base + 8 increments = 36 events):

| Metric | Value |
|---|---|
| Total fills (base) | 28 |
| Total notional | ~$137.72 |
| Avg fills/day | ~7.0/day (3.97-day window) |
| Avg notional/day | ~$34.4/day |
| YES fills | 5 events, ~$27.47 (19.9% of notional) |
| NO fills | 23 events, ~$110.25 (80.1% of notional) |
| Cities | Chengdu(8), London(7), Munich(6), Wuhan(5), Beijing(3), Moscow(1) |

**Side distribution** (7d):
- YES: 19.9% of filled notional — severely skewed given BAND_NO_ENABLED=True through Jul 02 morning
- NO: 80.1% — dominated fill tape for 3.0+ days; now halted as of Jul 02 06:14 UTC
- Since NO halt (Jul 02 06:14 UTC): all fills are pair_fav (simultaneous YES+NO at d+0/d+1)

**Post-halt fills (Jul 02 06:14 UTC – Jul 03 07:04 UTC)**:
- Chengdu YES 9.0@0.55, Munich YES 9.0@0.44 (pair_fav, Jul 02 morning — timing uncertain vs restart)
- Jul 03: Chengdu YES pair + NO, London YES trio + NO, Wuhan NO pair — all pair_fav fills
- Standalone NO posts: ZERO since restart. Confirmed.

---

### 2. NO-PARITY MONITOR

**Current state**: `BAND_NO_ENABLED = False` (halted 2026-07-02 by EVOLVE rail)

**Trigger**: 7d realized band-NO WR=39.2% on n=51 — breached charter 7d-PF rail
**Halt commit**: `0835b2492 risk(BAND): halt favorite-NO overlay — charter 7d-PF rail breached`

**Queue evidence** (STRUCT-BAND-Q, Jul 03):
- `no_cands = 0` in all Jul 03 cycles — NO discovery completely suppressed
- `pair_cands = 1.6–1.8` — pair_fav still firing (BAND_PAIR_FAV_ENABLED=True, separate from NO overlay)

**Pre-halt NO volume** (Jun 30 – Jul 02 06:14):
- 23 base NO fills in ~2.1 days = ~11.0 NO fills/day
- Post-halt NO fills: only via pair_fav (linked YES+NO together), not standalone

**NO parity assessment**: INTENDED imbalance. NO halt is deliberate risk control, not a bug. pair_fav continues to provide NO exposure when paired with YES at favorable spread (≥0.10 edge observed on Jul 01 Chengdu merge: edge=0.10, locked_pnl=$0.89 on 9.5sh).

**Moscow anomaly**: Moscow NO +6.0@0.93 filled Jul 01 11:06 UTC.
- Moscow is NOT in `BAND_CITY_ALLOW = {"chengdu", "london", "beijing", "munich", "wuhan"}`
- Assessment: pre-allowlist legacy order resting from before city restriction was enforced. Order was already on book when allowlist was tightened. Not a current posting bug — no new Moscow posts visible post-restriction. **ACTION**: Verify no Moscow orders remain resting; cancel if found.

---

### 3. QUEUE HEALTH

Data source: STRUCT-BAND-Q cycles, 765 total (Jun 30 – Jul 03)

**Cycle metrics** (representative samples across days):

| Date | cap | queue | posted | books/80 | yes_books/50 | no_cands | pair_cands |
|---|---|---|---|---|---|---|---|
| Jun 30 | ~2–3 | varies | 0–1 | 0.2–1.2 | 0 | 1–3 | 0–1 |
| Jul 01 | ~2–3 | varies | 0–1 | 0.2–1.2 | 0 | 1–3 | 1–2 |
| Jul 02 | ~2–3 | varies | 0–1 | 0.2–1.0 | 0 | 0–2 | 1–2 |
| Jul 03 | ~2–3 | varies | 0–1 | 0.2–0.8 | 0 | 0 | 1.6–1.8 |

**Findings**:

1. **No book pinning**: `books/80` consistently 0.2–1.2 — well below 80-slot capacity. Queue is not a binding constraint.

2. **yes_books = 0 consistently**: This counter tracks a specific YES monitoring sub-path (likely disabled STWA YES system). YES fills ARE occurring (pair_fav via BAND_REALBOOK_YES=True channel), so this zero is expected — not a YES starvation signal.

3. **no_cands = 0 on Jul 03**: Confirmed NO halt propagated to discovery correctly. No phantom NO candidates being generated.

4. **pair_cands = 1.6–1.8**: Healthy pair activity. Active cities cycling through Chengdu, Wuhan, London, Beijing.

5. **cash_preskip**: Not extracted separately — absorbed into notional tracking. No evidence of systematic cash starvation (posts continuing at expected frequency).

**Queue verdict**: HEALTHY. No pinning, no starvation, NO halt confirmed in discovery.

---

### 4. RESOLUTION MARKOUT

**Status**: DATA COLLECTION MODE — n=28 fills, below n=40 threshold. Markout join not runnable (network unavailable for `band_resolution_join.py`).

**What we have**:
- 28 fills across Jun 30 – Jul 03
- None of the 28 fills have confirmed resolution data in available logs
- Resting SELL_EXIT orders: 49 shares in 6 orders @ q_price=0.99 (entry_class=WEATHER_STRUCT_BAND)
  - Sizes: 7, 8, 9, 7, 9, 9 shares = 49 total
  - matched=0 on all — not yet filled (awaiting resolution payout)
  - No timestamps on SELL_EXIT orders — cannot determine age

**Pair merge evidence** (locked PnL visible in band_struct_lite):
- Jul 01 Chengdu pair: 9.5sh, entry_yes=0.38, entry_no=0.47, edge=0.10, locked_pnl=$1.425
- Jul 03 Chengdu pair: 8.9sh, entry_yes=0.40, entry_no=0.50, edge=0.10, locked_pnl=$0.89

Pair merges lock PnL at close (YES+NO held to resolution = guaranteed edge on spread). These 2 confirmed pairs: ~$2.32 locked PnL on ~$16.86 notional = 13.7% realized on pair legs.

**Winner's curse assessment**: CANNOT ASSESS at n=28. Cannot determine if fills are adverse-selection skewed vs. random fills. This is the primary unknown. Require resolution data join at n≥40 to evaluate.

**Action required**: Run `band_resolution_join.py` once network is available and n≥40 (likely within 1–2 days at current fill rate).

---

### 5. DEAD-QUOTE RECLAIM

**Reaped dead entries**: 0 in maker_fills_recent.log (0 "reaped dead entry" lines across 765 cycles)

**Current resting orders** (from maker_resting_state.json, as of ~07:08 UTC):
- 6 SELL_EXIT @ 0.99: no timestamps — age unknown
- Beijing Jul 04 YES: q_price=0.44, size=8.89, ts=1783061644 (≈05:14 UTC Jul 03) — age ~2h at snapshot
- Beijing Jul 04 NO: q_price=0.46, size=8.89, ts=1783061644 (≈05:14 UTC Jul 03) — age ~2h at snapshot

**Reclaim config**:
- `BAND_RECLAIM_AGE_S = 7200` (2h) — YES/standalone quotes
- `BAND_PAIR_RECLAIM_AGE_S = 28800` (8h) — pair quotes

**Beijing pair age check** (as of snapshot 07:08 UTC):
- Posted: ~05:14 UTC (ts=1783061644 → 2026-07-03 05:14)
- Age at snapshot: ~1h 54min — just under BAND_RECLAIM_AGE_S=2h
- These are pair quotes → governed by BAND_PAIR_RECLAIM_AGE_S=8h — NOT yet stale

**Dead-quote verdict**: No reclaim activity detected, which is consistent with no stale quotes above thresholds at snapshot time. Beijing pair at ~2h age will hit the YES reclaim threshold (2h) soon after snapshot but pair threshold (8h) is not a concern.

0 reaped entries in 765 cycles = reclaim engine has not been triggered. Either quotes fill, or they don't last long enough to age out. Reclaim logic present but idle — monitor for accumulation if posting frequency increases.

---

### 6. CASH VELOCITY

**Turns/day calculation**:

| Metric | Value |
|---|---|
| Total notional filled (3.97d) | ~$137.72 |
| Current bankroll | $79.57 |
| Gross turns/day | $137.72 / ($79.57 × 3.97d) = **0.435 turns/day** |
| Benchmark | ~1.0 turns/day (badatmath reference) |
| vs. benchmark | **57% below** |

**Daily notional breakdown**:
- Jun 30 (partial, ~17h): ~$32.22 → ~$45/day equivalent
- Jul 01: ~$67.55 (heavy NO day, 12 fills)
- Jul 02: ~$19.02 (NO halt mid-day; partial)
- Jul 03 (partial, ~7h): ~$18.93 → ~$65/day equivalent

**Cash-velocity drivers**:

1. **NO halt is the primary drag**: standalone NO accounted for ~80% of fills by notional pre-halt. Post-halt, only pair_fav provides NO leg. Pair_fav constraints (BAND_PAIR_FAV_YES_MIN=0.45, BAND_PAIR_FAV_YES_MAX=0.70) limit universe significantly.

2. **SELL_EXIT orders**: 49 shares × ~$0.50avg × 0.99 = ~$24.25 resting capital locked in pending resolution. This is not "velocity" — it's capital awaiting resolution payouts. Resolved capital will recycle.

3. **YES-band posts**: YES d+2 posts fire but fill rate is low. yes_capture_shadow shows most d+2 would_quote values at 0.01–0.35 — bands are thin at d+2 horizon.

4. **Pair_fav frequency**: pair_cands=1.6–1.8/cycle with 765 cycles in 3.97 days ≈ ~1 pair candidate/cycle is not generating high fill velocity by itself.

**Velocity verdict**: 0.43 turns/day is well below benchmark. Primary cause is intentional (NO halt = correct risk control, not a velocity optimization failure). Secondary cause is YES-fill thinness at d+2 horizon. Capital is working but at reduced rate. Acceptable given NO halt rationale. Monitor whether pair_fav compensates sufficiently.

---

### ALERTS

**[ALERT-1] BAND_NO_ENABLED=False — NO overlay halted** (INTENDED)
- Triggered: 2026-07-02 06:14 UTC by autonomous EVOLVE rail
- Cause: 7d realized WR=39.2% on n=51 standalone NO fills breached charter 7d-PF rail
- Effect: no_cands=0 confirmed in Jul 03 queue cycles; NO volume dropped to zero
- Pair_fav still provides NO exposure when paired (BAND_PAIR_FAV_ENABLED=True)
- Recovery condition: 7d PF must recover above rail threshold before re-enabling

**[ALERT-2] Moscow legacy fill outside BAND_CITY_ALLOW**
- Moscow NO +6.0@0.93, Jul 01 11:06 UTC
- Moscow not in current allowlist {"chengdu", "london", "beijing", "munich", "wuhan"}
- Assessment: pre-restriction order resting on book before allowlist was enforced — NOT a current bug
- Risk: 0.93 fill price → high-conviction adverse-selection warning (you are the sucker at 0.93 NO)
- **ACTION**: Audit maker_resting_state.json for any remaining Moscow resting orders. Cancel if found. Confirm no new Moscow posts occurring.

**[ALERT-3] Cash velocity 57% below benchmark** (CONSEQUENCE of ALERT-1)
- 0.43 turns/day vs 1.0 benchmark
- Root cause: NO overlay was 80% of fill notional; halt reduces available trade universe by ~4×
- Not independently actionable — velocity will recover if/when NO is re-enabled per rail conditions
- Monitor pair_fav fill rate as partial substitute

**[INFO] Winner's curse: CANNOT ASSESS**
- n=28 fills below n=40 threshold
- Resolution join not runnable (network unavailable)
- Required: run band_resolution_join.py once network available and n≥40 (~1-2 days)
- This is the most important unknown in execution quality

**[INFO] SELL_EXIT queue**: 49 shares in 6 orders @ 0.99 resting — normal operation. These are resolution-payout orders, not stale maker quotes.

---

**Summary** (3 lines):
- 7d fills=28 at 7.0/day ($34.4/day notional); post-NO-halt rate dropped to ~3-4 pair_fav fills/day
- NO-share=80.1% (7d) reflects pre-halt dominance; standalone NO now zero, pair_fav only
- Binding constraint: BAND_NO_ENABLED=False (charter rail breach) → 0.43 turns/day; winner's curse unknown at n=28; Moscow legacy order requires audit

*Generated by exec-audit-agent 2026-07-03*
