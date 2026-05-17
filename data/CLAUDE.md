# Klaus — Persistent Context for Claude Code

## CRITICAL
This is not a simulation. Capital is real. Every parameter change has a dollar cost.

---

## SESSION START PROTOCOL
**MANDATORY:** Read `state_log.md` and internally summarize the last 10 entries before any analysis or code change. Never rely on prior session memory without verifying against the log. Append every session-altering decision (filter added/removed, threshold changed, rule changed, interpretation changed) with: `YYYY-MM-DD HH:MM UTC | SYSTEM/ASSET | exact change | reason + evidence`. Only log meaningful state changes, not commentary.

---

## CODING DISCIPLINE
1. **Think before coding** — state the goal and root cause before touching any file.
2. **Simplicity first** — the simplest change that achieves the goal is the right change.
3. **Surgical edits only** — change the minimum lines necessary. No cleanup, no refactoring, no extras.
4. **Goal-driven targets** — define what success looks like (metric, threshold, behaviour) before starting. If the target isn't clear, ask.

---

## ANTI-SYCOPHANCY RULES
1. **A losing trade is not explained away** — it is data. If the last 5 trades are losses, the strategy may be broken. Say so.
2. **Never conclude edge exists from fewer than 100 trades per bucket.** Never. At n=40–99: flag as a potential trend only, do not act.
3. **Optimistic commit messages are a red flag** — if writing "should improve WR" without n≥100 evidence, stop.
4. **If analysis contradicts data, data wins.** Not the thesis. Not the architecture. The data.
5. **Dry-run trades are not live trades.** Confirm DRY_RUN=false before analysing live performance.

---

## DATA PRIMACY PROTOCOL
Run before any analysis or code change:
```
1. cat logs/trades.jsonl       — count n_live, confirm dry_run=false
2. WR, profit factor, avg_win, avg_loss, fee_bleed
3. WR by asset, by UTC hour, by entry_price bucket
4. n≥100 per bucket for decisions. n=40-99: flag trends only. n<40: data collection mode, no changes
5. Kill switch triggered? If yes — halt before anything else
```

**Data integrity rules:**
- Zero values may mean "not computed" not "actually zero" — verify before acting
- n<100 per bucket = no conclusion for parameter changes. Block/unblock hours only at n≥100
- n=40–99 per bucket = flag as potential trend, highlight for monitoring, do not act
- Orphan sells (entry=0.0) are logging bugs — exclude from WR
- Cross-check reports against raw trades.jsonl before drawing conclusions

---

## CURRENT PARAMETERS
See `config.json` and `state_log.md` for active configuration. All parameter values are strategy-specific and subject to change.

---

## KILL SWITCHES & CAPITAL RULES
| Metric | Floor | Action |
|---|---|---|
| Win rate | >45% | Flag if <35% over 20 trades |
| Profit factor | >1.3 | Halt if <0.8 over 20 trades |
| Daily loss | — | Halt after -$10/day |
| Weekly bankroll | <$75 | Halt, full review |
| Ruin floor | <$50 | Shut down entirely |

Scale-up: raise stake only after WR >55% confirmed over 20+ live trades.

---

## ACTION TIERS
- **Tier 1 (autonomous)**: reads, stats, bug fixes with clear root cause, parameter changes ±20% with n≥100
- **Tier 2 (cite data in commit)**: parameter changes >±20%, new filters, disabling signals
- **Tier 3 (never without instruction)**: stake beyond defined tiers, kill switch thresholds, disabling trade logging

---

## INFRASTRUCTURE
- **VPS**: systemd unit `klaus` at `/root/Klaus`
- **Deploy**: `cd /root/Klaus && git pull && systemctl restart klaus`
- **Logs**: `tail -f /root/Klaus/logs/bot.log` or `journalctl -u klaus -f`
- **Dev branch**: `claude/find-lag-parameter-rFQ0N`

**Development workflow (NON-NEGOTIABLE):**
Claude edits locally → commits → pushes to dev branch → Claude SSHes into VPS to deploy. Never edit or commit on the VPS. Never `git checkout origin/...` on VPS. VPS only writes to `logs/`.

**Deploy command (run via SSH):**
```bash
ssh root@85.137.174.86 "bash -c 'git -C /root/Klaus pull && systemctl restart klaus && systemctl is-active klaus'"
```

---

## KEY DESIGN DECISIONS
- `current_price` in position monitor = bid (sell-side)
- `window_outcome_price` logged to `logs/post_exit.jsonl` (record_type="resolution"), not trades.jsonl — join by trade_id for resolution analysis

---

## POLYMARKET HOLE DETECTION

Mechanical executions to find bugs and critical inefficiencies in Polymarket. All require live data from logs/trades.jsonl and order book snapshots.

### TIER A — MECHANICAL (Guaranteed, zero prediction required)

**A1: Resolution Tie Bug (flat klines → deterministic YES)**
- Query: `kline_close == kline_open` (bipower_30s < 0.5 as proxy for flatness)
- Expected outcome: 100% of ties resolve YES (contract rule: close ≥ open → YES)
- Frequency baseline: ~1.17% of windows (SOL-heavy)
- Detection: flag all flat-market entries; measure empirical YES resolution rate per asset
- Next step: gate on real-time flatness detector (bipower_30s or realized_vol_1h)

