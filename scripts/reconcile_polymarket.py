"""
reconcile_polymarket.py
-----------------------
Fetches real Polymarket trade history for FUNDER_ADDRESS and reconciles
against logs/trades.jsonl.

Usage:
    python3 scripts/reconcile_polymarket.py
    python3 scripts/reconcile_polymarket.py --since 2026-04-01
    python3 scripts/reconcile_polymarket.py --full          # all history

Output:
    - On-chain trades not in our logs  (MISSING from bot records)
    - Bot log entries with no on-chain match (ORPHAN or dry-run artefacts)
    - Matched trades with PnL discrepancy > $0.05
    - Summary WR and PnL from each source
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── dotenv ────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
CLOB_API     = "https://clob.polymarket.com"
GAMMA_API    = "https://gamma-api.polymarket.com"
DATA_API     = "https://data-api.polymarket.com"
TRADES_LOG   = Path(__file__).parent.parent / "logs" / "trades.jsonl"
RESULTS_FILE = Path(__file__).parent.parent / "logs" / "reconciliation.json"

WALLET = os.getenv("FUNDER_ADDRESS", "").strip()
if not WALLET:
    print("ERROR: FUNDER_ADDRESS not set in .env")
    sys.exit(1)

print(f"Wallet: {WALLET}")

# ─────────────────────────────────────────────────────────────────────────────
# Polymarket API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, retries: int = 3) -> Any:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def fetch_clob_trades(address: str, since_ts: int = 0) -> List[Dict]:
    """
    Fetch all fills for `address` from CLOB /trades endpoint.
    Polymarket CLOB returns fills where the address is maker OR taker.
    Paginates until exhausted.
    """
    all_trades = []
    for role in ("maker_address", "taker_address"):
        cursor = None
        page = 0
        while True:
            params: Dict[str, Any] = {role: address, "limit": 500}
            if cursor:
                params["next_cursor"] = cursor
            try:
                data = _get(f"{CLOB_API}/trades", params=params)
            except Exception as e:
                print(f"  WARN: CLOB /trades ({role}) failed: {e}")
                break

            if isinstance(data, dict):
                items = data.get("data", [])
                cursor = data.get("next_cursor") or data.get("cursor")
            elif isinstance(data, list):
                items = data
                cursor = None
            else:
                break

            if not items:
                break

            all_trades.extend(items)
            page += 1

            # filter by timestamp after collecting (API may not support since_ts)
            if not cursor:
                break
            # safety cap — 50 pages max
            if page >= 50:
                print(f"  WARN: hit page cap for {role}")
                break

    # deduplicate by trade_id
    seen = set()
    unique = []
    for t in all_trades:
        tid = t.get("id") or t.get("trade_id") or json.dumps(t, sort_keys=True)
        if tid not in seen:
            seen.add(tid)
            unique.append(t)

    # filter by timestamp
    if since_ts > 0:
        unique = [t for t in unique
                  if _parse_ts(t.get("created_at") or t.get("timestamp", "0")) >= since_ts]

    return unique


def fetch_data_api_activity(address: str, since_ts: int = 0) -> List[Dict]:
    """
    Fetch from data-api.polymarket.com/activity — richer trade history
    used by the Polymarket UI. Includes settled positions.
    """
    try:
        url = f"{DATA_API}/activity"
        params: Dict[str, Any] = {"user": address, "limit": 500}
        data = _get(url, params=params)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("history", data.get("data", []))
        else:
            items = []

        if since_ts > 0:
            items = [x for x in items
                     if _parse_ts(x.get("timestamp") or x.get("created_at", "0")) >= since_ts]
        return items
    except Exception as e:
        print(f"  WARN: data-api /activity failed: {e}")
        return []


def fetch_gamma_positions(address: str) -> List[Dict]:
    """
    Fetch resolved/open positions from gamma API.
    """
    try:
        url = f"{GAMMA_API}/positions"
        params = {"user": address, "limit": 500, "redeemable": "true"}
        data = _get(url, params=params)
        return data if isinstance(data, list) else data.get("positions", [])
    except Exception as e:
        print(f"  WARN: gamma /positions failed: {e}")
        return []


def _parse_ts(val: Any) -> float:
    """Parse timestamp string or int → unix seconds."""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 1000 if v > 1e12 else v
    s = str(val)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    try:
        return float(s) / (1000 if float(s) > 1e12 else 1)
    except (ValueError, TypeError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Load our internal logs
# ─────────────────────────────────────────────────────────────────────────────

def load_bot_trades(since_ts: int = 0) -> List[Dict]:
    if not TRADES_LOG.exists():
        print(f"ERROR: {TRADES_LOG} not found")
        return []
    trades = []
    with open(TRADES_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except json.JSONDecodeError:
                continue
            # skip orphans, stubs, dry-run artefacts
            if (t.get("signal_source") == "ORPHAN"
                    or t.get("exit_reason") == "ORPHAN_SELL"
                    or str(t.get("token_id", "")).startswith("stub_")):
                continue
            if not t.get("is_live", True):
                continue
            ts = t.get("ts_open", 0)
            if since_ts > 0 and ts < since_ts:
                continue
            trades.append(t)
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Reconciliation logic
# ─────────────────────────────────────────────────────────────────────────────

def normalise_clob_trade(t: Dict) -> Dict:
    """Flatten a CLOB fill record into a common format."""
    ts = _parse_ts(t.get("created_at") or t.get("timestamp"))
    size = float(t.get("size") or t.get("shares") or 0)
    price = float(t.get("price") or 0)
    token_id = t.get("asset_id") or t.get("token_id") or ""
    side = (t.get("side") or t.get("type") or "").upper()
    outcome = t.get("outcome") or ""
    market_id = t.get("market") or t.get("market_id") or ""
    notional = size * price
    return {
        "source": "clob",
        "id": t.get("id") or t.get("trade_id"),
        "ts": ts,
        "token_id": token_id,
        "market_id": market_id,
        "side": side,          # BUY or SELL
        "outcome": outcome,    # YES or NO
        "price": price,
        "size": size,
        "notional": notional,
        "raw": t,
    }


def normalise_activity(t: Dict) -> Dict:
    """Flatten a data-api activity record."""
    ts = _parse_ts(t.get("timestamp") or t.get("created_at"))
    size = float(t.get("size") or t.get("shares") or 0)
    price = float(t.get("price") or t.get("avg_price") or 0)
    side = (t.get("side") or t.get("type") or "").upper()
    token_id = t.get("asset_id") or t.get("token_id") or ""
    notional = size * price
    return {
        "source": "activity",
        "id": t.get("id") or t.get("transaction_hash"),
        "ts": ts,
        "token_id": token_id,
        "side": side,
        "price": price,
        "size": size,
        "notional": notional,
        "market_slug": t.get("market_slug") or t.get("slug") or "",
        "outcome": t.get("outcome") or "",
        "raw": t,
    }


def group_fills_into_trades(fills: List[Dict]) -> List[Dict]:
    """
    Group raw BUY/SELL fills by token_id into buy→sell pairs.
    A 'trade' = one BUY fill + matching SELL fills for the same token.
    Returns list of reconstructed trades with entry/exit prices.
    """
    from collections import defaultdict
    by_token: Dict[str, List[Dict]] = defaultdict(list)
    for f in fills:
        by_token[f["token_id"]].append(f)

    result = []
    for token_id, token_fills in by_token.items():
        token_fills.sort(key=lambda x: x["ts"])
        buys  = [f for f in token_fills if "BUY"  in f["side"] or f["side"] in ("BUY", "MATCH")]
        sells = [f for f in token_fills if "SELL" in f["side"]]

        if not buys:
            continue

        # simple FIFO pairing
        buy_notional  = sum(f["notional"] for f in buys)
        buy_shares    = sum(f["size"]     for f in buys)
        sell_notional = sum(f["notional"] for f in sells)
        sell_shares   = sum(f["size"]     for f in sells)

        entry_price = buy_notional  / buy_shares  if buy_shares  else 0
        exit_price  = sell_notional / sell_shares if sell_shares else 0

        ts_open  = buys[0]["ts"]
        ts_close = sells[-1]["ts"] if sells else 0

        cost   = buy_notional
        revenue = sell_notional
        net_pnl = revenue - cost  # ignores fees (we don't have fee data here)

        result.append({
            "token_id":    token_id,
            "ts_open":     ts_open,
            "ts_close":    ts_close,
            "entry_price": round(entry_price, 4),
            "exit_price":  round(exit_price, 4),
            "shares":      round(buy_shares, 2),
            "stake":       round(cost, 3),
            "net_pnl":     round(net_pnl, 4),
            "buy_fills":   len(buys),
            "sell_fills":  len(sells),
            "open":        sell_shares < buy_shares * 0.9,
            "market_slug": buys[0].get("market_slug", ""),
            "outcome":     buys[0].get("outcome", ""),
            "source_fills": token_fills,
        })

    result.sort(key=lambda x: x["ts_open"])
    return result


def match_to_bot_log(onchain: List[Dict], bot: List[Dict]) -> Dict:
    """
    Match on-chain reconstructed trades to bot log entries.
    Matching strategy:
      1. Exact token_id match
      2. token_id not available: entry_price ±0.02 + ts_open ±300s
    """
    bot_by_token = {t["token_id"]: t for t in bot}
    matched    = []
    missing    = []  # on-chain but not in bot log
    unmatched_bot = list(bot)

    for oc in onchain:
        bot_match = bot_by_token.get(oc["token_id"])
        if bot_match:
            unmatched_bot = [x for x in unmatched_bot if x is not bot_match]
            pnl_diff = abs((bot_match.get("net_pnl") or 0) - oc["net_pnl"])
            matched.append({
                "token_id":   oc["token_id"],
                "ts_open":    oc["ts_open"],
                "entry_price_onchain": oc["entry_price"],
                "entry_price_bot":     bot_match.get("entry_price"),
                "exit_price_onchain":  oc["exit_price"],
                "exit_price_bot":      bot_match.get("exit_price"),
                "pnl_onchain": oc["net_pnl"],
                "pnl_bot":     bot_match.get("net_pnl"),
                "pnl_diff":    round(pnl_diff, 4),
                "pnl_ok":      pnl_diff <= 0.10,
                "open":        oc["open"],
            })
        else:
            # try fuzzy match on timestamp + entry_price
            best = None
            for bt in unmatched_bot:
                if abs(bt.get("ts_open", 0) - oc["ts_open"]) < 300:
                    if abs(bt.get("entry_price", 0) - oc["entry_price"]) < 0.03:
                        best = bt
                        break
            if best:
                unmatched_bot = [x for x in unmatched_bot if x is not best]
                pnl_diff = abs((best.get("net_pnl") or 0) - oc["net_pnl"])
                matched.append({
                    "token_id":   oc["token_id"],
                    "ts_open":    oc["ts_open"],
                    "entry_price_onchain": oc["entry_price"],
                    "entry_price_bot":     best.get("entry_price"),
                    "exit_price_onchain":  oc["exit_price"],
                    "exit_price_bot":      best.get("exit_price"),
                    "pnl_onchain": oc["net_pnl"],
                    "pnl_bot":     best.get("net_pnl"),
                    "pnl_diff":    round(pnl_diff, 4),
                    "pnl_ok":      pnl_diff <= 0.10,
                    "fuzzy_match": True,
                    "open":        oc["open"],
                })
            else:
                missing.append(oc)

    orphan_bot = unmatched_bot  # in bot log but no on-chain match

    return {
        "matched":     matched,
        "missing":     missing,       # on-chain, missing from bot
        "orphan_bot":  orphan_bot,    # bot log, no on-chain trade
    }


def compute_stats(trades: List[Dict], pnl_key: str = "net_pnl") -> Dict:
    closed = [t for t in trades if not t.get("open", False)]
    if not closed:
        return {"n": 0}
    wins = [t for t in closed if (t.get(pnl_key) or 0) > 0.01]
    losses = [t for t in closed if (t.get(pnl_key) or 0) < -0.01]
    total_pnl = sum(t.get(pnl_key, 0) for t in closed)
    gross_win  = sum(t.get(pnl_key, 0) for t in wins)
    gross_loss = abs(sum(t.get(pnl_key, 0) for t in losses))
    return {
        "n":             len(closed),
        "wins":          len(wins),
        "losses":        len(losses),
        "wr":            round(len(wins) / len(closed), 3) if closed else 0,
        "net_pnl":       round(total_pnl, 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "avg_win":       round(gross_win  / len(wins),   4) if wins   else 0,
        "avg_loss":      round(-gross_loss / len(losses), 4) if losses else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None,
                        help="Only look at trades since this date (YYYY-MM-DD), default=today")
    parser.add_argument("--full",  action="store_true",
                        help="Fetch full history (no date filter)")
    args = parser.parse_args()

    if args.full:
        since_ts = 0
        since_label = "all time"
    elif args.since:
        since_ts = int(datetime.strptime(args.since, "%Y-%m-%d")
                       .replace(tzinfo=timezone.utc).timestamp())
        since_label = args.since
    else:
        # default: today UTC
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since_ts = int(today.timestamp())
        since_label = today.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"Klaus ↔ Polymarket Reconciliation")
    print(f"Wallet : {WALLET}")
    print(f"Period : {since_label}")
    print(f"{'='*60}\n")

    # ── Fetch on-chain data ────────────────────────────────────────────────
    print("1. Fetching CLOB trade fills...")
    clob_fills_raw = fetch_clob_trades(WALLET, since_ts)
    print(f"   → {len(clob_fills_raw)} raw fill records")

    print("2. Fetching data-api activity...")
    activity_raw = fetch_data_api_activity(WALLET, since_ts)
    print(f"   → {len(activity_raw)} activity records")

    # normalise
    clob_fills = [normalise_clob_trade(t) for t in clob_fills_raw]
    activity   = [normalise_activity(t)   for t in activity_raw]

    # merge: prefer activity (richer), supplement with CLOB
    merged_fills = activity if activity else clob_fills
    if activity and clob_fills:
        # add CLOB fills not already in activity (by id)
        activity_ids = {f["id"] for f in activity if f["id"]}
        extra = [f for f in clob_fills if f["id"] not in activity_ids]
        merged_fills = activity + extra
        print(f"   → merged: {len(merged_fills)} fills total")

    print("3. Reconstructing trades from fills...")
    onchain_trades = group_fills_into_trades(merged_fills)
    open_count   = sum(1 for t in onchain_trades if t["open"])
    closed_count = len(onchain_trades) - open_count
    print(f"   → {len(onchain_trades)} positions ({closed_count} closed, {open_count} open)")

    # ── Load bot logs ──────────────────────────────────────────────────────
    print("4. Loading bot logs...")
    bot_trades = load_bot_trades(since_ts)
    print(f"   → {len(bot_trades)} bot trades (excl. orphans/stubs)")

    # ── Reconcile ─────────────────────────────────────────────────────────
    print("5. Reconciling...\n")
    rec = match_to_bot_log(onchain_trades, bot_trades)

    # ── Stats ──────────────────────────────────────────────────────────────
    onchain_stats = compute_stats(onchain_trades, pnl_key="net_pnl")
    bot_stats     = compute_stats(bot_trades,     pnl_key="net_pnl")

    print("─" * 60)
    print("PERFORMANCE COMPARISON")
    print("─" * 60)
    print(f"{'Metric':<25} {'On-chain':>12} {'Bot Log':>12}")
    print(f"{'─'*25} {'─'*12} {'─'*12}")
    for key in ("n", "wins", "losses", "wr", "net_pnl", "profit_factor", "avg_win", "avg_loss"):
        oc_val = onchain_stats.get(key, "n/a")
        bt_val = bot_stats.get(key, "n/a")
        print(f"{key:<25} {str(oc_val):>12} {str(bt_val):>12}")

    # ── Missing trades ─────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"MISSING FROM BOT LOG ({len(rec['missing'])} trades)")
    print(f"{'─'*60}")
    if not rec["missing"]:
        print("  ✓ None — all on-chain trades are recorded")
    else:
        for m in rec["missing"]:
            dt = datetime.fromtimestamp(m["ts_open"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            status = "OPEN" if m["open"] else f"PnL={m['net_pnl']:+.3f}"
            print(f"  {dt}  token={m['token_id'][:20]}...  entry={m['entry_price']:.4f}  "
                  f"exit={m['exit_price']:.4f}  {status}  fills=buy:{m['buy_fills']}/sell:{m['sell_fills']}")

    # ── Orphan bot records ─────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"BOT LOG HAS NO ON-CHAIN MATCH ({len(rec['orphan_bot'])} trades)")
    print(f"{'─'*60}")
    if not rec["orphan_bot"]:
        print("  ✓ None — all bot log entries have on-chain matches")
    else:
        for o in rec["orphan_bot"][:20]:  # cap at 20
            dt = datetime.fromtimestamp(o.get("ts_open", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"  {dt}  {o.get('trade_id','?'):<30}  pnl={o.get('net_pnl', 0):+.3f}  "
                  f"exit={o.get('exit_reason','?')}")
        if len(rec["orphan_bot"]) > 20:
            print(f"  ... and {len(rec['orphan_bot'])-20} more")

    # ── PnL discrepancies ──────────────────────────────────────────────────
    bad = [m for m in rec["matched"] if not m["pnl_ok"] and not m.get("open")]
    print(f"\n{'─'*60}")
    print(f"PNL DISCREPANCIES > $0.10 ({len(bad)} trades)")
    print(f"{'─'*60}")
    if not bad:
        print("  ✓ None — all matched trades have consistent PnL")
    else:
        for b in bad:
            dt = datetime.fromtimestamp(b["ts_open"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"  {dt}  token={str(b['token_id'])[:20]}...")
            print(f"       on-chain: entry={b['entry_price_onchain']:.4f}  "
                  f"exit={b['exit_price_onchain']:.4f}  pnl={b['pnl_onchain']:+.3f}")
            print(f"       bot log:  entry={b['entry_price_bot']:.4f}  "
                  f"exit={b['exit_price_bot']:.4f}  pnl={b['pnl_bot']:+.3f}  "
                  f"diff={b['pnl_diff']:+.3f}")

    # ── Matched summary ────────────────────────────────────────────────────
    good_matches = [m for m in rec["matched"] if m["pnl_ok"]]
    print(f"\n{'─'*60}")
    print(f"MATCHED OK: {len(good_matches)}/{len(rec['matched'])} trades")
    print(f"{'─'*60}")

    # ── Save results ──────────────────────────────────────────────────────
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wallet": WALLET,
        "since": since_label,
        "onchain_stats": onchain_stats,
        "bot_stats": bot_stats,
        "missing_from_bot": len(rec["missing"]),
        "orphan_in_bot": len(rec["orphan_bot"]),
        "pnl_discrepancies": len(bad),
        "matched_ok": len(good_matches),
        "details": rec,
    }
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nFull results saved → {RESULTS_FILE}")


if __name__ == "__main__":
    main()
