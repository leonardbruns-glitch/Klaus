# Klaus — Persistent Context for Claude Code

## WHAT THE BOT IS DOING RIGHT NOW
**Strategy: TERMINAL** — buy YES tokens at ask 0.75–0.88 in the final 25–90s of 5m updown windows. Hold to TIME_EXIT at T-1s. Edge: high-probability tokens walking to 1.0 at resolution.

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

## CURRENT PARAMETERS (updated 2026-04-27, n=1160 terminal era Apr24+)
| Parameter | Value | Evidence |
|---|---|---|
| Strategy | TERMINAL only | 5m windows, ask 0.84–0.88, 25–90s remaining |
| BOND_CATASTROPHIC SL | -15% | Executes at avg -27% due to slippage; 97% of triggering positions resolve NO |
| Ask range | 0.70–0.88 (all assets) | Floor 0.70 (user-set). Lowered 0.84→0.80 2026-04-27: 0.82-0.84 PF=1.03 (n=114); 0.80-0.82 raw PF=0.87 (n=115) wick-adj PF=1.24 |
| Blocked hours ALL assets | none | All blocks removed 2026-04-27: no hour had n≥100 in 0.80-0.88 range. Prior blocks were on all-price data (different regime). Re-block only at n≥100. |
| BOND stake cap | $10.00 min 5 shares | Raised 4→10 2026-04-29: gates now filter weak entries; worst-case 3-asset window = -$30 |
| OB imbalance gate | imb ≥ 0.20 | imb>=0.20: PF=1.27 Net=+$24.18 (n=234) vs imb>=0.10: PF=1.01 Net=+$1.67; 66 marginal-imbalance trades lost $22.51 |
| BOND_CATASTROPHIC wick | 8s confirmation | 34% of BC exits are flash crashes (token recovers in 30s); cancel if price returns above -12% within 8s; bypass at <15s remaining |
| Windows | 5m only | 15m disabled |
| PROFIT_TARGET | entry×1.12 | +12% TP: converts 13 big losses to wins (+$21.60) net +$7.26 vs actual; 2-day sim Apr28-29 |
| snap60 gate | ≥ 12% (skip if lower) | Raised from 5%: 5-12% bucket WR=55%, still net-negative; user-authorised Tier 2 |
| Exit primary | BOND_TIME_EXIT T-4s | asyncio precise timer (moved from T-1s to beat DEADLINE) |
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