**A2: Oracle Front-Run (Chainlink 35s lag + Binance feed)**
- Mechanics: at window_end_ts + 1s, read Binance 5m kline → result is deterministic
- Detection: `grep 'record_type.*resolution' logs/post_exit.jsonl | wc -l` to count resolved windows
- Mean oracle delay: 35.02s (std 0.21s, n=3678) — integer-second boundary only
- Data check: compare window_outcome_price (from Chainlink) vs Binance kline at T+0; should agree 99%+
- Note: DISABLED (commit b79fdad) — MMs cancel winning-side asks pre-close; cheap post-resolution asks are on losing side only

**A3: Post-Resolution Stale Ask Sweep**
- Mechanics: orphaned limit sells from early window persist after resolution
- Confirmed event: SOL UP bought at $0.01 (331 tokens) → $327 profit
- Detection: scan post_exit.jsonl for trades with entry_price < 0.05 and entry_ts > window_end_ts
- Frequency: rare (1 confirmed event in May backtest)

**A4: Neg-Risk Mechanical Arb (arb_sum < 1.0)**
- Query: arb_sum < 0.98 in final 35s of window (579 windows in backtest, avg 8.2% discount)
- Mechanics: atomic 2-leg execution (buy YES+NO, net short payout leg)
- Constraint: requires simultaneous fills on both sides
- Status: not yet implemented (data verified only)

### TIER B — STRUCTURAL BIAS (Probabilistic)

**B1: ETH YES Systematic Overpricing**
- Metric: ETH UP historical rate = 48.6% but market prices YES at 0.51
- EV: -2.4% for YES buyers; +2.4% for NO buyers (statistically significant)
- Detection: `analytics/eth_overpricing.py` — stratify by asset, measure ask_mid vs. realized outcome

**B2: MM Silence Gaps (orphaned stale quotes)**
- Detection: `grep 'ask_stale' logs/post_exit.jsonl | awk -F'[:,]' '{if ($3 > 30) print}' | wc -l`
- Max gaps observed: 245s, 210s, 171s (YES+NO pairs go offline simultaneously)
- Count: 114 gaps >30s; 16% of replay ticks have ask_stale >30s
- Next step: detect gaps >60s in real time, poll REST order book, take stale asks if available

**B3: Cross-Asset Oracle Synchrony**
- Correlation: BTC/ETH=0.575, BTC/SOL=0.469, ETH/SOL=0.525
- Observation: 64.1% of windows all 3 assets resolve same direction
- Oracle timing: all 3 assets resolve at identical delay (diff=0.00s mean)
- Implication: read all 3 Binance klines at T+0, coordinate multi-condition sweeps

**B4: Window-Close Large Orders**
- Detection: `analytics/order_size_drift.py` — measure avg_size in final 20s vs. open
- Observation: avg_size final 20s = $62.36 vs $20.15 at open (3× larger)
- Implication: informed actors increasing position size at close

**B5: Fee Cap Nonlinearity**
- Taker fee caps at $1 at ~$143 stake (DISCOVER ask 0.35). Above that, marginal fee = $0
- Current $5 stake: fee = $0.035/trade
- Implication: scale-up captures nonlinear fee savings above breakeven stake

### TIER C — PROTOCOL DETAILS

**C1: Tie Resolution Rule**
- Contract rule: `close >= open` → YES (not `close > open`)
- Implication: exactly-flat candles (open == close) resolve YES

**C2: Oracle Integer Second Boundary**
- Observation: Chainlink fires at integer seconds only (35s, 36s, 37s, never 35.3s)
- Execution: submit sweep order at exactly T+34s for tightest fill timing

**C3: Sibling Token MM Synchrony**
- Observation: YES+NO tokens always go offline together (same MM process, one RFQ)
- Implication: when gap starts, both sides unquoted simultaneously

**C4: ob_delta Depth Reconstruction**
- BBO events emit ask_top3 + bid_top3; enables book state reconstruction during MM silence
- DEPLOYED (commit f5b25af)

### TIER D — INFORMATION ASYMMETRY

**D1: VPIN (Informed Flow)**
- Metric: High VPIN → pnl_T15 = -0.45 vs Low VPIN = -0.79
- Status: available in _last_ext_signals; needs S2-universe validation (n≥100 per bucket)

**D2: Jump vs. Diffusion (bipower_30s)**
- Metric: Low bipower_30s → pnl_T15 = -0.52 vs High = -0.88
- Status: no real-time bipower feed; proxy = realized_vol_1h from ExternalSignal

**D3: Liquidation Cascade**
- DEPLOYED: data/shadow/liquidation.py persists Binance forceOrder events
- Location: logs/shadow/liquidation.jsonl
- Status: data accumulating; analysis pending

---

## MECHANICAL EXECUTION CHECKLIST

Before proposing any new Polymarket strategy:
1. ✅ Query: which TIER applies? (A=mechanical, B=structural, C=protocol, D=info-asymmetry)
2. ✅ Data: n≥100 confirmed instances in historical data (see `logs/post_exit.jsonl`)
3. ✅ Fill validation: sample 20 live execution windows, confirm entry/exit fills are available
4. ✅ Causation: prove the edge is not correlation to a known market bias (e.g., ETH overpricing)
5. ✅ Stop-loss: define max loss per window if edge fails (no open-ended holds)
6. ✅ Capital: size position to survive 5 consecutive failures without ruin
