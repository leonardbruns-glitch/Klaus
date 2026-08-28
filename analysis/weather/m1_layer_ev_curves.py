"""
M1 per-layer empirical EV curves from existing shadow data.

For every (market, time-bucket) sample in the schema-v2 shadow records,
compute hypothetical counterfactual fills and per-layer expectancy.

We DO NOT have real fills. We have order-book snapshots. The "fill"
proxy is: displayed NO depth at a price implying edge >= threshold.
This is OPTIMISTIC — it assumes the displayed depth doesn't vanish
when an order arrives. Real fill rate will be lower. The LCB on net EV
must therefore clear zero by a margin before we enable any layer live.

Outputs:
  - per-layer aggregate EV curves at baseline gates
  - per-layer × edge-band decomposition
  - per-layer × depth-threshold decomposition
  - slippage / depth-decay between top-of-book and deeper levels

Decision rule (per user spec): enable layer L only if
  Wilson95-LCB(net_EV_per_$1) > 0  AND  n_samples >= 30
"""
from __future__ import annotations
import json
import glob
import math
from collections import defaultdict
from pathlib import Path

SHADOW_GLOB = "/root/Klaus/logs/shadow/hot/2026-05-2[345]/metar_lockout.jsonl"
BACKFILL = Path("/root/Klaus/analysis/weather/falsification_t1_backfill.jsonl")

# Time layers (seconds since first_lockout)
LAYERS = [
    ("L0_0-60s",     0,      60),
    ("L1_1-5m",      60,     300),
    ("L2_5-30m",     300,    1800),
    ("L3_30-60m",    1800,   3600),
    ("L4_60m+",      3600,   10**9),
]

# Edge bands (yes_bid at the snapshot moment)
EDGE_BANDS = [(0.02, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.50), (0.50, 1.00)]

# Depth thresholds — cumulative no_book USD at prices implying edge >= band_lo
DEPTH_THRESHOLDS = [1, 3, 5, 20]

# Fee assumption (Polymarket varies; conservative single-side total)
FEE_RATE = 0.02


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    halfw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - halfw), min(1.0, centre + halfw))


def ev_normal_lcb(mean: float, std: float, n: int, z: float = 1.96) -> float:
    """One-sided 95% lower bound on mean using normal approx (n >= 30)."""
    if n == 0:
        return float("-inf")
    se = std / math.sqrt(n)
    return mean - z * se


# Load resolution outcomes
resolutions = {}
with open(BACKFILL) as f:
    for line in f:
        r = json.loads(line)
        if not r["clob_resolved"]:
            continue
        resolutions[r["condition_id"]] = {
            "classification_correct": r["classification_correct"],
            "outcome_no": r["clob_outcome_no"],
            "lockout_depth_c": r["lockout_depth_c"],
        }

# Load shadow records grouped by market
by_market: dict[str, list[dict]] = defaultdict(list)
for f in sorted(glob.glob(SHADOW_GLOB)):
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            cond = rec.get("condition_id")
            if not cond:
                continue
            by_market[cond].append(rec)


def layer_for(t_offset: int) -> str | None:
    for name, lo, hi in LAYERS:
        if lo <= t_offset < hi:
            return name
    return None


# Aggregate cells: (layer, edge_band, depth_threshold)
Cell = lambda: {
    "n_signals": 0,
    "n_with_resolution": 0,
    "n_correct": 0,
    "gross_pnls": [],
    "entry_prices": [],
    "cumulative_depths": [],
    "depth_decay_top_to_avg": [],  # measure of slippage if we walk the book
    "unique_markets": set(),
}

cells: dict[tuple, dict] = defaultdict(Cell)


