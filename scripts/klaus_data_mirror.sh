#!/usr/bin/env bash
# /usr/local/bin/klaus_data_mirror.sh
#
# Pushes fresh trade + analytics data to the `data-mirror` branch on GitHub.
# Scheduled scout/audit/watchdog/validator routines fetch from this branch —
# they cannot SSH to the VPS (TCP/22 egress blocked), but they have git access.
#
# The branch is a single-rolling-commit force-push (orphan).
# Don't merge from it; don't fetch its history.
#
# Deploy:
#   sudo install -m 755 scripts/klaus_data_mirror.sh /usr/local/bin/
#   sudo systemctl restart klaus_data_mirror.timer
#   sudo systemctl start klaus_data_mirror.service    # manual run
#   journalctl -u klaus_data_mirror.service -n 50
#
# Verify from any other machine:
#   git fetch origin data-mirror
#   git show origin/data-mirror:data/SNAPSHOT.md
set -euo pipefail
exec 2>&1

KLAUS=/root/Klaus
WORK=/var/lib/klaus_data_mirror
REMOTE_URL=$(git -C "$KLAUS" remote get-url origin)
SNAPSHOT_TS="$(date -u +%FT%TZ)"

log() { echo "[klaus_data_mirror] $*"; }

# ── Initialise / refresh the standalone working repo ───────────────────────
if [ ! -d "$WORK/.git" ]; then
    rm -rf "$WORK"
    mkdir -p "$WORK"
    git -C "$WORK" init -q -b data-mirror
    git -C "$WORK" remote add origin "$REMOTE_URL"
fi
cd "$WORK"

# Drop the working tree completely between runs so removed files don't linger.
git rm -rf . >/dev/null 2>&1 || true
rm -rf data
mkdir -p data data/shadow

# ── Copy live data ─────────────────────────────────────────────────────────
cp -f "$KLAUS/logs/trades.jsonl"   data/trades.jsonl
cp -f "$KLAUS/logs/bankroll.json"  data/bankroll.json
[ -f "$KLAUS/state_log.md" ] && cp -f "$KLAUS/state_log.md" data/state_log.md

# ── UPDOWN-SNIPER extracts (2026-07-19 weekly: sniper = primary live path;
# cloud analysts get the tape, state, stop-file and gate ledger) ─────────────
for f in updown_sniper.jsonl updown_sniper_state.json UPDOWN_STOP; do
    [ -f "$KLAUS/logs/$f" ] && cp -f "$KLAUS/logs/$f" "data/$f" || true
done
[ -f "$KLAUS/logs/evolve/gate_ledger_latest.md" ] && \
    cp -f "$KLAUS/logs/evolve/gate_ledger_latest.md" data/gate_ledger_latest.md || true

# Optional: latest research artifacts if present (regenerated outside this script)
for f in paths.parquet entries.parquet; do
    [ -f "/tmp/research/$f" ] && cp -f "/tmp/research/$f" "data/$f" || true
done

# ── Agent context: CLAUDE.md + research_status.md ──────────────────────────
[ -f "$KLAUS/CLAUDE.md" ] && cp -f "$KLAUS/CLAUDE.md" data/CLAUDE.md
if [ -d "$KLAUS/agent_context" ]; then
    mkdir -p data/agent_context
    cp -rf "$KLAUS/agent_context/"* data/agent_context/ 2>/dev/null || true
fi

# ── Shadow loggers: today's *small* hot files + summary index ──────────────
# Some loggers (market_timeline, gate_trace) are 100s of MB/day — only copy
# files < 10MB into the mirror. The summary indexes ALL active loggers.
SHADOW_DIR="$KLAUS/logs/shadow"
TODAY=$(date -u +%Y-%m-%d)
if [ -d "$SHADOW_DIR/hot/$TODAY" ]; then
    find "$SHADOW_DIR/hot/$TODAY" -maxdepth 1 -name "*.jsonl" -size -10M \
        -exec cp -f {} data/shadow/ \; 2>/dev/null || true
fi

