"""Three example duckdb queries against the Phase-1 shadow substrate.

Run:  python3 analytics/shadow_query.py [path_to_shadow_root]

Default root: logs/shadow/hot/<today>. Uses duckdb in-process; no server needed.
Reads JSONL directly via read_json_auto — fine for the hot tier; warm/cold tier
will be Parquet (Phase 2).

Validation queries:
  1. Coverage     — rows/min/asset, would-take rate
  2. Reconstruct  — virtual-entry hit-rate at ask=[0.78,0.92] vs window_resolution
  3. Cross-check  — gate_trace `would_take_at_ask` rate vs trades.jsonl entries

Each query is self-contained — copy/paste into a duckdb shell or notebook.
"""
import os
import sys
from datetime import datetime, timezone

try:
    import duckdb
except ImportError:
    print("duckdb not installed.  pip install duckdb")
    sys.exit(1)


def shadow_root() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"logs/shadow/hot/{today}"


def main() -> None:
    root = shadow_root()
    if not os.path.isdir(root):
        print(f"shadow root not found: {root}")
        sys.exit(1)

    timeline = os.path.join(root, "market_timeline.jsonl")
    gates    = os.path.join(root, "gate_trace.jsonl")
    resol    = os.path.join(root, "window_resolution.jsonl")

    con = duckdb.connect()

    if os.path.exists(timeline):
        con.execute(f"CREATE VIEW timeline AS SELECT * FROM read_json_auto('{timeline}')")
    if os.path.exists(gates):
        con.execute(f"CREATE VIEW gates AS SELECT * FROM read_json_auto('{gates}')")
    if os.path.exists(resol):
        con.execute(f"CREATE VIEW resol AS SELECT * FROM read_json_auto('{resol}')")

    print(f"\n=== shadow root: {root} ===\n")

    # ── Q1: coverage ───────────────────────────────────────────────────────
    print("Q1 — Coverage by asset/hour")
    if os.path.exists(timeline):
        print(con.execute("""
            SELECT asset, hour_utc,
                   COUNT(*)                      AS rows,
                   COUNT(DISTINCT token_id)      AS tokens,
                   COUNT(DISTINCT window_end_ts) AS windows
            FROM timeline
            GROUP BY asset, hour_utc
            ORDER BY asset, hour_utc
        """).fetchdf())
    else:
        print("(no timeline data yet)")

    # ── Q2: virtual-entry hit-rate at the live ask range ───────────────────
    # For every (token, second) where ask in [0.78, 0.92] AND remaining in [5,90]:
    # join to window_resolution, compute "would have won" (resolved_yes for the
    # observed outcome_dir/side). This is the simplest virtual-entry analysis.
    print("\nQ2 — Virtual-entry hit-rate at live ask band, by asset × session")
    if os.path.exists(timeline) and os.path.exists(resol):
        print(con.execute("""
            WITH ve AS (
                SELECT t.asset, t.outcome_dir, t.session_bucket,
                       t.token_id, t.window_end_ts, t.best_ask
                FROM timeline t
                WHERE t.best_ask BETWEEN 0.78 AND 0.92
                  AND t.seconds_to_resolution BETWEEN 5 AND 90
            )
            SELECT ve.asset, ve.session_bucket,
                   COUNT(*) AS n_virtual_entries,
                   ROUND(AVG(CASE WHEN r.resolved_yes THEN 1 ELSE 0 END), 3) AS hit_rate,
                   ROUND(AVG(ve.best_ask), 3) AS avg_ask
            FROM ve
            JOIN resol r
              ON r.condition_id IS NOT NULL
             AND ve.window_end_ts = r.window_end_ts
             AND ve.asset = r.asset
            GROUP BY ve.asset, ve.session_bucket
            HAVING COUNT(*) >= 50
            ORDER BY ve.asset, ve.session_bucket
        """).fetchdf())
    else:
        print("(need both timeline and resolution data)")

    # ── Q3: gate-passive cross-check ──────────────────────────────────────
    print("\nQ3 — Passive-gate would-take rate vs gate-fail counts")
    if os.path.exists(gates):
        print(con.execute("""
            SELECT asset, outcome_dir,
                   COUNT(*) AS n,
                   SUM(CASE WHEN all_pass THEN 1 ELSE 0 END)  AS pass_n,
                   ROUND(AVG(CASE WHEN all_pass THEN 1 ELSE 0 END), 3) AS pass_rate,
                   first_failed_gate
            FROM gates
            WHERE all_pass = false
            GROUP BY asset, outcome_dir, first_failed_gate
            ORDER BY asset, outcome_dir, n DESC
        """).fetchdf())
    else:
        print("(no gate_trace data yet)")

    print("\nDone.")


if __name__ == "__main__":
    main()
