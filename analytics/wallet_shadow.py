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
    # Tennis negative-risk arb specialist. /value=$63k, +$1.6k cash PnL today.
    "Eulhunter": "0x98db8cca55c32b24cfb414b5b43d273f4e1fdd17",
    # Tennis arb, smaller. /value=$13k, 45% WR, +$4.4k realized.
    "tradecraft": "0xde9f7f4e77a1595623ceb58e469f776257ccd43c",
    # Long-tail NO grinder, multi-category. /value=$64k. realized +$306k.
    # Buys NO at 0.97-0.999 on "will rare-event happen by date" markets.
    "melchior1248": "0x36901eb0f21519cc9055662a6d2483e96da1e16f",
    # Politics + NO-on-certainty grinder. /value=$35k, 73% WR, +$2.8k cash.
    "vinii": "0x1ee9a5fc09665909c0cce297c581703bfbb9197f",
    # Crypto-only target specialist. /value=$373k, 234 pos, 65% WR, +$150k realized.
    # Buys YES at 0.95-0.99 on BTC/ETH "above $X by date" near-certain targets.
    "crypto_specialist_6E1d": "0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa",
    # Updown 15m passive limit-order scalper. /value=$263, +$33k realized.
    # 1935 BUYs / 0 SELLs across both UP and DOWN, micro-stakes — the rare wallet
    # making money on the same market our bot loses on.
    "sixx7": "0xee55214ee3a9ee22a404663c76ca832577df7b04",
    # UK politics specialist. /value=$55k, 290 pos, 59% WR, +$8k cash PnL.
    "buoys": "0x7e35a2a8cfd1eb1e69dacd043206db5a787f1a6c",
    # Politics + macro grinder. /value=$10k, 41% WR, +$2.7k cash.
    "cwc909": "0x8db4f2bcb37078763c70dac5d99c285995479c07",
    # Best WR signal in our sample: 78% WR, /value=$187k, +$24k pnl, only 27 positions
    # (highly selective; UFC, NBA, WTI futures).
    "selective_5F45": "0x5f45b60c29d6e4d55c0bfd8ddd39ad45c5e0a77a",
    # +756% ROI on $602 staked — geopolitical longshot NO at <0.05 entry. 7/7 WR.
    "outlier_756pct_geo": "0x2e0ab2ff6c513dc62870a0a7176186380222e172",
    # +172% ROI on $22.8k — multi-cat longshot NO grinder, 500 pos, avg_stake=$406.
    "outlier_172pct_multi": "0x91d757346e322976a9544dd07b9b7e3f58550dfc",
    # +75% ROI on $2.4k — LoL esports concentrated convictions, 100% WR.
    "esports_75pct": "0xea58b24f4add059c8e368d7318d3c30a4704930f",
    # mr.ozi: $56k profit, 85% WR on geopolitics. /value=$539k.
    "mr_ozi_geo": "0x614dc8d3542c12103d2c6a3553fd761e391d1546",
    # +262k profit, 64% WR on politics, /value=$520k. High-WR politics grinder.
    "politics_64wr_011f": "0x011f2d377e56119fb09196dffb0948ae55711122",
    # ---- Verified positive realized + non-negative cash (strict bar) ----
    # politics, 85% WR, realized +$110k, cash +$38k, /value=$547k — exceptional WR signal.
    "politics_85wr_0c0e": "0x0c0e270cf879583d6a0142fc817e05b768d0434e",
    # soccer specialist (best-cluster 38% profitable rate), realized +$105k, cash +$13k.
    "soccer_fe94": "0xfe9455e2cad5257b26547af62cbbfd75c8968a3d",
    # "other"/multi-cat, 51% WR, realized +$62k on 43 pos, /value=$42k.
    "other_51wr_05ab": "0x05ab749a8554fb7c852238c271d384bae6798145",
    # politics, 54% WR over 240 positions, realized +$21k, cash +$1.4k.
    "politics_54wr_bad2": "0xbad26fe5458e6219cec3e40272760e275e835296",
    # ---- High-realized whales (for cluster breadth, not necessarily replicable) ----
    # politics, 34% WR, 188 pos, realized +$313k, cash near-flat.
    "politics_whale_24c8": "0x24c8cf69a0e0a17eee21f69d29752bfa32e823e1",
    # politics, 45% WR, 500 pos, realized +$309k, cash near-flat.
    "politics_whale_4e25": "0x4e25605fd905e9972efc0f4d8814530c655cd7a7",
    # politics, 52% WR, 130 pos, realized +$49k, cash near-flat.
    "politics_52wr_7c3d": "0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b",
    # politics, 33% WR, 105 pos, realized +$84k.
    "politics_33wr_0042": "0x00425c692a667981118f679ef68fdc775257321e",
    # politics, 27% WR, 500 pos, realized +$47k. "Bikesarethebest".
    "Bikesarethebest": "0x0a6d26d31b28fd5a84c301f8b27296612f3b1d0a",
    # geopolitics, 43% WR, 65 pos, realized +$37k.
    "geo_43wr_44c1": "0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1",
    # other, 45% WR, 500 pos, realized +$140k. "swisstony".
    "swisstony": "0x204f72f35326db932158cba6adff0b9a1da95e14",
    # basketball, 4% WR longshot specialist, realized +$113k. "CavaSoTasty".
    "CavaSoTasty": "0x7fea691e28d169a33c500607279f2acb49058f74",
    # updown grinder, realized +$20k, similar pattern to sixx7. "fluffyfluffyfluffy".
    "fluffyfluffyfluffy": "0xc76f85c258044adea3167f4ee7b29c24c4eba5db",
    # politics, 22% WR, 500 pos, realized +$22k.
    "politics_22wr_21ff": "0x21ffd2b7a212a6f277ed3eca1a9f8efcbca90d71",
    # geopolitics, 40% WR, 500 pos, realized +$127k.
    "geo_40wr_d49b": "0xd49b42bce7ea10bac53e2901c188cae20ea4bdf9",
}

