# Klaus Agent Research Status

**Owner:** human + scheduled agents.
**Purpose:** single source of truth for scheduled agents (Scout, Auditor, Watchdog, Shadow Validator). Enumerates current strategy state, what's closed, what's open, and exactly how each agent must consume data.
**Updated:** 2026-05-16 12:50 UTC.

> Agents MUST treat this file as ground truth at fetch time. Read it BEFORE doing any other work. If you observe something in the live data that contradicts this file, raise it in your report — do not silently re-investigate a closed family or invent new mandates.

---

## 0. DATA FETCH PROTOCOL — DO THIS FIRST (mandatory)

**SSH to the VPS is blocked from agent containers.** Do not try `ssh root@…`, `scp`, or `rsync`. They will fail. Past agent reports falsely claimed "VPS unreachable, 63rd session" — those reports are useless. The fix has been live for ≥1 week: the VPS pushes a fresh data snapshot to the `data-mirror` branch on GitHub every 15 minutes.

Every agent must start with these exact commands (or equivalent):

```bash
git fetch origin data-mirror
mkdir -p /tmp/k && cd /tmp/k
for f in SNAPSHOT.md trades.jsonl bankroll.json state_log.md \
         lda_status.txt lda_config.txt system_status.txt \
         CLAUDE.md shadow_summary.json integrity_report.json; do
    git show origin/data-mirror:data/$f > $f 2>/dev/null || true
done
git show origin/data-mirror:data/agent_context/research_status.md > research_status.md 2>/dev/null
# Shadow hot files (today's <10MB JSONLs):
git ls-tree -r origin/data-mirror --name-only -- data/shadow/ \
  | while read p; do git show origin/data-mirror:$p > "$(basename $p)" 2>/dev/null; done
```

**Pre-flight checks (all four agents):**
1. `SNAPSHOT.md` `snapshot_ts` must be ≤ 45 minutes old. If older → mirror is stale, report `MIRROR_STALE`, EXIT.
2. `integrity_report.json` `blocks_agent_run` must be `false`. If `true` → report `DATA_POLLUTED` with the issue keys, EXIT.
3. The klaus HEAD shown in `SNAPSHOT.md` must match `git rev-parse origin/<dev-branch>` within 1 commit. Otherwise → `CODE_DESYNC`.

If any pre-flight fails, do not run analysis. Report the failure and exit zero-state.

---

## 1. Strategy state (live)

- **Active strategy:** LDA (late directional arb). All `signal_source == "LDA"`.
- **Win metric:** `kline_pnl` (Polymarket YES tokens pay $1/share at resolution). `net_pnl` is unreliable for unsold/RESOLVED_NO paths; do not use for WR/EV.
- **Dedup:** first-fire per `(condition_id, window_end_ts, rem_bucket)`. Per-trade WR inflates due to multi-entry; per-(asset, window, bucket) is canonical.
- **Stake (2026-05-16):** `$5.00` flat at every hour EXCEPT H14 and H18 → `$10.00` (2x stake for highest-EV hours per LDA audit n=19 each, mean EV +$1.50/+$1.87).
- **Kill switches:** disabled.
- **Decision rule:** parameter changes require n≥100 per bucket. n=40–99 = watchlist only. n<40 = collect.
- **Capital source of truth:** `data/bankroll.json` `capital` field. `daily_start_capital` field is stale; ignore.

### Bucket definitions (rem_bucket = code; B-label = user)
| rem range | code rem_bucket | user label |
|---|---|---|
| [0, 60)s | 0 | B1 |
| [60, 120)s | 1 | B2 |
| [120, 180)s | 2 | B3 |
| [180, 300)s | 3 | B4 |

### Live gate set (mirror of `data/lda_config.txt`)
- `BLOCKED_HOURS_UTC = {0, 1, 2, 3, 19}` (H23 partial-unblocked 2026-05-16; only B2 fires at H23)
- `_ALL_BLOCKED_LATE = {3, 5, 6, 7, 12, 15, 23}` (rem > 120 → blocks B3+B4)
- `_ALL_BLOCKED_LATE_B1 = {4, 5, 12, 13, 15, 16, 18, 20, 21}` (B2 hour blocks)
- `_ALL_BLOCKED_B3 = {4, 9, 10, 11, 13, 21}` (B4 hour blocks — added 2026-05-16)
- `_ETH_BLOCKED_B1 = {1, 2}`, `_ETH_BLOCKED_LATE = {0,8,9,13,16,21,22}`
- `_BTC_BLOCKED_B1 = {13}`, `_BTC_BLOCKED_LATE = {8}`, `_BTC_BLOCKED_B3 = {1,4,18,21,23}`
- H23 B1 (inline), H04 B3 (inline), ETH H16 B2 with ask<0.80 (inline)
- Ask gates: B1 [0.60,0.90), B2 [0.75,0.80), B3 [0.55,0.85), B4 [0.55,0.80)
- Adaptive BNC floor: 0.07% at B1, 0.10%/0.05%/0.07% by ask zone at B2-B4
- SOL fully blocked. 15m windows fully blocked.

