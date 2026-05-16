# Klaus Agent Research Status

**Owner:** human + scheduled agents.
**Purpose:** prevent agents from re-investigating closed research families and to enumerate the open ones with their pre-registered thresholds.
**Updated:** 2026-05-16.

Agents fetch this via the data-mirror branch (`data/agent_context/research_status.md`). Treat as ground truth at fetch time. If you observe a research family here marked closed but think you have new evidence, raise it in your report — do not silently re-investigate.

---

## Strategy state

- Active strategy: **LDA** (late directional arb). All `signal_source=="LDA"`.
- Win metric: **`kline_pnl`**. `net_pnl` logging is broken; do not use.
- Dedup: **first-fire per `(condition_id, window_end_ts, rem_bucket)`**.
- Stake: flat $5; Kelly off (since 2026-05-15 15:00 UTC).
- Kill switches: disabled.
- Decision rule: COLLECTING until n>=100. Re-evaluate EV/CI then.
- Capital: see `data/bankroll.json`.

## Closed research families — do NOT re-investigate

| Family | Status | Reason |
|---|---|---|
| BOND strategy | retired 2026-05-10 | replaced by LDA |
| DISCOVER strategy | retired 2026-05-12 | replaced by LDA |
| SNIPER / MOM | retired | superseded |
| Oracle sweep (A1/A2/A3) | structurally broken | MMs cancel winning asks pre-close; flat→UP=coin flip |
| Copy-trade (REST polling) | falsified | REST snapshots 0% match rate vs tick truth; queue priority binds, not latency |
| REST-poll order book signals | falsified | book state stale beyond microstructure usefulness |
| Microstructure thesis (book-derived) | falsified | tick reconstruction collapsed it |
| Past-price Polymarket signals | null | proven non-predictive |
| Wallet copy-trading | infeasible at our latency | only sound wallet is tennis-arb (Eulhunter) |
| SNAP60, DISP, OFI-mid, C1, MPDRIFT signals | closed | full audit failed |
| 15m windows | blocked | per-asset BNC gates disabled |
| SOL trading | blocked 2026-05-15 | n=178 WR=53.4% net=-$791 |
| Tennis arb | stopped 2026-05-15 | per user instruction |
| Low-ask convexity | blocked | hold_path sampling bias unverified |

## Open research candidates

| Candidate | Status | Pre-registered n | Notes |
|---|---|---|---|
| BNC-decay re-check | shadow validated, NOT deployed | n>=2643 (already met) | Re-fetch signed Binance 5m return ~500ms post-eval; skip if reversed below -0.03%. WR 81.1%→84.3%, retains 93.3% of volume. Holds in every cell. Threshold -0.03% selected over -0.07%. |
| Late-collapse "crested wave" exits | open | n>=100 LDA losers | 27% of losers peaked profitable before crashing per prior research. Quantify $ lost; baseline for exit revision. |
| Cross-asset BNC signal | open | n>=100 per asset | Does BTC BNC predict ETH outcome? Unverified. |
| `binance_ret_15m_pct` direction agreement | open | n>=100 per (5m_dir, 15m_dir) cell | New shadow field added 2026-05-15; co-direction may predict durability. |
| Watchlist cell trajectories (40<=n<100) | continuous monitoring | promote at n>=100 | Auditor patches at n>=100. Scout flags drift between runs. |

## Shadow logger manifest

Files at `/root/Klaus/logs/shadow/`. Mirror copies today's `hot/<YYYY-MM-DD>/` files + a `data/shadow_summary.json` index.

| Logger | Pre-registered n | Schema | Status |
|---|---|---|---|
| exit_shadow | 500 | `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}` | active; validate PT0.95+30s exit |
| expo_shadow | 500 | `{ts, trade_id, candidate_gate, baseline_gate, would_fire}` | active; paired with exit_shadow |
| ExitPolicyShadow | 500 | live exit-rule rolling validation rows | active |
| discover_signal | n/a | DISCOVER recorder | logger may still write; DISCOVER strategy is OFF — flag rows >0 as orphaned |
| wallet_* | closed | wallet audit/replay artifacts | closed; don't analyze further |
| market_microscope_* | closed | one-off research outputs | closed |
| backfill/* | n/a | re-runs of historical replays | ignore in live validation |

## Action tiers (mirrors CLAUDE.md)

- **Tier 1 (autonomous, no PR review needed)**: read-only stats, bug fixes with clear root cause, parameter changes ≤±20% with n>=100.
- **Tier 2 (cite data in commit; PR)**: parameter changes >±20%, new filters, disabling signals.
- **Tier 3 (never without instruction)**: stake beyond defined tiers, kill switch thresholds, disabling trade logging.

Auditor operates at Tier 1–2; Scout at report-only (no Tier); Watchdog and Shadow Validator at report-only.

## Hard rules

1. Use `kline_pnl`; first-fire dedup. Anything else invalid.
2. n<100 per bucket = no parameter decision.
3. Never re-block a cell `state_log.md` shows user explicitly unblocked.
4. Never touch: stake, SOL block, vol_regime gate, exits in main.py.
5. n=40–99 = watchlist only, not patch.
6. `data/SNAPSHOT.md` ts older than 45min = mirror stale; report and exit.

## Update protocol

Update this file when:
- A research family transitions open → closed (or back)
- A shadow logger crosses its n threshold
- A new strategy lever is added
- A hard rule changes

Commit message: `agent_context: research_status — <one-line reason>`.
