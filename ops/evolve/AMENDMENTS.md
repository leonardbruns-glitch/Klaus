# CHARTER AMENDMENTS — two-reading protocol log

A charter change by an unattended agent requires two readings, ≥7 days apart, both by
WEEKLY runs (daily/repair runs may never amend):

- **First reading (week N):** append below — exact charter diff, evidence, expected
  effect, and what would prove it wrong (the falsifier).
- **Second reading (week N+1):** re-validate against the fresh week's data. If still
  justified and kernel-compatible → apply the diff to CHARTER.md, mark APPLIED here,
  log to state_log.md. Otherwise mark REJECTED with the data that killed it.

A proposal that would weaken `INVARIANTS.md` is invalid at any reading.

---
(no proposals yet)

## 2026-07-19 — FIRST READING (weekly): ledger pre-registration for interactive deploys
**Proposed diff to CHARTER.md, "Deployment discipline" — append as item 6:**
> 6. Interactive/owner sessions deploying live-effect changes register them in
>    `logs/evolve/ledger.jsonl` at deploy time like any other change. The next
>    unattended run's FIRST bookkeeping act is to retro-register anything missing
>    (not counted vs the 2-change cap). A live change with no ledger entry has no
>    review_date and no revert_condition — it is invisible to the loop's rails.
**Evidence:** 07-08 interactive session deployed 4 live-effect changes with no
ledger entries (retro-registered 07-08 evening; ESCALATIONS #3 that day). 07-16
owner waivers 1–3 (candidate arm, Kelly 50%, CLIP_CAP 100) reached the ledger only
because the evening slot back-filled them. 07-19: the rail cut itself sat
unregistered ~3h because the morning slot died mid-run (session limit), and only
the weekly's backlog check caught it.
**Expected effect:** every live change carries review_date + revert_condition from
birth; the kill-watch never runs on an undocumented policy.
**Falsifier (second reading 2026-07-26):** if the week shows retro-registration
produced duplicate/conflicting entries, or the rule added friction that delayed a
risk action, mark REJECTED.
