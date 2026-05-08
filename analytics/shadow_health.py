#!/usr/bin/env python3
"""Shadow engine health check — read-side only, no instrumentation cost.

Surfaces validation-gate status from the running substrate. Safe to run any
time during the 24h shakedown. No restart, no impact on live writers.

Run on VPS:
    python3 /root/Klaus/analytics/shadow_health.py
Or via SSH:
    ssh root@<vps> "python3 /root/Klaus/analytics/shadow_health.py"

Exits non-zero on validation-gate failure — suitable for cron/alerting.

Per shadow_engine_principles directive #18: alert loudly, not silently.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

# Hard thresholds (per directive #18). Loud-fail if exceeded.
QUEUE_PCT_FULL_FAIL    = 0.50
FLUSH_P95_FAIL_MS      = 50.0
RSS_GROWTH_FAIL_PCT    = 0.20    # over the trend window


def load_jsonl(path: str, last_n: int = None) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-last_n:] if last_n else rows


def stream_filter(path: str, predicate) -> list:
    """Stream-filter — large files. Yields matching rows."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if predicate(r):
                yield r


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=None,
                   help="shadow date dir (default: today UTC)")
    p.add_argument("--minutes", type=int, default=60,
                   help="trend window")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    if args.root is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        args.root = f"/root/Klaus/logs/shadow/hot/{date}"

    if not os.path.isdir(args.root):
        print(f"shadow root not found: {args.root}", file=sys.stderr)
        return 2

    now = time.time()
    cutoff = int(now - args.minutes * 60)

    telem = load_jsonl(os.path.join(args.root, "shadow_telemetry.jsonl"))
    if not telem:
        print("no telemetry yet — wait for first 60s emit", file=sys.stderr)
        return 0
    latest = telem[-1]
    recent = [r for r in telem if r["ts_s"] >= cutoff] or [latest]

    if not args.quiet:
        ts_iso = datetime.fromtimestamp(latest["ts_s"], timezone.utc).isoformat(timespec="seconds")
        print(f"=== Telemetry @ {ts_iso} ===")
        print(f"  uptime         : {latest['uptime_s']}s ({latest['uptime_s']/3600:.2f}h)")
        print(f"  written_total  : {latest['written_total']:,}")
        print(f"  dropped_total  : {latest['dropped_total']}")
        print(f"  queue          : {latest['queue_depth']:,} / {latest['queue_max']:,} ({latest['queue_pct_full']*100:.2f}%)")
        print(f"  rows/min       : {latest['rows_per_min']}")
        print(f"  flush p50/p95  : {latest['flush_latency_p50_ms']}ms / {latest['flush_latency_p95_ms']}ms")
        print(f"  rss_mb         : {latest['rss_mb']}")
        print(f"  files          : {', '.join(f'{k}={v[\"size_bytes\"]/1024/1024:.1f}MB' for k,v in latest['files'].items())}")

        if len(recent) >= 2:
            print(f"\n=== Trend (last {args.minutes}min, n={len(recent)} samples) ===")
            print(f"  queue_depth_max     : {max(r['queue_depth'] for r in recent)}")
            print(f"  dropped_delta       : +{recent[-1]['dropped_total'] - recent[0]['dropped_total']}")
            rss_d = recent[-1]["rss_mb"] - recent[0]["rss_mb"]
            print(f"  rss_mb_delta        : {rss_d:+.1f} ({rss_d / max(1, recent[0]['rss_mb']) * 100:+.1f}%)")
            print(f"  flush_p95_max_ms    : {max(r['flush_latency_p95_ms'] for r in recent)}")
            print(f"  rows/min min/max    : {min(r['rows_per_min'] for r in recent):.0f} / {max(r['rows_per_min'] for r in recent):.0f}")

        # Per-session rates (directive #17)
        tl_path = os.path.join(args.root, "market_timeline.jsonl")
        if os.path.exists(tl_path):
            bucket_counts: Counter = Counter()
            bucket_minutes: dict = defaultdict(set)
            asset_counts: Counter = Counter()
            for r in stream_filter(tl_path, lambda r: r.get("ts_s", 0) >= cutoff):
                sb = r.get("session_bucket", "unknown")
                bucket_counts[sb] += 1
                bucket_minutes[sb].add(r["ts_s"] // 60)
                asset_counts[r.get("asset", "?")] += 1
            print(f"\n=== market_timeline coverage (last {args.minutes}min) ===")
            print(f"  by session:")
            for sb in sorted(bucket_counts):
                n = bucket_counts[sb]
                mins = len(bucket_minutes[sb]) or 1
                print(f"    {sb:14s}  rows={n:>7,}  active_min={mins:>3}  rate={n/mins:>6.1f}/min")
            print(f"  by asset:    {dict(asset_counts)}")

        res_path = os.path.join(args.root, "window_resolution.jsonl")
        if os.path.exists(res_path):
            res = load_jsonl(res_path)
            res_recent = [r for r in res if r.get("ts_resolved_s", 0) >= cutoff]
            print(f"\n=== Resolutions ===")
            print(f"  total          : {len(res)}")
            print(f"  in window      : {len(res_recent)}")
            if res_recent:
                yes = sum(1 for r in res_recent if r.get("resolved_yes"))
                methods = Counter(r.get("resolution_source", "?") for r in res_recent)
                print(f"  resolved_yes   : {yes}/{len(res_recent)} ({yes/len(res_recent):.1%})")
                print(f"  source         : {dict(methods)}")

    # Validation-gate evaluation (loud-fail per directive #18)
    fails = []
    if latest["dropped_total"] > 0:
        fails.append(f"DROPS DETECTED — dropped_total={latest['dropped_total']} (gate #4 FAILED)")
    if latest["queue_pct_full"] > QUEUE_PCT_FULL_FAIL:
        fails.append(f"QUEUE >50% FULL — pct_full={latest['queue_pct_full']*100:.1f}%")
    if latest["flush_latency_p95_ms"] > FLUSH_P95_FAIL_MS:
        fails.append(f"FLUSH P95 ELEVATED — {latest['flush_latency_p95_ms']}ms > {FLUSH_P95_FAIL_MS}ms")
    if len(recent) >= 2:
        rss_growth = (recent[-1]["rss_mb"] - recent[0]["rss_mb"]) / max(1, recent[0]["rss_mb"])
        if rss_growth > RSS_GROWTH_FAIL_PCT:
            fails.append(f"RSS GROWING — +{rss_growth*100:.1f}% in {args.minutes}min")

    print(f"\n=== Validation gate ===")
    if fails:
        print("  STATUS: FAILED")
        for f in fails:
            print(f"    !! {f}")
        return 1
    print("  STATUS: HEALTHY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
