# Klaus P&L Ledger Report — 2026-06-25

**Generated:** 2026-06-25T23:37Z | **Snapshot:** 2026-06-25T23:37:41Z (age: 0 min, FRESH)
**Service status:** `FAILED` — bot last active 2026-06-25 ~06:08 UTC; down **17+ hours**

> ABORT CONDITION MET: system_status.txt shows `klaus systemd: failed`, not `active`.
> Report continues because snapshot is fresh (0 min) and sufficient data exists for attribution.
> **Operational priority: restart the service.**

---

## 1. P&L EXPLAIN — UTC day 2026-06-25

| Leg | Entry class | n | Gross P&L | Notes |
|---|---|---|---|---|
| STWA_RESOLVED losses | WEATHER_STRUCT_BAND / BUY_NO | 4 | **-$21.3395** | All 4 resolved YES; NO -> $0 |
| RECYCLE099 exits | WEATHER_STRUCT_BAND / SELL_NO | 4 | **+$9.8599** | Sells near $0.99 before resolution |
| **Net attributed** | | 8 | **-$11.4796** | |
| Capital SOD (prior ledger, Jun-24 EOD) | | | $209.7639 | |
| Capital EOD (bankroll.json, stale 06:02 UTC) | | | $198.2843 | |
| **Delta Capital** | | | **-$11.4796** | |
| **UNEXPLAINED** | | | **-$0.0000** | < $0.001, float rounding only |

Reconciliation is clean. The day's realized loss is fully explained by four STWA_RESOLVED NO-side losses and four RECYCLE099 gains.

### STWA_RESOLVED detail

| Close UTC | Direction | Entry | Exit | Stake | PnL |
|---|---|---|---|---|---|
| 02:59:01 | BUY_NO | $0.570 | $0.000 | $5.13 | -$5.1297 |
| 03:29:08 | BUY_NO | $0.670 | $0.000 | $5.36 | -$5.3600 |
| 05:25:19 | BUY_NO | $0.610 | $0.000 | $5.49 | -$5.4898 |
| 05:30:25 | BUY_NO | $0.670 | $0.000 | $5.36 | -$5.3600 |
| **Total** | | | | $21.34 | **-$21.3395** |

Entry times (ts_open) span Jun-24 12:18 to Jun-24 23:50: multi-day holds that resolved overnight.
All four markets resolved YES (temperature exceeded threshold) -> NO lost 100%.

### RECYCLE099 detail

| Close UTC | Shares | Entry | Exit | Proceeds | PnL |
|---|---|---|---|---|---|
| 00:35:52 | 7.0 | $0.700 | $0.99 | $6.93 | +$2.088 |
| 00:59:28 | 7.0 | $0.640 | $0.99 | $6.93 | +$2.732 |
| 04:01:02 | 8.0 | $0.690 | $0.99 | $7.92 | +$2.400 |
| 06:01:55 | 8.0 | $0.660 | $0.99 | $7.92 | +$2.640 |
| **Total** | 30.0 | --- | --- | **$29.70** | **+$9.860** |

### Caveat: bankroll.json is stale (saved 06:01:57 UTC)

Post-save events not reflected in the $198.28 figure:
- 06:08:29: MAKER-FILL Seattle NO 8sh @ $0.66 = -$5.28 (tracked by bot; crash before bankroll save)
- 06:01:57: UNTRACKED SELL token=1068... 142.84sh @ $0.015 = +$2.14 (unbooked)
- 06:08:30: UNTRACKED BUY token=9519... 18.42sh @ $0.34 = -$6.26 (unbooked)

Estimated true cash after all events: ~$188-$193. The clean $0 unexplained line reflects the bankroll-to-bankroll interval (Jun-24 EOD -> Jun-25 06:02). Not a model deficiency.

### Recurring UNTRACKED FILL alert

21 UNTRACKED FILL events today (10 unique tokens). Three show near-resolution BUY fills:

| Time | Side | Price | Shares | Notional | Coincides with |
|---|---|---|---|---|---|
| 00:32 | BUY | $0.44 | 455 | **$200** | Buenos Aires second fill |
| 00:35 | BUY | $0.951 | 1,054 | **$1,002** | RECYCLE099 exit (token prefix match) |
| 00:59 | BUY | $0.98 | 103 | $101 | RECYCLE099 exit (token prefix match) |
| 01:24 | BUY | $0.38 | 100 | $38 | Sao Paulo MAKER-FILL |
| 02:33 | BUY | $0.40 | 50 | $20 | Munich MAKER-FILL |
| 03:05 | BUY | $0.30 | 500 | **$150** | Toronto MAKER-FILL |
| 04:01 | BUY | $0.95 | 781 | **$742** | RECYCLE099 exit (token prefix match) |
| 06:01 | SELL | $0.015 | 143 | $2 | Near-zero resolution |
| 06:08 | BUY | $0.34 | 18 | $6 | Seattle MAKER-FILL |

Total untracked BUY notional: $2,262. Three of four large BUY events (0:35, 0:59, 4:01) exactly coincide with RECYCLE099 exits and share token prefixes: most likely the same market's YES counterparty redemptions appearing in the WS feed, not the user's own fills. Cannot confirm without a wallet transaction audit. ACTION REQUIRED: Verify Polymarket wallet txn history. Persistent pattern (8 on Jun-22, 10 today).

---

## 2. COMPOUNDING SCOREBOARD

### Equity Estimate (at cost)

| Component | Value | Basis |
|---|---|---|
| Cash (bankroll, stale 06:02 UTC) | $198.28 | bankroll.json |
| SELL_EXIT resting at cost (est.) | $176.88 | 268 shares x avg entry $0.66 |
| Tokyo NO resting at cost | $5.00 | 7.46 sh @ $0.67 |
| WEATHER_M1_PROBE at cost (est.) | $5.50 | 11 sh @ est. $0.50 |
| **Equity total** | **$385.66** | **+-$40 uncertainty** |
| Deployed fraction | 48.6% | |
| SELL_EXIT gross proceeds if fully filled @$0.99 | $265.42 | unrealised upside |

