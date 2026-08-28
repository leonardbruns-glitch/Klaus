#!/bin/bash
# Real liveness watchdog for the klaus service (replaces the retired bond_watchdog,
# which watched a scanner that logs nothing — the June 24 crash sat dead 52h).
# Every 2 min: restart if the service is inactive OR the bot.log heartbeat is stale.
# >= CRASHLOOP_N restarts inside CRASHLOOP_WIN => declare crash-loop, stop flapping,
# hand off to the EVOLVE repair agent (klaus_evolve_repair.service).
set -u

ROOT=/root/Klaus
STATE=/var/lib/klaus_liveness.state          # one epoch per restart we performed
FLAG="$ROOT/logs/evolve/CRASHLOOP.flag"
LOG=/var/log/klaus_liveness.log
BOTLOG="$ROOT/logs/bot.log"
COOLDOWN=300        # min seconds between our restarts
STALE_SEC=900       # bot.log silent this long while "active" => hung
CRASHLOOP_N=4       # this many restarts ...
CRASHLOOP_WIN=7200  # ... inside 2h => crash-loop

log() { echo "$(date -u +%FT%TZ) $*" >>"$LOG"; }

mkdir -p "$(dirname "$STATE")" "$ROOT/logs/evolve"
touch "$STATE"
now=$(date +%s)

# prune restart history to the window
awk -v c=$((now - CRASHLOOP_WIN)) '$1 >= c' "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
recent=$(wc -l <"$STATE")
last=$(tail -1 "$STATE" 2>/dev/null || echo 0)
[ -n "$last" ] || last=0

# Aux live services (UPDOWN sniper = the live capital path since 07-13; shadow = its
# gate sensor). Active-check only: they have no heartbeat file (event-driven logs),
# so staleness can't be checked without false positives in quiet hours.
for svc in klaus_updown_sniper klaus_updown_shadow; do
  if [ "$(systemctl is-active "$svc")" != "active" ]; then
    st="/var/lib/${svc}_liveness.last"
    lastr=$(cat "$st" 2>/dev/null || echo 0)
    if [ $((now - lastr)) -ge "$COOLDOWN" ]; then
      echo "$now" >"$st"
      log "restarting $svc (inactive)"
      systemctl restart "$svc"
    else
      log "$svc inactive but inside cooldown"
    fi
  fi
done

unhealthy=""
if [ "$(systemctl is-active klaus)" != "active" ]; then
  unhealthy="service-inactive"
elif [ -f "$BOTLOG" ]; then
  age=$((now - $(stat -c %Y "$BOTLOG")))
  [ "$age" -gt "$STALE_SEC" ] && unhealthy="heartbeat-stale ${age}s"
fi
[ -z "$unhealthy" ] && exit 0

if [ -f "$FLAG" ]; then
  # crash-loop already declared: don't flap; make sure the repair agent is engaged
  systemctl start klaus_evolve_repair.service 2>/dev/null || true
  log "flag present ($unhealthy) — poked repair agent"
  exit 0
fi

if [ $((now - last)) -lt "$COOLDOWN" ]; then
  log "unhealthy ($unhealthy) but inside restart cooldown"
  exit 0
fi

if [ "$recent" -ge "$CRASHLOOP_N" ]; then
  {
    echo "crash-loop declared $(date -u +%FT%TZ): $recent watchdog restarts in ${CRASHLOOP_WIN}s — current state: $unhealthy"
    echo "--- journalctl -u klaus (tail) ---"
    journalctl -u klaus -n 80 --no-pager 2>/dev/null | tail -50
  } >"$FLAG"
  log "CRASHLOOP declared ($recent restarts/2h) — flag written, repair agent started"
  systemctl start klaus_evolve_repair.service 2>/dev/null || true
  exit 0
fi

echo "$now" >>"$STATE"
log "restarting klaus ($unhealthy; restart $((recent + 1)) in window)"
systemctl restart klaus
