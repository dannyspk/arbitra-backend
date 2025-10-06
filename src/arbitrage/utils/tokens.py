from __future__ import annotations

try:
    from web3 import Web3  # type: ignore
except Exception:  # pragma: no cover - optional
    Web3 = None

"""Token helpers.

This module provides a tiny symbol->address map for common tokens and helpers
to convert between human amounts and base (integer) units. You can pass either
a token symbol (e.g. "USDC") or a token address (0x...) to the helpers. If
an RPC URL and web3 are available the code will try to query the token's
decimals() method; otherwise it falls back to the built-in map or 18.
"""

# A small, opt-in mapping of common Ethereum mainnet token symbols to addresses.
# These are provided as helpful defaults for development. In production you
# should manage canonical mappings for each chain you support.
SYMBOL_TO_ADDRESS: dict[str, str] = {
    # ERC-20 tokens (mainnet addresses)
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "DAI":  "0x6b175474e89094c44da98b954eedeac495271d0f",
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
}

# Default decimals map (keyed by lowercase address) for the symbols above.
DEFAULT_TOKEN_DECIMALS: dict[str, int] = {
    SYMBOL_TO_ADDRESS["USDC"].lower(): 6,
    SYMBOL_TO_ADDRESS["USDT"].lower(): 6,
    SYMBOL_TO_ADDRESS["DAI"].lower(): 18,
    SYMBOL_TO_ADDRESS["WETH"].lower(): 18,
}


def resolve_token_address(token: str | None) -> str | None:
    """Resolve a token symbol or address to a canonical lowercase hex address.

    Returns None if token is falsy.
    """
    if not token:
        return None
    token = token.strip()
    # already looks like an address
    if token.startswith("0x") and len(token) >= 40:
        return token.lower()
    # try symbol lookup (case-insensitive)
    addr = SYMBOL_TO_ADDRESS.get(token.upper())
    if addr:
        return addr.lower()
    return None


def get_token_decimals(token: str | None, rpc_url: str | None = None) -> int:
    """Resolve token decimals.

    token can be a symbol ("USDC") or an address (0x...). If web3 + rpc_url are
    available, the ERC-20 decimals() method will be used. Otherwise the builtin
    map is consulted and finally 18 is returned as a safe default.
    """
    addr = resolve_token_address(token)
    if not addr:
        return 18
    # try RPC/web3 lookup if available
    if Web3 is not None and rpc_url:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            ERC20_ABI = [{"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}]
            token_contract = w3.eth.contract(address=w3.to_checksum_address(addr), abi=ERC20_ABI)
            return int(token_contract.functions.decimals().call())
        except Exception:
            # fall through to local map
            pass
    return DEFAULT_TOKEN_DECIMALS.get(addr.lower(), 18)


def human_to_base(amount: float, token: str | None, rpc_url: str | None = None) -> int:
    """Convert a human amount (e.g. 1.5 USDC) to base units (int)."""
    decimals = get_token_decimals(token, rpc_url)
    return int(amount * (10 ** decimals))


def base_to_human(amount_base: int, token: str | None, rpc_url: str | None = None) -> float:
    """Convert base units (int) to a human amount (float)."""
    decimals = get_token_decimals(token, rpc_url)
    return amount_base / (10 ** decimals)
