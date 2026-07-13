# Klaus PnL Ledger — 2026-07-13
**Generated:** 2026-07-13T23:37Z (scheduled day-end run)
**Snapshot age:** 22h 46m (last push: 2026-07-13T00:51:35Z) — STALE ✗ → **ABORT**
**System status:** `active` ✓ (bot uptime from 2026-07-11T22:06:15Z, now day 2)

---

## ⚠ ABORT — SNAPSHOT STALE (22h 46m > 6h threshold)

This is the **second consecutive ABORT day** (Jul 12 aborted at 21h stale; Jul 13 at 22h 46m stale). The data-mirror push cadence is structurally broken for the 23:37Z report slot: the mirror appears to snapshot once at ~00:51Z each day, yielding a guaranteed ~22h gap by report time. No intraday data after 00:51Z is available. **The data-mirror must be re-scheduled to push hourly or at 23:00Z, or this report will abort every night indefinitely.**

Full-day PnL cannot be attributed from snapshot data alone. The sections below use the most recent reliable sources:
- `bankroll.json` saved at **2026-07-13T00:00:09Z** (23h 37m before report time)
- `state_log.md` entries through **2026-07-12T19:20Z** (28h before report time)
- `maker_fills_recent.log` through **2026-07-12T17:10Z** (31h before report time)
- Shadow band_struct: only through **2026-07-13T00:49:54Z** (22h 47m before report time)

Numbers below reflect the midnight-UTC snapshot, not end-of-day.

---

## Section 1 — P&L Explain (best-effort, midnight-UTC snapshot)

### Capital Chain

| Event | Time (UTC) | Capital / Equity |
|---|---|---|
| Last real PnL report | 2026-07-10T23:37Z | $163.164 (all-cash) |
| Jul 11 22:06Z equity (state_log) | 2026-07-11T22:06Z | $205.76 = $143.34 cash + $62.42 open ladder shots |
| Jul 12 daily_start (bankroll.json) | 2026-07-12T00:00Z | $165.730 |
| Jul 12 intraday (state_log 19:20Z) | 2026-07-12T19:20Z | ~$120 tracked (includes open shots at cost) |
| **Jul 13 snapshot (bankroll.json)** | **2026-07-13T00:00Z** | **$103.824** |
| **Change vs Jul 10 real report** | | **−$59.34 (−36.4%)** |
| **Jul 12 alone (start→midnight)** | | **−$61.91 (−37.4%)** |

### Attribution

| Source | PnL | Notes |
|---|---|---|
| trades.jsonl closes Jul 7–13 | $0.00 | Zero rows with ts_close in this window |
| RECYCLE099 (exit099_live.jsonl) | $0.00 | No file present for Jul 7–13 |
| Sprint_ladder (state_log) | −$? | Jul 12 ladder fires visible: Toronto ~$16.42 deployed; prior shots at cost $62.42 at Jul 11 22:06Z; resolves not in trades.jsonl |
| Jul 12 untracked maker fills | ~−? | SELL NO 41.87 sh @0.40 + BUY YES 33.72 sh @0.47 (TAKER) + BUY 5.88 sh @0.52 (MAKER) + SELL 7.64 sh @0.48 (MAKER) + BUY 31 sh @0.52 (TAKER) — all UNTRACKED (no bot tracker entry) |
| Jul 11 ladder shots resolving | +$22.39 (implied) | $143.34 cash Jul 11 22:06Z → $165.73 Jul 12 start: difference = +$22.39 net from overnight resolution |
| **UNEXPLAINED** | **−$59.34** | Exceeds $5 threshold — investigation below |

### UNEXPLAINED = −$59.34 — Investigation

|UNEXPLAINED| = $59.34 >> $5 threshold. This is not noise.

**Most likely causes (ranked):**

1. **Sprint_ladder losses (PRIMARY):** The Jul 12 state_log entry at 19:20Z shows "Tracked ~$120 vs ruin_floor $89.16" and confirms "Toronto FIRED $16.42 today." The Jul 11 state_log confirmed 2 open shots at cost $62.42 (London $40.03 + MexCity $22.39 at restated cost). Jul 12 daily_start = $165.73. If both Jul 11 shots resolved poorly overnight plus new Jul 12 shots lost, a $61.91 single-day loss is consistent. Ladder lifetime as of Jul 10: 17 resolved, 7W/10L net ≈+$117 redemption-basis — but that predates Jul 12. The -$40.90 ladder alert flagged in Jul 11 gate-keeper commit now appears confirmed.

