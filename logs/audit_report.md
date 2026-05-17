# LDA Quantitative Audit — 2026-05-17 00:16 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-17T00:02:11Z (14 min old — FRESH) |
| Klaus state | active (VOLARB Phase 1 live since 2026-05-16 21:14 UTC) |
| Capital | $67.03 (prior usable audit was BOND-era at $84.61 — -$17.58 since) |
| LDA n live era | 111 (lda_status.txt canonical) / 116 kpnl-resolved (this audit, dedup diff below) |
| drift_status | OK — constants match lda_config.txt (cosmetic blank-line difference only) |
| VOLARB notice | LDA superseded by VOLARB Phase 1 2026-05-16 21:00 UTC; last LDA fill 20:00 UTC — n growth STOPPED |

**Data window:** 2026-05-15T15:02:00Z (Kelly-disable boundary) → 2026-05-17T00:02:11Z (snapshot)

**Overall LDA (lda_status.txt canonical):** n=111 WR=82.0% Net=+$7.01 Avg_EV=+$0.84%/fire CI95=[-7.89,+9.37]

**Dedup note:** canonical key is (condition_id, window_end_ts, rem_bucket); audit used (asset, direction, 5m-window) proxy → yields n=116 vs n=111. All analysis below uses canonical n=111 for overall-EV baseline. Per-cell n from proxy dedup.

---

## Data Integrity Flags

| field | problem | impact |
|---|---|---|
| `term_remaining_s` | all 0.0 in trades.jsonl | rem_bucket indeterminate; bucket-level analysis BLOCKED |
| `binance_ret_5m_pct` | field absent from trade records | BNC floor uplift analysis BLOCKED |
| `term_binance_5m_pct` | all 0.0 | same |
| `term_spot_delta_5m/30s/60s/5s` | all 0.0 | feature analysis blocked |

These fields appear populated at runtime (lda_status.txt computes correctly) but are not flushed to trades.jsonl. Fix required in LDA trade logger before bucket or BNC analysis can run.

---

## 6h Recency Cells (n≥10 flag threshold)

Window: 2026-05-16T18:02 → 2026-05-17T00:02 UTC

| cell | n | WR | kline_sum | flag |
|---|---|---|---|---|
| H18×B?×BTC | 1 | 0% | -$20.03 | n<10, no flag |
| H20×B?×ETH | 1 | pending | — | kline_pnl unresolved |

No cell reaches n≥10 in the 6h window. VOLARB deployment at 21:00 UTC truncated LDA fills.

---

## All-Time Cell Scan (data window: 2026-05-15T15:02Z .. 2026-05-17T00:02Z)

Overall EV baseline from lda_status.txt: $7.01 / 111 = **$0.063/fire**.
Bucket dim indeterminate (term_remaining_s logging bug); reported as hour×B?×asset.

| hour×bucket×asset | n | WR | PF | sum($) | uplift_vs_baseline | status |
|---|---|---|---|---|---|---|
| H07×B?×ETH | 6 | 67% | 0.421 | -6.44 | -1.14/fire | too_small |
| H09×B?×ETH | 4 | 75% | 0.966 | -0.17 | -0.31/fire | too_small |
| H10×B?×BTC | 10 | 60% | 0.364 | -16.37 | -1.70/fire | **collect** |
| H10×B?×ETH | 10 | 70% | 0.617 | -9.32 | -1.00/fire | **collect** |
| H14×B?×ETH | 3 | 33% | 0.172 | -16.27 | -5.55/fire | too_small |
| H16×B?×BTC | 12 | 75% | 0.715 | -7.51 | -0.69/fire | **collect** |
| H18×B?×BTC | 4 | 75% | 0.181 | -16.41 | -4.17/fire | too_small |
| H06×B?×BTC | 2 | 100% | inf | +3.90 | +1.84/fire | too_small |
| H07×B?×BTC | 3 | 100% | inf | +5.97 | +1.93/fire | too_small |
| H09×B?×BTC | 6 | 67% | 1.495 | +4.95 | +0.76/fire | too_small |
| H14×B?×BTC | 5 | 80% | 2.123 | +11.33 | +2.20/fire | too_small |
| H16×B?×ETH | 2 | 100% | inf | +4.19 | +2.04/fire | too_small |
| H17×B?×BTC | 10 | 90% | 3.448 | +13.11 | +1.25/fire | collect (positive) |
| H17×B?×ETH | 6 | 83% | 1.877 | +4.44 | +0.68/fire | too_small |
| H18×B?×ETH | 9 | 100% | inf | +16.96 | +1.82/fire | too_small |
| H20×B?×ETH | 6 | 100% | inf | +9.75 | +1.56/fire | too_small |

