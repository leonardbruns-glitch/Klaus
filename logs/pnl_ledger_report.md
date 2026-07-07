# Klaus PnL Ledger — 2026-07-07 *** STALL REPORT — DATA MIRROR DEAD ***
*Generated 2026-07-07T23:37Z | Snapshot age: ~20h 40m (ABORT threshold: 6h)*

---

## ABORT: STALE DATA — FULL PIPELINE NOT RUN

**Snapshot last updated: 2026-07-07T02:57:08Z** (commit `bfd3397753566d91a322c1c018f31a89850d6715`).
Run time: ~23:37 UTC. Snapshot age: **~20h 40m — exceeds 6h abort threshold.**

The `data-mirror` timer last pushed at **02:57 UTC July 7**. The prior two commits are
02:42Z and 02:27Z — consistent with a timer that was running normally and then stopped.
Since then: 20+ hours of silence. Root cause unknown from this vantage point; candidates are
VPS outage, systemd timer failure, or a git-push error that silenced the timer.

**This report covers last-known state only. Current capital and position state are UNKNOWN.**

---

## Last-Known State (2026-07-07T02:57Z snapshot)

| Field | Value |
|---|---|
| capital | **$42.02** |
| daily_start_capital | $108.35 |
| open positions | 0 |
| bot systemd | active (at snapshot time; current state unknown) |
| bot uptime since | 2026-07-06 22:08:19 UTC |
| trades.jsonl rows | 8,116 |
| disk utilization | 89% (11 GB free) |
| BAND_LIVE | **False** (wind-down) |
| M1_BETA_PROBE_ENABLED | **False** (wind-down) |
| MIN_LOCKOUT_LIVE | **False** (wind-down) |
| SPRINT_LADDER_LIVE | **1 — NOT disabled** (excluded from wind-down per state_log) |

---

## § 1 — Capital Trajectory (Jul 5 close → Jul 7 02:57Z)

| Checkpoint | Time (UTC) | Capital | Source |
|---|---|---|---|
| Jul 5 ledger close | 2026-07-05 23:37Z | **$217.44** | prior pnl_ledger_state.json |
| Jul 5 EVOLVE — 30d HW set | 2026-07-05 22:25Z | $222.90 equity | state_log (cash $196.83 + Munich $26.07) |
| Jul 6 wind-down trigger | 2026-07-06 ~21:53Z | **$108.35** | state_log + system_status (EVOLVE daily) |
| Jul 7 last snapshot | 2026-07-07 02:57Z | **$42.02** | bankroll.json |
| **Jul 7 NOW (~23:37Z)** | **UNKNOWN** | **UNKNOWN** | data mirror dead |

**2-day loss (Jul 5 → Jul 7 02:57Z): −$175.42 (−80.7% from $217.44)**

### July 6 Attributed P&L (partial — no full day analysis)

| Event | Time (UTC) | PnL | Source |
|---|---|---|---|
| recycle099 (9sh, 0.46→0.999) | ~07:55 Jul 6 | +$4.85 | shadow/2026-07-06/exit099_live.jsonl |
| exit099 M1_PROBE (26.28sh, 0.09→0.99) | ~11:56 Jul 6 | +$23.60 | shadow/2026-07-06/exit099_live.jsonl |
| recycle099 (9sh, 0.44→0.99) | ~17:02 Jul 6 | +$4.95 | shadow/2026-07-06/exit099_live.jsonl |
| Moscow M1β FALSE LOCKOUT (NO@0.9352 $19.64 + maker NO@0.06 $5 fill) | Jul 6 | **−$24.65** | state_log 22:10Z |
| Sprint ladder + unidentified band losses | Jul 6 | **~−$117.60** est. | residual |
| **Jul 6 total** | | **~−$109.09** | $217.44 → $108.35 |

**Jul 6 → Jul 7 02:57Z (5-hour overnight window):**

| Event | PnL | Source |
|---|---|---|
| No exit099_live events on Jul 7 (shadow file absent) | $0 | confirmed |
| Sprint ladder continuation (SPRINT_LADDER_LIVE=1, not disabled) | **~−$66.33** est. | residual |
| **Jul 7 early-morning total** | **~−$66.33** | $108.35 → $42.02 |