2. **STWA-family resolutions not in trades.jsonl (SECONDARY):** STWA fills appear in trades.jsonl only at resolution. Zero resolution rows for Jul 7–13 suggests either no STWA positions opened, or they were placed pre-restart and resolved without being tracked in the live session. The Jul 12 untracked fills (SELL NO @0.40, 41.87 sh = $16.75 notional received; TAKER BUY YES @0.47, 33.72 sh = $15.85 cost; TAKER BUY @0.52, 31 sh = $16.12 cost) total ~$32 in taker buy costs that represent UNTRACKED real-capital deployment. These are from resting orders placed pre-Jul-11-restart that filled post-restart against a new tracker state. **This is a MODEL DEFICIENCY — the UNTRACKED FILL warnings confirm the bot's tracker missed these fills after restart; the positions existed on-chain but were invisible to risk management.**

3. **Manual flows (POSSIBLE):** Cannot rule out — bankroll is not authoritative per schema notes. FLAG: if no manual deposit/withdrawal occurred, the −$59.34 is fully bot-driven.

**Model deficiency note:** The 20 untracked CONFIRMED fills on Jul 12 represent material capital movement (~$32 taker cost + maker fills) with zero risk management awareness. Tracker state lost at the Jul 11 22:06Z restart did not recover from the CLOB's resting order state.

---

## Section 2 — Compounding Scoreboard

**Equity estimate (caveat-heavy):**

| Component | Value | Confidence |
|---|---|---|
| Cash (bankroll.json 00:00Z) | $103.824 | HIGH — from bankroll file |
| Open positions at cost | Unknown | Mirror has no open_positions; state_log 19:20Z had "~$120 tracked" including shots; at midnight it may be $0 or residual |
| **Equity estimate** | **$103.82 (lower bound)** | Assumes no open shots at midnight; uncertain |

**Caveat:** The Jul 11 equity of $205.76 included $62.42 in open shots. If ladder shots fired Jul 12 remain open at midnight, actual equity could be higher than $103.82 (cash) — but the state_log context at 19:20Z suggests shots were in-flight. This estimate is the cash floor only.

| Metric | Value | Notes |
|---|---|---|
| Equity est. | $103.82 | Cash only; open shots unknown |
| Deployed fraction | ~0% (band dark) | BAND_LIVE=False, STWA disabled |
| Fills today (Jul 13 data) | $0 known | No activity after 00:49Z snapshot |
| Turns/day (Jul 13) | 0 | No fills |
| ROI/turn (Jul 13) | N/A | |
| Badatmath benchmark | ~1.0 turn/day at 10–20%/turn | We are at 0 turns for 7th consecutive day |

**7-day trend:** Band has been dark since Jul 6 (BAND_LIVE=False). Jul 7–13 realized fills = $0 from engine. Only sprint_ladder and MIN_LOCKOUT_LIVE are live. This is not compounding — it is capital drawdown from ladder shots with a broken tracker.

---

## Section 3 — Expected Maker Rebates

| Source | Expected Rebate | Formula |
|---|---|---|
| Jul 12 untracked MAKER fills: SELL NO @0.40, 41.87 sh | $0.13 | 41.87 × 0.05 × 0.40 × 0.60 × 0.25 |
| Jul 12 untracked MAKER fills: BUY @0.52, 15.49 sh total | $0.075 | 15.49 × 0.05 × 0.52 × 0.48 × 0.25 |
| Jul 12 untracked MAKER fills: SELL @0.48, 7.64 sh | $0.024 | 7.64 × 0.05 × 0.48 × 0.52 × 0.25 |
| **Jul 12 new estimate** | **$0.22** | Upper bound — competing makers reduce actual share |
| Cumulative carried (Jul 10) | $3.17 | |
| **Cumulative expected** | **$3.39** | |

**Notes:**
- The fat-middle SELL NO @0.40 (p=0.40, 1−p=0.60) and SELL @0.48 (near mid) are the highest-earning legs by p*(1-p). The TAKER fills earn no rebate.
- Cumulative expected rebate = **$3.39 > $1 min accrual**. Polymarket rebates land daily in pUSD. **ACTION FOR USER: verify whether any pUSD rebates have been received to date.** Given Jul 12's activity, at least one daily accrual should have posted if the wallet is eligible. No payout receipt has been recorded in any observed log.
- Note: these are UNTRACKED fills — rebate may not be attributed to the bot's wallets correctly if orders were placed in a different session state.

