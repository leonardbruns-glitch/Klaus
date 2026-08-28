"""
Redemption loop for positions held to window outcome.

SIGNATURE_TYPE=1 (proxy wallet / Magic account):
  The proxy wallet holds CTF tokens after resolution. On-chain direct calls
  require the Polymarket GSN relayer (no MATIC, proxy owned by GSN module).
  Strategy: call update_balance_allowance to refresh token approval, then post
  a limit sell at 0.99. Polymarket's CLOB briefly accepts orders right after
  resolution. Polymarket also auto-redeems winning positions via their backend.

SIGNATURE_TYPE=0 (EOA direct):
  EOA holds tokens directly. Call CTF.redeemPositions via web3.
  Requires a small amount of MATIC for gas on Polygon.

Run via asyncio: asyncio.create_task(redeemer.run_loop())
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://1rpc.io/matic")
CONFIRMED_WINNERS_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "confirmed_winners.json")

CTF_ABI = [
    {
        "name": "redeemPositions",
        "type": "function",
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
]


class Redeemer:
    """
    Polls for resolved winning positions and redeems them.

    For SIGNATURE_TYPE=1: refreshes approval + posts a limit sell at 0.99.
    For SIGNATURE_TYPE=0: calls CTF.redeemPositions via web3.
    """

    def __init__(
        self,
        clob_client,
        proxy_wallet: str,
        private_key: str,
        signature_type: int = 1,
        dry_run: bool = False,
    ) -> None:
        self._client = clob_client
        self._proxy = proxy_wallet.lower()
        self._pk = private_key
        self._sig_type = signature_type
        self._dry_run = dry_run
        self._redeemed: set[str] = set()       # token_ids processed this session
        self.confirmed_winners: set[str] = self._load_confirmed_winners()

    # ── persistence ──────────────────────────────────────────────────────────

    @staticmethod
    def _load_confirmed_winners() -> set[str]:
        try:
            with open(CONFIRMED_WINNERS_FILE) as f:
                data = json.load(f)
            loaded = set(data.get("winners", []))
            if loaded:
                logger.info("REDEEM loaded %d confirmed winners from disk", len(loaded))
            return loaded
        except FileNotFoundError:
            return set()
        except Exception as exc:
            logger.warning("REDEEM failed to load confirmed_winners: %s", exc)
            return set()

    def _save_confirmed_winners(self) -> None:
        try:
            tmp = CONFIRMED_WINNERS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"winners": list(self.confirmed_winners)}, f)
            os.replace(tmp, CONFIRMED_WINNERS_FILE)
        except Exception as exc:
            logger.warning("REDEEM failed to save confirmed_winners: %s", exc)

    # ── public ────────────────────────────────────────────────────────────────

    async def run_loop(self, interval_s: float = 300.0) -> None:
        """Background task: check and redeem every `interval_s` seconds."""
        logger.info("REDEEM loop started (interval=%.0fs sig_type=%d)", interval_s, self._sig_type)
        while True:
            await asyncio.sleep(interval_s)
            try:
                await self._redeem_pending()
            except Exception as exc:
                logger.error("REDEEM loop error: %s", exc)

    # ── internals ─────────────────────────────────────────────────────────────

    async def _redeem_pending(self) -> None:
        """Fetch redeemable positions and process winning ones."""
        if not self._proxy:
            return
        try:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={"user": self._proxy},
                timeout=10,
            )
        except Exception as exc:
            logger.warning("REDEEM data-api fetch failed: %s", exc)
            return

        if resp.status_code != 200:
            logger.warning("REDEEM data-api status %d", resp.status_code)
            return

        positions = resp.json()
        # Settled winning tokens always show curPrice=0 in the data API (market closed).
        # curPrice >= 0.95 check was wrong — redeemable=True is the correct signal.
        winning = [
            p for p in positions
            if p.get("redeemable")
            and (p.get("size") or 0) > 0
            and p.get("asset") not in self._redeemed
        ]

        # UPDOWN-SNIPER holds updown tokens to redemption by design (separate
        # process, shared wallet) — its opens never reach risk.open_positions,
        # so the 0.99 CLOB-sell shortcut poaches its winners in the gap between
        # resolution and auto-redeem (07-17 08:01Z: 16.5 sh sold $16.32 vs
        # $16.50 redeemable). Same guard as main._window_end_balance_sweep;
        # fail-open: unreadable state file → empty set.
        sniper_held: set = set()
        try:
            with open("logs/updown_sniper_state.json") as snf:
                snst = json.load(snf)
            sniper_held = {
                str(v.get("token"))
                for v in (snst.get("open") or {}).values()
                if v.get("token")
            }
        except Exception:
            pass
        if sniper_held:
            n_skip = sum(1 for p in winning if str(p.get("asset")) in sniper_held)
            if n_skip:
                logger.info("REDEEM skipping %d sniper-held token(s)", n_skip)
            winning = [p for p in winning if str(p.get("asset")) not in sniper_held]

        if not winning:
            logger.debug("REDEEM no redeemable positions found")
            return
        logger.info("REDEEM found %d redeemable positions (%.2f total shares)",
                    len(winning), sum(float(p.get("size", 0)) for p in winning))

        for pos in winning:
            token_id = pos["asset"]
            cur_price = pos.get("curPrice", 0)
            size = float(pos.get("size", 0))
            logger.info(
                "REDEEM candidate: %s | size=%.4f curPrice=%.4f",
                pos.get("title", "")[:40], size, cur_price,
            )
            if self._dry_run:
                logger.info("REDEEM dry-run: skipping %s", token_id[:12])
                self._redeemed.add(token_id)
                continue
            try:
                ok = await self._redeem_one(pos)
                if ok:
                    self._redeemed.add(token_id)
            except Exception as exc:
                logger.error("REDEEM token %s failed: %s", token_id[:12], exc)

    async def _redeem_one(self, pos: dict) -> bool:
        token_id = pos["asset"]
        size = float(pos.get("size", 0))
        condition_id: Optional[str] = pos.get("conditionId")
        neg_risk: bool = bool(pos.get("negativeRisk", False))

        cur_price = float(pos.get("curPrice", 0.0))
        if self._sig_type == 0:
            # EOA direct: call CTF.redeemPositions from the EOA wallet
            ok = await self._ctf_redeem_eoa(token_id, condition_id, neg_risk)
        else:
            # Proxy wallet: refresh approval + post limit sell via CLOB
            ok = await self._clob_sell_attempt(token_id, size, cur_price)

        return ok

    async def _clob_sell_attempt(self, token_id: str, size: float, cur_price: float = 1.0) -> bool:
        """
        SIGNATURE_TYPE=1 path: refresh approval + post limit sell at 0.99.
        The CLOB accepts sell orders briefly after resolution on winning markets.
        If not filled, Polymarket auto-redeems winners via their backend.
        """
        if self._client is None:
            logger.warning("REDEEM: no CLOB client — cannot sell %s", token_id[:12])
            return False
        if size <= 0:
            logger.warning("REDEEM: size=0 for %s, skipping", token_id[:12])
            return False

        try:
            from py_clob_client_v2.clob_types import (
                BalanceAllowanceParams, AssetType, MarketOrderArgsV2,
            )
            from py_clob_client_v2.order_builder.constants import SELL as CLOB_SELL

            # Refresh conditional token approval (required before every sell)
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=token_id,
                )
            )
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                )
            )
            await asyncio.sleep(1.0)

            # Market sell: amount = shares to sell, worst_price = floor
            order = self._client.create_market_order(
                MarketOrderArgsV2(
                    token_id=token_id,
                    amount=size,
                    side=CLOB_SELL,
                    price=0.99,   # CLOB max is 0.99; 0.999 was rejected on every sell
                )
            )
            result = self._client.post_order(order)
            logger.info("REDEEM CLOB sell result: %s", result)
            return True

        except Exception as exc:
            if "does not exist" in str(exc):
                # Orderbook closed post-resolution — market settled, PM will auto-redeem.
                # Only mark as confirmed winner if curPrice>=0.95 (token resolved YES).
                # Losers (curPrice=0) also get "orderbook does not exist" but must book at 0.
                if cur_price >= 0.95:
                    logger.info(
                        "REDEEM CONFIRMED_WIN %s: orderbook gone, curPrice=%.2f — PM will auto-redeem",
                        token_id[:12], cur_price,
                    )
                    self.confirmed_winners.add(token_id)
                    self._save_confirmed_winners()
                else:
                    logger.info(
                        "REDEEM CONFIRMED_LOSS %s: orderbook gone, curPrice=%.2f — resolved NO",
                        token_id[:12], cur_price,
                    )
                return True  # stop retrying either way
            if "invalid token id" in str(exc).lower():
                # 2026-06-08: terminal — the CLOB can't sell this token (settled/invalid id).
                # PM auto-redeems winners on-chain regardless. Was looping forever (14.5k
                # errors/day on 26 stuck tokens) because this wasn't treated as terminal.
                logger.info("REDEEM terminal (invalid token id) %s — done, PM auto-redeems", token_id[:12])
                return True
            logger.warning("REDEEM CLOB sell failed %s: %s", token_id[:12], exc)
            return False

    async def _ctf_redeem_eoa(
        self, token_id: str, condition_id: Optional[str], neg_risk: bool
    ) -> bool:
        """
        SIGNATURE_TYPE=0 path: call CTF.redeemPositions from the EOA.
        Requires MATIC for gas. Checks balance before sending tx.
        """
        try:
            from web3 import Web3
            from eth_account import Account

            w3 = Web3(Web3.HTTPProvider(POLYGON_RPC, request_kwargs={"timeout": 15}))
            if not w3.is_connected():
                logger.error("REDEEM: cannot connect to Polygon RPC %s", POLYGON_RPC)
                return False

            account = Account.from_key(self._pk)
            ctf = w3.eth.contract(
                address=w3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI
            )

            token_int = int(token_id)
            balance = ctf.functions.balanceOf(account.address, token_int).call()
            if balance == 0:
                logger.warning("REDEEM EOA: balance=0 for %s", token_id[:12])
                return False

            matic_balance = w3.eth.get_balance(account.address)
            if matic_balance < 10**15:  # < 0.001 MATIC
                logger.error(
                    "REDEEM EOA: insufficient MATIC (%.6f) for gas on %s",
                    w3.from_wei(matic_balance, "ether"), token_id[:12],
                )
                return False

            if not condition_id:
                logger.error("REDEEM EOA: no condition_id for %s", token_id[:12])
                return False

            cond_bytes = bytes.fromhex(condition_id.removeprefix("0x"))
            gas_price = w3.eth.gas_price
            nonce = w3.eth.get_transaction_count(account.address)

            tx = ctf.functions.redeemPositions(
                w3.to_checksum_address(USDC_ADDRESS),
                b"\x00" * 32,
                cond_bytes,
                [1, 2],   # covers both outcome slots
            ).build_transaction({
                "from": account.address,
                "nonce": nonce,
                "gasPrice": int(gas_price * 1.2),
                "gas": 200_000,
                "chainId": 137,
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(
                "REDEEM EOA tx sent: %s | token=%s balance=%d",
                tx_hash.hex(), token_id[:12], balance,
            )
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            logger.info(
                "REDEEM EOA confirmed: status=%d gas_used=%d",
                receipt.status, receipt.gasUsed,
            )
            return receipt.status == 1

        except Exception as exc:
            logger.error("REDEEM EOA error %s: %s", token_id[:12], exc)
            return False
