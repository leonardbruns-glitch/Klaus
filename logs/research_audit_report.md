# Klaus Research Audit — 2026-06-13T10:30Z

**Snapshot**: 2026-06-13T10:19:38Z (11 min old — FRESH ✓)  
**System**: `klaus systemd: active` ✓  
**Capital**: $250.68 (bankroll.json)  
**Specialist reports consumed**: exec_audit 07:09Z ✓ · calib_monitor 08:09Z ✓ · gatekeeper 09:07Z ✓ · pnl_ledger 23:37Z (Jun 12) ✓

---

## 1. PRIMARY BOTTLENECK: EQUITY DEPLOYED — YES POSTING FROZEN

**Rank justification**: turns/day = 0.36–0.55× (exec/pnl) vs badatmath ~1.0×. Fills at $74/day on $250 equity = 0.30× turns. The engine is cycling every 5 minutes, scanning 340+ queue candidates per cycle, and posting ~0.1 orders/cycle. This is not a calibration problem, not a fills-quality problem, and not a capital-scarcity problem. It is a mechanistic deployment freeze.

**Root cause (exec_audit §3)**: The NO cash reserve formula creates a stake floor paradox.

```
yes_cap = BAND_STAKE_FRAC_YES × capital × (1 − BAND_NO_CASH_RESERVE)
         = 0.010 × $250 × 0.50
         = $1.25 / cycle

Minimum YES stake (off=1): BAND_BASE_STAKE × BAND_BELL[1] = $3.0 × 0.70 = $2.10
Minimum YES stake (off=0): BAND_BASE_STAKE × BAND_BELL[0] = $3.0 × 1.0 = $3.00

Both > $1.25 → yes_resv_skip = 58/cycle (all YES candidates rejected, 07:09 UTC)
```

By 09:xx UTC the log shows yes_cap = $0.64–0.69 (tighter still, after intraday capital consumption by NO reserve), yes_resv_skip = 0, books = 0/80. The engine short-circuits the YES loop when yes_cap < min_stake — no book fetches occur, NO candidates are never processed downstream. Result: posted/cycle degraded from **1.7 on Jun 12 → 0.1 today** (−94%). A burst at 10:11 UTC (posted=2, yes_cap=$3.47) confirmed the mechanism works when capital is transiently adequate, then immediately collapsed to yes_cap=$0.17 as the two orders consumed the budget.

NO posting is also stalled: only 2 fire_no events all of Jun 13 despite no_cands = 155–165/cycle, BAND_NO_ENABLED=True, and BAND_NO_DAILY_CAP=$40. The cash reserve earmarked for NO is idle — not protective, just blocking.

**Compounding math**: Restoring yes_cap above $2.10 recovers the Jun 12 baseline of 1.7 posts/cycle (~$75–200/day fills). At identified ROI/turn of 49–70% on resolved legs (exec §4), this is the highest-leverage lever available. All other bottlenecks are secondary to this one.

---

## 2. EXISTING SYSTEM OPTIMIZATION

### 2A. Fix the stake floor vs yes_cap mismatch
**Mechanism**: yes_cap = $1.25 < min YES stake = $2.10. Three levers:
- **Option A**: Raise BAND_STAKE_FRAC_YES: 0.010 → 0.020 → yes_cap = $2.50 (clears off=1 at $2.10; off=0 at $3.00 still tight but clears with 0.025)
- **Option B**: Lower BAND_NO_CASH_RESERVE: 0.50 → 0.20 → yes_cap = $2.00 (marginal, weakens NO protection)
- **Option C**: Lower BAND_BASE_STAKE: 3.0 → 2.0 → off=1 = $1.40 (fits even under current cap; but reduces absolute edge per fill)

Option A is the cleanest: doubles deployment rate without touching NO reserve logic or per-fill sizing.

**Expected delta**: posted/cycle 0.1 → 1.7 (+17×), turns/day 0.36 → ~1.0, fills ~$75/day → ~$200/day. Confidence: HIGH (mechanism fully confirmed by exec). Effort: trivial (one parameter).

