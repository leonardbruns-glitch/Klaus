#!/usr/bin/env python3
"""
Learning-engine health monitor — the heartbeat of the self-learning system.

Checks every self-learning / calibration loop and reports whether it is actually
updating (freshness), how much training data it has (counts), and flags any loop
that has STALLED or is starved. Read-only: never changes a parameter.

This exists because a learning loop can silently rot — the NWP skill matrix was
frozen for 10 days (log_actual had no producer) while the daily refresh cheerily
reported "matrix unchanged". A heartbeat makes that visible instead of invisible.

Run:  python3 -m analysis.weather.learning_health
Exit code: 0 = all OK, 1 = at least one loop STALE/STARVED (for cron alerting).
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOW = time.time()
DAY = 86400.0


def _age_str(ts: float) -> str:
    if ts <= 0:
        return "never"
    d = NOW - ts
    if d < 3600:
        return f"{d/60:.0f}m ago"
    if d < DAY:
        return f"{d/3600:.1f}h ago"
    return f"{d/DAY:.1f}d ago"


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _count_jsonl(p: Path, pred=None) -> int:
    if not p.exists():
        return 0
    n = 0
    try:
        with p.open() as f:
            for line in f:
                if not line.strip():
                    continue
                if pred is None:
                    n += 1
                else:
                    try:
                        if pred(json.loads(line)):
                            n += 1
                    except Exception:
                        pass
    except OSError:
        pass
    return n


def _last_ts_jsonl(p: Path, ts_key: str, pred=None) -> float:
    """Last record's timestamp (scans from end is overkill; full pass is fine here)."""
    if not p.exists():
        return 0.0
    last = 0.0
    try:
        with p.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if pred is not None and not pred(r):
                    continue
                v = r.get(ts_key)
                if isinstance(v, (int, float)):
                    last = max(last, float(v))
                elif isinstance(v, str):
                    # try ISO-ish → epoch via best-effort
                    try:
                        import datetime as _dt
                        last = max(last, _dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass
    except OSError:
        pass
    return last


def check() -> int:
    rows: list[tuple] = []   # (loop, status, detail)
    worst_ok = True

    # ── 1. Actuals feed (the producer that was dead) ──────────────────────────
    fa = ROOT / "logs/weather/forecast_actuals.jsonl"
    n_fc = _count_jsonl(fa, lambda r: r.get("event") == "forecast")
    n_ac = _count_jsonl(fa, lambda r: r.get("event") == "actual")
    last_ac = _last_ts_jsonl(fa, "ts_utc", lambda r: r.get("event") == "actual")
    if n_ac == 0:
        rows.append(("actuals feed (log_actual)", "STALLED", f"forecasts={n_fc} actuals=0 — producer dead"))
        worst_ok = False
    elif last_ac and (NOW - last_ac) > 2 * DAY:
        rows.append(("actuals feed (log_actual)", "STALE", f"actuals={n_ac} last={_age_str(last_ac)}"))
        worst_ok = False
    else:
        rows.append(("actuals feed (log_actual)", "OK", f"forecasts={n_fc} actuals={n_ac} last={_age_str(last_ac)}"))

    # ── 2. Skill matrix → ensemble weights (daily refresh) ────────────────────
    sm = ROOT / "strategy/skill_matrix.json"
    sm_age = _mtime(sm)
    status = "OK" if (sm_age and NOW - sm_age < 3 * DAY) else "STALE"
    if status != "OK":
        worst_ok = False
    rows.append(("skill matrix (ensemble wts)", status, f"updated {_age_str(sm_age)}"))

    # ── 3. peak_calib (peak_bias + σ) ─────────────────────────────────────────
    pc = ROOT / "config/stwa_peak_calib.json"
    pc_age = _mtime(pc)
    # static-by-design today; flag as INFO with n of live pairs available to refit
    n_pairs = min(n_fc, n_ac)
    rows.append(("peak_calib (bias+σ)", "STATIC", f"file {_age_str(pc_age)}; live pairs≈{n_ac} (refit not yet wired)"))

    # ── 4. isotonic g (win-prob recal) ────────────────────────────────────────
    iso = ROOT / "config/stwa_isotonic.json"
    iso_age = _mtime(iso)
    rows.append(("isotonic g (win-prob)", "STATIC", f"file {_age_str(iso_age)}; needs n≥100 live resolved"))

    # ── 5. STWA resolution outcomes (training data for trading lane) ──────────
    tr = ROOT / "logs/trades.jsonl"
    def _is(cls):
        return lambda r: r.get("bond_entry_class") == cls
    n_stwa = _count_jsonl(tr, _is("WEATHER_STWA"))
    n_m1 = _count_jsonl(tr, _is("WEATHER_M1_PROBE"))
    rows.append(("STWA resolved (n→learn)", "INFO", f"WEATHER_STWA={n_stwa} (isotonic refit gate n≥100)"))

    # ── 6. M1β / probe1 lockout slice ─────────────────────────────────────────
    m1_status = "INFO" if n_m1 < 100 else "READY"
    rows.append(("M1β probe1 (lockout slice)", m1_status, f"resolved={n_m1} (slice refit gate n≥100)"))

    # ── 7. refresh cron actually pairing? (read refresh.log tail) ─────────────
    rl = ROOT / "logs/weather/refresh.log"
    paired_hint = "?"
    if rl.exists():
        try:
            tail = rl.read_text(errors="replace").splitlines()[-15:]
            for ln in reversed(tail):
                if "Paired:" in ln:
                    paired_hint = ln.split("Paired:")[-1].strip()
                    break
        except OSError:
            pass
    rows.append(("daily refresh (pairing)", "INFO", f"last refresh.log Paired: {paired_hint}"))

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"=== LEARNING-ENGINE HEALTH  {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(NOW))} ===")
    width = max(len(r[0]) for r in rows)
    for loop, status, detail in rows:
        mark = {"OK": "✓", "READY": "✓", "INFO": "·", "STATIC": "·",
                "STALE": "⚠", "STALLED": "✗", "STARVED": "✗"}.get(status, "?")
        print(f"  {mark} {loop.ljust(width)}  [{status:<7}] {detail}")
    print(f"=== overall: {'OK' if worst_ok else 'ATTENTION NEEDED'} ===")
    return 0 if worst_ok else 1


if __name__ == "__main__":
    raise SystemExit(check())
