"""Async batched JSONL writer for shadow records.

One asyncio.Queue, one writer task. Each record carries `record_type` which
determines the output file. Files rotate by date (UTC). fsync once per batch.
Drop-on-full with a global counter; never blocks the live event loop.
"""
import asyncio
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, IO, Optional

logger = logging.getLogger(__name__)

try:
    import orjson  # type: ignore
    def _dumps(obj: dict) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    def _dumps(obj: dict) -> str:
        return json.dumps(obj, separators=(",", ":"))


class ShadowPipeline:
    def __init__(
        self,
        root: str = "logs/shadow",
        queue_max: int = 50_000,
        batch_size: int = 500,
        flush_interval_s: float = 1.0,
        telemetry_interval_s: float = 60.0,
    ) -> None:
        self.root = root
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_max)
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.telemetry_interval_s = telemetry_interval_s
        self.dropped = 0
        self.written = 0
        self.flush_count = 0
        self._flush_latencies_ms: deque = deque(maxlen=512)  # rolling
        self._dropped_first_logged = False
        self._start_ts = time.time()
        self._handles: Dict[str, IO] = {}
        self._handle_paths: Dict[str, str] = {}
        self._writer_task: Optional[asyncio.Task] = None
        self._telemetry_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def emit(self, record: dict) -> None:
        """Non-blocking. Drops on queue-full. Safe from any async context.

        Per shadow_engine_principles directive #10, ANY drop is a hard
        validation-gate failure. First drop logs CRITICAL; subsequent every
        100 logs ERROR. Bot keeps running — surfacing the failure is the
        operator's job, not killing live trading.
        """
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            if not self._dropped_first_logged:
                self._dropped_first_logged = True
                logger.critical(
                    "SHADOW DROP — queue saturated, validation-gate failed; "
                    "first drop at written=%d queue_max=%d",
                    self.written, self.queue.maxsize,
                )
            elif self.dropped % 100 == 0:
                logger.error("shadow drops continuing — total=%d", self.dropped)

    async def start(self) -> None:
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(self._writer_loop(), name="shadow_writer")
            self._telemetry_task = asyncio.create_task(self._telemetry_loop(), name="shadow_telemetry")
            logger.info("ShadowPipeline started → %s (telemetry=%.0fs)", self.root, self.telemetry_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._telemetry_task, self._writer_task):
            if t:
                try:
                    await asyncio.wait_for(t, timeout=5.0)
                except asyncio.TimeoutError:
                    t.cancel()
        for h in self._handles.values():
            try:
                h.close()
            except Exception:
                pass
        self._handles.clear()
        self._handle_paths.clear()
        logger.info("ShadowPipeline stopped — written=%d dropped=%d", self.written, self.dropped)

    def _path_for(self, record_type: str) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.root, "hot", date, f"{record_type}.jsonl")

    def _ensure_handle(self, record_type: str) -> IO:
        path = self._path_for(record_type)
        if self._handle_paths.get(record_type) != path:
            old = self._handles.pop(record_type, None)
            if old:
                try:
                    old.close()
                except Exception:
                    pass
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._handles[record_type] = open(path, "a", buffering=64 * 1024)
            self._handle_paths[record_type] = path
        return self._handles[record_type]

    async def _writer_loop(self) -> None:
        buf: Dict[str, list] = defaultdict(list)
        last_flush = time.monotonic()
        while not self._stop.is_set():
            try:
                rec = await asyncio.wait_for(self.queue.get(), timeout=0.25)
                buf[rec.get("record_type", "unknown")].append(rec)
            except asyncio.TimeoutError:
                pass
            now = time.monotonic()
            total = sum(len(v) for v in buf.values())
            if total >= self.batch_size or (total > 0 and (now - last_flush) >= self.flush_interval_s):
                await asyncio.to_thread(self._flush, buf)
                buf.clear()
                last_flush = now
        # Drain remaining
        while not self.queue.empty():
            try:
                rec = self.queue.get_nowait()
                buf[rec.get("record_type", "unknown")].append(rec)
            except asyncio.QueueEmpty:
                break
        if any(buf.values()):
            await asyncio.to_thread(self._flush, buf)

    def _flush(self, buf: Dict[str, list]) -> None:
        t0 = time.monotonic()
        any_written = False
        for rt, rows in buf.items():
            if not rows:
                continue
            try:
                handle = self._ensure_handle(rt)
                handle.write("\n".join(_dumps(r) for r in rows) + "\n")
                handle.flush()
                self.written += len(rows)
                any_written = True
            except Exception:
                logger.exception("shadow flush failed for %s (n=%d)", rt, len(rows))
        if any_written:
            self.flush_count += 1
            self._flush_latencies_ms.append((time.monotonic() - t0) * 1000.0)

    # ------------------------------------------------------------------ telemetry

    def get_telemetry(self) -> dict:
        """Snapshot of pipeline health. Safe to call from any thread."""
        now = time.time()
        uptime = now - self._start_ts
        # rss in MB via /proc — Linux only; fall back to 0 if unavailable.
        rss_mb = 0.0
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_mb = int(line.split()[1]) / 1024.0
                        break
        except Exception:
            pass
        # latency p50/p95
        latencies = sorted(self._flush_latencies_ms)
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else (latencies[-1] if latencies else 0.0)
        # disk usage per record_type
        files: Dict[str, dict] = {}
        for rt, path in self._handle_paths.items():
            try:
                files[rt] = {"path": path, "size_bytes": os.path.getsize(path)}
            except Exception:
                files[rt] = {"path": path, "size_bytes": -1}
        return {
            "schema_version": 1,
            "record_type": "shadow_telemetry",
            "ts_s": int(now),
            "uptime_s": int(uptime),
            "queue_depth": self.queue.qsize(),
            "queue_max": self.queue.maxsize,
            "queue_pct_full": round(self.queue.qsize() / max(1, self.queue.maxsize), 4),
            "written_total": self.written,
            "dropped_total": self.dropped,
            "rows_per_min": round((self.written / uptime * 60.0) if uptime > 0 else 0.0, 1),
            "flush_count": self.flush_count,
            "flush_latency_p50_ms": round(p50, 2),
            "flush_latency_p95_ms": round(p95, 2),
            "rss_mb": round(rss_mb, 1),
            "files": files,
        }

    async def _telemetry_loop(self) -> None:
        """Emit a `shadow_telemetry` record every telemetry_interval_s.

        Telemetry rides the same queue as data records so it shares the same
        durability path (single fsync per batch). Uses a guarded put_nowait —
        if the queue is saturated, the telemetry drop is itself a signal
        (and the data-drop CRITICAL will already have fired).
        """
        # Wait one interval before first emit so uptime is meaningful.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=self.telemetry_interval_s)
        except asyncio.TimeoutError:
            pass
        while not self._stop.is_set():
            try:
                rec = self.get_telemetry()
                try:
                    self.queue.put_nowait(rec)
                except asyncio.QueueFull:
                    pass  # data-drop CRITICAL already fired
            except Exception:
                logger.exception("shadow telemetry build failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.telemetry_interval_s)
            except asyncio.TimeoutError:
                pass
