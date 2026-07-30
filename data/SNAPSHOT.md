# Klaus data mirror

| field | value |
|---|---|
| snapshot_ts (UTC) | 2026-07-30T02:18:16Z |
| klaus HEAD | ddbcecdd1 |
| trades.jsonl rows | 8228 |
| live rows | 8228 |
| bankroll capital | $88.750373 |
| klaus service | failed
unknown |
| shadow files | 3 |

This branch is force-pushed by `klaus_data_mirror.timer` every 15 minutes.
Single-commit rolling snapshot — do NOT merge or rebase from this branch.

## Files

- `data/trades.jsonl`       — live trade log (canonical analytics source)
- `data/bankroll.json`      — current capital + cumulative pnl
- `data/updown_sniper.jsonl` — UPDOWN-SNIPER primary tape (FIRE/SETTLE/skips)
- `data/updown_sniper_state.json` — sniper day-state (fires, losses, realized, opens)
- `data/UPDOWN_STOP`        — kill file (present = path CUT; absent from mirror = live)
- `data/gate_ledger_latest.md` — sniper gate status (the number the loop turns on)
- `data/lda_status.txt`     — week-1 status (live EV/fire, CI, decision rule)
- `data/lda_config.txt`     — current LDA strategy parameters (from source)
- `data/state_log.md`       — append-only user-decision log
- `data/system_status.txt`  — klaus systemd, commits, disk, open positions
- `data/integrity_report.json` — pre-flight data quality (read FIRST in agents)
- `data/CLAUDE.md`          — repo CLAUDE.md (action tiers, rules)
- `data/agent_context/`     — agent-readable ground truth (research_status.md, ...)
- `data/shadow_summary.json`— per-logger index (n_rows, mtime, head/tail)
- `data/shadow/*.jsonl`     — today's hot shadow logger files
- `data/shadow/<date>/`     — last 5 days of band/maker loggers (band_struct,
  exit099_live, basket_exit_shadow, thermo_maker, badatmath_watch, metar_lockout)
- `data/maker_resting_state.json` — live resting maker orders (side, q_price, matched)
- `data/band_posted_state.json`   — band posted-token dedup + daily spent
- `data/maker_fills_recent.log`   — 7d fill tape ([MAKER-FILL]/[STRUCT-BAND-Q] journal lines)
- `data/band_config.txt`    — live band/maker flags from stwa_engine.py
- `data/paths.parquet`      — hold-path data (7d, if regen'd)
- `data/entries.parquet`    — entry-state + outcomes (if regen'd)

## How a scheduled routine should consume this

```bash
git fetch origin data-mirror
mkdir -p /tmp/k && cd /tmp/k
for f in SNAPSHOT.md trades.jsonl bankroll.json state_log.md \
         lda_status.txt lda_config.txt system_status.txt \
         CLAUDE.md shadow_summary.json; do
    git show origin/data-mirror:data/$f > $f 2>/dev/null || true
done
git show origin/data-mirror:data/agent_context/research_status.md > research_status.md 2>/dev/null
```
