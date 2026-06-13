# Execution & Markout Audit — 2026-06-13T07:09Z

**Snapshot**: 2026-06-13T07:02:33Z (7 min old — FRESH)
**System**: `klaus systemd: active` ✓
**Data window**: Jun 10–Jun 13 07:09 UTC (partial day today)
**n**: 125 registered fills (4d) — **TREND-GRADE** (40–99 = trend; 100+ = decision-grade at upper boundary)

---

## 1. FILL TAPE (24h + 7d)

### Daily fills (registered new-token fills only; 88 additional increment fills not double-counted)

| Date | Fills | YES | NO | NO-share | $ Filled |
|------|------:|----:|---:|--------:|---------:|
| Jun 10 | 15 | 12 | 3 | 20.0% | $29.59 |
| Jun 11 | 51 | 30 | 21 | 41.2% | $143.08 |
| Jun 12 | 47 | 42 | 5 | 10.6% | $99.49 |
| Jun 13* | 12 | 8 | 4 | 33.3% | $27.62 |
| **Total** | **125** | **92** | **33** | **26.4%** | **$299.78** |

*\* Partial — 0–07h UTC only*

### By price band (4d total)

| Band | Fills | YES | NO | $ |
|------|------:|----:|---:|----|
| <0.10 | 2 | 2 | 0 | $1.57 |
| 0.10–0.30 | 71 | 71 | 0 | $111.86 |
| 0.30–0.50 | 19 | 19 | 0 | $46.60 |
| 0.50–0.85 | 22 | 0 | 22 | $77.75 |
| >0.85 | 11 | 0 | 11 | $62.00 |

**Structural finding**: YES fills are entirely in 0.10–0.50; NO fills are entirely in 0.50–0.99. Price bands are completely segregated by side — this is expected given BAND_PX_CEIL=0.45 (yes) and BAND_NO_MIN=0.52 (no).

### Time-to-fill (approximate, n=99 city+side+price matched pairs)

| Band | n | Median TTF |
|------|--:|----------:|
| <0.10 | 2 | ~156 min |
| 0.10–0.30 | 58 | 113 min |
| 0.30–0.50 | 18 | 58 min |
| 0.50–0.85 | 21 | 21 min |
| **Overall** | **99** | **82 min** |

NO legs (0.50–0.85) fill 5× faster than YES legs (0.10–0.30). YES legs at cheapest prices sit for ~113 min — long enough to span multiple resolve cycles for same-day markets.

### Top cities by fills (4d)
Jeddah (9), San Francisco (8), Beijing (8), Munich (7), Moscow (7), London (7), Qingdao (6), Taipei (6), Helsinki (6).

---

## 2. NO-PARITY MONITOR

**Context**: NO-starvation bug fixed 2026-06-12 (commit `222bf5cf`). Fix added: cash pre-check before book fetch, YES fetch sub-budget 50/80, NO-candidate rotation, per-cycle queue log.

### New posts by side per day (band_struct_lite `record=post`)

| Date | Posts | YES | NO | NO-share | >=10 posts? | ALERT? |
|------|------:|----:|---:|--------:|:-----------:|:------:|
| Jun 10 | 170* | 2 | 4 | 2.4% | Y | YES |
| Jun 11 | 68 | 54 | 14 | 20.6% | Y | YES |
| Jun 12 | 85 | 82 | 3 | **3.5%** | Y | **YES** |
| Jun 13 | 12 | 10 | 2 | 16.7% | N (n<10) | no |

*\* Jun 10 format differs — `side` field absent from many records; counts understated.*

**Jun 12 NO-share of posts: 3.5% — ALERT TRIGGERED** (threshold: <25% with >=10 posts).

The NO-starvation fix partially restored NO on Jun 11 (20.6%) but then Jun 12 regressed to 3.5%. This is not a fix regression — it reflects the underlying stake-cap interaction (see §3).

### Resting book parity (live, excl. SELL_EXIT)

| Side | Count | $ Locked |
|------|------:|---------:|
| YES | 20 | $21.10 |
| NO | 3 | $5.67 |
| **NO share** | **13.0%** | **21.2%** |

Target ~50%. Resting book is heavily YES-skewed. **ALERT: NO share of resting book = 13.0% (target ~50%).**

---

## 3. QUEUE HEALTH

### STRUCT-BAND-Q summary by day

