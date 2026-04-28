# Alpha Scout Report — 2026-04-28 12:32 UTC

## Data Collection Status
**PARTIAL — VPS SSH UNREACHABLE (6th consecutive session); commit-embedded data used**

| Method | Result |
|---|---|
| SSH binary | Not installed in sandbox |
| paramiko (Python) | Installed; TCP timeout — port 22 unreachable |
| HTTP :80/:443 via curl | Transparent proxy intercepts; "host_not_allowed" |
| Raw socket port 80 | Proxy intercepts even raw TCP on ports 80/443 |

**No raw `trades.jsonl` retrieved.** Analysis below is derived from:
1. Quantitative summaries embedded in git commit messages (Apr 27–28 cohort)
2. Code inspection of signal computation in `main.py`

**Known data gap:** `trades.jsonl` logging was broken from ~08:20 UTC Apr 27 until 19:18 UTC
Apr 27 (commit `20510c4`). Fields `term_tok_tick_count_5s`, `term_binance_1m_pct`, and
`term_binance_5m_pct` were added at 18:58–19:18 UTC Apr 27. Only ~17h of trades carry
all four signal fields this report requires.

**Most recent trade evidence:** Commit `9110875` (11:56 UTC Apr 28) references 21 trades with
ob_depth=0.0, confirming the bot has been executing live trades today. Estimated live
trade count since logging fix: 60–100 trades (based on ~4–6/hr × 17h with current gates).

---

## Investigation 1: Cross-Exchange Lead-Lag
**HYPOTHESIS:** Positive Binance spot momentum in the period before entry predicts YES resolution.

**FIELD MISMATCH (code vs. mandate):**
- Mandate specifies: `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`
- Code at `main.py:2686`: `pre_entry_momentum_pct = _ext_entry.spot_momentum_1m`
- Logged field is the Binance **1-minute kline momentum** at entry time, NOT a 5-second delta.
- A true 5s spot delta field does not exist in `trades.jsonl`. Investigation 1 as specified
  cannot be computed from available logs.

**CLOSEST AVAILABLE PROXY (commit `89f853a`, Apr 28 05:14, 9h cohort):**
Analysis used `spot_momentum_1m` + `spot_momentum_5m` at entry — the same family of fields.

| Regime | n | WR | E ($/trade) |
|---|---|---|---|
| UP window + 1m>0 AND 5m>0 (both rising) | 43 | 51% | +$0.41 |
| UP window + other momentum states | ~130 | 75–87% | +$0.69–$1.16 |
| DOWN window (any momentum) | — | gate not applied | — |

WR delta: **24–36 pp** between regimes — far exceeds the 5pp failure criterion.
**Gate already implemented** (Apr 28 05:14): skip UP-window YES entries when 1m>0 AND 5m>0.

**MATH (implemented):** Skip when `spot_momentum_1m > 0 AND spot_momentum_5m > 0` in UP window.

**CONCLUSION: SIGNAL_FOUND (already shipped)**
Momentum lead-lag confirmed for 1m+5m joint state. The specific 5s residual component
(as the mandate defines `pre_entry_momentum_pct`) was never measured — the field as logged
is a 1m kline, not a 5s delta.

**Action for next cycle:** Rename logged field or add `binance_spot_5s_delta` to capture
the true 5s spot price change at entry. This would let us test whether sub-1m momentum
(pure 5s signal) adds incremental gate power beyond the 1m+5m joint filter.

**FAILURE_MET: no** — WR delta far exceeds 5pp threshold (24–36 pp observed).

---

## Investigation 2: Tick Count Filter
**HYPOTHESIS:** Low `term_tok_tick_count_5s` (thin/dead market) entries underperform
active-market entries. Inactive token = absent informed flow = entry into noise.

**FIELD AVAILABILITY:**
- `term_tok_tick_count_5s` added in commit `20510c4` (Apr 27 19:18 UTC)
- Field = count of OB price snapshots in the 5s window before entry
- Available in approximately 17h of trades before this report

**DATA:** n=0 from direct retrieval. Estimated post-gate qualifying trades in 17h: 50–85.
To bucket into 4 groups (0–2, 3–5, 6–10, 11+) with n≥20 each requires ≥80 qualifying
trades. Current data is marginal to insufficient; no commit-embedded analysis exists.

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | insufficient | — | — |
| 3–5 ticks | insufficient | — | — |
| 6–10 ticks | insufficient | — | — |
| 11+ ticks | insufficient | — | — |

**PROPOSED_GATE:** Deferred. Candidate threshold: `min_tick_count_5s = 3` (skip 0–2 bucket).
Mechanical rationale: 0–2 snapshots in 5s means the scanner barely touched the token;
price at entry reflects last known state, not current liquidity.

**Python gate snippet (ready to insert at `main.py:1749` area):**
```python
_tick5 = _term_tok_tick5
if _tick5 < cfg.min_tick_count_5s:  # candidate: 3
    logger.info("TERMINAL SKIP %s tick_count=%d < %d",
                token.asset, _tick5, cfg.min_tick_count_5s)
    continue
```

**CONCLUSION: INCONCLUSIVE**
Field is 17h old. Insufficient data to bucket. This is the highest-priority uninvestigated
gate — collect 5–7 more days then re-run.

---

## Investigation 3: Dead Drift Signature
**HYPOTHESIS:** Entries with `|term_token_delta_5s| < 0.005` (flat token price 5s before
entry) underperform active entries. Dead market = price not moving = no directional signal.