### 2B. NO posting rate broken despite reserve being held
**Finding** (exec §2-3): BAND_NO_CASH_RESERVE=0.50 is holding $125 idle, but only 2 fire_no events fired Jun 13. Root cause: books=0/80 means NO candidates never reach the book-fetch stage. Fixing 2A (book fetches resume) should unblock NO simultaneously — no separate parameter needed.

**Expected delta**: NO posts proportionally recover. Jun 11 post-fix rate was ~20.6% NO of posts (exec §2), implying ~35/day NO posts if the pipeline clears. Confidence: MEDIUM (inferred, not directly confirmed for NO path). Effort: zero additional beyond 2A.

### 2C. RECYCLE099 dependency risk
**Finding** (pnl_ledger §5): Jun 12 net +$12.85 = RECYCLE099 (+$37.52) − STWA legacy bleed (−$28.33). Without RECYCLE099, Jun 12 = −$24.67. The band's active contribution was negative.

RECYCLE099 draws from legacy taker positions (STWA_REGULAR_YES_ENABLED disabled Jun 5) now resolving. Once this pool clears, the revenue buffer disappears. At current 0.1 posts/cycle, new fills entering the RECYCLE099 pipeline are negligible (~$0.60/day of future pipeline value vs $37/day being extracted). The pool is in net drawdown. Fixing 2A replenishes the pipeline; doing nothing leaves a closing revenue window.

**Expected delta**: restoring YES posting fills the RECYCLE099 pipeline at scale. No immediate parameter action needed beyond 2A.

### 2D. Dead-quote reclaim not executing
**Finding** (exec §5): Seattle NO @0.56 and Seoul NO @0.63 are 28h old, 0% filled, past the 6h reclaim threshold (BAND_RECLAIM_AGE_S=6h). BAND_RECLAIM_PER_CYCLE=10 is set but "No active reaping observed." Small dollar impact (~$10 locked) but confirms the reclaim sweep is not running or failing silently.

**Expected delta**: unlock ~$10 resting capital, reduce stale-quote book pollution. Confidence: HIGH. Effort: investigate + fix (low).

---

## 3. GATE PIPELINE REVIEW

**Master blocker**: Gamma API returns HTTP 403 from VPS (Cloudflare WAF). Zero resolution joins computed. All ROI/WR/CI metrics N/A across all 7 gates. No gate can reach READY/REJECTED until resolution access is restored.

### Gate proximity ranking:

| Gate | n (count) | Count threshold | Bottleneck | ETA to READY |
|---|---|---|---|---|
| G1 BAND_YES per slice | 1,539 (4 slices >100) | ✓ passed | **Gamma 403** | Immediate if unblocked |
| G7 SUM-POSTED 0.70-0.85 | 284 | ✓ passed | **Gamma 403** | Immediate if unblocked |
| G3 FILLED vs FIRED | 116 fills | ✓ passed (n≥40) | **Gamma 403** | Immediate if unblocked |
| G5 THERMO maker-NO | 13 candidates | n≥20 resolved | ~1-2d accumulation + Gamma | 2d |
| G4 BASKET EXIT | 38 basket-days | n≥100 | Time only | ~3d |
| G2 BAND_NO | 14 post-fix | n≥100 | Time (~7/day) + Gamma | ~12d |
| G6 M1 LOCKOUT | 1 | n≥100 | **Logger silent (0 rows)** | Indeterminate |

G1, G7, and G3 are count-complete. They are waiting only for resolution data — one working Gamma call or Polygon RPC query unlocks all three simultaneously.

**G6 (M1-beta lockout)**: metar_lockout.jsonl has 0 rows across all dates (gatekeeper §6). One WEATHER_M1_PROBE trade exists (Moscow 2026-05-26). Logger is either disabled or the thin-margin slice never triggers. Check `METAR_LOCKOUT_SHADOW_ENABLED` flag — without the logger, G6 is stuck at n=1 indefinitely.

