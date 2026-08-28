#!/usr/bin/env python3
"""
backfill_skill.py — prove the revived learning loop, DRY-RUN (no writes).

The learning loop is dead only because `log_actual` has no producer. But we already
have the actuals on disk (realized daily-max in metar_lockout.jsonl). This pairs the
logged forecasts with those realized maxes and runs the accumulator's OWN pure
functions (compute_incremental_skill + _merge_skill) to show EXACTLY what the skill
matrix would learn once the loop is revived — without touching skill_matrix.json or
the live forecast_actuals.jsonl (so the running bot's actuals-consumer is untouched).

This is the validation gate before wiring the live producer.

Run:  python3 -m analysis.weather.backfill_skill
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

from analysis.weather.skill_scorecard import (
    load_name_to_slug, load_actuals, load_forecasts, final_snapshot, ROOT,
)
from analysis.weather.live_accumulator import compute_incremental_skill, _merge_skill


def build_paired():
    name_to_slug = load_name_to_slug()
    actuals = load_actuals(name_to_slug)
    fc = load_forecasts()
    paired = []
    for key, snaps in fc.items():
        act = actuals.get(key)
        if act is None:
            continue
        _lead, mv, _mu, _sig = final_snapshot(snaps)
        if not mv:
            continue
        paired.append({
            "city_slug": key[0],
            "valid_day": key[1],
            "month": int(key[1][5:7]),
            "model_values": mv,
            "wu_high_c": float(act),
        })
    return paired


def main():
    paired = build_paired()
    print(f"=== REVIVED-LOOP DRY-RUN ===")
    print(f"paired forecast↔actual records: {len(paired)} "
          f"across {len({p['city_slug'] for p in paired})} cities")
    if not paired:
        print("no pairs"); return

    incr = compute_incremental_skill(paired)   # {slug:{model:{month:{bias,sigma,n}}}}
    raw = json.loads((ROOT / "strategy/skill_matrix.json").read_text())
    base = raw.get("stations", {})
    merged = _merge_skill(base, incr)

    # How big is the update?
    cells = sum(len(mm) for ms in incr.values() for mm in ms.values())
    print(f"new/updated (city,model,month) skill cells: {cells}")

    # The headline fix: per-model σ should GROW (live forecast error > ERA5 floor),
    # and biases should move toward the live values. Show the largest σ corrections.
    deltas = []   # (abs_dsig, slug, model, month, b0,s0,n0, b1,s1,n1)
    for slug, ms in incr.items():
        for model, mm in ms.items():
            for mo, live in mm.items():
                b0 = base.get(slug, {}).get(model, {}).get(mo)
                m1 = merged[slug][model][mo]
                if b0:
                    deltas.append((abs(m1["sigma"] - b0["sigma"]), slug, model, mo,
                                   b0["bias"], b0["sigma"], b0["n"],
                                   m1["bias"], m1["sigma"], m1["n"]))
                else:
                    deltas.append((m1["sigma"], slug, model, mo,
                                   None, None, 0, m1["bias"], m1["sigma"], m1["n"]))

    print("\n── largest σ corrections (base → merged) ──")
    print(f"  {'city':<14} {'model':<16} {'mo':>2} {'bias':>14} {'sigma':>14} {'n':>9}")
    for d in sorted(deltas, reverse=True)[:18]:
        _, slug, model, mo, b0, s0, n0, b1, s1, n1 = d
        if b0 is None:
            print(f"  {slug:<14} {model:<16} {mo:>2}   NEW {b1:+.2f}      NEW {s1:.2f}     n={n1}")
        else:
            print(f"  {slug:<14} {model:<16} {mo:>2} {b0:+.2f}→{b1:+.2f}  {s0:.2f}→{s1:.2f}  {n0}→{n1}")

    # Aggregate: mean σ before/after for the touched cells (does dispersion widen?)
    s_before = [d[5] for d in deltas if d[5] is not None]
    s_after = [d[8] for d in deltas if d[5] is not None]
    if s_before:
        import statistics as st
        print(f"\n  mean per-model σ on touched cells: {st.fmean(s_before):.2f} → {st.fmean(s_after):.2f} °C")
        print(f"  (σ growing = ERA5 floor was too tight = the overconfidence fix taking effect)")
    print("\nDRY-RUN ONLY — skill_matrix.json NOT modified, live actuals file NOT touched.")


if __name__ == "__main__":
    main()