Sprint ladder (Dubins–Savage bold-play on longshot YES markets) was explicitly excluded
from the wind-down per state_log 22:10Z: "live surface now NEG_RISK_ARB + RECYCLE099 +
redemption **(+ principal-authorized sprint ladder, outside charter scope)**."
The overnight $66 loss is attributed to sprint ladder as the only live capital-consuming
engine after wind-down. **This is the most likely cause; it is not confirmed** — trades.jsonl
(26 MB, inaccessible) is required for per-trade attribution.

---

## § 2 — Compounding Scoreboard

**Cannot compute for July 7** — data mirror dead; fills and resolved legs for the 20.7h
blackout window are unknown.

**Last-known equity (Jul 7 02:57Z):**

| Component | Value | Caveat |
|---|---|---|
| Cash (bankroll.json) | $42.02 | stale; 20.7h old |
| Open positions | 0 (at snapshot) | unknown since |
| equity_est | **~$42.02** | lower bound; any sprint ladder bets placed after 02:57Z not captured |

Turns/day and ROI/turn cannot be computed without current trades data.

---

## § 3 — Expected Maker Rebates

Maker fills for July 6-7 are unavailable (no shadow/thermo_maker.jsonl for Jul 6 or Jul 7;
band_struct_lite.jsonl too large for this run).

**Cumulative expected rebate through Jul 5 (last ledger): $2.757.**
No new rebate estimate can be computed for Jul 6-7 without fill tape access.

**FLAG (carried forward):** Cumulative expected $2.757 > $1 minimum payout. User should
verify pUSD receipt in Polymarket account. No rebate receipt recorded in available data.

---

## § 4 — Kill-Switch Proximity

| Gate | Threshold | Last-Known ($42.02) | Current | Status |
|---|---|---|---|---|
| Day PnL halt | < −$10/day | Jul 7: daily_start $108.35 → $42.02 = **−$66.33** | UNKNOWN | **BREACHED** (last-known) |
| Weekly floor | capital < $75 | **$42.02 < $75** | UNKNOWN | **BREACHED** (last-known) |
| Ruin floor (ledger) | capital < $50 | **$42.02 < $50** | UNKNOWN | **BREACHED** (last-known) |
| Ruin floor (bot-armed, state_log Jul 3) | $40 | $42.02 ($2.02 above) | UNKNOWN | AT THRESHOLD |

**CAVEAT — WR/PF floors:** Kill-switch re-derivation for maker era is still pending.
WR/PF floors specified for the taker era are not applicable to the maker band book.
The above cash-floor breaches are objective regardless of era.

**Sprint ladder exposure:** With capital near $42 and the sprint ladder running unbounded,
individual bold-play bets can represent 20-50%+ of remaining capital. The bot-armed ruin
floor of $40 (state_log Jul 3) provides only a $2.02 buffer.

---

## § 5 — Day Verdict

**CANNOT DETERMINE — data mirror dead for 20.7h.**

Last-known: **NO — equity did NOT compound on July 6 or July 7 early morning.**
- Jul 6: −$109.09 (−50.2% of $217.44)
- Jul 7 through 02:57Z: additional −$66.33 (−61.2% of $108.35)
- Combined 2-day loss from Jul 5 close: **−$175.42 (−80.7%)**

**Binding constraint:** Sprint ladder bold-play losses during/after wind-down. Three weekly-floor
and ruin-floor kill switches are breached on last-known data ($42.02). Capital after 02:57Z
is unknown — may be lower. **Immediate manual verification of account balance required.**

**Data-mirror issue is a separate operational problem.** Even if capital is intact, 20+ hours
without a data snapshot means no automated monitoring has been possible. The data-mirror
systemd timer needs inspection on the VPS.

---
*Report generated by pnl-ledger-agent | STALL ABORT | last good snapshot 2026-07-07T02:57:08Z (age 20h 40m) | trades.jsonl: not accessed | full pipeline skipped per abort protocol*
