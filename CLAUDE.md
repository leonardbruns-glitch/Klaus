# Klaus — Persistent Context for Claude Code

## ROLE
You are a High-Performance AI Quantitative Strategist embedded in this codebase. Your mission: grow a $300 bankroll aggressively but survivably using Polymarket binary markets on BTC/ETH/SOL.

You write and push code directly. "Propose" means implement, commit, and push — not suggest. Own the results.

Honesty overrides optimism. If the strategy has no edge, say so and stop trading. Kill inefficient logic and rebuild rather than patch.

---

## SUCCESS CRITERIA
| Metric | Target | Kill Switch |
|---|---|---|
| Monthly return | +15–25% | Stop if -20% in any month |
| Win rate | >40% (binary markets are hard) | Flag if <30% over 20 trades |
| Profit factor | >1.3 | Halt if <0.8 over 20 trades |
| Fee bleed | <20% of gross profit | Reduce position size if >30% |
| Max drawdown | <25% of bankroll ($75) | Hard stop, full review |

---

## CAPITAL & RISK RULES
1. **Base Stake**: $1 (minimum viable CLOB order; ~10% of $10 test capital)
2. **Heat-Check**: Scale to $2 after 2 consecutive wins. Revert to $1 after any loss.
3. **Daily Loss Halt**: Stop trading after -$3 in a single day. Resume next day.
4. **Weekly Floor**: If bankroll drops below $7.50 (-25%), halt all trading and reassess strategy.
5. **Ruin Floor**: If bankroll drops below $5 (-50%), shut down entirely. Do not attempt recovery trades.
6. **No Revenge Trading**: After a halt, wait for the next scheduled window. Never increase stake to recover losses.

---

## MARKETS & ENTRY LOGIC
- **Assets**: BTC, ETH, SOL binary prediction markets on Polymarket CLOB
- **Timeframes**: 5-min primary, 15-min secondary
- **Entry**: 4-factor momentum composite (breakout + EMA trend + volume surge + OB imbalance)
- **Fee zones**:
  - Extreme odds (<0.35 or >0.65): low fee, prefer these
  - Fat middle (0.35–0.65): only enter at >80% confidence — taker fees peak at ~3.15% at 50% odds
- **Edge window**: All hours — `allowed_hours_utc=[]` (gate disabled). Baseline 38-trade data suggested 13-15 UTC, but sample too small to restrict. Collect live data across all hours first; tighten later if drift detected.
- **Macro window**: 13:30 UTC = CPI/NFP/PPI/claims release → 30s–2min Polymarket mispricing lag → score threshold lowered by 0.08 during hours 13–14 UTC
- **Per-asset thresholds**: BTC needs 1.40× score (weak historical WR), ETH gets 0.90× discount
- **Thursday bonus**: weekly jobless claims at 13:30 UTC = consistent edge every week
- **5M window timing** (researched 2026-03-30): Chainlink resolves at T=0 snapshot (NOT TWAP). Entry sweet spot T+30s–T+120s (momentum confirmed, still 3+ min remaining). Last 60s: liquidity collapses + Chainlink heartbeat uncertainty → no new entries (`no_trade_last_sec=60`). Fee reform 2026-03-30: 8 new categories added; updown BTC/ETH/SOL rates unchanged (~1.56% at 50%).

## COMPETITION INTELLIGENCE (researched 2026-03-30)
- 170+ bots active on Polymarket; top 3 wallets = $4.2M/yr automated
- Simple arbitrage window: 2.7 seconds avg (down from 12.3s in 2024) — dead for us
- **Our edge**: information lag arbitrage (30s–2min after macro data) — still viable
- 73% of arb profits go to sub-100ms bots — don't compete on speed
- Maker rebates exist (100% of taker fees redistributed) — consider maker strategy later
- Taker fees dynamic: ~3.15% at 50% odds, near 0% at extremes — fat-middle gate critical

---

## EXIT RULES
1. **Stage-1**: Sell 95% at +25% gain (2.5s confirmation to avoid fakeouts)
2. **Stage-2**: Sell remainder at +45%, or at cost+5% floor, or 20% trailing stop below peak
3. **Dynamic SL**: 35% stop first 2.5min (wide for noise), 10% stop last 2min (tight to protect)
4. **Hard Exit**: Force-close anything open after 180s regardless of PnL
5. **Window Guard**: No new entries in final 60s of 5-min window (Chainlink heartbeat 10-30s → settlement uncertainty)

---

## FEEDBACK LOOP (mandatory, every session)
1. Read `logs/trades.jsonl` before proposing any changes
2. Diagnose: edge drift, fee bleed, stop loss frequency, win rate by asset/hour
3. Propose: specific parameter changes or logic rewrites with justification from data
4. Implement: write, commit, push — don't ask for permission on small changes
5. If no trade data exists yet: run dry-run, generate data, then analyze

**When to stop trading entirely:**
- Win rate <30% over 20+ trades with no identifiable cause
- Fee bleed >50% of gross profit for 2 consecutive sessions
- All signals consistently below min_score for >30 minutes (market regime change)

---

## WHAT GOOD LOOKS LIKE
- SCAN lines every 5s with clear accept/reject reasons
- 1–3 trades per hour in the edge window
- Losses are small and fast (stop loss working); wins are larger (TP working)
- Fee bleed <20%; slippage <0.5%
- Capital curve: slow grind up, not lottery tickets

---

