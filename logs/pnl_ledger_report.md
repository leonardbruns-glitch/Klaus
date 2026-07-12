# Klaus PnL Ledger — 2026-07-12
**Generated:** 2026-07-12T23:37Z (scheduled day-end run)
**Snapshot age:** 21h (last push: 2026-07-12T02:47:46Z) — STALE ✗
**System status at snapshot:** `active` ✓ (but 21h stale)

## ABORT — DATA-MIRROR STALL

Snapshot is 21 hours old (abort threshold: 6h). The `klaus_data_mirror.timer` has not pushed since **2026-07-12T02:47:46Z**. Full PnL analysis cannot be run on stale data — any figure would be fabricated from old snapshots. Report terminates here.

---

## What the stale snapshot shows

| Field | Value | Note |
|---|---|---|
| Snapshot timestamp | 2026-07-12T02:47:46Z | 21h ago |
| Capital at snapshot | $152.653 | Stale |
| Daily start capital | $165.731 | Stale |
| Intraday delta at snapshot | **−$13.08 (−7.9%)** | Only 02:47Z; unknown since |
| Prior ledger close (Jul 10) | $163.164 | From last good run |
| Change Jul 10→snapshot | **−$10.51** | Covers Jul 11 + partial Jul 12 |
| Bot systemd at snapshot | `active` | Restarted 2026-07-11T22:06:15Z |
| Current bot state | **UNKNOWN** | No data since 02:47Z |

**The −$13.08 intraday move at 02:47Z is notable.** The Jul 11 gate-keeper commit logged `bankroll alert -$40.90 ladder`, and the Jul 11 EVOLVE commit resolved the winner's curse finding (`realized -75.8% vs sim +7.6%, n=75`). The ladder book appears to be the primary PnL driver and has been losing. Capital trajectory since Jul 10 is down.

---

## Probable causes of timer stall

1. **Disk pressure (most likely):** VPS disk was at 93% (86G/97G) at snapshot. `git push` on the data-mirror branch may be failing silently if `/tmp` or the repo work tree ran out of space.
2. **Bot crash / restart loop:** Bot was restarted at 22:06 Jul 11 — if it crashed again, the timer script may have no lock and be failing.
3. **Network / git auth issue:** Less likely but possible if SSH key rotated.

**Check commands on VPS:**
```bash
systemctl status klaus_data_mirror.timer
journalctl -u klaus_data_mirror --since '2026-07-12 02:00' --no-pager
df -h
systemctl status klaus
```

---

## Today's weekly review context

Today (2026-07-12) was the scheduled weekly band re-enable review date (per prior state: `band_live_re_enable_gate: "Weekly review 07-12"`). No data is available to assess that decision. The review should be deferred until the data-mirror is restored and a fresh snapshot is available.

---

## Kill-switch (stale, informational only)

| Check | Value at 02:47Z | Status |
|---|---|---|
| Capital vs weekly floor $75 | $152.65 | STALE CLEAR |
| Capital vs ruin floor $50 | $152.65 | STALE CLEAR |
| Day PnL vs halt −$10 | −$13.08 intraday | ⚠ STALE BREACH at snapshot |

> The intraday figure (−$13.08) was at 02:47Z with ~21h unobserved since. If day-halt threshold is −$10 and the bot was live, this may already have breached. Cannot confirm without fresh data. **Check bot state immediately.**

> **CAVEAT:** Kill-switch thresholds are taker-era; maker YES legs ~22% WR by design. Re-derivation pending with user.

---

## Day Verdict

**ABORT — no verdict possible.** Data-mirror stalled 21h. Last known capital: **$152.65** (stale). Restore `klaus_data_mirror.timer` to resume ledger runs.
