# Shadow Validator — 2026-05-22T09:15:00Z

## Snapshot
- snapshot_ts: 2026-05-22T08:58:23Z (age: ~17 min — fresh)
- Loggers indexed (shadow_summary.json): 5 manifest-relevant, 30+ total
- Active (mtime < 24h): exit_policy_shadow, order_lifecycle, window_resolution, discover_signal (closed), shadow_telemetry
- Stalled (mtime > 6h): none
- Strategy live: VOLARB Phase 1 (activated 2026-05-16 21:00 UTC)

---

## Active Loggers

| name | n_total | n_new | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow / BE_trail_5_3 | 30,805 | 5,036 | +8.332% | +1.399% | +6.933% | [+5.28, +8.58] | 500 | SCHEMA_DRIFT→adapted READY |
| exit_policy_shadow / PT0.93+30s | 30,805 | 5,036 | +0.963% | +0.559% | +0.404% | [-1.83, +2.63] | 500 | SCHEMA_DRIFT→adapted AMBIGUOUS |
| exit_policy_shadow / PT0.95+30s | 30,805 | 5,036 | +0.824% | +0.559% | +0.265% | [-2.08, +2.61] | 500 | SCHEMA_DRIFT→adapted AMBIGUOUS |
| volarb_longshot_shadow | 0 | 0 | — | — | — | — | 100 | NOT_DEPLOYED |
| order_lifecycle | 3,583 | 222 | — | — | — | — | n/a | INFORMATIONAL |
| window_resolution | 15,774 | 2,232 | — | — | — | — | n/a | JOIN_SOURCE |

**Note on analysis scope**: Today's hot file (875 rows / 232 unique events) is the only data available for computation. Cumulative n=30,805 >> threshold of 500. Pair counts per policy (today only): BE_trail_5_3 n=193, PT0.93+30s n=225, PT0.95+30s n=225. CI computed from today's sample at t=1.96.

---

## READY for Live Review

**BLOCKED — schema drift prevents formal promotion:**

- **exit_policy_shadow / BE_trail_5_3**: uplift=+6.93% CI=[+5.28, +8.58] n_paired=193 (today's sample).
  This is the **third consecutive independent daily sample** with CI entirely above zero (2026-05-17, 2026-05-20, 2026-05-22-partial). Adapted analysis classifies as READY. Formal promotion blocked pending manifest update at research_status.md §5 to reflect actual schema (`policy_id`, `realistic_pnl_pct`). Recommend: Auditor or operator update the manifest, then re-run validator to clear formal READY.

---

## REJECTED / Recommend Close

None.

---

## STALLED (mtime > 6h, expected active)

None. All manifest loggers wrote within the last ~30 minutes of snapshot.

---

## SCHEMA DRIFT

- **exit_policy_shadow**: Manifest schema specifies `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}`. Actual rows use `{schema_version, record_type, ts_s, token_id, condition_id, policy_id, fire_ask, exit_bid, clean_pnl_pct, realistic_pnl_pct, exit_trigger, hold_seconds, ...}`. Multi-row-per-event format (one row per policy_id per fire event). Drift has persisted since at least 2026-05-17 (third consecutive flag). Manifest at research_status.md §5 still reads "rolling exit-rule validation rows" with old field names. Recommend manifest update to unblock formal READY status.

---

## Informational: order_lifecycle (n_new=222, today n=38)

- Event type: all `fill` events (no submitted/cancelled rows in today's hot file)
- Mean latency: 1,271ms (improving from 1,451ms prior run, 1,895ms two runs prior)
- Median latency: 1,178ms | p95: 1,947ms
- Full fills (realized_size ≥ intended_size): 27/38 = 71%
- Mean slippage: 0.899% (expected at extreme-odds thin markets; e.g. 0.07 ask price)
- CF (Cloudflare) attempts: mean=1.0, max=1 — no retries needed today

Latency trend is improving. Fill rate at 71% suggests partial fills at extreme odds; normal for VOLARB low-price tokens.

---

## Informational: window_resolution (n_new=2,232, today n=432)

- Today: 144 windows per asset (BTC/ETH/SOL), all logging `outcome_dir=up` (logger records only the "up" condition side of each updown market pair)
- YES (price went up) rate: 197/432 = 45.6% — consistent with near-random binary outcome
- Resolution method: all `kline`-based
- No anomalies. Join source functioning normally.

---

## Informational: volarb_longshot_shadow (NOT_DEPLOYED)

Phase 2 gate not yet deployed. File absent from data-mirror. Expected: ASK_FLOOR=0.0 OOS collection to begin before ASK_FLOOR lift from 0.10 → 0.0. Status unchanged since last run.

---

## State Transitions vs Prior (2026-05-20T09:18:00Z)

- **exit_policy_shadow**: SCHEMA_DRIFT → SCHEMA_DRIFT (no change). Schema-adapted sub-status: BE_trail_5_3 READY_PENDING_MANIFEST → READY_PENDING_MANIFEST (third consecutive CI>0 confirmation; no manifest update received). PT0.93+30s: AMBIGUOUS → AMBIGUOUS. PT0.95+30s: AMBIGUOUS → AMBIGUOUS.
- **volarb_longshot_shadow**: NOT_DEPLOYED → NOT_DEPLOYED (no change).
- **order_lifecycle**: INFORMATIONAL → INFORMATIONAL. Latency improving (1,451ms → 1,271ms mean).
- **window_resolution**: JOIN_SOURCE → JOIN_SOURCE (no change).

No promotions. No rejections. BE_trail_5_3 awaiting manifest correction to unlock formal READY.
