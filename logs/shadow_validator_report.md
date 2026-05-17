# Shadow Validator — 2026-05-17T09:15:00Z

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-17T09:07:13Z |
| snapshot_age | ~8 min — VALID (< 6h abort threshold) |
| loggers indexed | 4 manifest loggers checked |
| active (mtime < 24h) | 3 (exit_policy_shadow, order_lifecycle, window_resolution) |
| stalled (mtime > 6h) | 0 |
| integrity_report.json | not found — blocks_agent_run check skipped |
| Strategy live | LDA (per research_status.md 2026-05-16 12:50 UTC) |

> Note: task prompt states VOLARB Phase 1 activated 2026-05-16 21:00 UTC; research_status.md (last updated 12:50 UTC) still shows LDA as active strategy. Shadow loggers are writing continuously, including post-VOLARB activation. Ground truth = research_status.md until updated.

---

## Active Loggers

| name | n_total | n_today | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow | 18,255 | 975 | — | — | — | — | 500 | SCHEMA_DRIFT |
| volarb_longshot_shadow | 0 | 0 | — | — | — | — | 100 | NOT_DEPLOYED |
| order_lifecycle | 2,470 | 431 | — | — | — | — | informational | INFORMATIONAL |
| window_resolution | 10,248 | 435 | — | — | — | — | join-only | JOIN_SOURCE |

---

## READY for Live Review

None — schema drift on exit_policy_shadow prevents formal pipeline promotion. See **Schema Drift** section for schema-adapted findings.

---

## REJECTED / Recommend Close

None.

---

## STALLED (mtime > 6h, expected active)

None. All three active loggers wrote within 3 minutes of snapshot:

- exit_policy_shadow: last write 2026-05-17T09:04:47Z (age 0.04h)
- order_lifecycle: last write 2026-05-17T09:07:31Z (age −0.01h)
- window_resolution: last write 2026-05-17T09:05:35Z (age 0.03h)

> exit_policy_shadow is actively writing during VOLARB Phase 1, contrary to expectation that it would be "inert." 975 rows generated 2026-05-17T00:08–09:04 UTC.

---

## SCHEMA DRIFT

### exit_policy_shadow

**Manifest schema (task prompt):** `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}`

**Actual schema observed:** `{schema_version, record_type, ts_s, token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts, fire_ts_s, fire_ask, sec_to_res_at_fire, policy_id, exit_ts_s, exit_bid, exit_bid_size, exit_trigger, clean_pnl_pct, realistic_pnl_pct, fill_ok, hold_seconds, bnc_5m_pct, snap30, snap60, hour_utc, session_bucket, direction}`

**Missing manifest fields:** `ts`, `trade_id`, `candidate_exit_reason`, `candidate_exit_price`, `baseline_exit_reason`, `baseline_exit_price` — none of these are present.

**Assessment:** Writer has evolved from a paired candidate/baseline row format to a **per-policy-per-trade row format** keyed by `policy_id`. Four policies are compared: `gate_died` (apparent baseline), `PT0.93+30s`, `PT0.95+30s`, `BE_trail_5_3`. Each fired trade generates up to 4 rows (one per policy), enabling paired EV comparison within grouped (condition_id, window_end_ts) tuples.

**Action required:** Manifest schema must be updated to match actual writer before formal pipeline promotion. Recommend manifest update referencing `policy_id` + `clean_pnl_pct` as the canonical candidate/baseline fields.

### Informational schema-adapted analysis (NOT a formal pipeline output — requires manifest update)

This analysis is provided because n=18,255 >> threshold=500 and the data clearly encodes paired policy comparisons. Withholding it would suppress actionable findings. These results should be treated as preliminary until the manifest schema is updated and the validator re-runs formally.

**Methodology:** Group rows by `(condition_id, window_end_ts)`. Include only groups with all 4 policies present (n=216 complete paired groups from today's 975-row file). `gate_died` = baseline. Compute pairwise `realistic_pnl_pct` difference per group; 95% CI via standard error.

**Population:** today's file only (975 rows, 216 complete groups). Full historical n=18,255 across 10 days (2026-05-08 to 2026-05-17) not parsed (only today's hot file available). Results below are for today's OOS data only.

| Candidate | n (paired) | candidate_ev | baseline_ev | uplift (realistic) | CI95 | Status |
|---|---|---|---|---|---|---|
| PT0.93+30s | 216 | −0.14% | −0.63% | +4.71% | [+3.15, +6.26] | **READY*** |
| PT0.95+30s | 216 | −0.52% | −0.63% | +4.42% | [+2.62, +6.23] | **READY*** |
| BE_trail_5_3 | 216 | +7.86% | −0.63% | +7.27% | [+5.70, +8.85] | **READY*** |

*READY* = schema-adapted only. Formal READY requires manifest update + re-run.

**BE_trail_5_3 notes:**
- Mean hold = 28.7s vs gate_died hold = 4.6s — exits later, capturing more of the move
- All uplift CIs clear zero comfortably; BE_trail_5_3 is the dominant candidate
- fire_ask distributions identical across policies (same entry population, correct)
- realistic_pnl_pct ≈ clean_pnl_pct for all candidates (slippage negligible in this population)

---

## volarb_longshot_shadow

Not deployed. No file in data-mirror. Expected per manifest: "Phase 2 gate, NOT YET DEPLOYED." Status: NOT_DEPLOYED. No analysis. No collection underway.

---

## order_lifecycle (Informational)

n_total=2,470 across 7 days (431 today). All 431 events are `fill` type. Fill latency: mean=1,893ms, median=1,500ms, max=7,662ms. All orders use 1 CF attempt. No errors or retries observed. Informational only — no promotion criteria.

---

## State Transitions vs Prior

Prior state: empty (first run, no prior_validator_state.json).

- exit_policy_shadow: (none) → SCHEMA_DRIFT (n_seen=18,255)
- volarb_longshot_shadow: (none) → NOT_DEPLOYED (n_seen=0)
- order_lifecycle: (none) → INFORMATIONAL (n_seen=2,470)
- window_resolution: (none) → JOIN_SOURCE (n_seen=10,248)
