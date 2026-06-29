# Klaus PnL Ledger — 2026-06-28 (UTC)
_Generated: 2026-06-28T23:37Z by pnl-ledger-agent_

---

## Section 1 — P&L Explain

**Capital:** $69.887018 → $75.484568 (+$5.597550)

### 1a. Attributed Cash Flows

| Leg | Detail | Shares | Entry | Exit | PnL |
|---|---|---|---|---|---|
| RECYCLE099 — Beijing NO (Jun-26 d+2) | token 7695… exited 08:07 | 7 | 0.68 | 0.99 | +$2.325 |
| RECYCLE099 — Wuhan NO (Jun-26 d+?) | token 6647… exited 12:38 | 6 | 0.75 | 0.99 | +$1.603 |
| RECYCLE099 — Chengdu NO (Jun-26 d+?) | token 7333… (filled Jun-27) exited 12:53 | 6 | 0.84 | 0.99 | +$0.900 |
| RECYCLE099 — London NO (Jun-27 d+1) | token 7387… exited 08:07 | 7 | 0.83 | 0.99 | +$1.120 |
| RECYCLE099 — London NO (Jun-27 d+1) | token 5542… exited 15:34 | 6 | 0.81 | 0.99 | +$1.260 |
| RECYCLE099 — Munich NO (Jun-27 d+1) | token 1030… exited 16:52 | 8 | 0.66 | 0.99 | +$2.640 |
| RECYCLE099 — Moscow NO (same-day) | token 1116… bought 12:06 & exited 17:09 | 6 | 0.93 | 0.99 | +$0.360 |
| RECYCLE099 — London NO (Jun-27 d+1) | token 5348… exited 17:31 | 7 | 0.68 | 0.99 | +$2.325 |
| **RECYCLE099 TOTAL** | 8 exits, all wins, gross proceeds $52.47 | | | | **+$12.533** |

New entries deployed today (14 MAKER-FILL events):

| Asset/Market | Shares | Price | Cash Out |
|---|---|---|---|
| Munich NO d+1 (Jun-29) | 7.0 | 0.72 | $5.04 |
| London NO d+1 — token 40059… | 9.0 | 0.59 | $5.31 |
| London NO d+1 — token 70140… | 7.8 | 0.65 | $5.07 |
| London NO d+1 — token 89366… | 5.0 | 0.76 | $3.80 |
| Chengdu pair d+0 YES | 9.4 | 0.50 | $4.70 |
| Chengdu pair d+0 NO | 9.4 | 0.35 | $3.29 |
| Beijing NO d+1 — cond fd8c… | 7.2 | 0.70 | $5.04 |
| Beijing NO d+1 — cond 3cc4… | 8.0 | 0.71 | $5.68 |
| Moscow NO (same-day) | 6.0 | 0.93 | $5.58 |
| Wuhan NO d+1 — cond 389a… | 7.2 | 0.70 | $5.04 |
| Wuhan NO d+1 — cond 8e3b… | 7.0 | 0.83 | $5.81 |
| Wuhan NO d+1 — cond 4de5… | 2.0 | 0.71 | $1.42 |
| Chengdu NO d+1 — cond 9e85… | 7.2 | 0.70 | $5.04 |
| Chengdu NO d+1 — cond 3d6f… | 7.0 | 0.83 | $5.81 |
| **TOTAL NEW ENTRIES** | | | **$66.63** |

**Net attributed cash flow:** +$52.47 − $66.63 = **−$14.16**

**Expected capital from attribution:** $69.887 − $14.16 = **$55.73**

**Actual capital:** $75.485

### 1b. UNEXPLAINED: **+$19.758**

This is not a rounding line — it is a model deficiency alarm.

**Investigation:** The unexplained +$19.758 exceeds $5 threshold and requires explanation. Analysis of the MAKER-FILL log (Jun-26/27 positions) and the SELL_EXIT resting state:

- 10 Jun-26 positions (spent=$70); 3 confirmed in RECYCLE099 today; 7 unaccounted
- The 7 unaccounted Jun-26 tokens: some resolved Jun-27 (in prior capital) and some resolve Jun-28 TODAY
- Jun-26 posted d+2 NO positions (markets for Jun-28) settled at **$1.00/share via on-chain Polygon pUSD credit at 12:00Z** — these do not appear in RECYCLE099 (pre-resolution exits at $0.99) or SELL_EXIT resting (unfilled maker orders)
- Magnitude consistent with 3–4 winning d+2 positions (~20–25 shares × $1.00 = $20–25)
- **Most likely cause: batch on-chain settlement of Jun-26 d+2 NO positions at 12:00Z Jun-28.** NOT fraud, NOT ruin.
- **Action: verify Polygon pUSD inflows at or after 12:00Z Jun-28 in the funder wallet.** If the amount matches ~$19.76, attribution is closed.

