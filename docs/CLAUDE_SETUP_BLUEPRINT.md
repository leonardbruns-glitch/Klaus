# Klaus — Claude Code "Perfect Machine" Blueprint

> Research + audit findings for optimizing the Claude-run Polymarket bot operation
> (performance AND cost). Compiled 2026-06-07. Status: research complete through
> manual deep-research + setup audit; the 7-dimension verification workflow was
> stopped early (credits) — re-run via the saved script if desired:
> `~/.claude/projects/-root-Klaus/.../workflows/scripts/klaus-perfect-machine-*.js`

---

## A. AUDIT OF CURRENT SETUP (facts, not opinions)

**Two separate credit ledgers — never conflate:**
1. **Claude Code subscription** = interactive dev sessions (Opus 4.8). Cost dominated
   by the fixed preamble (CLAUDE.md + memory) loaded on EVERY message.
2. **`ANTHROPIC_API_KEY` in `.env`** = the bot's own calls — `macro_engine.py` (Haiku
   4.5, many small calls, max_tokens 80–400) + `research_agent.py` (Sonnet 4.6, 1×800).
   Already well-engineered model choices. Runs as asyncio tasks in `main.py`.

**Findings:**
| # | Severity | Finding |
|---|---|---|
| 1 | 🔴 | **MEMORY.md = 34.7 KB, over the 24.4 KB limit → silently truncating.** Losing recall every session. 126 files, many describe RETIRED strategies (TERMINAL, CAS, VOLARB, taker-fade, MM-fingerprint). Bot is STWA-only now. |
| 2 | 🟡 | **CLAUDE.md = 15 KB (~3.8k tok)** loaded every message; embeds full math core + dead-end history that isn't needed per-message. |
| 3 | 🔴 | **Zero hooks configured.** Biggest gap vs "system that prompts itself". |
| 4 | 🟡 | **No `env` tuning** in `~/.claude/settings.json` (only model/theme/workflows). |
| 5 | 🟢 | **No plugins enabled, no MCP servers** — correct; keep it. |
| 6 | 🟡 | **Bot API calls use no prompt caching, no Batches API** — every call pays full input cost. |
| 7 | 🟢 | OS crons (7 Python jobs) + systemd timers are Claude-free. Good. |
| 8 | 🟢 | Real Polymarket stack: `py-clob-client` 0.34.6 + `py_clob_client_v2` 1.0.0, `web3` 7.15. |

---

## B. THE 7-LAYER MENTAL MODEL

A perfect setup = each layer doing ONE job, so you stop hand-holding:

| Layer | Job | Loads when | Klaus status |
|---|---|---|---|
| CLAUDE.md | Always-on identity/rules | every message | 🟡 too big |
| Memory | Curated long-term facts | every session (index) | 🔴 truncating |
| Skills | On-demand playbooks | only when triggered | 🔴 none built |
| Hooks | Automation + guardrails | lifecycle events | 🔴 none |
| Subagents | Context isolation for heavy reads | on delegation | 🟡 no policy |
| Routines | Autonomous cadence | on schedule | 🟢 good |
| Settings/env | Cost & model governance | always | 🟡 untuned |

Core principle (Anthropic cost doc): **move instructions from CLAUDE.md → skills**,
**offload processing → hooks**. Keep the always-on layer tiny.

---

## C. SETTINGS / ENV BLOCK (pure wins) — `~/.claude/settings.json`

```json
{
  "model": "opus",
  "enableWorkflows": true,
  "skipWorkflowUsageWarning": true,
  "theme": "dark",
  "env": {
    "DISABLE_TELEMETRY": "1",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
    "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
    "MAX_MCP_OUTPUT_TOKENS": "8000"
  }
}
```
- `DISABLE_NON_ESSENTIAL_MODEL_CALLS`/`DISABLE_TELEMETRY` = free win.
- `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` = Explore/research subagents off Opus.
- `MAX_MCP_OUTPUT_TOKENS` = caps runaway output (your logs are huge).

