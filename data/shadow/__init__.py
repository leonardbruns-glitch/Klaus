"""Shadow market observation engine — Phase 1 base substrate.

Three writers run alongside the live trading loop:
  - TimelineSampler   → logs/shadow/hot/<date>/market_timeline.jsonl
                      → logs/shadow/hot/<date>/gate_trace.jsonl
  - ResolutionWriter  → logs/shadow/hot/<date>/window_resolution.jsonl

All emit through ShadowPipeline (single async queue + batched JSONL writer,
drop-on-full). No coupling to live trading state — read-only over feed caches.
"""
from .pipeline import ShadowPipeline
from .timeline import TimelineSampler
from .resolution import ResolutionWriter

__all__ = ["ShadowPipeline", "TimelineSampler", "ResolutionWriter"]
