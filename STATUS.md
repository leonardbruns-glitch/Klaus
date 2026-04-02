# Klaus — Current Status (updated every session)

## Last Updated
<!-- Update this every session: date, what changed, what's next -->
2026-04-02 — CLAUDE.md overhaul, MAX_TOKEN_ASK 0.62, PREARM 0.20, lag threshold 0.30

## Bankroll
<!-- Update after every session -->
- Starting capital: $100
- Current bankroll: unknown — read logs/trades.jsonl to compute
- Peak: unknown
- Drawdown from peak: unknown

## Live Trade Stats (update after reading logs)
- Total live trades (n): unknown
- Win rate: unknown
- Profit factor: unknown
- Fee bleed ratio: unknown
- Avg win: unknown
- Avg loss: unknown

## Current Parameters
| Parameter | Value | Last Changed |
|---|---|---|
| min_lag_5m | 0.30 | 2026-04-02 |
| min_lag_15m | 0.25 | 2026-04-02 |
| MAX_TOKEN_ASK | 0.62 | 2026-04-02 |
| PREARM_ELAPSED_MIN | 0.20 | 2026-04-02 |
| base_stake | $3 | — |
| max_open_positions | 2 | — |
| max_daily_loss | $10 | — |
| quiet_hours_min_delta | 0.10% | 2026-04-02 |
| active_hours_min_delta | 0.04% | — |

## Kill Switch Status
- [ ] Daily loss halt triggered
- [ ] Weekly floor ($75) breached
- [ ] Ruin floor ($50) breached
- [ ] WR <35% over 20 trades
- [ ] Profit factor <0.8 over 20 trades

## Open Positions
<!-- Update if bot stopped mid-session with open positions -->
None known

## Next Diagnostic Priority
1. Confirm n_live trades — if <20, data collection mode only
2. Check WR by hour from shadow_blocks.jsonl
3. Check fee bleed ratio
4. Verify DRY_RUN=false before analyzing live performance

## Infrastructure
- Bot running on: MacBook (local)
- VPS: NOT YET SET UP — QuantVPS Dublin $42/mo pending
- Branch: claude/investigate-zero-entry-price-lWxej
- Last commit: CLAUDE.md overhaul + parameter updates