| Date | Cycles | mean posted/cycle | 0-posted% | cash_preskip | books/80 | yes_books/50 | yes_resv_skip | yes_cap |
|------|-------:|------------------:|----------:|-------------:|---------:|-------------:|--------------:|--------:|
| Jun 12 | 130 | 1.7 | 84% | 197 | 0.3 | 0.3 | 22 | $1.19 |
| Jun 13 | 82 | **0.1** | **90%** | 229 | 0.1 | 0.1 | **58** | **$1.41** |

**No fetch starvation**: books pinned at 0.3/80 and 0.1/80 — nowhere near the 80-cap ceiling. Gamma book fetches are healthy.

**Deployment stall check**: cash_preskip=229 (>200) but posted/cycle=0.1 rather than strictly 0 — not a deployment stall, it's a stake-cap blockage (engine is running, just rejecting all candidates on cost).

### Root cause of 90% zero-posted cycles today

- `BAND_STAKE_FRAC_YES = 0.010` × `$249.10` = $2.49 per-cycle YES budget
- `BAND_NO_CASH_RESERVE = 0.50` reserves half the budget → effective YES cap ≈ **$1.24–$1.41/cycle**
- `BAND_YES_MAX_OFF = 1` → only off=0 ($3.00) and off=1 ($2.10) YES legs are eligible
- **Both YES stake sizes ($3.00, $2.10) exceed yes_cap ($1.41) → all YES candidates rejected**
- Result: yes_resv_skip=58/cycle (all candidates found, all blocked), posted=0.1/cycle
- NO is also effectively stalled: only 2 `fire_no` events all day (Seattle NO 0.65, Dallas NO 0.57)

**ALERT: Posted/cycle has declined 17× from Jun 12 (1.7) to Jun 13 (0.1). yes_resv_skip=58 is the binding constraint — the NO cash reserve combined with STAKE_FRAC_YES creates a stake floor that blocks all YES legs.**

---

## 4. RESOLUTION MARKOUT (fill quality)

### Exit099 (recycle099) events — filled legs that resolved to winner

| Date | n | Cost | PnL | ROI |
|------|--:|-----:|----:|----:|
| Jun 10 | 1 | $5.82 | $0.12 | 2.1% |
| Jun 11 | 10 | $40.83 | $20.21 | 49.5% |
| Jun 12 | 13 | $53.94 | $37.52 | 69.6% |
| Jun 13 | 3 | $5.42 | $33.19 | 612.7% |
| **Total** | **27** | **$106.00** | **$91.05** | **85.9%** |

*Jun 13 high ROI: 3 cheap entry wins (entry $0.13–$0.27 @ 0.99 exit).*

### By entry price band (resolved legs)

| Entry band | n | Cost | PnL | ROI |
|-----------|--:|-----:|----:|----:|
| 0.10–0.30 | 6 | $12.17 | $55.15 | 453.3% |
| 0.30–0.50 | 1 | $2.80 | $5.50 | 196.6% |
| 0.50–0.85 | 12 | $50.25 | $29.22 | 58.2% |
| >0.85 | 8 | $40.79 | $1.17 | 2.9% |

Cheap YES legs (entry <0.30) produce the highest ROI per dollar when they win. Near-resolution NO entries (>0.85) are very low margin per dollar.

### Winner's curse assessment

**Cannot compute**: `band_resolution_join.py` absent from codebase; `band_struct_lite` does not carry per-leg resolution outcomes. The all-fires baseline ROI (needed to detect selective adverse filling) is unavailable.

**Proxy signals**:
- 27 exit099 events = 27 wins. Zero explicit loss-exit events logged.
- 10 untracked fills at price <0.10 totaling $52.95 — consistent with losing-leg residual value recovery at resolution (the opposite token paid to ~$0.03).
- Win/loss proxy: 27 resolved wins vs ~10 resolved losses inferred from low-price untracked fills.
- **No winner's curse signal detectable** at n=27, but sample too small to clear (need n≥40 per slice for the adverse-selection test; 0.50–0.85 NO band has n=12 — closest to threshold).

---

## 5. DEAD-QUOTE RECLAIM

| Metric | Value |
|--------|------:|
| "reaped dead entry" lines (7d tape) | 0 |
| Reclaim events in band_struct_lite | 0 |
| Quotes >24h old | 4 |
| Quotes >48h old | 0 |

