# Exec Audit — 2026-06-16T07:21Z

**Snapshot age:** 0.35h (fresh; SNAPSHOT.md ts=2026-06-16T07:00:08Z)
**System status:** `active` (bot uptime since 2026-06-15 05:52 UTC)
**Capital (bankroll.json):** $236.24 | bankroll is CAVEAT — manual sells not modeled, do not infer PnL/ruin from this alone
**Band config authoritative source:** `band_config.txt` (snapshot 2026-06-16T07:00:08Z)
**Data window:** fill-tape (`maker_fills_recent.log`) only covers 2026-06-13 08:17Z → 2026-06-16 07:01Z (70.7h, not a full 7d — log retention is shorter than the 7d journal nominally promised). band_struct_lite posts available 2026-06-11 → 2026-06-16 (6 days).

---

## Section 1 — Fill Tape

### 24h (to 07:14Z)

- **Fills:** 120 | **$ filled:** $116.83
- **By side:** YES=119 ($112.75) | NO=1 ($4.08)
- **By price band:** <0.10: 18 | 0.10–0.30: 75 | 0.30–0.50: 26 | 0.50–0.85: 1
- **Top cities:** Beijing 7, London 7, Jeddah 6, Taipei 6, Seoul 6, Chengdu 5, Helsinki 5, Guangzhou 5, Paris 5, Istanbul 5

### Available window (70.7h, labeled "7d" but is actually 2.9 days)

- **Fills:** 271 | **$ filled:** $395.84
- **By side:** YES=224 ($254.51) | NO=47 ($141.34)
- **By price band:** <0.10: 28 | 0.10–0.30: 153 | 0.30–0.50: 44 | 0.50–0.85: 46
- **By day:** 06-13: 55 | 06-14: 81 | 06-15: 110 | 06-16 (partial): 25

### Fill rate (posted tokens with ≥1 fill anywhere in the fill-log window)

| Date | Posted tokens | Filled | Rate |
|---|---|---|---|
| 06-11 | 61 | 0 | 0.0% (predates fill-log retention) |
| 06-12 | 67 | 6 | 9.0% (mostly predates retention) |
| 06-13 | 51 | 37 | 72.5% |
| 06-14 | 73 | 49 | 67.1% |
| 06-15 | 108 | 82 | 75.9% |
| 06-16 (partial) | 24 | 11 | 45.8% |

Fill-log only goes back to 06-13 08:17Z, so 06-11/06-12 rates are not meaningful (denominator real, numerator censored). 06-13 through 06-15 show a healthy 67–76% same-window fill rate.

### Time-to-fill (post ts → first MAKER-FILL ts, joined on 12-digit token prefix — fill-log truncates `token_id` to its first 12 digits)

n=178: **median = 169 min (2.8h)** | p25 = 52 min | p75 = 7.1h | max = 44.0h

---

## Section 2 — NO-Parity Monitor

### New posts by side per day (`band_struct_lite` `post` records)

| Date | YES | NO | Total | NO-share | Alert (n≥10, <25%)? |
|---|---|---|---|---|---|
| 06-11 | 54 | 14 | 68 | 20.6% | ⚠ ALERT |
| 06-12 | 82 | 3 | 85 | 3.5% | ⚠ ALERT |
| 06-13 | 43 | 16 | 59 | 27.1% | OK |
| 06-14 | 67 | 20 | 87 | 23.0% | ⚠ ALERT |
| 06-15 | 178 | 4 | 182 | 2.2% | ⚠ ALERT |
| 06-16 (partial) | 26 | 0 | 26 | 0.0% | ⚠ ALERT |

### Hourly breakdown around the 06-15 cash-policy changes

NO-share by UTC hour, 06-14 → 06-15:

```
06-14 (spotty, ranging 0–50% across the day, broadly consistent with the post-fix baseline)
06-15 00:00–05:00   NO-share 0–50% (small samples)
06-15 06:00 onward  NO-share = 0.0% EVERY hour through end of day (16 consecutive hourly buckets, 0 NO posts)
06-16 (all hours so far)  NO-share = 0.0%
```

