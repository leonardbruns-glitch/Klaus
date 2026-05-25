"""
M1 β-probe live result reporter — CONTAMINATION-AWARE.

Multi-fire schema: each bucket (condition_id) can fire up to 5 times across layers.
Fires on the same bucket are NOT statistically independent — they share one
resolution outcome. The analyzer must compute:

  • per-FIRE stats (independent observations of the execution layer):
      - fill rate
      - slippage distribution
      - time-to-fill

  • per-BUCKET-CLUSTER stats (one outcome per condition_id, regardless of fires):
      - win rate (Wilson LCB) ← THIS IS THE STATISTICALLY HONEST WR
      - mean net P&L per bucket
      - cumulative net P&L (aggregated across all fires of all buckets)

  • per-EVENT-CLUSTER stats (city+date, deeper correlation):
      - event-level win rate (informational; shows correlation depth)

Reads:
  - logs/shadow/hot/*/m1_beta_probe.jsonl  (multi-phase: submit + result)
  - logs/trades.jsonl                       (resolution outcomes via patcher)
"""
from __future__ import annotations
import json
import glob
import math
import statistics
from collections import defaultdict

PROBE_GLOB = "/root/Klaus/logs/shadow/hot/*/m1_beta_probe.jsonl"
TRADES_PATH = "/root/Klaus/logs/trades.jsonl"
FEE_RATE = 0.02


def wilson_lcb(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    halfw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - halfw)


def load_probe_events() -> list[dict]:
    """Returns list of fire events. Each event has its submit + result paired,
    keyed by (condition_id, ts_submitted) for uniqueness across multi-fire."""
    submits: dict[tuple, dict] = {}
    results: dict[tuple, dict] = {}
    for fp in sorted(glob.glob(PROBE_GLOB)):
        with open(fp) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("record_type") != "m1_beta_probe":
                    continue
                key = (r.get("condition_id"), r.get("ts_submitted"))
                if r.get("phase") == "submit":
                    submits[key] = r
                elif r.get("phase") == "result":
                    results[key] = r
    events = []
    for key, sub in sorted(submits.items(), key=lambda kv: kv[0][1] or 0):
        ev = dict(sub)
        ev["_result"] = results.get(key)
        events.append(ev)
    return events


def load_resolved_trades() -> list[dict]:
    """Returns list of M1_BETA_PROBE trade records (one per fill).
    Each has condition_id, token_id, entry_price, size, and (after patching)
    entered_correctly. Multi-fire produces multiple records with same token_id."""
    rows = []
    try:
        with open(TRADES_PATH) as f:
            for line in f:
                try:
                    t = json.loads(line)
                except Exception:
                    continue
                if t.get("bond_entry_class") != "M1_BETA_PROBE":
                    continue
                rows.append(t)
    except FileNotFoundError:
        pass
    return rows