for cond, records in by_market.items():
    records.sort(key=lambda r: r["ts_s"])
    first = next((r for r in records if r.get("seconds_since_first_lockout", -1) == 0), None)
    if first is None:
        continue
    first_t = first["ts_s"]
    resolution = resolutions.get(cond)

    for rec in records:
        if rec.get("schema_version") != 2:
            continue
        if rec["ts_s"] < first_t:
            continue
        t_offset = rec["ts_s"] - first_t
        layer = layer_for(t_offset)
        if layer is None:
            continue

        yes_bid = rec.get("yes_bid")
        if yes_bid is None:
            continue

        no_book = rec.get("no_book") or {}
        no_asks = no_book.get("asks") or []
        if not no_asks:
            continue
        top_ask_price = no_asks[0].get("price")
        if top_ask_price is None or top_ask_price >= 1.0:
            continue

        # Walk the book for slippage: weighted-avg price if you took everything
        total_usd = sum(a.get("usd", 0.0) for a in no_asks)
        total_shares = sum((a.get("usd", 0.0) / a.get("price", 1.0)) for a in no_asks if a.get("price"))
        weighted_avg = (total_usd / total_shares) if total_shares > 0 else top_ask_price
        slippage_to_book_avg = weighted_avg - top_ask_price

        for edge_lo, edge_hi in EDGE_BANDS:
            if not (edge_lo <= yes_bid < edge_hi):
                continue

            # Required: no_ask <= 1 - edge_lo (so the buy preserves at least edge_lo of gross)
            cap_price = 1.0 - edge_lo
            cum_depth = sum(
                a.get("usd", 0.0) for a in no_asks
                if a.get("price", 1.0) <= cap_price + 1e-9
            )

            for depth_thresh in DEPTH_THRESHOLDS:
                if cum_depth < depth_thresh:
                    continue

                key = (layer, f"edge_{edge_lo:.2f}", f"depth_${depth_thresh}")
                cells[key]["n_signals"] += 1
                cells[key]["entry_prices"].append(top_ask_price)
                cells[key]["cumulative_depths"].append(cum_depth)
                cells[key]["depth_decay_top_to_avg"].append(slippage_to_book_avg)
                cells[key]["unique_markets"].add(cond)

                if resolution is not None:
                    cells[key]["n_with_resolution"] += 1
                    if resolution["classification_correct"]:
                        cells[key]["n_correct"] += 1
                        gross = 1.0 - top_ask_price
                    else:
                        gross = -top_ask_price
                    cells[key]["gross_pnls"].append(gross)


def cell_summary(c: dict) -> dict:
    n = c["n_signals"]
    n_res = c["n_with_resolution"]
    n_corr = c["n_correct"]
    correct_pct = (n_corr / n_res) if n_res else None
    correct_lcb, _ = wilson_ci(n_corr, n_res) if n_res else (None, None)
    gross = c["gross_pnls"]
    if gross:
        mean_gross = sum(gross) / len(gross)
        var = sum((x - mean_gross) ** 2 for x in gross) / max(len(gross) - 1, 1)
        std = math.sqrt(var)
        ev_lcb = ev_normal_lcb(mean_gross, std, len(gross))
        net_mean = mean_gross - FEE_RATE
        net_lcb = ev_lcb - FEE_RATE
    else:
        mean_gross = std = ev_lcb = net_mean = net_lcb = None
    mean_entry = sum(c["entry_prices"]) / n if n else None
    mean_depth = sum(c["cumulative_depths"]) / n if n else None
    mean_slip = sum(c["depth_decay_top_to_avg"]) / n if n else None
    return {
        "n_signals": n,
        "n_unique_markets": len(c["unique_markets"]),
        "n_with_resolution": n_res,
        "n_correct": n_corr,
        "correct_pct": correct_pct,
        "correct_lcb95": correct_lcb,
        "mean_entry_price": mean_entry,
        "mean_cum_depth_usd": mean_depth,
        "mean_book_slippage": mean_slip,
        "mean_gross_per_$1": mean_gross,
        "std_gross_per_$1": std,
        "gross_ev_lcb95": ev_lcb,
        "mean_net_per_$1": net_mean,
        "net_ev_lcb95": net_lcb,
    }


# === REPORTS ===
print("=" * 100)
print("M1 PER-LAYER EMPIRICAL EV CURVES  (shadow-derived, optimistic-fill, fee=2% single-side)")
print("=" * 100)