**DO NOT (X hype that's wrong for a capital-at-risk bot):**
- ❌ `MAX_THINKING_TOKENS=8000` — reasoning decides real money; thinking is the
  cheapest insurance. Leave default.
- ❌ `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` — early compaction is LOSSY; forensic
  sessions (oracle/running-max audits) need full detail. Use `/clear` between
  unrelated tasks + `/compact Focus on STWA calibration + param changes` instead.

---

## D. CLAUDE.md — cut to <200 lines
- **Keep:** what's live, params table, kill switches, protocol pointers, deploy cmd,
  coding + anti-sycophancy rules.
- **Move to `docs/STWA_MATH.md`** (read on demand): Langevin/Kalman derivation,
  recalibration math, dead-end map.
- Saves ~1.5–2k tokens PER MESSAGE.

---

## E. SKILLS TO BUILD (load-on-demand playbooks, `~/.claude/skills/<name>/SKILL.md`)
Frontmatter `description` = trigger; body <500 lines.

| Skill | Triggers when | Fixes |
|---|---|---|
| `stwa-preflight` | "what's firing / live status" | Runs DATA PRIMACY PROTOCOL: STWA_LIVE, resolved WEATHER_STWA count, shadow logs, kill switches. |
| `trades-query` | reading trades.jsonl / shadow logs | Schema gotchas: `ts_open` not `timestamp`; shadow logs ≠ trades.jsonl; WEATHER_STWA tag. Kills the recurring bug. |
| `stwa-calibration` | pricer/isotonic/σ/Brier work | Wraps backtest scripts + n≥100 gate + anti-sycophancy. |
| `lockout-validate` | lockout-NO analysis | Gates: margin≥0.5°C, oracle-clean, block HK. |
| `deploy-stwa` | "deploy/restart klaus" | Non-negotiable: edit local→commit→push dev→SSH deploy; never edit on VPS. |
| `kill-switch-check` | PnL/halt/ruin questions | WR/PF/daily-loss/bankroll vs floors; bankroll.json NOT authoritative (manual sells). |

Skill listing budget: ~15–25 skills before names truncate at default 1%. 6 custom +
built-ins is fine. Don't pad.

**Built-ins already useful — keep:** `/code-review` (+`ultra`), `/security-review`,
`/deep-research`, `/verify`, `/loop`, `/schedule`.

---

## F. HOOKS — the self-prompting / guardrail layer (biggest gap)
12 lifecycle events; handler types = command/HTTP/prompt/agent; exit code 2 blocks.

- **SessionStart** → inject last 10 `state_log.md` entries + STWA_LIVE + open-position
  count + kill-switch snapshot. Automates the mandatory protocol (free, never skipped).
- **PreToolUse (Bash on trades.jsonl)** → inject schema reminder before query runs.
- **PreToolUse (Edit/Write on `strategy/*engine*.py`)** → block-with-warning unless
  turn cites n≥100 (enforces Tier-3 rule mechanically).
- **PostToolUse (Edit on *.py)** → `python -m py_compile`, surface syntax errors.
- **Stop** → remind to append `state_log.md` if any param/config changed this turn.

Converts written discipline into harness-enforced guarantees.

---

## G. SUBAGENTS — policy
Cost ~3–6× tokens, save 50–80% wall-clock.
- **Use** for: sweeping shadow logs, multi-city calibration backtests, "search 5 ways."
  Run on Sonnet (env var).
- **Don't** for: single targeted reads / quick stats.
- Worktree isolation only when agents edit files in parallel.

---

## H. MCP — install NOTHING (deliberate)
Anthropic cost doc: prefer CLI/direct API — more context-efficient (no per-tool
listing). Bot already talks Gamma/CLOB over direct HTTP + py-clob-client. A Polymarket
MCP would ADD fixed context for zero new capability. Keep marketplace cloned, enable none.

---

## I. SCHEDULED ROUTINES — one safe addition
Python crons stay Claude-free (correct). Add ONE Claude routine: a **read-only daily
sentinel** (headless `claude -p`, Sonnet, env-explicit cron — cron doesn't load profile,
set ANTHROPIC_API_KEY inline) that reads `state_log.md` + resolved_feedback and REPORTS
kill-switch breaches / WR-PF drift / n≥100 crossings. **Report only. Never change params
/ deploy / commit.** (Tier-3 rule.)

---

## J. BOT'S OWN API CALLS — optimization candidates
- **Prompt caching** (`cache_control: {type: "ephemeral"}`): if macro_engine/research
  reuse a large shared system prompt, cache it (read ~−90%, write +25%, 5-min TTL;
  1-hr beta available). Benefit scales with shared-input size — verify prompt sizes first.
- **Message Batches API** (50% discount, async): for NON-latency-critical research/
  classification, batch instead of live calls. NOT for execution-path calls.
- Model routing already good (Haiku classify / Sonnet research). Keep.
- Structured outputs / tool-use for reliable JSON instead of parsing free text.

---

## K. PRIORITIZED ROADMAP
1. 🔴 NOW (lossy bug): fix MEMORY.md truncation + archive retired-strategy memories.
2. 🔴 NOW (free): add the `env` block (§C).
3. 🟡 WEEK (highest leverage): build `stwa-preflight` + `trades-query` skills +
   SessionStart hook + trades.jsonl PreToolUse hook.
4. 🟡 THEN: slim CLAUDE.md → docs/STWA_MATH.md; build remaining 4 skills + hooks.
5. 🟢 OPTIONAL: read-only daily sentinel routine; bot-side prompt caching/batching.

---

## SOURCES
- Manage costs — https://code.claude.com/docs/en/costs
- Hooks reference — https://code.claude.com/docs/en/hooks
- Skill authoring — https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- Subagents — https://code.claude.com/docs/en/sub-agents
- Sub-agent cost patterns — https://claudefa.st/blog/guide/agents/sub-agent-best-practices
- Env var reference — https://github.com/HikaruEgashira/claude-code-shared-settings/blob/main/environment_variables.md
- Skill listing budget — https://claudefa.st/blog/guide/mechanics/skill-listing-budget
- Headless mode — https://www.mindstudio.ai/blog/claude-code-headless-mode-autonomous-agents
- Prompt caching — https://docs.claude.com/en/docs/build-with-claude/prompt-caching
- Message Batches — https://docs.claude.com/en/docs/build-with-claude/batch-processing
