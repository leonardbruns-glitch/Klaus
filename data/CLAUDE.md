# Klaus — Persistent Context for Claude Code

## WHAT THE BOT IS DOING RIGHT NOW
**Strategy: CAS_LOWASK (Cross-Asset Synchrony × Low-Ask)**

Signal: at T-60s remaining, check Binance 5m partial return for BTC/ETH/SOL. If 2 of 3 assets align (all ≥ THR_PCT in same direction) and the third confirms (same sign), buy the third asset's matching-direction token — but only if ask is cheap (0.05–0.50, extended to 0.60 with range_pos>0.8).

Edge: structural cheap-tail mispricing. When 2-of-3 are aligned, the lagging token is underpriced. WR ~52%, but payout asymmetry (+$0.80 win vs −$0.20 loss at avg ask $0.21) makes it +EV.

Exit: **hold to resolution**. No PROFIT_TARGET, no SL. Token resolves 1.0 (win) or 0.0 (loss) at window close.

PnL truth: if kline direction matches entry direction → `exit_price=1.0`, `net_pnl = shares × (1−ep)`. This is patched into trades.jsonl at resolution. BANKROLL_AUTO_CORRECT reconciles the wallet.

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
- Use `kline_pnl` (not `net_pnl`) as truth for CAS trades — it reflects resolution at 1.0/0.0
- `entered_correctly=True` → win; `entered_correctly=False` → loss; `null` → unresolved, fetch kline
- Orphan sells (entry=0.0) are logging bugs — exclude from WR
- EXPIRED_UNSOLD with `entered_correctly=null` must be backfilled via Binance kline before analysis
- Cross-check reports against raw trades.jsonl before drawing conclusions

---

## CURRENT PARAMETERS (updated 2026-05-19)
| Parameter | Value | Notes |
|---|---|---|
| Strategy | CAS_LOWASK only | Cross-asset synchrony, 5m windows |
| Entry window | rem 10–95s | Blocks [65,75) and [85,95) |
| Ask range | 0.05–0.50 | Extended to 0.60 when range_pos>0.8 |
| Synchrony threshold | THR=0.005 | Relaxed to 0.001 for H06/H21 |
| Stakes | BTC $15, ETH $15, SOL $3 | Fixed per-asset; partial fills accepted |
| Max concurrent | 2 | Across all assets |
| Blocked hours (global) | {1,2,3,5,14,16,18,21} UTC | Negative EV in shadow/live |
| Blocked hours (SOL) | {5,11,13,18,22,23} UTC | Additional SOL-specific blocks |
| Exit | Hold to resolution | No PT, no SL — token resolves 1.0 or 0.0 |
| PnL convention | exit_price=1.0 if correct direction | Patched at resolution via kline |

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
- CAS entries: one per asset per 5m window (`_fired_asset_windows` dedup)
- `bond_entry_class = "CAS_LOWASK"` on all CAS positions — filter by this, not `signal_source`
- `bond_outcome_direction` = "up" or "down" — the kline direction that makes this token win
- Resolution patching: EXPIRED_UNSOLD → exit_price corrected to 1.0/0.0 at kline resolution; bankroll NOT touched (BANKROLL_AUTO_CORRECT handles wallet)
- `current_price` in position monitor = bid (sell-side)
- Orphan recovery: timeout → query Polymarket position → restore tracking

---

## ANALYSIS SCRIPTS
```bash
python3 analytics/feedback.py             # 30-min diagnostic report
```
