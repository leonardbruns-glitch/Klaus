#!/bin/bash
# Install/refresh the EVOLVE loop units. Idempotent. Run as root on the VPS.
set -eu
cd "$(dirname "$0")"
chmod +x ../run_agent.sh ../liveness_watchdog.sh
cp klaus_liveness.service klaus_liveness.timer \
   klaus_evolve_daily.service klaus_evolve_daily.timer \
   klaus_evolve_weekly.service klaus_evolve_weekly.timer \
   klaus_evolve_repair.service \
   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now klaus_liveness.timer klaus_evolve_daily.timer klaus_evolve_weekly.timer
# bond_watchdog watched the retired BOND scanner (inert) — superseded by klaus_liveness
systemctl disable --now bond_watchdog.timer 2>/dev/null || true
echo "installed. timers:"
systemctl list-timers --no-pager | grep -E 'klaus_(liveness|evolve)' || true