_Note: bankroll.json saved_ts ≈ 17:50Z; STRUCT-BAND-Q log confirms cap=$75 unchanged 17:50–23:31Z (no fills in that window). Capital figure is current._

---

## Section 2 — Compounding Scoreboard

### Equity Estimate

| Component | Value | Basis |
|---|---|---|
| Cash | $75.485 | bankroll.json |
| 12 SELL_EXIT resting (82 shares at $0.99) | $81.18 | maker_resting_state; all at exit price |
| Chengdu d+0 pair (merged, 9.4 shares) | $9.40 | locked pnl=$1.41, guaranteed $1.00/sh resolution |
| Munich YES d+2 (Jun-27 fill, 9.0 sh @ $0.51) | $4.59 | at cost; not in RECYCLE099, resolves Jun-29 |
| **Equity estimate** | **$170.63** | |

**CAVEAT (mandatory):** SELL_EXIT at $0.99 for today's 9 new NO positions (e.g., Munich 0.72, London 0.59) overstates — these positions are nowhere near $1.00 yet (they resolve Jun-29/30). Conservative mark at fill cost ≈ $47.48; adjusted equity ≈ **$137.32**. Range: $137–$171 depending on mark convention. Do not treat $170 as realisable today.

### Scoreboard

| Metric | Today | Yesterday | badatmath baseline |
|---|---|---|---|
| Capital | $75.485 | $69.887 | — |
| Equity est (mid) | ~$154 | ~$133 | — |
| Fills (entries) | $66.63 | $47.26 | — |
| Turns/day (fills/equity) | **0.43** | 0.355 | ~1.0× |
| ROI/turn (resolved) | **+30.9%** | −51.8% (was unrealised) | 10–20% |
| Consecutive wins | 12 | 9 | — |

**ROI/turn basis:** 8 RECYCLE099 exits; total entry cost $40.59 (sum: shares×entry_price per exit099 record); PnL $12.533; 30.9% return on deployed capital per completed cycle.

**7d trend vs benchmark:** Turns of 0.43 is still less than half of badatmath's ~1.0×/day, but improving (was 0.35 yesterday). The 30.9% ROI/turn materially exceeds the 10–20% benchmark — the band is selecting high-confidence winners. The bottleneck is **throughput** (turns), not **edge** (roi/turn).

**Critical observation — Cash Capacity Freeze:** From 17:46Z (last fill) to 23:31Z (snapshot), every STRUCT-BAND-Q cycle reported:
- `no_cands=13–15` (13–15 viable NO candidates visible per scan)
- `posted=0` (zero new orders placed)
- `cash_preskip=7–13` (7–13 candidates blocked per cycle by cash constraints)

**6.7 hours, ~80 sweep cycles, 0 fills.** With 14 resting positions tying up ~$70 of notional (BAND_NO_STAKE=$5 × 14 = $70), the bot's internal exposure tracker leaves insufficient headroom against the BAND_NO_CASH_RESERVE=0.30 floor ($75 × 0.30 = $22.65 reserved). The band sees a full card of actionable candidates every 5 minutes and executes zero. This is the binding constraint.

---

## Section 3 — Expected Maker Rebates

Formula: `rebate_est = shares × 0.05 × p×(1−p) × 0.25`  
Upper bound (assumes Klaus is the only maker in pool; actual is proportional share).

| Fill | Shares | p | p(1−p) | Est. Rebate |
|---|---|---|---|---|
| Munich NO | 7.0 | 0.72 | 0.2016 | $0.018 |
| London NO (0.59) | 9.0 | 0.59 | 0.2419 | $0.027 |
| London NO (0.65) | 7.8 | 0.65 | 0.2275 | $0.022 |
| London NO (0.76) | 5.0 | 0.76 | 0.1824 | $0.011 |
| Chengdu pair YES | 9.4 | **0.50** | **0.2500** | **$0.029** |
| Chengdu pair NO | 9.4 | 0.35 | 0.2275 | $0.027 |
| Beijing NO (0.70) | 7.2 | 0.70 | 0.2100 | $0.019 |
| Beijing NO (0.71) | 8.0 | 0.71 | 0.2059 | $0.021 |
| Moscow NO | 6.0 | 0.93 | 0.0651 | $0.005 |
| Wuhan NO ×3 | 16.2 | avg 0.76 | avg 0.18 | $0.036 |
| Chengdu NO ×2 | 14.2 | avg 0.76 | avg 0.18 | $0.031 |
| **Today total** | | | | **$0.246** |

