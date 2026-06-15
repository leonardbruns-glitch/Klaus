# Gate-Keeper Validation Report — 2026-06-15T10:35Z

**Snapshot age**: 16 min (2026-06-15T10:19:26Z) — VALID  
**System**: `klaus systemd: active` (uptime since 2026-06-15 05:52 UTC)  
**Capital**: $270.83  
**Prior run**: 2026-06-14T10:23:00Z  

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|------|---|------|----|-----|------|--------|-----------------|
| BAND_YES (all slices) | 1381‡ | +233 | — | +8.6%† | unverified† | COLLECTING | N/A (CI unverified) |
| BAND_NO + PAIR_FAV | ~37 | ~+13 | — | −1.2%† | unverified† | COLLECTING | ~5d (~Jun 20) |
| FILLED_VS_FIRED | 142 | +20 | — | — | — | COLLECTING | n>40 ✓ CI blocked |
| BASKET_EXIT | ~74★ | ~+18 | — | — | — | COLLECTING★ | ETA void (scope change) |
| THERMO_MAKER_NO | ~23 | +4 | — | — | — | COLLECTING | kill gate ~3-5d |
| M1_BETA_LOCKOUT | 1 | 0 | — | — | — | COLLECTING | dormant |
| SUM_POSTED_0.70–0.85 | 917 | +135 | — | — | — | COLLECTING | N/A (resolution blocked) |

†ROI figures are from `band_resolution_join.py` run on the Klaus VPS on 2026-06-14 (after prior gatekeeper run). These are **first-ever resolution outcomes** for the band system. CI95 cannot be computed from this container (no per-leg distribution data).

