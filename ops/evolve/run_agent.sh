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

# ── kernel tamper-trip ───────────────────────────────────────────────────────
# INVARIANTS.md is hash-pinned. On mismatch: try restoring the committed copy; if
# that also mismatches (committed tamper), refuse to launch any agent. Editing the
# kernel legitimately (interactive session only) requires updating this pin.
KERNEL_SHA="28329ea7fe29903d73d649ded992394c1c552887fca78c02c345763b17fc372d"
kernel_ok() { [ "$(sha256sum "$ROOT/ops/evolve/INVARIANTS.md" 2>/dev/null | cut -d' ' -f1)" = "$KERNEL_SHA" ]; }
if ! kernel_ok; then
  git -C "$ROOT" checkout HEAD -- ops/evolve/INVARIANTS.md 2>/dev/null || true
  if ! kernel_ok; then
    echo "$(date -u +%FT%TZ) KERNEL TAMPER: INVARIANTS.md hash mismatch, restore failed — refusing to launch $MODE agent" | tee -a "$LOG" >>"$LOGDIR/ESCALATIONS.md"
    exit 70
  fi
  echo "$(date -u +%FT%TZ) kernel drift detected — restored INVARIANTS.md from git" >>"$LOG"
fi
# every agent prompt must route through the charter (except the wiring test)
if [ "$MODE" != "test" ] && ! grep -q "CHARTER.md" "$PROMPT"; then
  echo "$(date -u +%FT%TZ) prompt $PROMPT lost its CHARTER.md reference — refusing to launch" | tee -a "$LOG" >>"$LOGDIR/ESCALATIONS.md"
  exit 70
fi

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