**Accelerating G2 without degrading expectancy**: NO posting rate (7/day) is a downstream symptom of the YES posting freeze. Fixing the YES cap (2A) unblocks book fetches → NO candidates processed → fire_no triggers → G2 accumulates at ~15-25/day (Jun 11 post-fix rate). No breadth changes or stake modifications needed for G2.

---

## 4. ASSUMPTION ATTACK

### Assumption 1: Dispersion premium persists (market-implied sigma > realized sigma)
**Status: UNDER STRESS ⚠️**

Calib §3 dispersion gauge fires RED: 7d median corrected ratio = **0.62** (threshold 1.10). Market-implied sigma is narrower than realized displacement in 73/149 non-exact-mode city-days. The CLAUDE.md edge claim is not confirmed this window.

Day-level trend is the decisive nuance:

| Date | Corrected ratio |
|---|---|
| Jun 8 | 0.458 |
| Jun 9 | 0.409 |
| Jun 10 | 0.781 |
| Jun 11 | 0.842 |
| Jun 12 | 0.857 |

Jun 8-9 collapsed to 0.41-0.46 and dominate the 7d median. Jun 10-12 recovered to 0.78-0.86. If the ratio holds at this level, the 7d window will clear 1.10 in approximately 5-7 days as the early-window outliers roll off. This is not a reason to declare edge restored — it is a reason to monitor carefully rather than halt.

**Data quality caveat** (calib §3): p_cal is used as a market-price proxy for historical days (stwa_ladder_book not archived). The isotonic plateau artificially compresses p_cal at high model confidence, narrowing computed implied sigma. True market-implied sigma is likely wider — but cannot be confirmed without the 7d archive (experiment B). The 0.62 reading may be a floor estimate.

**Verdict**: Assumption under stress. Do not halt. Do not expand. Watch daily ratio. Halt trigger: ratio stays below 0.70 through Jun 17, or falls from current 0.857 level.

### Assumption 2: Fills are not adversely selected (winner's curse below detection threshold)
**Status: CANNOT EVALUATE**

Exec §4 proxy signals: 27 exit099 wins, ~10 inferred losses, no all-fires baseline (band_resolution_join.py absent, Gamma 403). Calib settled lane: mode bucket [0.6, 0.7) wins 100% (n=160, decision-grade) — model has real predictive signal. Cheapest YES legs (0.10-0.30) show 453% ROI when they win (n=6, collect-grade only).

Winner's curse test requires: fill ROI per slice vs all-fires ROI per slice. Neither is computable without resolution. G3 (FILLED vs FIRED) tests this directly. Unblocking Gamma is the only path to answer.

**Verdict**: No signal of adverse selection detected; absence of detection is not evidence of absence. Gate G3 carries this test.

### Assumption 3: Recycle velocity scales with fill rate
**Status: THREATENED ⚠️**

RECYCLE099 generated $91.05 in 4 days (27 win events). Jun 12 RECYCLE099 alone = $37.52 on a day when the active band contributed −$24.67 net. The revenue is from a draining legacy stock, not a renewable source. New fill pipeline at 0.1 posts/cycle ≈ 2-3 positions/day ≈ ~$0.60/day of future pipeline value. Current extraction rate ~$37/day. Net drawdown ratio: ~60×.

**Verdict**: Assumption is false at current posting rate. The engine does not scale — it depletes. The recycle velocity assumption requires YES posting at adequate scale (fix 2A) to be true.

---

## 5. MARKET INTELLIGENCE — [Rotation 1: Market Census]

*Day-of-month mod 3 = 13 mod 3 = 1 → market census.*

**Proxy lane divergence leaders today** (calib §2, n=1,888 active buckets, 08:03 UTC):

| City | Median |p_cal − mkt_mid| |
|---|---|
| Lucknow | 0.305 |
| Qingdao | 0.271 |
| Jeddah | 0.262 |
| Helsinki | 0.262 |
| Madrid | 0.236 |

Exec report top fill cities (4d): Jeddah (9 fills), SF (8), Beijing (8), Munich (7), Moscow (7).

