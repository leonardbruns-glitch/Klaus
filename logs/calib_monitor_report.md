# Calibration & Dispersion Monitor — 2026-08-19

## STALL — DATA INFRASTRUCTURE ABSENT

**Abort condition triggered:** `system_status.txt` is missing from `data-mirror` branch (not stale — not present at all). Cannot confirm `klaus systemd: active`. Halting per task protocol.

---

### What was checked

| File | Expected location | Status |
|---|---|---|
| `SNAPSHOT.md` | `data-mirror:data/SNAPSHOT.md` | MISSING |
| `system_status.txt` | `data-mirror:data/system_status.txt` | MISSING |
| `band_config.txt` | `data-mirror:data/band_config.txt` | MISSING |
| `shadow_summary.json` | `data-mirror:data/shadow_summary.json` | MISSING |
| `trades.jsonl` | `data-mirror:data/trades.jsonl` | MISSING |
| `state_log.md` | `data-mirror:data/state_log.md` | MISSING |
| Shadow pricer files | `data-mirror:data/shadow/*/stwa_pricer_eval_s50.jsonl` | MISSING |
| Shadow band files | `data-mirror:data/shadow/*/band_struct_lite.jsonl` | MISSING |

**data-mirror branch contents** (actual): only `data/__init__.py` and `data/feeds.py` — the crypto trading bot's feed module. No weather/STWA/band data has ever been committed to this branch.

Additionally, `git fetch origin` timed out (network unavailable in this sandbox), so the branch was inspected via GitHub API.

---

### Root cause

The `data-mirror` branch is the Klaus crypto bot's feature branch, not a weather-market data mirror. The STWA pricer / band / shadow pipeline infrastructure that this calibration monitor depends on does not exist in this repository as of 2026-08-19.

Possible explanations:
1. The data-mirror push from the VPS has never run (bot not yet in weather-market mode)
2. The scheduled task was configured for a repository that doesn't yet have the weather layer
3. The VPS cron that writes `data/shadow/` has not been set up

---

### Pipeline sections

**1. SETTLED LANE:** Cannot run — no pricer_eval_s50 data.  
**2. PROXY LANE:** Cannot run — no today_pricer_full data.  
**3. DISPERSION GAUGE:** Cannot run — no shadow band/pricer data. Edge-health unknown.  
**4. ISOTONIC STALENESS:** Cannot run — no `config/stwa_isotonic.json` or `config/stwa_isotonic_candidate.json`.  
**5. STATE:** Written as stall record (see `logs/calib_monitor_state.json`).

---

### ALERTS

No pre-registered alerts can be evaluated. The absence of data is itself the alert: if the weather bot is supposed to be live and writing to data-mirror, it has not done so. The dispersion edge this monitor exists to guard cannot be confirmed healthy or decaying.

---

### Recommendation (report-only)

Verify on the VPS that:
- `systemctl status klaus` is active
- The data-mirror push cron is running (`crontab -l | grep data-mirror`)
- At least one `data/shadow/` file has been pushed in the last 24h

This monitor cannot resume meaningful operation until at least `SNAPSHOT.md` and one day of `stwa_pricer_eval_s50.jsonl` are present on `data-mirror`.
