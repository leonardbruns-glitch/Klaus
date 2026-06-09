---
name: trades-query
description: This skill should be used whenever querying logs/trades.jsonl, the shadow logs, or answering "what fired / last N trades / live STWA performance / is the bot trading". Encodes the schema and provenance gotchas so queries don't silently return 0 rows or read the wrong file.
---

# Querying Klaus trade & signal data

## CRITICAL: pick the right file
- **"What is firing RIGHT NOW / last N live signals"** → read the **shadow logs**, NOT trades.jsonl:
  - `logs/shadow/hot/<YYYY-MM-DD>/stwa_signals.jsonl` — what the engine emitted
  - `logs/shadow/hot/<YYYY-MM-DD>/stwa_pricer_eval.jsonl` — per-bucket p_model / p_cal vs book
  - plus `risk.open_positions` (positions appear here at fill, immediately)
- **`logs/trades.jsonl`** — STWA fills land here **only at resolution** (via `_stwa_resolution_loop`).
  Using it for "what fired today" misses everything still open. (This burned the user before — 06-06 missed live model-NO buys.)

## Schema gotchas (silent-0-row traps)
- Time filter uses **`ts_open`** (Unix float), NOT `timestamp` and NOT ISO strings.
- Live trades: `is_live == True`.
- STWA trades tagged **`WEATHER_STWA`** (M1β probe: `WEATHER_M1_PROBE`; favorite-YES: `WEATHER_FAVYES`).
- `bankroll.json` is **NOT authoritative** — the user sells manually; never conclude PnL/ruin from it.

## Example: count resolved STWA + recent fills
```bash
python3 - <<'PY'
import json
rows=[json.loads(l) for l in open('/root/Klaus/logs/trades.jsonl')]
stwa=[r for r in rows if r.get('strategy')=='WEATHER_STWA' or 'STWA' in str(r.get('signal_source',''))]
print('resolved STWA fills:', len(stwa))
for r in sorted(stwa,key=lambda r:r.get('ts_open',0))[-5:]:
    print(r.get('ts_open'), r.get('market'), r.get('side'), r.get('pnl'))
PY
```

Cross-check live pricing against ASOS/Gamma resolution before drawing any pricing conclusion.
See also: `stwa-preflight`, `reference_trades_schema` memory.
