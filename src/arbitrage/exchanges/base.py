from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol, Optional


@dataclass
class Ticker:
    symbol: str
    price: float
    # unix timestamp in seconds (optional). If provided scanners may enforce
    # freshness constraints when comparing quotes across exchanges.
    timestamp: Optional[float] = None


class Exchange(Protocol):
    """Protocol for exchange adapters (CEX or DEX)."""

    name: str

    def get_tickers(self) -> Dict[str, Ticker]:
        """Return a mapping symbol -> Ticker for the exchange."""

    def place_order(self, symbol: str, side: str, amount: float) -> str:
        """Place an order on the exchange. Return an order id or raise on failure.

        side is 'buy' or 'sell'. Implementations may simulate or actually execute.
        """
