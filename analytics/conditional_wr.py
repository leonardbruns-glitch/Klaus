"""
Klaus — Conditional Win Rate Calculator
========================================
Reads logs/trades.jsonl and computes historical WR by (regime, window_size_s).

Purpose:
  Phase 1 — Data collection: log cond_wr + cond_n on every trade record so we
             can see which conditions have low WR before gating anything.
  Phase 2 — Active filter: when CONDITIONAL_WR_GATE=True in config, block entries
             where cond_wr < CONDITIONAL_WR_MIN AND cond_n >= CONDITIONAL_WR_MIN_N.
             Only activates per-condition once there is enough data to trust.

Why (regime, window_size_s)?
  From 18 real trades, these two fields explain the most variance:
    QUIET_DEAD  (any window): 0/2 = 0% WR, net PnL = -$1.63
    QUIET_FLOW  (any window): 1/3 = 33% WR, net PnL = -$2.28
    ACTIVE_COLD (any window): 4/5 = 80% WR, net PnL = +$2.06
  The data is already screaming: don't trade quiet regimes.
  This module enforces that automatically once n ≥ MIN_N per condition.

Safe design:
  - Never raises — all errors are caught and logged; returns neutral (0.5, 0) on failure
  - Reloads every 30 min to pick up new trades without restart
  - Module-level singleton COND_WR for zero-overhead import
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger("conditional_wr")

TRADES_LOG      = Path("logs/trades.jsonl")
RELOAD_INTERVAL = 1800   # reload every 30 minutes
_NEUTRAL_WR     = 0.5    # returned when n < min_n (no information)


class ConditionalWR:
    """
    Computes and caches historical WR by (regime, window_size_s).
    Thread-safe for read (GIL); reload is single-threaded (called from score()).
    """

    def __init__(self) -> None:
        # (regime, window_size_s) → {"wins": int, "n": int}
        self._stats: Dict[Tuple[str, int], Dict[str, int]] = {}
        self._last_load: float = 0.0
        self._load()

    # ── Data loading ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not TRADES_LOG.exists():
            self._last_load = time.time()
            return
        stats: Dict[Tuple[str, int], Dict[str, int]] = defaultdict(
            lambda: {"wins": 0, "n": 0}
        )
        loaded = 0
        try:
            with open(TRADES_LOG) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        t = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Exclude orphans, stubs, dry-runs, UI-recovery records
                    if (
                        t.get("signal_source") == "ORPHAN"
                        or t.get("exit_reason") == "ORPHAN_SELL"
                        or str(t.get("token_id", "")).startswith("stub_")
                        or not t.get("is_live", False)
                        or "_UIREC" in str(t.get("trade_id", ""))
                    ):
                        continue
                    regime = t.get("regime", "")
                    window = int(t.get("window_size_s", 0))
                    if not regime or window == 0:
                        continue
                    key = (regime, window)
                    stats[key]["n"] += 1
                    if float(t.get("net_pnl", 0) or 0) > 0.01:
                        stats[key]["wins"] += 1
                    loaded += 1
        except Exception as exc:
            logger.warning("ConditionalWR._load failed: %s", exc)
            self._last_load = time.time()
            return

        self._stats = dict(stats)
        self._last_load = time.time()
        if loaded:
            logger.info(
                "ConditionalWR: loaded %d trades → %d condition buckets",
                loaded, len(self._stats),
            )
            for (regime, window), s in sorted(self._stats.items()):
                wr = s["wins"] / s["n"] if s["n"] > 0 else 0
                logger.debug(
                    "  WR[%s/%dm] = %.0f%% (%d/%d)",
                    regime, window // 60, wr * 100, s["wins"], s["n"],
                )

    def _maybe_reload(self) -> None:
        if time.time() - self._last_load > RELOAD_INTERVAL:
            self._load()

    # ── Public API ───────────────────────────────────────────────────────────

    def get(self, regime: str, window_size_s: int) -> Tuple[float, int]:
        """
        Return (wr, n) for this condition.
        Returns (_NEUTRAL_WR=0.5, n) when n < 3 — no information yet.
        """
        self._maybe_reload()
        key = (regime, window_size_s)
        s = self._stats.get(key, {"wins": 0, "n": 0})
        n = s["n"]
        if n < 3:
            return _NEUTRAL_WR, n
        return round(s["wins"] / n, 3), n

    def should_block(
        self,
        regime: str,
        window_size_s: int,
        min_wr: float = 0.35,
        min_n:  int   = 10,
    ) -> Tuple[bool, float, int]:
        """
        Returns (should_block, wr, n).

        Blocks when:
          - wr < min_wr  (historically losing condition)
          - n >= min_n   (enough data to trust the WR estimate)

        Never blocks when n < min_n — insufficient data is NOT evidence of no edge.
        The gate protects against KNOWN losing conditions, not unknown ones.
        """
        wr, n = self.get(regime, window_size_s)
        if n < min_n:
            return False, wr, n
        return (wr < min_wr), wr, n

    def summary(self) -> str:
        """Return a compact summary string for logging."""
        self._maybe_reload()
        lines = []
        for (regime, window), s in sorted(self._stats.items()):
            if s["n"] == 0:
                continue
            wr = s["wins"] / s["n"]
            lines.append(
                f"{regime}/{window//60}m: {wr:.0%} ({s['wins']}/{s['n']})"
            )
        return " | ".join(lines) if lines else "no data"


# Module-level singleton — import and use directly
COND_WR = ConditionalWR()
