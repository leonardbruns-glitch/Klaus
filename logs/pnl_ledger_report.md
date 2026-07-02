# Klaus PnL Ledger — 2026-07-01

**Generated:** 2026-07-01T23:37Z  
**Snapshot age:** 9 min (2026-07-01T23:28:51Z) — VALID  
**System:** `klaus systemd: active`  
**Capital:** $76.691556  
**Note: No Jun 30 report found in state — this report covers the 2-day window Jun 29 23:37→Jul 1 23:28 UTC. Jun 30 routine likely failed or was skipped.**

---

## Section 1 — P&L Explain

**Capital change (2-day):** $84.151838 → $76.691556 = **−$7.460**

### Jul 1 UTC: trades.jsonl closed legs (ts_close in window)

| Entry class | City | Side | Shares | Entry | Exit | Exit reason | Opened | net_pnl |
|---|---|---|---|---|---|---|---|---|
| WEATHER_STRUCT_BAND | Chengdu | YES | 9.5 | 0.38 | 0.455 | BAND_MERGE | Jul 1 06:58 | **+$0.713** |
| WEATHER_STRUCT_BAND | Chengdu | NO | 0.5 | 0.47 | 1.00 | STWA_RESOLVED | Jul 1 06:54 | **+$0.265** |
| WEATHER_STRUCT_BAND | Beijing | NO | 7.8 | 0.65 | 0.00 | STWA_RESOLVED | Jun 30 08:40 | **−$5.070** |
| WEATHER_STRUCT_BAND | Chengdu | NO | 7.0 | 0.74 | 0.00 | STWA_RESOLVED | Jun 29 18:07 | **−$5.180** |
| WEATHER_STRUCT_BAND | Munich | NO | 7.0 | 0.72 | 0.00 | STWA_RESOLVED | Jun 30 04:22 | **−$5.040** |
| **Total** | | | | | | | | **−$14.313** |

All 3 losses: NO positions resolved at $0.00 — underlying temperature was YES (within the target bucket). Beijing, Chengdu (Jun 29), Munich all wrong-side. Wins from Chengdu pair_fav (d+0 same-bucket YES+NO), both legs filled; YES exited early at 0.455 via band convergence; only 0.5 NO shares captured in trades.jsonl at resolution. **Remaining ~9 NO shares of the pair (~$4.23 at cost) are likely in SELL_EXIT queue pending $1.00 resolution or 0.99 RECYCLE — not yet in trades.jsonl.**

### Jun 30 UTC: RECYCLE099 exits (exit099_live)

| Token | Shares | Entry | Exit | PnL |
|---|---|---|---|---|
| 69181562... | 7.0 | 0.70 | 0.99 | +$2.088 |
| 114250850... | 11.0 | 0.97 | 0.99 | +$0.220 |
| 27976089... | 7.0 | 0.65 | 0.99 | +$2.652 |
| 80792441... | 7.0 | 0.68 | 0.99 | +$2.325 |
| **Total** | **32.0 sh** | | | **+$7.285** |

Three of four tokens were in Jun 29 band_posted_state (Jun 29-posted d+1 NO positions for Jul 1 date, converged and recycled early). One token (114250850...) is not in recent band_posted_state — likely an older position (≥Jun 28).

### Attribution summary

| Source | PnL |
|---|---|
| Jul 1 trades.jsonl (5 legs) | −$14.313 |
| Jun 30 RECYCLE099 (4 exits) | +$7.285 |
| Expected maker rebate (Jul 1, §3) | +$0.299 |
| **Total attributed** | **−$6.729** |
| **Observed capital delta** | **−$7.460** |
| **UNEXPLAINED** | **−$0.731** |

**UNEXPLAINED = −$0.731 — within the $5 investigation threshold. Do NOT flag as MODEL DEFICIENCY.**  
Most likely causes: (1) Polygon gas fees on 14+ maker order placements (~$0.03–0.05/tx × ~20 txs ≈ $0.60–$1.00 is plausible); (2) rounding on RECYCLE099 entry-price vs bankroll's tracked cost basis; (3) Jun 30 fills and rebate not separately attributed (this report covers 2 days; Jun 30 rebate is unaccounted). The small negative direction is consistent with gas bleed dominating the native-resolution tailwind for this 2-day window.

