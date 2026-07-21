# Klaus Band Execution & Markout Audit
**Date:** 2026-07-21
**Snapshot:** 2026-07-21T07:06:53Z (age < 6h ✓)
**System:** `service status: active` (uptime since 2026-07-17 22:05 UTC) ✓
**Capital:** $21.495 (bankroll.json — CAVEAT: includes manual sells; do not read as bot-only P&L)
**Open positions:** 0 | **Resting orders:** 0

---

## CONTEXT: Band Maker Status

**BAND_LIVE = False** (wound down 2026-07-06; equity below 50%-HW charter trigger)
**BAND_NO_ENABLED = False** (rail-halt 2026-07-02; 7d realized WR flagged)
**BAND_YES_LIVE_MIN_DOUT = 9** (standalone YES paused; 9=never fires at current d+2 horizon)
**BAND_PAIR_FAV_ENABLED = True** (parameter set, gated by BAND_LIVE=False)
**MAKER_SHADOW_ENABLED = True** (shadow quoting active; no execution)
**BAND_SHADOW = True** (band shadow evaluation active; no execution)

The band maker strategy has been fully wound down since 2026-07-06. Shadow engine is running
and healthy — band_struct_lite for 2026-07-21 shows `"live": false` fire records firing
normally through 07:07Z. Active live strategy is UPDOWN sniper only. Capital unchanged from
Jul 20 daily_start ($21.495) — no sniper trades on Jul 20.

---

## Section 1 — Fill Tape (24h + 7d)

### Band [MAKER-FILL] fills

| Window | Fills (n) | $ filled | By side | By price band |
|---|---|---|---|---|
| 24h (Jul 20 07:07 → Jul 21 07:07) | **0** | $0.00 | — | — |
| 7d (Jul 14 → Jul 21 07:07) | **0** | $0.00 | — | — |

Zero `[MAKER-FILL]` lines in `maker_fills_recent.log`. Structurally expected: last band
post date in `band_posted_state.json` is 2026-07-06. Fill rate: undefined (0 posts since
wind-down). Time-to-fill: not computable.

### Untracked fills (out of band-maker scope — UPDOWN sniper / legacy resting orders)

Log covers Jul 18–19 UTC. Jul 17 entries have rotated off the 7d window.

| Day | Fills (n) | MAKER | TAKER | Notable |
|---|---|---|---|---|
| Jul 18 | ~5 | ~2 | ~3 | MAKER BUY@0.08; TAKER at 0.97–0.98 |
| Jul 19 | **6** | **1** | **5** | MAKER BUY@0.02 (146.33 sh); TAKER at 0.88–0.98 |
| Jul 20–21 (24h) | **0** | 0 | 0 | No new fills logged |
| **7d total** | **~11** | **~3** | **~8** | |

All untracked — no tracker entry, no open position in bot scope. Price band breakdown (7d):
<0.10: ~3 MAKER fills; 0.10–0.85: 0; >0.85: ~8 TAKER fills. Bimodal pattern consistent with
orphaned legacy CLOB resting orders at extreme-low YES prices + UPDOWN sniper near-resolution
buys. The MAKER@0.02, 146.33 sh fill (Jul 19) = ~$2.93 capital risk, UNTRACKED — no
resolution PnL measurable.

---

## Section 2 — NO-Parity Monitor

**Status: Vacuous — BAND_NO_ENABLED=False, zero live posts in all audit days.**

| Date | New YES posts (live) | New NO posts (live) | NO share | ≥10 posts? | Alert? |
|---|---|---|---|---|---|
| 2026-07-18 | 0 | 0 | — | No | — |
| 2026-07-19 | 0 | 0 | — | No | — |
| 2026-07-20 | 0 | 0 | — | No | — |
| 2026-07-21 (to 07:07) | 0 | 0 | — | No | — |

### Shadow side distribution (band_struct_lite, confirming code-level NO-starvation fix)

| Date | Shadow yes_capture_shadow (YES) | Shadow NO side | NO shadow share |
|---|---|---|---|
| 2026-07-18 | 56 | 0 | 0% |
| 2026-07-19 | 57 | 0 | 0% |
| 2026-07-20 | ~56 | 0 | 0% |
| 2026-07-21 (partial) | varies | 0 | 0% |

`band_posted_state.json` last key: 2026-07-06. `maker_resting_state.json`: `{}` (0 YES, 0 NO).
Shadow YES-capture records uniformly `side: "YES"` — consistent with BAND_NO_ENABLED=False
suppressing NO-side quoting at the band engine level. NO-starvation fix (2026-06-12 commit
`fix(BAND): NO-starvation`) holds vacuously; cannot verify live behavior until band re-arms
and NO is reenabled.

**Alert — NO share < 25% on any day with ≥10 live posts: NOT FIRED** (0 live posts all days).

---

## Section 3 — Queue Health

**Status: Vacuous — zero [STRUCT-BAND-Q] lines; BAND_LIVE=False suppresses live cycles.**

No `[STRUCT-BAND-Q]` lines in `maker_fills_recent.log`. No cycle metrics (cash_preskip,
books_used, yes_books, posted/cycle) to report.

