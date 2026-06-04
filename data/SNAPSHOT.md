# Klaus data mirror

| field | value |
|---|---|
| snapshot_ts (UTC) | 2026-06-04T16:14:13Z |
| klaus HEAD | 74a6c098 |
| trades.jsonl rows | 7204 |
| live rows | 7204 |
| bankroll capital | $74.970708 |
| klaus service | active |
| shadow files | 12 |

This branch is force-pushed by `klaus_data_mirror.timer` every 15 minutes.
Single-commit rolling snapshot — do NOT merge or rebase from this branch.

## Files

- `data/trades.jsonl`       — live trade log (canonical analytics source)
- `data/bankroll.json`      — current capital + cumulative pnl
- `data/lda_status.txt`     — week-1 status (live EV/fire, CI, decision rule)
- `data/lda_config.txt`     — current LDA strategy parameters (from source)
- `data/state_log.md`       — append-only user-decision log
- `data/system_status.txt`  — klaus systemd, commits, disk, open positions
- `data/CLAUDE.md`          — repo CLAUDE.md (action tiers, rules)
- `data/agent_context/`     — agent-readable ground truth (research_status.md, ...)
- `data/shadow_summary.json`— per-logger index (n_rows, mtime, head/tail)
- `data/shadow/*.jsonl`     — today's hot shadow logger files
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
