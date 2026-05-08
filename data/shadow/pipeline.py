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
from collections import defaultdict
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
    ) -> None:
        self.root = root
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_max)
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.dropped = 0
        self.written = 0
        self._handles: Dict[str, IO] = {}
        self._handle_paths: Dict[str, str] = {}
        self._writer_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def emit(self, record: dict) -> None:
        """Non-blocking. Drops on queue-full. Safe from any async context."""
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                logger.warning("shadow queue full — dropped=%d", self.dropped)

    async def start(self) -> None:
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(self._writer_loop(), name="shadow_writer")
            logger.info("ShadowPipeline started → %s", self.root)

    async def stop(self) -> None:
        self._stop.set()
        if self._writer_task:
            try:
                await asyncio.wait_for(self._writer_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._writer_task.cancel()
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
        for rt, rows in buf.items():
            if not rows:
                continue
            try:
                handle = self._ensure_handle(rt)
                handle.write("\n".join(_dumps(r) for r in rows) + "\n")
                handle.flush()
                self.written += len(rows)
            except Exception:
                logger.exception("shadow flush failed for %s (n=%d)", rt, len(rows))