# Report 1: Layer aggregates at baseline gates (edge>=0.10, depth>=$5)
print("\n--- REPORT 1: PER-LAYER AGGREGATE @ baseline gates (edge>=0.10, cum_depth>=$5) ---")
print(f"{'Layer':<14} {'n_sig':>6} {'n_mkt':>6} {'n_res':>6} {'correct%':>10} {'corr_LCB':>9} "
      f"{'entry_$':>8} {'depth_$':>8} {'slip_$':>8} {'gross':>9} {'gross_LCB':>10} {'net':>9} {'net_LCB':>10}")
print("-" * 145)

# Aggregate by layer at baseline gates: edge bands [0.10, ...] AND depth>=$5
for layer_name, _, _ in LAYERS:
    aggregated = Cell()
    for key, c in cells.items():
        l, eb, db = key
        if l != layer_name:
            continue
        # baseline: edge >= 0.10 AND depth threshold == 5 (the gate used in falsification)
        if not eb.startswith(("edge_0.10", "edge_0.20", "edge_0.50")):
            continue
        if db != "depth_$5":
            continue
        aggregated["n_signals"] += c["n_signals"]
        aggregated["n_with_resolution"] += c["n_with_resolution"]
        aggregated["n_correct"] += c["n_correct"]
        aggregated["gross_pnls"].extend(c["gross_pnls"])
        aggregated["entry_prices"].extend(c["entry_prices"])
        aggregated["cumulative_depths"].extend(c["cumulative_depths"])
        aggregated["depth_decay_top_to_avg"].extend(c["depth_decay_top_to_avg"])
        aggregated["unique_markets"] |= c["unique_markets"]
    s = cell_summary(aggregated)
    if s["n_signals"] == 0:
        print(f"{layer_name:<14} {0:>6}  (no samples)")
        continue
    print(f"{layer_name:<14} {s['n_signals']:>6} {s['n_unique_markets']:>6} {s['n_with_resolution']:>6} "
          f"{(s['correct_pct'] or 0):>9.1%} {(s['correct_lcb95'] or 0):>9.1%} "
          f"{(s['mean_entry_price'] or 0):>8.3f} {(s['mean_cum_depth_usd'] or 0):>8.1f} "
          f"{(s['mean_book_slippage'] or 0):>+8.4f} "
          f"{(s['mean_gross_per_$1'] or 0):>+9.4f} {(s['gross_ev_lcb95'] or 0):>+10.4f} "
          f"{(s['mean_net_per_$1'] or 0):>+9.4f} {(s['net_ev_lcb95'] or 0):>+10.4f}")


print("\n--- REPORT 2: PER-LAYER × EDGE-BAND  @ depth>=$5 ---")
print(f"{'Layer':<14} {'edge_band':<14} {'n_sig':>6} {'n_res':>6} {'correct%':>10} "
      f"{'entry_$':>8} {'gross':>9} {'gross_LCB':>10} {'net':>9} {'net_LCB':>10} {'verdict':>10}")
print("-" * 130)
for layer_name, _, _ in LAYERS:
    for edge_lo, edge_hi in EDGE_BANDS:
        eb = f"edge_{edge_lo:.2f}"
        agg = Cell()
        for key, c in cells.items():
            if key[0] != layer_name or key[1] != eb or key[2] != "depth_$5":
                continue
            agg["n_signals"] += c["n_signals"]
            agg["n_with_resolution"] += c["n_with_resolution"]
            agg["n_correct"] += c["n_correct"]
            agg["gross_pnls"].extend(c["gross_pnls"])
            agg["entry_prices"].extend(c["entry_prices"])
            agg["cumulative_depths"].extend(c["cumulative_depths"])
            agg["depth_decay_top_to_avg"].extend(c["depth_decay_top_to_avg"])
            agg["unique_markets"] |= c["unique_markets"]
        s = cell_summary(agg)
        if s["n_signals"] == 0:
            continue
        # Verdict: ENABLE / HOLD / REJECT
        n = s["n_with_resolution"] or 0
        nl = s["net_ev_lcb95"]
        if n >= 30 and nl is not None and nl > 0:
            verdict = "ENABLE"
        elif n >= 30 and nl is not None and nl <= 0:
            verdict = "REJECT"
        else:
            verdict = "HOLD-n<30"
        print(f"{layer_name:<14} {eb:<14} {s['n_signals']:>6} {n:>6} "
              f"{(s['correct_pct'] or 0):>9.1%} {(s['mean_entry_price'] or 0):>8.3f} "
              f"{(s['mean_gross_per_$1'] or 0):>+9.4f} {(s['gross_ev_lcb95'] or 0):>+10.4f} "
              f"{(s['mean_net_per_$1'] or 0):>+9.4f} {(s['net_ev_lcb95'] or 0):>+10.4f} "
              f"{verdict:>10}")