**Overlap signal**: Jeddah appears in both high-divergence and high-fill-rate lists. Qingdao is high-divergence but not a top-fill city in this window (6 fills, rank 7). This suggests the band is correctly targeting Jeddah; Qingdao may be an underfished city if its divergence is genuine. Lucknow tops the divergence list (0.305) but does not appear in fill leaders — worth checking if it is in the active 51 or filtered by a config parameter.

**stwa_ladder_book baseline gap**: The calib report notes the proxy lane has no 7d baseline because stwa_ladder_book is not archived per-day in data-mirror. Divergence spikes cannot be distinguished from persistent structural gaps without this baseline. This is a new gap (first calib run). Archiving daily is experiment B below.

**Gamma census blocked**: No Gamma market API access from VPS (403). New weather city/product additions in the 51-city universe cannot be confirmed via API this session. Manual check on gamma.com recommended to confirm no new market categories have launched this week.

---

## 6. EXPERIMENTS

### Experiment A — Restore YES posting via BAND_STAKE_FRAC_YES increase

**Hypothesis**: Raising BAND_STAKE_FRAC_YES from 0.010 to 0.020 raises yes_cap from $1.25 to $2.50, clearing the off=1 stake floor ($2.10) and restoring posted/cycle from 0.1 to Jun 12 baseline of ~1.7.

**Data**: STRUCT-BAND-Q yes_resv_skip and posted/cycle in the next 1-2 cycles (5-10 min); fills/day over Jun 14.

**Time**: 5 min to see posting resume; 24h to confirm fills/day trend.

**Cost**: Zero. Capital at risk per cycle scales proportionally (same fraction of equity, twice deployed).

**Success metric**: yes_resv_skip < 10/cycle; posted/cycle > 1.0; Jun 14 fills > $100.

**Decision if YES**: confirm as operational parameter. **If NO** (posting resumes but adverse selection detected or fill quality degrades): revert and investigate fill composition by price band.

---

### Experiment B — Archive stwa_ladder_book daily for dispersion gauge

**Hypothesis**: Daily archiving of stwa_ladder_book.jsonl in data-mirror enables the proxy lane 7d baseline in calib_monitor, replacing the p_cal proxy and 1.06 point-estimate correction with true market-implied prices. May reveal the true dispersion ratio already exceeds 1.10 (calib §3 notes the p_cal compression likely understates market sigma).

**Data**: 7 daily snapshots of stwa_ladder_book captured at 12:00 UTC.

**Time**: 7 days to accumulate baseline; 1-2h to implement archive cron.

**Cost**: ~50MB/day storage, one cron entry.

**Success metric**: calib_monitor proxy lane has 7d baseline; dispersion ratio recomputed with true market_sigma. If ratio rises above 1.10 → alert clears. If ratio stays below 0.70 → edge assumption is genuinely broken.

**Decision if YES** (ratio > 1.10): edge confirmed, proceed with fill rate expansion and capital scaling. **If NO** (ratio < 0.70 even with true prices): reduce YES band exposure, revisit BAND_EV_MIN and BAND_P_MIN floors.

---

### Experiment C — Unblock Gamma resolution API via Polygon RPC fallback

**Hypothesis**: Market outcome prices are available on-chain via Polygon RPC (final outcome price per token = 0 or 1 after resolution). Implementing a Polygon RPC query path in band_resolution_join.py bypasses the Cloudflare 403 on Gamma REST API and provides resolution truth for G1, G3, G7 — all of which are n-complete.

**Data**: Outcome prices for Jun 8-12 condition IDs in G1/G3/G7.

**Time**: 2-4h dev to implement Polygon price query. Immediate results once running.

**Cost**: Low (RPC calls, negligible gas).

**Success metric**: band_resolution_join.py returns > 0 resolved outcomes for Jun 8-12 markets; G1 and G7 produce ROI/CI values and flip READY or REJECTED; G3 produces fill vs fire divergence.

**Decision if YES**: G1/G7 gate decisions within 24h. **If NO** (Polygon also fails or mismatches): defer to manual Gamma check via non-VPS IP or curl_cffi impersonation debug.

