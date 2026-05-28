# Shadow Validator — 2026-05-28T09:09:00Z

## Snapshot
- snapshot_ts: 2026-05-28T08:59:12Z (age: ~10 min — fresh, PASS)
- Loggers indexed (shadow_summary.json): 5 manifest-relevant
- Active loggers (mtime <24h): 3 (exit_policy_shadow, order_lifecycle, window_resolution)
- Stalled loggers (mtime >6h): 0
- Strategy live: VOLARB Phase 1 (activated 2026-05-16 21:00 UTC)

**Note:** research_status.md §1 still reads "Active strategy: LDA" (last updated 2026-05-16 12:50 UTC, 9h before VOLARB activation). This is stale but does not affect validator output — the validator is strategy-agnostic and tracks loggers by file, not strategy label.

---

## Active Loggers

| name | n_total | n_new_since_prior | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow (BE_trail_5_3) | 45,744 | 14,939 | +6.07% | +0.09% | +5.99% | [+4.59, +7.38] | 500 | READY_PENDING_MANIFEST |
| exit_policy_shadow (PT0.93+30s) | 45,744 | 14,939 | +0.44% | -0.46% | +0.90% | [-1.31, +3.11] | 500 | AMBIGUOUS |
| exit_policy_shadow (PT0.95+30s) | 45,744 | 14,939 | +0.30% | -0.46% | +0.76% | [-1.53, +3.05] | 500 | AMBIGUOUS |
| order_lifecycle | 3,665 | 82 | n/a | n/a | n/a | n/a | n/a | INFORMATIONAL |
| window_resolution | 22,512 | 6,738 | n/a | n/a | n/a | n/a | n/a | JOIN_SOURCE |
| volarb_longshot_shadow | 0 | 0 | n/a | n/a | n/a | n/a | 100 | NOT_DEPLOYED |

Analysis window: today's hot file (2026-05-28), n=972 rows, 220–250 paired groups per candidate.
Metric: `realistic_pnl_pct` (net of fees). Baseline: `gate_died` policy. t-crit ≈ 2.0 (n≥30).

---

## READY for Live Review

**exit_policy_shadow / BE_trail_5_3:** uplift=+5.99% CI=[+4.59,+7.38] n=220 (today) / n_total=45,744.

This is the **fourth consecutive independent-sample confirmation** that BE_trail_5_3 clears the CI>0 bar (prior confirmations: 2026-05-17, 2026-05-20, 2026-05-22). Candidate exit fires when bid crosses trailing floor at fire_ask+5% with 3% step, while the baseline (gate_died) holds until the gate timer expires.

The signal is stable. The formal READY call remains **blocked on a manifest update** — research_status.md §5 still describes the old schema (`trade_id`, `candidate_exit_price`, etc.) rather than the live schema (`policy_id`, `realistic_pnl_pct`). Recommend live deployment via Auditor **only after** research_status.md §5 is updated to reflect actual schema.

---

## REJECTED / Recommend Close

None.

---

## STALLED (mtime >6h, expected active)

None.

- exit_policy_shadow: last write 2026-05-28T08:59:10Z (age 0.00h) — ACTIVE
- order_lifecycle: last write 2026-05-28T06:03:52Z (age 2.92h) — active (low but < 6h)
- window_resolution: last write 2026-05-28T08:55:36Z (age 0.06h) — ACTIVE

---

## SCHEMA DRIFT

**exit_policy_shadow** (4th consecutive run flagged):

Manifest schema (research_status.md §5):
`{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}`

Actual schema (live, all 972 today's rows):
`{schema_version, record_type, ts_s, token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts, fire_ts_s, fire_ask, sec_to_res_at_fire, policy_id, exit_ts_s, exit_bid, exit_bid_size, exit_trigger, clean_pnl_pct, realistic_pnl_pct, fill_ok, hold_seconds, bnc_5m_pct, snap30, snap60, hour_utc, session_bucket, direction}`

The multi-policy per-trade log model (`policy_id` field) is fundamentally different from the paired-row manifest model. Schema-adapted analysis is consistent and valid, but the manifest is stale by at least 20+ days. **Recommend manifest update before Auditor acts on this.**

---

## State Transitions vs Prior (since 2026-05-22T09:15:00Z)

| logger | prior status | current status | change |
|---|---|---|---|
| exit_policy_shadow / BE_trail_5_3 | READY_PENDING_MANIFEST | READY_PENDING_MANIFEST | no change (4th confirmation; blocker = manifest) |
| exit_policy_shadow / PT0.93+30s | AMBIGUOUS | AMBIGUOUS | no change |
| exit_policy_shadow / PT0.95+30s | AMBIGUOUS | AMBIGUOUS | no change |
| volarb_longshot_shadow | NOT_DEPLOYED | NOT_DEPLOYED | no change |
| order_lifecycle | INFORMATIONAL | INFORMATIONAL | no change |
| window_resolution | JOIN_SOURCE | JOIN_SOURCE | no change |

### order_lifecycle: fill stats (today, n=7 fills)
- Mean latency: 1,187ms, median 1,145ms (consistent with prior 1,271ms mean — slight improvement)
- Full fill rate: 7/7 (100% today, vs 71% prior cumulative — small sample)
- Slippage: fills realizing below intended_price on BUY orders (favorable; prior mean 0.90%)

### window_resolution: today's resolved windows (n=423)
- YES rate: 45.9% (194/423) — consistent with prior 45.6%
- Equal split across ETH/BTC/SOL (141 each)
