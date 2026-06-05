# Shadow Validator — 2026-06-05T09:09:41Z

## Snapshot
- snapshot_ts: 2026-06-05T08:55:26Z (14 min old — fresh)
- Loggers indexed in shadow_summary: 28 logger types across hot/ files
- Active in mirror (mtime <24h): exit_policy_shadow, order_lifecycle, window_resolution, shadow_telemetry, maker_flow, wallet_shadow — plus 10+ others outside validator manifest
- Stalled (mtime >6h, expected active): **none** (exit_policy_shadow last write 03:59:30Z = 5h10m ago; technically clear of 6h threshold)
- Strategy live: VOLARB Phase 1 per context / WEATHER per recent commits (see Context Drift below)
- Bot status: **DOWN** (systemd: failed; last activated 2026-06-04 13:45:47 UTC; last data ~04:00 UTC today)

---

## Active Loggers

| name | n_total (est.) | n_new_since_prior | candidate_ev | baseline_ev | uplift | CI95 | threshold | status |
|---|---|---|---|---|---|---|---|---|
| exit_policy_shadow | ~62,514 | ~16,770 | schema_drift — see §below | — | — | — | 500 paired | SCHEMA_DRIFT |
| volarb_longshot_shadow | 0 | 0 | n/a | n/a | n/a | n/a | 100 OOS | NOT_DEPLOYED |
| order_lifecycle | ~298+ | ~4 | n/a (informational) | n/a | n/a | n/a | none | INFORMATIONAL |
| window_resolution | ~11,595+ | ~201 | n/a (join source) | n/a | n/a | n/a | none | JOIN_SOURCE |

_n_total estimated: shadow_summary cumulative + mirror-visible rows. Exact historical count not accessible — mirror exposes only today's hot file per logger at data/shadow/. Prior n_seen from prior_validator_state used as floor._

---

## Schema-Adapted Analysis — exit_policy_shadow (5th consecutive SCHEMA_DRIFT run)

**Manifest schema:** `{ts, trade_id, candidate_exit_reason, candidate_exit_price, baseline_exit_reason, baseline_exit_price}`

**Actual schema:** `{schema_version, record_type, ts_s, token_id, condition_id, asset, outcome_dir, outcome_side, window_end_ts, fire_ts_s, fire_ask, sec_to_res_at_fire, policy_id, exit_ts_s, exit_bid, exit_bid_size, exit_trigger, clean_pnl_pct, realistic_pnl_pct, fill_ok, hold_seconds, bnc_5m_pct, snap30, snap60, hour_utc, session_bucket, direction}`

**Drift note:** Logger writes one row per (condition_id, policy_id). Baseline = `gate_died`. Candidates = `BE_trail_5_3`, `PT0.93+30s`, `PT0.95+30s`. Paired by condition_id. Metric = `realistic_pnl_pct`.

**Today's analysis window:** 404 rows (2026-06-05T00:03–03:59 UTC). **100% ASIA session (hours 0–3).** 98 condition_ids with all four policies present.

| policy | n_pairs | candidate_ev | baseline_ev | uplift | CI95 (95%) | schema_adapted_status |
|---|---|---|---|---|---|---|
| BE_trail_5_3 | 90 | +6.41% | +0.76% | **+5.64%** | [+3.60, +7.69] | READY_PENDING_MANIFEST *(5th confirmation)* |
| PT0.93+30s | 98 | +4.37% | +0.25% | +4.12% | [+0.80, +7.45] | AMBIGUOUS *(see note)* |
| PT0.95+30s | 98 | +4.03% | +0.25% | +3.78% | [+0.43, +7.14] | AMBIGUOUS *(see note)* |

**PT0.93+30s / PT0.95+30s note:** CI lower > 0 in today's ASIA-only slice. Prior 4 pooled multi-session runs at n≈250 pairs each showed CI straddling 0 for both. Today's 4-hour window (hours 0–3 only, n=98) is insufficient to override the pooled result. Single-session CI flip is consistent with ASIA-regime variance, not signal emergence. Status held at AMBIGUOUS pending multi-day pooled reanalysis (requires historical file access or next mirror with full-day data).

**BE_trail_5_3:** Five independent daily windows now all show CI strictly above 0. Uplift stable across runs: 5.64% (today), 5.99% (2026-05-28), prior runs 5.99–6.93%. This is the most consistent finding in the validator history. Formal READY blocked only by: (a) n_pairs per session ~90–220 vs threshold 500; (b) SCHEMA_DRIFT not resolved in research_status.md §5. Neither indicates the signal is absent — they indicate the manifest is stale.

---

## READY for Live Review
None formally — all blocked by SCHEMA_DRIFT.

**Schema-adapted READY (pending manifest update):**
- **BE_trail_5_3**: uplift=+5.64% CI=[+3.60, +7.69], 5th independent daily confirmation. Recommend research_status.md §5 update to reflect actual schema (`policy_id` / `realistic_pnl_pct`), then promote to formal READY. Auditor action required to deploy.

---

## REJECTED / Recommend Close
None.

---

## STALLED (mtime > 6h, expected active)
None technically. **However:**
- exit_policy_shadow last write: 2026-06-05T03:59:30Z (5h10m ago, margin 50min from threshold)
- Bot systemd status: **failed** — service last activated 2026-06-04 13:45 UTC; no restart observed in current mirror
- If bot remains down, exit_policy_shadow will cross 6h stall threshold ~10:00 UTC today
- order_lifecycle last write: 2026-06-05T03:57:53Z (5h12m ago; same condition)

---

## SCHEMA DRIFT
- **exit_policy_shadow**: 5th consecutive run. Manifest (research_status.md §5) specifies `{ts, trade_id, candidate_exit_price, baseline_exit_price}`. Actual rows use `{ts_s, token_id, policy_id, realistic_pnl_pct, ...}`. Schema-adapted analysis run (see above). Manifest update required — every validator run is flagging drift because the manifest has not been corrected since at least 2026-05-17.

---

## Context Drift (not in prior state — new flag)
research_status.md last updated 2026-05-16 12:50 UTC. States "Active strategy: LDA." Validator context says "VOLARB Phase 1 (activated 2026-05-16 21:00 UTC). LDA dormant." Recent git commits (top-10) show:
- Weather-market strategies: FAVYES (buy YES on weather tails), fade, maker, M1β
- 10+ new shadow loggers outside the validator manifest: `fade_shadow` (n=38,544), `maker_shadow` (n=357,995), `maker_flow` (n=979,612), `wallet_shadow` (n=253,885), `stwa_pricer_eval` (n=2,829,243), `favyes_live`, `ofi_live`, `edge2_shadow`, etc.

These loggers are outside validator scope (manifest not updated to include them) and are not analyzed here. The exit_policy_shadow logger still logs BTC/ETH/SOL positions. Whether it reflects a live strategy or residual LDA/VOLARB activity is unclear. research_status.md update is overdue.

---

## State Transitions vs Prior
- exit_policy_shadow: SCHEMA_DRIFT → SCHEMA_DRIFT (no change; 5th run)
- volarb_longshot_shadow: NOT_DEPLOYED → NOT_DEPLOYED (no change)
- order_lifecycle: INFORMATIONAL → INFORMATIONAL (no change)
- window_resolution: JOIN_SOURCE → JOIN_SOURCE (no change)
