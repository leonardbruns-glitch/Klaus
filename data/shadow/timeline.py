"""Per-second observer of all in-eligibility-window updown tokens.

Emits one `market_timeline` record + one `gate_trace` record per
(token_id, second) when the token is within the eligibility band
(remaining_s in [5, eligibility_remaining_s + 60]).

Reads only from feed caches — never triggers HTTP calls or live state mutation.

Phase 1 field set is intentionally compact (~30 fields). Add fields by
appending to `_build_record` AND `_schema/v1.json`. Existing rows remain valid
because every field is null-tolerant on read.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .holdpath import HoldPathSampler
from .pipeline import ShadowPipeline

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# UTC hour → session_bucket. Aligned with feedback_updown_analysis findings
# (Asia / LDN / EU overlap / NY pre-open / NY open / NY lunch / power hour / after).
_SESSION_BUCKETS = (
    (0, 6,   "asia"),
    (6, 8,   "ldn_open"),
    (8, 13,  "eu_overlap"),
    (13, 14, "ny_pre"),
    (14, 16, "ny_open"),
    (16, 18, "ny_lunch"),
    (18, 21, "power_hour"),
    (21, 24, "after_hours"),
)

def _vol_regime(abs_5m_pct: float) -> str:
    if abs_5m_pct < 0.05: return "calm"
    if abs_5m_pct < 0.15: return "normal"
    if abs_5m_pct < 0.30: return "volatile"
    return "extreme"


def _trend_regime(ret_60s_pct: float) -> str:
    if ret_60s_pct > 0.02: return "up"
    if ret_60s_pct < -0.02: return "down"
    return "flat"


def _liquidity_regime(depth: float) -> str:
    if depth > 500: return "deep"
    if depth > 150: return "normal"
    return "thin"


# Passive gate replication — mirrors live thresholds as of 2026-05-09.
# NOT the authoritative trace (live strategy is), but lets analysts ask
# "what would the stripped-down structural gates have done" without joining
# trades.jsonl. Update this block whenever live thresholds change.
#
# Current live gates replicated here:
#   ask_floor  0.78  (main.py:2381)
#   ask_max    0.93  (main.py:2379)
#   ob_imb     0.20  (main.py:2437)
#   terminal   25-120s (main.py:_REM_MIN/_REM_MAX)
#
# Removed vs Phase-1 reconstruction (gates no longer in live bot):
#   spread     (SOL-only at 3%, not universal)
#   snap30     (removed 2026-05-09, Model A)
#   snap60     (removed earlier)
#   ob_imb_ceil (not in live code)
_GATE_ASK_FLOOR    = 0.78
_GATE_ASK_MAX      = 0.93
_GATE_OB_IMB_FLOOR = 0.0


def _session_bucket(hour: int) -> str:
    for lo, hi, name in _SESSION_BUCKETS:
        if lo <= hour < hi:
            return name
    return "after_hours"


class TimelineSampler:
    def __init__(
        self,
        bot: Any,
        pipeline: ShadowPipeline,
        tick_interval_s: float = 1.0,
        eligibility_remaining_s: float = 240.0,
    ) -> None:
        self.bot = bot
        self.pipe = pipeline
        self.tick_interval_s = tick_interval_s
        self.eligibility_remaining_s = eligibility_remaining_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_emit_ts: dict = {}  # token_id → int(ts_s) of last emission, dedup
        self.hold_path = HoldPathSampler(pipeline)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="shadow_timeline")
            logger.info("TimelineSampler started — tick=%.1fs", self.tick_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self._sample_once()
            except Exception:
                logger.exception("timeline sampler iteration failed")
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, self.tick_interval_s - elapsed))

    def _sample_once(self) -> None:
        now = time.time()
        now_s = int(now)
        feed = self.bot.feed
        for token_id, token in list(feed.tokens.items()):
            if getattr(token, "market_type", None) != "updown":
                continue
            wend = getattr(token, "window_end_ts", 0)
            if wend <= 0:
                continue
            remaining = wend - now
            if remaining < 5 or remaining > (self.eligibility_remaining_s + 60):
                continue
            # 1Hz dedup — multiple loop iterations within the same second emit once.
            if self._last_emit_ts.get(token_id) == now_s:
                continue
            try:
                rec = self._build_record(token_id, token, now, remaining)
                if rec is None:
                    continue
                self.pipe.emit(rec)
                gt = self._build_gate_trace(rec)
                if gt is not None:
                    self.pipe.emit(gt)
                # Exit-policy shadow: register first-fires (gate all_pass), then
                # evaluate active tracked positions against this tick.
                _exit_pol = getattr(self.bot, "shadow_exit_policy", None)
                if _exit_pol is not None:
                    if gt is not None:
                        _exit_pol.register_first_fire(rec, gt)
                    _exit_pol.evaluate_tick(rec)
                # Phase 2 Discovery — Step 3 passive recorder (2026-05-10).
                # Strict signal filter; first-fire-per-window dedup.
                _disc = getattr(self.bot, "shadow_discover_signal", None)
                if _disc is not None:
                    _disc.maybe_emit(rec, self.pipe)
                # Schedule window resolution (idempotent per cid+wend).
                # Mirrors live bot's _capture_resolution scheduling pattern —
                # task sleeps until window_end_ts+35s then fetches kline,
                # so we don't need the market still in feed.tokens at resolve.
                res = getattr(self.bot, "shadow_resolution", None)
                if res is not None and rec["condition_id"] and rec["window_end_ts"] > 0:
                    res.schedule(
                        cid=rec["condition_id"],
                        wend=rec["window_end_ts"],
                        asset=rec["asset"],
                        outcome_dir=rec["outcome_dir"],
                        window_size_s=rec["window_size_s"],
                    )
                # Oracle sweep: register this token's side + schedule sweep at window close.
                _sweep = getattr(self.bot, "oracle_sweeper", None)
                if _sweep is not None and rec["condition_id"] and rec["window_end_ts"] > 0:
                    _sweep.register_token(
                        cid=rec["condition_id"],
                        outcome_dir=rec["outcome_dir"],
                        token_id=token_id,
                    )
                    _sweep.schedule(
                        cid=rec["condition_id"],
                        wend=rec["window_end_ts"],
                        asset=rec["asset"],
                        window_size_s=rec["window_size_s"],
                    )
                # Phase 2: hold-path evolution (per-second trajectory of virtual positions).
                self.hold_path.on_tick(rec, gt)
                self._last_emit_ts[token_id] = now_s
            except Exception:
                logger.debug("timeline build failed token=%s", token_id, exc_info=True)
        # GC stale tokens from dedup map
        if len(self._last_emit_ts) > 200:
            stale_cutoff = now_s - 600
            self._last_emit_ts = {k: v for k, v in self._last_emit_ts.items() if v > stale_cutoff}
        # GC expired virtual positions from hold-path tracker
        self.hold_path.gc_stale(now)

    def _build_record(self, token_id: str, token, now: float, remaining: float) -> Optional[dict]:
        feed = self.bot.feed
        ob = feed.get_order_book(token_id)
        if ob is None or not ob.bids or not ob.asks:
            return None
        if (now - ob.ts) > 5.0:
            return None  # stale OB

        best_bid = ob.bids[0][0]
        best_ask = ob.asks[0][0]
        mid = (best_bid + best_ask) / 2.0
        spread_abs = best_ask - best_bid
        spread_bps = (spread_abs / best_ask) * 10000.0 if best_ask > 0 else 0.0

        b3 = sum(q for _, q in ob.bids[:3])
        a3 = sum(q for _, q in ob.asks[:3])
        ob_imb_top3 = (b3 - a3) / (b3 + a3) if (b3 + a3) > 0 else 0.0

        hist = self.bot._token_ask_history.get(token_id)
        snap_30s = self._snap_pct(hist, now, 30)
        snap_60s = self._snap_pct(hist, now, 60)
        tok_history_seconds = int(now - hist[0][0]) if hist else 0

        asset_up = token.asset.upper()
        binance_spot = feed._spot_price.get(asset_up, 0.0) or 0.0
        binance_vel_5s  = self._binance_ret(asset_up, now, 5)
        binance_ret_30s = self._binance_ret(asset_up, now, 30)
        binance_ret_60s = self._binance_ret(asset_up, now, 60)
        binance_ret_5m  = self._binance_ret_5m(asset_up)

        utc = datetime.now(timezone.utc)
        wend = int(getattr(token, "window_end_ts", 0))

        # Peer-token link (sister YES↔NO of same condition_id). Lets future
        # analyses compute (yes_ask + no_ask) sum-to-1 deviations and one-sided
        # pressure at the same instant — irrecoverable later because the
        # cross-token timing pair is what matters.
        cond_id = getattr(token, "condition_id", "") or ""
        peer_token_id = ""
        peer_bid = 0.0
        peer_ask = 0.0
        peer_age_ms = 0
        arb_sum_yes_no = 0.0
        if cond_id:
            for ptid, ptok in feed.tokens.items():
                if ptid == token_id:
                    continue
                if getattr(ptok, "condition_id", "") != cond_id:
                    continue
                pob = feed.get_order_book(ptid)
                if pob is None or not pob.bids or not pob.asks:
                    peer_token_id = ptid
                    break
                peer_token_id = ptid
                peer_bid = pob.bids[0][0]
                peer_ask = pob.asks[0][0]
                peer_age_ms = int((now - pob.ts) * 1000)
                arb_sum_yes_no = round(best_ask + peer_ask, 4)
                break

        vol_reg = _vol_regime(abs(binance_ret_5m))
        trend_reg = _trend_regime(binance_ret_60s)
        liq_reg = _liquidity_regime(b3 + a3)

        # ── Kline-based Binance momentum (same source as live bot gates) ──────
        # 1m: previous closed bar vs current; 60m: 61 bars ago vs current (G1).
        buf_1m = getattr(feed, "_1m_close_buf", {}).get(asset_up)
        c0 = binance_spot
        binance_ret_1m = 0.0
        binance_ret_60m = 0.0
        if buf_1m and c0 > 0:
            if len(buf_1m) >= 2:
                c1 = buf_1m[-2]
                if c1 > 0:
                    binance_ret_1m = round((c0 - c1) / c1 * 100.0, 4)
            if len(buf_1m) >= 61:
                p60 = buf_1m[-61]
                if p60 > 0:
                    binance_ret_60m = round((c0 - p60) / p60 * 100.0, 4)

        # ── VPIN ─────────────────────────────────────────────────────────────
        vpin_t = getattr(feed, "vpin_trackers", {}).get(asset_up)
        vpin_score = 0.0
        if vpin_t and getattr(vpin_t, "_trade_count", 0) > 50:
            vpin_score = round(vpin_t.vpin, 4)

        # ── Token microstructure from ask history ─────────────────────────────
        tok_d5 = 0.0
        tok_decel = 0.0
        ask_stale_s = 999.0
        if hist and len(hist) >= 2:
            latest_ask = hist[-1][1]
            # 5s token delta
            cutoff5 = now - 5.0
            ref5 = None
            for _ts, _p in hist:
                if _ts <= cutoff5:
                    ref5 = _p
            if ref5 and ref5 > 0:
                tok_d5 = round((latest_ask - ref5) / ref5 * 100.0, 4)
            # deceleration ratio: d5s / d30s (valid only when |d30| >= 0.5%)
            if abs(snap_30s) >= 0.5 and tok_d5 != 0.0:
                tok_decel = round(tok_d5 / snap_30s, 4)
            # ask staleness: seconds since ask last changed
            hist_list = list(hist)
            for _ts, _p in reversed(hist_list):
                if abs(_p - latest_ask) > 0.005:
                    ask_stale_s = round(now - _ts, 1)
                    break
            else:
                if hist_list:
                    ask_stale_s = round(now - hist_list[0][0], 1)

        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": "market_timeline",
            "ts_s": int(now),
            "ts_ms_local": int(now * 1000),
            # market identity
            "token_id": token_id,
            "condition_id": cond_id,
            "asset": token.asset,
            "outcome_dir": getattr(token, "outcome_direction", "up"),
            "outcome_side": getattr(token, "side", "YES"),
            "window_end_ts": wend,
            "window_size_s": int(getattr(token, "window_seconds", 300)),
            "seconds_to_resolution": round(remaining, 1),
            # time
            "weekday": utc.weekday(),
            "hour_utc": utc.hour,
            "minute_utc": utc.minute,
            "session_bucket": _session_bucket(utc.hour),
            # price
            "best_bid": round(best_bid, 4),
            "best_ask": round(best_ask, 4),
            "mid": round(mid, 4),
            "spread_abs": round(spread_abs, 4),
            "spread_bps": round(spread_bps, 1),
            # OB
            "ob_top1_bid_size": round(ob.bids[0][1], 2),
            "ob_top1_ask_size": round(ob.asks[0][1], 2),
            "ob_imb_top3": round(ob_imb_top3, 4),
            "ob_book_depth_size": round(b3 + a3, 2),
            "ob_levels_bid": len(ob.bids),
            "ob_levels_ask": len(ob.asks),
            "ob_quote_age_ms": int((now - ob.ts) * 1000),
            # token momentum
            "tok_snap_30s": round(snap_30s, 4),
            "tok_snap_60s": round(snap_60s, 4),
            "tok_history_seconds": tok_history_seconds,
            # external
            "binance_spot": binance_spot,
            "binance_vel_5s_pct":  round(binance_vel_5s, 4),
            "binance_ret_30s_pct": round(binance_ret_30s, 4),
            "binance_ret_60s_pct": round(binance_ret_60s, 4),
            "binance_ret_5m_pct":  round(binance_ret_5m, 4),
            # peer-token link (YES↔NO sister of same condition_id)
            "peer_token_id": peer_token_id,
            "peer_bid": round(peer_bid, 4),
            "peer_ask": round(peer_ask, 4),
            "peer_age_ms": peer_age_ms,
            "arb_sum_yes_no": arb_sum_yes_no,
            # Phase 2 regime tags (directive #6 — non-optional, baked in from day one)
            "vol_regime": vol_reg,
            "trend_regime": trend_reg,
            "liquidity_regime": liq_reg,
            "macro_event_window": False,  # placeholder; populate with CPI/NFP/FOMC ±15min later
            # Phase 2 signal enrichment — live-gate signals for signal_analysis
            "binance_ret_1m_pct":  binance_ret_1m,   # kline close-to-close, direction gate signal
            "binance_ret_60m_pct": binance_ret_60m,  # G1 regime filter signal
            "vpin_score":          vpin_score,        # 0=neutral, >0.6=elevated toxicity
            "tok_delta_5s":        tok_d5,            # 5s token ask momentum (tok5_gate signal)
            "tok_decel_ratio":     tok_decel,         # d5s/d30s — momentum deceleration
            "ask_stale_s":         ask_stale_s,       # seconds since ask last changed
        }

    def _snap_pct(self, hist, now: float, secs: float) -> float:
        if not hist or len(hist) < 2:
            return 0.0
        latest = hist[-1][1]
        cutoff = now - secs
        ref = None
        for ts, p in hist:
            if ts <= cutoff:
                ref = p
        if ref is None or ref <= 0:
            return 0.0
        return (latest - ref) / ref * 100.0

    def _binance_ret(self, asset_up: str, now: float, secs: float) -> float:
        feed = self.bot.feed
        spot_now = feed._spot_price.get(asset_up, 0.0)
        hist = feed._price_history.get(asset_up)
        if not spot_now or not hist:
            return 0.0
        cutoff = now - secs
        ref = None
        for ts, p in hist:
            if ts <= cutoff:
                ref = p
        if ref is None or ref <= 0:
            return 0.0
        return (spot_now - ref) / ref * 100.0

    def _binance_ret_5m(self, asset_up: str) -> float:
        feed = self.bot.feed
        spot_now = feed._spot_price.get(asset_up, 0.0)
        open_5m = feed._spot_open_5m.get(asset_up, 0.0)
        if not spot_now or not open_5m:
            return 0.0
        return (spot_now - open_5m) / open_5m * 100.0

    def _build_gate_trace(self, tl: dict) -> Optional[dict]:
        ask = tl["best_ask"]
        sec = tl["seconds_to_resolution"]
        imb = tl["ob_imb_top3"]
        gates = {
            "terminal_zone": "PASS" if 25.0 <= sec <= 90.0 else f"FAIL@{sec:.0f}s",
            "ask_floor":     "PASS" if ask >= _GATE_ASK_FLOOR else f"FAIL@{ask:.2f}<{_GATE_ASK_FLOOR}",
            "ask_max":       "PASS" if ask <= _GATE_ASK_MAX   else f"FAIL@{ask:.2f}>{_GATE_ASK_MAX}",
            "ob_imb_floor":  "PASS" if imb >= _GATE_OB_IMB_FLOOR else f"FAIL@{imb:.3f}<{_GATE_OB_IMB_FLOOR}",
        }
        all_pass = all(v == "PASS" for v in gates.values())
        first_fail = next((k for k, v in gates.items() if v != "PASS"), None)
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": "gate_trace",
            "ts_s": tl["ts_s"],
            "ts_ms_local": tl["ts_ms_local"],
            "token_id": tl["token_id"],
            "condition_id": tl["condition_id"],
            "asset": tl["asset"],
            "outcome_dir": tl["outcome_dir"],
            "outcome_side": tl["outcome_side"],
            "window_end_ts": tl["window_end_ts"],
            "seconds_to_resolution": tl["seconds_to_resolution"],
            "ask": tl["best_ask"],
            "gate_results": gates,
            "all_pass": all_pass,
            "first_failed_gate": first_fail,
            "strategy_version": "shadow-passive-v2",
            "would_take_at_ask": all_pass,
        }
