"""
Wallet shadow logger — passive, no trading.

Polls /trades?user= for a configured set of wallets every WALLET_POLL_S seconds.
Logs new trades + a book snapshot at trade-time to logs/shadow/hot/<date>/wallet_shadow.jsonl
so we can later analyse: (a) replicate-feasibility, (b) which wallets show edge across days.

Built 2026-05-12 after [[project-wallet-research-v2]] showed Eulhunter is the one
verifiable winner across 120 wallets surveyed. This recorder lets us validate that
finding over time without putting capital at risk.

Run standalone:
    python3 -m analytics.wallet_shadow

Tracked wallets are defined in WALLETS below. Add/remove there.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

DATA_API = "https://data-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

WALLETS: Dict[str, str] = {
    "Eulhunter": "0x98db8cca55c32b24cfb414b5b43d273f4e1fdd17",
}

POLL_S = 20.0
LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
LOG_NAME = "wallet_shadow.jsonl"
STATE_FILE = Path("/root/Klaus/logs/shadow/wallet_shadow_state.json")

logger = logging.getLogger("wallet_shadow")


@dataclass
class State:
    last_trade_ts: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            try:
                return cls(**json.loads(STATE_FILE.read_text()))
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(asdict(self)))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log_path() -> Path:
    d = utcnow().strftime("%Y-%m-%d")
    p = LOG_DIR / d / LOG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch_trades(session: requests.Session, wallet: str, after_ts: int) -> List[dict]:
    """Pull recent trades for a wallet; return those with timestamp > after_ts, oldest first."""
    try:
        r = session.get(
            f"{DATA_API}/trades",
            params={"user": wallet, "limit": 100},
            timeout=15,
        )
        if r.status_code != 200:
            logger.warning("trades http %s for %s", r.status_code, wallet[:14])
            return []
        d = r.json()
    except Exception as exc:
        logger.warning("trades fetch failed %s: %s", wallet[:14], exc)
        return []
    if not isinstance(d, list):
        return []
    out = [t for t in d if int(t.get("timestamp") or 0) > after_ts]
    out.sort(key=lambda t: int(t.get("timestamp") or 0))
    return out


def fetch_book(session: requests.Session, token_id: str) -> Optional[dict]:
    """Snapshot best 5 levels of the book for replicate-feasibility analysis."""
    try:
        r = session.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=8)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:
        return None
    asks = [(float(a["price"]), float(a["size"])) for a in (d.get("asks") or [])[:5]]
    bids = [(float(b["price"]), float(b["size"])) for b in (d.get("bids") or [])[:5]]
    return {"asks": asks, "bids": bids}


def fetch_opposite_token(session: requests.Session, condition_id: str, this_token: str) -> Optional[str]:
    """For a 2-outcome market, return the other token id (so we can record the other side too)."""
    try:
        r = session.get(f"{GAMMA_API}/markets", params={"condition_ids": condition_id}, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        if isinstance(d, list) and d:
            d = d[0]
        cids = d.get("clobTokenIds")
        if isinstance(cids, str):
            cids = json.loads(cids)
        if not cids or len(cids) != 2:
            return None
        for c in cids:
            if str(c) != str(this_token):
                return str(c)
    except Exception:
        return None
    return None


def record_event(out_path: Path, ev: dict) -> None:
    line = json.dumps(ev, separators=(",", ":"), default=str)
    with out_path.open("a") as f:
        f.write(line + "\n")


def poll_once(session: requests.Session, state: State, observed_ts: int) -> int:
    """One pass over all wallets. Returns number of new trades logged."""
    n_new = 0
    out_path = log_path()
    for name, wallet in WALLETS.items():
        last = state.last_trade_ts.get(wallet, observed_ts)
        trades = fetch_trades(session, wallet, last)
        if not trades:
            continue
        for t in trades:
            ts = int(t.get("timestamp") or 0)
            token_id = str(t.get("asset") or "")
            condition_id = t.get("conditionId") or ""
            this_book = fetch_book(session, token_id) if token_id else None
            opp_token = fetch_opposite_token(session, condition_id, token_id) if condition_id and token_id else None
            opp_book = fetch_book(session, opp_token) if opp_token else None
            ev = {
                "rec": "wallet_trade",
                "wallet_name": name,
                "wallet": wallet,
                "ts": ts,
                "iso": datetime.utcfromtimestamp(ts).isoformat() if ts else None,
                "polled_at": time.time(),
                "side": t.get("side"),
                "asset": token_id,
                "condition_id": condition_id,
                "size": float(t.get("size", 0) or 0),
                "price": float(t.get("price", 0) or 0),
                "notional": float(t.get("size", 0) or 0) * float(t.get("price", 0) or 0),
                "slug": t.get("slug"),
                "outcome": t.get("outcome"),
                "outcome_index": t.get("outcomeIndex"),
                "transaction_hash": t.get("transactionHash"),
                "book_this": this_book,
                "opp_token": opp_token,
                "book_opp": opp_book,
            }
            record_event(out_path, ev)
            n_new += 1
            state.last_trade_ts[wallet] = ts
    if n_new:
        state.save()
    return n_new


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    state = State.load()
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    # On first run, seed last_trade_ts to "now" so we don't backfill the entire history.
    seed_ts = int(time.time())
    for wallet in WALLETS.values():
        if wallet not in state.last_trade_ts:
            state.last_trade_ts[wallet] = seed_ts
    state.save()

    logger.info("wallet_shadow start — tracking %d wallets, poll=%ss", len(WALLETS), POLL_S)
    logger.info("logs → %s", LOG_DIR / "<date>" / LOG_NAME)

    while True:
        try:
            n = poll_once(session, state, seed_ts)
            if n:
                logger.info("recorded %d new trade(s)", n)
        except Exception as exc:
            logger.exception("poll failed: %s", exc)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
