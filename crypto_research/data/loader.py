"""Lazy JSONL loaders + window-panel assembly for the crypto_research stack.

Everything here is **streaming-first**: the Tier-1 feature era is ~82M rows /
40GB on disk, so the readers are generators that yield one parsed record at a
time and never materialise a whole stream in RAM.  Only the (small) label set
``window_resolution`` (~12k rows) and the per-token panels you explicitly ask
for are held in memory.

Public entry points
-------------------
* :func:`iter_jsonl`               — raw lazy line reader with date-range + cap.
* :func:`iter_window_resolution` / :func:`iter_market_timeline` / ...
                                     — typed lazy readers per stream.
* :func:`load_resolution_index`    — build the ``WindowKey -> WindowResolution``
                                     label dict (small; loaded eagerly).
* :func:`build_window_panels`      — join the ``market_timeline`` feature panel
                                     to its label by ``(asset, window_end_ts,
                                     window_size_s)`` and return ``WindowPanel``s.
* :func:`make_synthetic_panels`    — generate reproducible synthetic panels so
                                     the whole stack runs with NO real logs.

Join recipe (Tier-1 feature era, 2026-05-26..06-05)
---------------------------------------------------
``market_timeline`` carries ``window_size_s`` so its label key is direct.
``ob_delta`` / ``token_trade`` lack ``window_size_s`` (recover from
``window_end_ts`` congruence + the per-token mapping carried from the
timeline).  ``binance_trade`` carries no token/window at all and is bucketed
by ``ts_s`` into ``[window_end_ts - window_size_s, window_end_ts)``.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime, timedelta
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
)

import numpy as np

from .schema import (
    BinanceTrade,
    MarketTimelineRow,
    ObDelta,
    TokenTrade,
    WindowKey,
    WindowPanel,
    WindowResolution,
)

# Default root for the date-partitioned Tier-1 shadow logs.
DEFAULT_HOT_ROOT = "/root/Klaus/logs/shadow/hot"

# Stream filenames inside each <date> dir.
STREAM_FILES = {
    "window_resolution": "window_resolution.jsonl",
    "market_timeline": "market_timeline.jsonl",
    "ob_delta": "ob_delta.jsonl",
    "token_trade": "token_trade.jsonl",
    "binance_trade": "binance_trade.jsonl",
}

DateRange = Tuple[str, str]  # ('YYYY-MM-DD', 'YYYY-MM-DD') inclusive


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_day(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _dates_in_range(date_range: Optional[DateRange]) -> Optional[List[str]]:
    """Return inclusive list of ``YYYY-MM-DD`` strings, or ``None`` for all."""
    if date_range is None:
        return None
    start, end = _parse_day(date_range[0]), _parse_day(date_range[1])
    if end < start:
        start, end = end, start
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def discover_dates(hot_root: str = DEFAULT_HOT_ROOT) -> List[str]:
    """List available ``<date>`` partition dirs under ``hot_root`` (sorted)."""
    if not os.path.isdir(hot_root):
        return []
    out = []
    for name in os.listdir(hot_root):
        full = os.path.join(hot_root, name)
        if os.path.isdir(full):
            try:
                _parse_day(name)
            except ValueError:
                continue
            out.append(name)
    return sorted(out)


# ---------------------------------------------------------------------------
# Raw lazy JSONL reader
# ---------------------------------------------------------------------------


def iter_jsonl(
    paths: Sequence[str],
    *,
    max_records: Optional[int] = None,
    skip_bad_lines: bool = True,
) -> Iterator[dict]:
    """Lazily yield parsed JSON objects from a list of JSONL files.

    Parameters
    ----------
    paths
        Files to read in order.  Missing files are skipped.
    max_records
        Stop after this many records total (``None`` = unbounded).
    skip_bad_lines
        If ``True``, malformed JSON lines are silently skipped; otherwise the
        ``json.JSONDecodeError`` propagates.

    Yields
    ------
    dict
        One parsed JSON object per non-empty line.
    """
    count = 0
    for path in paths:
        if not os.path.isfile(path):
            continue
        with open(path, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    if skip_bad_lines:
                        continue
                    raise
                yield obj
                count += 1
                if max_records is not None and count >= max_records:
                    return


def _stream_paths(
    stream: str,
    *,
    date_range: Optional[DateRange],
    hot_root: str,
) -> List[str]:
    """Resolve the JSONL file paths for a date-partitioned stream."""
    fname = STREAM_FILES[stream]
    dates = _dates_in_range(date_range)
    if dates is None:
        return sorted(glob.glob(os.path.join(hot_root, "*", fname)))
    return [os.path.join(hot_root, d, fname) for d in dates]


def _iter_typed(
    stream: str,
    record_cls: Type,
    *,
    date_range: Optional[DateRange],
    max_records: Optional[int],
    hot_root: str,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator:
    """Generic typed lazy reader for a date-partitioned stream."""
    paths = _stream_paths(stream, date_range=date_range, hot_root=hot_root)
    assets = set(asset_filter) if asset_filter is not None else None
    for obj in iter_jsonl(paths, max_records=max_records):
        if assets is not None and obj.get("asset") not in assets:
            continue
        yield record_cls.from_dict(obj)


def iter_window_resolution(
    *,
    date_range: Optional[DateRange] = None,
    max_records: Optional[int] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator[WindowResolution]:
    """Lazily yield :class:`WindowResolution` label rows."""
    return _iter_typed(
        "window_resolution",
        WindowResolution,
        date_range=date_range,
        max_records=max_records,
        hot_root=hot_root,
        asset_filter=asset_filter,
    )


def iter_market_timeline(
    *,
    date_range: Optional[DateRange] = None,
    max_records: Optional[int] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator[MarketTimelineRow]:
    """Lazily yield :class:`MarketTimelineRow` feature rows."""
    return _iter_typed(
        "market_timeline",
        MarketTimelineRow,
        date_range=date_range,
        max_records=max_records,
        hot_root=hot_root,
        asset_filter=asset_filter,
    )


def iter_ob_delta(
    *,
    date_range: Optional[DateRange] = None,
    max_records: Optional[int] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator[ObDelta]:
    """Lazily yield :class:`ObDelta` order-book events."""
    return _iter_typed(
        "ob_delta",
        ObDelta,
        date_range=date_range,
        max_records=max_records,
        hot_root=hot_root,
        asset_filter=asset_filter,
    )


def iter_token_trade(
    *,
    date_range: Optional[DateRange] = None,
    max_records: Optional[int] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator[TokenTrade]:
    """Lazily yield :class:`TokenTrade` Polymarket prints."""
    return _iter_typed(
        "token_trade",
        TokenTrade,
        date_range=date_range,
        max_records=max_records,
        hot_root=hot_root,
        asset_filter=asset_filter,
    )


def iter_binance_trade(
    *,
    date_range: Optional[DateRange] = None,
    max_records: Optional[int] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    asset_filter: Optional[Iterable[str]] = None,
) -> Iterator[BinanceTrade]:
    """Lazily yield :class:`BinanceTrade` ticks (no token/window on stream)."""
    return _iter_typed(
        "binance_trade",
        BinanceTrade,
        date_range=date_range,
        max_records=max_records,
        hot_root=hot_root,
        asset_filter=asset_filter,
    )


# ---------------------------------------------------------------------------
# Label index
# ---------------------------------------------------------------------------


def load_resolution_index(
    *,
    date_range: Optional[DateRange] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    assets: Optional[Iterable[str]] = None,
    window_size_s: Optional[int] = None,
) -> Dict[WindowKey, WindowResolution]:
    """Eagerly load the label set into ``WindowKey -> WindowResolution``.

    The label set is small (~12k rows) so loading it fully is cheap and lets
    every feature row join in O(1).  Optionally filter by asset / window size.
    """
    out: Dict[WindowKey, WindowResolution] = {}
    for wr in iter_window_resolution(
        date_range=date_range, hot_root=hot_root, asset_filter=assets
    ):
        if window_size_s is not None and int(wr.window_size_s) != int(window_size_s):
            continue
        out[wr.key] = wr
    return out


def _label_for_token(wr: WindowResolution, is_up_token: bool) -> Optional[int]:
    """Resolve the label for a specific token direction.

    ``resolved_yes`` is the label for the UP token; the DOWN/NO token gets the
    complement.
    """
    if wr.resolved_yes is None:
        return None
    ry = int(wr.resolved_yes)
    return ry if is_up_token else (1 - ry)


# ---------------------------------------------------------------------------
# Panel assembly
# ---------------------------------------------------------------------------


def build_window_panels(
    *,
    assets: Sequence[str],
    window_size_s: int,
    date_range: Optional[DateRange] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    max_timeline_records: Optional[int] = None,
    up_only: bool = False,
    min_steps: int = 1,
) -> List[WindowPanel]:
    """Join ``market_timeline`` features to ``window_resolution`` labels.

    Streams the timeline lazily, groups feature rows by their token-window,
    attaches the resolved label by the composite key ``(asset, window_end_ts,
    window_size_s)`` and returns a list of fully-formed :class:`WindowPanel`.

    Parameters
    ----------
    assets
        Which assets to include (e.g. ``['BTC', 'ETH', 'SOL']``).
    window_size_s
        ``300`` (5-min) or ``900`` (15-min).
    date_range
        Inclusive ``('YYYY-MM-DD', 'YYYY-MM-DD')`` or ``None`` for all
        available partitions.
    max_timeline_records
        Cap on raw timeline rows read (for fast smoke tests).
    up_only
        If ``True``, keep only UP/YES-token panels (one per window).
    min_steps
        Drop panels with fewer than this many timeline rows.

    Returns
    -------
    list[WindowPanel]
        Sorted by ``(first_ts, asset, window_end_ts, token_id)`` so they can
        be fed to the event-driven engine in time order.

    Notes
    -----
    Raw ``binance_trade`` / ``ob_delta`` / ``token_trade`` are NOT attached
    here (they are large and most strategies use the timeline panel only).
    Use :func:`attach_binance_ticks` to enrich specific panels on demand.
    """
    labels = load_resolution_index(
        date_range=date_range,
        hot_root=hot_root,
        assets=assets,
        window_size_s=window_size_s,
    )
    asset_set = set(assets)

    # group timeline rows by token-window
    grouped: Dict[Tuple[str, str], WindowPanel] = {}
    for row in iter_market_timeline(
        date_range=date_range,
        hot_root=hot_root,
        asset_filter=asset_set,
        max_records=max_timeline_records,
    ):
        if row.window_size_s is None or int(row.window_size_s) != int(window_size_s):
            continue
        is_up = (row.outcome_dir or "").lower() == "up" or (
            row.outcome_dir is None and (row.outcome_side or "").upper() == "YES"
        )
        if up_only and not is_up:
            continue
        gkey = (row.token_id, str(row.window_end_ts))
        panel = grouped.get(gkey)
        if panel is None:
            panel = WindowPanel(
                asset=row.asset,
                window_end_ts=int(row.window_end_ts),
                window_size_s=int(window_size_s),
                token_id=row.token_id,
                outcome_dir=row.outcome_dir,
                outcome_side=row.outcome_side,
            )
            grouped[gkey] = panel
        panel.timeline.append(row)

    # attach labels + finalise
    panels: List[WindowPanel] = []
    for panel in grouped.values():
        if len(panel.timeline) < min_steps:
            continue
        wr = labels.get(panel.key)
        if wr is not None:
            panel.label_resolved_yes = _label_for_token(wr, panel.is_up_token)
            panel.realized_move_pct = wr.realized_move_pct
            panel.binance_open = wr.binance_open_5m
            panel.binance_close = wr.binance_close_5m
            panel.binance_high = wr.binance_high_5m
            panel.binance_low = wr.binance_low_5m
        panel.sort()
        panels.append(panel)

    panels.sort(key=lambda p: (p.first_ts(), p.asset, p.window_end_ts, p.token_id))
    return panels


def attach_binance_ticks(
    panels: Sequence[WindowPanel],
    *,
    date_range: Optional[DateRange] = None,
    hot_root: str = DEFAULT_HOT_ROOT,
    max_records: Optional[int] = None,
) -> None:
    """Bucket ``binance_trade`` ticks into the given panels, in place.

    Because ``binance_trade`` carries no token/window, each tick is assigned
    to a panel by matching ``asset`` and bucketing ``ts_s`` into
    ``[window_start_ts, window_end_ts)``.  Builds a per-asset interval index
    so the scan is O(N_ticks * log N_windows).
    """
    # Build per-asset sorted window-start arrays + panel lists.
    by_asset: Dict[str, List[WindowPanel]] = {}
    for p in panels:
        by_asset.setdefault(p.asset, []).append(p)
    for plist in by_asset.values():
        plist.sort(key=lambda p: p.window_start_ts)
    starts = {a: np.array([p.window_start_ts for p in plist]) for a, plist in by_asset.items()}

    for tick in iter_binance_trade(
        date_range=date_range,
        hot_root=hot_root,
        asset_filter=set(by_asset.keys()),
        max_records=max_records,
    ):
        plist = by_asset.get(tick.asset)
        if not plist:
            continue
        arr = starts[tick.asset]
        idx = int(np.searchsorted(arr, tick.ts_s, side="right")) - 1
        if idx < 0:
            continue
        panel = plist[idx]
        if panel.window_start_ts <= tick.ts_s < panel.window_end_ts:
            panel.binance_ticks.append(tick)
    for p in panels:
        p.binance_ticks.sort(key=lambda t: t.ts_s)


# ---------------------------------------------------------------------------
# Synthetic panels (no real logs required)
# ---------------------------------------------------------------------------


def make_synthetic_panels(
    n: int,
    *,
    seed: int = 7,
    window_size_s: int = 300,
    assets: Sequence[str] = ("BTC", "ETH", "SOL"),
    steps_per_window: int = 30,
    base_ts: int = 1_780_000_000,
    up_and_down: bool = False,
    edge_strength: float = 0.6,
) -> List[WindowPanel]:
    """Generate ``n`` reproducible synthetic :class:`WindowPanel` objects.

    The synthetic generator embeds a *real* but modest signal so that
    strategies can be unit-tested for sign-correctness without the 40GB logs:

    * The underlying Binance spot follows a GBM-like random walk inside each
      window; the window resolves UP iff ``close > open``.
    * The Polymarket ``mid`` tracks an over-confident transform of the running
      spot move, plus noise — i.e. the book is informative but imperfect, so
      a momentum / mean-reversion strategy can express a measurable edge.
    * ``edge_strength`` in ``[0, 1]`` scales how much the *late-window* spot
      drift predicts the outcome beyond what ``mid`` already prices, giving a
      tunable ground-truth edge for tests.

    Parameters
    ----------
    n
        Number of windows (each produces 1 panel, or 2 if ``up_and_down``).
    seed
        Seed for the numpy RNG (reproducible).
    up_and_down
        If ``True``, emit both the UP and the complementary DOWN token panel
        per window (the DOWN ``mid`` ≈ ``1 - up_mid``).
    edge_strength
        Ground-truth predictive strength injected into late-window features.

    Returns
    -------
    list[WindowPanel]
        Time-ordered synthetic panels with labels populated.
    """
    rng = np.random.default_rng(seed)
    panels: List[WindowPanel] = []
    dt = window_size_s / steps_per_window

    for i in range(n):
        asset = assets[i % len(assets)]
        window_end_ts = base_ts + (i // len(assets)) * window_size_s + (i % len(assets)) * 1
        # round window_end_ts onto the grid for realism
        window_end_ts = (window_end_ts // window_size_s + 1) * window_size_s + (i % len(assets))
        window_start_ts = window_end_ts - window_size_s

        price0 = {"BTC": 60000.0, "ETH": 1800.0, "SOL": 150.0}.get(asset, 100.0)
        vol = 0.0008  # per-step return vol
        rets = rng.normal(0.0, vol, steps_per_window)
        path = price0 * np.exp(np.cumsum(rets))
        open_px = float(path[0])
        close_px = float(path[-1])
        high_px = float(path.max())
        low_px = float(path.min())
        moved_up = close_px > open_px
        move_pct = (close_px - open_px) / open_px * 100.0

        # Ground-truth edge: late-window cumulative drift biased toward outcome
        drift_signal = (close_px - open_px) / open_px
        timeline: List[MarketTimelineRow] = []
        for s in range(steps_per_window):
            frac = (s + 1) / steps_per_window
            ts_s = window_start_ts + frac * window_size_s
            run_move = (path[s] - open_px) / open_px
            # informative-but-imperfect book mid for the UP token
            base_p = 0.5 + 4.0 * run_move + rng.normal(0.0, 0.03)
            # inject extra late-window predictive content (the test edge)
            base_p += edge_strength * frac * np.sign(drift_signal) * 0.05
            up_mid = float(np.clip(base_p, 0.02, 0.98))
            spread = 0.01 + 0.01 * (1.0 - frac)
            mt = MarketTimelineRow(
                ts_s=float(ts_s),
                token_id=f"SYN-{asset}-{window_end_ts}-UP",
                asset=asset,
                window_end_ts=int(window_end_ts),
                condition_id=f"COND-{asset}-{window_end_ts}",
                outcome_dir="up",
                outcome_side="YES",
                window_size_s=int(window_size_s),
                seconds_to_resolution=float(window_end_ts - ts_s),
                schema_version=2,
                best_bid=round(up_mid - spread / 2, 4),
                best_ask=round(up_mid + spread / 2, 4),
                mid=round(up_mid, 4),
                spread_abs=round(spread, 4),
                spread_bps=round(spread / max(up_mid, 1e-6) * 1e4, 2),
                ob_imb_top3=float(np.clip(rng.normal(0.0, 0.3), -1, 1)),
                ob_book_depth_size=float(abs(rng.normal(500, 150))),
                binance_spot=float(path[s]),
                binance_ret_1m_pct=float(run_move * 100.0),
                binance_ret_5m_pct=float(run_move * 100.0),
                binance_vel_5s_pct=float(rets[s] * 100.0),
                vpin_score=float(np.clip(rng.normal(0.5, 0.15), 0, 1)),
                vol_regime="mid",
                trend_regime="up" if run_move > 0 else "down",
                liquidity_regime="normal",
                arb_sum_yes_no=float(1.0 + rng.normal(0.0, 0.01)),
            )
            timeline.append(mt)

        up_panel = WindowPanel(
            asset=asset,
            window_end_ts=int(window_end_ts),
            window_size_s=int(window_size_s),
            token_id=f"SYN-{asset}-{window_end_ts}-UP",
            outcome_dir="up",
            outcome_side="YES",
            timeline=timeline,
            label_resolved_yes=int(moved_up),
            realized_move_pct=float(move_pct),
            binance_open=open_px,
            binance_close=close_px,
            binance_high=high_px,
            binance_low=low_px,
        )
        panels.append(up_panel)

        if up_and_down:
            down_timeline: List[MarketTimelineRow] = []
            for mt in timeline:
                up_mid = mt.mid if mt.mid is not None else 0.5
                down_mid = float(np.clip(1.0 - up_mid, 0.02, 0.98))
                spread = mt.spread_abs or 0.01
                down_timeline.append(
                    MarketTimelineRow(
                        ts_s=mt.ts_s,
                        token_id=f"SYN-{asset}-{window_end_ts}-DOWN",
                        asset=asset,
                        window_end_ts=int(window_end_ts),
                        condition_id=mt.condition_id,
                        outcome_dir="down",
                        outcome_side="NO",
                        window_size_s=int(window_size_s),
                        seconds_to_resolution=mt.seconds_to_resolution,
                        schema_version=2,
                        best_bid=round(down_mid - spread / 2, 4),
                        best_ask=round(down_mid + spread / 2, 4),
                        mid=round(down_mid, 4),
                        spread_abs=spread,
                        binance_spot=mt.binance_spot,
                        binance_ret_1m_pct=mt.binance_ret_1m_pct,
                        binance_ret_5m_pct=mt.binance_ret_5m_pct,
                    )
                )
            down_panel = WindowPanel(
                asset=asset,
                window_end_ts=int(window_end_ts),
                window_size_s=int(window_size_s),
                token_id=f"SYN-{asset}-{window_end_ts}-DOWN",
                outcome_dir="down",
                outcome_side="NO",
                timeline=down_timeline,
                label_resolved_yes=int(not moved_up),
                realized_move_pct=float(move_pct),
                binance_open=open_px,
                binance_close=close_px,
                binance_high=high_px,
                binance_low=low_px,
            )
            panels.append(down_panel)

    panels.sort(key=lambda p: (p.first_ts(), p.asset, p.window_end_ts, p.token_id))
    return panels


__all__ = [
    "DEFAULT_HOT_ROOT",
    "STREAM_FILES",
    "iter_jsonl",
    "discover_dates",
    "iter_window_resolution",
    "iter_market_timeline",
    "iter_ob_delta",
    "iter_token_trade",
    "iter_binance_trade",
    "load_resolution_index",
    "build_window_panels",
    "attach_binance_ticks",
    "make_synthetic_panels",
]
