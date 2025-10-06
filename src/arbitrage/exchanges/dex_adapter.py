from __future__ import annotations

from typing import Dict, Any

from .base import Exchange, Ticker

try:
    from web3 import Web3  # type: ignore
except Exception:  # pragma: no cover
    Web3 = None


class DexAdapter:
    """A minimal DEX adapter scaffold.

    This is a starting point for integrating on-chain DEXs like Uniswap. It provides
    a placeholder `get_tickers` implementation (which typically requires reading
    pair reserves and deriving price) and a `place_order` method that is intentionally
    a stub because on-chain swaps require wallet signing and gas handling.
    """

    def __init__(self, rpc_url: str, name: str = 'dex'):
        # web3 is optional for the scaffold; only required if you enable live on-chain behavior
        self.name = name
        self.rpc_url = rpc_url
        self.w3 = None
        if Web3 is not None and rpc_url:
            try:
                self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            except Exception:
                self.w3 = None
        # in-memory simulated orders
        self.orders = []

    def get_tickers(self) -> Dict[str, Ticker]:
        # TODO: implement pair discovery and price derivation using on-chain reserves
        # Returning empty dict for now as a safe default.
        return {}

    def place_order(self, symbol: str, side: str, amount: float) -> str:
        """Simulate or (optionally) perform a live on-chain swap.

        Safe behavior (default): when the environment variable ALLOW_LIVE_ONCHAIN != '1',
        this method will simulate the swap and return a synthetic order id.

        If ALLOW_LIVE_ONCHAIN == '1' and web3 + RPC + PRIVATE_KEY are configured, the
        live path is intentionally left as NotImplemented (requires careful signing and
        router integration). This keeps the default behavior safe-for-local-testing.
        """
        import os

        allow_live = os.environ.get('ALLOW_LIVE_ONCHAIN', '0') == '1'
        # simple estimated gas for an on-chain swap (rough default)
        estimated_gas = 200_000

        if not allow_live:
            # Simulate swap: create a synthetic id and record a simulated order
            oid = f"sim-{self.name}-{len(self.orders)+1}"
            # estimate output price simply as placeholder: use amount * 1 for now
            # In a real implementation you'd query pair reserves to compute expected output
            simulated = {
                "id": oid,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "estimated_gas": estimated_gas,
                "note": "simulated (ALLOW_LIVE_ONCHAIN not enabled)",
            }
            self.orders.append(simulated)
            return oid

        # live-path guard: only allow if we have web3 and rpc and private key
        priv = os.environ.get('PRIVATE_KEY')
        if self.w3 is None or not self.rpc_url or not priv:
            raise NotImplementedError("Live on-chain swaps require RPC and PRIVATE_KEY; set ALLOW_LIVE_ONCHAIN=1 and configure env vars")

        # Live on-chain token-to-token swap implementation (Uniswap V2 style)
        # NOTE: This is a minimal implementation for demonstration. Use at your own risk.
        from eth_account import Account  # type: ignore
        from web3 import Web3  # type: ignore
        import time
        # minimal ABIs for ERC20 approval and UniswapV2 router swapExactTokensForTokens
        ERC20_ABI = [
            {
                'constant': False,
                'inputs': [{'name': '_spender', 'type': 'address'}, {'name': '_value', 'type': 'uint256'}],
                'name': 'approve',
                'outputs': [{'name': '', 'type': 'bool'}],
                'type': 'function',
            },
            {
                'constant': True,
                'inputs': [{'name': '_owner', 'type': 'address'}, {'name': '_spender', 'type': 'address'}],
                'name': 'allowance',
                'outputs': [{'name': '', 'type': 'uint256'}],
                'type': 'function',
            },
        ]
        UNISWAP_ROUTER_ABI = [
            {
                'constant': False,
                'inputs': [
                    {'name': 'amountIn', 'type': 'uint256'},
                    {'name': 'amountOutMin', 'type': 'uint256'},
                    {'name': 'path', 'type': 'address[]'},
                    {'name': 'to', 'type': 'address'},
                    {'name': 'deadline', 'type': 'uint256'},
                ],
                'name': 'swapExactTokensForTokens',
                'outputs': [{'name': 'amounts', 'type': 'uint256[]'}],
                'type': 'function',
            }
        ]

        # Expect symbol as 'tokenIn/tokenOut' where token addresses are used
        parts = symbol.split('/')
        if len(parts) != 2:
            raise NotImplementedError("Live swaps require symbol in 'tokenIn/tokenOut' address format")
        token_in, token_out = parts[0], parts[1]

        router_addr = os.environ.get('UNISWAP_ROUTER_ADDRESS')
        if not router_addr:
            raise NotImplementedError('UNISWAP_ROUTER_ADDRESS env var must be set for live on-chain swaps')

        acct = Account.from_key(priv)
        account_addr = acct.address

        # instantiate router contract
        router = self.w3.eth.contract(address=Web3.to_checksum_address(router_addr), abi=UNISWAP_ROUTER_ABI)

        # path and amounts
        path = [Web3.to_checksum_address(token_in), Web3.to_checksum_address(token_out)]

        # estimate min amount out using on-chain reserves
        amount_out_est = self.estimate_output(token_in, token_out, amount)
        if amount_out_est is None:
            raise RuntimeError('Could not estimate output amount')
        # apply slippage tolerance (e.g., 1%)
        min_amount_out = int(amount_out_est * 0.99)

        deadline = int(time.time()) + 600

        # Ensure token_in approval
        erc20 = self.w3.eth.contract(address=Web3.to_checksum_address(token_in), abi=ERC20_ABI)
        allowance = erc20.functions.allowance(account_addr, router_addr).call()
        if allowance < int(amount):
            # need to approve
            tx = erc20.functions.approve(router_addr, int(2**256-1)).build_transaction({
                'from': account_addr,
                'nonce': self.w3.eth.get_transaction_count(account_addr),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
            })
            signed = Account.sign_transaction(tx, priv)
            txh = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            self.w3.eth.wait_for_transaction_receipt(txh)

        # build swap transaction
        tx = router.functions.swapExactTokensForTokens(
            int(amount), int(min_amount_out), path, account_addr, deadline
        ).build_transaction({
            'from': account_addr,
            'nonce': self.w3.eth.get_transaction_count(account_addr),
            'gas': 300000,
            'gasPrice': self.w3.eth.gas_price,
        })

        signed = Account.sign_transaction(tx, priv)
        txh = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return self.w3.to_hex(txh)

    def estimate_output(self, token_in: str, token_out: str, amount_in: float) -> int | None:
        """Estimate output token amount using pair reserves (Uniswap V2 formula).

        Returns estimated integer output or None if unavailable.
        """
        if self.w3 is None:
            return None
        from web3 import Web3  # type: ignore

        # minimal ABIs
        FACTORY_ABI = [
            {
                'inputs': [{'internalType': 'address', 'name': 'tokenA', 'type': 'address'}, {'internalType': 'address', 'name': 'tokenB', 'type': 'address'}],
                'name': 'getPair',
                'outputs': [{'internalType': 'address', 'name': 'pair', 'type': 'address'}],
                'stateMutability': 'view',
                'type': 'function',
            }
        ]
        PAIR_ABI = [
            {'inputs': [], 'name': 'getReserves', 'outputs': [{'internalType': 'uint112','name':'reserve0','type':'uint112'},{'internalType':'uint112','name':'reserve1','type':'uint112'},{'internalType':'uint32','name':'blockTimestampLast','type':'uint32'}],'stateMutability':'view','type':'function'},
            {'inputs': [], 'name': 'token0', 'outputs':[{'internalType':'address','name':'','type':'address'}],'stateMutability':'view','type':'function'},
        ]

        factory_addr = os.environ.get('UNISWAP_FACTORY_ADDRESS')
        if not factory_addr:
            return None
        factory = self.w3.eth.contract(address=Web3.to_checksum_address(factory_addr), abi=FACTORY_ABI)
        pair_addr = factory.functions.getPair(Web3.to_checksum_address(token_in), Web3.to_checksum_address(token_out)).call()
        if int(pair_addr, 16) == 0:
            return None
        pair = self.w3.eth.contract(address=pair_addr, abi=PAIR_ABI)
        try:
            reserves = pair.functions.getReserves().call()
            token0 = pair.functions.token0().call()
        except Exception:
            return None
        # reserves: (reserve0, reserve1)
        if Web3.to_checksum_address(token0) == Web3.to_checksum_address(token_in):
            reserve_in, reserve_out = reserves[0], reserves[1]
        else:
            reserve_in, reserve_out = reserves[1], reserves[0]

        # Uniswap V2 formula with 0.3% fee
        amount_in_with_fee = int(amount_in) * 997
        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in * 1000 + amount_in_with_fee
        if denominator == 0:
            return None
        amount_out = numerator // denominator
        return amount_out