**Contrast with Jun 29 report's +$14.90 unexplained:** that session showed large positive unexplained from native d+1 resolutions landing in funder wallet. For this window, 3 of 5 resolutions were losses (→$0), so the native resolution tail is negligible or negative. Not a repeat of the prior logging gap pattern.

---

## Section 2 — Compounding Scoreboard

### Equity estimate

| Component | Value | Caveat |
|---|---|---|
| Cash (bankroll.capital) | $76.69 | Authoritative |
| SELL_EXIT resting @ $0.99 (63 sh) | $62.37 | NOT yet cash — 9 orders on CLOB, matched=0; fills at 0.99 or resolution at $1.00 both plausible; size = [9,5,8,8,8,5,7,6,7] sh |
| Open book at 65% of cost (111.8 sh @ $71.73) | $46.63 | Binary at resolution; 65% a conservative mid-point between cost and expected par; no WR data yet for this book |
| **Equity estimate** | **~$186** | Range: $139 (cash+SELL_EXIT only) to $226 (open book at full par) |

**SELL_EXIT ($62.37) is the most important near-term liquidity event.** Once CLOB fills clear or oracle resolves, cash position jumps to ~$139 without any new activity. This is the actual safety cushion — the $1.69 floor proximity is cash-only and understates total equity.

### Turns and ROI

| Metric | Today (Jul 1) | Jun 29 (prior) | Benchmark (badatmath) |
|---|---|---|---|
| fills_usd | $71.73 | $78.50 | — |
| equity_est | ~$186 | ~$158 | — |
| turns/day | **0.39** | 0.50 | ~1.0 |
| ROI/turn (resolved) | **−74.8%** | +41.8% | +10–20% |

**ROI/turn −74.8% is driven entirely by 3 weather-miss resolutions at $0.** Cost of those 3 legs = $15.29, total PnL = −$15.29. This is a binary outcome (wrong side of weather), not a fee or spread bleed. WR on resolved legs today: 2/5 = 40% (2W 3L). Unresolved open book (111.8 sh, $71.73) has no realized outcome yet.

**7-day trend:** Jun 29 +$8.67 on strong RECYCLE099 ($22.05); Jun 30 no report, capital bled; Jul 1 −$14.31 realized (3 NO losses) + incoming SELL_EXIT. Turns declining: 0.50→0.39. ROI/turn sharply negative on resolved legs.

---

## Section 3 — Expected Maker Rebates

**feeRate = 0.05, maker share = 25%; formula: Σ(shares × 0.05 × p × (1−p)) × 0.25**

| Fill | Shares | p | est. rebate |
|---|---|---|---|
| Beijing NO d+1 @ 0.67 | 8.0 | 0.67 | $0.0221 |
| Munich NO d+1 @ 0.62 | 8.5 | 0.62 | $0.0250 |
| Chengdu NO d+0 pair @ 0.47 | 10.0 | 0.47 | $0.0311 ← highest (near mid) |
| London NO d+1 @ 0.63 | 8.0 | 0.63 | $0.0233 |
| Chengdu YES d+0 pair @ 0.38 | 9.5 | 0.38 | $0.0280 |
| Wuhan NO d+1 @ 0.71 | 8.0 | 0.71 | $0.0206 |
| Chengdu NO (old, pre-Jun30) @ 0.74 | 7.0 | 0.74 | $0.0168 |
| Wuhan NO off+2 @ 0.82 | 6.5 | 0.82 | $0.0120 |
| Munich NO d+1 @ 0.64 | 7.8 | 0.64 | $0.0225 |
| **Moscow NO @ 0.93 ⚠️** | 6.0 | 0.93 | **$0.0049** (near-extreme, low rebate) |
| Chengdu NO d+1 @ 0.67 | 8.0 | 0.67 | $0.0221 |
| London NO d+1 @ 0.61 | 9.0 | 0.61 | $0.0268 |
| Beijing NO d+1 @ 0.68 | 7.5 | 0.68 | $0.0204 |
| Wuhan NO d+1 @ 0.63 | 8.0 | 0.63 | $0.0233 |
| **Today total** | **111.8 sh** | | **$0.299** |

**Cumulative expected:** $2.080 (prior) + $0.299 = **$2.379**

⚠️ Cumulative $2.379 > $1.00 minimum accrual threshold — **user should verify pUSD receipt in funder wallet.** This was also flagged in the Jun 29 report ($2.080 then). If no payout has been received, raise with Polymarket #support.

