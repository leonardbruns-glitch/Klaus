#!/bin/bash
# EVOLVE loop agent runner — invokes headless Claude Code with the mode's prompt.
# Usage: run_agent.sh daily|weekly|repair|test
# One shared lock so daily/weekly/repair never run concurrently (they all touch git+systemd).
set -u

MODE="${1:?usage: run_agent.sh daily|weekly|repair|test}"
ROOT=/root/Klaus
PROMPT="$ROOT/ops/evolve/${MODE}_prompt.md"
[ -f "$PROMPT" ] || { echo "no prompt file: $PROMPT" >&2; exit 1; }

LOCK=/var/lock/klaus_evolve.lock
LOGDIR="$ROOT/logs/evolve"
mkdir -p "$LOGDIR"
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
LOG="$LOGDIR/run_${MODE}_${TS}.log"

export HOME=/root
export PATH="/root/.nvm/versions/node/v22.22.2/bin:/usr/local/bin:/usr/bin:/bin"
# required for --dangerously-skip-permissions as root (this box is a single-purpose VPS)
export IS_SANDBOX=1
cd "$ROOT"

# keep only the newest 40 run logs
ls -1t "$LOGDIR"/run_*.log 2>/dev/null | tail -n +41 | xargs -r rm -f

(
  # repair must not wait forever behind a wedged daily run; others wait up to 15 min
  WAIT=900; [ "$MODE" = "repair" ] && WAIT=1800
  flock -w "$WAIT" 9 || { echo "$(date -u +%FT%TZ) lock busy — abort $MODE" >>"$LOG"; exit 75; }

  echo "=== EVOLVE $MODE start $(date -u +%FT%TZ) ===" >>"$LOG"
  claude -p "$(cat "$PROMPT")" \
    --model claude-fable-5 \
    --dangerously-skip-permissions \
    --max-turns 250 \
    >>"$LOG" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "=== primary model failed rc=$rc — retry on default model $(date -u +%FT%TZ) ===" >>"$LOG"
    claude -p "$(cat "$PROMPT")" \
      --dangerously-skip-permissions \
      --max-turns 250 \
      >>"$LOG" 2>&1
    rc=$?
  fi
  echo "=== EVOLVE $MODE end rc=$rc $(date -u +%FT%TZ) ===" >>"$LOG"
  exit $rc
) 9>"$LOCK"