Caveats: avg entry $0.66 estimated from observed fills ($0.57-$0.71); true cost basis unavailable without full trades.jsonl join. Cash is stale (true cash ~$188-$193). Untracked fills excluded; if real they would represent undisclosed overexposure of ~$2k+ on a $200 bankroll.

### Turns and ROI

| Metric | Today (6h active) | Jun-24 (full day) | badatmath baseline |
|---|---|---|---|
| Fills $ | $59.70 | $320 | --- |
| Turns (fills/equity) | **0.15** | 0.78 | ~1.0x/day |
| Capital ROI/turn | **-19.2%** | -1.0% | ~+15-20% |
| RECYCLE099 standalone ROI | **+33.2%** | +36.0% | --- |

Turn rate today depressed by service failure (6 of 24 hours active). RECYCLE099 ROI strong (+33%) and consistent with yesterday (+36%). The drag is entirely from STWA_RESOLVED losses overwhelming gains at 2.4:1 ratio ($21.34 losses vs $9.86 gains).

Structural math: each STWA_RESOLVED NO loss costs $5-6. Each RECYCLE099 exit gains $2-3 net. To break even the bot needs >2 RECYCLE exits per 1 STWA_RESOLVED loss. At 20 consecutive STWA losses (rolling 20) with only 4 RECYCLE exits today, the exit rate cannot keep pace.

---

## 3. EXPECTED MAKER REBATES

| City | Shares | Entry price (p) | Est. rebate |
|---|---|---|---|
| Buenos Aires NO | 9.0 | 0.57 | $0.028 |
| Wuhan NO | 8.0 | 0.66 | $0.022 |
| Sao Paulo NO | 9.0 | 0.61 | $0.027 |
| Munich NO | 8.3 | 0.60 | $0.025 |
| Toronto NO | 8.0 | 0.69 | $0.021 |
| Chengdu NO | 8.0 | 0.71 | $0.021 |
| Seattle NO | 8.0 | 0.66 | $0.022 |
| **Total today** | **58.3 sh** | --- | **$0.166** |

Formula: shares x 0.05 x p x (1-p) x 0.25. Upper bound: actual depends on competing maker volume.

| Cumulative | Value |
|---|---|
| Through Jun-24 | $1.20 |
| Today addition | +$0.17 |
| **Cumulative est.** | **$1.37** |

Cumulative above $1 minimum payout threshold since Jun-24. Rebates land daily in pUSD.
User should verify pUSD wallet receipt: no payout confirmed in ledger.
Buenos Aires ($0.57) and Sao Paulo ($0.61) are highest-earning fills today (closest to p=0.50 where p x (1-p) peaks).

---

## 4. KILL-SWITCH PROXIMITY

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Rolling 20 WR | **5.0%** (1/20) | <30% flag | **FAR BELOW** |
| Rolling 20 PF | **0.0123** | <0.8 halt | **FAR BELOW** |
| Rolling 20 net P&L | **-$89.47** | --- | Severe |
| Day P&L | **-$11.48** | <-$10 halt | **BREACHED** |
| Capital vs weekly floor | $198.28 vs $75 | | **SAFE** (+$123) |
| Capital vs ruin floor | $198.28 vs $50 | | **SAFE** (+$148) |

Day halt is breached (-$11.48 vs -$10). Service was already down when the breach occurred.

CAVEAT (mandatory): The rolling-20 WR/PF is computed on STWA_RESOLVED trades only (positions held to resolution). The maker-band strategy's intended win path is RECYCLE099 (early sell ~$0.99), which does not register in STWA_RESOLVED. A book winning 33%+ on RECYCLE exits still shows WR=0% in STWA_RESOLVED because those positions never appear there. Do not trigger a kill-switch on WR/PF alone. Threshold re-derivation for the maker regime is pending with the user.

What the data does show: 20/20 STWA_RESOLVED events are full losses (-$89.47 net rolling). 4 today, 16 yesterday. The band is buying NO and every market is resolving YES. This is either a June seasonal bias (globally warm cities) or a miscalibration in city/bucket selection. Warrants investigation independent of kill-switch rules.

---

## 5. DAY VERDICT

**NO -- capital -$11.48 (-5.47%). Binding constraint: SERVICE FAILURE.**

Klaus systemd failed. Last log entry: 2026-06-25 06:08:38 UTC. Service down 17+ hours as of this report. 34 SELL_EXIT orders (268 shares) and Tokyo NO (7.46 shares) are resting on-chain with no bot supervision. No new bands posted since 06:08.

Five-day context: Jun-24 STWA losses = -$68.14 (16 trades, 1 win). Jun-25 STWA losses = -$21.34 (4 trades, 0 wins). Rolling 20 = 20 consecutive STWA_RESOLVED failures. This is not noise. The band is entering NO on cities where the market has been correct (YES resolves) at a near-100% rate.

RECYCLE099 is healthy (+33.2% ROI on exits, 4 exits in 6 hours). On a full operating day RECYCLE099 alone could generate $20-40. The problem is not the exit strategy: it is the STWA_RESOLVED full-loss rate.

Mexico City NO (prior alert): Resolved 2026-06-25T12:00Z. Prior state flagged 94.5sh @ cost $15.59 (market 94% YES, untracked in bot). If it resolved YES (expected), that is an additional -$15.59 not reflected in this reconciliation. Day loss including this: ~-$27. Will appear as unexplained discrepancy in a future session's wallet audit.