---

## 2. Closed research families — do NOT re-investigate

| Family | Status | Reason |
|---|---|---|
| BOND strategy | retired 2026-05-10 | replaced by LDA. `signal_source == 'BOND'` filter = n=0 — do not run audits keyed to BOND fields |
| DISCOVER strategy | retired 2026-05-12 | replaced by LDA |
| SNIPER / MOM | retired | superseded |
| Oracle sweep (A1/A2/A3) | structurally broken | MMs cancel winning asks pre-close; flat→UP=coin flip |
| Copy-trade (REST polling) | falsified | REST snapshots 0% match rate vs tick truth; queue priority binds, not latency |
| REST-poll order book signals | falsified | book state stale beyond microstructure usefulness |
| Microstructure thesis (book-derived) | falsified | tick reconstruction collapsed it |
| Past-price Polymarket signals | null | proven non-predictive |
| Wallet copy-trading (general) | infeasible at our latency | only sound wallet was tennis-arb (Eulhunter) |
| SNAP60, DISP, OFI-mid, C1, MPDRIFT signals | closed | full audit failed |
| 15m windows | blocked | per-asset BNC gates disabled |
| SOL trading | blocked 2026-05-15 | n=178 WR=53.4% net=-$791 |
| Tennis arb | stopped 2026-05-15 | per user instruction |
| Low-ask convexity | blocked | hold_path sampling bias unverified |

---

## 3. Open research candidates (Auditor + Scout focus on these)

| Candidate | Status | Pre-registered n | Notes |
|---|---|---|---|
| BNC-decay re-check | shadow validated, deployed 2026-05-13 | live | Re-fetch signed Binance 5m return ~500ms post-eval; skip if reversed below -0.03%. Watch live retention vs shadow (93.3% expected). |
| Late-collapse "crested wave" exits | open | n≥100 LDA losers | 27% of losers peaked profitable before crashing per prior research. Quantify $ lost; baseline for exit revision. |
| Cross-asset BNC signal | open | n≥100 per asset | Does BTC BNC predict ETH outcome? Unverified. |
| `binance_ret_15m_pct` direction agreement | open | n≥100 per (5m_dir, 15m_dir) cell | Shadow field added 2026-05-15; co-direction may predict durability. |
| H14/H18 2x stake performance | open | n≥20 live at $10 stake | Validate the 2026-05-16 2x boost holds at live stake. Monitor variance vs $5 baseline. |
| B3 H13 + H16 candidate blocks | watchlist | n≥40 per cell | Negative EV at n=6/n=10; awaiting more data before promotion. |
| Watchlist cell trajectories (40≤n<100) | continuous monitoring | promote at n≥100 | Auditor patches at n≥100. Scout flags drift between runs. |

---

## 4. Per-agent runbook

All four agents pre-flight per §0. Below is the role-specific behavior after pre-flight.

### 4a. Scout (every 12h) — report-only, no Tier
- **Goal:** read recent commits and shadow data; flag drift in watchlist cells; surface new patterns that warrant investigation.
- **Inputs:** `lda_status.txt`, `shadow_summary.json`, `state_log.md`, current commits.
- **Outputs:** `logs/scout_report.md` (overwrite), commit message `Scout report YYYY-MM-DD HH:MM UTC`.
- **Banned actions:** code edits, patches, parameter recommendations on n<40.
- **Skip if:** pre-flight failed, OR last Scout commit < 8h ago (avoid noise).

### 4b. Auditor (every 6h) — Tier 1-2
- **Goal:** scan watchlist cells; emit patches for cells crossing n≥100 thresholds with statistically clean evidence; otherwise "no patch required."
- **Mandate fields (LDA, not BOND):**
  | Old (BOND) | Current (LDA) — use these |
  |---|---|
  | `pre_entry_momentum_pct` | `binance_ret_5m_pct` (primary signal) |
  | `term_tok_tick_count_5s` | `ask_stale_s` |
  | `term_token_delta_5s` | `tok_delta_5s` |
  | `binance_price_at_entry` | `binance_spot` |
  | `ob_imbalance` | `ob_imb_top3` |
- **Patch authority:** Tier 1 (parameter ±20% with n≥100) and Tier 2 (cite data in commit). Never Tier 3.
- **Outputs:** `logs/audit_report.md` (overwrite); if patching, separate commit on dev branch with cited evidence.
- **Skip if:** pre-flight failed; OR no cell crosses n≥100 since last run.

