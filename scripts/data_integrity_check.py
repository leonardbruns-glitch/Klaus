#!/usr/bin/env python3
"""data_integrity_check.py — pre-flight integrity check for Klaus agents.

Reads a trades.jsonl, produces integrity_report.json with:
- Per-issue severity (CRITICAL / HIGH / MEDIUM / INFO)
- Counts + percentages where relevant
- A blocks_agent_run flag (true if any CRITICAL)

Scheduled agents (Auditor, Scout, Watchdog, Validator) MUST run this
as pre-flight and abort with DATA_POLLUTED if blocks_agent_run is true.
The mirror script runs this each snapshot and ships the report.

Usage:
  data_integrity_check.py --trades /path/to/trades.jsonl --output report.json
  data_integrity_check.py --trades trades.jsonl  # prints to stdout
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

# ─── Era boundaries (mirror agent_context/research_status.md §5) ─────────────
# 2026-05-15 15:02 UTC — Kelly disable boundary; current LDA-flat-$5 era
ERA_KELLY_DISABLE = 1778857320

# Severities ordered by blocking severity
SEV_ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "INFO": 0, "OK": -1}


def load_trades(path: str) -> tuple[list[dict], int]:
    trades: list[dict] = []
    bad = 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return trades, bad


def integrity_check(trades: list[dict], malformed_lines: int = 0,
                    era_boundary: int = ERA_KELLY_DISABLE) -> dict:
    issues: dict[str, dict] = {}

    if malformed_lines > 0:
        issues["MALFORMED_LINES"] = {
            "severity": "HIGH",
            "count": malformed_lines,
            "msg": f"{malformed_lines} non-JSON lines in trades.jsonl",
        }

    # Filter
    lda_all = [t for t in trades
               if t.get("signal_source") == "LDA" and t.get("is_live") is True]
    lda_era = [t for t in lda_all if (t.get("ts_open") or 0) >= era_boundary]
    n_era = len(lda_era)

    if not trades:
        issues["EMPTY_TRADES_FILE"] = {
            "severity": "CRITICAL",
            "msg": "trades.jsonl is empty",
        }
        return _summarize(issues, trades, lda_all, lda_era, era_boundary)

    if n_era == 0:
        issues["NO_LDA_ERA_TRADES"] = {
            "severity": "CRITICAL",
            "msg": "0 LDA trades in current era — agents cannot analyse",
        }
        return _summarize(issues, trades, lda_all, lda_era, era_boundary)

    # ── Required field presence ─────────────────────────────────────────────
    for field, severity in [
        ("ts_open", "CRITICAL"),
        ("ts_close", "HIGH"),
        ("entry_price", "CRITICAL"),
        ("asset", "CRITICAL"),
        ("net_pnl", "HIGH"),
    ]:
        missing = sum(1 for t in lda_era if t.get(field) is None or t.get(field) == "")
        if missing:
            pct = 100 * missing / n_era
            issues[f"NULL_{field.upper()}"] = {
                "severity": severity,
                "count": missing,
                "pct": round(pct, 1),
                "msg": f"{missing}/{n_era} ({pct:.1f}%) trades missing {field}",
            }

    # ── kline_pnl coverage (special: LDA_KLINE_WIN MUST have it) ────────────
    null_kline = [t for t in lda_era if t.get("kline_pnl") is None]
    if null_kline:
        n = len(null_kline)
        pct = 100 * n / n_era
        # Specific: LDA_KLINE_WIN with null kline_pnl is a real bug
        kw_null = sum(1 for t in null_kline if t.get("exit_reason") == "LDA_KLINE_WIN")
        severity = "CRITICAL" if pct > 25 else "HIGH" if (pct > 10 or kw_null > 0) else "MEDIUM"
        issues["NULL_KLINE_PNL"] = {
            "severity": severity,
            "count": n,
            "pct": round(pct, 1),
            "lda_kline_win_with_null": kw_null,
            "msg": f"{n}/{n_era} ({pct:.1f}%) trades have null kline_pnl"
                   + (f"; {kw_null} of those are LDA_KLINE_WIN exits (real bug)" if kw_null else ""),
        }

    # ── Dedup keys (informational — in-memory dedup still works) ────────────
    no_dedup = sum(1 for t in lda_era
                   if not t.get("condition_id") or not t.get("window_end_ts"))
    if no_dedup:
        pct = 100 * no_dedup / n_era
        issues["MISSING_DEDUP_KEYS"] = {
            "severity": "MEDIUM",
            "count": no_dedup,
            "pct": round(pct, 1),
            "msg": f"{no_dedup}/{n_era} ({pct:.1f}%) trades lack condition_id+window_end_ts in log "
                   "(in-memory dedup still functional; per-window dedup from log impossible)",
        }

    # ── Timestamp monotonicity ──────────────────────────────────────────────
    non_mono = sum(1 for t in lda_era
                   if (t.get("ts_close") or 0) <= (t.get("ts_open") or 0))
    if non_mono:
        issues["NON_MONOTONIC_TS"] = {
            "severity": "HIGH",
            "count": non_mono,
            "msg": f"{non_mono} trades with ts_close <= ts_open",
        }

    # ── bond_entry_class persistence bug ────────────────────────────────────
    empty_bec = sum(1 for t in lda_era if not t.get("bond_entry_class"))
    if empty_bec:
        issues["EMPTY_BOND_ENTRY_CLASS"] = {
            "severity": "MEDIUM",
            "count": empty_bec,
            "msg": f"{empty_bec} LDA trades have empty bond_entry_class "
                   "(restart-persistence bug — class-filtered queries miss these)",
        }

    # ── GHOST_POSITION (position state divergence) ──────────────────────────
    ghost = [t for t in lda_era if t.get("exit_reason") == "GHOST_POSITION"]
    if ghost:
        issues["GHOST_POSITION"] = {
            "severity": "MEDIUM",
            "count": len(ghost),
            "msg": f"{len(ghost)} GHOST_POSITION exits — exclude from analytics",
        }

    # ── SOL leakage (gate should block) ─────────────────────────────────────
    sol_n = sum(1 for t in lda_era if t.get("asset") == "SOL")
    if sol_n:
        issues["SOL_LEAKAGE"] = {
            "severity": "HIGH",
            "count": sol_n,
            "msg": f"{sol_n} SOL LDA trades despite block — possible gate failure",
        }

    # ── Aged trades missing window_outcome_price ────────────────────────────
    # Only flag trades older than 6h — younger ones may not be resolved yet
    now = time.time()
    aged_unresolved = [t for t in lda_era
                       if not t.get("window_outcome_price")
                       and (now - (t.get("ts_close") or 0)) > 6 * 3600]
    if aged_unresolved:
        n = len(aged_unresolved)
        aged_era = [t for t in lda_era
                    if (now - (t.get("ts_close") or 0)) > 6 * 3600]
        denom = max(1, len(aged_era))
        pct = 100 * n / denom
        severity = "HIGH" if pct > 30 else "MEDIUM"
        issues["AGED_NO_RESOLUTION"] = {
            "severity": severity,
            "count": n,
            "denom_aged": denom,
            "pct": round(pct, 1),
            "msg": f"{n}/{denom} ({pct:.1f}%) trades >6h old lack window_outcome_price "
                   "(resolution may live in post_exit.jsonl)",
        }

    # ── Suspicious net_pnl == 0 (might be orphan/error) ─────────────────────
    zero_net = sum(1 for t in lda_era if t.get("net_pnl") == 0.0)
    if zero_net:
        issues["ZERO_NET_PNL"] = {
            "severity": "MEDIUM",
            "count": zero_net,
            "msg": f"{zero_net} trades with net_pnl=0 exactly (may be orphans)",
        }

    return _summarize(issues, trades, lda_all, lda_era, era_boundary)


def _summarize(issues: dict, trades: list, lda_all: list, lda_era: list,
               era_boundary: int) -> dict:
    severities = [v.get("severity") for v in issues.values()]
    highest = max(severities, key=lambda s: SEV_ORDER.get(s, 0), default="OK")
    blocks = "CRITICAL" in severities

    return {
        "snapshot_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "era_boundary_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(era_boundary)),
        "trades_total": len(trades),
        "lda_trades_all_eras": len(lda_all),
        "lda_trades_current_era": len(lda_era),
        "assets": dict(Counter(t.get("asset") for t in lda_era)),
        "exit_reasons_top": dict(Counter(t.get("exit_reason") for t in lda_era).most_common(10)),
        "issues": issues,
        "highest_severity": highest,
        "blocks_agent_run": blocks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trades", default="/root/Klaus/logs/trades.jsonl",
                    help="path to trades.jsonl")
    ap.add_argument("--output", default="-",
                    help="output path (- for stdout)")
    ap.add_argument("--era-boundary", type=int, default=ERA_KELLY_DISABLE,
                    help="unix ts of era start (filters LDA trades)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress stderr warnings")
    args = ap.parse_args()

    if not Path(args.trades).exists():
        report = {
            "snapshot_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "issues": {"TRADES_FILE_MISSING": {
                "severity": "CRITICAL",
                "msg": f"{args.trades} does not exist",
            }},
            "blocks_agent_run": True,
            "highest_severity": "CRITICAL",
        }
    else:
        trades, bad = load_trades(args.trades)
        if bad and not args.quiet:
            print(f"[integrity_check] {bad} malformed lines skipped", file=sys.stderr)
        report = integrity_check(trades, malformed_lines=bad,
                                 era_boundary=args.era_boundary)

    out = json.dumps(report, indent=2, sort_keys=True)
    if args.output == "-":
        print(out)
    else:
        Path(args.output).write_text(out + "\n")

    # Exit code: 2 if blocks, 1 if non-critical issues, 0 if clean
    if report.get("blocks_agent_run"):
        return 2
    if report.get("issues"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