**No 48h alert triggered** (threshold: >20 quotes older than 48h).

Quotes >24h old (BAND_RECLAIM_AGE_S=6h = eligible after 6h):

| Age | City | Side | Price | Fill% | Question |
|----|------|------|------:|------:|---------|
| 28h | Seattle | NO | 0.56 | 0% | …highest temp between 64–65°F on June 12? |
| 28h | Seoul | NO | 0.63 | 0% | …highest temp 22°C on June 13? |
| 28h | Jeddah | YES | 0.04 | 100% | …highest temp 35°C on June 12? *(expired, fully filled)* |
| 28h | Guangzhou | YES | 0.15 | 37% | …highest temp 31°C on June 13? |

Seattle NO and Seoul NO: 28h old, 0% filled, CLOB bids likely stale or behind touch. Both are past the 6h reclaim threshold and should be candidates for the next reclaim sweep (BAND_RECLAIM_PER_CYCLE=10 rotating). **No active reaping observed — reclaim sweep may not be running or finding these orders.**

---

## 6. CASH VELOCITY

| Metric | Value | Benchmark |
|--------|------:|----------:|
| Capital (bankroll.json) | $249.10 | — |
| Maker locked YES+NO | $26.77 | — |
| SELL_EXIT pending (shares @ 0.99) | $686.07 | — |
| Avg fills/day (Jun 10–12) | $90.72 | — |
| Turns/day | **0.364** | ~1.0 (badatmath) |
| Fills last 24h (partial to 07h) | $27.62 | — |

**Turns/day = 0.364 — 2.7× below badatmath benchmark of ~1.0.**

SELL_EXIT book ($686 in resting 0.99 asks, 70 orders, 693 shares) represents significant value awaiting resolution-triggered buyers. These are not capital deployed but capital earned waiting to settle. Untracked SELL_EXIT fills at >=0.98 over 4d: $5,637 — implying strong resolution flow, but through the untracked WS path.

**Capital note (CAVEAT)**: `daily_start_capital=$15.95` in bankroll.json does not reflect actual capital. User sells manually. The $249.10 figure is what the bot tracks; do not infer ruin or PnL trend from this file alone.

---

## ALERTS

| # | Alert | Triggered | Detail |
|---|-------|:---------:|--------|
| A1 | NO share of new posts <25% on day with >=10 posts | **YES** | Jun 12: 3.5% NO (85 posts). Starvation fix did not hold through Jun 12. |
| A2 | Posted/cycle degradation | **YES** | Jun 12→13: 1.7→0.1 (-94%). YES stalled by yes_resv_skip=58/cycle (stake cap floor > yes_cap). |
| A3 | NO share of resting book <50% | **YES** | 3 NO / 20 YES = 13% (target ~50%). Book is structurally YES-heavy. |
| A4 | Dead quotes >48h | NO | 0 quotes >48h. |
| A5 | Books pinned at 80 (fetch starvation) | NO | books=0.1–0.3/80. Fetch healthy. |
| A6 | cash_preskip >200 sustained with posted=0 (deployment stall) | NO | cash_preskip=229 but posted=0.1/cycle — stake-cap blockage, not stall. |
| A7 | Winner's curse (filled ROI << all-fires ROI) | CANNOT COMPUTE | No all-fires baseline. n=27 wins observed, inference limited. |

---

## SUMMARY

**Fills/day**: 31 avg (125 fills / 4 days); $75/day avg inflow; turns/day = 0.364 (2.7× below benchmark).

**NO-share**: 26.4% of fills across 4d (trend; n=125). Jun 12 post-parity: 3.5% NO of posts = ALERT. Fix from Jun 12 has not produced sustained NO parity in the posting layer. Resting book: 13% NO.

**Binding execution constraint today**: `yes_resv_skip=58/cycle` caused by `BAND_STAKE_FRAC_YES×capital×(1−NO_CASH_RESERVE) ≈ $1.24 < BAND_BASE_STAKE_min($2.10)`. The NO cash reserve (0.50) combined with the YES per-cycle stake fraction creates a floor that blocks all BAND_YES_MAX_OFF=1 candidates. YES posting is functionally frozen. NO posting is also minimal (2 fire_no events all day). The bot is cycling but posting near-zero.

*Report generated by exec-audit-agent, 2026-06-13T07:09Z*