# ── Band-era history (2026-06-12): resolution joins span d+2 entries, so the
# cloud routines need the last 5 days of the band/maker loggers, not just
# today. Bounded to the named small loggers, 10MB cap each.
for i in 1 2 3 4 5; do
    D=$(date -u -d "-$i day" +%Y-%m-%d)
    [ -d "$SHADOW_DIR/hot/$D" ] || continue
    mkdir -p "data/shadow/$D"
    for f in exit099_live.jsonl basket_exit_shadow.jsonl \
             thermo_maker.jsonl badatmath_watch.jsonl metar_lockout.jsonl; do
        [ -f "$SHADOW_DIR/hot/$D/$f" ] && \
            find "$SHADOW_DIR/hot/$D" -maxdepth 1 -name "$f" -size -10M \
                -exec cp -f {} "data/shadow/$D/" \; 2>/dev/null || true
    done
done

# band_struct grows past the 10MB cap on busy days (13MB on 06-12) and
# stwa_pricer_eval is 40-80MB/day — ship a first-fire-deduped band extract
# (all posts/reclaims + first fire per (city,date,reason,side,off)) and a
# 1-in-50 pricer sample instead. Today + 5 days back.
python3 - <<'PYEOF' || true
import json, os, datetime
SH = "/root/Klaus/logs/shadow/hot"
today = datetime.datetime.now(datetime.timezone.utc).date()
for i in range(0, 6):
    d = (today - datetime.timedelta(days=i)).isoformat()
    src = os.path.join(SH, d)
    if not os.path.isdir(src):
        continue
    dst = os.path.join("data/shadow", d)
    os.makedirs(dst, exist_ok=True)
    bs = os.path.join(src, "band_struct.jsonl")
    if os.path.isfile(bs):
        seen = set()
        with open(os.path.join(dst, "band_struct_lite.jsonl"), "w") as out:
            for line in open(bs, errors="ignore"):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("record") == "post" or "reclaim" in str(r.get("record", "")):
                    out.write(line); continue
                k = (r.get("city"), r.get("date"), r.get("reason"),
                     r.get("side"), r.get("off"), r.get("days_out"))
                if k in seen:
                    continue
                seen.add(k); out.write(line)
PYEOF

# pricer sample via awk (python line loop over 6x60MB blew the unit timeout)
for i in 0 1 2 3 4 5; do
    D=$(date -u -d "-$i day" +%Y-%m-%d)
    PE="$SHADOW_DIR/hot/$D/stwa_pricer_eval.jsonl"
    [ -f "$PE" ] || continue
    mkdir -p "data/shadow/$D"
    awk 'NR%50==1' "$PE" > "data/shadow/$D/stwa_pricer_eval_s50.jsonl" || true
done

# Maker surface state (resting orders + posted dedup) — routines audit fills,
# NO-parity and quote age from these.
for f in maker_resting_state.json band_posted_state.json; do
    [ -f "$KLAUS/logs/$f" ] && cp -f "$KLAUS/logs/$f" "data/$f" || true
done

# Live fill tape: [MAKER-FILL] + queue-cycle + reaper lines from the journal
# (bot.log rotates). Bounded.
journalctl -u klaus --since "3 days ago" --no-pager 2>/dev/null \
    | grep -aE 'MAKER-FILL|STRUCT-BAND-Q|reaped dead entry|UNTRACKED FILL' \
    | tail -8000 > data/maker_fills_recent.log || true

# Band/maker live config snapshot from source (flags drift faster than docs)
{
    echo "# Band/maker config (live, from strategy/stwa_engine.py)"
    echo "# Snapshot: $SNAPSHOT_TS"
    grep -nE "^(BAND_|MAKER_|THERMO_|STWA_REGULAR|STWA_LIVE|RECYCLE)[A-Z0-9_]* *=" \
        "$KLAUS/strategy/stwa_engine.py" | head -60
} > data/band_config.txt

# Fast summary: wc -l for count (no Python iteration over GB files),
# head/tail for excerpts. Filter to last 7 days OR hot/, skip backfill.
python3 - <<'PYEOF' > data/shadow_summary.json 2>/dev/null || echo '{"loggers":{},"error":"index failed"}' > data/shadow_summary.json
import json, subprocess, time
from pathlib import Path

shadow = Path("/root/Klaus/logs/shadow")
out = {
    "snapshot_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "loggers": {},
}
SEVEN_DAYS = 7 * 86400
now = time.time()

