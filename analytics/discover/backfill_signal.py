"""Phase 2 Discovery — Step 3 backfill of replay-side signal events.

Reads market_timeline.jsonl over the historical window, applies the same
DiscoverSignalRecorder.matches() logic, writes one record per
(token_id, window_end_ts) first-fire to discover_signal_replay.jsonl
tagged source="replay".

Joinable to:
  - logs/shadow/hot/<date>/discover_signal.jsonl (live, source="live")
  - logs/shadow/hot/<date>/window_resolution.jsonl

Idempotent: rewrites the output every run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/root/Klaus")
from data.shadow.discover_signal import matches, build_record  # noqa: E402

SHADOW_ROOT = Path("/root/Klaus/logs/shadow/hot")
DATES = ["2026-05-08", "2026-05-09", "2026-05-10"]
OUT_NAME = "discover_signal_replay.jsonl"


def backfill(dates=DATES) -> int:
    n_total = 0
    n_emit = 0
    for d in dates:
        in_path = SHADOW_ROOT / d / "market_timeline.jsonl"
        if not in_path.exists():
            print(f"  skip {d}: no market_timeline.jsonl")
            continue
        out_path = SHADOW_ROOT / d / OUT_NAME
        seen = set()
        emit_d = 0
        rows_d = 0
        with in_path.open() as fin, out_path.open("w") as fout:
            for line in fin:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                rows_d += 1
                if not matches(rec):
                    continue
                key = (rec["token_id"], int(rec.get("window_end_ts", 0) or 0))
                if key in seen:
                    continue
                seen.add(key)
                out = build_record(rec, source="replay")
                fout.write(json.dumps(out, separators=(",", ":")) + "\n")
                emit_d += 1
        n_total += rows_d
        n_emit += emit_d
        print(f"  {d}: {rows_d:>9,} rows -> {emit_d:>4} replay first-fires -> {out_path}")
    print(f"\nTOTAL: {n_total:,} rows scanned -> {n_emit} replay first-fires written")
    return n_emit


if __name__ == "__main__":
    backfill()
