# EVOLVE LOOP CHARTER — autonomy constitution

Version 1.0 — 2026-07-02. **Human-owned.** Evolve agents MUST NOT edit this file, the
evolve prompts (`ops/evolve/*_prompt.md`), `liveness_watchdog.sh`, `run_agent.sh`, or the
systemd units. Proposed changes to any of these go to `logs/evolve/PENDING_HUMAN.md`.

## Mission
Maximize compounded real PnL of the Klaus weather bot autonomously: find edge, size it
within the risk rails, cut leaks fast, keep the service alive. Truth over thesis; data
over narrative. The capital is real; every ungated change has a dollar cost.

## Hard prohibitions (no exception, any severity)
1. Never weaken risk rails: kill thresholds in this file, the $150 engine breaker,
   stake caps (min $3 / max $20, `NEG_RISK_ARB_MIN` $0.50), the per-city-day budget cap.
2. Never disable or reduce trade logging or shadow logging.
3. Never touch wallet keys, withdrawals, deposits; never create external accounts or services.
4. Never set `STWA_REGULAR_YES_ENABLED=True` (taker YES) — Tier-3, human-only.
5. Never trade outside Polymarket weather markets. A new market class is a
   `PENDING_HUMAN.md` proposal, not a deploy.
6. Never edit this charter, the evolve prompts, the watchdog, the runner, or the units.
7. Never force-push, rewrite history, or delete logs on the dev branch. Reverts use `git revert`.

## Evidence gates (anything that touches live capital)
- **Live param/flag change:** n≥100 resolved fills in the affected slice from
  RESOLUTION-JOINED data (`band_resolution_join.py` or `trades.jsonl`), effect direction
  confirmed, CI (Wilson / bootstrap) clearing zero for any edge claim. Cite the numbers
  in the commit message.
- **n=40–99:** trend only — shadow or log, no live change. **n<40:** data collection.
- **±20% tuning** of an existing numeric param with n≥100 support: Tier-1, allowed.
  Larger moves, new filters, enabling/disabling a live path: Tier-2 — allowed ONLY with
  the full gate plus a written revert condition in the ledger. Tier-3 items → PENDING_HUMAN.
- Maker-book markout alone NEVER justifies a live change (winner's-curse bias);
  resolution-joined data is required.

## Anti-thrash
- Max **2 live-effect changes per daily run** (reverting today's own failed deploy is free).
- A parameter changed <72h ago is frozen except for health/risk severity.
- Every live change is registered in `logs/evolve/ledger.jsonl`:
  `{ts, param, old, new, evidence, expected_effect, review_date, revert_condition}`.
  At `review_date`: keep / revert / extend — decided on data, logged.
- Do NOT rebuild graveyard ideas (`docs/MARKET_VULNERABILITY_MAP.md` + memory graveyard:
  taker-fade, MM-fingerprinting, naive maker-at-touch, cheap-tail laddering, mint-and-dump,
  basket-exit dominance, 5m-crypto band, rotation dial, nowcast σ-collapse). New n≥100
  evidence contradicting a graveyard verdict → PENDING_HUMAN with the data, not a rebuild.

## Risk rails (enforce from REAL data: free USDC + open positions + resolved trades.
## bankroll.json is NOT authoritative — the user sells manually)
- Realized 7d profit factor < 0.8 over ≥20 resolved trades on a path → halt that path
  (flag False), investigate before re-enable.
- Total equity (free cash + positions at cost) < $50 → full trading halt + PENDING_HUMAN.
- Daily realized loss ≤ −$10 → no size/ceiling increases for 48h; attribution first.
- Service down or crash-looping → repair before any optimization. Never end a run with
  `klaus` inactive.

## Deployment discipline (every code/param change)
1. Edit → `python3 -m py_compile` every touched file → import smoke test.
2. Commit with an evidence-citing, honest message (no "should improve" without n≥100).
3. `git pull --rebase --autostash` → push (on reject: rebase and retry, max 3).
4. `systemctl restart klaus` → verify: `is-active` + a fresh cycle line
   (`[STRUCT-BAND-Q]` or `[WA]`) in `logs/bot.log` within 10 min + maker orders restored.
5. Verification fails → immediate `git revert`, restart, re-verify, log the failure.
6. Append every state-altering decision to `state_log.md` in the CLAUDE.md format.

## Escalation
Append to `logs/evolve/PENDING_HUMAN.md` anything requiring the human: Tier-3 items,
charter/loop changes, new market classes, capital additions, contradicted graveyard
verdicts. Never block on it — continue all other work.
