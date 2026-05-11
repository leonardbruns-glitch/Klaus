"""Shadow market observation engine — Phase 2.

Writers running alongside the live trading loop:
  - TimelineSampler   → market_timeline.jsonl, gate_trace.jsonl
  - HoldPathSampler   → hold_path.jsonl  (Phase 2: per-second trajectory of virtual positions)
  - ResolutionWriter  → window_resolution.jsonl
  - ExitPolicyShadow  → exit_policy_shadow.jsonl

All emit through ShadowPipeline (single async queue + batched JSONL writer,
drop-on-full). No coupling to live trading state — read-only over feed caches.
HoldPathSampler is owned by TimelineSampler; no separate start/stop needed.
"""
from .holdpath import HoldPathSampler
from .pipeline import ShadowPipeline
from .timeline import TimelineSampler
from .resolution import ResolutionWriter
from .exit_policy import ExitPolicyShadow
from .discover_signal import DiscoverSignalRecorder
from .trade import emit_token_trade, emit_binance_trade
from .ob_delta import emit_ob_delta
from .order_lifecycle import emit_order_event
from .liquidation import emit_liquidation

__all__ = [
    "HoldPathSampler", "ShadowPipeline", "TimelineSampler", "ResolutionWriter",
    "ExitPolicyShadow", "DiscoverSignalRecorder",
    "emit_token_trade", "emit_binance_trade", "emit_ob_delta", "emit_order_event",
    "emit_liquidation",
]
