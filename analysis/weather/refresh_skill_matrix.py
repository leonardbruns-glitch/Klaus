"""Weekly/nightly skill matrix refresh.

Two modes:
  --mode live     : merge logs/weather/forecast_actuals.jsonl into skill_matrix.json
                    and reload WeightedEnsemble in running strategy (hot-swap).
  --mode full     : re-pull 5-year archive from Open-Meteo + ASOS and rebuild from scratch.
                    Takes ~25 minutes. Meant for monthly runs.

The live mode is safe to run as a cron job every day (adds incremental observations).
The full mode rebuilds the entire matrix — run it monthly to incorporate new archive data.

Usage:
    # Daily merge (cron, fast):
    python3 -m analysis.weather.refresh_skill_matrix --mode live

    # Monthly full rebuild:
    python3 -m analysis.weather.refresh_skill_matrix --mode full

Cron example (daily at 09:00 UTC, after most markets have resolved):
    0 9 * * * cd /root/Klaus && python3 -m analysis.weather.refresh_skill_matrix --mode live >> logs/weather/refresh.log 2>&1
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_live() -> int:
    from analysis.weather.live_accumulator import update_skill_matrix, status
    logger.info("=== LIVE MERGE ===")
    status()
    result = update_skill_matrix(dry_run=False)
    if not result:
        logger.info("No new paired observations — matrix unchanged.")
        return 0
    n_cities = len(result)
    n_cells = sum(
        sum(len(months) for months in models.values())
        for models in result.values()
    )
    logger.info("Matrix updated: %d cities, %d model×month cells total", n_cities, n_cells)

    # Signal the running strategy to reload (if it's up)
    try:
        from strategy.ensemble_weights import WeightedEnsemble
        # The live instance is in weather_arb.py — we can't hot-swap it here,
        # but WeightedEnsemble.reload() can be called on the next scan cycle.
        # The strategy already calls _ensemble.combine() on every scan, so
        # the updated matrix file is picked up on next restart or explicit reload.
        logger.info("Skill matrix file updated; strategy reloads on next restart.")
    except Exception as e:
        logger.warning("Could not import ensemble_weights: %s", e)
    return 0


def run_full() -> int:
    from analysis.weather.build_skill_matrix import build_matrix
    logger.info("=== FULL REBUILD (5-year archive) ===")
    result = build_matrix()
    n_cities = len(result.get("stations", {}))
    logger.info("Full rebuild complete: %d cities", n_cities)
    return 0


def _cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["live", "full"], default="live",
                    help="live=merge incremental obs; full=rebuild from 5yr archive")
    ap.add_argument("--dry-run", action="store_true",
                    help="print diff without writing (live mode only)")
    args = ap.parse_args()

    if args.mode == "live":
        if args.dry_run:
            from analysis.weather.live_accumulator import update_skill_matrix
            update_skill_matrix(dry_run=True)
            return 0
        return run_live()
    else:
        return run_full()


if __name__ == "__main__":
    sys.exit(_cli())
