# Klaus Research Audit — 2026-06-12T11:27Z

**Snapshot**: 2026-06-12T11:27:09Z (fresh, 0.0h old) | Klaus: active (uptime 5.2h since 06:15 restart) | Capital: $225.67 | Trades.jsonl rows: 7,316

---

## DATA PRIMACY — Pre-Report Confirmation

**Live paths confirmed**: STWA_LIVE=True; NEG_RISK_ARB (always on) + engine model-NO (STWA_REGULAR_NO_ENABLED=True) + M1β lockout-NO + BAND pair-quoter (BAND_LIVE=True, since June 11 max-extraction package).

**Config epoch**: YES disabled 2026-06-05; engine model-NO re-enabled 2026-06-05; BAND pair-quoter deployed live 2026-06-11. Pre-June-5 weather trades (n=92 in trades.jsonl) are DEAD DATA—not cited in expectancy.

**Resolved WEATHER trades by config epoch**:

| Epoch | n | WR | Net PnL | Dead? |
|---|---|---|---|---|
| Pre-2026-06-05 (old config: YES ladder) | 92 | 5.4% | -$31.39 | **YES — dead data** |
| 2026-06-05 to 2026-06-12 (current config) | 39 | 17.9% | -$55.05 | **ACTIVE — analyzed below** |

**Open positions (basket_exit_shadow)**: 12 cities, 15 legs, cost $38.68, liquidation value $29.49 (-23.8%), max-hold $143.78. Close windows: Jun 12 15:59 UTC and Jun 13 07:59 UTC.

**Kill switch check**: WR=17.9% over 39 post-June5 resolved trades. **FLAG THRESHOLD BREACHED** (flag if <35% over 20 trades). Capital $225.67 >> ruin floor ($50). No daily halt triggered today.

---

## POST-JUNE-5 RESOLVED STWA TRADES BY PATH

| Path | n | Direction | WR | Net PnL | Stake | EV/$ | Decision tier |
|---|---|---|---|---|---|---|---|
| WEATHER_STWA (engine model-NO) | 14 NO + 6 YES* | BUY_NO: 14 | 14.3% NO | -$39.16 | $49.16 | **-$0.797** | Trend only (n<100) |
| WEATHER_STRUCT_BAND | 11 | YES: 8, NO: 3 | 18.2% | -$18.16 | $28.02 | **-$0.648** | Trend only (n<100) |
| WEATHER_M1_PROBE (M1β lockout) | 5 | BUY_NO: 5 | 40.0% | +$12.66 | $42.84 | **+$0.295** | Trend only (n<100) |
| WEATHER_THERMO (thermo-ceiling maker) | 2 | BUY_NO: 2 | 50.0% | -$5.56 | $11.06 | -$0.503 | Data-collection |
| WEATHER_FAVYES | 1 | BUY_YES | 0.0% | -$4.82 | $4.82 | -$1.000 | Single data point |

*6 BUY_YES WEATHER_STWA on June 5 opened before YES flag fully propagated—not a current-config path.

**Critical pattern on engine model-NO (n=14 NO trades)**:
- Entry prices concentrated at 0.50–0.56 (buying the "NO is favorable" side at PRICE_FLOOR gate)
- 12/14 resolved YES (bucket WAS the daily max) → WR=14.3% on NO
- Expected WR under random NO selection across weather buckets: ~70–80% (most buckets are not the daily max)
- 14.3% WR is **5× worse than random**, indicating the model is **anti-predictive**: it consistently selects the bucket that becomes the daily high, then bets it won't be