**Root cause identified:** commit `9caaf67a` (2026-06-15 04:56Z, "unreserve NO cash pool... YES is the +EV leg, NO breakeven") removed the `BAND_NO_CASH_RESERVE` protection that the 06-12 NO-starvation fix (`222bf5cf`) and the 06-12 `f733ef5a` follow-up had put in place. `ba59e945` (06-15 05:51Z, "YES stake to CLOB exchange minimum — breadth not size") landed ~1h later, shrinking YES per-slot stake to fit more YES candidates into the same cash budget. From 06-15 06:00Z onward, **NO-share of new posts has been a flat 0%** for ~25 consecutive hours (174 YES posts, 1 NO post total in that span). This is a full relapse — worse than the original bug the 06-12 fix addressed, and confirms the 06-12 fix's protection mechanism (cash reservation) was the only thing holding NO-share up, not a structural fix to candidate generation.

### Resting book (excl. SELL_EXIT)

YES=36 | NO=4 | None=1 → **NO-share = 9.8%**, consistent with the post-side collapse — the live book has been skewed toward YES for days and is not self-correcting.

---

## Section 3 — Queue Health

| Date | Cycles | mean cash_preskip | mean books | mean yes_books | posted/cycle | pinned books=80 | pinned yes_books=50 | posted=0 & cash>200 |
|---|---|---|---|---|---|---|---|---|
| 06-13 | 187 | 194.4 | 0.2/80 | 0.2/50 | 0.23 | 0/187 | 0/187 | 94/187 (50%) |
| 06-14 | 279 | 163.7 | 0.3/80 | 0.2/50 | 0.31 | 0/279 | 0/279 | 106/279 (38%) |
| 06-15 | 280 | 233.4 | 1.2/80 | 0.6/50 | 1.82 | 0/280 | 0/280 | 136/280 (49%) |
| 06-16 (partial) | 82 | 245.3 | 0.7/80 | 0.3/50 | 0.33 | 0/82 | 0/82 | 55/82 (67%) |

No book-fetch-starvation regression (`books`/`yes_books` never pinned at the 80/50 cap on any day). No day has `posted=0` for the entire day, so the deployment-stall alert (cash_preskip>200 sustained, posted=0 all day) does **not** fire. Context only: roughly 40–65% of individual cycles post nothing despite cash_preskip>200 — this is consistent with most of the candidate queue already being covered (no_cands/pair_cands stay in the 150–190 range all period) rather than a fetch problem.

---

## Section 4 — Resolution Markout (Fill Quality)

**Network status:** `gamma-api.polymarket.com` and `clob.polymarket.com` both return `403 Host not in allowlist` from this sandbox — `band_resolution_join.py` (which needs live Gamma resolution lookups) cannot run. All-fires simulated ROI is therefore **unavailable this run**, same limitation as the 06-15 audit. This is reported honestly rather than fabricated.