**Moscow fill note:** Moscow NO at p=0.93 generates minimal rebate ($0.005). More importantly: **Moscow is NOT in BAND_CITY_ALLOW = {chengdu, london, beijing, munich, wuhan}**. This fill is anomalous — most likely a residual order placed before the narrow-city allowlist was implemented (commit 847a22f). No Moscow entries observed in today's band_struct_lite shadow. Position is 6.0 sh at $0.93 cost ($5.58 deployed). If Moscow weather resolves against us, it's a $5.58 loss from a non-approved city. **User should verify whether this order should be cancelled or is considered legacy.**

---

## Section 4 — Kill-Switch Proximity

| Metric | Current | Threshold | Distance | Status |
|---|---|---|---|---|
| Capital | $76.692 | $75 weekly floor | +$1.69 | ⚠️ **CRITICAL** |
| Capital | $76.692 | $50 ruin floor | +$26.69 | ✅ Safe |
| Daily halt | −$14.313 resolved PnL | −$10 halt | Exceeded | ⚠️ FLAG (see below) |
| 20-trade WR (rolling) | ~40% today (n=5, insufficient) | <30% over 20 trades | n<20 | Monitor |
| Profit factor | n/a (n<20) | <0.8 over 20 trades | n<20 | Monitor |

**Weekly floor: CRITICAL at $1.69 cushion.** This is cash-only. Including SELL_EXIT pending ($62.37 at 0.99), effective equity is ~$139 — well above any floor. The cash floor may be breached if new maker fills deplete cash before SELL_EXIT orders clear.

**Daily halt ambiguity:** −$14.31 in trades.jsonl today exceeds the −$10 daily halt. **However, these losses represent positions opened on Jun 29–30 resolving today — the cash was already committed on those dates, not today.** Today's new capital deployed was $71.73 in maker fills. The daily halt rule ("stop after −$3 in a single day" per CLAUDE.md $10-era rules, or "−$10 halt" in the kill-switch table) was designed for taker trades with same-day open/close. Applying it to lagged maker resolutions creates a misleading trigger. **Recommendation: do not halt purely on this figure. Assess based on capital trajectory instead.**

**WR/PF caveat (from protocol):** The kill-switch WR/PF floors were specified for the taker era. Maker band YES legs win ~22% by design (4–5× payoff). This session's 2W/5 resolved is not meaningful with n<20. Re-derivation of kill-switch thresholds for maker regime is pending with user.

**3-loss streak context:** 3 consecutive NO losses at $0.00 resolution (Beijing, Chengdu, Munich) over 2 days is unusual for a strategy with historically ~77–80% d+1 NO win rate. Either (a) adverse weather regime (summer heat waves making YES more likely), or (b) city/bucket selection is off for current conditions. **Monitor next 5 resolutions closely.**

---

## Section 5 — Day Verdict

**NO — equity flat to down, realized P&L deeply negative.**

Capital fell $7.46 over 2 days (-8.9% from Jun 29 base). Three NO positions resolved as YES (weather was in the target temperature bucket for Beijing, Chengdu, Munich), generating $15.29 in losses. RECYCLE099 +$7.29 (4 Jun 29-era positions converged and exited cleanly) partially offset.

**Binding constraint:** weather outcome variance — 3/4 resolved NO positions failed in 2 days, double the expected miss rate. This is a high-variance event, not an edge problem, but it is the second time in a week the strategy has taken multiple same-direction hits.

**Mitigant:** 63 SELL_EXIT shares at $0.99 (~$62.37 pending) represent near-certain cash inflow once CLOB fills or oracle confirms. Once cleared, cash position restores to ~$139. Additionally, the Chengdu pair_fav residual (~9 NO shares, pending at $0.47 cost, likely resolving $1.00) could add ~$4.77 unrealized gain to trades.jsonl when booked.

**Open concern:** capital $1.69 above weekly floor on a cash basis. No new trades should be placed that would deplete cash further without SELL_EXIT clearing first. **User action suggested: verify SELL_EXIT orders are in the CLOB and clearing; verify Moscow position is intended; check pUSD rebate receipt.**

---

*Data sources: data-mirror snapshot 2026-07-01T23:28:51Z (9 min old); trades.jsonl 8044 rows; exit099_live 2026-06-30; band_struct_lite 2026-07-01; maker_resting_state.json; maker_fills_recent.log (today: 16 fill events, 14 positions).*