### 4c. Watchdog (continuous — recommended every 5–15 min)
- **Goal:** detect operational failures fast.
- **Alerts (write `logs/watchdog_state.json`; commit only when alert toggles):**
  | Alert | Trigger |
  |---|---|
  | `MIRROR_STALE` | `SNAPSHOT.md` ts > 45 min old |
  | `BOT_DOWN` | `system_status.txt` says klaus inactive |
  | `CAPITAL_DROP` | `bankroll.capital` dropped >25% vs prior_capital |
  | `CAPITAL_RUIN` | `bankroll.capital` < $50 |
  | `TRADE_LOOP_SILENT` | last trade ts (from `trades.jsonl` tail) > 2h ago AND we're in an open hour |
  | `ROLLING_DRAWDOWN` | last 20 trades net < -$10 |
  | `STALE_AUDIT_PR` | open Auditor PR > 24h |
  | `SHADOW_LOGGER_STALLED` | any non-closed logger in `shadow_summary.json` has `mtime` > 30min stale |
- **Output:** commit message `Watchdog YYYY-MM-DDTHH:MM:SSZ: OK — N alerts` (or per-alert details).

### 4d. Shadow Validator (every 12-24h) — report-only
- **Goal:** for each pre-registered shadow logger that has crossed its n threshold, run validation analysis and flag whether the candidate clears EV/CI bars.
- **Inputs:** `data/shadow/*.jsonl` for open shadow loggers (see §5).
- **Output:** `logs/shadow_validator_report.md` (overwrite), commit `Shadow Validator YYYY-MM-DD HH:MM UTC`.
- **Skip if:** no logger crossed its threshold since last run.

---

## 5. Shadow logger manifest

Files at `/root/Klaus/logs/shadow/`. Mirror copies today's `hot/<YYYY-MM-DD>/` <10MB files + a `data/shadow_summary.json` index.

| Logger | Pre-registered n | Schema | Status |
|---|---|---|---|
| `exit_shadow` | 500 | `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}` | active; validate PT0.95+30s exit candidate |
| `expo_shadow` | 500 | `{ts, trade_id, candidate_gate, baseline_gate, would_fire}` | active; paired with exit_shadow |
| `exit_policy_shadow` | 500 | rolling exit-rule validation rows | active |
| `discover_signal` | n/a | DISCOVER recorder | DISCOVER strategy is OFF — any new rows are orphaned; ignore |
| `market_timeline` | n/a | per-window OB+spot+features sampler | active; primary backtest source |
| `gate_trace` | n/a | per-tick gate decision trace | active; LDA gate audit |
| `hold_path` | n/a | per-fill peak/trough trajectories | active; exit candidate evaluation |
| `ob_delta` | n/a | OB tick deltas | active; microstructure |
| `binance_trade` | n/a | Binance aggTrade WS dump | active; signal feature source |
| `wallet_*` | closed | wallet audit/replay artifacts | closed; don't analyze further |
| `market_microscope_*` | closed | one-off research outputs | closed |
| `backfill/*` | n/a | re-runs of historical replays | ignore in live validation |

---

## 6. Action tiers (mirrors CLAUDE.md)

- **Tier 1 (autonomous, no review):** read-only stats; bug fixes with a clear root cause; parameter changes ≤±20% with n≥100.
- **Tier 2 (cite data in commit; open PR):** parameter changes >±20%; new filters; disabling signals.
- **Tier 3 (NEVER without explicit user instruction):** stake beyond defined tiers, kill switch thresholds, disabling trade logging.

Auditor operates at Tier 1–2. Scout, Watchdog, Shadow Validator are report-only (no Tier).

---

## 7. Hard rules

1. Use `kline_pnl` and first-fire dedup. Anything else is invalid.
2. n<100 per bucket → no parameter decision. n=40–99 → watchlist only. n<40 → collect.
3. Never re-block a cell that `state_log.md` shows the user explicitly unblocked.
4. Never touch: stake, SOL block, exits in `main.py`, kill-switch thresholds.
5. `SNAPSHOT.md` ts older than 45 min → mirror stale; report and exit.
6. If `integrity_report.json` says `blocks_agent_run: true` → exit immediately with `DATA_POLLUTED`.
7. Do not attempt SSH. Use the data-mirror branch exclusively. See §0.

---

## 8. Common failure modes (and the correct response)

| Symptom | Correct response |
|---|---|
| `ssh: connection refused / not found` | You're not supposed to use SSH. Re-read §0. Fetch from `origin/data-mirror`. |
| `signal_source == 'BOND'` returns n=0 | BOND was retired. Re-read §1 and §4b mandate-field translation table. |
| Bankroll snapshot hasn't changed in days | You're reading a stale cached copy. Re-fetch `origin/data-mirror`. |
| `data/trades.jsonl` not present on main | It's not on main. It's on `data-mirror`. See §0. |
| Auditor mandate references retired fields | Use the LDA equivalents in §4b. |

---

## 9. Update protocol

Update this file when:
- A research family transitions open ↔ closed
- A shadow logger crosses its n threshold or its status changes
- A new strategy lever is added (stake change, new gate, new hour block)
- A hard rule changes
- An agent's mandate or output schema changes

Commit message: `agent_context: research_status — <one-line reason>`.