**BAND pair-quoter (n=11, post-June-9)**:
- 8 BUY_YES all resolved 0.0 (0% YES WR)
- 1 BAND_MERGE win +$0.27 (Taipei YES+NO pair → merged → $1)
- 2 BUY_NO: 1 win (+$2.30), 1 loss (-$3.05)
- Merge rate: 1/11 = 9% (vs badatmath's 34% in June); net: -$18.16 on $28.02 staked

---

## 1 — PRIMARY BOTTLENECK

**Engine model-NO calibration failure (anti-predictive bucket selection)**

Rank: **model calibration / direction signal quality**

The PA-shrunk isotonic recalibration showed rank-corr +0.39 on 2024 backtest data. Live NO trades (n=14, June 5–8) show WR=14.3%—not merely unedged but reversed. The model selects buckets that are 5–6× more likely to be the daily high than a random bucket, then bets NO on them. Every dollar staked on this path destroys $0.80.

WEATHER_STWA is responsible for -$39.16 of the -$55.05 total post-June5 loss (71%). It is the most active path by capital deployed ($49.16) and has the worst EV. The flag threshold is breached (WR=17.9% overall, 14.3% on this path). The recalibration did NOT transfer to live 2026 data.

Second bottleneck: BAND merge rate (9% vs 34% target), but capital exposure is smaller.

---

## 2 — EXISTING SYSTEM OPTIMIZATION

### 2a. Engine model-NO: disable until direction signal is validated
- **Issue**: All 14 NO entries at 0.50–0.56, losing 86% of the time. 14.3% WR is 5× worse than random NO selection.
- **Δtrade-count if disabled**: −~1.8/day (current pace)
- **Δexpectancy**: +$39.16 saved over this 8-day window; +~$1,400/yr at current pace
- **Confidence**: HIGH (n=14, consistent, worse than random)
- **Effort**: LOW (STWA_REGULAR_NO_ENABLED=False, one flag)

### 2b. BAND Σ-gate: verify v3 basket fix is working
- **Issue**: Today's band_struct last record: reason="no_band", n_valid=0 at 11:26 UTC. June 11 v3 deployed Σ-gate fix (gate on Σ(posted legs, off≤1) instead of full ±2 band). But today's data shows near-zero firing.
- **Possible causes**: (a) Markets not yet at tradeable phase (PRE_PEAK, too early); (b) Σ(posted legs) still exceeds 0.85 for available ladders; (c) d+1/d+2 days don't have tradeable depth yet
- **Δtrade-count**: Unknown without parsing full band_struct; estimate 2–5× if gate is confirmed broken
- **Δexpectancy**: +$200–$600/yr if BAND ROI stays near simulated +46%
- **Confidence**: LOW (n=22 simulated gated slice, n=11 live)
- **Effort**: LOW (diagnostic: parse band_struct "fire" vs "gate" ratio)

### 2c. BAND YES: 0.03 price floor (PX_MIN_MD) not yet producing live data
- **Issue**: Deployed June 11. All 8 BAND YES fills at 0.10–0.33 predate this change. Sub-0.10 YES fills have not resolved yet.
- **Expected Δtrade-count**: +~30% YES legs
- **Annual $**: Unknown until first sub-0.10 YES batch resolves
- **Confidence**: UNVALIDATED; accumulating
- **Effort**: ZERO (already deployed)

### 2d. NEG_RISK_ARB: partial-arb or threshold relaxation
- **Issue**: 0 real fills in 670 scans today. 48 scans have real_edge > 0.01 but all_legs_fillable=False. The Σask < 0.85 condition is met but not all legs have book depth.
- **Potential fix**: Accept partial arb coverage when Σ(fillable legs NO) is enough to guarantee profit with certainty (subset of legs already locked)
- **Annual $**: From $0 currently; +$150–$400/yr if partial coverage triggers ~2/day
- **Confidence**: LOW (adverse selection risk on partial fills)
- **Effort**: MEDIUM

---

## 3 — FREQUENCY EXPANSION

**Do NOT expand frequency on engine model-NO path. Frequency multiplies negative EV.**

| Opportunity | Δtrade-count | Δexpectancy | Annual $ | Confidence | Effort |
|---|---|---|---|---|---|
| Min-lockout live enable (currently shadow) | +~5 fills/day | ~+$0.15/fill (if similar to max lockout) | +$250/yr | MEDIUM (n=0 resolved; needs validation join) | LOW (flag flip after validation) |
| Expand THERMO maker daily cap after n≥20 resolve | +~2–3 fills/day | ~+4–7%/turn if ceiling math holds | +$100–$300/yr | LOW (n=2 resolved) | ZERO (already built; cap increase only) |
| Peakscalp (PROPOSAL — no live path yet) | +TBD | Backtest gate OOS ~95%+ WR | Unknown | MEDIUM (model-free, needs user GO) | MEDIUM |

---

## 4 — EXECUTION AUDIT

**NEG_RISK_ARB fill probability**: 0/670 scans today = 0.0%. Not a fill-side problem; arb doesn't exist in fillable form.

**BAND maker orders today**: 1 live resting order (Beijing NO at 0.99, THERMO path, status=RESTING). maker_exercise.jsonl n=1 for the day — very low posting activity at 11:26 UTC.

**BAND current open positions** (basket_exit_shadow snapshot 11:26 UTC):
- 12 cities, 15 legs, cost $38.68
- Current bid-side liquidation: $29.49 (-23.8% of cost)
- Max hold value: $143.78 (+271.7% of cost)
- 1/12 baskets all_green (Moscow, $0.47 cost, $2.47 max)
- Notable: Jeddah 2-leg basket, cost $5.34, max $52.48 (9.8× if both legs win)

**Observation pipeline**: 1,535 obs today from 9 sources (AWC 60%, WIS2 12%, NWS 10%, JMA/HKO/FMI ~4.5% each). No dropped messages in shadow telemetry (0 dropped / 966k written). Memory stable at 725 MB RSS. System operational.

**Entry fill timing**: All BAND fills appear to execute and reach trades.jsonl at resolution (correct behavior — "STWA fills reach trades.jsonl only at resolution"). The system_status "open positions count=0" likely reflects the risk.open_positions counter (taker fills only); BAND maker fills tracked separately.

---

## 5 — ASSUMPTION ATTACK

**Assumption 1: "PA-shrunk + isotonic recalibration produces predictive NO bucket selection"**
- Evidence against: Live WR=14.3% on n=14 NO trades at 0.50–0.56 entry price. Rank-corr +0.39 (2024 backtest) did NOT transfer to live 2026. Worse than random by 5×.
- Cheapest test: Join stwa_pricer_eval.jsonl (n=167k records) to gamma resolution. Compute Spearman rank-corr(p_cal, resolved_YES) and WR by p_cal decile. Cost: 2h analyst time.

**Assumption 2: "BAND YES + NO pair posting replicates the badatmath merge mechanism"**
- Evidence against: 9% merge rate (1/11) vs badatmath's 34%. 0/8 YES resolved YES. Either the YES leg is posted on non-mode buckets, or the YES book is too thin to get filled at profitable prices.
- Cheapest test: Audit last 100 band_struct "fire_yes" entries: is the YES leg the mode bucket (highest p_cal rank) or an off-center bucket? Also check whether fills are happening or orders are stale-resting.

**Assumption 3: "NEG_RISK_ARB fires with sufficient frequency to be a revenue contributor"**
- Evidence against: 0 real fills across all dates. Median real_edge ≈ 0.001, never all_legs_fillable. The Σask < 0.85 condition in a liquid market is structurally unreachable.
- Cheapest test: Pull 30-day historical Σ(YES ask per city) from gamma snapshots. Check if Σask < 0.85 AND all_legs_fillable ever occurred simultaneously. If never: the arb gate needs redesign for partial coverage.

---

## 6 — EXTEND EXISTING EDGE

| Extension | Effort | Annual $ | P(success) |
|---|---|---|---|
| Min-lockout live (daily-low markets) | LOW | +$250/yr | MEDIUM — mechanism is sound (mirror of max-lockout), shadow has n~100k records Jun 8–12; needs resolution join for WR proof |
| THERMO maker cap expansion (after n≥20 resolved) | ZERO | +$200–$400/yr | LOW until n≥20 resolved; 2/2 so far mixed (1 near-certain win, 1 loss at 0.81) |
| Peakscalp (user GO required) | MEDIUM | Backtest +high ROI | MEDIUM — model-free mechanism; needs live test |

---

## 7 — PROPRIETARY EDGE RESEARCH

**Only after 1–6. Directional engine is anti-predictive; extending a losing system is capital destruction.**

One validated signal: **observation lead time edge** via multi-source NMS. 9 sources give 9–28 min lead. Currently moot because the direction signal itself is wrong—if model-NO were fixed, early obs would be the multiplier.

Do not build new infra. Validate direction signal correctness via Experiment 1 first.

---

## 8 — THREE EXPERIMENTS

### Experiment 1 (Cheap, Fast, High-VoI): Engine direction signal validation
- **Hypothesis**: p_cal from PA-shrunk pricer has positive rank-correlation with actual daily-max YES resolution probability
- **Data**: stwa_pricer_eval.jsonl (n=167k records today) joined to gamma resolution for same event_key
- **Time**: 2 hours
- **Cost**: $0
- **Success metric**: rank-corr > +0.20 AND WR for p_cal > 0.60 buckets exceeds 60%
- **If YES**: Direction signal works on YES side; investigate why NO selection fails specifically (entry timing? spread?)
- **If NO (rank-corr ≤ 0.20 or negative)**: Model direction is noise; disable STWA_REGULAR_NO_ENABLED and do not re-enable without Tier-3b model refit

### Experiment 2 (Cheap, Fast, High-VoI): BAND YES fill-quality audit
- **Hypothesis**: BAND YES fills land on mode buckets (off=0) and the mechanism is correct but YES odds are too cheap to survive
- **Data**: band_struct "fire_yes" events joined to fill prices and p_cal rank
- **Time**: 1–2 hours
- **Cost**: $0
- **Success metric**: >50% of YES fills are the off=0 (mode) bucket
- **If YES (fills on mode)**: YES edge is timing-dependent; consider posting YES closer to open
- **If NO (fills on off≥1)**: Off-rule is filtering mode but allowing shoulders → band selection bug

### Experiment 3 (Cheap, Medium, High-VoI): Min-lockout validation join
- **Hypothesis**: metar_min_lockout candidates with margin_c ≥ 0.5°C and non-null no_ask resolve NO at ≥90% WR
- **Data**: All hot/2026-06-08 through hot/2026-06-12 metar_min_lockout.jsonl records (n~100k) joined to gamma resolution via condition_id
- **Time**: 4–6 hours
- **Cost**: $0
- **Success metric**: n≥100 fillable candidates with WR ≥ 90%
- **If YES**: Enable MIN_LOCKOUT_LIVE=True; start at $0.50–$3/trade
- **If NO**: Oracle provenance issue present in min-lockout; investigate before enabling

---

## 9 — SINGLE BEST ACTION

**Disable engine model-NO path (STWA_REGULAR_NO_ENABLED=False)**

Why #1: This path is anti-predictive (WR=14.3% on n=14, 5× worse than random), responsible for 71% of post-June5 losses (-$39.16), and actively destroying capital at -$0.80/$ staked. Every additional day it runs increases the damage. The fix is one flag. Capital is the bottleneck for all other strategies; protecting it is the prerequisite.

Upside: Stops ~$1.75/day of capital destruction at current pace. Preserves capital for BAND pair-quoting and lockout paths that have structural logic.

Confidence: HIGH — direction consistent across all 14 NO trades, no cherry-picking.

First step: Set STWA_REGULAR_NO_ENABLED=False in config, then immediately run Experiment 1 (pricer_eval join) to determine whether re-enabling with a corrected recalibration is viable.

---

## STANDING MONITOR — M1β Thin-Margin Lockout Slice

**Data availability**: m1_beta_probe.jsonl files visible in shadow_summary for hot/Jun 2, 3, 4, 6, 7, 9 only. No m1_beta_probe.jsonl detected after June 9. Possible explanations: (a) probe was retired/merged; (b) thin-margin fires ceased; (c) file logging bug. metar_min_lockout.jsonl (current log) has minimum margin_c = 0.5°C — the [0.2,0.5)°C band is below detection threshold.

**Live n in [0.2,0.5)°C band**: Cannot isolate cleanly from available data. Proxy: WEATHER_M1_PROBE resolved trades (all BUY_NO):

| Trade | Open | Entry price | Net PnL | Likely depth |
|---|---|---|---|---|
| T1 | 2026-06-07 | 0.965 | -$10.62 | Deep lockout (≥0.5°C) → false lock |
| T2 | 2026-06-07 | 0.918 | +$0.95 | Deep lockout → genuine win |
| T3 | 2026-06-09 | 0.193 | +$35.50 | Thin margin candidate (cheap NO) |
| T4 | 2026-06-09 | 0.813 | -$9.76 | Mid-depth → false lock |
| T5 | 2026-06-09 | 0.083 | -$3.41 | Very thin / false lock |

- **Live n**: 5 total (cannot isolate [0.2,0.5)°C cleanly); << n≥100 threshold
- **WR**: 2/5 = 40% (dominated by one +$35.50 outlier)
- **EV/share**: Cannot compute (share counts not logged separately)
- **Trend**: Directionally mixed. The 2 false locks (0.965 and 0.083) suggest oracle-provenance issues persist in thin-margin zone.

**DECISION**: n=5 << n=100. **Report trend only: mixed, no action.**

**ANOMALY**: m1_beta_probe.jsonl absent after June 9. If the [0.2,0.5)°C probe is no longer running, the standing monitor has no data source. Engineering check needed: confirm whether the probe is logging to a different path or has been retired.

---

## PROPOSED ACTIONS (human review)

**ACTION-1 [URGENT]**: Disable engine model-NO path.
```python
# config.py
STWA_REGULAR_NO_ENABLED = False
```
Evidence: WR=14.3% n=14 NO trades, EV/$ = -0.797. Anti-predictive, responsible for 71% of post-June5 losses. Tier-2 action (disable a buy path).

**ACTION-2 [analysis, no deploy]**: Run Experiment 1 before re-enabling:
```bash
python3 analysis/weather/stwa_pricer_eval_join.py
# Compute rank-corr(p_cal, resolved_YES) and WR per p_cal decile
```
Decision gate: if rank-corr > +0.20, investigate specific failure mode of NO entry; if ≤ 0, do not re-enable without model refit.

**ACTION-3 [engineering check]**: Confirm m1_beta_probe.jsonl logging status.
```bash
# Run on VPS:
ls -la /root/Klaus/logs/shadow/hot/$(date +%Y-%m-%d)/m1_beta_probe.jsonl
```
If missing: determine whether probe was retired intentionally or logging bug. If retired, close the M1β standing monitor. If bug, restore.

**ACTION-4 [low urgency]**: Run min-lockout validation join (Experiment 3) and enable MIN_LOCKOUT_LIVE=True if WR ≥ 90% at n≥100.

---

## SUMMARY

System is active and well-capitalized ($225.67). Primary threat: engine model-NO is anti-predictive on live data (WR=14.3%, n=14) and is the dominant capital drain (-$39.16 of -$55.05 post-June5 losses). Kill switch flag threshold is breached (WR=17.9% across 39 trades). BAND has 11 resolved trades trending negative. NEG_RISK_ARB finds 0 fillable opportunities. M1β probe appears absent after June 9. One positive signal: WEATHER_M1_PROBE trend at +$0.295/$ on n=5 (driven by outlier). Recommended immediate action: disable STWA_REGULAR_NO_ENABLED and run direction signal validation before any further NO trading.