# Wallets that trade in same-second clusters (arb / scalp / HFT). We poll these
# aggressively — but note REST gives integer-second timestamps, so true sub-second
# resolution requires WebSocket which is not implemented here.
FAST_POLL_WALLETS = {
    "Eulhunter", "tradecraft",            # tennis taker-arb scalpers
    "sixx7", "fluffyfluffyfluffy",        # 15m updown both-side scalpers
    "outlier_172pct_multi",                # multi-market high-frequency
    "esports_75pct",                       # LoL concentrated rapid bets
    # Moved from SLOW after observing high event rate in first 6 min post-restart:
    "crypto_specialist_6E1d",              # 32 events in 6 min on SLOW tier
    "swisstony",                           # 21 events in 6 min on SLOW tier
}
FAST_POLL_S = 4.0
SLOW_POLL_S = 30.0
ACTIVITY_POLL_S = 30.0   # /activity poll for REDEEM + MERGE — these don't show in /trades
POLL_S = SLOW_POLL_S  # legacy fallback if FAST_POLL_WALLETS not used
LOG_DIR = Path("/root/Klaus/logs/shadow/hot")
LOG_NAME = "wallet_shadow.jsonl"
STATE_FILE = Path("/root/Klaus/logs/shadow/wallet_shadow_state.json")

logger = logging.getLogger("wallet_shadow")


@dataclass
class State:
    last_trade_ts: Dict[str, int] = field(default_factory=dict)
    last_activity_ts: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            try:
                raw = json.loads(STATE_FILE.read_text())
                # Tolerate older state files that don't have last_activity_ts
                if "last_activity_ts" not in raw:
                    raw["last_activity_ts"] = {}
                return cls(**raw)
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


def fetch_activity_events(session: requests.Session, wallet: str, after_ts: int) -> List[dict]:
    """Pull recent /activity for a wallet, return REDEEM + MERGE events newer than after_ts.

    REDEEM = winning shares converted to $1 each (after resolution).
    MERGE  = YES+NO pair burned for $1 each (instant exit, pre-resolution).

    These are the exit mechanisms for arb wallets. They DO NOT appear in /trades.
    """
    try:
        r = session.get(
            f"{DATA_API}/activity",
            params={"user": wallet, "limit": 100},
            timeout=15,
        )
        if r.status_code != 200:
            logger.warning("activity http %s for %s", r.status_code, wallet[:14])
            return []
        d = r.json()
    except Exception as exc:
        logger.warning("activity fetch failed %s: %s", wallet[:14], exc)
        return []
    if not isinstance(d, list):
        return []
    out = []
    for a in d:
        atype = (a.get("type") or "").upper()
        if atype not in ("REDEEM", "MERGE"):
            continue
        ts = int(a.get("timestamp") or 0)
        if ts > after_ts:
            out.append(a)
    out.sort(key=lambda a: int(a.get("timestamp") or 0))
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


