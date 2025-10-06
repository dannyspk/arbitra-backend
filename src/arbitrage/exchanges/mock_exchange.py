from __future__ import annotations

from typing import Dict, Optional
import time

from .base import Exchange, Ticker


class MockExchange:
    def __init__(self, name: str, prices: Dict[str, float], *, fee_rate: float = 0.001, withdraw_fee: float = 0.0, depth: float = 1.0, withdraw_enabled: bool = True, deposit_enabled: bool = True):
        """Create a mock exchange.

        - fee_rate: fractional taker fee applied to trades (e.g. 0.001 = 0.1%)
        - withdraw_fee: flat withdrawal fee in quote currency
        - depth: multiplier controlling synthetic orderbook sizes
        """
        self.name = name
        now = time.time()
        # store tickers as symbol -> Ticker (include a timestamp)
        self._tickers = {s: Ticker(s, p, timestamp=now) for s, p in prices.items()}
        self.orders = []
        # optional synthetic order book depth multiplier (1.0 default)
        self.depth = depth
        # trading fee (fraction)
        self.fee_rate = fee_rate
        # withdrawal fee (flat, in quote currency)
        self.withdraw_fee = withdraw_fee
        # whether this exchange allows withdrawals/deposits for coins (mock flags)
        self.withdraw_enabled = withdraw_enabled
        self.deposit_enabled = deposit_enabled

    def get_tickers(self) -> Dict[str, Ticker]:
        return self._tickers

    def place_order(self, symbol: str, side: str, amount: float) -> str:
        oid = f"mock-{len(self.orders)+1}"
        self.orders.append({"id": oid, "symbol": symbol, "side": side, "amount": amount})
        return oid

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        """Return a synthetic order book for the symbol.

        Produces 'asks' (price,size) ascending and 'bids' (price,size) descending around the
        ticker price. Size is scaled by self.depth.
        """
        tk = self._tickers.get(symbol)
        if not tk:
            return {"asks": [], "bids": []}
        mid = tk.price
        asks = []
        bids = []
        # create depth levels with small incremental price steps
        for i in range(1, depth + 1):
            step = 0.001 * i * mid * 0.001  # tiny percent steps
            price_ask = mid + step
            price_bid = mid - step
            size = max(0.001, (1.0 / i) * self.depth)
            asks.append((price_ask, size))
            bids.append((price_bid, size))
        # bids should be sorted descending
        bids = sorted(bids, key=lambda x: x[0], reverse=True)
        return {"asks": asks, "bids": bids}

    # Convenience helpers to let the scanner query deposit/withdraw availability
    def supports_withdraw(self, base_symbol: str) -> bool:
        # In the mock exchange we model this via a simple flag
        return bool(self.withdraw_enabled)

    def supports_deposit(self, base_symbol: str) -> bool:
        return bool(self.deposit_enabled)