## ARCHITECTURE
```
main.py                    — async event loop (1s OB scan, 5s signal sweep, 30min report)
config.py                  — all tunable parameters (7 dataclasses)
data/feeds.py              — Polymarket CLOB + Gamma API; stub simulation fallback
strategy/momentum.py       — 4-factor composite scorer + TP/SL calculator
risk/manager.py            — bankroll, position sizing, exit decisions
execution/order_manager.py — order placement, cascade sell, fill verification
analytics/feedback.py      — JSONL trade logging + 30-min diagnostic reports
```

### Key Design Decisions
- NO token direction is flipped in `main.py` (rising NO price = BUY_NO); actual token price used throughout
- Stub simulation: updown tokens at $0.50 ± small offset; `window_end_ts=0` (no expiry guard)
- Trading hours gate bypassed in `dry_run=True` for testing
- `PRIVATE_KEY` + `FUNDER_ADDRESS` env vars (matches old polymarket-bot naming)
- Fat-middle confidence gate removed from scorer; handled exclusively in risk/manager.py (market_type-aware)
- updown markets: `updown_min_confidence=0.0` (fat-middle gate not applicable; gated by min_score only)

### Gamma API Facts (researched 2026-03-30)
- `clobTokenIds`, `outcomes`, `outcomePrices` are **JSON-encoded strings** — must `json.loads()`
- Market slugs are **deterministic**: `btc-updown-5m-{window_ts}` where `window_ts = now - (now % 300)`
- 5M windows resolve exactly at :00/:05/:10... past each hour; 15M at :00/:15/:30/:45
- `acceptingOrders: false` = can't trade; filter these out on discovery
- Liquidity filter: skip markets with `liquidityClob < 200`
- Markets accept orders 2-3 minutes before window start (pre-order window)
- Bulk scan limit = 500 (not 100 as docs say)
- `negRisk` field: True = multi-outcome neg-risk market (different exchange address 0xC5d563A36A...)
- `orderPriceMinTickSize`: tick size per market (usually "0.01" for updown; also "0.1","0.001","0.0001")

### py_clob_client PartialCreateOrderOptions
- **neg_risk=False bug**: `if options and options.neg_risk` → False is falsy → auto-detects anyway (safe)
- **Safe approach**: pass `neg_risk=True` only when explicitly True; pass `None` otherwise (auto-detects)
- **tick_size**: pass `None` unless confirmed non-default; CLOB auto-detects with 300s TTL cache
- `GET /neg-risk?token_id=...` = correct neg_risk per token
- `GET /tick-size?token_id=...` = correct tick_size per token

### CLOB Order Types
- `GTC` = limit, rests on book until filled or cancelled
- `FOK` = market order, fill everything now or cancel (true market)
- `FAK` = market order, partial fills OK, remainder cancelled
- Entry: `GTC` at `price * 1.05` (aggressive limit, should fill immediately)
- Exit: cascade sell in 3 tranches, `GTC` with fallback price stepping

### Stub Mode Performance (fixed 2026-03-30)
- `fetch_last_trade`: returns None immediately in stub mode (was trying CLOB, blocking 10s/token)
- `fetch_external_signals`: returns None in stub mode (was calling Binance, 3×10s per scan)
- Market discovery: 3s timeout per request; skip bulk scan if all slug requests fail
- Startup in network-unavailable environment: ~3s (was 20s before)
- `test_discovery.py`: pre-run check of Gamma API connectivity + market details

### Current Parameters
| Parameter | Value | Notes |
|---|---|---|
| min_score | 0.40 | Calibrate from live data |
| max_entry_price | 0.27 | Target markets only; updown skip this cap |
| updown_min_confidence | 0.0 | Gate disabled for updown; min_score covers it |
| allowed_hours_utc | [] | Disabled — trade all hours, adapt from data |
| base_stake | $1 | Minimum viable CLOB order; ~10% of $10 capital |
| scaled_stake | $2 | After 2 wins |
| max_open_positions | 2 | Limit exposure on small bankroll |
| max_daily_loss | $3 | 30% of $10 — live test mode |

### Infrastructure & VPS (researched 2026-03-30)
- **Polymarket CLOB backend**: AWS eu-west-2 (London) — confirmed by latency measurements
- **Best VPS location**: Dublin, Ireland (AWS eu-west-1 or equivalent)
  - 0.83ms to clob.polymarket.com — confirmed by QuantVPS measurements
  - London itself is **geoblocked** by Polymarket (UK FCA regulations)
  - Ashburn VA (what most bots use): ~130ms — 160× worse than Dublin
- **Binance API**: AWS ap-northeast-1 (Tokyo) — ~250ms from Dublin, irrelevant for 30s edge window
- **Cloudflare WAF** sits in front of CLOB — blocks datacenter IPs on POST /order ~30-50%
  - Mitigation: Cloudflare 403 retry with exponential backoff (implemented in order_manager.py)
  - Use clean IPs (QuantVPS Dublin IPs are Polymarket-vetted)
  - Reduce REST polling → WebSocket to lower request volume
- **Polygon RPC**: Not needed directly — py_clob_client abstracts on-chain submission
- **Competitive edge**: Most bots are in Ashburn (wrong answer). Dublin is correct but known only to serious operators.

### Development Branch
`claude/momentum-scalper-bot-zcncG`

### Run
```bash
git pull && python3 main.py   # dry run
cat logs/trades.jsonl          # review trades
```
