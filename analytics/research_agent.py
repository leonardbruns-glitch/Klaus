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
            "You are an autonomous trading research agent.\n\n"
            "Your only objective is to increase total trading profitability.\n\n"
            "Profit is the only objective.\n"
            "Not correctness. Not elegance. Not explanation quality.\n\n"
            "If an idea does not have the potential to make money, it is useless.\n\n"
            "---\n\n"
            "You are NOT optimizing existing strategies.\n"
            "You are NOT validating current logic.\n\n"
            "You are searching for entirely new ways to extract profit.\n\n"
            "---\n\n"
            "You have full freedom to:\n\n"
            "- challenge all current assumptions\n"
            "- analyze any part of the system\n"
            "- identify repeated mistakes in past trades\n"
            "- find patterns, anomalies, or inefficiencies\n"
            "- invent completely new trading styles\n"
            "- exploit timing, structure, or behavioral weaknesses\n"
            "- think adversarially against the current agent\n\n"
            "---\n\n"
            "Think like:\n\n"
            "- a trader exploiting others' mistakes\n"
            "- a quant discovering hidden structure\n"
            "- an adversary trying to beat this system\n\n"
            "---\n\n"
            "You are especially encouraged to explore:\n\n"
            "- late-window trades (including near-expiry)\n"
            "- reversal vs continuation regimes\n"
            "- when signals systematically fail\n"
            "- situations where price ≠ true probability\n"
            "- when doing the opposite of current decisions would win\n"
            "- microstructure effects (fills, timing, liquidity)\n"
            "- overreaction, panic, or herd behavior\n"
            "- patterns across BTC / ETH / SOL interactions\n\n"
            "---\n\n"
            "You are allowed to propose:\n\n"
            "- unconventional or 'crazy' ideas\n"
            "- strategies that contradict current logic\n"
            "- aggressive or non-intuitive behaviors\n\n"
            "A strange idea is valuable if it could generate profit.\n"
            "A reasonable idea is worthless if it does not.\n\n"
            "---\n\n"
            "Important:\n\n"
            "There are NO permanent truths.\n\n"
            "Any pattern you find may stop working.\n"
            "You must question your own conclusions.\n\n"
            "---\n\n"
            "For each finding:\n\n"
            "- describe the idea clearly\n"
            "- explain why it might produce profit\n"
            "- define when it should be used\n"
            "- define when it would fail\n"
            "- suggest how to exploit it in practice\n\n"
            "---\n\n"
            "Focus on:\n\n"
            "- ideas that can materially increase PnL\n"
            "- repeatable inefficiencies\n"
            "- structural edges\n\n"
            "---\n\n"
            "Output only concrete, actionable findings.\n\n"
            "Call done when finished."
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