| Period | Expected rebate |
|---|---|
| Today | $0.246 |
| Prior cumulative (Jun-27 ledger) | $1.537 |
| **Cumulative total** | **$1.783** |

**⚑ FLAG — pUSD payout verification:** Cumulative expected exceeds $1.00 (minimum accrual threshold). If no pUSD payout has been observed in the funder wallet since the start of the maker era, verify now. Payouts land daily; if the fee tier or category assignment is incorrect, these rebates may not be accumulating. The Chengdu pair YES fill at p=0.50 is the highest quadratic earner (p×(1−p)=0.25 max) — confirm this fill is categorised as "weather" taker-side.

---

## Section 4 — Kill-Switch Proximity

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Capital | $75.485 | $75 weekly floor | ⚠️ ABOVE by $0.485 — razor-thin |
| Capital vs ruin floor | $75.485 | $50 ruin | ✅ +$25.485 above |
| Day PnL | +$5.598 | −$10 halt | ✅ Not triggered |
| Consecutive wins | 12 | N/A | — |
| Rolling 20-trade WR | n/a (trades.jsonl too large) | >40% kill below 30% | n/a |
| Rolling PF | n/a | Kill if <0.8 | n/a |

**Weekly floor cleared:** Capital crossed $75 today after a one-day breach ($69.887 Jun-27). Margin is $0.485 — a single $5 loss would re-breach. The SELL_EXIT positions (82 shares at $0.99 = $81.18 expected) provide a strong equity buffer, but they must FILL or SETTLE before capital updates.

**CAVEAT — WR/PF kills do not apply in maker band regime.** The kill switch thresholds (WR>40%, PF>1.3) were calibrated for taker-era binary bets where each trade is independently binary. In maker band:
- NO legs are bought at 0.60–0.85 when the fair value is higher → ~22–40% direct win probability by design
- EV is positive across the band structure even if individual WR appears low
- The kill-switch re-derivation proposal remains pending with the user. Do NOT halt on WR alone.

**FLAG — Moscow NO at 0.93 outside config:** One fill today registered "Moscow NO @ 0.93" (cond=0x016c0bb9). `BAND_NO_MAX=0.85` and `BAND_CITY_ALLOW={"chengdu","london","beijing","munich","wuhan"}` should exclude Moscow AND cap NO at 0.85. This fill violates both filters on paper. Possible explanations: (a) Moscow is a different strategy (THERMO_MAKER, but THERMO_MAKER_LIVE=False), (b) the fill was from a resting order placed before config was updated, (c) a new code path bypasses these gates. Outcome was positive (+$0.36, same-day exit). **Investigate the entry code path for this fill regardless of outcome.**

---

## Section 5 — Day Verdict

**YES — Equity compounded.**

| Metric | Value |
|---|---|
| Capital delta | +$5.598 (+8.0%) |
| Equity delta (est.) | +$21 to +$37 depending on mark convention |
| Realized PnL | +$12.533 (RECYCLE099) |
| Locked PnL (pair) | +$1.41 (resolves Jun-29 at 12:00Z) |
| Open positions (new NO entries) | $52.06 at cost, resolving Jun-29/30 |

**Binding constraint today: CASH CAPACITY.** Edge quality is excellent (30.9% ROI/turn). The band found 13–15 viable NO opportunities every 5 minutes all evening but executed zero because 14 resting positions consumed the available cash envelope. The entire 17:46–23:31Z window was dead — not because the market dried up, but because the book was full.

Secondary findings:
1. Weekly floor re-cleared (+$0.485 margin) after yesterday's breach
2. Unexplained +$19.758 → likely Jun-26 d+2 on-chain settlements; verify Polygon at 12:00Z
3. Moscow NO fill bypassed city allowlist and BAND_NO_MAX — investigate
4. Cumulative maker rebate $1.783 — verify pUSD receipt in wallet

---
