# Calib Monitor Report — 2026-08-18 — STALL

**STATUS: ABORTED — DATA PIPELINE NOT RUNNING**

Run timestamp: 2026-08-18 (UTC)

## Abort Condition

Required data files are entirely absent from the `data-mirror` branch:
- `data/SNAPSHOT.md` — NOT FOUND
- `data/system_status.txt` — NOT FOUND
- `data/shadow/` directory — NOT FOUND
- `data/band_config.txt` — NOT FOUND
- `data/shadow_summary.json` — NOT FOUND

The `data-mirror` branch and `claude/find-lag-parameter-rFQ0N` branch both resolve to the same commit tree as the main code branch. No VPS data has ever been pushed to the data-mirror branch.

Task abort rule: *ABORT if SNAPSHOT.md timestamp > 6h old OR system_status.txt missing 'klaus systemd: active'* — system_status.txt is entirely absent, which satisfies the abort condition.

## Root Cause

The VPS-side data mirror cron has either:
1. Never been configured, or
2. Failed to push any data to the `data-mirror` branch

The calibration and dispersion monitor cannot operate without live pricer logs (`stwa_pricer_eval_s50.jsonl`), band structure data (`band_struct_lite.jsonl`), or system health confirmation.

## No Metrics Computed

Brier-7d, ECE-7d, rank-rho, dispersion ratio: **all N/A — no data**

No alerts fired (no data to evaluate). No state file written (nothing to persist).

## Required Action

The VPS-side pipeline must be set up to push data files to the `data-mirror` branch before this monitor can run. Specifically needed:
- `data/SNAPSHOT.md` (with current UTC timestamp)
- `data/system_status.txt` (containing 'klaus systemd: active')
- `data/shadow/YYYY-MM-DD/stwa_pricer_eval_s50.jsonl` (1-in-50 sampled pricer rows)
- `data/shadow/YYYY-MM-DD/band_struct_lite.jsonl` (band structure snapshots)
- `data/shadow_summary.json`
- `data/band_config.txt`
