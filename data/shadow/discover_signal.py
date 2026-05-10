"""Discover-signal recorder — Step 3 of Phase 2 deploy validation.

Strictly passive. Records raw market state at the moment the single
surviving signal family fires:

    arb_sum_yes_no < 0.99
    AND outcome_dir == "down"
    AND 0.10 <= best_ask <= 0.55
    AND 60 <= seconds_to_resolution <= 240

Per (token_id, window_end_ts) first-fire dedup. One record per window.
Raw fields only — no derived features. Joinable to window_resolution.jsonl
via (condition_id, window_end_ts).

source="live"   — emitted by TimelineSampler in production
source="replay" — emitted by the offline backfill over historical parquet
"""
from typing import Set, Tuple

from .pipeline import ShadowPipeline

SCHEMA_VERSION = 1
RECORD_TYPE = "discover_signal"


def matches(rec: dict) -> bool:
    arb = rec.get("arb_sum_yes_no", 0.0) or 0.0
    if not (0.0 < arb < 0.99):
        return False
    if rec.get("outcome_dir") != "down":
        return False
    ask = rec.get("best_ask", 0.0) or 0.0
    if not (0.10 <= ask <= 0.55):
        return False
    rem = rec.get("seconds_to_resolution", 0)
    if rem is None:
        return False
    if not (60 <= rem <= 240):
        return False
    return True


def build_record(rec: dict, source: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "source": source,
        "ts_s": rec["ts_s"],
        "ts_ms_local": rec.get("ts_ms_local", rec["ts_s"] * 1000),
        "token_id": rec["token_id"],
        "condition_id": rec.get("condition_id", ""),
        "asset": rec.get("asset", ""),
        "outcome_dir": rec.get("outcome_dir", ""),
        "outcome_side": rec.get("outcome_side", ""),
        "window_end_ts": rec.get("window_end_ts", 0),
        "seconds_to_resolution": rec.get("seconds_to_resolution", 0),
        "best_ask": rec.get("best_ask", 0.0),
        "best_bid": rec.get("best_bid", 0.0),
        "ob_top1_ask_size": rec.get("ob_top1_ask_size", 0.0),
        "ob_top1_bid_size": rec.get("ob_top1_bid_size", 0.0),
        "peer_token_id": rec.get("peer_token_id", ""),
        "peer_ask": rec.get("peer_ask", 0.0),
        "peer_bid": rec.get("peer_bid", 0.0),
        "peer_age_ms": rec.get("peer_age_ms", 0),
        "arb_sum_yes_no": rec.get("arb_sum_yes_no", 0.0),
    }


class DiscoverSignalRecorder:
    """First-fire recorder for the surviving Phase 2 signal family.

    Hook from TimelineSampler._sample_once:
        rec = self._build_record(...)
        self.pipe.emit(rec)
        disc = getattr(self.bot, "shadow_discover_signal", None)
        if disc is not None:
            disc.maybe_emit(rec, self.pipe)

    Stateless across restart (in-memory dedup). On daemon restart a window
    can re-fire — accept it; downstream join by (token_id, window_end_ts)
    keeps the earliest by ts_s.
    """

    def __init__(self, pipe: ShadowPipeline) -> None:
        self.pipe = pipe
        self._seen: Set[Tuple[str, int]] = set()

    def maybe_emit(self, rec: dict, pipe: ShadowPipeline) -> None:
        if not matches(rec):
            return
        key = (rec["token_id"], int(rec.get("window_end_ts", 0) or 0))
        if key in self._seen:
            return
        self._seen.add(key)
        pipe.emit(build_record(rec, source="live"))

    def gc(self, retain_max: int = 5000) -> None:
        if len(self._seen) > retain_max:
            self._seen.clear()
