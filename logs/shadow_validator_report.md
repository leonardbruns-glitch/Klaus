# Shadow Validator — 2026-05-20T09:18:00Z

## Snapshot
- snapshot_ts: 2026-05-20T09:01:19Z (age: ~17 min — FRESH)
- Loggers indexed (all dates): 156 entries across 20 logger types
- Active (mtime <24h, today): 14 files
- Manifest-tracked active: 3 (exit_policy_shadow, order_lifecycle, window_resolution)
- Stalled (mtime >6h, expected active): 0
- Strategy live: VOLARB Phase 1 (activated 2026-05-16 21:00 UTC)

---

## Active Loggers

| name | n_total | n_new | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow / BE_trail_5_3 | 25769 rows | +7514 | +7.48% | +0.07% | +6.30% | [+4.91%, +7.69%] | 500 rows | **READY** (schema-adapted) |
| exit_policy_shadow / PT0.93+30s | 25769 rows | +7514 | +1.71% | +0.07% | +1.28% | [-0.83%, +3.39%] | 500 rows | AMBIGUOUS |
| exit_policy_shadow / PT0.95+30s | 25769 rows | +7514 | +2.03% | +0.07% | +1.62% | [-0.43%, +3.68%] | 500 rows | AMBIGUOUS |
| volarb_longshot_shadow | 0 | 0 | — | — | — | — | 100 | NOT_DEPLOYED |
| order_lifecycle | 3361 | +891 | — | — | — | — | n/a | INFORMATIONAL |
| window_resolution | 13542 | +3294 | — | — | — | — | n/a | JOIN_SOURCE |

**Analysis basis:** exit_policy_shadow uses today's hot file only (941 rows, 232 unique observations).
Paired analysis: each candidate policy vs baseline `gate_died` on same (condition_id, window_end_ts).
CI95 computed via t-distribution (n_paired: 206-226; t_crit=1.96 for n≥100).

---

## READY for Live Review

- **exit_policy_shadow / BE_trail_5_3**: uplift=+6.30% CI=[+4.91%, +7.69%] n_paired=206 (today).
  Prior run (2026-05-17): uplift=+7.27% CI=[+5.70%, +8.85%] n_paired=216.
  **Two independent samples, both CI clearly above 0. Signal is robust and consistent.**
  Recommend live deployment review via Auditor.
  **Formally blocked pending manifest update** — schema drift flag raised on two consecutive runs (see §SCHEMA DRIFT). Promotion requires manifest alignment before live deployment review.

---

## REJECTED / Recommend Close

None.

---

## STALLED (mtime >6h, expected active)

None. All manifest-tracked loggers wrote within 9 minutes of snapshot timestamp.
- exit_policy_shadow: last write 2026-05-20T08:59:20Z (2 min before snapshot)
- order_lifecycle: last write 2026-05-20T08:53:40Z (8 min before snapshot)
- window_resolution: last write 2026-05-20T09:00:35Z (1 min before snapshot)

---

## SCHEMA DRIFT

- **exit_policy_shadow**: Manifest schema `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}` does not match actual rows.

  Actual schema (observed): `{ts_s, token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts, fire_ts_s, fire_ask, sec_to_res_at_fire, policy_id, exit_ts_s, exit_bid, exit_bid_size, exit_trigger, clean_pnl_pct, realistic_pnl_pct, fill_ok, hold_seconds, bnc_5m_pct, ...}`

  The logger is per-policy-per-observation (multiple rows per window, one per `policy_id`). Policy IDs active today: `BE_trail_5_3`, `PT0.93+30s`, `PT0.95+30s`, `gate_died` (baseline).

  **This is the SECOND consecutive run flagging schema drift with no manifest update.** Schema-adapted analysis performed in both runs. Formal READY status remains blocked until research_status.md §5 is updated to reflect actual schema.

  Recommend: update `research_status.md §5` exit_policy_shadow schema definition to match actual rows, then re-run validator.

---

## Unregistered Active Loggers (not in manifest — flagged only, not analyzed)

The following loggers are writing today but absent from research_status.md §5. Not analyzed.

| logger | n_today | last_mtime |
|---|---|---|
| preseed_shadow | 445 | 2026-05-20T08:53:38Z |
| sports_copy_signals | 308 | 2026-05-20T08:47:20Z |

Recommend: register or explicitly close these in research_status.md §5.

---

## PT0.93 / PT0.95 Signal Regression Note

Prior run (2026-05-17): PT0.93 uplift=+4.71% CI=[+3.15%, +6.26%], PT0.95 uplift=+4.42% CI=[+2.62%, +6.23%] — both CI above 0.

Today (2026-05-20, independent sample): PT0.93 uplift=+1.28% CI=[-0.83%, +3.39%], PT0.95 uplift=+1.62% CI=[-0.43%, +3.68%] — both CI straddle 0.

Point estimates dropped ~3.5pp. Possible causes: different session/hour distribution under VOLARB Phase 1 vs prior; PT policies more sensitive to session composition than BE_trail. Do not promote. Extend collection to resolve.

---

## State Transitions vs Prior

| logger / sub-key | prior status | current status |
|---|---|---|
| exit_policy_shadow / BE_trail_5_3 | SCHEMA_DRIFT (CI>0 in prior adapted analysis) | **READY** (schema-adapted, blocked pending manifest update) |
| exit_policy_shadow / PT0.93+30s | SCHEMA_DRIFT (CI>0 in prior adapted analysis) | AMBIGUOUS (CI straddles 0 in today's independent sample) |
| exit_policy_shadow / PT0.95+30s | SCHEMA_DRIFT (CI>0 in prior adapted analysis) | AMBIGUOUS (CI straddles 0 in today's independent sample) |
| volarb_longshot_shadow | NOT_DEPLOYED | NOT_DEPLOYED (no change) |
| order_lifecycle | INFORMATIONAL | INFORMATIONAL (latency improving: mean 1451ms vs prior 1894ms) |
| window_resolution | JOIN_SOURCE | JOIN_SOURCE (no change) |