print("\n--- REPORT 3: PER-LAYER × DEPTH-THRESHOLD  @ edge>=0.10 (aggregated) ---")
print(f"{'Layer':<14} {'depth_thresh':<14} {'n_sig':>6} {'n_res':>6} {'correct%':>10} "
      f"{'gross':>9} {'net_LCB':>10} {'verdict':>10}")
print("-" * 110)
for layer_name, _, _ in LAYERS:
    for dt in DEPTH_THRESHOLDS:
        db = f"depth_${dt}"
        agg = Cell()
        for key, c in cells.items():
            if key[0] != layer_name or key[2] != db:
                continue
            if not key[1].startswith(("edge_0.10", "edge_0.20", "edge_0.50")):
                continue
            agg["n_signals"] += c["n_signals"]
            agg["n_with_resolution"] += c["n_with_resolution"]
            agg["n_correct"] += c["n_correct"]
            agg["gross_pnls"].extend(c["gross_pnls"])
            agg["entry_prices"].extend(c["entry_prices"])
            agg["unique_markets"] |= c["unique_markets"]
        s = cell_summary(agg)
        if s["n_signals"] == 0:
            continue
        n = s["n_with_resolution"] or 0
        nl = s["net_ev_lcb95"]
        if n >= 30 and nl is not None and nl > 0:
            verdict = "ENABLE"
        elif n >= 30 and nl is not None and nl <= 0:
            verdict = "REJECT"
        else:
            verdict = "HOLD-n<30"
        print(f"{layer_name:<14} {db:<14} {s['n_signals']:>6} {n:>6} "
              f"{(s['correct_pct'] or 0):>9.1%} {(s['mean_gross_per_$1'] or 0):>+9.4f} "
              f"{(s['net_ev_lcb95'] or 0):>+10.4f} {verdict:>10}")

print("\n--- REPORT 4: ADVERSE-SELECTION CHECK (correct% by layer) ---")
print("If correct% drops in late layers, that's evidence of informed counterparty arrival.")
print(f"{'Layer':<14} {'n_with_res':>10} {'correct%':>10} {'95% CI':>20}")
print("-" * 60)
for layer_name, _, _ in LAYERS:
    n_res = 0
    n_corr = 0
    for key, c in cells.items():
        if key[0] != layer_name:
            continue
        n_res += c["n_with_resolution"]
        n_corr += c["n_correct"]
    if n_res == 0:
        print(f"{layer_name:<14}  (no samples)")
        continue
    lo, hi = wilson_ci(n_corr, n_res)
    print(f"{layer_name:<14} {n_res:>10} {n_corr/n_res:>9.1%} [{lo:>5.1%}, {hi:>5.1%}]")


# Save the full cell table for the user
out_path = Path("/root/Klaus/analysis/weather/m1_layer_ev_cells.jsonl")
with open(out_path, "w") as f:
    for key, c in sorted(cells.items()):
        s = cell_summary(c)
        rec = {"layer": key[0], "edge_band": key[1], "depth_threshold": key[2], **s}
        f.write(json.dumps(rec) + "\n")
print(f"\nFull cell table: {out_path}")