---

## Section 4 — Kill-Switch Proximity

**CAVEAT:** WR/PF thresholds were specified for the taker era. Maker YES legs win ~22% by design at 4–5× payoff. Rolling 20-trade WR and PF are computed from all-time trades.jsonl (last 20 resolved). Do NOT halt on WR alone; a kill-switch re-derivation for the maker era is pending with the user.

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Capital vs weekly floor ($75) | $103.82 | Halt if <$75 | **CLEAR** — $28.82 buffer |
| Capital vs ruin floor ($50) | $103.82 | Stop if <$50 | **CLEAR** — $53.82 buffer |
| Day PnL vs −$10 halt (Jul 13) | $0 known | Stop if <−$10/day | **CLEAR** (no activity) |
| Day PnL vs −$10 halt (Jul 12) | ~−$61.91 | Stop if <−$10/day | **BREACHED** — Jul 12 loss far exceeds daily halt |
| Rolling 20 WR (trades.jsonl) | 40.0% (8/20) | Flag if <30% | CLEAR on WR threshold |
| Rolling 20 PF (trades.jsonl) | 0.08 | Halt if <0.8 | **⚠ CRITICAL BREACH** |
| BAND_LIVE | False | | Dark — 7th day |

### Rolling 20 Detail

Last 20 closed trades (trades.jsonl, all 2026-07-06):

| # | PnL | Direction |
|---|---|---|
| 1–6 | +$0.49 to +$0.83 | Small wins |
| 7 | −$4.41 | Loss |
| 8 | −$3.96 | Loss |
| 9 | −$3.96 | Loss |
| 10 | −$3.55 | Loss |
| 11 | +$0.91 | Win |
| 12 | −$1.01 | Loss |
| 13 | **−$24.65** | **Large loss** |
| 14 | −$4.14 | Loss |
| 15 | −$0.08 | Small loss |
| **GROSS WIN** | **$4.68** | |
| **GROSS LOSS** | **$58.25** | |
| **PF = 0.08** | | **Kill threshold: 0.8** |

**Kill-switch PF alarm:** PF = 0.08 is 10× below the 0.8 halt threshold. However, ALL 20 trades are from 2026-07-06 (the wind-down day) — this is historical stale data from a single catastrophic session, not current engine behavior. The engine has had zero new resolves since Jul 6 (band dark). The PF alarm is **technically valid but context-dependent**: it reflects the Jul 6 cluster of band maker fills that resolved against us (winner's curse, now confirmed in Jul 11 EVOLVE). The band that generated these trades is disabled. **Reporting proximity, not recommending halt** — per the maker-era caveat and the fact that the band responsible for these fills is now off.

---

## Section 5 — Day Verdict

**Jul 13 (to midnight UTC):** Equity **flat** (no activity) at $103.82 cash. No fills, no resolves, no attributed PnL. Bot running but band dark day 7, all STWA paths disabled, sprint_ladder is the only active live path. Binding constraint: **BAND_LIVE=False** (equity below 50%·30d-HW; EVOLVE review required to re-enable).

**Structural verdict on Jul 12:** −$61.91 loss from $165.73 start is the largest single-day loss since Jul 8 (−$43.78 Guangzhou shot). Primary driver is sprint_ladder shots that resolved adversely + pre-restart untracked MAKER fills that constitute an unmanaged capital outflow. The tracker restart bug is a MODEL DEFICIENCY that must be fixed before any new MAKER or band activity.

**Three-day view (Jul 10→13):** −$59.34 (−36.4%) from last real report. All from non-engine paths (ladder + untracked fills). Engine itself silent. This is not edge drift — it is pure capital bleed from un-gated variance paths.

**Data-mirror stall — CRITICAL OPERATIONAL FLAG:**  
Two consecutive ABORT days. The snapshot cadence (once at ~00:51Z) is incompatible with a 23:37Z report. Unless the data-mirror push is rescheduled, this report will abort every day indefinitely. Recommend: add a cron at 22:00Z or 23:00Z on the VPS to push to data-mirror. Without this, the day-end PnL ledger is permanently blind.
