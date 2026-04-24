"""
Autonomous research agent — runs every 30 minutes as a background task.

Objective: find anything that makes this operation more profitable.
No prescribed framework. The agent decides what to look at and what matters.
Findings are published to logs/research_notes.jsonl and made available
to the entry agent via the get_research_notes tool.
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

NOTES_PATH  = Path("logs/research_notes.jsonl")
TRADES_PATH = Path("logs/trades.jsonl")
SHADOW_PATH = Path("logs/llm_shadow.jsonl")

_INTERVAL_S = 1800.0  # 30 minutes


class ResearchAgent:
    def __init__(self, api_key: str):
        self._api_key  = api_key
        self._enabled  = bool(api_key)
        self._last_run = 0.0

    def due(self) -> bool:
        return self._enabled and (time.time() - self._last_run) >= _INTERVAL_S

    async def run(self, tokens: dict) -> int:
        """One research cycle. Returns number of findings published."""
        if not self._enabled:
            return 0
        self._last_run = time.time()

        trades  = self._load_trades(500)
        shadow  = self._load_shadow(200)
        perf    = self._compute_perf(trades)
        catalog = self._build_catalog(tokens)
        notes   = self._load_notes(20)

        _data = {
            "get_trade_log":            trades[:100],
            "get_shadow_log":           shadow[:100],
            "get_market_catalog":       catalog,
            "get_performance_breakdown": perf,
            "get_existing_notes":       notes,
        }

        tools = [
            {
                "name": "get_trade_log",
                "description": (
                    "Last 100 live closed trades: asset, direction, zone, "
                    "entry_price, exit_price, net_pnl_actual, exit_reason, "
                    "ts_open, window_seconds, signal_source."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_shadow_log",
                "description": (
                    "Last 100 LLM entry decisions (TAKE/SKIP) merged with "
                    "exit outcomes: asset, direction, zone, llm_decision, "
                    "llm_conf, llm_reason, entry_price, exit_reason, "
                    "shadow_gross_pnl, hold_seconds."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_market_catalog",
                "description": (
                    "All Polymarket tokens currently tracked: asset, side, "
                    "market_type, window_seconds, remaining_seconds."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_performance_breakdown",
                "description": (
                    "Pre-computed win rate and profit factor split by asset, "
                    "UTC hour, zone, direction, and exit reason."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_existing_notes",
                "description": "Your 20 most recent published findings (to avoid duplicating).",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "publish",
                "description": "Publish one finding. Call once per distinct insight.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "finding":    {"type": "string", "description": "The insight, up to 200 words"},
                        "confidence": {"type": "number",  "description": "0.5–0.95"},
                        "category":   {"type": "string",  "description": "e.g. timing / signal / market_structure / risk / opportunity / anomaly"},
                        "action":     {"type": "string",  "description": "Concrete suggestion for the entry or exit agent, up to 100 words"},
                    },
                    "required": ["finding", "confidence", "category", "action"],
                },
            },
            {
                "name": "done",
                "description": "End this research cycle.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ]

        system_prompt = (
            "You are an autonomous trading research agent exploring BTC, ETH, and SOL "
            "5-minute binary markets.\n\n"
            "Your mission is to discover ANY structure, pattern, or mechanism that could "
            "improve long-term profitability, including non-obvious and counterintuitive ones.\n\n"
            "You are NOT optimizing for plausibility. You are optimizing for discovery.\n\n"
            "---\n\n"
            "### Thinking modes (you should freely switch between them):\n\n"
            "1. PARANOID MODE\n"
            "Assume current system understanding is wrong.\n"
            "Look for hidden failure patterns, distortions, and systematic misreads.\n\n"
            "2. ALIEN MODE\n"
            "Assume the market does NOT behave like standard financial theory.\n"
            "Invent alternative explanations for price movement (including unusual or asymmetric mechanisms).\n\n"
            "3. FAILURE MODE\n"
            "Ignore wins. Focus only on where and why edges break.\n"
            "Find regime boundaries, collapse conditions, and hidden traps.\n\n"
            "4. EXPLOIT MODE\n"
            "Assume patterns are exploitable only in narrow or unstable conditions.\n"
            "Search for fragile but high-edge opportunities.\n\n"
            "---\n\n"
            "### Freedom rules:\n"
            "- You are allowed to speculate aggressively.\n"
            "- You are allowed to propose ideas that contradict each other.\n"
            "- You are allowed to propose ideas that seem \"wrong\" at first glance.\n"
            "- You are NOT required to be consistent across findings.\n\n"
            "---\n\n"
            "### Important:\n"
            "Do NOT filter ideas for realism.\n"
            "Do NOT remove ideas because they feel unlikely.\n"
            "Do NOT optimize for clarity over discovery.\n\n"
            "Conflicting ideas are expected.\n\n"
            "---\n\n"
            "### Output format (loose, not rigid):\n\n"
            "You may output any of:\n"
            "- strange hypotheses\n"
            "- unusual market mechanisms\n"
            "- broken assumptions in current trading logic\n"
            "- regime-specific \"weird behavior\"\n"
            "- contradictions between datasets\n"
            "- failure signatures before losses\n\n"
            "For each idea, optionally include:\n"
            "- why it might exist\n"
            "- when it appears\n"
            "- how it breaks\n"
            "- how it could be tested\n\n"
            "---\n\n"
            "### Core objective:\n"
            "Maximize discovery of non-obvious trading edges, even if they are unstable, weird, or partially wrong.\n\n"
            "Stop when no further fundamentally different ideas come to mind."
        )

        messages: list = [{"role": "user", "content": "Run your research cycle. Use publish() for each finding. Do not output analysis as text — call the tool."}]
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        n_published = 0

        try:
            import aiohttp, asyncio as _aio
            async with aiohttp.ClientSession() as sess:
                for _ in range(8):
                    payload = {
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 800,
                        "system": system_prompt,
                        "tools": tools,
                        "messages": messages,
                    }
                    # Retry up to 3 times on 429 with backoff
                    for _attempt in range(3):
                        async with sess.post(
                            "https://api.anthropic.com/v1/messages",
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as resp:
                            if resp.status == 429:
                                if _attempt < 2:
                                    await _aio.sleep(10 * (2 ** _attempt))
                                    continue
                                raise Exception(f"API 429 after retries")
                            if resp.status != 200:
                                raise Exception(f"API {resp.status}: {(await resp.text())[:80]}")
                            data = await resp.json()
                            break

                    blocks = data.get("content", [])
                    tool_results = []
                    stop = False

                    for block in blocks:
                        if block.get("type") != "tool_use":
                            continue
                        name = block["name"]
                        inp  = block.get("input", {})
                        bid  = block["id"]

                        if name == "done":
                            stop = True
                            tool_results.append({
                                "type": "tool_result", "tool_use_id": bid,
                                "content": "Cycle complete.",
                            })
                            break

                        elif name == "publish":
                            note = {
                                "ts":         time.time(),
                                "finding":    str(inp.get("finding", ""))[:2000],
                                "confidence": max(0.5, min(0.95, float(inp.get("confidence", 0.6)))),
                                "category":   str(inp.get("category", "general")),
                                "action":     str(inp.get("action", ""))[:1000],
                            }
                            self._write_note(note)
                            n_published += 1
                            logger.info(
                                "RESEARCH [%s] conf=%.2f | %s",
                                note["category"], note["confidence"],
                                note["finding"][:120],
                            )
                            tool_results.append({
                                "type": "tool_result", "tool_use_id": bid,
                                "content": f"Published #{n_published}.",
                            })

                        elif name in _data:
                            tool_results.append({
                                "type": "tool_result", "tool_use_id": bid,
                                "content": json.dumps(_data[name]),
                            })

                        else:
                            tool_results.append({
                                "type": "tool_result", "tool_use_id": bid,
                                "content": f"Unknown tool: {name}", "is_error": True,
                            })

                    if stop or data.get("stop_reason") == "end_turn" or not tool_results:
                        break

                    messages.append({"role": "assistant", "content": blocks})
                    messages.append({"role": "user",      "content": tool_results})

        except Exception as exc:
            logger.warning("ResearchAgent cycle failed: %s", exc)

        logger.info("RESEARCH cycle complete — %d findings published", n_published)
        return n_published

    # ── Data loaders ─────────────────────────────────────────────────────────

    def _load_trades(self, n: int) -> list:
        rows = []
        try:
            with open(TRADES_PATH) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
        return list(reversed(rows[-n:]))

    def _load_shadow(self, n: int) -> list:
        entries: dict = {}
        exits:   dict = {}
        try:
            with open(SHADOW_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    tid = r.get("token_id", "")
                    if r.get("record_type") == "llm_entry":
                        entries[tid] = r
                    elif r.get("record_type") == "llm_exit":
                        exits[tid] = r
        except FileNotFoundError:
            pass
        rows = [{**e, **exits.get(tid, {})} for tid, e in entries.items()]
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows[:n]

    def _compute_perf(self, trades: list) -> dict:
        live = [t for t in trades if t.get("is_live") and t.get("entry_price", 0) > 0]

        def _stats(rows: list) -> dict:
            pnls = [float(r.get("net_pnl_actual", r.get("gross_pnl", 0)) or 0) for r in rows]
            if not pnls:
                return {"n": 0}
            wins   = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else None
            return {
                "n":         len(pnls),
                "wr_pct":    round(len(wins) / len(pnls) * 100, 1),
                "pf":        round(pf, 2) if pf else None,
                "total_pnl": round(sum(pnls), 2),
                "avg_win":   round(sum(wins)   / len(wins),   3) if wins   else 0,
                "avg_loss":  round(sum(losses) / len(losses), 3) if losses else 0,
            }

        by_asset: dict = defaultdict(list)
        by_hour:  dict = defaultdict(list)
        by_zone:  dict = defaultdict(list)
        by_dir:   dict = defaultdict(list)
        by_exit:  dict = defaultdict(list)

        for t in live:
            by_asset[t.get("asset", "?")].append(t)
            h = datetime.fromtimestamp(t.get("ts_open", 0), tz=timezone.utc).hour
            by_hour[h].append(t)
            by_zone[t.get("zone", "?")].append(t)
            by_dir[t.get("direction", "?")].append(t)
            by_exit[t.get("exit_reason", "?")].append(t)

        return {
            "overall":           _stats(live),
            "by_asset":          {k: _stats(v) for k, v in sorted(by_asset.items())},
            "by_hour_utc":       {str(k): _stats(v) for k, v in sorted(by_hour.items())},
            "by_zone":           {k: _stats(v) for k, v in by_zone.items()},
            "by_direction":      {k: _stats(v) for k, v in by_dir.items()},
            "by_exit_reason":    {k: _stats(v) for k, v in by_exit.items()},
        }

    def _build_catalog(self, tokens: dict) -> list:
        now = time.time()
        return [
            {
                "asset":           getattr(t, "asset",          "?"),
                "side":            getattr(t, "side",           "?"),
                "market_type":     getattr(t, "market_type",    "?"),
                "window_seconds":  getattr(t, "window_seconds",  0),
                "remaining_seconds": round(max(0.0, getattr(t, "window_end_ts", 0) - now)),
            }
            for t in list(tokens.values())[:50]
        ]

    def _load_notes(self, n: int) -> list:
        rows = []
        try:
            with open(NOTES_PATH) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows[:n]

    def _write_note(self, note: dict) -> None:
        NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES_PATH, "a") as f:
            f.write(json.dumps(note) + "\n")