def main() -> None:
    events = load_probe_events()
    trades = load_resolved_trades()

    # Resolution by condition_id (one resolution per bucket cluster)
    # entered_correctly is True iff the lockout direction was right (= NO won).
    bucket_resolution: dict[str, bool | None] = {}
    for t in trades:
        cid = t.get("condition_id")
        if not cid:
            continue
        ec = t.get("entered_correctly")
        if ec is None:
            continue
        # Same bucket may have multiple trades but same resolution
        bucket_resolution[cid] = bool(ec)

    n_submitted = len(events)
    print("=" * 76)
    print("M1 β-PROBE — CONTAMINATION-AWARE REPORT")
    print("=" * 76)
    print(f"\nfire events logged: {n_submitted}")
    print(f"resolved trades:    {len(trades)}")
    print(f"unique buckets:     {len({e.get('condition_id') for e in events if e.get('condition_id')})}")
    print(f"unique events:      {len({e.get('event_key') for e in events if e.get('event_key')})}")

    if n_submitted == 0:
        print("\n(no events yet — probe has not fired)")
        return

    fills = [e for e in events if e.get("_result") and e["_result"].get("filled")]
    n_filled = len(fills)
    fill_rate = n_filled / n_submitted if n_submitted else 0

    # ===================== PER-FIRE (independent) =====================
    print("\n" + "─" * 76)
    print("PER-FIRE STATS  (each fire is an independent execution observation)")
    print("─" * 76)

    print(f"\n[fill rate]")
    print(f"  submitted: {n_submitted}   filled: {n_filled}   rate: {fill_rate:.1%}")
    print(f"  Wilson95-LCB: {wilson_lcb(n_filled, n_submitted):.1%}")
    if n_submitted >= 20:
        verdict = "PASS" if fill_rate >= 0.25 else "HALT"
        print(f"  threshold (n>=20): fill_rate >= 25%   verdict: {verdict}")
    else:
        print(f"  (n<20 → verdict deferred)")

    print(f"\n[fill rate BY LAYER]")
    by_layer = defaultdict(lambda: {"sub": 0, "filled": 0})
    for e in events:
        L = e.get("layer", "?")
        by_layer[L]["sub"] += 1
        if e.get("_result") and e["_result"].get("filled"):
            by_layer[L]["filled"] += 1
    for L in sorted(by_layer):
        s = by_layer[L]
        rate = s["filled"] / s["sub"] if s["sub"] else 0
        print(f"  {L}: {s['filled']:>3}/{s['sub']:<3}  rate={rate:.1%}  LCB={wilson_lcb(s['filled'], s['sub']):.1%}")

    slips = [e["_result"]["slippage_vs_displayed_no_ask"] for e in fills
             if e["_result"].get("slippage_vs_displayed_no_ask") is not None]
    if slips:
        ss = sorted(slips)
        print(f"\n[slippage  fill_price − displayed_no_ask]")
        print(f"  n={len(ss)}  mean=${statistics.mean(ss):+.4f}  med=${statistics.median(ss):+.4f}")
        print(f"  p10=${ss[len(ss)//10]:+.4f}  p90=${ss[9*len(ss)//10]:+.4f}")

    ttfs = [e["_result"]["time_to_fill_ms"] for e in fills if e["_result"].get("time_to_fill_ms") is not None]
    if ttfs:
        ts = sorted(ttfs)
        print(f"\n[time-to-fill ms]")
        print(f"  n={len(ts)}  med={ts[len(ts)//2]}  p90={ts[9*len(ts)//10]}  max={ts[-1]}")

    # ===================== PER-BUCKET-CLUSTER (authoritative WR) =====================
    print("\n" + "─" * 76)
    print("PER-BUCKET-CLUSTER STATS  (1 outcome per condition_id — CORRECT WR)")
    print("─" * 76)

    # Filled fires grouped by bucket
    filled_by_bucket: dict[str, list[dict]] = defaultdict(list)
    for f in fills:
        cid = f.get("condition_id")
        if cid:
            filled_by_bucket[cid].append(f)

    # Buckets with both at-least-one-fill AND resolution
    resolved_buckets = [cid for cid in filled_by_bucket if cid in bucket_resolution]
    n_buckets_filled = len(filled_by_bucket)
    n_buckets_resolved = len(resolved_buckets)

    print(f"\nbuckets with >=1 filled fire:        {n_buckets_filled}")
    print(f"buckets with resolution + fill:      {n_buckets_resolved}")

    if n_buckets_resolved == 0:
        print("\n(no resolved buckets yet)")
    else:
        n_won = sum(1 for cid in resolved_buckets if bucket_resolution[cid])
        wr = n_won / n_buckets_resolved
        wr_lcb = wilson_lcb(n_won, n_buckets_resolved)
        print(f"\n[bucket-level win rate]   (1 trial per bucket, regardless of fires)")
        print(f"  buckets correct: {n_won}/{n_buckets_resolved}   WR: {wr:.1%}")
        print(f"  Wilson95-LCB on WR: {wr_lcb:.1%}")
        if n_buckets_resolved >= 20:
            verdict = "PASS" if wr >= 0.85 else "HALT"
            print(f"  threshold (n>=20): WR >= 85%   verdict: {verdict}")

        # Cumulative net P&L (sum across ALL fills; correct accounting since each fill is a real trade)
        total_net_pnl = 0.0
        per_bucket_net_pnl = []  # one P&L per bucket (sum of all its fills)
        per_fill_net_pnls = []
        for cid in resolved_buckets:
            won = bucket_resolution[cid]
            bucket_sum = 0.0
            for f in filled_by_bucket[cid]:
                ep = f["_result"]["fill_avg_price"]
                sz = f["_result"]["fill_size_shares"]
                if ep is None or sz is None:
                    continue
                # NO token: pays 1 if won, 0 if lost
                gross_per_unit = (1.0 - ep) if won else (-ep)
                net_per_unit = gross_per_unit - FEE_RATE
                fill_pnl = net_per_unit * sz
                bucket_sum += fill_pnl
                per_fill_net_pnls.append(fill_pnl)
            per_bucket_net_pnl.append(bucket_sum)
            total_net_pnl += bucket_sum

        print(f"\n[net P&L]")
        print(f"  cumulative (all fills, all buckets):  ${total_net_pnl:+.4f}")
        if per_bucket_net_pnl:
            print(f"  per-BUCKET mean P&L:                  ${statistics.mean(per_bucket_net_pnl):+.4f}")
            print(f"  per-BUCKET std P&L:                   ${(statistics.stdev(per_bucket_net_pnl) if len(per_bucket_net_pnl)>1 else 0):+.4f}")
        if per_fill_net_pnls:
            print(f"  per-FILL mean P&L (NOT for inference): ${statistics.mean(per_fill_net_pnls):+.4f}")

        if len(per_bucket_net_pnl) >= 30:
            mean_pnl = statistics.mean(per_bucket_net_pnl)
            verdict = "PASS" if mean_pnl > 0 else "HALT"
            print(f"  threshold (n>=30 buckets): mean per-bucket P&L > 0   verdict: {verdict}")

        # Fire-count per bucket distribution
        fire_counts = [len(filled_by_bucket[cid]) for cid in filled_by_bucket]
        if fire_counts:
            print(f"\n[fires per filled bucket — multi-fire intensity]")
            fc_counts = defaultdict(int)
            for fc in fire_counts:
                fc_counts[fc] += 1
            for fc in sorted(fc_counts):
                print(f"  {fc} fire(s): {fc_counts[fc]} buckets")

    # ===================== PER-EVENT-CLUSTER (deeper correlation) =====================
    print("\n" + "─" * 76)
    print("PER-EVENT-CLUSTER STATS  (city+date — buckets sharing daily-high obs)")
    print("─" * 76)

    # Group buckets by event_key; an event "wins" iff all its filled buckets won.
    # (More conservative: event has loss if ANY filled bucket lost — same daily-high reading.)
    by_event: dict[str, list[str]] = defaultdict(list)
    for f in fills:
        ek = f.get("event_key")
        cid = f.get("condition_id")
        if ek and cid and cid in bucket_resolution:
            if cid not in by_event[ek]:
                by_event[ek].append(cid)
    resolved_events = [ek for ek, cids in by_event.items() if cids]
    if resolved_events:
        n_events = len(resolved_events)
        # An event resolves correctly iff all its buckets resolved correctly
        # (same daily-high observation → all should agree if lockout was real)
        events_won = sum(
            1 for ek in resolved_events
            if all(bucket_resolution[cid] for cid in by_event[ek])
        )
        ev_wr = events_won / n_events
        ev_lcb = wilson_lcb(events_won, n_events)
        print(f"\n  resolved events:  {n_events}")
        print(f"  events all-bucket correct: {events_won}/{n_events}   WR: {ev_wr:.1%}   LCB: {ev_lcb:.1%}")
        # Concentration check
        buckets_per_event = sorted([len(by_event[ek]) for ek in resolved_events])
        med_bpe = buckets_per_event[len(buckets_per_event)//2]
        max_bpe = buckets_per_event[-1]
        print(f"  buckets/event:    med={med_bpe}  max={max_bpe}  (concentration risk if max>>1)")

    # ===================== TAIL: last 12 events =====================
    print("\n" + "─" * 76)
    print("LAST 12 FIRES")
    print("─" * 76)
    tail = events[-12:]
    for e in tail:
        ts = e.get("ts_submitted", 0)
        city = e.get("city", "?")
        L = e.get("layer", "?")
        seq = e.get("bucket_fire_seq", "?")
        sec = e.get("sec_since_first_lockout", "?")
        edge = e.get("yes_bid_at_signal", 0)
        no_ask = e.get("no_ask_clob_at_signal", 0)
        result = e.get("_result")
        cid = e.get("condition_id")
        outcome = ""
        if cid and cid in bucket_resolution:
            outcome = "  bucket→WIN" if bucket_resolution[cid] else "  bucket→LOSS"
        if result and result.get("filled"):
            fp = result.get("fill_avg_price")
            ttf = result.get("time_to_fill_ms")
            print(f"  {int(ts)}  {city:14s} {L} seq={seq} sec={sec:>5}  "
                  f"sub@{no_ask:.3f}→fill@{fp:.3f}  ttf={ttf}ms{outcome}")
        elif result:
            print(f"  {int(ts)}  {city:14s} {L} seq={seq} sec={sec:>5}  "
                  f"sub@{no_ask:.3f}  NO-FILL ({result.get('fill_status')})")
        else:
            print(f"  {int(ts)}  {city:14s} {L} seq={seq} sec={sec:>5}  "
                  f"sub@{no_ask:.3f}  PENDING")


if __name__ == "__main__":
    main()