def poll_activity_once(session: requests.Session, state: State, observed_ts: int) -> int:
    """One pass over all wallets — captures REDEEM + MERGE only. Returns count logged."""
    n_new = 0
    out_path = log_path()
    for name, wallet in WALLETS.items():
        last = state.last_activity_ts.get(wallet, observed_ts)
        events = fetch_activity_events(session, wallet, last)
        if not events:
            continue
        for a in events:
            ts = int(a.get("timestamp") or 0)
            atype = (a.get("type") or "").upper()
            ev = {
                "rec": f"wallet_{atype.lower()}",   # wallet_redeem | wallet_merge
                "wallet_name": name,
                "wallet": wallet,
                "ts": ts,
                "iso": datetime.utcfromtimestamp(ts).isoformat() if ts else None,
                "polled_at": time.time(),
                "type": atype,
                "asset": a.get("asset"),
                "condition_id": a.get("conditionId"),
                "slug": a.get("slug"),
                "outcome": a.get("outcome"),
                "outcome_index": a.get("outcomeIndex"),
                "size": float(a.get("size", 0) or 0),
                "price": float(a.get("price", 0) or 0),
                "usdc_size": float(a.get("usdcSize", 0) or 0),
                "transaction_hash": a.get("transactionHash"),
            }
            record_event(out_path, ev)
            n_new += 1
            state.last_activity_ts[wallet] = ts
    if n_new:
        state.save()
    return n_new


def poll_once(session: requests.Session, state: State, observed_ts: int,
              wallet_subset: Optional[dict] = None) -> int:
    """One pass over wallet_subset (or all WALLETS). Returns number of new trades logged."""
    n_new = 0
    out_path = log_path()
    targets = wallet_subset if wallet_subset is not None else WALLETS
    for name, wallet in targets.items():
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

    fast_subset = {n: w for n, w in WALLETS.items() if n in FAST_POLL_WALLETS}
    slow_subset = {n: w for n, w in WALLETS.items() if n not in FAST_POLL_WALLETS}

    # Seed activity timestamps too (don't backfill years of REDEEM/MERGE on first run)
    for wallet in WALLETS.values():
        if wallet not in state.last_activity_ts:
            state.last_activity_ts[wallet] = seed_ts
    state.save()

    logger.info("wallet_shadow start — %d wallets total: %d FAST (%.1fs) + %d SLOW (%.1fs); activity-poll every %.1fs",
                len(WALLETS), len(fast_subset), FAST_POLL_S, len(slow_subset), SLOW_POLL_S, ACTIVITY_POLL_S)
    logger.info("logs → %s", LOG_DIR / "<date>" / LOG_NAME)
    logger.warning("REST timestamps are integer-second resolution; sub-second fills "
                   "cannot be captured. For ms-level capture, WebSocket subscription "
                   "to each tracked wallet's markets would be required.")
    logger.info("activity poll captures REDEEM + MERGE events (not in /trades — these are exit mechanisms for arb wallets)")

    # Interleaved scheduling: fast tier, slow tier, activity tier, each with its own deadline.
    next_fast = time.time()
    next_slow = time.time()
    next_act = time.time()
    while True:
        now = time.time()
        try:
            if now >= next_fast:
                n_fast = poll_once(session, state, seed_ts, wallet_subset=fast_subset)
                if n_fast:
                    logger.info("FAST tier: %d new trade(s)", n_fast)
                next_fast = now + FAST_POLL_S
            if now >= next_slow:
                n_slow = poll_once(session, state, seed_ts, wallet_subset=slow_subset)
                if n_slow:
                    logger.info("SLOW tier: %d new trade(s)", n_slow)
                next_slow = now + SLOW_POLL_S
            if now >= next_act:
                n_act = poll_activity_once(session, state, seed_ts)
                if n_act:
                    logger.info("ACTIVITY tier: %d new REDEEM/MERGE event(s)", n_act)
                next_act = now + ACTIVITY_POLL_S
        except Exception as exc:
            logger.exception("poll failed: %s", exc)
        sleep_for = max(0.5, min(next_fast, next_slow, next_act) - time.time())
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