Max n per cell: 12 (H16×BTC). Patch threshold n≥100 not reached by any cell.

lda_status.txt confirms H10 as worst hour (n=19 WR=63.2% Net=-$32.20) — consistent with cell scan.
Rolling-20 net: -$8.81 (current). Worst rolling-20: -$36.39 (T05206_BTC). lda_status STATUS: STOP.

---

## BNC Floor Analysis

**BLOCKED: `binance_ret_5m_pct` all 0.0 in trades.jsonl** — cannot validate whether current floors (0.10% at ask<0.70, 0.05% at ask<0.90, 0.07% at ask≥0.90) are correctly sized.

Ask-zone distribution (n counts only, without BNC signal):

| ask zone | n | WR | PF | net($) | BNC floor change eligible |
|---|---|---|---|---|---|
| <0.70 | 3 | 33% | 0.113 | -17.20 | NO (n=3<100) |
| [0.70,0.90) | 111 | 83% | 1.318 | +45.58 | n≥100 — but BNC field unavailable |
| ≥0.90 | 2 | 100% | inf | +0.94 | NO (n=2<100) |

No BNC floor change warranted. [0.70,0.90) is positive-EV at n=111 — existing floor not causing visible bleed.

---

## Proposed Patch

**No patch.** Decision: COLLECTING.

- All cells n<40 → collect (no watchlist entries, no block/unblock candidates)
- BLOCK condition requires n≥100: not met
- UNBLOCK condition requires n≥100: not met
- BNC floor requires uplift>+$15 net at n≥100: not met (field unavailable)
- VOLARB deployment means LDA n is frozen at ~111 unless strategy resumes

---

## Watchlist (40≤n<100)

None. No cell reaches n=40. Pre-watchlist cells if LDA resumes:

| cell | n | WR | PF | sum | trend | delta vs prior watchlist |
|---|---|---|---|---|---|---|
| H10×B?×BTC | 10 | 60% | 0.364 | -$16.37 | negative | prior audit BOND-era: N/A |
| H10×B?×ETH | 10 | 70% | 0.617 | -$9.32 | negative | prior audit BOND-era: N/A |
| H16×B?×BTC | 12 | 75% | 0.715 | -$7.51 | negative | prior audit BOND-era: N/A |
| H17×B?×BTC | 10 | 90% | 3.448 | +$13.11 | positive | prior audit BOND-era: N/A |

Prior audit report was BOND-era (all data stale/inapplicable) — no delta comparison possible.

---

## Skipped — User Override (state_log)

No block/unblock decisions reached threshold. For reference, cells state_log shows user explicitly handled (do not re-block without instruction):

| cell | state_log action | date |
|---|---|---|
| H23 B1 | partial unblock (H23 B2 only enabled, B0/B2/B3 remain blocked) | 2026-05-16 |
| H07 B1 | unblocked from `_ALL_BLOCKED_LATE_B1` | 2026-05-15 |
| H21 BTC B3 | user-blocked ("shadow+0.43 n=15 user block") | in _BTC_BLOCKED_B3 |
