# Klaus — Persistent Context for Claude Code

## WHAT THE BOT IS DOING RIGHT NOW
**Strategy: TERMINAL** — buy YES tokens at ask 0.75–0.88 in the final 25–90s of 5m updown windows. Hold to TIME_EXIT at T-1s. Edge: high-probability tokens walking to 1.0 at resolution.

This is not a simulation. Capital is real. Every parameter change has a dollar cost.

---

## CODING DISCIPLINE
1. **Think before coding** — state the goal and root cause before touching any file.
2. **Simplicity first** — the simplest change that achieves the goal is the right change.
3. **Surgical edits only** — change the minimum lines necessary. No cleanup, no refactoring, no extras.
4. **Goal-driven targets** — define what success looks like (metric, threshold, behaviour) before starting. If the target isn't clear, ask.

---

## ANTI-SYCOPHANCY RULES
1. **A losing trade is not explained away** — it is data. If the last 5 trades are losses, the strategy may be broken. Say so.
2. **Never conclude edge exists from fewer than 20 trades.** Never.
3. **Optimistic commit messages are a red flag** — if writing "should improve WR" without n≥20 evidence, stop.
4. **If analysis contradicts data, data wins.** Not the thesis. Not the architecture. The data.
5. **Dry-run trades are not live trades.** Confirm DRY_RUN=false before analysing live performance.

---

## DATA PRIMACY PROTOCOL
Run before any analysis or code change:
```
1. cat logs/trades.jsonl       — count n_live, confirm dry_run=false
2. WR, profit factor, avg_win, avg_loss, fee_bleed
3. WR by asset, by UTC hour, by entry_price bucket
4. n≥20? If not — data collection mode, minimal changes only
5. Kill switch triggered? If yes — halt before anything else
```

**Data integrity rules:**
- Zero values may mean "not computed" not "actually zero" — verify before acting
- n<20 per bucket = no conclusion. Block hours/assets only at n≥20
- Orphan sells (entry=0.0) are logging bugs — exclude from WR
- Cross-check reports against raw trades.jsonl before drawing conclusions

---

## CURRENT PARAMETERS (updated 2026-04-26, n=397 Apr25+)
| Parameter | Value | Evidence |
|---|---|---|
| Strategy | TERMINAL only | 5m windows, ask 0.75–0.88, 25–90s remaining |
| BOND_CATASTROPHIC SL | -15% | SL sim peak +$63.44 net vs no-SL; 54% of losers resolve YES but EV of holding = -$1.36/trade due to payoff asymmetry |
| Ask range | 0.75–0.88 (all assets) | ETH cap 0.82 removed — avg_ep was stuck at 0.79 |
| Blocked hours BTC | {2,6,10,18,21} | Validated n≥20 per bucket |
| Blocked hours ETH/SOL | {6,10,18,21} | Validated n≥20 per bucket |
| BOND stake cap | $4.00 | User instruction 2026-04-26 |
| OB imbalance gate | \|imb\| ≥ 0.10 | Balanced OB WR=44% (n=9) |
| Windows | 5m only | 15m disabled |
| Exit primary | BOND_TIME_EXIT T-1s | asyncio precise timer |
| Exit fallback | BOND_DEADLINE T-3s | scan loop safety net |

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
- **Tier 1 (autonomous)**: reads, stats, bug fixes with clear root cause, parameter changes ±20% with n≥20
- **Tier 2 (cite data in commit)**: parameter changes >±20%, new filters, disabling signals
- **Tier 3 (never without instruction)**: stake beyond defined tiers, kill switch thresholds, disabling trade logging

---

## INFRASTRUCTURE
- **VPS**: systemd unit `klaus` at `/root/Klaus`
- **Deploy**: `cd /root/Klaus && git pull && systemctl restart klaus`
- **Logs**: `tail -f /root/Klaus/logs/bot.log` or `journalctl -u klaus -f`
- **Dev branch**: `claude/find-lag-parameter-rFQ0N`

**Development workflow (NON-NEGOTIABLE):**
Claude edits locally → commits → pushes to dev branch → user runs `git pull && systemctl restart klaus` on VPS. Never edit or commit on the VPS. Never `git checkout origin/...` on VPS. VPS only writes to `logs/`.

---

## KEY DESIGN DECISIONS
- TERMINAL entries: one per asset per window (`_terminal_traded_windows` dedup)
- `current_price` in position monitor = bid (sell-side) — SL fires vs bid, not mid
- `window_outcome_price` logged to `logs/post_exit.jsonl` (record_type="resolution"), not trades.jsonl — join by trade_id for resolution analysis
- ETH cap removed: 0.82→0.88 because ETH avg_ep was stuck at 0.7941 below the profitable zone
- SL payoff asymmetry: at entry 0.84, win=+$0.86, loss=-$4.50 → need 84% YES resolution to justify holding through -15% drawdown

---

## ANALYSIS SCRIPTS
```bash
python3 analytics/check_catastrophic.py   # BOND_CATASTROPHIC breakdown by asset/hour
python3 analytics/sl_simulation.py        # SL threshold optimisation + recovery analysis
python3 analytics/feedback.py             # 30-min diagnostic report
```