### Shadow engine activity (band_struct_lite 2026-07-21, 00:00–07:07Z)

| Pass time (approx) | Scope | Fires (live=false) | Sum-gate blocks | Notes |
|---|---|---|---|---|
| ~04:45Z | d+0 spot: 10 cities | 0 (all no_band/converged) | — | London d+0 mode_ask 0.365–0.40 |
| ~04:46Z | d+1 (Jul 22): all 10 cities | 0 | 10 sum_gate | sum_ask 0.87–1.02; too-high sum |
| ~04:47Z | d+2 (Jul 23): all 10 cities | 8 | 2 sum_gate | London/Seoul sum_ask=0.57 (3 legs); Munich 0.82 (5); Tokyo 0.80 (5); Shanghai 0.77 (5); Taipei 0.67 (4); Beijing 0.78 (5); Wuhan 0.66 (5). Chongqing/Chengdu sum_gate (1.01–1.13) |
| ~05:23Z | d+1 rechecks + KL/Manila d+0 | 0 | — | Kuala Lumpur/Manila: no_band (0 valid markets) |
| ~06:57Z | d+1 Beijing rescan | 1 | — | Beijing d+1: sum_ask=0.84 (5 legs, live=false) |
| **Total** | | **9 fires** | | All live=false |

Shadow fires are structurally sound (n_legs=3–5, sum_ask=0.57–0.84, bell-shaped stake
weights: $3.0 mode / $1.35 off±1 / $1.0 off±2). Two new cities (KL, Manila) appeared in
d+0 feed — both no_band, consistent with thin market coverage on near-resolution day. Engine
is alive and would post if re-armed.

**Alert — books pinned at 80 or yes_books pinned at 50 most cycles: NOT FIRED** (no queue data).
**Alert — cash_preskip > 200 sustained with posted=0 all day: NOT FIRED** (no queue data).

---

## Section 4 — Resolution Markout (Fill Quality / Winner's Curse)

**Status: Cannot compute — 0 band [MAKER-FILL] fills available.**

n = 0. Below the 40-fill threshold for any conclusions.

`band_resolution_join.py` not run — empty fill input.

### Shadow markout preview (hypothetical, non-causal)

Today's shadow fires would quote YES at bid prices of 0.177–0.252 on the mode leg across
d+2 markets (Jul 23 resolution). Reference market ask prices: 0.19–0.25 (YES side, from
`would_quote` field). Spread at mode: 0.57–0.84 (YES sum). These are not fills; no
winner's-curse test can be applied.

Winner's curse assessment: **deferred indefinitely until band re-arms and fills accumulate.**

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|---|---|
| `maker_resting_state.json` entries | **0** |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |
| "reaped dead entry" lines (7d log) | 0 |
| $ freed by reclaim | $0.00 |

Resting book is empty; nothing to reclaim. `BAND_RECLAIM_AGE_S` and `BAND_PAIR_RECLAIM_AGE_S`
are configured but have no quotes to evaluate.

**Alert — >20 quotes older than 48h: NOT FIRED** (0 resting quotes).

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $21.495 |
| Daily start capital (today) | $21.495 (no change from Jul 20) |
| Resting $ (Σ q_price × unmatched size) | $0.00 |
| Band fills $ last 24h | $0.00 |
| Turns/day (band) | 0.00 |
| Benchmark (badatmath ~1.0 turn/day) | — |

Capital flat Jul 20→21: UPDOWN sniper did not trade on Jul 20. Total cumulative PnL since
inception (bankroll.json `total_pnl`): −$75.40 across 3,093 total trades. Do not read
$21.495 as band-driven; band has generated $0 fills since Jul 6.

System-status note: disk at 89% (82 GB of 97 GB used) per system_status.txt — not a trading
blocker but worth monitoring if shadow JSONL accumulation continues at current rate.

---

## ALERTS

*Pre-registered alerts that actually fired: **none**.*

| Alert condition | Status |
|---|---|
| NO share of new posts < 25% on any day with ≥10 live posts | NOT FIRED (0 live posts) |
| Books pinned at 80 / yes_books pinned at 50 most cycles | NOT FIRED (no queue data) |
| cash_preskip > 200 sustained, posted=0 all day | NOT FIRED (no queue data) |
| >20 quotes older than 48h | NOT FIRED (0 resting quotes) |
| Winner's curse: filled ROI << all-fires ROI at n≥40 | NOT FIRED (n=0 fills) |

---

## Summary

**Fills/day: 0** — band wound down 2026-07-06; zero registered fills in the 7d tape.
**NO-share: N/A** — 0 posts since 2026-07-02; parity fix holds vacuously, unverifiable.
**Binding execution constraint: BAND_LIVE=False** (equity-floor charter trigger); shadow engine
is healthy with 9 fires today across d+2 Jul 23 (8 cities) + d+1 Beijing, but no capital
deployment until charter conditions are met. UPDOWN sniper is the sole active strategy — no
sniper trades logged on Jul 20; capital flat at $21.495.
