"""
On-chain YES+NO pair merge for proxy-wallet (SIGNATURE_TYPE=1) accounts.

A held YES+NO pair on the same conditionId is $1/share of collateral locked
until resolution. NegRiskAdapter.mergePositions(conditionId, amount) converts
the pair back to USDC immediately — badatmath's cash-velocity engine (~50% of
his deployment recycles same-day via merge, re-audit 2026-06-11).

Mechanics (verified on-chain 2026-06-11):
  - Our funder is an EIP-1167 minimal proxy (impl 0x44e999d5…) made by the
    Polymarket ProxyWalletFactory. The factory's `proxy(ProxyCall[])` derives
    the wallet from msg.sender (CREATE2 over keccak(owner)) — so the owner EOA
    can execute through its proxy DIRECTLY, paying its own gas. No GSN needed.
  - The proxy has already setApprovalForAll(NegRiskAdapter) on the CTF.
  - Gas: the EOA needs a little POL/MATIC. Zero balance → merge logs a
    one-time funding hint and returns False (everything else keeps working;
    pairs still pay $1 at resolution, merge only accelerates the cash).

All calls are synchronous web3 — run via asyncio.to_thread from async code.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

POLYGON_RPC = os.getenv("POLYGON_RPC", "https://1rpc.io/matic")
PROXY_FACTORY = "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# ProxyWalletFactory.proxy(ProxyCall[]) — ProxyCall{uint8 typeCode, address to,
# uint256 value, bytes data}; CallType: 0 INVALID, 1 CALL, 2 DELEGATECALL.
FACTORY_ABI = [{
    "name": "proxy", "type": "function", "stateMutability": "payable",
    "inputs": [{"name": "calls", "type": "tuple[]", "components": [
        {"name": "typeCode", "type": "uint8"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
    ]}],
    "outputs": [{"type": "bytes[]"}],
}]
ADAPTER_ABI = [{
    "name": "mergePositions", "type": "function", "stateMutability": "nonpayable",
    "inputs": [{"name": "_conditionId", "type": "bytes32"},
               {"name": "_amount", "type": "uint256"}],
    "outputs": [],
}]
CTF_ABI = [
    {"name": "mergePositions", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "collateralToken", "type": "address"},
                {"name": "parentCollectionId", "type": "bytes32"},
                {"name": "conditionId", "type": "bytes32"},
                {"name": "partition", "type": "uint256[]"},
                {"name": "amount", "type": "uint256"}],
     "outputs": []},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"},
                {"name": "id", "type": "uint256"}],
     "outputs": [{"type": "uint256"}]},
]


class ProxyMerger:
    """Merges held YES+NO pairs back to USDC through the proxy wallet."""

    def __init__(self, private_key: str, proxy_wallet: str,
                 rpc: str = POLYGON_RPC) -> None:
        self._pk = private_key
        self._proxy = proxy_wallet
        self._rpc = rpc
        self._no_gas_logged = False

    def merge(self, condition_id: str, yes_token: str, no_token: str,
              shares: float, neg_risk: bool = True) -> float:
        """Merge min(shares, on-chain pair balance) of condition_id.
        Returns the SHARES actually merged (0.0 on failure/skip)."""
        try:
            from web3 import Web3
            from eth_account import Account
        except ImportError:
            logger.error("[MERGE] web3/eth_account not installed")
            return 0.0

        w3 = Web3(Web3.HTTPProvider(self._rpc, request_kwargs={"timeout": 20}))
        if not w3.is_connected():
            logger.warning("[MERGE] Polygon RPC not reachable (%s)", self._rpc)
            return 0.0
        acct = Account.from_key(self._pk)

        # gas gate — one-time hint, nothing else breaks without it
        if w3.eth.get_balance(acct.address) < 5 * 10**15:  # < 0.005 POL
            if not self._no_gas_logged:
                self._no_gas_logged = True
                logger.warning(
                    "[MERGE] EOA %s has <0.005 POL — merges blocked until funded "
                    "(~$2 of POL covers months; pairs still pay $1 at resolution)",
                    acct.address)
            return 0.0

        ctf = w3.eth.contract(address=w3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
        proxy = w3.to_checksum_address(self._proxy)
        # clamp to the real on-chain pair balance (accounting drift safety)
        try:
            bal_y = ctf.functions.balanceOf(proxy, int(yes_token)).call()
            bal_n = ctf.functions.balanceOf(proxy, int(no_token)).call()
        except Exception as e:
            logger.warning("[MERGE] balanceOf failed: %s", e)
            return 0.0
        amount = min(int(round(shares * 1e6)), bal_y, bal_n)
        if amount < 10**6:  # < 1 share
            logger.info("[MERGE] %s pair balance too small (y=%d n=%d req=%.1f)",
                        condition_id[:10], bal_y, bal_n, shares)
            return 0.0

        cond = bytes.fromhex(condition_id.removeprefix("0x"))
        if neg_risk:
            adapter = w3.eth.contract(
                address=w3.to_checksum_address(NEG_RISK_ADAPTER), abi=ADAPTER_ABI)
            inner = adapter.encode_abi("mergePositions", args=[cond, amount])
            target = w3.to_checksum_address(NEG_RISK_ADAPTER)
        else:
            inner = ctf.encode_abi("mergePositions", args=[
                w3.to_checksum_address(USDC_ADDRESS), b"\x00" * 32, cond,
                [1, 2], amount])
            target = w3.to_checksum_address(CTF_ADDRESS)

        factory = w3.eth.contract(
            address=w3.to_checksum_address(PROXY_FACTORY), abi=FACTORY_ABI)
        fn = factory.functions.proxy([(1, target, 0, bytes.fromhex(inner[2:]))])
        try:
            gas = int(fn.estimate_gas({"from": acct.address}) * 1.3)
        except Exception as e:
            logger.warning("[MERGE] gas estimate failed (%s) — aborting, not "
                           "sending blind", str(e)[:120])
            return 0.0
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gasPrice": int(w3.eth.gas_price * 1.2),
            "gas": gas,
            "chainId": 137,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
        merged = amount / 1e6
        if receipt.status == 1:
            logger.warning("[MERGE] OK %s: %.2f sh → $%.2f collateral (tx %s gas %d)",
                           condition_id[:10], merged, merged,
                           tx_hash.hex()[:14], receipt.gasUsed)
            return merged
        logger.error("[MERGE] tx REVERTED %s (tx %s)", condition_id[:10], tx_hash.hex())
        return 0.0
