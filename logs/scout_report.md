# Alpha Scout Report — 2026-04-28 00:42 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (SSH port 22 CLOSED)**

All four investigations require live `trades.jsonl` from the VPS at `85.137.174.86`.
Retrieval was not possible:

| Method | Result |
|---|---|
| SSH port 22 | CLOSED (connect_ex code 11 — connection refused) |
| SSH port 2222 | CLOSED |
| HTTP :80 | 403 Forbidden (Nginx/CF WAF running, no data exposed) |
| HTTPS :443 | 403 Forbidden |

Local `logs/bankroll.json`: `total_trades=0`, `capital=109.66` — local dev repo, no live trades.

This is the **third consecutive session** where the VPS has been unreachable via SSH:
- Audit 2026-04-27 18:42 UTC: "SSH timed out after 10s"
- Audit 2026-04-28 00:10 UTC: "SSH timed out (15s timeout, two attempts)"
- Scout 2026-04-28 00:42 UTC: Port 22 actively refused (not timeout — CLOSED)

**The SSH port changed from "timeout" (filtered) to "refused" (actively closed).** This indicates the SSH daemon may have crashed or been killed, not a firewall issue.

---

## Investigation 1: Cross-Exchange Lead-Lag
**HYPOTHESIS:** Positive Binance spot momentum in 5s before entry (`pre_entry_momentum_pct > 0`) predicts YES resolution.
**RESULT:** n=0 live TERMINAL trades retrieved. Cannot compute.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: n/a** — precondition (data access) failed, not the hypothesis.

---

## Investigation 2: Tick Count Filter
**HYPOTHESIS:** Low `term_tok_tick_count_5s` (dead market) entries underperform active-market entries.
**RESULT:** n=0. Cannot bucket by tick count.
**PROPOSED_GATE:** Deferred — requires n≥20 per bucket.
**CONCLUSION: INCONCLUSIVE**

---

## Investigation 3: Dead Drift Signature
**HYPOTHESIS:** Entries with `|term_token_delta_5s| < 0.005` (flat token price) underperform active entries.
**RESULT:** n=0. Cannot compare dead-drift vs active.
**CONCLUSION: INCONCLUSIVE**

---

## Investigation 4: Asset-Specific Edge
**RESULT:** n=0 per asset (BTC/ETH/SOL). Minimum threshold n≥20 not met.
**CONCLUSION: INCONCLUSIVE** — Failure criteria explicitly met: n < 20 per asset.

---

## Collateral Findings: Logging Gap Risk

Even if VPS SSH is restored, there are two known gaps in `trades.jsonl` coverage:

1. **Apr 27 08:20–19:18 UTC (≈11h gap):** `trades.jsonl` logging was broken (TypeError in `log_trade()`). Fixed in commit `20510c4`. Trades during this window exist only in `bot.log` and require `reconstruct_trades.py` to recover.

2. **Fields added after Apr 27 07:36:** `term_tok_tick_count_5s` and `term_token_delta_5s` were added in commit `1b933fb`. Any trades from before that timestamp will have these fields missing (will appear as `0`). Do not mix pre/post field cohorts in Investigation 2 and 3 analysis.

3. **Binance kline fields after Apr 27 18:58:** `pre_entry_momentum_pct` (kline-based) was upgraded in commit `8866057`. Pre-upgrade records used spot-price delta — same field name, different calculation. Investigation 1 should filter `ts_open ≥ 1745784000` (2026-04-27 19:00 UTC) for kline-quality momentum data.

---

## Priority Signal for Next Implementation
**No actionable signals this cycle — continue data collection.**

Immediate infrastructure fix required before any scout analysis is possible:

```
PRIORITY 1: Restore VPS SSH access
  - Check VPS provider console (85.137.174.86) — is the VM still running?
  - SSH daemon may have crashed: sudo systemctl restart sshd (via console)
  - Port 22 returning REFUSED (not timeout) = sshd process likely down

PRIORITY 2: Verify bot is still trading
  - Once SSH restored: systemctl status klaus
  - Check bot.log tail for recent TERMINAL ENTRY lines
  - If bot stopped after logging fix: restart, wait 48h for n≥20 data

PRIORITY 3: Run reconstruct_trades.py for gap window
  - python3 analytics/reconstruct_trades.py --since "2026-04-27 08:20"
  - cat logs/trades_recovered.jsonl >> logs/trades.jsonl
  - Re-run scout after reconstruction
```

Minimum viable data to unblock all 4 investigations: **n=80 live TERMINAL trades** (20 per bucket × 4 buckets for tick-count analysis, the most segmented investigation).

At the Apr 26 rate of n=201/day, this requires approximately **10 hours** of live bot operation after SSH is restored and logging is confirmed working.
