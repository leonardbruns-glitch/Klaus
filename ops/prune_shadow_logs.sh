#!/bin/bash
# prune_shadow_logs.sh — bound disk usage on the live box by aging out dated shadow-log
# dirs. Keeps the most recent KEEP_DAYS of logs/shadow/hot/<YYYY-MM-DD>/.
#
# SAFE BY CONSTRUCTION: only removes directories directly under logs/shadow/hot/ whose
# name is a valid YYYY-MM-DD strictly older than the cutoff. Never touches logs/ root
# files (positions.json, bankroll.json, trades.jsonl, bot.log), data/, or today's dir.
# Lexicographic compare on YYYY-MM-DD == chronological. Idempotent; logs what it removes.
#
# Install (already wired via crontab): 0 4 * * * KEEP_DAYS=10 /root/Klaus/ops/prune_shadow_logs.sh
# Manual run for immediate relief: KEEP_DAYS=10 /root/Klaus/ops/prune_shadow_logs.sh
set -euo pipefail
KEEP_DAYS="${KEEP_DAYS:-10}"
HOT="/root/Klaus/logs/shadow/hot"
cutoff="$(date -u -d "-${KEEP_DAYS} days" +%Y-%m-%d)"
[ -d "$HOT" ] || exit 0
freed=0
for d in "$HOT"/*/; do
  name="$(basename "$d")"
  [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue   # only dated dirs
  if [[ "$name" < "$cutoff" ]]; then                           # strictly older than cutoff
    sz="$(du -sm "$d" 2>/dev/null | cut -f1 || echo 0)"
    echo "$(date -u +%FT%TZ) prune_shadow_logs: removing $d (${sz}MB, keep=${KEEP_DAYS}d cutoff=${cutoff})"
    rm -rf "$d" && freed=$((freed + sz))
  fi
done
echo "$(date -u +%FT%TZ) prune_shadow_logs: done, freed ${freed}MB; df: $(df -h / | awk 'NR==2{print $4" free ("$5" used)"}')"