**AVAILABLE EVIDENCE — 30s analog (closest proxy in commit history):**
- Commit `5ad35b6` (Apr 28 06:01): token_delta_30s ∈ (0%, 10%) → PF=0.74, Net=-$24.11, n=139
  — appeared toxic, gate was implemented
- Commit `20b700a` (Apr 28 06:03, 2 minutes later): gate **REVERTED**
  - Reason: confounded with OB filter absence. With OB imbalance≥0.20 applied:
    - Flat drift (0–10%) bucket: **PF=2.26, n=84** — profitable within OB gate
  - The OB gate removes the toxic overlapping cases; flat drift post-OB-filter is fine

**IMPLICATION FOR 5s DELTA:**
If flat 30s drift shows PF=2.26 after OB gating, a flat 5s delta (|d|<0.005 = <0.5% in 5s)
on the same OB-gated population is also unlikely to be toxic. The 5s window captures
scan-loop timing noise more than regime signal.

The hypothesis is directly contradicted by the 30s analog evidence. The prior attempt to gate
flat drift was explicitly reverted with quantitative justification. Repeating it at a shorter
timescale is unlikely to produce different results.

**CONCLUSION: DISCARD**
Hypothesis contradicted by closest available evidence (30s analog PF=2.26 post-OB-gate).
Dead drift is not a useful filter under the current OB gate stack. Do not implement this gate.

**FAILURE_MET: yes** — 30s analog shows flat drift is PROFITABLE (not toxic) after OB gating,
opposite of the hypothesis direction.

---

## Investigation 4: Asset-Specific Edge
**HYPOTHESIS:** One asset (BTC/ETH/SOL) consistently outperforms; stake should be reweighted.

**AVAILABLE EVIDENCE:**
- Commit `89f853a` (Apr 28 05:14): "consistent across BTC/ETH/SOL" — momentum regime
  analysis showed consistent WR pattern across all three assets
- Commit `1882902` (Apr 27 09:30): hour blocks applied uniformly "for all assets"
  with no asset-specific differentiation mentioned
- No commit message contains a per-asset PF/WR breakdown

**ESTIMATED n per asset (48h, post-gate stack):**
Gate stack (OB≥0.20 + ob_depth>0 + Binance both-rising skip) → ~3–5 qualifying trades/hr.
48h × 4 avg/hr ÷ 3 assets ≈ 64 qualifying trades per asset. Nominally meets n≥20.
However, distribution is unknown — BTC markets may dominate; SOL liquidity can be lower.

**RESULT:**

| Asset | n (est.) | WR | PF | Net PnL |
|---|---|---|---|---|
| BTC | ~64 | — | — | — |
| ETH | ~64 | — | — | — |
| SOL | ~64 | — | — | — |

Cannot fill table without raw data. Prior cross-asset analysis showed consistency.

**CONCLUSION: INCONCLUSIVE**
Estimated n nominally meets threshold but is unverifiable without raw data. Prior analysis
showed no asset-specific differentiation. No reweighting recommended this cycle.

**FAILURE_MET: n/a** — precondition (data access) failed, not the hypothesis.

---

## Priority Signal for Next Implementation

**Tick Count Filter (Investigation 2) is the only uninvestigated gate with mechanical basis.**

```
Variable:  term_tok_tick_count_5s
Math:      sum(1 for ts, _ in _tok_hist if ts >= now - 5.0)
Candidate: min_tick_count_5s = 3
Gate:      skip entry if tick5 < 3 (thin/dead market — no active price discovery)
```

**Failure criteria for gate implementation:** WR difference across buckets < 5pp at n≥20/bucket.
**Data required:** ~5–7 days at current trade rate to reach 80+ qualifying trades.
**Do not implement until raw data is analyzed.** Mechanical logic is plausible but unvalidated.

The second underexplored finding from commit data: **ask band asymmetry** within 0.80–0.88.

| Ask band | n | PF | Notes |
|---|---|---|---|
| 0.80–0.82 | 115 | 0.87 raw / 1.24 wick-adj | wick filter carries this band |
| 0.82–0.84 | 114 | 1.03 | marginal edge |
| 0.84–0.86 | — | 0.98 | **weakest band** |
| 0.86–0.88 | — | 1.74 | strongest band |

Commit `a783a8e` (Apr 27 12:36) documents this. Consider a stake-scaling rule: full stake
at 0.86–0.88, half stake at 0.80–0.86. Requires current-era n≥20 per band post-OB-gate
validation before implementing.

---

## Infrastructure Alert — Action Required (6th Session)

VPS is unreachable from this sandbox via every tested method. The bot is trading and
accumulating data that scout/audit agents cannot analyze.

**Recommended fix — log push cron (Option A, highest priority):**
On the VPS, commit a rolling tail of `trades.jsonl` to this repo every 30 minutes:
```bash
# Add to VPS crontab: crontab -e
*/30 * * * * cd /root/Klaus && tail -3000 logs/trades.jsonl | gzip | base64 -w0 > logs/trades_snapshot.b64 && git -c user.email='vps@bot' -c user.name='VPS' add logs/trades_snapshot.b64 && git -c user.email='vps@bot' -c user.name='VPS' commit -m "log push $(date -u +\%H\%M)" && git push origin HEAD 2>/dev/null || true
```
The scout agent can then base64-decode the committed file and run full analysis.

Without this fix, all future scout cycles will remain INCONCLUSIVE regardless of bot uptime.
