"""Wallet-class tagger — offline batch processor for Tier 1 tx_hash data.

Reads all token_trade.jsonl (v2) files, collects unique transaction hashes,
queries Polygon RPC for the `from` address of each transaction, then classifies
each wallet by activity pattern.

Wallet classes:
  whale   — >50 trades in our observation window (large, frequent, informed)
  bot     — >10 trades, inter-trade variance <5s (mechanical, HFT-like)
  retail  — <=5 trades (casual, noise)
  unknown — tx_hash lookup failed

Outputs:
  analytics/discover/wallet_classes.parquet
    columns: tx_hash, from_address, wallet_class, trade_count, assets, first_seen_ts, last_seen_ts

Join key: token_trade.jsonl rows by tx_hash → wallet classification for each Polymarket fill.

Usage:
  python3 analytics/discover/wallet_tagger.py [--rpc URL] [--days N]

Defaults:
  --rpc   https://polygon-rpc.com  (free public endpoint, no auth required)
  --days  7                         (scan last N days of shadow data)
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path("/root/Klaus")
SHADOW_DIR = ROOT / "logs" / "shadow" / "hot"
OUT_PATH = ROOT / "analytics" / "discover" / "wallet_classes.parquet"

DEFAULT_RPC = "https://polygon-rpc.com"
RPC_TIMEOUT = 6   # seconds per request
MAX_CONCURRENT_HASHES = 500  # cap to avoid rate-limiting free endpoints


def rpc_call(url: str, method: str, params: list) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=RPC_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


def get_tx_from_address(rpc_url: str, tx_hash: str) -> str:
    """Return the `from` address for a Polygon transaction, or '' on failure."""
    result = rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash])
    tx = result.get("result") or {}
    return (tx.get("from") or "").lower()


def classify_wallet(trade_count: int, inter_trade_seconds: list) -> str:
    if trade_count > 50:
        return "whale"
    if trade_count > 10 and inter_trade_seconds:
        import statistics
        try:
            stdev = statistics.stdev(inter_trade_seconds)
            if stdev < 5.0:
                return "bot"
        except statistics.StatisticsError:
            pass
    if trade_count <= 5:
        return "retail"
    return "active"


def collect_tx_hashes(days: int) -> dict:
    """Scan shadow token_trade.jsonl files for the last N days.
    Returns: {tx_hash: [{"ts_s": ..., "asset": ..., "token_id": ...}, ...]}
    """
    tx_map = defaultdict(list)
    cutoff_ts = time.time() - days * 86400

    for day_dir in sorted(SHADOW_DIR.iterdir()):
        if not day_dir.is_dir():
            continue
        tf = day_dir / "token_trade.jsonl"
        if not tf.exists():
            continue
        with open(tf) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("schema_version", 0) < 2:
                    continue
                tx_hash = row.get("transaction_hash", "")
                if not tx_hash:
                    continue
                ts = row.get("ts_s", 0)
                if ts < cutoff_ts:
                    continue
                tx_map[tx_hash].append({
                    "ts_s": ts,
                    "asset": row.get("asset", ""),
                    "token_id": row.get("token_id", ""),
                })

    return dict(tx_map)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    print(f"Scanning last {args.days} days of token_trade.jsonl ...")
    tx_map = collect_tx_hashes(args.days)
    print(f"  Unique tx_hashes: {len(tx_map):,}")

    if not tx_map:
        print("No v2 token_trade rows found. Deploy must have been < {args.days} days ago.")
        return

    # Cap to avoid hammering the free RPC endpoint
    hashes = list(tx_map.keys())[:MAX_CONCURRENT_HASHES]
    if len(hashes) < len(tx_map):
        print(f"  Capped to {MAX_CONCURRENT_HASHES} hashes (rate-limit guard)")

    print(f"Looking up {len(hashes)} tx_hashes on Polygon ({args.rpc}) ...")
    from_addr_map = {}
    errors = 0
    for i, tx_hash in enumerate(hashes):
        addr = get_tx_from_address(args.rpc, tx_hash)
        from_addr_map[tx_hash] = addr
        if not addr:
            errors += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(hashes)} done ({errors} errors so far)")
        time.sleep(0.05)  # ~20 req/s — polite for a free endpoint

    print(f"  Lookup complete: {len(hashes)-errors} resolved, {errors} failed")

    # Group trades by wallet address
    wallet_trades = defaultdict(list)
    wallet_tx_hashes = defaultdict(set)
    for tx_hash, trades in tx_map.items():
        addr = from_addr_map.get(tx_hash, "")
        key = addr if addr else f"unknown_{tx_hash[:8]}"
        wallet_trades[key].extend(trades)
        wallet_tx_hashes[key].add(tx_hash)

    # Build wallet-class records
    records = []
    for addr, trades in wallet_trades.items():
        trades_sorted = sorted(trades, key=lambda r: r["ts_s"])
        ts_list = [r["ts_s"] for r in trades_sorted]
        inter = [b - a for a, b in zip(ts_list, ts_list[1:])] if len(ts_list) > 1 else []
        assets = list({r["asset"] for r in trades})
        wc = classify_wallet(len(trades), inter)
        records.append({
            "from_address": addr,
            "wallet_class": wc,
            "trade_count": len(trades),
            "tx_count": len(wallet_tx_hashes[addr]),
            "assets": ",".join(sorted(assets)),
            "first_seen_ts": ts_list[0] if ts_list else 0,
            "last_seen_ts": ts_list[-1] if ts_list else 0,
        })

    # Emit tx_hash → wallet_class join table
    join_records = []
    for tx_hash, trades in tx_map.items():
        addr = from_addr_map.get(tx_hash, "")
        key = addr if addr else f"unknown_{tx_hash[:8]}"
        wc_row = next((r for r in records if r["from_address"] == key), None)
        join_records.append({
            "tx_hash": tx_hash,
            "from_address": addr,
            "wallet_class": wc_row["wallet_class"] if wc_row else "unknown",
            "wallet_trade_count": wc_row["trade_count"] if wc_row else 1,
        })

    try:
        import pandas as pd
        df = pd.DataFrame(join_records)
        df.to_parquet(OUT_PATH, index=False)
        print(f"\nWrote {len(df):,} rows to {OUT_PATH}")
        print(f"\nWallet class distribution:")
        print(df.groupby("wallet_class")["tx_hash"].count().sort_values(ascending=False).to_string())
    except ImportError:
        # Fallback: write as JSONL if pandas not available
        out_jsonl = OUT_PATH.with_suffix(".jsonl")
        with open(out_jsonl, "w") as f:
            for r in join_records:
                f.write(json.dumps(r) + "\n")
        print(f"Wrote {len(join_records):,} rows to {out_jsonl} (pandas not available)")


if __name__ == "__main__":
    main()