**Proxy used (same as prior audit):** `trades.jsonl` `STWA_RESOLVED` exits since 2026-06-10, n=119 (98 YES, 21 NO) — these are actual resolved BAND positions, i.e. realized ROI **conditional on fill** (the half of the winner's-curse test we can compute without the API).

### BUY_YES (n=98, trend-grade, bordering decision-grade)

| Price band | n | WR | breakeven (avg entry) | avg ROI | total PnL |
|---|---|---|---|---|---|
| <0.10 | 4 | 0.0% | ~6.5% | −100.0% | −$8.40 |
| 0.10–0.30 | 77 | 5.2% | ~19.5% | −86.0% | −$144.17 |
| 0.30–0.50 | 17 | 5.9% | ~33.1% | −95.3% | −$44.03 |
| **Combined** | **98** | **5.1%** | **~21.4%** | **−88.4%** | **−$196.60** |

### BUY_NO (n=21, data-collection grade)

| Price band | n | WR | breakeven | avg ROI | total PnL |
|---|---|---|---|---|---|
| <0.10 | 1 | 0.0% | ~8.3% | −100.0% | −$3.41 |
| 0.50–0.85 | 18 | 16.7% | ~61.0% | −81.5% | −$63.52 |
| >0.85 | 2 | 50.0% | ~98.0% | −49.0% | −$5.28 |
| **Combined** | **21** | **19.0%** | **~62.0%** | **−78.4%** | **−$72.22** |

### Winner's-curse assessment

YES fill-conditional WR is **5.1% against a quoted-price-implied breakeven of ~21.4%** — a ~4× gap, n=98 (just under the n=100 decision gate, but consistent with yesterday's n=68/WR=4.4% reading and now larger). This is the same signal repeating and strengthening: **plainly, this looks like winner's curse.** The bot is filled selectively on the wrong side — fills happen when the market already knows the temperature bucket is unlikely, i.e. resting bids get picked off by better-informed flow as the event approaches resolution. NO side shows the same pattern (WR 19% vs ~62% breakeven) though n=21 is data-collection grade only.

Caveat: this proxy measures realized-ROI-conditional-on-fill only. It does NOT establish the "all-fires" comparator required to formally confirm winner's curse per the protocol (Gamma API blocked). But two consecutive daily reads at growing n, both showing WR roughly a quarter of breakeven, is strong directional evidence and should not be waved off as noise.

---

## Section 5 — Dead-Quote Reclaim

- **"reaped dead entry" lines in fill tape:** 0 (none in the available 70.7h window)
- **`BAND_RECLAIM_AGE_S`:** 7200s (2h, per band_config.txt)
- **Resting quotes >24h old:** 19
- **Resting quotes >48h old:** 16 (alert threshold is >20 → **not triggered**)
- **Oldest resting quotes:** 107.3h (~4.5 days) — Seoul NO and Seattle NO, both `matched=0.0` (never filled at all), both for markets whose `end_date` (06-10/06-11) has long passed.

Two genuinely dead, zero-fill quotes are sitting at ~4.5× the `BAND_RECLAIM_AGE_S` config value with zero reclaim activity logged anywhere in the available window. Raw count doesn't cross the pre-registered >20-quotes-over-48h alert, so no alert fires, but the complete absence of any reclaim log line despite a 2h configured age and several quotes 50× past that age is worth a flag for next run if it persists.

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $236.24 |
| Resting $ (Σ q_price×(size−matched), excl. SELL_EXIT) | $38.33 |
| Deployed at cost (Σ q_price×matched, excl. SELL_EXIT) | $49.57 |
| Fills $ last 24h | $116.83 |
| **Turns/day (fills$ ÷ capital)** | **0.49** |
| Benchmark (badatmath) | ~1.0 turn/day at 10–20% ROI/turn |

Turns/day at 0.49 is roughly half the badatmath benchmark. Combined with the NO-share collapse (Section 2) and the small per-stake size (`BAND_BASE_STAKE`=$1, `BAND_STAKE_FRAC_YES`=0.005), capital is being deployed in many small YES-only slices rather than the more symmetric, larger-notional flow the benchmark mirror implies.

---

## ALERTS (pre-registered, fired)

1. **NO-SHARE ALERT — fired 5 of 6 days, now total collapse.** NO-share of new posts <25% on 06-11 (20.6%), 06-12 (3.5%), 06-14 (23.0%), 06-15 (2.2%), 06-16 (0.0%). From 06-15 06:00Z onward NO-share has been **flat 0%** for ~25 consecutive hours (174 YES vs 1 NO posted). Traced to commit `9caaf67a` (unreserve NO cash pool, 06-15 04:56Z) + `ba59e945` (YES min-stake breadth, 06-15 05:51Z). The 06-12 NO-starvation fix's effectiveness depended entirely on the cash reservation these commits removed — this is a regression to a worse state than pre-fix, not a new bug.

2. **WINNER'S-CURSE FLAG — repeated, strengthening.** YES fill-conditional WR=5.1% vs breakeven~21.4% (n=98, just under the n=100 gate but consistent with and larger than yesterday's n=68/4.4% reading). All-fires comparison still blocked (Gamma/CLOB API both return 403 in this sandbox) so this isn't yet the full protocol-required confirmation, but two consecutive growing-n reads at ~1/4 of breakeven WR is a real signal, not noise.

No queue-fetch-starvation alert, no deployment-stall alert, no dead-quote->20-over-48h alert this run.

---

## 3-Line Summary

**Fills/day:** ~95–110/day on full days (06-13 through 06-15), $100–135/day notional, 0.49 turns/day (49% of the badatmath 1.0 benchmark).

**NO-share:** 0.0% for the last ~25 hours straight — total NO-side starvation, caused by the 06-15 cash-unreserve + YES-min-stake commits undoing the 06-12 fix's protection.

**Binding execution constraint today:** NO-parity collapse (book is now ~98% YES by new-post count) is the dominant execution problem; the still-unconfirmed-but-recurring YES winner's-curse signal (WR 5.1% vs ~21% breakeven, n=98) is the second, and the two compound — the bot is overweighting the leg with the weaker resolved-fill quality.