‡BAND_YES n=1381 uses **per-cid strict first-fire dedup** (this run's confirmed count via band_struct_lite). Prior run's n=2116 used per-(cid, days_out) dedup, which counts the same market twice when it appears in d+2 and d+1 on consecutive days. The per-(cid, days_out) equivalent estimate is ~2540 (1381 × 1.84×). All live slices remain well above n=100 on both methodologies.

★BASKET_EXIT structural scope change: logger now covers 22 cities, generating 5,322 unique (city,t_close) windows on Jun 15 alone. Prior n=56 was based on a narrower definition. "~74" uses the old per-day aggregate metric for continuity; under the new scope, n>>100 today but the metric (cash-out vs hold) remains uncomputable. Gate 4 definition needs a refresh by human.

---

## State Transitions vs Prior

**No gate transitions this run.** All gates carry forward COLLECTING.

**The blocker is no longer Gamma-only.** As of 2026-06-14, `band_resolution_join.py` RAN SUCCESSFULLY from the Klaus VPS and produced:
- **YES legs**: ROI **+8.6%** (n=1915 resolved)
- **NO legs**: ROI **−1.2%** (n=109 resolved; cited as "breakeven" in state_log)

This evidence was used by the human to justify `BAND_NO_CASH_RESERVE 0.50→0.0` (Tier-2 commit `9caaf67a`). However, **the gatekeeper's pre-registered CI rule requires CI_lower > 0**, and per-leg data needed to compute CI was not pushed to `data-mirror`. The state_log headline ROI is NOT sufficient for READY — that shortcut is explicitly prohibited by anti-sycophancy rules. Action required: push per-leg join output to `data-mirror` so CI can be computed here.

---

## Per-Gate Detail

### GATE 1 — BAND_YES  *(scale-up gate; state_log 2026-06-11)*

**Method**: first-fire dedup per cid from `band_struct_lite.jsonl` (fire records, quotes[] array).  
Confirmed count (Jun 10–15): **1,381 unique cid first-fires**.

| Date (first appearance) | New cids | Cumulative |
|---|---|---|
| Jun 10 | 113 | 113 |
| Jun 11 | 218 | 331 |
| Jun 12 | 293 | 624 |
| Jun 13 | 267 | 891 |
| Jun 14 | 257 | 1,148 |
| Jun 15 (partial, 70%) | 233 | **1,381** |

**Methodology note**: Prior run (n=2116) used per-(cid, days_out) dedup, which counts the same market in multiple days_out slices (d+2 on day 1, d+1 on day 2 = 2 entries). Per-cid strict dedup (this run) = 1,148 through Jun 14 vs prior 2116. The per-(cid, days_out) equivalent estimated today: ~2,540. All live slices (d≤2, off≤1) remain well above n=100 on both methodologies.

**All live-posted slices (d≤2, off≤1) remain above n=100 threshold.** Prior per-slice breakdown:

| days_out | offset | n (as of Jun 14) | ≥100? |
|----------|--------|------|-------|
| 0 | 0 | 150 | ✓ |
| 0 | 1 | 261 | ✓ |
| 1 | 0 | 175 | ✓ |
| 1 | 1 | 329 | ✓ |
| 2 | 0 | 205 | ✓ |
| 2 | 1 | 362 | ✓ |

**Resolution data (NEW)**: `band_resolution_join.py` ran from VPS 2026-06-14:  
- YES ROI = **+8.6%** (n=1915 resolved legs)  
- CI95 = **uncomputed** — per-leg data required. Estimated CI95 at avg_entry=0.25: [+1%, +16%] (borderline positive); at avg_entry=0.20: [−0.2%, +17.4%] (straddles zero).  
- The CI is sensitive to assumed avg entry price. **Cannot certify CI_lower > 0 from this container.**

**Parameter changes since prior run:**
- `BAND_BASE_STAKE 3→1` (Jun 15 05:51 UTC) — YES now posted at CLOB minimum ($1 / 5 shares / $0.20/leg)
- `BAND_STAKE_FRAC_YES 0.010→0.005` — per-leg cap halved
- Effect: YES posting breadth sharply increased; accumulation rate should rise above 443/day

**+24h**: +233 confirmed new cids on Jun 15 (partial day, 70% complete; extrapolated ~333/day) | **Prior rate**: ~443/day per-(cid,days_out); ~257 new per-cid/day (Jun 14). Jun 15 stub (~233 in 10.3h) implies ~550/day new cids — consistent with stake change increasing breadth.  
**Status**: COLLECTING — n >> threshold (all slices); first resolution data exists from VPS; CI unverified from container.  
**ETA to READY/REJECTED**: N/A — requires per-leg CI computation from VPS, not more n.

---

### GATE 2 — BAND_NO + PAIR_FAV  *(threshold n=100, counting from 2026-06-12 13:05 UTC)*

**NO legs (post-fix)**:
- Prior n=24 (Jun 12: 3, Jun 13: 14, Jun 14: 7)
- Estimated +13 since prior (rate 12.6/day × 1 day)
- **Estimated n ≈ 37**
- `maker_fills_recent.log`: 40 unique NO CIDs filled (Jun 12–15); fire count is higher than fill count

**PAIR_FAV legs**: **0** confirmed — trades.jsonl shows WEATHER_FAVYES is all pre-fix (last Jun 04); shadow `pair_fav` reason records = 0. PAIR-SHADOW logger added Jun 15 05:37 to measure co-fill rate; co-fill at 3.3% (far below badatmath's ~47%): the PAIR pathway is structurally limited for our fills.

**Resolution data (NEW from VPS join)**: NO ROI = **−1.2%** (n=109 total, includes pre-fix). Pre-fix data may be biased by NO-starvation. Post-fix–only subset (n≈37 out of 109) would have different ROI; cannot isolate from the VPS summary.

**Rate**: ~12.6/day (unchanged; NO cash reserve 0.50→0.0 may increase YES breadth but NO governed separately by BAND_NO_STAKE=$4.5 + daily cap)  
**+24h**: ~+13 estimated  
**ETA**: (100−37)/12.6 = **~5.0 days → ~Jun 20**  
**Status**: COLLECTING.

---

### GATE 3 — FILLED_VS_FIRED  *(watch threshold n=40 filled)*

From `maker_fills_recent.log` (Jun 12–15 rolling 7-day window):

| Metric | Value |
|--------|-------|
| MAKER-FILL events total | **244** |
| Unique CIDs (gate n) | **142** (+20 vs prior 122) |
| Unique YES CIDs | 105 |
| Unique NO CIDs | 40 |
| Date range | Jun 12 – Jun 15 10:16 UTC |
| Jun 15 new CIDs (today) | 21 |

Note: Jun 11 CIDs have rolled off the 7d window (prior run: "Jun 11 10:39" was oldest). Net +20 = +21 new today −1 rolled off.

**Operational context from STRUCT-BAND-Q (810 log lines today)**:
- 132/810 cycles posted YES > 0 (16.3% posting rate)
- `yes_resv_skip=0` in all recent lines — reserve eliminated (BAND_NO_CASH_RESERVE=0.0 in effect)
- `yes_cap` still hits 0.00 in most cycles; one cycle at 4.65 posted 4 YES
- 760 total YES legs posted across all cycles since midnight today

**+24h**: +20 unique CIDs  
**Watch threshold (n≥40)**: MET — winner's-curse divergence metric watch active.  
**Winner's-curse metric**: uncomputable (Gamma 403 from container; filled-leg vs all-fires ROI comparison requires resolution flags).  
**Bias note**: `exit099_live.jsonl` shows 5 RECYCLE099 exits today (entries 0.57–0.65, exit 0.99, PnL $2.44–$3.36 each). These are winning legs exiting at 0.99 — not captured as fills in maker_fills_recent but represent the winning-side of the fill cohort.  
**Status**: COLLECTING.

---

### GATE 4 — BASKET_EXIT  *(threshold n=100 basket-days)*

**STRUCTURAL SCOPE CHANGE** since prior run (noted for human review):

Prior `basket_exit_shadow.jsonl` (logger started Jun 12 06:14) tracked a small city set, accumulating ~18 basket-days/day → prior n=56 as of yesterday.

Today's hot file covers **only Jun 15** (resets daily) and shows:
- **5,351 rows** (one row per city scan event, every ~2 min)
- **5,322 unique (city, t_close)** pairs = dramatically expanded scope: 22 cities, multiple t_close windows per city
- **339 baskets resolved** (t_close < 10:18 UTC): all 339 had all_green=False when they closed
- **1,172 baskets currently all_green** (all have future t_close — windows still open)
- **0 resolved AND all_green** (too early in the day)

"~74" in the ledger table uses the old per-day aggregate metric for continuity (56 + 18 × 1d). Under the new scope, today alone generated 5,322 unique baskets, far exceeding n=100 on a single day. The gate definition needs refreshing to reflect the expanded city coverage.

**Cash-out metric** (cash-out value vs hold for all_green resolved baskets): **uncomputable** regardless of n — requires Gamma winner flags to determine held-leg outcomes.

**+24h**: ~+18 (estimated, old metric) | **Rate**: ~18/day (old) or ~5,000+/day (new scope)  
**Status**: COLLECTING (metric uncomputable; gate definition stale under expanded scope).

---

### GATE 5 — THERMO_MAKER_NO  *(pre-registered kill gate: first 20 resolved; state_log 2026-06-11 22:40)*

From `thermo_maker.jsonl` (hot file, resets daily — today's scan covers 2026-06-15):

- **10,430 rows** (21 cities, ~948 rows/hr since midnight)
- **4 past-resolution token_ids** (end_date = 2026-06-14): Dallas, Los Angeles, San Francisco, Toronto
- **64 active token_ids** for today (end_date = 2026-06-15)
- Prior n=19 candidates past resolution + 4 new Jun 14 = **~23 candidates past resolution date**

**Kill gate accounting**: The gate counts **placed-and-resolved NO bets**, not monitored candidates.
- Est. placed bets since Jun 11 22:40: ≤ 3/day × 3.5 days = ≤ **12–15 placed**
- Of those, Jun 13 and Jun 14 bets would now be past resolution date → some could be resolved
- Actual resolved: **unknown** (Gamma 403 blocks join; no winner field in thermo_maker.jsonl)
- Kill threshold = **20 resolved bets**; placed ≤ 15, resolved ≤ placed

**+24h**: +4 candidates past resolution | **Kill gate ETA**: ~1-2 calendar days of additional placement + resolution lag  
**Status**: COLLECTING — approaching but not yet at kill gate.

---

### GATE 6 — M1_BETA_LOCKOUT  *(threshold n=100 lockout trades)*

- **n = 1** (unchanged — 1 WEATHER_M1_PROBE trade, Moscow, net_pnl=−$1.65)
- `metar_lockout.jsonl`: absent from all 6 dated shadow directories
- `metar_min_lockout.jsonl` (15,771 rows hot file, 7 cities) is the **minimum temperature** lockout logger — distinct gate, margin_c ≥ 0.5°C throughout; zero M1-beta [0.2, 0.5)°C entries
- Strategy dormant: thin-margin [0.2, 0.5)°C weather market slice not accumulating

**+24h**: 0 | **Status**: COLLECTING — dormant.

---

### GATE 7 — SUM_POSTED_0.70–0.85  *(threshold n=100; V3 gate extension)*

Confirmed count (Jun 10–15): **917 unique first-fires with sum_posted ∈ [0.70, 0.85]**.

| Date (first appearance) | New sum_posted∈[0.70,0.85] | Cumulative |
|---|---|---|
| Jun 10 | 0 (no sum_posted field in 06-10 schema) | 0 |
| Jun 11 | 116 | 116 |
| Jun 12 | 223 | 339 |
| Jun 13 | 209 | 548 |
| Jun 14 | 234 | 782 |
| Jun 15 (partial, 70%) | 135 | **917** |

Jun 14 cumulative = 782 vs prior n=761 (+21 difference: Jun 9 not in current 6-day window). Methodology confirmed consistent with prior run.

**Resolution**: Same block as Gate 1. VPS join aggregate YES ROI +8.6% (n=1915) did not report sum_posted=0.70–0.85 slice breakdown.

**+24h**: +135 confirmed (Jun 15 partial) | **Rate**: Jun 14 had 234 new; Jun 15 on-pace ~193/day (135/0.70)  
**Status**: COLLECTING — n >> threshold; resolution blocked from container.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.** All 7 gates remain COLLECTING.

### ⚡ HIGH PRIORITY: per-leg join output needed on data-mirror

The VPS ran `band_resolution_join.py` on 2026-06-14 and produced YES ROI +8.6% (n=1915), NO ROI −1.2% (n=109). This is the first-ever resolution data for the band system. However:

- The headline ROI was used to justify `BAND_NO_CASH_RESERVE 0.50→0.0` (human decision, Tier-2)
- The **gatekeeper cannot formally advance Gates 1 or 7 to READY without CI95 > 0**
- CI95 requires the per-leg distribution (entry prices + outcomes), not just aggregate ROI
- At typical band entry prices (~0.20–0.30), estimated CI95 ranges from [−0.2%, +17.4%] (ambiguous) to [+1%, +16%] (barely positive). The answer changes the verdict.

**Requested action**: From the VPS, run:
```bash
python3 analysis/weather/band_resolution_join.py --output /tmp/band_join_output.jsonl
```
and push the per-leg output to `data-mirror` (or include mean/std/n per-leg in the join's printed output). This is the single action that unlocks Gates 1, 7 and provides post-fix NO data for Gate 2.

### Gate 4 (BASKET_EXIT) definition needs refresh

The logger scope has expanded dramatically (22 cities vs prior small set). The "n=100 basket-days" threshold was set under the old definition. Recommend the human clarify:
1. What is the canonical "basket-day" unit now? (unique city/t_close pair? unique city/date? other?)
2. Should the metric be computed on all all_green baskets or a quality-filtered subset?

Until this is clarified, Gate 4 is frozen at COLLECTING regardless of basket count.

### Gate 5 (THERMO_MAKER_NO) approaching kill gate

Estimated 12–15 bets placed; resolution lag ~24h. Kill gate (20 resolved) will likely be triggered within 3–5 calendar days if the current rate continues. Once 20 resolved, a YES/REJECT verdict from the VPS join is needed before the gate can transition.

---

## Operational Notes (not gate transitions)

**1. YES breadth surge from Jun 15 05:51 stake change**  
`BAND_BASE_STAKE 3→1` + `BAND_STAKE_FRAC_YES 0.010→0.005` should increase per-cycle YES posting breadth. STRUCT-BAND-Q shows `yes_resv_skip=0` (reserve eliminated), but `yes_cap=0.00` in most cycles suggests resting bids still consume available YES capital quickly. Today's rate: ~91 YES legs/day (39 tokens by 10:19, partial day), up from ~50/day implied by prior band_posted_state cadence.

**2. KILL SWITCH STALE** *(Tier-3 action required by human)*  
`daily_start_capital=$15.95` vs capital $270.83 → loss halt fires only at $5.95, which is ~$265 below current capital. This is a Tier-3 item (kill-switch parameter) — cannot be patched by this agent. **Capital is at risk without a functioning loss halt.**

**3. NO ROI −1.2% from VPS join: BREAKEVEN, not a gate decision**  
The join result (−1.2%, n=109) covers pre-fix + post-fix NO legs combined. Post-fix subset (n≈37) is isolated from the Jun 12 fix and represents the only fair evaluation window. With n=37 << 100, this is a trend, not a decision. Gate 2 remains COLLECTING.

**4. PAIR-SHADOW accumulation begins today**  
Logger added Jun 15 05:37. Will measure co-fill rate (real NO fill vs YES posted in same bucket). Current data: 18 pair_cands per cycle visible in STRUCT-BAND-Q. First useful signal expected at n≥100 co-fill events (~5–10 days at current fill rate).

---

## Appendix: entries.parquet CI Analysis (post-commit addendum)

`data/entries.parquet` (2.4 MB, 13,869 rows) was fetched and processed. **It is LDA kline strategy data from 2026-05-09 to 2026-05-15 — NOT band/weather resolution data.** The schema uses `rem_bucket` (seconds-to-expiry at entry), `binance_ret_5m_pct`, and LDA gate fields. It contains NO band-system fields (no `days_out`, no `sum_posted`, no `city`). The band_resolution_join.py output cited in state_log (+8.6% YES, n=1915) was computed on the VPS and used as verbal evidence in a Tier-2 commit — it was **not pushed to data-mirror in any machine-readable format**. Band gate CI remains unverifiable from this container.

### LDA CI findings (from entries.parquet — out of scope for band gates; flag for LDA auditor)

Statistically significant results (CI95 excludes zero, n≥100):

| Slice | n | mean_roi | CI95 | Verdict |
|---|---|---|---|---|
| YES ask=[0.65,0.75) | 383 | −10.0% | [−17.1%, −3.0%] | REJECT: confirmed losing band |
| NO ask=[0.10,0.20) | 601 | −22.2% | [−39.8%, −4.5%] | REJECT: cheap NO tokens lose |
| YES rem_bucket=B1b (~97-120s) | 826 | −16.3% | [−31.8%, −0.8%] | NEGATIVE: early entries underperform B1a |
| NO rem_bucket=B0b (~46s, inside guard) | 114 | −47.5% | [−57.2%, −37.9%] | STRONG REJECT: 60s no-trade guard validated |
| NO sum_ask≥1.05 (wide spread) | 401 | −26.1% | [−35.2%, −17.0%] | REJECT: wide-spread NO legs are traps |
| YES gate_all_pass | 418 | +2.5% | [−1.1%, +6.1%] | POSITIVE TREND — not yet significant (n=418, CI straddles 0) |

Aggregate (all resolved): YES n=6838, ROI=−3.3%, CI=[−10.6%, +4.0%] — straddles zero.  
Aggregate (all resolved): NO n=6841, ROI=+3.5%, CI=[−17.5%, +24.5%] — straddles zero.

**These findings apply to the LDA strategy (May 2026 era), not to the current band/weather system.** The LDA strategy auditor should act on the YES [0.65,0.75) and B1b findings as Tier-1 candidates (n≥100 per pre-registered LDA rule). This gatekeeper takes no action; reporting only.