---

## 7. SINGLE BEST ACTION

**Raise BAND_STAKE_FRAC_YES from 0.010 to 0.020 in strategy/stwa_engine.py.**

**Evidence chain** (exec_audit §3, primary report):
- yes_cap = 0.010 × $250 × 0.50 = **$1.25/cycle** < min YES stake = **$2.10** → all YES candidates mechanically rejected
- posted/cycle declined 17× in one day: 1.7 (Jun 12) → 0.1 (Jun 13)
- yes_resv_skip = 58/cycle at 07:09 UTC confirms the entire YES pool is rejected at the stake floor
- Burst at 10:11 UTC (posted=2 in one cycle when yes_cap transiently reached $3.47) confirms the engine executes correctly when the cap is met

**Compounding impact**: restoring posted/cycle to 1.7 → turns/day 0.36 → ~1.0 → 2.7× compounding acceleration with no strategy or edge change. The fix is parameter-level; the risk is bounded by the same BAND_EV_MIN, BAND_PX_CEIL, BAND_P_MIN gates already in place.

**P(success)**: HIGH. Mechanism fully confirmed, not inferred.

**Effort**: one parameter change, one config line.

**Cascading benefits**: book fetches resume → NO candidates also unblocked → G2 accumulation accelerates from 7/day to ~15-25/day → RECYCLE099 pipeline refilled by new maker fills → G3/G1 fill count grows for gate validation.

**Dispersion caveat**: the dispersion ratio alert fires (0.62 vs threshold 1.10), but Jun 10-12 trend shows recovery (0.78-0.86). Restoring fill rate is correct regardless because: (a) each fill generates data the gates need; (b) the posting freeze is the larger drag on expected value; (c) the band's gate logic (EV_MIN, PX_CEIL, P_MIN) provides downside protection even if the dispersion premium is temporarily compressed.

**Concrete first step**: In `strategy/stwa_engine.py`, change `BAND_STAKE_FRAC_YES = 0.010` to `BAND_STAKE_FRAC_YES = 0.020`. Monitor STRUCT-BAND-Q in the next cycle (5 min) for yes_resv_skip < 10 and posted > 0.

---

## PROPOSED ACTIONS (human review)

**P1** [HIGH — operational fix]: Raise `BAND_STAKE_FRAC_YES` from `0.010` to `0.020` in `strategy/stwa_engine.py`. Monitor yes_resv_skip + posted/cycle next cycle.

**P2** [MEDIUM — data infra]: Add stwa_ladder_book daily archive to data-mirror cron (one snapshot/day at 12:00 UTC). Unlocks proxy lane 7d baseline in calib_monitor.

**P3** [MEDIUM — gate unblock]: Implement Polygon RPC fallback in band_resolution_join.py (or enable curl_cffi Chrome impersonation for Gamma from VPS). G1, G7, G3 are n-complete; resolution data is the only missing piece.

**P4** [LOW — maintenance]: Check `METAR_LOCKOUT_SHADOW_ENABLED` flag. metar_lockout.jsonl has 0 rows across all dates; G6 cannot accumulate data until the logger fires.

**P5** [LOW — maintenance]: Investigate reclaim sweep for Seattle NO @0.56 and Seoul NO @0.63 (28h old, 0% filled, past 6h reclaim threshold). Both should have been swept 22h ago.

**P6** [WATCH — no action yet]: Dispersion gauge ratio = 0.62 (alert), trend recovering (0.857 on Jun 12). Hold YES band live. Halt trigger if ratio falls below 0.70 or stays below 0.80 through Jun 17.

**P7** [WATCH — do not deploy]: Isotonic candidate top-knot collapse (p=1.00 → p_cal 0.63→0.37, Δ=−0.258) contradicts settled lane (mode bucket wins 100% at p_cal ∈ [0.6,0.7), n=160). Human review required before any deployment.

---

*Report-only. No code, flags, or stakes touched.*  
*Generated by Klaus Research Agent | 2026-06-13T10:30Z*
