# Shadow Validator — 2026-06-09T09:07:00Z

## Snapshot
- **snapshot_ts:** 2026-06-09T08:57:09Z (age: ~10 min — FRESH)
- **Loggers indexed (shadow_summary.json):** 250
- **Active (mtime < 24h):** 49
- **Stalled (mtime > 6h, non-manifest context files):** 224 (all are prior-day hot/ partitions — expected)
- **Strategy live:** VOLARB Phase 1 (activated 2026-05-16 21:00 UTC; LDA dormant)

> Note: research_status.md last updated 2026-05-16 12:50 UTC — still shows "Active strategy: LDA". This file is stale and contradicts the system prompt context. Raising here as required; not re-investigating closed families.

---

## Active Loggers

| name | n (rolling 11d) | n_new_since_prior | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow / BE_trail_5_3 | 24,001 (total rows) | ~9,543 | 7.19% | 1.75% | **+5.45%** | [+4.05, +6.85] | 500 | SCHEMA_DRIFT / schema-adapted: **READY** |
| exit_policy_shadow / PT0.93+30s | 24,001 (total rows) | ~9,543 | 1.02% | 0.98% | +0.04% | [−2.07, +2.14] | 500 | SCHEMA_DRIFT / schema-adapted: **AMBIGUOUS** |
| exit_policy_shadow / PT0.95+30s | 24,001 (total rows) | ~9,543 | 1.20% | 1.06% | +0.14% | [−2.10, +2.38] | 500 | SCHEMA_DRIFT / schema-adapted: **AMBIGUOUS** |
| volarb_longshot_shadow | 0 | 0 | — | — | — | — | 100 | **NOT_DEPLOYED** |
| order_lifecycle | 165 (rolling) | ~52 | — | — | — | — | n/a | **INFORMATIONAL** |
| window_resolution | 11,310 (rolling) | ~4,431 | — | — | — | — | n/a | **JOIN_SOURCE** |

**Analysis method for exit_policy_shadow (schema-adapted):**
- Trade groups keyed on `(condition_id, window_end_ts, fire_ts_s)`. Each group has one row per policy_id.
- Pairwise uplift = `candidate.realistic_pnl_pct − gate_died.realistic_pnl_pct` per matched trade.
- Today's session (2026-06-09 00:03–08:54 UTC): 972 rows, 253 trade groups with gate_died baseline.
- n_paired today: BE_trail_5_3=223, PT0.93+30s=249, PT0.95+30s=247.
- Cumulative n_paired (est. from shadow_summary 24,001 rows / ~4 policies × ~87% match rate) ≈ 5,200 — well above threshold.

---

## READY for Live Review

**exit_policy_shadow — BE_trail_5_3 (schema-adapted):**
- uplift = +5.45% CI₉₅ = [+4.05%, +6.85%] (today's session, n_paired=223)
- 6th consecutive independent daily window with CI_lower > 0. Prior five sessions: uplift ranged 5.64–6.93%.
- Cumulative estimated n_paired ≈ 5,200 >> threshold (500).
- Recommend live deployment review via Auditor.
- **Blocker:** manifest schema has not been updated (6th consecutive SCHEMA_DRIFT flag). Manifest shows `{ts, trade_id, candidate_exit_reason, candidate_exit_price, ...}` but actual schema is per-policy-row format with `policy_id`, `realistic_pnl_pct`. Auditor/owner must update research_status.md manifest before deployment, then re-confirm READY.

---

## REJECTED / Recommend Close

None.

---

## STALLED (mtime > 6h, expected active)

None among manifest loggers:
- exit_policy_shadow: mtime 2026-06-09T08:54:25Z (3 min old)
- order_lifecycle: mtime 2026-06-09T08:56:36Z (1 min old)
- window_resolution: mtime 2026-06-09T08:55:39Z (2 min old)
- shadow_telemetry: mtime 2026-06-09T08:57:09Z (0 min old — matches snapshot)

System health (shadow_telemetry): uptime=35,380s (~9.8h), written_total=1,752,691, dropped_total=0, queue_depth=25, rows/min=2,972. No drops.

---

## SCHEMA DRIFT

- **exit_policy_shadow** (6th consecutive run):
  - Manifest schema: `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}`
  - Actual schema: per-policy rows with fields `{schema_version, record_type, ts_s, token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts, fire_ts_s, fire_ask, sec_to_res_at_fire, policy_id, exit_ts_s, exit_bid, exit_bid_size, exit_trigger, clean_pnl_pct, realistic_pnl_pct, fill_ok, hold_seconds, bnc_5m_pct, snap30, snap60, hour_utc, session_bucket, direction}`
  - No `trade_id`, no `candidate_exit_*`, no `baseline_exit_*` columns. Multiple rows per fire event (one per policy_id). Writer redesigned to emit policy fan-out rows.
  - **Recommend manifest update to reflect actual schema.** Writer has been stable in this format for 6+ sessions; manifest is the stale artifact.
  - Schema-adapted analysis was performed and yielded valid READY signal for BE_trail_5_3.

---

## State Transitions vs Prior (prior run: 2026-06-05T09:09:41Z)

- **exit_policy_shadow / BE_trail_5_3:** READY_PENDING_MANIFEST → **READY_PENDING_MANIFEST** (6th consecutive session CI>0; uplift stable at 5.45% vs 5.64–6.93% prior five). No change in formal status pending manifest correction.
- **exit_policy_shadow / PT0.93+30s:** AMBIGUOUS → **AMBIGUOUS** (today's full-session data: uplift near-zero at +0.04%, CI=[−2.07, +2.14]; ASIA-only prior readings were false positives from small slice; full-session evidence is null signal).
- **exit_policy_shadow / PT0.95+30s:** AMBIGUOUS → **AMBIGUOUS** (uplift +0.14%, CI=[−2.10, +2.38]; same issue as PT0.93+30s; both trending toward eventual REJECTED if pattern holds at accumulating n).
- **volarb_longshot_shadow:** NOT_DEPLOYED → **NOT_DEPLOYED** (Phase 2 gate file absent from data-mirror).
- **order_lifecycle:** INFORMATIONAL → **INFORMATIONAL** (today: 6 fills, mean_latency=1334ms, fill_rate=100%).
- **window_resolution:** JOIN_SOURCE → **JOIN_SOURCE**.

---

## Supplemental: PT0.93/PT0.95 Diagnosis

Prior runs analyzed ASIA-only slices (hours 0–3 UTC, ~90 paired obs each) and found borderline CI>0.
Today's file covers hours 0–8 UTC (broader session, 249/247 paired obs). Result: uplift collapses to near-zero (+0.04%/+0.14%) with CI spanning ±2%. ASIA-window artifacts — small samples from a single favorable 3-hour stretch — do not survive multi-session scrutiny. These policies produce no detectable uplift vs gate_died over the full trading day.