if shadow.exists():
    for jf in shadow.rglob("*.jsonl"):
        rel = jf.relative_to(shadow).as_posix()
        if rel.startswith("backfill/"):
            continue
        try:
            st = jf.stat()
        except OSError:
            continue
        if (now - st.st_mtime) > SEVEN_DAYS and not rel.startswith("hot/"):
            continue
        try:
            n = int(subprocess.check_output(["wc", "-l", str(jf)], timeout=10).split()[0])
            first = subprocess.check_output(["head", "-c", "400", str(jf)], timeout=5)
            first = first.decode("utf-8", errors="ignore").split("\n", 1)[0]
            last_raw = subprocess.check_output(["tail", "-c", "2048", str(jf)], timeout=5)
            last = last_raw.decode("utf-8", errors="ignore").rstrip().rsplit("\n", 1)[-1]
            out["loggers"][rel] = {
                "n_rows": n,
                "size_bytes": st.st_size,
                "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
                "first_excerpt": first[:300],
                "last_excerpt": last[:300],
            }
        except Exception as e:
            out["loggers"][rel] = {"error": str(e)[:200]}
print(json.dumps(out, indent=2, sort_keys=True))
PYEOF

# ── Compute fresh LDA status (uses /tmp/research/week1_status.py) ──────────
if [ -f /tmp/research/week1_status.py ]; then
    python3 /tmp/research/week1_status.py > data/lda_status.txt 2>&1 || \
        echo "(week1_status.py failed at $SNAPSHOT_TS)" > data/lda_status.txt
else
    echo "(week1_status.py not present at $SNAPSHOT_TS)" > data/lda_status.txt
fi

# ── Data integrity check (agents pre-flight against this) ──────────────────
# Exit 0=clean, 1=warn, 2=blocking. Never let a non-zero rc fail the snapshot.
if [ -x "$KLAUS/scripts/data_integrity_check.py" ]; then
    python3 "$KLAUS/scripts/data_integrity_check.py" \
        --trades "$KLAUS/logs/trades.jsonl" \
        --output data/integrity_report.json \
        --quiet || true
else
    echo '{"issues":{"INTEGRITY_SCRIPT_MISSING":{"severity":"HIGH","msg":"scripts/data_integrity_check.py not present"}},"blocks_agent_run":false,"highest_severity":"HIGH"}' > data/integrity_report.json
fi

# ── LDA config snapshot from source ────────────────────────────────────────
{
    echo "# Current LDA config (live, from late_direction_arb.py)"
    echo "# Snapshot: $SNAPSHOT_TS"
    echo "# Latest commit on klaus:"
    git -C "$KLAUS" log --oneline -1
    echo
    grep -nE "^(ASK_FLOOR|ASK_CEIL|BID_MIN|REM_MIN_S|REM_MAX_S|BLOCKED_HOURS_UTC|_ALL_BLOCKED|_ETH_BLOCKED|_BTC_BLOCKED|_SOL_BLOCKED|STAKE_)" \
        "$KLAUS/strategy/late_direction_arb.py" | head -40
} > data/lda_config.txt

# ── System health ──────────────────────────────────────────────────────────
{
    echo "## klaus systemd:"; systemctl is-active klaus 2>/dev/null || echo "unknown"
    echo
    echo "## Last 10 commits on klaus:"
    git -C "$KLAUS" log --oneline -10 2>/dev/null
    echo
    echo "## Disk (GB):"; df -BG /root | tail -1
    echo
    echo "## Bot uptime:"
    systemctl show klaus --property=ActiveEnterTimestamp 2>/dev/null
    echo
    echo "## Open positions (count):"
    if [ -f "$KLAUS/logs/positions.json" ]; then
        python3 -c "import json; print(len(json.load(open('$KLAUS/logs/positions.json')).get('positions', {})))" 2>/dev/null || echo "?"
    else
        echo "n/a"
    fi
} > data/system_status.txt

