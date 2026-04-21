#!/bin/bash
# BOND scanner watchdog.
#
# Restarts klaus if [BOND] log line hasn't appeared in the last $STALL_SEC seconds
# while [SNIPER] still is logging (= signal loop alive, but BOND scanner silent).
#
# Deploy:
#   sudo cp scripts/bond_watchdog.sh /usr/local/bin/klaus_bond_watchdog.sh
#   sudo chmod +x /usr/local/bin/klaus_bond_watchdog.sh
#   sudo cp scripts/bond_watchdog.service /etc/systemd/system/
#   sudo cp scripts/bond_watchdog.timer   /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now bond_watchdog.timer

set -u

STALL_SEC=${STALL_SEC:-120}        # restart if [BOND] silent this long
SNIPER_SEC=${SNIPER_SEC:-60}       # and [SNIPER] has logged in this window
COOLDOWN_SEC=${COOLDOWN_SEC:-300}  # never restart more often than this
STATE_FILE=/var/lib/klaus_bond_watchdog.state
LOG_FILE=/var/log/klaus_bond_watchdog.log

log() {
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') $*" >> "$LOG_FILE"
}

now_epoch() { date +%s; }

# Last restart time (cooldown enforcement).
last_restart=0
if [[ -r "$STATE_FILE" ]]; then
    last_restart=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi

now=$(now_epoch)
if (( now - last_restart < COOLDOWN_SEC )); then
    exit 0
fi

# journalctl --since uses absolute timestamps; we grep for most recent hits.
sniper_line=$(journalctl -u klaus --since "${SNIPER_SEC} seconds ago" --no-pager 2>/dev/null | grep -F '[SNIPER]' | tail -1)
bond_line=$(journalctl -u klaus --since "${STALL_SEC} seconds ago" --no-pager 2>/dev/null | grep -F '[BOND]' | tail -1)

# Bot not running at all (no SNIPER output) — don't interfere; let systemd handle it.
if [[ -z "$sniper_line" ]]; then
    exit 0
fi

# BOND still logging recently — healthy.
if [[ -n "$bond_line" ]]; then
    exit 0
fi

# SNIPER alive but BOND silent ≥ STALL_SEC → scanner is wedged. Restart.
log "STALL DETECTED: SNIPER active, [BOND] silent ≥${STALL_SEC}s — restarting klaus"
log "last SNIPER line: $sniper_line"

if systemctl restart klaus; then
    echo "$now" > "$STATE_FILE"
    log "restart OK"
else
    log "restart FAILED (rc=$?)"
fi
