"""
Falsification Test 1 — METAR-Lockout resolution-alignment backfill.

For each first-lockout event observed in
  logs/shadow/hot/2026-05-{23,24,25}/metar_lockout.jsonl
produce one structured record at
  analysis/weather/falsification_t1_backfill.jsonl

The single question this answers:
  "When the shadow detected a lockout (METAR running_max > bucket high),
   did the market actually resolve consistent with that lockout (NO wins)?"

Required per-event fields (per user specification):
  - condition_id, market_id, token_id (YES), no_token_id
  - station_id (icao)
  - resolution_rule_source (Polymarket question text + gamma description if available)
  - observed_max_value, observed_max_source ("metar_running_max"), observed_max_obs_ts
  - bucket_lo_c, bucket_hi_c
  - shadow_predicted_resolution (always "NO" — running_max > hi_c means YES bucket cannot hold)
  - gamma_resolved (bool), gamma_outcome_yes (bool), gamma_outcome_no (bool), gamma_outcome_raw
  - classification_correct (bool|None)
  - confidence (high|medium|low)  # based on lockout depth above ceiling
  - lockout_depth_c
  - yes_bid at first_lockout (= edge = no_ask premium)
  - lag from first_lockout to yes_bid <= 0.05 (CLOB repricing time)
  - never_converged_in_window
  - tradable_proxy_max_no_depth_usd (schema_v2 records only)
  - tradable_proxy_fillable_at_min_edge

NOTE on convergence direction:
  Lockout direction = NO wins. MM "convergence" therefore means
  yes_bid DROPS to ~0 (equivalently no_ask rises to ~1). We measure
  lag-to-yes_bid<=0.05 as the canonical convergence metric.

This script makes outbound HTTP calls to Polymarket gamma.
No live trades are executed. Read-only.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from pathlib import Path

SHADOW_GLOB = "/root/Klaus/logs/shadow/hot/2026-05-2[345]/metar_lockout.jsonl"
OUT_PATH = Path("/root/Klaus/analysis/weather/falsification_t1_backfill.jsonl")
CLOB = "https://clob.polymarket.com"
REQUEST_DELAY_S = 0.20  # be polite
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 klaus-research", "Accept": "application/json"}

# Confidence threshold on lockout depth (run_max - hi_c)
HIGH_CONF_DEPTH_C = 1.5
MED_CONF_DEPTH_C = 0.5

# Edge thresholds for measuring fillability
MIN_EDGE_FOR_FILL_PROXY = 0.05  # only count fillable depth where no_ask <= 1 - 0.05


def fetch_market_by_condition(condition_id: str) -> dict | None:
    """Fetch single market from CLOB by condition_id. Returns dict or {'_error': str}.

    gamma /markets filter params are silently ignored. CLOB /markets/{cond}
    returns the canonical record including {tokens: [{outcome, price, winner}]}.
    """
    url = f"{CLOB}/markets/{condition_id}"
    try:
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def parse_outcome_prices(raw) -> list | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None


def parse_outcomes(raw) -> list | None:
    return parse_outcome_prices(raw)


def clob_resolution(mkt: dict | None) -> dict:
    """Extract resolution status from a CLOB market record.

    CLOB returns tokens: [{token_id, outcome, price, winner}, ...].
    For resolved binary markets, winners have price=1, losers price=0.
    """
    if not mkt or mkt.get("_error"):
        return {
            "resolved": None,
            "outcome_yes": None,
            "outcome_no": None,
            "yes_token_price": None,
            "no_token_price": None,
            "tokens": None,
            "closed": None,
            "active": None,
            "end_date_iso": None,
            "resolution_source_text": None,
            "error": mkt.get("_error") if mkt else "no_market",
        }
    closed = bool(mkt.get("closed"))
    tokens = mkt.get("tokens") or []
    yes_tok = next((t for t in tokens if str(t.get("outcome", "")).lower().startswith("y")), None)
    no_tok = next((t for t in tokens if str(t.get("outcome", "")).lower().startswith("n")), None)
    outcome_yes = outcome_no = None
    yes_p = no_p = None
    if yes_tok is not None and no_tok is not None:
        try:
            yes_p = float(yes_tok.get("price"))
            no_p = float(no_tok.get("price"))
            if closed and (yes_p in (0.0, 1.0) or no_p in (0.0, 1.0)) and abs((yes_p + no_p) - 1.0) < 1e-6:
                outcome_yes = yes_p >= 0.5
                outcome_no = not outcome_yes
        except (TypeError, ValueError):
            pass
    return {
        "resolved": outcome_yes is not None,
        "outcome_yes": outcome_yes,
        "outcome_no": outcome_no,
        "yes_token_price": yes_p,
        "no_token_price": no_p,
        "tokens": tokens,
        "closed": closed,
        "active": mkt.get("active"),
        "end_date_iso": mkt.get("end_date_iso"),
        "resolution_source_text": (mkt.get("description") or "")[:500],
        "error": None,
    }


def measure_clob_repricing_lag(records: list[dict], first_t: int) -> dict:
    """Measure how fast yes_bid dropped from first_lockout value toward 0."""
    rs = sorted(records, key=lambda x: x["ts_s"])
    lag_to_0p05 = None
    lag_to_0p02 = None
    min_bid_seen = None
    max_bid_seen = None
    final_bid = None
    for r in rs:
        if r["ts_s"] < first_t:
            continue
        b = r.get("yes_bid")
        if b is None:
            continue
        b = float(b)
        if min_bid_seen is None or b < min_bid_seen:
            min_bid_seen = b
        if max_bid_seen is None or b > max_bid_seen:
            max_bid_seen = b
        final_bid = b
        if lag_to_0p05 is None and b <= 0.05:
            lag_to_0p05 = r["ts_s"] - first_t
        if lag_to_0p02 is None and b <= 0.02:
            lag_to_0p02 = r["ts_s"] - first_t
    return {
        "lag_to_yes_bid_0p05_s": lag_to_0p05,
        "lag_to_yes_bid_0p02_s": lag_to_0p02,
        "never_converged_at_0p05": (lag_to_0p05 is None),
        "min_yes_bid_seen": min_bid_seen,
        "max_yes_bid_seen": max_bid_seen,
        "final_yes_bid": final_bid,
        "window_duration_s": rs[-1]["ts_s"] - first_t if rs else None,
    }


def measure_tradable_proxy(records: list[dict], first_t: int) -> dict:
    """Schema-v2 only: aggregate no_book asks visible within the first 5 min of lockout
    at prices implying edge >= MIN_EDGE_FOR_FILL_PROXY."""
    rs = sorted(records, key=lambda x: x["ts_s"])
    window_end = first_t + 300  # 5 min
    max_depth_usd = 0.0
    n_v2_samples = 0
    n_v2_samples_with_fillable = 0
    fillable_ask_prices_seen = []
    for r in rs:
        if r["ts_s"] < first_t or r["ts_s"] > window_end:
            continue
        if r.get("schema_version") != 2:
            continue
        n_v2_samples += 1
        no_book = r.get("no_book") or {}
        asks = no_book.get("asks") or []
        # Only count asks priced <= (1 - MIN_EDGE_FOR_FILL_PROXY)
        cap = 1.0 - MIN_EDGE_FOR_FILL_PROXY
        depth = 0.0
        for a in asks:
            p = a.get("price")
            usd = a.get("usd")
            if p is None or usd is None:
                continue
            if p <= cap:
                depth += float(usd)
                fillable_ask_prices_seen.append(float(p))
        if depth > 0:
            n_v2_samples_with_fillable += 1
        if depth > max_depth_usd:
            max_depth_usd = depth
    return {
        "tradable_proxy_n_v2_samples": n_v2_samples,
        "tradable_proxy_n_samples_with_fillable": n_v2_samples_with_fillable,
        "tradable_proxy_max_no_depth_usd": round(max_depth_usd, 2) if n_v2_samples > 0 else None,
        "tradable_proxy_min_no_ask_seen": min(fillable_ask_prices_seen) if fillable_ask_prices_seen else None,
        "tradable_proxy_window_s": 300,
    }


def classify_confidence(depth_c: float) -> str:
    if depth_c >= HIGH_CONF_DEPTH_C:
        return "high"
    if depth_c >= MED_CONF_DEPTH_C:
        return "medium"
    return "low"


def build_record(condition_id: str, shadow_records: list[dict], market: dict | None) -> dict | None:
    """Build per-event record. Returns None if no first-lockout in records."""
    rs = sorted(shadow_records, key=lambda x: x["ts_s"])
    first = next((r for r in rs if r.get("seconds_since_first_lockout", -1) == 0), None)
    if first is None:
        return None
    run_max = first.get("running_max_c")
    hi_c = first.get("bucket_hi_c_padded")
    if run_max is None or hi_c is None:
        return None
    depth_c = round(float(run_max) - float(hi_c), 2)
    lag = measure_clob_repricing_lag(rs, first["ts_s"])
    trade = measure_tradable_proxy(rs, first["ts_s"])
    resol = clob_resolution(market)

    # Shadow always predicts NO wins on a hi_c lockout (the YES bucket
    # cannot resolve YES if running_max already exceeds its upper bound).
    shadow_predicted_no = True
    classification_correct = None
    if resol["resolved"]:
        classification_correct = bool(resol["outcome_no"]) == shadow_predicted_no

    edge_at_first = first.get("yes_bid")

    return {
        # identity
        "condition_id": condition_id,
        "yes_token_id": first.get("token_id"),
        "no_token_id": first.get("no_token_id"),
        "city": first.get("city"),
        "station_id_icao": first.get("icao"),
        "end_date": first.get("end_date"),

        # resolution rule
        "market_question": first.get("question"),
        "clob_end_date_iso": resol["end_date_iso"],
        "resolution_source_text": resol["resolution_source_text"],

        # observed physical state at first-lockout
        "observed_max_c": run_max,
        "observed_max_source": "metar_running_max",
        "observed_max_obs_ts": first.get("last_obs_ts"),
        "bucket_lo_c": first.get("bucket_lo_c_padded"),
        "bucket_hi_c": hi_c,
        "is_celsius_market": first.get("is_celsius_market"),
        "lockout_depth_c": depth_c,
        "confidence": classify_confidence(depth_c),

        # first-lockout timing & quote
        "first_lockout_ts_s": first["ts_s"],
        "first_lockout_ts_utc": first.get("ts_utc"),
        "edge_at_first_yes_bid": edge_at_first,    # = no_ask_implied premium = (1 - no_ask)
        "first_yes_ask": first.get("yes_ask"),
        "first_no_ask_implied": first.get("no_ask_implied"),
        "first_no_ask_clob": first.get("no_ask_clob"),
        "first_fill_path": first.get("fill_path"),

        # shadow prediction & ground-truth
        "shadow_predicted_no": shadow_predicted_no,
        "clob_resolved": resol["resolved"],
        "clob_outcome_yes": resol["outcome_yes"],
        "clob_outcome_no": resol["outcome_no"],
        "clob_yes_token_price": resol["yes_token_price"],
        "clob_no_token_price": resol["no_token_price"],
        "clob_closed": resol["closed"],
        "clob_active": resol["active"],
        "clob_fetch_error": resol["error"],
        "classification_correct": classification_correct,

        # CLOB repricing lag (yes_bid → 0)
        **lag,

        # Tradable-proxy depth (schema_v2)
        **trade,

        # bookkeeping
        "n_shadow_samples": len(rs),
    }


def main():
    import glob
    files = sorted(glob.glob(SHADOW_GLOB))
    by_market: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        with open(f) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                cond = r.get("condition_id")
                if not cond:
                    continue
                by_market[cond].append(r)

    candidates = []
    for cond, rs in by_market.items():
        if any(r.get("seconds_since_first_lockout", -1) == 0 for r in rs):
            candidates.append(cond)
    print(f"shadow files: {len(files)}")
    print(f"unique markets with first-lockout: {len(candidates)}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    n_resolved = 0
    n_correct = 0
    n_incorrect = 0
    n_open = 0
    n_fetch_error = 0

    with open(OUT_PATH, "w") as out:
        for i, cond in enumerate(candidates, 1):
            time.sleep(REQUEST_DELAY_S)
            market = fetch_market_by_condition(cond)
            rec = build_record(cond, by_market[cond], market)
            if rec is None:
                continue
            if rec["clob_fetch_error"]:
                n_fetch_error += 1
            elif rec["clob_resolved"]:
                n_resolved += 1
                if rec["classification_correct"]:
                    n_correct += 1
                else:
                    n_incorrect += 1
            else:
                n_open += 1
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if i % 25 == 0 or i == len(candidates):
                print(f"  [{i}/{len(candidates)}] resolved={n_resolved} correct={n_correct} "
                      f"incorrect={n_incorrect} open={n_open} fetch_err={n_fetch_error}")

    print()
    print(f"=== SUMMARY ({n_resolved + n_open + n_fetch_error} events written) ===")
    print(f"  resolved at gamma:      {n_resolved}")
    print(f"    classification correct: {n_correct}")
    print(f"    classification wrong:   {n_incorrect}")
    if n_resolved:
        print(f"    alignment %: {n_correct / n_resolved:.1%}")
    print(f"  still open:             {n_open}")
    print(f"  fetch errors:           {n_fetch_error}")
    print(f"\nOutput: {OUT_PATH}")


if __name__ == "__main__":
    main()