# ── Snapshot metadata ──────────────────────────────────────────────────────
CAPITAL=$(python3 -c "import json; print(json.load(open('data/bankroll.json')).get('capital','?'))" 2>/dev/null || echo "?")
N_TRADES=$(wc -l < data/trades.jsonl)
N_LIVE=$(grep -c '"is_live": *true' data/trades.jsonl 2>/dev/null || echo 0)
KLAUS_HEAD=$(git -C "$KLAUS" rev-parse --short HEAD 2>/dev/null || echo "?")
N_SHADOW_FILES=$(ls data/shadow/*.jsonl 2>/dev/null | wc -l)

cat > data/SNAPSHOT.md <<EOF
# Klaus data mirror

| field | value |
|---|---|
| snapshot_ts (UTC) | $SNAPSHOT_TS |
| klaus HEAD | $KLAUS_HEAD |
| trades.jsonl rows | $N_TRADES |
| live rows | $N_LIVE |
| bankroll capital | \$$CAPITAL |
| klaus service | $(systemctl is-active klaus 2>/dev/null || echo unknown) |
| shadow files | $N_SHADOW_FILES |

This branch is force-pushed by \`klaus_data_mirror.timer\` every 15 minutes.
Single-commit rolling snapshot — do NOT merge or rebase from this branch.

## Files

- \`data/trades.jsonl\`       — live trade log (canonical analytics source)
- \`data/bankroll.json\`      — current capital + cumulative pnl
- \`data/updown_sniper.jsonl\` — UPDOWN-SNIPER primary tape (FIRE/SETTLE/skips)
- \`data/updown_sniper_state.json\` — sniper day-state (fires, losses, realized, opens)
- \`data/UPDOWN_STOP\`        — kill file (present = path CUT; absent from mirror = live)
- \`data/gate_ledger_latest.md\` — sniper gate status (the number the loop turns on)
- \`data/lda_status.txt\`     — week-1 status (live EV/fire, CI, decision rule)
- \`data/lda_config.txt\`     — current LDA strategy parameters (from source)
- \`data/state_log.md\`       — append-only user-decision log
- \`data/system_status.txt\`  — klaus systemd, commits, disk, open positions
- \`data/integrity_report.json\` — pre-flight data quality (read FIRST in agents)
- \`data/CLAUDE.md\`          — repo CLAUDE.md (action tiers, rules)
- \`data/agent_context/\`     — agent-readable ground truth (research_status.md, ...)
- \`data/shadow_summary.json\`— per-logger index (n_rows, mtime, head/tail)
- \`data/shadow/*.jsonl\`     — today's hot shadow logger files
- \`data/shadow/<date>/\`     — last 5 days of band/maker loggers (band_struct,
  exit099_live, basket_exit_shadow, thermo_maker, badatmath_watch, metar_lockout)
- \`data/maker_resting_state.json\` — live resting maker orders (side, q_price, matched)
- \`data/band_posted_state.json\`   — band posted-token dedup + daily spent
- \`data/maker_fills_recent.log\`   — 7d fill tape ([MAKER-FILL]/[STRUCT-BAND-Q] journal lines)
- \`data/band_config.txt\`    — live band/maker flags from stwa_engine.py
- \`data/paths.parquet\`      — hold-path data (7d, if regen'd)
- \`data/entries.parquet\`    — entry-state + outcomes (if regen'd)

## How a scheduled routine should consume this

\`\`\`bash
git fetch origin data-mirror
mkdir -p /tmp/k && cd /tmp/k
for f in SNAPSHOT.md trades.jsonl bankroll.json state_log.md \\
         lda_status.txt lda_config.txt system_status.txt \\
         CLAUDE.md shadow_summary.json; do
    git show origin/data-mirror:data/\$f > \$f 2>/dev/null || true
done
git show origin/data-mirror:data/agent_context/research_status.md > research_status.md 2>/dev/null
\`\`\`
EOF

# ── Commit + force-push ────────────────────────────────────────────────────
git add data/
git -c user.name="klaus-data-mirror" -c user.email="bot@klaus.local" \
    commit -q --allow-empty -m "snapshot $SNAPSHOT_TS"

# force-push (overwrite remote single-commit branch)
git push --force origin HEAD:data-mirror >/dev/null

# Reset our local branch back to a clean state for the next run
LATEST=$(git rev-parse HEAD)
git update-ref -d refs/heads/data-mirror >/dev/null 2>&1 || true
git checkout -q --orphan data-mirror
git reset -q --hard "$LATEST"

log "pushed snapshot $SNAPSHOT_TS  trades=$N_TRADES  live=$N_LIVE  cap=\$$CAPITAL  klaus=$KLAUS_HEAD  shadow_files=$N_SHADOW_FILES"
