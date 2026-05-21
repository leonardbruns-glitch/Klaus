"""
Daily performance audit for weather strategies.

Runs at 08:30 UTC daily. Reads last 24h of trades.jsonl, computes
WR / PF / net_pnl per strategy. Writes config/auto_kill.json when any
strategy has PF < KILL_PF_THRESHOLD over n >= KILL_MIN_TRADES.

Strategy scan loops check is_killed() at their top — no bot restart needed.

Usage:
    python3 -m analysis.weather.daily_audit            # last 24h
    python3 -m analysis.weather.daily_audit --days 7   # rolling 7d window
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
TRADES_FILE   = ROOT / "logs" / "trades.jsonl"
AUTO_KILL_FILE = ROOT / "config" / "auto_kill.json"
REPORT_DIR    = ROOT / "logs" / "weather"

# ── Thresholds ────────────────────────────────────────────────────────────────
KILL_PF_THRESHOLD  = 0.70   # PF below this triggers the auto-kill flag
KILL_MIN_TRADES    = 20     # minimum n before triggering
WARN_PF_THRESHOLD  = 1.10   # warn (not kill) if PF drops below this

# Per-strategy expected baselines (PF, WR) from backtest
STRATEGY_BASELINES: dict[str, dict] = {
    "WEATHER_ARB":      {"pf_min": 1.3, "wr_min": 0.50},
    "WEATHER_INTRADAY": {"pf_min": 1.3, "wr_min": 0.50},
    "WEATHER_TAIL":     {"pf_min": 1.3, "wr_min": 0.20},
    "WEATHER_NWPLAG":   {"pf_min": 1.2, "wr_min": 0.45},
    "WEATHER_CITYCTR":  {"pf_min": 1.3, "wr_min": 0.35},
    "WEATHER_NOSIDE":   {"pf_min": 1.5, "wr_min": 0.60},
    "WEATHER_BRACKET":  {"pf_min": 1.2, "wr_min": 0.45},
}

WEATHER_CLASSES = set(STRATEGY_BASELINES.keys())


def is_killed(strategy_class: str) -> bool:
    """
    Called by strategy scan loops to check if auto-audit flagged this class.
    Returns True if PF was below KILL_PF_THRESHOLD over KILL_MIN_TRADES.
    Safe to call on every scan — reads a tiny JSON file.
    """
    try:
        if not AUTO_KILL_FILE.exists():
            return False
        data = json.loads(AUTO_KILL_FILE.read_text())
        entry = data.get(strategy_class, {})
        return entry.get("killed", False)
    except Exception:
        return False  # fail open


def _load_trades(days: float = 1.0) -> list[dict]:
    if not TRADES_FILE.exists():
        logger.warning("trades.jsonl not found at %s", TRADES_FILE)
        return []
    cutoff = time.time() - days * 86400
    trades = []
    with TRADES_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if not t.get("is_live", False):
                continue
            if t.get("ts_open", 0) < cutoff:
                continue
            bec = t.get("bond_entry_class", "")
            if bec in WEATHER_CLASSES:
                trades.append(t)
    return trades


def _compute_stats(trades: list[dict]) -> dict[str, dict]:
    by_class: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_class[t["bond_entry_class"]].append(t)

    result = {}
    for cls, ts in by_class.items():
        resolved = [t for t in ts if t.get("entered_correctly") is not None]
        wins  = [t for t in resolved if t["entered_correctly"]]
        losses = [t for t in resolved if not t["entered_correctly"]]

        gross_win  = sum(t.get("net_pnl", 0.0) for t in wins)
        gross_loss = abs(sum(t.get("net_pnl", 0.0) for t in losses))
        pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
        wr = (len(wins) / len(resolved)) if resolved else None

        result[cls] = {
            "n_total":     len(ts),
            "n_resolved":  len(resolved),
            "n_wins":      len(wins),
            "n_losses":    len(losses),
            "wr":          round(wr, 3) if wr is not None else None,
            "pf":          round(pf, 3) if pf != float("inf") else None,
            "net_pnl":     round(sum(t.get("net_pnl", 0.0) for t in ts), 3),
        }
    return result


def _write_auto_kill(stats: dict[str, dict], days: float) -> dict:
    """Update config/auto_kill.json. Returns {class: killed_bool}."""
    AUTO_KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if AUTO_KILL_FILE.exists():
        try:
            existing = json.loads(AUTO_KILL_FILE.read_text())
        except Exception:
            pass

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    changes = {}
    for cls, s in stats.items():
        n = s["n_resolved"]
        pf = s["pf"]
        prev = existing.get(cls, {})
        was_killed = prev.get("killed", False)

        kill_now = (
            n >= KILL_MIN_TRADES
            and pf is not None
            and pf < KILL_PF_THRESHOLD
        )
        existing[cls] = {
            "killed":       kill_now,
            "pf":           pf,
            "wr":           s["wr"],
            "n_resolved":   n,
            "net_pnl":      s["net_pnl"],
            "window_days":  days,
            "updated_at":   now_iso,
        }
        if kill_now and not was_killed:
            changes[cls] = "NEWLY_KILLED"
            logger.error("[AUDIT] AUTO-KILL %s — PF=%.2f n=%d < threshold %.2f",
                         cls, pf, n, KILL_PF_THRESHOLD)
        elif was_killed and not kill_now:
            changes[cls] = "REINSTATED"
            logger.info("[AUDIT] REINSTATED %s — PF now %.2f n=%d", cls, pf, n)

    AUTO_KILL_FILE.write_text(json.dumps(existing, indent=2))
    return changes


def _print_report(stats: dict[str, dict], days: float) -> None:
    total_pnl = sum(s["net_pnl"] for s in stats.values())
    print(f"\n{'─'*60}")
    print(f"WEATHER STRATEGY AUDIT — last {days:.0f}d  |  total net PnL: ${total_pnl:+.2f}")
    print(f"{'─'*60}")
    for cls in sorted(stats):
        s = stats[cls]
        pf_str  = f"{s['pf']:.2f}" if s["pf"] is not None else "  n/a"
        wr_str  = f"{s['wr']:.1%}"  if s["wr"]  is not None else "n/a"
        status  = ""
        if s["n_resolved"] >= KILL_MIN_TRADES and s["pf"] is not None:
            if s["pf"] < KILL_PF_THRESHOLD:
                status = "  *** KILL ***"
            elif s["pf"] < WARN_PF_THRESHOLD:
                status = "  ! WARN"
        print(f"  {cls:<22} n={s['n_resolved']:>3}/{s['n_total']:>3}"
              f"  WR={wr_str}  PF={pf_str}  PnL=${s['net_pnl']:+.2f}{status}")
    print(f"{'─'*60}\n")


def run(days: float = 1.0) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    trades = _load_trades(days)
    if not trades:
        logger.info("[AUDIT] no WEATHER trades in last %.0fd — nothing to audit", days)
        return

    stats   = _compute_stats(trades)
    changes = _write_auto_kill(stats, days)
    _print_report(stats, days)

    # Persist daily summary
    date_str = time.strftime("%Y-%m-%d", time.gmtime())
    summary_file = REPORT_DIR / f"daily_summary_{date_str}.json"
    summary_file.write_text(json.dumps({
        "date": date_str,
        "window_days": days,
        "strategies": stats,
        "auto_kill_changes": changes,
    }, indent=2))
    logger.info("[AUDIT] summary written to %s", summary_file)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=1.0,
                    help="rolling window in days (default 1.0 = last 24h)")
    args = ap.parse_args()
    run(days=args.days)
    sys.exit(0)
